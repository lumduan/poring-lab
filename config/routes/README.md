# Patrol routes: per-map waypoint circuits (Batt's own map knowledge)

Batt asked for these on 2026-10-22, after their Crusader demo in orcsdun01. The map is a loop
around a central block. Batt walks a fixed circuit of waypoints in ONE direction, never back and
forth, so they keep meeting monsters as they respawn.

A routes file holds that circuit for one map. It is reviewed static map data, as ADR-0015 allows:
static map knowledge used at plan time. It is the twin of `config/map_zones/` (README.md there):
the same review rules, the same fail-closed loading.

- One file per map: `config/routes/<map>.yaml`. The name is the map's, e.g. `orcsdun01.yaml`.
  The extension is `.yaml`; the loader refuses a `.yml`.
- **No file means no change.** Nothing walks a route the file does not give.
- **A file that is there but wrong stops the run before any input.** The loader
  (`scripts/map_routes.py`) fails closed.
- **The agent never writes or approves a route on its own.** The review rules are map_zones'
  own, through the same code (`map_zones.review`):
  - every file names the person who reviewed it (`reviewed_by`) and the date (`reviewed`);
  - a reviewer named like the agent (`claude`, `agent`, `bot`, `ai`, `assistant`, `auto`) is
    refused;
  - **the one exception is a person's recorded delegation**: the reviewer reads exactly
    `agent (delegated by <person>, YYYY-MM-DD)`, with a person who is not the agent and a real
    date, and the file carries a top-level `delegation:` note citing the person's decision;
  - `delegation:` without a delegated reviewer is refused.

Check a file (its schema; no map data needed):

    python3 scripts/map_routes.py check orcsdun01

It prints the file, its sha256, its review, its source and each route's waypoint and leg counts.
It exits 1 on any error in the file.

Prove a file on the map:

    python3 scripts/map_routes.py prove orcsdun01

It loads the runner's stand grid the way `scripts/dungeon_hunt.py` does: the map's GAT from
`poring_dataset.camera.GAT_DIR` (client data in /dev/shm, never committed) and
`anim_region.stand_grid`. It also loads the map's zones. Then it checks:
- every waypoint is walkable and outside every zone (not inside a no-enter area, not on a no-cross
  line, not in a piece the zones seal off);
- every leg is connected on the route grid: the walkable cells minus the zones, as the runners
  route (`hunt_core.astar`: 8-connected, a diagonal step needs both side cells). That includes a
  loop's closing leg.

It prints each leg's length (cells walked, and the cost in straight steps, a diagonal = 1.4) and
each route's total. It exits 1 on any failure, 2 when the map data is not there.

## Coordinates

Waypoints are **map cells**: `x` grows east, `y` grows **north**. These are the same numbers as
the minimap readout, `/where`, the server and `config/map_zones/`. Copy them as you read them;
nothing is flipped.

## Format

```yaml
map: orcsdun01                       # must equal the file's name
reviewed_by: "agent (delegated by batt, 2026-10-22)"   # REQUIRED: as map_zones
reviewed: 2026-10-22                 # REQUIRED: the review date, ISO (YYYY-MM-DD)
delegation: "..."                    # only with a delegated reviewer, and then REQUIRED
source: "the demo session id and the extractor"        # REQUIRED: where the waypoints came from
routes:                              # at least one; a patrol hunt walks the FIRST
  - id: batt-loop                    # 1-40 of [a-z0-9-], unique in the file
    kind: loop                       # loop (the last waypoint connects back to the first) | path
    note: "the circuit Batt walked in the demo"
    waypoints: [[40, 60], [120, 60], [120, 140], [40, 140]]   # the LISTED ORDER is the direction
```

- Each route needs exactly `id`, `kind`, `note` and `waypoints`. The note is a short reason.
- Every waypoint is `[x, y]` of two whole numbers, on the map when the map's shape is known.
- A loop needs at least 3 waypoints, a path at least 2.
- Unknown keys are refused, at the top level and in a route. A misspelt key would otherwise be
  ignored without a word.

The loader also refuses:
- a waypoint repeated straight after itself;
- a route whose last waypoint is its first (a loop closes by itself: one closing waypoint equal
  to the first is allowed and dropped, as for a zone polygon; a path that ends where it starts is a
  loop);
- a loop whose waypoints all lie on one line (it would walk back and forth);
- an empty `routes` list, or no `source`.

## Walking a route (Batt 2026-10-22)

The listed order is the direction. A loop goes round and round; a path ends at its last waypoint.
`scripts/map_routes.py` holds the rules as pure functions, for the runner:

- **Reached**: within 2 cells (Chebyshev) of a waypoint (`reached`, `REACH_TOL`).
- **Next**: the waypoint after the one reached (`next_index`): cyclic on a loop; none after a
  path's last.
- **Resume after an interruption** (a fight or a loot step moved the character; Batt: "afterwards
  resume at the NEXT waypoint AHEAD on the loop (never turn back to a passed one)"),
  `resume_index`:
  - k is the last waypoint reached or passed. The answer is k+1 or k+2, never k or one behind it.
  - k+1 counts as passed, so the answer is k+2, when the character is within 2 cells of k+1, or
    strictly closer to the leg k+1 → k+2 than to the leg k → k+1. Distance is Chebyshev, to the
    straight segment between the waypoints, sampled one cell per step.
  - Otherwise the answer is k+1.
- **Join from anywhere** (the run's start, after a Fly Wing), `entry_index`: the nearest waypoint
  (the first on a tie), then the same rule: if the character already lies past it (within 2
  cells, or closer to the leg after it than to the leg before it), the one after it.
- Each leg is walked on the route grid (the walkable cells minus the zones), never straight
  through a wall.

## The hunt block's search option

The /flows hunt block's `search_route` option (docs/planning/blocks-from-hunt-flow.md section 7d)
chooses how the hunt searches between fights: `heading` (the default; today's heading search) or
`patrol_route`: walk this file's first route continuously, in its listed direction, resuming by
the rules above after every fight or loot step.

- The linter refuses `patrol_route` when the map node's map has no routes file, or when this
  loader refuses the file (`patrol_route_missing`, `patrol_route_unreadable`).
- The run-start check refuses a patrol hunt when the routes were not loaded at all, and re-lints,
  so a file that no longer loads refuses the run.
- The editor has no routes layer yet: waypoints will be drawable there later, like the Zones
  layer. Until then a person writes the file, and git is the review record.
