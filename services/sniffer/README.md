# sniffer

**Implemented (ADR-0007, 2026-10-01); the slim image since 2026-10-03.** `Dockerfile` here builds
from the repo root (uv workspace, like the backend): Python + pydantic + websockets +
`poring_packets`, 71 MB. The length table (`_generated/lengths.json`, generated from pinned sources,
never committed) ships inside the wheel (hatch `artifacts`), and the build REFUSES an image whose
table is missing or differs from `tables.lock.json`.

    scripts/gen_packet_tables.py                                            # the table, before a build
    python3 scripts/guarded_build.py --sustain 30 --spike 25 build:sniffer recreate:sniffer@90

After every sniffer restart, relog the validation (GM) account: a running session's identity is
not recoverable mid-stream (docs/phase1-validation.md, limitation 1).

## What it does

- **Capture.** Passive capture of the lab client's game traffic: an AF_PACKET socket with a
  committed BPF filter (`host 192.168.1.169 and tcp and port 6900/6121/5121`) and kernel
  timestamps (`SO_TIMESTAMPNS`). It runs in rathena's network namespace.
- **pcapng.** Written to the `captures` volume, never `./data`.
  - CA_LOGIN passwords: the client → login payload is zeroed after its packet id.
  - A custom block records the realtime → CLOCK_MONOTONIC mapping every second.
  - Rotated hourly or at 256 MB; retention is 7 days or 20 GB.
- **Events.** Decoded first-slice events (`poring_packets.events`) go to `events-*.jsonl.gz` in the
  same volume, and to the backend's `/ingest/packets`, which feeds the console's "Packet timeline"
  panel (`/ws/packets`, LAN viewers only).
- **Validation tagging.** Sessions of the validation (GM) account are tagged `validation_account`,
  and GM commands plus their replies `gm_command`, so both can be excluded from datasets.

## Rules

- **Offline ground truth and a human view only.** No packet data reaches the agent: the agent
  schemas cannot carry it; vision has neither the package nor the volume; vision's code may not
  mention it. Tests in `test_guards.py` and `test_protocol.py` pin all three.
- **Passive only**: no injection, no modification, no replay against the server.
- Captures carry session tokens: they never leave the host and are never committed.

Validation results: [docs/phase1-validation.md](../../docs/phase1-validation.md).
