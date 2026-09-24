#!/usr/bin/env python3
"""
core/rrf.py — Reciprocal Rank Fusion（秩融合），v8.0 S2-1
========================================================

为什么需要它
------------
v8.0 之前，主检索的融合方式是**单条 SQL 线性加权**：
    0.45*向量 + 0.15*BM25 + 0.15*时间 + 0.15*可靠性 + 0.10*热度
问题: 五路分数**量纲完全不同**（余弦距离 ∈[0,2] / BM25 无上界 / 时间 ∈{0,0.08,0.15}）
      → 加权系数没有物理意义，只能靠拍脑袋调参。

RRF 的做法是**只看排名，不看分数**：
    score(d) = Σ_over_channels  1 / (k + rank_channel(d) + 1)
量纲无关，且被搜索引擎业界长期验证（k=60 是通用默认）。

与既有实现的关系
----------------
`wiki/wiki_bm25.py` 里已有一个 `rrf_fuse(vec_ranked, bm25_scores, graph_scores, k=60)`，
它面向**向量距离 + 分数型通道 + 图谱加成**这一特定组合，已在 WIKI 检索路径验证有效。
本模块是它的**秩列表泛化版**：输入是 N 个「已排好序的 id 列表」，输出统一融合分。
两者公式一致（1/(k+rank+1), k=60）；本模块不依赖 asyncpg / 项目其它模块，**纯函数、可单测**。

命名空间注意（实测踩点）
------------------------
`memories.id` 与 `wiki_pages.id` 是**两套独立 id 空间**，数值会撞。
所以调用方必须在 fuse **之前**给 id 加前缀（如 `m:123` / `w:45`），
否则两个不相关的条目会被当成同一条互相加分。
本模块不替调用方做这件事 —— 它只做纯秩融合；前缀由 `palace.summon_fused` 负责。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


def rrf_fuse_ranked(
    ranked_lists: Mapping[str, Sequence],
    k: int = 60,
    weights: Mapping[str, float] | None = None,
) -> List[Tuple]:
    """秩融合。

    ranked_lists : {通道名: [id, id, ...]}  —— 每个列表**已按该通道的好坏降序排列**
    k            : RRF 平滑常数，默认 60（越大则头部优势越平缓）
    weights      : 可选 {通道名: 权重}，缺省全部 1.0（等权）

    返回 : [(id, score, {通道: 该通道内 rank})] 按 score 降序。
           第二项 score 为融合分；第三项 channels 用于**可解释性**：
           回答“这条为什么被排上来” —— 是单通道高分，还是多通道共同命中。

    设计取舍（写进代码，不靠口头约定）:
      - **只看排名**，不看原始分 → 量纲无关，无需归一化
      - **多通道命中自动占优**：一条被 3 个通道同时命中的条目，
        得分必然高于只在 1 个通道排第一的条目（k 足够大时）。
        这正是我们想要的“共识优先”，且它是**数学结果**而非调参结果。
    """
    if k < 1:
        raise ValueError("k 必须 >= 1")
    weights = weights or {}
    scores: Dict = {}
    channels: Dict = {}

    for ch, ids in ranked_lists.items():
        w = float(weights.get(ch, 1.0))
        if w == 0:
            continue
        for rank, item_id in enumerate(ids):
            scores[item_id] = scores.get(item_id, 0.0) + w * (1.0 / (k + rank + 1))
            channels.setdefault(item_id, {})[ch] = rank

    return sorted(
        ((i, round(s, 10), channels[i]) for i, s in scores.items()),
        key=lambda t: (-t[1], str(t[0])),
    )


def fuse_within_topk(fused: Iterable[Tuple], top_k: int) -> List[Tuple]:
    """截断到 top_k（单独成函数，便于测试与复用）。"""
    if top_k < 0:
        raise ValueError("top_k 不能为负")
    out = []
    for i, row in enumerate(fused):
        if i >= top_k:
            break
        out.append(row)
    return out
