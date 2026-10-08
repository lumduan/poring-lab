---
doc_type: runbook
status: ACTIVE
related: [../demonstrations.md, ../adr/0018-component-licensing.md]
---

# The CPU unit detector for host-side rules (walk@11's click gate)

**Why it exists (2026-10-08):** walk@11 predicts every unit's position at the click instant from a
detection on the click-decision frame (Batt's decision 3, "CPU is fine, R2"). The host `.venv` has
no torch by design, and the vision container is refused while training holds the GPU (R2), so the
detector runs in its OWN environment, in RAM.

## What it is
- `scripts/detector_worker.py`: onnxruntime on CPU (8 threads), our own letterbox / decode / NMS:
  no ultralytics code at decision time.
- `scripts/unit_detector.py`: the host client (spawns the worker, frames over a pipe). It FAILS
  CLOSED: no environment or model raises `DetectorUnavailable`, and a rule must not click then.
- The model: v0-PNG (`data/train/v0png-20261006/weights/best.pt`, 30 epochs, mAP50 0.864), exported
  to ONNX with a 1280 x 736 input (~180 ms on 8 threads; the square 1280 input took ~500 ms).
  Classes: player / monster / npc.

## Rebuild after a host reboot (`/dev/shm` is wiped)
All of it lives in RAM; nothing touches the shared disk, the host `.venv` or `uv.lock`.

    mkdir -p /dev/shm/poring-lab-detector/model && cd /dev/shm/poring-lab-detector
    export UV_CACHE_DIR=/dev/shm/poring-lab-detector/uv-cache UV_LINK_MODE=copy
    uv venv -q .venv --python 3.12
    uv pip install -q --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchvision
    uv pip install -q --python .venv/bin/python "ultralytics==8.4.165" onnx onnxslim onnxruntime opencv-python-headless
    cp ~/docker/poring-lab/data/train/v0png-20261006/weights/best.pt model/v0png-best.pt
    cd model && ../.venv/bin/python -c "from ultralytics import YOLO; import shutil; \
        shutil.move(YOLO('v0png-best.pt').export(format='onnx', imgsz=(736, 1280), simplify=True, device='cpu'), \
        'v0png-best-736x1280.onnx')"
    rm -rf /dev/shm/poring-lab-detector/uv-cache        # ~1.4 GB of RAM back

Check the export against the pre-registration (sha256 of the .pt is pinned there):

    sha256sum /dev/shm/poring-lab-detector/model/v0png-best.pt

## Known limits (measured 2026-10-08)
- The detected monster box sits ~10-15 px ABOVE the sprite's feet on RDP frames: the gate's +1 step
  and its margin absorb it; the detector's recall on RDP frames is measured before walk@11 runs.
- It does not report our own character (the gate excludes it anyway).
