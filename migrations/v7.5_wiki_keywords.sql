-- v7.5 检索优化 P0a: wiki 关键词索引表 (jieba 分词, 双通道 BM25)
CREATE TABLE IF NOT EXISTS public.wiki_keywords (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES public.wiki_pages(id) ON DELETE CASCADE,
    token text NOT NULL,
    freq integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT now(),
    UNIQUE (page_id, token)
);
CREATE INDEX IF NOT EXISTS idx_wk_page ON public.wiki_keywords (page_id);
CREATE INDEX IF NOT EXISTS idx_wk_token ON public.wiki_keywords (token);
