---
title: "The cursor classifier's robustness: the gate's reader measured, a robust candidate, and its live acceptance (DRAFT)"
status: PROPOSED
date: 2026-10-09
owner: Batt
extends: docs/planning/npc-click-test.md
gate: "OFFLINE only: nothing here touched the client. The gate's default is NOT switched and no pre-registered rule's decision code changed (walk@15/16/17 and loot@1 keep walk6.CursorRefs v3; no module they import was edited). The robust reader (scripts/cursor_robust.py) enters only through the flag in section 6, after the live acceptance of section 5 (a DRAFT for the parent to review and paste into demonstrations.md BEFORE any run) and Batt's decision."
---

# The cursor classifier's robustness

**Batt (2026-10-09 ~19:30):** "the cursor-classifier robustness work is a priority".

> ➡️ **Status (2026-10-10):** the live acceptance (section 5, run as demonstrations.md 3.35, cursor@1)
> FAILED bar 1 for both readers on the client's no-entry ANIMATION (a blink frame shows the bare
> arrow). Its fix, robust2 (this reader per grab + a red-RING cue over the 6-grab series,
> `cursor_robust.ring_pixels` / `series_verdict`), is pre-registered as cursor@2 (3.36). The
> switch-over (section 6) stays Batt's decision; the live gate is still v3.

**Why:** the gate clicks only on a shape read twice, and its reader says UNKNOWN where it matters:
- loot@1 P3 (demonstrations 3.20a): over a Poring the first reads were **unknown 67 / 105 (64 %)**,
  WALK 35, SWORD 3. The kill phase is blocked.
- talk@1 / walk@17 item 5 (npc-click-test.md section 3): Garnet's TALK reads intermittent; a 1-px
  reference shift reproduces the live signature; held-out maps read worse.

Client pixels (references, crops, frames) stay in `data/` and `/dev/shm`. Every number here comes
from `scripts/cursor_eval.py` (section 7) on the v3 references (`data/walk6/cursor_refs_rdp_v3.npz`,
645 hovers) and their raw calibration hovers in `/dev/shm/poring-lab-tmp`.

## 0. At a glance

| question | answer (offline, 2026-10-09) |
|---|---|
| What does the gate's reader do wrong? | It needs the observed mask to overlap a reference at ONE registration (IoU ≥ 0.6) and then the colours on that overlap (≥ 0.85 within 40). **A 1-px offset fails the colour** (walk 170 / 1,000, talk 3 / 920, sword 8 / 250, no-entry 0 / 150 read; real colour median 0.70). **A light floor hollows the mask** (talk on prontera stone 36 / 92, on a UI window 20 / 92). **A bobbing Poring under the sword: 0 / 150 SWORD** (the live P3, reproduced). Any JPEG pass: no-entry 0 / 240. |
| Are the references sound? | Mostly. **9 WALK references carry a no-entry sign's mask** (a stale parked frame), **9 of 26 SWORD references** are > 30 % Poring motion, **indoor/100 ("sword") is no cursor at all**, 4 TALK references carry NPC pixels (section 1.2). The gate uses them as they are. |
| The robust candidate | `scripts/cursor_robust.py` `RobustRefs.match(a, mask)`, the same interface: prototypes trimmed to their class's consensus; a ±2 px shift search; the colour read on the cursor's OWN pixels in A (not on the mask); the mask only for two-sidedness and coverage; floors and margins learned leave-one-out; the leader must cover, every competitor counts without coverage; WALK strictest. **17 ms median, 47 ms p95 per read** (one core; the gate's reader: 8 / 88 ms). |
| Cross-shape errors | **0 for both, in every condition**: 15,433 perturbed leave-one-out reads each, 3,795 leave-neighbours-out reads, 78 banked crops. **WALK-from-anything: 0 / 0.** |
| Recall gained | 1-2 px shifts: walk 999 / 1,000, talk 910 / 920, sword 186 / 250, no-entry 150 / 150. 16 backgrounds: walk 1,600 / 1,600, talk 1,472 / 1,472, sword 287 / 400. **SWORD over a bobbing Poring: 97 / 150** (gate: 0). Banked live crops: walk 60 / 71 (gate 54 / 71), with a ±1 px best shift on 6 of the 8 the gate missed. |
| What it does not fix | Blur σ ≥ 0.8 (walk 66 / 100), extra changing content beside the cursor (WALK over a bobbing Poring: prec fails, fail closed), noise sd ≥ 20 (it breaks the MASK for both). |
| Live acceptance | DRAFT in section 5: the npc-click probe arm (TALK) + a new hover-only SWORD probe (`scripts/cursor_probe.py`, built, NOT run), both classifiers scored offline on the same saved crops, blind labels, 0 cross-shape errors as a hard bar. |

## 1. The gate's reader today, measured

### 1.1 What it decides
`walk6.CursorRefs.match(a, mask)` (Prober9 reads it through `walk6.cursor_mask`: |A − B| > 60
summed over the channels against the parked frame, the animated pixels of the two parked frames
removed, the green chevrons removed, the largest component touching the hotspot window):
1. the references in IoU order, down to 0.6;
2. the first whose colour on the OVERLAP (share of pixels with max channel |Δ| < 40) is ≥ 0.85 wins;
3. none: `unknown`, `"col": 0.0`. **The 0.0 is a placeholder**: the evaluator reports the real
   colour of the best-IoU reference and the best colour among the references with IoU ≥ 0.6.

### 1.2 The references (`cursor_eval.py audit`)
| class | n | flagged | what |
|---|---|---|---|
| walk | 491 | 9 | indoor/58, 69, 80, 148, 159, 170, 238, 249, 260: the crop shows an ARROW, the mask is a NO-ENTRY ring and slash (the parked frame held a stale no-entry sign). Their colour on the ring is floor, so the gate's colour check never let a real no-entry pass as WALK through them; still mislabelled masks. |
| sword | 26 | 9 + 1 | 9 masks are mostly Poring motion (walk@6's single parked frame): the class consensus keeps 32-67 % of them. **indoor/100 is no cursor** (its mask lies above the hotspot, 0 px at it; 2 % survives the consensus). Clean swords: about 12. |
| talk | 92 | 4 | npc-crusader-6 is a 51-px fragment; pastor-4, bard-4, bard-6 carry NPC pixels (42-70 % kept). |
| pickup, no-entry, warp | 9, 15, 12 | 0 | |

**Codec noise in the references** (pixels inside every mask of a static class, against the
class median, max channel): median 1-7, 90th percentile 7-45 (talk 1 / 7, no-entry 7 / 24,
pickup 7 / 45, sword 3.5 / 28). Per-channel noise of sd 20-30 is far outside it.

### 1.3 The perturbation set (`cursor_eval.py perturb`)
- **The sprite:** each reference's own pixels against its RAW parked background (`walk5-cal`,
  `cursor-diag-npc`, `walk6-cal/pickup2`): |A − B| > 30 summed, minus the chevrons, trimmed to
  its class's consensus (what moved behind it is not the cursor).
- **Composited** (moved by an integer or a sub-pixel shift, bilinear) over its own background or
  over a 64 × 64 patch of a banked frame: grass, green grass, a Poring's body, a Poring's feet
  (prt_fild08); light floor, carpet, a pew, a Poring, an NPC (prt_church); light paving, a guild
  flag, an NPC (prontera); a dark dungeon floor (iz_dun00); a white UI window, the chat window, the
  skill bar. The coordinates are in `cursor_eval.PATCHES`; the frames stay in `/dev/shm`.
- **Codec-like passes** on A and B, each image independently: Gaussian blur σ 0.5 / 0.8 / 1.2,
  JPEG q 90 / 70 / 50 (and q 80 on every patch), per-channel noise sd 5 / 10 / 20 / 30.
- **"bob":** a Poring's pink pixels moved by 0, ±amp px between the two parked frames and the
  hover (amp 1 and 2), so Prober9's animation map and the leak past it are both modelled.
- **Probes:** every non-walk reference (talk 92, sword 25, no-entry 15, warp 12, pickup 9) and a
  seeded sample of 100 walk references (seed 20261009); 61 conditions; 15,433 reads per
  classifier. **Leave-one-out:** the probe's own reference is excluded from BOTH classifiers;
  `--neighbours 3` also excludes the 3 hovers before and after it in its calibration sweep.

### 1.4 The failure modes (the gate's reader; read / unknown / wrong, pooled per group)

| group (reads) | walk | talk | sword | no-entry | why unknown: shape (IoU < 0.6) / colour (IoU ≥ 0.6), real colour median |
|---|---|---|---|---|---|
| stored references (253) | 99 / 1 / 0 | 85 / 7 / 0 | 6 / 19 / 0 | 15 / 0 / 0 | 21 / 10, 0.71 |
| own background (253) | 99 / 1 / 0 | 87 / 5 / 0 | 7 / 18 / 0 | 15 / 0 / 0 | 15 / 12, 0.71 |
| integer shift 1-2 px (2,530) | **170 / 830 / 0** | **3 / 917 / 0** | 8 / 242 / 0 | **0 / 150 / 0** | 371 / **1,953, 0.70** |
| sub-pixel 0.5 px (759) | 30 / 270 / 0 | 63 / 213 / 0 | 0 / 75 / 0 | 0 / 45 / 0 | 49 / 608, 0.72 |
| blur σ 0.5-1.2 (759) | 104 / 196 / 0 | 87 / 189 / 0 | 3 / 72 / 0 | 15 / 30 / 0 | 64 / 468, 0.69 |
| JPEG q 90-50 (759) | 288 / 12 / 0 | 258 / 18 / 0 | 13 / 62 / 0 | **0 / 45 / 0** | 59 / 90, 0.73 |
| noise sd 5-20 (759) | 198 / 102 / 0 | 174 / 102 / 0 | 14 / 61 / 0 | 30 / 15 / 0 | 285 / 23 (sd 20 breaks the mask) |
| 16 backgrounds (4,048) | 1,558 / 42 / 0 | **1,344 / 128 / 0** | 111 / 289 / 0 | 240 / 0 / 0 | 428 / 152, 0.56 |
| 16 backgrounds + JPEG 80 (4,048) | 1,548 / 52 / 0 | 1,316 / 156 / 0 | 62 / 338 / 0 | **0 / 240 / 0** | 474 / 448, 0.74 |
| background + 1 px or blur 0.8 (2,530) | 41 / 959 / 0 | 2 / 918 / 0 | 5 / 245 / 0 | 0 / 150 / 0 | 421 / 2,052, 0.67 |
| **bob: a Poring animating under it (1,518)** | 201 / 399 / 0 | 376 / 176 / 0 | **0 / 150 / 0** | 75 / 15 / 0 | **803** / 19, 0.65 |

(pickup and warp in appendix A.) The mechanisms:
1. **Misregistration (C1 of npc-click-test.md).** One pixel moves outline onto fill: the best IoU
   stays 0.67-0.89 (10th-90th percentile, median 0.79) and the real colour drops to 0.70 (median). Direction matters for WALK (+1 x: 7 / 100,
   −1 x: 81 / 100): the references themselves already sit at two registrations (12 % of walk
   references best-match another at a 1-px shift, section 3.4).
2. **The mask depends on the background (C3).** A white bubble or glove on a light floor or a UI
   window keeps only its outline in |A − B|: talk 36 / 92 on prontera's paving, 20 / 92 on a UI
   window, pickup 0 / 9 on both. This is the held-out prontera signature (TALK IoU median 0.81).
3. **Animation.** Over a bobbing Poring the animation map removes the cursor's pixels over the
   Poring and the Poring's motion past the map joins the cursor's component: the IoU collapses
   (803 of 822 unknowns are SHAPE misses). **SWORD 0 / 150**, over a STILL Poring 21 / 75: the live
   P3 (3 SWORD in 105), reproduced. The polluted sword references add to it: a clean sword can
   only match the ~12 clean ones (sword on its own background: 7 / 25).
4. **Thin colour features.** The no-entry ring fails the colour after ANY JPEG pass (0 / 240), the
   blade too (sword 62 / 400 with JPEG 80).
5. **Not a classifier failure:** per-channel noise sd ≥ 20 adds |A − B| > 60 over the whole
   background: no reader can use that mask (both read 0). The references' own per-pixel noise
   is sd ~2-10 (median per class).

**No perturbation made the gate's reader read one shape as another: 0 wrong reads of 15,433.** Its
failures are all UNKNOWN: safe, and blocking.

## 2. The robust candidate: `scripts/cursor_robust.py`

`RobustRefs.load(path).match(a, mask)` returns walk6's dict (`shape`, `iou`, `col`) plus `score`,
`second` (the best competitor and its score), `margin`, `shift`, `ref` and `why` for an unknown.
Prober9 calls `refs.match(a, mask)` only, so `w10.Prober9(agent, screen, RobustRefs.load())` runs
unchanged (section 6). Pure numpy, no new dependency.

1. **Prototypes:** every reference, its mask trimmed to the pixels at least 15 % of its class
   share (`FREQ_MIN`): the Poring outlines and portal swirls go, indoor/100 is dropped (644
   prototypes).
2. **Per prototype and shift (dx, dy) ∈ [−2, 2]²:**
   - `rec` = the share of the prototype's interior pixels (4-eroded) whose colour IN A is within 40:
     the cursor's own pixels, read on A, so the background and the mask do not enter;
   - `prec` = the share of the mask inside the prototype's support grown by 1 px (two-sided: the
     no-entry ring over the arrow, a sprite merged in, lower it);
   - `cov` = the share of the prototype's support present in the mask (the cursor really changed
     these pixels);
   - score = min(rec, prec), the best shift.
3. **The decision, asymmetric (fail closed):** the LEADER is the class with the best score among
   pairs with cov ≥ 0.25; every OTHER class competes with its best score over ALL pairs, coverage
   or not (a no-entry ring on a background of its own red leaves only the arrow in the mask, yet
   its colours are in A: a test pins it; the gate's reader reads that case WALK). shape = leader
   only if score ≥ `FLOORS[leader]` and score − best competitor ≥ `MARGINS[leader]`. Else UNKNOWN:
   `low_score`, `ambiguous:<class>`, `no_match`, `no_cursor`.
4. **Thresholds, learned leave-one-out on the 644 stored references BEFORE any perturbed read was
   scored** (`cursor_eval.py floors`): each floor sits ≥ 0.12 above the highest score any OTHER
   class's reference reached for that class.

   | class | other classes' max | floor | margin | own LOO: median / below the floor |
   |---|---|---|---|---|
   | walk | 0.707 (sword outdoor/164, a stale-arrow mask) | **0.85** | **0.25** | 1.00 / 11 of 491 |
   | talk | 0.663 | 0.78 | 0.15 | 1.00 / 5 of 92 |
   | sword | 0.511 | 0.65 | 0.15 | 0.74 / 9 of 25 (the polluted ones) |
   | pickup | 0.660 | 0.80 | 0.15 | 1.00 / 0 of 9 |
   | no-entry | 0.457 | 0.70 | 0.15 | 1.00 / 0 of 15 |
   | warp | 0.584 | 0.75 | 0.20 | 0.84 / 2 of 12 |

   WALK has the highest floor and the widest margin (a walk click over a unit is the unsafe
   direction); warp the next (a portal click leaves the map). Every floor − margin ≥ 0.5 (a test).
5. **Cost:** stage 1 computes prec and cov for every prototype at all 25 shifts from bit-packed
   rows (popcounts); stage 2 computes the colour only for the (prototype, shift) pairs that can
   change a decision (prec bounds the score; classes in decreasing bound; a batch stops when no
   remaining pair can lift the class above the leader or into the widest margin below it). The
   decision equals the exhaustive computation (tests; 333 perturbed reads compared). **17 ms
   median, 47 ms p95** per read in the 15,433-read run (one core); the gate's reader 8 ms median,
   88 ms p95 (its colour loop over every reference ≥ 0.6 when the colour fails). Loading: 0.3 s.

**Tried and rejected:**
- A read-path mask variant (the animation map grown by 2 px, every fragment within 2 px of the
  hotspot's kept): worse over Porings (prt_church sword 0 / 25 vs 16-18 / 25). Removed.
- De-duplicating near-identical prototypes (2 × faster): never evaluated against leave-one-out, so
  removed rather than left as an untested option.

**What it does not fix** (all fail closed):
- **Blur σ ≥ 0.8:** walk 66 / 100 at 0.8, 0 / 100 at 1.2 (the gate: 6, 0). If the live 6-grab series
  shows soft first grabs that sharpen (C2), Prober9's up-to-3 grabs already wait for them; blurred
  templates are the next step only if the live data asks for them.
- **Extra changing content beside the cursor:** WALK composited over a bobbing Poring (not a read
  the client would show) reads 316 / 600: the Poring's motion past the animation map stays in the
  mask and prec fails. Two-sidedness is the safety property; it is not relaxed.
- **Noise sd ≥ 20:** the mask itself fails (both readers 0).

## 3. Evaluation: both readers on the same reads

### 3.1 Pooled, leave-one-out (read / unknown / wrong; gate | robust)

| group (reads) | walk | talk | sword | pickup | no-entry | warp |
|---|---|---|---|---|---|---|
| stored (253) | 99/1/0 \| 99/1/0 | 85/7/0 \| 87/5/0 | 6/19/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 8/4/0 \| 10/2/0 |
| own background (253) | 99/1/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 7/18/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 9/3/0 \| 10/2/0 |
| shift 1-2 px (2,530) | 170/830/0 \| **999/1/0** | 3/917/0 \| **910/10/0** | 8/242/0 \| **186/64/0** | 13/77/0 \| 90/0/0 | 0/150/0 \| **150/0/0** | 12/108/0 \| 98/22/0 |
| sub-pixel (759) | 30/270/0 \| 269/31/0 | 63/213/0 \| 273/3/0 | 0/75/0 \| 35/40/0 | 0/27/0 \| 27/0/0 | 0/45/0 \| 30/15/0 | 9/27/0 \| 29/7/0 |
| blur (759) | 104/196/0 \| 166/134/0 | 87/189/0 \| 269/7/0 | 3/72/0 \| 23/52/0 | 9/18/0 \| 18/9/0 | 15/30/0 \| 15/30/0 | 9/27/0 \| 22/14/0 |
| JPEG (759) | 288/12/0 \| 289/11/0 | 258/18/0 \| 273/3/0 | 13/62/0 \| 49/26/0 | 25/2/0 \| 27/0/0 | 0/45/0 \| 30/15/0 | 26/10/0 \| 31/5/0 |
| noise 5-20 (759) | 198/102/0 \| 200/100/0 | 174/102/0 \| 182/94/0 | 14/61/0 \| 36/39/0 | 18/9/0 \| 18/9/0 | 30/15/0 \| 30/15/0 | 17/19/0 \| 20/16/0 |
| noise 30 (253) | 0/100/0 \| 0/100/0 | 0/92/0 \| 0/92/0 | 0/25/0 \| 0/25/0 | 0/9/0 \| 0/9/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 0/12/0 |
| 16 backgrounds (4,048) | 1558/42/0 \| **1600/0/0** | 1344/128/0 \| **1472/0/0** | 111/289/0 \| **287/113/0** | 126/18/0 \| 144/0/0 | 240/0/0 \| 240/0/0 | 89/103/0 \| 126/66/0 |
| backgrounds + JPEG 80 (4,048) | 1548/52/0 \| 1599/1/0 | 1316/156/0 \| 1464/8/0 | 62/338/0 \| 248/152/0 | 126/18/0 \| 144/0/0 | 0/240/0 \| 240/0/0 | 74/118/0 \| 118/74/0 |
| background + 1 px or blur (2,530) | 41/959/0 \| 793/207/0 | 2/918/0 \| 840/80/0 | 5/245/0 \| 107/143/0 | 8/82/0 \| 85/5/0 | 0/150/0 \| 75/75/0 | 1/119/0 \| 59/61/0 |
| bob, a Poring animating (1,518) | 201/399/0 \| 316/284/0 | 376/176/0 \| 532/20/0 | **0/150/0 \| 97/53/0** | 35/19/0 \| 54/0/0 | 75/15/0 \| 90/0/0 | 9/63/0 \| 52/20/0 |

### 3.2 Cross-shape errors: ZERO for both
- **0 wrong reads of 15,433 for each reader** (leave-one-out), **0 of 3,795** (leave-neighbours-out,
  15 conditions), **0 of 78** banked crops. **WALK-from-anything: 0 for both.**
- The one constructed case where they differ in the unsafe direction is the no-entry sign whose ring
  matches its background: the gate reads WALK, the robust reader `ambiguous` (synthetic test; no
  such background in the patches).
- Not proven: 0 in this set is not 0 live. The robust reader is NEW code; the live acceptance
  (section 5) keeps the zero as a hard bar and labels every WALK it claims.

### 3.3 Leave-neighbours-out (the 3 hovers before and after excluded; 15 conditions)
Same picture: robust walk 200 / 200 and talk 182 / 184 at 1-px shifts (the gate 12, 2); pickup 9 / 9
stored (the gate 4 / 9: its pickup references are one sweep); SWORD over a bobbing Poring 48 / 75 (the
gate 0 / 75). One regression: WALK over the bobbing prt_church Poring, amp 1: 16 / 100 (the gate
31 / 100), prec (section 2). Wrong reads 0 / 0.

### 3.4 Banked crops replayed (`cursor_eval.py replay`, labels by eye at design time)
78 crops that are NOT references: `cursor-diag` (walk@10's diagnostic, 2026-10-08: 34 walk, 3 talk,
1 warp), `cursor-diag-npc/npc-army-*` (8 walk), `walk6-cal/pickup/probes` (3 sword over a Poring,
13 walk), `walk6-cal/pickup2/sweep` minus its 9 references (16 walk).

| label | n | gate | robust |
|---|---|---|---|
| walk | 71 | 54 / 17 unknown | 60 / 11 unknown |
| talk | 3 | 3 | 3 |
| sword | 3 | 3 | 3 |
| warp | 1 | unknown | warp |

- 0 wrong reads either way. One walk read differs the other way: west-05 (the gate walk at IoU 0.60;
  robust 0.82 < 0.85).
- **Misregistration is real in the banked walk crops:** 15 of the 67 robust reads matched best at
  a ±1 px shift, and **6 of the 8 crops the gate missed and robust read were at ±1 px** (the gate's
  real colour 0.16-0.51 at IoU 0.63-0.75). No crop of a failing live TALK read exists yet.

## 4. What could not be determined offline
- **Whether live TALK / SWORD failures are misregistration, softening, hollow masks or animation**
  (C1-C5): each reproduces "unknown" offline and the robust reader recovers all but softening and
  motion leaks. Only live crops separate them: the probe arms save the 6-grab series.
- **RDP progressive's real softness:** σ 0.8 already drops the robust WALK rate to 66 / 100. The codec may
  refine within the 0.1 s regrabs (C2); unknown until the series is read.
- **The real Poring animation:** "bob" moves the Poring's pixels by 1-2 px; the live rate can differ.
- **Truth for live crops:** the packets cannot say what cursor the client drew: labels by eye
  (section 5). The 78 replayed crops were labelled by eye by Claude at design time, from the
  crops alone.
- **Unseen shapes** (a vending shop, a skill-target cursor): UNKNOWN by construction, untested.
- **S2:** no references there; the gate refuses, as before.

## 5. DRAFT acceptance pre-registration (for the parent; NOT pre-registered until pasted)

> **DRAFT.** The parent reviews it, then pastes it into docs/demonstrations.md with its commit time,
> BEFORE any run.
>
> ### 3.3x cursor@1: the robust cursor reader's LIVE acceptance (Batt 2026-10-09 ~19:30)
> **What it measures:** on the same live grabs, the gate's reader (v3, live) and the robust reader
> (`cursor_robust.RobustRefs` at <commit>, OFFLINE on the saved crops): per shape, the first read
> and the read-twice (the gate's click condition), and every cross-shape error. **Nothing changes
> in the live gate during the measurement.**
>
> **Arm A, TALK (and WALK on cells):** npc-click@1's probe arm unchanged (its 3.32a draft:
> `npc_click_test.py probe`, prontera `--near 156,191 --seed 20261160`, prt_church `--near 103,74
> --seed 20261161`; or prt_church alone if P1 is not ready for prontera). Its crops carry the 6-grab
> series.
>
> **Arm B, SWORD over a Poring (loot@1's kill phase):** `cursor_probe.py sword --n 10 --seed
> 20261170` at <commit> on prt_fild08: per trial one Poring, hovered only while its box is fresh
> and still (loot@1's tracker), at loot@1's 3 attack points and a 3 × 3 grid on the box, every
> third probe a CONTROL point on the floor 1.6 box widths beside it; ≤ 24 probes or 60 s per trial;
> the same 6-grab series and crops; **nothing is clicked**. Pilot first, never scored: `--n 2 --seed
> 20261171`; any harness fix is committed before the scored run.
>
> **Scoring:** `cursor_eval.py live SESSION` for both readers (first read = the first non-unknown of
> grabs 0-2; read twice = grabs 0-2 and 3-5 agree).
>
> **Truth, by eye; every label is fixed before any bar is computed:**
> 1. **The claims, audited:** `cursor_eval.py sheet SESSION --verdict S` for every shape S: every
>    crop the ROBUST reader reads as S, on pages that claim S. The labeller flags every crop that is
>    not S; a second labeller (Batt or a second agent) checks every flag. **Every WALK claim is
>    looked at.** The same for the gate's claims (its live verdicts).
> 2. **The recall denominators, blind:** a seeded random sample of 200 crops per arm (seed
>    20261172), labelled from `sheet` pages without `--verdict` (no reader output on them).
> 3. Labels: walk, talk, sword, pickup, noentry, warp, none, unclear. Unclear crops are excluded and
>    counted.
>
> **The bars (all on the robust reader; the gate's numbers are reported beside them):**
> 1. **SAFETY, hard: 0 cross-shape errors** among all flagged crops, first read or read twice, in
>    both arms. **WALK read on a crop labelled anything else: 0.** One error FAILS the acceptance;
>    no switch.
> 2. **TALK** on arm A's sprite points labelled talk: read twice ≥ 0.85.
> 3. **SWORD** on arm B's box points labelled sword: read twice ≥ 0.40 (with ≥ 100 such probes;
>    6 tries per still box then miss with ≤ 5 %), and ≥ the gate's + 0.25.
> 4. **WALK** on arm B's controls and arm A's cell points labelled walk: read twice ≥ 0.95 and not
>    below the gate's − 0.02 (no loss on the shape that clicks).
> Fewer than 100 labelled sword probes or 200 labelled talk probes: INCONCLUSIVE.
>
> **Reported:** both readers per arm, kind, NPC / background and grab index; the robust reader's
> best-shift distribution (C1), whether later grabs pass where the first failed (C2), unknown
> reasons; the labelling time.
>
> **Safety of the runs themselves:** arm A as its own pre-registration; arm B never clicks, so no
> attack request is possible: any `attack_request` or GM act in arm B's packets is a harness fault
> and stops the test.

## 6. The switch-over: a flag, never silent

Not built (a gate change: Batt's decision after section 5). The shape of it:
1. `cursor_gate.prober(agent, screen, classifier="v3")`: the default stays `"v3"`; `"robust1"`
   builds `cursor_robust.RobustRefs.load(REFS_V3)` instead of `walk6.CursorRefs.load(REFS_V3)`.
   Any other value raises (`GateUnavailable`). No environment variable: a rule run names it on its
   command line (`--cursor robust1`).
2. The session manifest records `cursor: robust1@<commit>`, and every read record carries
   `"clf"`; a scorer refuses a session without it.
3. **Pre-registered rules never change readers:** walk@15/16/17 and loot@1 keep v3 (their bytecode
   proofs stand; `cursor_robust.py` is imported by none of them). The robust reader enters through
   a NEW pre-registration that names it (loot@2, talk@1's amendment, walk@18).
4. Prober9 needs no change (`refs.match(a, mask)` is the whole interface). One harness detail:
   `npc_click_test.read_series` logs through `npc_click_score.explain`, which reads CursorRefs'
   arrays (`.m`, `.a`, `.cls`); a probe run whose prober carries RobustRefs logs the robust
   reader's own fields (`score`, `second`, `margin`, `shift`) instead. Part of the switch, not of
   the measurement (the measurement scores the robust reader offline).
5. Flipping the DEFAULT, if ever, is Batt's decision recorded in demonstrations.md, never a side
   effect of a merge.

## 7. Tools (this branch) and the commands behind the numbers
- `scripts/cursor_robust.py`: the robust reader (`RobustRefs`), `consensus_supports`.
- `scripts/cursor_eval.py`: `audit`, `floors`, `perturb`, `report`, `table`, `replay`, `live`,
  `sheet`.
- `scripts/cursor_probe.py`: `plan` (offline), `sword` (live, hover only; NOT run).
- `services/backend/tests/test_cursor_robust.py`: synthetic sprites only (no client pixels).

```bash
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD/scripts:$PWD/packages/poring_env/src:$PWD/packages/poring_dataset/src
R=data/walk6/cursor_refs_rdp_v3.npz
python scripts/cursor_eval.py audit  --refs $R
python scripts/cursor_eval.py floors --refs $R                      # ~1 min
python scripts/cursor_eval.py perturb --refs $R --out /dev/shm/poring-lab-tmp/cursor-eval/loo   # ~25 min, 1 core
python scripts/cursor_eval.py perturb --refs $R --neighbours 3 --out /dev/shm/poring-lab-tmp/cursor-eval/lno3 \
  --only "stored;own;shift+1,+0;shift+0,+1;subpx0.5,0.0;blur0.8;jpeg70;bg:grass;bg:town_stone;bg:church_floor;bg:poring_body;bg:npc_church;bob:poring_body:1;bob:poring_feet:1;bob:poring_church:1"
python scripts/cursor_eval.py report --out /dev/shm/poring-lab-tmp/cursor-eval/loo
python scripts/cursor_eval.py replay --refs $R --labels /dev/shm/poring-lab-tmp/cursor-robust/replay_labels.json
```

## Appendix A: every condition, leave-one-out (read / unknown / wrong; gate | robust)

Every row: 0 wrong reads for both readers (the cross-shape column of `cursor_eval.py table` is "0; 0" on all 61 rows).

| condition | walk | talk | sword | pickup | no-entry | warp |
|---|---|---|---|---|---|---|
| stored | 99/1/0 \| 99/1/0 | 85/7/0 \| 87/5/0 | 6/19/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 8/4/0 \| 10/2/0 |
| own | 99/1/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 7/18/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 9/3/0 \| 10/2/0 |
| shift+1,+0 | 7/93/0 \| 100/0/0 | 2/90/0 \| 91/1/0 | 1/24/0 \| 19/6/0 | 2/7/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 1/11/0 \| 10/2/0 |
| shift-1,+0 | 81/19/0 \| 100/0/0 | 1/91/0 \| 91/1/0 | 4/21/0 \| 19/6/0 | 4/5/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 9/3/0 |
| shift+0,+1 | 5/95/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 1/24/0 \| 17/8/0 | 3/6/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 2/10/0 \| 10/2/0 |
| shift+0,-1 | 77/23/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 2/23/0 \| 19/6/0 | 4/5/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 2/10/0 \| 10/2/0 |
| shift+1,+1 | 0/100/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 18/7/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 10/2/0 |
| shift-1,-1 | 0/100/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 19/6/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 10/2/0 |
| shift+2,+0 | 0/100/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 19/6/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 10/2/0 |
| shift+0,+2 | 0/100/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 18/7/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 1/11/0 \| 10/2/0 |
| shift-2,+0 | 0/100/0 \| 99/1/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 19/6/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 1/11/0 \| 8/4/0 |
| shift+0,-2 | 0/100/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 19/6/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 11/1/0 |
| subpx0.5,0.0 | 0/100/0 \| 86/14/0 | 63/29/0 \| 91/1/0 | 0/25/0 \| 11/14/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 12/3/0 | 0/12/0 \| 10/2/0 |
| subpx0.0,0.5 | 30/70/0 \| 100/0/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 11/14/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 9/3/0 \| 10/2/0 |
| subpx0.5,0.5 | 0/100/0 \| 83/17/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 13/12/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 3/12/0 | 0/12/0 \| 9/3/0 |
| blur0.5 | 98/2/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 3/22/0 \| 15/10/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 9/3/0 \| 10/2/0 |
| blur0.8 | 6/94/0 \| 66/34/0 | 0/92/0 \| 91/1/0 | 0/25/0 \| 6/19/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 8/4/0 |
| blur1.2 | 0/100/0 \| 0/100/0 | 0/92/0 \| 87/5/0 | 0/25/0 \| 2/23/0 | 0/9/0 \| 0/9/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 4/8/0 |
| jpeg90 | 99/1/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 7/18/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 8/4/0 \| 10/2/0 |
| jpeg70 | 96/4/0 \| 98/2/0 | 87/5/0 \| 91/1/0 | 4/21/0 \| 17/8/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 9/3/0 \| 11/1/0 |
| jpeg50 | 93/7/0 \| 91/9/0 | 84/8/0 \| 91/1/0 | 2/23/0 \| 14/11/0 | 7/2/0 \| 9/0/0 | 0/15/0 \| 0/15/0 | 9/3/0 \| 10/2/0 |
| noise5 | 99/1/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 7/18/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 9/3/0 \| 10/2/0 |
| noise10 | 99/1/0 \| 100/0/0 | 87/5/0 \| 91/1/0 | 7/18/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 8/4/0 \| 10/2/0 |
| noise20 | 0/100/0 \| 0/100/0 | 0/92/0 \| 0/92/0 | 0/25/0 \| 0/25/0 | 0/9/0 \| 0/9/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 0/12/0 |
| noise30 | 0/100/0 \| 0/100/0 | 0/92/0 \| 0/92/0 | 0/25/0 \| 0/25/0 | 0/9/0 \| 0/9/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 0/12/0 |
| bg:grass | 93/7/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 8/4/0 |
| bg:grass+jpeg80 | 93/7/0 \| 99/1/0 | 90/2/0 \| 92/0/0 | 5/20/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 8/4/0 |
| bg:green_grass | 91/9/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:green_grass+jpeg80 | 91/9/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 5/20/0 \| 17/8/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 6/6/0 |
| bg:poring_body | 93/7/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 7/18/0 \| 17/8/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:poring_body+jpeg80 | 94/6/0 \| 100/0/0 | 89/3/0 \| 91/1/0 | 2/23/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 6/6/0 |
| bg:poring_feet | 93/7/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 7/5/0 \| 8/4/0 |
| bg:poring_feet+jpeg80 | 93/7/0 \| 100/0/0 | 86/6/0 \| 90/2/0 | 3/22/0 \| 16/9/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:church_floor | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 10/2/0 |
| bg:church_floor+jpeg80 | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 5/20/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 3/9/0 \| 10/2/0 |
| bg:church_carpet | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 7/5/0 \| 11/1/0 |
| bg:church_carpet+jpeg80 | 99/1/0 \| 100/0/0 | 91/1/0 \| 92/0/0 | 6/19/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 11/1/0 |
| bg:church_pew | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 20/5/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 5/7/0 \| 10/2/0 |
| bg:church_pew+jpeg80 | 99/1/0 \| 100/0/0 | 91/1/0 \| 91/1/0 | 6/19/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:poring_church | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 17/8/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 5/7/0 \| 7/5/0 |
| bg:poring_church+jpeg80 | 98/2/0 \| 100/0/0 | 91/1/0 \| 92/0/0 | 3/22/0 \| 16/9/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:npc_church | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 8/4/0 |
| bg:npc_church+jpeg80 | 99/1/0 \| 100/0/0 | 90/2/0 \| 91/1/0 | 4/21/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 9/3/0 |
| bg:town_stone | 99/1/0 \| 100/0/0 | 36/56/0 \| 92/0/0 | 7/18/0 \| 17/8/0 | 0/9/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:town_stone+jpeg80 | 98/2/0 \| 100/0/0 | 28/64/0 \| 92/0/0 | 3/22/0 \| 13/12/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 3/9/0 \| 7/5/0 |
| bg:town_flag | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:town_flag+jpeg80 | 99/1/0 \| 100/0/0 | 91/1/0 \| 91/1/0 | 5/20/0 \| 17/8/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:npc_town | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 8/17/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 8/4/0 |
| bg:npc_town+jpeg80 | 99/1/0 \| 100/0/0 | 91/1/0 \| 92/0/0 | 3/22/0 \| 16/9/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 7/5/0 |
| bg:dungeon | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 16/9/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:dungeon+jpeg80 | 94/6/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 2/23/0 \| 12/13/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 4/8/0 \| 7/5/0 |
| bg:ui_window | 99/1/0 \| 100/0/0 | 20/72/0 \| 92/0/0 | 5/20/0 \| 16/9/0 | 0/9/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 5/7/0 \| 7/5/0 |
| bg:ui_window+jpeg80 | 97/3/0 \| 100/0/0 | 20/72/0 \| 92/0/0 | 2/23/0 \| 12/13/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 6/6/0 |
| bg:ui_chat | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 19/6/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:ui_chat+jpeg80 | 99/1/0 \| 100/0/0 | 90/2/0 \| 90/2/0 | 5/20/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:ui_skills | 99/1/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 6/19/0 \| 16/9/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 6/6/0 \| 7/5/0 |
| bg:ui_skills+jpeg80 | 97/3/0 \| 100/0/0 | 92/0/0 \| 92/0/0 | 3/22/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 5/7/0 \| 6/6/0 |
| bg:grass+shift+1,+0 | 7/93/0 \| 100/0/0 | 0/92/0 \| 92/0/0 | 1/24/0 \| 19/6/0 | 2/7/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 7/5/0 |
| bg:grass+blur0.8 | 0/100/0 \| 62/38/0 | 0/92/0 \| 72/20/0 | 0/25/0 \| 1/24/0 | 0/9/0 \| 7/2/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 5/7/0 |
| bg:town_stone+shift+1,+0 | 7/93/0 \| 100/0/0 | 0/92/0 \| 92/0/0 | 1/24/0 \| 16/9/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 7/5/0 |
| bg:town_stone+blur0.8 | 0/100/0 \| 50/50/0 | 0/92/0 \| 78/14/0 | 0/25/0 \| 7/18/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 5/7/0 |
| bg:poring_body+shift+1,+0 | 7/93/0 \| 100/0/0 | 0/92/0 \| 92/0/0 | 1/24/0 \| 17/8/0 | 2/7/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 1/11/0 \| 7/5/0 |
| bg:poring_body+blur0.8 | 1/99/0 \| 61/39/0 | 0/92/0 \| 78/14/0 | 0/25/0 \| 0/25/0 | 0/9/0 \| 7/2/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 4/8/0 |
| bg:npc_church+shift+1,+0 | 7/93/0 \| 100/0/0 | 1/91/0 \| 92/0/0 | 1/24/0 \| 19/6/0 | 2/7/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 8/4/0 |
| bg:npc_church+blur0.8 | 0/100/0 \| 61/39/0 | 0/92/0 \| 73/19/0 | 0/25/0 \| 5/20/0 | 0/9/0 \| 8/1/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 3/9/0 |
| bg:church_floor+shift+1,+0 | 7/93/0 \| 100/0/0 | 1/91/0 \| 92/0/0 | 1/24/0 \| 18/7/0 | 2/7/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 0/12/0 \| 9/3/0 |
| bg:church_floor+blur0.8 | 5/95/0 \| 59/41/0 | 0/92/0 \| 79/13/0 | 0/25/0 \| 5/20/0 | 0/9/0 \| 9/0/0 | 0/15/0 \| 0/15/0 | 0/12/0 \| 4/8/0 |
| bob:poring_body:1 | 0/100/0 \| 86/14/0 | 72/20/0 \| 90/2/0 | 0/25/0 \| 14/11/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 3/9/0 \| 9/3/0 |
| bob:poring_body:2 | 0/100/0 \| 0/100/0 | 0/92/0 \| 90/2/0 | 0/25/0 \| 14/11/0 | 4/5/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 0/12/0 \| 12/0/0 |
| bob:poring_feet:1 | 87/13/0 \| 100/0/0 | 72/20/0 \| 90/2/0 | 0/25/0 \| 17/8/0 | 5/4/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 0/12/0 \| 8/4/0 |
| bob:poring_feet:2 | 83/17/0 \| 100/0/0 | 72/20/0 \| 87/5/0 | 0/25/0 \| 18/7/0 | 0/9/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 0/12/0 \| 8/4/0 |
| bob:poring_church:1 | 31/69/0 \| 16/84/0 | 89/3/0 \| 88/4/0 | 0/25/0 \| 18/7/0 | 9/0/0 \| 9/0/0 | 15/0/0 \| 15/0/0 | 4/8/0 \| 8/4/0 |
| bob:poring_church:2 | 0/100/0 \| 14/86/0 | 71/21/0 \| 87/5/0 | 0/25/0 \| 16/9/0 | 8/1/0 \| 9/0/0 | 0/15/0 \| 15/0/0 | 2/10/0 \| 7/5/0 |
