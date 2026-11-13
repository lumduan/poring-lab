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
| 2 | SURVIVAL out of the runner into the box's EVENTS (functions with a trigger, section 2a): heal (F1 at HP < 30 %), the Fly Wing (F8 on a boss or HP < 25 %), stock out, the dead jump, the Garm Baby, an unread position. The runner's own handler is switched off for each one the box plays (its flags exist: `flow_config.py`); the event plays through the tick hook. | live A/B against the monolithic runner: deaths, potions, flies, kills/h |
| 3 | The Knife swap as two FUNCTIONS of presses and a wait (section 2a), the respawn, the weight home, the end | live A/B: steals, swaps, respawn, home |
| 4+ | The CORE as PRIMITIVE blocks + ONE FUNCTION PER MONSTER (attack_myst_case, attack_cookie, ...; section 2a), and use_model (the trained data) | live A/B each: kills/h, loot/h, zeny/h, deaths (Batt's own run is the bar) |

## 2a. Batt's shape for stages 2-4 (2026-11-13 ~22:0x, Thai, translated)

"Heal, Fly Wing, Knife swap: write every one of them as a FUNCTION, don't make one block.
Heal: press F1 (the White Potion) when HP < 30 %. Fly Wing: press F8 when a boss is seen or
HP < 25 %. The Knife swap (Damascus): a function: press F4, wait 100 ms, press F5; the other way
back to the Knife: the same swapped. The flow page should also have a block to LOAD THE TRAINED
DATA (I saw you made one), with the monsters the bot already knows. The core of the hunt (look,
choose a target, walk up, strike, loot, explore): break it into functions, never one block, e.g.
attack_myst_case, attack_cookie, because in the future each monster may get a different skill or
killing technique, and on some we may not swap the knife at all."

So the box is written like this (a sketch; the spellings are the engine's):

    # tab survival: events are functions with a trigger
    @on(hp_percent() < 30, mode=INSERT)       def heal():      press_key("F1")   # White Potion
    @on(boss_seen() or hp_percent() < 25)     def fly_away():  press_key("F8")   # Fly Wing
    # tab knife
    def knife_to_damascus():  press_key("F4"); wait(0.1); press_key("F5")
    def damascus_to_knife():  ...the same, swapped
    # tab monsters: one function per monster, each its own technique
    def attack_myst_case(t):  knife_to_damascus(); strike(t); wait_kill(t); damascus_to_knife(); loot(t)
    def attack_cookie(t):     strike(t); wait_kill(t); loot(t)               # no knife swap
    # tab main
    use_model("xmas02")                       # the trained data: the monsters the bot knows
    while weight_percent() < 50:
        t = choose_target()
        if t is mystcase: attack_myst_case(t)
        elif t is cookie: attack_cookie(t)
        else: explore()

- The PRIMITIVE live blocks the runner is broken into (each the runner's own code behind it):
  use_model(model) (the trained data; its classes become the monsters the other blocks name),
  choose_target() / nearest(class) (a monster as a value), walk_to_target(t), strike(t),
  wait_kill(t), loot(t), explore(), use_skill(key) (a press), plus the sensors (hp, weight,
  boss_seen, sees(class), dead, the map's name).
- Every key in a function; every threshold in an event's condition; every technique per monster
  in that monster's function: nothing of it a setting hidden in one block.

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

## 5. The night of 2026-11-13 (Batt: "plan a long night, go on without me; I read it tomorrow")

In order; each step only after the one before is proven; nothing of the hunt plays worse:

1. Merge stage 1 (the live player, the one box, Run on /maps and /flows) and the slot item check
   (dungeon@9.47: a role key holding another item refuses the start); every suite green; deploy
   (backend, Run helper); the minimap and slot references built on main.
2. Live stage 1, short: place her on xmas_dun02 with the lab's setup tool (a GM @warp line, the
   setup's, as this afternoon), the start check all ✓, Run the one-box project for 10 min through
   the new player, Stop: she flies home. Compare with the runner's own numbers (kills/h, loot,
   deaths, potions). The Stormy Knight's schedule is checked first (memory: the MVP).
3. Stage 2: heal and the Fly Wing as the box's EVENTS (section 2a) through the tick hook; the
   runner's own potion and fly switched off where the box plays them; offline tests; live A/B
   (the runner vs the box), alternating runs, as many pairs as the night allows.
4. Stage 3: the Knife swap as functions, the respawn, the weight home (the Knife question in the
   report for Batt: the strike between F4 and F5, or not).
5. Stage 4 begins: use_model (the trained data block) and the first primitives (choose_target,
   strike, wait_kill, loot, explore) with one function per monster for the two most common
   monsters; offline first; live only once the A/B of stage 2 holds.
6. matpilot re-reviews the pages (read only); its findings fixed.
7. The report for Batt in the morning: every run's numbers, what was proven, what is not.

## 6. Stage 1 live (2026-11-13 23:01-23:11 ICT): PASS

- The one-box project (main 2a3c87a5+ / a8f7d486) played by scripts/flow_play.py, started on the
  host like a night pilot (the backend's write gate refuses the lab host itself, `lab_host_peer`,
  by design; the browser's Run takes the same path through the Run helper). Setup: the lab's GM
  `@warp xmas_dun02 7 21` (crusader.py gm, the chat guard and UI gate on), the chat input closed
  and read closed 12 times. No immunity.
- First two starts refused BEFORE ANY INPUT, as designed: the project's max_runtime_s 7200 is above
  the run's 600 s maximum (the test's copy then had 600 s); a 3rd identical warp line was refused
  by the chat guard.
- The run, 10 min, the hunt core in-process (one Agent, one input writer): the start check all ✓
  (the map's name read xmas_dun02 from the minimap; the role keys' items read from their icons);
  28 kills, 33 loot steps, 26 Knife openers, 0 deaths, lowest HP 61 %, 0 potions; the time box
  ended it and the runner flew her home (Butterfly Wings 3 -> 2); read after it from the screen:
  geffen (119, 40), the bag 36 % (865 / 2430).
- For comparison, the runner alone through the old Run path this afternoon (15:18-15:28, 10 min):
  23 kills, 27 loot steps, 26 Knife swaps. One pair is no A/B: stage 2's pairs are.
- Found: the detect server of a refused start kept the socket, so the next start's wait timed out
  (the runner used the running server; harmless); the helper's path starts it once per run.

