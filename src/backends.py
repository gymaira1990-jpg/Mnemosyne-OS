"""
Mnemosyne OS v5.0 — 多后端模型配置
支持: 豆包(ARK) / DeepSeek / OpenAI 兼容 / 本地模型

推荐组合:
  豆包全家桶  —  Embedding-Vision + Seed-2.0 系列 (性价比高, 中文好)
  DeepSeek    —  V4 Pro (深度推理, 异构审计)
  OpenAI      —  GPT-4o (备用)

设置环境变量 MODEL_BACKEND=ark|openai|custom 切换
"""
import os
from typing import Optional

MODEL_BACKENDS = {
    "ark": {
        "name": "火山引擎 ARK (豆包) — 推荐",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "auth_env": "ARK_API_KEY",
        "models": {
            "embedding": "doubao-embedding-vision-251215",
            "chat_mini": "doubao-seed-2-0-mini-260215",
            "chat_lite": "doubao-seed-2-0-lite-260215",
            "chat_pro": "doubao-seed-2-0-code-preview-260215",
        },
        "dimensions": [1024, 2048],
        "default_dim": 1024,
    },
    "deepseek": {
        "name": "DeepSeek — 深度推理推荐",
        "base_url": "https://api.deepseek.com/v1",
        "auth_env": "DEEPSEEK_API_KEY",
        "models": {
            "chat_pro": "deepseek-v4-pro",
            "chat_lite": "deepseek-v4-flash",
        },
    },
    "openai": {
        "name": "OpenAI 兼容 (可接任何兼容API)",
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "auth_env": "OPENAI_API_KEY",
        "models": {
            "embedding": os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            "chat_mini": os.getenv("OPENAI_CHAT_MINI", "gpt-4o-mini"),
            "chat_lite": os.getenv("OPENAI_CHAT_LITE", "gpt-4o"),
        },
        "dimensions": [512, 1536],
        "default_dim": 1536,
    },
}

ACTIVE_BACKEND = os.getenv("MODEL_BACKEND", "ark")


def get_backend(name: Optional[str] = None) -> dict:
    backend = MODEL_BACKENDS.get(name or ACTIVE_BACKEND)
    if not backend:
        raise ValueError(f"未知后端: {name or ACTIVE_BACKEND}. 可选: {list(MODEL_BACKENDS.keys())}")
    return backend


def get_model(model_type: str, backend_name: Optional[str] = None) -> str:
    backend = get_backend(backend_name)
    model = backend["models"].get(model_type)
    if not model:
        raise ValueError(f"后端 {backend['name']} 不支持 {model_type}")
    return model


def list_backends() -> list:
    return [
        {"id": k, "name": v["name"], "dimensions": v.get("dimensions", [])}
        for k, v in MODEL_BACKENDS.items()
    ]
