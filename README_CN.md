<p align="center">
  <img src="https://img.shields.io/badge/version-5.3.2-brightgreen?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/DB-PostgreSQL%2016%20%2B%20pgvector-336791?style=flat-square" alt="postgres">
  <img src="https://img.shields.io/badge/graph-Apache%20AGE-forestgreen?style=flat-square" alt="graph">
  <img src="https://img.shields.io/badge/agent-Hermes%20native-8A2BE2?style=flat-square" alt="hermes">
</p>

<h1 align="center">🏛️ Mnemosyne OS</h1>
<h3 align="center">认知型记忆操作系统 · 给 AI Agent 的长期记忆</h3>

<p align="center">
  <i>不是向量数据库，不是 RAG 管道。<br>
  是会自己整理、提炼、老化的记忆 OS——跨会话、跨天数、跨项目。</i>
</p>

<p align="center">
  <a href="#它解决了什么">为什么</a> ·
  <a href="#怎么工作的">怎么工作</a> ·
  <a href="#核心能力">核心能力</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#技术栈">技术栈</a> ·
  <a href="#版本">版本</a> ·
  <a href="README.md">English</a>
</p>

---

| | |
|---|---|
| **记忆** | 1,921 条存储 · 1,810 条会话摘要 · 111 条日报 |
| **搜索** | 五维混合（语义+BM25+时间+信任+热度）· ~200ms |
| **技术** | PostgreSQL 16 · pgvector 1024d HNSW · Apache AGE · FastAPI |
| **Agent** | Hermes MCP（15工具）· Memory Provider（10生命周期Hook） |
| **运行** | 7×24 云端 · 端云双活（SQLite ↔ PG） |

---

## 它解决了什么

每个 AI Agent 都健忘：会话一关全忘光，上下文窗口溢出，重要决策消失在滚动条里。现有方案——向量数据库检索、RAG 注入、prompt 拼接——都是打补丁。能存数据，但不懂**什么重要、什么该忘**。

Mnemosyne OS 把记忆当作一等公民：**捕获 → 蒸馏 → 老化 → 遗忘 → 浮现**。专为需要跨周记忆的 Agent 设计，跑在你自己的服务器上。

---

## 怎么工作的

每次对话结束，系统自动触发蒸馏管道：

```
原始消息
     │
     ▼  conversation_messages (PostgreSQL, 永久存档)
     │
     ▼  L1: 记忆碎片 (提取 + 1024维向量化)
     │
     ├── L2: 会话摘要 (LLM 蒸馏，提取关键决策)
     │
     ├── L3: 日报 (跨会话主题提炼)
     │
     ├── L4: 周报 (重复模式识别)
     │
     └── L5: 用户画像 (稳定偏好与身份特征)
```

每层都是 **LLM 自动生成**，不是模板填空。同一个管道处理 Agent 委托事件、记忆写入和上下文压缩。

---

## 核心能力

| 能力 | Mnemosyne | Chroma/Pinecone | Mem0 |
|---|---|---|---|
| 向量搜索 (1024d HNSW) | ✅ | ✅ | ✅ |
| 全文搜索 (BM25 + ILIKE) | ✅ | ❌ | ❌ |
| 时间衰减评分 | ✅ 7/30/90天分层 | ❌ | ❌ |
| 自动蒸馏 (L1→L5) | ✅ LLM管道 | ❌ | ❌ |
| 知识图谱 (Cypher) | ✅ Apache AGE | ❌ | ❌ |
| 会话历史 | ✅ state.db→PG同步 | ❌ | ❌ |
| 端云同步 | ✅ SQLite↔PG | ❌ | ❌ |
| Agent原生Hook | ✅ 10个生命周期 | ❌ | 有限 |

### 🧠 五维搜索

每次查询五维独立打分不混淆：

```
评分 = 0.40 × 语义向量   (1024d HNSW pgvector)
     + 0.15 × BM25全文   (关键词匹配)
     + 0.15 × 时间新鲜度 (7天内0.15, 30天内0.08)
     + 0.15 × 可信度     (矛盾检测评分)
     + 0.15 × 热度       (访问频率 × 衰减曲线)
```

**纯时间排序** (`sort=created_at`) 跳过混合公式——适合"昨天聊了什么"类查询。热度轴和时间轴不再混淆。

```bash
curl -X POST :8010/api/v1/memories/search \
  -d '{"user_id":"default","query":"PostgreSQL 优化","top_k":5}'

curl "http://:8010/api/v1/memories?user_id=default&sort=created_at&limit=20&search=部署"
```

### 🏛️ 三馆闭环

知识有生命周期，通过闸机流转：

```
研究馆 → "我们在试这个方案"
  │  (验证通过)
工程馆 → "方案可行，坑在这里"
  │  (实战打磨)
档案馆 → "经过验证的真理"
```

每条记忆带 `valid_from` / `valid_to` 时间戳。矛盾检测自动标记过时知识。

### 🔗 知识图谱

实体（项目、人物、概念、工具）LLM+正则提取，Apache AGE 图存储：

```cypher
MATCH (m:Memory)-[:MENTIONS]->(e:Entity {name: "pgvector"})
RETURN m.content, e.name
```

多跳遍历——问"PostgreSQL 迁移那阵子还聊了什么"，返回的是关系上下文，不是关键词匹配。

### 💬 会话永久记忆

Hermes `state.db` (SQLite) 在每次会话结束时同步到 PostgreSQL `conversation_messages`。完整对话交换——用户、助手、工具调用、推理——全部保留时间戳。

```bash
curl "http://:8010/api/v1/sessions?limit=20"               # 会话列表
curl "http://:8010/api/v1/sessions/{id}/messages?limit=200"  # 聊天历史
curl "http://:8010/api/v1/sessions/{id}/messages?before_id=500"  # 分页
```

崩溃？`/new` 按早了？消息已在 PostgreSQL。前端加载就像微信打开昨天聊天。

### 🔌 Agent 原生集成

**MCP Bridge**（15工具）—— Hermes Agent 零配置接入：

```
mnemosyne_search        · mnemosyne_recall       · mnemosyne_hot_memories
mnemosyne_remember      · mnemosyne_dialectic    · mnemosyne_wiki
mnemosyne_media         · session_search         · mnemosyne_tree
```

**Memory Provider**（10 Hook）—— 全自动，无需手动 `remember()`：

```
on_session_end   → 同步 + L2蒸馏        on_turn_start    → 预取
on_pre_compress  → 压缩前注入            on_delegation    → 记录子任务
on_memory_write  → 镜像写入              on_session_switch → 刷写队列
```

### ☁️ 端云双活

WSL 断网？本地 SQLite 缓存。恢复后静默推回 PostgreSQL。7条 cron 任务维护：热度衰减、去重、实体提取、TMT 蒸馏、智能切块、离线同步。

---

## 快速开始

```bash
# Hermes Agent（一条命令）
hermes mcp add mnemosyne --command python3 \
  --args integrations/hermes-mcp/mnemosyne_mcp.py

# 独立部署
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
cd Mnemosyne-OS && pip install -r requirements.txt
python main.py  # → :8010
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 数据库 | PostgreSQL 16 + pgvector 1024d (HNSW) |
| 图 | Apache AGE (Cypher) |
| API | FastAPI + asyncpg · 38+ REST 端点 |
| 搜索 | 向量 + BM25 + ILIKE + 时间 + 热度 |
| 蒸馏 | 豆包 Seed-2.0 / DeepSeek V4 |
| 同步 | SQLite ↔ PostgreSQL |
| Agent | MCP 15工具 + Memory Provider 10 Hook |

---

## 规模

单用户 + 5 Agent 分身，7×24 稳定运行：

| 指标 | 数值 |
|---|---|
| 存储记忆 | 1,921+ 条 |
| 会话摘要 | 1,810 条 |
| 日报 | 111 条 |
| 搜索延迟 | ~200ms |
| 向量化 | 1024d 豆包 Embedding-Vision |

---

## 版本

| 版本 | 日期 | 发布内容 |
|---|---|---|
| [v5.3.2](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.2) | 2026-07-16 | 会话同步 · conversation_messages · 3端点 |
| [v5.3.1](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.1) | 2026-07-16 | 时间排序 · 双轴协议 · `sort=created_at` |
| [v5.3.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.0) | 2026-07-06 | 仓库治理 · 10-Hook Provider · 15-Tool MCP |
| v5.2.3 | 2026-07-06 | 宕机告警 · MCP重连 · L3蒸馏 |
| v5.2.2 | 2026-06-27 | 全模块豆包化 · 零本地模型 |
| v5.0.0 | 2026-06-24 | 首次 7×24 部署 |

[完整更新日志 →](CHANGELOG.md)

---

## 文档

| | |
|---|---|
| [AGENTS.md](AGENTS.md) | AI Agent 手册 — 架构/流程/红线 |
| [ROADMAP.md](ROADMAP.md) | 当前 → 下一步 |
| [CHANGELOG.md](CHANGELOG.md) | 完整版本历史 |
| [docs/WHITEPAPER_FULL.md](docs/WHITEPAPER_FULL.md) | 学术论文 — 架构/安全/认知设计 |

<p align="center">
  <i>「记忆不是用来存的，是用来活的。」</i><br><br>
  🐾 <b>G-CAT</b> & <b>Hermes Agent</b> · MIT · 2026
</p>
