"""
Mnemosyne v5.0 — LLM 路由引擎
支持任何 OpenAI 兼容 API 的分级调度

推荐组合:
  Tier 2 (快速) → 豆包 Seed-2.0 Mini / gpt-4o-mini
  Tier 3 (主力) → 豆包 Seed-2.0 Lite (JSON mode) / gpt-4o
  Tier 4 (深度) → DeepSeek V4 Pro / o1-mini

换模型只需改环境变量: LLM_MODEL_MINI / LLM_MODEL_LITE / LLM_MODEL_PRO
"""
import urllib.request
import json
import re
import sys, os
import time
from typing import Dict, Optional, List

try:
    from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_MINI, LLM_MODEL_LITE, LLM_MODEL_PRO
    from .config import LLM_BASE_URL_PRO, LLM_API_KEY_PRO, TMT_MAX_RETRIES
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_MINI, LLM_MODEL_LITE, LLM_MODEL_PRO
    from config import LLM_BASE_URL_PRO, LLM_API_KEY_PRO, TMT_MAX_RETRIES

# ── 模型梯队 — 从环境变量读取，可自由替换 ──
TIERS = {
    1: {"model": "embedding", "type": "embedding"},
    2: {"model": LLM_MODEL_MINI, "type": "chat", "max_tokens": 500},
    3: {"model": LLM_MODEL_LITE, "type": "chat", "max_tokens": 800},
    4: {"model": LLM_MODEL_PRO, "type": "chat", "max_tokens": 1024,
        "base_url": LLM_BASE_URL_PRO, "api_key": LLM_API_KEY_PRO},
}

_cost_stats: Dict[str, dict] = {}
_cache: Dict[str, dict] = {}
_embed_cache: Dict[str, List[float]] = {}
MAX_CACHE = 500


def _call_api(messages: list, model: str, max_tokens: int = 500,
              response_format: Optional[dict] = None, temperature: float = 0.3,
              base_url: str = None, api_key: str = None) -> dict:
    """通用 OpenAI 兼容 API 调用"""
    url = f"{base_url or LLM_BASE_URL}/chat/completions"
    key = api_key or LLM_API_KEY
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'}
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
    """分级路由 + 自动升降级 + 缓存"""
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
            result = _call_api(
                messages, tinfo["model"],
                tinfo.get("max_tokens", 800),
                response_format=fmt, temperature=temperature,
                base_url=tinfo.get("base_url"),
                api_key=tinfo.get("api_key"),
            )
            elapsed = time.time() - t0
            
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
            
            final = {
                "content": result["content"],
                "tokens": result["tokens"],
                "model": tinfo["model"],
                "tier": current_tier,
                "cache_hit": False,
                "latency_ms": round(elapsed * 1000),
                "upgraded": current_tier > tier,
            }
            
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
        "content": "", "tokens": 0, "model": "", "tier": 0,
        "cache_hit": False, "latency_ms": 0, "upgraded": False,
        "error": str(last_error),
    }


def call_llm_json(prompt: str, tier: int = 3) -> dict:
    return call_llm(prompt, tier=tier, json_mode=True)


def call_llm_fast(prompt: str) -> dict:
    return call_llm(prompt, tier=2)


def get_cost_stats() -> dict:
    return {"by_tier": _cost_stats, "total_cost": 0, "currency": "CNY (estimated)"}


def get_cache_stats() -> dict:
    return {"llm_cache_size": len(_cache), "llm_cache_max": MAX_CACHE}


def get_embed_cached(text: str) -> Optional[List[float]]:
    return _embed_cache.get(text)


def set_embed_cached(text: str, embedding: List[float]):
    if len(_embed_cache) >= MAX_CACHE:
        _embed_cache.pop(next(iter(_embed_cache)))
    _embed_cache[text] = embedding
