---
doc_type: runbook
status: "ACTIVE; the RAM environment was REMOVED 2026-11-02 19:56 ICT for the pause (rebuild below)"
related: [../demonstrations.md, ../adr/0018-component-licensing.md]
---

# The CPU unit detector for host-side rules (walk@11's click gate)

**Why it exists (2026-10-08):** walk@11 predicts every unit's position at the click instant from a
detection on the click-decision frame (Batt's decision 3, "CPU is fine, R2"). The host `.venv` has
no torch by design, and the vision container is refused while training holds the GPU (R2), so the
detector runs in its OWN environment, in RAM.

**State (2026-11-02 19:56 ICT, from `date`): the environment is REMOVED for the pause.** Batt paused
poring-lab on 2026-10-29 (fit-first and candy-closet hold the GPU for days) and approved the RAM
cleanup on 2026-11-02. The `.venv` (1.5 GB) was deleted. The night chain of 2026-11-03 03:06 ICT
archived `model/` to `/mnt/poring-lab-datasets/scratch-archive/2026-11-03/detector-model/` (7 files,
each verified by sha256 on the NAS 03:06:13; the list is `_checksums/detector-model.sha256`) and
removed `/dev/shm/poring-lab-detector`. Until the rebuild, every user fails closed (`DetectorUnavailable`).

## What it is
- `scripts/detector_worker.py`: onnxruntime on CPU (8 threads), our own letterbox / decode / NMS:
  no ultralytics code at decision time.
- `scripts/unit_detector.py`: the host client (spawns the worker, frames over a pipe). It FAILS
  CLOSED: no environment or model raises `DetectorUnavailable`, and a rule must not click then.
- **The model (since 2026-10-13, Batt decision 10): v1** (`data/train/v1png-20261008/weights/last.pt`,
  epoch 30, sha256 `03d53979…`), exported the same way to `model/v1png-last-736x1280.onnx`.
  - Deployment parity on the gold set (docs/benchmarks/v1-vs-v0png.md), position metric, monsters: v1
    ONNX 83 / 8 / 17 (P 0.912, R 0.830), vs v1 PyTorch 0.902 / 0.830, vs v0's ONNX 0.868 / 0.790.
  - ~263 ms median per 1280 x 720 frame on 8 threads (gold frames, 2026-10-13).
- **Before it:** v0-PNG (`data/train/v0png-20261006/weights/best.pt`, 30 epochs, mAP50 0.864), exported
  to ONNX with a 1280 x 736 input (~180 ms on 8 threads; the square 1280 input took ~500 ms). It stays
  in `model/` for a rollback (`unit_detector.V0_MODEL`). Classes: player / monster / npc (both models).

## Rebuild after a host reboot (`/dev/shm` is wiped)
All of it lives in RAM; nothing touches the shared disk, the host `.venv` or `uv.lock`.

    mkdir -p /dev/shm/poring-lab-detector/model && cd /dev/shm/poring-lab-detector
    export UV_CACHE_DIR=/dev/shm/poring-lab-detector/uv-cache UV_LINK_MODE=copy
    uv venv -q .venv --python 3.12
    uv pip install -q --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch torchvision
    uv pip install -q --python .venv/bin/python "ultralytics==8.4.165" onnx onnxslim onnxruntime opencv-python-headless
    N=/mnt/poring-lab-datasets/archive/train   # data/train moved to the NAS (2026-10-21, 2026-10-29)
    cp $N/v1png-20261008/weights/last.pt model/v1png-last.pt     # LIVE (v1), sha256 03d53979...
    cp $N/v0png-20261006/weights/best.pt model/v0png-best.pt     # rollback, sha256 b5966feb...
    cd model && for m in v1png-last v0png-best; do ../.venv/bin/python -c "from ultralytics import YOLO; import shutil; \
        shutil.move(YOLO('$m.pt').export(format='onnx', imgsz=(736, 1280), simplify=True, device='cpu'), \
        '$m-736x1280.onnx')"; done
    rm -rf /dev/shm/poring-lab-detector/uv-cache        # ~1.4 GB of RAM back

➡️ The `cp` lines read `~/docker/poring-lab/data/train/...` until 2026-11-02; those folders are on the
NAS now (both .pt sha256 checked there 2026-11-02 19:5x: v1 `03d53979...`, v0 `b5966feb...`).
**Shortcut after the 2026-11-03 archive:** copy the exported files back instead of exporting again
(`cp .../scratch-archive/2026-11-03/detector-model/* model/`, then `sha256sum -c` of
`_checksums/detector-model.sha256` inside `model/`). It also holds round 2's CPU export
(`gef10r2-last-736x1280.onnx` + `.names.json`). The venv is still installed as above.

Check the export against the pre-registration (sha256 of the .pt is pinned there):

    sha256sum /dev/shm/poring-lab-detector/model/v0png-best.pt

## Known limits (measured 2026-10-08)
- The detected monster box sits ~10-15 px ABOVE the sprite's feet on RDP frames: the gate's +1 step
  and its margin absorb it; the detector's recall on RDP frames is measured before walk@11 runs.
- It does not report our own character (the gate excludes it anyway).
