# Mnemosyne OS · 安装指南

> 从零到跑起来的完整手册。三种接入方式，按需选择。
> 版本: v9.0.21 | 更新: 2026-11-07

---

## 目录

- [三种接入方式](#三种接入方式)
- [前置要求](#前置要求)
- [方式一：Hermes Agent 一键接入（最快）](#方式一hermes-agent-一键接入最快)
- [方式二：独立部署（完整版）](#方式二独立部署完整版)
  - [1. 准备 PostgreSQL](#1-准备-postgresql)
  - [2. 导入数据库结构](#2-导入数据库结构)
  - [3. 配置模型后端](#3-配置模型后端)
  - [4. 安装 Python 依赖](#4-安装-python-依赖)
  - [5. 启动服务](#5-启动服务)
  - [6. 验证安装](#6-验证安装)
- [方式三：Python SDK 集成](#方式三python-sdk-集成)
- [分环境说明](#分环境说明)
  - [Ubuntu/Debian](#ubuntudebian)
  - [macOS](#macos)
  - [Windows (WSL2)](#windows-wsl2)
- [常见问题 FAQ](#常见问题-faq)
- [下一步](#下一步)

---

## 三种接入方式

| 方式 | 适合谁 | 耗时 | 说明 |
|------|--------|------|------|
| ① Hermes Agent 一键 | 使用 Hermes Agent 的用户 | ~2 分钟 | 配置一个命令，工具自动出现 |
| ② 独立部署 | 自托管 / 其他 Agent 框架 | ~15 分钟 | 完整服务，REST API + SDK |
| ③ Python SDK | 想在自己代码里调用 | 依赖方式② | 在独立部署基础上加一行 import |

> ⚠️ 三种方式都依赖一个 **PostgreSQL 16+ 数据库**（含 pgvector；实测 18.6 同样可用）和至少一个 **LLM/Embedding API**（火山引擎 ARK / DeepSeek / 任意 OpenAI 兼容端点）。

---

## 前置要求

| 组件 | 要求 |
|------|------|
| 操作系统 | Linux / macOS / Windows (WSL2) |
| Python | 3.11+ |
| PostgreSQL | 16.x 或更高（实测 18.6 通过）· pgvector ≥ 0.7 |
| 内存 | 8GB+（推荐） |
| 模型 API | 任选其一：火山引擎 ARK（豆包）、DeepSeek、OpenAI 兼容端点 |
| 磁盘 | 2GB+（不含数据库增长） |

---

## 方式一：Hermes Agent 一键接入（最快）

如果你已经在使用 [Hermes Agent](https://hermes-agent.nousresearch.com/docs)，Mnemosyne Memory Provider 已随 Hermes 内置：

```bash
# 1. 配置使用 mnemosyne 作为记忆提供者
hermes config set memory.provider mnemosyne

# 2. 重启 Hermes（或 /reset），工具自动出现：
#    mnemosyne_palace_summon · mnemosyne_search · mnemosyne_recall
#    mnemosyne_remember    · mnemosyne_dialectic · mnemosyne_hot_memories
#    mnemosyne_wiki        · mnemosyne_tree      · mnemosyne_media
```

> 前提：你已有一个可访问的 Mnemosyne 服务（本机 18010 端口或远程）。没有？请先走[方式二](#方式二独立部署完整版)部署服务本体。

**远程服务（如部署在服务器上）** 通过 SSH 隧道访问：

```bash
ssh -L 18010:127.0.0.1:8010 your-server
# 然后 Hermes 的 mnemosyne 工具自动通过 127.0.0.1:18010 访问
```

---

## 方式二：独立部署（完整版）

### 1. 准备 PostgreSQL

#### Ubuntu / Debian 24.04+

```bash
# 安装 PostgreSQL 16+ 与 pgvector
sudo apt install postgresql-16 postgresql-16-pgvector

# 启动服务
sudo systemctl enable --now postgresql

# 创建数据库和用户
sudo -u postgres psql <<'SQL'
CREATE USER mnemosyne WITH PASSWORD 'your-strong-password';
CREATE DATABASE mnemosyne OWNER mnemosyne;
SQL
```

#### macOS（Homebrew）

```bash
brew install postgresql@16
brew install pgvector
```

#### Windows (WSL2)

```bash
# WSL2 内就是 Ubuntu，按 Ubuntu 步骤执行即可
```

### 2. 导入数据库结构

```bash
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
cd Mnemosyne-OS

# 导入完整表结构（23 张表：记忆/卡片/分类树/实体/技能/日记）
# ⚠️ 需用数据库超级用户（如 postgres）执行：CREATE EXTENSION 需要高权限
# schema.sql 自带 CREATE EXTENSION（vector / pg_trgm），导入即自动建扩展
sudo -u postgres psql -d mnemosyne -f docs/schema.sql

# 导入后把权限交给应用用户（只需要 public —— 9.0 起不再有 ag_catalog / mnemosyne_graph）
sudo -u postgres psql -d mnemosyne -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO mnemosyne;"
sudo -u postgres psql -d mnemosyne -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO mnemosyne;"

# 验证表结构
PGPASSWORD=your-strong-password psql -h 127.0.0.1 -U mnemosyne -d mnemosyne -c "\dt"
```

> schema.sql 是纯结构（零数据），可安全导入。首次启动服务时还会自动创建宫殿相关表（幂等）。

### 3. 配置模型后端

复制环境变量模板并编辑：

```bash
cp .env.template .env
```

**最少配置（推荐组合：DeepSeek 主推理 + 豆包向量）**：

```dotenv
# ── 必填：至少一个模型后端 ──
ARK_API_KEY=你的火山引擎ARK密钥        # 豆包：向量化+日常LLM（推荐）
DEEPSEEK_API_KEY=你的DeepSeek密钥      # DeepSeek：蒸馏/审计（可选但推荐）

# ── PostgreSQL ──
PGUSER=mnemosyne
PGPASSWORD=your-strong-password
PGDATABASE=mnemosyne
PGHOST=127.0.0.1
PGPORT=5432
```

**只用 OpenAI 兼容后端**（OpenAI / 本地 vLLM / 任意兼容端点）：

```dotenv
# 关闭豆包，启用 OpenAI 兼容
MODEL_BACKEND=openai
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1   # 或本地 vLLM: http://localhost:8000/v1
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_CHAT_MINI=gpt-4o-mini
```

> 模型可插拔：换模型只改环境变量，零代码改动。详见 [.env.template](.env.template) 完整字段表。

### 4. 安装 Python 依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -c constraints.txt
```

> `requirements.txt` 全是 `>=`（不把下游锁死）；`constraints.txt` 钉的是**我们实测跑通的那一套**版本。
> 想省事就带上 `-c`；想自己挑版本就不带。出问题时两边的环境能对得上，靠的就是这个文件。

### 5. 启动服务

```bash
python main.py
# → FastAPI 服务监听 http://127.0.0.1:8010
```

> 端口与监听地址由 `MNEMOSYNE_PORT` / `MNEMOSYNE_HOST` 控制（默认 `8010` / `127.0.0.1`），v7.8.3 起真正生效（v8.0.0 沿用）；无需改代码。

> 生产环境建议用 systemd 或进程管理器。参考 [deploy/mnemosyne.service](deploy/mnemosyne.service)（uvicorn 双 worker）。

### 6. 自检：缺什么，直接告诉你

```bash
python3 scripts/doctor.py
```

逐项检查 Python 版本、依赖、`.env` 是否真的被读进来、PostgreSQL 连接、pgvector / pg_trgm 扩展、
表结构是否导全（含 `dedup_fingerprint_key` 这类关键唯一索引）、模型 key、端口占用。
每项一行输出，失败项**直接给修复命令**。

想马上看到效果，再跑：

```bash
python3 scripts/seed_demo.py     # 写入 5 条示例记忆并演示一次检索（--clean 可删）
```

### 7. 验证安装

```bash
# 健康检查
curl http://127.0.0.1:8010/api/v1/echo
# → {"status":"ok","service":"Mnemosyne OS","version":"9.0.9"}

# 存入一条记忆
curl -X POST http://127.0.0.1:8010/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","content":"我的第一条测试记忆","category":"knowledge"}'

# 搜索它
curl -X POST http://127.0.0.1:8010/api/v1/memories/search \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"default","query":"测试记忆","top_k":3}'

# 三通道召唤（宫殿核心能力）
curl "http://127.0.0.1:8010/api/v1/palace/summon?q=测试&user_id=default&top_k=3"
```

---

### 8. 验证 9.0 记忆操作系统（推荐）

```bash
# 子系统自检
curl -s http://127.0.0.1:8010/api/v1/memory-os/health
# → {"status":"ok","router":"memory-os","endpoints":5}

# 写入几张卡之后，试一次四通道召回
curl -s -X POST http://127.0.0.1:8010/api/v1/memory-os/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"上次部署的结论","limit":5}'

# 卡片体检（档号率 / 实体率 / 向量覆盖）
curl -s http://127.0.0.1:8010/api/v1/memory-os/stats
```

> 三个都通，说明卡片、召回、追溯这条主链路是活的。

---

## 方式三：Python SDK 集成

在方式二部署的服务之上，任何 Python 应用都可以接入：

```python
from integrations.sdk import MnemosyneHermesMemory

m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:8010")

# 存入
m.add("pgvector HNSW 对高维召回优于 IVFFlat")

# 检索（五维修: 向量+BM25+时间+信任+热度）
results = m.get_relevant("哪个 pgvector 索引更好？")

# 按馆查询
m.search_by_hall("archive")       # 已验证知识
m.search_by_hall("engineering")   # 踩坑记录
m.search_by_hall("research")      # 待验证
```

---

## 分环境说明

### Ubuntu/Debian

✅ 最省事路径（本指南实测环境）：apt 装 PG + pgvector 两个包即可。

```bash
sudo apt install postgresql-16 postgresql-16-pgvector
```

### macOS

- PostgreSQL 16 + pgvector：Homebrew 直接装。
- Apache AGE：**不再需要**。v7.8 起实体图谱改走 `entities` / `memory_entities` / `wiki_entities` 普通表，AGE 已移除。

### Windows (WSL2)

- 推荐 WSL2 + Ubuntu，完全按 Ubuntu 步骤。
- 原生 Windows 跑 PostgreSQL 需手动装扩展，不推荐。

---

## 常见问题 FAQ

**Q: 启动报 `column ... does not exist`？**
A: 数据库结构未导入。确认已执行 `psql -f docs/schema.sql`，且版本与仓库一致。

**Q: 报 `extension "age" is not available`？**
A: 多半是 pgvector 未安装。Ubuntu: `sudo apt install postgresql-16-pgvector`；macOS: `brew install pgvector`，再 `CREATE EXTENSION vector;`。

**Q: 搜索报 embedding 相关错误？**
A: 模型 API 密钥未配置或无效。检查 `.env` 中 `ARK_API_KEY` / `OPENAI_API_KEY`，并 `curl` 验证端点可达。

**Q: 可以用纯本地模型吗？**
A: 可以，任何 OpenAI 兼容端点都行（如 vLLM / Ollama 的 /v1 接口），设置 `MODEL_BACKEND=openai` + `OPENAI_BASE_URL=http://localhost:8000/v1` + `OPENAI_EMBED_MODEL=<你的模型>` 即可。
**⚠️ 维度必须对上**：库里的向量列固定是 `vector(1024)`，所以要么选原生 1024 维的模型，要么用支持 `dimensions=1024` 的模型（OpenAI 的 text-embedding-3-* 支持）。维度不一致时写入会直接报错，不会静默截断。

**Q: `/memory-os/recall` 返回 0 条，是装坏了吗？**
A: 多半不是。它只查 `content LIKE '[结果卡]%'` —— **裸记忆它不捞**（而且不报错）。
想看到效果：`make demo` 灌 40 张演示卡，再 `make eval`；查裸记忆请用 `POST /api/v1/memories/search`。
这是设计：这套 API 服务的是**著录卡**，不是裸文本。细节见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。

**Q: 多用户支持？**
A: **不。9.0 是单租户**，没有账号体系、没有权限隔离。`user_id` 只是**逻辑分组**参数，由调用方自报 —— 谁能访问 8010 端口，谁就能传任意 `user_id` 读写任何数据。
鉴权只做在**反向代理层**（见 `docs/DEPLOY-PRIVATE.md`：外层套 nginx + Token 或登录墙），应用本身不校验身份。所以：**只监听 127.0.0.1 / 内网，不要裸暴露公网**。多租户与权限体系是 9.1 的事。

**Q: 数据备份？**
A: 标准 pg_dump 即可：`pg_dump -U mnemosyne -d mnemosyne -Fc > backup.dump`。

---

## 下一步

- 📖 [README.md](README.md) — 产品全景与设计理念
- 🤖 [AGENTS.md](AGENTS.md) — AI Agent 接入手册（端点速查/环境变量/Hermes 配置）
- 🏰 [docs/palace-architecture.md](docs/palace-architecture.md) — 魔法记忆宫殿设计
- 📜 [docs/WHITEPAPER.md](docs/WHITEPAPER.md) — 产品白皮书
- 📚 [docs/schema.sql](docs/schema.sql) — 完整数据库结构

---

*Mnemosyne OS · MIT License · 用记忆构建会思考的 Agent*
