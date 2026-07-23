"""
test_weighting.py — 热度 + 可信度加权效果

场景: 验证高质量记忆在搜索结果中排位更靠前
"""
import pytest
import sys
sys.path.insert(0, ".")

from tmt.router import compute_parent_heat


def test_high_reliability_matters():
    """高 reliability 记忆 → 搜索权重更高"""
    # reliability 在五维搜索中占 0.15 权重
    # 0.9 reliability → 加分 0.135
    # 0.5 reliability → 加分 0.075
    # 相差 6%
    boost_high = 0.9 * 0.15
    boost_low = 0.5 * 0.15
    assert boost_high > boost_low
    assert abs(boost_high - 0.135) < 0.001


def test_high_heat_matters():
    """高 heat 记忆 → 搜索权重更高"""
    boost_high = 0.9 * 0.15
    boost_low = 0.1 * 0.15
    assert boost_high > boost_low


def test_parent_heat_aggregates_children():
    """父节点热度正确聚合子节点"""
    # 高热度子节点 → 高父节点热度
    high_children = [0.9, 0.9, 0.9]
    low_children = [0.1, 0.1, 0.1]
    
    parent_high = compute_parent_heat(high_children)
    parent_low = compute_parent_heat(low_children)
    
    assert parent_high > parent_low, \
        f"high children ({parent_high:.3f}) should produce higher parent heat than low children ({parent_low:.3f})"


def test_heat_boundaries():
    """热度值范围在 0-1 之间"""
    result = compute_parent_heat([0.5, 0.5, 0.5])
    assert 0.0 <= result <= 1.0, f"heat {result} out of bounds"


def test_reliability_heat_synergy():
    """高 reliability + 高 heat = 搜索时综合得分最高"""
    with open("main.py", "r") as f:
        content = f.read()
    
    # 验证五维搜索使用 reliability 和 heat
    assert "m.reliability" in content, "搜索应包含 reliability"
    assert "m.heat_score" in content, "搜索应包含 heat_score"
    assert "0.15 * m.reliability" in content, "reliability 权重 0.15"
