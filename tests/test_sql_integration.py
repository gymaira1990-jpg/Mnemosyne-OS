"""
test_sql_integration.py — 真 SQL 集成测试 (v7.8 补齐, 2026-08-18)

痛点: 原测试 190 个全 mock 单元测试, SQL 语法/逻辑错误(如 drawer_pipeline dedup
JSON 拼接崩溃)永远测不出来。本文件连真实 PostgreSQL(mnemosyne_itest 库)执行生产 SQL。

运行前提: 本地 PG 已建 mnemosyne_itest 库
    psql -d mnemosyne_itest: CREATE EXTENSION vector + memories/memory_keywords 表
无库时自动 skip。

覆盖:
1. dedup 合并 SQL(修复后 jsonb_build_object 语法)端到端 + merged_from 追加链
2. 旧拼接语法(修复前)必须报错 — 防回归(:: 优先级 > ||)
3. 主搜索真 BM25 子查询(命中分数 + ANY 参数)
4. BM25 无命中返回 0(不破坏向量排序)
5. reflect 变化过滤(IS DISTINCT FROM 不更新未变行)
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager

import pytest

import asyncpg

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")


@asynccontextmanager
async def _conn():
    """每测试独立连接(同一事件循环内使用, 避免跨 loop 归属错误)"""
    c = await asyncpg.connect(ITEST_DSN)
    try:
        yield c
    finally:
        await c.close()


def _run(coro):
    """同步包装(项目无 pytest-asyncio, 与纯函数测试风格一致)"""
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def pool():
    """连接本地测试库; 连不上则 skip 全模块。
    注意: 只用它做可用性检查 + 清表(同一 loop 内完成), 每个测试内部自建连接。
    """
    async def _init():
        conn = await asyncpg.connect(ITEST_DSN)
        try:
            await conn.execute("TRUNCATE memories RESTART IDENTITY CASCADE")
        finally:
            await conn.close()

    try:
        _run(_init())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"本地集成测试库不可用: {e}")
    yield True


def test_dedup_merge_sql_works(pool):
    """修复后的合并 SQL: jsonb_build_object 构造 metadata, merged_from 追加, 软删"""
    async def _run_test():
        async with _conn() as conn:
            old_id = await conn.fetchval(
                "INSERT INTO memories (content, category) VALUES ($1,'knowledge') RETURNING id",
                "检查下记忆宫殿是否正常运行的旧记忆")
            new_id = await conn.fetchval(
                "INSERT INTO memories (content, category) VALUES ($1,'knowledge') RETURNING id",
                "重新全面检查记忆宫殿使用情况的记忆")
            # 合并到旧记忆(生产 SQL, 修复后)
            await conn.execute("""
                UPDATE memories SET
                  content = $1,
                  heat_score = $2,
                  access_count = $3,
                  parent_memory_id = COALESCE(parent_memory_id, $4),
                  metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object(
                    'merged_from', COALESCE(metadata->'merged_from','[]'::jsonb) || $5::jsonb),
                  updated_at = NOW()
                WHERE id = $6
            """, "合并后的长内容", 0.9, 2, new_id, "[%d]" % new_id, old_id)
            # 软删新记忆
            await conn.execute("""
                UPDATE memories SET is_deleted = TRUE, forgotten_at = NOW(),
                  metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object('merged_into', $2::int)
                WHERE id = $1
            """, new_id, old_id)
            old = await conn.fetchrow("SELECT metadata, is_deleted FROM memories WHERE id=$1", old_id)
            new = await conn.fetchrow("SELECT metadata, is_deleted FROM memories WHERE id=$1", new_id)
            # asyncpg 读 jsonb 返回 str(技能坑: 需 json.loads)
            old_md = json.loads(old["metadata"])
            new_md = json.loads(new["metadata"])
            assert old["is_deleted"] is False
            assert new["is_deleted"] is True
            assert new_md["merged_into"] == old_id
            assert old_md["merged_from"] == [new_id]
            # 二次合并: merged_from 应追加而非覆盖(保留合并链)
            third = await conn.fetchval(
                "INSERT INTO memories (content, category) VALUES ('第三条相似记忆','knowledge') RETURNING id")
            await conn.execute("""
                UPDATE memories SET
                  content = $1, heat_score = 0.9, access_count = 3,
                  parent_memory_id = COALESCE(parent_memory_id, $2),
                  metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object(
                    'merged_from', COALESCE(metadata->'merged_from','[]'::jsonb) || $3::jsonb),
                  updated_at = NOW()
                WHERE id = $4
            """, "合并后的长内容", third, "[%d]" % third, old_id)
            old2 = await conn.fetchrow("SELECT metadata->'merged_from' AS mf FROM memories WHERE id=$1", old_id)
            mf = json.loads(old2["mf"]) if isinstance(old2["mf"], str) else old2["mf"]
            assert mf == [new_id, third], f"merged_from 应追加保留合并链, 实际 {mf}"
    _run(_run_test())


def test_dedup_old_syntax_raises(pool):
    """修复前的拼接语法 `'...' || x || ']}'::jsonb` 必须报错 — 防回归(:: 优先级 > ||)"""
    async def _run_test():
        async with _conn() as conn:
            mid = await conn.fetchval(
                "INSERT INTO memories (content) VALUES ('回归测试记忆') RETURNING id")
            with pytest.raises(Exception) as exc:
                await conn.execute(
                    "UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || "
                    "'{\"merged_from\":[' || $1::text || ']}'::jsonb WHERE id = $2",
                    "[123]", mid)
            assert "json" in str(exc.value).lower(), f"应报 JSON 语法错误, 实际: {exc.value}"
    _run(_run_test())


def test_bm25_keyword_score(pool):
    """主搜索真 BM25 子查询: memory_keywords SUM(freq) 命中分数"""
    async def _run_test():
        async with _conn() as conn:
            mid = await conn.fetchval(
                "INSERT INTO memories (content, category) VALUES ('代理架构 xray 配置优化','knowledge') RETURNING id")
            await conn.executemany(
                "INSERT INTO memory_keywords (memory_id, token, freq) VALUES ($1,$2,$3)",
                [(mid, "代理", 2.0), (mid, "架构", 1.0), (mid, "xray", 1.0)])
            # 主搜索 bm25_sql 原样(生产 SQL 子查询 + ANY tokens)
            score = await conn.fetchval(
                "SELECT (SELECT LEAST(1.0, COALESCE(SUM(k.freq),0)/4.0) FROM memory_keywords k "
                "WHERE k.memory_id = m.id AND k.token = ANY($2::text[])) "
                "FROM memories m WHERE m.id = $1", mid, ["代理", "架构", "xray"])
            assert score == 1.0, f"命中 3 token sum=4 → LEAST(1.0, 4/4)=1.0, 实际 {score}"
            score2 = await conn.fetchval(
                "SELECT (SELECT LEAST(1.0, COALESCE(SUM(k.freq),0)/4.0) FROM memory_keywords k "
                "WHERE k.memory_id = m.id AND k.token = ANY($2::text[])) "
                "FROM memories m WHERE m.id = $1", mid, ["代理"])
            assert score2 == 0.5, f"命中 1 token freq=2 → 2/4=0.5, 实际 {score2}"
    _run(_run_test())


def test_bm25_no_match_zero(pool):
    """BM25 无命中返回 0(不破坏纯向量排序)"""
    async def _run_test():
        async with _conn() as conn:
            mid = await conn.fetchval(
                "INSERT INTO memories (content) VALUES ('完全无关的测试记忆') RETURNING id")
            score = await conn.fetchval(
                "SELECT (SELECT LEAST(1.0, COALESCE(SUM(k.freq),0)/4.0) FROM memory_keywords k "
                "WHERE k.memory_id = m.id AND k.token = ANY($2::text[])) "
                "FROM memories m WHERE m.id = $1", mid, ["不存在的词", "另一个"])
            assert score == 0.0
    _run(_run_test())


def test_change_filter_noop(pool):
    """reflect 变化过滤: IS DISTINCT FROM 相同值时不更新(避免全表重写)"""
    async def _run_test():
        async with _conn() as conn:
            await conn.fetchval(
                "INSERT INTO memories (content, time_drawer) VALUES ('时间抽屉测试','recent') RETURNING id")
            r = await conn.execute("""
                UPDATE memories SET time_drawer = CASE
                    WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '30 days' THEN 'recent'
                    WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '90 days' THEN 'mid'
                    ELSE 'long'
                END
                WHERE user_id = 'default' AND is_deleted = FALSE
                  AND time_drawer IS DISTINCT FROM (
                    CASE
                      WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '30 days' THEN 'recent'
                      WHEN COALESCE(last_accessed, created_at) > NOW() - INTERVAL '90 days' THEN 'mid'
                      ELSE 'long'
                    END)
            """)
            assert "0" in r, f"值未变不应更新, 实际: {r}"
    _run(_run_test())
