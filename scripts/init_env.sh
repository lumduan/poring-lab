#!/usr/bin/env bash
# Create .env from .env.example (never overwrites an existing .env): detects HOST_LAN_IP and fills
# every empty secret with a random value. RDP credentials are left for you to fill in.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env already exists -- not touching it." >&2
  exit 1
fi

lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')"
secret() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

umask 077
cp .env.example .env
sed -i \
  -e "s|^HOST_LAN_IP=.*|HOST_LAN_IP=${lan_ip:-192.168.1.13}|" \
  -e "s|^DB_PASSWORD=$|DB_PASSWORD=$(secret)|" \
  -e "s|^DB_ROOT_PASSWORD=$|DB_ROOT_PASSWORD=$(secret)|" \
  -e "s|^RATHENA_SERVER_USER=$|RATHENA_SERVER_USER=srv_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_SERVER_PASSWORD=$|RATHENA_SERVER_PASSWORD=$(secret | cut -c1-23)|" \
  -e "s|^RATHENA_TEST_USER=$|RATHENA_TEST_USER=lab_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_TEST_PASSWORD=$|RATHENA_TEST_PASSWORD=$(secret | cut -c1-16)|" \
  .env

echo "wrote .env (mode 600): HOST_LAN_IP=${lan_ip:-192.168.1.13}, random DB, server and test-account secrets."
echo "RDP is disabled until you set WIN_HOST, RDP_USER and RDP_PASSWORD in .env."
