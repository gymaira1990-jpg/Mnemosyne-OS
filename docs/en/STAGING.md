# Pre-release environment (staging)

> English edition. Chinese original (and source of truth): [../STAGING.md](../STAGING.md).
> **Rule since 2026-11-08: every project must have one.** Shipping straight from a green local build
> means there was never a second line of defence.

## Why it is mandatory

A green local build ≠ a working deployment. Four classes of difference only show up in a real
environment — each of these actually bit this project:

| Difference | What happened here |
|---|---|
| Real database + real data | `memory_labels` existed only in a migration, not in `schema.sql` → a from-scratch DB lacked the table and those tests were **silently skipped** (green, but not run) |
| Real dependency versions | A `pg_dump` schema failed to import into PG16 (`transaction_timeout`) — only CI caught it |
| Real keys and config | The distillation path skipped embeddings → ~55 distilled memories/day became **invisible to semantic search** (3,594 accumulated before anyone noticed) |
| Real process model | `ssh` unavailable / wrong port / several workers — a smoke run on the wrong host reports a **fake red** |

## This project's instance (isolated on the same host)

| Dimension | Production | Staging |
|---|---|---|
| Directory | `/opt/mnemosyne` | `/opt/mnemosyne-staging` |
| Port | `127.0.0.1:8010` | `127.0.0.1:8020` |
| Database | `mnemosyne` | `mnemosyne_staging` (clone of production) |
| systemd unit | `mnemosyne` | `mnemosyne-staging` |
| Tunnel (dev box) | `18010 → 8010` | `18020 → 8020` |
| Exposure | never public | **never public** |
| venv | `/opt/mnemosyne/venv` | `/opt/mnemosyne-staging/venv` (independent) |
| `.env` | production keys | same keys + `PGDATABASE` / `MNEMOSYNE_PORT` overrides |

**Isolation must be demonstrable, not asserted:**

```bash
curl -s -X POST http://127.0.0.1:8020/api/v1/memories \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"staging-probe","content":"isolation probe","category":"temp"}'
# staging must be 1, production must be 0
ssh <host> "sudo -u postgres psql -d mnemosyne_staging -tAc \"select count(*) from memories where user_id='staging-probe'\""
ssh <host> "sudo -u postgres psql -d mnemosyne         -tAc \"select count(*) from memories where user_id='staging-probe'\""
```

Measured 2026-11-08: `staging=1 / production=0`.

## The flow (skip a step and you don't ship)

```
local: make test / lint / counter-proofs
  → bash scripts/deploy_staging.sh     (deploy + smoke 6/6)
  → human look
  → bash scripts/deploy_prod.sh        (refuses unless the commit was verified on staging)
  → production smoke + prod-diff must be 0 drift
  → all stage goals green + owner approval → tag / Release
```

`deploy_staging.sh` enforces three guards: clean worktree (deploy must map to a commit), service comes
up, smoke is 6/6. Any failure exits non-zero — **scripts are more reliable than memory**.

## Pass criteria

| # | Criterion | Command |
|---|---|---|
| 1 | Full test suite: 0 failed, 0 skipped | `make test` |
| 2 | Smoke 6/6 **and it queried the staging DB** | `MEMOS_DB=mnemosyne_staging python3 scripts/prod_smoke.py http://127.0.0.1:18020` |
| 3 | Isolation holds: staging writes never reach production | probe above (production must be 0) |
| 4 | Service reports the version matching the code | `curl -s http://127.0.0.1:18020/api/v1/capabilities` |

## Known limits (not papered over)

- **Snapshot data**: staging is a point-in-time clone; "historical data corruption" cases can't be judged there.
- **Same host**: shares CPU/RAM/disk, so load-test conclusions are not valid.
- **Shared keys**: staging calls the real external APIs (small but non-zero cost).
- **No automatic deploy**: a human gate is deliberate.

## Reusing this for another project

Change three things — directory (`/opt/<project>-staging`), port (+10), database (`<db>_staging`) —
and copy the rest: independent venv, independent systemd unit, bind 127.0.0.1 only, a `deploy_staging.sh`
with the same guards, and the four pass criteria.
