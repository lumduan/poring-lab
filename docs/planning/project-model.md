---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~19:3x (Batt's answers), BUILDING: the PROJECT model (format 3) replaces the flow IR 2 as what /maps and /flows edit and save"
role: null
verdict_date: null
verdict_ticket: null
supersedes: [world-map-flows.md section 15 (the one-studio round), flows-save-load.md (the file format)]
related: [world-map-flows.md, flows-studio.md, ADR-0020, ../../packages/poring_flow/src/poring_flow/ir.py, "matpilot ADR 0013 (tabs and functions)"]
next_action: "Engine BUILT 2026-11-13 (branch feat/project-engine: poring_flow/project.py + pyproject.py, the routes, the fixtures; ADR-0020 Amendment D). Still to build: /maps (nodes + Global), /flows (per-node tabs, functions with inputs), the map-name reader; then matpilot's re-review."
title: "The project model: nodes on /maps, tabs per node on /flows, functions like Python"
date: 2026-11-13
owner: Batt
---

# The project model (format 3)

## 0. Batt's words (2026-11-13 evening, Thai, translated)

- "First we make /maps: a login node, a choose-character node, a node for each map (all of them
  can be linked into a work flow), and a GLOBAL node that can share variables and functions. Think
  of modular programming."
- "Double-click a node and it comes to /flows. Each node has as many tabs as it likes, but only ONE
  main tab; the others the user makes, e.g. a tab of functions to talk to NPCs, a tab of functions
  to hunt monsters. Every tab is imported into main, and the Global node is imported into every map
  too, so main stays short. Look at matpilot's flows: we do it that way on /flows."
- Answers: (1) IRON RULE: every node on /maps has flows, at least a main; login works like n8n
  (credentials by name). (2) A map's function with a Global function's name OVERRIDES it. (3)
  Events can sit in Global; an event is a function the user writes; the same in a map overrides it
  (e.g. HP < 50 % on one map). (4) Global has NO main: the user makes its tabs, functions and
  variables and names them. (5) Functions with and without inputs, like real Python (defaults,
  *args, **kwargs); a function without inputs can be an event, e.g. "the character died: respawn".
  (6) Refactor fresh: clear the old system out and use the new structure (old IR 2 files are not
  converted).

## 1. What plays the game (unchanged)

The flow engine simulates; the game is played by the runner (scripts/dungeon_hunt.py) through the
map node's "hunt with the runner" block and Run. Login and Choose character are NOT run live in
this round: Run starts on a map node with the character already in the game (the bot's real login
stays ro_agent's Python). Their nodes' flows are simulated and shown.

## 2. The JSON (the contract every part builds against)

    Project = {
      "format": "poring-lab.project", "version": 3,
      "name": FLOW_NAME, "description": str (<= 500),
      "target": {client, server, locale, path},          # as IR 2
      "max_runtime_s": int, "where_budget": int, "stop_when": Expr | null, "assumes": [Expr],
      "start": NodeId,                                    # where Simulate and Run start: a login
                                                          # node, or a MAP node (2026-11-13, below)
      "nodes": [Node],                                    # ids unique
      "edges": [Edge]                                     # the session path (see 2.4)
    }
    Node = common {id: NodeId, kind, pos: {x: number, y: number}, tabs: [Tab]} plus
      kind "login":     (no more fields)
      kind "character": (no more fields)
      kind "map":       map: MapRef, entries: [Entry] (>= 1), targets: [MobRef], ignore: [MobRef],
                        zones?: ZonesRef (absent when none), resume_here: bool
      kind "global":    (no more fields; at most ONE global node, id "global")
    Tab = {name: TabName, main: [Stmt] | null, defs: [Def], vars: {NAME: Lit}}
      - every node but Global has exactly one tab "main", first, whose `main` is a list (its
        program); every other tab has main null. Global has no tab "main".
      - TabName ^[a-z][a-z0-9_]{0,19}$; "main" only as the main tab; not a Python keyword or
        built-in, not "global", not a function's or another tab's name of the same node.
    Def = {name: NAME, params: [Param], varargs: NAME | null, kwargs: NAME | null,
           body: [Stmt] (>= 1), on: Trigger | null}
      Param = {name: NAME, default: Lit | null}          # null = required; required ones first
      Trigger = the IR 2 Handler's fields but `name` and `body`: when, until, rearm, priority,
                rank, mode, escalate, max_insert_fails, cooldown_s, max_per_min,
                max_fires_per_10min, max_per_run, then. A def with a trigger is an EVENT: it takes
                no params, no *args, no **kwargs; its name is its event key.
    Stmt = IR 2's statements, with these changes:
      - call:   {kind: "call", proc: NAME, args: [Expr], kwargs: {NAME: Expr}}
      - return: {kind: "return", value: Expr | null}      # inside a def only
      - take_exit / exits as IR 2 (walk_exit, npc_warp, item_warp with item XOR proc), on a MAP
        node's tabs only; `to_block` names the target map node's id, `to_entry` its entry.
      - the session blocks (actions): login(server, credential) on a login node's main;
        choose_character(slot?, name?) on a character node's main.
    Expr = IR 2's expressions, plus
      - {kind: "callv", proc: NAME, args: [Expr], kwargs: {NAME: Expr}}   # a function's value
      - {kind: "var", name} also reads a param, a *args / **kwargs name, a tab or Global variable
    Edge = {from: NodeId, to: NodeId, entry?: EntryName}
      - the SESSION path: login -> character -> the start map node (its entry). Map -> map links
        are not edges: they are the exits (take_exit statements), drawn as today. Global has no
        edges.

Canonical JSON and the project's hash: as IR 2 (sorted keys, no whitespace, NFC; the engine's
floats as it prints them). A field that is absent by default (zones) stays out of the JSON.

➡️ **The engine's decisions on section 2 (built 2026-11-13, `poring_flow/project.py`; the JSON
is unchanged):**
- `stop_when: {"kind": "lit", "value": false}` is the explicit "run until stopped" (IR 2's
  `run_until_stopped`, 13.5: a workflow cycle needs a stop condition or that choice). The sample
  project uses it; no new field.
- Absent by default and out of the JSON: a map node's `zones` and an edge's `entry`. A call's
  `args` / `kwargs` are always IN a project's JSON. `pos` x / y are floats (the canonical JSON
  prints `260.0`); `where_budget` defaults to 12, `description` to "", `assumes` / `edges` to [].
- The shape rules are `ProjectError` problems `{node, tab, path, message}` (the routes' 422
  `invalid_project`, `problems`): main tabs, tab names, one namespace per node (a function and a
  variable count alike), parameters (required first, each once), an event takes no inputs, return
  only inside a def, take_exit only on a map node, edges (login -> character without an entry;
  character -> map WITH an existing entry; one edge out of a node), at most one Global with id
  "global", start a login node. An empty main is accepted while drafting (the lint's `empty_main`
  error on a map node).
- Tab names also refuse a VARIABLE's name of the same node (a module name clash), and
  `built_in`: findings at the engine's always-on safety events (when Global writes none) show
  under `global/built_in/<event>`. The list is GET /flows/catalogue's `tab_name_rule`.

➡️ **A MAP START (Batt 2026-11-13 ~21:4x: "START > map xmas_dun02, ONE box is enough; login
and choosing the character come later; the user puts the character on xmas_dun02 themself";
[live-blocks.md](live-blocks.md) stage 1; built on feat/one-box):** `start` may name a MAP node.
The run starts where she stands on it (a person put her there), at its FIRST entry, with no
session: login and character nodes are optional and `edges` may be empty. The engine:
`start_map(p)`, `session_path(p)` returns the map with `map_start` true; the compile starts the
workflow there; the simulator's trace has `session: null`; the Python view prints
`START = "<map>"`; the lint accepts it and WARNS when login / character nodes or edges are there
too ("not played"). Any other node kind as `start` stays an error. The ready-made xmas_dun02 is
now ONE map node (section 7).

## 3. Names: imports and overrides (the semantics)

- A node's tabs are ONE namespace: a name defined twice in one node (two tabs) is an error.
  Global's tabs are one namespace too.
- Main imports every tab of its node and Global (Batt: "every tab is imported into main"). Every
  tab may use its own node's names and Global's. Global uses only Global's names.
- OVERRIDE (Batt's answer 2, "like a public class"): while the run is on a node, a name resolves
  to that node's definition first, then Global's. This holds EVERYWHERE on that node, also inside
  Global's functions and events: Global's hp_low calling heal() on xmas_dun02 calls xmas_dun02's
  heal() when it has one (virtual dispatch, as a method of a subclass). Functions, variables and
  events override alike.
- Events: a def with a trigger. In Global = every node's event; a def of the same name in a node
  replaces it there (IR 2's Override); no def there = the Global one runs. The built-in safety
  events (dead, hp_critical, unexpected_map) stay always on: a user def of that name follows IR 2's
  rule (its body starts with the built-in's step; the engine's linter says so).
- Variables: a tab's `vars` are module names (every function of its node sees them); Global's are
  shared by all nodes. Assigning a Global variable from a node changes it for everyone (Python
  `module.name = value`); a node's variable of the same name overrides it there.
- Recursion: refused (a function calling itself, directly or through others): the engine
  inlines or frames calls with a depth bound; a loop is the way to repeat.

➡️ **How the engine runs it (built 2026-11-13, ADR-0020 Amendment D):** a project COMPILES to one
internal IR 2 flow, so every IR 2 rule holds unchanged. Map nodes are map blocks (the node id is
the block's name); Global's functions, variables and events are the flow's procedures, variables
and global events; a node's own functions and variables are procedures / variables of their own
(an internal name when another node or Global has the same one; texts always show the user's).
VIRTUAL DISPATCH is compiled by specialisation: a Global function or event that reaches (through
Global's calls and variables) a name a node overrides gets a copy for that node whose names
resolve there; a Global event's copy is an override on that node (the effective set shows it
"inherited", `dispatched: true`, and an info finding names the override it uses). It is exact:
code runs on the node where it was entered (an exit ends a main, a relocation ends everything).
Calls frame: arguments bind into a local environment per scheduler frame (an event that cuts a
function never sees its locals); a call deeper than 32 stops the run (`call_depth`). Further rules:
- an override keeps its kind (a function for a function, a variable for a variable, an event for
  an event: else an error); a node's PLAIN function named like a Global event turns that event
  off there (IR 2's Disable, a warning; refused for dead, hp_critical, unexpected_map);
- a node's def of a safety-critical event's name replaces it there (a strict override) only
  where the built-in's rule holds (its body starts with the built-in's step, no looser limits);
- an event is not called; an event condition cannot call a function (it reads sensors and
  variables); a parameter cannot reuse a visible function's, variable's or catalogue name;
- Global's code uses only Global's names (a name only a node defines is "there is no procedure").

## 4. The Python view (one file per tab)

    global/keys.py        def fly_wing():  press_key("F8")
    global/safety.py      @on(is_dead(), priority=CRITICAL, then=RELOCATE)
                          def dead():  respawn()
    login/main.py         login(server="lab-rathena", credential="lab_gm")
    character/main.py     choose_character()
    xmas_dun02/main.py    from global import *        # Global
                          from .hunt import *         # this map's other tabs
                          @map_node("xmas_dun02", entries=[...])
                          def main(): ...
    xmas_dun02/hunt.py    def ...

The engine owns the exact spelling (functions with defaults, *args, **kwargs, return; calls with
positional and keyword arguments) and its round trip (Python -> project and back, per file). A
file that overrides Global's names says so in a comment line the parser ignores.

➡️ **The spelling (built 2026-11-13, `poring_flow/pyproject.py`, its docstring is the
reference):** files `<node>/<tab>.py` plus `project.py` (the Config constants, `node("<id>",
kind=..., pos=(x, y), tabs=[...])`, `edge("<from>", "<to>", entry="<entry>")`). Every file starts
with the two generated lines and `from poring_flow.learner import *`; a node's file adds
`from global_ import *` (`global` is a Python keyword: the module takes PEP 8's trailing
underscore; the folder stays `global/`) and `from .<tab> import *` for its other tabs but main.
`def go(cell, times=3, *rest, **opts):`, `go(cell("m", 1, 2), times=4)`, `x = pick(3)`,
`return` / `return x`, an event `@on(hp_percent() < 30, ..., priority=SURVIVAL)` above a def
without inputs, a map node's main `@map_node("xmas_dun02", entries=[...], zones=zones(...))
def main():`, a login's `def main():\n    login(server="lab-rathena", credential="lab_gm")`,
and the override comment `# overrides Global's fly_wing (tab keys)`. A credential that is not a
plain name prints as `"<redacted>"`.

## 5. Login like n8n (credentials by name)

- The login block names a SERVER (an environment id of the Settings page) and a CREDENTIAL by
  name; a secret is never in a project, a file, a block or the Python view.
- This round's credentials: the lab's two accounts as ro_agent knows them, `lab_gm` and
  `lab_player` (.env prefixes; names only). A credential store a person fills on the Settings page
  (secrets typed human-only, ADR-0004 c) is a later step.
- The simulator plays login and choose_character as the Maps page's mocks (lib/maps/session.ts).

➡️ **Built 2026-11-13:** the blocks `login(server, credential)` and `choose_character(slot=None,
name=None)` (blocks.yaml; L1 `session.login` / `session.select_char`, out of `excluded`). Lint:
`session_place` (only on a login / character node's main), `session_main` (that main is the one
block), `session_server` (an environment id of config/environments.yaml: an error otherwise; a
warning unless it is lab-rathena; a warning when the project targets another server),
`session_credential` (one of lab_gm, lab_player; anything not matching `^[a-z][a-z0-9_]{0,31}$`
"looks like a secret": an error that never echoes the value, and the project's hash is then never
returned: null in every route), `session_character` (slot 1-15, a name of session.ts's
CHAR_NAME), `session_path` (start -> character -> a map node's entry by edges), `session_defs` (a
warning: a session node's functions never run). The simulator's play list starts with a `login`
step (0-7 s: `phases` start 0-1, login 1-7) and a `character` step (7-11 s, `enters` the start
map's entry); the map flow's times follow on the same clock. A scenario whose `start_block` is a
map node starts there without the session (Run's case).

## 6. Run (unchanged in effect)

Run belongs to a map node whose main holds "hunt with the runner" (dungeon_hunt) on a map with a
runner. Its five keys are read from the functions the block names (and the item warp's function),
resolved on THAT node (its override first, then Global), through calls with literal arguments, to
exactly one press_key each; the request carries them (POST /flows/run keys), as today.

➡️ **Built 2026-11-13:** `poring_flow.project.runner_keys(project, node_id)` -> the five keys
(`heal_key`, `fly_key`, `home_key`, `knife_key`, `dagger_key`) and the functions they came from,
or the problems (no dungeon_hunt, no item warp by function, a function that is not one press, a key
off the hotbar, two roles on one key). "Through calls with literal arguments": a function's body is
one press_key, or one call with literal arguments of such a function; a press_key may press its
function's parameter when every call gives it a literal hotbar key (the lint's `key_argument`).

➡️ **The home role (2026-11-13 ~21:4x, the one box):** dungeon_hunt has an optional FIFTH role,
`home`: the function the runner presses to fly home on a Butterfly Wing (the bag half full, or
Stop: its settings). Its lint is the four's (exactly one press_key, its own key), and its function
is a Butterfly Wing function (`functions.wing_functions`: its key is a wing key, as an item warp's).
`runner_keys` reads `home_key` from it FIRST, else from the node's item warp by function (as
before); neither is the problem "no Butterfly Wing home". Run on a map node now plays the PROJECT
through the live block player ([live-blocks.md](live-blocks.md) section 3: `POST
/flows/run/project`).

➡️ **2026-11-14 (live-blocks.md stage 3, section 3.3; ADR-0020 Amendment G):** knife_on, knife_back
and home may be a BODY of presses and waits (through calls with literal arguments) that the hunt
core calls at its own moment; `runner_keys` then takes the body's FIRST press
(`functions.role_key`; the browser's `roleKeyOf`). dungeon_hunt has two more optional roles,
`respawn` and `respawn_confirm` (functions of the new block click_at): they give no key.

## 7. The ready-made project (the fixture both sides test)

`services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json`: login (lab-rathena, lab_gm) ->
character (the remembered slot) -> xmas_dun02 (entry here) with geffen; Global tabs `keys`
(heal F1, fly_wing F8, butterfly_wing F9, knife_on F4, knife_back F5) and `safety` (an hp_low
event calling heal, as an example a map can override); xmas_dun02 main: the save point, the hunt
loop, the wing home. A second ready-made: the two-map sample (town_1 / field_1) on the sample
sheets.

➡️ **Built 2026-11-13:** `project_xmas_dun02.json` exactly as above (positions login (0,0),
character (260,0), xmas_dun02 (560,0), geffen (860,0), global (560,220); the zones sha256 is
config/map_zones/xmas_dun02.yaml's; Global's hp_low: when hp_percent() < 30, rearm above 50,
survival, insert, resume, body heal(): IR 2's rearm rule needs the re-arm); `project_sample.json`
(town / field on the synthetic sample sheets, Global keys: butterfly_wing = F9, `stop_when: false`
= run until stopped); the Maps page's trace `lib/maps/fixtures/project_sample_trace.json` (from the
login, horizon 71 s, encounters, seed 3). Both lint without an error (xmas_dun02: no static data,
with the zones provider, with the local KB when present; the sample on its sheets).

➡️ **SUPERSEDED 2026-11-13 ~21:4x by THE ONE BOX** (Batt: "take every box out: START > map
xmas_dun02, one box is enough"): `project_xmas_dun02.json` is ONE map node -- start xmas_dun02,
no edges, at (0, 0), entry `here` (anywhere, radius 2), the zones reference as before; tab `main`:
the save point (Geffen 119,40, the world rule's note), `dungeon_hunt(heal="heal", fly="fly_wing",
knife_on="knife_on", knife_back="knife_back", home="butterfly_wing")`, `stop("home")` (the runner
itself flies home); tab `keys`: heal F1, fly_wing F8, butterfly_wing F9, knife_on F4,
knife_back F5. No login, character, geffen or Global node. It lints without an error (no static
data; with the zones provider). The login-start project above is kept as the TESTS' fixture
`project_session.json` (the session path, Global and its overrides build on it); the sample is
unchanged.
➡️ **2026-11-14 (live-blocks.md stage 2, section 3.2):** the one box has a third tab, `survival`:
the events `drink` (`hp_percent() < 30`, repeating until 31 %, an insert paced 0.7 s; calls heal)
and `fly_away` (`sees_boss() or hp_percent() < 25`, a one-shot pre-empt re-armed 3 s after its Fly
Wing; calls fly_wing). They play INSIDE the hunt core, where the runner's own potion, Fly Wing on
HP and boss fly are then off. Its description now names the tabs (the Python view holds a string
of at most 200 characters). Still 0 lint errors.
➡️ **2026-11-14 (live-blocks.md stage 3, section 3.3):** five tabs: `keys` (heal F1, fly_wing F8,
butterfly_wing F9, wield_knife F4, wield_damascus F5), `survival` (drink, fly_away and `bag_full`:
`weight_percent() >= 50`, one stop("home") a run), `knife` (knife_on calls wield_knife, knife_back
calls wield_damascus: the swap at the runner's two moments), `exits` (fly_home calls
butterfly_wing; respawn_button `click_at(645, 481)`, respawn_ok `click_at(714, 405)`); main's
`dungeon_hunt(..., home=fly_home, respawn=respawn_button, respawn_confirm=respawn_ok)`. Still 0 lint
errors. The stage-2 box is kept as `project_xmas_dun02_stage2.json` (stage 3's A/B).
➡️ **2026-11-14 (live-blocks.md stage 4a, section 3.4):** six tabs: main holds
`use_model("xmas02")` before its dungeon_hunt (the trained data: the hunt core's model), and the new
tab `monsters` one function per monster xmas02's runner strikes -- `attack_mystcase(t,
priority=1)`, `attack_cruiser`, `attack_cookie`, `attack_cookie_xmas`, each TODAY's technique
(knife_on(), strike(t), wait_steal(t), knife_back(), wait_kill(t), loot(t)); the hunt core asks
the recipe of a target's species when it locks it. A function named `attack_<class>` is a monster's
RECIPE (poring_flow.recipes). Still 0 lint errors. The stage-3 box is kept as
`project_xmas_dun02_stage3.json` (its tests, stage 3's A/B).

## 8. Not converted (Batt's answer 6)

IR 2 flow files, the browser's old flow (`poring-lab.flows.flow.v1`) and the shelf are not
opened by the new pages: a notice says the format changed and offers the ready-made projects.
The engine may keep IR 2 internally as its execution form; nothing user-facing reads or writes it.

## 9. The build (2026-11-13 night)

| Part | Who | Notes |
|---|---|---|
| Engine: packages/poring_flow (project models, Python view, lint, simulate, routes) | subagent | the contract above; keeps the safety semantics of IR 2. ➡️ BUILT 2026-11-13 (feat/project-engine; the ➡️ notes in sections 2-7) |
| The map-name reader (pixels: which map she is on) | subagent | the start check's map line ✓ only when read; the runner's start refuses another map |
| /maps: login / character / map / Global nodes, edges, double-click -> /flows?node= | the parent or a subagent | lib/flow/project.ts is the shared TS model |
| /flows: one node's tabs (main + the user's), functions with inputs, events as functions, Python per tab, Run | the parent | matpilot's ADR 0013 as the model (MIT) |
| matpilot's 16 findings of 2026-11-13 | the parent | section 10 |

## 10. matpilot's review of 2026-11-13 (round 14) to fold in

| # | Finding | State |
|---|---|---|
| 1 | the map line never a tick | DONE 3b0657f1 ("?"); the map-name reader replaces it (section 9) |
| 2 | phone: Run first and biggest | DONE 3b0657f1 (last and small; the bar wraps) |
| 3 | "SIMULATE only" on a page with Run | DONE: "SIMULATE · RUN" on a node with Run |
| 4 | two buttons named Run | DONE: the drawer pane is "Before Run" |
| 5 | 0 items read on a key: say where they may be | PART: a hint to set the function's key (the check reads only the keys it is given) |
| 6 | "ready" with a ✗ or a clash | DONE: "not ready: …" |
| 7 | settings saved on the server, unsaid | DONE: a line above them |
| 8 | the known warnings in plain words | OPEN |
| 9 | the functions: what a function is, taken keys, a clash where it is | PART: the toolbox's words; the engine's hotbar_keys error names both roles |
| 10 | who flies home (three weight numbers) | OPEN: the loop's 50 % is the flow's, the runner's weight setting decides the real run |
| 11 | the inside view does not follow the function keys | OPEN |
| 12 | raw Python words on blocks, "xmas_dun02 · xmas_dun02" | DONE: the save point sentence, "arrive on … at …", the node chip |
| 13 | the tab row and the phone canvas | PART: the runner link left the tab row; the phone canvas not re-measured |
| 14 | the FLOWS row reorders on a press | DONE: by name |
| 15 | Load names the Map tab; Escape | DONE |
| 16 | the check shares the start's endpoint | DONE: POST /flows/run/check; a check body on /flows/run is refused |
