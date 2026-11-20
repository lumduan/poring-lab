---
doc_type: plan
status: PROPOSED
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [roles-not-names.md, world-map-flows.md, project-model.md, ../../scripts/map_routes.py, ../../packages/poring_env/src/poring_env/npc_dialog.py, ../../scripts/talk1.py, ../../packages/poring_env/src/poring_env/selfpos.py]
next_action: "Queued AFTER roles-not-names.md steps 1-3 and BEFORE the ML page (Batt 2026-11-20). matpilot's design answer pending (asked 2026-11-20 ~14:3x)."
title: "Walk by recorded waypoints, map to map, and NPC talks recorded by demonstration, any language (plan)"
date: 2026-11-20
owner: Batt
---

# Waypoints and NPC talks, recorded by demonstration (plan, 2026-11-20)

## 1. What Batt asked (2026-11-20, translated)

> "Insert this BEFORE the ML page, after you finish 1-3. Next: making a path, or walking points.
> Today we have one map; next we try adding maps:
> - the bag full -> the bot uses a Butterfly Wing to the home map;
> - after selling, or storing at the Kafra, the bot walks back to xmas_dun02 by itself.
>
> The user only makes WAYPOINTS: the bot checks its own position, walks to a waypoint, then follows
> the waypoints, through each map. It completes our /maps page: it links the maps.
> Talk with matpilot about the waypoint page: it is the same design as building the flow of a
> robot on a simulated mat, but here the user walks the character on the real map and we keep the
> x, y waypoints.
> Also talking to NPCs, since some maps need an NPC to warp. Do not lock it to a language: users
> play in many languages. Check the window the user really talks in: when a window opens, a mouse
> click on next goes to the next window, but most users press Enter and the arrow keys. Our program
> remembers:
> - where the user talked to the NPC;
> - how many next / Enter;
> - which item of a list was chosen (up / down arrows, then Enter).
> When the talk is over, it becomes an NPC block the user can name.
> Once learned, users carry this to robot contests such as WRO: a robot works step by step like
> this. While they learn I will teach flowcharts too."

## 2. What the lab already has (to build on, not to redo)

| Piece | What it does today | Where |
|---|---|---|
| /maps | the project's map graph: entries and exits (a warp, an NPC / Kafra warp, a Butterfly Wing), world rules, Simulate on GAT walk grids | docs/console.md "Maps", world-map-flows.md, project-model.md |
| waypoint routes | reviewed per-map circuits (loop / path), each leg proven walkable on the route grid, walked with the runner's A* | scripts/map_routes.py, config/routes/<map>.yaml |
| her own cell | the minimap's x, y from pixels (JumpGuard; the re-read rule, ADR-0020 Amendment W) | poring_env/selfpos.py |
| NPC windows | the dialog (NEXT / CLOSE) and the menu (4 rows, the selected band, OK / Cancel) found by IMAGE under a mask, never by text (ADR-0012) | poring_env/npc_dialog.py, talk1.py |
| the human's input | the console's mux logs control keys (Enter, arrows) and clicks with their codes; a key that types a character is never logged with its code (ADR-0004 amendment d) | services/backend |
| the map's name | the minimap picture -> the map (minimap_id); warp watching | scripts/warp_watch.py |

## 3. What is new

1. **Record a path by walking.** On a "Record path" page the user presses Record and walks the
   character by hand.
   - The lab samples her cell (selfpos, each read confirmed) and the map's name.
   - It keeps a waypoint each time she has moved N cells, turns, or the map changes, plus any
     point the user marks.
   - A map change (a warp, an NPC warp) ends the leg and starts the next map's leg.
   - Stop gives a PATH: (map, x, y) points per map, plus how each map was left (a warp cell, an
     NPC talk, a wing). The user names it.
2. **Check and edit.** The points are drawn on the map view (the /maps Map view, the GAT walk
   grid).
   - Each leg is proven walkable as map_routes does; a broken leg is drawn red.
   - The user can drag, insert or delete a point.
3. **Walk a path** (a block: `walk_path("<name>")`).
   - The bot reads her cell, goes to the nearest point AHEAD on the path (map_routes.next_index's
     rule: never back to a passed point), then follows the points map to map.
   - An unread position is re-read by a step, as Amendment W does.
   - A map that is not the path's map: stop with the words "she is on <map>, the path expects
     <map>" (never a guess).
4. **Record an NPC talk** (any language).
   - While recording, the lab watches the NPC windows (npc_dialog) and the human's input from the
     mux (Enter, the arrows, clicks: their CODES and places, never typed text).
   - It records where she stood and which cell the user clicked (the NPC).
   - Then the sequence:
     - each NEXT, by Enter or a click on the NEXT button;
     - each menu, with the chosen ROW (the selected band's index after the arrows, or the clicked
       row) and its confirmation (Enter / OK);
     - the CLOSE.
   - It records no text: the row's position and the number of steps, so the same talk plays in
     any language.
   - Stop gives an NPC block (`talk_npc("<name>")`) the user names.
5. **Play an NPC talk.**
   - Walk next to the recorded place, click the NPC's cell, then play the steps.
   - Each step needs the window it expects (the dialog with NEXT, the menu with at least the
     recorded row). A different window, or none within its time, stops with the words
     ("the NPC showed no menu at step 3").
6. **The town routine on /maps.** The flows link the maps with these blocks: the hunt map's
   bag_full -> Butterfly Wing -> the town node:
   - `walk_path("to kafra")`, then `talk_npc("kafra store")`;
   - `walk_path("to xmas_dun02")`, with its NPC warp.
   The Kafra storage itself (moving items) is its own step later. The bag census (bag_count)
   counts what was stored.

## 4. Teaching (Batt: flowcharts, WRO)

- **Each recorded thing is a NAMED block.** It has a flowchart picture (start -> walk -> talk ->
  choice -> end), the same three views as the flows studio: blocks, flowchart, Python.
- **Language-free by construction:** a talk is "the 2nd row, then Enter", never a word.
- **matpilot's design is asked first** (a robot's route on a mat, recorded or programmed). The
  plan adopts its data shape and block names where they fit. Its answer goes here as an amendment.

## 5. Order and bars (fixed before building)

1. Record + check + edit a path on ONE map (the lab's prontera stand -> the Kafra). Bar: the
   recorded path replays to its last point, 5 of 5 times.
2. Walk a path across a map change (a warp cell). Bar: 5 of 5 reach the next map's first point.
3. Record + play an NPC talk (the lab's Kafra warp menu). Bar: 5 of 5 replays end on the
   recorded map, and the same recording plays on the Thai data client too (any language).
4. The town routine from a full bag (bag_full -> home -> Kafra -> back). Bar: 3 of 3 come back to
   the hunt map's first point.

Not now: the ML page (after this, Batt). The Kafra storage moves, selling (their own steps).

## Amendment 1 (2026-11-20 14:25 ICT from `date`): matpilot's design answer, and what this plan adopts

matpilot (its session, from lumduan/matpilot main 4022c87) answered the five questions. Its own
code: `src/lib/mats/path.ts`, `path-edit.ts`, `src/lib/blocks/incoming.ts`,
`add-to-tab.ts`, `src/lib/sim/spread.ts`; ADR 0016.
- **No recording by demonstration in matpilot.** A child taps points on the mat's picture.
  - The path is a list (point / straight / turn / wait / speed, at most 60).
  - `planPath` plans each point's moves from where the robot REALLY is after the moves before
    it, so rounding does not pile up.
  - The planned steps are inserted INLINE as ordinary move blocks (no live link back).
- **Its advice for us** (its views, adopted here as the plan's design):
  - a) **A named recording with a picker,** not inline expansion. A 3-map walk inline would be
    unreadable. `walk_path("to_town")` and `talk_npc("kafra store")` take a picker of the
    recorded names; the waypoints show and edit in their own view.
  - b) **Record raw reads, then THIN them** (drop points closer than a minimum step; keep turns and
    map changes; matpilot's MIN_SEGMENT_MM). Show the thinned path for editing before saving.
    Every waypoint carries its map's name and an ARRIVAL RADIUS.
  - c) **Plan each leg from the CURRENT read, never from the plan** (planPath's lesson).
  - d) **A waypoint is a checkpoint with a radius.** On re-localizing, resume at the nearest
    waypoint AHEAD in path order (already map_routes.next_index's rule), never the nearest by
    distance.
  - e) **Landmarks over digits:** a map change, a warp's arrival cell, an NPC's dialog are hard
    re-sync points.
  - f) **A LOST state with a time box,** then the existing recovery (a Fly Wing). The learner sees
    it as a block ("if lost for 10 s: ...").
  - g) **The flowchart READ-ONLY,** generated from the same structure as the Python (a box per
    block, a diamond per if / until / while). Never a third editable view (three-way sync).
- **Its UI lessons** (from a child using it): pictures and handles first, exact numbers for quick
  changes; a simple mode that still works; nothing changes in a program without a click (offered
  like a paste, with Undo and Dismiss).
- **Its license:** MIT, "Copyright (c) 2026 Sarat Sonsuk" (LICENSE at 4022c87). A port of its code
  is recorded in THIRD_PARTY.md first (rule 4's reuse rule).
