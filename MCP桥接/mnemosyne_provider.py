"""
Mnemosyne Memory Provider — 替换 OpenViking，使用自研记忆宫殿。

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
import uuid
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINT = "http://127.0.0.1:18010"
_DEFAULT_USER_ID = "default"
_API_TIMEOUT = 15.0

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
    "description": "查询知识库(Wiki)页面。支持列表查看和按ID查看全文。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "list(列表) 或 get(查看)", "default": "list"},
            "page_id": {"type": "integer", "description": "get模式必填: 页面ID"},
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
        self._http = self._httpx.Client(timeout=_API_TIMEOUT)

    def _call(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self._api_base}{path}"
        try:
            r = self._http.request(method, url, **kwargs)
            r.raise_for_status()
            return r.json() if r.text else {}
        except Exception as e:
            detail = ""
            if hasattr(e, "response") and e.response is not None:
                detail = e.response.text[:300]
            return {"error": str(e), "detail": detail}

    def health(self) -> bool:
        try:
            r = self._http.get(f"{self._endpoint}/api/v1/echo", timeout=3.0)
            return r.status_code == 200
        except Exception:
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
        """3 阶段智能召回（含 LLM 蒸馏）。"""
        payload = {
            "user_id": self._user_id,
            "query": query,
            "max_results": max_results,
        }
        result = self._call("POST", "/tmt/recall", json=payload)
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

    def system_prompt_block(self) -> str:
        if not self._client:
            return ""
        try:
            tree = self._client.get_tmt_tree()
            levels = tree.get("levels", {})
            l2 = levels.get("L2", {}).get("count", 0)
            l3 = levels.get("L3", {}).get("count", 0)
            summary = (
                f"Mnemosyne 记忆宫殿 (Endpoint: {self._endpoint})\n"
                f"用户: {self._user_id} | "
                f"TMT: L2={l2}会话 L3={l3}每日\n"
                "使用 mnemosyne_search 或 mnemosyne_recall 检索记忆。\n"
                "使用 mnemosyne_remember 主动存储重要信息。"
            )
            return summary
        except Exception:
            return (
                "# Mnemosyne 记忆宫殿\n"
                f"Endpoint: {self._endpoint}\n"
                "使用 mnemosyne_search / mnemosyne_recall 检索记忆。\n"
                "使用 mnemosyne_remember 存储重要信息。"
            )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """返回后台预取的结果（上下文注入用）。"""
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=3.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        if not result:
            return ""
        return f"## Mnemosyne 关联记忆\n{result}"

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """后台搜索相关记忆，下轮对话注入上下文。"""
        if not self._client or not query:
            return

        def _run():
            try:
                client = _MnemosyneClient(self._endpoint, self._user_id)
                memories = client.search_memories(query, limit=5)
                if not memories:
                    # 尝试简单召回
                    memories = client.recall_simple(query)
                if not memories:
                    return

                parts = []
                for i, mem in enumerate(memories[:5]):
                    if isinstance(mem, dict):
                        content = mem.get("content", str(mem))
                        heat = mem.get("heat_score", mem.get("score", 0))
                        tier = mem.get("tier", "L1")
                        parts.append(f"- [{tier}|{heat:.2f}] {content[:200]}")
                    elif isinstance(mem, str):
                        parts.append(f"- {mem[:200]}")

                if parts:
                    with self._prefetch_lock:
                        self._prefetch_result = "\n".join(parts)
            except Exception as e:
                logger.debug("Mnemosyne prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(
            target=_run, daemon=True, name="mnemosyne-prefetch"
        )
        self._prefetch_thread.start()

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict[str, Any]]] = None) -> None:
        """每轮对话后自动存储到 Mnemosyne（经持久写队列，crash-safe）。"""
        if not self._client:
            return

        self._turn_count += 1

        # 清理消息（剥离注入标签 + 过滤临时消息）
        from .message_cleaner import prepare_for_storage
        clean_user = prepare_for_storage(user_content) if user_content else ""
        clean_asst = prepare_for_storage(assistant_content) if assistant_content else ""

        # 写入持久队列（立即 SQLite 落地，不丢数据）
        from .write_queue import get_queue
        q = get_queue()

        if clean_user:
            q.enqueue(user_content=clean_user[:500], assistant_content="",
                      category="chat", source="hermes-sync")

        if clean_asst:
            q.enqueue(user_content="", assistant_content=clean_asst[:800],
                      category="note" if len(clean_asst) > 100 else "chat",
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
                                content=f"用户提问: {item['user_content'][:500]}",
                                category="chat", importance=0.4, source=item["source"]
                            )
                        if item["assistant_content"]:
                            client.store_memory(
                                content=item["assistant_content"],
                                category="note" if len(item["assistant_content"]) > 100 else "chat",
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
        """会话结束时触发 TMT L2 蒸馏。"""
        if not self._client:
            return

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=10.0)

        if self._turn_count == 0:
            return

        try:
            result = self._client.consolidate_session()
            logger.info("Mnemosyne L2 consolidation triggered (%d turns): %s",
                        self._turn_count, result.get("skipped", False))
        except Exception as e:
            logger.warning("Mnemosyne session consolidation failed: %s", e)

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """镜像内置 memory 工具写入到 Mnemosyne。"""
        if not self._client or action != "add" or not content:
            return

        category_map = {
            "user": "preference",
            "memory": "pattern",
        }
        category = category_map.get(target, "fact")

        def _write():
            try:
                client = _MnemosyneClient(self._endpoint, self._user_id)
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
        return [SEARCH_SCHEMA, REMEMBER_SCHEMA, RECALL_SCHEMA, TREE_SCHEMA, HOT_SCHEMA,
                DIALECTIC_SCHEMA, TIERED_READ_SCHEMA, CONFLICT_SCHEMA, WIKI_SCHEMA, MEDIA_SCHEMA]

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
        for t in (self._sync_thread, self._prefetch_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)

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
        action = args.get("action", "list")
        if action == "get":
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
