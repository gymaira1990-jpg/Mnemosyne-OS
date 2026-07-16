# 🏛️ Mnemosyne OS — Cognitive Memory Operating System

> *A memory system that distills, organizes, and ages knowledge — not just stores it.*

<p align="center">
  <img src="https://img.shields.io/badge/version-5.3.2-brightgreen" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="license">
  <img src="https://img.shields.io/badge/python-3.12+-blue" alt="python">
  <img src="https://img.shields.io/badge/status-stable-success" alt="status">
  <img src="https://img.shields.io/badge/DB-PostgreSQL%2016%20%2B%20pgvector-336791" alt="postgres">
  <img src="https://img.shields.io/badge/graph-Apache%20AGE-forestgreen" alt="graph">
</p>

<p align="center">
  <img src="docs/poster.png" alt="Mnemosyne OS Architecture" width="720">
</p>

---

## Why This Exists

Vector databases store embeddings. RAG retrieves chunks. But neither **understands** your memory.

Mnemosyne OS is a **cognitive memory system** designed for AI agents. It doesn't just save — it **distills** raw conversations into sessions, daily summaries, weekly patterns, and user profiles. Knowledge flows through a three-hall lifecycle (research → engineering → archive). Memories naturally decay when unused, and important ones resurface. It's your agent's long-term memory cortex, not a key-value store.

| | Chroma / Pinecone | Mem0 | **Mnemosyne OS** |
|---|---|---|---|
| Embedding search | ✅ | ✅ | ✅ (1024d HNSW) |
| Full-text search | ❌ | ❌ | ✅ (BM25 + ILIKE) |
| Time decay scoring | ❌ | ❌ | ✅ (7/30/90 day tiers) |
| Auto-distillation | ❌ | ❌ | ✅ (L1→L5 TMT pipeline) |
| Knowledge graph | ❌ | ❌ | ✅ (Apache AGE, Cypher) |
| Offline sync | ❌ | ❌ | ✅ (SQLite↔PG) |
| Agent-native | ❌ | ❌ | ✅ (Hermes 15-tool MCP) |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Mnemosyne OS v5.3                    │
│                                                   │
│  L5 Profile  ←── "Who you are"                    │
│  L4 Weekly   ←── "This week's patterns"           │
│  L3 Daily    ←── "Today's takeaways"              │
│  L2 Session  ←── "One conversation's thread"      │
│  L1 Fragment ←── "A single memory"                │
│                                                   │
│  🏛️  Research → Engineering → Archive             │
│  🔍  Vector + BM25 + Temporal + Trust + Heat      │
│  🔗  Entity graph (Apache AGE / Cypher)            │
│  ✂️  Smart chunking (50-char overlap)             │
│  ☁️  Edge-cloud sync (SQLite ↔ PostgreSQL)        │
│  💬  Session sync (Hermes state.db → PG)          │
└─────────────────────────────────────────────────┘
```

---

## Key Features

### 🧠 Five-Layer Temporal Memory Tree (TMT)
Conversations don't stay flat. Every session end triggers auto-distillation: fragments → sessions → daily → weekly → profile. Inspired by arXiv 2601.02845.

### 🏛️ Three-Hall Knowledge Lifecycle
Research (speculative) → Engineering (battle-tested) → Archive (canonical). Gates between halls validate before promotion.

### 🔍 Five-Dimensional Search
`0.40×semantic + 0.15×BM25 + 0.15×temporal + 0.15×trust + 0.15×heat`. Pure time-ordered search also supported (`sort=created_at`).

### 🤖 Agent-Native Integration
15-tool MCP bridge for Hermes Agent. Memory Provider with 10 lifecycle hooks: `on_session_end`, `on_turn_start`, `prefetch`, `on_pre_compress`, `on_delegation`, and more.

### 💬 Permanent Conversation History
Every Hermes session syncs to `conversation_messages` table. Frontend can load history like a chat app — sessions, messages, pagination. Survives `/new`, survives crashes.

### 🔗 Knowledge Graph
Entities auto-extracted with LLM + regex. Stored as Apache AGE graph nodes. Multi-hop traversal for relational recall.

### ☁️ Edge-Cloud Resilience
WSL offline? Messages cache to local SQLite. Back online? Silent push to GZ PostgreSQL. 7 cron jobs keep everything ticking.

---

## Quick Start

### Hermes Agent (recommended)

```bash
# MCP Bridge — 15 memory tools exposed to your agent
hermes mcp add mnemosyne --command python3 \
  --args integrations/hermes-mcp/mnemosyne_mcp.py

# Memory Provider — auto-hooks for lifecycle events
cp integrations/hermes-provider/*.py \
  ~/.hermes/hermes-agent/plugins/memory/mnemosyne/
```

### Python SDK

```python
from integrations.sdk import MnemosyneHermesMemory
m = MnemosyneHermesMemory(endpoint="http://127.0.0.1:18010")

# Store
m.add("PostgreSQL 16 + pgvector 1024d works great for Chinese embeddings")

# Retrieve
results = m.get_relevant("what database for embeddings?")
# → hybrid search across semantic + keyword + temporal + heat
```

### REST API

```bash
# Health check
curl http://your-server:8010/api/v1/echo

# Store memory
curl -X POST :8010/api/v1/memories \
  -d '{"user_id":"default","content":"...","category":"fact"}'

# Search (time-ordered)
curl "http://your-server:8010/api/v1/memories?user_id=default&sort=created_at&limit=10"

# List sessions (conversation history)
curl "http://your-server:8010/api/v1/sessions?limit=20"
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Database | PostgreSQL 16 + pgvector (1024d HNSW) | Memory + embedding storage |
| Graph | Apache AGE (Cypher) | Entity knowledge graph |
| API | FastAPI + asyncpg | 38+ REST endpoints |
| Search | Vector + BM25 + ILIKE + Temporal + Heat | 5D hybrid ranking |
| Distillation | LLM (Doubao Seed-2.0 / DeepSeek V4) | TMT L1→L5 pipeline |
| Sync | SQLite ↔ PostgreSQL | Edge-cloud resilience |
| Agent | Hermes MCP (15 tools) + Memory Provider (10 hooks) | Agent-native memory |

**Model-agnostic**: supports any OpenAI-compatible API (OpenAI, DeepSeek, vLLM, Ollama) via `MODEL_BACKEND`.

---

## Documentation

| Doc | Audience |
|-----|----------|
| [White Paper](docs/WHITEPAPER.md) | Product overview, non-technical |
| [Full White Paper](docs/WHITEPAPER_FULL.md) | Architecture, security, cognitive design |
| [ROADMAP](ROADMAP.md) | v5.3 → v5.4 → v6.0 |
| [CHANGELOG](CHANGELOG.md) | Full version history |
| [AGENTS.md](AGENTS.md) | AI agent operating manual |
| [CONTRIBUTING](.github/CONTRIBUTING.md) | Dev workflow + red lines |
| [SECURITY](.github/SECURITY.md) | Vulnerability reporting |

---

## Roadmap

- [x] AGE knowledge graph
- [x] Three-hall lifecycle
- [x] TMT 5-level distillation
- [x] RAG smart chunking
- [x] Edge-cloud sync
- [x] Session message sync (Hermes → PG)
- [x] Time-ordered search (dual-axis retrieval)
- [ ] Self-trained model integration
- [ ] Multimodal memory (image/video/audio)
- [ ] Federated memory (multi-agent shared)
- [ ] Obsidian dashboard

---

## Version History

| Version | Date | What |
|---------|------|------|
| [v5.3.2](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.2) | 2026-07-16 | Session sync — Hermes→Mnemosyne real-time |
| [v5.3.1](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.1) | 2026-07-16 | Time-ordered search + dual-axis retrieval |
| [v5.3.0](https://github.com/gymaira1990-jpg/Mnemosyne-OS/releases/tag/v5.3.0) | 2026-07-06 | Repo governance + Hermes integration |
| v5.2.3 | 2026-07-06 | Downtime alerts + MCP reconnect + L3 distillation |
| v5.2.2 | 2026-06-27 | Full Doubao migration + repo cleanup |
| v5.2.1 | 2026-06-27 | Zero local-model dependency |
| v5.2.0 | 2026-06-26 | Project memory binding |
| v5.1.0 | 2026-06-26 | Session auto-archive |
| v5.0.0 | 2026-06-24 | 7×24 independent runtime |

[Full changelog →](CHANGELOG.md)

---

<p align="center">
  <i>"Memory isn't for storing. It's for living."</i><br>
  🐾 G-CAT & Hermes Agent · MIT · 2026
</p>
