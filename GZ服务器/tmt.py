"""
Mnemosyne TMT Module — 5级时间记忆树 (TiMem 架构)
基于 arXiv 2601.02845

依赖: main.py 中的 pool, CONFIG, get_embedding
"""

import json
import asyncio
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/tmt", tags=["tmt"])

# ── 从 main 注入的全局变量 ──
pool = None
embed_fn = None       # get_embedding
llm_url = None        # Qwen3.5-9B endpoint

# ── Pydantic Models ──
class ConsolidateRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    date: Optional[str] = None
    week_start: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None

class RecallRequest(BaseModel):
    user_id: str
    query: str
    complexity_hint: Optional[int] = None
    max_results: int = 20

# ── 层级表映射 ──
LEVEL_TABLES = {
    2: "tmt_sessions", 3: "tmt_daily", 4: "tmt_weekly", 5: "tmt_profiles"
}
LEVEL_CONTENT_COLS = {2: "summary", 3: "summary", 4: "summary", 5: "summary"}
WINDOW_SIZES = {2: 3, 3: 7, 4: 4, 5: 1}

# ── 层级提升指令 I_i ──
CONSOLIDATE_PROMPTS = {
    2: (
        "你是一个记忆摘要专家。分析以下对话记录，提取关键信息。\n"
        "输出 JSON:\n"
        "{{\n"
        "  \"summary\": \"一句话概括会话主题\",\n"
        "  \"key_facts\": [\"具体事实1\", \"事实2\"],\n"
        "  \"decisions\": [\"决定1\", \"决定2\"],\n"
        "  \"entities\": [\"提到的实体/人名/项目名\"],\n"
        "  \"importance\": 0.0-1.0\n"
        "}}\n"
        "注意：只提取确凿的事实，不要编造。\n\n"
        "本轮对话记录:\n{children}\n\n"
        "历史会话摘要(滑动窗口):\n{history}"
    ),
    3: (
        "你是一个每日记忆分析师。分析今天的多轮会话，提炼主题。\n"
        "输出 JSON:\n"
        "{{\n"
        "  \"summary\": \"今天的关键进展摘要\",\n"
        "  \"themes\": [\"主题1\", \"主题2\"],\n"
        "  \"key_changes\": [\"变化1\"],\n"
        "  \"importance\": 0.0-1.0\n"
        "}}\n\n"
        "今天的会话摘要:\n{children}\n\n"
        "近期每日摘要:\n{history}"
    ),
    4: (
        "Role: Weekly Pattern Analyst\n\nAnalyze daily reports for weekly trends.\nRules:\n1. Find recurring patterns across daily reports\n2. Compare with historical weeklies (ongoing vs emerging)\n3. Score importance 0.0-1.0 (frequency+impact+novelty)\n4. Data-driven only. Output valid JSON only.\n"
        "输出 JSON:\n"
        "{{\n"
        "  \"summary\": \"本周关键模式总结\",\n"
        "  \"patterns\": [\"模式1: 描述\", \"模式2: 描述\"],\n"
        "  \"emerging_trends\": [\"新兴趋势\"],\n"
        "  \"importance\": 0.0-1.0\n"
        "}}\n\n"
        "本周每日报告:\n{children}\n\n"
        "历史周报:\n{history}"
    ),
    5: (
        "Role: User Profile Analyst\n\nIncrementally update user profile from monthly observations.\nRules:\n1. Preserve stable traits unchanged from previous profile\n2. Detect and update changed preferences\n3. Add new patterns without removing existing ones\n4. Data-driven only. Output valid JSON only.\n"
        "保留稳定特征，更新已变化的偏好，添加新发现的模式。\n"
        "输出 JSON:\n"
        "{{\n"
        "  \"summary\": \"用户画像摘要\",\n"
        "  \"traits\": [\"性格/行为特征\"],\n"
        "  \"preferences\": [\"偏好\"],\n"
        "  \"knowledge_areas\": [\"知识领域\"],\n"
        "  \"communication_style\": \"沟通风格描述\",\n"
        "  \"importance\": 1.0\n"
        "}}\n\n"
        "上个月画像:\n{history}\n\n"
        "本月观察(周报+信念):\n{children}"
    )
}

# ── 工具函数 ──
async def call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """调用 LLM，带自动 fallback。
    
    优先: WSL Qwen3.5-4B (GPU, :11435) — 速度快
    保底: GZ Qwen3.5-2B (CPU, :11437) — WSL离线时自动切换
    """
    import httpx
    primary = llm_url or "http://127.0.0.1:11435/v1/chat/completions"
    fallback = "http://127.0.0.1:11437/v1/chat/completions"
    for attempt, url in enumerate([primary, fallback], 1):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={
                        "model": "default",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=120
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
                # reasoning模型可能把内容放reasoning_content
                if not text:
                    text = resp.json()["choices"][0]["message"].get("reasoning_content", "")
                return text
        except Exception as e:
            if attempt == 1:
                import logging
                logging.getLogger("tmt").warning(f"主LLM ({url}) 不可用，切换到保底: {e}")
                continue
            raise HTTPException(status_code=502, detail=f"LLM全部不可用: {e}")
    return ""

def parse_json_response(text: str) -> dict:
    text = text.strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    return json.loads(text)

async def gen_embedding(text: str) -> str:
    raw = (await embed_fn([text]))[0]
    return "[" + ",".join(str(x) for x in raw) + "]"

# ── 热度传播 ──
def compute_parent_heat(children_heats: list) -> float:
    if not children_heats:
        return 0.5
    max_h = max(children_heats)
    mean_h = sum(children_heats) / len(children_heats)
    variance = sum((h - mean_h)**2 for h in children_heats) / len(children_heats)
    agreement_bonus = max(0, 0.2 - variance * 2)
    return min(1.0, max(0.0, max_h * 0.6 + mean_h * 0.3 + agreement_bonus * 0.1))

# ── 核心蒸馏算法 ──
async def consolidate_level(user_id: str, level: int,
                            interval_start, interval_end) -> dict:
    async with pool.acquire() as conn:
        children = []
        child_ids = []
        child_texts = []

        if level == 2:
            rows = await conn.fetch(
                "SELECT id, content, created_at, heat_score FROM memories "
                "WHERE user_id=$1 AND created_at >= $2 AND created_at <= $3 "
                "AND is_deleted=FALSE ORDER BY created_at",
                user_id, interval_start, interval_end
            )
            children = [dict(r) for r in rows]
            child_id_ints = [c["id"] for c in children]  # int IDs for memories table
            child_texts = [f"[{c['created_at'].strftime('%H:%M')}] {c['content']}" for c in children]
        elif level == 3:
            rows = await conn.fetch(
                "SELECT id, summary, session_label, start_time, heat_score FROM tmt_sessions "
                "WHERE user_id=$1 AND start_time >= $2 AND start_time <= $3 ORDER BY start_time",
                user_id, interval_start, interval_end
            )
            children = [dict(r) for r in rows]
            child_id_uuids = [str(c["id"]) for c in children]
            child_texts = [f"[{c.get('session_label','')}] {c['summary']}" for c in children]
        elif level == 4:
            rows = await conn.fetch(
                "SELECT id, summary, date, heat_score FROM tmt_daily "
                "WHERE user_id=$1 AND date >= $2::date AND date <= $3::date ORDER BY date",
                user_id, interval_start, interval_end
            )
            children = [dict(r) for r in rows]
            child_id_uuids = [str(c["id"]) for c in children]
            child_texts = [f"[{c['date']}] {c['summary']}" for c in children]
        elif level == 5:
            rows = await conn.fetch(
                "SELECT id, summary, week_start, week_end, patterns, heat_score FROM tmt_weekly "
                "WHERE user_id=$1 AND week_start >= $2::date AND week_end <= $3::date ORDER BY week_start",
                user_id, interval_start, interval_end
            )
            children = [dict(r) for r in rows]
            child_id_uuids = [str(c["id"]) for c in children]
            child_texts = [f"[{c['week_start']}] {c['summary']}" for c in children]
            beliefs = await conn.fetch(
                "SELECT content, confidence FROM beliefs WHERE user_id=$1 AND status='established'",
                user_id
            )
            for b in beliefs:
                child_texts.append(f"[信念 置信度{b['confidence']:.1f}] {b['content']}")

        if not children:
            return {"skipped": True, "reason": "no_children"}

        w = WINDOW_SIZES.get(level, 3)
        table = LEVEL_TABLES[level]
        content_col = LEVEL_CONTENT_COLS[level]
        if level == 5:
            history_rows = await conn.fetch(
                f"SELECT {content_col} FROM {table} WHERE user_id=$1 "
                f"AND is_active=FALSE ORDER BY period_end DESC LIMIT {w}",
                user_id
            )
        elif level == 4:
            history_rows = await conn.fetch(
                f"SELECT {content_col} FROM {table} WHERE user_id=$1 "
                f"ORDER BY week_start DESC LIMIT {w}", user_id
            )
        elif level == 3:
            history_rows = await conn.fetch(
                f"SELECT {content_col} FROM {table} WHERE user_id=$1 "
                f"ORDER BY date DESC LIMIT {w}", user_id
            )
        else:
            history_rows = await conn.fetch(
                f"SELECT {content_col} FROM {table} WHERE user_id=$1 "
                f"ORDER BY created_at DESC LIMIT {w}", user_id
            )
        history_text = "\n".join(f"- {r[content_col][:300]}" for r in history_rows) or "(无历史)"

        prompt = CONSOLIDATE_PROMPTS[level].format(
            children="\n".join(child_texts),
            history=history_text
        )
        raw_result = await call_llm(prompt)
        parsed = parse_json_response(raw_result)

        vec_str = await gen_embedding(parsed.get("summary", ""))
        child_heats = [c.get("heat_score", 0.5) for c in children]
        heat = compute_parent_heat(child_heats)

        stored_id = None
        if level == 2:
            row = await conn.fetchrow(
                "INSERT INTO tmt_sessions (user_id, summary, embedding, heat_score, "
                "start_time, end_time, fragment_ids) VALUES ($1,$2,$3::vector,$4,$5,$6,$7) RETURNING id",
                user_id, parsed.get("summary", ""), vec_str, heat,
                interval_start, interval_end, child_id_ints
            )
            stored_id = row["id"]
            if child_id_ints:
                await conn.execute(
                    "UPDATE memories SET tmt_level=2, session_id=$1 "
                    "WHERE id = ANY($2::int[])",
                    str(stored_id), child_id_ints
                )
        elif level == 3:
            date_val = interval_start.date() if hasattr(interval_start, 'date') else interval_start
            row = await conn.fetchrow(
                "INSERT INTO tmt_daily (user_id, date, summary, embedding, heat_score, "
                "themes, session_ids) VALUES ($1,$2,$3,$4::vector,$5,$6,$7) "
                "ON CONFLICT (user_id, date) DO UPDATE SET summary=EXCLUDED.summary, "
                "embedding=EXCLUDED.embedding, themes=EXCLUDED.themes, updated_at=NOW() "
                "RETURNING id",
                user_id, date_val, parsed.get("summary", ""), vec_str, heat,
                json.dumps(parsed.get("themes", [])), child_id_uuids
            )
            stored_id = row["id"]
        elif level == 4:
            ws = interval_start.date() if hasattr(interval_start, 'date') else interval_start
            we = interval_end.date() if hasattr(interval_end, 'date') else interval_end
            row = await conn.fetchrow(
                "INSERT INTO tmt_weekly (user_id, week_start, week_end, summary, embedding, "
                "heat_score, patterns, daily_ids) VALUES ($1,$2,$3,$4::vector,$5,$6,$7,$8) RETURNING id",
                user_id, ws, we, parsed.get("summary", ""), vec_str,
                heat, json.dumps(parsed.get("patterns", [])), child_id_uuids
            )
            stored_id = row["id"]
        elif level == 5:
            await conn.execute(
                "UPDATE tmt_profiles SET is_active=FALSE WHERE user_id=$1 AND is_active=TRUE",
                user_id
            )
            prev = await conn.fetchrow(
                "SELECT id FROM tmt_profiles WHERE user_id=$1 ORDER BY period_end DESC LIMIT 1",
                user_id
            )
            prev_id = prev["id"] if prev else None
            profile_data = {
                "traits": parsed.get("traits", []),
                "preferences": parsed.get("preferences", []),
                "knowledge_areas": parsed.get("knowledge_areas", []),
                "communication_style": parsed.get("communication_style", ""),
            }
            row = await conn.fetchrow(
                "INSERT INTO tmt_profiles (user_id, period_start, period_end, profile_json, "
                "summary, embedding, heat_score, previous_id, weekly_ids) "
                "VALUES ($1,$2,$3,$4,$5,$6::vector,$7,$8,$9) RETURNING id",
                user_id, interval_start, interval_end,
                json.dumps(profile_data), parsed.get("summary", ""), vec_str,
                heat, prev_id, child_id_uuids
            )
            stored_id = row["id"]

        if child_id_ints and stored_id:
            for cid in child_id_ints:
                await conn.execute(
                    "INSERT INTO tmt_tree_edges (user_id, parent_level, parent_id, child_level, child_id) "
                    "VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
                    user_id, level, str(stored_id), level - 1, str(cid)
                )

        return {
            "level": level,
            "id": str(stored_id),
            "summary": parsed.get("summary", "")[:200],
            "heat_score": heat,
            "child_count": len(children)
        }

# ── API 端点 ──

@router.post("/consolidate/session")
async def tmt_consolidate_session(req: ConsolidateRequest):
    if req.session_id:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT MIN(created_at) AS start, MAX(created_at) AS end "
                "FROM memories WHERE session_id=$1 AND user_id=$2",
                req.session_id, req.user_id
            )
            if not rows or not rows[0]["start"]:
                return {"skipped": True, "reason": "no_memories"}
            start, end = rows[0]["start"], rows[0]["end"]
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT MIN(created_at) AS start, MAX(created_at) AS end "
                "FROM memories WHERE user_id=$1 AND tmt_level=1 "
                "AND created_at > NOW() - INTERVAL '30 minutes'",
                req.user_id
            )
            if not rows or not rows[0]["start"]:
                return {"skipped": True, "reason": "no_recent_fragments"}
            start, end = rows[0]["start"], rows[0]["end"]
    return await consolidate_level(req.user_id, 2, start, end)

@router.post("/consolidate/daily")
async def tmt_consolidate_daily(req: ConsolidateRequest):
    target_date = (
        datetime.strptime(req.date, "%Y-%m-%d").date()
        if req.date else date.today()
    )
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    return await consolidate_level(req.user_id, 3, day_start, day_end)

@router.post("/consolidate/weekly")
async def tmt_consolidate_weekly(req: ConsolidateRequest):
    if req.week_start:
        ws = datetime.strptime(req.week_start, "%Y-%m-%d").date()
    else:
        today = date.today()
        ws = today - timedelta(days=today.weekday())
    we = ws + timedelta(days=6)
    ws_dt = datetime.combine(ws, datetime.min.time()).replace(tzinfo=timezone.utc)
    we_dt = datetime.combine(we, datetime.max.time()).replace(tzinfo=timezone.utc)
    return await consolidate_level(req.user_id, 4, ws_dt, we_dt)

@router.post("/consolidate/monthly")
async def tmt_consolidate_monthly(req: ConsolidateRequest):
    today = date.today()
    year = req.year or today.year
    month = req.month or today.month
    period_start = date(year, month, 1)
    if month == 12:
        period_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        period_end = date(year, month + 1, 1) - timedelta(days=1)
    ps_dt = datetime.combine(period_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    pe_dt = datetime.combine(period_end, datetime.max.time()).replace(tzinfo=timezone.utc)
    return await consolidate_level(req.user_id, 5, ps_dt, pe_dt)

@router.post("/recall")
async def tmt_recall(req: RecallRequest):
    complexity = req.complexity_hint
    if complexity is None:
        classify_prompt = (
            f"将以下查询按复杂度分为: 0=简单事实, 1=多事实综合, 2=推理/预测/个性化\n"
            f"查询: \"{req.query}\"\n输出 JSON: {{\"complexity\": 0|1|2, \"reasoning\": \"\"}}"
        )
        raw = await call_llm(classify_prompt, temperature=0.1, max_tokens=128)
        complexity = parse_json_response(raw).get("complexity", 1)

    vec_str = await gen_embedding(req.query)
    params = {
        0: {"k": {"1": 5, "5": 1}, "limit": 10},
        1: {"k": {"1": 10, "2": 5, "3": 5, "4": 3, "5": 1}, "limit": 20},
        2: {"k": {"1": 20, "2": 10, "3": 10, "4": 5, "5": 2}, "limit": 30},
    }.get(complexity, {})

    candidates = []
    async with pool.acquire() as conn:
        l1 = await conn.fetch(
            f"SELECT id, content, heat_score, created_at, 1 AS tmt_level, 'memories' AS src "
            f"FROM memories WHERE user_id=$1 AND tmt_level=1 AND is_deleted=FALSE "
            f"AND heat_score >= 0.1 "
            f"ORDER BY embedding <=> $2::vector LIMIT {params['limit']}",
            req.user_id, vec_str
        )
        candidates.extend(dict(r) for r in l1)

        if complexity >= 1:
            for level in [2, 3, 4]:
                table = LEVEL_TABLES[level]
                content_col = LEVEL_CONTENT_COLS[level]
                k = params["k"].get(str(level), 5)
                if table and k > 0:
                    rows = await conn.fetch(
                        f"SELECT id, {content_col} AS content, heat_score, created_at, "
                        f"{level} AS tmt_level, '{table}' AS src "
                        f"FROM {table} WHERE user_id=$1 AND heat_score >= 0.15 "
                        f"ORDER BY embedding <=> $2::vector LIMIT {k}",
                        req.user_id, vec_str
                    )
                    candidates.extend(dict(r) for r in rows)

            profile = await conn.fetchrow(
                "SELECT id, summary AS content, heat_score, created_at, "
                "5 AS tmt_level, 'tmt_profiles' AS src "
                "FROM tmt_profiles WHERE user_id=$1 AND is_active=TRUE LIMIT 1",
                req.user_id
            )
            if profile:
                candidates.append(dict(profile))

    seen = set()
    deduped = []
    for c in candidates:
        key = f"{c['tmt_level']}_{c['id']}"
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    now = datetime.now(timezone.utc)
    deduped.sort(key=lambda m: (
        m["tmt_level"],
        abs((now - m.get("created_at", now)).total_seconds())
    ))

    filtered = deduped
    if len(deduped) > 10:
        gate_prompt = (
            f"查询: \"{req.query}\"\n\n候选记忆:\n" +
            "\n".join(f"[{m['tmt_level']}] {m['content'][:200]}" for m in deduped[:20]) +
            "\n\n输出 JSON: {{\"keep_indices\": [相关索引的编号列表]}}"
        )
        raw = await call_llm(gate_prompt, temperature=0.1, max_tokens=256)
        keep = set(parse_json_response(raw).get("keep_indices", []))
        filtered = [m for i, m in enumerate(deduped[:20]) if i in keep] + deduped[20:]

    return {
        "complexity": complexity,
        "total": len(filtered),
        "memories": [
            {"level": m["tmt_level"], "content": m["content"],
             "heat": m.get("heat_score", 0.5), "src": m.get("src", "")}
            for m in filtered[:req.max_results]
        ]
    }

@router.post("/recall/simple")
async def tmt_recall_simple(user_id: str, q: str, top_k: int = 5):
    vec_str = await gen_embedding(q)
    async with pool.acquire() as conn:
        l1 = await conn.fetch(
            f"SELECT id, content, heat_score FROM memories "
            f"WHERE user_id=$1 AND tmt_level=1 AND is_deleted=FALSE AND heat_score>=0.1 "
            f"ORDER BY embedding <=> $2::vector LIMIT {top_k}",
            user_id, vec_str
        )
        profile = await conn.fetchrow(
            "SELECT summary FROM tmt_profiles WHERE user_id=$1 AND is_active=TRUE LIMIT 1",
            user_id
        )
    result = [{"level": 1, "content": r["content"]} for r in l1]
    if profile:
        result.insert(0, {"level": 5, "content": profile["summary"]})
    return {"memories": result}

@router.get("/tree/{user_id}")
async def tmt_tree(user_id: str):
    async with pool.acquire() as conn:
        stats = {}
        for level in [2, 3, 4, 5]:
            table = LEVEL_TABLES[level]
            row = await conn.fetchrow(
                f"SELECT COUNT(*) AS cnt, AVG(heat_score) AS avg_heat "
                f"FROM {table} WHERE user_id=$1", user_id
            )
            stats[f"L{level}"] = {
                "count": row["cnt"],
                "avg_heat": round(float(row["avg_heat"] or 0), 3)
            }
        l1 = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt, AVG(heat_score) AS avg_heat "
            "FROM memories WHERE user_id=$1 AND tmt_level=1 AND is_deleted=FALSE",
            user_id
        )
        stats["L1"] = {"count": l1["cnt"], "avg_heat": round(float(l1["avg_heat"] or 0), 3)}
        active = await conn.fetchrow(
            "SELECT summary FROM tmt_profiles WHERE user_id=$1 AND is_active=TRUE",
            user_id
        )
    return {"user_id": user_id, "levels": stats, "active_profile": active["summary"] if active else None}

@router.get("/level/{level}/{node_id}")
async def tmt_node_detail(level: int, node_id: str, user_id: str):
    table = LEVEL_TABLES.get(level)
    if not table:
        raise HTTPException(400, f"Invalid level: {level}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT * FROM {table} WHERE id=$1 AND user_id=$2", node_id, user_id)
        if not row:
            raise HTTPException(404, "Node not found")
        children = await conn.fetch(
            "SELECT e.child_level, e.child_id FROM tmt_tree_edges e "
            "WHERE e.parent_id=$1 AND e.parent_level=$2 AND e.user_id=$3",
            node_id, level, user_id
        )
    return {"node": dict(row), "children": [dict(c) for c in children]}

@router.post("/decay")
async def tmt_decay(user_id: str):
    async with pool.acquire() as conn:
        results = {}
        r = await conn.execute(
            "UPDATE memories SET heat_score=GREATEST(0.01, heat_score*0.98) "
            "WHERE user_id=$1 AND is_deleted=FALSE", user_id
        )
        results["L1"] = int(r.split()[-1])
        for level, rate in {2: 0.985, 3: 0.99, 4: 0.995, 5: 0.999}.items():
            table = LEVEL_TABLES[level]
            r = await conn.execute(
                f"UPDATE {table} SET heat_score=GREATEST(0.01, heat_score*{rate}) WHERE user_id=$1",
                user_id
            )
            results[f"L{level}"] = int(r.split()[-1])
    return {"decayed": results}

@router.post("/backfill")
async def tmt_backfill(user_id: str):
    results = {"L2": 0, "L3": 0, "L4": 0, "L5": 0}
    async with pool.acquire() as conn:
        orphan_frags = await conn.fetch(
            "SELECT MIN(created_at) AS start, MAX(created_at) AS end "
            "FROM memories WHERE user_id=$1 AND tmt_level=1 "
            "AND session_id IS NULL AND is_deleted=FALSE",
            user_id
        )
        if orphan_frags and orphan_frags[0]["start"]:
            try:
                r = await consolidate_level(user_id, 2,
                    orphan_frags[0]["start"], orphan_frags[0]["end"])
                if not r.get("skipped"):
                    results["L2"] = 1
            except: pass

        missing_dates = await conn.fetch(
            "SELECT DISTINCT DATE(m.created_at) AS d FROM memories m "
            "LEFT JOIN tmt_daily d ON DATE(m.created_at)=d.date AND d.user_id=m.user_id "
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE AND d.id IS NULL "
            "AND m.created_at > NOW() - INTERVAL '7 days'",
            user_id
        )
        for md_row in missing_dates:
            d = md_row["d"]
            ds = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
            de = datetime.combine(d, datetime.max.time()).replace(tzinfo=timezone.utc)
            try:
                r = await consolidate_level(user_id, 3, ds, de)
                if not r.get("skipped"):
                    results["L3"] += 1
            except: pass

    return {"backfilled": results}
