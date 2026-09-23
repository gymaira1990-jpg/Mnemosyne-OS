# 环境变量全表

> 从 `AGENTS.md` 下沉。
> 返回 [AGENTS.md](../AGENTS.md)

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
| `MNEMOSYNE_PORT` | 否 | `8010` | 服务监听端口（v7.8.3 起真正生效） |

> 模型可插拔原则：换模型/换后端只改环境变量，不碰代码。

---
