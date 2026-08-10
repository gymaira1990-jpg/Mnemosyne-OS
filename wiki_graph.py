#!/usr/bin/env python3
"""wiki_graph — WIKI 图谱扩展检索通道 (v7.5 P1)

设计: 实体锚定 + 1跳 RELATED_TO
1. 查询 → jieba 分词 → entities 表匹配 (name ILIKE) → 候选实体 id
2. 沿 AGE RELATED_TO 边 1 跳 → 关联实体 id
3. 关联实体 → wiki_entities 表 → 出现在哪些 wiki 页面 (加分)
4. 返回 {page_id: graph_score, related_entities: [...]}

与向量/BM25 通道 RRF 融合 (search_wiki 调用)。
"""
import asyncio
import math


async def graph_expand(conn, query: str, user_id: str = "default", top_k: int = 10) -> dict:
    """图谱扩展: 返回 {page_scores: {page_id: score}, entities: [name,...]}"""
    try:
        import jieba
    except ImportError:
        return {"page_scores": {}, "entities": []}

    # 1. 查询分词 → entities 表匹配 (优先匹配有 wiki 关联的实体)
    tokens = [t.strip() for t in jieba.cut(query) if len(t.strip()) >= 2]
    if not tokens:
        return {"page_scores": {}, "entities": []}

    anchor_entities = []
    seen_ids = set()
    for tok in tokens[:6]:
        # 只取 2-12 字的实体名 (过滤超长全名), 且优先有 wiki 关联的
        rows = await conn.fetch(
            "SELECT DISTINCT e.id, e.name FROM entities e "
            "JOIN wiki_entities we ON we.entity_id = e.id "
            "WHERE e.user_id=$1 AND length(e.name) BETWEEN 2 AND 15 "
            "AND e.name ILIKE '%'||$2||'%' LIMIT 5",
            user_id, tok
        )
        for r in rows:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                anchor_entities.append({"id": r["id"], "name": r["name"]})

    if not anchor_entities:
        return {"page_scores": {}, "entities": []}

    anchor_ids = [e["id"] for e in anchor_entities]
    entities_found = [e["name"] for e in anchor_entities]

    # 2. AGE 1跳 RELATED_TO (按 entity_id, AGE 节点只有 entity_id 属性)
    related_ids = set()
    try:
        for aid in anchor_ids[:5]:
            rows = await conn.fetch(
                "SELECT * FROM cypher('mnemosyne_graph', $$ "
                "MATCH (a:Entity {entity_id: '%s'})-[r:RELATED_TO]->(b:Entity) "
                "RETURN b.entity_id $$) AS (v agtype)"
                % aid
            )
            for r in rows:
                v = str(r["v"])
                # 解析 agtype: {"id":..., "properties":{"entity_id":"123"}}
                import re
                m = re.search(r'"entity_id"\s*:\s*"(\d+)"', v)
                if m:
                    related_ids.add(int(m.group(1)))
    except Exception as e:
        # AGE 不可用时降级: 只用实体表匹配
        pass

    # 3. 关联实体 → wiki_entities 找页面
    all_ids = list(related_ids) + anchor_ids
    page_scores = {}
    if all_ids:
        rows = await conn.fetch(
            "SELECT we.wiki_page_id, count(*) AS n FROM wiki_entities we "
            "WHERE we.entity_id = ANY($1::bigint[]) GROUP BY we.wiki_page_id ORDER BY n DESC LIMIT $2",
            all_ids, top_k
        )
        total = sum(r["n"] for r in rows) or 1
        for r in rows:
            # 归一化: 页面关联实体数 / 总关联数
            page_scores[r["wiki_page_id"]] = round(r["n"] / total, 4)

    return {"page_scores": page_scores, "entities": entities_found[:10]}
