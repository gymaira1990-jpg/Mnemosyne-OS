# Mnemosyne OS · 安装指南

> 从零到跑起来的完整手册。三种接入方式，按需选择。
> 版本: v7.6.1 | 更新: 2026-08-11

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

> ⚠️ 三种方式都依赖一个 **PostgreSQL 16 数据库**（含 pgvector + Apache AGE 扩展）和至少一个 **LLM/Embedding API**（火山引擎 ARK / DeepSeek / 任意 OpenAI 兼容端点）。

---

## 前置要求

| 组件 | 要求 |
|------|------|
| 操作系统 | Linux / macOS / Windows (WSL2) |
| Python | 3.12+ |
| PostgreSQL | 16.x（含 pgvector ≥ 0.7、Apache AGE ≥ 1.5） |
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
# 安装 PostgreSQL 16 + 扩展（Apache AGE + pgvector）
sudo apt install postgresql-16 postgresql-16-age postgresql-16-pgvector

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
# Apache AGE: 无 Homebrew 官方包，需源码编译（见下方"AGE 编译"）
```

**AGE 源码编译（macOS / 无 apt 包的环境）**：

```bash
git clone https://github.com/apache/age.git
cd age && make PG_CONFIG=/usr/local/opt/postgresql@16/bin/pg_config
sudo make install PG_CONFIG=/usr/local/opt/postgresql@16/bin/pg_config
```

#### Windows (WSL2)

```bash
# WSL2 内就是 Ubuntu，按 Ubuntu 步骤执行即可
```

### 2. 导入数据库结构

```bash
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
cd Mnemosyne-OS

# 导入完整表结构（30 张表，含宫殿/图谱/知识库）
# ⚠️ 需用数据库超级用户（如 postgres）执行：CREATE EXTENSION 需要高权限
# schema.sql 自带 CREATE EXTENSION（age/vector/pg_trgm），导入即自动建扩展
sudo -u postgres psql -d mnemosyne -f docs/schema.sql

# 导入后把权限交给应用用户
sudo -u postgres psql -d mnemosyne -c "GRANT ALL ON ALL TABLES IN SCHEMA public, ag_catalog, mnemosyne_graph TO mnemosyne;"
sudo -u postgres psql -d mnemosyne -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public, ag_catalog, mnemosyne_graph TO mnemosyne;"

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
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. 启动服务

```bash
python main.py
# → FastAPI 服务监听 http://127.0.0.1:8010
```

> ⚠️ 端口当前硬编码为 8010（v7.6.1）。如需换端口，改 `main.py` 最后一行 `port=8010`（环境变量 `MNEMOSYNE_PORT` 暂未生效，下版本修复）。

> 生产环境建议用 systemd 或进程管理器。参考 [deploy/mnemosyne.service](deploy/mnemosyne.service)（uvicorn 双 worker）。

### 6. 验证安装

```bash
# 健康检查
curl http://127.0.0.1:8010/api/v1/echo
# → {"status":"ok","service":"Mnemosyne OS","version":"7.6.1"}

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

✅ 最省事路径（本指南实测环境）：apt 一条命令装齐 PG16+AGE+pgvector。

```bash
sudo apt install postgresql-16 postgresql-16-age postgresql-16-pgvector
```

### macOS

- PostgreSQL 16 + pgvector：Homebrew 直接装。
- Apache AGE：无官方包，需 [源码编译](#age-源码编译macos--无-apt-包的环境)（10 分钟，Makefile 一条命令）。

### Windows (WSL2)

- 推荐 WSL2 + Ubuntu，完全按 Ubuntu 步骤。
- 原生 Windows 跑 PostgreSQL 需手动装扩展，不推荐。

---

## 常见问题 FAQ

**Q: 启动报 `column ... does not exist`？**
A: 数据库结构未导入。确认已执行 `psql -f docs/schema.sql`，且版本与仓库一致。

**Q: 报 `extension "age" is not available`？**
A: Apache AGE 未安装。Ubuntu: `sudo apt install postgresql-16-age`；macOS: 源码编译后 `CREATE EXTENSION`。

**Q: 搜索报 embedding 相关错误？**
A: 模型 API 密钥未配置或无效。检查 `.env` 中 `ARK_API_KEY` / `OPENAI_API_KEY`，并 `curl` 验证端点可达。

**Q: 可以用纯本地模型吗？**
A: 可以，任何 OpenAI 兼容端点都行（如 vLLM / Ollama 的 /v1 接口），设置 `MODEL_BACKEND=openai` + `OPENAI_BASE_URL=http://localhost:8000/v1` 即可。

**Q: 多用户支持？**
A: 通过 `user_id` 字段天然隔离（如 `user_id=alice` / `user_id=bob`），记忆互不可见。

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
