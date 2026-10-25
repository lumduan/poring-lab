#!/usr/bin/env bash
# YOLO training under the GPU sharing rules R1-R3 (scripts/frigate_r3.py; infra side, Batt
# 2026-10-07). The 20:00-05:00 window is RETIRED: R1-R3 decide, day or night. The IO guard stays.
# Defaults: batch 2 / workers 1, the 25 % VRAM cap (train.py), checkpoints every epoch.
# - Every attempt goes through guarded_build.py rundev: (execdev: with WORKER=1, below), which
#   REFUSES to start while Ollama holds a model or another job of ours is on the GPU (R2) or Frigate
#   does not answer, and aborts on an IO stall, an R3 trip (below), Frigate unreachable for 60 s,
#   or Ollama loading a model.
# - THE ADAPTIVE DUTY CYCLE (Batt 2026-10-07 ~16:25; docs/operations/r3-paired.md): the training
#   NEVER pauses or stops because of load; it slows down. guarded_build's DutyController sets the
#   step sleep after every batch (100 / 200 / 400 / 800 / 2000 ms) from Frigate's live fleet load and
#   writes it to state/train-duty/duty.json, read-only in the container (`--duty-file`).
# - R3 is the PAIRED ON/OFF measurement: a paired latency trip (or "R3 inconclusive") raises the
#   duty FLOOR one level (DUTY_MIN) and resumes after 30 s; at the floor it keeps running there.
# - R3-HARD (a camera dropping frames for 30 s): the infra rule, so the abort stays IMMEDIATE and
#   verified; the guard logs the fleet load with it ($D/drop-aborts.log). Then: wait for 15 quiet
#   minutes (`frigate_r3.py quiet`, re-armed until it passes: never a stop), resume at the SLOWEST
#   level and walk back up slowly (DUTY_AFTER_ABORT). The 3rd abort within a rolling 2 h CAPS the
#   speed at >= 800 ms for the next hour and prints a `NOTIFY:` line (Batt is pushed); no stop.
# - Other trips (IO, Frigate unreachable, R2): PAUSE 15 min, then --resume from last.pt; at most 3
#   (unchanged).
# - Every guard stop is VERIFIED by guarded_build (container gone, no process of ours on the GPU,
#   escalation to docker kill if not); STOP-UNVERIFIED STOPS here: a person must look.
# - Never alongside an S2 session: it waits while the lock says console or a clean room is set.
#   To pause for a session started later, SIGINT the host-side `timeout ... poring_vision.train`
#   process by PID (`ps -eo pid,args | grep 'timeout .*poring_vision.train --cache'`); this script
#   then stops. Re-run with RESUME=1 afterwards.
# - MID_CKPT=1 (Batt 2026-10-08; v1 onwards, once docs/operations/mid-epoch-checkpoints.md's proof
#   PASSED): `--mid-ckpt`, so an abort loses at most ~5 min (weights/mid.pt), not the epoch, and
#   the resume is exact. A run keeps the mode it started with (train.py refuses a mixed resume).
#   [RESUME=1] [MID_CKPT=1] [INIT_WEIGHTS=/data/train/RUN0/weights/last.pt] [HSV_S=0.2] [CLOSE_MOSAIC=3] \
#     [DUTY_START=4] [DUTY_MIN=0] \
#     scripts/runbooks/train-day.sh RUN_NAME CACHE_ID EPOCHS OUT_DIR [BATCH=2] [WORKERS=1]
# - MARKET-OPEN WINDOWS (Batt 2026-10-09): no attempt starts or auto-resumes between 09:30-10:15 or
#   14:00-14:45 ICT (CLAUDE.md rule 5; two IO aborts that day came from auto-resumes at 14:12 and
#   14:33). An attempt due inside a window waits until it ends.
# - MAX_ATTEMPTS=N (Batt 2026-10-09, option D: "one attempt, no auto-retry after an IO trip"): after
#   N container starts that did not finish, stop as PAUSED (exit 3) -- no IO pause, no R3 resume.
#   0 (the default) = unlimited, as before.
# - WORKER=1 (option A, docs/operations/vision-long-lived.md; PROVEN + SWITCHED 2026-10-10, 5b):
#   every attempt is `guarded_build.py execdev:` INSIDE the long-lived vision worker
#   (started once, beforehand, through quiet_start: `worker:vision@120`) instead of a new `rundev:`
#   container. Everything else is unchanged (the exit codes, MAX_ATTEMPTS, the market windows, R3).
#   A worker that is down -> PAUSED (3) at once (its start is a cold start: a person picks the quiet
#   window); not ready (busy, paused, another checkout's) -> STOPPED (2); a stop that escalated to
#   `docker kill` of the worker (WORKER KILLED) -> PAUSED (3), no retry. To pause it for an S2
#   session by hand: SIGINT the in-worker `timeout --kill-after=30 ... poring_vision.train` process
#   (it shows in the host's ps); the guard then verifies the worker idle again. 0 (default): rundev:.
# EXIT CODES (2026-10-09: it exited 0 on every end, so a chain read "TRAIN PAUSED" at epoch 17 of 30
# as finished and started v1's evals on an unfinished checkpoint):
#   0 TRAIN DONE   2 TRAIN STOPPED (a person must look)   3 TRAIN PAUSED (resume by hand)
set -u
cd "$(dirname "$0")/../.."
RUN=${1:?RUN_NAME}; CACHE=/datasets/.framecache/${2:?CACHE_ID}; EPOCHS=${3:?EPOCHS}; D=${4:?OUT_DIR}
BATCH=${5:-2}; WORKERS=${6:-1}
GUARD=${GUARD:-python3 scripts/guarded_build.py}  # overridable for tests only
QUIET=${QUIET:-python3 -S scripts/frigate_r3.py quiet --minutes 15 --max-wait-min 120}
DROP_WINDOW_S=7200; DROP_MAX=3; CAP_LEVEL=3; CAP_S=3600; FLOOR=4
IO_PAUSE_S=${IO_PAUSE_S:-900}; R3_PAUSE_S=${R3_PAUSE_S:-30}  # overridable for tests only
MARKET_WINDOWS=${MARKET_WINDOWS:-"0930-1015 1400-1445"}  # ICT, CLAUDE.md rule 5
SLEEP=${SLEEP:-sleep}  # overridable for tests only
MAX_ATTEMPTS=${MAX_ATTEMPTS:-0}
KIND=rundev; [ "${WORKER:-0}" = 1 ] && KIND=execdev  # option A: an exec inside the long-lived worker
now_hhmm() { if [ -n "${CLOCK_HHMM:-}" ]; then echo "$CLOCK_HHMM"; else TZ=Asia/Bangkok date +%H%M; fi; }  # CLOCK_HHMM: tests only
now_dow() { if [ -n "${CLOCK_DOW:-}" ]; then echo "$CLOCK_DOW"; else TZ=Asia/Bangkok date +%u; fi; }  # 1 Mon .. 7 Sun; CLOCK_DOW: tests only
market_wait_s() {  # seconds until the market-open window we are in ends (minute grain, +1 min); 0 outside
  # Monday to Friday only (CLAUDE.md rule 5; Batt 2026-10-09: "not on Saturday or Sunday"). Until
  # 2026-10-24 this ignored the weekday: Saturday 09:31 waited 45 min for a closed market.
  local now w a b
  [ "$(now_dow)" -ge 6 ] && { echo 0; return; }
  now=$((10#$(now_hhmm)))
  for w in $MARKET_WINDOWS; do
    a=$((10#${w%-*})); b=$((10#${w#*-}))
    if [ "$now" -ge "$a" ] && [ "$now" -lt "$b" ]; then
      echo $(( ((b / 100) * 60 + b % 100 - (now / 100) * 60 - now % 100) * 60 + 60 )); return
    fi
  done
  echo 0
}
export DUTY_START=${DUTY_START:-$FLOOR} DUTY_MIN=${DUTY_MIN:-0}
export DUTY_CAP_LEVEL=${DUTY_CAP_LEVEL:-0} DUTY_CAP_UNTIL=${DUTY_CAP_UNTIL:-0}
export DUTY_AFTER_ABORT=${DUTY_AFTER_ABORT:-0}
mkdir -p "$D"
log() { echo "$(TZ=Asia/Bangkok date '+%F %T') ICT / $(date -u '+%T') UTC $*" | tee -a "$D/train.log"; }
s2_active() { grep -q '^BACKEND=console' state/capture-backend 2>/dev/null || [ -e state/cleanroom ]; }
extra=""; [ "${RESUME:-0}" = 1 ] && extra="--resume"
mid=""; [ "${MID_CKPT:-0}" = 1 ] && mid=" --mid-ckpt"
# INIT_WEIGHTS (2026-10-11, Batt: "continue training"): a NEW run's starting weights (train.py
# --weights; container path), e.g. a finished run's last.pt. Never passed with --resume, which
# continues from the run's own checkpoint.
init=""; [ -n "${INIT_WEIGHTS:-}" ] && init=" --weights $INIT_WEIGHTS"
# HSV_S / CLOSE_MOSAIC (2026-10-24, docs/planning/payf07-detector.md 12f): a NEW run's ultralytics
# hsv_s and close_mosaic (train.py --hsv-s / --close-mosaic), numbers only. Unset: ultralytics'
# defaults (0.7 / 10), as every run before. Never with --resume: a run keeps its checkpoint's own.
hyp=""
if [ -n "${HSV_S:-}" ]; then
  [[ "$HSV_S" =~ ^(0(\.[0-9]+)?|1(\.0+)?)$ ]] || { log "TRAIN STOPPED: HSV_S=$HSV_S is not a number in 0..1"; exit 2; }
  hyp="$hyp --hsv-s $HSV_S"
fi
if [ -n "${CLOSE_MOSAIC:-}" ]; then
  [[ "$CLOSE_MOSAIC" =~ ^[0-9]+$ ]] || { log "TRAIN STOPPED: CLOSE_MOSAIC=$CLOSE_MOSAIC is not a count"; exit 2; }
  hyp="$hyp --close-mosaic $CLOSE_MOSAIC"
fi
# SCALE (2026-10-26, docs/planning/gef10-detector.md D7): a NEW run's ultralytics scale (train.py
# --scale), a number in 0..0.9; unset: ultralytics' 0.5. Never with --resume.
if [ -n "${SCALE:-}" ]; then
  [[ "$SCALE" =~ ^0(\.[0-9]+)?$ ]] || { log "TRAIN STOPPED: SCALE=$SCALE is not a number in 0..0.9"; exit 2; }
  hyp="$hyp --scale $SCALE"
fi
trips=0; attempt=0; status=0
while :; do
  while s2_active; do log "S2 session/clean room active: waiting 5 min"; sleep 300; done
  ws=$(market_wait_s)
  if [ "$ws" -gt 0 ]; then
    log "market-open window: waiting ${ws} s before attempt $attempt (no disk-heavy steps 09:30-10:15 / 14:00-14:45 ICT)"
    $SLEEP "$ws"
  fi
  log "attempt $attempt batch $BATCH workers $WORKERS duty start $DUTY_START min $DUTY_MIN cap $DUTY_CAP_LEVEL until $DUTY_CAP_UNTIL after-abort $DUTY_AFTER_ABORT $extra"
  out="$D/train-guarded-$attempt.out"
  w="$init$hyp"; [ "$extra" = "--resume" ] && w=""
  $GUARD --sustain 30 --spike 25 \
    "$KIND:vision@43200=python -m poring_vision.train --cache $CACHE --epochs $EPOCHS --batch $BATCH --workers $WORKERS --name $RUN --step-sleep-ms 2000 --duty-file /lab-duty/duty.json$mid$w $extra" \
    > "$out" 2>&1
  rc=$?
  log "attempt $attempt rc=$rc: $(grep -E 'ABORT|REFUSED' "$out" | tail -1 | cut -c1-200)"
  log "  $(grep -a 'DUTY summary' "$out" | tail -1 | cut -c1-300)"
  attempt=$((attempt + 1))
  if [ "$rc" -eq 0 ]; then log "TRAIN DONE"; status=0; break; fi
  if grep -q "STOP-UNVERIFIED" "$out"; then log "TRAIN STOPPED: the guard could NOT verify the stop ($(grep STOP-UNVERIFIED "$out" | tail -1 | cut -c1-160)): a person must look"; status=2; break; fi
  if grep -q "REFUSED $KIND:vision: WORKER down" "$out"; then log "TRAIN PAUSED: the vision worker is down -- start it through quiet_start (worker:vision@120), then RESUME=1"; status=3; break; fi
  if grep -q "REFUSED $KIND:vision: WORKER" "$out"; then log "TRAIN STOPPED: the vision worker is not ready ($(grep 'REFUSED' "$out" | tail -1 | cut -c1-200)): a person must look"; status=2; break; fi
  if grep -q "WORKER KILLED" "$out"; then log "TRAIN PAUSED: the stop escalated to docker kill of the vision worker -- start it again through quiet_start (worker:vision@120), then RESUME=1"; status=3; break; fi
  if [ "$MAX_ATTEMPTS" -gt 0 ] && [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then log "TRAIN PAUSED: MAX_ATTEMPTS=$MAX_ATTEMPTS container start(s) used, no retry (resume by hand: RESUME=1)"; status=3; break; fi
  for f in last.pt mid.pt mid.prev.pt; do [ -e "data/train/$RUN/weights/$f" ] && extra="--resume"; done
  if grep -q "R3-HARD" "$out"; then
    now=$(date +%s)
    echo "$now $(grep -a 'ABORT' "$out" | tail -1 | cut -c1-400)" >> "$D/drop-aborts.log"
    recent=$(awk -v n="$now" -v w="$DROP_WINDOW_S" 'n - $1 <= w' "$D/drop-aborts.log" | wc -l)
    log "R3-HARD frame-drop abort ($recent in the last 2 h): $(grep -a 'ABORT' "$out" | tail -1 | cut -c1-300)"
    if [ "$recent" -ge "$DROP_MAX" ]; then
      export DUTY_CAP_LEVEL=$CAP_LEVEL DUTY_CAP_UNTIL=$((now + CAP_S))
      log "NOTIFY: $recent frame-drop aborts within 2 h: training CAPPED at >= 800 ms per step for the next hour (until $(TZ=Asia/Bangkok date -d "@$DUTY_CAP_UNTIL" '+%H:%M') ICT); it keeps running"
    fi
    log "waiting for 15 quiet minutes (no camera dropping frames); then the slowest level"
    until $QUIET >> "$D/quiet.log" 2>&1; do
      log "no 15 quiet minutes within the gate's 2 h: re-arming the gate (never a stop)"
    done
    export DUTY_START=$FLOOR DUTY_AFTER_ABORT=1
    log "15 quiet minutes: resuming at the slowest level (walking back up slowly)"
    continue
  fi
  pause=$IO_PAUSE_S
  # Only an ABORT line classifies (2026-10-08): an inconclusive R3 no longer aborts -- it logs
  # "R3: inconclusive measurement ... KEEP TRAINING" -- and an IO abort later in the same attempt
  # must not be mistaken for an R3 trip.
  if grep -q "ABORT [^ ]*: R3 \(inconclusive\|latency\)" "$out"; then
    export DUTY_MIN=$(( DUTY_MIN < FLOOR ? DUTY_MIN + 1 : FLOOR )) DUTY_START=$FLOOR DUTY_AFTER_ABORT=0
    log "R3 $(grep -o 'ABORT [^ ]*: R3 \(inconclusive\|latency\)' "$out" | tail -1 | grep -o 'R3 [a-z]*'): the duty floor is now level $DUTY_MIN; resuming in 30 s"
    pause=$R3_PAUSE_S
  elif grep -q "REFUSED $KIND" "$out"; then
    trips=$((trips + 1))
  elif ! grep -q "ABORT $KIND" "$out"; then
    log "TRAIN STOPPED: not a guard trip (see $out)"; status=2; break
  else
    trips=$((trips + 1))
  fi
  if [ "$trips" -gt 3 ]; then log "TRAIN PAUSED: 3 IO/R2 resumes used, resume by hand later (RESUME=1 DUTY_MIN=$DUTY_MIN)"; status=3; break; fi
  log "pausing ${pause} s before the next attempt"
  sleep "$pause"
done
exit "$status"
