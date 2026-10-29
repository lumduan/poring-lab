---
doc_type: plan
hypothesis: "The bot loses most of its gap to Batt by not SEEING: monsters that chase it go unanswered (the v1 detector finds ~8 % of gef_fild10's monsters), and the loot step hovers on after the last pickup (1,180 of 1,379 loot-step seconds came after it). A trimmed loot step now, then a gef_fild10 detector with an item class, close most of it, with no English-text cue."
status: ACTIVE
role: plan
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-detector.md, gef10-eval.md, gef10-idle-study.md, gef10-time-budget.md, gef10-miss-cue.md]
next_action: "2026-10-29 12:08: E5 STARTED (gef10-round3.md, PROPOSED; split fixed, TEST3 = e3b refused by name; ➡️ classes: Batt chose C, one pooled `item` class). Next: the offline build (round3 section 5). Before that, 2026-10-29: E3 COMPLETE with the short second session e3b (rogue-gef10.md AK-5/AK-6): the icon match fixed (stage@6 masked references), 6 of 6 spots, 36 staged floor items, no stop; E3 + e3b = 148 staged floor items, every class >= 10 (Cyfar 12). Next: E5 (labels; item_labels.py needs gef_fild10). Earlier, 2026-10-28: E3 RAN 15:11-15:50 (rogue-gef10.md AK-AK-3): 18 of 22 spots, 112 staged floor items, 9-11 per class (Cyfar 9); stopped by its drop check (icon references carry the new-item glow: fix before any second session); labels wait for E5. Earlier: E1 (loot trim) is pre-registered for the cycle after c11 (>= D8 + 131); the round-2 cache build retries at 20:05; the staged-items session (E3, approved) runs between cycles once E1 is judged; its offline prep is done (stage@5, 'E3 prep, offline': icon set A, then the ~47-min session B)."
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

- ➡️ **Run 2026-10-28** (Batt's go ~14:5x): pre-registered in rogue-gef10.md Amendment AK (two
  changes: the store step first, and immunity on / off by the judged toggle instead of a relog).
- ➡️ **Result 2026-10-28** (rogue-gef10.md AK-3): 18 of 22 spots, 112 staged floor items (9-11 per
  class; Cyfar 9, one short of the >= 10 target). The run stopped itself at spot 18 (two correct
  items read 3.07 / 3.29 against the 3.0 icon bar: the references carry the new-item glow). A
  Poporing may still carry <= 4 staged items (the extra kill was unobservable from one spot).
- ➡️ **Second session 2026-10-29** (Batt: fix the icon match, then a short second session;
  rogue-gef10.md AK-5 pre-registered, AK-6 result): stage@6's masked references (the client's own
  item icons, item pixels only) dropped 47 of 47 in the field. e3b: 6 of 6 spots, 36 staged
  floor items (3-4 per class), no stop; spots 0-1's 12 were looted within 0.3-6.2 s. **E3 + e3b:
  148 staged floor items, every class >= 10 (Cyfar 12).** Safety: npc_contact 0,
  attack_request 0, act 0; 18 map changes = our warps.


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

#### E3 prep, offline (2026-10-26 19:19 ICT from `date`; stage@5, commits 6a15930, b12c539)

Nothing live was run for this prep. `scripts/stage_items.py` is now **stage@5**: the item set is
per map (`MAP_SETS`).
- pay_fild07's set is the default and is unchanged. Its `spots` reproduce the recorded stage-b
  (seed 7) and stage-c (seed 8, `--open`) lists exactly. Its `run` types exactly stage@4's lines
  (a test drives it offline through fakes).
- Tests: `test_stage_items.py`, `test_stage_items_gef10.py`, `test_stage_items_run.py`, 19 pass;
  the click census and dungeon_judge tests stay green.

**The item ids and where each came from.** Every id is in the local KB, built from the pinned
rAthena e985006 and never committed: `data/kb/items.json` gives the id by name, and
`data/kb/drops.json` shows which gef_fild10 species drops it. The docs agree:
gef10-detector.md 1e lists all 11 (Nursing Bottle under its aegis name, Milk Bottle), and
gef10-prep.md 1a lists all but Green Herb.

| item | id | dropped by (drops.json, rate / 10,000) | icon name |
|---|---|---|---|
| Cyfar | 7053 | Orc Lady 4656 | `cyfar` |
| Orcish Voucher | 931 | Orc Warrior 9000 | `orcish_voucher` |
| Sticky Mucus | 938 | Poporing 5500 | `sticky_mucus` |
| Milk | 519 | Orc Baby 5000 | `milk` |
| Garlet | 910 | Poporing 1500 | `garlet` |
| Iron | 998 | Orc Lady 300, Orc Warrior 210 | `iron` |
| Large Jellopy | 7126 | Orc Baby 1000 | `large_jellopy` |
| Rough Oridecon | 756 | Orc Warrior 40 | `rough_oridecon` |
| Green Herb | 511 | Poporing 500, Green Plant 7000 | `green_herb` |
| Nursing Bottle | 7270 (aegis `Milk_Bottle`) | Orc Baby 200 | `nursing_bottle` |
| Axe | 1301 | Orc Warrior 100 | `axe` |

- Axe has three ids in items.json (1301, 1302, 1303). Only 1301 is in a gef_fild10 drop table.
- The icons go to `data/thief/stage_icons/gef_fild10/` (client pixels, never committed).
- Inventory tabs: 8 items in Etc, Milk and Green Herb in Use, Axe in Eqp. `clear_loot` reads all
  three.

**Positions covered.** Each spot gets a group of 6 items. A floor item lives 60 s. At stage-c's
cadence the drops come ~5 s apart, so eleven drops at one spot would expire before the views.
The groups are balanced and seeded: over 22 spots, each item is staged 12 times (132 floor
items).
- **(a) At our own feet, under our HP bar:** the (0, 0) view right after the drops. rAthena puts
  each dropped item on a cell of the 3 x 3 around us, and a spot needs that whole 3 x 3 inside
  the area.
- **(b) Several items beside each other:** the 6 items of a group share that 3 x 3.
- **(c) From the existing offsets:** (3, 0) shows the pile beside us and (0, 3) shows it below us.
  Two existing offsets are dropped:
  - (0, -3) would put the pile behind our own sprite;
  - (-3, 0) mirrors (3, 0), because an item is one billboard frame.
- **Expected views per spot:** all 6 items in (0, 0) and in (3, 0); about the last 4 in (0, 3).
  The first item expires ~32 s after the last drop.
- **Tab-order bias:** `clear_loot` drops the Etc tab first, so Etc items expire first and appear
  in fewer (0, 3) views.
- **Not covered: "beside a model".** Spots are open ground only. An item hidden under a model
  cannot be learnt from pixels anyway.

**The spots** (`spots --map gef_fild10 --n 22 --seed 2610 --open CANOPY --plan`):
- The canopy is built by `stage_items.py canopy --map gef_fild10` from the RSW in
  `/dev/shm/poring-lab-tmp/gef10-det/grf/data`. It has 67,533 cells, sha256 `1c0aa910…bc0d1`.
  Its rule (a model whose top is above altitude 10, vertex box floor..ceil) rebuilds stage@2's
  pay_fild07 mask cell for cell.
- Each spot is on the hunt's search area: client and server both walk it, it is outside warp
  spans and NPC touch areas, it is >= 10 cells off every warp, the zones apply, and the
  sealed-off pockets are cut. On top of that:
  - >= 10 cells off every NPC cell (the Kafra, the bulletin boards, the Orc's Memory NPCs);
  - open ground (the canopy widened 3 cells, and 6 to the north);
  - views and pile inside;
  - >= 25 cells apart;
  - `npc_click_test.check_warps` is a refusal on all 66 stands.
- Checked independently: minimum spacing 27; >= 14 cells from a warp span; >= 17 from an NPC; no
  view or pile cell in the canopy, in a zone, or on a cell the server or client refuses.

| k | spot | group | k | spot | group |
|---|---|---|---|---|---|
| 0 | (92,90) | Cyf Vou Gar ROr GHe Axe | 11 | (130,316) | Mil Gar Iro LJe ROr Axe |
| 1 | (239,185) | Muc Mil Iro LJe ROr NBo | 12 | (119,281) | Cyf Vou Muc ROr GHe NBo |
| 2 | (196,309) | Mil Gar Iro LJe NBo Axe | 13 | (192,68) | Cyf Vou Muc Iro GHe Axe |
| 3 | (127,148) | Cyf Vou Muc Iro GHe NBo | 14 | (316,197) | Mil Gar LJe ROr GHe NBo |
| 4 | (214,139) | Vou Muc Gar LJe GHe Axe | 15 | (81,155) | Vou Muc Mil Gar Iro LJe |
| 5 | (262,93) | Cyf Vou Mil ROr GHe Axe | 16 | (121,178) | Cyf Gar Iro LJe NBo Axe |
| 6 | (288,169) | Muc Mil Gar Iro LJe NBo | 17 | (314,75) | Vou Muc Mil ROr NBo Axe |
| 7 | (48,200) | Cyf LJe ROr GHe NBo Axe | 18 | (89,121) | Cyf Vou Mil Gar GHe NBo |
| 8 | (169,298) | Cyf Vou Muc Gar Iro ROr | 19 | (282,134) | Cyf Muc Iro LJe GHe Axe |
| 9 | (60,83) | Cyf Vou Mil Gar LJe NBo | 20 | (120,76) | Cyf Vou Gar Iro ROr GHe |
| 10 | (79,276) | Muc Mil Iro ROr GHe Axe | 21 | (220,279) | Muc Mil LJe ROr NBo Axe |

**Poporings and the end of the session (`--clear end`, gef_fild10's default).**
- `@killmonster2` cannot keep Poporings away. They respawn 5 s after it (rAthena's minimum spawn
  delay; their spawn line has delay 0) on random cells of the whole map.
- It also does NOT erase what a looter took. The pinned `mob.cpp` `mob_dead` drops a looter's
  loot even on a no-drop death (its "Loot MUST drop!" branch, rathena e985006, read
  2026-10-26).
- So the run ends with two `@killmonster2` lines 65 s apart:
  - the first makes every carrier drop the staged items, which expire 60 s later;
  - the second catches a Poporing that re-looted them in between.
- A start kill is NOT typed. It would not lower the looting odds, because the respawn is
  uniform. It would kill the Orc Lord ~45 min before the next cycle, and the Lord would then
  respawn inside that cycle.
- **The Orc Lord clock (the parent's call).** The first end kill kills the natural Orc Lord if
  it is alive. The Lord is alive when the session ends >= 131 min after the previous cycle's D,
  unless something killed it since. The run prints `killmonster2_ict`, and its first time can
  then serve as the next cycle's D (runs released within [D, D + 120)). The cycle's own setup
  kill then finds the Lord dead and changes nothing (rogue-gef10.md A4).
- The other option is `--clear none`. The Lord's clock stays untouched, but any carrier
  survives into the hunts.
- dungeon_judge cannot flag such a carrier's pile. Its staged rule knows pay_fild07's four target
  ids only. For this set it would false-flag natural piles: one Orc Warrior can drop Voucher,
  Iron, Rough Oridecon and Axe together.

**The parent's live sequence** (main checkout after the merge; Batt approved staging on
gef_fild10 on 2026-10-26).

**A. The icon set:** on the prt_fild08 stand (268,107), no immunity needed, ~10 min.
1. **The store step** (rogue-gef10.md section 4: `@storage` + `gm_state.store_loot`).
   - The bag must hold none of the 11 items: `clear_loot` drops WHOLE stacks.
   - Then `stage_items.py held --map gef_fild10` must return rc 0.
2. `stage_items.py give --map gef_fild10 --frames`.
   - It types 11 `@item` lines.
   - It then opens the inventory by its chord, reads it open, and banks one desktop frame per
     tab: `/dev/shm/poring-lab-tmp/shots/stage-give-gef_fild10-{etc,use,eqp}.png`.
   - It prints the game region's origin.
3. Judge the frames and write the SPEC. Then run
   `stage_items.py cut /dev/shm/poring-lab-tmp/stage-gef10/icons-spec.json --map gef_fild10`.
   - SPEC format: `{"origin": [gx, gy], "icons": [{"png": ".../stage-give-gef_fild10-etc.png",
     "col": c, "row": r, "name": "cyfar"}, ...]}`, one entry per icon name in the table.
   - `cut` writes nothing when an icon is within 6.0 of the White Potion, Fly Wing or empty-slot
     references (clear_loot would drop that stock), or within 3.0 of another icon of the set.
4. `stage_items.py drop --map gef_fild10`: the icon set's positive case.
   - rc 0 means `all_and_only_the_set` is true: all 11 were found and dropped, and the stock
     stayed.
   - rc 1: stop and re-cut.
5. **The DB catches up.**
   - Do an empty store step (its storage close saves the inventory) or wait for the autosave.
   - Then `held --map gef_fild10` must return rc 0. `run` refuses until it does.

**B. The session:** ~47 min, between cycles.

6. Build the canopy once (`<canopy>` below):

       stage_items.py canopy --map gef_fild10 \
           --out /dev/shm/poring-lab-tmp/stage-gef10/gef_fild10-canopy.npy

   - Expect cells 67,533, sha256 `1c0aa910…`.
   - After a host reboot, re-extract the RSW and models first.
7. On a fresh login, run `stage_items.py immune-on`, where the earlier immune watches typed it.
   A person judges `stage-immune.png`.
8. Start the recorder, then the run, as `/dev/shm/poring-lab-tmp/gef10-ow/w2.sh` does.
   - Recorder: `record_session.py --backend rdp --label stage-gef10-e3 --seconds 3300 --fps 1
     --format png --out /dev/shm/poring-lab-rec --max-bytes 8G --min-free-gb 6
     --max-unshipped-gb 12`.
   - Size: ~2.2 MB a frame (stage-b: 1,538 frames, 3.42 GB), so ~6.3 GB for 48 min. w2.sh's
     7G leaves only ~10 %, hence 8G. /dev/shm had 21 GB free at 19:2x.
   - Run: `stage_items.py run --map gef_fild10 --n 22 --seed 2610 --open <canopy>
     --immune-confirmed --label e3`.
   - Stop the recorder by PID >= 65 s after the run's last line, so the packets show whether
     the second kill's drops expire untouched. Ship it.
9. Relog. This clears @monsterignore. Set the next cycle's D from `killmonster2_ict`, as above.
10. **Offline, from the packets:**
    - which staged floor ids vanished before 60.0 s (looted);
    - that they fell again at the first end kill;
    - no early vanish after the second kill's falls.
    - If there is one, a Poporing still carries staged items. Type one more `@killmonster2`
      >= 60 s later, before any hunt.

**Expected duration** (stage-c's cadence, from its events and `data/ro_agent/gm.jsonl`):
- Measured parts:
  - a `@warp` + settle takes ~9.5 s;
  - `@item` lines come ~5 s apart;
  - an offset view takes 16.6 s (16.5-16.8);
  - `clear_loot` of 4 items took ~32 s.
- Estimated part: 4 drops split as ~10 s fixed + ~5.5 s per drop.
- Per spot: about 9.5 + 3 + 25 + 3 + 43 + 5 + 33 ≈ 122 s (the warp, the first line, 5 more
  lines, the chat close, clear_loot of 6, the (0, 0) view, two offset views).
- 22 spots take ~45 min. The end pair adds ~1.3 min. Total **~47 min**, roughly 42-52.
- Yield: 12 floor items per item, 2 above the >= 10 floor items per class.
- Looting can cost some: stage-c lost items at 5 of its 12 spots on pay_fild07. If an item ends
  below 10, a second session with `--seed 2611` adds 12 more of each.

**Open for E5's pre-registration (not decided here):**
- The frozen gef10-items rule (gef10-detector.md section 8) EXCLUDES every frame with an item
  under our box or under our HP bar (`under_self`, `under_self_bar`, frame-level).
  - So the (0, 0) views, the case 13j found most common, give no labels unless E5 labels them.
  - The offset views give ~10 item-views per spot under the current rule.
- No new English-text cue. The new code reads inventory icon pixels and the UI gate's existing
  window templates only.
- `gm_state.clear_loot` does not read the inventory open after its chord. `dungeon_hunt.clear_etc`
  does, since its toggle incident.
  - `give --frames` calls the UI gate first and then reads the window open before any tab click.
  - `drop` calls the UI gate first, so the chord opens a closed inventory.
  - `run` keeps the proven stage@1-4 path.

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

- ➡️ **Started 2026-10-29** (Batt: "go ahead, but do not affect the other work"): the PROPOSED
  pre-registration is `gef10-round3.md`. The split is fixed there before any read: TEST3 = e3b
  (refused by name), FIT = E3 spots 0-3, TRAIN = E3. The at-our-feet rule is kept. **The item
  classes wait for Batt** (A: Cyfar + Voucher + pooled, needs one more staged session; C: one
  pooled class, enough data now; recommended C). ➡️ **Batt chose C** (~12:1x): one pooled `item` class. Frames are read from the NAS after the
  2026-10-30 ship; the GPU only after round 2's evaluation.

- Round 2's classes, plus item classes from E3's labels, plus today's gef_fild10 runs as extra
  monster data:
  - b1, c1, c3-c8 and Batt's demo, banked on the NAS with packets;
  - the same frozen label rules, TEST sessions held back.
- Pre-registered like round 2: T1 / T2 label checks, then the eval.
- **A decision E5's pre-registration must make (from the E3 prep, 2026-10-26 19:2x):** the frozen
  gef10 item label rule EXCLUDES frames with an item under our own box or HP bar (under_self /
  under_self_bar). That is exactly the loot case: today's drops land at our feet. So E3's (0,0)
  views give no labels unless E5 changes that rule, and its T1 / T2 checks must then cover those
  labels too.

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
