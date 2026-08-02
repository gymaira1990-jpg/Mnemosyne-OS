"""v6.0 回归测试 — 受控分类词表归一化 + reflect L4 保护语义"""

import pytest
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 提取 normalize_category（不触发 main.py 完整导入副作用）
SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")).read()
_NS = {}
exec(SRC[SRC.index("CATEGORY_WHITELIST"):SRC.index("# ── v5.0: 模块化导入")], _NS)
normalize_category = _NS["normalize_category"]
CATEGORY_WHITELIST = _NS["CATEGORY_WHITELIST"]


@pytest.mark.parametrize("cat,expected", [
    # 受控主键直通
    ("knowledge", "knowledge"), ("pitfall", "pitfall"), ("reference", "reference"),
    ("project", "project"), ("ops", "ops"), ("deploy", "deploy"),
    ("preference", "preference"), ("session", "session"), ("worklog", "worklog"),
    ("temp", "temp"),
    # 旧英文分类映射
    ("monitoring", "ops"), ("healthcheck", "ops"), ("chat", "session"),
    ("note", "worklog"), ("work", "worklog"), ("fact", "knowledge"),
    ("pattern", "knowledge"), ("belief", "knowledge"), ("experience", "pitfall"),
    ("architecture", "knowledge"), ("design-pattern", "knowledge"), ("research", "reference"),
    # 中文分类
    ("架构", "knowledge"), ("架构设计", "knowledge"), ("论文研究", "reference"),
    ("踩坑记录", "pitfall"), ("运维日报", "ops"), ("部署文档", "deploy"),
    ("项目计划", "project"), ("用户偏好", "preference"), ("会话记录", "session"),
    ("工作日志", "worklog"), ("临时提醒", "temp"), ("知识图谱", "knowledge"),
    # 未知分类兜底
    ("", "knowledge"), (None, "knowledge"), ("xyz", "knowledge"),
])
def test_normalize_category(cat, expected):
    assert normalize_category(cat) == expected


def test_whitelist_has_exactly_10_categories():
    assert set(CATEGORY_WHITELIST.keys()) == {
        "knowledge", "pitfall", "reference", "project", "ops",
        "deploy", "preference", "session", "worklog", "temp",
    }


def test_reflect_l4_preserves_memory_not_deletes():
    """v6.0: reflect L4 只标记 forgotten_at，绝不 is_deleted=TRUE"""
    src = SRC
    # L4 迁移语句不应包含 is_deleted=TRUE
    l4_lines = [l for l in src.splitlines() if "tier = 'L4'" in l]
    assert l4_lines, "reflect 中应有 L4 迁移语句"
    for line in l4_lines:
        assert "is_deleted = TRUE" not in line, f"L4 不应直接删除: {line}"
        assert "forgotten_at = NOW()" in line, f"L4 应标记 forgotten_at: {line}"
