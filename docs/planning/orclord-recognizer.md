---
doc_type: design
hypothesis: "From pixels alone, a CPU recognizer cheap enough for the runner (<= 60 ms per 1280 x 720 frame, niced) tells 'the Orc Lord (mob 1190) or its Orc Archers (1189 / 1473) are in view' on gef_fild10 within 1 s of their first frame in view on >= 95 % of held-out lattice cells, with <= 1 false positive per 10 min of held-out hunting frames."
status: "SCORED 2026-10-25 21:34-21:37 ICT (once, frozen model sha256 43179452...): bar 1 FAILS (recall within 1 s 5 / 7 = 71.4 %: a spawn under a canopy, a spawn behind the summon's light pillar), bar 2 FAILS (2 false positives in the pilot's 10.6 held-out min = 1.89 per 10 min; supplementary s1 0.88), bar 3 PASSES (p95 53.7 ms). Pre-registered 20:20 ICT before any recognizer; Amendments A + B on DEV only. Offline only."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-prep.md, payf07-detector.md, ../../scripts/mvp_watch.py, ../../scripts/mvp_watch_study.py]
next_action: "Batt / the parent: decide whether the runner uses the frozen v1 (both cues) or the aura alone (section 6, POST-HOC: 0 FP in 33 min, the same 5 / 7 cells) for the live flee-rule proof; a second pre-registered watch with edge entries at 2-5 fps and >= 2 h of hunting negatives (section 8) to pass the bars."
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
