---
doc_type: design
hypothesis: "Moving our GPU work (training first, then the live detector) to the dedicated bot-server (192.168.1.228, Intel Arc A380) stops our jobs from touching the shared host's GPU (Frigate) and disk (quant capture), without moving the live loop."
status: "SURVEYED 2026-11-07 14:18-14:50 ICT (a read-only survey plus user-space test installs on bot-server). The CPU is measured; the Arc is NOT, because user `bot` lacks the render group. Recommended shape: A (GPU offload). Batt decides (section 7)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gpu-live-detector.md, endpoints-as-config.md, ../benchmarks/cpu-detector-speed.md, ../adr/0005-vision-x-access.md, ../operations/nas-sink.md]
next_action: "Batt: add `bot` to the render and video groups on bot-server (or grant agents sudo there). Then an agent runs the staged GPU test (/home/bot/survey/scripts/gpu_run.sh, ~5-10 min): OpenVINO on the Arc vs the CPU boxes, PyTorch XPU training. Its numbers decide A1 / A2."
title: "Moving the bot's GPU work to bot-server: survey and options"
date: 2026-11-07
owner: Batt
---

# Moving the bot's GPU work to bot-server (survey, 2026-11-07)

## 0. Batt's request (2026-11-07 ~14:1x ICT)
- Batt built a new Ubuntu server just for the bot (`ssh bot@192.168.1.228`). Batt's words, Thai,
  translated: "Send an agent to look at this machine first: if we move there, can we, and what must
  be prepared, so we no longer affect the GPU on this server. It has an Intel Arc GPU; check it."
- Agents may do anything on that machine, sudo included, as long as nothing affects other systems
  on the network. ~14:3x: mounting NFS from the NAS there is allowed too.
- The survey was one subagent, under the subagent brief. It installed packages in user space only
  and made no system changes (section 6). MEASURED below means measured on bot-server that day.

## 1. The machine (MEASURED; key facts re-checked by the parent at 14:5x)
| | |
|---|---|
| hardware | HP ProLiant ML350 Gen9, bare metal; 1 x Xeon E5-2609 v4, 8 cores / 8 threads, 1.7 GHz, no turbo; AVX2, no AVX-512 / VNNI |
| memory | 15 GiB (14 available idle); 4 GiB swap file |
| disk | ONE 128 GB SATA SSD (Plextor PX-128M5, ~2013): / is 122 GB, 98.4 GB free with the survey's 8.4 GiB in it (~108 GB before); 201 MB/s sequential write, ~130 synced 4 KiB writes a second |
| GPU | Intel Arc A380 (DG2, 6 GB by spec), i915 bound, GuC 70.53.0 / HuC 7.10.16 / DMC 2.8 loaded; Resizable BAR NOT available (BAR2 256 MiB, i915 asks for ReBAR); PCIe Gen3 x8; idle 16.9 W, PL1 43 W |
| network | 1 GbE up (eno1, DHCP 192.168.1.228), 3 more ports unplugged; global IPv6 addresses (SLAAC + DHCPv6) |
| OS | Ubuntu 26.04.1 LTS, kernel 7.0.0-43, Python 3.14 (3.12 via uv in the survey); no Docker; unattended-upgrades on; ufw active (rules unread without root) |
| reachability | the Windows PC (RDP port open; Sunshine ports filtered: its firewall admits only .13), the NAS (NFS port open), this host: all ~0.5-1.1 ms |

## 2. What was measured
- **CPU detection on bot-server, quiet machine** (50 real xmas_dun02 frames, our own
  `detector_worker.py`, 100 calls each, p50 / p95 ms, letterbox + forward + decode):

  | backend | v1 | xmas02 |
  |---|---|---|
  | onnxruntime, 8 threads | 122.5 / 146.3 | 126.2 / 137.1 |
  | **OpenVINO CPU, 8 threads** | **110.7 / 123.6** | **114.6 / 116.9** |
  | onnxruntime, 4 threads | 166.2 / 169.9 | 168.5 / 170.5 |

  - OpenVINO's boxes equal onnxruntime's: xmas02 137 / 137, v1 15 / 15, 0.0 px.
  - The numpy letterbox + decode is ~20-24 ms of each call, whatever does the forward.
  - The current host for comparison: 110 ms quiet at 16 threads, 194-339 ms under its usual load;
    the RTX 5060 Ti through the live socket ~50 ms (gpu-live-detector.md 6a).
- **The Arc: NOT measured.** `/dev/dri/renderD128` is `root:render 0660`, user `bot` is not in
  `render` / `video`, and sudo needs a password. OpenCL and PyTorch XPU both load the Intel runtime
  and then get EACCES on the render node. Everything else is installed and staged: OpenVINO
  2026.4.1, torch 2.15.0+xpu and ultralytics 8.4.165 (the same as the lab's) in user-space venvs,
  and the Intel compute runtime from the Ubuntu 26.04 archive extracted in user space.
- **Training scripts** are proven on the CPU: a YOLO11n forward + backward + step on random
  736 x 1280 tensors (450-466 ms an iteration at batch 1), and a 1-epoch ultralytics training run
  on synthetic images (13.9 s). Whether ultralytics trains with `device="xpu"`, and how much VRAM
  batch 4 at 1280 takes, are unknown until the Arc test runs.
- **NFS:** not tried. nfs-common is not installed and mounting needs root. The NAS exports for
  poring-lab admit only 192.168.1.13 (nas-sink.md), so a mount from .228 needs a TrueNAS change.

## 3. What the lab needs today (from the repo)
- The live loop on .13: the ONE RDP session (xfreerdp software decode, ~4.5 cores at 30 fps) or
  the S2 stream; the backend (frame bus, input mux, interlock); rathena + db with the sniffer in
  rathena's network namespace; the console; the host scripts; the detector (CPU worker in RAM, or
  the GPU detect server over a unix socket).
- Every GPU path is NVIDIA-specific today: the CUDA 13 image, compose `driver: nvidia`,
  `configure_gpu` -> `cuda:0`, `train.py`'s `torch.cuda`, `check_gpu.py`'s sm_120 check, and
  nvidia-smi in `frigate_r3.py`, guarded_build's verified stop and `gpumon.sh`. Nothing knows XPU
  or OpenVINO yet.
- Addresses: 192.168.1.13 / HOST_LAN_IP carry three roles (game server, bot server, the safety
  identity; endpoints-as-config.md, PROPOSED). On Windows, the client config, the 4 AssistAddr
  lubs, the lab-only firewall group, the watch task and Sunshine's rules all name .13; changing
  them is Batt's, from an elevated console (ADR-0019).
- Memory caps in compose sum to 12.8 GiB (15.8 with frontend-dev); what the containers really used
  at 14:4x without the vision worker: ~575 MiB.

## 4. The shapes
| | what moves | Windows | NAS | effort | verdict |
|---|---|---|---|---|---|
| **A1 (recommended first)** | training: the vision worker runs on bot-server, reading the datasets from the NAS | none | add .228 to the datasets export (read-only) + a place for outputs | small | ends R1-R3 pauses and the IO-guard pressure of OUR training on .13 |
| **A2 (later)** | the live detector: a detect server on bot-server (OpenVINO on the Arc, else its CPU), reached over the LAN | none | - | medium | the frame costs ~22-24 ms on 1 GbE (2.76 MB); needs an ADR (an off-host detect server: bot-server's firewall admits .13 only, plus a token) |
| B | the whole lab stack | every .13 item above, the Sunshine key, the Settings, a db dump / restore | exports | large, mostly Batt's | NOT on this hardware: 15 GiB RAM, a 128 GB SSD (recordings take 7-8 GB an hour against a 100 GB floor), a 1.7 GHz CPU |
| C | the game server only | as B | - | large | does not touch the GPU: misses the goal |

## 5. Prep checklist, in order
1. `bot` into the render and video groups (or agents get sudo on this agents-only box). Batt.
2. The staged Arc test (`/home/bot/survey/scripts/gpu_run.sh`, ~5-10 min): OpenVINO GPU FP32 /
   FP16 speed and parity against the CPU boxes, watts and temperature, PyTorch XPU forward +
   backward, an ultralytics `device="xpu"` probe. Agent.
3. A DHCP reservation for 192.168.1.228 on the router. Batt.
4. The Intel compute runtime installed system-wide (`intel-opencl-icd libze-intel-gpu1 libze1
   clinfo intel-gpu-tools`). Batt, or an agent with sudo.
5. NAS: .228 added to the datasets export (read-only), and where training outputs land. Batt
   approves; the TrueNAS change is Batt's. Then nfs-common and a read-only automount there.
6. Only if containers run there: BEFORE installing Docker, `/etc/docker/daemon.json` with
   `default-address-pools` and a `bip` outside 192.168/16 and 172.16/12 (the 192.168.96.0/20
   lesson on .13), then one pinned /24 per compose project.
7. A2 only: bot-server's firewall admits the detect port from .13 only.
8. The code (an XPU device path, a runner for a host that is not shared, for A2 a LAN transport
   and an OpenVINO server with the pinned ONNX and a parity gate) and its ADR. Agent; Batt
   approves.

## 6. What the survey left on bot-server
- `/home/bot/survey` (8.4 GiB): uv, Python 3.12, `venv-ov` (OpenVINO + onnxruntime, 319 MB),
  `venv-xpu` (torch XPU + ultralytics, 7.3 GB), the extracted Intel runtime, the two ONNX models,
  50 game frames from our lab server (97 MB; never commit or publish them), the scripts and the
  CPU results. Kept for step 2. Undo: `rm -rf /home/bot/survey /tmp/survey-tmp`;
  `venv-xpu` alone frees 7.3 GB.
- No apt install, no system file, no group, no network / firewall change, no Docker, no mount, no
  reboot.
- On .13: the survey's raw results are archived at
  `/mnt/poring-lab-datasets/scratch-archive/2026-11-07/bot-server/`.

## 7. Decisions for Batt
1. GPU access: `bot` into render + video, or sudo for agents on bot-server?
2. After the Arc numbers: A1 (training there)? Then A2 (the live detector over the LAN, its ADR)?
3. The NFS export for .228 and where training outputs go.
4. The DHCP reservation for .228.
5. Which of CLAUDE.md rule 5's guards apply on a host that is not shared (R1-R3 and the IO guard
   protect .13's Frigate and quant capture; the NAS stays shared).
6. Shape B only with more RAM, a bigger disk and a faster CPU: wanted, and when?
7. A `pci=realloc` trial for Resizable BAR (a bootloader change and a reboot of bot-server).
