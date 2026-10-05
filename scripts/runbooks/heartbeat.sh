#!/usr/bin/env bash
# The clean room's heartbeat while a session works. It STOPS on the first refusal: never mask a
# missing watchdog (2026-10-04: a blind loop kept a room alive ~3 h past its cap).
#   scripts/runbooks/heartbeat.sh LOG
cd "$(dirname "$0")/../.."
LOG=${1:?LOG}
while true; do
  if ! .venv/bin/python scripts/cleanroom.py heartbeat >>"$LOG" 2>&1; then
    echo "$(date '+%T') heartbeat REFUSED: loop stopped" >>"$LOG"
    exit 1
  fi
  sleep 60
done
