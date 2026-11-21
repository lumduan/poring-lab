#!/bin/bash
# c5b_c5.sh (Amendment 12, from c5b_chain.sh): cursor-1080.md 5b (Amendments 8 and 9) -- the four-arm play A/B at 1080, 25 min a
# run, NOT immune (OFF judged once before the series, the same session since), one-run series of
# screen_ab.py interleaved A B C D x 3; an invalid run (rc != 0, short, < 20 min played) gets ONE
# more run of its arm at the end. Each run: pilot_rec.sh's preamble (close-chat, @heal, the warp,
# the zoom check, the chat-window standard), no recorder. Holds:
#   - the round-7 item evaluation first: until its pack (or its script ends), the chain waits
#     before its next run, whatever live does (Amendment 9; Amendment 10);
#   - D2 (Amendment 9, REPORTED only since Amendment 10: Batt "dev need not wait, live slower is
#     fine"): during a D run the live detect server's minute p95 is logged to <label>.d2.
# A file STOP in this folder ends the chain before its next run.
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp TZ=Asia/Bangkok
D=/dev/shm/poring-lab-tmp/c5b
C=$D/chain.log
say() { echo "[$(TZ=Asia/Bangkok date +%T)] $*" >> "$C"; }
LIVE=/dev/shm/poring-lab-live-detect/detect.sock
LIVELOG=/dev/shm/poring-lab-live-tmp/poring-guarded-execdev-vision.log
EV=/dev/shm/poring-lab-tmp/i1080/eval-chain-r7.log
SA=/dev/shm/poring-lab-tmp/screen-ab
flags() {
  case "$1" in
    A) echo "" ;;
    B) echo "--box-set CURSOR_WAIT_S=1.0" ;;
    C) echo "--player-set cursor_click_on_sight=on" ;;
    D) echo "--player-set cursor_click_on_sight=on --box-set BOX_EVERY_S=0.25" ;;
  esac
}
hold_for_eval() {
  # the round-7 item evaluation first (Batt's order), WHATEVER live does: since 20:3x its last GPU
  # step no longer waits for live (eval_chain_r7b.sh, Batt "live slower is fine"), so this hold
  # cannot deadlock; it ends at its pack, or when its script is no longer running (then logged)
  local said=0
  while ! grep -q "eval pack (round 7" "$EV" 2>/dev/null && pgrep -f "eval_chain_r7b.sh" > /dev/null; do
    [ $said = 0 ] && say "hold: the item evaluation's GPU / ONNX / pack steps go first" && said=1
    sleep 30
  done
  [ $said = 1 ] && say "hold ends: $(tail -1 "$EV" | cut -c1-120)"
  return 0
}
# D2: the live server's minute stats, p95 > 35 ms three in a row -> the run's STOP file
d2_watch() {
  local lab=$1 stopf=$2 n=0 seen
  seen=$(wc -l < "$LIVELOG" 2>/dev/null || echo 0)
  while [ ! -e "$D/$lab.ended" ]; do
    sleep 20
    [ -S "$LIVE" ] || { n=0; continue; }
    local now; now=$(wc -l < "$LIVELOG" 2>/dev/null || echo 0)
    [ "$now" -gt "$seen" ] || continue
    local p; p=$(sed -n "$((seen + 1)),${now}p" "$LIVELOG" | grep '"stats"' | tail -1 | .venv/bin/python -c 'import json,sys
t=sys.stdin.read().strip()
print(json.loads(t[t.index("{"):]).get("ms_p95") if "{" in t else "")' 2>/dev/null)
    seen=$now
    [ -n "$p" ] && [ "$p" != "None" ] || continue
    echo "$(TZ=Asia/Bangkok date +%T) live p95 $p" >> "$D/$lab.d2"
  done
}
valid_run() {  # rc 0, not short, >= 20 min played, not yielded
  local lab=$1
  [ -e "$D/$lab.yielded" ] && return 1
  .venv/bin/python - "$SA/$lab/done.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
r = d[0] if d else {}
sys.exit(0 if r.get("rc") == 0 and not r.get("short") and float(r.get("s") or 0) >= 1200 else 1)
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
  local arm=$1 n=$2 lab="c5b-$1$2"
  [ -e "$D/STOP" ] && { say "STOP file: the chain ends before $lab"; exit 0; }
  hold_for_eval
  say "$lab ($arm: $(flags "$arm")) start"
  preamble || exit $?
  local w=""
  if [ "$arm" = D ]; then
    d2_watch "$lab" "$SA/$lab/$lab-r01B.STOP" & w=$!
  fi
  # shellcheck disable=SC2046
  .venv/bin/python scripts/screen_ab.py run --label "$lab" --screen 1080 --runs 1 --minutes 25 --model xmas02v1080 $(flags "$arm") > "$D/$lab.out" 2>&1
  local rc=$?
  touch "$D/$lab.ended"; [ -n "$w" ] && wait "$w" 2>/dev/null
  say "$lab end rc=$rc: $(grep -E 'ended rc|STOPPED|economy record' "$SA/$lab/series.log" 2>/dev/null | tail -2 | cut -c1-140 | tr '\n' ' ')"
  if valid_run "$lab"; then say "$lab VALID"; else say "$lab NOT valid"; fi
  return 0
}
# Amendment 12: C has 2 valid runs (C1 void, C3 a stock-out end at 15.0 min); C gets a fifth run,
# after round 7's score wrapper (xmas02_items_r7b_score.sh) has ended: its own last line, exactly,
# and no dev detect server left.
R7=/dev/shm/poring-lab-tmp/i1080/score-r7b.log
until grep -qE '^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] SCORE r7b DONE$' "$R7" 2>/dev/null; do sleep 30; done
while pgrep -f "score_r7b.sh" > /dev/null || [ -S /dev/shm/poring-lab-detect/detect.sock ]; do sleep 20; done
say "c5 (Amendment 12): round 7's score wrapper ended; C gets a fifth run"
run_one C 5
say "C5 DONE"
