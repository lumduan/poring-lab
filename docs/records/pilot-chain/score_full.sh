#!/bin/bash
# score_full.sh LABEL: every scorer of a 4BL-base pilot -> /dev/shm/poring-lab-tmp/LABEL/ (score.sh + fight_time + slf + time budget + P2 + late strikes)
set -u
L=$1
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
S=$(ls -d /dev/shm/poring-lab-demo/*xmas02-"$L" | head -1)
O=/dev/shm/poring-lab-tmp/$L
P=.venv/bin/python
bash /dev/shm/poring-lab-tmp/score.sh "$L" > "$O/score.out" 2>&1
$P scripts/fight_time.py "$S" > "$O/fight.json" 2> "$O/fight.err"
$P scripts/slf_score.py "$S" --out "$O/slf.json" > "$O/slf.out" 2>&1
$P scripts/time_budget.py session "$S" > "$O/tb.json" 2> "$O/tb.err"
$P /mnt/poring-lab-datasets/scratch-archive/2026-11-10/garm-confirm/p12.py "$S" > "$O/p12.out" 2>&1
$P scripts/late_strike.py score "$S" > "$O/late.json" 2> "$O/late.err"
echo "scored $L"
$P scripts/client_cell.py score "$S" --out "$O/client_cell.json" > "$O/client_cell.out" 2> "$O/client_cell.err"
echo "client_cell scored $L"
