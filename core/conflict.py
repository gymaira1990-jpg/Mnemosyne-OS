"""冲突检测：找出「同一个说法、不同数字」的记忆对（2026-11-07）

为什么先做检测、不先定权重规则：
    「前段说 A、回捞说 B，该信谁」这种规则，没有真实样本就只能拍脑袋。
    先把冲突**找出来**，看一眼真实冲突长什么样，再定裁决规则 —— 否则规则是想象的。

判据（不用 LLM，可解释、零成本）：
    1. 从正文里抽「数字 + 单位」（8 份 / 200ms / 340 元 / 5% …）；
    2. 取数字前后的上下文窗口；
    3. 两条记忆若**单位相同、上下文高度重合、数字不同** ⇒ 疑似冲突。
    只报「疑似」，最终由人裁 —— 这正是 9.0.23–25 那条求证/裁决链路该接的地方。
"""
from __future__ import annotations

import re
from typing import Iterable

UNIT_PATTERN = r"(?:份|天|小时|分钟|秒|毫秒|ms|元|%|GB|MB|KB|条|个|次|人|轮|张|台|核|G|T)"
NUM_UNIT_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({UNIT_PATTERN})", re.IGNORECASE)
CTX = 20                 # 数字前后各取多少字符作为「语境」
MIN_CTX_OVERLAP = 0.85   # 语境字面重合度门槛
MIN_COMMON_RUN = 4       # 语境之间必须有这么长的**连续**公共子串，才算「同一个说法」
# 为什么是 4：中文里「保留最近 8 份」这类短句，去掉了数字之后剩下的连续公共部分
# 也就 4 个字（「保留最近」）。调到 6 会把真冲突也一起滤掉（实测 3000 张卡 → 0 对）。

# 2026-11-07 实测调参记录（都是真实数据上的教训）：
#   初版 CTX=12 / 重合 0.6 ⇒ 3000 张卡报 331 对，抽样看几乎全是误报：
#     「48 条」vs「635 条」、「0.12 元」vs「286.86 元」、「47%」vs「19%」——
#     条/元/% 这类单位太泛，中文语境里 12 字的二元组重合很容易到 0.6。
#   收紧到 CTX=20 / 重合 0.85，并要求连续 6 字公共子串（真·同一说法才算）。


def _bigrams(text: str) -> set[str]:
    t = "".join(ch for ch in (text or "") if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else set()


def extract_facts(text: str) -> list[dict]:
    """抽出「数字 + 单位 + 语境」。语境用于判断两条说的是不是同一件事。"""
    out = []
    for m in NUM_UNIT_RE.finditer(text or ""):
        start, end = m.start(), m.end()
        ctx = (text[max(0, start - CTX):start] + " " + text[end:end + CTX]).strip()
        out.append({"value": m.group(1), "unit": m.group(2).lower(), "context": ctx,
                    "raw": m.group(0)})
    return out


def topic_of(text: str) -> str:
    """取「题名」当作主题；没有就用正文前 40 字。

    为什么必须要主题：结果卡是模板化的（档号/题名/摘要/证据/标签/实体），
    尾部字段（路径、URL、标签）大量重复，数字常落在这些重复区域 ——
    光看「数字相邻的字符」会把「2.2G 僵尸占用」和「1.53 G 代币」当成同一件事。
    """
    m = re.search(r"题名[：:]\s*(.+?)\s*(?:摘要|证据|标签|实体|来源|$)", text or "", re.S)
    return (m.group(1) if m else (text or "")[:40]).strip()


def _body_only(text: str) -> str:
    """只保留「题名 + 摘要」正文，砍掉证据/标签/来源/实体这些元数据段。"""
    cut = len(text or "")
    for marker in ("证据：", "证据:", "标签：", "来源：", "实体："):
        i = (text or "").find(marker)
        if i > 0:
            cut = min(cut, i)
    return (text or "")[:cut]


def _ctx_overlap(a: str, b: str) -> float:
    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / min(len(ba), len(bb))


def _longest_common_run(a: str, b: str) -> int:
    """最长连续公共子串长度 —— 「同一个说法」应该是连续文字，不是零散字的重合。"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b)).size


def detect_conflicts(items: Iterable[dict], min_overlap: float = MIN_CTX_OVERLAP,
                     min_run: int = MIN_COMMON_RUN, min_topic_overlap: float = 0.4) -> list[dict]:
    """items: [{"id"/"no": ..., "head"/"content": 文本}]，返回疑似冲突对。

    min_topic_overlap：两条记忆的**题名**必须相似到这个程度，才值得比数字。
    2026-11-07 实测：不做主题约束时，3000 张卡报 5 对，人工看完 **5/5 全是假阳性** ——
    模板化结果卡的「证据/标签」段大量重复，数字撞在一起纯属格式巧合。
    """
    items = [{"key": i.get("no") or i.get("id"), "text": i.get("head") or i.get("content") or ""}
             for i in items]
    topics = {it["key"]: _bigrams(topic_of(it["text"])) for it in items}
    bodies = {it["key"]: _body_only(it["text"]) for it in items}
    facts = [(it["key"], f) for it in items for f in extract_facts(bodies[it["key"]])]

    conflicts = []
    for i in range(len(facts)):
        k1, f1 = facts[i]
        for j in range(i + 1, len(facts)):
            k2, f2 = facts[j]
            if k1 == k2 or f1["unit"] != f2["unit"]:
                continue
            if f1["value"] == f2["value"]:
                continue
            ta, tb = topics.get(k1) or set(), topics.get(k2) or set()
            topic_ov = (len(ta & tb) / min(len(ta), len(tb))) if ta and tb else 0.0
            if topic_ov < min_topic_overlap:
                continue          # 说的根本不是同一个主题
            ov = _ctx_overlap(f1["context"], f2["context"])
            if ov < min_overlap:
                continue
            run = _longest_common_run(f1["context"], f2["context"])
            if run < min_run:
                continue          # 数字都对，但说的不是同一句话
            conflicts.append({
                "a": {"key": k1, "value": f1["value"], "unit": f1["unit"], "raw": f1["raw"],
                      "context": f1["context"]},
                "b": {"key": k2, "value": f2["value"], "unit": f2["unit"], "raw": f2["raw"],
                      "context": f2["context"]},
                "context_overlap": round(ov, 2),
                "common_run": run,
                "topic_overlap": round(topic_ov, 2),
                })
    # 同一条记忆内部的自我矛盾也报（常见于「目标 200ms，实测 340ms」这种，不是冲突，需人眼看）
    return conflicts


def summarize(conflicts: list[dict]) -> str:
    if not conflicts:
        return "未发现数字级冲突"
    lines = []
    for c in conflicts[:10]:
        lines.append(f"- `{c['a']['key']}` 说 {c['a']['raw']} ｜ `{c['b']['key']}` 说 {c['b']['raw']}"
                     f"（语境重合 {c['context_overlap']}）")
    return "\n".join(lines)
