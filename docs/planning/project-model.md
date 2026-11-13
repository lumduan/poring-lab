---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~19:3x (Batt's answers), BUILDING: the PROJECT model (format 3) replaces the flow IR 2 as what /maps and /flows edit and save"
role: null
verdict_date: null
verdict_ticket: null
supersedes: [world-map-flows.md section 15 (the one-studio round), flows-save-load.md (the file format)]
related: [world-map-flows.md, flows-studio.md, ADR-0020, ../../packages/poring_flow/src/poring_flow/ir.py, "matpilot ADR 0013 (tabs and functions)"]
next_action: "Build: the engine (packages/poring_flow/project), /maps (nodes + Global), /flows (per-node tabs, functions with inputs), the map-name reader; then matpilot's re-review."
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
      "start": NodeId,                                    # where Simulate starts (a login node)
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

## 5. Login like n8n (credentials by name)

- The login block names a SERVER (an environment id of the Settings page) and a CREDENTIAL by
  name; a secret is never in a project, a file, a block or the Python view.
- This round's credentials: the lab's two accounts as ro_agent knows them, `lab_gm` and
  `lab_player` (.env prefixes; names only). A credential store a person fills on the Settings page
  (secrets typed human-only, ADR-0004 c) is a later step.
- The simulator plays login and choose_character as the Maps page's mocks (lib/maps/session.ts).

## 6. Run (unchanged in effect)

Run belongs to a map node whose main holds "hunt with the runner" (dungeon_hunt) on a map with a
runner. Its five keys are read from the functions the block names (and the item warp's function),
resolved on THAT node (its override first, then Global), through calls with literal arguments, to
exactly one press_key each; the request carries them (POST /flows/run keys), as today.

## 7. The ready-made project (the fixture both sides test)

`services/frontend/src/lib/flow/fixtures/project_xmas_dun02.json`: login (lab-rathena, lab_gm) ->
character (the remembered slot) -> xmas_dun02 (entry here) with geffen; Global tabs `keys`
(heal F1, fly_wing F8, butterfly_wing F9, knife_on F4, knife_back F5) and `safety` (an hp_low
event calling heal, as an example a map can override); xmas_dun02 main: the save point, the hunt
loop, the wing home. A second ready-made: the two-map sample (town_1 / field_1) on the sample
sheets.

## 8. Not converted (Batt's answer 6)

IR 2 flow files, the browser's old flow (`poring-lab.flows.flow.v1`) and the shelf are not
opened by the new pages: a notice says the format changed and offers the ready-made projects.
The engine may keep IR 2 internally as its execution form; nothing user-facing reads or writes it.

## 9. The build (2026-11-13 night)

| Part | Who | Notes |
|---|---|---|
| Engine: packages/poring_flow (project models, Python view, lint, simulate, routes) | subagent | the contract above; keeps the safety semantics of IR 2 |
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
