---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~21:4x (Batt): build the live block player first; one box (START > xmas_dun02); break the runner into blocks. Stage 1 BUILT and PASSED live (section 6). Stages 2, 3 and 4a BUILT 2026-11-14 and their live A/Bs RUN 2026-11-14 00:4x-09:52 ICT: all three INCONCLUSIVE by their pre-registered bars (too few valid pairs: the Stormy Knight killed her in 10 of 30 played runs), the box's survival, Knife, home, respawn and recipes proven live (sections 7-9). Batt's 2026-11-14 ~14:0x answers: the Knight -> a Fly Wing away (section 11: dungeon@9.53 --alarm-fast BUILT; the Goblin class proposed); the HP band -> the drink raised to 50 % and the candies eaten at once (section 10); the Knife question delegated to the agent -> answer (a) KEPT (section 11.3). Batt's 2026-11-14 ~15:2x ask ("no runner [page]; make them ALL blocks"): stage 5a BUILT and MERGED 2026-11-14 17:2x (section 12: every runner setting a block in the project's tabs, the Run and the check read them, the runner page and the settings file gone); 5b (the loop as playable blocks) planned, not built. The live A/B s5ab-1114 (B4 the stage-4a box vs B5 the one box, both with the fast alarm; 15:10-17:19 ICT): FAIL by its pre-registered bar on line 2 only (time under 50 % HP: B4 0.000, B5 0.003; B4 never went under 50 %), deaths 0 in 6 (last night 10 in 30), eats B5 10, the alarm 8 fires (5 true, 3 false, each a Fly Wing in <= 0.42 s) (section 10.2). Stage 5b-1 (section 13; 5b, Batt 2026-11-14 18:1x: "go on"): the runner's loop state on one HuntState object and its loop as 20 steps run by a driver, BUILT 2026-11-14 (feat/huntstate, offline only), proven the same program as eb160ee1's run() by scripts/huntstate_check.py (as ASTs); its live A/B (13.5, stage5b_ab.py) pre-registered, not run; 5b-2 (the steps as live blocks) designed (13.4), not built."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [project-model.md, player-mode.md, ADR-0020, ../../scripts/dungeon_hunt.py, ../../scripts/runner_flow_export.py, ../../packages/poring_flow/src/poring_flow/runtime.py]
next_action: "5b-1 (section 13): review feat/huntstate (huntstate_check.py check), merge before any other change to scripts/dungeon_hunt.py, deploy, then the live A/B s5b1-ab (13.5: stage5b_ab.py plan / run / score); only after it holds, 5b-2 (13.4). Earlier: Batt decides the drink threshold: 50 % cost 10 White Potions in B5's hour (about 12,100 z / h) with no dip below 41 % and none in B4 (10.2); it is one number on the drink block now. The Christmas Goblin class (11.4) waits on Batt. Section 12 (5a): a browser re-measure of the setting blocks (block widths, the phone layout, /maps' tab rows). Then 5b: the loop as playable blocks (dungeon_hunt split into steps), checked by a live A/B against today's runner."
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
| The check | `POST /flows/run/check {project, node}` (routes_flowrun `check_values`) -> request `{action: "check", flow: "project", node, keys, vals}` -> flow_run `check_start` | the backend validates the project, the node's hunt core, its keys and its setting blocks (`settings_refused`, `no_hunt_core`, `keys_refused`, `not_a_map_node`, `invalid_project`) and sends every setting block's value; the helper checks them again (`check_level`, every block named, the clash rule) and runs the runner's read-only check with them. The checklist on /flows states the same values (`startChecklist(nodeSettings(...))`) |
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
| 2 | Setting blocks cut at 390 (scale 0.6, blocks from x 135): 108 of 121; alarm_fast 447 px (57 % shown), near_single_still; main's block 397 px; the zoom buttons over REGEN_STOP's "50" and POS_FLY_S's "20", the trashcan over NPC_NO_FIGHT's "cells" | A setting block is laid out on ROWS (settings.ts `settingRows`, blockdefs `settingDef`): its words wrapped (balanced) over one or more rows, a point-or-none's at / none menu on its own row, then the value with its unit and `· var` (the var on a row of its own where that row would be too wide), then a safety switch's warning rows, then 3 rows for the lint's note. Budget: no row over 300 workspace units = 180 px at 0.6, so a block ends by x 315 px, before the trashcan's column at x 323 (390 - 20 - 47): the controls no longer cover any value, by construction. main's blocks too: the hat's title on two rows (`titleLines`), the runner's block a role a row, the save point on three. MEASURED by a model of Blockly's text widths (no browser here; Blockly's getHeightWidth needs a rendered workspace, the real-Blockly tests are headless): per-character widths of a wide sans at 12 pt, zelos' paddings FITTED to the reviewer's own numbers (npc_guard's row 430 units, with its warning 1018, alarm_fast's 745: the model gives +2.4 %, +4.5 % and +2.6 % of them: it errs wide; settings.test.ts allows -3 / +10 %). Every one of the 121 blocks' rows, the note rows' longest kinds and main's rows are under the budget (settings.test.ts). Average 2.8 rows a block |
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
`restack`), the greyed style's look in light and dark, the Python sheet at 390 (#1), the flyout's
width at 390 (#5), and the /maps page height after selecting the card (#6).

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

**The lint and the refusals** (before any input; the backend's not_live names the same): a
primitive outside a hunt core's `hunt` tab or a recipe; a loop with no block that always advances
the cursor (explore or a time-boxed one; else it would spin without time passing); a recipe's
order the cursor cannot play (wait_kill before strike, loot before wait_kill: recipes.SHAPES
today, widened only with a trace test per new shape); use_skill without a declared role key the
start's slot check reads; a common step left out (impossible to write: they have no block);
`drive` with any other hook method missing.

**5b-2's A/B:** B5b-1 (the one box, 5b-1's built-in driver) vs B5b-2 (the same box plus the hunt
tab whose loop is the canonical one): an equivalence check with 13.5's bar; only after it holds,
the first experiment in blocks (e.g. no loot(t) for the Christmas Cookie, or no Knife swap on it).

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
| the tick pace | B's median and 95th-percentile gap between hp_read records each <= A's + 10 ms (valid runs pooled) |
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
