#!/usr/bin/env python3
"""
TMT MCP Server — Temporal Memory Tree bridge for Hermes

Connects to the GZ Mnemosyne REST API via SSH tunnel (localhost:18010),
providing TMT (Temporal Memory Tree) tools for multi-level memory
consolidation, semantic recall, and tree browsing.

Registration (Hermes config.yaml):
  mcp_servers:
    tmt:
      command: "python3"
      args: ["/home/g-cat/.hermes/hermes-agent/tools/tmt_mcp.py"]
"""

import json
import os
import sys
import httpx
from typing import Any, Optional

# ── Mnemosyne API address ─────────────────────────────────
MNEMOSYNE_URL = os.getenv("MNEMOSYNE_URL", "http://127.0.0.1:18010")
API_BASE = f"{MNEMOSYNE_URL}/api/v1"


# ── MCP SDK import ────────────────────────────────────────
try:
    import mcp.server as mcp_server
    import mcp.types as types
    from mcp.server.lowlevel import Server
except ImportError:
    print("ERROR: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


# ── HTTP client ───────────────────────────────────────────
http = httpx.Client(timeout=30, base_url=MNEMOSYNE_URL)


def _call(method: str, path: str, **kwargs) -> dict:
    """Call Mnemosyne REST API, handling errors gracefully."""
    try:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        r = http.request(method, url, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        detail = ""
        if hasattr(e, "response") and e.response is not None:
            detail = e.response.text
        return {"error": str(e), "detail": detail}


# ── MCP Server definition ─────────────────────────────────
app = Server("tmt")


# ── Tool list ──────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="tmt_recall",
            description="Semantic TMT search across all memory tiers (L1→L3). Uses 3-stage smart recall.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "user_id": {"type": "string", "description": "User ID", "default": "g-cat"},
                    "complexity_hint": {"type": "string", "description": "Hint: simple|moderate|complex", "default": "moderate"},
                    "max_results": {"type": "integer", "description": "Max results to return", "default": 5},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="tmt_store",
            description="Store a raw L1 memory in Mnemosyne and optionally trigger session consolidation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Memory content to store"},
                    "user_id": {"type": "string", "description": "User ID", "default": "g-cat"},
                    "session_id": {"type": "string", "description": "Optional session ID for consolidation grouping"},
                    "category": {"type": "string", "description": "Category: fact|experience|belief|chat|work|note|test", "default": "fact"},
                },
                "required": ["content"],
            },
        ),
        types.Tool(
            name="tmt_consolidate",
            description="Trigger manual TMT distillation/session consolidation at a given level.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "description": "Consolidation level: session|daily|weekly|monthly"},
                    "user_id": {"type": "string", "description": "User ID", "default": "g-cat"},
                    "date": {"type": "string", "description": "Date/period (ISO date for daily/weekly/monthly, optional)"},
                    "session_id": {"type": "string", "description": "Session ID (for session-level consolidation)"},
                },
                "required": ["level", "user_id"],
            },
        ),
        types.Tool(
            name="tmt_tree",
            description="Browse the full TMT structure overview for a user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID", "default": "g-cat"},
                },
            },
        ),
        types.Tool(
            name="tmt_profile",
            description="Get active user profile: recent memory count, TMT levels, and tree stats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID", "default": "g-cat"},
                },
            },
        ),
    ]


# ── Tool call handler ─────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    user_id = arguments.pop("user_id", "g-cat")

    try:
        # ── tmt_recall: 3-stage semantic TMT search ─────
        if name == "tmt_recall":
            payload = {
                "user_id": user_id,
                "query": arguments["query"],
                "max_results": arguments.get("max_results", 5),
            }
            if arguments.get("complexity_hint"):
                payload["complexity_hint"] = arguments["complexity_hint"]
            data = _call("POST", "/tmt/recall", json=payload)
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        # ── tmt_store: store L1 memory + optional consolidation ──
        elif name == "tmt_store":
            # Step 1: Store raw L1 memory
            store_payload = {
                "user_id": user_id,
                "content": arguments["content"],
                "category": arguments.get("category", "fact"),
            }
            mem_result = _call("POST", "/memories", json=store_payload)

            # Step 2: Optionally trigger session consolidation
            session_id = arguments.get("session_id")
            if session_id and "error" not in mem_result:
                cons_payload = {"user_id": user_id, "session_id": session_id}
                cons_result = _call("POST", "/tmt/consolidate/session", json=cons_payload)
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"memory": mem_result, "consolidation": cons_result}, ensure_ascii=False),
                )]

            return [types.TextContent(type="text", text=json.dumps(mem_result, ensure_ascii=False))]

        # ── tmt_consolidate: trigger manual distillation ──
        elif name == "tmt_consolidate":
            level = arguments["level"]
            payload = {"user_id": user_id}

            if level == "session":
                if arguments.get("session_id"):
                    payload["session_id"] = arguments["session_id"]
                data = _call("POST", "/tmt/consolidate/session", json=payload)

            elif level == "daily":
                if arguments.get("date"):
                    payload["date"] = arguments["date"]
                data = _call("POST", "/tmt/consolidate/daily", json=payload)

            elif level == "weekly":
                if arguments.get("date"):
                    payload["week_start"] = arguments["date"]
                data = _call("POST", "/tmt/consolidate/weekly", json=payload)

            elif level == "monthly":
                if arguments.get("date"):
                    try:
                        parts = arguments["date"].split("-")
                        payload["year"] = int(parts[0])
                        if len(parts) > 1:
                            payload["month"] = int(parts[1])
                    except (ValueError, IndexError):
                        pass
                data = _call("POST", "/tmt/consolidate/monthly", json=payload)

            else:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown consolidation level: {level}. Use: session|daily|weekly|monthly"}),
                )]

            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        # ── tmt_tree: browse TMT structure ──────────────
        elif name == "tmt_tree":
            data = _call("GET", f"/tmt/tree/{user_id}")
            return [types.TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]

        # ── tmt_profile: get user profile overview ──────
        elif name == "tmt_profile":
            result = {}

            # Get recent memory count from L1 memories list
            mems = _call("GET", "/memories/", params={"user_id": user_id, "limit": 1})
            total_count = 0
            if isinstance(mems, list):
                total_count = len(mems)
            elif isinstance(mems, dict) and "error" not in mems:
                total_count = mems.get("total", 0) if "total" in mems else (mems.get("count", 0) if "count" in mems else (len(mems.get("items", [])) if "items" in mems else 0))
            result["recent_memories"] = total_count

            # Get TMT tree overview for level counts
            tree = _call("GET", f"/tmt/tree/{user_id}")
            if isinstance(tree, dict) and "error" not in tree:
                result["tree"] = tree
                # Count nodes per level
                levels = {}
                for key in tree:
                    if key.startswith("L") and len(key) == 2 and key[1].isdigit():
                        val = tree[key]
                        levels[key] = len(val) if isinstance(val, list) else (1 if val else 0)
                if levels:
                    result["levels"] = levels
            else:
                result["tree"] = tree

            return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

        else:
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ── Startup ───────────────────────────────────────────────
async def main():
    async with mcp_server.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
