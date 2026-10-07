#!/usr/bin/env bash
# YOLO training under the GPU sharing rules R1-R3 (scripts/frigate_r3.py; infra side, Batt
# 2026-10-07). The 20:00-05:00 window is RETIRED: R1-R3 decide, day or night. The IO guard stays.
# Defaults: batch 2 / workers 1, the 25 % VRAM cap (train.py), checkpoints every epoch.
# - Every attempt goes through guarded_build.py rundev:, which REFUSES to start while Ollama holds
#   a model (R2) or without a Frigate baseline <= 3 h old, and aborts (SIGINT) on an IO stall, a
#   +5 ms Frigate detector slowdown, Frigate unreachable, Ollama loading a model, or, right after
#   an epoch, a baseline due for re-measurement.
# - A trip PAUSES: the pause IS a fresh 15 min Frigate baseline (nothing of ours running), then
#   --resume from last.pt. At most 3 resumes for IO/unreachable/R2 trips; planned re-baselines do
#   not count. Never a retry loop.
# - R3 latency trips walk the step-sleep ladder (SLEEP_LADDER, ms after every batch: duty cycle
#   only, never the maths): each one resumes one level up. A latency trip at the top level counts
#   as a trip.
# - R3-HARD (a camera dropping frames for 30 s) STOPS: no resume.
# - Every guard stop is VERIFIED by guarded_build (container gone, no process of ours on the GPU,
#   escalation to docker kill if not); STOP-UNVERIFIED STOPS here: a person must look.
# - Never alongside an S2 session: it waits while the lock says console or a clean room is set.
#   To pause for a session started later, SIGINT the host-side `timeout ... poring_vision.train`
#   process by PID (`ps -eo pid,args | grep 'timeout .*poring_vision.train --cache'`); this script
#   then stops. Re-run with RESUME=1 (and SLEEP_LEVEL=<index> to keep the ladder level) afterwards.
#   [RESUME=1] [SLEEP_LEVEL=0] [SLEEP_LADDER="0 100 200 400"] \
#     scripts/runbooks/train-day.sh RUN_NAME CACHE_ID EPOCHS OUT_DIR [BATCH=2] [WORKERS=1]
set -u
cd "$(dirname "$0")/../.."
RUN=${1:?RUN_NAME}; CACHE=/datasets/.framecache/${2:?CACHE_ID}; EPOCHS=${3:?EPOCHS}; D=${4:?OUT_DIR}
BATCH=${5:-2}; WORKERS=${6:-1}
read -r -a LADDER <<< "${SLEEP_LADDER:-0 100 200 400}"
level=${SLEEP_LEVEL:-0}
mkdir -p "$D"
log() { echo "$(TZ=Asia/Bangkok date '+%F %T') ICT / $(date -u '+%T') UTC $*" | tee -a "$D/train.log"; }
s2_active() { grep -q '^BACKEND=console' state/capture-backend 2>/dev/null || [ -e state/cleanroom ]; }
rebaseline() {  # the pause: a fresh baseline, nothing of ours running; R2 refusals wait (bounded)
  local i
  for i in $(seq 24); do  # the stopped step's container leaves the GPU within seconds: wait <= 2 min
    nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -q python || break
    sleep 5
  done
  for i in 1 2 3 4 5 6; do
    if python3 -S scripts/frigate_r3.py baseline --minutes 15 >> "$D/baseline.log" 2>&1; then
      log "  baseline: $(tail -1 "$D/baseline.log" | cut -c1-200)"; return 0
    fi
    log "  baseline refused/failed ($(tail -1 "$D/baseline.log" | cut -c1-160)); waiting 5 min"
    sleep 300
  done
  return 1
}
extra=""; [ "${RESUME:-0}" = 1 ] && extra="--resume"
trips=0; attempt=0
while :; do
  while s2_active; do log "S2 session/clean room active: waiting 5 min"; sleep 300; done
  ms=${LADDER[$level]}
  log "attempt $attempt batch $BATCH workers $WORKERS step-sleep ${ms} ms (ladder level $level) $extra"
  out="$D/train-guarded-$attempt.out"
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    "rundev:vision@43200=python -m poring_vision.train --cache $CACHE --epochs $EPOCHS --batch $BATCH --workers $WORKERS --name $RUN --step-sleep-ms $ms $extra" \
    > "$out" 2>&1
  rc=$?
  log "attempt $attempt rc=$rc: $(grep -E 'ABORT|REFUSED' "$out" | tail -1 | cut -c1-200)"
  attempt=$((attempt + 1))
  if [ "$rc" -eq 0 ]; then log "TRAIN DONE (step-sleep ${ms} ms)"; break; fi
  if grep -q "STOP-UNVERIFIED" "$out"; then log "TRAIN STOPPED: the guard could NOT verify the stop ($(grep STOP-UNVERIFIED "$out" | tail -1 | cut -c1-160)): a person must look"; break; fi
  if grep -q "R3-HARD" "$out"; then log "TRAIN STOPPED: R3-HARD (a camera dropped frames for 30 s): no resume"; break; fi
  if grep -q "REFUSED rundev" "$out"; then
    trips=$((trips + 1))
  elif ! grep -q "ABORT rundev" "$out"; then
    log "TRAIN STOPPED: not a guard trip (see $out)"; break
  elif grep -q "R3 rebaseline_due" "$out"; then
    log "planned re-baseline (does not count)"
  elif grep -q "R3 latency" "$out" && [ "$level" -lt $((${#LADDER[@]} - 1)) ]; then
    level=$((level + 1)); log "R3 latency: next resume at step-sleep ${LADDER[$level]} ms"
  else
    trips=$((trips + 1))
  fi
  if [ "$trips" -gt 3 ]; then log "TRAIN PAUSED: 3 resumes used, resume by hand later (SLEEP_LEVEL=$level)"; break; fi
  [ -e "data/train/$RUN/weights/last.pt" ] && extra="--resume"
  log "pausing: re-measuring the Frigate baseline (15 min) before resuming"
  if ! rebaseline; then log "TRAIN PAUSED: no valid baseline after 6 tries (SLEEP_LEVEL=$level)"; break; fi
done
