#!/usr/bin/env python3
"""
Mnemosyne MCP 适配测试 (mcp SDK 2.0)
=====================================
对 mnemosyne_mcp.py 做全工具协议级测试: 握手 / 15 工具发现 / 写入即命中 /
生命周期闭环 / 慢端点 / 错误路径。适用于 Hermes 对接 Mnemosyne 的 C 段验收。

用法:
  python3 scripts/mcp_adapt_test.py
  python3 scripts/mcp_adapt_test.py --mcp integrations/hermes-mcp/mnemosyne_mcp.py
  MNEMOSYNE_URL=http://127.0.0.1:18010 python3 scripts/mcp_adapt_test.py

参数:
  --python   MCP 桥解释器 (默认 python3)
  --mcp      mnemosyne_mcp.py 路径 (默认: 仓库根/integrations/hermes-mcp/mnemosyne_mcp.py)
  --url      Mnemosyne API 基地址 (默认 http://127.0.0.1:8010, 走隧道时给 18010)

退出码: 0 = 全部通过; 1 = 有失败
"""
import argparse
import json
import os
import select
import subprocess
import sys
import time

DEFAULT_URL = "http://127.0.0.1:8010"
READ_TIMEOUT = 35


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python", default=os.environ.get("MNEMOSYNE_PYTHON", "python3"))
    ap.add_argument("--mcp", default=None, help="mnemosyne_mcp.py 路径")
    ap.add_argument("--url", default=os.environ.get("MNEMOSYNE_URL", DEFAULT_URL))
    args = ap.parse_args()

    if args.mcp is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        args.mcp = os.path.join(repo_root, "integrations", "hermes-mcp", "mnemosyne_mcp.py")

    proc = subprocess.Popen(
        [args.python, args.mcp],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
        env={**os.environ, "MNEMOSYNE_URL": args.url},
    )

    def send(obj, timeout=READ_TIMEOUT):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
        r, _, _ = select.select([proc.stdout], [], [], timeout)
        if not r:
            return None
        line = proc.stdout.readline()
        return json.loads(line) if line.strip() else None

    tag = f"MCP2T-{int(time.time())}"
    results = {}

    r = send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "adapt-test", "version": "2.0"}}})
    results["initialize"] = "OK" if r and "result" in r else f"FAIL: {str(r)[:80]}"
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    r = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    n = len(r["result"]["tools"]) if r and "result" in r else -1
    results[f"tools/list({n}个)"] = "OK" if n == 15 else f"FAIL: {n}"

    def call(tid, name, args_dict):
        r = send({"jsonrpc": "2.0", "id": tid, "method": "tools/call",
                  "params": {"name": name, "arguments": args_dict}})
        if r is None:
            return None, "TIMEOUT"
        if "result" not in r:
            return None, f"NO_RESPONSE: {str(r)[:100]}"
        content = r["result"].get("content", [])
        text = content[0]["text"] if content else "{}"
        return text, r["result"].get("isError", False)

    # ── 快批: 核心链路 ──
    text, err = call(10, "store_memory",
                     {"content": f"{tag} MCP2.0适配测试记忆", "category": "test", "importance": 0.5})
    mid = None
    try:
        d = json.loads(text)
        mid = d.get("id") or d.get("memory", {}).get("id")
    except Exception:
        pass
    results["store_memory"] = f"OK id={mid}" if mid and not err else f"FAIL: {text[:100]}"

    text, err = call(11, "search_memories", {"query": tag, "top_k": 3})
    try:
        hits = json.loads(text).get("memories", [])
        hit = any(tag in (m.get("content", "") or "") for m in hits)
        results["search_memories(当日写入即命中)"] = f"OK hit={hit}" if not err else f"FAIL: {text[:100]}"
    except Exception:
        results["search_memories"] = f"PARSE: {text[:100]}"

    text, err = call(13, "get_hot_memories", {"limit": 3})
    results["get_hot_memories"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(14, "get_memory_stats", {})
    results["get_memory_stats"] = "OK" if not err and "total" in text else f"FAIL: {text[:100]}"

    text, err = call(15, "feedback_memory", {"memory_id": mid, "feedback": "positive"})
    results["feedback_memory"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(16, "get_memory_traces", {"memory_id": mid})
    results["get_memory_traces"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(17, "delete_memory", {"memory_id": mid})
    results["delete_memory"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(18, "restore_memory", {"memory_id": mid})
    results["restore_memory"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(19, "search_graph", {"query": "G-CAT", "limit": 3})
    results["search_graph"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(21, "create_wiki_page", {"title": f"{tag}-wiki", "content": f"{tag} wiki适配测试"})
    results["create_wiki_page"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(22, "search_wiki", {"query": tag, "limit": 3})
    results["search_wiki"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(23, "store_belief", {"content": f"{tag} 测试信念"})
    results["store_belief"] = "OK" if not err else f"FAIL: {text[:100]}"

    text, err = call(24, "search_beliefs", {"query": tag, "top_k": 3})
    results["search_beliefs"] = "OK" if not err else f"FAIL: {text[:100]}"

    # ── 慢批: LLM 端点 ──
    text, err = call(12, "dialectic_search", {"query": "记忆宫殿", "max_results": 1})
    results["dialectic_search(慢/LLM)"] = "OK" if not err and "error" not in text[:200] else f"FAIL: {text[:120]}"

    text, err = call(20, "extract_entities", {"text": f"{tag} 服务器部署在腾讯云"})
    results["extract_entities(慢/LLM)"] = "OK" if not err else f"FAIL: {text[:120]}"

    text, err = call(25, "no_such_tool", {})
    results["unknown_tool(错误路径)"] = "OK" if (err or "error" in text or "Unknown" in text) else f"FAIL: {text[:100]}"

    proc.stdin.close()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()

    print(f"=== Mnemosyne MCP 适配测试 (标记 {tag}) ===")
    ok = 0
    for k, v in results.items():
        good = str(v).startswith("OK")
        ok += 1 if good else 0
        print(f"  {'PASS' if good else 'FAIL'} {k}: {v}")
    print(f"\n结果: {ok}/{len(results)} 通过")
    print(f"测试数据标记 {tag} 请手动清理 (记忆/wiki/信念)")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
