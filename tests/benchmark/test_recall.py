"""时近性与权重：真库执行 + 绑定真源（2026-11-07 重写）

原来这一版是自证，三处病：
1. `sql = "CASE ... THEN 0.15"; assert "0.15" in sql` —— 断言自己刚写下的字符串，改实现照样绿；
2. 权重表是测试里**另抄的一份**（0.40/0.15/0.15/0.15/0.15），与生产（0.50/0.15/0.15/0.10/0.10）不一致，
   却因为断言只要求「和≈1.0」而一直绿 —— 这正是「复制型测试」的典型形态；
3. `test_architecture_has_memory_hierarchy` 只 grep main.py 里有没有 "L1"/"palace" 字样。

现在：权重从 `core/ranking.py` 取（单一真源），时近性表达式**放进 SQL 真跑**，
灌三条 1 天 / 15 天 / 365 天的记忆看算出来的值与排序。

不连库整模块 skip（CI 与本地 `make test-db` 都有全量 schema）。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")
USER = "itest-decay"


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg
    return await asyncpg.connect(ITEST_DSN)


@pytest.fixture(scope="module")
def conn():
    async def probe():
        c = await _connect()
        try:
            return bool(await c.fetchval("SELECT to_regclass('public.memories') IS NOT NULL"))
        finally:
            await c.close()

    try:
        ok = _run(probe())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"测试库不可用: {e}")
    if not ok:
        pytest.skip(f"测试库缺表: {ITEST_DSN}")

    async def seed():
        c = await _connect()
        try:
            await c.execute("DELETE FROM memories WHERE user_id=$1", USER)
            for days, txt in ((1, "一天前"), (15, "十五天前"), (365, "一年前")):
                await c.execute(
                    "INSERT INTO memories (user_id, content, category, created_at) "
                    "VALUES ($1,$2,'knowledge', NOW() - make_interval(days => $3))",
                    USER, txt, days)
        finally:
            await c.close()

    _run(seed())
    yield True


def test_temporal_weights_are_executed_not_asserted(conn):
    """把真源表达式放进 SQL 跑：1 天=0.15，15 天=0.08，365 天=0。"""
    from core.ranking import TEMPORAL_WEIGHT_SQL

    async def go():
        c = await _connect()
        try:
            return await c.fetch(
                "SELECT m.content, " + TEMPORAL_WEIGHT_SQL + " AS w FROM memories m "
                "WHERE m.user_id=$1 ORDER BY w DESC", USER)
        finally:
            await c.close()

    got = {r["content"]: float(r["w"]) for r in _run(go())}
    assert got["一天前"] == pytest.approx(0.15), got
    assert got["十五天前"] == pytest.approx(0.08), got
    assert got["一年前"] == pytest.approx(0.0), got


def test_newer_ranks_above_older(conn):
    """排序判据：内容质量相同时，越新越靠前 —— 这是时近性存在的全部意义。"""
    from core.ranking import TEMPORAL_WEIGHT_SQL

    async def go():
        c = await _connect()
        try:
            return await c.fetch(
                "SELECT m.content FROM memories m WHERE m.user_id=$1 "
                "ORDER BY (" + TEMPORAL_WEIGHT_SQL + ") DESC", USER)
        finally:
            await c.close()

    assert [r["content"] for r in _run(go())] == ["一天前", "十五天前", "一年前"]


def test_weights_sum_to_one():
    """权重和必须为 1.0（绑定真源，不再另抄一份）。"""
    from core.ranking import WEIGHTS
    assert sum(WEIGHTS.values()) == pytest.approx(1.0), WEIGHTS


def test_order_sql_contains_every_dimension():
    """五个维度都得进 ORDER BY —— 用各自的**独有标记**验，别用权重数字（0.15 会重复）。"""
    from core.ranking import build_order_sql
    sql = build_order_sql("bm25_placeholder")
    for marker, dim in (("m.embedding", "语义"),
                        ("bm25_placeholder", "关键词"),
                        ("created_at", "时近"),
                        ("m.reliability", "可信度"),
                        ("m.heat_score", "热度")):
        assert marker in sql, f"{dim} 维没进 ORDER BY: {sql}"
