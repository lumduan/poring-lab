---
doc_type: measurement
hypothesis: "Every swing a monster misses at the Rogue makes the client draw a 'Miss' text in a band around our head. A pure-pixel template detector can see it at the runner's 5 Hz with few false alarms. That would start the defend scan on the FIRST swing at us instead of the first HIT, several seconds earlier."
status: "MEASURED (offline): scripts/miss_cue.py, its template cut from TUNE (a2, a3, a4), validated on TEST (a7, a8, a5b, b1, c1, c2, c3) and on Batt's 5 Hz demo. Nothing is pre-registered; no runner changed."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [gef10-time-budget.md, rogue-gef10.md, gef10-cursor-unknown.md, ../../scripts/miss_cue.py, ../../scripts/dungeon_hunt.py, ../../scripts/time_budget.py, ../../services/backend/tests/test_miss_cue.py]
next_action: "The parent: (1) run `miss_cue.py validate --split test2 --open-held-back` (a9, a10, a11, w3: never opened here) and record it BEFORE sealing; (2) pre-register dungeon@9.1 `--miss-cue` (section 7: OFF by default, one arm against 9.0b, primary metric the reaction time when a monster swings first); (3) decide with Batt the sitting rule (section 7c: a Miss while sitting stands us up, a press of the stand toggle) and whether the Miss's x may order the ring scan (7d, not measured)."
title: "gef_fild10: the Miss cue -- seeing the first swing at us from pixels"
date: 2026-10-26
owner: Batt
---

# gef_fild10: the Miss cue -- seeing the first swing at us from pixels

**Why.** [gef10-time-budget.md](gef10-time-budget.md) ranks the REST as the bot's biggest loss
against Batt. The rest is downstream of the damage it takes: 239 HP per kill against his 34. Part
of that damage lands while the bot has not yet answered an attacker. Its median reaction to a
monster that swings first is 12.7 s; Batt's is 1.26 s. Today's defend scan starts on a **hit** on
us (the Battle Log's "taken" line, or the HP percent falling). The Rogue has FLEE 192, so the
orcs land only about one swing in thirteen (7.6 %, section 1). The first hit therefore comes
several swings after the attack began. Every swing that misses makes the client draw "Miss", and a human sees it at once.

**What this is NOT.** It changes no runner and no default, and it decides nothing. Every number
is **measured** offline from the recordings and packets of the allowed runs, unless it says
**estimate**. The switch of the trigger is the parent's, behind a pre-registration (section 7).

## 0. The answer in brief

1. **What the client draws.**
   - A small light-grey serif "Miss", about 30 x 10 px, with a dark drop shadow.
   - It is drawn above the **attacker**, not above us. A melee orc stands one cell from us, so the
     text appears in a band around our head (section 1b). It rises as it ages, and several stack
     while an orc keeps swinging.
   - It appears **0.7-0.8 s** after the server's act packet (the orcs' attack motion is
     864-900 ms). It stays up to about 3 s, and it is clearly matched while 0.8-1.8 s old.
2. **The detector** (`scripts/miss_cue.py`, pure numpy):
   - a "bright and neutral" feature, `clip(min(B, G, R) - 130, 0, 90) / 90`;
   - the best zero-mean normalised cross-correlation (FFT) with a 14 x 34 template, inside the
     ROI (520, 130)-(760, 340);
   - the template is averaged from 282 real Miss texts cut from the TUNE recordings. It lives in
     `data/miss_cue/` (client pixels, gitignored, never committed);
   - `miss_over_us(frame)` is True when the score is >= **0.60**. The threshold was fixed on TUNE
     before TEST was opened.
3. **Validation on the held-out TEST runs** (a7, a8, a5b, b1, c1, c2, c3; 1-fps PNG recordings).

   | measure | TEST | TUNE (a2, a3, a4) |
   |---|---|---|
   | recall per frame, text 0.8-1.8 s old | **58.7 %** (861 / 1,467; 95 % CI 56.2-61.2 %); 76.3 % without a8 | 70.6 % (688 / 975) |
   | recall per EVENT (first swing after >= 3 s quiet), at 1 fps | **65.9 %** (56 / 85; CI 55-75 %) | 63.5 % (40 / 63) |
   | false positives on negative frames | **0 of 4,207 frames** (70.5 min); <= 0.043 / min at 95 % | 1 of 2,814 (a real Miss: a gap in the truth) |
   | hard negatives (no Miss can be on screen; something else is) | **0 of 478** | 0 of 302 |

   - **Batt's 5 Hz demo** (JPEG q80, the runner's rate): per-event recall **86.1 %** (31 / 36).
     The cue fired a median **0.98 s** after the swing's packet (p90 1.34 s). 0 false positives
     on 1,371 negative frames.
   - **Precision audit:** all 36 of 36 randomly drawn TEST frames that fired show a "Miss" at the
     match. All 3 fired frames labelled negative (one in TUNE, two in the demo) show a real Miss
     with no act in the packets: these are gaps in the truth, not detector errors.
4. **Latency:** 8.4 ms per call at p50, 13-15 ms at p90 and 23 ms at worst. That is one core,
   niced, on this host under a load of 17-27. The 5 Hz HP loop has 200 ms per read.
5. **What it would gain** (an **estimate**, from the packets of the ten allowed runs, 5.0 h,
   249 attacks opened by a monster):
   - today the first HIT comes a median **4.0 s** (5 misses) after the first swing;
   - with the cue (recall 0.86, seen 1.0 s after the packet, the time after the trigger kept),
     the median reaction goes from **11.8 s to 5.8 s**. The gain per attack has a median of
     2.1 s, a mean of 3.4 s and a p90 of 8.9 s: 3.6 s per kill;
   - the damage landing in that time is **13,710 HP of 46,230 (29.7 %)**: 57 HP per kill, about
     2,700 HP per hour that the rest no longer has to repay.
6. **Open risks** (section 6):
   - recall drops under tree canopies: the text is drawn semi-transparent over dark leaves (a8);
   - texts from attackers beyond one cell fall outside the ROI;
   - our OWN misses would probably be drawn above us. The Rogue never missed in these runs
     (0 of 1,524 damaging acts), so this is unmeasured;
   - "Lucky" (1.4 % of swings) is another word, and it is not detected;
   - the hard-negative classes are small: fights are dense with misses.

## 1. What the client draws (measured)

**Read:** the a2 recording (1 fps, PNG, 1280 x 720 game region) and Batt's human demo
`20261026T095021-demo-human-demo-gef10` (5 Hz JPEG q80 frames on the NAS; its packets only; its
input log was never opened). The truth is the packets: an `act` with `target_gid` = our AID
2000002. Damage 0 of kind "normal" is a monster's **miss**; damage > 0 is a **hit**;
`lucky_dodge` draws "Lucky". Our acts carry `src_gid` = 2000002.

- **How often they miss.** In the recordings' packets of the ten allowed runs the orcs land 7.6 %
  of their swings at us: 292 hits, 3,503 misses and 55 Lucky. The attackers are Orc Lady (attack
  motion 900 ms), Orc Warrior and Orc Baby (864 ms), and rarely a Poporing (672 ms).
- **1a. Appearance.**
  - The word "Miss": light grey (BGR about 205-215), serif, about 30 x 10 px.
  - A 1-px dark drop shadow to the right and below.
  - The same size whatever its age. It fades, and it is partly transparent: over dark tree
    canopy it is much less bright (section 3f).
- **1b. Where: above the ATTACKER.** On a2, the frames where exactly one monster had missed us
  0.3-2.5 s before, matched with a score > 0.65, were set against that monster's cell relative to
  ours (`time_budget.Track`):

  | attacker's cell - ours (dx, dy) | frames | text centre x - 640 (median) | text centre y (median) |
  |---|---|---|---|
  | (-1, -1) | 37 | -35 px | 276 |
  | (-1, +1) | 14 | -34 px | 228 |
  | (+1, -1) | 30 | +48 px | 279 |
  | (+1, 0) | 6 | +49 px | 264 |
  | (+1, +1) | 5 | +38 px | 224 |
  | (0, +1) | 1 | +2 px | 220 |

  - Both x and y follow the attacker's cell: a monster to the north draws its Miss higher.
  - So the Miss is drawn at the attacker's position, and for a melee attacker that is a band
    about +-50 px around our head. Damage numbers on us (red) sit there too.
  - The text centres of a2's positives span x 576-704 and y 183-310 (10-90 %), and x 383-704,
    y 156-321 (2-98 %).
- **1c. When: the delay and the lifetime.**
  - Batt's demo at 5 Hz: the first swings after >= 3 s with no act on him, 38 events, scored with
    the seed template. Frames after the next act on him + 0.6 s were dropped.
  - No frame matched before **+0.6 s**. The share of frames with a match >= 0.5 rises from 6 % at
    0.6 s, 21 % at 0.7 s and 46 % at 0.8 s to 54-89 % at 1.0-1.6 s. It falls to 17-25 % from
    1.8-2.0 s on these JPEG frames (the faded, risen text; on the PNG recordings old texts still
    match, below).
  - On a2 at 1 fps, nothing before +0.8 s.
  - The delay is the attacker's attack motion: the client shows the result at the swing's hit
    frame, and the RDP path adds its ~0.1 s.
  - On the PNG recordings, matches of older, higher texts come up to ~3.0 s after the packet
    (y 140-165). Section 3a's first labels set "no Miss" at 2.5 s, and the matches then counted
    as false were these old texts (a2 1430, a4 349/356/390/399: a miss 2.56-2.93 s before).
    The "may be on screen" zone became 0.3-3.3 s before TEST was opened.
- **1d. The rise.**
  - In the demo, the median text centre y is 282 at 0.6 s, 257 at 0.8 s, 233-244 at 1.0-1.4 s
    and 218 at 1.6 s: about 60 px in its first second.
  - Older texts climb to y ~140-160 by ~3 s.

## 2. The detector (`scripts/miss_cue.py`)

- **ROI** (game-region px): x 520-760, y 130-340. It holds text centres x 537-743, y 137-333:
  the a2 band of section 1b with a margin.
- **Feature:** `clip(min(B, G, R) - 130, 0, 90) / 90`. Grass, dirt and leaves keep their blue
  channel low, so they read 0. The light-grey text reads high. Red damage numbers on us and the
  yellow / white totals of our hits read 0, or form other shapes.
- **Early exit:** fewer than 40 pixels >= 0.25 in the ROI gives score 0 (a third of TUNE's
  negative frames).
- **Score:** the maximum zero-mean NCC of the 14 x 34 template over the ROI, via FFT. A flat
  window scores 0. `read()` returns the score, the match's centre (x, y) and the ink count;
  `miss_over_us()` is the threshold test.
- **The template** (`miss_cue.py cut`):
  - seeded by one hand-located instance (a2 frame 1265, top-left 673, 278);
  - then matched in TUNE frames 0.6-2.2 s after a miss (match >= 0.75), cropped aligned and
    averaged; two iterations: 141 instances, then **282** (a2 100, a3 100, a4 82; median match
    0.84);
  - stored in `data/miss_cue/template.npy` with its provenance in `template.json` (session,
    frame, place and score of every instance). Client pixels: gitignored, never committed. The
    tests use synthetic glyphs.
- **Other features tried, on TUNE only** (450 positives, 700 negatives, 302 hard; recall at the
  negatives' maximum + 0.15):

  | feature | max over negatives | recall at max + 0.15 |
  |---|---|---|
  | **clip(min - 130) (chosen)** | 0.445 | **71.3 %** |
  | clip(min - 115) | 0.594 | 49.6 % |
  | clip(min - 100) | 0.732 | 22.7 % |
  | raw min(B, G, R) | 0.728 | 16.9 % |
  | min - 0.5 (max - min) | 0.735 | 18.9 % |

  A lower floor lets textured grass and leaves through, and that costs more than it gains on
  the dark canopy.
- **The threshold**, chosen on TUNE before TEST was opened:
  - the highest score of anything that is not a Miss on TUNE's 3,116 non-positive frames is
    0.443;
  - **0.60** leaves a 0.15 margin above it, at 70.6 % recall per frame on TUNE;
  - no threshold from 0.50 to 0.80 fired on a TUNE negative, except the real Miss of section 3d.
  - TUNE sweep (recall per frame): 0.50 75.3 %, 0.55 73.0 %, **0.60 70.6 %**, 0.65 64.4 %,
    0.70 52.8 %, 0.75 43.3 %, 0.80 33.5 %.

## 3. Validation

**The split, fixed before any result was read:**
- **TUNE** = a2, a3, a4: the template and the threshold.
- **TEST** = a7, a8, a5b, b1, c1, c2, c3: opened once, with the final detector.
- **TEST2** = a9, a10, a11, w3: held back for the parent and never opened here
  (`rec_dir` refuses them without `--open-held-back`).
- The recordings are 1 fps. They cover 3.5 h of the runs' 5.0 h (a4's recording is 9.6 min of
  its 36-min run).

**3a. The truth labels** (`miss_cue.label`, per frame, by its capture time t):
- **pos**: a miss on us 0.8-1.8 s before t;
- **skip**: else a miss 0.3-3.3 s before t (appearing, or an old high text: not judged);
- **hard negatives**, in this order: a hit on us 0.8-2.0 s before (a red number), Lucky 0.8-2.0 s,
  our damaging act 0.2-1.8 s, our Steal (the runner's events) 0-2 s, our potion 0-2 s, a notice
  (pickup result or chat line) 0-3 s, a level change 0-3 s;
- **fight**: else any act on us within +-3 s (sprites swinging; no Miss on screen);
- **neg**: none of these.

**3b. Per run** (threshold 0.60; "event" = the first swing after >= 3 s with no act on us, seen
when a frame 0.7-2.0 s after it fires, at 1 fps):

| run | split | recall per frame | recall per event | negative frames fired (minutes) | hard negatives fired |
|---|---|---|---|---|---|
| a2 | TUNE | 287 / 415 (69.2 %) | 18 / 30 | 1 / 1,327 (22.2) | 0 / 128 |
| a3 | TUNE | 233 / 358 (65.1 %) | 13 / 23 | 0 / 1,230 (20.6) | 0 / 119 |
| a4 | TUNE | 168 / 202 (83.2 %) | 9 / 10 | 0 / 257 (4.3) | 0 / 55 |
| **TUNE** | | **688 / 975 (70.6 %)** | **40 / 63 (63.5 %)** | **1 / 2,814 (47.1)** | **0 / 302** |
| a7 | TEST | 196 / 242 (81.0 %) | 8 / 10 | 0 / 981 (16.4) | 0 / 74 |
| a8 | TEST | 182 / 577 (31.5 %) | 15 / 19 | 0 / 1,261 (21.1) | 0 / 121 |
| a5b | TEST | 223 / 305 (73.1 %) | 16 / 25 | 0 / 1,124 (18.9) | 0 / 107 |
| b1 | TEST | 105 / 127 (82.7 %) | 3 / 4 | 0 / 330 (5.5) | 0 / 40 |
| c1 | TEST | 100 / 132 (75.8 %) | 8 / 13 | 0 / 305 (5.1) | 0 / 69 |
| c2 | TEST | 6 / 8 | 1 / 2 | 0 / 41 (0.7) | 0 / 20 |
| c3 | TEST | 49 / 76 (64.5 %) | 5 / 12 | 0 / 165 (2.8) | 0 / 47 |
| **TEST** | | **861 / 1,467 (58.7 %; CI 56.2-61.2)** | **56 / 85 (65.9 %; CI 55.3-75.1)** | **0 / 4,207 (70.5)** | **0 / 478** |

- The TEST false-positive rate is 0 per minute of negative footage, <= 0.043 / min at 95 %
  (rule of three). At the runner's 5 Hz the same scenes are read five times a second. A false
  fire on a static scene would repeat, so this bounds false TRIGGERS, not false reads.
- The per-event recall at 1 fps is a lower bound for 5 Hz: a text lives for several 5 Hz reads.

**3c. The hard negatives by class** (frames fired / frames):

| class | TUNE | TEST | Batt's demo (5 Hz) |
|---|---|---|---|
| a fight scene, no Miss possible | 0 / 160 | 0 / 244 | 0 / 540 |
| notices (pickup results, chat) | 0 / 126 | 0 / 189 | 0 / 308 |
| a red number on us (a hit) | 0 / 6 | 0 / 11 | 1 / 12 (a real Miss: 3d) |
| our damage numbers on the monster | 0 / 1 | 0 / 8 | 1 / 38 (a real Miss: 3d) |
| our Steal's shout bubble | 0 / 6 | 0 / 8 | - |
| our potion | 0 / 2 | 0 / 17 | - |
| Lucky | 0 / 1 | 0 / 1 | - |

- **What is NOT covered.**
  - The fight classes are small because fights are dense with misses.
  - No level change fell in a judged frame.
  - Our own misses on a monster: 0 in all allowed runs.
  - @heal's "HP, SP recovered": only at the setup.
- **Covered indirectly.** Every positive frame is also a hard case: our damage digits, the
  Steal bubble and the monsters are on screen beside the Miss. The 36-frame precision audit
  (3d) checks that the match lands on the Miss.

**3d. Precision audit and the truth's gaps.**
- 36 TEST frames that fired were drawn at random and cropped 80 x 40 px around the match. All 36
  show a "Miss" there: over grass, dirt, leaves, beside our big damage digits, and stacked two
  high.
- The three fired frames labelled negative all show a real Miss on screen, with **no act in the
  packets** that could have drawn it:
  - a2 frame 894: a Miss above an orc beside us, and no act on or by us within +-4 s;
  - demo 00491: a Miss above an orc, no miss within 4 s before; a hit 1.67 s before;
  - demo 00495: an old, high Miss, no miss on us before it.
  - These are probably act types the decoder does not emit (a monster skill that missed?). For
    the trigger they are swings at us all the same.

**3e. Per event at the runner's rate (Batt's 5 Hz demo).**
- The demo is JPEG q80, which lowers the scores, so this check is conservative. It is not the
  primary validation, because the runner reads raw frames.
- 36 first swings after >= 3 s quiet: the cue fired on **31 (86.1 %)**. The first firing read
  came a median **0.98 s** after the packet (p90 1.34 s).
- Per frame: 67.3 % (1,129 / 1,678) of the frames 0.8-1.8 s after a miss.
- Negatives: 0 of 1,371 frames (4.7 min at 5 Hz).

**3f. Where it fails** (looked at on TUNE's misses, then on a8's after TEST):
- **Tree canopy.**
  - a8 stood a long stretch under a big tree: per-frame recall 31.5 %, against 73-83 % on
    open ground. Its per-event recall is still 15 / 19: the canopy stretch adds many frames of
    one long attack, but few first swings.
  - The text is drawn partly transparent. Over dark leaves its min(B, G, R) falls under the
    feature's floor of 130, so the ROI reads no ink.
  - A lower floor lets the leaves themselves through (section 2's table).
- **Outside the ROI.** An attacker more than a cell away, or an old text that has climbed above
  y 130.
- **Overlap.** Big damage digits or a speech bubble drawn over the Miss.
- Changing any of these now would be tuning on TEST. A v2 needs a fresh held-out set
  (section 6).

## 4. Latency budget

- `miss_cue.py latency`: 200 frames of a2, `read()` alone (the frame is already in memory, as
  in the HP loop).
- **p50 8.4 ms, p90 13-15 ms, p99 17-20 ms, max 23 ms.** Two runs, one niced and one not, on
  one core with `OMP_NUM_THREADS=1`, on this host under a load of 17-27.
- A quiet frame takes the early exit (one min() over 240 x 210 x 3).
- At READ_HZ 5 the loop has 200 ms per read; the cue takes 4-7 % of it.

## 5. What the trigger would gain (estimate, packets only)

`miss_cue.py gain` uses `time_budget.engagements` on the runner windows of the ten allowed runs
(a2, a3, a4, a7, a8, a5b, b1, c1, c2, c3; 5.0 h; 239 kills, 46,230 HP of damage on us).

- **The cases.** The engagements a monster opened ("attacked" first): **249**.
- **Today.** The reaction is the first act on us -> our first request or walk toward it, median
  **11.8 s**. In 158 of them a HIT came before our answer, a median **4.0 s** (5 misses) after
  the first swing.
- **The model.**
  - Each swing is "seen": a hit always (today's trigger stays), a miss with probability r,
    1.0 s after its packet (the demo's latency).
  - The new trigger is the first seen swing. The time from the trigger to the answer is today's
    (the answer - the first hit; else that run's median).
  - The answer is never later than today's. The damage saved is the damage on us between the
    new answer and today's.

| recall r | reaction, median | gain per attack: median / mean | damage saved | share of all damage |
|---|---|---|---|---|
| 1.0 (a perfect cue) | 5.7 s | 2.3 / 3.5 s | 14,715 HP | 31.8 % |
| **0.86** (the demo's per-event) | **5.8 s** | **2.1 / 3.4 s** | **13,710 HP** | **29.7 %** |
| 0.66 (TEST, one 1-fps frame) | 6.1 s | 1.7 / 3.2 s | 12,872 HP | 27.8 % |

- **At r = 0.86:**
  - 169 of 249 attacks are answered earlier, 127 of them by >= 2 s. The gain quartiles are
    0 / 2.1 / 6.4 s, p90 8.9 s, and 850 s in all: 3.6 s per kill.
  - 57 HP saved per kill, against 193 taken. About 2,700 HP per hour that the rest no longer
    repays.
- **Per run** (r = 0.86; the median gain per attack, then the HP saved per hour): a2 5.2 s /
  1,587; a3 1.5 / 2,163; a4 0.9 / 5,986; a7 3.3 / 1,909; a8 1.0 / 1,215; a5b 0.6 / 2,769;
  b1 5.3 / 3,426; c1 2.0 / 3,699; c2 0 / 0 (6 attacks); c3 1.9 / 3,345.
- **While sitting.**
  - 6.8 % of the swings at us (362 of 5,299) came while we sat, in 21 attacked sits.
  - From the first swing to the first hit (or our stand) took a median 10.9 s, mean 18.8 s.
  - A miss does not stand us up: only damage does (pc_damage). So the cue can end those sits
    ~10 s earlier, if the runner presses stand (7c).
- **What the estimate leaves out.**
  - It keeps today's scan time after the trigger (a median ~5 s, the next loss in line).
  - It does not model false triggers: none were measured.
  - The 1.0-s delay is the demo's; the runner's own frame path adds a little.

## 6. Risks and open questions

1. **The canopy.** Recall falls under dark tree canopy (a8). A v2 could use a floor relative to
   the local background, or a second template for the dark-canopy look. It must be validated
   on runs neither TUNE nor TEST has seen.
2. **Ranged attackers and old texts** fall outside the ROI. Widening it costs latency and
   brings in more scene. Our melee case is covered.
3. **Our own misses.**
   - If the client draws every Miss at the attacker (as measured for the orcs), our misses
     would be drawn above US and fire the cue.
   - On gef_fild10 the Rogue missed 0 of 1,524 damaging acts, so this is unmeasured.
   - On another map or job, measure it before trusting the cue. Within a fight it is harmless,
     because we are already fighting.
4. **Lucky** (1.4 % of swings) is not seen. A hit, or the next miss, still triggers.
5. **The truth's gaps.** Some Misses have no act in the packets (3d). The recall and FP numbers
   count them against the cue, so they are slightly pessimistic.
6. **The hard-negative counts are small** (478 TEST frames). The 36 / 36 audit and 0 / 4,207
   negatives are the stronger evidence. The live run must count false triggers (7b).
7. **The JPEG demo** is the only 5 Hz per-event measurement. A raw 5 Hz check comes with the
   first live run.
8. **Other maps, the house interior (in_orcs01), towns, other players' Misses.** Unmeasured. The
   cue should run only where the defend scan runs, on the field.

## 7. Proposed integration and pre-registration (for the parent)

**7a. The change** (dungeon_hunt.py, the parent's; this study did NOT touch it):
- a new option `--miss-cue`, OFF by default;
- at start-up: `tpl = miss_cue.load_template()`. A missing template refuses the run, with
  `miss_cue.py cut ...` as the fix;
- in the HP loop, right after `img = frame()`: `mr = miss_cue.read(img, tpl)`. On
  `mr.score >= miss_cue.THRESHOLD`: `last_swing = tick`, plus a rate-limited event
  `{"kind": "miss_cue", "score", "x", "y"}`;
- the fight test becomes `(hit_now or dropped or swing_now or near_ is not None) and mode !=
  "fight"`, with `swing_now = tick - last_swing < FIGHT_TAKEN_S`;
- its engage event is `{"kind": "engage", "by": "miss_cue", "x": mr.x}`;
- the rest is unchanged: the scan, the strike, and the hit trigger, which stays.

**7b. Pre-registration sketch:**
- **Arms:** 9.0b (base) and 9.1 = 9.0b + `--miss-cue`, alternated, the same seeds, loop and
  strategy; at least 3 runs of 36 min each.
- **Primary:** the reaction when a monster swings first (`time_budget.py`, react_s,
  approach_by "attacked"). The prediction: a median of <= 8 s with the cue, against ~12 s.
- **Secondary:** damage taken per kill (predicted at least 20 % lower), the rest share, and
  kills per hour.
- **Safety and honesty counters:**
  - false triggers = `engage by miss_cue` with no act on us within 3 s before (packets,
    offline). The bar: <= 1 per 36-min run;
  - the scan clicks only on a SWORD read, so a false trigger costs time, never a wrong click;
  - every miss_cue event is logged with its score and place.
- **Before sealing:** `miss_cue.py validate --split test2 --open-held-back` on a9, a10, a11 and
  w3, recorded in the pre-registration.

**7c. Sitting.**
- A Miss while we sit means an orc is swinging at us, and the server will not stand us up until
  a hit lands (a median 10.9 s here).
- With the cue the runner should stand at once. But "stand" is a TOGGLE (dungeon@8.2 never
  presses it after a hit). So press it only when no hit and no HP fall came within
  FIGHT_TAKEN_S, and read the sit state back.
- This is a new decision for Batt and the parent. It is not part of 7a's minimal change.

**7d. Not measured, optional.** The Miss's x says which side the attacker is on (section 1b:
x - 640 about -35 = west, +48 = east). It could order ring 1 of the defend scan, but it needs
its own measurement first.

## 8. Reproduce

    export PYTHONPATH=$PWD/scripts:$PWD/packages/poring_dataset/src:$PWD/packages/poring_env/src
    PY=/home/batt/docker/poring-lab/.venv/bin/python
    nice -n 15 $PY scripts/miss_cue.py cut --seed 20261025T221059-rdp-rogue-a2:1265:673,278 --max-n 300
    nice -n 15 $PY scripts/miss_cue.py validate --split tune --out /dev/shm/.../val-tune.json
    nice -n 15 $PY scripts/miss_cue.py validate --split test --out /dev/shm/.../val-test.json
    nice -n 15 $PY scripts/miss_cue.py demo
    nice -n 15 $PY scripts/miss_cue.py latency --n 200
    nice -n 15 $PY scripts/miss_cue.py gain --delay 1.0 --recall 0.86

- The shard offsets are cached in RAM: `/dev/shm/poring-lab-tmp/miss-cue/idx/`.
- The template's provenance is in `data/miss_cue/template.json`.
- Unit tests: `services/backend/tests/test_miss_cue.py` (synthetic glyphs, the truth labels,
  the gain model).
