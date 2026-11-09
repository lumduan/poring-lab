---
doc_type: design
hypothesis: "From pixels alone, the Orc Lord's CPU recognizer recipe (scripts/mvp_watch.py: the boss AURA rule + the party window detector), refitted on xmas_dun02, tells 'the Stormy Knight (1251) or its summons (Garm Baby 1515, Christmas Goblin 1607) are in view' within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of hunting frames, at <= 60 ms p95 per frame -- enough for a Fly Wing at first sight."
status: "PROPOSED 2026-11-09 (Batt's Amendment L 2, rogue-xmas02.md 4AK). The split and bars are pre-registered in section 3 BEFORE any data exists. Section 1's look (07:51) is one live peek, no data set."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, orclord-recognizer.md, xmas02-detector.md, gpu-recording.md, ../adr/0024-gpu-video-recordings.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py, ../../scripts/stage_items.py, ../../scripts/watch_lattice.py]
next_action: "B1 (offline code): mvp_watch_study per boss (the Orc Lord unchanged, the Stormy Knight added). B2 (live): the immune watch on xmas_dun02 + a PNG hunting recording. Then B3 (fit on DEV, score HELD-OUT once) and the flee rule's own pre-registration."
title: "A Stormy Knight recognizer for the Rogue's flee rule on xmas_dun02 (pixels only, CPU; the Orc Lord's recipe refitted)"
date: 2026-11-09
owner: Batt
---

# A Stormy Knight recognizer for the Rogue's flee rule on xmas_dun02

**Why** (Batt, 2026-11-09 ~06:3x, rogue-xmas02.md Amendment L 2): "do not disable the MVP; train
the bot to know the boss: seen on the screen -> Fly Wing away at once". The Stormy Knight killed the
Rogue in p18 (2026-11-08 23:16:52-54: 1,170 then 5,912 damage 0.4 s apart, her HP 5,070); the
reactive Battle Log guard (`boss_of`) cannot beat two hits 0.4 s apart. The runner needs, from
PIXELS ONLY at decision time, "the Stormy Knight or its party is in view", as early as possible.
Packets are offline ground truth only (ADR-0007).

**The caution carried over** ([orclord-recognizer.md](orclord-recognizer.md) 12-13): the Orc
Lord's recognizer passed its offline bars, but its LIVE flee proof did not: the Lord could hit
0.97 s after entering view and the aura did not fire in time; the sight-flee was NOT adopted.
So until a Stormy Knight flee proof passes, Amendment K's schedule (`@mobsearch` +
`@killmonster2` before each run, 25-min pilots in the dead window) stays the protection.

## 1. What is known (before any data)

- The party: Stormy Knight (1251, MVP, sprite box ~141 x 133 px, aggressive), its summons Garm
  Baby (1515, ALSO a regular 30-min spawn on this map) and Christmas Goblin (1607, summons only)
  (xmas02-detector.md 1b). `dungeon_hunt.boss_names` already names all three for the boss guard.
- **The live peek (2026-11-09 07:51:45-07:52:5x, the Rogue immune, `@warp xmas_dun02 241 207` onto
  its `@mobsearch` cell; three game-region frames ~1 s apart, kept on the NAS, never committed):**
  - the Knight: a large red-caped figure with ice-white shoulder spikes, ~150 px tall;
  - its party around it: 2 Garm Babies (white, wolf-like) and ~5 Christmas Goblins (orange caps);
  - a green-yellow glow at the Knight's feet in both stills (the boss effect the Orc Lord's AURA
    rule reads: G >= 236, G - R >= 25, G - B >= 25 there) -- to be measured on the watch, not
    assumed;
  - a dark "!!" emotion box above every party member; one frame showed a large white lightning
    burst (a skill) over the party.
- xmas_dun02's floor is orange / tan / teal tiles; saturated bright green is not expected on it
  (to be measured on the hunting negatives).

## 2. The plan

- **B1 (offline code, no live step):** `mvp_watch_study.py` per BOSS: the party ids, the names,
  the map and the negative species become a profile (`orclord` = today's values, its tests
  unchanged; `stormy` = 1251 + 1515 + 1607 on xmas_dun02, negatives Myst Case / Cruiser / Cookie
  / Christmas Cookie). `mvp_watch.py`'s model file names its profile; the runner loads the map's.
- **B2 (live data, immune, the lab server only):**
  - the WATCH: `watch_lattice.py` cells on xmas_dun02 (train + test lattices, the three-check
    stand cells), `stage_items.py watch --spawn 1251` (one Stormy Knight per cell beside the
    immune Rogue, a 40-s dwell, `@killmonster2`, the next cell), 16 cells; recorded at 1 fps with
    `--format png` (ADR-0024 decision 4: cue studies need PNG);
  - the HUNTING NEGATIVES: one 25-min explore run on the base recorded with `--format png`, the
    MVP dead by the schedule (its own pilot label; the run's other bars as 4AL's).
- **B3:** the truth (`mvp_watch_study.py truth`, the projection of the label pipeline with
  xmas_dun02's GAT), the fit on DEV, the score on HELD-OUT once (section 3).
- **B4 (after B3 passes):** the flee rule in the runner (`seen` -> Fly Wing at once, every ~0.5 s,
  beside the reactive boss guard) and its LIVE proof, pre-registered on its own: spawned Knights
  with immunity OFF, a heal at every trial start, stop after a near-death -- section 13's lessons.

## 3. PRE-REGISTERED: the split, the scores and the bars (2026-11-09, BEFORE any data)

The Orc Lord's section 3 rules, unchanged except the boss and the map:
- **The split (by lattice cell, never by frame):** DEV = the watch's cells 0-7; HELD-OUT = cells
  8-15, scored ONCE with the frozen recognizer (its sha256 recorded). A watch frame belongs to the
  cell whose spawn precedes it. The hunting recording: its first 300 s on xmas_dun02 are DEV, the
  rest HELD-OUT.
- **Positive** = the decision's `seen`. **Episode** = frames with the Knight or a summon in view
  (the truth's rule), split where none is in view for > 3 s; a cell's first episode starts at its
  spawn. **Delay** = t(first positive of the cell's first episode) - t(the episode's first frame,
  the party's first frame -- the stricter start). **False positive** = a positive frame with no
  party box even partly on screen, per 10 min of frames.
- **Bars:** (1) recall within 1 s (delay <= 1.1 s) >= 95 % of the held-out cells (8 / 8);
  (2) false positives <= 1 per 10 min of the hunting recording's held-out frames; (3) latency p95
  <= 60 ms per 1280 x 720 frame, `nice -n 15`, one thread, >= 200 calls.
- A failed bar is reported plainly with what more data would fix it; nothing is refitted on
  HELD-OUT; a second attempt needs a second watch.
- **Garm Baby caveat (reported, not gating):** Garm Baby also spawns WITHOUT the Knight (its own
  30-min spawn). A positive on a lone Garm Baby counts as a true positive by the truth's rule
  (it is in the party list) -- and a flee from it costs one Fly Wing; its rate on the hunting
  recording is reported.
