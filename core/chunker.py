"""
Mnemosyne RAG Chunking Engine v1.0
长记忆 → 检索友好块，提升向量搜索精度

算法：
  1. 先按双换行（段落）分割
  2. 段落>500字 → 按句子边界切分
  3. 每个chunk 200-600字，50字重叠窗口
"""
import re
import logging
from typing import List

log = logging.getLogger("chunker")

CHUNK_SIZE = 500
CHUNK_MIN = 200
OVERLAP = 50
CHUNK_MIN_LENGTH = 300


def split_sentences(text: str) -> list:
    pattern = r'(?<=[。！？.!?\n])\s*'
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, min_length: int = CHUNK_MIN_LENGTH) -> list:
    if len(text) <= min_length:
        return [text]
    
    chunks = []
    paragraphs = re.split(r'\n\s*\n', text)
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(para) > CHUNK_SIZE:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            sentences = split_sentences(para)
            sub_chunk = ""
            for sent in sentences:
                if len(sub_chunk) + len(sent) > CHUNK_SIZE and len(sub_chunk) >= CHUNK_MIN:
                    chunks.append(sub_chunk.strip())
                    last_sent = split_sentences(sub_chunk)[-1] if split_sentences(sub_chunk) else ""
                    sub_chunk = last_sent + " " + sent if last_sent else sent
                else:
                    sub_chunk = (sub_chunk + " " + sent).strip() if sub_chunk else sent
            if sub_chunk:
                chunks.append(sub_chunk.strip())
        else:
            if len(current_chunk) + len(para) > CHUNK_SIZE and len(current_chunk) >= CHUNK_MIN:
                chunks.append(current_chunk.strip())
                overlap_text = current_chunk[-OVERLAP:] if len(current_chunk) > OVERLAP else current_chunk
                current_chunk = overlap_text + "\n" + para
            else:
                current_chunk = (current_chunk + "\n" + para).strip() if current_chunk else para
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    if len(chunks) == 1 and len(chunks[0]) <= CHUNK_SIZE + 200:
        return [text]
    
    return chunks


async def chunk_memory(pool, memory_id: int, embed_fn) -> dict:
    from datetime import datetime, timezone
    
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM memory_chunks WHERE memory_id=$1", memory_id)
        
        row = await conn.fetchrow(
            "SELECT content FROM memories WHERE id=$1 AND is_deleted=FALSE",
            memory_id
        )
        if not row or not row["content"]:
            return {"chunked": False, "reason": "not_found_or_empty"}
        
        text = row["content"]
        if len(text) <= CHUNK_MIN_LENGTH:
            return {"chunked": False, "reason": "too_short", "length": len(text)}
        
        chunks = chunk_text(text)
        if len(chunks) <= 1:
            return {"chunked": False, "reason": "single_chunk", "length": len(text)}
        
        chunk_texts = [c for c in chunks if c.strip()]
        embeddings = await embed_fn(chunk_texts)
        
        now = datetime.now(timezone.utc)
        for i, (ct, emb) in enumerate(zip(chunk_texts, embeddings)):
            vec_str = "[" + ",".join(str(x) for x in emb) + "]"
            await conn.execute(
                "INSERT INTO memory_chunks (memory_id, chunk_index, content, embedding, created_at) "
                "VALUES ($1,$2,$3,$4::vector,$5) "
                "ON CONFLICT (memory_id, chunk_index) DO UPDATE "
                "SET content=EXCLUDED.content, embedding=EXCLUDED.embedding",
                memory_id, i, ct, vec_str, now
            )
        
        return {"chunked": True, "chunk_count": len(chunk_texts), "original_length": len(text)}


async def chunk_all_unprocessed(pool, user_id: str, embed_fn, batch_size: int = 20) -> dict:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT m.id, m.content FROM memories m "
            "LEFT JOIN memory_chunks mc ON m.id = mc.memory_id "
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE "
            "AND length(m.content) > $2 "
            "AND mc.id IS NULL "
            "ORDER BY length(m.content) DESC "
            "LIMIT $3",
            user_id, CHUNK_MIN_LENGTH, batch_size
        )
        
        if not rows:
            return {"chunked": 0, "total_remaining": 0}
        
        total_chunks = 0
        for r in rows:
            result = await chunk_memory(pool, r["id"], embed_fn)
            if result.get("chunked"):
                total_chunks += result["chunk_count"]
        
        remaining = await conn.fetchrow(
            "SELECT count(*) FROM memories m "
            "LEFT JOIN memory_chunks mc ON m.id = mc.memory_id "
            "WHERE m.user_id=$1 AND m.is_deleted=FALSE "
            "AND length(m.content) > $2 AND mc.id IS NULL",
            user_id, CHUNK_MIN_LENGTH
        )
        
        return {"chunked_memories": len(rows), "total_chunks": total_chunks, "total_remaining": remaining["count"]}
