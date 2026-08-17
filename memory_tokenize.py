#!/usr/bin/env python3
"""memory_tokenize — 记忆 jieba 分词 → memory_keywords 表 (v7.8)

为主搜索真 BM25 建关键词索引: 每条记忆分词, 存 token+freq。
- 与 wiki_tokenize 同构; 记忆无标题, 正文即内容; 短记忆(<50)跳过
- 增量: 未分词的记忆 (metadata->>'kw_tokenized' IS NULL)

用法 (GZ):
    cd /opt/mnemosyne && venv/bin/python memory_tokenize.py --batch 500
    venv/bin/python memory_tokenize.py --all
"""
import asyncio
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg  # noqa: E402
import jieba  # noqa: E402

# 复用 wiki 专业词典 (术语分词)
_DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wiki", "wiki_dict.txt")
if os.path.exists(_DICT_PATH):
    jieba.load_userdict(_DICT_PATH)

USER_ID = "default"
MIN_LEN = 30  # 短记忆不值得分词 (wiki 用 50, 记忆普遍更短)


def clean_token(tok: str) -> bool:
    if len(tok) < 2 or len(tok) > 20:
        return False
    if tok.isdigit() or tok.isspace():
        return False
    if not any(c.isalnum() for c in tok):
        return False
    return True


def tokenize_content(content: str) -> list:
    """返回 [(token, freq), ...]; 前 60 字符当"标题"加权 ×2 (记忆开头常是主题)"""
    head_toks = [t.strip() for t in jieba.cut(content[:60]) if clean_token(t.strip())]
    body_toks = [t.strip() for t in jieba.cut(content[:20000]) if clean_token(t.strip())]
    cnt = Counter()
    for t in head_toks:
        cnt[t] += 2
    for t in body_toks:
        cnt[t] += 1
    return list(cnt.items())


async def tokenize_memory(conn, mem) -> dict:
    mid = mem["id"]
    content = mem["content"] or ""
    if len(content) < MIN_LEN:
        return {"id": mid, "status": "skipped-small"}
    toks = tokenize_content(content)
    if not toks:
        return {"id": mid, "status": "no-tokens"}
    await conn.execute("DELETE FROM memory_keywords WHERE memory_id=$1", mid)
    await conn.executemany(
        "INSERT INTO memory_keywords (memory_id, token, freq) VALUES ($1,$2,$3) "
        "ON CONFLICT (memory_id, token) DO UPDATE SET freq=EXCLUDED.freq",
        [(mid, t, f) for t, f in toks]
    )
    await conn.execute(
        "UPDATE memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{\"kw_tokenized\":true}'::jsonb "
        "WHERE id=$1", mid)
    return {"id": mid, "status": "ok", "tokens": len(toks)}


async def main(batch: int, all_pages: bool):
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            if all_pages:
                rows = await conn.fetch(
                    "SELECT id, content FROM memories WHERE user_id=$1 AND is_deleted=FALSE "
                    "AND content IS NOT NULL AND length(content)>=$2 ORDER BY id",
                    USER_ID, MIN_LEN
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, content FROM memories WHERE user_id=$1 AND is_deleted=FALSE "
                    "AND content IS NOT NULL AND length(content)>=$2 "
                    "AND COALESCE(metadata->>'kw_tokenized','false')='false' "
                    "ORDER BY id LIMIT $3",
                    USER_ID, MIN_LEN, batch
                )
            if not rows:
                print("无待分词记忆")
                return
            print(f"分词 {len(rows)} 条 ...")
            total_tokens = 0
            for mem in rows:
                start = time.time()
                r = await tokenize_memory(conn, mem)
                total_tokens += r.get("tokens", 0)
                if r["status"] == "ok":
                    print(f"  #{r['id']} tokens={r['tokens']} ({round(time.time()-start,2)}s)")
            print(f"完成: {len(rows)} 条, {total_tokens} tokens")
    finally:
        await pool.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--all", action="store_true", help="全量重建")
    args = ap.parse_args()
    asyncio.run(main(args.batch, args.all))
