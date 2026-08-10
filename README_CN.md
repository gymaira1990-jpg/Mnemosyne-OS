<p align="center">
  <img src="https://img.shields.io/badge/version-7.5.0-brightgreen?style=flat-square" alt="version">
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
| **记忆** | 8,647 条归档 · 6,231 条结构化事实 · 归档率 100% |
| **搜索** | 🏰 三通道召唤（点名/引导/共鸣）· ~100-400ms |
| **宫殿** | 分类树 7翼×20房 · 档号体系 · 著录卡片 · 永恒分级 |
| **技术** | PostgreSQL 16 · pgvector 1024d HNSW · Apache AGE · FastAPI |
| **Agent** | Hermes Memory Provider（11工具含 palace_summon）· 自动提取 |
| **运行** | 7×24 云端 · 端云双活（SQLite ↔ PG） |

---

## 它解决了什么

每个 AI Agent 都健忘：会话一关全忘光，上下文窗口溢出，重要决策消失在滚动条里。现有方案——向量数据库检索、RAG 注入、prompt 拼接——都是打补丁。能存数据，但不懂**什么重要、什么该忘**。

Mnemosyne OS 把记忆当作一等公民：**捕获 → 蒸馏 → 老化 → 遗忘 → 浮现**。专为需要跨周记忆的 Agent 设计，跑在你自己的服务器上。

---

## 怎么工作的

每次对话结束，系统自动触发蒸馏管道：

```
对话自动流经宫殿管道：

```
对话 (Hermes)
     │
     ▼  state.db (无损原始记录, Hermes 原生)
     │
     ▼  sync_turn → session 记忆 (2000/3000字符, 接近无损)
     │
     ▼  🕵️ 资料室: 事实提取 (DeepSeek) → 结构化 facts
     │
     ▼  🏛️ 档案馆: 分类 (7翼×20房) → 档号 → 著录卡片
     │
     ▼  📚 图书馆: 三通道召唤 (点名 / 引导 / 共鸣)
     │
     └  🍵 中药柜: 高频 facts 保持热度
```

每一步都是 **LLM 驱动**，不是模板填空。同一个管道处理 Agent 委托事件、记忆写入和上下文压缩。

---

## 核心能力

| 能力 | Mnemosyne | Chroma/Pinecone | Mem0 |
|---|---|---|---|
| 向量搜索 (1024d HNSW) | ✅ | ✅ | ✅ |
| 全文搜索 (BM25 + ILIKE) | ✅ | ❌ | ❌ |
| 时间衰减评分 | ✅ 7/30/90天分层 | ❌ | ❌ |
| 事实提取 (对话→facts) | ✅ LLM管道 | ❌ | ✅ |
| 知识图谱 (Cypher) | ✅ Apache AGE | ❌ | ❌ |
| 会话历史 | ✅ state.db→PG同步 | ❌ | ❌ |
| 端云同步 | ✅ SQLite↔PG | ❌ | ❌ |
| Agent原生Hook | ✅ 11个工具 | ❌ | 有限 |

### 🏰 魔法记忆宫殿

记忆像真实宫殿一样组织——灵感来自图书馆分类（杜威十进）、档案著录（DA/T18）、中药柜斗谱（位置即药）。这些体系在没有电脑的年代服务人类几百年，Mnemosyne 把它们带给 AI。

```
大厅 LOBBY   → 高频记忆（常驻注入，抬手取）
翼   WING    → K知识 · N网络 · D开发 · O运维 · A资产 · P人物 · I灵感
房间 ROOM    → 20 中类（proxy / deploy / secret / model / …）
书架 SHELF   → 小类 / 主题
书卷 TOME    → 单条知识：著录卡片 + 档号 + 全文指针
地下档案馆    → 原始对话全保真（Hermes state.db）
```

每条记忆获得**档号**——`K·NET·PROXY·2026-0007`——「编号即位置」，像图书馆索书号。不再把一切倒进扁平向量堆。

### 🪄 三通道召唤

知识招手就来——三通道各司其职：

| 通道 | 机制 | 延迟 |
|---|---|---|
| ① **点名**（精确） | 档号/题名/标签直命中 | <100ms |
| ② **引导**（范围） | 分类树翼/房逐层缩小 | ~200ms |
| ③ **共鸣**（模糊） | 向量检索（pgvector HNSW） | ~300ms |

```bash
# 一次调用同时走三通道
curl "http://:8010/api/v1/palace/summon?q=xray&user_id=default&top_k=5"
```

### 🕵️ 三室分工

| 室 | 职责 | 实现 |
|---|---|---|
| 🕵️ 资料室 | 对话 → 结构化 facts | `/palace/extract` |
| 🏛️ 档案馆 | 分类 + 著录 | `tome_cards` + 档号 |
| 📚 图书馆 | 检索召唤 | `/palace/summon` |
| 🍵 中药柜 | 高频快速取用 | 分类引导 + 档号点名 |

对话碎片（存储占比 88% → 27%）变成 **6,231 条结构化 facts**——可检索、可分类、可引用的知识，不再是对话噪音。

### ⏳ 永恒分级

不是所有记忆都活到永远。生命周期衰减：

| 等级 | 衰减 | 清理 |
|---|---|---|
| permanent | 永不 | 规则 / 身份 / 红线 |
| long | 0.999（极慢） | 知识 / 项目 |
| short | 快 | 90 天后自动撤架 |

### 💬 永久会话历史

Hermes `state.db`（SQLite）每次会话结束同步到 PostgreSQL。完整对话——用户、助手、工具调用、思考链——带时间戳全保真。宫殿下的地窖：原始真相，无损。

### 🔌 Agent 原生集成

**Memory Provider**（11 工具）——全自动，无需手动 `remember()`：

```
mnemosyne_palace_summon  → 三通道召唤（魔法前台）
mnemosyne_search         · mnemosyne_recall      · mnemosyne_hot_memories
mnemosyne_remember       · mnemosyne_dialectic   · mnemosyne_wiki
mnemosyne_media          · session_search        · mnemosyne_tree
```

**WIKI 知识库检索**（v7.4+，论文/方案全文快照档案馆）：

```
mnemosyne_wiki search      → 语义搜索（向量 HNSW + BM25 关键词，RRF 融合，默认开）
mnemosyne_wiki by_source   → 按来源路径/URL 精确查证（防源损毁）
mnemosyne_wiki get/list    → 按 ID 读全文 / 列表
可选参数: rerank=true（豆包重排，高精度场景）、graph=true（图谱 1 跳扩展，默认关）
效果: 20 查询评测 precision@3 100% / recall@3 98.3% / MRR 1.0（v7.5）
```

```
on_session_end   → 同步 + 事实提取        on_turn_start    → 预取
on_pre_compress  → 压缩前注入            on_delegation    → 记录子任务
on_memory_write  → 镜像写入              on_session_switch → 刷写队列
```

### ☁️ 端云双活

WSL 离线？本地 SQLite 缓存。恢复联网？静默推送 PostgreSQL。Cron 维护热度衰减、去重、事实提取、会话整合、离线同步。

---

## 快速开始

```bash
# Hermes Agent（一条命令）
hermes config set memory.provider mnemosyne
# 工具: mnemosyne_palace_summon · mnemosyne_search · mnemosyne_recall · …

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
| API | FastAPI + asyncpg · 50+ REST 端点（含 /palace/*） |
| 搜索 | 三通道召唤（点名/引导/共鸣） |
| 事实提取 | DeepSeek V4 / 豆包 ARK 双底座 |
| 同步 | SQLite ↔ PostgreSQL |
| Agent | Memory Provider 11 工具（含 palace_summon） |

---

## 规模

单用户 + 5 Agent 分身，7×24 稳定运行：

| 指标 | 数值 |
|---|---|
| 归档记忆 | 8,873+ 条（归档率 100%） |
| 结构化 facts | 6,231 条（knowledge 5,230 + preference 1,001） |
| 著录卡片 | 8,682 张 |
| 分类树 | 7翼 × 20房（30 节点） |
| 召唤延迟 | ~100-400ms（三通道） |
| 向量化 | 1024d 豆包 Embedding-Vision |
| 事实提取 | DeepSeek V4（双底座：DeepSeek + 豆包） |

---

## 版本

| 版本 | 日期 | 发布内容 |
|---|---|---|
| [v7.5.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v7.5.0) | 2026-08-09 | 🧠 综合Rank + 提及双向升级 + 快速指针 + 区域化检索 |
| [v7.2.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v7.2.0) | 2026-08-09 | 🧠 Bjork 双强度S/R + GZ调优(pg_stat_statements/workers/水位告警) |
| [v7.1.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v7.1.0) | 2026-08-09 | 🗄️ 抽屉化记忆: 温度×时间双轨制 + 遗忘候选 + 更新端点 + 抽屉API |
| [v7.0.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v7.0.0) | 2026-08-06 | 🏰 魔法记忆宫殿: 分类树+档号+著录卡片+三通道召唤+资料室事实提取+永恒分级 |
| [v6.4.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v6.4.0) | 2026-08-05 | 事实提取管道: 对话→用户事实 (preference/knowledge) |
| [v6.3.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v6.3.0) | 2026-08-05 | 认知写入信号: 重要记忆出生即热 · 保护衰减 |
| [v6.2.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v6.2.0) | 2026-08-05 | 认知热度引擎: 命中加热 · 差异化衰减 · 蒸馏热度 |
| [v6.0.1](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v6.0.1) | 2026-08-02 | 生产性能: uvicorn workers=2 · recall 容错 |
| [v6.0.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v6.0.0) | 2026-08-02 | 概念模型重构 · TMT 管道修复 · reflector 400x |
| [v5.5.2](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.5.2) | 2026-07-29 | NULL embedding 搜索修复 |
| [v5.5.1](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.5.1) | 2026-07-23 | TMT蒸馏修复 · JSON解析加固 |
| [v5.5.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.5.0) | 2026-07-23 | 时间有效性 · 39用例 |
| [v5.4.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.4.0) | 2026-07-23 | 闸机审计 · 建议API · pytest 18用例 |
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
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | v7.0 产品白皮书 — 宫殿架构 |
| [docs/palace-architecture.md](docs/palace-architecture.md) | 魔法记忆宫殿详细设计 |
| [docs/schema.sql](docs/schema.sql) | 完整数据库结构（含宫殿表） |

<p align="center">
  <i>「记忆不是用来存的，是用来活的。」</i><br><br>
  🐾 <b>G-CAT</b> & <b>Hermes Agent</b> · MIT · 2026
</p>
