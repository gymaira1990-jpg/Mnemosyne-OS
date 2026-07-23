"""
Mnemosyne v5.0 — 三馆闭环 API
白皮书 L4 核心业务层: 研究馆 ↔ 工程馆 ↔ 档案馆 流转
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

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
    """流转: 研究馆 → 工程馆 → 档案馆 (通过闸机 + 异构审计)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, hall, content FROM memories WHERE id=$1 AND is_deleted=FALSE",
            req.memory_id
        )
        if not row:
            raise HTTPException(404, "记忆不存在")
        
        current = row["hall"]
        target = req.target_hall
        content = row["content"] or ""
        
        # 流转规则
        valid_flow = {
            "research": ["engineering"],
            "engineering": ["archive", "research"],  # 失败可退回
            "archive": [],  # 归档后不可流转
        }
        
        if target not in valid_flow.get(current, []):
            raise HTTPException(400, f"不可从 {current} 流转到 {target}")
        
        # 闸机: 异构审计 (Phase 2.3 正式版)
        audit_result = None
        try:
            from security.audit import audit_memory
            audit_result = await audit_memory(conn, req.memory_id, content)
        except Exception as e:
            # 审计调用失败 → 降级为直通，记录 warning
            audit_result = {
                "verdict": "consistent",  # 降级直通
                "confidence": 0,
                "models": [],
                "reliability_delta": 0,
                "warning": f"audit_failed: {str(e)[:200]}",
            }
        
        passed = audit_result.get("verdict") == "consistent"
        
        if not passed:
            # 闸机拒绝 — 不升级，记录失败
            gate_type = "solution" if target == "engineering" else "archive"
            await conn.execute(
                """INSERT INTO gates (memory_id, gate_type, passed, checks, auditor_model)
                   VALUES ($1, $2, false, $3, 'doubao-lite+doubao-code')""",
                req.memory_id, gate_type,
                json.dumps({
                    "verdict": audit_result.get("verdict"),
                    "confidence": audit_result.get("confidence"),
                    "dispute": audit_result.get("dispute_detail", ""),
                    "models": audit_result.get("models", []),
                })
            )
            return {
                "memory_id": req.memory_id,
                "from": current,
                "to": target,
                "gate": gate_type,
                "passed": False,
                "reason": "异构审计未通过 — 双模型意见不一致，记忆保留在原馆",
                "audit": audit_result,
            }
        
        # 通过 — 执行升级
        await conn.execute(
            "UPDATE memories SET hall=$1, parent_memory_id=$2 WHERE id=$3",
            target, req.memory_id, req.memory_id
        )
        
        # 应用审计的 reliability 调整
        delta = audit_result.get("reliability_delta", 0)
        if abs(delta) > 0:
            await conn.execute(
                "UPDATE memories SET reliability = GREATEST(0, LEAST(1, reliability + $1)), "
                "updated_at = NOW() WHERE id = $2",
                delta, req.memory_id
            )
        
        # 记录闸机通过
        gate_type = "solution" if target == "engineering" else "archive"
        await conn.execute(
            """INSERT INTO gates (memory_id, gate_type, passed, checks, auditor_model)
               VALUES ($1, $2, true, $3, 'doubao-lite+doubao-code')""",
            req.memory_id, gate_type,
            json.dumps({
                "verdict": audit_result.get("verdict"),
                "confidence": audit_result.get("confidence"),
                "reliability_delta": delta,
            })
        )
        
        return {
            "memory_id": req.memory_id,
            "from": current,
            "to": target,
            "gate": gate_type,
            "passed": True,
            "audit": {
                "verdict": audit_result.get("verdict"),
                "confidence": audit_result.get("confidence"),
                "reliability_delta": delta,
            },
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


@router.get("/suggestions")
async def get_suggestions(user_id: str = "default"):
    """建议清单: 返回可升级/降级/遗忘的记忆候选项 (只读，不自动执行)"""
    async with pool.acquire() as conn:
        # 候选项1: 研究馆 → 工程馆 (reliability ≥ 0.8 + 停留 ≥ 7天)
        promote_to_eng = await conn.fetch(
            """SELECT id, content, reliability, heat_score, 
               EXTRACT(DAY FROM NOW() - created_at)::int AS days_ago
               FROM memories 
               WHERE hall='research' AND user_id=$1 AND is_deleted=FALSE
                 AND reliability >= 0.8
                 AND created_at < NOW() - INTERVAL '7 days'
               ORDER BY reliability DESC, heat_score DESC
               LIMIT 10""",
            user_id
        )
        
        # 候选项2: 工程馆 → 档案馆 (reliability ≥ 0.9 + 停留 ≥ 14天)
        promote_to_archive = await conn.fetch(
            """SELECT id, content, reliability, heat_score,
               EXTRACT(DAY FROM NOW() - created_at)::int AS days_ago
               FROM memories
               WHERE hall='engineering' AND user_id=$1 AND is_deleted=FALSE
                 AND reliability >= 0.9
                 AND created_at < NOW() - INTERVAL '14 days'
               ORDER BY reliability DESC
               LIMIT 10""",
            user_id
        )
        
        # 候选项3: 工程馆 → 退回研究馆 (停留 > 60天 + heat < 0.1)
        demote_candidates = await conn.fetch(
            """SELECT id, content, reliability, heat_score,
               EXTRACT(DAY FROM NOW() - created_at)::int AS days_ago
               FROM memories
               WHERE hall='engineering' AND user_id=$1 AND is_deleted=FALSE
                 AND created_at < NOW() - INTERVAL '60 days'
                 AND heat_score < 0.1
               ORDER BY created_at ASC
               LIMIT 10""",
            user_id
        )
        
        # 候选项4: 研究馆遗忘 (停留 > 30天 + heat < 0.1)
        forget_candidates = await conn.fetch(
            """SELECT id, content, reliability, heat_score,
               EXTRACT(DAY FROM NOW() - created_at)::int AS days_ago
               FROM memories
               WHERE hall='research' AND user_id=$1 AND is_deleted=FALSE
                 AND created_at < NOW() - INTERVAL '30 days'
                 AND heat_score < 0.1
               ORDER BY heat_score ASC
               LIMIT 10""",
            user_id
        )
        
        def fmt(row):
            return {
                "id": row["id"],
                "content": (row["content"] or "")[:150],
                "reliability": float(row["reliability"]) if row["reliability"] else 0.5,
                "heat": float(row["heat_score"]) if row["heat_score"] else 0,
                "days_ago": int(row["days_ago"]) if row["days_ago"] else 0,
            }
        
        return {
            "promote_to_engineering": [fmt(r) for r in promote_to_eng],
            "promote_to_archive": [fmt(r) for r in promote_to_archive],
            "demote_to_research": [fmt(r) for r in demote_candidates],
            "forget_candidates": [fmt(r) for r in forget_candidates],
            "note": "只读建议，不自动执行。Agent 自行决定是否调用 /promote 或 /demote。",
        }
