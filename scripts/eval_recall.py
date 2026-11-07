#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_recall.py —— 召回评测（recall@k）＋ 尺子自检

为什么有它：README 里的 90% 是第一方自测，评测脚本与标注在作者私有侧（标注指向真实记忆，没法脱敏）。
  这个脚本把**判据**开源出来：你灌自己的数据、写自己的 golden，用同一套尺子量。

2026-11-07 补的两件事（此前这把尺子分不出好坏）：
  1. **负样本**：`{"q": ..., "forbid": ["不该出现的词"]}` —— 库里根本没有答案，
     好检索器不该把禁词顶上来；只会「有返回就算命中」的尺子永远给满分。
  2. **区分度自检**：把同一批结果**倒序**再判一次。
     如果倒序分数 ≈ 正序分数，说明这些题与排序无关 —— 尺子无效（`--strict` 下直接失败）。
     实测价值：LCS 基线曾拿 12/12，正是缺这两条。

怎么用（三步）：
    bash scripts/bootstrap.sh                      # 起库起服务
    python3 scripts/seed_demo.py                   # 灌演示数据（user_id=demo）
    make eval                                      # 跑 evals/demo_cases.jsonl

    # 换自己的数据：
    python3 scripts/eval_recall.py --cases my_cases.jsonl --user me --k 10

cases 格式（JSONL，一行一条）：
    {"q": "数据库每天几点备份", "expect": ["03:00", "备份"], "note": "可选"}
    {"q": "我们和客户签的违约金比例", "forbid": ["违约金", "违约"], "note": "负样本：库里没有这条"}
  expect 是**或**关系：任意一个出现在前 k 条里就算命中。
  forbid 是该题的反向判据：**任意一个**出现在前 k 条里就算失败（负样本）。

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

# 区分度判据（2026-11-07 修正）：倒序不改变「是否在前 k 条」，靠它测区分度是错的。
# 真正的失效形态是「题太容易」——什么时候返回什么都能进前 k，分数必然满分。
# 所以判据改成两条：① 宽 k 不能满分；② 紧 k 必须比宽 k 低（说明位次有意义）。
TIGHT_K = 3


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


def judge(rows: list[str], expect: list[str], k: int,
          forbid: list[str] | None = None) -> tuple[bool, int | None]:
    """判定一条用例。

    正向（有 expect）：任一期望词出现在前 k 条 → 命中，返回首次位次。
    负向（有 forbid） ：**任一**禁词出现在前 k 条 → 未命中（不该被检索出来）。
    两者都没有     ：判为无效用例，直接抛错（避免默默算成通过）。
    """
    head = rows[:k]
    if forbid:
        for i, txt in enumerate(head, 1):
            if any(f in txt for f in forbid):
                return False, i
        return True, None
    if not expect:
        raise ValueError("用例既没有 expect 也没有 forbid，无法判定")
    for i, txt in enumerate(head, 1):
        if any(e in txt for e in expect):
            return True, i
    return False, None


def _score(cases: list[dict], results: dict[int, list[str]], k: int) -> tuple[float, int]:
    hit = 0
    for i, c in enumerate(cases):
        ok, _pos = judge(results[i], c.get("expect") or [], k, c.get("forbid"))
        hit += ok
    return hit / (len(cases) or 1), hit


def run(cases: list[dict], base: str, user: str, k: int, semantic: bool, quiet: bool,
        strict: bool = False) -> int:
    results: dict[int, list[str]] = {}
    for i, c in enumerate(cases):
        results[i] = fetch_candidates(base, c["q"], user, k, semantic)

    rate, hits = _score(cases, results, k)
    tight_rate, tight_hits = _score(cases, results, min(TIGHT_K, k))

    if not quiet:
        for i, c in enumerate(cases):
            ok, pos = judge(results[i], c.get("expect") or [], k, c.get("forbid"))
            kind = "负样本" if c.get("forbid") else "正向"
            mark = (f"✅ 第{pos}位" if ok else "❌ 未命中") if pos else ("✅ 未浮现" if ok else "❌ 被顶上来")
            print(f"  {mark:10s} [{kind}] {c['q']}（返回 {len(results[i])} 条）")

    n = len(cases)
    print(f"\nrecall@{k} = {hits}/{n} = {rate:.0%}"
          f"（{user} · {'E/C/T + S' if semantic else 'E/C/T'}）")
    sep = rate - tight_rate
    print(f"区分度自检：recall@{k} {rate:.0%} ｜ recall@{min(TIGHT_K, k)} {tight_rate:.0%}"
          f" ｜ 位次差 {sep:+.0%}")
    if rate >= 1.0:
        print("⚠️ 尺子无效：全部命中 ⇒ 任何「把库倒出来」的系统都能满分，这个百分比说明不了检索好坏")
        print("   处置：加负样本（forbid）、换更刁的题，或把 k 调小")
    elif sep <= 0:
        print("⚠️ 尺子偏软：紧 k 与宽 k 一样高 ⇒ 位次无区分（答对的都排在最前，题太容易）")
    else:
        print(f"✅ 尺子有效：位次越紧分数越低（{sep:+.0%}）⇒ 分数确实反映排序质量")

    miss = [c["q"] for i, c in enumerate(cases)
            if not judge(results[i], c.get("expect") or [], k, c.get("forbid"))[0]]
    if miss:
        print("未命中清单：")
        for q in miss:
            print(f"  · {q}")

    if strict and (hits == 0 or rate >= 1.0):
        return 1
    return 0


# 离线自检：只验判据逻辑，不联网（判据错了，跑多少数据都没意义）
SELFTEST = [
    # (rows, expect, forbid, 期望命中)
    (["A 有 /var/backups 这条"], ["/var/backups"], None, True),
    (["无关内容", "第三条才有 200ms"], ["200ms"], None, True),
    (["完全无关"], ["不存在的词"], None, False),
    ([], ["任意"], None, False),
    # 负样本：禁词出现即失败
    (["客户违约金是 5%"], None, ["违约金"], False),
    (["今天天气不错"], None, ["违约金"], True),
]


def selftest() -> int:
    bad = 0
    for rows, expect, forbid, want in SELFTEST:
        got, _pos = judge(rows, expect or [], len(rows) or 10, forbid)
        ok = got == want
        bad += not ok
        tag = "负样本" if forbid else "正向"
        print(("PASS" if ok else "FAIL") + f" 判据[{tag}]：{expect or forbid} vs {rows[:2]} → {got}（期望 {want}）")
    _ok, pos = judge(["a", "b", "c-200ms"], ["200ms"], 10)
    bad += pos != 3
    print(("PASS" if pos == 3 else "FAIL") + f" 位次判据：期望 3，实际 {pos}")
    # 非法用例必须报错，而不是默默算通过
    try:
        judge(["x"], [], 10)
        print("FAIL 非法用例（无 expect/forbid）应报错，实际通过了")
        bad += 1
    except ValueError:
        print("PASS 非法用例（无 expect/forbid）已报错")
    print(f"\n自检：{'全过' if not bad else f'失败 {bad} 项'}")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="召回评测 recall@k + 区分度自检")
    ap.add_argument("--cases", default="evals/demo_cases.jsonl")
    ap.add_argument("--base-url", default="http://127.0.0.1:8010")
    ap.add_argument("--user", default="demo")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--semantic", action="store_true", help="额外叠加 S 语义通道")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="区分度不足或零命中时返回非零（CI 用）")
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
            rc = run(cases, a.base_url, a.user, a.k, a.semantic, True, a.strict)
        print(json.dumps({"cases": len(cases), "rc": rc, "detail": buf.getvalue().strip()},
                         ensure_ascii=False))
        return rc
    return run(cases, a.base_url, a.user, a.k, a.semantic, a.quiet, a.strict)


if __name__ == "__main__":
    sys.exit(main())
