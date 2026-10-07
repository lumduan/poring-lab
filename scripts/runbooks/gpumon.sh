#!/usr/bin/env bash
# GPU + Frigate sampler for training runs (read-only): every 5 s, one CSV line.
# SUPERSEDED 2026-10-07 by `python3 -S scripts/frigate_r3.py sample OUT.csv` (distinct Frigate
# updates, every detector and camera, Ollama's loaded models); kept for the older CSVs' format.
#   scripts/runbooks/gpumon.sh OUT_CSV
# t_ict, gpu_util%, mem_used_MiB, ollama_MiB, frigate_det_MiB(sum), python_MiB(sum, ours), frigate_inference_ms(mean of detectors)
OUT=${1:?OUT_CSV}
[ -f "$OUT" ] || echo "t,util,mem_used,ollama,frigate_det,python,frigate_inf_ms" > "$OUT"
while true; do
  read -r util mem < <(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits | tr -d ',')
  apps=$(nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader,nounits)
  oll=$(echo "$apps" | awk -F', ' '/llama|ollama/ {s+=$2} END {print s+0}')
  fri=$(echo "$apps" | awk -F', ' '/frigate.detector/ {s+=$2} END {print s+0}')
  py=$(echo "$apps" | awk -F', ' '/python/ {s+=$2} END {print s+0}')
  inf=$(curl -s -m 2 http://127.0.0.1:5000/api/stats | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin)["detectors"]; v=[x.get("inference_speed",0) for x in d.values()]; print(round(sum(v)/len(v),2))
except Exception: print("")' 2>/dev/null)
  echo "$(TZ=Asia/Bangkok date +%T),$util,$mem,$oll,$fri,$py,$inf" >> "$OUT"
  sleep 5
done
