#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Memory OS 8.0.1 · 检索路由（先宫殿，后原文）

用户钦定顺序（2026-10-26）：先查 Memory OS，实在找不到再进会话记忆。

  ① Mnemosyne 语义检索 —— 命中「结果卡」优先（带 msg_range 可直接跳原文）
  ② 命中不足 / 相关度低 → 自动下探 state.db FTS（毫秒级，全文原文）
  ③ 两路都空 → 明说「未命中」，只给最接近的 3 条，不编造

用法:
    python3 route-search.py "上次那个悬停路径怎么发现的"
    python3 route-search.py "备份告警" --json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import urllib.request

MN = os.environ.get("MNEMOSYNE_URL", "http://127.0.0.1:18010")
DB = os.path.expanduser(os.environ.get("MEMOS_STATE_DB", "~/.hermes/state.db"))
CARD_PREFIX = os.environ.get("MEMOS_CARD_PREFIX", "[结果卡]").strip()
MIN_SEMANTIC_HITS = 1     # 至少 1 条结果卡命中才算够
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _post(url: str, payload: dict, timeout: int = 40):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def search_palace(query: str, limit: int = 8) -> list[dict]:
    try:
        d = _post(f"{MN}/api/v1/memories/search", {"query": query, "user_id": "default", "limit": limit})
    except Exception:
        return []
    items = d if isinstance(d, list) else (d.get("memories") or d.get("results") or [])
    return items or []


def _terms(query: str) -> list[str]:
    """粗切词：中文按 2-4 字滑窗取关键词，英文/数字按词。"""
    q = re.sub(r"[，。、？！：；\"'（）()\[\]]+", " ", query).strip()
    words = [w for w in re.split(r"\s+", q) if w]
    terms = []
    for w in words:
        if _CJK.search(w):
            if len(w) <= 4:
                terms.append(w)
            else:
                terms += [w[i:i + 3] for i in range(0, len(w) - 2, 2)]
        else:
            terms.append(w)
    return [t for t in dict.fromkeys(terms) if len(t) >= 2][:6]


def search_state(query: str, limit: int = 5) -> list[dict]:
    if not os.path.exists(DB):
        return []
    terms = _terms(query)
    if not terms:
        return []
    fts = " OR ".join(f'"{t}"' for t in terms)
    out = []
    try:
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT m.id, m.session_id, m.role, m.content FROM messages_fts f "
            "JOIN messages m ON m.id = f.rowid WHERE messages_fts MATCH ? "
            "ORDER BY rank LIMIT ?", (fts, limit)).fetchall()
        for r in rows:
            out.append({
                "msg_id": r["id"], "session_id": r["session_id"], "role": r["role"],
                "snippet": (r["content"] or "").replace("\n", " ")[:220],
            })
        conn.close()
    except Exception as e:  # noqa: BLE001
        out.append({"error": f"{type(e).__name__}: {e}"})
    return out


def resolve(query: str) -> dict:
    result = {"query": query, "path": None, "cards": [], "palace": [], "state": []}

    palace = search_palace(query)
    cards = [m for m in palace if (m.get("content") or "").startswith(CARD_PREFIX)]
    result["palace"] = palace[:5]
    result["cards"] = cards[:3]

    if cards:
        result["path"] = "palace:outcome"
        md = cards[0].get("metadata")
        try:
            md = json.loads(md) if isinstance(md, str) else (md or {})
        except Exception:  # noqa: BLE001
            md = {}
        result["jump"] = {"msg_from": md.get("msg_from"), "msg_to": md.get("msg_to"),
                          "session_id": md.get("session_id")}
        return result

    # 没有结果卡 ⇒ 宫殿只算"参考"，必须同时下探原文（8.0.1 修正：原逻辑 ≥2 条就停，实测会导致永不下探）
    state = search_state(query)
    result["state"] = state
    if state and "error" not in (state[0] or {}):
        result["path"] = "hybrid" if palace else "state:fts"
        return result

    if palace:
        result["path"] = "palace:weak"
        return result

    result["path"] = "miss"
    return result


def render(r: dict) -> str:
    L = [f"问题：{r['query']}", f"路由：{r['path']}"]
    if r["cards"]:
        L.append("\n【结果卡（宫殿，可直接跳原文）】")
        for c in r["cards"]:
            L.append(f"  #{c.get('id')} heat={c.get('heat_score')}")
            for line in (c.get("content") or "").splitlines():
                L.append("    " + line)
        if r.get("jump", {}).get("msg_from"):
            j = r["jump"]
            L.append(f"  → 原文：state.db messages {j['msg_from']}..{j['msg_to']}")
    elif r["palace"]:
        L.append("\n【宫殿（未命中结果卡，仅供参考）】")
        for m in r["palace"][:3]:
            L.append(f"  #{m.get('id')} {m.get('category','?'):9s} | {(m.get('content') or '')[:80]}".replace("\n", " "))
    if r["state"] and "error" not in (r["state"][0] or {}):
        L.append("\n【原文（state.db FTS）】")
        for s in r["state"][:3]:
            L.append(f"  msg{s['msg_id']} {s['role']:9s} | {s['snippet'][:120]}")
    if r["path"] == "miss":
        L.append("\n未命中：两路都没有结果，不做推测。")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Memory OS 8.0.1 检索路由")
    ap.add_argument("query")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = resolve(a.query)
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else render(r))
