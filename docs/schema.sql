--
-- Mnemosyne OS · 数据库结构（对外部署用）
--
-- 用法（见 README Quick Start / INSTALL.md）：
--   sudo -u postgres createdb mnemosyne
--   sudo -u postgres psql -d mnemosyne -f docs/schema.sql
--
-- 说明：
--   · 由生产库 pg_dump --schema-only 导出，含 23 张表的全部索引与约束。
--   · 需要的扩展：pg_trgm、vector(pgvector)。Apache AGE 可选（实体图谱），本文件不含。
--   · 不含运维监控扩展（需超级用户，核心路径不依赖）。
--   · 不含任何数据：建库后是空的。
--
-- 2026-11-04 重导：旧版漏了 22 个索引（含 dedup_fingerprint 唯一索引），
--   现象是「照 README 建库 → 存第一条记忆就 500」。现已按生产库真实结构导出。
--

-- Dumped from database version 18.6 (Ubuntu 18.6-1.pgdg24.04+2)
-- Dumped by pg_dump version 18.6 (Ubuntu 18.6-1.pgdg24.04+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: archive_taxonomy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.archive_taxonomy (
    id integer NOT NULL,
    wing text NOT NULL,
    room text NOT NULL,
    shelf text DEFAULT ''::text,
    name text DEFAULT ''::text
);


--
-- Name: archive_taxonomy_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.archive_taxonomy_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: archive_taxonomy_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.archive_taxonomy_id_seq OWNED BY public.archive_taxonomy.id;


--
-- Name: beliefs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.beliefs (
    id bigint NOT NULL,
    user_id text NOT NULL,
    content text NOT NULL,
    confidence double precision DEFAULT 0.5,
    trajectory text[] DEFAULT '{}'::text[],
    evidence_memories bigint[],
    embedding public.vector(1024),
    valid_from timestamp with time zone DEFAULT now(),
    valid_to timestamp with time zone,
    invalid_at timestamp with time zone,
    status text DEFAULT 'tentative'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: beliefs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.beliefs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: beliefs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.beliefs_id_seq OWNED BY public.beliefs.id;


--
-- Name: entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities (
    id bigint NOT NULL,
    user_id text NOT NULL,
    name text NOT NULL,
    type text DEFAULT 'concept'::text,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding public.vector(1024),
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: entities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.entities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.entities_id_seq OWNED BY public.entities.id;


--
-- Name: gc_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gc_log (
    id bigint NOT NULL,
    run_at timestamp with time zone DEFAULT now() NOT NULL,
    batch text NOT NULL,
    dry_run boolean NOT NULL,
    candidates integer DEFAULT 0 NOT NULL,
    purged integer DEFAULT 0 NOT NULL,
    refused_ref integer DEFAULT 0 NOT NULL,
    traces_kept integer DEFAULT 0 NOT NULL,
    rollback_csv text
);


--
-- Name: gc_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gc_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gc_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gc_log_id_seq OWNED BY public.gc_log.id;


--
-- Name: media_memories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media_memories (
    id bigint NOT NULL,
    user_id text NOT NULL,
    project_id text,
    content text NOT NULL,
    media_type text NOT NULL,
    media_url text,
    media_hash text,
    embedding public.vector(1024),
    importance double precision DEFAULT 0.5,
    reliability double precision DEFAULT 0.5,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: media_memories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.media_memories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: media_memories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.media_memories_id_seq OWNED BY public.media_memories.id;


--
-- Name: memories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memories (
    id bigint NOT NULL,
    user_id text NOT NULL,
    project_id_old text,
    content text NOT NULL,
    category text DEFAULT 'fact'::text,
    embedding public.vector(1024),
    importance double precision DEFAULT 0.5,
    reliability double precision DEFAULT 0.5,
    tier text DEFAULT 'L2'::text,
    heat_score double precision DEFAULT 0.5,
    last_accessed timestamp with time zone,
    access_count integer DEFAULT 0,
    is_deleted boolean DEFAULT false,
    forgotten_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    valid_from timestamp with time zone DEFAULT now(),
    valid_to timestamp with time zone,
    invalid_at timestamp with time zone,
    tmt_level smallint DEFAULT 1,
    session_id uuid,
    turn_index integer DEFAULT 0,
    project_id bigint,
    hall character varying(16) DEFAULT 'research'::character varying,
    parent_memory_id bigint,
    verification_status character varying(16) DEFAULT 'pending'::character varying,
    archive_no text,
    temp_drawer character varying(10) DEFAULT 'normal'::character varying,
    time_drawer character varying(10) DEFAULT 'recent'::character varying,
    dedup_fingerprint character varying(64),
    full_content_archived text,
    storage_strength double precision DEFAULT 3,
    retrieval_strength double precision DEFAULT 3,
    mention_count integer DEFAULT 0,
    last_mention timestamp with time zone,
    rank_score numeric DEFAULT 0,
    CONSTRAINT chk_hall CHECK (((hall)::text = ANY (ARRAY[('research'::character varying)::text, ('engineering'::character varying)::text, ('archive'::character varying)::text]))),
    CONSTRAINT chk_memories_category CHECK ((category = ANY (ARRAY['knowledge'::text, 'pitfall'::text, 'reference'::text, 'project'::text, 'ops'::text, 'deploy'::text, 'preference'::text, 'session'::text, 'worklog'::text, 'temp'::text]))),
    CONSTRAINT chk_temp_drawer CHECK (((temp_drawer)::text = ANY (ARRAY[('hot'::character varying)::text, ('normal'::character varying)::text, ('cool'::character varying)::text, ('frozen'::character varying)::text]))),
    CONSTRAINT chk_time_drawer CHECK (((time_drawer)::text = ANY (ARRAY[('recent'::character varying)::text, ('mid'::character varying)::text, ('long'::character varying)::text]))),
    CONSTRAINT chk_verification CHECK (((verification_status)::text = ANY (ARRAY[('pending'::character varying)::text, ('passed'::character varying)::text, ('failed'::character varying)::text])))
);


--
-- Name: memories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memories_id_seq OWNED BY public.memories.id;


--
-- Name: memories_archive; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memories_archive (
    id bigint DEFAULT nextval('public.memories_id_seq'::regclass) CONSTRAINT memories_id_not_null NOT NULL,
    user_id text CONSTRAINT memories_user_id_not_null NOT NULL,
    project_id_old text,
    content text CONSTRAINT memories_content_not_null NOT NULL,
    category text DEFAULT 'fact'::text,
    embedding public.vector(1024),
    importance double precision DEFAULT 0.5,
    reliability double precision DEFAULT 0.5,
    tier text DEFAULT 'L2'::text,
    heat_score double precision DEFAULT 0.5,
    last_accessed timestamp with time zone,
    access_count integer DEFAULT 0,
    is_deleted boolean DEFAULT false,
    forgotten_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    valid_from timestamp with time zone DEFAULT now(),
    valid_to timestamp with time zone,
    invalid_at timestamp with time zone,
    tmt_level smallint DEFAULT 1,
    session_id uuid,
    turn_index integer DEFAULT 0,
    project_id bigint,
    hall character varying(16) DEFAULT 'research'::character varying,
    parent_memory_id bigint,
    verification_status character varying(16) DEFAULT 'pending'::character varying,
    archive_no text,
    temp_drawer character varying(10) DEFAULT 'normal'::character varying,
    time_drawer character varying(10) DEFAULT 'recent'::character varying,
    dedup_fingerprint character varying(64),
    full_content_archived text,
    storage_strength double precision DEFAULT 3,
    retrieval_strength double precision DEFAULT 3,
    mention_count integer DEFAULT 0,
    last_mention timestamp with time zone,
    rank_score numeric DEFAULT 0,
    _archived_at timestamp with time zone DEFAULT now(),
    _archive_batch text,
    _traces jsonb,
    _entities jsonb,
    _keywords jsonb,
    _tome_cards jsonb
);


--
-- Name: memory_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_entities (
    id bigint NOT NULL,
    memory_id bigint,
    entity_id bigint,
    relation text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: memory_entities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_entities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_entities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_entities_id_seq OWNED BY public.memory_entities.id;


--
-- Name: memory_keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_keywords (
    memory_id bigint NOT NULL,
    token text NOT NULL,
    freq real DEFAULT 1 NOT NULL
);


--
-- Name: memory_traces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memory_traces (
    id bigint NOT NULL,
    memory_id bigint,
    action text NOT NULL,
    details jsonb DEFAULT '{}'::jsonb,
    executed_at timestamp with time zone DEFAULT now()
);


--
-- Name: memory_traces_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.memory_traces_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_traces_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.memory_traces_id_seq OWNED BY public.memory_traces.id;


--
-- Name: skill_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_assets (
    id bigint NOT NULL,
    skill_name text NOT NULL,
    description text DEFAULT ''::text,
    category text DEFAULT ''::text,
    state text DEFAULT 'active'::text,
    pinned boolean DEFAULT false,
    source_path text DEFAULT ''::text,
    use_count integer DEFAULT 0,
    view_count integer DEFAULT 0,
    last_used_at timestamp with time zone,
    last_viewed_at timestamp with time zone,
    archived_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    embedding public.vector(1024),
    metadata jsonb DEFAULT '{}'::jsonb,
    tenant_id text DEFAULT 'default'::text,
    CONSTRAINT skill_assets_state_check CHECK ((state = ANY (ARRAY['active'::text, 'stale'::text, 'archived'::text])))
);


--
-- Name: skill_assets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.skill_assets ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.skill_assets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: skill_keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skill_keywords (
    id bigint NOT NULL,
    skill_id bigint NOT NULL,
    token text NOT NULL,
    freq integer DEFAULT 1,
    tenant_id text DEFAULT 'default'::text
);


--
-- Name: skill_keywords_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.skill_keywords ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.skill_keywords_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: tmt_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_daily (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    date date NOT NULL,
    summary text NOT NULL,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    themes jsonb DEFAULT '[]'::jsonb,
    session_ids uuid[] DEFAULT '{}'::uuid[],
    token_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    profile_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    summary text NOT NULL,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 1.0,
    is_active boolean DEFAULT true,
    previous_id uuid,
    weekly_ids uuid[] DEFAULT '{}'::uuid[],
    belief_ids integer[] DEFAULT '{}'::integer[],
    token_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    session_label character varying(255),
    summary text NOT NULL,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    start_time timestamp with time zone DEFAULT now() NOT NULL,
    end_time timestamp with time zone DEFAULT now() NOT NULL,
    fragment_ids integer[] DEFAULT '{}'::integer[],
    token_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_tree_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_tree_edges (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    parent_level smallint NOT NULL,
    parent_id text NOT NULL,
    child_level smallint NOT NULL,
    child_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT tmt_tree_edges_child_level_check CHECK (((child_level >= 1) AND (child_level <= 4))),
    CONSTRAINT tmt_tree_edges_parent_level_check CHECK (((parent_level >= 2) AND (parent_level <= 5)))
);


--
-- Name: tmt_weekly; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_weekly (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    week_start date NOT NULL,
    week_end date NOT NULL,
    summary text NOT NULL,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    patterns jsonb DEFAULT '[]'::jsonb,
    daily_ids uuid[] DEFAULT '{}'::uuid[],
    token_count integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: tome_cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tome_cards (
    memory_id bigint NOT NULL,
    title text NOT NULL,
    summary text DEFAULT ''::text,
    archive_no text,
    wing text,
    room text,
    shelf text,
    tags text[] DEFAULT '{}'::text[],
    retention text DEFAULT 'long'::text,
    source_session text DEFAULT ''::text,
    created_by text DEFAULT 'auto'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    name character varying(255) DEFAULT ''::character varying,
    preferences jsonb DEFAULT '{}'::jsonb,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: wiki_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wiki_entities (
    id bigint NOT NULL,
    wiki_page_id bigint NOT NULL,
    entity_id bigint NOT NULL,
    relation text,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: wiki_entities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.wiki_entities ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.wiki_entities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: wiki_keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wiki_keywords (
    id bigint NOT NULL,
    page_id bigint NOT NULL,
    token text NOT NULL,
    freq integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: wiki_keywords_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.wiki_keywords ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.wiki_keywords_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: wiki_pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wiki_pages (
    id bigint NOT NULL,
    user_id text NOT NULL,
    title text NOT NULL,
    content text,
    tags jsonb DEFAULT '[]'::jsonb,
    embedding public.vector(1024),
    version integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    source_path text,
    source_url text,
    content_hash text,
    source_type text DEFAULT 'memo'::text,
    source_lost boolean DEFAULT false,
    extracted_at timestamp without time zone
);


--
-- Name: wiki_pages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wiki_pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wiki_pages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wiki_pages_id_seq OWNED BY public.wiki_pages.id;


--
-- Name: wiki_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wiki_versions (
    id bigint NOT NULL,
    page_id bigint NOT NULL,
    content text,
    embedding public.vector(1024),
    version integer,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: wiki_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wiki_versions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wiki_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wiki_versions_id_seq OWNED BY public.wiki_versions.id;


--
-- Name: wiki_versions_page_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wiki_versions_page_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wiki_versions_page_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wiki_versions_page_id_seq OWNED BY public.wiki_versions.page_id;


--
-- Name: archive_taxonomy id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy ALTER COLUMN id SET DEFAULT nextval('public.archive_taxonomy_id_seq'::regclass);


--
-- Name: beliefs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.beliefs ALTER COLUMN id SET DEFAULT nextval('public.beliefs_id_seq'::regclass);


--
-- Name: entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ALTER COLUMN id SET DEFAULT nextval('public.entities_id_seq'::regclass);


--
-- Name: gc_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gc_log ALTER COLUMN id SET DEFAULT nextval('public.gc_log_id_seq'::regclass);


--
-- Name: media_memories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_memories ALTER COLUMN id SET DEFAULT nextval('public.media_memories_id_seq'::regclass);


--
-- Name: memories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories ALTER COLUMN id SET DEFAULT nextval('public.memories_id_seq'::regclass);


--
-- Name: memory_entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_entities ALTER COLUMN id SET DEFAULT nextval('public.memory_entities_id_seq'::regclass);


--
-- Name: memory_traces id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_traces ALTER COLUMN id SET DEFAULT nextval('public.memory_traces_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: wiki_pages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_pages ALTER COLUMN id SET DEFAULT nextval('public.wiki_pages_id_seq'::regclass);


--
-- Name: wiki_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions ALTER COLUMN id SET DEFAULT nextval('public.wiki_versions_id_seq'::regclass);


--
-- Name: wiki_versions page_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions ALTER COLUMN page_id SET DEFAULT nextval('public.wiki_versions_page_id_seq'::regclass);


--
-- Name: archive_taxonomy archive_taxonomy_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy
    ADD CONSTRAINT archive_taxonomy_pkey PRIMARY KEY (id);


--
-- Name: archive_taxonomy archive_taxonomy_wing_room_shelf_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.archive_taxonomy
    ADD CONSTRAINT archive_taxonomy_wing_room_shelf_key UNIQUE (wing, room, shelf);


--
-- Name: beliefs beliefs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.beliefs
    ADD CONSTRAINT beliefs_pkey PRIMARY KEY (id);


--
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (id);


--
-- Name: gc_log gc_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gc_log
    ADD CONSTRAINT gc_log_pkey PRIMARY KEY (id);


--
-- Name: media_memories media_memories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_memories
    ADD CONSTRAINT media_memories_pkey PRIMARY KEY (id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (id);


--
-- Name: memory_entities memory_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_entities
    ADD CONSTRAINT memory_entities_pkey PRIMARY KEY (id);


--
-- Name: memory_keywords memory_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_keywords
    ADD CONSTRAINT memory_keywords_pkey PRIMARY KEY (memory_id, token);


--
-- Name: memory_traces memory_traces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_traces
    ADD CONSTRAINT memory_traces_pkey PRIMARY KEY (id);


--
-- Name: skill_assets skill_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_assets
    ADD CONSTRAINT skill_assets_pkey PRIMARY KEY (id);


--
-- Name: skill_assets skill_assets_tenant_id_skill_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_assets
    ADD CONSTRAINT skill_assets_tenant_id_skill_name_key UNIQUE (tenant_id, skill_name);


--
-- Name: skill_keywords skill_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_keywords
    ADD CONSTRAINT skill_keywords_pkey PRIMARY KEY (id);


--
-- Name: skill_keywords skill_keywords_skill_id_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_keywords
    ADD CONSTRAINT skill_keywords_skill_id_token_key UNIQUE (skill_id, token);


--
-- Name: tmt_daily tmt_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_daily
    ADD CONSTRAINT tmt_daily_pkey PRIMARY KEY (id);


--
-- Name: tmt_daily tmt_daily_user_id_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_daily
    ADD CONSTRAINT tmt_daily_user_id_date_key UNIQUE (user_id, date);


--
-- Name: tmt_profiles tmt_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_profiles
    ADD CONSTRAINT tmt_profiles_pkey PRIMARY KEY (id);


--
-- Name: tmt_sessions tmt_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_sessions
    ADD CONSTRAINT tmt_sessions_pkey PRIMARY KEY (id);


--
-- Name: tmt_tree_edges tmt_tree_edges_parent_level_parent_id_child_level_child_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_tree_edges
    ADD CONSTRAINT tmt_tree_edges_parent_level_parent_id_child_level_child_id_key UNIQUE (parent_level, parent_id, child_level, child_id);


--
-- Name: tmt_tree_edges tmt_tree_edges_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_tree_edges
    ADD CONSTRAINT tmt_tree_edges_pkey PRIMARY KEY (id);


--
-- Name: tmt_weekly tmt_weekly_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_weekly
    ADD CONSTRAINT tmt_weekly_pkey PRIMARY KEY (id);


--
-- Name: tmt_weekly tmt_weekly_user_id_week_start_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_weekly
    ADD CONSTRAINT tmt_weekly_user_id_week_start_key UNIQUE (user_id, week_start);


--
-- Name: tome_cards tome_cards_archive_no_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tome_cards
    ADD CONSTRAINT tome_cards_archive_no_key UNIQUE (archive_no);


--
-- Name: tome_cards tome_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tome_cards
    ADD CONSTRAINT tome_cards_pkey PRIMARY KEY (memory_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_user_id_key UNIQUE (user_id);


--
-- Name: wiki_entities wiki_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_entities
    ADD CONSTRAINT wiki_entities_pkey PRIMARY KEY (id);


--
-- Name: wiki_keywords wiki_keywords_page_id_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_keywords
    ADD CONSTRAINT wiki_keywords_page_id_token_key UNIQUE (page_id, token);


--
-- Name: wiki_keywords wiki_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_keywords
    ADD CONSTRAINT wiki_keywords_pkey PRIMARY KEY (id);


--
-- Name: wiki_pages wiki_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_pages
    ADD CONSTRAINT wiki_pages_pkey PRIMARY KEY (id);


--
-- Name: wiki_versions wiki_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions
    ADD CONSTRAINT wiki_versions_pkey PRIMARY KEY (id);


--
-- Name: dedup_fingerprint_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX dedup_fingerprint_key ON public.memories USING btree (dedup_fingerprint) WHERE (dedup_fingerprint IS NOT NULL);


--
-- Name: idx_beliefs_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_beliefs_embedding ON public.beliefs USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_beliefs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_beliefs_status ON public.beliefs USING btree (status);


--
-- Name: idx_beliefs_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_beliefs_user ON public.beliefs USING btree (user_id);


--
-- Name: idx_entities_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_embedding ON public.entities USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_entities_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_type ON public.entities USING btree (type);


--
-- Name: idx_entities_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entities_user ON public.entities USING btree (user_id);


--
-- Name: idx_gc_log_run_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_gc_log_run_at ON public.gc_log USING btree (run_at DESC);


--
-- Name: idx_me_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_me_entity ON public.memory_entities USING btree (entity_id);


--
-- Name: idx_me_memory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_me_memory ON public.memory_entities USING btree (memory_id);


--
-- Name: idx_media_memories_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_media_memories_embedding ON public.media_memories USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_memories_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_active ON public.memories USING btree (user_id, is_deleted, created_at);


--
-- Name: idx_memories_archive_no; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_memories_archive_no ON public.memories USING btree (archive_no) WHERE (archive_no IS NOT NULL);


--
-- Name: idx_memories_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_category ON public.memories USING btree (category);


--
-- Name: idx_memories_drawers_join; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_drawers_join ON public.memories USING btree (temp_drawer, time_drawer) WHERE (is_deleted = false);


--
-- Name: idx_memories_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_embedding ON public.memories USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_memories_forget_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_forget_candidate ON public.memories USING btree (((metadata ->> 'forget_candidate'::text))) WHERE (is_deleted = false);


--
-- Name: idx_memories_heat_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_heat_score ON public.memories USING btree (heat_score);


--
-- Name: idx_memories_metadata_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_metadata_gin ON public.memories USING gin (metadata);


--
-- Name: idx_memories_sr; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_sr ON public.memories USING btree (storage_strength, retrieval_strength) WHERE (is_deleted = false);


--
-- Name: idx_memories_temp_drawer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_temp_drawer ON public.memories USING btree (temp_drawer) WHERE (is_deleted = false);


--
-- Name: idx_memories_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_tier ON public.memories USING btree (tier);


--
-- Name: idx_memories_time_drawer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_time_drawer ON public.memories USING btree (time_drawer) WHERE (is_deleted = false);


--
-- Name: idx_memories_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_user ON public.memories USING btree (user_id);


--
-- Name: idx_memory_keywords_mid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_keywords_mid ON public.memory_keywords USING btree (memory_id);


--
-- Name: idx_memory_keywords_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_keywords_token ON public.memory_keywords USING btree (token);


--
-- Name: idx_memory_traces_memory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_traces_memory ON public.memory_traces USING btree (memory_id);


--
-- Name: idx_sk_tenant_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sk_tenant_token ON public.skill_keywords USING btree (tenant_id, token);


--
-- Name: idx_sk_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sk_token ON public.skill_keywords USING btree (token);


--
-- Name: idx_skill_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skill_embedding ON public.skill_assets USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_skill_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skill_state ON public.skill_assets USING btree (state);


--
-- Name: idx_skill_usage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skill_usage ON public.skill_assets USING btree (use_count DESC);


--
-- Name: idx_tmt_daily_heat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_daily_heat ON public.tmt_daily USING btree (user_id, date DESC);


--
-- Name: idx_tmt_daily_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_daily_hnsw ON public.tmt_daily USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_profiles_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_profiles_active ON public.tmt_profiles USING btree (user_id, is_active);


--
-- Name: idx_tmt_profiles_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_profiles_hnsw ON public.tmt_profiles USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_sessions_heat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_sessions_heat ON public.tmt_sessions USING btree (user_id, heat_score DESC);


--
-- Name: idx_tmt_sessions_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_sessions_hnsw ON public.tmt_sessions USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_weekly_heat; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_weekly_heat ON public.tmt_weekly USING btree (user_id, week_start DESC);


--
-- Name: idx_tmt_weekly_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_weekly_hnsw ON public.tmt_weekly USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tome_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tome_tags ON public.tome_cards USING gin (tags);


--
-- Name: idx_tome_wing_room; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tome_wing_room ON public.tome_cards USING btree (wing, room);


--
-- Name: idx_we_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_we_entity ON public.wiki_entities USING btree (entity_id);


--
-- Name: idx_we_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_we_page ON public.wiki_entities USING btree (wiki_page_id);


--
-- Name: idx_wiki_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_embedding ON public.wiki_pages USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_wiki_source_path; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_source_path ON public.wiki_pages USING btree (source_path);


--
-- Name: idx_wiki_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_source_type ON public.wiki_pages USING btree (source_type);


--
-- Name: idx_wiki_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_user ON public.wiki_pages USING btree (user_id);


--
-- Name: idx_wk_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wk_page ON public.wiki_keywords USING btree (page_id);


--
-- Name: idx_wk_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wk_token ON public.wiki_keywords USING btree (token);


--
-- Name: idx_wv_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wv_page ON public.wiki_versions USING btree (page_id);


--
-- Name: memory_entities memory_entities_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_entities
    ADD CONSTRAINT memory_entities_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: memory_entities memory_entities_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_entities
    ADD CONSTRAINT memory_entities_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id) ON DELETE CASCADE;


--
-- Name: memory_keywords memory_keywords_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_keywords
    ADD CONSTRAINT memory_keywords_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id) ON DELETE CASCADE;


--
-- Name: memory_traces memory_traces_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_traces
    ADD CONSTRAINT memory_traces_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id) ON DELETE CASCADE;


--
-- Name: skill_keywords skill_keywords_skill_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skill_keywords
    ADD CONSTRAINT skill_keywords_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES public.skill_assets(id) ON DELETE CASCADE;


--
-- Name: tmt_profiles tmt_profiles_previous_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_profiles
    ADD CONSTRAINT tmt_profiles_previous_id_fkey FOREIGN KEY (previous_id) REFERENCES public.tmt_profiles(id);


--
-- Name: tome_cards tome_cards_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tome_cards
    ADD CONSTRAINT tome_cards_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id) ON DELETE CASCADE;


--
-- Name: wiki_entities wiki_entities_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_entities
    ADD CONSTRAINT wiki_entities_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: wiki_entities wiki_entities_wiki_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_entities
    ADD CONSTRAINT wiki_entities_wiki_page_id_fkey FOREIGN KEY (wiki_page_id) REFERENCES public.wiki_pages(id) ON DELETE CASCADE;


--
-- Name: wiki_keywords wiki_keywords_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_keywords
    ADD CONSTRAINT wiki_keywords_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.wiki_pages(id) ON DELETE CASCADE;


--
-- Name: wiki_versions wiki_versions_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions
    ADD CONSTRAINT wiki_versions_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.wiki_pages(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

