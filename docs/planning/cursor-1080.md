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
