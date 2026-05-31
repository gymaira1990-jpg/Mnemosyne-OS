# MCP 桥接文件

Hermes Agent ↔ Mnemosyne 记忆引擎的 MCP 工具桥接。

## 文件路径

| 文件 | 路径 | 说明 |
|------|------|------|
| `mnemosyne_mcp.py` | `/home/g-cat/.hermes/hermes-agent/tools/mnemosyne_mcp.py` | 14 个记忆工具 |
| `tmt_mcp.py` | `/home/g-cat/.hermes/hermes-agent/tools/tmt_mcp.py` | 5 个 TMT 工具 |

## Hermes config.yaml 配置

```yaml
mcp_servers:
  mnemosyne:
    command: "python3"
    args: ["/home/g-cat/.hermes/hermes-agent/tools/mnemosyne_mcp.py"]
  tmt:
    command: python3
    args:
      - /home/g-cat/.hermes/hermes-agent/tools/tmt_mcp.py
  prompt-optimizer:
    url: "http://127.0.0.1:3333/mcp"
    tools:
      resources: false
      prompts: false
```

## 工具清单

### mnemosyne_mcp (14 工具)
- `store_memory` / `search_memories` / `get_hot_memories`
- `get_memory_stats` / `feedback_memory` / `get_memory_traces`
- `delete_memory` / `restore_memory` / `search_graph`
- `extract_entities` / `create_wiki_page` / `search_wiki`
- `store_belief` / `search_beliefs`

### tmt_mcp (5 工具)
- `tmt_recall` — 3阶段智能召回
- `tmt_store` — 存记忆+可选蒸馏
- `tmt_consolidate` — 手动触发蒸馏
- `tmt_tree` — 浏览记忆树
- `tmt_profile` — 聚合画像
