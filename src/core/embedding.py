"""
Mnemosyne v5.0 — Embedding 抽象层
主后端: 豆包 doubao-embedding-vision-251215 (ARK API)
维度: 1024 (用户确认)
"""
import urllib.request
import json
import asyncio
import functools
import sys, os
from typing import List

# 兼容包导入和脚本导入
try:
    from .config import ARK_API_KEY, EMBED_MODEL, EMBED_DIM, EMBED_URL
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import ARK_API_KEY, EMBED_MODEL, EMBED_DIM, EMBED_URL


def get_embedding(texts: List[str]) -> List[List[float]]:
    """
    同步版本 — 用于 run_in_executor 调用
    
    Args:
        texts: 文本列表
        
    Returns:
        embeddings: 向量列表，每个 1024 维
    
    Raises:
        RuntimeError: API 调用失败
    """
    embeddings = []
    for text in texts:
        payload = json.dumps({
            "model": EMBED_MODEL,
            "input": [{"type": "text", "text": text}],
            "dimensions": EMBED_DIM,
        }).encode()
        
        req = urllib.request.Request(
            EMBED_URL,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {ARK_API_KEY}'
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            emb = data['data']['embedding']  # dict, not list!
            embeddings.append(emb)
    
    return embeddings


async def get_embedding_async(texts: List[str]) -> List[List[float]]:
    """
    异步版本 — 通过 run_in_executor 避免阻塞 uvicorn 事件循环
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, functools.partial(get_embedding, texts)
    )


def get_embedding_single(text: str) -> List[float]:
    """单个文本的便捷包装"""
    return get_embedding([text])[0]
