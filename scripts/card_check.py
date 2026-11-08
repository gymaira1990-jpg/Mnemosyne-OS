#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""card_check.py —— 著录卡（Card Spec v1）机器校验器

规范正文：docs/CARD-SPEC.md
为什么有它：规范写在文档里没人执行，三个月后卡片就会长成十种样子。
  这个脚本让「什么算一张合格的卡」变成一条可跑的判据（CI 与 `make test` 都调得动）。

用法：
    python3 scripts/card_check.py <卡片文件>          # 校验单个文件（一张卡）
    cat card.txt | python3 scripts/card_check.py -    # 从 stdin 读
    python3 scripts/card_check.py --selftest          # 自检（正例必须过、反例必须挂）

退出码：0 = 合格；1 = 不合格（逐条打印原因）
"""
from __future__ import annotations

import argparse
import re
import sys

# ── 规范常量（改这里 = 改规范，必须同步 docs/CARD-SPEC.md）──
PREFIX = "[结果卡]"
ARCHIVE_RE = re.compile(r"^\[结果卡\] 档号：(K·[A-Z][A-Z0-9]{0,9}·\d{4}-\d{4})$")
TITLE_MIN, TITLE_MAX = 4, 80
BODY_MIN, BODY_MAX = 40, 600
EVID_MAX = 6
EVID_LEN_MAX = 140
TAG_MAX = 8
# 证据里出现这些 = 指向一次性文件，跑完即删，等于没有证据
EPHEMERAL = ("/scratch/", "/cache/", "/tmp/", "/.hermes/data/digest/")
SENTENCE_END = "。！？!?"
# 摘要里出现这些词 = 写的是计划不是结果
PLAN_WORDS = ("待补", "TODO", "todo", "下一步再说", "应该会", "预计将")

ORDER = ["档号", "题名", "摘要", "实体", "证据", "标签", "来源"]


def _fields(text: str) -> tuple[dict, list[str], list[str]]:
    """把卡片正文拆成字段；返回 (fields, problems, warnings)。"""
    problems: list[str] = []
    warnings: list[str] = []
    lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return {}, ["空内容"], []

    m = ARCHIVE_RE.match(lines[0])
    if not m:
        problems.append(f"R1 首行必须是 `[结果卡] 档号：K·项目·年-序号`，实际：{lines[0][:60]}")
    fields: dict[str, str] = {"档号": m.group(1) if m else ""}
    order_seen: list[str] = []

    for ln in lines[1:]:
        key, sep, val = ln.partition("：")
        if not sep:
            problems.append(f"R7 出现不成字段的行：{ln[:40]}")
            continue
        if key not in ORDER:
            problems.append(f"R7 未知字段 `{key}`（合法字段：{'/'.join(ORDER[1:])}）")
            continue
        if key in fields:
            problems.append(f"R7 字段 `{key}` 重复出现")
        fields[key] = val.strip()
        order_seen.append(key)

    # 行序：实际出现顺序必须等于规范顺序的子序列
    # （写成「按 ORDER 过滤」会永远通过 —— 那等于没查，实测自检时被自己的反例抓出来）
    expect = [k for k in ORDER if k in order_seen]
    if order_seen != expect:
        # 历史形态：8.x 时代实体行写在末尾（实测生产库存量卡里就有）。
        # 去掉实体行后顺序一致 ⇒ 只算「历史形态」，降级为提醒，不算不合格。
        if [k for k in order_seen if k != "实体"] == [k for k in expect if k != "实体"]:
            warnings.append("R7 实体行在末尾（8.x 历史形态；9.0 规范是放在证据之前）")
        else:
            problems.append(f"R7 字段顺序不对：实际 {'→'.join(order_seen)}，应为 {'→'.join(expect)}")
    return fields, problems, warnings


def check(text: str) -> tuple[list[str], list[str]]:
    """返回 (problems, warnings)；problems 为空 = 合格。"""
    f, problems, warnings = _fields(text)

    # R2 题名
    title = f.get("题名", "")
    if not title:
        problems.append("R2 缺题名")
    elif not (TITLE_MIN <= len(title) <= TITLE_MAX):
        problems.append(f"R2 题名长度 {len(title)} 不在 {TITLE_MIN}-{TITLE_MAX}")
    elif "\n" in title or title.endswith(SENTENCE_END):
        problems.append("R2 题名不该是句子（去掉句末标点）")

    # R3 摘要
    body = f.get("摘要", "")
    if not body:
        problems.append("R3 缺摘要")
    elif not (BODY_MIN <= len(body) <= BODY_MAX):
        problems.append(f"R3 摘要长度 {len(body)} 不在 {BODY_MIN}-{BODY_MAX}")
    for w in PLAN_WORDS:
        if w in body:
            problems.append(f"R3 摘要里出现「{w}」——卡片记的是发生过的事，不是计划")

    # R4 证据
    evid_raw = f.get("证据", "")
    if not evid_raw:
        problems.append("R4 缺证据行（没有证据的卡不是结果卡）")
    else:
        items = [e.strip() for e in evid_raw.split("·") if e.strip()]
        if not items:
            problems.append("R4 证据行为空")
        if len(items) > EVID_MAX:
            problems.append(f"R4 证据 {len(items)} 项超过上限 {EVID_MAX}")
        for e in items:
            if e in ("无指针", "（无指针，仅结论）"):
                continue
            if len(e) > EVID_LEN_MAX:
                problems.append(f"R4 证据过长（{len(e)} 字，疑似吞了句子）：{e[:40]}…")
            if any(c in e for c in SENTENCE_END):
                problems.append(f"R4 证据含句末标点（是句子片段不是指针）：{e[:40]}")
            if any(x in e for x in EPHEMERAL):
                problems.append(f"R4 证据指向一次性目录（跑完即删）：{e[:60]}")

    # R5 标签
    tags = [t for t in f.get("标签", "").split() if t]
    if not tags:
        problems.append("R5 缺标签")
    elif len(tags) > TAG_MAX:
        problems.append(f"R5 标签 {len(tags)} 个超过上限 {TAG_MAX}")

    # R6 来源
    src = f.get("来源", "")
    if not src.startswith("sid=") or len(src) <= 4:
        problems.append("R6 来源必须是 `sid=<会话 id>`")

    return problems, warnings


GOOD = """[结果卡] 档号：K·GEN·2026-0841
题名：修 SVG 箭头不显示
摘要：定位到 marker 的 id 与 defs 里的引用对不上，改成显式 url(#id) 后箭头正常显示，回归了同页另外两处图标。
实体：v9.0.10 · T-0642 · docs/CARD-SPEC.md
证据：T-0642 · 64624c6 · docs/CARD-SPEC.md
标签：svg 前端 修复
来源：sid=2f1c9a3e-7b41-4c8e-9d2a-0f6b5c1e8a77"""

BAD = [
    ("缺档号", GOOD.replace("[结果卡] 档号：K·GEN·2026-0841\n", "")),
    ("摘要太短", GOOD.replace("摘要：定位到 marker 的 id 与 defs 里的引用对不上，改成显式 url(#id) 后箭头正常显示，回归了同页另外两处图标。", "摘要：修好了")),
    ("证据是残句", GOOD.replace("证据：T-0642 · 64624c6 · docs/CARD-SPEC.md", "证据：T-0642 · 这个我看了半天应该就是这里的问题。")),
    ("证据指向 scratch", GOOD.replace("证据：T-0642 · 64624c6 · docs/CARD-SPEC.md", "证据：/home/x/scratch/probe.py")),
    ("缺来源", GOOD.replace("来源：sid=2f1c9a3e-7b41-4c8e-9d2a-0f6b5c1e8a77", "来源：无")),
    ("字段顺序乱", GOOD.replace("题名：修 SVG 箭头不显示\n摘要：", "摘要：").replace("实体：v9.0.10 · T-0642 · docs/CARD-SPEC.md", "实体：v9.0.10 · T-0642 · docs/CARD-SPEC.md\n题名：修 SVG 箭头不显示")),
]


def selftest() -> int:
    bad = []
    ok_problems, ok_warn = check(GOOD)
    print(f"{'PASS' if not ok_problems else 'FAIL'} 正例应通过；问题={ok_problems} 提醒={ok_warn}")
    if ok_problems:
        bad.append("正例未通过")
    for name, sample in BAD:
        probs, _w = check(sample)
        print(f"{'PASS' if probs else 'FAIL'} 反例「{name}」应判红；问题={probs[:1]}")
        if not probs:
            bad.append(name)
    print(f"\n自检结果：{'全过' if not bad else '失败 ' + str(bad)}")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="著录卡规范校验（docs/CARD-SPEC.md）")
    ap.add_argument("path", nargs="?", help="卡片文件路径；`-` = stdin")
    ap.add_argument("--selftest", action="store_true", help="跑内置正反例自检")
    ap.add_argument("--jsonl", action="store_true",
                    help="把 path 当 JSONL，逐行取 content 校验（evals/demo_cards.jsonl 用这个）")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.jsonl:
        if not a.path:
            print("需要 JSONL 路径", file=sys.stderr)
            return 2
        return _check_jsonl(a.path)
    if not a.path:
        ap.print_help()
        return 2

    text = sys.stdin.read() if a.path == "-" else open(a.path, encoding="utf-8").read()
    problems, warnings = check(text)
    for w in warnings:
        print("⚠️ ", w)
    if problems:
        print(f"❌ 不合格（{len(problems)} 项）：")
        for p in problems:
            print("   ·", p)
        return 1
    print("✅ 符合 Card Spec v1")
    return 0


def _check_jsonl(path: str) -> int:
    """JSONL 逐条校验（DSH 审计 D-2，2026-11-08）。

    以前 `card_check.py evals/demo_cards.jsonl` 会直接 exit 1 ——
    因为它把整个 JSONL 当成一张卡的正文去校验。"40 卡全过"只能人工抽，无法自动化。
    """
    import json

    total = bad = 0
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                content = json.loads(line).get("content") or ""
            except Exception as e:  # noqa: BLE001
                bad += 1
                print(f"❌ 第 {lineno} 行 JSON 解析失败：{e}")
                continue
            problems, _warnings = check(content)
            if problems:
                bad += 1
                print(f"❌ 第 {lineno} 行不合格（{len(problems)} 项）：{'; '.join(problems[:3])}")
    print(f"\n共 {total} 条，不合格 {bad} 条")
    return 1 if bad else 0


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
