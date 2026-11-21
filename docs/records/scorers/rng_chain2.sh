#!/bin/bash
# rng_chain2.sh (Amendment 2, from rng_chain.sh): ranged-attacker-1080.md section 3 -- A' (the base) vs R (defend_box + defend_ranged)
# at 1080 on the dev lab's Rogue at xmas_dun02, 25 min a run, NOT immune (OFF judged before 5b on
# this game session, the same session since), one-run series of screen_ab.py interleaved
# A' R A' R A' R (rng-A1.., rng-R1..). Each run: 5b's preamble (close-chat, @heal, the warp, the
# zoom check, the chat-window standard), no recorder. A run is valid by the SCORER's own rule
# (screen_ab.valid: >= 80 % of the time box played or a home end, rc 0); an arm short of 3 valid
# runs gets more runs at the end, at most 2 more (every run of the arm counts).
# Starts after 5b's fifth C run ("C5 DONE", cursor-1080.md Amendment 12), then fast-forwards the dev
# checkout to origin/main (the ranged switch, 84d5256c or later) before its first run.
# A file STOP2 in this folder ends this follow-on chain before its next run (STOP ended the first).
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp TZ=Asia/Bangkok
D=/dev/shm/poring-lab-tmp/rng
C=$D/chain.log
say() { echo "[$(TZ=Asia/Bangkok date +%T)] $*" >> "$C"; }
SA=/dev/shm/poring-lab-tmp/screen-ab
flags() {
  case "$1" in
    A) echo "" ;;
    R) echo "--box-set defend_box=true --player-set defend_ranged=on" ;;
  esac
}
valid_run() {  # the scorer's own rule (screen_ab.valid), on the run's scored document
  .venv/bin/python - "$1" <<'PY'
import sys
sys.path.insert(0, "scripts")
import screen_ab as sa
try:
    _, runs = sa.score_block(sys.argv[1])
except Exception:
    sys.exit(1)
sys.exit(0 if runs and sa.valid(runs[0], 25.0) else 1)
PY
}
preamble() {
  say "  close-chat: $(.venv/bin/python scripts/stage2_ab.py close-chat 2>&1 | tail -1)"
  say "  heal: $(.venv/bin/python scripts/crusader.py --char thief gm --job rogue '@heal' 2>&1 | tail -1 | cut -c1-80)"
  say "  warp: $(.venv/bin/python scripts/crusader.py --char thief gm --job rogue '@warp xmas_dun02 114 23' 2>&1 | tail -1 | cut -c1-80)"
  sleep 8
  say "  close-chat: $(.venv/bin/python scripts/stage2_ab.py close-chat 2>&1 | tail -1)"
  local z; z=$(.venv/bin/python /dev/shm/poring-lab-tmp/i1080/zoom_check.py 2>&1 | tail -1)
  say "  close-chat: $(.venv/bin/python scripts/stage2_ab.py close-chat 2>&1 | tail -1)"
  say "  zoom: $z"
  echo "$z" | grep -q '"ok": true' || { say "STOP: zoom not default"; return 3; }
  local cw; cw=$(.venv/bin/python scripts/chat_window.py read 2>&1 | tail -1 | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); print(d["standard"], d["tabs"])' 2>&1)
  say "  chat: $cw"
  [ "$cw" = "True ok" ] || { say "STOP: chat window not standard"; return 4; }
}
run_one() {
  local arm=$1 n=$2 lab="rng-$1$2"
  [ -e "$D/STOP2" ] && { say "STOP2 file: the chain ends before $lab"; exit 0; }
  say "$lab ($arm: $(flags "$arm")) start"
  preamble || exit $?
  # shellcheck disable=SC2046
  .venv/bin/python scripts/screen_ab.py run --label "$lab" --screen 1080 --runs 1 --minutes 25 --model xmas02v1080 $(flags "$arm") > "$D/$lab.out" 2>&1
  local rc=$?
  touch "$D/$lab.ended"
  say "$lab end rc=$rc: $(grep -E 'ended rc|STOPPED|economy record' "$SA/$lab/series.log" 2>/dev/null | tail -2 | cut -c1-140 | tr '\n' ' ')"
  if valid_run "$lab"; then say "$lab VALID"; else say "$lab NOT valid"; fi
  return 0
}
# Amendment 2: the first chain ends by its STOP file after rng-A2; then the fix (60e622b1) reaches the
# dev checkout between runs, and the rest plays: R1 A3 R2 R3, then up to 2 make-up runs an arm.
until grep -qE 'STOP file: the chain ends before' "$C" 2>/dev/null; do sleep 30; done
while pgrep -f "screen_ab.py run" > /dev/null || pgrep -f "rng/rng_chain.sh" > /dev/null || [ -S /dev/shm/poring-lab-detect/detect.sock ]; do sleep 20; done
git fetch -q origin && git merge -q --ff-only origin/main || { say "STOP: the dev checkout did not fast-forward"; exit 2; }
grep -q 'switches: Sequence\[str\] = ()' scripts/screen_ab.py || { say "STOP: the screen_ab fix is not in the checkout"; exit 2; }
say "chain 2 (Amendment 2): the dev checkout at $(git rev-parse --short HEAD); R1 A3 R2 R3"
for spec in "R 1" "A 3" "R 2" "R 3"; do set -- $spec; run_one "$1" "$2"; done
for arm in A R; do
  n=3; extra=0
  while :; do
    v=0; for k in $(seq 1 $n); do valid_run "rng-$arm$k" && v=$((v + 1)); done
    [ $v -ge 3 ] && break
    [ $extra -ge 2 ] && { say "$arm has $v valid runs after 2 more: it stays so"; break; }
    n=$((n + 1)); extra=$((extra + 1)); say "$arm has $v valid runs: one more ($arm$n)"; run_one "$arm" "$n"
  done
done
say "RNG CHAIN DONE"
