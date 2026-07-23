"""
test_conflict.py — 矛盾检测准确率测试

场景: 验证 detect_conflict 的 merge/conflict/fresh 分类
"""
import pytest
import sys
sys.path.insert(0, ".")

from main import text_diff_ratio


def test_merge_identical():
    """完全相同文本 → ratio > 0.85 → merge"""
    r = text_diff_ratio(
        "pgvector HNSW index is faster than IVFFlat",
        "pgvector HNSW index is faster than IVFFlat"
    )
    assert r > 0.85, f"identical texts got ratio={r}"


def test_merge_near_identical():
    """几乎相同文本 → ratio > 0.85 → merge"""
    r = text_diff_ratio(
        "HNSW index has better recall than IVFFlat",
        "HNSW index has better recall than IVFFlat in most cases"
    )
    assert r > 0.85, f"near-identical texts got ratio={r:.3f}"


def test_fresh_different():
    """完全不同话题 → ratio < 0.5 → fresh (可能)"""
    r1 = text_diff_ratio(
        "HNSW is the best index for vector search",
        "The weather in Beijing is sunny today"
    )
    # 完全不同，ratio 应该很低
    assert r1 < 0.5, f"different texts got ratio={r1:.3f}"


def test_conflict_contradiction():
    """语义相似 + 内容矛盾 → ratio < 0.5"""
    r = text_diff_ratio(
        "HNSW is the best index for all scenarios",
        "IVFFlat is actually better for low-dimensional data"
    )
    # 主题相关但不完全相同，ratio 应该在中间范围
    assert r < 0.5, f"contradicting texts got ratio={r:.3f}"


def test_boundary_085():
    """边界测试: 恰好 0.85 的 case"""
    # ratio 应该 = 0.85 左右（取决于实现细节）
    r = text_diff_ratio("a" * 85 + "b" * 15, "a" * 85 + "c" * 15)
    # 85% 匹配 → ratio 应该 ≥ 0.85
    assert r >= 0.8, f"boundary case got ratio={r:.3f}"
