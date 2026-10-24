---
doc_type: design
hypothesis: "A Thief (Base 50 / Job 40, AGI 62 / DEX 40, Damascus + NPC gear) hunting a Payon field by the dungeon runner's walk-and-hit, with Steal Lv 10 tried first on Elder Willow / Bigfoot, yields measurable counts of the high-value items (Dead Branch, Rough Elunium, Rough Oridecon, Honey) per hour, safely (deaths and hard bars counted)."
status: "PHASE 1a DONE 2026-10-24 10:09-10:29: Thief8fce built on slot 3 and verified (section 4b). pay_fild07 prep merged (payf07-prep.md). 4.03 (the walk-and-hit base) pre-registered 0055ed6 10:54:38, CONDITIONAL: no run before Batt confirms the map (pay_fild07 by default: section 2) and reviews or delegates config/map_zones/pay_fild07.yaml (a DRAFT the loader refuses)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [crusader-orcsdun01.md, item-class.md, ../demonstrations.md, ../../scripts/dungeon_hunt.py, ../../scripts/crusader.py]
next_action: "Batt: the map (pay_fild07?) and the zones delegation. Then 4.03 (pilot + 40-min runs, tags banked), then 4.04 (Steal first, gated on the labelled tags)."
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
