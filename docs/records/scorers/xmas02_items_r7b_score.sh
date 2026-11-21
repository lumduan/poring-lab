#!/bin/bash
# score_r7b.sh: xmas02-items-1080.md Amendment 24 -- round 7's I5 latency AGAIN, in a quiet window,
# and fi_eval with ONLY the latency files replaced. score_r7.sh's first pass measured them during
# 5b's run c5b-B1: its wait matched the 5b log's "hold ends: ... CHAIN DONE" quote, and its cleanup
# killed B1's detect server. The item lines' inputs are unchanged: the labels, the predictions, the
# key and both-good.json from that pass. This waits for the 5b chain's OWN last line, exactly.
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
I=/dev/shm/poring-lab-tmp/i1080; E=data/train/eval/xmas02fi6-r7; M=/dev/shm/poring-lab-detector/model
K=$I/key-eval-seed74/answer_key.json
LIVE=/dev/shm/poring-lab-live-detect/detect.sock; DEV=/dev/shm/poring-lab-detect/detect.sock
O=$I/score-r7b.log; say() { local t; t=$(TZ=Asia/Bangkok date +%T); echo "[$t] $*" >> $O; }
until grep -qE '^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] CHAIN DONE$' /dev/shm/poring-lab-tmp/c5b/chain.log 2>/dev/null; do sleep 60; done
while [ -S "$DEV" ] || pgrep -f "screen_ab.py run" > /dev/null || ! .venv/bin/python -c "import sys; sys.path.insert(0,'scripts'); import guarded_build as gb; sys.exit(0 if gb.worker_not_ready(gb.WORKER) is None else 1)"; do sleep 20; done
say "5b's chain ended (its own last line); no dev detect server, no screen_ab run; the worker idle; a live Run beside: $([ -S "$LIVE" ] && echo yes || echo no)"
mkdir -p $E/void-r7a && mv $E/lat-cpu.json $E/gpu-fi6.json $E/gpu-fi5.json $E/score-r7.json $E/void-r7a/ 2>/dev/null
say "the first pass's latency files and score moved to $E/void-r7a (kept, unread)"
.venv/bin/python scripts/eval_latency.py $E/refs-lat.json --model xmas02fi5=$M/xmas02fi5-last-736x1280.onnx --model xmas02fi6=$M/xmas02fi6-last-736x1280.onnx --out $E/lat-cpu.json > $I/lat-cpu-r7b.out 2>&1
say "cpu latency rc=$?"
L=/dev/shm/poring-lab-tmp/poring-guarded-execdev-vision.log; rm -f $L
CMD=$(.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds 900)
( eval "$CMD" > $I/serve-r7b.log 2>&1 ) & SP=$!
for i in $(seq 1 60); do sleep 2; grep -q '"listening"' $L 2>/dev/null && break; done
say "server: $(grep -c '"listening"' $L 2>/dev/null) listening line(s) (pid $SP)"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi6.json xmas02fi6 > $I/gpu-fi6-r7b.out 2>&1; say "gpu fi6 rc=$?"
.venv/bin/python scripts/fi_gpu_latency.py $E/refs-lat.json $E/gpu-fi5.json xmas02fi5 > $I/gpu-fi5-r7b.out 2>&1; say "gpu fi5 rc=$?"
for pid in $(.venv/bin/python -c "
import sys; sys.path.insert(0,'scripts'); import guarded_build as gb
for p, (pp, a) in (gb.worker_procs(gb.WORKER) or {}).items():
    if b'poring_vision.detect_server' in b' '.join(a) and not a[0].endswith(b'timeout'): print(p)"); do kill -INT $pid; done
wait $SP; say "server ended"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r7/*.json --predictions gpu=$E/pred-gpu-xmas02fi6.json onnx=$E/pred-onnx-xmas02fi6.json --key $K --evaluated $E/both-good.json --cpu-latency $E/lat-cpu.json --cpu-item xmas02fi6 --cpu-deployed xmas02fi5 --comparator xmas02fi5 --gpu-server $E/gpu-fi6.json $E/gpu-fi5.json --strata r7 --item-floor 0.5 --ring-red 30 --refs $E/refs.json --out $E/score-r7.json > $I/fi-eval-r7b.out 2>&1
say "fi_eval r7 (fi6 + the fi7 rule) rc=$? $(sha256sum $E/score-r7.json | cut -c1-16)"
.venv/bin/python scripts/fi_eval.py --labels $I/labels-eval-r7/*.json --predictions gpu=$E/pred-gpu-xmas02fi5.json --key $K --evaluated $E/both-good.json --cpu-latency $E/lat-cpu.json --cpu-item xmas02fi5 --cpu-deployed xmas02fi5 --comparator xmas02fi5 --gpu-server $E/gpu-fi5.json $E/gpu-fi5.json --strata r7 --out $E/score-r7-fi5-norule.json > $I/fi-eval-r7b-fi5.out 2>&1
say "fi_eval r7 report-only (fi5, no rule) rc=$?"
say "SCORE r7b DONE"
