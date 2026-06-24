"""
Mnemosyne v5.0 — 三馆闭环 API
白皮书 L4 核心业务层: 研究馆 ↔ 工程馆 ↔ 档案馆 流转
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/halls", tags=["halls"])

# pool 由 main.py 注入
pool = None


class MemoryArchiveRequest(BaseModel):
    content: str
    content_type: str = "text"
    memory_type: str = "general"
    category: str = "general"
    tags: list[str] = []
    session_id: Optional[str] = None
    project_id: Optional[int] = None
    tenant_id: str = "default"
    source: str = "manual"


class PromoteRequest(BaseModel):
    memory_id: int
    target_hall: str  # "engineering" or "archive"
    gate_notes: Optional[str] = None


@router.post("/archive")
async def archive_to_research(req: MemoryArchiveRequest):
    """入馆: 接收记忆 → 入馆闸机 → 研究馆 (hall='research')"""
    async with pool.acquire() as conn:
        # 入馆闸机: 规则过滤
        content = req.content.strip()
        if len(content) < 5:
            return {"error": "内容过短 (闸机拒绝)", "hall": None}
        
        # 写入研究馆
        row = await conn.fetchrow(
            """INSERT INTO memories (content, category, session_id, project_id, 
               user_id, hall, verification_status)
               VALUES ($1, $2, $3, $4, $5, 'research', 'pending')
               RETURNING id, hall""",
            content, req.category, req.session_id,
            req.project_id, req.tenant_id
        )
        return {
            "memory_id": row["id"],
            "hall": row["hall"],
            "status": "processing",
            "note": "已进入研究馆，待方案推演"
        }


@router.post("/promote")
async def promote_memory(req: PromoteRequest):
    """流转: 研究馆 → 工程馆 → 档案馆 (通过闸机)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, hall FROM memories WHERE id=$1 AND is_deleted=FALSE",
            req.memory_id
        )
        if not row:
            raise HTTPException(404, "记忆不存在")
        
        current = row["hall"]
        target = req.target_hall
        
        # 流转规则
        valid_flow = {
            "research": ["engineering"],
            "engineering": ["archive", "research"],  # 失败可退回
            "archive": [],  # 归档后不可流转
        }
        
        if target not in valid_flow.get(current, []):
            raise HTTPException(400, f"不可从 {current} 流转到 {target}")
        
        # 方案闸机 / 归档闸机 (简化版，Phase 2.3 完善)
        await conn.execute(
            "UPDATE memories SET hall=$1, parent_memory_id=$2 WHERE id=$3",
            target, req.memory_id, req.memory_id
        )
        
        # 记录闸机通过
        gate_type = "solution" if target == "engineering" else "archive"
        await conn.execute(
            """INSERT INTO gates (memory_id, gate_type, passed, checks, auditor_model)
               VALUES ($1, $2, true, $3, 'auto')""",
            req.memory_id, gate_type, 
            f'{{"notes": "{req.gate_notes or "手动流转"}"}}'
        )
        
        return {
            "memory_id": req.memory_id,
            "from": current,
            "to": target,
            "gate": gate_type,
            "passed": True
        }


@router.post("/demote")
async def demote_memory(req: PromoteRequest):
    """退回: 工程馆失败 → 研究馆"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, hall FROM memories WHERE id=$1", req.memory_id
        )
        if not row:
            raise HTTPException(404, "记忆不存在")
        if row["hall"] != "engineering":
            raise HTTPException(400, "仅工程馆记忆可退回")
        
        await conn.execute(
            "UPDATE memories SET hall='research' WHERE id=$1", req.memory_id
        )
        
        return {"memory_id": req.memory_id, "from": "engineering", "to": "research"}


@router.get("/{hall}")
async def list_by_hall(hall: str, tenant_id: str = "default", limit: int = 20):
    """按馆查询记忆"""
    if hall not in ("research", "engineering", "archive"):
        raise HTTPException(400, "无效的馆名")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, content, category, hall, verification_status, 
               heat_score, reliability, created_at
               FROM memories WHERE hall=$1 AND user_id=$2 AND is_deleted=FALSE
               ORDER BY created_at DESC LIMIT $3""",
            hall, tenant_id, limit
        )
        return {
            "hall": hall,
            "count": len(rows),
            "memories": [
                {
                    "id": r["id"],
                    "content": (r["content"] or "")[:200],
                    "category": r["category"],
                    "hall": r["hall"],
                    "verification": r["verification_status"],
                    "heat": r["heat_score"],
                    "reliability": r["reliability"],
                    "created": str(r["created_at"])[:19],
                }
                for r in rows
            ]
        }
