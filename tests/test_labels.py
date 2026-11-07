"""裁决回写的判据（2026-11-07）

「拿不准就问人」之后必须有回写，否则问完就散了。这里锁三件事：
1. 选中 = 强正信号：heat +0.05（封顶 1.0）、access_count +1；
2. 「都不是」（chosen_id=None）也要落记录 —— 那是「库里没有」的正面证据；
3. 裁决必须限定在自己的 user 里：拿别人的 id 选，不能改别人的热度。
"""
import asyncio
import os

import pytest

ITEST_DSN = os.environ.get("MNEMOSYNE_ITEST_DSN", "postgresql:///mnemosyne_itest")
USER = "itest-label"


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
            return bool(await c.fetchval("SELECT to_regclass('public.memory_labels') IS NOT NULL"))
        finally:
            await c.close()

    try:
        ok = _run(probe())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"测试库不可用: {e}")
    if not ok:
        pytest.skip("测试库缺 memory_labels 表（先跑 docs/migrations/v9.0.24_memory_labels.sql）")

    async def seed():
        c = await _connect()
        try:
            await c.execute("DELETE FROM memory_labels WHERE user_id LIKE 'itest-%'")
            await c.execute("DELETE FROM memories WHERE user_id LIKE 'itest-%'")
            await c.execute(
                "INSERT INTO memories (user_id, content, category, heat_score, access_count) "
                "VALUES ($1,$2,'knowledge',0.5,0)", USER, "[结果卡] 档号：K·IT·L1 候选一")
            await c.execute(
                "INSERT INTO memories (user_id, content, category, heat_score, access_count) "
                "VALUES ($1,$2,'knowledge',0.5,0)", "itest-other", "[结果卡] 档号：K·IT·L2 别人的卡")
        finally:
            await c.close()

    _run(seed())
    yield True


def _label(payload):
    import asyncpg
    from api import memory_os

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            memory_os.pool = pool
            return await memory_os.record_label(memory_os.LabelIn(**payload))
        finally:
            await pool.close()

    return _run(go())


def _state(uid):
    async def go():
        c = await _connect()
        try:
            return await c.fetchrow(
                "SELECT heat_score, access_count FROM memories WHERE user_id=$1 ORDER BY id DESC LIMIT 1",
                uid)
        finally:
            await c.close()

    return _run(go())


def _mid(uid):
    async def go():
        c = await _connect()
        try:
            return await c.fetchval("SELECT id FROM memories WHERE user_id=$1 ORDER BY id DESC LIMIT 1", uid)
        finally:
            await c.close()

    return _run(go())


def test_chosen_raises_heat_and_access(db):
    mid = _mid(USER)
    before = _state(USER)
    res = _label({"user_id": USER, "query": "候选一是哪条", "chosen_id": mid,
                  "candidates": [{"id": mid, "no": "K·IT·L1", "score": 40}]})
    after = _state(USER)
    assert res["heat_bumped"] is True
    assert after["heat_score"] == pytest.approx(float(before["heat_score"]) + 0.05, abs=1e-6)
    assert after["access_count"] == (before["access_count"] or 0) + 1


def test_none_choice_is_recorded_without_bumping(db):
    before = _state(USER)
    res = _label({"user_id": USER, "query": "库里没有的问题", "chosen_id": None,
                  "candidates": [{"id": 1, "score": 10}]})
    after = _state(USER)
    assert res["label_id"] > 0
    assert res["heat_bumped"] is False
    assert after["heat_score"] == before["heat_score"]


def test_cannot_bump_other_users_memory(db):
    other_mid = _mid("itest-other")
    before = _state("itest-other")
    res = _label({"user_id": USER, "query": "越权尝试", "chosen_id": other_mid})
    after = _state("itest-other")
    assert res["heat_bumped"] is False, "拿到别人的 id 也不该改别人热度"
    assert after["heat_score"] == before["heat_score"]


def test_label_can_be_exported_as_case(db):
    """裁决就是天然的评测题：query + 正确档号。"""
    import asyncpg
    from api import memory_os

    async def go():
        pool = await asyncpg.create_pool(ITEST_DSN, min_size=1, max_size=2)
        try:
            memory_os.pool = pool
            return await memory_os.list_labels(USER, 5)
        finally:
            await pool.close()

    out = _run(go())
    assert out["count"] >= 1
    assert any(lab["chosen_no"] == "K·IT·L1" for lab in out["labels"]), out["labels"]


# ── 冲突裁决（2026-11-07 加）：动的是 reliability，不是 heat ──

def _rel(uid):
    async def go():
        c = await _connect()
        try:
            return await c.fetchrow(
                "SELECT reliability, heat_score FROM memories WHERE user_id=$1 ORDER BY id DESC LIMIT 1",
                uid)
        finally:
            await c.close()
    return _run(go())


def test_conflict_verdict_moves_reliability_not_heat(db):
    """冲突裁决表达的是「对不对」，所以动 reliability；heat 是使用频率，不动。"""
    mid = _mid(USER)
    before = _rel(USER)
    res = _label({"user_id": USER, "query": "备份保留几份", "chosen_id": mid,
                  "source": "conflict", "candidates": [{"id": mid, "no": "K·IT·L1"}]})
    after = _rel(USER)
    assert res["heat_bumped"] is True
    assert after["reliability"] == pytest.approx(float(before["reliability"]) + 0.10, abs=1e-6)
    assert after["heat_score"] == before["heat_score"], "conflict 裁决不该改热度"


def test_rejected_card_loses_reliability(db):
    mid = _mid(USER)
    before = _rel(USER)
    res = _label({"user_id": USER, "query": "哪个值对", "source": "conflict",
                  "rejected_ids": [mid]})
    after = _rel(USER)
    assert res["adjusted"]["rejected"]["rows"] == 1
    assert after["reliability"] == pytest.approx(float(before["reliability"]) - 0.10, abs=1e-6)


def test_reliability_has_floor(db):
    """连否十次也不能把可信度压成负数 —— 下限 0。"""
    mid = _mid(USER)
    for _ in range(12):
        _label({"user_id": USER, "query": "反复否决", "source": "conflict",
                "rejected_ids": [mid]})
    assert float(_rel(USER)["reliability"]) >= 0.0
