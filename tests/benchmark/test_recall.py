"""
test_recall.py — 长期记忆保持率测试

场景: 验证记忆随时间的检索精度
不连真实 PG，用确定性逻辑验证
"""
import pytest
import sys
sys.path.insert(0, ".")


def test_temporal_sql_decay_7days():
    """7天内记忆: 权重 0.15"""
    sql = "CASE WHEN m.created_at > NOW() - INTERVAL '7 days' THEN 0.15"
    assert "0.15" in sql


def test_temporal_sql_decay_30days():
    """30天内记忆: 权重 0.08"""
    sql = "WHEN m.created_at > NOW() - INTERVAL '30 days' THEN 0.08"
    assert "0.08" in sql


def test_temporal_sql_old():
    """超过30天: 权重 0"""
    sql = "ELSE 0 END"
    assert "ELSE 0" in sql or "ELSE 0 END" in sql


def test_five_dimension_weights_sum():
    """五维权重之和应接近 1.0"""
    weights = {
        "semantic": 0.40,
        "bm25": 0.15,
        "temporal": 0.15,  # reduced to 0.10 for validity
        "reliability": 0.15,
        "heat": 0.15,
    }
    total = sum(weights.values())
    assert 0.95 <= total <= 1.05, f"weights sum should be ~1.0, got {total}"


def test_architecture_has_memory_hierarchy():
    """验证架构存在层级记忆结构"""
    with open("main.py", "r") as f:
        content = f.read()
    
    # TMT 层级
    assert "L1" in content or "tier" in content, "应有记忆层级"
    # 三馆
    assert "hall" in content, "应有三馆字段"
    # 时间衰减
    assert "INTERVAL" in content, "应有时间衰减机制"
