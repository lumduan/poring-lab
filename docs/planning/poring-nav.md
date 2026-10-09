---
title: "poring_nav: ONE source of truth for map navigation (ADR-0020 #18)"
status: PROPOSED
date: 2026-10-09
owner: Batt
extends: docs/adr/0020-block-programming-flows.md
gate: "PLAN ONLY. Batt 2026-10-09: 'Plan first, stop for my approval before moving code (it touches the executor the walk rules use). Never move it while a scored client run is active; no change to pre-registered rule behaviour without the bytecode-identical proof or a new pre-registration.'"
---

# poring_nav: one source of truth for map navigation

**Batt's decision (2026-10-09, ADR-0020 #18):**
- Create a small shared package for map navigation: GAT loading, the walk graph, A*, and the path
  limits as single named constants.
- Both poring_flow (editor, linter, simulator) and the executor import it. The duplicate planner
  is removed afterwards.
- The existing cross-check test (240 legs on the 6 lab maps, 0 disagreements) stays the regression
  gate for the move: it must still pass, unchanged, after the swap.
- Check the limits against the server, and document how a leg splits into clicks. The per-click
  limit is the one the server enforces; the linter and the executor use the same constants.

## 1. What exists today (inventory, main 64426fc + feat/adr0020-resolutions)

| piece | where | used by |
|---|---|---|
| A* `walk_path(grid, x0, y0, x1, y1, *, max_len=MAX_LEN, altitude, climb)`: 8-way, costs 10 / 14, the server's corner rule | `packages/poring_dataset/src/poring_dataset/walk.py:61` | the walk RULES through `scripts/walk5.py:300` (`plan_path`) and `scripts/walk6.py:163` (`plan`, with blocked cells), walk@5–16; `walk_check.py` |
| `MAX_LEN = 32` (comment: "the server … refuses a longer path") | `poring_dataset/walk.py:42` | `walk_path`'s default |
| `GatGrid` (a `Grid` over a GAT walkable array) | `scripts/walk5.py:59` | the walk rules |
| `PLAN_MAX = 48` ("the A* plan's own step limit (it is split into clicks)") | `scripts/walk5.py:48` | walk5/6/12's `max_len` |
| `SEG_MAX = 5` (comment: "far under the server's 32") | `scripts/walk5.py:47` | walk@5 |
| `SEG_INDOOR, SEG_OPEN = 3, 5`, `FARTHER = 4`, `SHORTER = 4` | `scripts/walk11.py:110`, `:150`; `scripts/walk13.py` | walk@11–16's click points |
| GAT parser `parse` / `Gat.walkable()` / `relative_altitude` | `packages/poring_dataset/src/poring_dataset/gat.py` | the rules, the camera, picking |
| MW1's own A* `Walk.route(a, b)`: 8-way, unbounded | `packages/poring_flow/src/poring_flow/sheet.py:125` | the linter's routes, the simulator |
| MW1's GAT reader `read_gat` → `Walk` rows | `packages/poring_flow/src/poring_flow/kbsheet.py:67` | the /flows local world |
| the cross-check test | `packages/poring_dataset/tests/test_walk_matches_flow_planner.py` | the regression gate (host only) |

The cross-check found two planners that agree on every leg (reachability, cost, step count), and
two GAT readers that see the same walkable cells on all 6 lab maps. It also found one real
difference: the executor plans ONE leg of at most `PLAN_MAX` = 48 steps, while the linter routes
legs of any length (75 of 240 lab legs are longer).

## 2. What the server enforces (read from the pinned rAthena e985006, 2026-10-09)
- `src/map/unit.cpp:841` `unit_walktoxy` is every walk request (a click's `CZ_REQUEST_MOVE` lands
  here).
  1. It runs `path_search` (`:855`). Its buffer holds `MAX_WALKPATH` = **32** steps
     (`src/map/path.hpp:14`); a longer path fails the search (`path.cpp:415`).
  2. For a non-NPC: **`path_len > battle_config.max_walk_path` → refused** (`unit.cpp:860`).
     `max_walk_path` defaults to **17** (`src/map/battle.cpp:8684`, range 1–32), and
     `conf/battle/client.conf:42` sets `max_walk_path: 17` ("Maximum walk path (how many cells a
     player can walk going to cursor)"). The lab's conf imports do not override it
     (`services/rathena/conf/import/`: no battle import).
  3. `OFFICIAL_WALKPATH` is DEFINED (`src/config/core.hpp:26`): a path longer than **14** steps is
     refused unless the straight line has no obstacle (`unit.cpp:864–868`, `path_search_long`).
- **So, per click: ≤ 14 steps always passes (if a path exists); 15–17 passes only on a clear
  straight line; > 17 is refused.** Batt's "about 32" is the search buffer's size, not the click
  limit.
- The current comments citing 32 (`poring_dataset/walk.py:37–42`, `walk5.py:47`) are incomplete,
  and are corrected in the move (comment-only).
- Our rules click far inside the limit: at most `SEG_OPEN + 3 + FARTHER` = 12 cells along the plan
  (`walk11.farther_candidates`), and 9,636 recorded walks were all ≤ 14 steps (`walk_check.py`,
  2026-10-04).

## 3. How a LEG splits into CLICKS (the model both sides will share)
1. A **leg** is one planned walk from the current cell to a goal on the same map: one `walk_path`
   call, at most **`PLAN_MAX` = 48** steps. A longer route needs WAYPOINTS: legs chained at
   intermediate cells.
   - The executor: the flow's `walk_to`.
   - The linter: a route between two cells on one map.
2. A leg is walked as **clicks** on cells along it. The rule picks each click cell at
   `SEG_INDOOR` / `SEG_OPEN` cells ahead (3 / 5), with its nearer / farther alternates. Every click
   cell is at most **`CLICK_MAX_SAFE` = 14** server path steps from where the character stands:
   the server's unconditional limit.
3. The server re-plans each click itself. Our planner mirrors its costs (10 / 14) and corner rule,
   which is why the cross-check agrees with the client's walks.

**The constants, one place** (`poring_nav.limits`):

| constant | value | source |
|---|---|---|
| `SERVER_SEARCH_MAX` | 32 | path.hpp:14 `MAX_WALKPATH` |
| `SERVER_MAX_WALK_PATH` | 17 | battle.cpp:8684 default + client.conf:42 (lab: not overridden) |
| `SERVER_OBSTACLE_FREE_MAX` | 14 | unit.cpp:864–868 with core.hpp:26 `OFFICIAL_WALKPATH` |
| `CLICK_MAX_SAFE` | 14 | = min of the above: the per-click limit the rules and the linter use |
| `PLAN_MAX` | 48 | the leg limit (today walk5.py:48; unchanged value) |
| `STRAIGHT`, `DIAGONAL` | 10, 14 | the server's path costs (path.hpp `MOVE_COST`, `MOVE_DIAGONAL_COST`) |

A test pins each server constant to its source line (the pinned ref), as the knowledge base pins
its facts.

## 4. The package
`packages/poring_nav` (Apache-2.0, our own code; stdlib + numpy only; no poring_* imports):
- `limits.py`: the table above.
- `gat.py`: the ONE GAT reader. `poring_dataset.gat`'s parser moves here; MW1's `read_gat` becomes a
  thin view (`.walkable()` rows).
- `grid.py`: `Grid` (the protocol) + `GatGrid` (from walk5.py).
- `astar.py`: `walk_path` and `octile` moved verbatim; `legs(path)` (split at `PLAN_MAX`) and
  `click_ok(steps)` (≤ `CLICK_MAX_SAFE`).

**Who imports it:**
- `poring_dataset.walk` and `.gat`: re-export (`from poring_nav.astar import walk_path`), so every
  existing import path keeps working.
- `poring_flow`: `Walk.route` calls `poring_nav.astar.walk_path` with `PLAN_MAX` legs; MW1's own A*
  is deleted.
- `scripts/walk5.py`: `PLAN_MAX` imported, not defined.
- The vision executor (MW3) later.
- `test_guards`: poring_nav may be imported by vision and the backend; it imports nothing of ours.
- **The backend gets it like poring_flow:** a read-only `dev-src` mount (compose.dev) + PYTHONPATH,
  and a guarded `recreate:backend` (a new mount) at a gap.

## 5. Order, and the gates
1. **Create poring_nav** with copies, its own tests, and the limits table pinned to the source.
   Nothing imports it yet.
2. **poring_flow switches** to `poring_nav.walk_path` + `legs()`, and its A* is removed.
   - The cross-check test must pass UNCHANGED.
   - The linter newly reports a route leg over `PLAN_MAX` as "needs a waypoint". This is a NEW
     lint finding. Severity proposed: readiness, since it blocks a run, not the design (#6).
3. **poring_dataset re-exports;** walk5's constants come from `limits`. The rules' behaviour must
   not move. The **bytecode-identical proof:** for walk@15 and walk@16 (pre-registered) and their
   whole call chain into the planner (`walk5.plan_path`, `walk6.plan`, `walk_path`, `octile`,
   `GatGrid` methods), a test asserts the same `co_code`, `co_consts`, `co_names` and the same
   constant VALUES before and after.
   - Line numbers may move with the comments; behaviour may not.
   - If any of it cannot be identical, that step waits for a new pre-registration.
4. **Deploy:** backend (new mount: recreate) + frontend-dev at a gap with NO scored client run.
   The walk rules are host scripts: they pick the code up at their next start, which is why step 3's
   proof comes before any further scored run.
5. **Remove** MW1's duplicate GAT reader once it is a view.

**Not in scope:**
- No change to any rule's click distances.
- `CLICK_MAX_SAFE` only asserts what the rules already do. A test fails if a rule's farthest click
  candidate could exceed 14.

## 6. Risks
- Moving the GAT parser touches the camera and picking imports, which are offline and runtime
  shared. The re-export keeps their import paths.
- The backend image (production) needs poring_nav copied in, like poring_flow. That is a later
  guarded image rebuild.
- **Waiting for Batt's approval. No code moves before it.**
