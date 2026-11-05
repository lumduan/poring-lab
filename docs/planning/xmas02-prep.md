---
doc_type: research
hypothesis: "Before the Rogue's first runs on xmas_dun02 (rogue-xmas02.md), the offline map prep that gef_fild10 had (the KB with the map's sources, the client / server walkability, script-NPC cells, the zones, Batt's edge loop as a patrol route, start stands on it, the runner's per-map inputs, the species' sprites, the X2 scoring path) can be produced from the local sources alone, with no live action."
status: "MEASURED offline 2026-11-05 14:47-15:10 ICT (from `date`; no client, no GPU, no input, nothing written to data/kb or the NAS). The zones file and the routes file are committed under the review fields the parent's X1 brief set (Batt's order of 2026-11-05 ~13:2x cited) and proved: 0 cells cut off; the edge loop is 85 waypoints, 952 cells a lap, every leg exactly on its edge segment. The KB, first_workflow, npc_cells and route.json candidates are in /dev/shm, NOT installed (section 8)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-xmas02.md, gef10-prep.md, gef10-detector.md, ../benchmarks/gef10-eval.md, ../../config/map_zones/xmas_dun02.yaml, ../../config/routes/xmas_dun02.yaml, ../../scripts/map_prep.py, ../../scripts/dungeon_hunt.py]
next_action: "The parent: install the KB candidates (section 8), re-run section 9's checks on the main checkout; the runner items of section 5 (rows 1, 11, 16-18 need code: the start stand on the loop and level_hold 63 -> 99 above all); amend the X2 pre-registration with section 7's open points BEFORE its recording."
title: "xmas_dun02 prep for the Rogue: KB, walkability, zones, the edge loop, stands, runner inputs, sprites, the X2 scoring path"
date: 2026-11-05
owner: Batt
---

# xmas_dun02 prep for the Rogue's edge-loop runs (X1)

**The brief** (the parent session, 2026-11-05 ~14:4x ICT; [rogue-xmas02.md](rogue-xmas02.md)
section 2, X1). Do for xmas_dun02 what [gef10-prep.md](gef10-prep.md) did for gef_fild10, with
Batt's technique as the route. His order (2026-11-05 ~13:2x, Thai, translated in rogue-xmas02.md
section 0): "the map is a bit hard: it is hard to walk, many things block the way, but there is a
technique: walk along the edge of the map, going clockwise round and round. If you meet the boss,
run away."

Offline only, in a tmpfs worktree, on the pinned pre-renewal rAthena
`e985006171d2eb320ee512a653f4c83aea3d81b6`. Both new source files
(`npc/pre-re/mobs/dungeons/xmas_dun.txt` sha256 `09202ac2…c9baac`, `npc/warps/dungeons/xmas_dun.txt`
`1059657b…6f02c`) were fetched at the pin and agree byte for byte with the read-only mirror
`/dev/shm/poring-lab-rathena-src`. No rAthena table is copied here: only cells, ids, counts and
derived values.

## 0. Bottom line

1. **KB** (section 1): the candidate matches rogue-xmas02.md section 1 exactly: 6 species
   (Myst Case 50, Cruiser 35, Cookie 20, Christmas Cookie 20, Garm Baby 1, the Stormy Knight MVP 1),
   one warp (129,130) span 1,1 -> xmas_dun01. `classes_for` adds the MVP's slave **Christmas
   Goblin (1607), aggressive, 100 ms per cell**. The candidate differs from the installed KB only
   by added maps (xmas_dun01, xmas_dun02) and one more `xmas` warp row.
2. **No script NPC** on the map (npc_cells: `complete`, 0 NPCs); its only other script line is the
   Kafra dungeon teleport's arrival at (130,123) (`npc/kafras/dts_warper.txt`).
3. **Zones** (section 2): `config/map_zones/xmas_dun02.yaml`, one no-enter area, the warp span + 4
   (x 124-134, y 125-135). `check` ok; `prove`: **0 cells cut off, 0 newly unreachable** (both
   connectivities, both grids); 400 / 400 clicks into it and 400 / 400 onto the span refused.
4. **The edge loop** (section 3): `config/routes/xmas_dun02.yaml`, one loop, CLOCKWISE, **85
   waypoints, 952 cells a lap (cost 952.0: not one diagonal step), ~143 s at 150 ms per cell**.
   Each leg's A* path on the route grid IS its edge segment (0 cells off it): no leg cuts through
   the interior.
5. **Stands** (section 4): **START (7,21)** = waypoint 0, **FALLBACK (114,23)** = waypoint 74.
   Both pass the three stand-cell checks and lie outside the zone; START joins the loop at
   waypoint 1.
   - **The runner today would NOT start there:** `hunt.start_cell(area, ...)` draws near the
     search area's centre, **(141,129), in the maze 11 cells from the warp span**.
   - **`hunt_core.search_area` drops a 20-cell border**, so **732 of the loop's 952 cells lie
     outside the runner's search area** (only the south edge, x 20-239, is inside). In patrol mode
     the area is used only for the start, so the patrol itself is not blocked by it.
6. **The runner** (section 5): `--map xmas_dun02 --search patrol` loads with no map code change
   once the KB is in. Two code changes are needed before a run:
   - a start stand on the loop;
   - the Rogue's `level_hold` 63 -> 99 (the parent's). **At hold 63 the setup would LOWER the
     Base-99 Rogue back to 63** (`level_lines`).
   - Also: its max HP / SP in `CHARS_CONF` and in `dungeon_judge.py`.
7. **Sprites** (section 6): the stems equal the aegis names lower-cased (the Christmas Goblin:
   `gobline_xmas`). No species flies.
   - **The Stormy Knight is drawn 141 x 133 px idle**: about twice any other species (the widest
     other is Garm Baby at 74). Its hue (334°) is the map's red, so **size separates it, colour
     does not**.
   - **Cookie and Christmas Cookie share their images**: the SPRs differ only in the palette. The
     hue is 44° against 3°.
8. **X2 scoring** (section 7): the pieces exist (labels, the camera, the scorer's matching rule)
   but **5 things are missing or must be decided before X2's recording**. Among them:
   - a CPU-ONNX predictor that saves per-frame boxes for a recorder session;
   - the scorer's per-map species list and a recorder-session input;
   - a definition of per-species precision for a class-agnostic detector;
   - which label rule (the full gef10 o3h method needs a FIT part and a re-measured T_h);
   - the 2026-11-05 chat window in the in-view rule.

## 1. The KB (`scripts/kb_build.py`, the candidate)

`kb_build.py --out /dev/shm/poring-lab-tmp/x1/kb --maps prt_fild08 iz_dun00 iz_dun01 orcsdun01
pay_fild07 gef_fild10 xmas_dun02`, built 2026-11-05 14:48:44 ICT (`kb.lock.json` `built_at`).
`SPAWNS` / `WARPS` already list both xmas_dun files on main (85394ba). Against the installed
`data/kb` (the gef10-prep candidates, installed 2026-10-25 19:49):

| file | candidate sha256 | installed (first 16) | difference |
|---|---|---|---|
| mobs, mob_skills, items, drops, server | | | **identical** |
| spawns.json | `3337ab448d1c3a4e71d9ad864aa8a523b99c7d8eb899433d5f11cc3498f2606c` | `9beb3a14c0645f8d` | + xmas_dun01, xmas_dun02; nothing else |
| warps.json | `ce0796df9ab36a9f0247e7f81acd087ed84562756d44521ba3955b38294d5d6d` | `4811b8eb367e7852` | + xmas_dun01, xmas_dun02; `xmas` 12 -> 13 rows (its dungeon entrance) |
| classes.json | `3900bced3ed5aa17cb2cd3515bdbb459a9b71b48ccafa27d86e4fa4e7fb5e6b7` | `96e38a7cc18785fd` | + xmas_dun02; the six maps before unchanged |
| kb.lock.json | `697b1f633e04bba5b136005d95d0e5886fc3dee0c80cfd5b0511532c33190ee4` | `cd77b068f3463aa1` | + the 2 input files; the ref and every other input unchanged |

**xmas_dun02 against rogue-xmas02.md section 1** (all agree):

| id | species (mob_db name) | spawns | respawn (ms) | walk (ms / cell) | AI | via |
|---|---|---|---|---|---|---|
| 1249 | Myst Case | 50, whole map | 0 | 400 | 17 (passive) | spawn |
| 1248 | Cruiser | 35, whole map | 0 | 400 | 05 (aggressive, range 7) | spawn |
| 1246 | Christmas Cookie | 20, whole map | 0 | 400 | 17 (passive) | spawn |
| 1265 | Cookie | 20, whole map | 0 | 200 | 03 (passive, assist) | spawn |
| 1515 | Garm Baby ("Baby Hatii" in mob_db) | 1, whole map | 1,800,000 | 450 | 04 (aggressive) | spawn |
| 1251 | Stormy Knight, MVP (`boss_monster`) | 1, whole map | 3,600,000 + up to 600,000 | 200 | 21 (aggressive) | spawn |
| 1607 | **Christmas Goblin** | none | | **100** | 21 (aggressive) | **slave of 1251** (NPC_SUMMONSLAVE, attack and idle) |

- **The one warp:** `xmas_dun2-2` at (129,130), span 1,1 (trigger cells x 128-130, y 129-131) ->
  xmas_dun01 (132,130). The arrival from xmas_dun01 is (131,130).
- **The Stormy Knight also summons Garm Baby** (idle state). `classes_for` lists it once, as a
  spawn.
- **The Christmas Goblin is NEW information**: it is not in rogue-xmas02.md. It walks 100 ms per
  cell, faster than the Rogue (150), and it comes only with the MVP.
- **The MVP respawns 60-70 min after its death.** So a run started after the setup's
  `@killmonster2` (`--clear-map`) can meet it again after ~60 min. Garm Baby comes back after
  30 min.
- **Mapflag:** `nomemo` only (`npc/mapflag/nomemo.txt:380`). Teleport and Fly Wing work.

**first_workflow.json candidate** (`kb_first_workflow.py build --kb-dir data/kb --mapcache-dir
packages/poring_dataset/src/poring_dataset/_generated --also prt_church prt_fild08 iz_dun00
prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 gef_fild10 xmas_dun02`, built 14:50:05 ICT,
522 files loaded, 0 problems, 40 maps, 36.3 s):
- sha256 `b8c7fedb0dede906fd4f2fd46bfef73b8fd48f3b5dda24a029a7a1648fb8fa24`;
- against the installed (`71ea31907ad53a8a`, 39 maps): the 39 maps identical, xmas_dun02 added;
  `built_at`, `scope` (maps, also), `completeness` and `seconds` differ, nothing else;
- xmas_dun02: 1 warp, 6 spawn lines, **0 NPCs**, mapflag `nomemo`, nothing unparsed. Its counts:
  6 monster lines, 1 warp line, 1 warp line to it, 1 mapflag, and 3 script warps naming it (the
  Kafra dungeon teleport, `warp "xmas_dun02",130,123`, three menu branches of one NPC).

**npc_cells.json candidate** (a copy of the installed `821ced830d336b9d`, merged with `npc-cells
--only xmas_dun02`): sha256 `2d029f69f05841b71d06a64ec00f6490db33cdd83f8b1369a96470bdd22cf01f`.
The 39 old blocks and the header are identical. xmas_dun02 is `{"complete": true, "npcs": []}`,
and a third `merged` record names it and the 14:50:05 build.

**route.json candidate** (`kb_route.py --out /dev/shm/poring-lab-tmp/x1/kb-route --first-workflow
<the candidate above>`): sha256 `4178fffc470e48837e809523ba03d7798a02827c8d853bd194a26eccc5de9365`.
Against the installed (`03347ada29018794`): xmas_dun02 added (its 1 warp, from first_workflow.json);
`warps_source` gains the map; nothing else changed. `route.md` is byte-identical to the installed
one (`2d6b69b0…`). **It is needed**: the stand grid (`npc_click_test.load_warps`) refuses a map
route.json does not cover.

**Walkability** (`map_prep.py walkability xmas_dun02`; the client GAT
`/dev/shm/poring-lab-tmp/gat/data/xmas_dun02.gat`, 1,352,014 bytes, sha256 first 16
`4cf9265fcce2fec4`): 260 x 260, **client 50,183 = server 50,183, 0 disagreements either way**,
519 client-walkable cells on the server's edge. ONE component of 50,183 cells with and
without the corner rule. The stand grid has 50,174 cells: the 9 warp-span cells are out.

## 2. The zones (`config/map_zones/xmas_dun02.yaml`)

**The review fields** are the parent's X1 brief's:
- `reviewed_by: "agent (delegated by batt, 2026-11-05)"`, `reviewed: 2026-11-05`;
- a `delegation:` note quoting Batt's order (section 0 above).
- **The reason given:** the keep-out around the only exit warp is the edge technique's safety
  necessity. A walk or click onto the warp is a map change, a hard bar.
- **No separate "do you delegate this file" question was asked**, unlike gef_fild10's. The
  README records that.

**The file.** One no-enter area, `warp-xmas_dun01`: the span grown by **4** on every side (x 124-134,
y 125-135), as orcsdun01 / pay_fild07 / gef_fild10. 121 cells, 104 walkable on client and server
(95 on the stand grid).
- **The arrival (131,130) is inside.** It is one step from the trigger, so nothing may stand
  there.
- **The Kafra teleport's arrival (130,123) is outside**, 2 cells south of the area.
- The area sits in the map's central chamber, between its two wall rows (y 124-125 and 134-135).

**The proof** (2026-11-05 15:07:55 ICT, the final file, sha256
`440149ede297799d131f7fedef51dd307d9ef3b8e7cd51f77202b2756919c1ed`):

    $ python3 scripts/map_zones.py check xmas_dun02          # ok, 1 no_enter, 121 cells, 104 walkable
    $ python3 scripts/map_zones.py prove xmas_dun02 --samples 400

| grid | walkable | zone cells | pieces cut off (no corner rule / corner rule) | main component before -> after | newly unreachable | spawn cells in zones / in cut pieces |
|---|---|---|---|---|---|---|
| client ∩ server | 50,183 | 104 | **0 / 0** | 50,183 -> 50,079 | **0** | 104 of 50,183 (0.21 %) / 0 |
| the stand grid | 50,174 | 95 | **0 / 0** | 50,174 -> 50,079 | **0** | (same) |
| the search area (warps 10 off, the 20-cell border) | 40,327 | 0 | 0 | 40,327 -> 40,327 | | |

    $ python3 scripts/orc_dungeon_prep.py zone-clicks --map xmas_dun02 --samples 400 --seed 0

- Into the area: **400 / 400 refused**, all `dest_no_enter`.
- Onto the warp span: **400 / 400 refused**.
- Outside -> outside: 207 / 400 refused. The east-west corridor of the central chamber runs
  through the area, so most short paths across the centre cross it. That costs mobility in the
  centre only; the edge loop never comes within 107 cells (Chebyshev) of the warp.

## 3. The edge loop (`config/routes/xmas_dun02.yaml`)

**The route IS Batt's technique**: the map's edge, clockwise. The polyline is rogue-xmas02.md
section 1's:

    (7,21) -> (7,253) -> (251,253) -> (251,156) -> (240,156) -> (240,23) -> (11,23) -> (11,21) -> (7,21)

Every cell of those 8 segments is walkable on the stand grid (0 blocked).
- **The corridor widths** (free cells across the segment): the west side min 2 (at y 136-137,
  x 6-7), median 6; the north side min 4, median 10; the east side min 4.
- The (11,23) -> (11,21) -> (7,21) step goes round the wall end at x 9-10, y 22.

**The waypoints (the agent's only part):**
- each of the 8 corners keeps its own waypoint;
- each side is split into ceil(length / 12) equal legs, so the waypoints are 10-12 cells apart;
- the corner legs are 11, 2 and 4 cells.
- 85 waypoints, file sha256 `ba7dd5f600cb4fa1c6a4367b59c9587d138825aa143363d5bd3e78a0640c8e8a`.

**The proof** (2026-11-05 14:55:54 ICT, with the final zones file):

    $ python3 scripts/map_routes.py check xmas_dun02          # ok: 1 route, 85 waypoints, 85 legs
    $ python3 scripts/map_routes.py prove xmas_dun02          # ok, problems []

- Every waypoint is walkable and outside the zone. Every leg, the closing one included, is
  connected on the route grid.
- **The lap: 952 cells, cost 952.0 straight steps.** Not one diagonal step. Legs are 2-12 cells.
- **~143 s a lap at the Rogue's 150 ms per cell, with no fights.**
- **The per-leg path check** (a scratch script on the same grid: `map_routes.leg_path` for each
  leg, then `seg_dist` of every path cell to its leg's straight segment):
  - **the worst distance is 0**;
  - **0 path cells lie off their segment**.
  - So each A* path is its edge segment itself, and no leg cuts through the interior.
- **Clockwise, checked:** the shoelace sum of the 85 waypoints (x east, y north) is -109,330.
  Negative means clockwise; the reversed list gives +109,330.
- The loop's 952 cells against the runner's search area: 220 inside (the south edge x 20-239),
  **732 outside the 20-cell border** (section 5, row 11).

## 4. Stands

**`map_prep.py stands xmas_dun02` (the runner's own anchor), for the record:**
- the stand grid has 50,174 cells, the search area 40,327 and the route grid 50,079;
- START = `hf.area_centre(area)` = **(141,129)**. It passes the three checks. It lies in the
  maze, 11 cells from the warp span and 7 east of the zone. Its clearance is 1;
- FALLBACK (113,146), clearance 10, 262 steps away;
- the 1,515 area cells of its seeded-start box all pass.
- **This is not where the edge technique starts.** The plan's setup warps straight to an edge
  cell (rogue-xmas02.md section 1).

**The proposed stands, ON the loop** (the same checks, through `map_prep`'s own functions):

| stand | cell | waypoint | three stand-cell checks | client ∩ server | main component | in the zone | open neighbours | clearance | to the warp span | walk steps from START | joins the loop at | in the runner's search area |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **START** | **(7,21)** | 0 | pass | yes | yes | no | 8 | 1 (3 x 3) | 121 | 0 | waypoint 1 (7,33) | no (the border) |
| FALLBACK | (114,23) | 74 | pass | yes | yes | no | 8 | 5 (11 x 11) | 106 | 107 | waypoint 75 (103,23) | yes |

- START is the loop's first waypoint, the SW corner. The map's outer wall (x <= 5, y <= 13)
  limits its clearance, not a pillar.
- **FALLBACK's rule** (map_prep's, restricted to the loop): of the waypoints at least 20 cells
  (Chebyshev) from START, those with the largest clearance (5: waypoints 67, 71 and 74), then
  the nearest to START (Euclidean).
- **All 85 waypoints pass the three checks in ONE `check_warps` call.**
- **Positive cases through the same call:**

| cell | expected | result |
|---|---|---|
| (129,130), the warp centre | refused | refused: "stand (129, 130) in xmas_dun2-2 -> xmas_dun01" |
| (128,129), (130,131), the span's corners | refused | refused |
| **(131,130), the arrival** | **passes the three checks; only the zone keeps it** | passes, `in_no_enter` true |
| (132,130), two cells east | passes; in the zone | passes, `in_no_enter` true |
| (130,123), the Kafra teleport's arrival | passes; outside the zone | passes, `in_no_enter` false |
| (5,21), the outer wall | refused | refused: "the server does not let the GM stand on" |
| a touch area: prontera (45,67) | refused | refused: "in an NPC touch area" (xmas_dun02 has none) |

- **So a start table in code must check the zones as well as the three checks.** (131,130)
  passes the three checks; only the zone refuses it.

## 5. What `dungeon_hunt.py` `run()` needs per map, and what xmas_dun02 has

Read from the CURRENT runner (main at 85394ba, `VERSION = "dungeon@8.5"`). Unchanged here: the
parent edits the runner.

| # | input | where (today) | xmas_dun02 | what to do |
|---|---|---|---|---|
| 1 | the map | `--map M` (no `choices`: any name; default `orcsdun01`) | - | pass `--map xmas_dun02`; **works as is** |
| 2 | script NPCs / melee ring | `--engage melee_ring` only: `MR_MAPS = {"orcsdun01"}` and npc_cells' `npcs` empty | 0 NPCs, but not in MR_MAPS | keep the default `defend_scan` (refused under melee_ring) |
| 3 | the client GAT | `cam.GAT_DIR / "xmas_dun02.gat"` | **yes** | re-extract after a host reboot (`grf_read.py extract ... 'data\xmas_dun02.gat'`) |
| 4 | the stand grid | `anim_region.stand_grid`: route.json warps + first_workflow touch areas | **refused** with the installed KB (route.json lacks the map) | install the candidates (section 8) |
| 5 | the warp keep-away | `data/kb/warps.json` `.get(map_, [])` | absent in the installed KB -> `[]` **silently** (fails open; row 4's refusal hides it) | install the kb_build candidate WITH route.json |
| 6 | NPC keep-away, `--walk-trust`, `--npc-guard` | npc_cells.json, `complete` required | complete, 0 NPCs | works once installed |
| 7 | the zones (required) | `map_zones.load(map_)` | **yes** (section 2) | merge this branch |
| 8 | rest spots | `config/dungeon/<map>.json`, optional | none: sits where it stands | the no-rest strategies (P / P2) need none |
| 9 | White Plant areas | `plant_finder.spawn_areas` (job 1082) | none | inert |
| 10 | the patrol route | `config/routes/<map>.yaml`, `--search patrol` | **yes** (section 3); every waypoint on `okr` | pass `--search patrol` (`--walk-through` optional) |
| 11 | **the start** | `hunt.start_cell(area, seed, near=hf.area_centre(area))`; the setup types `@warp xmas_dun02 x y` | would be within 25 cells of **(141,129)**, in the maze; the area's 20-cell border (`hunt_core.search_area`, `border=20`) excludes 732 of the loop's 952 cells | **CODE:** a start on the loop, e.g. a per-map start-stand table (START (7,21), FALLBACK (114,23)), checked at run start with the three checks AND `in_no_enter`; never (131,130) |
| 12 | the search area in patrol mode | `area` is read for the start and in the heading branch only | - | no change for the patrol; a heading search on this map would never walk the edge band |
| 13 | camera + altitude | `camera_rdp.json` (outdoor), `gat.relative_altitude` | **xmas_dun02 is not in indoorrswtable.txt** (115 indoor maps; nor are xmas_dun01, orcsdun01, gef_fild10): the outdoor camera, as gef_fild10 | - |
| 14 | name-tag templates | `data/nametags/xmas_dun02/templates.npz` | none | tags are banked by default off orcsdun01; nothing matches; dungeon@8.5 does not need them |
| 15 | the Fly Wing escape / the map-change bar | `JUMP_CELLS = 20`, `FLY_*`, `POS_FLY_*` | teleport allowed (`nomemo` only) | after a wing the patrol re-joins at the nearest waypoint (`entry_index`), often from inside the maze: a longer walk back to the edge |
| 16 | **the character** | `CHARS_CONF["rogue"]`: `level_hold` 63, `max_hp` 2209, `max_sp` 341 | Base 99, AGI 99 / DEX 99 after X0 | **CODE (the parent's):** `level_hold` 99. **At 63 the setup's `level_lines` would LOWER the Base-99 Rogue to 63.** Max HP / SP from the status window after X0: the HP-rate triggers are fractions of `max_hp` |
| 17 | the MVP | `--clear-map` (dungeon@8: `@killmonster2` after the warp) | Stormy Knight + Christmas Goblins, Garm Baby | pass `--clear-map` until X4's recognizer is proven. **The MVP respawns 60-70 min after the clear**: keep runs under ~60 min, or clear again |
| 18 | the offline judge | `dungeon_judge.py row SID --map`; `CHAR_MAX_HP["rogue"]` 2146 / `CHAR_MAX_SP["rogue"]` 336 | - | the parent: the Base-99 values (2146 is already older than the runner's 2209); `TARGET_ITEMS` and the staged flag are pay_fild07's; stolen vs dropped needs X4's decoders (0x09CB / 0x0110) or the picklog |
| 19 | the box watcher | `unit_detector` v1, class-agnostic | zero-shot, unmeasured | X2 measures it |
| 20 | the econ model | `data/econ/maps.json` | **absent** (no xmas_dun02 block) | optional: `econ_model.py build xmas_dun02`; the judge's zeny columns read `econ_items` only |

**What differs from gef_fild10:**
- **No script NPC** and **one warp**, in the centre of the maze, far from the edge loop.
- **The start must be ON the loop:** the runner's centre-of-area start lands in the maze next to
  the warp's keep-out (row 11).
- **The aggressive monsters:** 35 ranged Cruisers (range 7), Garm Baby and the MVP. That is 37 of
  127 normal + MVP spawns, against 95 of 110 on gef_fild10.
- **The MVP walks 200 ms per cell** (slower than the Rogue's 150), but **its Christmas Goblins
  walk 100**.

## 6. The species' sprites (client stems, idle boxes)

    python3 scripts/npc_sprites.py mob-names 1249 1248 1246 1265 1515 1251 1607 \
      --mobs data/kb/mobs.json --out /dev/shm/poring-lab-tmp/x1/kb-sprites/monster_sprite_names.json
    python3 scripts/sprite_catalog.py --aegis mystcase cruiser cookie_xmas cookie garm_baby \
      knight_of_windstorm gobline_xmas --work /dev/shm/poring-lab-tmp/x1/sprites \
      --out /dev/shm/poring-lab-tmp/x1/kb-sprites/sprite_catalog.json --decode-mixcrypt

Run 2026-11-05 14:58 ICT from the Thai `data.grf` (NAS, read-only). Every SPR is MIXCRYPT (0x03),
decoded study-only (Batt 2026-10-05); every ACT is DES-header (0x05). 0 problems.

| species (mob id) | spawns | walk (ms / cell) | sprite stem | idle box (native px, x0 y0 x1 y1) | idle size | idle frames' bottom (y1 min / max) | flies? | idle hue / saturation / value | opaque px |
|---|---|---|---|---|---|---|---|---|---|
| Myst Case (1249) | 50 | 400 | `mystcase` | -31.5 -66.5 33.5 10.5 | 65 x 77 | -3.2 / 10.5 (it hops) | no | 4° / 0.51 / 0.74 | 3,260 |
| Cruiser (1248) | 35 | 400 | `cruiser` | -18.5 -88.5 20.5 9.5 | 39 x 98 | 9.5 / 11.5 | no | 355° / 0.42 / 0.55 | 1,649 |
| Christmas Cookie (1246) | 20 | 400 | `cookie_xmas` | -14.5 -42.5 12.5 12.5 | 27 x 55 | 12.5 | no | **3° / 0.45 / 0.72** | 1,065 |
| Cookie (1265) | 20 | 200 | `cookie` (client name `Cookie`) | -14.5 -42.5 12.5 12.5 | 27 x 55 | 12.5 | no | **44° / 0.32 / 0.63** | 1,065 |
| Garm Baby (1515) | 1 | 450 | `garm_baby` | -37 -50.2 37 9.8 | 74 x 60 | 9.8 / 10.5 | no | 267° / 0.20 / 0.79 | 2,608 |
| **Stormy Knight (1251), MVP** | 1 | 200 | `knight_of_windstorm` | **-81.5 -122.5 59.5 10.5** | **141 x 133** | 10.0 / 10.5 | no | **334° / 0.38 / 0.60** | **6,882** |
| Christmas Goblin (1607), its slave | 0 | 100 | **`gobline_xmas`** (aegis `G_GOBLINE_XMAS`) | -24 -61 18 7 | 42 x 68 | -3.0 / 7.0 (it hops) | no | 2° / 0.32 / 0.68 | 1,629 |

- **The method:** hue / saturation / value come from the rendered idle frame
  (`orc_camera_check.reference_hue`: direction 0, frame 0, the ACT tint, unlit). The bottom
  column is the idle boxes of direction 0, frame by frame.
- **No species flies.** Every idle box reaches the ground: y1 > 0 in the first frame.
  - Myst Case and the Christmas Goblin hop: some idle frames lift the box ~3 px above the anchor.
- **For a Stormy Knight recognizer (X4):**
  - **size separates it**: 141 x 133 px idle against at most 74 wide (Garm Baby) and 98 tall
    (Cruiser) for the others. Its opaque area is 2.1 x Myst Case's. Its attack envelope is
    150 x 198, its idle envelope 151.5 x 138.5;
  - **colour does not**: its hue (334°) sits beside the map's reds (Myst Case 4°, Cruiser 355°,
    Christmas Cookie 3°, Christmas Goblin 2°);
  - **it rarely walks alone**: it summons Christmas Goblins and Garm Baby.
- **Cookie vs Christmas Cookie:** the two SPRs (38,168 bytes each) differ in 153 bytes, all in
  the last 1,024 (the palette).
  - The images and the box geometry are the same; the ACTs differ.
  - So **only colour tells them apart** (hue 44° tan vs 3° red). A species detector (X5) must
    keep colour: gef10's `hsv_s` augmentation would blur exactly this.
- **Left for the parent in /dev/shm (client-derived, never committed):**
  - the SPR / ACT of all 7 stems in `/dev/shm/poring-lab-tmp/x1/sprites/data/sprite/몬스터/`;
  - the catalog and the names in `/dev/shm/poring-lab-tmp/x1/kb-sprites/` (sha256 `1dd29dc4…`
    and `c38daf75…`).
  - **These two files hold these 7 ids only. Do NOT copy them over data/kb's**: merge them, or
    the installed ones lose their species.

## 7. The X2 scoring path: what exists, what is missing

X2 (rogue-xmas02.md section 4) scores the live v1 `monster` class per species on a recording,
against packet labels, with Q1's bar (recall and precision >= 0.80 for each of the four common
species with >= 30 labels).

**What exists and works for xmas_dun02 as is:**
- **The recorder:** `record_session.py`, PNG at 1 fps in tar shards to `/home/batt/poring-lab-rec`,
  `packets.jsonl.gz` beside them.
  - `chat_window.for_sid` gives sessions from `20261105T12` on the 2026-11-05 standard chat
    window.
- **The camera and the heights:**
  - xmas_dun02 is NOT in `indoorrswtable.txt`, so it gets the fitted outdoor camera
    (`camera_rdp.json`, `camera_for_map(indoor=False)`), as gef_fild10;
  - `load_scene` reads the GAT heights from `GAT_DIR` (the GAT and the indoor table are both
    there now; both are lost on a host reboot).
- **The simple packet truth:** `mvp_watch_study.truth` / `truth_row` (map name a parameter).
  - Per recorder frame (`png_index`), each monster's `predict_sprite` box at t - 1d (OFFSET_MS
    120, K 0.14: payf07's frozen values), its Timeline state, and the in-view rule (`labels_for_v1`'s,
    the layout's UI rectangles).
  - The map change and GM-command flags are included.
  - This is what scored the live detector on Batt's gef10 demo.
- **The matching rule** (`detector_vs_packets.score_capture`), which is the gef10 POSITION rule,
  class-agnostic:
  - recall = in-view truth boxes that contain a `monster` detection's centre;
  - precision = detections whose centre lies in some monster's predicted box;
  - its breakdowns: distance bins, states, self-motion and first sight.
- **The v1 CPU model:** `unit_detector.UnitDetector` (`/dev/shm/poring-lab-detector/model/v1png-last-736x1280.onnx`).
  Its RAM environment was removed in the pause; rogue-xmas02.md says it is rebuilt from the NAS
  before X2.

**What is MISSING or must be decided before X2's recording (none built here):**
1. **A CPU predictor that saves boxes.** Nothing writes v1's per-frame CPU-ONNX boxes for a
   recorder session:
   - `eval_latency.py` runs UnitDetector over predict_dir-style refs but only COUNTS boxes;
   - `predict_dir` is the torch / GPU path (the vision worker, R1-R3);
   - `human_demo.py` logs `boxes.jsonl` live only;
   - `dungeon_hunt.BoxWatch` logs counts only.
   - Needed: a refs builder for every frame of a recorder session (`png_index` -> {key: {path,
     offset, size}}), and an eval_latency-style loop that writes predict_dir's JSON (or
     `boxes.jsonl` rows keyed by `t_mono_ns`).
   - The alternative is to log boxes live during the recording, human_demo's way: a live-side
     change.
2. **The scorer's per-map parts** (`detector_vs_packets.py score`):
   - `SPECIES` is gef_fild10's four (1273, 1023, 1031, 1686); everything else is `other`.
     xmas_dun02 needs 1249, 1248, 1246, 1265 (+ 1515, 1251, 1607 reported);
   - it reads a HUMAN-DEMO dir (manifest `t0_live_ns`, `boxes.jsonl`, `--window-s`), not a
     recorder session (PNG shards, per-frame `t_mono_ns`): it needs a recorder-session input, or
     a converter;
   - `--map` defaults to gef_fild10 (pass xmas_dun02);
   - **`mvp_watch_study.SPRITES` / `SPRITE_NAMES` are hard-wired** to
     `/dev/shm/poring-lab-tmp/gef10-prep/...`. That directory is GONE now, and it held gef10's
     species only. Point them at a merged sprite set holding the 7 stems of section 6 (or make
     them a parameter).
3. **Per-species PRECISION for a class-agnostic detector is defined nowhere:**
   - X2's bar asks for it per species;
   - the scorer pools precision;
   - Q1's definition (class-s detections) needs a species class that v1 does not have.
   - **The pre-registration needs an amendment BEFORE the recording.** For example: a detection
     counts for species s when its centre lies in an s box and in no other species' box; the
     detections that land in no box count against every species present in the frame, or are
     reported pooled.
4. **Which label rule:**
   - **(a) the gef10 method proper**, which the pre-registration names (`map_labels.py labels`,
     the o3h rule with the RSW / RSM occluders). It needs:
     - an `XMAS02` `MapSpec` (`MAPS` has pay_fild07 and gef_fild10 only): cells 260 x 260, the
       map's RSW and its models extracted from the GRF to /dev/shm, the species and walkers,
       `fit_px`, a FIT / TEST role table, the kb and sprite dirs, the label name and salt, the
       layouts;
     - a FROZEN `params.json`: 1d, **T_h re-measured on xmas_dun02's own FIT data**
       (payf07 0.479, gef_fild10 0.636: it is per map), tau, k, the fit radius, the engaged
       variant, the RSW / RSM sha256;
     - **so a FIT part on xmas_dun02, which does not exist and which the pre-registration does
       not name.** The Toy Factory has many models, so occlusion matters here;
   - **(b) the simpler truth** (`mvp_watch_study.truth_row`: no fit, no occlusion test), as the
     gef10 demo score used.
   - Write the choice into the pre-registration before the recording.
   - `eval_q1.py` (Q1's scorer) is not usable as is: it needs the blind labellers' answers, and
     X2 has none.
5. **The in-view rule's UI rectangles:** `client_layout.RECTS` (`hunt` and `standard`) still
   carry the LEGACY chat window (0,532,600,626).
   - Since 2026-11-05 the client shows the STANDARD one (6 lines, bottom 719:
     `chat_window.STANDARD`).
   - `mvp_watch_study.truth` takes `RECTS[layout]` with no override.
   - `detector_vs_packets` has `--chat-rect`, but a recorder-session path would need it too.
   - Verify on the recording's own frames.
- **Reported, deciding nothing:**
  - Hallucination: Myst Case and the MVP cast it, and its frames distort the picture. No tool
    flags them;
  - Myst Case teleports away when hit rudely: a label that ends without a death;
  - the 30-label minimum per species: at 1 fps over >= 20 min of a 127-monster map this is likely
    for the four common species. Unmeasured.

## 8. Pending, install steps, limits

**PENDING the parent (in this order):**
1. Merge this branch: `config/map_zones/xmas_dun02.yaml` and `config/routes/xmas_dun02.yaml` then
   load on the main checkout.
2. Install the KB candidates. Check the installed sha256 first (the "installed" column of
   section 1), then copy; the sha256 below are the ones verified here:

        cp /dev/shm/poring-lab-tmp/x1/kb/spawns.json /dev/shm/poring-lab-tmp/x1/kb/warps.json \
           /dev/shm/poring-lab-tmp/x1/kb/classes.json /dev/shm/poring-lab-tmp/x1/kb/kb.lock.json data/kb/
        cp /dev/shm/poring-lab-tmp/x1/kb-fw/first_workflow.json data/kb/
        cp /dev/shm/poring-lab-tmp/x1/kb-route/route.json data/kb/      # route.md is unchanged
        cp /dev/shm/poring-lab-tmp/x1/kb-fw/npc_cells.json data/kb/     # only if data/kb/npc_cells.json is still 821ced830d336b9d...

   - spawns `3337ab448d1c3a4e`, warps `ce0796df9ab36a9f`, classes `3900bced3ed5aa17`, kb.lock
     `697b1f633e04bba5`, first_workflow `b8c7fedb0dede906`, route `4178fffc470e4883`, npc_cells
     `2d029f69f05841b7`.
   - If npc_cells.json changed meanwhile, re-merge instead:
     `python3 scripts/kb_first_workflow.py npc-cells --kb data/kb/first_workflow.json --out data/kb/npc_cells.json --only xmas_dun02`.
3. Re-run on the main checkout: `map_zones.py check / prove xmas_dun02`, `map_routes.py check /
   prove xmas_dun02` and `map_prep.py stands xmas_dun02`. Expect sections 2-4's numbers.
4. The runner items of section 5 (rows 11, 16, 17, 18) and the X2 points of section 7, before X2's
   recording.

**Not done, limits:**
- **One archive** for the GAT and the sprites: the Thai `data.grf`. The exact client / server
  agreement is the evidence that its walkable cells are the lab client's.
- The START (7,21) has clearance 1: the map's outer wall is beside it. Monsters spawn on a random
  cell of the whole map, so no edge cell is safer by the spawn rule.
- No rest spot is measured: there are no xmas_dun02 packets yet.
- No live action, no GPU, nothing written to data/kb or the NAS. The KB files, the GAT and the
  sprites stay local.

## 9. Reproduce

    W=<checkout>; export PYTHONPATH=$W/scripts:$W/packages/poring_dataset/src:$W/packages/poring_env/src:$W/packages/poring_packets/src:$W/packages/poring_flow/src
    python3 scripts/kb_build.py --out /dev/shm/poring-lab-tmp/x1/kb --maps prt_fild08 iz_dun00 iz_dun01 orcsdun01 pay_fild07 gef_fild10 xmas_dun02
    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\xmas_dun02.gat' --out /dev/shm/poring-lab-tmp/gat --decode-des
    python3 scripts/map_prep.py walkability xmas_dun02
    python3 scripts/kb_first_workflow.py build --kb-dir data/kb --mapcache-dir packages/poring_dataset/src/poring_dataset/_generated --also prt_church prt_fild08 iz_dun00 prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 gef_fild10 xmas_dun02 --out /dev/shm/poring-lab-tmp/x1/kb-fw/first_workflow.json
    cp data/kb/npc_cells.json /dev/shm/poring-lab-tmp/x1/kb-fw/npc_cells.json
    python3 scripts/kb_first_workflow.py npc-cells --kb /dev/shm/poring-lab-tmp/x1/kb-fw/first_workflow.json --out /dev/shm/poring-lab-tmp/x1/kb-fw/npc_cells.json --only xmas_dun02
    python3 scripts/kb_route.py --out /dev/shm/poring-lab-tmp/x1/kb-route --first-workflow /dev/shm/poring-lab-tmp/x1/kb-fw/first_workflow.json
    # sections 2-4 need the candidates in data/kb (here: the tmpfs worktree's own copy of data/kb)
    python3 scripts/map_zones.py check xmas_dun02 && python3 scripts/map_zones.py prove xmas_dun02 --samples 400
    python3 scripts/orc_dungeon_prep.py zone-clicks --map xmas_dun02 --samples 400 --seed 0
    python3 scripts/map_routes.py check xmas_dun02 && python3 scripts/map_routes.py prove xmas_dun02
    python3 scripts/map_prep.py stands xmas_dun02     # the runner's own centre anchor; the loop stands: section 4
    python3 scripts/npc_sprites.py mob-names 1249 1248 1246 1265 1515 1251 1607 --mobs data/kb/mobs.json --out /dev/shm/poring-lab-tmp/x1/kb-sprites/monster_sprite_names.json
    python3 scripts/sprite_catalog.py --aegis mystcase cruiser cookie_xmas cookie garm_baby knight_of_windstorm gobline_xmas --work /dev/shm/poring-lab-tmp/x1/sprites --out /dev/shm/poring-lab-tmp/x1/kb-sprites/sprite_catalog.json --decode-mixcrypt

- **The per-leg path check and the on-loop stands** (sections 3-4) were scratch scripts on
  `map_routes.leg_path` / `seg_dist` and on `map_prep.stand_check` / `_stand` / `clearance`.
  They were not committed. The committed tests pin the pure parts:
  - `test_map_routes.py`: the corners in order, clockwise, straight legs <= 12 cells, the 952-cell
    lap, no waypoint in the zone;
  - `test_map_prep.py`: the span + 4 exactly, the arrival inside, the stands outside.
