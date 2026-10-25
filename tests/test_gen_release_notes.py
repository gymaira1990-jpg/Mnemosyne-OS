#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-release-notes.py 回归测试

覆盖：
  · bump 规则（breaking→major / feat→minor / fix→patch / 仅杂务→patch）
  · 分类生成（Added/Fixed/Docs 小节顺序与内容）
  · 版本表插入（双语，幂等不重复）
  · CHANGELOG 幂等（同版本不重复插）

运行：PYTHONPATH= .venv/bin/python -m pytest tests/test_gen_release_notes.py -q
"""
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(ROOT, "scripts", "gen-release-notes.py")
    spec = importlib.util.spec_from_file_location("genrel", path)
    assert spec is not None and spec.loader is not None, f"无法加载 {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load()


@pytest.mark.parametrize("commits,want", [
    ([{"type": "fix", "scope": "", "subject": "a", "breaking": False}], "1.2.4"),
    ([{"type": "perf", "scope": "", "subject": "a", "breaking": False}], "1.2.4"),
    ([{"type": "feat", "scope": "", "subject": "a", "breaking": False}], "1.3.0"),
    ([{"type": "feat", "scope": "", "subject": "a", "breaking": True}], "2.0.0"),
    ([{"type": "docs", "scope": "", "subject": "a", "breaking": False}], "1.2.4"),
    ([{"type": "chore", "scope": "", "subject": "a", "breaking": False}], "1.2.4"),
])
def test_next_version(commits, want):
    got, why = G.next_version("1.2.3", commits)
    assert got == want, f"期望 {want} 实得 {got}（{why}）"


def test_build_notes_sections_and_order():
    notes = G.build_notes("1.3.0", [
        {"type": "feat", "scope": "gate", "subject": "新增检查", "breaking": False},
        {"type": "fix", "scope": "", "subject": "修漂移", "breaking": False},
        {"type": "chore", "scope": "", "subject": "杂务", "breaking": False},
    ], today="2026-10-26")
    assert "## 1.3.0 — 2026-10-26" in notes
    assert "**gate**: 新增检查" in notes
    assert notes.index("### Added") < notes.index("### Fixed") < notes.index("### Chores")


def test_build_notes_breaking_goes_first():
    notes = G.build_notes("2.0.0", [
        {"type": "feat", "scope": "", "subject": "新东西", "breaking": False},
        {"type": "fix", "scope": "", "subject": "破坏性改动", "breaking": True},
    ], today="2026-10-26")
    assert notes.index("Breaking Changes") < notes.index("Added")


def test_build_notes_empty_is_honest():
    notes = G.build_notes("9.9.9", [], today="2026-10-26")
    assert "无可归类" in notes


def test_write_version_history_idempotent(tmp_path, monkeypatch):
    """双语版本表插入：一次插入、二次不重复。"""
    monkeypatch.setattr(G, "ROOT", str(tmp_path))
    (tmp_path / "README.md").write_text(
        "| Version | Date | Ships |\n|---|---|---|\n| [v1.0.0](https://github.com/o/r/releases/tag/v1.0.0) | 2026-01-01 | old |\n",
        encoding="utf-8")
    (tmp_path / "README_CN.md").write_text(
        "| 版本 | 日期 | 发布内容 |\n|---|---|---|\n| [v1.0.0](https://github.com/o/r/releases/tag/v1.0.0) | 2026-01-01 | 旧 |\n",
        encoding="utf-8")
    notes = G.build_notes("1.1.0", [{"type": "feat", "scope": "", "subject": "x", "breaking": False}])
    changed = G.write_version_history("1.1.0", notes, "o/r")
    assert set(changed) == {"README.md", "README_CN.md"}
    for f in changed:
        txt = (tmp_path / f).read_text(encoding="utf-8")
        assert txt.index("v1.1.0") < txt.index("v1.0.0"), "新行必须插在表头之下、旧版之上"
    # 幂等
    assert G.write_version_history("1.1.0", notes, "o/r") == []


def test_write_changelog_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "ROOT", str(tmp_path))
    (tmp_path / "CHANGELOG.md").write_text("## 1.0.0 — 2026-01-01\n\n- old\n", encoding="utf-8")
    notes = G.build_notes("1.1.0", [{"type": "feat", "scope": "", "subject": "x", "breaking": False}])
    assert G.write_changelog("1.1.0", notes) is True
    assert "## 1.1.0" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert G.write_changelog("1.1.0", notes) is False, "同版本不许重复插"


def test_bump_badge(tmp_path, monkeypatch):
    """badge 也要自动改 —— 手改必漏（实测漏过一次）。"""
    monkeypatch.setattr(G, "ROOT", str(tmp_path))
    (tmp_path / "README.md").write_text(
        "![v](https://img.shields.io/badge/version-1.0.0-brightgreen?style=flat-square)", encoding="utf-8")
    (tmp_path / "README_CN.md").write_text(
        "![v](https://img.shields.io/badge/version-1.0.0-brightgreen?style=flat-square)", encoding="utf-8")
    changed = G.bump_badge("2.0.0")
    assert set(changed) == {"README.md", "README_CN.md"}
    for f in changed:
        assert "version-2.0.0-brightgreen" in (tmp_path / f).read_text(encoding="utf-8")
    assert G.bump_badge("2.0.0") == [], "已是目标版本则不应再报改动"


def test_selftest_passes():
    assert G._selftest() == 0
