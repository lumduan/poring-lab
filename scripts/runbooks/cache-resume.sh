#!/usr/bin/env bash
# A frame-cache build under Batt's OPTION (a) (2026-10-26 ~20:5x): after an IO-guard abort, wait
# until the capture cgroups have been QUIET for QUIET_MIN minutes (measured by quiet_start.py, as
# io_baseline does) and `--resume` with the SAME arguments, at most MAX_RESUMES times (the night's
# 12). Any other failure, or an abort whose stop was not verified, stops at once (a person looks).
# build_frame_cache.py's --resume refuses changed arguments and checks every recorded shard.
#   MAX_RESUMES=12 QUIET_MIN=10 scripts/runbooks/cache-resume.sh ARGS_FILE TIMEOUT_S LOG
# EXIT CODES: 0 CACHE DONE   2 CACHE STOPPED (a person must look)   3 CACHE PAUSED (cap used)
set -u
cd "$(dirname "$0")/../.."
ARGS_FILE=${1:?ARGS_FILE}; TIMEOUT_S=${2:?TIMEOUT_S}; LOG=${3:?LOG}
MAX_RESUMES=${MAX_RESUMES:-12}; QUIET_MIN=${QUIET_MIN:-10}
GUARD=${GUARD:-python3 scripts/guarded_build.py}  # overridable for tests only
QUIET=${QUIET:-python3 scripts/runbooks/quiet_start.py --quiet-min $QUIET_MIN --max-wait-h 2 -- true}
TMP=${TMPDIR:-/dev/shm/poring-lab-tmp}
ARGS="$(cat "$ARGS_FILE")"
log() { echo "$(TZ=Asia/Bangkok date '+%F %T') $*" >> "$LOG"; }
n=0
while :; do
  out=$(mktemp -p "$TMP" cache-attempt.XXXXXX)
  $GUARD --sustain 30 --spike 25 "cache@$TIMEOUT_S=$ARGS --resume" > "$out" 2>&1
  rc=$?
  cat "$out" >> "$LOG"
  if [ "$rc" -eq 0 ]; then log "CACHE DONE"; rm -f "$out"; exit 0; fi
  if ! grep -q "ABORT cache: .*IO stall" "$out"; then
    log "CACHE STOPPED rc=$rc: not an IO-guard abort (a person must look)"; rm -f "$out"; exit 2
  fi
  if ! grep -q "STOP VERIFIED cache" "$out"; then
    log "CACHE STOPPED: the abort's stop was not verified (a person must look)"; rm -f "$out"; exit 2
  fi
  rm -f "$out"
  n=$((n + 1))
  if [ "$n" -gt "$MAX_RESUMES" ]; then log "CACHE PAUSED: $MAX_RESUMES resumes used"; exit 3; fi
  log "IO abort, resume $n of $MAX_RESUMES: waiting for $QUIET_MIN measured quiet minutes"
  until $QUIET >> "$LOG.quiet" 2>&1; do log "no $QUIET_MIN quiet minutes within 2 h: re-arming"; done
  log "$QUIET_MIN quiet minutes: resuming"
done
