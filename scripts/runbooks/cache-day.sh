#!/usr/bin/env bash
# A frame cache built in the DAYTIME (Batt, 2026-10-06): niced, under the IO guard
# (guarded_build.py cache:), lossless PNG shards straight to the NAS (nothing on the root disk).
# - A guard trip PAUSES: wait 15 min, then --resume (finished sessions are kept, the cut one is
#   redone); at most 3 resumes. Any other failure stops at once: never a retry loop.
# - Never alongside an S2 session (it perturbs the stream timing): it waits while the lock says
#   console or a clean room is set. To pause for a session started later:
#       pkill -INT -f scripts/build_frame_cache.py      # stops cleanly; this script then stops
#   and re-run this same command afterwards: it resumes by itself (progress.json exists).
#   scripts/runbooks/cache-day.sh OUT_DIR CACHE_ID <build_frame_cache args, no --cache-id/--resume>
set -u
cd "$(dirname "$0")/../.."
D=${1:?OUT_DIR}; ID=${2:?CACHE_ID}; shift 2
mkdir -p "$D"
log() { echo "$(TZ=Asia/Bangkok date '+%F %T') ICT $*" | tee -a "$D/cache.log"; }
s2_active() { grep -q '^BACKEND=console' state/capture-backend 2>/dev/null || [ -e state/cleanroom ]; }
extra=""
[ -e "/mnt/poring-lab-datasets/.framecache/$ID/progress.json" ] && extra="--resume"
attempt=0
while :; do
  while s2_active; do log "S2 session/clean room active: waiting 5 min"; sleep 300; done
  log "attempt $attempt $extra"
  out="$D/cache-guarded-$attempt.out"
  python3 scripts/guarded_build.py --sustain 30 --spike 25 "cache@14400=$* --cache-id $ID $extra" \
    > "$out" 2>&1
  rc=$?
  log "attempt $attempt rc=$rc"
  if [ "$rc" -eq 0 ]; then log "CACHE DONE"; break; fi
  if ! grep -q "ABORT cache" "$out"; then log "CACHE STOPPED: not a guard trip (see $out)"; break; fi
  attempt=$((attempt + 1))
  if [ "$attempt" -gt 3 ]; then log "CACHE PAUSED: 3 resumes used, resume by hand later"; break; fi
  extra="--resume"
  log "guard trip: pausing 15 min before resuming"
  sleep 900
done
