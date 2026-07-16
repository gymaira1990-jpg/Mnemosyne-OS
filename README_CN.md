[English](README.md) | 中文版

# 🏛️ Mnemosyne OS — 认知型记忆操作系统

**给 AI Agent 用的长期记忆系统。不是向量数据库，不是 RAG 管道。是会自己整理、提炼、老化的记忆 OS。**

<p align="center">
  <img src="https://img.shields.io/badge/version-5.3.2-brightgreen" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license">
  <img src="https://img.shields.io/badge/python-3.12+-blue" alt="python">
  <img src="https://img.shields.io/badge/DB-PostgreSQL%2016%20%2B%20pgvector-336791" alt="postgres">
  <img src="https://img.shields.io/badge/graph-Apache%20AGE-forestgreen" alt="graph">
  <img src="https://img.shields.io/badge/agent-Hermes%20native-8A2BE2" alt="hermes">
</p>

---

## 它解决了什么

每个 AI Agent 都健忘：会话一关全忘光，上下文窗口溢出，重要决策消失在滚动条里。现有方案（向量数据库 + RAG + prompt 拼接）都是打补丁——能存数据，但不懂"什么重要、什么该忘"。

Mnemosyne OS 把记忆当作一等公民：**捕获 → 蒸馏 → 老化 → 遗忘 → 浮现**。你的 Agent 记的不是碎片，是有生命周期的知识。7×24 跑在你自己的服务器上。

---

## 怎么工作的

每次对话结束，系统自动触发蒸馏管道：

```
原始消息
  │
  ▼ conversation_messages (PostgreSQL, 永久存储)
  │
  ▼ L1: 记忆碎片 (提取 + 1024维向量化)
  │
  ├── L2: 会话摘要 (LLM 蒸馏，提取关键决策)
  │
  ├── L3: 日报 (跨会话主题提炼)
  │
  ├── L4: 周报 (重复模式识别)
  │
  └── L5: 用户画像 (稳定偏好与身份特征)
```

每层都是 **LLM 自动生成的**，不是模板填空。同一个管道也处理 Agent 委托事件、记忆写入和上下文压缩。

---

## 核心能力

### 五维搜索

不只是余弦相似度。每次查询五维打分：

```
评分 = 0.40 × 语义向量 (1024d HNSW pgvector)
     + 0.15 × BM25 全文关键词
     + 0.15 × 时间新鲜度 (7天内0.15, 30天内0.08)
     + 0.15 × 可信度 (矛盾检测评分)
     + 0.15 × 热度 (访问频率 × 衰减曲线)
```

**纯时间排序模式** (`sort=created_at`) 跳过混合公式——适合"昨天聊了啥"类查询。时间轴（最近）和热度轴（重要）不再混淆。

```bash
# 混合搜索：语义理解
curl -X POST :8010/api/v1/memories/search \
  -d '{"user_id":"default","query":"PostgreSQL 优化","top_k":5}'

# 时间排序：查最近动态
curl "http://:8010/api/v1/memories?user_id=default&sort=created_at&limit=20&search=部署"
```

### 三馆闭环

知识有生命周期：

```
研究馆 → "我们在试这个方案"
  │ (验证通过)
工程馆 → "这个方案可行，坑在这里"
  │ (实战打磨)
档案馆 → "这是经过验证的真理"
```

每条记忆带 `valid_from` / `valid_to` 时间戳。矛盾检测自动标记过时知识。东西不会腐烂——它会优雅老化。

### 知识图谱

实体（项目、人物、概念、工具）通过 LLM + 正则提取，存入 Apache AGE 图：

```cypher
MATCH (m:Memory)-[:MENTIONS]->(e:Entity {name: "pgvector"})
RETURN m.content, e.name
```

多跳遍历意味着问"PostgreSQL 迁移那阵子还聊了什么"，返回的是上下文，不是关键词匹配。

### 会话永久记忆

Hermes `state.db` (SQLite) 在每次会话结束时同步到 PostgreSQL `conversation_messages`。完整的对话交换——用户、助手、工具调用、推理过程——全部保留时间戳。

```bash
# 列出所有会话
curl "http://:8010/api/v1/sessions?limit=20"

# 像聊天软件一样加载对话
curl "http://:8010/api/v1/sessions/{session_id}/messages?limit=200"

# 支持分页
curl "http://:8010/api/v1/sessions/{session_id}/messages?before_id=500"
```

意外崩溃？`/new` 按早了？消息已经持久化在 PostgreSQL 里了。前端加载就像微信打开昨天的聊天。

### Agent 原生集成

**MCP Bridge** — 15 个工具直接暴露给 Hermes Agent：

```
mnemosyne_search       — 五维混合检索
mnemosyne_recall       — 深度辨证推理（附带上下文）
mnemosyne_hot_memories — 热度排行
mnemosyne_remember     — 存储（自动矛盾检测）
session_search         — 时间轴会话浏览
mnemosyne_dialectic    — 知识图谱多跳检索
mnemosyne_wiki         — 版本化知识库
mnemosyne_media        — 多模态记忆（文件/图片/链接）
```

**Memory Provider** — 10 个生命周期 Hook，自动触发：

```
on_session_end    → 同步消息 + 触发 L2 蒸馏
on_turn_start     → 每轮对话前预取相关记忆
on_pre_compress   → 上下文压缩前注入关键记忆
on_delegation     → 记录子任务与结果
on_memory_write   → 镜像 Hermes 记忆写入
on_session_switch → 会话切换时刷写队列
```

不需要手动调 `remember()`。系统自己在看、在记、在蒸馏。

### 端云双活

WSL 断网？消息缓存到本地 SQLite。恢复后静默推回云端 PostgreSQL。7 条 cron 任务保证一切正常：热度衰减、重复清理、实体提取、TMT 蒸馏、智能切块、离线同步。

---

## 快速开始

```bash
# Hermes Agent 用户（一条命令）
hermes mcp add mnemosyne --command python3 \
  --args integrations/hermes-mcp/mnemosyne_mcp.py

# 独立部署
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
pip install -r requirements.txt
python main.py  # → :8010
```

---

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 数据库 | PostgreSQL 16 + pgvector (1024d HNSW) | 记忆 + 向量存储 |
| 图 | Apache AGE (Cypher) | 知识图谱 |
| API | FastAPI + asyncpg | 38+ REST 端点 |
| 搜索 | 向量 + BM25 + ILIKE + 时间 + 热度 | 五维混合排序 |
| 蒸馏 | LLM (豆包 Seed-2.0 / DeepSeek V4) | L1→L5 TMT 管道 |
| 同步 | SQLite ↔ PostgreSQL | 端云双活 |
| Agent | Hermes MCP (15工具) + Memory Provider (10 Hook) | Agent 原生记忆 |

---

## 规模

单用户 + 5 Agent 分身，7×24 稳定运行：

| 指标 | 数值 |
|------|------|
| 存储记忆 | 1,921+ 条 |
| L2 会话摘要 | 1,810 条 |
| L3 日报 | 111 条 |
| 搜索延迟 | ~200ms (五维混合) |
| 向量化 | 1024d 豆包 Embedding-Vision |
| 模型 | 豆包 Seed-2.0 Lite / DeepSeek V4 |

---

## 版本

| 版本 | 日期 | 发布内容 |
|------|------|---------|
| [v5.3.2](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.2) | 2026-07-16 | 会话消息同步，conversation_messages 表，3 个 API 端点 |
| [v5.3.1](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.1) | 2026-07-16 | 时间排序检索，双轴协议，`sort=created_at` |
| [v5.3.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.0) | 2026-07-06 | 仓库治理，Hermes 10-Hook Provider，MCP 15 工具 |
| v5.2.3 | 2026-07-06 | 宕机告警，MCP 重连，L3 蒸馏强化 |
| v5.2.2 | 2026-06-27 | 全模块豆包化，零本地模型依赖 |
| v5.0.0 | 2026-06-24 | 首次 7×24 独立部署 |

[完整更新日志 →](CHANGELOG.md)

---

## 文档

| 文档 | 受众 |
|------|------|
| [AGENTS.md](AGENTS.md) | 进入本仓库的 AI Agent — 架构/流程/红线 |
| [ROADMAP.md](ROADMAP.md) | 当前 → 下一步 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史 |
| [docs/WHITEPAPER_FULL.md](docs/WHITEPAPER_FULL.md) | 学术论文 — 架构/安全/认知设计 |
| [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) | 开发规范 |
| [.github/SECURITY.md](.github/SECURITY.md) | 漏洞报告 |

<p align="center">
  <i>「记忆不是用来存的，是用来活的。」</i><br>
  🐾 G-CAT & Hermes Agent · MIT · 2026
</p>
