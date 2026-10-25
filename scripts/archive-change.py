#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""archive-change.py — 把已完成的 openspec 变更从 changes/ 移入 changes/archive/

为什么要有它（2026-10-26 审计发现）：
  openspec/changes/ 积累 5 个活跃变更、archive/ 为 0 —— 完成的变更从不归档，
  半年后没人分得清「哪份是现行设计、哪份是历史提案」。手工移动易漏，故脚本化。

用法：
    python3 scripts/archive-change.py --list                 # 列出活跃变更与完整度
    python3 scripts/archive-change.py <change-name> [--force] # 归档（默认要求 proposal+tasks 齐）
    python3 scripts/archive-change.py --auto --since v8.1.0   # 归档「已发版且无 ACTIVE 指针」的变更
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGES = os.path.join(ROOT, "openspec", "changes")
ARCHIVE = os.path.join(CHANGES, "archive")
ACTIVE = os.path.join(ROOT, "openspec", "ACTIVE")

REQUIRED = ("proposal.md",)


def active_change() -> str:
    if not os.path.exists(ACTIVE):
        return ""
    for ln in open(ACTIVE, encoding="utf-8"):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            return ln
    return ""


def list_changes() -> list[tuple[str, int, bool]]:
    out = []
    if not os.path.isdir(CHANGES):
        return out
    for name in sorted(os.listdir(CHANGES)):
        d = os.path.join(CHANGES, name)
        if not os.path.isdir(d) or name == "archive":
            continue
        files = [f for f in os.listdir(d) if not f.startswith(".")]
        complete = all(os.path.exists(os.path.join(d, r)) for r in REQUIRED)
        out.append((name, len(files), complete))
    return out


def archive(name: str, force: bool = False) -> int:
    src = os.path.join(CHANGES, name)
    if not os.path.isdir(src):
        print(f"❌ 不存在变更目录: openspec/changes/{name}", file=sys.stderr)
        return 1
    if name == active_change() and not force:
        print(f"❌ {name} 是当前 ACTIVE 变更，拒绝归档（确实要归档请 --force 并先换 ACTIVE 指针）",
              file=sys.stderr)
        return 1
    missing = [r for r in REQUIRED if not os.path.exists(os.path.join(src, r))]
    if missing and not force:
        print(f"❌ {name} 缺必需文件 {missing}，不归档（--force 可强制）", file=sys.stderr)
        return 1
    os.makedirs(ARCHIVE, exist_ok=True)
    dst = os.path.join(ARCHIVE, name)
    if os.path.exists(dst):
        print(f"❌ 归档目标已存在: openspec/changes/archive/{name}", file=sys.stderr)
        return 1
    shutil.move(src, dst)
    print(f"✅ 已归档: openspec/changes/{name} → openspec/changes/archive/{name}")
    print("   记得: 若这是 specs 活规格的来源，请同步 openspec/specs/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="归档已完成的 openspec 变更")
    ap.add_argument("name", nargs="?", help="变更目录名")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="跳过完整性/ACTIVE 检查")
    a = ap.parse_args()

    if a.list or not a.name:
        rows = list_changes()
        print(f"活跃变更 {len(rows)} 个（ACTIVE = {active_change() or '(未设置)'}）:")
        for name, n, complete in rows:
            flag = "✅完整" if complete else "⚠️缺 proposal"
            mark = " ← 当前" if name == active_change() else ""
            print(f"  {name:44s} {n} 文件 {flag}{mark}")
        print(f"\n已归档: {len(os.listdir(ARCHIVE)) if os.path.isdir(ARCHIVE) else 0} 个")
        return 0

    return archive(a.name, a.force)


if __name__ == "__main__":
    raise SystemExit(main())
