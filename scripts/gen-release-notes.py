#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-release-notes.py — 从 conventional commits 自动生成发布材料

为什么要它（2026-10-26 实测教训）：
  「版本号 / CHANGELOG 段 / 双语版本表行」一直靠手写 ⇒ 连续两版漏登记、ROADMAP 落后三版。
  人力纪律不可靠，能自动生成的就别手写。

借鉴而不依赖（本机铁律：只用标准库，不装第三方工具）：
  · git-cliff   —— conventional commits → 分类分组的 changelog
  · commitizen  —— feat/fix/breaking → 语义化版本 bump
  · towncrier   —— 结构化 news fragment 的思路
  三者共同规则在这里用约 200 行标准库实现，无外部依赖。

用法：
  python3 scripts/gen-release-notes.py                  # 干跑：打印建议版本 + 预览
  python3 scripts/gen-release-notes.py --bump           # 只报建议的下一个版本号
  python3 scripts/gen-release-notes.py --write          # 真写：CHANGELOG 段 + 双语版本表行
  python3 scripts/gen-release-notes.py --since v8.0.0   # 指定起点（默认=最近 tag）

判据（自检）：python3 scripts/gen-release-notes.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 分类映射（Conventional Commits → Keep a Changelog 小节）──
SECTIONS = [
    ("breaking", "⚠️ Breaking Changes", "💥"),
    ("feat",     "Added",               "➕"),
    ("fix",      "Fixed",               "🩹"),
    ("perf",     "Performance",         "⚡"),
    ("refactor", "Changed",             "♻️"),
    ("docs",     "Docs",                "📝"),
    ("test",     "Tests",               "✅"),
    ("ci",       "CI",                  "🔧"),
    ("build",    "Build",               "📦"),
    ("chore",    "Chores",              "🧹"),
    ("release",  "Release",             "🚀"),
]
TYPE_TO_SECTION = {t: s for s, _, _ in SECTIONS for t in [s]}
SYMBOL = {s: sym for s, _, sym in SECTIONS}

COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?:\s*(?P<subject>.+)$")
BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.M)


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def last_tag() -> str:
    try:
        return sh("git", "describe", "--tags", "--abbrev=0")
    except subprocess.CalledProcessError:
        return ""


def repo_slug() -> str:
    try:
        url = sh("git", "remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        return "owner/repo"
    m = re.search(r"[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else "owner/repo"


def parse_commits(since: str) -> list[dict]:
    rng = f"{since}..HEAD" if since else "HEAD"
    raw = sh("git", "log", "--format=%H%x1f%s%x1f%b%x1e", rng)
    out = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 2:
            continue
        sha, subject = parts[0], parts[1]
        body = parts[2] if len(parts) > 2 else ""
        m = COMMIT_RE.match(subject)
        if not m:
            out.append({"sha": sha, "type": "other", "scope": "", "subject": subject,
                        "breaking": bool(BREAKING_FOOTER.search(body)), "body": body})
            continue
        out.append({
            "sha": sha,
            "type": m.group("type"),
            "scope": m.group("scope") or "",
            "subject": m.group("subject"),
            "breaking": bool(m.group("breaking")) or bool(BREAKING_FOOTER.search(body)),
            "body": body,
        })
    return out


def next_version(cur: str, commits: list[dict]) -> tuple[str, str]:
    """语义化 bump：breaking→major / feat→minor / 其余→patch。返回 (版本, 理由)。"""
    major, minor, patch = (int(x) for x in cur.split("."))
    if any(c["breaking"] for c in commits):
        return f"{major + 1}.0.0", "存在 breaking change"
    if any(c["type"] == "feat" for c in commits):
        return f"{major}.{minor + 1}.0", "含新功能 (feat)"
    if any(c["type"] in ("fix", "perf") for c in commits):
        return f"{major}.{minor}.{patch + 1}", "含修复/性能改进"
    return f"{major}.{minor}.{patch + 1}", "仅非功能性改动（patch 档）"


def build_notes(ver: str, commits: list[dict], today: str | None = None) -> str:
    """生成 Keep a Changelog 风格的 Markdown 段。"""
    today = today or dt.date.today().isoformat()
    buckets: dict[str, list[dict]] = {}
    for c in commits:
        if c["type"] == "other":
            key = "chore"
        elif c["breaking"]:
            key = "breaking"
        else:
            key = c["type"] if c["type"] in TYPE_TO_SECTION else "chore"
        buckets.setdefault(key, []).append(c)

    lines = [f"## {ver} — {today}", ""]
    for key, title, _sym in SECTIONS:
        items = buckets.get(key)
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for c in items:
            scope = f"**{c['scope']}**: " if c["scope"] else ""
            lines.append(f"- {SYMBOL[key]} {scope}{c['subject']}")
        lines.append("")
    if len(lines) == 2:
        lines.append("- （本段无可归类的提交）")
        lines.append("")
    return "\n".join(lines)


def write_changelog(ver: str, notes: str) -> bool:
    path = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(path):
        return False
    txt = open(path, encoding="utf-8").read()
    if re.search(rf"^##\s*v?{re.escape(ver)}\b", txt, re.M):
        return False                      # 已有该版本段，不重复插
    open(path, "w", encoding="utf-8").write(notes + "\n" + txt)
    return True


def bump_badge(ver: str) -> list[str]:
    """把双语 README 的 version badge 改到 ver。

    2026-10-26 实测：本脚本先只写 CHANGELOG + 版本表，结果 version-consistency 立刻报
    「EN badge 是 8.0.1，应为 8.1.0」—— badge 也是一处落点，手改必漏。能自动的就别手写。
    """
    changed = []
    pat = re.compile(r"(badge/version-)(\d+\.\d+\.\d+)(-)")
    for fname in ("README.md", "README_CN.md"):
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        new = pat.sub(lambda m: m.group(1) + ver + m.group(3), txt, count=1)
        if new != txt:
            open(path, "w", encoding="utf-8").write(new)
            changed.append(fname)
    return changed


def write_version_history(ver: str, notes: str, slug: str) -> list[str]:
    """向双语 README 的版本表插入新行。返回被改动的文件名。"""
    today = dt.date.today().isoformat()
    # 取 Added/Fixed 的标题做摘要
    heads = re.findall(r"^###\s+(.+)$", notes, re.M)
    summary = " · ".join(heads[:4]) if heads else "release"
    row = (f"| [v{ver}](https://github.com/{slug}/releases/tag/v{ver}) "
           f"| {today} | {summary} |")
    changed = []
    for fname in ("README.md", "README_CN.md"):
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        if f"releases/tag/v{ver}" in txt:
            continue                      # 已登记
        lines = txt.split("\n")
        insert_at = None
        for i, ln in enumerate(lines):
            # 版本表表头分隔行之后就是最新版本行
            if re.match(r"^\|[\s\-:|]+\|\s*$", ln) and i >= 1 and "Version" in lines[i - 1] or \
               re.match(r"^\|[\s\-:|]+\|\s*$", ln) and i >= 1 and "版本" in lines[i - 1]:
                insert_at = i + 1
            if insert_at is not None:
                break
        if insert_at is None:
            continue
        lines.insert(insert_at, row)
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        changed.append(fname)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="从 conventional commits 生成发布材料")
    ap.add_argument("--since", default=None, help="起始 tag（默认=最近 tag）")
    ap.add_argument("--bump", action="store_true", help="只报建议版本号")
    ap.add_argument("--write", action="store_true", help="真写 CHANGELOG + 版本表")
    ap.add_argument("--selftest", action="store_true", help="跑内置自检")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()

    cur = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    since = a.since if a.since is not None else last_tag()
    commits = parse_commits(since)
    if not commits:
        print(f"（自 {since or 'HEAD~'} 起没有新提交）")
        return 0

    ver, why = next_version(cur, commits)
    if a.bump:
        print(ver)
        return 0

    notes = build_notes(ver, commits)
    print(f"当前 VERSION: {cur}")
    print(f"起点: {since or '(全部历史)'} · 提交 {len(commits)} 条")
    print(f"建议版本: {ver}（{why}）")
    print()
    print(notes)

    if not a.write:
        print("\n[干跑] 加 --write 才写入 CHANGELOG 与双语版本表。")
        return 0

    changed = []
    if write_changelog(ver, notes):
        changed.append("CHANGELOG.md")
    changed += bump_badge(ver)
    changed += write_version_history(ver, notes, repo_slug())
    if not changed:
        print("\n⚠️ 未写入任何文件（可能该版本已存在）")
        return 1
    print(f"\n✅ 已写入: {', '.join(changed)}")
    print(f"   下一步: 把 VERSION 改为 {ver} → 跑 scripts/release_checks.py version-consistency")
    return 0


def _selftest() -> int:
    """内置自检：分类、bump 规则、生成结构。不依赖仓库状态。"""
    cases = [
        # (commits, 期望版本)
        ([{"type": "fix", "scope": "", "subject": "a", "breaking": False}], "1.2.4"),
        ([{"type": "feat", "scope": "x", "subject": "b", "breaking": False}], "1.3.0"),
        ([{"type": "feat", "scope": "", "subject": "c", "breaking": True}], "2.0.0"),
        ([{"type": "docs", "scope": "", "subject": "d", "breaking": False}], "1.2.4"),
    ]
    for commits, want in cases:
        got, _ = next_version("1.2.3", commits)
        assert got == want, f"{commits[0]['type']}: 期望 {want} 实得 {got}"

    notes = build_notes("1.3.0", [
        {"type": "feat", "scope": "gate", "subject": "新增检查", "breaking": False},
        {"type": "fix", "scope": "", "subject": "修漂移", "breaking": False},
        {"type": "chore", "scope": "", "subject": "杂务", "breaking": False},
    ], today="2026-10-26")
    assert "## 1.3.0 — 2026-10-26" in notes
    assert "### Added" in notes and "**gate**: 新增检查" in notes
    assert "### Fixed" in notes and "修漂移" in notes
    assert notes.index("### Added") < notes.index("### Fixed"), "小节顺序应按 SECTIONS"
    print("SELFTEST OK — bump 规则 4 例 + 生成结构 4 项断言全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
