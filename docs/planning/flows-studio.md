---
doc_type: design
hypothesis: null
status: "BUILT 2026-11-09: round 1 2efe641a (backend restarted 16:21; matpilot's headless-Chrome side-by-side matched on desktop); round 2 a06076e1 (the Python in the blocks' words, Config constants, the phone height, Results, no dev indicator, an app icon; backend restarted 17:23 ICT)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0020, world-map-flows.md, mw2-block-editor.md, blocks-from-hunt-flow.md, xmas02-detector.md, stormy-knight-recognizer.md, orclord-recognizer.md, ../../THIRD_PARTY.md, ../../services/frontend/src/components/flows/FlowsApp.tsx, ../../packages/poring_flow/src/poring_flow/models.yaml]
next_action: "matpilot re-runs its side-by-side on round 2 (asked 17:23 ICT; section 8's checklist). For Batt: the import line and try/finally in Main (section 3 / 8 proposals). Open: section 7."
title: "The /flows studio: matpilot's /blocks layout, the Python side by side, the trained models as blocks"
date: 2026-11-09
owner: Batt
---

# The /flows studio

**Batt (2026-11-09, translated):** "Put /flows in the navbar [done, 6c02492c]. I want a layout like
matpilot.org/blocks, which I already use to teach kids, so I am familiar with it and learners can go
on to real-world robots without learning much more: that is my purpose. The key is Python code
shown side by side. Use matpilot's colour theme. Design the trained model files as blocks. Other
things like talking to an NPC or walking probably have old blocks already."

Nothing on /flows runs live, before or after this change: the green button is SIMULATE (no game,
no input), and the page reaches no executor, mux, agent channel or input path.

## 1. The layout (matpilot's BlocksApp, MIT, commit d639909)

```
┌ NavBar (unchanged) ───────────────────────────────────────────────────────────────┐
│ Flows  [SIMULATE only]  my_first_flow     [Blocks|Python]  Load Save Start over [▶ Simulate] │  header
│ (notice: "Opened … [Undo] [x]")                                                   │  only when needed
│ flow: plain (one main) · static data [local ▾] · lint: lint ok · hash 3f2a…       │  context bar
│ ┌ main │ events ─────────────────────────────────┐┌ Python ─────────── [Copy] [x]┐ │
│ │ Search  ┌──────────────┐                 (↶)(↷) ││ my_first_flow.py | .flow.json│ │
│ │ Movement│ when the program starts       │       ││  3 # --- Config ------------ │ │
│ │ Actions │   wait 1 seconds              │       ││  4 FLOW_NAME = "my_first_…"  │ │
│ │ Control │   wait until (detector v1 …)  │       ││  …                           │ │
│ │ …       │   stop done                   │       ││ 12 # --- Main -------------- │ │
│ └─────────┴───────────────────────────────┘       │└──────────────────────────────┘ │
│ ┌ Inspect ┐┌ Lint ┐┌ Results ┐┌ Path map ┐┌ Hunt rules ┐    drawer, when a pane is on │
│ Fix before simulating: … · Lint errors: … · Not running (the faded blocks): …       │  problems
│ Ready. Press Simulate…                   (Python)(Inspect)(Lint)(Results)(Path map) │  status footer
└───────────────────────────────────────────────────────────────────────────────────┘
```

- **The page column** (`app/flows/page.tsx`): NavBar + the studio in a `100dvh` flex column; the
  studio takes the rest (`min-height: 30rem`).
- **Header:** title, a SIMULATE-only pill, the flow's name; the Blocks | Python switch (Python =
  the code over the whole canvas, z-index 80 above Blockly's toolbox at 70); Load (a menu: a
  `.json` file, Batt's sample, a new workflow, the starter), Save (downloads the IR JSON), Start
  over (confirm, then the starter, with Undo), and the big green **Simulate** (`--run-bg`).
- **Notices:** only when there is something to say; a replaced flow gets **Undo** and folds away
  after 12 s; errors stay until hidden.
- **Context bar** (matpilot's device bar): the flow's shape, the static-data source (moved here
  from the old header), the lint summary, the flow hash.
- **Canvas:** a tab bar, then the blocks. Tabs: `main` + `events` for a plain flow; `Map` (the
  workflow canvas of map blocks and exits, React Flow) + one tab per map block + `events` for a
  workflow; `+ map block` adds a block and opens its tab. The Blockly toolbox is on the left with a
  **search box** as its first row (matpilot's search.ts, ported); undo / redo float top right.
- **Python side pane:** `clamp(18rem, 30vw, 28rem)`, header "Python" + Copy + close, file pills
  `<name>.py` / `<name>.flow.json` (the JSON view of the old page lives here now). **Open by
  default at widths >= 48rem** (Batt: side by side is the key), closed on a phone.
- **Drawer:** the output panes, `clamp(12rem, 36vh, 26rem)`, side by side (1-3 columns; 4-5 wrap).
- **Problems under the blocks:** "Fix before simulating" (blocks that cannot become the IR; Simulate
  is disabled until they are fixed), "Lint errors" (Simulate still runs: a run is never approved
  with them), "Not running (the faded blocks)" in words, e.g. *“walk to prontera x 150 y 180” is not
  attached to “when the program starts”, so it does not run.* Each line is a button that selects
  and shows its block (a lint error opens its tab first).
- **Status footer:** a sentence ("Ready. Press Simulate…"), toggles with `aria-pressed`, each
  remembered per browser (`poring-lab.flows.*.v1`, every localStorage access wrapped).
- **Narrow (< 48rem):** icon-only file buttons, the Python pane becomes a bottom sheet (55 %), the
  drawer 45vh with panes stacked, the status sentence on its own line. ➡️ Round 2 (section 8): one
  header row with ▶, the NavBar in one row, a scrolling context bar, the footer's "More ▾".

**What a learner sees first** (➡️ since round 5, section 11: the Map tab of a two-map starter): the header, the tab `main`, the starter program (when the program
starts: wait 1 seconds; wait until detector v1 sees monster, at most 30 s; stop done) and its Python
beside it. A browser's last flow is restored instead when it has one (checked like an imported
file; a broken one gives the starter and a notice).

**Every feature of the old page, and where it is now:**

| Old page | Studio |
|---|---|
| workflow canvas (map nodes, exits, events nodes, status lines, minimap) | the **Map** tab (workflow flows) |
| double-click a node → a full-screen Blockly modal with Apply / Close | the node's **tab**; edits apply live (no Apply step) |
| Inspect tab (map block props, run settings, static data, Simulate this node, Start here, Delete) | **Inspect** pane (follows the tab, or the node clicked on the Map tab) |
| Lint tab | **Lint** pane + errors under the blocks + the context bar's summary |
| Simulate tab + its path maps | the green **Simulate** runs it; the **Results** pane (its form, + a detector sighting row) and the **Path map** pane |
| JSON tab | the `.flow.json` pill in the Python pane |
| Python tab (hidden) | the **Python pane beside the blocks**, and the full Python view |
| Load sample / New / Import JSON / Export JSON | **Load** menu (sample, a new workflow, the starter, a file) / **Save** |
| "+ Map block" | `+ map block` in the tab bar |
| static data select | the context bar |
| hunt rules panel (inside the modal) | **Hunt rules** pane (when the catalogue has them) |
| Zones layer (full-window overlay) | unchanged: still a full-window dark overlay, opened from Inspect (it is a drawing tool, not a pane; it did not fit the drawer's height) |

## 2. The colours (matpilot's theme)

- Page tokens on the studio root, light then dark under `prefers-color-scheme` (studio.css): the
  brief's values exactly (`--bg`, `--surface`, `--text`, `--muted`, `--border`, `--accent`,
  `--run-bg`, the ok / warn / error / neutral triples, system font stacks).
- Blockly (lib/flow/theme.ts, copied from matpilot's `colours.ts` + `theme.ts` with the MIT notice):
  MatPilot's category colours, its block and category style names (start / hat blocks with
  `hat: 'cap'`), its font style, two themes on `Blockly.Themes.Classic` (light / dark component
  styles), following the system's mode live. Inject: `zelos`, sounds off, trashcan, zoom controls,
  the wheel SCROLLS (never zooms), grid 24 / 2, media self-hosted.
- Our blocks onto matpilot's categories (only words, colours and the toolbox changed; the block
  TYPES and the IR did not):

| Toolbox (matpilot's order) | Our blocks | Colour |
|---|---|---|
| Search | the search box | — |
| Movement | walk to, hunt (the map's targets); in a map block also the three exits | `#a21caf` |
| Actions | talk to the NPC, choose menu option, use item, open window | output `#1d4ed8` |
| Control | wait N seconds, wait until, repeat, while, stop, break, continue; the "when …" event hat | flow `#b45309` |
| Conditions | if / else, compare, and / or, not, OK, an action's outcome | flow `#b45309` |
| Sensors | detector sees, detector count, wait until detector sees; sensor expressions | input `#0e7490` |
| Operators | expression blocks (numbers, arithmetic) | data `#15803d` |
| Variables | set | `#be185d` |
| Functions | call | `#4338ca` |
| Advanced | More skills (every other catalogue block), Map events (extend, disable) | other / setup |

"When the program starts" is our `main` hat (a map block's: "when the flow arrives on <block>"),
in flow colour with the cap.

## 3. The Python pane, and the Python's shape

- **Source:** the backend's canonical Python view (`POST /flows/python`, `pyview.print_flow`), the
  same text the importer parses back. The page asks again after every converted edit (350 ms after
  the last one, one request in flight, the latest flow wins). The route has its **own rate budget**
  since this change (120 a minute; lint and simulate keep their 20), and a "rate_limited" answer
  waits 5 s and retries with the latest flow.
- **CodeView** (matpilot's, ported): a `<pre>` with a line-number gutter, the error line marked,
  React text spans only (never innerHTML). **Colours by our own tokenizer** (`lib/flow/pycolor.ts`,
  no new dependency: matpilot's @lezer/python is not added): MatPilot's token kinds and rules
  (control words, keywords, a name before `(` a function, `def` / `class` names, ALL_CAPS
  constants, strings with escapes and prefixes and triple quotes, numbers, comments, brackets by
  depth), CSS variables `--py-*` as VS Code Light+ / Dark+.
- **Copy:** `navigator.clipboard.writeText`; the LAN page is not a secure origin, so where the
  browser refuses, the code is SELECTED and a notice says to press Ctrl+C (⌘C).

**The shape decision: DONE as section comments.** `print_flow` now heads each part as matpilot's
generator does (`# --- Config ---…`, 76 characters): **Config** (the `flow(...)` head; ➡️ since
round 2 UPPER_CASE constants, section 8), **Setup**
(the variables), **Functions** (procedures), **Map blocks**, **Events** (global handlers and map
events), **Main** (a plain flow's statements); an empty part has no heading. They are comments, so
the parser drops them and every round trip holds (IR → Python → IR identical; canonical Python →
IR → Python identical). Updated honestly: the canonical fixture `hunt_field.flow` (two heading
lines added) and `test_routes_flows.py` (the view now starts with `# --- Config ---`); new tests in
`tests/test_models.py`. Nothing else asserted the old first line.

**Not done: matpilot's `try:` / `finally:` around Main** (its `finally` stops every motor). It is a
larger change, proposed here for Batt:
- what would change: the restricted Python would accept ONE fixed form at the end, `try:` + the
  main body + `finally:` + a fixed `stop_everything()` (or the printer would only print it);
- what breaks: the allow-list (`ast.Try` is refused today, and the hostile corpus pins that), the
  parser's main-body rules, the printer's chunking, every canonical fixture with a main, and the
  LLM drafter's feedback grammar. The IR has no "finally": the executor already releases
  everything at every stop (ADR-0020 section 6), so the form would be display-only or a new IR
  field. Neither is needed for the side-by-side view.

## 4. The trained models as blocks (ADR-0020 Amendment B)

| Block (Sensors, `#0e7490`) | Words | IR (an ordinary `Sense`) | Python view |
|---|---|---|---|
| question, hexagon, Boolean | "[eye] detector `v1 ▾` sees `monster ▾`" | `detector_sees(model, label)` | `detector_sees("v1", "monster")` |
| value, round, Number | "[eye] detector `xmas02 ▾` count of `cookie xmas ▾`" | `detector_count(model, label)` | `detector_count("xmas02", "cookie_xmas")` |
| (a toolbox preset) | "wait until (detector … sees …) at most 10 s" | the existing `wait_until` + the question | `wait_until(detector_sees(...), timeout_s=10)` |

- **No IR change:** two catalogue sensors (`blocks.yaml`) with two text parameters, `model` and
  `label`. IR 2, its JSON Schema, every flow hash and the Python grammar are unchanged (the schema
  drift test stays green with nothing regenerated).
- **The catalogue:** `packages/poring_flow/src/poring_flow/models.yaml` (`models.py`), served in
  `GET /flows/catalogue` as `models`. Each fact is copied from where the repo records it, and
  `tests/test_models.py` reads those sources (`scripts/unit_detector.py`, `scripts/mvp_profiles.py`,
  `scripts/mvp_watch.py`, `config/detector/classes-xmas02.json`) and fails on any difference:

| id | kind | status | sha256 | maps | classes |
|---|---|---|---|---|---|
| `v1` | detector | live (2026-10-13) | `32b448a1d197` | every map | player, monster, npc |
| `xmas02` | detector | live (2026-11-07) | `293dca922e3e` | xmas_dun02 | player, mystcase, cruiser, cookie, cookie_xmas (npc, warp: in the model, trained on no example) |
| `stormy-v1` | boss recognizer | **not adopted** (round 1 failed, 2026-11-09) | `a1287571e264` | xmas_dun02 | party (1251, 1515, 1607) |
| `orclord-v1` | boss recognizer | **not adopted** (flee proof: no verdict) | `43179452d01f` | gef_fild10 | party (1190, 1189, 1473) |

- **Not offered as working sensors:** the model menu lists only LIVE models (a count only
  detectors); the not-adopted ones are a text line in the Sensors category. A flow that names one
  anyway (an imported file) keeps it, shown "(not adopted)", and the linter refuses it.
- **The linter** (`lint/detectors.py`, layer 1): `detector_literal` (error: model and class written
  as text), `detector_model` (error: in the catalogue), `detector_not_adopted` (error),
  `detector_class` (error: one of the model's trained classes; an empty class "never fires"),
  `detector_count_kind` (error: a recognizer does not count), `detector_map` (warning: a model
  trained for some maps, read in a map block on another map).
- **SIMULATE:** a detector is a scenario input, as `sees` is: `Change.detects`,
  `"<model>/<class>" -> boxes from t on`; every pair a flow reads starts at 0 (the detector sees
  nothing until the scenario says so). The Simulate pane has one sighting row (t, model, class,
  boxes).
- **Not built: "confidence of <class> (%)".** Our detectors give a score per BOX after a 0.25
  confidence cut and NMS; a per-class frame confidence is not something the models report, and a
  learner would read it as a calibrated probability. Left out on purpose.
- **Left out of the catalogue:** gef10 round 2 (did not pass; its 26 class names live only in the
  model's local sidecar, never committed) and v0 (v1's rollback).

## 5. Checks run (2026-11-09)

- `docker exec -w /app poring-lab-frontend-dev-1 corepack pnpm typecheck` / `lint` (clean), `test`
  (247 pass: 217 before; new pycolor 8, studio 11, blockly_headless 6, blocks 4, editor_css 1).
- `blockly_headless.test.ts` runs the REAL Blockly 13 headless in node: every block type, every
  toolbox block, IR → Blockly → IR exact for the fixtures, the starter and a flow with model blocks
  (values the menus do not offer kept), the model / class menus, the class following the model, the
  themes and the search row registered.
- poring_flow + backend flows tests (`pytest`), `ruff check`, `ruff format --check`, `mypy` strict.
- The lazily loaded chunks of /flows compiled in the dev server with no error (fetched, scanned).
- **Not run: a browser.** The host has none; the matpilot session's headless-Chrome side-by-side
  (light and dark, 1280 px and 390 px) is the visual check.

## 6. What the parent does to see it

1. Restart the backend (a guarded `restart:backend`): the new sensors, the lint rules, the model
   catalogue, the Python sections and the Python route's own budget are host source the backend
   imports at start. Until then the page works but the catalogue has no `models`, lint names the
   detector sensors unknown, and the Python has no section headings.
2. Open http://192.168.1.228:3000/flows (the dev server already serves the working tree).

## 7. Open

- **Per-tab workspaces:** a tab's workspace is made when the tab opens, so undo does not cross a tab
  switch, and a tab whose blocks cannot become the IR cannot be left (a notice says why) instead of
  keeping its broken blocks. matpilot keeps every tab's workspace alive; that is the next step.
- **Procedures as tabs** (matpilot's function tabs): procedures are in the IR but have no tab yet;
  `call` names one.
- **The Zones layer** stays a dark full-window overlay (above).
- **`try` / `finally`** (section 3): Batt's call.
- **Python import** (editing the Python and turning it back into blocks, matpilot's "Edit"): waits
  for ADR-0020 F3's sandbox, as before.

## 8. Round 2 (2026-11-09 afternoon: matpilot's side-by-side review, ranked)

matpilot's headless Chrome against /blocks (light / dark, 1280 x 800 and 390 x 844) found the
desktop geometry and colours MATCH (the Python pane 384 px at x = 896, the toolbox 123 px, the
header, zelos, the block colours, the cap hat, the search row, the grid, dark mode, the code view,
the detector hexagon, the bottom sheet). Its ranked list, and what was done:

1. **The Python in each block's own words** (pyview, printer sugar the parser reads back):
   - "wait 1 seconds" prints `wait(1)` (was `wait_until(False, timeout_s=1.0)`); the parser reads
     `wait(N)` as the same IR. With an outcome it keeps `R = wait_until(False, timeout_s=N)`
     (`R = wait(1)` is refused, with that hint). `wait` is a reserved helper name.
   - Every SECONDS field (timeouts, cooldowns, `bounded(max_s=)`) prints whole seconds without
     ".0": `wait_until(X, timeout_s=30)`. The fields are floats, so 30 reads back as 30.0: the IR,
     its JSON and its hash are unchanged. Literal VALUES keep their type (an int stays an int).
   - The other blocks were checked against their words: `walk_to(cell(...))`,
     `talk_npc(npc(...))`, `choose_menu(option(...))`, `use_item(...)`, `open_window(window(...))`,
     `stop("done")`, `for _ in range(3):` (repeat), `while ...:`, `X = ...` (set), `proc()` (call),
     `take_exit(...)`, `detector_sees(...)`: each one line a learner can connect to its block; no
     other sugar was needed.
2. **A real program's shape:** DONE for the header and the Config.
   - The first line is `# Made by poring-lab from blocks. The flow engine reads this Python; it
     never runs it.`
   - The Config section is UPPER_CASE constants, one per line: `FLOW_NAME`, `DESCRIPTION`,
     `IR_VERSION`, `MAX_RUNTIME_S`, `WHERE_BUDGET`, `RUN_UNTIL_STOPPED`, `START`, `STOP_WHEN`,
     `ASSUMES`, `CLIENT`, `SERVER`, `LOCALE`, `PATH` (each only when the old call printed it).
   - The parser reads both the constants and the old `flow(...)` call (every committed source,
     the hostile corpus and the LLM-facing grammar keep working). A flow with a VARIABLE named like
     a constant keeps the `flow(...)` call, so its Python still reads back exactly (tested).
   - **NOT done: the import line.** There is no module a learner could import: the flow engine
     parses this Python and never runs it, so `from ... import *` would teach a false fact.
     Proposal: print it once an executor or an SDK a learner can run exists (MW3), naming that
     module; until then the first comment line says what the file is.
   - Evidence: `tests/test_models.py`:
     - every committed `.flow` source, the sample and the starter go IR -> Python -> IR identical,
       with the same `flow_hash`, and the canonical Python is stable;
     - `flow(...)` and the constants give the same flow and hash;
     - `wait(N)` and `wait_until(False, ...)` give the same IR and hash;
     - whole seconds read back as the same float.
     All of test_pyview (round trips, the hostile corpus) passes unchanged. Updated honestly:
     hunt_field.flow (canonical: regenerated), test_where (`WHERE_BUDGET = 3`),
     test_lint_zones_hunt (its server swap now edits `SERVER = ...`), test_routes_flows (the
     first line).
3. **Phone height (390 x 844):**
   - (a) the NavBar (every page): under 48rem one row, the pages in a "Flows ▾" menu, the mode
     badge as its LED only (colour and pulse; the word stays for screen readers and in its
     tooltip);
   - (b) the studio header is ONE row on a phone: Blocks | Python, the Load / Save / Start over
     icons, ▶ Simulate (its word kept for screen readers); the brand is left to the NavBar;
   - (c) the context bar is one row that scrolls sideways, without its labels and the hash;
     shorter source names ("lab data/kb", "sample sheets");
   - (d) the footer: Python plus one "More ▾" for Inspect / Lint / Results / Path map / Hunt
     rules, beside the status sentence (one row).
4. **"Simulate" means run it:** the footer toggle and its pane are **Results**.
5. **The Next.js dev indicator is off** (`devIndicators: false`, next.config.ts; Next 16's
   documented option; compile and runtime errors still show).
6. **An app icon:** `src/app/icon.svg` (our own drawing: two program blocks and a play mark).
   Next emits `<link rel="icon" href="/icon.svg?...">`, so browsers stop asking for /favicon.ico.

## 9. Round 3 (2026-11-09 evening: matpilot's re-run, three small items)

1. **Every Config value is a plain Python value** (a learner may run the Config):
   `PATH = "S2"`, a string (it was the bare name `S2`, undefined in plain Python), and
   `START = ("town", "spawn")`, a tuple (it was a call, `entry(...)`). The parser still reads the
   bare name and `entry(...)`, so older text reads back as the same flow and hash (tested,
   `test_every_config_value_is_a_python_literal`). The other constants were already literals
   (strings, ints, True). `STOP_WHEN` and `ASSUMES`, when a flow has them, stay expressions
   (sensor calls, like every line in Main); none of the committed flows has them.
2. **The starter's lint chip** ("1 warning · 2 not ready") **cannot be cleared from the starter**.
   All three findings belong to the ALWAYS-ON safety events the engine adds to EVERY flow
   (ADR-0020 #15: `dead` respawns, `hp_critical` escapes); none of them comes from the starter's
   three blocks:
   - readiness: `handlers.dead.0: respawn is unsupported here: L2 binding
     L2.window.death_dialog (not bound for kro-20211103-prere/lab-rathena)`;
   - readiness: `handlers.hp_critical.0: escape is unsupported here: L3 binding L3.map.flags (not
     bound for kro-20211103-prere/lab-rathena)`;
   - warning: `handlers.dead: a death at main.0 respawns at the save point, which nothing sets
     before it: set it first, or assert it`.
   The safety events cannot be disabled (they are safety-critical). The two bindings are lab gaps
   that every flow shows until they are written. The warning would go away only with
   `set_save_point` (walking to a Kafra on a real map) or `assert_save_point(cell(...))`, which
   would put an invented fact about the character into a learner's first program. Options for
   Batt, none taken:
   - (a) the context chip says "your blocks: lint ok · built-in safety events: 1 warning, 2 not
     ready" (UI wording only; the Lint pane keeps every finding);
   - (b) write the two bindings (the death dialog's L2 anchor for the lab client; lab-rathena's
     L3 map flags); this clears the readiness items for every flow;
   - (c) accept the save-point warning as a lesson (a flow that never sets a save point respawns
     where the character last saved).
3. **The header fits the 384 px pane and a phone:** two comment lines of 33 and 52 characters,
   `# Made by poring-lab from blocks.` and `# The flow engine reads this file; it never runs it.`;
   section rules are 52 characters (`RULE_WIDTH`; matpilot's are 76, which that pane clips).
   ➡️ SUPERSEDED the same evening (matpilot's round-3 check: the pane shows ~43 monospace
   characters after the gutter, so 52 still clipped): two lines of 33 and 37 characters, `# Made
   by poring-lab from blocks.` and `# Read by the flow engine, never run.`; rules 42 (`RULE_WIDTH`).
   Code lines are left as they are (they scroll, as in an editor; matpilot's advice).

## 10. Round 4 (2026-11-09 ~20:xx, Batt: "add the import line and try/finally now"; option (b))

**A. The Python reads like a file a learner could run, and stays honest.**
- The file now has three parts around its sections:
  - `from poring_flow.learner import *` comes right after the two comment lines;
  - a plain flow's Main runs in `try:` ... `finally:` with the comment line
    `# the engine lets go of all input` and `release_all()`.
- The `finally` is what the engine really does when a flow ends: runtime.Sim.run sends a
  ReleaseAll when anything is held or the flow did not end normally, and ADR-0020 section 6
  releases everything at every stop.
- `poring_flow.learner` is a **STUB** module, built from the catalogue so it never drifts.
  - Every block, sensor, reference constructor and helper has its name and signature; calling one
    raises `NotImplementedError("…: poring-lab runs flows itself; this file is read, never run")`.
  - So `python my_flow.py` stops at its first block with that message, not a NameError.
  - `release_all()` is the one name that does nothing: nothing ran, so nothing is held.
  - `range` is Python's own. The constants (`OK`, `CRITICAL`, `S2`, …) are their IR values.
- **The parser** removes exactly these two forms before its allow-list:
  - the import as the FIRST statement;
  - the try / finally as the LAST top-level statement, with no except or else, and nothing but
    `release_all()` in its finally.
  - Main's statements inside it are read as Main statements: a def or a new name in there is
    refused.
  - Any other import or try is still refused as before: the hostile corpus is unchanged, and 12
    new refusal cases are in tests/test_models.py.
  - The older shapes (no import, no wrapper) read back as the same flow and hash.
- Workflow flows (map blocks) have no Main, so they get the import line only.
- Every printed name is defined by the file, the stub or Python (a static test over every
  committed flow, the sample and the starter).
- Every comment line, the indented finally note included, is at most 42 characters.

**B. The lab's missing safety bindings (Batt chose option (b)): "not ready" clears for every flow.**

| Binding | Where | What it points to | Committed? |
|---|---|---|---|
| `L2.window.death_dialog` | `packages/poring_skills/l2/kro-20211103-prere.yaml` | the "Game option" death dialog at client [505, 450, 280, 70] (gm_vitals DEAD_BOX), recognised by the LOCAL signature `dead_game_option` (+ `@ko`), `data/ro_agent/signatures/` | the names and numbers yes; the signature pixels NO (local, gitignored) |
| `L2.element.return_button` | same file | the dialog's FIRST button, "move to the save point": box [534, 472, 221, 20], click (644, 481), measured OFFLINE on the archived frame `crusader/deathcap` 0149 (NAS scratch-archive/2026-10-21, read only) | numbers yes; the frame NO |
| `L2.element.stay_button` (extra) | same file | the SECOND button, "return to game": box [534, 495, 221, 20], click (644, 504); gm_vitals RETURN_TO_GAME (645, 503), clicked live in S6b | numbers yes |
| `L3.map.flags` | `data/kb/bindings/lab-rathena.json` (LOCAL, gitignored) | the maps of rAthena's `npc/mapflag/noteleport.txt` (345) and `noreturn.txt` (8 active; the rest are commented out at this ref) at the pinned ref e985006; a leaf of lists (escape takes no parameter) | NO: GPL-derived, written by `scripts/kb_bindings.py --only-map-flags`; the code is committed |

- Every binding is `status: unverified`. The dialog was proven on RDP (3.96b S6b), but its first
  button was never clicked by us, so char.respawn's L1 badge stays unverified.
- The map flags are read from the static flag files only: a script that sets a flag at run time
  is not read (the leaf says so).
- **The starter's chip:** "1 warning". The save-point warning stays as Batt's lesson.

## 11. Round 5 (2026-11-09 evening, Batt said yes to both proposals)

1. **The first screen is a TWO-MAP STARTER on the Map tab.** Batt asked whether the node-red /
   n8n map canvas had been dropped: it must be the first thing a learner sees.
   - `starterFlow()` (fixtures/starter.json) is a workflow of two map blocks:
     - `town` (town_1): `set_save_point(npc("n_kafra"))`, walk to (97, 71), then the NPC warp exit
       (talk to `n_warper`, choose `o_to_field`) to `field`.
     - `field` (field_1, targets 9101, 9102, 9105, 9109): `for _ in range(5): attack_nearest(within=12)`,
       then a Butterfly Wing (`WING = item(9002)`) back to the save point, `town.spawn`.
     - It runs until stopped.
   - **A correction:** the brief said a Fly Wing, but a Fly Wing teleports within the same map; the
     Butterfly Wing goes to the save point, which the town sets.
   - **Facts used:** the SYNTHETIC maps, NPC and option keys, item and mob ids of Batt's sample
     (packages/poring_flow examples/sheets/sample). Nothing client-derived. So the starter is
     linted and simulated on the sample sheets (`STARTER_WORLD = "sample"`; the context bar shows
     it).
   - Every spawn of field_1 is a target (the boss 9109 too), so no species warning.
   - **Lint:** 0 errors, 2 not ready, 1 warning (the sample itself has 0 / 5 / 2 / 2 info):
     - not ready: `set_save_point` needs `L4.text.menu_option` (no L4 locale resolver yet,
       ADR-0012);
     - not ready: `attack_nearest` needs `L2.input.attack_click` (not bound for the lab client);
     - warning: the save-point lesson. It stays even with `set_save_point` first, because a death
       DURING it respawns at the old save point. No true fix exists, so Batt's lesson stays.
   - **SIMULATE** on the sample sheets: town → npc_warp → field → item_warp → town, every exit
     arriving.
   - The Python pane shows `def town()` and `def field()`, each under its `@map_block`.
   - The one-map starter is kept: Load ▸ "Starter: one map" (fixtures/starter_one_map.json).
     Load ▸ "Starter: two maps" and Start over give the new one.
   - A browser's saved flow still wins over the starter; the static-data choice is remembered
     with it (`poring-lab.flows.world.v1`).
2. **The shop / Kafra / storage blocks are Actions, written as sentences** (matpilot's output
   blue, after talk / choose / use item / open window, under the label "At a shop or a Kafra:"):

   | Block | Words |
   |---|---|
   | set_save_point | "set the save point at the Kafra <npc>" |
   | kafra_teleport | "teleport with the Kafra <npc> to <map>" |
   | kafra_store | "store <items> at the Kafra <npc>, or all but <keep>" |
   | kafra_withdraw | "take <items> from the Kafra <npc>" |
   | rent_cart | "rent a cart from the Kafra <npc>" |
   | buy | "buy <items> from <npc>" |
   | sell | "sell all but <keep> to <npc>" |

   - The IR is unchanged: each sentence block is the same catalogue action.
   - Item lists are typed as text, "501, 502" or "501, WING".
   - A value a field cannot hold exactly stays the generic block, losslessly: a list variable,
     an empty list, or an extra parameter.
   - `cart_transfer` stays in More skills: its `direction` values are written nowhere, so a
     sentence would invent them. `refine` is a smith's service, not a shop / Kafra / storage block.

## 12. The Maps page and the map a tab is bound to (2026-11-10)

Batt asked for a map-flow page beside /flows: [world-map-flows.md](world-map-flows.md) (the Maps
page, /maps: START → Login → Choose character (mocks) → the map nodes, each bound to its flow, and
the bot simulated on the maps' walk grids). What changed HERE, on /flows:
- **The Map picker** at the end of the tab row (matpilot's Robot choice): "Map ▾" names the map the
  open tab's flow is bound to (a map block's tab) and opens another map's tab; **◂ Maps** goes to the
  Maps page with that map selected.
- **`/flows?block=<name>`** opens that map block's tab (the Maps page's "Open flow").
- **The Map tab is kept**, with a link to the Maps page over its canvas (section 11: Batt wants the
  map canvas first here). Whether to keep both is Batt's call (world-map-flows.md section 4).
- The flow is written to this browser's storage at once when the page links to /maps or goes, so
  the two pages show the same flow.
- The simulator's trace gains the `play` list (`Scenario.encounters` off here: /flows' runs are
  unchanged but for that list).

