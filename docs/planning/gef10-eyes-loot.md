---
doc_type: plan
hypothesis: "The bot loses most of its gap to Batt by not SEEING: monsters that chase it go unanswered (the v1 detector finds ~8 % of gef_fild10's monsters), and the loot step hovers on after the last pickup (1,180 of 1,379 loot-step seconds came after it). A trimmed loot step now, then a gef_fild10 detector with an item class, close most of it, with no English-text cue."
status: ACTIVE
role: plan
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-detector.md, gef10-eval.md, gef10-idle-study.md, gef10-time-budget.md, gef10-miss-cue.md]
next_action: "E1 (loot trim) is pre-registered for the cycle after c11 (>= D8 + 131); the round-2 cache build retries at 20:05; the staged-items session (E3, approved) runs between cycles once E1 is judged."
---

# gef_fild10: the bot's eyes and its loot step (plan, 2026-10-26 18:3x ICT)

## 1. Why: Batt's two clips (2026-10-26 18:12, run c8)

- **18:12:40 (3.8 s).** The Rogue walks its patrol from (77,254) to (88,264).
  - An Orc Warrior and an Orc Lady trail 2-3 cells behind it the whole time. The Warrior's HP bar
    shows it was hit earlier.
  - The bot never turns. Orcs walk slower than the Rogue, so they chase without landing a hit:
    no Battle Log line, no HP drop, no Miss.
  - The runner's only other sight of monsters is the v1 CPU detector, on gef_fild10:
    - about 8 % recall, Orc Lady 1.4 % (gef10-detector.md);
    - once a second;
    - it counts a box only within 110 px of our feet.
- **18:12:56 (14.4 s).** The last floor item is picked at ~2-3 s. Then for ~10 s the pointer
  hovers empty cells around the Rogue: loot v1's hover list and sweep.
  - The idle study measured this (gef10-idle-study.md): a loot step after one kill makes ~35
    hovers (~14-15 s).
  - **80 of 84 pickups came within the first 9 hovers.**
  - 1,180 of the 1,379 loot-step seconds came after the step's last pickup.

## 2. Batt's decisions and constraints (2026-10-26 ~18:2x)

- **Staged items on gef_fild10: APPROVED.**
  - The GM is immune.
  - Items are placed with @item and dropped by the inventory's known path.
  - Poporings are cleared first.
  - Staged items are never income: dungeon_judge's "staged" column, out of the total.
- **P2 (no sitting) is the default strategy.**
- **No English UI text as a cue.** A Thai rAthena server would break it. Pickup proof may not be
  the "obtained" notice or the "You got" Battle Log line.
  - Allowed: sprites, shapes, colours and digits.
  - Each new cue is checked on the Thai client (`--profile th`) before it is relied on there.

## 3. The workstreams, in order

### E1. LOOT TRIM (now; no model needed)

- **The change, from the idle study:** `--loot trim`, OFF by default.
  - Loot v1's order is unchanged: our own cell, then ring 1, nearest first.
  - Hovers are capped at 9 (`LOOT_MAX_HOVERS` 30 -> 9), with no sweep.
- **No text.** A pickup is still the PICKUP-hand cursor read before the click (a cursor shape).
- **Safety.**
  - It removes pointer hovers and adds no click.
  - The SWORD-verified strike, the NPC guard, the zones, the UI watch / gate and the hard bars
    are untouched.
- **Estimate, from the idle study:**
  - +14 kills / h: pooled 88.7 -> 102.7 over c5b-c8;
  - 4 of 113 pickups lost, all 2-3 cells out after multi-kill fights.
- **Pre-registration:**
  - Arms: P2 (the default) + `--loot v1` against P2 + `--loot trim`. Paired, >= 2 pairs, 36 min
    each.
  - **Primary:** kills / h from packets. **Bar:** trim - v1 >= +8.
  - **Secondary:**
    - loot-step seconds per kill <= 3.5 (from ~8.5);
    - floor-loot completeness within 8 points;
    - items / h and value / h at OC not lower;
    - damage per kill and potions + wings per h at most +10 %.
- **When:** built and pre-registered during c9-c11. It runs in the cycle after c11 (>= D8 + 131).

### E2. LOOT END BY SIGHT (after E5's item class)

- The pile is SEEN: the detector's item boxes inside the 5 x 5 around the death cell give the
  count.
- Each pickup is clicked at its box. The step ends the moment a fresh frame shows no item box
  left in the pile area. No hover list, no sweep.
- **Pickup proof, no text:**
  - the item's box vanishes from the detector's view;
  - AND the weight digits rise (a digit read, `gm_state._weight`; its position on the Thai client
    is checked first).
- A box under our own HP bar or a model counts as unsure. Only then a hover, on that cell alone.

### E3. THE STAGED-ITEMS SESSION (approved; D10's recipe)

- `scripts/stage_items.py` (built for pay_fild07). Here it uses the gef_fild10 drop set:
  - Cyfar, Orcish Voucher, Sticky Mucus, Milk, Garlet, Iron, Large Jellopy, Rough Oridecon, Green
    Herb, Nursing Bottle, Axe;
  - with gef_fild10's open-ground spots: off the RSW footprints, away from the warps, the Kafra
    and the bulletin board (the zones, delegated).
- **Positions that matter for the loot case:**
  - **at our own feet, under our HP bar** (where today's drops land: 13j);
  - beside another item;
  - beside a model;
  - on open ground.
  Each item type in each, from several camera offsets.
- **Steps:**
  1. Immunity ON, judged from its frame.
  2. Poporings cleared: they loot staged items (memory: staged-items looter contamination).
  3. The 1-fps recorder beside it. Labels from packets OFFLINE: floor-item cells and appear /
     vanish times, item_labels.py.
- **Target:** >= 40 labels from >= 10 floor items per class (gef10-detector.md section 7).
- **Slot:** between hunt cycles, about 45 min. The relog afterwards clears @monsterignore.

### E4. ROUND 2: THE MONSTER DETECTOR (tonight; registered in gef10-detector.md 13s-13u)

- 26 classes, with Orc Lady, Orc Warrior, Orc Baby, Orc Lord and Orc Archer; no items (D10).
- **The cache build** retries once at 20:05 (Batt). If it aborts again: stop and ask.
- **Training:**
  - 10 epochs from payf07's epoch-1 weights;
  - R1-R3, the duty cycle, the IO guard, the 25 % VRAM cap;
  - MID_CKPT gives a checkpoint per epoch. One epoch is ~1 h nominal, but ~10 h of wall time
    under Frigate's load (payf07's).
- **The scored check:** gef10-eval.md, per-species recall on held-out sessions. Before anything
  goes live.

### E5. ROUND 3: MONSTERS + ITEMS (after E3)

- Round 2's classes, plus item classes from E3's labels, plus today's gef_fild10 runs as extra
  monster data:
  - b1, c1, c3-c8 and Batt's demo, banked on the NAS with packets;
  - the same frozen label rules, TEST sessions held back.
- Pre-registered like round 2: T1 / T2 label checks, then the eval.

### E6. THE "EYES" RUNNER VERSION (after E4 passes its eval)

- **The new model in BoxWatch, on the CPU** (the hunt detector stays CPU unless Batt decides):
  - first measure its latency per frame, then set the rhythm: <= 0.5 s if the CPU allows.
- **The CHASER rule:** a monster box within ~5 cells across >= 2 consecutive reads while we walk
  means stop walking and engage.
  - The strike still needs the SWORD cursor read, the NPC guard and the zones. No new click path.
- The watch radius grows from 110 px to the chaser's ~5 cells. Boxes behind us count.
- **Measure (offline, packets): CHASE TIME.**
  - From a monster's first move toward us within 5 cells to our first attack on it.
  - Today's runs give the baseline (Batt's clip is one such chase). Pre-registered with the
    version.

### E7. RUNNER-UPS FROM THE IDLE STUDY (each its own version, later)

- **Longer walk legs, routed through the next waypoint:** +3 / +5 / +7 cells estimated at
  +8.1 / +11.1 / +12.5 kills / h. With E1, about 122 kills / h if independent.
- **Patrol dead end (a bug, c7):** a whole-run no-entry carve sealed a pocket of the route grid,
  and the runner stood 62.8 s. Fix: route without the carves when nothing routes, and a Fly Wing
  after one lap of skips.
- **Empty defend scans** after a Battle Log hit with no SWORD in rings 1-2: up to +1.7 / +1.1.

## 4. Language dependencies today (an audit for the Thai server; nothing changes tonight)

| cue | reads | language-free? |
|---|---|---|
| Battle Log trigger (`battle_log.py`) | English lines: `[name] receives 'N' damage points.`, `You got ...` | **no**: Thai lines need their own parser, or a pixel cue instead |
| HP / SP percent (`hp_percent.py`) | digit glyphs | digits: yes; positions to check on the Thai client |
| Hotbar stock (`hotbar_count.py`) | digits | yes |
| Weight (`gm_state._weight`) | digits after a label | digits yes; the label's width may move them |
| Miss cue (`miss_cue.py`) | the client's "Miss" sprite | to check on the Thai client's GRF |
| Cursor reads (SWORD / PICKUP / WALK) | cursor sprites | yes |
| UI gate templates | window chrome and titles | titles may differ: the gate refuses the unknown (safe, fail closed) |
| Pickup notice "obtained" | English text | **not used** (Batt) |

## 5. Timeline (ICT, 2026-10-26 evening; each live step behind its pre-registration)

1. 18:41-20:41: cycle D8. c9 (P2 + cue), c10 (P2), c11 (P2 + cue). Meanwhile:
   - E1 is built in a tmpfs worktree, with census + safety tests;
   - its pre-registration is committed before the next cycle.
2. 20:05: the round-2 cache build (E4). If rc 0: the R2 check, then training.
3. >= D8 + 131 (~20:52): the E1 cycle (trim vs v1, paired).
4. After E1's verdict: the staged-items session (E3), between cycles.
5. Round 2's first checkpoint -> the eval -> E6's pre-registration.
6. E3's labels -> round 3 (E5) -> E2.
