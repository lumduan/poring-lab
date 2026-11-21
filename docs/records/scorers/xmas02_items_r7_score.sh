#!/bin/bash
# score_r7.sh: xmas02-items-1080.md Amendment 22 (round 7), ONCE -- score_8a.sh's steps for round 7,
# after the r7 chain (eval_chain_r7.sh + r7b: labels, refs, GPU predictions fi6 + fi5, ONNX fi6,
# the seed-74 pack) and BOTH new blind labellers' answers (t3/answers-eval-r7-L1/L2.json):
# - I5: a latency sample (every 7th ref): CPU (eval_latency, xmas02fi6 vs xmas02fi5) and GPU (the
#   detect server's forward, fi_gpu_latency, each model) -- after 5b's chain ends (no dev detect
#   server). A live Run may play beside (Batt 20:2x: dev does not wait for live); the log says
#   whether one did, since it can only make the GPU numbers worse;
# - both-good (fi_blind_score), then fi_eval --strata r7 --comparator xmas02fi5 with the fi7 rule
#   (--item-floor 0.50 --ring-red 30 --refs), once; a second fi_eval of xmas02fi5 WITHOUT the rule,
#   for the report only.
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
I=/dev/shm/poring-lab-tmp/i1080; E=data/train/eval/xmas02fi6-r7; M=/dev/shm/poring-lab-detector/model
K=$I/key-eval-seed74/answer_key.json; A1=$I/t3/answers-eval-r7-L1.json; A2=$I/t3/answers-eval-r7-L2.json
LIVE=/dev/shm/poring-lab-live-detect/detect.sock; DEV=/dev/shm/poring-lab-detect/detect.sock
O=$I/score-r7.log; say() { local t; t=$(TZ=Asia/Bangkok date +%T); echo "[$t] $*" >> $O; }
n() { python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$1" 2>/dev/null || echo 0; }
NC=$(python3 -c "import json; print(len(json.load(open('$K'))['crops']))")
say "the seed-74 pack has $NC crops"
python3 - <<'PY'
import json
refs = json.load(open("data/train/eval/xmas02fi6-r7/refs.json"))
keys = sorted(refs)[::7]
json.dump({k: refs[k] for k in keys}, open("data/train/eval/xmas02fi6-r7/refs-lat.json", "w"))
PY
say "latency sample: $(n $E/refs-lat.json) frames (every 7th ref)"
until [ "$(n $A1)" = "$NC" ] && [ "$(n $A2)" = "$NC" ]; do sleep 30; done
say "both answer files hold $NC"
until grep -q "CHAIN DONE" /dev/shm/poring-lab-tmp/c5b/chain.log 2>/dev/null; do sleep 60; done
while [ -S "$DEV" ] || ! .venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import guarded_build as gb; sys.exit(0 if gb.worker_not_ready(gb.WORKER) is None else 1)"; do sleep 20; done
say "5b's chain done; no dev detect server; the worker idle; a live Run beside: $([ -S "$LIVE" ] && echo yes || echo no)"
.venv/bin/python scripts/eval_latency.py $E/refs-lat.json --model xmas02fi5=$M/xmas02fi5-last-736x1280.onnx --model xmas02fi6=$M/xmas02fi6-last-736x1280.onnx --out $E/lat-cpu.json > $I/lat-cpu-r7.out 2>&1
say "cpu latency rc=$?"
L=/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log; rm -f $L
CMD=$(.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds 900)
( eval "$CMD" > $I/serve-r7.log 2>&1 ) & SP=$!
for i in $(seq 1 60); do sleep 2; grep -q '"listening".*"precision": "f32".*"gpu_clock"' $L 2>/dev/null && break; done
say "server: $(grep -c '"listening"' $L 2>/dev/null) listening line(s); a live Run beside: $([ -S "$LIVE" ] && echo yes || echo no)"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi6.json xmas02fi6 > $I/gpu-fi6-r7.out 2>&1; say "gpu fi6 rc=$?"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi5.json xmas02fi5 > $I/gpu-fi5-r7.out 2>&1; say "gpu fi5 rc=$?"
for pid in $(.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts'); import guarded_build as gb
for p, (pp, a) in (gb.worker_procs(gb.WORKER) or {}).items():
    if b'poring_vision.detect_server' in b' '.join(a) and not a[0].endswith(b'timeout'): print(p)"); do kill -INT $pid; done
wait $SP; say "server ended"
.venv/bin/python scripts/fi_blind_score.py --key $K $A1 $A2 --both-good $E/both-good.json --out $E/blind.json > $I/blind-r7.out 2>&1
say "blind rc=$? $(tail -1 $I/blind-r7.out | cut -c1-160)"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r7/*.json --predictions gpu=$E/pred-gpu-xmas02fi6.json onnx=$E/pred-onnx-xmas02fi6.json --key $K --evaluated $E/both-good.json --cpu-latency $E/lat-cpu.json --cpu-item xmas02fi6 --cpu-deployed xmas02fi5 --comparator xmas02fi5 --gpu-server $E/gpu-fi6.json $E/gpu-fi5.json --strata r7 --item-floor 0.5 --ring-red 30 --refs $E/refs.json --out $E/score-r7.json > $I/fi-eval-r7.out 2>&1
say "fi_eval r7 (fi6 + the fi7 rule) rc=$? $(sha256sum $E/score-r7.json | cut -c1-16)"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r7/*.json --predictions gpu=$E/pred-gpu-xmas02fi5.json --key $K --evaluated $E/both-good.json --strata r7 --out $E/score-r7-fi5-norule.json > $I/fi-eval-r7-fi5.out 2>&1
say "fi_eval r7 report-only (fi5, no rule) rc=$?"
say "SCORE r7 DONE"
