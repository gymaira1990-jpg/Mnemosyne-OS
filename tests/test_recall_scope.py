"""召回必须按 user 隔离（2026-11-07）

为什么单独锁这一条：`/memory-os/recall` 的三个通道（E/C/T）此前**完全不带 user_id**，
在只有一个人用的机器上看不出问题；一旦有第二个 Agent 开始写记忆，
就是「别人的 3 万条把我的答案挤没」——而且不会有任何报错。

判据：两个用户写同样关键词的卡，按 A 查只能出 A 的。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")


def _run(coro):
    return asyncio.run(coro)


async def _connect():
    import asyncpg
    return await asyncpg.connect(ITEST_DSN)


@pytest.fixture(scope="module")
def db():
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
            for uid, txt in (("itest-a", "[结果卡] 档号：K·IT·A 海报配色用 FF9F43 暖橘"),
                             ("itest-b", "[结果卡] 档号：K·IT·B 海报配色用 000000 纯黑")):
                await c.execute("DELETE FROM memories WHERE user_id=$1", uid)
                await c.execute(
                    "INSERT INTO memories (user_id, content, category) VALUES ($1,$2,'knowledge')",
                    uid, txt)
        finally:
            await c.close()

    _run(seed())
    yield True


def _kw(kws, user_id, limit=10):
    """直接调通道函数（端点只是它的壳），避免起一个 HTTP 服务。"""
    import asyncpg
    from api import memory_os

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            memory_os.pool = pool
            return await memory_os._multi_kw(kws, user_id, limit)
        finally:
            await pool.close()

    return _run(go())


def test_keyword_channel_is_user_scoped(db):
    rows = _kw(["海报"], "itest-a")
    assert rows, "A 自己的卡应该被搜到"
    assert all("K·IT·A" in (r.get("head") or "") for r in rows), \
        f"A 查到了别人的卡: {[r.get('head') for r in rows]}"


def test_keyword_channel_does_not_leak_across_users(db):
    rows_a = _kw(["海报"], "itest-a")
    rows_b = _kw(["海报"], "itest-b")
    assert rows_a and rows_b
    assert not ({"K·IT·B"} & {("K·IT·B" if "K·IT·B" in (r.get("head") or "") else "") for r in rows_a})
    assert not any("K·IT·A" in (r.get("head") or "") for r in rows_b)


def test_exact_channel_is_user_scoped(db):
    import asyncpg
    from api import memory_os

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            memory_os.pool = pool
            return await memory_os._exact("K·IT·B", "itest-a", 10)
        finally:
            await pool.close()

    rows = _run(go())
    assert rows == [], f"A 不该查到 B 的档号，实际: {rows}"
