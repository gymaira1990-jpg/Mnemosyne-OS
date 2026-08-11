#!/usr/bin/env python3
"""wiki_sync_check — 线上快照 vs 本地源 定期自检 (v7.4)

设计: WSL 本地源 = 真相; GZ 线上 wiki = 档案馆快照。
WSL 会关机, 所以定期自检放 GZ: 对比「线上快照」与「上次同步时的 hash 清单」。
- 若线上 hash 与清单一致 → 快照健康
- 若不一致 → 说明发生了本地更新同步或异常, 记录
- 同时检查: 线上页有 content 但 hash 为空 (老数据) / content 为空的孤儿页

用法 (GZ crontab):
    0 5 * * * cd /opt/mnemosyne && venv/bin/python wiki_sync_check.py >> /tmp/wiki_sync_check.log 2>&1
"""
import asyncio
import json
import os
import sys
import time

# 仓库根入 path (wiki/ 子目录运行时需要 tmt/core)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg  # noqa: E402

USER_ID = "default"
SNAPSHOT_FILE = "/opt/mnemosyne/wiki_hash_snapshot.json"


async def main():
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, source_path, content_hash, source_lost, "
                "length(content) AS content_len "
                "FROM wiki_pages WHERE user_id=$1 ORDER BY id",
                USER_ID
            )
    finally:
        await pool.close()

    total = len(rows)
    with_hash = [r for r in rows if r["content_hash"]]
    no_hash = [r for r in rows if not r["content_hash"]]
    empty = [r for r in rows if not r["content_len"]]
    lost = [r for r in rows if r["source_lost"]]

    print(f"[{time.strftime('%Y-%m-%d %H:%M')}] wiki 自检: 共 {total} 页")
    print(f"  ✅ 有指纹: {len(with_hash)} | ⚠️ 无指纹(老数据): {len(no_hash)} | ⚠️ 空内容: {len(empty)} | 🏳️ 源丢失标记: {len(lost)}")

    issues = []
    for r in no_hash[:10]:
        issues.append(f"无指纹: #{r['id']} {r['title']} ({r['content_len']}ch)")
    for r in empty[:10]:
        issues.append(f"空内容: #{r['id']} {r['title']}")
    for r in lost[:10]:
        issues.append(f"源丢失: #{r['id']} {r['title']} ({r['source_path']})")
    for i in issues:
        print(f"  ⚠️ {i}")

    # 读上次清单对比
    prev = {}
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            pass

    changed = []
    for r in with_hash:
        pid = str(r["id"])
        cur = r["content_hash"]
        if pid in prev and prev[pid] != cur:
            changed.append(f"#{pid} {r['title']}")
    if changed:
        print(f"  🔄 相对上次清单变化 {len(changed)} 页: {'; '.join(changed[:8])}")
    else:
        print("  🔄 相对上次清单: 无变化")

    # 更新清单
    snap = {str(r["id"]): r["content_hash"] for r in with_hash}
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)

    # 退出码: 有问题返回 1 (watchdog 可感知)
    if no_hash or empty:
        sys.exit(1)
    print("  ✅ 自检完成")


if __name__ == "__main__":
    asyncio.run(main())
