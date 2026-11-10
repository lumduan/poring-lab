---
doc_type: design
hypothesis: null
status: "BUILT 2026-11-10: round 1 bd317dd8 (the Maps page /maps; trace play + encounters, backend restarted 10:42; xmas_dun02's GAT in data/gat); round 2 510b1c89 (matpilot's review, 7 items, all verified by its re-run: section 10); round 3 26c880ca (4 small items + the graph fold, verified: section 11); round 4 d95b24b5 (a NaN console bug: section 12); round 5 (the other monsters as an option: section 13) not committed yet."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [flows-studio.md, mw2-block-editor.md, blocks-from-hunt-flow.md, ADR-0020, ADR-0006, ADR-0016, ../../THIRD_PARTY.md, ../../services/frontend/src/components/maps/MapsApp.tsx, ../../packages/poring_flow/src/poring_flow/trace.py]
next_action: "Parent: commit round 5; matpilot: a look at the decoration toggle (section 13) and a recount of the NaN messages during a folded run (expected 0)."
title: "The Maps page: the flow as a graph of maps, each map bound to its flow, and the bot walking them"
date: 2026-11-10
owner: Batt
---

# The Maps page (/maps)

**Batt (2026-11-10, translated):** "Besides /flows, design a map-flow page too -- call it 'map' or
anything that carries the meaning well. Start from login and character selection; make it a MOCK
for now -- we already have the Python code for this part (the bot uses it). In this map-flow use the
n8n / Node-RED way of placing blocks, like we did at the very start, because it is easy to read, and
one map links to many other maps. The current flow must be BOUND TO A MAP, like binding a program to
a robot in matpilot -- but here it is each map's flow: what to do in this map. We already have the
map data (xmas_dun02's walk grid, grey walkable / black blocked, the bot's walked trails). Use this
to SIMULATE the bot: e.g. walk from point a -> b -> c, like matpilot's mat page where you watch the
robot walk, but also simulate meeting monsters and talking to NPCs at the positions in the block
flow."

Nothing on /maps runs live: the green button is SIMULATE (no game, no input), Login and Choose
character are mocks, and the page reaches no executor, mux, agent channel or input path.

## 1. The name: "Maps", at /maps

- Batt's own word ("call it 'map'").
- matpilot's parallel: Blocks / Robots / **Mats** there, Flows / **Maps** here. The Mats page is
  where a learner watches the robot walk; Maps is where they watch the bot walk.
- "World" already means the STATIC DATA in this code (`WorldSource`, `GET /flows/world`,
  `sheet.World`, the context bar's "static data"): a page named World beside it would be ambiguous.
- The NavBar: Console · Flows · **Maps** · Settings · Hardware.

## 2. What Batt sees

```
┌ NavBar ──────────────────────────────────────────────────────────────────────────────────┐
│ Maps [SIMULATE only] my_first_workflow                         Load ▾  Save  [▶ Simulate] │
│ login (mock) lab-rathena · character (mock) the remembered slot · static data ▾ · maps 2 · lint │
│ ┌ + map   (drag from a port onto another map …) ─────────────────┐┌ Node | Run | Python ┐ │
│ │ (START)→[Login MOCK]→[Choose character MOCK]→[town_1]⇄[field_1] ││ the node's inspector │ │
│ ├ map ▾ town_1 · a simulation · fit 2× 4× ────────────────────────┤│ or the run: checks,  │ │
│ │  the walk grid; green walked routes; the bot; monsters; NPCs    ││ what happens, step   │ │
│ │        ⏮ ◀ [▶ Play] ▶ ───────●────── 12.4 s / 71.0 s  4×       ││ by step; or Python   │ │
│ └ legend ─────────────────────────────────────────────────────────┘└──────────────────────┘ │
│ Playing at 12.4 s of 71.0 s · town: walk to the NPC …                  [Map view] [Panel] │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

Tap by tap:
1. **Maps** in the NavBar. The graph shows START → Login → Choose character → the flow's maps (the
   two-map starter on a new browser: town_1 ⇄ field_1). The map view under it shows the first map's
   walk grid (grey walkable, dark blocked) with its NPCs (squares) and warps (rings).
2. **Login** (click it): the server list from config/environments.yaml. Only "Lab rAthena" can be
   chosen; the Thai-data lab server, both official servers and the community server are disabled,
   each with why (ADR-0006 / ADR-0016 / ADR-0019). The account is ro_agent's `which` (gm / player):
   "the lab account from the server" (.env). There is no id or password field anywhere.
3. **Choose character**: the slot (default: the one the client remembers, as the bot does) and an
   optional character name (enter_game's `char`).
4. **A map node**: its map id, its block, how many blocks its flow has, lint, the last run. **Open
   flow** (or double-click) opens that map's blocks on /flows; **▶ here** simulates from that map
   (no login). The panel shows /flows' own Inspect (name, map, entry, targets, ignore, zones, exits,
   events) plus "Open its flow ↗", "Simulate from here", "Show its map".
5. **Linking maps**: drag from a map's port (walk exit, npc warp, item warp) onto another map: an
   exit with placeholder details the linter names (fill them in the map's flow). One map may link
   to many. Select an exit and press Delete to remove it. **+ map** places a map node from the
   static data (section 6).
6. **▶ Simulate**: the run plays on the map view. The bot logs in (the two mock steps, 11 s), enters
   the first map, walks its routes (green behind it, dashed ahead), walks up to each monster
   (placed from the seed, its HP bar draining, then gone, a loot sparkle), stops next to each NPC
   with a speech bubble ("set the save point with … at (56, 44)"), and on a warp the map view
   switches to the next map while the graph's node glows and the exit edge thickens. Play / pause,
   the step before / the next step, the time slider, 1× to 16×, back to the start.
7. **Run** (the panel): start at START or at a map node, the monsters' seed, the time limit, a death
   at t (the respawn), then matpilot's checks (e.g. ✓ reached town, ✓ every exit arrived, ✓ met N
   monsters (placed from seed 1), ✗ never reached …) and **What happens**, every step with its time (click
   one to go there).
8. **Python** (the panel): `session.py (mock)`: the bot's real login calls the two mock nodes stand
   for; `<flow>.py`: the flow engine's Python (every map's flow is a `def` under `@map_block`; the
   selected map's def is scrolled into view); `<flow>.flow.json`.
9. **On /flows**: at the end of the tab row, **Map ▾** says which map this tab's flow is bound to
   (matpilot's Robot choice) and opens another map's flow; **◂ Maps** comes back with that map
   selected. The Map tab keeps its canvas and gains a link "The Maps page ↗".

## 3. The session mock (lib/maps/session.ts)

| Node | What the mock shows | The bot's real code (scripts/ro_agent.py) |
|---|---|---|
| START | the client open on its login screen | `session(name)` (the Agent + Screen) |
| Login | server (only lab-rathena selectable), account gm / player | `to_char_select(agent, screen, which)`: service select, the id and password from .env typed as a sensitive batch, Login, OK on the server list at once |
| Choose character | the remembered slot or slot N, optional name | `enter_game(agent, screen, which, char=None)`: Enter on the selected slot, online=1 in the DB, the chat window check |

- `login(agent, screen, which)` = both; `ro_agent.py login gm` runs it. ro_agent has NO slot click:
  a numbered slot is "selected first, by hand" in the mock's words.
- Times are illustrative (1 + 6 + 4 s); the real login waits on the client and the database.
- `packages/poring_flow/tests/test_maps_page.py` fails if ro_agent's signatures, its `.env` account
  prefixes, its `login` command or config/environments.yaml's ids and statuses stop matching what
  the mock says.
- Not read: settings/environments.json (the user-managed set). A server a person adds on the
  Settings page does not appear here until the list is updated (a known gap; the mock automates
  nothing either way).

## 4. Binding a flow to a map

- A map node IS a map block of the flow IR (`workflow.blocks[]`: its `map`, entries, targets,
  ignore, events, `main`). "Its flow" = the block's `main`, the blocks on its /flows tab. The IR,
  its hash and its JSON are unchanged (no new IR field: the session is the page's mock).
- The two pages share ONE flow: this browser's `poring-lab.flows.flow.v1` (and the static-data
  choice). Each page writes it at once when it links to the other, and when it unmounts.
- Exits use what the IR has: walk_exit (a warp portal, or a walk off the map's edge onto its warp
  cell), npc_warp (an NPC's menu path: a warper, or a Kafra teleport with its options), item_warp
  (a Butterfly Wing to the save point; a Fly Wing stays on the map, so it is no exit), and the
  derived death_respawn (to the save point's map).
- **/flows' Map tab: KEPT**, with a link to the Maps page (round 5: Batt wanted the map canvas
  first on /flows). It shows the event nodes the Maps page leaves out. Proposal for Batt: keep both
  for now; later either (a) the Map tab becomes a link only, or (b) /flows opens on the first map's
  blocks and the Maps page is the one map canvas.

## 5. The simulator (poring_flow.trace `play`, the browser's playback)

- **Backend (trace.py):** the trace gains `play`, the run IN ORDER: walk (its route), talk (the
  NPC's key and cell), menu (an option key), fight (the monster's species and cell, loot), item,
  loot, respawn, act, wait, exit (from block / map → to block / map / cell), arrive (a wing, a
  respawn). Each step has t0, t1, its map block and map. Bounded: 2000 steps, 20 000 cells.
- **Encounters** (`Scenario.encounters`, `seed`): OFF by default, so /flows' Simulate is unchanged
  except for the added list. The Maps page turns them on: each attack meets ONE monster, placed
  deterministically from the seed (the block's target species the sheet spawns, weighted by count;
  the block's `mob` when it names one; inside the spawn's area when the sheet has one), 2..R cells
  away on a walkable cell the walk grid reaches (R = `within`, at most 12); the bot walks up to the
  cell next to it, then the kill takes `attack_s`. A hunt block meets one monster per call. A
  SIMULATION: the monsters are placed, never seen.
- **Browser (lib/maps/play.ts, draw.ts):** a timeline (the session's mock steps, then `play`),
  the character's position at any time (a walk interpolated at RO's 150 ms a cell / 212 ms a
  diagonal, scaled to the step), what the map shows then, the words, the checks.
- **An older backend** (before the restart) refuses `encounters` / `seed` (422, extra inputs): the
  page runs again without them, and with no `play` it builds an APPROXIMATE timeline from the walked
  segments (each route once) and the exits, and says so.
- `lint/simulate.py` (the linter's layer 3) is not the editor's simulator; it was not changed.

## 6. xmas_dun02 (the Rogue's map)

- The local KB has its sheet (spawns: Christmas Cookie 1246, Cookie 1265, Cruiser 1248, Myst Case
  1249, Garm Baby 1515 x1, Stormy Knight 1251 x1 boss line).
- **Its walk grid is not in the backend's GAT mount** (`data/gat`, compose.dev.yaml `/lab-gat`): the
  extraction in /dev/shm has `xmas_dun02.gat`, `data/gat` does not. `python3 scripts/flows_gat.py`
  copies the extraction there (client-derived, gitignored; the backend reads it per request, no
  restart). Until then a node on xmas_dun02 has no entry cell ("anywhere") and the map view says
  "no walk grid".
- **Load ▸ One map from the lab data** (default xmas_dun02) and **+ map** build the node in the
  browser from GET /flows/world at run time (nothing derived is committed): the entry = the walkable
  cell nearest the centre; targets = the species spawned 2 or more times; ignored = boss lines and
  single spawns (on xmas_dun02: the four species / the Stormy Knight and the Garm Baby, the Rogue's
  own rule); its flow: attack the nearest target 5 times (within 9), then stop.
- Checked offline with the shm GAT (the simulator, not the page): entry (130, 130), five fights on
  Myst Case / Cookie / Cruiser cells, every walk on the grid.

## 7. Checks run (2026-11-10)

- Frontend (frontend-dev): `pnpm lint` clean, `pnpm typecheck` clean, `pnpm test` 263 pass (14 new
  in `src/lib/maps/maps.test.ts`: the session, its Python, the graph, placing a map node, the
  timeline, the pose, the overlays, the words and checks, the old-backend fallback, the drawing on a
  recording 2D context).
- A server-render smoke test of the real components (TypeScript's transpiler in the container's
  tmpfs, no browser): the Maps page, its Login / Character / Start / Run panels, the playback bar,
  the graph (5 nodes) and the map view, and /flows with `?block=field` (its field tab, the map
  picker, the Maps link) render without an error; no password input anywhere.
- poring_flow + the backend's flows routes: pytest (the new trace tests, test_maps_page.py,
  test_routes_flows.py's play-list test), ruff, mypy strict.
- `curl` /maps, /maps?node=block:town, /flows, /flows?block=field: 200; the lazy chunks of the maps
  components compiled in the dev server.
- **Not run: a browser** (none on this host): the canvas drawing runs in node against a recording
  context only.

## 8. What the parent does

1. A guarded backend restart (`python3 scripts/guarded_build.py --sustain 30 --spike 25
   restart:backend@30`): trace.py's play list and encounters. Until then the page falls back
   (section 5).
2. Optional, for xmas_dun02's walk grid: `python3 scripts/flows_gat.py` (section 6).
3. Commit (the parent's).

## 9. Open (for Batt)

➡️ ANSWERED by Batt (received by 13:38 ICT, 2026-11-10):
- the /flows Map tab: KEEP it in /flows ("เก็บไว้ที่ /flows ดีกว่า จะได้เป็นสัดส่วน": better kept in
  /flows, so each has its place). Both stay, as now;
- the other spawns wandering: "ทำเป็น option ไว้" (make it an option): a toggle, decoration
  only (round 5);
- the Login list from config/environments.yaml: "รับทราบ" (acknowledged); it stays.


- The /flows Map tab: keep both, or one of section 4's options.
- Monsters on the map view are PLACED (a seed), not seen: should the run also show the map's other
  spawns wandering (decoration only), or only the one met (now)?
- The session's server list mirrors config/environments.yaml, not the Settings page's set.
- Learner mode (ADR-0023, decided, not built) will change the Login node (a declared permission, the
  Windows host on the console); this mock follows today's rules.

## 10. Round 2 (2026-11-10, matpilot's headless-Chrome review, ranked)

matpilot checked /maps in headless Chrome: light and dark, 1280x800 and 390x844, no console
errors. Its verdict: the desktop run view matches its mats page (the playback bar, the run report,
the checks, the step list, the tabs, the legend, the active node, /flows' Map picker). Done, in its
order:

1. **Phone: Simulate jumped to the step list.** The step list's `scrollIntoView` also scrolled the
   PAGE, so the map and the playback bar ended above the screen.
   - The list now scrolls only inside itself.
   - On a phone, Simulate brings the MAP VIEW into view.
   - During a run the playback bar is fixed to the screen's bottom, and the page keeps room for it.
   - The Run report stays under the map (the phone's one column).
2. **The map was small on desktop** (a 360x270 canvas in a 922x294 stage).
   - "fit" is now the largest scale that shows the whole map in the stage, keeping its aspect.
     It is no longer a whole number of pixels a cell. `draw.fitScale`, measured by a
     ResizeObserver on the stage.
   - The grid is drawn at whole DEVICE pixels a cell (devicePixelRatio, up to 3), then scaled
     with smoothing off, so it stays sharp.
   - 2x and 4x zoom from the fit.
   - The graph now keeps about a third of the height (`clamp(11rem, 32%, 20rem)`) and the map view
     the rest (at least 22rem). A short window scrolls the stage instead of squeezing the map.
   - Example: town_1 (120x90) in a 922x360 stage is drawn at about 4 px a cell (about 475x356;
     it was 3 px, 360x270).
3. **Playback icons:**
   - the media glyphs U+23EE and U+23F8 were empty boxes in Chromium on Linux. They are now
     inline SVG icons (`components/maps/icons.tsx`), each with an aria-label, and so are the
     header's Simulate and the node buttons;
   - the step list's glyph marks are now coloured dots per kind;
   - a test fails on any media glyph or default-emoji character in the Maps components.
4. **Graph legibility:**
   - the fit never zooms below 0.85, so node text is 11 px or more (the node fonts were raised);
   - a graph wider than the view starts at its left (START) and pans;
   - only then does a small 120x80 minimap show (none otherwise);
   - when the playback's node is out of view, the graph centres it.
5. **Phone header:** Load and Save have their folder and save icons and aria-labels (the words
   stay for screen readers), as /flows' icon row has. Load's "▾" is an SVG caret.
6. **The first seconds of a run:** while the mock login runs, an overlay on the map says
   "Logging in… (a mock)" or "Entering the game…", what the step does, and "the character
   appears on town_1 at (40, 40) in N s".
7. **/flows details:**
   - the Python pane's file chips wrap (no second scrollbar); a long name is cut with "…";
   - the Map picker's first choice is "every map" (it was cut on a phone);
   - choosing it opens the Map tab.

matpilot's item 8 (the lint chip) is Batt's decision: left as it is.

Checks: pnpm lint and typecheck clean, pnpm test 265 pass (2 new: the fit, and the glyph and
label guard). A server-render smoke test passes: the playback bar (4 SVG icons, no media glyph,
every label), the Run panel (one dot a step), the Maps page header (labelled icons), the graph, the
map view, and /flows ("every map"). Not verifiable here: the real geometry and scrolling in a
browser (no browser on this host). matpilot's re-run is the visual check.

## 11. Round 3 (2026-11-10, matpilot's re-run)

matpilot re-ran round 2 (light 1280 DPR 1, dark 1280 DPR 2, light 390 DPR 2, dark 390 DPR 3, no
console errors) and VERIFIED section 10's seven items. Four small ones were left, plus one option:

1. **The MOCK badges** (and the FIRST badge) are 13 px, so 11 px at the fit's 0.85 zoom (they were
   12 px: 10.2 px).
2. **The phone's fixed playback bar:**
   - its background is opaque (var(--surface)), border and shadow kept;
   - the page ends with a spacer of bar + 16 px + the safe area, so its last fields scroll clear
     of the bar.
3. **The login overlay:**
   - it sits over the MAP itself (MatView's frame), no longer over the stage's empty top;
   - on a phone it is one or two lines: "Logging in… (a mock) the character appears on town_1
     (40, 40) in 9 s". The details stay in the step list.
4. **Zoom:** 2x and 4x open CENTRED, on the character during a run, else on the map's middle (they
   opened at the top-left).
5. **Option, done:** on a wide screen Simulate FOLDS the graph to its toolbar, so the map gets the
   height. The toolbar says "The graph is folded while the run plays · now: field (field_1)", and
   "Show the graph" brings it back ("Fold the graph" folds it again). A phone keeps its one column.

Checks:
- pnpm lint and typecheck clean; pnpm test 266 pass. The new test: every graph text rule is
  11 px or more at 0.85, the bar is opaque, the spacer's height is as specified.
- A server-render smoke test: the overlay inside the map's frame; the spacer; the graph open, with
  no fold button before a run.
- Not seen in a browser here: the fold, the centred zoom and the phone overlay (matpilot's eyes
  again).

## 12. Round 4 (2026-11-10): the NaN `<circle>` during a run

- **The bug:** React logged "Received NaN for the cx / cy / r attribute" during a run (matpilot
  counted 23 in the first 1.5 s, then 127).
- **The cause:** the only `<circle>` is React Flow's background dot (r = zoom / 2). While the graph
  is FOLDED (display: none, a 0 x 0 box), the follow-the-playback pan called `setCenter` with a
  300 ms animation. d3-zoom interpolates over the view's width, and with a width of 0 every frame
  is NaN (`log(0 / 0)`; reproduced in node: `[NaN, NaN, NaN]` at t = 0.5). So the zoom, and the
  dot, were NaN on every frame of each pan.
- **The fix:** the fit and the pan are pure functions in lib/maps/graph.ts (`fitViewport`,
  `followCentre`). They return null for a box with no size or for any non-finite number, and then
  nothing moves the view. Unfolding re-fits from the real size.
- **Tests:** 2 new unit tests (268 pass).

## 13. Round 5 (2026-11-10): the map's other monsters, as an option (Batt, section 9)

- **The toggle:** a checkbox at the START of the map view's legend row (under the map), labelled
  "Show the map's other monsters (decoration)". Its tooltip says what it is. It is OFF by default
  and remembered per browser (`poring-lab.maps.other-monsters.v1`). When on, the legend adds
  "other monsters (decoration)".
- **What it draws** (lib/maps/wander.ts, drawn by draw.ts):
  - the map's spawns from the static data the backend already gives (no backend change);
  - each species in proportion to its count, at most 40 on a map, at least one of each while the
    cap allows;
  - inside their spawn areas when the sheet has them; nothing without a walk grid;
  - small faint dots under the trails: no HP bar, no name.
- **How they move:** each one's walk is made ONCE: a random walk of 48 cells from the run's seed
  (the Run form's seed before a run), RO's 8 ways with no corner cutting, within 6 cells of its
  first cell, walked forth and back at 1 cell / 1.6 s. A frame only interpolates into a list made
  once (no allocation per frame).
- **What it is not:** never engaged; never in the step list, the checks or the Python; never
  drawn within one cell of the monster the run meets, while it is shown (from first seen to faded).
- **Tests:** 3 new tests (271 pass):
  - the cap and the shares;
  - the same seed gives the same walks, another seed others; every cell walkable; one cell a
    step; no diagonal through a corner; inside the area; one output list;
  - never at the met monster's cell during any meeting of the fixture's run; off draws none.


- **Round 5, matpilot's check (by 13:55 ICT):** PASSES.
  - It reads as decoration: 39 dots on xmas_dun02, faint in light and dark, all on walkable cells.
  - It does not change the run (the same steps, Python and checks with the box on or off).
  - It is remembered; 0 console errors.
  - Its one finding: on a phone the separate legend key wrapped the legend (73 -> 94 px, the map
    -6 %). Fixed by the parent: the faint dot sits in the checkbox label, the key is gone, and the
    label has a 24 px touch height (WCAG 2.2 2.5.8).
