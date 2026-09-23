#!/usr/bin/env python3
"""
会话归档 — Hermes 对话 → Mnemosyne 记忆宫殿
用法:
  python3 archive_session.py                    # 归档最近一次会话
  python3 archive_session.py --session-id ID    # 归档指定会话
  python3 archive_session.py --last N           # 归档最近N场会话
  python3 archive_session.py --dry-run          # 预览不推送
  python3 archive_session.py --auto             # 自动归档首个未归档会话(供 hook/cron)
  python3 archive_session.py --list             # 列出最近会话

v7.8.4 (2026-09-24) 归档质量三改 —— 触发: 收尾汇报里的交付物路径/哈希/实测数字在语义层查不到
  1. 分级截断: 收尾汇报 + 用户消息 **全文保留**, 只压缩过程消息。
     旧版对每条消息一刀切 `content[:2000]`, 而汇报常 >2000 字 —— 被切的正是精华。
  2. 证据签名: 带 tool_calls 的消息附 `⟪工具: terminal×3, read_file×2⟫`, 让语义层看得见"这轮干了什么"。
  3. 短会话不弃: message_count < 5 改为入库并打 `[短]` 前缀 (旧版直接跳过 → 小任务无痕)。
"""
import collections
import re
import sqlite3
import json
import sys
import os
import argparse
import urllib.request
from datetime import datetime, timezone

HERMES_DB = os.path.expanduser("~/.hermes/state.db")
MNEMOSYNE_API = "http://127.0.0.1:18010/api/v1/sessions/archive"
TRACKING_FILE = os.path.expanduser("~/.hermes/archived_sessions.json")

# ---- v7.8.4 分级截断预算 ----
LIMIT_FINAL_REPORT = 12000   # 会话最后一条 AI 消息(收尾汇报) — 全文保留
LIMIT_USER = 8000            # 用户消息 — 全文保留(上限仅防极端粘贴)
LIMIT_PROCESS = 1200         # 过程消息(工具往返/中间分析) — 压缩
MAX_TOTAL = 120000           # 单会话总预算(旧版同会话实测入档 12.5 万字符且生产无恙, 不订更低)
                             # 超限时只从"过程消息"里让位; 受保护内容(汇报/用户消息)永不裁剪
TOOL_SIG_MAX = 5             # 证据签名最多列几种工具
SHORT_SESSION = 5            # 低于此数叫"短会话": 入库但打 [短] 前缀

# 项目关键词 (从配置文件加载, 不存在返回空)
KEYWORDS_FILE = os.path.join(os.path.dirname(__file__), "project_keywords.json")
try:
    with open(KEYWORDS_FILE) as f:
        PROJECT_KEYWORDS = json.load(f)
    # 去掉注释键
    PROJECT_KEYWORDS = {k: v for k, v in PROJECT_KEYWORDS.items() if not k.startswith("_")}
except (FileNotFoundError, json.JSONDecodeError):
    PROJECT_KEYWORDS = {}


def _compose_title(title, proj: str | None, is_short: bool) -> str:
    """把 [项目] / [短] 合成**单个**前缀标签, 幂等。

    旧写法两次前插会得到 `[短] [relife] 标题` —— 方括号套娃, 且重复调用会叠加。
    """
    title = str(title or "")
    m = re.match(r"^\[([^\]]*)\]\s*(.*)$", title)
    tag, rest = (m.group(1), m.group(2)) if m else ("", title)
    parts = [p.strip() for p in tag.split("·") if p.strip()]
    if is_short and "短" not in parts:
        parts.insert(0, "短")
    if proj and proj not in parts:
        parts.append(proj)
    return "[{}] {}".format("·".join(parts), rest) if parts else rest


def _detect_project(text: str) -> str:
    """根据文本检测所属项目 (命中关键词 >=2 才算, 避免单字误撞)"""
    t = text.lower()
    best, best_score = None, 0
    for proj, words in PROJECT_KEYWORDS.items():
        s = sum(1 for w in words if w.lower() in t)
        if s > best_score:
            best, best_score = proj, s
    return best if best_score >= 2 else None


# ---- v7.8.4: 证据签名 ----

def _tool_names(tool_calls) -> list:
    """从 tool_calls(OpenAI 形态) 抽工具名列表, 容错到底。"""
    if not tool_calls:
        return []
    try:
        items = json.loads(tool_calls)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(items, list):
        items = [items]
    names = []
    for it in items:
        if not isinstance(it, dict):
            continue
        nm = None
        fn = it.get("function")
        if isinstance(fn, dict):
            nm = fn.get("name")
        if not nm:
            nm = it.get("name")
        if isinstance(nm, str) and nm.strip():
            names.append(nm.strip())
    return names


def tool_signature(tool_calls) -> str:
    """`⟪工具: terminal×3, read_file×2⟫` — 无工具则空串。"""
    names = _tool_names(tool_calls)
    if not names:
        return ""
    counts = collections.Counter(names)
    top = ", ".join(f"{n}×{c}" if c > 1 else n for n, c in counts.most_common(TOOL_SIG_MAX))
    extra = f", …共{len(counts)}种" if len(counts) > TOOL_SIG_MAX else ""
    return f" ⟪工具: {top}{extra}⟫"


def _last_report_id(messages) -> int | None:
    """会话最后一条有正文的 AI 消息 = 收尾汇报 (要全文保留的那条)。"""
    for msg in reversed(messages):
        if msg["role"] != "user" and (msg["content"] or "").strip():
            return msg["id"]
    return None


def format_session(messages) -> tuple:
    """分级截断组装会话正文。返回 (content, stats)。

    预算规则: 收尾汇报(最后一条 AI 消息)与用户消息永不裁剪;
    总长超 MAX_TOTAL 时, 从"最早的过程消息"开始压缩让位。
    """
    final_id = _last_report_id(messages)
    stats = {"messages": 0, "final_report_chars": 0, "truncated_process": 0, "budget_trimmed": 0}

    entries = []  # (label, content, sig, protected)
    for msg in messages:
        role_label = "用户" if msg["role"] == "user" else "AI"
        content = (msg["content"] or "").strip()
        sig = tool_signature(msg["tool_calls"] if "tool_calls" in msg.keys() else None)
        if not content and not sig:
            continue
        is_final = (msg["id"] == final_id)
        protected = is_final or msg["role"] == "user"
        limit = LIMIT_FINAL_REPORT if is_final else (LIMIT_USER if msg["role"] == "user" else LIMIT_PROCESS)
        if len(content) > limit:
            dropped = len(content) - limit
            content = content[:limit] + f"...(截断 {dropped} 字)"
            if not protected:
                stats["truncated_process"] += 1
        if is_final:
            stats["final_report_chars"] = len(content)
        entries.append([role_label, content, sig, protected])

    total = sum(len(f"{e[0]}: {e[1]}{e[2]}") + 2 for e in entries)
    trimmed = set()
    while total > MAX_TOTAL:
        cand = [i for i, e in enumerate(entries) if not e[3] and len(e[1]) > 220]
        if not cand:
            break                        # 只剩余"受保护"内容 → 允许超预算(汇报优先)
        i = cand[0]                      # 最早的过程消息先让位
        before = len(entries[i][1])
        new_len = max(200, before // 2)
        entries[i][1] = entries[i][1][:new_len] + "...(预算压缩)"
        total -= before - len(entries[i][1])   # 净减量(含后缀, 旧版少算后缀 → 循环多跑)
        trimmed.add(i)
    stats["budget_trimmed"] = len(trimmed)     # 语义: 被让位的"消息条数"

    lines = [f"{e[0]}: {e[1]}{e[2]}" for e in entries]
    stats["messages"] = len(lines)
    return "\n\n".join(lines), stats


def get_session(db_path: str, session_id: str = None) -> dict:
    """从 Hermes DB 取会话 (v7.8.4: 同时取 tool_calls, 短会话不再排除)"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if session_id:
        session = conn.execute(
            "SELECT * FROM sessions WHERE id=? ORDER BY started_at DESC LIMIT 1",
            (session_id,)
        ).fetchone()
    else:
        session = conn.execute(
            "SELECT * FROM sessions WHERE message_count > 3 ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

    if not session:
        conn.close()
        return None

    try:
        messages = conn.execute(
            "SELECT id, role, content, tool_calls FROM messages WHERE session_id=? AND active=1 "
            "ORDER BY id",
            (session["id"],)
        ).fetchall()
    except sqlite3.OperationalError:
        # 老库没有 tool_calls 列 → 退化为只取正文
        messages = conn.execute(
            "SELECT id, role, content, '' AS tool_calls FROM messages "
            "WHERE session_id=? AND active=1 ORDER BY id",
            (session["id"],)
        ).fetchall()

    conn.close()

    content, stats = format_session(messages)

    # v7.8.4: 回库项目前缀接线(部署副本 2026-09-04 已验证) + 短会话标记, 合成单标签
    proj = _detect_project(content)
    title = _compose_title(session["title"], proj,
                           session["message_count"] < SHORT_SESSION)

    return {
        "session_id": session["id"],
        "title": title,
        "content": content,
        "message_count": session["message_count"],
        "started_at": session["started_at"],
        "stats": stats,
    }


def archive_to_mnemosyne(session: dict, dry_run: bool = False) -> dict:
    """推送会话到记忆宫殿 (title 已含 [项目]/[短] 前缀)"""
    payload = json.dumps({
        "user_id": "default",
        "session_id": session["session_id"],
        "title": session["title"],
        "content": session["content"],
    }).encode()

    if dry_run:
        return {
            "dry_run": True,
            "would_send": len(session["content"]),
            "title": session["title"],
            "stats": session.get("stats"),
            "preview": session["content"][:200],
        }

    try:
        req = urllib.request.Request(
            MNEMOSYNE_API,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"archived": False, "error": str(e)}


def list_sessions(db_path: str, limit: int = 10) -> list:
    """列出最近会话"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title, message_count, started_at FROM sessions "
        "WHERE message_count > 0 ORDER BY started_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_archived() -> set:
    """加载已归档的会话ID集合"""
    try:
        with open(TRACKING_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_archived(archived: set):
    """保存已归档会话ID"""
    with open(TRACKING_FILE, 'w') as f:
        json.dump(list(archived), f)


def auto_mode(include_short: bool = True):
    """自动模式: 归档首个未归档的已完成会话

    v7.8.4: 短会话不再跳过, 改为入库并打 [短] 前缀 (include_short=False 可还原旧行为)。
    """
    archived = load_archived()
    sessions = list_sessions(HERMES_DB, limit=20)

    for s in sessions:
        sid = s["id"]
        if sid in archived:
            continue
        if not include_short and s["message_count"] < SHORT_SESSION:
            continue

        session = get_session(HERMES_DB, sid)
        if not session:
            continue

        result = archive_to_mnemosyne(session)
        if result.get("archived"):
            archived.add(sid)
            save_archived(archived)
            print(json.dumps({"auto_archived": True, "session_id": sid[:20],
                            "memory_id": result.get("memory_id"), "title": s["title"],
                            "messages": s["message_count"],
                            "stats": session.get("stats")}, ensure_ascii=False))
            return result

        # 即使重复也算归档过了
        if result.get("reason") == "duplicate":
            archived.add(sid)
            save_archived(archived)

    return {"auto_archived": False, "reason": "nothing_new"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes 会话归档 → Mnemosyne")
    parser.add_argument("--session-id", help="归档指定会话")
    parser.add_argument("--last", type=int, default=1, help="归档最近N场")
    parser.add_argument("--dry-run", action="store_true", help="预览")
    parser.add_argument("--list", action="store_true", help="列出可归档会话")
    parser.add_argument("--auto", action="store_true", help="自动归档首个未归档会话(供cron/hook)")
    parser.add_argument("--skip-short", action="store_true",
                        help="v7.8.4 兼容开关: 还原旧行为(跳过 <5 条的短会话)")
    args = parser.parse_args()

    if args.auto:
        result = auto_mode(include_short=not args.skip_short)
        sys.exit(0 if result.get("auto_archived") else 0)

    if args.list:
        sessions = list_sessions(HERMES_DB)
        for s in sessions:
            print(f"  {s['id'][:12]}...  [{s['message_count']}条] {s['title'] or '(无标题)'}  {str(s['started_at'])[:19]}")
        sys.exit(0)

    for i in range(args.last):
        sid = args.session_id if args.session_id else None
        session = get_session(HERMES_DB, sid)

        if not session:
            print("No sessions found.")
            sys.exit(1)

        result = archive_to_mnemosyne(session, args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if args.session_id:
            break  # 指定ID只跑一次
