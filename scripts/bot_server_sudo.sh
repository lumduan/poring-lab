#!/bin/bash
# Run stdin as a root bash script on bot-server (docs/planning/bot-server-migration.md 8):
#     scripts/bot_server_sudo.sh <<'SCRIPT'
#     usermod -aG render bot
#     SCRIPT
# The sudo password is .env's BOT_SERVER_SUDO_PASSWORD (Batt 2026-11-07). It travels on stdin ahead
# of the script (sudo -S reads one line), never on an argv, never printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
pw="$(grep '^BOT_SERVER_SUDO_PASSWORD=' "$ROOT/.env" | cut -d= -f2-)"
[ -n "$pw" ] || { echo "BOT_SERVER_SUDO_PASSWORD missing in .env" >&2; exit 2; }
{ printf '%s\n' "$pw"; cat; } | ssh -o BatchMode=yes bot@192.168.1.228 'sudo -S -p "" bash -s'
