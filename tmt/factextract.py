#!/usr/bin/env python3
"""tmt/factextract.py — 事实提取管道 v6.4
设计来源: LongMemEval 归因结论 (#6293) — 补上"个人信息 facts"维度
从 session/worklog 提取用户事实(个人信息/偏好/事件/安排/能力) → preference/knowledge

教训吸收:
- 短文本逐条提取 (豆包 lite 长会话漏深处答案)
- 非 json 模式 (豆包 json_mode 长 prompt >2500 字符返回空)
- tier3 lite 够用 (提取是简单任务)
- 只提取不编造, ANN 去重闸机, 热度 0.65, 溯源 metadata, 失败重捞

用法: venv/bin/python tmt/factextract.py [--batch N] [--dry-run]
"""
import argparse
import asyncio
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先加载 .env 再 import core (key 在 import 时读取)
from tmt.distill import load_env, get_pool, dedup_check, get_embedding, utcnow, EXCLUDE_WORDS

load_env()

from core.llm import call_llm  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("factextract")

MIN_LEN = 80          # 最小候选长度 (短文本提取)
MAX_FACTS = 5         # 每条最多事实数
HEAT_INIT = 0.65      # 功能记忆初始热度
DEDUP_THRESHOLD = 0.92

# 偏好/个人信息 → preference; 其他事实 → knowledge
PREF_KEYWORDS = ("喜欢", "爱好", "想要", "希望", "居住", "住在", "工作", "职业",
                 "毕业", "家人", "宠物", "生日", "习惯", "不爱", "讨厌", "最近在",
                 "计划", "打算", "预约", "每周", "每天")


def extract_prompt(content: str) -> str:
    return f"""从下面的内容中提取关于用户的事实。
事实类型: 个人信息(毕业/职业/居住/家人/宠物/年龄)、偏好(喜欢/不喜欢/习惯)、事件(做过的具体事/经历)、安排(计划/预约/任务)、能力(技能)。

内容:
{content}

规则:
- 只提取明确提到的, 不猜测不编造
- 每条一行, 以 "- " 开头
- 中文表述
- 最多{MAX_FACTS}条
- 没有事实就输出 "无" """


def parse_facts(text: str) -> list[str]:
    """解析 "- fact" 行格式 (非 json)"""
    facts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line in ("无", "没有", "暂无"):
            continue
        line = re.sub(r"^[-•*]?\s*\d*[\.、\)]?\s*", "", line).strip()
        if len(line) > 4 and not line.startswith("从") and not line.startswith("规则"):
            facts.append(line[:200])
        if len(facts) >= MAX_FACTS:
            break
    return facts


def classify_fact(fact: str) -> str:
    """偏好/个人信息 → preference, 其他 → knowledge"""
    if any(k in fact for k in PREF_KEYWORDS):
        return "preference"
    return "knowledge"


def is_skip(content: str) -> bool:
    """跳过过短/寒暄 (EXCLUDE_WORDS 是寒暄排除词)"""
    if len(content) < MIN_LEN:
        return True
    if any(s in content for s in EXCLUDE_WORDS):
        return True
    return False


async def extract_facts(content: str) -> tuple[list[str], str]:
    """非 json 提取 (tier3 lite)。返回 (facts, status): status in ('ok','no_facts','fail')"""
    r = call_llm(extract_prompt(content), tier=3, temperature=0.1)
    txt = (r.get("content") or "").strip()
    if not txt:
        # 超时/空 → 重试一次
        r = call_llm(extract_prompt(content), tier=3, temperature=0.1)
        txt = (r.get("content") or "").strip()
    if not txt:
        return [], "fail"
    if txt in ("无", "没有", "暂无", "没有事实"):
        return [], "no_facts"
    return parse_facts(txt), "ok"


async def find_candidates(pool, batch: int) -> list[dict]:
    rows = await pool.fetch(
        "SELECT id, content, category FROM memories "
        "WHERE user_id='default' AND category IN ('session','worklog') AND is_deleted=FALSE "
        "AND metadata->>'fact_extracted' IS NULL "
        "ORDER BY created_at ASC LIMIT $1", batch)
    return [dict(r) for r in rows]


async def insert_fact(pool, src_id: int, src_category: str, fact: str, ftype: str) -> bool:
    """事实入库 (preference/knowledge, 热度 0.65, 溯源)"""
    vec = await get_embedding(fact)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    metadata = json.dumps({
        "fact_extracted_from": src_id,
        "fact_extracted_at": utcnow(),
        "source_category": src_category,
        "fact_type": ftype,
    }, ensure_ascii=False)
    r = await pool.fetchrow(
        "INSERT INTO memories (user_id, project_id, content, category, embedding, metadata, heat_score, tmt_level, tier, hall) "
        "VALUES ('default', NULL, $1, $2, $3, $4::jsonb, $5, 1, 'L1', 'engineering') "
        "RETURNING id",
        fact, ftype, vec_str, metadata, HEAT_INIT)
    return r is not None


async def run(batch: int, dry_run: bool) -> None:
    pool = await get_pool()
    cands = await find_candidates(pool, batch)
    log.info("候选 %d 条 (dry_run=%s)", len(cands), dry_run)

    stats = {"extracted": 0, "facts": 0, "dedup": 0, "fail": 0, "skip": 0, "no_facts": 0}
    in_batch: list[str] = []

    for i, c in enumerate(cands, 1):
        if is_skip(c["content"]):
            stats["skip"] += 1
            continue
        log.info("[%d/%d] 提取 #%d (%s): %.40s...", i, len(cands), c["id"], c["category"], c["content"])
        facts, status = await extract_facts(c["content"])
        if status == "fail":
            stats["fail"] += 1
            continue
        if status == "no_facts" or (status == "ok" and not facts):
            stats["no_facts"] += 1
            if not dry_run:
                await pool.execute(
                    "UPDATE memories SET metadata = metadata || $2::jsonb WHERE id = $1",
                    c["id"], json.dumps({"fact_extracted": True, "fact_extracted_at": utcnow(),
                                          "fact_result": "no_facts"}, ensure_ascii=False))
            continue
        if not dry_run:
            for f in facts:
                if await dedup_check(pool, f, in_batch):
                    stats["dedup"] += 1
                    continue
                ftype = classify_fact(f)
                ok = await insert_fact(pool, c["id"], c["category"], f, ftype)
                if ok:
                    stats["facts"] += 1
                    in_batch.append(f)
                    log.info("  +%s [%s]: %.50s", ftype, ftype, f)
            await pool.execute(
                "UPDATE memories SET metadata = metadata || $2::jsonb WHERE id = $1",
                c["id"], json.dumps({"fact_extracted": True, "fact_extracted_at": utcnow()},
                                    ensure_ascii=False))
        stats["extracted"] += 1

    log.info("═══ 事实提取结果: 处理 %d 条 → %d facts / %d 去重 / %d 跳过 / %d 无事实 / %d 失败 ═══",
             stats["extracted"], stats["facts"], stats["dedup"], stats["skip"], stats["no_facts"], stats["fail"])
    await pool.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.batch, args.dry_run))


if __name__ == "__main__":
    main()
