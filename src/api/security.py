"""
Mnemosyne v5.0 — 安全 API 路由
审计 + 哈希净化端点
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/security", tags=["security"])
pool = None


class DeleteRequest(BaseModel):
    memory_id: int
    reason: str = "user_request"


@router.post("/audit/run")
async def run_audit(tenant_id: str = "default", limit: int = 5):
    """运行异构审计"""
    from security.audit import schedule_audit
    async with pool.acquire() as conn:
        results = await schedule_audit(conn, tenant_id, limit)
        return {"audited": len(results), "results": results}


@router.post("/purify")
async def purify_memory(req: DeleteRequest):
    """哈希净化一条记忆 (不可逆删除)"""
    from security.purifier import soft_delete_memory
    async with pool.acquire() as conn:
        result = await soft_delete_memory(conn, req.memory_id, req.reason)
        return result


@router.get("/fossils")
async def list_fossils(tenant_id: str = "default", limit: int = 20):
    """列出化石节点"""
    from security.purifier import get_fossil_nodes
    async with pool.acquire() as conn:
        fossils = await get_fossil_nodes(conn, tenant_id, limit)
        return {"fossils": fossils, "count": len(fossils)}


@router.get("/costs")
async def get_costs():
    """查询成本统计"""
    from core.llm import get_cost_stats, get_cache_stats
    return {
        "costs": get_cost_stats(),
        "cache": get_cache_stats(),
    }
