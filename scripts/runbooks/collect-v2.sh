#!/usr/bin/env bash
# collect@1 (docs/planning/labels-v2-plan.md 7.6a): ONE labels-v2 COLLECTION session on a training-
# ground map, every move made by @warp, the GM immune (3.33) and at its fixed state (3.20a); the GM
# makes NO world click. The m4-rerun.sh pattern: gates, the recorder in the background, the driver,
# SIGINT the recorder, the timeline copied into the session, the offline judge.
#
#   scripts/runbooks/collect-v2.sh MAP SEED OUT_DIR [collect_v2.py plan/run options ...]
#   e.g. scripts/runbooks/collect-v2.sh new_1-3 20261010 /dev/shm/poring-lab-tmp/collect/new_1-3-a
#   COLLECT_MAX_MINUTES (default 55) caps the driver; the recording gets that + 90 s (<= 3540 s:
#   the S2 client's per-recording cap is 3600 s, record_session.H264_MAX_SECONDS).
#
# BEFORE (the parent, in this order; this script does none of it):
#  0. G1-G3 (labels-v2-plan 3.3): G1's long-lived vision container if any vision step runs; a
#     quiet IO window (scripts/runbooks/quiet_start.py), never 09:30-10:15 / 14:00-14:45 ICT;
#     training paused (one Windows session).
#  1. The UI gate must be able to see the client on THIS path. Since 2026-10-09 it is path-aware
#     (poring_env.ui_sets): on console it reads ONLY a PROVEN S2 set (data/ui_anchors/s2/proof.json:
#     windows + T2; gm_state: gm_levels + gm_notices) and refuses every typed line otherwise.
#     `collect_v2.py preflight` reports it (`ui_gate.py status` shows the proof). Until the S2 set
#     is cut and proven live (docs/operations/s2-gate-templates.md), an S2 session cannot type a
#     single GM line (it stops before the recorder starts).
#  2. Enter the S2 clean room: `cleanroom.py preflight` -> `cleanroom.py start --hard-cap-min N`
#     -> `cleanroom.py variant S2` -> `cleanroom.py checks --box-min N`; then start
#     `scripts/runbooks/heartbeat.sh LOG &` (it stops on the first refusal). Never run a room
#     across a question to Batt.
#  3. The GM logged in (ASSIST, interlock green). Immunity, once per GM LOGIN:
#       .venv/bin/python scripts/collect_v2.py immune-on       (types @monsterignore ONCE, a shot)
#     READ the screenshot it names: the immune answer ->
#       .venv/bin/python scripts/collect_v2.py immune-confirm --shot <that path>
#     the normal-state answer (it was already ON, now OFF) -> immune-on --again, read again.
#  4. The plan, offline, read before the session (spots, blocks, portal cells, the line check):
#       .venv/bin/python scripts/collect_v2.py plan --map MAP --seed SEED [options]
# AFTER: OUT_DIR/judge.json (safety, immunity, sensor, warps, blocks); then
#   `labels_v2.py coverage SESSION`, `cleanroom.py end` (or the next session), and ship the session
#   in a quiet window (dataset_ship.py). events.jsonl also stays in OUT_DIR (scratch).
set -u -o pipefail
cd "$(dirname "$0")/../.."
MAP=${1:?MAP}; SEED=${2:?SEED}; D=${3:?OUT_DIR}; shift 3
mkdir -p "$D"
PY=.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
MAXMIN=${COLLECT_MAX_MINUTES:-55}
SECS=$(( MAXMIN * 60 + 90 )); (( SECS > 3540 )) && SECS=3540
LABEL="p3-collect-${MAP//_/-}"  # record_session's id allows [a-z0-9-] only (H264_ID)
log() { echo "$(TZ=Asia/Bangkok date '+%T') ICT / $(date -u '+%T') UTC $*" | tee -a "$D/runs.log"; }
log "start: $MAP seed $SEED max ${MAXMIN} min, recording ${SECS} s, extra: $*"
# Gate 1: nothing is recorded unless the RO client is what the stream shows (no input).
if ! $PY scripts/collect_v2.py --check-client 2>&1 | tee -a "$D/runs.log"; then
  log "GATE: the RO client is not on the stream -- nothing recorded"; exit 3
fi
# Gate 2: the typing-only foreground gate needs the S2 template (else every GM line is refused).
if $PY scripts/foreground_template.py status | grep -q "client_title_active@stream.npy *MISSING"; then
  log "GATE: no S2 foreground template (scripts/foreground_template.py install stream) -- nothing recorded"
  exit 4
fi
# Gate 3: the driver's own preflight (no input): the plan + its line check, the UI gate on this
# path, the GM-state template, immunity confirmed for THIS GM login, the typing guard's state.
if ! $PY scripts/collect_v2.py preflight --map "$MAP" --seed "$SEED" --max-minutes "$MAXMIN" "$@" \
    >"$D/preflight.json" 2>>"$D/runs.log"; then
  log "GATE: preflight failed -- nothing recorded ($(tr -d '\n' <"$D/preflight.json" | head -c 600))"
  exit 5
fi
$PY scripts/collect_v2.py plan --map "$MAP" --seed "$SEED" "$@" >"$D/plan.json" 2>>"$D/runs.log"
$PY scripts/record_session.py --backend console --label "$LABEL" --seconds "$SECS" --max-bytes 5G \
  >"$D/record.json" 2>"$D/record.log" &
rpid=$!
sleep 10
if ! kill -0 "$rpid" 2>/dev/null; then
  log "the recorder is not running -- no session driven (record.log)"; exit 6
fi
$PY scripts/collect_v2.py run --map "$MAP" --seed "$SEED" --out "$D/events.jsonl" \
  --max-minutes "$MAXMIN" "$@" >"$D/run.json" 2>"$D/run.log"
rc=$?
log "driver rc=$rc ($(tr -d '\n' <"$D/run.json" | head -c 400))"
log "stopping the recorder (SIGINT: it finalises the session)"
kill -INT "$rpid" 2>/dev/null
wait "$rpid"; log "record rc=$?"
SESSION=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1])).get("dir",""))' "$D/record.json" 2>/dev/null)
if [ -z "$SESSION" ] || [ ! -d "$SESSION" ]; then
  log "no session directory in record.json -- events.jsonl stays in $D only"; exit 7
fi
cp "$D/events.jsonl" "$SESSION/collect-events.jsonl"
cp "$D/plan.json" "$SESSION/collect-plan.json"
log "timeline copied into $SESSION"
$PY scripts/collect_v2.py judge "$SESSION" >"$D/judge.json" 2>>"$D/runs.log"
log "judge rc=$? ($D/judge.json)"
log "COLLECT@1 DONE ($MAP seed $SEED, driver rc=$rc)"
exit "$rc"
