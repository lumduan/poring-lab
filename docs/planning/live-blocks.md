---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~21:4x (Batt): build the live block player first; one box (START > xmas_dun02); break the runner into blocks. Stage 1: the PLAYER BUILT 2026-11-13 ~22:3x (feat/live-player, offline tests only; NOT run live yet), the one-box project and the pages' Run on feat/one-box."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [project-model.md, player-mode.md, ADR-0020, ../../scripts/dungeon_hunt.py, ../../scripts/runner_flow_export.py, ../../packages/poring_flow/src/poring_flow/runtime.py]
next_action: "Stage 1: merge feat/live-player (the player, section 3's BUILT notes) and feat/one-box (the one-box project, Run on /flows and /maps); the first LIVE run of the player needs Batt's OK, with her placed on xmas_dun02 by a person. Then stage 2."
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

### 3.1 ➡️ BUILT 2026-11-13 ~22:3x (feat/live-player; offline only, not run live)

How to read it, file by file:

| Piece | Where | What it does |
|---|---|---|
| The live set | `packages/poring_flow/src/poring_flow/live.py` + blocks.yaml `live: true` | the ONE place: blocks press_key, dungeon_hunt, assert_save_point; sensors hp_percent, sp_percent, weight_percent, is_dead, current_map, map_load_seen; the control statements; an item warp by a FUNCTION. `problems(flow)` names every other thing ("walk_to cannot play live yet (stage 4)"); GET /flows/catalogue serves `live` (and each block's `spec.live`) |
| The player | `scripts/flow_play.py` (`play`, `plan`) | the engine's tree runtime (`runtime.Sim`) with a LIVE environment (`LivePlayer`): the real clock paced at 0.1 s, the sensors from pixels each tick (hp_percent.py, gm_state's weight, the death dialog's signature, minimap_id's map name), input through ONE ro_agent Agent (the mux: ASSIST, the lease, the interlock, the foreground gate); the UI gate and the client in front at the start |
| The runtime's seams | `packages/poring_flow/src/poring_flow/runtime.py` | `_advance`, `_waited`, `_guard`, `Relocate`: no-ops for the simulator (its tests unchanged), the player's clock, Stop and the hunt core's own map exits |
| The hunt core | `scripts/dungeon_hunt.py` dungeon@9.48 (`LIVE_BLOCKS_VERSION`; VERSION stays dungeon@8.7) | `run(a, hook=None, session=None)`: the player passes ITS (Agent, Screen) and a hook whose `tick(HuntTick)` is called once per loop tick (read access: HP / SP, dead, her cell, the mode, the counters, the frame; a str back = the run's normal end) and whose `event()` mirrors the runner's events into the player's record. `args_for(argv)` parses the Run helper's own argv with the CLI's parser (`build_parser`). The CLI passes neither: unchanged |
| Run of a project | `services/backend/src/poring_backend/routes_flowrun.py` POST /flows/run/project; `scripts/flow_run.py` `start_project` | the backend checks (valid, a map node, 0 lint errors, the live set, the run-start verdict, the keys) and writes the checked `project.json` + one request; the helper checks the file's hash and starts `flow_play.py play` (the detect server first when a hunt core plays) |

The run, in order (each step refuses before any input until the Agent opens):

    prepare (pure)  -> the start check (reads)  -> the Agent (ASSIST, the lock)  -> the UI gate
       |                 |                                                            |
       project valid,    with a hunt core on the node: the runner's own              run_start, then
       a map node,       read-only check in-process (identity, the map read         the tree runtime
       the live set,     from the minimap, chat closed, weight, stock); else        tick by tick ->
       the time box,     identity, chat closed, the map's name                       run_end (words)
       the hunt core's
       keys + settings

- **Stop**: the Run helper's stop file; at the next tick outside an atomic section the run ends,
  ReleaseAll, `run_end` "Stopped by you". Inside a hunt core the runner sees the same file (its
  --stop-file, its normal end) and the hook asks it too. The time box: min(the project's
  max_runtime_s, the Settings maximum).
- **The hunt core's end**: its own way home or respawn (the runner's player end) -> the player
  follows her by the map's NAME to a node on that map, or ends ("she is on geffen: no map node of
  the project plays there"); a death -> the run ends; its time box -> the run ends; an end on the
  map (its own time box, a weight exit with no wing) -> the box's main goes on.
- **The safety-critical three** a project does not write play as the SAFE END in stage 1 (dead,
  HP under 20 %, an unexpected map: release, end, named); while the hunt core runs, the runner's
  own survival plays and the box's events wait.
- **The record**: `/dev/shm/poring-lab-demo/<time>-play-<label>/events.jsonl` (`run_start`,
  `block` with its node path, `key`, `event`, `hp_read` each second, the hunt core's mirrored
  events and `hunt_start` / `hunt_end`, `run_end` with its words); the helper's Live tracker reads
  it (status.json `live`: `node`, `keys`, `fired`, `last_event`, `end.words` besides the runner's).
- **Not yet (stage 2)**: survival through the tick hook into the box's events; the respawn, the
  escape and the /where read as live blocks; the check of a project (POST /flows/run/check with
  the flow "project" is the runner's check for now).

## 4. Not in stage 1

Login, choose character, walk_to on the live player, talk to NPC, the shop / Kafra blocks.
