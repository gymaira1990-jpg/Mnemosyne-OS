"""
Mnemosyne v7.7.0 — 注入调度大厅 (Injection Scheduler)
注入 = 认知调度, 不是内容塞入。
场景(查询) × 价值(rank/热度/状态) → 动态决定「这一轮该看到什么」。
全部复用现有能力: 向量+BM25(wiki 模式) / memories hybrid 搜索 / heat-top。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/injection", tags=["injection"])

pool = None


class InjectionPlanRequest(BaseModel):
    user_id: str = "default"
    context: str = ""                      # 当前会话/任务场景描述
    limits: dict = {"skills": 3, "memories": 5, "hooks": 5}


@router.post("/plan")
async def injection_plan(req: InjectionPlanRequest):
    """按场景返回注入流: {skills, memories, hooks}
    通道: ①技能语义召唤(含沉寂, 可唤醒) ②记忆 hybrid 搜索 ③热点钩子
    任一通道失败 → 只返回成功通道 (静默降级, 不阻断)
    服务端硬校验: limits 超上限自动截断 (防打爆上下文窗口)"""
    result = {"session_token": "", "skills": [], "memories": [], "hooks": [], "meta": {}}
    # ── 服务端硬上限 (防恶意/错误超大 limit) ──
    HARD_CAPS = {"skills": 8, "memories": 10, "hooks": 10}
    limits = req.limits or {}
    try:
        caps = {k: max(1, min(int(limits.get(k, 3)), HARD_CAPS[k])) for k in HARD_CAPS}
    except Exception:
        caps = {"skills": 3, "memories": 5, "hooks": 5}
    # ── 空 context → 返回空注入流 (不浪费 embedding 调用) ──
    if not (req.context or "").strip():
        result["meta"] = {"latency_ms": 0, "channels": {"skills": 0, "memories": 0, "hooks": 0}, "note": "empty_context"}
        return result
    from core.embedding import get_embedding_async
    import time
    t0 = time.time()
    STATE_WEIGHT = {"active": 1.0, "stale": 0.85, "archived": 0.7}

    # ── ① 技能通道: 向量 + BM25 (对齐 wiki search 模式) ──
    skills_out = []
    try:
        r_q = (await get_embedding_async([req.context]))[0]
        q_str = "[" + ",".join(str(x) for x in r_q) + "]"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, skill_name, description, category, state, use_count,
                          embedding <=> $1::vector AS dist
                   FROM skill_assets
                   WHERE tenant_id = $2 AND embedding IS NOT NULL
                   ORDER BY embedding <=> $1::vector
                   LIMIT 30""",
                q_str, req.user_id
            )
            # BM25 补强 (租户隔离)
            bm25_scores = {}
            try:
                import jieba
                query_tokens = [t.strip() for t in jieba.cut(req.context) if len(t.strip()) >= 2]
                if query_tokens and rows:
                    kw_rows = await conn.fetch(
                        """SELECT sk.skill_id, sk.token, sk.freq,
                                  (SELECT count(DISTINCT skill_id) FROM skill_keywords sk2
                                   WHERE sk2.token = sk.token AND sk2.tenant_id = $2)
                                  AS skills_with_token
                           FROM skill_keywords sk
                           JOIN skill_assets sa ON sa.id = sk.skill_id
                           WHERE sk.token = ANY($1::text[]) AND sk.tenant_id = $2
                           ORDER BY sk.freq DESC
                           LIMIT 200""",
                        query_tokens, req.user_id
                    )
                    from wiki.wiki_bm25 import compute_bm25_scores
                    bm25_scores = compute_bm25_scores(
                        [{"page_id": r["skill_id"], "token": r["token"], "freq": r["freq"],
                          "pages_with_token": r["skills_with_token"]} for r in kw_rows],
                        query_tokens, len(rows) or 1
                    )
            except Exception:
                pass
            from wiki.wiki_bm25 import rrf_fuse
            fused = rrf_fuse([(r["id"], r["dist"]) for r in rows], bm25_scores) if rows else []
            id2row = {r["id"]: r for r in rows}
            scored = []
            for pid, rrf in fused:
                r = id2row.get(pid)
                if not r:
                    continue
                w = STATE_WEIGHT.get(r["state"], 1.0)
                scored.append((rrf * w, r))
            scored.sort(key=lambda x: -x[0])
            for _s, r in scored[:caps["skills"]]:
                skills_out.append({
                    "name": r["skill_name"],
                    "state": r["state"],
                    "score": round(1.0 / (1.0 + float(r["dist"])), 4),
                    "reason": "场景匹配",
                    "wakeable": r["state"] in ("stale", "archived"),
                    "hint": "输入【唤醒 %s】即加载" % r["skill_name"] if r["state"] in ("stale", "archived") else None,
                })
    except Exception:
        skills_out = []
    result["skills"] = skills_out

    # ── ② 记忆通道: 复用 memories hybrid 搜索 ──
    memories_out = []
    try:
        if req.context.strip():
            # 直接查库 (与 /memories/search 同逻辑的轻量路径)
            r_q2 = (await get_embedding_async([req.context]))[0]
            q_str2 = "[" + ",".join(str(x) for x in r_q2) + "]"
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT id, content, category, heat_score,
                              embedding <=> $1::vector AS dist
                       FROM memories
                       WHERE user_id = $2 AND is_deleted = FALSE
                         AND (valid_to IS NULL OR valid_to > NOW())
                         AND embedding IS NOT NULL
                       ORDER BY embedding <=> $1::vector
                       LIMIT $3""",
                    q_str2, req.user_id, caps["memories"]
                )
                for r in rows:
                    memories_out.append({
                        "id": r["id"],
                        "category": r["category"],
                        "heat": round(float(r["heat_score"] or 0), 2),
                        "score": round(1.0 / (1.0 + float(r["dist"])), 4),
                        "preview": (r["content"] or "")[:120],
                    })
    except Exception:
        memories_out = []
    result["memories"] = memories_out

    # ── ③ 热点钩子通道: 复用 heat-top + 时间衰减 ──
    hooks_out = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, content, category, heat_score
                   FROM memories
                   WHERE user_id=$1 AND is_deleted=FALSE
                     AND (valid_to IS NULL OR valid_to > NOW())
                     AND heat_score >= 0.3
                   ORDER BY heat_score DESC LIMIT $2""",
                req.user_id, caps["hooks"]
            )
            for r in rows:
                hooks_out.append({
                    "id": r["id"],
                    "category": r["category"],
                    "heat": round(float(r["heat_score"] or 0), 2),
                    "summary": (r["content"] or "")[:30],
                })
    except Exception:
        hooks_out = []
    result["hooks"] = hooks_out

    import uuid
    result["session_token"] = "inj_" + uuid.uuid4().hex[:12]
    result["meta"] = {
        "latency_ms": round((time.time() - t0) * 1000),
        "channels": {
            "skills": len(skills_out),
            "memories": len(memories_out),
            "hooks": len(hooks_out),
        },
    }
    return result
