-- ══════════════════════════════════════════════════════════════════════════════
-- Mnemosyne OS v8.0 · 迁移
--   写入原子性配套 / 幂等键唯一索引 / 记忆回收(GC)配套
--
-- 日期    : 2026-09-25
-- 提案    : P-20260925-01  (openspec/changes/2026-09-25-v8-memory-os/proposal.md)
-- ADR     : docs/adr/0002-文件系统机制取舍与触发器.md
-- 幂等性  : 全部 IF NOT EXISTS / 条件判断 —— 可重复执行, 不报错
-- 回滚    : 见文件末尾「回滚段」
-- ══════════════════════════════════════════════════════════════════════════════


-- ─────────────────────────────────────────────────────────────────────────────
-- S1-2 · 幂等键: dedup_fingerprint 唯一索引
-- ─────────────────────────────────────────────────────────────────────────────
-- 现状【已查证 2026-09-25 生产实测】: memories 16,595 行, dedup_fingerprint 非空 **0** 行
--   → 该列自 v7.1 加入后从未被写入, 无幂等能力。
--
-- 决策: **不回填历史指纹**。三条理由 ——
--   (a) PostgreSQL 唯一索引**忽略 NULL** → 直接建索引不会因历史重复而失败;
--   (b) 回填会把历史重复行(实测 132 组同 content)暴露给唯一索引 → 建索引**可能失败**;
--   (c) 历史语义去重本就由 `detect_conflict()` 的 merge/conflict 路径负责, 与此键职责不重叠。
--
-- 效果: 新写入必带指纹 → 崩溃重试 / 端云断线重发 / 重复 POST **不再产生新行**, 返回原 id。
CREATE UNIQUE INDEX IF NOT EXISTS dedup_fingerprint_key
    ON memories (dedup_fingerprint)
    WHERE dedup_fingerprint IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- S1-3 · 冷归档表: 物理删除之前的**可恢复凭证**
-- ─────────────────────────────────────────────────────────────────────────────
-- 设计: 与 memories **同构**(LIKE) + 三个账务列。
--   _archived_at   归档时刻
--   _archive_batch 批次号(与 gc_log.batch 对应, 支持整批还原)
--   _traces        该记忆的 memory_traces 快照(jsonb) —— 因为 CASCADE 会随主行清掉 traces
-- ⚠️ v8.0.1 补正：**必须把 CASCADE 子表一起快照**，否则还原出来是「僵尸记忆」
--   实测（2026-09-25，红队指出后复现）：删前 keywords=1/tome_cards=1 → 删后 0/0 →
--   --restore 还原后 memories 回来了，但 keywords/tome_cards 仍是 0
--   → 记忆在库里，却 BM25 搜不到、没有著录卡片。
--   根因：原实现只归档 memories + traces，而 memory_entities / memory_keywords /
--   tome_cards 三张表都挂在 memories 上是 ON DELETE CASCADE，会**静默连带删除**。
CREATE TABLE IF NOT EXISTS memories_archive (LIKE memories INCLUDING DEFAULTS);
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _archived_at   timestamptz DEFAULT NOW();
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _archive_batch text;
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _traces        jsonb;
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _entities      jsonb;  -- memory_entities 快照
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _keywords      jsonb;  -- memory_keywords 快照(BM25)
ALTER TABLE memories_archive ADD COLUMN IF NOT EXISTS _tome_cards    jsonb;  -- tome_cards 快照(著录卡片)


-- ─────────────────────────────────────────────────────────────────────────────
-- S1-3 · GC 台账: 每一次回收都可审计、可复盘
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gc_log (
    id           bigserial   PRIMARY KEY,
    run_at       timestamptz NOT NULL DEFAULT NOW(),
    batch        text        NOT NULL,
    dry_run      boolean     NOT NULL,
    candidates   integer     NOT NULL DEFAULT 0,   -- 进入窗口的候选数
    purged       integer     NOT NULL DEFAULT 0,   -- 实际物理删除数
    refused_ref  integer     NOT NULL DEFAULT 0,   -- 因仍被引用而**拒绝回收**数
    traces_kept  integer     NOT NULL DEFAULT 0,   -- 一并归档的 traces 行数
    rollback_csv text                              -- 回滚凭证文件路径
);

CREATE INDEX IF NOT EXISTS idx_gc_log_run_at ON gc_log (run_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- S1-3 · memory_traces 外键改为 ON DELETE CASCADE
-- ─────────────────────────────────────────────────────────────────────────────
-- 现状【已查证】: memory_traces_memory_id_fkey = FOREIGN KEY (memory_id) REFERENCES memories(id)
--                 即 **NO ACTION** → 物理删 memories 时会被 traces 挡住, 回收根本走不完。
-- 修法: 改 CASCADE。安全性由 compaction 作业保证 —— 它在删除前把 traces 快照
--       写进 memories_archive._traces, 所以 CASCADE 清掉的是**已归档副本**。
DO $$
DECLARE orphans bigint;
BEGIN
    -- 先验: 有孤儿则不能加约束(与 project-governance 教训一致: 加约束前先查孤儿)
    SELECT count(*) INTO orphans
    FROM memory_traces t LEFT JOIN memories m ON m.id = t.memory_id
    WHERE m.id IS NULL;
    IF orphans > 0 THEN
        RAISE EXCEPTION '存在 % 条孤儿 memory_traces, 请先清理再加 CASCADE 约束', orphans;
    END IF;

    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conname = 'memory_traces_memory_id_fkey' AND confdeltype <> 'c') THEN
        ALTER TABLE memory_traces DROP CONSTRAINT memory_traces_memory_id_fkey;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'memory_traces_memory_id_fkey') THEN
        ALTER TABLE memory_traces
            ADD CONSTRAINT memory_traces_memory_id_fkey
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE;
    END IF;
END $$;


-- ─────────────────────────────────────────────────────────────────────────────
-- 回滚段（手工执行, 不在本迁移内自动跑）
-- ─────────────────────────────────────────────────────────────────────────────
-- DROP INDEX IF EXISTS dedup_fingerprint_key;
-- ALTER TABLE memory_traces DROP CONSTRAINT memory_traces_memory_id_fkey;
-- ALTER TABLE memory_traces ADD CONSTRAINT memory_traces_memory_id_fkey
--     FOREIGN KEY (memory_id) REFERENCES memories(id);          -- 回到 NO ACTION
-- 冷归档表与台账**不建议删**（它们是删除凭证的载体）:
-- DROP TABLE IF EXISTS gc_log;  DROP TABLE IF EXISTS memories_archive;
