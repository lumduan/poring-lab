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
