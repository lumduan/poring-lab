---
doc_type: design
hypothesis: "On gef_fild10, resting INSIDE a sealed orc house (in_orcs01) instead of sitting in the field removes the damage the bot takes while it sits and right after it stands (26 % of all its damage in the 8.x runs), so the sitting it needs falls and kills / h rise, while no click, walk or bug can reach the Orc Dungeon warps, because the three rooms used hold no warp but their own exit."
status: "PROPOSED (offline; not live)"
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [rogue-gef10.md, gef10-time-budget.md, gef10-cursor-unknown.md, gef10-prep.md, ../../scripts/house_rest.py, ../../scripts/dungeon_hunt.py, ../../scripts/dungeon_judge.py, ../../config/map_zones/gef_fild10.yaml, ../../config/routes/gef_fild10.yaml, ../../services/backend/tests/test_house_rest.py]
next_action: "The parent: run the live checks of section 8 (unscored, supervised) before any scored run, then pre-register --rest house (section 9) as ONE change against the version current then. Batt: decide whether his own door (gef022) may be used although its room holds the orcsdun01 warp (section 3; this design refuses it)."
title: "gef_fild10: rest inside a sealed orc house (--rest house), design, safety and estimate"
date: 2026-10-26
owner: Batt
---

# gef_fild10: rest inside a sealed orc house (`--rest house`)

**Why.** The bot sits to rest for about 42 % of its time on gef_fild10, and rest is 50 % of its
gap to Batt ([gef10-time-budget.md](gef10-time-budget.md) section 5). The rest is driven by
damage, and part of that damage lands while it sits in the field or scans right after standing
up. In his demo (2026-10-26, 10:05:59) Batt walked into an orc house and sat there: "I rest on
this map because it is safer". This document designs the same move for the runner.

**What this is.** A design, the pure planning code (`scripts/house_rest.py`), its integration in
`scripts/dungeon_hunt.py` behind `--rest house` (default `spot` = today's behaviour), the judge's
hook, 23 tests, and an estimate. **Nothing ran live.** Every number is **measured** unless it is
marked **estimate**.

## 0. The answer in brief

1. **Three of the five houses are SEALED rooms.** On the interior's walkable grid (client GAT
   and the server's map cache agree exactly: 2,686 cells), the rooms behind gef018, gef019 and
   gef020 hold only their own exit warp. The other two rooms hold a dungeon warp **24 steps**
   from the arrival:
   - gef021's room: orc02 -> orcsdun02;
   - gef022's room (**Batt's door**): orc01 -> orcsdun01.
   The runner uses **only the sealed three**. In them, no click, no client detour and no bug of
   ours can reach a dungeon warp: nothing walkable leads there.
2. **Inside, the runner does not walk.** It sits at once on the arrival cell, rests, stands, and
   makes ONE click on the room's own exit, 2 cells away. The click cell is the exit's centre, so a
   1-cell error in any direction still lands on the exit.
3. **Map changes are read from pixels**, never packets. Batt's own door step is the positive case:
   Basic Info unreadable for 3.4 s (the loading screen, then one black frame), then Basic Info
   back with **no minimap readout** and a **dark** frame (mean 26-39 against the field's
   97-112).
4. **Every step is a row of a closed transition table** (`house_rest.Trip`). Any other event in a
   state stops the run.
5. **The estimate is modest: about +3 to +5 kills / h** at the 8.x level (45.7 kills / h in the 7
   allowed runs). The ceiling, if every rest moved indoors at no cost, is +11.7.
   - Most of the sitting pays for damage taken in FIGHTS, not while resting.
   - Only 27 of the 47 rest decisions qualify (HP >= 30 %, a sealed door <= 120 steps).
   - The walk to a sealed door is long: a median of 77 route steps.
   - **Rest indoors does not close the gap to Batt on its own.** It removes the exposure around
     the rest. The damage per kill is the larger lever.

## 1. What was read

- **L3:** `data/kb/warps.json` (generated locally from the pinned rAthena tree, never committed).
- **The rAthena mirror** `/dev/shm/poring-lab-rathena-src` (pinned, read-only):
  - the warps: `npc/pre-re/warps/fields/geffen_fild.txt`, `npc/warps/dungeons/orcsdun.txt`;
  - the in_orcs01 NPCs: `npc/quests/newgears/2004_headgears.txt`, `2008_headgears.txt` (both in
    `scripts_athena.conf`, loaded by the pre-renewal server);
  - the mapflags: `npc/mapflag/noteleport.txt:34` (`in_orcs01 noteleport`, loaded by
    `scripts_mapflags.conf`);
  - no monster spawn line names in_orcs01.
- **The client GAT of in_orcs01**, extracted 2026-10-26 12:51 into
  `/dev/shm/poring-lab-tmp/gat/data/in_orcs01.gat` (800,014 bytes, sha256 `c299917c5f1fe4fc...`;
  client data, never committed), with the same command as gef10-prep.md section 2.
  - It agrees with the server's map cache cell for cell: 2,686 walkable on both sides, 0 on one
    side only.
  - The client's `indoorrswtable.txt` lists in_orcs01: it is an **indoor** map (the camera turned
    by ~46 degrees and closer).
- **Batt's demo** `20261026T095021-demo-human-demo-gef10`: its packets (the door step and his
  rest) and **85 of its frames** (5 Hz, read in place on the NAS: -3 s .. +14 s around his map
  change). Nothing of them is copied.
- **The bot's runs**, 7 runs, 4.20 h: a2, a3, a4, a7, a8, a5b (dungeon@8.x) and b1 (dungeon@8.3).
  Their events and packets in /dev/shm.
  - a9, a10, a11 and w3 are the detector's TEST2 recordings: **not read** (the time budget's 8-run
    pool used a9 and a11, so its numbers differ slightly from this pool).
  - c1 and c2 (today) and a1 / a6 were not used for the estimate.

## 2. The five houses

Spans are rAthena's: the warp cell plus or minus the span (map_zones' convention). "Steps" are
8-connected walking steps on in_orcs01's walkable grid, with rAthena's corner rule; the
no-corner-rule superset gives the same numbers.

| door (field) | door cell | arrival (in_orcs01) | exit warp | exit span (x / y) | exit click cell | click from arrival | return cell (field) | dungeon warp reachable from the arrival | click -> orc01 / orc02 (Chebyshev) | click -> nearest touch NPC | used |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gef018 | 136,331 | 122,171 | orc002 (1,3) | 123-125 / 168-174 | **124,171** | 2 steps (east) | 138,329 | **none (sealed)** | 92 / 56 | 63 | **yes** |
| gef019 | 138,284 | 29,114 | orc004 (4,1) | 25-33 / 115-117 | **29,116** | 2 steps (north) | 137,286 | **none (sealed)** | 65 / 77 | 21 (Orc Warrior#1) | **yes** |
| gef020 | 215,51 | 162,53 | orc003 (4,1) | 158-166 / 54-56 | **162,55** | 2 steps (north) | 214,53 | **none (sealed)** | 130 / 58 | 20 (Orc Hero#1) | **yes** |
| gef021 | 223,205 | 108,89 | orc001 (3,2) | 105-111 / 84-88 | 108,86 | 3 steps (south) | 223,203 | **orc02 (orcsdun02), 24 steps** | 95 / **27** | 18 (Orc Lady) | no |
| gef022 (Batt's) | 63,337 | 30,157 | orc005 (3,2) | 27-33 / 152-156 | 30,154 | 3 steps (south) | 65,335 | **orc01 (orcsdun01), 24 steps** | **27** / 76 | 59 | no |

- **The brief's check holds for every house:** every exit click cell is >= 10 cells from both
  dungeon spans (the smallest is 27). Within a 2-cell aiming error the smallest is still 25.
- **The floor is flat** between every arrival and its click. The GAT's relative altitude is 0.0 on
  every walkable cell of the box around them, so the projected point is the flat projection.
- **The click's screen point** (game-region px; the character at the screen centre, 641,362; the
  indoor camera of camera_rdp.json):

  | house | click px |
  |---|---|
  | gef018 | 709.0, 312.0 |
  | gef019 | 569.9, 313.8 |
  | gef020 | 569.9, 313.8 |

  The indoor camera's RDP numbers are carried over from the console measurement and are **not
  measured on RDP** (camera_rdp.json "indoor": `validated: null`). The first live check is there
  (section 8).
- **Touch NPCs inside** (pre-renewal): Orc Warrior#1 (31,93), Orc Hero#1 (162,33) and
  Orc Lady#2008hat03 (119,106). Each has a 2-cell touch area (`OnTouch`), so walking into it would
  be an NPC contact. Each lies >= 18 cells from any click, and the runner never walks inside.

## 3. The safety argument (why a dungeon warp can never be reached)

The dungeon warps are orc01 (30,182) -> orcsdun01 and orc02 (108,114) -> orcsdun02, both inside
in_orcs01. They can be reached only by walking onto their cells inside in_orcs01. Five layers
keep that from happening:

1. **Structure (the strongest).** The runner refuses any house whose room reaches a forbidden warp
   (`house_rest.room_check` / `usable_why`).
   - A forbidden warp is any in_orcs01 warp that does not lead back to gef_fild10, derived from
     L3 rather than named.
   - Reach is tested from the arrival with BOTH connectivity rules: the client's (no corner
     cutting) and the superset without it. A room counts as sealed only when neither rule reaches
     a forbidden cell (a test covers a room that touches one corner to corner).
   - On the real data only gef018, gef019 and gef020 pass. In those rooms there is no walkable
     path to a dungeon warp at all: no click, client detour, retry loop or bug can reach one.
   - The check runs at the runner's start, from the local GAT and map cache, and fails closed:
     no GAT, no map cache, no indoor table, or no usable house = the run refuses to start.
2. **Behaviour.** Inside, the runner never makes a walk click.
   - It sits on the arrival cell, where the server put it (rAthena places a warped player on the
     destination cell when it is walkable; all 5 are).
   - It makes ONE exit click (two at most, on "no load") on a fixed pixel 2 cells away.
3. **The transition table.** `house_rest.Trip` holds a closed table:
   - field -> walk -> door -> inside -> rest -> exit -> back -> field, plus the retries and the
     fallbacks in section 4;
   - any other event in a state raises `TripStop` (a test enumerates every state x event pair);
   - the field logic (sustain's Fly Wing, the position rules) does not run from the door click
     until the field's readout is back. The house code runs in blocking helpers that call none of
     it.
4. **No Fly Wing inside.** in_orcs01 is `noteleport` (the mapflag above), so a wing would be
   refused, and a random teleport would be the one move that could land near a dungeon warp. The
   inside helpers press only sit and stand. Every unexpected sign inside STOPS the run (`r.Stop`;
   the `finally` block's `@warp` takes the character home):
   - a minimap readout;
   - a hit on us (Battle Log);
   - HP falling 2 points;
   - death;
   - Basic Info unreadable for 10 s;
   - an unknown UI state.
5. **The map-change bars.**
   - **At run time (pixels):**
     - after the door click the tracker accepts only "inside": a load gap, then no readout and a
       dark frame;
     - after the exit click it accepts only "back": a load gap, then the readout within 4 cells of
       the house's own return cell, or a bright frame with no readout for 6 s (the sealed room's
       only warp is its exit);
     - anything else is `stop:` = `r.Stop`;
     - on the field, in house mode, a load screen of >= 2 s with no door / exit click of ours
       within 8 s and no Fly Wing within 15 s is a hard bar ("an unexpected load screen"). In the
       7 allowed runs every load-like gap of >= 0.8 s followed one of our Fly Wings (4 of 4), so
       this adds no false bar on that sample.
   - **Offline (packets, `dungeon_judge.hard_bars`):** a map change counts as the planned house
     trip (`map_changes_house`) only when it matches a `house_door` event (to in_orcs01, at that
     house's arrival cell, within 30 s) or a `house_exit` event (back to gef_fild10 at its return
     cell). Each allowance is used once. Any other map change, orcsdun01 and orcsdun02 included,
     stays `map_changes_other`, the bar. Without house events the judge's record is unchanged.
- **On the field**, the walk to the door stays on the route grid: every zone of
  config/map_zones/gef_fild10.yaml still holds, the door's own included.
  - The ONE exception is the door click. It is made from an **approach cell**: on the route grid,
    within 7 cells of the door, from a standstill.
  - Its walk (the straight segment and the client's own path proxy on the stand grid with ONLY
    this door's touch area opened, `map_zones.walk_why`) may enter **only that door's** no-enter
    area, in <= 9 steps.
  - The other doors, the map exits and the NPC areas still hold.
- **Why not Batt's door (gef022)?** Its exit click is 3 cells from the arrival and 27 from orc01,
  so a correct runner cannot reach the warp, and probably not a buggy one either. But "cannot by
  construction" is a stronger guarantee than "does not by behaviour". gef022 is refused until Batt
  decides otherwise (it would also add the Kafra / bulletin-board zones at its approach).

## 4. The design (what `--rest house` does)

`dungeon_hunt.py run ... --rest house`; gef_fild10 only (refused elsewhere). The default
`--rest spot` is byte-for-byte today's code path. Its run_start, manifest and events gain nothing:
`fixes` names `rest` only when it is not the default, and the judge adds `map_changes_house` only
when house events exist.

1. **At the start:**
   - pair the 5 doors with their exits;
   - check every room (section 3) and compute the exit click cell and its pixel (indoor camera
     + GAT);
   - compute each usable house's approach cells (62 / 62 / 63 on the real map);
   - record all of it in run_start's `house` (usable, refused with why, exit px, approach
     counts).
2. **When the rest rule fires** (`rest_wanted`; strategy B: HP < 60 %), the trip goes walk.
   - `house_rest.choose` picks the usable house whose nearest approach cell is the fewest
     route-grid steps away: a BFS on the route grid, ties by name. Route steps, not distance: a
     wall can make the nearest door the farthest walk (tested).
   - **Fallback to today's field rest** ("sit where we stand"; event `house_fallback` with why)
     when:
     - HP is unread or below 30 % (HOUSE_MIN_HP);
     - no approach is within 120 steps (HOUSE_MAX_STEPS);
     - there is no route;
     - the approach is not reached in 90 s (HOUSE_WALK_MAX_S);
     - the door point is off the view or reads no-entry;
     - two door clicks gave no load.
3. **The walk** is the runner's ordinary walk (walk_target, the cursor gate, --walk-trust if on)
   along an A* route to the approach cell. A fight interrupts it: the trip goes back to field, and
   after the fight the rest rule decides again.
4. **The door click** is made on an approach cell, from a standstill (the readout unchanged for
   0.8 s).
   - The runner hovers the door's centre; a SWORD there is engaged, a no-entry ring is a fallback.
     It then clicks it through `click_at` (FrameGuard).
   - The tracker then needs, within 8 s, a load gap (Basic Info unread >= 1 s), then Basic Info
     back with no readout and a dark frame (mean <= 70) for 1.5 s: "inside".
   - A hit before any gap = "hit" (the fight first).
   - No gap = "none" (one retry).
5. **Inside:**
   - sit (Insert) at once, then one UI gate check (`farm0.client_state`, must be "clear");
   - then one read per second until `rest_done` (B: HP 100 %), or 600 s (HOUSE_REST_MAX_S; there
     is no damage to cut a rest short indoors);
   - then stand;
   - the time box can end inside: the run ends there, and the `finally` block's `@warp` takes the
     character home.
6. **The exit:**
   - hover the exit pixel; SWORD or no-entry = STOP (the projection or the room is not as
     planned);
   - click it; the tracker needs "back" at the house's return cell;
   - a second click on "none", then STOP.
7. **Back on the field:**
   - our cell is the read position, or the return cell from own knowledge (recorded `read:
     false`);
   - the old hits and the loot list are cleared;
   - the patrol RE-JOINS the loop (`map_routes.entry_index`: the nearest waypoint, or the one
     after it when we lie past it), as after a Fly Wing;
   - event `house_back`.

**New events** (house mode only): `house_plan`, `rest_route` (with `house`), `house_door`,
`house_read` (one per change of the tracker's state), `rest_start` / `rest_end` (with
`map: in_orcs01` and `house`), `house_exit`, `house_back`, `house_fallback`, `house_gap`,
`house_time_box`.
**New click sites:** two, both through `click_at` (`house_door`, `house_exit`). The click census
count of dungeon_hunt.py is unchanged (2), and its reason is extended.

## 5. Map changes from pixels: Batt's door step (the positive case)

His 5-Hz frames around his map change (packet at 0.00 s; the frames lag ~0.7 s):

| time from the packet | Basic Info HP | minimap readout | frame mean | what it is |
|---|---|---|---|---|
| -2.9 .. +0.54 s | 39 % | 69,323 ... 63,335 | 97-112 | walking onto the door |
| +0.76 .. +3.77 s | unread | none | 175 | the loading screen (3.0 s) |
| +3.94 s | unread | none | 8 | one black frame |
| +4.15 .. +14 s | 39 -> 40 % | **none** | **26-39** | inside in_orcs01 (he sat at +11 s) |

- The tracker (`house_rest.Transition`) fed with this sequence answers "inside" (a test replays
  it).
- The thresholds:
  - GAP_MIN_S 1.0 (his gap: 3.4 s);
  - DARK_MAX 70 (his room: <= 39; the field: >= 97);
  - INSIDE_S 1.5.
- **Only gef022's room was seen.** The three sealed rooms' brightness is unmeasured (section 8).
- Fly Wings also blank Basic Info (gaps of 3.8-12.4 s after a wing in a3, a6, a8). The field's
  gap bar therefore excuses 15 s after our own wing.

## 6. What it would have saved (the 7 allowed runs, 4.20 h, 192 kills, 45.7 kills / h)

**Measured** (`time_budget.py compare` over a2, a3, a4, a7, a8, a5b and b1; their events;
`house_rest.py steps` for the route steps):

| measure | value |
|---|---|
| rest (sitting + walking to sit) | 6,445 s, 42.6 % of the time, 33.6 s per kill |
| idle around a rest (before / after the sit) | 420 s, 2.2 s per kill |
| attacks on us while resting / around a rest | 297 / 769 attempts, 20 / 67 hits, **2,322 / 7,476 HP** |
| all damage taken | 37,750 HP; so the rest windows hold **26 %** (9,798 HP) |
| sitting regen | 3.68 HP / s (Batt's: 3.80) |
| field rests (rest_start -> rest_end) | 32: 4 ended full, **14 at the 300-s cap, 14 cut by a hit** |
| rest decisions (rest_go) | 47; HP at the decision 16-55 % |
| route steps from each decision to the nearest SEALED door's approach | median **77**, p75 113, p90 123, max 149, mean 82.4 |
| ... to the nearest of all 5 doors | median 50, mean 61.4 |
| decisions that qualify (HP >= 30 %, <= 120 steps) | **27 of 47**, mean 73 steps (a8's 16-19 % rests do not) |
| doors chosen | gef020 22, gef019 16, gef018 9 |
| Batt's loop: waypoints to the nearest sealed approach | median 73.5, max 175 steps |
| the return cells to the loop's nearest waypoint | gef018 10, gef019 27, gef020 22 cells |

**Estimate** (a transparent model, not a measurement):
- **The saving.** Indoors, no damage lands during the rest or around it. The 9,798 HP need not
  be sat back: 9,798 / 3.68 = **2,663 s** less sitting. Add the 420 s of idling around rests:
  **3,083 s at most**.
  - That is the **ceiling**, 15,124 -> 12,041 s for the same 192 kills = **57.4 kills / h
    (+11.7)**.
  - It assumes every rest moved indoors at zero cost.
- **Only the qualifying 27 of 47 decisions move indoors:** about 57 % of the ceiling, ~1,760 s.
- **The cost per trip:**
  - the walk to the door plus ~20 cells back to the loop (~93 cells), at 0.18 s per cell
    (continuous, Batt's pace) or 0.56 s per cell (the 8.x stop-and-go: 7-cell legs 3.9 s apart);
  - plus ~13 s of overhead: two loads of ~4 s (Batt's: 0.8 s to the screen + 3.4 s unread), the 1.5-s
    confirm, sit / stand / UI check, the exit hover and click, the 0.8-s standstill;
  - total **~30 s** (continuous) to **~65 s** (stop-and-go).
- **The number of trips:**
  - lower bound ~10: indoor rests run to full, and the mean rest decision at ~37 % HP needs
    ~370 s of sitting;
  - upper bound 27: one per qualifying decision;
  - 14 of the 32 field rests were cut short by a hit, which indoors does not happen.
- **Net:**

  | case | trips x cost | net saving | kills / h |
  |---|---|---|---|
  | best | 10 x 30 s = 300 s | ~1,460 s | **50.6 (+4.9)** |
  | middle | 15 x 45 s = 675 s | ~1,080 s | **49.2 (+3.5)** |
  | worst | 27 x 65 s = 1,755 s | ~0 s | **45.7 (+0)** |

- **What it does not touch.** Fights and reactions hold 24,767 HP (66 %) of the damage. Those
  still have to be sat back, indoors or out. To approach Batt's bar, the **damage per kill** must
  fall (the react time, the unanswered attackers, the defend scan:
  [gef10-time-budget.md](gef10-time-budget.md) section 10).
- **A cheaper variant, not built** (one change per version): an OPPORTUNISTIC rest. When the
  patrol passes within ~30 steps of a sealed door with HP < 80 %, rest there. That gives short
  detours and full rests in safety; Batt himself rested when his loop brought him to his door.

## 7. Tests (`services/backend/tests/test_house_rest.py`, 23; synthetic grids)

- The door / exit pairing for all 5 houses (and a refusal when a door has 0 or 2 matching exits);
  the forbidden warps are orc01 and orc02.
- Only the sealed rooms are usable. For all 5 houses: the click cell, 2-3 steps from the arrival,
  >= 10 cells from both dungeon warps and from every touch NPC.
- A room reaching a dungeon warp only corner to corner is NOT sealed.
- The exit click: the centre, else the widest-margin cell nearest the arrival, else none.
- The screen point: the indoor camera (rotated against the outdoor one), flat floor = GAT with zero
  altitude, rel (0,0) = the screen centre, 2-3 cells = 40-200 px, north drawn up and east drawn
  right.
- The approach cells: outside every area, the click's walk enters only its own door's area, a
  cell behind a no-cross wall is refused; the door grid opens only the chosen door's touch area.
- The door choice: route steps, not distance; the bound; ties by name.
- The pixel tracker: Batt's real sequence = inside. Every other outcome is named and tested:
  - a readout after the load (another map);
  - a bright frame with no readout;
  - no load ("none");
  - a blink that is not a load;
  - a hung loading screen;
  - Basic Info lost again;
  - back at the return cell, or by own knowledge after 6 s;
  - a readout far away;
  - a dark frame after the exit.
- The field's gap bar (Fly Wing and own click excused).
- The trip's table: the happy path, the retries, and every undefined state x event pair raises.
- The runner: house_trip_why, still_since, fixes_of (the default record has no `rest` key), the
  CLI default `spot`, the two click sites once each through click_at, `hr` reached only in house
  mode.
- The judge: the recorded trip counts as `map_changes_house`. The dungeon, another house's arrival,
  a late change and a second entry stay bars. No house events = no new key.
- One test reads the real local data when it is there (skipped in CI): the 3 sealed rooms, 24
  steps to orc01 / orc02 from gef022 / gef021, every click >= 10 from both.
- The estimate's helpers: the multi-source steps (= one BFS per source, nearest wins) and the
  rest decisions read from a run's events.
- The runner's start-up (`dungeon_hunt.house_setup`): any map but gef_fild10 is refused; on the
  real local data (skipped without it) it accepts exactly gef018 / gef019 / gef020, refuses
  gef021 / gef022 as not sealed, finds >= 60 approach cells each (on the route grid, outside
  every area) and computes the exit pixels of section 2. This is the offline proof that a
  `--rest house` run would start.
- With them: test_dungeon_hunt, test_click_census (count unchanged, reason extended),
  test_walk_trust, test_map_zones, test_map_routes, test_cursor_unknown, test_dungeon_judge,
  test_time_budget and test_map_prep pass.

## 8. Open risks, and what needs a live check FIRST (unscored, supervised)

1. **The indoor camera on RDP** (yaw +45.96 degrees, distance 273) was measured on the console
   path, not on RDP. The exit click's pixel depends on it.
   - The geometry tolerates a 1-cell error in any direction, and any error "beyond" the exit (the
     walk crosses the span).
   - Live check: in each sealed house, hover the computed point and read the cursor (WALK
     expected, not no-entry), then make the exit once.
2. **The three sealed rooms' pixels:** the interior's frame mean (<= 70?), the absence of a
   minimap, the HP / SP readers on that background, and `ui_gate` "clear" inside.
   - Only gef022's room was seen, in Batt's frames.
   - Live check: one visit per sealed house; record its frame mean and the reads.
   - A brighter room makes the tracker STOP the run (it fails safe, not silently).
3. **The door click:** the cursor verdict over a warp cell (WALK or unknown expected), and that the
   client's walk into the span fires the warp within 8 s.
   - Batt's request to 62,338 was answered 0.63 s later by the map change.
4. **The minimap readout at the three return cells** (138,329 / 137,286 / 214,53): if it does not
   read there, the runner uses own knowledge after 6 s, and the 8.1 rule (a Fly Wing after 20 s
   unread, on the field) applies as today.
5. **The walk to the door at 30-60 % HP** crosses orc territory, 73 steps on average. The fights on
   the way are ordinary fights, but at lower HP. HOUSE_MIN_HP = 0.30 keeps the lowest rests in the
   field.
6. **The judge's 30-s match window** assumes the warp fires soon after our click (Batt: 0.6 s).
7. **The field's gap bar** is new in house mode. A long Basic Info gap that is not a load (a client
   freeze: memory `client-frozen-after-idle`) now stops the run instead of waiting. That fails
   safe.
8. **Not handled, by design:** an Orc Lord at a door, and a monster standing on an approach cell
   (the runner engages it or falls back).

## 9. Proposed pre-registration (for the parent)

- **Arm:** the version current then, plus `--rest house` (ONE change). The baseline is the same
  version without it, run in the same block (Amendment E's cycle, `--clear-map`, the judged pre-run
  frame, the hotbar stock check).
- **Before it:** the live checks of section 8 (items 1-3), unscored, Batt in Watch only, one trip
  per sealed house. Any STOP there = no scored run until it is understood.
- **Hard bars** (packets, the judge):
  - map changes other than the recorded house trips: 0;
  - map changes to orcsdun01 / orcsdun02: 0, absolute;
  - NPC contacts 0, attacks on non-targets 0;
  - no Fly Wing pressed between a `house_door` and its `house_back` (events);
  - no attack act on us while in in_orcs01 (packets).
- **Trip bars:**
  - >= 90 % of door clicks reach "inside";
  - 100 % of exits come "back" at the planned return cell;
  - every STOP is reported with its frame (`stop-house.jpg`).
- **Measures** (pooled over >= 2 runs, against the baseline and Batt's bar):
  - kills / h, items / h, value / h at Overcharge;
  - the rest share, and HP taken per kill in the rest and around-rest windows;
  - trips / h, the trip time (door click -> house_back), route steps to the door;
  - fallbacks by why, deaths.
- **Prediction (from section 6):**
  - kills / h +3 to +5 over the baseline;
  - the HP taken in rest and around-rest windows per kill falls by >= 50 %;
  - the rest share does not rise.

## 10. Reproduce

    export PYTHONPATH=scripts:packages/poring_dataset/src:packages/poring_env/src
    python3 scripts/grf_read.py extract /mnt/poring-thai-src/ro_thai/data.grf 'data\in_orcs01.gat' \
        --out /dev/shm/poring-lab-tmp/gat --decode-des
    python3 scripts/house_rest.py table          # the door / exit table (section 2), JSON
    python3 scripts/house_rest.py steps <a2 a3 a4 a7 a8 a5b b1 sids>   # section 6's route steps
    python3 scripts/time_budget.py compare --target 20261026T095021-demo-human-demo-gef10 \
        --live 898 <a2 a3 a4 a7 a8 a5b b1 sids> --json   # section 6's time and damage rows
