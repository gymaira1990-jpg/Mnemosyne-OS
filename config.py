"""
Mnemosyne v5.0 — 统一配置中心
替代 v2.1 的内联 CONFIG dict，支持环境变量 + 多后端
"""
import os

# ── 豆包 API (火山引擎 ARK) ──
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"

# Embedding
EMBED_MODEL = "doubao-embedding-vision-251215"
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
EMBED_URL = f"{ARK_BASE}/embeddings/multimodal"

# LLM 梯队
DOUBAO_MINI = "doubao-seed-2-0-mini-260215"     # Tier 2: 快速/便宜
DOUBAO_LITE = "doubao-seed-2-0-lite-260215"      # Tier 3: 主力, 支持 JSON/工具调用
DOUBAO_CODE = "doubao-seed-2-0-code-preview-260215"  # Tier 4: 深度推理

# DeepSeek (Tier 4 异构审计)
DEEPSEEK_PRO = os.getenv("DEEPSEEK_PRO", "deepseek-v4-pro")
DEEPSEEK_FLASH = os.getenv("DEEPSEEK_FLASH", "deepseek-v4-flash")

# ── 数据库 ──
PG_USER = os.getenv("PGUSER", "postgres")
PG_PASSWORD = os.getenv("PGPASSWORD", "")
PG_DB = os.getenv("PGDATABASE", "mnemosyne")
PG_HOST = os.getenv("PGHOST", "127.0.0.1")
PG_PORT = int(os.getenv("PGPORT", "5432"))

# ── 服务 ──
HOST = os.getenv("MNEMOSYNE_HOST", "127.0.0.1")
PORT = int(os.getenv("MNEMOSYNE_PORT", "8010"))

# ── 搜索权重 ──
SEARCH_WEIGHTS = {
    "vector": 0.45,
    "bm25": 0.15,
    "time": 0.15,
    "reliability": 0.15,
    "heat": 0.10,
}

# ── 热度衰减 ──
HEAT_DECAY_ALPHA = 0.95   # 每日衰减系数
HEAT_BOOST_ACCESS = 0.05   # 每次访问增量

# ── TMT 蒸馏 ──
TMT_LLM_TIER = "lite"       # 蒸馏用模型: mini/lite/pro
TMT_MAX_RETRIES = 3          # LLM 调用最大重试次数
