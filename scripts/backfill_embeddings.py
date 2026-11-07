#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_embeddings.py —— 给缺向量的记忆补向量（2026-11-08）

为什么要它：蒸馏路径（`tmt/distill.py`）原来写库不带 embedding，
每天约 55 条「提炼出来的知识」落库后**语义通道搜不到**（BM25 还能中）。
修了写入路径只能防将来，存量得补 —— 这批存量恰恰是最有价值的提炼结果。

特性：
  · 幂等：只挑 embedding 为空的，跑几遍都一样
  · 可限量：--limit（分批跑，别一次打满 API）
  · 可干跑：--dry-run 只报数不写
  · 失败不静默：逐条计数，失败原因打前 3 条，退出码 1

用法：
    python3 scripts/backfill_embeddings.py --limit 50 --dry-run
    python3 scripts/backfill_embeddings.py --limit 500
    python3 scripts/backfill_embeddings.py --all
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def connect():
    import asyncpg
    return await asyncpg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        database=os.getenv("PGDATABASE", "mnemosyne"),
    )


async def run(limit: int | None, dry_run: bool, batch: int = 16) -> int:
    from core.embedding import get_embedding
    import asyncpg

    conn = await connect()
    try:
        total = await conn.fetchval(
            "SELECT count(*) FROM memories WHERE is_deleted=false "
            "AND coalesce(array_length(embedding::real[],1),0)=0")
        print(f"待补向量：{total} 条")
        if dry_run:
            rows = await conn.fetch(
                "SELECT category, count(*) c FROM memories WHERE is_deleted=false "
                "AND coalesce(array_length(embedding::real[],1),0)=0 GROUP BY 1 ORDER BY 2 DESC")
            for r in rows:
                print(f"  {r['category']:12s} {r['c']}")
            return 0

        done = failed = 0
        errors: list[str] = []
        while True:
            if limit is not None and done + failed >= limit:
                break
            take = batch if limit is None else min(batch, limit - done - failed)
            rows = await conn.fetch(
                "SELECT id, content FROM memories WHERE is_deleted=false "
                "AND coalesce(array_length(embedding::real[],1),0)=0 "
                "ORDER BY id DESC LIMIT $1", take)
            if not rows:
                break
            texts = [(r["content"] or "")[:2000] for r in rows]
            try:
                vecs = get_embedding(texts)
            except Exception as e:                       # 整批失败就停，不空转
                print(f"❌ 取向量失败：{e}")
                return 1
            for r, v in zip(rows, vecs):
                vec_str = "[" + ",".join(str(x) for x in v) + "]"
                try:
                    await conn.execute(
                        "UPDATE memories SET embedding = $1::vector WHERE id = $2", vec_str, r["id"])
                    done += 1
                except Exception as e:                   # 单条失败不影响整批
                    failed += 1
                    if len(errors) < 3:
                        errors.append(f"id={r['id']}: {e}")
            print(f"  进度 +{len(rows)}（成功 {done} / 失败 {failed}）", flush=True)
        print(f"\n完成：成功 {done}，失败 {failed}")
        for e in errors:
            print("  ·", e)
        return 0 if failed == 0 else 1
    finally:
        await conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="补记忆向量（幂等、可限量）")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--all", action="store_true", help="补全部（分批直到没有空向量）")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    return asyncio.run(run(None if a.all else a.limit, a.dry_run, a.batch))


if __name__ == "__main__":
    sys.exit(main())
