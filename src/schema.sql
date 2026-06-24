--
-- PostgreSQL database dump
--

\restrict li9qdJqWpqAY4NHBTx1BgZRsnjB2nkTGaOo8Nps9hLRcNuRiOobsAqLDIry6ZRL

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
-- Name: ag_catalog; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA ag_catalog;


--
-- Name: mnemosyne_graph; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA mnemosyne_graph;


--
-- Name: age; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS age WITH SCHEMA ag_catalog;


--
-- Name: EXTENSION age; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION age IS 'AGE database extension';


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
-- Name: beliefs; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.beliefs (
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
-- Name: beliefs_id_seq; Type: SEQUENCE; Schema: ag_catalog; Owner: -
--

CREATE SEQUENCE ag_catalog.beliefs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: beliefs_id_seq; Type: SEQUENCE OWNED BY; Schema: ag_catalog; Owner: -
--

ALTER SEQUENCE ag_catalog.beliefs_id_seq OWNED BY ag_catalog.beliefs.id;


--
-- Name: memory_chunks; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.memory_chunks (
    id integer NOT NULL,
    memory_id integer NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    embedding public.vector(1024),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: memory_chunks_id_seq; Type: SEQUENCE; Schema: ag_catalog; Owner: -
--

CREATE SEQUENCE ag_catalog.memory_chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: ag_catalog; Owner: -
--

ALTER SEQUENCE ag_catalog.memory_chunks_id_seq OWNED BY ag_catalog.memory_chunks.id;


--
-- Name: tmt_daily; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.tmt_daily (
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
-- Name: tmt_profiles; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.tmt_profiles (
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
-- Name: tmt_sessions; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.tmt_sessions (
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
-- Name: tmt_tree_edges; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.tmt_tree_edges (
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
-- Name: tmt_weekly; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.tmt_weekly (
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
-- Name: users; Type: TABLE; Schema: ag_catalog; Owner: -
--

CREATE TABLE ag_catalog.users (
    id integer NOT NULL,
    user_id character varying(255) NOT NULL,
    name character varying(255) DEFAULT ''::character varying,
    preferences jsonb DEFAULT '{}'::jsonb,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: ag_catalog; Owner: -
--

CREATE SEQUENCE ag_catalog.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: ag_catalog; Owner: -
--

ALTER SEQUENCE ag_catalog.users_id_seq OWNED BY ag_catalog.users.id;


--
-- Name: _ag_label_vertex; Type: TABLE; Schema: mnemosyne_graph; Owner: -
--

CREATE TABLE mnemosyne_graph._ag_label_vertex (
    id ag_catalog.graphid NOT NULL,
    properties ag_catalog.agtype DEFAULT ag_catalog.agtype_build_map() NOT NULL
);


--
-- Name: Entity; Type: TABLE; Schema: mnemosyne_graph; Owner: -
--

CREATE TABLE mnemosyne_graph."Entity" (
)
INHERITS (mnemosyne_graph._ag_label_vertex);


--
-- Name: Entity_id_seq; Type: SEQUENCE; Schema: mnemosyne_graph; Owner: -
--

CREATE SEQUENCE mnemosyne_graph."Entity_id_seq"
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 281474976710655
    CACHE 1;


--
-- Name: Entity_id_seq; Type: SEQUENCE OWNED BY; Schema: mnemosyne_graph; Owner: -
--

ALTER SEQUENCE mnemosyne_graph."Entity_id_seq" OWNED BY mnemosyne_graph."Entity".id;


--
-- Name: _ag_label_edge; Type: TABLE; Schema: mnemosyne_graph; Owner: -
--

CREATE TABLE mnemosyne_graph._ag_label_edge (
    id ag_catalog.graphid NOT NULL,
    start_id ag_catalog.graphid NOT NULL,
    end_id ag_catalog.graphid NOT NULL,
    properties ag_catalog.agtype DEFAULT ag_catalog.agtype_build_map() NOT NULL
);


--
-- Name: _ag_label_edge_id_seq; Type: SEQUENCE; Schema: mnemosyne_graph; Owner: -
--

CREATE SEQUENCE mnemosyne_graph._ag_label_edge_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 281474976710655
    CACHE 1;


--
-- Name: _ag_label_edge_id_seq; Type: SEQUENCE OWNED BY; Schema: mnemosyne_graph; Owner: -
--

ALTER SEQUENCE mnemosyne_graph._ag_label_edge_id_seq OWNED BY mnemosyne_graph._ag_label_edge.id;


--
-- Name: _ag_label_vertex_id_seq; Type: SEQUENCE; Schema: mnemosyne_graph; Owner: -
--

CREATE SEQUENCE mnemosyne_graph._ag_label_vertex_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 281474976710655
    CACHE 1;


--
-- Name: _ag_label_vertex_id_seq; Type: SEQUENCE OWNED BY; Schema: mnemosyne_graph; Owner: -
--

ALTER SEQUENCE mnemosyne_graph._ag_label_vertex_id_seq OWNED BY mnemosyne_graph._ag_label_vertex.id;


--
-- Name: _label_id_seq; Type: SEQUENCE; Schema: mnemosyne_graph; Owner: -
--

CREATE SEQUENCE mnemosyne_graph._label_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 65535
    CACHE 1
    CYCLE;


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
-- Name: gates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gates (
    id bigint NOT NULL,
    memory_id bigint NOT NULL,
    gate_type character varying(16) NOT NULL,
    passed boolean DEFAULT false NOT NULL,
    checks jsonb DEFAULT '{}'::jsonb,
    auditor_model character varying(64),
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT gates_gate_type_check CHECK (((gate_type)::text = ANY ((ARRAY['entry'::character varying, 'solution'::character varying, 'archive'::character varying])::text[])))
);


--
-- Name: gates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gates_id_seq OWNED BY public.gates.id;


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
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id bigint NOT NULL,
    project_id character varying(64) NOT NULL,
    tenant_id character varying(64) DEFAULT 'default'::character varying,
    name character varying(255) NOT NULL,
    description text,
    sandbox_config jsonb DEFAULT '{}'::jsonb,
    status character varying(16) DEFAULT 'active'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT projects_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'archived'::character varying, 'destroyed'::character varying])::text[])))
);


--
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.projects_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- Name: tmt_daily_old; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_daily_old (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    date date NOT NULL,
    summary text,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    themes jsonb DEFAULT '[]'::jsonb,
    session_ids uuid[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_profiles_old; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_profiles_old (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    period_start timestamp with time zone NOT NULL,
    period_end timestamp with time zone NOT NULL,
    profile_json jsonb DEFAULT '{}'::jsonb,
    summary text,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    is_active boolean DEFAULT true,
    previous_id uuid,
    weekly_ids uuid[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_sessions_old; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_sessions_old (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    summary text,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    fragment_ids integer[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tmt_weekly_old; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tmt_weekly_old (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    week_start date NOT NULL,
    week_end date NOT NULL,
    summary text,
    embedding public.vector(1024),
    heat_score double precision DEFAULT 0.5,
    patterns jsonb DEFAULT '[]'::jsonb,
    daily_ids uuid[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tool_archives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tool_archives (
    id bigint NOT NULL,
    archive_id character varying(64) NOT NULL,
    memory_id bigint,
    tool_name character varying(128) NOT NULL,
    params jsonb DEFAULT '{}'::jsonb,
    result text,
    success boolean,
    error_type character varying(64),
    knowledge_type character varying(16) DEFAULT 'skill'::character varying,
    session_id character varying(64),
    project_id bigint,
    duration_ms integer,
    tenant_id character varying(64) DEFAULT 'default'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT tool_archives_knowledge_type_check CHECK (((knowledge_type)::text = ANY ((ARRAY['skill'::character varying, 'pitfall'::character varying, 'observation'::character varying])::text[])))
);


--
-- Name: tool_archives_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tool_archives_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tool_archives_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tool_archives_id_seq OWNED BY public.tool_archives.id;


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
    updated_at timestamp without time zone DEFAULT now()
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
-- Name: beliefs id; Type: DEFAULT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.beliefs ALTER COLUMN id SET DEFAULT nextval('ag_catalog.beliefs_id_seq'::regclass);


--
-- Name: memory_chunks id; Type: DEFAULT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.memory_chunks ALTER COLUMN id SET DEFAULT nextval('ag_catalog.memory_chunks_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.users ALTER COLUMN id SET DEFAULT nextval('ag_catalog.users_id_seq'::regclass);


--
-- Name: Entity id; Type: DEFAULT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph."Entity" ALTER COLUMN id SET DEFAULT ag_catalog._graphid((ag_catalog._label_id('mnemosyne_graph'::name, 'Entity'::name))::integer, nextval('mnemosyne_graph."Entity_id_seq"'::regclass));


--
-- Name: Entity properties; Type: DEFAULT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph."Entity" ALTER COLUMN properties SET DEFAULT ag_catalog.agtype_build_map();


--
-- Name: _ag_label_edge id; Type: DEFAULT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph._ag_label_edge ALTER COLUMN id SET DEFAULT ag_catalog._graphid((ag_catalog._label_id('mnemosyne_graph'::name, '_ag_label_edge'::name))::integer, nextval('mnemosyne_graph._ag_label_edge_id_seq'::regclass));


--
-- Name: _ag_label_vertex id; Type: DEFAULT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph._ag_label_vertex ALTER COLUMN id SET DEFAULT ag_catalog._graphid((ag_catalog._label_id('mnemosyne_graph'::name, '_ag_label_vertex'::name))::integer, nextval('mnemosyne_graph._ag_label_vertex_id_seq'::regclass));


--
-- Name: entities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities ALTER COLUMN id SET DEFAULT nextval('public.entities_id_seq'::regclass);


--
-- Name: gates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gates ALTER COLUMN id SET DEFAULT nextval('public.gates_id_seq'::regclass);


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
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- Name: tool_archives id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_archives ALTER COLUMN id SET DEFAULT nextval('public.tool_archives_id_seq'::regclass);


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
-- Name: beliefs beliefs_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.beliefs
    ADD CONSTRAINT beliefs_pkey PRIMARY KEY (id);


--
-- Name: memory_chunks memory_chunks_memory_id_chunk_index_key; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.memory_chunks
    ADD CONSTRAINT memory_chunks_memory_id_chunk_index_key UNIQUE (memory_id, chunk_index);


--
-- Name: memory_chunks memory_chunks_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.memory_chunks
    ADD CONSTRAINT memory_chunks_pkey PRIMARY KEY (id);


--
-- Name: tmt_daily tmt_daily_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_daily
    ADD CONSTRAINT tmt_daily_pkey PRIMARY KEY (id);


--
-- Name: tmt_daily tmt_daily_user_id_date_key; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_daily
    ADD CONSTRAINT tmt_daily_user_id_date_key UNIQUE (user_id, date);


--
-- Name: tmt_profiles tmt_profiles_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_profiles
    ADD CONSTRAINT tmt_profiles_pkey PRIMARY KEY (id);


--
-- Name: tmt_sessions tmt_sessions_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_sessions
    ADD CONSTRAINT tmt_sessions_pkey PRIMARY KEY (id);


--
-- Name: tmt_tree_edges tmt_tree_edges_parent_level_parent_id_child_level_child_id_key; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_tree_edges
    ADD CONSTRAINT tmt_tree_edges_parent_level_parent_id_child_level_child_id_key UNIQUE (parent_level, parent_id, child_level, child_id);


--
-- Name: tmt_tree_edges tmt_tree_edges_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_tree_edges
    ADD CONSTRAINT tmt_tree_edges_pkey PRIMARY KEY (id);


--
-- Name: tmt_weekly tmt_weekly_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_weekly
    ADD CONSTRAINT tmt_weekly_pkey PRIMARY KEY (id);


--
-- Name: tmt_weekly tmt_weekly_user_id_week_start_key; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_weekly
    ADD CONSTRAINT tmt_weekly_user_id_week_start_key UNIQUE (user_id, week_start);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_user_id_key; Type: CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.users
    ADD CONSTRAINT users_user_id_key UNIQUE (user_id);


--
-- Name: Entity Entity_pkey; Type: CONSTRAINT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph."Entity"
    ADD CONSTRAINT "Entity_pkey" PRIMARY KEY (id);


--
-- Name: _ag_label_edge _ag_label_edge_pkey; Type: CONSTRAINT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph._ag_label_edge
    ADD CONSTRAINT _ag_label_edge_pkey PRIMARY KEY (id);


--
-- Name: _ag_label_vertex _ag_label_vertex_pkey; Type: CONSTRAINT; Schema: mnemosyne_graph; Owner: -
--

ALTER TABLE ONLY mnemosyne_graph._ag_label_vertex
    ADD CONSTRAINT _ag_label_vertex_pkey PRIMARY KEY (id);


--
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (id);


--
-- Name: gates gates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gates
    ADD CONSTRAINT gates_pkey PRIMARY KEY (id);


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
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: projects projects_project_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_project_id_key UNIQUE (project_id);


--
-- Name: tmt_daily_old tmt_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_daily_old
    ADD CONSTRAINT tmt_daily_pkey PRIMARY KEY (id);


--
-- Name: tmt_daily_old tmt_daily_user_id_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_daily_old
    ADD CONSTRAINT tmt_daily_user_id_date_key UNIQUE (user_id, date);


--
-- Name: tmt_profiles_old tmt_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_profiles_old
    ADD CONSTRAINT tmt_profiles_pkey PRIMARY KEY (id);


--
-- Name: tmt_sessions_old tmt_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_sessions_old
    ADD CONSTRAINT tmt_sessions_pkey PRIMARY KEY (id);


--
-- Name: tmt_weekly_old tmt_weekly_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_weekly_old
    ADD CONSTRAINT tmt_weekly_pkey PRIMARY KEY (id);


--
-- Name: tool_archives tool_archives_archive_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_archives
    ADD CONSTRAINT tool_archives_archive_id_key UNIQUE (archive_id);


--
-- Name: tool_archives tool_archives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_archives
    ADD CONSTRAINT tool_archives_pkey PRIMARY KEY (id);


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
-- Name: idx_beliefs_embedding; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_beliefs_embedding ON ag_catalog.beliefs USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: idx_beliefs_status; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_beliefs_status ON ag_catalog.beliefs USING btree (status);


--
-- Name: idx_beliefs_user; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_beliefs_user ON ag_catalog.beliefs USING btree (user_id);


--
-- Name: idx_memory_chunks_embedding; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_memory_chunks_embedding ON ag_catalog.memory_chunks USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_tmt_daily_heat; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_daily_heat ON ag_catalog.tmt_daily USING btree (user_id, date DESC);


--
-- Name: idx_tmt_daily_hnsw; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_daily_hnsw ON ag_catalog.tmt_daily USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_profiles_active; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_profiles_active ON ag_catalog.tmt_profiles USING btree (user_id, is_active);


--
-- Name: idx_tmt_profiles_hnsw; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_profiles_hnsw ON ag_catalog.tmt_profiles USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_sessions_heat; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_sessions_heat ON ag_catalog.tmt_sessions USING btree (user_id, heat_score DESC);


--
-- Name: idx_tmt_sessions_hnsw; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_sessions_hnsw ON ag_catalog.tmt_sessions USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: idx_tmt_weekly_heat; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_weekly_heat ON ag_catalog.tmt_weekly USING btree (user_id, week_start DESC);


--
-- Name: idx_tmt_weekly_hnsw; Type: INDEX; Schema: ag_catalog; Owner: -
--

CREATE INDEX idx_tmt_weekly_hnsw ON ag_catalog.tmt_weekly USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='200');


--
-- Name: _ag_label_edge_end_id_idx; Type: INDEX; Schema: mnemosyne_graph; Owner: -
--

CREATE INDEX _ag_label_edge_end_id_idx ON mnemosyne_graph._ag_label_edge USING btree (end_id);


--
-- Name: _ag_label_edge_start_id_idx; Type: INDEX; Schema: mnemosyne_graph; Owner: -
--

CREATE INDEX _ag_label_edge_start_id_idx ON mnemosyne_graph._ag_label_edge USING btree (start_id);


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

CREATE INDEX idx_gates_memory ON public.gates USING btree (memory_id);


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

CREATE INDEX idx_tmt_daily_user ON public.tmt_daily_old USING btree (user_id);


--
-- Name: idx_tmt_profiles_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_profiles_active ON public.tmt_profiles_old USING btree (user_id) WHERE (is_active = true);


--
-- Name: idx_tmt_profiles_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_profiles_user ON public.tmt_profiles_old USING btree (user_id);


--
-- Name: idx_tmt_sessions_embedding; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_sessions_embedding ON public.tmt_sessions_old USING ivfflat (embedding public.vector_cosine_ops);


--
-- Name: idx_tmt_sessions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_sessions_user ON public.tmt_sessions_old USING btree (user_id);


--
-- Name: idx_tmt_weekly_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tmt_weekly_user ON public.tmt_weekly_old USING btree (user_id);


--
-- Name: idx_tool_archives_tool; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tool_archives_tool ON public.tool_archives USING btree (tool_name, success);


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
-- Name: memory_chunks memory_chunks_memory_id_fkey; Type: FK CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.memory_chunks
    ADD CONSTRAINT memory_chunks_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id) ON DELETE CASCADE;


--
-- Name: tmt_profiles tmt_profiles_previous_id_fkey; Type: FK CONSTRAINT; Schema: ag_catalog; Owner: -
--

ALTER TABLE ONLY ag_catalog.tmt_profiles
    ADD CONSTRAINT tmt_profiles_previous_id_fkey FOREIGN KEY (previous_id) REFERENCES ag_catalog.tmt_profiles(id);


--
-- Name: gates gates_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gates
    ADD CONSTRAINT gates_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id);


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
-- Name: tmt_profiles_old tmt_profiles_previous_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tmt_profiles_old
    ADD CONSTRAINT tmt_profiles_previous_id_fkey FOREIGN KEY (previous_id) REFERENCES public.tmt_profiles_old(id);


--
-- Name: tool_archives tool_archives_memory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_archives
    ADD CONSTRAINT tool_archives_memory_id_fkey FOREIGN KEY (memory_id) REFERENCES public.memories(id);


--
-- Name: tool_archives tool_archives_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tool_archives
    ADD CONSTRAINT tool_archives_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: wiki_versions wiki_versions_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wiki_versions
    ADD CONSTRAINT wiki_versions_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.wiki_pages(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict li9qdJqWpqAY4NHBTx1BgZRsnjB2nkTGaOo8Nps9hLRcNuRiOobsAqLDIry6ZRL

