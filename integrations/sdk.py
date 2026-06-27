"""
Mnemosyne v5.0 — Hermes MemoryProvider SDK
白皮书 §6.2 工作流级深度映射 + §6.4 官方原生SDK

零侵入替换 Hermes 原生记忆基类
"""
import json
import urllib.request
from typing import Dict, List, Optional


class MnemosyneHermesMemory:
    """
    Hermes 原生 SDK — 3行代码集成
    
    Usage:
        from mnemosyne_hermes_sdk import MnemosyneHermesMemory
        memory = MnemosyneHermesMemory(endpoint="http://127.0.0.1:18010")
        memory.add("用户偏好使用 Python 3.10", memory_type="preference")
    """
    
    def __init__(self, endpoint: str = "http://127.0.0.1:18010", 
                 api_key: str = "", 
                 user_id: str = "default",
                 agent_id: str = "hermes-main"):
        self.endpoint = endpoint.rstrip("/")
        self.user_id = user_id
        self.agent_id = agent_id
        self.session_id = None
        self.decision_level = "L0"  # L0/L1/L2
        
        self._opener = urllib.request.build_opener()
        if api_key:
            self._opener.addheaders = [("Authorization", f"Bearer {api_key}")]
    
    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.endpoint}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Agent-Id": self.agent_id,
            },
            method="POST"
        )
        with self._opener.open(req, timeout=30) as resp:
            return json.loads(resp.read())
    
    def _get(self, path: str) -> dict:
        url = f"{self.endpoint}{path}"
        req = urllib.request.Request(url, method="GET")
        with self._opener.open(req, timeout=10) as resp:
            return json.loads(resp.read())
    
    # ── 会话管理 ──
    def on_session_start(self, session_id: str):
        """会话启动"""
        self.session_id = session_id
    
    # ── 记忆操作 ──
    def add(self, content: str, memory_type: str = "general", 
            category: str = "general", tags: List[str] = None) -> dict:
        """添加记忆 → 研究馆"""
        return self._post("/api/v1/halls/archive", {
            "content": content,
            "memory_type": memory_type,
            "category": category,
            "tags": tags or [],
            "session_id": self.session_id,
            "tenant_id": self.user_id,
        })
    
    def get_relevant(self, query: str, top_k: int = 3) -> List[dict]:
        """检索相关记忆"""
        r = self._post("/api/v1/memories/search", {
            "query": query,
            "top_k": top_k,
            "user_id": self.user_id,
        })
        data = r.get("data", r)  # 兼容有无包装
        return data.get("memories", [])
    
    def search_by_hall(self, hall: str, limit: int = 10) -> List[dict]:
        """按馆查询"""
        r = self._get(f"/api/v1/halls/{hall}?tenant_id={self.user_id}&limit={limit}")
        data = r.get("data", r)
        return data.get("memories", [])
    
    # ── 工具调用 ──
    def archive_tool_call(self, tool_name: str, params: dict,
                          result: str, success: bool,
                          error_type: str = None, duration_ms: int = None) -> dict:
        """归档工具调用结果"""
        return self._post("/api/v1/tools/archive", {
            "tool_name": tool_name,
            "params": params,
            "result": str(result),
            "success": success,
            "error_type": error_type,
            "session_id": self.session_id,
            "duration_ms": duration_ms,
            "tenant_id": self.user_id,
        })
    
    # ── 项目管理 ──
    def start_project(self, project_name: str, description: str = "") -> dict:
        """创建项目"""
        return self._post("/api/v1/projects/create", {
            "name": project_name,
            "description": description,
            "tenant_id": self.user_id,
        })
    
    def archive_project(self, project_id: int) -> dict:
        """归档项目"""
        return self._post(f"/api/v1/projects/{project_id}/archive", {})
    
    # ── 安全操作 ──
    def purify_memory(self, memory_id: int, reason: str = "user_request") -> dict:
        """哈希净化记忆"""
        return self._post("/api/v1/security/purify", {
            "memory_id": memory_id,
            "reason": reason,
        })
    
    def run_audit(self, limit: int = 5) -> dict:
        """运行异构审计"""
        return self._post(f"/api/v1/security/audit/run?limit={limit}", {})
    
    def get_costs(self) -> dict:
        """查询成本"""
        return self._get("/api/v1/security/costs")
    
    # ── 配置 ──
    def set_decision_level(self, level: str):
        """设置决策级别 L0/L1/L2"""
        self.decision_level = level
    
    def enable_anonymous_feedback(self, enabled: bool = True):
        """启用匿名回传"""
        self._feedback_enabled = enabled
    
    # ── 统计 ──
    def stats(self) -> dict:
        """记忆库统计"""
        return self._get(f"/api/v1/memories/stats?user_id={self.user_id}")
    
    # ── 快捷方法 ──
    def remember(self, content: str, category: str = "note") -> dict:
        """快捷记忆 (归档到档案馆)"""
        return self.add(content, memory_type="fact", category=category)
    
    def pitfall(self, tool: str, error: str, fix: str = "") -> dict:
        """记录踩坑"""
        return self.archive_tool_call(
            tool_name=tool,
            params={},
            result=f"{error} || FIX: {fix}" if fix else error,
            success=False,
            error_type="user_reported"
        )
