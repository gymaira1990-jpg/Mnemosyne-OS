"""
Mnemosyne v5.0 — LLM 模型路由引擎
白皮书 L3 算力调度层: 五级模型梯队 + 自动升降级

Tier 1: doubao-embedding-vision   → 向量化 (embedding.py)
Tier 2: doubao-seed-2-0-mini      → 快速摘要/分类
Tier 3: doubao-seed-2-0-lite      → 蒸馏/方案推演 (主力, 支持 JSON mode)
Tier 4: deepseek-v4-pro           → 矛盾检测/异构审计 (Hermes 当前模型)
Tier 5: doubao-seedream           → 可视化素材 (image gen)
"""
import urllib.request
import json
import re
import sys, os
from typing import Dict, Optional

# 兼容包导入和脚本导入
try:
    from .config import (
        ARK_API_KEY, ARK_BASE,
        DOUBAO_MINI, DOUBAO_LITE, DOUBAO_CODE,
        TMT_MAX_RETRIES,
    )
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import (
        ARK_API_KEY, ARK_BASE,
        DOUBAO_MINI, DOUBAO_LITE, DOUBAO_CODE,
        TMT_MAX_RETRIES,
    )


# ── 简易缓存 (避免重复调用) ──
_cache: Dict[str, dict] = {}


def _call_ark(messages: list, model: str, max_tokens: int = 500,
              response_format: Optional[dict] = None) -> dict:
    """
    调用火山引擎 ARK Chat API
    
    Returns:
        {"content": str, "tokens": int, "model": str}
    """
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    
    req = urllib.request.Request(
        f"{ARK_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {ARK_API_KEY}'
        }
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
        return {
            "content": data['choices'][0]['message']['content'],
            "tokens": data['usage']['total_tokens'],
            "model": model,
        }


def call_llm(prompt: str, tier: str = "lite", json_mode: bool = False) -> dict:
    """
    统一 LLM 调用入口
    
    Args:
        prompt: 提示词
        tier: 模型层级 ("mini" | "lite" | "code" | "pro")
        json_mode: 是否启用 JSON 结构化输出
    
    Returns:
        {"content": str, "tokens": int, "model": str, "tier": str}
    
    自动升降级:
        tier=mini 失败 → 升到 lite
        tier=lite 失败 → 升到 code
        tier=code 失败 → 返回错误
    """
    cache_key = f"{tier}:{json_mode}:{hash(prompt)}"
    if cache_key in _cache:
        return _cache[cache_key]
    
    model_map = {
        "mini": DOUBAO_MINI,
        "lite": DOUBAO_LITE,
        "code": DOUBAO_CODE,
    }
    
    messages = [{"role": "user", "content": prompt}]
    fmt = {"type": "json_object"} if json_mode else None
    
    last_error = None
    for attempt in range(TMT_MAX_RETRIES):
        model_key = tier
        model = model_map.get(model_key, DOUBAO_LITE)
        
        try:
            result = _call_ark(messages, model, max_tokens=800, response_format=fmt)
            result["tier"] = model_key
            
            # JSON mode: 验证解析
            if json_mode:
                try:
                    content = result["content"]
                    # 提取 JSON (可能包裹在 markdown 代码块中)
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        json.loads(json_match.group())
                        result["content"] = json_match.group()
                    else:
                        json.loads(content)  # 直接试
                except json.JSONDecodeError:
                    if tier == "lite":
                        tier = "code"  # 升级
                        continue
                    result["error"] = "JSON parse failed after upgrade"
            
            _cache[cache_key] = result
            return result
            
        except Exception as e:
            last_error = e
            # 自动升级
            if tier == "mini":
                tier = "lite"
            elif tier == "lite":
                tier = "code"
            else:
                break
    
    return {
        "content": "",
        "tokens": 0,
        "model": "",
        "tier": tier,
        "error": str(last_error),
    }


def call_llm_json(prompt: str, tier: str = "lite") -> dict:
    """JSON 模式的便捷包装"""
    return call_llm(prompt, tier=tier, json_mode=True)


def call_llm_fast(prompt: str) -> dict:
    """快速模式的便捷包装 (Tier 2 mini)"""
    return call_llm(prompt, tier="mini")
