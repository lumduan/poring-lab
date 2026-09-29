#!/usr/bin/env bash
# Dev stack without image builds (see compose.dev.yaml). Examples:
#   scripts/dev.sh up -d backend frontend-dev     # backend runs host source; console on :3000
#   scripts/dev.sh logs -f frontend-dev
#   scripts/dev.sh stop frontend-dev              # console off; desktop (RDP) keeps running
# Name the services: a bare `up` would also try to start (and build) the production frontend.
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose -f compose.yaml -f compose.dev.yaml --profile remote --profile dev "$@"
