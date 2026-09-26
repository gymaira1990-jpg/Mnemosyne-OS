#!/usr/bin/env python3
"""
v8.0 S1-2 / S1-3 · 幂等键与记忆回收（GC）集成测试

需要一台装好 **v8.0 迁移** 的 PostgreSQL（默认 `postgresql:///mnemosyne_v8test`，
可用环境变量 `MNEMOSYNE_V8TEST_DSN` 覆盖）。库不可用或未跑迁移 → 整体 skip，
不影响 CI（与 `test_sql_integration.py` 同一策略）。

覆盖（每条都是「做了到底成不成」的判据，不是"跑通了"）:
  C1 干跑不动数据（最危险的反证：默认绝不能删东西）
  C2 真删只删该删的；受保护/被引用的**一条都不许少**
  C3 归档表拿到整行 + traces 快照
  C4 回滚凭证行数 == 删除行数（用 CSV 解析器数，不用 wc -l）
  C5 子表随主行级联清理
  C6 整批还原能把记忆与 traces 复原
  C7 唯一索引**真能拦住**重复指纹（反证：造违规样本）
  C8 窗口未到 / 未软删的**不进入候选**
"""
import asyncio
import csv
import os

import pytest

DSN = os.environ.get("MNEMOSYNE_V8TEST_DSN", "postgresql:///mnemosyne_v8test")

asyncio_marker = pytest.mark.skipif(
    os.environ.get("MNEMOSYNE_SKIP_DB_TESTS") == "1",
    reason="显式跳过数据库测试")

FIXTURE_SQL = """
-- ⚠️ TRUNCATE 列表必须包含夹具里插入的**所有**表 ——
--   漏了 entities 会让第二次跑撞 entities_pkey（实测踩到，表现为一串 UniqueViolationError）
TRUNCATE memories, memory_traces, tome_cards, memory_entities, memory_keywords,
         entities, beliefs, memories_archive, gc_log RESTART IDENTITY CASCADE;

-- ① 该回收: 5 条超窗 tombstone, 无引用 (id 1-5)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at, tier)
SELECT g, 'default', 'GC-PURGE '||g, 'knowledge', TRUE, NOW() - INTERVAL '60 days', 'L2'
FROM generate_series(1,5) g;

-- ② permanent 保护 (id 6)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at)
VALUES (6, 'default', 'PERMANENT', 'knowledge', TRUE, NOW() - INTERVAL '60 days');
INSERT INTO tome_cards (memory_id, title, retention) VALUES (6, '永久卡', 'permanent');

-- ③ pinned 保护 (id 7)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at, metadata)
VALUES (7, 'default', 'PINNED', 'knowledge', TRUE, NOW() - INTERVAL '60 days', '{"pinned":"true"}');

-- ④ 被信念引用 (id 8)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at)
VALUES (8, 'default', 'BELIEFREF', 'knowledge', TRUE, NOW() - INTERVAL '60 days');
INSERT INTO beliefs (id, user_id, content, evidence_memories)
VALUES (1, 'default', '引用#8', ARRAY[8]::bigint[]);

-- ⑤ 有存活子记忆 (id 9)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at)
VALUES (9, 'default', 'LIVECHILD', 'knowledge', TRUE, NOW() - INTERVAL '60 days');
INSERT INTO memories (id, user_id, content, category, is_deleted, parent_memory_id)
VALUES (90, 'default', '子', 'knowledge', FALSE, 9);

-- ⑥ 窗口未到 (id 10) / ⑦ 未软删 (id 11)
INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at)
VALUES (10, 'default', 'TOORECENT', 'knowledge', TRUE, NOW() - INTERVAL '5 days');
INSERT INTO memories (id, user_id, content, category, is_deleted)
VALUES (11, 'default', 'ALIVE', 'knowledge', FALSE);

-- ⑧ 给 3 号挂**四张**子表数据（验级联 + 验还原完整性）
--   ⚠️ 原夹具漏了 entities —— 正好是红队指出的「CASCADE 静默连带删除」那张表，
--      漏测导致「还原不完整」的缺陷没被发现。
INSERT INTO memory_traces (memory_id, action, details) VALUES (3,'stored','{"a":1}'), (3,'accessed','{"b":2}');
INSERT INTO memory_keywords (memory_id, token, freq) VALUES (3, '测试', 3);
INSERT INTO tome_cards (memory_id, title, retention) VALUES (3, '普通卡', 'short');
INSERT INTO entities (id, user_id, name, type) VALUES (1, 'default', '测试实体', 'concept');
INSERT INTO memory_entities (memory_id, entity_id) VALUES (3, 1);

-- ⚠️ 夹具用显式 id 插入 → 必须把序列推到 max(id)，否则后续不带 id 的 INSERT 撞 pkey
SELECT setval(pg_get_serial_sequence('memories', 'id'),
              GREATEST((SELECT COALESCE(max(id), 1) FROM memories), 1));
"""

PURGEABLE = {1, 2, 3, 4, 5}
PROTECTED = {6, 7, 8, 9}
UNTOUCHABLE = {10, 11, 90}


def _connect():
    import asyncpg
    return asyncpg.connect(DSN)


def _db_ready():
    async def probe():
        import asyncpg
        conn = await asyncpg.connect(DSN)
        try:
            cols = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='memories' AND column_name='dedup_fingerprint'")
            gc = await conn.fetchval("SELECT to_regclass('public.gc_log')")
            arc = await conn.fetchval("SELECT to_regclass('public.memories_archive')")
            return bool(cols) and gc is not None and arc is not None
        finally:
            await conn.close()
    try:
        return asyncio.run(probe())
    except Exception:
        return False


_needs_db = pytest.mark.skipif(not _db_ready(),
                               reason=f"v8.0 测试库不可用或未跑迁移: {DSN}")


def _setup():
    async def go():
        conn = await _connect()
        try:
            await conn.execute(FIXTURE_SQL)
        finally:
            await conn.close()
    asyncio.run(go())


def _fetch(sql, *args):
    async def go():
        conn = await _connect()
        try:
            return await conn.fetch(sql, *args)
        finally:
            await conn.close()
    return asyncio.run(go())


def _run_gc(*argv):
    """直接调 jobs.compaction.main 的等价路径（不起子进程，便于断言）。"""
    import argparse
    from jobs import compaction
    args = argparse.Namespace(
        apply=False, window_days=30, limit=500, dsn=DSN, csv=None,
        batch=None, vacuum=False, restore=None)
    for a in argv:
        k, v = a
        setattr(args, k, v)
    return asyncio.run(compaction.run(args))


@_needs_db
@asyncio_marker
def test_c1_dry_run_changes_nothing():
    """最危险的反证：默认干跑绝不能动数据。"""
    _setup()
    before = _fetch("SELECT count(*) AS c FROM memories")[0]["c"]
    rc = _run_gc()
    after = _fetch("SELECT count(*) AS c FROM memories")[0]["c"]
    assert rc == 0
    assert before == after == 12, "干跑后行数必须不变"
    assert _fetch("SELECT count(*) AS c FROM memories_archive")[0]["c"] == 0, "干跑不得写归档"
    log = _fetch("SELECT dry_run FROM gc_log ORDER BY id DESC LIMIT 1")
    assert log and log[0]["dry_run"] is True


@_needs_db
@asyncio_marker
def test_c2_apply_purges_only_purgeable():
    _setup()
    assert _run_gc(("apply", True)) == 0
    ids = {r["id"] for r in _fetch("SELECT id FROM memories")}
    assert not (PURGEABLE & ids), f"该删的没删干净: {PURGEABLE & ids}"
    assert PROTECTED <= ids, f"受保护/被引用的被误删: {PROTECTED - ids}"
    assert UNTOUCHABLE <= ids, f"不该入候选的被动过: {UNTOUCHABLE - ids}"


@_needs_db
@asyncio_marker
def test_c3_archive_has_rows_and_traces_snapshot():
    import json
    _setup()
    _run_gc(("apply", True))
    assert _fetch("SELECT count(*) AS c FROM memories_archive")[0]["c"] == 5
    raw = _fetch("SELECT _traces FROM memories_archive WHERE id=3")[0]["_traces"]
    # asyncpg 读 jsonb 返回 str → 必须 json.loads（项目既有坑，见 AGENTS 教训）
    t = json.loads(raw) if isinstance(raw, str) else raw
    assert len(t) == 2, "traces 快照必须完整进归档（CASCADE 会清掉原表行）"
    assert _fetch("SELECT count(*) AS c FROM memories_archive WHERE _archive_batch IS NULL")[0]["c"] == 0


@_needs_db
@asyncio_marker
def test_c4_rollback_voucher_rowcount_matches():
    """凭证行数必须等于删除行数 —— 用 CSV 解析器数（字段含换行时 wc -l 会数错）。"""
    _setup()
    csv_path = os.path.join(os.path.dirname(__file__), "_v8_gc_voucher.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)
    try:
        _run_gc(("apply", True), ("csv", csv_path))
        assert os.path.exists(csv_path)
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5
        assert {int(r["id"]) for r in rows} == PURGEABLE
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


@_needs_db
@asyncio_marker
def test_c5_child_rows_cascade():
    _setup()
    _run_gc(("apply", True))
    for tbl in ("memory_traces", "memory_keywords", "tome_cards"):
        n = _fetch(f"SELECT count(*) AS c FROM {tbl} WHERE memory_id=3")[0]["c"]
        assert n == 0, f"{tbl} 未随主行级联清理"


@_needs_db
@asyncio_marker
def test_c6_restore_recovers_memories_and_traces():
    _setup()
    _run_gc(("apply", True))
    batch = _fetch("SELECT batch FROM gc_log WHERE dry_run=FALSE ORDER BY id DESC LIMIT 1")[0]["batch"]
    assert _run_gc(("restore", batch)) == 0
    ids = {r["id"] for r in _fetch("SELECT id FROM memories")}
    assert PURGEABLE <= ids, "还原不完整"
    assert _fetch("SELECT count(*) AS c FROM memory_traces WHERE memory_id=3")[0]["c"] == 2
    # 凭证不销毁 —— 归档表仍在，可重复救援
    assert _fetch("SELECT count(*) AS c FROM memories_archive")[0]["c"] == 5


@_needs_db
@asyncio_marker
def test_c9_restore_is_complete_across_all_cascade_children():
    """v8.0.1 回归测试：还原必须重建**全部四张 CASCADE 子表**，不能只重建 memories。

    这一条来自真实缺陷（红队指出 → 我复现）：
      原实现只归档+还原 memories/traces，而 memory_entities / memory_keywords /
      tome_cards 会随主行 CASCADE 删除且**不被还原** →
      还原出来的是「僵尸记忆」：在库里，但 BM25 搜不到、没有著录卡片。

    判据：删前各子表计数 == 还原后各子表计数。任一表不一致即红。
    """
    _setup()
    before = {
        t: _fetch(f"SELECT count(*) AS c FROM {t} WHERE memory_id=3")[0]["c"]
        for t in ("memory_traces", "memory_entities", "memory_keywords", "tome_cards")
    }
    assert all(v > 0 for v in before.values()), f"夹具不完整，测不出问题: {before}"

    _run_gc(("apply", True))
    # 删后：四张子表都该被 CASCADE 清空
    for t in before:
        n = _fetch(f"SELECT count(*) AS c FROM {t} WHERE memory_id=3")[0]["c"]
        assert n == 0, f"{t} 未随主行级联清空"

    batch = _fetch("SELECT batch FROM gc_log WHERE dry_run=FALSE ORDER BY id DESC LIMIT 1")[0]["batch"]
    assert _run_gc(("restore", batch)) == 0

    after = {
        t: _fetch(f"SELECT count(*) AS c FROM {t} WHERE memory_id=3")[0]["c"]
        for t in before
    }
    assert after == before, f"还原不完整（僵尸记忆）: 删前 {before} vs 还原后 {after}"
    # 顺带验：CM 检索依赖的 keywords 必须真回来
    assert after["memory_keywords"] > 0, "keywords 没回来 → BM25 永远搜不到这条记忆"


@_needs_db
@asyncio_marker
def test_c10_voucher_survives_oversized_field():
    """回归（2026-09-26 生产实测缺陷）：content 超 csv 默认字段上限时，凭证回数行数不许把整批带走。

    真实缺陷（2026-09-26 生产实测）：`csv` 模块默认 `field_size_limit = 131072` 字节，
    而生产最长记忆 content 达 270448 **字符** ⇒ 凭证写完回数行数时抛
    `Error: field larger than field limit (131072)` → `--apply` 整批 exit=3。

    危险点有两层：
      ① 夹具全用短文本 ⇒ 本地全绿也测不出（“本地全绿 ≠ 路径正确”的又一例）；
      ② 报错发生在**事务内**、但 CSV 已落盘 ⇒ 出现「凭证存在、数据没删」的撒谎凭证。

    判据：带 270KB content 的批次必须 rc=0、删干净、凭证能被解析器读全。
    """
    _setup()
    big = "B" * 270_000
    _fetch("INSERT INTO memories (id, user_id, content, category, is_deleted, forgotten_at) "
           "VALUES (12, 'default', $1, 'knowledge', TRUE, NOW() - INTERVAL '60 days') RETURNING id",
           big)
    csv_path = os.path.join(os.path.dirname(__file__), "_v8_gc_voucher_big.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)
    try:
        rc = _run_gc(("apply", True), ("csv", csv_path))
        assert rc == 0, "超长字段把整批回收带崩了（field larger than field limit）"
        ids = {r["id"] for r in _fetch("SELECT id FROM memories")}
        assert not (PURGEABLE & ids) and 12 not in ids, "该删的没删干净"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(PURGEABLE) + 1, f"凭证行数不对: {len(rows)}"
        assert max(len(r["content"]) for r in rows) == 270_000, "超长行没进凭证"
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


@_needs_db
@asyncio_marker
def test_c11_rolled_back_run_leaves_no_voucher(monkeypatch):
    """反证：事务失败后**不得留下任何"像凭证"的文件**（撒谎凭证）。

    真实事故（2026-09-26 生产批次 GC-20260926）：作业在「凭证行数统计」处抛错 → 事务回滚、
    一条都没删；但凭证 CSV 已落盘 8.4MB —— 事后看像「已回收 549 条」。这类文件比"没有凭证"危险得多。

    判据：注入失败后 ①正式凭证不存在 ②半成品 `.part` 也不存在 ③库里数据一条没少。
    """
    _setup()
    from jobs import compaction

    csv_path = os.path.join(os.path.dirname(__file__), "_v8_gc_voucher_fail.csv")
    real = compaction.write_csv_voucher

    async def boom(conn, ids, path):
        await real(conn, ids, path)          # 先真写出来（模拟"已写盘"这一步已完成）
        raise RuntimeError("injected failure after voucher write")

    monkeypatch.setattr(compaction, "write_csv_voucher", boom)
    try:
        rc = _run_gc(("apply", True), ("csv", csv_path))
        assert rc == 3, "注入的失败必须被判定为失败（不能静默成功）"
        assert not os.path.exists(csv_path), "回滚后仍留下正式凭证 = 撒谎凭证"
        assert not os.path.exists(csv_path + ".part"), "半成品必须清掉，别留在磁盘上混淆"
        ids = {r["id"] for r in _fetch("SELECT id FROM memories")}
        assert PURGEABLE <= ids, f"回滚不干净，数据被删了: {PURGEABLE - ids}"
        assert _fetch("SELECT count(*) AS c FROM memories_archive")[0]["c"] == 0, "归档也不该留痕"
    finally:
        for p in (csv_path, csv_path + ".part"):
            if os.path.exists(p):
                os.remove(p)


@_needs_db
@asyncio_marker
def test_c12_successful_run_promotes_voucher_without_part_file():
    """正证：成功路径下凭证**转正**（正式文件名存在、`.part` 不残留）。"""
    _setup()
    csv_path = os.path.join(os.path.dirname(__file__), "_v8_gc_voucher_ok.csv")
    for p in (csv_path, csv_path + ".part"):
        if os.path.exists(p):
            os.remove(p)
    try:
        assert _run_gc(("apply", True), ("csv", csv_path)) == 0
        assert os.path.exists(csv_path), "成功路径必须产出正式凭证"
        assert not os.path.exists(csv_path + ".part"), "`.part` 不许残留（说明转正没执行）"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(PURGEABLE)
    finally:
        for p in (csv_path, csv_path + ".part"):
            if os.path.exists(p):
                os.remove(p)


@_needs_db
@asyncio_marker
def test_c7_unique_index_rejects_duplicate_fingerprint():
    """反证：只测"干净输入能进"不够，必须证明索引**真能拦住**重复。"""
    import asyncpg
    _setup()

    async def go():
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(
                "INSERT INTO memories (id,user_id,content,category,dedup_fingerprint) "
                "VALUES (900,'default','a','knowledge','FP-DUP')")
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO memories (id,user_id,content,category,dedup_fingerprint) "
                    "VALUES (901,'default','b','knowledge','FP-DUP')")
            # 历史行(NULL 指纹)不受影响 —— 这是"不回填历史"设计的前提
            await conn.execute("INSERT INTO memories (id,user_id,content,category) VALUES (902,'default','n1','knowledge')")
            await conn.execute("INSERT INTO memories (id,user_id,content,category) VALUES (903,'default','n2','knowledge')")
        finally:
            await conn.close()
    asyncio.run(go())


@_needs_db
@asyncio_marker
def test_c8_window_and_alive_excluded_from_candidates():
    """窗口未到 / 未软删 → 不进候选；且真删后它们仍原封不动。"""
    import argparse
    from jobs import compaction
    _setup()

    async def go():
        conn = await _connect()
        try:
            purge, refused = await compaction.select_batch(conn, 30, 500)
            pids = {r["id"] for r in purge}
            assert pids == PURGEABLE, f"候选集不对: {pids}"
            assert 10 not in pids and 11 not in pids
        finally:
            await conn.close()
    asyncio.run(go())
