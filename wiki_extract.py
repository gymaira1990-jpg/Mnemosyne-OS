#!/usr/bin/env python3
"""wiki_extract — WIKI 页面 LLM 实体+关系抽取 (v7.4)

对 wiki_pages 中未抽取的页面:
1. LLM 抽取 {实体名, 类型, 描述, 关系[{target, relation}]}
2. upsert entities 表 (带 embedding + type)
3. 写 wiki_entities 关联 (page→entity, relation)
4. AGE 图: 页面 MENTIONS 实体

用法 (GZ):
    cd /opt/mnemosyne && venv/bin/python3 wiki_extract.py --batch 5
    venv/bin/python3 wiki_extract.py --batch 5 --dry-run
"""
import asyncio
import json
import os
import sys
import time

# 必须最先 load_env (core.config 在 import 时读环境变量)
from tmt.distill import load_env, PG_DSN
load_env()

import asyncpg  # noqa: E402
from core.llm import call_llm_json  # noqa: E402
from core.embedding import get_embedding_async  # noqa: E402

async def get_embedding(texts):
    return await get_embedding_async(texts)

USER_ID = "default"

PROMPT = """你是知识图谱抽取引擎。从下面的文章/论文中抽取核心实体与关系，输出严格 JSON。

要求:
- 只抽有实质意义的实体: 概念/理论/系统/人名/技术/架构/材料/地点 (不抽虚词)
- 每篇 8-20 个实体, 每个实体给: name(规范名), type(concept|theory|system|person|tech|architecture|material|place|other), description(一句话, ≤40字)
- 实体间的关系 5-15 条: [from](实体名), [relation](动词短语, ≤10字), [to](实体名)
- 关系两端的实体必须在实体列表内
- 输出格式: {"entities": [{"name":"","type":"","description":""}], "relations": [{"from":"","relation":"","to":""}]}
- 不要输出 JSON 以外的任何内容

文章内容:
{content}
"""


async def extract_page(conn, page):
    pid = page["id"]
    title = page["title"]
    content = (page["content"] or "")[:6000]  # 截断防超长
    prompt = PROMPT.replace("{content}", content)
    try:
        res = call_llm_json(prompt, tier=3)
        raw = res.get("content") if isinstance(res, dict) else None
        if isinstance(raw, str):
            data = json.loads(raw)
        elif isinstance(raw, dict):
            data = raw
        else:
            return {"page_id": pid, "status": "empty", "title": title}
        entities = data.get("entities", []) or []
        relations = data.get("relations", []) or []
        if not entities:
            return {"page_id": pid, "status": "no-entities", "title": title}

        # name → entity_id 映射
        name2id = {}
        for ent in entities:
            name = (ent.get("name") or "").strip()
            if not name:
                continue
            typ = ent.get("type") or "concept"
            desc = (ent.get("description") or "")[:200]
            row = await conn.fetchrow("SELECT id FROM entities WHERE user_id=$1 AND name=$2", USER_ID, name)
            if row:
                eid = row["id"]
                if desc:
                    await conn.execute("UPDATE entities SET type=$1, description=$2 WHERE id=$3", typ, desc, eid)
            else:
                try:
                    r_v = (await get_embedding([name]))[0]
                    v_str = "[" + ",".join(str(x) for x in r_v) + "]"
                    row = await conn.fetchrow(
                        "INSERT INTO entities (user_id, name, type, description, embedding) "
                        "VALUES ($1,$2,$3,$4,$5::vector) RETURNING id",
                        USER_ID, name, typ, desc, v_str
                    )
                    eid = row["id"]
                except Exception as e:
                    print(f"  [warn] entity {name} insert failed: {e}")
                    continue
            name2id[name] = eid
            # 页面关联
            await conn.execute(
                "INSERT INTO wiki_entities (wiki_page_id, entity_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                pid, eid
            )

        # 关系: 实体对之间建 AGE 边 (RELATED_TO) — 先查重再 MERGE (AGE 无边索引时 MERGE 可能重复)
        edge_count = 0
        for rel in relations:
            frm = (rel.get("from") or "").strip()
            to = (rel.get("to") or "").strip()
            rel_name = (rel.get("relation") or "related_to").strip()[:60]
            if frm in name2id and to in name2id and frm != to:
                try:
                    # 查重: 同三元组已存在则跳过 (2026-08-10: 清理 2257 重复边后固化)
                    exists = await conn.fetch(
                        "SELECT * FROM cypher('mnemosyne_graph', $$ "
                        "MATCH (a:Entity {entity_id: '%s'})-[r:RELATED_TO {relation: '%s'}]->(b:Entity {entity_id: '%s'}) "
                        "RETURN count(*) $$) AS (v agtype)"
                        % (name2id[frm], rel_name.replace("'", ""), name2id[to])
                    )
                    if exists and str(exists[0]["v"]).strip('"') != "0":
                        continue  # 已存在, 跳过
                    await conn.execute(
                        "SELECT * FROM cypher('mnemosyne_graph', $$ "
                        "MERGE (a:Entity {entity_id: '%s'}) "
                        "MERGE (b:Entity {entity_id: '%s'}) "
                        "MERGE (a)-[r:RELATED_TO {relation: '%s'}]->(b) $$) AS (v agtype)"
                        % (name2id[frm], name2id[to], rel_name.replace("'", ""))
                    )
                    edge_count += 1
                except Exception as e:
                    print(f"  [warn] edge {frm}-{rel_name}->{to} failed: {e}")

        # 页面→实体 MENTIONS 边 (MERGE 确保节点)
        try:
            await conn.execute(
                "SELECT * FROM cypher('mnemosyne_graph', $$ "
                "MERGE (m:WikiPage {page_id: '%s'}) $$) AS (v agtype)" % pid
            )
            for eid in name2id.values():
                await conn.execute(
                    "SELECT * FROM cypher('mnemosyne_graph', $$ "
                    "MATCH (m:WikiPage {page_id: '%s'}) WITH m "
                    "MERGE (e:Entity {entity_id: '%s'}) "
                    "MERGE (m)-[:MENTIONS]->(e) $$) AS (v agtype)"
                    % (pid, eid)
                )
        except Exception as e:
            print(f"  [warn] wiki mentions failed: {e}")

        # 标记已抽取
        await conn.execute("UPDATE wiki_pages SET extracted_at=now() WHERE id=$1", pid)
        return {"page_id": pid, "status": "ok", "title": title,
                "entities": len(name2id), "relations": edge_count}
    except Exception as e:
        return {"page_id": pid, "status": "error", "title": title, "error": str(e)[:200]}


async def init_age_connection(conn):
    try:
        await conn.execute("LOAD 'age'")
        await conn.execute("SET search_path = ag_catalog, public")
    except Exception:
        pass


async def main(batch: int, dry_run: bool):
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=3, init=init_age_connection)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, title, content FROM wiki_pages "
                "WHERE user_id=$1 AND content IS NOT NULL AND length(content)>200 AND extracted_at IS NULL "
                "ORDER BY id LIMIT $2",
                USER_ID, batch
            )
            if not rows:
                print("无待抽取页面")
                return
            if dry_run:
                print(f"[dry-run] 待抽取 {len(rows)} 页:")
                for r in rows:
                    print(f"  #{r['id']} {r['title']} ({len(r['content'])}ch)")
                return
            print(f"抽取 {len(rows)} 页 ...")
            for page in rows:
                start = time.time()
                r = await extract_page(conn, page)
                r["sec"] = round(time.time() - start, 1)
                print(json.dumps(r, ensure_ascii=False))
    finally:
        await pool.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.batch, args.dry_run))
