"""
Mnemosyne v5.0 — 工具归档 API
白皮书 §9.2 踩坑闭环: 工具调用 → 失败/成功 → 沉淀
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
import json

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

pool = None


class ToolArchiveRequest(BaseModel):
    tool_name: str
    params: dict = {}
    result: str
    success: bool
    error_type: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[int] = None
    duration_ms: Optional[int] = None
    tenant_id: str = "default"


@router.post("/archive")
async def archive_tool_call(req: ToolArchiveRequest):
    """工具调用归档: 成功→技能 失败→踩坑"""
    async with pool.acquire() as conn:
        archive_id = f"tool_arc_{uuid.uuid4().hex[:12]}"
        knowledge_type = "skill" if req.success else "pitfall"
        
        # 写入归档
        row = await conn.fetchrow(
            """INSERT INTO tool_archives 
               (archive_id, tool_name, params, result, success, error_type,
                knowledge_type, session_id, project_id, duration_ms, tenant_id)
               VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11)
               RETURNING id""",
            archive_id, req.tool_name,
            json.dumps(req.params), req.result[:5000], req.success,
            req.error_type, knowledge_type, req.session_id,
            req.project_id, req.duration_ms, req.tenant_id
        )
        
        # 同时写入记忆库 → 研究馆
        hall = "engineering" if not req.success else "archive"
        try:
            mem = await conn.fetchrow(
                """INSERT INTO memories (content, category, hall, user_id)
                   VALUES ($1, 'tool_call', $2, $3)
                   RETURNING id""",
                f"[{'✅' if req.success else '❌'}] {req.tool_name}: {req.result[:300]}",
                hall, req.tenant_id
            )
            mem_id = mem["id"] if mem else None
        except Exception:
            mem_id = None  # session_id UUID issue - skip memory write
        
        # 失败 → 关联踩坑预警
        warning = None
        if not req.success:
            # 检查是否有同类历史踩坑
            similar = await conn.fetchval(
                """SELECT result FROM tool_archives 
                   WHERE tool_name=$1 AND success=false AND error_type=$2
                   ORDER BY created_at DESC LIMIT 1""",
                req.tool_name, req.error_type
            )
            if similar:
                warning = {
                    "type": "repeat_pitfall",
                    "message": f"该工具 ({req.tool_name}) 有历史踩坑记录",
                    "previous": (similar or "")[:200]
                }
        
        return {
            "archive_id": archive_id,
            "knowledge_type": knowledge_type,
            "memory_id": mem_id,
            "hall": hall,
            "warning": warning,
        }


@router.get("/pitfalls")
async def list_pitfalls(tool_name: Optional[str] = None, 
                         tenant_id: str = "default", limit: int = 20):
    """查询踩坑记录"""
    async with pool.acquire() as conn:
        if tool_name:
            rows = await conn.fetch(
                """SELECT archive_id, tool_name, result, error_type, 
                   created_at, duration_ms
                   FROM tool_archives 
                   WHERE success=false AND tool_name=$1 AND tenant_id=$2
                   ORDER BY created_at DESC LIMIT $3""",
                tool_name, tenant_id, limit
            )
        else:
            rows = await conn.fetch(
                """SELECT archive_id, tool_name, result, error_type,
                   created_at, duration_ms
                   FROM tool_archives
                   WHERE success=false AND tenant_id=$1
                   ORDER BY created_at DESC LIMIT $2""",
                tenant_id, limit
            )
        
        return {
            "pitfalls": [
                {
                    "archive_id": r["archive_id"],
                    "tool": r["tool_name"],
                    "error_type": r["error_type"],
                    "result": (r["result"] or "")[:300],
                    "duration_ms": r["duration_ms"],
                    "created": str(r["created_at"])[:19],
                }
                for r in rows
            ],
            "count": len(rows)
        }


@router.get("/skills")
async def list_skills(tenant_id: str = "default", limit: int = 20):
    """查询沉淀的技能"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT archive_id, tool_name, result, created_at
               FROM tool_archives
               WHERE success=true AND tenant_id=$1
               ORDER BY created_at DESC LIMIT $2""",
            tenant_id, limit
        )
        return {
            "skills": [
                {
                    "archive_id": r["archive_id"],
                    "tool": r["tool_name"],
                    "result": (r["result"] or "")[:300],
                    "created": str(r["created_at"])[:19],
                }
                for r in rows
            ],
            "count": len(rows)
        }
