"""
Mnemosyne v5.0 — 模型路由引擎 v2.0
白皮书 L3 算力调度层完整实现

Tier 1: doubao-embedding-vision   → 向量化 (128 tokens/条, ¥0.0001)
Tier 2: doubao-seed-2-0-mini      → 快速分类/摘要 (¥0.001/1K tokens)
Tier 3: doubao-seed-2-0-lite      → 蒸馏主力 JSON mode (¥0.003/1K tokens)
Tier 4: deepseek-v4-pro           → 异构审计/矛盾检测 (¥0.015/1K tokens)
Tier 5: doubao-seedream           → 可视化素材 (按图计费)
"""
import urllib.request
import json
import re
import sys, os
import time
from typing import Dict, Optional, List

# 兼容导入
try:
    from .config import ARK_API_KEY, ARK_BASE, DOUBAO_MINI, DOUBAO_LITE, DOUBAO_CODE, TMT_MAX_RETRIES
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import ARK_API_KEY, ARK_BASE, DOUBAO_MINI, DOUBAO_LITE, DOUBAO_CODE, TMT_MAX_RETRIES

# ── 模型梯队定义 ──
TIERS = {
    1: {"model": "doubao-embedding-vision-251215", "type": "embedding", "cost_per_1k": 0.0001},
    2: {"model": DOUBAO_MINI, "type": "chat", "cost_per_1k": 0.001, "max_tokens": 500},
    3: {"model": DOUBAO_LITE, "type": "chat", "cost_per_1k": 0.003, "max_tokens": 800},
    4: {"model": DOUBAO_CODE, "type": "chat", "cost_per_1k": 0.006, "max_tokens": 1024},
    5: {"model": "doubao-seedream-5-0-260128", "type": "image", "cost_per_image": 0.02},
}

# ── 成本统计 ──
_cost_stats: Dict[str, dict] = {}  # {tier: {calls, tokens, cost}}

# ── 双层语义缓存 ──
_cache: Dict[str, dict] = {}
_embed_cache: Dict[str, List[float]] = {}
MAX_CACHE = 500


def _call_ark(messages: list, model: str, max_tokens: int = 500,
              response_format: Optional[dict] = None, temperature: float = 0.3) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    
    req = urllib.request.Request(
        f"{ARK_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {ARK_API_KEY}'}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        return {
            "content": data['choices'][0]['message']['content'],
            "tokens": data['usage']['total_tokens'],
            "model": model,
        }


def call_llm(prompt: str, tier: int = 3, json_mode: bool = False, 
             temperature: float = 0.3, no_cache: bool = False) -> dict:
    """
    分级路由 + 自动升降级 + 缓存
    
    Args:
        prompt: 提示词
        tier: 初始层级 2-4 (2=mini, 3=lite, 4=code)
        json_mode: JSON 结构化输出
        temperature: 温度 (仅 Tier 2-4)
        no_cache: 跳过缓存
    
    Returns:
        {"content": str, "tokens": int, "model": str, "tier": int, "cost": float, "cache_hit": bool}
    """
    # 缓存检查
    cache_key = f"t{tier}:j{json_mode}:t{temperature}:{hash(prompt)}"
    if not no_cache and cache_key in _cache:
        result = _cache[cache_key].copy()
        result["cache_hit"] = True
        return result
    
    messages = [{"role": "user", "content": prompt}]
    fmt = {"type": "json_object"} if json_mode else None
    
    current_tier = tier
    last_error = None
    
    for attempt in range(TMT_MAX_RETRIES):
        tinfo = TIERS.get(current_tier, TIERS[3])
        
        try:
            t0 = time.time()
            result = _call_ark(messages, tinfo["model"], 
                              tinfo.get("max_tokens", 800), 
                              response_format=fmt, temperature=temperature)
            elapsed = time.time() - t0
            
            # JSON 验证
            if json_mode:
                try:
                    content = result["content"]
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        json.loads(json_match.group())
                        result["content"] = json_match.group()
                    else:
                        json.loads(content)
                except json.JSONDecodeError:
                    if current_tier < 4:
                        current_tier += 1
                        continue
                    result["content"] = "{}"
            
            # 成本核算
            cost = (result["tokens"] / 1000) * tinfo["cost_per_1k"]
            
            final = {
                "content": result["content"],
                "tokens": result["tokens"],
                "model": tinfo["model"],
                "tier": current_tier,
                "cost": round(cost, 6),
                "cache_hit": False,
                "latency_ms": round(elapsed * 1000),
                "upgraded": current_tier > tier,
            }
            
            # 成本统计
            tk = str(current_tier)
            if tk not in _cost_stats:
                _cost_stats[tk] = {"calls": 0, "tokens": 0, "cost": 0.0}
            _cost_stats[tk]["calls"] += 1
            _cost_stats[tk]["tokens"] += result["tokens"]
            _cost_stats[tk]["cost"] += cost
            
            # 缓存
            if len(_cache) >= MAX_CACHE:
                _cache.pop(next(iter(_cache)))
            _cache[cache_key] = final
            
            return final
            
        except Exception as e:
            last_error = e
            if current_tier < 4:
                current_tier += 1
            else:
                break
    
    return {
        "content": "",
        "tokens": 0,
        "model": "",
        "tier": 0,
        "cost": 0,
        "cache_hit": False,
        "latency_ms": 0,
        "upgraded": False,
        "error": str(last_error),
    }


def call_llm_json(prompt: str, tier: int = 3) -> dict:
    """JSON 模式便捷包装"""
    return call_llm(prompt, tier=tier, json_mode=True)


def call_llm_fast(prompt: str) -> dict:
    """Tier 2 快速模式"""
    return call_llm(prompt, tier=2)


def get_cost_stats() -> dict:
    """获取成本统计"""
    total = sum(s["cost"] for s in _cost_stats.values())
    return {
        "by_tier": _cost_stats,
        "total_cost": round(total, 6),
        "currency": "CNY (estimated)",
    }


def get_cache_stats() -> dict:
    """获取缓存统计"""
    return {
        "llm_cache_size": len(_cache),
        "llm_cache_max": MAX_CACHE,
        "embed_cache_size": len(_embed_cache),
    }


def get_embed_cached(text: str) -> Optional[List[float]]:
    """获取缓存的向量"""
    return _embed_cache.get(text)


def set_embed_cached(text: str, embedding: List[float]):
    """缓存向量"""
    if len(_embed_cache) >= MAX_CACHE:
        _embed_cache.pop(next(iter(_embed_cache)))
    _embed_cache[text] = embedding
