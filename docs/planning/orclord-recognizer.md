---
doc_type: design
hypothesis: "From pixels alone, a CPU recognizer cheap enough for the runner (<= 60 ms per 1280 x 720 frame, niced) tells 'the Orc Lord (mob 1190) or its Orc Archers (1189 / 1473) are in view' on gef_fild10 within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of held-out hunting frames."
status: "PRE-REGISTERED 2026-10-25 20:20 ICT (from `date`), BEFORE any recognizer existed; AMENDED A (party edges) and B (pilot2 joins DEV, s1 a supplementary FP test, the frozen recipe) on DEV only; the model is FROZEN (sha256 43179452...) and NOT yet scored on HELD-OUT. Offline only (no client, no GPU, no input)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, payf07-detector.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py]
next_action: "This branch: score the HELD-OUT cells and minutes once with the frozen model (section 3 + Amendment B)."
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

## 4. Amendments (written on DEV only, BEFORE any held-out cell or held-out pilot frame was scored)

### 4a. Amendment A (2026-10-25 ~20:35 ICT): the party's dying and appearing frames

DEV frames 110-112 and 335-336 (just after `@killmonster2`) still show the dying Orc Lord, its
archers and its aura; frame 346 shows the aura 50 ms after a spawn, before the 1d-shifted Timeline
has the unit. The truth drops a unit at its vanish packet, so these frames would count as
negatives. **Change:** a frame within 4 s after an MVP-party unit's vanish, or from 0.5 s before to
1 s after its "new" appearance, is flagged `party_edge` and is neither positive nor negative
(`mvp_watch_study.frame_flags`). It only touches the watch's gap frames (reported, not a bar);
the pilot holds no party unit at all.

### 4b. Amendment B (2026-10-25 ~21:10 ICT): more DEV negatives, a supplementary test, the frozen recipe

**Data.**
- `20261025T203115-rdp-rogue-pilot2` (the parent's second pilot, 20:31-20:41 ICT, 518 frames on
  gef_fild10, no MVP-party unit in its packets) joins **DEV** as hunting negatives.
- The first scored run `20261025T204315-rdp-rogue-s1` (40 min, `@killmonster2` at its setup) is a
  **SUPPLEMENTARY held-out FP test**: scored once with the frozen model, reported beside the bar,
  NOT gating (the bar stays on the pilot's held-out minutes, section 3).

**What the DEV work found (inner 2-fold CV by cell: fit on cells 0-3 + the pilot's DEV 0-150 s,
score cells 4-7 + its DEV 150-300 s, and the reverse):**
- **A colour LUT alone fails**, as the prep predicted: a window mean of the party's colour
  log-likelihood ratio put hunting negatives (a yellow bush, palm leaves, orc-village houses and
  palisades: brown-pink wood) as high as the party (pos median 1.86, hunting max 2.18).
- **The aura is the cleanest cue, but only as a strict RULE.** A learned aura LUT fired on sunlit
  foliage (G 150-210, low blue), white popups ("... obtained") and yellow skill flashes. The rim's
  own colour saturates the green channel: G >= 236, G - R >= 25, G - B >= 25. Of the DEV hunting
  pixels only 0.09 % are that colour, against 60 % of the aura's green pixels.
  - What remained in the hunting frames was OUR OWN HP bar (bright green, its top at y 358-396
    on 99 % of 584 frames) and a potion's green sparkle on our Rogue. The centre mask grew to
    (600, 250)-(680, 412).
  - With it, the DEV hunting max of the ring score is 0.065 (one potion frame), p99 0.025.
- **The aura misses** the spawn frames (the `@monster` summon's light pillars cover it), canopies,
  the chat window, and archers standing on the ring. Per Orc Lord frame its recall is ~0.6.
- **A linear window detector covers most of the rest:** 11 features per 8 x 8 cell (the colour
  LLR, the aura share, mean R / G / B, dark share, 4 gradient orientations, gradient energy), a
  7 x 5-cell window, L2 logistic regression, the party's windows (and 4 neighbours) against random
  and then hard-negative windows (2 rounds).
- **Combined (aura >= 0.08 OR party >= the fit negatives' max + 1.0):** on the out-of-fold half,
  0 / 151 and 0 / 150 hunting false positives, 0 / 51 and 0 / 44 watch-gap false positives, every
  cell (8 / 8) seen on its first or second frame, per-frame party recall 0.79 / 0.66.
  - Margin + 0.0 gave 2 hunting FPs out of fold; + 1.5 lost a cell's first two frames.
- **DEV cell 3** spawned under a tree canopy with our Rogue: nothing of the party is visible for
  9-10 frames. The truth calls it in view (no RSW occlusion, section 2). This is a known miss
  mode, and it can recur in the held-out cells.

**One more DEV finding, on the final fit (all DEV), before the freeze.** Our OWN effects decide the
party threshold:
- The highest DEV negative was pilot frame 78: a light green weapon-swing arc and a potion
  sparkle around our Rogue, a party window footed at (616, 432), just below the centre box.
- Taken as the global maximum it set the threshold at 15.4. The party cue then caught almost
  nothing: in-sample DEV recall 0.62, cell 1 missed on its first two frames.
- A wider mask of (560, 230)-(720, 450) for both cues lost DEV cell 2's first five frames: the
  spawns stand within ~2 cells of the Rogue.
- **The adopted rule:** a party window whose foot lies in SELF_ZONE (560, 230)-(720, 450) must
  clear its OWN threshold, the max of the DEV negatives' in-zone windows + 1.0. Windows outside
  the zone keep the out-of-zone max + 1.0. In the model this is `zone_penalty` = the difference.
  - The aura keeps only the narrow centre box (600, 250)-(680, 412).
  - Its DEV max stays 0.065 (frame 78's arc) under the 0.08 threshold chosen above.

**The frozen recipe** (`mvp_watch_study.py fit`, `mvp_watch.decide`), fitted 2026-10-25 21:30 ICT:
- **The aura rule** at 0.08 on a ring (27, 15, 17, 8 half-res px; grid 3), the centre box masked.
- **The party detector**, fitted on ALL DEV:
  - the data: cells 0-7, the frames before the first spawn, the pilot's first 300 s and pilot2.
    That is 293 positive, 90 watch-negative, 60 edge and 816 hunting frames;
  - the body LUT counts hunting pixels x 10 and other species' foreground x 5;
  - 2 hard-negative rounds;
  - its threshold is the DEV negatives' max outside SELF_ZONE + 1.0 = **9.1903** (that max: 8.1903);
  - inside SELF_ZONE, + `zone_penalty` **6.2013** (the zone threshold is 15.3916).
- **The title-bar guard** at mean |difference| <= 15.
- **The model:** `/dev/shm/poring-lab-tmp/orclord/model/orclord-v1.npz`, 137,746 bytes, sha256
  **43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff**.
- **Its DEV in-sample results** (optimistic, for reference):
  - frame recall 0.72;
  - 7 / 8 cells seen on the first or second frame. Cell 1 is first seen on its third frame: the
    summon's light pillars.
- **Nothing is re-fitted after the held-out score.**
