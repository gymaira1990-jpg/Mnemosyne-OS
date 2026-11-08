#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""labels_to_cases.py —— 把人工裁决变成评测题（2026-11-07）

闭环的最后一段：`/memory-os/label` 记下的裁决，本身就是「query + 正确档号」，
可以直接补进 golden set，用同一把尺子量 —— 这样「问人」不是打扰，是采集。

用法：
    python3 scripts/labels_to_cases.py                    # 打印 JSONL 到 stdout
    python3 scripts/labels_to_cases.py --out evals/labels_cases.jsonl
    python3 scripts/labels_to_cases.py --user default --limit 100

判据（宁可少出题，也不出错题）：
    · 只取「人明确选了某条」的 label（chosen_id 非空）
    · 只取**选了之后验得出来**的：能拿到那条的档号或正文片段，否则 skip
    · 同 query 只保留**最新**一条 —— 人的判断会变，后来的更可信
"""
from __future__ import annotations

import argparse
import asyncio
import json
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


async def run(user: str, limit: int) -> list[dict]:
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (l.query)
                   l.query, l.chosen_no, l.chosen_id, l.created_at,
                   m.archive_no, m.content
              FROM memory_labels l
              LEFT JOIN memories m ON m.id = l.chosen_id
             -- 🔴 必须排除「裁决之后被删掉的记忆」：软删除不走物理删，
             --   FK 的 ON DELETE SET NULL 根本不会触发（2026-11-08 实测 label9）
             --   ⇒ 若不过滤，就会拿一条已删记忆的档号当标准答案，题永远答不对。
             WHERE l.user_id = $1 AND l.chosen_id IS NOT NULL
               AND m.id IS NOT NULL AND m.is_deleted = FALSE
             ORDER BY l.query, l.created_at DESC
             LIMIT $2
            """, user, limit)
    finally:
        await conn.close()

    cases = []
    for r in rows:
        expect: list[str] = []
        if r["archive_no"]:
            expect.append(r["archive_no"])
        elif r["chosen_no"]:
            expect.append(r["chosen_no"])
        elif r["content"]:
            expect.append(r["content"][:24].replace("\n", " "))
        if not expect:
            continue                      # 拿不到可判定的锚点，宁可不出题
        cases.append({"q": r["query"], "expect": expect, "note": "来自人工裁决"})
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description="人工裁决 → 评测用例")
    ap.add_argument("--user", default="default")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    cases = asyncio.run(run(a.user, a.limit))
    body = "\n".join(json.dumps(c, ensure_ascii=False) for c in cases)
    if a.out:
        Path(a.out).write_text(body + ("\n" if body else ""), encoding="utf-8")
        print(f"✅ 导出 {len(cases)} 条 → {a.out}", file=sys.stderr)
    else:
        print(body)
    return 0 if cases else 1


if __name__ == "__main__":
    sys.exit(main())
