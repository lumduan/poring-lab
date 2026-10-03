---
doc_type: roadmap
status: LIVING
last_reviewed: 2026-10-03
---

# poring-lab roadmap

## At a glance

```mermaid
flowchart TD
    N1["Now · web console, 30 fps stream,<br/>clipboard + file transfer (ADR-0004)<br/>ACTIVE"]
    N2["Disk split<br/>NOT DOING - Batt 2026-10-01<br/>guards + tar/tmpfs instead"]
    N3["Guarded builds · operator window<br/>sniffer + gamestream done 2026-10-03<br/>vision: stall ACCEPTED, timer Sun 03:35"]
    D1["PACKETVER 20211103 · pre-renewal<br/>DECIDED 2026-09-30"]
    S1["RO client running on rAthena<br/>DONE · 30 fps reach the lab (FreeRDP 3.32)"]
    D2["ADR-0005 · vision loses direct X access<br/>DECISION - PROPOSED"]
    D3["Environment interlock · ADR-0006 rule 2<br/>NOT BUILT - issue"]
    E1["Community-server permission evidence<br/>OPERATOR - pending"]
    P0["Phase 0 · stack up, capture FPS,<br/>end-to-end latency<br/>ACTIVE - console latency work"]
    P1["Phase 1 · packet decoder +<br/>world state, ground truth<br/>DONE first slice · validated"]
    H1["RDP delivery · Arm C FreeRDP 3.32.1<br/>30 fps outdoor, p95 157 ms<br/>DONE"]
    C1["Console capture · Sunshine S1 trial<br/>cause found 2026-10-03: GL present on Xvfb<br/>DONE - superseded by S2"]
    S2["S2 · GameStream without Xvfb<br/>V3b on the frame bus reliable 2026-10-03<br/>ACTIVE - key-to-paint tail, step 3"]
    P2["Phase 2 · projection + auto-labeling<br/>1280x720 frozen · sink + locale tooling built<br/>ACTIVE - sink live, ADR-0010 accepted"]
    P3["Phase 3 · YOLO training +<br/>evaluation vs ground truth<br/>BLOCKED"]
    P4["Phase 4 · fast loop, FSM,<br/>input through the mux<br/>BLOCKED"]
    P5["Phase 5 · humanizer +<br/>human-vs-bot detector<br/>BLOCKED"]
    P6["Phase 6 · Typhoon slow loop<br/>community server + rAthena<br/>BLOCKED"]

    N1 --> N2 --> N3
    N3 --> H1
    H1 --> C1
    H1 --> S2
    H1 --> P2
    D1 --> S1
    N1 --> P0
    S1 --> P0
    S1 --> P1
    P0 --> P2
    P1 --> P2
    P2 --> P3 --> P4
    D2 --> P4
    D3 --> P4
    E1 --> P6
    P4 --> P5
    P4 --> P6

    classDef done     fill:#d4f4dd,stroke:#2d8a4e,color:#1a5c33
    classDef active   fill:#fff3cd,stroke:#cc9a06,color:#7a5c04
    classDef ready    fill:#d6e9ff,stroke:#3b7dd8,color:#1e4d8f
    classDef blocked  fill:#f0f0f0,stroke:#888,color:#555
    classDef decision fill:#fde0e0,stroke:#d05555,color:#8f2e2e
    classDef goal     fill:#ede0fb,stroke:#8a5cd8,color:#4d2e8f

    class D1,S1,P1,N2,H1,C1 done
    class N1,P0,P2,S2,N3 active
    class D2,D3,E1 decision
    class P3,P4,P5,P6 blocked
```

| Step | Status | What it is | Blocker |
|---|---|---|---|
| **Now** | 🟡 ACTIVE | Web console on `frontend-dev` (tmpfs, no image builds); 30 fps stream; 24 h IO baseline in `data/metrics/`. **Clipboard paste + `\\tsclient\transfer` files ([ADR-0004](adr/0004-human-only-clipboard-and-file-transfer.md))**: ✅ deployed and live-verified 2026-09-30 11:34 ICT. ⌘V works directly on the remote screen (a hidden textarea captures the keys). Windows → Mac clipboard: future work, blocked on ADR-0005 + HTTPS. **2026-10-03:** the banner's D3D/"ro_agent recover" warning is RDP-only, and a clean room shows its variant, box and hard cap. ASSIST now comes back by itself after a GUARDED `restart:backend` ([ADR-0002](adr/0002-input-mux.md) amendment; never BOT, any other boot stays HUMAN), verified live twice. | Batt's manual checks: console keys/toolbar, paste ASCII + Thai, upload/download |
| **Disk split** | ✅ DECIDED: NOT DOING | Batt, 2026-10-01: no disk split. Keep the guards (`scripts/guarded_build.py`, tolerant `--sustain 30 --spike 25`) and the tar/tmpfs approach; don't plan around a split. | — |
| **Guarded builds** | 🟡 vision SCHEDULED: Sun 2026-10-04 03:35 ICT | ➡️ **2026-10-03 (Batt): the ~70 s quant stall is ACCEPTED** (he backfills it from AWS; weekends are the home servers' maintenance window). The `poring-vision-night` systemd --user timer fires at 03:30 ICT (5 min baseline), then `guarded_build.py --sustain 180 --spike 101 build:vision` (tolerates the known stall, still aborts a cgroup above 10 % for 3 min straight), then `run:vision check_gpu.py`; hard deadline 05:30. It records the STALL WINDOW (`pressure_sampler.py window`: 10 s bins with quant-postgres or orderbook io_full > 25 %, ICT + UTC) and container/GPU state before and after, all in `/dev/shm/poring-lab-tmp/vision-night/`.<br>**Weekend window 2026-10-03 (tolerant guard):**<br>- ✅ **slim sniffer** live (71 MB; [ADR-0007](adr/0007-packet-ground-truth-channel.md) decision 2 superseded);<br>- ✅ **gamestream** with the clean-room variants and the S2 spike (364 MB);<br>- ❌ **vision ABORTED twice.** 1st: quant-postgres 27.9 % while uv wrote ~3 GB of CUDA wheels. 2nd (uv throttled, after settling): orderbook 61–99 % and postgres 38–52 % within the first 15 s, while BuildKit resolved/unpacked the cuda base image. Per the rule, stopped and reported.<br>- ❌ **3rd attempt (Batt's one-off guard for vision, `--sustain 60 --spike 101`, 14:13):** ABORTED again, sustained. orderbook 76.7 % for 60 s; quant-postgres 60–86 % per 10 s bin for ~70 s while uv wrote the ~5 GB install. No restarts. Not retried.<br>- `check_gpu.py` is ready (cap enforcement + a runtime-download report) and runs via `guarded_build.py run:vision`.<br>Still to build: the production frontend. Earlier: desktop ✅ 2026-10-01; rathena and db 2026-09-30. | The night run's result (see `/dev/shm/poring-lab-tmp/vision-night/run.log`). ~~**Batt:** vision needs a write-RATE cap … A tolerance change alone won't do it~~ ➡️ SUPERSEDED 2026-10-03: Batt accepted the stall instead (backfilled from AWS). Avoid the host cron at ~:03–:05 |
| **PACKETVER + RO client** | ✅ DECIDED | Batt, 2026-09-30: the 2021-11-03 kRO exe at **PACKETVER 20211103**, **pre-renewal**, kRO 2021-06 data, WARP patches ([docs/client/rathena-client.md](client/rathena-client.md)). | — |
| **RO client on rAthena** | ✅ DONE 2026-09-30 | A **separate client** in `C:\RO-rAthena\` logs in to this lab's rAthena. RagnarokClassic is untouched (a registry and folder baseline is compared at every step). What works: login, a character on `new_4-1`, movement. Thai typed via Kedmanee, rendered in chat, and stored byte-exact as CP874 in `chatlog`. Recipe: [rathena-client.md](client/rathena-client.md). ~~RDP session 1280×800 (2026-09-30). Game window 800×664 (client area 784×625)~~ ➡️ **2026-10-02: RDP session 1440×900, game window 1296×759 = a 1:1 1280×720 client area at (80,77), frozen for Phase 2** (the client renders at its client-area size; it was never scaled). dgVoodoo **FPSLimit 30**, and a "Ragnarok Offline" desktop shortcut (2026-10-01). **Render performance measured:** the game renders at **60 fps on the Intel UHD 630** (not WARP). Clicks register at 20 ms holds; UI click→response is p50 64 ms from release. English UI text applied (data only, 2026-10-01): no more `NO MSG`, and Thai chat is still byte-exact. Desktop is CPU-protected (weight 12, 8-core ceiling). **Open:** only ~6–17 fps reach Xvfb during full-scene motion. Windows RemoteFX counters show the server skipping 25–28 frames/s for "Insufficient Client Resources", so the bottleneck is FreeRDP decode ([phase0-latency.md](phase0-latency.md)). | **RDP delivery ceiling: must be fixed before dataset collection.** 2026-10-01: RDP session moved to the STANDARD account `poring-lab`; `RDP_GFX=progressive` doubled outdoor delivery (6 -> 12 fps); next a newer FreeRDP (H.264 row) |
| **Environment interlock · ADR-0006 rule 2** | 🟥 NOT BUILT | Fail-closed: the mux refuses BOT/ASSIST automation unless a verifiable signal (not the agent's judgment) says the connected server is rAthena or the community server. Until it exists, no agent automation runs on the community server; Batt may play there manually. [Issue #2](https://github.com/lumduan/poring-lab/issues/2), `blocks-phase-4`. | Design + implementation; a prerequisite of Phase 4 (with ADR-0005) |
| **Community-server permission evidence** | 🟥 OPERATOR | The server's bot/AI-testing rules, recorded for its exact host in [environments/community-server.md](environments/community-server.md). **Pending**, so the server counts as forbidden until then (ADR-0006 rule 1). | Batt supplies the link |
| **ADR-0005 · vision X isolation** | 🟥 DECISION | vision can reach XTEST, selections and window contents directly, and can pose as HUMAN on `:8000`. Recommended: frames from the backend + an X auth cookie + an internal agent network + no RECORD ([ADR-0005](adr/0005-vision-x-access.md); [issue #1](https://github.com/lumduan/poring-lab/issues/1), `blocks-phase-4`). | Operator picks the option set; implemented before Phase 4 |
| **Phase 0** | 🟡 ACTIVE (part) | Stack up; capture FPS; end-to-end (motion-to-photon) latency; RDP codec comparison (`RDP_GFX`). **Started 2026-09-30:** latency instrumentation, runtime knobs, and the probe ([phase0-latency.md](phase0-latency.md): method, results, ranked options, the Windows App A/B). **HP/SP text fidelity is now unblocked**: the RO client on rAthena works. | The agent-side grab rate needs the vision image |
| **Phase 1** | ✅ FIRST SLICE DONE 2026-10-01 | Packet decoder + world state as **offline ground truth**, never agent input ([ADR-0007](adr/0007-packet-ground-truth-channel.md) ACCEPTED). `poring_packets` (build-time length tables from pinned rAthena + OpenKore), the sniffer on the dev overlay (no build), `/ingest/packets` → console "Packet timeline" (`/ws/packets`, LAN viewers only), the `captures` volume, agent player + validation GM accounts. **Validated live** ([phase1-validation.md](phase1-validation.md)): server tick = host CLOCK_MONOTONIC (406 samples, 0–1 ms); position, chat (ASCII + Thai, byte-exact), HP and entities (5/5 within 1 cell) against GM/DB truth; 0 unknown ids, 0 desyncs; packet→frame p50 150 / p95 585 ms. | Next slices (combat, items) as Phase 2 needs them; GAT paths in Phase 2. (The slim sniffer image is live since 2026-10-03.) |
| **RDP delivery (H.264)** | ✅ DONE 2026-10-01 | **Arm C: FreeRDP 3.32.1** (trixie-backports, one guarded desktop build) lifted the ceiling. `progressive` now delivers **30 fps outdoors** (was 9) and 17 indoors (was 7), Windows output 30 with **0 client skips** (was 17–20/s), 4.4–4.8 desktop cores (was 6.7–6.8), and packet→frame p50/p75/p90/p95 **119/139/151/157 ms** (was 242/1007/>1500/>1500). `AVCthin` matches the frames at ~1 core but is lossy; **progressive kept**. The client runs 26 threads, not 329. ⚠ 3.32 claims X CLIPBOARD (empty) on Windows copies, and the watchdog clears it (ADR-0004 amendment b). History: Arm A (AVC444 on 3.15, no gain); the AVC420 experiment. [h264-plan.md](h264-plan.md), "Arm C results". | Done. Open: Batt's live paste check on 3.32; optional FPSLimit 60 + DWMFRAMEINTERVAL now that delivery sits at the 30 fps cap |
| **Console capture (Sunshine; VNC fallback)** | ✅ CAUSE FOUND 2026-10-03 (clean room; it was PARKED 2026-10-02): Moonlight-qt's first SDL_RenderPresent hangs in Mesa llvmpipe GLX on Xvfb. Superseded by S2 | **Batt approved Sunshine and the S1 trial** ("Sunshine research gets the weight"). Built: the **capture-backend lock** (`state/capture-backend`, `scripts/capture_backend.py`: rdp-loop and the new `gamestream` service each connect only under their backend; `/health` + console show it), the **benchmark SPEC v1** + `scripts/bench.py` (one fixed procedure for every backend), the `gamestream` service (moonlight-qt 6.1.0: absolute mouse via X events). Sunshine v2026.914.233613 installed by Batt (➡️ 2026-10-02: that MSI had never run, and the April EXE install was running; REPLACED the same evening by the verified MSI, 2026.914.233613, with payload-verified binaries, pairing kept: [runbook](operations/sunshine-msi-replace.md)) after a signature check. [ADR-0009](adr/0009-console-session-capture.md) (revised), [benchmarks](benchmarks/README.md). **2026-10-02: the lock is deployed** (one guarded midday window; host, desktop, backend and `/health` agree). **SPEC v2** (1280×720 client): the RDP baseline is 23 fps outdoor (was 30 at 784×625), packet→frame p50 376 / p95 521 ms, key→paint p50 101 ms, static UI bit-exact. The larger frame made the RDP leg throughput-bound. **Paired** (exactly one client, ours). **Handover 1 stopped and recovered:** tscon from Batt's console failed (1326) and the console stayed 1920×1080 ([ADR-0009](adr/0009-console-session-capture.md)). **2026-10-02 evening (handovers 2–6), [ADR-0009](adr/0009-console-session-capture.md):** the Windows side works. VDD 1440×900 with Sunshine `ensure_only_display`, and tscon through Batt's SYSTEM task (exit 0); Mouse Keys stay off (Flags 62 before and after). Lab side: a **1920×1200 canvas** with `SESSION_SIZE=1440x900` at 0,0 is live (RDP `/size`; backend, vision and ro_agent crop to it; GAME_REGION unchanged), and Moonlight now opens its window at native 1440×900. Fixed along the way: the X focus left at None after a stream (keys vanished), the placer's window class, and llvmpipe's 64-thread pool throttling the 4-core quota. **OPEN: the stream stays black.** Moonlight's main thread stalls in a futex, so nothing is presented although video arrives (8.9 Mbit/s); the same with the software renderer and dummy audio. Handover 1 (no VDD) did render. **Any S1-vs-RDP number mixes protocol AND renderer** (Batt, 2026-10-02): S1's value is functional, and performance conclusions come from S2. **PARKED (Batt, 2026-10-02)** at "Windows side works, Moonlight-qt main loop stalls"; no gdb. Display investigation: **inconclusive**. Moonlight saw no mid-stream reconfiguration; Sunshine's own log is rewritten at each start, so its side is gone. Fact: TERM-killed clients left Sunshine's app running and later connects were `/resume`s. **to-rdp now ends the stream cleanly** (Moonlight `quit` → Sunshine /cancel), then checks the revert (rc 3 + remedy). Not yet exercised live. | none: superseded by **S2**. Its step 0 (a temporary Mac Moonlight pairing, Batt) answers S1's functional questions and whether the stall is lab-side. ~~The pending Sunshine display revert clears at the next console session~~ ➡️ SUPERSEDED 2026-10-02 22:15: the new Sunshine dropped it. ~~The Samsung stays off until Batt presses Win+P at the Dell~~ ➡️ SUPERSEDED 2026-10-03: Batt switched the Samsung on and asked for it to be restored WITHOUT Win+P through RDP. Read-only from RDP: connected and enumerated, inactive; the method (Sunshine `dd_configuration_option` disabled for the entry, `DisplaySwitch /extend` in the console session) is proposed in [s2-plan.md](s2-plan.md) §9a and waits for approval |
| **S2 · GameStream without Xvfb** | 🟡 ACTIVE: plan APPROVED 2026-10-02; the step 1 spike LIVE and reliable 2026-10-03; V3b (frame bus) measured 2026-10-03 | Batt's capture-direction note: decode the GameStream video ONCE (PyAV) in the `gamestream` service, into a shared-memory **frame bus**. The bot reads every frame; the human view (console JPEG) is capped, and both share `frame_id`/`t_mono_ns`. Input goes from the mux (all rules intact) to the GameStream input channel through a backend-only socket (`poring_env` `gamestream` backend). vision reads the bus read-only = ADR-0005 option (a) for this path. Shared viewing and shared control are designed only ([ADR-0013](adr/0013-windows-status-indicator.md) indicator; pixel-only human-presence detection; audit without keystrokes). Plan: [s2-plan.md](s2-plan.md); [ADR-0009](adr/0009-console-session-capture.md) 2026-10-02 amendment (APPROVED). [ADR-0013](adr/0013-windows-status-indicator.md) ACCEPTED (build later). **2026-10-03, step 0 attempt 1:** the Mac paired, but its app was started while the session was still on RDP (black, as expected), so nothing was tested. The lab's `quit` ended the Mac's app (`/cancel` is host-wide), and the Mac was unpaired and the firewall restored to `192.168.1.13`, both read back ([s2-plan.md](s2-plan.md) §9). | **2026-10-03 clean room (13:16–14:07)** ([ADR-0009](adr/0009-console-session-capture.md)):<br>- V1/V2 Moonlight-qt BLACK: the first SDL_RenderPresent hangs in Mesa llvmpipe GLX on Xvfb;<br>- **V3, the S2 spike, RELIABLE**: every functional check passes through the mux, and SPEC v2 gives 33 fps / packet→frame 119 ms / 1.5 cores vs RDP's 23 fps / 376 ms / ~4.5 cores; the key→paint tail is worse.<br>~~No blocker: **step 2, the frame bus**~~ ➡️ step 2 BUILT 2026-10-03 (0 torn frames in the torture test). ✅ **V3b clean room DONE 17:07–18:12** (ADR-0009 "Clean room 2"): the S2 client on the frame bus is reliable; key→paint p50/p95 121/277 ms (V3 138/350, RDP 101/114), packet→frame 114/268, **1.03 lab cores** (RDP 5.4), all measured on the bus. **The console is VDD-only by Batt's decision** ([console-display.md](operations/console-display.md)). Next: the key→paint tail; S2 step 3 (the input socket, replacing the input-only X window) |
| **Phase 2** | 🟡 ACTIVE (offline foundation) 2026-10-02 | Backend-agnostic, offline: `packages/poring_dataset` -- rAthena map caches at the pinned SHA + the exact A* port (walk paths), `Timeline` (world at a frame's time, per-backend latency offset), homography projection, YOLO labels, WebDataset shards, IoU metrics; `record_session.py`, `calibrate_projection.py`, `qa_export.py` + the console `/qa` page. [phase2-plan.md](phase2-plan.md), [ADR-0010](adr/0010-dataset-format.md) PROPOSED. **2026-10-02: resolution FROZEN at a 1:1 1280×720 client** (Batt). UI anchor map: registry, masked templates and measured geometry ([ADR-0011](adr/0011-ui-anchor-map.md) PROPOSED). **2026-10-02 evening:** **dataset sink built** (`scripts/dataset_ship.py`: sha256 → rsync → re-hash on the NAS → INDEX → only then delete the local copy; SET-hours refusal; 365 d retention with pins; `record_session.py` records to `/home/batt/poring-lab-rec` with caps of 140 GB free / 20 GB unshipped). The operator recipe is [nas-sink.md](operations/nas-sink.md); ADR-0010 stays PROPOSED until the round-trip. **Language-agnostic UI** ([ADR-0012](adr/0012-locale-agnostic-ui.md) PROPOSED): the anchor map stores keys (`label_key`, never text), with masks that are locale-invariant (N-way); `grf_read.py` and `locale_pack.py` (canonical `msg.k` keys, alignment + coverage); the never-commit guard (`.gitignore` + `.githooks/pre-commit`). The guide is [locale-packs.md](locale-packs.md). **Part D** (resolution- and language-agnostic, one goal) is in [phase2-plan.md](phase2-plan.md); its first step, the session area on a 1920×1200 canvas, is live. **2026-10-02 21:06: the dataset sink is LIVE and [ADR-0010](adr/0010-dataset-format.md) is ACCEPTED**: a 30 s recording shipped to the NAS (re-hash verified, the local copy deleted); soft+automount NFS mounts on the VM. | ✅ **Thai copy DONE 2026-10-03:** data only, 434 files hash-verified, revoked, `@pristine-20261003`.<br>**Part C:** C1–C3 done. `data.grf` is GRF 0x200 with standard flags; the text sources are plain; msgstringtable has 4,733 lines, a newer build than the lab's 3,970.<br>~~**C4 is BLOCKED on the kRO reference table** … Batt decides its source~~ ➡️ **2026-10-03, Batt decided: an OFFLINE PARSER of the exe's bytes** (never executed; WARP only as a cross-check). Built: `scripts/msgtable_extract.py` + `locale_pack.py --source-ref/--reindex/--source-untranslated`. ✅ **C4 DONE 2026-10-03:** the lab exe's table extracted (exactly 3,970 records; it is the KOREAN original, which corrects rathena-client.md's "embeds English"); the Thai exe is packed (WinLicense-style), so the ids were verified instead; the `th` pack is valid, 3,055/3,785 keys (80.7 %), a reindexed 3,970-line install table (3,223 Thai), printf-safe. `ro_thai` deleted (NAS copy 434/434 OK first). ~~**C5 BLOCKED: Windows refuses guest SMB**~~ ➡️ the guest share was refused by Windows (error 1272) and deleted unused; Batt chose a one-off through `\\tsclient\transfer`. ✅ **C5 DONE 16:07:** installed (hash = manifest), Thai frames, acceptance th + en on the registered windows: basic_info ✅ (after a Thai mask variant), hotbar ✅, open/close + HP read ✅, Thai chat HEX byte-exact ✅; chat window ❌ in BOTH languages (a stale template, not the pack). **English restored** as the baseline ([locale-packs.md](locale-packs.md) §6). Follow-ups: login/OK-Cancel/NPC anchors, the chat template re-cut |
| **Phase 3** | ⬜ BLOCKED | YOLO training on the auto-labels + evaluation against ground truth on held-out sessions. | Phase 2 labels (and the vision image) |
| **Phase 4** | ⬜ BLOCKED | Fast loop: an FSM acting only through `/internal/agent` and the mux (ASSIST first; interventions logged). | Needs ALL of Phase 3 (perception), ADR-0005 implemented (its acceptance test passing), AND the environment interlock (ADR-0006 rule 2) |
| **Phase 5** | ⬜ BLOCKED | Humanizer (timing and trajectories of the bot's input) + a human-vs-bot detector trained on the human and bot input logs; target ROC-AUC toward 0.5. | Phase 4 bot traces |
| **Phase 6** | ⬜ BLOCKED | Typhoon slow loop (addressee detection and multi-party chat on the community server; deterministic tests on rAthena). The LLM emits **intents only**, consumed by the FSM; never in the fast loop. Any chat it writes goes through the mux as `source=bot`. | Phase 4 (independent of Phase 5); community-server experiments also need the permission evidence |

**The real bottlenecks are OPERATOR DECISIONS (build windows, ADR-0005, ADR-0009's install list) and the
environment interlock (ADR-0006).** The RDP delivery ceiling was removed on 2026-10-01 (Arm C).
- ~~S2's next step needs **Batt's presence** … or a **build window**~~ ➡️ 2026-10-03: the spike ran (V3
  reliable) and step 2 (the frame bus) is built. ~~S2's next step is **Batt's approval** of the V3b clean-room
  run~~ ➡️ done 2026-10-03 (V3b measured; Part C done too). S2's next steps (the key→paint tail,
  step 3's input socket) need a build window, not a decision.
- There is no disk split (Batt, 2026-10-01): image builds are deliberate, guarded steps in an operator-chosen
  window. Phase 1 needed none (dev-overlay sniffer).
- ~~**Dataset collection (Phase 2) waits for the RDP delivery ceiling**~~ ➡️ RESOLVED 2026-10-01 (Arm C):
  FreeRDP 3.32.1 delivers the game's full 30 fps outdoors ([h264-plan.md](h264-plan.md)). Phase 2 still
  needs Phase 0's remaining numbers (codec fidelity vs a lossless reference; agent-side grab rate) and
  Phase 1.
- Phase 4 cannot start until vision loses direct X access (ADR-0005) AND the environment interlock
  exists (ADR-0006), however good perception gets.
- Phase 6's social experiments also wait for the community server's permission evidence.
- Phase 0's desktop-only measurements have no blocker at all.

## Ideas / parked (kept, not scheduled -- Batt, 2026-10-02)

| Idea | Design notes so far | Why parked |
|---|---|---|
| **Hyper-V + XKore / NetRedirect / OpenKore study track** | A Windows VM (Hyper-V) running the RO client with OpenKore attached via XKore (client-side packet hook) or NetRedirect, to study a mature bot's decision loop against our rAthena. It must stay inside the sanctioned environments (ADR-0006: rAthena only) and never touch the community server; it is a separate research track, never the agent's input path (CLAUDE.md rule 1: pixels in, input out). | Queued after the console-capture work; needs its own ADR before any install |
| **FPSLimit 60 + DWMFRAMEINTERVAL 15** | Now actionable: FreeRDP 3.32.1 delivers the full 30 fps at FPSLimit 30 (h264-plan.md, Arm C). Raise dgVoodoo's FPSLimit to 60 and the DWM frame interval together, then re-run the benchmark (SPEC v1) per backend. | Kept for after the backend comparison, so one variable changes at a time |
| **Low-latency remote control for a driving game / a real drone** | The same stack (capture backend + benchmark SPEC + mux) applied to a latency-critical target: the key->paint and packet->frame metrics become control-loop latency budgets. | An idea only; no design yet |

## Ordered plan

1. **Now** (2026-09-29/30): web console, fps fix, 24 h IO baseline, ADR-0004 clipboard + file
   transfer. In parallel, because nothing blocks it: Phase 0 on desktop content (motion-to-photon, codec
   comparison).
2. ~~**Weekend:** disk split~~ ➡️ NOT DOING (Batt, 2026-10-01): guards + tar/tmpfs instead.
3. **Guarded builds, operator-chosen window** (no split):
   - guarded builds (`scripts/guarded_build.py`): frontend, desktop, sniffer (rathena and db: done 2026-09-30);
   - `scripts/smoke_test.sh`;
   - the vision build, then `check_gpu.py`.
4. ~~**RO client on rAthena**~~ ✅ done 2026-09-30. Next: Phase 0's HP/SP text fidelity, the client resolution, and Thai Test A vs B.
5. **Phase 1 → Phase 2 → Phase 3** as the graph allows. ADR-0005 and the environment interlock can
   be implemented any time before Phase 4, and the earlier the better.
6. **Phase 4**, then **Phases 5 and 6** in parallel.

## Phases (exit gates are proposals; adjust as the research sharpens)

| Phase | Scope | Exit gate |
|---|---|---|
| 0 · Stack up + measure | Capture FPS (backend and agent side); motion-to-photon latency (a mux-injected key toggles a large UI element; time to the first changed pixel, on one host clock); codec fidelity vs a lossless on-Windows screenshot (SSIM/PSNR), first on desktop content, then HP/SP text in the RO client | Numbers recorded; codec chosen |
| 1 · Packet decoder + world state | Offline decoder for the client's PACKETVER; world-state timeline (entities, positions, HP/SP, map) aligned to frames; cross-checked against rAthena logs | The decoded state matches the server on N sessions |
| 2 · Projection + auto-labeling | Calibrate isometric world → screen (zoom, camera) from ground-truth positions; generate YOLO labels by projection | Projection error within an agreed pixel bound; an auto-labelled dataset of agreed size |
| 3 · YOLO + evaluation | Train on the auto-labels; precision/recall vs projected ground truth on held-out sessions | Above an agreed bar |
| 4 · Fast loop (FSM) | Scripted FSM through `/internal/agent` only; ASSIST first; the human lease handles interventions | Stable multi-hour run; interventions logged; ADR-0005 acceptance test green |
| 5 · Humanizer + detector | Detector on human vs bot input logs; humanizer shapes bot input | Detector ROC-AUC near 0.5 on held-out data |
| 6 · Typhoon slow loop | Addressee detection and multi-party chat on the community server; deterministic tests on rAthena. LLM intents (goals) → FSM; never in the fast loop | Intents steer the FSM with no added fast-loop latency; addressee detection scored on community-server chat (pseudonymized) |

Hard rule throughout: pixels in, mouse/keyboard out.
- Packet and server-log data are only ever *offline* ground truth (Phases 1–3), never agent input
  (see `CLAUDE.md`).
- Clipboard and file transfer are human-only (ADR-0004).

## Maintenance

This is a **living document**. Any task that closes or materially advances an item here must update the
at-a-glance diagram, the status table and `last_reviewed` in the same change, not later.
