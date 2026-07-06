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
from typing import List, Optional
from datetime import datetime, timezone

# ── v5.0: 模块化导入 ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PG_USER, PG_PASSWORD, PG_DB, PG_HOST, PG_PORT, HOST, PORT
from core.embedding import get_embedding_async
from core.llm import call_llm as llm_call
from core.chunker import chunk_memory as chunk_memory_fn, chunk_all_unprocessed
# TMT (兼容现有 v2.1 路由)
import tmt.router as tmt_module
from tmt.router import router as tmt_router

app = FastAPI(title="Mnemosyne OS v5.0 — 认知型记忆操作系统")

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

        await conn.execute("SELECT * FROM cypher('mnemosyne_graph', $$ CREATE (:Entity {entity_id: '%s', name: '%s', user_id: '%s'}) $$) AS (v agtype)" % (eid, name, user_id))
        
        await conn.execute("INSERT INTO memory_entities (memory_id, entity_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", memory_id, eid)
        try:
            await conn.execute("SELECT * FROM cypher('mnemosyne_graph', $$ MERGE (m:Memory {memory_id: '%s'}) WITH m MATCH (e:Entity {entity_id: '%s'}) MERGE (m)-[:MENTIONS]->(e) $$) AS (v agtype)"% (memory_id, eid))
        except Exception as e:
            pass
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
            "FROM memories m WHERE m.user_id=$1 AND m.is_deleted=FALSE "
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
            "FROM memories WHERE user_id=$1 AND is_deleted=FALSE "
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
    """每个新连接加载 AGE 扩展"""
    await conn.execute("LOAD 'age'")

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
    user_id: str
    project_id: Optional[str] = None
    content: str
    category: str = "fact"
    metadata: dict = {}
    entities: Optional[List[str]] = None

@app.post("/api/v1/memories")
async def create_memory(mem: MemoryCreate):
    raw_vec = (await get_embedding([mem.content]))[0]
    vec_str = "[" + ",".join(str(x) for x in raw_vec) + "]"
    async with pool.acquire() as conn:
        # 矛盾检测
        conflict = await detect_conflict(conn, mem.user_id, mem.content, vec_str)
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
        # 正常存入（含valid_from）
        row = await conn.fetchrow(
            'INSERT INTO memories (user_id, project_id, content, category, embedding, metadata, valid_from) '
            'VALUES ($1,$2,$3,$4,$5::vector,$6,NOW()) RETURNING id',
            mem.user_id, mem.project_id, mem.content, mem.category, vec_str,
            json.dumps(locals().get("meta", mem.metadata))
        )
        mid = row["id"]
        if mem.entities:
            await sync_entities_to_age(conn, mid, mem.entities, mem.user_id)
    return {"status": "stored", "id": row["id"]}

class MemorySearch(BaseModel):
    user_id: str
    project_id: Optional[str] = None
    query: str
    top_k: int = 5
    category_filter: Optional[str] = None
    tier_filter: Optional[str] = None

@app.post("/api/v1/memories/search")
async def search_memories(req: MemorySearch):
    """Full search: BM25 + rerank + trust_score (inline BM25 SQL)"""
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
            "FROM memories m WHERE m.user_id=$1 AND m.is_deleted=FALSE "
            "ORDER BY (0.40 * (1.0 - (m.embedding <=> $2::vector)) "
            "  + 0.15 * (" + bm25_sql + ") "
            "  + 0.15 * (" + temporal_sql + ") "
            "  + 0.15 * m.reliability "
            "  + 0.15 * GREATEST(0.0, m.heat_score)) DESC "
            "LIMIT $3",
            req.user_id, q_str, req.top_k
        )
    
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
async def list_memories(user_id: str, limit: int = 20, tier: Optional[str] = None, category: Optional[str] = None):
    query = "SELECT id, content, category, tier, heat_score, created_at FROM memories WHERE user_id = $1 AND is_deleted = FALSE"
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
    query += f" ORDER BY created_at DESC LIMIT ${idx}"
    params.append(limit)
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]

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
        rows = await conn.fetch("SELECT id, content, category, tier, heat_score, access_count, created_at FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND heat_score>=$2 ORDER BY heat_score DESC LIMIT $3", user_id, min_heat, limit)
    return {"memories": [dict(r) for r in rows]}

@app.get("/api/v1/memories/stats")
async def get_memory_stats(user_id: str = "default"):
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE", user_id)
        by_cat = await conn.fetch(
            "SELECT category, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE GROUP BY category ORDER BY cnt DESC",
            user_id
        )
        by_tier = await conn.fetch(
            "SELECT tier, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE GROUP BY tier ORDER BY tier",
            user_id
        )
        avg_h = await conn.fetchval("SELECT COALESCE(AVG(heat_score), 0) FROM memories WHERE user_id=$1 AND is_deleted=FALSE", user_id)
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
            "SELECT tier, COUNT(*) AS cnt FROM memories WHERE user_id=$1 AND is_deleted=FALSE GROUP BY tier ORDER BY tier",
            user_id
        )
        l1s = await conn.fetch(
            "SELECT id, content, category, heat_score FROM memories WHERE user_id=$1 AND is_deleted=FALSE AND tier='L1' ORDER BY heat_score DESC LIMIT $2",
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
        # 1. 热度v2: 多维衰减
        # 时间衰减 (最后一次访问越久越冷)
        await conn.execute("""
            UPDATE memories SET heat_score = GREATEST(0.0, heat_score -
                CASE
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
        # 矛盾记忆加速衰减
        await conn.execute("""
            UPDATE memories SET heat_score = GREATEST(0.0, heat_score - 0.1)
            WHERE user_id = $1 AND is_deleted = FALSE AND invalid_at IS NOT NULL
        """, user_id)
        # 2. 层级自动迁移
        await conn.execute("UPDATE memories SET tier = 'L1' WHERE user_id = $1 AND heat_score > 0.7 AND tier != 'L1'", user_id)
        await conn.execute("UPDATE memories SET tier = 'L2' WHERE user_id = $1 AND heat_score BETWEEN 0.2 AND 0.7 AND tier NOT IN ('L2','L3','L4')", user_id)
        await conn.execute("UPDATE memories SET tier = 'L3' WHERE user_id = $1 AND heat_score < 0.2 AND last_accessed < NOW() - INTERVAL '30 days'", user_id)
        await conn.execute("UPDATE memories SET tier = 'L4', is_deleted = TRUE, forgotten_at = NOW() WHERE user_id = $1 AND heat_score < 0.05 AND last_accessed < NOW() - INTERVAL '90 days'", user_id)
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
    return {"service": "Mnemosyne Memory Engine v2.1", "docs": "/api/v1/capabilities"}

@app.get("/api/v1/capabilities")
async def capabilities():
    return {
        "service": "Mnemosyne OS v5.0",
        "version": "5.2.1",
        "description": "个人AI记忆库 — 存入、搜索、追溯、演化",
        "auth": "X-API-Token (Nginx层)",
        "base_url": "https://gz.g-cat.cn/mnemosyne",
        "endpoints": [
            {"path": "POST /api/v1/memories", "purpose": "存入一条记忆。自动向量化+实体提取+矛盾检测(相似内容合并/冲突标记时间窗口)", "params": {"user_id": "str", "content": "str", "category": "fact|experience|belief"}, "example": "curl -X POST https://gz.g-cat.cn/mnemosyne/api/v1/memories -H 'X-API-Token: <token>' -H 'Content-Type: application/json' -d '{\"user_id\":\"noah\",\"content\":\"要记住的内容\"}'", "tags": ["core", "write"]},
            {"path": "POST /api/v1/memories/search", "purpose": "4维检索(语义向量+BM25关键词+时序加权+图遍历) + 交叉编码重排", "params": {"user_id": "str", "query": "str", "top_k": "int(5)"}, "example": "curl -X POST https://gz.g-cat.cn/mnemosyne/api/v1/memories/search -H 'X-API-Token: <token>' -H 'Content-Type: application/json' -d '{\"user_id\":\"noah\",\"query\":\"搜索内容\"}'", "tags": ["core", "read"]},
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
    return {"status": "ok", "service": "Mnemosyne OS", "version": "5.2.1"}

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
        total = await conn.fetchval("SELECT count(*) FROM memories WHERE user_id=$1 AND is_deleted=FALSE", user_id)
        chunked = await conn.fetchval("SELECT count(DISTINCT m.id) FROM memories m JOIN memory_chunks mc ON m.id=mc.memory_id WHERE m.user_id=$1 AND m.is_deleted=FALSE", user_id)
        total_chunks = await conn.fetchval("SELECT count(*) FROM memory_chunks mc JOIN memories m ON m.id=mc.memory_id WHERE m.user_id=$1 AND m.is_deleted=FALSE", user_id)
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
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE "
            "ORDER BY dist LIMIT $3",
            req.user_id, q_str, req.top_k
        )
        mem_rows = await conn.fetch(
            "SELECT id, content, embedding <=> $2::vector AS dist "
            "FROM memories WHERE user_id=$1 AND is_deleted=FALSE "
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
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8010, log_level="info")