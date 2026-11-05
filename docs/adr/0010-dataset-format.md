---
doc_type: decision
hypothesis: null
status: GO
role: null
verdict_date: 2026-10-02
verdict_ticket: null
supersedes: null
related: []
next_action: H.264 (IDR 1 s) is the default since 2026-10-04 (Batt). Record console sessions as H.264, ship them, run scripts/dataset_check.py on the NAS copy; keep benchmark/hand-labelled sessions pinned.
---

# ADR-0010: Phase 2 dataset format -- WebDataset tar shards of lossless frames + packet ground truth

- **Status:** ➡️ **ACCEPTED 2026-10-02 21:06** (was PROPOSED the same day). The format is
  implemented in `packages/poring_dataset`. The storage location (decision 4), decided by Batt the
  same day: record to the VM's local disk, then ship to TrueNAS cold storage (see "Implementation").
  **Acceptance evidence:**
  - the NAS is set up per `docs/operations/nas-sink.md`;
  - a 30 s recording (`20261002T210604-rdp-ship-test`: 204 frames, 140.7 MB, 2 files) was shipped
    (sha256 → rsync → NAS re-hash → manifest `storage` → `INDEX.jsonl` → local copy deleted);
  - a NAS-side `sha256sum -c` also passes;
  - quant-postgres io_full 3.0 → 3.7 % (record) and 3.9 → 2.6 % (ship), 5 min before vs after.
- **Related:**
  - [ADR-0007](0007-packet-ground-truth-channel.md): packets are offline ground truth only;
  - [ADR-0009](0009-console-session-capture.md): sessions are tagged with their capture backend;
  - [ADR-0005](0005-vision-x-access.md): what vision may read;
  - the plan is [phase2-plan.md](../phase2-plan.md).

> ➡️ **Note 2026-10-04 (Batt, recording rate on the shared disk):** S2 sessions at a 10 fps target
> wrote ~9 MB/s of lossless PNG and tripped the recorder's quant IO guard within 2 min. A
> 1280×720 frame is ~2.1 MB at any zlib level. Batt's decision: record at **fps 1** under the armed
> guard (~2.1 MB/s, ~7 GB/h); anything faster is his call per window. The sink and format are
> unchanged. Results: [phase2-plan.md](../phase2-plan.md) "S2 datasets".

> ➡️ **Note 2026-10-04, later (Batt, C4): the DEFAULT FORMAT is now raw H.264 with an IDR every
> 1 s.** On console, `record_session.py` keeps the S2 client's own bitstream instead of PNG frames.
> PNG shards (above) stay selectable (`--format png --fps 1`) and remain the format on rdp.
>
> **Layout.** A session dir holds `stream.h264` (the Annex-B access units as the live client
> decoded them), `stream.idx.csv` (one row per access unit: bus frame_id, IDR flag, offset,
> length, decode-complete time) and `stream.hash.csv` (a crc32+adler32 per decoded frame), plus
> `stream.done.json` (the recorder's summary, incl. the decoder build), `packets.jsonl.gz` and
> `manifest.json` (`format: h264`, `idr_every_s`, freeze spans).
>
> **Rates** (C3, [h264-vs-png.md](../benchmarks/h264-vs-png.md)): 32–48 MB/min keeping EVERY
> frame (~30/s). At IDR 1 s that is 40.7 MB/min ≈ **2.5 GB/h**, against PNG fps 1 at
> 124 MB/min ≈ 7.5 GB/h for 1 frame/s. The worst case is the bitrate cap, 20 Mb/s = 150 MB/min.
>
> **Headroom.** The free-space floor stays 140 GB (Batt): with 152 GB free that is 12 GB, about
> **5 h of H.264 per session before shipping**. The 20 GB unshipped cap alone would allow ~8 h.
> ➡️ SUPERSEDED 2026-11-05: the floor is **120 GB** (Batt; see "Amendment 2026-11-05" below).
>
> **Determinism.** The bitstream is the dataset only while decoding is bit-identical.
> - `scripts/dataset_check.py` decodes every frame on the HOST after shipping and compares each
>   checksum with the live client's.
> - The host's PyAV is the gamestream image's exact wheel (19.0.1, libavcodec 63.1.102).
> - The 5 C3 sessions gave 27,910 / 27,910 identical frames.
> - The reader refuses another decoder build.
>
> **Reading.** `poring_dataset.h264.H264Session` decodes by GOP, verifies each frame and skips
> freeze spans. Random access costs ~200–300 ms per frame on this host (offline seek, h264-vs-png),
> so training reads a frame cache built in one pass per session (Phase 3 plan).
>
> ➡️ **Note 2026-10-04, evening (Batt, Phase 3 decision 4): the TRAINING FRAME CACHE.**
> - Vision reads the NAS **read-only**, and a frame cache is **sharded** (large files), never one
>   file per frame on the shared disk.
> - `scripts/build_frame_cache.py` (host) decodes each session in ONE sequential pass
>   (`H264Session.iter_every`) and keeps every 15th usable frame (~2 fps).
> - It writes ~512 MB tar shards (`<key>.jpg` q95 + `<key>.txt` YOLO + `<key>.json`) to
>   `/mnt/poring-lab-datasets/.framecache/<cache_id>/`, with `manifest.json` (shard sha256s, read
>   back from the NAS) and `split.json`, split BY SESSION; the hand-checked gold session is test
>   only.
> - The dot-directory is invisible to `dataset_ship` (sessions/status/prune skip it).
> - Vision mounts the export through a soft, read-only NFS volume (`compose.yaml` `datasets-nas` →
>   `/datasets:ro`, vision only, test_guards) and reads the shards in place
>   (`poring_vision.shards`).
>
> ➡️ **Note 2026-10-04, night: SIDECARS.** A shipped session may gain a re-derived file without
> touching what was verified. `dataset_ship.add_sidecar`:
> - only `packets.<kind>.jsonl.gz`;
> - copied as `.part`, re-hashed on the NAS, renamed;
> - its line joins `checksums.sha256`, and INDEX.jsonl gets a `sidecar` event;
> - never replaced.
>
> The first is `packets.states.jsonl.gz` (Phase 3 M3: the act/turn decoders, replayed from the
> banked captures by `scripts/replay_states.py`).

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
4. **Storage: OPEN, Batt decides before any long recording.** ➡️ **DECIDED 2026-10-02 (Batt):**
   local disk as a capped buffer, then TrueNAS cold storage -- option b with a local stage. See
   "Implementation (2026-10-02)". The rest of this item is kept as the history of the choice.
   - **Now:** `/dev/shm/poring-lab-rec/` (RAM) for the calibration run only. ➡️ No longer the
     default: `record_session.py` now writes to `/home/batt/poring-lab-rec`.
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

## Implementation (2026-10-02)

Batt's decision: record to the VM's local disk, then move to TrueNAS cold storage.

```
record_session.py ──► /home/batt/poring-lab-rec/<session>/ ──► dataset_ship.py ship ──► NAS
 (local disk, capped buffer)                       sha256 → rsync → re-hash → manifest → INDEX → delete local
```

**Local root:** `/home/batt/poring-lab-rec`, `record_session.py`'s default `--out`.
- It is on the disk shared with live capture, never `./data` (vision mounts it), never `/dev/shm`.
- A **buffer, capped** (`dataset_ship.local_caps`). Recording **refuses to start**, and **stops
  cleanly** mid-run (`stop_reason: local_cap: …`, re-checked every 5 s), when either:
  - the filesystem has **< 120 GB free** (`--min-free-gb`; 140 GB until 2026-11-05, see the
    amendment below);
  - **> 20 GB** of sessions wait under the root, unshipped (`--max-unshipped-gb`). 20 GB is about
    40 min at the measured 489 MB/min.
- The quant IO guard, `ionice -c3` and the per-session size cap are unchanged.
- During SET hours (09:30–17:00 Bangkok, weekdays) it warns, and the guard stays armed.
- The manifest records the sink: `sink: {root, min_free, max_unshipped}`.

**Ship** (`scripts/dataset_ship.py ship`). Only finished sessions (a `manifest.json`, which is
written last) are shipped, one session at a time, in this order:

1. sha256 of every file except the manifest → `checksums.sha256` (sha256sum format);
2. `rsync -a --partial --timeout=60 --bwlimit=40000` (~40 MB/s) at `ionice -c3`. The quant IO guard
   stops it on a breach, and a re-run resumes;
3. **re-hash on the NAS**: every file must match, and the checksum file and manifest must arrive
   byte-identical;
4. the NAS manifest gets `storage: {nas_path, verified_at, files, bytes, checksums_sha256}`;
5. one line is appended to `INDEX.jsonl` at the NAS root;
6. **only then** is the local copy deleted.

Any failure before step 6 keeps the local copy and leaves the NAS manifest without `storage`.

**Refusals:**
- during SET hours, unless `--force-market`;
- when the NAS root is **not a mounted filesystem**: an NFS outage must never fill the empty
  mount-point directory on the shared disk;
- a second concurrent `ship` (a lock file).

**Why the manifest is excluded from `checksums.sha256`:** step 4 rewrites it. Instead it is
compared byte-for-byte in step 3, and `storage.checksums_sha256` chains it to the data files.

**NAS layout:** `/mnt/poring-lab-datasets` = `tank-main/poring-lab/datasets`
(`docs/operations/nas-sink.md`).
- `<session_id>/`: the session as recorded, plus `checksums.sha256`, and an optional `pin`;
- `INDEX.jsonl`: where each session lives. One JSON line per event, `shipped` / `pinned` /
  `pruned`, with its time and path.
- Host-side only: never bind-mounted into a container.

**Retention:**
- The NAS keeps sessions **365 days**, counted from the session id's timestamp.
- `dataset_ship.py prune` is a **dry run** unless `--apply`.
- **Pinned** sessions are kept indefinitely: benchmark evidence, hand-labelled sets. Pin with
  `dataset_ship.py pin <id> --reason …`, which writes `pin`.
- Optional: a daily TrueNAS snapshot of `datasets`, kept 14 days, guards against a mistaken prune.
- The TrueNAS quota alert stays at its default 80 % of the 2 TiB quota.

**`dataset_ship.py status`:** one line per session:
- local: `unshipped` or `recording/incomplete`;
- NAS: `verified <time>` or `UNVERIFIED`, with `pinned` shown.

It ends with the local totals against both caps and whether the NAS is mounted.

**Tests:** `services/backend/tests/test_dataset_ship.py`, using real rsync between two tmp dirs.
They cover:
- ship → verify → delete, in that order;
- a corrupted NAS copy or a failed rsync keeps the local copy;
- the SET-hours refusal and its boundaries;
- an unmounted or missing NAS refuses;
- an unfinished recording is never shipped;
- prune is a dry run by default, honours pins and `--older-than`;
- the caps;
- `record_session` refuses before opening the screen when a cap is hit.

**Verified live 2026-10-02 21:06:** the 30 s round-trip in `nas-sink.md` section 6 passed (see Status).

## Amendment 2026-11-05: the free-space floor is 120 GB (Batt)

- **Decision (Batt, 2026-11-05 ~19:0x ICT):** `dataset_ship.MIN_FREE_BYTES` goes from 140 GB to
  **120 GB**. Recording still refuses to start, and stops cleanly mid-run, below the floor; the
  20 GB unshipped cap, the IO guard and shipping after each session are unchanged.
- **Why it came up:** the xmas_dun02 X2 recording (docs/planning/rogue-xmas02.md, Amendment B) was
  refused at 134 GB free. The disk's other tenants take it down by about 0.9-1.4 GB/h on
  2026-11-05 evening (HA's and our `df` readings), so freeing images alone (at most ~10 GB that
  night, HA) would not have stayed above 140 GB.
- **The sizes the decision used** (NAS manifests, 25 RDP PNG sessions, 2026-10-25..10-29):
  - 1 frame/s, PNG level 1, 1280 x 720: **7.0-8.4 GB per hour** (120-140 MB/min);
  - 2 frames/s: about 16 GB per hour;
  - H.264 at IDR 1 s (this ADR's rates): about 2.5 GB per hour.
  A session lives on the root disk only until it is shipped and verified, then it is deleted.

