#!/usr/bin/env python3
"""
Mnemosyne OS v8.0 · 记忆回收作业 (GC / compaction)
==================================================

问题（实测 2026-09-25）: 全仓无 `DELETE FROM memories`、无 `VACUUM`
  → 软删(is_deleted=TRUE) 即终点, tombstone 永久堆积, 表只增不减。
  文件系统对照: 只有 unlink(目录项消失), 没有 GC(空间真正归还)。

本作业补上 tombstone → purged 这一环, 并保证**不可能误删**:

安全设计（五道闸）
  闸1 窗口   : 只处理 COALESCE(forgotten_at, updated_at, created_at) 早于 N 天前的行
  闸2 保护位 : tome_cards.retention='permanent' 或 metadata->>'pinned'='true' → 永不回收
  闸3 引用   : 被 beliefs.evidence_memories[] 引用, 或被存活子记忆 parent_memory_id 引用 → 拒绝回收
  闸4 归档   : 删除前把整行 + traces 快照写进 memories_archive (可整批还原)
  闸5 凭证   : 删除前导出 CSV 回滚凭证, 路径记入 gc_log

默认 **干跑**(--dry-run)。真正删除必须显式 --apply。

用法:
  python3 jobs/compaction.py                          # 干跑, 窗口 30 天
  python3 jobs/compaction.py --window-days 90         # 干跑, 窗口 90 天
  python3 jobs/compaction.py --apply                  # 真删(设旗后才能跑)
  python3 jobs/compaction.py --apply --vacuum         # 真删 + VACUUM(ANALYZE)
  python3 jobs/compaction.py --restore BATCH-xxxx     # 从归档整批还原

退出码: 0 正常 / 2 参数或安全检查失败 / 3 数据库错误
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone

try:
    import asyncpg
except ImportError:  # pragma: no cover
    print("需要 asyncpg（在项目 venv 里运行）", file=sys.stderr)
    sys.exit(2)

DEFAULT_WINDOW_DAYS = 30
DEFAULT_REFUSE_TIER = ("L4",)


def dsn_from_env() -> str:
    user = os.getenv("PGUSER", "postgres")
    pwd = os.getenv("PGPASSWORD", "")
    db = os.getenv("PGDATABASE", "mnemosyne")
    host = os.getenv("PGHOST", "127.0.0.1")
    port = os.getenv("PGPORT", "5432")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


# ─────────────────────────────────────────────────────────────────────────────
# 候选选择 + 五道闸
# ─────────────────────────────────────────────────────────────────────────────
CANDIDATES_SQL = """
WITH cand AS (
    SELECT m.id,
           COALESCE(m.forgotten_at, m.updated_at, m.created_at) AS tomb_at
    FROM memories m
    WHERE m.is_deleted = TRUE
      AND COALESCE(m.forgotten_at, m.updated_at, m.created_at)
          < NOW() - make_interval(days => $1)
    ORDER BY tomb_at ASC
    LIMIT $2
)
SELECT c.id,
       c.tomb_at,
       -- 闸2 保护位
       EXISTS (SELECT 1 FROM tome_cards tc
               WHERE tc.memory_id = c.id AND tc.retention = 'permanent') AS is_permanent,
       COALESCE(m.metadata->>'pinned', 'false') = 'true'               AS is_pinned,
       -- 闸3 引用完整性
       (SELECT count(*) FROM beliefs b WHERE c.id = ANY(b.evidence_memories)) AS belief_refs,
       (SELECT count(*) FROM memories ch
        WHERE ch.parent_memory_id = c.id AND ch.is_deleted = FALSE)            AS child_refs,
       (SELECT count(*) FROM memory_traces t WHERE t.memory_id = c.id)         AS trace_rows
FROM cand c JOIN memories m ON m.id = c.id
"""


async def select_batch(conn, window_days: int, limit: int):
    rows = await conn.fetch(CANDIDATES_SQL, window_days, limit)
    purge, refused = [], []
    for r in rows:
        if r["is_permanent"] or r["is_pinned"] or r["belief_refs"] > 0 or r["child_refs"] > 0:
            refused.append(r)
        else:
            purge.append(r)
    return purge, refused


# ─────────────────────────────────────────────────────────────────────────────
# 归档 / 还原
# ─────────────────────────────────────────────────────────────────────────────
async def table_columns(conn, table: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position", table)
    return [r["column_name"] for r in rows]


async def archive_columns(conn) -> list[str]:
    return await table_columns(conn, "memories")


async def do_archive(conn, ids: list[int], batch: str) -> int:
    """把整行 + **四张子表**快照写进 memories_archive。返回归档行数。

    ⚠️ v8.0.1 补正（实测缺陷）：原来只抓 memories + traces，漏了
    memory_entities / memory_keywords / tome_cards —— 这三张表都是
    ON DELETE CASCADE，会被静默连带删除，而 --restore 又不重建它们，
    结果还原出来是「僵尸记忆」（在库里但 BM25 搜不到、无著录卡片）。
    """
    cols = await archive_columns(conn)
    collist = ", ".join(cols)
    sql = (
        f"INSERT INTO memories_archive ({collist}, _archived_at, _archive_batch, "
        f"                                 _traces, _entities, _keywords, _tome_cards) "
        f"SELECT m.*, NOW(), $2, "
        f"  COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM memory_traces   t WHERE t.memory_id = m.id), '[]'::jsonb), "
        f"  COALESCE((SELECT jsonb_agg(to_jsonb(e)) FROM memory_entities e WHERE e.memory_id = m.id), '[]'::jsonb), "
        f"  COALESCE((SELECT jsonb_agg(to_jsonb(k)) FROM memory_keywords k WHERE k.memory_id = m.id), '[]'::jsonb), "
        f"  COALESCE((SELECT jsonb_agg(to_jsonb(c)) FROM tome_cards      c WHERE c.memory_id = m.id), '[]'::jsonb) "
        f"FROM memories m WHERE m.id = ANY($1::bigint[])"
    )
    status = await conn.execute(sql, ids, batch)
    return int(status.split()[-1]) if status else 0


async def write_csv_voucher(conn, ids: list[int], path: str) -> int:
    """回滚凭证: 删除前的完整行快照, CSV 格式（用 csv 模块写, 字段含换行也安全）。"""
    rows = await conn.fetch("SELECT * FROM memories WHERE id = ANY($1::bigint[])", ids)
    if not rows:
        return 0
    fields = list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v, default=str, ensure_ascii=False)
                            if isinstance(v, (list, dict)) else v) for k, v in dict(r).items()})
    # 行数用解析器数（不是 wc -l —— 字段含换行会数错）
    with open(path, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


# ─────────────────────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────────────────────
async def run(args) -> int:
    conn = await asyncpg.connect(args.dsn)
    try:
        if args.restore:
            return await do_restore(conn, args.restore)

        batch = args.batch or f"GC-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        purge, refused = await select_batch(conn, args.window_days, args.limit)

        summary = {
            "batch": batch,
            "dry_run": not args.apply,
            "window_days": args.window_days,
            "candidates": len(purge) + len(refused),
            "purgeable": len(purge),
            "refused_by_ref": len(refused),
            "traces_to_archive": sum(r["trace_rows"] for r in purge),
        }

        if not purge:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print("\n无候选 → 无需回收")
            await _log(conn, batch, not args.apply, summary, 0, csv_path=None)
            return 0

        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\n将被回收（前 10 条）:")
        for r in purge[:10]:
            print(f"  #{r['id']}  tomb={r['tomb_at']:%Y-%m-%d}  traces={r['trace_rows']}")
        if refused:
            print(f"\n因仍被引用/受保护而**拒绝回收** {len(refused)} 条（前 5）:")
            for r in refused[:5]:
                why = []
                if r["is_permanent"]:
                    why.append("permanent")
                if r["is_pinned"]:
                    why.append("pinned")
                if r["belief_refs"]:
                    why.append(f"belief×{r['belief_refs']}")
                if r["child_refs"]:
                    why.append(f"livechild×{r['child_refs']}")
                print(f"  #{r['id']}  理由: {', '.join(why) or '未知'}")

        if not args.apply:
            print("\n[干跑] 未做任何更改。加 --apply 才真删。")
            await _log(conn, batch, True, summary, 0, csv_path=None)
            return 0

        # ── 真删（闸4 归档 → 闸5 凭证 → 删除），全过程单事务 ──
        ids = [r["id"] for r in purge]
        csv_path = args.csv or os.path.join(
            os.path.expanduser("~"), ".hermes", "reports", "gc", f"{batch}.csv")

        async with conn.transaction():
            archived = await do_archive(conn, ids, batch)
            if archived != len(ids):
                raise RuntimeError(f"归档行数 {archived} != 待删 {len(ids)} → 中止（宁可不删）")
            vouchered = await write_csv_voucher(conn, ids, csv_path)
            if vouchered != len(ids):
                raise RuntimeError(f"凭证行数 {vouchered} != 待删 {len(ids)} → 中止（宁可不删）")
            status = await conn.execute("DELETE FROM memories WHERE id = ANY($1::bigint[])", ids)
            deleted = int(status.split()[-1]) if status else 0

        vacuum_msg = "跳过"
        if args.vacuum:
            # VACUUM 不能在事务块里跑；asyncpg 默认 autocommit, 所以放在事务外
            await conn.execute("VACUUM (ANALYZE) memories")
            await conn.execute("VACUUM (ANALYZE) memory_traces")
            vacuum_msg = "已完成 VACUUM (ANALYZE) memories + memory_traces"

        out = dict(summary, purged=deleted, archived=archived, rollback_csv=csv_path,
                   vacuum=vacuum_msg)
        print("\n" + json.dumps(out, ensure_ascii=False, indent=2))
        await _log(conn, batch, False, summary, deleted,
                   csv_path=csv_path, traces_kept=archived and summary["traces_to_archive"])
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        await conn.close()


async def do_restore(conn, batch: str) -> int:
    """从 memories_archive 整批还原（误删救援）。

    列名一律**动态取 information_schema** —— 不写死。理由（实测教训）：
    `memory_traces` 的时间列是 `executed_at` 而非 `created_at`，写死列名会让
    还原在关键时刻（救援现场）直接报错。
    """
    cols = await archive_columns(conn)
    collist = ", ".join(cols)
    # 四张 CASCADE 子表：(归档列, 目标表, 快照里的主键列)
    CHILDREN = [("_traces", "memory_traces", "id"),
                ("_entities", "memory_entities", None),
                ("_keywords", "memory_keywords", None),
                ("_tome_cards", "tome_cards", None)]

    async def _restore_child(c, col: str, table: str, pk: str | None) -> int:
        tcols = await table_columns(conn, table)
        tlist = ", ".join(tcols)
        conflict = f"ON CONFLICT ({pk}) DO NOTHING " if pk else ""
        return await conn.fetchval(
            f"WITH ins AS ("
            f"  INSERT INTO {table} ({tlist}) "
            f"  SELECT (jsonb_populate_record(NULL::{table}, j)).* "
            f"  FROM memories_archive a, jsonb_array_elements(a.{col}) j "
            f"  WHERE a._archive_batch=$1 {conflict} RETURNING 1) "
            f"SELECT count(*) FROM ins", batch)

    async with conn.transaction():
        n = await conn.fetchval(
            f"WITH ins AS ("
            f"  INSERT INTO memories ({collist}) "
            f"  SELECT {collist} FROM memories_archive WHERE _archive_batch=$1 "
            f"  ON CONFLICT (id) DO NOTHING RETURNING 1) SELECT count(*) FROM ins", batch)
        counts = {}
        for col, table, pk in CHILDREN:
            try:
                counts[table] = await _restore_child(conn, col, table, pk)
            except Exception as e:  # noqa: BLE001
                counts[table] = f"ERR:{type(e).__name__}"

        # ── 完整性断言（v8.0.1 新增）：归档里有的子表记录，还原后必须都有 ──
        #   这是把「假安全」变成不可能的判据：漏还原一张表就报错，而不是给一具僵尸记忆。
        problems = []
        for col, table, _pk in CHILDREN:
            want = await conn.fetchval(
                f"SELECT COALESCE(SUM(jsonb_array_length(a.{col})),0) "
                f"FROM memories_archive a WHERE a._archive_batch=$1", batch)
            got = counts.get(table)
            if want != got:
                problems.append(f"{table}: 归档 {want} 条 → 还原 {got} 条（不一致）")
        if problems:
            raise RuntimeError("还原不完整，已回滚：" + "; ".join(problems))

    print(json.dumps({"restored_memories": n, **counts, "batch": batch,
                      "integrity": "OK（四张子表全部一致）"},
                     ensure_ascii=False, indent=2))
    return 0


async def _log(conn, batch, dry_run, summary, purged, csv_path, traces_kept=None):
    try:
        await conn.execute(
            "INSERT INTO gc_log (batch, dry_run, candidates, purged, refused_ref, traces_kept, rollback_csv) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            batch, dry_run, summary["candidates"], purged, summary["refused_by_ref"],
            traces_kept or 0, csv_path)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ gc_log 写入失败(不影响回收结果): {e}", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description="Mnemosyne OS v8.0 记忆回收作业 (GC)")
    p.add_argument("--apply", action="store_true", help="真正执行删除（默认干跑）")
    p.add_argument("--dry-run", action="store_true",
                   help="显式声明干跑（本就是默认；给门禁脚本一个自解释的写法）")
    p.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                   help=f"软删后多少天才可回收（默认 {DEFAULT_WINDOW_DAYS}）")
    p.add_argument("--limit", type=int, default=500, help="单批上限（默认 500）")
    p.add_argument("--dsn", default=None, help="PG DSN（默认取 PG* 环境变量）")
    p.add_argument("--csv", default=None, help="回滚凭证 CSV 路径")
    p.add_argument("--batch", default=None, help="批次号（默认按时间生成）")
    p.add_argument("--vacuum", action="store_true", help="回收后跑 VACUUM (ANALYZE)")
    p.add_argument("--restore", default=None, metavar="BATCH", help="从归档整批还原")
    args = p.parse_args()
    args.dsn = args.dsn or dsn_from_env()
    if args.window_days < 0:
        print("--window-days 不能为负", file=sys.stderr)
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
