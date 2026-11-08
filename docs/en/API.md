# API quick reference

> English edition. The Chinese original ([../API.md](../API.md)) is the source of truth.
> **The authoritative, always-current endpoint list is the service's own description:**
> `GET /api/v1/capabilities`.

## Core (memories)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/echo` | GET | Health check + version |
| `/api/v1/memories` | GET | List memories (`?sort=created_at` timeline / `?sort=heat` heat) |
| `/api/v1/memories` | POST | Store a memory (auto-embed + entity extraction + conflict detection) |
| `/api/v1/memories/{id}` | GET | One memory |
| `/api/v1/memories/{id}` | PUT | Update |
| `/api/v1/memories/{id}` | DELETE | Soft delete |
| `/api/v1/memories/{id}/restore` | POST | Restore a deleted memory |
| `/api/v1/memories/search` | POST | Five-dimensional search (vector + BM25 + time + reliability + heat) |
| `/api/v1/memories/{id}/feedback` | POST | Feedback (`positive` / `negative`, shifts reliability) |
| `/api/v1/memories/heat-top` | GET | Heat ranking |
| `/api/v1/memories/stats` | GET | Corpus statistics |
| `/api/v1/memories/tree` | GET | Hierarchical tree |
| `/api/v1/memories/{id}/traces` | GET | Lifecycle traces |
| `/api/v1/memories/conflicts` | GET | **Conflicts awaiting review** (since 9.0.15 conflicts are only flagged, never auto-invalidated) |
| `/api/v1/memories/conflicts/resolve` | POST | **Human verdict**: `keep_both` / `invalidate_old` |
| `/api/v1/memories/{id}/tiered` | GET | Tiered read (L5/L3/L1) |

## Palace (v7 core)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/palace/status` | GET | Palace status (archival rate / card count / taxonomy) |
| `/api/v1/palace/summon` | GET | Three-channel summon (named / guided / resonance) |
| `/api/v1/palace/archive` | POST | Classify + archive (generates archive number and catalog card) |
| `/api/v1/palace/extract` | POST | Fact extraction (dialogue → facts) |
| `/api/v1/palace/refine` | POST | Card refinement (LLM) |
| `/api/v1/palace/lifecycle` | POST | Lifecycle transitions |
| `/api/v1/palace/pin` | POST | Pin (prevents decay) |

## Recall (v9.1.2 milestone)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/memory-os/recall` | POST | Four-channel recall; `user_id`, `limit` (alias `k`), `semantic`, `sim_floor`, `confirm_margin`, `abstain_below` |
| `/api/v1/memory-os/exact` | POST | Exact channel only (`q`, `user_id`, `limit`) |
| `/api/v1/memory-os/keywords` | POST | Multi-keyword channel (`keywords[]`, `user_id`, `limit`) |
| `/api/v1/memory-os/label` | POST | Record a human verdict (`source="confirm"` or `"conflict"`, `rejected_ids[]`) |
| `/api/v1/memory-os/labels` | GET | Recent verdicts (for review / export) |
| `/api/v1/memory-os/trace/{archive_no}` | GET | Two-hop trace back to the transcript |
| `/api/v1/agents` | GET | Agent roster (identity card lives in `users.metadata`; agents without a card are listed with `has_card=false`) |

## Graph / Wiki / Beliefs

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/graph/search` | POST | Entity-linked memory search (entity vectors → `memory_entities`) |
| `/api/v1/wiki` | GET/POST | Knowledge base pages |
| `/api/v1/wiki/search` | POST | Semantic search (vector + BM25, RRF fusion) |
| `/api/v1/wiki/by-source` | GET | Exact lookup by source path / URL |
| `/api/v1/beliefs` | POST | Create a belief (confidence auto-merged) |
| `/api/v1/beliefs/search` | POST | Semantic belief search |
| `/api/v1/beliefs/{id}/evolve` | POST | Evolve a belief (add evidence / adjust confidence) |

## Sessions / distillation / ops

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/sessions/archive` | POST | Archive a session (v7.8 removed message-list/sync endpoints; transcripts live in Hermes `state.db`) |
| `/api/v1/reflect` | POST | TMT reflection (`?mode=light` heat decay / `?mode=deep` LLM distillation) |
| `/api/v1/extract-entities` | POST | Batch entity extraction into the graph |
| `/api/v1/health/{user_id}` | GET | Per-user health report |
| `/api/v1/capabilities` | GET | Full capability manifest (self-describing) |
| `/api/v1/dialectic` | POST | Dialectic retrieval (with context) |

## Error contract (v9.1.2)

| Situation | Status |
|---|---|
| Empty `content`, or content containing NUL (`\x00`) | `400` |
| `chosen_id` that doesn't exist or belongs to another user | `400` |
| Purify a memory that isn't yours / doesn't exist | `404` |
| Database unreachable during smoke | exit `2` (hard fail, never "unverified = passed") |

> 📋 Full list with parameters: `GET /api/v1/capabilities`.
