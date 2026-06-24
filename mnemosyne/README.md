# Mnemosyne OS v5.0 — 认知型记忆操作系统

**全球首款认知级独立记忆OS · 任何AI Agent的永久记忆基建**

> 记忆不是推理的附属功能，而是与推理引擎平级的底层基建。

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.12+
- PostgreSQL 16+ (需 pgvector 扩展)
- 模型 API Key (火山引擎 ARK 或其他)

### 2. 安装

```bash
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git
cd Mnemosyne-OS

# 安装依赖
pip install fastapi uvicorn asyncpg pydantic

# 配置
cp .env.example .env
# 编辑 .env: 填入 ARK_API_KEY + PG 连接信息
```

### 3. 数据库初始化

```sql
-- PostgreSQL 需安装 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
```

### 4. 启动

```bash
python3 main.py
# → Mnemosyne OS 运行在 http://127.0.0.1:8010
```

或 Docker (推荐):
```yaml
# docker-compose.yml — 见白皮书 §12.2.2
```

### 5. 验证

```bash
curl http://127.0.0.1:8010/api/v1/echo
# → {"status":"ok","service":"Mnemosyne"}
```

---

## 📦 核心能力

| 模块 | 能力 | API |
|------|------|-----|
| 🏛️ 三馆闭环 | 研究馆→工程馆→档案馆 知识生产 | `/halls/*` |
| 🧠 五级蒸馏 | TMT: L1碎片→L5画像 | `/tmt/*` |
| 🔍 五维修搜索 | 向量+BM25+时间+信任+热度 | `/memories/search` |
| 🛡️ 纵深安全 | 入馆闸+异构审计+哈希净化 | `/security/*` |
| 📂 项目管理 | 项目沙箱+工具归档 | `/projects/*` `/tools/*` |
| 🔌 多后端 | 豆包/OpenAI兼容/本地模型 | `core/backends.py` |

---

## 🔧 模型配置

默认使用豆包 (火山引擎 ARK)。可切换 OpenAI 兼容后端:

```bash
# .env
MODEL_BACKEND=ark          # 豆包 (默认)
# MODEL_BACKEND=openai      # OpenAI / DeepSeek 兼容
ARK_API_KEY=*** API Key
# OPENAI_API_KEY=*** LLM 梯队
```

| Tier | 豆包模型 | 用途 | 支持切换 |
|:---:|------|------|:---:|
| 1 | embedding-vision (1024d) | 向量化 | ✅ |
| 1.5 | cosine similarity | 排序(Reranker) | ❌ 嵌入式 |
| 2 | seed-2.0-mini | 快速摘要 | ✅ |
| 3 | seed-2.0-lite | 蒸馏主力 (JSON) | ✅ |
| 4 | seed-2.0-code | 审计/深度推理 | ✅ |
| 5 | seedream | 图片生成 | ✅ |

---

## 📖 使用指南

### Hermes Agent 集成

加载技能: `skill_view(name="mnemosyne-os-usage")`

### Python SDK (3行代码)

```python
from integrations.sdk import MnemosyneHermesMemory
m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:8010")
m.add("记忆内容", category="note")        # 存入研究馆
m.get_relevant("搜索关键词")              # 检索记忆
m.archive_tool_call("cmd", {}, "ok", True) # 工具归档
```

### cURL 示例

```bash
# 存入记忆
curl -X POST :8010/api/v1/halls/archive -H 'Content-Type: application/json' \
  -d '{"content":"内容","category":"分类"}'

# 搜索
curl -X POST :8010/api/v1/memories/search -H 'Content-Type: application/json' \
  -d '{"query":"关键词","top_k":5}'

# 三馆流转
curl -X POST :8010/api/v1/halls/promote \
  -d '{"memory_id":123,"target_hall":"archive"}'
```

---

## 🗺️ 架构

```
L7 认知涌现 ← 方案基因重组        [远期]
L6 智能体接入 ← Hermes SDK + MCP   [✅ SDK就绪]
L5 运行时调度 ← 项目沙箱+会话管理   [✅]
L4 核心业务 ← 三馆闭环知识生产      [✅]
L3 算力安全 ← 模型路由+异构审计     [✅]
L2 物理存储 ← PostgreSQL+pgvector  [✅]
L1 端云协同 ← 增量同步              [🟡 单机运行]
```

---

## 📊 当前状态

| 指标 | 值 |
|------|:---:|
| API端点 | 35+ |
| 代码行数 | 4,610 |
| 当前记忆 | 1,158 |
| 三馆分布 | R20/E3/A2 |
| 模型后端 | 豆包 ARK (支持切换) |
| 许可 | MIT |

---

## 🔗 链接

- **白皮书**: `认知型记忆操作系统 产品白皮书.md`
- **Hermes使用技能**: `skill_view("mnemosyne-os-usage")`
- **环境配置模板**: `.env.example`
