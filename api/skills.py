"""
Mnemosyne v7.7.0 — 程序性记忆翼 (技能资产 API)
技能 = 可执行记忆, 与陈述性记忆并列, 共享分层/热度/召唤体系, 自有状态机(对齐 curator)
状态: active / stale / archived — 永不 DELETE, 只流转
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

pool = None


class SkillItem(BaseModel):
    skill_name: str
    description: str = ""
    category: str = ""
    state: str = "active"
    pinned: bool = False
    source_path: str = ""
    use_count: int = 0
    view_count: int = 0
    last_used_at: Optional[str] = None
    last_viewed_at: Optional[str] = None
    archived_at: Optional[str] = None


class SkillSyncRequest(BaseModel):
    skills: List[SkillItem]
    tenant_id: str = "default"


class SkillSearchRequest(BaseModel):
    query: str
    user_id: str = "default"
    top_k: int = 5
    include_archived: bool = True


@router.post("/sync")
async def sync_skills(req: SkillSyncRequest):
    """批量同步技能资产 (幂等 upsert, skill_sync.py 调用)
    描述非空 → 计算 embedding; 描述为空 → 用 skill_name+category 兜底计算 (防失联)
    单条 embedding 失败 → 该条跳过(保留已有), 不影响成功条目"""
    if not req.skills:
        return {"synced": 0, "updated": 0, "new": 0}
    from core.embedding import get_embedding_async
    # 批量算 embedding: 描述优先, 空描述用 name+category 兜底
    desc_map = {}
    for s in req.skills:
        text = s.description.strip() if s.description.strip() else f"{s.skill_name} {s.category}"
        desc_map[s.skill_name] = text
    vecs = {}
    if desc_map:
        try:
            texts = list(desc_map.values())
            raw = await get_embedding_async(texts)
            for name, vec in zip(desc_map.keys(), raw):
                vecs[name] = "[" + ",".join(str(x) for x in vec) + "]"
        except Exception:
            vecs = {}
    updated = new = 0
    failed = []
    from datetime import datetime, timezone

    def _dt(v):
        """ISO 字符串 → datetime (容错)"""
        if not v:
            return None
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except Exception:
            return None

    async with pool.acquire() as conn:
        for s in req.skills:
            if s.state not in ("active", "stale", "archived"):
                continue
            vec_str = vecs.get(s.skill_name)
            try:
                row = await conn.fetchrow(
                    """INSERT INTO skill_assets
                       (skill_name, description, category, state, pinned, source_path,
                        use_count, view_count, last_used_at, last_viewed_at, archived_at,
                        tenant_id, embedding)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                               CASE WHEN $13::text IS NOT NULL THEN $13::vector ELSE NULL END)
                       ON CONFLICT (tenant_id, skill_name) DO UPDATE SET
                         description=EXCLUDED.description,
                         category=EXCLUDED.category,
                         state=EXCLUDED.state,
                         pinned=EXCLUDED.pinned,
                         source_path=EXCLUDED.source_path,
                         use_count=EXCLUDED.use_count,
                         view_count=EXCLUDED.view_count,
                         last_used_at=EXCLUDED.last_used_at,
                         last_viewed_at=EXCLUDED.last_viewed_at,
                         archived_at=EXCLUDED.archived_at,
                         embedding=COALESCE(EXCLUDED.embedding, skill_assets.embedding),
                         updated_at=NOW()
                       RETURNING id, (xmax = 0) AS inserted""",
                    s.skill_name, s.description, s.category, s.state, s.pinned,
                    s.source_path, s.use_count, s.view_count,
                    _dt(s.last_used_at), _dt(s.last_viewed_at), _dt(s.archived_at),
                    req.tenant_id, vec_str
                )
                if row["inserted"]:
                    new += 1
                else:
                    updated += 1
            except Exception as e:
                failed.append({"skill_name": s.skill_name, "error": str(e)[:200]})
    return {"synced": len(req.skills), "updated": updated, "new": new,
            "embedded": len(vecs), "failed": failed}


@router.post("/search")
async def search_skills(req: SkillSearchRequest):
    """语义召唤技能 (含沉寂/归档): 向量 + BM25 双通道 RRF 融合 + 状态权重
    对齐 wiki search 模式: 向量候选池 → BM25 补强 → 状态标注
    状态权重: active×1.0 / stale×0.85 / archived×0.7 (沉寂可唤醒, 活跃优先)"""
    from core.embedding import get_embedding_async

    STATE_WEIGHT = {"active": 1.0, "stale": 0.85, "archived": 0.7}
    # 向量通道
    r_q = (await get_embedding_async([req.query]))[0]
    q_str = "[" + ",".join(str(x) for x in r_q) + "]"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, skill_name, description, category, state, pinned, use_count,
                      embedding <=> $1::vector AS dist
               FROM skill_assets
               WHERE tenant_id = $2 AND embedding IS NOT NULL
                 AND ($3::bool OR state != 'archived')
               ORDER BY embedding <=> $1::vector
               LIMIT 50""",
            q_str, req.user_id, req.include_archived
        )
        vec_ranked = [(r["id"], r["dist"]) for r in rows]

        # BM25 通道 (jieba 分词, 租户隔离)
        bm25_scores = {}
        try:
            import jieba
            query_tokens = [t.strip() for t in jieba.cut(req.query) if len(t.strip()) >= 2]
            if query_tokens and rows:
                kw_rows = await conn.fetch(
                    """SELECT sk.skill_id, sk.token, sk.freq,
                              (SELECT count(DISTINCT skill_id) FROM skill_keywords sk2
                               WHERE sk2.token = sk.token AND sk2.tenant_id = $2)
                              AS skills_with_token
                       FROM skill_keywords sk
                       JOIN skill_assets sa ON sa.id = sk.skill_id
                       WHERE sk.token = ANY($1::text[])
                         AND sk.tenant_id = $2
                       ORDER BY sk.freq DESC
                       LIMIT 200""",
                    query_tokens, req.user_id
                )
                from wiki.wiki_bm25 import compute_bm25_scores
                total = len(rows)
                bm25_scores = compute_bm25_scores(
                    [{"page_id": r["skill_id"], "token": r["token"], "freq": r["freq"],
                      "pages_with_token": r["skills_with_token"]} for r in kw_rows],
                    query_tokens, total or 1
                )
        except Exception:
            bm25_scores = {}

        # RRF 融合 + 状态权重
        from wiki.wiki_bm25 import rrf_fuse
        fused = rrf_fuse(vec_ranked, bm25_scores) if (bm25_scores or vec_ranked) else []
        id2row = {r["id"]: r for r in rows}
        scored = []
        for pid, rrf in fused:
            r = id2row.get(pid)
            if not r:
                continue
            w = STATE_WEIGHT.get(r["state"], 1.0)
            scored.append((rrf * w, r))
        scored.sort(key=lambda x: -x[0])
        matches = []
        for _rrf, r in scored[:req.top_k]:
            matches.append({
                "skill_name": r["skill_name"],
                "description": (r["description"] or "")[:200],
                "category": r["category"],
                "state": r["state"],
                "pinned": r["pinned"],
                "use_count": r["use_count"],
                "score": round(1.0 / (1.0 + float(r["dist"])), 4),
                "wakeable": r["state"] in ("stale", "archived"),
                "hint": "输入【唤醒 %s】即加载" % r["skill_name"] if r["state"] in ("stale", "archived") else None,
            })
        return {"matches": matches}


@router.patch("/{skill_name}")
async def update_skill_state(skill_name: str, body: dict):
    """状态流转 (唤醒/降级): body={"state": "active", "reason": "..."}"""
    state = (body or {}).get("state", "")
    if state not in ("active", "stale", "archived"):
        raise HTTPException(400, "无效状态: " + str(state))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE skill_assets SET state=$1, updated_at=NOW(),
                      archived_at = CASE WHEN $1='archived' THEN NOW() ELSE archived_at END
               WHERE skill_name=$2 RETURNING skill_name, state, source_path""",
            state, skill_name
        )
        if not row:
            raise HTTPException(404, "技能不存在: " + skill_name)
        return {"skill_name": row["skill_name"], "state": row["state"],
                "source_path": row["source_path"]}


@router.post("/{skill_name}/touch")
async def touch_skill(skill_name: str):
    """使用回馈: 召唤命中/加载时调用, 使用即升温"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """UPDATE skill_assets
               SET use_count = use_count + 1, last_used_at = NOW(), updated_at = NOW()
               WHERE skill_name=$1
               RETURNING skill_name, state, use_count""",
            skill_name
        )
        if not row:
            raise HTTPException(404, "技能不存在: " + skill_name)
        return {"skill_name": row["skill_name"], "state": row["state"],
                "use_count": row["use_count"]}
