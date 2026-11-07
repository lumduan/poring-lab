#!/usr/bin/env bash
# Compile services/vision/requirements-intel.txt (the Intel vision image, ADR-0022) from
# requirements-intel.in. Every package the workspace lock also resolves for poring-vision is held at
# the lock's version, so the Intel image differs from the CUDA one only in the torch stack (XPU),
# OpenVINO and the Intel runtime wheels. Re-run after uv.lock or the .in changes; commit both files.
# Disk-light (CLAUDE.md rule 7): the uv cache and the scratch live in /dev/shm.
set -euo pipefail
cd "$(dirname "$0")/.."
W="${TMPDIR:-/dev/shm/poring-lab-tmp}/intel-req"
mkdir -p "$W"
uv export --package poring-vision --frozen --no-dev --no-hashes --no-emit-workspace --no-header \
  --no-annotate | grep -vE '^(torch|torchvision|triton|nvidia-|cuda-|opencv-python==)' \
  | grep -v '^ *#' > "$W/lock-constraints.txt"
echo opencv-python > "$W/excludes.txt"
UV_CACHE_DIR="$W/uv-cache" uv pip compile services/vision/requirements-intel.in \
  -c "$W/lock-constraints.txt" --excludes "$W/excludes.txt" \
  --extra-index-url https://download.pytorch.org/whl/xpu --index-strategy unsafe-best-match \
  --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --generate-hashes --no-annotate --custom-compile-command scripts/gen_intel_requirements.sh \
  -o services/vision/requirements-intel.txt
rm -rf "$W"
