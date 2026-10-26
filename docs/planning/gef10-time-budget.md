---
doc_type: measurement
hypothesis: "Measured with ONE ruler from the packets, the bot's gef_fild10 runs lose their time against Batt's demo in a few causes that can be ranked by seconds per kill, and the largest of them are not the fight itself (the time to kill is fixed by the build)."
status: "MEASURED (offline): Batt's demo (14.95 min) against 8 bot runs (a2, a3, a4, a7, a8, a5b, a9, a11; 4.80 h). Nothing is decided here."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, ../../scripts/time_budget.py, ../../scripts/dungeon_judge.py, ../../scripts/dungeon_style.py, ../../config/routes/gef_fild10-batt-loop.json, ../../config/routes/README.md]
next_action: "The parent and Batt: design dungeon@9 against section 5's ranking. The biggest loss is the REST (33 s per kill), and it sits downstream of the DAMAGE taken per kill (7x Batt's): resting in the field, the slow defend scan and attackers it never finds. Next come the stop-and-go walk (15 s per kill) and the loot pause (5 s per kill). Batt's loop is in config/routes/gef_fild10-batt-loop.json; it still needs his review as a routes YAML before a runner may walk it."
title: "gef_fild10: where the bot's time goes against Batt's demo (time budget, per-kill cycle, his loop, ranked losses)"
date: 2026-10-26
owner: Batt
---

# gef_fild10: where the bot's time goes against Batt's demo

**Why.** Batt played the Rogue on gef_fild10 for 14.95 min as the benchmark
([rogue-gef10.md](rogue-gef10.md) Amendment L). He reached 232.7 kills / h; the bot's runs reached
about 44. His bar is "at least my numbers". This document says **where the bot loses its time
against him, ranked by time lost**, so that dungeon@9 (modelled on his loop) attacks the biggest
losses first.

**What this is NOT.** It changes no runner and no parameter, and it decides nothing. Every number
is **measured** from the packets unless it is marked **estimate**.

## 0. The answer in brief

1. **The fight is NOT where the time goes.** Time to kill: 5.31 s median for both (Batt 5.37 s mean,
   bot 5.15 s). The engage distance is 1 cell for both, and in both most monsters swing first:
   47 of 58 for Batt, 201 of 212 for the bot.
2. **The bot needs 81.6 s per kill, Batt 15.5 s.** Of the 66.1 s gap:

   | cause | share of the gap |
   |---|---|
   | rest | 50 % |
   | stop-and-go walking | 22 % |
   | the slow reaction when a monster swings first | 8 % |
   | the loot pause | 7 % |
   | idling beside rests | 7 % |
   | the pause after a fight | 4 % |
   | everything else | about 1 % |

3. **The rest comes downstream of the damage.** The bot takes 239 HP per kill, Batt 34 HP: 7 times
   as much.
   - It suffers 29 attack attempts per kill against his 7.
   - 40 % of those attempts land while it rests in the field or idles beside a rest.
   - 25 % land while it scans for an attacker that is already hitting it.
   - In 20 minutes (6.8 % of the bot's time), monsters attacked it and it never hit them back.
4. **The stop-and-go walk.**
   - The bot walks at Batt's speed (about 340 cells per walking minute) but only 8.7 % of the
     time; Batt walks 35.6 % of the time.
   - 64 % of its walk decisions refuse to click: the cursor reads "unknown".
   - Its walk clicks fall a median 3.9 s apart. Batt sends 28 walk requests a minute, one every
     2.1 s, and does not stop.
5. **Batt's 232.7 kills / h is a 15-minute burst; it is not a steady state** (estimate).
   - His HP fell from 1,710 to 846 while he hunted, with one White Potion (+450).
   - Holding HP steady at his pace would cost either about 12 White Potions / h, or about 6 s of
     sitting per kill. With the sitting, his own style gives about 174 kills / h.
6. **His loop.**
   - 82 waypoints, 833 cells, clockwise.
   - He walked it TWICE: lap 1 took 8.9 min (41 kills), lap 2 took 4.9 min.
   - His kills lie a median 1 cell from the loop, 83 % of them within 5 cells.
   - The bot's kills lie a median 22 cells from it, 20 % within 5.
7. **The judge fix.** Batt's 82 items are now 44 picked / 38 snatched / 0 other (before:
   44 / 0 / 38). That moves his **value at Overcharge from 52,780 to 102,084 z / h** (section 8).

## 1. What was read

- **Batt:** `20261026T095021-demo-human-demo-gef10`.
  - The window is his first input `t0_live_ns` .. + 898 s, capped at the recording's end: 897.2 s.
  - At 848.4 s he walked into in_orcs01 and sat. The "field" columns stop at that map change.
- **The bot:** the 8 runs of the brief, each run_start .. run_end, 36 min each, 4.80 h in all.
  - Arm N (no Steal): a4, a8, a5b, a9. Arm S (Steal first): a2, a3, a7, a11.
  - Batt chose arm N (Amendment L), so arm N is shown pooled on its own as well.
  - a1 (the Orc Lord death), a6 and a10 (the restock-bug death) are not in the brief's list.
- **Packets:** each run's `packets.jsonl.gz` in /dev/shm. It is the same data as the recording's
  copy on the NAS: the a2 and a9 windows match type by type (3,454 and 5,232 packets).
- **Batt's input log** was read only to count events per label (section 3). Nothing of it is
  copied, stored or quoted.
- **The client GAT** (`/dev/shm/poring-lab-tmp/gat/data/gef_fild10.gat`) was used only to check
  and snap waypoints. Nothing of it is committed.

## 2. The definitions (the same for Batt and the bot)

They are in `scripts/time_budget.py`'s docstring, which is the definition of record. Every instant
of a window gets exactly ONE label. Where spans overlap, the first label in this order wins:

| label | definition (short) |
|---|---|
| **rest** | our sitting (act sit -> stand), plus the runner's rest_go -> rest_end, plus time on another map (Batt's in_orcs01) |
| **fight** | per engagement: our first act on the monster (a miss counts) until it dies, or our last act + 1 s if it does not |
| **loot** | per pile (one kill's drops): from the walk that ends at its first item until the pickup_result of its last pickup |
| **approach** | from the earliest of our attack request on it, the walk that ends at it, and ITS first act on us (<= 15 s back), until our first act. **react** = from its first act on us to our first request or walk toward it; **close** = the rest |
| **search** | our walking (self_move paths) with none of the above |
| **idle** | everything else, split by its neighbours: *inside search*, *loot pause*, *after fight*, *before engage*, *around rest*, *other* |

**Changed after a first look, and recorded:**
- The loot span is per pile, not per request. Per request, Batt's 44 pickups added up to 1 s.
- The approach was split into react and close, and idle by its context. This locates the losses;
  no label boundary moved.
- The route comes from his first lap, because he walked the loop twice.

**Sensitivity of the 15-s approach bound.**
- With 60 s instead, the bot's approach per kill goes from 6.5 to 9.7 s. The extra 3.3 s come out
  of idle (-2.4 s) and search (-0.8 s). Its median reaction goes from 12.7 to 14.9 s.
- Batt's numbers do not move (median 1.26 s).

## 3. The time budget (seconds; share of the window)

| label | Batt (897 s) | Batt, field only (848 s) | bot pooled (8 runs, 17,294 s) | bot arm N (4 runs, 8,652 s) |
|---|---|---|---|---|
| fight | 311 s, 34.7 % | 311 s, 36.7 % | 1,137 s, 6.6 % | 570 s, 6.6 % |
| approach | 62 s, 6.9 % | 62 s, 7.3 % | 1,370 s, 7.9 % | 599 s, 6.9 % |
| loot | 9 s, 1.0 % | 9 s, 1.0 % | 24 s, 0.1 % | 9 s, 0.1 % |
| rest | 49 s, 5.4 % | 0 s, 0 % | 7,187 s, **41.6 %** | 3,661 s, **42.3 %** |
| search | 310 s, 34.6 % | 310 s, 36.6 % | 1,307 s, 7.6 % | 638 s, 7.4 % |
| idle | 156 s, 17.4 % | 156 s, 18.4 % | 6,269 s, **36.2 %** | 3,174 s, **36.7 %** |
| **kills / h** | **232.7** | 246.1 | **44.1** | 44.1 |

- **The rest cross-check.**
  - The bot's sitting from the packets is 7,068 s. Its runner rest_start -> rest_end is 6,986 s.
  - The label adds the walk to the spot, rest_go -> rest_start. That is why it reads 41.6 %, not
    the ~35 % quoted before.
- **Batt's input in each label** (aggregate counts only):

  | label | mouse moves | clicks / buttons | keys |
  |---|---|---|---|
  | search | 2,708 | 744 | 0 |
  | idle | 2,511 | 194 | 0 |
  | fight | 1,117 | 61 | 2 |
  | approach | 1,005 | 72 | 0 |
  | loot | 146 | 13 | 0 |
  | rest | 37 | 4 | 12 |

  His "idle" is not idle hands: it is mostly the pause to aim the loot click and the wait for the
  monster to arrive (section 4).

**Per run** (shares in %, in this order: fight / approach / loot / rest / search / idle):

| run | arm | kills / h | shares | hits / kill | dmg / kill | unanswered s | Fly Wings | potions | kills' median distance to the loop |
|---|---|---|---|---|---|---|---|---|---|
| a2 | S | 48.3 | 7.2 / 12.1 / 0.1 / 25.5 / 10.3 / 44.8 | 1.14 | 131 | 19 | 1 | 0 | 22 |
| a3 | S | 50.0 | 7.2 / 8.6 / 0.3 / 40.7 / 7.7 / 35.4 | 1.17 | 129 | 85 | 1 | 0 | 19 |
| a4 | N | 51.7 | 8.0 / 8.5 / 0.0 / 49.5 / 6.3 / 27.8 | 1.71 | 194 | 18 | 2 | 4 | 6 |
| a7 | S | 46.6 | 6.6 / 8.6 / 0.3 / 55.6 / 4.5 / 24.4 | 1.79 | 205 | 25 | 1 | 1 | 30 |
| a8 | N | 33.3 | 5.0 / 6.2 / 0.0 / 29.0 / 10.3 / 49.5 | 3.70 | 410 | **321** | 10 | 10 | 16 |
| a5b | N | 43.3 | 6.6 / 5.5 / 0.1 / 56.3 / 6.4 / 25.1 | 1.88 | 220 | 19 | 2 | 2 | 6.5 |
| a9 | N | 48.1 | 6.8 / 7.5 / 0.3 / 34.5 / 6.6 / 44.4 | 2.90 | 332 | **501** | 10 | 10 | 25 |
| a11 | S | 31.7 | 5.2 / 6.4 / 0.0 / 41.3 / 8.4 / 38.7 | 3.58 | 410 | 187 | 2 | 9 | 39 |

## 4. The per-kill cycle (kill to kill)

| | Batt (57 cycles) | bot pooled (204) | bot arm N (102) |
|---|---|---|---|
| **kill to kill, median / p75 (mean)** | **14.8 / 19.2 s (14.3)** | **33.3 / 86.2 s (79.0)** | 34.2 / 94.6 s (80.2) |
| fight, median / p75 | 5.31 / 5.90 | 5.32 / 5.91 | 5.31 / 5.91 |
| approach, median / p75 | 0.89 / 1.32 | 4.96 / 11.68 | 3.66 / 9.47 |
| loot, median / p75 (mean) | 0 / 0 (0.15) | 0 / 0 (0.12) | 0 / 0 (0.09) |
| rest, median / p75 (mean) | 0 / 0 (0) | 0 / 0 (32.4) | 0 / 0 (33.1) |
| search, median / p75 | 3.15 / 7.6 | 0 / 8.18 | 0 / 8.07 |
| idle, median / p75 | 3.03 / 4.52 | 13.35 / 38.73 | 11.7 / 37.0 |
| hits taken per cycle, mean | 0.30 | 1.98 | 2.54 |

| per kill | Batt | bot pooled | bot arm N |
|---|---|---|---|
| time to kill (first hit -> death), median / p75 | 5.31 / 5.90 s | 5.31 / 5.91 s | 5.31 / 5.90 s |
| engage distance at our first request, median (histogram) | 1 (1: 54, 2: 2, 5: 1, 8: 1) | 1 (1: 196 of 212) | 1 (1: 100 of 106) |
| who started it: it swung first / our request / our walk | 47 / 6 / 5 | 201 / 6 / 5 | 102 / 2 / 2 |
| react (it swung first -> our request), median / p75 | **1.26 / 5.62 s** | **12.7 / 14.2 s** (60-s bound: 14.9 / 24.5) | 10.9 / 14.0 s |
| hits taken per kill (damage > 0) | **0.31** | **2.10** | 2.45 |
| damage taken per kill | **33.8 HP** | **239.4 HP** | 278.9 HP |
| attack attempts on us per kill (misses too) | 7.0 | 29.2 | 34.2 |
| their hit rate on us | 4.4 % | 7.2 % | |
| hits before our first hit, per kill | 0.29 | 1.43 | 1.64 |
| a second monster joined (acted on us, or we on it) | 50 % | 64 % | 63 % |
| engagements not ending in a kill | 0 of 58 | 19 of 232 | 12 of 119 |
| fall of a pile -> our first pickup request, median | 1.32 s | 2.1-4.3 s (median per run) | |

**Reading.**
- Batt and the bot fight the same way: melee, at range 1, mostly against a monster that came to
  them, at the same time to kill.
- Batt answers in about a second.
- The bot's DEFEND-SCAN hovers ring 1, then ring 2, before its first click, and is hit
  meanwhile.
- Monsters attack it 4 times as often per kill, and land a hit more often (7.2 % against 4.4 %),
  because they come in pairs more often.

## 5. RANKED LOSSES (bot pooled against Batt)

Seconds per kill are **measured** and additive: the "lost" column sums to the whole gap of
66.1 s per kill. "+kills / h alone" is an **estimate**: the bot's rate if only that cause matched
Batt's, everything else held at the bot's own seconds per kill. "cumulative" applies the fixes in
rank order and ends at Batt's 232.7.

| # | cause | bot s / kill | Batt s / kill | **lost s / kill** | share of the gap | +kills / h alone | kills / h cumulative |
|---|---|---|---|---|---|---|---|
| 1 | **rest** (sitting + walking to sit) | 33.90 | 0.84 | **33.06** | 50.0 % | +30.1 | 74.2 |
| 2 | **idle inside search** (stop-and-go walking) | 15.31 | 0.46 | **14.85** | 22.5 % | +9.8 | 107.0 |
| 3 | **approach: react** (it swings first; the defend scan) | 6.37 | 0.85 | **5.52** | 8.4 % | +3.2 | 128.0 |
| 4 | **idle: loot pause** (after a fight before / beside a loot) | 5.95 | 1.24 | **4.71** | 7.1 % | +2.7 | 153.7 |
| 5 | **idle around rest** (before / after the sit) | 4.62 | 0.00 | **4.62** | 7.0 % | +2.7 | 191.5 |
| 6 | idle after fight (no loot follows) | 2.64 | 0.19 | 2.45 | 3.7 % | +1.4 | 220.2 |
| 7 | search walking | 6.16 | 5.35 | 0.81 | 1.2 % | +0.4 | 231.7 |
| 8 | idle before engage (waiting for the monster) | 0.98 | 0.80 | 0.18 | 0.3 % | +0.1 | 234.4 |
| 9 | idle other | 0.07 | 0.00 | 0.07 | 0.1 % | 0.0 | 235.4 |
| 10 | fight | 5.36 | 5.37 | -0.01 | 0 % | 0.0 | 235.3 |
| 11 | loot (walk to the item + pickups) | 0.11 | 0.15 | -0.04 | 0 % | 0.0 | 234.7 |
| 12 | approach: close (request -> first hit) | 0.09 | 0.22 | -0.13 | 0 % | -0.1 | 232.7 |
| | **total** | **81.6** | **15.5** | **66.1** | | | |

- **Arm N alone** (the arm Batt chose) ranks the same causes in nearly the same order:

  | # | cause | lost s / kill |
  |---|---|---|
  | 1 | rest | 33.7 |
  | 2 | inside search | 13.4 |
  | 3 | around rest | 6.7 |
  | 4 | react | 4.7 |
  | 5 | loot pause | 4.7 |
  | 6 | after fight | 2.5 |
  | 7 | search walking | 0.7 |

- **Against Batt's field-only window** (no in_orcs01 rest), the order is unchanged and rest's loss
  is 33.9 s per kill.
- **The 6 labels on their own:**

  | label | lost s / kill | share of the gap |
  |---|---|---|
  | rest | 33.06 | 50 % |
  | idle | 26.87 | 41 % |
  | approach | 5.40 | 8 % |
  | search | 0.81 | 1 % |
  | fight | about 0 | |
  | loot | about 0 | |

**What the bot does in each lost second.** This comes from its own events, each overlapped with
the label.

1. **Rest, 33.1 s per kill.**
   - It is driven by damage. The bot nets 213 HP per kill; Batt nets 22.5 HP. Net means the damage
     minus the regen while not sitting.
   - Sitting regains 3.7 HP / s, the same for both (measured: +11 every 3 s).
   - So holding HP steady needs 58 s of sitting per kill, and the bot sits 34 s. Its 36 potions
     (15,084 HP) and 29 Fly Wings cover the difference.
   - **Where the damage comes from**, bot pooled. Attack attempts on us (misses too) / hits / HP:

     | cause | attempts | hits | HP |
     |---|---|---|---|
     | idle around rest | 1,924 | 151 | 17,244 |
     | react (scanning) | 1,563 | 124 | 13,982 |
     | fight | 1,490 | 119 | 13,428 |
     | rest itself | 545 | 32 | 3,718 |
     | inside search | 406 | 15 | 1,784 |
     | before engage | 161 | 2 | 234 |

     Batt's 406 attempts all fell in his fights (331) and approaches (75: react 67, close 8);
     none fell while he walked, looted, idled or sat.
   - **Unanswered attackers.** 30 monsters attacked the bot and were never hit back in the window:
     1,767 attempts, 138 hits, 15,910 HP, 1,174 s.
     - a8 (321 s) and a9 (501 s) hold the long cases. In a8, one Orc Warrior attacked for 321 s
       while the defend scan ran 67 times and found it on no ring cell. Its verdicts were "clear"
       and "unknown"; the monster's packet cell was 6 cells from ours.
     - Those are also the runs with 10 Fly Wings and 10 potions each.
   - So the bot's REST is mostly **self-inflicted exposure**: it sits in the field ("no rest spot:
     sit where we stand"), it is attacked while sitting or standing up, and it scans slowly.
   - Batt went to sit in **in_orcs01** ("safer", he said): no monster acted on him there.
2. **Inside search, 14.9 s per kill.**
   - Of these 3,246 s, the runner's logged scans and hovers cover only 199 s. The rest is the walk
     loop itself: a hover before each walk click, the 1.2-s floor, a 7-cell walk.
   - Its walk events (all 8 runs): 3,807 decisions, 1,367 clicked (36 %), 2,437 refused because
     the cursor read "unknown", 3 refused as "no entry". Clicked walks are 3.9 s apart (median; per
     run 3.78-4.00).
   - Batt sends 28.1 walk requests a minute and his walk never stops: 119.8 cells per minute of
     the window against the bot's 30.1.
3. **React, 5.5 s per kill** (8.8 s per kill with the 60-s bound).
   - The defend scan: its "scan" spans cover 270 s of the 1,351 s; the rest is the battle-log /
     HP-drop trigger, the strike clicks (101 s) and Steal casts (84 s).
   - It feeds cause 1: 1.43 hits land before our first hit, per kill.
4. **Loot pause, 4.7 s per kill.**
   - The loot hover. The runner's loot_step spans cover 1,001 s of these 1,261 s, plus 434 s of
     the idle after fights.
   - Batt clicks the drop 1.3 s after it falls (median). The bot's first pickup comes 2.1-4.3 s
     after it.
5. **Around rest, 4.6 s per kill.**
   - These are mostly defend scans (865 of 980 s) right after standing up, when a monster is
     already on the bot. It belongs with cause 1.

## 6. HP: why Batt's bar is a burst, and what sustaining it costs (ESTIMATES)

| | Batt (window) | bot pooled |
|---|---|---|
| HP at the start / lowest / at the field's end | 1,710 / **476 (22 % of 2,146)** / 846 | |
| damage taken (sum of HP falls) | 1,963 | 53,871 |
| potions (HP they gave) | 1 (450) | 36 (15,084) |
| natural regen while sitting / not sitting (HP / s) | 3.80 / 0.77 | 3.69 / 0.85 |
| net HP lost per kill (damage - regen not sitting) | 22.5 | 213.4 |
| sitting needed per kill to hold HP (no potions) | **6.1 s** | 57.9 s |
| kills / h with that sitting instead of the window's own rest | **173.7** | 34.1 |
| White Potions / h to hold HP at the window's own kill rate (450 HP each) | **11.6** | 20.9 |

- His demo started at 80 % HP and ended its field part at 39 %, after one potion.
- At his pace, a 40-min run must either sit about 6 s per kill (about 174 kills / h) or drink about
  12 White Potions an hour to hold 232.7.
- The bar is reachable only with his **damage profile**: 34 HP per kill, about 0.3 hits.

## 7. The route (Batt's loop)

- **File:** `config/routes/gef_fild10-batt-loop.json` holds waypoints only, plus the map, the kind
  and a one-line source.
  - It is **not** a reviewed routes file. Those are `config/routes/<map>.yaml` (README there),
    with `reviewed_by` and a proof by `map_routes.py prove`.
  - No runner reads this JSON. Turning it into `gef_fild10.yaml` needs Batt's review, or his
    recorded delegation.
- **How it was made:** `time_budget.py route` takes his SEARCH walking cells (detours to monsters
  and items left out), on gef_fild10 only, in time order, then:
  - cuts the FIRST LAP, until he came back within 10 cells of the start;
  - simplifies it with Ramer-Douglas-Peucker (eps 3 cells);
  - spaces the waypoints 8-15 cells of path apart;
  - drops spikes (a turn sharper than 120 degrees; 6 dropped);
  - moves 2 waypoints off the client GAT's walkable grid onto walked cells next to them:
    183,306 -> 181,308 and 232,87 -> 233,86.

| measure | value |
|---|---|
| waypoints | 82, a loop, **clockwise** (x east, y north), starting at 76,337 by the Kafra |
| length | 833 cells (Chebyshev, waypoint to waypoint); legs 2-18, median 10 |
| lap 1 | 8.95 min (536.9 s) on the clock, 167.5 s of it walking, **41 kills**; 914 cells walked |
| lap 2 | closed 295.7 s (4.9 min) after lap 1 (836 cells); about 17 kills: fewer monsters had come back |
| his lap-1 cells to the loop | median 0, p90 2, all within 10 |
| his lap-2 cells to the loop | median 2, p90 6, 99 % within 10 |
| his kills to the loop (our cell at the kill) | median 1, p75 2.75, p90 7; 83 % within 5, 100 % within 10 |
| the bot's kills to the loop | median 22, p75 39, p90 57; **20 % within 5**, 34 % within 10 (arm N: median 16) |
| the straight legs on the client GAT | 98.6 % of their cells walkable (a runner routes each leg with A*) |

- *Correction of "one loop"* (Amendment L): his ~1,800-1,900 cells in 14.1 min were the same
  loop walked **twice**.

## 8. The judge fix (Snatcher in a human demo)

- `dungeon_judge.py` filed Batt's Snatcher gains as "other", because its rule keyed on the runner's
  run_start "char".
- **Now:** with no runner events and the manifest's character "rogue", a gain with no pickup
  request and no Steal SP fall is "snatched" when it comes <= SNATCH_S (1 s) after one of OUR acts
  with damage > 0 (`own_hits`).
- Runner sessions keep the runner's rule. Tests cover a synthetic case (rogue, crusader, no
  character, a runner session) and the real demo.

| Batt's demo (--live 898) | picked | snatched | other | value / h at Overcharge |
|---|---|---|---|---|
| before | 44 | 0 | 38 | 52,780 z |
| **after** | **44** | **38** | **0** | **102,084 z** |

- The 38 gains match Amendment L's "Snatcher procs 38".
- Items / h (329) does not change: it counted every gain.
- **The value bar does change, from 52,780 to 102,084 z / h at Overcharge.** The bot's 14,111 z / h
  already counted its own snatches.

**A second gap, found, NOT fixed** (the brief allowed one):
- For a human demo the judge takes MaxHP from run_start's char, which is absent, so it falls back
  to 5,260 (the Crusader's).
- Amendment L's "HP low 9 % once" is therefore 476 / 5,260. The real figure is
  **476 / 2,146 = 22 %**.
- The fix is one line in `judge()`: use `rs.get("char") or man.get("character")` for CHAR_MAX_HP
  and CHAR_MAX_SP.

## 9. Limits

- **Batt is one 15-minute sample.** His lap 2 found fewer monsters than lap 1 (17 against 41
  kills), so a longer run along the same loop would see a lower rate.
- **The "+kills / h" columns are estimates.** They assume the causes are independent, and they are
  not: rest follows from damage, and damage follows from the react time, the field rests and the
  unanswered attackers.
- **The labels come from packets.**
  - The bot's hovers write no packet, so its "thinking" falls in idle. Section 5 splits that idle
    by its own events.
  - The approach bound (15 s) censors the bot's slowest reactions (section 2).
- **Monster positions come from the move packets.** In a8's unanswered case the attacker's cell is
  6 cells from ours, which a melee attack cannot be: one of the two cells is stale. The count of
  unanswered attacks does not depend on positions.
- **A pile is "one kill's drops"** by time and space (1 s, 3 cells). Two kills side by side within
  a second make one pile, which matters only for the loot label (about 0 s here).

## 10. What it suggests for dungeon@9 (for the parent and Batt; NOT decided here)

1. **Cut the damage per kill. It is the root of 57 % of the gap: rest plus around-rest.**
   - Rest off the field, as Batt did (in_orcs01), or only where no monster walks.
     ➡️ **Designed and built since (2026-10-26, offline, PROPOSED):**
     [gef10-house-rest.md](gef10-house-rest.md), `dungeon_hunt --rest house` (OFF by default).
     Only 3 of the 5 houses are sealed rooms; Batt's door gef022 is refused, because its room
     holds the orcsdun01 warp. Its estimate is +3 to +5 kills / h, because most of the sitting
     pays for fight damage.
   - Answer an attacker within about 1 s.
   - Never stay in a defend loop that does not find the attacker. Bound it, then step away or
     strike at its packet-free pixel position.
2. **Walk continuously along his loop.**
   - Use longer legs, from his waypoints.
   - Click the next step before the walk ends.
   - Do not gate each walk click on a cursor read: the loop's cells are known walkable.
   - ➡️ **Measured and built since (2026-10-26):** [gef10-cursor-unknown.md](gef10-cursor-unknown.md).
     The UNKNOWN reads are a timing failure (93 % within 2 s of a move). `dungeon_hunt --walk-trust`
     (OFF by default) clicks a trusted cell on an UNKNOWN read: 2,190 of 2,249 offline.
3. **Shorten the loot pause.** Click the drop where the kill fell, about 1 s after the death, as
   Batt does, instead of a hover sweep.
4. **Budget HP for a 40-min run.** At his damage profile, either about 12 White Potions an hour or
   about 6 s of sitting per kill. Otherwise the 232.7 bar does not hold over 40 minutes.

## 11. Reproduce

    export PYTHONPATH=scripts:packages/poring_dataset/src:packages/poring_env/src
    python3 scripts/time_budget.py compare --target 20261026T095021-demo-human-demo-gef10 \
        --live 898 <the 8 run sids> [--json] [--approach-max 60]
    python3 scripts/time_budget.py route 20261026T095021-demo-human-demo-gef10 --live 898 \
        --out config/routes/gef_fild10-batt-loop.json
    python3 scripts/dungeon_judge.py items 20261026T095021-demo-human-demo-gef10 --live 898 \
        --map gef_fild10
