#!/usr/bin/env python3
"""
端云同步推送脚本
从 WSL 本地 SQLite 读取待推送记忆 → 发送到 GZ Mnemosyne API
用法: python3 sync_push.py [--batch 50]
"""
import sys
import os
import json
import time
import argparse
import httpx
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from local_cache import get_pending, mark_synced, mark_failed, log_sync, get_stats, init_db

GZ_API = "http://127.0.0.1:18010"  # SSH 隧道
HEALTH_ENDPOINT = f"{GZ_API}/api/v1/echo"
MEMORY_ENDPOINT = f"{GZ_API}/api/v1/memories"
TIMEOUT = 15
RETRY = 2


def check_gz_online() -> bool:
    """检查 GZ 是否可达"""
    try:
        r = httpx.get(HEALTH_ENDPOINT, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def push_one(memory: dict) -> bool:
    """推送单条记忆到 GZ"""
    payload = {
        "content": memory["content"],
        "category": memory.get("category", "fact"),
        "user_id": memory.get("user_id", "default"),
        "importance": memory.get("importance", 0.5),
    }
    
    for attempt in range(RETRY + 1):
        try:
            r = httpx.post(
                MEMORY_ENDPOINT,
                json=payload,
                timeout=TIMEOUT,
                params={"user_id": payload["user_id"]}
            )
            if r.status_code == 200:
                return True
            if attempt < RETRY:
                time.sleep(2)
        except Exception as e:
            if attempt < RETRY:
                time.sleep(2)
            else:
                mark_failed(memory["local_id"], str(e)[:200])
                return False
    return False


def push_batch(batch_size: int = 50, dry_run: bool = False) -> dict:
    """批量推送到 GZ"""
    init_db()
    
    if not check_gz_online():
        log_sync("skip", 0, "GZ offline")
        return {"status": "offline", "pushed": 0, "pending": get_stats()["pending"]}
    
    memories = get_pending(batch_size)
    if not memories:
        return {"status": "empty", "pushed": 0, "pending": 0}
    
    if dry_run:
        return {"status": "dry_run", "would_push": len(memories), "pending": get_stats()["pending"]}
    
    pushed = 0
    failed = 0
    for mem in memories:
        if push_one(mem):
            mark_synced(mem["local_id"])
            pushed += 1
        else:
            failed += 1
    
    log_sync("push", pushed, f"failed={failed}" if failed else "ok")
    
    remaining = get_stats()["pending"]
    return {"status": "done", "pushed": pushed, "failed": failed, "pending": remaining}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WSL→GZ 记忆同步推送")
    parser.add_argument("--batch", type=int, default=50, help="单批推送数量")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不推送")
    args = parser.parse_args()
    
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Sync push...", flush=True)
    result = push_batch(args.batch, args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
