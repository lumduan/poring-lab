#!/usr/bin/env bash
# The M4 re-run's missing blocks, ONE RECORDING PER BLOCK GROUP (2026-10-05: a quant-postgres burst
# tripped the recorder's IO guard at 20:17 and the rest of the spawns went unrecorded; per-group
# recordings lose at most one group, and a group whose recorder stopped early is reported).
# Same pre-registration (docs/phase3-plan.md §5b), same spots and cells. Run inside a clean room
# that is streaming S2, with scripts/runbooks/heartbeat.sh running.
#   scripts/runbooks/m4-rerun-groups.sh OUT_DIR GROUP...
#   GROUP = name:species+species:block+block   e.g. ob:poring+lunatic:outdoor-bottom
set -u -o pipefail
cd "$(dirname "$0")/../.."
D=${1:?OUT_DIR}; shift
mkdir -p "$D"
PY=.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
CELLS=data/bench/m4/cells.json
SPOTS=(--spot outdoor=268,107 --spot indoor=104,122)
log() { echo "$(TZ=Asia/Bangkok date '+%T') ICT / $(date -u '+%T') UTC $*" | tee -a "$D/runs.log"; }
if ! $PY scripts/m4_spawns.py --check-client 2>&1 | tee -a "$D/runs.log"; then
  log "GATE: the RO client is not on the stream -- nothing recorded"; exit 3
fi
for g in "$@"; do
  name=${g%%:*}; rest=${g#*:}; species=${rest%%:*}; blocks=${rest#*:}
  log "group $name: species ${species//+/ } blocks ${blocks//+/ }"
  $PY scripts/record_session.py --backend console --label "p3-m4-rerun-$name" --seconds 1800 \
    --max-bytes 3G >"$D/record-$name.json" 2>"$D/record-$name.log" &
  rpid=$!
  sleep 10
  if ! kill -0 "$rpid" 2>/dev/null; then log "group $name: the recorder is not running -- skipped"; continue; fi
  # shellcheck disable=SC2086
  $PY scripts/m4_spawns.py --out "$D/events-$name.jsonl" "${SPOTS[@]}" --cells "$CELLS" \
    --blocks ${blocks//+/ } --species ${species//+/ } --per-species 5 \
    >"$D/spawns-$name.json" 2>"$D/spawns-$name.log"
  log "group $name: spawns rc=$?"
  if kill -0 "$rpid" 2>/dev/null; then kill -INT "$rpid"; fi
  wait "$rpid"; log "group $name: record rc=$? $(cat "$D/record-$name.json" 2>/dev/null)"
done
log "GROUPS DONE"
