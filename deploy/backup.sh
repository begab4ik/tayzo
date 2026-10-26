#!/usr/bin/env bash
# Бэкап базы. Ставится в cron (см. DEPLOY.md). Хранит последние 14 копий в ./backups
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
f="backups/tayzo_$(date +%F_%H-%M).sql.gz"
docker compose exec -T postgres pg_dump -U tayzo tayzo | gzip > "$f"
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm -f
echo "backup: $f"
