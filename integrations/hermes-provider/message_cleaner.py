"""消息清理 + 临时检测 — 存储前过滤无用内容和上下文注入。

参考：Supermemory (_is_trivial_message, 消息清理)
用途：存储到 Mnemosyne 前剥离 Hermes 自身注入的标签，过滤无意义消息

v1.1 升级 (0706): 中文确认语过滤 + 工具调用JSON过滤 + 信息密度检测
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── 需要剥离的上下文注入标签 ──

_CONTEXT_INJECTION_PATTERNS = [
    r"## Mnemosyne 关联记忆[\s\S]*?(?:\n---|\n\n)",
    r"## 关联记忆[\s\S]*?(?:\n---|\n\n)",
    r"<hermes-context>[\s\S]*?</hermes-context>",
    r"<memory-context>[\s\S]*?</memory-context>",
    r"\[SYSTEM\].*?(?:\n|$)",
]

_CONTEXT_RE = re.compile(
    "|".join(_CONTEXT_INJECTION_PATTERNS),
    re.DOTALL | re.IGNORECASE,
)

# ── 临时消息检测 ──

_MIN_CONTENT_LENGTH = 5

_TRIVIAL_PATTERNS = [
    r"^[\s\d\.,!?。，！？、\-—……~～·@#\$%\^&\*\(\)\[\]{}:;\"'《》【】]+$",
    r"^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF"
    r"\uFE00-\uFE0F\u200D]+$",
    r"^(.{1,4})\1{2,}$",
    r"^\s*$",
    # v1.1: 中文确认语
    r"^(好的|收到|明白|了解|懂了|知道了|行|好|嗯|哦|噢|OK|ok|OKAY|okay)[\s!！。.]*$",
    r"^(明白了|了解了|收到了|好的好的|行吧|好吧|可以|没问题)[\s!！。.]*$",
    # v1.1: 纯动作确认
    r"^(已(完成|处理|执行|修复|更新|删除|添加|创建|保存|记录))[\s!！。.]*$",
    # v1.1: 纯JSON工具结果
    r"^\s*\{\s*\".*\}\s*$",
    # v1.1: 极低信息密度
    r"^[^a-zA-Z\u4e00-\u9fff]{0,3}$",
]

_TRIVIAL_RE = re.compile("|".join(_TRIVIAL_PATTERNS))

# ── v1.1: 内容有效密度 ──

def _content_density(content: str) -> float:
    """中文+英文+数字占内容长度的比例"""
    if not content:
        return 0.0
    meaningful = sum(1 for c in content if (
        '\u4e00' <= c <= '\u9fff' or c.isalpha() or c.isdigit()
    ))
    return meaningful / len(content)


def clean_content(content: str) -> str:
    """剥离上下文注入标签"""
    if not content:
        return ""
    cleaned = _CONTEXT_RE.sub("", content).strip()
    return cleaned


def is_trivial(content: str, min_length: int = _MIN_CONTENT_LENGTH) -> bool:
    """判断是否为无意义消息"""
    if not content:
        return True
    if len(content) < min_length:
        return True
    if _TRIVIAL_RE.match(content):
        return True
    # v1.1: 长内容但有效密度 < 30% → 乱码/噪音
    if len(content) >= 10 and _content_density(content) < 0.3:
        return True
    return False


def prepare_for_storage(content: str, min_length: int = _MIN_CONTENT_LENGTH) -> str:
    """预存储处理：清理 + 过滤"""
    cleaned = clean_content(content)
    if not cleaned:
        return ""
    if is_trivial(cleaned, min_length):
        logger.debug("跳过临时消息：%s", cleaned[:30])
        return ""
    return cleaned
