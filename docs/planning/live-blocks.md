---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~21:4x (Batt): build the live block player first; one box; break the runner into blocks. Stage 1 PASSED live (6); stages 2-4a A/Bs INCONCLUSIVE (7-9; the Knight). 2026-11-14: Batt's answers built (10, 11); s5ab-1114 FAIL by its bar on line 2 only, deaths 0/6 (10.2). Stage 5a (settings as blocks, the runner page gone) MERGED 17:2x (12), then rounds 20-24 of matpilot's browser review (12.4-12.8, all re-measured PASS): wrapped setting blocks, pickers for every value that is not a name (Batt 19:4x), no overlaps, exact Escape/Undo. Stage 5b-1 (HuntState, the loop as 20 steps; AST-proven the same program) MERGED 19:2x; its live A/B s5b1-ab FAIL by the pace p95 line only (noise), every outcome line passed (13.7; the parent's decision: keep it, go on). Stage 5b-2 (the steps as live blocks: a hunt tab, find_target / fight_target) MERGED 2026-11-15 03:0x; its live A/B s5b2-ab PASS on every line (14.11). The Christmas Goblin class round FAILED its precision bar (xmas02-detector S4.10), not deployed. 2026-11-15 (Batt's answers, 14.12): no hunt tab in the ready-made box (the runner block dissolves into function tabs: 5c); the first real block experiment, no Knife swap on the Christmas Cookie and the Cookie, BUILT offline and its A/B pre-registered 13:32 ICT (16), NOT run. Stage 5c (Batt 14.12: the runner block dissolved into functions in tabs -- hunt_loop() in main, role blocks, hunt_tick()'s step blocks) BUILT 2026-11-15 13:5x on feat/runner-blocks, offline-proven, merged with main 95583b9f there, not yet into main; its live A/B s5c-ab pre-registered (15.8), not run (15.11). 2026-11-16 (Batt 17 #6): the Fly Wing FIRST on a boss at any distance (18, dungeon@9.57 --fly-first, the setting fly_first, off until its A/B) BUILT offline on feat/fly-first; s7ab pre-registered (18.7), not run. ➡️ s7ab PASS (18.9), fly_first ON in the ready-made boxes; s8ab PASS (18.13), fly_first_hp ON too. 2026-11-17 (Batt 18.14: \"use it for real\"): xmas02sk DEPLOYED as xmas_dun02's model (18.15, dungeon@9.59; xmas02gb the reference), its live A/B s9ab pre-registered, ➡️ run 07:32-10:23: PASS on every line (18.16), xmas02sk stays the default; the stale re-fire (both arms) found, its fix 18.17. ➡️ dungeon@9.60 --fly-first-land BUILT offline (18.17; FF_LAND_S 0.75 s derived from 79 banked teleports; OFF everywhere until s10ab), s10ab pre-registered, ➡️ run 11:23-14:11: PASS on every line (18.18: B 0 stale re-fires of 7 alarm boss Fly Wings, A 4; deaths 0/0), fly_first_land still OFF (a person's decision). ➡️ 2026-11-17 ~15:0x ICT (Batt): fly_first_land ON in the ready-made boxes (18.18's last item; feat/fly-first-land-on), the registry and the reference boxes off."

role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [project-model.md, player-mode.md, ADR-0020, ../../scripts/dungeon_hunt.py, ../../scripts/runner_flow_export.py, ../../packages/poring_flow/src/poring_flow/runtime.py]
next_action: "18.18: fly_first_land ON in the ready-made boxes (Batt 2026-11-17 ~15:0x ICT), built on feat/fly-first-land-on (4a4e0022): merge it, then the frontend's test / typecheck / lint in its container; the clear-bag key fix (F2 vs F8) still open. ➡️ Older: 18.18: s10ab PASS; Batt decides whether fly_first_land goes ON in the ready-made boxes (17d18124's pattern). ➡️ Older: 18.17: merge feat/fly-first-land, then run s10ab FROM MAIN (stage10_ab.py plan / run / score --label s10ab --pairs 4 --minutes 20); PASS -> fly_first_land ON in the ready-made boxes (a person's decision); FAIL -> it stays off; the clear-bag key fix (F2 vs F8) is named there, not built. ➡️ Older: 18.16: s9ab PASS, xmas02sk stays deployed; 18.17: the stale re-fire fix (a sighting grabbed after the landing) built offline as a flag, then its own live A/B"

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
| 2 | SURVIVAL out of the runner into the box's EVENTS (functions with a trigger, section 2a): heal (F1 at HP < 30 %), the Fly Wing (F8 on a boss or HP < 25 %), stock out, the dead jump, the Garm Baby, an unread position. The runner's own handler is switched off for each one the box plays (its flags exist: `flow_config.py`); the event plays through the tick hook. ➡️ BUILT 2026-11-14 for heal and the Fly Wing (section 3.2; the switch is a new run() argument, not a flag); stock out, the dead jump, the Garm Baby and an unread position stay the runner's (a later stage) | live A/B against the monolithic runner: deaths, potions, flies, kills/h (➡️ pre-registered in 3.2) |
| 3 | The Knife swap as two FUNCTIONS of presses and a wait (section 2a), the respawn, the weight home, the end. ➡️ BUILT 2026-11-14 (section 3.3): the runner keeps WHEN, the box's functions say WHAT at its moments (knife_on / knife_back, the way home, the death dialog's two clicks: the new block click_at) and the weight home is a box event; the Knife's open question (the strike between F4 and F5, or not) is Batt's, both written | live A/B: steals, swaps, respawn, home (➡️ the stage-2 box vs the stage-3 box, pre-registered in 3.3) |
| 4+ | The CORE as PRIMITIVE blocks + ONE FUNCTION PER MONSTER (attack_myst_case, attack_cookie, ...; section 2a), and use_model (the trained data). ➡️ 4a BUILT 2026-11-14 (section 3.4): use_model("xmas02") and a `monsters` tab, one recipe per monster (attack_<class>(t, priority=1): knife_on, strike, wait_steal, knife_back, wait_kill, loot = today's technique); at its lock the runner asks the box which recipe attacks that species and plays it with its own code (no knife_on: no Knife swap on it); use_skill linted, not played (4b); 4b (the steps as blocks) not built | live A/B each: kills/h, loot/h, zeny/h, deaths (Batt's own run is the bar) (➡️ 4a: the stage-3 box vs the stage-4a box, an equivalence check, pre-registered in 3.4) |

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

## 2b. Stage 4's design (written 2026-11-14 ~00:5x, offline, before any stage-4 code)

The hunt core today is ONE state machine (scripts/dungeon_hunt.py run: ~4,000 lines of loop,
modes search / fight / after / loot, ~60 closures sharing its state). Breaking it into blocks
the player schedules one by one (Batt's "never one block") is the largest change of the four
stages, so it comes in two steps, each A/B'd against the step before; the hunt never plays worse.

**4a: the box decides WHICH technique per monster; the runner still plays every step.** The same
shape as stages 2 and 3 (the runner says WHEN, the box says WHAT):
- `use_model("xmas02")`: the trained data. It names an entry of
  packages/poring_flow/src/poring_flow/models.yaml (status `live`; its file and sha256 prefix are
  what the detect server prints). Its `classes` become the MONSTERS the other blocks may name
  (the editor's `mob` values: mystcase, cruiser, cookie, cookie_xmas, garm_baby); a name the
  model does not have is a lint error. Live: the runner's box detector takes that model instead
  of its map default (`box_model choice: map` today), refused before any input when the entry is
  not live, not on this map, or its sha256 differs from the server's.
- A `monsters` tab: one function per monster, its body a RECIPE of primitive calls, e.g.

      def attack_mystcase(t):   knife_on(); strike(t); wait_steal(t); knife_back(); wait_kill(t); loot(t)
      def attack_cookie(t):     strike(t); wait_kill(t); loot(t)        # no knife swap
      def attack_cruiser(t):    use_skill("F6"); strike(t); wait_kill(t); loot(t)

- When the runner LOCKS a target, it asks the box which function attacks that monster (by the
  detector's species of the box it struck, before the collapse) and plays the recipe's steps WITH
  ITS OWN CODE: strike = its strike (the two-motion click, the lead, the reach check), wait_steal
  = the bare-steal popup cue, wait_kill = its kill read (the exp line, else the kill gap),
  knife_on / knife_back = stage 3's functions at those points, loot = its loot step, use_skill =
  a press of a declared role. A recipe without knife_on: that monster is fought without the swap
  (Batt: "on some we may not swap the knife at all"). No function for a monster: the runner's
  default recipe, named in the lint as info ("cookie: no attack function; the runner's own").
- Which monster to choose stays the runner's (`--value-target`); 4a adds a per-monster
  `priority` (a function argument default, e.g. `def attack_mystcase(t, priority=3)`), so the
  person can change the order in blocks.
- Refused before any input: a recipe step outside that set, a recipe whose order cannot be
  played (wait_kill before strike, loot before wait_kill), knife_back without knife_on, a key
  that is not a role the start check reads.
- 4a's A/B: the stage-3 box (B3) vs the same box plus a monsters tab that writes TODAY's
  technique for every monster (B4 = an equivalence check: kills/h, steals/h, loot/h within the
  noise, deaths not more). Only after it holds, the first real experiment in blocks: no knife
  swap on cookie / cookie_xmas (which carry no steal worth the swap time), B4 vs B4'.

**4b: the recipe's steps run as blocks.** The player runs each primitive as a live block with the
runner's code behind it (choose_target() returns a monster value; walk_to_target(t), strike(t),
wait_kill(t), loot(t), explore() each one bounded call into the hunt core's state, through the
same hook and the same Agent). That needs the loop's state (lock, goal path, loot list, odometry,
the bare-steal controller, the memory) moved out of run()'s closures into one HuntState object
the primitives share: a refactor of the runner, done behind the CLI's unchanged behaviour
(`dungeon_hunt.py run` plays byte-for-byte as before; every existing runner test stays green).
4b is planned only after 4a's A/B.

What 4a does NOT change: search / patrol / explore, the loot model, the stock, the safety events
(stage 2), the way home (stage 3).

➡️ **4a BUILT 2026-11-14 (section 3.4)**, as designed here but for four decisions made while
building it, each written there: (1) a recipe is exactly one of two orders (the Knife swap's, or
the same without it): wait_kill and loot are in every recipe, since the runner reads every kill
and loots it; (2) the priority is a WEIGHT on the species' --value-target value (1 = today's
order); (3) use_skill is linted and refused live (4b); (4) use_model may name only the map's own
model live (the switch of the detect server's model is a follow-up). With --bare-ready (the Run
config's) the Knife is already on when the runner locks a target, so a recipe without knife_on
puts the dagger on first.

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
  own survival plays and the box's events wait. ➡️ Stage 2 (3.2): the box's own events play inside
  the hunt core now; the three built-ins still wait there (the runner's own rules cover them).
- **The record**: `/dev/shm/poring-lab-demo/<time>-play-<label>/events.jsonl` (`run_start`,
  `block` with its node path, `key`, `event`, `hp_read` each second, the hunt core's mirrored
  events and `hunt_start` / `hunt_end`, `run_end` with its words); the helper's Live tracker reads
  it (status.json `live`: `node`, `keys`, `fired`, `last_event`, `end.words` besides the runner's).
- **Not yet (stage 2)**: survival through the tick hook into the box's events; the respawn, the
  escape and the /where read as live blocks; the check of a project (POST /flows/run/check with
  the flow "project" is the runner's check for now). ➡️ The first BUILT 2026-11-14 (3.2); the rest
  is still not built.

### 3.2 ➡️ Stage 2 BUILT 2026-11-14 (feat/stage2; offline only, NOT run live)

Batt's words (section 2a): "Heal: press F1 (the White Potion) when HP < 30 %. Fly Wing: press F8
when a boss is seen or HP < 25 %", each a FUNCTION. The one box (`project_xmas_dun02.json` =
`xmasProject()`, byte-identical canonical; 0 lint errors) has a third tab, `survival`:

    @on(hp_percent() < 30, until=hp_percent() >= 31, priority=SURVIVAL, mode=INSERT, cooldown_s=0.7)
    def drink():
        heal()            # tab keys: press_key("F1"), the White Potion

    @on(sees_boss() or hp_percent() < 25, priority=CRITICAL, cooldown_s=3)
    def fly_away():
        fly_wing()        # tab keys: press_key("F8"), the Fly Wing

**Why these trigger fields** (the runner's own pacing, `dungeon_hunt.sustain`):
- `drink` is a REPEATING event (`until`): the runner presses a potion on every tick under its line,
  at most every 0.7 s (at most 3 in 2 s). The box: while HP reads under 30 %, a potion at most
  0.7 s after the last one ended (`cooldown_s`), until HP reads 31 % or more (the engine's
  hysteresis rule wants the stop one readout step past the start: the exact complement `>= 30`
  is a lint warning). INSERT, class survival: it never cuts what it lands in.
- `fly_away` is a ONE-SHOT (no `until`, no `rearm`): a Fly Wing on the edge -- a boss line, or HP
  falling under 25 % -- re-armed once its condition reads false and 3 s have passed since its Fly
  Wing (the runner's Fly Wing pace: 3 s; its boss fly waits 2 s). A boss line is a momentary cue:
  one Fly Wing per sighting, as the runner's. After the jump she is elsewhere: the next Fly Wing
  needs a new boss line or a new fall under 25 % (between them it is the potion's job); a fast
  fall right after a jump is the runner's HP-RATE fly, which stays the runner's. A repeating
  version would need `until` to hold, and `sees_boss()` is unknown outside the hunt core and on a
  quick read: it would repeat there. PRE-EMPT, class critical: a ReleaseAll before its press (the
  engine's rule), and it goes before `drink` when both are due (drink then plays at the same safe
  point, as the engine's inserts do after a pre-empt).
- Names: `escape` is a catalogue block (hp_critical's body) and `heal` the keys function; the
  sensor is `sees_boss()`, because `boss_seen` is a map event of the IR 2 samples
  (town_warp_farm, farm_loop) and a sensor of that name would make them invalid.
- The thresholds are Batt's: 30 % / 25 %. The runner's own (P2) are 40 % (potion) and 20 % (Fly
  Wing). The A/B measures that difference with the rest. ➡️ **2026-11-14 (Batt, section 10):** the
  one box drinks under 50 % (until 51 %) and eats the candies; this 30 % box is
  `project_xmas_dun02_stage2.json` (and the stage-3 / stage-4a copies).

**The sensor `sees_boss()`** (blocks.yaml `live: true`, cue; the simulator's scenario key;
`dungeon_hunt.HuntTick.boss`): the runner's OWN boss read of that tick -- its boss guard's
(--engage-screen) Battle Log line, damage or taken, whose bracketed name fits the map's boss or
one of its summons (`boss_of` over `boss_names`: the Stormy Knight, the Garm Baby, ...). It is not
the detector's boxes: the detector's Garm Baby box (--garm-fly) is the runner's Garm Baby rule
and stays the runner's. Read only inside a hunt core (elsewhere unknown: it never fires there);
guard_tick's quick reads carry no boss.

**How the hook plays them** (dungeon@9.49, `run(a, hook=..., session=..., box_plays=...)`):

    the runner's tick (run loop)                         the player (flow_play LivePlayer.hunt_tick)
      HP read; the stop hook (stage 1)
      the Battle Log's new lines -> boss_hit
      box_on: hook_survive(HuntTick(..., boss_hit), box_press)
                                                  -->  the box's sensors from the tick
                                                       _perceive(its events) -> _fire (limits)
                                                       the pre-empts now (ReleaseAll, body), then
                                                       the inserts (_run_inserts), each press ->
                       box_press(code, why)       <--  the runner's OWN press of that role: a
                                                       stand-up, the unread escape's end, the dagger
                                                       before a bare fly, its count, its record,
                                                       the stock read after it
      a box Fly Wing: the runner's own after-the-fly steps (fly_at, the target / loot / mode /
        position reset, the 3-s Fly Wing pace, 1 s) and on a boss line its boss fly's end (continue)
      sustain(off=the box's): the HP-rate fly, Heal; the Garm Baby box; the boss guard (no fly of
        its own for a Battle Log line), the box engagement it blocks for 30 s
    guard_tick, inside a long action: the same call (quick, no boss); a box Fly Wing ends the action

- A tick with no HP read and no boss line decides nothing (the runner's own sustain reads nothing
  without an HP read either).
- An event's limit (handler_runaway, max_per_run) or a key the hunt core does not hand the box ends
  the run through the runner's NORMAL end (its safe-end escape, its way home), and the player ends
  with that reason, in words.
- `live.hunt_plan` (the ONE place) refuses before any input an event on a hunt-core node that reads
  anything but hp_percent / sp_percent / sees_boss, presses another key than dungeon_hunt's heal and
  fly ones, holds a wait / loop / exit / stop, presses nothing, presses the Fly Wing on a condition
  that reads neither HP nor the boss, escalates, or does not resume (the backend's `not_live` names
  the same).

**What the box plays and what stays the runner's** (per run; `box_plays` from `live.hunt_plan`):

| The runner's handler | With the one box | Why |
|---|---|---|
| the potion (`potion_below`, 40 %) | OFF: `drink` | an event presses the heal key |
| the Fly Wing on HP (`fly_below`, 20 %) | OFF: `fly_away` | an event presses the fly key on hp_percent |
| the boss fly (a Battle Log boss line) | OFF: `fly_away` | an event presses the fly key on sees_boss |
| the HP-RATE fly (150 HP/s under 50 %) | the runner's | not in the box (it waits 3 s after any box Fly Wing, as after its own) |
| the Garm Baby box (--garm-fly), the boss guard's 30-s box avoidance | the runner's | not in the box |
| stock out / stock keep, the dead jump, an unread position, the NPC guard, the safe end's escape, the knife, the way home | the runner's | stage 3 and later |

A box without such events (no survival tab) passes no `box_plays`: the runner plays exactly as in
stage 1, and the CLI (`dungeon_hunt.py run`, the old Run path) passes neither hook nor box.
➡️ **2026-11-14 (matpilot round 17 N1, project-model.md 10c):** the pages say this table per
project: `live.takeovers` (from `hunt_plan`, its `play_by`) gives each play, the run settings it
replaces (`PLAY_SETTINGS`: potion_below, fly_below, weight_home, respawn_at / respawn_confirm_at)
and what stays the runner's (fly_rate, fly_rate_below), in POST /flows/lint's `box`; Before Run's
rows, the tab strip "IN A RUN" and the /maps inspector read it.

**The record**: the player's events.jsonl has each event fired (`event`: its name, its node path,
`reading` -- the values its condition read --, `in: "hunt"`), the runner's press records mirrored
(`press` what potion / fly, why "box drink (hp_percent 28)" or "box fly_away (hp_percent 100,
sees_boss True)": the live line counts potions and flies from them), `hunt_start` with the events
and box_plays, `hunt_end` with its survive calls. The runner's own session: run_start `box_plays` /
`box_version`, `escape {by: "box", boss}`, `boss_guard {box: ...}`, the counters box_potion /
box_fly.

**The engine, corrected (ADR-0020 Amendment F)**: an insert's pacing counts `cooldown_s` from the
end of its last body run; before, the fire's own mark held it back `cooldown_s` (the potion would
have waited 0.7 s). The simulator plays the box's events too (a scripted `sees_boss`).

**Versions**: `dungeon_hunt.VERSION` stays dungeon@8.7; `SURVIVAL_EVENTS_VERSION` = `live.VERSION`
= `flow_play.VERSION` = 9.49 (stage 1's `LIVE_BLOCKS_VERSION` stays 9.48); the runner export
counts neither (no feature of the runner's own play: its description is unchanged).

**THE A/B** (`scripts/stage2_ab.py`; run by the parent; NOT run yet):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage2_ab.py plan  --label s2ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage2_ab.py run   --label s2ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage2_ab.py score --label s2ab-1114

- Before it: merged and deployed; ASSIST; the Rogue in the game (on xmas_dun02 or at her save
  point); the Run helper idle; no chain. `plan` prints everything it will do and refuses before any
  input if the box cannot play.
- The arms, the same runner settings for both (the Run config, the box's five keys, --minutes M):
  A = `dungeon_hunt.py run` with the old Run path's argv (`flow_run.command`, player mode); B =
  `flow_play.py play` of the box (its time box M minutes) with those settings as its runner
  config. Order AB, BA, AB, BA (each pair's first arm alternates).
- The setup before every run, the same for both: the read (weight, the F1 / F8 / F9 counts);
  clear-bag (etc, use) at 40 % or an unread weight; the lab GM's `@warp xmas_dun02 7 21` or
  `114 23`, alternating (the chat guard never meets a line 3 times in a row), until the minimap
  reads xmas_dun02; `@item 602` only under 2 Butterfly Wings (to 3), `@item 601` under 7 Fly Wings
  (to 10), `@item 504` under 7 White Potions (to 10); the chat input closed and read closed. The
  detect server once for the series. A STOP file in its folder ends it before the next run.
- The score per run, from the RUNNER's own session (the same reader for both arms) and B's player
  session: minutes, deaths, potions, Fly Wings by cause (hp, rate, boss, garm, pos_unread, stuck,
  unreach, end, other), kills / h, loot steps / h, the lowest HP, the box's events fired.

**THE PRE-REGISTERED BAR** (written 2026-11-14, before any live run; `stage2_ab.BAR`): B must hold,
against A, over the valid pairs:

| Line | B must hold |
|---|---|
| deaths | B's total <= A's total |
| potions | B's potions per hour <= A's + 6 |
| Fly Wings (all but the end's own escape) | B's per hour <= A's + 4 |
| kills per hour | the mean paired difference (B - A) >= -2 x its standard error, over at least 3 valid pairs |
| a valid run | at least 80 % of M minutes on the runner's own clock; a pair counts when both runs are valid |

Reported, not judged: loot steps per hour (the mean paired difference), the lowest HP, the boss
flies, the Garm Baby flies, the box's events fired. The verdict: PASS when every judged line
passes, FAIL when one fails, INCONCLUSIVE when fewer than 3 pairs are valid (kills per hour
unjudged) and nothing failed. Why these margins: tonight's two 10-min runs pressed 0 potions and
0 Fly Wings, so the counts are small; "6 potions / 4 Fly Wings an hour more" is about one more
potion every 10 min and one more Fly Wing every 15 min -- within reason for a lower potion line
(30 % vs 40 %) and a higher Fly Wing line (25 % vs 20 %); kills per hour is held to the pairs' own
noise.

**Not yet (stage 3)**: the Knife swap as two functions (F4, wait 100 ms, F5 and back), the respawn,
the weight home, the end; stock out, the dead jump, the Garm Baby, an unread position as the box's
events; the built-ins' bodies (respawn, escape, /where) live; `sees_boss()` outside a hunt core.
➡️ The first four BUILT 2026-11-14 (section 3.3); the rest is still not built (a later stage).

### 3.3 ➡️ Stage 3 BUILT 2026-11-14 (feat/stage3; offline only, NOT run live)

Batt's words: "The Knife swap (Damascus): a function: press F4, wait 100 ms, press F5; the other
way back to the Knife: the same swapped" (section 2a); "make respawn a function block, in case
another server's menu differs; make everything editable in blocks, don't hard-code" (2026-11-13);
"if the weight is over 50 %, use a Butterfly Wing to go back to town" (dungeon@9.41). The runner
keeps deciding WHEN; the box decides WHAT is pressed at each of the runner's moments. The one box
(`project_xmas_dun02.json` = `xmasProject()`, byte-identical canonical; 0 lint errors, run allowed,
the same four warnings as stage 2's box) has five tabs now, its Python view (➡️ since stage 4a,
3.4, the one box also has use_model and a monsters tab; the box as stage 3 left it is kept byte for
byte as `project_xmas_dun02_stage3.json`, stage3_ab.py's B3 and stage 3's tests):

    # tab main (the same shape: the save point, the hunt core, stop)
    dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back, home=fly_home,
                 respawn=respawn_button, respawn_confirm=respawn_ok)
    # tab keys: every key a function (the item on each slot)
    heal F1, fly_wing F8, butterfly_wing F9, wield_knife F4, wield_damascus F5
    # tab survival: stage 2's drink and fly_away, and the weight home
    @on(weight_percent() >= 50, priority=UPKEEP, max_per_run=1)
    def bag_full():
        stop("home")
    # tab knife: the swap at the runner's two moments (the strike between: the runner's own today)
    def knife_on():     wield_knife()        # before the steal strike
    def knife_back():   wield_damascus()     # after the steal's cue, or its time box
    # tab exits: the way home and the death dialog
    def fly_home():        butterfly_wing()
    def respawn_button():  click_at(645, 481)   # the death dialog's first button
    def respawn_ok():      click_at(714, 405)   # this client's confirmation: OK

The stage-2 box is kept, byte for byte, as `project_xmas_dun02_stage2.json` (the A/B's B2 arm and
stage 2's own tests; `scripts/stage2_ab.py` plays it as its B arm).

**Which role functions the box plays** (`poring_flow.functions.is_body`): a role function that is
exactly ONE press_key statement is the stage 1-2 KEY shape -- the runner presses that key itself, as
before (the same key at the same moment either way). Anything else -- a call of a key function,
presses and waits -- is a BODY the hunt core CALLS at its moment. So the stage-2 box (every role one
press_key) plays exactly as stage 2; the one box's knife tab calls the key functions, so the box
plays its swap. A body's KEY for the Run settings and the start's slot check is its FIRST press
(`functions.role_key`); `runner_keys` gives the same five keys for both boxes (the same runner
argv).

**How the hunt core calls them** (dungeon@9.50, `run(a, hook=..., session=..., box_plays=...,
box_roles=...)`; `box_roles` = the called roles, each with where its body leaves her):

| The runner's moment | Today's press (stays when the box does not play it) | With the box |
|---|---|---|
| the opener before the steal strike (`opener_seq`: a press, the read-back, at most one more press) | `opener_press`: the Knife's key | `box_call("knife_on")`: the body's steps; the runner's read-back and retry unchanged |
| the swap back (`bare_equip_seq`: on the steal's cue, its time box, the HP floor, the fight's end, the run's end) | `press("equip")`: the dagger's key | `box_call("knife_back")` |
| the escape's dagger before a Fly Wing (`BareCtl.escape`, "safety") | `press("equip")` | the SAME: the runner's own key, never delayed by a body's waits |
| the end's way home (`player_home_end`: the count read, the stand-up, the load wait) | `press("home")` | `box_call("home")`; no Butterfly Wing after a death (the runner's rule) |
| the death exit (`respawn_end`: the dialog read, the confirmation read, the load wait) | two-motion clicks at `--respawn-at` / `--respawn-confirm-at` | `box_call("respawn")`, then (the confirmation read) `box_call("respawn_confirm")`; no confirm function: none pressed |
| the UI watch's weight read (every UI_EVERY_S, never in a fight) | `weight_home_due(--weight-home)` on the read | the box's weight events on THAT read (`HuntTick.weight_pct`); an unread weight drawn red keeps the runner's own rule |

- The player plays a call's STEPS, prepared before any input (`live.hunt_plan` -> `HuntPlan.calls`:
  presses, waits, clicks, flattened through calls with literal arguments) NOW, while the runner
  waits: a press through the runner's own press of a key of that moment (the opener's three lines,
  `press()`'s count, record and stock read), a click through the runner's own two-motion click
  (dungeon@9.41's respawn press, now `two_motion_click`), a wait slept exactly. No engine tick sits
  between two steps (the runner's timing: the default bodies are one press each, so the keys go out
  exactly as today). A call plays during the runner's normal end too (the swap back, the way home)
  after a box event ended the run.
- The weight event: on the UI watch's read the player evaluates ONLY the events that read
  `weight_percent()`, by the engine's rules; a due one plays at once (a pre-empt: its ReleaseAll,
  then its `stop`); the runner ends its run there with the reason `weight_home: the box: ...`, its
  NORMAL end (the swap back, the way home); the player then ends with `home` ("The flow stopped
  after N min. The flow stopped at xmas_dun02/survival/bag_full.0 (stop "home"); the hunt core flew
  her home."). On every other tick the weight events are not evaluated (and no insert plays on the
  weight read).

**What may be written** (`live.hunt_plan` / `live.problems`, the backend's `not_live`; each refused
before any input, named):
- knife_on / knife_back: presses of the two knife keys only (the role keys the slot check reads),
  waits and calls; at most 4 presses and 1 s of waits in all (`functions.STEPS_MAX`,
  `STEPS_WAIT_MAX_S`); knife_back ends on the dagger's key; no click, no loop, no if, no sensor
  read, no exit, no stop.
- home: ONE press of the home key (one Butterfly Wing: the runner's rule), waits around it.
- respawn / respawn_confirm (optional roles; respawn_confirm only with respawn): click_at and waits
  only, every point inside the game picture (1280 x 720).
- click_at ANYWHERE else (a main, an event, a function no respawn role names, an exit's function, a
  call of a clicking function) cannot play live ("a click anywhere else in the world is stage 4's").
- an event that reads `weight_percent()` inside the hunt core reads only it, is a pre-empt, and its
  body is ONE stop.
- the runner refuses (`box_plays_refused`, before any input): the box's Knife swap without the
  run's knife swap (--bare-steal + --steal-opener), the other Knife answer with --bare-ready, the
  map's exits without --player-mode, the respawn with the run's respawn off, the way home without a
  Butterfly Wing key, a play without its functions, a hook without `call`.
The lint names the same shapes in the editor (`hunt_function`: a body's caps, its keys, the
respawn functions' clicks).

➡️ **DECIDED 2026-11-14: (a) KEPT** (Batt delegated it to the agent: section 11.3). The question as it stood: **THE OPEN QUESTION FOR BATT (both are written and both play):** "press F4, wait
100 ms, press F5" -- is the strike between F4 and F5, or not?
- (a) The strike between (BUILT as the one box's, and the runner's own today): knife_on = the
  Knife's key before the steal strike, knife_back = the Damascus's key after the steal's cue. Batt's
  own run (2026-11-12): the Damascus 1.36 s after the steal, 91 % stolen.
- (b) No strike between: ONE function at the opener's moment, `def knife_on(): wield_knife();
  wait(0.1); wield_damascus()`. The runner then reads back the dagger worn (`opener_seq(ends=
  "armed")`): one swap per target, no bare phase, nothing to swap back after the steal, the strike
  goes on with the Damascus (`bare_opener_through`). It needs the knife's bare_ready off (refused
  otherwise: --bare-ready waits with the Knife on between targets).
Batt picks; the box changes in its knife tab only.

**What stays the runner's**: WHEN (every moment above, its read-backs, retries and waits); the
escape's dagger before a Fly Wing; the HP-rate fly, the Garm Baby, stock out, the dead jump, an
unread position, the NPC guard; the weight's red-line rule on an unread weight; the Butterfly Wing
count read, the stand-up and the load wait; the death dialog's and the confirmation's reads.

**The record**: the player's events.jsonl has each call (`call`: the role, the function, the
runner's why, its node path, its steps, `in: "hunt"`) with its keys and clicks, the weight event
fired (`event` bag_full with its reading), `hunt_end` with its `calls`. The runner's session:
run_start `box_roles` / `box_version` 9.50, `box_call` (role, why, ms), `click` (the respawn's),
`weight_home {by: "box"}`, `bare` opener events with `ends: "armed"` for answer (b), the counters
box_call_<role>, click_box_<role>, bare_opener_through.

**Versions**: `dungeon_hunt.VERSION` stays dungeon@8.7; `BOX_FUNCTIONS_VERSION` = `live.VERSION`
= `flow_play.VERSION` = 9.50 (stage 2's `SURVIVAL_EVENTS_VERSION` 9.49 and stage 1's 9.48 stay);
the runner export counts none of them (`runner_flow_export.NOT_FEATURES`).

**Known differences to watch live** (B3 against B2):
- the weight line: B3's event reads the ROUNDED percent (`weight_percent() >= 50`: a share from
  0.495), the runner's own exit a share over 0.50: B3 may go home half a point earlier, at the same
  moment (the UI watch);
- the end's words: B3 ends `home` (the flow's stop), B2 `relocate_no_block` (she is on geffen);
- a ReleaseAll at the weight event's pre-empt (nothing is held at the UI watch);
- every Knife press, the way home and the respawn go through the hook: the same keys and clicks
  at the same moments, one Python call and one record more each;
- in a 20-min run with the bag cleared at 40 %, the weight line and a death may not happen: their
  lines are then "not exercised" (reported, not judged).

**THE A/B** (`scripts/stage3_ab.py`, a sibling sharing `stage2_ab.py`'s setup, detect server, run
and runner score; run by the parent; NOT run yet):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage3_ab.py plan  --label s3ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage3_ab.py run   --label s3ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage3_ab.py score --label s3ab-1114

- The arms, both `flow_play.py play` with the same runner config (the same five keys, checked):
  B2 = the stage-2 box, B3 = the one box (➡️ since stage 4a: `project_xmas_dun02_stage3.json`,
  the box as stage 3 left it; stage4_ab.py measures the one box). Order B2 B3, B3 B2, ... The setup
  before every run is stage2_ab's (3.2). `plan` refuses before any input if either box cannot play,
  if B2 plays a stage-3 function or if B3 plays none.
- The score per run (the runner's own session, the same reader for both): stage 2's lines and the
  Knife (openers, opener fails, swaps back, swap fails, steals = swaps back on the steal's cue, the
  opener -> steal seconds, the swap-back read-back ms), the respawn (pressed, arrived), the way home
  (pressed, arrived), the weight (the highest read, a weight-home end and by whom), the box's calls.

**THE PRE-REGISTERED BAR** (written 2026-11-14, before any live run; `stage3_ab.BAR`): B3 must
hold, against B2, over the valid pairs:

| Line | B3 must hold |
|---|---|
| deaths | B3's total <= B2's total |
| kills per hour | the mean paired difference (B3 - B2) >= -2 x its standard error, over at least 3 valid pairs |
| steals per hour | the same rule (the swaps back on the steal's cue) |
| failed Knife swaps (opener fails + swap-back fails) | B3's per hour <= B2's + 2 |
| the respawn | every B3 death respawned and arrived (judged when B3 died) |
| the way home | B3's share of non-death runs that pressed the Butterfly Wing and arrived >= B2's |
| the weight home | every B3 run that read the bag at >= 50 % ended by the box's weight event, and no box weight event fired under 49.5 % (judged when a B3 run read >= 50 %) |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: loot steps per hour, the Knife openers per hour, the steal share (steals per
opener; Batt's own: 91 % stolen), the opener -> steal seconds and the swap-back ms (Batt's own: the
Damascus 1.36 s after the steal), the box's calls. The
verdict: FAIL when a judged line fails; INCONCLUSIVE when fewer than 3 pairs are valid (kills and
steals unjudged) and nothing failed; else PASS, with the respawn / way-home / weight lines that had
nothing to judge listed as not exercised. Why these margins: the default bodies press the same keys
at the same moments, so the Knife lines are held to the pairs' own noise, and two failed swaps an
hour is about one in a 30-min run; the exits are held to "every time".

### 3.4 ➡️ Stage 4a BUILT 2026-11-14 (feat/stage4; offline only, NOT run live)

Batt's words (section 2a): "The core of the hunt (look, choose a target, walk up, strike, loot,
explore): break it into functions, never one block, e.g. attack_myst_case, attack_cookie, because
in the future each monster may get a different skill or killing technique, and on some we may not
swap the knife at all"; "the flow page should also have a block to LOAD THE TRAINED DATA, with the
monsters the bot already knows". 4a is section 2b's first step: the box decides WHICH technique
per monster; the runner still plays every step with its own code (the runner says WHEN, the box
says WHAT).

**Today's technique per species, as found in the code (feat/stage4's line numbers):**
- The species the runner strikes on xmas_dun02 are the four of xmas02 that collapse to "monster"
  (scripts/unit_detector.py:89 MAP_MODELS["xmas_dun02"].collapse: mystcase, cruiser, cookie,
  cookie_xmas). garm_baby is never struck: it is not collapsed (an alarm class; --garm-fly takes
  the Fly Wing on it). models.yaml now records the four as xmas02's `strikes` (drift-tested
  against MAP_MODELS).
- The Knife swap applies to EVERY target, whatever its species: the Run config
  (scripts/flow_run.py:159-162: knife_swap, bare_ready, steal_cue popup, swap_gap) puts the Knife
  on while idle (--bare-ready: BareCtl.ready_tick, scripts/dungeon_hunt.py:5627, called at :9875 --
  searching, no lock, HP >= 50 %), strikes the new target bare at once (BareCtl.before_strike
  :5669, _begin), puts the Damascus back on the steal's popup cue (bare_steal.BareSteal.tick), its
  time box (BARE_MAX_S 8 s, scripts/bare_steal.py:63) or the HP floor (BARE_HP_MIN 0.5, :64) --
  an escape puts it on first; with --bare-ready a fight that ends bare stays bare --; then the kill
  read (the EXP line, --kill-gap) and the loot step (--loot trim, the xmas02fi5 item model).
  Neither BareCtl nor BareSteal looks at the species; a plant is struck as it is.
- What differs per species today is only the CHOICE: --value-target (flow_run.py:176;
  scripts/value_target.py) ranks the candidates by value(species) / (1 + d / 150 px), the values
  read at run time from data/econ/maps.json (Myst Case ~262 z a kill, Christmas Cookie ~125, Cookie
  ~100, Cruiser ~76; value_target.py's docstring). The species of a box is the detector's own class
  before the collapse (dungeon_hunt.box_species :2883).
So "today's technique for every monster" is one recipe, the same four times:
`knife_on(); strike(t); wait_steal(t); knife_back(); wait_kill(t); loot(t)`.

**The one box** (`project_xmas_dun02.json` = `xmasProject()`, byte-identical canonical; 0 lint
errors, the same four warnings as stage 3's, run allowed; the stage-3 box kept byte for byte as
`project_xmas_dun02_stage3.json`: stage3_ab.py's B3 and stage 3's tests) has six tabs now (➡️
since 2026-11-14, section 10, it also drinks under 50 % and eats the candies; the box as 4a left
it is `project_xmas_dun02_stage4.json`, stage4_ab.py's B4):

    # tab main: the trained data before the hunt core
    assert_save_point(cell("geffen", 119, 40))
    use_model("xmas02")
    dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back, home=fly_home,
                 respawn=respawn_button, respawn_confirm=respawn_ok)
    stop("home")
    # tab monsters: one function per monster xmas02's runner strikes, each TODAY's technique
    def attack_mystcase(t, priority=1):
        knife_on()
        strike(t)
        wait_steal(t)
        knife_back()
        wait_kill(t)
        loot(t)
    def attack_cruiser(t, priority=1): ...      # the same
    def attack_cookie(t, priority=1): ...       # the same
    def attack_cookie_xmas(t, priority=1): ...  # the same

**The new blocks** (blocks.yaml; poring_flow/recipes.py holds every rule, the lint and the live
set read it):
- `use_model(model)` (core: no input): a models.yaml entry by id, in a map node's main, one
  statement, before its dungeon_hunt. Its `strikes` are the monsters the recipes may name.
- `strike(t)` (combat.attack_target), `wait_steal(t)`, `wait_kill(t)` (core: the runner's reads),
  `loot(t)` (the existing loot block: `target` is its first parameter now, `item` by name; `loot()`
  without a target is the old block, not live). Live ONLY inside a recipe; their binding is the
  runner's (live.OWN_BINDING).
- `use_skill(key="F6")`: the existing block gained a `key` parameter (a hotbar key; `skill` no
  longer required). Expressible and linted in a recipe; REFUSED live in 4a ("stage 4b"): binding it
  safely needs a declared role key the start's slot check reads, its SP read and its cast /
  after-cast waits, none of which the runner models at the strike.
- A RECIPE: a function named `attack_<class>` (the box's tab `monsters`), its first input the
  target `t`, an optional `priority=N`, its body exactly one of the two orders the runner plays
  (recipes.SHAPES): `knife_on, strike, wait_steal, knife_back, wait_kill, loot` (the Knife swap)
  or `strike, wait_kill, loot` (no Knife swap). knife_on() / knife_back() are calls of the hunt
  core's own Knife functions (its knife_on / knife_back roles: stage 3's bodies, or one press_key).

**How the hunt core asks** (dungeon@9.51, `run(a, hook=..., box_plays=..., box_roles=...,
box_model=..., box_recipes=...)`; BOX_PLAYS gains "model" and "recipes", == live.PLAYS):

    the player (flow_play, before any input)           the runner (dungeon_hunt.run)
      live.hunt_plan: model, recipes (species -> steps)
      run(box_model=<models.yaml entry>,          -->  box_model_refused: live, a detector, for
          box_recipes=<species -> recipe>)              this map, the file and sha256 its box
                                                        detector loads here (MAP_MODELS, GPU_WEIGHTS)
                                                        recipes_refused: shapes, species, knife,
                                                        priority (before any input)
                                                        box_model record: choice "box"
                                                        a strike: box_target's box -> its species
                                                        (BoxWatch.near: last_species), a queue pick's
                                                        entry; any other strike: unknown (None)
                                                        BareCtl.before_strike, a NEW target's
                                                        decision (its LOCK): recipe() ->
      HuntHook.recipe(species, why)               <--  hook_recipe -> recipe_choice(answer, plan)
      -> the plan's recipe (a `recipe` record)
                                                        knife True: exactly as before
                                                        knife False: _no_knife -- armed: struck as
                                                        it is; bare (--bare-ready): the dagger on
                                                        first ("recipe", read back), the aim read
                                                        again; the next idle: the Knife again
      strike / wait_steal / knife_back / wait_kill / loot: the runner's own code, at its moments

- The answer is asked ONCE per target (BareCtl's decision point: a new target's first strike);
  only an answer that IS the run's plan for that species plays (`recipe_choice`); no function for
  a species, an unknown species, a disagreement (counted `recipe_mismatch`): the runner's own
  recipe -- its Knife swap, as before.
- The priority: a recipe's `priority` default weighs its species' --value-target value
  (`recipe_values`: value x priority; 1 or none written: the values as they are, so B4 plays the
  same order). A priority other than 1 needs the run's value target (refused otherwise). The one
  box writes priority=1 on each: the place to change it, with today's order.

**What the box decides** (4a): the hunt core's model (use_model: today only the map's own model
can be named live, below) and, per species, the Knife swap or none, and a weight on its value.
**What stays the runner's**: WHEN (the lock, the swaps' moments, the cue, the kill read, the loot
step), WHICH monster (its candidates, its value ordering), how it strikes (the two-motion click,
the lead, the reach check), the search / patrol / explore, the loot model, the stock, the safety
events (stage 2), the way home and the respawn (stage 3). **Linted, not played (4b)**: use_skill
in a recipe; any other order or step; a recipe without loot or without wait_kill (the runner loots
and reads every kill); a recipe CALLED from a block; the primitives anywhere but in a recipe;
choose_target() and the steps as blocks the player schedules (2b's 4b).

**The model switch is a follow-up**: the runner's box detector loads the map's own model
(unit_detector.for_map / for_map_gpu) and the detect server is started once per series with the
pinned weights. A use_model that names another model than the map's own (v1 on xmas_dun02, a
future model) is REFUSED before any input in named words ("another model than the map's own is a
follow-up: the detect server serves the map's; a run never restarts it"). xmas02 IS the map's
model (xmas02gb-last-736x1280.onnx, b22d972b714f), so the one box plays exactly the detector it
played before; the record says `box_model {choice: "box", box_model: "xmas02"}`, and the runner
checks the loaded file again after the watcher starts.

**Refused before any input** (live.problems / hunt_plan, the backend's not_live, and the lint's
errors; each named): a recipe step outside the set; an order the runner cannot play (wait_kill
before strike, loot before wait_kill, knife_back without knife_on, wait_steal without knife_on,
knife_on without knife_back or without wait_steal, knife_back before the cue, a step twice, no
strike, no wait_kill, no loot); a target that is not the recipe's own input; a recipe for a class
the model lacks, or one the runner never strikes (garm_baby); recipes without use_model; a
use_model that is not live, not a detector, not for the map, unknown, misplaced or written twice;
use_skill in a recipe (4b); a primitive outside a recipe; a recipe called from a block. The
runner's own (`box_plays_refused` -> `recipes_refused`, `box_model_refused`): the plays without
their arguments, a recipe the runner cannot play, a Knife recipe without the run's Knife swap,
recipes in a run with no Knife swap at all (nothing for them to decide in 4a), a priority without
--value-target, a hook without `recipe`, a model that is not the run's box detector (above). The
lint's `recipe_default` (info) names each monster without a function: "cookie: no attack
function (attack_cookie); the runner's own recipe (...)".

**A box without use_model and a monsters tab plays exactly as stage 3**: its hunt plan has no
model and no recipes, so `RunnerPlan.box_kwargs()` passes run() exactly stage 3's arguments (the
test takes the one box, removes use_model and the tab, and checks the run() call byte for byte
against the stage-3 box's); the CLI and the old Run path pass none at all (`return run(a)`).
VERSION stays dungeon@8.7; BOX_RECIPES_VERSION = live.VERSION = flow_play.VERSION =
recipes.VERSION = 9.51 (stage 3's 9.50, stage 2's 9.49 and stage 1's 9.48 stay), in
runner_flow_export.NOT_FEATURES.

**The record**: the runner's session: run_start `box_model` / `box_recipes` (box_version 9.51),
the box_model event's `choice: "box"`, a `recipe` event at each lock (species, by, knife,
function; `mismatch` when the answer was not the plan), `bare {what: "recipe", knife: false}` for
a monster struck without the Knife, the counters recipe_knife / recipe_no_knife /
recipe_species_<sp> / recipe_mismatch / bare_recipe_no_knife / bare_equip_recipe. The player's
events.jsonl: `hunt_start` with box_model, box_recipes and default_species, a `recipe` record per
lock (species, the function, its node path, its steps), `hunt_end` with `recipes`.

**The editor** (/flows): in a map node's main the Movement category offers `use_model(...)`; a tab
named `monsters` gets a Monsters category: one `def attack_<monster>(t, priority=1)` per monster
of the node's model (its use_model; models.yaml `strikes`), each monster as a `mob(<id>)` value,
and the recipe's steps in their order (knife_on(), strike, wait_steal, knife_back(), wait_kill,
loot; use_skill marked 4b). The primitives are no longer offered under "More skills". Run's
readiness follows the recipes too (liveready: a use_model reaches the node's attack_* functions).

**Known differences to watch live** (B4 against B3):
- every lock asks the hook (one Python call and one record more per target);
- the box_model record says `choice: "box"` (the same file, the same sha256);
- a strike that knows no species (the ring scan, a plant, a loot or walk SWORD, the cursor) gets
  the runner's own recipe -- for B4 the same as its recipes, so no difference; for a later B4'
  (no Knife on cookies) those strikes still swap;
- nothing else differs by construction: every recipe is today's (stage4_ab.py's plan refuses a B4
  that is not).

**THE A/B** (`scripts/stage4_ab.py`, a sibling sharing stage3_ab.py's and stage2_ab.py's setup,
detect server, run and score; run by the parent; NOT run yet):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage4_ab.py plan  --label s4ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage4_ab.py run   --label s4ab-1114 --pairs 4 --minutes 20
    .venv/bin/python scripts/stage4_ab.py score --label s4ab-1114

- Before it: merged and deployed (the backend, the Run helper); ASSIST; the Rogue in the game; the
  Run helper idle; no chain. `plan` prints everything it will do and refuses before any input if
  either box cannot play, if B3 names a model or recipes, if B4 names none, if B4's recipes are
  not today's technique, or if the two boxes' stage-3 functions or keys differ.
- The arms, both `flow_play.py play` with the same runner config (the same five keys, checked):
  B3 = the stage-3 box, B4 = the one box (➡️ since 2026-11-14: `project_xmas_dun02_stage4.json`,
  the box as 4a left it; section 10). Order B3 B4, B4 B3, ... The setup before every run is
  stage2_ab's (3.2).
- The score per run (the runner's own session, the same reader for both): stage 3's lines and the
  recipes asked (per species), the locks without the Knife, the mismatches, the loot steps per
  hour, the openers per hour, and the species mix of the box strikes (box_target's struck box).

**THE PRE-REGISTERED BAR** (written 2026-11-14, before any live run; `stage4_ab.BAR`): B4 must
hold, against B3, over the valid pairs:

| Line | B4 must hold |
|---|---|
| deaths | B4's total <= B3's total |
| kills per hour | the mean paired difference (B4 - B3) >= -2 x its standard error, over at least 3 valid pairs |
| steals per hour | the same rule (the swaps back on the steal's cue) |
| loot steps per hour | the same rule |
| Knife openers per hour | B4's series rate within +-20 % of B3's |
| the recipes | every B4 run that struck asked the box at its locks, no lock's answer differed from the run's plan (recipe_mismatch 0), and B3 asked none |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: the species mix of the strikes per arm (box_target's struck box), B4's
recipes asked per species, the locks without the Knife (0 for today's recipes), the steal share
and the opener -> steal seconds. The verdict: FAIL when a judged line fails; INCONCLUSIVE when
fewer than 3 pairs are valid (kills, steals and loot unjudged) and nothing failed; else PASS. Why
these margins: B4 plays the same technique by construction, so the rates are held to the pairs'
own noise; the openers (about one a target, ~50-75 in a 20-min run) are held to +-20 % of B3's
series rate, about two standard errors of the difference of two 4-run Poisson rates; the recipes
line is held to "every time" (it is what 4a adds). Only after it holds: the first real experiment
in blocks, no Knife swap on cookie / cookie_xmas (B4 vs B4', section 2b).

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
   (the runner vs the box), alternating runs, as many pairs as the night allows. ➡️ BUILT
   2026-11-14 (section 3.2, feat/stage2); its A/B pre-registered there, not run yet.
4. Stage 3: the Knife swap as functions, the respawn, the weight home (the Knife question in the
   report for Batt: the strike between F4 and F5, or not). ➡️ BUILT 2026-11-14 (section 3.3,
   feat/stage3); its A/B (the stage-2 box vs the stage-3 box) pre-registered there, not run yet;
   the Knife question is open, both answers written.
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

## 7. Stage 2 live A/B (2026-11-14 00:38-04:12 ICT): INCONCLUSIVE by its bar (1 valid pair)

The series: `scripts/stage2_ab.py run --pairs 4 --minutes 20` (AB, BA, AB, BA; the bar of 3.2,
unchanged). Main is frozen for code while a series runs (every run starts main's scripts); only
the series tool's own setup was fixed between series, never an arm.

**What stopped a series, in order (each fixed in the SETUP, before the next series):**

| Series | Stopped | Why | Fix (commit) |
|---|---|---|---|
| s2ab-1114 | 00:38, before run 1 | the chat guard's state is per host: stage 1's two setups had typed `@warp xmas_dun02 7 21` twice, so the series' first warp was a 3rd identical line (refused, no input) | the warp reads the guard's history and takes the other patrol cell (26fa0dd8) |
| s2ab-1114b | 01:02, run 3's setup | run 1 (A) DIED to the Stormy Knight at 19.0 min; she respawned with almost no HP and run 2 (B) met the player's built-in hp_critical safe end at once (0.1 min, rc 0, counted as a run); then clear-bag ended rc 1 on its own stock read-back | the setup reads her HP and types the lab GM's `@heal` under 95 % (940a4e7f); a run under 60 s stops the series; a clear-bag rc is judged by the series' own read (0715521e) |
| s2ab-1114c | 01:06, run 2's start | run 1 (A) DIED to the Stormy Knight after 1.3 min at full HP (three ~1,200 hits in under 1 s with its Christmas Goblins; no boss line read first) with the Knife worn; run 2's start check refused rightly (F4 empty, F5 the dagger in the bag) | the setup reads a worn Knife and presses the dagger key once (a081df50) |
| s2ab-1114d | 02:09, run 4's setup | run 3 (B) ended by the box's RUNAWAY guard (below) with the Knife worn; clear-bag refused with the dagger in the bag | the dagger on BEFORE clear-bag (3f29f9fc) |

**Runs so far (stage2_ab.py score):**

| Run | Arm | Min | Deaths | Potions | Fly Wings (cause) | Kills/h | Lowest HP | Box events |
|---|---|---|---|---|---|---|---|---|
| b-r01A | A | 19.0 | 1 (Knight) | 4 | 4 (boss 2) | 157.6 | 0 | - |
| b-r02B | B | 0.1 | 0 | 0 | 0 | - | - | (hp_critical at the start) |
| c-r01A | A | 1.3 | 1 (Knight) | 0 | 0 | - | - | - |
| d-r01A | A | 20.0 | 0 | 0 | 1 (garm) | 128.9 | 54 | - |
| d-r02B | B | 19.8 | 0 | 6 | 4 (garm 2, rate 2) | 148.1 | 27 | drink 6 |
| d-r03B | B | 18.0 | 0 | 10 pressed, 0 used | 1 (box, hp "0") | 153.0 | "0" | drink 10, fly_away 1 |

- d's pair 1 (d-r01A, d-r02B) is the first VALID pair. The box's `drink` fired live 6 times at
  HP 27-29 %, each one White Potion through the runner's own press (consumed: the next setup
  topped F1 up).
- The Stormy Knight was seen in all 5 of tonight's series runs that lasted (packets, job 1251;
  checked run by run), and in none of the 6 xmas_dun02 runs of 2026-11-13 before them (10:02 to
  23:11); it roams cells ~(126-188, 70-95), on the patrol route; it hit her in b-r01A (2 hits)
  and c-r01A (3 hits), both deaths. On 2026-11-12's night: 0 deaths in 18 runs,
  met 3 times. Its two-hit kill is faster than any Battle-Log guard (memory: the MVP schedule).

**d-r03B: a CLIENT HP desync (unexplained, one run tonight).** From 1,065.7 s to the run's end
(1,083 s) the client's Basic Information read HP **0 %** (25 reads) while the SERVER's packets
said HP 3,312-3,390 of 5,070 (about 65 %), and she went on fighting (attack requests, damage
dealt). In that time the client IGNORED every item: the box's `fly_away` (HP "0" < 25) pressed
one Fly Wing (no teleport packet), `drink` pressed 10 White Potions (F1 still 10 after), and the
end's Butterfly Wing (pressed, no load screen; F9 still 3). The engine's runaway guard (an event
over its max_fires_per_10min: drink 10) ended the run normally. She was left standing on the map
and the Knight killed her ~50 s later (the server's death packet; no death dialog drawn after it,
so no respawn button could be pressed). Aftercare: the lab GM's `@alive`, then `@warp geffen 119
40` (her save point). Not seen in any other run tonight. Open: why the client drew 0 %, and why it
refused items while the server still had her alive.

**Series e (02:13-04:12, the last; the setup fixes all in):**

| Run | Arm | Min | Deaths | Potions | Fly Wings | Kills/h | Loot/h | Lowest HP |
|---|---|---|---|---|---|---|---|---|
| e-r01A | A | 1.4 | 1 (Knight) | 0 | 1 | - | - | 0 |
| e-r02B | B | 19.9 | 0 | 0 | 3 | 169.2 | 208.5 | 33 |
| e-r03B | B | 19.8 | 0 | 0 | 0 | 160.2 | 205.6 | 30 |
| e-r04A | A | 2.2 | 1 (Knight) | 0 | 0 | - | - | 0 |
| e-r05A | A | 20.0 | 0 | 0 | 1 | 147.0 | 194.9 | 64 |
| e-r06B | B | 19.9 | 0 | 0 | 1 | 136.0 | 166.2 | 73 |
| e-r07B | B | 2.1 | 1 (Knight) | 0 | 1 | - | - | 0 |
| e-r08A | A | 20.0 | 0 | 0 | 0 | 131.9 | 176.9 | 54 |

- **The pre-registered verdict (3.2's bar, `stage2_ab.py score --label s2ab-1114e`): INCONCLUSIVE.**
  Only pair 3 (e-r05A / e-r06B) is valid: kills/h B - A = -11.0 (one pair: no standard error,
  so the kills line is not judged); deaths 0 / 0, potions/h 0 / 0, Fly Wings/h 3.0 / 3.02 all
  within the bar. The other three pairs each lost a run to the Stormy Knight (a death ends a run
  under 80 % of its minutes, so it is invalid).
- **A flaw in the bar, found by running it:** the death line counts only VALID pairs, and a death
  makes its run invalid, so the line can never see a death that ends a run early. Tonight's
  deaths are therefore reported below, outside the bar; the bar itself is unchanged (it was
  pre-registered). A next bar should count deaths over every run that played.
- **Report-only, pooled over series b-e (not the bar):** runs that played (>= 1 min): A 7, B 6;
  deaths A 4, B 1 (all five to the Stormy Knight, four of them in the first 2.5 min at 98-100 %
  HP, before any survival rule could act). Valid runs: A 4 (1.32 h) 141.2 kills/h, 182.9 loot
  steps/h; B 5 (1.62 h) 153.3 kills/h, 185.3 loot steps/h. Potions/h A 3.0, B 9.9 -- but 10 of
  B's 16 presses were d-r03B's desync presses the client ignored (none used); without them B is
  3.7/h. Fly Wings/h (not the end's) A 4.6, B 5.5.
- What stage 2 PROVED live: the box's `drink` plays inside the hunt core at Batt's 30 % (d-r02B:
  6 potions at HP 27-29 %, each used); the box's `fly_away` pressed on its condition (d-r03B, on a
  false "0 %" read); the runaway guard ends a run that repeats an event past its limit, normally,
  with the way home tried; nothing of the runner was worse in the valid runs. What it did NOT
  prove: a kills/h equivalence under the bar, and the boss fly by the box (no box boss Fly Wing
  fired in a valid run: the Knight's kills came before any Battle Log line could be acted on).

## 8. Stage 3 live A/B (2026-11-14 04:14-08:02 ICT): INCONCLUSIVE by its bar (2 valid pairs of 3)

The series: `scripts/stage3_ab.py run` (B2 = the stage-2 box, B3 = the stage-3 box; the bar of
3.3, unchanged). s3ab-1114 (04:14-05:31, 4 pairs planned) stopped after a B2 death 46 s after its
warp (the short-run rule, since fixed: 813893cc); s3ab-1114b (06:05-08:02, 3 pairs) ran through.

| Run | Box | Min | Deaths | Kills/h | Steals/h | Openers / back | Failed swaps | Home at the end |
|---|---|---|---|---|---|---|---|---|
| s3ab-1114-r01B2 | B2 | 19.9 | 0 | 132.5 | 60.2 | 23 / 23 | 0 | yes |
| s3ab-1114-r02B3 | B3 | 19.9 | 0 | 169.2 | 51.4 | 20 / 20 | 0 | yes |
| s3ab-1114-r03B3 | B3 | 19.9 | 0 | 144.8 | 102.5 | 41 / 41 | 0 | yes |
| s3ab-1114-r04B2 | B2 | 9.4 | 1 (one-shot from 65 %, no decoded damage packet) | - | - | 25 / 24 | 0 | (respawned) |
| s3ab-1114-r05B2 | B2 | 0.4 | 1 (the Knight at the start cell) | - | - | 1 / 0 | 0 | (respawned) |
| s3ab-1114b-r01B2 | B2 | 19.9 | 0 | 141.9 | 48.3 | 27 / 27 | 0 | yes |
| s3ab-1114b-r02B3 | B3 | 19.9 | 0 | 136.0 | 75.5 | 37 / 37 | 0 | yes |
| s3ab-1114b-r03B3 | B3 | 8.0 | 1 (the Knight, 1,309, from 81 %) | - | - | 18 / 18 | 0 | (respawned BY THE BOX) |
| s3ab-1114b-r04B2 | B2 | 19.9 | 0 | 148.0 | 96.7 | 47 / 47 | 0 | yes |
| s3ab-1114b-r05B2 | B2 | 19.9 | 0 | 132.8 | 75.4 | 37 / 37 | 0 | yes |
| s3ab-1114b-r06B3 | B3 | 19.9 | 0 | 144.9 | 90.6 | 45 / 45 | 0 | yes |

- **The pre-registered verdict (`stage3_ab.py score --label s3ab-1114b`): INCONCLUSIVE**: 2 valid
  pairs, the bar needs 3. Its lines: deaths 0 / 0 (valid pairs only: the same flaw as 3.2's bar,
  section 7); kills/h B3 - B2 +3.1 (SE 9.0; pairs -6.0, +12.1); steals/h +21.2 (SE 6.0; +27.2,
  +15.1); failed swaps 0 / 0 (pass); home at the end 1.0 / 1.0 (pass); the respawn and the weight
  lines NOT EXERCISED in the valid runs.
- **Report-only:** with s3ab-1114's one valid pair (B2 132.5 / B3 169.2 kills/h; steals 60.2 /
  51.4) the three valid pairs' kills/h differences are +36.7, -6.0, +12.1 (mean +14.3) and
  steals/h -8.8, +27.2, +15.1 (mean +11.2). Not the bar (each series is scored on its own).
- **What stage 3 PROVED live:** the B3 runs' 161 Knife openers all came from the box's knife_on
  (161 box calls), and 159 of their 161 swaps back from the box's knife_back (the other 2: the
  runner's own dagger press before an escape Fly Wing, which stays the runner's by design, 3.3);
  0 failed swaps; the way home
  at the end pressed the box's fly_home() in every valid B3 run and arrived; the death exit played
  the box's respawn_button() = click_at(645, 481) then respawn_ok() = click_at(714, 405) and she was
  back in 4.33 s (s3ab-1114b-r03B3, outside the bar: that run is invalid). NOT proven: the weight
  event (no run reached 50 %: the setup clears the bag at 40 %, and 20-min runs end at 32-43 %).
- Deaths: 3 in 11 played runs (B2 2, B3 1), all to the Stormy Knight or a one-shot with it near.

## 9. Stage 4a live A/B (2026-11-14 08:03-09:52 ICT): INCONCLUSIVE by its bar (1 valid pair of 3)

`scripts/stage4_ab.py run --label s4ab-1114 --pairs 3 --minutes 20` (B3 = the stage-3 box, B4 =
the one box: use_model("xmas02") + the monsters tab written as today's technique; the bar of 3.4,
unchanged).

| Run | Box | Min | Deaths | Kills/h | Steals/h | Loot/h | Openers/h | Recipes asked | Mismatches |
|---|---|---|---|---|---|---|---|---|---|
| r01B3 | B3 | 15.2 | 1 (with the Knight in view; the killing hit not decoded) | 142.5 | 55.4 | 178.2 | 75.2 | 0 | 0 |
| r02B4 | B4 | 19.9 | 0 | 132.6 | 21.1 | 171.8 | 33.2 | 59 | 0 |
| r03B4 | B4 | 19.9 | 0 | 151.1 | 75.6 | 184.4 | 117.9 | 60 | 0 |
| r04B3 | B3 | 19.8 | 0 | 117.9 | 84.7 | 181.4 | 105.8 | 0 | 0 |
| r05B3 | B3 | 5.5 | 1 (the Knight: 1,124 + goblins, from 88 %) | 141.2 | 76.0 | 184.7 | 119.5 | 0 | 0 |
| r06B4 | B4 | 19.9 | 0 | 154.1 | 84.6 | 208.4 | 108.7 | 68 | 0 |

- **Verdict: INCONCLUSIVE** (pair 2 the only valid one: the Knight invalidated pairs 1 and 3).
  Pair 2's judged lines pass: deaths 0 / 0; Knife openers/h within +-20 % (B4 117.9, B3 105.8);
  recipes asked at every B4 lock (60) with 0 mismatches, none asked in B3. kills/h B4 - B3 +33.2,
  steals/h -9.1, loot/h +3.0: one pair, no standard error, not judged.
- Proven live: the box's use_model chose the detector (box_model choice "box", the same xmas02gb
  file and sha256); every B4 lock asked the box's recipe for the struck species (187 asks over
  the three B4 runs: mystcase, cruiser, cookie, cookie_xmas; in r02B4, 5 of its 59 were scan
  strikes of unknown species, on the runner's own recipe), 0 mismatches; the box's respawn again (r01B3, r05B3).
- r02B4's low openers (33.2/h) were HP-gated, not the recipes: 59 of 59 recipes said the Knife;
  she spent 70 % of that run under 50 % HP (r01B3: 43 %), where the runner skips the Knife
  (knife_hp_min 0.5; bare_skip_hp 41).
- **A design interaction for Batt (not a bug):** the box drinks under 30 % (Batt's number) and the
  Knife swap needs 50 %: between 30 and 50 % she neither drinks nor swaps. The runner alone drinks
  under 40 %. In stage 2's valid runs the runner alone spent 0 % of its time under 50 % HP (3 runs)
  and the box 0, 0, 21, 32 and 47 % (5 runs): a small sample (where she fought), but the band is
  real. The runner's tick rate is the same in both arms (2.2-2.5 reads/s, median gap 201 ms), so
  the box's hook does not slow it. ➡️ **Batt answered 2026-11-14 ~14:0x ("raise the drink"):** the
  one box drinks under 50 % now, the band is closed (section 10).

## 10. Batt's 2026-11-14 answers (built): the drink at 50 %, the candies eaten at once

Batt, 2026-11-14 ~14:0x ICT (Thai, translated): "Raise the drink. And the moment we get a Candy
Cane or a Candy, eat it to add HP right away; that also cuts the weight." BUILT 2026-11-14 14:5x
(feat/candy-box; offline tests only, NOT run live). dungeon@9.52 (`BOX_EAT_VERSION` = `live.VERSION`
= `flow_play.VERSION`; stage 4a's 9.51 and the earlier stages' versions stay; `dungeon_hunt.VERSION`
stays dungeon@8.7; in the runner export's `NOT_FEATURES`).

**The one box now** (`project_xmas_dun02.json` = `xmasProject()`, byte-identical canonical; 0 lint
errors, the same four warnings; the box as stage 4a left it is kept byte for byte as
`project_xmas_dun02_stage4.json`: stage4_ab.py's B4 and stage 4a's tests, so s4ab-1114 stays the
series it measured):

    # tab main: the eat role names the box's eat function
    dungeon_hunt(heal=heal, fly=fly_wing, knife_on=knife_on, knife_back=knife_back, home=fly_home,
                 respawn=respawn_button, respawn_confirm=respawn_ok, eat=eat)
    # tab keys: the five keys as before, and the food on the hotbar
    def eat(key):      press_key(key)   # dungeon_hunt's eat role: whatever food is on that slot
    def candy_cane():  eat("F6")        # the Candy Cane (item 530): the lab Rogue's F6
    def candy():       eat("F7")        # the Candy (item 529): her F7
    # tab survival: the drink raised; one event per item
    @on(hp_percent() < 50, until=hp_percent() >= 51, priority=SURVIVAL, mode=INSERT, cooldown_s=0.7)
    def drink():
        heal()
    @on(hotbar_count("F6") > 0, until=hotbar_count("F6") == 0, priority=UPKEEP, rank=51,
        mode=INSERT, cooldown_s=1.5, max_fires_per_10min=30)
    def eat_cane():
        candy_cane()
    @on(hotbar_count("F7") > 0, until=hotbar_count("F7") == 0, priority=UPKEEP, rank=52,
        mode=INSERT, cooldown_s=1.5, max_fires_per_10min=30)
    def eat_candy():
        candy()

- **The drink** goes from HP < 30 % (until 31 %) to HP < 50 % (until 51 %): the Knife swap needs
  50 % (`knife_hp_min` 0.5), so the 30-50 % band of section 9 (she neither drank nor swapped) is
  closed: the drink repeats until 51 %, over the Knife's floor. The runner's own P2
  line (`potion_below` 0.4) is unchanged: it is the old Run path's, and it is off in a box run.
- **The eat**: each item's event fires the moment its slot reads a count over 0, at ANY HP (no HP
  gate), and repeats every 1.5 s (`cooldown_s`, a literal in the box: long enough for the slot's
  count to change after a press) until the slot reads empty. An INSERT, class upkeep, then
  resume; ranks 51 / 52 order the two after bag_full (rank 50) and each other (the lint's ties
  rule: an info, no warning). `max_fires_per_10min` 30: a stack of 7 is 7-8 fires; the count of
  fires clears each time the slot reads empty. The F6 / F7 keys and every number are defaults: a
  person changes them in the keys and survival tabs.
- **Two literals a person keeps in step**: the key the condition reads (`hotbar_count("F6")`) and
  the key the item's function eats (`candy_cane(): eat("F6")`). The model allows no better: an
  event's condition cannot read a function's input, and press_key / hotbar_count take literal keys
  (a tab variable is refused as a press key, lint `param_option` / `key_argument`). So the engine
  checks them against each other instead: an event that reads hotbar_count and eats a key its
  condition does not read is REFUSED before any input, in words ("eat_cane eats F3 but its
  condition reads hotbar_count of F6: the count it reads is not the slot it eats from").

**The sensor `hotbar_count(key)`** (blocks.yaml, `live: true`, int 0..999, a positional `key` with
press_key's options F1-F9): the count drawn on a row-1 hotbar slot, read with the runner's OWN
reader (`hotbar_count.read_count` on `hotbar_count.gray` of the frame's top 40 rows;
`dungeon_hunt.hotbar_slot(key)`; its digit templates loaded at RUN TIME from data/hotbar, never in
git). Live ONLY inside a hunt core: `flow_play.LivePlayer.hunt_tick` reads it from
`HuntTick.frame` (the tick's game-region frame, already passed), only for the keys the box's
events name (`live.hunt_plan` -> `HuntPlan.hotbar_keys`), each at most once every
`flow_play.HOTBAR_EVERY_S` (1.0 s; between reads the last value stands). An empty slot reads 0; a
count it cannot read (a digit no template matches, a frame-less tick) is unknown: an event that
reads it is then not evaluated (it never fires, and a repeating one pauses until a read). An event
that reads only hotbar_count is evaluated on a tick without an HP read too (stage 2's rule -- no
HP read, no boss line: nothing decided -- still holds for every event that reads HP, SP or the
boss). Outside a hunt core it is unknown. The simulator reads it from the scenario
(`trace.Change.hotbar`: "F6" -> a count from t on; every slot the flow reads starts at 0); the
editor offers `hotbar_count(key="F6")` under Sensors.

**The role and the play.** `dungeon_hunt`'s new OPTIONAL role `eat` names the function the box's
events call to eat (`functions.eat_shape`: ONE press_key of its input, the item's key, or of one
literal key). Every press inside a call of it, in a hunt-core event, is an EAT press; `live.PLAYS`
== `dungeon_hunt.BOX_PLAYS` gains `"eat"` (by the events that eat: `play_by`). It replaces nothing
of the runner's, so `live.takeovers` lists no row for it (`OWN_PLAYS`; the pages' "IN A RUN" words
name only what is switched off) and it has no Run setting.

    the player (prepare, before any input)               the runner (dungeon_hunt.run)
      live.hunt_plan: eat_keys (F6, F7), hotbar_keys
      run(box_plays=[..., "eat"], box_eat=["F6","F7"]) -->  box_plays_refused -> eat_refused:
                                                          "eat" <=> box_eat, row-1 keys, each
                                                          once, never beside --heal-candy, none
                                                          another key of the run (keys_clash over
                                                          its whole key map and --steal-opener)
                                                          run_start: box_eat, box_version 9.52
                                                          box_keys: F6 / F7 -> "eat"
      each tick: hotbar_count from HuntTick.frame
      eat_cane due: candy_cane() -> eat("F6") ->     -->  box_press("F6", "box eat_cane
                                                          (hotbar_count(F6) 2)"): agent_raw.keys,
                                                          counts eat / box_eat, a press record
                                                          {what: eat, key, why}; no stock read
                                                          any other key: box_refused, not pressed

**Refused before any input** (`live.problems` / `hunt_plan`, the backend's not_live; the lint's
`hunt_function` / `hotbar_keys` name the same in the editor): an eat key that is dungeon_hunt's
heal, Fly Wing, Knife, dagger or Butterfly Wing key ("eats F1 through eat() inside the hunt core: F1
is dungeon_hunt's heal key (the heal item's key); an eat key must be its own ..."); an eat event
whose condition reads another slot than it eats; a direct press_key of a food's key in an event
(not through the eat function); a hotbar_count whose key is not a literal row-1 key; an eat
function that is not one press_key; an eat role naming no function.

**What stays the runner's**: the start's slot check (dungeon@9.47) and the stock read and end
(dungeon@8.4 / 8.3) never see the eat keys -- 0 candies is normal, and an empty food slot never
ends a run; the runner's own `--heal-candy` (dungeon@9.31: a due potion presses the cane, then the
candy, then the White Potion, its keys HEAL_CANDY_KEYS F6 / F7 fixed in code) is untouched and stays
the runner's own flag, refused beside the box's eat (one candy eater); the HP-rate fly, the Garm
Baby, the dead jump, an unread position, the NPC guard. A box without the eat role or eat events
passes run() exactly stage 4a's arguments (no box_eat).

**The record**: the player's events.jsonl has each eat event fired (`event`, its `reading`
`{"hotbar_count(F6)": 2}`, `in: "hunt"`), the runner's press records mirrored (`press` what "eat",
the key, why "box eat_cane (hotbar_count(F6) 2)"), `hunt_start` with `box_eat` and `hotbar_keys`;
the runner's session: run_start `box_eat` / `box_version` 9.52, `press {what: "eat"}`, the counters
`eat` and `box_eat`.

**The expected cost and gain** (from the local KB and the records named; NOT measured with the new
box yet):
- **More potions.** A White Potion buys at 1,200 z (KB item 504). Drinking under 50 % instead of
  30 % will use more of them: stage 4a's r02B4 spent 70 % of its run under 50 % (section 9), all of
  it now inside the drink's band. Each extra potion an hour costs 1,200 z/h, about 0.9 % of Batt's
  bar of 135,737 common z/h (computed). The next live run should count potions per hour against
  stage 4a's, with the Knife openers per hour (the band closing should raise them).
- **The candies are small.** They sell for 5 z (Candy, 529) and 10 z (Candy Cane, 530), weigh 3 and
  4, and heal ~45-65 and ~105-145 HP (rogue-xmas02.md 4CF). On xmas_dun02 they drop from the Myst
  Case (Candy 3.4 %, Candy Cane 0.9 %) and the Cookie (3.2 % / 1.5 %) only (the local KB's
  drops.json: rates 340 / 90 and 320 / 150; the Christmas Cookie and the Cruiser drop neither).
  With kills in the spawn mix (Myst Case 50, Cruiser 35, Cookie 20, Christmas Cookie 20) that is
  about 1.9 Candies and 0.6 Candy Canes per 100 kills (computed, steals not counted): at ~140
  kills/h, ~2.6 + 0.8 an hour, ~250 HP an hour (less than one White Potion), ~11 weight an hour off
  the bag and ~21 z/h of NPC sales given up.
- **The start eats the slots**: the lab Rogue's F6 holds 2 Candy Canes and F7 7 Candies (read
  2026-11-14 14:0x); the first ~10-15 s of a run eat all 9 (each slot paced 1.5 s), at full HP.

**Tests** (offline): services/backend/tests/test_box_eat.py (the sensor on fake frames: eaten one by
one until empty, the 1-s rate, unknown pauses, no HP needed; the reader stubbed and on synthetic
pixels; the templates loaded at run time; the simulator's scenario; the refusals; run()'s own
box_press executed from its source; eat_refused; the AST: the eat keys never reach the run's key
map, slot check or stock); the one box's pins in test_project.py, test_live_player.py and the
frontend's project.test.ts / box.test.ts.

**Still fixed in code** (a person cannot set them yet): `HOTBAR_EVERY_S` (1.0 s) and the 40-row
crop; the hotbar reader's geometry and font (hotbar_count.py, row 1 at the 1280 x 720 client) and
its two-digit limit (a count over 99 reads unknown, though the sensor's range is 0..999); one press
per call of the eat function; the runner's `HEAL_CANDY_KEYS`.

### 10.1 The live A/B: B4 (the stage-4a box) vs B5 (the one box today) -- pre-registered 2026-11-14 15:08 ICT from `date`, BEFORE any run

`scripts/stage5_ab.py run --label s5ab-1114 --pairs 3 --minutes 20` (alternating B4 B5, B5 B4, B4
B5; stage2_ab's setup before every run; a STOP file in /dev/shm/poring-lab-tmp/stage5-ab/<label>/).
- **B4** = `project_xmas_dun02_stage4.json` (drink under 30 %, no eat); **B5** =
  `project_xmas_dun02.json` (drink under 50 %, eat F6 / F7). The plan refuses unless only B5 eats
  and the two boxes' roles, model and recipes are the same, and unless the Run config has
  `alarm_fast` on: BOTH arms run dungeon@9.53's fast alarm (section 11), so its live numbers are
  reported too (report-only).
- **The bar (`stage5_ab.BAR`)**:
  1. **deaths**: B5's <= B4's, over EVERY run that played (>= 1 min, or a death) -- section 7's
     flaw fixed: a death no longer hides by making its run invalid;
  2. **under50**: B5's share of HP-read time under 50 % < B4's (valid runs pooled; each read holds
     until the next, at most 2 s): the band closed;
  3. **openers_h**: B5's Knife openers / h >= 0.8 x B4's (valid runs pooled);
  4. **kills_h**: the mean paired (B5 - B4) kills / h >= -2 x its standard error, judged only with
     >= 3 valid pairs (a valid run: >= 80 % of its minutes, or a weight-home end);
  5. **eat**: B5 pressed an eat key at least once and B4 never.
  Any line FAIL -> FAIL; a line not judged -> INCONCLUSIVE; else PASS.
- **Report-only**: potions / h and their cost at 1,200 z each; eats / h; the alarm's fires inside a
  long action and between steps (each to be judged true or false against the packets' party in
  view, as 11.1/11.2); the lowest HP; and for the alarm, deaths per played run against last night's
  10 in 30 (both arms here run it).
- **Known before the run**: her F6 / F7 hold 2 Candy Canes and 7 Candies from 2026-11-11's GM
  `@item` setup (4CF), not loot; the first B5 run eats them. They are counted apart from looted
  candies in the report (the setup never tops candies up).

### 10.2 Result of s5ab-1114 (run 15:10-17:19 ICT, scored 17:2x): FAIL by the bar -- on line 2 only

`stage5_ab.py score --label s5ab-1114`: 3 pairs, all 6 runs valid (19.8-19.9 min, each ended by
its time box), 0 invalid.

    run        arm  min  deaths kills/h open/h potions eats  <50 %  lowest HP  alarm in/between
    r01B4      B4   19.9   0    160.2   136.0    0      0    0.00     67 %        0/0
    r02B5      B5   19.9   0    129.9   120.8    3      6    0.00     45 %        0/2
    r03B5      B5   19.9   0    141.9   114.7    0      3    0.00     68 %        0/3
    r04B4      B4   19.9   0    120.9   123.9    0      0    0.00     75 %        0/3
    r05B4      B4   19.9   0    148.1   126.9    0      0    0.00     54 %        0/0
    r06B5      B5   19.8   0    139.0   120.9    7      1    0.01     40 %        0/0

The bar, line by line:
1. deaths: B4 0, B5 0 -> PASS.
2. under50: B4 0.000, B5 0.003 of the HP-read time -> **FAIL** (B5 < B4 is impossible against 0).
3. openers_h: B4 128.9, B5 118.8 (0.92 x) -> PASS.
4. kills_h: paired B5 - B4 = -30.2, +21.1, -9.1; mean -6.1 / h, SE 14.9 -> PASS (>= -2 SE).
5. eat: B4 0, B5 10 -> PASS.

The verdict stays **FAIL**, as pre-registered; it is not re-scored. What line 2 measured: B4
(drink under 30 %) never went under 50 % in its hour, the lowest 54 %. So the line could pass
only if B5 never did either, and a drink AT 50 % comes after a read under 50 %. Lesson for the
next bar: a strict "<" against an arm at 0 cannot pass. Compare the time in the 30-50 % band with
"<=", or require that the band was entered at all.

Report-only, from the packets (sniffer, offline):
- **B5's dips under 50 %:** 10, each 0.2-6.1 s, lowest 41 % (r06B5). The HP is stat 5, against
  the run's highest HP, 5,070, because max HP is sent only at login. The damage in the 15 s
  before each low point came from the map's ordinary monsters (jobs 1249, 1248, 1246), never the
  boss party. B4 had no dip under 50 %.
- **Potions:** B5 drank 10 White Potions (item 504) in 59.6 min, 10.1 / h = about 12,100 z / h at
  1,200 z each. B4 drank 0. Fly Wings (601): B5 12, B4 4. Butterfly Wings (602): one per run, the
  home at the end; the setup tops F9 up before each run.
- **Eats:** B5 10 (Candy 529 x 6, Candy Cane 530 x 4), 10.1 / h; B4 0. **Correction to "Known
  before the run":** the 11-11 candies were gone before any B5 run. The setup's clear-bag
  ("etc, use", run when the bag reads over 0.40) emptied the use tab before r01B4. It did the
  same before r04B4 and r06B5, then restocked 10 White Potions and 10 Fly Wings each time. So
  r02B5's first eat read hotbar_count(F7) = 2, which is r01B4's 2 looted Candies, and its first
  F6 eat came 90 s in, after a looted cane. r05B4's 6 looted candies were cleared before r06B5.
  All 10 eaten were looted, in that B5 run or in the B4 run just before it with no clear-bag in
  between. B4 looted 8 candies (529 x 5, 530 x 3) and, by design, ate none.
- **The shortcut survives a count of 0:** F7 read 2, then 1, then 0, and later 1 again for each
  looted Candy, eaten each time (r02B5: 4 F7 presses, 2 F6 presses).
- **The fast alarm (dungeon@9.53, both arms; 6 runs, 2.0 h):**
  - **Fires:** 8 in all. 5 were true (a boss-party member in view by packets, within 2 s) and 3
    false, which is 1.5 false fires / h; the offline estimate in 11.2 was 1.7 / h.
  - **By kind:** all 3 single-box fires (score 0.88, 0.98, 0.99) were true. The 3 false ones
    were two-in-a-row fires at scores 0.31, 0.38 and 0.70.
  - **Fly Wing:** every fire pressed it 0.21-0.42 s later (fly "boss").
  - **Inside long actions:** 0 fires. guard_tick's inside path was not exercised live.
  - **Party visits:** 6 by packets, and the alarm fired in 5. The sixth was one Christmas Goblin
    (1607) at 11 cells or more, for 1.6 s, with no damage to her (the alarm watches Garm Babies).
- **Deaths: 0 in 6 played runs**, against last night's 10 in 30. Too few runs to credit the
  alarm: at last night's rate (1 in 3 per run), 0 in 6 has a chance of (2/3)^6 = 8.8 %.
  Party visits were few (6 in 2 h).

**Batt's decisions on 10.2 (2026-11-14 ~18:1x ICT, Thai, translated):**
1. The drink: "keep it at 50 % for now". It stays at 50 %; the next long series measures it
   again, with income.
2. The Goblin class (11.4): "if it can run in parallel, do it now; if not, wait". It can: 5b is
   offline work for hours and the detect server runs only beside a Run. So the round runs now
   (xmas02-detector.md, its own pre-registered amendment). The new model is NOT deployed until
   its held-out result and a later step of its own.
3. 5b: "go on, no need to ask me again". Started (section 12.3).
4. The /flows page: Batt reviews it himself.

## 11. Batt's 2026-11-14 answers (~14:0x ICT): the Knight, the Knife, the Butterfly Wings

**Batt's words (Thai, translated), answering the morning report's four questions:**
1. The Stormy Knight: "a Fly Wing away, or walk around it; I recommend the Fly Wing."
2. The 30-50 % HP band: "raise the drink, and the moment we get a Candy Cane or a Candy, eat it to add
   HP; that also cuts the weight." (Built as section 10.)
3. The Knife (F4 -> F5, the strike between or not): "decide it yourself, then report to me."
4. "Top up the Butterfly Wings on F9" (1 was left).

### 11.1 Why the Fly Wing came too late: the 11 deaths of 2026-11-13/14, from packets

The analysis (packets = the offline truth; the runner's own events and detections; scratch scripts,
read-only, over the 30 series sessions in /dev/shm/poring-lab-demo): for each death, when the
knight's party last came into view (no member in view -> one in view), the nearest member, the first
garm_baby box of the deployed model (xmas02gb) in either detection stream, and the runner's escapes.

| Run | Min into the run | Party in view before the death | Nearest at the death (cells; s after entry) | First garm_baby box before the death | Two boxes in a row before the death |
|---|---|---|---|---|---|
| s2ab-1114b-r01A | 19.0 | 4.6 s | Goblin 2; 3.6 s | 1.6 s | none |
| s2ab-1114c-r01A | 1.0 | 4.6 s | Goblin 6; 0.5 s | 4.0 s | 3.8 s |
| s2ab-1114d-r03B (the desync run; she died ~50 s AFTER its end, section 7) | 18.0 + ~0.8 | 3.2 s | - (no position read) | 1.9 s | 1.8 s |
| s2ab-1114e-r01A | 1.4 | 4.8 s | Goblin 4; 3.2 s | 3.8 s | none |
| s2ab-1114e-r04A | 2.2 | 3.4 s | Goblin 2; 3.4 s | 1.6 s | 0.6 s |
| s2ab-1114e-r07B | 2.1 | 6.1 s | Goblin 2; 4.3 s | 4.3 s | 4.3 s |
| s3ab-1114-r04B2 | 9.4 | 5.3 s | Goblin 5; 5.1 s | 0.2 s | none |
| s3ab-1114-r05B2 | 0.3 | 5.4 s | Goblin 1; 4.3 s | 2.7 s | none |
| s3ab-1114b-r03B3 | 8.0 | 6.4 s | Goblin 1; 3.9 s | none | none |
| s4ab-1114-r01B3 | 15.1 | 2.4 s | Goblin 7; 2.3 s | 1.9 s | 1.6 s |
| s4ab-1114-r05B3 | 5.5 | 2.8 s | Goblin 2; 1.4 s | 2.2 s | none |

- At every death the party in view was **6 Christmas Goblins and the knight, no Garm Baby** (the
  knight's two Garm Babies were gone by then). It came into view 2.4-6.4 s before the death; the
  Goblins came first and closest (1-2 cells in 7 of 10).
- The deployed model has no Goblin class (xmas02-detector.md S3: the cache could not carry one), but
  it boxes some of them as garm_baby: a box came before 10 of the 11 deaths, 0.2-4.3 s ahead.
- **The runner flew on none of them.** The alarm (`--garm-fly --garm-confirm 2`) read only the
  watcher's ~1-s detections (the HUD twin's, ~4x as many, never fed it: 9.29c by design), and only
  between steps: in the seconds before each death the loop was inside a target's settle wait or a
  strike (1.5-2.5 s each). In one run (s3ab-1114b-r03B3) a Fly Wing was pressed 0.65 s before the
  death packet, on the HP, not the alarm: too late.
- No zone avoids it: the deaths were all over the map ((7, 71) to (192, 54)), so "walk around" has
  nothing fixed to walk around; Batt's recommended Fly Wing it is.

### 11.2 Built: dungeon@9.53 `--alarm-fast` (branch feat/fast-alarm; ON in the Run's xmas_dun02 flow)

- The HUD twin's detections feed the alarm too: one streak over both streams, in grab order (a
  detection grabbed before the alarm's own is late and changes nothing).
- `guard_tick` reads the alarm INSIDE long actions (every QUICK_S, 0.25 s) and flies there: the
  runner's own `press("fly", "garm")` (the dagger first when bare), then the action stops (the
  loop's after-the-fly steps, as for an HP fly inside an action). Not within 2 s of a Fly Wing, never
  twice in one action.
- `--alarm-solo T` (default 0.7): one alarm box at score >= T flies without --garm-confirm's streak.
- Both are Run settings (flow_config: "safety"), a person's to change: `alarm_fast` (needs
  garm_fly) and `alarm_solo` (0 = off). Recorded in run_start `fixes.alarm_fast` = [solo, HUD fed,
  "9.53"]; the run's end record counts `n_alarm_hud`; events `garm_seen` with `inside: true`.
- **What to expect, offline on the same 30 runs (7.66 h; deaths caught >= 1.5 s before the death
  packet, a fire within 5 s of another merged; false = no party member in view +-2 s):**

| Rule | Deaths caught >= 1.5 s | False flies |
|---|---|---|
| today: the watcher's stream, 2 in a row | 1 of 11 (but never read in time live) | 0.3/h |
| both streams, 2 in a row | 4 of 11 | 1.2/h |
| **both streams, 2 in a row or one box >= 0.7 (the default)** | **5 of 11** | **1.7/h** |
| both streams, 2 in a row or one box >= 0.6 | 5 of 11 | 2.3/h |
| both streams, 2 in a row or one box >= 0.4 | 6 of 11 | 4.0/h |

  This assumes the loop reacts within its 0.25-s guard read, which 9.53 makes true inside actions;
  a live check measures it. **At best about half the deaths: the model sees the Goblins only by
  accident.**

### 11.3 The Knife: answer (a) KEPT -- the strike between F4 and F5 (the agent's decision, Batt's delegation)

- (a) is Batt's own technique: his 2026-11-12 benchmark run struck with the Knife, then put the
  Damascus on 1.36 s after the steal (91 % stolen). The strike falls between the two presses.
- (b) ("press F4, wait 100 ms, press F5" before the strike) would wear the Knife for 100 ms and
  never strike with it: every steal would have to come from Damascus hits -- a different technique
  from Batt's, measured by no run.
- (a) plays live: stage 3's B3 runs made 161 openers through the box's knife_on and 159 of 161
  swaps back through knife_back (the other 2 were the runner's own escape dagger), 0 failed swaps.
- (b) stays written (knife_ends "armed", section 3.3): a person may try it by editing the knife tab.

### 11.4 Next: a Christmas Goblin class (➡️ STARTED 2026-11-14 ~18:2x, Batt: "if it can run in parallel, do it now"; 10.2)

The Goblin is a summon only on this map and came first in every death above, so a Goblin class
in the alarm would see the party 2.4-6.4 s ahead. S3's blocker was the cache's WHOLE-frame rule (a
frame with any excluded label is not written; the knight's crowded party almost never leaves a frame
whole: 12 Goblin boxes from 2,823 kept labels). The proposal: a new detector amendment that masks the
excluded labels' boxes in the cached frame instead of dropping the frame, then the round as Amendment
M/S (the sk1a/sk2a DEV recordings on the NAS, init xmas02gb, the held-out sk3a unread so far), its
bars pre-registered before any data step.

➡️ **RESULT (2026-11-15 00:32 ICT, xmas02-detector.md Amendment S4, scored once): FAIL, NOT
deployed.** The masked cache (S4.1-S4.7) gave TRAIN 1,138 Goblin boxes (S3: 12); 10 epochs from
xmas02gb (`xmas02sk`, last.pt `0b43ebbf...`, ONNX `76316fb4...`, archived, registered in GPU_WEIGHTS
only). On sk3a the Goblin's Q1s recall is 0.807 but its precision **0.597 < 0.80** (31 boxes charged,
26 of them on real Goblins not drawn into the pack: the scorer's crowd rule, S4.10); the knight 59 /
59 (reported); Garm Baby, the four species and D1 (17.96 ms) PASS. The alarm stays xmas02gb's.

➡️ **S5 (2026-11-15 14:06 ICT, xmas02-detector.md S5, scored once on the FRESH held-out sk4a, Batt's
"Allowed"): FAIL by ONE crop.** The same frozen model, under the crowd rule pre-registered before
sk4a existed. The Goblin's precision is 1.000 (every charged box lay on a Goblin), but its per-crop
recall is 43 / 54 = 0.796 < 0.80 (44 would pass). The alarm's view, reported: frame recall 0.911
(0.856 at conf 0.7), 0 false-alarm frames (0 / 95 on sk4a, 0 / 231 TEST, 0 / 261 gw3), the first
Goblin box within 2 s in 16 of 17 visits (the 17th 2.01 s). Not deployed; the next step is the
parent's / Batt's.

➡️ **S6 (2026-11-16 14:18 ICT, xmas02-detector.md S6, Batt's "the alarm signal", scored once on the
fresh 32-stand sk5a): FAIL by ONE false fire.**
- Detection: 38 / 39 visits fired within 2.5 s (bar >= 90 %).
- Goblin-free held-outs: 0 false fires in 265 frames.
- But sk5a's alarm-free frames: 3 / 254 = 1.18 % > 1 %, and all three were party members the client
  still drew just after the watch's `@killmonster2`, when the packets had already removed them: a gap
  in S6's own truth, to be closed by a new amendment before any new held-out.
- Not deployed.

➡️ **S7 (2026-11-16 21:54 ICT, xmas02-detector.md S7, Batt's "test again", scored once on the NEW
32-stand sk6a): PASS on every line.**
- The truth fix, pre-registered before sk6a: a frame within 5 s after an alarm unit's vanish
  (died or out of sight) is not alarm-free.
- Detection: 33 / 33 visits fired within 2.5 s.
- False fires: 0 / 98 on sk6a's alarm-free frames, and 0 / 265 on the Goblin-free held-outs.
- The fix decided it: under S6's definition sk6a would have read 2 / 195 = 1.03 % and failed by one
  fire. Both fires were units the client still drew (looked at).
- Not deployed by S7: deployment is its own step, the parent's and Batt's.

### 11.5 The Butterfly Wings (done 14:02 ICT)

The lab GM's `@item 602 4` (crusader.py, `"typed": true`), read back from the hotbar: F9 1 -> **5**.
She stands in geffen at full HP; F8 8, F1 10, F6 2 Candy Canes, F7 7 Candies; the chat closed again
by the UI gate's own step.

## 12. Stage 5a: the settings are blocks, the runner page is gone (Batt 2026-11-14 ~15:2x)

**Batt's words (2026-11-14 ~15:2x, Thai, translated; with screenshots of /flows?runner=xmas_dun02
and of his /flows project):** "We should not make the page /flows?runner=xmas_dun02 like this: it
makes learning very hard. There should be no runner. Everything should be in the xmas_dun02 flow,
split into tabs, e.g. the knife swap as its own tab on the /flows page of xmas_dun02. Move all the
blocks of xmas_dun02 on the runner page into /flows, in map xmas_dun02. And these values [the
settings panel: the Knife swap, heal and escape, leaving the map, the respawn, and 'all the other
numbers (102: the start, the fight, aiming, loot, walking, safety, the loop)'] -- make them ALL
blocks, no hardcoding like this. The xmas_dun02 map in /flows may have as many tabs as needed."

**The plan, in two steps** (the parent's):
- **5a (BUILT here, branch feat/settings-blocks, offline only):** every Run setting becomes a BLOCK
  in the project's tabs; the Run reads its values from the blocks; the settings form and the
  runner description page go.
- **5b (NOT built):** the runner's loop itself becomes the flow's own playable blocks (the
  HuntState refactor of section 2b's 4b). Only then do the loop's DESCRIPTION blocks (the outline
  scripts/runner_flow_export.py still prints: look, choose, approach, strike, loot, explore, the
  safety rules) move into the map's tabs: moving them earlier would put blocks on the page that do
  nothing when edited.

### 12.1 The design as built

| Piece | Where | What |
|---|---|---|
| The registry | `packages/poring_flow/src/poring_flow/settings.py` (moved from scripts/flow_config.py, which re-exports it) | the 126 fields as before (group, kind, range, words, flag or --tune, needs, warn) plus each one's DEFAULT (`DEFAULTS`: the Run's values of 2026-11-14; a runner constant's is the runner's own number, test_flow_config pins each equal to dungeon_hunt's / value_target's). `flow_run.FLOWS["xmas_dun02_rogue"].defaults` is DERIVED from it (`flag_defaults()`, pinned to the old dict key for key). The catalogue serves it (`settings`); the browser's copy is `lib/flow/settings.gen.ts` (`typescript_module`, drift-tested; scripts/gen_protocol.sh writes it) |
| A setting in a project | a tab's `vars` (a literal), the existing model | named like the setting; the three that cannot be, in ONE table (`VAR_NAMES`): `vt.D0_PX` -> `D0_PX` (a dotted name is no variable), `loot` -> `loot_step` and `respawn` -> `respawn_on_death` (catalogue names). It stays an ordinary variable too (a block may read it). The five hotbar keys are NOT setting blocks: they are the functions dungeon_hunt names, as before |
| The tabs | one per group (`TABS`): knife, survival, exits, respawn, start, fight, aim, loot, walk, safety, loop | in the one box, knife, survival and exits hold their settings BESIDE their functions (the tab of the same name); the other eight are tabs of settings ➡️ partly superseded by 12.4 (round 20) |
| The name rule | `settings.node_values` (the project's JSON), `lint/settings.node_values` (the models), `lib/flow/settings.ts nodeSettings` (the browser) | per setting: the map node's variable (any of its tabs) > Global's > the default. A deleted block falls back; a value it cannot take is no value (the default stands in; the lint's error refuses the run) |
| The block | `lib/flow/blockdefs.ts settingDef` (one Blockly type `pl_set_<var>` per setting), `blocks.ts` | its words; its value by kind (number / int with the range, step and unit; a share as a PERCENT; a switch on / off; a choice's options; a point's x and y; point_or_none's at / none); `· <var>` after it; a safety switch (respawn, npc_guard, garm_fly, alarm_fast) has a row its warning fills while it is off. Its tooltip: the range, our default, the runner's flag, and what deleting it falls back to (Global's block, else the default). A value the block cannot hold (out of range, the wrong kind) stays a plain `variable` block, so nothing is clamped and the lint says why. In a tab: the plain variables first, then the settings in the registry's order, one row apart ➡️ partly superseded by 12.4 (round 20) |
| The toolbox | blockdefs `settingItems` | a **Settings** category on map nodes and Global: every setting at our default, by group, the shown tab's group first. The same setting twice on a tab is refused ("on this tab twice") ➡️ partly superseded by 12.4 (round 20) |
| The Python view | `pyproject.print_tab` | `knife_hp_min = 0.5  # or at once under HP (50 %)`, `knife_swap = True  # Batt's Knife swap (on / off)`, `respawn_at = "645,481"  # respawn button at ("X,Y" in the game picture)`; the settings in the registry's order after the plain variables; a map's that overrides Global's says so in the line above. The parser reads the assignment (the comment is words), so the round trip is exact ➡️ partly superseded by 12.4 (round 20) |
| The lint | `poring_flow/lint/settings.py` (from project._project_rules), in words on the block | `settings` ERROR: the wrong kind, out of range or off the grid ("or at once under HP: 95 % is not from 20 % to 90 %"); `settings` WARNING: a name that looks like a typo of a setting's (another case, or difflib >= 0.85: "potion_bellow is not a setting: did you mean potion_below ...?"; any other name is an ordinary variable and says nothing), and a hotbar key as a variable ("not read: the hunt core takes its hotbar keys from the functions ..."); `settings_clash` ERROR on the node: flow_config's clash rule on the values its hunt core takes (two roles on one key, hud_fast not faster than BOX_EVERY_S); `settings_use` INFO: a setting not in use ("not in use while Batt's Knife swap (knife_swap) is off: the runner is not given it"), one the box replaces in a Run (live.takeovers: "potion_below ... is not used in a Run of this box: drink plays the runner's potion on HP instead"), settings on a node without a hunt core ("not read") ➡️ partly superseded by 12.4 (round 20) |
| The Run | `flow_play.prepare` (`flow_run.project_values`) | a hunt core's runner settings = the checked project's setting blocks on its node (> Global's > the defaults), the node's keys over them, then the clash rule; `runner_vals` (an A/B series' runner-config.json) still replaces them for a block. `settings.argv` skips a runner constant AT ITS DEFAULT (the runner keeps its own number), so a box whose blocks hold every default runs exactly today's command |
| The check | `POST /flows/run/check {project, node}` (routes_flowrun `check_values`) -> request `{action: "check", flow: "project", node, keys, vals}` -> flow_run `check_start` | the backend validates the project, the node's hunt core, its keys and its setting blocks (`settings_refused`, `no_hunt_core`, `keys_refused`, `not_a_map_node`, `invalid_project`; ➡️ round 29: `old_runner`, 12.13) and sends every setting block's value; the helper checks them again (`check_level`, every block named, the clash rule) and runs the runner's read-only check with them. The checklist on /flows states the same values (`startChecklist(nodeSettings(...))`) |
| The stage tools | `stage2_ab.box_vals` / `same_vals`; stage3-5 `run_vals` | each arm's box's setting blocks and keys; a series REFUSES before any input when two arms' runner settings differ ("the boxes' runner settings differ: knife_hp_min is 0.5 in B4, 0.6 in B5 (an A/B changes the box, not the settings)"). A still plays `flow_run.command` with those values |

**The settings file is not imported:** settings/flowrun/config.json was `{"v": 2, "global": {},
"maps": {}}` on bot-server when it went (read 2026-11-14 16:4x ICT; its mtime 2026-11-13 15:29), so
no value moved into a project. The file stays on disk, unread.

**The same argv, before and after** (`services/backend/tests/test_settings_blocks.py`): the three
frozen A/B arms (`project_xmas_dun02_stage2/3/4.json`, byte-identical: their sha256 pinned) and the
one box with its 121 blocks (➡️ 116 since round 20: 12.4 #4a; the argv unchanged) at their defaults all give the runner argv main 2d19014d gave them
(computed with that commit's flow_config / flow_run / flow_play and an empty settings file; one
list, pinned literally). A changed block is what the runner gets; a deleted one falls back.

### 12.2 What moved where, what went

| Before | Now |
|---|---|
| the runner page `/flows?runner=xmas_dun02` (RunnerView, its blocks, its Simulate, its Run) | GONE; the link opens the map's node on /flows (page.tsx maps `xmas_dun02_rogue` and a map's name to that node) |
| Before Run's settings panel (ConfigPanel, "saved on the bot server at once") | the setting BLOCKS in the node's tabs; Before Run keeps the checklist, the live line and the check, and says the settings are blocks |
| settings/flowrun/config.json, GET / PUT /flows/config, `flow_config.read_config / effective / put_level`, `flow_run.run_values / config_of / CONFIG_DIR` | GONE (the project's blocks; `flow_run.project_values` / `values_of`) |
| the runner-only Run (POST /flows/run start of flow `xmas_dun02_rogue`, `Helper.start`) | GONE (refused in words: `project_has_its_own_route`); a start is a project's |
| the check `POST /flows/run/check {flow, keys}` | `{project, node}` (the backend computes the keys and settings) |
| lib/flow/runner.ts, runner_sim.ts, config.ts, runners/index.ts, runners/xmas_dun02_rogue.gen.ts, components/flows/blockly-runner.ts, their tests (runner.test.ts, runner_sim.test.ts, config.test.ts), the "Inside the runner" chip and Load entry, the runner page's CSS | GONE; the checklist helpers moved to lib/flow/settings.ts |
| scripts/runner_flow_export.py `export` / `check` (the gen.ts and its drift test) | GONE; `show` and `build()` stay (the loop's outline: 5b's map, the docs; its own tests keep its numbers, flags and code symbols honest) |
| the registry in scripts/flow_config.py | poring_flow.settings (flow_config re-exports it: dungeon_hunt's --tune, flow_run, flow_play, the tests) |

**Not a setting block (what a person still cannot set as a block):** the five hotbar keys (they
are FUNCTIONS: the keys tab, as before); the runner's fixed part (`flow_run.FIXED`: the character
rogue, the map, --strategy P2, the seed) and the flags flow_config.NOT_SETTINGS lists with their
reasons (--player-mode, the GM trial lines, --heal-candy ...); the loop itself (5b).

**Deploy (after the merge):** a guarded backend restart (routes_flowrun: the check route, the config
routes gone) and a restart of the Run helper (parse_request takes project checks only; on bot-server it is a
plain process, `scripts/flow_run.py serve`, restarted by its PID: the unit
`scripts/host/poring-lab-flowrun.service` is not installed there). Until both, a running helper still accepts the old runner-only start; the
new page never sends one. A series started from main before the merge keeps main's code.

### 12.3 5b (➡️ STARTED 2026-11-14 ~18:2x, Batt: "go on, no need to ask me again"; 10.2)

The loop as playable blocks: HuntState (section 2b, 4b) moves the loop's state out of run()'s
closures so look, choose_target, walk_to_target, strike, wait_kill, loot and explore each play as
a bounded live block; then the outline's description blocks become the map's tabs, each one doing
what it shows. Each step A/B'd against the step before, the hunt never playing worse.
➡️ 5b is split in two (section 13): **5b-1** (the refactor: HuntState and the loop as steps; no
behaviour) and **5b-2** (the steps as live blocks; designed in 13.4, not built).

### 12.4 Round 20 (matpilot's review of eb160ee1 at 1440 x 900 and 390 x 844; fixed 2026-11-14 ~19:2x ICT, branch fix/round20)

The reviewer checked the page read-only; the parent decided each finding. ➡️ This SUPERSEDES, in
12.1: the "tabs" row (the order is survival, knife, ...; "loop" is "timing"), the "block" row (rows,
not one row; the warning on rows of its own), the "toolbox" row (sub-categories, not one list with the
shown tab first), the "Python view" row (respawn_at no longer in the box; the comment carries the
lint's words) and the "lint" row (a safety switch off is a warning; the "not used" words per block);
and in 12.1's last paragraph "the one box with its 121 blocks": it holds 116 (below, #4a).

| # | Finding (the reviewer's measure) | Fixed how |
|---|---|---|
| 1 | The footer's Python sheet at 390: 14 file buttons in wrapped rows took 295 of 331 px; the code box was 390 x 0, unreachable (the sheet did not scroll) | On a phone the file buttons are ONE row that scrolls sideways (the selected one kept in view: the row scrolls, never the page), in the sheet and in the Python view; the sheet scrolls (`overflow-y: auto`) and the code keeps at least 12rem (studio.css; editor_css.test.ts pins the rules) |
| 2 | Setting blocks cut at 390 (scale 0.6, blocks from x 135): 108 of 121; alarm_fast 447 px (57 % shown), near_single_still; main's block 397 px; the zoom buttons over REGEN_STOP's "50" and POS_FLY_S's "20", the trashcan over NPC_NO_FIGHT's "cells" | A setting block is laid out on ROWS (settings.ts `settingRows`, blockdefs `settingDef`): its words wrapped (balanced) over one or more rows, a point-or-none's at / none menu on its own row, then the value with its unit and `· var` (the var on a row of its own where that row would be too wide), then a safety switch's warning rows, then 3 rows for the lint's note. Budget: no row over 300 workspace units = 180 px at 0.6, so a block ends by x 315 px, before the trashcan's column at x 323 (390 - 20 - 47): the controls no longer cover any value, by construction. main's blocks too: the hat's title on two rows (`titleLines`), the runner's block a role a row, the save point on three (➡️ NOT what Blockly drew: with inputs inline, zelos joins a message's leftover fields to the NEXT row, so the save point stayed one row and the runner's rows were off by one; the reviewer's re-measure, fixed in 12.5 A). MEASURED by a model of Blockly's text widths (no browser here; Blockly's getHeightWidth needs a rendered workspace, the real-Blockly tests are headless): per-character widths of a wide sans at 12 pt, zelos' paddings FITTED to the reviewer's own numbers (npc_guard's row 430 units, with its warning 1018, alarm_fast's 745: the model gives +2.4 %, +4.5 % and +2.6 % of them: it errs wide; settings.test.ts allows -3 / +10 %). Every one of the 121 blocks' rows, the note rows' longest kinds and main's rows are under the budget (settings.test.ts). Average 2.8 rows a block |
| 3 | Safety switches (respawn, npc_guard, garm_fly, alarm_fast): the "⚠ off" warning a field at the end of the row (258 -> 611 px at 390, all off-screen); a switch off added no lint finding; tooltips said "While it is off: off: ..." | The warning on rows of its own, shown while the switch is off (the `pl_setting` extension, blockly-register.ts `syncSetting`; no event, no undo step); a switch off where a hunt core reads it is a `settings_safety` WARNING on its block (a warning never blocks a Run; the chip and the /maps card count it); its Python line ends `· ⚠ off: <warning>`; the registry's `warn` no longer starts with "off:" (the tooltip says "While it is off: ...") |
| 4a | Five settings of the ready-made box never used in a Run (potion_below, fly_below, weight_home, respawn_at, respawn_confirm_at: drink, fly_away, bag_full and the exits tab's respawn_button / respawn_ok play them) read as live; the respawn tab had no IN A RUN line | DECISION (the parent): REMOVED from the box (`project_xmas_dun02.json` = `xmasProject()`, byte-identical canonical; project.ts `BOX_PLAYS_THEM`, which test_settings.py pins to the engine's live.takeovers for that box): it holds 116 setting blocks. The argv is unchanged: test_settings_blocks.py still gives today's 97 arguments (the five are passed at their defaults, as before) and proves them NOT USED -- the box plays them, so the runner's own handler is off (its plays) -- and that a block a person adds changes that flag's value only. The frozen stage 2/3/4 arms are byte-identical (their sha256 pinned). DECISION: a block a Run of this box does not use -- a takeover (live.takeovers) or a `needs` not met (quick_drop_scaled while quick_drop is off, near_single_still while near_single is off, NPC_NO_FIGHT while npc_guard is off; the ROOT switch is named) or a map without a hunt core -- is GREYED (a light-slate block style of its own with dark words, never Blockly's disabled state) with rows "· not used here: the drink event plays it" / "· not used while npc_guard is off", the same in its tooltip and as its Python line's comment. ONE computation: `poring_flow/lint/settings.py` `notes` (the lint's own `_analyse`), sent by POST /flows/lint as `settings` and printed by pyproject, so the lint, the block and the Python never disagree. The ready-made box shows two such blocks (quick_drop_scaled, near_single_still: their switches are off by default). The respawn and exits tabs' IN A RUN lines now say which function of another tab plays their group's setting ("respawn_button (tab exits) replaces the runner's clicks on the death dialog (its setting respawn_at is not used in this box)") |
| 4b | 11 blocks read as fragments ("…" first; HP_DROP_PTS "…" last) | Each names its subject in the registry's `words`: "a hit the Battle Log missed: her HP falls by at least" / "... that HP fall within", "the walk toward a target stops this far short of it", "a still screen: this many frame pairs in a row", "exploring favours the regions seen least", "a near strike too (from 2 cells): one click, then wait", "the quick drop's wait grows with the distance", "Garm Baby alarm: seen in this many detections in a row", "Garm Baby alarm also read on the HUD's boxes and inside a strike or a wait", "Garm Baby alarm: one box this sure is enough (0 = off)", "the HUD: a fresh box every". Nothing pinned the old words but the tests updated here (runner_flow_export's outline has its own describe strings and pins none of the registry's) |
| 4c | "then confirm (OK) at at x 714"; "HP points ... 2 %"; "looks a second 5"; "1 cells" | "then confirm with the OK button" (its menu says "at"); HP_DROP_PTS is percent POINTS of her HP bar (dungeon_hunt: `(max - now) * 100 >= HP_DROP_PTS`), so its unit is "% of max HP"; READ_HZ "the bot reads the screen [5] times a second"; a unit said of ONE is singular (`SINGULAR`: "1 cell", "in steps of 1 cell", "1 time a second"), on the block (the extension), the tooltip, the lint and the Python comment |
| 4d | Tooltips said "A map's block replaces Global's there" in a project without a Global node | Said only when the project has one; else "Delete this block: the default X applies" |
| 5 | The Settings flyout one flat list (121 blocks, ~6,900 px; a 1,062 px header cut at 1440; 877 px wide at 390, 109 of 133 items past the edge) in an order unlike the tabs'; "knife" found 3 of 6; "loop" collided with Control's loop | One sub-category per group, named as its tab, in the tabs' order (GROUPS reordered: survival before knife, as the box's tabs; argv's order is FIELDS', unchanged), each headed by its group's title and line wrapped to the blocks' width; the blocks are the narrow ones of #2. Every setting has search words (`find`: its group's, FIND_GROUP, and its own, FIND): "knife" finds all six, "garm" the five Garm Baby settings; none is found by "loop". The group "loop" is "timing" everywhere (registry, tabs, the ready-made box, its Python file `timing.py`, the strip, docs, tests); no frozen fixture names a "loop" tab, so no alias was needed (a project saved with one still runs: a run reads a setting from any tab of the node; only the strip's line is the group's) |
| 5 (question) | Does anything stop a second block of a setting already in another tab of the same node? | Before: the browser took it into the project; the ENGINE then refused the whole project (one namespace per node: "D0_PX is defined twice on xmas_dun02: a variable in tab aim and a variable in tab loot"), at /flows/lint and /flows/python, shown as a notice, not on the block. Now the block editor refuses it on the block itself ("the tab aim of xmas_dun02 sets it already: one block per setting on a node"), so the project never becomes invalid; the engine's rule stays the backstop, and the Python view's reader refuses a duplicate naming both tabs (test_settings.py, settings.test.ts). It is an error of the project's shape, not a lint finding: a lint never sees such a project |
| 6 | /maps "Tabs and names": 162 raw lines (`potion_below = 0.4`), ~10 screens; after a click selected the xmas_dun02 card the PAGE was 1,064 px tall at 1440 x 900 and a scrollIntoView left a 164 px black band | Each tab FOLDS (a `<details>`, folded by default) with a line saying what it holds ("aim · 33 settings (1 changed)"); a setting reads as its block does ("heal at HP under 40 %", "the client's pick within 1 cell") with its var, and one that differs from our default comes first, marked "changed" (nodewords `tabRows` / `tabSummary`). The page: the node inspector's visually hidden words (the entries table's sr-only "remove", `position: absolute`) had `.maps-body` as their containing block, OUTSIDE the side panel's scroll box, so one about 1,064 px down the inspector grew the page; `.maps-side-body` is now `position: relative` (their containing block, inside the scroll box), `.maps-body` is `overflow: hidden` on a wide screen (visible on a phone, whose page scrolls), and the lint chip's scrollIntoView runs on a phone only. Found by reading the CSS (no browser here): the reviewer re-measures |

**Measured only by the model and the tests here (no browser), for the reviewer's re-measure:** every
block width (#2: getBoundingClientRect of each setting block at 390 and 1440, and main's), the rows'
heights and the gaps the editor keeps (a block that grows pushes the ones under it down: BlockEditor
`restack`; ➡️ round 23, 12.7 A: `settle`, every top block from its measured height), the greyed style's look in light and dark, the Python sheet at 390 (#1), the flyout's
width at 390 (#5), and the /maps page height after selecting the card (#6).

### 12.5 Round 21: pickers instead of textboxes (Batt 2026-11-14 ~19:4x ICT; built 2026-11-14, branch feat/pickers, written 20:54 ICT from `date`; offline only)

**Batt's words (2026-11-14 ~19:4x, Thai, translated; with screenshots of the main tab's hat --
"geffen x 119 y 40", `use_model ( model="xmas02" )`, the hunt block's "heal: call heal", "Fly Wing:
call fly_wing", "Knife on: call knife_on" --, "stop home", and the survival tab's drink event --
`this node when hp_percent() < 50`, `until hp_percent() >= 51`, rank, pause 0.7 s, "at most _ a
minute", "escalate to _", `do call heal ( )`):** "Fields that choose a value, like use_model or
'this node when', should be DROPDOWNS with the values to choose from, so you know what there is.
Typing should work like a search, guessing the word, and help with AUTO-COMPLETION. Check matpilot:
where a value must be entered, I made it a visual UI, e.g. the turn angle, more/less speed. Our
project should do that too, for values that are not naming, such as functions or variables."

**The rule** (the parent's reading; ADR-0020 Amendment K): free text ONLY where a name is DEFINED
(a function's name, a variable's name, an event's name, a tab's name); every other field is a
picker: (a) a REFERENCE to something that exists is a dropdown of what exists, with type-to-filter
search; (b) a NUMBER is a visual control in matpilot's way; (c) a CONDITION is a structured picker
with a typed fallback that autocompletes. The stored IR and the Python text stay EXACTLY as they
were: a picker edits the same string or number, so old projects load unchanged, and a value that
is not in the list is kept, marked, and named by the lint.

#### 12.5.1 The kit

| Piece | Where | What |
|---|---|---|
| Two field types | `components/flows/blockly-pickers.ts` | `field_pl_num` (a FieldNumber: it saves, validates and loads as field_number did, the field's own min / max / precision unchanged) and `field_pl_text` (a FieldTextInput: any text saves and loads as field_input did). Each carries a `pick` (the JSON block definition) saying which picker opens in Blockly's DropDownDiv, in the block's colour. Registered by `register()` before the block types, so the headless tests register exactly what the page does |
| The DOM kit | the same file, ported from matpilot 4022c87 `src/lib/blocks/fields/common.ts` (MIT; THIRD_PARTY.md) | `svgEl` / `htmlEl` / `button`, `openPicker` (the block's colours, never taller than the blocks area, `keepInside`), `closePicker`, `onDrag` (a press and its drag are ONE undo step), `makeSlider` (role slider, aria values). Every picker session is one Blockly event group (one undo step). Every key typed in a picker stays in it (Backspace never deletes the block); Escape closes (➡️ round 22, 12.6: Escape CANCELS the whole session; `keepInside` is gone: a picker never covers its field). The DOM is built element by element: no innerHTML (the CSP, gamefile.test.ts) |
| stepper | seconds, counts, ranks, a setting's number | − value +, a native range slider over the control's range and step (`lo` / `hi` / `step`; widened to hold a loaded value outside it, so a step never jumps), presets (0.5, 1, 2, 5, 10 s ...), a number box to type an exact value (kept exactly as typed: the field's own validation decides) |
| percent | a setting's share (knife_hp_min, WEIGHT_MAX, ...) | the LEVER BAR (matpilot's throttle, lying down): a bar that fills to the value like an HP bar -- red low, green high; the bag's (weight_home, WEIGHT_MAX, REGEN_STOP) the other way round --, dragged or tapped, arrows / Page Up / Down / Home / End; with the stepper under it |
| point | respawn_at, respawn_confirm_at (x, y in the 1280 x 720 game picture) | both fields' steppers in ONE picker, and the picture with its dot: tap or drag to place it |
| cell | the save point, walk to, a walk exit (a map cell's x, y) | both fields' steppers in one picker (no picture: the map's size is not known at edit time) |
| optnum | an event's rank, "at most … a run / a minute", "in 10 min:", "insert fails:" (text fields where EMPTY means none or the engine's default) | a "no limit" / "the table order" / "the default (10)" button and a stepper over the converter's own range; the empty field shows `auto`, `—` or `default 10`; a text that is no whole number is kept (`abc ⚠`), the converter says why, as before |
| ref | every reference (12.5.2) | a search box and the list under it: typing ranks the list (`pickers.ts rankChoices`: the word itself, a start, every typed word starting a word of it -- matpilot's block search --, inside it, its letters in order); arrows and Enter, or a tap; a word the list does not have is offered "as typed" where the converter would take it (a new stop reason, a function not written yet), else refused with why; a model must be one of the list. Closed, the field shows its value and `▾`, and `⚠` when the value is not one of what exists (kept as it is: the lint names it); an empty optional role shows `none` |
| expr | a pl_expr's text (a condition or a value), a catalogue block's inputs (pl_action, pl_do), a call's inputs (pl_call, pl_callv) | ABOVE: a condition as `sensor ▾  comparison ▾  value` (the catalogue's sensors, live ones first, and the node's functions; a sensor's own input such as hotbar_count's key as a dropdown; the value's control follows the sensor: the lever for hp_percent(), a stepper for a count, the map names for current_map()); a count (repeat's times) as a stepper; a block's inputs as rows of pickers (use_model's model from the models list, use_skill's key F1-F9, a number as a number box; a call's inputs by the function's own parameters, `eat("F6")` keeping its input by position). BELOW: the text itself, which AUTOCOMPLETES while typing (`completions`: sensors with their parentheses, functions, variables and the function's own inputs, True / False / OK / FAILED, and / or / not, mob( item( map_id( cell(; after a value the comparisons; after `key=` the hotbar keys). Every builder change prints the text with the block's own printer (expr.ts exprText), so `hp_percent() < 50` stays exactly that (pickers.test.ts: every event condition of the ready-made projects prints back byte for byte). Escape keeps the old text; a tap outside keeps what was typed (as Blockly's own text field) (➡️ round 22, 12.6: Escape cancels every kind, Done / Enter / a tap outside keep) |
| name | a function's name (pl_def NAME) | free text (Blockly's own editor); on the monsters tab it first offers `attack_<class>` for each monster of the node's model (the ones not written yet first), a suggestion only |
| Phone | all of them | on a touch screen a picker does not focus its text box (the keyboard would cover the list); inputs are 16 px (no zoom-in); touch targets 40 px; the DropDownDiv is never taller than the blocks area and is moved into it when it fits neither below nor above (matpilot keepInside); Blockly's phone `prompt()` for text fields is no longer used by any picker |
| Pure part | `lib/flow/pickers.ts` (+ pickers.test.ts) | the ranking, the steps (`snap`, `stepBy`, `sliderKey` ported from matpilot), the option sources, `condOf` / `condText`, `completions`, the input rows, `closedText` (what a closed field shows: the width model uses it) |

#### 12.5.2 Each block and field

Converted (field: picker, its options' source):

| Block | Field | Picker | Options from |
|---|---|---|---|
| main's save point (pl_save_point) | MAP | ref, maps with a Kafra first | GET /flows/maps (the local KB at run time: names, a Kafra there) + the project's map nodes |
| | X, Y | cell | -- |
| use_model, and every other catalogue block (pl_action, pl_do) | ARGS | expr (inputs as rows) | the catalogue's parameters of that block; use_model's `model` from the models (models.yaml via the catalogue: id, its map, live / not adopted) |
| the runner (pl_dungeon_hunt) | HEAL, FLY, KNIFE_ON, KNIFE_BACK, HOME, RESPAWN, RESPAWN_OK, EAT | ref (role), the role's usual function first, then the functions that press a key, then the others; never an event | the node's and Global's functions (each with what it does: "presses F1 · tab keys", "calls wield_knife", "clicks a point", its inputs) + those written on the tab and not converted yet |
| stop (pl_stop) | REASON | ref, typing a new one allowed | the project's own stop reasons (with how often), then done / home |
| call (pl_call), a function's value (pl_callv) | PROC | ref | functions, then events (the node's and Global's) |
| | ARGS | expr (callargs) | the called function's own inputs (a key-like input as F1-F9) |
| event (pl_event) | WHEN, UNTIL, REARM (their pl_expr) | expr (condition) | the catalogue's sensors (not the trained models' -- they have blocks of their own -- nor `position`) and the node's functions; the comparisons |
| | RANK | optnum 1..99, empty `auto` | -- |
| | COOLDOWN | stepper 0..30 s, step 0.1 (the field's own 0..3600 kept) | -- |
| | MAX_RUN, MAX_MIN, MAX_10, FAILS | optnum (1..100, 1..60, 1..100, 1..10), empty `—` / `default 10` / `default 3` | -- |
| | ESCALATE | ref (escalate), empty `none` | the node's and Global's functions (no events: the engine resolves a procedure) |
| | PRIORITY, MODE, THEN | Blockly's dropdowns already (unchanged) | -- |
| wait (pl_wait) | SECONDS | stepper 0..60 s, step 0.5 | -- |
| wait until (pl_wait_until) | TIMEOUT | stepper 0..120 s | -- |
| if / while / wait until / not / and / or | their condition (pl_expr) | expr (condition) | as the event's |
| repeat | TIMES (its pl_expr) | expr (a number: a stepper, presets 1 2 3 5 10) | -- |
| press key (pl_press_key), log in's credential, the detector blocks' model and class, the hunt block's rule versions | -- | Blockly's dropdowns already (unchanged) | -- |
| walk to (pl_walk_to) | MAP; X, Y | ref (map); cell | as the save point's |
| Kafra teleport | TO | ref (map) | as above |
| the exits (walk, npc, item, item by function) | TO_BLOCK; TO_ENTRY | ref (node); ref (entry of that node) | the project's map nodes; the entries of the node TO_BLOCK names |
| | walk exit's MAP, X, Y; item-by-function's FN | ref (map), cell; ref (function) | as above |
| open window | WINDOW | ref | the catalogue's `windows` (the L2 windows of the client) |
| log in | SERVER | ref | the catalogue's `servers` (config/environments.yaml, the lab's marked) |
| set (pl_set) | VAR | ref (variable), typing allowed | the function's own inputs, then the variables of the node's tabs and Global's |
| a function (pl_def) | NAME | name (free text; attack_<class> suggested on the monsters tab) | the node's model's monsters (catalogue models, `strikes`) |
| every setting block (116 in the box, 121 in all) | VALUE (number, int) | stepper over the registry's lo..hi, step and unit | the registry (settings.gen.ts) |
| | VALUE (share) | percent lever bar | the registry |
| | X, Y (point, point or none) | point (with the game picture) | -- |
| | VALUE (switch, choice), AT | Blockly's dropdowns already (unchanged) | -- |

Left as TEXT, and why:

| Block | Field | Why |
|---|---|---|
| a function (pl_def) | NAME (off the monsters tab), PARAMS | names it DEFINES (its inputs are names too) |
| a variable (pl_vardecl) | NAME | a name it defines |
| an event (pl_event) | NAME | a name it defines (the event's key) |
| a tab | its name | a name it defines (the tab row, not a block) |
| talk to the NPC, set the save point at / teleport with / rent a cart from the Kafra, buy, sell, store, take, npc warp | NPC | an NPC KEY (`n_` + 8 hex of a hash: one-way, local only, ADR-0020 Q11); the names behind them are the KB's local labels. A picker needs the node map's world sheet fetched per map (GET /flows/world): not built in this round (a follow-up) |
| choose menu option, npc warp | OPTION / OPTIONS | option keys, the same as the NPC's |
| use item, item warp, buy / sell / store / take | ITEM / ITEMS / KEEP | item ids or variables, comma separated; the item names are client data (no list served yet) |
| choose the character | CHAR | a character's name on the server: no list exists at edit time (empty = the remembered slot) |
| extend / disable event (retired blocks) | KEY | refused in the project model since 2026-11-13 (a map replaces Global's event by writing its own); not offered |
| the raw blocks (pl_raw, pl_raw_expr) | TEXT | read-only labels (edited in the JSON view) |

#### 12.5.3 The map names

The backend knows them at run time: `GET /flows/maps?source=local|sample&server=` (routes_flows,
read gate and the /flows/world read budget) returns `{server, source, maps: [{id, kafra}], notes}`
-- `kbsheet.known_maps` reads the local KB (data/kb: the generated sheets' names, the L3 warps' both
ends, the NPCs' and the Kafras' maps, the spawn lines'; a Kafra there = a save point can be set
there), `editor.sample_maps` the committed synthetic sample. Nothing is written and no list of map
names is committed (test_kbsheet.py and test_routes_flows.py use synthetic files). The studio
fetches it once per world and server (ProjectStudio `maps`); until it arrives a map picker lists the
project's own maps and marks nothing unknown.

#### 12.5.4 Round 20's re-measure leftovers (the reviewer, live on main bb6d41eb at 1440 x 900 and 390 x 844; each decision the parent's)

The reviewer PASSED the 116 setting blocks (widest 172 px at 390, right edge <= 307), the zoom /
trash on the safety tab, the footer Python sheet, the greyed unused settings, safety-off as a lint
WARNING, the flyout sub-categories, /maps' folds and the page height. The rest:

| # | Finding | Decision | Done how |
|---|---|---|---|
| A | main's stack at 390 cut (main's block 287 px from x 135, right edge 422): "the save point is on geffen x 119 y 40" (404), "use_model ( model="xmas02" ) ● plays live" (402), "Fly Wing: call fly_wing Knife on: call knife_on" (413); the runner's rows OFF BY ONE ("call knife_back home (Butterfly Wing):" as one step) | one role per row, its label with its picker; the hat and use_model wrap to the 300-unit budget; main's stack ends before x 315; a width-model test | FIXED (by the model; a browser re-measures). The cause: zelos draws every input inline and ends a row only after an END-ROW input (or around a statement, or before every input when the block's inputs are not inline: `zelos/info.ts shouldStartNewRow_`), and Blockly's JSON puts a message's leftover fields in an implicit DUMMY input -- so round 20's messages-as-rows were not rows. Now every row ends with an end-row input: the save point "the save point is" / "on geffen ▾" / "x 119 y 40"; the runner one role a row, its words with its picker ("heal: heal ▾" ... "Knife off: knife_back ▾", "home:", "died:", "confirm:", "eat:"; "call" dropped, "home (Butterfly Wing)" / "after a death" / "then confirm" shortened to fit); every statement block's badge and its last-run line on rows of their own, shown only while they say something (`blockdefs.ownLabelRows`, a pass over the definitions, so a block added later -- 5b-2's -- gets it too; `pl_label_rows`); a catalogue block's inputs on their own row ("use_model" / `( model="xmas02" )`). THE MODEL: `lib/flow/layout.ts` (zelos' row rules over the definitions, settings.ts' text widths, a 20-unit statement indent and a 20-unit field box: zelos' 16 + 4); its positive case is the reviewer's three rows (the model gives +5.8 %, +9.4 %, +10.6 %: it errs wide); layout.test.ts: every row of every block of every tab of the ready-made projects AND the frozen A/B arms <= 300 units (the box's widest per tab: main 282 "died: respawn_button ▾", survival 296 the shortened `hotbar_count(…) > 0`, knife 276 "call wield_damascus ▾", exits 256, monsters 235, keys 228 a badge row); blockly_pickers.test.ts: the REAL Blockly builds those rows (each role's words and picker in ONE end-row input) |
| B | a second copy of a setting (knife_max_s into main while knife has it): refused under the canvas, Simulate off, but the block unmarked, the message naming only the other tab; Run (amber) ENABLED -- what would it play? | mark the copy (⚠ + "already set in tab knife; one block per setting on a node"); the message names both tabs; Run and Check DISABLED while the editor holds a problem, with the reason; never a Run of a project other than what the screen shows | FIXED. How Run gets its project TODAY (checked): BlockEditor converts the tab after every edit (`tabFromWorkspace`); when it fails, `onProject` is NOT called, so the studio's `project` stays the last good one, and `projectRun = { project, node }` -> `useLiveRun`'s `runRef` -> the POST of a start or a check sent THAT project: Run would have played the project from before the copy, without it. Now: the message is "knife_max_s is set on this tab (main) and on the tab knife of xmas_dun02: one block per setting on a node (delete one of the two)"; the copy's own note rows say "⚠ already set in tab knife; one block per setting on a node" in the warning colour (an Issue's `note`, BlockEditor paint; any other block with such a problem gets Blockly's warning); `editorHeld` holds Run (footer and Before Run) and "Check the game" (and its automatic first check), the reason shown under Run ("Run is held: the blocks of tab main have 1 problem ...") and under the problems ("Run and Check wait until these are fixed") |
| C | the five settings the box leaves out still in the flyout and the search, looking live ("heal" lists potion_below and fly_below first) | in the flyout and the search, mark a setting the open node's box replaces with the lint's notes (greyed, "not used here: the drink event plays it"); keep it listed | FIXED. `box.ts boxReplaced` (the lint's `box[node]` takeovers, the lint's own words: box.test.ts pins them to lint/settings.py `_use`); the `pl_setting` extension writes them into a FLYOUT block's note rows before the flyout measures it, and greys it once drawn; the search's results are flyout blocks too. Deleting the drink event makes the next lint drop it, and the setting is live in the flyout again |
| D | with fly_below gone, fly_rate / fly_rate_below read "or HP falling faster than 150 HP/s", "while under 50 %"; the IN A RUN line repeats it | name the subject; check every block that began as a continuation of a removed one | FIXED: "Fly Wing when HP falls faster than", "the Fly Wing's fall rule: only while HP is under"; respawn_confirm_at (it continued respawn_at, also removed) "the OK button that confirms the respawn"; the IN A RUN line "The HP-rate fly stays the runner's: Fly Wing when HP falls faster than 150 HP/s (fly_rate); the Fly Wing's fall rule: only while HP is under 50 % (fly_rate_below)." (poring_flow settings.py; settings.gen.ts regenerated, drift-tested). Checked the rest: knife_hp_min ("or at once under HP") continues knife_max_s, which is still there beside it: KEPT. The words change the Python view's comments of these three settings (the comments are words; the values and the round trips are unchanged) |
| E | "Global" named in a project without a Global node: the SETTINGS strip line, IMPORTS, main's tab title, the /maps inspector | name Global only when the project has one | FIXED: `settingTabNote(..., hasGlobal)` ("a deleted one falls back to the default"), the IMPORTS part (its tabs only), main's tab title, the inspector's "Tabs and names" line |
| F | at 390 the events and functions under the controls (fly_away 306 px, 83 % shown: rank, "resume ▾", "s after each run · at most"; attack_cruiser's "t, priority=1", strike's / wait_steal's / wait_kill's / loot's "● plays live") | the event, function and recipe blocks wrap to the same budget | FIXED (by the model): the event one or two fields a row ("this node when" / its condition / "event drink" / "class ▾" / "rank auto" / "mode ▾" / "then ▾" / "until" / ... / "insert fails: default 3" / "then escalate to none ▾"); and / or a BLOCK of its terms, one a row (`sees_boss() or hp_percent() < 25` was one 31-character text; blocks.ts exprBlock, the IR the same: the round trips cover it); "function" / its name / its inputs on three rows; a call's inputs on their own row; if / while / wait until their condition on its own row; on a phone a condition wider than the row (the eat events' `hotbar_count(key="F6") == 0`) shows shortened in the middle, `hotbar_count(…) == 0`, whole in its tooltip and its picker (`shortExpr`, `EXPR_SHOW_UNITS` = the budget less the sides) (➡️ SUPERSEDED by round 22, 12.6 #5: it read the same twice; a long condition now WRAPS, whole) |
| G | the folded strip at 390 cut on survival, knife, exits, respawn ("IN A RUN: 3 events replace the runner's own · 4 m…", 380-421 px in 366) | it fits | FIXED by words: "IN A RUN: 3 events replace the runner · +4"; the respawn tab "2 functions in exits play it"; box.test.ts: every tab's line <= 45 characters (`FOLD_MAX_CHARS`, from the reviewer's ~7.3 px a character) |
| H1 | weight_exit's tooltip "a switch for the settings it needs" (weight_home is out of the box) | say what it switches | FIXED: a switch with no flag of its own says which settings it turns on: "a switch with no flag of its own: weight_home (go home when the bag is over) is used only while it is on" |
| H2 | /maps' folds show "off · near_single_still" with no not-used note; NPC_NO_FIGHT none | the same notes on /maps | FIXED: the inspector's setting rows carry the lint's words (`settings[path].unused`), and a safety switch off is marked "⚠ off" (its warning on hover) |
| H3 | at 390 with Settings open the toolbox is 22 rows; Functions and Advanced scroll below the canvas | collapse, or keep them reachable | FIXED: Settings is the LAST category (studio.test.ts pins the order), so opening it never moves Functions and Advanced |
| H4 | the 390 Python sheet: the code box takes the file's full height, the sheet scrolls, the file row and the × scroll away | keep them sticky, let the code scroll | FIXED: the code box takes the room left (at least 12rem) and scrolls inside; the header and the file row are sticky (studio.css; editor_css.test.ts) |

#### 12.5.5 Not measured here (no browser): the re-measure list

- every picker's position at 390 x 844 and 1440 x 900: opening under its field or above it, never
  past the blocks area (the DropDownDiv), and with a phone's keyboard open (a ref's search box, a
  condition's text);
- touch: the lever bar's drag, the point picture's tap, the steppers' 40 px buttons, the native
  sliders and selects;
- keyboard: Enter on a focused field opens its picker, arrows in the lists and the sliders, Escape;
- the closed fields' `▾` and `⚠` (and the amber unknown text), the empty words (`auto`, `—`,
  `default 10`, `none`);
- every block's width at 390 against the model (layout.test.ts: main's widest row 282 units =
  169 px, so its right edge at ~304 px; survival's 296; the events', functions' and recipes'); the
  badge and run rows appearing and hiding (the blocks under them move: `restack` now for nested
  blocks too; ➡️ round 23, 12.7 A: `settle`);
- and / or as blocks of their terms (fly_away), and the shortened condition (➡️ round 22: wrapped) on a phone with its
  tooltip;
- the Settings flyout's and the search's greyed blocks with their note rows;
- the duplicate setting's own rows and Run / Check held with the reason;
- the folded strip line on survival, knife, exits and respawn; the Python sheet's sticky rows; the
  toolbox with Settings last and open.

### 12.6 Round 22: the reviewer's browser measure of round 21 (written 2026-11-14 22:38 ICT from `date`; branch fix/round22 from 5d6bf17e; offline only)

The reviewer measured round 21 live on main 5d6bf17e in a real browser at 1440 x 900 and 390 x 844.
PASS: the block widths, the runner rows, the duplicate copy holding Run / Check, the flyout and
search greying, round 20's leftovers, and no bare textbox that should be a picker. The gaps, each
with the parent's decision and what was done:

| # | Finding (the reviewer's measure) | Decision | Done how |
|---|---|---|---|
| 1 | A picker 290-407 px tall that fits neither below nor above its field was pushed to the top of the blocks area, OVER its own field, its arrow at another block: 9 cases at 390 (survival's until condition, knife's wield_damascus ref, RESPAWN_LOAD_S, HP_DROP_PTS, APPROACH_KEEP, WALK_EVERY_S, END_FLY_BELOW, STOCK_READ_S, BOX_FRESH_S), 13 at 1440 (survival's two conditions, drink's rank, the at-most rows and escalate, fly_rate_below, the call refs on knife and exits, HP_DROP_PTS, FAR_MAX_S, END_FLY_BELOW) | before opening, scroll the workspace so the field sits where the picker fits; when it still cannot, a compact layout (fewer rows, no duplicate slider); never cover the field or point at another block; a test of the placement | FIXED (a browser re-measures). `pickers.ts placePicker` (pure): below when it fits (Blockly's PADDING_Y 16 and an 8 px margin counted), else above; else, when the area holds the field and the picker, SCROLL the workspace so the field goes to the area's top (or bottom, whichever is the shorter scroll; `WorkspaceSvg.scroll`); else COMPACT (no title, presets, key hint or typed-text label; a smaller picture, list and lever); else the larger side with the picker's height capped to it (it scrolls inside). `openPicker` measures the hidden DropDownDiv, plans, scrolls, measures again, then shows; round 21's `keepInside` (which moved a picker over its field) is gone. pickers.test.ts: the cases, and a sweep of field positions x picker heights in a 390-px area proving the picker always stays on its side |
| 2 | A MOUSE drag in the point picker read y wrong (50 % -> y 360 right; 55 % -> 691, from 60 % stuck at 719); a touch drag was right; y looked measured from the picker's top, ~59 px above the picture | FIX it and test it | FIXED in the code, the cause NOT reproduced here (no browser; ➡️ round 23, 12.7 B: still wrong in the COMPACT picker at 1440 -- the drag now maps from the drawn picture's box, and the scroll lock holds the picker's own root). Each place is now mapped through the picture's own screen matrix (`getScreenCTM().inverse()`: its box, viewBox and any transform), else its box at that moment (`toViewBox`), and the picker's content cannot scroll under the pointer during a drag (its scrollTop held: the X slider under the picture took the focus when the picker opened, which can scroll a capped picker -- the likeliest cause). pickers.test.ts: 50 / 55 / 60 % read 360 / 396 / 432 |
| 3 | ArrowDown on a select inside the condition picker changed the value AND closed the picker, the focus on the page body: a keyboard user could not browse the 36 sensors (a mouse change kept it open) | arrow keys browse and update without closing | FIXED: the cause -- the change drew the picker's parts again, the focused select left the page, the focus fell outside the DropDownDiv and Blockly closed it (its popover focus loss). Now the focus waits on the picker itself while its parts are drawn again, then goes to the new control of the same name (`redraw`) |
| 4 | Escape inconsistent: steppers, the lever, cells and dropdowns applied at once and Escape kept the change; text typed in the condition box was dropped on Escape | Escape CANCELS the whole session for every kind, restoring the value from before it opened; Done, Enter or a click outside APPLIES; say so in the picker | FIXED: `session([fields])` records every field a picker may change (a point's and a cell's pair too); Escape and a new **Cancel** button put them back in the session's group and then drop the group's events from the undo stack (blockly_pickers.test.ts: the value back, no undo step; a kept session one undo step). ➡️ Round 23 (12.7 C): that drop ran before Blockly's events fired (an animation frame later), so Ctrl+Z re-applied a cancelled value; the preview now records no undo step and a kept session is ONE step of its own. Every picker ends with Cancel, Done and "Esc: cancel · Enter or Done: keep"; Enter keeps (not on a button or a select) |
| 5 | Shortened conditions read the same in the until rows ("hotbar_count(…) == 0" twice), and the when rows kept a stray '6")' | never cut the arguments; WRAP a long condition onto more rows at a token boundary within the 300-unit budget; the full text in the tooltip | FIXED: `wrapExpr` breaks between tokens -- before a comparison or and / or, else after "(" or ",", else before the token that does not fit -- each line within the one-line limit (`WRAP_UNITS` = `EXPR_SHOW_UNITS` = 232); the field shows the first line, each further line is a dark label in a row of its own (`syncExprWrap`, the `pl_expr_wrap` extension and the editor's paint): one field a row, so Blockly still draws the block as ONE white box. `hotbar_count(key="F6") == 0` shows `hotbar_count(` / `key="F6") == 0` (the whole of the first token group, 234 units, is 2 over the model's line: the model errs wide); F6 and F7 now read apart. Not saved: the workspace fields are the text alone (blockly_pickers.test.ts); layout.ts measures the widest line (layout.test.ts: every row of the box still <= 300) |
| 6 | "Global" still in Before Run, twice: "Its keys are this node's functions (its own first, then Global's)" and "This node's block replaces Global's; a deleted one falls back to Global's, else the default." | name Global only when the project has one; scan every other string | FIXED: both lines and LiveRun's hint for a key that reads none ("this node's, or Global's keys tab"). The scan: the rest name Global only where one exists (an override mark, the Global card, the world rules' own event, the Global node's inspector) or describe the Global node kind in /maps' help |
| 7a | Drink's rank optnum read "the table order (13.6.3)" | learner words, no spec number | FIXED: "the usual order"; its title "which of its class runs first (1 = first)" |
| 7b | Percent presets 5 / 28 / 50 / 73 / 95 | round values in the range | FIXED: `presetsOf` takes, near each of the range's 5 / 25 / 50 / 75 / 95 % points, the roundest value on the field's grid: 10 / 25 / 50 / 75 / 90 for 5..95; 25 / 40 / 50 / 75 / 90 for knife_hp_min's 20..90 (➡️ round 23, 12.7 D2 / D3: the values are enumerated, END_HOT_S's were still 1.5 / 15.25 / 21.5, and the lever's ticks are the presets) |
| 7c | Percent and condition pickers showed a lever AND a plain slider for one value | the lever only | FIXED: the stepper's slider is left out wherever the lever is drawn |
| 7d | END_HOT_S's +/- stepped 0.01 s (2,950 taps for 0.5-30 s) | a coarser nice step (1 % of the range rounded to 1 / 2 / 5 x 10^n, never finer than the field's step); the exact box and presets stay | FIXED: `niceStep` / `buttonStep` (END_HOT_S 0.5 s; 0..3600 50; a whole-number field never under 1) |
| 7e | An incomplete condition said 'col 17: unexpected "end"' | learner words | FIXED: `exprProblem`: "the condition is not finished: a value is missing after >=", "a ( is not closed: add ) after its inputs", 'a text in quotes is not closed: add " at its end', "one comparison at a time: join two with and / or", "… cannot stand here (character n)" (➡️ round 23, 12.7 D4: no character numbers; "after < a value is missing") |
| 7f | The point picker's game picture was a blank grid | the latest stream frame if an existing read-only route serves it cheaply, else the client's fixed areas as outlines; never commit a picture | OUTLINES: no read-only route serves the live stream as an image (the stream is the console's socket; `GET /flows/run/end.png` is a past run's end picture, not the live frame), so the picture outlines and names the client's fixed windows where they usually are -- basic info, hotbar, minimap, chat -- from the UI anchors' home places and sizes (`GAME_AREAS`; pickers.test.ts pins them to packages/poring_env ui_anchors.py). No picture is shown, fetched or kept |
| 7g | The heal: role's list offered all 17 functions, attack_mystcase(t, priority) included | only the functions a role can call: no required inputs, no recipes, no events; a loaded value that does not fit stays, marked | FIXED: roles and "escalate to" list functions with no input lacking a default, not on the monsters tab, no events; the eat role keeps a function of ONE input (the box's events call eat("F6")); a loaded attack_mystcase in heal: stays, ⚠ |
| 8 | A greyed block's picker took the block's slate (rgb 203, 213, 225) with white words, about 1.5:1 | a readable pair (>= 4.5:1) for pickers of greyed blocks, light and dark; a contrast test | FIXED: `pickerColours` darkens any block colour white words read on at under 4.5:1 (the greyed slate and any other), keeping its hue; the block colours are the same in both themes, so one pair serves both. pickers.test.ts: every block style >= 4.5:1 |

**For 5b-2 (feat/hunt-blocks):** `argRow` is unchanged this round (its selects keep their focus
through the picker's `redraw`, outside argRow), so its two new row kinds and `at` merge as they are.

**Not measured here (no browser): the re-measure list.**
- 1: every picker of the reviewer's 9 (390) and 13 (1440) cases, opening on its field's side
  after the scroll, compact where it must, never over its field; the arrow at its field;
- 2: a mouse drag and a touch drag in the point picture at 50, 55 and 60 %;
- 3: ArrowUp / ArrowDown through the condition picker's sensor list and comparison, the focus
  staying in the picker;
- 4: Escape and Cancel after a stepper, the lever, a cell, an optnum, a condition's dropdowns and
  typed text (the value back, Undo greyed if nothing else was done); Done, Enter, a tap outside;
- 5: the eat events' wrapped conditions (two rows in one white box, dark words) and their tooltips;
  the widths at 390;
- 7: the presets, the lever without a slider, the nice step, the plain-word errors, the outlined
  picture, heal:'s list;
- 8: a greyed block's picker in light and dark mode.

### 12.7 Round 23: the reviewer's browser measure of round 22 (written 2026-11-15 00:07 ICT from `date`; branch fix/round23 from f3898e8b; offline only)

The reviewer measured round 22 live on main f3898e8b at 1440 x 900 and 390 x 844. The gaps, each
with the parent's decision and what was done:

| # | Finding (the reviewer's measure) | Decision | Done how |
|---|---|---|---|
| A | The survival tab's event blocks OVERLAPPED: drink / fly_away by 78 px at 390 and 97 at 1440, fly_away / bag_full 131 / 164, bag_full / eat_cane 78 / 96; 8 fields hidden under the next block | after a tab's blocks are drawn, stack its TOP blocks again from their MEASURED heights, a fixed gap apart, in their order and at their x; again whenever a block's height changes; never change the fixtures' saved positions; save positions only when a person moves a block; a test that no two top blocks' boxes intersect -- headless real Blockly if it can give heights, else the width / height model held to the measured heights (say which) | FIXED; the test is the MODEL (node cannot draw Blockly: no SVG layout, so `getHeightWidth` has nothing to measure). ➡️ Round 25 (12.9): the places a person chose are saved with the project and WIN; on open only the unplaced blocks are laid out (left to right), and afterwards only a growth pushes what it reaches. The page: `BlockEditor settle` -- once Blockly has drawn the tab (`finishQueuedRenders`), its top blocks' boxes from `getRelativeToSurfaceXY` + `getHeightWidth`, stacked by `layout.ts stackTops`: the tab just opened, PACKED from its top (90 units), `STACK_GAP` 24 apart; afterwards, whenever a top block's measured height changed (a picker's value, a note, a warning row, a wrapped condition, a block plugged in or taken out: every non-UI event and every decoration settles), a block only ever moves DOWN, as far as the ones above it need. Moves are made with events off: no undo step, no conversion, nothing saved (a project keeps no block positions; the frozen fixtures are untouched); not during a drag (it waits for the gesture's end). Round 20's `restack` (only the blocks under a SETTING that grew) is gone. The first placement (`blocks.ts tabToWorkspace`) now uses `layout.ts blockHeight` (rows, statement inputs with what they hold, wrapped conditions) + 24 instead of the fixed `EVENT_ROWS_Y` (11 x 48 = 528 units, which made drink 710 units apart while it is 840 tall). The model against the reviewer (f3898e8b's placements + the overlaps at scale 0.6 / 0.75 give the heights): drink 858 vs 840 (+2.1 %), fly_away 962 vs 928 (+3.7 %), bag_full 810 vs 793 (+2.1 %); layout.test.ts holds it in [measured, measured x 1.06], proves its own positive case (f3898e8b's steps with the measured heights overlap by the reviewer's pixels, within 1 px at 390 and 1.5 at 1440; this round's are >= 24 units apart), and finds no intersection on any tab of the ready-made projects and the FROZEN ones (project_xmas_dun02.json, stage 2-4, sample, session), the blocks in their order |
| B | The point picker's drag, right at 390, was wrong at 1440: respawn_at's picker opened COMPACT (176 x 99 picture at (702, 505)); a press at 50 % read y 360, moving to 55 % read 719 and stuck (mouse and touch); the focused x box showed 645 while the readout and the block said 128 | fix the mapping in compact mode; keep focused boxes in sync; test both layouts | FIXED in the code, the cause NOT reproduced here (no browser; ➡️ round 24, 12.8: the first drag at 1440 still read 719 -- the cause was the canvas rising under the picker after the press, when the strip lost its IN A RUN lines; the drag is now read against the picture as pressed). Two faults found by reading: (1) the compact CSS set only `max-width: 176px` on a picture whose box kept its 144-px height attribute, and (2) the drag's scroll lock held `.blocklyDropDownContent`, while the compact (capped) picker scrolls in its OWN root -- a drag could scroll that root under the pointer, the picture rising and the reading running to 719 (the likeliest cause). Now the picture's box is 176 x 99 (width and height), a drag holds the nearest scrolling picker root, the svg pieces are not text-selectable, and every place is mapped from the DRAWN picture's own screen box (`getBoundingClientRect` of its background rect, at each move) onto its extent (`pickers.ts toArea`), whatever size, letterboxing or scroll; the lever the same on its bar. A stepper's box follows the value unless the person is TYPING in it (first key to Enter, change or leaving; focus alone no longer freezes it). pickers.test.ts: full 255 x 143 and compact 175 x 98 read the same places (50 / 55 / 90 % -> 360 / 396 / 646; past the edge 719), the lever's middle |
| C | Undo after a cancel was enabled, and Ctrl+Z RE-APPLIED the cancelled value (stepper 3.5 -> 4, percent 50 -> 51, cell 119 -> 120, a condition "< 50" -> "<= 50") | a cancelled session leaves the undo stack exactly as before the picker opened (Undo greyed on a fresh page); a kept session stays ONE undo step; test every kind, Ctrl+Z included | FIXED. The cause: Blockly fires its events on the next animation frame (`requestAnimationFrame` then a timeout), so round 22's clean-up timeout ran BEFORE the session's events reached the undo stack. Now `session.run` (the live preview) records NO undo step (Blockly's `recordUndo` off); `cancel` puts every field back the same way; `commit` (the picker closes any way but Escape / Cancel: Done, Enter, a tap outside, a pick from a list) sets the fields back to their values from before, unrecorded, then forward to the kept values, RECORDED, in a group of its own -- its own because Blockly merges a queued change into the one before it of the same group, block and field and keeps the first one's undo flag (in one group, "back" and "forward" became one unrecorded no-op). blockly_pickers.test.ts, with a browser's frames given to node (16-ms `requestAnimationFrame`): for stepper, percent, cell, point, condition, optnum and reference -- the preview leaves no step, Cancel leaves the stack empty and Ctrl+Z (`ws.undo(false)`) re-applies nothing; a kept session is one group, Ctrl+Z gives back the value from before and redo the kept one, also when everything happens in one frame. Both halves proved by their positive case: a recorded preview fails the first test, a commit in the preview's group the second |
| D1 | A wrapped condition's second row was plain text: tapping it opened nothing | every wrapped row opens the same picker | FIXED: a further line is a `WrapLine` label (`blockly-pickers.ts wrapLineField`) whose editor is the block's TEXT field's (its picker); not saved; cursor pointer. blockly_pickers.test.ts: each row clickable and opening the TEXT field's editor, the saved fields still the text alone |
| D2 | The lever's tick labels were not round (END_FLY_BELOW 5 / 28 / 50 / 73 / 95, REGEN_STOP 10 / 32 / 55 / 77 / 99) | the same round values as the presets | FIXED: the ticks ARE the presets (`presetsOf`), each where it sits on the bar: END_FLY_BELOW 10 / 25 / 50 / 75 / 90, REGEN_STOP 20 / 40 / 50 / 75 / 90 |
| D3 | END_HOT_S's stepper presets read 1.5 / 10 / 15.25 / 21.5 / 30 s | round values (e.g. 1 / 5 / 10 / 20 / 30) | FIXED: `presetsOf` ENUMERATES round values instead of sampling a 0.01 grid (which never hit 15 exactly): near each 5 / 25 / 50 / 75 / 95 % point, the multiple of the largest unit 5 / 2 / 1 x 10^n (and 25 / 250 ...; never 2.5 or 0.25) within a tenth of the range, never within a tenth of the range of the preset before it (two labels that close collide on the lever: the next finer unit, else the point is left out). END_HOT_S 2 / 10 / 15 / 25 / 30 s. pickers.test.ts: every number setting's presets have at most two significant digits, are in range, on the grid and apart |
| D4 | After "< " the message read "and cannot stand here (character 17)" | learner words ("after < a value is missing"); check the parser's other messages for leaks | FIXED: `learnerWords` -- something out of place right after an operator is "after < a value is missing" ("after ( a value is missing before <"); a single `=` "= cannot stand here: to compare two values, use =="; an open [ "a [ is not closed: add ] after its items"; a stray ) "no ( is open before it"; a single-quoted text 'a text goes in double quotes: "like this"'. The leak check found one more: round 22 read `expected "x"` inside `unexpected "x"`, so "x = 3" said "a = is missing here" (fixed). pickers.test.ts: 23 broken conditions, none says a column, a character number, a token or "unexpected" |
| D5 | Two of Blockly's own menus (npc_guard's, quick_drop_scaled's on / off) ran 4-15 px past the canvas's bottom at 390; at 1440 four menus and keys' call-argument picker ran over the footer | keep them inside the blocks area if Blockly allows it cheaply, else note it | FIXED in the code (a browser re-measures). The cause: Blockly's fit check leaves out the 16 px between a field and its menu (`PADDING_Y`). `keepDropDownsInside` watches the DropDownDiv's style (Blockly places it there); once it has slid to its place, a menu past the blocks area moves back inside by at most 12 px (so it never reaches its field) and, for the rest, its content gets shorter and scrolls (`pickers.ts fitDropDown`, pickers.test.ts). Our own pickers are now always capped to the room on their side, not only when compact, so one that grows once open (the suggestions under a typed condition) scrolls inside |

**Superseded in 12.6:** #2's cause (12.7 B: the scroll lock held the wrong element, the compact
picture's box), #4's mechanism (12.7 C: no undo step during the preview; the kept change one step
of its own), 7b's rule and 7e's "cannot stand here (character n)" (12.7 D3, D4). 12.4's and
12.5.5's `restack` is 12.7 A's `settle`.

**For 5b-2 (feat/hunt-blocks):** `argRow` and every export of `pickers.ts` keep their names and
signatures; this round ADDS `toArea`, `fitDropDown`, `learnerWords` (pickers.ts), `blockHeight`,
`stackHeight`, `stackTops`, `overlaps`, `STACK_GAP`, `TopBox` (layout.ts), `wrapLineField` and
`keepDropDownsInside` (blockly-pickers.ts). Internal: `onDrag` takes the session's `run` (and an
optional drawn area) instead of `group`, and `lever` / `condRow` a `run` too -- a 5b-2 caller of
either passes `s.run` where it passed `s.group`.

**Not measured here (no browser): the re-measure list.**
- A: the survival tab at 390 and 1440 -- no two blocks overlap, 24 units apart, after the tab opens
  and after a picker changes a block's height (a condition wrapping onto a new row, a rank set); a
  settings tab whose lint note rows appear; a block dragged meanwhile is not moved under the finger;
- B: respawn_at's point picker COMPACT at 1440 and full at 390: a mouse drag and a touch drag
  from 50 % to 55 % and 90 % (y 360 / 396 / 646), the x and y boxes following, focused or not;
- C: on a fresh page, a stepper, the lever, a cell, a point, a condition, an optnum and a
  reference: change, Escape -> Undo greyed, Ctrl+Z changes nothing; change, Done -> one Ctrl+Z puts
  the old value back, Ctrl+Y the kept one;
- D1: a tap on each row of eat_cane's and eat_candy's wrapped conditions opens the picker;
- D2-D4: the ticks of END_FLY_BELOW and REGEN_STOP, END_HOT_S's presets, the message after "< ";
- D5: npc_guard's and quick_drop_scaled's menus at 390, the four menus and keys' call-argument
  picker at 1440, inside the blocks area (and the arrow still at the field).

### 12.8 Round 24: the point picker's first drag at 1440 (written 2026-11-15 01:03 ICT from `date`; branch fix/round24 from c26d96c0; offline only)

The reviewer re-measured round 23 live on main c26d96c0 (no frontend change since round 23).
A, C and D pass. B was still open at 1440: respawn_at's picker opened COMPACT (the picture
176 x 99 at about (702, 505)). The FIRST drag after it opened, by mouse or by touch, read y 360 at
50 %, then 719 at 55 %, and stayed 719 at 90 %. A second drag in the same picker read 360 / 396 /
648. x was right in every drag, the x and y boxes followed the value, and at 390 both drags were
right.

**The cause: the likeliest one, NOT proven in a browser (none here).** It was found by reading
Blockly 13.3's source and the studio's layout.
- The DropDownDiv lives INSIDE Blockly's injection div. Blockly's `common.getParentContainer`
  defaults to the main workspace's injection div, so a picker moves with the canvas.
- On a wide screen the node strip over the canvas is unfolded. Its **IN A RUN** part came from
  the lint only while the lint was fresh (`lintStale ? null : ...`).
- The first press changes the value. 120 ms later the edit is converted, the project's key
  changes and the lint becomes stale.
- The IN A RUN part (two or three lines on the respawn tab) then left the strip. The canvas, and
  the picker inside it, rose by those lines, and stayed up until a new lint came back.
- Round 23 read the picture's box again at every move. So the moves were read against the risen
  picture: the pointer was below it, and the reading was 719.
- At 390 the strip is folded to ONE line, so nothing rose. A later drag found the strip already
  settled and the picture measured where it then was.
- "Compact" was incidental. It is how respawn_at's picker opens at that place on that screen.
- The other candidates were checked against the source:
  - Blockly's slide is 16 px (`PADDING_Y`, 0.25 s), and keepDropDownsInside's nudge is at most
    12 px. Together they cannot carry 55 % past the picture's bottom, which needs 45 px or more.
  - A scroll of the picker's root was already undone by round 23's hold before each read.
  - Focus at the press: Chrome does not move focus when pointerdown is cancelled, and a touch
    drag never focuses.
- The tests below replay this sequence. Round 23's per-move read reproduces the reviewer's
  numbers exactly: 360 / 719 / 719.

**The fix: four parts.**
1. **The drag is read against the picture AS IT WAS PRESSED** (`blockly-pickers.ts onDrag`).
   - The drawn box, or the screen matrix without one, is read once, at the press.
   - Nothing that moves the picker after the press can change what a move reads: the strip,
     Blockly's slide, the nudge, a scroll.
   - The next press reads the box again.
2. **The strip keeps its height.** While the lint checks an edit, the IN A RUN part keeps the last
   check's words, shown faded (`box.ts boxStripPart`, `data-stale`, studio.css). The canvas, and a
   picker open in it, no longer jump at an edit.
3. **A drag holds both scroll boxes.** It holds the scroll of the picker's root AND of Blockly's
   content box. keepDropDownsInside waits until no drag is in progress, so it never moves a
   picker under a finger.
4. **Focus at open never scrolls** (`focusFirst` uses `preventScroll`).

**The tests:**
- blockly_pickers.test.ts runs the real drag code on a fake picture whose box moves when the
  page does.
  - Test 1, the reviewer's sequence. After the slide, the picture sits at (702, 505), 175 x 98.
    The press is at 50 %. Then the strip's three IN A RUN lines go (56 px). Then the moves at
    55 % and 90 % of where the picture was measured. It reads 360 / 396 / 646, x 640. A second
    drag, measured where the picture now is, reads the same.
  - Test 2. The press lands mid-slide, then the slide's end, the nudge and a root scroll land
    before the first move. It reads 360 / 396, and the root's scroll stays at its press value.
  - Both are proven by their positive case. With round 23's per-move read put back, test 1 reads
    360 / 719 / 719 (the reviewer's numbers) and test 2 reads 425.
- box.test.ts: the part keeps the same words while checking, marked stale.

**Superseded:** 12.7 B said "the likeliest cause" was the scroll lock and the compact picture's
box. Both fixes stay, but they were not this cause.

**Not measured here (no browser): the re-measure list.**
- At 1440, respawn_at's compact picker, opened fresh:
  - the FIRST drag by mouse and by touch reads 360 / 396 / about 648;
  - the strip over the canvas keeps its height after the first change (IN A RUN faded while
    checking, then normal);
  - the canvas does not jump.
- At 390, both drags as before.

**➡️ Re-measured 2026-11-15 01:06-01:11 ICT (matpilot, read only, main d350897c): ALL PASS.**
- **1440, the compact picker opened fresh:** the FIRST drag reads y 360 / 396 / 648 and x 640 / 704 /
  1152, by mouse and by touch. The second drag reads the same, and Escape restores 645,481.
- **The strip:** it stays 152 px tall, and the canvas top stays at 347 through both drags. IN A RUN
  fades to 0.6 while the lint checks and keeps its words.
- **390:** both drags read 360 / 396 / 648; the folded strip stays 36 px.
- **The rank, set by name:** drink's rank goes auto -> 1 (the Python's rank=1), with 0 overlaps and 0
  covered fields on survival.
- **The arc, rounds 20-24, all re-measured in a browser:** every setting block fits at 390, no
  overlaps, every value field a picker, and Escape/Undo exact. Nothing is left open from the
  reviews.

### 12.9 Round 25: remembered positions, left to right (Batt 2026-11-15 ~13:0x ICT; written 2026-11-15 13:32 ICT from `date`; branch fix/round25 from 09d5e6fb; offline only)

Batt's two asks (Thai, translated by the parent, with a screenshot of the monsters tab showing its
four functions side by side):
- (a) "When a tab holds several functions and there is room to the right, lay them out LEFT TO
  RIGHT, as in the monsters tab, so I don't have to scroll and can see which functions the tab
  has."
- (b) "Most important: /flows and /maps must REMEMBER where the user placed blocks. Today they
  don't: after I rearrange and refresh the page, the last positions I dragged to are forgotten."

**(b) Remembered positions (the main item).**
- **Storage:** a tab's optional `layout`, `{key: [x, y]}` in workspace units. The contract is in
  [project-model.md](project-model.md) 2.6.
- **The key: what the project says, never a Blockly id** (an id lives only as long as one
  workspace).
  - `main` is the main tab's start block.
  - `def:<name>` is a function or an event: one namespace per node, and an event's name is its
    key.
  - `var:<name>` is a variable or a setting block (a setting is a variable of the tab).
  - Other top blocks have no key: a loose block is not kept by the project, so there is nothing
    to put its place on.
  - Code: `layout.ts layoutKey`; the engine's pattern is `project.py LAYOUT_KEY`.
  - A rename keeps the place. The editor tracks the PLACED blocks by their workspace ids and
    writes their current names at each conversion.
- **Which blocks have a place: only the ones a PERSON placed.**
  - That is a drag (mouse, touch or the keyboard's move mode, all Blockly's "drag") or "Clean
    up Blocks" (`layout.ts personMoved`), plus the blocks the tab's layout placed when it opened
    (`blocks.ts placedIds`).
  - Blockly's own moves (a bump, a snap, a connection, a new block) and the editor's (settle,
    events off) are not a person's.
  - Undo moves a block back, and the place saved follows at the next conversion. It is undoable
    like the drag itself because it IS the drag's position.
- **Where it is kept: the studio's working copy.** That is this browser's localStorage project
  (`prefs.ts writeProjectText`, written `SAVE_DEBOUNCE_MS` after every change and as the page
  goes; shared by /flows and /maps). So it survives a refresh. It also survives Save, Load and
  GitHub (`exportProject` / `importProject` keep it) and the engine's JSON round trip (`from_json`
  / `to_json`).
- **Outside the run:**
  - The browser sends every project to the engine without it (`project.ts forEngine`): lint,
    simulate, the Python view, Run (`projectRunBody`), the check (`checkBody`). An engine older
    than the field reads them too.
  - The studio's "is this the engine's answer for this project" key is the engine form's
    (`engineKey`). A drag is no new lint, Python view or simulation, and it spends none of the
    20-a-minute lint budget.
  - In the engine, `project_hash` is taken WITHOUT the layouts. `compile_project`, the lint and
    the Python view never read them.
  - The editor's ORDER no longer follows the canvas (`tabFromWorkspace`). Definitions keep the
    project's order (each hat's `order`, the index it was loaded at) and variables the tab's
    order; a block new since then comes after them, in reading order.
    - Before this round a tab's definitions were in top-to-bottom order. Side-by-side columns
      would have reordered the project (and its hash) just by being drawn.
    - This drops the old "move a function up to move it in the Python view". Nothing relied on
      it: no test did.
- **Python → project:** `project.keep_layout(new, old)` keeps the old layout of every block the
  new project still has. `pyproject.parse_files` never sees one. There is no Python → project
  path in the browser today.
- **settle() (round 23) now lets saved places WIN.**
  - When the tab opens, only the blocks no person placed are laid out again with the measured
    sizes (the shelf below), around the placed ones.
  - Afterwards only a GROWTH pushes (`layout.ts pushGrown`). A block that grew taller pushes the
    blocks under its old bottom down its column; one that grew wider (a badge arriving) pushes
    the blocks right of its old edge along its row. Each keeps the gap.
  - A person's own overlapping drop stays where it was dropped, as the reviewer saw on the timing
    tab: it overlapped before, so the growth did not "reach" it.
  - ➡️ This supersedes 12.7 A's "packed from its top on open; afterwards any overlap pushed down".
- **/maps: nothing was lost.** Its map nodes' positions are `Node.pos`, set on every drag stop
  (`MapsCanvas onNodeDragStop` → `moveNodes`) and kept in the same working copy. START is derived
  and not draggable.
  - `pos` stays in the hash as it always was. Taking it out would change every frozen sha256.
  - /maps' change key now leaves out the tabs' layouts too.

**(a) Left to right, for the blocks with no saved place.** This is `layout.ts shelf`, used by
`blocks.ts tabToWorkspace` and the first settle.
- The blocks go left to right, in the tab's order, while they fit the canvas's visible width at
  its scale (`shelfWidth`: the view less Blockly's controls, 72 px). Then they wrap to a new row
  under the row's tallest block, `STACK_GAP` (24) apart both ways.
- A block that would land on a placed one goes down its column under it.
- The start block takes a row of its own (the editor fills in its title).
- Widths leave room for the widest badge (`WIDEST_BADGE`), so a badge arriving with the lint
  widens no block into the next column.
- Every tab: functions, events, setting blocks.
- At 390 px the canvas holds about 313 units, so one 300-unit block a row: a phone stays one
  column. With no width given (headless callers), it is round 23's single list, unchanged.
- The model at 1440 (the canvas beside the Python pane, ~1,028 units):
  - the monsters tab's four recipes (228-235 units each) in ONE row;
  - survival three a row;
  - keys four a row;
  - setting tabs three or four a row.
  - With the Python pane closed (~1,604 units): five or more a row.

**Tests:**
- layout.test.ts (7 new):
  - every key the shelf makes on every tab is one the engine accepts, and the widest badge is
    the widest;
  - the monsters tab: 3+ in its first row at 1440 (4 with the Python pane closed), one column
    at 390;
  - no two top blocks closer than 24 and none past the edge, on every tab of every ready-made
    and FROZEN project, at widths 313 / 600 / 1028 / 1604 / 2400;
  - a remembered place wins, and the others go around it;
  - random positions and any top-block order leave the ENGINE's project unchanged on every tab,
    and with nothing placed there is no layout and the JSON is as before;
  - a rename keeps the place, a later conversion without `placed` keeps the layout's blocks, the
    file round trip keeps it, and Run's and the check's bodies carry none;
  - `pushGrown`: down its column, a cascade, a person's overlapping drop stays, beside stays, a
    shrink moves nothing, a wider block pushes its row.
- blockly_headless.test.ts (1 new, REAL Blockly): a `drag` move is saved and a `bump` is not;
  undo moves the block back and the saved place follows; only drag and cleanup of Blockly's eight
  move reasons count.
- packages/poring_flow/tests/test_project_layout.py (15 new):
  - every fixture with a layout on every tab gives the same `project_hash`, compiled IR, lint
    findings, lint document and Python view;
  - the canonical JSON and the round trip keep the layout;
  - `keep_layout` after a Python round trip, including a function gone;
  - six hostile layouts are refused;
  - `{}` is no layout.
- services/backend/tests/test_settings_blocks.py (4 new): the three frozen arms and the one box,
  with every top block of every tab placed, give TODAY's 97-argument runner argv and the same
  `project_hash` (the fixture files stay byte-identical).

**Deploy note (for the parent).**
- The browser never sends a layout to the engine, so an engine on older code keeps working with
  the new frontend.
- A saved FILE with a layout, read by a Python tool (`flow_play.py`, an A/B plan, the Run helper
  reading its project file), needs poring_flow at this commit: older code refuses the field
  (`extra="forbid"`).

**Not measured here (no browser): the re-measure list.**
1. Drag a function, an event and a setting block. Refresh: each is where it was dropped. Then on
   /maps and back: the same.
2. Drag, then Ctrl+Z: the block goes back, and after a refresh it is where the undo left it.
3. Rename a dragged function: it keeps its place after a refresh.
4. The monsters tab at 1440, with no saved places: its four recipes in one row (the Python pane
   closed or open). keys / survival / a setting tab in rows. At 390: one column.
5. A block that grows (a wrapped condition, a note row, a badge arriving) pushes only the blocks
   under or right of it. A block dropped ONTO another stays where it was dropped (the timing
   tab).
6. A drag is no new lint: the Lint pane and the strip do not say "checking…" after a drag.
7. Save to a file, start over, Load the file: the places come back. The Python view shows no
   layout.
8. Run and Check still start (their project carries no layout; the hash is the same before and
   after a drag).

**➡️ Re-measured 2026-11-15 14:01-14:15 ICT (matpilot, read only, main 95583b9f): all 8 items PASS**
(Save / Load skipped: they write).
- **Remembered:** a dragged function, event and setting come back at exactly their dropped places
  after a refresh and after /maps and back, by mouse at 1440 and by touch at 390.
  - localStorage holds `def:knife_back`, `def:eat_candy` and `var:hud_fast`.
  - Undo is remembered too.
  - A renamed function keeps its place under its new key (`def:knife_off`).
- **The shelf:**
  - monsters shows ONE row of 4 at 1440, with the Python pane open or closed; keys 2 x 4 (6 + 2 with
    the pane closed); the setting tabs 3-4 a row;
  - 390 is one column;
  - 0 overlaps and 0 covered fields on all 14 tabs at both sizes.
- **Growth:** a longer condition and a safety switch off push only the blocks under them in their
  column; a block dropped onto another stays.
- **No new lint on a drag:** 0 POSTs in 3 s, and no "checking...".
- **The Python view:** no layout.
- **/maps:** a dragged node's pos is kept across a refresh at both sizes.
- **Two notes, left as they are** (by design, recorded):
  - after a drag is undone, the block stays "placed" at its old spot (its key is kept), so it does
    not re-shelve at another width;
  - within a row the gaps vary 24-77 units: the shelf aligns column slots.

### 12.10 Round 26: the 5c review (the reviewer, read only, on main 569d03b0 at 1440 and 390; written 2026-11-15 16:47 ICT from `date`; branch fix/round26 from 5f24285f; offline only; s5c-ab was RUNNING, so nothing the runner imports at run time changed its behaviour)

**PASS on 5c:** layout and widths (16 tabs, 0 overlaps, hunt shelved 4/4/1, main ends x 333 / 291),
the role blocks' wording, the step blocks' legibility, the lint words for a left-out or moved step.
The findings, each with the parent's decision and what was done:

| # | Finding | Decision | Done how |
|---|---|---|---|
| 1 | SAFETY and REQUIRED steps were not locked in the editor: Delete removed step_survive, and only the lint refused the run (➡️ round 28, 12.12: only the copy IN ITS PLACE is locked; an extra or a misplaced copy stays deletable and says why) | until Batt answers 15.10 Q1 the editor matches the built default: SAFETY and REQUIRED step blocks cannot be deleted or dragged out of hunt_tick (on load and on creation), with a visible lock and a colour per class; the lint stays the backstop | FIXED. The extension `pl_tick_lock` runs on every step block at init (load and creation). Inside `hunt_tick()` a SAFETY or REQUIRED step: `isDeletable()` is false (the context menu, the Delete key, the trashcan and Cut all ask it), and its drag is a no-op (the tick's drag strategy, a `BlockDragStrategy`: no disconnect, no move, no drop). Out of the tick (a step from the toolbox) it is a normal block, so it can be put in. NOT Blockly's `setMovable(false)`: Blockly's heal keeps an unmovable block under the one deleted ATTACHED, so deleting `loot` would have deleted `after` with it (a test proves it). Visible: a 🔒 on the head row of each locked step; the classes' colours SAFETY red `#b91c1c`, REQUIRED blue `#1e40af`, optional green `#15803d` (theme.ts; white words 4.5:1 or more). The lint rules (tick_step, tick_place) and the runner's own refusal are unchanged |
| 2 | Dragging the OPTIONAL step_loot out took every step under it (9) and gave 6 errors about others | a step's drag moves that ONE step and heals the stack, as Delete does; test with real Blockly | FIXED: the tick's drag strategy (`tickDragOf`, on every step block and, from the editor's paint, every block inside `hunt_tick()`) takes the block out ALONE first (`takeOutAlone`: the blocks under it go up to where it was, whatever they are), then Blockly drags it; one undo step (the Dragger's event group). Tests in real Blockly 13: takeOutAlone leaves the tick whole but loot; Blockly's own pointer drag would take the stack (its `shouldHealStack` is false without Ctrl / Meta); a locked step's drag leaves the tick as it was |
| 3 | The role pickers offered hunt_loop and hunt_tick (the loop itself) | leave out hunt_loop, hunt_tick, any def using hunt primitives, and events; main's plain call picker may list everything | FIXED: a function is the hunt core's own when it is `hunt_loop` / `hunt_tick` or its body (anywhere in it) plays a hunt loop block, a recipe step, a tick step or the old runner block (pickers.ts `playsHunt`); the role pickers (and escalate's) leave those out, events and recipes as before; main's call lists every function |
| 4a | `hunt_tick()` is never called by a visible block | a line on the tick def | ➡️ Round 27 (12.11): the rows did NOT show on the page (filled at init, before a load sets the name); now they follow the name's value. FIXED: a function's own ABOUT rows (blockdefs.ts `DEF_ABOUT_WORDS`, on rows of its own inside the budget, hidden for any other function, in the flyout too): hunt_tick "played by find_target and fight_target, every tick (about 200 ms)" |
| 4b | find_target / fight_target showed ⚠ with "info: find_target is unsupported here: L2 binding L2.input.attack_click (not bound for kro-20211103-prere/lab-rathena (params {}))", twice | an INFO shows no warning triangle; learner words or drop it; once | FIXED: the editor never puts an info into Blockly's warning (always a triangle; the Lint pane lists infos), and each line of a block's warning shows once (api.ts `warningText`). The lint's words for a binding the runner answers: "find_target is played by the runner's own code: nothing to set up for it here" (project.py `lint_doc`; the text and the message alike) |
| 4c | The lint said "xmas_dun02/main/main.2: dungeon_hunt is unsupported here …"; the Hunt category header said "… or runs dungeon_hunt" | in the functions shape name hunt_loop(), never dungeon_hunt where no block shows it | FIXED: on a node whose main calls `hunt_loop()` (the lowered nodes) a finding's words name `hunt_loop()` (project.py `_call_words`; "dungeon_hunt.py" kept); the old one-block shape, whose block shows the runner, keeps its name. The Hunt header: "(the node's main calls hunt_loop(); t: the target, empty until find_target finds one)" |
| 4d | find_target's empty "( )" opened a picker saying "This block takes no inputs" | hide the args row for a block whose catalogue entry takes no inputs | FIXED: a hunt loop block whose catalogue entry takes no inputs hides its inputs' row while it holds none (blockdefs.ts `argsRowShown`; a typed one stays, to be read and taken out) |
| 4e | find_target's "t ▾" picker listed t and every SETTING (fly_rate = 150, ...) | the function's inputs and plain variables only, never settings | FIXED: the variable picker (pickers.ts `variablesOn`) offers the function's inputs and plain variables; a setting or a role block is left out (a loaded one stays, marked ⚠) |
| 4f | `hunt_loop(t=False)` showed t as an input | say "t: the target (starts empty)" or similar | ➡️ Round 27 (12.11): as 4a, it did not show until round 27. FIXED: hunt_loop's ABOUT rows (4a): "t: the target (it starts empty); main calls hunt_loop() with no inputs"; its inputs stay `t=False` (the IR and the Python view unchanged) |
| 4g | "at most 120 s" / "at most 300 s" had no counterpart in the Python (they are defaults) | show the default as a comment, or another way that keeps the round trip byte-identical; my call, and why | A COMMENT: a hunt loop block at its default time box ends its line with `# at most 120 s` (pyview.py `HUNT_BOX_BLOCKS`). Why: a comment is never read back (the parser reads the code), so `parse_files(print_files(p)) == p` and printing again gives the same text, byte for byte; printing `timeout_s=120` would have been code a learner thinks they must write, and every other block prints only a time box that is not its default. A non-default one is still `timeout_s=N` |
| 5 | Batt's Q2, the safe default until he answers | keep the old runner block for old projects, in Advanced, labelled "the old one-block runner (old projects)", so a learner starting fresh sees hunt_loop() first in main's toolbox | DONE: Advanced > "Old projects" holds it under "the old one-block runner (old projects; a new box calls hunt_loop() in its main):"; Movement in a map's main offers `hunt_loop()` and no longer the runner block. A project holding the block loads and runs as before |

**Tests:**
- tick_lock.test.ts (8 new, REAL Blockly 13 where it needs it):
  - a locked step is not deletable in the tick, an optional one is, and any is out of it;
  - deleting `loot` heals the tick and keeps `after`. The positive case: with `setMovable(false)`
    Blockly would have deleted `after` with it;
  - takeOutAlone; a locked drag is a no-op; Blockly's default pointer drag takes the stack;
  - the padlock and the three colours;
  - the ABOUT rows (both functions, renamed: gone; inside the budget);
  - the role pickers leave out hunt_loop, hunt_tick, a function playing find_target and the
    events, while main's call lists them;
  - argsRowShown and warningText;
  - the old runner in Advanced > Old projects, and no "dungeon_hunt" in the Hunt header.
- pickers.test.ts: the variable picker offers no setting and does offer a plain variable; pl_def's
  fields (its ABOUT labels).
- packages/poring_flow/tests/test_runner_functions.py (1 new), with the L2 resolver:
  - every answered binding is an info in learner words (no "L2", "binding", "unsupported");
  - the functions box names `hunt_loop()` and never "dungeon_hunt";
  - each finding once;
  - the old shape keeps "dungeon_hunt".
- test_hunt_loop.py: the hunt tab's Python view carries the time-box comments, the round trip is
  byte-identical, and pyview's names are huntloop.NEW_BLOCKS.

**Deploy:** project.py (lint_doc's words) and pyview.py (the comments) are imported by the runner's
process; this round changes no runner behaviour (prepare, the IR, the hash, the argv untouched), but
merge after s5c-ab as the parent said.

**Not measured here (no browser): the re-measure list.**
1. Tab tick: Delete / Backspace / the context menu / the trashcan / Cut on a SAFETY or REQUIRED
   step: refused. Dragging one: it does not move. The 🔒 on each, and the three colours.
2. Drag step_loot out: it comes ALONE, the steps under it close up, and the lint shows no error
   about the others. Ctrl+Z puts it back.
3. A step block from the toolbox can be dropped into the tick, and is locked there.
4. Tab hunt: no role picker lists hunt_loop, hunt_tick or an event. main's call picker lists every
   function.
5. The ABOUT rows on hunt_tick and hunt_loop, at 390 and 1440.
6. find_target / fight_target: no ⚠. The Lint pane says "find_target is played by the runner's own
   code: nothing to set up for it here", once. main.2 names hunt_loop().
7. find_target shows no "( )" row. Its "t ▾" lists t and no setting.
8. The Python view's `# at most 120 s` / `# at most 300 s`.
9. main's toolbox: hunt_loop() in Movement, and the old runner only in Advanced > Old projects.

### 12.11 Round 27: two gaps from the round-26 re-measure (the reviewer, live on main e41964b1; written 2026-11-15 18:36 ICT from `date`; branch fix/round27 from e41964b1; offline only)

**PASS on 7 of 9** of 12.10's re-measure:
- the locks: Delete, Backspace, Ctrl+X, a drag and the trashcan are all refused, and the
  context menu has no Delete, Cut or Duplicate; the 🔒 and the colours show;
- step_loot drags alone, with no lint lines, and Ctrl+Z restores it;
- the role pickers: 12 functions, no loop, no events;
- no ⚠, and the learner lint words show once;
- find_target has no "( )";
- the Python comments;
- the toolbox: the old runner only under Advanced > Old projects;
- 0 overlaps on all 16 tabs.

**1. No step block in any toolbox.** The reviewer checked every category on main, hunt and tick.
Searching "survive" gave "No block matches", so a deleted OPTIONAL step came back only by Undo or
Start over.
- **The cause:** the catalogue marks the 20 step blocks CORE (`core.tick_step`). BlockEditor's
  toolbox kept, of the core blocks, only `CORE_OFFERED` (the save point, use_model, wait_steal,
  wait_kill), so it dropped all 20. The Tick category is built only when every step is in the
  toolbox's catalogue, so it was never built, and the search, which reads the same toolbox, found
  nothing.
  - 5c's own toolbox test passed because it handed `toolbox()` a catalogue with the steps in it,
    past the page's filter.
  - Round 26's change did not drop it, and the tab name (`tick`) was right.
- **The fix:**
  - `CORE_OFFERED` gains the 20 step blocks.
  - The page's filter is now `blockdefs.ts toolboxCatalogue`, the one function the page and the
    tests use.
  - The category is named **"Tick steps"** (`TICK_CATEGORY`): hunt_tick() and the 20 steps, by
    class.
  - The search finds them by name and by their words. It reads a block's `toString()`, so
    "survive" and "potion" find step_survive and "loot" finds step_loot.
  - A step dropped in the tick is locked there if it is SAFETY or REQUIRED (round 26; free in the
    flyout and outside the tick).
  - A step dropped in the wrong place: the lint now says WHERE it goes. Its `tick_step` words read
    "step_loot() is out of its place in hunt_tick(): it goes after step_hold() and before
    step_after()".
    - It names the step outside the longest run already in order, not the first step after it.
    - This changes `poring_flow.tick`'s words only. No series was running.

**2. The ABOUT rows did not show, at either size.**
- **The cause:** the extension filled them at the block's INIT, and on a BLOCK_CHANGE event.
  - When a workspace or the flyout LOADS a block, Blockly creates it first (its NAME still the
    default "my_function"), then sets its fields.
  - The editor loads with events OFF, so no change event ever came, and the rows stayed empty.
  - Round 26's test called the sync itself after appending the block, so it passed.
- **The fix:**
  - The rows follow the NAME field's VALUE through its validator (`watchDefAbout`). Blockly calls
    it on every set of the value, the load's included.
  - The tooltip is no longer the generic one. hunt_tick's and hunt_loop's carry their ABOUT words
    (`defTooltip`).
  - Every function's tooltip, and a variable's (`varTooltip`), names Global only in a project that
    has one. The editor's paint sets them; the static one names no Global.
- 12.10's 4a and 4f carry a pointer here.

**Tests:**
- tick_lock.test.ts (4 new):
  - the tab tick's "Tick steps" category holds hunt_tick() and the 20 steps, through
    `toolboxCatalogue` with the engine's kinds. The positive case: round 26's filter leaves no
    category;
  - the flyout's 20 step blocks as Blockly builds them: found by "survive", "potion" and "loot",
    and free (deletable) until they are inside the tick;
  - the ABOUT rows and tooltips on the page's own path: a tab LOADED with events off, for
    hunt_tick and hunt_loop, and the toolbox's def. The positive case: with round 26's sync (at
    init only) the test fails with "hunt_tick on load", the reviewer's finding;
  - the Global-conditional tooltips.
- functions.test.ts: the category's new name.
- packages/poring_flow/tests/test_runner_functions.py (2 new cases): a step dropped at the end, or
  first, is named with where it goes.

**Not measured here (no browser): the re-measure list.**
1. Tab tick: the toolbox has "Tick steps" with hunt_tick() and the 20 steps.
   - Searching "survive", "loot" or "potion" finds them.
   - Delete step_loot, then drag it back from "Tick steps" between step_hold and step_after: the
     lint is clean.
   - Dropped elsewhere, the lint says where it goes.
   - A SAFETY step dropped in the tick is locked there.
2. hunt_tick shows "played by find_target and fight_target, every tick (about 200 ms)" and
   hunt_loop "t: the target (it starts empty); main calls hunt_loop() with no inputs", at 390 and
   1440. Their tooltips carry those words.
3. A function's tooltip in a project without Global names no Global.

### 12.12 Round 28: a locked extra copy, and "run()" (the reviewer, live on main 5c229faf; written 2026-11-15 18:56 ICT from `date`; branch fix/round28 from 5c229faf; offline only)

**PASS: all 3 of 12.11's re-measure.** Tick steps lists and searches; loot goes back with a clean
lint; the misplaced-step words say where it goes; the ABOUT rows and tooltips show; no Global.

**1. The trap: a SECOND copy of a SAFETY step became LOCKED inside the tick.** step_survive was
dropped from the toolbox after step_pace. The lint said "step_survive() twice in hunt_tick(): each
step plays once a tick", but the learner could not delete the copy; only Ctrl+Z worked.
- **The cause:** round 26 locked EVERY SAFETY or REQUIRED step inside hunt_tick(), whatever its
  place.
- **The decision:** lock only the copy that stands in its right place in the runner's order (the
  one the lint accepts). An extra copy, or a misplaced copy, stays deletable and draggable, and
  its rows say why. The editor and the lint must never disagree.
- **The fix: one rule, written twice and pinned by the same cases.** It is `poring_flow.tick
  places` for the lint and `lib/flow/tick.ts tickPlaces` for the editor.
  - The accepted copies are the longest run of steps already in the runner's order, with at most
    one copy of a step. Where two copies would do, the earlier one is accepted.
  - Any other copy of an accepted step is an EXTRA copy. Lint: "step_survive() twice in
    hunt_tick(): an extra copy: delete it (each step plays once a tick)".
  - A step with no copy in its place is OUT OF ITS PLACE (its first copy; any other copies are
    extra). Lint: "... it goes after X() and before Y()".
  - Round 27's lint called the FIRST copy the real one, so a copy dropped at the top made the
    original the "twice". Now the copy in its place is the real one wherever the others are.
- **In the editor:**
  - `lockedStep` locks only an accepted SAFETY or REQUIRED step. Its place is read fresh from the
    tick's statements on every ask (`stepPlace`), so a drop, a delete or an undo is followed at
    once.
  - On an extra or a misplaced copy (`syncStepPlace`, from the paint):
    - the padlock is a label of its own (`LOCK`), emptied on a copy the editor does not lock;
    - its new WHY rows (hidden while empty) say "an extra copy: delete it (each step plays once a
      tick)" or "out of its place: it goes after X() and before Y()".

**2. Wording: "run()" is a name no block shows.** It now says "the runner's order" in:
- the lint's tick words (holds / stands only / out of its place);
- the hunt_tick tooltip;
- the Tick steps label;
- the step blocks' tooltip.

The tests check that the misplaced words no longer say "run()".

**Tests:**
- tick_lock.test.ts (3 new, real Blockly on the page's load path: a tab loaded with events off):
  - the shared cases (`PLACE_CASES`) through `tickPlaces`, and the words;
  - a second step_survive dropped after step_pace, made from the toolbox item: deletable, with no
    padlock and its WHY row; the original stays locked; deleting the copy gives the 20 steps
    again, every place "ok";
  - a misplaced only copy: not locked, says where it goes; moved back, it locks.
  - Round 26's padlock test now reads the LOCK label.
- test_runner_functions.py (the same 9 cases through `places`, and 1 new test): the extra copy's
  words; a tick without it gives no tick_step finding; the misplaced words name the runner's order
  and never run().

**Not measured here (no browser): the re-measure list.**
1. Tab tick: drop a second step_survive after step_pace.
   - It shows no 🔒, and its rows say "an extra copy: delete it".
   - It is deletable (Delete, the trashcan) and draggable.
   - The original keeps its 🔒 and stays locked.
   - Delete the copy: the lint is clean.
2. Drag the only step_survive below step_pace: no 🔒, and "out of its place: it goes after
   step_battle_log() and before step_engage()". Move it back: it locks.
3. The words read "the runner's order", never "run()": the lint, the hunt_tick tooltip, the Tick
   steps label.

**➡️ Re-measured 2026-11-15 19:02-19:12 ICT (matpilot, read only, main bd9329ca, 1440):**
- **Item 1 PASS:**
  - an extra step_survive shows no 🔒 and reads "an extra copy: delete it";
  - it can be dragged out and deleted, and the lint is back to 0 errors;
  - the original keeps its 🔒.
- **Item 3 PASS:** "the runner's order" in the lint, the tooltip and the Tick steps label; no "run()".
- **Item 2 cannot be reached in the editor.** Every in-place SAFETY / REQUIRED step is locked, so the
  only survive cannot be moved out of its place. The same "out of its place: it goes after ... and
  before ..." words were checked on an OPTIONAL step (step_loot dropped before step_sense).
- **OPEN, small (not fixed):** a step copy dragged LOOSE onto the workspace, outside hunt_tick, shows
  its 🔒 again while it still reads "an extra copy: delete it". Delete still removes it, so the
  padlock only misleads there. The next frontend round takes it: a step outside hunt_tick shows no
  padlock.

### 12.13 Round 29: Batt's decisions 17 #1, #2 and #7 (written 2026-11-16 10:5x ICT from `date`; branch fix/round29 from f4342ed9, fast-forwarded to main 1f260bd7 (docs only) before its commit; offline only, while s5c-ab2 ran from main)

**1. Every step can be edited (17 #1; 15.10 Q1 answered).** Round 26's editor lock is gone.
- SAFETY and REQUIRED steps delete (context menu, Delete, the trashcan, Cut) and drag like any
  block. `isDeletable` is Blockly's own again, and the tick's drag strategy no longer freezes a
  step.
- The drag still takes ONE step out (`takeOutAlone`; the steps under it close up), as round 26
  built for the optional steps. No block is ever made `setMovable(false)`.
- The 🔒 is gone. It no longer stood for anything, and on a loose copy it misled (12.12's open
  item). Each needed step's first line now reads "SAFETY · needed to run" (or "REQUIRED · needed
  to run") in the class colours. That is true of the step wherever a copy of it stands.
  - It is not on the head row because there it ran to 349 of the 300-unit budget
    (step_battle_log).
- The Run is held, not the edit. A tick without a SAFETY or REQUIRED step is refused:
  - by the lint, in its words: "hunt_tick() leaves out step_survive(), a SAFETY step (...):
    without it ...";
  - by live.problems (not_live), in the same words (`test_the_tick_refuses_each_unsafe_edit_in_words`);
  - by POST /flows/run/project (`lint_errors`).
  The page's Run button shows that reason (round 21's hold). Batt: "if it cannot run, just Undo
  or load the saved file".
- Round 28's ONE rule for extra and misplaced copies (`tick.places` = `tickPlaces`) stays, as do
  its WHY rows. It now decides only the words, never a lock.

**2. The old one-block runner is no real run (17 #2; 15.10 Q2 answered).** A project whose map node
holds the old runner block (a `dungeon_hunt` action in any of its tabs, i.e. NOT a lowered
`hunt_loop()`) is refused on the PRODUCT Run path, in the engine's words
(`poring_flow.project.OLD_RUNNER_WORDS`): "this box uses the old one-block runner; real runs use
hunt_loop() (load xmas_dun02)".
- **The lint:** a `readiness` finding `old_runner` at the block. It is not an error: the old box
  stays a valid design that loads and simulates. A readiness finding refuses the run start
  (`run_start_refused`).
- **The check and the Run:** POST /flows/run/check and /flows/run/project refuse
  `old_runner` (400) before anything is written.
- **The Run helper:** `flow_run.old_runner_problem`. A start of such a checked file is "refused
  before any input: ...", even with the right hash.
- **The pages:** the Run button on /flows (ProjectStudio) and /maps is held with the same words
  (`lib/flow/project.ts oldRunnerOn` / `OLD_RUNNER_WORDS`).
- **The block stays loadable** under Advanced > Old projects (round 26), as `xmas_dun02_runner`.
- **Which ready-made boxes this holds:** every one whose main still calls the runner block:
  - xmas_dun02_runner;
  - xmas_dun02_hunt (14: its hunt tab plays as blocks, but main is the runner block);
  - the one-box xmas_dun02_cookie_noswap file (16: stage6_ab's arm C; ➡️ off the Load lists since
    its functions twin, below);
  - the stage 2-4 and session fixtures.

  The listed ones' Load-list words now say "it loads and simulates, but Run is held". Only
  xmas_dun02 (the functions box) and boxes built like it run.
  - ➡️ **The no-swap example's twin is BUILT (the parent's follow-up, 2026-11-16; Batt 14.12 #2
    "make it work", 16.8 "an example, not the default"):**
    - `fixtures/project_xmas_dun02_functions_cookie_noswap.json` = `xmasFunctionsCookieNoSwapProject()`.
      It is the functions box with attack_cookie and attack_cookie_xmas cut to strike(t);
      wait_kill(t); loot(t), 16.1's very recipes. Everything else is the functions box byte for
      byte (`stage6_ab.box_difference(functions, twin)` is None).
    - It replaces the old entry on both Load lists, under the same title,
      xmas_dun02_cookie_noswap. Its words say "an EXAMPLE of a recipe edit, not the default".
    - Its Run is not held: there is no old runner block.
    - The one-box file stays for stage6_ab's arm C (its sha256 pins), off the lists.
    - Tests:
      - test_cookie_noswap.py: prepare gives the functions box's argv and run() arguments but
        box_recipes for the two cookies; lint without errors or readiness items, its rules the
        functions box's; not_live none; the same keys.
      - project.test.ts: the fixture equals the TS twin; the twin is the functions box but the
        two recipes; every tab round-trips.
      - blockly_headless.test.ts: every tab through real Blockly.
      - layout.test.ts: no overlap, at 390 to 2400.
      - tick_lock.test.ts: oldRunnerOn is false.
- **Reading (the parent's, 17 #2):** the stage A/B tools (`scripts/stage*_ab.py`) launch
  `flow_play.py play` directly with their REFERENCE arms (e.g. 15.13's arm A, the runner block).
  Those are tests of the new shape against the old, not real runs, so they stay allowed.
  `flow_play.py`'s own play refusal (`live.problems`) is unchanged: the rule lives on the product
  path only.

**3. Every run records its economy (17 #7).** It is `econ_db.record_after_run`, called from:
- the Run helper, at each project run's end (`flow_run.Helper.record`);
- the A/B series, after each run (`stage2_ab.Series.econ`, so stage3/4/5/5b/5b2/5c/6 too).

The details are in [econ/economics.md](../econ/economics.md) section 10, "When a run is recorded":
- the sessions by label: `*-<label>` and `*-<label>-hunt<n>`, never `-play-`;
- `econ_db.py update`, niced, under a 900 s cap; a session already in the file is skipped;
- the wait: a series waits at most 60 s, the helper 5 s (under the backend's 10 s helper
  freshness); past that the record goes on in the background and its end is noted;
- non-fatal: the outcome is a series.log line and done.json's `econ`, or a runs.jsonl `econ` /
  `econ_end` row. The run's result never changes.

The 11-14 / 11-15 runs are back-filled by the parent separately (17.1), not here.

**Tests:**
- Python:
  - test_routes_flowrun.py (2 new): the old box refused on the project run and the check, nothing
    written, the functions shape running, the lint's one readiness finding at field/main/main.1;
    a tick without step_survive refused by the Run in the lint's words.
  - test_live_player.py: the helper refuses an old-shape start in words, then starts the functions
    shape. `functions_shape()` turns a test project's runner block into hunt_loop() + role blocks
    + the box's own hunt_loop def; the route tests' real runs use it.
  - test_econ_db.py (5 new, synthetic sessions as its own tests):
    - done, idempotent, none;
    - failed is reported, never raised;
    - the background record and its reap;
    - sessions found by label, `-play-` never;
    - the helper's and the series' hooks are non-fatal, and the helper waits under the freshness.
- Frontend (tick_lock.test.ts, real Blockly on the page's load path):
  - every step deletable and movable, in the tick and out;
  - a SAFETY step deleted converts (the design is kept), and Undo puts it back;
  - a SAFETY step comes out alone;
  - each class's mark and colour, with no padlock label;
  - round 28's extra / misplaced copies are deletable and say why.

**For the re-measure (no browser here):**
1. Tab tick: delete step_survive (and drag step_pace out). Both go; the steps close up. The lint
   says "leaves out step_survive(), a SAFETY step ...", and Run is held with that reason. Ctrl+Z
   puts it back and Run is ready again.
2. No 🔒 anywhere. SAFETY and REQUIRED steps read "· needed to run" in red / blue; optional steps
   are green. A step copy dragged loose shows no padlock (12.12's open item).
3. Load xmas_dun02_runner (Advanced > Old projects). It loads and simulates. Run (on /flows and
   /maps) is held: "this box uses the old one-block runner; real runs use hunt_loop() (load
   xmas_dun02)".
4. After the next live run: `econ_db.py list` shows its session(s), and runs.jsonl / series.log
   says "economy record done".

## 13. Stage 5b-1: HuntState and the loop as steps (design written 2026-11-14 18:3x ICT from `date`, before any 5b code; offline only)

**Batt's words:** "break the runner into blocks" (2026-11-13); "there should be no runner [page]
... everything in the xmas_dun02 flow, as tabs ... make them ALL blocks" (2026-11-14); on 5b: "go
on, no need to ask me again" (2026-11-14 18:1x). **The parent's standing rule:** a block that does
nothing when it is edited is worse than no block, so the loop's description blocks move into the
map's tabs only once each one really plays (5b-2).

**What 5b-1 is.** `dungeon_hunt.run()` (main eb160ee1: lines 6212-10605, the loop 9304-10423, 85
top-level statements in the loop body, ~100 closures) keeps the hunt's state in its local
variables, shared with the closures through `nonlocal`; the loop is one block of code, so nothing
outside run() can play a part of it. 5b-1 changes NO behaviour: the same decisions, inputs and
records for the same frames. It only moves the state onto one object and cuts the loop's body
into named steps, so 5b-2 can let the block player call the steps. `dungeon_hunt.py run ...`, the
old Run path and flow_play's `run(a, hook=..., session=..., box_plays=..., box_roles=...,
box_model=..., box_recipes=..., box_eat=...)` stay exactly as they are.

### 13.1 HuntState: what moves into one object

The rule is mechanical, so a reviewer can re-derive it (13.3):
- **REBOUND state** = every run()-scope variable that is bound before the loop AND again inside it
  (or after it), or that a closure declares `nonlocal`: 48 names, plus `bare` (bound twice in the
  setup: None, then the bare-steal controller). Each becomes an attribute: written `hs.<name>`
  everywhere in run() (`hs = HuntState()` is run()'s first statement); the closures' `nonlocal`
  declarations of them go.
- **IN-PLACE state** = the containers the loop mutates but never rebinds (each bound exactly once):
  49 of them. Each is created ON the object and keeps its old local name as an ALIAS of the same
  object (`counts = hs.counts = Counter()`), so no use of it changes.
- **Not moved:** the tick's own reads (`tick`, the frame `img`, `pct`, `frac`, the Battle Log's
  `new` lines, `boss_hit`, `near_`, `calm`, ...: each tick makes them again; they stay run()'s
  locals, which the steps reach through `nonlocal`); the setup's configuration and resources (the
  map grids, the templates, the Agent and Screen, the box watcher, every refusal's value); three
  names a tick reuses as temporaries (`why_bx`, `why_hk`, `cmd`).

| Group | REBOUND (`hs.<name>`) | IN PLACE (alias) |
|---|---|---|
| the mode, the target, the end | mode, lock, reason, sitting, fight_ref, fight_t0, qscan_i, watch_i, bare (the bare-steal controller) | box_fight, box_sp, queue, n_strike, n_shots, n_box_target, last_strike, steal_done, false_rel |
| the walk | goal_path, walk_from, stall, noentry_n, last_uncarve, idle_pos, idle_since, last_walk, last_walk_click | walk_st, wp_st, ex_st, stalls_here, carved, last_click_t, plant_last |
| odometry | here, last_pos_t, pos_flies, n_reads | pos_ok, pos_hist, own_moves, frame_meta, ust |
| the fight's clocks, the battle log | last_taken, last_ours, ours_used, last_swing, swing_floor, seen_lines, exp_seen, exp_pair, ua_marks, ua_drop_t | ours_ticks, kills_seen, ua_locks, ua_walks |
| loot (the list, the budgets, the recheck, the memory) | loot_list, loot_settle_t | loot_used, loot_picked, empty_cells, rk_pending, rk_st, lm_kills, lm_mem, lm_st |
| survival and safety | fly_at, boss_until, boss_grace_until, ag_last, ag_absent | st (Sustain), escaped, last_quick, boss_walks, box_stop, box_pressed, bq_st |
| the UI watch, the weight, the stock, caches | last_ui, w_share, red_seen, rest_since, rest_skip_t | stock_due, stock_tries, reach_cache, reach_logged, reach_pick, reach_proj, spot_logged |
| the house rest | hplan, house_fb, house_tries, house_click_t, gap_since | trip |
| the counters | | counts |

`class HuntState` (scripts/dungeon_hunt.py, before run()) has `__slots__` = exactly these 98 names
(a misspelt attribute is an AttributeError, never a silent new field), each with its type and the
comment its local had. Why an object and not the closures' cells: 5b-2's blocks hand back on the
mode and the target (13.4), the hook's HuntTick can be read from it, and a later stage can move a
step out of run() and test it with a constructed state. The one-item lists (`escaped = [False]`,
`n_strike = [0]`, ...) were the closures' way around `nonlocal`; 5b-1 keeps them as they are (an
alias each); turning them into plain attributes is a later, separate rewrite.

### 13.2 The steps: run() becomes a driver

The loop's 85 statements are cut, in order, into 20 consecutive SECTIONS; each becomes a closure
`step_<name>() -> str | None`, defined just before the loop at the loop body's own indentation (so
its text, comments and line breaks stay as they are). A step returns None (the next step runs),
`TICK_DONE` (where the loop said `continue`: the rest of this tick is skipped) or `RUN_END` (where
it said `break`: the loop ends, `hs.reason` says why, and the normal end follows unchanged). The
loop becomes the driver:

    hunt_steps = (("begin", step_begin), ("sense", step_sense), ..., ("pace", step_pace))
    def hunt_tick() -> str | None:            # one tick: the steps in order, to the first signal
        for _name, step_ in hunt_steps:
            sig_ = step_()
            if sig_ is not None:
                return sig_
        return None
    while time.monotonic() < t_end:
        if hunt_tick() == RUN_END:
            break

| Step | What it does (today's code, unchanged) | Can end the tick / the run |
|---|---|---|
| begin | the tick's clock; the Run's Stop file; a stop the box asked for inside an action; a Fly Wing inside an action (guard_tick) resets the target and loot | RUN_END |
| sense | the frame; HP and SP; the stock re-reads after a press; the Miss cue; Auto Guard's icon; dead; the position (fresh after a Fly Wing, PosConfirm, late confirm, the jump bar); the hp_read record | RUN_END (stock out / kept, a jump) |
| hook | the live player's tick hook (stage 1) | RUN_END (its stop) |
| vitals | death; the house rest's unexpected load | RUN_END |
| battle_log | the Battle Log's new lines: the boss line, hits taken and dealt, the exp kills, the loot list, the recheck / memory kills | RUN_END (its reader died) |
| survive | the stand-up on damage; calm; the box's survival events (stage 2) and their Fly Wing's after-steps; the runner's sustain (the potion, the Fly Wings, heal); Auto Guard | RUN_END (the box's end) |
| engage | the fight signs (hit, HP drop, Miss, a box near); the Garm Baby alarm; the boss guard (walk away or fly); the engage record and mode "fight" | TICK_DONE (a walk away, a fly) |
| ui | the UI watch every UI_EVERY_S; the weight; the box's weight event (stage 3); the weight home | RUN_END |
| upkeep | overweight; the idle clock; the recheck and memory ageing; the HUD; the bare-steal controller's tick | - |
| fight | mode "fight": the lock's kill read (exp line, kill gap), unlock, the unreach escape, quick drop, the quiet kill's end, melee-ring scan and queue, the box strike, the defend box, the ring scan, the fight's end | TICK_DONE (always) |
| hold | a lock without a fight waits; the loot recheck; the loot memory | TICK_DONE |
| loot | mode "after": the queue cleared; the loot step | TICK_DONE (a fight began) |
| after | the queue pick due; the stand-up when overweight; the rest decision; "after" becomes "search" | - |
| ready | --bare-ready's idle swap; --queue's next target | TICK_DONE |
| rest | mode "rest": sitting, the house rest, the walk to a rest spot | TICK_DONE |
| idle | the idle watchdog (uncarve, or a Fly Wing) | TICK_DONE |
| plant | the White Plant sweep | TICK_DONE |
| search | the goal (heading, patrol, explore), the walk click (pick, dodge, trust, stall, carve), the walk-sword engage; melee-ring's forward watch | TICK_DONE (a stall's fly or scan) |
| position | the unread position's Fly Wing; 30 s unread | RUN_END |
| pace | the sleep to READ_HZ | - |

Why the steps keep the tick's reads as `nonlocal`: a section's text then stays byte for byte as
it was, and no step has a local of its own (checked), so every name means what it meant. Why the
loot / after cut sits where it does: 5b-2's loot(t) must be able to be LEFT OUT of a recipe, so
the loot step is its own step, apart from the rest decision that always runs (13.4).
`HUNT_STEPS_VERSION` = "9.54" names 5b-1 (in runner_flow_export.NOT_FEATURES: no feature of its
own; recorded nowhere: the records stay exactly as they were).

### 13.3 How the equivalence is shown

**Offline, proven** (scripts/huntstate_check.py, committed with the refactor):
- `huntstate_check.py check [--base eb160ee1]` takes the BASE's run() (git show), applies the three
  rewrites as AST transforms -- LIFT (13.1's rebound names -> `hs.<name>`), ALIAS (the containers),
  OUTLINE's inverse on the committed file (the steps' bodies back into the loop, in the driver's
  order, `return TICK_DONE` -> continue, `return RUN_END` -> break) -- and compares the two run()s
  as ASTs (formatting, comments and docstrings aside). Equal ASTs = the same program on every
  path, not only the paths a test reaches.
- The rewrites' preconditions, each checked on the base and printed: no exec / eval / locals / vars
  / globals in run(); no `except NameError` (an unset attribute raises AttributeError where an
  unbound local raised NameError: the same only if nothing catches the difference); no lifted name
  deleted or bound by import / def / class / except; the name `hs` unused; an alias bound exactly
  once; no step binds a name of its own (every bound name `nonlocal`); no loop-level return / yield
  / await; no `else:` on the loop; `HuntState.__slots__` == the lifted + aliased names; every
  top-level statement outside run() unchanged but the class and three constants.
- The scope resolver (which `here` is run()'s and which a closure's own) is cross-checked against
  CPython's `symtable` twice: every table's locals, and, independently of the resolver's own chain
  walk, every Name of a lifted name.
- The rewrite rules are tested BY EXECUTION on small programs that have each hazard (a closure's
  nonlocal, a shadowing parameter, a default argument, a comprehension, an except-as, a
  continue / break in a nested loop, try / finally around a continue, a for-else): the original
  and the rewritten function run on the same inputs and must give the same outputs and traces;
  and the checker is shown a deliberate wrong rewrite of each kind and must name it (a verifier
  proves a positive case).
- The whole Python suite stays green at every commit called green.

**The tests that read run()'s source** (many slice the file's text and assert code fragments):
each fragment is re-written the same way the code was -- its occurrences in the base mapped
through the same text edits -- so the test asserts the same fact on the new text; a fragment whose
occurrences map to different texts, or that formatting broke, is changed by hand. Every changed
test is listed in the 5b-1 report.

**Not built: a scripted fake environment that drives the WHOLE run().** run()'s setup reads the map
grid (GAT), the KB, nine template sets, the slot icons and the minimap references (client-derived:
present on this host at run time, never in git), opens the session, runs the start check, a Battle
Log reader process, the box watcher and the item model's client; a fake world plausible enough to
reach the loop would stub ~30 modules and would mostly test its stubs, on the few paths it
scripts. The AST identity covers every path; the rule tests cover the semantics of each rewrite.
What neither can see is what only a live run shows:
- the cost of the driver (20 function calls a tick, attribute access instead of locals: tens of
  microseconds against a 200-ms tick);
- the real I/O interleaving (the Battle Log process, the box watcher's thread, the detect server);
- the A/B's own launcher (13.5).
The live A/B (13.5) is the check of those.

### 13.4 5b-2 (designed, NOT built): the steps as live blocks

➡️ **BUILT 2026-11-14 (section 14, feat/hunt-blocks; offline only), with 12 refinements (14.2)
that SUPERSEDE parts of this design: `explore()` is `find_target()` and `attack(t)` is `fight_target(t)`
(#1), the loop is `def hunt_loop(t)` (#2), a block hands back only before the fight or the after
step (#3), guarded steps are called whoever plays (#4), the ownership table below (#5: find_target
owns hold too; loot owns fight, hold and loot), the exits (#6), loot's time box (#7), the recipe
chosen at the lock (#8), use_skill's key (#9). Read 14 first; this section is the design as
written.**

**The tick cursor.** The hunt core keeps a cursor: the current tick and the next step in
hunt_steps. Each primitive block ADVANCES the cursor -- runs steps in order, a new tick after
`pace` (or at a TICK_DONE) -- until ITS exit condition holds at a step boundary, then hands back to
the block program; the next primitive resumes the cursor where it stopped. Two kinds of step:
- COMMON steps run in every tick whichever block is playing (begin, sense, hook, vitals,
  battle_log, survive, engage, ui, upkeep): perception and safety are never a block's to skip;
- MODE steps (fight, hold, loot, after, ready, rest, idle, plant, search, position, pace) are
  OWNED: a block runs only the ones it owns; a mode step no playing block owns is passed.
So the box's canonical loop (below) calls exactly the driver's step sequence, tick for tick: the
equivalence of 5b-2 is by construction, and is checked offline by comparing step traces (the
driver against the block program, on scripted mode changes).

**The blocks and their bounds** (each "one bounded call": a time box, its exit condition, a value):

| Block | Owns | Hands back when | Returns |
|---|---|---|---|
| explore() | after (the rest decision and "after" -> "search"), ready, rest, idle, plant, search, position, pace | mode becomes "fight" (a target engaged) | the monster engaged (a value: species, box, cell), or none at its time box |
| choose_target() | -- (no step: reads the state) | at once | the target the engage step chose (hs.box_fight / the lock), or none |
| walk_to_target(t) | fight (the approach part: far approach, the reach check) | the target is in reach or gone | in reach / gone |
| strike(t) | fight | hs.lock is set (the strike landed) or the target is gone | struck / gone |
| wait_steal(t) | fight | the bare-steal controller's cue or time box | stolen / not |
| wait_kill(t) | fight, hold | the lock clears by a kill read (exp line, kill gap), or the fight ends | killed / lost |
| loot(t) | loot | the loot step ends (mode leaves "after"), or a fight begins | the pickups |
| look() | -- | after the common steps of one tick | the tick's reads |
| use_skill(key) | -- | one press of a declared role key, at a step boundary | pressed / refused |

➡️ SUPERSEDED by 14.2 #5-#7 and 14.5 (the built table): find_target (this table's explore) owns
hold as well; wait_kill owns fight only and hands back at the fight's end; loot owns fight, hold and
loot, and hands back once the loot step was reached.

Every block has a time box (a literal argument with a default: explore 120 s, the fight blocks
LOCK_MAX_S, loot the loot budget), and every block hands back at once on RUN_END (the run's end),
on a safety step's change of mode (a Fly Wing: the target is gone) or on the player's Stop.

**How the player schedules them.** The block `dungeon_hunt(...)` stays the hunt core, played
in-process (one input writer). With a `hunt` tab, run() gets a hook with `drive`: instead of its
own driver loop it calls `hook.drive(hunt)` (hunt = the cursor and the steps), and the player
plays the tab's loop function there, synchronously, as `_play_sync` plays an event: each primitive
call advances the cursor; the box's survival events keep playing through the same tick hook; when
`drive` returns (the loop function ended, a stop, RUN_END), run()'s normal end runs unchanged
(the swap back, the way home, the respawn).

**What the xmas_dun02 tabs show** (the description blocks of scripts/runner_flow_export.py's
outline become playing blocks): a `hunt` tab with the loop,

    def hunt_loop():
        while True:
            t = explore()
            attack(t)               # the monsters tab's recipe for t's species (stage 4a)

and the `monsters` tab's recipes (`knife_on(); strike(t); wait_steal(t); knife_back();
wait_kill(t); loot(t)`) played as blocks, not only read; each setting tab (5a) as now.

**The lint and the refusals** (➡️ as built: 14.4) (before any input; the backend's not_live names the same): a
primitive outside a hunt core's `hunt` tab or a recipe; a loop with no block that always advances
the cursor (explore or a time-boxed one; else it would spin without time passing); a recipe's
order the cursor cannot play (wait_kill before strike, loot before wait_kill: recipes.SHAPES
today, widened only with a trace test per new shape); use_skill without a declared role key the
start's slot check reads; a common step left out (impossible to write: they have no block);
`drive` with any other hook method missing.

**5b-2's A/B:** B5b-1 (the one box, 5b-1's built-in driver) vs B5b-2 (the same box plus the hunt
tab whose loop is the canonical one): an equivalence check with 13.5's bar; only after it holds,
the first experiment in blocks (e.g. no loot(t) for the Christmas Cookie, or no Knife swap on it).
➡️ Pre-registered in 14.7 (stage5b2_ab.py, not run); the first experiment: 14.8.

### 13.5 THE A/B of 5b-1 -- pre-registered 2026-11-14 18:3x ICT from `date`, BEFORE any 5b-1 run

**The arms differ ONLY in the runner's file.** Both play the one box (project_xmas_dun02.json,
section 10) through `flow_play.py play`, with the same runner settings (the box's setting blocks
and keys, checked as stage2_ab.same_vals does):
- **A** = the runner as main eb160ee1 has it (`git show eb160ee1:scripts/dungeon_hunt.py`, its
  sha256 pinned in the tool);
- **B** = 5b-1's runner (the merged file, its sha256 pinned at the merge).

How two arms run two runner files in one checkout: flow_play puts scripts/ first on sys.path
when it is imported, so a path trick cannot pick the file. A launcher (scripts/runner_pin.py)
reads the pinned file's TEXT, checks its sha256, compiles it as `dungeon_hunt` with `__file__` =
scripts/dungeon_hunt.py (the module's ROOT is computed from it) into sys.modules BEFORE flow_play
runs, then runs flow_play.py's main with the same argv. BOTH arms go through the launcher (the same
launch path), each with its own pinned text, and it writes `<run label>.runner.json` (the file's
sha256, the base revision, `HuntState` present or not). Why not a frozen copy committed in the
repo: 11,425 lines duplicated, and a copy that drifts. Why not before / after series: the Stormy
Knight's schedule and the map's state change over hours; alternating pairs share them. Why not a
second checkout of the base: it would also run the base's flow_play, poring_flow and the rest;
the launcher varies one file only. ➡️ Correction (the parent, 2026-11-14 19:3x, on review): the
tool has NO `git diff` check; both arms share the checkout's other code by construction, so only
the runner text differs. Since 5b-1's merge, main also carries round 20 (12.4: poring_flow's
settings, lint and the box's fixture; no change to flow_play or run()'s signature), which both
arms play alike.

**The series** (`scripts/stage5b_ab.py`, a sibling of stage5_ab.py sharing stage2_ab's setup,
detect server, run and score; run by the parent after review, NOT run yet):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage5b_ab.py plan  --label s5b1-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5b_ab.py run   --label s5b1-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5b_ab.py score --label s5b1-ab

- 3 pairs of 20 min, order A B, B A, A B; stage2_ab's setup before every run; a STOP file ends the
  series before its next run. Before it: merged and deployed; ASSIST; the Rogue in the game; the
  Run helper idle; no chain; `plan` refuses before any input on any check above.
- The score per run: stage5_ab's lines (the runner's own session, the same reader for both arms),
  and the tick pace: the gaps between consecutive hp_read records (one per tick).

**THE PRE-REGISTERED BAR** (`stage5b_ab.BAR`): B must hold, against A:

| Line | B must hold |
|---|---|
| deaths | B's deaths <= A's, over EVERY run that played (>= 1 min, or a death) |
| kills per hour | the mean paired difference (B - A) >= -2 x its standard error, over at least 3 valid pairs |
| loot steps per hour | the same rule |
| Knife openers per hour | B's series rate within +-20 % of A's (valid runs pooled) |
| the tick pace | B's median and 95th-percentile gap between hp_read records each <= A's + 10 ms (valid runs pooled) ➡️ s5b1-ab FAILED this line on the p95 alone (13.7: noise-dominated); kept as scored |
| no new record kind | every record kind B's runner sessions write is one the base runner's source writes (its `"kind": "..."` literals) |
| no runner error | no B run ends by an exception of the runner (hunt_end `error`, or a traceback in its log) |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: potions / h, Fly Wings / h by cause, steals / h, eats / h, the lowest HP, the
end reasons, each record kind's rate per hour per arm, the alarm's fires. The verdict: FAIL when
a judged line fails; INCONCLUSIVE when fewer than 3 pairs are valid (kills and loot unjudged) and
nothing failed; else PASS. Why these lines: B is the same program by construction, so the rates
are held to the pairs' own noise (as stage 4a's); the tick pace is the one thing the refactor can
change (the driver's calls): 10 ms is 5 % of the 200-ms tick, far above the expected tens of
microseconds and far below anything that changes play; the record kinds and the runner errors
catch a refactor slip that the rates would hide. No line is a strict "<" against an arm that may
read 0 (10.2's lesson), and deaths count over every run that played (section 7's).

### 13.6 ➡️ 5b-1 BUILT 2026-11-14 (feat/huntstate; offline only, NOT run live; the A/B of 13.5 not run)

As designed in 13.1-13.3, but for five things found while building it, each AST-neutral and each
checked by `huntstate_check.py check`:
1. **The tick's reads are DECLARED in run().** A name bound only inside the loop (155 of them:
   `tick`, `img`, `pct`, `near_`, ...) had no binding left in run() once its statements moved into
   the steps, so the steps' `nonlocal` was a SyntaxError (the rule test found it). OUTLINE now
   writes one bare annotation per such name before the steps (`tick: Any`; it binds nothing, so a
   read before any assignment is still a NameError, as the unbound local was). The checker
   verifies the declared set is EXACTLY the names only the steps bind (an extra one could shadow a
   global).
2. **A loop-level annotated assignment loses its annotation to that declaration** (`boss_hit: str
   | None = None` becomes `boss_hit = None` in its step; `boss_hit: str | None` is declared):
   Python forbids annotating a `nonlocal` name; a local's annotation is never evaluated.
3. **Comments moved, never code:** a line that the rewrite pushed past 100 columns only because of
   its trailing comment got the comment on its own line above (16 in LIFT, 5 in OUTLINE); 16
   format-skipped statements were re-wrapped by hand; every other wrap is ruff format's own.
4. **Each step has a one-line docstring** (`huntstate_check.STEP_DOCS`, from 13.2's table) and a
   long `nonlocal` list is several `nonlocal` statements.
5. **A helper for tests:** `huntstate_check.driver_loop(run)` = the loop as the driver plays it
   (the steps' bodies inlined in hunt_steps' order, the signals back to continue / break): the
   tests that reason about "the loop's statements" (the hook's place, the box's survival tick, the
   flag-off counts of 9.36 / 9.37) assert their facts on it.

**The commits:** a5102f9b (this section's design, before code), 12003e99 (the tool and its rule
tests), bb623c04 (LIFT + ALIAS: HuntState), 4737c272 (OUTLINE: the steps), cd1af906 (the A/B
tools), then this note. The full Python suite at bb623c04 and at 4737c272: every test passes but
the three known to fail in a /dev/shm worktree only (test_mapcache_paths, test_dungeon_hunt's
dagger-worn start check, test_patrol_sim's gef_fild10 laps: client data a worktree lacks); 5,806
passed at 4737c272; ruff check, ruff format --check and mypy clean. run() is 4,741 lines now (+347: the 155 declarations, the step
heads and docstrings, the driver; the HuntState class is outside it); dungeon_hunt.py 11,932.

**Re-derive it** (the reviewer's check; the base must be eb160ee1's runner):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/huntstate_check.py check      # prints every line below, rc 0

    LIFT (49) / ALIAS (49) / OUTLINE (20 steps): begin sense hook vitals battle_log survive engage
      ui upkeep fight hold loot after ready rest idle plant search position pace
    resolver vs symtable (each table's locals; each lifted Name's binding): the same
    LIFT/ALIAS preconditions: all hold;  OUTLINE conditions: all hold
    HuntState.__slots__: missing none, extra none;  signals: ['RUN_END', 'TICK_DONE']
    run() == OUTLINE(ALIAS(LIFT(base))): YES;  the module outside run(): the same

If scripts/dungeon_hunt.py changes on main before the merge, 5b-1 is re-derived on the new base
(`derive`, then `derive --steps`, ruff format, the long lines by hand, `check --base <new>`), and
BASE_REV / stage5b_ab.A_SHA256 move with it.

**The evidence and its limits:**
- PROVEN offline, every path: the committed run() is the three rewrites of eb160ee1's run() (the
  check above), under preconditions the checker verifies; the rewrite rules' semantics shown BY
  EXECUTION on a program with every hazard (services/backend/tests/test_huntstate_check.py: the
  same traces on three inputs that reach a continue inside try / finally, a for-else, the loop's
  break, an except-as, a walrus in a comprehension, a lambda default, a shadowing parameter, a
  closure's nonlocal); and each kind of wrong rewrite NAMED by the checker (a shadowed parameter
  renamed -- and it plays differently --, a step binding a name without nonlocal, the steps
  reordered, a signal swapped, a slot missing, a new top-level statement, a wrong resolver against
  symtable, locals() / except NameError / a twice-bound alias refused).
- Run-time sanity: HuntState() takes its 98 slots; an unset read and a misspelt write raise
  AttributeError; the runner's feature version stays dungeon@9.53.
- NOT shown offline (13.3): the driver's cost per tick, the real I/O interleaving, the launcher
  live -- the A/B of 13.5 is their check. No whole-run fake environment was built (13.3's
  reasons).

**The tests changed** (the same fact on the new text; listed by test in the 5b-1 report): in
LIFT, 49 test functions in 11 files (the fragments re-written through the rewrite's own edits, by
hand where a line moved; test_loot_memory's 9.36 hash re-pinned on the rewritten lines, its
provenance in the comment; test_dungeon_hunt's `'if reason != "death"' not in` -- which the rename
made vacuous -- now names `hs.reason`; `"nonlocal last_walk_click" in src` now says the closure
writes `hs.last_walk_click` with no nonlocal); in OUTLINE, 14 in 9 files and two helpers (`_loop`
in test_live_player.py and test_survival_events.py now return driver_loop) (`continue` / `break`
written as the steps' signals; the AST tests read driver_loop). Every assertion kept its fact; the
negative ones were scanned for a rename that would make them vacuous (one found, above). New:
test_huntstate_check.py (12 test functions, 14 cases), test_stage5b_ab.py (10).

**The A/B tools (13.5) BUILT, not run:** scripts/stage5b_ab.py (plan / run / score; BAR as 13.5)
and scripts/runner_pin.py (the launcher). `plan` refuses unless A's text is eb160ee1's (sha256
a1bb5728...) and B is its 5b-1 rewrite (huntstate_check), and unless the Run config has the fast
alarm on. One change from 13.5's words: the plan does not test `git diff eb160ee1 <head>`; every
module but the runner is the checkout's own for BOTH arms by construction (the launcher pins only
dungeon_hunt), so the one thing to prove is that B's text is A's rewrite, which is the stronger
check. Each run's `<label>.runner.json` records the text's sha256, its size and whether it has
HuntState; series.json records the base revision and both sha256s.

**Still fixed / left for later** (none needed for 5b-2's first step):
- the 155 declarations: a name that one step alone binds and reads (most of them) could be that
  step's own local, but only with a liveness proof (no read before its write within a tick, none
  across ticks); 5b-1 keeps them run()'s;
- the one-item cells (`escaped[0]`, `n_strike[0]`, ...) and the 49 aliases could be plain `hs.`
  attributes (more rename churn in the tests, no behaviour);
- HuntTick could be built from hs (the hook's view), and the steps could move out of run() to take
  (hs, io): later stages.

### 13.7 Result of s5b1-ab (run 2026-11-15 00:37-02:47 ICT, scored 02:4x): FAIL by the bar -- on the pace p95 line only

`stage5b_ab.py score --label s5b1-ab`: 3 pairs, all 6 runs valid (19.9-20.0 min, each ended by its
time box), 0 invalid, 0 deaths. A = eb160ee1's runner (pinned a1bb5728), B = 5b-1's (521e86ac).

    run      arm  min   deaths kills/h loot/h open/h  tick median  p95     errors
    r01A     A    19.9    0    151.1   193.4  117.9    201.2      1044.4    -
    r02B     B    19.9    0    151.0   193.3  120.8    201.7       991.1    -
    r03B     B    19.9    0    142.0   163.2  136.0    201.6      1108.7    -
    r04A     A    19.9    0    142.0   169.2  129.9    201.6       974.1    -
    r05A     A    20.0    0    138.3   159.3  132.3    201.6       956.9    -
    r06B     B    19.9    0    147.4   168.5  138.4    201.5       985.1    -

The bar, line by line:
- deaths A 0, B 0 -> PASS;
- record kinds: none new in B -> PASS;
- runner errors: none -> PASS;
- openers/h: A 126.7, B 131.7 (within +-20 %) -> PASS;
- kills/h: paired -0.1, 0.0, +9.1; mean +3.0, SE 3.0 -> PASS;
- loot steps/h: paired -0.1, -6.0, +9.1; mean +1.0, SE 4.4 -> PASS;
- **tick pace:**
  - median: A 201.5, B 201.6 ms (n 10,714 / 10,596) -> within +10;
  - p95: A 991.3, B 1016.7 ms -> **+25.4 > +10 -> FAIL**.

**The verdict stays FAIL, as pre-registered; it is not re-scored** (5b-1's BAR is unchanged:
`stage5b_ab.py score` still prints FAIL). What the failing line measured:
- **The p95 gap between hp_read records is not a tick's cost.** It is the long actions: a walk, a
  strike, the loot step, which hold the tick for about a second. It moves with the game, not the code.
- **Its noise dwarfs its tolerance:**
  - the per-run p95 SD is 46.4 ms in A and 69.7 in B;
  - the three A runs alone, the same code, spread 87.5 ms;
  - the PAIRED B - A p95 differences are -53.3, +134.6 and +28.2: mean +36.5, SE 54.4, i.e. zero
    within noise.
- **The median shows a tick's own cost:** the `pace` step holds a tick at 200 ms, so driver overhead
  would push it up. It is equal, +0.1 ms, and its per-run spread is 0.5 ms.
- **The code is the same program:** huntstate_check proves run() is the same program as eb160ee1's
  (13.3).
- **Lesson for the next bar** (the same family as 10.2's): set a tolerance from the measured noise, or
  pick a statistic the change can move. 14.7a corrects 5b-2's pace line BEFORE any 5b-2 data.

**The decision (the parent, 2026-11-15 02:5x ICT; within Batt's 18:1x "5b: go on, no need to ask me
again"):** 5b-1 stays on main, and 5b-2 goes ahead.
- **Why:**
  - every outcome line passes;
  - the only line that failed is noise-dominated by the numbers above;
  - the AST proof stands;
  - the median, the line that would show a slower runner, is equal.
- **Not done:** a re-run of 5b-1 with a new bar. It would re-measure noise for 2 h on a proven-equal
  program.
- **Recorded for Batt to overrule:** if he wants "proven before the next" read strictly, the step is a
  fresh s5b1-ab2 with 14.7a's corrected pace line.

## 14. Stage 5b-2: the steps as live blocks (➡️ BUILT 2026-11-14 20:1x-20:5x ICT, feat/hunt-blocks; offline only, NOT run live; its A/B pre-registered below, not run)

**What it is.** 13.4 as designed, but for the refinements of 14.2: a map node's function
`hunt_loop(t)` (the editor's tab `hunt`) is its hunt core's loop. run() calls the live player's
`hook.drive(cursor)` instead of its own driver loop, and the player plays the function's
statements with the engine's own interpreter; each block is ONE bounded call into run()'s steps
through the TICK CURSOR. A box without a hunt loop plays exactly as 5b-1 (14.3). The parent merges
it only after 5b-1's A/B (13.5): `stage5b_ab.py` refuses the 5b-2 runner as its B (14.3).

    def hunt_loop(t):
        while True:
            t = find_target()       # 13.4's explore()
            fight_target(t)                # 13.4's attack(t): the monsters tab's recipe for t's species

### 14.1 What was built

| Piece | Where | What |
|---|---|---|
| The cursor | `scripts/dungeon_hunt.py` `HuntCursor`, `HuntView`, `HuntTarget`, the tables `STEP_NAMES` / `COMMON_STEPS` / `HANDBACK_AT` / `STEP_GUARD` / `BLOCK_OWNS` (HUNT_BLOCKS_VERSION 9.55, in runner_flow_export.NOT_FEATURES) | (the tick, the next step); a block advances it until its exit holds at a hand-back point, its time box passes there, or the run ends (a RUN_END, the run's time box, a spin: `DRIVE_SPIN_MAX` 50 block calls in a row with no step). Each block's value (14.5) |
| The drive branch | run(): `if hook_drives(hook): ... hunt_drive(hook, HuntCursor(hunt_steps, ...), hs, ev) else: <5b-1's driver loop>` | `hunt_drive` refuses a driving hook without tick / survive / call / recipe / event (`drive_refused`, before any step), records `drive` start / end (the cursor's counts), sets the reason when the loop returns (`drive_end: ...`) or spins (`drive_spin: ...`); a step's RUN_END and the time box keep their own reasons; run()'s normal end follows unchanged |
| The proof of "no drive = 5b-1" | `scripts/huntstate_check.py drive` (`drive_check`, `undrive`, `guard_problems`, `DRIVE_ADDED`) | 14.3 |
| The rules | `packages/poring_flow/src/poring_flow/huntloop.py` (the ONE place), `lint/huntloop.py` (findings), `live.problems` / `live.hunt_plan` (`HuntPlan.loop`, `skill_keys`; not a play: run() gets the same arguments), `lint/loops.py` (a hunt loop's `while True` is bounded by the hunt core), `lint/structure.py` (a hunt block's value is any value), `recipes.py` (the recipe primitives may stand in the loop) | 14.4 |
| The blocks | blocks.yaml: `find_target`, `choose_target`, `walk_to_target`, `look`, `fight_target` (new, `live: true`); `use_skill` live (in the loop only) | 14.5 |
| The player | `scripts/flow_play.py`: `RunnerPlan.loop` / `skill_keys`, `DriveHook` (a HuntHook with `drive`, only for a box with a hunt loop), `LivePlayer.hunt_drive` / `_drive_block` / `_drive_fight`, the lock's recipe answer remembered (`_lock_answer`) | the loop played synchronously inside run() (no engine tick between blocks: a statement that would wait is refused before any input); the box's survival events keep playing through the tick hook inside the common steps; records `drive` (start / end) and `fight_target` (the species, the recipe, each step's value) |
| The step-trace harness | `scripts/hunt_trace.py` (`check`) | 14.3 |
| The editor | blockdefs.ts (additive: `pl_hunt_take`, `pl_hunt_step`, the Hunt category on a tab named `hunt`), blocks.ts (one converter case each way), theme.ts, search.ts, liveready.ts (Run's readiness reaches hunt_loop), project.ts `xmasHuntProject()` / `huntLoopDef()`, the Load lists of /flows and /maps | 14.5, 14.6 |
| The fixture | `services/frontend/src/lib/flow/fixtures/project_xmas_dun02_hunt.json` (= `xmasHuntProject()`, canonical; sha256 prefix of its canonical form `2ea8918c536d`) | 14.6 |
| The A/B tool | `scripts/stage5b2_ab.py` (plan / run / score), tests | 14.7 |

### 14.2 Refinements of 13.4 (each found while building it)

1. **`explore()` is `find_target()`, `attack(t)` is `fight_target(t)`.** The one box's walk tab has a
   SETTING named `explore` (its exploring rule), and a catalogue name cannot be a variable or a
   function (the names rule); the pre-commit locale-pack guard refuses the other word as a quoted
   code literal (a client UI string), and a first `fight(t)` collided with a function `fight` that
   existing test flows define (the full suite found it: test_rank, test_lint_matrix).
   `find_target` says what it returns (the monster engaged), `fight_target` what it plays (the
   recipe on t); with choose_target and walk_to_target the four read alike.
2. **The loop takes its target as its one input: `def hunt_loop(t)`.** An assignment needs a
   declared variable or a function input, and an IR literal has no "none": the player calls the
   loop with t = none.
3. **Where a block hands back: only BEFORE the fight step or the after step** (`HANDBACK_AT`), the
   two points where a tick's mode work and the search's work begin (the common steps of the tick
   have run there). An exit checked before every mode step would hand back mid-tick after the
   search step's walk-sword engage (it sets mode fight and does NOT end its tick: position and pace
   still run): the fight blocks own neither, so they would be passed.
4. **Mode steps with a GUARD are called whoever plays when their mode is another**
   (`STEP_GUARD`: fight acts only in mode fight, loot only in mode after; huntstate_check proves it
   from the AST): their bodies then do nothing, and the trace stays the driver's literally. A step
   is PASSED only when its guard holds and no playing block owns it -- the only way a block
   program plays differently (counted; the drive's end record carries the counts).
5. **The ownership, as it must be for the driver's sequence** (13.4's table was close but not
   exact): `find_target` owns hold, after, ready, rest, idle, plant, search, position, pace (13.4
   left hold to wait_kill, but the driver runs the loot recheck and memory in hold on every search
   tick); `walk_to_target`, `strike`, `wait_steal` and `wait_kill` own fight; `loot` owns fight,
   hold and loot (it may be entered while the fight still runs: a wait_kill's time box); `look`,
   `choose_target` and `use_skill` own none.
6. **The exits:** find_target: mode fight (its value the target: the lock's cell, else the engage
   box's spot, and the detector's species of the box the runner struck, None before any box
   strike); strike: a lock, or no fight ("gone"); walk_to_target: a lock or a far approach's walk
   over (APPROACH_HOLD_S), or gone; wait_steal: no bare phase running ("stolen", "not_stolen",
   "no_knife") or gone; wait_kill: the FIGHT's end ("killed" when a kill was read meanwhile, else
   "lost": a fight can hold several kills, the melee ring's queue); loot: the cursor reached the
   loot step since loot began (its value the loot clicks), at once (0) with no fight and no fight's
   end before this tick's loot step.
7. **loot(t)'s time box bounds the fight it waits for, never its loot step.** The harness (14.3)
   found it: with 1-s time boxes, a loot(t) that handed back between the fight's end and the loot
   step (a recheck's TICK_DONE in between) left find_target to pass the loot step. Once the fight is
   over, loot(t) plays on to the step (the step's own budget, LOOT_MAX_S, bounds it), as the driver
   does. Every other time box hands over to a block that owns the same steps, so it never changes
   the steps run (the harness checks it with every time box at 1 s).
8. **fight_target(t) chooses its recipe AT THE LOCK, after strike(t).** t's species is often unknown when
   the fight begins (an engage by a hit), and the runner asks `hook.recipe(species)` at a new
   target's lock (BareCtl's decision); the player remembers that answer and fight_target(t) plays THAT
   recipe's remaining steps (both shapes begin with the strike after the Knife; no recipe for the
   species: the runner's own, the Knife shape). knife_on() / knife_back() play at the runner's
   moments (stage 3's calls: the same presses at the same moments), so at their place in the recipe
   they take no step. Inside one fight series the runner still asks per lock, as 4a.
9. **use_skill(key) presses only the hunt core's heal key** (`DRIVE_SKILL_ROLES` "potion"): a role
   key the start's slot check reads AND that a block may press between two steps; the Fly Wing (its
   after-the-fly steps), the Butterfly Wing (the way home) and the Knife keys (the swap's read-backs)
   have moments of the runner's own. In a recipe use_skill stays refused (8: a step before the strike
   cannot depend on the species). A skill key of its own (a new role the start checks, its SP, its
   cast and after-cast waits) is a follow-up.
10. **A loop that could spin is refused statically** (`hunt_spin`): each `while` begins with
    `t = find_target()` and holds, at its top level, a block that plays the fight to its end on t
    (fight_target, wait_kill, loot). Then every turn takes a step: find_target advances whenever no fight
    runs, the fight player whenever one does. The cursor's spin guard is the run time's own
    backstop.
11. **The hunt loop's language is small**: its blocks and if / while / repeat / for / set / break /
    continue / return; conditions read `known(t)` and the blocks' values only (no sensor: the runner
    reads them itself). No wait, press_key, call, stop or exit: the runner waits for each block and
    plays nothing else there. A block's value is a VALUE (a monster, a word, a count), never a
    failure that stops (on_fail is not applied).
12. **The A/B runs one runner file for both arms.** A box without a hunt tab plays run()'s own
    driver, which IS 5b-1's program (14.3), so the arms differ only in the box (stage5_ab's
    pattern), with no launcher.

### 14.3 The proofs, and their limits

**With no drive, the program is 5b-1's** (`huntstate_check.py drive`, rc 0; re-derive it):

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/huntstate_check.py drive    # the base: DRIVE_BASE bb6d41eb (5b-1 merged)

    the drive branch: line 11292; its condition: hook_drives(hook); its else: 5b-1's driver loop
    run() without the drive branch == 5b-1's run() (as ASTs, docstrings included): YES
    the module outside run(): 5b-1's statements unchanged; added [the 16 names of DRIVE_ADDED]
    the additions == DRIVE_ADDED: YES
    the guarded steps (fight: mode fight, loot: mode after): each acts only in its mode;
      step_fight ends a fight tick with TICK_DONE
    STEP_NAMES == hunt_steps' names: YES

- run() with its drive `if` replaced by its `else` (the driver loop) is 5b-1's run() as an AST,
  docstrings included: on every path, the CLI (no hook) and a box without a hunt tab (a HuntHook,
  no `drive`) play 5b-1's program. The condition `hook_drives(hook)` is pure (`hook is not None and
  callable(getattr(hook, "drive", None))`).
- The module outside run(): every 5b-1 statement unchanged, the additions exactly DRIVE_ADDED.
- The cursor's facts about the steps, from the AST: step_fight's body is one `if hs.mode ==
  "fight":` whose every return is TICK_DONE and which ends with one; step_loot's statements are
  ifs whose test begins with `hs.mode == "after"`.
- `huntstate_check.py check` (5b-1's proof) reads the drive branch as its else only with
  `drive_ok` (the CLI's, the committed-runner test's); without it -- stage5b_ab's B check -- the
  branch is a failed condition ("NOT 5b-1's rewrite alone"): 5b-1's A/B keeps measuring 5b-1's text
  alone (test_stage5b_ab: its plan refuses the 5b-2 runner as B).
- Positive cases (each wrong rewrite NAMED, test_hunt_cursor.py): a decision changed outside the
  branch, an else that is not the driver loop, the branch's condition changed, a 5b-1 module
  statement changed, an addition not listed, the loot step's guard dropped, the fight step falling
  through in mode fight.

**The canonical loop calls the driver's step sequence, tick for tick** (`hunt_trace.py check`,
rc 0): run()'s driver loop (A) and the hunt loop played by the REAL live player through the
cursor (B: `LivePlayer.hunt_drive` on the fixture's hunt_loop, the engine's interpreter,
find_target / fight_target / the recipe answered at the fake lock) over the same FAKE steps -- the real
steps' names, order and mode semantics (14.2's guards; the after step turns after into search; the
hold step ends the tick on a lock or a fight), with effects drawn per (seed, tick, step, mode), so
the same call in the same state has the same effect in both runs:

    .venv/bin/python scripts/hunt_trace.py check --seeds 200

    13 hand scenarios (one fight; a fight that never locks; the loot step starts a fight; the
      recheck holds a tick; a box Fly Wing mid-fight; a walk-sword engage that keeps its tick; a
      plant and a queued target; a rest; two kills in one fight; an unreachable attacker; a RUN_END
      mid-fight; the run's time box mid-search; no Knife), 200 random ones, 10 random ones with
      every hunt block's time box at 1 s
    the driver's trace == the hunt loop's: YES, every scenario (223 scenarios)
      -- 154,420 ticks, 1,900,948 step calls; every effect occurs (engages by a hit / walk sword /
      plant / queue / the loot step: 3815 / 1231 / 717 / 1030 / 452; locks 19,619; kills 17,877;
      fight ends 4,663; loot steps 4,172; rechecks 3,477; box Fly Wings 1,549; RUN_ENDs at 9 steps)

- No step is passed in B; the traces are equal call for call ((tick, step, signal)).
- Negative controls (test_hunt_blocks.py): a loop without loot (`t = find_target(); wait_kill(t)`)
  passes the loot step and differs; loot(t) without hold, or no hand-back before the after step,
  differs. The comparison names each.
- The bug it found (14.2 #7) was fixed in the cursor, not in the harness.

**Their limits** (what neither shows; the live A/B, 14.7, is their check):
- the harness's steps model the MODE SEMANTICS only, not the real steps' bodies, reads or input;
  that the real steps have those semantics is the AST facts above, and the guards cover only the
  two steps the cursor calls without owning them;
- the box's survival events are not played in the harness (they play inside the common steps,
  which every block runs, so they cannot change which steps run);
- the clock is simulated: the player's interpreter between steps (a few Python calls a block) is
  not measured (the A/B's tick pace line is);
- equal traces mean the same steps in the same order in the same ticks, which with the same world
  is the same program; a live run's world differs between any two runs anyway;
- recipes other than SHAPES' two are not traced (they are refused: 14.4).

### 14.4 The lint rules and the refusals (before any input; the backend's not_live says the same)

| Rule | What | Words (abridged) |
|---|---|---|
| hunt_primitive | find_target, choose_target, walk_to_target, look, fight_target, use_skill outside the hunt loop (strike / wait_steal / wait_kill / loot(t) outside a recipe and the loop: 4a's recipe_primitive) | "find_target plays live only in the hunt core's hunt loop (a map node's function hunt_loop(t), its tab hunt; stage 5b-2)" |
| hunt_loop_place | a hunt loop on a node whose main runs no dungeon_hunt | "hunt_loop is a hunt core's loop: its map node's main runs dungeon_hunt" |
| hunt_loop_input | not `def hunt_loop(t)` | "hunt_loop takes one input, the target its blocks work on (none at the start)" |
| hunt_statement | a wait, press_key, call, stop, exit, another block, a call's value in the loop | "a wait in hunt_loop: the hunt core waits for its blocks and plays nothing else there ..." |
| hunt_sensor | a sensor in its conditions but known() | "hp_percent() in hunt_loop: the loop reads the hunt through its blocks' values" |
| hunt_target | a block's target that is not a variable | "its target is a variable holding find_target()'s value" |
| hunt_spin | a while not beginning with t = find_target(), or with no fight player on t at its top level | "... else it could spin while no step runs" |
| hunt_skill | use_skill without a declared role key (the heal key) | "use_skill in hunt_loop presses a DECLARED role key the start's slot check reads ..." |
| (4a, unchanged) | a recipe order the cursor cannot play: recipes.SHAPES, widened only with a trace test per new shape; use_skill in a recipe (still "4b"); a recipe called by a block (fight_target(t) is the way) | |
| (the runner's) | a driving hook without tick / survive / call / recipe / event (`drive_refused`) | |

A common step cannot be left out (it has no block). The cursor ends a spin at run time
(`drive_spin`), the backstop of hunt_spin.

### 14.5 The new blocks (and the fields that should become pickers)

| Block (Python) | Block type on /flows | Value | Time box (timeout_s default) |
|---|---|---|---|
| `t = find_target()` | `pl_hunt_take`: VAR, BLOCK, ARGS, TIMEOUT | the monster engaged, or none | 120 s |
| `t = choose_target()` | `pl_hunt_take` | the fight's monster, or none | at once |
| `r = look()` | `pl_hunt_take` | the tick's reads | at once (the first tick's common steps first) |
| `walk_to_target(t)` | `pl_hunt_step`: BLOCK, ARGS, TIMEOUT | "in_reach" / "gone" | 30 s |
| `fight_target(t)` | `pl_hunt_step` | wait_kill's value ("killed" / "lost") | 300 s (its steps: their own) |
| `strike(t)`, `wait_steal(t)`, `wait_kill(t)`, `loot(t)` | `pl_action` (as in 4a) | "struck" / "gone"; "stolen" / "not_stolen" / "no_knife" / "gone"; "killed" / "lost"; the loot clicks | 60 / 10 / 120 / 30 s |
| `use_skill(key="F1")` | `pl_action` | "pressed" / "refused" | at once |

The Hunt category (a tab named `hunt` of a map node): `def hunt_loop(t)`, `while True`, the
canonical pair, walk_to_target, the four recipe steps, choose_target, look, use_skill and `if
known(value=t)`. **Fields that should become pickers** (the pickers agent's conversion, after both
merges): `pl_hunt_take.VAR` (a variable picker: the loop's input and the tab's variables),
`pl_hunt_take.ARGS` / `pl_hunt_step.ARGS` `target=t` (a variable picker), `TIMEOUT` (a number with
the block's range, 1-600 s), and on the generic `pl_action` of use_skill its `key="F1"` (a key
picker of the declared keys) and of strike / wait_steal / wait_kill / loot their `target=t`.
➡️ CONVERTED at the merge of main's round 21 (14.10).

### 14.6 The fixture

`project_xmas_dun02_hunt.json` (name `xmas_dun02_hunt`) is `project_xmas_dun02.json` plus the tab
`hunt` after `monsters`, holding the canonical `hunt_loop(t)`; nothing else differs (but the name
and the description: tested). The ready-made one box is NOT changed (5b-1's A/B plays it, and
`stage5b_ab` refuses unless the runner is 5b-1's), nor are the frozen arms (their sha256 pinned):
the pinned argv (test_settings_blocks.py, 97 arguments) is unchanged, and the hunt box gives the
same argv, the same run() arguments and the same keys as the one box (test_hunt_blocks.py). Its
Python view:

    # xmas_dun02/hunt.py
    def hunt_loop(t):
        while True:
            t = find_target()
            fight_target(t)

The round trip is exact: project JSON -> the Python files -> the project (test_hunt_loop.py), and
every tab -> Blockly -> the project, in the converter and in the real Blockly (project.test.ts,
blockly_headless.test.ts, huntloop.test.ts); `xmasHuntProject()` is the fixture byte for byte.

### 14.7 THE A/B of 5b-2 -- pre-registered 2026-11-14 20:5x ICT from `date`, BEFORE any 5b-2 run

**The arms differ ONLY in the box** (`scripts/stage5b2_ab.py`, stage5_ab's pattern sharing
stage2_ab's setup, detect server, run and score and stage5b_ab's score lines): both play the
checkout's runner through `flow_play.py play` with the same runner settings (stage2_ab.same_vals):
- **A = B5b-1**: `project_xmas_dun02.json` (no hunt tab: run()'s own driver, 5b-1's program);
- **B = B5b-2**: `project_xmas_dun02_hunt.json` (the canonical hunt loop drives the steps).

`plan` refuses before any input unless the two boxes take the same settings and keys and the fast
alarm is on; A has no hunt loop and B the canonical one, B being A plus that tab alone; run()
gives both the same arguments; the checkout's run() without its drive branch is 5b-1's
(huntstate_check drive); and the step traces are equal on every hand scenario and 50 random ones.

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage5b2_ab.py plan  --label s5b2-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5b2_ab.py run   --label s5b2-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5b2_ab.py score --label s5b2-ab

- 3 pairs of 20 min, order A B, B A, A B; stage2_ab's setup before every run; a STOP file ends the
  series before its next run. Before it: 5b-1's A/B run and passed (13.5), feat/hunt-blocks merged
  and deployed (the backend, the Run helper); ASSIST; the Rogue in the game; the Run helper idle;
  no chain.
- The score per run: stage5b_ab's lines (the runner's own session, the same reader for both arms;
  the tick pace from the hp_read gaps; the record kinds; a runner exception) and the drive's
  records (`drive` start / end: ended, passed, ticks).

**THE PRE-REGISTERED BAR** (`stage5b2_ab.BAR`): B must hold, against A -- 13.5's lines, with A
the 5b-1 program, and the drive's own line:

| Line | B must hold |
|---|---|
| deaths | B's deaths <= A's, over EVERY run that played (>= 1 min, or a death) |
| kills per hour | the mean paired difference (B - A) >= -2 x its standard error, over at least 3 valid pairs |
| loot steps per hour | the same rule |
| Knife openers per hour | B's series rate within +-20 % of A's (valid runs pooled) |
| the tick pace | ~~B's median and 95th-percentile gap between hp_read records each <= A's + 10 ms (valid runs pooled)~~ ➡️ CORRECTED by 14.7a before any run: B's MEDIAN gap <= A's + 5 ms; the p95 reported only |
| no new record kind | every record kind B's runner sessions write is one the 5b-1 runner's source writes (its literal kinds), one A's sessions wrote, or the drive's own `drive` |
| no runner error | no B run ends by an exception of the runner (a traceback in its log, or hunt_end `error` not a refusal) |
| the drive | every B run that played drove (one `drive` start and one end in its runner session), passed no step (the end's `passed` empty), and its drive ended as the run did (`time_box` / `run_end`, never a spin, a refusal or the loop returning); no A run drove |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: potions / h, Fly Wings / h, steals / h, eats / h, the lowest HP, the end
reasons, each record kind's rate per hour per arm. The verdict: FAIL when a judged line fails;
INCONCLUSIVE when fewer than 3 pairs are valid (kills and loot unjudged) and nothing failed; else
PASS. Why: B calls the same steps by construction (14.3), so the rates are held to the pairs' own
noise as in 13.5; the tick pace is what the drive can cost (a few Python calls a block: far below
10 ms); the drive line catches a pass or a spin that the rates would hide. No line is a strict "<"
against an arm that may read 0 (10.2's lesson); deaths count over every run that played (section 7's).

#### 14.7a CORRECTION to the pace line, pre-registered 2026-11-15 02:5x ICT from `date`, BEFORE any 5b-2 run (13.7's lesson)

- **Judged now: the MEDIAN alone.** The pace line judges the MEDIAN hp_read gap: B's <= A's + 5 ms,
  pooled over the valid runs (`stage5b2_ab.BAR`: `pace_ms` 5.0, `pace_p95` False).
- **Why the median:**
  - 5b-2's possible cost is the block interpreter's work per step, which lands in every tick;
  - `pace` holds a tick at 200 ms, so a cost shows as a higher median;
  - s5b1-ab's per-run medians spread 0.5 ms, so 5 ms is 10x that and still catches a real per-tick
    cost;
  - test_stage5b_ab's new test fails a B tick 6 ms slower.
- **Reported, no longer judged: the 95th percentile.** It is the long actions' (per-run SD 46-70 ms in
  s5b1-ab).
- **Every other line of 14.7 is unchanged.** `stage5b_ab`'s own BAR (5b-1's, scored) is untouched.

### 14.8 The first real block experiment after it (➡️ BUILT 2026-11-15 and pre-registered: section 16; not run yet)

Only once 14.7 holds. **First: no Knife swap on the Christmas Cookie and the Cookie** -- B5b-2 vs
B5b-2' where `attack_cookie` and `attack_cookie_xmas` are `strike(t); wait_kill(t); loot(t)` (4a's
PLAIN_SHAPE, already playable: the runner strikes those species without the Knife, and fight_target(t)
plays that recipe's steps). It needs no new shape, so no new trace test; its bar would be the
openers / h and the steals / h per species (the Cookies carry no steal worth the swap time, 2b),
the kills / h within the noise, deaths not more. **Next: no loot(t) for the Christmas Cookie**
(13.4's other suggestion) needs recipes.SHAPES widened to `strike, wait_kill` -- with a trace test
for the new shape (the loot step is then PASSED after that species' fight: the harness's
"no loot" control shows exactly that pass) and an answer to what the runner's loot recheck /
memory do with that kill's cells (they would still look later: 14.2 #5's hold).

### 14.9 Commits, tests, and what stays

**The commits** (feat/hunt-blocks): 18b41136 (the cursor; run()'s drive branch; huntstate_check
drive), c224ac54 (the hunt loop: blocks, rules, the player, the harness, the fixture), 7a8c07ca (the
editor: the hunt tab and its blocks), c302029a (stage5b2_ab.py), 62ddbc56 (this section, ADR-0020
Amendment L -- written as K on the branch, renumbered L at the merge of main's round 21, whose
Amendment K is the pickers --, console.md), 31997a22 (the block `fight` renamed `fight_target`: the full suite found a
function `fight` in existing flows, 14.2 #1), then the test results below.

**The tests at 31997a22** (2026-11-14, the suite ended ~21:2x ICT): the full Python suite 5,869 passed, 94 skipped,
3 failed -- exactly the three that fail in a /dev/shm worktree only (test_mapcache_paths,
test_dungeon_hunt's dagger-worn start check, test_patrol_sim's gef_fild10 laps: client data a
worktree lacks); ruff check and mypy clean; ruff format --check clean but the two files that fail on
main (docs/setup/new-lab-host.md, test_fight_time.py); the frontend's test (458 passed, 1 skipped),
typecheck and lint clean; `huntstate_check.py check` and `drive` rc 0; `hunt_trace.py check
--seeds 200` YES on all 223 scenarios. **Changed
tests** (the same fact on the new state): test_huntstate_check (the committed runner is the rewrite
with `drive_ok`; without it the branch is named), test_stage5b_ab (B is 5b-1's file, bb6d41eb's;
new: the 5b-2 runner is refused as B), test_recipes (use_skill in a recipe: refused in the recipe's
own words; the catalogue lists use_skill live), test_live_player (the live blocks list). **New:**
test_hunt_cursor.py (12 test functions), test_hunt_blocks.py (9; 21 cases), test_stage5b2_ab.py
(6), packages/poring_flow/tests/test_hunt_loop.py (7; 16 cases),
services/frontend/src/lib/flow/huntloop.test.ts (5); project.test.ts and blockly_headless.test.ts
round-trip the hunt box too.

**Still fixed / left for later:** a skill key of its own for use_skill (14.2 #9); sensors in the
loop's conditions (they would need the tick's reads as values); calls of helper functions from the
loop; recipes beyond SHAPES (14.8); the loop on a Global node shared by several hunt cores (allowed
by the name rule, not exercised); the 13.6 leftovers (the 155 declarations, the one-item cells).

### 14.10 ➡️ The merge of main's round 21 (5d6bf17e: the pickers), 2026-11-14 ~21:3x ICT

**The conflicts:** one, ADR-0020's last amendment. Main's Amendment K is round 21's ("a value that
is not a name is a picker", written ~19:4x); 5b-2's (the hunt loop, ~20:5x) is now **Amendment L**,
after it, adding to C-K (14.9's pointer says so). Everything else merged by itself: main changed no
script, so the runner is the same on both sides, `huntstate_check.py drive` (base bb6d41eb) and
`check` (base eb160ee1) stand as they were, and so does every Python test of 5b-2.

**The two block types under round 21's rules** (blockdefs.ts, additive): `pl_hunt_take` and
`pl_hunt_step` are laid out in ROWS as every block now is -- the variable and the block (`t =
find_target`), its inputs (`( target=t )`), its time box (`at most 120 s`), then the badge and the run
line on rows of their own (`ownLabelRows`, applied to them as the definitions are) -- and every row
is within the 300-unit budget at 390 (layout.ts's model: the widest is 242 units;
layout.test.ts now checks the hunt box's every tab too).

**The fields converted** (the IR, the Python text and every round trip unchanged: a picker saves the
same value as the plain field it replaces):

| Field | Picker |
|---|---|
| `pl_hunt_take.VAR` | a variable reference (`ref: variable`): the function's inputs first (the loop's `t`), then the tab's, the node's and Global's variables; a typed name that is no variable's is kept |
| `pl_hunt_take.ARGS`, `pl_hunt_step.ARGS` | round 21's inputs picker (`expr` / `args`); a `target` row of find_target / walk_to_target / fight_target / strike / wait_steal / wait_kill / loot is a VARIABLE row (pickers.ts `TARGET_BLOCKS`, `rowKind`), a list of the same variables |
| `pl_action` ARGS of strike / wait_steal / wait_kill / loot | the same: their `target=t` row a variable row |
| `pl_hunt_take.TIMEOUT`, `pl_hunt_step.TIMEOUT` | a stepper 1-600 s (presets 10, 30, 60, 120, 300); the field keeps no min / max, so a loaded time box (e.g. 0.5 s) is never clamped |
| use_skill's `key` row | the DECLARED keys (pickers.ts `skillKeysOn`: the node's hunt core's heal key, as poring_flow.huntloop allows; the hunt box: F1), the key picker of round 21 where the node declares none |

The tests: pickers.test.ts (the variable rows, the declared key, the variable list with `t` first),
layout.test.ts (the hunt box), and huntloop.test.ts / project.test.ts / blockly_headless.test.ts
(the hunt box's round trips, byte for byte, on the merged converter).

**Re-run on the merged tree (a198b384):** the full Python suite 5,873 passed, 94 skipped, 3 failed
-- the three worktree-only ones of 14.9; ruff check and mypy clean; ruff format --check clean but
main's two old files; the frontend's test (487 passed, 1 skipped), typecheck and lint clean;
`huntstate_check.py drive` and `check` rc 0; `hunt_trace.py check --seeds 200` YES on all 223
scenarios; stage5b2_ab's plan and its refusals (test_stage5b2_ab, in-process, no live run) and
stage5b_ab's refusal of the 5b-2 runner as its B (test_stage5b_ab) hold.

➡️ **Main's round 22 (f3898e8b, frontend only) merged too, 2026-11-14 ~22:4x ICT:** two conflicts,
both import lists (layout.test.ts: round 22's wrapExpr in place of round 21's shortExpr, beside the
hunt box; pickers.test.ts: its toViewBox / placement imports beside TARGET_BLOCKS and
xmasHuntProject); argRow, the variable list (`t` first) and the declared key row unchanged. No
Python file changed: the frontend's test (497 passed, 1 skipped), typecheck and lint clean,
layout.test.ts with the hunt box green; the 5b-2 Python tests, `huntstate_check.py drive` and
`check`, and `hunt_trace.py check --seeds 50` (73 scenarios) as before.


### 14.11 Result of s5b2-ab (run 2026-11-15 03:06-05:15 ICT, scored 05:1x): PASS on every line

`stage5b2_ab.py score --label s5b2-ab`: 3 pairs, all 6 runs valid (19.9 min, each ended by its time
box), 0 invalid, 0 deaths. A = the one box on run()'s own driver; B = the hunt box, whose `hunt` tab
plays `t = find_target(); fight_target(t)` through hook.drive.

    run      arm  kills/h loot/h open/h  tick median  p95     drive
    r01A     A    132.9   154.0  138.9    201.5      1021.6    -
    r02B     B    138.8   178.1  117.7    201.5      1038.6    run_end
    r03B     B    132.7   159.8  114.6    201.7       989.6    run_end
    r04A     A    114.7   132.8  114.7    201.8      1003.2    -
    r05A     A    114.8   154.0  123.8    202.2       982.7    -
    r06B     B    169.0   184.1  141.8    201.8      1020.6    run_end

The bar (14.7, with 14.7a's pace line):
- deaths A 0, B 0 -> PASS;
- record kinds: none new in B -> PASS;
- runner errors: none -> PASS;
- openers/h: A 125.8, B 124.7 -> PASS;
- pace: median A 201.8, B 201.7 ms -> PASS; the p95 is reported only: A 999.8, B 1002.2;
- kills/h: paired +5.9, +17.9, +54.2; mean +26.0, SE 14.5 -> PASS;
- loot steps/h: paired +24.0, +27.0, +30.0; mean +27.0, SE 1.7 -> PASS;
- drive: all 3 B runs drove, passed no step, and ended run_end; no A run drove -> PASS.
**VERDICT: PASS.**

**B's extra loot steps are its extra kills, not a different loot program** (checked from the runner
sessions, report-only; the bar is one-sided and already passes):
- A loot step follows each kill:
  - steps per kill: A 1.16 / 1.16 / 1.34, B 1.28 / 1.20 / 1.09;
  - steps with a kill listed: A 39 / 36 / 35, B 46 / 38 / 54;
  - steps with no kill listed: A 28 in all, B 26.
- B killed more in its runs: +2, +6 and +18 a run, which is within noise (+26 +- 14.5 / h). A's two
  lowest runs, r04A and r05A (38 kills each), were the night's back-to-back A runs, 04:1x-04:5x.
- Picks in the loot steps: A 16, B 26.
- So the hunt box plays as the driver does, as the step-trace proof said (14.3). This series is not
  evidence that it plays BETTER.

**What this unlocks:** the canonical hunt loop is proven live, so the hunt tab can become the
ready-made box's (the description blocks of the outline now play). The first real experiment in blocks
is 14.8's (no Knife swap on the Christmas Cookie and the Cookie), with its own pre-registered A/B
against B5b-2. Not started: the next step, and the ready-made box's change, are recorded for Batt.


### 14.12 Batt's decisions on the night report (2026-11-15 ~13:0x ICT, Thai, translated, with two screenshots: main's "hunt with the runner (dungeon_hunt.py)" block and the monsters tab)

1. **No hunt tab in the ready-made box. The runner block goes:** "Not dungeon_hunt.py like this: make it functions in separate tabs. dungeon_hunt.py should be blocks the user sees and can edit himself." So:
   - the opaque "hunt with the runner (dungeon_hunt.py)" block in main is dissolved into FUNCTIONS in tabs, blocks a person sees and edits;
   - this is stage 5c (section 15). It is designed first, then built, proven offline, and A/B'd live against B5b-2.
2. **14.8's experiment:** "Test it, and make it work too." No Knife swap on the Christmas Cookie and the Cookie, as a pre-registered live A/B (section 16). The no-swap recipes must be shown to play.
3. **5b-1:** "I accept your decision" (13.7). No re-run.
4. **The Goblin class:** "Allowed." A fresh held-out recording with staged knights is allowed, with the rule change pre-registered first (xmas02-detector S5).
5. **The rm of the archived RAM copies:** "Delegated to you." Done 13:0x after re-checking each copy on the NAS: 24 + 31 session folders and the 5b series folders; /dev/shm 890 -> 679 MB.
6. **The block layout** (two new asks):
   - (a) when a tab holds several functions and there is room to the right, lay them out LEFT TO RIGHT, as the monsters tab does, so a person sees every function without scrolling;
   - (b) "most important": /flows and /maps must REMEMBER where a person placed blocks and nodes. Today a refresh forgets the last drag.
   - Both are round 25 (12.9).

## 15. Stage 5c: the runner block dissolves into functions in tabs (design written 2026-11-15 13:17 ICT from `date`, BEFORE any 5c code; offline only; ➡️ BUILT 13:2x-13:5x ICT, feat/runner-blocks, NOT run live: 15.11)

**Batt (2026-11-15 ~13:0x, 14.12 item 1):** "Not dungeon_hunt.py like this: make it functions in
separate tabs. dungeon_hunt.py should be blocks the user sees and can edit himself." So the opaque
"hunt with the runner (dungeon_hunt.py)" block leaves the ready-made box's main. What it held --
the roles (which function is heal, the Fly Wing, ...), the loop and the tick -- becomes blocks in
tabs a person sees and edits; the runner's settings are already blocks (5a). Nothing of the hunt
plays differently: the canonical new box compiles to EXACTLY the hunt box's hunt core (5b-2, proven
live in 14.11), so its live A/B (15.8) is an equivalence check again.

### 15.1 The new box (what a person sees)

    # tab main
    assert_save_point(cell("geffen", 119, 40))
    use_model("xmas02")
    hunt_loop()                 # the hunt core: it starts HERE and plays the tab hunt's loop
    stop("home")

    # tab hunt: the hunt core's ROLES (one block each, a picker of the node's functions), its loop
    role_heal = "heal"                  # heal:       [heal ▾]
    role_fly = "fly_wing"               # Fly Wing:   [fly_wing ▾]
    role_knife_on = "knife_on"          # Knife on:   [knife_on ▾]
    role_knife_back = "knife_back"      # Knife off:  [knife_back ▾]
    role_home = "fly_home"              # home:       [fly_home ▾]
    role_respawn = "respawn_button"     # died:       [respawn_button ▾]
    role_respawn_confirm = "respawn_ok" # confirm:    [respawn_ok ▾]
    role_eat = "eat"                    # eat:        [eat ▾]
    def hunt_loop(t=False):             # t: the target (none until find_target finds one)
        while True:
            t = find_target()
            fight_target(t)

    # tab tick: every tick of the hunt core, in run()'s order -- each a block, its class shown
    # (➡️ BUILT as def hunt_tick(): a tab cannot share a function's name -- 15.11)
    def tick():
        step_begin(); step_sense(); step_hook(); step_vitals(); step_battle_log(); step_survive()
        step_engage(); step_ui(); step_upkeep()                       # SAFETY: every tick
        step_fight(); step_hold(); step_loot(); step_after(); step_ready(); step_rest()
        step_idle(); step_plant(); step_search(); step_position(); step_pace()

keys, survival, knife, exits, monsters and the setting tabs stay as they are (their blocks
unchanged). Why each name:
- **`hunt_loop()`**: `hunt` is a catalogue block (Amendment A's hunt), so a function cannot be named
  so (the names rule). It is 5b-2's loop function, now CALLED: the call is where the hunt core
  starts. Its one input t takes a default (`t=False`) so main can call it with none; the player
  binds t to none either way (14.2 #2).
- **`role_<param>`**: one variable per role of the old block (dungeon_hunt's parameters: heal, fly,
  knife_on, knife_back, home, respawn, respawn_confirm, eat), its value the function's name, shown
  as a ROLE BLOCK with round 21's role picker (the functions of the node and Global, the usual one
  first) -- the old block's rows, each now a block of its own. An optional role (home, respawn,
  respawn_confirm, eat) is absent when its block is deleted, as an empty field was.
- **`step_<name>()`**: run()'s step closures are `step_<name>`; a bare `fight`, `loot`, `search`
  ... is a catalogue name, a setting or a function name flows already use.

### 15.2 How the engine recognises the hunt core without the runner block

**A map node whose main calls `hunt_loop()` (at its top level, no arguments) has its hunt core
there.** The compiler LOWERS that shape before anything else reads it (`poring_flow.project`:
`compile_project` -> `lower_hunt_core`): the call becomes the hunt core's action at that place,
`dungeon_hunt(heal=<role_heal>, fly=<role_fly>, ...)`, its parameters the node's role blocks. The
IR is then exactly the one the hunt box (5b-2) compiles to: the player, the live set, the plan, the
keys, the settings, the recipes, the lint, the backend and the Run helper read it unchanged, and
`hunt_loop` drives the steps as in 5b-2 (`hook.drive`). The lowering touches only the compiled
flow: the project, its Python view and its blocks keep `hunt_loop()` and the role blocks. A node
WITH the runner block is not lowered (old projects, the frozen fixtures, the 5b-2 hunt box: played
exactly as before).

Refused before any input (the lint's errors; the backend's `not_live` says the same through
`live.problems`):
- `hunt_core_call`: `hunt_loop()` called anywhere but a map node's main's top level, with
  arguments, twice, or on a node that also holds the runner block (one hunt core a node);
- `hunt_roles`: a lowered hunt core without its four required roles (heal, Fly Wing, Knife on,
  Knife off): "its role block heal: names the function the runner presses to heal" -- and every
  rule the runner block's roles had (one press_key each, distinct keys, the bodies of stage 3) still
  applies, through the lowered action;
- `role_block`: a role block on a node whose main does not call `hunt_loop()` (a warning: it is not
  read).
Words name the role block or the call, never "dungeon_hunt". The places a lowered rule points at
are the call's (its main's statement); 15.9 says so as a limit.

### 15.3 The tick made visible

Today the cursor runs the 20 steps implicitly. In 5c the node's function `tick()` (➡️ built as
`hunt_tick()`, 15.11; tab `tick`)
LISTS them, one block each, in run()'s order, each with its words and its CLASS:

| Class | Steps | The rule |
|---|---|---|
| SAFETY | begin (the tick's clock, the Run's Stop), sense (HP, SP, the position, stock out, the jump guard), hook (the box's own tick: its Stop, its events), vitals (death), battle_log (hits, kills, a boss line's Fly Wing), survive (the potion, the Fly Wing, Auto Guard), engage (a fight begins, the Garm Baby alarm, the boss guard), ui (the UI watch's hard bar on an unknown UI, the weight home), upkeep (the Knife's HP floor, overweight, the HUD), idle (stuck: uncarve or a Fly Wing), position (an unread position's Fly Wing; 30 s unread ends the run) | cannot be left out or moved: an ERROR naming the step and what it protects |
| REQUIRED | fight (the fight itself), hold (a lock waits: no walk while a target is held), after (a fight's end becomes search or rest), rest (a rest the after step decides is played), search (the walk), pace (the tick's 200 ms) | cannot be left out or moved: an ERROR ("without it the hunt cannot go on: ...") |
| OPTIONAL | loot (the loot step after a fight), ready (the Knife put on while idle; the queue's next target), plant (the White Plant sweep) | may be LEFT OUT: the runner then never plays it (the cursor passes it, counted as `left_out`); its place stays fixed |

Why the classes: every common step protects her or the run (13.2's table): leaving one out would
blind the runner (sense, battle_log), mute a Stop (begin, hook) or drop an escape (survive, engage,
ui's hard bar, upkeep's HP floor, idle, position). Of the mode steps, fight, hold, after, rest,
search and pace carry the loop's own mechanics (without hold a held target is walked away from;
without after a fight never ends; without rest a decided rest freezes her in mode rest; without
pace the tick spins); loot, ready and plant are plays a person may well not want (14.8's "no loot"
is exactly such an edit, for every monster). **No step may be MOVED**: the order is run()'s, and the
cursor's hand-back points (before fight, before after) and its guards rely on it.

What the blocks show and own: the tick tab is the TICK; the hunt loop's blocks are who plays which
mode steps (15.4), so each mode step's block says its owner ("played while find_target plays").
The common steps run on every tick whichever block plays (5b-2).

A node without a `tick()` plays the full tick (all 20: the default, as 5b-2). A `tick()` is read
only where a hunt loop drives (refused elsewhere: `tick_place`), and holds nothing but step blocks
(`tick_step`); the step blocks stand nowhere else; nobody calls `tick()`. **Open question for Batt
(15.10): may a person leave out a SAFETY step?** The safe default is built: no.

The runner checks the same set at run time: the cursor's `leave_out(names)` takes only the OPTIONAL
steps (`dungeon_hunt.DRIVE_OPTIONAL_STEPS`) and refuses any other (the drive is then refused, its
reason named), so a lint gap cannot leave a safety step out.

### 15.4 The bounds and the canonical form

Nothing of 14.2 changes: each block is one bounded call (its timeout_s), hands back only before the
fight or the after step, at the run's end or on Stop; the canonical loop (`t = find_target();
fight_target(t)`) with the full tick calls exactly the driver's step sequence. A left-out step is
the only new difference, and only where a person writes it.

### 15.5 Which runner settings and flags stay

All of 5a's setting blocks, unchanged, in their tabs; the runner's fixed part (`flow_run.FIXED`)
and the flow's flags unchanged; the five hotbar keys still come from the role functions
(`runner_keys`, through the lowered action). So the new box gives the hunt box's runner argv
exactly (and the one box's: the pinned 97 arguments), and run() the same arguments (`box_kwargs`).

### 15.6 The ready-made box and the old shapes

- **The ready-made box** (what /flows and /maps load) becomes the new shape:
  `fixtures/project_xmas_dun02_functions.json` = `xmasFunctionsProject()` (byte-identical
  canonical): the one box's tabs, its main as 15.1, plus the tabs hunt and tick.
- **The old one-box shape stays** `fixtures/project_xmas_dun02.json` = `xmasProject()` (the runner
  block; its argv pinned; every stage tool and test that names it keeps it), and the hunt box
  `project_xmas_dun02_hunt.json` (5b-2's B), and the frozen stage arms. A saved project with the
  runner block loads, lints and runs as today (it is never lowered).
- The editor offers the new shape: a `hunt_loop()` call in a map node's main, the role blocks and
  the hunt loop on a tab named `hunt`, the step blocks on a tab named `tick`; the runner block stays
  offered for an old project.

### 15.7 The proofs

- **The canonical new box = the hunt box's hunt core**: its compiled flow equals the hunt box's but
  for the hunt loop's default (`t=False`) and the tick function, and `prepare` gives the same runner
  argv, keys, settings and run() arguments (tests, and stage5c_ab's plan refuses otherwise).
- **The canonical form = the driver's steps**: hunt_trace.py's check runs the new box too, with its
  full tick; a variant with loot left out PASSES the loot step and differs (the edit plays; the
  harness names it).
- **No drive = 5b-1** (huntstate_check.py drive): the runner's new names are in DRIVE_ADDED; run()
  without its drive branch is still 5b-1's.
- **The refusals**: each rule of 15.2 / 15.3 has a test that names it, the lint and live.problems
  alike; the runner's own refusal of a non-optional left-out step has a test.

### 15.8 THE A/B of 5c -- pre-registered 2026-11-15 13:17 ICT from `date`, BEFORE any 5c run

**The arms differ ONLY in the box's shape** (`scripts/stage5c_ab.py`, stage5b2_ab's pattern; the
checkout's runner for both, the same settings):
- **A = B5b-2**: `project_xmas_dun02_hunt.json` (the runner block, the hunt tab: proven in 14.11);
- **B = B5c**: `project_xmas_dun02_functions.json` (`hunt_loop()` in main, the role blocks, the full
  tick).

`plan` refuses before any input unless the two boxes give the same runner settings, keys, argv and
run() arguments; both drive the canonical loop and B's tick leaves nothing out; B differs from A
only in main's hunt statement, the hunt tab's role blocks and loop default, the tick tab, the name
and the description; huntstate_check drive holds; and the step traces equal the driver's on every
hand scenario and 50 random ones, for both boxes.

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage5c_ab.py plan  --label s5c-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5c_ab.py run   --label s5c-ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage5c_ab.py score --label s5c-ab

3 pairs of 20 min, order A B, B A, A B; stage2_ab's setup before every run; a STOP file ends the
series before its next run. **THE PRE-REGISTERED BAR** (`stage5c_ab.BAR`) -- 14.7's lines with
14.7a's pace line, and the drive line for BOTH arms:

| Line | B must hold |
|---|---|
| deaths | B's deaths <= A's, over EVERY run that played (>= 1 min, or a death) |
| kills per hour | the mean paired difference (B - A) >= -2 x its standard error, over at least 3 valid pairs |
| loot steps per hour | the same rule |
| Knife openers per hour | B's series rate within +-20 % of A's (valid runs pooled) |
| the tick pace | B's MEDIAN gap between hp_read records <= A's + 5 ms (valid runs pooled); the p95 reported only (14.7a) |
| no new record kind | every record kind B's runner sessions write is one the 5b-1 runner's source writes, one A's sessions wrote, or the drive's own |
| no runner error | no B run ends by an exception of the runner |
| the drive | every run of EITHER arm that played drove (one drive start and end in its runner session), passed no step, left none out, and its drive ended as the run did (time_box / run_end) |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: potions / h, Fly Wings / h, steals / h, eats / h, the lowest HP, the end
reasons, each record kind's rate per hour per arm. FAIL when a judged line fails; INCONCLUSIVE when
fewer than 3 pairs are valid (kills and loot unjudged) and nothing failed; else PASS. Why: B is the
same hunt core by construction (15.7), so the rates are held to the pairs' own noise, as in 14.7; no
line is a strict "<" against an arm that may read 0.

### 15.9 Limits (what 5c does not do)

- The tick's SAFETY and REQUIRED steps are visible, not editable (15.3; Batt's open question). ➡️ Round 26 (12.10): the editor now LOCKS them too (no delete, no drag out), until Batt answers.
- What a step DOES inside stays the runner's code: a step block names a step of run(), it does not
  open its body (its words and tooltip say what it does).
- A lint finding on a role (one press_key, distinct keys, a body's caps) points at the
  `hunt_loop()` call (the lowered action's place), not at the role block (its words name the role).
- The hunt loop's language is 5b-2's (14.2 #11).

### 15.10 Open questions for Batt

1. May a person leave out (or move) a SAFETY step of the tick, e.g. the UI watch's weight home? The
   built default: no (an error naming what it protects); the runner refuses it too.
2. Should the old runner block leave the toolbox (it stays offered for old projects today)?

➡️ **The reviewer's view on Q1 and Q2 was given (the 5c review, 2026-11-15; 12.10): Batt decides.**
Until he answers, the editor matches the built defaults (the parent's decision): Q1 -- a SAFETY or
REQUIRED step is LOCKED in the editor (cannot be deleted or dragged out of hunt_tick(); a padlock
and a colour per class), the lint and the runner still refuse it; Q2 -- the old runner block stays
for old projects, in Advanced > Old projects ("the old one-block runner (old projects)"), so a fresh
box meets hunt_loop() first.

### 15.11 ➡️ BUILT (2026-11-15 13:2x-13:5x ICT from `date` and the commits; feat/runner-blocks, from main 09d5e6fb; offline only, NOT run live)

What changed from the design, each for a reason the build found:
- **The tick's function is `hunt_tick()`**, not `tick()` (15.1, 15.3 carry pointers): its tab is
  `tick`, and a tab cannot share a function's name (the project's names rule refused the box).
- **Role blocks are shown in the old runner block's order of rows** (heal ... eat), whatever order
  the file holds them in (a saved file sorts its keys): the Python view prints them as variables.
- **The ready-made box /flows and /maps open first is the new shape** (xmasFunctionsProject(); the
  menu's "xmas_dun02"); the old one-box shape is the menu's "xmas_dun02_runner" (xmasProject(), the
  runner block), the hunt box stays "xmas_dun02_hunt". A browser's saved project loads as before.
- **The hunt loop's def is offered as `def hunt_loop(t=False)`** in the toolbox: it serves both
  shapes (the runner block's hunt core takes a default too; hunt_loop_input allows it).

What was built:
- The engine (3d438b51): `poring_flow.tick` (the table: run()'s 20 steps, their class, words, why,
  owner); `lint/tick.py` (tick_step, tick_place); `huntloop` (HUNT_CALL, the role blocks,
  hunt_core_call, hunt_roles, role_block; hunt_loop_input takes a default); `project.lower_hunt_core`
  (compile_project lowers first; lowered_nodes, role_values); live.problems and the HuntPlan carry
  the tick (tick_left_out); 20 step blocks in blocks.yaml (core.tick_step, live: true).
- The runner and the player (3d438b51): RUNNER_BLOCKS_VERSION 9.56; DRIVE_OPTIONAL_STEPS;
  `HuntCursor.leave_out` (only those; a left-out step is never played, traced `left_out`, counted
  in its drive end); flow_play hands the plan's left-out steps to the cursor and refuses the drive
  in words when the runner does not take them; flow_run sees the new shape's hunt core.
- The browser (ec742096): lib/flow/tick.ts (the table; pinned to the engine by
  test_runner_functions.py); the role blocks pl_role_<param> (a role picker each, round 21) and the
  step blocks pl_step_<name> (their class and words on rows inside the 300-unit budget); their
  converters; the toolbox (hunt_loop() in a map's main, Roles on the tab hunt, Tick on the tab tick
  -- ➡️ the page never showed it until round 27, 12.11: the catalogue's core step blocks were
  filtered out; now "Tick steps";
  never under More skills); runnerBlockOn BUILDS the runner block a main's hunt_loop() stands for
  (the keys, use_skill's keys, the home function, Run's readiness, the pages); the fixture's TS
  twin.
- The A/B tool (3d438b51): scripts/stage5c_ab.py, 15.8's bar exactly (stage5c_ab.BAR).

What a person sees and may change (and what the lint refuses, the backend's not_live alike):

| Where | They see | They may change | Refused (rule) |
|---|---|---|---|
| main | `hunt_loop()` where the runner block stood | where it stands among main's statements | a second call, a call with inputs, a call outside a map's main's top level, beside a runner block (hunt_core_call) |
| tab hunt | a role block per role (heal ... eat), each a picker of the node's and Global's functions; the loop | any role's function; delete an optional role (home, died, confirm, eat); the loop as 5b-2 | a required role missing (hunt_roles: "needs its role blocks: heal (role_heal) ..."); a role twice / on two tabs (the editor); role blocks with no hunt core (role_block, a warning) |
| tab tick | `hunt_tick()` and 20 step blocks, each with its class and words, in run()'s order | leave out loot, ready or plant (the runner then never plays it); delete the tab (every step plays) | a SAFETY or REQUIRED step left out (its words: what it protects), a step moved, twice, any other statement, a step block elsewhere, a call of hunt_tick(), a tick where no hunt loop drives (tick_step, tick_place); the runner's cursor refuses a non-optional left-out step too |

The proofs (offline, all green):
- The functions box = the hunt box's hunt core: `prepare` gives the same runner argv, keys, settings
  and run() arguments (test_runner_blocks.py; for the one box too: the pinned argv); its compiled
  flow's hunt plan equals the hunt box's (test_runner_functions.py).
- The canonical form = the driver's steps: hunt_trace.py check runs both boxes (hand scenarios +
  random ones: SAME every one); loot left out differs at the first loot step, named
  ('loot', 'left_out').
- No drive = 5b-1: huntstate_check.py drive (the additions are DRIVE_ADDED, with
  RUNNER_BLOCKS_VERSION and DRIVE_OPTIONAL_STEPS) and check, both rc 0.
- The refusals: one test per rule of 15.2 / 15.3, the lint and live.problems alike
  (test_runner_functions.py); the cursor's own refusal (test_runner_blocks.py); the browser's
  (functions.test.ts).
- The checks (2026-11-15 13:5x-14:2x): hunt_trace.py check --seeds 200, 446 scenarios over both
  boxes, the driver's trace == the hunt loop's in every one; huntstate_check.py drive and check rc 0;
  the full Python suite 5,922 passed, 94 skipped, 3 failed -- the worktree's known three, each a
  gitignored data file a worktree lacks (data/hotbar/digits.npz; the generated map cache, twice);
  ruff check and mypy clean; ruff format clean on every file 5c touches (two files of main's are not:
  docs/setup/new-lab-host.md, services/backend/tests/test_fight_time.py); the frontend's 521 tests
  520 passed, 0 failed (1 skipped), tsc and eslint (the whole tree) clean; stage5c_ab's plan passes
  its refusals in process (no input).

**The A/B is pre-registered (15.8) and built, not run** (the parent runs it; the commands in 15.8).
Open for Batt: 15.10 (a SAFETY step left out; the old runner block in the toolbox).

➡️ **Merged with main 95583b9f (2026-11-15 14:0x-14:3x ICT; round 25's layout and 16's cookie box).**
s5c-ab runs FROM MAIN after 5c merges there: the runner's start check reads gitignored data
(data/hotbar/digits.npz and the like) a worktree lacks. 15.8 is unchanged. What the merge joined:
- Round 25's layout: a role block's key is `var:role_<param>`, hunt_tick's `def:hunt_tick`
  (layout.ts layoutKey); the shelf places the new blocks like any other; a tab's variables keep the
  project's order (round 25), and the role blocks show first in the runner block's order of rows.
  The functions box: no two top blocks of any tab overlap at 313 to 2400 units (layout.test.ts over
  every ready-made and frozen project, and functions.test.ts); a person's places never change the
  engine's project, its lowering or its hash (functions.test.ts; test_project_layout.py over every
  fixture, this one too).
- The READY lists keep every entry: xmas_dun02 (the functions box, the default), xmas_dun02_runner,
  xmas_dun02_hunt, xmas_dun02_cookie_noswap, my_first_project.
- The checks on the merged tree: huntstate_check drive and check rc 0; hunt_trace check --seeds 50,
  146 scenarios, all the same as the driver's; the full Python suite 5,972 passed, 94 skipped, 3
  failed (the worktree's same three); ruff check, mypy clean; ruff format clean but main's same two
  files; the frontend's 532 tests 531 passed, 0 failed (1 skipped), tsc and eslint clean; stage5c_ab's
  plan passes in process (no input); stage6_ab's and the cookie box's tests pass.

### 15.12 Result of s5c-ab (run 2026-11-15 16:13-17:55 ICT, scored 17:55): INCONCLUSIVE -- two of three pairs valid

`stage5c_ab.py score --label s5c-ab`: A = the hunt box (B5b-2), B = the functions box (B5c).

    run       arm  min   death kills/h loot/h open/h  tick median  p95     end
    r01A      A     6.2    1   174.4   164.7  145.3    202.1      1052.7    death
    r02B      B     6.5    1   157.3   185.0  111.0    201.6      1143.1    death
    r03B      B    19.9    0   145.0   172.2  126.9    201.5       980.9    time box
    r04A      A    19.9    0   153.8   165.8  126.6    202.1      1043.0    time box
    r05A      A    19.4    0   142.0   182.1  120.4    201.7      1021.1    weight home (bag_full)
    r06B      B    19.9    0   105.7   148.0  105.7    202.1       978.3    time box

- Pair 1 is invalid: both runs ended by a death in under 80 % of their minutes. So kills/h and loot/h
  are NOT judged (they need >= 3 valid pairs), and the verdict is **INCONCLUSIVE**, as pre-registered.
- The lines that are judged all pass:
  - deaths: A 1, B 1 (B <= A);
  - record kinds: none new;
  - errors: none;
  - openers/h: A 123.5, B 116.3;
  - pace: median A 201.9, B 201.8 ms;
  - drive: every run of both arms drove, passed no step, left none out, and ended run_end.
- Reported only, 2 pairs: kills/h -8.7 and -36.2 (mean -22.5, SE 13.8); loot/h +6.4 and -34.1. The
  low one is r06B, at 105.7 kills/h.
- The equivalence stands on the build's proofs (15.11):
  - the functions box LOWERS to the hunt box's IR, with the same argv, keys, vals, box arguments and
    HuntPlan;
  - the traces are equal on 446 scenarios.
  - The live series could not add its kills line. Whether to re-run it is Batt's (16.8 / the report).

**The two deaths (from the packets; findings, not verdicts):**
- **r01A: the Fly Wing worked, but the Knight met her again.**
  - At -10.6 s the fast alarm (garm, inside a long action) pressed the Fly Wing. use_item_result 601
    ok, then a map_change on xmas_dun02: a random cell on the SAME map.
  - At -0.94 s and -0.47 s the Knight (1251) hit 2,380 and 1,310. The box's fly_away fired at HP 0,
    too late.
- **r02B: the Fly Wing never reached the server.** ➡️ **CORRECTED in 18.1 (2026-11-16): on ONE
  clock (the packets, the backend's input log, the runner's events) there was no 1.4-s delay.** The
  times below mix the runner's death EVENT (written 1.54 s after the death packet) with the packet
  clock: the F5 reached the server 29 ms after its key, both keys came after the first boss line,
  and the F8 came 0.16 s AFTER the death (a dead character sends no item use). The first sighting
  the alarm's own rule counts came 2.2 s before the death, inside box_target's waits.
  - The Knight and 6 Goblins appeared 2.05 s before the death.
  - The runner pressed F5 (its "safety" dagger equip) at -1.42 s, and the box's fly_away pressed F8 at
    -1.21 s (sees_boss: Christmas Goblin).
  - The server got the EQUIP only at -0.02 s, 1.4 s late, and NO use_item_request.
  - HP 4,323 went to 0 in one hit that is not an `act` packet: a skill.
  - The F5 equip queued in the client seems to have held up the Fly Wing.
- **Candidates for a next, pre-registered step (not built):**
  - when a boss is seen, press the Fly Wing FIRST, with no safety equip before it;
  - after a Knight escape by Fly Wing, leave the MAP (the Butterfly Wing home) instead of staying on
    it.

### 15.13 THE RE-RUN s5c-ab2 -- pre-registered 2026-11-16 10:3x ICT from `date`, BEFORE any of its data (Batt 2026-11-16: "test it again")

- **What:** the same arms and the same bar as 15.8 (14.7's lines, 14.7a's median pace line, the
  drive line for both arms), the same tool:
  `stage5c_ab.py run --label s5c-ab2 --pairs 4 --minutes 20` (order alternate: A B, B A, A B, B A).
- **The one change, decided BEFORE any new data and for a reason that is not an outcome:**
  - **4 pairs instead of 3.** s5c-ab lost a pair to two Knight deaths, and the Knight still roams in
    player mode. The verdict is judged on every valid pair, with >= 3 valid pairs needed for
    kills/h and loot/h, as before. A 4th pair only makes 3 valid pairs likelier. No pair is dropped
    or added after the run.
  - **s5c-ab stays scored as it was:** INCONCLUSIVE (15.12). s5c-ab2 is scored on its own, never
    pooled with it.
- **The runner:** today's main. Batt's decision 6 (Fly Wing first on a boss) is NOT in it yet; it
  is its own step (section 17). Both arms play the same runner.
- **The economy** of every run is recorded in data/econ/lab.sqlite (Batt 2026-11-16: "collect the
  economy every run"), report only.

### 15.14 Result of s5c-ab2 (run 2026-11-16 10:35-13:22 ICT, scored 13:23): PASS on every line

`stage5c_ab.py score --label s5c-ab2`: 4 pairs, all 8 runs valid (19.9-20.0 min, each ended by its time
box), 0 deaths. A = the hunt box (runner block + hunt tab), B = the functions box (hunt_loop()).

    run        arm  kills/h loot/h open/h  tick median  p95
    r01A       A    157.1   181.3  142.0    201.7      1011.6
    r02B       B    163.2   193.4  133.0    201.7      1082.3
    r03B       B    141.6   192.9  111.5    202.2      1038.8
    r04A       A     96.5   141.7  111.6    202.9      1010.1
    r05A       A    139.0   163.2  120.9    201.6      1000.3
    r06B       B    132.8   166.0  120.7    201.7       981.1
    r07B       B    165.1   198.2  123.1    201.6      1032.0
    r08A       A    142.1   157.2  126.9    201.7       958.2

The bar (15.8, with 15.13's 4 pairs):
- deaths 0 / 0 -> PASS;
- record kinds: none new -> PASS;
- errors: none -> PASS;
- openers/h: A 125.3, B 122.1 -> PASS;
- pace: median A 201.9, B 201.8 ms -> PASS; the p95 reported only (990.4 / 1020.8);
- kills/h: paired +6.0, +45.2, -6.2, +23.1; mean +17.0, SE 11.1 -> PASS;
- loot/h: paired +12.1, +51.2, +2.8, +41.0; mean +26.8, SE 11.5 -> PASS;
- drive: every run of both arms drove cleanly -> PASS.
**VERDICT: PASS.**
- **The functions shape plays as the hunt box does, live.** The positive differences are within
  noise, led by A's low r04A (96.5 kills/h). They are not a claim that B plays better.
- **The economy** (17 #7; data/econ dashboard xmas02-1116-s5c-ab2), net z/h: A 50,205, B 49,367.
  Equal.

## 16. The first real experiment in blocks: no Knife swap on the Christmas Cookie and the Cookie (➡️ BUILT 2026-11-15, feat/cookie-noswap; offline only, NOT run live; its A/B pre-registered 2026-11-15 13:32 ICT from `date`, BEFORE any run)

Batt's words (14.12 #2, 2026-11-15 ~13:0x): "Test it, and make it work too." The experiment is 14.8's
first one. The Christmas Cookie and the Cookie are fought WITHOUT the Knife swap, because they carry
no steal worth the swap's time (2b). On every other monster the Rogue keeps Batt's technique: the
Knife opener steals, then the dagger (Damascus) strikes.

### 16.1 The box (arm C) and how it differs

- **The fixture:** `services/frontend/src/lib/flow/fixtures/project_xmas_dun02_cookie_noswap.json`
  (name `xmas_dun02_cookie_noswap`). It is the one box (`project_xmas_dun02.json`) with
  `attack_cookie` and `attack_cookie_xmas` cut to `strike(t); wait_kill(t); loot(t)` (4a's plain
  shape). The three statements are the one box's own, byte for byte, and `priority=1` is kept.
  Everything else is the one box but the name and the description. `stage6_ab.box_difference`
  checks this.
- **Its TS twin** is `xmasCookieNoSwapProject()` (project.ts); `project.test.ts` checks it byte for
  byte against the fixture, as it checks the other ready-made boxes.
- **Loading it:** the /maps Load list offers it ("xmas_dun02_cookie_noswap"). /flows has it in its
  ready-made table, like the hunt box, but no menu item of its own. A person loads it on /maps,
  where Run is, and Runs it from START.
- **Checked offline** (test_cookie_noswap.py):
  - the lint finds 0 errors and the one box's four warnings;
  - `live.problems` is empty: the backend's `not_live` check passes;
  - the Run keys are the one box's five;
  - `flow_play.prepare` gives the same runner argv and the same run() arguments as the one box,
    except `box_recipes`: cookie / cookie_xmas `[strike, wait_kill, loot]` knife false, mystcase /
    cruiser the Knife swap, every priority 1;
  - the runner's own start check (`dungeon_hunt.box_plays_refused` / `recipes_refused`) accepts
    both boxes with the Run config (`knife_swap`, `bare_ready`, `value_target` on).
- **What the Run route checks that this does not cover:** the zones file and the run-start
  verdict on the lab's static data. Those read the map node's zones and the KB, which the two
  recipe bodies do not touch, so they are the one box's.

### 16.2 The recipes PLAY as written (offline proof)

The proof uses the runner's own `BareCtl` on test_dungeon_hunt's simulated client with the Run
config's Knife: the opener on F4 through the box's knife_on, the dagger on F5 through knife_back,
--bare-ready and the popup cue. The REAL player's hook, prepared from the fixture, answers at the
lock. The wiring is run()'s: test_box_recipes checks it by AST, and test_cookie_noswap checks run()'s
`recipe` record against its source.

| At a lock on | With the Knife on (--bare-ready, the Run config) | With the dagger on (armed) |
|---|---|---|
| cookie / cookie_xmas (C) | the dagger FIRST (`box knife_back (recipe)`), its aim read again, then nothing: no opener, no swap back on the steal's popup, none at the Knife's 8 s time box. The next idle moment puts the Knife on again (`box knife_on (ready)`) | no press at all |
| mystcase / cruiser (C) | struck bare at once (no press), the dagger back on the steal's popup: a steal, as today | the opener AT the strike, then the dagger on the popup |
| cookie (B, the one box) | struck bare at once, the dagger back on the popup: the counter's positive case | - |

- **A negative control:** a hook answer that is not C's plan makes the runner play its own recipe,
  the swap. The reader then names that lock a Knife try, which fails C's plays line.
- **Three things to know about the no-swap play** (the runner's code, unchanged):
  - **The swaps per cookie lock stay two.**
    - C: the dagger first, then the Knife at the next idle.
    - B: the dagger on the steal's cue or the 8 s time box, then the Knife at the next idle.
    - What C removes is the BARE PHASE: B fights a cookie with the Knife first. In s5b1-ab and
      s5b2-ab's 12 runs that phase lasted a median 5.7 s on a Cookie (n 37) and 4.8 s on a
      Christmas Cookie (n 50); it ended on the popup 22 / 38 times and on the time box 12 / 8 times.
    - C instead waits for the dagger's read-back first (a median 342 ms over 506 swaps) and the aim
      read again.
  - **A re-lock costs C the swap again.** A cookie unlocked without a kill ("no hits") and locked
    again gets the dagger first again, because the Knife went back on at the idle moment between.
    B stays bare between those locks.
  - **Strikes that know no species keep the swap in both arms.** The ring scan and a walk or loot
    SWORD strike play the runner's own recipe (3.4's known limit). They were 29 % of the locks in
    those 12 runs (60.4 of 205.6 an hour). So C's cookies still get the Knife when such a strike
    finds them first, and the effect is diluted.

### 16.3 The records the score counts, by the species at the lock

A LOCK is one `recipe` record (run()'s `recipe_knife`): the species of the box it struck ("?" when
the strike knew none), the answer (`knife`) and `mismatch`. The runner's records up to the next lock
belong to it:
- **a Knife strike:** `bare` `begin` ok (--bare-ready: already bare, the phase begins there), or
  `bare` `opener` / `unequip` AT the strike. The idle swap (`by` "ready") is nobody's: with
  --bare-ready the opener goes on before any species is known;
- **a Knife TRY:** the same, a failed opener included;
- **the no-knife play:** `bare` `recipe` with `knife` false, the runner's own record
  (`BareCtl._no_knife`). `swap` true means the dagger went on first;
- **a steal:** `bare` `equip` ok on the steal's cue (`popup` / `cyan`);
- **the kills** after the lock, and the seconds from the lock to the first of them.

**The reader's positive case on REAL sessions:** the 12 runs of s5b1-ab and s5b2-ab (3.98 h, the
Knife swap on every lock; archived on the NAS, scratch-archive/2026-11-15/5b-series):
- every lock of every species read as a Knife strike: 148 cookie / cookie_xmas locks, 148 Knife
  strikes, 0 no-knife plays;
- the steals attributed to a lock: 353 of 353; the kills: 555 of 555;
- mismatches: 0.

C has no real session yet. Its positive case is the offline BareCtl run of 16.2, read by the same
reader.

### 16.4 The tool

`scripts/stage6_ab.py` follows stage5_ab's pattern, with stage2_ab's setup, detect server and run,
and stage5b_ab's score lines. Run by the parent; NOT run yet:

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage6_ab.py plan  --label s6ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage6_ab.py run   --label s6ab --pairs 3 --minutes 20
    .venv/bin/python scripts/stage6_ab.py score --label s6ab

- **The series:** 3 pairs of 20 min, order B C, C B, B C. stage2_ab's setup runs before every run.
  A STOP file in /dev/shm/poring-lab-tmp/stage6-ab/<label>/ ends the series before its next run.
- **Before it:** merged and deployed (the backend, the Run helper); ASSIST; the Rogue in the game;
  the Run helper idle; no chain.
- **The arms:**
  - B = the one box (`project_xmas_dun02.json`);
  - C = the no-swap box.
  - Both play the checkout's runner on run()'s own driver. 14.8 named B5b-2 (the hunt box) as the
    base; Batt's 14.12 #1 keeps the hunt tab out of the ready-made box, and 14.11 showed the hunt
    loop plays as the driver does. So the base is the box a person loads.
- **`plan` refuses before any input** unless:
  - the two boxes differ only in the two recipes' bodies;
  - they take the same settings and keys, and the fast alarm is on;
  - neither has a hunt loop;
  - they give the same runner argv and the same run() arguments but box_recipes;
  - B's four recipes are the Knife swap, C's two cookies the plain shape and its other two B's own,
    every priority 1;
  - the runner's `recipes_refused` accepts both with this Run config.

### 16.5 THE PRE-REGISTERED BAR (`stage6_ab.BAR`, 2026-11-15 13:32 ICT, BEFORE any live data)

C must hold, against B:

| Line | C must hold |
|---|---|
| plays | over EVERY run that played: C TRIED the Knife on no cookie / cookie_xmas lock (0), and played its no-swap recipe (the runner's own record) on at least 5 of them; B struck at least 1 with the Knife (the counter sees one); no lock's answer was not its arm's plan (recipe_mismatch 0, both arms) |
| deaths | C's deaths <= B's, over EVERY run that played (>= 1 min, or a death) |
| kills per hour | the mean paired (C - B) >= -2 x its standard error, over at least 3 valid pairs (non-inferiority: the swap's time saved must not cost kills) |
| the other monsters | C's Knife strikes per hour at mystcase + cruiser locks within +-25 % of B's (valid runs pooled) |
| the tick pace | C's MEDIAN gap between hp_read records <= B's + 5 ms (valid runs pooled; 14.7a's rule; the p95 is reported) |
| no runner error | no C run ends by an exception of the runner (a traceback in its log, or hunt_end `error` that is not a refusal); B's are reported |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

- **The verdict:** FAIL when a judged line fails. INCONCLUSIVE when a line cannot be judged: fewer
  than 3 valid pairs for kills, no valid run in an arm, or an arm that never played for plays.
  PASS otherwise.
- **Adjusted from the brief, each with its reason:**
  1. **"Knife openers on cookie locks" is counted as Knife TRIES.** A failed opener counts too,
     which is stricter. With --bare-ready the opener key goes on while idle, before a species is
     known, so the per-species Knife is the lock's Knife STRIKE (16.3).
  2. **"C fought at least 5 cookie locks" counts the runner's own no-knife record**, not only the
     recipe asked: that record is what shows the recipe PLAYED.
  3. **recipe_mismatch 0 is part of the plays line.** A mismatch plays the runner's own swap; in C
     the Knife try would show it, in B nothing would.
  4. **The errors line judges C** (the changed arm) and reports B's, as 13.5's line judged its new
     arm.
- **The +-25 % on the other monsters, derived from s5b1-ab / s5b2-ab's 12 runs** (the same technique
  on every run):
  - Knife strikes at mystcase + cruiser locks: a mean 107.9 an hour per run, SD 17.9;
  - the per-run CV is 16.6 % overall and 15.1 % within a series (Poisson for ~36 counts a run:
    16.7 %);
  - the relative SE of the ratio of two 3-run pooled arms is sqrt(2) x CV / sqrt(3) = 12.3 %, so
    2 SE = 24.7 %;
  - the two equal-program series' arm ratios read 1.04 and 1.18.
  - C may legitimately see a few % more locks of the other species (less time on cookies), well
    inside the band.
- **No line is a strict "<" against an arm that can read 0** (10.2's lesson): deaths are "<=", and
  B's positive case is ">= 1". The pace tolerance comes from the measured noise of the same
  statistic (13.7's lesson).

### 16.6 Report only, and what the 12 runs say before the series

The score reports, valid runs pooled, per hour and per arm:
- steals by species, and the zeny of the steals lost on the cookies;
- the seconds from a lock to its kill, by species;
- loot steps (and their paired difference);
- kills by species;
- locks, Knife strikes, no-knife plays and dagger-first swaps by species;
- every opener (stage 5's count, the idle ones included);
- potions, Fly Wings, the lowest HP, the end reasons and B's runner errors.

**The zeny:** the score reads data/econ/maps.json at run time (value_target's file: built locally
from the lab server's tables, never committed). One stolen item is valued as drawn in proportion to
its drop rate (cards cannot be stolen): sum(p x sell_oc) / sum(p). Without the file it reports the
counts only.

The 12 runs' reference (B's technique on every lock; the reader's numbers, valid as a baseline, not
as data of this series):

| Species | Locks / h | Steals / h | Steals a lock | Lock -> kill, median s (n) | Value a steal (z, OC) |
|---|---|---|---|---|---|
| cookie | 18.4 | 5.5 | 0.30 | 7.9 (47) | 611 |
| cookie_xmas | 18.9 | 9.6 | 0.51 | 8.7 (55) | 351 |
| mystcase | 64.4 | 27.4 | 0.43 | 11.9 (176) | 928 |
| cruiser | 43.5 | 26.4 | 0.61 | 9.9 (141) | 170 |
| ? (no species) | 60.4 | 19.9 | 0.33 | 7.7 (136) | - |

- **What C gives up:** at those values (every item, the rare ones included) B's cookie steals are
  worth about 6,700 z an hour (5.5 x 611 + 9.6 x 351). Batt's own run, the bar, made 135,737 common-item z / h (rogue-xmas02.md).
- **What C saves:** at most a few seconds of the bare phase on ~37 cookie locks an hour, i.e. 1-3
  minutes an hour. That is a few kills an hour, inside the pairs' noise (s5b2-ab: SE 14.5 kills / h).
  So the kills line tests that the change costs nothing; it cannot show a gain of this size.
- **For Batt to weigh (not judged):** by the lab's own values a Cookie steal (611 z) is worth more
  than a Cruiser's (170 z), because its first drop sells well. The premise "no steal worth the
  swap's time" is what the zeny line measures against the time saved.

### 16.7 Commits, tests, and what stays

- **The commits** (feat/cookie-noswap):
  - 6fbf3f9d: the fixture, its TS twin, the /maps Load entry and /flows' ready-made table,
    project.test.ts;
  - fce18c98: scripts/stage6_ab.py, test_stage6_ab.py (19 cases), test_cookie_noswap.py (10);
  - then this section and docs/console.md.
- **The tests** (2026-11-15, the full suite ended ~13:4x ICT):
  - the full Python suite: 5,914 passed, 94 skipped, 3 failed. The three are exactly the
    worktree-only ones of 14.9 (test_mapcache_paths, test_dungeon_hunt's dagger-worn start check,
    test_patrol_sim's gef_fild10 laps: client data a /dev/shm worktree lacks);
  - ruff check and mypy clean; ruff format --check clean but main's two old files;
  - the frontend's test (513: 512 passed, 1 skipped), typecheck and lint clean;
  - `stage6_ab.py plan --label s6ab --pairs 3 --minutes 20` rc 0, in-process and as a process
    (pure: no input, no folder written).
- **Unchanged:** scripts/dungeon_hunt.py and scripts/flow_play.py. The no-swap recipe plays on the
  recipe path stage 4a built.
- **Not built:** 14.8's next step (no loot(t) for the Christmas Cookie: a new shape in
  recipes.SHAPES).


### 16.8 Result of s6ab (run 2026-11-15 ~14:00-16:10 ICT, scored 16:10): PASS on every line -- and the no-swap box is NOT recommended

`stage6_ab.py score --label s6ab`: 3 pairs, all 6 runs valid (19.8-19.9 min, each ended by its time
box), 0 invalid, 0 deaths. B = the one box (the swap on every monster); C = the cookie no-swap box.

    run       arm  kills/h loot/h  cookie locks (Knife / plain)  steals  others' Knife/h  tick median
    r01B      B    174.9   190.0   14 (14 / 0)                   9       111.6            201.7
    r02C      C    120.9   136.0    9 (0 / 9)                    0        96.7            202.3
    r03C      C    135.9   166.2   17 (0 / 17)                   0        87.6            201.6
    r04B      B    138.8   178.1   17 (17 / 0)                   7        93.6            201.7
    r05B      B    142.0   166.2   11 (11 / 0)                   3       117.8            201.3
    r06C      C    139.0   172.3   14 (0 / 14)                   0        99.7            201.8

The bar (16.5):
- **plays:**
  - C: 40 cookie / cookie_xmas locks, 0 Knife tries, 40 played plain;
  - B: 42 locks, 42 Knife strikes;
  - mismatches 0 / 0;
  -> PASS (Batt's "make it work": the no-swap recipes play live, as written).
- deaths B 0, C 0 -> PASS;
- kills/h: paired -54.0, -2.9, -3.0; mean -20.0, SE 17.0 -> PASS (>= -2 SE);
- other monsters' Knife strikes/h: B 107.7, C 94.7 (within +-25 %) -> PASS;
- pace: median B 201.6, C 201.9 ms -> PASS; p95 reported only (1051.3 / 1022.7);
- errors: none -> PASS.
**VERDICT: PASS**, a non-inferiority bar.

**What it buys, and what it costs** (report only, deciding nothing):
- **Time per cookie kill falls**, lock to kill (median):
  - Cookie 7.95 s (B, n 11) -> 5.99 s (C, n 13);
  - Christmas Cookie 9.52 s (n 18) -> 6.95 s (n 14).
  - About 2-2.6 s a cookie kill.
- **No more kills:** C made 132.0 kills/h against B's 151.9 (paired -20.0 +- 17.0). The point estimate
  is negative, and the time saved (about 2.5 s x ~30 cookie kills/h, about 75 s an hour) is too small
  to show.
- **The steals given up:** B stole cookie 3.0/h and cookie_xmas 16.1/h, about 1,832 + 5,658 = **7,490
  z/h** at the lab's values (Cookie 610.6 z and Christmas Cookie 351.4 z a steal; data/econ). C steals
  none there.
- **Other lines:**
  - loot steps/h: B 178.1, C 158.2;
  - all steals/h: B 94.6, C 71.5;
  - Fly Wings/h: B 5.0, C 10.1;
  - potions/h: 3.0 both;
  - lowest HP: 48 % both.
- **The premise did not hold.** The cookies' steals ARE worth the swap's time: 16.6 predicted it
  from the 12 earlier runs.

**Recommendation (the parent, for Batt):**
- Do NOT make the no-swap box the default: same kills within noise, about 7,500 z/h less.
- Keep it as a loadable example (xmas_dun02_cookie_noswap). It shows that a recipe edit plays live.
  - ➡️ **2026-11-16 (round 29 follow-up, 12.13):** the example on the Load lists is now the
    FUNCTIONS-shape twin (`project_xmas_dun02_functions_cookie_noswap.json`,
    `xmasFunctionsCookieNoSwapProject()`): the ready-made xmas_dun02 with the same two recipes, so
    its Run is a real run. Its words say it is an example, not the default. The one-box file
    measured here stays for stage6_ab's arm C and its sha256 pins, off the lists.
- The next block experiment should target time without giving up steals, e.g. no loot(t) for a
  species whose drops are trimmed anyway (needs recipes.SHAPES widened, 14.8).


## 17. Batt's decisions on the day report (2026-11-16 ~10:2x ICT, Thai, translated)

1. **The SAFETY steps (15.10 Q1):** "Delete, move: it must be editable. If it cannot run, just Undo or
   load the file we saved back."
   - So SAFETY and REQUIRED steps become EDITABLE in the editor: round 26's lock goes.
   - The lint still refuses a Run without them, in its words, and a person undoes or reloads.
   - ➡️ **BUILT 2026-11-16 (round 29, 12.13 item 1; fix/round29).**
2. **The old runner block (15.10 Q2):** "Keep it as a backup, but it is no longer used in real runs:
   only the separate blocks."
   - A RUN of a project whose hunt core is the old one-block runner is refused, in words that point
     to hunt_loop().
   - The block stays loadable, under Advanced > Old projects.
   - The parent's reading: the A/B tools' REFERENCE arms (e.g. 15.13's arm A) are tests of the new
     shape against the old, not real runs, and stay allowed there.
   - ➡️ **BUILT 2026-11-16 (round 29, 12.13 item 2; fix/round29):** the lint (`old_runner`,
     readiness), the check and the Run routes, the Run helper, and the Run button on /flows and
     /maps all refuse it. `flow_play.py` is unchanged, so the A/B reference arms still play.
3. **The cookie no-swap box as the default:** "No." It stays a loadable example (16.8).
4. **5c:** "Test it again." -> 15.13, s5c-ab2.
5. **The Goblin:** "the alarm signal". A per-visit ALARM bar is pre-registered and scored once on a NEW
   held-out with staged knights (xmas02-detector S6); deployment is its own step after it.
6. **The Knight:** "A boss on the screen, at ANY distance: press the Fly Wing first, no Knife swap."
   - It is built as its own pre-registered live A/B. ➡️ Designed and built as **section 18**
     (dungeon@9.57 `--fly-first`, the setting `fly_first`); its A/B s7ab pre-registered in 18.7.
   - The second candidate in 15.12, leaving the map after the escape, was NOT chosen and is not
     built.
7. **New standing ask:** "Every run, collect the economy too."
   - Every live run's session goes into data/econ/lab.sqlite (scripts/econ_db.py update) when it
     ends: the stage A/B series and the Run helper's project runs.
   - The 11-14 / 11-15 runs are back-filled from the NAS archive.
   - ➡️ **The every-run hook BUILT 2026-11-16 (round 29, 12.13 item 3; fix/round29):** the Run
     helper and the A/B series (`econ_db.record_after_run`; economics.md section 10). The
     back-fill is 17.1's.


### 17.1 The economy back-fill (2026-11-16 ~10:3x ICT; Batt's item 7)

- `econ_db.py update` was run over every archived live run of 11-14 and 11-15 (the NAS
  scratch-archive copies): 61 added, 1 already in the file. data/econ/lab.sqlite now holds 113 runs.
- Dashboards for the /economy page (data/econ/dashboard/): xmas02-1114-stage2-4 (30 runs),
  xmas02-1114-s5ab (6), xmas02-1115-s5b1-s5b2 (12), xmas02-1115-s6ab-cookie (6),
  xmas02-1115-s5c-ab (6).
- Net zeny / h per arm, from the dashboards' totals (gross = picked + STOLEN at NPC sell, minus the
  consumables), report only:

      series                   arm   net z/h   stolen  picked
      s5ab (drink 30 vs 50 %)  B4     62,766    106      30
                               B5     36,705    104      30   (cost 12,819 z/h: the 50 % drink)
      s5b1/s5b2                A      49,809    198      52
                               B      50,704    216      66
      s6ab (cookie no-swap)    B      70,527    112      49
                               C      55,205     94      27
      s5c-ab (2 deaths)        A      64,284     87      34
                               B      33,855     70      21

  - **The cookie series agrees with 16.8, and more strongly:** the Knife swap on cookies (B) nets about
    15,300 z/h more than C, because C also picked less.
  - **A correction to the parent's first reading:** an earlier quick read of econ_row's net_h
    (PICKED drops only, no steals) had C ahead. That field leaves Steal / Snatcher income out. The
    dashboard totals above are the ones to use.
  - **Every series is below Batt's 100,000 z/h goal**: 34k-71k net. Batt's own benchmark run was
    135,737 common z/h (memory: batt-benchmark-knife-swap).

## 18. The Fly Wing FIRST on a boss, at any distance (Batt 17 #6; design written 2026-11-16 10:51 ICT from `date`, BEFORE any code; offline only)

**Batt (2026-11-16 ~10:2x, 17 item 6, Thai, translated):** "A boss on the screen, at ANY distance:
press the Fly Wing first, no Knife swap." It is built as its own pre-registered live A/B (18.7).

### 18.1 What the two deaths of s5c-ab show (the packets, the backend's input log and the runner's events, on ONE clock)

The host's CLOCK_MONOTONIC is shared by the sniffer (`t_mono_ns`), the backend's input log (when
it accepted each key, and the runner's own send time) and the runner's events (`t_ns`, written
AFTER the key's batch returned: a median 158 ms after its key down, 2,100 presses). Times below are
from the death packet (her own `entity_vanish`, reason 1) = 0.

- **r02B** (s5c-ab, the functions box):
  - The Stormy Knight came into view at -7.7 s, 13 cells away; 6 Christmas Goblins at -3.9 s.
  - -3.26 s: the runner engaged a box (a Christmas Cookie) and sat in `box_target`'s settle sleep and
    still wait (1,592 ms + 1,585 ms, to -1.27 s). Neither reads the Garm Baby alarm: 9.53's inside
    read is guard_tick's, which scans, strikes, the steal and the hold call, but not these waits.
  - In that wait the HUD twin boxed `garm_baby` at -2.21 s (score 0.74, above --alarm-solo 0.7) and
    -1.97 s (0.50: two detections in a row = --garm-confirm 2). **A sighting by the runner's own rule,
    2.2 s before the death.** It was gone (an empty detection) at -1.72 s, before the loop read it.
  - -1.17 s: the opener (the Knife, F4), -1.11 s the strike; the Goblins' first hits at -0.80 s.
  - The first boss line in the Battle Log (a Goblin's 94) was read at -0.28 s: the box's fly_away
    fired. The backend accepted a ReleaseAll at -0.103 s (the pre-empt's), **F5 down at -0.050 s**
    (BareCtl.escape: "never fly bare", the dagger first) and **F8 down at +0.162 s**, 0.21 s later.
  - The F5's equip_request reached the server at -0.021 s (29 ms after its key). The death at 0.000
    was one hit of 4,323 (not an `act`: a skill; the Battle Log read "Stormy Knight 6275").
  - **No use_item_request: the Fly Wing key came 0.16 s after she was dead.**
  - ➡️ **This corrects 15.12's reading** ("the server got the EQUIP only at -0.02 s, 1.4 s late; the
    F5 seems to have held up the Fly Wing"). 15.12 compared the runner's death EVENT -- written
    1.54 s after the death packet, when the runner READ the death -- with the packet clock. On one
    clock there was no 1.4-s delay: the equip went out 29 ms after its key, and both keys came after
    the boss line, the Fly Wing after the death.
- **r01A** (s5c-ab, the hunt box):
  - -10.8 s: the fast alarm flew inside a fight (garm_seen inside, 0.70): F5 (-10.73 s at the server),
    then F8: use_item_result 601 ok at -10.53 s, a random cell on the same map.
  - The Knight came into view again at -4.24 s, 14 cells away. Alarm boxes in two detections in a row
    at -3.38 s (HUD 0.48) and -3.35 s (watcher 0.33), and -2.89 s (HUD 0.53): **a sighting by the
    runner's own rule for ~0.7 s, 3.4 s before the death** -- again inside box_target's settle and
    still wait (1,770 + 1,536 ms, to -2.85 s). The next box (-2.36 s, 0.38) stood alone: under 0.7.
  - The Knight hit at -0.94 s (2,380) and -0.47 s (1,310). The box's fly_away (HP 0) pressed F5, then
    F8, 0.4-0.6 s after the death.
- **So both deaths had a sighting the runner's own rule counts, 2.2 s and 3.4 s before the death,
  inside a wait that never reads the alarm.** The dagger-first escape cost 0.21 s more on each Fly
  Wing pressed while she wore the Knife.

### 18.2 The keys and the requests: what the data shows (the 24 series runs of 2026-11-15, 7.5 h)

The backend's key down -> the sniffer's request for it (read-only; `stage7_ab.py derive` over the
24 sessions and the two days' input logs gives these numbers exactly):

| Key | n | Request after the key down: median / p95 / max |
|---|---|---|
| F8 Fly Wing | 76 | 24 / 38 / 221 ms (from the runner's own send time: 75 / 88 / 272 ms) |
| F5 the dagger | 945 | 23 / 39 / 305 ms |
| F4 the Knife | 946 | 21 / 37 / 126 ms |
| F1, F6, F7, F9 | 129 | all within 41 ms |

- **No systematic client delay of an item use after an equip:** of the 47 Fly Wings pressed 0.21 s
  after an F5 (the dagger-first escape), 45 went within 40 ms, 2 at 212 and 221 ms (one while her
  own attack motion played: her `act` came 19 ms before its request). Of the 29 with no equip in the
  0.5 s before, every one within 38 ms. The occasional ~0.2-s wait (2 of 47) goes with the equip
  before the fly; fly-first removes that equip.
- **Every Fly Wing pressed alive reached the server:** the only 4 presses of 2,100 with no request
  were all after the death (r01A: F5, F8, F1 at +0.44 to +0.95 s; r02B: F8 at +0.16 s).
- The backend accepted every key ~50 ms after the runner sent it; no queue, no refusal.
- **What I chose:** the Fly Wing goes first, nothing before it but the ReleaseAll of a box's
  pre-empt (no key) and, when she sits, the stand-up (the runner's own rule; not a weapon key).

### 18.3 The boss signals the runner and the box have today

| Signal | Where it is read | Distance condition |
|---|---|---|
| The detector alarm: a `garm_baby` box (ALARM_CLASSES) in a detection <= 1.5 s old, --garm-confirm 2 in a row or one >= --alarm-solo 0.7 | step_engage every tick; (9.53, --alarm-fast) guard_tick inside scans, strikes, the steal, the hold | none |
| The HUD twin's boxes | feed the alarm under --alarm-fast with --hud-fast (~0.2 s, 4x the watcher) | none |
| The Battle Log boss line (boss_guard; the box's `sees_boss()`): a damage / taken line whose name fits the KB's boss names (Stormy Knight, Garm Baby, Christmas Goblin) | every full tick (step_battle_log) | contact only: it needs a hit |
| --boss-walk (off in the box; the box's boss fly refuses it) | step_engage | walks away from a SUMMON's line when a far cell is reachable, and ignores boss lines 2.5 s after |

- **Unread waits:** box_target's settle sleep (<= 1.2 s), its still wait (<= 1.5 s) and its fresh-box
  wait (<= 1.8 s): up to 4.5 s with no alarm read (both deaths). The loot pickups' walks
  (0.45 + 0.2 s a cell) lie between guard_tick reads.
- **The models:** the deployed xmas02 (xmas02gb, b22d972b714f) has player, mystcase, cruiser, cookie,
  cookie_xmas and garm_baby: no Knight or Goblin class. The boss recognizer stormy-v1 (class party:
  1251 / 1515 / 1607) is NOT adopted (98 false per 10 min). **No class is unused.** The hook for the
  Goblin alarm-bar round (xmas02sk, if it deploys): a model's models.yaml entry may name its alarm
  classes (`alarm: [garm_baby, ...]`); the runner's alarm then takes those classes (else garm_baby),
  with no code change. No model changes here.

### 18.4 The design: dungeon@9.57 `--fly-first` (the Run setting `fly_first`, tab safety)

1. **ONE boss read, FIRST in the tick.** At the start of step_survive -- before the box's events and
   the runner's sustain, so before any press of the tick -- the latched alarm sighting (2), or the
   tick's Battle Log boss line when the box does not play the boss fly, takes the Fly Wing at once
   (the 2-s Fly Wing pace kept: a teleport still landing), then the boss guard's after-fly steps
   (no box engagement for BOSS_AVOID_S, the lock / route / loot reset, mode search, 1 s) and
   TICK_DONE. step_engage no longer reads the alarm itself under the flag.
2. **A sighting is LATCHED.** A detection that qualifies (the streak, or one box >= --alarm-solo) is
   kept FF_LATCH_S = 3.0 s, until a Fly Wing acts on it or a newer one replaces it: an empty
   detection after it no longer erases it. Why 3 s: the longest wait left unread (the fresh-box
   wait, <= 1.8 s) is under it; the party came 2.4-6.4 s before every death of 11.1.
3. **Read inside the waits.** guard_tick's inside read is the fly-first read (latched; no
   --alarm-fast needed); box_target's settle sleep reads it every QUICK_S and its still wait every
   frame; a strike reads it before its opener and its click. A fly there ends the action
   (`escaped`), as 9.53's.
4. **The Fly Wing FIRST.** A boss Fly Wing (the alarm, the boss line, the box's Fly Wing on a tick
   with a boss line) presses F8 with nothing before it: no BareCtl.escape() dagger (F5), no opener
   (F4), no knife_back. FF_REARM_S = 1.0 s after the landing, the dagger goes back on (the escape's
   own equip, read back on the next tick), so the next fight starts armed. Nothing is cancelled after
   it is sent; what would have come is read first: a strike's opener and the box's knife_on wait for
   the read in (3); a knife_back cue plays at a later step of the tick than the read in (1).
5. **Every sighting stream:** under the flag the HUD twin's detections feed the alarm (as
   --alarm-fast does), and --boss-walk is off (a summon's line flies).
6. **The box's events play the same order.** The box still decides the Battle Log line: its
   fly_away / boss fly runs right after the read in (1), a pre-empt (the engine's ReleaseAll, then
   its body), and its F8 goes out with no dagger (the tick's boss flag). The alarm stays the
   runner's, as today. A boss line read within 2 s after a Fly Wing is not a new sighting for the
   box's events (the lines from before the jump). Both shapes -- the old runner block and the
   functions box -- lower to the same runner, so they play the same.
7. **Records:** `fly_first` events {what: fly / rearm, why, src: alarm / line, the sighting's grab
   time, class, score, streak, HUD or watcher, its age, `t_read_ns`, `t_key_ns` (the F8's send
   time)}; counts fly_first, fly_first_inside, fly_first_rearm; run_start `fixes.fly_first` =
   [FF_LATCH_S, FF_REARM_S, "9.57"].
8. **The setting:** `fly_first` (switch, safety tab, "a boss seen, at any distance: the Fly Wing
   first, no Knife swap before it"), **default OFF until s7ab passes** (then one line turns it on,
   with the ready-made boxes' block). Off: the runner is today's, byte for byte in what it does.
9. **The proofs stay green:** every fly-first change is a branch `if fly_first:` (run()'s) or
   `if FLY_FIRST:` (the module's), whose else is today's code. huntstate_check reads every such
   branch as its else (and leaves out the names fly-first adds, FLY_FIRST_ADDED): with it, `check`
   (5b-1) and `drive` (5b-2) read today's base exactly. A test stages a change OUTSIDE a branch and
   sees both refuse. hunt_trace (the steps' trace) is untouched: the cursor and the steps' order do
   not change.

### 18.5 Limits

- A boss the detector does not box and that does not hit her is not seen (the Goblins: no class; the
  Knight: boxed as garm_baby only by accident, 11.1). The hook in 18.3 takes a new class.
- The 2-s pace stays: a sighting within 2 s after a Fly Wing waits for the landing.
- The fresh-box wait inside BoxWatch is read when it returns (<= 1.8 s), not during it.
- A box event a PERSON writes whose body presses another key before the Fly Wing keeps its order.
- False flies: the alarm rule is today's (11.2: ~1.7 an hour offline); the latch and the waits add
  the sightings today's loop missed, true or false. s7ab measures the cost.

### 18.6 Open for Batt

1. When s7ab passes: fly_first ON in the ready-made boxes? (Built: off until then.)
2. The HP Fly Wing (no boss) still puts the dagger on first; should it fly first too?

### 18.7 THE A/B s7ab -- pre-registered 2026-11-16 10:51 ICT from `date`, BEFORE any of its data

**The arms differ ONLY in the setting fly_first** (`scripts/stage7_ab.py`, stage5c_ab's pattern; the
checkout's runner for both): the ready-made functions box (project_xmas_dun02_functions.json), its
copy per arm with the safety tab's `fly_first` = False (**A**, today's runner) or True (**B**).
`plan` refuses before any input unless the two copies differ in that block alone, give the same
runner argv but `--fly-first`, and huntstate_check drive / check hold.

    cd /home/bot/docker/poring-lab
    .venv/bin/python scripts/stage7_ab.py plan  --label s7ab --pairs 4 --minutes 20
    .venv/bin/python scripts/stage7_ab.py run   --label s7ab --pairs 4 --minutes 20
    .venv/bin/python scripts/stage7_ab.py score --label s7ab

4 pairs of 20 min, order A B, B A, A B, B A; stage2_ab's setup before every run; a STOP file ends the
series before its next run; never beside another live series. **THE BAR** (`stage7_ab.BAR`):

| Line | B must hold |
|---|---|
| kills per hour | the mean paired difference (B - A) >= -2 x its standard error, over at least 3 valid pairs |
| loot steps per hour | the same rule |
| Knife openers per hour | B's series rate within +-20 % of A's (valid runs pooled) |
| the tick pace | B's MEDIAN gap between hp_read records <= A's + 5 ms (valid runs pooled); the p95 reported (14.7a) |
| no new record kind | every kind B's runner sessions write is one the 5b-1 runner's source writes, one A's sessions wrote, the drive's own, or fly-first's (fly_first) |
| no runner error | no B run ends by an exception of the runner |
| the drive | every run of either arm that played drove, passed no step, left none out, and ended as the run did (15.8) |
| **fly first** | every B fly-first Fly Wing pressed while she was alive: no F4 / F5 key down (the backend's input log) between the runner's read of the sighting and the F8, and its use_item_request within **0.35 s** of the F8's send time (18.2: 76 of 76 within 0.272 s, median 0.075). Judged when B made at least one; none: the line is INCONCLUSIVE |
| a valid run | at least 80 % of M minutes on the runner's own clock, or a weight-home end; a pair counts when both runs are valid |

Reported, not judged: **deaths per played run, per arm** (they are rare -- 2 in the 7.5 h of
18.2 -- so no line compares them against an arm that may read 0: 13.7 / 10.2); the boss sightings,
the flies by source (alarm / line / box / HP), B's flies inside a wait, the sightings A read late or
never (from A's alarm boxes, offline), Fly Wings / h, potions / h, the economy per arm (gross_h and
net_h, zeny an hour, from data/econ/lab.sqlite after `econ_db.py update`: Batt's "every run, the
economy"), each record kind's rate. FAIL when a judged line fails; INCONCLUSIVE when fewer than 3
pairs are valid or the fly-first line was not exercised, and nothing failed; else PASS.

### 18.8 ➡️ BUILT (2026-11-16 10:5x-11:2x ICT from `date` and the commits; feat/fly-first from main f4342ed9; offline only, NOT run live)

- **The runner** (defa31fd): dungeon@9.57 `--fly-first`, as 18.4, every change a branch
  `if fly_first:` / `if FLY_FIRST:` whose else is today's code (20 branches). The module adds
  FLY_FIRST, FLY_FIRST_VERSION, FF_LATCH_S (3.0), FF_REARM_S (1.0), FF_BOSS_WHYS, alarm_classes,
  ff_latch, ff_sighting; run() adds the head of step_survive, ff_fly / ff_inside / ff_wait, the
  reads in guard_tick, box_target (settle, still, fresh) and strike, the press order and its
  record, the old-line filter, the alarm left to the head in step_engage, --boss-walk off.
- **The proofs:** huntstate_check reads every such branch as its else and leaves out the names in
  FLY_FIRST_ADDED (`unflag`): `drive` and `check` hold (run() without the drive branch == 5b-1's;
  OUTLINE(ALIAS(LIFT(base)))), and a test bends one line OUTSIDE a branch and sees both refuse.
  `driver_loop(tree, fly_first=True)` reads the program with the flag ON, for the tests.
- **The setting:** `fly_first` (switch, safety tab, default OFF), 122 setting blocks; the four
  ready-made boxes hold its block at its default, so their runner argv stays today's (the pinned one
  included); settings.gen.ts regenerated.
- **The A/B tool** (d83a36cf): scripts/stage7_ab.py, 18.7's bar exactly (stage7_ab.BAR); the score
  runs `econ_db.py update` for the runs' sessions first (17 #7). `stage7_ab.py derive` over 18.2's 24
  sessions and the two days' input logs gives 18.2's table exactly.
- **What the execution tests show** (test_fly_first.py, run()'s own closures in a namespace of fakes):
  a boss Fly Wing (the alarm's, the line's, the box's on a boss tick) sends F8 alone; an HP one sends
  F5 then F8 (9.27's order); the flag off sends F5 then F8 for every one (r02B's order); a fresh
  latched sighting flies once inside an action and never within 2 s of a Fly Wing; a wait that reads
  it stops at it; the tick's head flies on the alarm or on a line the box does not play, leaves a
  line the box plays to the box (its flag set), and puts the dagger back FF_REARM_S after.
- **The checks:** hunt_trace check --seeds 50: 146 scenarios, the same as the driver's;
  huntstate_check drive and check rc 0; the full Python suite (nice 10) 6,011 passed, 94 skipped,
  4 failed -- the worktree's 3 data files (data/hotbar/digits.npz, the generated map cache twice) and
  one version pin then updated (test_slot_items: the newest feature is 9.57; its file re-run green);
  ruff check and mypy clean; ruff format clean but main's two files; the frontend's 547 tests 546
  passed, 0 failed (1 skipped), tsc and eslint clean; stage7_ab's plan passes in process (no input).
- **Not built:** fly_first ON in the ready-made boxes (Batt's, after s7ab: 18.6); a Fly Wing first for
  the HP Fly Wing (18.6 #2); leaving the map after the escape (17 #6: not chosen).


### 18.9 Result of s7ab (run 2026-11-16 14:05-16:52 ICT, scored 16:52): PASS on every line

`stage7_ab.py score --label s7ab`: 4 pairs, all 8 runs valid, 0 deaths. A = the functions box with
fly_first OFF; B = the same box with it ON.
- Run ends: r06B ended by bag_full's home at 16.4 min, still valid; every other run by its time box.

    run       arm  kills/h loot/h open/h  tick median  fly-first flies (ok)
    r01A      A    163.2   178.3  139.0    201.5        -
    r02B      B    172.3   181.4  145.1    201.9        0
    r03B      B    117.8   142.0  105.7    202.6        3 (3)
    r04A      A    132.8   157.0  120.8    202.1        -
    r05A      A    150.8   159.9  123.7    201.8        -
    r06B      B    157.5   179.5  135.6    201.5        0
    r07B      B    123.9   151.1  114.8    201.8        8 (8)
    r08A      A    142.0   178.2  126.9    202.0        -

The bar (18.7):
- **fly first:** 11 fly-first Fly Wings in B, all judged, 0 after a death. No F4 / F5 key came between
  the read and the F8, and the use_item_request followed in 0.083 s median, 0.089 s max (bar 0.35 s)
  -> PASS;
- kills/h: paired +9.2, -15.0, +6.7, -18.1; mean -4.3, SE 7.1 -> PASS;
- loot/h: paired +3.1, -15.0, +19.6, -27.1; mean -4.9, SE 10.3 -> PASS;
- openers/h: A 127.6, B 124.8 -> PASS;
- pace: median A 201.8, B 202.0 ms -> PASS;
- kinds, errors: PASS;
- drive: all 8 drove -> PASS.
**VERDICT: PASS.**

Report only:
- deaths 0 / 0;
- potions/h A 5.3, B 7.9; Fly Wings/h A 9.8, B 11.1; steals/h A 87.6, B 89.3; lowest HP A 39 %, B 47 %.
- **The economy** (the first series recorded by round 29's hook: every run "economy record done";
  dashboard xmas02-1116-s7ab-flyfirst), gross / cost / net z/h with steals:
  - A 50,207 / 6,998 / 43,209;
  - B 54,117 / 10,212 / 43,905.
  - Equal net; B spends more on potions and wings.
- **A reporting bug found (not a data bug):** the tool's per-run "z/h" column and its econ report
  (gross_h 14,312, net_h 4,408) read econ_row's net_h, which leaves Steal / Snatcher income out
  (17.1). The database holds the steals; the A/B tools' z/h must use the dashboard totals. To fix.

**What it means:** Batt's rule plays live without costing kills or loot. A boss sighting now sends
the Fly Wing alone and at once. Whether fly_first becomes ON in the ready-made boxes is 18.6's open
question 1; Batt's own 17 #6 asks for this behaviour.


### 18.10 Batt's decisions on 18.9 (2026-11-16 ~20:3x ICT, Thai, translated)

1. **fly_first ON by default** in the ready-made boxes: "On." The functions box and its cookie twin
   get the block at ON. The old one-box, hunt-box and frozen A/B fixtures keep their pinned argv
   (reference arms). ➡️ **BUILT 2026-11-16 (18.12, feat/fly-first-hp).**
2. **The HP Fly Wing first too:** "Agree, do it." When HP calls for the Fly Wing with no boss in
   sight, the F8 also goes out alone, with no dagger key before it.
   - It is built behind its own setting, default OFF until a pre-registered live A/B (s8ab) passes,
     the same discipline as 18.7. ➡️ **Designed and pre-registered in 18.11; BUILT 2026-11-16
     (18.12): dungeon@9.58 `--fly-first-hp`, the setting fly_first_hp (off), scripts/stage8_ab.py.**
3. **The Goblin alarm: "test again."** Amendment S7 fixes S6's truth gap (frames just after a GM
   kill are not alarm-free), is pre-registered before any new data, and is scored once on a NEW
   held-out.
4. **The A/B tools' z/h counts steal income:** "Count the steal income too, since stealing is our
   main income." Every stage tool's per-run z/h and econ report use the totals with Steal and
   Snatcher income, the dashboards' gross, not econ_row's picked-only net_h. ➡️ **BUILT 2026-11-16
   (18.12): econ_db.totals_of, used by stage7_ab and stage8_ab; on s7ab's runs it gives 18.9's
   dashboard figures exactly.**

### 18.11 The HP Fly Wing first too (Batt 18.10 #2), and THE A/B s8ab -- design and pre-registration written 2026-11-16 20:40 ICT from `date`, BEFORE any code or run

**What changes** (dungeon@9.58 `--fly-first-hp`, the Run setting `fly_first_hp`, safety tab, needs
fly_first ON, **default OFF until s8ab passes**):
- An HP Fly Wing -- the runner's own (sustain's "hp ..." under fly_below, the HP-rate fly
  "rate ... at hp ...") or the box's fly_away on HP (a box Fly Wing on a tick with no boss line,
  its why naming hp_percent) -- sends F8 ALONE: no dagger key (BareCtl.escape) before it, as a boss
  Fly Wing under 9.57. The dagger goes back on FF_REARM_S (1 s) after the landing, by 9.57's own
  re-arm. The stand-up when she sits stays before it (not a weapon key).
- Other Fly Wings keep their order: the end's escape, an unread position, stuck, unreachable.
- Its record: 9.57's fly_first record with `src` "hp" (the runner's) or "box_hp" (the box's), its
  read time the press's start, and `sight` = {"hp": true, "bare": whether she wore the Knife}.
- **The proofs:** every change is a branch `if fly_first_hp:` (run()'s) or `if FLY_FIRST_HP:` (the
  module's), whose else is 9.57's code. huntstate_check's `drive` and `check` read every fly-first
  branch (both families) as its else, as before; and a new `flag` proof reads ONLY the
  fly_first_hp branches as their else and finds the WHOLE module equal to main 8a091a72's runner --
  the very program s7ab measured (18.9). So the A arm below is s7ab's B, byte for byte in what it
  does.

**How often an HP Fly Wing happens** (the 78 hunt sessions of 2026-11-14..16, 22.7 h; the runner's
press records): 31 HP Fly Wings while alive (28 the runner's HP-rate fly, 3 the box's fly_away on HP;
3 more pressed after a death are not counted), **1.37 an hour**; of them **8 while she wore the
Knife (6 HP-rate, 2 the box's; 0.35 an hour)**. Only those 8 differ between the arms: when she is armed, 9.57's escape presses no
dagger either, so an armed HP Fly Wing is the same program in both arms.
- In 4 pairs (80 minutes of B): about 1.8 HP Fly Wings in B, about 0.47 while bare. P(at least one
  bare) ~ 37 % (Poisson); in 8 pairs ~ 61 %; in 12 pairs ~ 75 %.

**THE A/B s8ab** (`scripts/stage8_ab.py`, stage7_ab's pattern and score):
- **A** = the ready-made functions box as 18.10 #1 makes it (fly_first ON) with fly_first_hp OFF;
  **B** = the same with fly_first_hp ON. The arms differ ONLY in that block; `plan` refuses before
  any input unless the copies, their settings and their argv (`--fly-first-hp` alone) differ in it
  alone, the runner is 9.58, and `drive`, `check` and `flag` hold.
- 4 pairs of 20 min, order A B, B A, A B, B A; stage2_ab's setup; a STOP file ends the series.

      cd /home/bot/docker/poring-lab
      .venv/bin/python scripts/stage8_ab.py plan  --label s8ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage8_ab.py run   --label s8ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage8_ab.py score --label s8ab

- **THE BAR** (`stage8_ab.BAR`): 18.7's lines -- kills/h and loot steps/h (mean paired difference
  >= -2 SE over >= 3 valid pairs), openers/h within +-20 %, the median tick pace <= A's + 5 ms, no
  new record kind, no runner error, the drive line for both arms, a valid run as 14.7 -- and:
  - **fly first on HP:** every B HP fly-first Fly Wing pressed while she was alive: no F4 / F5 key
    down (the backend's input log) between the press's start and its F8, and its use_item_request
    within 0.35 s of the F8's send time (18.2). **The line is judgeable only when B made at least
    ONE such Fly Wing while she wore the Knife** (the only case where B differs from A); otherwise it
    is INCONCLUSIVE, and so is the verdict unless a judged line failed.
  - **The pre-registered extension** (decided now, before any data, because 4 pairs judge it only
    ~37 % of the time): if the HP line is INCONCLUSIVE and no judged line failed, the series may be
    extended by blocks of 4 more pairs, each its own label (`s8ab-x2`, `s8ab-x3`), up to 12 pairs in
    all: `stage8_ab.py score --label s8ab --also s8ab-x2 [--also s8ab-x3]` judges the HP line on
    every block pooled; the other lines stay judged on s8ab's first 4 pairs (their own sample);
    nothing is dropped or re-run.
- Reported, not judged: deaths per played run per arm; the boss fly-first Fly Wings of both arms
  (9.57's line, as a check); every Fly Wing by source; the HP ones armed and bare; potions / h; the
  economy per arm WITH steals (18.10 #4: the dashboards' gross, cost and net an hour).
- FAIL when a judged line fails; INCONCLUSIVE when fewer than 3 pairs are valid or the HP line is not
  judgeable, and nothing failed; else PASS. PASS: fly_first_hp ON by default is the parent's (18.10
  #2).

### 18.12 ➡️ BUILT: 18.10's items 1, 2 and 4 (2026-11-16 20:4x-21:4x ICT from `date`; feat/fly-first-hp from main 8a091a72; offline only, NOT run live)

1. **fly_first ON in the ready-made boxes (18.10 #1).**
   - project_xmas_dun02_functions.json and its cookie twin (project_xmas_dun02_functions_cookie_noswap
     .json) hold the fly_first block ON. Their TS twins set it: xmasFunctionsProject(), and the cookie
     twin through it.
   - **The reference arms keep it OFF and keep their pinned argv:** the old one box
     (project_xmas_dun02.json), the hunt box (_hunt), the one-box cookie box and the frozen A/B
     fixtures (stage2 / 3 / 4: no setting blocks, so the registry's default). The registry's default
     stays OFF for that reason: a project WITHOUT the block runs fly_first off.
   - The functions box's runner argv is the hunt box's plus `--fly-first`, and its settings differ
     in fly_first alone (test_runner_blocks says so now).
   - The A/B tools keep their meaning, each arm's blocks set explicitly:
     - stage5c_ab (15.8, the shape alone): B is the functions box with fly_first set to the hunt box's
       value (off; arm_doc, B_SAME_AS_A), as s5c-ab and s5c-ab2 ran it; its box_difference, its
       settings check (now from the arms' texts) and its argv check mean what they meant;
     - stage7_ab (18.7): both arms' fly_first were already set explicitly (A off, B on): unchanged
       logic, its docstring says so;
     - stage8_ab (18.11): fly_first ON in both, fly_first_hp set per arm.
2. **The HP Fly Wing first (18.10 #2), as 18.11:**
   - dungeon@9.58 `--fly-first-hp`, the setting `fly_first_hp` (safety tab, needs fly_first, OFF in
     every ready-made box);
   - the HP Fly Wings (sustain's "hp ..." and "rate ...", the box's fly_away naming hp_percent:
     `ff_hp_why`) send F8 alone and re-arm 1 s after, their record `src` "hp" / "box_hp" with
     `sight` {"hp", "bare"};
   - every change is a branch `if fly_first_hp:` / `if FLY_FIRST_HP:` (4). huntstate_check `flag`
     (new) reads ONLY those as their else and finds the whole module equal to 8a091a72's -- the
     runner s7ab measured -- and refuses a changed 9.57 line; `drive` and `check` hold as before
     (22 branches read as else).
   - scripts/stage8_ab.py: 18.11's bar exactly (stage8_ab.BAR), the HP line (B's HP fly-first Fly
     Wings; judgeable with at least one pressed while bare), `score --also` for the pre-registered
     extension, the boss line of both arms reported.
3. **The A/B tools' z/h with steal income (18.10 #4):**
   - the one function: `econ_db.totals_of(sessions)` -- the DASHBOARD's totals, each run's
     (econ_dash.entry_of) and the runs pooled (econ_dash.pool_runs), through econ_dash.totals: gross
     = (picked + stolen by Steal and Snatcher) x NPC sell, cost = the consumables used, net = gross -
     cost, each an hour; the file read-only;
   - stage7_ab's per-run "z/h" column and its per-arm economy (now `econ_with_steals`: gross_h,
     cost_h, net_h, each arm's valid runs pooled) use it; stage8_ab reuses stage7_ab's;
   - **checked on s7ab's 8 recorded runs:** A 50,207 / 6,998 / **43,209** and B 54,117 / 10,212 /
     **43,905** gross / cost / net z/h -- 18.9's dashboard figures exactly;
   - the other stage tools print no econ zeny: stage5_ab has none; stage6_ab's `steal_zeny` is its
     own per-steal value line (data/econ/maps.json), already a steal figure; nothing else read
     econ_row's net_h.
4. **The checks:** the full Python suite (nice 10) 6,033 passed, 94 skipped, 5 failed -- the
   worktree's 3 data files, and two pins that 18.10 #1 / 18.11 moved (test_settings' unused-setting
   notes of the one box, test_runner_blocks' functions-box argv), updated after and re-run green;
   huntstate_check drive / check / flag rc 0; hunt_trace check --seeds 50, 146 scenarios the same;
   ruff and mypy clean, ruff format clean but main's two files; the frontend's 550 tests 549 passed,
   0 failed (1 skipped), tsc and eslint clean; stage8_ab's, stage7_ab's and stage5c_ab's plans pass
   in process (no input).


### 18.13 Result of s8ab (run 2026-11-16 21:36 - 2026-11-17 00:23 ICT, scored 00:25): PASS on every line

`stage8_ab.py score --label s8ab`: 4 pairs, all 8 runs valid, 0 deaths. A = the functions box with
fly_first ON and fly_first_hp OFF; B = both ON.
- Run ends: r02B ended by bag_full's home at 13.7 min, still valid; every other run by its time box.

    run       arm  kills/h loot/h open/h  tick median  z/h (with steals)
    r01A      A    111.7   141.9  114.7    202.3       31,978
    r02B      B    145.0   153.7  136.2    201.7          524
    r03B      B    126.9   181.3  117.9    201.8       62,710
    r04A      A    139.0   175.2  126.9    201.8       57,125
    r05A      A    129.8   153.9  108.6    201.8       40,190
    r06B      B    141.7   168.8  108.5    201.8       74,671
    r07B      B    136.0   154.1   90.6    201.9       42,371
    r08A      A    136.0   175.3  117.8    202.5       42,786

The bar (18.11):
- **the HP fly-first line:** B made 1 HP Fly Wing while alive, and it was BARE (she wore the Knife),
  so the line is judgeable. No F4 / F5 key came between its press and its F8, and the request
  followed in 0.072 s (bar 0.35 s) -> PASS.
  - Judged at 4 pairs; the pre-registered extension (s8ab-x2) is not needed.
- the boss fly-first line in both arms: every one alone -> PASS;
- kills/h: paired +33.2, -12.1, +11.9, 0.0; mean +8.3, SE 9.7 -> PASS;
- loot/h: paired +11.8, +6.1, +14.9, -21.2; mean +2.9, SE 8.2 -> PASS;
- openers/h: A 117.0, B 111.4 -> PASS;
- pace: median A 202.1, B 201.8 ms -> PASS;
- kinds, errors and drive: PASS.
**VERDICT: PASS.**

Report only:
- deaths 0 / 0;
- potions/h A 6.0, B 3.3; Fly Wings/h A 15.9, B 11.5; steals/h A 77.0, B 82.7; lowest HP A 41 %,
  B 48 %;
- the economy with steals (18.10 #4's totals; 137 runs in the file), valid runs pooled:
  - gross / cost / net z/h A 51,255 / 8,238 / 43,017;
  - B 63,214 / 4,688 / 58,526;
  - B nets more, from fewer potions and wings and more steals, within the run-to-run noise
    (r02B's 524 z/h short run among them). It is reported, not a claim.
- **Next:** fly_first_hp goes ON in the ready-made boxes, as 18.10 #2 decided once the A/B passes.
- ➡️ **fly_first_hp ON in the ready-made boxes, 17d18124** (2026-11-17, feat/fly-first-hp-on): the
  functions box and its cookie twin hold the block ON (argv + `--fly-first-hp`); the reference arms
  -- the one box, the hunt box, the one-box cookie box, the frozen A/B fixtures -- keep it off and
  their pinned argv, and the registry's default stays off; stage5c_ab's, stage7_ab's and stage8_ab's
  arms set the block explicitly, so each plan means what it meant.


### 18.14 Batt's decision on the Goblin model (2026-11-17, Thai, translated)

- **"Use it for real."** The frozen xmas02sk (S4 last.pt 0b43ebbf; S7 PASS) becomes the xmas_dun02
  model in the ready-made boxes.
- **What changes:** the live alarm flies on its Goblin and knight boxes as well as the Garm Baby, with
  18's fly-first.
- **The parent's way of doing it:**
  - deploy it as the default (the registration, a serve test, the map's model, the box's use_model,
    the alarm classes);
  - check it with a pre-registered live A/B (A = the old xmas02 as the reference arm, B = xmas02sk):
    deaths, false Fly Wings per hour against the packets (with S7's post-vanish rule), and kills/h.
  - If B fails a judged line, the default goes back and Batt is told.


### 18.15 ➡️ DEPLOYED: xmas02sk is xmas_dun02's model (dungeon@9.59), and THE A/B s9ab -- written 2026-11-17 07:05 ICT from `date`, BEFORE any s9ab run (feat/xmas02sk-live from main f8e27d21; offline, one serve test; NOT run live)

➡️ **RUN 2026-11-17 07:32-10:23: PASS on every line (18.16); xmas02sk stays deployed.**

**What changed (18.14's "deploy it as the default"):**

| Piece | Before | Now |
|---|---|---|
| `unit_detector.GPU_WEIGHTS` | 8 models (376a0137's `xmas02sk` reverted by c26d96c0) | + `xmas02sk` again: last.pt `0b43ebbf...`, ONNX `76316fb4...` (S4.8 / S4.9); fi_gpu_latency's ONNX line too |
| `MAP_MODELS["xmas_dun02"]` | xmas02gb (`b22d972b...`) | **xmas02sk**; the same collapse (Myst Case, Cruiser, Cookie, Christmas Cookie -> "monster"); garm_baby, g_gobline_xmas, knight_of_windstorm NOT collapsed: never struck, read by the alarm by name |
| `MAP_REFERENCES["xmas_dun02"]` (new) | - | xmas02gb, loadable ONLY when a box's use_model names its file (`map_model`, `for_map(onnx=)`, `for_map_gpu(onnx=)`); any other file fails closed |
| models.yaml | `xmas02` = xmas02gb, the map's own | `xmas02sk` live, `alarm: [garm_baby, g_gobline_xmas, knight_of_windstorm]` (18.3's hook `alarm_classes` reads it), first; `xmas02` live with `reference: true` (`map_detector` skips it). New fields `alarm` (in class order, never a struck class) and `reference` (a live detector of named maps), validated |
| The box's run() argument (`BlockPlan.model_doc`) | id, file, sha256, maps, status, kind, strikes | + `alarm` and `classes` for a model that names an alarm; a model without one gives exactly the old entry (the reference arms' run() arguments unchanged) |
| The runner, dungeon@9.59 `MODEL_PICK` | the box watcher loaded the map's model; a use_model naming another was refused | `box_model_refused` takes the map's own OR one of its references by the box's file; `BoxWatch(..., model_file=)` loads that file's CPU model and its GPU weights; run() hands it the box's file. No use_model, or the map's own: the map's model, as before |
| The ready-made functions box and its cookie twin | `use_model("xmas02")` | **`use_model("xmas02sk")`** (fixtures + project.ts `FUNCTIONS_MODEL`); argv, settings, keys, loop unchanged |
| The reference arms (the one box, the hunt box, the one-box cookie box, the frozen stage-4 fixture) | xmas02 | **xmas02 kept**, with their pinned argv and box. stage5c_ab's B takes A's use_model, stage7_ab's and stage8_ab's arms name xmas02 explicitly (`MEASURED_MODEL`), so each plan means what it meant. The stage-2 / stage-3 fixtures and a CLI run name no model: they now get the map's, xmas02sk |
| /flows | - | the model picker notes "live, a reference arm's"; a node without use_model is shown xmas02sk's monsters (the TS `monstersOf` skips a reference) |

- **The runner change is a branch family, like fly-first.** Every change is `if MODEL_PICK:` whose
  else is 9.58's code, plus BoxWatch's keyword-only `model_file` (default None).
  `huntstate_check.py pick` (new): with only these branches read as their else and the keyword
  dropped, the WHOLE module equals PICK_BASE `f8e27d21`'s (the 9.58 runner s8ab measured): **YES, 5
  branches**. `check`, `drive` and `flag` read the family as its else too and all pass (rc 0), so
  each still proves what it proved. `unflag(..., params=)` drops a family's keyword only when its
  default is None; the module comparison then refuses any use of it outside a branch (tested).
- **A box whose use_model names neither the map's own nor a reference is refused before any input**
  (the words now name both files); the 11-07 model (`GPU_WEIGHTS["xmas02"]`) stays a rollback only,
  never loadable by a box.

**The offline checks (before the serve test, i.e. before 06:56 ICT):**
- The ready-made box (and its cookie twin): plan model `xmas02sk`, the four recipes resolve
  (attack_mystcase / _cruiser / _cookie / _cookie_xmas: the same four struck species), lint and
  `live.problems` clean, `box_model_refused` None (GPU and CPU), alarm classes = the three.
- The one box: still `xmas02`, not refused (a reference), alarm = garm_baby alone.
- The CPU detector on this host: `for_map("xmas_dun02")` loads xmas02sk-last-736x1280.onnx
  (`76316fb4e581`, its sidecar's 10 names in class order, the four species collapsed);
  `for_map(..., onnx=xmas02gb)` loads xmas02gb (`b22d972b714f`, 8 names).
- Detection quality to expect (scored once, never again): S4.10 -- Garm Baby on gw3 Q1s 1.000 /
  0.922 (= xmas02gb's M11), the four species pooled TEST Q1c 0.983-1.000 / 0.933-0.937; S7.6 -- the
  alarm bar 33 / 33 visits detected, false fires 0 / 98 and 0 / 265; D1 forward p95 17.96 ms.

**THE SERVE TEST (one guarded step, 06:56:20-06:58:52 ICT; the worker idle, no Run or series, no
detect server before it):** the worktree's `unit_detector.py serve-cmd --backend openvino --seconds
150`, run with the main checkout's guarded_build.
- The server's listening line named **9 models** (v1, xmas02, xmas02gb, xmas02fi ... fi5, xmas02sk
  `76316fb4e581`), OpenVINO GPU, `ov_preproc` gpu, f32, the clock floor 2450 MHz.
- A host client asked it through `for_map_gpu("xmas_dun02")` (weights xmas02sk) and
  `for_map_gpu(..., onnx=xmas02gb)` (weights xmas02gb), on the 8 s8ab end screenshots (the game
  region): **18 / 18 calls on the GPU path** (the hello's pin accepted), server forward p50 15.7 ms /
  p95 19.2 ms, the client's call 17.7-28.9 ms after a first ~104-121 ms one.
- GPU vs CPU of the same file: the same classes on every frame, boxes 0.0 px apart.
- The step ended at its time box (rc 124) with the verified stop: "worker up and idle (no CUDA
  context), nothing of ours on the GPU".
- In passing: on every end screenshot (her in Geffen after the Butterfly Wing) xmas02gb boxes a
  "cookie" that xmas02sk does not.

**THE A/B s9ab (pre-registered here, BEFORE any of its data; `scripts/stage9_ab.py`):**
- **The arms:** the ready-made functions box, fly_first and fly_first_hp ON in both (set
  explicitly), with `use_model("xmas02")` (A: xmas02gb, the alarm on the Garm Baby) or
  `use_model("xmas02sk")` (B: the alarm on the Garm Baby, the Christmas Goblin and the Stormy
  Knight). 4 pairs of 20 min, alternating (ABBA ABBA), stage2_ab's setup before every run.
- **`plan` refuses before any input unless the arms differ ONLY in the model:** the box texts in
  the use_model alone; the runner settings, argv, keys, loop and tick not at all; the run() box
  arguments only in `box_model`, whose entries differ only in id / file / sha256 and the alarm (and
  its classes) that follows from the model; each a model the runner loads on the map and the detect
  server serves; A's alarm classes garm_baby, B's the three. Also the runner is 9.59, `drive`,
  `check`, `flag` and `pick` hold, and the box's step traces equal the driver's (63 scenarios).
  Today's plan passes (rc 0; project hashes A `e5d8c8b2...`, B `f9aaef1d...`).
- **The packets' truth of a boss Fly Wing** (every fly_first record but the HP ones; the moment the
  runner acted on = the alarm sighting's grab time, else its read):
  - FALSE when no alarm-species unit (Goblin 1607, knight 1251, Garm Baby 1515) is ON SCREEN by the
    packets and the moment is outside every S7.1 post-vanish window (5.0 s after a vanish, reason 0
    or 1, of an alarm-species unit).
  - On screen: the Timeline world 0.12 s earlier (the frames trail the packets), each unit's cell
    relative to hers projected by the runner's own camera (camera_rdp.json, flat ground), the
    knight's sprite envelope (the largest of the three) meeting the 1280 x 720 game region.
  - Its positive case, on the 12 banked fly-first runs of xmas02gb (s7ab's B, s8ab's A and B, all 39
    boss Fly Wings alarm ones): **on the 21 judged true, the nearest alarm unit's projected foot lay
    2-98 px from the box's foot (median 45)**. On the 16 judged false, the nearest monster of any
    kind was >= 190 px away or absent, or a Myst Case / Cruiser / Cookie she was fighting 8-24 px
    away (a species confusion). High scores and long streaks (0.96-0.98, 4-12 in a row) on nothing
    at all fit S7.1's painted Garm Baby on the floor. 2 lay inside post-vanish windows.
- **JUDGED (FAIL if one fails, INCONCLUSIVE if none fails but one cannot be judged, else PASS):**
  1. deaths: B's <= A's over every run that played (stage5b_ab's line; `<=`: two zero arms pass);
  2. **false boss Fly Wings an hour: B <= A + 6.2** (each arm's valid runs pooled). The margin,
     derived at 07:00 from the same 12 runs (3.83 h): per-run false rates 0-15.0 / h, SD 4.32 / h,
     pooled 4.01 / h; 2 x sqrt(2 / 4) x 4.32 = 6.11 / h, the Poisson floor 2 x sqrt(2 x 4.01 /
     1.33) = 4.91 / h; the larger, rounded up to 0.1 = 6.2 / h (`stage9_ab.py derive`);
  3. kills / h and loot / h: mean paired (B - A) >= -2 SE (judged with >= 3 valid pairs);
  4. openers / h: B within +-20 % of A;
  5. the tick pace: B's median <= A's + 5 ms;
  6. kinds, errors, the drive (stage7_ab's lines);
  7. the model: every run that played loaded its arm's model (its box_model records: the ONNX and
     the detect server's weights).
- **The scorer's dry run (07:18 ICT, read-only, on s8ab's archived series and sessions, both
  arms xmas02gb so only the new lines mean anything):** every line computes; s8ab's own per-run
  kills / loot / openers / pace come back as in 18.13; false boss Fly Wings "A" 3.02 / h, "B" 4.91
  / h; party visits 8 and 3, 6 and 2 of them flown, 1.0 and 1.44 s to the Fly Wing (median); the
  detect server's call 21.4 / 21.5 ms median.
- **REPORTED only:** the alarm's true Fly Wings per party visit (a visit: 0.25-s samples with a
  Goblin or the knight on screen, a gap > 5 s ends it); the time from a visit's first sample to its
  Fly Wing; the boss Fly Wings by source and the alarm sightings by class; the economy with steals
  (econ_db.totals_of); the detect server's call ms; deaths per arm.
- **On a FAIL of a judged line:** the default goes back (18.14) -- the ready-made boxes'
  use_model to "xmas02" and MAP_MODELS to xmas02gb -- and Batt is told.
- **Commands (from MAIN after the merge, the worker free):**

      cd /home/bot/docker/poring-lab
      .venv/bin/python scripts/stage9_ab.py plan  --label s9ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage9_ab.py run   --label s9ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage9_ab.py score --label s9ab

  ~3.5 h (the detect server's time box 12,600 s).
- **Limits:**
  - The on-screen rule is approximate: flat ground (no GAT altitude), one envelope for the three,
    the Timeline without the map grid (diagonal-first walks), so a unit at the screen's edge may be
    judged either way. Both arms and the margin's data are judged by the same rule.
  - Visits are rare: the knight respawns every 60-70 min; the banked 12 runs held 13 visits.
  - The false-Fly-Wing line has little power at 4 pairs: the margin (6.2 / h) is wider than A's
    expected rate (~4 / h).


### 18.16 Result of s9ab (run 2026-11-17 07:32 - 10:23 ICT, scored 10:23): PASS on every line; xmas02sk STAYS deployed

- **Valid:** 4 pairs of 4 (ABBA ABBA), every run rc 0, 0 deaths. r03B ended at 17.2 min by the
  runner's own stock keep ("1 Fly Wing(s) left, kept for the end"); every other run hit the time
  box.
- **Judged lines (18.15's bar), all PASS:**

      line                     A (xmas02gb)        B (xmas02sk)        bar
      deaths                   0                   0                   B <= A
      false boss Fly Wings/h   3.02 (4 of 10)      5.46 (7 of 21)      B <= A + 6.2
      kills/h, paired          -                   -6.5 +- 5.0         >= -2 SE
      loot/h, paired           -                   -15.6 +- 10.7       >= -2 SE
      openers/h                137.2               121.7               within +-20 %
      pace, median tick        201.6 ms            201.9 ms            <= A + 5 ms
      kinds / errors / drive   clean               clean               no new kind, none
      the model                xmas02gb records    xmas02sk records    each arm's own

- **Reported only:**
  - the party's visits: A 7, 4 of them flown (0.571 true Fly Wings a visit); B 5, all 5 flown
    (1.000);
  - the time from a visit's first sample to its Fly Wing: A median 2.52 s (max 6.95); B 0.35 s
    (max 2.51);
  - boss Fly Wings all from the alarm; sightings by class: A garm_baby 10; B the Goblin 10,
    garm_baby 9, the knight 2;
  - Fly Wings/h 7.5 vs 17.2; potions/h 0.0 vs 3.9; steals/h 101.8 vs 89.0; HP low 61 vs 46 %;
  - the detect server's call: median 21.7 vs 21.9 ms, p95 24.9 vs 25.1 ms;
  - the economy with steals (econ_db.totals_of; 145 runs in data/econ/lab.sqlite): net z/h A
    77,218 (gross 77,723, cost 505), B 86,870 (gross 92,621, cost 5,751). Per run 50k-106k:
    within the noise, not a claim.
- **A defect found in the score, in BOTH arms (fly_first, dungeon@9.57): the stale re-fire.**
  - 9 boss Fly Wings (B 8 of 21, A 1 of 10) went out 2.28-2.46 s after the previous one. Each acted
    on a sighting GRABBED 0.29-0.45 s after the previous Fly Wing's key: a frame still showing the
    old place, because the frames trail her teleport. The 3-s latch (FF_LATCH_S) kept it, and
    ff_sighting's "grabbed after the last Fly Wing" passed it. The loop acted on it 1.81-2.07 s
    later (age_s), once the landing and the re-arm were over.
  - By the packets, none of the 9 had an alarm-species unit on screen: 5 were judged false, 4 fell
    inside a post-vanish window. Her own teleport makes every unit vanish from her view (reason 0),
    so S7.1's window covered them.
  - A tenth quick repeat (r07B, 2.38 s) was a FRESH sighting (grabbed 2.22 s after, age 0.08 s, 7
    units on screen): a true Fly Wing.
  - Without the 9: A 9 boss Fly Wings, 3 false (2.26/h); B 13, 3 false (2.34/h). The Goblin
    model's own false rate is A's.
  - It costs Fly Wings, and it ended r03B early by the stock keep (4 of its 9 boss Fly Wings were
    re-fires).
  - The fix (a sighting must be grabbed after the LANDING, not just after the key) is a runner
    change: built offline as its own flag, then its own live A/B (18.17).
- **Other observations:**
  - Between r06B and r07B the series' clear-bag returned rc 1: its stock check read Fly Wing (601)
    0 after the restock, while the hotbar count read 10. The series went on with the hotbar's
    read. The run played normally.
  - With the Goblin and the knight in the alarm, the Fly Wing use more than doubles (17.2/h). A
    long run needs a bigger Fly Wing stock (the box's stock settings) even after the fix (about
    10/h without the 9).
- **Decision (the parent's, under 18.14):** no judged line failed, so xmas02sk stays deployed as
  the default. Batt is told, with the defect and its fix.


### 18.17 ➡️ BUILT: the stale re-fire's fix, dungeon@9.60 `--fly-first-land`, and THE A/B s10ab -- written 2026-11-17 10:58 ICT from `date`, BEFORE any s10ab run (feat/fly-first-land from main c694f0f4; offline only, NOT run live) ➡️ RUN 11:23-14:11: PASS on every line (18.18); fly_first_land stays OFF until Batt decides ➡️ Batt 2026-11-17 ~15:0x ICT: ON in the ready-made boxes (18.18's last item)

**The rule (the simplest one the data proves):**
- Every Fly Wing's key moves a LAND FLOOR to its send time + `FF_LAND_S`. This covers the boss
  ones, the HP fly-first ones, the box's and the end's, because every Fly Wing goes through `press()`.
- A latched boss sighting counts only when it was grabbed after that floor, and after the last Fly
  Wing as before (`ff_floor` = max of the two).
- Both reads that act on the latch use it: the tick's head (`step_survive`) and the read inside
  actions (`ff_inside`).
- The HP Fly Wing itself is decided by the HP read, never by a latched sighting. So the floor does
  not gate it; its re-fire gates stay sustain's 3 s and the box's 3-s cooldown.
- `ff["after"]` (set at a fly-first Fly Wing, cleared at the re-arm) gates only the dagger's re-arm
  (FF_REARM_S), never a re-fire: unchanged. The re-fire's own gate was `ff_sighting`'s `after` =
  hs.fly_at, which the floor now raises.
- The two settings, tab safety:
  - `fly_first_land` (the switch, "after a Fly Wing: no Fly Wing again on what the picture showed
    before the landing"; needs fly_first): **registry default OFF**, and OFF in every box,
    the ready-made ones included, until s10ab passes. The ready-made box as it is now is s10ab's A.
    ➡️ s10ab passed (18.18); since 2026-11-17 (Batt) the two ready-made functions boxes hold it ON
    (so the fixture is B's box now; stage10_ab's A sets it OFF explicitly); the registry's default
    and the reference boxes stay OFF.
  - `FF_LAND_S` (a runner constant through `--tune`, 0.2-2.0 s, "after a Fly Wing, ignore boss
    sightings in the pictures of the first"): **our default 0.75 s**.
- Records:
  - run_start `fixes.fly_first_land` = [FF_LAND_S, "9.60"];
  - with the switch on, one `fly_first` record `what: land` per Fly Wing (its `t_key_ns` and
    `floor_ns`), written after the key.

**THE LANDING TIME, derived from banked data (read-only; 24 runner sessions: s9ab here, s8ab and
s7ab from the NAS; 94 teleports, each a `use_item_result` 601 ok + its `map_change`):**
- Method: the detections (both streams) by their GRAB time, i.e. the log time minus the measured
  log offset (47.8 ms median, 39-73 ms, 70 sightings matched by class and score).
  - A frame still shows the OLD place while its monster boxes continue the pre-teleport frames:
    a same-class box within 60 px, at least half of its boxes. Her own box must also stay within
    20 px (the camera's glide).
  - The first frame that does not continue shows the new place. 29 of them were a blank transition
    frame, the rest a new box set.
  - 79 teleports were measured; 15 had no monster box before the key and could not be.
  - The continuity rule alone was fooled once: s8ab r07B, a new-place box 49 px from an old one.
    Her own box's 22-px jump decided it.
- The numbers:

      measure (s)                                n    p50    p95    p99    max
      key -> map_change packet                   51   0.107  0.121  0.123  0.123
      map_change -> last frame of the old place  68   0.255  0.340  0.352  0.579
      map_change -> first frame of the new one   68   0.469  0.577  0.586  0.829
      key -> last frame of the old place         51   0.362  0.434  0.452  0.452
      key -> first frame of the new place        51   0.565  0.676  0.684  0.684

- **FF_LAND_S = 0.75 s:**
  - start from the p99 of the old place's last frame after the key, 0.123 + 0.352 = 0.475 s;
  - add one HUD frame interval of margin (0.25 s: the frames are sampled, so the true change lies
    between two of them): 0.725 s;
  - round up: 0.75 s.
  - It lies above every old frame measured: keyed 0.452 s, by the map_change 0.702 s at most (the
    one s7ab r05A outlier). It also lies above the keyed first new frame's max (0.684 s).
- Why not larger: a 1.0-s window lost one TRUE Fly Wing on the banked data (s8ab r06B, a Garm Baby
  at the landing spot boxed only at 0.74-0.96 s). 0.75 s loses none (below).

**THE OFFLINE REPLAY on s9ab's 8 sessions (31 boss Fly Wings, all alarm ones):**
- **Suppressed: exactly the 9 stale re-fires.** They were grabbed 0.29-0.45 s after the previous
  key:
  - r02B 0.29, 0.30;
  - r03B 0.29, 0.40, 0.42, 0.40;
  - r04A 0.45;
  - r07B 0.33, 0.35.
- For none of them was there a qualifying alarm detection (solo >= 0.7, or 2 in a row) after the
  floor, up to that Fly Wing + 1 s. So no other Fly Wing takes its place.
- **Kept: 22.**
  - r07B's fresh quick repeat (grabbed 2.22 s after the key, 7 alarm units on screen) is kept.
  - Every first Fly Wing is kept: all 21 whose previous Fly Wing was >= 5 s earlier, or none.
- **What it costs (all 24 sessions, 94 teleports):**
  - Frames show the new place from 0.42-0.68 s after the key (median 0.565). The floor drops
    sightings grabbed before 0.75 s: at most 0.33 s of them (median 0.19 s).
  - The Fly Wing itself already waits for hs.fly_at + 2.0 s (about key + 2.2 s) in 9.59. So a boss
    that is boxed again after 0.75 s flies at the same moment as today: **0 extra delay**.
  - On the banked data, 13 teleports had a qualifying alarm detection within 5.2 s:
    - 12 of them before the floor: 9 on the old place, 3 true;
    - all 3 true ones were boxed again 0.11-0.24 s later (0.79-0.97 s after the key);
    - **lost: 0.**
  - The loss case is a boss boxed ONLY between the first new frame and 0.75 s. That Fly Wing would
    then not go out; the 1.0-s window above shows such a case can happen.

**THE PROOFS (all rc 0):**
- `huntstate_check.py land` (new): with only the 7 `if FLY_LAND:` branches read as their else and
  FLY_LAND, FLY_LAND_VERSION, FF_LAND_S and ff_floor left out, the WHOLE module equals LAND_BASE
  `c694f0f4`'s (the 9.59 runner s9ab measured): YES.
- `check`, `drive`, `flag` and `pick` read the family as their else too, and all hold.
- The runner's feature version is dungeon@9.60.

**THE A/B s10ab (pre-registered here, BEFORE any of its data; `scripts/stage10_ab.py`):**
- **The arms** (4 pairs of 20 min, ABBA ABBA, stage2_ab's setup before each run):
  - A = the ready-made functions box as it is: xmas02sk, fly_first and fly_first_hp ON,
    fly_first_land OFF. That is 9.59's program, by the `land` proof.
  - B = the same box with fly_first_land ON.
  - Each block is set explicitly. FF_LAND_S is at 0.75 in both.
- **`plan` refuses before any input unless the arms differ only in fly_first_land:**
  - the box texts in that block alone;
  - the runner settings in it alone;
  - the argv by `--fly-first-land` alone;
  - the box arguments, keys, loop and tick equal, the box model xmas02sk;
  - the runner is 9.60, and drive, check, flag, pick and land hold;
  - the step traces equal the driver's (63 scenarios).
- Today's plan passes (rc 0; project hashes A `dde5257d...`, B `bfdb5d4a...`). The s7ab, s8ab and
  s9ab plans still pass.
- **JUDGED (FAIL if one fails, INCONCLUSIVE if none fails but one cannot be judged, else PASS):**
  1. **B's stale re-fires == 0** over its played runs. A stale re-fire is an alarm boss Fly Wing
     whose sighting (its record's `sight.t_ns`) was grabbed at or before the previous Fly Wing's
     key + its run's FF_LAND_S, from the runner's records (B's land records give every Fly Wing's
     key). It is judged when B made at least one alarm boss Fly Wing (none: INCONCLUSIVE). A's
     count is reported.
  2. deaths: B <= A over every played run (non-strict: two zero arms pass);
  3. kills/h and loot/h: mean paired (B - A) >= -2 SE (with >= 3 valid pairs);
  4. openers/h: B within +-20 % of A;
  5. the tick pace: B's median <= A's + 5 ms;
  6. kinds, errors, the drive (stage7_ab's lines).
- **The lines against the bar lessons** (no strict < against an arm at 0; tolerances above the
  noise; judge what the change can move):
  - Line 1 is the change's own line. With the switch off it is not 0: the scorer on s9ab's own
    data finds A 1, B 8 (exactly 18.16's 9), so the line FAILS when nothing changed, as it must.
  - With the switch on it is 0 by construction: the runner and the scorer compare the same
    recorded key and grab times.
  - It needs one alarm boss Fly Wing in B to be judged at all: no vacuous PASS.
  - Lines 2-6 pass when nothing changed:
    - deaths: <=, so 0 = 0 passes;
    - kills and loot: -2 SE of the paired difference, so about 98 % under no difference;
    - openers: +-20 % is about 2.3 SEs of the pooled ratio (per-run SD about 12 %, s8ab's runs);
    - the median tick: its per-run noise is under 1 ms (201.3-202.5 ms in s8ab / s9ab), so 5 ms is
      far above it.
- **REPORTED only:**
  - Fly Wings/h (by kind);
  - false boss Fly Wings/h by S7's truth (stage9_ab's);
  - the party's visits flown, and the time to the Fly Wing;
  - the sightings the floor holds (alarm detections inside a landing window);
  - deaths;
  - the economy with steals;
  - the detect ms;
  - the model each run loaded.
- **The scorer's dry run on s9ab's own series** (both arms had the switch off; read-only):
  - stale A 1 (+0.454 s), B 8 (+0.288-0.424 s), so the stale line FAILS, as it must;
  - deaths 0 / 0;
  - held alarm detections: A 7, B 23.
- **Commands (from MAIN after the merge, the worker free; about 3.5 h):**

      cd /home/bot/docker/poring-lab
      .venv/bin/python scripts/stage10_ab.py plan  --label s10ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage10_ab.py run   --label s10ab --pairs 4 --minutes 20
      .venv/bin/python scripts/stage10_ab.py score --label s10ab

- **On a PASS:** fly_first_land goes ON in the ready-made boxes, as fly_first and fly_first_hp did
  (a person's decision, 18.10's pattern). **On a FAIL:** it stays off, and Batt is told.
- **Limits:**
  - The landing measure needs monster boxes before the key: 15 of 94 teleports could not be
    measured.
  - The frames are sampled every 0.25 s, so the window carries one interval of margin.
  - A boss boxed only between the first new frame and 0.75 s is lost from that Fly Wing; none was
    in 94 teleports.

**18.16's other observation, the clear-bag stock check (report only, NOT fixed here):**
- Between r06B and r07B (and before r02B, r04A and r05A), `dungeon_hunt.py clear-bag` read Fly
  Wing 601 as 0 after the restock, while the series' own read said 10.
- The cause is a key, not the reader: clear-bag reads the hotbar slot of `CHARS_CONF["thief"]
  ["keys"]["fly"]`, which is F2 (slot 1). The ready-made box (Batt 2026-11-13: "the Fly Wing on
  F8") and the series read F8.
- The Fly Wing is no longer on F2, so slot 1 reads 0 and the check raises "the stock is short".
  The potion's slot (F1) is the same in both and read 10.
- The fix is a parameter, not a one-line read bug: clear-bag should take the box's keys (the Run's
  fly_key and heal_key) from the series. Changing CHARS_CONF would move the CLI's default keys.


### 18.18 Result of s10ab (run 2026-11-17 11:23 - 14:11 ICT, scored 14:13): PASS on every line; fly_first_land stays OFF until Batt decides ➡️ Batt 2026-11-17 ~15:0x ICT: ON in the ready-made boxes (the last item)

- **Valid:** 3 pairs of 4 (ABBA ABBA), every run rc 0, 0 deaths.
  - r08A (A) ended at 12.8 min by the runner's own stock keep ("1 Fly Wing(s) left, kept for the
    end"). That is under the 80 % share (16 min), so its pair (r07B, r08A) is out of the paired
    lines.
  - 2 of r08A's 7 boss Fly Wings were stale re-fires: the defect ended an A run early again, as it
    ended s9ab's r03B.
  - r06B ended at 19.3 min by the bag-full flow ("weight_home", stop "home"), which counts as a
    valid end. Every other run hit the time box.
- **Judged lines (18.17's bar), all PASS:**

      line                     A (land OFF)        B (land ON)         bar
      stale re-fires           4 (reported)        0 of 7 alarm boss   B == 0, >= 1 alarm boss fly
      deaths (played runs)     0 (4 runs)          0 (4 runs)          B <= A
      kills/h, paired          -                   +14.5 +- 9.3        >= -2 SE
      loot/h, paired           -                   +8.8 +- 15.0        >= -2 SE
      openers/h                124.8               121.5               within +-20 % (-2.6 %)
      pace, median tick        202.0 ms            201.7 ms            <= A + 5 ms
      kinds / errors / drive   clean               clean               no new kind, none
      the model                xmas02sk            xmas02sk            each arm's own

  - Paired kills/h (B - A): -0.3, +12.2, +31.5. Loot/h: -9.4, -2.9, +38.6.
  - The stale line was judged: B made 7 alarm boss Fly Wings, so it is not a vacuous PASS.
    - B wrote 11 land records, one per Fly Wing of every kind.
    - B held 7 alarm detections inside a landing window. On A, 16 such detections fell inside a
      window that A does not hold.
- **A's 4 stale re-fires** (grabbed 0.30-0.44 s after the previous key, acted on 1.90-2.10 s
  later; all 4 judged FALSE by the packets):
  - r04A +0.352 s (Garm Baby);
  - r05A +0.334 s (the Goblin);
  - r08A +0.440 s (the Goblin) and +0.296 s (Garm Baby).
  - These are 18.16's shape exactly: the frames still showed the old place.
- **Reported only:**
  - Fly Wings/h: A 13.1, B 8.4. Boss Fly Wings/h: A 10.1, B 5.3; HP or other: 3.0 in both.
  - False boss Fly Wings/h by S7's truth: A 7.05 (7 of 10, 0.993 h), B 3.80 (5 of 7, 1.316 h),
    all from the alarm.
    - Without A's 2 valid-run stale ones (r04A, r05A, both false): A 5 false of 8.
    - Of the 10 false boss Fly Wings in the valid runs that were not stale re-fires, 8 were on a
      Goblin box (B 5 of 5, A 3 of 5). The Goblin class is now the main source of false Fly Wings.
      This is an observation, not a change.
  - The party's visits, by the packets:
    - A 3 visits, 3 flown; to the Fly Wing median 0.35 s, max 0.52 s.
    - B 2 visits, both flown. The scorer shows "1 of 2" because of a window artefact in a
      reported line. r03B's second visit was flown 0.01 s after the visit's first packet sample:
      its knight sighting was grabbed 0.10 s BEFORE that sample, so stage9_ab's visit window
      (which starts at the first 0.25-s sample) does not contain it. The Fly Wing itself is
      judged TRUE (unit 1251 on screen).
  - potions/h A 7.0, B 2.3; steals/h 81.5 vs 88.1; eats/h 6.0 vs 6.8; lowest HP A 39 %, B 48 %.
  - The detect server's call: median 21.9 vs 21.8 ms, p95 25.0 vs 25.2 ms.
  - The economy with steals (econ_db.totals_of; 153 runs in data/econ/lab.sqlite), valid runs
    pooled:
    - gross / cost / net z/h: A 68,394 / 9,287 / 59,107 (3 runs);
    - B 64,674 / 3,286 / 61,388 (4 runs).
    - Per run 37k-84k: within the noise, not a claim.
- **The clear-bag stock check (18.17's note, still NOT fixed):** before r01A, r03B, r04A, r05A and
  r07B, clear-bag returned rc 1 because it read Fly Wing (601) as 0 on F2 while the box keeps it on
  F8. The series went on with its own read each time.
- **Decision:** none taken here. 18.17 says that on a PASS, fly_first_land goes ON in the
  ready-made boxes as a person's decision. It stays OFF (registry and every box) until Batt says
  so. The change would be the same as 17d18124 did for fly_first_hp: the functions box and its
  cookie twin get the block ON, and the reference arms keep their pinned argv.
- ➡️ **Batt's decision (2026-11-17 ~15:0x ICT, in Thai: "turn it on"): fly_first_land ON in the
  ready-made boxes, 4a4e0022** (feat/fly-first-land-on from main 12680ffb):
  - The functions box and its cookie twin hold the block ON. Their runner argv is the hunt box's
    plus `--fly-first`, `--fly-first-hp` and now `--fly-first-land`, in that order. FF_LAND_S stays
    at its default 0.75 s, so no `--tune` is passed.
  - The reference arms keep it off and their pinned argv: the one box, the hunt box, the one-box
    cookie box and the frozen A/B fixtures. The registry's default stays off.
  - The A/B tools built from the ready-made box set the block explicitly, so each plan means what
    it meant:
    - stage5c_ab's B: the hunt box's value (off);
    - stage7_ab's, stage8_ab's and stage9_ab's arms: off in both (what s7ab, s8ab and s9ab
      measured), checked by their box_difference; stage8_ab and stage9_ab also refuse
      `--fly-first-land` in a runner argv;
    - stage10_ab: A off, B on, as before.
  - The five plans (`plan --label chk --pairs 1 --minutes 20`; offline, read-only, no series
    folder) were run on main 12680ffb and on this branch. All are rc 0, and every arm's project
    hash, runner settings and run argv equal main's:

        A/B      A          B
        5c       eaac67e8   0dfd2174
        s7ab     0dfd2174   88f3234b
        s8ab     88f3234b   e3f90eeb
        s9ab     e3f90eeb   dde5257d
        s10ab    dde5257d   bfdb5d4a   (18.17's pre-registered pair)

    Only stage10_ab's A label changed: "as s10ab measured it".
