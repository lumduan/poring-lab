# Map zones: per-map forbidden zones (Batt's own map knowledge)

Batt asked for these on 2026-10-20 at about 21:0x, after the "map traps" runs. The bot walked
through a narrow entrance into a big room and kept circling inside it. The pocket escape never
fired, because the room is large.

A zones file holds Batt's knowledge of one map. It is reviewed static map data, as ADR-0015
allows: static map knowledge used at plan time.

- One file per map: `config/map_zones/<map>.yaml`. The name is the map's, e.g. `prt_fild08.yaml`.
  The extension is `.yaml`; the loader refuses a `.yml`.
- **No file means no change.** The hunt runner (`scripts/hunt_flow.py`) behaves exactly as before.
- **A file that is there but wrong stops the run before any input.** The loader fails closed.
- **The agent never writes or approves a zone on its own.** Every file names the person who
  reviewed it, and the loader refuses a file without one. It also refuses a reviewer named like the
  agent (`claude`, `agent`, `bot`, `ai`, `assistant`, `auto`).
  - **The one exception: a person's recorded delegation** (Batt, 2026-10-21, decision 1 on the
    overnight loot report: "I DELEGATE the zone authoring to you ... reviewed_by: "agent
    (delegated by batt, 2026-10-21)", plus a note pointing to this decision; keep fail-closed
    loading").
  - The reviewer must then read exactly `agent (delegated by <person>, YYYY-MM-DD)`, with a person
    who is not the agent and a real date.
  - The file must also carry a top-level `delegation:` note citing the person's decision. Any other
    agent-like reviewer is still refused, and `delegation:` without a delegated reviewer is refused.
  - `prt_fild08.yaml` is the first such file (2026-10-21), `orcsdun01.yaml` the second (2026-10-22:
    no-enter areas around both warp spans; docs/planning/orcsdun01-dungeon-prep.md section 3).

Check a file before a run:

    python3 scripts/map_zones.py check prt_fild08

It prints the items, how many cells each one takes, and the file's sha256. It exits 1 on any error
in the file.

Prove what a file seals and cuts off (Batt 2026-10-21: "PROVE it offline on client∩server
walkability"):

    python3 scripts/map_zones.py prove prt_fild08

It prints JSON for two grids: client ∩ server walkability, and the runner's stand grid. For each:
- every piece the zones cut off: its cells, box and the item it borders, under two connectivities
  (with and without rAthena's no-corner-cutting rule);
- the cells newly unreachable OUTSIDE those pieces (0 = nothing else was cut off);
- the server's spawn cells lost;
- the runner's search area lost;
- sampled clicks into each piece, every one refused by the click gate.

## The /flows editor (B2, 2026-10-21: export only)

The map node's **Zones layer** in /flows draws these files (docs/planning/blocks-from-hunt-flow.md
section 3 and 7b). It never writes one: Batt decided "export only for now" (D6). A person downloads
the YAML and commits it here; git is the review record.

- **Check with the loader** sends the text to the backend, which runs THIS loader on it
  (`map_zones.py`: the same messages as `check`, the same sha256 of the bytes). The cells each item
  closes, the pieces it seals off and the search area are the loader's, drawn as returned.
- **The editor never fills `reviewed_by`** (nor `reviewed`, nor `delegation`). They are typed for
  each export, even when the editor started from the committed file; the file's own review is shown
  only as a reference.
- **The editor's form.** A file written by hand in exactly this form has the SAME bytes, so the same
  sha256, as the editor's: `prt_fild08.yaml` is in it.
  - The leading `#` lines first (`# ` + text, `#` alone for an empty line). Only that leading block
    is kept.
  - Then `map`, `reviewed_by`, `reviewed`, `delegation` (only when there is one), `no_cross`,
    `no_enter`.
  - `map` and every `id` plain when YAML reads them back as the same string (a letter or `_`
    first, then letters, digits, `_`, `-`; never a word like `yes` or `null`), else double-quoted.
  - `reviewed_by`, `delegation` and every `note` double-quoted; `reviewed` a plain date.
  - Each item as `  - id: ...`, `    note: "..."`, `    points: [[x, y], ...]` (`polygon:` for an
    area, its first point not repeated); `\n` line ends, one at the end.
  - A file in another form (the example below: `reviewed_by: batt` plain) is still a valid file;
    its editor twin just differs in bytes.

## Coordinates

Points are **map cells**: `x` grows east, `y` grows **north**. These are the same numbers as:
- the minimap readout under the minimap;
- `/where`;
- the server.

Copy them as you read them; nothing is flipped. The runner's grids are indexed `[y, x]` with this
same `y`.

## Format

```yaml
map: prt_fild08            # must equal the file's name
reviewed_by: batt          # REQUIRED: the person who reviewed this file
reviewed: 2026-10-21       # REQUIRED: the review date, ISO (YYYY-MM-DD)
no_cross:                  # walls: a polyline the GM never crosses
  - id: nc1                # unique in the file (both kinds share one id space)
    note: "the narrow entrance to the NE room"
    points: [[300, 250], [302, 250]]        # >= 2 cells
no_enter:                  # areas: the GM never walks into them
  - id: ne1
    note: "the NE room itself"
    polygon: [[300, 251], [340, 251], [340, 290], [300, 290]]   # >= 3 cells, closes by itself
```

- Each item needs exactly `id`, `note` and `points` (or `polygon`). The note is a short reason in
  your words.
- Every point is `[x, y]` of two whole numbers, on the map.
- Unknown keys are refused, at the top level and in an item. A misspelt key would otherwise be
  ignored without a word.
- Either list may be empty or left out.

The loader also refuses:
- a point repeated straight after itself in a line;
- a polygon that repeats a point (one closing point equal to the first is allowed and dropped);
- a polygon with no area, whose edges cross, or that folds back on itself.

## What each kind does

**A sealed room** (Batt 2026-10-21: "a no-cross line sealing C1's entrance"). When the lines
and areas cut a part of the walkable map off from the rest, the runner drops that part from the
search area and the route grid (`map_zones.sealed_off`). No heading, goal or route goes in. A
monster there is still seen and tracked, but never engaged (`target_dropped`, zone
`target_sealed`). The pieces cut off are the smaller ones; the largest piece of each walkable
part stays.

**`no_cross`: a wall.**
- Every cell the line touches is closed to the GM. A line that passes exactly through a cell corner
  closes all four cells around that corner.
- So no step, straight or diagonal, can slip across it.
- A click whose walk would cross it is refused.
- Use a line for a doorway or a narrow entrance: a line across the gap.

**`no_enter`: an area.**
- The cells whose centre lies inside the polygon or on its edge are closed.
- The GM never walks into them.
- No target inside one is engaged, and no loot inside one is picked up.
- If the GM is ever inside one (a start, or the client's own path), the runner walks it out the
  shortest way. That way never crosses a line and never enters another area.
- An area is not a wall: a polygon one cell wide on a diagonal can be passed corner to corner. Draw
  a wall as a `no_cross` line.

## How the runner enforces them

`scripts/hunt_flow.py` applies the zones only when the file exists AND the version opts in with
`"map_zones": True` (v52 onwards, 2026-10-21). An older version re-run stays what it was.

- **Planning.** The search area loses both kinds. The headings, sweeps and coverage goals use the
  search area. Routes (approach, escape, stall breaker) use the walkable grid minus both kinds.
- **The start cell** is drawn from the largest connected part of the search area. A room sealed by
  a line is never the start.
- **Every walk click** is refused (reason `zone`) when any of these holds:
  - its destination is in a no-enter area (allowed only on the way out of the area the GM stands
    in);
  - the straight line from the GM to the destination crosses a line or passes through an area;
  - the client's own likely path does. That path is approximated by A* on the zone-free walkable
    grid, because the client paths on its own map, not ours.
- **Targets.** A dropped target's spot is banned for a while, as for any other drop.
  - A target standing in a no-enter area is dropped (`target_dropped`, why `zone`). It is still
    tracked, so the unit and risk checks keep seeing it.
  - A target in strike range is dropped too when its walk-in would cross a line or enter an area.
    The walk-in is the client's own path from the GM to the target.
  - The attack click and the burst's re-clicks check the walk-in again just before they fire.
- **Loot.** A loot cell inside an area, or across a line from the GM, is skipped.
- **The run's records.**
  - One `map_zones` event at the start: the file, its sha256, its reviewer, its items and the
    cells they take.
  - A `map_zones` block in the run summary, with the refusals counted.
