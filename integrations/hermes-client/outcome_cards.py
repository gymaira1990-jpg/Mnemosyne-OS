#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Memory OS 8.0.1 · 结果卡生成器（outcome cards）

设计口径（2026-10-26 v0.7 方案 §4）：
  · 轮起点 = role='user' 的消息（实测 100%，不用「汇报完毕请指示」—— 仅 57% 覆盖）
  · 只收「有结果的东西」：该轮出现可验证产物（文件/URL/哈希/编号/版本）或明确结论/根因
    ⇒ 建卡；纯讨论/寒暄 ⇒ 返回 None，不建卡（原文仍在 state.db，可 FTS 回查）
  · 全摘录，不调模型（0 token）
  · 钩子 msg_from/msg_to ⇒ 直查 state.db 原文

对外：
    build_cards(messages, session_id) -> list[dict]   # 干跑/生成
    push_cards(cards, dry_run=False, api=None) -> dict # 写入 Mnemosyne
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

MNEMOSYNE_API = os.environ.get("MNEMOSYNE_API", "http://127.0.0.1:18010/api/v1/memories")

# 证据指针：路径 / URL / 长哈希 / 台账编号 / issue 号 / 版本号
_EVID = re.compile(
    r"(?:/[\w.\-/]{6,}|https?://\S+|\b[0-9a-f]{8,40}\b|T-\d{4}|#\d{3,}|v?\d+\.\d+\.\d+)"
)
# 结论/结果性词
_RESULT = re.compile(
    r"完成|已(?:经)?(?:上线|部署|修|改|验证|通过|交付|归档|同步|清理)|实测|PASS|FAIL|失败|"
    r"根因|结论|交付|验证|重启|部署|提交|合并|生成|上线"
)
# 摘录时要剔除的行：引用块、代码围栏、mine 的示例行
_SKIP_LINE = re.compile(r"^\s*(?:>|```|\||---|<)")
# 列表符号
_BULLET = re.compile(r"^\s*(?:[-*·]|\d+[.、)]|[①②③④⑤⑥⑦⑧⑨])\s*")
# 系统注入的伪用户消息（后台通知 / OOB / memory-context）——不是用户真问，跳过该轮
_SYSTEM_ASK = re.compile(r"^\s*\[(?:IMPORTANT|OUT-OF-BAND|SYSTEM|System note)", re.I)
# 缩进 4+ 空格的示例/引用块行（正文里展示的样例，不是结论）
_INDENTED = re.compile(r"^(?: {4,}|\t)\S")

# 服务端会静默覆盖 category / importance（实测 outcome→knowledge、0.8→0.5），
# 故改用「内容前缀」做识别 —— 服务端不改内容，这是唯一稳的锚点。
CARD_PREFIX = os.environ.get("MEMOS_CARD_PREFIX", "[结果卡] ")   # 可改英文如 "[outcome] "
CARD_CATEGORY = os.environ.get("MEMOS_CARD_CATEGORY", "worklog")   # 服务端白名单内的类别；语义=工作记录，最贴近"有结果的事"

ASK_LIMIT = 120        # 「问」最多字数
DO_LINES = 3           # 「做」最多行数
LINE_LIMIT = 150       # 单行截断
MAX_EVIDENCE = 6


def _clean_ask(text: str) -> str:
    s = " ".join((text or "").split())
    return s[:ASK_LIMIT]


def _pick_do_lines(text: str) -> list[str]:
    """从回复里挑信息量最高的行（带证据/结论词优先），去掉引用块与代码块。"""
    scored: list[tuple[int, str]] = []
    for raw in (text or "").splitlines():
        if _SKIP_LINE.match(raw) or _INDENTED.match(raw):
            continue
        line = _BULLET.sub("", raw.strip())
        if len(line) < 12:
            continue
        score = 0
        if _EVID.search(line):
            score += 2
        if _RESULT.search(line):
            score += 1
        scored.append((score, line[:LINE_LIMIT]))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, line in scored:
        key = line[:24]
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= DO_LINES:
            break
    return out


def _split_turns(messages) -> list[dict]:
    """按 role='user' 切轮。messages: 可迭代，元素支持 ['id'] / ['role'] / ['content']。"""
    turns, cur = [], None
    for m in messages:
        try:
            mid, role, content = m["id"], m["role"], (m["content"] or "")
        except (KeyError, IndexError, TypeError):
            mid, role, content = getattr(m, "id", 0), getattr(m, "role", ""), getattr(m, "content", "") or ""
        if role == "user":
            if cur:
                turns.append(cur)
            if _SYSTEM_ASK.match(content or ""):
                cur = None          # 系统通知不算一轮（其后续 assistant 回复也不单独建卡）
                continue
            cur = {"ids": [mid], "ask": content, "asst": []}
        elif cur is not None:
            cur["ids"].append(mid)
            if role == "assistant" and content.strip():
                cur["asst"].append(content)
    if cur:
        turns.append(cur)
    return turns


def build_cards(messages, session_id: str) -> list[dict]:
    """生成结果卡（不写库）。无产出的轮次直接跳过。"""
    cards = []
    for seq, t in enumerate(_split_turns(messages), 1):
        ask = _clean_ask(t["ask"])
        if len(ask) < 6:
            continue
        merged = "\n".join(t["asst"])
        evid = sorted({m.group(0) for m in _EVID.finditer(merged)})[:MAX_EVIDENCE]
        has_result = bool(_RESULT.search(merged))
        # 写入判据：有证据指针 或 有明确结论；否则不建卡
        if not evid and not has_result:
            continue
        do_lines = _pick_do_lines(t["asst"][-1] if t["asst"] else "")
        if not do_lines and not evid:
            continue
        body = [f"{CARD_PREFIX}问：{ask}"]
        body += [f"做：{ln}" for ln in do_lines]
        body.append(f"证据：{' · '.join(evid) if evid else '（无指针，仅结论）'}")
        cards.append({
            "content": "\n".join(body),
            "metadata": {
                "session_id": session_id,
                "turn_seq": seq,
                "msg_from": t["ids"][0],
                "msg_to": t["ids"][-1],
                "evidence_count": len(evid),
                "kind": "outcome",
            },
        })
    return cards


def push_cards(cards: list[dict], dry_run: bool = False, api: str = MNEMOSYNE_API) -> dict:
    """逐卡写入 Mnemosyne（category=outcome, importance 0.8）。"""
    if not cards:
        return {"pushed": 0, "skipped": True}
    if dry_run:
        return {"pushed": 0, "dry_run": True, "would_push": len(cards),
                "sample": cards[0]["content"][:300]}
    ok, fail = 0, []
    for c in cards:
        payload = json.dumps({
            "content": c["content"],
            "category": CARD_CATEGORY,
            "importance": 0.8,
            "user_id": "default",
            "source": "memos-8.0.1",
            "metadata": c["metadata"],
        }).encode()
        try:
            req = urllib.request.Request(api, data=payload,
                                        headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                json.loads(resp.read())
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail.append(f"{c['metadata'].get('turn_seq')}:{type(e).__name__}:{e}"[:120])
    return {"pushed": ok, "failed": len(fail), "errors": fail[:3]}


if __name__ == "__main__":  # 自测：用 ./scripts/outcome_cards.py --selftest
    import sys
    if "--selftest" in sys.argv:
        fake = [
            {"id": 1, "role": "user", "content": "帮我把备份修一下"},
            {"id": 2, "role": "assistant", "content": "我先查一下。"},
            {"id": 3, "role": "tool", "content": "..."},
            {"id": 4, "role": "assistant",
             "content": "改完了。\n- 修了 /opt/backup/run.sh 的路径\n- 实测 PASS，备份 596MB\n- 工单 T-1234 已记"},
            {"id": 5, "role": "user", "content": "嗯"},
            {"id": 6, "role": "assistant", "content": "好。"},
        ]
        cards = build_cards(fake, "test-session")
        print(json.dumps(cards, ensure_ascii=False, indent=2))
        assert len(cards) == 1 and cards[0]["metadata"]["turn_seq"] == 1, "应只对第 1 轮建卡"
        print("\nSELFTEST OK — 无产出的第 2 轮被正确跳过")
