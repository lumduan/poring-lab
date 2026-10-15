---
title: "search_targets: finding targets like a player (farm@2's SEARCH skill) -- design"
status: PROPOSED (its test is PRE-REGISTERED in demonstrations.md 3.39; one decision is Batt's, section 6)
date: 2026-10-15
owner: Batt
related: [../demonstrations.md, walk17.md, npc-render.md, ../../scripts/farm1.py]
---

# search_targets -- design

## 1. Why (Batt, 2026-10-15 ~21:40)

farm@1 spent 89 % of its 30 minutes FINDING a monster.
- It looked only while standing, and it wandered at random inside a 61 x 56-cell box.
- In 76 of its 78 wanders, the packets put no monster within 14 cells.

Batt's correction: choosing a dense area hides the real gap. The bot must SEARCH like a player,
including for targets that never come to it (plants, mushrooms). So farm@2 adds a SEARCH skill (L1
`combat.search_targets`), designed here and pre-registered as its own test (3.39).

## 2. Batt's five points, and how each is built

### 2.1 Look while walking
- The detector already runs in its own thread on the frame bus (~3-4 Hz at 8 threads, full frame;
  `loot1.Sampler`).
- The search loop reads every new detection frame, standing or walking. A TARGET IN VIEW
  INTERRUPTS the route: the next waypoint click is not sent, and the engagement starts at once.
- A target in view means:
  - a detector `monster` box;
  - size-gated (farm@1's Creamy gate, 45 native px at the camera's scale for its cell);
  - its cell inside the search area;
  - not one dropped in the last DROP_S seconds.

### 2.2 Explore with a plan
- **The SEARCH AREA:** the map's stand cells (client GAT AND server map cache, outside every warp
  span and touch area: the three checks) AND the map's animated-region MEASURED area. Clicks
  outside the measured area are refused (Batt's decision 3, 2026-10-15). On prt_fild08 that is the
  tuning scope (+-68 of 268,107), about 15.5k cells.
- **The VIEW footprint** (from the camera model): the cells drawn on screen and not under the
  static UI windows, about dx -10..+18, dy -13..+17 around the GM.
- **A COVERAGE GRID of 16 x 16-cell tiles** (about half a view each).
  - Each tile keeps a LAST-SEEN time.
  - It is refreshed whenever the GM's footprint covers most of the tile's area cells.
- **The next GOAL** is the tile maximising `staleness / (1 + path_cells / 40)`:
  - staleness = now - last seen, capped at 600 s; never seen = the cap;
  - plus the memory's bonus (2.3).
  - The goal is the tile's area cell nearest its centre.
  - One A* PATH on the area cells takes the GM there in long, continuous routes. The route is not
    re-planned until it ends or a target interrupts it.
- **Position:** the minimap readout (`poring_env.selfpos`). While walking, one read is accepted
  when it is within 3 cells of the dead-reckoned position (the path progress at the map's speed).
  Standing, two equal reads are required (farm@1's settle rule).

### 2.3 Remember sightings
- Every target sighting is kept with its cell and time.
- **A STATIONARY target** = seen on the same cell (+-1) twice, >= 10 s apart.
  - On prt_fild08 that is a Pupa: an immobile mob that v1 knows.
  - Plants and mushrooms join when the detector learns them (labels v2 scope).
  - It is remembered until it is engaged, or until it is not found when its cell is in view again.
  - Its tile gets a +900 s staleness bonus, so routes return to it.
- **A MOVING sighting** decays: its bonus is 300 s x exp(-age / 20 s), gone after 60 s.

### 2.4 Spawn data
- `data/kb/spawns.json` gives the species to expect and their counts, so the run reports the
  expected density (prt_fild08: 140 mobs on ~90k walkable cells).
- The TARGET list (Poring, Lunatic, Pupa, Drops) and the IGNORE list (everything else) are Batt's.
  The pixels cannot tell species apart, so the ignore list is enforced by:
  - the size gate (Creamy: 51 x 53 native, it flies);
  - the packets afterwards: a non-target hit is a hard safety failure.
- The L3 mob data marks immobile species; the report counts their sightings apart.

### 2.5 Walk continuously
- Waypoints every 10 cells along the path, inside the view.
- The next click is ISSUED BEFORE THE CHARACTER STOPS: when the dead-reckoned remaining distance to
  the current waypoint is <= 3 cells (~0.45 s at 150 ms a cell).
- **How a click DURING motion is gated is Batt's decision: section 6.**

## 3. Engagement, loot and the stops

- **Engagement and loot: farm@1's, unchanged** (`farm1._engage`), with three exceptions:
  - the damage cue is DROPPED: it is not usable (1 of 3 consistent);
  - the re-engage is the REATTACK_S click only;
  - a target whose cell is in the measured animated region is skipped (decision 3: no hover or
    click point there).
- **The first-click diagnosis (Batt: "as planned") is closed:** the first SWORD click attacked 3/3
  (the client walks up and sends its own attack_request 0.4-2.4 s later).
- **The attack-started signal stays to be PROVEN, and search@1 banks the frames for it.**
  - For each engagement click: 6 s of game-region grabs at 5 Hz into the session.
  - A candidate pixel signal is then pre-registered and judged offline against the packets' first
    damaging act.
- **Stops:** as farm@1.
  - the UI gate's pixel check: at every engagement start, and every 30 s while walking;
  - HP;
  - Batt's takeover;
  - the mux leaving ASSIST;
  - an unknown own cell.

## 4. Measured (3.39), against farm@1 by the SAME definitions from its session

- **time to first target:** from the loop start to the first engagement start.
- **targets found per 10 min:** engagements started, over the run's minutes. Also reported: the
  distinct target units in view from the packets, a ceiling.
- **coverage per 10 min:** distinct search-area cells that entered the GM's view footprint, from
  the PACKETS' own GM track (self_move), identical for both runs.
- **kills / h:** from the packets.

## 5. Not in search@1

Plants and mushrooms (the detector does not know them yet), other maps, and S2.

## 6. THE DECISION FOR BATT: how a click DURING motion is gated

robust2 reads the cursor against a PARKED, STILL background. While the GM walks, the whole scene
scrolls, the cursor mask covers everything, and the read is `unknown`. So a click issued before the
character stops cannot be cursor-read.

| option | what gates a moving click | continuous? | risk |
|---|---|---|---|
| **A. stop-and-go (built, the default until Batt decides)** | robust2 WALK series at standstill, as walk@15 | no: ~1.5 s stop per waypoint; waypoints 14 cells apart (~2.1 s walking) | none new |
| **B. predictive** | map + units instead of the cursor (below) | yes | a click on an UNDETECTED monster attacks it |
| C. a moving-scene cursor reader | a new reader, measured first | yes | needs its own measurement before any use |

**B's gates, every one fail-closed.** The FIRST click of a route (from standstill) stays
cursor-gated as in A. Each later click must pass all of these:
- a stand cell of the search area;
- outside the measured animated region;
- >= 3 cells from every L3 NPC cell and warp span;
- no detector unit box within 40 px of the click point, on a frame <= 0.35 s old;
- the click point outside the static UI windows.

Its safety is judged from the packets (3.39):
- any NPC contact, dialog, non-target hit or map change fails the run;
- an attack request no engagement click explains (an "unintended attack") is counted and reported.

**Claude's recommendation:** B for search@1, with those hard bars. It gives Batt's point 5 now; A
cannot. On prt_fild08, the only units that matter are monsters, and those the bot would attack
anyway, except a Creamy, which the packet bar catches.
