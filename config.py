"""
Mnemosyne v5.0 — 统一配置中心
替代 v2.1 的内联 CONFIG dict，支持环境变量 + 多后端
"""
import os

# .env 自动加载（2026-11-04 补）：README 让你 `cp .env.template .env` 填好后直接 `python3 main.py`，
# 但此前全仓库没有任何 load_dotenv() —— .env 形同废纸，配置只能靠 systemd 的 EnvironmentFile 注入。
# 外人照文档操作时所有 PG/密钥配置被静默忽略，表现为「连到了意料之外的库」或「embedding 401」。
# override=False：已存在的环境变量优先，systemd / 容器注入的优先级不变。
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # 依赖未装时降级为纯环境变量，不阻塞启动
    pass

# ── 模型后端（9.0.10 起 embedding 也走这个开关，不再写死 ARK）──
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ark").strip().lower()

# ── 豆包 API (火山引擎 ARK) ──
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE = os.getenv("ARK_BASE", "https://ark.cn-beijing.volces.com/api/v3")

# Embedding
# 默认值 = 9.0.9 行为（ark + doubao-embedding-vision-251215），不设环境变量时行为完全不变。
# MODEL_BACKEND=openai 时才切到 OpenAI 兼容端点（vLLM / Ollama / OpenAI 均可）。
# ⚠️ 切后端注意维度：pgvector 列是 vector(1024)，EMBED_DIM 必须与库一致；
#    OpenAI 的 text-embedding-3-* 支持 dimensions=1024，vLLM/Ollama 视模型而定。
if MODEL_BACKEND == "openai":
    EMBED_MODEL = os.getenv("EMBED_MODEL") or os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    _EMBED_BASE = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    EMBED_URL = os.getenv("EMBED_URL", f"{_EMBED_BASE}/embeddings")
    EMBED_API_KEY = os.getenv("OPENAI_API_KEY", "")
    EMBED_PAYLOAD_STYLE = "openai"   # {"input": "纯文本"}
else:
    EMBED_MODEL = os.getenv("EMBED_MODEL", "doubao-embedding-vision-251215")
    EMBED_URL = os.getenv("EMBED_URL", f"{ARK_BASE}/embeddings/multimodal")
    EMBED_API_KEY = ARK_API_KEY or os.getenv("OPENAI_API_KEY", "")
    EMBED_PAYLOAD_STYLE = "ark"      # {"input": [{"type": "text", "text": ...}]}
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))

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
