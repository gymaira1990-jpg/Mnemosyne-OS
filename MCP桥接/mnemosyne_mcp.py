#!/usr/bin/env python3
"""
Mnemosyne MCP Server — 桥接 Hermes 与记忆宫殿

通过 SSH 隧道 (localhost:18010) 连接到 GZ 服务器上的 Mnemosyne REST API,
为 Hermes Agent 提供记忆存储/检索/MCP 工具。

启动方式 (注册到 Hermes config.yaml):
  mcp_servers:
    mnemosyne:
      command: "python3"
      args: ["/home/g-cat/.hermes/hermes-agent/tools/mnemosyne_mcp.py"]
"""

import json
import os
import sys
import httpx
from typing import Any, Optional

# ── Mnemosyne API 地址 ─────────────────────────────────
MNEMOSYNE_URL = os.getenv("MNEMOSYNE_URL", "http://127.0.0.1:18010")
API_BASE = f"{MNEMOSYNE_URL}/api/v1"


# ── MCP SDK 导入 ───────────────────────────────────────
try:
    import mcp.server as mcp_server
    import mcp.types as types
    from mcp.server.lowlevel import Server
except ImportError:
    print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


# ── HTTP 客户端 ────────────────────────────────────────
http = httpx.Client(timeout=30, base_url=MNEMOSYNE_URL)


def _call(method: str, path: str, **kwargs) -> dict:
    """调用 Mnemosyne REST API，自动处理异常。"""
    try:
        r = http.request(method, f"{API_BASE}{path}", **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        detail = ""
        if hasattr(e, "response") and e.response is not None:
            detail = e.response.text
        return {"error": str(e), "detail": detail}


# ── MCP Server 定义 ────────────────────────────────────
app = Server("mnemosyne")


# ── 工具列表 ────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── 记忆核心 ──
        types.Tool(
            name="store_memory",
            description="存储一条记忆到 Mnemosyne。用户 ID 默认为 'g-cat'。",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "记忆内容"},
                    "category": {"type": "string", "description": "分类: fact|experience|belief|chat|work|note|test", "default": "fact"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "importance": {"type": "number", "description": "重要性 0-1", "default": 0.5},
                },
                "required": ["content"],
            },
        ),
        types.Tool(
            name="search_memories",
            description="四维搜索记忆（语义+关键词+时序+图谱）。返回最匹配的记忆。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                    "category": {"type": "string", "description": "可选：按分类过滤"},
                    "mode": {"type": "string", "description": "hybrid|semantic|fulltext", "default": "hybrid"},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_hot_memories",
            description="获取热度最高的记忆（L1梯队）。快速了解当前最重要信息。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "limit": {"type": "integer", "description": "返回条数", "default": 10},
                    "min_heat": {"type": "number", "description": "最低热度阈值", "default": 0.0},
                },
            },
        ),
        # ── 记忆管理 ──
        types.Tool(
            name="get_memory_stats",
            description="获取记忆库健康报告：总条数、分类分布、热度层级、平均热度、删除数。",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                },
            },
        ),
        types.Tool(
            name="feedback_memory",
            description="对记忆可信度反馈：positive=升温, negative=降温。影响后续检索排序。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆 ID"},
                    "feedback": {"type": "string", "description": "positive|negative"},
                },
                "required": ["memory_id", "feedback"],
            },
        ),
        types.Tool(
            name="get_memory_traces",
            description="查看记忆的生命周期历史：存储、召回、反馈、删除、恢复等。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆 ID"},
                },
                "required": ["memory_id"],
            },
        ),
        types.Tool(
            name="delete_memory",
            description="软删除一条记忆（可恢复）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆 ID"},
                },
                "required": ["memory_id"],
            },
        ),
        types.Tool(
            name="restore_memory",
            description="恢复一条已软删除的记忆。",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "记忆 ID"},
                },
                "required": ["memory_id"],
            },
        ),
        # ── 知识图谱 ──
        types.Tool(
            name="search_graph",
            description="在知识图谱中搜索实体和关系。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "limit": {"type": "integer", "description": "返回条数", "default": 10},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="extract_entities",
            description="从文本中自动提取实体，存入知识图谱。",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "待提取的文本"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                },
                "required": ["text"],
            },
        ),
        # ── Wiki ──
        types.Tool(
            name="create_wiki_page",
            description="创建或更新 Wiki 页面（版本化知识文档）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Wiki 标题"},
                    "content": {"type": "string", "description": "Wiki 内容"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                },
                "required": ["title", "content"],
            },
        ),
        types.Tool(
            name="search_wiki",
            description="搜索 Wiki 页面（支持模糊匹配）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "limit": {"type": "integer", "description": "返回条数", "default": 5},
                },
                "required": ["query"],
            },
        ),
        # ── 信念系统 ──
        types.Tool(
            name="store_belief",
            description="存储一条信念到信念系统。",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "信念内容"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                },
                "required": ["content"],
            },
        ),
        types.Tool(
            name="search_beliefs",
            description="搜索信念库。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户 ID", "default": "g-cat"},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                },
                "required": ["query"],
            },
        ),
    ]


# ── 工具调用处理 ──────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    user_id = arguments.pop("user_id", "g-cat")

    try:
        if name == "store_memory":
            data = _call("POST", "/memories", json={
                "user_id": user_id,
                "content": arguments["content"],
                "category": arguments.get("category", "fact"),
                "importance": arguments.get("importance", 0.5),
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "search_memories":
            data = _call("POST", "/memories/search", json={
                "user_id": user_id,
                "query": arguments["query"],
                "top_k": arguments.get("top_k", 5),
                "category": arguments.get("category"),
                "mode": arguments.get("mode", "hybrid"),
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "get_hot_memories":
            params = {"user_id": user_id, "limit": arguments.get("limit", 10)}
            if arguments.get("min_heat"):
                params["min_heat"] = arguments["min_heat"]
            data = _call("GET", "/memories/heat-top", params=params)
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "get_memory_stats":
            data = _call("GET", "/memories/stats", params={"user_id": user_id})
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "feedback_memory":
            data = _call("POST", f"/memories/{arguments['memory_id']}/feedback", json={
                "feedback": arguments["feedback"],
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "get_memory_traces":
            data = _call("GET", f"/memories/{arguments['memory_id']}/traces")
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "delete_memory":
            data = _call("DELETE", f"/memories/{arguments['memory_id']}")
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "restore_memory":
            data = _call("POST", f"/memories/{arguments['memory_id']}/restore")
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "search_graph":
            data = _call("POST", "/graph/search", json={
                "user_id": user_id,
                "query": arguments["query"],
                "limit": arguments.get("limit", 10),
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "extract_entities":
            data = _call("POST", "/extract-entities", json={
                "text": arguments["text"],
                "user_id": user_id,
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "create_wiki_page":
            data = _call("POST", "/wiki", json={
                "title": arguments["title"],
                "content": arguments["content"],
                "user_id": user_id,
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "search_wiki":
            data = _call("POST", "/wiki/search", json={
                "query": arguments["query"],
                "user_id": user_id,
                "limit": arguments.get("limit", 5),
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "store_belief":
            data = _call("POST", "/beliefs", json={
                "user_id": user_id,
                "content": arguments["content"],
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        elif name == "search_beliefs":
            data = _call("POST", "/beliefs/search", json={
                "user_id": user_id,
                "query": arguments["query"],
                "top_k": arguments.get("top_k", 5),
            })
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ── 启动 ────────────────────────────────────────────────
async def main():
    async with mcp_server.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
