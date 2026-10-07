#!/usr/bin/env bash
# YOLO training under the GPU sharing rules R1-R3 (scripts/frigate_r3.py; infra side, Batt
# 2026-10-07). The 20:00-05:00 window is RETIRED: R1-R3 decide, day or night. The IO guard stays.
# Defaults: batch 2 / workers 1, the 25 % VRAM cap (train.py), checkpoints every epoch.
# - Every attempt goes through guarded_build.py rundev:, which REFUSES to start while Ollama holds
#   a model or another job of ours is on the GPU (R2) or Frigate does not answer, and aborts on an
#   IO stall, an R3 trip (below), Frigate unreachable for 60 s, or Ollama loading a model.
# - R3 is the PAIRED ON/OFF measurement (docs/operations/r3-paired.md): guarded_build pauses and
#   unpauses the step's container in 3-min windows and trips on the median load-matched ON-OFF
#   detector delta > 5 ms. A paired latency trip moves one level up the step-sleep ladder
#   (SLEEP_LADDER, ms after every batch: duty cycle only, never the maths) after 30 s; at the top
#   level the run STOPS and the setting is Batt's. "R3 inconclusive" (load too variable) STOPS.
# - Other trips (IO, Frigate unreachable, R2) PAUSE 15 min, then --resume from last.pt; at most 3.
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
  pause=900
  if grep -q "R3 inconclusive" "$out"; then
    log "TRAIN STOPPED: R3 could not measure our effect (Frigate load too variable): fail closed"; break
  elif grep -q "REFUSED rundev" "$out"; then
    trips=$((trips + 1))
  elif ! grep -q "ABORT rundev" "$out"; then
    log "TRAIN STOPPED: not a guard trip (see $out)"; break
  elif grep -q "R3 latency" "$out" && [ "$level" -lt $((${#LADDER[@]} - 1)) ]; then
    level=$((level + 1)); pause=30
    log "R3 paired latency trip: the next attempt runs at step-sleep ${LADDER[$level]} ms"
  elif grep -q "R3 latency" "$out"; then
    log "TRAIN STOPPED: R3 paired latency trip at the top of the ladder (${LADDER[$level]} ms): setting parked for Batt"; break
  else
    trips=$((trips + 1))
  fi
  if [ "$trips" -gt 3 ]; then log "TRAIN PAUSED: 3 resumes used, resume by hand later (SLEEP_LEVEL=$level)"; break; fi
  [ -e "data/train/$RUN/weights/last.pt" ] && extra="--resume"
  log "pausing ${pause} s before the next attempt"
  sleep "$pause"
done
