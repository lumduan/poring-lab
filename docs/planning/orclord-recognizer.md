---
doc_type: design
hypothesis: "From pixels alone, a CPU recognizer cheap enough for the runner (<= 60 ms per 1280 x 720 frame, niced) tells 'the Orc Lord (mob 1190) or its Orc Archers (1189 / 1473) are in view' on gef_fild10 within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of held-out hunting frames."
status: "PRE-REGISTERED 2026-10-25 20:20 ICT (from `date`), BEFORE any recognizer exists and before any held-out cell is scored. Offline only (no client, no GPU, no input)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, payf07-detector.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py]
next_action: "This branch: build the recognizer on the DEV cells, freeze it, then score the HELD-OUT cells once (section 3)."
title: "An Orc Lord recognizer for the Rogue's flee rule on gef_fild10 (pixels only, CPU, scored offline on held-out lattice cells)"
date: 2026-10-25
owner: Batt
---

# An Orc Lord recognizer for the Rogue's flee rule on gef_fild10

**Why** ([rogue-gef10.md](rogue-gef10.md) Amendment A4, Batt 2026-10-25: "run away; you may try
spawning it first"). The Orc Lord cannot be outrun on foot ([gef10-prep.md](gef10-prep.md) 1c):
the escape is a Fly Wing at FIRST SIGHT. The runner (`scripts/dungeon_hunt.py`, dungeon@8) needs,
from PIXELS ONLY at decision time, "the Orc Lord, or its Orc Archers (which only it brings on this
map), is in view", as early as possible. Packets are offline ground truth only (ADR-0007).

## 1. The data (read before this section was written)

- **The watch** `20261025T195327-watch-gef_fild10-ow1` (stage_items.py watch --spawn 1190,
  19:53-20:08 ICT, the Rogue IMMUNE): 15 lattice cells i = 0..14; at each, `@monster 1190 1` near the
  Rogue, a 40-s dwell, then `@killmonster2`, then the warp to the next cell (~12 s later).
  - Its recording `20261025T195325-rdp-ow1`: 835 PNG frames at 1 fps (median spacing 1.005 s,
    p95 1.034 s), 3,312 packet events, the "standard" client layout (4-row bar, Basic Info
    expanded).
  - Every `@monster 1190` brought **5 Orc Archers (1189)** in the same packet burst: 15 Orc Lords,
    75 archers.
- **The hunting pilot** `20261025T200925-demo-dungeon-rogue-gef_fild10-B-pilot` (the Rogue NOT
  immune, 15 min, its setup's `@killmonster2` first: no Orc Lord in it). Its recording
  `20261025T200922-rdp-rogue-pilot` (the "hunt" layout) gives the hunting negatives.
- **What was looked at before this pre-registration** (none of it fitted anything):
  - the per-frame truth's counts over the whole watch (section 2);
  - three overlay frames (frame ids 20, 100, 140: cells 0, 1, 2);
  - crop galleries sampled across ALL 15 cells: 32 Orc Lord, 24 Orc Warrior and 16 Orc Lady crops.
    They showed what the plan did not know: **the client draws a bright green aura ring at the Orc
    Lord's feet** (its boss/MVP effect; hue ~93 deg, saturation ~0.55, value 0.8-1.0), and tree
    canopies hide the Orc Lord on some frames.

## 2. The truth (from the packets; `scripts/mvp_watch_study.py truth`)

- The label pipeline's projection, unchanged (payf07-detector.md 4-5): the fitted RDP camera with
  gef_fild10's client GAT altitude; `predict_sprite`'s box for each unit's Timeline state, facing
  and the decoded sprite (gef10-prep 9); payf07's frozen 1d = 120 ms and k = 0.14.
- **In view** = labels_for_v1's rule: at least half the box on screen, under half of it behind the
  layout's UI windows (`client_layout.RECTS`). RSW models (trees, houses) are NOT modelled: a unit
  under a canopy counts as in view (a known limit; it makes the recall bar harder, not easier).
- Counts on the watch (828 of 835 frames on gef_fild10): Orc Lord in view on 511 frames, an Orc
  Archer on 555, the party (either) on 561; other species in view: Orc Lady 237 frames, Poporing
  97, Orc Warrior 78, Orc Baby 24.

## 3. PRE-REGISTERED: the split, the scores and the bars (2026-10-25 20:20 ICT, BEFORE any recognizer)

**The split (by lattice cell, never by frame):**
- **DEV** = cells 0-7 of the watch: everything is designed, fitted and thresholded on DEV only.
- **HELD-OUT** = cells 8-14 of the watch, scored ONCE with the frozen recognizer.
- A watch frame belongs to the cell whose `spawn` precedes it: from that spawn up to the next spawn
  (the dwell, the `@killmonster2`, the warp). Frames before the first spawn are DEV.
- **The pilot:** its frames on gef_fild10 from its first frame there: the first 300 s are DEV, the
  rest HELD-OUT.

**The scores (all on HELD-OUT, after the recognizer and its threshold are frozen with a sha256):**
- **Positive** = the decision function's `seen` on that frame.
- **Episode** = a run of frames with the Orc Lord or an Orc Archer in view (section 2), split where
  none is in view for more than 3 s. A cell's FIRST episode starts at its spawn; later ones are
  re-entries.
- **Delay** (per cell) = t(the first positive frame of the cell's first episode) - t(that episode's
  first frame). Using the party's first frame (Lord OR archer) is the stricter start.
- **Recall within 1 s** = the share of held-out cells whose delay is <= 1.1 s, i.e. a positive on
  the episode's first or second recorded frame (the recording is 1 fps; the runner polls every
  ~0.5 s). The first-frame recall (delay 0) and the per-episode recall (re-entries included) are
  reported beside it, not gating.
- **False positives** = positive frames with NO Orc Lord or Orc Archer box even partly on screen.
  Reported per 10 min of frames (at 1 fps: count / frames x 600), apart for the pilot's held-out
  hunting frames (the bar) and the watch's held-out gap frames (after `@killmonster2`, before the
  next spawn; reported).
- **Latency** = the decision function's wall time per 1280 x 720 frame, `nice -n 15`, one thread,
  >= 200 calls on real frames.

**The bars:**
1. **Recall within 1 s >= 95 %** of the held-out cells (with 7 cells: 7 / 7).
2. **False positives <= 1 per 10 min** of the pilot's held-out hunting frames.
3. **Latency p95 <= 60 ms.**

If a bar fails, the report says so plainly, with what more data would fix it. Nothing is re-fitted
on HELD-OUT; a second attempt would need new held-out data (a second watch).
