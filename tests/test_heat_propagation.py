"""
test_heat_propagation.py — 热度传播公式 4 用例
"""
import pytest
import sys
sys.path.insert(0, ".")

from tmt.router import compute_parent_heat


def test_heat_uniform():
    """三个子节点均匀热度 → parent = max*0.6 + mean*0.3 + bonus*0.1"""
    result = compute_parent_heat([0.8, 0.8, 0.8])
    # max=0.8, mean=0.8, variance=0, bonus = max(0, 0.2-0) = 0.2
    expected = 0.8 * 0.6 + 0.8 * 0.3 + 0.2 * 0.1
    assert abs(result - expected) < 0.001, f"expected {expected}, got {result}"


def test_heat_varied():
    """子节点热度差异大 (0.9, 0.1, 0.1)"""
    result = compute_parent_heat([0.9, 0.1, 0.1])
    max_h = 0.9
    mean_h = (0.9 + 0.1 + 0.1) / 3  # 0.3667
    variance = ((0.9-mean_h)**2 + (0.1-mean_h)**2 + (0.1-mean_h)**2) / 3
    bonus = max(0, 0.2 - variance * 2)
    expected = min(1.0, max(0.0, max_h * 0.6 + mean_h * 0.3 + bonus * 0.1))
    assert abs(result - expected) < 0.001, f"expected {expected}, got {result}"


def test_heat_all_zero():
    """全零热度 → parent 非零但很低"""
    result = compute_parent_heat([0.0, 0.0, 0.0])
    # max=0, mean=0, variance=0, bonus=0.2
    expected = 0.02  # 0*0.6 + 0*0.3 + 0.2*0.1
    assert abs(result - expected) < 0.001


def test_heat_all_one():
    """全 1.0 热度 → parent = 1.0"""
    result = compute_parent_heat([1.0, 1.0, 1.0])
    # max=1.0, mean=1.0, variance=0, bonus=0.2
    expected = 1.0 * 0.6 + 1.0 * 0.3 + 0.2 * 0.1
    assert abs(result - expected) < 0.001


def test_heat_empty_list():
    """空列表 → 默认 0.5"""
    assert compute_parent_heat([]) == 0.5


def test_heat_single_child():
    """单个子节点 → max=mean=该值"""
    result = compute_parent_heat([0.7])
    # max=0.7, mean=0.7, variance=0, bonus=0.2
    expected = 0.7 * 0.6 + 0.7 * 0.3 + 0.2 * 0.1
    assert abs(result - expected) < 0.001
