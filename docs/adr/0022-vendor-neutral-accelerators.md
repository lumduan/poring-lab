---
doc_type: decision
hypothesis: null
status: ACCEPTED
role: null
verdict_date: 2026-11-07
verdict_ticket: null
supersedes: null
related: [0005-vision-x-access.md, 0018-component-licensing.md, ../planning/gpu-live-detector.md, ../planning/bot-server-migration.md]
next_action: "Intel first (bot-server's Arc A380): the OpenVINO inference backend + the torch device layer, each proven on bot-server against the CPU boxes / a real training cache. NVIDIA keeps working on ubuntu-docker; a dedicated NVIDIA host uses dedicated-nvidia (Amendment 2026-11-12) and proves it there first (check_gpu, a serve test, the parity check); AMD is designed in and untested until a host has one."
---

# ADR-0022: Vendor-neutral accelerators (Intel, NVIDIA, AMD; chosen per host)

- **Status:** ACCEPTED 2026-11-07. Batt, answering the 16:25 report (Thai, translated): "Do not
  lock our bot to one GPU vendor, using NVIDIA CUDA. I want it to support many GPUs, e.g. AMD,
  NVIDIA, Intel, depending on which host we run it on; choose freely. Do Intel first." The
  principle is Batt's; the design below is the agent's, and Batt may revise it.
- **Context:**
  - Until today every GPU path was NVIDIA-only: the CUDA 13 image, compose `driver: nvidia`,
    `configure_gpu` -> `cuda:0`, `train.py`'s `torch.cuda`, the detect server's
    `torch.cuda.synchronize`, `check_gpu.py`'s sm_120, nvidia-smi in the R3 monitor.
  - The bot is moving to bot-server, whose GPU is an Intel Arc A380. Its test passed:
    bot-server-migration.md 9.

## Decision
1. **Inference runs the deployed ONNX on any runtime.** The ONNX files are already the pinned
   deployment format (`unit_detector.MAP_MODELS` sha256s); the CPU path runs them with
   onnxruntime.
   - A GPU runtime runs the same file: OpenVINO for Intel (GPU or CPU); onnxruntime with the
     CUDA / TensorRT provider for NVIDIA, or ROCm / MIGraphX for AMD; torch (today's path) stays
     an option.
   - The detect server picks its backend with `--backend` and `--device`. Its protocol (frames
     in, the head's raw output out) and the host's decode do not change.
   - So the boxes match across vendors by construction: the same file, the same decode, only the
     forward differs, proven per host by the parity check (gpu-live-detector.md 6).
2. **Training uses torch's device string, chosen per host:**
   - `cuda` (NVIDIA CUDA; also AMD ROCm builds, which expose the same `torch.cuda` API);
   - `xpu` (Intel);
   - `mps`;
   - `cpu`.
   One small module, `poring_vision.accel`, owns everything vendor-specific: which device, the
   memory cap, peak memory, synchronize, empty-cache, the RNG states for checkpoints. Nothing else
   calls `torch.cuda` directly. ultralytics takes the same device strings.
3. **A host profile says what a host has**, instead of code assuming it:
   - its accelerator;
   - its inference backend and device;
   - its training device;
   - whether it is SHARED.
   ubuntu-docker is shared: Frigate's GPU, quant's disk, so R1-R3 and the IO guard apply there.
   bot-server is dedicated: Batt 2026-11-07, "use it fully, no limits like this machine"; there
   R1-R3 do not apply (no Frigate), and the IO guard has no capture to protect.
4. **Images per vendor:** the CUDA image stays for NVIDIA. An Intel image (the compute runtime +
   OpenVINO + torch-xpu) and an AMD one (ROCm) are built when a host needs them. The vision code
   stays one tree.
5. **Unchanged:**
   - the AGPL boundary (ADR-0018): ultralytics only inside `services/vision`;
   - ADR-0005's isolation: frames in, numbers out; no X, no input;
   - a model's weights load only by their pinned sha256.

## Consequences
- A host with any of the three vendors, or none (the CPU detector), runs the same bot. Moving a
  host means writing its profile and proving parity there, not changing code.
- The NVIDIA-only checks (`check_gpu.py` sm_120, nvidia-smi in R3) become the NVIDIA case of the
  host profile. R3 stays exactly as it is on ubuntu-docker.
- AMD is designed in but unproven: no host here has an AMD GPU.

## Implementation (2026-11-07)
- Decision 3, the host profile: `scripts/host_profile.py`, named by `LAB_HOST_PROFILE` in `.env`.
  Unset means `shared-nvidia` (ubuntu-docker), so a host is dedicated only by declaration.
  guarded_build adds the profile's compose overlay last, and on a DEDICATED host skips R1-R3, the
  R2 co-tenant watch and the duty cycle, and idles the IO guard. It refuses every step on a
  declared-dedicated host where a capture service runs (`dedicated_refusal`). VM 103's commands
  are unchanged (`test_host_profile.py`).
- Decision 4, the Intel image: `services/vision/Dockerfile.intel` + `requirements-intel.txt`
  (scripts/gen_intel_requirements.sh: every package the lock also has at the lock's version, by
  hash), selected by `compose.intel.yaml` / `compose.vision-worker.intel.yaml` (the image, the DRM
  render node and render group, `PORING_ACCEL=xpu`; nothing else, `test_guards.py`). Built on
  bot-server 2026-11-07 (11.8 GB); a guarded `run:vision` there saw the A380 (torch 2.15.0+xpu),
  ran a matmul, OpenVINO listed `GPU`, and an ultralytics forward ran on xpu.

## Amendment 2026-11-12: dedicated-nvidia
- **Batt (Thai, translated):** "NVIDIA on a new machine still needs a profile -- please add NVIDIA
  too; we already tried it on the old server, remember?"
- **Why:** until now a NEW host with its own NVIDIA card could choose only between two wrong
  profiles:
  - `shared-nvidia`: its R3 needs Frigate's stats and fails closed without them, so every GPU step
    is refused;
  - `dedicated-intel`: the Intel image and the DRM render node, wrong for an NVIDIA card.
- **What it is:** a third profile, `dedicated-nvidia` (`scripts/host_profile.py`): shared-nvidia's
  NVIDIA path with dedicated-intel's dedicated rules.

  | | shared-nvidia (VM 103) | dedicated-nvidia | dedicated-intel (bot-server) |
  |---|---|---|---|
  | accelerator, detect backend, GPU lister | cuda, torch, nvidia-smi | cuda, torch, nvidia-smi | xpu, openvino, drm-fdinfo |
  | vision image | the CUDA image (torch 2.14.0+cu130) | the same CUDA image | the Intel image |
  | GPU in compose | the NVIDIA reservation | the same reservation | the render node + render group |
  | VRAM cap default | 0.25 (R1) | 1.0 | 1.0 |
  | R1-R3, co-tenant watch, duty cycle | yes | no | no |
  | IO guard on capture cgroups | yes | idle | idle |
  | SET-hour shipping gate | yes | no | no |
  | recorder disk floor | 100 GB | 30 GB | 30 GB |
  | refused if a capture service runs there (`dedicated_refusal`) | - | yes | yes |

  - Its overlays, `compose.nvidia.yaml` and `compose.vision-worker.nvidia.yaml`, change exactly
    ONE thing: `VISION_MAX_VRAM_FRACTION` defaults to 1.0 (`test_guards.py` pins it; a diff of
    the merged compose config with and without them shows that one key only). A value in `.env`
    still wins, so a dedicated-nvidia host sets `VISION_MAX_VRAM_FRACTION=1.0` there.
  - The worker keeps compose.vision-worker.yaml's 6 GB memory cap. The Intel worker's 11 GB was
    bot-server's own (15 GiB, Batt 2026-11-08).
  - The recorder floor follows the profile's `shared` flag, not its name
    (`dataset_ship.MIN_FREE_BY_PROFILE` is derived from it). The SET-hour gate already did.
- **What it is NOT:**
  - **Not for VM 103 (ubuntu-docker).** Its GPU is shared with Frigate, Ollama and fit-first's
    VTON worker, and its disk with live quant capture. It stays unset = `shared-nvidia`, with
    every rule of CLAUDE.md rule 5 and exactly its old commands. A dedicated profile on a host
    with a capture service is refused at every step.
  - Not a CPU-only profile: that gap stays open (docs/planning/second-install-gaps.md D).
  - Not a new image, and not proven on a dedicated host. The NVIDIA path ran only on VM 103 (the
    RTX 5060 Ti, shared: the detect server's torch backend 49-52 ms a call, paused half the time
    while R3 measured). The first dedicated-nvidia host proves it with `scripts/check_gpu.py`, a
    serve test and the parity check (gpu-live-detector.md 6).
- **Its needs on the host (from the CUDA image):** an NVIDIA driver of release 580 or newer
  (the image is CUDA 13.0; a CUDA 13.2 image refuses to start on R580) and the NVIDIA Container
  Toolkit for compose's `driver: nvidia` reservation.
- Built 2026-11-12 on the branch `feat/dedicated-nvidia` (commit da115f3f): the profile, the two
  overlays, the floor, and their tests (`test_host_profile.py`, `test_dataset_ship.py`,
  `test_guards.py`).


- ➡️ 2026-11-12 (Batt: "write it in the docs"): training on a dedicated-NVIDIA host needs more than the
  worker's 6 GB (bot-server's trainer was OOM-killed at 6 GB; its Intel overlay gives 11 GB). Raise it in
  the machine's own `compose.override.yaml` (`mem_limit` == `memswap_limit`), never in a tracked file:
  docs/setup/new-lab-host.md section 5.

## Amendment 2026-11-17: dedicated-cpu, and the setup detects and recommends

- **Batt (Thai, translated):** "If it is this specific, users cannot even start installing and
  learning, e.g. fixing the graphics card. The setup should detect the graphics card by itself and
  recommend it to the user; with no GPU, use the CPU instead." The wider decision is ADR-0026
  (any host, nothing locked).
- **A fourth profile, `dedicated-cpu`** (`scripts/host_profile.py`): a host with NO usable GPU (none,
  an AMD card, or a card whose driver or container runtime is not ready). The dedicated rules,
  accelerator `cpu`, no vision image, no vision worker, no GPU lister; the CPU detector serves alone.
  guarded_build refuses every vision step there with that reason. It closes
  second-install-gaps.md row D's "a CPU-only profile still open".
- **What the setup checks** (`scripts/gpu_ready.py`; the wizard's pre-flight and profile screen):
  only what a container cannot bring, because the GPU's kernel driver is the host's:

  | GPU | ready when | recommended | otherwise |
  |---|---|---|---|
  | NVIDIA | the driver's release >= 580 (`/proc/driver/nvidia/version`; the image is CUDA 13.0) and the NVIDIA Container Toolkit is installed (its runtime hook / `nvidia-ctk`) | `dedicated-nvidia`, build the vision image, VRAM share 1.0, the worker's memory from the RAM | `dedicated-cpu`, with the fixes (update the driver; install the toolkit + `nvidia-ctk runtime configure`) |
  | Intel | the i915/xe kernel driver is loaded and the user is in the render node's group | `dedicated-intel`, the same | `dedicated-cpu`, with the fixes; a note when the host is not Ubuntu 26.04 (the Intel image's runtime must match the host's driver) |
  | AMD | (no vision image for AMD yet) | `dedicated-cpu` | |
  | none | | `dedicated-cpu` | |

  The person may still choose the GPU profile against the recommendation; the real proof is
  later and inside the image (`scripts/check_gpu.py`).
- **The worker's memory** (`VISION_WORKER_MEM`, both worker overlays read it): the setup proposes
  the host's RAM minus 6 GiB, between 4 and 16 GiB (bot-server's 15 GiB would get 8g; the lab
  keeps its Intel overlay's 11g, Batt 2026-11-08, by leaving the key unset).
- **The detect server and the Run helper follow the profile:** the Run helper starts the profile's
  detect backend (torch on NVIDIA, OpenVINO on Intel, none on `dedicated-cpu`), and the detect
  server registers only the models whose pinned files are present in the storage folder (a new
  install has v1 only; the lab all eight). It closes second-install-gaps.md row N.
  - ⚠️ The torch backend (NVIDIA) loads each model's `.pt` checkpoint, the OpenVINO one (Intel) its
    ONNX. The teaching-kit branch publishes v1's ONNX only, so a NEW NVIDIA install has no model
    for its GPU server until it has a `.pt` (its own training, or a published v1 checkpoint): its
    detections come from the CPU detector, which runs v1's ONNX. A decision for Batt (publishing
    v1's `.pt` beside its ONNX, or an ONNX backend on CUDA) -- not decided here.
- **The starter model** for a new install: v1 (`v1.onnx` of the teaching-kit branch, the same file
  as the lab's `v1png-last-736x1280.onnx`, sha256 `32b448a1...`), installed by
  `scripts/detector_setup.py` into the CPU detector's folder and the storage folder's
  `archive/models/`.
- **Unchanged:** the three existing profiles, their rules and overlays; VM 103 stays `shared-nvidia`.
