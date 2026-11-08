# Architecture at a glance

> English edition. The Chinese original ([../ARCHITECTURE.md](../ARCHITECTURE.md)) is the source of truth;
> if the two disagree, the Chinese one wins. Deeper design: [../WHITEPAPER.md](../WHITEPAPER.md),
> [../palace-architecture.md](../palace-architecture.md).

```
Mnemosyne OS (FastAPI, 50+ endpoints)
  ├── main.py            Service entrypoint + core routes (memories/search/palace/wiki/...)
  ├── palace.py          🏰 Palace core (taxonomy / archive numbers / cards / summon / lifecycle)
  ├── core/              LLM / Embedding / Chunker engines
  ├── api/               REST API modules
  ├── tmt/               Distillation engine (factextract / distill)
  ├── wiki/              WIKI knowledge base (BM25 / graph / extraction / eval)
  ├── security/          Audit and purification
  ├── integrations/      Hermes integration (Memory Provider + MCP)
  │   └── hermes-provider/  Memory Provider v7 (11 tools, palace_summon)
  ├── sync/              Edge–cloud sync (SQLite ↔ PostgreSQL)
  └── docs/              Whitepaper + palace design + schema

Data layer: PostgreSQL 16 + pgvector 1024d (HNSW).
            v7.8 dropped Apache AGE — entity relations live in entities / memory_entities / wiki_entities.
Model layer: pluggable — Doubao ARK / DeepSeek / any OpenAI-compatible endpoint.
```

## Retrieval: four channels, one call

The server answers E/C/T in a single request; the client adds S (semantic) when it wants more recall.

| Ch | Name | What it does |
|---|---|---|
| E | Exact | Archive numbers, account IDs, commit hashes, file paths — anchored on the first line |
| C | Keywords | Multi-keyword OR, ranked by how many keywords hit. **Not card-only**: any live memory can match (ranked relevance-first, cards on ties) |
| T | Temporal | Recent-window scan, optionally keyword-filtered |
| S | Semantic | pgvector cosine similarity over 1024d embeddings (client-side, `sim_floor` default 0.40) |

Merged scoring lives in one place — `core/ranking.py`:

```python
WEIGHTS = {semantic: 0.50, bm25: 0.15, temporal: 0.15, reliability: 0.10, heat: 0.10}
```

Temporal weight decays with age (≤7 days: full, ≤30 days: half, older: zero), so recent context wins
without making old knowledge unreachable.

## When recall isn't sure

`recall` accepts `confirm_margin`. If the top two candidates are closer than the margin, or there is a
single weak candidate, the response carries a `confirm` block with up to three options and a question.
The human verdict goes to `POST /memory-os/label`, which:

- raises `reliability` by 0.10 for the chosen memory (and lowers it for rejected ones, floor 0),
- records the label, which `scripts/labels_to_cases.py` can export as a new eval case.

That is the "usage becomes training data" loop: ask → judge → reweight → new test case.
