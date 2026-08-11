"""v7.5 WIKI hybrid 检索 — BM25 + RRF 纯函数测试 (不依赖 DB)

覆盖: BM25 打分 (IDF/词频/长度归一) + RRF 融合 (双通道排名)。
生产逻辑同源复制 (见 wiki_bm25.py)。
"""
import sys
sys.path.insert(0, ".")
from wiki.wiki_bm25 import compute_bm25_scores, rrf_fuse


class TestBM25:
    def test_high_freq_scores_higher(self):
        rows = [
            {"page_id": 1, "token": "记忆", "freq": 5, "pages_with_token": 2},
            {"page_id": 2, "token": "记忆", "freq": 1, "pages_with_token": 2},
        ]
        s = compute_bm25_scores(rows, ["记忆"], 10)
        assert s.get(1, 0) > s.get(2, 0)

    def test_rare_token_gets_higher_idf(self):
        rows = [
            {"page_id": 1, "token": "浑天芯算", "freq": 3, "pages_with_token": 1},
            {"page_id": 2, "token": "浑天芯算", "freq": 3, "pages_with_token": 5},
        ]
        s = compute_bm25_scores(rows, ["浑天芯算"], 10)
        assert s.get(1, 0) > s.get(2, 0)  # 罕见词 IDF 更高

    def test_empty_query(self):
        assert compute_bm25_scores([], [], 10) == {}

    def test_multi_token_accumulates(self):
        rows = [
            {"page_id": 1, "token": "记忆", "freq": 5, "pages_with_token": 2},
            {"page_id": 1, "token": "宫殿", "freq": 3, "pages_with_token": 1},
        ]
        s = compute_bm25_scores(rows, ["记忆", "宫殿"], 10)
        assert s.get(1, 0) > 0


class TestRRF:
    def test_fusion_combines_channels(self):
        vec = [(1, 0.1), (2, 0.3), (3, 0.5)]  # 向量通道: 1 最前
        bm = {2: 10.0, 4: 20.0}  # BM25 通道: 4 最高分, 2 高分
        fused = rrf_fuse(vec, bm, k=60)
        ids = [pid for pid, _ in fused]
        # BM25 高分的 2 应该进前二 (向量第2 + BM25 第2)
        assert ids[0] == 2 or ids[1] == 2
        # 4 只在 BM25 出现, 应排在纯向量 3 之前 (BM25 排名1)
        assert ids.index(4) < ids.index(3)

    def test_graph_boost_only_existing(self):
        """图谱是加成通道: 只提升已有页面, 不引入新页面"""
        vec = [(1, 0.1), (2, 0.2), (3, 0.3)]
        bm = {}
        graph = {1: 1.0, 99: 1.0}  # 99 不在向量结果中, 不应被引入
        fused = rrf_fuse(vec, bm, graph, k=60)
        ids = [pid for pid, _ in fused]
        assert 99 not in ids  # 防噪音: 图谱独有页面不进入结果
        assert ids[0] == 1  # 图谱加成后 1 仍保持第一 (加成不改变排序本质)

    def test_graph_boost_reorders_within_existing(self):
        """图谱加成可以提升已有页面的相对排名"""
        vec = [(1, 0.1), (2, 0.11), (3, 0.12)]  # 1 略优于 2, 2 略优于 3
        bm = {}
        graph = {2: 1.0}  # 图谱给 2 强加成
        fused = rrf_fuse(vec, bm, graph, k=60)
        ids = [pid for pid, _ in fused]
        assert ids[0] == 2  # 加成后 2 超越 1

    def test_k_parameter_smoothing(self):
        vec = [(1, 0.1), (2, 0.2)]
        bm = {2: 100.0}
        fused_small = rrf_fuse(vec, bm, k=1)
        fused_big = rrf_fuse(vec, bm, k=60)
        assert fused_small[0][0] == 2  # k 小 = 排名权重更陡, BM25 第1 稳赢
        assert fused_big[0][0] == 2

    def test_empty_bm25_falls_back_to_vec(self):
        vec = [(1, 0.1), (2, 0.2)]
        fused = rrf_fuse(vec, {}, k=60)
        assert [pid for pid, _ in fused] == [1, 2]  # 保持向量原序

    def test_tie_handling(self):
        vec = [(1, 0.1)]
        bm = {1: 5.0}
        fused = rrf_fuse(vec, bm)
        assert fused[0][0] == 1  # 双通道命中, 不报错不重复
