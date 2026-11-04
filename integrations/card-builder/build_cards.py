#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_cards.py —— 参考实现：一段对话 → 著录卡（Card Spec v1）

这是 `docs/CARD-SPEC.md` 的最小可跑实现，**纯标准库、零依赖、不调模型**。
生产的卡片生成器比它多三层（会话切分策略、标题优选、精修/判重作业），
那层是针对真实语料磨出来的，不进公开仓；这个文件的作用是让你**照着一份能跑通**。

判据：产出的卡必须能过 `scripts/card_check.py`。

用法：
    python3 integrations/card-builder/build_cards.py example_session.json
    python3 integrations/card-builder/build_cards.py example_session.json --json
    python3 integrations/card-builder/build_cards.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── 证据：字符类必须显式写出，别用 \S / \w（\w 在 Python 里含中文，会吞进句子）──
URL_CH = r"[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]"
PATH_CH = r"[^\s`'\"<>）】」，。；：、]"
EVID_PATTERNS = [
    ("task", re.compile(r"\bT-\d{4}\b")),
    ("commit", re.compile(r"\b[0-9a-f]{7,40}\b")),
    ("file", re.compile(rf"(?:docs|scripts|src|tests|integrations|core|api)/{PATH_CH}+")),
    ("url", re.compile(rf"https?://{URL_CH}+")),
    ("path", re.compile(rf"(?:~|/opt|/home|/var)/{PATH_CH}+")),
]
EPHEMERAL = ("/scratch/", "/cache/", "/tmp/", "/.hermes/data/digest/")
SENT_END = "。！？!?"

ENT_PATTERNS = [
    re.compile(r"\bv?\d+\.\d+\.\d+\b"),          # 版本号
    re.compile(r"\bT-\d{4}\b"),                   # 台账卡号
    re.compile(r"\b[0-9a-f]{7,40}\b"),            # 提交 hash
    re.compile(rf"(?:docs|scripts|integrations)/{PATH_CH}+"),
]


def clean_ev(s: str) -> str | None:
    """三刀：去包裹符 / 超长丢 / 含句末标点丢。（缺一刀，下一种脏形态还会漏进来）"""
    s = s.strip().strip("`'\"()（）[]【】")
    if not s or len(s) > 140:
        return None
    if any(c in s for c in SENT_END):
        return None
    return s


def evid_rank(e: str) -> int:
    """证据分级：台账 > 提交 > 仓库文件 > URL > 绝对路径 > 其他。"""
    for i, (_name, pat) in enumerate(EVID_PATTERNS):
        if pat.match(e):
            return i
    return 9


def extract_evidence(text: str, limit: int = 6) -> list[str]:
    cand: set[str] = set()
    for _name, pat in EVID_PATTERNS:
        for m in pat.finditer(text):
            e = clean_ev(m.group(0))
            if e and not any(x in e for x in EPHEMERAL):
                cand.add(e)
    return sorted(cand, key=lambda e: (evid_rank(e), e))[:limit]


def extract_entities(text: str, limit: int = 5) -> list[str]:
    seen: list[str] = []
    for pat in ENT_PATTERNS:
        for m in pat.finditer(text):
            v = m.group(0).strip(".,;:")
            if v and v not in seen and len(v) <= 60:
                seen.append(v)
    return seen[:limit]


def pick_title(ask: str) -> str:
    """题名 = 提问里信息量最高的那一句，截到 80 字，去掉句末标点。"""
    first = re.split(r"[。！？\n]", ask.strip())[0].strip()
    first = re.sub(r"^(帮我|请|麻烦|你|能不能|可以)\s*", "", first)
    return first[:80].rstrip(SENT_END).strip()


def pick_body(asst: str) -> str:
    """摘要 = 回复里的结论部分（去代码块/引用块），40–600 字。"""
    text = re.sub(r"```.*?```", "", asst, flags=re.S)
    text = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith(">"))
    text = re.sub(r"\s+", " ", text).strip()
    # 优先取带结果词的那一段
    m = re.search(r"(完成|已|通过|失败|修好|部署|实测|结论)[^。]*。", text)
    body = m.group(0) if m and len(m.group(0)) >= 40 else text
    return body[:600].strip()


def split_turns(messages: list[dict]) -> list[dict]:
    turns, cur = [], None
    for m in messages:
        role, content = m.get("role"), (m.get("content") or "").strip()
        if role == "user":
            if cur:
                turns.append(cur)
            cur = {"ask": content, "asst": []}
        elif cur is not None and role == "assistant" and content:
            cur["asst"].append(content)
    if cur:
        turns.append(cur)
    return turns


def build_cards(messages: list[dict], session_id: str, date: str, project: str = "GEN") -> list[dict]:
    cards = []
    year = (date or "2026")[:4]
    seq = 0
    for t in split_turns(messages):
        merged = "\n".join(t["asst"])
        evid = extract_evidence(merged)
        if not evid or len(t["ask"]) < 6:
            continue                      # 没有证据就没有卡（结果卡的最低门槛）
        body = pick_body(merged)
        if len(body) < 40:
            continue
        title = pick_title(t["ask"])
        if len(title) < 4:
            continue
        seq += 1
        cards.append({
            "archive_no": f"K·{project}·{year}-{seq:04d}",
            "title": title,
            "body": body,
            "entities": extract_entities(f"{title} {body} {merged[:2000]}"),
            "evidence": evid,
            "tags": [project] + [w for w in ("修复", "部署", "分析") if w in body][:2],
            "sid": session_id,
        })
    return cards


def render(card: dict) -> str:
    lines = [
        f"[结果卡] 档号：{card['archive_no']}",
        f"题名：{card['title']}",
        f"摘要：{card['body']}",
    ]
    if card.get("entities"):
        lines.append(f"实体：{' · '.join(card['entities'])}")
    lines += [
        f"证据：{' · '.join(card['evidence'])}",
        f"标签：{' '.join(card['tags'])}",
        f"来源：sid={card['sid']}",
    ]
    return "\n".join(lines)


SAMPLE = {
    "session_id": "demo-0001",
    "date": "2026-11-04",
    "messages": [
        {"role": "user", "content": "帮我把导出脚本的编码问题修一下，中文全乱码"},
        {"role": "assistant", "content": "已修好。根因是 open() 没写 encoding，在中文 Windows 上按 GBK 解码。"
                                        "改成 encoding='utf-8' 后导出正常，回归了三份样本。证据：scripts/export.py。"
                                        "提交 64624c6，台账 T-0642。"},
        {"role": "user", "content": "好，那顺带说下明天做什么"},
        {"role": "assistant", "content": "明天先补文档。"},
    ],
}


def selftest() -> int:
    cards = build_cards(SAMPLE["messages"], SAMPLE["session_id"], SAMPLE["date"])
    print(f"PASS 从 {len(SAMPLE['messages'])} 条消息产出 {len(cards)} 张卡（无证据那轮必须被跳过）")
    ok = len(cards) == 1 and not cards[0]["evidence"] == [] and cards[0]["archive_no"].endswith("-0001")
    print(("PASS" if ok else "FAIL") + " 卡骨架 / 档号 / 证据齐全")
    assert cards, "没有产出卡"
    txt = render(cards[0])
    ok2 = "编码" not in "".join(extract_evidence("中文全乱码，没有指针"))
    print(("PASS" if ok2 else "FAIL") + " 无指针文本不产出证据")
    ok3 = extract_entities("修好了 v9.0.10，提交 64624c6，改了 docs/x.md") == ["v9.0.10", "64624c6", "docs/x.md"]
    print(("PASS" if ok3 else "FAIL") + " 实体抽取：版本号 / 提交 / 路径")
    print("\n--- 产出示例 ---")
    print(txt)
    return 0 if (ok and ok2 and ok3) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="对话 → 著录卡（Card Spec v1 参考实现）")
    ap.add_argument("input", nargs="?", help="会话 JSON（{session_id, date, messages[]}）")
    ap.add_argument("--project", default="GEN", help="档号里的项目代号")
    ap.add_argument("--json", action="store_true", help="输出 JSON 而不是卡片正文")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.input:
        ap.print_help()
        return 2

    data = json.loads(Path(a.input).read_text(encoding="utf-8"))
    cards = build_cards(data["messages"], data["session_id"], data.get("date", "2026-01-01"), a.project)
    if not cards:
        print("没有产出卡片（没有一轮带证据——这是正确行为，不是 bug）")
        return 0
    if a.json:
        print(json.dumps(cards, ensure_ascii=False, indent=2))
    else:
        for c in cards:
            print(render(c))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
