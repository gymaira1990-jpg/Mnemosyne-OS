#!/usr/bin/env python3
"""scripts/prod_diff.py — 仓库 ↔ 生产 内容级对拍（部署指纹）

为什么要有它（2026-11-07 审计的结论）
------------------------------------
在这之前，判断「生产跑的是不是这份代码」靠三样：生产 `VERSION` 文件、
`/api/v1/capabilities` 自报版号、`release_checks version-consistency`。
**三处都在读同一个文本文件** —— 只改 `VERSION` 就能让它们全绿，代码一行没动。
实测那次：生产自报 v9.0.16、15/15 全绿，而 209 个入库文件里生产缺 64、内容不同 25。

判据必须是内容级（逐文件 sha256），并且**只比该上生产的那些文件**
（`deploy/prod-manifest.json` 的 `deploy`）。否则 README、tests、CI 全会进来，
每天都红，红久了就被无视 —— 那等于没有门禁。

用法
----
  python3 scripts/prod_diff.py            # 人对读
  python3 scripts/prod_diff.py --json      # 机读（给 CI / 脚本）
  python3 scripts/prod_diff.py --remote gz --path /opt/mnemosyne

退出码
------
  0 = 与清单一致　1 = 有未登记漂移　2 = 环境问题（ssh 不通 / 路径不对）

清单三条铁律
------------
- `deploy`：**必须**与仓库一致的文件（运行面）。空 = 全放行，脚本会拒绝启动。
- `prod_only`：生产上合法存在的独有文件，每条必须写 `why`（源头在别的仓 / 定时脚本 / 备份）。
- `known_diff`：已知不一致，每条必须写 `why` + `until`；这是**欠账清单**，不是免检。
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "deploy", "prod-manifest.json")


def tracked() -> list[str]:
    out = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [l for l in out.splitlines() if l.strip()]


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def ssh_run(remote: str, script: str, stdin: str | None = None) -> str:
    p = subprocess.run(["ssh", remote, script], input=stdin,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ssh {remote} 失败(rc={p.returncode}): {p.stderr.strip()[:300]}")
    return p.stdout


def remote_hashes(remote: str, path: str, names: list[str]) -> dict[str, str]:
    """一次 ssh 拿全部 sha256（逐文件往返会让这条命令没人愿意跑）。"""
    script = (f"cd {path} 2>/dev/null || exit 3; "
              "while IFS= read -r f; do "
              '[ -f "$f" ] && sha256sum -- "$f" 2>/dev/null; done; exit 0')
    payload = "\n".join(names) + "\n"
    # 两跳：脚本先落成远端临时文件，再 `sh 文件` 并把文件名喂给它。
    # ① 不能 `echo b64 | base64 -d | sh`：脚本自己的 stdin 就是那条管道，
    #    `while read` 会读到脚本文本（实测生产命中数 = 0，正是这个坑）。
    # ② 不能 `sh -c "..."` 直传：外层远端 shell 会把内层 "$f" 展开成空。
    b64 = base64.b64encode(script.encode()).decode()
    ssh_run(remote, f"echo {b64} | base64 -d > /tmp/_prod_diff_hash.sh")
    out = ssh_run(remote, "sh /tmp/_prod_diff_hash.sh", payload)
    res = {}
    for line in out.splitlines():
        if "  " not in line:
            continue
        h, _, f = line.partition("  ")
        res[f.strip()] = h.strip()
    return res


def remote_code_files(remote: str, path: str) -> list[str]:
    script = (f"cd {path} 2>/dev/null || exit 3; "
              "find . -maxdepth 2 \\( -name '*.py' -o -name '*.sh' \\) "
              "-not -path './venv/*' -not -path './.venv/*' -not -path './__pycache__/*' "
              "-not -path './data/*' -not -path './backups/*' -not -path './.git/*' "
              "| sed 's|^\\./||' | sort")
    b64 = base64.b64encode(script.encode()).decode()
    out = ssh_run(remote, f"echo {b64} | base64 -d | sh")
    return [f.strip() for f in out.splitlines() if f.strip()]


def load_manifest() -> dict:
    if not os.path.exists(MANIFEST):
        raise SystemExit(f"❌ 找不到 {MANIFEST}（没有部署清单就没有判据）")
    m = json.load(open(MANIFEST, encoding="utf-8"))
    if not m.get("deploy"):
        raise SystemExit("❌ 清单里 deploy 为空 = 全部放行，拒绝执行")
    for key in ("prod_only", "known_diff"):
        for it in m.get(key, []):
            if not it.get("why"):
                raise SystemExit(f"❌ {key} 有条目没写 why：{it}（免检必须给理由）")
    for it in m.get("known_diff", []):
        if not it.get("until"):
            raise SystemExit(f"❌ known_diff 缺 until（欠账必须有到期）：{it}")
    return m


def matched(files: list[str], patterns: list[str]) -> list[str]:
    return [f for f in files if any(fnmatch.fnmatch(f, p) for p in patterns)]


def find_entry(entries: list[dict], path: str) -> dict | None:
    for e in entries:
        pat = e.get("path") or e.get("glob")
        if pat and fnmatch.fnmatch(path, pat):
            return e
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="仓库 ↔ 生产 内容级对拍")
    ap.add_argument("--remote", default=None)
    ap.add_argument("--path", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    m = load_manifest()
    remote = a.remote or m.get("remote", "gz")
    path = a.path or m.get("path", "/opt/mnemosyne")

    files = tracked()
    deploy_set = matched(files, m["deploy"])
    if not deploy_set:
        print("❌ deploy 清单没有命中任何文件（模式写错了？）", file=sys.stderr)
        return 2

    try:
        rh = remote_hashes(remote, path, deploy_set)
        prod_code = remote_code_files(remote, path)
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2

    missing, differ, known = [], [], []
    for f in deploy_set:
        e = find_entry(m.get("known_diff", []), f)
        if f not in rh:
            # 缺也得能登记：路径漂移（仓库 cron/x.sh vs 生产 /x.sh）就是「缺」的形态
            (known if e else missing).append((f, e))
        elif rh[f] != sha(os.path.join(ROOT, f)):
            (known if e else differ).append((f, e))

    deploy_set_set = set(deploy_set)
    prod_only_ok, extra_viol = [], []
    for f in prod_code:
        if f in deploy_set_set:
            continue
        e = find_entry(m.get("prod_only", []), f)
        (prod_only_ok if e else extra_viol).append((f, e))

    violations = len(missing) + len(differ) + len(extra_viol)
    if a.json:
        print(json.dumps({
            "remote": remote, "path": path,
            "deploy_files": len(deploy_set), "prod_hit": len(rh),
            "missing": missing,
            "differ": [f for f, _ in differ],
            "extra": [f for f, _ in extra_viol],
            "known_diff": [{"path": f, "until": (e or {}).get("until")} for f, e in known],
            "violations": violations,
        }, ensure_ascii=False, indent=2))
        return 0 if violations == 0 else 1

    print(f"部署面 {len(deploy_set)} 个文件 ｜ 生产命中 {len(rh)} ｜ "
          f"已登记欠账 {len(known)} ｜ 生产独有(合法) {len(prod_only_ok)}")
    if violations == 0:
        print("✅ prod-diff：部署面无未登记漂移")
        if known:
            print("   ⚠️ 仍有 %d 条已登记欠账（known_diff，含缺文件/内容差异）—— "
                  "它们不是绿，是记账；到期未还会在下次审计里被点名" % len(known))
        return 0
    print(f"❌ prod-diff：{violations} 处未登记漂移")
    for label, items in (("生产缺", missing), ("内容不同", differ),
                         ("生产多出未登记", extra_viol)):
        if not items:
            continue
        print(f"\n[{label}] {len(items)} 个")
        for it in items[:40]:
            f = it if isinstance(it, str) else it[0]
            print(f"   - {f}")
        if len(items) > 40:
            print(f"   … 另有 {len(items) - 40} 个")
    print("\n处置：这是本次预期改动 → 部署过去；长期差异 → 写进 deploy/prod-manifest.json"
          "（prod_only 给 why / known_diff 给 why+until），否则它就该红。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
