# Mnemosyne Memory Provider

> 让 **Hermes Agent** 拥有 Mnemosyne OS 记忆宫殿的官方 Memory Provider。
> 版本: v7.6.2 | 适配: Hermes Agent (ABC MemoryProvider 协议)

---

## 这是什么

Hermes Agent 的长期记忆插件。启用后，你的 Agent 自动获得：

- 🪄 **11 个记忆工具**（含三通道召唤 `mnemosyne_palace_summon`）
- 🔄 **自动钩子**：每轮对话同步、会话结束蒸馏、压缩前归档、子任务记录
- 🧠 **热度管理**：重要记忆升温，噪音衰减
- 🏰 **宫殿组织**：分类树 + 档号 + 著录卡片

对标：Mem0 / Zep / Honcho。差异点：宫殿式组织 + 11 工具 + 崩溃安全写队列 + 熔断保护。

---

## 快速启用

```bash
# 1. 前提：Mnemosyne OS 服务已运行（见仓库 INSTALL.md）
#    本地: http://127.0.0.1:8010  |  远程: SSH 隧道映射到 18010

# 2. 配置 Hermes 使用 mnemosyne provider
hermes config set memory.provider mnemosyne

# 3. 可选：指定服务地址（默认 http://127.0.0.1:18010）
#    在 profile 的 .env 中：
echo "MNEMOSYNE_ENDPOINT=http://127.0.0.1:8010" >> ~/.hermes/.env
echo "MNEMOSYNE_USER_ID=default" >> ~/.hermes/.env

# 4. 重启 Hermes（或 /reset），工具自动出现
```

---

## 配置项

| 环境变量 | 默认 | 说明 |
|---------|------|------|
| `MNEMOSYNE_ENDPOINT` | `http://127.0.0.1:18010` | Mnemosyne API 地址 |
| `MNEMOSYNE_USER_ID` | `default` | 用户 ID（多用户隔离用） |
| `MNEMOSYNE_API_KEY` | 无 | 若服务有鉴权（X-API-Key 头） |

---

## 11 个工具

| 工具 | 作用 |
|------|------|
| `mnemosyne_palace_summon` | 🏰 三通道召唤（点名/引导/共鸣）— 魔法前台 |
| `mnemosyne_search` | 四维搜索（语义+关键词+热度+图谱） |
| `mnemosyne_recall` | 智能召回（跨层级 L1→L3） |
| `mnemosyne_remember` | 主动存储记忆 |
| `mnemosyne_dialectic` | 辨证检索（带会话上下文） |
| `mnemosyne_hot_memories` | 当前热点记忆 |
| `mnemosyne_tree` | 记忆树浏览（TMT 层级） |
| `mnemosyne_tiered_read` | 三级读取（L5/L3/L1） |
| `mnemosyne_conflicts` | 矛盾检测列表 |
| `mnemosyne_wiki` | 知识库检索 |
| `mnemosyne_media` | 媒体记忆 |

---

## 自动钩子（ABC 协议）

| Hook | 触发 | 行为 |
|------|------|------|
| `sync_turn` | 每轮对话 | 当前轮记忆写入（写队列） |
| `on_session_end` | 会话结束 | TMT L2 蒸馏 + 事实提取 |
| `on_turn_start` | 新轮次 | 预取相关记忆注入 context |
| `on_pre_compress` | 上下文压缩前 | 归档关键洞察，防丢失 |
| `on_delegation` | 子任务完成 | 任务+结果入宫 |
| `on_memory_write` | 内置记忆写入 | 镜像到 Mnemosyne |
| `on_session_switch` | 切会话 | 刷新写队列 |

> 崩溃安全写队列 + 熔断保护：业界独有，即使 Mnemosyne 短暂不可用也不丢记忆。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `__init__.py` | Provider 主体（ABC 协议实现 + 11 工具） |
| `write_queue.py` | 崩溃安全写队列 + 熔断器 |
| `message_cleaner.py` | 消息清洗（去重/截断/敏感过滤） |
| `VERSION.md` | 版本历史 |
| `CHANGELOG.md` | 变更日志 |

> MCP 桥接（标准 MCP 协议）：见 `../hermes-mcp/mnemosyne_mcp.py`，适用于非 Hermes 框架。

---

## 兼容性说明

- 需要 Mnemosyne OS 服务 v5.3.0+（推荐 v7.x）
- 依赖 Hermes 的 `agent.memory_provider.MemoryProvider` 基类
- 无本地模型依赖：所有 LLM/Embedding 调用走 Mnemosyne 服务

---

*Mnemosyne OS · 记忆不是用来存的，是用来活的。*
