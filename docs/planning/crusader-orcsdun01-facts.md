---
doc_type: research
hypothesis: "A Base 60 / Job 50 AGI-first Crusader (one-handed sword + shield, unmounted, GM immunity OFF) can hunt orcsdun01 if the bot knows which monsters bypass FLEE, how fast a pack drains HP, and where the map corners it."
status: FACTS (offline arithmetic, 2026-10-21; pinned pre-renewal rAthena e985006; no decision taken here)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, ../competition.md, ../../config/map_zones/README.md]
next_action: "The build agent's exact numbers (HIT, FLEE, DEF, VIT, LUK, MaxHP, skills) go into the tables in sections 2 and 4. Batt decides the HP-threshold rule and whether any orcsdun01 zone is wanted; section 3c only lists candidates."
title: "Crusader on orcsdun01 (Orc Dungeon F1): the monsters' numbers, the map and survival (offline facts)"
date: 2026-10-21
owner: Batt
---

# Crusader on orcsdun01: the monsters' numbers, the map and survival

**The scenario (Batt):** a CRUSADER at Base 60 / Job 50, built AGI-first, with a one-handed sword
and a shield, unmounted. It hunts Orc Dungeon F1 (`orcsdun01`) with GM immunity OFF, and the
monsters come to it.

**How this was made.** Offline research and arithmetic only: no live action, no game input, no GPU.
Scratch work ran 2026-10-21 16:17-16:46 ICT (from `date`).

**Sources.** Every number cites a file and line at the pinned rAthena
`e985006171d2eb320ee512a653f4c83aea3d81b6`.
- The db and npc files are the local partial copy (`/dev/shm/poring-lab-rathena-src`).
- `src/` and `conf/battle/` were fetched at the same commit, read as text only.
- Only numbers and facts are quoted (GPL), never code.

**Pre-renewal is confirmed.** `.env` sets `RATHENA_PRERE=yes`; `.env.example:70` gives Batt's
2026-09-30 reason. `compose.yaml:63` passes it into the Dockerfile's `--enable-prere`. So every
formula below comes from the `#ifndef RENEWAL` branch, and every table from `db/pre-re`.

**No lab battle overrides.**
- `services/rathena/conf/import/` holds only the char, inter, log, login and map templates, plus
  `groups.yml`.
- The upstream `conf/import-tmpl/battle_conf.txt` is empty.

So the `conf/battle/*.conf` defaults at e985006 apply. The running container was not inspected
(see UNVERIFIED).

**Already known; this doc reuses it.**
- The local `/dev/shm/poring-lab-tmp/orc/FACTS.md`: spawns, warps, the map size and walkability.
- `orcsdun01-detector.md`, section 2a: the live server showed exactly the 135 units of the 7
  species in three collection blocks.

## 0. Bottom line

1. **The player always hits.** The monsters' FLEE is 20-60, so HIT 80 already gives 100 % against
   all 7 species (cap `max_hitrate: 100`). HIT above 80 buys nothing on this map.
2. **FLEE works against the Orcs' normal attacks; their skills ignore it.** At FLEE 130 and one
   attacker, an Orc Zombie's normal attack lands 5 % of the time and an Orc Skeleton's 8 %.
   - About 5 % of the Orcs' skill rolls are **NPC_CRITICALSLASH**: always a critical, so it
     ignores FLEE, DEF and Divine Protection.
   - It hits for the flat maximum ATK: 184 for an Orc Zombie, 236 for an Orc Skeleton.
   - It is the largest share of a lone Orc's damage at high FLEE: ~5.9 HP/s from an Orc Zombie
     and ~8.3 HP/s from an Orc Skeleton (simulated, Angry state).
   - Only Auto Guard can block it.
3. **Drainliar is the real FLEE-breaker.** Its HIT is 102 (Lv 24 + DEX 78), so it lands 52 % of
   its normal attacks at FLEE 130.
   - One Drainliar alone does ~16 HP/s.
   - Its Blind Attack blinds about 47 % of the times it lands, for ~25 s. Blind cuts FLEE by
     25 %.
   - Only 5 are on the map, but each respawns 5 s after it dies.
4. **The multi-attacker FLEE penalty decides everything.** From 3 attackers, FLEE drops 10 % per
   attacker (`agi_penalty_*`). With 5 attackers, FLEE 130 counts as 91, and an Orc Skeleton then
   lands 47 %.
   - Familiars (1 HP a hit) and Steel Chonchons are near-harmless themselves.
   - But **every attacker counts toward that penalty**, so they make the Orcs hit.
5. **Pack damage at FLEE 130, DEF 20, VIT 30, DP 10**, as HP per second with the monsters'
   skills included (normal attacks only in brackets):

   | pack | HP/s with skills (normal attacks only) |
   |---|---|
   | 3 Orc Zombies | 23.8 (6.8) |
   | 3 Orc Zombies + 2 Orc Skeletons | 103.8 (65.3) |
   | + 1 Drainliar | 163.1 (123.6) |
   | 8 around the player (the worst case) | 249.0 (199.6) |

   - A random spot of the map has **3.2 aggressive monsters within aggro reach on average**.
   - If they all engage: a mean of **~2,400 HP/min** (p50 1,431, p90 5,466).
6. **The map is a ring of wide corridors around a central rock** (4,006 blocked cells, x50-142
   y59-136). Dead-end wings hang off the ring.
   - There is **no narrow (<= 2-cell) choke between areas**, and no single door of 4 cells or less
     cuts anything off. The repo's pocket finder, run with prt_fild08's settings, returns 0
     candidates.
   - The only <= 4-cell doors are the two into a 40-cell side bit at x69-76 y27-33, and it has
     both of them.
   - The dead ends are WIDE:
     - the SE wing: 1,625-1,838 cells behind a 9-wide throat at x163-171 y~62-95, with the
       warp to F2 at its far end;
     - the N pocket: 458 cells behind a 10-wide door at x109-117 y148-151;
     - the NW entrance wing: 466-651 cells, with the exit warp inside it.
7. **A Fly Wing does not land in safety here.** Its landing cell is uniform over the same band as
   the spawns, and has on average 3.2 aggressive monsters within reach: P(>= 1) = 93.6 %.
   - It trades a heavy pack for an average one.
   - Potions have the throughput to out-heal any pack: the server allows one item every 100 ms.
     Their stock, weight and the bot's reaction time are the limits (section 4).

## 1. The 7 species

### 1a. Stats

Source: `db/pre-re/mob_db.yml`, the row starting at the line given.
- A stat the row leaves out defaults to 1, and Defense / MagicDefense to 0 (`mob.cpp:4946-4958`).
- `Attack2` is the MAXIMUM attack in pre-renewal (`mob.cpp:5107-5117`).

| species (id, mob_db line) | Lv | HP | base / job EXP | ATK | DEF | MDEF | STR AGI VIT INT DEX LUK |
|---|---|---|---|---|---|---|---|
| Orc Zombie (1153, :7195) | 24 | 1,568 | 196 / 120 | 151-184 | 5 | 10 | 1* 12 24 0 24 5 |
| Orc Skeleton (1152, :7148) | 28 | 2,278 | 315 / 194 | 190-236 | 10 | 10 | 1* 14 18 0 30 15 |
| Familiar (1005, :245) | 8 | 155 | 28 / 15 | 20-28 | 0* | 0* | 1* 12 8 5 28 0 |
| Drainliar (1111, :5173) | 24 | 1,162 | 431 / 176 | 74-84 | 0* | 0* | 1* 36 24 0 78 0 |
| Steel Chonchon (1042, :1936) | 17 | 530 | 109 / 71 | 54-65 | 15 | 0* | 1* 43 17 5 33 10 |
| White Plant (1082, :3776) | 1 | 10 | 0 / 0 | 1-2 | 100 | 99 | 0 0 0 0 0 0 |
| Black Mushroom (1084, :3876) | 1 | 15 | 0 / 0 | 1-2 | 100 | 99 | 0 0 0 0 0 0 |

`*` = not in the row, so the default applies. STR does not matter for monsters:
`enable_baseatk: 0x9` (battle.conf:13) gives base ATK to players and homunculi only
(`status.cpp:2432-2433`).

| species | AttackRange / SkillRange (aggro) / ChaseRange | Size | Race | Element | WalkSpeed ms/cell (cells/s) | AttackDelay / AttackMotion / DamageMotion (ms) |
|---|---|---|---|---|---|---|
| Orc Zombie | 1 / 10 / 12 | Medium | Undead (Orc group) | Undead 1 | 400 (2.5) | 2,852 / 1,152 / 840 |
| Orc Skeleton | 1 / 10 / 12 | Medium | Undead (Orc group) | Undead 1 | 200 (5.0) | 2,420 / 720 / 648 |
| Familiar | 1 / 10 / 12 | Small | Brute | Dark 1 | 150 (6.67) | 1,276 / 576 / 384 |
| Drainliar | 1 / 10 / 12 | Small | Brute | Dark 2 | 250 (4.0) | 1,276 / 576 / 384 |
| Steel Chonchon | 1 / 10 / 12 | Small | Insect | Wind 1 | 150 (6.67) | 1,076 / 576 / 480 |
| White Plant | 1 / 7 / 12 | Small | Plant | Earth 1 | 1,000 (immobile) | 1 / 1 / 1 |
| Black Mushroom | 1 / 7 / 12 | Small | Plant | Earth 1 | 1,000 (immobile) | 1 / 1 / 1 |

- **The player walks at 150 ms/cell.** That is `DEFAULT_WALK_SPEED`, `mmo.hpp:93`; unmounted, no
  speed item.
  - Familiar and Steel Chonchon match that speed and cannot be outrun.
  - Orc Skeleton (5 cells/s), Drainliar (4) and Orc Zombie (2.5) can.
- **The monster's attack period is its AttackDelay** (`unit.cpp:1900-1907`). It is never shorter
  than AttackMotion (`mob.cpp:5564`).

### 1b. AI and modes

The Ai code maps to the mode bits in `mob.hpp:155-160`. The bits are named in `mmo.hpp:243-271`
and described in `doc/mob_db_mode_list.txt`.

| species | Ai | bits | modes | what it means for the Crusader |
|---|---|---|---|---|
| Orc Zombie, Orc Skeleton, Familiar | 04 | 0x3885 | CanMove, **Aggressive**, CanAttack, **Angry**, ChangeTargetMelee, ChangeTargetChase | Attacks on sight. "Angry": until the player hits it, it runs a separate before-attacked skill state that rolls its skills on a 1-s clock (section 1c) |
| Drainliar | 09 | 0x3095 | CanMove, **Aggressive**, **CastSensorIdle**, CanAttack, ChangeTargetMelee, ChangeTargetChase | Attacks on sight, and goes for anyone who casts a skill near it while it is idle |
| Steel Chonchon | 07 + Detector | 0x108B + 0x2000000 | CanMove, **Looter**, **Assist**, CanAttack, ChangeTargetMelee, Detector | NOT aggressive. Once one attacks you, idle Chonchons within `assist_range: 11` join it (`unit.cpp:3299-3302`, monster.conf:114). It loots floor items |
| White Plant, Black Mushroom | none (default 06 = 0, `mob.cpp:4963`) + Modes | IgnoreMelee / Magic / Ranged / Misc | never moves, never attacks | Takes 1 damage from any hit (`battle.cpp:4959-4961`): 10 and 15 hits to kill, no EXP |

**Aggro (verified in code).**
- An aggressive monster searches a square of SkillRange = 10 cells: Chebyshev distance, since
  `CIRCULAR_AREA` is off (`core.hpp:39`; `path.cpp:436-446`). The search is `mob.cpp:2027`.
- It needs a line of sight that walls do not block (`battle.cpp:8215-8239`).
- And a walk path within 10 steps when it stands still, or 12 when it walks (`ACTIVEPATHSEARCH`,
  `mob.cpp:58`, `:1347-1356`).
- `view_range_rate` and `chase_range_rate` are 100 (monster.conf:93, :98).

**Monsters do not follow through warps** (`mob_warp: 0`, monster.conf:82).

### 1c. Their skills that matter to a melee fighter

Source: `db/pre-re/mob_skill_db.txt`, columns rate / cast / delay.
- The rate is per 10,000 per roll (`mob.cpp:4315`).
- Each skill then waits 5 s before it can roll again.
- Skill mechanics: `src/map/skills/npc/*.cpp` and `db/pre-re/skill_db.yml`.

| species | skill (lines) | lv | rate / cast / delay | effect |
|---|---|---|---|---|
| Orc Zombie | NPC_CRITICALSLASH (812-813) | 1 | 5 % / 500 ms / 5 s | **Always critical** (`battle.cpp:3022`; crits always hit, `:3240`, `:5435-5444`); damage = the max ATK (`:2573`); **ignores DEF and VIT DEF, so Divine Protection too** (`:3336-3339`). Auto Guard can still block it (skill_db.yml:5488 has no IgnoreAutoGuard) |
| Orc Zombie | NPC_UNDEADATTACK (814-815) | 1 | 20 % / 0 / 5 s | A normal roll at 100 %, Undead element, hit chance x1.2 before the cap (`undeadelementattack.cpp`) |
| Orc Skeleton | the same pair (808-811) | 1 | 5 % and 20 % | the same; crit = 236 |
| Familiar | NPC_BLINDATTACK (68, 70) | 1 | 5 % / 0 / 5 s | Blind 20 % base on a landed hit (`blindattack.cpp`); hit x1.2 |
| Familiar | NPC_DARKNESSATTACK (69, 71) | 1 | 20 % | Dark element, hit x1.2 |
| Drainliar | NPC_BLINDATTACK (548) | **3** | 5 % | **Blind 60 % base**; hit x1.2 |
| Drainliar | NPC_BLOODDRAIN (549) | 1 | 5 % | **IgnoreFlee** (skill_db.yml:5885-5898): always lands; the damage heals the Drainliar (`suckingblood.cpp`) |
| Drainliar | NPC_DARKNESSATTACK (550) | 1 | 20 % | Dark element, hit x1.2 |
| Steel Chonchon | NPC_SILENCEATTACK (218) | 2 | 5 % / 700 ms / 5 s | Silence 40 % base on a landed hit; hit x1.2 |
| Steel Chonchon | NPC_WINDATTACK (219) | 1 | 20 % | Wind element, hit x1.2 |

**When the skills roll.**
- When the mob attacks back (MSS_BERSERK, the retaliation state), it rolls at each attack opportunity, before
  the normal attack (`mob.cpp:1876-1879`; the attack timer runs the AI, `unit.cpp:3207-3215`).
- When it is "angry" (aggressive, not hit yet), it rolls every 1,000 ms (`mob.cpp:1883-1884`,
  `MOB_SKILL_INTERVAL` `mob.hpp:42`). So it rolls 2-3 times per attack cycle.
- Both Orcs and the Familiar list their skills for both states.
- `mob_skill_rate` is 100 (monster.conf:142).

**The skills' elements do not change the damage on Neutral armor.**
- Dark, Undead and Wind attacking Neutral 1 are all 100 % (attr_fix.yml:114, :136, :81).
- Faith's +50 % Holy resistance (`status.cpp:4676-4677`) therefore does nothing on this map.
- Faith's **+2,000 MaxHP** (`status.cpp:3150-3151`) does.

**The monsters' normal attacks have no element:** `attack_attr_none: 14` (battle.conf:134;
`battle.cpp:3669-3670`) makes them 100 % against any armor element.

## 2. The monsters' numbers against the Crusader (pre-renewal formulas)

### 2a. The formulas and the settings

| quantity | pre-renewal rule | source |
|---|---|---|
| monster HIT | Lv + DEX | `status.cpp:2704-2707` (the `#else` = pre-re branch) |
| monster FLEE | Lv + AGI | `status.cpp:2708-2711` |
| player VIT DEF (def2) | VIT (+ bonuses) | `status.cpp:2712-2715` |
| hit chance | **80 + attacker HIT − target FLEE**, capped to **[5, 100]** (not 95) | `battle.cpp:3258-3277`, `:3312`; `min_hitrate: 5`, `max_hitrate: 100` (battle.conf:78-79) |
| multi-attacker FLEE penalty | with n >= `agi_penalty_count` (3) units attacking the player: FLEE × (100 − (n − 2) × 10) / 100, floor 1; players only | `battle.cpp:3265-3275`; battle.conf:85-95 (type 1 = %, count 3, num 10, target 1 = PC) |
| n | the units whose attack target is the player: set when a monster starts attacking in range (`unit_attack`), not while it only chases | `unit.cpp:2944`, `:2782-2797`, `:3516-3523` |
| multi-attacker DEF penalty | n >= 3: hard DEF and VIT DEF × (100 − (n − 2) × 5) / 100 (n capped at 22); VIT DEF floor 1 | `battle.cpp:4780-4800`; battle.conf:101-111 |
| monster damage roll | uniform integer in **[ATK, ATK2 − 1]**; a critical = ATK2; no STR bonus for monsters | `battle.cpp:2526-2539`, `:2570-2573`, `:2622-2624` |
| player hard DEF | damage × (100 − DEF) / 100, DEF capped at 100 (player `max_def: 99`) | `battle.cpp:4872-4880`; player.conf:132 |
| player VIT DEF (pre-re) | ⌊0.3·VIT⌋ + rnd(0, max(0, ⌊VIT²/150⌋ − ⌊0.3·VIT⌋ − 1)) + ⌊0.5·VIT⌋, subtracted after hard DEF | `battle.cpp:4809-4813` |
| Divine Protection | + ⌊(BaseLv / 25 + 3) × lv + 0.5⌋ to VIT DEF vs a monster of Undead ELEMENT or Demon race: **54 at Base 60, lv 10** | `battle.cpp:4816-4818`; `undead_detect_type: 0` = element (battle.conf:72; `battle.cpp:7778-7792`) |
| minimum damage | 1 per landed hit | `battle.cpp:4912`, `:4931` |
| Lucky Dodge (player) | (LUK + 10) / 10 % against normal attacks only; LUK 1 gives 1.1 %. Left out of the tables | `battle.cpp:5424`; `status.cpp:2735-2738`; `enable_perfect_flee: 1` (battle.conf:17) |
| monster criticals | only through NPC_CRITICALSLASH: `enable_critical: 17` = players + mercenaries (battle.conf:21) | |
| Auto Guard | blocks a weapon hit with chance 5/10/14/18/21/24/26/28/29/**30 %** at lv 1-10 (crits included) | `status.cpp:11293-11299`; `battle.cpp:1521` |

The penalty factors are not used in this doc's tables; the VIT DEF table is.

**At VIT 25 / 30 / 35, the random part of VIT DEF is 0**, so VIT DEF is exactly **19 / 24 / 27**.
- With 4 attackers it is 17 / 21 / 24, and with 6 it is 16 / 19 / 22.
- The random part starts only around VIT 50.

### 2b. The player's hit chance

The table uses the formula above with the monsters' FLEE.

| species | FLEE | HIT needed for 100 % | HIT 80 | 90 | 100 | 110 |
|---|---|---|---|---|---|---|
| Orc Zombie | 36 | 56 | 100 | 100 | 100 | 100 |
| Orc Skeleton | 42 | 62 | 100 | 100 | 100 | 100 |
| Familiar | 20 | 40 | 100 | 100 | 100 | 100 |
| Drainliar | 60 | 80 | 100 | 100 | 100 | 100 |
| Steel Chonchon | 60 | 80 | 100 | 100 | 100 | 100 |
| White Plant / Black Mushroom | 1 | 21 | 100 (1 damage) | 100 | 100 | 100 |

### 2c. The monsters' chance to hit the player (normal attacks, %)

n = the units attacking the player, of any species. The effective FLEE row is FLEE after the
penalty.

| FLEE 120 | n = 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| effective FLEE | 120 | 120 | 108 | 96 | 84 | 72 |
| Orc Zombie (HIT 48) | 8 | 8 | 20 | 32 | 44 | 56 |
| Orc Skeleton (HIT 58) | 18 | 18 | 30 | 42 | 54 | 66 |
| Familiar (HIT 36) | 5 | 5 | 8 | 20 | 32 | 44 |
| **Drainliar (HIT 102)** | **62** | **62** | **74** | **86** | 98 | 100 |
| Steel Chonchon (HIT 50) | 10 | 10 | 22 | 34 | 46 | 58 |

| FLEE 130 | n = 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| effective FLEE | 130 | 130 | 117 | 104 | 91 | 78 |
| Orc Zombie | 5 | 5 | 11 | 24 | 37 | 50 |
| Orc Skeleton | 8 | 8 | 21 | 34 | 47 | 60 |
| Familiar | 5 | 5 | 5 | 12 | 25 | 38 |
| **Drainliar** | **52** | **52** | **65** | **78** | 91 | 100 |
| Steel Chonchon | 5 | 5 | 13 | 26 | 39 | 52 |

| FLEE 140 | n = 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| effective FLEE | 140 | 140 | 126 | 112 | 98 | 84 |
| Orc Zombie | 5 | 5 | 5 | 16 | 30 | 44 |
| Orc Skeleton | 5 | 5 | 12 | 26 | 40 | 54 |
| Familiar | 5 | 5 | 5 | 5 | 18 | 32 |
| **Drainliar** | **42** | **42** | **56** | **70** | 84 | 98 |
| Steel Chonchon | 5 | 5 | 5 | 18 | 32 | 46 |

**The elemental, blind and silence skills hit at 1.2 × the base chance, before the cap.** At FLEE
130 that gives:

| n = 1 / 2 / 3 / 4 | hit chance (%) |
|---|---|
| Orc Zombie | 5 / 5 / 13 / 28 |
| Orc Skeleton | 9 / 9 / 25 / 40 |
| Familiar | 5 / 5 / 5 / 14 |
| Drainliar | 62 / 62 / 78 / 93 |
| Steel Chonchon | 5 / 5 / 15 / 31 |

**NPC_CRITICALSLASH and NPC_BLOODDRAIN always land.** Only Auto Guard stops them.

**Blind (status.cpp:7569-7570, 7681-7682): HIT and FLEE −25 %.** Blinded at FLEE 130, the base is
97, so 3 Orc Zombies land 37 % instead of 11 % (section 2f).

### 2d. Damage per landed normal hit (n = 1)

The cells show avg (min-max); the rows are hard DEF, the columns VIT.
- The roll is the pre-renewal one: ⌊roll × (100 − DEF) / 100⌋ − VIT DEF [− 54 DP], minimum 1.
- The Undead-element skill uses the same numbers.
- A Critical Slash ignores the table: 184 from an Orc Zombie, 236 from an Orc Skeleton.

**Orc Zombie (ATK 151-184)**

| DEF | no DP: VIT 25 | VIT 30 | VIT 35 | **DP 10 (−54): VIT 25** | **VIT 30** | **VIT 35** |
|---|---|---|---|---|---|---|
| 10 | 130.8 (116-145) | 125.8 (111-140) | 122.8 (108-137) | 76.8 (62-91) | 71.8 (57-86) | 68.8 (54-83) |
| 15 | 122.5 (109-136) | 117.5 (104-131) | 114.5 (101-128) | 68.5 (55-82) | 63.5 (50-77) | 60.5 (47-74) |
| 20 | 114.2 (101-127) | 109.2 (96-122) | 106.2 (93-119) | 60.2 (47-73) | 55.2 (42-68) | 52.2 (39-65) |
| 25 | 105.9 (94-118) | 100.9 (89-113) | 97.9 (86-110) | 51.9 (40-64) | 46.9 (35-59) | 43.9 (32-56) |

**Orc Skeleton (ATK 190-236)**

| DEF | no DP: VIT 25 | VIT 30 | VIT 35 | **DP 10: VIT 25** | **VIT 30** | **VIT 35** |
|---|---|---|---|---|---|---|
| 10 | 171.8 (152-192) | 166.8 (147-187) | 163.8 (144-184) | 117.8 (98-138) | 112.8 (93-133) | 109.8 (90-130) |
| 15 | 161.2 (142-180) | 156.2 (137-175) | 153.2 (134-172) | 107.2 (88-126) | 102.2 (83-121) | 99.2 (80-118) |
| 20 | 150.6 (133-169) | 145.6 (128-164) | 142.6 (125-161) | 96.6 (79-115) | 91.6 (74-110) | 88.6 (71-107) |
| 25 | 140.0 (123-157) | 135.0 (118-152) | 132.0 (115-149) | 86.0 (69-103) | 81.0 (64-98) | 78.0 (61-95) |

**The species DP does not cover** (Familiar and Drainliar are Brute / Dark, Steel Chonchon is
Insect / Wind):

| DEF | Familiar (20-28): VIT 25 / 30 / 35 | Drainliar (74-84): VIT 25 / 30 / 35 | Steel Chonchon (54-65): VIT 25 / 30 / 35 |
|---|---|---|---|
| 10 | 2.2 (1-5) / 1 / 1 | 51.2 (47-55) / 46.2 (42-50) / 43.2 (39-47) | 33.6 (29-38) / 28.6 (24-33) / 25.6 (21-30) |
| 15 | 1.6 (1-3) / 1 / 1 | 47.2 (43-51) / 42.2 (38-46) / 39.2 (35-43) | 30.6 (26-35) / 25.6 (21-30) / 22.6 (18-27) |
| 20 | 1.1 (1-2) / 1 / 1 | 43.4 (40-47) / 38.4 (35-42) / 35.4 (32-39) | 27.8 (24-32) / 22.8 (19-27) / 19.8 (16-24) |
| 25 | 1 / 1 / 1 | 39.5 (36-43) / 34.5 (31-38) / 31.5 (28-35) | 24.9 (21-29) / 19.9 (16-24) / 16.9 (13-21) |

**Divine Protection 10 roughly halves an Orc Zombie's normal hit** (−54 of ~109). It takes about a
third off an Orc Skeleton's. It does nothing against their criticals.

### 2e. Damage per second from ONE monster

Every cell in this section is for one monster at n = 1.

**The brief's formula: hit chance × average damage / AttackDelay** (normal attacks only, FLEE 130,
VIT 30), in HP/s:

| species | DEF 10 | DEF 15 | DEF 20 | DEF 25 |
|---|---|---|---|---|
| Orc Zombie, no DP | 2.21 | 2.06 | 1.91 | 1.77 |
| Orc Zombie, DP 10 | 1.26 | 1.11 | 0.97 | 0.82 |
| Orc Skeleton, no DP | 5.51 | 5.16 | 4.81 | 4.46 |
| Orc Skeleton, DP 10 | 3.73 | 3.38 | 3.03 | 2.68 |
| Familiar | 0.04 | 0.04 | 0.04 | 0.04 |
| **Drainliar** | **18.83** | **17.20** | **15.65** | **14.06** |
| Steel Chonchon | 1.33 | 1.19 | 1.06 | 0.93 |

**The same with the monsters' skills** (a simulation of the skill rolls above; DEF 20, VIT 30, DP 10
on the Orcs), in HP/s:

| species (state) | FLEE 120 | FLEE 130 | FLEE 140 | notes |
|---|---|---|---|---|
| Orc Zombie (angry) | 7.16 | 6.51 | 6.51 | berserk at 130: 4.47; no DP: 7.48. **The crit alone: 5.93 HP/s** (116 crits/h, angry) |
| Orc Skeleton (angry) | 15.98 | 11.96 | 10.71 | berserk at 130: 7.92; no DP: 13.82. **The crit alone: 8.33 HP/s** (127 crits/h) |
| Familiar (angry) | 0.04 | 0.04 | 0.04 | harmless, except Blind (section 2g) |
| Drainliar (berserk: it has no Angry mode) | 19.41 | 16.49 | 13.56 | Blood Drain always lands |
| Steel Chonchon (berserk; it fights only when engaged) | 2.08 | 1.01 | 1.01 | Silence (section 2g) |

- **"Angry" vs "berserk".** An aggressive Orc or Familiar that the player has not hit yet is
  "angry" (`mob.cpp:1823-1832`). The one the player is hitting is "berserk". A monster that
  acquires the player already in attack range skips Angry (`mob.cpp:2027-2033`).
- **FLEE barely moves the Orcs' total.** From FLEE 130 to 140 a lone Orc Zombie stays at 6.5 HP/s:
  the normal hit is already at the 5 % floor, and the criticals ignore FLEE.

### 2f. Packs

Every member counts toward n. The settings are DEF 20, VIT 30 and DP 10, with the monsters in the
states above.

| pack | n | FLEE 120: normal / +skills / +skills & AG10 | FLEE 130 | FLEE 140 |
|---|---|---|---|---|
| A: 3 Orc Zombies | 3 | 12.4 / 29.9 / 20.9 | 6.8 / 23.8 / 16.7 | 3.1 / 19.7 / 13.8 |
| B: 2 Orc Skeletons | 2 | 13.6 / 32.0 / 22.4 | 6.1 / 23.9 / 16.7 | 3.8 / 21.4 / 15.0 |
| C: 3 OZ + 2 OS | 5 | 76.0 / 115.1 / 80.6 | 65.3 / 103.8 / 72.6 | 54.6 / 92.4 / 64.7 |
| D: 2 OZ + 1 Familiar (close to the typical draw) | 3 | 8.3 / 20.0 / 14.0 | 4.6 / 15.9 / 11.2 | 2.1 / 13.2 / 9.2 |
| E: 3 OZ + 2 OS + 1 Drainliar | 6 | 133.1 / 173.1 / 121.2 | 123.6 / 163.1 / 114.2 | 113.5 / 152.2 / 106.5 |
| **F: 4 OZ + 2 OS + 1 Drainliar + 1 Familiar (all 8 cells around the player)** | 8 | 207.5 / **256.6** / 179.6 | 199.6 / **249.0** / 174.3 | 191.7 / **241.1** / 168.7 |

Notes on the table:
- All values are HP/s; × 60 gives HP/min. Pack C at FLEE 130 is 3,918 / 6,228 HP/min (normal /
  with skills).
- AG10 = Auto Guard 10, which blocks 30 % of weapon hits, criticals included.
- **Blinded** (FLEE 130 × 0.75), normal attacks only:

  | pack | HP/s |
  |---|---|
  | A | 25.3 (from 6.8) |
  | C | 102.1 |
  | E | 155.1 |

- **The step from n = 2 to n = 5 is the cliff.** From 3 to 5 attackers, the FLEE build loses most
  of its value. Pack C deals ~10× pack A's normal-attack damage, with only 2 monsters more.

**The typical encounter.**
- Take the aggressive monsters within aggro reach of a random walkable cell (section 3d): their
  counts per species are Poisson with these means:

  | species | mean count in reach |
  |---|---|
  | Orc Zombie | 2.32 |
  | Familiar | 0.44 |
  | Orc Skeleton | 0.29 |
  | Drainliar | 0.15 |

- Assume all of them engage at once (20,000 draws):

| FLEE | n mean | P(n >= 3) | P(n >= 5) | HP/min with skills: mean / p50 / p90 | normal only: mean / p90 |
|---|---|---|---|---|---|
| 120 | 3.2 | 0.62 | 0.22 | 2,743 / 1,792 / 5,984 | 1,718 / 4,516 |
| 130 | 3.2 | 0.62 | 0.22 | 2,405 / 1,431 / 5,466 | 1,409 / 3,918 |
| 140 | 3.2 | 0.62 | 0.22 | 2,211 / 1,184 / 5,049 | 1,218 / 3,448 |

These figures count the monsters' damage only. The player's own kills shrink a pack over time;
that rate is the build agent's number.

### 2g. Status effects

The resistances are pre-renewal (`status.cpp:9620-9945`): rate × (1 − sc_def / 10000) −
sc_def2, rounded up to 10.

| effect | source | chance per LANDED skill hit (VIT 30, INT 1, LUK 1, Base 60) | duration | per minute from one engaged monster (FLEE 130) |
|---|---|---|---|---|
| Blind from a Familiar (lv 1) | sc_def (VIT + INT) × 50, sc_def2 LUK × 10 + 10 × (60 − 8) (`status.cpp:9755-9763`) | 11.6 % | 25.3 s | 0.012 |
| **Blind from a Drainliar (lv 3)** | the same, mob Lv 24 | **47 %** | 25.3 s | **0.53-0.61** |
| Silence from a Steel Chonchon (lv 2) | sc_def VIT × 100, sc_def2 LUK × 10 + 10 × (60 − 17) (`status.cpp:9691-9699`) | 23.6 % | 21.0 s | 0.026 |

- The effects apply only on a hit that lands (`skill.cpp:1213`).
- **Blind:** −25 % FLEE and HIT.
- **Silence:** no skills, so no Heal, no Cure and no re-cast of Auto Guard. Items still work.
- **Green Potion** cures Poison, Silence and Blind (db/pre-re/item_db_usable.yml:133, script
  141-143), as does Panacea (:315).

### 2h. The Crusader's offense against these species

For the build agent.

| species | DEF % / VIT DEF (pre-re monster: VIT + rnd(0, ⌊VIT/20⌋² − 1), `battle.cpp:4825-4832`) | Demon Bane 10 at Base 60 | 1H sword size fix | neutral sword vs its element | Holy (for reference) |
|---|---|---|---|---|---|
| Orc Zombie | 5 / 24 | **+60** | Medium 100 % | Undead 1: 100 % | 150 % |
| Orc Skeleton | 10 / 18 | **+60** | Medium 100 % | Undead 1: 100 % | 150 % |
| Familiar | 0 / 8 | no (Brute / Dark) | Small **75 %** | Dark 1: 100 % | 125 % |
| Drainliar | 0 / 24 | no | Small **75 %** | Dark 2: 100 % | 150 % |
| Steel Chonchon | 15 / 17 | no (Insect / Wind) | Small **75 %** | Wind 1: 100 % | 100 % |
| White Plant / Black Mushroom | 1 damage per hit | no | (n/a) | Earth 1: 100 % | 100 % |

- **Demon Bane:** + ⌊lv × (BaseLv / 20 + 3)⌋ against Undead ELEMENT or Demon race (`battle.cpp:2291-2293`).
  - It is a mastery: in pre-renewal it is added AFTER DEF (`battle.cpp:3781-3800`,
    `:4907-4912`), and then multiplied by the element.
  - Sword Mastery adds +4 / lv with a 1H sword (`battle.cpp:2332-2339`).
- **Size:** `db/size_fix.yml:40-42` (1hSword: Small 75, Medium 100, Large 75). `db/pre-re/size_fix.yml`
  overrides only Knuckle and Whip.
  - The size fix touches only the weapon's damage roll. It does not touch the STR base ATK or
    the masteries (`battle.cpp:2580-2585`, `:2622-2624`).
- **Element:** `db/pre-re/attr_fix.yml`, Level 1 block from line 35, Level 2 from 146.
  - Neutral vs Earth 1 :39, Wind 1 :41, Dark 1 :44, Undead 1 :46, Dark 2 :155.
  - Holy vs Earth 1 :105, Wind 1 :107, Dark 1 :110, Undead 1 :112, Dark 2 :221.
- **EXP per HP:**

  | species | EXP per HP |
  |---|---|
  | Drainliar | 0.37 |
  | Steel Chonchon | 0.21 |
  | Familiar | 0.18 |
  | Orc Skeleton | 0.14 |
  | Orc Zombie | 0.13 |
  | the plants | 0 |

## 3. The map for survival

### 3a. Warps

From `npc/warps/dungeons/orcsdun.txt`. The touch area is centre ± span.

| warp (line) | cell, span -> area | goes to | for the fighter |
|---|---|---|---|
| orc01-1 (:22) | (32,172), 3,1 -> x29-35 y171-173 | in_orcs01 30,180 (the way out) | **An escape hatch:** step on it and no monster follows (`mob_warp: 0`). The arrival from in_orcs01 is (32,170) (:21), one cell south of it |
| orc03 (:25) | (183,8), 4,2 -> x179-187 y6-10 | orcsdun02 21,185 (F2) | **Never walk onto it while fleeing:** it leads deeper. The arrival from F2 is (183,11) (:26) |

- The only mapflag is `nomemo` (npc/mapflag/nomemo.txt:344). There is no noteleport, so Fly Wing
  and Butterfly Wing work.
- `dynamic_mobs: yes`: the whole population spawns at once when the first player enters
  (monster.conf:254; FACTS.md section 1).

### 3b. Spawns

`npc/pre-re/mobs/dungeons/orcsdun.txt:16-26`; the effective respawns are from FACTS.md.

| species | n | where | respawn on the lab server |
|---|---|---|---|
| Orc Zombie | 80 | whole map | 10 @ 3 s, 30 @ 60 s, 40 @ 120 s |
| Familiar | 15 | whole map | 5 s |
| Steel Chonchon | 10 | whole map | 5 s |
| Orc Skeleton | 10 | whole map | 180 s |
| Drainliar | 5 | whole map | 5 s |
| Black Mushroom | 10 | (167,133) ±4 and (67,34) ±4 | 900 s |
| White Plant | 5 | (83,50) ±4 and (58,67) ±9 | 180 s |

**How a whole-map spawn is placed.** It takes a uniform random cell with x, y in [15, 184]
(`map_edge_size: 15`, misc.conf:192), retried until the cell is walkable (`map.cpp:1830-1847`,
`mob.cpp:1139-1153`).
- That band holds 9,181 of the 9,356 walkable cells.
- 110 whole-map monsters are aggressive (Orc Zombie 80, Familiar 15, Orc Skeleton 10,
  Drainliar 5): 0.012 per spawnable cell.

### 3c. The geometry for an escape-minded fighter

The data is client ∩ server walkability (`poring_dataset.walkable.load_both("orcsdun01")`; the 9,356
cells are identical to the local `both.npy`). The server's map cache has only types 0 and 1 here,
so every non-walkable cell is a wall: it blocks both walking and sight.

**The shape: a RING.**
- A single enclosed block of 4,006 non-walkable cells (x50-142, y59-136) sits in the middle.
- The walkable area is the wide corridor network around it: one component.
- 372 walkable cells border the block, so walking the ring is a full loop of roughly 340 cells
  (~50 s at 150 ms/cell).
- 27 smaller enclosed blocks are pillars you can circle around (the 8-connected ring of walkable
  cells around each):

  | pillar | where | ring |
  |---|---|---|
  | 64 cells | x40-55 y84-87 | 44 cells |
  | 30 cells | x104-109 y160-165, inside the N pocket | 28 cells |
  | 16 cells | x176-180 y28-31, inside the SE wing | 22 cells |
  | 16 cells | x55-59 y68-71 | 22 cells |
  | 16 cells | x54-57 y28-31 | 20 cells |

**Corridor widths.**
- The chessboard distance to the nearest wall has a median of 3 and reaches 11.
- **Only 313 cells (3.3 %) lie in a <= 2-cell-wide spot** (the shortest walkable run through the
  cell, horizontal, vertical or diagonal, is <= 2).
- They form 132 small pieces, 76 of them single cells. All the wider cells form ONE connected
  area, except one 4-cell bit. So **no narrow passage separates two parts of the map.**
- The largest narrow pieces are wall alcoves (dead-end slots):

  | alcove | where |
  |---|---|
  | 2 wide, 9 long (13 cells) | x35-36 y100-108 |
  | 12 cells | x52-59 y27-30 |
  | 11 cells | x32-37 y93-95 |
  | 8 cells | x27-28 y78-83 |
  | 8 cells | x143-144 y114-119 |
  | 8 cells | x52-57 y155-156 |
  | 7 cells | x140-142 y143-147 |
  | 13 cells | x60-65 y93-97 (joins only a 4-cell bit) |

  An alcove limits how many monsters can stand next to the player, but it has one way out.

**Dead ends: areas behind ONE opening.**
- The repo's region / door code (`scripts/map_zone_candidates.py` `regions` / `doors` /
  `pockets`) was run at several corridor scales.
- `core_min` k splits passages narrower than 2k − 1 cells.
- "Pocket" = cut off from the largest region by removing one door.

| candidate | cells | box | the one opening | depth (steps from the opening to the far end) | inside |
|---|---|---|---|---|---|
| **SE wing** (k = 5..7) | 1,625 (k5, opening at its south end) to 1,758-1,838 (k6-7 / k5, opening at its north end) | x139-187 y7-70..94 | the 9-wide N-S throat x163-171, y~62-95 (rows checked: walkable x163-171 at every even y 64-98) | 63-87 to (180,7) | the warp to F2 (orc03); the 16-cell pillar; one of the 3 densest aggro areas (x155-172 y25-45, section 3d) |
| **N pocket** (k = 4..5) | 458 (and its inner end, 55 cells x86-97 y165-172) | x86-117 y148-172 | 10 wide at x109-117 y148-151 | 24 to (86,170) | no warp; the 30-cell pillar (you can circle it) |
| **NW entrance wing** (k = 4..6) | 466-651 | x27-69 y137-172 | 10-17 wide, at x55-67 y136-155 (it depends on the scale) | 28-38 to (27,159) | the EXIT warp orc01-1 (x29-35 y171-173) and the arrival cell (32,170): a dead end whose way out is the warp itself |

**Against prt_fild08's zones.**
- In `config/map_zones/prt_fild08.yaml`, C1 was a 2,391-cell room behind a **2-cell** door.
- It was justified by banked runs:
  - the bot circled inside up to 849 s;
  - 374 s per run-hour, 37.5 % of v51 run 4;
  - 0.24 vs 1.72 kills/min inside vs outside (competition.md "Top causes, re-ranked after v51");
  - and by `map_zones.py prove`.
- **On orcsdun01 the same finder at the same settings (`--max-door 4 --min-room 150`) returns 0
  candidates.** No single door that narrow cuts anything off. The only 4-wide doors are the pair
  into the 40-cell bit x69-76 y27-33. There are no banked hunt runs here yet.
- So the candidates above rest on geometry only. Their risk is being CORNERED by a pack in a
  wide dead end, not failing to find a narrow door.
- No zones file is proposed. If one is wanted, the evidence would come from the first hunt runs:
  time and deaths in the SE wing and the N pocket.
- One thing to settle before the first run either way: whether the runner's warp handling already
  keeps the bot off orc03's area (x179-187 y6-10). The stand grid excludes warp spans.

### 3d. The aggro picture

**The computation (a scratch script, since deleted; method below).** For every walkable cell c, count the spawnable
cells s that can aggro c.
- s lies in [15, 184]², walkable, Chebyshev distance <= 10.
- The straight line from s to c (rAthena's `path_search_long` stepping, `path.cpp`) crosses no
  wall.
- The walk path is <= 10 steps (8-way, no corner cutting; walls only, as `path_search(...,
  CELL_CHKWALL)` counts it).
- E[aggressive in reach at c] = 110 × count / 9,181. Spawns are uniform over the band (3b), and
  the stationary spread of random-walking idle monsters is assumed to stay close to that
  (UNVERIFIED).

| | in the 21 x 21 box only | + line of sight + path <= 10 (the server's rule) |
|---|---|---|
| spawnable cells in reach: mean / p10 / p50 / p90 | 290.7 / 190 / 285 / 409 | 266.3 / 166 / 256 / 391 |
| **aggressive monsters in reach: mean / p10 / p50 / p90 / max** | 3.48 / 2.28 / 3.41 / 4.90 / 5.28 | **3.19 / 1.99 / 3.07 / 4.68 / 5.28** |
| P(at least 1), Poisson | 0.952 | **0.932** |

| species | in reach per cell |
|---|---|
| Orc Zombie | 2.32 |
| Familiar | 0.44 |
| Orc Skeleton | 0.29 |
| Drainliar | 0.15 |
| Steel Chonchon (not aggressive) | 0.29 |

A path limit of 12 (walking monsters) changes the mean only from 3.19 to 3.20.

**The densest areas (E >= 4.7, the top decile)** are the open halls. They are the worst places to
fight a pack:

| area | cells | mean E |
|---|---|---|
| x38-75 y47-82 (around White Plant (58,67)) | 544 | 4.95 |
| x155-172 y25-45 (the SE wing) | 208 | 4.91 |
| x149-161 y115-133 | 142 | 4.87 |

**The sparsest areas (E <= 2.0)** are corners and dead ends. Few monsters reach them, and they have
few exits:

| area | mean E |
|---|---|
| x175-187 y7-37, by the F2 warp; below y 15 nothing spawns | 1.35 |
| x67-76 y27-38 | 1.37 |
| x46-62 y27-34 | 1.12 |
| x86-97 y164-172, the end of the N pocket | 1.42 |
| x27-37 y166-172, the exit-warp corner | 1.68 |

At the arrival cells:

| cell | E |
|---|---|
| (32,170), from in_orcs01 | 1.76 |
| (183,11), from F2 | 1.01 |

**While walking.** One orthogonal step brings on average 11.35 new spawnable cells into the 21 × 21
box.
- That is **0.136 new aggressive monsters per cell walked**: one per ~7.4 cells, ~0.9 per second
  at full walking speed.
- This is box-only, an upper bound. The line-of-sight / path rule removed ~8 % in the static
  case.

**A Fly Wing** lands on a uniform passable cell in the same [15, 184] band, never on a warp area
(`pc.cpp:7208-7225` `pc_randomwarp`; `teleport_on_portal: no`, skill.conf:356).
- **Landing:** E[aggressive in reach] = **3.23**.
- P(>= 1) = **93.6 %**, P(0) = 6.4 %, P(>= 3) = 59.3 %.

## 4. What this means for survival

**1. The real threats, ranked by damage to an AGI Crusader.**
1. **Drainliar.** 52 % hit at FLEE 130, one alone ~16 HP/s, and Blood Drain always lands.
   - Its Blind (47 % per landed blind hit) cuts FLEE 25 % for ~25 s, and every Orc's hit chance
     with it.
   - Only 5 exist, but they respawn in 5 s.
2. **Orc Skeleton.** The heaviest hits (normal 146 avg at DEF 20 / VIT 30 without DP, 92 with DP).
   - Critical Slash: 236 flat, unavoidable.
   - It walks 5 cells/s, nearly the player's 6.67.
3. **Orc Zombie.** Weak alone at high FLEE: 6.5 HP/s, almost all of it from criticals.
   - But there are 80 of them, 2.3 within reach of an average spot, and 10 respawn every 3 s. They
     supply the attacker count.
   - Slow (2.5 cells/s): the one monster you can always walk away from.
4. **Familiar and Steel Chonchon.** They barely hurt (1 HP; ~1 HP/s).
   - But each one attacking you raises n, so they make the Orcs and Drainliars hit.
   - The Chonchon's Silence (23.6 % per landed silence hit, 21 s) blocks Heal and Auto Guard.
   - Chonchons come in groups (Assist, 11 cells). Both match the player's walking speed.

**2. Expected HP loss at FLEE 130** (DEF 20, VIT 30, DP 10; monster damage only, before the
player's kills):

| situation | HP/min |
|---|---|
| typical encounter | mean ~2,400; p50 ~1,430; p90 ~5,500 |
| 3 Orc Zombies (A) | ~1,430 |
| 3 OZ + 2 OS (C) | ~6,200 |
| + 1 Drainliar (E) | ~9,800 |
| the full 8-ring (F) | ~14,900 |
| A, blinded (normal attacks) | ~1,520 |

**MaxHP for scale.** Pre-renewal: base HP × (1 + VIT / 100) + bonuses (`status.cpp:3511-3549`, `status_calc_maxhp_pc`).
- The Crusader's Lv 60 base HP is 2,470 (db/pre-re/job_basepoints.yml:3060-3061).
- So VIT 25 / 30 / 35 gives 3,087 / 3,211 / 3,334, and **5,087 / 5,211 / 5,334 with Faith 10
  (+2,000)**, before gear.
- At 5,211 HP, the time to death:

  | situation | time to death |
  |---|---|
  | typical mean (~40 HP/s) | ~130 s |
  | pack C | ~50 s |
  | pack E | ~32 s |
  | pack F | ~21 s |

**3. What the HP-threshold logic should be built on.**
- **Count the attackers, not only HP.** n >= 3 switches on both penalties. n >= 5 roughly
  multiplies the damage by 10 compared with n = 2-3.
  - A rule on "monsters adjacent / attacking" reacts BEFORE the HP drop.
  - A Drainliar in the pack, or Blind on the player, should count like 2-3 more attackers.
- **The reaction budget.** The bot's frames lag the server ~0.5 s (memory: frames lag), plus its
  decide-and-press time.
  - At pack F's 249 HP/s, every second of latency costs ~250 HP; at pack C's, ~100.
  - So a threshold should be about **HP_min ≈ pack DPS × (latency + action time) × a safety
    factor**, not a fixed %. With F and ~1.5 s total that is ≥ ~400 HP before any factor.
- **Potions vs Fly Wing.**
  - **Potions: throughput is not the limit.** `item_use_interval: 100` ms (items.conf:68) lets the
    server take up to 10 items a second.
    - A White Potion heals rand(325, 405) × (100 + 2·VIT + 10·HP-Recovery lv) / 100
      (item_db_usable.yml:123; `pc.cpp:10700`).
    - At VIT 30 that is avg 584 (520-648) without Increase HP Recovery, and avg 949 (845-1,053)
      with lv 10.
    - So holding pack F needs ~0.26-0.43 White Potions a second: ~16-26 a minute, 240-390 weight
      (15 each; Buy 1,200 z).
    - The limits are **stock, weight, zeny and the bot's input rate**, not the server.
  - **Fly Wing** (item_db_usable.yml:1035-1043, AL_TELEPORT 1): an instant random cell. Every
    current attacker loses the player, and none follows.
    - But the landing has 3.2 aggressive monsters in reach on average (P(>= 1) 93.6 %). It
      exchanges the current pack for a typical one (~40 HP/s mean if all engage).
    - **It pays when the current pack is far above typical** (n >= 5, a Drainliar plus Blind, a
      Skeleton pair), or when potion stock is the binding constraint.
    - It is a poor answer to 2-3 Orc Zombies: pots or walking away (2.5 cells/s) are cheaper.
  - **Butterfly Wing** (:1045-1053, AL_TELEPORT 3) and the exit warp orc01-1 are the only real
    exits. The warp only helps from the NW wing.
- **Walking away.** It works against Orc Zombies, Orc Skeletons and Drainliars (slower than the
  player). It does not work against Familiars and Steel Chonchons (same speed).
  - **Each landed hit stops the walk** ("officially, when getting hit, you just get stopped on the
    nearest cell center", battle.conf:35-40).
  - It adds a can't-walk delay of `pc_damage_walk_delay_rate` 20 % × dmotion (battle.conf:45;
    `battle.cpp:274-297`). dmotion = clamp(800 − 4·AGI, 400, 800) (`status.cpp:6438-6439`), so
    ~88-96 ms at AGI 80-90.
  - Under a pack the bot must re-issue the move after every hit.
- **Where not to fight.**
  - Don't fight deep in the SE wing (63-87 steps from its only throat, a dense hall, and the F2
    warp at the end), nor in the N pocket.
  - In the open halls (E ≈ 4.9) the attacker count climbs fastest.
  - The ring corridors and the pillars allow loops.
- **Detection hint.** The two FLEE-proof Orc skills are visible before they hurt: Critical Slash
  has a 500-ms cast (mob_skill_db.txt:808-815). Whether the client draws it is UNVERIFIED.

## UNVERIFIED

1. **The running server's configuration.** No container was inspected. The claim of no battle
   override rests on the repo templates and the empty upstream import template. The live
   135-unit count (orcsdun01-detector.md 2a) supports the npc side only.
2. **The Angry-state skill cadence** (one roll per second between attacks). It comes from reading
   `mob.cpp:1873-1888`, not from a measurement. The berserk numbers (one roll per attack) are the
   lower bound and are given beside them.
   - A banked session with a non-immune character, or the sniffer's skill packets from monsters,
     would measure it.
3. **The pack figures assume every member attacks continuously from the first second.** Chasing
   time, the player's kills, Lucky Dodge (~1 %) and card or gear reductions are not modelled.
4. **The stationary distribution of idle monsters is taken as uniform**, like the spawn rule.
   - Idle monsters random-walk.
   - The collection blocks' per-species unit-seconds near the GM (detector doc 2a) could check
     this. Not done here.
5. **Monsters' give-up rules while chasing** (`mob.cpp:1904-1936`, `:2195-2211`): only the
   Angry-state rule (it drops the target when it is not reachable within ChaseRange 12) was read
   closely.
6. **Fly Wing and Butterfly Wing under Silence.** Not checked in code (an item skill, not a cast).
7. **Endure (SM_ENDURE)** as a way to walk through hits without stopping: not checked at this
   commit.
8. **Whether the client draws a monster's cast bar** for Critical Slash: not checked.
9. **The weight capacity and HP / SP of the actual build.** That is the build agent's job; the
   MaxHP above uses Faith 10 and no gear.
10. **The Base-60 numbers.** DP 54 and Demon Bane +60 assume exactly Base 60 and level 10 in each
    skill.

## How it was computed (scratch only; nothing data-bearing is committed)

The scratch work lived in `/dev/shm/poring-lab-tmp/crusader/dungeon/`. **It was deleted at the end
of the task (2026-10-21), as the brief asked**, so re-deriving a number means re-running the method
below:
- **The tables and DPS:** the section 2a formulas, evaluated exactly over every damage roll.
- **The skill-aware DPS:** a 100-ms-tick simulation of the mob skill rolls (berserk = one roll per
  attack opportunity; angry = one roll per 1,000 ms), with the rates, casts and delays of section
  1c.
- **The typical encounter:** 20,000 Poisson draws.
- **Aggro (3d):** a per-cell count over the server's wall map, with rAthena's line stepping and an
  8-way, no-corner-cutting BFS.
- **Geometry (3c):**
  - `scripts/map_zone_candidates.py` `regions` / `doors` / `pockets` at `core_min` 3-8;
  - a run-length width test for the <= 2-cell spots;
  - the enclosed non-walkable components for the pillars.
- **The upstream GPL sources:** fetched read-only at e985006 for reading only; deleted with the
  rest.

The walkability is client-derived (the GAT) and stays in /dev/shm. Only cell coordinates and counts
appear here.
