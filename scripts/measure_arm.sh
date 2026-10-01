#!/usr/bin/env bash
# One codec/build measurement arm (docs/h264-plan.md): the same three runs for every arm, so the
# tables compare like with like.
#
#   scripts/measure_arm.sh LABEL
#
#   1. indoor rotation   prt_church 99 112  (measure_motion.py rotate 60)
#   2. outdoor rotation  new_4-1 53 111     (busy town square)
#   3. 40 walks          prt_fild08 170 375 (NPC-free; new_4-1's wandering NPC "Shion" blocks walks)
#
# Preconditions (the script does not check them all): mux ASSIST with the GM logged in and online,
# the client visible, the codec already selected (scripts/rdp_reconnect.sh KEYWORD). The typeperf
# counters run on Windows separately; the wall-clock marks this script writes are what the
# Windows-side summary is cut by.
#
# Output (scratch, rule 7): $SCRATCH/arm_LABEL.jsonl, $SCRATCH/delay_raw_LABEL.json, marks in
# $SCRATCH/marks.txt. Exit 3 if a warp fails (nothing measured at the wrong spot).
set -u
L="${1:?usage: scripts/measure_arm.sh LABEL}"
[[ "${L}" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "bad label ${L}" >&2; exit 2; }
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
SCRATCH="${SCRATCH:-/dev/shm/poring-lab-tmp}"
mkdir -p "${SCRATCH}"
OUT="${SCRATCH}/arm_${L}.jsonl" M="${SCRATCH}/marks.txt"
mark() { echo "${L} $1 $(date +%T)" >>"${M}"; }
warp() { uv run python scripts/ro_agent.py gm "@warp $1" || exit 3; sleep 7; }

warp "prt_church 99 112"
mark "indoor start"
uv run python scripts/measure_motion.py rotate 60 --label "${L}_indoor" | tee -a "${OUT}"
mark "indoor end"

warp "new_4-1 53 111"
mark "outdoor start"
uv run python scripts/measure_motion.py rotate 60 --label "${L}_outdoor" | tee -a "${OUT}"
mark "outdoor end"

warp "prt_fild08 170 375"
mark "delay start"
uv run python scripts/measure_delay.py walks 40 --as gm | tee -a "${OUT}"
mark "delay end"
cp "${SCRATCH}/delay_raw.json" "${SCRATCH}/delay_raw_${L}.json"
