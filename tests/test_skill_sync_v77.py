"""v7.7.0 程序性记忆翼 — skill_sync 纯函数测试 (不依赖 DB)

覆盖: frontmatter 解析 / state 映射 / 目录扫描合并 / 去重 / 变更检测
对齐现有范式: 生产逻辑同源复制 (见 skill_sync.py)
"""
import sys
sys.path.insert(0, ".")
from skill_sync import parse_frontmatter, state_mapping, build_skill_items, dedup_items, diff_manifest


class TestFrontmatter:
    def test_simple(self):
        md = "---\nname: proxy-troubleshooting\ndescription: Use when 代理问题排查\n---\n# body"
        n, d = parse_frontmatter(md)
        assert n == "proxy-troubleshooting"
        assert "代理" in d

    def test_block_scalar(self):
        md = '---\nname: x\ndescription: >-\n  多行描述\n  合并一行\n---\n'
        n, d = parse_frontmatter(md)
        assert n == "x"
        assert "合并一行" in d

    def test_template_garbage(self):
        md = '---\nname: y\ndescription: Use when 使用 y 技能处理相关任务\n---\n'
        n, d = parse_frontmatter(md)
        assert d == ""  # 模板化描述应过滤

    def test_no_frontmatter(self):
        n, d = parse_frontmatter("plain text")
        assert n == "" and d == ""


class TestStateMapping:
    def test_curator_states_passthrough(self):
        assert state_mapping({"state": "active"}) == "active"
        assert state_mapping({"state": "stale"}) == "stale"
        assert state_mapping({"state": "archived"}) == "archived"

    def test_missing_defaults_active(self):
        assert state_mapping(None) == "active"
        assert state_mapping({}) == "active"
        assert state_mapping({"state": "weird"}) == "active"


class TestBuildItems:
    def test_active_and_archive(self, tmp_path):
        # active 技能
        sk = tmp_path / "skills"
        (sk / "devops" / "skill-a").mkdir(parents=True)
        (sk / "devops" / "skill-a" / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: Use when 网络排查\n---\n", encoding="utf-8")
        # 归档技能
        arch = sk / ".archive"
        (arch / "skill-b").mkdir(parents=True)
        (arch / "skill-b" / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: Use when 旧技能\n---\n", encoding="utf-8")
        usage = {"skill-a": {"state": "active", "use_count": 5}}
        items = build_skill_items(str(sk), usage)
        by_name = {i["skill_name"]: i for i in items}
        assert by_name["skill-a"]["state"] == "active"
        assert by_name["skill-a"]["use_count"] == 5
        assert by_name["skill-b"]["state"] == "archived"  # 归档目录强制 archived
        assert by_name["skill-b"]["use_count"] == 0

    def test_dedup_active_wins(self):
        items = [
            {"skill_name": "dup", "state": "archived"},
            {"skill_name": "dup", "state": "active"},
        ]
        out = dedup_items(items)
        assert len(out) == 1
        assert out[0]["state"] == "active"


class TestDiff:
    def test_new_item_pushed(self):
        local = [{"skill_name": "a", "description": "d", "state": "active",
                  "use_count": 0, "view_count": 0, "content_hash": "h1"}]
        to_push = diff_manifest(local, [])
        assert len(to_push) == 1

    def test_unchanged_skipped(self):
        local = [{"skill_name": "a", "description": "d", "state": "active",
                  "use_count": 1, "view_count": 2, "content_hash": "h1"}]
        remote = [dict(local[0])]
        assert diff_manifest(local, remote) == []

    def test_state_change_pushed(self):
        local = [{"skill_name": "a", "description": "d", "state": "active",
                  "use_count": 1, "view_count": 2, "content_hash": "h1"}]
        remote = [{"skill_name": "a", "description": "d", "state": "stale",
                   "use_count": 1, "view_count": 2, "content_hash": "h1"}]
        to_push = diff_manifest(local, remote)
        assert len(to_push) == 1
        assert "_change" in to_push[0]
