"""持久写队列 — crash-safe 记忆写入缓冲

参考：RetainDB _WriteQueue 模式
用途：Hermes sync_turn → SQLite 队列 → 后台逐条发送 → Mnemosyne API
特性：WSL 断电不丢数据，重启自动回放，熔断器防重复轰炸

队列表:
  pending(id PK, user_content, assistant_content, category,
          status, attempts, last_error, created_at)
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".hermes" / "mnemosyne_queue.db"
_POLL_INTERVAL = 2.0  # 消费间隔秒数
_MAX_RETRIES = 3
_CIRCUIT_BREAK_THRESHOLD = 5
_CIRCUIT_RESET_SECONDS = 120


class WriteQueue:
    """SQLite 持久化写入队列（线程安全）"""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_db()

        # 熔断器状态
        self._fail_count = 0
        self._circuit_open_until = 0.0
        self._circuit_lock = threading.Lock()

    # ── 连接管理 ──

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self):
        with self._lock:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_content TEXT,
                    assistant_content TEXT,
                    category TEXT DEFAULT 'chat',
                    source TEXT DEFAULT 'hermes-sync',
                    status TEXT DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pending_status
                ON pending(status)
            """)
            conn.commit()

    # ── 写入队列 ──

    def enqueue(self, user_content: str, assistant_content: str,
                category: str = "chat", source: str = "hermes-sync") -> int:
        """写入队列（立即持久化，crash-safe）"""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT INTO pending (user_content, assistant_content, category, source) VALUES (?,?,?,?)",
                (user_content[:500], assistant_content[:800], category, source)
            )
            conn.commit()
            return cur.lastrowid

    # ── 消费队列（由后台线程调用）──

    def dequeue(self, batch_size: int = 5) -> list[dict]:
        """取出待发送的条目"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, user_content, assistant_content, category, source, attempts "
                "FROM pending WHERE status='pending' AND attempts < ? "
                "ORDER BY id ASC LIMIT ?",
                (_MAX_RETRIES, batch_size)
            ).fetchall()
            return [
                {"id": r[0], "user_content": r[1], "assistant_content": r[2],
                 "category": r[3], "source": r[4], "attempts": r[5]}
                for r in rows
            ]

    def mark_done(self, item_id: int):
        """发送成功，删除队列条目"""
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM pending WHERE id=?", (item_id,))
            conn.commit()

    def mark_failed(self, item_id: int, error: str):
        """发送失败，标记重试"""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE pending SET status='pending', attempts=attempts+1, "
                "last_error=? WHERE id=?",
                (error[:200], item_id)
            )
            conn.commit()

    # ── 统计 ──

    def pending_count(self) -> int:
        with self._lock:
            conn = self._get_conn()
            r = conn.execute("SELECT count(*) FROM pending WHERE status='pending'").fetchone()
            return r[0] if r else 0

    def replay_pending(self) -> list[dict]:
        """重启时回放所有待发送条目"""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, user_content, assistant_content FROM pending "
                "WHERE status='pending' ORDER BY id ASC"
            ).fetchall()
            return [{"id": r[0], "user_content": r[1], "assistant_content": r[2]} for r in rows]

    # ── 熔断器 ──

    def is_circuit_open(self) -> bool:
        with self._circuit_lock:
            if self._circuit_open_until == 0:
                return False
            if time.time() > self._circuit_open_until:
                self._circuit_open_until = 0
                self._fail_count = 0
                logger.info("熔断器 HALF_OPEN → 恢复试探")
                return False
            return True

    def record_success(self):
        with self._circuit_lock:
            self._fail_count = 0
            self._circuit_open_until = 0

    def record_failure(self):
        with self._circuit_lock:
            self._fail_count += 1
            if self._fail_count >= _CIRCUIT_BREAK_THRESHOLD:
                self._circuit_open_until = time.time() + _CIRCUIT_RESET_SECONDS
                logger.warning("熔断器 OPEN — 暂停 %ds (fail_count=%d)",
                               _CIRCUIT_RESET_SECONDS, self._fail_count)


# ── 全局单例 ──
_queue: Optional[WriteQueue] = None


def get_queue() -> WriteQueue:
    global _queue
    if _queue is None:
        _queue = WriteQueue()
    return _queue
