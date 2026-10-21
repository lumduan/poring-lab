---
doc_type: design
hypothesis: "A dedicated Crusader (Base 60 / Job 50, AGI-first, one-handed sword + shield, unmounted) hunting orcsdun01 with immunity OFF survives on pixel-read HP, potions, Fly Wing escapes and Auto Guard, using the hunt flow's striking, EXP-line dead, stand + one-pass HAND loot and heading search."
status: "PROPOSED (plan + prep, 2026-10-21 16:1x). STOPPED for Batt's OK on the character creation and the one new permission (section 1). The dungeon run waits for the orcsdun01 detector to pass its pre-registered evaluation (../benchmarks/v2orc-vs-v1.md)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [orcsdun01-detector.md, crusader-build.md, crusader-orcsdun01-facts.md, ../benchmarks/v2orc-vs-v1.md, ../competition.md, ../demonstrations.md]
next_action: "Batt: OK (or not) on section 1 (a 2nd character on the GM account via the client's own Make Character UI + `jobchange` for group 20). Then the build (section 2) and the survival skills on prt_fild08 (section 3), each pre-registered before its run."
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
- **What Batt is asked:** (1) A, the 2nd character on the GM account; (2) `jobchange: true` in
  group 20. Nothing is added before the answer.

## 2. The build (verified numbers: crusader-build.md)

### 2a. Verified so far (the parent's spot checks; the full build is PENDING in crusader-build.md)

- Status points at Base 60: **555** in all, 48 of them at Base 1 (pinned
  `db/pre-re/statpoint.yml:36` and `:154`).
- The raise cost, pre-renewal: **1 + (stat + 9) / 10** points to go from `stat` to `stat + 1`
  (pinned `src/map/pc.cpp:8803`, the `#else` branch of `RENEWAL_STAT`).
- Batt's estimate as BASE stats (before the job bonus): AGI 60 = 263 points, STR 45 = 164,
  VIT 25 = 66, DEX 20 = 47, INT 1 and LUK 1 = 0. **540 of 555, so 15 are left.** The fit, the
  job bonus, ASPD / FLEE / HIT / HP / SP and the alternatives: crusader-build.md.
- The skill points: Batt's Swordman list sums to 50 (a Swordman at Job 50 has 49 points) and his
  Crusader list to 47. That is 97 of 98 in all, "1 left", IF the Crusader's points may go into
  Swordman skills. That rule is checked in crusader-build.md.

- How it is applied, all scripted, after Batt's OK:
  1. `@job Swordman` at Job 10 Novice (Basic Skill 9 via `learn_skill`), `@joblevelup` to 50,
     the Swordman skills in the skill window, `@job Crusader`, `@joblevelup` to 50, the Crusader
     skills (+1 point into a Swordman skill if the tree allows: section 2a);
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

PENDING: the 7 species against this Crusader (levels, elements, races, modes, damage vs DEF and
FLEE, hit chances), the warps, the spawn spread and the dead ends / narrow passages are in
crusader-orcsdun01-facts.md (a subagent, offline, running since 16:18).

- Already known (orcsdun01-detector.md): 135 units of 7 species (pinned spawn lines); 200 x 200,
  9,356 walkable cells, one component; 2 warps; nomemo only, so **teleport (a Fly Wing) works
  there** (the pinned npc/mapflag/: orcsdun01 is in nomemo.txt only, not in noteleport.txt).

## 7. The order and the gates

1. NOW (no client): this plan; the facts (two subagents, offline); the hit-rate judge.
2. AFTER Batt's OK on section 1: the character, the build (section 2), each scripted step
   judged on screenshots.
3. The survival skills S1-S6 on prt_fild08, immunity OFF, each pre-registered, with its
   positive case.
4. The dungeon run: only when the orcsdun01 detector PASSES its pre-registered evaluation
   (../benchmarks/v2orc-vs-v1.md). As of 2026-10-21 16:00 that detector is not trained: its
   label gates failed (orcsdun01-detector.md 3a, 3b).
- The client keeps alternating with the hunting work, as ordered. The GM's Novice baseline is
  never touched by this work.

## 8. What Batt decides

1. Section 1: the character (A, proposed) and `jobchange` for group 20.
2. Riding: unmounted first (Batt's default). Mounting later needs `mount_peco` or the Peco Peco
   renter NPC, plus re-cut sprite boxes.
3. The quest skills (crusader-build.md section 2): by their NPC quests (talk + items by `@item`),
   or skipped for the first test.
