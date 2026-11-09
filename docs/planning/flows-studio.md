---
doc_type: design
hypothesis: null
status: "BUILT 2026-11-09 (working tree, not committed): the /flows studio in matpilot.org/blocks's layout and colours, the Python beside the blocks, the trained models as sensor blocks (ADR-0020 Amendment B). Checked by unit tests and a headless Blockly 13 round trip; not yet looked at in a browser."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [ADR-0020, mw2-block-editor.md, blocks-from-hunt-flow.md, xmas02-detector.md, stormy-knight-recognizer.md, orclord-recognizer.md, ../../THIRD_PARTY.md, ../../services/frontend/src/components/flows/FlowsApp.tsx, ../../packages/poring_flow/src/poring_flow/models.yaml]
next_action: "The parent restarts the backend (the new sensors, lint rules, model catalogue, Python sections and the Python route's own rate budget are host source); then Batt and the matpilot session look at http://192.168.1.228:3000/flows (light and dark, 1280 px and 390 px) against /blocks. Open: section 7."
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
│ │ Movement│ when the program starts       │       ││  1 # --- Config ------------ │ │
│ │ Actions │   wait 1 seconds              │       ││  2 flow(                     │ │
│ │ Control │   wait until (detector v1 …)  │       ││  …                           │ │
│ │ …       │   stop done                   │       ││  9 # --- Main -------------- │ │
│ └─────────┴───────────────────────────────┘       │└──────────────────────────────┘ │
│ ┌ Inspect ┐┌ Lint ┐┌ Simulate ┐┌ Path map ┐┌ Hunt rules ┐   drawer, when a pane is on │
│ Fix before simulating: … · Lint errors: … · Not running (the faded blocks): …       │  problems
│ Ready. Press Simulate…                  (Python)(Inspect)(Lint)(Simulate)(Path map) │  status footer
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
  drawer 45vh with panes stacked, the status sentence on its own line.

**What a learner sees first:** the header, the tab `main`, the starter program (when the program
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
| Simulate tab + its path maps | **Simulate** pane (+ a detector sighting row) and the **Path map** pane |
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
generator does (`# --- Config ---…`, 76 characters): **Config** (the `flow(...)` head), **Setup**
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
