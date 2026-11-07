---
doc_type: decision
hypothesis: null
status: ACCEPTED
role: null
verdict_date: 2026-11-07
verdict_ticket: null
supersedes: null
related: [0005-vision-x-access.md, 0018-component-licensing.md, ../planning/gpu-live-detector.md, ../planning/bot-server-migration.md]
next_action: "Intel first (bot-server's Arc A380): the OpenVINO inference backend + the torch device layer, each proven on bot-server against the CPU boxes / a real training cache. NVIDIA keeps working on ubuntu-docker; AMD is designed in and untested until a host has one."
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
