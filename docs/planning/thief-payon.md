---
doc_type: design
hypothesis: "A Thief (Base 50 / Job 40, AGI 62 / DEX 40, Damascus + NPC gear) hunting a Payon field by the dungeon runner's walk-and-hit, with Steal Lv 10 tried first on Elder Willow / Bigfoot, yields measurable counts of the high-value items (Dead Branch, Rough Elunium, Rough Oridecon, Honey) per hour, safely (deaths and hard bars counted)."
status: "4.04 RESULT 2026-10-24 (demonstrations 4.04, s1-s6, 240.3 min): 35.7 kills / h, deaths 0, hard bars pass; Steal 56 of 109 tries (Elder Willow 39 / 65); natural target items: Dead Branch 3 + Rough Elunium 1. Second block s7: 30.0 / h, then the 40 % weight stop (42.6 %). Target items round 2 PASSES all four on open ground (target-items.md). The pay_fild07 detector is TRAINING since 2026-10-25 02:56 ICT (payf07-detector.md 13f). Renewal PARKED."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [crusader-orcsdun01.md, item-class.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/crusader.py]
next_action: "Batt: the weight (42.6 %: sell / store / drop non-target loot) before more runs; whether to pre-register a live loot-by-sight version (target-items.md round 2). The parent: watch the detector training (payf07-detector.md 13f; resume at the 12 h step cap) and score it per ../benchmarks/payf07-eval.md."
title: "A Thief (then Rogue) for economics on a Payon field: the decisions, the facts, the build and the plan"
date: 2026-10-24
owner: Batt
---

# A Thief (then Rogue) for economics on a Payon field

## 1. Batt's decisions (2026-10-24 ~09:45, his reply to the overnight report)

- **The Crusader tests end here for now.** orcsdun01 is ended ("quit orcsdun01 and come train at
  pay_fild08"). The Auto Guard recast question is dropped ("not training the Crusader any more").
  The Crusader (slot 2, `Crus4b7e2`) stays as it is.
- **The new job is for ECONOMICS: a Thief now, a Rogue later (Snatcher).** We stop farming junk.
  The targets are high-value items that are vended to players, not sold to NPCs, and don't track
  inflation:
  - Dead Branch, Rough Elunium, Rough Oridecon, Honey.
- **The map:** "collect at pay_fild08". If an Elder Willow or a Bigfoot is met, **use Steal Lv 10
  first** to steal before fighting.
- **Phase 1:** the stats and skills from his calculator screenshots (section 3), and the gear any
  NPC sells, with a Damascus.
- **The item class** is re-registered on this map ("use pay_fild08; this map has many trees").
- **No 6-minute gap** on this map: "practise walking and hitting first".
- **yoyo-lab:** not our concern any more (its questions file is closed).
- **Reports:** add the count of EACH item collected per hour, because some items are never sold
  to an NPC.

## 2. The map: pay_fild08 on THIS server has neither Elder Willow nor Bigfoot

The lab server is pre-renewal (pinned rAthena e985006, `npc/pre-re/mobs/fields/payon.txt`, read
through data/kb). The spawn tables:

| map | spawns (count) | the four target items, by kill drop |
|---|---|---|
| **pay_fild07** | Elder Willow 70, Eggyra 40, Bigfoot 30, Poporing 20, Willow 20, Green Plant 8 | EW: Dead Branch 1 %, Rough Elunium 0.4 %; Bigfoot: Honey 4.5 %, Rough Oridecon 0.43 %; Eggyra: Rough Elunium 0.57 % |
| pay_fild08 | Spore 70, Willow 50, Poring 30, Pupa 20, Green Plant 10, Shining Plant 1 (a ~1 h respawn) | only the Shining Plant: Honey 5 % |
| pay_fild09 | Smokie 80, Bigfoot 70, Poporing 20, Green Plant 10, Shining Plant 1 | Bigfoot only |

- Renewal does not explain the name either: its pay_fild08 is Spore 148, Wormtail 31, Boa 31
  (`npc/re/mobs/fields/payon.txt` at the same ref).
- **Default: pay_fild07**, the only map with both of his steal targets and all four items.
  Batt was told at 10:0x; his answer overrides this default.
- pay_fild07 has 4 edge warps (to pay_fild01, pay_fild03, pay_fild08, pay_fild10) and no script NPC
  in the KB's warp list. Its NPC cells, the client / server walkability agreement and the client
  GAT are prepared in section 5.

## 3. The Thief (Batt's screenshots), checked against the pinned server files

- **Job:** Thief, Base 50.
- **Skills (39 points = Job 40):** Double Attack 10, Increase Dodge 10, Steal 10, Hiding 1,
  Envenom 7, Detoxify 1. The quest-skill rows are cut off in the screenshot and are not granted.
  - Job 40 is also the minimum for the Rogue change.
  - Plus Basic Skill 9 (the Novice's 9 job levels).
- **Stats:** STR 1, AGI 62, VIT 1, INT 1, DEX 40, LUK 1.
  - The server's `db/pre-re/statpoint.yml` gives 420 points at Base 50; these stats cost 413
    (AGI 1→62: 278, DEX 1→40: 135), so **7 points are left, as his calculator shows**. (This doc
    first said 418 / 2: an arithmetic slip, corrected 10:25 from the live status window.)
  - The Thief's job bonus at Job 40 (`job_stats.yml`): STR +3, AGI +3, VIT +1, INT +1, DEX +2,
    LUK +2. The calculator had Job Lv 1, so it showed none.
- **Weight cap:** 2,400 + 30 x STR = 2,430 (as the calculator).
- **The gear (Batt: what NPCs sell, a Damascus).** The rule: the highest DEF a Thief may wear
  among items in a loaded NPC shop (`npc/merchants/shops.txt` + `npc/pre-re/merchants/shops.txt`),
  per slot:

| slot | item | DEF / effect | weight | sold at (one of) |
|---|---|---|---|---|
| weapon | Damascus 1222 (dagger: Double Attack applies) | ATK 118, unbreakable | 80 | Morroc, Aldebaran, Einbroch, Lutie weapon dealers |
| shield | Buckler 2103 | 4 | 60 | Alberta, Aldebaran |
| head (top + mid) | Goggles 2224 | 5 | 30 | Hugel Armor Dealer |
| body | Thief Clothes 2335 (see below) | 6, AGI +1 | 10 | Morroc, Lighthalzen, Comodo |
| garment | Manteau 2505 | 4 | 60 | Alberta, Aldebaran |
| shoes | Boots 2405 | 4 | 60 | Alberta, Aldebaran |
| accessory x 2 | Rosary 2608 | MDEF +5, LUK +2 each | 10 each | the Prontera church |

- **The one exception to the rule is the body.** Chain Mail has DEF 8 but weighs 330. Thief
  Clothes has DEF 6 and weighs 10.
  - For a looting character, the 320 weight is 13 % of the cap, and natural regen stops at 50 %
    weight.
  - So it is -2 DEF for +320 of loot room and +1 AGI. Batt can swap it back.
- **Carried:** White Potion 504 x 10 (150 weight) and Fly Wing 601 x 10 (50 weight).
  - The Crusader carried 50 potions, which weigh 750: that is 31 % of this cap.
  - Equipped + carried = 520 of 2,430 (21 %).
- **Expected numbers, to read against the status window:**
  - flee about 50 + 65 + 30 (Increase Dodge 10) = ~145;
  - the monsters' HIT (level + DEX): Elder Willow 58, Bigfoot 45, Eggyra 56. Each therefore lands
    the 5 % minimum on one Thief while at most 2 attack (pre-re: flee drops 10 % per attacker
    beyond 2).
  - **Magic ignores flee:** Elder Willow casts Fire Bolt Lv 3 and Fire Attack (mob_skill_db), and
    Bigfoot has a STUN attack. VIT 1 resists nothing.

## 4. The build (phase 1a): the Crusader's way (crusader-orcsdun01.md 2b), slot 3 of the GM account

- **Character:** a NEW character on the GM account (same block id 2000002), made with the client's
  Make Character UI.
  - The name is fresh and in `data/thief/char.json` (gitignored).
- **Guarded GM lines:** every level / job / item command goes through `crusader.py gm --char thief
  --job J`.
  - The DB must say the Thief is the account's online character.
  - The name line and the job line on Basic Info must match their references. The references are
    cut only after a judged frame.
  - So no command can land on the Novice GM or the Crusader.
- **The steps, each judged on a frame:**
  1. character select → slot 3 → Make Character → the name → Create;
  2. enter the game, `@warp` off new_1-1 at once;
  3. `@joblevelup 9`, then Basic Skill 9 in the skill window;
  4. `@job 6` (Thief), `@joblevelup 39` (Job 40), then the six Thief skills in the skill window
     (39 points);
  5. `@baselevelup 49` (Base 50);
  6. the status window's '+': AGI +61, DEX +39 (100 clicks). The points read back 2;
  7. `@item` the gear and the consumables, and equip each by a double-click in the inventory;
  8. hotkeys: F1 White Potion, F2 Fly Wing, F3 Steal (the skill window icon dragged to the bar);
  9. the DB read-back after the server's save: class 6, Base 50 / Job 40, the stats, the skills,
     the equipped items.
- **Stop rule:** any identity, UI-gate or read-back mismatch stops the build for a judged look.
  Nothing is retried blind.

### 4b. BUILT 2026-10-24 10:09-10:29 (every GM line through `crusader.py --char thief`)

- **Thief8fce**, slot 3 of the GM account, char id 150004 (the name is in data/thief/char.json,
  gitignored). Made by the client's Make Character UI (Human, the default look).
- **Steps, each judged on a frame:**
  1. `@warp prt_fild08 170 375`;
  2. `@joblevelup 9`, then Basic Skill 9 (learn_skill@1's rule: points 9 → 0);
  3. `@job 6`, `@joblevelup 39`;
  4. the six skills by the same rule, the geometry shifted per icon on the Thief tab: Steal 10 →
     Hiding 1 → Envenom 7 → Detoxify 1 → Double Attack 10 → Increase Dodge 10 (points 39 → 29 →
     28 → 21 → 20 → 10 → 0);
  5. `@baselevelup 49`;
  6. the status window's '+': AGI x 61, DEX x 39;
  7. `@item` x 9, then 8 double-clicks in the Eqp tab, each located by its icon;
  8. hotbar drags: F1 White Potion, F2 Fly Wing, F3 Steal.
- **The status window, judged:**
  - STR 1+3, AGI 62+4 (Thief Clothes +1), VIT 1+1, INT 1+1, DEX 40+2, LUK 1+6 (Rosaries +4),
    Status Point 7;
  - ATK 131, DEF 23+2, MDEF 10+2, HIT 92, FLEE 146+1, ASPD 165;
  - HP 952, SP 112; weight 570 / 2,430. That includes the starter Knife and Cotton Shirt (50),
    which the client had equipped and which came off at the first equips.
- **The DB read-back:** class 6, Base 50 / Job 40, the same stats, 7 status points, 0 skill
  points; skills NV_BASIC 9, TF_DOUBLE 10, TF_MISS 10, TF_STEAL 10, TF_HIDING 1, TF_POISON 7,
  TF_DETOXIFY 1.
- **What was met on the way (each recorded, none worked around):**
  - learn_skill@1's no-modal reference was cut over the Novice tree. On the Thief tab its side
    reads 0.84 (bar 0.85), so the modal was read one-sided, the Crusader build's way.
  - The FIRST Steal attempt declined "no tentative": my builder's Io kept the UNSHIFTED reader
    geometry (Basic Skill's +N box). A diagnostic frame showed the +1 inside the shifted box (10
    of 10 frames read). RESET restored the points, the reader got the per-skill geometry, and the
    whole tree applied.

### 4b2. The +8 Damascus (Batt 2026-10-24 ~12:0x; demonstrations 4.03 Amendment B)

- 4.03's pilot did 2.7 damage per attack to Bigfoot (dagger 50 % vs Large, VIT 55).
- Batt's sample status window (Renewal; this build with a +8 Damascus) sets the target. Group 20
  got `refine` (logged), and `@refine 2 8` made the equipped Damascus +8.
- The status window: ATK 131 + 40; the rest unchanged. Pre-re adds the refine bonus after DEF, so
  that is ~+40 per hit against anything.

### 4b3. The status window vs Batt's sample (Batt 2026-10-24 ~16:0x: "make ATK, Flee and Hit close to the sample")

Our window: ATK 131 + 40, HIT 92, FLEE 146 + 1. The sample's: ATK 27 + 158, HIT 271, FLEE 249 + 1.
The gap is the SERVER MODE's formulas, not the build. The pinned source (e985006), read
2026-10-24 ~16:2x:

| | pre-renewal (ours) | renewal (the sample's server) |
|---|---|---|
| a player's HIT (status.cpp status_calc_misc) | Base Lv + DEX | Base Lv + DEX + LUK / 3 **+ 175** |
| a player's FLEE | Base Lv + AGI | Base Lv + AGI + LUK / 5 **+ 100** |
| a monster's HIT / FLEE | Lv + DEX / Lv + AGI | Lv + DEX **+ 150** / Lv + AGI **+ 100** |
| hit chance (battle.cpp is_attack_hitting) | **80** + HIT - FLEE | **0** + HIT - FLEE |
| caps (conf/battle/battle.conf) | min_hitrate 5, max_hitrate 100 | the same |

- The renewal constants are added to BOTH sides and cancel in the chance. Our attacks: 80 + 92 -
  (Lv + AGI) is over 100 against every pay_fild07 monster (Elder Willow 40, Eggyra 60, Bigfoot
  50), so it is capped at 100 %. Their attacks: 80 + (Lv + DEX) - 146 is under 5 for all of them,
  so it is floored at 5 %.
- **Measured (t1b + t2 packets):**
  - our attacks hit 455 of 457 (99.6 %);
  - the monsters' attacks hit us 39 of 629 (6.2 %).
  - A bigger window number cannot do better than these caps. Elder Willow's MAGIC ignores flee in
    both modes.
- No pre-renewal stat or NPC gear shows HIT 271: DEX 99 at Base 50 shows 149.
- **ATK:** the pre-renewal window shows Damascus 118 + STR / DEX / LUK 13 = 131, + 40 for the
  refine. It does NOT show the OVER-REFINE bonus:
  - refine.yml (pre-re, weapon level 3): RandomBonus 2400 at +8, so overrefine = 24;
  - battle.cpp battle_add_weapon_damage adds rnd() % 24 + 1 to every hit's base damage, a mean
    of +12.5.
  - Effective ATK = 171 + 12.5 = ~183.5 against the sample's 185.
- **So nothing was changed.** The 7 unspent status points stay unspent: the sample keeps STR at
  1 too. Raising STR 1 -> 4 (6 points) would add +3 ATK, if Batt wants it.

### 4c. The economics model (econ_model.py build, NPC prices only; rares out)

| map | V z / kill | aggressive share | note |
|---|---|---|---|
| pay_fild07 | 63.7 | 0.372 | Elder Willow, Eggyra, Bigfoot, Poporing, Willow |
| pay_fild09 | 62.0 | 0.0 | Smokie, Bigfoot |
| orcsdun01 | 56.0 | 0.815 | the Crusader's dungeon |
| pay_fild08 | 17.3 | 0.0 | Spore, Willow, Poring, Pupa |
| prt_fild08 | 7.4 | 0.0 | the Novice's field |

V counts NPC sell prices only. The four target items are worth far more in a player shop, and are
counted per hour apart (dungeon_judge.py items).

### 4e. The target items, staged on the floor for their recognition (Batt 2026-10-24 ~16:0x: "train the target drops ... for pickup accuracy")

- **Why staged:** the four items almost never drop: 0.07-0.75 per 100 kills (4c). 4.03's 69 kills
  gave 1 and the 4.04 pilot's 7 gave 1. The labelled frames have to be made.
- **The tool:** `scripts/stage_items.py` (fa5062b; settle fix 9119de9).
  - The Thief, immune (`@monsterignore`; its "You are now immune to attacks." line read on a
    frame), gives itself one of each (`@item 757 / 756 / 604 / 518 1`).
  - It drops them by the inventory's KNOWN path: `gm_state.clear_loot` with the tool's own icon
    set (data/thief/stage_icons, cut from judged inventory frames). Only these four are loot;
    everything else is never dropped.
  - Then ~5 s still at the spot and at 4 offsets (+-3 cells, same-map `@warp`): typed lines only,
    no world click.
  - The 1-fps recorder banks the frames. The packets give each floor item's cell and its drop and
    vanish times: the OFFLINE labels.
- **The session (2026-10-24 17:04-17:31):**
  - 12 spots on pay_fild07 (seed 7, >= 25 cells apart, inside the hunt's own search area);
  - all four items dropped at every spot: 48 drops;
  - recording `20261024T170356-rdp-stage-items-b`: 1,538 frames, 3.42 GB, 1,617 packet events;
    shipped to the NAS and verified;
  - events `20261024T170401-stage-items-pay_fild07-b`.
  - A first attempt (17:02) stopped safely at spot 0: a fixed 2.5-s wait after the map-change
    `@warp` checked the loading screen. It now waits for the identity to read.
  - A relog at 17:32 cleared the immunity before 4.04's s1.
- The Dead Branch picked in the 4.04 pilot and the Rough Elunium from 4.03 t1 were in the bag.
  They were dropped with the staged stacks (lab items; counted in their runs' tables already).
- **The study:** a subagent, offline (CPU, no GPU, no live input). It pre-registers a split by
  spot (0-7 fit, 8-11 test) and bars, builds packet labels and per-item templates, and tests them
  against the 4.03 hunting frames as negatives and the pilot's natural Dead Branch.
  `docs/planning/target-items.md` (its branch). The verdict decides "loot by sight" by templates,
  or a learned item class later (GPU: R1-R3).
  - **➡️ RESULT (target-items.md 9b, merged 2026-10-24 ~18:4x): all four FAIL the recall bar.**
    - Recall: 757 19.0 %, 756 40.0 %, 604 66.7 %, 518 66.7 %. Precision 100 %, and 0 false
      detections in 4,392 hunting frames. The pilot's natural Dead Branch was found.
    - Trees hide 29 % of the TEST labels, which caps recall under 80 % for every item.
    - On open ground: Honey 100 %, Dead Branch 85.7 %.
    - The proposal: re-stage on OPEN ground, use multi-templates, and clear the Poporings, which
      looted spots 7-8 within seconds.
  - **➡️ ROUND 2 (target-items.md 10, merged 2026-10-25 ~00:1x): ALL FOUR PASS on open ground.**
    - Staging c (22:23-22:51, 12 spots outside the tree footprints) + multi-templates.
    - TEST recall: 757 97.3 %, 756 95.7 %, 604 95.7 %, 518 94.9 %; precision 100 %.
    - False detections: <= 0.022 per 100 unseen hunting frames (s4 + s5).
    - All 8 misses fall on 3 frames where the client flashes floor items yellow.
    - "Loot by sight" qualifies for all four. The live version needs its own pre-registration.
- **➡️ STAGING c ALSO DROPPED 4.04's NATURAL TARGET ITEMS (found 2026-10-25 ~03:2x from its
  packets; not seen at the time).** `clear_loot` drops WHOLE stacks, as with b above.
  - c's first spot (79,118-121) dropped Dead Branch 5, Rough Elunium 3, Rough Oridecon 2 and
    Honey 2: one fresh `@item` copy each, plus everything held.
  - What was held: 4.04's natural Dead Branch 3 (2 picked + 1 stolen) and Rough Elunium 1, plus
    s3's looter-returned staged set (1 of each).
  - Nothing picked them back up. The 4.04 RESULT still counts them as collected (demonstrations
    4.04), but the Thief no longer holds them.
  - Its target items now (DB, 2026-10-25 ~03:1x) are 1 of each: s7's returned staged set, not
    income.
  - **Fix: stage@3 (`stage_items.held_refusal`) refuses to stage while the Thief holds any target
    item** (DB last save). A person stores them first.

### 4d. Renewal? (Batt 2026-10-24 ~11:3x: "can our server and client move to Renewal (third classes)?")

**➡️ PARKED by Batt 2026-10-24 ~16:0x: "park it; use ours as before".** The study below stays as written.

A PROPOSED study is in [renewal-feasibility.md](renewal-feasibility.md):
- the server is a rebuild with `PRERE=no`; the same client exe and data, no Windows change;
- under renewal, the targets move: Elder Willow leaves pay_fild07, and the drop level penalty
  halves a Base 50 Thief's kill drops;
- option A, a second renewal rAthena run one at a time beside today's, is recommended.
Batt decides. 4.03 runs on pre-re as registered.

## 5. pay_fild07 prep (offline; a subagent in a tmpfs worktree)

As orcsdun01-dungeon-prep.md did for the dungeon:
- the client GAT extract (run-time, /dev/shm) and the client / server walkability agreement;
- the NPC cells (`kb_first_workflow.py npc-cells` for the map);
- `config/map_zones/pay_fild07.yaml`: the 4 warp spans with their margins, refused by
  `map_zones.walk_why` (the zone click proof);
- a start stand that passes the three stand-cell checks;
- the hunt lint's map allowlist.

➡️ **DONE offline 2026-10-24 10:06-10:33 ICT: [payf07-prep.md](payf07-prep.md).** Two items are
still open, and the runner refuses pay_fild07 until both are done:
- the zones file is a DRAFT the loader refuses, PENDING Batt's review or delegation;
- the rebuilt first_workflow.json (the touch areas) waits to be installed in data/kb.

That doc's section 6 lists what dungeon_hunt.py needs per map. It also lists two Thief conflicts
that are not map files: the Etc drop takes Rough Oridecon / Elunium, and the Auto Guard F3 is Steal.

The name tags (`nametag.py cut` / `build`) for the five species are cut live, by the immune
Novice GM hovering monsters without clicking.

## 6. Phase 1b: walk-and-hit with Steal first (pre-registered BEFORE its first scored run)

The runner is `dungeon_hunt.py`, parametrised by map and character. Its walk search, cursor SWORD
engagement and loot step carry over. The Crusader-only parts (Heal, Auto Guard) are off for the
Thief. Sustain is strategy B: potions below 30 %, a Fly Wing below 20 %, rest after a fight under
60 %.

**Steal first:** on a struck target whose name tag reads Elder Willow or Bigfoot, F3 (Steal) and
a click on it, until the item line says it was stolen or K attempts. K and the success read are
fixed in the pre-registration.

**Steal, as the pinned server computes it (pre-re, `pc_steal_item`):**
- rate = (DEX - the monster's DEX) / 2 + 6 x 10 + 4;
- the drop slots are tried IN ORDER, each with drop rate x rate / 100;
- the FIRST slot that passes is the stolen item;
- a monster is stolen from once; tries are unlimited (`skill_steal_max_tries: 0`);
- its kill drops are unaffected.

With DEX 42:

| target | success / attempt | what a success gives | the four target items per SUCCESSFUL steal |
|---|---|---|---|
| Elder Willow (DEX 38, rate 66) | 61.2 % | Resin 96.8 % of successes | Dead Branch 0.42 %, Rough Elunium 0.17 % |
| Bigfoot (DEX 20, rate 75) | 82.7 % | Bear's Footskin 81.6 %, Animal Skin 14.7 % | Honey 0.73 %, Rough Oridecon 0.07 % |

- So Steal adds about +42 % Dead Branch per Elder Willow (0.42 % on top of the 1 % kill drop) and
  +16 % Honey per Bigfoot. It costs ~1.6 and ~1.2 attempts (10 SP each).
- **Expected target items per 100 kills** at the spawn mix (kills in proportion to the counts):

| item | from kill drops | from steals |
|---|---|---|
| Dead Branch | 0.39 | +0.16 |
| Rough Elunium | 0.28 | +0.07 |
| Honey | 0.75 | +0.12 |
| Rough Oridecon | 0.07 | +0.01 |

- **At ~150 kills/h, expect about 0-3 of each target item per hour.** Per-item rates for these
  items need many run-hours before they are precise. Every report gives the counts with the hours
  behind them.
- **Measured per run** (packets, offline):
  - kills/h;
  - **every item per hour, by source (kill drop picked / stolen)** (Batt 2026-10-24);
  - steal attempts, successes and what was stolen;
  - NPC z/h (sell = buy / 2) and the four target items apart;
  - s/kill (fight / walk / stand);
  - HP min, potions / Fly Wings, deaths, hard bars (map change, NPC contact, unknown UI state);
  - monsters met per 10 min.
- **Capture first:** every run banks its frames and packets to the NAS. They are the item class's
  and the pay_fild07 detector's label source (item-class.md is re-registered on this map's
  sessions).
