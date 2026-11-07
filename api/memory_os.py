"""Memory OS 9.0 · 服务端 API（5 个新端点）

## 为什么要单独一个 router

老接口 `/api/v1/memories/*` 是 8.x 的语义检索，动它会牵一发动全身。
9.0 的能力（四通道召回 / 精确查档号 / 多词 BM25 / 两级跳 trace / 卡片体检）
物理隔离在 `/api/v1/memory-os/*`，将来演进互不拖累。

## 设计原则

1. **只取数，不做判断**：返回候选+分数+通道来源，谁裁决在客户端
2. **不引入新依赖**：复用 asyncpg pool + 现有的表
3. **每个端点都能用 curl 一行验**

## 为什么这些逻辑要搬到服务端

以前它们在我本地的 Python 脚本里（sandbox/mem9），本机一关机就全停。
主人 2026-11-03 指出：「本机会关机，主体功能肯定是跟着 Memory OS 走，
不是说还专门有了一个管家」。

挂载方式（main.py）：
    from api.memory_os import router as memory_os_router
    app.include_router(memory_os_router)
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/memory-os", tags=["memory-os"])

# 由 main.py 在启动时注入（避免循环 import）
pool: Optional[Any] = None

CARD_PREFIX = "[结果卡]"
CREDIT = {"E": 100, "C": 60, "T": 45, "S": 40}
RECENT_HINTS = ("上次", "最近", "刚才", "昨天", "前天", "上一回", "上一次")

# 与客户端 recall.py 保持一致的领域词典（后续可移到配置表）
DOMAIN_LEX = {
    "出图": ["出图", "生图", "配图", "seedream"],
    "小本本": ["小本本", "日记", "手账", "diary"],
    "召回": ["召回", "检索", "搜索", "命中", "recall"],
    "记忆": ["记忆", "mnemosyne", "宫殿", "memory", "结果卡", "memory os"],
    "台账": ["台账", "gcat-track", "任务卡"],
    "技能": ["技能", "skill"],
    "备份": ["备份", "backup", "dump"],
    "部署": ["部署", "上线", "deploy", "发布"],
    "向量": ["向量", "embedding", "向量化", "语义"],
    "卡片": ["卡片", "结果卡", "著录卡"],
    "凭据": ["凭据", "密钥", "泄露", "key", "密码"],
    "压缩": ["压缩", "太长", "上下文", "ctx", "context"],
    "状态机": ["状态机", "状态流转", "状态", "待启动", "开发中", "阻塞"],
}
STOP = ("哪个", "哪些", "什么", "怎么", "上次", "最近", "刚才", "多少", "如何",
        "为什么", "是不是", "这个", "那个", "一下", "可以", "我们", "你们")

EXACT_PATTERNS = [
    (re.compile(r"^K·[A-Z]+·\d{4}-\d{4}$"), "档号"),
    (re.compile(r"^T-\d{4}$"), "台账号"),
    (re.compile(r"^[0-9a-f]{7,40}$"), "提交"),
    (re.compile(r"^/[\w./-]{4,}$"), "路径"),
]


# ---------- 工具函数 ----------

def keywords(q: str, max_n: int = 8) -> List[str]:
    """口语查询 → 实义词。词典优先，双字滑窗补位。"""
    s = q
    hits: List[str] = []
    for canon, forms in DOMAIN_LEX.items():
        for f in forms:
            if f and f in q.lower():
                if f not in hits:
                    hits.append(f)
                if canon not in hits:
                    hits.append(canon)
                s = s.replace(f, " ")
                break
    for w in STOP:
        s = s.replace(w, " ")
    for ch in "的是了吗呢吧啊嗯哦在和与就都也还把被给对从向以为":
        s = s.replace(ch, " ")
    out: List[str] = []
    for part in s.split():
        part = part.strip("?？!！。，,、 ")
        if not part:
            continue
        if part.isascii() or len(part) <= 3:
            out.append(part)
        else:
            out += [part[i:i + 2] for i in range(0, len(part) - 1, 2)]
    merged, seen = [], set()
    for k in hits + out:
        if len(k) > 1 and k not in seen:
            seen.add(k)
            merged.append(k)
    return merged[:max_n]


def expand_kw(kws: List[str]) -> List[str]:
    out: List[str] = []
    for k in kws:
        for f in DOMAIN_LEX.get(k, [k]):
            if f and f not in out:
                out.append(f)
    return out


# ---------- 数据访问 ----------
# 判重口径（2026-11-03 T-0594）：被管家判定为「同一张卡的另一代」的卡
# （metadata.dup_verdict='same'）默认**不参与召回** —— 不是删，恢复只需改这个标记。
# 动机：K· 一代与 M· 一代存在 825 对同 sid 同题名重复，重复候选会挤占 top-k。

async def _exact(q: str, user_id: str = "default", limit: int = 10) -> List[dict]:
    """精确查：必须锚定首行，否则会命中「正文里提到过这个号」的卡。

    2026-11-07 修两处：①加 user_id 范围（原来跨用户，33k 条老板记忆会淹掉别人）；
    ②改参数化（原来把 query 拼进 f-string，只靠转义引号）。
    """
    sql = """
        SELECT m.id, m.category,
               NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
               left(m.content, 200) AS head
        FROM memories m
        WHERE m.user_id = $1
          AND m.is_deleted = false
          AND (m.metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND (m.content LIKE '[结果卡] 档号：' || $2 || '%'
               OR m.content LIKE '%' || $2 || '%')
        ORDER BY (m.content LIKE '[结果卡] 档号：' || $2 || '%') DESC, m.id DESC
        LIMIT $3
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, q, int(limit))
    return [dict(r) for r in rows]


async def _multi_kw(kws: List[str], user_id: str = "default", limit: int = 60) -> List[dict]:
    """多关键词 OR + 按命中数降序（BM25 的穷人版）。

    2026-11-07：加 user_id 范围；关键词走 unnest($2) 参数化，不再拼 f-string。
    """
    kws = [k for k in (x.strip() for x in kws) if k]
    if not kws:
        return []
    sql = """
        SELECT m.id, m.category,
               NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
               left(m.content, 200) AS head,
               (SELECT count(*) FROM unnest($2::text[]) AS t(kw)
                 WHERE m.content ILIKE '%' || t.kw || '%') AS kw_hit,
               array_length($2::text[], 1) AS n_kw
        FROM memories m
        WHERE m.user_id = $1
          AND m.is_deleted = false AND m.content LIKE '[结果卡]%'
          AND (m.metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND EXISTS (SELECT 1 FROM unnest($2::text[]) AS t(kw)
                       WHERE m.content ILIKE '%' || t.kw || '%')
        ORDER BY kw_hit DESC, m.id DESC
        LIMIT $3
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, kws, int(limit))
    return [dict(r) for r in rows]


async def _recent(days: int, kws: List[str], user_id: str = "default", limit: int = 30) -> List[dict]:
    """时间通道：按天窗口 + 可选关键词。2026-11-07 加 user_id 范围与参数化。"""
    sql = """
        SELECT m.id, m.category,
               NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
               left(m.content, 200) AS head
        FROM memories m
        WHERE m.user_id = $1
          AND m.is_deleted = false AND m.content LIKE '[结果卡]%'
          AND (m.metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND m.created_at > now() - make_interval(days => $2)
          AND ($3::text[] IS NULL OR EXISTS (
                SELECT 1 FROM unnest($3::text[]) AS t(kw)
                 WHERE m.content ILIKE '%' || t.kw || '%'))
        ORDER BY m.created_at DESC LIMIT $4
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, int(days), kws or None, int(limit))
    return [dict(r) for r in rows]


def _should_abstain(ranked: List[dict], threshold: float) -> bool:
    """弃权判据：最高分低于阈值就返回空（threshold<=0 表示关闭）。

    ⚠️ 实测（2026-11-07，16 题）：**分数阈值不足以做弃权判据** ——
    正样本最低 16.2 低于负样本 20.0，任何阈值都会误伤。参数先留着，
    等找到更有区分度的信号（关键词覆盖度 / 问题类型 vs 卡片结构）再定默认值。
    """
    if threshold <= 0 or not ranked:
        return False
    raw = ranked[0].get("score")
    if raw is None:
        return False          # 分数缺失 = 判不了，宁可不弃权也别误吞结果
    try:
        return float(raw) < float(threshold)
    except (TypeError, ValueError):
        return False


async def _semantic(q: str, user_id: str = "default", limit: int = 30,
                    sim_floor: float = 0.45) -> List[dict]:
    """语义通道（S）：2026-11-07 新增。

    之前 recall 端点**根本不做语义**（注释说"交给调用方叠加"），文档却写着「四通道」——
    实测后果：只在语义上相近的问题（"周报怎么写"），E/C/T 三条全空，答案永远出不来。
    """
    import core.embedding as _emb

    try:
        vec = await _emb.get_embedding_async([q])
        vec = vec[0]
        if isinstance(vec, tuple):
            vec = vec[2]
    except Exception:
        return []          # 语义路失败不致命：其余通道照常返回
    vs = "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"
    # 相似度门槛（2026-11-07 实测加）：不设门槛时，任何问题都会捞回一堆「勉强相关」的卡，
    # 把正确答案挤出 top-k，还会让负样本（库里根本没有的题）也冒出禁词。
    sql = """
        SELECT m.id, m.category,
               NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
               left(m.content, 200) AS head,
               (1 - (m.embedding <=> $2::vector))::float AS sim
        FROM memories m
        WHERE m.user_id = $1
          AND m.is_deleted = false AND m.embedding IS NOT NULL
          AND (m.metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND (1 - (m.embedding <=> $2::vector)) >= $4
        ORDER BY m.embedding <=> $2::vector
        LIMIT $3
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, vs, int(limit), float(sim_floor))
    return [dict(r) for r in rows]


# ---------- 端点 ----------

class RecallIn(BaseModel):
    query: str
    user_id: str = "default"     # 2026-11-07：多 Agent 口子——召回必须限定在自己的记忆里
    limit: int = 10
    k: int | None = None         # 兼容：客户端传 k 等价于 limit（以前传 k 会被静默忽略，只回 10 条）
    days: int = 0
    semantic: bool = True        # 2026-11-07 实测：配 sim_floor=0.40 时 94% vs 只有字面通道 88%
    sim_floor: float = 0.40      # 语义相似度下限。无门槛=81%（近似项挤掉正确答案），0.40=94%
    abstain_below: float = 0.0   # 弃权阈值：最高分低于它就直接说「没找到」，别硬凑（0=关闭）


@router.post("/recall")
async def recall(body: RecallIn = Body(...)):
    """四通道召回（E 精确 / C 关键词 / T 时间 / S 语义）。

    返回的每条带 channels 字段说明它是被哪条路捞到的，交客户端裁决。
    """
    q = body.query.strip()
    if not q:
        return {"candidates": [], "error": "query 不能为空"}

    chans: dict[str, List[dict]] = {}
    uid = body.user_id or "default"
    limit = max(1, int(body.k if body.k is not None else body.limit))

    for pat, _kind in EXACT_PATTERNS:
        if pat.match(q):
            chans["E"] = await _exact(q, uid, limit)
            break

    kws = keywords(q)
    kws_exp = expand_kw(kws)
    multi = await _multi_kw(kws_exp, uid, limit=60) if kws_exp else []
    if multi:
        chans["C"] = multi

    if body.days or any(h in q for h in RECENT_HINTS):
        chans["T"] = await _recent(body.days or 7, kws_exp, uid, limit=30)

    # 语义通道（2026-11-07 接上）：只有它能在「字面不重合」的提问上找到卡。
    if body.semantic:
        sem = await _semantic(q, uid, limit=max(limit, 30), sim_floor=body.sim_floor)
        if sem:
            chans["S"] = sem

    pool_map: dict[str, dict] = {}
    for ch, rows in chans.items():
        for r in rows:
            key = r.get("no") or f"id:{r['id']}"
            base = float(CREDIT[ch])
            if ch == "C" and r.get("n_kw"):
                # 覆盖率分母封顶 3：同义词展开后可能有 13 个词，
                # 用 13 做分母会让「只命中 1 个核心词」的卡被挤掉
                base = CREDIT[ch] * min(int(r.get("kw_hit") or 0), 3) / min(int(r["n_kw"]), 3)
            if ch == "S":
                # 语义分按相似度折算：sim=0.9 → 0.9*40，避免任何一条都拿满分
                base = float(CREDIT[ch]) * max(0.0, min(1.0, float(r.get("sim") or 0.0)))
            if not (r.get("no") or "").strip():
                base *= 0.75      # 老格式卡（无档号）轻微降权
            if key in pool_map:
                pool_map[key]["channels"] = pool_map[key]["channels"] + ch
                pool_map[key]["score"] += base
            else:
                pool_map[key] = {"id": str(r["id"]), "no": r.get("no") or "",
                                 "head": r.get("head") or "",
                                 "channels": ch, "score": base}

    out = sorted(pool_map.values(),
                 key=lambda x: (-x["score"],
                                0 if str(x.get("head") or "").startswith(CARD_PREFIX) else 1,
                                str(x.get("id") or "")))
    # 弃权（2026-11-07）：以前无论多不相干都硬返 top-k，负样本必然被污染。
    if _should_abstain(out, body.abstain_below):
        return {"query": q, "user_id": uid, "keywords": kws, "expanded": kws_exp,
                "channel_counts": {k: len(v) for k, v in chans.items()},
                "candidates": [], "abstained": True,
                "abstain_reason": f"最高分 {float(out[0].get('score') or 0):.1f} < 阈值 {body.abstain_below:.1f}",
                "suppressed": len(out)}

    return {"query": q, "user_id": uid, "keywords": kws, "expanded": kws_exp,
            "channel_counts": {k: len(v) for k, v in chans.items()},
            "candidates": out[:limit]}


class ExactIn(BaseModel):
    q: str
    user_id: str = "default"
    limit: int = 10


@router.post("/exact")
async def exact(body: ExactIn = Body(...)):
    """精确查档号/台账号/提交/路径。锚定首行优先。"""
    return {"query": body.q, "user_id": body.user_id,
            "hits": await _exact(body.q, body.user_id, body.limit)}


class KwIn(BaseModel):
    keywords: List[str]
    user_id: str = "default"
    limit: int = 60


@router.post("/keywords")
async def kw_search(body: KwIn = Body(...)):
    """多关键词 OR，按命中个数降序。"""
    rows = await _multi_kw(body.keywords, body.user_id, body.limit)
    return {"keywords": body.keywords, "count": len(rows), "hits": rows}


@router.get("/trace/{archive_no}")
async def trace(archive_no: str):
    """两级跳：档号 → 卡片 → sid 指针 → 会话原文。

    这是 9.0 最有价值的取证能力：向量查不到的东西，顺着档号永远找得回来。
    """
    rows = await _exact(archive_no, limit=1)
    if not rows:
        return {"archive_no": archive_no, "error": "档号不存在"}
    card = rows[0]

    async with pool.acquire() as conn:
        full = await conn.fetchrow(
            "SELECT content, session_id, created_at FROM memories WHERE id = $1",
            int(card["id"]))
    content = full["content"] if full else ""
    m = re.search(r"sid=([\w-]+)", content)
    sid = m.group(1) if m else (str(full["session_id"]) if full and full["session_id"] else None)

    return {
        "archive_no": archive_no,
        "card": {"id": str(card["id"]), "head": card.get("head") or ""},
        "content": content,
        "sid": sid,
        "hint": "用 sid 到 state.db 的 messages 表按 session_id 查原文",
    }


@router.get("/stats")
async def stats():
    """卡片库体检：档号数/实体率/向量覆盖/老格式残留。"""
    sql = """
        SELECT
          count(*)                                                       AS total_cards,
          count(*) FILTER (WHERE content LIKE '[结果卡] 档号：K·%')        AS with_archive_no,
          count(*) FILTER (WHERE content LIKE '%实体：%')                 AS with_entities,
          count(*) FILTER (WHERE content NOT LIKE '[结果卡] 档号：K·%')    AS legacy_cards,
          count(embedding)                                               AS with_vector,
          round(avg(length(content))::numeric, 0)                        AS avg_len
        FROM memories
        WHERE is_deleted = false AND content LIKE '[结果卡]%'
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql)
        total = await conn.fetchval("SELECT count(*) FROM memories WHERE is_deleted = false")
    d = dict(row) if row else {}
    d["all_memories"] = total
    return d




@router.get("/diary")
async def diary(limit: int = 400):
    """小本本：每日日记 + 心里话 + 情感卡。

    三类分开查，因为它们的 created_at 分布差很远：
    日记是今天批量导入的、情感卡是昨晚生成的 —— 混在一起 order by created_at
    再 limit，情感卡会被日记挤掉（实测 feel_cards 永远 0）。
    """
    q_diary = """
        SELECT content FROM memories
        WHERE is_deleted = false AND content LIKE '[每日日记]%'
        ORDER BY content DESC
        LIMIT $1
    """
    q_feel = """
        SELECT content FROM memories
        WHERE is_deleted = false AND content LIKE '[情感卡]%'
        ORDER BY id DESC LIMIT $1
    """
    q_note = """
        SELECT content FROM memories
        WHERE is_deleted = false AND content LIKE '[心里话]%'
        ORDER BY id DESC LIMIT $1
    """
    async with pool.acquire() as conn:
        drows = await conn.fetch(q_diary, int(limit))
        frows = await conn.fetch(q_feel, 100)
        nrows = await conn.fetch(q_note, int(limit))

    diary, notes, feels = [], [], []
    for r in drows:
        c = r["content"] or ""
        head, _, body = c.partition("\n")
        m = re.search(r"日期[：:]\s*(\d{4}-\d{2}-\d{2})", head)
        text = "\n".join(l for l in body.splitlines() if not l.startswith("来源：")).strip()
        diary.append({"date": m.group(1) if m else "", "text": text})

    for r in frows:
        c = r["content"] or ""
        head, _, body = c.partition("\n")
        feels.append({"title": head.replace("[情感卡]", "").strip(),
                      "body": "\n".join(l for l in body.splitlines()
                                         if not l.startswith(("证据日期：", "来源："))).strip()})

    for r in nrows:
        c = r["content"] or ""
        head, _, body = c.partition("\n")
        txt = body.strip() or head.replace("[心里话]", "").strip()
        if txt:
            notes.append({"text": txt})

    diary.sort(key=lambda x: x["date"], reverse=True)
    return {"diary": diary, "notes": notes, "feel": feels,
            "counts": {"diary_days": len({d["date"] for d in diary if d["date"]}),
                       "feel_cards": len(feels), "notes": len(notes)}}


@router.get("/health")
async def health():
    """本 router 的连通性自检（不依赖数据库）。"""
    return {"status": "ok", "router": "memory-os", "endpoints": 5}
