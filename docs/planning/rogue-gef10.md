---
doc_type: design
hypothesis: "On gef_fild10 (the lab's pre-renewal server), a Rogue built to Batt's sample at the SAME EFFECT (Base 62 / Job 50: 100 % hit on, and 5 % hit from, every normal species of the map) gains at least as much NPC-sell value per hour (at Overcharge +24 %) WITHOUT a Steal opening (Snatcher Lv 10 steals on its own) as WITH dungeon@7's Steal-first opening, because the opening's casts, SP and rests cost kill time that its extra steals do not repay."
status: "VERDICT 2026-10-26 03:51 (Amendment H): as registered, NO DIFFERENCE (N 13,754 vs S 14,381 z / h at OC), so N is kept; the sensitivity view without a6 says S wins (18,055 vs 13,754). Bag full 03:49, stored 1,069 -> 480. A second block (a9-a11, reported only) runs after it. History: PRE-REGISTERED 2026-10-25 (Batt's decisions 12:3x-13:1x ICT, section 0)."
role: null
verdict_date: 2026-10-26
verdict_ticket: null
supersedes: null
related: [thief-payon.md, payf07-detector.md, payf07-prep.md, renewal-feasibility.md, ../demonstrations.md, ../../config/map_zones/README.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py]
next_action: "PAUSED by Batt 2026-10-29 (before 19:53 ICT): fit-first and candy-closet use the GPU heavily for 2-3 days; no poring-lab step until Batt says to resume (RAM cleanup approved 2026-11-02; docs/operations/disk-audit.md, the pause). ➡️ Since the rest of this field was written (2026-10-26): Amendments AK-4 / AK-5 (the staged item sessions e3, e3x, e3b; all SHIPPED 2026-10-30 03:05-03:35) and gef10 round 2 (scored 2026-10-29 17:04, does not pass: gef10-eval.md RESULT R2). Written 2026-10-26: Batt: pick the arm (the registered verdict keeps N; the sensitivity view favours S), and decide the next step (a Kafra trip needs his OK for the NPC contact; a second Orc Lord flee proof; a gef10 detector round 2). The parent: report the second block (a9-a11) when it ends."
title: "The Rogue on gef_fild10: Batt's build at the same effect, no Steal vs Steal first, loot kept for the Overcharge merchant (pre-registered)"
date: 2026-10-25
owner: Batt
---

# The Rogue on gef_fild10 (pre-registered)

**This replaces the pay_fild07 phase** ([thief-payon.md](thief-payon.md)): Batt moved the target
to gef_fild10 on 2026-10-25. Every number below is read from the pinned rAthena tree
(`e985006`, pre-renewal: the read-only mirror `/dev/shm/poring-lab-rathena-src` and single files
fetched into `/dev/shm`) or from the lab DB. No rAthena table is copied here (GPL data rule).

## 0. Batt's decisions (2026-10-25; translated from Thai)

1. **~12:3x, one message with three images** (his status window, his skill calculator, his
   merchant's sell window):
   - "New plan: train on Geffen Field (gef_fild10) instead", with the monsters "Orc Warrior,
     Poporing, Orc Lady, Orc Baby, Yoyo", "because the map is more open, little blocks the view".
   - "Change the job to Rogue, with the status and skills as in these images."
   - "Try first without Steal, and try Steal before attacking, because the Rogue has Snatcher
     Lv 10."
   - "This map has a Kafra, so items can be stored for the OC merchant: junk sells higher." His
     window: Orcish Voucher 53 -> 65 z, Cyfar 289 -> 358 z (Overcharge, +24 %).
   - The four open pay_fild07 decisions (weight, the held staged set, ENGAGED labels, loot by
     sight): "change the target to gef_fild10".
   - The /dev/shm glob lines: "please do them, I assign it to you" (done, section 1).
   - "You may use the GPU to train on the monsters and items of this map."
2. **~12:4x, a fourth image (the status totals):** "the totals must be as in this image; you may
   raise status more, but the totals must be these": Atk 35 + 183, Def 45 + 176, Matk 23 + 70,
   Mdef 25 + 5, Hit 279, Flee 291 + 1, Critical 1, Aspd 174, Status Point 0.
3. **~12:5x (asked: the totals cannot exist on pre-renewal, section 3a):** "Pre-re, same effect".
   His choice over "switch the lab to Renewal" and over "pre-re, your stats exactly".
4. **~13:1x (asked):**
   - "Delegate gef_fild10 zones": the agent authors `config/map_zones/gef_fild10.yaml` with
     `reviewed_by: "agent (delegated by batt, 2026-10-25)"` (README rule).
   - "Add @storage to group 20": the setup stores loot between runs with @storage (no NPC, no
     fee). In-run Kafra trips come later, as their own pre-registered step.

## 1. Done at once (before this commit)

- **The pay_fild07 detector training is STOPPED** (Batt: "instead"). SIGINT to the in-worker
  `timeout ... poring_vision.train` PID at 12:40:19 ICT; train-day.sh logged "TRAIN STOPPED: not a
  guard trip" at 12:40:25; the guard verified the worker "up and idle (no CUDA context), nothing
  of ours on the GPU". Epoch 1 had completed (val mAP50 0.800, mAP50-95 0.568);
  [payf07-detector.md](payf07-detector.md) 13g has the record.
- **The /dev/shm glob lines (delegated):** 25 `pytest-*` basetemps, 109 `shots/*` and 17
  `poring-guarded-*.log` were removed BY EXPLICIT PATH (the hook refuses a glob rm; the paths were
  listed first and `fuser` showed none open). `/dev/shm/poring-lab-tmp` 493 M -> 161 M.

## 2. The map on OUR server (pre-renewal)

### 2a. Spawns (`npc/pre-re/mobs/fields/geffen.txt`)

| species (id) | spawns | Lv | HP | its HIT / FLEE (Lv + DEX / Lv + AGI) | AI |
|---|---|---|---|---|---|
| Orc Lady (1273) | 70 | 31 | 2,000 | 100 / 73 | 21 (aggressive) |
| Orc Warrior (1023) | 20 | 24 | 1,400 | 58 / 48 | 4 (aggressive) |
| Poporing (1031) | 15 | 14 | 344 | 33 / 28 | 2 (passive, looter) |
| Orc Baby (1686) | 5 | 21 | 912 | 56 / 36 | 4 (aggressive) |
| Orc Lord (1190), MVP | 1 (2 h +- 10 min) | 74 | 783,000 | 184 / 156 | 21 |
| Blue Plant (1079) / Green Plant (1080) | 3 + 3 / 3, fixed areas | | | | plant |

- **No Yoyo** on this map in either mode. Renewal's gef_fild10 (for reference) is Orc Warrior
  179, Orc Lady 55, Orc Baby 27 and Orc Lord, with no Poporing either.
- **Most of the map is aggressive** (95 of 110 normal monsters): unlike pay_fild07, they come to
  us. dungeon_hunt's DEFEND-SCAN (a hit on us -> scan the ring around the character) was built for
  that (orcsdun01).
- **The Orc Lord** kills a Base 62 Rogue in one or two hits (ATK 3,700-4,150; its hit on us
  80 + 184 - 181 = 83 %). It is never a target. The bot has no way to tell it apart from the
  pixels yet, so meeting it most likely ends a run in a DEATH, which is a RESULT (the run stops,
  the cause is recorded, the dialog closes by its known step, then @alive + @heal).

> ➡️ **2026-10-25, the map prep ([gef10-prep.md](gef10-prep.md) 1a, 1c) adds:**
> - the Orc Lord walks with **5 Orc Archers**, its slaves (range 9, 73 % to hit this Rogue);
> - it comes back **120-130 min** after a death, not 2 h +- 10;
> - it stays on the map while alive: `dynamic_mobs` never removes an MVP.
> - It walks 100 ms per cell (75 under its Increase AGI) against the Rogue's 150. While it
>   chases it casts Lv 10 bolts from 9 cells: 1,700-2,660 before MDEF, about the Rogue's
>   ~2,030 HP.
> - **On foot it cannot be outrun.** Only a Fly Wing at first sight breaks contact. Silence
>   does not block the Fly Wing; Stun (its Shield Charge) does.

### 2b. Warps and NPCs (what the zones and the hard bars must keep us off)

- **9 warps** (`npc/pre-re/warps/fields/geffen_fild.txt`):
  - 4 map exits: gef_fild09 (251,371), gef_fild11 (104,21), gef_fild03 (370,56), gef_fild14
    (27,219);
  - 5 doors into the Orc village houses, in_orcs01: (136,331), (138,284), (215,51), (223,205),
    (63,337).
  - The Orc Dungeon is entered from inside in_orcs01, not from the field.
- **5 script NPCs load on the pre-renewal server:**
  - the Kafra Employee (73,340; `npc/kafras/kafras.txt`; storage fee 130 z);
  - Bulletin Board#3 (69,340; `npc/pre-re/other/bulletin_boards.txt`);
  - Bulletin Board#15 (109,23; `npc/other/bulletin_boards.txt`);
  - the Orc's Memory instance pair at (242,202) and (238,202) (`npc/instances/OrcsMemory.txt`),
    near the house door at (223,205).
- The custom warper / porter lines that name this map are commented out in `scripts_custom.conf`.

### 2c. What a kill is worth (NPC sell price x 1.24, base rates; every item_rate_* is 100 %)

| species | value per kill | weight per kill | the bulk of it |
|---|---|---|---|
| Orc Lady | ~232 z | 0.63 | Cyfar (46.56 %, sell 386 -> 478 z) |
| Orc Warrior | ~88 z | 2.11 | Orcish Voucher (90 %, 71 -> 88 z) |
| Orc Baby | ~79 z | 1.64 | Large Jellopy (10 %, 420 -> 520 z) |
| Poporing | ~31 z | 0.97 | Sticky Mucus (55 %, 35 -> 43 z) |

- Weighted by the spawns: ~171 z and ~1.0 weight per kill. At 4.04's 35.7 kills / h that is
  ~36 weight / h, so a bag stored down to its fixed part lasts many hours before the 40 % stop.
- ➡️ 2026-10-25 ([gef10-prep.md](gef10-prep.md) 8): the values above INCLUDE the rares.
  - The econ model's V (rares out, Batt's rule) at Overcharge: Orc Lady 224.42, Orc Warrior
    84.97, Orc Baby 78.71, Poporing 30.23.
  - The mix without plants: 165.96 z and 0.94 weight per kill (`econ_model.py species
    gef_fild10`).
- Batt's window prices (Voucher 53, Cyfar 289) are RENEWAL's item_db; ours are pre-renewal's
  (71, 386). The judge uses ours.
- Steal and Snatcher take from the same drop table.

## 3. The build: Batt's sample at the same effect

### 3a. Why the totals cannot be copied

- Batt's window is the RENEWAL formula at Base 55: Hit 175 + 55 + DEX 49 = 279, Matk 23,
  soft Def 45 (VIT/2 + AGI/5 + Base/2).
- Pre-renewal shows Hit = Base + DEX and Flee = Base + AGI (+ Increase Dodge), with stats capped
  at 99 (`max_parameter`): even Base 99 with DEX 99 shows Hit ~205. Def 176 would need VIT 176.
- The fight depends on the CHANCE, and that is the same in both modes for this build. Pre-re:
  80 + HIT - FLEE. Renewal: HIT - FLEE. Both are clamped 5..100.

### 3b. The build (Batt's choice: "pre-re, same effect")

| | Batt's sample (renewal) | ours (pre-re) |
|---|---|---|
| Base / Job | 55 / Rogue 50 (his calculator: 49 points) | **62** / Rogue **50** |
| STR AGI VIT INT DEX LUK | 1 71 1 1 40 1 | 1 **82** 1 1 40 1 |
| status points left | 0 | 0 (Base 62 = 585 points; AGI 82 = 450, DEX 40 = 135) |
| window HIT / FLEE | 279 / 291 + 1 | ~109 / ~181 + 1 (+ gear; read off the window after) |
| Thief skills | Double Attack 10, Increase Dodge 10, Steal 10, Envenom 3 (33) | the same |
| Rogue skills | Sword Mastery 10, Snatcher 10 (20; 29 unspent) | the same |
| quest skills | Sprinkle Sand, Back Sliding, Pick Stone, Throw Stone, Close Confine: 1 each | the same (@questskill) |

The chances on gef_fild10 (one attacker):

| species | we hit it: sample / ours | it hits us: sample / ours |
|---|---|---|
| Orc Lady | 100 % / 100 % | 5 % / 5 % (80 + 100 - 181 = -1) |
| Orc Warrior | 100 / 100 | 5 / 5 |
| Orc Baby | 100 / 100 | 5 / 5 |
| Poporing | 100 / 100 | 5 / 5 |

- With Batt's base stats exactly (Base 55, AGI 71), Orc Lady would hit us 21 % on pre-re. Base 60
  / AGI 78 is the smallest build at 5 %; Base 62 / AGI 82 keeps 6 points of margin and spends
  every status point, as his window does.
- **Known difference, mobbing:** both modes cut FLEE by 10 % per attacker beyond 2
  (`agi_penalty_*`). With 3 attackers Orc Lady hits the sample 5 % and us ~18 %; with 4, 19 % and
  ~35 %. Reported per run (hits taken from the packets), not built around.
- Equipment unchanged (the +8 Damascus and the rest). Max weight stays 2,430 (24,000 base + STR
  x 300, rAthena units).

### 3c. The order of the GM steps (and why)

- The server keeps `player_skillup_limit` = 1: second-class skills open only after (the Thief's
  Job Level at the change - 1) Thief points are spent (`pc_calc_skilltree_normalize_job_sub`).
  `pc_jobchange` stores that level. Batt's tree spends 33 Thief points, so the change is made at
  **Thief Job 34**. (The job change NPC's Job 40 rule does not bind a GM change; job bonuses
  follow the CURRENT job only.)
- Steps, each read back from the DB (char row + skill table) before the next:
  1. `@resetskill`; `@joblevelup -6` (Thief Job 40 -> 34, 33 points);
  2. `@jobchange 17` (Rogue); `@joblevelup 49` (Rogue Job 50); `@baselevelup 12` (Base 62);
  3. `@resetstat`; the status window's '+' to AGI 82 and DEX 40;
  4. learn_skill@1 on the Thief tab (Double Attack, Increase Dodge, Steal 10; Envenom 3), then on
     the Rogue tab (Sword Mastery 10, Snatcher 10);
  5. `@questskill` for the five quest skills;
  6. the hotbar: F1 White Potion, F2 Fly Wing, F3 Steal, checked on a screenshot;
  7. a judged screenshot of the status and skill windows, beside Batt's images.
- Every GM line goes through crusader.gm_line's identity check and the UI gate.
- If `@joblevelup -6` does not leave 33 points, the steps stop and are re-planned (no
  workaround).

## 4. Storage between runs (@storage, Batt decision 4)

- `storage: true` is added to group 20 in `services/rathena/conf/import/groups.yml` (logged, as
  `refine` was), applied by a guarded recreate of rathena.
- **The store step** (new, in the setup; pre-registered here, built and proven before any run):
  - it opens storage with `@storage`;
  - it drags every inventory stack that is NOT equipped and NOT stock (White Potion, Fly Wing)
    into the storage window, entering the whole amount in the quantity box;
  - it closes the storage window by its own control;
  - it confirms the bag from the DB (inventory weight) and a screenshot.
  - It runs only outside a run, on the setup's open-field stand where the loot clear already
    runs (dungeon_hunt `CLEAR_STAND`, prt_fild08 268,107: no aggressive monster), never on
    gef_fild10, whose monsters are aggressive. It replaces the Etc-tab drop (`clear_etc`) for the
    Rogue, at the same 40 % trigger.
- Its first live use is its positive case: today's bag (1,034 weight, 42.6 %) -> its fixed part
  (equipped 320 + stock 185 = ~505, ~21 %). The four pay_fild07 target items the Thief holds
  (s7's returned staged set) go to storage with the rest. That answers pending decision 2: kept,
  stored.
- The click census and the targeted safety tests run on the new clicking code before its use.
- **Not in scope:** the Kafra NPC (a deliberate NPC contact, 130 z a visit) during a run. That is
  a later step and needs Batt's OK for the contact.

## 5. The two arms and the runs

- **N (no Steal):** dungeon_hunt without `--steal`. The Rogue attacks at once; Snatcher Lv 10
  steals on its own.
- **S (Steal first):** `--steal`, dungeon@7's rule (4.04): one Steal Lv 10 on every monster
  first, SP permitting, then a plain fight.
- **Both arms:**
  - `--char rogue`: the Thief's keys and stock, the Rogue's identity check and its max HP read
    from the DB at setup;
  - `--map gef_fild10`: the delegated zones and the prep's stands and rest spots;
  - 4.04's sustain (potions, rests, the Fly Wing escape);
  - DEFEND-SCAN plus the heading walk, the loot hover;
  - immunity OFF during the run;
  - the store step between runs.
- **Order:** 8 runs of 40 min, alternating by run as N S S N N S S N, each on a fresh seed, with a
  judged screenshot and the ok-<label> gate before each.
  - A 15-min pilot in arm N comes first (unscored), to see the runner on the map.
- **Measures** (`dungeon_judge.py`, from the packets, offline):
  - value per hour at Overcharge (pre-re NPC sell x 1.24);
  - items per hour by item, split picked / stolen / snatched / staged;
  - kills per hour and kills per species;
  - deaths with their cause; HP potions, Fly Wings, rests;
  - SP spent on Steal; Steal tries / successes; Snatcher procs;
  - hits taken per species, and with 3+ attackers;
  - weight gained per hour; monsters seen per 10 min;
  - the hard bars.
  - "Snatched" (a steal event with no Steal cast by us just before) is NEW in the judge. It is
    built with a test on a real case from the first runs before it is quoted.
- **The decision rule:** pool each arm's 4 runs and compare value per hour.
  - If |N - S| is larger than half of the larger within-arm range, the higher arm wins.
  - Otherwise there is no difference, and N is kept (no SP, simpler).
  - The prediction (the hypothesis): N >= S.
- **Hard bars (stop the run):** a map change, an NPC contact, an unknown UI state.
- **Results:** a death; the 40 % weight stop.

## 6. The detector for gef_fild10 (Batt: the GPU may train on this map's monsters and items)

- **The source:** the runs' recordings and packets (as payf07-detector.md did with 4.04's).
  - **Monsters:** Orc Lady, Orc Warrior, Poporing, Orc Baby, the plants, the Orc Lord if met.
    Labels follow the o3h rule re-measured on this map's FIT data, with its T1 / T2 tiers.
    ENGAGED units (Batt's clip) are part of that pre-registration, not an afterthought.
  - **Items:** floor items of this map's drops (Cyfar, Orcish Voucher, Sticky Mucus, Milk, Iron,
    Garlet, Large Jellopy, ...), labelled from `floor_item_appear` + the camera model (the
    target-items method).
- It gets its own pre-registration (labels, tiers, split, classes, the init weights) once two or
  more runs exist. The GPU work follows R1-R3, the warm worker and MID_CKPT as before.
- The worker stays up meanwhile (idle, no CUDA context), so the training needs no new quiet
  window.

## 7. Order of work (2026-10-25)

1. This pre-registration: commit + push.
2. The map prep, offline, by a subagent in a tmpfs worktree (payf07-prep.md's list for gef_fild10):
   - the KB with the Geffen field sources;
   - the client GAT and the client / server walkability;
   - the script-NPC cells;
   - the zones (delegated);
   - start stands that pass the three checks, and rest spots;
   - the runner's map inputs and the lint allowlist;
   - the econ model's gef_fild10 entry at Overcharge.
3. The parent, live:
   - @storage in group 20 (a guarded recreate:rathena, then a relog);
   - the Rogue build (3c);
   - the store step, built, census-tested, then its first live use (4).
4. Merge the prep; the census plus the targeted safety tests; the pilot; the runs (5).
5. The detector pre-registration once the recordings exist (6).

## Amendment A (2026-10-25 19:45 ICT from `date`; BEFORE any run on gef_fild10)

**Batt's answers to the 18:49 report (translated from Thai):**
1. "Run on; do whatever can run in parallel at the same time."
2. The Orc Lord: "run away; you may try spawning it first."
3. The Kafra: "first get the hunting to fill the bag."
4. The shell-permission outage: "fix it if you can" (section A5).

**A1. Done live (19:06-19:40 ICT):**
- `@storage` is live: a guarded `recreate:rathena@120` 19:06:39-19:08:52 (worst capture stall
  7.2 %), then `recreate:sniffer@30` 19:09:04-19:09:39 (the sniffer shares rathena's network).
  - `verify_mount.py rathena`: groups.yml ok.
  - The auto GM recover reported rc 3 ("the character never came online"): the client entered its
    last-used slot, the Thief, not the Novice GM. The interlock was green and the Thief online, so
    nothing was retried.
- **The Rogue build (3c), each step read back on a frame:**
  - @resetskill; @joblevelup -6 (Job 34; the pinned atcommand.cpp lowers the points with it: 33);
    @job 17;
  - `cut-job rogue` on the judged frame; @joblevelup 49; @baselevelup 12; @resetstat (585 points);
  - AGI +81, DEX +39 by the status window;
  - skills one at a time. The skill window reopens on the ROGUE tab, so each Thief skill had the
    Thief tab clicked and checked on a frame first;
  - Snatcher sits at (2,0) of the Rogue tab, not (1,0) (that is Tunnel Drive): only the three
    learnable icons were lit, matching the pinned tree;
  - @questskill 149 / 150 / 151 / 152 / 1005; F3 = Steal (dragged from the Thief tab).
- **The final status window:** Base 62 / Job 50, STR 1 AGI 82 (+8) VIT 1 INT 1 DEX 40 (+7) LUK 1,
  Status Point 0, HIT 109, **FLEE 192 + 1**, Aspd 170, HP 2146, SP 336, skill points 29 left.
  - FLEE is 10 above 3b's estimate: Increase Dodge gives the 2nd class +4 per level.
  - So Orc Lady hits us 5 % alone and ~7 % with 3 attackers (3b said ~18 %).
- **The store step:** `gm_state.store_loot` (842e1d0, census 2 -> 3, tests). Its first live use
  19:38-19:40 stored 20 stacks and kept White Potion x9 / Fly Wing x10. Weight 1,034 -> 505 /
  2,430 (20.8 %), as section 4 predicted.

**A2. Storage is ONCE, not between runs (Batt 3).** The runs follow each other with the loot kept in
the bag. The setup stops at 40 % (972): that is "the bag is full", the milestone before any Kafra
trip. Section 5's "the store step between runs" is withdrawn.

**A3. The runner is dungeon@8:**
- `--char rogue`: the same character's data, job "rogue", HP 2146 / SP 336;
- the Steal cast is read as a fall of half Steal's SP share, rounded up (Rogue: 2 points; the
  Thief's 5 unchanged).

**A4. The Orc Lord (Batt 2: flee; practise on spawned ones first):**
- **Practice first, off the scored runs:**
  - an immune watch on gef_fild10 (the elder-willow watch's way): at each lattice cell `@monster
    1190 1`, a dwell, then `@killmonster2`, recorded with its packets;
  - then a recognizer, built offline on those frames and scored against the packet positions;
  - then a FLEE rule (a Fly Wing at once, since the Orc Lord's walk speed decides whether a run on
    foot can work), proven live on a spawned Orc Lord with immunity OFF before any scored run
    uses it.
- **Until that rule is proven,** each scored run's setup types `@killmonster2` on gef_fild10 before
  the start. Every monster there dies without drops and respawns, and the natural Orc Lord comes
  back only after 2 h (+- 10 min), longer than a 40-min run. Both arms get the same fresh map.
- That keeps an MVP death out of the Steal comparison. It is an experimenter's setup step, never a
  decision of the bot.

**A5. The outage (Batt 4).** The docs (claude-code-guide, 19:0x) say:
- the auto mode classifier is server-side;
- allow rules and PreToolUse "allow" do not bypass it;
- there is no fallback setting.
So nothing on our side can repair it. What limits the damage:
- long work runs as DETACHED background chains, which keep going while the agent's turn is stopped;
- after 2-3 failed checks the agent switches to non-shell work and spaces its retries, not 10 in a
  row;
- Batt can switch the session to manual approval with Shift+Tab during an outage.

## Amendment B (2026-10-25 20:43 ICT from `date`; during s1, before s1's result is read)

**B1. The two pilots (unscored):**
- **Arm N pilot** `20261025T200925-...-B-pilot`: 15.0 min, 16 kills, deaths 0, hard bars pass.
  - 7 items came in with no pickup and no Steal, each 0.289-0.306 s after our own hit and from the
    hit species' drop table. That is Snatcher: judge column "snatched" (2319ce7).
  - Value 5,951 z at Overcharge (all causes; `items_value`, ccbeec9).
- **Arm S pilot2** `20261025T203118-...-B-pilot2` (its first start, 20:28, stopped safely: the line
  after the setup's @warp read the LOADING screen and was refused; fixed 9c04fcf):
  - 10.0 min, 13 kills, deaths 0, hard bars pass;
  - Steal casts read by the runner 6 = packet SP falls of 10: 6. Stolen 1, snatched 5.
- Both arms work on gef_fild10, so the 8 scored runs started at 20:43 (s1).

**B2. Past s8: "until the bag is full" (Batt 3).**
- The 8 runs add only ~210 weight at the pilots' rate (540 -> ~750 of 2,430, ~31 %), short of the
  40 % stop.
- So the chain goes on in the same ABBA order (s9 N, s10 S, s11 S, s12 N, ...) until the setup's
  40 % stop. That stop is the milestone.
- **The N-vs-S verdict uses s1-s8 only**, as section 5 registered. s9 and later are reported as a
  second block, pooled by arm, not used for the decision.

**B3. Work beside the runs (offline, niced, single-threaded; noted for the load):**
- the Orc Lord recognizer (a subagent, from the watch `20261025T195325-rdp-ow1`);
- the gef_fild10 detector's pre-registration and FIT work (a subagent; TEST = s7, s8, never read
  before the parameters are frozen).

## Amendment C (2026-10-25 21:38 ICT from `date`; BEFORE any run of the restarted block)

**What happened in the first block attempt:**
- **s1** (arm N, 20:43-21:24): time box. 35 kills (52.5 / h), deaths 0, hard bars pass. The
  Rogue sat or rested 45 % of the time. 8,967 z at Overcharge.
- **s2** (arm S, 21:25) ended after 5.1 min: "position unread for 30 s".
  - The Rogue stood at (292,62) in the forest, where the minimap's "292 62" readout sits over
    sunlit grass.
  - The reader read every digit but refused the frame: one "stroke start" in the rect's LAST
    column, where no whole digit can begin, failed its uncovered-ink rule.
  - With no position, the heading walk had no goal and stood still. The stuck rule then pressed a
    Fly Wing (a same-map teleport, loading screen), and the 30-s rule ended the run.
  - It is a safe stop: the hard bars pass, deaths 0.
- **The fix** (2d0100c, `poring_env.selfpos`): ink beyond (rect width - glyph width + the
  templates' largest first-stroke offset, 2) is scenery.
  - On 90 real strike frames only that one reading changes, None -> (292,62).
  - The same failure stopped hunt.py once before (2026-10-15, "uncovered_ink" at 122,78).

**The restarted block:**
- The reader fix changes the runner's perception for both arms. So the block RESTARTS with it: a1
  N, a2 S, a3 S, a4 N, a5 N, a6 S, a7 S, a8 N (seeds 25521-25528, 40 min). Then a9+ in the same
  order until the 40 % stop.
- **The verdict uses a1-a8.** s1 and s2 are reported apart, as the first attempt.
- The gef_fild10 detector's TEST sessions move with it: a7 and a8, never read before its
  parameters are frozen.

## Amendment D (2026-10-25 21:51 ICT from `date`; the Orc Lord recognizer's RESULT)

**The result:** [orclord-recognizer.md](orclord-recognizer.md), a subagent, offline.
- Its bars were pre-registered at 20:21:07, before any recognizer existed. The scoring used
  held-out lattice cells 8-14 and the pilot after 300 s.
- **Recall within 1 s: FAIL**, 5 of 7 cells (bar 95 %).
  - One Orc Lord spawned with our Rogue under a tree canopy: 11 s.
  - One was hidden 2 s by the spawn's starburst.
- **False positives: FAIL**, 1.89 per 10 min of hunting (bar 1). Both came near our own effects:
  a cast flash, a magic circle.
- **Latency: PASS**, p95 54 ms.
- A finding: the client draws a bright green AURA ring at the Orc Lord's feet. Post hoc, the aura
  rule ALONE had 0 false positives in 33.2 hunting minutes with the same 5 of 7 cells. That is not
  a bar result: it gets its own pre-registration.

**So the FLEE rule does NOT go live.** `--clear-map` stays on for every scored run (A4).

**Next (before any flee):**
1. A second immune watch, pre-registered, with EDGE ENTRIES at 2-5 fps: spawn the Lord, warp
   16-20 cells away, walk back.
2. The aura-alone recipe pre-registered on it.
3. Hunting negatives from a1-a6, hours of them; a7 / a8 stay the detector's TEST.
4. Then a live flee proof on a spawned Lord with immunity OFF.

## Amendment E (2026-10-25 22:06 ICT from `date`; after a1's death, BEFORE a2)

**a1 (arm N, 21:39:52) ended in a DEATH at 23.7 min.** Its kills and items count, and the death is
recorded as a result. The cause, from the packets' last 20 s:
- 4 Orc Archer hits (253-286 damage each), then an Orc Lord hit of 3,296;
- HP 2,146 -> 665 -> 1 within 2.5 s.

That was the NATURAL Orc Lord respawning:
- the watch's first `@killmonster2` (~19:54) had killed it;
- it respawns 120-130 min after its death, so ~21:54-22:04;
- a1's own `@killmonster2` at 21:40 found it still dead and could not reset its timer.

**A4's premise was wrong.** `--clear-map` at a run's start keeps the Orc Lord away only when it is
ALIVE then.

**The schedule (from a2):**
- The Orc Lord is alive now (it killed us at 22:04, and nothing killed it after). a2's setup kills
  it at a KNOWN time D.
- Runs are then 36 min, three per cycle, released at D, D+38, D+76. Each ends before D+120, the
  earliest respawn.
- The next cycle's first run is released only after D+131. The Lord has respawned by then, and
  that run's `@killmonster2` kills it again (the new D).
- The parent holds each run's ok gate by the clock: no new bot behaviour, no mid-run GM line.
- The idle part of each cycle (~17 min) is for the Orc Lord practice (Amendment D), never a scored
  run.
- a1 keeps its 40-min registration (its result stands at 23.7 min). a2-a8 are 36 min. The verdict
  pools by hours, as section 5 says.

## Amendment F (2026-10-26 00:24 ICT from `date`; BEFORE a6)

**What happened:**
- a2 (S), a3 (S) and a4 (N) ran their 36 min. 
- **a5 (N, 00:19:45) ended after 1.5 min:** "position unread for 30 s".
  - Its seeded start (206,191) is beside the Orc village. The minimap readout "206 191" sat over
    a bright thatched roof, and the reader found no strokes (no_glyph / uncovered_ink).
  - The runner never had a position. Its idle watchdog (a Fly Wing after 45 s) comes later than
    the 30-s stop.
  - s2's case was the other side of the same gap: a Fly Wing after a read gap ended the run at
    once.

**dungeon@8.1** (from a6; the code commit follows this amendment):
- after POS_FLY_S = 20 s without a position read, a Fly Wing (at most 3 a run, 20 s apart). That
  is a same-map teleport, so the readout gets a new background;
- every Fly Wing restarts the 30-s window.
- It reuses the runner's proven escape. Nothing in the hunt's decisions changes.

**The block:**
- a5 is RE-RUN as **a5b (N, seed 25535)** in cycle 3.
- Each arm then has 2 runs before the fix and 2 after: N a1, a4 / a5b, a8; S a2, a3 / a6, a7.
- The verdict pools a1-a4, a5b, a6-a8 by hours. a5 is reported apart (1.5 min).

## Amendment G (2026-10-26 01:06 ICT from `date`; BEFORE a7)

**a6 (S, 00:24:59) ran its 36 min but sat stuck for ~20 of them.** Its counters: 192 potion
presses, 33 Fly Wing presses, 8 strikes. Its recording shows why (frame 445: "You cannot use this
item while sitting" x3, the Rogue sitting under a tree at (72,79)):
- **The server stands a sitting player up when hit** (pinned pc.cpp `pc_damage` ->
  `pc_setstand`). The runner then pressed "stand", which is the Insert TOGGLE: the character SAT
  back down while the runner believed it stood.
- From then on, every walk click stalled, and every potion and Fly Wing was refused while
  sitting.
- This bug is in every version since dungeon@1. a6 is where it bit hardest: a hit during a rest.

**dungeon@8.2** (this commit):
- a hit or an HP drop seen while the runner believes it sits only RECORDS that the server stood it
  up; it presses nothing;
- the "hit while sitting" stand press is gone;
- the other stand presses (rest full / max, overweight, escape) remain. They come with no damage
  first.

**The block:**
- a7 (S), a5b (N) and a8 (N) run @8.2.
- The verdict pools a1-a4, a5b, a6-a8 as registered.
- Beside it, a sensitivity view leaves out a6, the run that hit the since-fixed fault. Both are
  reported, and neither is chosen after the fact.

## Amendment H (2026-10-26 03:51 ICT from `date`; after a5b, BEFORE the store step and a9)

**H1. The A/B verdict (section 5's rule, value per hour at Overcharge, `dungeon_judge.py`):**

| run | arm | hours | value at OC | per hour | kills / h | deaths |
|---|---|---|---|---|---|---|
| a1 | N | 0.395 | 6,706 | 16,961 | 53.1 | 1 |
| a2 | S | 0.600 | 12,521 | 20,867 | 48.3 | 0 |
| a3 | S | 0.600 | 9,445 | 15,741 | 50.0 | 0 |
| a4 | N | 0.600 | 9,902 | 16,502 | 51.7 | 0 |
| a5b | N | 0.600 | 7,574 | 12,619 | 43.3 | 0 |
| a6 | S | 0.600 | 2,014 | 3,356 | 11.7 | 0 |
| a7 | S | 0.600 | 10,539 | 17,557 | 46.6 | 0 |
| a8 | N | 0.600 | 6,016 | 10,026 | 33.3 | 0 |

- **As registered (a1-a4, a5b, a6-a8, pooled by hours):** N 13,754 / h (4 runs, 2.20 h, range
  6,935); S 14,381 / h (4 runs, 2.40 h, range 17,511). |N - S| = 627 < 8,755 (half the larger
  range): **NO DIFFERENCE, so N is kept** (no SP, simpler). The prediction N >= S is not shown
  either way.
- **The sensitivity view (Amendment G: a6 left out, the run that hit the since-fixed stand-toggle
  fault):** S 18,055 / h (3 runs, 1.80 h, range 5,126) vs N 13,754. |N - S| = 4,301 > 3,467:
  **S WINS** in this view.
- Both are reported, and neither is chosen after the fact (Amendment G). The registered verdict is
  "no difference". The sensitivity view says that without a6's fault, Steal-first earned ~31 %
  more per hour. Batt decides the arm for the next step.

**H2. The milestone: "the bag is full" (A2, B2).**
- a9's pre-run frame (03:49:19) reads Weight 1,069 / 2,430 = **44.0 % >= 40 %** (972). a9's setup
  would refuse. Batt's "first train hunting until the bag is full" is reached at a5b's end (03:49).
- **What the 44 % holds:** about 160 of it is the restocked stock (8 White Potions, 8 Fly Wings,
  read on the hotbar). a8 had used all 10 of each; a5b's setup restocked 10 + 10. The rest is the
  equipped gear (~320) plus the loot since the 19:38 store.

**H3. What follows tonight:**
1. **The store step** (section 4, at its registered 40 % trigger; Batt decision 4, @storage in
   group 20; its first use 19:38 is its positive case). A2 withdrew storing BETWEEN runs so the bag
   could fill; the milestone is now reached. It runs on the safe stand (prt_fild08 268,107), with a
   judged frame of the open storage first and the DB weight after.
2. **The schedule (Amendment E).** After the store, a9 cannot end by D3 + 120 (04:32:08), so
   cycle 3 ends with a8 and a5b. a9 moves to cycle 4.
3. **The Orc Lord flee proof** (orclord-recognizer.md section 12) runs in this gap, on prt_fild08,
   instead of at 04:24. It starts with the Fly Wings topped up; afterwards the stand first, then
   immunity OFF (verified on the bubble), then a fresh pre-run frame.
4. **Cycle 4:** a9 (N), a10 (S) and a11 (S), released at D4, D4 + 38 and D4 + 76, where D4 >= 04:43:08
   is a9's setup kill. Each ends <= D4 + 120.
   - a12 and a13 do not run tonight: cycle 5 would end after the 07:00 report.
   - The second block (a9+) is reported pooled by arm and decides nothing (B2, C).
5. **Not done:** a Kafra NPC trip (a deliberate NPC contact) needs Batt's OK (section 4).

## Amendment I (2026-10-26 04:44 ICT from `date`; a9 running, BEFORE a10)

- **The store step (H3.1), 03:52-03:54:** `@storage` was opened and the open window judged.
  `store_loot` moved 12 stacks (8 Etc, 1 Usable, 3 Axes). Weight went **1,069 -> 480 / 2,430
  (19.8 %)**. The DB holds only the equipped gear plus 8 White Potions and 8 Fly Wings; storage
  holds the loot, e.g. Cyfar 159 and Orcish Voucher 79.
- **The flee proof (H3.3):** see orclord-recognizer.md 12a-12c.
  - Attempts fp1 and fp1b stopped safely by their own immunity checks (a 1-px bubble drift, then
    a double toggle; both fixed: flee@2, flee@3).
  - fp1c ran whole: bar 1 NO VERDICT (3 / 6 trials counted, 2 passed), bar 2 PASS. **The flee
    rule is not adopted.** `--clear-map` and the clock schedule stay.
- **Cycle 4 (H3.4):** a9 was released at 04:43:08 (judged frame `rogue-pre-a9b.png`: immunity
  OFF, verified 04:15:59) and started 04:43:11.
  - **D4 = 04:43:47** (a9's setup `@killmonster2`).
  - a10 is released >= 05:21:47, a11 >= 05:59:47. Each ends <= 06:43:47.

## Amendment J (2026-10-26 05:48 ICT from `date`; a10 died, BEFORE a11)

- **a9 (N, 04:43-05:20):** 29 kills (48.1 / h), 0 deaths, loot 94 %, 11,171 z / h at OC. It used
  ALL 10 potions and 10 Fly Wings (HP escapes at 15-19 %), as a8 did. The last wing went at
  35.1 of 36 min.
- **a10 (S, 05:21:47-05:45) DIED** after 22.8 min (23 kills, 60.5 / h).
  - **The cause is a runner bug, read from the packets.**
  - The setup tops the stock up against the DB's last SAVE. a9's last wings were used after the
    last save, so the DB still showed them. a10's setup typed `@item 504 8` and **no
    `@item 601`**.
  - a10 hunted with 0 Fly Wings. Its 7 HP escapes (17 % -> 0 %) sent **no** use-item request.
  - It died to Orc Ladies after its 8 potions. Then the runner's death path ran: `@alive`,
    `@heal`, the stand.
  - a10's pre-run frame showed F1 / F2 empty. The frame check passed that as the stock being out
    before the restock, but it was never checked AFTER the restock.
- **a11 (S, cycle 4, released >= 05:59:47, ends <= 06:43:47) runs only with:**
  1. the stock topped up by the parent first (`@item 601 10`, `@item 504 10`, on the stand,
     through the identity check);
  2. a judged pre-run frame that SHOWS the counts on F1 and F2 (wings >= 10); otherwise a11 does
     not run.
- **The runner fix is NOT made tonight** (it changes the setup; it needs its own
  pre-registration and tests). Proposed: **dungeon@8.3**, where the setup reads the stock after
  the restock from a source that cannot lag (the hotbar counts, or a forced save), and refuses to
  start below the target.

## Amendment K (2026-10-26 06:41 ICT from `date`): the second block and the night's end

**a11 (S, 05:59:47-06:36):** it started with the stock SEEN on its frame (10 / 10; its setup added
none). 36 min, 31.7 kills / h, 14,420 z / h at OC, 0 deaths, loot 100 %, Steal 6 / 15. It used 9
potions and 2 wings, and ended by the time box.

**The second block (a9-a11, reported pooled by arm; it decides nothing, B2 / C):**

| arm | runs | hours | value at OC / h |
|---|---|---|---|
| N | a9 | 0.60 | 11,171 |
| S | a10 (died: the restock bug), a11 | 0.98 | 16,068 |

**All 11 scored runs, descriptive only** (a1-a4, a5b, a6-a11; 6.18 h):
- N 13,201 / h (2.80 h) vs S 14,874 / h (3.38 h);
- 2 deaths: a1 (the natural Orc Lord, before Amendment E) and a10 (the restock bug, J);
- items per hour: Cyfar 25.2, Orcish Voucher 13.3, Milk 2.3, Iron 1.9, Sticky Mucus 1.5, Large
  Jellopy 1.0, Axe 0.5, Garlet 0.3;
- of 284 items: 148 picked, 30 stolen, 106 by Snatcher (37 %).

**The end state (06:40):**
- The Rogue stands on prt_fild08 268,107, HP 94 %, weight 485 / 2,430, 1 potion and 8 wings,
  immunity OFF.
- No runner, recorder or chain is running. a12 and a13 do not run (H3.4).
- The bag was stored once more (03:52). Storage holds the night's loot for Batt's Overcharge
  merchant.

## Amendment L (2026-10-26 10:28 ICT from `date`): Batt's demo is the bar; his decisions of the morning

**Batt's decisions (2026-10-26 ~09:4x, on the overnight report):**
1. The arm is **N** (no Steal): "focus on the kill speed per hour".
2. **dungeon@8.3** (the restock fix, Amendment J) is approved; build it in parallel.
3. **YOLO round 2** for this map: go. "If it is not accurate, you may train YOLO on the monsters."
4. **A new Orc Lord flee proof:** test again.
5. The Kafra trip comes later: "first, more items per hour".

**Batt's human demo** (09:51:01-10:05:59, 14.95 min, `20261026T095021-demo-human-demo-gef10`;
frames 5 Hz on the NAS; judged by `dungeon_judge.py row --live 898` plus the packets):

| measure | Batt | the bot, all 11 runs (6.18 h) |
|---|---|---|
| kills / h | **232.7** (58: Orc Lady 38, Orc Warrior 18, Poporing 2) | 42.6 (best run 60.5) |
| items / h | **329** (82: Cyfar 47, Orcish Voucher 31, Iron 4) | 46 |
| value / h at OC | **52,780 z** ➡️ **102,084 z** once his 38 Snatcher gains count as income (the judge fix, [gef10-time-budget.md](gef10-time-budget.md) §8) | 14,111 z (its snatches counted) |
| floor loot picked / dropped | **97.8 %** (44 / 45; 44 pickup clicks, all OK) | ~87 % |
| Snatcher procs / h | 152 (38: each <= 1 s after his own hit; SP never moved) | 17 |
| deaths / potions / wings | 0 / 1 / 0 (HP low 9 % once ➡️ **22 %**: 476 / 2,146; the 9 % was the judge's Crusader MaxHP fallback for a human demo, gef10-time-budget.md §8) | 2 deaths in 6.18 h |

- **His play:**
  - One clockwise loop along the map's ring from the Kafra: 1,894 cells in 14.1 min (134 cells
    / min), 28 walk clicks / min. ➡️ The same loop walked **twice** (833 cells; lap 1 8.9 min with
    41 kills, lap 2 4.9 min): gef10-time-budget.md §7, waypoints in
    `config/routes/gef_fild10-batt-loop.json`.
  - 62 attack clicks for 58 kills: one click, then auto-attack.
  - A kill every ~15 s (median 14.8 s). From the first hit to the death: median 5.3 s.
  - **No rest in the field.** At 14.1 min he entered in_orcs01 (the orc house) and sat with
    `/sit`: "I rest on this map because it is safer".
  - His only UI change: one chat-window drag (09:51:04), reversed by the parent at 10:26 from his
    own input log.
- **THE BAR (Batt: "at minimum equal, or better"):** the bot's pooled runs reach >= 232.7
  kills / h AND >= 329 items / h, with floor loot >= 97.8 % and no death from a bug. Each version
  is judged against it, on at least two pooled runs.
- The judge's Snatcher rule keys on the runner's events, so for a human demo it files Snatcher
  gains as "other". Fixed next (packets: a gain <= 1 s after our own hit act). ➡️ FIXED
  (`dungeon_judge.own_hits`): his demo reads picked 44 / snatched 38 / other 0.
- ➡️ **Where the bot loses its time against this demo, ranked:** [gef10-time-budget.md](gef10-time-budget.md)
  (rest 33 s / kill, stop-and-go walking 15, the defend-scan reaction 5.5, the loot pause 4.7, ...).

**The work, in parallel:**
- (a) dungeon@8.3, the restock fix;
- (b) the demo's time budget vs the bot's (walk / fight / loot / rest / search), ranked by time
  lost, to design dungeon@9 on his loop;
- (c) YOLO round 2: the notice rule in C1, a NEW TEST (a9-a11, never read), T1, then the cache and
  training, plus the detector's recall on his demo frames;
- (d) the flee proof's new pre-registration.

## Amendment M (2026-10-26 10:40 ICT from `date`): dungeon@8.3, the stock read from the hotbar; run b1

**Why not the DB:** rAthena writes the inventory to the DB only on its autosave (minutes) or on
events such as a storage close. `@save` does not help:
- it calls `chrif_save(sd, CSAVE_NORMAL)` without `CSAVE_INVENTORY` (rAthena master
  `atcommand.cpp` / `chrif.cpp`, read 10:4x);
- it would also move Batt's save point.

**dungeon@8.3** (`scripts/hotbar_count.py` + the setup):
- The DB lines are a first guess and are typed on the stand.
- Then the setup reads the F1 / F2 counts the client DRAWS on the hotbar and adds what is
  missing from that count (`stock_plan`).
- It reads again and STOPS if a count is unreadable or below 10 / 10. An empty slot (no digit,
  no icon) reads 0; an icon without a readable digit is unreadable.
- Excess potions are drunk by the true count.
- Rogue only (`hotbar_stock`).

**The calibration and the positive case:**
- Digit templates: on the safe stand, 10:32, F1's potions were drunk 9 -> 0 and the strip was
  grabbed each time. The templates are the client's pixels, in `data/hotbar/` (gitignored).
- **The reader was validated on 12 real frames from last night, none used for the cut: 24 / 24
  slot reads right.** They include a5b's and a10's EMPTY slots (0 / 0), the case that killed a10.
- The skill slot (F3) is not read: its dark frame enters the count box.

**Run b1** (arm N, seed 25540, 36 min, `--clear-map`), the live proof of 8.3:
- The setup's `stock` record must match the judged pre-run frame, and the run must start with
  10 / 10.
- The Orc Lord was cleared at 09:49:28 (Batt's demo prep). b1 must end <= 11:49:28; the next
  cycle starts >= 12:00:28 (Amendment E).
- b1's numbers are reported against Batt's bar (Amendment L). dungeon@9, modelled on his loop,
  follows the time-budget analysis.

## Amendment N (2026-10-26 11:31 ICT from `date`): b1, fp2, the time budget, and the order of work

**b1 (N, dungeon@8.3, 10:41:44-11:18):**
- 8.3's live proof: the setup read the hotbar as F1 10 / F2 10 before and after, matching the
  judged frame; no top-up was needed.
- 36.0 min, 28 kills (**46.6 / h**), 0 deaths, HP low 25 %, 1 potion and 1 wing, loot 91.7 %,
  14,870 z / h at OC. The same level as the night's runs (8.3 changes the restock only).

**fp2 (the Orc Lord flee proof, round 2):** NO VERDICT, and trial 1 left the Rogue at 1-2 HP
(orclord-recognizer.md 13a). The sight-based flee is NOT adopted. `--clear-map` plus
Amendment E's clock schedule stay the protection, for every run.

**Where the bot loses its time against Batt** ([gef10-time-budget.md](gef10-time-budget.md); the
same ruler from packets; 8 runs, 4.80 h):
- 81.6 s per kill against Batt's 15.5 s.
- **Rest takes 50 % of the gap.** It is downstream of DAMAGE: 213 HP lost per kill against
  22.5. The bot answers an attacker after a median 12.7 s, against 1.3 s; 30 attackers were
  never hit back.
- **Stop-and-go walking takes 22 %.** 2,437 of 3,807 walk decisions were refused on a
  "cursor unknown". The bot walks 8.7 % of its time, Batt 35.6 %.
- Loot pauses and idle after the fight make up most of the rest.
- **Why the reactions are slow:** v1 sees almost none of this map's monsters (gef10-round2.md:
  recall 8.0 %, Orc Lady 1.4 %).

**The order of work (each version pre-registered with one main change, judged against Batt's
bar):**
1. **The gef10 detector, round 2** (gef10-detector.md 13s):
   - w3, the immune watch: 11:29 -> ~12:02;
   - T1 on TEST2 once;
   - if it passes, the cache before 14:00, then training on the GPU (R1-R3).
2. **dungeon@9.0: continuous walking on Batt's loop** (`config/routes/gef_fild10-batt-loop.json`).
   It waits for the cursor-unknown diagnosis (a subagent, offline).
3. **dungeon@9.1:** a quick loot click.
4. **Then the detector-driven engagement,** once a gef10 model passes its evaluation: answer an
   attacker in about 1 s, target monsters at range.
   ➡️ 2026-10-29 17:04 (gef10-eval.md RESULT R2): the round-2 model did NOT pass (G1 precision
   0.867 < 0.882; Q1 and G2 passed). No gef10 model has passed yet. Batt decides the next step.
5. **The rest policy last** (rest is downstream of damage).

- Recordings stay in /dev/shm during SET hours (`dataset_ship` refuses 09:30-17:00 on
  weekdays). They ship at 17:01.

## Amendment O (2026-10-26 12:22 ICT from `date`): dungeon@9.0 "the walk" -- Batt's loop + --walk-trust; runs c2, c3

**Why** (gef10-time-budget.md, gef10-cursor-unknown.md):
- Stop-and-go walking is 22 % of the gap to Batt.
- 64 % of the walk decisions read the cursor as "unknown", and ~75 % of those are REDRAW LAG:
  the 0.35-s read ends before the client draws the arrow while the Rogue is still moving.
- 71 % of the clicks came only after standing still for >= 2 s.

**The change** (the walk; arm N; everything else is 8.3):
1. `--search patrol` on **config/routes/gef_fild10.yaml** (Batt's loop, 82 waypoints).
   - Authored and reviewed by the agent under Batt's delegation (~12:2x, "Delegate to the
     agent").
   - Waypoint 0 was moved off the Kafra's no-enter area.
   - `map_routes.py prove gef_fild10`: ok, every waypoint walkable and outside the zones, every
     leg connected, 834 steps.
   - The patrol joins at the nearest waypoint and resumes at the NEXT one ahead after a fight (as
     on orcsdun01).
2. `--walk-trust` (merged, OFF by default).
   - An UNKNOWN walk read is clicked when the cell is trusted: on the route grid, the straight
     walk and 4 landing cells beyond clear of every zone (closed supercover), >= 6 cells from every
     L3 NPC, no fresh detector box within 60 px.
   - SWORD still engages; red no-entry still carves.
   - Its estimate: 2,190 of 2,249 unknowns would have been clicked; risk <= ~3 attack requests per
     run on target-species monsters.

**Runs:** c2 (seed 25542) at >= 12:44:30 and c3 (seed 25543) at >= 13:22:30, 36 min each.
- Amendment E's cycle: D5 = c1's setup kill 12:06:30; each run ends <= 14:06:30.
- `--clear-map`, the judged pre-run frame, 8.3's hotbar stock check.

**Measures** (pooled c2 + c3, against the 8.x arm-N runs a1, a4, a5b, a8, a9, b1 and against
Batt's bar):
- kills / h, items / h, value / h at OC;
- the time budget (walking share, idle inside search);
- `walk_trusted` and the walk refusals;
- deaths;
- the hard bars from the packets: NPC contact 0, map change 0, attacks on non-targets 0.

**Prediction:** the walking share rises from 8.7 % toward Batt's 35.6 %, and kills / h rise by
>= 5 over the 8.x arm-N pool (rest stays, being damage-driven).

**Census:** the click census and the targeted tests pass with --walk-trust merged
(walk_trust, cursor_unknown, click_census, dungeon_hunt, map_zones, map_routes: 83 passed).

**Noted, not fixed:** `map_zones.segment_violates` misses axis-aligned straight walks through a
no-enter area (gef10-cursor-unknown.md 8). No impact is found on this walk, whose targets come
from the zoned route grid. Its own commit and tests later.

## Amendment P (2026-10-26 13:01 ICT from `date`): c2's HARD BAR (the bulletin board), dungeon@9.0b; run c3

**c2 (9.0, 12:44:31-12:53:54) stopped on a HARD BAR: an NPC dialog was open.**
- The bulletin board at (69,340) beside the Kafra showed "[Orc Dungeon] Caution! ..."; the UI
  gate found it and typed nothing.
- **The cause, from c2's events:** a kill at -11.8 s, a scan, then a **strike** at -11.4 s on a
  monster standing in front of the board. The strike never hit ("unlock: no hits"): the click
  landed on the board's sprite.
  - The Rogue stood at 68,337: inside the board's no-enter area and 5 cells from the house door
    gef022 (63,337).
  - The patrol's Kafra corner had brought the fights there. Waypoint 0 (80,333) was 7 cells from
    the Kafra; waypoint 81 (71,327) was outside the search area, 9 cells from the door. The old
    heading search stayed inside the area, whose 10-cell warp margin covers that corner.
  - It was NOT `--walk-trust`: the dialog came from a strike click.
- **The recovery (12:56):** the board's script (npc/pre-re/other/bulletin_boards.txt) is mes /
  next x3 / close, no menu. When the parent read the dialog it already showed CLOSE (it had
  advanced; possibly Batt). `ui_gate.ensure_clear` pressed its known Enter on CLOSE, then
  `@warp` to the stand and `@heal`. The Orc Baby had hit the Rogue during the dialog: HP 22 %.
- c2's own events: 198 walk clicks in 9.4 min (187 trusted), against ~5 / min before.
- c2's recorder stopped after 74 s on the IO guard, so the judge's numbers for c2 cover about a
  minute and are not used.

**dungeon@9.0b = 9.0 + two safety changes:**
1. **The route:** the Kafra corner's waypoints 80,333 and 71,327 are DROPPED. The loop closes
   76,317 -> 88,337.
   - `map_routes.py prove`: ok, 80 waypoints, 827 steps.
   - Every waypoint is inside the search area and >= 15 cells from an L3 NPC; every walked leg
     cell is >= 11.
2. **`--npc-guard`** (new, OFF by default; this commit): no strike / burst / Steal / loot click
   while OUR cell is within `NPC_NO_FIGHT` = 8 cells of an L3 NPC.
   - NPC sprites stand <= ~5 cells tall.
   - The refusal is logged (`npc_guard`) and counted.
   - Tests pass; the click census is unchanged (the guard only refuses).

**Run c3** (9.0b: `--search patrol --walk-trust --npc-guard`, seed 25543, 36 min):
- it starts after this commit and ends <= 14:06:30 (D5 + 120);
- the hard bars from the packets, plus `npc_guard` refusals, `walk_trusted`, kills / h;
- its numbers are judged from the runner's own packets (its recorder may stop on the IO guard
  during SET hours).

## Amendment Q (2026-10-26 13:36 ICT from `date`): c1-c3 judged; rest is now the bottleneck; 9.1 = react on the first swing; c4-c6

**The runs.** Packets were rebuilt from the sniffer archive (`record_session.write_packets`): the
fail-closed stop path exits before writing them.

| run | version | minutes | kills / h | deaths | HP low | loot | OC z / h | hard bars | end |
|---|---|---|---|---|---|---|---|---|---|
| c1 | 8.3 (heading) | 10.8 | 72.0 | 0 | 28 % | 92 % | 24,649 | pass | stop: no fresh frame within 1.5 s |
| c2 | 9.0 | 8.6 | 55.9 | 0 | 71 % | 67 % | 18,852 | **NPC contact 1** (Amendment P) | the board's dialog |
| c3 | 9.0b | 28.8 | 50.0 | 0 | 15 % | 100 % | 17,249 | pass (npc 0) | stop: no fresh frame within 1.5 s |

- **The frame stalls (c1 at 10.8 min, c3 at 28.8 min):** the runner refused to act on a frame
  older than 1.5 s. Both fell in SET hours, when the host's IO and CPU were busy: the recorders
  stopped on quant-postgres and Frigate IO spikes all day, and the cache build aborted. The stop
  is fail-closed and correct.
- **9.0b did what it targeted (c3's time budget against Batt, time_budget.py):**
  - idle inside search fell from 15.3 s per kill (the 8-run pool) to **5.8**;
  - search walking rose from 7.6 % to 13.6 % of the time;
  - 50 kills / h against the pool's ~44.
- **But REST grew to 46.7 % of the time (33.6 s per kill, 32.8 lost against Batt).** Rest repays
  DAMAGE. Sitting regen is ~3.7 HP/s for both. The bot loses ~213 HP per kill, Batt ~22.5,
  because the bot answers an attacker after ~12.7 s and Batt after 1.3 s.
- **Why so late:** the defence scan starts on a HIT (the Battle Log) or an HP fall. With FLEE
  192, orcs hit only 4-7 % of their swings, so the first hit comes many swings in. Batt reacts to
  the swing itself; the client draws a "Miss" text above our head on every missed swing.
- **9.1 (next, pre-registered when its detector is validated):** start the defence scan on the
  FIRST swing at us. A pixel detector of "a Miss above our head" is being built and validated
  offline against the packets (`act` on us with damage 0; subagent; `gef10-miss-cue.md`).
  - The house rest (`--rest house`, merged, OFF) estimates only +3 to +5 kills / h. It needs a
    supervised live probe of the indoor camera first. It comes after 9.1.
- **c4, c5, c6** (9.0b unchanged: `--search patrol --walk-trust --npc-guard`; seeds
  25544-25546):
  - Amendment E's next cycle: D6 = c4's setup kill at >= 14:17:30; c5 at >= D6 + 38; c6 at
    >= D6 + 76.
  - Pooled with c3 as 9.0b's result. They run in the market window 14:00-14:45: runs are not
    disk-heavy steps; their recordings stay in RAM until 17:01.

## Amendment R (2026-10-26 14:19 ICT from `date`): dungeon@9.2 = 9.0b + `--rest house`; the door probe first; run c7

**Done so far** (gef10-house-rest.md 11, 13:38-13:42): the exits of all three SEALED houses
(gef018, gef019, gef020) work from the computed indoor pixels, landing exactly on the return
cells. The rooms are dark (17-20), with no minimap, HP readable and the UI clear.

**Before the scored run: the DOOR probe** (unscored, GM-assisted, IMMUNE), at ~16:12-16:25 after
c6. Per sealed house:
- `@warp` to one of its approach cells (`house_setup`'s);
- confirm the readout; hover the door cell's projected pixel;
- ONE click; expect the load and "inside" by `house_rest.Transition`;
- exit by the validated pixel; back at the return cell; `@warp` to the stand.
- **Any STOP or a wrong map = no scored house run** until it is understood.

**Run c7** (if the probe passes):
- dungeon@9.2 = 9.0b (`--search patrol --walk-trust --npc-guard`) + **`--rest house`**, the ONE
  change; seed 25547, 36 min;
- Amendment E's next cycle: D7 = c7's setup kill at >= 16:29:15 (D6 14:18:15 + 131).
- The baseline is 9.0b's pool (c3-c6).

**Hard bars** (packets, the judge; gef10-house-rest.md 9):
- map changes other than the recorded house trips: 0;
- to orcsdun01 / orcsdun02: 0, absolute;
- NPC contacts 0; attacks on non-targets 0;
- no Fly Wing between a `house_door` and its `house_back`;
- no attack act on us inside in_orcs01.

**Trip bars:** >= 90 % of door clicks reach "inside"; 100 % of exits come back at the planned
return cell; every STOP reported with its frame.

**Measures:**
- kills / h, items / h, value / h at OC;
- the rest share, and the HP taken per kill in the rest and around-rest windows;
- trips / h, the trip time, route steps to the door;
- fallbacks by why, deaths.

**Prediction:** kills / h +3 to +5 over 9.0b's pool; the HP taken in the rest and around-rest
windows per kill falls by >= 50 %; the rest share does not rise.

**The 17:01 ship:** it ships every recording in RAM at 17:01. c7's recording, still running then,
is excluded and shipped after its run.

## Amendment S (2026-10-26 14:51 ICT from `date`): dungeon@9.1 = 9.0b + `--miss-cue`; run c6

**The cue** ([gef10-miss-cue.md](gef10-miss-cue.md); a subagent, merged; `scripts/miss_cue.py`):
- The "Miss" of a monster's swing that misses us is drawn above the ATTACKER. For a melee orc
  one cell away, that is within about +-50 px of our head. It appears ~0.7-0.8 s after the swing's
  packet.
- The detector: a pure-numpy NCC of a 282-instance mean template in a ROI around our head.
  Threshold 0.60, fixed on TUNE before TEST. ~8 ms a read.
- **TEST** (a7, a8, a5b, b1, c1, c2, c3):
  - per-frame recall 58.7 %; per-EVENT recall 65.9 % (56 / 85);
  - **0 of 4,207 negative frames** fired; 0 of 478 hard negatives;
  - 36 / 36 audited fires showed a real Miss.
- **Batt's 5 Hz demo:** per-event recall 86.1 %, the first fire a median 0.98 s after the swing.
- **TEST2, the held-back set** (a9, a10, a11, w3; opened ONCE by the parent at 14:4x):
  - per-frame recall 39.0 % (688 / 1,764);
  - **0 of 2,979 negative frames** fired (49.8 min); 0 / 157 notices; 0 on potions / Steal /
    Lucky / our attacks / hits on us;
  - 1 of 166 "fight" frames, likely a real Miss with no packet (a known truth gap).
- **Estimated gain** (packets of 10 runs): the reaction median 11.8 s -> ~6 s; ~28-32 % of all
  damage avoided.

**dungeon@9.1** (`--miss-cue`, d5793aa, OFF by default; the ONE change over 9.0b):
- A Miss read in the HP loop counts as a swing at us. Within FIGHT_TAKEN_S (2.5 s) it starts a
  fight like a hit, logged as an engage "by miss_cue".
- It is NOT read while sitting: a miss never presses the stand toggle (8.2's lesson).

**Run c6:** 9.1 = `--search patrol --walk-trust --npc-guard --miss-cue`, seed 25546, 36 min,
at >= D6 + 76 = 15:34:15. It is compared with 9.0b's runs c3-c5. A6's `--rest house` is not
included.

**Measures:**
- **primary:** the reaction time of engagements the monster opened (packets: its first swing at
  us -> our first attack request); prediction median <= 8 s, against ~12 s;
- damage per kill (prediction >= 20 % lower), the rest share, kills / h;
- **false triggers:** an engage "by miss_cue" with no act on us within 3 s before. Bar: <= 1
  per run;
- the hard bars as always.

## Amendment T (2026-10-26 14:53 ICT from `date`): Batt's NO-REST arm (strategy P); c5 becomes it

**Batt (~14:5x, translated):** "Try the approach of not sitting to rest: keep HP above 20 % with
White Potions and keep hunting continuously. I want to know the rate per hour with no sitting at
all."

**Strategy P** (this commit; on 9.0b's walk; the ONE change is the sustain rule):
- `rest_below` None: **never sits**;
- a White Potion below **40 %**: an Orc Warrior hits up to ~300 (14 %), so two hits from 40 % stay
  above Batt's 20 %;
- the Fly Wing only below 15 % (or on a fast drop below 25 %);
- **30 potions stocked** (8.3's hotbar check tops up to 30). The carried weight stays under the
  setup's 48 %.

**c5 is this arm** (instead of 9.0b, at Batt's request):
`--strategy P --search patrol --walk-trust --npc-guard`, seed 25545, 36 min, at >= D6 + 38 =
14:56:15. It must end <= D6 + 120 = 16:18:15.

**Measures:**
- kills / h, items / h, value / h at OC, and the NET value (the potions' cost counted, the
  judge's cost_h);
- potions and wings used per hour;
- deaths, the HP low, the rest share (expected 0);
- the hard bars.

It is compared with 9.0b's runs (c3, c4) and Batt's bar.

**The rest of the plan shifts:** 9.1 (`--miss-cue`, Amendment S) and the door probe / 9.2
(Amendment R) follow in the next cycles.

## Amendment U (2026-10-26 15:03 ICT from `date`): c5 (strategy P) DIED at 4.5 min to a swarm; P2 adds a swarm escape; c5b

**c5** (P: no rest, a potion below 40 %, a Fly Wing below 15 % or a fast drop below 25 %),
14:56:16-15:00:5x.
- **A death after ~4.5 min**, recovered by the runner's death path (@alive, @heal, home).
- **The cause** (packets): a SWARM. 8 orcs were on us at once (6 Orc Ladies, an Orc Warrior, an
  Orc Baby). The last 30 s held 59 acts on us, 23 hits, 2,900 damage (~200-250 HP/s).
- Three White Potions at 31 / 39 / 35 % were each eaten within a second.
- The last 37 % -> 0 took 0.8 s. The escape rule (fast drop BELOW 25 %) never fired before that,
  because the potions held HP above 25 %.
- **What it says about Batt's question** (the rate with no rest): the bot as it is reacts and
  kills too slowly to keep a no-rest pace. The orcs pile up and the potions cannot outrun a swarm.

**P2** (this commit): P plus a SWARM ESCAPE, a Fly Wing when HP < 50 % AND the loss over 2 s is
>= 150 HP/s. On c5's trace it would have flown at ~43 %, about 5 s before the end (a unit test
replays it). Otherwise unchanged: never sits; a potion below 40 %; the Fly Wing below 20 %;
30 potions stocked.

**c5b** (P2: `--strategy P2 --search patrol --walk-trust --npc-guard`), seed 25545, 36 min:
- starts at once and ends <= 16:18:15 (D6 + 120);
- **c6 (9.1) moves to the next cycle** (>= 16:29:15), and the door probe / 9.2 after it.
- **Measures:** as Amendment T, plus Fly Wings by why (swarm / low / position).

## Amendment V (2026-10-26 15:44 ICT from `date`): c5b (P2, NO REST) -- 96.6 kills / h, 0 deaths; c6 = P2 + `--miss-cue`

**c5b** (P2: never sits; a potion below 40 %; the swarm escape; 9.0b's walk), 15:06:15-15:43:11,
the full 36 min:

| | c4 (9.0b, sits) | **c5b (P2, no rest)** | Batt's demo |
|---|---|---|---|
| kills / h | 43.3 | **96.6** (58 kills) | 232.7 |
| deaths | 0 | **0** | 0 |
| HP low | 20 % | 19.9 % | 22 % |
| potions / wings used | 6 / 5 | **12 / 6** (20 / 10 per h) | 1 / 0 |
| floor loot | 92 % | 90.5 % | 97.8 % |
| items / h | ~46 | **~82** (Cyfar 61.7, Voucher 15.0, Sticky Mucus 3.3, Axe 1.7; 30 of 49 by Snatcher) | 329 |
| value / h at OC | 13,812 | **31,445** | 102,084 |
| rest share | ~47 % | **0 %** | 0 |

- **All 6 Fly Wings were the new swarm escape:** the rate rule fired at 171-456 HP/s with HP 25-49 %.
  c5 under P had died to that drain.
- **Consumables:** 20 White Potions and 10 Fly Wings per hour.
  - At NPC buy prices that is ~24,590 z / h, so value at OC minus consumables is ~+6,850 z / h.
  - The judge's stricter net (picked items at NPC sell only, `net_h`) is -15,056 z / h.
  - The potions' real cost depends on Batt's source.
- **Answer to Batt's question:** with no sitting, the bot hunts at **~97 kills / h, 2.2x** the
  resting bot. Its damage per kill is unchanged; it is now paid in potions and Fly Wings instead
  of time.

**c6, amended (Amendment S had 9.1 on 9.0b):** **P2 + `--miss-cue`**, seed 25546, 36 min, at
Amendment E's next cycle (>= 16:29:15, D6 + 131). Compared with c5b.
- **Prediction:** earlier reactions; fewer potions and Fly Wings per hour (damage -20 % or more);
  kills / h not lower.
- The house rest (9.2, Amendment R) is shelved while the runs do not sit; its code stays, OFF.

## Amendment W (2026-10-26 16:43 ICT from `date`): c6's re-engage loop; dungeon@9.1b; c7 = P2, c8 = P2 + the 9.1b cue

**c6 (P2 + `--miss-cue` as 9.1, seed 25546) runs as registered**, 16:29:15 onwards. It has a defect
that showed live at 3 min:
- **The loop.** After a kill, a Miss still drawn on screen restarts the fight on every 0.1 s tick:
  - the quiet-kill end (`fight_end` "quiet kill") tests hits only (`last_taken`), so it ends the
    fight again at once;
  - `swing_now` stays true for 2.5 s after the last Miss read, so it fires the trigger again.
- **Counts at 13.6 min:**
  - 569 engages "by miss_cue" from 60 Miss onsets, and 572 fight ends;
  - 29 kills (the same pace as 128 kills / h, against c5b's 96.6).
  - Example: 181.8-182.9 s held 12 engage / end pairs in 1.1 s.
- **Cost and safety.** The loop sends no click and no input (engage / fight_end events only), so
  it has no safety effect. It delays the loot step after an affected kill by up to ~2.5 s plus one
  ring scan.
- **How c6 is reported.** As "9.1, with the loop", and not pooled. It does not test the cue as
  Amendment S intended: a swing that restarts a fight the same tick it ended.

**dungeon@9.1b (the runner's fixes record `miss_cue_rule: "9.1b"`):**
- Every fight end (both paths: the quiet kill and the empty scan) sets `swing_floor = tick`.
- A Miss starts a fight only when it was read AFTER the floor:
  `swing_engages(tick, last_swing, swing_floor)`.
- The cue is not read on the tick right after a fight end (`mode == "after"`), so a Miss still
  drawn goes to the loot step.
- **Residual, bounded.** A Miss still readable after the loot step can start one more fight. That
  fight is a ring-1 scan that then ends. The text is matched only while 0.8-1.8 s old
  (gef10-miss-cue.md 1c).
- **Tests:** `test_a_miss_read_before_the_fights_end_never_restarts_it` plus the updated 9.1 pin.
  The click census and the safety tests are green. No click path changed.

**This cycle (Amendment E, D7 = c6's setup @killmonster2 at 16:30:01):**

| run | arm | seed | release | must end by |
|---|---|---|---|---|
| c7 | **P2 alone** (9.0b + P2; the arm of c5b) | 25547 | >= 17:08:01 (D7 + 38) | 18:30:01 |
| c8 | **P2 + `--miss-cue` 9.1b** | 25548 | >= 17:46:01 (D7 + 76) | 18:30:01 (D7 + 120) |

- Both runs: 36 min; Batt's loop; `--walk-trust --npc-guard`; a judged pre-run frame.
- **Storage.** A store step on the prt_fild08 stand comes before a run whose weight would start at
  >= 40 %. c6 read 37.7 % at 13.6 min.
- The next cycle starts >= 18:41:01 (D7 + 131).

**Compared (pooled):** c5b + c7 (P2) against c8 (P2 + 9.1b). c6 is reported apart.
- **Measures:**
  - kills / h;
  - damage taken / kill;
  - White Potions + Fly Wings / h;
  - reaction (first swing or hit at us -> our first strike), from packets;
  - the cue's false fires (a Miss onset with no monster attack at us within 1.5 s in packets),
    <= 1 / run (Amendment S).
- **Prediction (unchanged from Amendment V):** earlier reactions; damage / kill down >= 20 %, and
  potions + wings / h with it; kills / h not lower.

## Amendment X (2026-10-26 17:11 ICT from `date`): c6 judged (P2 + the 9.1 cue, with its loop); c7 running

**c6**, 16:29:15-17:05:43:
- **Window:** 35.4 min, run_start..run_end.
- **End:** a fail-closed frame stall ("no frame newer than the action within 1.5 s") about 20 s
  before its 36 min. The end warp to the prt_fild08 stand ran (17:05:39).
- **Packets:** rebuilt from the sniffer archive with `record_session.write_packets`.

| | c5b (P2) | **c6 (P2 + 9.1 cue, the loop)** |
|---|---|---|
| kills / h | 96.6 | **101.6** (60 kills) |
| deaths | 0 | **0** |
| HP low | 19.9 % | **35.5 %** |
| White Potions / h | 20.0 | **11.9** (7) |
| Fly Wings / h (all swarm escapes) | 10.0 | **6.8** (4) |
| damage taken / kill cycle (mean, packets) | 126.1 | **103.9** (-18 %) |
| reaction when attacked first (median / mean) | 8.40 / 8.53 s | **6.07 / 7.38 s** (-28 % / -13 %) |
| items / h | ~82 | **110.1** (65; 29 by Snatcher) |
| value / h at OC | 31,445 | **32,276** |
| floor loot (completeness) | 90.5 % | 90.7 % |
| idle per kill | 14.84 s | 17.4 s |

- **c6's items:** Cyfar 34 (57.6 / h), Orcish Voucher 24 (40.7 / h), Sticky Mucus 3, Green Herb 1,
  Milk 1, Garlet 1, Large Jellopy 1.
- **The cue's honesty counters** (`scripts/miss_cue_live.py`, committed with this amendment, run on
  c6's packets):
  - 122 Miss onsets, **0 false**: every onset came within 3 s after a monster's act on us;
  - 1,163 engages "by miss_cue": 1,135 were the loop (within 0.3 s after a fight end), 28 were
    distinct, **0 false**.
  - The bar (<= 1 false engage per 36-min run) holds.
  - This run is the scorer's positive case on a real session.
- **Reading.**
  - Even with the loop, c6 met Amendment V's prediction on reaction and consumables:
    - reaction -28 % at the median;
    - potions + wings per hour -38 %;
    - kills / h not lower.
  - Damage per kill fell 18 %, just short of the predicted 20 %.
  - The loop's cost shows in idle per kill: 17.4 s against 14.8 s.
  - This is one run on its own seed, so it is **not pooled** (Amendment W). c7 (P2) against
    c8 (P2 + 9.1b) is the registered comparison.

## Amendment Y (2026-10-26 18:27 ICT from `date`): c8 judged; Batt's decisions; base dungeon@8.4 + the map_zones fix; c9-c11

**c7** (P2 alone, seed 25547), 17:09:07-17:46:10, the full 36 min:
- 75.0 kills / h (45), 0 deaths, HP low 16.9 %.
- 17 potions and 10 Fly Wings (28.3 + 16.7 per h): 10 escapes, all 10 wings.
- **Its 10th wing went at 28.5 min.** It then hunted 7.5 min with no escape: the a10 condition.
- 207 damage per kill cycle (c5b: 126).
- Items: 98.3 / h (59). Value at OC: 24,352 z / h.

**c8** (P2 + `--miss-cue` 9.1b, seed 25548), 17:47:04-18:24:06, the full 36 min:
- 81.7 kills / h (49), 0 deaths, HP low 22.3 %.
- 10 potions and 6 Fly Wings (16.7 + 10.0 per h).
- 168 damage per kill cycle.
- Items: 78.3 / h (47). Value at OC: 24,490 z / h.
- **The cue:** 90 onsets, 0 false; 24 engages, **0 in a loop**, 0 false. 9.1b works live.

**The registered comparison (Amendment W): c5b + c7 (P2) against c8 (P2 + 9.1b):**

| measure | P2 pooled | c8 | Amendment V's prediction | met? |
|---|---|---|---|---|
| reaction when attacked first (mean) | 8.66 s | 7.73 s (median 6.56) | earlier | yes, -11 % |
| damage per kill cycle | ~161 | 168 | -20 % or more | **no**, +4 % |
| potions + wings / h | 37.5 | 26.7 | lower | yes, -29 % |
| kills / h | 85.8 | 81.7 | not lower | **no**, -5 % |

- **Sensitivity, both cue runs** (c6 with its loop + c8 against c5b + c7):
  - kills / h 91.6 vs 85.8;
  - damage per cycle ~133 vs ~161;
  - consumables 22.7 vs 37.5 / h.
- Runs differ a lot from each other: c5b 96.6 against c7 75.0 kills / h, on the same arm.
- **Verdict: not adopted yet.** The alternation goes on (below). The cue is safe: 0 false fires in
  212 onsets.

**Batt's decisions (2026-10-26 ~18:2x, in chat):**
1. **P2 (no sitting) is the DEFAULT strategy** for the gef_fild10 Rogue from now on.
2. **The immune staged-items session on gef_fild10 is APPROVED**, for floor-item labels (D10's
   recipe):
   - the GM immune;
   - items placed by @item on open ground;
   - Poporings cleared first;
   - staged items never counted as income.
   - Its plan is `docs/planning/gef10-eyes-loot.md`.
3. **New pixel cues must not read English UI text.** A Thai rAthena server would break them. The
   "obtained" / "You got" texts are NOT to be used as pickup proof. Sprites, shapes, colours and
   digits only, each checked on the Thai client before it is relied on.

**Base from c9 on (both arms):**
- dungeon@8.4, the stock guard (2f1cc9f):
  - the hotbar count is re-read after every potion and Fly Wing press;
  - a 0 ends the run as `stock_out`, with the end warp home;
  - P2 stocks 20 Fly Wings.
- The map_zones fix (da01ee6): an axis-aligned straight walk through a no-enter area is refused.
  gef_fild10's loop proves the same: 80 legs, 827 steps.
- A `stock_out` end is a normal end: the run counts over its own window.

**This cycle (Amendment E):**
- D8 = c9's setup @killmonster2, at or after 18:41:01 (D7 + 131).
- Runs of 36 min each, Batt's loop, `--walk-trust --npc-guard`.

| run | arm | seed | release |
|---|---|---|---|
| c9 | P2 + `--miss-cue` 9.1b | 25549 | >= 18:41:01 |
| c10 | P2 | 25550 | >= D8 + 38 |
| c11 | P2 + `--miss-cue` 9.1b | 25551 | >= D8 + 76, ending by D8 + 120 |

- A store step comes before any run that would start at >= 40 % weight.
- **The comparison after c11:** P2 (c5b, c7, c10) against P2 + 9.1b (c8, c9, c11). c6 is
  reported apart.
  - The same measures as above, and the same prediction.
  - The cue is adopted only if, pooled, reaction AND consumables improve with kills / h not lower.

## Amendment Z (2026-10-26 18:42 ICT from `date`): D8 = 18:41:45; the LOOT TRIM block (gef10-eyes-loot.md E1), pre-registered

**The cycle's clock:**
- **D8 = c9's setup @killmonster2 at 18:41:45.** c9 runs dungeon@8.4: stock 30 / 20 verified on
  the hotbar, weight 870 / 2430.
- c10 is released at >= 19:19:45 and c11 at >= 19:57:45; both end by 20:41:45.
- **The next cycle (D9) starts at >= 20:52:45.**

**The change, `--loot trim`** (branch `feat/loot-trim`, e1e5a70; merged only after c11 ends, so
c9-c11 keep their registered base):
- Loot v1's list and its order (nearest first) are unchanged.
- At most `LOOT_TRIM_HOVERS` = 9 cell hovers. Cells out of view are not counted. No sweep.
- No new click and no click path changed.
  - A pickup is still the PICKUP-hand cursor read before its click; no text is read (Batt's rule).
  - Click census and safety tests are green.
- **Why:**
  - The idle study (gef10-idle-study.md): 80 of 84 pickups came within the first 9 hovers, and
    1,180 of the 1,379 loot-step seconds came after the step's last pickup.
  - Batt's 18:12:56 clip shows ~10 s of hovers after the last pickup.
- **Its estimate (offline, before any run):** +14 kills / h (pooled c5b-c8: 88.7 -> 102.7), and
  4 of 113 pickups lost.

**The block:**
- Starts at D9 (>= 20:52:45). Amendment E's clock as before: runs at D9, D9 + 38, D9 + 76, then
  the next cycle.
- **Arms:** T = `--loot trim` and V = `--loot v1`, alternated T, V, T, V.
  - Seeds 25552-25555, 36 min each, at least 2 pairs (4 runs, across two cycles).
- **Everything else is held constant:**
  - strategy P2 (the default), Batt's loop, `--walk-trust --npc-guard`;
  - base dungeon@8.4 with the map_zones fix;
  - **the cue as c9-c11's verdict leaves it** (Amendment Y's rule): on in both arms if adopted,
    off in both if not. This is recorded in the block's first run_start.
- **Primary:** kills / h from packets, pooled T against pooled V. **Bar: T - V >= +8.**
- **Secondary:**
  - loot-step seconds per kill (time_budget idle_loot_pause + loot): T <= 3.5, against ~8.5;
  - floor-loot completeness: T within 8 points of V;
  - items / h and value / h at OC: T not lower;
  - damage per kill and potions + wings / h: T at most +10 %.
- **Hard bars as always.** A `stock_out` end counts over its own window.
- **Known confound, equal for both arms:** the round-2 training (gef10-detector.md 13u) may run on
  the GPU / CPU during the block, if its cache builds at 20:05. Its load is noted per run.

## Amendment AA (2026-10-26 20:01 ICT from `date`): c10 DIED after its time box; dungeon@8.5, a safe end; c11 runs 8.5

**c10** (P2, seed 25550), 19:20:56-19:57:58: the full 36 min, ended by its time box.
- **Inside the judged window:** 78.3 kills / h (47), 0 deaths, HP low 357 (16.6 %).
- **It then DIED 0.96 s AFTER `run_end`.** The judge's window (run_start..run_end) does not count
  it. The packets:
  - In its last ~3 s, about ten orcs hit it. HP fell 907 -> 357 within 0.42 s (-1.24 .. -0.82 s).
  - At 0 the time box ended the loop. From then on the runner stopped reacting: no Fly Wing, no
    potion.
  - The end path typed the end @warp (~7 s through the identity check).
  - At +0.96 s HP read 1, with base experience lost: the death.
  - At +7.34 s the GM warp moved it to prt_fild08 with HP 2.
  - The next pre-run frame showed the "Base Experience has lost" line. That is how it was caught.
- **c10's row therefore says "1 death after the time box".** Every report shows it.
- **Earlier runs: re-checked from packets after run_end (20:04).** c10 is the ONLY death after a
  time box.
  - b1, c4, c5b, c6, c7, c8 and c9 have the end warp inside their banked tails (6.9-11.2 s). Their
    minimum HP after run_end was 952-1811, with no experience lost.
  - c1 and c3 had short rebuilt tails, so 30 s were pulled from the sniffer archive: minimum HP
    1713 and 1128, experience only rising, then the warp to prt_fild08.
  - c5's death was in-run and is already counted (it ended that run).

**dungeon@8.5, a safe end** (`end_escape_needed`):
- **The rule.** When a run ends, a Fly Wing goes first, then the end warp, if all of these hold:
  - the reason is not a death and not a hard bar (an unknown UI state gets no key);
  - and one of: a hit within 3.5 s, an HP fall (`hp_dropped`), or the last HP share read under
    50 %.
- It is logged as `end_escape`.
- **Outside the measured window**, so no measured number changes. c11 runs 8.5. Its
  pre-registration (Amendment Y) is otherwise unchanged.
- **Checks:** census and safety tests green; a unit test on c10's numbers.

## Amendment AB (2026-10-26 20:40 ICT from `date`): c9-c11 judged; THE MISS CUE (9.1b) IS ADOPTED; the d-block runs with it

| run | arm | base | kills / h | potions + wings / h | damage / cycle | reaction mean (median) | items / h | value / h at OC |
|---|---|---|---|---|---|---|---|---|
| c5b | P2 | 8.3 | 96.6 | 20.0 + 10.0 | 126 | 8.53 (8.40) | 81.6 | 31,445 |
| c7 | P2 | 8.3 | 75.0 | 28.3 + 16.7 | 207 | 8.84 (8.65) | 98.3 | 24,352 |
| c10 | P2 | 8.4 | 78.3 (+1 death after the time box) | 28.3 + 13.3 | 198 | 10.02 (11.69) | 91.6 | 27,823 |
| c8 | P2 + 9.1b | 8.3 | 81.7 | 16.7 + 10.0 | 168 | 7.73 (6.56) | 78.3 | 24,490 |
| c9 | P2 + 9.1b | 8.4 | 100.0 | 16.7 + 10.0 | 117 | 7.94 (6.90) | 126.6 | 37,925 |
| c11 | P2 + 9.1b | 8.5 | 103.2 | 21.7 + 11.7 | 124 | 7.13 (6.01) | 116.6 | 40,506 |

**Pooled** (3 runs each, 108 min each arm):

| measure | P2 | P2 + 9.1b | change |
|---|---|---|---|
| kills / h | 83.3 | 95.0 | +14 % |
| potions + wings / h | 38.9 | 28.9 | -26 % |
| reaction when attacked first, mean | 9.08 s | 7.59 s | -16 % |
| damage per kill cycle, kill-weighted | ~173 | ~134 | -23 % |
| items / h | 90.6 | 107.2 | +18 % |

- **Amendment Y's rule** was: adopted only if reaction AND consumables improve with kills / h not
  lower. All three hold. **The cue (`--miss-cue`, rule 9.1b) is ADOPTED.**
- Amendment V's prediction of damage -20 % or more holds pooled (-23 %). It had failed on c8 alone.
- **The cue's honesty:** 0 false fires in 441 onsets (c6, c8, c9, c11); 0 loop engages under 9.1b.
- **Base and caveats:**
  - c5b, c7 and c8 ran 8.3: 10 Fly Wings, no stock guard. c7 hunted its last 7.5 min with none.
    c9 and c10 ran 8.4, c11 ran 8.5 (the safe end, outside the window).
  - On the 8.4+ runs alone, the cue arm also leads: c9 100.0 and c11 103.2 against c10's 78.3.
  - The per-run spread is large (75.0-103.2 kills / h).

**The d-block (Amendment Z), as its rule fixes it:**
- the cue ON in both arms (`cue-d` = `--miss-cue`);
- `--loot trim` merged at b60115c, OFF by default, chosen per run;
- d1 (T) at >= 20:52:45, then d2 (V), d3 (T), d4 (V), on Amendment E's clock.
- **The round-2 cache resume** (gef10-detector.md 13w) started at 20:39:19, right after c11. Its
  CPU / NAS load overlaps the d-block, alternated T / V.

## Amendment AC (2026-10-26 21:12 ICT from `date`): Batt's decisions of ~20:5x; the level hold; the night until 07:00

**Batt's decisions (in chat, after the 20:5x report):**
1. **Cache and training: option (a).** After an IO-guard trip, wait for measured quiet minutes and
   resume, up to a cap he asked me to set:
   - **the cache:** `scripts/runbooks/cache-resume.sh`, `MAX_RESUMES=12`, `QUIET_MIN=10`.
   - **the training:** `train-day.sh` with `IO_RESUMES=20 IO_QUIET_MIN=10`. The defaults stay 3
     resumes and a fixed 15-min pause.
   - **Why these caps:**
     - each resume first needs a MEASURED 10-min quiet window (quiet_start.py: no second of any
       capture cgroup above 25 %), so the resume rate limits itself;
     - the cache's remaining work is about an hour, and 12 resumes cover a trip rate like today's
       recorders' (10 of 11 tripped within 1-36 min);
     - training runs all night at the duty cycle, and 20 covers ~10 h at a trip every ~30 min;
     - hitting a cap PAUSES the job (exit 3) for the morning report. It never loops on.
   - **Unchanged:** the market-open windows (no start or resume 09:30-10:15 / 14:00-14:45 on
     weekdays), R1-R3, the duty cycle, verified stops.
2. **The Rogue is HELD at Base 63** ("ค้างไว้ที่ 63"). It levelled 62 -> 63 by hunting during c11
   (the packets' `base_level`).
   - The setup reads the DB level and types `@baselevelup -N` if it is above 63. The command takes
     back that level's (unspent) status points and zeroes the EXP. It never raises a level.
   - The DB lags the server by up to one autosave, so a level-up in a run's last minutes is undone
     at the next setup after that.
   - The char conf now carries Base 63's max HP / SP: 2209 / 341.
     - It feeds the HP-per-second of the swarm rule. **d1 ran with 2146**, about 3 % under; d2
       onwards run with 2209. Recorded as a small T / V asymmetry inside the d-block.
     - The judge already takes max HP from the packets.
   - `run_start` records `level_db` and `level_hold`.
3. **Continuous work tonight until 07:00; the report in the morning.**

**The night's plan** (each version pre-registered before its run, as always):
- The hunts on Amendment E's clock:
  - the d-block (loot trim T / V: d2 >= 21:31:43, d3 >= 22:09:43, d4 in the next cycle);
  - then the runner-ups of the idle study, each its own version: longer walk legs, and the patrol
    dead-end fix.
- **The round-2 cache**, then the training, under option (a). Both are chained, and quiet_start
  gates the first attempt.
- **The staged-items session (E3)** between two cycles, if the hunts leave a slot. Its icon cut
  and immune frames are judged on screenshots, as every pre-run frame is.
- A report at ~07:00.

## Amendment AD (2026-10-26 21:34 ICT from `date`): the LONG WALK LEGS block, pre-registered (gef10-idle-study.md 6.1)

**The change** (OFF by default; both runner options are in 0b84336 + 39177a5):
- `--walk-ahead 12`: the walk click aims 12 path cells ahead instead of 7.
- `--walk-through`: a patrol leg continues along the route to the NEXT waypoint, so the click is
  not capped at the current one.
  - The waypoint is marked passed once it is behind us on the path, or when the leg's end is
    reached.
- **Why (the idle study):**
  - idle inside search is 6.7 s per kill, 82 % of it the walk's stop-and-go;
  - 52-56 % of the clicks were capped at the waypoint;
  - the Rogue stood a median ~0.4 s after nearly every click (1,679 stops in c5b-c7).
- **Its estimate (offline, before any run):** +3 cells gives +8.1 kills / h, +5 gives +11.1.
- **The safety of the walk is unchanged:**
  - the same walk_target `fits` (in view, no zone segment crossed: the axis-aligned fix included);
  - walk-trust's landing cells and NPC distance;
  - SWORD engages and NO-ENTRY carves as before;
  - no new click path. Click census and safety tests are green.
- **The offline check, `scripts/patrol_sim.py`** (committed, 16bc65e): the runner's own route /
  through_path / walk_target on gef_fild10's loop, its patrol logic mirrored.
  - Its first run FOUND A BUG: a through-leg that ended near its end replanned back to the waypoint
    it had run through, and the walk oscillated at waypoint 64. Fixed in 39177a5.
  - Every case (2-10 cells per decision) now finishes 2 laps with all 159 waypoint events in order,
    with fewer clicks: 186 against 276 at 10 cells.

**The block** (after the d-block's last run, d4):
- **Arms:** L = `--walk-ahead 12 --walk-through` and V = the defaults, alternated L, V, L, V.
  - Seeds 25556-25559, 36 min each, Amendment E's clock.
- **Held constant:** P2, the cue ON (Amendment AB), the level hold at 63, base dungeon@8.5.
  - The LOOT as the d-block's verdict leaves it: `--loot trim` in both arms if it passes Amendment
    Z's bar, `--loot v1` in both if not. Recorded in the first L run's run_start.
- **Primary:** kills / h from packets, pooled L against pooled V. **Bar: L - V >= +6.**
  - That is about half the estimate, because the walk's share shrinks once the loot is trimmed.
- **Secondary:**
  - idle_inside_search s / kill: L lower;
  - walk clicks per kill: L lower;
  - search_walk s / kill: not higher;
  - hard bars and NPC-guard refusals: not more;
  - damage / kill and consumables / h: at most +10 %.
- **Abort rule:** a patrol that stands > 60 s or logs a reached-waypoint order break in the live
  events ends the arm's run as a fault, reported as such.

## Amendment AE (2026-10-26 23:43 ICT from `date`): the d-block judged -- THE LOOT TRIM PASSES; the walk block uses it

| run | arm | kills / h | loot-step s / kill | floor loot | items / h | value / h at OC |
|---|---|---|---|---|---|---|
| d1 | T | 134.7 | 2.67 | 80.7 % | 149.7 | 43,289 |
| d2 | V | 78.3 | 8.10 | 88.2 % | 96.7 | 29,108 |
| d3 | T | 109.9 | 3.22 | 81.3 % | 123.2 | 36,683 |
| d4 | V | 119.9 (72 kills) | 6.60 | 87.0 % | 141.6 | 40,512 |

**Pooled** (2 runs per arm, 72 min each):

| measure | T (trim) | V (v1) | bar (Amendment Z) | met? |
|---|---|---|---|---|
| **kills / h (primary)** | **122.3** | 99.1 | T - V >= +8 | **yes, +23.2** |
| loot-step s / kill | 2.92 | 7.19 | T <= 3.5 | yes |
| floor-loot completeness | 80.9 % | 87.5 % | within 8 points | yes (-6.6) |
| items / h | 136.5 | 119.1 | not lower | yes |
| value / h at OC | 39,988 | 34,811 | not lower | yes |
| damage per kill cycle | 109.0 | 106.3 | at most +10 % | yes (+2.5 %) |
| potions + wings / h | 27.5 | 23.3 | at most +10 % | **NO, +18 %** |

- **One secondary bar fails as written.** Consumables per HOUR rose 18 %, because T fights more per
  hour. Per kill they FELL about 4 % (0.225 against 0.235). This is reported as a failed
  secondary, not re-read. A per-hour bar on a cost that scales with kills was a poor choice; future
  pre-registrations state consumables per kill.
- **The primary passes,** so Amendment AD's rule puts `--loot trim` in BOTH arms of the walk block
  (`loot-e` = `--loot trim`).
- **Ends:** no death after any time box. d3's end_escape fired, and the Fly Wing went first. d4's
  minimum HP after its end was 1438.
- **The clock:** D10 = d4's setup @killmonster2 at 23:05:28. e1 (L) >= 23:43:28, e2 (V) >= 00:21:28,
  both ending by 01:05:28. D11 >= 01:16:28.

## Amendment AF (2026-10-27 01:18 ICT from `date`): the WALK TIMER block, pre-registered (gef10-idle-study.md 4a)

**The change:** `--walk-every 0.8` (3256250; OFF by default, 1.2 s).
- The walk decision fires every `walk_every` seconds, counted from the previous decision's START.
- **Why (the idle study):** one decision takes ~0.9 s (a ~0.4 s cursor read, then a ~0.5 s paced
  click). The 5-6 cell path takes ~0.9 s. So at 1.2 s the Rogue stands ~0.3-0.4 s before nearly
  every click: 1,679 stops.
- At 0.8 s the next decision begins as soon as the last one ends, so its click lands while the
  path is still being walked.
- Same clicks, same checks (fits, walk-trust, SWORD, NO-ENTRY, NPC guard), no new click path.

**The block:**
- D11 = e3's setup @killmonster2 at 01:17:13. f1 starts in D11's third slot (>= 02:33:13).
- D12 (>= 03:28:13) holds f2, f3, f4.
- **Arms:** F = `--walk-every 0.8` and V = 1.2, alternated F, V, F, V. Seeds 25560-25563.
- **The base:**
  - P2, the cue, `--loot trim`, the level hold, dungeon@8.5;
  - the patrol dead-end fix (c6f3e07, merged after e4, before f1);
  - **the walk legs as the e-block's verdict leaves them** (Amendment AD): L in both arms if it
    passes AD's bar, the defaults if not.
- **Primary:** kills / h from packets, pooled F against pooled V. **Bar: F - V >= +6.**
- **Secondary:**
  - idle_inside_search s / kill: F lower;
  - walk clicks per kill;
  - search_walk s / kill: not higher;
  - hard bars and NPC-guard refusals: not more;
  - damage per kill cycle and potions + Fly Wings PER KILL: at most +10 % (per kill, Amendment AE's
    lesson).
- **After f4:** D13 (~05:39) holds ONE confirmation run of the night's best configuration. It is a
  measurement, not part of any comparison. Then the morning report.

## Amendment AG (2026-10-27 02:34 ICT from `date`): the e-block judged -- THE LONG WALK LEGS FAIL; the walk-timer block runs on the default legs

| run | arm | kills (packets) | kills / h | walk clicks / kill | min HP after the time box |
|---|---|---|---|---|---|
| e1 | L | 58 | 96.6 | 14.2 | 1041 (end_escape) |
| e2 | V | 66 | 110.0 | 11.1 | 1273 |
| e3 | L | 59 | 98.3 | 15.3 | 1000 (end_escape) |
| e4 | V | 54 | 90.0 | 16.4 | 1097 |

**Pooled** (Amendment AD's bars):

| measure | L | V | bar | met? |
|---|---|---|---|---|
| **kills / h (primary)** | 97.5 | 100.0 | L - V >= +6 | **NO, -2.5** |
| idle_inside_search s / kill | 5.31 | 7.59 | L lower | yes |
| walk clicks / kill | 14.7 | 13.5 | L lower | no |
| search_walk s / kill | 14.44 | 10.78 | not higher | **no** |
| hard bars / NPC-guard refusals | 0 / 0 | 0 / 0 | not more | yes |
| damage per kill cycle | 109.5 | 120.5 | at most +10 % | yes |

- **Not adopted.**
  - The legs did what they were built for: less standing inside the search (5.31 against 7.59 s
    per kill).
  - The bot walked more per kill instead (14.44 against 10.78 s).
- **A mechanism was considered:** the blind bot meets monsters when they catch it, and slower orcs
  never catch a bot that keeps walking (Batt's 18:12:40 clip). The engage sources do NOT show it
  clearly: e1 had the most monster-started fights per hour (114.9) and e3 the fewest (68.3). Spawn
  variance dominates at this sample size, so it is NOT recorded as a prediction.
- **The same configuration varies across the night.** Trim + cue + default legs gave d1 134.7,
  d3 109.9, e2 110.0 and e4 90.0 kills / h.
- **The f-block (Amendment AF)** therefore runs on the DEFAULT legs (`legs-f` empty). The
  patrol dead-end fix is merged in its base (0047135, 02:34).

## Amendment AH (2026-10-27 05:24 ICT from `date`): the f-block judged -- THE WALK TIMER FAILS; the confirmation run

| run | arm | kills (packets) | kills / h | walk clicks / kill | potions + wings / kill | min HP after the time box |
|---|---|---|---|---|---|---|
| f1 | F | 63 | 105.0 | 14.3 | 0.460 | 1230 (one dead-end fly, the c7 pocket) |
| f2 | V | 65 | 108.3 | 12.6 | 0.277 | 1074 (end_escape) |
| f3 | F | 70 | 116.6 | 13.6 | 0.300 | 1263 (one dead-end fly) |
| f4 | V | 72 | 120.0 | 11.1 | 0.347 | 1178 |

**Pooled** (Amendment AF's bars):

| measure | F (0.8 s) | V (1.2 s) | bar | met? |
|---|---|---|---|---|
| **kills / h (primary)** | 110.8 | 114.1 | F - V >= +6 | **NO, -3.3** |
| idle_inside_search s / kill | 4.67 | 5.39 | F lower | yes |
| walk clicks / kill | 13.9 | 11.8 | -- | higher |
| search_walk s / kill | 10.65 | 9.62 | not higher | **no** |
| damage per kill cycle | 134.0 | 110.6 | at most +10 % | **no, +21 %** |
| potions + wings per kill | 0.376 | 0.314 | at most +10 % | **no, +20 %** |
| hard bars / NPC-guard refusals | 0 / 0 | 0 / 0 | not more | yes |

- **Not adopted.**
- This is the SECOND "stand less" change to fail the same way (AG's long legs were the first). Each
  cut standing inside the search as built, and the bot then walked more per kill and took more
  damage. **The walk's stop-and-go is no longer the binding loss.**
- What remains is SIGHT:
  - approach_react 3.9 s / kill, and search_walk, against Batt (the 00:3x ranking on d1 / d3);
  - Batt's 18:12:40 clip;
  - the walk hover's 1-2 `walk_sword` finds per run.
  That is round 2's detector and the chaser rule (gef10-eyes-loot.md E4 / E6).
- **The patrol dead-end fix works live:** f1 and f3 each hit the c7 pocket (153,309) and flew after
  one lap of route-less skips, instead of standing ~45 s.
- **The night's best configuration** (P2, the 9.1b cue, `--loot trim`, the default walk, dungeon@8.5
  + the dead-end fix) pooled over d1, d3, e2, e4, f2 and f4: **404 kills in 3.6 h = 112.2 kills / h**,
  0 deaths.
- **The confirmation run, g1** (D13 >= 05:39:58, seed 25564): that configuration, 36 min. A
  MEASUREMENT for the morning report, not a comparison.

**Correction to Amendments AG and AH (2026-10-27 05:56 ICT from `date`).** Some per-run rows
printed the RUNNER's own kill count (its `kill` events) where the pooled verdicts used the JUDGE's
count from packets. The two differ by 0-4 kills a run.
- **Corrected to the judge's count:**
  - AG: e3 is 59 kills / 98.3 per h (was 61 / 101.7);
  - AH: f1 63, f2 65, f4 72 (were 66, 69, 73).
- **Recomputed with the judge's counts:** the per-kill ratios (walk clicks; potions + wings, which
  are now also the judge's packet counts). Pooled potions + wings per kill: F 0.376 against V
  0.314, +20 % (was +23 %).
- **No verdict changes.** The pooled kills / h always used the judge.

## Amendment AI (2026-10-27 06:33 ICT from `date`): the confirmation run; g1's fault stop; the level held again

- **g1** (05:50:33-05:52:34) **stopped fail-closed after ~1.2 min: "no input_ack within 3 s"**.
  - The end path ran: the warp home at 05:52:30.
  - The backend was healthy right after: ASSIST, no bot agents, no input refusals.
  - The likely cause is my own. A guarded `measure:du` of `data/` (05:52:24-35, ~424 MB of files)
    walked the shared disk while quant-postgres was stalling it, and the backend's input path
    (its input log append) waited.
  - **Rule kept from now on: no disk measurement while a run is live.**
  - g1 is a fault, not a result.
- **g1b** (seed 25565; setup @killmonster2 05:55:25, inside D13 = 05:51:16): the night's best
  configuration (P2, the 9.1b cue, `--loot trim`, the default walk, dungeon@8.5 + the dead-end fix),
  36 min:
  - **80 kills, 133.3 kills / h**, 0 deaths, HP low 30.9 %;
  - 16 potions and 4 Fly Wings;
  - 74 items (123.3 / h: Cyfar 65.0, Orcish Voucher 45.0, Iron 6.7, Large Jellopy 3.3, Stem 1.7,
    Sticky Mucus 1.7);
  - **37,289 z / h at OC**, floor loot 89.7 %;
  - minimum HP after the time box 1276.
- **The best configuration over its 7 runs** (d1, d3, e2, e4, f2, f4, g1b): **484 kills in 4.2 h =
  115.2 kills / h**, 0 deaths. Batt's demo is 232.7 kills / h.
- **The level hold, applied at the end.** g1b levelled the Rogue to Base 64 (HP 2272). There is no
  next setup to undo it, so the hold's own line (`@baselevelup -1`, then `@heal`) was typed at
  06:33 through the identity check.
  - The final frame shows Base 63, HP 2209 / 2209, SP 341 / 341, EXP 0, on the prt_fild08 stand.
  - A client "up" icon (unspent status points) now shows at the lower right. The next pre-run
    judges it against the UI gate.

## Amendment AJ (2026-10-28 13:32 ICT from `date`): Batt's decisions of 2026-10-28 ~13:2x -- recorders on RAM use the sustained IO rule; fit-first may share the GPU; /dev/shm cleaned

- **The recorders (Batt: "use the new rule").** `record_session.py` (recorder v6) now picks its IO
  rule from where it writes.
  - A tmpfs sink (`--out /dev/shm/poring-lab-rec`, as every hunt run uses) stops only on 30 s of
    stall above 30 % (`RAM_RULE`). It puts nothing on the disk shared with capture.
  - Any other sink keeps the tolerant one-spike rule (`DISK_RULE`). The default sink,
    `/home/batt/poring-lab-rec`, is the root disk.
  - Each manifest records the rule as `guard_rule`.
  - Why: 10 of the 11 hunt recorders of 10-26 were cut short by the host's own 1-5 s bursts
    (gef10-detector.md 13x, 13y).
  - This unblocks the staged-items session (approved, 68590b9) and round 3's frames.
  - **Not changed:** `dataset_ship.py`'s guard. A ship reads RAM and writes the NAS, but Batt's
    decision named the recorders only; the e4 / f3 ships wait for a quiet moment as before.
- **fit-first (Batt: "top priority now; never touch or stop it; co-running is allowed").** The
  training may share the GPU with fit-first's VTON worker. The R2 exception and its protections
  are in gef10-detector.md 13z.
- **/dev/shm (Batt: "please do it").** The two rm commands of the 10-27 morning report ran at
  ~13:3x, after a fresh `rsync --dry-run --itemize-changes` comparison found every file identical
  on the NAS:
  - the 78 demo sessions (`scratch-archive/2026-10-26|27/demo-sessions/`);
  - `poring-lab-tmp/shots` (69 files, `scratch-archive/2026-10-27/shots/`), re-created empty.
  - `.ship.lock` was kept. /dev/shm went from 6.6 G to 5.9 G used.

## Amendment AK (2026-10-28 14:55 ICT from `date`): the staged-items session (E3) starts, pre-registered -- Batt: "start now"

Batt's go came at ~14:5x ("เริ่มได้เลย"). The plan is `gef10-eyes-loot.md` E3 (approved 2026-10-26,
decision 2 above; the recorders' sustained IO rule since Amendment AJ). Nothing in the plan's
recipe changes except the two points marked CHANGED, which today's state forces.

**Beside it:** the gef10 detector training (gef10-detector.md 13z) on the GPU, and fit-first's VTON
worker (never touched). This session uses no GPU. No hunt cycle is scheduled.

**State at 14:52 (judged screenshot `shots/e3-pre-0.png`):** the Rogue Thief8fce on the prt_fild08
stand (268,107), HP/SP full, weight 703 / 2430, no dialog or menu open; capture lock rdp, steady.
`stage_items.py held --map gef_fild10` refuses (rc 1): the bag holds hunt loot of the set
(Cyfar 42, Orcish Voucher 27, Iron 4, Large Jellopy 2, Sticky Mucus 1).

**A. The icon set** (prt_fild08 stand, no immunity), as the plan:
1. The store step (`@storage` through the identity check + a judged frame, then `store_run4.py`'s
   path, `gm_state.store_loot`). Then `held --map gef_fild10` must return rc 0 (an empty store
   step first if the DB has not saved).
2. `give --map gef_fild10 --frames` (11 `@item` lines; one frame per inventory tab).
3. Frames judged, the SPEC written, `cut ... --map gef_fild10` (its clash bars refuse a cut too
   near the stock or another icon).
4. `drop --map gef_fild10`: rc 0 (`all_and_only_the_set`) is the icon set's positive case; rc 1
   stops the session for a re-cut.
5. An empty store step (the DB catches up); `held` rc 0.

**B. The session**, as the plan:
6. The canopy: `canopy --map gef_fild10`; it must give 67,533 cells, sha256 `1c0aa910...bc0d1`,
   else stop.
7. **CHANGED: immunity by the toggle, judged, instead of a fresh login.** `immune-on` types
   `@monsterignore` (a toggle). Its frame must show "You are now immune to attacks." over the
   character (w2's proven frame, `gef10-ow/immune-on-w2.png`). If it shows "Returned to normal
   state.", it is typed once more and judged again. The run starts only with `--immune-confirmed`
   after that judgement.
8. The recorder (`record_session.py --backend rdp --label stage-gef10-e3 --seconds 3300 --fps 1
   --format png --out /dev/shm/poring-lab-rec --max-bytes 8G --min-free-gb 6
   --max-unshipped-gb 12`; recorder v6, tmpfs -> RAM_RULE), then `run --map gef_fild10 --n 22
   --seed 2610 --open <canopy> --immune-confirmed --label e3` (`--clear end`: the @killmonster2
   pair 65 s apart). The recorder stops by PID >= 65 s after the run's last line.
   - Unshipped beside it: e4 2.0 G + f3 1.9 G; this one ~6.3 G: 10.2 G < 12 G.
9. **CHANGED: immunity off by the toggle, judged** ("Returned to normal state.", w2's
   `immune-off-w2.png`), instead of a relog; then the character back to the prt_fild08 stand
   (268,107) and a judged frame.
   - The first end kill kills the natural Orc Lord if alive: `killmonster2_ict[0]` is the next
     cycle's D.
10. The ship waits for the end of SET hours (`dataset_ship` refuses), with e4 and f3 (after 17:00).

**Stops:** any `r.Stop` (identity, UI gate, a settle timeout), a wrong drop (`names != want`), an
NPC contact or a map change other than our own `@warp`s. A human lease stops it as designed.

**Offline, after (from the packets, the plan's step 10 + safety):**
- the staged floor ids that vanished before 60.0 s (looted), that they fell again at the first
  end kill, and no early vanish after the second kill's falls;
- npc_contact 0, attack_request 0, every map change one of our `@warp`s;
- labels per class (target >= 40 labels from >= 10 floor items per class) by `item_labels.py`.

**What it measures:** floor-item labels for round 3 (E5). It is not a scored run and has no
verdict; staged items are never income.

### AK-1 (15:06 ICT from `date`): the icon set's positive case failed on the Axe -- a test-procedure artifact; repeated under the run's conditions

- Done so far: the store step (6 Etc stacks, weight 703 -> 610; `held` rc 0); `give --frames`
  (11 lines, 14:57:53-14:58:41); the icons identified by the client's OWN item icons (the Thai
  GRF's `texture/.../item/*.bmp`, extracted to /dev/shm, never committed: every slot's best match
  3.9-20, the runner-up >= 44.9; by eye Iron and Large Jellopy had been swapped); `cut` wrote 11
  icons, no clash.
- `drop` returned rc 1 at 15:03:58: the 10 Etc / Use items dropped, the Axe (Eqp) did not.
- **Cause (read from a diagnostic frame of the three tabs, `_bank_tabs`, nothing moved):** the
  icons were cut with the client's pink new-item glow under them. Viewing the Eqp tab in
  `give --frames` cleared the Axe's glow, so the same Axe now reads 3.11 against the 3.0 bar
  (the cut frame 0.0). A run's items are always fresh: given with the inventory closed, then
  `clear_loot`'s first view, as the 10 that passed.
- **Not a re-cut.** The positive case is repeated under the run's own conditions: the stale Axe
  goes to storage (the store step), `held` rc 0, then `give --map gef_fild10` WITHOUT `--frames`
  and `drop --map gef_fild10`. rc 0 continues the plan; rc 1 stops the session and asks Batt.

### AK-2 (15:58 ICT from `date`): the session stopped at spot 18 by design; a carrier is left -- the plan's extra @killmonster2, pre-registered

- `run` rc 1 at 15:50:33: spots 0-17 complete; at spot 18 (89,121) `clear_loot` dropped 4 of the
  6 (Cyfar and Orcish Voucher read 3.07 / 3.29 against the 3.0 bar on the recorded frames: the cut
  icons carry the slot background and its new-item glow, so a correct item's distance moves with
  its neighbours). The run then typed the end pair (15:49:15, 15:50:28) as designed. Recorder:
  2,227 frames, 5.0 GB, stopped by signal 15:51:46.
- Afterwards: `@warp prt_fild08 268 107` while still immune, immunity OFF there (judged:
  "Returned to normal state."), the two staged copies (Cyfar 1, Voucher 1) to storage by the store
  step, `held` rc 0, weight 610 (judged frame).
- **Packets (loot_truth.py):** 112 staged falls (9-11 per class); 16 vanished before 60 s (spots
  14, 15, 18); spot 18's four items were looted AFTER the first end kill, fell again at the second
  (15:50:28 + 0.1 s) and vanished again 7-9 s later. So a Poporing most likely carries Garlet,
  Nursing Bottle, Milk and Green Herb (the plan's step 10 case).
- **The cleanup, pre-registered (the plan's step 10):** immunity ON (judged), `@warp gef_fild10
  89 121` (spot 18, vetted), a 3-min 1-fps recorder for the packets, `@killmonster2`, 70 s, then
  check that the falls lived 60 s. An early vanish again -> one more `@killmonster2` >= 60 s
  later, at most two in all; then back to the stand, immunity OFF (judged), and report. The first
  extra kill's ICT time is recorded; the Orc Lord's D stays 15:49:15 unless a respawned Lord dies.

### AK-3 (16:09 ICT from `date`): E3 result -- 18 of 22 spots, 112 staged floor items (9-11 per class); the extra kill unobservable; state restored

**Yield** (`loot_truth.py` on the session's packets; staged falls before the first end kill):

| class | falls | class | falls | class | falls |
|---|---|---|---|---|---|
| Axe | 10 | Iron | 10 | Orcish Voucher | 10 |
| Cyfar | **9** | Large Jellopy | 10 | Rough Oridecon | 10 |
| Garlet | 11 | Milk | 11 | Sticky Mucus | 10 |
| Green Herb | 10 | Nursing Bottle | 11 | total | 112 |

- The plan's target was >= 10 floor items per class: 10 of 11 classes meet it; Cyfar has 9.
- Fates of the 112: 64 lived ~60 s in sight; 32 had no vanish seen (we warped on first); 16
  vanished before 60 s (looted): spot 14 all six at 20.0-43.8 s, spot 15 all six at 0.8-4.2 s,
  spot 18 four at 24.1-39.9 s.
- The end pair: spot 18's four were looted AFTER the first kill (a Poporing respawns 5 s after
  it), fell at the second kill and vanished again 7.1-8.9 s later.
- **The extra `@killmonster2` (AK-2) at 16:00:20 ICT** from (89,121), immune, with a 3-min
  recorder (`20261028T160008-rdp-stage-gef10-e3x`, 173 frames): no monster died in sight and no
  item fell in sight. Whether it reached the carrier is NOT observable from one spot (sight
  ~14 cells). **Residual:** a Poporing on gef_fild10 may still carry <= 4 staged items (Garlet,
  Nursing Bottle, Milk, Green Herb). Each hunt cycle's setup `@killmonster2` (A4) makes such a
  carrier drop them again; `dungeon_judge` cannot flag this set (its staged rule knows
  pay_fild07's ids only).
- **Labels are not made today.** `item_labels.py` covers prt_fild08 / orcsdun01 only, and the
  at-our-feet rule is E5's pre-registration decision (gef10-eyes-loot.md E5). The frames and
  packets are the input for it.

**Safety, from the sniffer's events in the session's window (`packets.jsonl.gz`, keyed by
`type`):** `npc_contact` 0, `attack_request` 0, `act` 0; `map_change` 55 = our 55 `@warp`
targets, in order, all on gef_fild10, all `gm_command`. The extra kill's window: 0 / 0 / 0, one
map change.
- Positive control, the same reader on the 10-27 hunt e4: `attack_request` 30, `act` 549.
- No NPC-contact positive case exists for this sniffer start (2026-10-25 19:09 ICT, self-test
  code 5af7a1f9da66). That zero rests on the decoder's earlier §2a proofs.
- (A first count keyed on `kind` showed attacks as "repeat" and `attack_request` 0 even for
  e4; recounted by `type`.)

**The stop's cause, for the fix:** `clear_loot`'s icon references carry the slot background
and the client's pink new-item glow. A correct item reads 2.77-3.84 against the 3.0 bar
depending on its slot and neighbours: the Nursing Bottle read 3.84 in slot 3 and 0.41 in slot 2
of the same view. The Axe glow clears once its tab was the one shown when the inventory closed.
Any second session needs a background-free match first (a code change: census + tests +
pre-registration).

**State at 16:04 (judged `rogue/e3x-immune-off.png`):** the Rogue on the prt_fild08 stand
(268,107), immunity OFF, weight 610, HP / SP full, no dialog; `held` rc 0; the two staged
copies (Cyfar 1, Voucher 1) are in storage, not income. The Orc Lord's D for the next cycle:
15:49:15.

**Ship:** after 17:00, chained (e4, f3, e3 5.0 GB, e3x 0.39 GB), one at a time.

## Amendment AK-4 (2026-10-29 10:47 ICT from `date`): Batt's four decisions on E3's open items

Batt, 2026-10-29 ~10:0x (translated), answering AK-3's report section 12:
1. **Shipping: "switch to the sustained rule".** `dataset_ship.py`'s IO guard now follows the
   sessions' root like a recorder: on tmpfs it stops only on stall above 30 % for 30 s (RAM_RULE);
   on a disk it keeps the tolerant rule (above 10 % for 30 s, or above 25 % once); unknown = disk.
   The rule now lives in `dataset_ship.py` (`DISK_RULE`, `RAM_RULE`, `fs_type`, `guard_rule`);
   `record_session.py` re-binds the same objects. `ship` prints the rule it uses. Tests: the rule
   by root, `load_guard`'s built Guard, `cmd_ship` passing its root, and the positive and negative
   case on a scripted cgroup: 10-28's single 29.0 % quant-postgres second (which cut the e4 ship at
   17:04:54) trips the disk rule and not the RAM rule; 30 s above 30 % trips the RAM rule.
   - The four sessions (e4, f3, e3, e3x; 9.3 GB) ship after 17:00, one at a time, stopping at
     the first failure (SET hours still refuse).
   - Note (10:3x incident, gef10-detector.md 13z-4): these /dev/shm sessions sit partly in swap,
     so the ship's read is swap-in IO on the root disk. The guard's sustained rule still stops it.
2. **E3: "fix the icon matcher, then run a short second session".** The fix is pre-registered
   (AK-5) BEFORE any live step: the rule, its bars, the offline check, the census and targeted
   safety tests, then the `give` / `drop` positive case under run conditions, then the session.
3. **Infra (mid.pt to tmpfs; telling the fit-first side about the VTON restart): "leave it, I'll
   handle it".** Nothing is done here.
4. **The /dev/shm rm lines: "please carry them out".** Done 2026-10-29 ~10:0x after a check: the
   43 listed files byte-identical on the NAS (`scratch-archive/2026-10-28/`), the 35 `frames-s18`
   frames byte-identical inside the e3 recording, `icons-grf` re-extractable from the GRF. /dev/shm
   12 G -> 11 G used. Kept: the canopy, `icons-spec.json`, `ship4.sh` / `ship4.log`.

## Amendment AK-5 (2026-10-29 10:59 ICT from `date`): PRE-REGISTERED -- the icon fix (stage@6) and the short second session (e3b)

Batt's decision 2 (AK-4): fix the icon matcher, then run a short second session. This is
recorded BEFORE any live step and before `cut-grf` writes anything. (AK-4's ship timing moved:
the four sessions now ship 2026-10-30 03:05-04:25 ICT, the window home-assistant-ops OS-036
recommends, each first paged back out of swap at 8 MB/s under the quant IO guard. ➡️ SHIPPED
2026-10-30 03:05-03:35 ICT: all five verified on the NAS, local copies deleted.)

**1. The fix (stage@6, code in the same commit as this record, 26abd70; tests below).**
- **Masked references from the client's own item icons:** the Thai GRF's item BMPs (resource
  names from `idnum2itemresnametable.txt`), extracted to /dev/shm (study use, never committed).
  Template = the BMP's grey (gm_state.to_gray's weights); the item = every non-magenta pixel;
  placed at `ICON_BMP_OFFSET` 3 (icon_crop's column c = the BMP's column c - 3, rows aligned:
  the best offset for all 13 icons measured, each runner-up offset >= 17.5 worse). Stored as
  `loot-<name>.npz` (template + item mask) beside the screen-cut `.npy`, which they replace in
  `gm_state.load_loot_refs`.
- **The rule (gm_state.classify_icon):** mean |crop - template| over the item's pixels only;
  a match within `ICON_MATCH_MASKED` 10.0; a second masked reference within `ICON_AMBIGUOUS`
  20.0 makes it "unknown" (never dropped). Plain references keep ICON_MATCH 3.0 exactly, so the
  hunts' loot steps (dungeon_hunt, store_loot) are unchanged.
- **The FIT evidence (2026-10-29, the references at hand; no frame of the E3 recording was read
  under this rule):** each item's screen-cut reference (slot background + glow) reads 1.1-4.4
  against its own template (Green Herb 4.36; ➡️ corrected 10:59 from `date`, first written
  1.1-3.8; `cut-grf`'s own printout); the White Potion 0.9, the Fly Wing 4.8; the nearest DIFFERENT item or
  the empty slot reads >= 30.8. (pay_fild07's `green_etc` reads 3.09 against Sticky Mucus: the
  same icon; it is not in this inventory's stock set.)
- **The write gate (`cut-grf`, refused = nothing written = STOP):** every screen-cut reference
  must classify as its own item through the same classify_icon; every kept / empty stock
  reference (White Potion, Fly Wing, the empty slot) must classify "unknown" and lie beyond 20.0
  of every template; >= 40 item pixels each.
- **Checks done before this record:** the click census + targeted safety tests (click_census,
  dungeon_hunt, gm_state, safety_signal_check, stage_items, stage_items_gef10, stage_items_run,
  ui_gate): 118 passed. New tests: the E3 failure reproduced (background + glow change off the
  item: the plain reference misses, the masked one matches at 2.0), the 10.0 bar both sides, a
  different item and an empty slot "unknown", the ambiguity rule, `.npz` loading, the BMP
  placement, the resname table, every refusal path of the write gate.

**2. The steps, in order (any failure stops and asks Batt):**
1. `cut-grf --map gef_fild10` (offline): its write gate passes, or STOP.
2. A judged screenshot; /health ASSIST with no human lease. `held --map gef_fild10` rc 0.
3. **The positive case under the run's conditions (AK-1):** `give --map gef_fild10` (no
   `--frames`), then `drop --map gef_fild10`: rc 0 (`all_and_only_the_set`: the 11 dropped,
   nothing else). rc 1 STOPS everything. Then an empty store step if the DB lags; `held` rc 0.
4. The canopy: the existing `/dev/shm/.../gef_fild10-canopy.npy`, checked at 10:58: 67,533
   cells, sha256 `1c0aa910...bc0d1` (AK's values).
5. Immunity by the toggle, judged ("You are now immune to attacks."), as AK step 7.
6. The recorder: `record_session.py --backend rdp --label stage-gef10-e3b --seconds 1500 --fps 1
   --format png --out /dev/shm/poring-lab-rec --max-bytes 3G --min-free-gb 6
   --max-unshipped-gb 13`, then **`run --map gef_fild10 --n 6 --seed 2611 --open <canopy>
   --immune-confirmed --label e3b`** (`--clear end`). The plan (offline, 10:5x): spots
   (99,287) (76,100) (299,189) (196,293) (123,171) (256,96); 36 floor items: Cyfar 3, Orcish
   Voucher 4, Sticky Mucus 3, Milk 3, Garlet 3, Iron 3, Large Jellopy 3, Rough Oridecon 3,
   Green Herb 4, Nursing Bottle 3, Axe 4. The recorder stops by PID >= 65 s after the run's last
   line.
7. Immunity off by the toggle, judged; the character back to the prt_fild08 stand (268,107);
   a judged frame. The first end kill's ICT is the Orc Lord's next D.

**Stops (as AK):** any `r.Stop` (identity, UI gate, a settle timeout), a wrong drop
(`names != want`), an NPC contact or a map change other than our own `@warp`s; a human lease.

**Offline, after:** the same readouts as AK-3 from the session's packets (falls per class,
fates, early vanishes and the end pair; npc_contact / attack_request / act keyed by `type`, with
e4 as the positive control; every map change one of our warps). The end pair also makes
yesterday's possible carrier (<= 4 staged items, AK-3) drop them once more.

**Success:** Cyfar >= 10 staged floor items in sight across E3 + e3b (9 + 3 planned) and every
class >= 10; no stop. A stop by the drop check again means the masked rule failed in the field:
report, no retry.

**After the session (diagnostic, not a gate):** once e3 ships (03:05 window), its spot-18 frames
are re-read from the NAS copy under a 4 GB memory cap, to show what the masked rule reads there.
➡️ e3 SHIPPED 2026-10-30 03:05-03:29; this re-read has NOT run (poring-lab paused since 2026-10-29).
- **10:59, step 1 done:** `cut-grf --map gef_fild10` rc 0, 11 masked references written; the
  screen-cut references read cyfar 2.07, orcish_voucher 3.82, sticky_mucus 3.09, milk 1.61,
  garlet 2.56, iron 2.15, large_jellopy 1.40, rough_oridecon 2.77, green_herb 4.36,
  nursing_bottle 1.12, axe 3.47; the stock (fly_wing, slot, white_potion) unknown and beyond 20.0.

### AK-6 (11:26 ICT from `date`): RESULT -- e3b ran clean, 6 of 6 spots, 36 staged floor items; the masked rule dropped 47 of 47 in the field; E3 + e3b reach >= 10 per class (Cyfar 12)

**Timeline (from the tools' own clock lines):**
- 11:01:31-11:02:30 `give --map gef_fild10` (no frames): weight 610 -> 727.
- 11:02:47-11:03:51 **`drop` rc 0: `all_and_only_the_set` true** (the 11 dropped, nothing else;
  `unknown` 126 = every other slot): the masked rule's positive case under the run's conditions.
  A prt_fild08 Poring stood on that drop pile (`stage-drop-gef_fild10.png`): a prt_fild08 looter
  may carry some of these 11 (no prt_fild08 hunt is scheduled; dungeon_judge's staged rule does
  not know these ids).
- `held` rc 1 at 11:04:12 (the DB's last save was mid-drop: 5 of the 11). The empty store step
  (11:04:57 `@storage`, 11:05:20-11:05:39 `store_loot`: stored nothing, kept White Potion and Fly
  Wing) did NOT force a save; the autosave did: `held` rc 0 at 11:07:21.
- 11:07:50 `immune-on`, judged ("You are now immune to attacks.").
- 11:08:11 recorder; 11:08:14-11:21:40 **`run` rc 0, reason "done", 6 spots**, every spot's drop
  check passed (6 x 6 = 36 of 36). End kills 11:20:23 and 11:21:35 (72 s apart). **The Orc Lord's
  next D: 11:20:23.** Recorder `20261029T110813-rdp-stage-gef10-e3b`: 795 frames, 1.77 GB, 943
  packet events, stopped by PID 11:22:53.
- 11:23:22 immunity off ("Returned to normal state.") ON gef_fild10 at spot 5: an Orc Lady was
  beside the Rogue and hit twice (113, 102) before the warp at 11:23:46. **Procedure flaw:** warp
  to the safe stand FIRST, then the toggle (AK step 7 and AK-5 step 7 had it the other way; E3's
  spot 18 had no monster close). 11:24:32 `@heal`.

**Yield** (`loot_truth.py` on the session's packets; deaths in sight 0):

| class | e3b falls | E3 + e3b | class | e3b falls | E3 + e3b |
|---|---|---|---|---|---|
| Axe | 4 | 14 | Milk | 3 | 14 |
| Cyfar | 3 | **12** | Nursing Bottle | 3 | 14 |
| Garlet | 3 | 14 | Orcish Voucher | 4 | 14 |
| Green Herb | 4 | 14 | Rough Oridecon | 3 | 13 |
| Iron | 3 | 13 | Sticky Mucus | 3 | 13 |
| Large Jellopy | 3 | 13 | total | 36 | 148 |

- **Fates of the 36:** 18 lived 60.0 s in sight; 6 had no vanish seen (we warped on first);
  **12 vanished 0.3-6.2 s after their own fall, all of spots 0 (99,287) and 1 (76,100)**: a
  looter stood on the pile (as E3's spot 15). The end pair is map-wide; whether it reached those
  looters is not observable from spot 5 (same caveat as AK-3).
- **Success as pre-registered:** Cyfar >= 10 (12) and every class >= 10 (13-14) in E3 + e3b; no
  stop. Labels per class (the plan's >= 40) are E5's count; the quick-looted items give few frames.

**The masked rule in the field:** 11 (positive case) + 36 (run) = 47 staged items dropped, 0
missed, 0 wrong; the stock (White Potion, Fly Wing) never dropped.

**Safety, from the sniffer's events in the run window (`packets.jsonl.gz`, keyed by `type`):**
`npc_contact` 0, `attack_request` 0, `act` 0; `map_change` 18 = 6 spots x 3 views, all on
gef_fild10 at our warp cells. Positive control, the same reader on e4: `attack_request` 30,
`act` 549. No NPC-contact positive case exists for this sniffer start (AK-3's caveat).

**State at 11:24 (judged `rogue/e3b-healed.png`):** the prt_fild08 stand (268,107), immunity OFF,
HP / SP full, weight 610, no dialog; the DB holds none of the set.

**Ship:** e3b joins the 2026-10-30 03:05-04:25 chain (now five sessions, ~11 GB). ➡️ SHIPPED
2026-10-30 03:30-03:35 ICT (8 files, 1.77 GB); all five on the NAS (disk-audit.md, the pause).
