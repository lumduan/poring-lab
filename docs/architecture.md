# Architecture

<!-- Moved from the root README on 2026-11-13 (Batt: "the README only for setup; the rest in docs/"). -->

## Topology

```
 Windows game PC                                  Linux Docker host (HOST_LAN_IP)    
┌────────────────────────────────┐               ┌────────────────────────────────────────────────────────────────┐
│ ONE interactive session        │   RDP :3389   │ desktop   xfreerdp3 /size (no WM) ─► Xvfb :99 canvas 1920x1200 │
│   └─ RO client                 │ ◄──────────── │           x11vnc (view-only) ──► noVNC :6080                   │
│        │                       │  exactly one  │                                     │ /tmp/.X11-unix (volume)  │
│        │ game traffic          │               │              ┌──────────────────────┴────┐                     │
│        │ 6900 / 6121 / 5121    │               │              ▼ grab (ro)                 ▼ grab (ro)           │
│        └────────────────────── │ ──────────►   │ rathena      backend :8000               vision (GPU)          │
│                                │               │  login       JPEG stream                 grab → infer →        │
│                                │               │  char        INPUT MUX ◄─────────────    decide → act          │
│                                │               │  map          └─► XTest                  (:8001, internal)     │
│                                │               │   │          (the only input writer)                           │
│                                │               │   ▼          ▲ /ws/input   │ /ws/stream                        │
│                                │               │  db          │             ▼                                   │
│                                │               │              frontend :3000 ◄──► your browser                  │
│                                │               │  sniffer (ADR-0007, rathena's netns) ─► captures + /ingest     │
└────────────────────────────────┘               └────────────────────────────────────────────────────────────────┘
```

- Pixels flow Windows → RDP → `xfreerdp3` → Xvfb framebuffer, and `backend` grabs them for the
  browser stream. Input flows browser/agent → **backend mux** → XTest → Xvfb → `xfreerdp3` → RDP →
  Windows. The mux is the only writer (ADR-0002).
- **The bot's path is S2** (ADR-0014; the diagram above predates it): Sunshine on the Windows
  console → the `gamestream` S2 client decodes once → the shared-memory **frame bus** → backend
  (human view) and **vision** (the bot). The mux's input goes to the S2 client over a unix socket.
- **vision has no X at all** (ADR-0005 closed, option c2, 2026-10-04):
  - no `x11-unix` mount; it reads the bus only;
  - it lives ONLY on the internal `agent` network (`10.210.97.0/24`, `internal: true`, gateway
    isolated), shared with the backend alone;
  - the backend refuses that subnet on every listener but `:8001`. So the bot's one way in is
    `/internal/agent` → the mux, and it can reach neither the LAN, the host nor the internet.
- **Datasets** (ADR-0010, ADR-0024): `scripts/record_session.py` records H.264 by default on
  console (the S2 client's own bitstream, an IDR every 1 s, ~2.5 GB/h; Batt 2026-10-04) and, on
  rdp, GPU-encoded HEVC video (`vpp-hevc444-10-q20`: 10-bit 4:4:4, CQP 20, all-intra, lossy;
  ~0.84 GB/h at 1 fps; Batt 2026-11-09) through the `media-rec` sidecar, which must be up
  (`guarded_build.py start:media-rec@60`; without it the recording is refused). Lossless PNG
  stays selectable (`--format png --fps 1`, either backend) and is required by the studies that
  fit pixel cues. `scripts/dataset_ship.py ship` moves sessions to the NAS;
  `scripts/dataset_check.py` then verifies every H.264 frame against the live checksums, or decodes
  every video frame alone; `poring_dataset.h264` reads H.264 and `poring_dataset.frames` reads PNG
  and video sessions for every other reader (`scripts/qa_export.py` reads all three).
- **The environment interlock** (ADR-0016) gates the mux's BOT presses:
  - the environments are user-managed on the Settings page (seeded once from
    `config/environments.yaml`);
  - the sniffer's attestation must say a lab account's session is live;
  - or, in ASSIST only, a bounded operator window is open (`scripts/capture_backend.py window`).

  `/health.environment` shows its state.
