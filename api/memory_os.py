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

async def _exact(q: str, limit: int = 10) -> List[dict]:
    """精确查：必须锚定首行，否则会命中「正文里提到过这个号」的卡。"""
    safe = q.replace("'", "''")
    sql = f"""
        SELECT id, category,
               NULLIF(split_part(split_part(content, '档号：', 2), chr(10), 1), '') AS no,
               left(content, 200) AS head
        FROM memories
        WHERE is_deleted = false
          AND (metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND (content LIKE '[结果卡] 档号：{safe}%'
               OR content LIKE '%{safe}%')
        ORDER BY (content LIKE '[结果卡] 档号：{safe}%') DESC, id DESC
        LIMIT {int(limit)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


async def _multi_kw(kws: List[str], limit: int = 60) -> List[dict]:
    """多关键词 OR + 按命中数降序（BM25 的穷人版）。"""
    kws = [k for k in (x.strip() for x in kws) if k]
    if not kws:
        return []
    safe = [k.replace("'", "''") for k in kws]
    hit_sum = " + ".join(f"(content ILIKE '%{k}%')::int" for k in safe)
    where = " OR ".join(f"content ILIKE '%{k}%'" for k in safe)
    sql = f"""
        SELECT id, category,
               NULLIF(split_part(split_part(content, '档号：', 2), chr(10), 1), '') AS no,
               left(content, 200) AS head,
               ({hit_sum}) AS kw_hit, {len(safe)} AS n_kw
        FROM memories
        WHERE is_deleted = false AND content LIKE '[结果卡]%'
          AND (metadata->>'dup_verdict') IS DISTINCT FROM 'same'
          AND ({where})
        ORDER BY kw_hit DESC, id DESC
        LIMIT {int(limit)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


async def _recent(days: int, kws: List[str], limit: int = 30) -> List[dict]:
    cond = f"AND created_at > now() - interval '{int(days)} days'"
    if kws:
        safe = [k.replace("'", "''") for k in kws]
        cond += " AND (" + " OR ".join(f"content ILIKE '%{k}%'" for k in safe) + ")"
    sql = f"""
        SELECT id, category,
               NULLIF(split_part(split_part(content, '档号：', 2), chr(10), 1), '') AS no,
               left(content, 200) AS head
        FROM memories
        WHERE is_deleted = false AND content LIKE '[结果卡]%'
          AND (metadata->>'dup_verdict') IS DISTINCT FROM 'same' {cond}
        ORDER BY created_at DESC LIMIT {int(limit)}
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(r) for r in rows]


# ---------- 端点 ----------

class RecallIn(BaseModel):
    query: str
    limit: int = 10
    days: int = 0


@router.post("/recall")
async def recall(body: RecallIn = Body(...)):
    """四通道召回（E 精确 / C 关键词 / T 时间 / S 语义）。

    返回的每条带 channels 字段说明它是被哪条路捞到的，交客户端裁决。
    """
    q = body.query.strip()
    if not q:
        return {"candidates": [], "error": "query 不能为空"}

    chans: dict[str, List[dict]] = {}

    for pat, _kind in EXACT_PATTERNS:
        if pat.match(q):
            chans["E"] = await _exact(q)
            break

    kws = keywords(q)
    kws_exp = expand_kw(kws)
    multi = await _multi_kw(kws_exp, limit=60) if kws_exp else []
    if multi:
        chans["C"] = multi

    if body.days or any(h in q for h in RECENT_HINTS):
        chans["T"] = await _recent(body.days or 7, kws_exp, limit=30)

    # 语义：走老接口的内部逻辑需要 embedding，这里交给调用方决定要不要叠加，
    # 避免在同一个请求里既查 SQL 又调 embedding 导致超时不可控。

    pool_map: dict[str, dict] = {}
    for ch, rows in chans.items():
        for r in rows:
            key = r.get("no") or f"id:{r['id']}"
            base = float(CREDIT[ch])
            if ch == "C" and r.get("n_kw"):
                # 覆盖率分母封顶 3：同义词展开后可能有 13 个词，
                # 用 13 做分母会让「只命中 1 个核心词」的卡被挤掉
                base = CREDIT[ch] * min(int(r.get("kw_hit") or 0), 3) / min(int(r["n_kw"]), 3)
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
    return {"query": q, "keywords": kws, "expanded": kws_exp,
            "channel_counts": {k: len(v) for k, v in chans.items()},
            "candidates": out[: body.limit]}


class ExactIn(BaseModel):
    q: str
    limit: int = 10


@router.post("/exact")
async def exact(body: ExactIn = Body(...)):
    """精确查档号/台账号/提交/路径。锚定首行优先。"""
    return {"query": body.q, "hits": await _exact(body.q, body.limit)}


class KwIn(BaseModel):
    keywords: List[str]
    limit: int = 60


@router.post("/keywords")
async def kw_search(body: KwIn = Body(...)):
    """多关键词 OR，按命中个数降序。"""
    rows = await _multi_kw(body.keywords, body.limit)
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
