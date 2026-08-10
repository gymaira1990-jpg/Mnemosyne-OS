#!/usr/bin/env python3
"""wiki_dedupe — 图谱边定期去重 (v7.5.1)

AGE 无边索引时 MERGE 可能创建重复 RELATED_TO 边 (2026-08-10 实测 69% 重复)。
wiki_extract 已加查重, 此脚本兜底定期清理历史残留。
GZ cron: 每周一 8am

用法: venv/bin/python wiki_dedupe.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg  # noqa: E402


async def init_age(conn):
    try:
        await conn.execute("LOAD 'age'")
        await conn.execute("SET search_path = ag_catalog, public")
    except Exception:
        pass


async def main():
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2, init=init_age)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM cypher('mnemosyne_graph', $$ "
                "MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity) "
                "RETURN id(r) AS rid, a.entity_id AS aid, r.relation AS rel, b.entity_id AS bid $$) "
                "AS (rid agtype, aid agtype, rel agtype, bid agtype)"
            )
            edges = [(str(r["rid"]).strip('"'), str(r["aid"]).strip('"'),
                      str(r["rel"]).strip('"'), str(r["bid"]).strip('"')) for r in rows]
            seen = set()
            to_delete = []
            for rid, a, rel, b in edges:
                k = (a, rel, b)
                if k in seen:
                    to_delete.append(rid)
                else:
                    seen.add(k)
            if not to_delete:
                print(f"图谱边: {len(edges)} 条, 无重复 ✅")
                return
            for rid in to_delete:
                try:
                    await conn.execute(
                        "SELECT * FROM cypher('mnemosyne_graph', $$ "
                        "MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity) WHERE id(r) = %s DELETE r $$) AS (v agtype)" % rid
                    )
                except Exception as e:
                    print(f"  delete {rid} fail: {str(e)[:80]}")
            print(f"图谱边去重: {len(edges)} → {len(edges) - len(to_delete)} (删 {len(to_delete)} 重复)")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
