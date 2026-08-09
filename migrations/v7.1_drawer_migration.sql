-- Mnemosyne v7.1 抽屉化迁移 (2026-08-09)
-- 生产库 ag_catalog? 否 — memories 在 public schema (已实测 \d public.memories 正常)
-- 但注意: 宫殿表(tome_cards/tmt_*) 在 ag_catalog; memories 在 public ✓

-- 1. 新增双抽屉字段 + 去重指纹 (幂等: IF NOT EXISTS)
ALTER TABLE public.memories
  ADD COLUMN IF NOT EXISTS temp_drawer varchar(10) DEFAULT 'normal',
  ADD COLUMN IF NOT EXISTS time_drawer varchar(10) DEFAULT 'recent',
  ADD COLUMN IF NOT EXISTS dedup_fingerprint varchar(64),
  ADD COLUMN IF NOT EXISTS full_content_archived text;

-- 2. 约束 (先删旧的再建, 幂等)
ALTER TABLE public.memories DROP CONSTRAINT IF EXISTS chk_temp_drawer;
ALTER TABLE public.memories ADD CONSTRAINT chk_temp_drawer
  CHECK (temp_drawer IN ('hot','normal','cool','frozen'));
ALTER TABLE public.memories DROP CONSTRAINT IF EXISTS chk_time_drawer;
ALTER TABLE public.memories ADD CONSTRAINT chk_time_drawer
  CHECK (time_drawer IN ('recent','mid','long'));

-- 3. 索引 (查询抽屉分布/遗忘候选用)
CREATE INDEX IF NOT EXISTS idx_memories_temp_drawer ON public.memories (temp_drawer) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_time_drawer ON public.memories (time_drawer) WHERE is_deleted = FALSE;
CREATE INDEX IF NOT EXISTS idx_memories_forget_candidate ON public.memories ((metadata->>'forget_candidate')) WHERE is_deleted = FALSE;

-- 4. 存量初始化: 按当前 heat_score + last_accessed 回填抽屉 (跑一次, 之后由 reflect 维护)
UPDATE public.memories SET temp_drawer = CASE
    WHEN heat_score >= 0.7 THEN 'hot'
    WHEN heat_score >= 0.3 THEN 'normal'
    WHEN heat_score >= 0.1 THEN 'cool'
    ELSE 'frozen'
  END
WHERE is_deleted = FALSE;

UPDATE public.memories SET time_drawer = CASE
    WHEN COALESCE(last_accessed, created_at) >= NOW() - INTERVAL '30 days' THEN 'recent'
    WHEN COALESCE(last_accessed, created_at) >= NOW() - INTERVAL '90 days' THEN 'mid'
    ELSE 'long'
  END
WHERE is_deleted = FALSE;

-- 5. 遗忘候选初始标记 (与 reflect 同规则)
UPDATE public.memories SET metadata = COALESCE(metadata,'{}'::jsonb) || '{"forget_candidate":true}'::jsonb
WHERE is_deleted = FALSE
  AND temp_drawer = 'frozen' AND time_drawer = 'long'
  AND COALESCE(metadata->>'pinned','false') != 'true'
  AND category != 'preference';

-- 6. 验证
SELECT '抽屉分布' AS check_name;
SELECT temp_drawer, COUNT(*) FROM public.memories WHERE is_deleted = FALSE GROUP BY 1 ORDER BY 1;
SELECT '时间抽屉分布' AS check_name;
SELECT time_drawer, COUNT(*) FROM public.memories WHERE is_deleted = FALSE GROUP BY 1 ORDER BY 1;
SELECT '遗忘候选' AS check_name;
SELECT COUNT(*) FROM public.memories
WHERE is_deleted = FALSE AND COALESCE(metadata->>'forget_candidate','false') = 'true';
