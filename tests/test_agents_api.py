"""身份卡接口的判据（2026-11-07，T-0678 第 1 步）

要锁住的是**两条都容易漏的行为**：
1. `users` 里没建卡、但写过记忆的 Agent 必须被列出来（`has_card=false`）——
   只用 INNER JOIN 会把缺口吃掉，看上去「人人有卡」。
2. 卡片字段来自 `users.metadata`，值要原样透出（role/status/boundary），不能被丢掉。

不连库整模块 skip（与 test_sql_integration 同风格）。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def db():
    import asyncpg

    async def probe():
        conn = await asyncpg.connect(ITEST_DSN)
        try:
            ok = bool(await conn.fetchval("SELECT to_regclass('public.memories') IS NOT NULL")) and \
                 bool(await conn.fetchval("SELECT to_regclass('public.users') IS NOT NULL"))
        finally:
            await conn.close()
        return ok

    try:
        ok = _run(probe())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"测试库不可用: {e}")
    if not ok:
        pytest.skip(f"测试库缺表: {ITEST_DSN}")

    async def seed():
        conn = await asyncpg.connect(ITEST_DSN)
        try:
            await conn.execute(
                "INSERT INTO users (user_id, name, metadata) VALUES ($1,$2,$3::jsonb) "
                "ON CONFLICT (user_id) DO UPDATE SET metadata = EXCLUDED.metadata",
                "itest-writer", "测试写作员",
                '{"role":"writer","status":"paused","model":"deepseek-flash","boundary":"不改代码"}')
            await conn.execute(
                "INSERT INTO memories (user_id, content, category) VALUES ($1,$2,'knowledge')",
                "itest-ghost", "只写过记忆、没有身份卡的 Agent")   # 故意不在 users 里建卡
        finally:
            await conn.close()

    _run(seed())
    yield True


def _list():
    import asyncpg
    from api import agents as agents_api

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            agents_api.pool = pool
            return await agents_api.list_agents()
        finally:
            await pool.close()

    return _run(go())


def test_agent_without_card_is_listed(db):
    data = _list()
    ids = {a["user_id"]: a for a in data["agents"]}
    assert "itest-ghost" in ids, "只写过记忆的 Agent 必须出现在列表里（FULL OUTER JOIN）"
    assert ids["itest-ghost"]["has_card"] is False


def test_card_fields_pass_through(db):
    data = _list()
    card = next(a for a in data["agents"] if a["user_id"] == "itest-writer")
    assert card["has_card"] is True
    assert card["role"] == "writer"
    assert card["status"] == "paused"
    assert card["boundary"] == "不改代码"
    assert card["memory_count"] >= 0


def test_counts_are_reported(db):
    data = _list()
    assert data["count"] == len(data["agents"])
    assert data["without_card"] >= 1


def test_empty_content_rejected_before_embedding():
    """空内容必须在入口被挡（400），不能送到 embedding API 变 500。

    2026-11-08 边界审计实测：POST /api/v1/memories 空 content →
    embedding 返回 400 → RuntimeError → 调用方看到 500（像服务器故障）。
    """
    import inspect
    import main as app_main
    src = inspect.getsource(app_main.create_memory)
    assert 'content 不能为空' in src, "入口必须显式拒绝空内容"
    assert src.index('content 不能为空') < src.index('get_embedding'), \
        "拒绝必须发生在算向量之前（否则照样打 API）"


def test_nul_byte_rejected_before_db():
    """NUL 字节必须在入口拒绝：PostgreSQL 的 text 存不了 \\x00，走到 asyncpg 就是 500。

    2026-11-08 边界审计实测：content 含 \\x00 → 500 Internal Server Error。
    """
    import inspect
    import main as app_main
    src = inspect.getsource(app_main.create_memory)
    assert "NUL 字节" in src
    assert src.index("NUL 字节") < src.index("get_embedding"), "拒绝必须早于算向量/入库"
