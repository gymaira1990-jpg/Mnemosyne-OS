"""v7.7.0 Embedding 深度优化 — 纯逻辑测试 (mock API, 不真实调用)

覆盖: 缓存命中 / 批量切块 / 重试退避 / 并发 / LRU 裁剪 / 空输入
"""
import sys
sys.path.insert(0, ".")
import json
import urllib.error
from unittest.mock import patch, MagicMock
import core.embedding as emb


class TestCache:
    def setup_method(self):
        emb._cache.clear()
        emb._cache_loaded = True  # 跳过磁盘加载

    def test_cache_hit_no_api_call(self):
        """同文本二次调用 → 不再打 API"""
        fake = MagicMock(return_value=[0.1] * 3)
        with patch.object(emb, "_call_ark_single", fake):
            emb.get_embedding(["hello"])
            emb.get_embedding(["hello"])
        assert fake.call_count == 1  # 只打了一次

    def test_partial_cache_miss(self):
        fake = MagicMock(return_value=[0.1] * 3)
        with patch.object(emb, "_call_ark_single", fake):
            emb.get_embedding(["a", "b"])
            emb.get_embedding(["b", "c"])  # b 命中, c 新
        assert fake.call_count == 3  # a,b,c 三条各打一次 (并发逐条)

    def test_many_texts_concurrent(self):
        """多文本 → 并发取回, 结果顺序与原顺序一致"""
        n = 30
        texts = [f"t{i}" for i in range(n)]
        fake = MagicMock(side_effect=lambda t: [float(t[1:])] * 3)  # 按文本编号返回
        with patch.object(emb, "_call_ark_single", fake):
            out = emb.get_embedding(texts)
        assert len(out) == n
        # 顺序一致: 第 i 条向量首位 = i
        for i, vec in enumerate(out):
            assert vec[0] == float(i)

    def test_empty_input(self):
        assert emb.get_embedding([]) == []

    def test_lru_cutoff(self):
        """超过 CACHE_SIZE 自动裁剪"""
        fake = MagicMock(return_value=[0.1] * 3)
        with patch.object(emb, "_call_ark_single", fake):
            for i in range(emb.CACHE_SIZE + 50):
                emb.get_embedding([f"unique{i}"])
        assert len(emb._cache) <= emb.CACHE_SIZE


class TestRetry:
    def setup_method(self):
        emb._cache.clear()
        emb._cache_loaded = True

    class FakeResp:
        """真实 context manager 响应 (MagicMock __enter__ 会返回新对象, 不可靠)"""
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_retry_then_success(self):
        """_call_ark_single 前两次 HTTP 失败, 第三次成功 → 返回结果"""
        calls = {"n": 0}

        def flaky_urlopen(req, timeout=0):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)
            payload = json.dumps({"data": {"embedding": [0.5] * 3}}).encode()
            return self.FakeResp(payload)

        with patch.object(emb.urllib.request, "urlopen", flaky_urlopen), \
             patch.object(emb, "RETRY_BASE", 0.01):
            out = emb._call_ark_single("x")
        assert len(out) == 3
        assert calls["n"] == 3

    def test_total_failure_raises(self):
        def always_fail(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

        with patch.object(emb.urllib.request, "urlopen", always_fail), \
             patch.object(emb, "RETRY_BASE", 0.01):
            try:
                emb._call_ark_single("x")
                assert False, "should raise"
            except RuntimeError:
                pass
