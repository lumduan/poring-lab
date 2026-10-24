---
doc_type: research
hypothesis: "Before the Thief's first walk-and-hit run on pay_fild07, the offline map prep that orcsdun01 had (client GAT, client / server walkability, script-NPC cells, no-enter zones around the warps, a start stand, the runner's map inputs) can be produced for pay_fild07 from the local sources alone, with no live action."
status: "MEASURED offline 2026-10-24 10:06-10:33 ICT (from `date`; no client, no GPU, no input). The zones file is a DRAFT that the loader REFUSES: PENDING Batt's delegation (section 4). The rebuilt first_workflow.json is a candidate in /dev/shm, not installed (section 3)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [thief-payon.md, orcsdun01-dungeon-prep.md, ../../config/map_zones/README.md, ../../config/map_zones/pay_fild07.yaml, ../../scripts/map_prep.py, ../../scripts/dungeon_hunt.py]
next_action: "Batt: review config/map_zones/pay_fild07.yaml or delegate it (section 4). The parent: install the rebuilt first_workflow.json (section 3; the runner's stand grid refuses pay_fild07 without it), then parametrise dungeon_hunt.py by map and character using section 6's list."
title: "pay_fild07 prep for the Thief: client GAT, walkability, NPC cells, warp zones (draft), stands, the runner's map inputs"
date: 2026-10-24
owner: Batt
---

# pay_fild07 prep for the Thief's walk-and-hit runs

**The brief** (the parent session, 2026-10-24 ~10:05 ICT; [thief-payon.md](thief-payon.md)
section 5). Do the offline prep that [orcsdun01-dungeon-prep.md](orcsdun01-dungeon-prep.md) did
for the dungeon, now for pay_fild07:
- the client GAT;
- the client / server walkability agreement;
- the script-NPC cells;
- a DRAFT zones file around the 4 warp spans;
- start stands;
- what `scripts/dungeon_hunt.py` `run()` needs for a map other than orcsdun01.

Offline only: no client, no GPU, no live input. pay_fild08 and pay_fild09 get the GAT,
walkability and NPC cells too, for comparison.

**The zones are NOT approved.** The agent may approve a zones file only under a person's recorded
delegation (config/map_zones/README.md). Batt has not delegated pay_fild07. So the committed file
is a draft that the loader refuses on purpose. Its geometry was proved on a test-reviewer COPY in
/dev/shm, which is never committed.

## 0. Bottom line

1. **Client GAT:** pay_fild07, pay_fild08 and pay_fild09 are extracted to the camera's GAT_DIR
   (`/dev/shm/poring-lab-tmp/gat/data`). pay_fild07 is 400 x 400 cells (section 1).
2. **Walkability: client and server agree exactly on all three maps** (section 2).
   - pay_fild07: 72,069 walkable cells on each side, 0 disagreements either way.
   - It forms ONE connected component of 72,069 cells, with or without the corner rule.
3. **Script NPCs** (section 3):
   - pay_fild07: **none**. The list is complete, every file the server loads.
   - pay_fild09: none.
   - pay_fild08: one drawn dialog NPC at (218,283). It has no touch area.
   - The three blocks were merged into `data/kb/npc_cells.json` by the generator's new `--only`
     option. The other 35 maps' blocks are unchanged.
   - **The runner still refuses pay_fild07** until the rebuilt `first_workflow.json` is
     installed. That file is a candidate in /dev/shm; the brief keeps data/kb read-only apart from
     npc_cells.
4. **Zones** (section 4): `config/map_zones/pay_fild07.yaml` is a DRAFT. It has 4 no-enter areas,
   each a warp span grown by 4 cells.
   - `map_zones.py check pay_fild07` **refuses it** (exit 1, `no reviewed_by`).
   - On the test-reviewer copy:
     - the areas take 248 walkable cells (61 / 61 / 56 / 70);
     - **nothing is sealed off** and 0 cells become unreachable;
     - 0.34 % of the spawn cells fall in the zones;
     - every sampled click into each area and onto each warp span is refused (400 / 400 each).
   - Each warp's arrival cell from the neighbouring map lies inside its area.
5. **Stands** (section 5): **START (198,202)** and **FALLBACK (198,182)**.
   - Both pass the three stand-cell checks.
   - Both lie in the main component, outside the draft zones, with all 8 neighbours open.
   - START is the runner's own anchor (`area_centre`). All 2,544 cells of the seeded-start box
     around it pass too.
6. **Runner inputs** (section 6): pay_fild07 has its GAT, warps, NPC cells and a start.
   - **It lacks:**
     - an installed first_workflow.json (the touch areas);
     - a loadable zones file (Batt's review);
     - a rest-spot file (needs banked pay_fild07 packets);
     - a `--map` parameter in dungeon_hunt.py itself.
   - **Two conflicts for the Thief that are not map files:**
     - `clear_etc` drops the WHOLE Etc tab at 40 % weight, and Rough Oridecon / Rough Elunium are
       Etc items;
     - the Auto Guard recast presses F3, which is Steal on the Thief's hotbar plan.

## 1. The client GAT (run-time, /dev/shm only)

    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf \
      'data\pay_fild07.gat' 'data\pay_fild08.gat' 'data\pay_fild09.gat' \
      --out /dev/shm/poring-lab-tmp/gat --decode-des

Run 2026-10-24 10:06 ICT. The archive is read in place, read-only, on the NAS mount. The GATs are
DES-flagged entries (0x05), decoded by our header-DES; zlib and the table's size verified each.

| map | bytes | cells (w x h) | sha256 (first 16) |
|---|---|---|---|
| pay_fild07 | 3,200,014 | 400 x 400 | 6172b390fd412b91 |
| pay_fild08 | 2,240,014 | 280 x 400 | 4bdda34607caf51a |
| pay_fild09 | 3,200,014 | 400 x 400 | 344aa7cf94534bf9 |

- They live in `/dev/shm/poring-lab-tmp/gat/data` (the runner reads `camera.GAT_DIR`). They are
  client data: never committed, and gone after a host reboot (re-run the command above).
- The RSWs (`pay_fild0N.rsw`) are MIXCRYPT (0x03). They were not extracted: the runner does not
  read them; only the occlusion test of orcsdun01-detector.md did.
- **Caveat: one archive.** This is the host's only client GRF, the Thai `data.grf`. The lab client
  draws from the kRO `data.grf` on the Dell. The exact agreement with the server's map cache
  (section 2) is the evidence that the walkable cells are the same ones.

## 2. Client / server walkability (`poring_dataset.walkable`)

    python3 scripts/map_prep.py walkability pay_fild07 pay_fild08 pay_fild09

`walkable.agreement` counts on the two grids' overlap, excluding the server's last row and column
(always NOPASS on the server). The components are those of client ∩ server, 8-connected, with
rAthena's no-corner-cutting rule and without it.

| map | client walkable | server walkable | client only | server only | both | client-walkable on the server's edge | components (both rules) |
|---|---|---|---|---|---|---|---|
| **pay_fild07** | 72,069 | 72,069 | **0** | **0** | 72,069 | 799 | **1 of 72,069** |
| pay_fild08 | 43,871 | 43,871 | 0 | 0 | 43,871 | 679 | 1 of 43,871 |
| pay_fild09 | 64,319 | 64,319 | 0 | 0 | 64,319 | 0 | 1 of 64,319 |

- The sizes match on every map (400 x 400, 280 x 400, 400 x 400).
- The "edge" cells are walkable in the GAT on the server's last row and column. A walk never uses
  them: they are not in `both`.
- **The main walkable component is the whole walkable map.** pay_fild07 is a forest with
  corridors (45 % of its cells are walkable), with no island.
- `data/kb/map_agreement.json` (L3 `map.walkability`) does not list these maps yet. Its builder
  (`map_agreement.py build`) writes the KB, which was read-only for this task. No runner reads it.

## 3. Script-NPC cells (L3)

**Why the generator could not run directly.** `kb_first_workflow.py npc-cells` writes
npc_cells.json from `data/kb/first_workflow.json`. That file covers 35 maps, and pay_fild07 is not
among them. So the first step is a rebuild of the KB with the three maps added, written to
/dev/shm:

    python3 scripts/kb_first_workflow.py build --kb-dir data/kb \
      --mapcache-dir packages/poring_dataset/src/poring_dataset/_generated \
      --also prt_church prt_fild08 iz_dun00 prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 \
      --out /dev/shm/poring-lab-tmp/payf07-prep/kb/first_workflow.json

The build ran at 2026-10-24 10:31:01 ICT (`built_at`). The first build, at 10:11:48, recorded an
absolute `--kb-dir` path and was superseded.
- It parses the map-server's own load list, `npc/pre-re/scripts_main.conf`: 522 files, 0 problems.
- It holds 38 maps.
- sha256 `7940d6e8c2d200ffa852825deba37990ee0c7bbe60651da267ead9ad49ddb9d3`.

**Diff against the installed file** (sha256 first 16 `99c809c397101600`, 35 maps):
- **34 maps are identical.**
- The 3 Payon fields are added.
- `orcsdun01` gains `kill_math` and its completeness counts. The installed file carried its
  block without them: it was evidently added outside a full build. Its warps, spawns, NPCs and
  mapflags are unchanged.
- `scope.also` / `scope.maps` list the new maps; `built_at` and `seconds` differ. Nothing else
  changed: `requirements`, `clone_groups` and the other maps' completeness are the same.

**The NPC cells: three blocks merged by the generator's own code.** `npc-cells` gained `--only MAP
...` (`merge_npc_cells`, tested).
- It adds or replaces just those maps' blocks in the existing file.
- Every other block, its banked `packet_check` included, and the header stay exactly as they were.
- The merge is recorded under a top-level `merged` list: the maps, the build's time and its ref.
- It refuses a different rAthena ref, or a map the fresh build lacks.
- A whole-file rewrite would have dropped the 33 banked `packet_check` blocks. That is why the
  plain command was not used.

      python3 scripts/kb_first_workflow.py npc-cells \
        --kb /dev/shm/poring-lab-tmp/payf07-prep/kb/first_workflow.json \
        --out data/kb/npc_cells.json --only pay_fild07 pay_fild08 pay_fild09

Run at 10:31 ICT on the main checkout's `data/kb/npc_cells.json`.
- Before: sha256 first 16 `47bfe81cfa026727`, 35 maps.
- After: sha256 first 16 `82f383b0b41676b4`, 38 maps.
- Verified: all 35 old blocks and the header are identical.
- A first merge at 10:25, from the superseded 10:11 build, was restored from its backup and redone
  once, so the file carries ONE `merged` record.

| map | complete | script NPCs | drawn | touch areas (L3) | notes |
|---|---|---|---|---|---|
| **pay_fild07** | yes | **0** | - | **none** | its files: the night mapflag, the pre-re field spawns, the field warps; 1 mapflag (nightenabled) |
| pay_fild08 | yes | 1 | yes | none | `npc/quests/doomed_swords.txt:257` at **(218,283)**, sprite 89, a dialog NPC, facing 2, no trigger span |
| pay_fild09 | yes | 0 | - | none | |

- "Complete" means the server loads the map and every file line naming it was classified, and no
  script places anything on it at run time (`map_complete`).
- pay_fild07's 4 warps are `warp` lines, drawn as portals (section 4). Its spawns are the KB's:
  Elder Willow 70, Eggyra 40, Bigfoot 30, Poporing 20, Willow 20, all whole-map random, and Green
  Plant 8 in a fixed area (171,331) ± 20.
- `npc_noclick.load_l3_npcs("pay_fild07")` reports complete, with 0 NPCs from npc_cells.json,
  route.json and the bindings.

**Still needed: install the rebuilt first_workflow.json.** `npc_click_test.load_touch_areas`, and
so `check_warps` and `anim_region.stand_grid`, read the touch areas from first_workflow.json.
Against the installed KB they return None for pay_fild07, so these refuse: "L3 does not cover
pay_fild07's NPC touch areas (refused)". Installing it is the parent's step:

    cp /dev/shm/poring-lab-tmp/payf07-prep/kb/first_workflow.json data/kb/first_workflow.json

It is the 10:31 candidate, kept in /dev/shm for this purpose. Re-running the build command above
reproduces it, with a new `built_at`. Every number in sections 4-5 was computed on a worktree copy
of data/kb carrying that candidate.

## 4. The zones DRAFT (`config/map_zones/pay_fild07.yaml`)

**The file.** Four `no_enter` areas, each a warp span from `data/kb/warps.json` (touch area =
centre ± span) grown by **4 cells** on every side, as orcsdun01.yaml explains.
- A click made while the GM moves can resolve up to ~3 cells further along its walk than the aimed
  cell (frames lag the server ~0.5 s). The + 1 keeps a destination just outside an area >= 1 cell
  short of the span.
- **`reviewed_by: ""` and `reviewed: null`, and no `delegation:`.** The intended delegation lines
  sit in the file's comment as a placeholder: "PENDING Batt's delegation".
- The 4 areas cover 940 cells in all.

| item | warp | span (touch area) | area | walkable cells taken | walkable span cells | arrival from the neighbour |
|---|---|---|---|---|---|---|
| `warp-pay_fild01` | payf03-1 (16,200) -> pay_fild01 | 3,3: x 13-19 y 197-203 | x 9-23 y 193-207 | 61 | 16 | (23,207): inside, the corner |
| `warp-pay_fild03` | payf08-1 (163,17) -> pay_fild03 | 5,2: x 158-168 y 15-19 | x 154-172 y 11-23 | 61 | 25 | (167,20): inside |
| `warp-pay_fild08` | payf11 (280,382) -> pay_fild08 | 4,2: x 276-284 y 380-384 | x 272-288 y 376-388 | 56 | 24 | (280,379): inside |
| `warp-pay_fild10` | payf12 (382,290) -> pay_fild10 | 2,5: x 380-384 y 285-295 | x 376-388 y 281-299 | 70 | 30 | (379,290): inside |

**The loader refuses the draft** (2026-10-24 10:17 ICT):

    $ python3 scripts/map_zones.py check pay_fild07
    {"ok": false, "error": ".../config/map_zones/pay_fild07.yaml: no reviewed_by: a zones file
     names the PERSON who reviewed it (the agent never approves zones)"}       (exit 1)

`map_zones.py prove pay_fild07` refuses too: a ZoneError, exit 1. So does every runner that loads
zones on pay_fild07, before any input:
- `dungeon_hunt.py` requires the file (`dungeon@1 refused: map zones: ...`);
- `hunt_flow.py` v52+ loads it.
- The review check runs before the geometry check, so `check` on the draft does not validate the
  polygons. The test-reviewer copy below does.

**The geometry proof on a test-reviewer COPY.** The copy is
`/dev/shm/poring-lab-tmp/payf07-prep/zones-test/pay_fild07.yaml`: the same bytes with
`reviewed_by: "geometry-proof-only (payf07-prep, never committed)"` and `reviewed: 2026-10-24`,
sha256 `f392c428…14bcd8aa`. It was never committed and was deleted after the proof.

- `check --root <copy>`: ok. no_cross 0 cells, no_enter 940 cells, walkable taken
  61 / 61 / 56 / 70 = 248.
- `prove pay_fild07 --root <copy> --samples 400` (10:18 ICT; re-run identical at ~10:32 on the
  final KB):

| grid | walkable | zone cells | pieces cut off (no corner rule / corner rule) | main component before -> after | newly unreachable | spawn cells in zones / in cut pieces |
|---|---|---|---|---|---|---|
| client ∩ server | 72,069 | 248 | 0 / 0 | 72,069 -> 71,821 | **0** | 248 of 72,069 (0.34 %) / 0 |
| the runner's stand grid | 71,974 | 153 | 0 / 0 | 71,974 -> 71,821 | **0** | (same) |
| the runner's search area | 71,555 | 0 | 0 | 71,555 -> 71,555 | | it already keeps warps 10 cells off, and 20 off the map edge |

- **No area seals off any walkable cell.** There are no cut pieces under either connectivity, 0
  cells become unreachable, and the main component loses exactly the 248 zone cells.
- The stand grid is 95 cells smaller than client ∩ server: these are the walkable cells of the
  four warp spans (16 + 25 + 24 + 30).

`prove` samples clicks only into CUT pieces, and there are none. So the clicks were sampled per
AREA, with `orc_dungeon_prep.py zone-clicks`, now generalised with `--map` / `--root` and tested.
- The orcsdun01 numbers reproduce exactly after the change: 400 / 400 twice, and 0 / 400 and
  13 / 400 for outside -> outside.
- Run: `--map pay_fild07 --root <copy> --samples 400 --seed 0`, through `map_zones.walk_why`, the
  runner's gate.

| area | walkable inside | span cells | clicks INTO it refused | clicks ONTO its warp span refused | outside -> outside clicks refused (over-reach, not a leak) |
|---|---|---|---|---|---|
| `warp-pay_fild01` | 61 | 16 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 8 / 400 |
| `warp-pay_fild03` | 61 | 25 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 21 / 400 |
| `warp-pay_fild08` | 56 | 24 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 0 / 400 |
| `warp-pay_fild10` | 70 | 30 | **400 / 400** (`dest_no_enter`) | **400 / 400** | 0 / 400 |

**What Batt's decision changes.** To make the file valid, a person sets `reviewed_by` and
`reviewed`:
- Batt himself: `reviewed_by: batt`;
- or under his recorded delegation: `reviewed_by: "agent (delegated by batt, YYYY-MM-DD)"` plus a
  `delegation:` line citing his words (the placeholder is in the file's comment).

The geometry stays as proved. Its sha256 then changes, and a run records the new one in its
`map_zones` event.

## 5. Stand cells (`scripts/map_prep.py stands`)

    python3 scripts/map_prep.py stands pay_fild07 --root /dev/shm/poring-lab-tmp/payf07-prep/zones-test

The search area is built exactly as `dungeon_hunt.run()` builds it (`map_prep.runner_area`):
1. `anim_region.stand_grid`;
2. `hunt_core.search_area`, keeping each warp span 10 cells off;
3. `map_zones.apply`;
4. minus what the zones seal off;
5. the largest 8-connected component.

The stand grid then has 71,974 cells, the area 71,555 and the route grid 71,821.
- **START** = `hunt_flow.area_centre(area)`. It is the anchor `hunt.start_cell` draws the run's
  seeded start near (within 25 cells).
- **FALLBACK** = the area cell nearest START whose whole 21 x 21 square is walkable on client AND
  server (clearance >= 10), at least 20 cells (Chebyshev) from START. It is a second, wide-open
  stand somewhere else.

| stand | cell | three stand-cell checks | client ∩ server | main component | in a draft zone | open neighbours | clearance (radius of its all-walkable square) | to the nearest warp span (Chebyshev) | walk steps from START |
|---|---|---|---|---|---|---|---|---|---|
| **START** | **(198,202)** | pass | yes | yes | no | 8 | 6 (13 x 13) | 178 | 0 |
| **FALLBACK** | **(198,182)** | pass | yes | yes | no | 8 | 11 (23 x 23) | 163 | 20 |
| the seeded-start box | 2,544 area cells within 25 of START | **all pass** (one check_warps call) | yes | yes | no | | | | |

- **The three checks** (`npc_click_test.check_warps` on a stand-only plan):
  - outside every warp span (route.json's 4);
  - outside every script-NPC touch area (first_workflow.json: none on pay_fild07);
  - standable on the SERVER map cache.
- **Positive cases, through the same call:**

| cell | expected | result |
|---|---|---|
| (16,200), a warp centre | refused | refused: "stand (16, 200) in payf03-1 -> pay_fild01" |
| (19,203), a span corner | refused | refused |
| (20,203), one cell outside the span | passes | passes |
| (164,150), a server-NOPASS cell | refused | refused: "the server does not let the GM stand on" |
| a touch area: prontera (45,67) | refused | refused: "in an NPC touch area" (pay_fild07 has none to test) |

- `in_no_enter` on the copy is True for the 4 arrival cells and False for (24,207), START and
  FALLBACK.
- The seeds the runner would use: seed 1 -> (181,213), 2 -> (176,182), 3 -> (188,214),
  20261024 -> (210,188). These are illustrative: the start cell is drawn per run.
- **The Crusader's `CLEAR_STAND` is off this map:** ("prt_fild08", 268, 107), the open-field stand
  where `clear_etc` drops the Etc tab. It needs no pay_fild07 cell, but see section 6, item 12,
  before it is used for the Thief.

## 6. What `dungeon_hunt.py` `run()` needs per map, and what pay_fild07 has

This is read from `run()` (lines ~630-830) and the constants it uses. The runner itself is
unchanged here: parametrising it is the parent's step.

| # | input | where (today) | pay_fild07 | what to do |
|---|---|---|---|---|
| 1 | the map | `MAP = "orcsdun01"` (module constant) | - | a `--map` parameter (the parent) |
| 2 | the melee-ring allowlist + 0 script NPCs | `MR_MAPS = {"orcsdun01"}`; `npc_cells.json["maps"].get(MAP, {}).get("npcs", [])` must be empty | npc_cells: complete, 0 NPCs (section 3) | add pay_fild07 to MR_MAPS if melee_ring is used. Note: `.get(MAP, {})` passes a map ABSENT from the file (0 NPCs by default); requiring `MAP in maps` and `complete` would fail closed |
| 3 | the client GAT | `cam.GAT_DIR / f"{MAP}.gat"` | **yes** (section 1) | re-extract after a host reboot |
| 4 | the stand grid | `anim_region.stand_grid(MAP, gat)`: route.json warps + first_workflow.json touch areas + both sources | warps yes; **touch areas NO in the installed KB** (refused) | install the rebuilt first_workflow.json (section 3) |
| 5 | the warps (search-area keep-away) | `data/kb/warps.json[MAP]` | **yes**, 4 | - |
| 6 | the zones (REQUIRED by the runner) | `map_zones.load(MAP)`; no file -> "refused: no config/map_zones/orcsdun01.yaml" (the text names orcsdun01) | **draft, REFUSED** (section 4) | Batt reviews or delegates |
| 7 | rest spots (strategy B / H) | `REST_FILE = config/dungeon/orcsdun01.json` (hard-coded path); each spot must be on the route grid | **none** | the orcsdun01 method (`orc_dungeon_prep.py rest-spots`) needs banked pay_fild07 packets (warp-and-watch dwells): none exist yet. Until then a geometry-only prior is possible (`static_reach`), or no rest |
| 8 | White Plant sweep areas | `plant_finder.spawn_areas(MAP)` (job 1082) | none (pay_fild07 has no White Plant; Green Plant 1080 at (171,331) ± 20) | inert; `--plant-sweep` is off by decision 6 anyway |
| 9 | the patrol route (`--search patrol` only) | `config/routes/<map>.yaml` | none | the heading search (the default) needs none |
| 10 | the start | `hunt.start_cell(area, seed, near=hf.area_centre(area))` | **(198,202)** anchor; the box passes (section 5) | - |
| 11 | camera + altitude | `camera_rdp.json` (map-agnostic), `gat.relative_altitude` | yes (the GAT) | - |
| 12 | the Etc drop (setup and run) | `CLEAR_AT = 0.40` -> `clear_etc` drops the WHOLE Etc tab on `CLEAR_STAND` (prt_fild08) | - | **conflict:** Rough Oridecon 756 and Rough Elunium 757 are type Etc (weight 200 each; data/kb items.json). Dead Branch 604 is Usable and Honey 518 is Healing. Dropping the Etc tab would drop two of Batt's four target items |
| 13 | the offline judge | `dungeon_judge.py row SID --map` (has a --map option); `MAX_HP, MAX_SP = 5260, 312` | - | the Thief's own max HP / SP |

**Character inputs, not map ones.** They must change for the Thief all the same:
- `cr.check(screen, "crusader")` and `data/crusader/char.json` (the identity, the DB queries).
- `MAX_HP = 5260`.
- `SELF_PX` / `SELF_BOX`: the drawn Crusader's body.
- `POTIONS_TO, WINGS_TO = 40, 15`: strategy B tops up to 40 White Potions = 600 weight, 25 % of the
  Thief's 2,430 cap. thief-payon.md carries 10.
- **The Auto Guard recast presses `KEYS["autoguard"] = "F3"`, but F3 is Steal on the Thief's
  hotbar plan** (thief-payon.md section 4, step 8). thief-payon.md section 6 already turns the
  Crusader-only parts off; this is the concrete key collision to guard.

**Species parameters measured on orcs.** They are not map files:
- `ARROW_UP = 150`, the lock-arrow band above the target;
- `BODY_UP = 26`, the hover point above a monster's cell.

Elder Willow and Willow are tree sprites, and Bigfoot is large, so both may need a measurement on
pay_fild07 frames.

**The DEFEND-SCAN premise is weaker here.** It is the KB's `kill_math`: only Elder Willow (ai 09)
of the six species is aggressive, 70 of 188 monsters (37 %).
- Eggyra and Bigfoot (ai 17), Willow (01), Poporing (02, a looter) and Green Plant (06) do not
  come to the character.
- Most fights must start from the walk's own SWORD reads or the boxes, not from a hit on us.
- v1's zero-shot recall on these species is unmeasured: there are no pay_fild07 recordings yet.

**Not runner inputs but in thief-payon.md section 5's list:**
- the hunt lint's melee-ring checks (`poring_flow/lint/hunt.py`). There is no map allowlist there:
  `melee_ring_species` needs every species on the map, from the sheet, to be a TARGET of the map
  block. The KB's classes for pay_fild07 are the 6 spawned species, with no metamorphosis
  (`kb_build.classes_for`). So a map block listing all six passes;
- the name tags (`nametag.py`), cut live.

## 7. Pending, not done, limits

- **PENDING Batt:** review or delegate `config/map_zones/pay_fild07.yaml`. Until then every run on
  pay_fild07 that loads zones refuses before input. That is by design.
- **PENDING the parent:**
  - install the rebuilt first_workflow.json (section 3);
  - parametrise dungeon_hunt.py (section 6: map, rest file, the Etc drop, the F3 collision, the
    character constants);
  - optionally run `map_agreement.py build` and `kb_bindings` for the L3 walkability record.
- **No rest spots:** the method needs banked pay_fild07 packets.
- **One archive** for the GAT: the Thai `data.grf`, not the lab client's kRO one (section 1). The
  exact server agreement makes a layout difference unlikely, not impossible.
- `map_zones.py prove` on a refused file raises a traceback (exit 1), not `check`'s JSON error.
  It fails closed either way; left as it is.
- No live action, no GPU, nothing written to the NAS. Only cells and counts are quoted here; the
  KB files and the GATs stay local.

## 8. Reproduce

    W=<checkout>; export PYTHONPATH=$W/scripts:$W/packages/poring_dataset/src:$W/packages/poring_env/src:$W/packages/poring_packets/src:$W/packages/poring_flow/src
    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\pay_fild07.gat' 'data\pay_fild08.gat' 'data\pay_fild09.gat' --out /dev/shm/poring-lab-tmp/gat --decode-des
    python3 scripts/map_prep.py walkability pay_fild07 pay_fild08 pay_fild09
    python3 scripts/kb_first_workflow.py build --kb-dir data/kb --mapcache-dir packages/poring_dataset/src/poring_dataset/_generated --also prt_church prt_fild08 iz_dun00 prt_fild06 orcsdun01 pay_fild07 pay_fild08 pay_fild09 --out /dev/shm/poring-lab-tmp/payf07-prep/kb/first_workflow.json
    python3 scripts/kb_first_workflow.py npc-cells --kb /dev/shm/poring-lab-tmp/payf07-prep/kb/first_workflow.json --out data/kb/npc_cells.json --only pay_fild07 pay_fild08 pay_fild09
    python3 scripts/map_zones.py check pay_fild07                      # refused (exit 1)
    # a test-reviewer copy, OUTSIDE the repo:
    Z=/dev/shm/poring-lab-tmp/payf07-prep/zones-test; mkdir -p $Z
    sed -e 's/^reviewed_by: ""$/reviewed_by: "geometry-proof-only (payf07-prep, never committed)"/' -e 's/^reviewed: null$/reviewed: 2026-10-24/' config/map_zones/pay_fild07.yaml > $Z/pay_fild07.yaml
    python3 scripts/map_zones.py check pay_fild07 --root $Z && python3 scripts/map_zones.py prove pay_fild07 --root $Z --samples 400
    python3 scripts/orc_dungeon_prep.py zone-clicks --map pay_fild07 --root $Z --samples 400 --seed 0
    python3 scripts/map_prep.py stands pay_fild07 --root $Z            # needs the rebuilt first_workflow.json in data/kb

The sections 4-5 numbers need the rebuilt first_workflow.json in `data/kb` (section 3). Against
the installed KB, `stand_grid` and `check_warps` refuse pay_fild07.
