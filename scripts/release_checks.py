#!/usr/bin/env python3
"""
scripts/release_checks.py — 发布门禁的可执行检查项（v8.0 S3-2 配套）
====================================================================

为什么单独成一个脚本
--------------------
发布状态机（`gcat-std/scripts/release-gate.py`）按 gcat-std 红线
**不许用 shell**（`shlex.split` → argv 列表 → 无元字符解释）。
所以「版本一致 / 隐私扫描 / 服务自报版号 / 变更日志」这些复合检查
不能写成带管道的 shell 一行，必须是有明确退出码的可执行文件。

每个子命令都是**独立可跑、退出码说话**的：
  0 = 通过   1 = 未过   2 = 用法/环境问题
这让门禁能自动化，也让人能单独手工复核（不是黑箱）。

子命令
------
  version-consistency   版本号三处一致: VERSION ↔ README/README_CN badge ↔ CHANGELOG 首条
  privacy               隐私扫描: 硬编码密钥/IP/域名/本机路径 —— 判据「零输出」
  service-version URL   线上服务自报版号必须 == 本地 VERSION（防"文档写了实际没跑"）
  changelog VERSION     CHANGELOG 里必须有该版本条目
  artifact POINTER      产出物指针完整性: 路径存在 + sha256 可算

用法:
  python3 scripts/release_checks.py version-consistency
  python3 scripts/release_checks.py privacy
  python3 scripts/release_checks.py service-version http://127.0.0.1:18010/
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 隐私扫描模式（与 CI 门禁同源思想）：
#   ⚠️ 扫描器必然自指 —— 模式定义本身就含敏感串写法 → 必须排除自身
SELF_EXCLUDE = {"scripts/release_checks.py", ".github/workflows/privacy.yml",
                ".github/workflows/ci.yml"}
PRIVACY_PATTERNS = [
    ("私钥块", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("明文密钥赋值", r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    ("常见云密钥前缀", r"\b(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})"),
    ("真实 IPv4（排除 127/0/255/文档段）", r"\b(?!127\.|0\.|255\.|10\.0\.2\.)(?:\d{1,3}\.){3}\d{1,3}\b"),
    # 只认**真实账号**，不认 /home/u/ 这类测试占位符 ——
    # 判据是"泄露了本机身份"，不是"出现过 /home/"。
    # 收紧前实测被 tests 里的 `/home/u/proj/a.py` 夹具误报（那是通用占位符，零信息量）。
    ("本机账号路径", r"/home/(g-cat|ubuntu|gy_ma)/"),
    ("Windows 用户路径", r"[A-Za-z]:\\\\?Users\\\\?(gy_ma|g-cat|Administrator)"),
]


def _tracked_files() -> list[str]:
    """只看 git 追踪的文件 —— 本地模拟 == CI 实际行为（治理标准里的踩坑教训）。

    ⚠️ 必须 `-c core.quotepath=false`：否则 git 会把**非 ASCII 文件名**转义成
    `"\\351\\207\\207\\224..."` 这种带引号的八进制串，`open()` 直接 FileNotFoundError
    （实测踩到：中文命名的 ADR 文件）。
    """
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=false", "-C", ROOT, "ls-files"],
                             capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return [f for f in out.stdout.splitlines() if f.strip()]
    except Exception:  # noqa: BLE001
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in
                       (".git", ".venv", "__pycache__", ".pytest_cache", "node_modules")]
        for fn in filenames:
            files.append(os.path.relpath(os.path.join(dirpath, fn), ROOT))
    return files


def check_version_consistency() -> int:
    vpath = os.path.join(ROOT, "VERSION")
    if not os.path.exists(vpath):
        print("❌ 缺 VERSION 文件")
        return 1
    ver = open(vpath, encoding="utf-8").read().strip()
    problems = []
    for readme in ("README.md", "README_CN.md"):
        p = os.path.join(ROOT, readme)
        if not os.path.exists(p):
            continue
        txt = open(p, encoding="utf-8").read()
        if ver not in txt:
            problems.append(f"{readme} 未出现版本 {ver}")
    cl = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(cl):
        problems.append("缺 CHANGELOG.md")
    else:
        head = open(cl, encoding="utf-8").read()[:4000]
        if ver not in head:
            problems.append(f"CHANGELOG 头部未见 {ver}")
    if problems:
        print("❌ 版本一致性未过: " + "; ".join(problems))
        return 1
    print(f"✅ 版本一致性通过（VERSION={ver}）")
    return 0


def check_privacy() -> int:
    hits = []
    for rel in _tracked_files():
        if rel in SELF_EXCLUDE:
            continue
        p = os.path.join(ROOT, rel)
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    for name, pat in PRIVACY_PATTERNS:
                        if re.search(pat, line):
                            hits.append(f"{rel}:{lineno} [{name}] {line.strip()[:110]}")
        except (IsADirectoryError, PermissionError):
            continue
    if hits:
        print(f"❌ 隐私扫描命中 {len(hits)} 处（判据：零输出）:")
        for h in hits[:40]:
            print("   " + h)
        return 1
    print(f"✅ 隐私扫描通过（扫描 {len(_tracked_files())} 个追踪文件，零输出）")
    return 0


def check_service_version(url: str) -> int:
    ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            body = r.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法访问 {url}: {type(e).__name__}: {e}")
        return 2
    if ver in body:
        print(f"✅ 线上服务自报版号含 {ver}（{body.strip()[:120]}）")
        return 0
    print(f"❌ 线上服务自报版号与本地 VERSION({ver}) 不一致 → {body.strip()[:160]}")
    return 1


def check_changelog(ver: str) -> int:
    cl = os.path.join(ROOT, "CHANGELOG.md")
    if not os.path.exists(cl):
        print("❌ 缺 CHANGELOG.md")
        return 1
    txt = open(cl, encoding="utf-8").read()
    if ver in txt:
        print(f"✅ CHANGELOG 含 {ver}")
        return 0
    print(f"❌ CHANGELOG 缺 {ver}")
    return 1


def check_artifact(pointer: str) -> int:
    """产出物指针完整性：路径存在 + sha256 可算（记忆里只放指针 + 指纹）。"""
    p = os.path.expanduser(pointer)
    if not os.path.exists(p):
        print(f"❌ 产出物不存在: {p}")
        return 1
    if os.path.isdir(p):
        print(f"✅ 目录存在: {p}（未做哈希，目录请改用文件指针）")
        return 0
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    print(f"✅ 产出物完好: {p}  sha256={h.hexdigest()[:16]}…  {os.path.getsize(p)} bytes")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="v8.0 发布门禁检查项")
    ap.add_argument("check", choices=["version-consistency", "privacy",
                                      "service-version", "changelog", "artifact"])
    ap.add_argument("arg", nargs="?", default=None)
    a = ap.parse_args()
    if a.check == "version-consistency":
        return check_version_consistency()
    if a.check == "privacy":
        return check_privacy()
    if a.check == "service-version":
        if not a.arg:
            print("需要 URL 参数", file=sys.stderr)
            return 2
        return check_service_version(a.arg)
    if a.check == "changelog":
        return check_changelog(a.arg or open(os.path.join(ROOT, "VERSION"),
                                             encoding="utf-8").read().strip())
    if a.check == "artifact":
        if not a.arg:
            print("需要路径参数", file=sys.stderr)
            return 2
        return check_artifact(a.arg)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
