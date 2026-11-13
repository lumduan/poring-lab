---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~21:4x (Batt): build the live block player first; one box (START > xmas_dun02); break the runner into blocks. Stage 1 BUILDING."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [project-model.md, player-mode.md, ADR-0020, ../../scripts/dungeon_hunt.py, ../../scripts/runner_flow_export.py, ../../packages/poring_flow/src/poring_flow/runtime.py]
next_action: "Stage 1: the one-box project, the live block player with the generic blocks and the hunt core as one block (in-process, a tick hook), Run on /flows and on /maps."
title: "Live blocks: the player that plays a project's blocks in the game, and the runner broken into blocks"
date: 2026-11-13
owner: Batt
---

# Live blocks

## 0. Batt's words (2026-11-13 ~21:4x, Thai, translated)

- "Build the player of blocks in the real game first. Take every box out of the page: START >
  map xmas_dun02, ONE box is enough. Then build this box's flow, put EVERYTHING the bot has
  trained to play into it. We start from only this. Login and choosing the character come later.
  Start simple."
- "If someone wants to try this bot program, the user must put the character on xmas_dun02
  themself."
- "On the Maps page add a Run button too: it runs from START, box by box."
- Asked how the hunt should appear, Batt chose: BREAK THE RUNNER INTO BLOCKS (each technique a
  block the player plays), over keeping it one block; he was told it is days to weeks and that the
  hunt must not play worse until each piece is proven again.

## 1. What exists

- The flow engine (packages/poring_flow) SIMULATES: runtime.py's tree runtime runs a fake
  environment and emits the input batches a real run would send; ADR-0020's real executor
  (F2 / MW2) is not built. The run-start check (runstart.py, MW3) exists.
- The game is played by scripts/dungeon_hunt.py `run()`: ONE function of 4,044 lines whose loop
  holds every technique (the export scripts/runner_flow_export.py describes it as ~70 blocks:
  look, safety, boxes, engage, choose, approach, still, lead, strike, loot, explore, walk, the
  Knife swap's two functions, the respawn function, the safety rules: stock out, a dead jump, the
  Fly Wing on HP, the potion, the Garm Baby, the boss, the weight, an unread position, the NPC
  guard).
- Run today: the browser asks the host's Run helper (scripts/flow_run.py) to start the runner as
  a process, in player mode, with the flow's keys and the server's settings.

## 2. The stages (each one proven before the next; the hunt never plays worse)

| Stage | What becomes blocks | Proven by |
|---|---|---|
| 1 | The ONE-BOX project (START > xmas_dun02). The LIVE BLOCK PLAYER: press key, wait, wait until (HP, weight, dead, the map's name: pixels), if / while / repeat, functions with inputs, variables, events, stop, the item warp by a function (its arrival read on the minimap). The hunt core as ONE block played IN-PROCESS (the runner's loop as a library with a tick hook: one process, one input writer). Run on /flows and on /maps (from START, box by box). | offline: fakes prove the input it sends; live: Batt's OK, she placed on xmas_dun02 by a person |
| 2 | SURVIVAL out of the runner into the box's events: the potion, the Fly Wing on HP and on the HP rate, stock out, the dead jump, the Garm Baby, the boss, an unread position. The runner's own handler is switched off for each one the box plays (its flags exist: `flow_config.py`), the event plays it through the tick hook. | live A/B against the monolithic runner: deaths, potions, flies, kills/h |
| 3 | The FUNCTIONS the runner calls: the Knife swap (knife_on / knife_back), the respawn, the weight home, the end: blocks the hunt calls at its hook points | live A/B: steals, swaps, respawn, home |
| 4+ | The CORE, one technique at a time: look, boxes, engage, choose (value target), approach, still / lead / strike, loot, explore / walk / carve | live A/B each: kills/h, loot/h, zeny/h, deaths (Batt's own run is the bar) |

## 3. Stage 1 in detail

- The project: `start` may be a MAP node (the run starts where she stands on it); login /
  character nodes become optional (later). The ready-made project is ONE box, xmas_dun02 (entry
  "here"), with its tabs: main, keys (every key a function), and the parts of the hunt as they
  become blocks.
- The player: a host program (scripts/flow_play.py), started by the Run helper like the runner;
  it compiles the project (poring_flow.project), runs the engine's tree runtime with a LIVE
  environment (real clock, pixel sensors, real input through ro_agent's Agent: the mux, the
  foreground gate, the UI gate), and refuses BEFORE ANY INPUT a block that has no live binding
  (the run-start check names it). Player mode: it types no GM line.
- One input writer: the hunt core block runs in the SAME process with the same Agent; while it
  runs, the box's events reach the game only through its tick hook.
- Stop: as Run's today (the stop file); the player releases what it holds and ends.
- The start: the start check (chat closed, the map's name read as the run's map, the stock on the
  right keys) refuses before any input: the person places her on the map.

➡️ **The project and the browser side, BUILT 2026-11-13 (branch feat/one-box; the backend and the
player are feat/live-player's):**
- The engine: `start` may be a map node (`project.start_map`, `SessionPath.map_start`): the run
  starts at its first entry with no session (the simulator's `session` is null); login and
  character nodes are optional, `edges` may be empty (a map start with session nodes or edges
  warns they are not played). dungeon_hunt has an optional fifth role `home` (the Butterfly Wing
  the runner flies home on: one press_key, its own key, a wing key); `runner_keys` takes the home
  key from it first, else from the node's item warp by function.
- The ready-made project is ONE box (`project_xmas_dun02.json` = `xmasProject()`): start
  xmas_dun02 (entry `here`, anywhere), no edges; tab `main` = the save point (Geffen 119,40),
  `dungeon_hunt(heal, fly=fly_wing, knife_on, knife_back, home=butterfly_wing)`, `stop("home")`;
  tab `keys` = heal F1, fly_wing F8, butterfly_wing F9, knife_on F4, knife_back F5. 0 lint errors.
  The login-start project before it is the tests' fixture `project_session.json`.
- THE REQUEST (lib/flow/liverun.ts `projectRunBody` / `projectRunPath`): `POST /flows/run/project
  {"project": <format 3>, "node": "<map node id>"}` with the CSRF header; refusals 400 / 409
  `{detail: {reason, detail}}`: `lint_errors`, `not_live`, `run_start_refused`,
  `already_running`, `mode_not_assist`, `helper_not_running` (worded in `REFUSALS`). The status
  stays `GET /flows/run` (flow id `project`), Stop stays `POST /flows/run {action: "stop"}`.
  `useLiveRun(..., run)` posts it on a start; the check is the runner's, as before.
- Live readiness (lib/flow/liveready.ts): every block a run from the node reaches -- its main,
  the functions it calls (resolved on that node), the runner's role functions, an item warp's
  function, the events that run there, and the map nodes its exits go on to -- must have
  `GET /flows/catalogue blocks[name].spec.live === true` (missing = not live); an exit other than
  the item warp by a function is not live yet. Else Run is greyed: "walk_to, talk_npc: not live
  yet".
- /flows: Run on a map node plays the project from that node (the same request), gated as above;
  "Before Run" keeps the checklist, the live line, the settings and the read-only check.
- /maps: a START marker (a pill, not a project node) joined to the start map's entry; dragging
  that connection onto another map sets `start` ("Start here" in the node inspector too). Run
  beside Simulate plays the project from START, box by box (the same amber press-twice button),
  with the live line while it plays. A login start keeps today's behaviour: Run says login is not
  live yet.

## 4. Not in stage 1

Login, choose character, walk_to on the live player, talk to NPC, the shop / Kafra blocks.
