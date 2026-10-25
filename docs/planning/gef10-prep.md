---
doc_type: research
hypothesis: "Before the Rogue's first walk-and-hit run on gef_fild10 (rogue-gef10.md), the offline map prep that pay_fild07 had (the KB with the map's sources, the client GAT, client / server walkability, script-NPC cells, the delegated zones, a start stand, rest spots, the runner's map inputs, the econ model at Overcharge, the species' sprites) can be produced from the local sources alone, with no live action."
status: "MEASURED offline 2026-10-25 19:04-19:45 ICT (from `date`; no client, no GPU, no input, nothing written to data/kb or the NAS). The zones file is DELEGATED (Batt 2026-10-25 ~13:1x) and proved: 0 cells cut off. The KB, first_workflow, npc_cells and route.json candidates are in /dev/shm, NOT installed (section 10)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, payf07-prep.md, orcsdun01-dungeon-prep.md, payf07-detector.md, ../econ/economics.md, ../../config/map_zones/README.md, ../../config/map_zones/gef_fild10.yaml, ../../scripts/map_prep.py, ../../scripts/dungeon_hunt.py]
next_action: "The parent: install the four KB candidates (section 10), then re-run `map_zones.py check / prove gef_fild10` and `map_prep.py stands gef_fild10` on the main checkout; build the Orc Lord escape from section 1c (on foot cannot outrun it: a Fly Wing at first sight); add --char rogue and the runner items of section 7."
title: "gef_fild10 prep for the Rogue: KB, client GAT, walkability, NPC cells, delegated zones, stands, rest prior, runner inputs, econ at Overcharge, sprites"
date: 2026-10-25
owner: Batt
---

# gef_fild10 prep for the Rogue's walk-and-hit runs

**The brief** (the parent session, 2026-10-25 ~19:0x ICT; [rogue-gef10.md](rogue-gef10.md)
section 7, step 2). Do for gef_fild10 what [payf07-prep.md](payf07-prep.md) did for pay_fild07:
- the KB with the Geffen field sources;
- the client GAT and the client / server walkability;
- the script-NPC cells;
- the zones (DELEGATED by Batt);
- start stands and what rest spots are possible;
- the runner's map inputs;
- the econ model at Overcharge;
- the species' sprite stems and boxes.

Offline only, in a tmpfs worktree. The lab server is PRE-RENEWAL, rAthena pinned
`e985006171d2eb320ee512a653f4c83aea3d81b6` (the read-only mirror `/dev/shm/poring-lab-rathena-src`
and kb_build's fetch cache of the same ref, which agree byte for byte on all 31 files both hold).
No rAthena table is copied here (GPL data rule): only cells, ids, counts and derived values.

## 0. Bottom line

1. **KB** (section 1): `kb_build.py` now lists `npc/pre-re/mobs/fields/geffen.txt` and
   `npc/pre-re/warps/fields/geffen_fild.txt`, and `classes_for` adds summoned SLAVES.
   - gef_fild10: Orc Lady 70, Orc Warrior 20, Poporing 15, Orc Baby 5, the Orc Lord MVP 1,
     Blue Plant 3 + 3 and Green Plant 3 (fixed areas). 9 warps.
   - `classes_for gef_fild10` = those 7 species **plus the Orc Archer (1189 and 1473)**, the Orc
     Lord's slaves. **The Orc Lord walks with 5 Orc Archers**: range 9, 73 % to hit the Rogue.
   - The candidate differs from the installed KB ONLY by added maps (the Geffen fields
     gef_fild00-14, in_orcs01, orcsdun02), two more gef_fild06 warp rows and the classes of
     pay_fild07 and gef_fild10.
2. **The Orc Lord cannot be outrun on foot** (section 1c). It walks 100 ms per cell against the
   Rogue's 150; under its own Increase AGI it walks 75.
   - It notices within 10 cells, and it casts Lv 10 Cold / Fire Bolt (range 9, no cast time) while
     it chases. One bolt is 1,700-2,660 damage before MDEF, about the Rogue's whole HP (~2,030).
   - **Only a Fly Wing breaks contact.** It works on this map (no noteleport flag) and under
     Silence (Lex Divina), but **not under Stun** (Shield Charge, range 3). So: a Fly Wing at
     first SIGHT, before it is within 10 cells.
   - Normal orcs walk 200 ms per cell: the Rogue CAN outrun them (they drop a target past 12 cells).
3. **Client GAT and walkability** (section 2): gef_fild10 is 400 x 400. **Client and server agree
   exactly**: 72,656 walkable cells on each side, 0 disagreements either way. ONE component of
   72,656 cells, with or without the corner rule.
4. **Script NPCs** (section 3): **5, all drawn dialog NPCs, NONE with a touch area.**
   - The Kafra (73,340), the bulletin boards (69,340) and (109,23), the Orc's Memory pair
     (242,202) and (238,202).
   - The custom warper / porter files (`npc/custom/warper.txt`,
     `npc/custom/etc/quest_warper.txt`, `npc/custom/etc/airplane.txt`) are NOT loaded.
   - Merged into a candidate npc_cells.json with `--only gef_fild10`: the other 38 blocks unchanged.
5. **Zones** (section 4): `config/map_zones/gef_fild10.yaml`, reviewed by the agent under Batt's
   recorded delegation. 14 no-enter areas: the 9 warp spans + 4 and the 5 NPC cells + 4.
   - `check` ok. `prove`: **0 cells cut off, 0 newly unreachable** (both connectivities).
   - 860 walkable zone cells (1.18 % of the spawn cells).
   - Every sampled click into each area, and onto each warp span, is refused: 400 / 400.
   - Each of the 9 arrivals lies inside its warp's area.
6. **Stands** (section 5): **START (186,179)**, the runner's own anchor, and FALLBACK (186,159).
   - Both pass the three stand-cell checks, as do all 1,717 cells of the seeded-start box.
   - START is 36 cells from the nearest warp span and 52 from the nearest NPC.
7. **Rest spots** (section 6): there are no gef_fild10 packets, so there is no measured rest
   spot. A GEOMETRY PRIOR gives 5 pockets with ~0.03-0.05 aggressive monsters expected within
   10 cells, against 0.56 at the median cell. It is proposed, not installed.
8. **The runner** (section 7) needs no map change for `--map gef_fild10` once the KB is in.
   - The default `--engage defend_scan` does NOT refuse a map with script NPCs. `melee_ring`
     does: gef_fild10 is not in MR_MAPS and it has 5 NPCs.
   - Its search area keeps only the WARPS 10 cells off, not the NPCs. On this map the zones'
     NPC areas are its only NPC keep-away.
   - **warps.json is read with `.get(map, [])`, which fails OPEN** while route.json is the
     only guard. Install them together.
9. **Econ** (section 8): the Overcharge option already existed (`econ_items.overcharge`, `--oc`;
   pc.cpp:5708-5719, truncated per unit). New: `econ_model.py species MAP`.
   - Value per kill at Overcharge, rares out: **Orc Lady 224.42 z**, Orc Warrior 84.97,
     Orc Baby 78.71, Poporing 30.23.
   - The spawn mix without plants: 165.96 z and 0.94 weight per kill.
10. **Sprites** (section 9): the stems equal the aegis names. No species flies.
    - **The Orc Lord's colour is the Orc Warrior's and the Orc Archer's** (hue 41 / 36 / 30°,
      saturation 0.38 / 0.35 / 0.36). Its SIZE differs: an 81 x 100 idle box, against 65 x 96 and
      66 x 89.
    - Its SPR / ACT are left in `/dev/shm/poring-lab-tmp/gef10-prep/sprites/`.

## 1. The KB (`scripts/kb_build.py`)

**The change.** `SPAWNS` gains `npc/pre-re/mobs/fields/geffen.txt` and `WARPS`
`npc/pre-re/warps/fields/geffen_fild.txt`.
- Both are the pre-renewal overrides the map-server loads: `npc/pre-re/scripts_monsters.conf:54`
  and `npc/pre-re/scripts_warps.conf:15`.
- A test pins the hunt maps' sources: listed once, pre-renewal, never `npc/re/`.
- `classes_for` also adds the slaves a spawned species summons (`NPC_SUMMONSLAVE`, skill 196,
  val1..val5), with `"via": "slave of <id>"`. It is tested.
  - Of the six maps in the candidate's classes, only gef_fild10 changes: it gains 1189 and 1473.

**The candidate** (`kb_build.py --out /dev/shm/poring-lab-tmp/gef10-prep/kb --maps prt_fild08
iz_dun00 iz_dun01 orcsdun01 pay_fild07 gef_fild10`, built 2026-10-25 19:33:28 ICT). Against the
installed `data/kb` (built 10-09, its spawns / warps / classes rewritten 10-21):
- mobs, mob_skills, items, drops, server: **identical**;
- spawns.json: +16 maps (gef_fild00-14, orcsdun02), nothing else changed;
- warps.json: +16 maps (gef_fild00-05, 07-14, in_orcs01, orcsdun02); gef_fild06 keeps its one
  row and gains 2 (the new file's);
- classes.json: + pay_fild07 and gef_fild10; the four installed maps unchanged.
- `npc/warps/dungeons/orcsdun.txt`, listed since 10-21, was never in the fetch cache. It was
  seeded from the mirror, as was `geffen_fild.txt`. `geffen.txt` was already cached.

### 1a. gef_fild10 in the candidate KB

| species (id) | spawn line | walk (ms / cell) | AI | notes |
|---|---|---|---|---|
| Orc Lady (1273) | 70, whole map | 200 | 21 (aggressive) | |
| Orc Warrior (1023) | 20, whole map | 200 | 04 (aggressive) | |
| Poporing (1031) | 15, whole map | 300 | 02 (passive, looter) | |
| Orc Baby (1686) | 5, whole map | 200 | 04 (aggressive) | calls 1 Orc Warrior + 1 Orc Lady while it has none (NPC_SUMMONSLAVE Lv 2; then a 100-min delay) |
| Orc Lord (1190), MVP | 1, whole map, `boss_monster`, respawn 7,200,000 ms + up to 600,000 | **100** | 21 | section 1c |
| Blue Plant (1079) | 3 at (46,350) +- 5, 3 at (287,61) +- 5 | immobile | plant | |
| Green Plant (1080) | 3 at (300,253) +- 5 | immobile | plant | |
| Orc Archer (1189 / 1473) | none: the Orc Lord's slaves | 300 | 09 / 04 | range 9; 1189 x 5 on its spawn, 1473 x 6 when it has <= 3 slaves |

- **The 9 warps**:
  - 4 map exits: (251,371) span 5,2 -> gef_fild09; (104,21) 5,2 -> gef_fild11;
    (370,56) 2,5 -> gef_fild03; (27,219) 1,1 -> gef_fild14;
  - 5 house doors, span 1,1 each, to in_orcs01: (136,331), (138,284), (215,51), (223,205),
    (63,337).
- **`classes_for gef_fild10`**, by slots: 1273 (70), 1023 (20), 1031 (15), 1079 (6), 1686 (5),
  1080 (3), 1190 (1), then 1473 and 1189 (0, slave of 1190).
- **Slaves die with their master and drop NOTHING** (`status_kill`, "no drops/exp":
  status.hpp:3556; mob.cpp:3619-3620). So killing an Orc Baby removes its Orc Warrior and Orc
  Lady unlooted. A slave killed first drops as usual (mob.cpp:3251-3255).
- **The Orc Lord is on the map whenever it is alive**, whoever is there. `dynamic_mobs` never
  removes an MVP from an empty map (map.cpp:3028-3050: "is a mvp"). It spawns with the map's
  first visitor (npc.cpp:5392) and comes back 120-130 min after its death (7,200,000 ms + rnd() % 600,000: mob.cpp:1072-1073, `mob_spawn_variance: 1` keeps the variance for bosses). The Crusader's walks
  to orcsdun01 crossed this map, so expect it to be there.
- **Drops** (the four target species; the full tables are printed by `kb_build.py --show-drops
  1273 1023 1686 1031` and are not copied here). The rows that carry the value are:
  - 1273: Cyfar 7053 (46.56 %), Iron 998 (3 %);
  - 1023: Orcish Voucher 931 (90 %), Axe 1301 (1 %), Iron 998 (2.1 %), Rough Oridecon 756 (0.4 %);
  - 1686: Large Jellopy 7126 (10 %), Milk 519 (50 %), Nursing Bottle 7270 (2 %), Pinafore 7269 (1 %);
  - 1031: Sticky Mucus 938 (55 %), Garlet 910 (15 %), Grape 514 (2 %).
  - The rest are rares (<= 0.10 %, cards) or low-value herbs.
  - `rate_adjustment` is None: every `item_rate_*` is 100, so the rates are mob_db's.

### 1b. Walk speeds (ms per cell; mob_db `WalkSpeed`, the Rogue's from `DEFAULT_WALK_SPEED`)

| unit | ms / cell | against the Rogue (150) |
|---|---|---|
| the Rogue | 150 (`src/common/mmo.hpp:93`; no speed skill on this build) | |
| Orc Lady, Orc Warrior, Orc Baby | 200 | the Rogue outruns them (+1 cell per 600 ms) |
| Poporing | 300 | outrun |
| **Orc Lord** | **100**; **75** under Increase AGI | **it gains 1 cell per 300 ms (per 150 ms with Increase AGI)** |
| Orc Archer (its slaves) | 300 | outrun, but they shoot from 9 cells |
| Blue / Green Plant | immobile | |

A diagonal step costs x 1.4 for every unit (unit.cpp:229, MOVE_DIAGONAL_COST 14 / MOVE_COST 10), so the ratios hold on any path.

### 1c. The Orc Lord: what it casts, and how a Rogue gets away

Its mob skills (pinned `db/pre-re/mob_skill_db.txt`, 21 lines). By the state they fire in:

| state | skill (level) | rate per check | delay | target / condition | skill range |
|---|---|---|---|---|---|
| chase | AL_INCAGI (10) | 20 % | 300 s | self | |
| chase | MG_COLDBOLT (10), MG_FIREBOLT (10) | 20 % each | 5 s | the target; no cast time | 9 |
| chase | PR_LEXDIVINA (10) | 20 % (100 % after skill 18) | 5 s | the target (Silence) | 5 |
| chase | SM_PROVOKE (10) | 20 % | 5 s | the target | 9 |
| chase / attack | NPC_EARTHQUAKE (5) | 100 % | 30 s | only below 80 % of its HP (never, unless someone hits it) | |
| attack | CR_SHIELDCHARGE (5) | 20 % | 5 s | the target (Stun) | 3 |
| attack | NPC_SHIELDBRAKE (10), NPC_GROUNDATTACK (5) | 20 % | 5 s | the target | |
| attack / idle | NPC_CALLSLAVE, NPC_SUMMONSLAVE (Orc Archers) | 100 % | 30 s / 10 s | its slaves | |
| attack | NPC_POWERUP (5) | 100 % | 120 s | below 30 % of its HP | |
| idle / walk | AL_TELEPORT | 100 % / 50 % | | when RUDE-attacked (hit and cannot reach back) | |
| idle | AL_HEAL (11) | 100 % | 5 s | below 50 % of its HP | |

- **It notices us within 10 cells** (its view range, `SkillRange` 10 = range2, mob.cpp:1897).
  It keeps a target within 12 (`ChaseRange` = range3; status.cpp:2292-2314 and
  mob.cpp:1921-1932).
- **Its chase skills are checked once per second** (`MOB_SKILL_INTERVAL` 1000: mob.hpp:42, mob.cpp:4289),
  in file order, the first that passes is cast. So a Cold or Fire Bolt follows within a second
  with ~29 % (~36 % once Increase AGI is on its 300 s delay), and within ~3 s more likely than not.
- **Damage against a Base 62 / VIT 1 Rogue** (~2,030 max HP by `JobDatabase::calc_basehp`,
  pc.cpp:13709: 35 + 62 x 5 + the Rogue's factor 85, x 1.01; before gear):
  - a Lv 10 bolt is 10 x MATK; pre-re MATK is INT + (INT / 7)^2 .. INT + (INT / 5)^2
    (status.cpp:2511-2516), INT 70 -> 170-266. So **1,700-2,660 before MDEF**, about the
    Rogue's whole HP;
  - its melee hit is ATK 3,700-4,150 at 83 % (80 + 184 - 181), every 1,248 ms;
  - its 5 Orc Archers hit at 73 % (80 + 49 + 125 - 181) for ATK 310-390, from 9 cells.
- **On foot it cannot be outrun.** It walks 1.5 x the Rogue's speed, 2 x under Increase AGI
  (status.cpp:8149-8150: GetMoveHasteValue1 25 -> x 75 / 100). Back Sliding moves 5 cells once
  and does not change that.
- **A Fly Wing (a random cell of the same map) is the escape:**
  - gef_fild10's mapflags are only nomemo and nightenabled: teleport is allowed;
  - **Silence does not block it**: the item's AL_TELEPORT skips the cant-cast check
    (status.cpp:2171, `skillitem`);
  - **Stun does** (opt1, status.cpp:2107-2111), and Shield Charge stuns from 3 cells in its
    attack state;
  - after the jump it loses us once we are beyond 12 cells (the visibility check above).
- **So the escape must fire at FIRST SIGHT**, before it is within 10 cells, and never wait for a
  hit. The client draws units within 14 cells (AREA_SIZE), and the RDP view spans more than
  that (34 x 24 px per cell in 1280 x 720). So the Orc Lord can first appear 14 cells away: 4
  cells before it can notice us, ~0.4 s if it walks straight at us.
  - The recognizer's inputs are in section 9.

## 2. The client GAT and the client / server walkability

    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\gef_fild10.gat' \
      --out /dev/shm/poring-lab-tmp/gat --decode-des
    python3 scripts/map_prep.py walkability gef_fild10

Run 2026-10-25 19:18 ICT. The archive is read in place, read-only, on the NAS mount. The GAT is a
DES-flagged entry, decoded by our header-DES.

| map | bytes | cells (w x h) | sha256 (first 16) | client walkable | server walkable | client only | server only | client-walkable on the server's edge | components (both rules) |
|---|---|---|---|---|---|---|---|---|---|
| **gef_fild10** | 3,200,014 | 400 x 400 | cc5f35bef6c4f684 | 72,656 | 72,656 | **0** | **0** | 799 | **1 of 72,656** |

- It lives in `/dev/shm/poring-lab-tmp/gat/data/gef_fild10.gat` (the runner's `camera.GAT_DIR`).
  It is client data: never committed, and gone after a host reboot (re-run the command).
- **Caveat: one archive.** This is the Thai `data.grf`. The exact server agreement is the
  evidence that its walkable cells are the lab client's.
- 45 % of the map is walkable, with no island. The houses, trees and cliffs make pockets (section 4's
  sealed pocket, section 6's priors).

## 3. Script-NPC cells (L3): first_workflow, npc_cells, route.json

    python3 scripts/kb_first_workflow.py build --kb-dir data/kb \
      --mapcache-dir packages/poring_dataset/src/poring_dataset/_generated \
      --also prt_church prt_fild08 iz_dun00 prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 gef_fild10 \
      --out /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/first_workflow.json

**first_workflow.json candidate**: built 2026-10-25 19:16:40 ICT (`built_at`).
- 522 files loaded, 0 problems, 39 maps, 38.6 s.
- sha256 `71ea31907ad53a8a12ab901970bb3292bf87d3d71f088bedd48e4802cb3ad623`.
- **Against the installed file** (sha256 first 16 `7940d6e8c2d200ff`, payf07-prep's 10:31 build,
  38 maps): **38 maps identical**, gef_fild10 added. `scope`, `completeness` (gef_fild10's counts
  and files), `built_at` and `seconds` differ. Nothing else does.

**npc_cells.json candidate**: a copy of the installed file (sha256 first 16 `82f383b0b41676b4`,
38 maps), merged with `npc-cells --only gef_fild10`, gives first 16 `821ced830d336b9d`, 39 maps.
- The 38 old blocks and the header are identical.
- A second `merged` record names gef_fild10 and the 19:16:40 build.

| NPC (file:line) | cell | sprite | kind | facing | drawn | touch area |
|---|---|---|---|---|---|---|
| the Kafra (`npc/kafras/kafras.txt:664`) | (73,340) | 116 | dialog | 5 | yes | **none** |
| a bulletin board (`npc/pre-re/other/bulletin_boards.txt:109`) | (69,340) | 837 | dialog | 5 | yes | none |
| a bulletin board (`npc/other/bulletin_boards.txt:264`) | (109,23) | 836 | dialog | 5 | yes | none; it stands on the corner of warp geff12's span |
| the Orc's Memory instance NPC (`npc/instances/OrcsMemory.txt:38`) | (242,202) | 406 | dialog | 0 | yes | none |
| the Orc's Memory quest NPC (`npc/instances/OrcsMemory.txt:108`) | (238,202) | 865 | dialog | 6 | yes | none |

- **gef_fild10 is "complete"**: every file line naming it was classified, and no script places
  anything on it at run time.
  - Its counts: 5 scripts, 9 warp lines, 8 monster lines, 2 mapflags (nomemo, nightenabled), and
    the Kafra's savepoint (54,326).
- **NOT loaded:** the custom warper / porter files (`npc/custom/warper.txt`,
  `npc/custom/etc/quest_warper.txt`, `npc/custom/etc/airplane.txt`), the events, and every
  `npc/re/` file naming the map. That is the build's `not_loaded_files_naming` list.
- **No NPC has a touch area, so the three stand-cell checks pass ON an NPC cell**: (73,340), the
  Kafra's own cell, passes. Only the zones (section 4) keep the runner off them.

**route.json candidate** (`kb_route.py --out /dev/shm/poring-lab-tmp/gef10-prep/kb-route
--first-workflow <the candidate above>`): sha256 first 16 `03347ada29018794`. Against the
installed file (first 16 `b719efa654275ffa`, built 10-21):
- gef_fild10 added (9 warps, from first_workflow.json);
- pay_fild07 / 08 / 09 and prt_fild06 re-sourced from first_workflow.json. They have the same
  geometry and the same count; the rows gain `key` / `kind` / `drawn`;
- `maps`, `npcs`, `skill_trees` and `targets` identical.
- **It is needed**: `npc_click_test.load_warps` (the stand grid, `check_warps`) reads route.json.
  The installed one lacks gef_fild10, so the runner refuses the map:
  `L3 does not cover gef_fild10's warps / touch areas: refused`.

## 4. The zones (`config/map_zones/gef_fild10.yaml`, delegated)

**The delegation.** Batt, 2026-10-25 ~13:1x ICT, answered the parent's question "Do you delegate
the gef_fild10 warp zones to me, as for pay_fild07?" with "Delegate gef_fild10 zones"
([rogue-gef10.md](rogue-gef10.md) section 0, decision 4).
- `reviewed_by: "agent (delegated by batt, 2026-10-25)"`, `reviewed: 2026-10-25`, and a
  `delegation:` note citing that answer (README format).
- **Scope note:** the question named the WARP zones; the answer says "zones". The 5 NPC areas
  below follow the brief. They are separate items (`npc-*`), and dropping them changes nothing
  else.

**The file.** 14 no-enter areas, no line:
- each warp span from warps.json (centre +- span) grown by **4 cells** on every side, as
  pay_fild07.yaml and orcsdun01.yaml;
- each NPC cell grown by 4, like a span of 0. The README's format has no NPC kind: an area is an
  area.
  - The drawn body is covered with a cell to spare. On the RDP camera (34 px per cell east,
    24 px per cell north) the Kafra's idle box (80.5 px up, 17.5 px each side) covers its cell
    and 3 cells north; a board's (58.5 px up) covers 2.
  - Sprites 406 and 865 are not in the NPC sprite catalog, so their height is not measured.
- **One exception, recorded in its note:** the door at (63,337) reaches 2 more cells west
  (x 56-68). With x 58-68 the pocket (56-57,334) was sealed off: its only way out was through
  the area. The first prove found it (2 cells cut, both connectivities). Inside the area, it is
  no longer cut.

| item | span / cell | area | walkable cells taken | arrival from the neighbour |
|---|---|---|---|---|
| `warp-gef_fild09` | geff11-1 (251,371) 5,2 | x 242-260 y 365-377 | 84 | (251,368): inside |
| `warp-gef_fild11` | geff12 (104,21) 5,2 | x 95-113 y 15-27 | 99 | (104,24): inside |
| `warp-gef_fild03` | geff05-1 (370,56) 2,5 | x 364-376 y 47-65 | 82 | (367,56): inside |
| `warp-gef_fild14` | geff19-1 (27,219) 1,1 | x 22-32 y 214-224 | 72 | (31,219): inside |
| `door-in_orcs01-136-331` | gef018 (136,331) 1,1 | x 131-141 y 326-336 | 67 | (138,329): inside |
| `door-in_orcs01-138-284` | gef019 (138,284) 1,1 | x 133-143 y 279-289 | 62 | (137,286): inside |
| `door-in_orcs01-215-51` | gef020 (215,51) 1,1 | x 210-220 y 46-56 | 72 | (214,53): inside |
| `door-in_orcs01-223-205` | gef021 (223,205) 1,1 | x 218-228 y 200-210 | 52 | (223,203): inside |
| `door-in_orcs01-63-337` | gef022 (63,337) 1,1 | x **56**-68 y 332-342 | 69 | (65,335): inside |
| `npc-kafra-73-340` | (73,340) | x 69-77 y 336-344 | 80 | |
| `npc-board-69-340` | (69,340) | x 65-73 y 336-344 | 67 | |
| `npc-board-109-23` | (109,23) | x 105-113 y 19-27 (inside `warp-gef_fild11`'s) | 50 | |
| `npc-orcsmemory-242-202` | (242,202) | x 238-246 y 198-206 | 81 | |
| `npc-orcsmemory-238-202` | (238,202) | x 234-242 y 198-206 | 81 | |

- The arrivals are the other maps' warp lines into gef_fild10, and the 5 houses' in
  `npc/warps/dungeons/orcsdun.txt`. Each is inside its own area (`in_no_enter` True for all 9).
  The cell just beyond each, on the same side, is outside.
- The areas overlap in three places (the Kafra / board / west door group, the Orc's Memory pair,
  the south board inside its warp's area). The loader allows that: the union is 1,695 cells,
  860 of them walkable on client and server.

**The proof** (2026-10-25 19:36-19:37 ICT, the final file: sha256
`6e81d8819f6d43d82e27233b1ff6a0d20d748c8e7cc5b23743fc936d46d588b7`):

    $ python3 scripts/map_zones.py check gef_fild10        # ok, 14 no_enter, 1,695 cells
    $ python3 scripts/map_zones.py prove gef_fild10 --samples 400

| grid | walkable | zone cells | pieces cut off (no corner rule / corner rule) | main component before -> after | newly unreachable | spawn cells in zones / in cut pieces |
|---|---|---|---|---|---|---|
| client ∩ server | 72,656 | 860 | **0 / 0** | 72,656 -> 71,796 | **0** | 860 of 72,656 (1.18 %) / 0 |
| the stand grid | 72,514 | 718 | **0 / 0** | 72,513 -> 71,796 | **0** | (same) |
| prove's search area (warps AND NPCs 10 off, hunt_flow's) | 69,368 | 0 | 0 | 69,368 -> 69,368 | | |

- The stand grid lacks the 142 walkable warp-span cells. Its one cell off the main component
  before the zones, (61,337), lies in the west door's area.

    $ python3 scripts/orc_dungeon_prep.py zone-clicks --map gef_fild10 --samples 400 --seed 0

| area | walkable inside | span cells | clicks INTO it refused | clicks ONTO its warp span refused | outside -> outside clicks refused (over-reach, not a leak) |
|---|---|---|---|---|---|
| `warp-gef_fild09` | 84 | 30 | **400 / 400** | **400 / 400** | 10 / 400 |
| `warp-gef_fild11` | 99 | 33 | **400 / 400** | **400 / 400** | 0 / 400 |
| `warp-gef_fild03` | 82 | 33 | **400 / 400** | **400 / 400** | 2 / 400 |
| `warp-gef_fild14` | 72 | 9 | **400 / 400** | **400 / 400** | 23 / 400 |
| `door-in_orcs01-136-331` | 67 | 7 | **400 / 400** | **400 / 400** | 149 / 400 |
| `door-in_orcs01-138-284` | 62 | 8 | **400 / 400** | **400 / 400** | 161 / 400 |
| `door-in_orcs01-215-51` | 72 | 8 | **400 / 400** | **400 / 400** | 170 / 400 |
| `door-in_orcs01-223-205` | 52 | 5 | **400 / 400** | **400 / 400** | 155 / 400 |
| `door-in_orcs01-63-337` | 69 | 9 | **400 / 400** | **400 / 400** | 205 / 400 |
| `npc-kafra-73-340` | 80 | 0 | **400 / 400** | - | 163 / 400 |
| `npc-board-69-340` | 67 | 0 | **400 / 400** | - | 167 / 400 |
| `npc-board-109-23` | 50 | 0 | **400 / 400** | - | 0 / 400 |
| `npc-orcsmemory-242-202` | 81 | 0 | **400 / 400** | - | 166 / 400 |
| `npc-orcsmemory-238-202` | 81 | 0 | **400 / 400** | - | 179 / 400 |

- Every refusal into an area is `dest_no_enter`.
- **The over-reach is large around the small village areas** (37-51 % of random pairs within
  12 cells): the straight line or the client's A* path between two cells on opposite sides
  crosses the area. It costs mobility near the houses, not safety. pay_fild07's edge warps cost
  0-5 %.

## 5. Start stands (`scripts/map_prep.py stands gef_fild10`)

The search area is built as `dungeon_hunt.run()` builds it (`map_prep.runner_area`): warps 10 off,
the zones, minus what they seal (nothing), the largest component. The stand grid has 72,514 cells,
the area 69,641 and the route grid 71,796.

| stand | cell | three stand-cell checks | client ∩ server | main component | in a zone | open neighbours | clearance | to the nearest warp span | to the nearest NPC | walk steps from START |
|---|---|---|---|---|---|---|---|---|---|---|
| **START** | **(186,179)** | pass | yes | yes | no | 8 | 6 (13 x 13) | 36 | 52 | 0 |
| FALLBACK | (186,159) | pass | yes | yes | no | 8 | 11 (23 x 23) | 45 | 52 | 20 |
| the seeded-start box | 1,717 area cells within 25 of START | **all pass** (one check_warps call) | yes | yes | no | | | | | |

- **The proposed anchor is START (186,179)**, for four reasons:
  - it is what the runner already computes (`hunt_flow.area_centre`), so nothing changes in the
    code;
  - the 4 normal species spawn whole-map random, so no spot is richer than another;
  - the centre keeps every heading's run longest before the map edge or a warp turns it;
  - every seeded start near it passes.
  - The seeds would give: 1 -> (209,158), 2 -> (164,159), 3 -> (195,162),
    20261025 -> (188,178). These are illustrative: the cell is drawn per run.
- **Positive cases through the same call:**

| cell | expected | result |
|---|---|---|
| (251,371), a warp centre | refused | refused: "stand (251, 371) in geff11-1 -> gef_fild09" |
| (251,369), the span's edge | refused | refused |
| (251,368), one cell outside the span (the arrival) | passes | passes (the zones keep it) |
| (223,205), a door centre | refused | refused: "in gef021 -> in_orcs01" |
| (104,23) / (104,24), the south span's edge / one outside | refused / passes | refused / passes |
| (158,150), a server-NOPASS cell | refused | refused: "the server does not let the GM stand on" |
| a touch area: prontera (45,67) | refused | refused: "in an NPC touch area" (gef_fild10 has none) |
| (73,340), the Kafra's own cell | passes (no touch area) | passes: **only the zones cover it** |

## 6. Rest spots: what is possible without gef_fild10 packets

- **The measured method needs banked packets.** `orc_dungeon_prep.py rest-spots` reads the GM's
  view of every monster during warp-and-watch dwells, and none exist on gef_fild10. It is also
  still orcsdun01-only: `MAP`, its spawn box (15..184) and `ENTRANCE` are module constants.
  Running it on gef_fild10's first runs' packets needs a `--map` generalisation first.
- **Without a rest file the runner sits where it stands** (4.03 Amendment C). On gef_fild10 that
  is ~0.56 aggressive monsters expected within 10 cells (the median cell).
- **A GEOMETRY PRIOR is possible now** (`orc_dungeon_prep.static_reach`: walkable cells with a
  clear straight line within 10).
  - Every walkable cell is spawnable here: the 4 normal species spawn on the whole map.
  - E[aggressive within 10] = 105 x reach / 72,656. The 105 are Orc Lady 70, Orc Warrior 20,
    Orc Baby 5 and its 2 slaves each.
  - `pick_spots` keeps 20 cells between candidates, over the runner's area on the zone-free route
    grid. Each passes the three checks.

| candidate | reach (cells in line of sight within 10) | E[aggressive within 10] | free neighbours | walk steps from START | to the nearest warp span |
|---|---|---|---|---|---|
| (155,310) | 20 | 0.029 | 4 | 138 | 20 |
| (247,259) | 21 | 0.030 | 3 | 180 | 53 |
| (142,221) | 22 | 0.032 | 5 | 84 | 62 |
| (254,48) | 29 | 0.042 | 4 | 132 | 38 |
| (265,222) | 32 | 0.046 | 4 | 84 | 41 |

- These are narrow pockets (clearance 0): fewer attackers at once (3-5 free neighbours), but a
  monster that walks in finds us.
  - The line of sight is an approximation: an aggressive mob notices a target by a walk path in
    view range, not a straight line.
  - The walks cost 84-180 steps (13-27 s at 150 ms per cell), and `REST_WALK_MAX_S` is 120 s.
- **Not installed.** No `config/dungeon/gef_fild10.json` is written: the runner would use it.
  The list is in `/dev/shm/poring-lab-tmp/gef10-prep/rest-prior.json`.
  - The parent / Batt decide prior vs none. The pilot's packets can then confirm or replace it.

## 7. What `dungeon_hunt.py` `run()` needs per map, and what gef_fild10 has

Read from the CURRENT runner (main at 5af7a1f, `VERSION = "dungeon@7"`, `--map` / `--char` since
dungeon@6). It is unchanged here: the parent edits the runner.

| # | input | where (today) | gef_fild10 | what to do |
|---|---|---|---|---|
| 1 | the map | `--map M` (dungeon@6; default `MAP = "orcsdun01"`) | - | pass `--map gef_fild10` |
| 2 | script NPCs / the melee-ring allowlist | only for `--engage melee_ring`: `MR_MAPS = {"orcsdun01"}` and npc_cells' `npcs` must be empty | **5 NPCs** (section 3) | **the default `defend_scan` never reads npc_cells: the runner does NOT refuse a map with NPCs.** melee_ring is refused twice: not in MR_MAPS, 5 NPCs. Its lint (`melee_ring_species`) would also need the Orc Lord as a TARGET. Keep defend_scan |
| 3 | the client GAT | `cam.GAT_DIR / "gef_fild10.gat"` | **yes** (section 2) | re-extract after a host reboot |
| 4 | the stand grid | `anim_region.stand_grid`: route.json warps + first_workflow touch areas + both sources | **refused** with the installed KB (route.json and first_workflow.json lack the map) | install the candidates (section 10) |
| 5 | the warp keep-away (search area) | `data/kb/warps.json`, read with `.get(map_, [])` | absent in the installed KB -> **[] silently** | install the kb_build candidate WITH route.json. Suggested: fail closed when the map is absent (today only #4's refusal hides it) |
| 6 | the NPC keep-away | none: `hunt_core.search_area` gets the warps only (hunt_flow and `map_zones.prove` also keep NPC cells 10 off) | 5 NPCs, no touch area | **the zones' 5 NPC areas are the runner's only NPC keep-away.** Optional (the parent's call): pass npc_cells' cells to `keep` too. The runner's area is then 69,368 cells, not 69,641 |
| 7 | the zones (required) | `map_zones.load(map_)` | **yes**, delegated, proved (section 4) | merge the file |
| 8 | rest spots | `config/dungeon/<map>.json`, optional | none (absent = sit where it stands) | section 6: the prior or none; packets later |
| 9 | White Plant sweep areas | `plant_finder.spawn_areas(map_)`, job 1082, from spawns.json | none (Blue / Green Plants only) | inert; `--plant-sweep` is off by decision 6 |
| 10 | the patrol route | `config/routes/<map>.yaml`, `--search patrol` only | none | the heading search needs none |
| 11 | the start | `hunt.start_cell(area, seed, near=hf.area_centre(area))` | **(186,179)**; the box passes (section 5) | - |
| 12 | camera + altitude | `camera_rdp.json`, `gat.relative_altitude` | yes | - |
| 13 | name-tag templates | `nametag.map_dir`: `data/nametags/gef_fild10/templates.npz` | none | tags are BANKED by default off orcsdun01; nothing matches until templates are cut. dungeon@7 does not need them |
| 14 | the Etc drop / the store | `CLEAR_AT = 0.40`, `CLEAR_STAND` (prt_fild08 268,107), `clear_etc` per character | - | the store step replaces it for the Rogue (rogue-gef10.md 4; the parent) |
| 15 | the character | `CHARS_CONF`: crusader, thief | - | `--char rogue`: identity, keys F1 / F2 / F3, max HP / SP, stock (the parent) |
| 16 | the box watcher | `unit_detector` v1, class-agnostic (player / monster / npc) | zero-shot unmeasured here | it may box the Kafra and boards as `npc` |
| 17 | the Fly Wing escape / map-change bar | `JUMP_CELLS = 20`, `FLY_*` | teleport allowed (mapflags nomemo + nightenabled only) | - |
| 18 | the offline judge | `dungeon_judge.py row SID --map`; `CHAR_MAX_HP / SP` (crusader, thief); `TARGET_ITEMS` and the staged flag are pay_fild07's | econ: data/econ/maps.json already holds gef_fild10 (built 10-24, reproduced identically here) | the parent: the Rogue's max HP / SP; the gef_fild10 item list |

**What differs from pay_fild07:**
- **Script NPCs:** pay_fild07 had none, gef_fild10 has 5 dialog NPCs (two of them in the village
  near the west door, two near the door at (223,205), one on the south exit's span). A click on
  one is the NPC-contact hard bar. Only the zones keep the runner off them (rows 2, 6).
- **Aggressive:** 95 of 110 normal monsters (86 %), plus the Orc Babies' slaves. pay_fild07 had
  37 %. DEFEND-SCAN's premise (they come to us) holds as on orcsdun01.
- **The Orc Lord MVP and its 5 Orc Archers** (section 1c): no recognizer yet. Meeting them is
  most likely a death (a RESULT) unless the escape fires at first sight.
- **5 house doors** inside the field (1-cell spans), not only edge exits. A walk into one is a map
  change (a hard bar). The zones cover them.
- Body-height constants (`ARROW_UP 150`, `BODY_UP 26`) were measured on orcsdun01's orcs.
  gef_fild10's orcs are 86-96 px tall idle (section 9), close to them; unmeasured here.

## 8. The econ model at Overcharge (`scripts/econ_model.py`)

**Overcharge already existed.**
- `econ_items.overcharge` implements `pc_modifysellvalue` at the pin: rate = 5 + 2 L - (L == 10)
  = 24 % at Lv 10; `(int32)(value_sell x 124 / 100.)` truncated PER UNIT (pc.cpp:5708-5719,
  re-read here). It is then x the amount (npc.cpp:3080-3082) and >= `min_shop_sell` 0
  (conf/battle/items.conf:138). The client's sell list shows the same per-unit value
  (clif.cpp:2309).
- `items.json` carries `sell_oc10`; `econ_model` `show` / `table --oc` and `econ_row` (`V_oc`,
  `gross_h_oc`, `net_h_best`) use it. So the judge already reports value per hour at Overcharge.
- gef_fild10 was already a candidate map (built 10-24 10:55). A rebuild here
  (`build gef_fild10 --out /dev/shm/...`) gives identical species, mix and trips.

**Added on this branch:**
- `econ_model.py species MAP [--L 1.0] [--top 3]`: value per kill PER SPECIES, at NPC sell and
  at Overcharge, then the spawn mix and the mix without plants (`species_rows`, pure, tested).
- A test pins the per-unit truncation on this map's main prices (386 -> 478, 71 -> 88,
  420 -> 520, 35 -> 43, 20 -> 24; a stack of 10 Sticky Mucus is 430, not 434).
- The gef_fild10 candidate's note names the Rogue.

| species | spawns | V (NPC sell) | **V_oc (Overcharge)** | W (weight / kill) | rare_v (NPC sell, apart) | the bulk of V_oc |
|---|---|---|---|---|---|---|
| Orc Lady (1273) | 70 | 181.22 | **224.42** | 0.616 | 5.95 | Cyfar 7053: 0.4656 x 478 = 222.56 |
| Orc Warrior (1023) | 20 | 68.55 | **84.97** | 1.885 | 2.71 | Orcish Voucher 931: 0.90 x 88 = 79.20 |
| Orc Baby (1686) | 5 | 63.90 | **78.71** | 1.630 | 0.002 | Large Jellopy 7126: 0.10 x 520 = 52.00 |
| Poporing (1031) | 15 | 24.68 | **30.23** | 0.940 | 0.60 | Sticky Mucus 938: 0.55 x 43 = 23.65 |
| Blue Plant (1079) | 6 | 50.82 | 62.76 | 4.345 | 0.002 | Mastela Fruit 522 (0.5 %) and Blue Herb 510 |
| Green Plant (1080) | 3 | 17.77 | 21.69 | 2.675 | 0.002 | Stem / Pointed Scale |
| **the spawn mix, no plants** | 110 | 134.06 | **165.96** | 0.937 | | |
| the spawn mix (normal lines) | 119 | 126.93 | 157.12 | 1.152 | | |

- **Rares are out of V by the model's rule** (Batt: "no rares"; base rate <= 0.10 %, every
  card). rogue-gef10.md 2c's figures (~232 / ~88 / ~79 / ~31, ~171 weighted) include them, at
  Overcharge. The two agree once the rares are added back: e.g. Orc Lady 224.42 + 5.95 x 1.24.
- The Orc Lord's drops are MVP drops: never in V, and never a target.
- At 4.04's 35.7 kills / h (the Thief on pay_fild07; the Rogue's K is unmeasured), the mix
  without plants is ~5,925 z / h at Overcharge and ~33 weight / h.
  - `show gef_fild10 --K 35.7 --L 1.0 --oc` (plants in): G 5,609 z / h, 41.1 weight / h.
  - The nearest way to reset the bag is the map's own Kafra: T 90.3 s, fee 130 z. The nearest
    NPC that buys is in geffen_in: T 479 s.
  - The model's `C` is the Crusader's (1,155). For the Rogue: 0.5 x 2,430 - ~505 fixed ~= 710.

## 9. The species' sprites (client stems, idle boxes)

    python3 scripts/npc_sprites.py mob-names 1273 1023 1686 1031 1190 1079 1080 1189 1473 \
      --mobs data/kb/mobs.json --out /dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/monster_sprite_names.json
    python3 scripts/sprite_catalog.py --aegis orc_lady ork_warrior orc_baby poporing orc_lord blue_plant \
      green_plant orc_archer --work /dev/shm/poring-lab-tmp/gef10-prep/sprites \
      --out /dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/sprite_catalog.json --decode-mixcrypt

Run 2026-10-25 19:20 ICT from the Thai data.grf (NAS, read-only). Every SPR is MIXCRYPT (0x03),
decoded study-only (Batt 2026-10-05); every ACT is DES-header (0x05). 0 problems.

| species (mob id) | spawns | walk (ms / cell) | idle sprite box (native px, x0 y0 x1 y1) | idle size | flies? | sprite stem | idle hue / saturation |
|---|---|---|---|---|---|---|---|
| Orc Lady (1273) | 70 | 200 | -25.5 -76 25.5 10 | 51 x 86 | no | `orc_lady` | 73° / 0.35 |
| Orc Warrior (1023) | 20 | 200 | -31.5 -83 33.5 13 | 65 x 96 | no | `ork_warrior` | 36° / 0.35 |
| Orc Baby (1686) | 5 | 200 | -12.5 -46.5 32.5 4.5 | 45 x 51 | no | `orc_baby` | 56° / 0.42 |
| Poporing (1031) | 15 | 300 | -18.5 -30 18.5 6 | 37 x 36 | no | `poporing` | 74° / 0.30 |
| **Orc Lord (1190)** | 1 | **100** | **-35.5 -89 45.5 11** | **81 x 100** | no | `orc_lord` | **41° / 0.38** |
| Orc Archer (1189, 1473) | its slaves | 300 | -23 -77.5 43 11.5 | 66 x 89 | no | `orc_archer` (both ids; 1473's aegis is G_ORC_ARCHER) | 30° / 0.36 |
| Blue Plant (1079) | 6 | immobile | -20 -15 20 15 | 40 x 30 | no | `blue_plant` | 220° / 0.64 |
| Green Plant (1080) | 3 | immobile | -20 -15 20 15 | 40 x 30 | no | `green_plant` | 83° / 0.42 |

- The stems equal the aegis names lower-cased, except 1473 (the Orc Archer's sprite).
- **No species flies:** every idle box reaches the ground (y1 > 0).
- The hue and saturation are those of the rendered idle frame (`orc_camera_check.reference_hue`,
  direction 0, frame 0). The opaque pixels: Orc Lord 4,721, Orc Warrior 3,746, Orc Archer 2,742,
  Orc Lady 2,906.
- **For an Orc Lord recognizer:**
  - **colour does not separate it** from the Orc Warrior or its own Orc Archers (hue 41 / 36 /
    30°, saturation 0.38 / 0.35 / 0.36, value 0.47 for all three);
  - its **width does**: 81 px against 65 and 66;
  - so does its opaque area: +26 % over the Orc Warrior;
  - its attack envelope is much larger (158 x 166);
  - and **it never walks alone**: its 5 Orc Archers are summoned within 2 cells of it
    (MOB_SLAVEDISTANCE) and follow it.
  - Look-alikes for the detector: Orc Lady and Poporing share a hue (73° / 74°) but differ in
    brightness (value 0.41 vs 0.79) and size.
- **Left for the parent in /dev/shm (client-derived, never committed):**
  `/dev/shm/poring-lab-tmp/gef10-prep/sprites/data/sprite/몬스터/orc_lord.spr` and `.act`, and the
  other 7 stems' beside them; the catalog and the names in
  `/dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/`.
  - These two files are NOT for data/kb as they are: they hold these 9 ids / 8 stems only.
    Merge them, or the installed ones lose their species.

## 10. Pending, install steps, limits

**PENDING the parent (in this order):**
1. Merge this branch. `config/map_zones/gef_fild10.yaml` then loads on the main checkout.
2. Install the KB candidates. Check the installed sha256 first, then copy; the four sha256 below
   are the ones verified here:

        cp /dev/shm/poring-lab-tmp/gef10-prep/kb/spawns.json /dev/shm/poring-lab-tmp/gef10-prep/kb/warps.json \
           /dev/shm/poring-lab-tmp/gef10-prep/kb/classes.json /dev/shm/poring-lab-tmp/gef10-prep/kb/kb.lock.json data/kb/
        cp /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/first_workflow.json data/kb/
        cp /dev/shm/poring-lab-tmp/gef10-prep/kb-route/route.json /dev/shm/poring-lab-tmp/gef10-prep/kb-route/route.md data/kb/
        cp /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/npc_cells.json data/kb/   # only if data/kb/npc_cells.json is still 82f383b0b41676b4...

   - spawns `9beb3a14c0645f8d`, warps `4811b8eb367e7852`, classes `96e38a7cc18785fd`,
     first_workflow `71ea31907ad53a8a`, route `03347ada29018794`, npc_cells `821ced830d336b9d`.
   - If npc_cells.json changed meanwhile, re-merge instead:
     `python3 scripts/kb_first_workflow.py npc-cells --kb data/kb/first_workflow.json --out data/kb/npc_cells.json --only gef_fild10`.
3. Re-run on the main checkout: `map_zones.py check gef_fild10`, `map_zones.py prove gef_fild10`
   and `map_prep.py stands gef_fild10`. Expect sections 4-5's numbers.
4. The runner items of section 7 (rows 5, 6, 15, 18), and the Orc Lord escape from 1c.

**Not done, limits:**
- No rest spot is measured (section 6). The rest-spot method also needs `--map`.
- **One archive** for the GAT and the sprites: the Thai `data.grf`, not the lab client's kRO one.
- The NPC area sizes rest on two catalogued sprites (Kafra, board). Sprites 406 and 865 are
  unmeasured.
- The Rogue's max HP (~2,030) is the pinned formula at VIT 1 without gear. The bolt damage is
  before MDEF. Both are read off the status window after the build (rogue-gef10.md 3c).
- No live action, no GPU, nothing written to data/kb or the NAS. Only cells, ids, counts and
  derived values are quoted. The KB files, the GAT and the sprites stay local.

## 11. Reproduce

    W=<checkout>; export PYTHONPATH=$W/scripts:$W/packages/poring_dataset/src:$W/packages/poring_env/src:$W/packages/poring_packets/src:$W/packages/poring_flow/src
    python3 scripts/kb_build.py --out /dev/shm/poring-lab-tmp/gef10-prep/kb --maps prt_fild08 iz_dun00 iz_dun01 orcsdun01 pay_fild07 gef_fild10 --show-drops 1273 1023 1686 1031 1190
    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\gef_fild10.gat' --out /dev/shm/poring-lab-tmp/gat --decode-des
    python3 scripts/map_prep.py walkability gef_fild10
    python3 scripts/kb_first_workflow.py build --kb-dir data/kb --mapcache-dir packages/poring_dataset/src/poring_dataset/_generated --also prt_church prt_fild08 iz_dun00 prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 gef_fild10 --out /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/first_workflow.json
    cp data/kb/npc_cells.json /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/npc_cells.json
    python3 scripts/kb_first_workflow.py npc-cells --kb /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/first_workflow.json --out /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/npc_cells.json --only gef_fild10
    python3 scripts/kb_route.py --out /dev/shm/poring-lab-tmp/gef10-prep/kb-route --first-workflow /dev/shm/poring-lab-tmp/gef10-prep/kb-fw/first_workflow.json
    # sections 4-5 need the candidates in data/kb (here: the tmpfs worktree's own copy of data/kb)
    python3 scripts/map_zones.py check gef_fild10 && python3 scripts/map_zones.py prove gef_fild10 --samples 400
    python3 scripts/orc_dungeon_prep.py zone-clicks --map gef_fild10 --samples 400 --seed 0
    python3 scripts/map_prep.py stands gef_fild10
    python3 scripts/econ_model.py species gef_fild10          # data/econ/maps.json (built 10-24) holds gef_fild10
    python3 scripts/npc_sprites.py mob-names 1273 1023 1686 1031 1190 1079 1080 1189 1473 --mobs data/kb/mobs.json --out /dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/monster_sprite_names.json
    python3 scripts/sprite_catalog.py --aegis orc_lady ork_warrior orc_baby poporing orc_lord blue_plant green_plant orc_archer --work /dev/shm/poring-lab-tmp/gef10-prep/sprites --out /dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/sprite_catalog.json --decode-mixcrypt
