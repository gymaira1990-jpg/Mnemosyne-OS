#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开仓库隐私扫描（P0 真凭据 / P1 内部信息 两档）

判据：P0 零命中才允许推；P1 逐条复核后必须为零（公开托管远端逐行展开）。
用法：python3 privacy_scan.py <repo_dir>
"""
import re
import subprocess
import sys
import pathlib

P0 = [
    ("OpenAI/DS key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("Tavily key", re.compile(r"tvly-[A-Za-z0-9]{16,}")),
    ("GitHub token", re.compile(r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("腾讯云 AK", re.compile(r"AKID[A-Za-z0-9]{13,}")),
    ("硬编码 PGPASSWORD", re.compile(r"PGPASSWORD=[\"']?[A-Za-z0-9]{8,}")),
    ("硬编码 API_KEY 字面量", re.compile(r"(?:API_KEY|TOKEN|SECRET)\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']")),
]
P1 = [
    ("个人裸域名", re.compile(r"g-cat\.(?:cn|cv|com)")),
    ("内网/公网 IP", re.compile(r"\b(?!127\.0\.0\.1|0\.0\.0\.0|10\.0\.0\.1)(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("本机家目录", re.compile("/home/" + "g-cat|" + "gy_" + "ma|/mnt/c/Users/")),  # 拼接构造，避免自命中
    ("个人邮箱", re.compile(r"[\w.\-]+@g-cat\.[a-z]+")),
    ("SSH 私钥路径", re.compile(r"\.pem\b|id_rsa|tencent-gz")),
    ("内部端口", re.compile(r"\b2222\b")),
    ("内部主机名", re.compile(r"\bgz\b(?=/|\.|\s|:)|\bwsl\b", re.I)),
]
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".sqlite", ".db", ".gz", ".zip"}

repo = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
files = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout.splitlines()

hits = {"P0": [], "P1": []}
for rel in files:
    p = repo / rel
    if p.suffix.lower() in SKIP_EXT or not p.exists():
        continue
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for i, line in enumerate(txt.splitlines(), 1):
        if "privacy_scan" in rel:
            continue
        for name, pat in P0:
            if pat.search(line):
                hits["P0"].append((rel, i, name, line.strip()[:110]))
        for name, pat in P1:
            if pat.search(line):
                hits["P1"].append((rel, i, name, line.strip()[:110]))

for tier in ("P0", "P1"):
    print(f"\n=== {tier} 命中 {len(hits[tier])} 处 ===")
    for rel, i, name, line in hits[tier][:40]:
        print(f"  {rel}:{i}  [{name}]  {line}")
print(f"\n判定：P0={len(hits['P0'])}（必须 0）｜P1={len(hits['P1'])}（必须逐条复核为 0）")
sys.exit(1 if hits["P0"] else 0)
