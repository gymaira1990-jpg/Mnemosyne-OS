"""
Mnemosyne v5.0 — 统一配置中心
所有值通过环境变量读取，不硬编码任何模型或密钥。

推荐组合:
  向量化  → 豆包 Embedding-Vision (1024d, 多模态)
  日常LLM → 豆包 Seed-2.0 Lite (JSON mode, 便宜)
  深度推理 → DeepSeek V4 (异构审计/矛盾检测)

.env 示例:
  EMBEDDING_API_KEY=your-key
  EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  EMBEDDING_MODEL=doubao-embedding-vision-251215
  EMBEDDING_DIM=1024

  LLM_API_KEY=your-key
  LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  LLM_MODEL_LITE=doubao-seed-2-0-lite-260215
  LLM_MODEL_PRO=deepseek-v4-pro

  PGUSER=postgres
  PGPASSWORD=your-db-password
  PGDATABASE=mnemosyne
  PGHOST=127.0.0.1
"""
import os


# ═══════════════════════════════════════════
# Embedding — 任何 OpenAI 兼容 API
# 推荐: 豆包 Embedding-Vision / text-embedding-3-small / 本地模型
# ═══════════════════════════════════════════
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "doubao-embedding-vision-251215")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# 端点: 通常为 {BASE}/embeddings 或 {BASE}/embeddings/multimodal
EMBEDDING_ENDPOINT = os.getenv(
    "EMBEDDING_ENDPOINT",
    f"{EMBEDDING_BASE_URL}/embeddings/multimodal"
)


# ═══════════════════════════════════════════
# LLM — 任何 OpenAI 兼容 API
# 推荐: 豆包 Seed-2.0 系列 (日常) + DeepSeek V4 (深度推理)
# 也可用: OpenAI / 本地 llama.cpp / vLLM
# ═══════════════════════════════════════════
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("EMBEDDING_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

# 模型名 — 换成你自己的就行
LLM_MODEL_MINI = os.getenv("LLM_MODEL_MINI", "doubao-seed-2-0-mini-260215")
LLM_MODEL_LITE = os.getenv("LLM_MODEL_LITE", "doubao-seed-2-0-lite-260215")
LLM_MODEL_PRO = os.getenv("LLM_MODEL_PRO", "deepseek-v4-pro")

# 如果用 DeepSeek，设置这个 base URL（不同于豆包）
LLM_BASE_URL_PRO = os.getenv("LLM_BASE_URL_PRO", "https://api.deepseek.com/v1")
LLM_API_KEY_PRO = os.getenv("LLM_API_KEY_PRO", os.getenv("LLM_API_KEY", ""))

# 蒸馏用模型层级
TMT_LLM_TIER = os.getenv("TMT_LLM_TIER", "lite")  # mini / lite / pro
TMT_MAX_RETRIES = int(os.getenv("TMT_MAX_RETRIES", "3"))


# ═══════════════════════════════════════════
# 数据库 — PostgreSQL + pgvector
# ═══════════════════════════════════════════
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "")
PG_DB = os.getenv("PGDATABASE", "mnemosyne")
PG_HOST = os.getenv("PGHOST", "127.0.0.1")
PG_PORT = int(os.getenv("PGPORT", "5432"))


# ═══════════════════════════════════════════
# 服务
# ═══════════════════════════════════════════
HOST = os.getenv("MNEMOSYNE_HOST", "127.0.0.1")
PORT = int(os.getenv("MNEMOSYNE_PORT", "8010"))


# ═══════════════════════════════════════════
# 搜索 & 热度
# ═══════════════════════════════════════════
SEARCH_WEIGHTS = {
    "vector": 0.45,
    "bm25": 0.15,
    "time": 0.15,
    "reliability": 0.15,
    "heat": 0.10,
}

HEAT_DECAY_ALPHA = 0.95
HEAT_BOOST_ACCESS = 0.05
