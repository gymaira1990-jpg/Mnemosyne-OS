# Docs — English edition

> These are English editions of the Chinese originals in `docs/`. The Chinese files are the source of
> truth; if they disagree, the Chinese one wins. New content lands in Chinese first, English follows.

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module layout, the four retrieval channels, merged scoring weights, the ask-when-unsure loop |
| [API.md](API.md) | Endpoint quick reference (core / palace / recall / graph-wiki-beliefs / ops) + the v9.1.2 error contract |
| [STAGING.md](STAGING.md) | Pre-release environment: why it's mandatory, isolation proof, deploy flow, pass criteria |

Chinese originals: [../README.md](../README.md) (full index).

## Fastest path to a running instance

```bash
git clone https://github.com/gymaira1990-jpg/Mnemosyne-OS.git && cd Mnemosyne-OS
# 1. PostgreSQL 16 + pgvector, then create a database
psql -d mnemosyne -f docs/schema.sql
# 2. Python deps
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# 3. Keys (see docs/ENV.md)
cp .env.template .env && $EDITOR .env
# 4. Run
.venv/bin/python3 main.py     # → http://127.0.0.1:8010
curl -s localhost:8010/api/v1/capabilities
```

If you plan to keep it running, do what this project does: run a staging instance on a different port
and database first, prove isolation with a probe row, smoke-test it, and only then point production at it.
