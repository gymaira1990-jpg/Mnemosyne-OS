#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_recall.py —— 召回评测（recall@k），公开仓可复现的那一版

为什么有它：README 里的 90% 是第一方自测，评测脚本与标注在作者私有侧（标注指向真实记忆，没法脱敏）。
  这个脚本把**判据**开源出来：你灌自己的数据、写自己的 golden，用同一套尺子量。
  判据本身很简单 —— 期望的那条，在不在前 k 条里。

怎么用（三步）：
    bash scripts/bootstrap.sh                      # 起库起服务
    python3 scripts/seed_demo.py                   # 灌 5 条演示数据（user_id=demo）
    make eval                                      # 跑 evals/demo_cases.jsonl

    # 换自己的数据：
    python3 scripts/eval_recall.py --cases my_cases.jsonl --user me --k 10

cases 格式（JSONL，一行一条）：
    {"q": "数据库每天几点备份", "expect": ["03:00", "备份"], "note": "可选说明"}
    expect 是**或**关系：任意一个出现在前 k 条里就算命中。

通道说明（重要）：服务端 `/memory-os/recall` 只出 E/C/T；S（语义）要客户端叠加。
  本脚本默认 `--channels ect`，加 `--semantic` 会额外调一次语义检索再合并去重（更接近生产检索器的四通道）。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def post(url: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_candidates(base: str, q: str, user: str, k: int, semantic: bool) -> list[str]:
    """返回候选正文列表（按服务端排序）。E/C/T 必有；semantic=True 再叠一路 S。"""
    out: list[str] = []
    try:
        d = post(f"{base.rstrip('/')}/api/v1/memory-os/recall",
                 {"user_id": user, "query": q, "k": k})
        for c in d.get("candidates", []) or []:
            txt = c.get("head") or c.get("content") or ""
            if txt:
                out.append(txt)
    except urllib.error.URLError as e:
        raise SystemExit(f"❌ 连不上服务 {base}：{e}\n   先跑 `bash scripts/bootstrap.sh` 或确认 BASE_URL")
    if semantic:
        try:
            d2 = post(f"{base.rstrip('/')}/api/v1/memories/search",
                      {"user_id": user, "query": q, "top_k": k})
            for m in (d2.get("memories") or d2.get("results") or []):
                txt = m.get("content") or ""
                if txt and txt not in out:
                    out.append(txt)
        except urllib.error.URLError:
            pass  # 语义那路失败不致命：E/C/T 的结果仍作数（与生产一致：S 是叠加）
    return out[:k]


def judge(rows: list[str], expect: list[str], k: int) -> tuple[bool, int | None]:
    """命中 = 任一期望词出现在前 k 条里；返回 (是否命中, 首次命中的位次(1 起))。"""
    for i, txt in enumerate(rows, 1):
        if any(e in txt for e in expect):
            return True, i
    return False, None


def run(cases: list[dict], base: str, user: str, k: int, semantic: bool, quiet: bool) -> int:
    hit_n, rows_out = 0, []
    for c in cases:
        rows = fetch_candidates(base, c["q"], user, k, semantic)
        ok, pos = judge(rows, c["expect"], k)
        hit_n += ok
        rows_out.append({"q": c["q"], "hit": ok, "rank": pos, "returned": len(rows)})
        if not quiet:
            mark = f"✅ 第{pos}位" if ok else "❌ 未命中"
            print(f"  {mark:8s} {c['q']}（返回 {len(rows)} 条）")
    n = len(cases) or 1
    rate = hit_n / n
    print(f"\nrecall@{k} = {hit_n}/{n} = {rate:.0%}（{user} · {'E/C/T + S' if semantic else 'E/C/T'}）")
    miss = [r for r in rows_out if not r["hit"]]
    if miss:
        print("未命中清单：")
        for m in miss:
            print(f"  · {m['q']}")
    return 0 if hit_n else 1


# 离线自检：只验判据逻辑，不联网（判据错了，跑多少数据都没意义）
SELFTEST = [
    (["A 有 /var/backups 这条"], ["/var/backups"], True),
    (["无关内容", "第三条才有 200ms"], ["200ms"], True),
    (["完全无关"], ["不存在的词"], False),
    ([], ["任意"], False),
]


def selftest() -> int:
    bad = 0
    for rows, expect, want in SELFTEST:
        got, _pos = judge(rows, expect, len(rows) or 10)
        ok = got == want
        bad += not ok
        print(("PASS" if ok else "FAIL") + f" 判据：{expect} vs {rows[:2]} → {got}（期望 {want}）")
    # 位置判据：第 3 条命中必须报 rank=3
    _ok, pos = judge(["a", "b", "c-200ms"], ["200ms"], 10)
    good_pos = pos == 3
    bad += not good_pos
    print(("PASS" if good_pos else "FAIL") + f" 位次判据：期望 3，实际 {pos}")
    print(f"\n自检：{'全过' if not bad else f'失败 {bad} 项'}")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="召回评测 recall@k")
    ap.add_argument("--cases", default="evals/demo_cases.jsonl")
    ap.add_argument("--base-url", default="http://127.0.0.1:8010")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--semantic", action="store_true", help="额外叠加 S 语义通道")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    p = Path(a.cases)
    if not p.exists():
        print(f"❌ 找不到用例文件 {p}（示例：evals/demo_cases.jsonl）")
        return 2
    cases = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if a.json:
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run(cases, a.base_url, a.user, a.k, a.semantic, True)
        print(json.dumps({"cases": len(cases), "rc": rc, "detail": buf.getvalue().strip()},
                         ensure_ascii=False))
        return rc
    return run(cases, a.base_url, a.user, a.k, a.semantic, a.quiet)


if __name__ == "__main__":
    sys.exit(main())
