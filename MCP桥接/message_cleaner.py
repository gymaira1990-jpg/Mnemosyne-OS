"""消息清理 + 临时检测 — 存储前过滤无用内容和上下文注入。

参考：Supermemory (_is_trivial_message, 消息清理)
用途：存储到 Mnemosyne 前剥离 Hermes 自身注入的标签，过滤无意义消息
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── 需要剥离的上下文注入标签 ──

_CONTEXT_INJECTION_PATTERNS = [
    # Mnemosyne 自身注入的关联记忆块（到 --- 或空行为止）
    r"## Mnemosyne 关联记忆[\s\S]*?(?:\n---|\n\n)",
    r"## 关联记忆[\s\S]*?(?:\n---|\n\n)",
    # Hermes 系统上下文标记（成对标签）
    r"<hermes-context>[\s\S]*?</hermes-context>",
    r"<memory-context>[\s\S]*?</memory-context>",
    # 系统反馈/摘要标记行
    r"\[SYSTEM\].*?(?:\n|$)",
]

# 预编译正则
_CONTEXT_RE = re.compile(
    "|".join(_CONTEXT_INJECTION_PATTERNS),
    re.DOTALL | re.IGNORECASE,
)

# ── 临时消息检测 ──

_MIN_CONTENT_LENGTH = 5

_TRIVIAL_PATTERNS = [
    # 纯符号/数字
    r"^[\s\d\.,!?。，！？、\-—……~～·@#\$%\^&\*\(\)\[\]{}:;\"'《》【】]+$",
    # 纯 emoji
    r"^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF"
    r"\uFE00-\uFE0F\u200D]+$",
    # 单个词重复 (如 "哈哈哈" "好的好的" "嗯嗯")
    r"^(.{1,4})\1{2,}$",
    # 纯空格/空字符串
    r"^\s*$",
]

_TRIVIAL_RE = re.compile("|".join(_TRIVIAL_PATTERNS))


def clean_content(content: str) -> str:
    """剥离上下文注入标签，返回纯净内容"""
    if not content:
        return ""

    cleaned = _CONTEXT_RE.sub("", content).strip()

    # 如果清理后为空，返回空
    if not cleaned:
        return ""

    return cleaned


def is_trivial(content: str, min_length: int = _MIN_CONTENT_LENGTH) -> bool:
    """判断是否为无意义消息"""
    if not content:
        return True

    # 长度过短
    if len(content) < min_length:
        return True

    # 匹配无意义模式
    if _TRIVIAL_RE.match(content):
        return True

    return False


def prepare_for_storage(content: str, min_length: int = _MIN_CONTENT_LENGTH) -> str:
    """完整的预存储处理：清理 + 过滤，返回存储就绪内容（空字符串表示应跳过）"""
    cleaned = clean_content(content)
    if not cleaned:
        return ""

    if is_trivial(cleaned, min_length):
        logger.debug("跳过消息（临时）：%s", cleaned[:30])
        return ""

    return cleaned
