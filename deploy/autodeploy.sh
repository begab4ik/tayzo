#!/bin/bash
# Автодеплой: раз в минуту (cron) проверяем GitHub; если есть новые коммиты — подтягиваем и пересобираем.
# Так обновления выкатываются без захода в консоль. Лог: /var/log/tayzo-deploy.log
set -e
cd /opt/tayzo
exec 9>/tmp/tayzo-deploy.lock
flock -n 9 || exit 0
git fetch -q origin main
LOCAL=$(git rev-parse HEAD); REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
echo "[$(date '+%F %T')] deploy $LOCAL -> $REMOTE" >> /var/log/tayzo-deploy.log
CHANGED=$(git diff --name-only "$LOCAL" "$REMOTE")
git pull -q --ff-only origin main
# одноразовые серверные задачи: deploy/ops/*.sh выполняются один раз (отметка в .ops_done)
mkdir -p .ops_done
for f in deploy/ops/*.sh; do
  [ -f "$f" ] || continue
  n=$(basename "$f")
  [ -f ".ops_done/$n" ] && continue
  echo "[$(date '+%F %T')] ops $n" >> /var/log/tayzo-deploy.log
  bash "$f" >> /var/log/tayzo-deploy.log 2>&1 && touch ".ops_done/$n"
done
if echo "$CHANGED" | grep -qE '^(app/|requirements|Dockerfile|docker-compose|\.env\.example)'; then
  docker compose up -d --build bot >> /var/log/tayzo-deploy.log 2>&1
fi
if echo "$CHANGED" | grep -qE '^(Caddyfile|docker-compose)'; then
  docker compose up -d --force-recreate caddy >> /var/log/tayzo-deploy.log 2>&1
fi
echo "[$(date '+%F %T')] done" >> /var/log/tayzo-deploy.log
