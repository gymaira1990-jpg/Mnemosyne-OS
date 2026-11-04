#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v9.0.15 · 冲突「只标记、不裁决」的契约测试

为什么有这一条
--------------
旧实现在**写入时**就把语义相近的旧记忆 `valid_to=NOW()` 作废。外部白盒审阅指出：
判据是「语义近 + 措辞差得远」，而**两件不同的事很容易恰好同主题** —— 旧条被静默作废，
知识库悄悄变少，且没人知道少了什么。

9.0.15 改成：写入只打 `pending_review` 标记，作废必须经
`POST /api/v1/memories/conflicts/resolve` 由人确认。

本测试防两件事：
1. **写入路径不许再自动作废**（源码契约，防有人好心加回去）
2. **裁决接口真的只在 invalidate_old 时作废**，keep_both 一个字都不许动旧条（真库行为）
"""
import asyncio
import os
import re

import pytest

DSN = os.environ.get("MNEMOSYNE_V8TEST_DSN", "postgresql:///mnemosyne_v8test")
MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


# ── 1. 源码契约：写入路径不许出现「自动作废旧条」 ──
def test_write_path_does_not_auto_invalidate():
    """冲突分支里不许再出现 `valid_to = NOW()` —— 那是「静默作废」的原文。"""
    src = open(MAIN_PY, encoding="utf-8").read()
    m = re.search(r'elif conflict\["action"\] == "conflict":(.*?)# 正常存入', src, re.S)
    assert m, "main.py 的冲突分支结构变了 —— 请同步本测试"
    branch = m.group(1)
    assert "valid_to = NOW()" not in branch, "冲突分支又在自动作废旧记忆了（9.0.15 已改成只标记）"
    assert "pending_review" in branch, "冲突分支应打 pending_review 标记"
    assert "conflict_flagged" in branch, "应记录 conflict_flagged 供接口返回提示"


# ── 2. 真库行为：裁决接口只在被要求时作废 ──
async def _db_ready() -> bool:
    try:
        import asyncpg
        conn = await asyncpg.connect(DSN, timeout=3)
    except Exception:
        return False
    try:
        return await conn.fetchval("SELECT to_regclass('public.memories') IS NOT NULL")
    finally:
        await conn.close()


def _ready() -> bool:
    try:
        return asyncio.run(_db_ready())
    except Exception:
        return False


@pytest.mark.skipif(not _ready(), reason="测试库不可用（MNEMOSYNE_V8TEST_DSN）")
def test_resolve_only_invalidates_when_asked():
    import asyncpg
    import main

    async def run():
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=2)
        main.pool = pool           # 端点函数在调用时才读 main.pool
        uid = "pytest_conflict"
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE user_id=$1", uid)
                old_id = await conn.fetchval(
                    """INSERT INTO memories (user_id, content, category, tier, heat_score)
                       VALUES ($1, '端口是 8010', 'ops', 'L2', 0.5) RETURNING id""", uid)
                new_keep = await conn.fetchval(
                    """INSERT INTO memories (user_id, content, category, tier, heat_score, metadata)
                       VALUES ($1, '端口改成 8011 了', 'ops', 'L2', 0.5, $2::jsonb) RETURNING id""",
                    uid, '{"conflicts_with": %d, "conflict_type": "pending_review"}' % old_id)

            # A. 先列出来：应能看到 1 条待复核，且旧条仍然有效
            #    注意用的是 8.x 就存在的 GET /memories/conflicts（9.0.15 没新增同名路由 —— 影子实现会被老路由遮住）
            listing = await main.list_conflicts(user_id=uid, limit=20)
            assert listing["total"] == 1, listing
            assert listing["pending_review"] == 1, listing
            item = listing["conflicts"][0]
            assert item["id"] == new_keep
            assert item["conflict_type"] == "pending_review"
            async with pool.acquire() as conn:
                vt0 = await conn.fetchval("SELECT valid_to FROM memories WHERE id=$1", old_id)
            assert vt0 is None, "旧条此刻必须仍然有效（这就是本次修复的意义）"

            # B. keep_both：一个字段都不许动旧条
            r = await main.resolve_pending_conflict(
                main.ConflictResolveReq(user_id=uid, new_id=new_keep, action="keep_both"))
            assert r["old_invalidated"] is False
            async with pool.acquire() as conn:
                vt = await conn.fetchval("SELECT valid_to FROM memories WHERE id=$1", old_id)
                assert vt is None, "keep_both 竟然把旧条作废了"
                again = await conn.fetchval(
                    """SELECT count(*) FROM memories WHERE user_id=$1
                       AND metadata->>'conflict_type'='pending_review'""", uid)
                assert again == 0, "标记应已清除"

            # C. invalidate_old：这次才作废（人工确认 = 旧的自动行为）
            async with pool.acquire() as conn:
                new2 = await conn.fetchval(
                    """INSERT INTO memories (user_id, content, category, tier, heat_score, metadata)
                       VALUES ($1, '端口确定改成 8011', 'ops', 'L2', 0.5, $2::jsonb) RETURNING id""",
                    uid, '{"conflicts_with": %d, "conflict_type": "pending_review"}' % old_id)
            r2 = await main.resolve_pending_conflict(
                main.ConflictResolveReq(user_id=uid, new_id=new2, action="invalidate_old"))
            assert r2["old_invalidated"] is True
            async with pool.acquire() as conn:
                vt2 = await conn.fetchval("SELECT valid_to FROM memories WHERE id=$1", old_id)
                assert vt2 is not None, "人工确认后旧条应被作废"
                trace = await conn.fetchval(
                    "SELECT count(*) FROM memory_traces WHERE memory_id=$1 AND action='superseded'", old_id)
                assert trace >= 1, "作废应留 trace（可追溯）"
        finally:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE user_id=$1", uid)
            await pool.close()

    asyncio.run(run())


if __name__ == "__main__":
    print("源码契约：", "OK" if (test_write_path_does_not_auto_invalidate() or True) else "FAIL")
    if _ready():
        test_resolve_only_invalidates_when_asked()
        print("真库行为：OK")
    else:
        print("真库不可用，跳过行为测试")
