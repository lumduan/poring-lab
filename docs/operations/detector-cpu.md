---
doc_type: runbook
status: "ACTIVE: rebuilt 2026-11-05 15:07 ICT; since 2026-11-07 16 threads and a map-scoped model for xmas_dun02 (section 'Map-scoped models'); since 2026-11-07 13:4x the box watcher uses the GPU's detect server first, this detector behind it (section 'The GPU path')"
related: [../demonstrations.md, ../adr/0018-component-licensing.md]
---

# The CPU unit detector for host-side rules (walk@11's click gate)

**Why it exists (2026-10-08):** walk@11 predicts every unit's position at the click instant from a
detection on the click-decision frame (Batt's decision 3, "CPU is fine, R2"). The host `.venv` has
no torch by design, and the vision container is refused while training holds the GPU (R2), so the
detector runs in its OWN environment, in RAM.

➡️ **REBUILT 2026-11-05 15:07 ICT** (the `.venv` and `model/` in `/dev/shm/poring-lab-detector`); the
paragraph below is history.

**State (2026-11-02 19:56 ICT, from `date`): the environment is REMOVED for the pause.** Batt paused
poring-lab on 2026-10-29 (fit-first and candy-closet hold the GPU for days) and approved the RAM
cleanup on 2026-11-02. The `.venv` (1.5 GB) was deleted. The night chain of 2026-11-03 03:06 ICT
archived `model/` to `/mnt/poring-lab-datasets/scratch-archive/2026-11-03/detector-model/` (7 files,
each verified by sha256 on the NAS 03:06:13; the list is `_checksums/detector-model.sha256`) and
removed `/dev/shm/poring-lab-detector`. Until the rebuild, every user fails closed (`DetectorUnavailable`).

## What it is
- `scripts/detector_worker.py`: onnxruntime on CPU (`unit_detector.THREADS`: **16 since 2026-11-07**,
  Batt's decision after docs/benchmarks/cpu-detector-speed.md; 8 before), our own letterbox /
  decode / NMS: no ultralytics code at decision time. An optional NMS-groups argument suppresses
  several classes together (the map-scoped models below).
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

## Map-scoped models (Batt 2026-11-07: "use it"; docs/planning/xmas02-detector.md T-11)
- `unit_detector.for_map(map)` gives the map's own model when `MAP_MODELS` has one, else v1. The
  ONNX's sha256 is pinned there: a different file fails closed (`DetectorUnavailable`).
- **xmas_dun02:** `model/xmas02-last-736x1280.onnx` (sha256 `293dca92...`, from last.pt `5c5bb67a...`;
  docs/benchmarks/xmas02-eval.md PASSED 2026-11-07 00:39) with its `.names.json` (player, npc, warp,
  mystcase, cruiser, cookie, cookie_xmas).
  ➡️ **SUPERSEDED 2026-11-10 06:53 (3d8427a3, xmas02-detector.md M12):** `MAP_MODELS` now names
  `xmas02gb-last-736x1280.onnx` (sha256 `b22d972b...`, GPU name `xmas02gb`). It keeps `garm_baby`
  as its own class (never collapsed: the runner never strikes it, and `--garm-fly` reads it); the
  four species are still renamed `monster`. `xmas02` stays in `GPU_WEIGHTS` as the rollback.
  (second-install-gaps.md row G.)
- Its four species are renamed `monster` and suppressed TOGETHER (one NMS group): per-class NMS
  drew a Cookie AND a Christmas Cookie box on one sprite (13 of 964 boxes on X2). The positive case
  on 113 real X2 frames (13 with a double, 100 random): 197 monster boxes -> 184; all 13 dropped
  boxes overlapped a higher-scored box of another species at IoU > 0.5; 0 added; 0 doubles left.
  `Box.species` keeps the model's class.
- The user is `dungeon_hunt.py`'s box watcher (`--box-model map`, the default; `--box-model v1` is
  the rollback). Every other user still calls `UnitDetector()`: v1.

## The GPU path (Batt 2026-11-07, option A; ADR-0005 Amendment 2026-11-07)
- ➡️ On bot-server (the Intel Arc, since the 2026-11-07 cutover) the detect server runs on
  OpenVINO IN the Intel vision worker: `worker:vision@60`, then the step that
  `.venv/bin/python scripts/unit_detector.py serve-cmd --backend openvino --seconds <run + 10 min>`
  prints (the pinned ONNX files from the NAS's `archive/models/`). The CUDA `.pt` path below is
  ubuntu-docker's.
- `unit_detector.for_map_gpu(map)` = this CPU detector behind the vision worker's GPU detect server
  (`poring_vision.detect_server`): the SAME model's forward pass on the GPU (pinned `.pt` sha256s,
  `GPU_WEIGHTS`), decoded on the host by this worker's own code. Parity on 200 frames: 1.000, the
  largest box difference 0.1 px (docs/planning/gpu-live-detector.md 6a).
- Any failure gives this detector's boxes: no server (the socket is absent), R3's pause window, a
  250-ms timeout, a bad reply. The GPU is retried every 5 s. A wrong sha256 or an unsafe socket
  turns it off for the run.
- **To use it beside a run** (`dungeon_hunt.py`'s default `--box-detector gpu`; `cpu` = rollback):

      python3 scripts/runbooks/quiet_start.py --quiet-min 10 --limit 25 -- \
          python3 scripts/guarded_build.py --sustain 30 --spike 25 worker:vision@120
      eval "$(.venv/bin/python scripts/unit_detector.py serve-cmd --seconds <run + 10 min>)"
      ... the runner, once /dev/shm/poring-lab-detect/detect.sock exists ...
      python3 scripts/guarded_build.py worker-stop:vision

  The step ends at its time box with `FAILED rc=124` (that is `timeout` ending a server); read
  the line before it for the verified stop. A step over 20 min uses R3's 180-s windows: until 4
  load-matched pairs pass, the worker is paused half the time and the CPU serves then.
- Each GPU-path detection is logged in the session's `detections.jsonl` (wall time, path,
  preference, reason).

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
**The xmas_dun02 model** (2026-11-07): copy `scratch-archive/2026-11-07/detector-model/*` (its ONNX
and `.names.json`; `_checksums/detector-model.sha256` there) into `model/`. `for_map` checks the
ONNX's sha256 itself.

Check the export against the pre-registration (sha256 of the .pt is pinned there):

    sha256sum /dev/shm/poring-lab-detector/model/v0png-best.pt

## Known limits (measured 2026-10-08)
- The detected monster box sits ~10-15 px ABOVE the sprite's feet on RDP frames: the gate's +1 step
  and its margin absorb it; the detector's recall on RDP frames is measured before walk@11 runs.
- It does not report our own character (the gate excludes it anyway).
