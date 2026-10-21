---
title: "Disk audit: poring-lab's footprint on the shared root disk"
status: living
created: 2026-10-21
last_reviewed: 2026-10-22
owner: poring-lab
---

# Disk audit: poring-lab's footprint on the shared root disk

**Rule (Batt, 2026-10-21):** long-term files live ONLY on the NAS. That covers datasets,
recordings, session evidence, model weights, caches not in active use, and archives. The local disk
holds only ACTIVE WORKING SETS, each with a retention note. Every report states our local disk
footprint (CLAUDE.md "How we work").

**How it is measured** (the disk carries live quant capture):
- `python3 scripts/guarded_build.py --sustain 30 --spike 25 measure:du=<path>` measures ONE path
  per step, with `nice -n 19 ionice -c3 du -s -x`. It runs only under our roots (the repo,
  `/home/batt/poring-lab-shm-archive`, `~/.cache/poring-lab`), under the IO guard; a trip kills it.
- `measure:docker-df` (`docker system df -v`) and `measure:buildx-du` (the lab builder, `default`).
- Not ours: never walked. Only `df` and what `docker system df -v` shows.

## Audit 1 -- 2026-10-21 20:34-20:42 ICT

The root LV holds 613.5 GiB, with **474.6 GiB used (81 %)** and 111.5 GiB free. Every measurement
step ran under the guard; the worst capture stall was 8.0 % (frigate), 0 s above 10 %.

### Ours, item by item (sizes in GB = 10^9 bytes, measured 20:34-20:42)

| # | path | size | what | last used | needed locally | NAS copy | action |
|---|---|---|---|---|---|---|---|
| 1 | `~/poring-lab-shm-archive/poring-lab-demo` | 2.88 | 37 old demo sessions (talk-cal, npc-click, ...) moved off /dev/shm 10-19 20:07 - 10-20 03:40, SYMLINKED back from `/dev/shm/poring-lab-demo` | 10-13 | no | no | **move** to the NAS datasets root (as sessions), verify, delete local, drop the symlinks |
| 2 | `~/poring-lab-shm-archive/poring-lab-tmp` | 1.09 | 35 scratch dirs, SYMLINKED back from `/dev/shm/poring-lab-tmp`. Some are still WRITTEN through the links (npc-check today; nametags by hunt_flow, ui-gate by ui_gate), so rule-7 scratch lands on the shared disk | today (via links) | the names in use: yes (as tmpfs) | no | **move** to `scratch-archive/`; each name code still uses becomes a REAL /dev/shm dir, refilled where code reads it (sprites, src, where, q1, ...) |
| 3 | `~/poring-lab-shm-archive/poring-lab-{kb,pktgen,rathena-src}` | 0.14 | stale copies; the live ones are real tmpfs dirs since option B (10-20) | 10-09 | no | no | **move** to `scratch-archive/` |
| 4 | `data/input_log` | 0.83 | the backend's input log, one JSONL per day since 09-29 | today | the last 2 days | no | **move** 09-29 .. 10-19 to the NAS; keep 2 days (retention: 2 days local) |
| 5 | `data/train` | 0.32 | training outputs v0 / v1 (10-04 .. 10-11) | 10-11 | read by species_check, gold_eval, train-day | no | **list**: Batt's call (weights + results -> NAS needs a path change) |
| 6 | `data/nametags` | 0.20 | nametag cuts written by every hunt run, plus templates.npz | today | writer: yes | no | **list**: propose cuts -> NAS with a retention |
| 7 | `data/metrics` | 0.06 | io_pressure CSVs (the IO baseline; not running since 10-12) | 10-12 | no | no | **move** |
| 8 | `data/{gat,bench,walk6,kb,weights,ro_agent,ui_anchors,...}` | 0.10 | active inputs (GAT, cursor refs, KB, detector weights, UI templates) | today | yes | - | keep |
| 9 | `.venv`, `.git`, sources | 0.51 | the env and the checkout | today | yes | - | keep |
| 10 | `services/frontend/node_modules` | 0.50 | a HOST pnpm install from 09-29. frontend-dev never copies it (run-dev.mjs SKIP); only gen_protocol.sh's first branch would use it, and its frontend-dev branch works | 09-29 | no | n/a (regenerable) | **list**: delete proposed (no NAS value), needs Batt's OK |
| 11 | `services/frontend/.qa-local` | 0.36 | the /qa label bundles (7 sessions, incl. Batt's hand-checked labels.json) | 10-05 | the /qa dev route + label_quality's default read it | no | **copy** to the NAS + verify now; the local delete waits on Batt (it breaks /qa until a NAS-backed path) |
| 12 | `.mypy_cache` | 0.02 | stale (mypy runs with `--cache-dir=/dev/null`) | ? | no | n/a | **list**: delete proposed |
| 13 | `~/.claude/projects/-home-batt-docker-poring-lab/<session>.jsonl` | 1.39 | THIS Claude session's transcript | live | yes while live | no | keep; propose a NAS archive after the session ends |
| 14 | `~/.cache/poring-lab` | 0.0002 | locale-pack fingerprints | today | yes | - | keep |
| 15 | Docker images (unique) | 12.29 | vision 10.34 (GPU work); gamestream 0.49; rathena-build 0.48 (0 containers); mariadb 0.34 (db, db-th); rathena 0.29; backend 0.24; sniffer 0.10. Plus ~0.86 desktop layers shared with gamestream, and base layers | images 2-3 weeks old | yes; rathena-build too (21:4x: `gen_packet_tables.py` and `gen_mapcache_th.py` run their throwaway containers from it) | - | keep |
| 16 | Docker volumes | 0.54 | captures 0.22 (the 7-day pcap ring); db-data 0.17; **db-th-data 0.16** (the Thai experiment; its container exited, the th client copy was removed) | - | db-th: no | no | keep; **list** db-th (dump to the NAS + remove = Batt's call) |
| 17 | Build cache (lab builder `default`) | ~10.3 records, **0.03 private** | the vision `uv sync` layer (9.52) etc. are SHARED with our images, so a prune frees ~nothing | 2 weeks | - | - | **not pruned** (a builder prune would also hit other projects' 3.15 GB private cache) |
| 18 | Dangling images | 0 ours | the 3 dangling images are fitfirst + tuya-energy-mqtt | - | - | - | not touched |
| 19 | Container logs | <= 0.27 | compose caps every service at 10 MB x 3 | - | - | - | bounded; not measurable without root |

**Total ours ≈ 23.0 GB** (21.4 GiB):
- repo 2.90;
- the shm archive 4.11;
- the transcript 1.39;
- Docker ≈ 14.6: images ~13.4 with their shared layers, volumes 0.54, build cache private 0.03, logs <= 0.27.

That is **≈ 4.5 % of the 474.6 GiB used**, and ≈ 3.5 % of the disk.

### Not ours (no walk; `df` + `docker system df -v` only)
- quant volumes: **95.98 GB**. crypto_cold_tier 48.52, orderbook_raw_log 33.54, orderbook_cold_tier
  6.40, ticker_raw_log 5.77, and the small ones.
- buildx `armbuilder` state volume: 19.34 GB (another project's arm64 builder; our builds use
  `default`).
- The dockerd build cache of other projects: ~16 GB of records, 3.15 GB of it private.
- Other images, unique layers: **47.42 GB** (frigate-blackwell tags 12.9, ollama 9.19, quant / candy /
  sec-archive / ... rollback tags).
- ollama volume 3.30 GB; other named volumes 0.65 GB.
- Anonymous volumes 1.51 GB: 13 with no labels; 2 are candy-closet-web's, 11 unattached (created
  08-21 .. 10-14).
- **Unattributed: roughly 290 GB.** It is outside Docker's view: bind-mounted project data, the
  system, other users' files. It was not walked, by rule.

### Growth vs earlier reports
- Root 76 % (10-19 06:40) -> 80 % (10-19 19:45) -> 79 % -> 81 % now (+5 points ≈ +30 GiB).
- **Ours in that time:**
  - the shm archive, +4.11 GB, moved onto the disk 10-19 20:07 - 10-20 03:40. That was my own
    cleanup putting /dev/shm overflow on the shared disk instead of the NAS, the exact thing the
    new rule forbids.
  - input_log +0.24 GB (10-19 .. 10-21);
  - the session transcript growing.
- Not ours: our images and build cache are 2-3 weeks old. The 10-19 06:40 -> 19:45 jump (+4
  points ≈ +25 GiB in 13 h) is NOT ours: we wrote < 0.5 GB that day. The newest images on the disk
  are other projects' (candy-closet 19-29 h old, m3u8 2 days, fitfirst 3-5 days, csm-set 7 days).

## Actions (audit 1)

Each move was a paced rsync (20 MB/s) to the NAS under the guard, then a size+count verification
(`rsync -n --itemize-changes` lists nothing; its positive case: a missing file and a changed size are
both listed), then the local delete under the guard.

| when (ICT) | what | to (NAS, `/mnt/poring-lab-datasets/`) | items | result |
|---|---|---|---|---|
| 20:45:46 | `poring-lab-kb` (stale copy) | `scratch-archive/2026-10-20-shm-archive/` | 1 | verified + deleted (the step's live positive case) |
| 20:47-20:55 | the 37 archived demo sessions | the datasets root `<sid>/` (36), `scratch-archive/.../poring-lab-demo/` (1: `20261010T001818-demo-npc-click-click-prontera` already exists on the NAS in a DIFFERENT version, 162 differing entries; never overwritten, so both are kept) | 37 | all verified + deleted; worst stall 14.0 %, 6 s above 10 % |
| 20:55-21:04 | the 35 archived scratch dirs + `pktgen` + `rathena-src` | `scratch-archive/2026-10-20-shm-archive/` | 37 | all verified + deleted; worst stall 6.8 % |
| 21:04 | the /dev/shm symlinks into the archive | - | 72 | the 37 session links removed. Of the 35 scratch links: the 12 names code still writes or reads became REAL tmpfs dirs (refilled: sprites, labels-prep, walk5-cal's no-entry mask); 23 were dropped |
| 21:05 | MANIFEST.tsv + move.log | `scratch-archive/2026-10-20-shm-archive/` | 2 | verified + deleted; `~/poring-lab-shm-archive` removed (empty) |
| 21:05-21:10 | `data/input_log` 09-29 .. 10-19 (20 days), `data/metrics` (5 CSVs), `services/frontend/.qa-local` (7 bundles + index.json) | `archive/input_log/`, `archive/metrics/`, `archive/qa-bundles/` | 33 | all verified + deleted; worst stall **21.5 % on capture-streaming-pro, 6 s above 10 %** (inside the guard's limits; later moves get a lower pace) |

- **Not done, listed for Batt:**
  - `services/frontend/node_modules` (0.50 GB, regenerable, unused);
  - `.mypy_cache` (0.02);
  - `data/train` (0.32);
  - `data/nametags` (0.20);
  - the `db-th-data` volume + its exited container (0.16);
  - the session transcript (1.39, live).
- **Docker prune:** none. Our build-cache records share their bytes with our images (private
  0.03 GB), and no dangling image is ours.
- **To read a moved item:** `/mnt/poring-lab-datasets/archive/...`. `label_quality.py --bundles
  /mnt/poring-lab-datasets/archive/qa-bundles`; the /qa page shows no bundle until one is
  re-exported (`qa_export.py`) or copied back for a session.

### After (21:10 ICT)

| | before (20:34) | after (21:10) |
|---|---|---|
| root LV used | 474.6 GiB (81 %) | **464.8 GiB (80 %)**; ours moved ≈ 4.9 GiB of the 9.8 GiB drop, the other ≈ 4.9 GiB was freed by something not ours |
| repo `data/` | 1.51 GB | 0.73 GB |
| repo `services/` | 0.87 GB | 0.50 GB (node_modules, listed) |
| `~/poring-lab-shm-archive` | 4.11 GB | gone |
| ours in total | ≈ 23.0 GB (≈ 4.5 % of used) | **≈ 17.7 GB (≈ 3.5 % of the 464.8 GiB used; Docker ≈ 14.6 of it, the vision image 10.3)** |

## Check -- 2026-10-22 04:44 ICT (end of the overnight; no moves)

| | 21:10 (after audit 1) | 04:44 |
|---|---|---|
| root LV used | 464.8 GiB (80 %) | **468.9 GiB** (80 %), 117.2 GiB free |
| ours in total | ≈ 17.7 GB | **≈ 17.8 GB** (≈ 3.5 % of used) |
| repo `data/` (`measure:du`, 0.0 % stall) | 0.73 GB | 0.78 GB (today's input log; the nametag cuts of 4 hunt runs) |
| the session transcript | 1.39 GB | 1.42 GB |
| /dev/shm (ours, RAM) | ≈ 2.3 GB | 1.83 GB (the CPU detector 1.54) |

- **+4.1 GiB in 7.5 h, NOT ours** (ours ≈ +0.1 GB; no build, no pull). `measure:docker-df` at
  04:46 (worst stall 4.6 %): every quant volume at its 20:34 size (crypto_cold_tier 48.52,
  orderbook_raw_log 33.54, ticker_raw_log 5.77 GB) and no new image. So the growth is outside
  Docker's view (bind-mounted data, the system, other users). Not walked, by rule.
  - One candidate, unverified: candy-closet's restic offsite-backup container (up 10 h at 04:46).
- **Rate:** ≈ 13 GiB/day, the same as 10-19 -> 10-21 (+30 GiB in 2.6 days). At 117.2 GiB free that
  is ≈ 9-10 days to full. Raised to Batt (the 2026-10-22 06:00 report).
- Tonight's finished scratch went to `scratch-archive/2026-10-22/poring-lab-tmp/`; the 4 v55
  sessions to the datasets root (`dataset_ship.py ship`, re-hashed on the NAS).
