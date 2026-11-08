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

    ok = False
    try:
        ok = _run(probe())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"测试库不可用: {e}")
    # 🔴 缺表必须**失败**，不许 skip：schema.sql 本来就该建这张表，
    # 缺了就说明「从零建库」路径是坏的（CI 正是这么建库的）。
    # 以前这里写 skip ⇒ 表没建也全绿，等于测试没跑（2026-11-07 自检发现）。
    assert ok, ("docs/schema.sql 必须建 memory_labels 表；"
                "缺它说明从零建库路径坏了（CI 会一起绿着错）")

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
    """越权选别人的卡：**明确拒绝（400）**，而不是静默不动。

    2026-11-07 自检改的：静默不动的坏处是调用方以为写成功了，
    而这里「什么都没发生」和「写失败」长得一模一样。拒绝更诚实。
    """
    from fastapi import HTTPException
    other_mid = _mid("itest-other")
    before = _state("itest-other")
    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "越权尝试", "chosen_id": other_mid})
    assert e.value.status_code == 400
    after = _state("itest-other")
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


def test_label_rejects_forged_selected_no(db):
    """伪造档号必须被拒（2026-11-08 DSH 审计 P0-2，已核实）。

    档号会经 labels_to_cases 变成**评测标准答案** ⇒ 客户端给什么就落什么，
    等于允许污染自己的尺子。现在一律以库为准，不一致就 400。
    """
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "伪造档号尝试",
                "chosen_id": _mid(USER), "selected_no": "K·FAKE·9999"})
    assert e.value.status_code == 400
    assert "不一致" in str(e.value.detail) or "不存在" in str(e.value.detail)


def test_label_rejects_selected_no_without_id(db):
    """只给一个库里不存在的档号、不给 id —— 也必须拒，不许凭空写裁决。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "凭空档号", "selected_no": "K·NOTHING·0000"})
    assert e.value.status_code == 400


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


# ── 脏输入（2026-11-07 自检发现：这三条原本都会 500）──

def test_empty_query_rejected(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "   ", "chosen_id": None})
    assert e.value.status_code == 400


def test_unknown_chosen_id_rejected_not_500(db):
    """前端缓存过期会提交已经不存在的卡 —— 该给 400，不该 500（500 等于「系统挂了」）。"""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "不存在的卡", "chosen_id": 999999999})
    assert e.value.status_code == 400


def test_other_users_chosen_id_rejected(db):
    from fastapi import HTTPException
    other = _mid("itest-other")
    with pytest.raises(HTTPException) as e:
        _label({"user_id": USER, "query": "越权选卡", "chosen_id": other})
    assert e.value.status_code == 400


def test_rejected_ids_of_other_users_are_dropped_not_fatal(db):
    """别人的 id 混进 rejected_ids：丢掉，不炸，也不该动别人的卡。"""
    other = _mid("itest-other")
    before = _state("itest-other")
    res = _label({"user_id": USER, "query": "混合越权", "chosen_id": None,
                  "rejected_ids": [other]})
    after = _state("itest-other")
    assert res["adjusted"] == {} or res.get("adjusted", {}).get("rejected") is None
    assert after["heat_score"] == before["heat_score"]
