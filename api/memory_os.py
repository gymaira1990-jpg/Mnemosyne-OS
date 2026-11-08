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

import json
import math
import re
from typing import Any, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
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
        if part.isascii() or len(part) <= 2:
            # 2026-11-08：阈值 3 → 2。3 字段原来整段保留，于是「分级按」这种
            # 停用词残留段会被当成一个关键词去库里做子串匹配 —— 纯噪音，还占候选名额。
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


def _kw_weight(k: str) -> float:
    """关键词的「辨识度」权重（2026-11-08）。

    为什么不用 IDF：① 候选池本身就是按「命中任一词」筛出来的，池内 df 分布被压缩，
    稀有词算不出稀有（实测 recall 72% → 67%，反效果）；② 全库 df 在请求路径上算不起 ——
    中文 ILIKE 走不了索引（pg_trgm 对 <3 字符无效），8 个词就是 8 次全表扫描，实测 800ms+。

    静态权重是能解释的近似：
      · ascii / 含数字 / 路径 / 档号 → 3.0（专名，最 specific：TMT / 2438 / K·ABC·2026-0123）
      · 中文 ≥3 字                  → 2.0
      · 中文 2 字（多为常用词）      → 1.0
    """
    if not k:
        return 1.0
    if k.isascii() or any(c.isdigit() for c in k):
        return 3.0
    if len(k) >= 3:
        return 2.0
    return 1.0


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


_PG_RE_SPECIAL = set(r".^$*+?()[]{}|\\-")


def _kw_regex(kws: List[str]) -> str:
    """把关键词数组编成一条 PG 正则的 alternation —— **一次全表扫描**代替 N 次 ILIKE。

    为什么必须这么绕（2026-11-08 实测）：`content ILIKE '%kw%'` 在这套中文语料上
    **走不了索引**（pg_trgm 对少于 3 个字符的 pattern 无效，中文两字词全部中招），
    8 个关键词就是 8 次全表扫描。同一组词实测：
        4 次 ILIKE = 807ms ／ 一条等价正则 = 220ms（快 3.7 倍，结果集完全相同 911 条）。
    """
    parts = []
    for k in kws:
        if not k:
            continue
        parts.append("".join(("\\" + c) if c in _PG_RE_SPECIAL else c for c in k))
    return "|".join(parts)


async def _multi_kw(kws: List[str], user_id: str = "default", limit: int = 5000) -> List[dict]:
    """多关键词 OR 候选池（BM25 的穷人版）。

    2026-11-07：加 user_id 范围；关键词走 unnest($2) 参数化，不再拼 f-string。
    2026-11-08：改「一次正则粗筛 + 候选行内算命中词」，**不再按 kw_hit 截断窗口**。
      旧实现按 `kw_hit DESC` 取前 60/300 —— 命中泛词多的卡先把窗口占满，
      命中稀有锚点的正确记忆根本进不来（实测「TMT 的 L3 表缺哪个字段」永远搜不到）。
      现在全量返回候选，真正的排序交给调用方按 IDF 做。
    """
    kws = [k for k in (x.strip() for x in kws) if k]
    if not kws:
        return []
    pattern = _kw_regex(kws)
    sql = """
        WITH cand AS (
            SELECT m.id, m.category, m.content,
                   NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
                   (m.content LIKE '[结果卡]%') AS is_card
            FROM memories m
            WHERE m.user_id = $1
              AND m.is_deleted = false
              -- 🔴 2026-11-08 审计：原来这里写死 `content LIKE '[结果卡]%'`，
              --   而库里 33,165 条未删除记忆中只有 3,622 条（11%）是这个形态 ⇒
              --   **89% 的记忆在关键词通道里彻底搜不到**（含全部 4,375 条蒸馏知识）。
              AND (m.metadata->>'dup_verdict') IS DISTINCT FROM 'same'
              -- 一次正则扫描拿候选；只对候选行逐词算命中（成本从 全表×N 降到 候选×N）
              AND m.content ~* $2
            LIMIT $4
        )
        SELECT c.id, c.category, c.no, left(c.content, 200) AS head, c.is_card,
               (SELECT array_agg(t.kw ORDER BY t.kw) FROM unnest($3::text[]) AS t(kw)
                 WHERE c.content ILIKE '%' || t.kw || '%') AS hit_kws,
               array_length($3::text[], 1) AS n_kw
        FROM cand c
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, user_id, pattern, kws, int(limit))
    return [dict(r) for r in rows]


async def _recent(days: int, kws: List[str], user_id: str = "default", limit: int = 30) -> List[dict]:
    """时间通道：按天窗口 + 可选关键词。2026-11-07 加 user_id 范围与参数化。"""
    sql = """
        SELECT m.id, m.category,
               NULLIF(split_part(split_part(m.content, '档号：', 2), chr(10), 1), '') AS no,
               left(m.content, 200) AS head
        FROM memories m
        WHERE m.user_id = $1
          AND m.is_deleted = false
          -- 同 _multi_kw：不再只认结果卡形态（否则时间通道同样漏掉 89% 的记忆）。
          -- 时间通道的排序本来就是「最近优先」，卡片不加特权也合理。
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


def _needs_confirmation(ranked: List[dict], margin: float) -> bool:
    """求证判据：**拿不准就问**，而不是硬给一个答案（margin<=0 表示关闭）。

    两种「拿不准」（2026-11-07 主人定：召回不可能 100%，宁可多给候选让人裁）：
      1. 并列：top1 与 top2 分数差 < margin —— 两条都像，选谁都是猜；
      2. 单条微弱：只有 1 条候选且分数低（< margin），孤证不立。
    分数高且明显领先时不打扰人。
    """
    if margin <= 0 or not ranked:
        return False
    raw = ranked[0].get("score")
    if raw is None:
        return False          # 分数缺失 = 判不了，别拿缺数据去打扰人
    try:
        top = float(raw)
    except (TypeError, ValueError):
        return False
    if len(ranked) == 1:
        return top < float(margin)
    try:
        second = float(ranked[1].get("score") or 0)
    except (TypeError, ValueError):
        return False
    return (top - second) < float(margin)


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
    abstain_below: float = 0.0   # 弃权阈值：最高分低于它就直接说「没找到」（0=关闭；分数阈值已证否，见 9.0.22）
    confirm_margin: float = 0.0  # 求证阈值：top1-top2 差小于它 ⇒ 回候选+疑问让人裁（0=关闭）


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
    # 🔴 2026-11-08：窗口不再按 kw_hit 截断（60→300 仍会漏），改成「正则粗筛 + 全量候选」，
    #   真正的排序在下面按 IDF 做。上限 5000 只是防爆保护（39k 库里 8 个词最多命中也才几千）。
    multi = await _multi_kw(kws_exp, uid, limit=5000) if kws_exp else []
    if multi:
        chans["C"] = multi

    if body.days or any(h in q for h in RECENT_HINTS):
        chans["T"] = await _recent(body.days or 7, kws_exp, uid, limit=30)

    # 语义通道（2026-11-07 接上）：只有它能在「字面不重合」的提问上找到卡。
    if body.semantic:
        # 2026-11-08：S 通道从 30 → 200。语义检索是向量索引，多捞几乎不要钱；
        # 而 eval --k 10 时原来只捞 30 条，很多「字面不重合、只能靠语义」的记忆根本进不了池。
        sem = await _semantic(q, uid, limit=max(limit, 200), sim_floor=body.sim_floor)
        if sem:
            chans["S"] = sem

    # ---- C 通道：按「词的辨识度」加权，而不是按命中个数（2026-11-08）----
    # 试过两条路，都留痕：
    #   ① 等权命中计数 → 「字段/原因/标准」这些泛词和「TMT/2438」同分，实测让 SVG 卡登顶。
    #   ② 候选池内 IDF → 池子本身是按「命中任一词」筛出来的，df 分布被压缩，
    #      稀有词算不出稀有（39k 全库里 df=381 的词，在 2000 条池子里看起来只差 5 倍 ⇒ log 后几乎无差别）。
    #      实测反而把分数拉平，recall 从 72% 掉到 67%，**因此放弃**。
    # 现在用可解释的静态权重：专名（ascii / 含数字 / 长词）比两字常用词更 specific。
    kw_w = {k: _kw_weight(k) for k in kws_exp}
    top3_w = sum(sorted(kw_w.values(), reverse=True)[:3]) or 1.0

    pool_map: dict[str, dict] = {}
    for ch, rows in chans.items():
        for r in rows:
            key = r.get("no") or f"id:{r['id']}"
            base = float(CREDIT[ch])
            if ch == "C":
                got = sum(kw_w.get(k, 1.0) for k in (r.get("hit_kws") or []))
                base = CREDIT[ch] * min(got, top3_w) / top3_w
            if ch == "S":
                # 语义分按相似度折算：sim=0.9 → 0.9*40，避免任何一条都拿满分
                base = float(CREDIT[ch]) * max(0.0, min(1.0, float(r.get("sim") or 0.0)))
            # 🔴 2026-11-08 删掉「无档号 × 0.75」：档号是卡片的元数据，不是相关性信号。
            #   这条降权让占 89% 的非卡片记忆先天少 25%，是「修了过滤仍然搜不到」的第二个原因。
            #   「卡片优先」已经由下面的 tie-break 承担，不该再拿分数惩罚。
            if key in pool_map:
                pool_map[key]["channels"] = pool_map[key]["channels"] + ch
                pool_map[key]["score"] += base
            else:
                pool_map[key] = {"id": str(r["id"]), "no": r.get("no") or "",
                                 "head": r.get("head") or "",
                                 "channels": ch, "score": base}

    def _id_num(x: dict) -> int:
        """id 必须是**数值**排序（2026-11-08 DSH P1，已核实）。

        原来用 str 比较："100" < "99"（逐字符 '1'<'9'）⇒ 排序结果随 id 位数变化而抖动，
        看起来「新记忆靠前」纯属歪打正着，一旦 id 到 4-5 位就不可控。
        现在显式按数值降序（id 自增 ⇒ 越大越新），行为与原来一致但可控。
        """
        try:
            return int(x.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    out = sorted(pool_map.values(),
                 key=lambda x: (-x["score"],
                                0 if str(x.get("head") or "").startswith(CARD_PREFIX) else 1,
                                -_id_num(x)))
    # 弃权（2026-11-07）：以前无论多不相干都硬返 top-k，负样本必然被污染。
    if _should_abstain(out, body.abstain_below):
        return {"query": q, "user_id": uid, "keywords": kws, "expanded": kws_exp,
                "channel_counts": {k: len(v) for k, v in chans.items()},
                "candidates": [], "abstained": True,
                "abstain_reason": f"最高分 {float(out[0].get('score') or 0):.1f} < 阈值 {body.abstain_below:.1f}",
                "suppressed": len(out)}

    resp = {"query": q, "user_id": uid, "keywords": kws, "expanded": kws_exp,
            "channel_counts": {k: len(v) for k, v in chans.items()},
            "candidates": out[:limit]}
    if _needs_confirmation(out, body.confirm_margin):
        # 不装懂：把最像的 3 条摆出来，请人来判；判完的结果由调用方回写（access/heat/label）
        resp["confirm"] = {
            "reason": "top1 与 top2 分数接近（或孤证分数偏低）",
            "margin": body.confirm_margin,
            "question": f"「{q}」在记忆里有 {len(out[:3])} 条都沾边，你能确认是哪一个吗？",
            "options": [{"id": c.get("id"), "no": c.get("no"), "head": c.get("head"),
                         "score": c.get("score"), "channels": c.get("channels")}
                        for c in out[:3]],
        }
    return resp


class LabelIn(BaseModel):
    """人做的裁决（求证回写）。chosen_id=None 表示「都不是」——这也是有效信号。"""
    user_id: str = "default"
    query: str
    chosen_id: int | None = None
    selected_no: str | None = None
    candidates: List[dict] = []
    margin: float | None = None
    source: str = "confirm"          # confirm = 召回求证；conflict = 冲突裁决
    note: str | None = None
    rejected_ids: List[int] = []     # 人明确说「这条不对」的卡（仅 conflict 用）


@router.post("/label")
async def record_label(body: LabelIn = Body(...)):
    """把人的裁决记下来 —— 「问人」之后必须有这一步，否则问完就散了。

    一份数据两个用途：① 选中项 heat/access 上升（调权的燃料）；
    ② 直接就是一条评测题（query + 正确档号），可用 scripts/labels_to_cases.py 导出。
    """
    # 脏输入必须挡在门口：前端缓存过期会提交不存在的卡 id，默认实现是 FK 报错 → 500。
    # 500 对前端等于「系统挂了」，实际上是「这张卡已经没了」，该给 400 + 明确原因。
    query_text = (body.query or "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="query 不能为空")
    uid = body.user_id or "default"
    cands = body.candidates or []
    # 🔴 2026-11-08 修（DSH 审计 P0-2，已核实成立）：
    #   原来这里 `chosen_no = body.selected_no` 客户端给什么就落什么 ——
    #   而档号会经 labels_to_cases 变成**评测标准答案**，等于允许污染自己的尺子。
    #   现在：档号一律以库为准（下面在事务里回填/校验），客户端给的只作对照。
    chosen_no = (body.selected_no or "").strip() or None
    async with pool.acquire() as conn:
        async with conn.transaction():
            if body.chosen_id is not None:
                owned = await conn.fetchrow(
                    "SELECT substring(content from '档号：\\s*([^\\s]+)') AS no "
                    "FROM memories WHERE id=$1 AND user_id=$2 AND is_deleted=FALSE",
                    body.chosen_id, uid)
                if not owned:
                    raise HTTPException(status_code=400,
                                        detail=f"chosen_id={body.chosen_id} 不属于 {uid} 或已删除")
                db_no = (owned["no"] or "").strip() or None
                if chosen_no and db_no and chosen_no != db_no:
                    raise HTTPException(status_code=400,
                                        detail=f"selected_no={chosen_no} 与库内档号 {db_no} 不一致（拒绝伪造）")
                chosen_no = db_no or chosen_no
            elif chosen_no:
                # 只给了档号没给 id：按档号反查，必须真实存在且未删除，否则不收
                row = await conn.fetchrow(
                    "SELECT substring(content from '档号：\\s*([^\\s]+)') AS no "
                    "FROM memories WHERE user_id=$1 AND is_deleted=FALSE "
                    "AND content LIKE '%档号：' || $2 || '%' LIMIT 1", uid, chosen_no)
                if not row:
                    raise HTTPException(status_code=400,
                                        detail=f"selected_no={chosen_no} 在库中不存在（拒绝凭空档号）")
            rejected_ids = list(body.rejected_ids or [])
            if rejected_ids:
                owned_ids = await conn.fetch(
                    "SELECT id FROM memories WHERE id = ANY($1::bigint[]) AND user_id=$2 "
                    "AND is_deleted=FALSE",
                    rejected_ids, uid)
                owned_set = {r["id"] for r in owned_ids}
                rejected_ids = [i for i in rejected_ids if i in owned_set]
            row = await conn.fetchrow(
                """INSERT INTO memory_labels
                       (user_id, query, chosen_id, chosen_no, candidates, margin, source, note)
                   VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8)
                   RETURNING id, created_at""",
                uid, query_text, body.chosen_id, chosen_no,
                json.dumps(cands, ensure_ascii=False), body.margin, body.source, body.note)
            bumped = False
            adjusted = {}
            if body.chosen_id is not None:
                # 选中 = 人确认这条可信：
                #   · reliability +0.10（可信度，排序里权重 0.10）—— 这是「对不对」的载体
                #   · access_count +1（被用过一次）
                #   · 求证来源额外 heat +0.05（热度=使用频率，不拿来表达对错）
                heat_expr = ("LEAST(1.0, COALESCE(heat_score, 0.5) + 0.05)"
                             if body.source == "confirm" else "COALESCE(heat_score, 0.5)")
                res = await conn.execute(
                    f"""UPDATE memories SET
                            reliability = LEAST(1.0, COALESCE(reliability, 0.5) + 0.10),
                            heat_score = {heat_expr},
                            access_count = COALESCE(access_count, 0) + 1
                        WHERE id=$1 AND user_id=$2""",
                    body.chosen_id, uid)
                bumped = res.endswith(" 1")
                adjusted["chosen"] = {"id": body.chosen_id, "reliability_delta": 0.10,
                                      "heat_delta": 0.05 if body.source == "confirm" else 0.0}

            rejected = []
            if rejected_ids:
                # 人明确否掉的卡：可信度 -0.10（下限 0）。不删、不改内容、可回滚。
                res = await conn.execute(
                    """UPDATE memories SET
                           reliability = GREATEST(0.0, COALESCE(reliability, 0.5) - 0.10)
                       WHERE id = ANY($1::bigint[]) AND user_id=$2""",
                    rejected_ids, uid)
                rejected = rejected_ids
                adjusted["rejected"] = {"ids": rejected, "reliability_delta": -0.10,
                                        "rows": int(res.split()[-1]) if res.split() else 0}
    return {"label_id": row["id"], "created_at": row["created_at"].isoformat(timespec="seconds"),
            "chosen_id": body.chosen_id, "chosen_no": chosen_no,
            "heat_bumped": bumped, "adjusted": adjusted}


@router.get("/labels")
async def list_labels(user_id: str = "default", limit: int = 20):
    """最近的人工裁决（复盘/导出用）。"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, query, chosen_id, chosen_no, margin, source, note, created_at
                 FROM memory_labels WHERE user_id=$1 ORDER BY id DESC LIMIT $2""",
            user_id, max(1, min(int(limit), 200)))
    return {"user_id": user_id, "count": len(rows),
            "labels": [{**dict(r), "created_at": r["created_at"].isoformat(timespec="seconds")}
                       for r in rows]}


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
