#!/bin/bash
# The night's pilot runner (rogue-xmas02.md Amendment J): run_pilot.sh LABEL "EXTRA FLAGS"
#   the detect server (final: gpu conversion, FP32, the floor from the unit), then the 30-min run
#   with the base command + EXTRA FLAGS; evidence in /dev/shm/poring-lab-tmp/LABEL.
set -u
LABEL=$1
EXTRA=$2
MIN=${3:-25}  # Amendment K: 25-min pilots (two fit inside the MVP's respawn window)
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
D=/dev/shm/poring-lab-tmp/$LABEL
mkdir -p "$D"
LOG=/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log
say() { echo "[$(TZ=Asia/Bangkok date +%T)] $*" >> "$D/progress.txt"; }
say "floor $(cat /sys/class/drm/card1/gt_min_freq_mhz) MHz; flags: $EXTRA; minutes $MIN"
rm -f "$LOG"  # only the NEW step's start line may match (p19's slip read p18's)
.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds $((MIN * 60 + 150)) > "$D/serve.cmd"
( eval "$(cat "$D/serve.cmd")" > "$D/serve.log" 2>&1; echo "serve rc=$?" >> "$D/serve.log" ) & SP=$!
say "server step started"
ok=0
for i in $(seq 1 60); do
  sleep 2
  if grep -q 'REFUSED' "$D/serve.log" 2>/dev/null; then break; fi  # the step's OWN log (p19's slip)
  if [ -S /dev/shm/poring-lab-detect/detect.sock ] && grep -q '"listening".*"precision": "f32".*"gpu_clock": {"min": 2450' "$LOG" 2>/dev/null; then ok=1; break; fi
done
# 11-12 09:3x fix: the detect-prio server puts "hud_wait_ms" between precision and gpu_clock (two p84s
# refused); a refusal also writes "run rc=REFUSED" so the chain ends the server in 30 s and the recorder stops
if [ $ok = 0 ]; then say "REFUSED: no listening line with f32 + floor 2450 (the step: $(grep -o 'REFUSED.*' "$D/serve.log" | head -1 | cut -c1-120))"; say "run rc=REFUSED"; wait $SP; exit 2; fi
say "server listening: $(grep -o '"listening".*' "$LOG" | head -1 | cut -c1-260)"
TZ=Asia/Bangkok date '+%F %T' > "$D/start.txt"
say "run start"
# shellcheck disable=SC2086
nice -n 10 uv run --quiet python scripts/dungeon_hunt.py run --char rogue --map xmas_dun02 \
    --strategy P2 --search patrol --walk-trust --npc-guard --miss-cue --loot trim \
    --clear-map --minutes "$MIN" --seed 20261105 --label "xmas02-$LABEL" --box-strike --box-now \
    --self-recheck --still-strike --engage-screen $EXTRA > "$D/run.log" 2>&1
say "run rc=$?"
wait $SP
say "server step ended: $(grep -v '^  |' "$D/serve.log" | tail -2 | tr '\n' ' ' | cut -c1-300)"
say "ALL DONE"
