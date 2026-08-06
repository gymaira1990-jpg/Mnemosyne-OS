# Mnemosyne OS v7.0 · Magic Memory Palace

> Product whitepaper · 2026-08-06 · v7.0.0
> Previous: v5.2 (archived in docs/archive/)

## What This Is

Mnemosyne OS is a personal AI memory operating system. It stores, organizes, refines,
and retrieves an individual's knowledge — the memories, decisions, preferences, and
lessons accumulated across a lifetime of work with AI agents.

v7.0 introduces the **Magic Memory Palace**: a memory architecture inspired by human
civilization's proven information systems — library classification (Dewey Decimal),
archive description standards (DA/T18), and the Chinese medicine cabinet (斗谱/position
registry). No computers needed; these systems worked for centuries.

## Core Ideas

| Human wisdom | Mechanism | Mnemosyne mapping |
|---|---|---|
| Library: number = position | Classification number IS the shelf location | Archive-no: `K·NET·PROXY·2026-0007` |
| Archive: standardized description | Every item has a description card | `tome_cards` (title/summary/tags/retention) |
| Chinese medicine cabinet: fixed drawers | Position registry + labels | Taxonomy: 7 wings × 20 rooms |
| Method of loci (2500 years) | Spatial encoding for recall | Wing → Room → Shelf → Tome hierarchy |

## Architecture

```
Lobby        → high-frequency memories (always-injected)
Wing         → top domain: K knowledge / N network / D dev / O ops / A assets / P people / I ideas
Room         → 20 mid categories (proxy/deploy/secret/model/...)
Shelf        → sub-topic
Tome         → individual memory (description card + archive-no + content pointer)
Vault        → raw conversations, lossless (Hermes state.db)
```

## Three-Chamber Division

| Chamber | Role | Implementation |
|---|---|---|
| 🕵️ Research room | dialogue → structured facts | `/palace/extract` (factextract pipeline) |
| 🏛️ Archive | classify + describe | `tome_cards` + archive-no + taxonomy |
| 📚 Library | retrieval | `/palace/summon` 3-channel |
| 🍵 Medicine cabinet | high-frequency fast access | taxonomy guide + archive-no lookup |

## Three-Channel Summon

1. **Name** (exact): archive-no/title/tag ILIKE hit → <100ms
2. **Guide** (range): taxonomy wing/room keyword narrowing
3. **Resonate** (fuzzy): vector search (pgvector HNSW) fallback

## Data Model

- `archive_taxonomy`: classification tree (wing/room/shelf)
- `tome_cards`: description cards (memory_id, title, summary, archive_no, wing, room, shelf, tags, retention)
- `tome_links`: related-memory pointers (lightweight graph)
- `memories.archive_no`: archive number column

## Retention Tiers

| Tier | Decay | Cleanup |
|---|---|---|
| permanent | 0.0 (never) | never (rules/identity) |
| long | 0.999 (very slow) | no auto-cleanup (knowledge/projects) |
| short | fast | auto-removed after 90 days (temporary notes) |

## Fact Pipeline

Dialogue → fact extraction (DeepSeek Tier3/4) → classify → archive-no → tome card.
2319 conversation fragments → 6,231 structured facts (knowledge 5,230 + preference 1,001).

## Hermes Integration

- `mnemosyne_palace_summon` tool (3-channel summon)
- `on_session_end` auto fact extraction
- `system_prompt_block` palace state injection
- `sync_turn` lossless session storage (2,000/3,000 chars)

## v7.0 Metrics

- 8,873 memories | 100% archive coverage | 8,682 tome cards | 30 taxonomy nodes
- 6,231 structured facts
- Summon latency ~100-400ms
- Full test suite: 97 passed

## Docs Index

- `docs/palace-architecture.md` — detailed palace design
- `docs/design/` — per-version design docs (v6.2-v6.4)
- `docs/archive/` — archived whitepapers (v5.x)
- `docs/schema.sql` — full database schema (incl. palace tables)
