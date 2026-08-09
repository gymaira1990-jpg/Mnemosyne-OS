-- Mnemosyne v7.2 Bjork S/R 分离迁移 (2026-08-09)
-- 存储强度 S (1-10, 不衰减) / 检索强度 R (1-10, 指数衰减半衰期30天)
-- 与 v7.1 heat_score/temp_drawer 共存: S/R 是新一代抽屉依据, heat_score 保留兼容

-- 1. 新增 S/R 字段 (幂等)
ALTER TABLE public.memories
  ADD COLUMN IF NOT EXISTS storage_strength double precision DEFAULT 3,
  ADD COLUMN IF NOT EXISTS retrieval_strength double precision DEFAULT 3;

-- 2. 存量初始化: 基于 heat_score + category + access_count 回填 S
--    手动/重要类 (preference/pin) S=7; 知识类 S=5; 其余 S=3
--    R 初始 = S (后续由 reflect 按访问衰减)
UPDATE public.memories SET
  storage_strength = CASE
    WHEN COALESCE(metadata->>'pinned','false') = 'true' OR category = 'preference' THEN 7
    WHEN category IN ('knowledge','pitfall','reference') THEN 5
    ELSE 3
  END,
  retrieval_strength = CASE
    WHEN COALESCE(metadata->>'pinned','false') = 'true' OR category = 'preference' THEN 7
    WHEN category IN ('knowledge','pitfall','reference') THEN 5
    ELSE 3
  END
WHERE is_deleted = FALSE;

-- 3. 索引 (S/R 查询)
CREATE INDEX IF NOT EXISTS idx_memories_sr ON public.memories (storage_strength, retrieval_strength) WHERE is_deleted = FALSE;

-- 4. 验证
SELECT 'S/R 初始化分布' AS check_name;
SELECT storage_strength, COUNT(*) FROM public.memories WHERE is_deleted = FALSE GROUP BY 1 ORDER BY 1;
