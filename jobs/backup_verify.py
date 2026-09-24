#!/usr/bin/env python3
"""
Mnemosyne OS v8.0 · 备份复验作业 (S1-4 后半)
============================================

为什么需要它
------------
真实事故: `backup.sh` 曾**静默失败 36 天**（末次成功 2026-08-18），
原因是日志文件属主被改、`set -e` 在打开重定向时就退出 —— 连报错都进不了日志。
2026-09-23 已修（失败显式写 ALERT 文件）。

但「失败会告警」只回答了一半问题: **备份文件存在 ≠ 备份能用**。
本作业补另一半 —— **可恢复性抽验**:

  V1 新鲜度 : 最新备份的年龄必须 < --max-age-hours（默认 30h，日备留余量）
  V2 体积   : 文件大小 > --min-bytes（默认 1MB；空/截断文件直接判死）
  V3 结构   : `pg_restore --list` 能解析出 TOC —— 这是**真读一遍归档目录**，
              证明文件不是截断/损坏的（比 `ls` 看大小强得多）
  V4 内容   : --deep 时把 `memories` 表**真恢复到临时库**并比对行数
              （可恢复性的最强证据；默认关闭以免拖慢日常巡检）

判据: 任一 V 不过 → 退出码 1，并打印可供告警系统抓取的单行 `ALERT:` 前缀。
本作业**只读**（--deep 只往一次性临时库写，用完即删），绝不触碰生产库。

用法:
  python3 jobs/backup_verify.py                          # V1-V3
  python3 jobs/backup_verify.py --deep                   # +V4 真恢复
  python3 jobs/backup_verify.py --dir /path/to/backups
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def find_latest(directory: str) -> str | None:
    pats = ["*.dump", "*.sql", "*.sql.gz", "*.tar", "*.tar.gz", "backup_*"]
    files: list[str] = []
    for p in pats:
        files.extend(glob.glob(os.path.join(directory, p)))
    files = [f for f in files if os.path.isfile(f)]
    if not files:
        return None
    return max(files, key=lambda f: os.path.getmtime(f))


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError as e:
        return 127, f"命令不存在: {e}"
    except subprocess.TimeoutExpired:
        return 124, f"超时({timeout}s)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Mnemosyne 备份可恢复性复验（只读）")
    ap.add_argument("--dir", default=os.path.expanduser("~/noah-buffer/backups"),
                    help="备份目录")
    ap.add_argument("--max-age-hours", type=float, default=30.0)
    ap.add_argument("--min-bytes", type=int, default=1_000_000)
    ap.add_argument("--deep", action="store_true", help="额外做真实恢复抽验（V4）")
    ap.add_argument("--scratch-db", default="mnemosyne_restore_probe")
    args = ap.parse_args()

    checks: list[tuple[str, bool, str]] = []

    latest = find_latest(args.dir)
    if not latest:
        print(f"ALERT: 备份目录无文件 → {args.dir}")
        return 1

    st = os.stat(latest)
    age_h = (datetime.now(timezone.utc).timestamp() - st.st_mtime) / 3600.0
    size = st.st_size

    # V1 新鲜度
    ok = age_h <= args.max_age_hours
    checks.append(("V1 新鲜度", ok, f"{latest} 年龄 {age_h:.1f}h（阈值 {args.max_age_hours}h）"))

    # V2 体积
    ok2 = size >= args.min_bytes
    checks.append(("V2 体积", ok2, f"{size/1048576:.1f} MB（阈值 {args.min_bytes/1048576:.1f} MB）"))

    # V3 结构：真读归档目录
    if latest.endswith((".sql", ".sql.gz")):
        cmd = ["zcat", latest] if latest.endswith(".gz") else ["cat", latest]
        rc, out = run(cmd, timeout=180)
        toc_n = len(re.findall(r"^CREATE ", out, flags=re.M)) if rc == 0 else 0
        checks.append(("V3 结构", toc_n > 0,
                       f"纯文本 dump：解析到 {toc_n} 条 CREATE 语句" if rc == 0 else f"读取失败 rc={rc}"))
    else:
        rc, out = run(["pg_restore", "--list", latest], timeout=180)
        toc_n = len([l for l in out.splitlines() if re.match(r"^\d+;", l)])
        checks.append(("V3 结构", rc == 0 and toc_n > 0,
                       f"pg_restore --list：{toc_n} 条 TOC 条目" if rc == 0 else f"pg_restore 失败 rc={rc}"))

    # V4 内容：真恢复抽验
    if args.deep:
        db = args.scratch_db
        run(["dropdb", "--if-exists", db])
        rc, out = run(["createdb", db])
        if rc != 0:
            checks.append(("V4 真恢复", False, f"临时库创建失败: {out.strip()[:120]}"))
        else:
            try:
                rc, out = run(["pg_restore", "-d", db, "--no-owner", "--no-privileges",
                               "-t", "memories", latest], timeout=600)
                if rc != 0:
                    checks.append(("V4 真恢复", False, f"恢复失败 rc={rc}: {out.strip()[:160]}"))
                else:
                    p = subprocess.run(["psql", "-d", db, "-tAc", "SELECT count(*) FROM memories"],
                                       capture_output=True, text=True, timeout=120)
                    n = p.stdout.strip()
                    ok4 = p.returncode == 0 and n.isdigit() and int(n) > 0
                    checks.append(("V4 真恢复", ok4, f"恢复后 memories 行数 = {n}"))
            finally:
                run(["dropdb", "--if-exists", db])

    print(f"备份复验 · {datetime.now().strftime('%F %T')} · 目录 {args.dir}")
    all_ok = True
    for name, ok, detail in checks:
        print(f"  {'✅' if ok else '❌'} {name}: {detail}")
        all_ok &= ok
    if not all_ok:
        bad = [n for n, ok, _ in checks if not ok]
        print(f"ALERT: 备份复验失败 ({', '.join(bad)}) → 最新备份 {latest}")
    else:
        print(f"  判定: OK（{len(checks)}/{len(checks)} 项通过）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
