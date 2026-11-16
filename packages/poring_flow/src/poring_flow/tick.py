"""Live blocks STAGE 5c: THE TICK MADE VISIBLE (Batt 2026-11-15 ~13:0x: "dungeon_hunt.py should be
blocks the user sees and can edit himself"; docs/planning/live-blocks.md 15.3).

The hunt core's tick is run()'s 20 steps (scripts/dungeon_hunt.py ``hunt_steps``; their cursor,
``HuntCursor``). A map node's function ``hunt_tick()`` (the editor's tab `tick`) LISTS them, one
STEP BLOCK each (``step_<name>()``), in run()'s order, each with its words and its CLASS:

- SAFETY: protects her or the run (the Stop, HP, a boss, the UI watch's hard bar, an escape): it
  cannot be left out or moved;
- REQUIRED: the loop's own mechanics (the fight, a held target's wait, the after step, the rest,
  the walk, the pace): it cannot be left out or moved;
- OPTIONAL: a play a person may not want (the loot step, the idle Knife and the queue, the White
  Plant sweep): it may be LEFT OUT -- the runner then never plays it -- but not moved.

Without a ``hunt_tick()`` a hunt core plays the full tick (every step). Everything here reads the IR
only (PURE): the linter (lint/tick.py), the live set (poring_flow.live) and the player share it.
Refused before any input (the lint's errors; the backend's not_live: live.problems), each named:
``tick_step`` (a step left out that may not be, a step moved, a step twice, another statement in
``hunt_tick()``, a step block outside it), ``tick_place`` (a ``hunt_tick()`` where no hunt loop
drives the hunt core, a call of ``hunt_tick()``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from poring_flow import ir
from poring_flow import recipes as rc

VERSION = "9.56"  # scripts/dungeon_hunt.py RUNNER_BLOCKS_VERSION (test_tick.py pins them)
TICK = "hunt_tick"  # the function's name: run()'s own hunt_tick() runs the steps in this order
# (a tab cannot share a function's name, so the function is hunt_tick and its tab tick)
TICK_TAB = "tick"
PREFIX = "step_"  # a step block is step_<run()'s step name>
Klass = Literal["safety", "required", "optional"]


@dataclass(frozen=True)
class Step:
    name: str  # run()'s step name (dungeon_hunt.STEP_NAMES)
    klass: Klass
    words: str  # what it does (the block's words)
    why: str  # what leaving it out would cost (the lint's words)
    owner: str = ""  # a mode step: the hunt loop's block that plays it ("" a common step)

    @property
    def block(self) -> str:
        return f"{PREFIX}{self.name}"


# run()'s steps in their order (== dungeon_hunt.STEP_NAMES: test_tick.py), each one's class
STEPS: tuple[Step, ...] = (
    Step("begin", "safety", "the tick's clock; the Run's Stop", "the Run's Stop would not be read"),
    Step("sense", "safety", "the frame, HP, SP, the position",
         "HP and her position would not be read"),
    Step("hook", "safety", "the box's own tick: its Stop, its events",
         "the box's Stop and its events would not play"),
    Step("vitals", "safety", "death", "a death would not be seen"),
    Step("battle_log", "safety", "the Battle Log: hits, kills, a boss",
         "a boss line (its Fly Wing), the hits and the kills would not be read"),
    Step("survive", "safety", "the potion, the Fly Wing, Auto Guard",
         "no potion and no Fly Wing would be pressed"),
    Step("engage", "safety", "a fight begins; the Garm Baby alarm",
         "an attack, the Garm Baby alarm and the boss guard would not be seen"),
    Step("ui", "safety", "the UI watch; the weight; home",
         "an unknown UI state would not stop the run, and the weight would not take her home"),
    Step("upkeep", "safety", "the Knife's HP floor; overweight; HUD",
         "the Knife would not come off at the HP floor"),
    Step("fight", "required", "the fight (the recipe's steps)", "no target would ever be struck",
         "fight_target"),
    Step("hold", "required", "a held target waits; the loot recheck",
         "she would walk away from a target she holds", "find_target"),
    Step("loot", "optional", "the loot step after a fight", "", "fight_target"),
    Step("after", "required", "a fight's end: rest or search",
         "a fight's end would never become a search", "find_target"),
    Step("ready", "optional", "the Knife while idle; the queue", "", "find_target"),
    Step("rest", "required", "sit until HP is full",
         "a rest the after step decides would freeze her", "find_target"),
    Step("idle", "safety", "stuck: uncarve, or a Fly Wing", "being stuck would never end",
         "find_target"),
    Step("plant", "optional", "the White Plant sweep", "", "find_target"),
    Step("search", "required", "the walk", "she would never walk to a monster", "find_target"),
    Step("position", "safety", "an unread position: a Fly Wing",
         "an unread position would neither fly nor end the run", "find_target"),
    Step("pace", "required", "the tick's pace (200 ms)", "the tick would spin with no pause",
         "find_target"),
)  # fmt: skip
BY_BLOCK = {s.block: s for s in STEPS}
STEP_BLOCKS = tuple(s.block for s in STEPS)
OPTIONAL = tuple(s.name for s in STEPS if s.klass == "optional")  # == DRIVE_OPTIONAL_STEPS
WORDS = {"safety": "SAFETY", "required": "REQUIRED", "optional": "optional"}


@dataclass(frozen=True)
class TickPlan:
    """One map block's tick, as the runner plays it: the optional steps left out."""

    block: str
    function: str  # its IR name
    left_out: tuple[str, ...] = ()  # run()'s step names, in their order


def tick_function(flow: ir.Flow, block: str) -> str | None:
    """The IR name of a map block's tick: its own copy (``<block>__hunt_tick``) first, else
    ``hunt_tick``."""
    own = f"{block}__{TICK}"
    if own in flow.procedures:
        return own
    return TICK if TICK in flow.procedures else None


def _drives(flow: ir.Flow, b: ir.MapBlock) -> bool:
    """The map block's hunt core plays a hunt loop (a runner action and a hunt_loop function)."""
    own = f"{b.name}__{rc.HUNT_LOOP}"
    return rc.has_hunt_core(flow, b) and (own in flow.procedures or rc.HUNT_LOOP in flow.procedures)


def analyse(flow: ir.Flow) -> tuple[dict[str, TickPlan], list[rc.Issue]]:
    """PURE: every map block's tick and every issue of the flow's step blocks (the module
    docstring). Empty when the flow has none."""
    out: list[rc.Issue] = []

    def bad(path: str, what: str, rule: str, words: str, block: str | None = None) -> None:
        out.append(rc.Issue(path, what, rule, "error", words, True, block))

    ticks = {n for n in flow.procedures if n == TICK or n.endswith(f"__{TICK}")}
    uses = any(a.block in BY_BLOCK for site in ir.sites(flow) for a in ir.actions_in(site.stmt))
    if not ticks and not uses:
        return {}, []
    blocks = list(flow.workflow.blocks) if flow.workflow else []
    plans: dict[str, TickPlan] = {}
    for b in blocks:
        name = tick_function(flow, b.name)
        if name is not None and _drives(flow, b):
            plans[b.name] = TickPlan(b.name, name, _left_out(flow, name))
    for name in sorted(ticks):
        owner = name[: -len(f"__{TICK}")] if name != TICK else None
        if not any(p.function == name for p in plans.values()):
            bad(name, TICK, "tick_place", f"{TICK}() is the tick of a hunt core whose hunt loop "
                "plays its steps: a map node whose main starts the hunt core (hunt_loop()) and has "
                "a hunt_loop", owner)  # fmt: skip
        sig = flow.signatures.get(name) or ir.Signature()
        if sig.params or sig.varargs or sig.kwargs:
            bad(name, TICK, "tick_step", f"{TICK}() takes no inputs: it lists the tick's steps",
                owner)  # fmt: skip
        _body(flow, name, owner, bad)
    for site in ir.sites(flow):
        if site.scope == "procedure" and site.root in ticks:
            continue
        for a in ir.actions_in(site.stmt):
            if a.block in BY_BLOCK:
                words = (
                    f"{a.block}() is a step of the tick: it stands only in the function "
                    f"{TICK}() (its tab tick), in the runner's order"
                )
                bad(site.path, a.block, "tick_step", words)
        if any(p in ticks for p in ir.calls_in(site.stmt)):
            bad(site.path, TICK, "tick_place", f"{TICK}() is read by the hunt core, never called: "
                "it lists the steps every tick plays")  # fmt: skip
    return plans, out


def _left_out(flow: ir.Flow, name: str) -> tuple[str, ...]:
    have = {st.block for st in flow.procedures.get(name, []) if isinstance(st, ir.ActionStmt)}
    return tuple(s.name for s in STEPS if s.klass == "optional" and s.block not in have)


def _body(flow: ir.Flow, name: str, owner: str | None, add: Callable[..., None]) -> None:
    """hunt_tick()'s statements: step blocks only, each once, in the runner's order, every SAFETY
    and REQUIRED step present (`places`: which copy stands in its place, which is an extra copy,
    which is out of its place -- the editor's lock reads the same, lib/flow/tick.ts tickPlaces)."""
    body = list(flow.procedures.get(name, []))
    blocks = [st.block if isinstance(st, ir.ActionStmt) and st.block in BY_BLOCK and not st.params
              else None for st in body]  # fmt: skip
    for i, (st, p) in enumerate(zip(body, places(blocks), strict=True)):
        path = f"{name}.{i}"
        if p.kind == "other":
            what = st.block if isinstance(st, ir.ActionStmt) else f"a {st.kind}"
            add(path, what, "tick_step", f"{TICK}() holds {what}: it holds the step blocks "
                "only (step_begin() ... step_pace()), each once, in the runner's order",
                owner)  # fmt: skip
        elif p.kind == "extra":
            add(path, blocks[i], "tick_step", f"{blocks[i]}() twice in {TICK}(): {EXTRA_WORDS} "
                "(each step plays once a tick)", owner)  # fmt: skip
        elif p.kind == "misplaced":
            # round 27: the words say WHERE it goes, between the steps in their place around it
            add(name, blocks[i], "tick_step", f"{blocks[i]}() is out of its place in {TICK}(): "
                f"{p.where} (the steps play in the runner's order; the hunt core's hand-backs and "
                "guards rely on it)", owner)  # fmt: skip
    present = {b for b in blocks if b}
    for s in STEPS:
        if s.klass != "optional" and s.block not in present:
            kind = "a SAFETY step" if s.klass == "safety" else "a REQUIRED step"
            add(name, s.block, "tick_step", f"{TICK}() leaves out {s.block}(), {kind} ({s.words}): "
                f"without it {s.why}. Only {', '.join(PREFIX + o + '()' for o in OPTIONAL)} may "
                "be left out", owner)  # fmt: skip


# Round 28 (the reviewer: a SECOND step_survive dropped after step_pace was locked in the editor,
# and the lint said "twice" -- the learner could not delete it): which copy of a step the tick
# ACCEPTS. The copies in their place in the runner's order (the longest run of steps already in
# order, one copy of a step at most, the earlier copy where two would do) are accepted; any other
# copy of an accepted step is an EXTRA copy; a step with no copy in its place is OUT OF ITS PLACE
# (its first copy; its other copies extra). The editor says the same words on an extra or a
# misplaced one (lib/flow/tick.ts tickPlaces: the same rule, pinned by the same cases in
# test_runner_functions.py and tick_lock.test.ts). ➡️ Round 29 (Batt 2026-11-16, live-blocks.md 17
# #1): the editor locks no step any more; a tick without a SAFETY or REQUIRED step in its place is
# refused here (tick_step) and by the Run (live.problems), in these words.
EXTRA_WORDS = "an extra copy: delete it"


@dataclass(frozen=True)
class Place:
    """Where one statement of hunt_tick() stands: "ok" (in its place: the one the tick accepts),
    "extra" (another copy of an accepted step), "misplaced" (`where` it goes), "other" (no step)."""

    kind: Literal["ok", "extra", "misplaced", "other"]
    where: str = ""


def places(blocks: Sequence[str | None]) -> list[Place]:
    """PURE: each statement's place (`blocks`: its step block's name, None for any other)."""
    idx = [i for i, b in enumerate(blocks) if b is not None and b in BY_BLOCK]
    rank = {i: STEP_BLOCKS.index(str(blocks[i])) for i in idx}
    best: dict[int, list[int]] = {}  # the longest in-order chain ending at each statement
    for i in idx:
        # (strictly in order: one copy of a step at most; of chains as long, the one ending at the
        # earlier step, then the earlier copy)
        before = [best[j] for j in idx if j < i and rank[j] < rank[i]]
        chain = max(before, key=lambda c: (len(c), -rank[c[-1]])) if before else []
        best[i] = [*chain, i]
    chains = list(best.values())
    longest: list[int] = max(chains, key=len) if chains else []
    keep = set(longest)
    accepted = {blocks[i] for i in keep}
    present = {b for b in blocks if b is not None and b in BY_BLOCK}
    out: list[Place] = []
    misplaced: set[str] = set()
    for i, b in enumerate(blocks):
        if b is None or b not in BY_BLOCK:
            out.append(Place("other"))
        elif i in keep:
            out.append(Place("ok"))
        elif b in accepted or b in misplaced:
            out.append(Place("extra"))
        else:
            misplaced.add(b)
            out.append(Place("misplaced", _where(b, present)))
    return out


def _where(moved: str, present: set[str]) -> str:
    """Where a step goes: after the step before it in the runner's order, before the one after it
    (of the steps the tick holds)."""
    at = STEP_BLOCKS.index(moved)
    have = [b for b in STEP_BLOCKS if b in present and b != moved]
    before = next((b for b in reversed(have) if STEP_BLOCKS.index(b) < at), None)
    after = next((b for b in have if STEP_BLOCKS.index(b) > at), None)
    if before and after:
        return f"it goes after {before}() and before {after}()"
    if after:
        return f"it goes first, before {after}()"
    return f"it goes last, after {before}()" if before else "it goes in its own place"


def is_step(a: ir.ActionStmt) -> bool:
    return a.block in BY_BLOCK
