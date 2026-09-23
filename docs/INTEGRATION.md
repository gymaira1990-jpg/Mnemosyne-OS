# 对接指南（3 种方式）

> 从 `AGENTS.md` 下沉。任何框架 5 分钟对接。
> 返回 [AGENTS.md](../AGENTS.md)

## 快速对接（3 种方式）

### 方式 1：REST API（任何框架通用）

```bash
# 健康检查
curl http://127.0.0.1:8010/api/v1/echo

# 存记忆
curl -X POST http://127.0.0.1:8010/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","content":"要记住的知识","category":"knowledge"}'

# 搜记忆（五维修：向量+BM25+时间+信任+热度）
curl -X POST http://127.0.0.1:8010/api/v1/memories/search \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","query":"关键词","top_k":5}'

# 三通道召唤（宫殿核心）
curl "http://127.0.0.1:8010/api/v1/palace/summon?q=关键词&user_id=default&top_k=5"
```

### 方式 2：Python SDK

```python
from integrations.sdk import MnemosyneHermesMemory

m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:8010")
m.add("知识内容", category="knowledge")
results = m.get_relevant("查询")
m.search_by_hall("archive")       # 已验证知识
m.search_by_hall("engineering")   # 踩坑记录
```

### 方式 3：Hermes Agent（原生 Memory Provider）

```bash
hermes config set memory.provider mnemosyne
# 自动获得 11 个工具：
#   mnemosyne_palace_summon · mnemosyne_search · mnemosyne_recall
#   mnemosyne_remember     · mnemosyne_dialectic · mnemosyne_hot_memories
#   mnemosyne_wiki         · mnemosyne_tree      · mnemosyne_media
#   mnemosyne_tiered_read  · mnemosyne_conflicts
```

---

---

## 与 Hermes 集成（Memory Provider）

### 配置

```yaml
# ~/.hermes/config.yaml
memory:
  provider: mnemosyne
  config:
    endpoint: "http://127.0.0.1:18010"   # 或远程 via SSH 隧道
```

### SSH 隧道（远程部署）

```bash
ssh -L 18010:127.0.0.1:8010 your-server
# Hermes 的 mnemosyne 工具自动经 127.0.0.1:18010 访问
```

### MCP 桥接（可选，标准 MCP 协议）

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  mnemosyne:
    command: "python3"
    args: ["/path/to/mnemosyne_mcp.py"]
    enabled: true
```

> MCP server 源码: `integrations/hermes-mcp/mnemosyne_mcp.py`

### 自动钩子（Memory Provider 内置）

| 钩子 | 触发时机 | 作用 |
|------|---------|------|
| `sync_turn` | 每轮对话 | 记忆同步 |
| `on_session_end` | 会话结束 | 蒸馏 + 事实提取 |
| `on_turn_start` | 新轮次 | 预取相关记忆注入 |
| `on_pre_compress` | 压缩前 | 归档防丢 |
| `on_delegation` | 子任务 | 记录子任务记忆 |
| `on_memory_write` | 写记忆 | 镜像到 Mnemosyne |

---
