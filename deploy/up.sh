#!/usr/bin/env bash
# Запуск / обновление бота. Запускать из /opt/tayzo:  bash deploy/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Нет .env — скопируй .env.example в .env и заполни DOMAIN"; exit 1; }
[ -f tokens.env ] || { echo "Нет tokens.env — заполни токены (см. SETUP_TOKENS.md)"; exit 1; }
grep -q '^BOT_TOKEN=.\+' tokens.env || { echo "BOT_TOKEN пустой в tokens.env"; exit 1; }
grep -q '^DOMAIN=.\+' .env || { echo "DOMAIN пустой в .env"; exit 1; }

chmod 600 tokens.env .env
docker compose pull --ignore-buildable 2>/dev/null || true
docker compose up -d --build
echo
docker compose ps
echo
echo "Логи: docker compose logs -f bot"
