#!/usr/bin/env python3
"""
distill.py — 知识蒸馏管道 v0.1 (2026-08-05)

设计来源: 爆炸遗产考古 — NCP-008 知识吸收七步(识别→分析→语义化→索引→验证→归档→引用)
          + 认知AI底座 TEL/MAIL 协议(架构级杜绝幻觉: FACTS 多源验证 + MAIL 结构化返回)

目标: 解决分类失衡 (session+worklog 88%, knowledge 仅 9%)
    从原始 session/worklog 记忆中提炼可复用的 knowledge/pitfall 知识条目。

用法:
  python3 distill.py --batch 30            # 处理最近 30 条未蒸馏候选
  python3 distill.py --batch 30 --dry-run  # 只预览候选+LLM产出, 不入库
  python3 distill.py --stats               # 查看蒸馏统计

流程 (七步映射):
  1. 识别    — 候选筛选: session/worklog + 未蒸馏 + 长度/信号词过滤
  2. 分析    — TEL 组装: CONTRACT + FACTS + REQUIREMENTS
  3. 语义化  — LLM 凝练: 豆包 Lite (tier3), JSON 模式
  4. 索引    — 入库: category=knowledge/pitfall, hall=archive/engineering
  5. 验证    — 去重闸机: pgvector ANN, sim>0.92 跳过
  6. 归档    — 三馆流转: knowledge→archive, pitfall→engineering
  7. 引用    — metadata.source_memory_id 溯源
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

async def get_embedding(text: str) -> list[float]:
    """同步 embedding 包装 (同 consolidate.py 模式)"""
    return _embedding_sync([text])[0]

PG_DSN = os.environ.get("MNEMOSYNE_PG_DSN", "postgresql://postgres@127.0.0.1:5432/mnemosyne")


def load_env(path: str = "/opt/mnemosyne/.env") -> None:
    """加载 .env (独立脚本不依赖 systemd EnvironmentFile)"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


load_env()

# key 就绪后再 import (core.config 在 import 时读取环境变量)
from core.embedding import get_embedding as _embedding_sync
from core.llm import call_llm_json

# 知识信号词: 候选记忆命中任一即进入蒸馏候选
SIGNAL_WORDS = (
    "学到", "解决", "发现", "坑", "教训", "经验", "方案", "架构", "踩坑",
    "修复", "优化", "结论", "要点", "注意", "规则", "流程", "设计", "原理",
    "配置", "部署", "故障", "报错", "错误", "成功", "失败", "踩过", "总结",
)
# 排除词: 纯寒暄/情绪/无关
EXCLUDE_WORDS = ("撒娇", "可爱", "晚安", "早安", "哈哈", "嘿嘿", "呜呜", "喵~", "欺负", "亲亲")

MIN_LEN = 120          # 最小候选长度
DEDUP_THRESHOLD = 0.92  # 与已有 knowledge 相似度超过此值 → 跳过
MAX_RETRY = 2          # LLM 失败重试

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("distill")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)


# ── 1. 识别: 候选筛选 ──
async def find_candidates(pool, batch: int) -> list[dict]:
    """未蒸馏的 session/worklog 记忆, 按新鲜度倒序取 batch 条"""
    rows = await pool.fetch(
        """
        SELECT id, content, category, created_at
        FROM memories
        WHERE user_id = 'default'
          AND is_deleted = FALSE
          AND category IN ('session', 'worklog')
          AND (metadata->>'distilled_at') IS NULL
          AND char_length(content) >= $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        MIN_LEN, batch * 3,  # 多取 3 倍, 信号词过滤后仍够数
    )
    # 信号词 + 排除词过滤
    cands = []
    for r in rows:
        c = r["content"]
        if any(w in c for w in EXCLUDE_WORDS) and not any(w in c for w in SIGNAL_WORDS):
            continue
        if any(w in c for w in SIGNAL_WORDS):
            cands.append(r)
        if len(cands) >= batch:
            break
    # 若信号词过滤后不足, 补足长度足够且非纯寒暄的
    if len(cands) < batch:
        for r in rows:
            if r not in cands and len(cands) < batch:
                cands.append(r)
    return cands[:batch]


# ── 2+3. 分析 + 语义化: TEL 组装 → LLM 凝练 ──
def build_tel(content: str) -> str:
    return f"""<TEL>
<CONTRACT>你是记忆宫殿的知识蒸馏器。把一段原始记忆凝练成结构化知识条目。铁律:
1. 只提炼可复用的知识/教训/经验/方案, 剔除寒暄、情绪、过程流水、对话噪音
2. type 三选一: knowledge(可复用知识/方案/经验) / pitfall(坑/教训/踩坑) / skip(无提炼价值)
3. summary 用中文, 一句话讲清核心, 60字内
4. keywords 给 3-5 个检索关键词(中英皆可)
5. importance 0-1, 越通用越可复用越高
6. confidence 三选一: high(事实明确可复用) / medium(经验性) / low(存疑)
7. 必须输出合法 JSON, 不要多余文字</CONTRACT>
<TASK>蒸馏以下原始记忆为知识条目</TASK>
<FACTS>{content[:3000]}</FACTS>
<REQUIREMENTS>{{"type": "knowledge|pitfall|skip", "summary": "...", "keywords": [...], "importance": 0.0-1.0, "confidence": "high|medium|low"}}</REQUIREMENTS>
</TEL>"""


async def distill_one(content: str) -> dict | None:
    for attempt in range(MAX_RETRY):
        try:
            res = call_llm_json(build_tel(content), tier=3)
            raw = res.get("content", "")
            m = json.loads(raw) if raw else {}
            if not m or "type" not in m:
                raise ValueError(f"LLM 返回无 type: {raw[:100]}")
            return m
        except Exception as e:
            log.warning("  LLM 失败 (attempt %d): %s", attempt + 1, e)
    return None


# ── 5. 验证: 去重闸机 (ANN) ──
async def dedup_check(pool, summary: str, in_batch: list[str] | None = None) -> bool:
    """与已有 knowledge/pitfall 记忆比较 + 本批内比较, sim>阈值返回 True (重复)"""
    # 批内去重 (v6.2): 同批已提炼的相似条目直接跳过
    if in_batch:
        for prev in in_batch:
            if prev and len(prev) > 5 and (summary[:40] in prev or prev[:40] in summary):
                return True
    emb = await get_embedding(summary)
    if not emb:
        return False
    vec_str = "[" + ",".join(str(x) for x in emb) + "]"
    row = await pool.fetchrow(
        """
        SELECT 1 - (embedding <=> $1::vector) AS sim
        FROM memories
        WHERE user_id = 'default' AND is_deleted = FALSE
          AND category IN ('knowledge', 'pitfall')
          AND embedding IS NOT NULL
          AND 1 - (embedding <=> $1::vector) > $2
        ORDER BY embedding <=> $1::vector
        LIMIT 1
        """,
        vec_str, DEDUP_THRESHOLD,
    )
    return row is not None


# ── 4+6+7. 索引+归档+引用: 入库 ──
async def insert_knowledge(pool, src_id: int, src_category: str, distilled: dict) -> bool:
    mtype = distilled["type"]
    if mtype == "skip":
        # 只标记源, 不产生新记忆
        await pool.execute(
            "UPDATE memories SET metadata = metadata || $2::jsonb WHERE id = $1",
            src_id, json.dumps({"distilled_at": utcnow(), "distill_result": "skip"}),
        )
        return False

    hall = "archive" if mtype == "knowledge" else "engineering"
    # 再次确认类型合法
    if mtype not in ("knowledge", "pitfall"):
        return False

    summary = (distilled.get("summary") or "").strip()
    if len(summary) < 10:
        # 摘要太短视为无效, 只标记
        await pool.execute(
            "UPDATE memories SET metadata = metadata || $2::jsonb WHERE id = $1",
            src_id, json.dumps({"distilled_at": utcnow(), "distill_result": "invalid"}),
        )
        return False

    importance = min(max(float(distilled.get("importance", 0.4)), 0.1), 0.95)
    # v6.2: 蒸馏新知识初始热度信号 0.65 (默认 0.5 → 0.65, 标记"新提炼")
    # v6.3: pitfall(坑) 天生重要 → 0.70
    heat_init = 0.70 if mtype == "pitfall" else 0.65
    metadata = {
        "distilled_from": src_id,
        "distilled_at": utcnow(),
        "source_category": src_category,
        "keywords": distilled.get("keywords", []),
        "confidence": distilled.get("confidence", "medium"),
    }
    await pool.execute(
        """
        INSERT INTO memories
          (user_id, content, category, hall, importance, tier, heat_score, metadata, tmt_level)
        VALUES ('default', $1, $2, $3, $4, 'L3', $5, $6::jsonb, 1)
        """,
        summary, mtype, hall, importance, heat_init, json.dumps(metadata, ensure_ascii=False),
    )
    # 标记源已蒸馏
    await pool.execute(
        "UPDATE memories SET metadata = metadata || $2::jsonb WHERE id = $1",
        src_id, json.dumps({"distilled_at": utcnow(), "distill_result": mtype}),
    )
    return True


# ── 主流程 ──
async def run(batch: int, dry_run: bool) -> None:
    pool = await get_pool()
    try:
        cands = await find_candidates(pool, batch)
        log.info("候选 %d 条 (dry_run=%s)", len(cands), dry_run)

        stats = {"knowledge": 0, "pitfall": 0, "skip": 0, "dedup": 0, "fail": 0}
        in_batch: list[str] = []  # v6.2: 批内去重
        for i, c in enumerate(cands, 1):
            log.info("[%d/%d] 蒸馏 #%d (%s): %.50s...", i, len(cands), c["id"], c["category"], c["content"])
            d = await distill_one(c["content"])
            if d is None:
                stats["fail"] += 1
                continue
            t = d.get("type", "skip")
            if t == "skip":
                stats["skip"] += 1
                if not dry_run:
                    await insert_knowledge(pool, c["id"], c["category"], d)
                log.info("  → skip: %.60s", d.get("summary", ""))
                continue
            if t not in ("knowledge", "pitfall"):
                stats["skip"] += 1
                continue

            dup = await dedup_check(pool, d.get("summary", ""), in_batch if not dry_run else None)
            if dup:
                stats["dedup"] += 1
                log.info("  → 去重跳过 (sim>%.2f): %.60s", DEDUP_THRESHOLD, d.get("summary", ""))
                continue

            stats[t] += 1
            in_batch.append(d.get("summary", ""))
            if not dry_run:
                await insert_knowledge(pool, c["id"], c["category"], d)
            log.info("  → %s [%s]: %.70s (imp=%.2f)", t, d.get("confidence", "?"), d.get("summary", ""), float(d.get("importance", 0)))

        log.info("═══ 蒸馏完成: %s ═══", json.dumps(stats, ensure_ascii=False))
    finally:
        await pool.close()


async def show_stats(pool) -> None:
    rows = await pool.fetch(
        """
        SELECT category, COUNT(*) AS n,
               COUNT(*) FILTER (WHERE metadata ? 'distilled_at') AS distilled
        FROM memories
        WHERE user_id='default' AND is_deleted=FALSE
        GROUP BY category ORDER BY n DESC
        """
    )
    print("\n=== 分类分布 (蒸馏前/后) ===")
    print(f"{'分类':<12}{'总数':>6}{'已蒸馏':>8}")
    for r in rows:
        print(f"{r['category']:<12}{r['n']:>6}{r['distilled']:>8}")


async def main():
    parser = argparse.ArgumentParser(description="Mnemosyne 知识蒸馏管道")
    parser.add_argument("--batch", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    pool = await get_pool()
    try:
        if args.stats:
            await show_stats(pool)
            return
        await run(args.batch, args.dry_run)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
