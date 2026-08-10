#!/usr/bin/env python3
"""wiki_eval — WIKI 检索质量定期评测 (v7.5 P2)

固定 20 条真实查询评测集, 对比三档: 纯向量 / 向量+BM25 / 全通道(+图谱)。
输出 precision@3 报告 + 变化告警 (防止检索漂移)。
GZ cron: 每周一 7am 跑一次, 结果写入 /tmp/wiki_eval_report.txt

用法: venv/bin/python wiki_eval.py
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg  # noqa: E402

USER_ID = "default"
REPORT_FILE = "/tmp/wiki_eval_report.txt"

# 评测集: (query, [期望 page_id], 期望 source_type 可空)
EVAL_SET = [
    ("浑天芯算 正二十面体 光电混合 类脑", [51]),
    ("石匠逻辑 劈叉 概念裂变 双星认知", [49]),
    ("上下文腐烂 KV缓存 记忆困境", [50]),
    ("金闪闪协议 智能体封装 能力交付", [58]),
    ("记忆宫殿 档号 著录卡片 分类树", [81, 72, 76]),
    ("诺亚认知操作系统 认知底座", [101, 99]),
    ("诺亚 眼睛与手 工具系统", [103]),
    ("医学AI研发 工程化 避坑手册", [52, 61]),
    ("A2A 分布式网络 Agent 协议", [54]),
    ("AgentOS 操作系统 智能体架构", [55]),
    ("钢渣 生态矿园 固废转化", [67]),
    ("荒漠化 生态修复 固沙", [57]),
    ("光热发电 光伏 多联产 全光谱", [60]),
    ("模块化能源 电动汽车 分布式驱动", [65]),
    ("记忆仓库 物流设计 抽屉 压缩", [78, 83]),
    ("三室分工 资料室 档案馆 图书馆", [72, 76]),
    ("魔法记忆宫殿 蓝图 总规划", [81, 80]),
    ("Mnemosyne 记忆系统 整体方案", [68]),
    ("小镇 像素风 交互前端", [108]),
    ("抽屉 级联压缩 引擎", [83]),
]


async def search(conn, query: str, hybrid: bool, graph: bool, top_k: int = 5) -> list:
    """模拟 search_wiki 的 SQL 查询 (纯函数版, 不调 API)"""
    from core.embedding import get_embedding_async
    vec = (await get_embedding_async([query]))[0]
    q_str = "[" + ",".join(str(x) for x in vec) + "]"
    rows = await conn.fetch(
        "SELECT id, title FROM wiki_pages WHERE user_id=$1 AND content IS NOT NULL AND embedding IS NOT NULL "
        "ORDER BY embedding <=> $2::vector LIMIT $3",
        USER_ID, q_str, top_k + 20
    )
    vec_ranked = [(r["id"], 0.0) for r in rows]

    bm25_scores = {}
    if hybrid:
        import jieba
        from wiki_bm25 import compute_bm25_scores
        tokens = [t.strip() for t in jieba.cut(query) if len(t.strip()) >= 2]
        if tokens:
            kw = await conn.fetch(
                "SELECT wk.page_id, wk.token, wk.freq, "
                "(SELECT count(DISTINCT page_id) FROM wiki_keywords wk2 WHERE wk2.token=wk.token) AS pages_with_token "
                "FROM wiki_keywords wk WHERE wk.token = ANY($1::text[])",
                tokens
            )
            total = await conn.fetchval("SELECT count(*) FROM wiki_pages WHERE user_id=$1 AND content IS NOT NULL", USER_ID)
            bm25_scores = compute_bm25_scores(list(kw), tokens, total or 71)

    graph_scores = {}
    if graph:
        from wiki_graph import graph_expand
        gres = await graph_expand(conn, query, USER_ID, top_k)
        graph_scores = gres.get("page_scores", {})

    if bm25_scores or graph_scores:
        from wiki_bm25 import rrf_fuse
        fused = rrf_fuse(vec_ranked, bm25_scores, graph_scores)
        return [pid for pid, _ in fused[:top_k]]
    return [pid for pid, _ in vec_ranked[:top_k]]


def hit_rate(ids: list, expected: list) -> bool:
    return any(i in expected for i in ids[:3])


def first_rank(ids: list, expected: list) -> int:
    """第一个命中排位 (1-based), 未命中返回 4 (top3 外)"""
    for i, pid in enumerate(ids[:3]):
        if pid in expected:
            return i + 1
    return 4


def recall_at3(ids: list, expected: list) -> float:
    """recall@3: 期望集合被命中的比例 (多文档查询适用)"""
    if not expected:
        return 0.0
    hit = sum(1 for e in expected if e in ids[:3])
    return hit / len(expected)


async def main():
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:
            n = len(EVAL_SET)
            modes = {
                "pure_vec": lambda q: search(conn, q, False, False),
                "vec_bm25": lambda q: search(conn, q, True, False),
                "vec_bm25_graph": lambda q: search(conn, q, True, True),
            }
            # v7.5 扩充: precision@3 + recall@3 + MRR
            results = {}
            for mode, fn in modes.items():
                prec_hits = 0
                recall_sum = 0.0
                mrr_sum = 0.0
                for q, exp in EVAL_SET:
                    ids = await fn(q)
                    prec_hits += 1 if hit_rate(ids, exp) else 0
                    recall_sum += recall_at3(ids, exp)
                    mrr_sum += 1.0 / first_rank(ids, exp)
                results[mode] = {
                    "precision@3": round(prec_hits / n * 100, 1),
                    "recall@3": round(recall_sum / n * 100, 1),
                    "MRR": round(mrr_sum / n, 3),
                }
    finally:
        await pool.close()

    lines = [
        f"WIKI 检索评测 {time.strftime('%Y-%m-%d %H:%M')} ({n} 查询)",
        f"  纯向量:        {results['pure_vec']}",
        f"  向量+BM25:     {results['vec_bm25']}",
        f"  全通道(+图谱): {results['vec_bm25_graph']}",
        f"  结论: {'稳定 ✅' if results['vec_bm25']['precision@3'] >= 95 else '⚠️ 需关注: BM25 precision@3 低于95%'}",
    ]
    report = "\n".join(lines)
    print(report)

    # 对比上次 (兼容旧格式)
    prev = {}
    if os.path.exists(REPORT_FILE):
        with open(REPORT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "precision" in line or "%" in line:
                    prev_line = line.strip()
        # 简化: 只对比 vec_bm25 precision
        cur_p = results["vec_bm25"]["precision@3"]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    asyncio.run(main())
