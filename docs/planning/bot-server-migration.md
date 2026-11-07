---
doc_type: design
hypothesis: "Moving our GPU work (training first, then the live detector) to the dedicated bot-server (192.168.1.228, Intel Arc A380) stops our jobs from touching the shared host's GPU (Frigate) and disk (quant capture), without moving the live loop."
status: "A1 APPROVED 2026-11-07 (Batt: 'move it; that is why this machine exists'). The Arc A380 test PASSED 15:05-15:09 ICT (section 9): OpenVINO FP32 boxes = CPU boxes, 41-42 ms a call; PyTorch XPU + ultralytics train. Waiting on Batt: the NFS export for .228 and the DHCP reservation (section 10). The agent's knowledge is on bot-server (docs/operations/bot-server-handover.md)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gpu-live-detector.md, endpoints-as-config.md, ../benchmarks/cpu-detector-speed.md, ../adr/0005-vision-x-access.md, ../operations/nas-sink.md]
next_action: "Batt: add 192.168.1.228 to NFS export 7 and reserve .228 in DHCP. Then the agent: the read-only datasets mount on bot-server, an XPU device path in poring_vision (train.py / gpu.py), a trainer runner for a host that is not shared, and a first training run there pre-registered against the RTX 5060 Ti."
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
    process;
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
- **For comparison, ubuntu-docker's RTX path:** 49-52 ms a call, but paused half the time while
  R3 measures (p9: 911 GPU / 905 CPU detections).
