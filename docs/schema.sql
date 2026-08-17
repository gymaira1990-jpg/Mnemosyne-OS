--
-- PostgreSQL database dump
--

-- Dumped from database version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

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
    category text DEFAULT 'knowledge'::text,
    archive_no text,
    CONSTRAINT chk_memories_category CHECK (((category)::text = ANY ((ARRAY['knowledge'::character varying, 'pitfall'::character varying, 'reference'::character varying, 'project'::character varying, 'ops'::character varying, 'deploy'::character varying, 'preference'::character varying, 'session'::character varying, 'worklog'::character varying, 'temp'::character varying])::text[]))),
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
    temp_drawer character varying(10) DEFAULT 'normal'::character varying,
    time_drawer character varying(10) DEFAULT 'recent'::character varying,
    dedup_fingerprint character varying(64),
    full_content_archived text,
    storage_strength double precision DEFAULT 3,
    retrieval_strength double precision DEFAULT 3,
    mention_count integer DEFAULT 0,
    last_mention timestamp with time zone,
    rank_score numeric DEFAULT 0,
    CONSTRAINT chk_temp_drawer CHECK (((temp_drawer)::text = ANY ((ARRAY['hot'::character varying, 'normal'::character varying, 'cool'::character varying, 'frozen'::character varying])::text[]))),
    CONSTRAINT chk_time_drawer CHECK (((time_drawer)::text = ANY ((ARRAY['recent'::character varying, 'mid'::character varying, 'long'::character varying])::text[]))),
    CONSTRAINT chk_hall CHECK (((hall)::text = ANY ((ARRAY['research'::character varying, 'engineering'::character varying, 'archive'::character varying])::text[]))),
    CONSTRAINT chk_verification CHECK (((verification_status)::text = ANY ((ARRAY['pending'::character varying, 'passed'::character varying, 'failed'::character varying])::text[])))
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
    source_lost boolean DEFAULT false
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
-- Name: beliefs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.beliefs ALTER COLUMN id SET DEFAULT nextval('public.beliefs_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
--


--
--


--
--


--
--


--
--


--
--


--
--


--
--


--
-- Name: entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ALTER COLUMN id SET DEFAULT nextval('public.entities_id_seq'::regclass);


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
-- Name: beliefs beliefs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.beliefs
    ADD CONSTRAINT beliefs_pkey PRIMARY KEY (id);


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
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (id);


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
-- Name: memory_traces memory_traces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_traces
    ADD CONSTRAINT memory_traces_pkey PRIMARY KEY (id);


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
-- Name: idx_memory_chunks_embedding; Type: INDEX; Schema: public; Owner: -
--


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
--


--
--


--
--


--
--


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
-- Name: idx_gates_memory; Type: INDEX; Schema: public; Owner: -
--


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
-- Name: idx_memories_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_category ON public.memories USING btree (category);


--
-- Name: idx_memories_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_embedding ON public.memories USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_memories_heat_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_heat_score ON public.memories USING btree (heat_score);


--
-- Name: idx_memories_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_tier ON public.memories USING btree (tier);


--
-- Name: idx_memories_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memories_user ON public.memories USING btree (user_id);


--
-- Name: idx_memory_traces_memory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_memory_traces_memory ON public.memory_traces USING btree (memory_id);


--
-- Name: idx_tmt_daily_user; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tmt_profiles_active; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tmt_profiles_user; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tmt_sessions_embedding; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tmt_sessions_user; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tmt_weekly_user; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_tool_archives_tool; Type: INDEX; Schema: public; Owner: -
--


--
-- Name: idx_wiki_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_embedding ON public.wiki_pages USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_wiki_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wiki_user ON public.wiki_pages USING btree (user_id);


--
-- Name: idx_wv_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wv_page ON public.wiki_versions USING btree (page_id);


--
-- Name: tmt_profiles tmt_profiles_previous_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_profiles
    ADD CONSTRAINT tmt_profiles_previous_id_fkey FOREIGN KEY (previous_id) REFERENCES public.tmt_profiles(id);


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
-- Name: memory_traces memory_traces_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memory_traces
    ADD CONSTRAINT memory_traces_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id);


--
-- Name: wiki_versions wiki_versions_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions
    ADD CONSTRAINT wiki_versions_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.wiki_pages(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


--
-- v7.0 魔法记忆宫殿 (palace.py 建表)
--
SET search_path = public;

CREATE TABLE IF NOT EXISTS archive_taxonomy (
    id SERIAL PRIMARY KEY,
    wing TEXT NOT NULL,
    room TEXT NOT NULL,
    shelf TEXT DEFAULT '',
    name TEXT DEFAULT '',
    UNIQUE(wing, room, shelf)
);

CREATE TABLE IF NOT EXISTS tome_cards (
    memory_id BIGINT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    archive_no TEXT UNIQUE,
    wing TEXT, room TEXT, shelf TEXT,
    tags TEXT[] DEFAULT '{}',
    retention TEXT DEFAULT 'long',
    source_session TEXT DEFAULT '',
    created_by TEXT DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tome_wing_room ON tome_cards(wing, room);
CREATE INDEX IF NOT EXISTS idx_tome_tags ON tome_cards USING GIN(tags);


-- Name: wiki_entities; Type: TABLE; Schema: public
CREATE TABLE public.wiki_entities (
    id bigint NOT NULL,
    wiki_page_id bigint NOT NULL,
    entity_id bigint NOT NULL,
    relation text,
    created_at timestamp without time zone DEFAULT now()
);
ALTER TABLE public.wiki_entities ADD CONSTRAINT wiki_entities_pkey PRIMARY KEY (id);


-- ═══ v7.5-v7.8 增量表(2026-08-18 审计补齐: 新部署重建库必需) ═══
-- v7.5 检索优化 P0a: wiki 关键词索引表 (jieba 分词, 双通道 BM25)
CREATE TABLE IF NOT EXISTS public.wiki_keywords (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    page_id bigint NOT NULL REFERENCES public.wiki_pages(id) ON DELETE CASCADE,
    token text NOT NULL,
    freq integer DEFAULT 1,
    created_at timestamp without time zone DEFAULT now(),
    UNIQUE (page_id, token)
);

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

CREATE TABLE IF NOT EXISTS public.skill_keywords (
    id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    skill_id BIGINT NOT NULL REFERENCES public.skill_assets(id) ON DELETE CASCADE,
    token    TEXT NOT NULL,
    freq     INTEGER DEFAULT 1,
    tenant_id TEXT DEFAULT 'default',
    UNIQUE (skill_id, token)
);

-- 主搜索 BM25 分量从 ILIKE(假) 升级为 jieba 分词 TF 加权(复用 wiki v7.5 方案)
CREATE TABLE IF NOT EXISTS public.memory_keywords (
    memory_id bigint NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    token      text  NOT NULL,
    freq       real  NOT NULL DEFAULT 1,
    PRIMARY KEY (memory_id, token)
);

