#!/usr/bin/env python3
"""
记忆网关 — 智能路由 GZ/本地
用法:
  python3 memory_gateway.py store --content "..." [--category fact] [--user default]
  python3 memory_gateway.py status
  python3 memory_gateway.py push [--batch 50]
"""
import sys
import os
import json
import argparse
import httpx
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from local_cache import store_memory, get_stats, init_db
from sync_push import push_batch, check_gz_online

GZ_API = "http://127.0.0.1:18010"
MEMORY_ENDPOINT = f"{GZ_API}/api/v1/memories"
TIMEOUT = 10


def store_to_gz(content: str, category: str = "fact", user_id: str = "default",
                importance: float = 0.5) -> dict:
    """尝试写入 GZ Mnemosyne"""
    payload = {
        "content": content,
        "category": category,
        "user_id": user_id,
        "importance": importance,
    }
    try:
        r = httpx.post(
            MEMORY_ENDPOINT,
            json=payload,
            timeout=TIMEOUT,
            params={"user_id": user_id}
        )
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "target": "gz", "id": data.get("id"), "content": content[:100]}
        return {"ok": False, "target": "gz", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "target": "gz", "error": str(e)[:100]}


def smart_store(content: str, category: str = "fact", user_id: str = "default",
                importance: float = 0.5) -> dict:
    """智能存储：先 GZ → 失败则本地 SQLite"""
    init_db()
    
    # 先试 GZ
    result = store_to_gz(content, category, user_id, importance)
    if result["ok"]:
        return result
    
    # GZ 不可用，存本地
    local_id = store_memory(content, category, user_id, importance)
    pending = get_stats()["pending"]
    return {
        "ok": True,
        "target": "local",
        "local_id": local_id,
        "pending_total": pending,
        "gz_error": result.get("error", "offline"),
        "content": content[:100]
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="记忆网关 — GZ/本地双写")
    sub = parser.add_subparsers(dest="cmd")
    
    store_p = sub.add_parser("store", help="存储记忆")
    store_p.add_argument("--content", required=True, help="记忆内容")
    store_p.add_argument("--category", default="fact")
    store_p.add_argument("--user", default="default")
    store_p.add_argument("--importance", type=float, default=0.5)
    
    sub.add_parser("status", help="查看本地缓存状态")
    
    push_p = sub.add_parser("push", help="推送本地缓存到GZ")
    push_p.add_argument("--batch", type=int, default=50)
    
    sub.add_parser("check", help="检查GZ连通性")
    
    args = parser.parse_args()
    
    if args.cmd == "store":
        result = smart_store(args.content, args.category, args.user, args.importance)
        print(json.dumps(result, ensure_ascii=False))
    
    elif args.cmd == "status":
        stats = get_stats()
        online = check_gz_online()
        print(json.dumps({**stats, "gz_online": online}, ensure_ascii=False))
    
    elif args.cmd == "push":
        result = push_batch(args.batch)
        print(json.dumps(result, ensure_ascii=False))
    
    elif args.cmd == "check":
        online = check_gz_online()
        print(json.dumps({"gz_online": online, "endpoint": GZ_API}))
    
    else:
        parser.print_help()
