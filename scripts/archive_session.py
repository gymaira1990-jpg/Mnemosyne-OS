#!/usr/bin/env python3
"""
会话归档 — Hermes 对话 → Mnemosyne 记忆宫殿
用法:
  python3 archive_session.py                    # 归档最近一次会话
  python3 archive_session.py --session-id ID    # 归档指定会话
  python3 archive_session.py --last N           # 归档最近N场会话
  python3 archive_session.py --dry-run          # 预览不推送
"""
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

# 项目关键词 (用于自动标记)
PROJECT_KEYWORDS = {
    "记忆宫殿": ["记忆宫殿", "mnemosyne", "TMT", "蒸馏", "AGE", "chunking"],
    "猫窝": ["猫窝", "catnest", "经验分享", "代理架构"],
    "G-CAT个人研究网站": ["网站", "g-cat.cn", "topnav", "sitemap"],
    "系统运维自检": ["运维", "health check", "xray", "代理链路"],
    "本地模型管理": ["llama", "Qwen", "GPU", "本地模型", "GGUF"],
}

def _detect_project(text: str) -> str:
    """根据文本检测所属项目"""
    t = text.lower()
    best, best_score = None, 0
    for proj, words in PROJECT_KEYWORDS.items():
        s = sum(1 for w in words if w.lower() in t)
        if s > best_score:
            best, best_score = proj, s
    return best if best_score >= 2 else None


def get_session(db_path: str, session_id: str = None) -> dict:
    """从 Hermes DB 取会话"""
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
    
    messages = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? AND active=1 "
        "ORDER BY id",
        (session["id"],)
    ).fetchall()
    
    conn.close()
    
    # 格式化对话
    lines = []
    for msg in messages:
        role_label = "用户" if msg["role"] == "user" else "AI"
        content = (msg["content"] or "").strip()
        if content:
            # 截断过长消息
            if len(content) > 2000:
                content = content[:2000] + "...(截断)"
            lines.append(f"{role_label}: {content}")
    
    return {
        "session_id": session["id"],
        "title": session["title"] or "",
        "content": "\n\n".join(lines),
        "message_count": session["message_count"],
        "started_at": session["started_at"],
    }


def archive_to_mnemosyne(session: dict, dry_run: bool = False) -> dict:
    """推送会话到记忆宫殿"""
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
            "preview": session["content"][:200]
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


def auto_mode():
    """自动模式: 归档首个未归档的已完成会话"""
    archived = load_archived()
    sessions = list_sessions(HERMES_DB, limit=20)
    
    for s in sessions:
        sid = s["id"]
        if sid in archived:
            continue
        if s["message_count"] < 5:
            continue  # 太短的跳过
        
        session = get_session(HERMES_DB, sid)
        if not session:
            continue
        
        result = archive_to_mnemosyne(session)
        if result.get("archived"):
            archived.add(sid)
            save_archived(archived)
            print(json.dumps({"auto_archived": True, "session_id": sid[:20], 
                            "memory_id": result.get("memory_id"), "title": s["title"],
                            "messages": s["message_count"]}, ensure_ascii=False))
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
    parser.add_argument("--auto", action="store_true", help="自动归档首个未归档会话(供cron)")
    args = parser.parse_args()
    
    if args.auto:
        result = auto_mode()
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
