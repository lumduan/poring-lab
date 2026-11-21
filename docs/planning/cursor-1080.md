---
doc_type: plan
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [screen-size-ab.md, fullscreen-client.md, xmas02-1080-detector.md, xmas02-items-1080.md, gef10-cursor-unknown.md, ../adr/0020-block-programming-flows.md, ../../scripts/cursor_sword.py, ../../scripts/cursor_robust.py, ../../scripts/cursor_learn.py]
next_action: "Phase 1 probes on the lab at 1080 after the item round's overnight chain (the lab is busy until ~04:30)."
title: "The cursor at 1920x1080: why the hover check answers 'unknown' on far targets, and the fix (pre-registration)"
date: 2026-11-20
owner: Batt
---

# The cursor at 1080 (pre-registration, 2026-11-20)

Written before any probe of this round. Nothing below is edited after its commit, except by a
labelled, clock-stamped amendment (section 9).

## 0. What Batt asked

- 2026-11-20 ~21:1x: the order is the item model at 1080, then **the cursor at 1080**, then the
  false goblin alarms; "long".
- The same evening, from his live 1080 PC: **"from the clips, many times the bot still walks
  past monsters."**
  - His Run 11202049 (GPU, xmas02v1080): of 42 chosen boxes, 10 were struck. The cursor
    verdict was "unknown" 19 times, and a hover gave no verdict 24 times.

## 1. The facts (recorded; pointers in screen-size-ab.md and the code)

- **How a box target strikes** (the byte-pinned runner; cursor_sword is called by name):
  - one hover per box (`n_hover = 1` with box_now);
  - `cursor_sword.check`: two motions, then 64 x 64 crops read until the first read that is not
    unknown, or for CURSOR_WAIT_S 0.35 s;
  - colour recall against the sword / pickup / walk references. "sword" >= 0.75; "clear" =
    pickup >= 0.90, or walk >= 0.85 with sword < 0.60;
  - the strike happens only on "sword". "unknown" (no sword and no clear read in 0.35 s) = no
    strike, and she walks on.
- **At 1080 against 720:**

| measure | 720 | 1080 |
|---|---|---|
| unknown share on box targets | 0-2.4 % | 26-33 % (B), 36-48 % (B2 with fast reads) |
| kills per box engagement | ~0.7 | 0.32-0.38 |
| hover, grab to verdict | 254 ms | 293-460 ms |
| reads in 0.35 s | ~9 (every ~38 ms) | ~5 (every 49-50 ms; the first ~150 ms after the start) |
| reads that repeat the previous frame | not recorded | 29 % |

- **The trace (s11scr-diag, 589 checks)** shows that "unknown" reads see NEITHER cursor:
  - their best sword match has a median of 0.357 (151 of 248 under 0.40; only 11 near the bar)
    and their best walk match 0.485;
  - their targets lie far from the screen centre: a median of 160 px, against 62 for sword and
    59 for clear;
  - standing at 1080 the client draws the sword in time (the first at a median 110 ms, 34 of 40).
- Ruled out or weak:
  - a longer window alone (few near misses);
  - faster reads alone (the unknown share did not fall);
  - the Miss cue.
- **Not measured:** the frame rate IN MOTION at 1080 against 720, and what the 64 x 64 crop
  actually holds on an unknown read. The trace keeps recalls only, no pixels.

## 2. The question this round answers first

Why do far-target reads at 1080 show no cursor at all? The candidates, each testable:

1. **Timing:** in motion the client redraws the cursor late (0.35-0.4 s while scrolling, at 720)
   and the bus delivers fewer new frames, so 5 reads in 0.35 s may all predate the redraw.
2. **Place:** the cursor patch pastes the real pixels around the virtual pointer's real point. If
   the client draws the cursor elsewhere at a far point, the crop holds world, not cursor:
   - the hotspot offset;
   - the rounding of the 1.5 x mapping;
   - a pointer that has not moved yet.
3. **Shape:** the sword at 1080 differs from the references (native size, but another
   rendering).

## 3. Phase 1: probes (the lab at 1080, the lab's Rogue, immune for the moves, nothing struck)

- **P1, the pixels of a hover:** a probe tool (committed, outside the runner) that does
  cursor_sword.check's motions on far and near monster boxes and SAVES each read's 64 x 64 crop
  (both the virtual crop and the real pixels around the real point) for 1.0 s, at least 60
  hovers, standing and while walking.
  - Pictures of the lab's own client only, scratch, deleted after their verdict.
  - Each read is classified by eye-free rules: the sword / walk / pickup recalls, and the
    cursor's own colours anywhere in the real 160 x 160 around the point.
- **P2, frames in motion:** the bus counters (new frames per second, repeats) standing and
  walking, at 1080 and at 720 (one switch of the screen, as screen-size-ab.md did).
- **P3, when the cursor shows:** from P1, the time of the first sword read per hover, near and
  far, standing and walking.
- Phase 1 names the cause by these readings, in an amendment, before any fix is chosen.

## 4. Phase 2: the fix, chosen by the cause (outside the pinned runner)

- If timing: read for longer or wait for a NEW frame between reads (cursor_sword's own loop,
  `gap_s` and the grab), and/or a second hover on an unknown.
  - Any change of the runner's own constants goes through a Run-time patch, as flow_play
    already does for its tables; the file stays byte-identical.
- If place: correct the cursor patch's real point (ro_agent's real_xy / CURSOR_BOX /
  client_view).
- If shape: references cut at 1080 (cursor_learn already learns the WALK arrow per Run; the
  sword would need its own proof, ADR-0020 Amendment V).

## 5. The bars, each scored once

### 5a. The hover at 1080 (a probe block, immune, the lab)
- Unknown share on far box hovers (>= 120 px from the centre, >= 60 hovers): <= 5 % (720's level
  is 0-2.4 %).
- Sword recall on hovers over a live monster (packets: a monster on the hovered cell):
  >= 90 %.
- No false sword on hovers over open ground (>= 40): <= 2 %.

### 5b. In play at 1080 (the decisive bar; screen_ab.py, 3 valid runs a side, the deployed model)
- A = today's code, B = the fix.
- kills/h: mean(B) - mean(A) > +2 SE.
- The unknown share on box targets: B <= 5 %.
- deaths B <= A; errors none new.
- Reported: kills per box engagement, the share of chosen boxes struck, loot/h, each as a % of
  Batt's run (Amendment 14 of xmas02-1080-detector.md: >= 56.5 % of his kills/h is the line he
  set for 1080).

## 6. The order and the times (estimates)

1. The probe tool (P1), offline with tests: ~2 h. Then P1-P3 on the lab: ~1.5 h, after the item
   chain.
2. The cause amendment; the fix with tests: ~2-3 h.
3. 5a: ~1 h. 5b: ~2.5 h.

## 7. What it runs beside

- The item round (xmas02-items-1080.md) has the lab overnight. This round's lab steps wait for
  the chain's end.
- Offline analysis of the existing trace and sessions may run at any time.

## 8. Not in this round

- The false goblin alarms (next, Batt's order).
- The 0.5 s frame lag (the lead is the runner's own rule).

## 9. RESULTS and AMENDMENTS (clock-labelled)

### Amendment 1 (2026-11-21 00:28 ICT from `date`): Batt's live Run; a crash at the frame's edge, fixed; the trace re-read; the P1 tool

Written before any probe of this round.

- **Batt's live Run 11202100** (his 1080 PC, GPU 100 % of 11,409 detections, xmas02v1080):
  - 180 min, 311 kills, by hunt core:

    | hunt | span | kills | kills/h | strikes | box targets |
    |---|---|---|---|---|---|
    | 1 | 21:01-22:48 (107.1 min) | 234 | 131 | 322 | 558 |
    | 2 | 22:48-23:27 (38.6 min) | 77 | 120 | 96 | 199 |
    | 3 | 23:27-00:01 (33.9 min) | 0 | 0 | 0 | 22 |

  - Hunt 1 is 57 % of Batt's 228.5 kills/h, hunt 2 52 %; the whole Run 45 %.
  - **Hunt 2 ended on a code error in the cursor reader** (23:27:16):
    `ValueError: could not broadcast input array from shape (3,0,64) into shape (3,64,64)`
    (cursor_robust._planes, from cursor_sword.check). A box whose hover point lay within 32 px
    of the virtual frame's TOP asked for crop rows above it; the virtual client's whole-frame
    path sliced `vf[y:y+h]` with a negative y and returned NO rows. The Run's retry restarted
    the hunt core 19 s later.
    - FIXED on branch cursor-p1 (`ro_agent.box_of`, `desktop_clip`): every grab returns the size
      asked for, the part off the frame (or off the desktop) black. The runner's ring crop at the
      same point (80 x 80, in the pinned file) is fixed by the same change. Tests:
      test_ro_agent_fullscreen (the 1080 top-edge crop; the real path's clip and pad).
    - It merges after the item chain (no code change on main while a block runs).
  - **Hunt 3 played 34 min with no kill:** 49 Fly Wings (31 "idle", 10 "stuck", 3 "garm", 3
    "pos_unread", 2 "dead_end"), 0.92 boxes per detection (hunts 1-2: 2.3, 2.2), 7,123 goal
    events; it ended on "position unread for 30 s", and the next start on "her cell did not read
    on the minimap readout within 5.0 s".
    - The minimap never named the map in this Run (best xmas_dun02 0.27 at the start, then
      0.19, then moc_fild14 0.14, prontera 0.12; a map is named at 0.40).
    - Not this round's question (it is the position, not the cursor). Recorded for Batt.
  - The bag count at the start failed ("Alt+E showed no bag"): live still had the code before
    T-I5 (the 1:1 inventory panel). Live was updated at 00:05 (main d367a1f5).
- **The trace re-read** (s11scr-diag, 589 checks, offline):
  - the first read comes at a median 151 ms after the first motion (p90 161);
  - SWORD and CLEAR are decided at a median ~250 ms (the third read): the client draws the
    cursor at the new point about 0.25 s after the motions;
  - "unknown" checks read neither cursor on their FIRST or their LAST read (sword 0.30 / 0.30,
    walk 0.32 / 0.39 medians); 2 of 248 ever read walk >= 0.85, 11 sword >= 0.60;
  - none of the 589 points lies within 34 px of a lab panel's virtual box or the frame's edge;
  - the pointer's jump from the previous check: median 42 px before an unknown, 66 before a
    sword (a long jump does not explain it).
  - So whether the cursor arrives LATER than 0.35 s, or not at that point at all, is open:
    exactly what P1's 1.0 s window and its real 160 x 160 box answer.
- **The P1 tool** (`scripts/cursor_probe_1080.py`, branch cursor-p1, 14 tests; the older
  cursor_probe.py is cursor@probe's, unrelated):
  - `hovers`: the runner's hover point (the box centre), FAR >= 120 px within the runner's
    220 px reach, the bands alternated, the two motions, then reads for 1.0 s: the reader's
    64 x 64 crop and the real 160 x 160 around the real pointer per new frame (repeats keep
    their time only), and the real 160 x 160 around the previous pointer point at the start and
    at 0.35 s. `--mode walk`: a walk click first (after two WALK-arrow reads; census-registered),
    the hover 0.15 s after it.
  - `frames`: P2's bus counters, standing or walking.
  - `analyse` (offline): each read's recalls and verdict, the black share of the reader's crop,
    its difference to the real pixels at the point, the cursor searched in the real box (64 x 64
    slid by 4 px); the hover's class (sword_at_point / sword_offset / walk_at_point / old_place /
    nothing); the runner's decision replayed inside 0.35 s and at 1.0 s; the first SWORD's time.
  - The reads are denser than the runner's (no recall in the loop), so the 0.35 s replay is the
    runner's best case inside its window. 60 hovers of each mode at least (P1's minimum), far and
    near alternated.
- **Next:** the item chain ends ~04:30; then the merge; then P1 stand and walk, P2 stand and
  walk (1080), on the lab, immune.

### Amendment 2 (2026-11-21 00:45 ICT from `date`): the bus writes ~30 frames a second at 1080 too (offline)

- From the runner's own records (hp_read's lf2 frame ids, the bus writer's ids, the rate between
  consecutive reads 0.05-3 s apart): s11scr-720-r01A **29.8** frames/s (p10 29.3, p90 30.2; 9
  samples), s11scr-1080-r01B **29.8** (28.3 / 30.4; 24), ifT2-play-r01B (1080, tonight) **29.6**
  (28.9 / 30.1; 25).
- So the bus is not slower at 1080: the "fewer new frames" half of candidate 1 is weak at the
  bus. What the bus cannot say is when the GAME redraws its cursor (the client's own frame
  rate); P1's 1.0 s reads and P3 answer that. P2 still measures standing against walking.
- The samples are sparse (lf2 runs only on some reads) and none is split by motion.

### Amendment 3 (2026-11-21 07:25 ICT from `date`): P2 recorded; the first P1 is VOID (a bug in the probe), fixed; P1 again after the item training

- **The runs** (06:13-06:20, the lab at 1080, the Rogue immune -- judged on the 03:45 frame, the
  same game session since -- the GPU detect server beside it as the runner's, after the item
  stagings; `probe_run.sh`, scratch).
- **P2, the bus counters** (`frames`, 30 s each):

  | mode | reads | bus fps (the writer's frame ids) | new frames read / s | repeat share | walk clicks |
  |---|---|---|---|---|---|
  | stand | 2,654 | **31.8** | 29.1 | 0.706 | 0 |
  | walk | 1,302 | **29.8** | 16.1 | 0.682 | 13 |

  - The bus writes ~30 frames a second walking as standing (as Amendment 2 found offline). The
    walking "new frames read / s" counts the reader's dead time inside its 13 walk clicks (the
    reads pause there), so it is not a slower bus. Candidate 1's "fewer new frames" half is
    weak at the bus. The client's own redraw of its cursor stays P1's question.
  - The 720 side of P2: Amendment 2's offline measure stands for it (no screen switch done).
- **P1 (`hovers`, 60 standing + 60 walking): VOID.** The probe's target picker took ANY box in
  reach, her own `player` box included: **116 of the 120 hovers went over the Rogue herself**
  (60 / 60 standing, 56 / 60 walking; 4 monster boxes). Over her own character the client draws
  the walk arrow, and the analysis says so (standing: 60 / 60 `walk_at_point`, no sword read).
  So this P1 says nothing about monster hovers. It is not used.
  - Why it slipped: the picker's test used made-up class names. Few monsters stood near the
    start cell then (the stagings' @killmonster2 had just cleared the map).
  - **Fixed (01ea9447):** only `monster` boxes are targets (TARGET_CLS, the runner's own box
    targets in dungeon_hunt's watcher); a test pins the player and NPC boxes out.
  - The walking analysis was stopped (the same void data); the standing one's output is kept as
    the evidence of the slip.
- **P1 again** after the item training frees the GPU (~08:45): the same tool and settings with
  the fix, the Rogue still immune (judged again on a frame), after a wait for the map's
  monsters to stand around the start cell. Then P3 and the cause amendment, before any fix.

### Amendment 4 (2026-11-21 09:04 ICT from `date`, BEFORE any fix is chosen): P1 and P3 -- THE CAUSE is motion: standing the cursor reads every time; walking it comes late and the point misses

- **The runs** (07:54-08:12, the lab at 1080, the Rogue immune: judged by two toggles on frames at
  07:32-07:33, "Returned to normal state." then "You are now immune to attacks."; the GPU detect
  server beside it, detection median 61 ms standing / 86 ms walking). Tool fixes before them,
  both recorded: 01ea9447 (monster boxes only, Amendment 3) and 90fd1e22 (a hover waits up to
  120 one-second looks in a row for a monster in reach: an immune Rogue's monsters wander; the
  07:34 rerun had stopped after 40 misses in all). Walking first, then standing; 60 hovers each,
  every one over a `monster` box; 1.0 s of reads per hover.
- **P1 / P3, the analysis** (`cursor_probe_1080.py analyse`, stride 4):

  | hovers | n | the runner's 0.35 s decision (replayed) | at 1.0 s | classes | first sword read (from the first motion) |
  |---|---|---|---|---|---|
  | stand, far (>= 120 px) | 51 | sword 51 (**unknown 0 %**) | sword 51 | sword_at_point 51 | median 214 ms, p90 232 ms |
  | stand, near | 9 | sword 9 | sword 9 | sword_at_point 9 | 225 / 238 ms |
  | **walk, far** | 54 | sword 24, clear 6, **unknown 24 (44.4 %)** | sword 27, clear 27 | sword_at_point 27, **walk_at_point 27** | **229 / 409 ms** (n 27) |
  | walk, near | 6 | sword 1, clear 1, unknown 4 | sword 2, clear 4 | sword_at_point 2, walk_at_point 4 | 294 / 514 ms (n 2) |

  - No hover anywhere was `nothing`, `old_place` or `sword_offset`: the cursor is always drawn,
    at the point, in the shape the references read.
  - Bus reads: ~29.8 fps median per hover, ~55 % repeats, the first read ~130 ms after the motion,
    standing and walking alike (P2: the bus ~30 fps both ways).
- **THE CAUSE (section 2's candidates):**
  1. **Timing -- yes, in motion only.** Standing, the client draws the sword 214 ms (p90 232) after
     the motions: inside the runner's 0.35 s, every time. Walking (the camera scrolling), the
     sword comes later and spread out (p90 409 ms): the runner's 0.35 s window ends before it on
     many hovers, which then read "unknown" (24 / 54). With 1.0 s of reads no hover stays unknown.
  2. **Place -- yes, in motion only, and the larger half.** Walking, 27 / 54 far hovers end with
     the client's WALK arrow at the point: no unit under the pointer. The hover point is the box
     centre of a frame read before the scroll moved the world under it (and the frames lag the
     server, memory: ~0.5 s). Standing, 0 / 51.
  3. **Shape -- no.** 60 / 60 standing hovers read the sword with the lab's references.
  - The cursor patch's mapping is right (standing 100 % at the point; no cursor elsewhere).
- So the 1080 gap is a **hover while the camera scrolls**: half of those miss the monster, and a
  quarter more resolve too late for the 0.35 s window. 720's 0-2.4 % unknown (screen-size-ab.md)
  is the same rule with targets nearer her (the trace: far targets, 160 px vs 62).
- **Not yet chosen (section 4, by this cause):** e.g. (a) a hover only once she has stopped (a far
  box target while walking: stop, then hover), (b) the hover point led by the scroll, (c) a longer
  read window in motion (helps the timing half only). The fix comes in its own amendment with
  tests, then 5a (the hover bar, immune) and 5b (play).
- Evidence (scratch, RAM): p1c-walk / p1c-stand (hover JSON + crops), the analyses'
  `summary.json`; pictures of the lab's own client only, archived or deleted with this verdict.

### Amendment 4a (2026-11-21 09:06 ICT from `date`, still before any fix): the same split in PLAY, from the runner's own records

- The runner already hovers a box target only after its walk settles (BOX_SETTLE_S 1.2 s) and,
  with `still_strike` ON (the box's default), after a STILL scene (3 frame pairs scrolling
  < 2 px, at most 1.5 s). Its `box_target` records (offline, no new run):

  | block | box targets | still wait timed out | after a still scene: sword / unknown / clear | after a NOT-still scene (timed out): sword / unknown / clear |
  |---|---|---|---|---|
  | 720 (s11scr-720, 3 runs) | 224 | 57 (25 %) | 118 / **0** / 0 | 16 / **1** / 0 |
  | 1080 (the 12 item-chain pilots) | 1,127 | 373 (33 %) | 411 / **154 (26 %)** / 24 | 12 / **162 (92 %)** / 2 |

  (the rest of each row: no box picked, or off screen). Still-wait median 547 ms at 720, 842 ms
  at 1080.
- So in play, as in P1: at 720 a hover reads the sword whatever the scene did; at 1080 a hover
  after a scene that never went still fails 92 %, and even after a "still" scene 26 % (P1
  standing: 0 %). The still check runs on the virtual frames, which at 1080 come slower (a whole
  virtual frame ~69 ms, ro_agent's measure), so its 3 pairs span more time; why a "still" scene
  still fails a quarter of the time at 1080 is the next reading (the targets' own motion, the
  scene's measure on the scaled world), before the fix is chosen.

### Amendment 4b (2026-11-21 09:07 ICT from `date`, still before any fix): the unknowns follow how long she was MOVING

- The same records, the box targets with a cursor verdict, binned by the still wait (how long the
  scene took to read still: long = she or the camera moved for most of it):

  | still wait | 720 unknown | 1080 unknown |
  |---|---|---|
  | 300-600 ms | 0 / 75 | 8 / 208 (4 %) |
  | 600-900 ms | 0 / 14 | 19 / 204 (9 %) |
  | 900-1200 ms | 0 / 9 | **59 / 78 (76 %)** |
  | 1200-1450 ms | 0 / 6 | **47 / 69 (68 %)** |
  | timed out (1.5 s) | 1 / 31 (3 %) | **183 / 206 (89 %)** |

  - Among the 1080 "still" hovers, the unknown ones had waited a median 1,169 ms, the sword ones
    602 ms; their distance (143 vs 171 px) and their detection's age (70 vs 66 ms after the
    still) hardly differ.
- So at 1080 a hover fails when it follows a long motion, even once the 3-pair check says still;
  at 720 it never mattered. P1 says what the failures are in motion: half no unit under the
  point, the rest a late sword. **The fix's direction (chosen in its own amendment, with tests):**
  the hover waits on HOW LONG the scene has been still at 1080 (not only the 3 pairs), and/or a
  second fresh detection and hover after an unknown, measured by 5a (a walk-then-stop probe
  block) and decided by 5b (play). The pinned runner stays untouched (a Run-time patch, as
  flow_play's others, and a setting with today's values as the default).

### Amendment 5 (2026-11-21 12:07 ICT from `date`): the STOP probe; THE FIX CHOSEN (the cursor read window, a setting)

- **The stop probe** (c5935558's `--mode stop`, 11:04-11:27, immune: "You are now immune to
  attacks." read at 11:02 after the pilots' OFF; 60 monster hovers, 48 far): a walk click (5-8
  cells), the runner's own still rule on the virtual frames, then the hover 0 / 0.25 / 0.5 / 0.75 /
  1.0 s later (12 each). The still rule TIMED OUT (1.5 s) on 49 of the 60 walks: she was still
  scrolling. The CPU beside it carried the item round's ONNX predictions (nice 10); the reads'
  first-read times (~130 ms) match P1's.

  | far hovers, delay after the still wait | n | runner unknown at 0.35 s | first sword median / p90 | at 1.0 s |
  |---|---|---|---|---|
  | 0.00 s | 10 | 60 % | 464 / 603 ms | sword 10 |
  | 0.25 s | 10 | 80 % | 552 / 701 ms | sword 6, walk arrow 4 |
  | 0.50 s | 11 | 64 % | 364 / 686 ms | sword 8, clear 2, nothing 1 |
  | 0.75 s | 7 | 43 % | 327 / 616 ms | sword 7 |
  | 1.00 s | 10 | 10 % | 227 / 259 ms | sword 9 |

  (near hovers: 12, too few to split.) So right after she stops the 1080 client draws its sword
  LATE (median ~0.35-0.55 s, p90 ~0.6-0.7 s), and about 1 s after the stop it is back to the
  standing time (P1 stand: 214 / 232 ms). The cursor does come, at the point; the runner's 0.35 s
  window gives up first.
- **THE FIX (section 4's "timing" branch):** the runner's cursor read window `CURSOR_WAIT_S`
  becomes a SETTING (a runner constant set with --tune, like STILL_N; default 0.35 s = today's,
  so 720 and every box that does not set it are unchanged), and a 1080 box sets **0.75 s**.
  - Why the window, not a wait after the stop: cursor_sword.check ends at the FIRST decision
    (a sword or a clear read), so a longer window costs time only on hovers that would otherwise
    end "unknown" (a lost engagement); a fixed 1 s wait would cost every engagement.
  - 0.75 s: above the p90 of the first sword after a stop (0.6-0.7 s), still under P1-walk's
    late tail only partly (p90 409 ms in motion, but half those points had no unit under them:
    the window cannot fix a point that misses).
  - The pinned runner stays byte-identical: --tune reads the registry's names (poring_flow
    .settings), and hover() reads CURSOR_WAIT_S at call time.
- **The bars, as registered (section 5), on NEW data:** 5a = a fresh probe block (stop mode,
  >= 60 far hovers, immune) with the runner replayed at 0.75 s: unknown <= 5 %; sword recall /
  false sword as registered where the block measures them. 5b = screen_ab at 1080, A = today's
  box, B = the same box with CURSOR_WAIT_S 0.75 (one setting, checked: the runner's argv differs
  in that --tune alone), 3 valid runs a side: kills/h B - A > +2 SE, box-target unknown B <= 5 %,
  deaths B <= A, no new errors.

### Amendment 6 (2026-11-21 13:28 ICT from `date`): 5a at 0.75 s FAILS (6.3 % > 5 %); the window 1.0 s chosen, a fresh 5a block

- **5a, scored once** (`probe_run5.sh`, 12:21-12:38, immune: judged ON at 11:02, the same session
  since; a FRESH stop-mode block of 80 monster hovers, 63 far; the runner replayed at today's
  0.35 s and at the fix window 0.75 s; analysis 13:27):

  | far hovers (63) | unknown at 0.35 s (today) | unknown at **0.75 s (the fix)** | unknown at 1.0 s |
  |---|---|---|---|
  | pooled | 42 (66.7 %) | **4 (6.3 %)** | 0 |

  Per delay after the still wait (far): 0.00 s: 12 / 15 unknown at 0.35, 0 at 0.75 (7 of the 15
  end on the walk arrow: no unit under the point); 0.25 s: 9 / 12 -> 0; 0.50 s: 10 / 12 -> **3**;
  0.75 s: 6 / 12 -> **1**; 1.00 s: 5 / 12 -> 0. The first sword in this block: median 226-588 ms
  by delay, p90 up to 803 ms (the stop probe's p90 was 0.6-0.7 s).
- **The bar (unknown <= 5 % on >= 60 far hovers): 6.3 % -> FAIL** for 0.75 s. The window cuts the
  unknowns ten-fold, but not to the bar.
- **The next choice (its own amendment, before its block):** the window **1.0 s** (this block's
  late swords reach 0.8 s; the check still ends at the first decision, so the extra time is spent
  only on hovers that would otherwise end unknown). Its 5a is a NEW fresh block (stop mode, >= 60
  far), the runner replayed at 1.0 s, the same bar, scored once. 1.0 s is also the probe's own read
  window, so the replay at 1.0 s needs no new reads. If it fails too, the timing branch is not
  enough and the place branch (a fresh detection and second hover after an unknown) comes next.

### Amendment 7 (2026-11-21 17:08 ICT from `date`): 5a at 1.0 s PASSES (1.2 % <= 5 %, 82 far hovers); 5b next

- **5a block 2, scored once:** `probe_run9.sh`, analysis 17:07, summary sha256
  `431993c62a1ef28e...`.
  - A fresh stop-mode block of 104 monster hovers, 82 far, the runner replayed at 1.0 s
    (Amendment 6).
  - Recorded in three parts in the same lab setup, each immune, judged on a frame:
    - 13:28-13:30, 7 hovers;
    - 13:45-13:51, 17 hovers; a person's mux switch at 13:51 stopped it, as it must;
    - 16:10-16:33, 80 hovers, after the dev client's crash (an access violation after Batt's
      dev Run) was recovered at 16:08 and immunity re-judged at 16:09 ("You are now immune to
      attacks.").

  | far hovers by delay after the still wait | n | unknown at 0.35 s (today) | at 0.75 s | at **1.0 s (the fix)** | first sword, median / p90 |
  |---|---|---|---|---|---|
  | 0.00 s | 16 | 11 | 0 | 0 | 392 / 631 ms |
  | 0.25 s | 18 | 13 | 2 | 1 | 377 / 668 ms |
  | 0.50 s | 17 | 12 | 1 | 0 | 421 / 711 ms |
  | 0.75 s | 16 | 7 | 0 | 0 | 287 / 605 ms |
  | 1.00 s | 15 | 3 | 0 | 0 | 227 / 384 ms |
  | **pooled** | **82** | **46 (56.1 %)** | 3 (3.7 %) | **1 (1.2 %)** | |

- **The bar (unknown <= 5 % on >= 60 far hovers): 1.2 % -> PASS** for 1.0 s.
  - The 0.75 s column is reported, not scored: 0.75 s failed its own block (Amendment 6), and
    this block was registered for 1.0 s.
- **Next: 5b in play** (Amendment 5's A/B):
  - `screen_ab` at 1080, A = the box, B = the box with `--box-set CURSOR_WAIT_S=1.0`;
  - 3 valid runs a side, immunity OFF;
  - after the round-7 item pilots, which hold the dev lab now (items come first in Batt's
    order).

### Amendment 8 (2026-11-21 17:15 ICT from `date`, BEFORE any code or data of it): Batt's idea, "click on sight", as 5b's arm C

- **Batt's words** (2026-11-21, after Amendment 7): "Try it without waiting for the sword? See it,
  click to strike at once; an arrow over the monster's head means the target is locked."
- **What the data already says:**
  - The late sword is the client's cursor being slow to REDRAW after a stop.
    - In Amendment 7's block the point was over the monster nearly every time: 1 of 82 far hovers
      never showed a sword within 1.0 s.
    - A click at once would usually attack, without the 0.29-0.42 s median / 0.6-0.7 s p90 wait.
  - The idea was tried at 720 in hunt_flow v12 (burst strike: "he clicks until the client draws
    the ARROW"). Its arrow reader then measured, after a click: P(arrow | the attack registered)
    0.71, P(arrow | not) 0.08, first seen at a median 0.44 s.
  - The runner already watches its lock arrow and the strike's end after every strike: that
    confirmation stays as it is.
- **Arm C, "click on sight":** a player setting, off by default; the live player wraps
  `cursor_sword.check`, and the runner file stays byte-identical.
  - The hover point lies inside a FRESH monster box: the detector's last read, <= 0.5 s old,
    from the Sight holder.
  - At such a point the sword check reads for at most **0.10 s**.
  - Its verdict is used when it decided: "sword" strikes; "clear" (the walk arrow) does not.
  - An undecided "unknown" counts as "sword": the click goes.
  - Every other hover is untouched (the walk gate, the loot hovers, a point outside any monster
    box). They keep the full check.
- **5b becomes three arms** at 1080, each 3 valid runs, not immune, interleaved, scored once:
  - A = the box (CURSOR_WAIT_S 0.35);
  - B = CURSOR_WAIT_S 1.0 (5a passed);
  - C = click on sight.
- **Judged against A, as 5b registers it** (kills/h > +2 SE; deaths and errors none worse).
  Reported for each arm from the lab's packets:
  - the share of strike clicks that became an attack request;
  - the walk requests that followed a strike click (the cost of a stale box);
  - the time from the box to the first attack request.

### Amendment 9 (2026-11-21 18:42 ICT from `date`, BEFORE any data of it): Batt's "detect fast, on the GPU" as 5b's arm D

- **Batt's words** (2026-11-21, on Amendment 8): "This will work, because a person plays that way:
  see the monster, click to strike, check the lock by the arrow over its head; then the character
  attacks by itself. The key point is detecting monsters fast, the faster the better. Otherwise the
  monster moves, and the click becomes a walk, as with our bot at first. I strongly recommend the GPU
  for the detection." He also okayed the test ("go ahead").
- **What the data says** (offline; the 18 round-6/7 item pilots at 1080, 380 min, the hunt cores'
  `detections.jsonl` and strike events; `/dev/shm/poring-lab-tmp/box_age.py`):
  - **The GPU is already the detector** in every 1080 run, dev and live. It is the OpenVINO detect
    server on the Arc: forward p50 23.8 ms / p95 38.0 ms in the pilots. The two servers' own minute
    stats at 18:3x, both labs playing: dev p50 18-19 / p95 27-29 ms, live p50 19 / p95 27-30 ms.
    **The GPU is not the bottleneck.**
  - **The runner LOOKS only once a second.** The box watcher's rhythm is `BOX_EVERY_S` 1.0: 24,453
    world detections in 380 min, 1.07 a second, gap p50 1.00 s / p90 1.02 s. The HUD twin's frames
    (~3.5 a second) feed the alarm and the console, not the box path.
  - **The box's age at a box strike:** p10 0.21 / p50 0.23 / p90 0.57 s (628 strikes). Ends by age:
    - < 0.25 s: 428, 20 % "bound" (no confirmation);
    - 0.25-0.5 s: 113, 20 %;
    - 0.5-1 s: 87, 30 %.
    This is a small sample with no control, but it points Batt's way: older boxes miss more.
  - **4 looks a second was tried once, at 720:** 4AD, pilot p22, 2026-11-09, `--box-every 0.25`.
    It FAILED (kills per monster seen 0.531, 70.7 kills/h vs 108). The extra targets it found were
    far, 9+ cells, and behind walls: the server ignores such walk clicks
    (`server-walk-click-limits`). The reach check that skips them (4AE, `--reach-check`) is in
    today's base: the 1080 run_start carries `reach_check`, and ifH6 logged 48 `reach_skip`.
    p22's cause is therefore covered, and 4 looks a second has never been tried with it.
- **Arm D, "click on sight, looking fast":** arm C plus `--box-set BOX_EVERY_S=0.25` (4 looks a
  second).
  - The runner's own flag, dungeon@9.11, and a setting; the runner file stays byte-identical.
  - BOX_FRESH_S, the settle, the reach check and every other value are unchanged.
- **5b becomes four arms** at 1080: A (the box), B (CURSOR_WAIT_S 1.0), C (click on sight), D (C +
  BOX_EVERY_S 0.25).
  - Each arm gets 3 valid runs of 25 min, not immune.
  - Interleaved A, B, C, D, then again twice; each run is its own one-run series of screen_ab.py.
  - Scored once, by a scorer committed before the first 5b score.
- **Judged:** C and D, each against A, as 5b registers it.
  - kills/h: mean(arm) - mean(A) > +2 SE (Welch);
  - deaths: no worse than A;
  - errors: none new.
  - B is judged the same way (Amendment 8).
- **Guards for arm D** (the GPU is shared with Batt's live Runs: `yield-gpu-to-live-runs`):
  - **D1:** the dev detect server's p95 <= 35 ms at 4x the rate (4AD's D1).
  - **D2:** the live detect server's p95 <= 35 ms in every minute stat during a D run, while a live
    Run plays.
  - A D2 breach for 3 minutes in a row ends that D run as invalid ("yielded"), and the series pauses
    until the live Run ends.
- **Reported for every arm:**
  - world detections a second;
  - the box's age at each strike click, and the strike ends by that age;
  - the strike clicks that became an attack request, and the walk requests after a strike click
    (packets);
  - the time from the box to the first attack request;
  - escapes and Fly Wings per hour (the alarm reads more frames in D);
  - z/h (economy, every run).
- **Order beside the item round:** the round-7 item evaluation (xmas02-items-1080.md A22) comes
  first, per the standing order.
  - Its GPU predictions wait for a quiet GPU: no live Run and no dev detect server.
  - Once Batt's live Run ends, the 5b chain holds before its next run until the evaluation's GPU and
    ONNX steps are done.

### Amendment 10 (2026-11-21 20:20 ICT from `date`, BEFORE any 5b data): D2 is reported, not a stop (Batt); a new session before the series

- **Batt's words** (20:2x, on the overnight plan): "No need for dev to stop and wait; run it long.
  It is fine if live gets slower."
  - D2 no longer stops a D run or pauses the series.
  - The live detect server's minute p95 during each D run is still logged and REPORTED
    (`<label>.d2`).
  - D1 (the dev server's p95 <= 35 ms) stays a reported guard as before.
- **The order stays as written** (Batt, same message): the round-7 item evaluation's GPU steps first,
  then 5b, then the ranged-attacker A/B (ranged-attacker-1080.md, written next).
- **A new game session before the series:** rAthena was recreated at 20:12-20:14 for group 20's
  `@zeny` (Batt's OK at 20:11, the zeny reader's test). The Rogue logged in again at 20:15:36 and
  is back at 0 zeny, her fixed state. Immunity is judged OFF again on this session before the
  first 5b run; the chain then keeps this session.

### Amendment 11 (2026-11-21 21:55 ICT from `date`, before any 5b score): c5b-B1 is VOID, B gets a fourth run

- **What happened (my error, not the arm's):** round 7's item score wrapper
  (docs/records/scorers/xmas02_items_r7_score.sh) waited for 5b's end with `grep "CHAIN DONE"` on
  5b's log.
  - That log's 21:07 line "hold ends: [21:06:49] CHAIN DONE" quotes the item evaluation's own last
    line, so the wrapper started at 21:37:47, in the gap after A1.
  - Its CPU latency ran during B1's setup and start (21:37-21:45), and its GPU latency step queried
    B1's detect server.
  - At 21:51:37 its cleanup KILLED the dev detect server, which was B1's: from then on B1's
    detections were the CPU path ("down", ~185 ms).
- **Ruling:** B1 is void, whatever its numbers. It was stopped by its own STOP file and marked
  `c5b-B1.yielded`, so the chain gives B a fourth run (c5b-B4) after the twelfth. B is scored on
  B2, B3, B4 (`--arm B=c5b-B2+c5b-B3+c5b-B4`). A1 (21:12-21:37) ended before the wrapper started:
  valid.
- **The fix:** the corrected wrapper (xmas02_items_r7b_score.sh) waits for 5b's OWN last line,
  exactly (`^\[hh:mm:ss\] CHAIN DONE$`), and for no screen_ab run.

### Amendment 12 (2026-11-22 03:09 ICT from `date`, before any 5b score): C1 void (a person's click); C3 not valid by the committed rule; C gets a fifth run

- **The chain ended at 03:03:48.** Valid by the COMMITTED rule (`screen_ab.valid`, which
  cursor_5b_score.py applies: >= 80 % of the 25 min played, or a home end; rc 0):
  A1 A2 A3, B2 B3 B4, C2 C4, D1 D2 D3. B1 is void (Amendment 11).
- **C1 (21:57-22:01) is VOID, an outside event.** The dev input log shows a person's mode change
  on the DEV console: `set_mode` BOT at 22:01:03 and ASSIST at 22:01:06 (`source: human`).
  - The hunt core stops when the mux leaves the mode it started in ("mux left ASSIST (BOT):
    stopping"), as it must (it never fights a person).
  - Not the arm's doing.
- **C3 (01:23-01:38) ended after 15.0 min by the runner's own safe end:** "stock_out: item 504
  reads 0 on the hotbar" (8 White Potions used), then the Butterfly Wing home (geffen:
  `relocate_no_block`).
  - The cause, from its packets (report-only; docs/records/scorers/c5b_dmg_taken.py, verbatim): the
    damage she took jumped at minute 10 (2,418 in that minute). One Cruiser, a ranged attacker
    (attack range 7), did 1,670 of the run's 6,955.
  - Damage taken a minute: C3 454. The other 11 full runs: 157-248 (C2 182, C4 248).
  - Heals used: C3 8; the full runs 0-4.
  - This is the problem of ranged-attacker-1080.md (Batt's Cruiser clip), the next A/B on dev.
- **Ruling: the committed rule stands; it is not changed after seeing this.**
  - C3 played < 80 % and its end is not a home end, so it is not in C's kills/h line.
  - The chain's "one more run" counted runs 1-3 only, so C has 2 valid runs. 5b registers 3 valid
    runs a side, so C gets a FIFTH run (c5b-C5), now. It uses the same preamble and flags, and
    starts after round 7's score wrapper (xmas02_items_r7b_score.sh) has ended
    (docs/records/scorers/c5b_c5.sh, verbatim).
  - If C5 is not valid either, C is judged on its 2 valid runs (the scorer allows it), and the
    report says so.
- **Scored once, after C5:**

      cursor_5b_score.py score --arm A=c5b-A1+c5b-A2+c5b-A3 --arm B=c5b-B2+c5b-B3+c5b-B4 \
          --arm C=c5b-C2+c5b-C3+c5b-C4+c5b-C5 --arm D=c5b-D1+c5b-D2+c5b-D3

  - C3 is passed IN the C list, so the committed `valid` excludes it from kills/h while its deaths
    and errors still count for C. C1 and B1 (void) are left out.
  - The packet measures (cursor_5b_packets.py) for the same runs, beside it.
- **Reported beside the verdicts (decides nothing):**
  - the kills/h line again with C3's own rate (its 15.0 min) added, as a sensitivity;
  - per arm: the runs ended by a stock-out, the damage taken a minute and the heals used
    (packets).

### RESULT 5b (2026-11-22 03:49 ICT from `date`): scored ONCE -- B, C and D are each NOT BETTER than A

`cursor_5b_score.py score --arm A=c5b-A1+c5b-A2+c5b-A3 --arm B=c5b-B2+c5b-B3+c5b-B4
--arm C=c5b-C2+c5b-C3+c5b-C4+c5b-C5 --arm D=c5b-D1+c5b-D2+c5b-D3` (Amendment 12; the dev checkout
at 20cdf35a, the scorer unchanged since a623d7ad; `score-5b.json` sha256 f84c6e39...). 3 valid
runs a side (C3 not valid by the committed rule: 14.4 min, a stock-out).

| arm | kills/h per run | mean (SE) | % of Batt's 228.5 | vs A: diff / 2 SE | verdict |
|---|---|---|---|---|---|
| A the box (0.35 s) | 87.5, 94.7, 62.9 | 81.7 (9.6) | 35.8 % | | |
| B CURSOR_WAIT_S 1.0 | 104.5, 106.6, 94.8 | 102.0 (3.6) | 44.6 % | +20.3 / 20.6 | NOT BETTER |
| C click on sight | 89.5, 82.4, 97.3 | 89.7 (4.3) | 39.3 % | +8.0 / 21.1 | NOT BETTER |
| D C + 4 looks a second | 89.9, 77.5, 97.1 | 88.2 (5.7) | 38.6 % | +6.5 / 22.4 | NOT BETTER |

- Deaths 0 and errors 0 in every arm. B's cursor-unknown share on box targets 2.6 % (bar <= 5 %:
  PASS).
- B misses its bar by 0.3 kills/h (1.97 SE). A's spread (62.9-94.7) makes the SE wide.
- **The sensitivity (Amendment 12, decides nothing):** with C3's own rate (112.8 kills/h over
  14.4 min) in C: 95.5 (6.5), +13.8 against a 2-SE bar of 23.3. Still NOT BETTER.
- **Reported (decides nothing):**

  | arm | strike clicks | became an attack | became a walk | box -> attack p50 by run (s) | loot/h | Fly Wings/h | alarm flies |
  |---|---|---|---|---|---|---|---|
  | A | 116 | 88.8 % | 11.2 % | 1.54, 1.57, 1.49 | 112.4 | 34.8 | 40 |
  | B | 119 | 81.5 % | 15.1 % | 1.56, 1.56, 1.62 | 131.1 | 26.7 | 33 |
  | C | 202 | 64.4 % | 32.7 % | 1.42, 1.65, 1.61, 1.40 | 111.6 | 24.2 | 27 |
  | D | 137 | 76.6 % | 19.7 % | 1.34, 1.19, 1.32 | 103.5 | 38.0 | 44 |

  - World detections a second: A 1.06, B 1.05, C 1.06, D 4.03. The box's age at a strike, p50:
    A 0.239 s, B 0.243, C 0.265, D 0.104.
  - **Batt's point holds for the click itself:** clicking on sight on a 1-a-second look (C) turned
    a third of its clicks into walks (the monster had moved). Looking 4 times a second (D) halved
    that (19.7 %) and gave the fastest box -> attack. Neither turned into more kills an hour.
  - D2 (live detect server's minute p95 during each D run, Amendment 10, reported): D1 median
    29.9 / max 32.4 ms, D2 28.6 / 30.3, D3 28.5 / 30.7; no minute over 35 ms.
- **Nothing joins the base from 5b.** Each arm stays a player switch, off. B is the nearest; it
  would need its own new A/B to say more.

