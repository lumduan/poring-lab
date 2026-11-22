#!/bin/bash
# score_r8.sh: xmas02-items-1080.md Amendments 26 / 30 (round 8), ONCE -- score_r7.sh's steps for
# round 8, after the r8 chain (eval_chain_r8.sh: the eight held-out sessions labelled --eval-test
# against the frozen xmas02fi8, refs, GPU predictions fi8 + fi6 + fi5, ONNX fi8, the seed-75 pack)
# and BOTH new blind labellers' answers (t4/answers-eval-r8-L1/L2.json):
# - I5: a latency sample (every 7th ref): CPU (eval_latency, xmas02fi8 vs xmas02fi5) and GPU (the
#   detect server's forward, fi_gpu_latency, each model) -- with no dev detect server, no screen_ab
#   run and the dev worker idle. A live Run may play beside (Batt 11-22: dev does not yield); the
#   log says whether one did, since it can only make the GPU numbers worse;
# - both-good (fi_blind_score); a failed blind step stops here (no score);
# - fi_eval --strata r8 --comparator xmas02fi5 with the fi7 rule unchanged (--item-floor 0.50
#   --ring-red 30 --refs; pad 6), once: THE BARS;
# - report only (no bar): xmas02fi6 + the fi7 rule, and xmas02fi5 without it, on the same
#   held-out, evaluated crops and key (no latency inputs: their I5 reads NO_VERDICT).
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
I=/dev/shm/poring-lab-tmp/i1080; E=data/train/eval/xmas02fi8-r8; M=/dev/shm/poring-lab-detector/model
K=$I/key-eval-seed75/answer_key.json; A1=$I/t4/answers-eval-r8-L1.json; A2=$I/t4/answers-eval-r8-L2.json
LIVE=/dev/shm/poring-lab-live-detect/detect.sock; DEV=/dev/shm/poring-lab-detect/detect.sock
O=$I/score-r8.log; say() { local t; t=$(TZ=Asia/Bangkok date +%T); echo "[$t] $*" >> $O; }
n() { python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$1" 2>/dev/null || echo 0; }
ram_wait() { until [ "$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)" -ge "$1" ]; do sleep 20; done; }
NC=$(python3 -c "import json; print(len(json.load(open('$K'))['crops']))")
say "the seed-75 pack has $NC crops"
python3 - <<'PY'
import json
refs = json.load(open("data/train/eval/xmas02fi8-r8/refs.json"))
keys = sorted(refs)[::7]
json.dump({k: refs[k] for k in keys}, open("data/train/eval/xmas02fi8-r8/refs-lat.json", "w"))
PY
say "latency sample: $(n $E/refs-lat.json) frames (every 7th ref)"
until [ "$(n $A1)" = "$NC" ] && [ "$(n $A2)" = "$NC" ]; do sleep 30; done
say "both answer files hold $NC"
while [ -S "$DEV" ] || pgrep -f "screen_ab.py run" > /dev/null || ! .venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import guarded_build as gb; sys.exit(0 if gb.worker_not_ready(gb.WORKER) is None else 1)"; do sleep 20; done
ram_wait 2500
say "no dev detect server, no screen_ab run; the worker idle; MemAvailable $(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo) MB; a live Run beside: $([ -S "$LIVE" ] && echo yes || echo no)"
.venv/bin/python scripts/eval_latency.py $E/refs-lat.json --model xmas02fi5=$M/xmas02fi5-last-736x1280.onnx --model xmas02fi8=$M/xmas02fi8-last-736x1280.onnx --out $E/lat-cpu.json > $I/lat-cpu-r8.out 2>&1
say "cpu latency rc=$?"
L=/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log; rm -f $L
CMD=$(.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds 900)
( eval "$CMD" > $I/serve-r8.log 2>&1 ) & SP=$!
for i in $(seq 1 60); do sleep 2; grep -q '"listening"' $L 2>/dev/null && break; done
say "server: $(grep -c '"listening"' $L 2>/dev/null) listening line(s) (pid $SP); a live Run beside: $([ -S "$LIVE" ] && echo yes || echo no)"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi8.json xmas02fi8 > $I/gpu-fi8-r8.out 2>&1; say "gpu fi8 rc=$?"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi5.json xmas02fi5 > $I/gpu-fi5-r8.out 2>&1; say "gpu fi5 rc=$?"
for pid in $(.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts'); import guarded_build as gb
for p, (pp, a) in (gb.worker_procs(gb.WORKER) or {}).items():
    if b'poring_vision.detect_server' in b' '.join(a) and not a[0].endswith(b'timeout'): print(p)"); do kill -INT $pid; done
wait $SP; say "server ended"
.venv/bin/python scripts/fi_blind_score.py --key $K $A1 $A2 --both-good $E/both-good.json --out $E/blind.json > $I/blind-r8.out 2>&1
rc=$?
say "blind rc=$rc; both-good $(n $E/both-good.json) crops"
[ $rc -eq 0 ] || { say "STOP: the blind step failed (no score)"; exit 2; }
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r8/*.json --predictions gpu=$E/pred-gpu-xmas02fi8.json onnx=$E/pred-onnx-xmas02fi8.json --key $K --evaluated $E/both-good.json --cpu-latency $E/lat-cpu.json --cpu-item xmas02fi8 --cpu-deployed xmas02fi5 --comparator xmas02fi5 --gpu-server $E/gpu-fi8.json $E/gpu-fi5.json --strata r8 --item-floor 0.5 --ring-red 30 --refs $E/refs.json --out $E/score-r8.json > $I/fi-eval-r8.out 2>&1
say "fi_eval r8 (fi8 + the fi7 rule) rc=$? $(sha256sum $E/score-r8.json | cut -c1-16)"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r8/*.json --predictions gpu=$E/pred-gpu-xmas02fi6.json --key $K --evaluated $E/both-good.json --comparator xmas02fi5 --strata r8 --item-floor 0.5 --ring-red 30 --refs $E/refs.json --out $E/score-r8-fi6-rule.json > $I/fi-eval-r8-fi6.out 2>&1
say "fi_eval r8 report-only (fi6 + the fi7 rule) rc=$?"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r8/*.json --predictions gpu=$E/pred-gpu-xmas02fi5.json --key $K --evaluated $E/both-good.json --comparator xmas02fi5 --strata r8 --out $E/score-r8-fi5-norule.json > $I/fi-eval-r8-fi5.out 2>&1
say "fi_eval r8 report-only (fi5, no rule) rc=$?"
say "SCORE r8 DONE"
