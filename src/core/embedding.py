"""
Mnemosyne v5.0 — Embedding 抽象层
支持任何 OpenAI 兼容 Embedding API
默认: 豆包 Embedding-Vision 1024d (推荐)
也可用: OpenAI text-embedding-3 / 本地 Ollama / vLLM
"""
import urllib.request
import json
import asyncio
import functools
import sys, os
from typing import List

try:
    from .config import EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_ENDPOINT
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_ENDPOINT


def get_embedding(texts: List[str]) -> List[List[float]]:
    """
    同步版本 — 用于 run_in_executor 调用
    
    返回: 向量列表，每个 EMBEDDING_DIM 维
    
    换模型只需改环境变量:
      EMBEDDING_MODEL=your-model
      EMBEDDING_BASE_URL=https://your-api.com/v1
    """
    embeddings = []
    for text in texts:
        payload = json.dumps({
            "model": EMBEDDING_MODEL,
            "input": [{"type": "text", "text": text}],
            "dimensions": EMBEDDING_DIM,
        }).encode()
        
        req = urllib.request.Request(
            EMBEDDING_ENDPOINT,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {EMBEDDING_API_KEY}'
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            emb = data['data']['embedding']
            embeddings.append(emb)
    
    return embeddings


async def get_embedding_async(texts: List[str]) -> List[List[float]]:
    """异步版本 — FastAPI 路由使用"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(get_embedding, texts))
