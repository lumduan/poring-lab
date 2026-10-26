---
doc_type: design
hypothesis: "From pixels alone, a CPU recognizer cheap enough for the runner (<= 60 ms per 1280 x 720 frame, niced) tells 'the Orc Lord (mob 1190) or its Orc Archers (1189 / 1473) are in view' on gef_fild10 within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of held-out hunting frames."
status: "FLEE PROOF fp1c 2026-10-26 04:07-04:14 (12c): bar 1 NO VERDICT (3 / 6 trials had the party in view; 2 / 3 fled by the aura before any damage; trial 1 was hit first), bar 2 PASS (no death); the flee rule is NOT adopted. Earlier: ROUND 2 SCORED 2026-10-26 01:21-01:33 ICT (section 11): the aura rule alone (frozen v1 model) PASSES both bars by the letter -- recall 4 / 4 edge entries within 1.1 s (3 / 4 within 1.0 s; a one-sided 95 % lower bound of 47 %), false positives 0.56 per 10 min on 143 min of gef_fild10 hunting (all 8: our own lock-on magic circle, 0.080-0.100 against 0.08). Thin evidence: only 4 entries; archers alone are not seen. Round 1 (section 5) FAILED with both cues."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, payf07-detector.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py]
next_action: "Batt: whether a second flee proof is worth it (12c: a plan with the party in view in every trial, the OFF toggle out of its reach, the Lord's entry separated from the archers'). Until then --clear-map and Amendment E's schedule keep the natural Lord out of the runs."
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

## 5. RESULT: the held-out score (run 2026-10-25 21:34:25-21:36:37 ICT, once, model sha256 43179452...; `score-heldout.json`)

**Bars 1 and 2 FAIL; bar 3 passes.**

| bar | measured | verdict |
|---|---|---|
| 1. recall within 1 s >= 95 % of held-out cells | **5 / 7 = 71.4 %** (first-frame recall also 71.4 %) | **FAIL** |
| 2. false positives <= 1 per 10 min of the pilot's held-out hunting frames | **2 in 634 frames (10.6 min) = 1.89 per 10 min** | **FAIL** |
| 3. latency p95 <= 60 ms | **p50 30.5 ms, p95 53.7 ms, max 114.6 ms** (1,006 calls, `nice -n 15`, one thread, full 1280 x 720 frames) | PASS |

**Per held-out cell** (the first episode's delay; the recording is 1 fps):

| cell | spawn | delay | within 1.1 s | what the frames show |
|---|---|---|---|---|
| 8 | (159,291) | 0.0 s | yes | |
| 9 | (148,269) | **11.0 s** | **no** | the party AND our Rogue spawn under a big tree's canopy: nothing of them is visible for 11 frames (the truth has no canopy occlusion, section 2) |
| 10 | (49,302) | 0.0 s | yes | |
| 11 | (82,137) | 0.0 s | yes | |
| 12 | (159,302) | **2.0 s** | **no** | frame 1: the summon's white starburst over the party; frame 2: its light pillar; seen on frame 3 |
| 13 | (335,159) | 0.0 s | yes | |
| 14 | (93,93) | 0.0 s | yes | |

- Per frame (held-out cells): the party seen on 224 / 268 frames in view (0.836); the Orc Lord
  in view on 254, seen on 220 (0.866).
- Re-entries (a later episode after > 3 s out of view): 1, seen within 1 s.
- The watch's held-out gap frames: 0 false positives in 71.

**The two hunting false positives** (both the PARTY cue; the aura stayed under 0.08):
- pilot frame 475: an Orc Lady wrapped in a bright yellow-white cast flash, (488, 304). Its
  score was 9.209 against the threshold 9.190, a 0.02 margin.
- pilot frame 722: a green MAGIC CIRCLE (pentagram) on the ground around our Rogue and an Orc
  attacking it, (584, 416). The raw window score was 20.56, far above anything on DEV in the
  self zone (14.39), so 14.36 remained after the zone penalty.

**The supplementary test (Amendment B, NOT a bar):** `20261025T204315-rdp-rogue-s1`.
- It was stopped by its IO guard at 26 min; 1,356 frames are on the map (22.6 min).
- **2 false positives = 0.88 per 10 min**, both the party cue at the self zone's edge:
  - frame 906 at (552, 400), score 11.98;
  - frame 1248 at (744, 432), score 10.62.
- 4 frames were refused as `no_game_view` (loading screens).
- Pooled with the pilot's held-out minutes: 4 FPs in 33.2 min = 1.2 per 10 min.

## 6. POST-HOC (after the score; NOT a bar, nothing here passes or fails anything)

Run on the same held-out frames with the frozen model, to say what the next pre-registration should
test. The scratch scripts (`posthoc.py`, `posthoc_s1.py`), the score JSONs, the truth files, the
fit logs, the crops and a copy of the model are archived, sha256-checked (103 files), in
`/mnt/poring-lab-datasets/scratch-archive/2026-10-25/orclord/`.
- **The aura rule ALONE** (`decide(..., cues=("aura",))`, added after the score; the default stays
  the frozen two-cue recipe):
  - false positives: 0 in the pilot's 634 held-out frames and 0 in s1's 1,356, i.e. **0 in
    33.2 min of hunting**;
  - the highest hunting aura score is 0.0697 (pilot 722's magic circle), against the threshold
    0.08. **The margin is thin.**
  - **The same 5 / 7 cells** within 1 s, missing the same two (canopy, summon pillar);
  - per-frame recall 0.735 against 0.836 for both cues;
  - it costs **p50 8.9 ms, p95 12.5 ms** per frame, against 32-40 / 44-54 ms for both cues.
  - So on these frames the party detector added frame recall but no cell, and all four false
    positives.
- **Two consecutive positive frames, both cues:** 0 pilot false positives, but only 4 / 7 cells
  within the window (one frame later).
- **Latency under load** (load average 17-20): both cues p95 44-54 ms with a max of 76-128 ms;
  the aura alone p95 10-12.5 ms.

## 7. For the runner (the parent wires it; `dungeon_hunt.py` is not edited here)

    import mvp_watch
    model = mvp_watch.load(Path("data/mvp_watch/orclord-v1.npz"),
                           sha256="43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff")
    # in its own thread with its OWN r.Screen() (screen-grab-not-thread-safe), every ~0.5 s:
    v, ms = mvp_watch.timed(frame_bgr_1280x720, model)            # the frozen v1: both cues
    # or, after Batt's / the parent's decision on section 6: cues=("aura",)
    if v["seen"]:
        ...  # the flee rule: the Fly Wing key at once; log v (aura, party, where, cue) and ms

- `load` fails closed (`ModelUnavailable`): the runner must then refuse the flee-dependent mode,
  not run blind.
- The frame is the game region only (1280 x 720, BGR), in the hunt layout. Other layouts pass
  their own `ui_rects`. A loading screen returns `reason: no_game_view`, never `seen`.
- Install: `cp /dev/shm/poring-lab-tmp/orclord/model/orclord-v1.npz data/mvp_watch/` on the main
  checkout (gitignored; it holds client-derived pixel statistics).

## 8. What more data would fix the bars

1. **Real approaches, not spawns.** Both missed cells are artefacts of `@monster` next to the
   Rogue: the summon's starburst and pillar, and a spawn under a canopy. A natural Orc Lord walks
   in from the screen edge. Proposal for a second, pre-registered watch:
   - spawn the Orc Lord;
   - `@warp` the immune Rogue 16-20 cells away, then walk back toward it;
   - every episode is then an EDGE ENTRY;
   - record at 2-5 fps so the delay is measured at the runner's 0.5-s poll, not in 1-s steps.
2. **Canopies in the truth:** extract gef_fild10's RSW and models, as payf07's occluders, so a
   party hidden under a tree is flagged rather than counted. Or Batt decides that a hidden Orc
   Lord counts as a miss.
3. **Our own fight effects are the false positives' source:** magic circles, cast flashes, swing
   arcs and potion sparkles, all around our own character. They are rare, so they need hours of
   hunting to sample. The scored runs s2-s8 (40 min each, `@killmonster2` at setup) would give
   them:
   - some as DEV negatives for the party detector;
   - the rest as a held-out FP test of >= 2 h, which an FP bar of 1 per 10 min needs (10.6 min
     cannot show 1 per 10 min with any confidence).
4. **Pre-register the aura-alone recipe** on that new data. The post-hoc numbers in section 6 are
   NOT evidence for it, because they were seen after the score.

## 9. Reproduce

    W=<checkout>; export PYTHONPATH=$W/scripts:$W/packages/poring_dataset/src:$W/packages/poring_env/src:$W/packages/poring_packets/src:$W/packages/poring_flow/src
    T=/dev/shm/poring-lab-tmp/orclord; E=/dev/shm/poring-lab-demo/20261025T195327-watch-gef_fild10-ow1/events.jsonl
    D=/mnt/poring-lab-datasets
    python3 scripts/mvp_watch_study.py truth $D/20261025T195325-rdp-ow1 --layout standard --out $T/ow1-truth.json
    python3 scripts/mvp_watch_study.py truth $D/20261025T200922-rdp-rogue-pilot --layout hunt --out $T/pilot-truth.json
    python3 scripts/mvp_watch_study.py truth $D/20261025T203115-rdp-rogue-pilot2 --layout hunt --out $T/pilot2-truth.json
    python3 scripts/mvp_watch_study.py truth $D/20261025T204315-rdp-rogue-s1 --layout hunt --out $T/s1-truth.json
    python3 scripts/mvp_watch_study.py fit --watch $D/20261025T195325-rdp-ow1 --watch-truth $T/ow1-truth.json --events $E \
        --pilot $D/20261025T200922-rdp-rogue-pilot $T/pilot-truth.json \
        --extra $D/20261025T203115-rdp-rogue-pilot2 $T/pilot2-truth.json --work $T/fit --out $T/model/orclord-v1.npz
    python3 scripts/mvp_watch_study.py score --model $T/model/orclord-v1.npz --sha256 43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff \
        --watch $D/20261025T195325-rdp-ow1 --watch-truth $T/ow1-truth.json --events $E \
        --pilot $D/20261025T200922-rdp-rogue-pilot $T/pilot-truth.json \
        --supplement $D/20261025T204315-rdp-rogue-s1 $T/s1-truth.json --out $T/score.json

- The truth needs the KB with gef_fild10 (data/kb), the client GAT
  (`/dev/shm/poring-lab-tmp/gat/data/gef_fild10.gat`) and the decoded sprites
  (`/dev/shm/poring-lab-tmp/gef10-prep/sprites/`): all local, client- or GPL-derived, never
  committed.
- The watch's events.jsonl lives in /dev/shm/poring-lab-demo/ (the parent's session folder).
- The fit is deterministic (seed 0).

## 10. PRE-REGISTERED: round 2 -- the AURA rule alone on EDGE ENTRIES (the parent, 2026-10-25 22:16 ICT from `date`, BEFORE any round-2 frame exists)

**Why:** round 1 failed both bars (section 5). Its two missed cells were spawn artefacts (the Lord
spawned on us under a canopy; the summon's starburst). Its false positives came from the party
cue near our own effects. Section 6 saw the aura rule ALONE give 0 false positives in 33.2
hunting minutes, but that was post hoc. Section 8 asked for edge entries. This round tests exactly
that recipe on new data, once.

**The recipe (frozen now, nothing fitted on round-2 data):**
- `mvp_watch.decide(frame, model, cues=("aura",))` with the round-1 model;
  - sha256 `43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff`;
  - `/dev/shm/poring-lab-tmp/orclord/model/orclord-v1.npz`, with a copy in the NAS scratch
    archive;
- the aura threshold 0.08 and HUNT_RECTS unchanged.

**The data:**
- **ow2** (`scripts/orclord_edge_watch.py run --map prt_fild08 --n 8 --seed 26`): the immune Rogue
  on prt_fild08, in the gap between gef_fild10 runs (its `@killmonster2` cannot touch gef_fild10's
  natural Lord; rogue-gef10.md Amendment E).
  - At each of 8 cells: spawn the Lord, warp 17 cells away, then hop back 3 cells at a time to 8.
  - The Lord enters the view from its edge at one of the hops.
  - A 2-fps PNG recorder runs beside it.
- **Hunting negatives:** gef_fild10's a2-a6 recordings, every frame on the map. (Round 1 used the
  pilots and s1.)
- **Limits, said now:** prt_fild08 is open ground, so this tests edge entries, not canopy. A Lord
  hidden under gef_fild10's trees stays a known gap.

**The truth:** packets + projection, round 1's `mvp_watch_study.py truth` unchanged. "In view" is
its rule. An entry is a hop at which the Lord (or an archer) goes from not in view to in view.

**The bars (scored ONCE, by `mvp_watch_study.py score` with cues=("aura",)):**
1. **Recall:** >= 95 % of the edge entries have a positive within 1 s of the first in-view frame.
   Each entry also gets its delay.
2. **False positives:** <= 1 per 10 min of gef_fild10 hunting frames (a2-a6, >= 2 h).
3. Latency already passed (p95 12.5 ms for the aura alone, section 6): reported, not a bar.

**If both pass:** a FLEE rule follows, pre-registered on its own: a Fly Wing on the first positive.
It gets a live proof on a spawned Lord with immunity OFF before any scored run uses it.
**If either fails:** no flee. `--clear-map` with Amendment E's schedule stays.

### 10a. Amendment (2026-10-26 00:26 ICT from `date`; BEFORE any round-2 frame is scored)

- **Negatives become a1-a6** (was a2-a6). The recorders stopped early on the IO guard (a4: 578
  frames; a5: 84, a 1.5-min run), so a2-a6 give ~111 min of recorded hunting, short of the
  required >= 2 h. a1 (`20261025T213953-rdp-rogue-a1`, 23.7 min) was never seen by round 1 and
  brings it to ~135 min. Nothing else changes: the recipe, the entries and both bars stay as above.
- **The tool:** `mvp_watch_study.py` gains a `--map` (ow2 is on prt_fild08: its GAT for the
  projection) and a round-2 `entries` scorer:
  - an entry is a hop where the Lord or an archer goes from not in view to in view;
  - its frames run from the hop's settle to the next hop.
  - Both are written before the score runs and tested on synthetic cases only.

## 11. RESULT: round 2, scored ONCE (2026-10-26 01:21:23-01:33:45 ICT from `date`; written 01:38)

**Both bars PASS by the letter: entries 4 / 4 within 1 s, false positives 0.56 per 10 min.**
The evidence is thinner than the bars suggest. Only 4 of the 32 hops were edge entries, and one
of the four passes on round 1's 0.1-s jitter allowance. All 8 hunting false positives are one
effect, at margins of 0.0004-0.0205 over the threshold.

**What ran:**
- The scorer (`mvp_watch_study.py entries`, `truth --map`) was committed BEFORE the score:
  89ed662, 01:19:14 ICT. It was tested on synthetic cases only (Amendment 10a).
- Nothing was fitted or changed after it. The run: one process, `nice -n 19`, one thread.
- The recipe: `decide(frame, model, cues=("aura",))`, HUNT_RECTS, the aura threshold 0.08.
- The model: round 1's `orclord-v1.npz`, its sha256 checked before the run (43179452...).
- The truth: round 1's rule. ow2 used `--layout hunt --map prt_fild08`; by eye its frames are in
  the hunt layout, as are a1-a6's.
  - prt_fild08's own monsters (Poring, Pupa, Lunatic, Drops) have no decoded sprite sheet, so
    they are not in the truth. Only the party matters to the bars.
- The output: `score-round2.json`.

**The rules as committed** (89ed662; recorded here because 10a gave them in one line):
- **An entry** is a hop whose last frame before its @warp has no party unit in view, and whose
  window has at least one in-view frame.
  - The window runs from the hop's settle (its event is written after the settle) to the next
    @warp, or to the cell's @killmonster2.
- **The delay** = the first in-view frame of the window with a positive, minus the window's first
  in-view frame. Positives on in-view frames only, as round 1's `cell_scores`.
- **Within 1 s** = a delay <= 1.1 s: round 1's RECALL_S, unchanged. At 2 fps that is an entry's
  first three frames. The strict <= 1.0 s is reported beside it.
- **The hunting minutes and false positives** are counted on the recorders' 1-fps stream.
  - The recorder skips a tick whose picture is unchanged, so a stored frame stands for itself and
    the ticks skipped after it.
  - The skipped ticks counted from the frame times equal each manifest's `unchanged_skipped`
    exactly (123 / 160 / 375 / 0 / 0 / 1,099).
  - The stored-frames-only rate is reported beside it.

### 11a. The bars

| bar | measured | verdict |
|---|---|---|
| 1. >= 95 % of edge entries with a positive within 1 s of the first in-view frame | **4 / 4 = 100 %** within 1.1 s. Strict 1.0 s: 3 / 4 (one at 1.007 s). On the first in-view frame: 2 / 4 | **PASS** |
| 2. <= 1 false positive per 10 min of a1-a6 hunting frames (>= 2 h) | **8 in 143.0 min = 0.56 per 10 min** on the 1-fps stream. Stored frames only: 8 in 113.9 min = 0.70 | **PASS** |
| (data) >= 2 h of hunting negatives | 143.0 min on the stream; **113.9 min** by stored frames alone | met on the stream only |
| 3. latency (reported, not a bar) | p50 9.5 ms, p95 16.2 ms, max 49.3 ms; 8,090 calls, `nice -n 19`, one thread, load average ~9-12 | -- |

**How much these numbers can carry:**
- 4 / 4 has a one-sided 95 % lower bound of **47 %** (Clopper-Pearson). It cannot show 95 %
  recall.
- 8 false positives in 143 min have a 95 % Poisson interval of **0.24-1.10 per 10 min**. The bar's
  limit, 1, lies inside it.

### 11b. The edge entries (ow2, prt_fild08, 2 fps, 1,233 frames)

Of the 32 hops, **4 were entries**. Section 10 expected about one per cell, and that held in 4 of
the 8 cells.
- In cells 4, 5 and 6 the party was already in view at the far hop, 17 cells away. Why (its
  own walking, or the view's reach on those directions) is not established here.
- In cell 1 the party never came into view at any hop.

| cell | dir | hop 0 (17 cells) | hop 1 (14) | hop 2 (11) | hop 3 (8) |
|---|---|---|---|---|---|
| 0 | (-1,-1) | out of view | out | **ENTRY** | out |
| 1 | (-1,-1) | out | out | out | out |
| 2 | (1,1) | out | out | out | **ENTRY** |
| 3 | (1,-1) | out | out | out | **ENTRY** |
| 4 | (0,-1) | in view (already before the warp) | in view | out | out |
| 5 | (-1,1) | in view | in view | in view | in view |
| 6 | (-1,0) | in view | in view | in view | in view |
| 7 | (-1,1) | out | out | **ENTRY** | in view (continuing) |

**Per entry** (frame ids of `20261026T000413-rdp-ow2`; "by eye" is from the frames):

| # | cell / hop (dist) | first in-view frame of the window | first in | first positive | delay | <= 1.1 s | <= 1.0 s | by eye |
|---|---|---|---|---|---|---|---|---|
| 1 | 0 / 2 (11) | 110 (settle + 0.16 s) | Orc Lord | 110 | **0.0 s** | yes | yes | the Lord and its aura at the top-right edge from frame 109, before the settle, already positive |
| 2 | 2 / 3 (8) | 434 (settle + 0.39 s) | archers | 436 | **1.007 s** | yes | **no** | archers at the left edge from 432 (pre-settle); the aura rule sees nothing until the Lord walks in on 436 |
| 3 | 3 / 3 (8) | 588 (settle + 0.38 s) | Orc Lord | 588 | **0.0 s** | yes | yes | the Lord and its aura at the top edge from 586, before the settle (2 of the 4 pre-settle in-view frames 584-587 were positive) |
| 4 | 7 / 2 (11) | 1190 (settle + 6.93 s) | Orc Lord | 1191 | **0.504 s** | yes | yes | the Lord walks in at the bottom right on 1190 (see below for 1174-1176) |

**The frames between a @warp and its settle** are outside every window, as pre-registered. The
pre-settle columns of the JSON show why the window starts at the settle:
- The truth already counts the party in view there.
- The first 1-2 frames, however, still show the PRE-warp picture (584) or the client's dark warp
  fade (107, 431, 585, 1173).

Two of them matter for the flee rule (POST-HOC, read from the frames, not a bar):
- **Entry 2:** archers were on screen from frame 432. The first positive came on 436, about
  **2.0 s** later, when the Lord itself came in.
- **Cell 7:** archers were on screen on 1174-1176, right after the warp, with no positive. They
  left the view on 1177. The entry scored is the Lord's later walk-in (1190).
- So the aura rule sees the Orc Lord, not its archers. Archers ahead of their Lord are a gap of
  about 2 s on these frames.

**Per frame on ow2** (not a bar):
- the party in view: positive on 307 / 493 frames (0.62);
- the Orc Lord in view: 304 / 456 (0.67);
- partly on screen: 9 / 74.
- In two non-entry windows the party stayed in view with archers first, and the first positive
  came 4.0 s (cell 5, hop 0) and 2.5 s (cell 5, hop 3) after the window's first in-view frame.
- **One positive on a negative ow2 frame:** frame 351, aura 0.140 at (423, 181).
  - It is the first frame after cell 2's far @warp. The client still draws the pre-warp picture,
    with the Lord, its aura and the archers on screen.
  - The truth (packets, 1d = 120 ms) already has us 17 cells away.
  - So it is a truth-timing artefact at a warp, not a wrong positive.

### 11c. The hunting negatives (gef_fild10 a1-a6, 1 fps, every frame on the map)

| session | stored frames on map | negative frames | 1-fps ticks (min) | party frames (not counted) | false positives |
|---|---|---|---|---|---|
| a1 `20261025T213953-rdp-rogue-a1` | 1,334 | 1,309 | 1,429 (23.82) | 25 | 1 |
| a2 `20261025T221059-rdp-rogue-a2` | 2,027 | 2,027 | 2,181 (36.35) | 0 | 3 |
| a3 `20261025T224840-rdp-rogue-a3` | 1,806 | 1,806 | 2,181 (36.35) | 0 | 0 |
| a4 `20261025T232619-rdp-rogue-a4` | 556 | 556 | 556 (9.27) | 0 | 2 |
| a5 `20261026T001947-rdp-rogue-a5` | 52 | 52 | 52 (0.87) | 0 | 0 |
| a6 `20261026T002500-rdp-rogue-a6` | 1,082 | 1,082 | 2,181 (36.35) | 0 | 2 |
| **total** | 6,857 | 6,832 | **8,580 (143.0)** | 25 | **8** (8 ticks) |

- 29 frames were refused as `no_game_view` (loading screens).
- Every false positive stood for one tick: none was followed by skipped duplicates.
- Leaving out a6 (Amendment G's stuck run): 6 in 106.7 min, 0.56 per 10 min, but then under 2 h.

**The 8 false positives** are all one effect. Each is a **pale green-white pentagram magic
circle on the ground around our own Rogue**, the effect round 1 met at 0.0697 on pilot frame 722.
Here it reaches 0.0804-0.1005 against the threshold 0.08, with its foot just outside the masked
centre box:

| session | frame | aura score | where | on screen (by eye) |
|---|---|---|---|---|
| a1 | 133 | 0.0969 | (627, 409) | the circle around our Rogue; an Orc Lady attacking beside it |
| a2 | 471 | 0.1005 | (627, 409) | the circle around our Rogue; an orc beside it |
| a2 | 1444 | 0.0875 | (597, 343) | the circle around our Rogue; two Orc Ladies, one mid-swing, a "Miss" |
| a2 | 1740 | 0.0946 | (657, 421) | the circle around our Rogue; an Orc Lady |
| a4 | 298 | 0.0993 | (639, 421) | the circle around our Rogue (just sat down); an Orc Lady |
| a4 | 414 | 0.0816 | (567, 391) | the circle around our Rogue; an Orc Lady, a fallen log |
| a6 | 266 | 0.0851 | (723, 367) | the circle around our Rogue behind a yellow bush; an Orc Warrior attacking from the left, "Miss" x3 |
| a6 | 348 | 0.0804 | (693, 337) | the same spot; the Orc Warrior, damage "122", our HP bar red |

**Where the circle comes from: not confirmed.** The sniffer decodes no skill-cast packet. It
matches the client's lock-on circle around a skill's TARGET:
- in the local KB (`mob_skills.json`), every hunting species on this map casts a targeted skill
  with a cast time;
- Orc Lady and Orc Warrior: NPC_GROUNDATTACK, 500 ms;
- Orc Baby: SM_BASH, 800 ms;
- Poporing: NPC_POISON, 800 ms.

Our own SP fell by 10 within 2 s of 2 of the 8 frames, and was unchanged around the other 6.

**The natural Orc Lord in a1** (frames 1326-1350; listed, never counted; not a bar):
- the party came in under a tree canopy over our Rogue;
- 1326: an archer in view at the bottom edge, no positive;
- 1327: the Lord and 5 archers in view, aura 0.065, no positive;
- **first positive 1328** (aura 0.122): 2.0 s after the first in-view frame (1 fps) and 1.0 s
  after the Lord's own;
- the first HP loss (none in the 40 s before) came 2.4 s after 1328, and HP reached 1 at 4.2 s
  (Amendment E's death);
- positives on 17 / 22 of its in-view frames.
- It is the only natural approach in these data: a canopy case, which section 10 named as a known
  gap.

### 11d. What this says

- **By the pre-registration, both bars pass.** Section 10 then calls for a FLEE rule,
  pre-registered on its own, with a live proof on a spawned Lord with immunity OFF before any
  scored run uses it. That is Batt's / the parent's step; nothing here starts it.
- **The caveats belong in that rule's pre-registration:**
  1. Recall rests on 4 entries. The lower bound is 47 %, and one entry passes only on the 0.1-s
     allowance.
  2. The aura sees the Lord, not its archers. Archers ahead of the Lord were on screen ~2 s
     before the first positive (entry 2, cell 7).
  3. Every false positive is the target lock-on circle around our own Rogue, just over 0.08. A
     map or build where monsters cast on us more often would raise the rate. Two things would
     address it:
     - an exclusion for the circle's own shape (a thin ring centred on our feet);
     - a 2-frame confirmation, which round 1 (section 6) found cost one frame of delay.
     Either is a NEW recipe and needs new held-out data.
  4. A canopy hides the Lord: a1's real approach was first positive 2 s after the first in-view
     frame, 4.2 s before the death.

**Files** (in `/dev/shm/poring-lab-tmp/orclord-r2/score/`, then archived to the NAS scratch
archive):
- `score-round2.json` and its log;
- the truths `ow2-truth.json` and `a1-truth.json` ... `a6-truth.json`;
- the frames looked at by eye.

Reproduce: section 9's environment, then:

    T=/dev/shm/poring-lab-tmp/orclord-r2/score; D=/mnt/poring-lab-datasets
    python3 scripts/mvp_watch_study.py truth $D/20261026T000413-rdp-ow2 --layout hunt --map prt_fild08 --out $T/ow2-truth.json
    python3 scripts/mvp_watch_study.py truth $D/20261025T213953-rdp-rogue-a1 --layout hunt --out $T/a1-truth.json   # a2-a6 alike
    python3 scripts/mvp_watch_study.py entries --model /dev/shm/poring-lab-tmp/orclord/model/orclord-v1.npz \
        --sha256 43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff \
        --watch $D/20261026T000413-rdp-ow2 --watch-truth $T/ow2-truth.json \
        --events /dev/shm/poring-lab-demo/20261026T000416-watch-prt_fild08-ow2/events.jsonl \
        --hunt $D/20261025T213953-rdp-rogue-a1 $T/a1-truth.json ... --hunt $D/20261026T002500-rdp-rogue-a6 $T/a6-truth.json \
        --out $T/score-round2.json

## 12. PRE-REGISTERED: the FLEE rule's live proof (the parent, 2026-10-26 01:48 ICT from `date`, BEFORE it runs)

**The rule:** a Fly Wing (F2) on the FIRST aura positive.
- The recognizer is round 2's recipe unchanged: `mvp_watch.decide(frame, model, cues=("aura",))`,
  model sha256 `43179452...`, threshold 0.08, HUNT_RECTS.
- It reads fresh frames every 0.25 s.
- A backup fires F2 below 50 % HP. It is logged apart and is not the rule under test.

**The proof** (`scripts/orclord_flee_proof.py run --map prt_fild08 --n 6 --seed 27 --label fp1`):
- 6 trials on prt_fild08, the edge-watch plan's cells (gef_fild10's natural Lord is untouched).
- Per trial:
  1. immunity ON;
  2. `@warp` the cell, `@monster 1190 1`, then `@warp` 17 cells out;
  3. immunity OFF;
  4. hop back 3 cells at a time with the watcher running;
  5. on the first positive, F2;
  6. immunity ON, `@killmonster2`.
- Each immunity toggle is VERIFIED on the client's own reply bubble ("You are now immune to
  attacks." / "Returned to normal state."). The text pixels of tonight's judged frames
  (`data/mvp_watch/immune_bubbles.npz`, never committed) read on 1.00 / off 1.00 / another
  bubble 0.13. An unreadable or wrong bubble stops the proof.
- A death stops it too.
- It runs in Amendment E's 04:24 gap (rogue-gef10.md), between scored runs, never inside one.

**The bars** (from the packets, offline):
1. In >= 5 of 6 trials, F2 is pressed by the AURA (not the HP backup) BEFORE the Orc Lord party's
   first damage on us. A trial with no party unit in view at all is reported and not counted.
2. No death.
3. Reported, not bars:
   - seen -> F2 (ms);
   - F2 -> the same-map teleport (the `map_change` packet);
   - the HP lost per trial.

**If both pass:**
- the runner gains the rule as **dungeon@9** (the watcher thread, its own `r.Screen()`, a Fly Wing
  at once, the 8.2 stand fix kept);
- it is used only AFTER the scored A/B block (a1-a8), so the block is not changed.
- Batt then decides whether `--clear-map` goes.

### 12a. Attempt 1 stopped safely by its own check; flee@2 (2026-10-26 04:02 ICT from `date`, BEFORE attempt 2)

- **fp1 (03:55:33-03:56:17), trial 1 of 6:** immunity ON was read; `@warp` 252,329,
  `@monster 1190 1`, `@warp` 252,346 (17 cells out). The OFF toggle was typed, but **no reply
  bubble was read within 3 s**, and the proof stopped by design. The flee rule never ran: no hop
  and no watch. Nothing about the rule was measured. HP stayed at 100 %.
- **The cause, read on frames afterwards** (the parent, on the open-field stand, 03:57-04:00):
  - The toggle had worked: the next read on the stand said "on", so the state before it was OFF.
  - The live "Returned to normal state." bubble draws **1 px lower** than its reference: text rows
    8-17 vs 7-16, a score of 0.50 at the box and 1.00 one row down.
  - The reference's "off 1.00" (section 12) was a self-match on the frames it was cut from. That
    is not a positive case (feedback: a verifier proves a positive case).
  - The ON bubble matches at 0 px.
- **flee@2 (this commit):**
  - `read_bubble` searches +-2 px for each reference. On tonight's real frames it reads on 5/5,
    off 5/5, and None with no bubble. The cross-scores stay <= 0.44 (the bar is 0.8 / 0.6).
  - **A stop after a spawn now exits safely:** `@warp` to the open-field stand (268,107), then
    `@killmonster2`. In fp1 the parent did this by hand: stand first, then immunity read and set
    OFF by eye on the bubble, at 04:00.
  - Tests: thin-stroke synthetic shifts and a 7-px miss stay None.
- **Attempt 2** runs the same plan unchanged (seed 27, 6 trials, the same model, cue, watch and
  bars) under label `fp1b`. fp1 counts as no trial.

### 12b. Attempt 2 stopped safely at trial 2; flee@3 (2026-10-26 04:06 ICT from `date`, BEFORE attempt 3)

- **fp1b (04:03:40-04:05:16), flee@2:**
  - **Trial 1 ran whole:** immunity ON, then OFF read live at the far cell (the 12a fix works),
    then 4 hops at 17 / 14 / 11 / 8 cells, then ON and `@killmonster2`. `fled=None`: no aura
    positive and no HP backup. Its packets decide whether any party unit was in view (an unseen
    trial is not counted).
  - **Trial 2 stopped by the read:** each trial began with an ON toggle, but trial 1 had ended ON,
    so the toggle flipped it OFF. The check read "off" (wanted "on") and stopped. The party was
    already cleared; the Rogue stood at 252,337 among passive monsters.
- **flee@3:** a trial toggles ON only when the believed state is not ON.
- **Attempt 3** (`fp1c`) runs the full plan again: seed 27, all 6 trials, everything else
  unchanged. fp1b's trial 1 is reported apart and not counted, so no trial is selected after the
  fact.

### 12c. RESULT: fp1c -- bar 1 NO VERDICT (3 of 6 trials counted, 2 passed), bar 2 PASS (no death) (2026-10-26 04:18 ICT from `date`)

- **The run:** fp1c, 04:07:04-04:14:06, flee@3, the plan unchanged (seed 27, 6 trials). Every
  immunity toggle was read and verified; it ended "done". Recording
  `20261026T040702-rdp-fp1c` (NAS, 841 frames at 2 fps).
- **Scored once** (04:16-04:17) with the scorer committed BEFORE the scoring (630b1c1, 04:09:51):
  the per-frame truth (`mvp_watch_study.py truth --layout hunt --map prt_fild08`), our AID
  2000002 (DB).
  - **Result: counted 3 / 6, passed 2 / 3. Bar 1 NO_VERDICT (fewer than 4 counted). Bar 2 PASS.**
- **A scorer flaw, found reading that output, and fixed in this commit:**
  - The proof logs its `flee` event after the key send returns, about 130 ms after the press.
  - 630b1c1 timed F2 at the event, and matched a LATER map change: F2 -> teleport read 134 s,
    155 s and none.
  - The fix takes the press from the Fly Wing's `use_item_request` and the teleport from the
    first map change after it, GM-tagged or not.
  - Re-run: **the same verdict** (counted 3, passed 2; no trial changes). F2 -> teleport is
    34.6-35.9 ms. Both outputs are kept (`score-fp1c-v1.json`, `-v2.json`).

| trial | cell | counted | F2 by | seen -> F2 | F2 vs the first damage | passed |
|---|---|---|---|---|---|---|
| 1 | 252,329 | yes | aura | 221 ms | 136 ms AFTER it | no |
| 2 | 164,299 | no (no party unit in view in 49 s) | - | - | no damage | - |
| 3 | 248,217 | yes | aura | 9,473 ms | no damage | yes |
| 4 | 92,79 | no | - | - | no damage | - |
| 5 | 48,121 | yes | aura | 9,804 ms | no damage | yes |
| 6 | 279,72 | no | - | - | no damage | - |

- **Trial 1:** the party stood within reach of the far cell; it had wandered while we were
  immune. Its archers hit us (288 / 287 / 265) in the moment of the OFF toggle, 0.24 s before the
  OFF read was logged. The Orc Lord's act of 3,050 followed. HP went 2,146 -> 1,306 (61 %). F2
  came 221 ms after the party was in view: fast, but after the damage.
- **Trials 2, 4, 6:** the immune party wandered out of the approach. No unit came in view during
  the 4 hops down to 8 cells, so these trials are not counted.
- **Trials 3, 5:** the first party unit in view (an archer or the Lord; not separated here) came
  9.5 / 9.8 s before the aura fired. Nothing hit us before F2.
- **By section 12: not both bars pass, so the flee rule is NOT adopted.** No dungeon@9, and
  `--clear-map` stays. The clock schedule keeps gef_fild10's natural Lord out of the runs.
- **What a next attempt would need (Batt's decision):**
  - a plan where the party is in view in every trial; it wanders while we are immune;
  - the OFF toggle out of the party's reach;
  - the Lord's own entry time separated from the archers'.

### 12d. Reported after 12c, deciding nothing: the Lord's own entry -> F2 (2026-10-26 04:46 ICT from `date`)

From the same truth (`in_view` per species), in the 3 counted trials:

| trial | an archer in view | the Lord in view | F2 (the Fly Wing request) | Lord -> F2 | first damage |
|---|---|---|---|---|---|
| 1 | 0.30 s | 0.30 s | 0.52 s | 0.22 s | 0.38 s |
| 3 | 5.44 s | 14.48 s | 14.91 s | 0.43 s | none |
| 5 | 26.97 s | 36.47 s | 36.78 s | 0.31 s | none |

(seconds after the verified OFF read)

- **The aura rule fired within 0.22-0.43 s of the Lord entering view in all three.** Round 2's
  bar was "within 1.1 s".
- **The archers enter view first:** about 9 s before the Lord in trials 3 and 5. They spread out
  and shoot from range, so a rule keyed on the Lord alone can be late against them. They did not
  shoot in 3 and 5.
- **Trial 1's fail is the procedure, not the recognizer:** the whole party was in view when
  immunity went OFF.

## 13. PRE-REGISTERED: the flee proof, round 2 (fp2) (the parent, 2026-10-26 10:46 ICT from `date`, BEFORE it runs; Batt ~09:4x: "test again")

**Unchanged (the rule under test):** F2 on the FIRST aura positive.
- `mvp_watch.decide(..., cues=("aura",))`, model sha256 `43179452...`, threshold 0.08, frames
  every 0.25 s;
- the HP backup below 50 %, logged apart;
- every immunity toggle verified on its bubble (flee@3).

**Changed: the PROCEDURE, against fp1c's two failures (12c):**
1. **The OFF toggle is beyond the party's reach.** Per trial: immunity ON, `@warp` C,
   `@monster 1190 1`, `@warp` to the TOGGLE cell 25 cells out, immunity OFF there, `@warp` to
   the first hop (17), then the hops. In fp1c trial 1 the archers hit us at the moment of the OFF
   toggle, at 17 cells.
2. **The approach goes closer:** hops at 17 / 14 / 11 / 8 / 5 / 2 cells (`--near 1`). In fp1c,
   3 of 6 trials never had the party in view down to 8 cells.
3. **8 trials** (`--n 8 --seed 28`, the plan's cells on prt_fild08, `--toggle 25`).
   `orclord-flee@4`, recorder at 2 fps.

**Changed: the COUNTING (fixed now, before any data):**
- **A trial is COUNTED when the ORC LORD itself (1190) is in view** (the truth's `in_view`). The
  aura is the Lord's cue, and the Lord is the lethal one: its hit was 3,050 in fp1c, an archer's
  265-288.
- **It PASSES when the aura's F2** (the Fly Wing request packet) **precedes the Lord's first
  damage on us.**
- The archers' damage before F2 is REPORTED per trial; it does not fail a trial.
- `orclord_flee_score.py --count-by lord` (this commit; tests; fp1c's default scoring is
  unchanged: 3 counted, 2 passed).

**The bars:**
1. With c trials counted, **PASS when c >= 4 and passes >= ceil(5c / 6)**. NO VERDICT when c < 4.
2. No death.
3. Reported, not bars:
   - the Lord -> F2 time;
   - F2 -> teleport;
   - the archers' damage before F2;
   - trials with no Lord in view.

**If both pass:**
- dungeon@9 may carry the flee rule (watcher thread, its own `r.Screen()`, F2 at once).
- Batt then decides whether `--clear-map` goes. Until then, the clock schedule keeps the natural
  Lord out of the runs.

**The command (after b1, before 12:00:28):**

    uv run python scripts/orclord_flee_proof.py run --map prt_fild08 \
        --area /dev/shm/poring-lab-tmp/rogue/prt_fild08_area.npy --n 8 --seed 28 \
        --near 1 --toggle 25 --label fp2 \
        --model /dev/shm/poring-lab-tmp/orclord/model/orclord-v1.npz --sha256 43179452d01f8882c46669540b62d18a3b8e020ff685f2d765f41822c78ea1ff
