---
doc_type: design
hypothesis: null
status: "DECIDED 2026-11-13 ~21:4x (Batt): build the live block player first; one box (START > xmas_dun02); break the runner into blocks. Stage 1: BUILT 2026-11-13 ~22:3x and run live 23:01 (PASS, section 6). Stage 2 (heal and the Fly Wing as the box's events inside the hunt core): BUILT 2026-11-14 (feat/stage2, offline tests only; section 3.2); its live A/B pre-registered, NOT run yet. Stage 3 (the Knife swap, the respawn, the weight home and the way home as the box's functions and event at the runner's moments): BUILT 2026-11-14 (feat/stage3, offline tests only; section 3.3); its live A/B (the stage-2 box vs the stage-3 box) pre-registered, NOT run yet; the Knife's open question is Batt's (3.3)."
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [project-model.md, player-mode.md, ADR-0020, ../../scripts/dungeon_hunt.py, ../../scripts/runner_flow_export.py, ../../packages/poring_flow/src/poring_flow/runtime.py]
next_action: "Stage 2's A/B (3.2, scripts/stage2_ab.py) first. Then merge feat/stage3, deploy (backend, Run helper), and the A/B of section 3.3 (scripts/stage3_ab.py run; its bar pre-registered there) -- the parent runs it. Batt answers the Knife question (3.3: the strike between F4 and F5, or not)."
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
  Wing). The A/B measures that difference with the rest.

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
the same four warnings as stage 2's box) has five tabs now, its Python view:

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

**THE OPEN QUESTION FOR BATT (not decided; both are written and both play):** "press F4, wait
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
  B2 = the stage-2 box, B3 = the one box. Order B2 B3, B3 B2, ... The setup before every run is
  stage2_ab's (3.2). `plan` refuses before any input if either box cannot play, if B2 plays a
  stage-3 function or if B3 plays none.
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

Reported, not judged: loot steps per hour, the Knife openers per hour, the opener -> steal seconds
and the swap-back ms (Batt's own: the Damascus 1.36 s after the steal), the box's calls. The
verdict: FAIL when a judged line fails; INCONCLUSIVE when fewer than 3 pairs are valid (kills and
steals unjudged) and nothing failed; else PASS, with the respawn / way-home / weight lines that had
nothing to judge listed as not exercised. Why these margins: the default bodies press the same keys
at the same moments, so the Knife lines are held to the pairs' own noise, and two failed swaps an
hour is about one in a 30-min run; the exits are held to "every time".

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

