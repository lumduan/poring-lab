#!/bin/bash
# pilot_rec_min.sh LABEL REC_LABEL "EXTRA" [MINUTES]: a 4BL-base pilot beside its 1-fps recorder (REC_LABEL "-" = none);
# the recorder is stopped by ITS OWN PID after the run (O6's slip). Immunity / MVP are the caller's, judged before.
set -u
L=$1 RL=$2 EXTRA=$3 MIN=${4:-25}
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
D=/dev/shm/poring-lab-tmp/$L
mkdir -p "$D"
BASE="--reach-check --far-single --far-approach --explore --walk-pick --kill-gap --loot-first --walk-pick-step --quiet-scan --garm-fly --garm-confirm 2 --late-confirm --still-target --lead-press"
RP=""
if [ "$RL" != "-" ]; then
  nohup nice -n 5 .venv/bin/python scripts/record_session.py --backend rdp --label "$RL" --seconds $((MIN * 60 + 120)) --fps 1 --format png --max-bytes 6G > "$D/recorder.log" 2>&1 < /dev/null &
  RP=$!
  echo "$RP" > "$D/recorder.pid"
  sleep 3
  # 11-11 fix (the aborted p62 recorded 17 min of setup work): stop the recorder when the RUN ends,
  # not when the detect server's time box does
  ( until grep -q "run rc=" "$D/progress.txt" 2>/dev/null; do sleep 2; done; sleep 3; kill -TERM "$RP" 2>/dev/null ) &
fi
bash /dev/shm/poring-lab-tmp/run_pilot_v3.sh "$L" "$BASE $EXTRA" "$MIN"
if [ -n "$RP" ]; then
  sleep 3; kill -TERM "$RP" 2>/dev/null
  for i in $(seq 1 30); do kill -0 "$RP" 2>/dev/null || break; sleep 1; done
  echo "[$(TZ=Asia/Bangkok date +%T)] recorder stopped (alive=$(kill -0 $RP 2>/dev/null && echo yes || echo no))" >> "$D/progress.txt"
fi
echo "[$(TZ=Asia/Bangkok date +%T)] PILOT DONE" >> "$D/progress.txt"
