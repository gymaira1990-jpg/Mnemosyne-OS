#!/usr/bin/env python3
"""
v8.0 · 写入路径 SQL 契约测试（**从 main.py 源码里取出真实 SQL 去跑**）

这一条测试的由来（真实事故，必须记牢）
--------------------------------------
v8.0 部署到生产后，**第一发写入就 500**：
    asyncpg.exceptions.InvalidColumnReferenceError:
    there is no unique or exclusion constraint matching the ON CONFLICT specification

根因：`dedup_fingerprint_key` 是**部分唯一索引**（`WHERE dedup_fingerprint IS NOT NULL`），
而主写入写的是 `ON CONFLICT (dedup_fingerprint)` —— **缺谓词**。
PostgreSQL 的部分索引推断要求谓词显式匹配，否则直接报错。

为什么单测没抓到：既有测试只验证了「索引能拦住重复指纹」（裸 INSERT），
**从没跑过产品代码里那条 INSERT ... ON CONFLICT 语句本身**。
→ 教训：**测了索引 ≠ 测了使用索引的那条 SQL**。
凡"代码里拼出来的 SQL"与"库里建的对象"有耦合，就必须把**真实 SQL**拉出来跑一遍。

本测试的做法：正则从 `main.py` 里抽出那条 INSERT 语句（含谓词），
把占位符绑上值，投到真实测试库执行 —— 源码与索引一旦不匹配，这里立刻红。
"""
import asyncio
import os
import re

import pytest

DSN = os.environ.get("MNEMOSYNE_V8TEST_DSN", "postgresql:///mnemosyne_v8test")
MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


def _extract_insert_sql() -> str:
    """从 main.py 抽真实 INSERT ... ON CONFLICT 语句（拼接相邻字符串字面量）。"""
    src = open(MAIN_PY, encoding="utf-8").read()
    m = re.search(r"('INSERT INTO memories \(.*?RETURNING id',)", src, re.S)
    assert m, "未能从 main.py 抽到 INSERT 语句 —— 结构变了，请同步本测试"
    literals = re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))
    sql = "".join(literals)
    return sql


def _db_ready() -> bool:
    async def probe():
        import asyncpg
        conn = await asyncpg.connect(DSN)
        try:
            return bool(await conn.fetchval(
                "SELECT to_regclass('public.gc_log') IS NOT NULL"))
        finally:
            await conn.close()
    try:
        return asyncio.run(probe())
    except Exception:
        return False


_needs_db = pytest.mark.skipif(not _db_ready(), reason=f"v8.0 测试库不可用: {DSN}")


def _vec() -> str:
    return "[" + ",".join(["0.01"] * 1024) + "]"


async def _sync_seq(conn) -> None:
    """把 memories.id 序列对齐到 max(id)。

    夹具/历史用例会插入**显式 id**，但不会推进序列 ——
    后续不带 id 的 INSERT 就会撞 `memories_pkey`（实测踩到）。
    """
    await conn.execute(
        "SELECT setval(pg_get_serial_sequence('memories','id'), "
        "GREATEST((SELECT COALESCE(max(id),1) FROM memories), 1))")


def test_w1_extracted_sql_is_the_real_one():
    """护栏：抽取逻辑本身要能自证 —— 抽出来必须是 INSERT + ON CONFLICT。"""
    sql = _extract_insert_sql()
    assert "INSERT INTO memories" in sql
    assert "ON CONFLICT" in sql
    assert "dedup_fingerprint" in sql


def test_w2_on_conflict_predicate_matches_partial_index():
    """核心断言：部分唯一索引 → ON CONFLICT 必须带同款谓词。

    这是产线事故的直接回归测试。若有人把谓词删了，这里先红。
    """
    sql = _extract_insert_sql()
    assert re.search(r"ON CONFLICT\s*\(\s*dedup_fingerprint\s*\)\s+WHERE\s+dedup_fingerprint IS NOT NULL",
                     sql), f"ON CONFLICT 缺少部分索引谓词，生产写入会 500：\n{sql}"


@_needs_db
def test_w3_real_sql_runs_and_is_idempotent():
    """把真实 SQL 投到库里跑：首插返回 id，同指纹再插返回空（幂等）。"""
    import asyncpg
    sql = _extract_insert_sql()

    async def go():
        conn = await asyncpg.connect(DSN)
        try:
            await _sync_seq(conn)
            await conn.execute(
                "DELETE FROM memories WHERE user_id='default' AND content LIKE 'W3-%'")
            args = ("default", None, "W3-probe", "knowledge", _vec(), "{}",
                    None, 0.5, 3, 3, "FP-W3-CONTRACT")
            r1 = await conn.fetchrow(sql, *args)
            assert r1 is not None and r1["id"] is not None, "首插必须返回 id"
            r2 = await conn.fetchrow(sql, *args)
            assert r2 is None, "同指纹再插必须被 ON CONFLICT 拦下（返回空）"
            n = await conn.fetchval(
                "SELECT count(*) FROM memories WHERE dedup_fingerprint='FP-W3-CONTRACT'")
            assert n == 1
        finally:
            await conn.execute(
                "DELETE FROM memories WHERE dedup_fingerprint='FP-W3-CONTRACT'")
            await conn.close()
    asyncio.run(go())


@_needs_db
def test_w4_partial_index_leaves_null_fingerprints_alone():
    """部分索引只约束有指纹的行 —— 历史 NULL 行可以多行共存（不回填设计的前提）。"""
    import asyncpg

    async def go():
        conn = await asyncpg.connect(DSN)
        try:
            await _sync_seq(conn)
            await conn.execute("DELETE FROM memories WHERE content LIKE 'W4-%'")
            await conn.executemany(
                "INSERT INTO memories (user_id, content, category) VALUES ('default', $1, 'knowledge')",
                [("W4-a",), ("W4-b",)])
            n = await conn.fetchval(
                "SELECT count(*) FROM memories WHERE content LIKE 'W4-%' AND dedup_fingerprint IS NULL")
            assert n == 2
        finally:
            await conn.execute("DELETE FROM memories WHERE content LIKE 'W4-%'")
            await conn.close()
    asyncio.run(go())
