#!/usr/bin/env bash
# The M4 re-run session (docs/phase3-plan.md §5b, pre-registered 2026-10-05 before the recording).
# Run INSIDE a clean room that is already entered and streaming S2 (cleanroom.py preflight / start /
# variant S2 / checks), with the heartbeat loop (scripts/runbooks/heartbeat.sh) running.
#   scripts/runbooks/m4-rerun.sh OUT_DIR
# OUT_DIR (scratch, e.g. /dev/shm/poring-lab-tmp/m4-rerun) gets events.jsonl, the recorder's
# json/log and runs.log. Copy events.jsonl to data/bench/m4/ right after (2026-10-05: the only copy
# of the first M4 timeline lived in /dev/shm).
set -u -o pipefail
cd "$(dirname "$0")/../.."
D=${1:?OUT_DIR}
mkdir -p "$D"
PY=.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
CELLS=data/bench/m4/cells.json  # scripts/m4_cells.py, chosen before the session
SPOTS=(--spot outdoor=268,107 --spot indoor=104,122)
log() { echo "$(TZ=Asia/Bangkok date '+%T') ICT / $(date -u '+%T') UTC $*" | tee -a "$D/runs.log"; }
log "start"
# The gate: no input, no screenshot; nothing is recorded unless the RO client is on the stream.
if ! $PY scripts/m4_spawns.py --check-client 2>&1 | tee -a "$D/runs.log"; then
  log "GATE: the RO client is not on the stream -- nothing recorded"; exit 3
fi
$PY scripts/record_session.py --backend console --label p3-m4-rerun --seconds 3500 --max-bytes 5G \
  >"$D/record.json" 2>"$D/record.log" &
rpid=$!
sleep 10
$PY scripts/m4_spawns.py --out "$D/events.jsonl" "${SPOTS[@]}" --cells "$CELLS" \
  --blocks outdoor-top outdoor-centre outdoor-bottom --species poring lunatic --per-species 5 \
  >"$D/spawns-outdoor.json" 2>"$D/spawns-outdoor.log"
log "outdoor spawns rc=$?"
$PY scripts/m4_spawns.py --out "$D/events.jsonl" "${SPOTS[@]}" --cells "$CELLS" \
  --blocks indoor-top indoor-centre indoor-bottom --species poring --per-species 5 \
  >"$D/spawns-indoor.json" 2>"$D/spawns-indoor.log"
log "indoor spawns rc=$?"
log "spawns done; stopping the recorder (SIGINT: it finalises its shards)"
kill -INT "$rpid" 2>/dev/null
wait "$rpid"; log "record rc=$?"
log "M4 RE-RUN DONE"
