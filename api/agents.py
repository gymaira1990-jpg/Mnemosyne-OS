"""多 Agent 身份卡 API（2026-11-07 建，对应 T-0678 第 1 步）

定位：个人版 OPC 编制 —— 每个 Agent 一张卡，卡片数据存在**已有的 `users` 表** `metadata` 里，
不新建表、不动 memories 结构。本步只读：列出全部身份卡 + 各自记忆量与最后活跃时间。

设计稿：箱子 `00_收件箱/多Agent记忆模型_设计稿_v0.1_20261107.{html,md}`
契约（按 user_id 隔离）：仓库 `docs/MULTI-AGENT-SEAM.md`

判据（踩过的坑）：只列 `users` 表会漏掉「只写过记忆、没建卡」的 Agent ——
所以用 FULL OUTER JOIN，把「有记忆但没卡」的也列出来并标 `has_card=false`，
这样缺口是**看得见**的，而不是被 INNER JOIN 悄悄吃掉。
"""
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])
pool = None

_CARD_FIELDS = ("role", "owner", "model", "status", "capabilities", "boundary", "started_at")


def _card(metadata: Any) -> dict:
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}
    if not isinstance(metadata, dict):
        return {}
    return {k: metadata.get(k) for k in _CARD_FIELDS if metadata.get(k) is not None}


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


@router.get("")
async def list_agents() -> dict:
    """列出全部 Agent 身份卡（含只写过记忆、没有卡的）。"""
    rows = await pool.fetch(
        """
        SELECT COALESCE(u.user_id, m.user_id)          AS agent_id,
               u.name                                  AS name,
               u.metadata                              AS metadata,
               COUNT(m.id) FILTER (WHERE NOT m.is_deleted) AS memory_count,
               MAX(m.created_at)                       AS last_active
        FROM users u
        FULL OUTER JOIN memories m ON m.user_id = u.user_id
        GROUP BY 1, 2, 3
        ORDER BY memory_count DESC, agent_id
        """
    )

    agents = []
    for r in rows:
        card = _card(r["metadata"])
        agents.append({
            "user_id": r["agent_id"],
            "name": r["name"],
            "has_card": bool(card),
            "role": card.get("role"),
            "status": card.get("status") or ("active" if card else "unknown"),
            "model": card.get("model"),
            "owner": card.get("owner"),
            "boundary": card.get("boundary"),
            "capabilities": card.get("capabilities"),
            "memory_count": r["memory_count"] or 0,
            "last_active": _iso(r["last_active"]),
        })

    active = sum(1 for a in agents if a["status"] == "active")
    return {
        "agents": agents,
        "count": len(agents),
        "active": active,
        "without_card": sum(1 for a in agents if not a["has_card"]),
    }
