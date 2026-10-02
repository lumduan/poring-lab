---
doc_type: decision
hypothesis: null
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: []
next_action: Batt picks the persistent sink (data-disk under the IO guard vs a TrueNAS share) before any recording longer than the calibration run; then ACCEPT after the first labelled session passes the QA check.
---

# ADR-0010: Phase 2 dataset format -- WebDataset tar shards of lossless frames + packet ground truth

- **Status:** PROPOSED (2026-10-02). The format is implemented in `packages/poring_dataset`. The
  storage location is **open** (decision 4).
- **Related:**
  - [ADR-0007](0007-packet-ground-truth-channel.md): packets are offline ground truth only;
  - [ADR-0009](0009-console-session-capture.md): sessions are tagged with their capture backend;
  - [ADR-0005](0005-vision-x-access.md): what vision may read;
  - the plan is [phase2-plan.md](../phase2-plan.md).

## Context

Phase 2 needs recorded sessions:
- frames as the capture path delivered them, with their host-clock timestamps;
- the packet events of the same time window;
- then labels projected from those events (auto-labeling).

Three constraints shape the format:

1. **The disk is shared with live capture** (CLAUDE.md rule 5).
   - A lossless 784×625 frame is ~0.7–1 MB as fast PNG.
     ➡️ **Measured 2026-10-02 at the frozen 1280×720:** about 1.84 MB per frame. The calibration session
     wrote **489 MB/min (~29 GB/h)** at an effective 4.4 fps. That number sizes decision 4 (the sink).
   - At 30 fps that is ~25–90 GB per hour of writes: the disk-IO pattern that has stalled quant
     capture before.
   - Thousands of small files are worse still (metadata IO).
2. **Labels are derived from packets.** They are training data, never decision-time input
   (ADR-0007).
   - `./data` is mounted read-write into **vision** (`compose.yaml`).
   - So datasets must not live there, or the live agent could read packet-derived positions.
3. **Backend-agnostic.** RDP and console (Sunshine) sessions must be comparable. Every session
   records its backend and config hash, and its latency offset comes from the benchmark
   (docs/benchmarks/SPEC.md).

## Decision (proposed)

1. **Session = a directory of WebDataset-style tar shards** (`poring_dataset.shards`):
   - `shard-NNNNNN.tar` (≤ 256 MiB each). Per frame:
     - `<frame_id>.png`: **lossless** pixels of `GAME_REGION`, exactly what the capture path
       delivered;
     - `<frame_id>.json`: `{frame_id, t_mono_ns, t_wall}`;
     - later `<frame_id>.txt` (YOLO labels).
   - `manifest.json`: session id, `backend`, `config_hash` + config, game region, fps cap, shards,
     t0/t1, recorder version.
   - `packets.jsonl.gz`: the sniffer's events for [t0 − 5 s, t1 + 5 s], **pseudonymised**: names
     and chat text of anyone other than the lab accounts replaced by stable hashes (CLAUDE.md
     rule 9).
2. **Frames are capped, not continuous.** The recorder grabs on damage, capped at **10 fps** by
   default; it is the labels' rate, not the game's. An IO guard pauses and aborts on a quant
   io_full breach, the process writes at `ionice -c3`, and a size cap applies (2 GiB by default).
3. **Labels are YOLO txt inside the shards.** Classes v0: player, monster, npc. Boxes hang from the
   projected foot point with per-class sizes refined on the hand-checked set. The GM's own hidden
   character and every GM-command window are excluded.
4. **Storage: OPEN, Batt decides before any long recording.**
   - **Now:** `/dev/shm/poring-lab-rec/` (RAM) for the calibration run only.
   - **Candidates:**

     | Option | For | Against |
     |---|---|---|
     | **a.** A gitignored `datasets/` dir **outside** `./data` | Simple | It is on the shared disk: needs the IO guard, a rate cap and ionice; nothing new is mounted into vision |
     | **b.** A **TrueNAS share** mounted on the Docker host | Off the shared disk entirely; snapshots | Network IO; needs the share (Batt's infra) |

   - **Never** under `./data` (vision mounts it).
5. **Never committed**: shards, frames and packet copies are like captures (rule 4); only the code
   and the manifest schema are.

## Consequences

- One format for every capture backend. Comparing labelled RDP and console sessions is a matter of
  the manifest's backend and config hash.
- Lossless frames are big: sampling (10 fps) and the size cap are part of the format, not
  afterthoughts. The calibration run measures MB per minute.
- Pseudonymisation is applied at recording time, so a shard can be shared without leaking other
  players' identities. Only the lab's own accounts stay named.
