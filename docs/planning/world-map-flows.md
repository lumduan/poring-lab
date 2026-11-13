---
doc_type: design
hypothesis: null
status: "BUILT 2026-11-10: round 1 bd317dd8 (the Maps page /maps; trace play + encounters, backend restarted 10:42; xmas_dun02's GAT in data/gat); round 2 510b1c89 (matpilot's review, 7 items, all verified by its re-run: section 10); round 3 26c880ca (4 small items + the graph fold, verified: section 11); round 4 d95b24b5 (a NaN console bug: section 12); round 5 (the other monsters as an option: section 13) not committed yet. Round 6 (2026-11-13, Batt: 'like n8n'; section 14): entry / exit ports, the Links panel, the world rules, the /flows binding strip, the NavBar order. Section 15 (2026-11-13 evening): ONE studio -- no Map tab on /flows, a functions tab, every key a function, xmas_dun02 an ordinary flow whose Run reads its keys from the functions."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [flows-studio.md, mw2-block-editor.md, blocks-from-hunt-flow.md, ADR-0020, ADR-0006, ADR-0016, ../../THIRD_PARTY.md, ../../services/frontend/src/components/maps/MapsApp.tsx, ../../packages/poring_flow/src/poring_flow/trace.py]
next_action: "Batt: try section 15.6 (one studio: the functions tab, xmas_dun02 as a map tab, Run reading its keys from the functions)."
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
- The NavBar: Console · Flows · **Maps** · Settings · Hardware. ➡️ SUPERSEDED 2026-11-13 (Batt):
  Console · Maps · Flows · Economy · Hardware · Settings (section 14).

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
- ➡️ SUPERSEDED 2026-11-13 (Batt: "take the Map tab off /flows"; section 15): /flows has no Map
  tab; the Maps page is the one map graph.
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

## 14. Round 6 (2026-11-13): "like n8n": entries, exits, the Links panel, the world rules

**Batt (2026-11-13, Thai, translated):**
1. "Reorder the NavBar: Console Maps Flows Economy Hardware Setting."
2. "/maps: make it like n8n. Show how each map links to which map, with the information below.
   Maps are bound to flows: map-A has map-A's flow; on /flows we choose the map, or click a map to
   see its flow. A map starts from its ENTRY: walking in from a warp, a Butterfly Wing (the town),
   a Kafra teleport's arrival all count as entries. We write blocks, but there must be an END
   condition, a way OUT of the map: walking to the coordinates of map B's entrance, a Butterfly
   Wing, a teleport. On /maps each map has any number of exit points: exit 1 links to map-B, exit 2
   to the town (a Butterfly Wing). And maybe a guard against walking into a teleport by accident:
   on a map we do not know, press a Butterfly Wing back to the save town. This value we can set as
   a global."
3. "/flows should say which map this flow is bound to, and where each exit goes. And why does the
   flow page have only these few blocks? Explain."

### 14.1 What the IR already had (no new IR)

- A map node IS a map block (section 4). Its EXITS are its `take_exit` statements, three authored
  kinds that are exactly Batt's: `walk_exit` (walk onto a warp cell), `npc_warp` (an NPC's menu:
  a warper, a Kafra teleport), `item_warp` (a Butterfly Wing to the save point), plus the derived
  `death_respawn`. Each names its target block and the ENTRY it lands on.
- An ENTRY is `{name, at, radius}`; its kind was never stored and is not needed: it is HOW the flow
  arrives there (lib/maps/links.ts): the start, each exit that targets it, a death's respawn.
- The guard: the engine already has the always-on `unexpected_map` event (always_on.py): on a map
  load it reads the position and relocates to that map's block; on a map with no block it STOPS
  (`relocate_no_block`). Batt's guard is that event made stricter, as the linter allows (same
  trigger, class and `then`, the body starting with the built-in's step).

### 14.2 What changed

| Part | Change |
|---|---|
| NavBar | Console · Maps · Flows · Economy · Hardware · Settings |
| Map node (MapsCanvas.tsx) | a card: map id, its flow (block, size, targets), lint / run; LEFT one port per entry with how the character arrives ("start · wing arrival from field_1 · respawn"); RIGHT one port per exit ("→ field_1 · talk to n_warper · o_to_field"), the derived respawn, and three "+" ports (walk to a warp, NPC / Kafra warp, Butterfly Wing) to drag a new exit |
| Edges (graph.ts) | from the exit's own port (`x:<path>`) onto the entry it lands on (`e:<entry>`); `in` (the node's head) for what names no entry |
| Any other map (new node) | the world rules; with the wing rule on, an orange edge "world rule: a Butterfly Wing home" to the save point's map node |
| Under the graph | Links / Map view tabs (remembered; a Simulate switches to Map view). Links: the selected map's Entries and Exits tables, or Every link, and the world rules' line |
| World rules (RulesPanel.tsx, lib/maps/rules.ts) | the save point (map, x, y), stated as `assert_save_point` at the START block's first step; on an unknown map: stop (the built-in) or a Butterfly Wing home |
| /flows (MapBinding.tsx) | a strip under the tabs: bound to map X (block B) · arrives: entry: how, from which map · exits: → map (how) · world rules; each map name opens its tab. A plain flow: "Not bound to a map", with a link to the two-map starter and to /maps |
| Load menu | "Starter: one map" renamed "Starter: one program (no map)": it was never bound to a map |

### 14.3 The unknown-map rule, as written into the flow

    @on(map_load_seen(), priority=CRITICAL, then=RELOCATE, max_per_run=3)
    def unexpected_map():
        read_position()
        if current_map() not in [map_id("field_1"), map_id("town_1")]:
            use_item(WING, note="the world rule: on an unknown map, a Butterfly Wing to the save point")

- The list is the flow's maps plus the stated save point's map (a wing there would land on the same
  map again). It follows the map nodes by itself (`refreshRule` on every edit, on /maps and /flows).
- At most 3 a run, then the run stops. After the wing, `relocate` picks the save town's map node;
  a town without a node stops the run there.
- The item is the flow's own Butterfly Wing exit's (e.g. the starter's `WING`), else item 602.
- A flow that writes a different `unexpected_map` is never overwritten unasked (a "Replace" button).

### 14.4 The save point, and ONE linter change (Batt's 2026-10-08 rule stands)

- Batt's rule: every wing before the save point is known is an ERROR (lint/simulate.py). The
  start block's first step is always "unknown", so an event's wing in ANY workflow was an error,
  even after an `assert_save_point` at that step, although the linter's own advice says "set it
  first, or assert it".
- Batt: "this value we can set as a global" -> the save point stated ONCE: an `assert_save_point`
  as the START block's FIRST step. **The linter change:** that one assertion counts from the run's
  first step (`SavePoint._start_state`). An assertion anywhere else counts from where it runs, as
  before, and every assertion stays the visible warning at approval.
- The fixture `services/frontend/src/lib/flow/fixtures/starter_world_rules.json` is rules.ts's
  output on the starter (links.test.ts checks the TypeScript makes exactly it):
  `packages/poring_flow/tests/test_world_rules.py`: canonical, **0 errors** (left: the
  assertion's own warning and the two lab binding gaps), the Python round-trips; WITHOUT the
  assertion the wing rule is an error again; an assertion after the first step does not count.

### 14.5 "Why does the flow page have only these few blocks?" (Batt's screenshot)

The flow in that browser was **"my_first_flow"**, Load ▸ "Starter: one map": a 3-step demo (wait
1 s, wait until a detector sees something, at most 30 s, stop). It is a PLAIN flow: one program,
no map blocks, so the Map picker said "none" and the Maps page had no maps to link. Its old menu
name was misleading (renamed, 14.2). The two-map starter (Load ▸ Starter: two maps) is the map
example. The live bot on xmas_dun02 is not an IR flow: "How the bot hunts here" shows the runner
(dungeon_hunt.py) as blocks made from its code, and the Run button plays it.
➡️ Since 2026-11-13 ~13:2x that flow is NAMED **xmas_dun02** (Batt: "name it after the map"): the
first entry of Load, `/flows?runner=xmas_dun02`, four tabs (the run, the knife swap, the respawn, the
safety rules); docs/console.md has the details. It stays a description of the runner, not an IR
flow: the IR's hunt block cannot hold the Knife swap's two halves (one at idle, one on every tick).
➡️ SUPERSEDED the same evening (section 15): xmas_dun02 is an ordinary IR flow; its map tab holds ONE
block, "hunt with the runner" (dungeon_hunt), and the runner's own blocks are its read-only inside.

### 14.6 Checks (2026-11-13)

- Frontend (frontend-dev): typecheck clean, lint clean, `pnpm test` 381 pass (9 new in
  `src/lib/maps/links.test.ts`; the graph test pins the new handles).
- poring_flow + the flows routes: 427 pass (3 new in test_world_rules.py); ruff and mypy clean.
- The dev server: /, /maps, /flows, /maps?node=unknown, /flows?block=field answer 200; the top bar
  reads Console, Maps, Flows, Economy, Hardware, Settings.
- Not run here: a browser (none on this host). The headless review is matpilot's.

### 14.7 For Batt to try

1. /maps (a new browser shows the two-map starter; else Load ▸ Starter: two maps): each map shows
   its entries left and its exits right; click field_1: the Links panel lists them.
2. Click **Any other map** ▸ state the save point (town_1, 40, 40) ▸ choose "Use a Butterfly
   Wing ...": an orange edge goes to town_1; the lint chip stays without an error.
3. /flows ▸ the field tab: the strip says "bound to map field_1 · arrives ... · exits → town_1".


### 14.8 matpilot's review of round 6 (received 2026-11-13 ~10:45) and what was done

Headless Chrome, a fresh profile, 1440 x 900 and 390 x 844. 0 console errors on every step; 13
warnings in step c; no NaN in any SVG attribute (round 4's bug is gone). Passed: the top bar, every
port dot on its card's edge, all six edges on the right dots, the Links tables, the world-rules line,
Simulate switching to Map view, the /flows strip (plain and bound), the renamed starter.

| # | Finding (matpilot's rank) | Cause | Done |
|---|---|---|---|
| 1 | HIGH: after "State it" the town_1 -> field_1 edge vanished until a reload; 12x React Flow error#008 for `x:town.3`; 1x for `rule:unknown` | an exit's handle id is its statement PATH, so the stated save point (a step inserted above the exit) renamed `town.2` to `town.3`, and React Flow kept the node's old handle list | every map node tells React Flow when its ports change (`useUpdateNodeInternals`, keyed by its handle ids); "Any other map" always renders its `out` handle (hidden while the rule is off). Paths stay the IR's address (lint, removeExit, the trace use them): stable exit ids would be an IR change, not done |
| 2 | HIGH: choosing the wing ended with 1 lint ERROR ("nothing sets it before maps.town.0") although the save point was stated | the BACKEND had not been restarted, so it ran the old linter; the new rule (14.4) was only in the host's code | guarded `restart:backend@30` 10:51 (ASSIST kept, interlock green); the backend's poring_flow has `_start_state`; the same flow (town_1 40 40 + the wing) lints 0 errors on that code. The chip now says "(checking…)" while a re-lint is pending (it showed the old result for ~3.5 s) |
| 3 | HIGH: at 1440 x 900 the graph was a 191 px strip (Links 452 px, mostly empty); one map in view; START / Login / Character took ~650 px; Fit View went to 0.41 (5 px text); at 390 only START and Login showed | the graph kept round 2's cap (`clamp(11rem, 32 %, 20rem)`, sized for the map view) and the fit starts at START | with Links under it the graph takes the height (`flex: 1`, min 18rem) and Links at most 40 %; a graph too big for the view opens on its MAPS (and Any other map); Fit is ours (the maps, never below 0.85); on a phone the graph is 24rem and Links as tall as its rows |
| 4 | MEDIUM: the minimap covered town_1's EXITS header; the attribution covered "+ Butterfly Wing" | top-right minimap, bottom-right attribution | minimap bottom-right, attribution top-left |
| 5 | MEDIUM: session edge labels under the cards ("en the cli", "cter s"); the rule edge's label 100 % under Any other map | the cards are wider than the gaps; Any other map sat under the maps | session labels above the session row; Any other map under the session row, left of the maps (its edge runs through open space); map rows 1.35x apart (taller cards) |
| 6 | LOW-MEDIUM: Login's server / account lines and Any other map's line cut off, no tooltip | one-line ellipsis | they wrap, and the Login lines have a title |
| 7 | LOW: a grey dot at each card's top-left that does nothing | the head's `in` handle (for what names no entry) | invisible, no pointer events |
| 8 | LOW: no gap between radio and words; "(the built-in, always on)" on a switchable radio | | a gap; "(the built-in default)" |

Asked of matpilot: a re-run of steps a and c (the edge after State it, the lint chip after the wing,
the graph's height and first view at both sizes).


### 14.9 matpilot's re-check (2026-11-13 ~11:00) and the last fixes

- VERIFIED by it: the edge stays after State it (x:town.3 -> field_1 e:arrival), the lint 0 errors
  after the wing ("(checking…)" for ~3 s), the graph 469 px at 1440 x 900 (was 191), no card under
  the minimap or the attribution, the wrapped lines, the hidden head dot, the radios.
- Left by it, done: the first view and "Fit the maps" fit the MAP cards only (Any other map, left
  of them, had stretched the box to the session row: field_1 was never in view); the handle refresh
  is a layout effect (1 error#008 was left after State it); the attribution top-right (top-left
  printed over "open the client").

## 15. One studio: every key a function, xmas_dun02 a map tab (2026-11-13 evening)

**Batt (2026-11-13, Thai, translated):** "Why does the xmas_dun02 flow have to be separate, not made
in /flows like my_first_flow? We just add a map named xmas_dun02, and add whatever block is missing.
Fly Wing and Butterfly Wing: don't write them fixed like that; write them as functions, and in the
function say which shortcut key F1-F9 to press: more flexible. The Knife swap too, as functions,
choosing which key to press; casting skills, anything: the same principle, make functions. Don't
forget we have Save and Load, so these can be shared, and we can keep global functions in a tab of
their own. In matpilot I made modules, and main joins all the flows together. And on /flows take the
Map tab off, so it does not duplicate /maps: /maps is the main one; each map, when opened, has its
own flow, and maybe a global flow every map shares, like a public class."

### 15.1 What plays in the game (unchanged, said plainly)

The flow engine (packages/poring_flow) SIMULATES only; ADR-0020's executor is not built. The game
is played by the runner `scripts/dungeon_hunt.py`. So the xmas_dun02 map tab does not turn the
runner's loop into editable blocks: it holds ONE block, **hunt with the runner (dungeon_hunt.py)**,
a task-level block like `hunt` (its parameters are a person's choices, its internals stay in the
engine). The runner's own blocks (the export, four tabs) are that block's **inside**, read only.
Everything AROUND it is ordinary blocks: the save point, the loop "while the bag is under 50 %",
the way home, the functions, the events.

### 15.2 The flow (lib/flow/starter.ts `xmasFlow`, fixtures/xmas_dun02_flow.json)

    def heal():           press_key("F1")
    def fly_wing():       press_key("F8")
    def butterfly_wing(): press_key("F9")
    def knife_on():       press_key("F4")
    def knife_back():     press_key("F5")

    @map_block(xmas_dun02, entry here: where she stands)
        assert_save_point(geffen 119 40)
        while weight_percent() < 50:
            dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back)
        take_exit(item_warp(by butterfly_wing -> geffen.save))

    @map_block(geffen, entry save: 119 40)
        stop("home")

(The Python view's exact spelling is the engine's: section 15.5.)

### 15.3 What changed

| Part | Change |
|---|---|
| /flows tabs | one per map block (the START map first), **every map** (the global events: "like a public class"), **functions**; the Map tab is gone (the Maps page is the map graph; "+ map block" stays) |
| Functions | a hat "function NAME ( )" on the functions tab = `Flow.procedures[NAME]` (the IR had procedures; the editor had only "call"); "call NAME ( )" on any tab |
| press key | a new catalogue block `press_key(key)`, F1-F9 (hotbar row 1), L1 concept `ui.press_hotkey`; insertable like use_item (Batt's Q17: a hotbar press) |
| Item warp by a function | `Exit.proc`: an item_warp takes an item OR a function (left out of the canonical JSON when absent: every older flow keeps its hash); "item warp: call butterfly_wing → geffen . save" |
| The runner's block | `dungeon_hunt(heal, fly, knife_on, knife_back)`: each role names a function that is exactly ONE press_key; only on a map that has a runner (today xmas_dun02) |
| Run | on a flow whose map holds that block: beside Simulate; it reads the five keys from the functions (lib/flow/functions.ts `runnerKeys`: the four roles + the item warp's function) and sends them with Run; the Run helper checks them as any setting (F1-F9, no clash) and applies them to that run only. The Run pane (drawer): the live run, the start checklist, the settings (the keys group says "your functions") |
| The FLOWS row | every flow by name: the one open, the ones KEPT in this browser (the shelf), the ready-made ones (my_first_workflow, xmas_dun02); switching keeps the one left |
| my_first_workflow | its wing is the function butterfly_wing (press F9); the world rule's wing calls it (`call butterfly_wing`) |
| /maps | Load ▸ xmas_dun02 opens the flow (the one before is kept); a map card's runner button reads "Inside the runner" |

### 15.4 Not done (each a next step, none decided silently)

- **Modules:** ONE functions tab. matpilot's several modules (tabs of functions) would need a module
  name per function: the IR has none (an IR change).
- **A map's own function** (same name, overriding the global one): the IR's procedures are global;
  a map uses another function by name instead (e.g. `heal_strong`).
- **Heal and escape as events:** the heal / Fly Wing thresholds stay settings (the Run pane, every
  map / this map); compiling an event "when hp_percent() < 40: call heal()" into the runner's numbers
  is not built.
- **The loop's 50 %** is the flow's own; the runner's weight exit is its setting (default 50 %).
  The two are not tied yet.
- The live block highlight runs on the runner's inside view, not on the studio's blocks.

### 15.5 The engine's side (packages/poring_flow, ADR-0020 Amendment C)

- Python view: `press_key("F8")`; `take_exit(item_warp(using=butterfly_wing, to=entry("geffen",
  "save")))` (a bare function name as the first argument is refused: "butterfly_wing is a function:
  item_warp(using=butterfly_wing, to=...)"); `dungeon_hunt(heal=heal, fly=fly_wing,
  knife_on=knife_on, knife_back=knife_back)`. All round-trip.
- ADR-0020 section 2.1 said "never a block: raw keys". Amendment C narrows it: `press_key` takes
  exactly the L2 hotbar keys F1-F9 (a guard test pins it and still bans key / press / chord /
  click); everything else of 2.1 stands.
- The catalogue (GET /flows/catalogue) gains param type `proc` (a function's name) and
  `runner_maps` (poring_flow/functions.py RUNNER_MAPS = ["xmas_dun02"], tested against
  scripts/flow_run.py FLOWS).
- Lint (lint/functions.py), all ERRORS: `exit_function` (the item warp's function is missing, a
  variable, or presses no key); `hunt_function` (a role's function is not exactly one press_key);
  `hotbar_keys` (two roles, or a role and the wing, on one key); `runner_map` (dungeon_hunt on a map
  without a runner, or outside a map block's steps). A key pressed by the wing exit's function is
  that Butterfly Wing everywhere: the save-point rule (14.4), relocating and exit placement treat it
  as use_item(WING). A press of any other key in an event that does not relocate is a WARNING.
- The simulators: an item warp by function is ONE item step (with its proc and key) then the exit;
  a wing press elsewhere (e.g. `call butterfly_wing` in an event) keeps its own map change.
- On the live backend (2026-11-13 19:02) the xmas_dun02 flow lints with 0 errors on the lab's data
  (left: the assertion's warning, map flags not extracted, one readiness item as hunt's).
- The live ticks (dungeon@9.45, docs/planning/player-mode.md): the Run pane's checklist is ticked
  from the screen by `dungeon_hunt.py check` (no input). The map's NAME is not read from pixels: a
  cell of another map can pass as xmas_dun02's open ground (Geffen 119, 40 does).
  ➡️ dungeon@9.46 (player-mode.md "The map's name from the minimap"): it is read from the
  minimap's picture now; the line ticks only on the run's map and a player start refuses another.

### 15.6 For Batt to try

1. /flows ▸ FLOWS row ▸ **xmas_dun02**: the tabs xmas_dun02 · geffen · every map · functions.
2. functions: change fly_wing's key to F6. xmas_dun02 ▸ Run pane: the keys line says "F6 fly_wing()".
3. Back on the FLOWS row ▸ my_first_workflow: your flow comes back as you left it.

