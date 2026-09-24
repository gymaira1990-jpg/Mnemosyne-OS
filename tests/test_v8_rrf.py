#!/usr/bin/env python3
"""
v8.0 S2-1 · RRF 秩融合纯函数测试（无需数据库）

覆盖:
  R1 基本融合与降序
  R2 多通道共识优先（这是 RRF 的核心价值，必须是**数学结果**而非调参）
  R3 k 参数效应
  R4 权重
  R5 top_k 截断
  R6 非法入参被拒（反证）
  R7 空输入不炸
  R8 命名空间隔离（memories/wiki 两套 id 空间）
"""
import pytest

from core.rrf import rrf_fuse_ranked, fuse_within_topk


def test_r1_basic_desc_order():
    fused = rrf_fuse_ranked({"a": ["x", "y", "z"]})
    assert [i for i, _s, _c in fused] == ["x", "y", "z"]
    assert fused[0][1] > fused[1][1] > fused[2][1]


def test_r2_multichannel_consensus_wins():
    """只在 1 个通道排第 1 的，应当**输给**在 3 个通道都靠前的条目。

    这是 RRF 存在的理由 —— 若这条挂掉，说明融合没有意义。
    """
    fused = rrf_fuse_ranked({
        "vec":    ["solo_first", "shared"],
        "bm25":   ["shared", "other"],
        "time":   ["shared", "another"],
    })
    order = [i for i, _s, _c in fused]
    assert order[0] == "shared", f"共识条目应排第一，实际: {order}"
    shared = next(t for t in fused if t[0] == "shared")
    assert set(shared[2].keys()) == {"vec", "bm25", "time"}, "应记录三个通道的命中"


def test_r3_k_controls_flatness():
    """k 越大头部优势越平缓：第 1 名与第 2 名的差距应随 k 单调收窄。"""
    lists = {"a": ["p", "q"]}
    gaps = []
    for k in (1, 10, 60, 1000):
        f = rrf_fuse_ranked(lists, k=k)
        gaps.append(round(f[0][1] - f[1][1], 12))
    assert gaps == sorted(gaps, reverse=True), f"差距应随 k 递减: {gaps}"
    assert gaps[0] > gaps[-1], "k 的效应必须真实存在"


def test_r4_weights_shift_ranking():
    lists = {"a": ["x"], "b": ["y"]}
    equal = [i for i, _s, _c in rrf_fuse_ranked(lists)]
    assert equal == sorted(equal) or equal in (["x", "y"], ["y", "x"])
    biased = [i for i, _s, _c in rrf_fuse_ranked(lists, weights={"b": 5.0, "a": 1.0})]
    assert biased[0] == "y", "加权后应改变排序"
    zeroed = [i for i, _s, _c in rrf_fuse_ranked(lists, weights={"b": 0.0})]
    assert zeroed == ["x"], "权重 0 的通道应完全不参与"


def test_r5_topk_truncation():
    fused = rrf_fuse_ranked({"a": list("abcdefghij")})
    assert len(fuse_within_topk(fused, 3)) == 3
    assert len(fuse_within_topk(fused, 0)) == 0
    assert len(fuse_within_topk(fused, 100)) == 10


def test_r6_invalid_args_rejected():
    """反证：故意传非法值，必须被拒 —— 而不是静默算出错误结果。"""
    with pytest.raises(ValueError):
        rrf_fuse_ranked({"a": ["x"]}, k=0)
    with pytest.raises(ValueError):
        rrf_fuse_ranked({"a": ["x"]}, k=-5)
    with pytest.raises(ValueError):
        fuse_within_topk([], top_k=-1)


def test_r7_empty_input_is_safe():
    assert rrf_fuse_ranked({}) == []
    assert rrf_fuse_ranked({"a": []}) == []
    assert fuse_within_topk([], 5) == []


def test_r8_namespace_isolation():
    """两套 id 空间：不加前缀会让 memories#1 与 wiki#1 互相加分（错误合并）。

    这条锁住 palace._ns 的存在理由 —— 若有人图省事去掉前缀，此处会红。
    """
    from palace import _ns
    assert _ns("wiki", 1) == "w:1"
    assert _ns("resonate", 1) == "m:1"
    assert _ns("summon", 1) == "m:1"
    # 同一数值在 memory / wiki 通道里是**不同**条目
    fused = rrf_fuse_ranked({"resonate": [_ns("resonate", 1)], "wiki": [_ns("wiki", 1)]})
    assert len(fused) == 2, "数值相同但命名空间不同，必须算两条"
