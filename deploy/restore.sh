#!/usr/bin/env bash
# Восстановить базу из бэкапа:  bash deploy/restore.sh backups/tayzo_2026-10-26_09-00.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "Укажи файл бэкапа"; exit 1; }
read -r -p "Это ПЕРЕЗАПИШЕТ текущую базу. Продолжить? [y/N] " a; [ "$a" = y ] || exit 0
docker compose stop bot
docker compose exec -T postgres psql -U tayzo -d postgres -c "DROP DATABASE IF EXISTS tayzo;" -c "CREATE DATABASE tayzo;"
gunzip -c "$1" | docker compose exec -T postgres psql -U tayzo -d tayzo
docker compose start bot
echo "восстановлено из $1"
