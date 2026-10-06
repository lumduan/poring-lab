#!/usr/bin/env bash
# YOLO training in the DAYTIME (Batt, 2026-10-06), at a gentle pace: batch 2 / workers 1 unless
# raised on Frigate's evidence (scripts/runbooks/gpumon.sh), the 25 % VRAM cap (train.py), the IO
# guard on (guarded_build.py rundev:), checkpoints every epoch.
# - A guard trip PAUSES: wait 15 min, then --resume from last.pt; at most 3 resumes. Any other
#   failure stops at once: never a retry loop.
# - Never alongside an S2 session (it perturbs the stream measurements): it waits while the lock
#   says console or a clean room is set. To pause for a session started later:
#       pkill -INT -f "poring_vision.train --cache"     # last.pt stays; this script then stops
#   and re-run with RESUME=1 afterwards.
#   [RESUME=1] scripts/runbooks/train-day.sh RUN_NAME CACHE_ID EPOCHS OUT_DIR [BATCH=2] [WORKERS=1]
set -u
cd "$(dirname "$0")/../.."
RUN=${1:?RUN_NAME}; CACHE=/datasets/.framecache/${2:?CACHE_ID}; EPOCHS=${3:?EPOCHS}; D=${4:?OUT_DIR}
BATCH=${5:-2}; WORKERS=${6:-1}
mkdir -p "$D"
log() { echo "$(TZ=Asia/Bangkok date '+%F %T') ICT $*" | tee -a "$D/train.log"; }
s2_active() { grep -q '^BACKEND=console' state/capture-backend 2>/dev/null || [ -e state/cleanroom ]; }
extra=""; [ "${RESUME:-0}" = 1 ] && extra="--resume"
attempt=0
while :; do
  while s2_active; do log "S2 session/clean room active: waiting 5 min"; sleep 300; done
  log "attempt $attempt batch $BATCH workers $WORKERS $extra"
  out="$D/train-guarded-$attempt.out"
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    "rundev:vision@43200=python -m poring_vision.train --cache $CACHE --epochs $EPOCHS --batch $BATCH --workers $WORKERS --name $RUN $extra" \
    > "$out" 2>&1
  rc=$?
  log "attempt $attempt rc=$rc"
  if [ "$rc" -eq 0 ]; then log "TRAIN DONE"; break; fi
  if ! grep -q "ABORT rundev" "$out"; then log "TRAIN STOPPED: not a guard trip (see $out)"; break; fi
  attempt=$((attempt + 1))
  if [ "$attempt" -gt 3 ]; then log "TRAIN PAUSED: 3 resumes used, resume by hand later"; break; fi
  extra="--resume"
  log "guard trip: pausing 15 min before resuming"
  sleep 900
done
