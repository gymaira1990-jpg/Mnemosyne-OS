"""stage_dedup 批处理循环 — 契约测试（issue T-0414 补）

为什么必须有这组测试
--------------------
2026-09-28 的生产修复（T-0199，2026-10-14 回流为 `93d581b`）：原来 `stage_dedup` 一轮只处理
`DEDUP_BATCH=30` 条，而 distill/factextract 每天新增 500+ 条 ⇒ **去重队列永远追不上**。
修复把单批逻辑抽成 `_dedup_one_batch`，外层改成循环，靠**三个出口**停机：

    · 队列清空（某批候选 < DEDUP_BATCH）
    · 达 DEDUP_MAX_BATCHES（防止队列长期积压时一轮吃掉太多）
    · 超 DEDUP_TIME_BUDGET_S（防止跑爆，cron 03:35 起跑要留余量）

这段控制流此前**零自动化覆盖**（`tests/test_drawer_v71.py` 只测抽屉边界与遗忘规则），
唯一证据是生产日志（`/tmp/drawer_pipeline.log`：`本轮 7 批, 共合并 22 条, 用时 16.1s`）
⇒ 谁把它改坏（改成死循环、或退回单批）都不会被发现。本组测试把三个出口变成可证伪断言。

覆盖
----
  E1 队列清空 → 立即停，不多跑一批
  E2 满批场景 → 跑满 DEDUP_MAX_BATCHES 后停（**同时是反证点**：旧「单批」实现下必红）
  E3 时间预算耗尽 → 一批都不跑就停
  E4 累计合并数正确 + pool 原样透传
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def dp():
    """加载被测模块（drawer_pipeline 会 `from tmt.distill import ...`，故需 ROOT 在 sys.path）"""
    if importlib.util.find_spec("asyncpg") is None:
        pytest.skip("asyncpg 未安装 —— 见 requirements.txt")
    spec = importlib.util.spec_from_file_location("dp_under_test", ROOT / "drawer_pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_batches(dp, monkeypatch):
    """把 `_dedup_one_batch` 换成可编程假件；返回 (calls, set_plan)"""
    state = {"calls": [], "plan": []}

    async def fake(pool):
        i = len(state["calls"])
        n, m = state["plan"][i] if i < len(state["plan"]) else state["plan"][-1]
        state["calls"].append({"pool": pool, "n": n, "m": m})
        return n, m

    monkeypatch.setattr(dp, "_dedup_one_batch", fake)
    return state["calls"], lambda plan: state.update(plan=plan)


# ── E1 队列清空 ────────────────────────────────────────────────────────────
def test_e1_queue_empty_stops_immediately(dp, fake_batches):
    """首批就不足一批 ⇒ 必须立刻停（不能多跑）"""
    calls, set_plan = fake_batches
    set_plan([(5, 2)])
    got = asyncio.run(dp.stage_dedup(object()))
    assert len(calls) == 1, "候选不足一批就代表队列已清空，不该再多跑"
    assert got == 2


def test_e1b_stops_on_the_batch_that_drains(dp, fake_batches):
    """前两批满、第三批不足 ⇒ 停在第三批"""
    calls, set_plan = fake_batches
    set_plan([(dp.DEDUP_BATCH, 1), (dp.DEDUP_BATCH, 1), (7, 3)])
    got = asyncio.run(dp.stage_dedup(object()))
    assert len(calls) == 3
    assert got == 5


# ── E2 批数上限（★反证点）─────────────────────────────────────────────────
def test_e2_stops_at_max_batches(dp, fake_batches, monkeypatch):
    """每批都满 ⇒ 必须停在 DEDUP_MAX_BATCHES，且**确实跑了多批**。

    ★ 这就是反证点：旧「单批」实现下 calls 长度恒为 1，本断言立刻红 ——
      所以它真能抓住「有人把循环改回单批」这种退化。
    """
    monkeypatch.setattr(dp, "DEDUP_MAX_BATCHES", 4)
    calls, set_plan = fake_batches
    set_plan([(dp.DEDUP_BATCH, 1)])          # 恒满批
    got = asyncio.run(dp.stage_dedup(object()))
    assert len(calls) == 4, "满批场景必须跑满上限（旧单批实现下这里会是 1 ⇒ 红）"
    assert len(calls) > 1, "必须是『循环』：多批处理是这个修复的全部意义"
    assert got == 4


# ── E3 时间预算 ────────────────────────────────────────────────────────────
def test_e3_time_budget_exhausted_runs_zero_batches(dp, fake_batches, monkeypatch):
    """预算已耗尽 ⇒ 一批都不跑就停（护栏优先于产出）"""
    monkeypatch.setattr(dp, "DEDUP_TIME_BUDGET_S", -1)   # 必然「超预算」
    calls, set_plan = fake_batches
    set_plan([(dp.DEDUP_BATCH, 9)])
    got = asyncio.run(dp.stage_dedup(object()))
    assert calls == [], "预算耗尽时必须连第一批都不跑"
    assert got == 0


# ── E4 累计与透传 ──────────────────────────────────────────────────────────
def test_e4_accumulates_merged_and_passes_pool(dp, fake_batches, monkeypatch):
    monkeypatch.setattr(dp, "DEDUP_MAX_BATCHES", 10)
    calls, set_plan = fake_batches
    set_plan([(30, 2), (30, 3), (6, 1)])
    sentinel = object()
    got = asyncio.run(dp.stage_dedup(sentinel))
    assert got == 6, "返回值必须是各批合并数之和（生产日志靠它报『共合并 N 条』）"
    assert len(calls) == 3
    assert all(c["pool"] is sentinel for c in calls), "pool 必须原样透传给每批"
