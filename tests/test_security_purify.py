"""净化接口的两条契约（2026-11-07 补）

背景：`POST /api/v1/security/purify` 是不可逆操作（内容被 SHA-256 替换），原来有两个问题：
1. 只按 `memory_id` 定位 ⇒ 多 Agent / 多用户部署下，任何调用方都能净化别人的记忆；
2. `metadata` 用 f-string 拼 jsonb ⇒ `reason` 里一个双引号就让 `$2::jsonb` 抛 22P02（500）。

这两条都**不会**在正常路径暴露：单用户、reason 是普通词时一切正常。所以必须显式锁住。
不连库时整模块 skip（与 test_sql_integration 同风格）。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")


async def _connect():
    import asyncpg
    return await asyncpg.connect(ITEST_DSN)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def ready():
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
    yield True


def _insert(user_id: str, content: str) -> int:
    async def go():
        c = await _connect()
        try:
            return await c.fetchval(
                "INSERT INTO memories (user_id, content, category) VALUES ($1,$2,'knowledge') RETURNING id",
                user_id, content)
        finally:
            await c.close()
    return _run(go())


def _purify(memory_id: int, reason: str, user_id: str):
    from security.purifier import soft_delete_memory

    async def go():
        c = await _connect()
        try:
            return await soft_delete_memory(c, memory_id, reason, user_id)
        finally:
            await c.close()
    return _run(go())


def test_purify_rejects_other_users_memory(ready):
    """净化必须限定在自己的 user 范围内 —— 否则是越权删除。"""
    mid = _insert("alice", "alice 的私有记忆：预算 3000 万")
    res = _purify(mid, "越权尝试", user_id="bob")
    assert "error" in res, f"别人的记忆不该被净化，实际返回: {res}"


def test_purify_same_user_works(ready):
    mid = _insert("alice", "alice 准备被净化的记忆")
    res = _purify(mid, "user_request", user_id="alice")
    assert res.get("status") == "purified", res


def test_purify_reason_with_quotes_does_not_break_jsonb(ready):
    """reason 里带双引号/反斜杠也必须能落库（原来 f-string 拼 jsonb 会 500）。"""
    mid = _insert("default", "reason 里带引号的净化测试")
    weird = '他说 "这条要删掉" \\ 还有反斜杠'
    res = _purify(mid, weird, user_id="default")
    assert res.get("status") == "purified", res

    async def check():
        c = await _connect()
        try:
            return await c.fetchval("SELECT metadata->>'reason' FROM memories WHERE id=$1", mid)
        finally:
            await c.close()

    assert _run(check()) == weird


def test_purify_endpoint_maps_not_found_to_404(monkeypatch):
    """API 层必须把「不属于你/不存在」映射成 404，而不是 200 + {"error": ...}。

    2026-11-08 边界审计实测：越权净化返回 200，调用方会误以为成功了。
    """
    import asyncio

    from fastapi import HTTPException

    import api.security as sec
    import security.purifier as pur

    async def fake(conn, mid, reason, uid):
        return {"error": "Memory not found or already deleted"}

    monkeypatch.setattr(pur, "soft_delete_memory", fake)

    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Ctx()

    sec.pool = _Pool()
    req = sec.DeleteRequest(memory_id=1, reason="probe", user_id="not-mine")
    with pytest.raises(HTTPException) as e:
        asyncio.run(sec.purify_memory(req))
    assert e.value.status_code == 404
