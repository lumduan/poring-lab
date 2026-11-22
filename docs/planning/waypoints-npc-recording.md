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

## Amendment 2 (2026-11-20 14:28 ICT from `date`): a prerequisite -- the map's NAME on the player's own client

- **Map-to-map walking needs to know which map she is on.** Today the map is told by the
  minimap's PICTURE against the lab's references (minimap_id).
- **On Batt's live client it does not read.** The 11-20 13:21 Run: "no map's picture matches the
  minimap (the best, gl_chyard's, 0.21; a map is named at 0.40)". The Run started on a warning
  only.
- **The fix fits this plan's recording:** while a person records a path, the lab learns THIS
  client's minimap picture of each map it crosses.
  - The map's name comes from the server-independent `/where` line (an ASCII map id and the
    cell, typed behind the UI gate) once per map, or from the recording's start map.
  - The pictures stay in that copy's data/ (client pixels, never committed), as the live HP
    font does.
- **The bar:** on the player's client, every map of a recorded path is named on 20 of 20 fresh
  arrivals, before step 2 (a map change) is tried.

## Amendment 3 (2026-11-21 22:28 ICT from `date`): Batt's decisions -- the map by `/where`, build in parallel, matpilot may look

- **The map's name (Amendment 2's prerequisite) is NOT learned from pictures.** Batt: "this is very
  easy: when the minimap changes, type `/where` and the map is known; no need to teach".
  - On a minimap CHANGE (its picture differs from the last frames' by a margin), the bot types
    `/where` behind the UI gate, with `/ex` before it (the client refuses one phrase typed more
    than three times in a row: where-position-fix).
  - It reads the reply's ASCII map id and cell from the chat. They are an id and digits, not a
    word of any language.
  - The 20-of-20 bar of Amendment 2 is replaced by: every map of a recorded path named by
    `/where` on 20 of 20 fresh arrivals.
- **The order:**
  - The path recorder and the /maps waypoint editor are built OFFLINE now, in parallel (Batt: "if
    free, do it in parallel").
  - The dev-lab steps (record / replay a path, an NPC talk) run when the dev queue is free ("when
    free, just do it, at a good moment").
  - The standing order for the dev lab (items -> cursor -> goblin) is unchanged.
- **matpilot may help:** Batt allows asking the matpilot session to look at the web pages or the
  live screen. Its answers are advice, adopted by a recorded amendment, never by its own edits
  here.

## Amendment 4 (SUPERSEDED by Amendment 5: the multi-map path file is gone; the code is now scripts/path_blocks.py, see Amendment 6) (2026-11-22 04:47 ICT from `date`): the path recorder's pure core is built (offline); questions for Batt

- **Built** (Amendment 3's "in parallel"): `scripts/path_record.py` + `test_path_record.py`
  (113 tests on synthetic grids; map_routes' 50 unchanged and passing). It does no live read,
  sends no input and writes no file.
  - A versioned path file (`poring-lab-path` v1): named legs, one per map, each with waypoints
    (x, y, arrival radius, mark) and how the map is left. The exit kinds are the flow IR's own
    words: walk_exit (a cell), npc_warp (a talk's name), item_warp, end.
  - **Thinning** raw reads into waypoints (Amendment 1 b): unconfirmed reads dropped; a point every
    10 cells, at turns over 40 degrees, at every map change and every mark; never two points
    closer than 3 cells except there. Every threshold is a setting with these as defaults.
  - **Leg proof** with map_routes' own functions (`route_grid`, `leg_path`, `closed_why`, ...):
    each point and segment is ok / broken / closed / unproven, for the editor to draw red.
  - **Edits** (move, insert, delete, radius, exit, rename) return a new path, re-validated.
  - **Walking:** `ahead` = map_routes' next / entry / resume rule with each point's own radius
    (Amendment 1 d), and a wrong map stops with the words "she is on X, the path expects Y".
  - Names in any script, stored as data and never turned into code.
- **Not built yet:** the live recording loop (selfpos reads, `/where` on a minimap change), the
  /maps editor UI, the NPC-talk recorder, the `walk_path` block.
- **Questions for Batt** (current behaviour in brackets; nothing decided silently):
  1. Which grid proves a path: the walk grid minus every warp span except the leg's own exit?
     [the caller chooses]
  2. Do a hunt map's zones apply to a path's legs? [only if passed]
  3. A map change with no recorded leave: take the nearest warp cell as the exit, or let the
     walker keep its heading until the map changes? [the last read cell, flagged for the person]
  4. item_warp: which item / function, and what if none is chosen? [optional]
  5. Joining a leg: the nearest point (map_routes' rule), or only its first point? [nearest]
  6. A restart mid-path on a later leg's map: start at that leg? [no: leg 0, else wrong map]
  7. A warp inside one map stays one leg (no "split a leg" edit yet).
  8. Over 1,000 points on a leg is refused; the live loop keeps the raw reads to re-thin.
  9. A path ends with `end`; "walk, then fly home" stays its own block.
  10. The default thresholds come from the committed routes' 10-12-cell legs; bar 1 (5 of 5
      replays) tests them.
  11. A mark is a flag, with no label.

## Amendment 5 (2026-11-22 07:54 ICT from `date`): Batt's design -- the recorder GENERATES BLOCKS in the map's own flow; nothing new

Batt, on Amendment 4 (2026-11-22 ~08:1x), confirmed after a restatement: "What we build is not a
new system. It makes waypoints from what we already have, the block coding in /flows of each map.
The system looks where the player walked and creates blocks in that map's flow, nothing more. Or
the user writes the blocks himself from the start, without walking, if he knows the way (A -> B,
short). In matpilot I did this too: the system is only a block generator. It is very simple." And:
"The user can edit and tune the walking path through the code blocks himself; we only make a tool
to create the blocks faster."

**The design (it replaces Amendment 4's multi-map path file):**
- **Recording = generating ordinary blocks.** The player walks; the tool thins the reads (Amendment
  1 b) and writes a run of `walk_to(x, y)` blocks (the palette's existing block, `nav.walk_to`)
  into the flow of the map she is on. The user edits them like any block, or writes them by hand.
- **One map, one flow.** Whatever map she is on, the bot runs that map's flow; a map change hands
  over to the next map's flow through the /maps links that exist already. No path spans maps; no
  "wrong map" state; no length limit beyond the map's own flow.
- **Off the route: GPS.** Knocked off by a monster, or any detour: rejoin at the nearest point
  ALONG the route's line (between two points too), ahead of where she was, and walk on from there.
  Never back to the start. A run of consecutive `walk_to` blocks is the route for this.
- **Batt's answers to Amendment 4's questions:**
  1. No warp cells cut from the grid: the user's line is followed. If a warp should be avoided, a
     no-enter zone does it. If she walks into a warp by mistake and the minimap changes, she walks
     back out.
  2. No-enter zones are respected; the user's waypoints come first; off the route = back to it.
  3. The exit is the nearest warp portal (option a): the game puts her on the new map next to the
     portal she came through.
  4. An item exit uses the flow's "home" key; none set = a warning at the start check.
  5. The nearest point, GPS-like (as above).
  6. Not a question any more: each map runs its own flow.
  7. GPS-like as well. Wings are never used inside a map (their destination cannot be chosen).
  8. Not an issue: a route lives in one map's flow.
  9. Gone: flying home is its own block.
  10. The thinning defaults stay settings.
  11. A mark becomes a note on its block.
- **Kept from the core already built (1424b810):** thinning, the walk proof of each segment on the
  walk grid with the zones (drawn red, a warning only), the GPS rejoin. Dropped: the multi-map path
  file, legs, exits and the wrong-map rule.

## Amendment 6 (2026-11-22 08:16 ICT from `date`): Amendment 5 built -- scripts/path_blocks.py; what is still open

- **Built** (af4cd0c6): `scripts/path_record.py` became `scripts/path_blocks.py` (81 tests in
  test_path_blocks.py; map_routes' 50 unchanged). Nothing else imported the old module.
  - `thin(reads)`: one run of points per map stay, in walking order.
  - `walk_blocks` / `run_blocks`: the studio's own `walk_to` statement, field for field (concept
    `nav.walk_to`, timeout 120 s); a mark becomes the block's note. Example, in the Python view:

        walk_to(cell("town_1", 55, 45))
        walk_to(cell("town_1", 85, 60), note="mark")

  - `propose(project, node, at, blocks)` -> a proposal; `apply(proposal, current)` makes the new
    project only on the user's click, and refuses if the project changed meanwhile. The input
    is never changed.
  - `check_route`: each segment ok / broken / unproven on the walk grid with the zones; no warp
    cell cut; a warning, never a refusal.
  - `routes_in` / `route_at`: a run of consecutive walk_to is one route. `rejoin(cells, here, last)`
    is the GPS rule: the nearest point (straight line) on the remaining line ahead of the last point
    passed. On a tie, the first equally near stretch, at its far end, so a loop or an out-and-back
    never skips ahead.
  - Dropped, as Amendment 5 says: the path file, legs, exits, names, WrongMap, the radius.
- **Open (Batt):**
  1. The studio's lint (`poring_flow/lint/simulate.py`, rule `routes`) already checks walk_to legs.
     It calls an unreachable cell and a line that crosses a warp ERRORS, which refuse the Run's
     start check. That contradicts "a warning only" and "no warp cutting".
  2. The rejoin distance is a straight line, so on a U-shaped route the nearest point can be behind
     a wall. A walk-distance rejoin is possible (one A* search per candidate).
  3. A run that ended in a map change keeps its last read cell, which may be the warp cell itself;
     a walk_to there changes the map in the middle of the block.
- Scope as built: inserts go into a map node's main tab at a top-level position; a route counts
  literal cells only (a walk_to with a variable cell ends it).

## Amendment 7 (2026-11-22 08:56 ICT from `date`): Batt's answers to Amendment 6's three questions (built)

Batt, 2026-11-22 (~08:3x): "ok" to each recommendation.
1. **The studio's lint, rule `routes`:** a walk_to line that crosses a warp is now a WARNING (it
   no longer stops the Run's start check): the user's line is followed, and a warp entered by
   mistake is walked back out of. A cell the bot cannot reach at all stays an ERROR (the bot would
   be stuck there). `poring_flow/lint/simulate.py`; a test pins both levels.
2. **The rejoin stays a straight-line nearest point** (fast). A walk-distance rejoin comes only if
   a real test shows a U-shaped route rejoining behind a wall.
3. **A run that ended in a map change leaves out its last point** (the cell read just before the
   change, often the warp itself): `run_blocks` drops it, and the map's own exit block
   (`take_exit`) crosses. A one-point stay before a change gives no block.
   `keep_exit_cell=True` keeps the raw line for a caller that wants it.


## Amendment 8 (2026-11-22 12:08 ICT from `date`): Batt's proposal -- routes from a RECORDING of the player's own play (video), recorded once, used twice

**Batt, 2026-11-22 (~11:5x), the proposal:** the route helper records the player's own play as
video. One recording serves two uses: the walk_to blocks (Amendment 5) and the future ML page
(training data). Frames whose `x y` read badly are fixed from the frames beside them. Before a
recording starts, the system checks the free disk and estimates how many minutes fit, so the user
can manage their own disk. Recordings live in a folder layout like the logs, with a way to delete
them when done.

**The agent's view (given before any work):** agree. Analysis runs offline on the raw recording,
so a better analysis can re-run on old recordings without walking the route again. The recorder
already exists: `record_session.py`, whose RDP default is GPU video (ADR-0024: 0.84 vs 5.69 GB/h
for PNG at 1 fps). PNG at 1080 and 1 fps measured 124.6 MB/min on ifH13 today.

**Batt's decisions (11-22 ~12:0x):**
1. **A notification on screen guides the player** step by step (e.g. "type /where now"), and is a
   way to talk to the player. The player, not the bot, types `/where` on a new map: the bot never
   types into the chat while a person plays. The reply is read from the video afterwards. If it
   is missing, the editor asks for the map from a picker.
   - Where it shows: in the CONSOLE page (web), over the stream view, plus an optional browser
     notification. It is never drawn on the Windows game window: ADR-0019 (Windows stays clean)
     needs a new ADR for any Windows-side piece. ➡️ CONFIRMED by Batt 2026-11-22 12:11 ICT
     ("agree, this is right").
2. **5 fps video for a route recording** (agreed). The gap between two frames is filled with the
   shortest walkable path on the map's GAT (`map_routes`).
3. **The recording starts only when the game UI is up** (Batt: "this is easy"):
   - Basic Information (the status window) and the chat window must be on screen, so a login
     screen is never recorded;
   - the minimap is optional. Indoor maps draw NO minimap on the lab's client, and so no `x y`
     readout (`selfpos.py`: "a map where the client draws no minimap"). TO TEST on the dev client
     before the design is fixed: which maps, and what the position source is there (the player's
     `/where`, guided by the notification).
   - Kept: recording only when the user presses Record, with a visible "recording" sign; other
     players' names and chat stay local, never shipped; nothing on Windows (the server records).
4. **Deleting is a user SETTING:** automatic (delete the video once its blocks are made) or manual
   (one at a time, with the space freed shown). A recording marked "keep" is never deleted
   automatically. The walk_to blocks live in the map's flow, so deleting the video loses no route.
5. **Order, in parallel with the item-model work** (Batt: "if it can run in parallel, just do it"):
   1. the offline pass on recordings: positions from the minimap readout, then smoothing over
      neighbouring frames, scored against packet truth (lab sessions). The sessions and the bars
      are pre-registered in a later amendment, before any score;
   2. the "Record route" button: the readiness check (decision 3), the disk check and the minutes
      estimate, the notifications;
   3. walk_to blocks from a recording (`path_blocks.py`, Amendments 5-7);
   4. the recordings page (list, size, keep, delete, the auto-delete setting), which the ML page
      reuses.
- **The folder layout** (like the logs; the root comes from the storage setting, no NAS assumed):

      <storage>/recordings/<YYYY-MM-DD>/<stamp>-<map>-route/
        manifest.json   format, fps, bytes, sha256, start/end, purpose (route / ml), keep,
                        split (train / held-out, decided before anyone looks)
        video ...       the recording (record_session.py's own files)
        events.jsonl    minimap-change marks, readiness, notifications shown, the /where replies read
        derived/        positions.jsonl (the smoothed track), blocks.json (the walk_to made)
      <storage>/recordings/index.json   what the page lists: size, age, purpose, keep

## Amendment 9 (2026-11-22 12:33 ICT from `date`, BEFORE any route recording): phase 1 built (`scripts/route_track.py`); its dev check; the score pre-registered

- **Built** (2b81c223; new files only, no existing module changed): `scripts/route_track.py` and
  47 tests (`services/backend/tests/test_route_track.py`; with path_blocks' and map_routes' tests,
  179 pass).
  - **The pure core**, `build_track(reads, grid, zones, settings)`, works on one map stay:
    - a read is a candidate only on a walkable cell;
    - it is ACCEPTED when its neighbours agree (consistent = `cheb <= max_speed * dt + slack`),
      voted twice so a good read beside a misread burst survives;
    - an out-and-back faster than walking is dropped as an `excursion`;
    - frames between two accepted reads are FILLED from `map_routes.leg_path`, timed by walk time;
    - a gap that is too long, a jump, or no path SPLITS the track;
    - `to_reads(map, segment)` gives path_blocks' `(t, map, x, y, confirmed)`;
    - path_blocks.thin splits only at a map change, so each segment is thinned on its own.
  - **Settings** (user settings, these defaults):
    - `max_speed` 10 cells/s (the default walk is ~6.7, plus speed effects);
    - `slack` 2 cells;
    - `window` 3 reads a side;
    - `max_gap_s` 2.0;
    - `min_support` 1 (PosConfirm's "another read agrees").
  - **The CLI:**
    - `reads SESSION` reads every 0.2 s with `selfpos.read_minimap(light=True)`; a 1080 frame
      goes through clientview's virtual client;
    - `track RAW --map` builds the track;
    - `check` compares it with the packet truth, reusing selfpos_calibrate's and selfpos_eval's
      functions unchanged.
- **Dev check (NOT a score; the reader's own calibration sessions, in-sample):**
  - The raw reads were already right: outdoor-a 6,001 standing frames 100 % exact;
    outdoor-b 99.28 % exact and 100 % within 1 (117 walking frames: 93.16 % exact, 100 % within 1).
  - The track dropped nothing, but there was also nothing wrong to drop.
  - Synthetic damage on outdoor-b's prt_fild08 stay (the raw file edited, dev only):
    - half the frames blanked: coverage 49.96 -> 100 %, within 1 100 %;
    - every 10th / 37th read shifted 30 / 20 cells: within 1 87.35 -> 100 %;
    - 3-frame misread bursts: 93.63 -> 100 %;
    - 6-frame bursts: 87.17 -> 99.28 % (23 of 24 caught).
    - Every dropped read was a real error (> 1 cell).
  - **Known limits:**
    - a fill over a > 1 s hole is timed proportionally, so a start or stop inside the gap misses
      (2 of 15 filled frames > 1 cell off at 1.2 s holes; none at 0.4 s);
    - a misread burst right before a REAL jump survives as its own segment (1 of 24).
- **The score, PRE-REGISTERED now (before any route recording exists; scored ONCE by a wrapper
  committed before the score):**
  - **Held-out:** the first 3 route recordings made after this amendment on the dev lab,
    `route-H1` .. `route-H3`:
    - 1080, 5 fps (`record_session.py --fps 5`, the RDP default video);
    - packets on (the lab sniffer: truth only, offline);
    - each walking for most of its time (>= 60 % walking frames by selfpos_eval's classes);
    - at least 2 outdoor maps in all;
    - one may cross an indoor map, which is reported apart (no readout there, decision 3).
    - A recording that misses these is void and replaced (the next name).
  - **Scored frames:** selfpos_eval's classes and exclusions (GM windows, map loading, frames
    without a true position), on maps whose client draws a minimap, in map stays cut by the
    PACKETS' map changes (the recorder's own cut is phase 2).
  - **Bars (pooled over the 3, walking frames, the TRACK):**
    - T1: within one cell >= 97 % (T0's walking bar, applied to the track);
    - T2: coverage (a read or filled cell) >= 95 %;
    - T3: the walk_to blocks made from each recording (path_blocks.thin per segment ->
      run_blocks) give no `routes` lint ERROR on the map (warnings allowed, Amendment 7).
  - **Reported beside them (no bar):** the raw reads' rates, standing frames, every source /
    drop / split count, and the indoor stay.

## Amendment 10 (2026-11-22 13:33 ICT from `date`): the indoor test (decision 3) and a bright-town finding, on the dev client at 1080

- **Indoors there is NO minimap window at all** (`@warp prt_in 134 106`, frame 13:3x): no picture,
  no `x y` readout. `selfpos.read_minimap` gives `no_glyph`. Basic Information and the chat
  window stay, so the readiness check (decision 3) passes indoors.
  - The position source indoors is the player's `/where`, which already works indoors (where@1 /
    where@2 on prt_church, docs/demonstrations.md 3.13 / 3.15).
  - The window's DISAPPEARANCE is itself a clear map-change cue for the notification ("type
    /where").
  - Between two `/where` replies indoors, the route is unknown from the minimap. A possible
    later source is the player's own walk clicks (the input log) projected to cells. It is not
    designed yet.
- **A bright town defeats the reader at 1080:** in Prontera at (156, 191) the readout
  `156 191` is plainly on screen. Two frames (13:26, 13:4x) both read None (`light_failed`:
  `uncovered_ink`). The bright paving shows through the translucent strip; this is the reader's
  known light-strip weak spot.
  - The same 1080 path (the virtual client, the minimap anchored top-right) reads xmas_dun02
    correctly on 3 of 3 frames: (93, 82).
  - The track cannot fix a stay where most reads abstain. Town stays may need the light reader's
    fix, or `/where` prompts. route-H1..H3 (Amendment 9) report town stays apart; the bars count
    the walking frames as pre-registered.
