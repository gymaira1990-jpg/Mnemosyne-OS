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
    """版本落点一致性 —— 覆盖**全部对外可知的落点**，不再只查三处。

    2026-10-26 实测教训：AGENTS.md 的红线曾写「版本号三处一致（VERSION / README badge / CHANGELOG）」，
    于是每轮只对齐这三处 ⇒ ROADMAP 落后三个版本（停在 v7.8.3）、AGENTS 停在 v8.0.0 都没人发现。
    旧技能（mnemosyne-version-publish §3.2）本来有 15 处清单，整合时缩水了。
    结论：「三处一致」这个口号本身就是缺陷 —— 落点有多少个就查多少个，且必须机器查。
    """
    vpath = os.path.join(ROOT, "VERSION")
    if not os.path.exists(vpath):
        print("❌ 缺 VERSION 文件")
        return 1
    ver = open(vpath, encoding="utf-8").read().strip()
    problems, checked = [], []

    def grab(rel, pattern, label, required=True):
        """从文件里抓出版本串并与 VERSION 比对。"""
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            if required:
                problems.append(f"缺文件 {rel}")
            return
        try:
            txt = open(path, encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            problems.append(f"{rel} 读取失败: {type(e).__name__}")
            return
        m = re.search(pattern, txt, re.M)
        if not m:
            problems.append(f"{rel} 未找到[{label}]标记（格式变了？）")
            return
        got = m.group(1).strip()
        checked.append(f"{label}={got}")
        if got != ver:
            problems.append(f"{rel} 的{label}是 {got}，应为 {ver}")

    # ① 双语 badge
    grab("README.md", r"badge/version-([\d.]+)-", "EN badge")
    grab("README_CN.md", r"badge/version-([\d.]+)-", "CN badge")
    # ② 双语版本表首行（Version History）
    grab("README.md", r"releases/tag/v([\d.]+)\)\s*\|", "EN 版本表首行")
    grab("README_CN.md", r"releases/tag/v([\d.]+)\)\s*\|", "CN 版本表首行")
    # ③ CHANGELOG 最新段
    grab("CHANGELOG.md", r"^##\s*(?:\[)?v?([\d.]+)", "CHANGELOG 最新段")
    # ④ ROADMAP 首行
    grab("ROADMAP.md", r"^>\s*v([\d.]+)\s*\|", "ROADMAP 首行")
    # ⑤ AGENTS 当前版本
    grab("AGENTS.md", r"\*\*当前版本\*\*：?\s*v?([\d.]+)", "AGENTS 当前版本")
    # ⑥ PROGRESS 当前版本
    grab("PROGRESS.md", r"^##\s*当前版本[:：]\s*v?([\d.]+)", "PROGRESS 当前版本")
    # ⑦ INSTALL 版本行
    grab("INSTALL.md", r"^>\s*版本[:：]\s*v([\d.]+)", "INSTALL 版本行")

    if problems:
        print("❌ 版本落点不一致（查了 %d 处）：" % len(checked))
        for x in problems:
            print("   · " + x)
        return 1
    print(f"✅ 版本落点全部一致 = {ver}（查了 {len(checked)} 处：{' / '.join(checked)}）")
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


def check_plan(path: str) -> int:
    """P0 方案阶段判据：方案文档存在，且**含判据表与不做清单**（否则方案不可验收）。

    为什么把它做成命令而不是"人工看看"：标准里写得很清楚 ——
    方案的验收标准是「每条诉求有判据」，没有判据的方案不许进开发。
    """
    p = os.path.join(ROOT, path) if not os.path.isabs(path) else path
    if not os.path.exists(p):
        print(f"❌ P0 方案文档不存在: {p}")
        return 1
    txt = open(p, encoding="utf-8").read()
    need = {"判据": "判据表", "不做": "不做清单/Out of Scope"}
    missing = [desc for kw, desc in need.items() if kw not in txt]
    if missing:
        print(f"❌ 方案缺验收要件: {missing}（方案不许无判据就开工）")
        return 1
    print(f"✅ P0 方案要件齐备（判据表 + 不做清单）: {path}  {len(txt)} 字符")
    return 0


def check_version_history() -> int:
    """P6 判据：README 的 Version History 必须登记当前 VERSION。

    为什么做成命令（2026-10-26 实测教训）：v8.0.0 与 v8.0.1 连续两个版本漏登记 ——
    因为**没有任何门禁查它**，漏了没人发现（badge 写着 8.0.1，Version History 却停在 7.8.4，
    自相矛盾却全绿通过）。人工纪律靠不住，必须机器拦。
    """
    ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    checked, missing = [], []
    for f in ("README.md", "README_CN.md"):
        path = os.path.join(ROOT, f)
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        # 判据要准：必须「确实有版本历史表」（≥3 条 releases/tag 链接）才要求登记本版本。
        # 旧判据用关键词「版本历史」会误判 —— README_CN 的导航表里就有这四个字，却无历史表。
        if txt.count("releases/tag/v") < 3:
            continue
        checked.append(f)
        ok = (f"releases/tag/v{ver}" in txt) or (f"| v{ver} " in txt) or (f"| v{ver} |" in txt)
        if not ok:
            missing.append(f)
    if not checked:
        print("❌ 没有任何 README 含 Version History 段（发布记录无处登记）")
        return 1
    if missing:
        print(f"❌ Version History 未登记 v{ver}: {missing}")
        return 1
    print(f"✅ Version History 含 v{ver}（已查 {', '.join(checked)}）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="v8.0 发布门禁检查项")
    ap.add_argument("check", choices=["version-consistency", "version-history", "privacy",
                                      "service-version", "changelog", "artifact", "plan"])
    ap.add_argument("arg", nargs="?", default=None)
    a = ap.parse_args()
    if a.check == "version-consistency":
        return check_version_consistency()
    if a.check == "version-history":
        return check_version_history()
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
    if a.check == "plan":
        if not a.arg:
            print("需要方案文档路径参数", file=sys.stderr)
            return 2
        return check_plan(a.arg)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
