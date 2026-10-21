---
doc_type: design
hypothesis: "A Base 60 / Job 50 Crusader (Batt's skill list, AGI > STR > VIT > DEX, one-handed sword + shield from NPC shops) is buildable on the pinned pre-renewal lab server, and its numbers can be computed from the pinned source before anything is built."
status: PROPOSED (offline research only; nothing built, no GM command run, no live action; numbers derived from the pinned source and db, 2026-10-21 16:36 ICT)
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, ../adr/0006-sanctioned-test-environments.md]
next_action: "Batt: decide (a) whether the GM test account gets the extra commands the GM route needs (jobchange, mount_peco, questskill, zeny; group 20 has none of them today, section 1d), (b) the stat split (section 3c), (c) buy the gear or @item it (section 4)."
title: "A Crusader test character for orcsdun01: job path, skill points, stats at Base 60 / Job 50, shop gear (pinned pre-renewal rAthena)"
date: 2026-10-21
owner: Batt
---

# A Crusader test character for Orc Dungeon F1 (orcsdun01)

Batt's scenario: a dedicated **Crusader** test character, built with GM commands in the lab, that
hunts Orc Dungeon F1. This doc answers four questions from the pinned server:

1. the job path and the skill points;
2. the skills;
3. the stats at Base 60 / Job 50;
4. the gear from NPC shops.

It closes with the discrepancies against Batt's list and an UNVERIFIED list.

**Sources and conventions.**

- **Server.** PRE-RENEWAL rAthena at `e985006171d2eb320ee512a653f4c83aea3d81b6`.
  - The lab image builds with `--enable-prere=${PRERE}` (`services/rathena/Dockerfile:51`), and
    `.env.example:70` sets `RATHENA_PRERE=yes`.
  - So every formula below is the `#ifndef RENEWAL` (or `#else`) branch. Where a line is shared by
    both branches, the doc says so.
- **`db/` and `npc/`** were read from the local partial copy of the pinned tree.
  - `db/pre-re/*.yml` overrides `db/*.yml` through each file's `Footer: Imports`.
  - `db/import-tmpl/*.yml` has no body entries, so `db/import` adds nothing.
- **`src/` and `conf/`** were fetched from GitHub at the pin and read as text.
  - Citations look like `status.cpp:2410`, which means `src/map/status.cpp` line 2410 at the pin.
- **The lab's overrides.**
  - The lab's conf overrides are only the `services/rathena/conf/import/*.tmpl` files: char, inter,
    log, login and map conf. None of them sets a battle setting.
  - `conf/import-tmpl/battle_conf.txt` is empty. So every battle setting below is the upstream
    default in `conf/battle/*.conf` at the pin.
- **Which scripts load.** The pre-re map server loads `npc/pre-re/scripts_main.conf`
  (`map.cpp:4263-4267`, `#else` branch). That file imports both the common `npc/scripts_*.conf`
  and the pre-re ones (`npc/pre-re/scripts_main.conf`).
- **Shops.** Every shop below was found by following that include chain: 13 conf files, 532 NPC
  files. Each line was checked against `item_db`.
- **Units.**
  - Weights are in-game weight (the db value / 10) unless a line says "db units"; the db stores
    10 = 1 in-game weight.
  - Times are in ms unless noted.
- **No live check.** Nothing here was checked on the live server; see UNVERIFIED.

---

## 1. Job path and skill points

### 1a. Job levels and skill points per job

| Job | Max job level | Skill points earned | Source |
|---|---|---|---|
| Novice | 10 | 9 (Job 1 → 10) | `db/pre-re/job_exp.yml:567` `MaxJobLevel: 10` |
| Swordman | 50 | 49 (Job 1 → 50) | `job_exp.yml:603` |
| Crusader | 50 | 49 (Job 1 → 50) | `job_exp.yml:737` |
| **Total** | | **107** | |

- **Points per level.** Each job level gives one skill point: `sd->status.skill_point ++` per
  level in `pc_checkjoblevelup` (`pc.cpp:8333-8334`).
- **`@joblevelup N`** adds exactly N points (`atcommand.cpp:1763-1764`), the same as levelling.
- **A job change resets the job level, not the points.** `pc_jobchange` sets
  `sd->status.job_level=1` (`pc.cpp:10920`) and leaves `skill_point` untouched, so unspent points
  carry over.

### 1b. Job-change requirements (the NPCs the pre-re server loads)

**Novice → Swordman.** Swordman Association, `izlude_in,74,172` (`npc/pre-re/jobs/1-1/swordman.txt:40`).

- It needs `F_CanChangeJob` (`swordman.txt:141`). That function returns true when `NV_BASIC > 8`,
  i.e. Basic Skill 9 (`npc/other/Global_Functions.txt:626-628`), because `basic_skill_check: yes`
  (`conf/battle/player.conf:47`).
- It also needs the Swordman test passed: `job_sword_q == 4` (`swordman.txt:155-158`).
- No job-level check beyond that. Basic Skill 9 itself costs 9 points, i.e. Novice Job 10.
- No unspent-points check.

**Swordman → Crusader.** Michael Halig, "Senior Crusader", `prt_castle,45,169`
(`npc/pre-re/jobs/2-2/crusader.txt:11`, a duplicate of the common `npc/jobs/2-2/crusader.txt`).
Both files load: `npc/scripts_jobs.conf` loads the common one and `npc/pre-re/scripts_jobs.conf:16`
the pre-re one.

- **Job Level ≥ 40**: `if(JobLevel < 40)` refuses (`npc/jobs/2-2/crusader.txt:119`).
- **All skill points spent**: `if (SkillPoint)` refuses, both at the start (`:131`) and at the
  final change (`:278`).
- Then the item task, the four tests, and the change (`:289`).
- Reward: 12 White Potions at Job 50, 6 otherwise (`:302-303`). The script stores `.@Joblevel` and
  tests `.@JobLevel`, but rAthena's variable lookup is case-insensitive (`script.cpp:694-695`,
  `strcasecmp`), so the Job 50 branch does work.

### 1c. Can Crusader points buy Swordman skills? Yes, after every first-class point is spent

- **The tree.** The Crusader tree **inherits** the Swordman tree (`skill_tree.yml:827-830`,
  `Inherit: Novice, Swordman`).
- **The limit.** `player_skillup_limit: yes` (`player.conf:35`). The comment there says: "forces
  skill points gained from 1st class to be put into 1st class skills".
- **How it is implemented** (`pc_calc_skilltree_normalize_job_sub`, `pc.cpp:2893-2977`).
  1. It counts the points **spent**, excluding quest skills (`pc.cpp:2518-2541`).
  2. While fewer than 9 are spent, the usable tree is the Novice tree (`:2901-2907`).
  3. Then, while fewer than `change_level_2nd - 1` are spent, it is the Swordman tree
     (`:2925-2929`).
  4. Once both are spent, it is the full Crusader tree, which includes the Swordman skills.
- **`change_level_2nd`** is the job level at the moment of the Swordman → Crusader change
  (`pc.cpp:10889-10892`).
- **Consequence:**
  - **Change at Swordman Job 50 → 49 first-class points.** Once 9 + 49 = 58 points are spent, a
    Crusader point can buy the 50th Swordman level.
  - **At Job 49:** Batt's list still fits, with 0 points spare.
  - **Below Job 49:** it does not fit. 9 + 50 + 47 = 106 points are needed, and the pool is
    9 + (J−1) + 49.
- **On the GM route,** run `@joblevelup` to Swordman Job 50 *before* `@jobchange 14`, or
  `change_level_2nd` records the lower level. Job ids: Swordman = 1, Crusader = 14 (`mmo.hpp:888-903`).

### 1d. The GM route, and what group 20 can do today (read only, nothing run)

`@baselevelup` and `@joblevelup` grant points exactly like normal levelling (section 3a, `atcommand.cpp:1684`, `:1764`).

| Step | Command | Permission | Group 20 today (`services/rathena/conf/import/groups.yml`) |
|---|---|---|---|
| Job levels | `@joblevelup N` | joblevelup | yes |
| Base levels | `@baselevelup N` | baselevelup | yes |
| Stat / skill reset | `@streset` / `@skreset` | resetstat / resetskill | yes |
| Items | `@item` | item | yes |
| Job change | `@jobchange <id>` (alias `@job`, `conf/atcommands.yml:677-679`; `atcommand.cpp:1203`) | jobchange | **no** |
| Peco | `@mount_peco` (aliases `@mount`, `@mountpeco`, `atcommands.yml:966-971`). Refuses without KN_RIDING (`atcommand.cpp:5073`) | mount_peco | **no** |
| Quest skills | `@questskill <id>` (`atcommand.cpp:11591`) | questskill | **no** |
| Zeny | `@zeny` | zeny | **no** |

**What this means:**

- Without `jobchange`, the only route is the two job quests.
  - The Swordman test.
  - The Crusader quest: items plus four tests at Prontera Castle.
- Adding commands to group 20 is a groups.yml change, which is Batt's call. This doc does not make it.
- Stats and skills are spent from the client's own windows, at the costs below. No command is needed.

---

## 2. Skills

### 2a. Swordman (Batt's list: 50 points, against 49 earned)

| Skill (internal name, id) | Batt | Max | Prerequisite (`skill_tree.yml`) | Satisfied by the list? |
|---|---|---|---|---|
| Sword Mastery (SM_SWORD, 2) | 10 | 10 (`:59-60`) | none | — |
| Increase HP Recovery (SM_RECOVERY, 4) | 10 | 10 (`:66-67`) | none | — |
| Bash (SM_BASH, 5) | 10 | 10 (`:68-69`) | none | — |
| Provoke (SM_PROVOKE, 6) | 5 | 10 (`:70-71`) | none | — |
| Magnum Break (SM_MAGNUM, 7) | 5 | 10 (`:72-73`) | SM_BASH 5 (`:75-76`) | yes (Bash 10) |
| Endure (SM_ENDURE, 8) | 10 | 10 (`:77-78`) | SM_PROVOKE 5 (`:80-81`) | yes (Provoke 5) |
| **Sum** | **50** | | | **one more than 49** |

The ids come from `db/pre-re/skill_db.yml`: `:150`, `:160`, `:164`, `:225`, `:260`, `:327`.

**Novice:** Basic Skill (NV_BASIC, id 1, `skill_db.yml:146`), max 9 (`skill_tree.yml:46-47`). It costs all 9 Novice points.

**Quest skills.** These are obtainable in the pinned pre-re server. All three are `IsQuest`
(`skill_db.yml:5092`, `:5098`, `:5105`). `quest_skill_learn: no` (`player.conf:39`), and they cost
no skill points (`pc.cpp:2528`).

| Skill (id) | NPC (map,x,y; file) | Job level | Items taken |
|---|---|---|---|
| Moving HP-Recovery (SM_MOVINGRECOVERY, 144) | Knight De Thomas, `izlude_in,175,130` (`npc/pre-re/quests/skills/swordman_skills.txt:15`, a duplicate of `::KnightDeThomas` in `npc/quests/skills/swordman_skills.txt:20`) | Swordman Job ≥ 35, or already Knight/Crusader (`:21`) | 200 Empty Bottle (713) + 1 Wing of Moth (1058) (`:30`, `:44-46`) |
| Fatal Blow (SM_FATALBLOW, 145) | Leon Von Frich, `prt_in,75,88` (`swordman_skills.txt:152`) | Job ≥ 25, or Knight/Crusader (`:153`) | 10 Fire Arrow (1752), 10 Silver Arrow (1751), 1 Banana Juice (532), 30 Tentacle (962), 5 Royal Jelly (526) (`:163`, `:174-179`) |
| Auto Berserk (SM_AUTOBERSERK, 146) | Juan, `prt_in,94,57` (`swordman_skills.txt:305`) | Job ≥ 30, or Knight/Crusader (`:316-324`) | 35 Powder of Butterfly (924), 10 Horrendous Mouth (958), 10 Decayed Nail (957), 10 Honey (518) (`:330`, `:341-345`) |

All three are loaded: `npc/pre-re/scripts_jobs.conf:21` (the pre-re file) and `npc/scripts_jobs.conf` (the common file).

### 2b. Crusader (Batt's list: 47 points)

| Skill (internal name, id) | Batt | Max | Prerequisite (`skill_tree.yml`) | Satisfied? |
|---|---|---|---|---|
| Faith (CR_TRUST, 248) | 10 | 10 (`:866-867`) | none | — |
| Cure (AL_CURE, 35) | 1 | 1 (`:844-845`) | **CR_TRUST 5** (`:847-848`) | yes (Faith 10) |
| Divine Protection (AL_DP, 22) | 10 | 10 (`:849-850`) | **AL_CURE 1** (`:852-853`) | yes (Cure 1) |
| Demon Bane (AL_DEMONBANE, 23) | 10 | 10 (`:854-855`) | AL_DP 3 (`:857-858`) | yes |
| Auto Guard (CR_AUTOGUARD, 249; db description "Guard") | 10 | 10 (`:868-869`) | **none** | — |
| Peco Peco Riding (KN_RIDING, 63) | 1 | 1 (`:832-833`) | SM_ENDURE 1 (`:835-836`) | yes (Endure 10) |
| Cavalier Mastery (KN_CAVALIERMASTERY, 64) | 5 | 5 (`:837-838`) | KN_RIDING 1 (`:840-841`) | yes |
| **Sum** | **47** | | | |

The ids come from `skill_db.yml`: `:6687`, `:1722`, `:1286`, `:1291`, `:6691`, `:2315`, `:2320`.

- **Learning order this forces:** Faith ≥ 5 → Cure 1 → Divine Protection ≥ 3 → Demon Bane.
- **Endure** must be learned before Riding. It is (in the Swordman phase).
- **No prerequisite is missing from Batt's list.**

**Quest skill Shrink** (CR_SHRINK, id 1002, `IsQuest`, `skill_db.yml:16790`; it needs a shield
equipped). It is obtainable in the pinned server through `npc/quests/skills/crusader_skills.txt`
(loaded by `npc/scripts_jobs.conf`). The quest is a chain:

1. Ford, `geffen,110,117` (`:16`).
2. Soldier, `gef_fild13,297,242` (`:280`): give 1 Red Potion (`:361`, `:387`).
3. Pastor, `prt_church,87,127` (`:581`): give 20 Sticky Mucus, 1 Unripe Apple, 5 Jellopy, 1 Grape,
   1 Coal, 3 Cyfar and 3 Empty Bottle (`:654`, `:684-690`).
4. Back to the Soldier. **The skill is granted with a 2-in-5 chance** (`rand(1,5)` is 1 or 5,
   `:466-476`). A failure sends you back to the Pastor to retry (`:539`, `:781`).

There is no job-level requirement anywhere in the script.

### 2c. Points: the corrected total

| | Points |
|---|---|
| Pool at Crusader Job 50 (changed at Swordman Job 50) | 9 + 49 + 49 = **107** |
| Basic Skill 9 | 9 |
| Swordman list | 50: **49 Swordman points + 1 Crusader point** (section 1c) |
| Crusader list | **47** |
| Crusader points used | 47 + 1 = **48** |
| **Left** | **1** (of the Crusader's 49) |

Batt's "the Crusader tree uses 48, 1 left (of 49)" is **right if the 48 includes the one
Swordman-overflow point**. The Crusader skills alone are 47, not 48 (see DISCREPANCIES).

### 2d. Riding a Peco Peco (pinned pre-re)

- **Movement.** Riding sets the haste value to 25 (`status.cpp:8052-8053`). The speed is then
  `speed * speed_rate / 100` with `speed_rate = 100 − 25` (`:8202`, `:8213-8214`).
  - So the default walk speed 150 ms per cell (`mmo.hpp:93`) becomes **112 ms per cell**.
  - That is about 34 % more cells per second.
- **ASPD penalty.** Riding adds `500 − 100 × CavalierMastery` to `aspd_rate`, whose base is 1000
  (`status.cpp:4632-4633`, `#ifndef RENEWAL_ASPD`).
  - Cavalier Mastery 0: **×1.5 attack delay**.
  - Cavalier Mastery 5: **no penalty**.
- **Weight.** +1000 in-game weight (+10000 in db units) with KN_RIDING (`status.cpp:3680-3681`).
- **Size.** `character_size: 0` (`player.conf:182`), so riding does **not** make the player Large
  (`status.cpp:3830`).
- **Getting a Peco.**
  - **NPC:** Peco Peco Breeder#cru at `prontera,232,318` (`npc/merchants/renters.txt:95`, loaded
    by `npc/scripts_athena.conf:151`).
    - It costs **3500 zeny** (`:96`).
    - It needs KN_RIDING (`:120`).
  - **GM command:** `@mount_peco` (`@mount`), which needs the permission (section 1d).

---

## 3. Stats at Base 60 / Job 50

### 3a. Status points

- **At creation:** 48 points (`charserv_config.start_status_points = 48`, `char/char.cpp:2811`).
  - They are used at `char.cpp:1460`, in the `PACKETVER >= 20120307` branch; the lab's
    `PACKETVER=20211103`.
  - All six stats start at 1 (`char/char_clif.cpp:1279-1284`, `PACKETVER >= 20151001`).
  - Neither `conf/char_athena.conf` nor the lab's `char_conf.txt.tmpl` sets `start_status_points`.
- **The table:** `db/pre-re/statpoint.yml` gives the TOTAL at each level, Level 1 = 48
  (`:35-36`) and **Level 60 = 555** (`:153-154`).
  - A level-up adds `table(L+1) − table(L)` (`pc.cpp:8755-8764`, used at `pc.cpp:8258`).
  - `@baselevelup` uses the same function (`atcommand.cpp:1683-1684`), so it grants identical points.
  - `@streset` sets the points back to `table(BaseLv)` = 555 (`pc.cpp:9358`).
- **Available at Base 60: 555** (48 at creation + 507 from levels).
- **Raise cost, pre-re:** `PC_STATUS_POINT_COST(x) = 1 + (x + 9) / 10`, integer division
  (`pc.cpp:8803`, `#else` of `RENEWAL_STAT`). It is summed over each step x → x+1
  (`pc.cpp:8809-8829`).
  - Steps from 1 to 10 cost 2 each, 11-20 cost 3, 21-30 cost 4, 31-40 cost 5, 41-50 cost 6, and
    51-60 cost 7.
  - Cumulative cost from 1: to 10 = 18, to 17 = 38, to 18 = 41, to 20 = 47, to 24 = 62,
    to 25 = 66, to 30 = 86, to 32 = 95, to 38 = 125, to 39 = 130, to 45 = 164, to 50 = 194,
    to 55 = 228, to 58 = 249, to 60 = 263.
- **Cap:** `max_parameter: 99` (`player.conf:114`).

### 3b. Crusader job bonus at Job 50

The job bonus totals are summed from `db/pre-re/job_stats.yml:771-840`, the Crusader BonusStats,
levels 1-50. The loader accumulates them per level (`pc.cpp:14322-14333`). They are added on top
of the allocated stats (`status.cpp:4249-4266`, then `:4291-4301`).

| STR | AGI | VIT | INT | DEX | LUK | total |
|---|---|---|---|---|---|---|
| +7 | +2 | +7 | +6 | +3 | +5 | 30 |

### 3c. Fitting Batt's estimate (AGI ~60, STR ~45, VIT ~25, DEX ~20, INT 1, LUK 1)

**Reading 1: the targets are the ALLOCATED base stats.** They all fit:

| | base | cost | final with job bonus |
|---|---|---|---|
| STR | 45 | 164 | 52 |
| AGI | 60 | 263 | 62 |
| VIT | 25 | 66 | 32 |
| INT | 1 | 0 | 7 |
| DEX | 20 | 47 | 23 |
| LUK | 1 | 0 | 6 |
| **spent** | | **540** | **15 points left over** |

**Reading 2: the targets are the FINAL stats.**

- The base stats are STR 38, AGI 58, VIT 18, INT 1, DEX 17, LUK 1.
- That spends 453 points and leaves **102** over.
- The final stats are STR 45, AGI 60, VIT 25, INT 7, DEX 20, LUK 6. INT and LUK come out above 1
  because of the job bonus.

**The recommended split (MAIN) is Reading 1, with the 15 spare kept unspent.** That spare is for
Batt's re-spec on hit rate.

Alternatives near it (base stats; each column uses at most the 555 points):

| Variant | STR | AGI | VIT | INT | DEX | LUK | spent | left |
|---|---|---|---|---|---|---|---|---|
| MAIN | 45 | 60 | 25 | 1 | 20 | 1 | 540 | 15 |
| MAIN + DEX | 45 | 60 | 25 | 1 | 24 | 1 | 555 | 0 |
| ALT B (+DEX) | 45 | 55 | 25 | 1 | 32 | 1 | 553 | 2 |
| ALT C (++DEX) | 45 | 50 | 25 | 1 | 39 | 1 | 554 | 1 |
| Reading 2 | 38 | 58 | 18 | 1 | 17 | 1 | 453 | 102 |

### 3d. Formulas used (pre-re)

- **ASPD (amotion), in three steps:**
  1. `amotion = BaseASPD[weapon]`. For a Crusader with a 1H sword this is **500**
     (`db/pre-re/job_aspd.yml:236-245`; `status.cpp:2405-2406`).
  2. Then `amotion −= amotion × (4·AGI + DEX) / 1000`, integer arithmetic (`status.cpp:2410`).
  3. Then `amotion = amotion × aspd_rate / 1000` (`status.cpp:6397`).
- **No shield penalty in pre-re.** The job_aspd loader adds a shield column only `#ifdef RENEWAL`
  (`pc.cpp:13950-13955`), and the pre-re branch of `status_base_amotion_pc` never reads the shield
  (`status.cpp:2400-2414`).
- **Attack interval.** `adelay = 2 × amotion` (`status.cpp:6417`). It is used as the attack delay
  in `unit.cpp:1893`, `:1970`.
- **Client ASPD** = `(2000 − amotion) / 10` (`status.hpp:61-67`).
- **ASPD cap.** `max_aspd: 190` (`player.conf:80`), converted at `battle.cpp:8965` and applied as
  an amotion floor of 100 (`status.cpp:6415`). None of the variants is near it.
- **Max HP:**
  - `BaseHp[60] × (1 + VIT_final/100)`, then + Faith 200/level (`status.cpp:3511-3540`;
    `:3524`; `:3150-3151`).
  - The Crusader's `BaseHp` at level 60 is **2470** (`db/pre-re/job_basepoints.yml:3060-3061`).
    The table is used because `HP_SP_TABLES` is defined (`src/config/core.hpp:49`).
  - `hp_rate: 100` (`player.conf:13`).
- **Max SP:** `BaseSp[60] × (1 + INT_final/100)`, with `BaseSp[60]` = **292**
  (`job_basepoints.yml:8136-8137`; `status.cpp:3575`). No Crusader skill adds SP
  (`status.cpp:3298-3330`).
- **Status ATK (batk), for a melee weapon:**
  - The formula is `STR + (STR/10)² + DEX/5 + LUK/5` (`status.cpp:2479-2481`, pre-re `BL_PC`
    branch).
  - Players have batk because `enable_baseatk: 0x9` (`conf/battle/battle.conf:13`).
- **Weapon damage per normal hit:**
  - A random value in `[DEX × (80 + 20·WeaponLevel)/100, WeaponATK)`, capped at WeaponATK.
  - Then × the size modifier, then + batk (`battle.cpp:2545-2552`, `:2571`, `:2582`,
    `:2622-2624`).
- **HIT** = BaseLv + DEX; **FLEE** = BaseLv + AGI (`status.cpp:2704-2711`, pre-re `#else`).
- **Soft DEF (def2)** = VIT; **soft MDEF** = INT + VIT/2 (`status.cpp:2712-2719`).
- **Crit** = 10 + LUK·10/3, in tenths of a percent; **perfect dodge** = LUK + 10, in tenths
  (`status.cpp:2729`, `:2737`; `battle.cpp:5424`).
- **Hard DEF** = the sum of the equipment's DEF (`status.cpp:3917`), capped at `max_def: 99`
  (`player.conf:132`).
  - Damage taken × (100 − DEF)/100 (`battle.cpp:4872-4876`).
  - Then minus the VIT reduction: `⌊0.3·def2⌋ + rnd(0, max(0, ⌊def2²/150⌋ − ⌊0.3·def2⌋ − 1)) + ⌊def2/2⌋`
    (`battle.cpp:4808-4812`, pre-re).
- **Max weight** = `MaxWeight 28000 + 300 × allocated STR`, in db units
  (`job_stats.yml:776`; `status.cpp:3663`).
  - It uses `sd->status.str`, the allocated STR **without** the job bonus.

### 3e. Results (gear from section 4: Flamberge + Shield + Full Plate + Helm + Geek Glasses + Manteau + Boots, unmounted)

| | MAIN | MAIN + DEX | ALT B | ALT C | Reading 2 |
|---|---|---|---|---|---|
| final STR/AGI/VIT/INT/DEX/LUK | 52/62/32/7/23/6 | 52/62/32/7/27/6 | 52/57/32/7/35/6 | 52/52/32/7/42/6 | 45/60/25/7/20/6 |
| amotion → client ASPD | 365 → 163.5 | 363 → 163.7 | 369 → 163.1 | 375 → 162.5 | 370 → 163.0 |
| attack interval (adelay) / attacks per s | 730 ms / 1.37 | 726 / 1.38 | 738 / 1.36 | 750 / 1.33 | 740 / 1.35 |
| HIT | 83 | 87 | 95 | 102 | 80 |
| FLEE | 122 | 122 | 117 | 112 | 120 |
| Max HP (with Faith 10) | 5260 | 5260 | 5260 | 5260 | 5087 |
| Max SP | 312 | 312 | 312 | 312 | 312 |
| status ATK (batk) | 82 | 83 | 85 | 86 | 66 |
| weapon ATK (Flamberge) | 150 | 150 | 150 | 150 | 150 |
| minimum weapon roll (DEX × 1.4) | 32 | 37 | 49 | 58 | 28 |
| soft DEF (VIT) → reduction per hit | 32 → 25 | 32 → 25 | 32 → 25 | 32 → 25 | 25 → 19 |
| hard DEF (gear) | 31 | 31 | 31 | 31 | 31 |
| soft MDEF / hard MDEF | 23 / 0 | 23 / 0 | 23 / 0 | 23 / 0 | 19 / 0 |
| crit / perfect dodge | 3.0 % / 1.6 % | same | same | same | same |
| max weight (in-game) | 4150 | 4150 | 4150 | 4150 | 3940 |

- **Mounted** (MAIN, Cavalier Mastery 5): the same ASPD as unmounted.
- **Mounted with Cavalier Mastery 0:** amotion 547 → ASPD 145.3, 1094 ms per attack, 0.91 attacks per s.
- **Max HP for MAIN, worked:** 2470 × 1.32 = 3260.4, + 2000 → 5260.
- **Hard MDEF is 0:** none of the shop items carry MagicDefense.
- **Endure** adds MDEF (section 3f).

**What the hit rate means in orcsdun01.**

- **Monster stats.** The monsters come from `npc/pre-re/mobs/dungeons/orcsdun.txt:16-26`, with
  their stats in `db/pre-re/mob_db.yml`. A monster's FLEE = level + AGI and its HIT = level + DEX
  (same `status.cpp:2704-2711`).
- **Our chance to hit** = 80 + HIT − monster FLEE, capped to 5..100 (`battle.cpp:3262`, `:3278`,
  `:3312`; `min_hitrate 5`, `max_hitrate 100` at `battle.conf:78-79`).
- **Their chance to hit us** is the same formula with our FLEE.
  - FLEE drops 10 % per attacker beyond 2 (`agi_penalty_type 1`, `count 3`, `num 10`;
    `battle.conf:85-95`; `battle.cpp:3265-3274`).
  - Our hard and soft DEF drop 5 % per attacker beyond 2 (`vit_penalty_*`, `battle.conf:101-111`; `battle.cpp:4780-4803`).

| Monster (mob_db line) | lv | FLEE / HIT | our hit (MAIN) | it hits MAIN at 1 / 3 / 4 / 5 attackers | its damage to MAIN per hit |
|---|---|---|---|---|---|
| Orc Zombie (`:7195`) | 24 | 36 / 48 | 100 % | 6 / 19 / 31 / 43 % | 25-47 |
| Orc Skeleton (`:7148`) | 28 | 42 / 58 | 100 % | 16 / 29 / 41 / 53 % | 52-83 |
| Steel Chonchon (`:1936`) | 17 | 60 / 50 | 100 % | 8 / 21 / 33 / 45 % | 12-19 |
| Drainliar (`:5173`) | 24 | 60 / 102 | 100 % | 60 / 73 / 85 / 97 % | 26-32 |
| Familiar (`:245`) | 8 | 20 / 36 | 100 % | 5 / 7 / 19 / 31 % | 1 |

- **Monster damage** is computed as `rnd[ATK, ATK2) × (100 − 31)/100 − 25`, plus −54 more from
  Divine Protection against the two Undead orcs (section 3f).
  - Monsters have no batk (`enable_baseatk 0x9` covers only players and homunculi).
  - These are the figures for a hit that lands. Auto Guard blocks up to 30 % of them first (section 3f).
- **Black Mushroom and White Plant** are plants with every Ignore mode (`mob_db.yml:3876`, `:3776`).
- **Every variant hits every orcsdun01 monster 100 %.** MAIN's HIT 83 is already 23 above the
  highest FLEE there (60).
  - The minimum for 100 % on the whole map is HIT 80, i.e. final DEX 20, i.e. base DEX 17.
  - So extra DEX buys damage (the weapon's minimum roll) and a quarter of AGI's ASPD per point.
    It buys no hit rate.
- **Expected normal-hit damage on Orc Zombie** (derived: the mean weapon roll + batk, × 0.95 for
  its DEF 5, − its VIT reduction 24, + Sword Mastery 40 + Demon Bane 60; crits ignored):
  - MAIN about 240 per hit, about 329 per second;
  - MAIN + DEX about 243 / 335;
  - ALT B about 251 / 340;
  - ALT C about 256 / 341;
  - Reading 2 about 223 / 301.
  - The Orc Zombie has 1568 HP (`mob_db.yml:7195`), so about 7 normal hits.
  - The trade-off: ALT B and ALT C gain about 3-4 % damage, and the monsters' chance to hit rises
    by 5-10 points.

### 3f. Skill effects (pinned pre-re)

| Skill | Effect at the planned level | Source |
|---|---|---|
| Sword Mastery 10 | +40 ATK with a 1H sword or dagger, added **after** DEF (a mastery; pre-re) | `battle.cpp:2332-2339`; post-DEF order `battle.cpp:4900-4914` (`#ifndef RENEWAL`) |
| Demon Bane 10 | +`lv × (BaseLv/20 + 3)` = **+60** ATK at Base 60 against Undead race or element, or Demon, monsters only; also post-DEF. This line is NOT under `#ifdef` (pre-re and renewal share it) | `battle.cpp:2291-2294` |
| Divine Protection 10 | **−54** damage per hit from Undead/Demon monsters at Base 60: `(int)((BaseLv/25 + 3) × lv + 0.5)`, added to the VIT reduction | `battle.cpp:4816-4818` |
| Faith 10 | **+2000** Max HP (200/level); **+50 %** Holy resistance (5 %/level) | `status.cpp:3150-3151`; `:4676-4677` |
| Auto Guard 10 | Block chance is cumulative per level: 5, 10, 14, 18, 21, 24, 26, 28, 29, **30 %**. It blocks weapon (`BF_WEAPON`) attacks only. After a block the walk delay is 300 ms (lv 1-5), 200 ms (6-9) or **100 ms** (10). Duration 300 s at every level; SP 12 + 2/level = **30**; needs a shield equipped | `status.cpp:11293-11300`; `battle.cpp:1521-1531`; `skill_db.yml:6691` |
| Endure 10 | Duration 10 s + 3 s/level = **37 s**; ends after 7 monster hits; +MDEF = its level (**+10**); SP 10; cooldown 10 s | `skill_db.yml:327` (Duration1, SpCost, Cooldown); `status.cpp:10856-10857`, `:1583-1589`; `:7946-7947` |
| Increase HP Recovery 10 | Every 10 s standing still (`natural_heal_skill_interval: 10000`, `player.conf:63`): `lv×5 + lv×MaxHP/500` = **155 HP** at Max HP 5260. Off while walking (`status.cpp:15527`). Potions: +10 %/level (below) | `status.cpp:5304-5305` |
| Natural HP regen (for reference) | `VIT/5 + max(1, MaxHP/200)` = **32 HP every 6 s** at MAIN (`natural_healhp_interval: 6000`, `player.conf:57`); the interval doubles while walking | `status.cpp:5276`; `:15548-15551` |
| Moving HP-Recovery (quest) | Natural HP regen keeps running while walking (at the doubled interval) | `status.cpp:4653-4656`, `:15529-15530`, `:15550-15551` |
| Bash 10 (+ Fatal Blow) | 100 + 30·lv = **400 %** damage; hit +5 %/level on the final hit rate (**×1.5**); SP 15 at levels 6-10. With Fatal Blow: stun chance `(lv−5) × BaseLv × 10` in 1/10000 = **30 %** at Base 60 | `src/map/skills/swordman/bash.cpp:12-14`, `:17-20`, `:26-29`; `skill_db.yml:164`; rate unit `status.cpp:9615` |
| Potions (VIT, IRP) | HP heal × `(100 + 2·VIT_final + 10·IRP_level)`% = **×2.64** at MAIN (VIT 32, IRP 10); ×2.50 at Reading 2. This line is shared by both branches | `pc.cpp:10700` |

**Weight and regen.** At ≥ 50 % weight, all natural and skill regen stops:

- `natural_heal_weight_rate` defaults to 50 in pre-re (`battle.cpp:8393-8395`, `#else`); the line in
  `player.conf:69` is commented out.
- `pc.cpp:3030`, `:3050` set the overweight state, and `status.cpp:15521-15522` stops the regen.
- At ≥ 90 % (`major_overweight_rate: 90`, `player.conf:77`) the character cannot attack.

---

## 4. Gear from NPC shops (pinned pre-re, loaded shops only, unrefined, no cards)

**How the shops were checked.**

- Every `shop` line was taken from the 532 loaded NPC files, then each item was checked against
  `db/pre-re/item_db_equip.yml`.
- **Shop price.** In a `shop`, a price of `-1` means the item's `Buy` value (`npc.cpp:4146-4147`).
  Every line below uses `-1`.

**How rAthena decides that a Crusader can wear an item.**

- **The Jobs key.** Each key under an item's `Jobs:` is looked up as `EAJ_<name>`
  (`itemdb.cpp:330-372`). `itemdb_jobid2mapid` then sets one bit in one of three arrays
  (`itemdb.cpp:3201-3229`):
  - `class_base[0]`: base jobs;
  - `class_base[1]`: 2-1 jobs;
  - `class_base[2]`: 2-2 jobs.
- **The Crusader's bit.** `EAJ_CRUSADER = MAPID_CRUSADER = JOBL_2_2 | MAPID_SWORDMAN`
  (`script_constants.hpp:310`; `map.hpp:140`). So `Crusader: true` sets the Swordman bit in
  `class_base[2]`.
- **The equip check.** `pc_job_can_use_item` checks a 2-2 job against `class_base[2]` only
  (`pc.cpp:1771-1792`).
- **So `Swordman: true` alone does NOT let a Crusader equip.** The item needs `Crusader: true` or
  `All: true`; an absent `Jobs` key means All (`itemdb.cpp:368-374`).
- **Classes.** `Classes` is absent on every item below, which means All (`itemdb.cpp:418-420`).
  That includes the normal 2nd class (`pc.cpp:1806`).
- **Level.** `EquipLevelMin` must be ≤ the base level (`pc.cpp:1882`).

### 4a. Best per slot

| Slot | Item (id, AegisName) | ATK/DEF | Slots | Weight | Equip Lv | Crusader can wear (Jobs key) | Price | Shops (map,x,y; file:line) |
|---|---|---|---|---|---|---|---|---|
| Weapon (1H sword) | **Flamberge** (1129, `Flamberge`), weapon level 3 | ATK **150** | 0 | 150 | 27 | `Crusader: true` (`item_db_equip.yml:805-821`) | **60,000** | Weapon Dealer#prt `prt_in,172,130` (`npc/merchants/shops.txt:255`); One Hand Weapon Dealer `ein_in01,106,27` (`:99`) |
| Shield | **Shield** (2105, `Shield`) | DEF **6** | 0 | 130 | — | `Crusader: true` (`:14481-14496`) | **56,000** | Armor Dealer#iz `izlude_in,70,127` (`shops.txt:141`); also Al De Baran (`:59`), Comodo (`:88`, `:94`), Hugel (`:135`), Lutie (`:194`) |
| Body | **Full Plate** (2316, `Plate_Armor`) | DEF **10** | 0 | 450 | 40 | `Crusader: true` (`:17013-17028`) | **80,000** | Armor Dealer#iz (`shops.txt:141`); Al De Baran (`:59`), Comodo (`:88`, `:94`), Lutie (`:194`) |
| Head top | **Helm** (2228, `Helm`) | DEF **6** | 0 | 60 | — | `Crusader: true` (`:15649-15664`) | **44,000** | Armor Dealer#iz (`shops.txt:141`); Al De Baran (`:59`), Comodo (`:88`, `:94`), Lutie (`:194`) |
| Head mid | **Geek Glasses** (2243, `Spinning_Eyes`), +15 % Blind resist | DEF **1** | 0 | 10 | — | no Jobs key = All (`:15880-15892`) | **20,000** | Tool Dealer#alb2 `alberta_in,182,97` (`shops.txt:51`); Toy Supplier#lhz (`:178`) |
| Garment | **Manteau** (2505, `Manteau`) | DEF **4** | 0 | 60 | — | `Crusader: true` (`:19821-19843`) | **32,000** | Armor Dealer#iz (`shops.txt:141`); also Alberta (`:52`), Payon (`:235`) and others |
| Footgear | **Boots** (2405, `Boots`) | DEF **4** | 0 | 60 | — | `Crusader: true` (`:18797-18823`) | **18,000** | Armor Dealer#iz (`shops.txt:141`); also many others |

**Totals.**

- Hard DEF **31**.
- Gear weight **920** in-game.
- Cost **310,000 zeny**. Without the Geek Glasses: DEF 30, 290,000 zeny.
- **One-stop:** Izlude's Armor Dealer#iz sells the Shield, Full Plate, Helm, Manteau and Boots
  together. Prontera's Weapon Dealer#prt sells the Flamberge.

**Excluded, and why:**

- **Legion Plate Armor** (2341, DEF 11): EquipLevelMin 70 (`item_db_equip.yml:17476`).
- **Greaves** (2411, DEF 5): EquipLevelMin 65 (`:18914`).
- **Town Sword** (1146, ATK 100): Novice and Super Novice only (`:1259`).
- **Arm Guard** (2117): Ninja only.
- **The next swords down:** Tsurugi 1119 (ATK 130, 1 slot, 51,000), Haedonggum 1123 (120, 1 slot,
  50,000), Saber 1126 (115, 2 slots, 49,000). All are at `prt_in,172,130`.
- **Goggles** (2224, top + mid, DEF 5) cost **20 zeny** (`Buy: 20`, `:15545-15570`) at Hugel's
  Armor Dealer#hu (`shops.txt:135`). They give 2 less DEF than Helm + Geek Glasses (5 against 7),
  for about 64,000 zeny less.
- **No shop accessory carries DEF.**

**The GM alternative:** `@item <id>`, which group 20 already has, gives the same items with no zeny.

### 4b. HP potions and the Fly Wing

All are sold by Tool Dealer#iz `izlude_in,115,61` (`npc/pre-re/merchants/shops.txt:40`) and Tool
Dealer#prt1 `prt_in,126,76` (`npc/merchants/shops.txt:254`). The nearest shop to the dungeon is
Tool Dealer#gef `geffen_in,77,167` (`shops.txt:115`). The heal is `itemheal rand(a,b)`, and
`rand(min,max)` is inclusive (`script.cpp:5579`, BUILDIN_FUNC(rand): only the one-argument form subtracts 1).

| Item (id, AegisName; `item_db_usable.yml` line) | Base heal | Price | Weight | Heal at ×2.64 (MAIN) | HP per zeny | HP per weight |
|---|---|---|---|---|---|---|
| Red Potion (501, `Red_Potion`; `:92`) | 45-65 | 50 | 7 | 118-171 (mean 145) | **2.89** | 20.7 |
| Orange Potion (502, `Orange_Potion`; `:100`) | 105-145 | 200 | 10 | 277-382 (mean 330) | 1.65 | 33.0 |
| Yellow Potion (503, `Yellow_Potion`; `:108`) | 175-235 | 550 | 13 | 462-620 (mean 541) | 0.98 | 41.6 |
| White Potion (504, `White_Potion`; `:116`) | 325-405 | 1,200 | 15 | 858-1069 (mean 963) | 0.80 | **64.2** |
| Fly Wing (601, `Wing_Of_Fly`; `:1034`) | random teleport (`itemskill "AL_TELEPORT",1`) | 60 | 5 | — | — | — |

**Potion delay.**

- None of these potions has a `Delay` key.
- The only server-side throttle is `item_use_interval: 100` ms between any two item uses
  (`conf/battle/items.conf:68`; `pc.cpp:6299`, `:6545`). That is at most 10 potions per second.
- So the **per-second** ranking is the same as per potion: White (about 9,600 HP/s at the cap)
  > Yellow > Orange > Red. Zeny or weight binds before the delay does.
- **Recommendation:**
  - Red Potion when zeny matters: about 3.6× the HP per zeny of a White.
  - White Potion when weight or tempo matters: about 3.1× the HP per weight of a Red, and 6.7× the
    heal per use.

**The Fly Wing works in orcsdun01.** The map has only `nomemo` (`npc/mapflag/nomemo.txt:344`) and
no `noteleport` entry (`npc/mapflag/noteleport.txt`, loaded).

### 4c. Weight budget (MAIN: allocated STR 45)

- **Max weight:** 2800 + 30 × 45 = **4150** in-game (`job_stats.yml:776`; `status.cpp:3663`).
  - **50 % (regen stops): 2075.**
  - **90 % (cannot attack): 3735.**
  - Mounted: +1000 → 5150 (50 % = 2575).
- **What fits under 50 %:** the gear uses 920, leaving 1155. That is 165 Red, or 115 Orange, or
  88 Yellow, or 77 White, before Fly Wings (5 each).
- **Reading 2** (allocated STR 38): max weight 3940.

---

## DISCREPANCIES vs Batt's list

1. **Swordman: 50 points against 49 earned.**
   - Sword Mastery 10, IRP 10, Bash 10, Provoke 5, Magnum Break 5 and Endure 10 sum to 50. A
     Swordman earns 49 from Job 1 to 50.
   - The 50th point must come from a **Crusader** point. The pinned server allows that once all 49
     first-class points are spent (`player_skillup_limit: yes`; `pc.cpp:2925-2929`).
   - **Only if the job change happens at Swordman Job 50** (49 also fits, with 0 spare).
   - The Crusader job NPC also refuses while any point is unspent (`npc/jobs/2-2/crusader.txt:131`,
     `:278`). So on the NPC route, spend the 49 on Swordman skills first, change job, then buy the
     50th level.
2. **Crusader: the list is 47 points, not 48.**
   - Divine Protection 10 + Demon Bane 10 + Cure 1 + Riding 1 + Cavalier Mastery 5 + Faith 10 +
     Auto Guard 10 = 47.
   - With the 1 Swordman overflow point, the Crusader uses 48 of 49 and **1 is left**. Batt's
     result is right if his 48 already counted the overflow.
3. **Prerequisites: all satisfied, two non-obvious ones.**
   - In the Crusader tree, **Divine Protection needs Cure 1**, and **Cure needs Faith 5**
     (`skill_tree.yml:844-853`). Demon Bane needs Divine Protection 3.
   - **Auto Guard has no prerequisite.** It does not need Faith.
   - Riding needs Endure 1.
4. **Naming.**
   - "Cavalry Mastery" is **Cavalier Mastery** (KN_CAVALIERMASTERY).
   - "Auto Guard" is described as "Guard" in `skill_db.yml`; its internal name is CR_AUTOGUARD.
5. **The stat targets.**
   - As **allocated** stats they fit Base 60 with **15 spare** (540 of 555).
   - As **final** stats (with the job bonus) they cost 453, with **102 spare**.
   - Batt's INT 1 and LUK 1 become 7 and 6 after the job bonus.
6. **Hit rate is not the constraint in orcsdun01.**
   - MAIN's HIT 83 hits every orcsdun01 monster 100 %; the highest FLEE there is 60, and 100 %
     needs HIT 80.
   - A DEX re-spec buys damage and a little ASPD, not hits.
7. **The shield has no ASPD cost in pre-re** (no shield column outside RENEWAL). Batt's
   "one-handed sword + shield" loses nothing in attack speed.
8. **"Built via GM commands":** the current GM group (20) lacks `jobchange`, `mount_peco`,
   `questskill` and `zeny`. Today the build needs either those permissions (Batt's decision) or
   the Swordman and Crusader job quests. Gear can come from `@item`, which group 20 has.

## UNVERIFIED

- **Not checked against the running server.** No live check was made: no `@` command was run, and
  the live container's `conf/` and `db/import/` were not read. The doc assumes the image was built
  from the pinned commit with `PRERE=yes`, which the repo's build files say, and that the
  container's `conf/import` holds only what `entrypoint.sh` renders.
- **The client's ASPD display and any client-side item-use throttle.** The client is not in the
  source. The ASPD figure is the server's `(2000 − amotion)/10`; the client may round it (for
  example 163.5 shown as 163).
- **The expected-damage and damage-taken figures in 3e** are DERIVED from the cited formulas, at the
  mean of each roll. They ignore:
  - crits (3 %);
  - Auto Guard blocks;
  - Endure;
  - the multi-attacker DEF penalty on our side;
  - monster skills;
  - card or element effects other than neutral against Undead 1 (100 %, `db/pre-re/attr_fix.yml:36-46`).

  They are a guide for choosing a variant, not a measurement.
- **Monster stats** are from `db/pre-re/mob_db.yml` for the spawn lines in
  `npc/pre-re/mobs/dungeons/orcsdun.txt`. Whether the live map's population matches those lines was
  not observed here.
- **The Crusader job quest's tests** (endurance, purification and so on) were not traced step by
  step. Only the gating checks were: job level, unspent points, and the item task's entry.
- **The Shrink quest's** intermediate dialogue steps were traced only through the `CRUS_SK` state
  changes and the item checks.
