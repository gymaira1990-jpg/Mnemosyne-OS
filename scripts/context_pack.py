#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context_pack.py —— 三段式采样：前（历史）→ 中（当前会话）→ 后（输出要求）

主人 2026-11-07 定的方向：
    「采样的时候一定要做前中后三个阶段的反应。前就是以前的资料来整理，
      中就是当前的会话，后就是输出的结果。输出的结果要根据前中来处理。
      关键点是 AI 的自主性——思考、查看和回忆。」

这个脚本就是那句话的工具化：回答之前先跑一次，把三段摆清楚。
    · 前：从记忆宫殿召回与本题相关的旧资料（带档号，可追溯）
    · 中：当前会话最近若干轮（判断「上下文够不够」）
    · 后：输出约束（结论先行 / 引档号 / 不确定就标注 / 缺什么就说缺什么）

为什么需要它：新会话上下文薄，靠模型自己「感觉」够不够是不准的；
    这里给出**可判定的信号**（前段最高分 + 命中档号数 + 当前会话轮数），
    低于阈值就明确写「上下文不足，建议回捞」，而不是硬答。

用法：
    python3 scripts/context_pack.py --query "召回延迟现在多少"
    python3 scripts/context_pack.py --query "..." --md          # 输出 Markdown 块，可直接贴进思考
    python3 scripts/context_pack.py --query "..." --session 最近  # 指定会话（默认取最新）
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime

BASE = os.getenv("MEMOS_BASE", "http://127.0.0.1:8010")
STATE_DB = os.path.expanduser(os.getenv("HERMES_STATE_DB", "~/.hermes/state.db"))

# 判定「上下文够不够」的阈值（都可用参数覆盖，别写死在脑子里）
MIN_PRIOR_SCORE = 25.0     # 前段最高分低于它 ⇒ 历史资料不足
MIN_SESSION_TURNS = 4      # 当前会话少于这么多轮 ⇒ 当前上下文薄


def _post(path: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(BASE.rstrip("/") + path,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def prior(query: str, user: str, k: int) -> dict:
    """前段：历史资料。走四通道召回（含语义，门槛 0.40）。"""
    d = _post("/api/v1/memory-os/recall",
              {"user_id": user, "query": query, "limit": k,
               "semantic": True, "sim_floor": 0.40, "confirm_margin": 10})
    cands = d.get("candidates") or []
    return {
        "candidates": [{"no": c.get("no") or "", "head": (c.get("head") or "")[:120],
                        "score": round(float(c.get("score") or 0), 1),
                        "channels": c.get("channels")} for c in cands[:k]],
        "top_score": round(float(cands[0].get("score") or 0), 1) if cands else 0.0,
        "with_no": sum(1 for c in cands[:k] if (c.get("no") or "").strip()),
        "confirm": d.get("confirm"),
        "channel_counts": d.get("channel_counts"),
    }


def current_session(session: str, limit: int) -> dict:
    """中段：当前会话最近若干轮。只读 state.db，不改任何东西。"""
    if not os.path.exists(STATE_DB):
        return {"session": session, "turns": 0, "recent": [], "note": "state.db 不存在"}
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        if session in ("", "最近", "latest"):
            cur.execute("SELECT id FROM sessions ORDER BY rowid DESC LIMIT 1")
            row = cur.fetchone()
            if not row:
                return {"session": "", "turns": 0, "recent": [], "note": "没有会话记录"}
            session = row[0]
        cur.execute("SELECT count(*) FROM messages WHERE session_id=?", (session,))
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT role, substr(replace(content,char(10),' '),1,100) FROM messages "
            "WHERE session_id=? AND role IN ('user','assistant') ORDER BY id DESC LIMIT ?",
            (session, limit))
        recent = [{"role": r, "text": t} for r, t in cur.fetchall()][::-1]
    finally:
        con.close()
    return {"session": session, "turns": total, "recent": recent}


def _bigrams(text: str) -> set[str]:
    t = "".join(ch for ch in (text or "") if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)} if len(t) > 1 else set()


def topic_drift(query: str, recent_user_texts: list[str]) -> float:
    """话题漂移度 0–1：当前问句与最近几条「用户消息」的字面重合越低，漂移越大。

    为什么不用 embedding：这里要的是**便宜且可解释**的信号（0 依赖、0 调用），
    判「是不是换话题了」不需要语义精度；语义留给召回那一层去做。
    """
    q = _bigrams(query)
    # 只拿「有实质内容」的用户消息来比：「继续推进」「好」这类短指令不承载话题，
    # 拿它们算重合度会让漂移恒等于 1.0（等于没信号）。
    substantive = [t for t in recent_user_texts if len(t or "") >= 8 and len(_bigrams(t)) >= 4]
    if not q or not substantive:
        return None            # 无可比对象 ⇒ 未知，而不是「漂移」
    # 用「问句被覆盖的比例」而不是 Jaccard：Jaccard 会被长消息稀释，
    # 同一个话题也会算出 0.7 的「漂移」，那样阈值就没法设了。
    best = 0.0
    for t in substantive[-5:]:
        tb = _bigrams(t)
        if not tb:
            continue
        best = max(best, len(q & tb) / max(1, len(q)))
    return round(1.0 - best, 3)


def widen_history(query: str, exclude_session: str, limit: int = 5) -> list[dict]:
    """往前捞：在当前会话之外的历史消息里按关键词找（FTS5，只读）。

    这是「新会话上下文薄时主动回捞」的那只手 —— 记忆宫殿管卡片，这里管**对话原文**。
    """
    if not os.path.exists(STATE_DB):
        return []
    # FTS5 的 MATCH 是「查询语法」，用户问题里带引号/括号/星号会直接语法错误。
    # 只留字母数字（含中文），别的当分隔符 —— 宁可能召回少，不许因为一个括号报错。
    words = "".join(ch if ch.isalnum() else " " for ch in query).split()
    toks = sorted({w for w in words if len(w) > 1})
    if not toks:
        return []
    match = " OR ".join(toks[:6])
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        try:
            cur.execute(
                """SELECT m.session_id, m.role, substr(replace(m.content,char(10),' '),1,120),
                          datetime(m.timestamp,'unixepoch','localtime')
                     FROM messages_fts f JOIN messages m ON m.id=f.rowid
                    WHERE messages_fts MATCH ?
                      AND m.role IN ('user','assistant')
                      AND length(trim(coalesce(m.content,''))) > 20
                      AND m.session_id <> ?
                    ORDER BY m.id DESC LIMIT ?""",
                (match, exclude_session or "", limit))
            return [{"session": r[0][:20], "role": r[1], "text": r[2], "at": r[3]}
                    for r in cur.fetchall()]
        except sqlite3.OperationalError as e:
            if os.getenv("CTX_PACK_DEBUG"):
                print(f"[widen_history] FTS 查询失败，按无结果处理: {e}", file=sys.stderr)
            return []          # FTS 不可用就当没有，不阻塞主流程
    finally:
        con.close()


def verdict(p: dict, s: dict, min_score: float, min_turns: int,
            drift: float | None = None, drift_limit: float = 0.85) -> dict:
    """够不够，用可判定的信号说，而不是凭感觉。"""
    gaps = []
    if p["top_score"] < min_score:
        gaps.append(f"历史资料最高分 {p['top_score']} < {min_score}")
    if p["with_no"] == 0:
        gaps.append("前段没有任何带档号的卡（无法追溯原文）")
    if s["turns"] < min_turns:
        gaps.append(f"当前会话仅 {s['turns']} 轮 < {min_turns}")
    if drift is not None and drift > drift_limit:
        gaps.append(f"话题漂移 {drift:.2f} > {drift_limit}（和最近几轮几乎无重合）")
    return {"sufficient": not gaps, "gaps": gaps, "drift": drift}


def render(pack: dict, as_md: bool) -> str:
    p, s, v = pack["prior"], pack["session"], pack["verdict"]
    if not as_md:
        return json.dumps(pack, ensure_ascii=False, indent=2)
    L = [f"## 三段式采样 · {pack['query']}", ""]
    L.append(f"**判定：{'上下文够' if v['sufficient'] else '上下文不足'}**"
             + ("" if v["sufficient"] else "（" + "；".join(v["gaps"]) + "）"))
    if v.get("drift") is not None:
        L.append(f"话题漂移度：{v['drift']:.2f}（0=接得上，1=完全换话题）")
    L += ["", f"### 前 · 历史资料（{len(p['candidates'])} 条，最高分 {p['top_score']}）"]
    for c in p["candidates"][:5]:
        L.append(f"- `{c['no'] or '无档号'}` ({c['score']}) {c['head'][:80]}")
    if p.get("confirm"):
        L.append(f"- ❓ 需你确认：{p['confirm']['question']}")
    L += ["", f"### 中 · 当前会话（{s['turns']} 轮，最近 {len(s['recent'])} 条）"]
    for m in s["recent"][-6:]:
        L.append(f"- {m['role']}: {m['text'][:70]}")
    hist = pack.get("history") or []
    if hist:
        L += ["", f"### 补 · 回捞到的历史会话（{len(hist)} 条，当前会话之外）"]
        for h in hist:
            L.append(f"- `{h['session']}` {h['at']} {h['role']}: {h['text'][:80]}")
    L += ["", "### 后 · 输出要求",
          "- 结论先行；引用记忆必须带档号；不确定处标注 [UNCERTAIN] 并说明卡在哪里",
          "- 上下文不足时先说缺什么，再问一句，别硬编"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="三段式采样（前/中/后）")
    ap.add_argument("--query", required=True)
    ap.add_argument("--user", default="default")
    ap.add_argument("--session", default="最近")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--recent", type=int, default=12)
    ap.add_argument("--min-score", type=float, default=MIN_PRIOR_SCORE)
    ap.add_argument("--min-turns", type=int, default=MIN_SESSION_TURNS)
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--widen", action="store_true", default=True,
                    help="判「不足」时回捞历史会话原文（默认开）")
    ap.add_argument("--no-widen", dest="widen", action="store_false")
    ap.add_argument("--widen-limit", type=int, default=5)
    ap.add_argument("--drift-limit", type=float, default=0.85,
                    help="话题漂移阈值：0.85 表示与最近几轮几乎无重合")
    a = ap.parse_args()

    sess = current_session(a.session, a.recent)
    user_texts = [m["text"] for m in sess["recent"] if m["role"] == "user"]
    drift = topic_drift(a.query, user_texts)

    pack = {
        "query": a.query,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": a.user,
        "prior": prior(a.query, a.user, a.k),
        "session": sess,
        "drift": drift,
    }
    pack["verdict"] = verdict(pack["prior"], sess, a.min_score, a.min_turns,
                              drift=drift, drift_limit=a.drift_limit)
    # 判「不足」时主动回捞历史会话原文（主人：缺上下文就往前捞，别硬答）
    if a.widen and not pack["verdict"]["sufficient"]:
        pack["history"] = widen_history(a.query, sess["session"], limit=a.widen_limit)
    print(render(pack, a.md))
    return 0 if pack["verdict"]["sufficient"] else 1


if __name__ == "__main__":
    sys.exit(main())
