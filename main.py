"""
Mnemosyne 记忆核心引擎 v5.0
认知型记忆操作系统 — 七层架构完整实现

v5.0 升级:
  - 豆包 API 全替代本地模型 (embedding-vision 1024d + seed-2.0)
  - 模型分级路由 (Tier1-5)
  - GZ 7×24 独立运行，无反向隧道依赖
  - 三馆闭环知识生产流水线 (Phase 2)
"""
import os
import sys
import asyncio
import json
import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, sys, json, uuid, math, re, time, difflib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging
logger = logging.getLogger("mnemosyne")

# ── v6.0: 受控分类词表 (category 唯一合法值) ──
# 单用户 (user_id=default) 语义收敛：10 类中文主键，英文为 API 兼容别名。
# 记忆生命周期: 写入(tmt_level=1 原始碎片) → TMT蒸馏(L2会话/L3日报/L4周报/L5画像)
# 价值分层: tier 由 reflect 按热度维护 (L1核心/L2常规/L3低频/L4待清理)
CATEGORY_WHITELIST = {
    "knowledge":   ["knowledge", "架构", "architecture", "design-pattern", "设计", "概念", "知识", "fact", "pattern", "belief"],
    "pitfall":     ["pitfall", "踩坑", "坑", "教训", "故障", "experience"],
    "reference":   ["reference", "参考", "论文", "资料", "research"],
    "project":     ["project", "项目", "进度"],
    "ops":         ["ops", "运维", "monitoring", "healthcheck", "巡检", "监控", "健康"],
    "deploy":      ["deploy", "部署", "发布", "版本", "变更"],
    "preference":  ["preference", "偏好", "喜好", "人设", "习惯"],
    "session":     ["session", "会话", "对话", "chat"],
    "worklog":     ["worklog", "note", "日志", "汇报", "工作", "记录", "notes", "general", "work"],
    "temp":        ["temp", "临时", "提醒"],
}

def normalize_category(cat: str) -> str:
    """分类归一化: 中文/旧英文 → 受控词表主键。未知分类默认 knowledge。
    匹配规则: ①全等(key/别名) ②中文别名(≥2字)子串包含。"""
    if not cat:
        return "knowledge"
    c = str(cat).strip().lower()
    # ① 全等匹配
    for key, aliases in CATEGORY_WHITELIST.items():
        if c == key or c in [a.lower() for a in aliases]:
            return key
    # ② 子串包含匹配 (中文别名 ≥2 字, 如 "论文研究"→reference)
    for key, aliases in CATEGORY_WHITELIST.items():
        for a in aliases:
            a_l = a.lower()
            if len(a_l) >= 2 and (a_l in c or c in a_l):
                return key
    return "knowledge"

# ── v5.0: 模块化导入 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PG_USER, PG_PASSWORD, PG_DB, PG_HOST, PG_PORT, HOST, PORT
from core.embedding import get_embedding_async
from core.llm import call_llm as llm_call
from core.chunker import chunk_memory as chunk_memory_fn, chunk_all_unprocessed
# TMT (兼容现有 v2.1 路由)
import tmt.router as tmt_module
from tmt.router import router as tmt_router

app = FastAPI(title="Mnemosyne OS v6.4.0 — 认知型记忆操作系统")

# ── 挂载 v5.0 路由 ──
app.include_router(tmt_router)

# 三馆闭环 (Phase 2)
import api.halls as halls_module
from api.halls import router as halls_router
app.include_router(halls_router)
halls_module.pool = None  # startup 时注入

# 工具归档 (Phase 2)
import api.tools as tools_module
from api.tools import router as tools_router
app.include_router(tools_router)
tools_module.pool = None

# 项目管理 (Phase 2)
import api.projects as projects_module
from api.projects import router as projects_router
app.include_router(projects_router)
projects_module.pool = None

# 安全模块 (Phase 3)
import security.audit as audit_module
import security.purifier as purifier_module

import api.security as security_module
from api.security import router as security_router
app.include_router(security_router)
security_module.pool = None

# 数据库连接池

# ── AGE 图同步 ──
async def sync_entities_to_age(conn, memory_id: int, entities: list, user_id: str):
    for name in entities:
        name = name.strip()
        if not name:
            continue
        # 安全: 转义单引号 + 截断
        safe_name = name.replace("'", "\\'")[:200]
        safe_user = user_id.replace("'", "\\'")
        
        row = await conn.fetchrow("SELECT id FROM entities WHERE user_id=$1 AND name=$2", user_id, name)
        if row:
            eid = row["id"]
        else:
            raw = (await get_embedding([name]))[0]
            e_str = "[" + ",".join(str(x) for x in raw) + "]"
            row = await conn.fetchrow(
                "INSERT INTO entities (user_id, name, type, description, embedding) VALUES ($1,$2,$3,$4,$5::vector) RETURNING id",
                user_id, name, "auto", "", e_str
            )
        eid = row["id"]

        await conn.execute("SELECT * FROM cypher('mnemosyne_graph', $$ CREATE (:Entity {entity_id: '%s', name: '%s', user_id: '%s'}) $$) AS (v agtype)" % (eid, safe_name, safe_user))
        
        await conn.execute("INSERT INTO memory_entities (memory_id, entity_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", memory_id, eid)
        try:
            await conn.execute("SELECT * FROM cypher('mnemosyne_graph', $$ MERGE (m:Memory {memory_id: '%s'}) WITH m MATCH (e:Entity {entity_id: '%s'}) MERGE (m)-[:MENTIONS]->(e) $$) AS (v agtype)" % (memory_id, eid))
        except Exception as e:
            logger.debug(f"AGE MENTIONS edge creation skipped: {e}")
async def clean_age_relations(conn, memory_id: int):
    try:
        await conn.execute("SELECT * FROM cypher('mnemosyne_graph', $$ MATCH (m:Memory {memory_id: '" + str(memory_id) + "'})-[r]-() DELETE r $$) AS (v agtype)")
    except Exception as e:
        pass
    await conn.execute("DELETE FROM memory_entities WHERE memory_id=$1", memory_id)

# ── 矛盾检测 ──
import difflib

def text_diff_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

async def detect_conflict(conn, user_id: str, new_content: str, new_embedding_str: str) -> dict:
    """检测新记忆是否与已有记忆冲突或重复"""
    rows = await conn.fetch(
        f"SELECT id, content, embedding <=> $1::vector AS dist, heat_score "
        "FROM memories WHERE user_id=$2 AND is_deleted=FALSE AND valid_to IS NULL "
        "ORDER BY embedding <=> $1::vector LIMIT 5",
        new_embedding_str, user_id
    )
    for r in rows:
        if r["dist"] > 0.15:  # 语义不相似,跳过
            continue
        ratio = text_diff_ratio(new_content, r["content"])
        if ratio > 0.85:
            # 几乎完全重复 → 合并
            return {"action": "merge", "id": r["id"]}
        elif ratio < 0.5 and r["dist"] < 0.12:
            # 语义相似但内容冲突 → 旧记忆标记为过期
            return {"action": "conflict", "id": r["id"], "old_content": r["content"]}
    return {"action": "fresh"}

# ── 启动/关闭 ──


class DialecticRequest(BaseModel):
    query: str = ""
    user_id: str = "default"
    max_memories: int = 3


@app.post("/api/v1/dialectic")
async def dialectic_search(req: DialecticRequest):
    query = req.query.strip()
    if not query:
        return {"error": "query required"}
    user_id = req.user_id
    async with pool.acquire() as conn:
        r_q = (await get_embedding([query]))[0]
        q_str = "[" + ",".join(str(x) for x in r_q) + "]"
        keywords = [w.strip() for w in query.replace("?", "").replace("!", "").split() if len(w.strip()) > 1]
        bm25_sql = "0"
        for kw in keywords:
            kw_safe = kw.replace("'", "''")
            bm25_sql = "CASE WHEN m.content ILIKE '%" + kw_safe + "%' THEN 0.15 ELSE " + bm25_sql + " END"
        temporal_sql = "CASE WHEN m.created_at > NOW() - INTERVAL '7 days' THEN 0.15 WHEN m.created_at > NOW() - INTERVAL '30 days' THEN 0.08 ELSE 0 END"
        rows = await conn.fetch(
            "SELECT m.id, m.content, m.category, m.tier, m.heat_score, m.reliability, m.created_at, m.session_id "
            "FROM memories m WHERE m.user_id=$1 AND m.is_deleted=FALSE AND (m.valid_to IS NULL OR m.valid_to > NOW()) AND m.embedding IS NOT NULL "
            "ORDER BY (0.40 * (1.0 - (m.embedding <=> $2::vector)) "
            "  + 0.15 * (" + bm25_sql + ") "
            "  + 0.15 * (" + temporal_sql + ") "
            "  + 0.15 * m.reliability "
            "  + 0.15 * GREATEST(0.0, m.heat_score)) DESC "
            "LIMIT $3", user_id, q_str, req.max_memories * 2
        )
        if not rows:
            return {"query": query, "memories": [], "context": [], "total_memories": 0}
        memories = []
        session_ids = set()
        for r in rows:
            mem = {"id": r["id"], "content": r["content"][:300], "category": r["category"],
                   "tier": r["tier"], "heat": r["heat_score"], "reliability": r["reliability"],
                   "created": str(r["created_at"])[:19]}
            memories.append(mem)
            if r["session_id"]:
                session_ids.add(str(r["session_id"]))
        context = []
        if session_ids:
            session_list = list(session_ids)
            phs = ",".join("${}".format(2 + i) for i in range(len(session_list)))
            s_rows = await conn.fetch(
                "SELECT s.id::text, s.session_label, s.summary, s.heat_score, s.fragment_ids, s.start_time, s.created_at "
                "FROM ag_catalog.tmt_sessions s WHERE s.user_id=$1 AND s.id::text = ANY(ARRAY[" + phs + "])",
                user_id, *session_list
            )
            for s in s_rows:
                context.append({
                    "type": "L2_session", "id": s["id"], "label": s["session_label"] or "",
                    "summary": (s["summary"] or "")[:500], "heat": s["heat_score"],
                    "fragment_count": len(s["fragment_ids"] or []),
                    "start_time": str(s["start_time"])[:19] if s["start_time"] else "",
                    "created": str(s["created_at"])[:19],
                })
        return {"query": query, "memories": memories, "context": context, "total_memories": len(memories)}


@app.get("/api/v1/memories/{memory_id}/tiered")
async def tiered_read(memory_id: int, level: str = "L3", user_id: str = "default"):
    """三级读取：L5摘要 / L3概览 / L1全文+上下文"""
    level = level.upper().strip()
    if level not in ("L5", "L3", "L1"):
        return {"error": "level must be L5, L3, or L1"}
    
    async with pool.acquire() as conn:
        # 1. Fetch the memory
        row = await conn.fetchrow(
            "SELECT m.id, m.content, m.category, m.tier, m.tmt_level, m.heat_score, "
            "m.reliability, m.access_count, m.created_at, m.session_id "
            "FROM memories m WHERE m.id=$1 AND m.user_id=$2 AND m.is_deleted=FALSE",
            memory_id, user_id
        )
        if not row:
            return {"error": f"memory {memory_id} not found"}
        
        base = {
            "id": row["id"],
            "category": row["category"],
            "tier": row["tier"],
            "heat": row["heat_score"],
            "reliability": row["reliability"],
            "created": str(row["created_at"])[:19],
        }
        
        if level == "L5":
            # 摘要：截取 200 字 + session 标签
            base["summary"] = (row["content"] or "")[:200]
            base["content_truncated"] = True
            if row["session_id"]:
                s = await conn.fetchrow(
                    "SELECT session_label FROM ag_catalog.tmt_sessions WHERE id=$1",
                    row["session_id"]
                )
                if s and s["session_label"]:
                    base["session_label"] = s["session_label"]
            return base
        
        elif level == "L3":
            # 概览：800字 + session 摘要
            content_full = row["content"] or ""
            base["content"] = content_full[:800]
            base["content_length"] = len(content_full)
            base["content_truncated"] = len(content_full) > 800
            if row["session_id"]:
                s = await conn.fetchrow(
                    "SELECT session_label, summary FROM ag_catalog.tmt_sessions "
                    "WHERE id=$1", row["session_id"]
                )
                if s:
                    base["session"] = {
                        "label": s["session_label"] or "",
                        "summary": (s["summary"] or "")[:500],
                    }
            return base
        
        else:  # L1
            # 全文 + session 全信息 + 片段列表
            base["content"] = row["content"] or ""
            base["content_length"] = len(row["content"] or "")
            base["access_count"] = row["access_count"]
            
            if row["session_id"]:
                sid = row["session_id"]
                s = await conn.fetchrow(
                    "SELECT session_label, summary, heat_score, fragment_ids, "
                    "start_time, end_time, token_count "
                    "FROM ag_catalog.tmt_sessions WHERE id=$1", sid
                )
                if s:
                    base["session"] = {
                        "id": str(sid),
                        "label": s["session_label"] or "",
                        "summary": s["summary"] or "",
                        "heat": s["heat_score"],
                        "fragment_count": len(s["fragment_ids"] or []),
                        "token_count": s["token_count"],
                        "start": str(s["start_time"])[:19] if s["start_time"] else "",
                        "end": str(s["end_time"])[:19] if s["end_time"] else "",
                    }
                    # 同 session 的其它片段
                    fids = s["fragment_ids"] or []
                    if fids:
                        others = await conn.fetch(
                            "SELECT id, content, category, heat_score, created_at "
                            "FROM memories WHERE id = ANY($1::bigint[]) AND id != $2 "
                            "ORDER BY created_at LIMIT 10",
                            fids, memory_id
                        )
                        if others:
                            base["related_fragments"] = []
                            for o in others:
                                base["related_fragments"].append({
                                    "id": o["id"],
                                    "content": (o["content"] or "")[:150],
                                    "category": o["category"],
                                    "heat": o["heat_score"],
                                })
            
            # 每日摘要（如果属于某天）
            try:
                d = await conn.fetchrow(
                    "SELECT d.date, d.summary FROM ag_catalog.tmt_daily d "
                    "WHERE d.user_id=$1 AND $2::date >= d.date "
                    "ORDER BY d.date DESC LIMIT 1",
                    user_id, str(row["created_at"])[:10]
                )
                if d:
                    base["daily"] = {
                        "date": str(d["date"]),
                        "summary": (d["summary"] or "")[:300],
                    }
            except Exception:
                pass
            
            return base


@app.get("/api/v1/memories/conflicts")
async def list_conflicts(user_id: str = "default", limit: int = 20):
    """Query memories with conflict metadata"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, category, tier, heat_score, reliability, metadata, created_at "
            "FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) "
            "AND metadata->>'conflicts_with' IS NOT NULL "
            "ORDER BY created_at DESC LIMIT $2", user_id, limit
        )
        if not rows:
            return {"conflicts": [], "total": 0}
        result = []
        for r in rows:
            meta = r["metadata"] or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            result.append({
                "id": r["id"],
                "content": r["content"][:200],
                "category": r["category"],
                "tier": r["tier"],
                "heat": r["heat_score"],
                "reliability": r["reliability"],
                "conflicts_with": meta.get("conflicts_with"),
                "conflict_type": meta.get("conflict_type", "unknown"),
                "created": str(r["created_at"])[:19],
            })
        return {"conflicts": result, "total": len(result)}



@app.get("/api/v1/wiki")
async def list_wiki_pages(user_id: str = "default", limit: int = 20):
    """List wiki knowledge pages"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, title, content, created_at, updated_at "
            "FROM wiki_pages WHERE user_id=$1 ORDER BY updated_at DESC LIMIT $2",
            user_id, limit
        )
        return [{"id": r["id"], "title": r["title"],
                  "content_preview": (r["content"] or "")[:200],
                  "content_length": len(r["content"] or ""),
                  "created": str(r["created_at"])[:19] if r["created_at"] else "",
                  "updated": str(r["updated_at"])[:19] if r["updated_at"] else "",
                 } for r in rows]

@app.get("/api/v1/wiki/{page_id}")
async def get_wiki_page(page_id: int):
    """Get wiki page full content"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, title, content, user_id, created_at, updated_at "
            "FROM wiki_pages WHERE id=$1", page_id
        )
        if not row:
            return {"error": "not found"}
        return {"id": row["id"], "title": row["title"], "content": row["content"] or "",
                "user_id": row["user_id"], "created": str(row["created_at"])[:19] if row["created_at"] else "",
                "updated": str(row["updated_at"])[:19] if row["updated_at"] else ""}

@app.post("/api/v1/wiki")
async def create_wiki_page(title: str, content: str = "", user_id: str = "default"):
    """Create a wiki page"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO wiki_pages (title, content, user_id) VALUES ($1, $2, $3) RETURNING id",
            title, content, user_id
        )
        return {"status": "created", "id": row["id"]}



@app.get("/api/v1/media")
async def list_media(user_id: str = "default", limit: int = 20, media_type: str = ""):
    """列出媒体记忆（文件/图片/链接等）"""
    async with pool.acquire() as conn:
        if media_type:
            rows = await conn.fetch(
                "SELECT id, content, media_type, media_url, importance, reliability, metadata, created_at "
                "FROM media_memories WHERE user_id=$1 AND media_type=$2 "
                "ORDER BY created_at DESC LIMIT $3", user_id, media_type, limit
            )
        else:
            rows = await conn.fetch(
                "SELECT id, content, media_type, media_url, importance, reliability, metadata, created_at "
                "FROM media_memories WHERE user_id=$1 "
                "ORDER BY created_at DESC LIMIT $2", user_id, limit
            )
        return [{"id": r["id"], "content": (r["content"] or "")[:200],
                 "media_type": r["media_type"], "media_url": r["media_url"],
                 "importance": r["importance"], "reliability": r["reliability"],
                 "created": str(r["created_at"])[:19]} for r in rows]

@app.get("/api/v1/media/{media_id}")
async def get_media(media_id: int):
    """获取媒体记忆全文"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, content, media_type, media_url, media_hash, importance, "
            "reliability, metadata, created_at FROM media_memories WHERE id=$1", media_id
        )
        if not row:
            return {"error": "not found"}
        return {"id": row["id"], "content": row["content"] or "",
                "media_type": row["media_type"], "media_url": row["media_url"],
                "media_hash": row["media_hash"], "importance": row["importance"],
                "reliability": row["reliability"],
                "metadata": row["metadata"] or {},
                "created": str(row["created_at"])[:19]}

@app.post("/api/v1/media")
async def create_media(content: str, media_type: str = "file", media_url: str = "",
                       media_hash: str = "", user_id: str = "default", importance: float = 0.5):
    """创建媒体记忆（关联文件/图片/链接到记忆系统）"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO media_memories (user_id, content, media_type, media_url, media_hash, importance) "
            "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, content, media_type, media_url, media_hash, importance
        )
        return {"status": "created", "id": row["id"]}

@app.delete("/api/v1/media/{media_id}")
async def delete_media(media_id: int, user_id: str = "default"):
    """删除媒体记忆"""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM media_memories WHERE id=$1 AND user_id=$2", media_id, user_id
        )
        deleted = result.split()[-1] if result else "0"
        return {"status": "deleted", "id": media_id, "affected": int(deleted)}

async def init_age_connection(conn):
    """每个新连接加载 AGE 扩展; 环境无 AGE 时优雅降级 (生产必装, 本地开发可缺)"""
    try:
        await conn.execute("LOAD 'age'")
    except Exception:
        pass

@app.on_event("startup")
async def startup():
    global pool
    pool = await asyncpg.create_pool(
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_DB,
        host=PG_HOST,
        port=PG_PORT,
        min_size=2,
        max_size=10,
        server_settings={'search_path': 'ag_catalog, public'},
        init=init_age_connection
    )
    # 注入 TMT 模块
    tmt_module.pool = pool
    # 注入 v5.0 模块
    halls_module.pool = pool
    tools_module.pool = pool
    projects_module.pool = pool
    security_module.pool = pool
    tmt_module.embed_fn = get_embedding
    tmt_module.llm_url = "http://127.0.0.1:11435/v1/chat/completions"
    # v7.0 魔法记忆宫殿: 初始化 (建表+存量归档, 幂等)
    try:
        import palace
        palace_result = await palace.init_palace(pool)
        logger.info(f"[palace] 初始化完成: tables={palace_result['tables']} classified={palace_result['classified']} cards={palace_result['cards']}")
    except Exception as e:
        logger.warning(f"[palace] 初始化跳过: {e}")

@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()

# ── v5.0: 豆包 API Embedding (替代本地 Qwen3-Embedding) ──
async def get_embedding(texts: List[str]) -> List[List[float]]:
    """调用豆包 Embedding-Vision API — 1024维多模态向量"""
    return await get_embedding_async(texts)

async def rerank_docs(query: str, documents: List[str], top_k: int = 5) -> List[str]:
    """
    v5.1 Reranker: 豆包 doubao-embedding-vision-251215 主用 (余弦相似度排序)
    本地 Qwen3-Embed (GZ :11436) 作为 fallback
    """
    RERANK_URL = "http://127.0.0.1:11436/v1/embeddings"
    
    async def _embed_local(texts):
        """Fallback: 本地 Qwen3-Embedding"""
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(RERANK_URL, json={"input": texts})
            resp.raise_for_status()
            data = resp.json()
            return [d["embedding"] for d in data["data"]]
    
    try:
        # 主路径: 豆包 embedding
        from core.backends import rerank_by_similarity
        q_emb = (await get_embedding([query]))[0]
        d_embs = await get_embedding(documents)
        return rerank_by_similarity(q_emb, documents, d_embs, top_k)
    except Exception:
        # Fallback: 本地 Qwen3-Embedding
        try:
            q_emb = (await _embed_local([query]))[0]
            d_embs = await _embed_local(documents)
            from core.backends import rerank_by_similarity
            return rerank_by_similarity(q_emb, documents, d_embs, top_k)
        except Exception:
            return documents[:top_k]

# ── 信念模型 ──
class BeliefCreate(BaseModel):
    user_id: str
    content: str
    confidence: float = 0.5
    evidence_memories: List[int] = []
    status: str = "tentative"

class BeliefSearch(BaseModel):
    user_id: str
    query: str
    top_k: int = 5
    status_filter: Optional[str] = None

# ── 基础记忆 API ──
class MemoryCreate(BaseModel):
    user_id: str = "default"
    project_id: Optional[str] = None
    content: str
    category: str = "knowledge"
    metadata: dict = {}
    entities: Optional[List[str]] = None
    session_id: Optional[str] = None

SIGNAL_WEIGHTS = [
    (("待办", "下一步", "TODO", "pending", "未完成", "接着", "继续做"), 0.15, "未完成任务"),
    (("不是", "错了", "不要", "应该改", "修正", "记住"), 0.10, "用户纠正"),
    (("坑", "教训", "报错", "失败", "注意", "踩过", "小心"), 0.10, "踩坑教训"),
    (("决定", "方案", "采用", "架构", "设计", "选择"), 0.08, "决策方案"),
    (("路径", "端口", "API", "配置", "key", "密钥"), 0.05, "路径/API"),
    (("重要", "关键", "核心", "必须"), 0.05, "重要标记"),
]
# 天生重要的类别
IMPORTANT_CATS = {"preference", "knowledge", "pitfall"}


def compute_write_heat(content: str, category: str) -> float:
    """v6.3 认知写入信号: 初始热度按内容重要性加分 (抽屉级联温度设计, 纯正则不调LLM)"""
    heat = 0.5
    for keywords, weight, _name in SIGNAL_WEIGHTS:
        if any(k in content for k in keywords):
            heat += weight
    if category in IMPORTANT_CATS:
        heat += 0.10
    return round(min(max(heat, 0.3), 0.8), 2)


@app.post("/api/v1/memories")
async def create_memory(mem: MemoryCreate):
    raw_vec = (await get_embedding([mem.content]))[0]
    vec_str = "[" + ",".join(str(x) for x in raw_vec) + "]"
    # v6.0: 分类归一化 + user_id 收敛单用户
    cat = normalize_category(mem.category)
    uid = "default" if mem.user_id in ("g-cat", "noah", "mnemosyne-agent", "website-agent", "system", "test", "audit") else (mem.user_id or "default")
    # v6.3: 认知写入信号 — 初始热度按内容重要性加分 (抽屉级联温度设计, 纯正则不调LLM)
    heat_init = compute_write_heat(mem.content, cat)
    async with pool.acquire() as conn:
        # 矛盾检测
        conflict = await detect_conflict(conn, uid, mem.content, vec_str)
        if conflict["action"] == "merge":
            # 合并：增加访问计数，不创建新记录
            await conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = NOW() WHERE id = $1",
                conflict["id"]
            )
            return {"status": "merged", "id": conflict["id"], "action": "merged_with_existing"}
        elif conflict["action"] == "conflict":
            # 冲突：旧记忆标记为过期，新记忆标记冲突来源
            old_id = conflict["id"]
            await conn.execute(
                "UPDATE memories SET valid_to = NOW(), invalid_at = NOW() WHERE id = $1",
                old_id
            )
            await conn.execute(
                "INSERT INTO memory_traces (memory_id, action, details) VALUES ($1, 'superseded', $2)",
                old_id, json.dumps({"new_content": mem.content[:200]})
            )
            # 新记忆标记冲突来源
            meta = dict(mem.metadata) if isinstance(mem.metadata, dict) else {}
            meta["conflicts_with"] = old_id
            meta["conflict_type"] = "superseded"
        # 正常存入（含valid_from）；v6.0: 原始碎片 tmt_level=1，tier 由 reflect 维护
        # v6.3: 写入 heat_score = 认知写入信号 (初始热度)
        # v7.2: 初始 S 由写入信号映射 (heat_init≥0.7→7 / ≥0.6→5 / 其他→3), R=S; 4维标记进 metadata
        s_init = 7 if heat_init >= 0.7 else (5 if heat_init >= 0.6 else 3)
        meta_extra = dict(locals().get("meta", mem.metadata)) if isinstance(locals().get("meta", mem.metadata), dict) else {}
        meta_extra.setdefault("novelty", 1)        # 新内容
        meta_extra.setdefault("valence", 0)        # 中性
        meta_extra.setdefault("relevance", 0)      # 待任务绑定
        meta_extra.setdefault("repetition", 0)     # 访问次数 (与 access_count 联动)
        row = await conn.fetchrow(
            'INSERT INTO memories (user_id, project_id, content, category, embedding, metadata, valid_from, session_id, tmt_level, heat_score, storage_strength, retrieval_strength) '
            'VALUES ($1,$2,$3,$4,$5::vector,$6,NOW(),$7,1,$8,$9,$10) RETURNING id',
            uid, mem.project_id, mem.content, cat, vec_str,
            json.dumps(meta_extra), mem.session_id, heat_init, s_init, s_init
        )
        mid = row["id"]
        if mem.entities:
            await sync_entities_to_age(conn, mid, mem.entities, uid)
    return {"status": "stored", "id": row["id"], "category": cat}

class MemorySearch(BaseModel):
    user_id: str
    project_id: Optional[str] = None
    query: str
    top_k: int = 5
    category_filter: Optional[str] = None
    tier_filter: Optional[str] = None
    sort: str = "hybrid"  # hybrid (default), created_at — time-ordered search

@app.post("/api/v1/memories/search")
async def search_memories(req: MemorySearch):
    """Full search: hybrid (default) or time-ordered.
    
    sort=hybrid: BM25 + embedding + rerank + trust_score
    sort=created_at: keyword ILIKE + created_at DESC (pure time order)
    """
    
    async def heat_hits(conn, ids, delta: float = 0.05) -> None:
        """v6.2 认知热度: 搜索命中 → access_count+1 + heat 加权 (noah 双权重频次分量)"""
        ids = [int(i) for i in ids]
        if not ids:
            return
        await conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = NOW(), "
            "heat_score = LEAST(1.0, heat_score + $2), "
            "retrieval_strength = GREATEST(retrieval_strength, storage_strength), "
            "metadata = COALESCE(metadata,'{}'::jsonb) || "
            "jsonb_build_object('repetition', COALESCE((metadata->>'repetition')::int, 0) + 1, 'last_access_ts', EXTRACT(EPOCH FROM NOW())::int) "
            "WHERE user_id = $1 AND id = ANY($3::bigint[]) AND is_deleted = FALSE",
            req.user_id, delta, ids,
        )
    
    # Time-ordered mode: skip embedding, just keyword + time sort
    if req.sort == "created_at":
        async with pool.acquire() as conn:
            query_sql = ("SELECT id, content, category, tier, heat_score, reliability, access_count, created_at "
                        "FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) ")
            params = [req.user_id]
            idx = 2
            if req.query.strip():
                keywords = [w.strip() for w in req.query.replace("?", "").replace("!", "")
                           .replace("\uff0c", " ").replace("\u3002", " ").split() if len(w.strip()) > 1]
                if keywords:
                    ilike_clauses = []
                    for kw in keywords:
                        ilike_clauses.append(f"content ILIKE ${idx}")
                        params.append(f"%{kw}%")
                        idx += 1
                    query_sql += "AND (" + " OR ".join(ilike_clauses) + ") "
            if req.category_filter:
                query_sql += f"AND category = ${idx} "
                params.append(req.category_filter)
                idx += 1
            if req.tier_filter:
                query_sql += f"AND tier = ${idx} "
                params.append(req.tier_filter)
                idx += 1
            query_sql += f"ORDER BY created_at DESC LIMIT ${idx}"
            params.append(req.top_k)
            rows = await conn.fetch(query_sql, *params)
            if rows:  # v6.2: 命中加热
                await heat_hits(conn, [r["id"] for r in rows[:5]])
        if not rows:
            return {"memories": [], "sort": "created_at"}
        return {"memories": [{
            "id": str(r["id"]), "content": r["content"][:300],
            "category": r["category"], "tier": r["tier"],
            "heat_score": r["heat_score"], "reliability": r["reliability"],
            "access_count": r["access_count"],
            "created_at": str(r["created_at"])[:19] if r["created_at"] else None,
        } for r in rows], "sort": "created_at"}
    
    # Default: hybrid search (embedding + BM25 + rerank)
    r_q = (await get_embedding([req.query]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    
    # Inline BM25 (no param binding, compatible with vector $idx)
    keywords = [w.strip() for w in req.query.replace("?", "").replace("!", "")
                .replace("\uff0c", " ").replace("\u3002", " ").split() if len(w.strip()) > 1]
    bm25_sql = "0"
    for kw in keywords:
        bm25_sql = "CASE WHEN m.content ILIKE '%" + kw.replace("'", "''") + "%' THEN 0.15 ELSE " + bm25_sql + " END"
    temporal_sql = "CASE WHEN m.created_at > NOW() - INTERVAL '7 days' THEN 0.15 WHEN m.created_at > NOW() - INTERVAL '30 days' THEN 0.08 ELSE 0 END"
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT m.id, m.content, m.category, m.tier, m.heat_score, m.reliability, m.access_count, m.created_at "
            "FROM memories m WHERE m.user_id=$1 AND m.is_deleted=FALSE AND (m.valid_to IS NULL OR m.valid_to > NOW()) AND m.embedding IS NOT NULL "
            "ORDER BY (0.40 * (1.0 - (m.embedding <=> $2::vector)) "
            "  + 0.15 * (" + bm25_sql + ") "
            "  + 0.15 * (" + temporal_sql + ") "
            "  + 0.15 * m.reliability "
            "  + 0.15 * GREATEST(0.0, m.heat_score)) DESC "
            "LIMIT $3",
            req.user_id, q_str, req.top_k
        )
        if rows:  # v6.2: 命中加热
            await heat_hits(conn, [r["id"] for r in rows[:5]])
    
    if not rows:
        return {"memories": []}
    
    # Rerank with fallback
    try:
        docs = [r["content"] for r in rows]
        ids = [r["id"] for r in rows]
        ranked = await rerank_docs(req.query, docs, req.top_k)
        ranked_memories = []
        for rc in ranked:
            for r in rows:
                if r["content"] == rc:
                    ranked_memories.append({
                        "id": str(r["id"]), "content": r["content"],
                        "category": r["category"], "tier": r["tier"],
                        "heat_score": r["heat_score"], "reliability": r["reliability"],
                        "access_count": r["access_count"],
                        "created_at": str(r["created_at"]) if r["created_at"] else None,
                    })
                    break
        return {"memories": ranked_memories}
    except Exception:
        pass  # fallback to original order
    
    return {"memories": [
        {"id": str(r["id"]), "content": r["content"],
         "category": r["category"], "tier": r["tier"],
         "heat_score": r["heat_score"], "reliability": r["reliability"],
         "access_count": r["access_count"],
         "created_at": str(r["created_at"]) if r["created_at"] else None}
        for r in rows]
    }

@app.get("/api/v1/memories")
async def list_memories(user_id: str, limit: int = 20, tier: Optional[str] = None, 
                        category: Optional[str] = None, sort: str = "created_at",
                        search: Optional[str] = None):
    """List memories with optional search and sort.
    
    sort: created_at (default), heat, updated_at
    search: optional keyword filter (ILIKE match)
    """
    query = "SELECT id, content, category, tier, heat_score, access_count, created_at, updated_at, valid_to FROM memories WHERE user_id = $1 AND is_deleted = FALSE AND (valid_to IS NULL OR valid_to > NOW())"
    params = [user_id]
    idx = 2
    if tier:
        query += f" AND tier = ${idx}"
        params.append(tier)
        idx += 1
    if category:
        query += f" AND category = ${idx}"
        params.append(category)
        idx += 1
    if search:
        query += f" AND content ILIKE ${idx}"
        params.append(f"%{search}%")
        idx += 1
    
    # Sort: time (default) or heat
    if sort == "heat":
        query += f" ORDER BY heat_score DESC, created_at DESC LIMIT ${idx}"
    elif sort == "updated_at":
        query += f" ORDER BY updated_at DESC NULLS LAST LIMIT ${idx}"
    else:
        query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return {"memories": [{
        "id": r["id"], "content": r["content"][:300],
        "category": r["category"], "tier": r["tier"],
        "heat_score": r["heat_score"], "access_count": r["access_count"],
        "created_at": str(r["created_at"])[:19] if r["created_at"] else None,
        "updated_at": str(r["updated_at"])[:19] if r["updated_at"] else None,
        "expired": r["valid_to"] is not None and r["valid_to"] < __import__("datetime").datetime.now(),
    } for r in rows], "total": len(rows), "sort": sort}

@app.post("/api/v1/memories/evolve")
async def evolve_memories(user_id: str, strategy: str = "consolidate", limit: int = 50):
    async with pool.acquire() as conn:
        if strategy == "cleanup":
            # Remove very old L3 memories with low heat
            r = await conn.execute("UPDATE memories SET is_deleted=TRUE, forgotten_at=NOW() WHERE user_id=$1 AND tier='L3' AND heat_score<0.05 AND last_accessed<NOW()-INTERVAL '60 days'", user_id)
            return {"strategy": "cleanup", "affected": int(r.split()[-1])}
        elif strategy == "boost":
            # Boost frequently accessed low-tier memories
            r = await conn.execute("UPDATE memories SET heat_score=LEAST(1.0, heat_score+0.15) WHERE user_id=$1 AND access_count>5 AND heat_score<0.3 AND is_deleted=FALSE", user_id)
            return {"strategy": "boost", "affected": int(r.split()[-1])}
        elif strategy == "consolidate":
            # Merge duplicate-ish memories (same content, keep the newest)
            dups = await conn.fetch("SELECT id, content, created_at, ROW_NUMBER() OVER (PARTITION BY content ORDER BY created_at DESC) as rn FROM memories WHERE user_id=$1 AND is_deleted=FALSE ORDER BY content", user_id)
            merged = 0
            seen = {}
            for row in dups:
                if row["content"] not in seen:
                    seen[row["content"]] = row["id"]
                else:
                    keep_id = seen[row["content"]]
                    # Transfer entities
                    await conn.execute("UPDATE memory_entities SET memory_id=$1 WHERE memory_id=$2 AND entity_id NOT IN (SELECT entity_id FROM memory_entities WHERE memory_id=$1)", keep_id, row["id"])
                    await conn.execute("UPDATE memories SET is_deleted=TRUE WHERE id=$1", row["id"])
                    merged += 1
            return {"strategy": "consolidate", "merged": merged}
    return {"strategy": strategy, "status": "done"}
@app.get("/api/v1/memories/heat-top")
async def heat_top_memories(user_id: str, limit: int = 10, min_heat: float = 0.0):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, content, category, tier, heat_score, access_count, created_at FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) AND heat_score>=$2 ORDER BY heat_score DESC LIMIT $3", user_id, min_heat, limit)
    return {"memories": [dict(r) for r in rows]}

@app.get("/api/v1/memories/stats")
async def get_memory_stats(user_id: str = "default"):
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW())", user_id)
        by_cat = await conn.fetch(
            "SELECT category, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) GROUP BY category ORDER BY cnt DESC",
            user_id
        )
        by_tier = await conn.fetch(
            "SELECT tier, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) GROUP BY tier ORDER BY tier",
            user_id
        )
        avg_h = await conn.fetchval("SELECT COALESCE(AVG(heat_score), 0) FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW())", user_id)
        deleted = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE user_id=$1 AND is_deleted=TRUE", user_id)
        total_all = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE user_id=$1", user_id)
    return {
        "total": total, "total_including_deleted": total_all, "deleted": deleted,
        "avg_heat_score": float(avg_h),
        "by_category": {r["category"]: r["cnt"] for r in by_cat},
        "by_tier": {r["tier"]: r["cnt"] for r in by_tier},
    }

@app.get("/api/v1/memories/tree")
async def get_memory_tree(user_id: str = "default", limit: int = 5):
    async with pool.acquire() as conn:
        tiers = await conn.fetch(
            "SELECT tier, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) GROUP BY tier ORDER BY tier",
            user_id
        )
        l1s = await conn.fetch(
            "SELECT id, content, category, heat_score FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) AND tier='L1' ORDER BY heat_score DESC LIMIT $2",
            user_id, limit
        )
    return {
        "tree": {r["tier"]: r["cnt"] for r in tiers},
        "l1_previews": [{"id": r["id"], "content": r["content"][:100], "category": r["category"], "heat": r["heat_score"]} for r in l1s],
    }

@app.delete("/api/v1/memories/{memory_id}")
async def delete_memory(memory_id: int, user_id: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE memories SET is_deleted = TRUE, forgotten_at = NOW() WHERE id = $1 AND user_id = $2",
            memory_id, user_id
        )
        await clean_age_relations(conn, memory_id)
    return {"status": "soft-deleted"}

# ── 更新 API (v7.1 抽屉化: 补齐记忆修改权 — 内容纠错/替换, 不删重存) ──
class MemoryUpdate(BaseModel):
    content: str | None = None
    category: str | None = None
    importance: float | None = None
    heat_score: float | None = None
    metadata: dict | None = None
    pin: bool | None = None          # True=钉为永久卷, False=取消钉

@app.put("/api/v1/memories/{memory_id}")
async def update_memory(memory_id: int, user_id: str, update: MemoryUpdate):
    """更新记忆内容/属性。不重建 embedding 时保留原向量; content 变了会重算向量+重分类+刷新档号。"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, content, category, embedding, metadata, archive_no FROM memories WHERE id = $1 AND user_id = $2 AND is_deleted = FALSE",
            memory_id, user_id
        )
        if not row:
            return {"status": "not_found", "memory_id": memory_id}

        sets = []
        params = [memory_id, user_id]
        idx = 3
        new_content = None

        if update.content is not None:
            if len(update.content.strip()) < 1:
                return {"status": "error", "message": "content cannot be empty"}
            new_content = update.content.strip()
            sets.append(f"content = ${idx}")
            params.append(new_content)
            idx += 1
        if update.category is not None:
            sets.append(f"category = ${idx}")
            params.append(update.category)
            idx += 1
        if update.importance is not None:
            sets.append(f"importance = ${idx}")
            params.append(max(0.0, min(1.0, update.importance)))
            idx += 1
        if update.heat_score is not None:
            sets.append(f"heat_score = ${idx}")
            params.append(max(0.0, min(1.0, update.heat_score)))
            idx += 1
        if update.pin is not None:
            # pin 状态存 metadata (与 palace/pin 一致)
            pin_flag = "true" if update.pin else "false"
            sets.append(f"metadata = COALESCE(metadata,'{{}}'::jsonb) || ('{{\"pinned\":\"{pin_flag}\"}}')::jsonb")
            if update.pin:
                sets.append("heat_score = GREATEST(heat_score, 0.5)")  # 钉卷至少回常温

        if update.metadata is not None:
            sets.append(f"metadata = COALESCE(metadata,'{{}}'::jsonb) || ${idx}::jsonb")
            params.append(json.dumps(update.metadata))
            idx += 1

        if not sets:
            return {"status": "no_changes"}

        sets.append("updated_at = NOW()")
        await conn.execute(
            f"UPDATE memories SET {', '.join(sets)} WHERE id = $1 AND user_id = $2",
            *params
        )

        # content 变更 → 重算向量 + 重分类 + 归档档号
        if new_content is not None:
            try:
                emb = await get_embedding([new_content])
                await conn.execute(
                    "UPDATE memories SET embedding = $1::vector WHERE id = $2",
                    emb[0], memory_id
                )
            except Exception:
                pass  # 向量失败不阻塞内容更新
            # 重新分类 (复用 palace 分类嗅探, 若无则跳过)
            try:
                from palace import classify
                cls = classify(new_content)
                if cls and cls.get("room") and cls.get("room") != "unfiled":
                    new_cat = cls["room"]
                    await conn.execute("UPDATE memories SET category = $1 WHERE id = $2", new_cat, memory_id)
            except Exception:
                pass
            # 记录 trace
            try:
                await conn.execute(
                    "INSERT INTO memory_traces (memory_id, action, details) VALUES ($1, 'update', $2)",
                    memory_id, json.dumps({"old_len": len(row["content"]), "new_len": len(new_content)})
                )
            except Exception:
                pass

    return {"status": "updated", "memory_id": memory_id}

@app.patch("/api/v1/memories/{memory_id}")
async def patch_memory(memory_id: int, user_id: str, update: MemoryUpdate):
    """PATCH 别名: 与 PUT 相同语义 (部分更新)。"""
    return await update_memory(memory_id, user_id, update)

# ── 抽屉 API (v7.1 抽屉化: 分布/遗忘候选/手动遗忘) ──
# v7.1 空间感知: 水位检查 (预警/授权 用)
async def _storage_usage() -> dict:
    """计算记忆系统存储水位: 基于 memories 内容总字节 vs 磁盘/库容量。"""
    try:
        async with pool.acquire() as conn:
            content_bytes = await conn.fetchval(
                "SELECT COALESCE(SUM(LENGTH(content)), 0)::bigint FROM memories WHERE is_deleted = FALSE"
            )
            deleted_bytes = await conn.fetchval(
                "SELECT COALESCE(SUM(LENGTH(content)), 0)::bigint FROM memories WHERE is_deleted = TRUE"
            )
            db_size = await conn.fetchval("SELECT pg_database_size(current_database())")
            db_cap = await conn.fetchval("SHOW data_directory") and None  # 占位, 用磁盘
    except Exception:
        content_bytes, deleted_bytes, db_size = 0, 0, 0
    # 磁盘总容量/已用 (只读 / 文件系统)
    disk_total = disk_used = 0
    try:
        import shutil
        du = shutil.disk_usage("/")
        disk_total, disk_used = du.total, du.used
    except Exception:
        pass
    ratio = (disk_used / disk_total * 100) if disk_total else 0
    level = "low"
    if ratio >= 90:
        level = "critical"
    elif ratio >= 70:
        level = "warning"
    return {
        "disk_used_gb": round(disk_used / 1024**3, 1),
        "disk_total_gb": round(disk_total / 1024**3, 1),
        "disk_usage_pct": round(ratio, 1),
        "memory_content_mb": round((content_bytes or 0) / 1024**2, 2),
        "deleted_content_mb": round((deleted_bytes or 0) / 1024**2, 2),
        "db_size_mb": round((db_size or 0) / 1024**2, 1),
        "level": level,
        "message": "空间充足" if level == "low" else ("⚠️ 警戒水位" if level == "warning" else "🚨 高水位"),
    }


@app.get("/api/v1/drawers/status")
async def drawers_status(user_id: str):
    """双抽屉分布 + 遗忘候选概览 + 存储水位 (周报/盘点用)。"""
    async with pool.acquire() as conn:
        temp = await conn.fetch("""
            SELECT temp_drawer, COUNT(*) AS cnt FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE GROUP BY 1 ORDER BY 1
        """, user_id)
        time_d = await conn.fetch("""
            SELECT time_drawer, COUNT(*) AS cnt FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE GROUP BY 1 ORDER BY 1
        """, user_id)
        forget = await conn.fetchrow("""
            SELECT COUNT(*) AS cnt FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE
              AND COALESCE(metadata->>'forget_candidate','false') = 'true'
        """, user_id)
        garbage = await conn.fetchrow("""
            SELECT COUNT(*) AS cnt FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE
              AND COALESCE(metadata->>'is_garbage','false') = 'true'
        """, user_id)
        pinned = await conn.fetchrow("""
            SELECT COUNT(*) AS cnt FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE
              AND COALESCE(metadata->>'pinned','false') = 'true'
        """, user_id)
    storage = await _storage_usage()
    return {
        "temp_drawers": {r["temp_drawer"]: r["cnt"] for r in temp},
        "time_drawers": {r["time_drawer"]: r["cnt"] for r in time_d},
        "forget_candidates": forget["cnt"],
        "garbage_marked": garbage["cnt"],
        "pinned": pinned["cnt"],
        "storage": storage,
    }

@app.get("/api/v1/drawers/forget-candidates")
async def forget_candidates(user_id: str, limit: int = 20):
    """列出遗忘候选 (frozen+long+非pin)。"""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, content, category, heat_score, last_accessed, created_at
            FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE
              AND COALESCE(metadata->>'forget_candidate','false') = 'true'
            ORDER BY heat_score ASC, last_accessed ASC
            LIMIT $2
        """, user_id, limit)
    return {"candidates": [dict(r) for r in rows]}

@app.post("/api/v1/drawers/forget")
async def forget_memories(user_id: str, ids: list[int] | None = None, all_candidates: bool = False):
    """[兼容] 手动遗忘: 软删指定记忆 (或全部遗忘候选)。留统计指纹。= authorize soft_delete"""
    return await authorize_action(user_id, "soft_delete", ids, all_candidates)


# v7.1 空间感知: 授权动作 — 关键遗忘/空间不足 不自动执行, 必须人工授权
class AuthorizeAction(BaseModel):
    action: str                                   # delete / recommend / expand / soft_delete / compress
    ids: list[int] | None = None                  # 指定记忆 (recommend 可省略, 返回候选)
    all_candidates: bool = False                  # 是否覆盖全部遗忘候选


@app.post("/api/v1/drawers/authorize")
async def authorize_action(user_id: str, body: AuthorizeAction | None = None,
                           action: str | None = None):
    """授权动作: 用户在空间预警/关键遗忘时手动拍板。
    - delete      彻底删除 (软删 + 指纹, 物理清理交给 cleanup)
    - soft_delete 伪删除 (is_deleted=true, 可恢复)
    - compress    压缩备份 (全文入 full_content_archived, 只留摘要)
    - expand      记录扩容提示 (不删任何记忆)
    - recommend   返回推荐候选列表 (综合分排序, 不执行)
    """
    # 兼容: body JSON 或 query action 两种传法
    ids = None
    all_candidates = False
    if body is not None:
        action = action or body.action
        ids = body.ids
        all_candidates = body.all_candidates
    if action == "expand":
        return {"status": "expand_hint",
                "message": "请扩容存储 (当前水位见 /drawers/status); 未删除任何记忆",
                "action": "expand"}

    if action == "recommend":
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, LEFT(content, 120) AS preview, category, heat_score, access_count,
                       LENGTH(content) AS content_len,
                       COALESCE(metadata->>'forget_candidate','false') AS is_candidate,
                       COALESCE(metadata->>'is_garbage','false') AS is_garbage
                FROM memories
                WHERE user_id = $1 AND is_deleted = FALSE
                  AND (COALESCE(metadata->>'forget_candidate','false') = 'true'
                       OR COALESCE(metadata->>'is_garbage','false') = 'true')
                ORDER BY heat_score ASC, COALESCE(access_count,0) ASC
                LIMIT $2
            """, user_id, 50)
        # 综合分 = 0.6×不常用度 + 0.4×(1-影响分近似: 短内容低影响)
        def score(r):
            uncommon = 1.0 / (1 + (r["access_count"] or 0))
            impact = min(1.0, (r["content_len"] or 0) / 5000)
            return round(0.6 * uncommon + 0.4 * (1 - impact), 3)
        cands = [dict(r, score=score(r)) for r in rows]
        cands.sort(key=lambda x: -x["score"])
        return {"status": "recommendations", "action": "recommend",
                "count": len(cands), "candidates": cands[:20],
                "hint": "确认后调用 POST /drawers/authorize action=delete|soft_delete|compress + ids"}

    # 执行类动作 — 安全护栏: 拦截对重要记忆的操作 (pin/高热度/preference)
    async with pool.acquire() as conn:
        if all_candidates:
            rows = await conn.fetch("""
                SELECT id FROM memories
                WHERE user_id = $1 AND is_deleted = FALSE
                  AND COALESCE(metadata->>'forget_candidate','false') = 'true'
            """, user_id)
            ids = [r["id"] for r in rows]
        if not ids:
            return {"status": "nothing", "action": action, "processed": 0}

        if action in ("delete", "soft_delete", "compress"):
            # 校验: 受保护记忆 (pin/preference/高热度) 不允许被授权动作处理
            protected = await conn.fetch("""
                SELECT id FROM memories
                WHERE user_id = $1 AND id = ANY($2::bigint[])
                  AND (COALESCE(metadata->>'pinned','false') = 'true'
                       OR category = 'preference'
                       OR heat_score >= 0.7)
            """, user_id, ids)
            if protected:
                pids = [r["id"] for r in protected]
                return {"status": "blocked_protected",
                        "message": "以下记忆受保护(pin/偏好/高热度), 不允许此操作",
                        "protected_ids": pids,
                        "hint": "如需处理请先取消保护 (PUT /memories/{id} pin=false 或降低热度)"}

        if action == "compress":
            # 压缩备份: 原文入 full_content_archived, 内容截为摘要前缀
            # ⚠️ 截断后必须重算 embedding, 否则向量=全文, 检索返回不匹配摘要
            await conn.execute("""
                UPDATE memories SET
                  full_content_archived = content,
                  content = LEFT(content, 200),
                  metadata = COALESCE(metadata,'{}'::jsonb) || '{"compressed":true}'::jsonb,
                  updated_at = NOW()
                WHERE user_id = $1 AND id = ANY($2::bigint[])
            """, user_id, ids)
            # 重算被压缩记忆的 embedding (摘要版)
            comp_rows = await conn.fetch(
                "SELECT id, content FROM memories WHERE user_id=$1 AND id = ANY($2::bigint[]) AND is_deleted=FALSE",
                user_id, ids)
            for cr in comp_rows:
                try:
                    emb = await get_embedding([cr["content"]])
                    await conn.execute(
                        "UPDATE memories SET embedding = $1::vector WHERE id = $2",
                        emb[0], cr["id"])
                except Exception:
                    pass  # 向量失败不阻塞压缩
            return {"status": "compressed", "action": "compress", "processed": len(ids)}

        if action in ("delete", "soft_delete"):
            # 留指纹 (fingerprints 表存在时), 再软删
            try:
                for mid in ids:
                    row = await conn.fetchrow("SELECT content, category FROM memories WHERE id=$1", mid)
                    if row:
                        await conn.execute("""
                            INSERT INTO memory_fingerprints (original_id, category, summary_hash, destroyed_at)
                            VALUES ($1, $2, $3, NOW())
                            ON CONFLICT DO NOTHING
                        """, mid, row["category"], hash(row["content"]) % (10**8))
            except Exception:
                pass
            await conn.execute("""
                UPDATE memories SET is_deleted = TRUE, forgotten_at = NOW()
                WHERE user_id = $1 AND id = ANY($2::bigint[])
            """, user_id, ids)
            return {"status": "soft_deleted", "action": action, "processed": len(ids),
                    "note": "软删可恢复; 彻底清理走 POST /api/v1/cleanup"}

    return {"status": "unknown_action", "action": action, "supported": ["delete", "recommend", "expand", "soft_delete", "compress"]}

# ── 反馈 API ──
@app.post("/api/v1/memories/{memory_id}/feedback")
async def feedback_memory(memory_id: int, user_id: str, feedback: str):
    async with pool.acquire() as conn:
        if feedback == "positive":
            await conn.execute("UPDATE memories SET reliability = LEAST(1.0, reliability + 0.1) WHERE id = $1 AND user_id = $2", memory_id, user_id)
        elif feedback == "negative":
            await conn.execute("UPDATE memories SET reliability = GREATEST(0.0, reliability - 0.1) WHERE id = $1 AND user_id = $2", memory_id, user_id)
        await conn.execute(
            "INSERT INTO memory_traces (memory_id, action, details) VALUES ($1, 'feedback', $2)",
            memory_id, f'{{"feedback": "{feedback}"}}'
        )
    return {"status": "feedback recorded"}

@app.get("/api/v1/memories/{memory_id}/traces")
async def get_memory_trace(memory_id: int):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM memory_traces WHERE memory_id = $1 ORDER BY executed_at", memory_id)
    return {"traces": [dict(r) for r in rows]}

# ── 多模态记忆（HERMES传描述文本，不调用视觉API）──
class MultiModalCreate(BaseModel):
    user_id: str
    content: str
    media_urls: List[str]
    media_type: str = "image"

@app.post("/api/v1/media-memories")
async def create_multimodal(mem: MultiModalCreate):
    raw_v = (await get_embedding([mem.content]))[0]
    v_str = "[" + ",".join(str(x) for x in raw_v) + "]"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO media_memories (user_id, content, media_type, media_url, embedding) VALUES ($1,$2,$3,$4,$5::vector)",
            mem.user_id, mem.content, mem.media_type, mem.media_urls[0] if mem.media_urls else "", v_str
        )
    return {"status": "stored"}

@app.get("/api/v1/media-memories")
async def search_media(user_id: str, query: str, top_k: int = 5):
    v = (await get_embedding([query]))[0]
    v_str = "[" + ",".join(str(x) for x in v) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, media_type, media_url, metadata, created_at, "
            "1 - (embedding <=> $2::vector) AS score "
            "FROM media_memories WHERE user_id=$1 "
            "ORDER BY score DESC LIMIT $3",
            user_id, v_str, top_k
        )
    return [dict(r) for r in rows]


# ── 信念 API ──
@app.post("/api/v1/beliefs")
async def create_belief(bel: BeliefCreate):
    raw_vec = (await get_embedding([bel.content]))[0]
    vec_str = "[" + ",".join(str(x) for x in raw_vec) + "]"
    async with pool.acquire() as conn:
        # 检查是否存在相同信念
        existing = await conn.fetchrow(
            "SELECT id, confidence, trajectory FROM beliefs WHERE user_id=$1 AND content=$2 AND status!='contradicted'",
            bel.user_id, bel.content
        )
        if existing:
            # 更新置信度 (取平均)
            new_conf = (existing["confidence"] + bel.confidence) / 2
            await conn.execute(
                "UPDATE beliefs SET confidence=$1, updated_at=NOW() WHERE id=$2",
                new_conf, existing["id"]
            )
            return {"status": "updated_confidence", "id": existing["id"], "confidence": new_conf}
        row = await conn.fetchrow(
            "INSERT INTO beliefs (user_id, content, confidence, evidence_memories, embedding, status) "
            "VALUES ($1,$2,$3,$4,$5::vector,$6) RETURNING id",
            bel.user_id, bel.content, bel.confidence, bel.evidence_memories, vec_str, bel.status
        )
    return {"status": "created", "id": row["id"]}

@app.post("/api/v1/beliefs/search")
async def search_beliefs(req: BeliefSearch):
    r_q = (await get_embedding([req.query]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    conditions = ["user_id = $1"]
    params = [req.user_id]
    idx = 2
    if req.status_filter:
        conditions.append(f"status = ${idx}")
        params.append(req.status_filter)
        idx += 1
    where = " AND ".join(conditions)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT id, content, confidence, status, trajectory, valid_from, "
            f"embedding <=> ${idx}::vector AS dist FROM beliefs WHERE {where} "
            f"ORDER BY dist LIMIT ${{}}".format(idx+1),
            *params, q_str, req.top_k
        )
    return [dict(r) for r in rows]

@app.get("/api/v1/beliefs/{belief_id}")
async def get_belief(belief_id: int, user_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM beliefs WHERE id=$1 AND user_id=$2", belief_id, user_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Belief not found")
    return dict(row)

@app.post("/api/v1/beliefs/{belief_id}/evolve")
async def evolve_belief(belief_id: int, user_id: str, new_confidence: float = None, evidence_id: int = None):
    """更新信念: 调整置信度/添加证据/状态自动演化"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, confidence, evidence_memories, status FROM beliefs WHERE id=$1 AND user_id=$2",
            belief_id, user_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Belief not found")
        new_status = row["status"]
        new_conf = row["confidence"] if new_confidence is None else new_confidence
        evidences = row["evidence_memories"] or []
        if evidence_id and evidence_id not in evidences:
            evidences.append(evidence_id)
            new_conf = min(1.0, new_conf + 0.1)  # 新证据+0.1
        # 状态自动演化
        if new_conf >= 0.7:
            new_status = "established"
        elif new_conf >= 0.4:
            new_status = "tentative"
        elif new_conf < 0.3:
            new_status = "hypothesis"
        trajectory = row.get("trajectory") or []
        if new_status != row["status"]:
            trajectory.append(f"{row['status']}→{new_status}")
        await conn.execute(
            "UPDATE beliefs SET confidence=$1, evidence_memories=$2, status=$3, trajectory=$4 WHERE id=$5",
            new_conf, evidences, new_status, trajectory, belief_id
        )
    return {"id": belief_id, "confidence": new_conf, "status": new_status}


# ── 反思与自我进化 ──
@app.post("/api/v1/reflect")
async def reflect(user_id: str, mode: str = "light"):
    async with pool.acquire() as conn:
        # 0. 用户活跃感知 (v7.2 遗忘节流): 最近7天有写入/访问 = 活跃
        #    主人不在场时暂停衰减 — 记忆陪主人等, 不独自变冷 (用户红线: 旅游回来全变冷)
        last_active = await conn.fetchval("""
            SELECT GREATEST(MAX(created_at), MAX(last_accessed)) FROM memories
            WHERE user_id = $1 AND is_deleted = FALSE
        """, user_id)
        user_active = last_active is not None and last_active >= datetime.now(timezone.utc) - timedelta(days=7)
        absence_days = (datetime.now(timezone.utc) - last_active).days if (last_active is not None and not user_active) else 0
        # 1. 热度v2: 多维衰减
        # 时间衰减 (最后一次访问越久越冷); v6.3: 保护衰减 — pinned/preference 几乎不衰减
        # v7.2: 用户不活跃时暂停全部衰减 (只标记 pause 透明)
        if user_active:
            await conn.execute("""
                UPDATE memories SET heat_score = GREATEST(0.0, heat_score -
                    CASE
                        WHEN metadata->>'pinned' = 'true' OR category = 'preference' THEN 0.005
                        WHEN last_accessed IS NULL THEN 0.02
                        WHEN last_accessed < NOW() - INTERVAL '90 days' THEN 0.08
                        WHEN last_accessed < NOW() - INTERVAL '30 days' THEN 0.04
                        WHEN last_accessed < NOW() - INTERVAL '7 days' THEN 0.02
                        ELSE 0.01
                    END
                ) WHERE user_id = $1 AND is_deleted = FALSE
            """, user_id)
            # 访问加权 (近期高频访问+0.05)
            await conn.execute("""
                UPDATE memories SET heat_score = LEAST(1.0, heat_score + 0.05)
                WHERE user_id = $1 AND is_deleted = FALSE AND access_count >= 5
                  AND last_accessed > NOW() - INTERVAL '7 days'
            """, user_id)
        else:
            # 主人不在: 不衰减, 打暂停标记 (透明, 恢复时清除)
            await conn.execute("""
                UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) ||
                  ('{"paused_absence":true,"paused_days":' || $2::text || '}')::jsonb
                WHERE user_id = $1 AND is_deleted = FALSE
            """, user_id, absence_days)
            # 回归检测: 若之前有暂停标记但现在活跃了, 清除 (下次活跃轮触发)
        # 活跃回归: 清除暂停标记 (用户回来了, 记忆恢复独立衰减)
        if user_active:
            await conn.execute("""
                UPDATE memories SET metadata = metadata - 'paused_absence' - 'paused_days'
                WHERE user_id = $1 AND is_deleted = FALSE
                  AND metadata ? 'paused_absence'
            """, user_id)
        # 矛盾记忆加速衰减 (始终运行 — 矛盾是数据质量问题, 不因主人不在而保留)
        await conn.execute("""
            UPDATE memories SET heat_score = GREATEST(0.0, heat_score - 0.1)
            WHERE user_id = $1 AND is_deleted = FALSE AND invalid_at IS NOT NULL
        """, user_id)
        # 2. 层级自动迁移 (v6.0: tier=价值分层, 与 TMT 时间树 tmt_level 解耦)
        #    L4 不再直接删除 — 仅标记待清理, 保留可恢复; 清理交给 cleanup API
        await conn.execute("UPDATE memories SET tier = 'L1' WHERE user_id = $1 AND heat_score > 0.7 AND tier != 'L1'", user_id)
        await conn.execute("UPDATE memories SET tier = 'L2' WHERE user_id = $1 AND heat_score BETWEEN 0.2 AND 0.7 AND tier NOT IN ('L2','L3','L4')", user_id)
        await conn.execute("UPDATE memories SET tier = 'L3' WHERE user_id = $1 AND heat_score < 0.2 AND last_accessed < NOW() - INTERVAL '30 days' AND tier NOT IN ('L3','L4')", user_id)
        await conn.execute("UPDATE memories SET tier = 'L4', forgotten_at = NOW() WHERE user_id = $1 AND heat_score < 0.05 AND last_accessed < NOW() - INTERVAL '90 days' AND is_deleted = FALSE AND tier != 'L4'", user_id)
        # 2.5 双抽屉流转 (v7.1 抽屉化: 温度抽屉 × 时间抽屉)
        # 温度: hot≥0.7 / normal 0.3-0.7 / cool 0.1-0.3 / frozen<0.1 (与 tier L1-L4 对齐但独立维度)
        # 时间: recent<30d / mid 30-90d / long≥90d (基于 last_accessed)
        await conn.execute("""
            UPDATE memories SET temp_drawer = CASE
                WHEN heat_score >= 0.7 THEN 'hot'
                WHEN heat_score >= 0.3 THEN 'normal'
                WHEN heat_score >= 0.1 THEN 'cool'
                ELSE 'frozen'
            END
            WHERE user_id = $1 AND is_deleted = FALSE
        """, user_id)
        await conn.execute("""
            UPDATE memories SET time_drawer = CASE
                WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '30 days' THEN 'recent'
                WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '90 days' THEN 'mid'
                ELSE 'long'
            END
            WHERE user_id = $1 AND is_deleted = FALSE
        """, user_id)
        # 2.6 Bjork S/R 分离 (v7.2): 存储强度S不衰减 / 检索强度R指数衰减(半衰期30天)
        #    R = R0 * 0.5^(天数/30), 下限1; 访问后重置 R=S; pin 兜底 R≥5
        #    回退开关: metadata->>'use_sr' = 'false' 则跳过 (保留纯 heat 模式)
        #    v7.2 节流: 用户不活跃(user_active=False)时 R 不衰减 (只保留访问重置), 抽屉保持
        if user_active:
            await conn.execute("""
                UPDATE memories SET
                  retrieval_strength = GREATEST(1.0,
                    CASE
                      WHEN COALESCE(metadata->>'pinned','false') = 'true' THEN GREATEST(5.0, retrieval_strength * POW(0.5, (EXTRACT(EPOCH FROM (NOW() - COALESCE(last_accessed, created_at)))/86400.0)/30.0))
                      WHEN last_accessed IS NOT NULL AND last_accessed >= NOW() - INTERVAL '7 days'
                        THEN GREATEST(storage_strength, retrieval_strength * POW(0.5, (EXTRACT(EPOCH FROM (NOW() - last_accessed))/86400.0)/30.0))
                      ELSE retrieval_strength * POW(0.5, (EXTRACT(EPOCH FROM (NOW() - COALESCE(last_accessed, created_at)))/86400.0)/30.0)
                    END),
                  temp_drawer = CASE
                    WHEN storage_strength >= 7 AND retrieval_strength >= 5 THEN 'hot'
                    WHEN storage_strength >= 5 OR retrieval_strength >= 3 THEN 'normal'
                    WHEN storage_strength >= 3 THEN 'cool'
                    ELSE 'frozen'
                  END
                WHERE user_id = $1 AND is_deleted = FALSE
                  AND COALESCE(metadata->>'use_sr','true') = 'true'
            """, user_id)
        else:
            # 主人不在: 仅保留「近期访问重置」, 不做时间衰减; 清除暂停标记由回归时处理
            await conn.execute("""
                UPDATE memories SET retrieval_strength = GREATEST(retrieval_strength, storage_strength)
                WHERE user_id = $1 AND is_deleted = FALSE
                  AND last_accessed IS NOT NULL AND last_accessed >= NOW() - INTERVAL '7 days'
            """, user_id)
        # 遗忘候选标记: frozen + long + 非pin + 非preference → forget_candidate=true (不物理删, 等30天宽限或用户确认)
        await conn.execute("""
            UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{"forget_candidate":true}'::jsonb
            WHERE user_id = $1 AND is_deleted = FALSE
              AND temp_drawer = 'frozen' AND time_drawer = 'long'
              AND COALESCE(metadata->>'pinned','false') != 'true'
              AND category != 'preference'
        """, user_id)
        # 遗忘候选降温: 被命中过但不再相关的记忆, 每轮 reflect 额外 -0.03 (加速沉降, 对应 Mem0 salience 思路)
        await conn.execute("""
            UPDATE memories SET heat_score = GREATEST(0.0, heat_score - 0.03)
            WHERE user_id = $1 AND is_deleted = FALSE
              AND COALESCE(metadata->>'forget_candidate','false') = 'true'
              AND COALESCE(metadata->>'pinned','false') != 'true'
        """, user_id)
        # 3. 深度模式: 实体提取
        if mode == "deep":
            unproc = await conn.fetch("SELECT m.id, m.content FROM memories m LEFT JOIN memory_entities me ON m.id = me.memory_id WHERE m.user_id = $1 AND me.memory_id IS NULL AND m.is_deleted = FALSE LIMIT 100", user_id)
            extracted = 0
            import re
            for row in unproc:
                cand = set()
                for m in re.finditer(r'[\u201c\u201d\u300c\u300d]([^\u201c\u201d\u300c\u300d]{2,15})[\u201c\u201d\u300c\u300d]', row["content"]):
                    cand.add(m.group(1).strip())
                if not cand:
                    for p in re.split(r'[、，．！？,.!?\s的和在是了]+', row["content"]):
                        p = p.strip()
                        if 2 <= len(p) <= 15:
                            cand.add(p)
                for name in cand:
                    try:
                        ex = await conn.fetchrow("SELECT id FROM entities WHERE user_id=$1 AND name=$2", user_id, name)
                        if not ex:
                            await sync_entities_to_age(conn, row["id"], [name], user_id)
                            extracted += 1
                    except Exception:
                        pass
            if extracted > 0:
                await conn.execute("UPDATE memories SET heat_score = heat_score + 0.1 WHERE user_id = $1 AND is_deleted = FALSE AND id IN (SELECT memory_id FROM memory_entities)", user_id)
    return {"status": f"Reflection ({mode}) completed"}

@app.post("/api/v1/cleanup")
async def cleanup(user_id: str, threshold: float = 0.1):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE memories SET is_deleted = TRUE, forgotten_at = NOW() WHERE user_id = $1 AND heat_score < $2", user_id, threshold)
    return {"status": "cleanup done"}

@app.get("/api/v1/health/{user_id}")
async def health_report(user_id: str):
    async with pool.acquire() as conn:
        tiers = await conn.fetch("SELECT tier, COUNT(*) as cnt FROM memories WHERE user_id = $1 AND is_deleted = FALSE GROUP BY tier", user_id)
    return {"tiers": {r["tier"]: r["cnt"] for r in tiers}}

# ── 自描述化 API ──
@app.get("/")
async def root():
    return {"service": "Mnemosyne Memory Engine v6.0", "docs": "/api/v1/capabilities"}

@app.get("/api/v1/capabilities")
async def capabilities():
    return {
        "service": "Mnemosyne OS v6.4.0",
        "version": "7.2.0",
        "description": "个人AI记忆库 — 存入、搜索、追溯、演化",
        "auth": "X-API-Token (Nginx层)",
        "base_url": "https://your-server.example.com/mnemosyne",
        "endpoints": [
            {"path": "POST /api/v1/memories", "purpose": "存入一条记忆。自动向量化+实体提取+矛盾检测(相似内容合并/冲突标记时间窗口)", "params": {"user_id": "str", "content": "str", "category": "fact|experience|belief"}, "example": "curl -X POST https://your-server.example.com/mnemosyne/api/v1/memories -H 'X-API-Token: <token>' -H 'Content-Type: application/json' -d '{\"user_id\":\"noah\",\"content\":\"要记住的内容\"}'", "tags": ["core", "write"]},
            {"path": "POST /api/v1/memories/search", "purpose": "4维检索(语义向量+BM25关键词+时序加权+图遍历) + 交叉编码重排", "params": {"user_id": "str", "query": "str", "top_k": "int(5)"}, "example": "curl -X POST https://your-server.example.com/mnemosyne/api/v1/memories/search -H 'X-API-Token: <token>' -H 'Content-Type: application/json' -d '{\"user_id\":\"noah\",\"query\":\"搜索内容\"}'", "tags": ["core", "read"]},
            {"path": "GET /api/v1/memories", "purpose": "按热度/分类列出记忆", "params": {"user_id": "str", "limit": "int(20)", "tier": "str?", "category": "str?"}, "tags": ["core", "read"]},
            {"path": "GET /api/v1/memories/{id}", "purpose": "获取单条记忆详情", "tags": ["core", "read"]},
            {"path": "DELETE /api/v1/memories/{id}", "purpose": "软删除记忆", "tags": ["core", "write"]},
            {"path": "POST /api/v1/memories/{id}/feedback", "purpose": "记录反馈(positive/negative), 影响reliability评分", "params": {"user_id": "str", "feedback": "positive|negative"}, "tags": ["core", "write"]},
            {"path": "POST /api/v1/memories/{id}/restore", "purpose": "恢复已删除的记忆", "tags": ["core", "write"]},
            {"path": "POST /api/v1/memories/evolve", "purpose": "触发记忆进化(合并重复/清理/提升)", "tags": ["system"]},
            {"path": "GET /api/v1/memories/heat-top", "purpose": "热度排行", "tags": ["core", "read"]},
            {"path": "POST /api/v1/reflect", "purpose": "手动触发Reflector: 热度衰减+层级迁移+实体提取", "params": {"user_id": "str", "mode": "light|deep"}, "tags": ["system"]},
            {"path": "POST /api/v1/beliefs", "purpose": "创建信念。自动与已有信念合并置信度", "params": {"user_id": "str", "content": "str", "confidence": "float(0.5)", "status": "tentative|established"}, "tags": ["belief"]},
            {"path": "POST /api/v1/beliefs/search", "purpose": "语义搜索信念", "tags": ["belief"]},
            {"path": "GET /api/v1/beliefs/{id}", "purpose": "获取信念详情(含置信度/轨迹/证据)", "tags": ["belief"]},
            {"path": "POST /api/v1/beliefs/{id}/evolve", "purpose": "演化信念: 调整置信度+添加证据, 状态自动演进", "tags": ["belief"]},
            {"path": "POST /api/v1/graph/search", "purpose": "AGE知识图谱多跳搜索(通过实体关联发现记忆)", "tags": ["graph"]},
            {"path": "POST /api/v1/wiki", "purpose": "创建Wiki页面(手动知识库)", "tags": ["wiki"]},
            {"path": "POST /api/v1/wiki/search", "purpose": "语义搜索Wiki", "tags": ["wiki"]},
            {"path": "POST /api/v1/extract-entities", "purpose": "从未处理记忆中批量提取实体到AGE图", "tags": ["system"]},
            {"path": "POST /api/v1/media-memories", "purpose": "存入多模态记忆", "tags": ["media"]},
            {"path": "GET /api/v1/echo", "purpose": "连通性测试", "tags": ["system"]},
            {"path": "GET /api/v1/capabilities", "purpose": "本能力清单", "tags": ["meta"]},
            {"path": "GET /api/v1/health/{user_id}", "purpose": "健康检查(层级统计)", "tags": ["system"]}
        ],
        "graceful_degradation": {
            "rerank_unavailable": "降级为纯向量+BM25+时序混合搜索(不经过交叉编码)",
            "embed_unavailable": "全部API不可用(需修复llama-embed.service)"
        },
        "quick_start": "1. 存记忆 POST /api/v1/memories → 2. 搜记忆 POST /api/v1/memories/search → 3. 触反思 POST /api/v1/reflect → 4. 看健康 GET /api/v1/health/{user_id}"
    }

@app.get("/api/v1/echo")
async def echo():
    return {"status": "ok", "service": "Mnemosyne OS", "version": "7.2.0"}

# ── v7.0 魔法记忆宫殿 API ──
@app.get("/api/v1/palace/status")
async def palace_status(user_id: str = "default"):
    """宫殿状态: 分类树统计 + 著录卡片数 + 档号覆盖率"""
    import palace
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT count(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE", user_id)
        archived = await conn.fetchval(
            "SELECT count(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND archive_no IS NOT NULL", user_id)
        cards = await conn.fetchval(
            "SELECT count(*) FROM tome_cards", )
        dist = await conn.fetch(
            "SELECT wing, room, count(*) n FROM tome_cards GROUP BY wing, room ORDER BY wing, room LIMIT 30")
    return {
        "total_memories": total,
        "archived": archived,
        "archive_coverage": round(100.0 * (archived or 0) / max(total, 1), 1),
        "tome_cards": cards,
        "taxonomy": [{"wing": r["wing"], "room": r["room"], "count": r["n"]} for r in dist],
    }

@app.post("/api/v1/palace/archive")
async def palace_archive(user_id: str = "default", limit: int = 500):
    """手动触发存量归档 (幂等, 分批)"""
    import palace
    result = await palace.init_palace(pool)
    # 返回本次归档数 (只数新处理的)
    return {"classified": result["classified"], "cards": result["cards"]}

@app.get("/api/v1/palace/summon")
async def palace_summon(q: str, user_id: str = "default", top_k: int = 5):
    """魔法召唤: 三通道 (点名精确/引导范围/共鸣语义)"""
    import palace
    result = await palace.summon(pool, q, user_id, top_k)
    return result

@app.post("/api/v1/palace/refine")
async def palace_refine(limit: int = 20):
    """资料室精炼: LLM 生成题名/摘要/标签"""
    import palace
    return await palace.refine_cards(pool, limit=limit)

@app.post("/api/v1/palace/extract")
async def palace_extract(batch: int = 20):
    """资料室事实提取: 对话→facts→自动建档 (幂等)"""
    import palace
    return await palace.extract_facts_pipeline(pool, batch=batch)

@app.post("/api/v1/palace/lifecycle")
async def palace_lifecycle():
    """永恒分级: 短期过期撤架 + 永久卷热度保护"""
    import palace
    return await palace.apply_lifecycle(pool)

@app.post("/api/v1/palace/pin")
async def palace_pin(memory_id: int, retention: str = "permanent"):
    """把某条记忆钉为永久卷 (规则/红线/身份类)"""
    if retention not in ("permanent", "long", "short"):
        raise HTTPException(status_code=400, detail="retention must be permanent/long/short")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tome_cards SET retention=$1 WHERE memory_id=$2", retention, memory_id)
    return {"memory_id": memory_id, "retention": retention}

@app.post("/api/v1/graph/search")
async def graph_search(query: str, user_id: str, max_hops: int = 2):
    r_q = (await get_embedding([query]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, type, embedding <=> $1::vector AS dist FROM entities WHERE user_id = $2 ORDER BY dist LIMIT 5", q_str, user_id)
        entity_ids = [r["id"] for r in rows]
        if not entity_ids:
            return {"nodes": [], "memories": []}
        if max_hops > 1:
            try:
                id_list = ", ".join(chr(39) + str(e) + chr(39) for e in entity_ids)
                cql = "SELECT * FROM cypher('mnemosyne_graph', $cyq$ MATCH (e:Entity) WHERE e.entity_id IN [" + id_list + "] MATCH (e)-[*1.." + str(max_hops) + "]-(related:Entity) RETURN DISTINCT related.entity_id $cyq$) AS (entity_id agtype)"
                age_rows = await conn.fetch(cql)
                for r in age_rows:
                    raw = str(r[0]).replace(chr(34), "").strip()
                    if raw and raw.isdigit():
                        extra = int(raw)
                        if extra not in entity_ids:
                            entity_ids.append(extra)
            except Exception:
                pass
        mems = await conn.fetch(
            "SELECT m.content FROM memories m "
            "JOIN memory_entities me ON m.id = me.memory_id "
            "WHERE me.entity_id = ANY($1) LIMIT 10",
            entity_ids
        )
    return {"nodes": [dict(r) for r in rows], "memories": [m["content"] for m in mems]}

@app.post("/api/v1/wiki")
async def create_wiki(user_id: str, title: str, content: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("INSERT INTO wiki_pages (user_id, title, content) VALUES ($1,$2,$3) RETURNING id", user_id, title, content)
        page_id = row["id"]
        r_v = (await get_embedding([content]))[0]
        v_str = "[" + ",".join(str(x) for x in r_v) + "]"
        await conn.execute("INSERT INTO wiki_versions (page_id, version, content, embedding) VALUES ($1,1,$2,$3::vector)", page_id, content, v_str)
    return {"id": page_id, "status": "created"}

@app.post("/api/v1/wiki/search")
async def search_wiki(query: str, user_id: str, top_k: int = 5):
    r_q = (await get_embedding([query]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT wv.content, wv.embedding <=> $1::vector AS dist FROM wiki_versions wv JOIN wiki_pages wp ON wv.page_id = wp.id WHERE wp.user_id = $2 ORDER BY dist LIMIT $3", q_str, user_id, top_k)
        return [dict(r) for r in rows]

@app.post("/api/v1/extract-entities")
async def extract_entities(user_id: str, max_memories: int = 50):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT m.id, m.content FROM memories m LEFT JOIN memory_entities me ON m.id = me.memory_id WHERE m.user_id = $1 AND me.memory_id IS NULL AND m.is_deleted = FALSE LIMIT " + str(max_memories), user_id)
        extracted = 0
        import re
        for row in rows:
            cand = set()
            for m in re.finditer(r'[""“”「」]([^"“”「」]{2,10})["“”「」]', row["content"]):
                cand.add(m.group(1).strip())
            if not cand:
                for p in re.split(r'[、，．！？,.!?\s的和在是了]+', row["content"]):
                    p = p.strip()
                    if 2 <= len(p) <= 15:
                        cand.add(p)
            for name in cand:
                try:
                    ex = await conn.fetchrow("SELECT id FROM entities WHERE user_id=$1 AND name=$2", user_id, name)
                    if not ex:
                        await sync_entities_to_age(conn, row["id"], [name], user_id)
                        extracted += 1
                except Exception:
                    pass
    return {"status": "done", "extracted": extracted, "from": len(list(rows))}



@app.get("/api/v1/memories/{memory_id}")
async def get_memory(memory_id: int, user_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, user_id, content, category, tier, heat_score, importance, reliability, metadata, created_at, last_accessed, access_count, is_deleted FROM memories WHERE id=$1 AND user_id=$2", memory_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found")
    return dict(row)

@app.post("/api/v1/memories/{memory_id}/restore")
async def restore_memory(memory_id: int, user_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("UPDATE memories SET is_deleted=FALSE, forgotten_at=NULL, heat_score=0.3, tier='L2' WHERE id=$1 AND user_id=$2 AND is_deleted=TRUE RETURNING id, content, tier, heat_score", memory_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Memory not found or not deleted")
    return {"status": "restored", "memory": dict(row)}


# RAG Chunking
@app.post("/api/v1/memories/{memory_id}/chunk")
async def chunk_memory_endpoint(memory_id: int):
    result = await chunk_memory_fn(pool, memory_id, get_embedding)
    return result

@app.post("/api/v1/memories/chunk-all")
async def chunk_all_endpoint(user_id: str = "default", batch_size: int = 50):
    result = await chunk_all_unprocessed(pool, user_id, get_embedding, batch_size)
    return result

@app.get("/api/v1/memories/chunks/stats")
async def chunk_stats_endpoint(user_id: str = "default"):
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT count(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW())", user_id)
        chunked = await conn.fetchval("SELECT count(DISTINCT m.id) FROM memories m JOIN memory_chunks mc ON m.id=mc.memory_id WHERE m.user_id=$1 AND m.is_deleted=FALSE AND (m.valid_to IS NULL OR m.valid_to > NOW()) AND m.embedding IS NOT NULL", user_id)
        total_chunks = await conn.fetchval("SELECT count(*) FROM memory_chunks mc JOIN memories m ON m.id=mc.memory_id WHERE m.user_id=$1 AND m.is_deleted=FALSE AND (m.valid_to IS NULL OR m.valid_to > NOW()) AND m.embedding IS NOT NULL", user_id)
    return {"total_memories": total, "chunked": chunked or 0, "total_chunks": total_chunks or 0}

class ChunkSearchRequest(BaseModel):
    q: str
    user_id: str = "default"
    top_k: int = 10

@app.post("/api/v1/memories/search-chunks")
async def search_chunks(req: ChunkSearchRequest):
    """Chunk级语义搜索 — 比全记忆搜索更精准"""
    r_q = (await get_embedding([req.q]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    async with pool.acquire() as conn:
        chunk_rows = await conn.fetch(
            "SELECT mc.id, mc.content, mc.memory_id, m.content as full_content, "
            "mc.embedding <=> $2::vector AS dist "
            "FROM memory_chunks mc "
            "JOIN memories m ON m.id = mc.memory_id "
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE AND (m.valid_to IS NULL OR m.valid_to > NOW()) AND m.embedding IS NOT NULL "
            "ORDER BY dist LIMIT $3",
            req.user_id, q_str, req.top_k
        )
        mem_rows = await conn.fetch(
            "SELECT id, content, embedding <=> $2::vector AS dist "
            "FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND (valid_to IS NULL OR valid_to > NOW()) "
            "ORDER BY dist LIMIT $3",
            req.user_id, q_str, req.top_k
        )
    results = []
    seen = set()
    for r in chunk_rows:
        mid = r["memory_id"]
        if mid not in seen:
            seen.add(mid)
            results.append({
                "type": "chunk", "memory_id": mid, "chunk_id": r["id"],
                "chunk_content": r["content"][:300],
                "full_content": r["full_content"][:500],
                "dist": round(float(r["dist"]), 4)
            })
    for r in mem_rows:
        if r["id"] not in seen and len(results) < req.top_k:
            results.append({
                "type": "memory", "memory_id": r["id"],
                "content": r["content"][:500],
                "dist": round(float(r["dist"]), 4)
            })
    return {"query": req.q, "total": len(results), "results": results}




class SessionArchiveRequest(BaseModel):
    user_id: str = "default"
    session_id: str = ""
    title: str = ""
    content: str  # 完整对话文本

@app.post("/api/v1/sessions/archive")
async def archive_session(req: SessionArchiveRequest):
    """归档完整对话到记忆宫殿 — 自动向量化+入TMT蒸馏"""
    content = req.content.strip()
    if not content:
        return {"archived": False, "reason": "empty_content"}
    
    async with pool.acquire() as conn:
        # 生成 embedding
        raw = (await get_embedding([content[:2000]]))[0]
        vec_str = "[" + ",".join(str(x) for x in raw) + "]"
        
        # 检测冲突
        conflict = await detect_conflict(conn, req.user_id, content, vec_str)
        
        if conflict["action"] == "merge":
            return {"archived": False, "reason": "duplicate", "merged_into": conflict["id"]}
        
        # 存入记忆
        row = await conn.fetchrow(
            "INSERT INTO memories (user_id, content, category, embedding, heat_score, "
            "metadata, tmt_level) VALUES ($1,$2,$3,$4::vector,$5,$6,$7) RETURNING id",
            req.user_id, content, "session", vec_str, 0.6,
            json.dumps({"session_id": req.session_id, "title": req.title}),
            1  # tmt_level=1，纳入蒸馏
        )
        memory_id = row["id"]
        
        # 实体提取 (异步，不阻塞)
        try:
            from core.llm import call_llm_json
            entities_prompt = f"从以下对话中提取关键实体(项目名/人名/技术名/概念)，输出JSON: {{\"entities\": [\"实体1\", \"实体2\"]}}\n\n对话片段:\n{content[:1500]}"
            entities_result = call_llm_json(entities_prompt, tier=2)
            entities_data = json.loads(entities_result.get("content", "{}"))
            entities = entities_data.get("entities", [])
            if entities:
                await sync_entities_to_age(conn, memory_id, entities, req.user_id)
        except Exception:
            pass
        
        # 生成一句话摘要
        summary = ""
        try:
            from core.llm import call_llm_fast
            summary_result = call_llm_fast(f"用一句话概括这段对话(不超过30字):\n{content[:1000]}")
            summary = summary_result.get("content", "")[:100]
        except Exception:
            summary = content[:100]
        
        return {
            "archived": True,
            "memory_id": memory_id,
            "summary": summary,
            "content_length": len(content)
        }
# ── 会话消息同步 (Hermes state.db → Mnemosyne) ──

class SessionMessagesUpload(BaseModel):
    messages: list  # [{role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning}, ...]

@app.post("/api/v1/sessions/{session_id}/messages")
async def upload_session_messages(session_id: str, req: SessionMessagesUpload):
    """批量写入会话消息 — Hermes on_session_end 调用"""
    async with pool.acquire() as conn:
        count = 0
        for msg in req.messages:
            await conn.execute(
                "INSERT INTO conversation_messages (session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT DO NOTHING",
                session_id,
                msg.get("role", ""),
                msg.get("content", ""),
                msg.get("tool_call_id"),
                json.dumps(msg.get("tool_calls")) if msg.get("tool_calls") else None,
                msg.get("tool_name"),
                msg.get("timestamp", 0.0),
                msg.get("token_count"),
                msg.get("finish_reason"),
                msg.get("reasoning")
            )
            count += 1
    return {"status": "stored", "session_id": session_id, "messages": count}


@app.get("/api/v1/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 200, before_id: int = None):
    """读取会话消息 — UI 前端加载历史"""
    async with pool.acquire() as conn:
        if before_id:
            rows = await conn.fetch(
                "SELECT id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning, created_at "
                "FROM conversation_messages WHERE session_id=$1 AND id < $2 ORDER BY timestamp ASC LIMIT $3",
                session_id, before_id, limit
            )
        else:
            rows = await conn.fetch(
                "SELECT id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, token_count, finish_reason, reasoning, created_at "
                "FROM conversation_messages WHERE session_id=$1 ORDER BY timestamp ASC LIMIT $2",
                session_id, limit
            )
    return {"session_id": session_id, "messages": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/v1/sessions")
async def list_sessions(user_id: str = "default", limit: int = 20):
    """列出最近会话 — UI 会话列表"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT session_id, MIN(timestamp) as start_time, MAX(timestamp) as end_time, "
            "COUNT(*) as msg_count, SUM(COALESCE(token_count,0)) as total_tokens "
            "FROM conversation_messages GROUP BY session_id "
            "ORDER BY MIN(timestamp) DESC LIMIT $1", limit
        )
    return {"sessions": [dict(r) for r in rows], "count": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8010, workers=4, log_level="info")