"""
Mnemosyne v5.0 — Embedding 抽象层
支持任何 OpenAI 兼容 Embedding API
默认: 豆包 Embedding-Vision 1024d (推荐, 中文好)
也可: text-embedding-3 / 本地 Ollama / vLLM

换模型只需改环境变量:
  EMBEDDING_MODEL=your-model
  EMBEDDING_BASE_URL=https://your-api.com/v1
"""
import urllib.request, json, asyncio, functools, sys, os
from typing import List

try:
    from .config import EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_ENDPOINT
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import EMBEDDING_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM, EMBEDDING_ENDPOINT


def get_embedding(texts: List[str]) -> List[List[float]]:
    """同步版本 — run_in_executor 用"""
    embeddings = []
    for text in texts:
        payload = json.dumps({
            "model": EMBEDDING_MODEL,
            "input": [{"type": "text", "text": text}],
            "dimensions": EMBEDDING_DIM,
        }).encode()
        req = urllib.request.Request(
            EMBEDDING_ENDPOINT, data=payload,
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {EMBEDDING_API_KEY}'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            embeddings.append(data['data']['embedding'])
    return embeddings


async def get_embedding_async(texts: List[str]) -> List[List[float]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(get_embedding, texts))
