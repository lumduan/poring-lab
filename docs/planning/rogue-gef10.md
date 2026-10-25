---
doc_type: design
hypothesis: "On gef_fild10 (the lab's pre-renewal server), a Rogue built to Batt's sample at the SAME EFFECT (Base 62 / Job 50: 100 % hit on, and 5 % hit from, every normal species of the map) gains at least as much NPC-sell value per hour (at Overcharge +24 %) WITHOUT a Steal opening (Snatcher Lv 10 steals on its own) as WITH dungeon@7's Steal-first opening, because the opening's casts, SP and rests cost kill time that its extra steals do not repay."
status: "PRE-REGISTERED 2026-10-25 (Batt's decisions 12:3x-13:1x ICT, section 0). Nothing live yet: the map prep, @storage in group 20, the Rogue build, then the pilot and the runs (section 7)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [thief-payon.md, payf07-detector.md, payf07-prep.md, renewal-feasibility.md, ../demonstrations.md, ../../config/map_zones/README.md, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py]
next_action: "The parent: the map prep (a subagent), @storage in group 20, the Rogue build (live), the store step and its first live use, then the pilot and the 8 runs (section 7)."
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

## Amendment E (2026-10-25 22:08 ICT from `date`; after a1's death, BEFORE a2)

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
