---
doc_type: design
hypothesis: "A dedicated Crusader (Base 60 / Job 50, AGI-first, one-handed sword + shield, unmounted) hunting orcsdun01 with immunity OFF survives on pixel-read HP, potions, Fly Wing escapes and Auto Guard, using the hunt flow's striking, EXP-line dead, stand + one-pass HAND loot and heading search."
status: "ACCEPTED by Batt 2026-10-21 ~16:4x (character A + jobchange + questskill, all logged; LIVE since the guarded restart:rathena 16:45:35-16:47:46). The build and the survival skills on prt_fild08 proceed. The dungeon run waits for the orcsdun01 detector to pass its pre-registered evaluation (../benchmarks/v2orc-vs-v1.md)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, crusader-build.md, crusader-orcsdun01-facts.md, ../benchmarks/v2orc-vs-v1.md, ../competition.md, ../demonstrations.md]
next_action: "The build is DONE and verified (2b). Survival: 3.96 pre-registered 18:03; T-S6 trial 1 failed S1 (the bar) and S6 (the old death signature), both re-registered as 3.96b (the HP PERCENT text; the death dialog re-cut on this client) and S6b PASSED 19:16; the T-S2 / T-S3 trials run from 19:17 (demonstrations 3.96 / 3.96b run logs). The human demo (section 9) was armed 17:57-18:42 and got no input: re-arm when Batt says."
title: "A Crusader hunting Orc Dungeon F1 (orcsdun01) for real: the test character, the build, the survival skills and the order (plan)"
date: 2026-10-21
owner: Batt
---

# A Crusader hunting Orc Dungeon F1 for real (plan)

**Batt, 2026-10-21 ~16:1x (abridged):** "a CRUSADER hunting ORC DUNGEON F1 for real: monsters come
to us, immunity OFF, survive using everything learned (striking, EXP-line dead, stand + one-pass 5x5
HAND loot, heading search). 1. TEST CHARACTER: use a DEDICATED character, not the GM 2000002 ...
ask me before adding permissions. 2. BUILD (verify every number against the pinned rAthena) ...
3. SURVIVAL SKILLS (build + test on prt_fild08 with immunity OFF before the dungeon; pre-register
each) ... 4. ORC DUNGEON facts ... 5. ORDER: in parallel with the orcsdun01 collection + training
already ordered: (1)-(2) prep, (3) survival on prt_fild08. The dungeon run starts only when the
detector passes its pre-registered orcsdun01 evaluation. Plan first and stop for my OK on the
character creation/permissions; the rest proceeds."

**Addendum (Batt, the same hour):** "the stats are a STARTING POINT, not fixed ... If the hit rate
is poor (measure misses per target species from packets ...), move points into DEX, taking them
from STR or AGI a little, and re-test. Treat each re-spec as a pre-registered change with the hit
rate as its primary and kills/h, deaths and flee as guards ... record every split tried and its
numbers."

The facts behind the numbers are in two companion docs, each number with its source at the pinned
rAthena e985006 (pre-renewal):
- [crusader-build.md](crusader-build.md): the job path, the skill points and trees, the stats at
  Base 60, ASPD / FLEE / HIT / HP / SP, and the shop gear;
- [crusader-orcsdun01-facts.md](crusader-orcsdun01-facts.md): the 7 species against this
  Crusader, the map's warps, spawns and survival-relevant zones.

## 1. The test character (STOP: Batt's OK needed)

### 1a. What group 20 can already do (services/rathena/conf/import/groups.yml)

`where who whomap mapmove mobsearch monster killmonster2 hide alive heal item monsterignore
baselevelup joblevelup resetstat resetskill`, plus Player's.

What the build needs, checked against the pinned `src/map/atcommand.cpp` and
`conf/atcommands.yml`:

| need | command (pinned name, aliases) | group 20 today |
|---|---|---|
| Novice -> Swordman -> Crusader | `jobchange` (`@job`); atcommand.cpp:1203 `ACMD_FUNC(jobchange)` -> `pc_jobchange` | **NO** |
| Base Lv 60, Job Lv 50 (points come with the levels) | `baselevelup`, `joblevelup` | yes |
| gear, potions, Fly Wings | `item` | yes |
| re-specs (Batt's addendum) | `resetstat` (`@streset`), `resetskill` (`@skreset`) | yes |
| recovery after a death (the run has already stopped) | `alive`, `heal` | yes |
| immunity OFF / ON | `monsterignore` (a toggle) | yes |
| stat / skill points without levels | `statuspoint`, `skillpoint` | no; NOT needed |
| a Peco Peco | `mount_peco` (`@mount`, `@mountpeco`; "class is required, but not the skill") | no; NOT needed for the first test (unmounted) |
| zeny | `zeny` | no; NOT needed (gear by `@item`) |

### 1b. Two ways to make the character

| | A. A 2nd character on the GM account (the client's Make Character UI) | B. A 2nd lab account in group 20 |
|---|---|---|
| server change | **none** (char_athena.conf `char_new: yes`) | the agent account (`RATHENA_AGENT_USER`, group 0 today, entrypoint.sh:146) moved to group 20, or a new account: `.env` + `rotate_secrets`, compose, entrypoint's `ensure_account`, the sniffer's `VALIDATION_USERIDS` |
| permissions | group 20 is per ACCOUNT, so the new character inherits it; + `jobchange` | the same set + `jobchange`, on a second account |
| packets | the SAME block id 2000002 (a player's block id is its account id), so every offline judge keyed on the GM's id keeps working. The character is told apart by its char id and the name on Basic Info | a new block id: every judge's GM id becomes a parameter |
| login | ro_agent's GM login + a slot pick at character select | a second credential set and login path |
| interlock | unchanged (the GM account is attested today) | already accepts both lab accounts (`test_interlock.py`) |
| risk | an account-wide command typed on the WRONG character (the Novice baseline). Guard: every level / job / stat / item command checks the character's name and job on Basic Info first, and refuses on a mismatch | none to the Novice; more moving parts |

**Proposal: A, plus ONE new permission, `jobchange`, for group 20** (logged like every group-20
command: `LogCommands: true`).
- The job change by NPC quests (Swordman's test course in Izlude, the Crusader quest) would be
  world clicks and dialogs that we do not need to prove for this test.
- Character creation, by the client's own UI at character select:
  - an empty slot -> Make Character -> the name (a fresh, never-reused name, `char_name_option 2`
    rules) and the same hair style and colour as the GM's Novice where the UI allows. The hunt
    guards exclude the GM's hair colour (`GUARD_EXCLUDE`, `loot_pink_gm_exclude`), so keeping it
    keeps those guards meaningful;
  - the client types the name: a new typed context, under the foreground gate, judged on a
    screenshot before and after.
- The character starts on **new_1-1 (53,111)** (pinned `start_point_pre`), the Novice training
  ground, which is NPC-dense. Its first action is `@warp` (mapmove) out. No world click happens
  there. Start items: Knife 1201 + Cotton Shirt 2301 (`start_items_pre`); start zeny 0.
- ~~**What Batt is asked:** (1) A, the 2nd character on the GM account; (2) `jobchange: true` in
  group 20.~~ ➡️ **ANSWERED (Batt, 2026-10-21 ~16:4x):** "1) Character A (2nd character on the GM
  account, with the name+job check before every command). 2) Yes, add jobchange to group 20
  (logged). 3) Quest skills: GRANT them by GM command too ... add only that permission to group
  20, logged: Moving HP Recovery, Fatal Blow, Auto Berserk, Shrink. Moving HP Recovery matters: I
  want to see whether HP regen keeps up while the bot walks and fights continuously."
  - Applied: `jobchange` + `questskill` in group 20 (cc184ff, edited in place, logged). LIVE after
    the guarded `restart:rathena@120` 16:45:35-16:47:46 (worst capture stall 10.4 %, 8 s above
    10 %); the GM re-logged in 16:48:57 (`ro_agent recover gm`).
  - The pinned `questskill` (atcommand.cpp:3819) grants by number, with no job check: 144 Moving HP
    Recovery, 145 Fatal Blow (Attack Weak Point), 146 Auto Berserk, 1002 Shrink.

## 2. The build (verified numbers: crusader-build.md)

### 2a. The build (crusader-build.md, merged faca4a0; the parent re-checked the job bonus, base HP, ASPD, the prerequisites and the gear against the pinned files)

- **Points:** 555 status points at Base 60 (48 at creation); the pre-re raise cost
  1 + (stat + 9) / 10 (`pc.cpp:8803`). Skill points 9 + 49 + 49 = 107.
- **Batt's skill lists fit with 1 point left:** Swordman 50 (49 earned + 1 Crusader point) +
  Crusader 47 + Basic Skill 9 = 106 of 107.
  - The Crusader tree inherits Swordman's (`skill_tree.yml:827-830`), so a Crusader point may buy
    the 50th Swordman level.
  - **The change Swordman -> Crusader must happen at Swordman Job 50**: `@joblevelup` to 50 BEFORE
    `@job Crusader`.
  - Hidden prerequisites, all inside Batt's lists: Divine Protection needs Cure 1, Cure needs
    Faith 5, Demon Bane needs DP 3, Riding needs Endure 1.
- **Stats (Batt's split read as ALLOCATED):** STR 45 / AGI 60 / VIT 25 / INT 1 / DEX 20 / LUK 1 =
  540 of 555, **15 left**.
  - The Crusader's Job 50 bonus is STR +7 AGI +2 VIT +7 INT +6 DEX +3 LUK +5 (`job_stats.yml`),
    so the finals are 52 / 62 / 32 / 7 / 23 / 6.
- **The numbers (Flamberge + Shield, unmounted):**
  - ASPD 163.5 = amotion 365 (1H sword base 500, `job_aspd.yml`), an attack every 730 ms. The
    shield costs no ASPD in pre-re.
  - HIT 83, FLEE 122, MaxHP 5260 (2470 x 1.32 + Faith 2000), MaxSP 312.
  - Hard DEF 31 (gear), soft DEF 32. Max weight 4150.
- **The gear (by `@item`; the shop is named for the record):** Flamberge 1129 (1H sword, ATK 150,
  elv 27, 60,000 z, Weapon Dealer#prt). The rest is at Armor Dealer#iz:
  - Shield 2105 (DEF 6, 56,000 z);
  - Full Plate 2316 (DEF 10, elv 40, 80,000 z);
  - Helm 2228 (DEF 6, 44,000 z);
  - Manteau 2505 (DEF 4, 32,000 z);
  - Boots 2405 (DEF 4, 18,000 z);
  - plus Geek Glasses 2243 (DEF 1, 20,000 z, Alberta).
  - Every item is Crusader-wearable by its own Jobs key ("Swordman: true" alone would NOT cover
    a Crusader).
- **Potions:** Red 501 (50 z, the best HP per zeny); White 504 (1,200 z, the best per weight and
  per press). There is no per-item delay, only `item_use_interval` 100 ms. Heals x2.64 at VIT 32 +
  IRP 10. Fly Wing 601 (60 z).
- **The hit rate (Batt's addendum) on orcsdun01:**
  - the pinned formula is 80 + HIT - FLEE, capped 5..100 (`battle.cpp`). The highest FLEE there is
    60 (Drainliar, Steel Chonchon), so **every split with HIT >= 80 hits every species 100 %**.
    MAIN's HIT is 83.
  - So the re-spec loop's primary is expected to read ~100 % from the start. The measurement
    (hit_rate.py) is the check of that prediction.
  - A DEX re-spec would buy damage (the minimum roll) and a quarter of AGI's ASPD per point, while
    costing FLEE: the monsters' chance to hit rises 5-10 points.

- How it is applied, all scripted, after Batt's OK:
  1. `@joblevelup` 9 + Basic Skill 9 (`learn_skill`), `@job Swordman`, `@joblevelup` to 50, the
     Swordman skills in the skill window (49), `@job Crusader` (at Swordman Job 50), `@joblevelup`
     to 50, the Crusader skills (47) + the 50th Swordman level; `@questskill 144 / 145 / 146 /
     1002`. Every command first checks the name + job on Basic Info;
  2. `@baselevelup` to 60; the stats by the status window's `+` (the STR path exists:
     `gm_state.STATUS_STR_PLUS`; AGI / VIT / DEX need their own `+` offsets and a stat reader,
     cut from screenshots and proven offline first);
  3. the gear by `@item`, equipped from the inventory (a UI step: double-click, judged on a
     screenshot), potions and Fly Wings by `@item`;
  4. the hotkeys: F1 potion, F2 Fly Wing, F3 Auto Guard, F4 Endure. They are set once by
     dragging into the shortcut bar (a new UI step, judged on screenshots; the bar is saved
     server-side per character). Fallback: Batt sets them once by hand.
- `learn_skill` today knows the Novice tree only (the L2 binding `skill_tree`, the level digit
  "1" only, learn_skill@1). The Swordman and Crusader trees need their own binding and digit
  references: a prove step on banked frames before any live click.

### 2b. BUILT 2026-10-21 17:16-17:52 (the client; every GM line through `scripts/crusader.py`, bd68eec)

- **The character:** `Crus4b7e2`, slot 2 of the GM account (account 2000002, group 20), char id
  150003. Made by the client's own Make Character UI (Human, the default look = the Novice GM's).
  The name is in `data/crusader/char.json` (gitignored).
- **The steps** (frames under the NAS scratch-archive):
  1. `@warp prt_fild08 170 375` (bench's outdoor stand);
  2. `@joblevelup 9`, Basic Skill 9 by learn_skill@1's own rule;
  3. `@job 1`, `@joblevelup 49`, the Swordman skills;
  4. `@job 14` at Swordman Job 50, `@joblevelup 49`, the Crusader skills, Endure's 10th level;
  5. `@questskill 144 / 145 / 146 / 1002`, `@baselevelup 59`;
  6. the stats by the status window's '+' (146 clicks);
  7. `@item` x 9, the 7 items equipped by double-clicks in the Eqp tab.
- **The DB read-back (17:52, after the server's save):**
  - class 14, Base 60 / Job 50;
  - STR 45 AGI 60 VIT 25 INT 1 DEX 20 LUK 1, status points 15, skill points 1;
  - MaxHP 5260, MaxSP 312;
  - skills: NV_BASIC 9; SM_SWORD 10, SM_RECOVERY 10, SM_BASH 10, SM_PROVOKE 5, SM_MAGNUM 5,
    SM_ENDURE 10; CR_TRUST 10, AL_CURE 1, AL_DP 10, AL_DEMONBANE 10, CR_AUTOGUARD 10,
    KN_RIDING 1, KN_CAVALIERMASTERY 5; quest 144, 145, 146, 1002;
  - equipped: Flamberge 1129, Shield 2105, Full Plate 2316, Helm 2228, Manteau 2505, Boots 2405,
    Geek Glasses 2243;
  - carried: White Potion 504 x 50, Fly Wing 601 x 20, the starter Knife and Cotton Shirt.
- **The status window agrees with crusader-build.md's predictions:**
  - ATK 232 + 0, DEF 31 + 32, HIT 83, FLEE 122 + 1, ASPD 163;
  - HP 5260; weight 1820 / 4150 (43.9 %).
- **What was met on the way (each is recorded, none was worked around):**
  - `@job Swordman` answered "@job failed.": the permission WAS live (a refused command is said
    as chat). The name lookup compares against the server's job names, which are localized.
    `@job 1` / `@job 14` (the ids) worked.
  - The warp's loading screen was still up when the next line was due: the identity check
    refused (name crop 1,624 px off) and NOTHING was sent. A live negative case of the check.
  - Skills reach the DB only at the server's save. So each skill was proven by the rule's own
    points read (P -> P - n) and judged frames, and the DB confirmed all of them after the save.
  - On the Crusader tab the modal reader's no-modal side read 0.85 (bar 0.85): the reference was
    cut over the Novice tree. For that tab the read was made one-sided (the modal's own pixels:
    >= 0.85 present, < 0.5 absent, else unknown), with the same clicks and the same points
    check. It is noted in the scratch builder; learn_skill1.py is unchanged.
  - Auto Guard shows a cast-level selector ("1 / 10"): the client casts level 1 unless it is
    raised. S4 sets it to 10 before the hotkey is made.
  - Two-hand / Spear skills were never touched; 1 skill point and 15 status points are left
    (Batt's plan; the 15 are the DEX reserve for the re-spec loop).

## 3. The survival skills (build and test on prt_fild08, immunity OFF; each pre-registered)

The test bed: the Crusader at its full build on prt_fild08 with immunity OFF. prt_fild08's own
monsters cannot hurt a Base 60 Crusader much, so every survival skill gets a **deliberate positive
case**: aggressive orcsdun01 species spawned beside it with `@monster` (group 20 has it), fought
or fled, then removed with `@killmonster2` (no drops). Packets judge everything offline (HP from
the server's status updates, item use, damage, deaths).

| id | skill | the rule (pixels in, keys out) | pre-registered measure (offline, packets) |
|---|---|---|---|
| S1 | HP from pixels | Basic Info's HP bar (`gm_vitals.hp_fraction`, calibrated on 40/40 only) PLUS the "HP a / b" digits in the weight readout's glyph family | each read vs the server's HP at that frame: \|error\| <= 3 % of max on >= 95 % of reads; latency |
| S2 | potion | HP < T_pot -> F1, paced; re-read; no second press before the heal shows | potions used, HP min, time below T_pot, heals that landed |
| S3 | Fly Wing escape | HP < T_fly (< T_pot), or > N monsters on us -> F2 | escapes, HP at the escape, attackers at the escape (packets), deaths |
| S4 | Auto Guard | re-cast on expiry: the status icon gone (a template), with a timer backstop | uptime share, re-cast delay |
| S5 | Endure (optional) | when mobbed (>= N attackers) | casts, flinches avoided |
| S6 | death | the death dialog (`gm_vitals.DEAD_BOX`'s signature) -> STOP the run, record the cause (a RESULT, not a hard bar). The dialog stays until the UI gate's known step (its second button, "return to game"); never the first (a respawn elsewhere) | deaths / h, the cause: HP trace, attackers, species (packets) |

- The thresholds (T_pot, T_fly, N) are set from crusader-orcsdun01-facts.md's damage per second
  (section 3a, filled with the facts): the escape must fire while one more worst-case second
  cannot kill.
- Measures in every run: deaths per hour, HP min, potions used, escapes, Auto Guard uptime,
  damage taken per minute.
- Hard bars stay: NPC contact, map change (a Fly Wing does NOT change the map; a map change is
  still a bar), unknown UI state. A non-target hit: on orcsdun01 all 7 species are targets.

## 4. The re-spec loop (Batt's addendum)

- **Start:** the AGI-first split (section 2a).
- **The instrument, offline, built now:** a per-species hit-rate judge. Our attack results from the
  packets (each of our normal attacks on a monster: damage > 0 or a miss), by the target's species
  (the Timeline's job id). Its positive case comes from a REAL session: a v52 hunt has misses
  against Lunatic or Poring.
- **Each re-spec is ONE pre-registered change:**
  - points move into DEX, taken a little from STR or AGI;
  - PRIMARY: the hit rate per target species (Orc Skeleton, Orc Zombie, Drainliar ...), against
    the formula's prediction (section 2a);
  - GUARDS: kills/h, deaths/h, FLEE (the formula, and the monsters' measured hit rate on us).
- Every split tried, with its numbers, gets a row in one table (docs/competition.md, a new
  "Crusader splits" section).
- A re-spec costs `@resetstat` + the scripted status-window clicks, about a minute.
- The hit rate against orcsdun01's species is measured IN the dungeon (or against `@monster`
  orcs on prt_fild08). The bot targets only what the detector knows, so this waits for the
  orcsdun01 detector too.

## 5. What our code assumes about "the GM" (each becomes per-character)

| assumption | where | for the Crusader |
|---|---|---|
| the drawn sprite box (a Novice, 40 x 90 px) | `hunt_flow.GM_SPRITE_BOX` (620,285,660,375), `GUARD_EXCLUDE` (605,270,675,390), `drop_blobs.GM_BOX`, `belief_map.GM_SPRITE`, `attack_cue.GM_BOX` (600,260,680,372) | re-measured on screenshots (a shield widens one side). Mounted, a Peco Peco is far bigger: every box re-cut, which is one more reason to stay unmounted first |
| the sprite centre | `hunt_flow.GM_SPRITE_PX` (640,340) | unchanged: the camera centres on the character |
| route previews | cells from selfpos (`route_plan`, `route_previewd`) | unchanged (cell-based, not sprite-based) |
| the weight cap = a Novice's 2000 + 30 x STR | `gm_state.NOVICE_WEIGHT_BASE`, `str_of_weight_max` | the Crusader's MaxWeight (crusader-build.md) |
| the fixed state = Lv 1 / Lv 70 Novice templates | `gm_state.PROFILES` (`levels_1_1.npy`, `levels_70_1.npy`) | a "crusader" profile: Lv 60 / 50, its own level templates, the job name, the split |
| HP = a fraction of a bar calibrated at 40/40 | `gm_vitals.HP_BAR`, `HP_FULL_FILL` | re-calibrated; the digits read (S1) |
| immunity ON at every restore | `collect_v2` immune-on, `farm0.immunity_confirmed` | OFF for this character's survival runs; the Novice's restore unchanged |
| skill window = the Novice tree | `learn_skill1` (L2 `skill_tree` binding) | Swordman + Crusader bindings |
| the detector's view of self | v1 / v2orc trained on a Novice GM | the Crusader's own look near the centre is excluded by the box; its look is NOT in any training set (a risk for a self-detection near the box edge) |

## 6. Orc Dungeon F1 against this Crusader (facts: crusader-orcsdun01-facts.md)

### 6a. The facts (crusader-orcsdun01-facts.md, merged 98503c8; the parent re-checked the 7 species in `mob_db.yml`)

- **The threats, worst first:**
  - Drainliar: HIT 102, so it lands 52 % of its hits even at FLEE 130; Blood Drain ignores FLEE.
  - Orc Skeleton: ATK 190-236. Critical Slash always hits for its max and ignores FLEE, DEF and
    Divine Protection.
  - Orc Zombie: weaker, but 80 of the 135 units.
  - Familiar and Steel Chonchon do little damage, but each one attacking raises the attacker
    count.
- **Our hit:** 100 % on every species from HIT 80 (section 2a).
- **Their hit:** each attacker past 2 cuts our FLEE by 10 % (the pinned `agi_penalty_*`
  defaults), and the cap is 5..100, not 95.
  - At FLEE 130, an Orc Skeleton hits 8 % alone, 21 % with 3 attackers, 34 % with 4.
- **Divine Protection 10 at Base 60** = +54 VIT DEF against the orcs (Undead element).
  - Average per landed hit (DEF 20 / VIT 30): Orc Zombie 109 -> 55; Orc Skeleton 146 -> 92.
- **Packs (HP/s at FLEE 130, with their skills):** 3 Orc Zombies 23.8; 3 OZ + 2 OS 103.8;
  + a Drainliar 163.1; all 8 cells around us ~249.
  - Times to death from ~5.2 k HP: ~50 s, ~32 s and ~21 s.
  - Auto Guard 10 cuts these to ~0.7 x.
- **The typical encounter:** 3.19 aggressive monsters in reach of a random cell (p90 4.68). A Fly
  Wing lands among ~3.2 too, so **a Fly Wing swaps a heavy pack for a typical one, not for
  safety**.
- **Potions keep up:** a White heals ~584 at VIT 30 (949 with IRP 10). Holding the worst pack
  needs ~16-26 a minute; stock, weight and our input rate limit it, not the server.
- **The map:**
  - a RING of wide corridors (5-15 cells) around a central rock;
  - no <= 2-cell choke between areas;
  - wide dead ends: the SE wing (holds the warp to F2), the N pocket and the NW entrance wing
    (holds the exit warp and the arrival cell);
  - pillars to circle around;
  - monsters do not follow through warps.
- **What this changes in section 3:** the HP rule keys on the ATTACKER COUNT, a Drainliar in the
  pack and Blind, not on HP % alone.
  - T_fly from the worst plausible pack's damage per second x (read latency + key + the client's
    response) x a safety factor.
  - The Fly Wing is for n >= 5, or a Drainliar + Blind.
  - **The map's exit warp (orc01-1, NW wing) is a better escape than a Fly Wing** when it is near.
  - The survival tests on prt_fild08 use the same species by `@monster`, so the thresholds are
    measured against the real attackers.

- Already known (orcsdun01-detector.md): 135 units of 7 species (pinned spawn lines); 200 x 200,
  9,356 walkable cells, one component; 2 warps; nomemo only, so **teleport (a Fly Wing) works
  there** (the pinned npc/mapflag/: orcsdun01 is in nomemo.txt only, not in noteleport.txt).

## 7. The order and the gates

1. DONE 16:2x-16:5x: this plan; the facts (two subagents, offline, merged); the hit-rate judge
   (b3c5739); Batt's OK and the permissions (live 16:47).
2. NOW: the character, the build (section 2), each scripted step judged on screenshots.
3. The survival skills S1-S6 on prt_fild08, immunity OFF, each pre-registered, with its
   positive case.
4. The dungeon run: only when the orcsdun01 detector PASSES its pre-registered evaluation
   (../benchmarks/v2orc-vs-v1.md). As of 2026-10-21 16:00 that detector is not trained: its
   label gates failed (orcsdun01-detector.md 3a, 3b).
- The client keeps alternating with the hunting work, as ordered. The GM's Novice baseline is
  never touched by this work.

## 8. What Batt decided (2026-10-21 ~16:4x)

1. ~~Section 1: the character (A, proposed) and `jobchange` for group 20.~~ ➡️ A, with the name +
   job check before every command; `jobchange` added (logged).
2. Riding: unmounted first (Batt's default). Mounting later needs `mount_peco` or the Peco Peco
   renter NPC (Peco Peco Breeder#cru prontera 232,318, 3,500 z), plus re-cut sprite boxes.
3. ~~The quest skills: by their NPC quests or skipped~~ ➡️ GRANTED by `@questskill` (only that
   permission added, logged). Moving HP Recovery is measured: does HP regen keep up while the bot
   walks and fights continuously.

## 9. Batt's human demo on orcsdun01 (Batt, 2026-10-21 ~16:4x)

"When the Crusader is built, I will play a 10-min demo there as the comparison (same setup as my
prt_fild08 demo: frames, mux log source=human, packets; immunity OFF; tell me when it's ready to
record)."
- The setup is the same as the 2026-10-16 human demo (`20261016T093835-demo-human-demo`):
  - the frames, the mux's input log (source = human) and the packets;
  - the Crusader at its full build;
  - immunity OFF;
  - the GM's Novice untouched.
- The agent tells Batt when it is ready to record, and records nothing before he starts.
