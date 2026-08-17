-- v7.7.0 程序性记忆翼: skill_assets + skill_keywords
-- 对齐 curator state 值域: active / stale / archived (绝不 DELETE, 只流转)
-- embedding 与 memories 同规格 vector(1024)

CREATE TABLE IF NOT EXISTS public.skill_assets (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    skill_name     TEXT NOT NULL,
    description    TEXT DEFAULT '',
    category       TEXT DEFAULT '',
    state          TEXT DEFAULT 'active'
                   CHECK (state IN ('active','stale','archived')),
    pinned         BOOLEAN DEFAULT FALSE,
    source_path    TEXT DEFAULT '',
    use_count      INTEGER DEFAULT 0,
    view_count     INTEGER DEFAULT 0,
    last_used_at   TIMESTAMPTZ,
    last_viewed_at TIMESTAMPTZ,
    archived_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    embedding      public.vector(1024),
    metadata       JSONB DEFAULT '{}',
    tenant_id      TEXT DEFAULT 'default',
    UNIQUE (tenant_id, skill_name)
);
CREATE INDEX IF NOT EXISTS idx_skill_state ON public.skill_assets (state);
CREATE INDEX IF NOT EXISTS idx_skill_usage ON public.skill_assets (use_count DESC);
CREATE INDEX IF NOT EXISTS idx_skill_embedding ON public.skill_assets
    USING hnsw (embedding public.vector_cosine_ops);

CREATE TABLE IF NOT EXISTS public.skill_keywords (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES public.skill_assets(id) ON DELETE CASCADE,
    token    TEXT NOT NULL,
    freq     INTEGER DEFAULT 1,
    tenant_id TEXT DEFAULT 'default',
    UNIQUE (skill_id, token)
);
CREATE INDEX IF NOT EXISTS idx_sk_token ON public.skill_keywords (token);
CREATE INDEX IF NOT EXISTS idx_sk_tenant_token ON public.skill_keywords (tenant_id, token);
