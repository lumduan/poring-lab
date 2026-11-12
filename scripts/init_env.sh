#!/usr/bin/env bash
# Create .env from .env.example (never overwrites an existing .env): detects HOST_LAN_IP and fills
# every empty secret with a random value. RDP credentials are left for you to fill in.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env already exists -- not touching it." >&2
  exit 1
fi

# `|| true`: under pipefail a failing `ip` (no route) would end the script silently, before .env
lan_ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}' || true)"
secret() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

umask 077
cp .env.example .env
sed -i \
  -e "s|^HOST_LAN_IP=.*|HOST_LAN_IP=${lan_ip}|" \
  -e "s|^DB_PASSWORD=$|DB_PASSWORD=$(secret)|" \
  -e "s|^DB_ROOT_PASSWORD=$|DB_ROOT_PASSWORD=$(secret)|" \
  -e "s|^RATHENA_SERVER_USER=$|RATHENA_SERVER_USER=srv_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_SERVER_PASSWORD=$|RATHENA_SERVER_PASSWORD=$(secret | cut -c1-23)|" \
  -e "s|^RATHENA_TEST_USER=$|RATHENA_TEST_USER=lab_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_TEST_PASSWORD=$|RATHENA_TEST_PASSWORD=$(secret | cut -c1-16)|" \
  -e "s|^RATHENA_AGENT_USER=$|RATHENA_AGENT_USER=agt_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_AGENT_PASSWORD=$|RATHENA_AGENT_PASSWORD=$(secret | cut -c1-16)|" \
  -e "s|^RATHENA_GM_USER=$|RATHENA_GM_USER=val_$(secret | cut -c1-8)|" \
  -e "s|^RATHENA_GM_PASSWORD=$|RATHENA_GM_PASSWORD=$(secret | cut -c1-16)|" \
  -e "s|^RATHENA_AGENT_CHAR=$|RATHENA_AGENT_CHAR=Agt$(secret | cut -c1-6)|" \
  -e "s|^RATHENA_GM_CHAR=$|RATHENA_GM_CHAR=Val$(secret | cut -c1-6)|" \
  .env

echo "wrote .env (mode 600): HOST_LAN_IP=${lan_ip:-<not detected>}, random DB, server, test and agent account secrets."
if [[ -z "$lan_ip" ]]; then
  # second-install-gaps.md row K: never a guessed address (it was VM 103's 192.168.1.13): compose
  # stops with "set HOST_LAN_IP in .env" until it is set, instead of binding the wrong one
  echo "WARNING: this host's LAN address was not detected: set HOST_LAN_IP in .env yourself." >&2
fi
echo "RDP is disabled until you set WIN_HOST, RDP_USER and RDP_PASSWORD in .env."
