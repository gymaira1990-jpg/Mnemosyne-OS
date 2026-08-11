#!/usr/bin/env python3
"""wiki_bm25 — WIKI 关键词通道 BM25 打分 (v7.5 P0a)

从 wiki_keywords 表计算 BM25 分数 (简化 BM25: 用 token 频次 + IDF)。
被 main.py search_wiki 调用, 与向量通道 RRF 融合。
"""
import math


def _idf_from_stats(total_pages: int, pages_with_token: int) -> float:
    """IDF = ln(1 + (N - n + 0.5) / (n + 0.5)), 防除零"""
    n = max(pages_with_token, 1)
    return math.log(1 + (total_pages - n + 0.5) / (n + 0.5))


def compute_bm25_scores(rows, query_tokens: list, total_pages: int) -> dict:
    """rows: [{'page_id', 'token', 'freq', 'pages_with_token'}]
    query_tokens: jieba 分词后的查询词
    返回 {page_id: bm25_score}
    BM25 = Σ IDF * (freq*(k1+1)) / (freq + k1*(1-b+b*dl/avgdl))
    简化: k1=1.5, b=0.75, dl≈freq 总和, avgdl 用页面平均 token 数
    """
    k1 = 1.5
    b = 0.75

    # 每页总词数 (dl) 与全局均值 (avgdl)
    page_dl = {}
    for r in rows:
        page_dl[r["page_id"]] = page_dl.get(r["page_id"], 0) + r["freq"]
    avgdl = sum(page_dl.values()) / max(len(page_dl), 1)

    scores = {}
    for tok in query_tokens:
        # 每行用自己的 pages_with_token 算 IDF (稀有词 IDF 更高)
        for r in rows:
            if r["token"] != tok:
                continue
            pid = r["page_id"]
            freq = r["freq"]
            idf = _idf_from_stats(total_pages, r["pages_with_token"])
            dl = page_dl.get(pid, 1)
            denom = freq + k1 * (1 - b + b * dl / max(avgdl, 1))
            score = idf * (freq * (k1 + 1)) / max(denom, 0.001)
            scores[pid] = scores.get(pid, 0) + score
    return scores


def rrf_fuse(vec_ranked: list, bm25_scores: dict = None, graph_scores: dict = None, k: int = 60) -> list:
    """Reciprocal Rank Fusion: 融合多通道 (向量 + BM25 + 图谱加成)。
    vec_ranked: [(page_id, distance), ...] 按距离升序(越近越好)
    bm25_scores: {page_id: score} (可空) — 独立通道, 给 RRF 排名分
    graph_scores: {page_id: score} (可空) — 加成通道, 只提升已有页面排名 (防噪音)
    返回 [(page_id, rrf_score), ...] 降序
    """
    bm25_scores = bm25_scores or {}
    graph_scores = graph_scores or {}
    rrf = {}
    for rank, (pid, _dist) in enumerate(vec_ranked):
        rrf[pid] = rrf.get(pid, 0) + 1.0 / (k + rank + 1)

    # BM25 通道: 按分数降序给排名分 (独立通道)
    if bm25_scores:
        sorted_bm = sorted(bm25_scores.items(), key=lambda x: -x[1])
        for rank, (pid, _) in enumerate(sorted_bm):
            rrf[pid] = rrf.get(pid, 0) + 1.0 / (k + rank + 1)

    # 图谱通道: 加成而非独立通道 — 只提升已命中页面, 不引入新页面 (防噪音)
    if graph_scores:
        for pid, score in graph_scores.items():
            if pid in rrf and score > 0:
                rrf[pid] = rrf[pid] + 0.02 * min(score, 1.0)

    return sorted(rrf.items(), key=lambda x: -x[1])
