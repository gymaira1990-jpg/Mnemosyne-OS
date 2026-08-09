-- Mnemosyne v7.3 综合算法迁移 (2026-08-09)
-- 从遗忘转向整理优化+高效检索
-- 新增: 提及计数/综合Rank/快速指针表

-- 1. memories 新增字段 (幂等)
ALTER TABLE public.memories
  ADD COLUMN IF NOT EXISTS mention_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_mention timestamptz,
  ADD COLUMN IF NOT EXISTS rank_score numeric DEFAULT 0;

-- 2. 快速全盘指针表 (幂等)
CREATE TABLE IF NOT EXISTS public.memory_pointer (
  memory_id     bigint PRIMARY KEY REFERENCES public.memories(id) ON DELETE CASCADE,
  rank_score    numeric DEFAULT 0,
  palace_path   text,
  archive_no    text,
  mention_count integer DEFAULT 0,
  last_mention  timestamptz,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now()
);

-- 3. 指针表索引 (幂等)
CREATE INDEX IF NOT EXISTS idx_pointer_rank ON public.memory_pointer (rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_pointer_palace ON public.memory_pointer (palace_path);
CREATE INDEX IF NOT EXISTS idx_pointer_archive ON public.memory_pointer (archive_no);

-- 4. 存量初始化: 指针表回填 (非删除记忆)
INSERT INTO public.memory_pointer (memory_id, rank_score, palace_path, archive_no, mention_count, last_mention)
SELECT id,
       ROUND((0.3*storage_strength + 0.3*retrieval_strength + 0.2*heat_score*10 + 0.2*(LN(access_count+1)/LN(1001)) )::numeric, 4) AS rank_score,
       NULL AS palace_path,
       archive_no,
       access_count AS mention_count,
       COALESCE(last_accessed, created_at) AS last_mention
FROM public.memories
WHERE is_deleted = FALSE
ON CONFLICT (memory_id) DO NOTHING;

-- 5. 验证
SELECT '指针表回填' AS check_name;
SELECT count(*) AS pointer_rows FROM public.memory_pointer;
SELECT 'Rank 分布' AS check_name;
SELECT ROUND(rank_score) AS rank_bucket, count(*) FROM public.memory_pointer GROUP BY 1 ORDER BY 1;
