#!/usr/bin/env bash
# Compile services/vision/requirements-vulkan.txt (the Vulkan vision image, ADR-0022 Amendment
# 2026-11-18b: AMD's path) from requirements-vulkan.in. Every package the workspace lock also
# resolves for poring-vision is held at the lock's version (numpy, protobuf, flatbuffers, packaging).
# Re-run after uv.lock or the .in changes; commit both files.
# Disk-light (CLAUDE.md rule 7): the uv cache and the scratch live in /dev/shm.
set -euo pipefail
cd "$(dirname "$0")/.."
W="${TMPDIR:-/dev/shm/poring-lab-tmp}/vulkan-req"
mkdir -p "$W"
uv export --package poring-vision --frozen --no-dev --no-hashes --no-emit-workspace --no-header \
  --no-annotate | grep -vE '^(torch|torchvision|triton|nvidia-|cuda-|onnxruntime)' \
  | grep -v '^ *#' > "$W/lock-constraints.txt"
UV_CACHE_DIR="$W/uv-cache" uv pip compile services/vision/requirements-vulkan.in \
  -c "$W/lock-constraints.txt" --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --generate-hashes --no-annotate --custom-compile-command scripts/gen_vulkan_requirements.sh \
  -o services/vision/requirements-vulkan.txt
rm -rf "$W"
