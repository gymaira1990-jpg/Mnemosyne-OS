#!/usr/bin/env python3
"""
skill_tokenize.py — 技能描述 jieba 分词 → skill_keywords (v7.7.0 BM25 通道)
对齐 wiki_tokenize 模式: 标题(技能名)权重 ×3, 描述 ×1, 过滤单字/停用词。
用法:
  PGDATABASE=xxx python3 skill_tokenize.py            # 增量
  PGDATABASE=xxx python3 skill_tokenize.py --all      # 全量重建
"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg, jieba  # noqa: E402

STOPWORDS = {"的", "了", "和", "与", "或", "在", "是", "用", "当", "要", "会", "可以",
             "怎么", "如何", "什么", "一个", "我们", "进行", "使用", "这个", "那个"}


def tokenize(text):
    toks = []
    for t in jieba.cut(text or ""):
        t = t.strip()
        if len(t) < 2 or t.isdigit() or t in STOPWORDS:
            continue
        toks.append(t)
    return toks


async def main(full_rebuild=False):
    conn = await asyncpg.connect(PG_DSN)
    try:
        if full_rebuild:
            await conn.execute("DELETE FROM skill_keywords")
        rows = await conn.fetch(
            "SELECT id, skill_name, description FROM skill_assets WHERE embedding IS NOT NULL")
        total = 0
        for r in rows:
            # 技能名 ×3, 描述 ×1 (权重编码进 freq)
            name_toks = tokenize(r["skill_name"].replace("-", " "))
            desc_toks = tokenize(r["description"])
            from collections import Counter
            freq = Counter()
            for t in name_toks:
                freq[t] += 3
            for t in desc_toks:
                freq[t] += 1
            if not freq:
                continue
            await conn.execute(
                "DELETE FROM skill_keywords WHERE skill_id=$1", r["id"])
            for t, f in freq.items():
                await conn.execute(
                    "INSERT INTO skill_keywords (skill_id, token, freq, tenant_id) "
                    "VALUES ($1,$2,$3,$4) ON CONFLICT (skill_id, token) DO UPDATE SET freq=$3",
                    r["id"], t, f, "default")
            total += 1
        print(f"[tokenize] 完成: {total} 技能, 关键词表已更新 (full={full_rebuild})")
    finally:
        await conn.close()

if __name__ == "__main__":
    full = "--all" in sys.argv
    asyncio.run(main(full_rebuild=full))
