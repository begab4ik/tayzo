#!/usr/bin/env bash
# Первичная настройка чистого Ubuntu 24.04 под Tayzo. Запускать от root ОДИН раз:
#   bash server_setup.sh
set -euo pipefail

echo "==> Обновление системы"
apt-get update -y && apt-get upgrade -y
apt-get install -y curl git ufw fail2ban unattended-upgrades

echo "==> Swap 2 ГБ (страховка от нехватки RAM)"
if ! swapon --show | grep -q swapfile; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Файрвол: только SSH, HTTP, HTTPS"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> fail2ban (защита SSH от перебора)"
systemctl enable --now fail2ban

echo "==> Часовой пояс"
timedatectl set-timezone Asia/Tashkent

echo "==> Папка проекта"
mkdir -p /opt/tayzo

echo
echo "Готово. Дальше: скопируй проект в /opt/tayzo и запусти bash deploy/up.sh"
