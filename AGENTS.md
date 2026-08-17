# Mnemosyne OS · Agent 手册

> 给 AI 编码助手 / Agent 框架的对接手册。你的 AI 进入本仓库时自动加载此文件。
> 目标：让任何 Agent（Hermes / Claude Code / Cursor / 自定义框架）都能在 5 分钟内对接 Mnemosyne OS。

---

## 项目定位

**认知型记忆操作系统** —— 给 AI Agent 的长期记忆宫殿。

不是向量数据库，不是 RAG 管道。它会自己**捕获 → 蒸馏 → 老化 → 遗忘 → 浮现**：
- 🏰 魔法宫殿组织：分类树(7翼×20房) + 档号体系 + 著录卡片
- 🪄 三通道召唤：点名(精确) / 引导(分类) / 共鸣(向量)
- 🕵️ 事实提取：对话 → 结构化 facts（个人信息/偏好/事件/能力）
- ⏳ 永恒分级：permanent / long / short 生命周期
- 🧠 认知热度：重要记忆自动升温，噪音自动衰减

当前版本: **v7.8.0** | License: MIT | 生产运行: 7×24 单机

---

## 架构速览

```
Mnemosyne OS (FastAPI, 50+ 端点)
  ├── main.py            服务入口 + 核心路由 (memories/search/palace/wiki/...)
  ├── palace.py          🏰 宫殿核心 (分类/档号/卡片/召唤/生命周期)
  ├── core/              LLM / Embedding / Chunker 引擎
  ├── api/               REST API 模块
  ├── tmt/               蒸馏引擎 (factextract/distill)
  ├── wiki/              WIKI 知识库模块 (BM25/图谱/提取/评测)
  ├── security/          审计与净化
  ├── integrations/      Hermes 集成 (Memory Provider + MCP)
  │   └── hermes-provider/  Memory Provider v7 (11 工具, palace_summon)
  ├── sync/              端云同步 (SQLite ↔ PostgreSQL)
  └── docs/              白皮书 + 宫殿设计 + schema

数据层: PostgreSQL 16 + pgvector 1024d (HNSW)(v7.8: Apache AGE 图已切除 — 实体关联走 entities/memory_entities/wiki_entities 表)
模型层: 可插拔 —— 豆包 ARK / DeepSeek / 任意 OpenAI 兼容端点
```

---

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

## API 端点速查

### 核心（记忆）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/echo` | GET | 健康检查 + 版本 |
| `/api/v1/memories` | GET | 列出记忆（`?sort=created_at` 时间轴 / `?sort=heat` 热度轴） |
| `/api/v1/memories` | POST | 存入记忆（自动向量化+实体提取+矛盾检测） |
| `/api/v1/memories/{id}` | GET | 单条详情 |
| `/api/v1/memories/{id}` | PUT | 更新 |
| `/api/v1/memories/{id}` | DELETE | 软删除 |
| `/api/v1/memories/{id}/restore` | POST | 恢复已删 |
| `/api/v1/memories/search` | POST | 五维修搜索（向量+BM25+时间+信任+热度） |
| `/api/v1/memories/{id}/feedback` | POST | 反馈（positive/negative，影响可信度） |
| `/api/v1/memories/heat-top` | GET | 热度排行 |
| `/api/v1/memories/stats` | GET | 记忆库统计 |
| `/api/v1/memories/tree` | GET | 记忆层级树 |
| `/api/v1/memories/{id}/traces` | GET | 生命周期轨迹 |
| `/api/v1/memories/{id}/tiered` | GET | 三级读取（L5/L3/L1） |

### 宫殿（v7 核心）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/palace/status` | GET | 宫殿状态（归档率/卡片数/分类树） |
| `/api/v1/palace/summon` | GET | 三通道召唤（点名/引导/共鸣） |
| `/api/v1/palace/archive` | POST | 分类归档（自动生成档号+著录卡片） |
| `/api/v1/palace/extract` | POST | 事实提取（对话→facts） |
| `/api/v1/palace/refine` | POST | 卡片精炼（LLM） |
| `/api/v1/palace/lifecycle` | POST | 生命周期流转 |
| `/api/v1/palace/pin` | POST | 置顶（防衰减） |

### 图谱 / Wiki / 信念

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/graph/search` | POST | 实体关联记忆检索(entities 向量→memory_entities 关联) |
| `/api/v1/wiki` | GET/POST | 知识库页面读写 |
| `/api/v1/wiki/search` | POST | 语义搜索（向量+BM25 RRF 融合） |
| `/api/v1/wiki/by-source` | GET | 按来源路径/URL 精确查证 |
| `/api/v1/beliefs` | POST | 创建信念（自动合并置信度） |
| `/api/v1/beliefs/search` | POST | 语义搜索信念 |
| `/api/v1/beliefs/{id}/evolve` | POST | 演化信念（加证据/调整置信度） |

### 会话 / 蒸馏 / 运维

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/sessions/archive` | POST | 会话归档（v7.8: 消息列表/同步端点已切除, 原文走 Hermes state.db） |
| `/api/v1/reflect` | POST | TMT 反思（`?mode=light` 热度衰减 / `?mode=deep` LLM 凝练） |
| `/api/v1/extract-entities` | POST | 批量实体提取到图谱 |
| `/api/v1/health/{user_id}` | GET | 用户健康报告 |
| `/api/v1/capabilities` | GET | 完整能力清单（自描述） |
| `/api/v1/dialectic` | POST | 辨证检索（带上下文） |

> 📋 完整端点列表与参数：`GET /api/v1/capabilities`（服务自描述，始终最新）。

---

## 环境变量全表

复制 `.env.template` 为 `.env` 并填写。所有配置通过环境变量注入，**零代码改动**。

| 变量 | 必填 | 默认 | 说明 |
|------|:---:|------|------|
| `ARK_API_KEY` | 推荐 | - | 火山引擎 ARK（豆包）：向量化+日常 LLM |
| `DEEPSEEK_API_KEY` | 推荐 | - | DeepSeek：蒸馏/审计（双底座） |
| `MODEL_BACKEND` | 否 | `ark` | `ark` \| `openai`（OpenAI 兼容端点切换） |
| `OPENAI_API_KEY` | 条件 | - | `MODEL_BACKEND=openai` 时必填 |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1` | 本地 vLLM: `http://localhost:8000/v1` |
| `OPENAI_EMBED_MODEL` | 否 | `text-embedding-3-small` | embedding 模型 |
| `OPENAI_CHAT_MINI` | 否 | `gpt-4o-mini` | 轻量对话 |
| `OPENAI_CHAT_LITE` | 否 | `gpt-4o` | 主力对话 |
| `EMBED_DIM` | 否 | `1024` | 向量维度（openai 默认 1536） |
| `PGUSER` | 是 | `postgres` | 数据库用户 |
| `PGPASSWORD` | 是 | - | 数据库密码 |
| `PGDATABASE` | 是 | `mnemosyne` | 数据库名 |
| `PGHOST` | 否 | `127.0.0.1` | 数据库地址 |
| `PGPORT` | 否 | `5432` | 数据库端口 |
| `MNEMOSYNE_HOST` | 否 | `127.0.0.1` | 服务监听地址 |
| `MNEMOSYNE_PORT` | 否 | `8010` | ⚠️ v7.8.0 暂未生效（硬编码 8010） |

> 模型可插拔原则：换模型/换后端只改环境变量，不碰代码。

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

## 最佳实践（Agent 用）

1. **存**：重要决策/踩坑/用户偏好 → `POST /memories`，带 `category`（10 类词表见下）
2. **取**：日常查询用 `POST /memories/search`；宫殿能力用 `palace/summon`；时间问题用 `GET /memories?sort=created_at`（**热度≠时间**）
3. **分类词表**（10 类，数据库 CHECK 约束）：
   `knowledge` 知识 · `pitfall` 踩坑 · `reference` 资料 · `project` 项目 · `ops` 运维 · `deploy` 部署 · `preference` 偏好 · `session` 会话 · `worklog` 日志 · `temp` 临时
4. **多用户**：`user_id` 天然隔离（`alice` / `bob` 互不可见）
5. **蒸馏**：定时 `POST /reflect?mode=light`（无 LLM 成本）；深度凝练用 `mode=deep`
6. **不要存**：代码/脚本（放 git）；临时状态（放会话）；可直接重算的中间值

---

## 开发贡献

```bash
# 本地开发
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
cd Mnemosyne-OS && pip install -r requirements.txt

# 测试（194 用例）
pytest tests/

# 提交规范
feat: / fix: / docs: / chore: / release:

# 红线
- 绝不硬编码 API Key / 真实 IP / 域名 / 密码
- push 前必须隐私扫描（git-privacy-audit）
- 版本号三处一致（VERSION / README badge / CHANGELOG）
```

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 产品全景（英文） |
| [README_CN.md](README_CN.md) | 产品全景（中文） |
| [INSTALL.md](INSTALL.md) | 分环境安装指南 |
| [docs/WHITEPAPER.md](docs/WHITEPAPER.md) | 白皮书（设计理念） |
| [docs/palace-architecture.md](docs/palace-architecture.md) | 宫殿架构详解 |
| [docs/schema.sql](docs/schema.sql) | 完整数据库结构 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |

---

*Mnemosyne OS · 记忆不是用来存的，是用来活的。*
