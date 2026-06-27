"""
Mnemosyne v5.0 — 哈希净化与化石节点
白皮书 L3 第三纵深 + 合规保真

原理: 
- 删除 = SHA-256 哈希替代原始内容 (不可逆)
- 保留元数据 + 拓扑关系 (链路完整)
- DAG 中显示为灰色化石节点

对应 白皮书 §5.6 合规与保真平衡
"""
import hashlib
from datetime import datetime, timezone


def purify_content(content: str) -> str:
    """
    哈希净化: 将原始内容替换为 SHA-256 哈希
    
    Args:
        content: 原始内容
    
    Returns:
        sha256:hash_prefix (不可逆)
    """
    h = hashlib.sha256(content.encode()).hexdigest()
    return f"sha256:{h}"


async def soft_delete_memory(conn, memory_id: int, reason: str = "user_request") -> dict:
    """
    软删除 + 哈希净化
    
    流程:
    1. 原始内容 → SHA-256 哈希
    2. content 替换为净化值 (不可读)
    3. is_deleted = TRUE
    4. metadata 记录删除原因
    5. 保留所有关联关系 (拓扑完整)
    
    Returns:
        {"memory_id": int, "status": "purified", "fossil": bool}
    """
    row = await conn.fetchrow(
        "SELECT content FROM memories WHERE id=$1 AND is_deleted=FALSE",
        memory_id
    )
    if not row:
        return {"error": "Memory not found or already deleted"}
    
    purified = purify_content(row["content"] or "")
    
    await conn.execute(
        """UPDATE memories SET 
           content=$1, is_deleted=TRUE, 
           metadata = COALESCE(metadata,'{}')::jsonb || $2::jsonb,
           updated_at=$3
           WHERE id=$4""",
        purified,
        f'{{"purified_at": "{datetime.now(timezone.utc).isoformat()}", "reason": "{reason}"}}',
        datetime.now(timezone.utc),
        memory_id
    )
    
    return {
        "memory_id": memory_id,
        "status": "purified",
        "fossil": True,
        "purified_hash": purified[:20] + "...",
        "reason": reason,
        "note": "内容已哈希净化，拓扑关系完整保留",
    }


def verify_purified(content: str) -> bool:
    """检查内容是否已被净化"""
    return content.startswith("sha256:")


async def get_fossil_nodes(conn, tenant_id: str = "default", limit: int = 20) -> list:
    """
    查询化石节点列表 (已净化但拓扑保留的记忆)
    
    白皮书: "净化后的节点在 DAG 中显示为灰色化石状"
    """
    rows = await conn.fetch(
        """SELECT id, content, category, hall, metadata, 
           created_at, updated_at, reliability, heat_score
           FROM memories
           WHERE user_id=$1 AND is_deleted=TRUE AND content LIKE 'sha256:%'
           ORDER BY updated_at DESC LIMIT $2""",
        tenant_id, limit
    )
    
    import json as _json
    fossils = []
    for r in rows:
        meta = r["metadata"] or {}
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta)
            except:
                meta = {}
        
        fossils.append({
            "id": r["id"],
            "status": "fossilized",
            "hash_snippet": (r["content"] or "")[:30] + "...",
            "category": r["category"],
            "hall": r["hall"],
            "purified_at": meta.get("purified_at", ""),
            "reason": meta.get("reason", "unknown"),
            "created": str(r["created_at"])[:19],
            "reliability": r["reliability"],
            "heat": r["heat_score"],
        })
    
    return fossils
