"""
Mnemosyne v5.0 — 统一配置中心
所有值通过环境变量读取，不硬编码任何模型或密钥。

推荐组合:
  向量化  → 豆包 Embedding-Vision (1024d, 多模态, 中文好)
  日常LLM → 豆包 Seed-2.0 Lite (JSON mode, 便宜量大)
  深度推理 → DeepSeek V4 Pro (异构审计/矛盾检测)
  Reranker → Qwen3-Embed 0.6B 本地部署 (交叉编码精排)

.env 示例:
  EMBEDDING_API_KEY=***  EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  EMBEDDING_MODEL=doubao-embedding-vision-251215
  EMBEDDING_DIM=1024

  LLM_API_KEY=***  LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  LLM_MODEL_LITE=doubao-seed-2-0-lite-260215
  LLM_MODEL_PRO=deepseek-v4-pro
  LLM_BASE_URL_PRO=https://api.deepseek.com/v1

  RERANKER_URL=http://127.0.0.1:11436/rerank

  PGUSER=postgres  PGPASSWORD=***  PGDATABASE=mnemosyne
"""
import os


# ═══════════════════════════════════════════
# Embedding — OpenAI 兼容 API
# 推荐: 豆包 Embedding-Vision / text-embedding-3-small / 本地
# ═══════════════════════════════════════════
EMBEDDING_API_KEY=os.get...Y", "")
EMBEDDING_BASE_URL=os.get...SE_URL", "https://ark.cn-beijing.volces.com/api/v3")
EMBEDDING_MODEL=os.get...MODEL", "doubao-embedding-vision-251215")
EMBEDDING_DIM=int(os.getenv("EMBEDDING_DIM", "1024"))
EMBEDDING_ENDPOINT=os.get...POINT", f"{EMBEDDING_BASE_URL}/embeddings/multimodal")


# ═══════════════════════════════════════════
# LLM — OpenAI 兼容 API，支持多后端
# 推荐: 豆包 Seed-2.0 系列 (日常) + DeepSeek V4 (深度推理)
# ═══════════════════════════════════════════
LLM_API_KEY=os.get...Y", os.getenv("EMBEDDING_API_KEY", ""))
LLM_BASE_URL=os.get...SE_URL", "https://ark.cn-beijing.volces.com/api/v3")

LLM_MODEL_MINI=os.get...NI", "doubao-seed-2-0-mini-260215")
LLM_MODEL_LITE=os.get...TE", "doubao-seed-2-0-lite-260215")
LLM_MODEL_PRO=os.get...RO", "deepseek-v4-pro")
LLM_BASE_URL_PRO=os.get...RO", "https://api.deepseek.com/v1")
LLM_API_KEY_PRO=os.get...RO", os.getenv("LLM_API_KEY", ""))

TMT_LLM_TIER=os.get...ER", "lite")
TMT_MAX_RETRIES=int(os.getenv("TMT_MAX_RETRIES", "3"))


# ═══════════════════════════════════════════
# Reranker — 交叉编码精排 (可选)
# 推荐: Qwen3-Embed 0.6B via llama.cpp server
# ═══════════════════════════════════════════
RERANKER_URL=os.get...RL", "http://127.0.0.1:11436/rerank")


# ═══════════════════════════════════════════
# 数据库 — PostgreSQL + pgvector + AGE
# ═══════════════════════════════════════════
PG_USER=os.get...ER", "postgres")
PG_PASSWORD=os.get...RD", "")
PG_DB=os.get...SE", "mnemosyne")
PG_HOST=os.get...ST", "127.0.0.1")
PG_PORT=int(os.getenv("PGPORT", "5432"))


# ═══════════════════════════════════════════
# 服务
# ═══════════════════════════════════════════
HOST=os.get...ST", "127.0.0.1")
PORT=int(os.getenv("MNEMOSYNE_PORT", "8010"))


# ═══════════════════════════════════════════
# 搜索 & 热度
# ═══════════════════════════════════════════
SEARCH_WEIGHTS = {"vector": 0.45, "bm25": 0.15, "time": 0.15, "reliability": 0.15, "heat": 0.10}
HEAT_DECAY_ALPHA = 0.95
HEAT_BOOST_ACCESS = 0.05
