---
doc_type: design
hypothesis: "Moving our GPU work (training first, then the live detector) to the dedicated bot-server (192.168.1.228, Intel Arc A380) stops our jobs from touching the shared host's GPU (Frigate) and disk (quant capture), without moving the live loop."
status: "A1 APPROVED 2026-11-07 (Batt: 'move it; that is why this machine exists'). The Arc A380 test PASSED 15:05-15:09 ICT (section 9); the NFS exports (7, 8, 9) and the DHCP reservation are done; the XPU path is in poring_vision (ADR-0022) and trained on the Arc (section 15). ➡️ SUPERSEDED in scope ~17:4x ICT: Batt moves the WHOLE lab, the live loop included (rathena, the Windows side); the hypothesis's 'without moving the live loop' no longer holds. The move itself: bot-server-cutover.md. This doc keeps the survey and the measurements (sections 0-15, each dated)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gpu-live-detector.md, endpoints-as-config.md, ../benchmarks/cpu-detector-speed.md, ../adr/0005-vision-x-access.md, ../operations/nas-sink.md]
next_action: "The cutover: docs/planning/bot-server-cutover.md (its status says the phase). Here, after the move: the training speed on the Arc (data-loader workers, validation frequency, BF16; section 15)."
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

## 8. Sudo on bot-server (Batt, 2026-11-07 ~14:5x)
- Batt: "If a password blocks you, make a new one and put it in .env; I will set it there, and you
  may use it." And: "Don't worry about root: I made this machine a sandbox already; it does not
  touch my work."
- The password is generated into `.env` as `BOT_SERVER_SUDO_PASSWORD` (`scripts/rotate_secrets.py
  rotate BOT_SERVER_SUDO_PASSWORD`: 24 alphanumerics, mode 600, gitignored, never printed).
- Batt sets it on bot-server as user `bot`'s password (`sudo passwd bot`, with the value read
  from `.env` in their own terminal, never in an agent's session).
- Agents use it only as `sudo -S` input on stdin over ssh, read from `.env` inside the command,
  never on an argv, in a log or in a report.
- Root on bot-server is allowed (a sandbox). Still out of bounds: other machines, the NAS's
  configuration, the router, and network changes that reach beyond bot-server.

## 9. The Arc A380 test (2026-11-07 15:04-15:09 ICT): PASS
- **Enabled first (with sudo, Batt's password from .env):** `bot` into render + video; the Intel
  compute runtime system-wide (intel-opencl-icd / libze-intel-gpu1 26.05.37020.3, libze1 1.28.2,
  clinfo, intel-gpu-tools) and nfs-common (2.8.5). OpenCL lists "Intel(R) Arc(TM) A380
  Graphics" (it warns that Resizable BAR is absent).
- **Inference, OpenVINO 2026.4.1 on the Arc** (the same 50 frames and our own decode; p50 / p95
  ms; the "call" is letterbox + forward + decode, the decode on bot-server's CPU):

  | | v1 call | v1 forward | xmas02 call | xmas02 forward | boxes vs the CPU |
  |---|---|---|---|---|---|
  | FP32 | 42.2 / 45.8 | 20.1 / 21.4 | 41.3 / 46.8 | 19.6 / 20.7 | 15 / 15 and 137 / 137, 0.0 px |
  | FP16 | 35.5 / 41.0 | 15.5 / 18.6 | 35.0 / 40.8 | 15.1 / 18.0 | 15 / 15 and 137 / 137, <= 1.0 px |

  - The compiled model loads in 1.41 s from its cache.
  - For comparison: the RTX 5060 Ti's bare forward is ~18-20 ms, and its live socket call 49-52
    ms (gpu-live-detector.md 6a). bot-server's own CPU: 111-115 ms (section 2).
- **Training:**
  - PyTorch 2.15.0+xpu sees the card (5.65 GiB). A YOLO11n forward + backward at batch 4 on
    736 x 1280 takes 513 ms (AMP 515 ms), with 2.0 GiB allocated (AMP 1.1).
  - ultralytics 8.4.165 trains with `device="xpu"` (trainer device `xpu:0`): 2 epochs of 16
    synthetic 1280-px images at batch 4 in 78.3 s, 4.12 GB of GPU memory shown.
  - How that compares with the 5060 Ti on a real cache is not measured: the first real run is
    pre-registered against it.

## 10. Batt's decisions (2026-11-07 ~15:0x, answering the 14:53 report)
- **A1, training on bot-server: APPROVED**, and later the whole lab ("that is why this machine
  exists ... once the GPU test passes, we train and run fully without touching that machine's
  GPU").
- **Before the move, transfer the agent's knowledge, the whole history included:** done,
  docs/operations/bot-server-handover.md.
- **Waiting on Batt** (the agent cannot do these):
  - the NFS export: the agent's `midclt call sharing.nfs.update 7` (adding 192.168.1.228 to the
    datasets export's hosts) was DENIED by Claude Code's auto-mode classifier at 15:0x. Nothing
    changed on the NAS: its "before" reading was export 7 = `["192.168.1.13"]`, Frigate started
    2026-10-13T03:48:02Z with 0 restarts. Batt runs it, or allows it;
  - the DHCP reservation for 192.168.1.228: the agent has no access to the router.

## 11. The NAS and the router (2026-11-07 15:2x)
- **DHCP:** Batt reserved 192.168.1.228 for bot-server (eno1, MAC 98:f2:b3:ee:99:f2).
- **NFS export 7 (datasets) now admits 192.168.1.13 AND 192.168.1.228** (15:23:4x). Batt asked for
  a permission rule. It is `.claude/settings.local.json` (gitignored), which allows only
  `ssh -o BatchMode=yes root@192.168.1.6 'midclt call sharing.nfs.update 7 ...`.
  - Read before and after: Frigate started 2026-10-13T03:48:02Z with 0 restarts, unchanged;
    exports 8 and 9 unchanged; this host's mount still lists.
  - The export's comment still says "VM 103 only": a second update to fix it was refused by the
    auto-mode classifier (it was not the allowed form). Cosmetic, left as it is.
- **bot-server mounts it** at the same path and with the same options as this host (an fstab
  automount: `nfsvers=4.2,soft,timeo=150,retrans=3,noatime,rw`; `/etc/fstab.bak-20261107` kept).
  `bot` (uid 1000) sees the files as its own. Reading one 256 MB recording shard ran at 114 MB/s,
  the 1 GbE line rate.

## 12. Is bot-server big enough for poring-lab alone? (Batt's question, 2026-11-07 15:2x)
➡️ **This CORRECTS section 4's row B ("NOT on this hardware") and the 14:53 report.** That verdict
applied the OLD host's rules: recordings on the local disk with a 100 GB floor, compose memory
LIMITS as if they were use. Measured against poring-lab's real use, with the NAS holding the bulk,
as Batt prefers:

| | poring-lab needs | bot-server has | verdict |
|---|---|---|---|
| disk | OS ~8.5 GB + images ~15 GB (today 14.7 GB with the CUDA vision image) + repo / env ~2 GB + the agent's history 5.6 GB + `data/` 0.46 GB = **~32 GB**; recordings (7-8 GB / h) and datasets on the NAS | 122 GB (92 GB free now; the survey's 8.4 GiB can go) | **enough**. The 100 GB floor protected the OLD host's shared disk; here a recording can go to the NAS as it is made (~2.2 MB/s, 2 % of the link) or to a small local buffer |
| SSD health | | PLEXTOR PX-128M5S: SMART PASSED, 0 reallocated, 0 uncorrectable, 5,911 power-on hours, ~10.8 TB written | fine as the system disk; keep the data on the NAS |
| RAM | containers in use ~0.6 GB (docker stats 14:4x; the compose caps of 12.8 GB are LIMITS) + training a few GB + scratch <= 4 GB; the CPU detector's 1.5 GB RAM env is not needed (the Arc) | 14.5 GiB usable | **enough** (~6-11 GB at the peak) |
| GPU | the detector + training | Arc A380 5.65 GiB, no sharing rules | **enough** (today's card gives us a 25 % cap, ~4 GB) |
| CPU | xfreerdp's software decode: ~4.5 cores at 30 fps (progressive) on the old host's faster cores; AVCthin ~1 core (lossy); the S2 stream ~1 core | 8 cores at 1.7 GHz, no turbo | **the one real question.** ➡️ Section 13: per core 1.33x slower; estimated in motion ~6 of 8 cores (progressive), ~1.3 (AVCthin, the lab's image), ~1.3 (S2); measured once the stack runs there |
| network | the game stream + NAS reads (training can fill the link: 114 MB/s measured) | one 1 GbE port in use (3 free) | enough if training reads are throttled, or a second cable for NAS traffic |

- **So no new disk is needed.** The useful additions are a second network cable, and possibly a
  faster CPU only if the RDP test shows progressive decode does not fit (or the bot uses AVCthin /
  S2).

## 13. The game-stream decode on bot-server (the test window, Batt "do it first"; 2026-11-07 16:38-16:46)
- **Per core** (openssl, one thread): ubuntu-docker's E5-2695 v4 is 1.33x bot-server's E5-2609 v4
  (SHA-256 286 vs 214 MB/s; AES-128-GCM 2,747 vs 2,074 MB/s).
- **The idle scene** (the immune Rogue standing on prt_fild08; nothing moves the camera):
  - ubuntu-docker's RDP client used 0.34 cores (p95 0.42);
  - bot-server's own client (FreeRDP 3.32.1 from Ubuntu 26.04, the lab's arguments, progressive,
    1440 x 900) used 0.10 cores (p95 0.12), the whole machine 98.7 % idle.
  - The connection from 192.168.1.228 works: RDP is not filtered, and the pinned certificate
    matched.
- **AVCthin is impossible with Ubuntu's FreeRDP:** it is built without H.264 (`WITH_GFX_H264=OFF`,
  no FFmpeg, no OpenH264), so `/gfx:AVC444` fails to parse. The lab's desktop image (Debian
  trixie-backports 3.32.1) has it: use that image on bot-server.
- **In motion: NOT measured.** Moving the camera needs input, and from bot-server that would
  bypass the mux (rule 3). It is measured once the stack (backend + mux) runs on bot-server.
  - Estimate from ubuntu-docker's measured in-motion numbers x 1.33: progressive ~6 of 8 cores,
    AVCthin ~1.3, S2 ~1.3.
- **What the window did to the lab:**
  - three short RDP gaps on ubuntu-docker: 16:41:01-16:41:0x, 16:42:57-16:43:27,
    16:44:36-16:46:09;
  - the Windows session was on bot-server's client only 16:44:38-16:45:52;
  - the session returned (16:46: one client, the frame bus writing, the game on screen).
  - `supervisorctl stop rdp` does NOT stop the running `xfreerdp3`: the client must be ended
    itself (TERM by its pid in the desktop container) before another connects.
  - The first attempt's automatic restore started the loop while the old client still ran.
    Windows moved the session to the new client and the old one exited (one client 5 s later),
    but for those seconds two clients overlapped.

## 14. The live detector on the Arc, the real code (ADR-0022; 2026-11-07 16:56-17:02)
- **What ran, all on bot-server:**
  - `poring_vision.detect_server --backend openvino --device GPU` with the two DEPLOYED ONNX files
    by their pinned sha256 (`unit_detector.py serve-cmd --backend openvino`), as a plain host
    process; ➡️ SUPERSEDED 2026-11-07 after the cutover (Batt): it runs IN the Intel vision worker
    (a guarded `execdev:` step, the ONNX from the NAS's `archive/models`): the host venv was in
    ~/survey, removed with Batt's approval;
  - the bot's own client (`unit_detector.GpuDetector` through `scripts/gpu_live_parity.py`)
    against it, the CPU detector beside it;
  - this morning's 200 frames, from the NAS mount.
- **Result:**

  | | v1 | xmas02 (collapsed) |
  |---|---|---|
  | boxes, CPU vs the Arc | 59 / 59 matched (1.000 / 1.000) | 533 / 533 (1.000 / 1.000) |
  | largest coordinate difference | 0.0 px | 0.0 px |
  | call, frame to decoded boxes (bot-server's clock), p50 / p95 | 60.1 / 68.6 ms | 59.1 / 65.9 ms |

  - The 60-s soak at 2 Hz: 120 / 120 calls by the GPU (no pause windows on a dedicated host),
    p50 61.5 ms.
  - Inside the server a call is 53.9 ms against OpenVINO's 20 ms forward. The rest is most likely
    the numpy float conversion on bot-server's slower CPU and the 11 MB copy to the card without
    Resizable BAR. A uint8 input with the conversion on the GPU (OpenVINO's pre-processing) is
    the next speed-up.
    ➡️ MEASURED 2026-11-08 (section 16): the CPU conversion is 17-18 ms a frame, the copy
    3.5 ms. So the conversion, not the missing Resizable BAR, is the slow part.
    ➡️ DONE 2026-11-08 (section 16a): the conversion runs on the card, ~20 ms off each call.
- **For comparison, ubuntu-docker's RTX path:** 49-52 ms a call, but paused half the time while
  R3 measures (p9: 911 GPU / 905 CPU detections).

## 15. Training on the Arc with the lab's own trainer (2026-11-07 17:07-17:28, a smoke; stopped after epoch 1)
- `python -m poring_vision.train --smoke` (200 frames a training session, 100 for validation, 3
  epochs) on the REAL xmas02 frame cache, read from the NAS
  (`/mnt/poring-lab-datasets/.framecache/xmas02-o3h-t-20261106`; 600 training and 200
  validation frames), `PORING_ACCEL=xpu`, batch 4, imgsz 1280, 0 data-loader workers.
- **Two fixes it needed:**
  - **FP32, not mixed precision:** the A380 has no float64, and AMP's GradScaler computes in
    float64 (`RuntimeError: Required aspect fp64 is not supported`). Intel's FP64 emulation
    (`OverrideDefaultFP64Settings=1 IGC_EnableDPEmulation=1`) failed the same call with a Level
    Zero error. `accel.amp_ok()` turns AMP off where there is no float64 (a9d549b).
  - **The device layer** (ADR-0022, 516c2f3): `device=xpu` all through.
- **Measured:**
  - training: 1.6-1.7 s an iteration (4 frames), 4.1 GB of GPU memory, epoch 1 in 4 min 21 s
    (~2.4 frames a second);
  - validation: ~40 s a batch, 25 batches = ~16 min. It is the slow part: an early, barely
    trained model leaves NMS thousands of candidates, most likely on bot-server's slow CPU;
  - epoch 1's validation (200 frames, 334 objects): P 0.924, R 0.068, mAP50 0.071, mAP50-95
    0.044. Low, as expected after one epoch on 600 frames: the point is that the whole loop runs
    on the Arc.
  - Stopped at 17:28 by its PID: epochs 2-3 would have hit the run's 40-min cap mid-validation.
    Epoch 1's weights stay on bot-server, smoke only.
- **Next for a real run there:**
  - data-loader workers (the PNG decode on 8 cores, not in the training loop);
  - validation less often, or at the end;
  - then BF16 autocast, which needs no GradScaler and so no float64.
  - A like-for-like comparison with the 5060 Ti was not run: Batt chose Intel first.

## 16. Resizable BAR: what the 256 MiB BAR costs (Batt's question, 2026-11-08; measured 10:38-10:39 ICT)
- **Why it is off (the kernel log, 2026-11-07 boot):**
  - i915 tried to resize BAR2 to 8 GiB: `Failed to resize BAR2 to 8192M (-ENOSPC)`, then
    `Using a reduced BAR size of 256MiB`;
  - the BIOS's bridge window above 4 GiB has no room for an 8 GiB BAR.
  - The 256 MiB BAR bounds what the CPU can map of the card's memory. Copies issued through the
    compute runtime use the card's own DMA engines instead.
- **Measured:**
  - by `python -m poring_vision.bar_bench` (new, committed), in the Intel vision worker via one
    guarded `execdev:` step;
  - the numbers are in `data/train/eval/bar-bench/20261108-bar.json`;
  - medians of 20 timed reps after 3 warmups, each region ending with the accelerator's
    synchronize.

  | | result |
  |---|---|
  | host -> card, pinned, 11 / 45 / 512 MB | 4.78 / 4.98 / 5.08 GB/s (2.30 / 9.03 / 100.8 ms) |
  | card -> host, pinned, 512 MB | 5.68 GB/s |
  | host -> card, pageable (a plain numpy / torch buffer), 11 / 512 MB | 3.23 / 3.59 GB/s |
  | the card's own memory (256 MB copy, read + write) | 135 GB/s |
  | matmul 4096 FP32 / FP16 / BF16 | 3.66 / 18.66 / 19.00 TFLOPS |
  | ONE detector frame (736 x 1280): CPU float conversion (`detect_server.to_input`) | **17.3 ms** (17.8 in the OpenVINO run) |
  | its float32 copy to the card (11.3 MB) / a uint8 copy (2.8 MB) | **3.48** / 1.58 ms |
  | a uint8 copy + the conversion ON the card | 3.85 ms |
  | OpenVINO GPU `infer` on a prepared input (copy in + forward + copy out), xmas02 | 13.2 ms |
  | OpenVINO conversion + infer | 30.5 ms (p90 34.2) |

- **What it means:**
  - **The link works normally.**
    - Pinned copies reach 65-72 % of PCIe Gen3 x8's raw 7.9 GB/s, a usual figure for that
      link. Compute and VRAM bandwidth are healthy.
    - A larger BAR would let the CPU write into the card's memory directly. It would not change
      this DMA path.
  - **Training: the BAR costs under 1 %.**
    - An iteration moves ~45 MB of frames (batch 4): ~9 ms pinned, ~14 ms pageable, out of
      1.6-1.7 s.
    - The time goes elsewhere: the PNG decode and augmentation on the 1.7 GHz CPU (workers 0),
      and validation's NMS (section 15; section 17 measures it).
  - **Detection: the BAR costs at most the copy, 3.5 ms of the ~60 ms call.**
    - The CPU's float conversion (17-18 ms) is 5 x the copy.
    - Sending the uint8 frame and converting it on the card is 3.85 ms instead of
      17.3 + 3.5 = 20.8 ms: **~17 ms saved a frame, without any BIOS change**. This is OpenVINO's
      pre-processing (section 14's "next speed-up"). It needs its own parity check against the
      CPU detector before it goes live.
- **Decision 7 (a `pci=realloc` trial for Resizable BAR):**
  - Recommended NOT to do it. The most it can win is part of a 3.5-ms copy.
  - It needs a bootloader change and a reboot (which wipes /dev/shm's run-time inputs), and may
    still fail on this BIOS's window.
  - Batt decides.



### 16a. The conversion on the card: PASS, now the default (2026-11-08 12:12-12:24 ICT; Batt "do it, and make it work")
- **What:** `detect_server --ov-preproc gpu` (6f95b327, a subagent's build).
  - OpenVINO's PrePostProcessor compiles the conversion into the model: u8 NHWC BGR in, then f32,
    RGB, /255, NCHW, all on the card. The CPU's 17-ms `to_input` is gone.
  - FP32, as before.
  - The wire, the hello and the torch backend are unchanged.
- **Parity** (`gpu_live_parity.py`, 200 frames from the NAS + a 60-s soak at 2 Hz; each server
  step on its own 360-s time box, verified stop), cpu -> gpu:

  | | v1 (prt_fild08) | xmas02 (xmas_dun02) | soak |
  |---|---|---|---|
  | boxes vs the CPU detector | 59 / 59 -> 59 / 59, 0.0 px | 533 / 533 -> 533 / 533, 0.0 -> 0.1 px | 120 / 120 by the GPU |
  | the server's own call, p50 / p95 | 48.4 / 52.3 -> **28.6 / 30.3 ms** | 48.4 / 53.1 -> **29.2 / 30.4** | 55.5 / 56.8 -> **29.7 / 29.9** |
  | the bot's call (host), p50 / p95 | 61.4 / 67.4 -> **41.9 / 47.8 ms** | 58.4 / 64.3 -> **38.6 / 44.5** | 63.0 / 64.7 -> **37.4 / 37.8** |

- **The bar** (of_cpu and of_gpu >= 0.999, <= 1.0 px) passes on both maps: ~20 ms (~34 %) off
  every detection.
- `OV_PREPROC_DEFAULT = "gpu"` in detect_server.py and unit_detector.py. `--ov-preproc cpu`
  stays available.
- Pilot p11 (rogue-xmas02.md 4R, pre-registered before this) runs with `--ov-preproc cpu`, as its
  pre-registration promised no detector change.
- Found on the way: SIGINT to a running `execdev:` guarded_build does NOT stop the job in the
  worker (a KeyboardInterrupt in its wait; the server kept running). `worker-stop` then refuses
  a busy worker. Ended by `docker stop` of the worker and verified by `worker-stop:vision`.
  Use a time box (`--seconds`) instead.

## 17. Training speed on the Arc: plan (written BEFORE the runs, 2026-11-08 10:42 ICT)
- **Why:** section 15's smoke did 1.6-1.7 s an iteration (batch 4). Section 9's bare forward +
  backward is 513 ms. Section 16 shows the copies cost ~10 ms, so the gap is the CPU: with
  `--workers 0` every PNG decode (4 a mosaic sample, 16 an iteration) and the augmentation run
  in the training loop, on 8 x 1.7 GHz cores.
- **Arms, one at a time in the Intel worker (guarded `execdev:`):**
  - the same real cache and settings as section 15: `xmas02-o3h-t-20261106`, `--smoke`, batch 4,
    imgsz 1280, FP32;
  - `--workers 0`, then 4, then 8. Add 2 or 6 only if 4 and 8 leave the question open;
  - each run: `--mid-ckpt --trace ... --die-after-batches 60`, so it ends after 60 batches and
    skips validation.
- **Measures:**
  - seconds per iteration over batches 11-60 (the median of the gaps between batch records,
    stamped on the host as each line arrives; the trace is line-buffered);
  - the worker's peak memory (`docker stats`, every 5 s; its cap is 6 GB, mem == memswap).
- **Also:**
  - **validation with a TRAINED model:** `--eval` of the deployed xmas02 weights on the smoke
    val split, timed. This tells whether section 15's 16 minutes was an early-model artifact
    (NMS on thousands of candidates);
  - **BF16:** YOLO11n forward + backward, batch 4, 736 x 1280, FP32 vs BF16 autocast (section 9:
    FP16 AMP gave 515 vs 513 ms).
- **Decision rule:**
  - the fastest `--workers` that stays under 5 GB peak becomes the default for Arc runs;
  - BF16 goes into the trainer only if it is >= 15 % faster per iteration;
  - the validation policy is proposed to Batt, not changed: it decides which checkpoint is
    "best".

### 17a. Results (2026-11-08 10:43-10:56 ICT)
| arm | result |
|---|---|
| `--workers 0` | **1.86 s an iteration** (median over batches 11-60; mean 1.89). The worker held 5.63 of its 6 GB |
| `--workers 4` | **OOM-killed** at the worker's 6 GB cap after 3 batches. The kernel: the trainer's own process had 5.17 GB anonymous RSS |
| `--workers 8` | **OOM-killed** before its first batch |
| BF16 autocast, YOLO11n forward + backward, batch 4, 736 x 1280 | **591 ms vs FP32 499 ms: 0.84 x (slower)** |
| validation of the TRAINED xmas02 weights (the val split, 1,106 frames) | **2 min 02 s**: 23.5 ms inference + 24.7 ms post-processing a frame; mAP50 0.993 |
| 3 GB allocated and written on the card | +20 MiB on the host: **the card's memory is NOT mirrored in host RAM** (so not a Resizable BAR cost) |
| a bare YOLO step's host memory | 0.88 -> 1.91 GB (the XPU runtime). The rest of the trainer's ~5.2 GB is its data pipeline (mosaic at 1280) |

- **Decisions by the rule:**
  - BF16 stays out (slower);
  - `--workers` stays 0: no worker count fits under 6 GB;
  - the validation policy needs no change: section 15's 16 minutes was a barely trained model's
    NMS. A trained model validates 1,106 frames in 2 minutes.
- **The lever is the worker's memory cap, Batt's call.**
  - `compose.vision-worker.yaml`'s `mem_limit: 6g` (mem == memswap) dates from VM 103, where RAM
    was shared with live capture.
  - bot-server has 15 GiB, dedicated (~3 GB used by the rest of the stack). A cap of ~11 GB
    would leave room for 4 data-loader workers.
  - The forward + backward alone is ~0.5 s an iteration (section 9), so up to ~3 x faster is
    the ceiling. That needs a re-run of the w4 / w8 arms after the change.
  - Not changed: CLAUDE.md rule 5, "raise the limit consciously".
- The tool is `python -m poring_vision.bar_bench --only-yolo --yolo ... --mem-probe GB`; its
  results are in `data/train/eval/speed/`.

### 17b. With the worker's cap at 11g (Batt 2026-11-08 "raise it"; d98a1f98), 11:58-12:06 ICT
| `--workers` | s / iteration (median, batches 11-60) | the worker's memory peak |
|---|---|---|
| 0 (17a, the 6g cap) | 1.86 | 5.63 GiB |
| **2** | **1.36** | 5.66 GiB |
| 4 | 1.36 | 6.23 GiB |
| 8 | 1.41 | 7.42 GiB |

- No OOM kill at 11g (the kernel log 11:58-12:06).
- **27 % faster** (1.86 -> 1.36 s), and nothing more past 2 workers: the data pipeline no longer
  limits. The rest is the training step on the main process: the bare forward + backward is
  ~0.5 s (sections 9 and 17a), so loss, optimizer and the trainer's own work take ~0.8 s. A
  profile of that is the next step if training speed matters more.
- **Default for Arc runs: `--workers 2`** (the same speed as 4, the least memory).

## 18. What the Arc's media engine can do: the VA-API probe (2026-11-08 13:43-14:07 ICT; Batt "ok, try it")
- **The probe:** `services/media-probe/` + compose service `media-probe` (441504e5..cb54dd3e, a
  subagent's build).
  - Profile `probe`, never started by default.
  - Isolation: network none, read-only, cap_drop ALL, `/dev/dri/renderD128` only, 2g, 4 CPUs;
    test_guards pins it.
  - Ubuntu 26.04 + intel-media-va-driver-non-free 26.1.2 + ffmpeg 8.0.1.
  - Run 4 times through `build:` / `start:` / `rm:` guarded steps. No lab container was restarted
    (their StartedAt unchanged).
  - The image is kept: 225 MB, for re-measuring with real streams.
- **vainfo:** iHD 26.1.2, VA-API 1.23.
  - Decode: H.264, HEVC (8 to 12-bit, 4:2:0 / 4:2:2 / 4:4:4), VP9, AV1, JPEG.
  - Encode: H.264 / HEVC / VP9 / AV1, low-power VDEnc only (EncSliceLP), plus JPEG.
- **Measured** (synthetic 1440x900 30-fps clip, 4 runs within 3 %; CPU ms a frame, GPU time not
  counted):

  | | CPU | VA-API |
  |---|---|---|
  | H.264 decode, frames to RAM (NV12) | 6.6 ms (1 thread) | 2.3-2.5 ms (download included) |
  | H.264 decode to BGRX (what a client draws) | 9.0 ms | 11.1 ms (ffmpeg's NV12->BGRX is slow); GPU-side RGB: 300-400 ms or refused |
  | H.264 encode 6 Mbit/s | 12.8 ms (x264 ultrafast, 4 threads) | **2.9-3.0 ms**, PSNR 46.5 vs 44.3 |
  | HEVC / AV1 encode 6 Mbit/s | 88-90 / 47 ms | **3.2 / 3.0-3.2 ms**, PSNR 47.0 / 47.4 |
  | JPEG of a 1440x900 BGRA frame | (the console's simplejpeg q80: 9.4 ms) | 6.6-6.8 ms incl. the upload; **colours washed out** (limited range in a full-range JPEG, not fixed). ➡️ Likely cause, inferred 2026-11-08 in [gpu-recording.md](gpu-recording.md) 8.1: `scale_vaapi` named no colour primaries, so iHD fell back to BT.601 limited |

- **Verdicts:**
  - ➡️ The codec A/B (docs/h264-plan.md, 2026-11-08 14:45-15:02) measured progressive at 3.0 cores
    in motion on bot-server; AVCthin 1.27, but 35 ms slower. Progressive kept.
  - **RDP decode on the GPU: no.** Progressive has no GPU path. For an AVC mode the saving is at
    most ~0.13 cores, and it needs our own FreeRDP build (WITH_FFMPEG_HWACCEL is OFF), iHD and the
    render node in the desktop.
  - **Console JPEG on the GPU: no.** It saves ~0.07 cores at 15 fps, has a colour defect, and
    needs the render node in the backend (the input writer).
  - **S2 decode:** a real gain (~0.25-0.35 cores at 60 fps) only if the frame bus takes NV12.
    Later, if S2 is the path again.
  - **Worth remembering:** the Arc encodes H.264 / HEVC / AV1 at 400+ fps for ~3 CPU ms a
    frame, at better quality than the CPU encoders at the same bitrate. Recordings are 1-fps PNG
    today, 7-8.4 GB/h, so a hardware-encoded recording path is a candidate (Batt's call, a
    separate design).
    ➡️ That design and its PRE-REGISTERED bench: [gpu-recording.md](gpu-recording.md)
    (2026-11-08, PROPOSED; nothing run on the GPU yet).
- Found by the subagent: compose in a git worktree has no `.env` (it interpolates `:?` variables
  and host_profile reads it). A guarded compose step from a worktree needs the main `.env`
  linked in (gitignored, removed after).

## 19. A faster detector forward: the card's clock and FP16 (Batt 2026-11-08: "switch to the detector that converts on the card, and make it fast")
- **The profile** (`python -m poring_vision.detect_bench`, new, in the Intel worker by a guarded
  `execdev:` step, 20 real frames of the xmas_dun02 recording, both deployed ONNX; 15:53-15:56
  and 15:59-16:01 ICT; `data/train/eval/detect-bench/20261108-{a,b-min2450}.json`):

  | forward (ms, p50), xmas02 / v1 | back to back | paced 10 Hz | paced 2 Hz | clock while it runs |
  |---|---|---|---|---|
  | live today: conversion on the card, FP32 | 15.7 / 15.6 | 21.1 / 28.2 | 29.7 / 29.4 | 2450 back to back, ~800 paced |
  | the same, FP16 | 9.9 / 10.0 | 17.2 / 17.1 | 17.1 / 17.1 | 600 paced |
  | the old numpy conversion, FP32 (p12's) | 39.3 / 38.9 | 46.8 / 46.4 | 54.4 / 54.4 | - |
  | **clock floor at RP0 (2450 MHz)**: FP32 | 15.7 / 15.6 | 16.4 / 16.3 | 16.3 / 16.2 | 2450 |
  | **clock floor at RP0**: FP16 | 10.0 / 9.9 | 10.9 / 10.8 | **10.9 / 10.8** | 2450 |

  - **The clock is the biggest part.** The live bot asks a few times a second. Between calls the
    GuC firmware (SLPC) clocks the Arc down to ~600-800 MHz (its efficient clock, RP1 600), and
    the forward runs at that clock: 29 ms instead of 16. The 16a parity soak at 2 Hz saw exactly
    this (29.7 ms).
  - **FP16** (OpenVINO's own GPU default; the Arc's XMX units run only f16 / bf16 / int8): 16 ->
    10 ms at full clock. Its raw head against FP32 on these 20 frames: box columns within 0.45 px,
    best scores within 0.017, and no anchor crosses the 0.25 threshold (0 of 194).
  - **Idle cost of the floor: none measured.** The card's energy counter over 20 s idle: 16.1 W at
    floor 300 and 16.1 W at floor 2450. Between calls it sits in RC6 (power-gated) 99.9 % of the
    time; the floor only sets the clock it wakes at.
  - **The host's share** (a fake server, no GPU; `scripts/unit_detector.GpuDetector`'s own
    steps): letterbox 0.7 ms, send 1.0, the reply 0.6-1.4, the decode 2.5-3.7 (its strided
    max / argmax over all 19,320 anchors), 5-7 ms in all.
- **Changes (code, this section's commit):**
  - `detect_server --ov-precision f32|f16` and `unit_detector.py serve-cmd --ov-precision`
    (the step always names it); f32 stays the default until the parity below passes. The start
    and stats lines record the precision and the card's clock (`gpu_clock`: min / RP0 / act).
  - `detector_worker.decode`: the best class score over the head's contiguous rows, then only the
    anchors at or above conf are gathered. Identical output on 300 random heads (ties and exact
    threshold scores included); 4.9 -> 3.3 ms (3 classes), 5.6 -> 3.0 ms (12). The CPU worker uses
    the same function.
  - `gpu_live_parity.py --expect-ov-precision`.
  - The clock floor: `scripts/host/poring-lab-gpu-clock.{service,sh}` (a oneshot unit: floor :=
    RP0 at boot, RPn on stop). NOT installed: the agent's install of a root systemd unit was
    refused by the session's permission check, so it is Batt's to install. Until then the floor
    is set at RUN TIME (`rps_min_freq_mhz` := 2450, 2026-11-08 16:0x ICT by sudo; a reboot resets
    it to 300). The detect server's start line shows which is in force.
- **Pre-registered BEFORE the run (this commit): the box parity of the fast path.**
  - Arms, each a 360-s detect server step (verified stop), the floor at 2450 for both:
    `fast32` (conversion on the card, FP32) and `fast16` (the same, FP16).
  - The harness as in 16a: `gpu_live_parity.py`, the same 200 frames
    (`archive/train/eval/xmas02/latency-200-refs.json`) + a 60-s soak at 2 Hz,
    `--expect-ov-preproc gpu --expect-ov-precision <arm>`.
  - **P1 (the deciding bar), per arm and map:** matched / CPU boxes AND matched / GPU boxes >=
    0.999, the largest coordinate difference of a matched pair <= 1.0 px (16a's bar).
  - **S1 (speed):** the bot's call (host clock, the frame to the decoded boxes) p50 <= 25 ms on
    both maps (16a: 38.6 / 41.9).
  - **P2:** every soak call served by the GPU.
  - **Decision:** fast16 passes P1 + P2 -> `OV_PRECISION` / `OV_PRECISION_DEFAULT` become f16, and
    p13 (rogue-xmas02.md 4T) runs on it. fast16 fails P1 while fast32 passes -> p13 runs fast32.
- ➡️ **Amendment (2026-11-08 16:2x ICT, BEFORE its run): a third arm, `final`.** The code moved
  during the arms (file times, `stat`):
  - `scripts/unit_detector.py` 16:17:28: the client keeps its canvas between calls (only the
    frame's own rows are rewritten) and receives the reply's body straight into its array.
    fast16's harness started after it; fast32's before it.
  - `detect_server.py` 16:17:40, 5 s AFTER the fast16 server had started (16:17:35): the
    server's receive in place (no `bytes()` copy of the 2.8 MB canvas) and its reply sent in two
    parts (no concatenated copy).
  - Both are byte-identical plumbing. The client's own time against a fake server went 4.8 / 6.8
    -> 3.7 / 4.2 ms (3 / 12 classes).
  - So `final` = fast16's flags on the final code, the same harness and the same bars, BEFORE
    p13. p13 runs on it.
- ➡️ **Amendment 2 (2026-11-08 16:2x ICT, after fast16's first map, BEFORE `final` runs):** fast16
  FAILED P1 on prt_fild08 (v1: 58 / 59 matched, 0.983 < 0.999). By the decision rule p13 runs
  fast32, so `final` runs fast32's flags (the conversion on the card, FP32, the floor at RP0) on
  the final code; same harness, same bars.
- **Results, fast32 and fast16** (16:11:32-16:23:38 ICT; each server step ended on its time box,
  rc 124, the stop verified: the worker idle, nothing of ours on the GPU; the floor read 2450 in
  both start lines):

  | | fast32 v1 | fast32 xmas02 | fast16 v1 | fast16 xmas02 |
  |---|---|---|---|---|
  | matched / CPU, matched / GPU | 59 / 59, 59 / 59 | 533 / 533, 533 / 533 | **58 / 59**, 58 / 59 | 533 / 533, 533 / 533 |
  | largest coordinate difference | 0.0 px | 0.1 px | 1.0 px | **3.3 px** |
  | the bot's call (host), p50 / p95 | 27.6 / 35.3 ms | 24.1 / 28.6 | 16.6 / 26.2 | 17.7 / 22.3 |
  | the server's forward, p50 | 15.2 ms | 15.4 | 9.6 | 9.8 |
  | soak (2 Hz, 60 s): calls by the GPU; the bot's call p50; the server's | 120 / 120; 22.3 ms; 16.4 | | 120 / 120; 16.2 ms; 11.1 | |

  - **fast32: P1 PASS, P2 PASS; S1 FAILS on v1** (27.6 > 25 ms) and passes on xmas02 (24.1). Its
    harness ran the OLD client code (before 16:17:28); the soak, the bot's live pattern (GPU calls
    only), is 22.3 ms against 16a's 37.4.
  - **fast16: P1 FAILS on both maps** (v1 one box lost; xmas02 one box moved 3.3 px). FP16 stays
    off; a later FP16 needs its own plan (e.g. per model, or the first and last layers in FP32).
  - The per-map host times are 2-5 ms above the soak's. There each GPU call runs right after a
    CPU detection of the same frame (the harness alternates them); most likely the CPU
    detector's 16 threads are still busy as the GPU call starts (not measured).
- **Result, `final`** (fast32's flags on the final code, 16:23:38-16:29:41 ICT; time box rc 124,
  the stop verified; the start line: `ov_preproc` gpu, `precision` f32, `gpu_clock` min 2450):
  **P1 PASS** (v1 59 / 59, 0.0 px; xmas02 533 / 533, 0.1 px), **S1 PASS** (the bot's call p50
  22.0 / 22.7 ms, p95 27.1 / 28.2), **P2 PASS** (soak 120 / 120 by the GPU, the bot's call p50
  20.6 ms, the server's 16.2).

  | the bot's GPU call, p50 | 16a (11-08 noon) | p12's live run | `final` |
  |---|---|---|---|
  | per-map (alternating with the CPU) | 41.9 / 38.6 ms | - | **22.0 / 22.7 ms** |
  | soak / live, GPU calls only | 37.4 ms | 64.7 ms (the numpy conversion) | **20.6 ms** |

  - **Decision (pre-registered):** p13 (rogue-xmas02.md 4T) runs on `final`: `serve-cmd
    --ov-preproc gpu --ov-precision f32` (the defaults), the floor at 2450.
- ➡️ **The floor's unit INSTALLED 2026-11-08 18:06:52 ICT** (Batt: "install it, do it for me";
  rogue-xmas02.md Amendment H): `/etc/systemd/system/poring-lab-gpu-clock.service` +
  `/usr/local/libexec/poring-lab-gpu-clock.sh`, enabled and active; its log "floor 2450 MHz
  (start)". Proven both ways: `systemctl stop` -> 300, `start` -> 2450. p13 (16:33-17:04) ran on
  the run-time setting; the live result: 20.6 ms a call (p12 64.7). Batt adopted the fast path
  as the live detector (Amendment H item 2).
