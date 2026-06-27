#!/usr/bin/env python3
"""
Reflector — Mnemosyne 定时反思引擎 v1.0

用法:
  python3 reflector.py --mode light    # 每小时执行：热度衰减 + 冗余合并
  python3 reflector.py --mode deep     # 每天凌晨执行：同上 + 实体提取

设计文档: 文件14 §6 Reflector 反思引擎
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

import asyncpg
import httpx

# ── 配置 ──
API_BASE = "http://127.0.0.1:8010"
PG_DSN = "postgresql://postgres@127.0.0.1:5432/mnemosyne"
# v5.1 — 已迁移到豆包 doubao-embedding-vision-251215
from core.embedding import get_embedding as _get_embedding
SIM_THRESHOLD = 0.92  # 余弦相似度 > 此值判为冗余合并
BATCH_SIZE = 200       # 每批处理的记忆数

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("reflector")


# ── 工具函数 ──

async def get_embedding(text: str) -> list[float]:
    """v5.1 — 豆包多模态 Embedding (via core.embedding)"""
    return _get_embedding([text])[0]


def cosine_sim(a_raw, b_raw) -> float:
    """pgvector 类型返回为 JSON 数组字符串 \"[0.014, -0.042, …]"，需反序列化"""
    a = json.loads(a_raw) if isinstance(a_raw, (str, bytes)) else a_raw
    b = json.loads(b_raw) if isinstance(b_raw, (str, bytes)) else b_raw
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na * nb > 0 else 0.0


def parse_embedding(raw) -> list[float]:
    """统一将 pgvector 返回值转为 float list"""
    if isinstance(raw, (str, bytes)):
        return json.loads(raw)
    return raw


async def get_all_users(pool) -> list[str]:
    rows = await pool.fetch(
        "SELECT DISTINCT user_id FROM memories WHERE is_deleted = FALSE"
    )
    return [r["user_id"] for r in rows]


# ── 冗余检测与合并 ──

async def detect_redundancy(pool, user_id: str) -> int:
    """
    检测余弦相似度 > SIM_THRESHOLD 的记忆对并合并。
    保留 heat_score 更高的那条，转移 entities，软删另一条。
    """
    rows = await pool.fetch(
        """SELECT id, content, heat_score
           FROM memories
           WHERE user_id = $1 AND is_deleted = FALSE
             AND embedding IS NOT NULL
           ORDER BY heat_score DESC""",
        user_id,
    )
    if len(rows) < 2:
        return 0

    merged = 0
    checked: set[int] = set()
    total = len(rows)

    for i in range(total):
        if rows[i]["id"] in checked:
            continue
        if merged >= BATCH_SIZE:
            break

        ei_raw = await pool.fetchval(
            "SELECT embedding::text FROM memories WHERE id = $1", rows[i]["id"]
        )
        if ei_raw is None:
            continue
        ei = parse_embedding(ei_raw)

        for j in range(i + 1, total):
            if rows[j]["id"] in checked:
                continue
            if merged >= BATCH_SIZE:
                break

            ej_raw = await pool.fetchval(
                "SELECT embedding::text FROM memories WHERE id = $1", rows[j]["id"]
            )
            if ej_raw is None:
                continue
            ej = parse_embedding(ej_raw)

            sim = cosine_sim(ei, ej)
            if sim < SIM_THRESHOLD:
                continue

            # 决定保留哪条（高热获胜）
            keep_id = rows[i]["id"]
            del_id = rows[j]["id"]
            if rows[j]["heat_score"] > rows[i]["heat_score"]:
                keep_id, del_id = del_id, keep_id

            # 转移 entities（避免重复）
            await pool.execute(
                """UPDATE memory_entities
                   SET memory_id = $1
                   WHERE memory_id = $2
                     AND entity_id NOT IN (
                       SELECT entity_id FROM memory_entities WHERE memory_id = $1
                     )""",
                keep_id,
                del_id,
            )
            # 软删冗余记忆
            await pool.execute(
                "UPDATE memories SET is_deleted = TRUE WHERE id = $1",
                del_id,
            )

            checked.add(del_id)
            merged += 1
            log.info("  └─ Merged #%d → #%d  (sim=%.3f, keep_heat=%.1f)",
                      del_id, keep_id, sim,
                      max(rows[i]["heat_score"], rows[j]["heat_score"]))

    return merged


# ── 运行模式 ──

async def run_light(pool, users: list[str]):
    """Light 模式：热度衰减 + 冗余合并"""
    for uid in users:
        log.info("[light] Processing user=%s", uid)
        # 1. 调 reflect API（热度衰减 + 层级迁移）
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{API_BASE}/api/v1/reflect",
                    params={"user_id": uid, "mode": "light"},
                )
                if r.status_code == 200:
                    log.info("  ├─ reflect(light) API OK")
                else:
                    log.warning("  ├─ reflect API returned %s", r.status_code)
        except Exception as e:
            log.error("  ├─ reflect API error: %s", e)

        # 2. 冗余检测
        n = await detect_redundancy(pool, uid)
        if n:
            log.info("  └─ Merged %d redundant memories", n)
        else:
            log.info("  └─ No redundancy found")


async def run_deep(pool, users: list[str]):
    """Deep 模式：热度衰减 + 实体提取 + 冗余合并"""
    for uid in users:
        log.info("[deep] Processing user=%s", uid)
        # 1. 调 reflect(deep) API（热度衰减 + 实体提取）
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    f"{API_BASE}/api/v1/reflect",
                    params={"user_id": uid, "mode": "deep"},
                )
                if r.status_code == 200:
                    log.info("  ├─ reflect(deep) API OK")
                else:
                    log.warning("  ├─ reflect API returned %s", r.status_code)
        except Exception as e:
            log.error("  ├─ reflect API error: %s", e)

        # 2. 冗余检测
        n = await detect_redundancy(pool, uid)
        if n:
            log.info("  └─ Merged %d redundant memories", n)
        else:
            log.info("  └─ No redundancy found")


# ── 入口 ──

async def main():
    parser = argparse.ArgumentParser(description="Mnemosyne Reflector — 定时反思引擎")
    parser.add_argument(
        "--mode",
        choices=["light", "deep"],
        default="light",
        help="light=每小时(热度+冗余), deep=每日(含实体提取)",
    )
    args = parser.parse_args()

    log.info("Reflector starting — mode=%s", args.mode)
    start = datetime.now(timezone.utc)

    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)
    try:
        users = await get_all_users(pool)
        if not users:
            log.info("No users found, nothing to do.")
            return

        log.info("Found %d active user(s)", len(users))

        if args.mode == "light":
            await run_light(pool, users)
        else:
            await run_deep(pool, users)

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        log.info("Reflector completed in %.1fs", elapsed)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
