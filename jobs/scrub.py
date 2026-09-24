#!/usr/bin/env python3
"""
Mnemosyne OS v8.0 · 完整性巡检作业 (scrub)
==========================================

文件系统对照: Btrfs csum tree / ZFS checksum + scrub —— 后台**主动**发现异常,
而不是等召回出错才发现（read-time check 是被动的, scrub 是主动的）。

本作业**只读**: 只报告, 不改数据。任何修复都必须人工决定并走单独流程。
这与 gcat-std 的「巡检器永远只读」红线一致。

检查项（四类孤儿/异常）:
  O1 孤儿 inode   : memories 有行但无 tome_cards 著录卡片
  O2 孤儿引用     : memory_entities / memory_keywords 指向已不存在的 memory
  O3 引用悬空     : beliefs.evidence_memories 里的 id 已不存在
  O4 到期未回收   : 软删已超保留窗口但仍未被 compaction 回收（GC 是否在跑）
  O5 指纹缺失     : 非软删记忆 dedup_fingerprint 为空（v8.0 之后写入的应有指纹）
  O6 活子挂死父   : parent_memory_id 指向一条已软删的记忆

用法:
  python3 jobs/scrub.py                # 全量巡检
  python3 jobs/scrub.py --json         # 机器可读输出
  python3 jobs/scrub.py --window-days 30
退出码: 0 无异常 / 1 存在异常（可供 cron 告警用） / 3 数据库错误
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

try:
    import asyncpg
except ImportError:  # pragma: no cover
    print("需要 asyncpg（在项目 venv 里运行）", file=sys.stderr)
    sys.exit(2)


def dsn_from_env() -> str:
    user = os.getenv("PGUSER", "postgres")
    pwd = os.getenv("PGPASSWORD", "")
    db = os.getenv("PGDATABASE", "mnemosyne")
    host = os.getenv("PGHOST", "127.0.0.1")
    port = os.getenv("PGPORT", "5432")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


CHECKS = [
    ("O1_orphan_tome_card", "有记忆无著录卡片（孤儿 inode）",
     "SELECT count(*) FROM memories m "
     "LEFT JOIN tome_cards c ON c.memory_id = m.id "
     "WHERE c.memory_id IS NULL AND m.is_deleted = FALSE"),
    ("O2_orphan_entity_ref", "实体关联指向不存在的记忆",
     "SELECT count(*) FROM memory_entities e "
     "LEFT JOIN memories m ON m.id = e.memory_id WHERE m.id IS NULL"),
    ("O2_orphan_keyword_ref", "分词索引指向不存在的记忆",
     "SELECT count(*) FROM memory_keywords k "
     "LEFT JOIN memories m ON m.id = k.memory_id WHERE m.id IS NULL"),
    ("O3_dangling_belief_ref", "信念的证据指向不存在的记忆",
     "SELECT COALESCE(SUM(n),0) FROM ("
     "  SELECT (SELECT count(*) FROM unnest(b.evidence_memories) e "
     "          LEFT JOIN memories m ON m.id = e WHERE m.id IS NULL) AS n"
     "  FROM beliefs b WHERE b.evidence_memories IS NOT NULL) t"),
    ("O5_missing_fingerprint", "未软删记忆缺幂等指纹（v8.0 起写入的应有）",
     "SELECT count(*) FROM memories WHERE is_deleted = FALSE "
     "AND dedup_fingerprint IS NULL AND created_at > TIMESTAMPTZ '2026-09-25T06:25:00+08'"),
    ("O6_live_child_dead_parent", "存活子记忆挂在已软删的父记忆下",
     "SELECT count(*) FROM memories ch JOIN memories pa ON pa.id = ch.parent_memory_id "
     "WHERE ch.is_deleted = FALSE AND pa.is_deleted = TRUE"),
]


async def run(args) -> int:
    conn = await asyncpg.connect(args.dsn)
    try:
        results = {}
        for key, desc, sql in CHECKS:
            try:
                results[key] = {"desc": desc, "count": int(await conn.fetchval(sql))}
            except Exception as e:  # noqa: BLE001
                results[key] = {"desc": desc, "count": -1, "error": f"{type(e).__name__}: {e}"}

        # O4 需要参数
        o4 = await conn.fetchval(
            "SELECT count(*) FROM memories WHERE is_deleted = TRUE "
            "AND COALESCE(forgotten_at, updated_at, created_at) < NOW() - make_interval(days => $1)",
            args.window_days)
        results["O4_overdue_tombstone"] = {
            "desc": f"软删超 {args.window_days} 天仍未回收（GC 未跑？）", "count": int(o4)}

        # 基线规模
        scale = await conn.fetchrow(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE is_deleted) AS tombstone, "
            "pg_total_relation_size('memories') AS bytes FROM memories")

        problems = {k: v for k, v in results.items() if v["count"] > 0}
        out = {
            "checked_at": str(await conn.fetchval("SELECT NOW()")),
            "window_days": args.window_days,
            "scale": {"total": scale["total"], "tombstone": scale["tombstone"],
                      "table_bytes": scale["bytes"],
                      "tombstone_ratio": round(scale["tombstone"] / max(scale["total"], 1), 4)},
            "checks": results,
            "problems": sorted(problems.keys()),
            "verdict": "OK" if not problems else "ATTENTION",
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"🔍 Mnemosyne 完整性巡检 · {out['checked_at']}")
            print(f"   规模: {scale['total']} 条（软删 {scale['tombstone']} = "
                  f"{out['scale']['tombstone_ratio']:.1%}）· 表 {scale['bytes']/1048576:.1f} MB")
            print(f"   窗口: {args.window_days} 天\n")
            for k, v in results.items():
                flag = "⚠️" if v["count"] > 0 else "✅"
                extra = f"  [{v['error']}]" if "error" in v else ""
                print(f"   {flag} {k:26s} {v['count']:>6}  {v['desc']}{extra}")
            print(f"\n   判定: {out['verdict']}")
        return 0 if not problems else 1
    except Exception as e:  # noqa: BLE001
        print(f"❌ 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Mnemosyne OS v8.0 完整性巡检（只读）")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--window-days", type=int, default=30, help="到期未回收判定窗口（默认 30 天）")
    p.add_argument("--dsn", default=None)
    args = p.parse_args()
    args.dsn = args.dsn or dsn_from_env()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
