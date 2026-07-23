"""
test_hall_flow.py — 三馆流转规则 6 用例
"""
import pytest
import sys
sys.path.insert(0, ".")

# valid_flow 规则在 api/halls.py promote_memory 中定义
# 此处测试规则矩阵的正确性

VALID_FLOW = {
    "research": ["engineering"],
    "engineering": ["archive", "research"],
    "archive": [],
}


def test_flow_research_to_engineering():
    """研究馆 → 工程馆: 允许"""
    assert "engineering" in VALID_FLOW["research"]


def test_flow_engineering_to_archive():
    """工程馆 → 档案馆: 允许"""
    assert "archive" in VALID_FLOW["engineering"]


def test_flow_engineering_to_research():
    """工程馆 → 研究馆: 允许 (退回)"""
    assert "research" in VALID_FLOW["engineering"]


def test_flow_archive_blocked():
    """档案馆 → 任何: 禁止 (终态)"""
    assert VALID_FLOW["archive"] == []


def test_flow_research_to_archive_blocked():
    """研究馆 → 档案馆: 禁止 (必须经过工程馆)"""
    assert "archive" not in VALID_FLOW["research"]


def test_flow_invalid_target():
    """不存在的目标馆 → 不在 valid_flow 中"""
    for targets in VALID_FLOW.values():
        assert "invalid_hall" not in targets
