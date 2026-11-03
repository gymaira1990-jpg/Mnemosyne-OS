#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release.py —— 版本号 / tag / Release 三件套的唯一入口

为什么有这个脚本（2026-11-04 主人第三次提「打版本总遗漏」）：
  VERSION 改了、代码推了、**tag 和 GitHub Release 忘了**，于是：
  线上是 9.0.2、仓库说 9.0.3、GitHub 最新 Release 还是 9.0.2 —— 三处对不上，谁也说不清到底发了没发。
  根因不是记不住，是**没有一条命令同时做这三件事**，只能靠人记住。

用法：
    python3 scripts/release.py verify                 # 只检查：VERSION ↔ tag ↔ Release ↔ 已推送
    python3 scripts/release.py notes                  # 打印本版 CHANGELOG 段（可当 Release 正文）
    python3 scripts/release.py ship  [--no-push]      # 建 tag（缺则建）→ 推 tag → 建 Release → 复验
    python3 scripts/release.py ship  --title "..."    # 自定义 Release 标题

判据（verify 非零退出即「发版不完整」）：
    ① 工作区干净（无未提交改动）
    ② 本地有 tag v<VERSION>，且指向当前 HEAD 的祖先或自身
    ③ 远端有同名 tag
    ④ GitHub 上有该 tag 的 Release
    ⑤ 当前分支已推送且 HEAD == 远端 HEAD
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=ROOT, capture_output=True, text=True, check=False)


def version() -> str:
    return open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()


def changelog_section(ver: str) -> str:
    path = os.path.join(ROOT, "CHANGELOG.md")
    text = open(path, encoding="utf-8").read()
    m = re.search(rf"^## \[{re.escape(ver)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if not m:
        return ""
    body = m.group(1).strip()
    hm = re.search(rf"^## \[{re.escape(ver)}\]([^\n]*)", text, re.M)
    header = (hm.group(1) if hm else "").strip(" —·")
    return f"{header}\n\n{body}" if header else body


def branch() -> str:
    return sh("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def remote_tag_exists(tag: str) -> bool:
    out = sh("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}").stdout
    return bool(out.strip())


def local_tag_exists(tag: str) -> bool:
    return sh("git", "tag", "-l", tag).stdout.strip() == tag


def release_exists(tag: str) -> bool:
    r = sh("gh", "api", f"repos/{repo_slug()}/releases/tags/{tag}")
    return r.returncode == 0


def repo_slug() -> str:
    url = sh("git", "remote", "get-url", "origin").stdout.strip()
    m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else ""


def verify() -> int:
    ver = version()
    tag = f"v{ver}"
    problems: list[str] = []

    dirty = sh("git", "status", "--porcelain").stdout.strip()
    if dirty:
        problems.append(f"工作区不干净（{len(dirty.splitlines())} 个文件未提交）")

    if not local_tag_exists(tag):
        problems.append(f"本地缺 tag {tag}")
    else:
        # tag 必须指向 HEAD 或其祖先
        anc = sh("git", "merge-base", "--is-ancestor", tag, "HEAD")
        if anc.returncode != 0:
            problems.append(f"{tag} 不指向 HEAD 的祖先（tag 落后于代码）")

    if local_tag_exists(tag) and not remote_tag_exists(tag):
        problems.append(f"远端缺 tag {tag}（git push origin {tag}）")

    if remote_tag_exists(tag) and not release_exists(tag):
        problems.append(f"GitHub 缺 {tag} 的 Release（gh release create {tag} …）")

    b = branch()
    up = sh("git", "rev-parse", "@{upstream}").stdout.strip()
    head = sh("git", "rev-parse", "HEAD").stdout.strip()
    if up and up != head:
        problems.append(f"{b} 有未推送提交（本地 {head[:7]} ≠ 远端 {up[:7]}）")

    print(f"VERSION = {ver} ｜ 分支 {b}")
    if problems:
        print("❌ 发版不完整：")
        for p in problems:
            print("   ·", p)
        return 1
    print(f"✅ 三件套齐全：VERSION {ver} = tag {tag} = Release {tag}，且已推送")
    return 0


def ship(push: bool, title: str | None) -> int:
    ver = version()
    tag = f"v{ver}"
    notes = changelog_section(ver)
    if not notes:
        print(f"❌ CHANGELOG 里没有 {ver} 的段落，先补 CHANGELOG 再发版")
        return 1

    if not local_tag_exists(tag):
        r = sh("git", "tag", "-a", tag, "-m", f"Mnemosyne OS {ver}")
        if r.returncode != 0:
            print("❌ 建 tag 失败：", r.stderr.strip()[:200])
            return 1
        print(f"① 已建 tag {tag}")
    else:
        print(f"① tag {tag} 已存在")

    if push:
        r = sh("git", "push", "origin", tag)
        print("② 推 tag:", "OK" if r.returncode == 0 else r.stderr.strip()[:160])
        if r.returncode != 0 and "already exists" not in r.stderr:
            return 1
        r = sh("git", "push", "origin", branch())
        if r.returncode != 0:
            print("② 推分支失败：", r.stderr.strip()[:160])
            return 1
    else:
        print("② 跳过推送（--no-push）")

    if not release_exists(tag):
        t = title or f"Mnemosyne OS {ver}"
        r = sh("gh", "release", "create", tag, "--title", t, "--notes", notes)
        print("③ 建 Release:", "OK" if r.returncode == 0 else r.stderr.strip()[:200])
        if r.returncode != 0:
            return 1
    else:
        print(f"③ Release {tag} 已存在")

    print("④ 复验")
    return verify()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["verify", "ship", "notes"])
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--title")
    a = ap.parse_args()
    if a.cmd == "notes":
        print(changelog_section(version()))
        return 0
    if a.cmd == "verify":
        return verify()
    return ship(push=not a.no_push, title=a.title)


if __name__ == "__main__":
    sys.exit(main())
