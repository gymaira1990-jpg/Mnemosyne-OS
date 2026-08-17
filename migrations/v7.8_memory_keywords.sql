-- v7.8: 主搜索真 BM25 — memory_keywords 关键词索引表
-- 主搜索 BM25 分量从 ILIKE(假) 升级为 jieba 分词 TF 加权(复用 wiki v7.5 方案)
CREATE TABLE IF NOT EXISTS memory_keywords (
    memory_id bigint NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    token      text  NOT NULL,
    freq       real  NOT NULL DEFAULT 1,
    PRIMARY KEY (memory_id, token)
);
CREATE INDEX IF NOT EXISTS idx_memory_keywords_token ON memory_keywords(token);
CREATE INDEX IF NOT EXISTS idx_memory_keywords_mid ON memory_keywords(memory_id);
