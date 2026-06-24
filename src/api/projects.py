"""
Mnemosyne v5.0 — 项目管理 API
白皮书 L5 运行时调度层: 项目级沙箱
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

pool = None


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    tenant_id: str = "default"


class ProjectArchive(BaseModel):
    project_id: int


@router.post("/create")
async def create_project(req: ProjectCreate):
    """创建项目"""
    async with pool.acquire() as conn:
        pid = f"proj_{uuid.uuid4().hex[:12]}"
        row = await conn.fetchrow(
            """INSERT INTO projects (project_id, tenant_id, name, description)
               VALUES ($1, $2, $3, $4) RETURNING id, project_id, created_at""",
            pid, req.tenant_id, req.name, req.description
        )
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": req.name,
            "created": str(row["created_at"])[:19],
        }


@router.get("/{project_id}")
async def get_project(project_id: int):
    """查询项目"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM projects WHERE id=$1", project_id
        )
        if not row:
            raise HTTPException(404, "项目不存在")
        
        # 统计项目下的记忆数
        mem_count = await conn.fetchval(
            "SELECT count(*) FROM memories WHERE project_id=$1", project_id
        )
        
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "status": row["status"],
            "memory_count": mem_count,
            "created": str(row["created_at"])[:19],
            "updated": str(row["updated_at"])[:19],
        }


@router.post("/{project_id}/archive")
async def archive_project(project_id: int):
    """归档项目"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE projects SET status='archived', updated_at=NOW() WHERE id=$1 RETURNING id",
            project_id
        )
        if not row:
            raise HTTPException(404, "项目不存在")
        return {"id": project_id, "status": "archived", "message": "项目已归档"}


@router.post("/{project_id}/destroy")
async def destroy_project(project_id: int):
    """销毁项目沙箱 (不可逆)"""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE projects SET status='destroyed', updated_at=NOW() WHERE id=$1 RETURNING id",
            project_id
        )
        if not row:
            raise HTTPException(404, "项目不存在")
        # 清除关联记忆的 project_id
        await conn.execute(
            "UPDATE memories SET project_id=NULL WHERE project_id=$1", project_id
        )
        return {"id": project_id, "status": "destroyed", "message": "项目沙箱已销毁 (记忆已保留)"}


@router.get("/")
async def list_projects(tenant_id: str = "default"):
    """列出所有项目"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT p.*, 
               (SELECT count(*) FROM memories m WHERE m.project_id=p.id) as mem_count
               FROM projects p WHERE p.tenant_id=$1 ORDER BY p.created_at DESC""",
            tenant_id
        )
        return {
            "projects": [
                {
                    "id": r["id"],
                    "project_id": r["project_id"],
                    "name": r["name"],
                    "description": r["description"],
                    "status": r["status"],
                    "memory_count": r["mem_count"],
                    "created": str(r["created_at"])[:19],
                }
                for r in rows
            ],
            "count": len(rows)
        }
