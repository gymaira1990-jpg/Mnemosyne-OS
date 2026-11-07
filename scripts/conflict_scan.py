#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_scan.py —— 在真实记忆里扫数字级冲突（2026-11-07）

为什么需要它：「前段说 A、回捞说 B，该信谁」这条裁决规则，没有真实样本就只能拍脑袋。
先扫出真实冲突，再定规则。

用法：
    python3 scripts/conflict_scan.py --user default --limit 3000
    python3 scripts/conflict_scan.py --user default --limit 3000 --show 5

判据见 core/conflict.py（同单位 + 语境高度重合 + 数值不同 ⇒ 疑似冲突）。
只读，不写库。输出默认只给**计数与档号**，正文片段要 --show 才打印。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.conflict import MIN_COMMON_RUN, MIN_CTX_OVERLAP, detect_conflicts  # noqa: E402


async def connect():
    import asyncpg
    return await asyncpg.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        database=os.getenv("PGDATABASE", "mnemosyne"),
    )


async def run(user: str, limit: int, min_overlap: float, min_run: int) -> list[tuple[dict, list[dict]]]:
    conn = await connect()
    try:
        rows = await conn.fetch(
            """SELECT id, archive_no, left(content, 400) AS head, category
                 FROM memories
                WHERE user_id = $1 AND is_deleted = false AND content LIKE '[结果卡]%'
                ORDER BY id DESC LIMIT $2""", user, limit)
    finally:
        await conn.close()

    # 按 category 分桶比对：跨类别的数字（比如「3 天」在部署和日记里各说一次）多半不是冲突
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(r["category"] or "-", []).append(
            {"no": r["archive_no"] or r["id"], "head": r["head"]})

    out = []
    for cat, items in buckets.items():
        cs = detect_conflicts(items, min_overlap=min_overlap, min_run=min_run)
        if cs:
            out.append(({"category": cat, "cards": len(items), "pairs": len(cs)}, cs))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="扫描记忆里的数字级冲突（只读）")
    ap.add_argument("--user", default="default")
    ap.add_argument("--limit", type=int, default=3000)
    ap.add_argument("--show", type=int, default=0, help="打印前 N 对（含正文片段，注意隐私）")
    ap.add_argument("--min-overlap", type=float, default=MIN_CTX_OVERLAP)
    ap.add_argument("--min-run", type=int, default=MIN_COMMON_RUN)
    a = ap.parse_args()

    results = asyncio.run(run(a.user, a.limit, a.min_overlap, a.min_run))
    total = sum(b["pairs"] for b, _ in results)
    print(f"user={a.user} limit={a.limit} ⇒ 命中 {len(results)} 个分类，疑似冲突 {total} 对")
    for stat, cs in results:
        print(f"  [{stat['category']}] {stat['cards']} 张卡 → {stat['pairs']} 对")
    for _stat, cs in results:
        for c in cs[:a.show]:
            print(f"    {c['a']['key']}: …{c['a']['raw']}…  ||  {c['b']['key']}: …{c['b']['raw']}…"
                  f"  (语境重合 {c['context_overlap']})")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
