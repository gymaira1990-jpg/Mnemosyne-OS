"""MCP 桥契约测试 — 入参形态 (user_id / feedback 必须走 query, 缺失即 422)

背景 (2026-09-12 生产实测): feedback_memory / delete_memory / restore_memory 三个工具
**必报 422** —— 桥把 feedback 发成 JSON body 且完全没传 user_id, 而服务端 REST 要求它们
都是 query 参数。用户侧看到的是"工具坏了"; 而同类错误若发生在**响应字段**上(如读 `heat`
而服务端返回 `heat_score`)则**连报错都没有**, 静默取默认值 —— 所以两边都锁契约。

本测试锁死 outbound 请求形态, 不依赖数据库/网络 (monkeypatch 掉 _call)。
mcp SDK 仅 Hermes 侧安装, 最小安装下自动 skip, 不影响服务端测试套件。
"""
import asyncio
import importlib.util
from pathlib import Path

import pytest

BRIDGE = (Path(__file__).resolve().parents[1]
          / "integrations" / "hermes-mcp" / "mnemosyne_mcp.py")


@pytest.fixture(scope="module")
def bridge():
    pytest.importorskip("mcp")      # 最小安装(无 Hermes)下跳过
    pytest.importorskip("httpx")
    spec = importlib.util.spec_from_file_location("mnes_bridge", BRIDGE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def calls(bridge, monkeypatch):
    """拦截 _call, 记录 (method, path, kwargs)。"""
    seen = []

    def fake_call(method, path, **kwargs):
        seen.append({"method": method, "path": path, "kwargs": kwargs})
        return {"status": "ok"}

    monkeypatch.setattr(bridge, "_call", fake_call)
    return seen


def _dispatch(bridge, name, arguments=None):
    return asyncio.run(bridge._dispatch(name, dict(arguments or {})))


class TestQueryParamContract:
    """三个"必填 query 参数"的 handler —— 漏传即 422。"""

    def test_feedback_uses_query_params_not_body(self, bridge, calls):
        _dispatch(bridge, "feedback_memory", {"memory_id": "42", "feedback": "positive"})
        req = calls[-1]
        assert (req["method"], req["path"]) == ("POST", "/memories/42/feedback")
        assert req["kwargs"]["params"]["user_id"] == "default"
        assert req["kwargs"]["params"]["feedback"] == "positive"
        assert "json" not in req["kwargs"], "feedback 发 JSON body 会被服务端 422"

    def test_feedback_honours_caller_user_id(self, bridge, calls):
        _dispatch(bridge, "feedback_memory",
                  {"memory_id": "7", "feedback": "negative", "user_id": "alice"})
        assert calls[-1]["kwargs"]["params"]["user_id"] == "alice"

    def test_delete_requires_user_id(self, bridge, calls):
        _dispatch(bridge, "delete_memory", {"memory_id": "99"})
        req = calls[-1]
        assert (req["method"], req["path"]) == ("DELETE", "/memories/99")
        assert req["kwargs"]["params"] == {"user_id": "default"}

    def test_restore_requires_user_id(self, bridge, calls):
        _dispatch(bridge, "restore_memory", {"memory_id": "99", "user_id": "bob"})
        req = calls[-1]
        assert (req["method"], req["path"]) == ("POST", "/memories/99/restore")
        assert req["kwargs"]["params"] == {"user_id": "bob"}


class TestBodyContractRegression:
    """回归: 别把 query 修过头 —— 需要 body 的端点仍走 json。"""

    def test_store_memory_uses_json_body(self, bridge, calls):
        _dispatch(bridge, "store_memory", {"content": "契约测试", "category": "knowledge"})
        req = calls[-1]
        assert (req["method"], req["path"]) == ("POST", "/memories")
        assert req["kwargs"]["json"]["user_id"] == "default"
        assert req["kwargs"]["json"]["content"] == "契约测试"
        assert "params" not in req["kwargs"]

    def test_search_memory_uses_json_body(self, bridge, calls):
        _dispatch(bridge, "search_memories", {"query": "契约"})
        req = calls[-1]
        assert req["path"] == "/memories/search"
        assert req["kwargs"]["json"]["query"] == "契约"


class TestSearchFieldContract:
    """字段名契约：发错名字不会报错，只会静默失效 —— 所以必须锁。

    2026-11-07 实测：桥发 category / mode，服务端 MemorySearch 的字段是 category_filter / sort，
    Pydantic 忽略多余字段 ⇒ 「按分类查」永远等于没过滤（过滤前后结果一模一样，且零报错）。
    """

    def test_search_uses_category_filter_not_category(self, bridge, calls):
        _dispatch(bridge, "search_memories", {"query": "部署", "category": "deploy"})
        body = calls[-1]["kwargs"]["json"]
        assert body["category_filter"] == "deploy"
        assert "category" not in body, "服务端没有 category 字段，发了就是静默丢弃"
        assert body["sort"] == "hybrid"
        assert "mode" not in body

    def test_search_omits_filter_when_not_given(self, bridge, calls):
        _dispatch(bridge, "search_memories", {"query": "部署"})
        body = calls[-1]["kwargs"]["json"]
        assert "category_filter" not in body, "没给分类就不该塞空条件"

    def test_store_keeps_importance_in_metadata(self, bridge, calls):
        _dispatch(bridge, "store_memory", {"content": "x", "category": "knowledge", "importance": 0.9})
        body = calls[-1]["kwargs"]["json"]
        assert body["metadata"]["importance"] == 0.9, "importance 不是 MemoryCreate 字段，必须落到 metadata 才不丢"
        assert "importance" not in body
        assert body["source"] == "hermes-mcp"
