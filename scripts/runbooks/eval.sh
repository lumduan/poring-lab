#!/usr/bin/env bash
# A trained best.pt per session (light GPU, ~1 min each).
#   scripts/runbooks/eval.sh RUN_NAME CACHE_ID OUT_DIR SPLIT:SESSION...
# e.g. eval.sh v1-20261005 v1-20261005 /dev/shm/... test:20261004T152232-console-p3-indoor-c
set -u
cd "$(dirname "$0")/../.."
RUN=${1:?RUN_NAME}; CACHE=/datasets/.framecache/${2:?CACHE_ID}; D=${3:?OUT_DIR}; shift 3
mkdir -p "$D"
W=/data/train/$RUN/weights/best.pt
for spec in "$@"; do
  split=${spec%%:*}; sid=${spec#*:}
  echo "== $split $sid $(TZ=Asia/Bangkok date '+%T') ICT" | tee -a "$D/eval.log"
  python3 scripts/guarded_build.py --sustain 30 --spike 25 \
    "rundev:vision@900=python -m poring_vision.train --cache $CACHE --eval $W --split $split --sessions $sid --batch 8 --workers 2" \
    > "$D/eval-$RUN-$sid.out" 2>&1
  echo "   rc=$?" | tee -a "$D/eval.log"
done
echo "EVAL DONE $(TZ=Asia/Bangkok date '+%T') ICT" | tee -a "$D/eval.log"
