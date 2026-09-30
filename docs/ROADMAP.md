---
doc_type: roadmap
status: LIVING
last_reviewed: 2026-09-30
---

# poring-lab roadmap

## At a glance

```mermaid
flowchart TD
    N1["Now · web console, 30 fps stream,<br/>clipboard + file transfer (ADR-0004)<br/>ACTIVE"]
    N2["Weekend · disk split<br/>quant data to its own vdisk<br/>OPERATOR"]
    N3["After the split · pending builds,<br/>smoke test, vision + check_gpu<br/>BLOCKED"]
    D1["PACKETVER + RO client<br/>OPERATOR DECISION"]
    S1["RO client running on rAthena<br/>BLOCKED"]
    D2["ADR-0005 · vision loses direct X access<br/>DECISION - PROPOSED"]
    P0["Phase 0 · stack up, capture FPS,<br/>end-to-end latency<br/>READY - desktop + backend parts"]
    P1["Phase 1 · packet decoder +<br/>world state, ground truth<br/>BLOCKED"]
    P2["Phase 2 · isometric projection<br/>calibration + auto-labeling<br/>BLOCKED"]
    P3["Phase 3 · YOLO training +<br/>evaluation vs ground truth<br/>BLOCKED"]
    P4["Phase 4 · fast loop, FSM,<br/>input through the mux<br/>BLOCKED"]
    P5["Phase 5 · humanizer +<br/>human-vs-bot detector<br/>BLOCKED"]
    P6["Phase 6 · Typhoon slow loop,<br/>intents only<br/>BLOCKED"]

    N1 --> N2 --> N3 --> S1
    D1 --> S1
    N1 --> P0
    S1 --> P0
    S1 --> P1
    P0 --> P2
    P1 --> P2
    P2 --> P3 --> P4
    D2 --> P4
    P4 --> P5
    P4 --> P6

    classDef done     fill:#d4f4dd,stroke:#2d8a4e,color:#1a5c33
    classDef active   fill:#fff3cd,stroke:#cc9a06,color:#7a5c04
    classDef ready    fill:#d6e9ff,stroke:#3b7dd8,color:#1e4d8f
    classDef blocked  fill:#f0f0f0,stroke:#888,color:#555
    classDef decision fill:#fde0e0,stroke:#d05555,color:#8f2e2e
    classDef goal     fill:#ede0fb,stroke:#8a5cd8,color:#4d2e8f

    class N1 active
    class N2,D1,D2 decision
    class P0 ready
    class N3,S1,P1,P2,P3,P4,P5,P6 blocked
```

| Step | Status | What it is | Blocker |
|---|---|---|---|
| **Now** | 🟡 ACTIVE | Web console on `frontend-dev` (tmpfs, no image builds); 30 fps stream; 24 h IO baseline in `data/metrics/`. **Clipboard paste + `\\tsclient\transfer` files ([ADR-0004](adr/0004-human-only-clipboard-and-file-transfer.md))**: ✅ deployed and live-verified 2026-09-30 11:34 ICT. | Batt's manual checks: console keys/toolbar, paste ASCII + Thai, upload/download |
| **Weekend · disk split** | 🟥 OPERATOR | Move the quant Postgres/Mongo data to its own Proxmox vdisk; the window comes from the IO baseline (`scripts/io_summary.py`). | Operator, weekend |
| **After the split** | ⬜ BLOCKED | Build rathena, the production frontend, desktop (bakes the ADR-0004 `rdp-loop.sh`/`run-x11vnc.sh`, today bind-mounted by the dev overlay) and vision; pull db; `scripts/smoke_test.sh`; `check_gpu.py` (sm_120). | The disk split: on the shared disk, builds pushed capture Postgres past 25 % IO stall (2026-09-29) |
| **PACKETVER + RO client** | 🟥 OPERATOR | Which client executable date (PACKETVER); renewal or pre-renewal. Defaults: 20211103, renewal. | Operator decision; deferred |
| **RO client on rAthena** | ⬜ BLOCKED | The Windows client logs in to this lab's rAthena. | Needs BOTH the rathena image (after the split) AND the PACKETVER decision |
| **ADR-0005 · vision X isolation** | 🟥 DECISION | vision can reach XTEST, selections and window contents directly, and can pose as HUMAN on `:8000`. Recommended: frames from the backend + an X auth cookie + an internal agent network + no RECORD ([ADR-0005](adr/0005-vision-x-access.md); [issue #1](https://github.com/lumduan/poring-lab/issues/1), `blocks-phase-4`). | Operator picks the option set; implemented before Phase 4 |
| **Phase 0** | 🔵 READY (part) | Stack up; capture FPS; end-to-end (motion-to-photon) latency; RDP codec comparison (`RDP_GFX`). **Can start now** on desktop + backend: motion-to-photon, and the codec comparison on desktop content. **HP/SP text fidelity waits** for a working RO client on rAthena. | Full exit needs "RO client on rAthena"; the agent-side grab rate needs the vision image |
| **Phase 1** | ⬜ BLOCKED | Packet decoder + world state as **offline ground truth** (sniffer pcaps + rAthena logs → a timeline of entities, positions, HP/SP, synchronised to frames by `t_mono_ns`). Never agent input. | RO client on rAthena (and the sniffer image, after the split) |
| **Phase 2** | ⬜ BLOCKED | Isometric projection calibration (world → screen for the client's camera) + auto-labeling (project the ground-truth world state into frames to make YOLO labels). | Needs BOTH Phase 0 (capture pipeline + chosen codec) AND Phase 1 (ground-truth positions) |
| **Phase 3** | ⬜ BLOCKED | YOLO training on the auto-labels + evaluation against ground truth on held-out sessions. | Phase 2 labels (and the vision image) |
| **Phase 4** | ⬜ BLOCKED | Fast loop: an FSM acting only through `/internal/agent` and the mux (ASSIST first; interventions logged). | Needs BOTH Phase 3 (perception) AND ADR-0005 implemented (its acceptance test passing) |
| **Phase 5** | ⬜ BLOCKED | Humanizer (timing and trajectories of the bot's input) + a human-vs-bot detector trained on the human and bot input logs; target ROC-AUC toward 0.5. | Phase 4 bot traces |
| **Phase 6** | ⬜ BLOCKED | Typhoon slow loop: an LLM proposes **intents only**, consumed by the FSM; never in the fast loop. | Phase 4 (independent of Phase 5) |

**The real bottlenecks are the SHARED DISK, OPERATOR DECISIONS and ADR-0005.**
- Every image build waits for the weekend disk split, and with it the RO client on rAthena. That is the
  root of Phase 1 and Phase 0's HP/SP fidelity.
- The PACKETVER/client decision gates the same node.
- Phase 4 cannot start until vision loses direct X access (ADR-0005), however good perception gets.
- Phase 0's desktop-only measurements have no blocker at all.

## Ordered plan

1. **Now** (2026-09-29/30): web console, fps fix, 24 h IO baseline, ADR-0004 clipboard + file
   transfer. In parallel, because nothing blocks it: Phase 0 on desktop content (motion-to-photon, codec
   comparison).
2. **Weekend:** disk split (operator), in the quietest window from `scripts/io_summary.py`.
3. **After the split:**
   - guarded builds (`scripts/guarded_build.py`): rathena, frontend, desktop, then `pull:db` and `up`;
   - `scripts/smoke_test.sh`;
   - the vision build, then `check_gpu.py`.
4. **RO client on rAthena**, once PACKETVER is decided. Then Phase 0's HP/SP text fidelity.
5. **Phase 1 → Phase 2 → Phase 3** as the graph allows. ADR-0005 can be implemented any time before
   Phase 4, and the earlier the better.
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
| 6 · Typhoon slow loop | LLM intents (goals) → FSM; never in the fast loop | Intents steer the FSM with no added fast-loop latency |

Hard rule throughout: pixels in, mouse/keyboard out.
- Packet and server-log data are only ever *offline* ground truth (Phases 1–3), never agent input
  (see `CLAUDE.md`).
- Clipboard and file transfer are human-only (ADR-0004).

## Maintenance

This is a **living document**. Any task that closes or materially advances an item here must update the
at-a-glance diagram, the status table and `last_reviewed` in the same change, not later.
