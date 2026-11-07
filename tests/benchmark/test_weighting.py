"""热度 + 可信度加权（2026-11-07 重写）

原来有三处是假的：
1. `boost_high = 0.9 * 0.15` 然后断言 `> boost_low` —— 纯算术，测的是 Python 乘法；
2. 注释写「reliability 占 0.15」，而生产实际是 **0.10** —— 抄错了一直没人发现；
3. `test_reliability_heat_synergy` 去 `open("main.py")` grep 字面量 "0.10 * m.reliability"，
   等于把实现焊死在源码排版上：一旦把权重抽成常量（就像现在做的），测试就红 ——
   它护的不是行为，是排版。

现在：`compute_parent_heat` 是真函数照旧测；权重的断言全部绑到 `core/ranking.py`（单一真源）。
"""
import pytest

from tmt.router import compute_parent_heat
from core.ranking import WEIGHTS, build_order_sql


def test_parent_heat_aggregates_children():
    """父节点热度聚合：高热子节点 → 更高父热度。"""
    assert compute_parent_heat([0.9, 0.9, 0.9]) > compute_parent_heat([0.1, 0.1, 0.1])


def test_heat_boundaries():
    """热度值必须落在 0–1。"""
    for hs in ([0.5, 0.5, 0.5], [], [0.0], [1.0, 1.0], ["0.7", None]):
        assert 0.0 <= compute_parent_heat(hs) <= 1.0


def test_parent_heat_type_defensive():
    """脏输入（字符串/None）不能让聚合炸掉 —— 生产里确实会从 JSON 读回字符串。"""
    assert 0.0 <= compute_parent_heat(["0.8", None, 0.4]) <= 1.0


def test_reliability_and_heat_carry_real_weight():
    """可信度与热度必须有非零权重，且真的进了 ORDER BY（不再 grep 源码字面量）。"""
    assert WEIGHTS["reliability"] > 0
    assert WEIGHTS["heat"] > 0
    sql = build_order_sql("0")
    assert "m.reliability" in sql
    assert "m.heat_score" in sql


def test_no_dimension_dominates():
    """没有任何单一维度权重 ≥ 0.6 —— 单一维度碾压会让其余四维形同虚设。"""
    assert max(WEIGHTS.values()) < 0.6, WEIGHTS
    assert sum(WEIGHTS.values()) == pytest.approx(1.0), WEIGHTS
