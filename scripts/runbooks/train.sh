#!/usr/bin/env bash
# One YOLO training run in the night window (Batt: heavy training 20:00-05:00 only; batch 4,
# workers 2 accepted for Frigate). Resumable: an IO-guard SIGINT (or any failure) waits 5 min and
# resumes from last.pt, at most 3 times; it never runs past 04:55 ICT.
#   scripts/runbooks/train.sh RUN_NAME CACHE_ID EPOCHS OUT_DIR
# (the v0 baseline's train.sh of 2026-10-04, kept in the repo this time)
set -u
cd "$(dirname "$0")/../.."
RUN=${1:?RUN_NAME}; CACHE=/datasets/.framecache/${2:?CACHE_ID}; EPOCHS=${3:?EPOCHS}; D=${4:?OUT_DIR}
mkdir -p "$D"
END=$(TZ=Asia/Bangkok date -d "04:55" +%s)
[ "$END" -lt "$(date +%s)" ] && END=$(TZ=Asia/Bangkok date -d "tomorrow 04:55" +%s)
attempt=0
while :; do
  left=$(( END - $(date +%s) ))
  if [ "$left" -lt 900 ]; then echo "$(date '+%T') under 15 min left: stop" | tee -a "$D/train.log"; break; fi
  extra=""; [ "$attempt" -gt 0 ] && extra="--resume"
  echo "$(TZ=Asia/Bangkok date '+%T') ICT / $(date -u '+%T') UTC attempt $attempt ($left s left) $extra" | tee -a "$D/train.log"
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    "rundev:vision@${left}=python -m poring_vision.train --cache $CACHE --epochs $EPOCHS --batch 4 --workers 2 --name $RUN $extra" \
    >> "$D/train-guarded.out" 2>&1
  rc=$?
  echo "$(TZ=Asia/Bangkok date '+%T') ICT attempt $attempt rc=$rc" | tee -a "$D/train.log"
  [ "$rc" -eq 0 ] && { echo "TRAIN DONE" | tee -a "$D/train.log"; break; }
  attempt=$((attempt + 1))
  if [ "$attempt" -gt 3 ]; then echo "TRAIN STOPPED: 3 resumes used" | tee -a "$D/train.log"; break; fi
  sleep 300
done
