-- 2026-11-07 · 裁决标签表（v9.0.24）
--
-- 为什么建这张表：召回「拿不准就问人」之后，人的裁决必须落下来，否则问完就散了。
-- 这张表是「早期 AI 数据标注员」那条线的物理载体，一份数据两个用途：
--   1. 调权：选中 → heat/access 上升；被否 → 下降（越用越准的燃料）
--   2. 出题：一条 label = 一条**天然的评测用例**（query + 正确 archive_no），
--      直接补进 golden set，下次用尺子量——闭环才成立。
--
-- 只记「人做过选择」的事实，不记未发生的事；被否的候选留在 candidates 里可复盘。

CREATE TABLE IF NOT EXISTS memory_labels (
    id            bigserial PRIMARY KEY,
    user_id       text        NOT NULL DEFAULT 'default',
    query         text        NOT NULL,
    chosen_id     bigint      REFERENCES memories(id) ON DELETE SET NULL,
    chosen_no     text,                              -- 选中的档号（有就记，方便直接生成评测题）
    candidates    jsonb       NOT NULL DEFAULT '[]'::jsonb,  -- 当时摆给人看的候选快照
    margin        double precision,                  -- 当时的求证阈值，便于复盘「当时有多模糊」
    source        text        NOT NULL DEFAULT 'confirm',    -- confirm | manual | eval
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_labels_user_created
    ON memory_labels (user_id, created_at DESC);

-- 导出评测用例用：只取「人明确选了某一条」的记录
CREATE INDEX IF NOT EXISTS idx_memory_labels_chosen
    ON memory_labels (chosen_id) WHERE chosen_id IS NOT NULL;
