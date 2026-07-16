# Cron Scripts

These scripts run on the GZ production server via crontab. They are NOT portable — paths reference `/opt/mnemosyne/` and `/home/ubuntu/.local/bin/hermes`.

| Script | Schedule | Purpose |
|--------|----------|---------|
| `check-mnemosyne-health.sh` | Every 4h | Mnemosyne health check → healthcheck table |
| `tmt-consolidate.sh` | 1am/1:30am Sun/2am 1st | TMT L1→L5 distillation |
| `cron-hermes-health.sh` | Daily 9am | Hermes system housekeeping |
| `cron-hermes-billing.sh` | Weekly Mon 10am | API billing check |
| `cron-hermes-kanban.sh` | Daily | Kanban board maintenance |
| `cron-hermes-memory.sh` | Daily 8pm | Memory capacity check |

To deploy: copy to `/opt/mnemosyne/cron/` on GZ, add to crontab.
