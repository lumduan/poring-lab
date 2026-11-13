#!/usr/bin/env python3
"""Export a DESCRIPTION of a live runner as a /flows "runner flow" (Batt 2026-11-12, rogue-xmas02.md
4CQ: "make the flows of this map, so I can see how the bot works").

    runner_flow_export.py export   write services/frontend/src/lib/flow/runners/<id>.gen.ts
    runner_flow_export.py check    exit 1 when the committed file differs from a fresh export
    runner_flow_export.py show     print the Python outline (what the page shows beside the blocks)

WHAT IT IS: the xmas_dun02 Rogue's loop in scripts/dungeon_hunt.py `run`, as blocks a learner can
read (the matpilot.org/blocks studio style: the blocks with their Python side by side). The blocks,
their words and the Python outline are written HERE (SPEC below); every NUMBER in them is read from
the code at export time (dungeon_hunt.py's constants, STRATEGIES / CHARS_CONF for the base command's
--strategy / --char, value_target.py, bare_steal.py), every FLAG's help text and default from
`run`'s own argparse block (read by ast: the parser is local to main()), and every code symbol a
block names is checked to exist. A renamed constant, flag or function fails the export loudly.

WHAT IT IS NOT: the runner. The Python is an OUTLINE (valid Python, never run); the page shows it
and SIMULATES the description in the browser (a model of these rules on an example scenario).
Nothing on /flows reaches the executor, the mux or any input path. Offline: it imports
dungeon_hunt / value_target / bare_steal for their numbers and sends nothing. The output holds our
own numbers and words only (no GPL-derived values: the species' worth is read by the runner at run
time from data/econ/maps.json, never exported).
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUT_DIR = ROOT / "services" / "frontend" / "src" / "lib" / "flow" / "runners"
FORMAT = 1

# The base command: the /flows Run button's own (scripts/flow_run.py FLOWS["xmas_dun02_rogue"]; Batt
# 2026-11-13: the Knife base of rogue-xmas02.md 4DQ, played as a player). Read from flow_run.py, so
# the page can never describe another command than the one Run starts. --seed / --label vary per run
# and are left out.
sys.path.insert(0, str(SCRIPTS))
import flow_run as _fr  # noqa: E402

_RUN_FLOW = _fr.FLOWS["xmas_dun02_rogue"]


def _without_seed(argv: list[str]) -> list[str]:
    out, skip = [], False
    for tok in argv:
        if skip:
            skip = False
        elif tok == "--seed":
            skip = True
        else:
            out.append(tok)
    return out


BASE_COMMAND = [*_without_seed(list(_fr.FIXED)), "--minutes", str(_RUN_FLOW.minutes),
                *_RUN_FLOW.flags]  # fmt: skip
# The optional flag sets (not in the base). The Knife opener JOINED the base (4DQ, 2026-11-13).
OPTIONAL: list[dict[str, Any]] = []

# Block styles: MatPilot's categories (lib/flow/theme.ts) + the runner view's own (runner.ts)
S_HAT, S_SETUP, S_SENSE = "mp_start_blocks", "mp_setup_blocks", "mp_sensor_blocks"
S_MOVE, S_ACT, S_DECIDE = "mp_movement_blocks", "mp_output_blocks", "mp_function_blocks"
S_LOOP, S_IF = "loop_blocks", "logic_blocks"
S_SAFE_HAT, S_SAFE = "rd_safety_hat_blocks", "rd_safety_blocks"
S_OPT_HAT, S_OPT = "rd_optional_hat_blocks", "rd_optional_blocks"


# --- the spec's building blocks ------------------------------------------------------------------
@dataclass
class Branch:
    text: str
    py: str  # the branch's header line ("if ...:", "elif ...:", "else:")
    body: list[Node]


@dataclass
class Node:
    id: str
    kind: str  # hat | step | loop | if
    style: str
    text: str = ""  # hat / step / loop: the block's words; {param} or {param:pct} for numbers
    py: list[str] = field(default_factory=list)  # hat / loop: header lines; step: its lines
    why: str = ""
    body: list[Node] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)  # a hat's last lines (after its body)
    flags: list[str] = field(default_factory=list)
    code: list[str] = field(default_factory=list)  # symbols: name (dungeon_hunt), vt. / bs. / em.


def step(id_: str, style: str, text: str, py: list[str], why: str, flags: list[str] | None = None,
         code: list[str] | None = None) -> Node:  # fmt: skip
    return Node(id_, "step", style, text, py, why, flags=flags or [], code=code or [])


def cond(id_: str, style: str, branches: list[Branch], why: str, flags: list[str] | None = None,
         code: list[str] | None = None) -> Node:  # fmt: skip
    return Node(id_, "if", style, why=why, branches=branches, flags=flags or [], code=code or [])


# --- THE SPEC: the xmas_dun02 Rogue (dungeon_hunt.py run with BASE_COMMAND) ----------------------
# Words: plain English for a learner. Numbers: {id} placeholders only (resolved from the code). In
# the Python lines, $(id) is replaced by the value's Python literal; constant NAMES are defined at
# the outline's top with their values.
def spec() -> list[Node]:
    main = Node(
        "run",
        "hat",
        S_HAT,
        "when the run starts",
        [
            "def run():",
            '    """when the run starts: dungeon_hunt.run(a), a = the parsed command line"""',
        ],
        why="The runner starts here: `dungeon_hunt.py run` with the base command (see the Command "
        "pane). Everything below runs once, top to bottom; the loop inside it is the hunt.",
        flags=["--char", "--map", "--strategy"],
        code=["run"],
        body=[
            step(
                "identity",
                S_SETUP,
                "check who is playing: the {cmd.char}",
                [
                    "check_identity(job=$(char.job))  # the status window must name her job, else "
                    "no run"
                ],
                "Before any key is pressed, the runner reads the status window from the pixels and "
                "checks that the character on screen is the one asked for. Anything else stops the "
                "run before it starts.",
            ),
            step(
                "stock",
                S_SETUP,
                "read her stock on the hotbar: at least {PLAYER_MIN_WINGS} Fly Wings and "
                "{PLAYER_MIN_HEALS} heal items",
                [
                    "stock = hotbar_stock()  # the digits the hotbar draws: a player has no @item",
                    'if too_little(stock): stop("bring more Fly Wings / heal items first")',
                ],
                "A normal player cannot conjure items, so the run never adds any (--player-mode): "
                "it reads the counts on the hotbar and will not start with less. You bring the "
                "stock; the run uses it.",
                flags=["--player-mode"],
                code=["player_stock_refused"],
            ),
            cond(
                "weight",
                S_IF,
                [
                    Branch(
                        "the bag reads {WEIGHT_MAX:pct} % full or more (or does not read): stop "
                        "(a person lightens it)",
                        "if weight_unread() or weight_share() >= WEIGHT_MAX:  # never dropped",
                        [
                            step(
                                "weight_stop",
                                S_SETUP,
                                "stop the run",
                                ['stop("the bag is too full: a person empties it first")'],
                                "The Rogue never throws loot away (it is value for Batt's "
                                "merchant), so a "
                                "full bag stops the run instead.",
                            )
                        ],
                    )
                ],
                "At 50 % weight the server gives no natural HP / SP regeneration, so the run "
                "refuses to start this close to it. A player's run never throws loot away.",
                code=["player_weight_refused"],
            ),
            step(
                "start_here",
                S_MOVE,
                "start where she stands (on the map's open ground, within {PLAYER_POS_S} s)",
                [
                    "here = minimap_cell()  # the minimap's readout, no warp",
                    'if not on_route_grid(here): stop("walk her onto the open ground first")',
                ],
                "You put her on the map yourself, the way a player walks in. There is no warp and "
                "no GM command clears the map: the big boss may be alive, and the boss guard "
                "below escapes it with a Fly Wing.",
                flags=["--player-mode"],
                code=["player_start_refused"],
            ),
            step(
                "timebox",
                S_SETUP,
                "set the time box: {cmd.minutes} minutes",
                [
                    "t_end = time.monotonic() + $(cmd.minutes) * 60  # --minutes: the time box",
                    'mode, lock, loot_list, kills = "search", None, [], []',
                ],
                "The run lasts this long, then ends safely. `mode` is what she is doing: "
                "search, fight, or after (a fight just ended).",
                flags=["--minutes"],
            ),
            Node(
                "loop",
                "loop",
                S_LOOP,
                "repeat until the time box ends",
                ["while time.monotonic() < t_end:"],
                "The hunt: one pass of this loop is one TICK, about {READ_HZ} a second. Every "
                "tick looks at the screen, checks the safety rules, then does ONE thing: fight, "
                "loot, or search.",
                body=main_loop(),
            ),
            cond(
                "end",
                S_IF,
                [
                    Branch(
                        "time is up while hit or under {END_FLY_BELOW:pct} % HP: a Fly Wing first",
                        'if end_escape_needed(now, last_taken, hist, "time"):  # a hit within '
                        "END_HOT_S too",
                        [
                            step(
                                "end_fly",
                                S_SAFE,
                                "press the Fly Wing (F2)",
                                ['press("fly", "end")'],
                                "A safe end: the end warp takes seconds, so she teleports away "
                                "from a "
                                "fight first.",
                            )
                        ],
                    )
                ],
                "The safe end (dungeon@8.5): a run once ended inside a swarm and the character "
                "died during the end warp.",
                code=["end_escape_needed"],
            ),
            step(
                "home",
                S_MOVE,
                "go home on a Butterfly Wing ({HOME_KEY}) if the hotbar shows one",
                ["press_home_if_stocked()  # one press; none on the hotbar: she stays put"],
                "A player's way home: the Butterfly Wing takes her to her save point. The run "
                "also ends by itself when her Fly Wings fall to {PLAYER_WINGS_KEEP}: the last "
                "one stays for the escape.",
                flags=["--player-mode"],
                code=["player_home_refused"],
            ),
        ],
    )
    return [main, safety(), knife()]


def main_loop() -> list[Node]:
    look = step(
        "look",
        S_SENSE,
        "look at the screen: HP, SP, where we are, the Battle Log",
        [
            "eyes = look()  # pixels only: HP / SP %, the minimap readout, the Battle Log's new "
            "lines",
            "now, here = eyes.t, eyes.cell",
        ],
        "PIXELS IN: the HP and SP percent are read from the Basic Info window's digits, her cell "
        "from the minimap's coordinates, and the Battle Log's new lines (hits on her, her own "
        "damage, a Miss) from the chat window. Nothing reads the game's memory or packets. "
        "--late-confirm: a position read held back as doubtful is confirmed at once by a newer "
        "frame. --miss-cue: a monster's 'Miss' drawn beside her counts as an attack.",
        flags=["--late-confirm", "--miss-cue"],
        code=["late_confirm", "read_outcome"],
    )
    safe = cond(
        "safety",
        S_SAFE,
        [
            Branch(
                "check the safety rules first (the red stack): a Fly Wing ends this tick",
                "if safety_rules(eyes):  # a Fly Wing or a stop: this tick ends here",
                [
                    step(
                        "safety_skip",
                        S_SAFE,
                        "start the next tick",
                        ["continue"],
                        "After a Fly Wing she is somewhere else on the map: the target, the loot "
                        "list "
                        "and the path are forgotten and the next tick starts fresh.",
                    )
                ],
            )
        ],
        "The safety rules (on the right) run before anything else on every tick, and again "
        "inside long actions (guard_tick reads the HP between clicks).",
        code=["guard_tick"],
    )
    boxes = step(
        "boxes",
        S_SENSE,
        "see the monster boxes: the GPU detector, every {BOX_EVERY_S} s",
        [
            "boxes = box_watch.boxes(fresh_s=BOX_FRESH_S)  # the map's own model, one detection a "
            "second",
            "hud_send(hud, boxes, mode, lock is not None)  # --hud: the console's HUD, DISPLAY "
            "ONLY",
        ],
        "The box watcher runs in its own thread: about once a second it gives a fresh picture to "
        "the vision worker's GPU detector (the xmas_dun02 model) and keeps the monster boxes it "
        "finds, each with its species and the time of its picture. A box older than "
        "{BOX_FRESH_S} s is not used. --hud only SHOWS the boxes on the console; no decision "
        "reads the HUD.",
        flags=["--hud"],
        code=["BoxWatch", "hud_send", "box_species"],
    )
    engage = cond(
        "engage",
        S_IF,
        [
            Branch(
                "a fight starts: a hit on us, the HP falling, a Miss at us, or a box we can reach",
                'if mode != "fight" and (eyes.hit_on_us or eyes.hp_dropped or eyes.miss_at_us or '
                "near_box(boxes)):",
                [
                    step(
                        "fight_on",
                        S_IF,
                        "switch to fight mode",
                        ['mode, fight_t0 = "fight", now'],
                        "--loot-first: right after a kill a box alone does not start the next "
                        "fight while "
                        "that kill's loot is still waiting (a hit on her still does).",
                        flags=["--loot-first"],
                        code=["box_engage_held"],
                    )
                ],
            )
        ],
        "Four signs start a fight: a hit on her in the Battle Log, her HP falling {HP_DROP_PTS} "
        "points within {HP_DROP_S} s, a Miss drawn at her, or a monster box anywhere on the "
        "screen (--engage-screen) that the server would walk her to in one click (--reach-check: "
        "at most 17 steps). The box watcher's own cell (her body) is never a target.",
        flags=["--engage-screen", "--reach-check"],
        code=["hp_dropped", "reach_ok", "self_box"],
    )
    return [
        look,
        safe,
        boxes,
        engage,
        cond(
            "modes",
            S_IF,
            [
                Branch("if we are fighting", 'if mode == "fight":', fight()),
                Branch("else, if a fight just ended: loot", 'elif mode == "after":', after()),
                Branch("else: search for monsters", "else:", search()),
            ],
            "Each tick does ONE of three things, by `mode`.",
        ),
    ]


def fight() -> list[Node]:
    kill = cond(
        "killgap",
        S_DECIDE,
        [
            Branch(
                "an EXP or Job EXP line in the Battle Log: it died (FIRST)",
                "if exp_line and exp_kill(exp_line.type, now, pair)[0]:  # EXP_PAIR_S",
                [
                    step(
                        "kill_exp",
                        S_DECIDE,
                        "count the kill; its cells join the loot list",
                        [
                            "kills.append(now)",
                            "loot_list.append((here, now))  # the 5 x 5 cells around her",
                            "lock = None",
                        ],
                        "Batt's rule (2026-11-12): when the game prints an EXP or Job EXP line, "
                        "the monster is dead -- this is checked FIRST. One kill prints both lines, "
                        "so the second within {EXP_PAIR_S} s is the same kill.",
                    )
                ],
            ),
            Branch(
                "else, no exp line in this game: {KILL_GAP_HITS}+ of our hits, then none for "
                "{KILL_GAP_S} s: it died",
                "elif not exp_seen and kill_gapped(lock.hits, now - lock.last_hit):",
                [
                    step(
                        "kill",
                        S_DECIDE,
                        "count the kill; its cells join the loot list",
                        [
                            "kills.append(now)",
                            "loot_list.append((here, now))  # the 5 x 5 cells around her",
                            "lock = None",
                        ],
                        "Items drop where the monster died, close to her: the 5 x 5 cells around "
                        "her cell at the kill are remembered for the loot step.",
                    )
                ],
            ),
            Branch(
                "no hit of ours for {LOCK_NO_HIT_S} s: let it go",
                "elif now - max(lock.last_hit, lock.t) > LOCK_NO_HIT_S:",
                [
                    step(
                        "unlock",
                        S_DECIDE,
                        "forget the target",
                        ["lock = None"],
                        "The target walked off or was never reached: look for another one.",
                    )
                ],
            ),
        ],
        "--exp-first (ON by default, Batt 2026-11-12): an EXP / Job EXP line is the kill. "
        "Where the game prints none (the lab's Base 99 Rogue: its 2021 client hides EXP 0; the "
        "Thai server's client prints EXP '0'), --kill-gap: at Base 99 the Battle Log shows no "
        "experience line, so the runner cannot SEE a "
        "kill. It infers one: her hits on a living monster come about every half second, so after "
        "{KILL_GAP_HITS} or more hits a silence of {KILL_GAP_S} s means it died. (A real kill "
        "took 3-22 "
        "hits in the pilots; 5 keeps nearly all real kills and few false ones.)",
        flags=["--kill-gap"],  # --exp-first is ON by default: in no command line
        code=["exp_kill", "kill_gapped"],
    )
    choose = step(
        "choose",
        S_DECIDE,
        "choose the box worth the most: value / (1 + distance / {vt.D0_PX} px)",
        ["target = value_pick(candidates(boxes), SPECIES_VALUES)  # ties: the nearer one"],
        "--value-target (in the base since 2026-11-12, Batt): not simply the nearest box, but the "
        "one worth the most a kill, discounted by distance. A monster's worth is what its drops "
        "sell for at the NPC (read at run time from data/econ/maps.json, by the detector's "
        "species). Example: a box worth 3 times as much wins up to about {vt.D0_PX} x 2 px "
        "farther away. The candidates are the same as before: on the screen, reachable, not "
        "her own body.",
        flags=["--value-target", "--box-strike", "--box-now"],
        code=["value_pick", "vt.pick", "vt.score", "box_target"],
    )
    approach = cond(
        "approach",
        S_MOVE,
        [
            Branch(
                "{APPROACH_CELLS}+ cells away: walk to {APPROACH_KEEP} cells short of it, then "
                "look again",
                "if target and target.cells >= APPROACH_CELLS:  # at most APPROACH_MAX times a "
                "fight",
                [
                    step(
                        "approach_walk",
                        S_MOVE,
                        "walk toward it",
                        [
                            "walk_click(approach_cell(target.rel, APPROACH_KEEP))",
                            "continue  # the box path looks again once that walk has ended",
                        ],
                        "One click that far rarely carried: she walks closer first, then the box "
                        "path looks "
                        "again with a fresh detection.",
                    )
                ],
            )
        ],
        "--far-approach: strikes 9+ cells away missed 26 of 28 times in a pilot.",
        flags=["--far-approach"],
        code=["approach_cell"],
    )
    still = step(
        "still",
        S_SENSE,
        "wait for a still screen; a walking target: wait until it stands ({HOLD_MAX_S} s max)",
        ["aim = still_target(target)  # --still-strike + --still-target"],
        "--still-strike: while she walks, the screen scrolls and a click lands where the monster "
        "WAS; so she waits for a still scene ({STILL_N} frame pairs moving under {STILL_PX} px, at "
        "most {STILL_MAX_S} s). --still-target: one more detection of the same monster; if its "
        "feet moved {WALKER_PX} px or more it is walking, and she waits (a detection every "
        "{HOLD_GAP_S} s) until it stands.",
        flags=["--still-strike", "--still-target"],
        code=["wait_still", "press_decide", "hold_track"],
    )
    lead = step(
        "lead",
        S_DECIDE,
        "a fast walker ({LEAD_PX}+ px): aim where it will be (at most {LEAD_CAP_CELLS} cell)",
        ["aim = press_lead(target, aim)  # its speed x (LEAD_AGE_S + the time since the picture)"],
        "--lead-press: instead of waiting for a fast walker, aim ahead of it, by its speed times "
        "the time until the client acts on the click ({LEAD_AGE_S} s plus the time already "
        "spent), at most {LEAD_CAP_CELLS} cell ahead.",
        flags=["--lead-press"],
        code=["press_lead", "lead_cap"],
    )
    strike = cond(
        "strike",
        S_ACT,
        [
            Branch(
                "strike: hover it, click on a SWORD cursor ({FAR_CELLS}+ cells: one click, wait "
                "{FAR_MAX_S} s max)",
                "if aim and strike(*aim):  # hover, read the cursor: a SWORD -> click",
                [
                    step(
                        "lock_on",
                        S_ACT,
                        "lock on: count our hits from now",
                        ["lock = Lock(t=now)"],
                        "The strike connected (the client's lock arrow or her first damage line): "
                        "from now on her hits are counted for the kill gap.",
                    )
                ],
            ),
            Branch(
                "no box: damage in the last {QUIET_SCAN_S} s? scan the cells around us",
                "elif scan_needed(now, last_taken, last_ours, last_swing, eyes.hp_dropped):",
                [
                    step(
                        "ring_scan",
                        S_SENSE,
                        "hover the 8 cells around her; strike a SWORD",
                        [
                            'found = scan("defend", ring(1), "sword")  # --self-recheck on her '
                            "own sprite",
                            "if found and strike(*found):",
                            "    lock = Lock(t=now)",
                        ],
                        "Something hits her but no box shows it: the pointer visits the cells "
                        "around "
                        "her and strikes where the cursor turns into a SWORD. --self-recheck: a "
                        "sword "
                        "read on top of her own sprite counts only if it is still there "
                        "{SELF_RECHECK_S} s later.",
                        flags=["--self-recheck"],
                        code=["scan", "ring"],
                    )
                ],
            ),
        ],
        "The pointer hovers the target's body; the client draws a SWORD cursor over a monster, and "
        "only then does she click. --far-single: from {FAR_CELLS} cells away she clicks ONCE and "
        "waits up to {FAR_MAX_S} s (the client walks her there); a re-click would land on the "
        "floor "
        "and cancel the walk. Close up the click repeats every {BURST_GAP_S} s until it connects. "
        "--quiet-scan: the ring scan runs only after damage in the last {QUIET_SCAN_S} s.",
        flags=["--far-single", "--quiet-scan"],
        code=["strike", "far_window", "scan_needed"],
    )
    quiet = cond(
        "quiet",
        S_IF,
        [
            Branch(
                "no hit on us for {FIGHT_TAKEN_S} s and our target died: the fight is over",
                "if lock is None and quiet(eyes) and quiet_kill_ends(kills, now, fight_t0, True):",
                [
                    step(
                        "fight_over",
                        S_IF,
                        "switch to after-the-fight",
                        ['mode = "after"'],
                        "--loot-first: only a kill that came during THIS fight ends it, so a "
                        "fight that "
                        "started right after a kill is not ended by that kill.",
                        flags=["--loot-first"],
                    )
                ],
            )
        ],
        "A quiet fight with a recent kill ends at once: no long scan for monsters that are not "
        "there.",
        code=["quiet_kill_ends"],
    )
    no_target = [choose, approach, still, lead, strike]
    return [
        cond(
            "locked",
            S_IF,
            [
                Branch("if we have a target (locked on)", "if lock is not None:", [kill]),
                Branch("else: no target yet", "else:", no_target),
            ],
            "Locked on = a strike connected and she is hitting it.",
        ),
        quiet,
    ]


def after() -> list[Node]:
    return [
        step(
            "loot",
            S_ACT,
            "loot: hover the kills' cells nearest first ({LOOT_TRIM_HOVERS} at most); click a "
            "pickup hand",
            [
                "loot_step_v1(loot_list, fight_ref)  # --loot trim: LOOT_TRIM_HOVERS hovers, no "
                "sweep"
            ],
            "The loot list's cells (the 5 x 5 around her at each kill of the fight) are hovered "
            "nearest first. Over an item the client draws a PICKUP hand: she clicks there (the "
            "client walks her over and picks it up). A SWORD there starts a fight instead. "
            "--loot trim stops after {LOOT_TRIM_HOVERS} hovers (in the pilots nearly every "
            "pickup came within the first 9), at most {LOOT_MAX_PICKS} picks and {LOOT_MAX_S} s; "
            "a hit on her ends the loot step.",
            flags=["--loot", "--loot-first"],
            code=["loot_step_v1", "pickup_seen"],
        ),
        step(
            "search_again",
            S_IF,
            "back to searching",
            ['loot_list, mode = [], "search"'],
            "The loot step happens once per fight.",
        ),
    ]


def search() -> list[Node]:
    explore = step(
        "explore",
        S_MOVE,
        "explore: aim for a region of the map worth a visit",
        [
            "goal = explore_goal(here)  # --search patrol --explore: explore + exploit",
            "path = route(okr, carved, here, goal)",
        ],
        "--explore: the map is cut into regions; she walks to one chosen from what earlier runs "
        "saw there (time spent, fights, good fights, stalls; data/maps/xmas_dun02/explore.json) "
        "plus a chance for less-visited ones. On arrival, or after {EXPLORE_LEG_MAX_S} s, she "
        "picks the next. The run's own knowledge is merged into the file at its end.",
        flags=["--search", "--explore"],
        code=["explore_goal", "route", "em.choose", "em.scores"],
    )
    pick = step(
        "walk_pick",
        S_SENSE,
        "the walk target: {WALK_AHEAD} cells ahead, where the client picks that cell",
        [
            "cell = walk_target(path, WALK_AHEAD, fits)  # --walk-pick: picked_cell() within "
            "WALK_PICK_TOL",
            "verdict = hover(cell)  # the cursor there: walk, sword, noentry or unknown",
        ],
        "--walk-pick: on raised floors the client may pick a DIFFERENT cell under the pointer "
        "than the one meant; a walk target counts only when the client's own pick (the camera "
        "ray's first tile top) is within {WALK_PICK_TOL} cell of it. --walk-pick-step: when no "
        "path cell passes, a nearby cell that does. Never a click straight north of her (the "
        "client sends no move for those). The pointer first HOVERS the cell and reads the cursor.",
        flags=["--walk-pick", "--walk-pick-step"],
        code=["walk_target", "picked_cell", "walk_pick_ok", "pick_step", "column_dodge"],
    )
    cursor = cond(
        "cursor",
        S_IF,
        [
            Branch(
                "the cursor shows WALK (or the cell is trusted): click",
                'if verdict == "walk" or walk_trusted(cell):',
                [
                    step(
                        "walk_click",
                        S_MOVE,
                        "click there: she walks",
                        ["click_at(cell)"],
                        "--walk-trust: an UNKNOWN cursor read on a cell the route trusts is "
                        "clicked too.",
                        flags=["--walk-trust"],
                    )
                ],
            ),
            Branch(
                "it shows a SWORD: a monster is there, strike it",
                'elif verdict == "sword":',
                [
                    step(
                        "walk_sword",
                        S_ACT,
                        "strike there",
                        ["strike(cell)"],
                        "A monster stood under the walk target: it is struck where it stands.",
                    )
                ],
            ),
            Branch(
                "it shows NO-ENTRY: carve that cell off the route",
                'elif verdict == "noentry":',
                [
                    step(
                        "carve",
                        S_MOVE,
                        "carve the cell; the route plans again",
                        ["carve(carved, cell, NOENTRY_CARVE_R)"],
                        "The client calls it a wall: that cell leaves her route grid for the run.",
                    )
                ],
            ),
        ],
        "Reading the cursor first means she never clicks blind.",
        code=["carve"],
    )
    walk = cond(
        "walk",
        S_IF,
        [
            Branch(
                "every {WALK_EVERY_S} s: the next walk click",
                "if now - last_walk >= WALK_EVERY_S:",
                [pick, cursor],
            )
        ],
        "A walk decision takes about 0.9 s and a 5-6 cell walk about 0.9 s, so at this rhythm "
        "she stands for a moment before the next click.",
    )
    return [explore, walk]


def safety() -> Node:
    def fly(id_: str, why_: str) -> Node:
        return step(
            id_,
            S_SAFE,
            "press the Fly Wing (F2): this tick ends",
            [f'press("fly", "{why_}")  # a same-map teleport, far from here', "return True"],
            "A Fly Wing teleports her to a random spot on the same map.",
        )

    return Node(
        "safety_rules",
        "hat",
        S_SAFE_HAT,
        "on every tick, before anything else",
        [
            "def safety_rules(eyes) -> bool:",
            '    """the guards run() checks first on every tick; True = this tick ends"""',
        ],
        "The safety rules are not a separate program: run() checks them at the top of every "
        "tick (and guard_tick() reads the HP inside long actions such as a strike's clicks or "
        "the loot hovers). Shown as their own stack so they are easy to read.",
        tail=["return False"],
        body=[
            cond(
                "stock_out",
                S_SAFE,
                [
                    Branch(
                        "a hotbar count reads 0 after a press: end the run",
                        "if stock_out(hotbar_counts) is not None:  # re-read STOCK_READ_S after "
                        "each press",
                        [
                            step(
                                "stock_stop",
                                S_SAFE,
                                "end the run (no escape left)",
                                ['raise Stop("stock_out")'],
                                "With no Fly Wing left there is no escape, so the run ends.",
                            )
                        ],
                    )
                ],
                "After every potion or Fly Wing the hotbar's count is read again "
                "({STOCK_READ_S} s later).",
                code=["stock_out"],
            ),
            cond(
                "dead_jump",
                S_SAFE,
                [
                    Branch(
                        "dead, or a jump of {JUMP_CELLS}+ cells we did not make: stop",
                        "if eyes.dead or is_jump(here, eyes.cell, eyes.since_s):  # a map change?",
                        [
                            step(
                                "hard_stop",
                                S_SAFE,
                                "stop the run",
                                ['raise Stop("death" if eyes.dead else "hard_bar: position jump")'],
                                "A death is a result: recorded, then the dialog closes by its "
                                "known button. "
                                "A jump nobody asked for may be a map change: never act on an "
                                "unknown map.",
                            )
                        ],
                    )
                ],
                "Hard bars stop the run.",
                code=["is_jump"],
            ),
            cond(
                "wing_hp",
                S_SAFE,
                [
                    Branch(
                        "HP under {strategy.fly_below:pct} %, or falling {strategy.fly_rate} HP/s "
                        "under "
                        "{strategy.fly_rate_below:pct} %: escape",
                        'if eyes.hp < STRATEGY["fly_below"] or (rate_hp_s(hist, now) or 0) > '
                        'STRATEGY["fly_rate"] '
                        'and eyes.hp < STRATEGY["fly_rate_below"]:',
                        [fly("wing_hp_fly", "hp")],
                    )
                ],
                "Strategy {cmd.strategy} (the swarm escape): low HP, or HP falling fast "
                "(measured over 2 s against her max HP {char.max_hp}) while under half: she "
                "teleports away before a swarm can kill her.",
                flags=["--strategy"],
                code=["sustain", "rate_hp_s"],
            ),
            cond(
                "potion",
                S_SAFE,
                [
                    Branch(
                        "HP under {strategy.potion_below:pct} %: drink a potion",
                        'if eyes.hp < STRATEGY["potion_below"]:  # 0.7 s apart, at most 3 in 2 s',
                        [
                            step(
                                "drink",
                                S_SAFE,
                                "press the potion key (F1)",
                                ['press("potion", "hp")'],
                                "One press; the next only 0.7 s later (or at once if the HP "
                                "rose), at most "
                                "3 in 2 s.",
                            )
                        ],
                    )
                ],
                "No sitting to rest in this strategy: potions keep her going.",
                code=["sustain"],
            ),
            cond(
                "garm",
                S_SAFE,
                [
                    Branch(
                        "a Garm Baby box in {cmd.garm_confirm} detections in a row: escape at once",
                        "if alarm_seen(boxes.alarm, now, streak=boxes.alarm_n, "
                        "need=$(cmd.garm_confirm)):",
                        [
                            step(
                                "garm_avoid",
                                S_SAFE,
                                "no box fights for {BOSS_AVOID_S} s",
                                ["boss_until = now + BOSS_AVOID_S"],
                                "After the escape, boxes start no fight for a while.",
                            ),
                            fly("garm_fly", "boss"),
                        ],
                    )
                ],
                "--garm-fly: the boss's summon (it hits hard and chases far) is a class of the "
                "detector; seeing it in a fresh detection ({GARM_FRESH_S} s old at most) is "
                "enough to fly away BEFORE it reaches her. --garm-confirm: {cmd.garm_confirm} "
                "detections in a row, so one false box does not waste a Fly Wing.",
                flags=["--garm-fly", "--garm-confirm"],
                code=["alarm_seen", "alarm_streak"],
            ),
            cond(
                "boss",
                S_SAFE,
                [
                    Branch(
                        "a boss name in the Battle Log: escape",
                        "if boss_of(eyes.name_read, bosses, species):  # the map's boss and its "
                        "summons",
                        [
                            step(
                                "boss_avoid",
                                S_SAFE,
                                "no box fights for {BOSS_AVOID_S} s",
                                ["boss_until = now + BOSS_AVOID_S"],
                                "After the escape, boxes start no fight for a while.",
                            ),
                            fly("boss_fly", "boss"),
                        ],
                    )
                ],
                "The boss guard of --engage-screen: the detector has no class for the boss "
                "itself (yet), so its name in a Battle Log line (read from the map's knowledge "
                "base) is the backstop.",
                flags=["--engage-screen"],
                code=["boss_of", "boss_names"],
            ),
            cond(
                "ui_watch",
                S_SAFE,
                [
                    Branch(
                        "every {UI_EVERY_S} s (not in a fight): check the screen's windows and "
                        "the weight",
                        'if now - last_ui >= UI_EVERY_S and mode != "fight":',
                        [
                            step(
                                "ui_check",
                                S_SAFE,
                                "an unknown window stops the run; read the weight",
                                [
                                    'if client_state() != "clear":  # never click into an unknown '
                                    "state",
                                    '    raise Stop("hard_bar: unknown UI state")',
                                    "w_share = weight_share()  # at REGEN_STOP no natural regen",
                                ],
                                "An open dialog or window nobody expected means the clicks could "
                                "go "
                                "somewhere unsafe: stop. At {REGEN_STOP:pct} % weight the server "
                                "gives no "
                                "natural regeneration.",
                            )
                        ],
                    )
                ],
                "The UI watch.",
                code=["overweight_red"],
            ),
            cond(
                "pos_unread",
                S_SAFE,
                [
                    Branch(
                        "no position read for {POS_FLY_S} s: a Fly Wing (at most {POS_FLY_MAX} a "
                        "run)",
                        "if now - last_pos_t > POS_FLY_S and pos_flies < POS_FLY_MAX:",
                        [fly("pos_fly", "pos_unread")],
                    )
                ],
                "When the minimap's coordinates cannot be read (a bright background behind "
                "them), a teleport gives the readout a new background.",
            ),
            step(
                "npc_guard",
                S_SAFE,
                "no strike or loot click within {NPC_NO_FIGHT} cells of an NPC",
                [
                    "# --npc-guard: npc_guard_blocks() refuses those clicks (a strike once opened "
                    "a dialog)"
                ],
                "--npc-guard: a click near a script NPC can open its dialog; within "
                "{NPC_NO_FIGHT} cells of one she does not strike or loot.",
                flags=["--npc-guard"],
                code=["npc_guard_blocks"],
            ),
        ],
    )


def knife() -> Node:
    return Node(
        "knife_opener",
        "hat",
        S_OPT_HAT,
        "Batt's technique, ON in this flow: the Knife opener",
        [
            "def knife_opener(eyes):",
            '    """--bare-steal --bare-ready --steal-opener F4 --steal-cue popup --swap-gap"""',
        ],
        "Batt's own technique (his 2026-11-12 run: a steal on 91 % of kills), in the base since "
        "rogue-xmas02.md 4DQ (a steal on 78 % of kills, common items +8 % an hour). The Rogue's "
        "Snatcher steals when she HITS, so a weak first weapon keeps the monster alive for more "
        "hits, and more steals; once it stole, the dagger goes back on to kill fast. The swaps "
        "are hotbar keys, each read back from the hotbar's pixels.",
        flags=["--bare-steal", "--bare-ready", "--steal-opener", "--swap-gap"],
        body=[
            cond(
                "knife_on",
                S_OPT,
                [
                    Branch(
                        "idle (after the loot, no target): put the Knife on ({cmd.steal_opener})",
                        "if idle(mode, lock) and not knife_worn():  # --bare-ready: never at the "
                        "strike",
                        [
                            step(
                                "press_knife",
                                S_OPT,
                                "press {cmd.steal_opener}",
                                [
                                    "press($(cmd.steal_opener))  # read back: its slot empty, the "
                                    "dagger in the bag"
                                ],
                                "The swap happens while nothing else is going on, so the next "
                                "strike is "
                                "not delayed.",
                            )
                        ],
                    )
                ],
                "--bare-ready + --steal-opener.",
                flags=["--bare-ready", "--steal-opener"],
                code=["bare_idle"],
            ),
            step(
                "knife_hit",
                S_OPT,
                "the next target is hit with the Knife: Snatcher steals",
                ["# strike() as usual: a weak hit keeps it alive longer, so more chances to steal"],
                "The strike itself does not change.",
                flags=["--bare-steal"],
            ),
            cond(
                "knife_off",
                S_OPT,
                [
                    Branch(
                        "a steal cue, {bs.BARE_MAX_S} s, or HP under {bs.BARE_HP_MIN:pct} %: the "
                        "dagger back on",
                        "if steal_cue() or now - knife_t > BARE_MAX_S or eyes.hp < BARE_HP_MIN:",
                        [
                            step(
                                "press_dagger",
                                S_OPT,
                                "press {bs.EQUIP_KEY}",
                                ["press($(bs.EQUIP_KEY))  # the dagger on again, read back"],
                                "Also before any escape and at the run's end: she never flees or "
                                "ends "
                                "with the Knife on.",
                            )
                        ],
                    )
                ],
                "The steal cue is the item popup (or a new cyan Battle Log line): no words are "
                "read. After {bs.BARE_MAX_S} s without a steal, or under "
                "{bs.BARE_HP_MIN:pct} % HP, the dagger goes back on anyway.",
                flags=["--bare-steal"],
                code=["bs.cyan_new", "bs.popup_new"],
            ),
            step(
                "swap_gap",
                S_OPT,
                "a swap restarts the no-hit clocks",
                ["last_ours = max(last_ours, swap_t)  # --swap-gap"],
                "--swap-gap: her hit lines pause during a swap; without this the kill gap would "
                "call the monster dead while she was only changing weapons.",
                flags=["--swap-gap"],
            ),
        ],
    )


# --- the numbers -------------------------------------------------------------------------------
@dataclass
class Param:
    id: str
    get: Callable[[Ctx], Any]
    source: str
    note: str


@dataclass
class Ctx:
    dh: Any
    vt: Any
    bs: Any
    cmd: dict[str, Any]

    @property
    def strategy(self) -> dict[str, Any]:
        return dict(self.dh.STRATEGIES[self.cmd["strategy"]])

    @property
    def char(self) -> dict[str, Any]:
        return dict(self.dh.CHARS_CONF[self.cmd["char"]])


def const(name: str, note: str, mod: str = "dh") -> Param:
    pid = name if mod == "dh" else f"{mod}.{name}"
    file_ = {"dh": "dungeon_hunt.py", "vt": "value_target.py", "bs": "bare_steal.py"}[mod]
    return Param(pid, lambda c: getattr(getattr(c, mod), name), f"{file_}: {name}", note)


def params(cmd: dict[str, Any]) -> list[Param]:
    s, ch = cmd["strategy"], cmd["char"]
    out = [
        Param(
            f"cmd.{k}",
            lambda c, k=k: c.cmd[k],
            f"the base command: --{k.replace('_', '-')}",
            "as the night pilots ran it",
        )
        for k in sorted(cmd)
    ]
    for k, note in (("potion_below", "HP share under which a potion is pressed"),
                    ("fly_below", "HP share under which a Fly Wing is pressed"),
                    ("fly_rate", "HP lost a second (over 2 s) that counts as a swarm"),
                    ("fly_rate_below", "... while the HP share is under this")):  # fmt: skip
        out.append(
            Param(
                f"strategy.{k}",
                lambda c, k=k: c.strategy[k],
                f'dungeon_hunt.py: STRATEGIES["{s}"]["{k}"]',
                note,
            )
        )
    for k, note in (("job", "the job the identity check expects"),
                    ("max_hp", "her max HP (the HP-rate trigger)"),
                    ("etc_hold_max", "the weight share the setup refuses at")):  # fmt: skip
        out.append(
            Param(
                f"char.{k}",
                lambda c, k=k: c.char[k],
                f'dungeon_hunt.py: CHARS_CONF["{ch}"]["{k}"]',
                note,
            )
        )
    out += [
        Param(
            "derived.potions",
            lambda c: c.dh.potions_target(c.strategy, c.char),
            f'dungeon_hunt.py: potions_target(STRATEGIES["{s}"], CHARS_CONF["{ch}"])',
            "the run's potion stock (her own count outranks the strategy's)",
        ),
        Param(
            "derived.wings",
            lambda c: int(c.strategy.get("wings_to") or c.char["wings_to"]),
            f'dungeon_hunt.py run(): int(STRATEGIES["{s}"].get("wings_to") or '
            f'CHARS_CONF["{ch}"]["wings_to"])',
            "the run's Fly Wing stock",
        ),
        Param(
            "PATROL_START.x",
            lambda c: c.dh.PATROL_START[c.cmd["map"]][0][0],
            f'dungeon_hunt.py: PATROL_START["{cmd["map"]}"][0][0]',
            "the patrol start's x",
        ),
        Param(
            "PATROL_START.y",
            lambda c: c.dh.PATROL_START[c.cmd["map"]][0][1],
            f'dungeon_hunt.py: PATROL_START["{cmd["map"]}"][0][1]',
            "the patrol start's y",
        ),
        const("READ_HZ", "ticks a second (the loop's rhythm)"),
        const("PLAYER_MIN_WINGS", "--player-mode: Fly Wings on the hotbar to start at least"),
        const("PLAYER_MIN_HEALS", "--player-mode: heal items on the hotbar to start at least"),
        const("PLAYER_WINGS_KEEP", "--player-mode: the run ends at this many Fly Wings"),
        const("PLAYER_POS_S", "--player-mode: her cell must read within this long (s)"),
        const("WEIGHT_MAX", "the weight share a run refuses to start at"),
        const("HOME_KEY", "the Butterfly Wing's hotbar key"),
        const("FIGHT_TAKEN_S", "a hit on her within this long = still in a fight (s)"),
        const("HP_DROP_PTS", "HP percent points falling ..."),
        const("HP_DROP_S", "... within this long (s) = a hit the log did not show"),
        const("BOX_EVERY_S", "the box watcher's rhythm (s)"),
        const("BOX_FRESH_S", "a box older than this is not used (s)"),
        const("EXP_PAIR_S", "a Base and a Job EXP line this close = one kill (s)"),
        const("KILL_GAP_S", "no hit of ours for this long after KILL_GAP_HITS = the kill (s)"),
        const("KILL_GAP_HITS", "our hits on the target before the gap counts"),
        const("LOCK_NO_HIT_S", "locked, but none of our hits for this long: let go (s)"),
        const("D0_PX", "the distance (px) that halves a box's worth", "vt"),
        const("APPROACH_CELLS", "a target this many cells away is walked toward first"),
        const("APPROACH_KEEP", "the approach walk stops this many cells short"),
        const("APPROACH_MAX", "approach walks a fight at most"),
        const("STILL_PX", "the screen moved less than this (px) = still ..."),
        const("STILL_N", "... this many frame pairs in a row"),
        const("STILL_MAX_S", "the wait for a still screen at most (s)"),
        const("WALKER_PX", "a target's feet moving this far between detections = walking (px)"),
        const("HOLD_GAP_S", "a held target's detections: one every this long (s)"),
        const("HOLD_MAX_S", "a hold's backstop (s)"),
        const("LEAD_PX", "feet moving this far = struck ahead, not held (px)"),
        const("LEAD_AGE_S", "the picture-to-client delay the lead covers (s)"),
        const("LEAD_CAP_CELLS", "the lead at most this many cells"),
        const("FAR_CELLS", "from this many cells away: one click, no re-click"),
        const("FAR_MAX_S", "a far click's wait for the arrow / damage at most (s)"),
        const("BURST_GAP_S", "close up, the re-click rhythm (s)"),
        const("QUIET_SCAN_S", "the ring scan only after damage within this long (s)"),
        const("SELF_RECHECK_S", "a sword on her own sprite read again after this long (s)"),
        const("LOOT_TRIM_HOVERS", "--loot trim: hovers per loot step at most"),
        const("LOOT_MAX_PICKS", "pickups per loot step at most"),
        const("LOOT_MAX_S", "a loot step's time at most (s)"),
        const("EXPLORE_LEG_MAX_S", "a region not reached by then is given up (s)"),
        const("WALK_AHEAD", "the walk click's target: this many path cells ahead"),
        const("WALK_EVERY_S", "seconds between walk decisions"),
        const("WALK_PICK_TOL", "the client's pick within this many cells of the target"),
        const("NOENTRY_CARVE_R", "a no-entry carves this radius (0 = one cell)"),
        const("END_HOT_S", "at the end: a hit within this long = a Fly Wing first (s)"),
        const("END_FLY_BELOW", "at the end: under this HP share = a Fly Wing first"),
        const("STOCK_READ_S", "the hotbar count is re-read this long after a press (s)"),
        const("JUMP_CELLS", "a jump this large without our Fly Wing = a map change"),
        const("GARM_FRESH_S", "an alarm box at most this old (s)"),
        const("BOSS_AVOID_S", "after a boss escape, no box fights for this long (s)"),
        const("UI_EVERY_S", "the UI watch's rhythm (s)"),
        const("REGEN_STOP", "the weight share with no natural regen"),
        const("POS_FLY_S", "no position read for this long = a Fly Wing (s)"),
        const("POS_FLY_MAX", "such Fly Wings a run at most"),
        const("NPC_NO_FIGHT", "--npc-guard: no fight click within this many cells of an NPC"),
        const("BARE_MAX_S", "the opener on this long with no steal cue: the dagger back (s)", "bs"),
        const("BARE_HP_MIN", "under this HP share the dagger goes back at once", "bs"),
        const("EQUIP_KEY", "the hotbar key holding the dagger", "bs"),
    ]
    return out


# --- the command and the flags -----------------------------------------------------------------
def run_flags(dh: Any, path: Path) -> dict[str, dict[str, Any]]:
    """`run`'s argparse flags from main()'s source (the parser is local to main): each flag's
    dest, help text, default (a constant name resolved on the module), kind and type."""
    tree = ast.parse(path.read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    out: dict[str, dict[str, Any]] = {}
    for call in ast.walk(main):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "add_argument" and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "t" and call.args
                and isinstance(call.args[0], ast.Constant)):  # fmt: skip
            continue
        flag = str(call.args[0].value)
        kw = {k.arg: k.value for k in call.keywords if k.arg}
        default: Any = None
        if "default" in kw:
            d = kw["default"]
            default = getattr(dh, d.id) if isinstance(d, ast.Name) else ast.literal_eval(d)
        action = kw.get("action")
        boolean = isinstance(action, ast.Attribute) and action.attr == "BooleanOptionalAction"
        typ = kw.get("type")
        help_ = kw.get("help")
        out[flag] = {
            "dest": flag[2:].replace("-", "_"),
            "help": None if help_ is None else str(ast.literal_eval(help_)).replace("%%", "%"),
            "default": default,
            "kind": "bool" if boolean else "value",
            "type": typ.id if isinstance(typ, ast.Name) else None,
        }
    return out


def parse_command(tokens: list[str], flags: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The command's values by dest, typed as the parser types them; every flag must exist."""
    out: dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        f = tokens[i]
        if f not in flags:
            raise SystemExit(f"runner_flow_export: {f} is not a flag of dungeon_hunt.py run")
        spec_ = flags[f]
        if spec_["kind"] == "bool":
            out[spec_["dest"]] = True
            i += 1
            continue
        raw = tokens[i + 1]
        out[spec_["dest"]] = {"float": float, "int": int}.get(spec_["type"] or "", str)(raw)
        i += 2
    return out


def flag_names(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t.startswith("--")]


# --- the Python outline ------------------------------------------------------------------------
def py_lit(v: Any) -> str:
    """A Python literal of ``v`` (double-quoted strings, as ruff formats)."""
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, bool) or v is None:
        return repr(v)
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, tuple):
        inner = ", ".join(py_lit(x) for x in v)
        return f"({inner},)" if len(v) == 1 else f"({inner})"
    if isinstance(v, list):
        return "[" + ", ".join(py_lit(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{py_lit(k)}: {py_lit(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"no literal for {type(v).__name__}")


def json_val(v: Any) -> Any:
    if isinstance(v, tuple):
        return [json_val(x) for x in v]
    if isinstance(v, list):
        return [json_val(x) for x in v]
    if isinstance(v, dict):
        return {str(k): json_val(x) for k, x in v.items()}
    return v


def shown(v: Any, fmt: str | None) -> str:
    if fmt == "pct":
        return f"{float(v) * 100:g}"
    if isinstance(v, bool):
        return "on" if v else "off"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


PLACE = re.compile(r"\{([A-Za-z0-9_.]+)(?::(pct))?\}")
PY_PLACE = re.compile(r"\$\(([A-Za-z0-9_.]+)\)")
WORD = re.compile(r"[A-Z][A-Z0-9_]+")


def parts_of(text: str, values: dict[str, Any], used: set[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    pos = 0
    for m in PLACE.finditer(text):
        if m.start() > pos:
            out.append({"text": text[pos : m.start()]})
        pid = m.group(1)
        if pid not in values:
            raise SystemExit(f"runner_flow_export: the words name an unknown number {pid!r}")
        used.add(pid)
        out.append({"param": pid, "shown": shown(values[pid], m.group(2))})
        pos = m.end()
    if pos < len(text):
        out.append({"text": text[pos:]})
    return out


def words_of(text: str, values: dict[str, Any], used: set[str]) -> str:
    """An explanation with its numbers filled in (plain text)."""

    def sub(m: re.Match[str]) -> str:
        pid = m.group(1)
        if pid not in values:
            raise SystemExit(f"runner_flow_export: the words name an unknown number {pid!r}")
        used.add(pid)
        return shown(values[pid], m.group(2))

    return PLACE.sub(sub, text)


def py_line(line: str, values: dict[str, Any], used: set[str], consts: dict[str, str]) -> str:
    def sub(m: re.Match[str]) -> str:
        pid = m.group(1)
        if pid not in values:
            raise SystemExit(f"runner_flow_export: the Python names an unknown number {pid!r}")
        used.add(pid)
        return py_lit(values[pid])

    out = PY_PLACE.sub(sub, line)
    used.update(consts[w] for w in WORD.findall(out) if w in consts)  # a NAME -> its number's id
    return out


class Builder:
    def __init__(self, values: dict[str, Any], consts: dict[str, str], flags_ok: set[str],
                 symbols: set[str]) -> None:  # fmt: skip
        self.values, self.consts, self.flags_ok, self.symbols = values, consts, flags_ok, symbols
        self.lines: list[str] = []
        self.ids: set[str] = set()

    def emit(self, n: Node, ind: int) -> dict[str, Any]:
        if n.id in self.ids:
            raise SystemExit(f"runner_flow_export: the block id {n.id!r} is used twice")
        self.ids.add(n.id)
        for f in n.flags:
            if f not in self.flags_ok:
                raise SystemExit(f"runner_flow_export: block {n.id} names {f}, not in the commands")
        for s in n.code:
            if s not in self.symbols:
                raise SystemExit(f"runner_flow_export: block {n.id} names {s}, not in the code")
        used: set[str] = set()
        pad = " " * ind
        start = len(self.lines) + 1
        doc: dict[str, Any] = {"id": n.id, "kind": n.kind, "style": n.style}
        if n.kind == "if":
            branches = []
            head_end = start
            for k, b in enumerate(n.branches):
                self.lines.append(pad + py_line(b.py, self.values, used, self.consts))
                if k == 0:
                    head_end = len(self.lines)
                body = [self.emit(c, ind + 4) for c in b.body] or [self.pass_(ind + 4)]
                branches.append({"parts": parts_of(b.text, self.values, used),
                                 "body": [c for c in body if c]})  # fmt: skip
            doc["branches"] = branches
            doc["head"] = [start, head_end]
        else:
            doc["parts"] = parts_of(n.text, self.values, used)
            for ln in n.py:
                self.lines.append(pad + py_line(ln, self.values, used, self.consts))
            doc["head"] = [start, len(self.lines)]
            if n.kind in ("hat", "loop"):
                doc["body"] = [self.emit(c, ind + 4) for c in n.body]
                for ln in n.tail:
                    self.lines.append(pad + "    " + py_line(ln, self.values, used, self.consts))
        doc["lines"] = [start, len(self.lines)]
        doc["why"] = words_of(n.why, self.values, used)
        doc["flags"] = list(n.flags)
        doc["code"] = list(n.code)
        doc["params"] = sorted(used)
        return doc

    def pass_(self, ind: int) -> dict[str, Any]:
        self.lines.append(" " * ind + "pass")
        return {}


def code_symbols() -> set[str]:
    """Every function / class / top-level name the blocks may cite: dungeon_hunt's (bare), and
    value_target's / bare_steal's / explore_map's with their prefixes."""
    out: set[str] = set()
    for prefix, name in (("", "dungeon_hunt"), ("vt.", "value_target"), ("bs.", "bare_steal"),
                         ("em.", "explore_map")):  # fmt: skip
        tree = ast.parse((SCRIPTS / f"{name}.py").read_text())
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                out.add(prefix + n.name)
    return out


def build() -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS))
    import bare_steal as bs
    import dungeon_hunt as dh
    import value_target as vt

    path = SCRIPTS / "dungeon_hunt.py"
    flags = run_flags(dh, path)
    cmd = parse_command(BASE_COMMAND, flags)
    opt_cmd: dict[str, Any] = {}
    for o in OPTIONAL:
        opt_cmd.update(parse_command(list(o["flags"]), flags))
    ctx = Ctx(dh, vt, bs, {**cmd, **opt_cmd})
    plist = params(ctx.cmd)
    values = {p.id: p.get(ctx) for p in plist}
    consts = {
        p.id.split(".")[-1]: p.id
        for p in plist
        if not p.id.startswith(("cmd.", "strategy.", "char.", "derived.", "PATROL_START."))
    }
    commands = flag_names(BASE_COMMAND) + [
        f for o in OPTIONAL for f in flag_names(list(o["flags"]))
    ]
    b = Builder(values, consts, set(commands), code_symbols())

    head = [
        f"# {cmd['map']}: how the {cmd['char'].title()} hunts -- a DESCRIPTION of "
        "`scripts/dungeon_hunt.py run`",
        "# GENERATED by scripts/runner_flow_export.py with dungeon_hunt.py's own numbers: an "
        "outline for",
        "# learners, not the real code (the real loop is dungeon_hunt.run(), with many more "
        "checks).",
        "# Nothing here runs, and nothing on /flows reaches the game.",
        "#",
        "#   dungeon_hunt.py run \\",
    ]
    for chunk in wrap(BASE_COMMAND, 88):
        head.append(f"#       {chunk}")
    head += [
        "",
        "import time",
        "",
        "# --- the numbers, read from the code at export time -------------------------------",
    ]
    strat = {k: v for k, v in ctx.strategy.items()}
    char_keys = ("job", "max_hp", "max_sp", "potions_to", "wings_to", "etc_hold_max")
    char_ = {k: ctx.char[k] for k in char_keys if k in ctx.char}
    head.append(f'STRATEGY = {py_lit(strat)}  # STRATEGIES["{cmd["strategy"]}"] (--strategy)')
    head.append(f'CHAR = {py_lit(char_)}  # some of CHARS_CONF["{cmd["char"]}"] (--char)')
    head.append(f'PATROL_START = {{{py_lit(cmd["map"])}: '
                f'{py_lit(dh.PATROL_START[cmd["map"]])}}}  # some of PATROL_START')  # fmt: skip
    for p in plist:
        name = p.id.split(".")[-1]
        if name in consts:
            head.append(f"{name} = {py_lit(values[p.id])}  # {p.source.split(':')[0]}")
    head += ["SPECIES_VALUES = {}  # read at run time from data/econ/maps.json (never exported)"]
    b.lines = list(head)

    stacks = []
    for n in spec():
        b.lines += ["", ""]
        stacks.append(b.emit(n, 0))
    python = "\n".join(b.lines).rstrip("\n") + "\n"
    compile(python, "outline.py", "exec")  # the outline is valid Python (never run)

    rid = f"{cmd['map']}_{cmd['char']}"
    used_flags = sorted(set(commands))
    return {
        "kind": "runner-flow",
        "format": FORMAT,
        "generated_by": "scripts/runner_flow_export.py from scripts/dungeon_hunt.py "
        "(+ value_target.py, "
        "bare_steal.py) -- do not edit",
        "description_only": True,
        "id": rid,
        "title": f"{cmd['map']}: how the {cmd['char'].title()} hunts",
        "map": cmd["map"],
        "char": cmd["char"],
        "script": "scripts/dungeon_hunt.py run",
        "version": dh.VERSION,
        "file": f"{rid}.py",
        "command": {
            "base": list(BASE_COMMAND),
            "optional": [
                {
                    "name": o["name"],
                    "title": o["title"],
                    "flags": list(o["flags"]),
                    "note": o["note"],
                }
                for o in OPTIONAL
            ],  # fmt: skip
        },
        "params": {
            p.id: {"value": json_val(values[p.id]), "source": p.source, "note": p.note}
            for p in plist
        },  # fmt: skip
        "flags": {
            f: {
                "help": flags[f]["help"],
                "default": json_val(flags[f]["default"]),
                "value": json_val(ctx.cmd.get(flags[f]["dest"])),
                "kind": flags[f]["kind"],
                "base": f in BASE_COMMAND,
            }
            for f in used_flags
        },  # fmt: skip
        "stacks": stacks,
        "python": python,
    }


def wrap(tokens: list[str], width: int) -> list[str]:
    out, cur = [], ""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
            t = f"{t} {tokens[i + 1]}"
            i += 1
        i += 1
        if cur and len(cur) + 1 + len(t) > width:
            out.append(cur)
            cur = t
        else:
            cur = f"{cur} {t}".strip()
    if cur:
        out.append(cur)
    return out


def render(doc: dict[str, Any]) -> str:
    name = re.sub(r"[^A-Z0-9_]", "_", doc["id"].upper())
    body = json.dumps(doc, indent=2, ensure_ascii=False)
    return (
        "/* GENERATED by scripts/runner_flow_export.py from scripts/dungeon_hunt.py: a DESCRIPTION "
        "of the runner for /flows\n"
        " * (display + SIMULATE only; nothing on the page runs). DO NOT EDIT: change the "
        "exporter's "
        "SPEC and run\n"
        " * `.venv/bin/python scripts/runner_flow_export.py export`. */\n"
        'import type { RunnerDoc } from "../runner.ts";\n\n'
        f"export const {name}: RunnerDoc = {body};\n"
    )


def out_path(doc: dict[str, Any]) -> Path:
    return OUT_DIR / f"{doc['id']}.gen.ts"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("cmd", choices=["export", "check", "show"])
    a = ap.parse_args()
    doc = build()
    text = render(doc)
    path = out_path(doc)
    if a.cmd == "show":
        sys.stdout.write(doc["python"])
        return 0
    if a.cmd == "export":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path.relative_to(ROOT)} ({len(text)} bytes)")
        return 0
    old = path.read_text() if path.exists() else ""
    if old == text:
        print(f"{path.relative_to(ROOT)}: current")
        return 0
    diff = difflib.unified_diff(old.splitlines(), text.splitlines(), "committed", "fresh",
                                lineterm="", n=1)  # fmt: skip
    sys.stdout.write("\n".join(list(diff)[:60]) + "\n")
    print(
        f"{path.relative_to(ROOT)} is stale: .venv/bin/python scripts/runner_flow_export.py export"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
