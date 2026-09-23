#!/usr/bin/env python3
"""
汇报卡 — 把"交付级汇报"从会话里抽出来, 结构化留存 + 可选入记忆宫殿

为什么: 收尾汇报是每轮任务最浓缩的成果, 但会话级归档把整场会话揉成一条记忆,
汇报里的**交付物绝对路径 / URL / 哈希 / 实测数字**在语义层查不到。
本工具把这些要素单独抽成"汇报卡"(证据层留原文摘录, 语义层留可召回条目)。

用法:
  python3 report_card.py --session-id ID            # 抽取单个会话的卡(只落本地)
  python3 report_card.py --last 5 --push            # 抽最近5场的卡并推入记忆宫殿
  python3 report_card.py --last 1 --dry-run         # 只看会抽到什么, 不写入
  python3 report_card.py --list                     # 列出已抽到的卡

落点: ~/.hermes/reports/cards.jsonl (一行一张卡) + .index.json (去重索引)
入宫: POST /api/v1/memories {user_id, content, category='worklog'}
      category 取自 capabilities 受控词表(knowledge|pitfall|reference|project|ops|deploy|
      preference|session|worklog|temp) —— **不许自造**, 否则服务端静默归一化为 knowledge。
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime

HERMES_DB = os.path.expanduser("~/.hermes/state.db")
REPORTS_DIR = os.environ.get("REPORTS_DIR", os.path.expanduser("~/.hermes/reports"))
CARDS_FILE = os.path.join(REPORTS_DIR, "cards.jsonl")
INDEX_FILE = os.path.join(REPORTS_DIR, ".index.json")
MNEMOSYNE_MEMORIES_API = os.environ.get(
    "MNEMOSYNE_MEMORIES_API", "http://127.0.0.1:18010/api/v1/memories")

# capabilities 受控词表(权威: GET /api/v1/capabilities) —— 只许取这里面的值
CONTROLLED_CATEGORIES = frozenset([
    "knowledge", "pitfall", "reference", "project", "ops",
    "deploy", "preference", "session", "worklog", "temp",
])
CATEGORY = "worklog"          # 汇报卡归类: 工作产出记录
assert CATEGORY in CONTROLLED_CATEGORIES, "汇报卡 category 必须在受控词表内"

EXCERPT = 1500                # 原文摘录上限
MAX_SIG_LEN = 160             # 单个信号片段上限(防把整段 diff 输出当"路径")
FINAL_LOOKBACK = 3            # final 模式向前回看条数(会话常以一句简短收尾结束, 汇报在其前面)
THRESHOLD_SCAN = 3            # scan 模式: 信号种类下限(实测 >=2 太松: 3 场会话抽出 66 张卡 → 污染记忆)
STRICT_KINDS = ("收尾语", "哈希", "校验语", "路径")   # scan 模式必须至少命中其一
REPORT_TAIL = "汇报完毕请指示"

# 信号定义: 交付要素 —— 有这些东西的 AI 消息 = 交付级汇报, 不是普通闲聊
SIGNALS = [
    # 排除反斜杠/加号/反引号: 工具输出的 `\n` 转义与 diff 的 `+++` 会被误当路径(实测踩到)
    ("路径", re.compile(r"[A-Za-z]:\\[^\s\"'，。；）)\]`+]+")),
    ("路径", re.compile(r"/(?:home|mnt|opt|var|etc|usr|srv|root|tmp)/[^\s\"'，。；）)\]`+\\]+")),
    ("URL", re.compile(r"https?://[^\s\"'，。；）)\]]+")),
    ("哈希", re.compile(r"\b[0-9a-f]{16,64}\b")),
    ("实测数字", re.compile(r"\b\d+(?:\.\d+)?\s?(?:GiB|MiB|KiB|GB|MB|KB|TB|G|M|K)\b")),
    ("收尾语", re.compile(re.escape(REPORT_TAIL))),
    ("校验语", re.compile(r"哈希(?:一致|比对)|sha256|校验(?:通过|一致)|已核验|实测(?:通过|验证)")),
]


def extract_signals(text: str) -> dict:
    """按信号类型归组抽取(保序去重), 返回 {信号名: [命中片段...]}"""
    out = {}
    for name, rx in SIGNALS:
        hits = []
        for m in rx.finditer(text or ""):
            v = m.group(0).rstrip(".,;:、，。；）)]}>*\\+`")
            if not v or len(v) > MAX_SIG_LEN or v in hits:
                continue
            hits.append(v)
        if hits:
            out.setdefault(name, []).extend(hits)
    return out


def is_report_card(text: str, signals: dict | None = None, mode: str = "final") -> bool:
    """判定是否交付级汇报。

    mode="final"(默认): 收尾汇报 —— 每场会话只取**最后一条** AI 消息, 命中任一交付要素即算。
                        (用户的定义: "你每干完一个事不都会做一个汇报吗")
    mode="scan":  全会话扫描, 门槛更严: >=3 类信号 **且** 至少一类是交付证据(路径/哈希/校验/收尾语)。
    mode="all":   最宽(>=2 类), 只用于分析, 别用于入库。
    """
    signals = signals if signals is not None else extract_signals(text)
    kinds = [k for k, v in signals.items() if v]
    if mode == "final":
        return len(kinds) >= 1
    if mode == "all":
        return len(kinds) >= 2
    return len(kinds) >= THRESHOLD_SCAN and any(k in kinds for k in STRICT_KINDS)


def message_time(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return str(ts)


def build_card(msg: dict, signals: dict | None = None) -> dict:
    """把一条消息变成汇报卡(dict, 可直接 json.dumps)"""
    content = (msg.get("content") or "").strip()
    signals = signals if signals is not None else extract_signals(content)
    card = {
        "session_id": msg.get("session_id", ""),
        "msg_id": msg.get("id"),
        "time": message_time(msg.get("timestamp")),
        "signals": {k: len(v) for k, v in sorted(signals.items())},
        "paths": sorted(set(signals.get("路径", [])))[:20],
        "urls": sorted(set(signals.get("URL", [])))[:10],
        "hashes": sorted(set(signals.get("哈希", [])))[:10],
        "measures": sorted(set(signals.get("实测数字", [])))[:20],
        "excerpt": content[:EXCERPT],
        "chars": len(content),
    }
    return card


def card_digest(card: dict) -> str:
    """卡片指纹(去重用): 会话+消息+原文, 与时间无关"""
    raw = f"{card['session_id']}|{card['msg_id']}|{card['excerpt']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def card_text(card: dict) -> str:
    """推入记忆宫殿的正文(人类可读 + 可被语义检索)"""
    parts = [f"[汇报卡] {card['session_id']} · msg#{card['msg_id']} · {card['time']}",
             "信号: " + ", ".join(f"{k}×{v}" for k, v in card["signals"].items())]
    if card["paths"]:
        parts.append("交付物路径: " + "; ".join(card["paths"]))
    if card["urls"]:
        parts.append("URL: " + "; ".join(card["urls"]))
    if card["hashes"]:
        parts.append("哈希: " + "; ".join(card["hashes"]))
    if card["measures"]:
        parts.append("实测数字: " + "; ".join(card["measures"]))
    parts.append("原文摘录:\n" + card["excerpt"])
    return "\n".join(parts)


def load_index() -> dict:
    try:
        with open(INDEX_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_index(idx: dict):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(INDEX_FILE, "w") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)


def append_cards(cards: list):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(CARDS_FILE, "a") as f:
        for c in cards:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def push_card(card: dict) -> dict:
    """入宫: POST /api/v1/memories (json body + 受控 category)"""
    payload = json.dumps({
        "user_id": "default",
        "content": card_text(card),
        "category": CATEGORY,
    }).encode()
    try:
        req = urllib.request.Request(
            MNEMOSYNE_MEMORIES_API, data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"stored": False, "error": str(e)}


def fetch_report_messages(db_path: str, session_id: str | None = None, last: int = 1,
                          mode: str = "final", max_per_session: int = 3) -> list:
    """取候选 AI 消息(带正文), 按会话时间倒序

    mode="final": 每场会话只取最后一条有正文的 AI 消息(收尾汇报)。
    其他模式: 全扫, 命中门槛由 is_report_card 决定, 每会话最多 max_per_session 张。
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if session_id:
        sids = [session_id]
    else:
        rows = conn.execute(
            "SELECT id FROM sessions WHERE message_count > 0 ORDER BY started_at DESC LIMIT ?",
            (last,)).fetchall()
        sids = [r["id"] for r in rows]

    out = []
    for sid in sids:
        msgs = conn.execute(
            # 只认 assistant 本体的发言: role='tool' 是工具回显, 会把 diff/日志当交付物(实测踩到)
            "SELECT id, session_id, role, content, timestamp FROM messages "
            "WHERE session_id=? AND active=1 AND role='assistant' AND content!='' ORDER BY id",
            (sid,)).fetchall()
        if mode == "final":
            # 向前回看最多 FINAL_LOOKBACK 条, 取**最近一条**含交付要素的消息(汇报常不在最后一句)
            for m in reversed(msgs[-FINAL_LOOKBACK:]):
                txt = m["content"] or ""
                if not txt.strip():
                    continue
                sig = extract_signals(txt)
                if is_report_card(txt, sig, "final"):
                    out.append((dict(m), sig))
                    break
            continue
        picked = 0
        for m in msgs:
            txt = m["content"] or ""
            sig = extract_signals(txt)
            if is_report_card(txt, sig, mode):
                out.append((dict(m), sig))
                picked += 1
                if picked >= max_per_session:
                    break
    conn.close()
    return out


def run(db_path: str, session_id: str | None = None, last: int = 1,
        push: bool = False, dry_run: bool = False, mode: str = "final") -> dict:
    """主流程: 抽卡 → 落本地 → 可选入宫。返回统计。"""
    idx = load_index()
    found = fetch_report_messages(db_path, session_id, last, mode)
    fresh, dup = [], 0
    for msg, sig in found:
        card = build_card(msg, sig)
        d = card_digest(card)
        if d in idx:
            dup += 1
            continue
        card["digest"] = d
        fresh.append(card)

    result = {"session_id": session_id or f"last{last}", "mode": mode, "cards_found": len(found),
              "new_cards": len(fresh), "duplicates": dup,
              "pushed": 0, "would_push": len(fresh) if push else 0,
              "dry_run": dry_run, "local_file": CARDS_FILE,
              "cards": [{"msg_id": c["msg_id"], "time": c["time"],
                         "signals": c["signals"], "paths": c["paths"][:3]} for c in fresh]}

    if dry_run:
        result["preview"] = [card_text(c)[:400] for c in fresh[:2]]
        return result

    if fresh:
        append_cards(fresh)
        if push:
            for c in fresh:
                r = push_card(c)
                ok = bool(r.get("stored") or r.get("memory_id") or r.get("id"))
                idx[c["digest"]] = {"pushed_at": datetime.now().isoformat(timespec="seconds"),
                                    "memory_id": r.get("memory_id") or r.get("id"),
                                    "ok": ok, "session_id": c["session_id"], "msg_id": c["msg_id"]}
                result["pushed"] += 1 if ok else 0
        else:
            for c in fresh:   # 只落本地也要记索引, 避免重复抽
                idx[c["digest"]] = {"pushed_at": None, "session_id": c["session_id"],
                                    "msg_id": c["msg_id"], "ok": False}
        save_index(idx)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="汇报卡抽取 → 本地 JSONL + 记忆宫殿")
    ap.add_argument("--session-id", help="指定会话")
    ap.add_argument("--last", type=int, default=1, help="最近 N 场会话(默认1)")
    ap.add_argument("--push", action="store_true", help="推入记忆宫殿(category=worklog)")
    ap.add_argument("--dry-run", action="store_true", help="只预览, 不写任何东西")
    ap.add_argument("--mode", choices=["final", "scan", "all"], default="final",
                    help="final=每会话只取收尾汇报(默认); scan=全扫(严); all=最宽(仅分析)")
    ap.add_argument("--list", action="store_true", help="列出已抽到的卡")
    ap.add_argument("--db", default=HERMES_DB, help="state.db 路径(测试用)")
    args = ap.parse_args()

    if args.list:
        idx = load_index()
        if not os.path.exists(CARDS_FILE):
            print("(还没有卡)")
            sys.exit(0)
        with open(CARDS_FILE) as f:
            for line in f:
                c = json.loads(line)
                print(f"  msg#{c['msg_id']:<7} {c['time']}  {c['session_id'][:22]}  "
                      f"信号:{','.join(c['signals'])}  入宫:{'是' if idx.get(c.get('digest'), {}).get('pushed_at') else '否'}")
        sys.exit(0)

    out = run(args.db, args.session_id, args.last, args.push, args.dry_run, args.mode)
    print(json.dumps(out, ensure_ascii=False, indent=2))
