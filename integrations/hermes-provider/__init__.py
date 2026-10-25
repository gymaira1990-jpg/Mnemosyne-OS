"""
Mnemosyne Memory Provider — 替换 OpenViking，使用自研记忆宫殿。

Provider v1.1.0 (2026-07-29)
  - v1.0.0: 初始版本，全量 sync_turn + 热点记忆 + prefetch
  - v1.1.0: 写过滤(低价值消息跳过) + 首轮冷启动 + 格式优化(cat_emoji)
  - Mnemosyne 依赖: v5.5.1+ (GZ 服务器)
  - 兼容: Hermes v0.19.0+

通过 SSH 隧道连接到 GZ 服务器上的 Mnemosyne REST API (localhost:18010)。
提供全量记忆存储、语义检索、TMT 层级蒸馏和热度管理。

配置 (profile-scoped .env):
  MNEMOSYNE_ENDPOINT — API 地址 (default: http://127.0.0.1:18010)
  MNEMOSYNE_USER_ID — 用户 ID (default: default)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from agent.memory_provider import MemoryProvider, spawn_context_thread
from tools.registry import tool_error

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "http://127.0.0.1:18010"
_DEFAULT_USER_ID = "default"
_API_TIMEOUT = 15.0
# recall 含 GZ 端 LLM 蒸馏(实测 13s+)，单独放宽超时，防偶发超时被误判为空结果
_RECALL_TIMEOUT = 60.0
# ── 自回声过滤 (2026-10-07, T-0327①) ──────────────────────────────
# 实测: 本会话自己的发言会被 sync_turn 存成 L2/session 条, 下一轮又被 prefetch
#      语义检索捞回来注入 prompt ⇒ **自己的话当"记忆"回灌**: 每轮成本上升 +
#      模型可能把自己的输出当外部事实 (实测本会话 28788/28789 两条已出现在注入块里)。
# 修法: 注入前过滤「本会话内产生」与「近 _ECHO_RECENT_HOURS 的 session/worklog 碎片」。
# 字段来源: /memories/search 返回 id/category/content/created_at/heat_score/tier/reliability/access_count。
_ECHO_CATEGORIES = ("session", "worklog")
_ECHO_RECENT_HOURS = 2.0


def _session_start(session_id: str):
    """从会话 ID 解析开始时刻。ID 形如 20261007_211449_b0fb01(YYYYMMDD_HHMMSS_xxxx)。

    ⚠️ 会话 ID 是**本机本地时间**(CST), 而 created_at 是 UTC ⇒ 必须 `.astimezone()`
    附上本地时区再比较; 若误当 UTC, 过滤条件恒不成立 = 静默失效(修了等于没修)。
    """
    if not session_id:
        return None
    try:
        from datetime import datetime
        parts = str(session_id).split("_")
        if len(parts) < 2 or len(parts[0]) != 8 or len(parts[1]) < 6:
            return None
        naive = datetime.strptime(parts[0] + parts[1][:6], "%Y%m%d%H%M%S")
        return naive.astimezone()          # 附本地时区 → 可跨时区比较
    except Exception:
        return None


def _parse_dt(v):
    """解析 ISO 时间字符串为 aware datetime(缺时区按 UTC)。失败返回 None。"""
    if not v:
        return None
    try:
        from datetime import datetime, timezone
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_self_echo(mem, session_id: str = "", *, now=None) -> bool:
    """True = 该条属于「自回声/近期会话碎片」, 不该注入上下文。"""
    if not isinstance(mem, dict):
        return False
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    created = _parse_dt(mem.get("created_at"))
    if created is None:
        return False                      # 无时间戳 ⇒ 不误杀(保守)
    start = _session_start(session_id)
    if start is not None and created >= start:
        return True                       # ① 本会话内产生 = 自回声
    cat = str(mem.get("category", "") or "").lower()
    if cat in _ECHO_CATEGORIES and created >= now - timedelta(hours=_ECHO_RECENT_HOURS):
        return True                       # ② 近 2h 的会话/日志碎片
    return False


# ── 碎片降权 (2026-10-13, T-0327②) ────────────────────────────────
# 实测: 库内 session+worklog 占 ~21.6%, 而 prefetch 每轮只取 top-N ⇒ 与真知识条目
#       争注入位。① 只滤「本会话 / 近 2h」, **存量旧碎片仍在**。
# 修法: **降权不删**（历史价值仍在，只是不该压过知识条）—— 排序时 session/worklog ×0.5。
#       只改「注入什么顺序」，不改库内容；稳定排序（同分保原顺序，不抖动）。
_FRAGMENT_WEIGHT = {"session": 0.5, "worklog": 0.5}


def _rank_by_category(memories: list) -> list:
    """按类别降权后重排（T-0327②）。碎片 ×0.5，其余权重 1.0；非 dict 项排后。"""
    def _key(item):
        i, m = item
        heat, cat = 0.0, ""
        if isinstance(m, dict):
            try:
                heat = float(m.get("heat_score", m.get("score", 0)) or 0)
            except (TypeError, ValueError):
                heat = 0.0
            cat = str(m.get("category", "") or "").lower()
        return (-(heat * _FRAGMENT_WEIGHT.get(cat, 1.0)), i)
    return [m for _, m in sorted(enumerate(memories), key=_key)]
# ── 会话边界收尾 (2026-09-28, T-0221) ─────────────────────────────
# 实测: /new 会先 await session.close → agent.close → shutdown_memory_provider
#      → on_session_end，所以这里同步跑多久，用户就等多久「新会话出现」。
# 两处调用都是 LLM 型慢活: L2 蒸馏实测 6.1s; palace/extract 每片约 7s
#      (batch=3→22s, batch=5→35s) ⇒ 旧的 batch=30 + 15s 客户端超时**必然超时**,
#      等于每次会话结束白等 15s 且事实提取从未成功。
# 修法: 整体丢后台(spawn_context_thread) + 提取用小批次 + 放宽超时。
_SESSION_END_SYNC_JOIN = 1.0        # 写队列是 sqlite 持久化的, 会话边界不必等它排空
_PALACE_EXTRACT_BATCH = 5           # 每片约 7s; 30 在客户端超时内跑不完
_PALACE_EXTRACT_TIMEOUT = 90.0      # 后台执行, 不再受 _API_TIMEOUT(15s) 拖累
# ⚠️ 2026-09-28 (T-0223): 事实提取**默认不再在会话边界跑**（改成 True 可恢复旧行为）。
#    理由（取证）: GZ 侧每天 02:00 已有 `tmt/factextract.py --batch 60`，而本调用走的是
#    **同一候选集合同一套逻辑** —— palace.extract_facts_pipeline() 内部直接 `from tmt import
#    factextract` 复用 find_candidates(metadata->>'fact_extracted' IS NULL, category in
#    session/worklog, length>=80, oldest-first)。⇒ 会话边界再跑一次是重复劳动（每片约 7s 的
#    LLM 活），而且每次会话结束都占 GZ 一个 LLM 时段。
#    裕量判据（2026-09-28 实测）: 待提取积压 23 条 < 日额度 60 ⇒ 日批处理追得上；此判据失效
#    （积压长期接近/超过 60）时再恢复本开关或调大 GZ 的 --batch。
_SESSION_END_FACT_EXTRACT = False
# 幂等检索类 POST 路径：连接/超时错误可安全重试（写入类绝不重试，防重复写入）
_RETRYABLE_POST = {
    "/memories/search",
    "/memories/search-chunks",
    "/memories/tree",
    "/memories/stats",
    "/memories/chunks/stats",
    "/memories/heat-top",
    "/memories/conflicts",
    "/tmt/recall",
    "/tmt/recall/simple",
    "/tmt/tree",
    "/dialectic",
    "/graph/search",
    "/beliefs/search",
    "/halls/stats",
    "/projects/",
}
_HEADER_API_KEY = "X-API-Key"

# ── 工具 Schemas ─────────────────────────────────────────

SEARCH_SCHEMA = {
    "name": "mnemosyne_search",
    "description": "四维搜索 Mnemosyne 记忆宫殿（语义+关键词+热度+图谱）。返回最匹配的历史记忆。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "user_id": {"type": "string", "description": "用户 ID（默认当前用户）"},
            "limit": {"type": "integer", "description": "返回条数", "default": 5},
            "category": {"type": "string", "description": "按分类过滤"},
        },
        "required": ["query"],
    },
}

REMEMBER_SCHEMA = {
    "name": "mnemosyne_remember",
    "description": "主动存储一条重要记忆到 Mnemosyne 记忆宫殿。自动加入语义索引和热度体系。",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容"},
            "category": {
                "type": "string",
                "enum": ["fact", "experience", "belief", "chat", "work", "note", "test"],
                "description": "记忆分类",
                "default": "fact",
            },
            "importance": {"type": "number", "description": "重要性 0-1", "default": 0.5},
        },
        "required": ["content"],
    },
}

RECALL_SCHEMA = {
    "name": "mnemosyne_recall",
    "description": "TMT 智能召回：跨层级（L1→L3）综合检索记忆宫殿。比 search 更深入，包含会话蒸馏和每日摘要。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索内容"},
            "max_results": {"type": "integer", "description": "最大返回条数", "default": 5},
        },
        "required": ["query"],
    },
}

TREE_SCHEMA = {
    "name": "mnemosyne_tree",
    "description": "浏览 TMT 记忆树结构：L1碎片/L2会话/L3每日/L4每周/L5画像，快速了解记忆体系全貌。",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

HOT_SCHEMA = {
    "name": "mnemosyne_hot_memories",
    "description": "获取当前热度最高的记忆。快速了解近期最重要的信息。",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "返回条数", "default": 5},
            "min_heat": {"type": "number", "description": "最低热度阈值", "default": 0.3},
        },
    },
}

PALACE_SUMMON_SCHEMA = {
    "name": "mnemosyne_palace_summon",
    "description": "魔法记忆宫殿三通道召唤：①点名(档号/题名/标签精确命中) ②引导(分类树缩小范围) ③共鸣(向量语义兜底)。用于精确查询配置/密钥/路径/项目时，比语义搜索更准更快。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "查询内容(档号/标签/题名/关键词)"},
            "user_id": {"type": "string", "description": "用户 ID（默认当前用户）"},
            "top_k": {"type": "integer", "description": "返回条数", "default": 5},
        },
        "required": ["query"],
    },
}

DIALECTIC_SCHEMA = {
    "name": "mnemosyne_dialectic",
    "description": "辨证推理：搜索记忆并附带L2/L3会话上下文，返回结构化记忆树以便LLM综合分析。比search更深入，包含时序关系。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回条数", "default": 3},
        },
        "required": ["query"],
    },
}

TIERED_READ_SCHEMA = {
    "name": "mnemosyne_tiered_read",
    "description": "三级读取记忆：L5摘要(200字)/L3概览(800字+会话摘要)/L1全文(关联片段+每日摘要)。比直接查更智能分级。",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "integer", "description": "记忆ID"},
            "level": {"type": "string", "description": "读取级别: L5/L3/L1", "default": "L3"},
        },
        "required": ["memory_id"],
    },
}

CONFLICT_SCHEMA = {
    "name": "mnemosyne_conflicts",
    "description": "查看存在矛盾/冲突的记忆列表。检测到矛盾时会自动标记旧记忆为过期并存证。",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "返回条数", "default": 10},
        },
    },
}

WIKI_SCHEMA = {
    "name": "mnemosyne_wiki",
    "description": "查询知识库(Wiki)页面 — 论文/文章/方案的全文快照档案馆。支持: search(语义搜索全文), get(按ID看全文), by_source(按来源路径查证), list(列表)。存了要用起来: 查论文/方案细节优先用它。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "search(语义搜索) / get(按ID查看) / by_source(按来源查证) / list(列表)", "default": "search"},
            "query": {"type": "string", "description": "search模式: 自然语言查询"},
            "page_id": {"type": "integer", "description": "get模式: 页面ID"},
            "source_path": {"type": "string", "description": "by_source模式: 源文件路径"},
            "source_url": {"type": "string", "description": "by_source模式: 源URL"},
            "top_k": {"type": "integer", "description": "search模式: 返回条数", "default": 5},
            "limit": {"type": "integer", "description": "list模式: 返回条数", "default": 10},
        },
    },
}

MEDIA_SCHEMA = {
    "name": "mnemosyne_media",
    "description": "管理媒体记忆（文件/图片/链接）。支持 list(列表), get(查看), create(创建)。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "list/get/create", "default": "list"},
            "media_id": {"type": "integer", "description": "get模式: 媒体ID"},
            "content": {"type": "string", "description": "create模式: 内容描述"},
            "media_type": {"type": "string", "description": "create模式: file/image/link", "default": "file"},
            "media_url": {"type": "string", "description": "create模式: 文件路径/URL"},
            "limit": {"type": "integer", "description": "list模式: 返回条数", "default": 10},
        },
    },
}


# ── HTTP 客户端 ──────────────────────────────────────────

def _get_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        return None


class _MnemosyneClient:
    """简易 HTTP 客户端封装 Mnemosyne REST API。"""

    def __init__(self, endpoint: str, user_id: str):
        self._endpoint = endpoint.rstrip("/")
        self._api_base = f"{self._endpoint}/api/v1"
        self._user_id = user_id
        self._httpx = _get_httpx()
        if self._httpx is None:
            raise ImportError("httpx is required: pip install httpx")
        headers = {}
        api_key = os.environ.get("MNEMOSYNE_API_KEY", "")
        if api_key:
            headers[_HEADER_API_KEY] = api_key
        self._http = self._httpx.Client(timeout=_API_TIMEOUT, headers=headers)

    def _call(self, method: str, path: str, retry: bool = True, **kwargs) -> dict:
        """统一 API 调用。连接/超时类错误对幂等检索请求自动重试 1 次。

        retry=False 或非检索类路径（写入操作）绝不重试，防重复写入。
        """
        url = f"{self._api_base}{path}"
        can_retry = retry and (
            method.upper() == "GET"
            or (method.upper() == "POST" and path in _RETRYABLE_POST)
        )
        last_error: Optional[Exception] = None
        for attempt in range(2 if can_retry else 1):
            try:
                r = self._http.request(method, url, **kwargs)
                r.raise_for_status()
                return r.json() if r.text else {}
            except Exception as e:
                last_error = e
                if attempt == 0 and can_retry:
                    logger.debug("mnemosyne %s %s failed (%s), retrying…", method, path, e)
                    time.sleep(0.5)
                    continue
        detail = ""
        if last_error is not None:
            resp = getattr(last_error, "response", None)
            if resp is not None:
                detail = getattr(resp, "text", "")[:300]
        return {"error": str(last_error) if last_error else "unknown error", "detail": detail}

    def health(self) -> bool:
        """带重试的健康检查：首包慢时给第二次机会，避免误判 service down。"""
        for attempt in range(2):
            try:
                r = self._http.get(f"{self._endpoint}/api/v1/echo", timeout=8.0)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            if attempt == 0:
                time.sleep(0.5)
        return False

    def search_memories(self, query: str, limit: int = 5, category: str = "") -> list:
        payload = {"query": query, "user_id": self._user_id, "top_k": limit}
        if category:
            payload["category"] = category
        result = self._call("POST", "/memories/search", json=payload)
        if "error" in result:
            return []
        # 不同响应格式兼容
        if isinstance(result, dict):
            return result.get("memories", result.get("results", result.get("items", [])))
        return result if isinstance(result, list) else []

    def dialectic_search(self, query: str, limit: int = 3) -> dict:
        """辨证推理：搜索+会话上下文，返回结构化记忆树。"""
        payload = {"query": query, "user_id": self._user_id, "max_memories": limit}
        result = self._call("POST", "/dialectic", json=payload)
        if "error" in result:
            return {"memories": [], "context": [], "error": result["error"]}
        return result

    def tiered_read(self, memory_id: int, level: str = "L3") -> dict:
        """三级读取：L5摘要 / L3概览 / L1全文+上下文。"""
        result = self._call("GET", f"/memories/{memory_id}/tiered",
                           params={"level": level, "user_id": self._user_id})
        if "error" in result:
            return {"error": result["error"]}
        return result

    def get_conflicts(self, limit: int = 10) -> dict:
        """查看矛盾/冲突记忆。"""
        return self._call("GET", "/memories/conflicts",
                         params={"user_id": self._user_id, "limit": limit})

    def list_wiki(self, limit: int = 10) -> list:
        return self._call("GET", "/wiki", params={"user_id": self._user_id, "limit": limit})

    def get_wiki_page(self, page_id: int) -> dict:
        return self._call("GET", f"/wiki/{page_id}")

    def search_wiki(self, query: str, top_k: int = 5) -> list:
        """语义搜索 Wiki 知识库 (v7.4: 直查 wiki_pages.embedding HNSW)"""
        return self._call("POST", "/wiki/search",
                          json={"query": query, "user_id": self._user_id, "top_k": top_k})

    def get_wiki_by_source(self, source_path: str = "", source_url: str = "") -> dict:
        """按来源精确查证快照 (v7.4 防损毁档案馆)"""
        params = {"user_id": self._user_id}
        if source_path:
            params["source_path"] = source_path
        if source_url:
            params["source_url"] = source_url
        return self._call("GET", "/wiki/by-source", params=params)

    def list_media(self, limit: int = 20, media_type: str = "") -> list:
        params = {"user_id": self._user_id, "limit": limit}
        if media_type:
            params["media_type"] = media_type
        return self._call("GET", "/media", params=params)

    def get_media(self, media_id: int) -> dict:
        return self._call("GET", f"/media/{media_id}")

    def create_media(self, content: str, media_type: str = "file",
                     media_url: str = "", media_hash: str = "") -> dict:
        return self._call("POST", "/media", params={
            "content": content, "media_type": media_type, "media_url": media_url,
            "media_hash": media_hash, "user_id": self._user_id
        })

    def store_memory(self, content: str, category: str = "fact",
                     importance: float = 0.5, source: str = "hermes") -> dict:
        payload = {
            "user_id": self._user_id,
            "content": content,
            "category": category,
            "importance": importance,
            "source": source,
        }
        return self._call("POST", "/memories", json=payload)

    def delete_memory(self, memory_id) -> dict:
        """软删一条记忆（T-0327③ 镜像 upsert 用）。写操作 ⇒ retry=False，防重复删。"""
        return self._call("DELETE", f"/memories/{memory_id}",
                          params={"user_id": self._user_id}, retry=False)

    def list_memories(self, limit: int = 10) -> list:
        result = self._call("GET", f"/memories", params={"user_id": self._user_id, "limit": limit})
        if "error" in result:
            return []
        if isinstance(result, dict):
            return result.get("items", result.get("results", []))
        return result if isinstance(result, list) else []

    def get_hot_memories(self, limit: int = 5, min_heat: float = 0.0) -> list:
        params = {"user_id": self._user_id, "limit": limit, "min_heat": min_heat}
        result = self._call("GET", "/memories/heat-top", params=params)
        if "error" in result:
            return []
        if isinstance(result, dict):
            return result.get("memories", result.get("results", result.get("items", [])))
        return result if isinstance(result, list) else []

    def get_tmt_tree(self) -> dict:
        return self._call("GET", f"/tmt/tree/{self._user_id}")

    def consolidate_session(self) -> dict:
        return self._call("POST", "/tmt/consolidate/session",
                          json={"user_id": self._user_id})

    def consolidate_daily(self) -> dict:
        return self._call("POST", "/tmt/consolidate/daily",
                          json={"user_id": self._user_id})

    def recall_simple(self, query: str) -> list:
        """快速召回（无需 LLM）。"""
        result = self._call("GET", f"/tmt/recall/simple",
                            params={"user_id": self._user_id, "q": query})
        if "error" in result:
            return self.search_memories(query)  # fallback
        if isinstance(result, dict):
            return result.get("results", result.get("memories", []))
        return result if isinstance(result, list) else []

    def recall(self, query: str, max_results: int = 5) -> dict:
        """3 阶段智能召回（含 LLM 蒸馏）。GZ 端蒸馏慢，用独立长超时。"""
        payload = {
            "user_id": self._user_id,
            "query": query,
            "max_results": max_results,
        }
        result = self._call("POST", "/tmt/recall", json=payload, timeout=_RECALL_TIMEOUT)
        return result


# ── MemoryProvider 实现 ──────────────────────────────────

class MnemosyneMemoryProvider(MemoryProvider):

    def __init__(self):
        self._client: Optional[_MnemosyneClient] = None
        self._endpoint = ""
        self._user_id = ""
        self._session_id = ""
        self._turn_count = 0
        self._sync_thread: Optional[threading.Thread] = None
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread: Optional[threading.Thread] = None
        # 会话边界收尾任务（后台）: 见 on_session_end / _run_session_end_job
        self._endjob_thread: Optional[threading.Thread] = None

    @property
    def name(self) -> str:
        return "mnemosyne"

    def is_available(self) -> bool:
        return bool(os.environ.get("MNEMOSYNE_ENDPOINT", _DEFAULT_ENDPOINT))

    def get_config_schema(self):
        return [
            {
                "key": "endpoint",
                "description": "Mnemosyne API 地址",
                "required": True,
                "default": _DEFAULT_ENDPOINT,
                "env_var": "MNEMOSYNE_ENDPOINT",
            },
            {
                "key": "user_id",
                "description": "Mnemosyne 用户 ID",
                "default": _DEFAULT_USER_ID,
                "env_var": "MNEMOSYNE_USER_ID",
            },
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        self._endpoint = os.environ.get("MNEMOSYNE_ENDPOINT", _DEFAULT_ENDPOINT)
        self._user_id = os.environ.get("MNEMOSYNE_USER_ID", _DEFAULT_USER_ID)
        self._session_id = session_id
        self._turn_count = 0
        self._hot_cache = []  # 预热缓存

        try:
            self._client = _MnemosyneClient(self._endpoint, self._user_id)
            if not self._client.health():
                logger.warning("Mnemosyne at %s not reachable", self._endpoint)
                self._client = None
            else:
                # P3-T2a: 启动预热 — 预加载热门记忆
                self._preheat_memories()
        except ImportError:
            logger.warning("httpx not installed — Mnemosyne plugin disabled")
            self._client = None

    def _preheat_memories(self) -> None:
        """启动时预加载热度最高的记忆到缓存。"""
        try:
            hot = self._client.get_hot_memories(limit=5, min_heat=0.5)
            if hot:
                self._hot_cache = [
                    {"content": m.get("content", "")[:200], "heat": m.get("heat_score", 0)}
                    for m in hot if isinstance(m, dict)
                ]
                logger.info("preheat: %d hot memories loaded", len(self._hot_cache))
        except Exception as e:
            logger.debug("preheat failed: %s", e)

    def _fetch_hot_memories(self) -> str:
        """获取热度最高且非测试的记忆，格式化内联文本。带时间衰减。"""
        try:
            from datetime import datetime, timezone
            client = _MnemosyneClient(self._endpoint, self._user_id)
            hot = client.get_hot_memories(limit=12, min_heat=0.1)
            if not hot:
                return ""
            now = datetime.now(timezone.utc)
            scored = []
            for m in hot:
                if not isinstance(m, dict):
                    continue
                content = (m.get("content", "") or "")[:150].replace("\n", " ")
                heat = m.get("heat_score", 0)
                tier = m.get("tier", "L1")
                cat = m.get("category", "?")
                m_id = m.get("id", "")
                # 跳过测试/无意义记忆
                if "测试" in content[:20] or heat < 0.1:
                    continue
                # 自回声过滤 (T-0327①): 热点兜底同样不许回灌本会话/近期碎片
                if _is_self_echo(m, self._session_id):
                    continue
                # ── 时间衰减 ──
                effective_heat = heat
                if m.get("created"):
                    try:
                        created_str = m["created"]
                        if created_str.endswith("Z"):
                            created_str = created_str[:-1] + "+00:00"
                        created = datetime.fromisoformat(created_str)
                        age_days = (now - created).total_seconds() / 86400
                        # 指数衰减: 7天半衰期，21天降到12.5%
                        if age_days > 0:
                            effective_heat = heat * (0.5 ** (age_days / 7))
                    except Exception:
                        pass
                if effective_heat < 0.15:
                    continue
                scored.append((effective_heat, heat, tier, cat, m_id, content))
            # 按有效热度排序
            scored.sort(key=lambda x: x[0], reverse=True)
            lines = []
            for eff_heat, raw_heat, tier, cat, m_id, content in scored[:3]:
                age_note = ""
                if eff_heat < raw_heat * 0.5:
                    age_note = " [衰减]"
                lines.append(f"- [{tier}|{cat}|{eff_heat:.2f}{age_note}] {content}")
            return "\n".join(lines)
        except Exception:
            return ""

    def system_prompt_block(self) -> str:
        if not self._client:
            return ""
        try:
            # v7.0 宫殿状态 (替代旧 TMT L1-L5 统计, 时间蒸馏已停用)
            palace_stats = {}
            try:
                palace_stats = self._client._call("GET", f"/palace/status?user_id={self._user_id}")
            except Exception:
                pass

            # 获取热点记忆（带衰减 + 语义相关性过滤）
            # 注意: 首轮无用户消息时不设 context_filter
            hot_block = self._fetch_hot_memories()

            # 统计概览
            try:
                stats = self._client._call("GET", f"/memories/stats?user_id={self._user_id}")
                total_mem = stats.get("total", "?")
                by_cat = stats.get("by_category", {})
                top_cats = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
                cat_str = " | ".join(f"{k}:{v}" for k, v in top_cats)
            except Exception:
                total_mem = "?"
                cat_str = "?"

            archive_coverage = palace_stats.get("archive_coverage", "?")
            tome_cards = palace_stats.get("tome_cards", "?")
            tax_count = len(palace_stats.get("taxonomy", [])) if isinstance(palace_stats.get("taxonomy"), list) else "?"

            parts = [
                f"Mnemosyne 记忆宫殿 (Endpoint: {self._endpoint})",
                f"用户: {self._user_id} | 总记忆: {total_mem} | 分类: {cat_str}",
                f"🏰 宫殿: 档案覆盖率 {archive_coverage}% | 著录卡片 {tome_cards} | 分类树 {tax_count} 节点",
            ]
            if hot_block:
                parts.append(
                    "🔥 热点记忆（跨会话汇总，时间衰减后排序。会话接续请优先用 session_search）:\n"
                    f"{hot_block}"
                )
            parts.append(
                "📌 使用 mnemosyne_search/mnemosyne_recall 检索相关记忆。\n"
                "📌 当用户聊到技术/项目/偏好等已知话题时，主动搜索记忆并引用。"
            )
            return "\n\n".join(parts)
        except Exception:
            return (
                "# Mnemosyne 记忆宫殿\n"
                f"Endpoint: {self._endpoint}\n"
                "📌 使用 mnemosyne_search/mnemosyne_recall 检索记忆。\n"
                "📌 当用户聊到已知话题时，主动搜索并引用。"
            )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """返回后台预取的结果（上下文注入用）。
        
        读优化 v1.1: 第一轮无 prefetch 时，用热点记忆填充。"""
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            # 2026-09-28 (T-0221): 3.0s → 1.5s。这行在**每次发言的回合开始**上，
            # 预取没赶上就用下面「热点记忆」兜底（原本就这么设计），不该让用户等 3 秒。
            self._prefetch_thread.join(timeout=1.5)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        if not result:
            # 首轮: 用热点记忆作为冷启动上下文
            try:
                hot = self._fetch_hot_memories()
                if hot:
                    return f"## Mnemosyne 热点记忆（冷启动）\n{hot}"
            except Exception:
                pass
            return ""
        return f"## Mnemosyne 关联记忆\n{result}"

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """后台搜索相关记忆，下轮对话注入上下文。

        对标 Honcho dialectic：复杂查询时追加辨证搜索（含 L2/L3 会话上下文）。
        """
        if not self._client or not query:
            return

        def _run():
            try:
                client = _MnemosyneClient(self._endpoint, self._user_id)
                # T-0327②: 多取候选(15) 留降权余量, 注入时仍截前 8 ⇒ 总召回量不减
                memories = client.search_memories(query, limit=15)
                if not memories:
                    memories = client.recall_simple(query)
                # 自回声过滤 (T-0327①): 剔掉本会话产生 / 近 2h 会话碎片
                if memories:
                    _n0 = len(memories)
                    memories = [m for m in memories if not _is_self_echo(m, self._session_id)]
                    if len(memories) != _n0:
                        logger.debug("prefetch: 过滤自回声/近期碎片 %d 条", _n0 - len(memories))
                    # T-0327②: 会话/日志碎片降权重排(只改注入顺序, 不改库/不删)
                    memories = _rank_by_category(memories)

                # 复杂查询（>15字）追加辨证搜索
                dialectic_context = ""
                if len(query) > 15:
                    try:
                        dialectic = client.dialectic_search(query, limit=1)
                        if dialectic and isinstance(dialectic, dict):
                            ctx = dialectic.get("context", [])
                            if ctx:
                                dialectic_parts = []
                                for c in ctx[:1]:
                                    if isinstance(c, dict):
                                        dialectic_parts.append(
                                            f"[{c.get('tier','?')}] {c.get('summary', str(c))[:120]}"
                                        )
                                if dialectic_parts:
                                    dialectic_context = " | 会话上下文: " + "; ".join(dialectic_parts)
                    except Exception:
                        pass

                if not memories:
                    return

                parts = []
                for i, mem in enumerate(memories[:8]):
                    if isinstance(mem, dict):
                        content = mem.get("content", str(mem))
                        heat = mem.get("heat_score", mem.get("score", 0))
                        tier = mem.get("tier", "L1")
                        cat = mem.get("category", "?")
                        # 双因子: 低热度(<0.3)不注入, 省 token
                        try:
                            if float(heat) < 0.3:
                                continue
                        except Exception:
                            pass
                        stars = "⭐" if heat > 0.6 else ("✦" if heat > 0.3 else "·")
                        cat_emoji = {"fact":"📌","experience":"💡","belief":"🧠","chat":"💬","work":"🔧","note":"📝"}.get(cat, "📎")
                        parts.append(f"- {stars} [{tier}|{cat_emoji}|{heat:.2f}] {content[:160]}")
                    elif isinstance(mem, str):
                        parts.append(f"- · {mem[:160]}")
                    if len(parts) >= 3:  # 预取上限 3 条, 控制注入量
                        break

                if parts:
                    result_text = "\n".join(parts)
                    if dialectic_context:
                        result_text += f"\n{dialectic_context}"
                    with self._prefetch_lock:
                        self._prefetch_result = result_text
            except Exception as e:
                logger.debug("Mnemosyne prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(
            target=_run, daemon=True, name="mnemosyne-prefetch"
        )
        self._prefetch_thread.start()

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        """每轮对话后自动存储到 Mnemosyne（经持久写队列，crash-safe）。
        
        写优化 v1.1: 过滤低价值短消息（嗯/好的/ok/继续等），减少 L1 噪音。
        """
        if not self._client:
            return

        self._turn_count += 1

        # 清理消息（剥离注入标签 + 过滤临时消息）
        from .message_cleaner import prepare_for_storage
        clean_user = prepare_for_storage(user_content) if user_content else ""
        clean_asst = prepare_for_storage(assistant_content) if assistant_content else ""

        # ── 写过滤 v1.1: 低价值短消息跳过 ──
        _LOW_VALUE_PATTERNS = [
            "嗯", "好的", "ok", "OK", "继续", "go on", "是的",
            "知道了", "明白", "试试", "来吧", "看看", "搞起",
        ]
        def _is_low_value(text: str) -> bool:
            stripped = text.strip().lower()
            if len(stripped) < 8:  # 短于8字符
                for pat in _LOW_VALUE_PATTERNS:
                    if pat.lower() in stripped:
                        return True
            return False

        if _is_low_value(clean_user) and _is_low_value(clean_asst):
            return  # 两边都是低价值，跳过整轮

        # 写入持久队列（立即 SQLite 落地，不丢数据）
        from .write_queue import get_queue
        q = get_queue()

        if clean_user and not _is_low_value(clean_user):
            q.enqueue(user_content=clean_user[:2000], assistant_content="",
                      category="session", source="hermes-sync")

        if clean_asst and not _is_low_value(clean_asst):
            q.enqueue(user_content="", assistant_content=clean_asst[:3000],
                      category="session" if len(clean_asst) > 100 else "chat",
                      source="hermes-sync")

        # 后台发送线程（从队列消费）
        def _sync():
            from .write_queue import get_queue
            q = get_queue()

            if q.is_circuit_open():
                logger.debug("Mnemosyne 熔断器 OPEN，跳过本轮发送")
                return

            try:
                client = _MnemosyneClient(self._endpoint, self._user_id)
                items = q.dequeue(batch_size=3)
                for item in items:
                    try:
                        if item["user_content"]:
                            client.store_memory(
                                content=f"用户提问: {item['user_content'][:2000]}",
                                category="session", importance=0.4, source=item["source"]
                            )
                        if item["assistant_content"]:
                            client.store_memory(
                                content=item["assistant_content"][:3000],
                                category="session" if len(item["assistant_content"]) > 100 else "chat",
                                importance=0.3, source=item["source"]
                            )
                        q.mark_done(item["id"])
                        q.record_success()
                    except Exception as e:
                        q.mark_failed(item["id"], str(e))
                        q.record_failure()
                        logger.debug("Mnemosyne 发送失败 (id=%d): %s", item["id"], e)
            except Exception as e:
                q.record_failure()
                logger.debug("Mnemosyne sync_turn client failed: %s", e)

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)

        self._sync_thread = threading.Thread(
            target=_sync, daemon=True, name="mnemosyne-sync"
        )
        self._sync_thread.start()

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """会话结束时：触发 TMT L2 蒸馏。
        (v7.8: 移除 conversation_messages 全保真同步 — Hermes state.db 已是权威会话存储,
         Mnemosyne 不再存双份; 需要会话原文走 session_search)"""
        if not self._client:
            return

        if self._turn_count == 0:
            return

        # ⚠️ 2026-09-28 (T-0221): 这里**绝不允许**同步等待。
        # /new 的链路是 `await session.close` → agent.close() → shutdown_memory_provider
        # → on_session_end，所以本方法跑多久，用户就干等多久「新会话出现」。
        # 旧实现同步跑 join(10s) + L2 蒸馏(实测 6.1s) + palace/extract(15s 超时) ⇒
        # 用户实测「卡半天」(20~31s)。现在整体丢后台。
        if self._endjob_thread and self._endjob_thread.is_alive():
            return  # 上一次收尾还在跑: 不排队、不阻塞（端点幂等, 日维度 consolidate 兜底）
        self._endjob_thread = spawn_context_thread(
            self._run_session_end_job, name="mnemosyne-session-end")
        self._endjob_thread.start()

    def _run_session_end_job(self) -> None:
        """会话边界的记忆收尾（**后台**）：等写队列 → L2 蒸馏 → 资料室事实提取。

        只做写侧收尾，不阻塞任何会话切换；失败只记日志（写队列 sqlite 持久化，
        turn 级记忆不依赖本任务）。"""
        try:
            if self._sync_thread and self._sync_thread.is_alive():
                self._sync_thread.join(timeout=_SESSION_END_SYNC_JOIN)
        except Exception:
            pass

        # ② TMT L2 蒸馏
        try:
            result = self._client.consolidate_session()
            logger.info("Mnemosyne L2 consolidation triggered (%d turns): %s",
                        self._turn_count, result.get("skipped", False))
        except Exception as e:
            logger.warning("Mnemosyne session consolidation failed: %s", e)

        # ③ 资料室事实提取 (v7.0): 本会话新写入的 session 碎片 → facts → 建档
        #    ⚠️ 2026-09-28 (T-0223): 默认关闭 —— GZ 每天 02:00 的 `tmt/factextract.py --batch 60`
        #    走的是同一候选集合、同一套逻辑（palace.extract_facts_pipeline 直接复用 tmt.factextract
        #    的 find_candidates），会话边界再跑一次属重复劳动；开关见文件头 _SESSION_END_FACT_EXTRACT。
        if _SESSION_END_FACT_EXTRACT:
            try:
                ex = self._client._call("POST", f"/palace/extract?batch={_PALACE_EXTRACT_BATCH}",
                                        json={"batch": _PALACE_EXTRACT_BATCH},
                                        timeout=_PALACE_EXTRACT_TIMEOUT)
                logger.info("Mnemosyne palace extract: processed=%s facts=%s",
                            ex.get("processed", "?"), ex.get("facts_created", "?"))
            except Exception as e:
                logger.warning("Mnemosyne palace extract failed: %s", e)

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """镜像内置 memory 工具写入到 Mnemosyne。

        v7.3 (T-0327③): 由「每次 add 无条件写新条」改为 **upsert** ——
        旧实现无关联键 ⇒ 同一条目改 N 次就堆 N+1 条镜像，召回可能捞到旧版。
        关联键来自上游 metadata["previous_content"]（被替换/删除的旧条目全文，由
        memory_manager.notify_memory_tool_write **只在写入真正落库时**提供）:
          replace/remove → 先按旧内容定位并软删旧镜像条 → 再写新条（remove 只删）。
        """
        if not self._client or action not in ("add", "replace", "remove"):
            return
        md = metadata or {}
        prev = str(md.get("previous_content") or "")
        if action != "remove" and not content:
            return

        category_map = {
            "user": "preference",
            "memory": "pattern",
        }
        category = category_map.get(target, "fact")

        def _write():
            try:
                client = _MnemosyneClient(self._endpoint, self._user_id)
                if prev:
                    # 定位旧镜像条：source 标记 + 内容全等（旧内容本身即稳定关联键）
                    for m in client.search_memories(prev[:120], limit=8, category=category):
                        if not isinstance(m, dict):
                            continue
                        if (str(m.get("content", "")).strip() == prev.strip()
                                and str(m.get("source", "")).startswith("hermes-memorytool")):
                            client.delete_memory(m.get("id"))
                            logger.debug("mnemosyne mirror: 旧条 %s 已软删 (%s)", m.get("id"), action)
                if action != "remove":
                    client.store_memory(
                        content=content,
                        category=category,
                        importance=0.6,
                        source="hermes-memorytool"
                    )
            except Exception as e:
                logger.debug("Mnemosyne memory mirror failed: %s", e)

        t = threading.Thread(target=_write, daemon=True, name="mnemosyne-memwrite")
        t.start()

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """检索工具面默认留给 MCP —— 这里返回 []（本 provider 只保留钩子能力）。

        理由（2026-09-23 实测）: MemoryProvider 的工具在
        `agent/memory_manager.py::inject_memory_provider_tools()` 里被**直接 append**
        进 `agent.tools`，该函数**不看** `tools.tool_search.defer` → 这 11 个 schema
        (5_381B ≈ 1_345 token)是**每轮常驻**成本，与「on-demand > always-on」冲突。
        MCP 侧 15 个 mnemosyne 工具覆盖同等检索能力且已是 deferred(按需加载),
        故 provider 只保留 MCP 给不了的部分: prefetch / system_prompt_block /
        on_pre_compress / on_memory_write / on_session_end / on_delegation 等钩子。
        临时把工具面放回来: export HERMES_MNEMOSYNE_PROVIDER_TOOLS=1
        """
        if os.environ.get("HERMES_MNEMOSYNE_PROVIDER_TOOLS", "").strip().lower() not in (
                "1", "true", "yes", "on"):
            return []
        return [SEARCH_SCHEMA, REMEMBER_SCHEMA, RECALL_SCHEMA, TREE_SCHEMA, HOT_SCHEMA,
                DIALECTIC_SCHEMA, TIERED_READ_SCHEMA, CONFLICT_SCHEMA, WIKI_SCHEMA, MEDIA_SCHEMA,
                PALACE_SUMMON_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        if not self._client:
            return tool_error("Mnemosyne 未连接")

        try:
            if tool_name == "mnemosyne_search":
                return self._tool_search(args)
            elif tool_name == "mnemosyne_remember":
                return self._tool_remember(args)
            elif tool_name == "mnemosyne_recall":
                return self._tool_recall(args)
            elif tool_name == "mnemosyne_tree":
                return self._tool_tree(args)
            elif tool_name == "mnemosyne_hot_memories":
                return self._tool_hot(args)
            elif tool_name == "mnemosyne_palace_summon":
                return self._tool_palace_summon(args)
            elif tool_name == "mnemosyne_dialectic":
                return self._tool_dialectic(args)
            elif tool_name == "mnemosyne_tiered_read":
                return self._tool_tiered(args)
            elif tool_name == "mnemosyne_conflicts":
                return self._tool_conflicts(args)
            elif tool_name == "mnemosyne_wiki":
                return self._tool_wiki(args)
            elif tool_name == "mnemosyne_media":
                return self._tool_media(args)
            return tool_error(f"未知工具: {tool_name}")
        except Exception as e:
            return tool_error(str(e))

    def shutdown(self) -> None:
        # 2026-09-28 (T-0221): 只做短等 —— 写队列是 sqlite 持久化的，会话收尾任务
        # 已在后台跑（_run_session_end_job），关停路径不该再把用户/网关卡住。
        for t in (self._sync_thread, self._prefetch_thread):
            if t and t.is_alive():
                t.join(timeout=1.0)

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """上下文压缩前：提取关键洞察存储到 Mnemosyne，并返回压缩摘要。

        对标 Honcho dialectic + Mem0 fact extraction。
        messages 是将被压缩/丢弃的消息列表。
        返回的文本会被注入压缩 prompt，让压缩器保留这些洞察。
        """
        if not self._client or not messages:
            return ""

        try:
            # 提取用户问题和 AI 关键决策
            user_questions = []
            ai_decisions = []

            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if not content or len(content) < 10:
                    continue

                if role == "user":
                    # 提取问题（以问号结尾或包含关键词）
                    if "?" in content or "?" in content or "？" in content:
                        user_questions.append(content[:300])
                    elif any(kw in content[:50] for kw in ["检查", "修复", "部署", "发布", "审计"]):
                        user_questions.append(content[:200])

                elif role == "assistant":
                    # 提取关键决策/结论（含 ✅ ❌ 标记或总结陈述）
                    if any(kw in content[:200] for kw in ["✅", "完成", "已修复", "已部署", "结论"]):
                        ai_decisions.append(content[:400])

            if not user_questions and not ai_decisions:
                return ""

            # 构建压缩洞察
            blocks = []
            if user_questions:
                blocks.append(f"- 用户关注: {'; '.join(q[:100] for q in user_questions[:5])}")
            if ai_decisions:
                blocks.append(f"- AI决策: {'; '.join(d[:150] for d in ai_decisions[:3])}")

            insight_text = "\n".join(blocks)

            # 同步归档到 Mnemosyne 并拿到实体 ID（防丢闭环: 压缩丢的细节可召回）
            mid = None
            try:
                resp = self._client.store_memory(
                    content=f"[压缩洞察] {insight_text[:500]}",
                    category="note",
                    importance=0.5,
                    source="hermes-precompress"
                )
                mid = resp.get("id") or (resp.get("memory") or {}).get("id")
            except Exception as e:
                logger.debug("pre_compress store failed: %s", e)

            if mid:
                return f"[压缩洞察已归档 Mnemosyne#{mid}, 完整细节可召回] {insight_text}"
            return insight_text
        except Exception as e:
            logger.debug("on_pre_compress failed: %s", e)
            return ""

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs) -> None:
        """子代理完成后：存储任务+结果到记忆宫殿。

        对标 Zep temporal fact tracking — 记录「谁在什么时候做了什么」。
        """
        if not self._client or not task:
            return

        try:
            # 提取结果摘要（取前200字）
            result_summary = (result or "")[:200].replace("\n", " ")
            task_summary = task[:200].replace("\n", " ")

            content = (
                f"[子代理] 任务: {task_summary}"
            )
            if result_summary:
                content += f" | 结果: {result_summary}"
            if child_session_id:
                content += f" | session={child_session_id[:20]}"

            def _store():
                try:
                    client = _MnemosyneClient(self._endpoint, self._user_id)
                    client.store_memory(
                        content=content,
                        category="work",
                        importance=0.5,
                        source="hermes-delegation"
                    )
                except Exception as e:
                    logger.debug("delegation store failed: %s", e)

            threading.Thread(target=_store, daemon=True,
                            name="mnemosyne-delegation").start()
        except Exception as e:
            logger.debug("on_delegation failed: %s", e)

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs,
    ) -> None:
        """会话切换时自动刷新：检查队列 + 更新 session ID。"""
        try:
            from .write_queue import get_queue
            q = get_queue()
            pending = q.pending_count()
            if pending > 0:
                logger.info("session_switch: %d pending (consumer active)", pending)
                q.replay_pending()  # 确保消费者继续处理
        except Exception as e:
            logger.debug("session_switch queue check: %s", e)
        logger.debug("session_switch → %s (parent=%s, reset=%s)", new_session_id, parent_session_id, reset)

    # ── 工具实现 ──────────────────────────────────────────

    def _tool_search(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return tool_error("query 必填")
        user_id = args.get("user_id") or self._user_id
        limit = args.get("limit", 5)
        category = args.get("category", "")

        # 用指定 user_id 创建临时客户端
        client = _MnemosyneClient(self._endpoint, user_id)
        memories = client.search_memories(query, limit, category)

        if not memories:
            return json.dumps({"results": [], "total": 0})

        formatted = []
        for mem in memories:
            if isinstance(mem, dict):
                formatted.append({
                    "content": mem.get("content", "")[:300],
                    "heat": mem.get("heat_score", mem.get("score", 0)),
                    "tier": mem.get("tier", "L1"),
                    "category": mem.get("category", ""),
                    "id": mem.get("id", ""),
                    "created": mem.get("created_at", ""),
                })
            elif isinstance(mem, str):
                formatted.append({"content": mem[:300]})

        return json.dumps({"results": formatted, "total": len(formatted)}, ensure_ascii=False)

    def _tool_remember(self, args: dict) -> str:
        content = args.get("content", "")
        if not content:
            return tool_error("content 必填")

        # 清理消息后存储
        from .message_cleaner import prepare_for_storage
        clean = prepare_for_storage(content)
        if not clean:
            return tool_error("清理后内容为空，跳过存储")

        category = args.get("category", "fact")
        importance = args.get("importance", 0.5)

        result = self._client.store_memory(clean, category, importance)
        if "error" in result:
            return tool_error(f"存储失败: {result['error']}")
        return json.dumps({
            "status": "stored",
            "id": result.get("id", "?"),
            "message": "记忆已存入宫殿并加入索引",
        }, ensure_ascii=False)

    def _tool_recall(self, args: dict) -> str:
        query = args.get("query", "")
        if not query:
            return tool_error("query 必填")
        max_results = args.get("max_results", 5)

        result = self._client.recall(query, max_results)
        if "error" in result:
            # fallback 到简单搜索
            memories = self._client.search_memories(query, max_results)
            return json.dumps({"recall": memories, "fallback": True}, ensure_ascii=False)

        return json.dumps(result, ensure_ascii=False)

    def _tool_tree(self, args: dict) -> str:
        tree = self._client.get_tmt_tree()
        return json.dumps(tree, ensure_ascii=False)

    def _tool_hot(self, args: dict) -> str:
        limit = args.get("limit", 5)
        min_heat = args.get("min_heat", 0.3)
        memories = self._client.get_hot_memories(limit, min_heat)

        formatted = []
        for mem in memories:
            if isinstance(mem, dict):
                formatted.append({
                    "content": mem.get("content", "")[:200],
                    "heat": mem.get("heat_score", 0),
                    "tier": mem.get("tier", "L1"),
                    "access_count": mem.get("access_count", 0),
                    "id": mem.get("id", ""),
                })

        return json.dumps({"hot_memories": formatted, "total": len(formatted)}, ensure_ascii=False)

    def _tool_palace_summon(self, args: dict) -> str:
        """魔法记忆宫殿三通道召唤 (点名/引导/共鸣)"""
        query = args.get("query", "")
        user_id = args.get("user_id", self._user_id)
        top_k = args.get("top_k", 5)
        if not query:
            return tool_error("query 必填")
        try:
            result = self._client._call("GET", f"/palace/summon?q={quote(query)}&user_id={quote(user_id)}&top_k={top_k}")
            if isinstance(result, dict) and result.get("error"):
                # fallback 到语义搜索
                memories = self._client.search_memories(query, top_k)
                return json.dumps({"recall": memories, "fallback": True}, ensure_ascii=False)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return tool_error(f"palace_summon failed: {e}")

    def _tool_dialectic(self, args: dict) -> str:
        query = args.get("query", "")
        limit = args.get("limit", 3)
        if not query:
            return tool_error("query required")
        result = self._client.dialectic_search(query, limit)
        if isinstance(result, dict) and result.get("error"):
            return tool_error(result["error"])
        return json.dumps(result, ensure_ascii=False)

    def _tool_tiered(self, args: dict) -> str:
        memory_id = args.get("memory_id", 0)
        level = args.get("level", "L3")
        if not memory_id:
            return tool_error("memory_id required")
        result = self._client.tiered_read(memory_id, level)
        if isinstance(result, dict) and result.get("error"):
            return tool_error(result["error"])
        return json.dumps(result, ensure_ascii=False)

    def _tool_conflicts(self, args: dict) -> str:
        limit = args.get("limit", 10)
        result = self._client.get_conflicts(limit)
        if isinstance(result, dict) and result.get("error"):
            return tool_error(result["error"])
        return json.dumps(result, ensure_ascii=False)

    def _tool_wiki(self, args: dict) -> str:
        action = args.get("action", "search")
        if action == "search":
            query = args.get("query", "")
            if not query:
                return tool_error("query required for search action")
            top_k = args.get("top_k", 5)
            data = self._client.search_wiki(query, top_k)
            result = {"hits": data, "total": len(data)} if isinstance(data, list) else data
        elif action == "by_source":
            sp = args.get("source_path", "")
            su = args.get("source_url", "")
            if not sp and not su:
                return tool_error("source_path or source_url required for by_source action")
            result = self._client.get_wiki_by_source(source_path=sp, source_url=su)
        elif action == "get":
            page_id = args.get("page_id", 0)
            if not page_id:
                return tool_error("page_id required for get action")
            result = self._client.get_wiki_page(page_id)
        else:
            limit = args.get("limit", 10)
            data = self._client.list_wiki(limit)
            result = {"pages": data, "total": len(data)} if isinstance(data, list) else data
        if isinstance(result, dict) and result.get("error"):
            return tool_error(result["error"])
        return json.dumps(result, ensure_ascii=False)

    def _tool_media(self, args: dict) -> str:
        action = args.get("action", "list")
        if action == "get":
            mid = args.get("media_id", 0)
            if not mid:
                return tool_error("media_id required")
            result = self._client.get_media(mid)
        elif action == "create":
            content = args.get("content", "")
            if not content:
                return tool_error("content required for create")
            result = self._client.create_media(
                content, args.get("media_type", "file"),
                args.get("media_url", ""),
            )
        else:
            limit = args.get("limit", 10)
            data = self._client.list_media(limit)
            result = {"media": data, "total": len(data)} if isinstance(data, list) else data
        if isinstance(result, dict) and result.get("error"):
            return tool_error(result["error"])
        return json.dumps(result, ensure_ascii=False)


# ── 插件入口 ────────────────────────────────────────────

def register(ctx) -> None:
    """注册 Mnemosyne 为 Hermes memory provider。"""
    ctx.register_memory_provider(MnemosyneMemoryProvider())
