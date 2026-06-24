"""
Mnemosyne OS v5.0 — 多后端模型配置
支持: 豆包(ARK) / OpenAI兼容 / 本地模型
"""
import os
from typing import Optional

# ── 模型后端定义 ──
MODEL_BACKENDS = {
    "ark": {
        "name": "火山引擎 ARK (豆包)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "auth": lambda: f"Bearer {os.getenv('ARK_API_KEY', '')}",
        "models": {
            "embedding": "doubao-embedding-vision-251215",
            "chat_mini": "doubao-seed-2-0-mini-260215",
            "chat_lite": "doubao-seed-2-0-lite-260215",
            "chat_code": "doubao-seed-2-0-code-preview-260215",
            "image": "doubao-seedream-5-0-260128",
        },
        "dimensions": [1024, 2048],
        "default_dim": 1024,
    },
    "openai": {
        "name": "OpenAI 兼容 (OpenAI / DeepSeek / 本地)",
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "auth": lambda: f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
        "models": {
            "embedding": os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            "chat_mini": os.getenv("OPENAI_CHAT_MINI", "gpt-4o-mini"),
            "chat_lite": os.getenv("OPENAI_CHAT_LITE", "gpt-4o"),
            "chat_code": os.getenv("OPENAI_CHAT_CODE", "gpt-4o"),
        },
        "dimensions": [512, 1536],
        "default_dim": 1536,
    },
}

# ── 当前激活的后端 ──
ACTIVE_BACKEND = os.getenv("MODEL_BACKEND", "ark")


def get_backend(name: Optional[str] = None) -> dict:
    """获取模型后端配置"""
    backend = MODEL_BACKENDS.get(name or ACTIVE_BACKEND)
    if not backend:
        raise ValueError(f"未知模型后端: {name or ACTIVE_BACKEND}. 可用: {list(MODEL_BACKENDS.keys())}")
    return backend


def get_model(model_type: str, backend_name: Optional[str] = None) -> str:
    """
    获取指定类型的模型名
    
    model_type: embedding / chat_mini / chat_lite / chat_code / image
    """
    backend = get_backend(backend_name)
    model = backend["models"].get(model_type)
    if not model:
        raise ValueError(f"后端 {backend['name']} 不支持 {model_type}")
    return model


def list_backends() -> list:
    """列出所有可用后端"""
    return [
        {"id": k, "name": v["name"], "dimensions": v["dimensions"]}
        for k, v in MODEL_BACKENDS.items()
    ]


# ── Reranker (Tier 1.5) — 基于Embedding相似度 ──
# 白皮书定义的三重召回需要reranker。豆包没有独立reranker API。
# 我们用embedding cosine similarity做轻量替代。
def rerank_by_similarity(query_embedding: list, documents: list, 
                         doc_embeddings: list, top_k: int = 5) -> list:
    """
    基于余弦相似度的轻量reranker
    
    Args:
        query_embedding: 查询向量
        documents: 文档列表
        doc_embeddings: 文档向量列表 (与documents同序)
        top_k: 返回前N条
    
    Returns:
        重排后的文档列表
    """
    import numpy as np
    
    q = np.array(query_embedding)
    scores = []
    for i, emb in enumerate(doc_embeddings):
        d = np.array(emb)
        sim = np.dot(q, d) / (np.linalg.norm(q) * np.linalg.norm(d) + 1e-8)
        scores.append((i, float(sim)))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return [documents[i] for i, _ in scores[:top_k]]
