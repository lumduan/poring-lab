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
# On bot-server itself (since 2026-11-07 the lab's agent runs THERE) run sudo locally: an ssh to its
# own address fails with "Host key verification failed" (found 2026-11-13). From any other machine
# (VM 103 before the cutover) it still goes over ssh.
if ip -4 -o addr show 2>/dev/null | grep -q ' 192\.168\.1\.228/'; then
    { printf '%s\n' "$pw"; cat; } | sudo -S -p "" bash -s
else
    { printf '%s\n' "$pw"; cat; } | ssh -o BatchMode=yes bot@192.168.1.228 'sudo -S -p "" bash -s'
fi
