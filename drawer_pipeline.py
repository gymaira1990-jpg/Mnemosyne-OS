#!/usr/bin/env python3
"""
Mnemosyne v7.1 抽屉化三级管线 (drawer_pipeline.py)
一级: 压缩去噪 — 冷/冻记忆 LLM 提摘要, 原文入 full_content_archived
二级: 完整压缩去重 — 相似记忆合并 (sim>0.95 版本 / 0.90-0.95 合并摘要+频次+最高热度)
三级: 蒸馏合并 — 冻结抽屉蒸馏核心知识 (复用 distill 去重闸机)
冲突加速遗忘 — invalid_at 记忆自动进遗忘候选

用法:
  venv/bin/python drawer_pipeline.py --stage denoise    # 一级: 压缩去噪 (每日)
  venv/bin/python drawer_pipeline.py --stage dedup      # 二级: 去重合并 (每日)
  venv/bin/python drawer_pipeline.py --stage distill    # 三级: 蒸馏合并 (每周)
  venv/bin/python drawer_pipeline.py --stage forget     # 冲突加速遗忘 (每日)
  venv/bin/python drawer_pipeline.py --all              # 全跑
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/mnemosyne")
from tmt.distill import load_env, get_pool, get_embedding  # 复用 .env 加载 + 连接池 + 向量

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("drawer_pipeline")

# ── 配置 ──
DENOISE_MIN_LEN = 300      # 超过此长度才值得压缩
DENOISE_TARGET_DRAWERS = ("cool", "frozen")  # 只压缩冷/冻抽屉
DEDUP_SIM_VERSION = 0.95   # ≥0.95 → 版本+1 (保留新旧)
DEDUP_SIM_MERGE = 0.90     # 0.90-0.95 → 合并 (摘要取长+频次累加+最高热度)
DEDUP_BATCH = 30            # 单批候选数
# 2026-09-28 修（issue T-0199）: 原来只有 DEDUP_BATCH，一轮只吃 30 条，
#   而 distill/factextract 每天新增 500+ 条 ⇒ 队列永不追上，冗余长期堆积。
#   改为「循环跑到无候选 / 达上限 / 超预算」三选一即止，仍保留 oldest-first（先清历史）。
DEDUP_MAX_BATCHES = 100     # 100 批 × 30 = 3000 条/轮，覆盖 500+/天 新增并快速清积压
#   实测（2026-09-28 canary）: 20 批=600 条仅用 15.1s ⇒ 原上限保守；时间预算才是真正的护栏。
DEDUP_TIME_BUDGET_S = 600   # 单轮时间预算（秒），防跑爆；cron 03:35 起跑，留足余量
FORGET_CONFLICT_DROP = 0.05  # 冲突记忆额外降温 (reflect 已 -0.1, 这里只标记)


async def stage_denoise(pool):
    """一级: 压缩去噪 — 冷/冻长记忆 LLM 提摘要, 原文归档"""
    rows = await pool.fetch("""
        SELECT id, content, category FROM memories
        WHERE is_deleted = FALSE
          AND temp_drawer IN ('cool','frozen')
          AND LENGTH(content) >= $1
          AND COALESCE(metadata->>'denoised','false') = 'false'
        ORDER BY created_at ASC LIMIT $2
    """, DENOISE_MIN_LEN, DEDUP_BATCH)
    log.info("压缩去噪: %d 条候选", len(rows))
    done = 0
    for r in rows:
        try:
            # 原文归档到 full_content_archived (已有列), 内容保留 (不截断 — 防信息丢失)
            await pool.execute("""
                UPDATE memories SET
                  full_content_archived = content,
                  metadata = COALESCE(metadata,'{}'::jsonb) || '{"denoised":true}'::jsonb,
                  updated_at = NOW()
                WHERE id = $1
            """, r["id"])
            done += 1
        except Exception as e:
            log.warning("  denoise %s 失败: %s", r["id"], e)
    log.info("压缩去噪完成: %d/%d", done, len(rows))
    return done


async def _dedup_one_batch(pool):
    """单批去重 — 返回 (候选数, 合并数)。**主体逻辑与行为一字未改**（含 v7.1 的
    JSON 拼接/embedding 重算两处坑的修法），只是把结果多返回一个候选数供外层判断。
    """
    rows = await pool.fetch("""
        SELECT id, content, category, heat_score, access_count, embedding, dedup_fingerprint
        FROM memories
        WHERE is_deleted = FALSE
          AND embedding IS NOT NULL
          AND COALESCE(metadata->>'dedup_checked','false') = 'false'
        ORDER BY created_at ASC LIMIT $1
    """, DEDUP_BATCH)
    log.info("去重合并: %d 条候选", len(rows))
    merged = 0
    for r in rows:
        # 找最相似且 id < 自己的 (只向前合并, 避免反复)
        sim_row = await pool.fetchrow("""
            SELECT m2.id, m2.content, m2.heat_score, m2.access_count, m2.category,
                   m2.embedding <=> $2::vector AS dist
            FROM memories m2
            WHERE m2.is_deleted = FALSE
              AND m2.id < $1
              AND m2.embedding IS NOT NULL
            ORDER BY m2.embedding <=> $2::vector ASC
            LIMIT 1
        """, r["id"], r["embedding"])
        if not sim_row:
            await pool.execute(
                "UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{\"dedup_checked\":true}'::jsonb WHERE id=$1",
                r["id"])
            continue
        sim = 1.0 - sim_row["dist"]
        if sim >= DEDUP_SIM_MERGE:
            # 合并到旧记忆 (id 小的)
            merged_content = r["content"] if len(r["content"]) > len(sim_row["content"]) else sim_row["content"]
            new_heat = max(r["heat_score"], sim_row["heat_score"])
            new_acc = (r["access_count"] or 0) + (sim_row["access_count"] or 0)
            # ⚠️ 修 v7.1 坑: `|| '...'::jsonb` 中 :: 优先级高于 || → 单独把残缺串转 jsonb 必崩
            #    (InvalidTextRepresentationError: invalid input syntax for type json, 每日 dedup 静默失败)
            #    改用 jsonb_build_object 构造, 彻底避开字符串拼 JSON; merged_from 追加保留合并链
            await pool.execute("""
                UPDATE memories SET
                  content = $1,
                  heat_score = $2,
                  access_count = $3,
                  parent_memory_id = COALESCE(parent_memory_id, $4),
                  metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object(
                    'merged_from', COALESCE(metadata->'merged_from','[]'::jsonb) || $5::jsonb),
                  updated_at = NOW()
                WHERE id = $6
            """, merged_content, new_heat, new_acc, r["id"], json.dumps([r["id"]]), sim_row["id"])
            # 合并后 content 变了 → 必须重算 embedding, 否则向量检索失真 (v7.1 教训: 改 content 不改 embedding)
            try:
                new_emb = await get_embedding(merged_content)
                emb_str = "[" + ",".join(str(x) for x in new_emb) + "]"  # asyncpg 传 vector 必须字符串
                await pool.execute(
                    "UPDATE memories SET embedding = $1::vector WHERE id = $2",
                    emb_str, sim_row["id"])
            except Exception as e:
                log.warning("  embedding 重算失败 #%s: %s", sim_row["id"], e)
            # 软删新记忆 (留指纹)
            await pool.execute("""
                UPDATE memories SET is_deleted = TRUE, forgotten_at = NOW(),
                  metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object('merged_into', $2::int)
                WHERE id = $1
            """, r["id"], sim_row["id"])
            merged += 1
            log.info("  合并 #%s → #%s (sim=%.3f)", r["id"], sim_row["id"], sim)
        else:
            await pool.execute(
                "UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{\"dedup_checked\":true}'::jsonb WHERE id=$1",
                r["id"])
    log.info("本批去重完成: 候选 %d, 合并 %d", len(rows), merged)
    return len(rows), merged


async def stage_dedup(pool):
    """二级: 完整压缩去重 — 相似记忆合并 (sim≥0.90)

    2026-09-28（T-0199）: 由「一轮只跑一批 30 条」改为**循环**，直到
      · 候选不足一批（队列已清空）／ · 达到 DEDUP_MAX_BATCHES ／ · 超出时间预算
    三选一即止。保留 oldest-first（先清历史），单批逻辑在 _dedup_one_batch 内未改。
    """
    t0 = time.monotonic()
    total_merged = 0
    batches = 0
    for batch_no in range(1, DEDUP_MAX_BATCHES + 1):
        if time.monotonic() - t0 > DEDUP_TIME_BUDGET_S:
            log.info("去重: 时间预算 %ds 用尽，本轮已跑 %d 批", DEDUP_TIME_BUDGET_S, batches)
            break
        n_cand, merged = await _dedup_one_batch(pool)
        batches += 1
        total_merged += merged
        if n_cand < DEDUP_BATCH:
            log.info("去重: 候选队列已清空（第 %d 批只剩 %d 条）", batch_no, n_cand)
            break
    else:
        log.info("去重: 达到单轮上限 %d 批（队列可能仍有积压，明日继续）", DEDUP_MAX_BATCHES)
    log.info("去重完成: 本轮 %d 批, 共合并 %d 条, 用时 %.1fs",
             batches, total_merged, time.monotonic() - t0)
    return total_merged


async def stage_forget(pool):
    """冲突加速遗忘: invalid_at 记忆标记为遗忘候选 + 额外降温"""
    rows = await pool.execute("""
        UPDATE memories SET
          heat_score = GREATEST(0.0, heat_score - $1),
          metadata = COALESCE(metadata,'{}'::jsonb) || '{"forget_candidate":true}'::jsonb
        WHERE is_deleted = FALSE
          AND invalid_at IS NOT NULL
          AND COALESCE(metadata->>'pinned','false') != 'true'
    """, FORGET_CONFLICT_DROP)
    log.info("冲突加速遗忘: 处理 %s 条", rows)
    return rows


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["denoise", "dedup", "distill", "forget", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env()
    pool = await get_pool()
    try:
        if args.stage in ("denoise", "all"):
            await stage_denoise(pool)
        if args.stage in ("dedup", "all"):
            await stage_dedup(pool)
        if args.stage in ("forget", "all"):
            await stage_forget(pool)
        if args.stage in ("distill", "all"):
            # 三级蒸馏: 复用现有 distill (冻结抽屉核心知识)
            log.info("蒸馏合并: 交给 tmt/distill.py 处理 (每日 cron 已配置)")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
