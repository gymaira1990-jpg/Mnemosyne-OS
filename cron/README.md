# Cron Scripts

These scripts run on the production server via crontab (deploy via `cron/` + system crontab). Paths are examples — adjust `/opt/mnemosyne/` to your install location.

| Script | Schedule | Purpose |
|--------|----------|---------|
| `check-mnemosyne-health.sh` | Every 4h | Mnemosyne health check → healthcheck table |
| `tmt-consolidate.sh` | 1am daily / Sun 1:30am / 1st 2am | Session consolidation + fact extraction pipeline |
| `cron-hermes-health.sh` | Daily 9am | Hermes system housekeeping |
| `cron-hermes-billing.sh` | Weekly Mon 10am | API billing check |
| `cron-hermes-memory.sh` | Daily 8pm | Memory capacity check |
| `mnemosyne-health-monitor.sh` | Every 15min | Health monitor + backup freshness alert |

Deploy: copy scripts to your server, add to crontab, adjust paths.
