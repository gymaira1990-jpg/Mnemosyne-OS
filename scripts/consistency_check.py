#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对外文档一致性检查（防止「文档说 A、实际是 B」这类错误反复出现）

起因：2026-11-03 一轮里，AGENTS.md 写着「生产运行 v8.1.0 待部署」「200 用例」「8 类落点」，
实际是 v9.0.1 / 294 用例 / 10 类落点；PROGRESS 也停在「待部署」。
这些不是代码 bug，是**文档在骗人**，而肉眼每次都要扫三遍才发现。
所以做成可执行判据：`make test` 里跑一次，红了就改，不靠记性。

检查项：
  C1 版本落点（交给 release_checks.py，不重复实现）
  C2 文档里的「用例数」是否等于真实收集数
  C3 文档里的「落点数」是否等于 release_checks 报的数
  C4 出现「待部署 / not deployed」但生产已自报同版本 → 矛盾
  C5 README 相对链接与图片是否存在
  C6 README 引用的截图文件是否真实存在
  C7 文档里出现「v8.」（旧版本）而当前是 9.x → 提示核对
  C8 生产自报版本 ≠ VERSION → 失败（发布后忘部署；取不到生产版本时跳过）

用法：python3 scripts/consistency_check.py [--repo .]
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

DOCS = ("README.md", "README_CN.md", "AGENTS.md", "PROGRESS.md", "ROADMAP.md", "INSTALL.md")


def sh(cmd, cwd):
    """固定命令、无外部输入：一律用 argv 列表，不开 shell（避免命令注入面）。"""
    # 🔴 2026-11-08：原来只有 text=True。在 GBK 控制台（PYTHONIOENCODING=gbk）下，
    #   子进程返回的字节用 utf-8 解码会抛 UnicodeDecodeError —— 门禁脚本直接崩，
    #   比 stdout 打不出 emoji 更致命。errors="replace" 兜底，解码不中断。
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    a = ap.parse_args()
    root = pathlib.Path(a.repo).resolve()
    fails, warns = [], []

    ver = (root / "VERSION").read_text(encoding="utf-8").strip()

    # C2 真实用例数
    r = sh([sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "-p", "no:warnings"], root)
    out = r.stdout + r.stderr
    m = re.search(r"(\d+)\s+tests?\s+collected", out)
    if m:
        real_cases = int(m.group(1))
    else:
        # 本机 pytest 的 --collect-only -q 按文件聚合：「tests/test_x.py: 9」
        nums = [int(x) for x in re.findall(r":\s*(\d+)\s*$", out, re.M)]
        real_cases = sum(nums) if nums else None
    if real_cases is None:
        warns.append("C2 拿不到真实用例数（.venv 或 pytest 不可用），本项跳过")
    else:
        for d in DOCS:
            p = root / d
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                # 版本历史表 / 历史完成项清单里的数字都属于「历史」，不参与当前对账
                if re.match(r"^\|\s*\[v\d", line) or re.match(r"^\s*[-*]\s", line):
                    continue
                mm = re.search(r"(\d{2,4})\s*(?:用例|tests?\b|cases)", line)
                if mm:
                    n = int(mm.group(1))
                    if n != real_cases:
                        fails.append(f"C2 {d} 写「{n} 用例」，实际收集 {real_cases}：{line.strip()[:60]}")

    # C3 落点数
    r = sh([sys.executable, "scripts/release_checks.py", "version-consistency"], root)
    m = re.search(r"查了\s*(\d+)\s*处", r.stdout)
    real_spots = int(m.group(1)) if m else None
    if real_spots:
        for d in DOCS:
            p = root / d
            if not p.exists():
                continue
            for mm in re.finditer(r"(\d+)\s*(?:类落点|处落点|spots)", p.read_text(encoding="utf-8")):
                if int(mm.group(1)) != real_spots:
                    fails.append(f"C3 {d} 写「{mm.group(1)} 类落点」，实际 {real_spots}")

    # C4 待部署 vs 生产自报
    prod = sh(["curl", "-s", "-m", "8", "http://127.0.0.1:18010/"], root).stdout
    prod_ver = None
    mv = re.search(r"v?(\d+\.\d+\.\d+)", prod or "")
    if mv:
        prod_ver = mv.group(1)
    for d in DOCS:
        p = root / d
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8")
        if re.search(r"待部署|not deployed|pending deploy", txt) and prod_ver == ver:
            fails.append(f"C4 {d} 写「待部署」，但生产已自报 {prod_ver}")

    # C5/C6 链接与图片
    for d in ("README.md", "README_CN.md"):
        p = root / d
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        for mm in re.finditer(r"\]\(([^)#][^)]*)\)|src=\"([^\"]+)\"", s):
            t = mm.group(1) or mm.group(2)
            if not t or t.startswith(("http", "#", "mailto:", "data:")):
                continue
            if not (root / t).exists():
                fails.append(f"C5 {d} 链接/图片不存在：{t}")

    # C7 旧版本号残留（同段里出现 v8.x 且不是历史表）
    for d in ("AGENTS.md", "PROGRESS.md", "ROADMAP.md", "INSTALL.md"):
        p = root / d
        if not p.exists() or not ver.startswith("9"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"v?8\.\d+\.\d+", line) and not re.search(r"20\d\d-\d\d-\d\d\s*[|｜]", line):
                warns.append(f"C7 {d}:{i} 出现旧版本号，确认是历史叙述还是残留：{line.strip()[:70]}")

    # C8 生产自报版本必须等于 VERSION（「发了 tag 忘了部署」是反复发生的老毛病）
    #     取不到生产版本（隧道没开 / 本机离线）时跳过，不误报。
    if prod_ver and prod_ver != ver:
        fails.append(
            f"C8 生产自报 {prod_ver}，仓库 VERSION 是 {ver} —— 要么没部署，要么生产跑的是旧版"
        )

    print(f"版本 {ver}｜真实用例 {real_cases}｜落点 {real_spots}｜生产自报 {prod_ver}")
    for f in fails:
        print("  ❌", f)
    for w in warns:
        print("  ⚠️ ", w)
    print(f"\n结果：{len(fails)} 失败 / {len(warns)} 提醒")
    return 1 if fails else 0


def _safe_console() -> None:
    """GBK 控制台打 emoji 会直接崩（DSH 审计 P1-3）。errors=replace 兜底，不中断。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            reconf = getattr(stream, "reconfigure", None)
            if reconf is not None:
                reconf(errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    _safe_console()
    sys.exit(main())
