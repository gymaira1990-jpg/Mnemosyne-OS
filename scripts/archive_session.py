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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hermes 会话归档 → Mnemosyne")
    parser.add_argument("--session-id", help="归档指定会话")
    parser.add_argument("--last", type=int, default=1, help="归档最近N场")
    parser.add_argument("--dry-run", action="store_true", help="预览")
    parser.add_argument("--list", action="store_true", help="列出可归档会话")
    args = parser.parse_args()
    
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
