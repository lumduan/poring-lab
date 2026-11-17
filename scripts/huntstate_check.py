#!/usr/bin/env python3
"""live-blocks 5b-1 (docs/planning/live-blocks.md section 13): the HuntState refactor of
dungeon_hunt.run(), as MECHANICAL rewrites a reviewer can re-derive and check.

run() was ONE function (~4,400 lines) whose loop state lived in its local variables, shared with
~100 closures through `nonlocal`. 5b-1 changes no behaviour; it moves that state onto ONE object
(`HuntState`, `hs`) and turns the loop's body into named STEPS (closures run in order by a driver),
so 5b-2 can play the steps as live blocks. Three rewrites, each a pure function of the source:

- LIFT (T1): every run()-scope variable the loop REBINDS (bound before the loop and again inside
  it, or declared `nonlocal` by a closure) becomes an attribute of `hs`: each Name that resolves to
  run()'s binding (this module's own scope resolver, cross-checked against `symtable`) is written
  `hs.<name>`; its `nonlocal` declarations go; `name: T = v` becomes `hs.name = v` (the type is the
  class's); `hs = HuntState()` is run()'s first statement.
- ALIAS (T1b): a container the loop mutates IN PLACE but never rebinds (bound exactly once) is
  created ON `hs` and keeps its local name as an alias of the same object: `counts = Counter()`
  becomes `counts = hs.counts = Counter()`. Nothing else changes.
- OUTLINE (T2): the main loop's body, statement by statement, is cut into consecutive SECTIONS;
  each becomes a closure `def step_<name>() -> str | None` defined just before the loop at the
  loop body's own indentation (so its text is unchanged), with `nonlocal` for every name it binds
  (no step has a local of its own), its loop-level `continue` written `return TICK_DONE` and its
  loop-level `break` `return RUN_END`. The loop becomes the driver: `while ...: if hunt_tick() ==
  RUN_END: break`, where `hunt_tick()` calls the steps of `hunt_steps` in order and stops at the
  first that returns a signal.

Why each rewrite keeps behaviour (the conditions `check` verifies on the base):
- LIFT: one object, created before any binding and never rebound, holds exactly one attribute
  per lifted variable; every read / write / augmented write of the variable is the same read /
  write of the attribute, in the same order, with the same values (defaults, f-strings, closures
  and comprehensions read it when they did). Refused when run() uses exec / eval / locals / vars /
  globals, deletes a lifted name, catches NameError, binds a lifted name by import / def / class /
  except / global, or already uses the name `hs`.
- ALIAS: the local and the attribute name the same object from its one binding on.
- OUTLINE: a section's statements run in the same order with the same names (each bound name is
  run()'s, through `nonlocal`); `return TICK_DONE` from a step ends the tick exactly as `continue`
  did (the driver skips the rest of the tick's steps), `return RUN_END` ends the loop exactly as
  `break` did (no `else:` on the loop), falling through runs the next step. Refused when a section
  has a loop-level `return` / `yield` / `await`, or the loop an `else:`.

    huntstate_check.py derive BASE OUT [--steps]   rewrite BASE (a dungeon_hunt.py) into OUT
    huntstate_check.py check [--base REV] [--file F]
        F's run() must equal the rewrites of REV's run() (default: the base pinned in BASE_REV),
        compared as ASTs (formatting, comments, the class's and the steps' docstrings aside);
        prints what moved and every condition, rc 1 on any difference (5b-2's drive branch is
        read as its else: the driver loop)
    huntstate_check.py drive [--base REV] [--file F]
        live-blocks 5b-2 (section 14): F's run() without its drive branch must equal REV's run()
        (default DRIVE_BASE, 5b-1's merged runner) as ASTs; the module outside run() is REV's plus
        exactly DRIVE_ADDED; the guarded steps act only in their mode; rc 1 on any difference

live-blocks 18 (dungeon@9.57 --fly-first, Batt 2026-11-16: "a boss on the screen, at any distance:
the Fly Wing first"): every fly-first change is a BRANCH whose condition is exactly one of
FLY_FIRST_TESTS (`if fly_first:` in run(), `if FLY_FIRST:` in the module), its else today's code.
`check` and `drive` read the file with every such branch as its else and without the module names
fly-first adds (FLY_FIRST_ADDED): so with the flag off the program they prove is the base's, and a
change anywhere else is refused as before.
    huntstate_check.py flag [--base REV] [--file F]
        live-blocks 18.11 (dungeon@9.58 --fly-first-hp): with ONLY the fly_first_hp branches read
        as their else, F's whole module equals REV's (default FLAG_BASE: the runner s7ab measured)

live-blocks 18.15 (dungeon@9.59, the box's model among the map's: xmas02sk deployed, xmas02gb the
reference arm's): every change a branch `if MODEL_PICK:` whose else is 9.58's code, plus BoxWatch's
keyword-only `model_file` (default None). `check`, `drive` and `flag` read the family as its else
and without the keyword (MODEL_PICK_*) besides.
    huntstate_check.py pick [--base REV] [--file F]
        with ONLY the model-pick branches read as their else, F's whole module equals REV's
        (default PICK_BASE: the 9.58 runner s8ab measured)

The text it derives is formatted by `ruff format` afterwards (formatting is AST-neutral); `check`
reads the committed file, never trusts `derive`'s output.
"""

from __future__ import annotations

import argparse
import ast
import copy
import subprocess
import symtable
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "dungeon_hunt.py"
BASE_REV = "eb160ee1"  # main when 5b-1 began (2026-11-14 18:2x ICT): the run() 5b-1 rewrites
HS = "hs"  # the HuntState instance's name in run()
LOOP_TEST = "time.monotonic() < t_end"  # the main loop's condition (exactly one such loop)
TICK_DONE, RUN_END = "TICK_DONE", "RUN_END"  # the steps' signals (module constants in the target)
INERT = (TICK_DONE, RUN_END, "HUNT_STEPS_VERSION")  # new module constants that change nothing
DECL_COMMENT = "# run()'s locals only the steps bind (nonlocal): declared here, never set here"
# live-blocks 5b-2 (section 14): the drive branch around the driver loop, and what 5b-2 added to
# the module outside run() (the cursor, its tables, the hook helpers): `check` (5b-1) reads the
# file without them; `drive` proves that run() without the branch IS 5b-1's run(), that the module
# is 5b-1's plus exactly these, and the steps' guards the cursor relies on
DRIVE_BASE = "bb6d41eb"  # main when 5b-2 began (2026-11-14 19:5x ICT): 5b-1's merged runner
DRIVE_TEST = "hook_drives(hook)"  # the branch's condition (no hook, or a hook without drive: else)
DRIVE_ADDED = (
    "HUNT_BLOCKS_VERSION", "STEP_NAMES", "COMMON_STEPS", "MODE_STEPS", "HANDBACK_AT",
    "STEP_GUARD", "BLOCK_OWNS", "DRIVE_SPIN_MAX", "DRIVE_SKILL_ROLES", "DRIVE_HOOK", "HuntTarget",
    "HuntView", "HuntCursor", "hook_drives", "drive_refused", "hunt_drive",
    "RUNNER_BLOCKS_VERSION", "DRIVE_OPTIONAL_STEPS",  # 5c (live-blocks 15.3): the visible tick
)  # fmt: skip
# live-blocks 18 (dungeon@9.57): the fly-first branches' conditions, and the module names it adds;
# 18.11 (dungeon@9.58): the fly-first-hp family's, which `flag` reads alone against FLAG_BASE
FLY_FIRST_HP_TESTS = ("fly_first_hp", "FLY_FIRST_HP")
FLY_FIRST_HP_ADDED = ("FLY_FIRST_HP", "FLY_FIRST_HP_VERSION", "ff_hp_why")
FLY_FIRST_TESTS = ("fly_first", "FLY_FIRST", *FLY_FIRST_HP_TESTS)
FLY_FIRST_ADDED = (
    "FLY_FIRST", "FLY_FIRST_VERSION", "FF_LATCH_S", "FF_REARM_S", "FF_BOSS_WHYS", "alarm_classes",
    "ff_latch", "ff_sighting", *FLY_FIRST_HP_ADDED,
)  # fmt: skip
# 18.11: main when 9.58 began (2026-11-16 20:3x ICT): the 9.57 runner s7ab measured (18.9)
FLAG_BASE = "8a091a72"
# live-blocks 18.15 (dungeon@9.59, the box's model among the map's): its branches' condition, the
# module names it adds and BoxWatch's keyword it adds; `pick` reads them alone against PICK_BASE,
# and `check`, `drive` and `flag` read them as their else (and without the keyword) besides
MODEL_PICK_TESTS = ("MODEL_PICK",)
MODEL_PICK_ADDED = ("MODEL_PICK", "MODEL_PICK_VERSION")
MODEL_PICK_PARAMS = ("model_file",)
# main when 9.59 began (2026-11-17 06:2x ICT): the 9.58 runner s8ab measured (18.13)
PICK_BASE = "f8e27d21"
# the mode steps the cursor calls whoever plays when their mode is another (STEP_GUARD): each one's
# body acts only in that mode (the proof: its statements are ifs on that mode, nothing else)
GUARDED = {"fight": "fight", "loot": "after"}

# T1b: the containers that hold the loop's state in place (each bound exactly once in run()).
ALIASED = (
    "counts", "kills_seen", "queue", "box_fight", "last_strike", "steal_done", "false_rel",
    "loot_used", "loot_picked", "empty_cells", "wp_st", "ex_st", "bq_st", "walk_st", "ust",
    "own_moves", "ours_ticks", "ua_locks", "ua_walks", "boss_walks", "stalls_here", "plant_last",
    "carved", "rk_pending", "rk_st", "lm_mem", "lm_kills", "lm_st", "st", "pos_ok", "pos_hist",
    "escaped", "box_stop", "box_pressed", "box_sp", "n_strike", "n_shots", "n_box_target",
    "last_click_t", "last_quick", "frame_meta", "stock_due", "stock_tries", "reach_cache",
    "reach_logged", "reach_pick", "reach_proj", "spot_logged", "trip",
)  # fmt: skip
# T1: names bound before the loop AND inside it that are NOT loop state: a refusal's or a
# setup loop's name reused as a tick's temporary (they stay run()'s locals)
NOT_LIFTED = ("why_bx", "why_hk", "cmd")
# T1: lifted although only the setup binds it (twice: None, then the controller): the bare-steal
# controller is loop state the steps share
EXTRA_LIFTED = ("bare",)

# T2: the main loop's body, cut by the FIRST statement of each section (its first source lines,
# each stripped, must start with the text given); the names are the steps' (step_<name>)
SECTIONS = (
    ("begin", "tick = time.monotonic()"),
    ("sense", "img = frame()"),
    ("hook", "if hook is not None:"),
    ("vitals", "if dead:"),
    ("battle_log", "with blt.lock:"),
    ("survive", "frac = None if pct is None"),
    ("engage", "hit_now = tick - hs.last_taken"),
    ("ui", "if tick - hs.last_ui >= UI_EVERY_S"),
    ("upkeep", "overweight = hs.red_seen"),
    ("fight", 'if hs.mode == "fight":'),
    ("hold", 'if hs.mode == "fight" or (hs.lock is not None):'),
    ("loot", 'if hs.mode == "after":\nqueue.clear()'),
    ("after", 'if q_on and hs.mode == "after":'),
    ("ready", "ready_hold = False"),
    ("rest", 'if hs.mode == "rest":'),
    ("idle", "if hs.here != hs.idle_pos"),
    ("plant", 'if hs.mode == "search" and hs.here is not None and hs.lock is None'),
    ("search", "near_end = ("),
    ("position", "if (tick - hs.last_pos_t > POS_FLY_S"),
    ("pace", "time.sleep(max(0.0, 1.0 / READ_HZ"),
)

# T2: each step's one-line docstring (live-blocks.md 13.2's table); a step without one has none
STEP_DOCS = {
    "begin": "The tick's clock; the Run's Stop; a stop or a Fly Wing from inside an action.",
    "sense": "The frame, HP and SP, the stock re-reads, the Miss cue, dead, the position.",
    "hook": "The live player's tick hook (stage 1): its stop ends the run.",
    "vitals": "Death; the house rest's unexpected load screen.",
    "battle_log": "The Battle Log's new lines: the boss line, hits, the exp kills, the loot list.",
    "survive": "Calm; the box's survival events (stage 2); the runner's sustain; Auto Guard.",
    "engage": "The fight signs, the Garm Baby alarm, the boss guard; the engage: mode fight.",
    "ui": "The UI watch (every UI_EVERY_S): the weight, the box's weight event, home.",
    "upkeep": "Overweight; the idle clock; the recheck / memory ageing; the HUD; bare.tick.",
    "fight": "Mode fight: the kill read, unlock, the quiet end, the strikes, the scans.",
    "hold": "A lock without a fight waits; the loot recheck; the loot memory.",
    "loot": "Mode after: the queue cleared; the loot step.",
    "after": "The queue pick due; overweight; the rest decision; after becomes search.",
    "ready": "--bare-ready's idle swap; --queue's next target.",
    "rest": "Mode rest: sitting, the house rest, the walk to a rest spot.",
    "idle": "The idle watchdog: uncarve, or a Fly Wing.",
    "plant": "The White Plant sweep.",
    "search": "The goal; the walk click (pick, dodge, trust, stall, carve); melee-ring.",
    "position": "The unread position's Fly Wing; 30 s unread ends the run.",
    "pace": "The sleep to READ_HZ.",
}
DYNAMIC = ("exec", "eval", "locals", "vars", "globals")
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ListComp,
          ast.SetComp, ast.DictComp, ast.GeneratorExp)  # fmt: skip
COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
LOOPS = (ast.For, ast.AsyncFor, ast.While)


# --- the scope resolver ---------------------------------------------------------------------------
@dataclass
class Scope:
    node: ast.AST
    parent: Scope | None
    kind: str  # "function" | "class" | "comp"
    bound: set[str] = field(default_factory=set)  # names bound in THIS scope (incl. declared)
    declared: set[str] = field(default_factory=set)  # nonlocal / global in this scope
    names: list[ast.Name] = field(default_factory=list)  # Name nodes whose scope this is
    children: list[Scope] = field(default_factory=list)
    nonlocals: list[ast.Nonlocal] = field(default_factory=list)

    @property
    def locals(self) -> set[str]:
        return self.bound - self.declared

    def resolve(self, name: str) -> Scope | None:
        """The scope whose binding `name` means here (None: global / builtin)."""
        if name in self.locals:
            return self
        s = self.parent
        while s is not None:
            if s.kind != "class" and name in s.locals:
                return s
            s = s.parent
        return None


def _bind_targets(t: ast.AST, out: set[str]) -> None:
    for n in ast.walk(t):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, ast.Starred):
            pass


class ScopeBuilder:
    """Python's own rules, for the subset run() uses: functions, lambdas, comprehensions (their
    first iterable in the enclosing scope; a walrus binds in the nearest function), classes."""

    def __init__(self, root: ast.FunctionDef) -> None:
        self.owner: dict[int, Scope] = {}  # def / class / import / except node -> its scope
        self.root = Scope(root, None, "function")
        for a in _args(root.args):
            self.root.bound.add(a)
        self._body(root.body, self.root)

    def _fn_scope(self, s: Scope) -> Scope:
        while s.kind == "comp":
            assert s.parent is not None
            s = s.parent
        return s

    def _body(self, stmts: Iterable[ast.AST], s: Scope) -> None:
        for st in stmts:
            self._visit(st, s)

    def _new(self, node: ast.AST, s: Scope, kind: str) -> Scope:
        c = Scope(node, s, kind)
        s.children.append(c)
        return c

    def _visit(self, n: ast.AST, s: Scope) -> None:  # noqa: C901 -- one case per node kind
        if isinstance(
            n,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Import,
                ast.ImportFrom,
                ast.ExceptHandler,
            ),
        ):
            self.owner[id(n)] = s
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            s.bound.add(n.name)
            for d in n.decorator_list:
                self._visit(d, s)
            self._defaults(n.args, s)
            if n.returns is not None:
                self._visit(n.returns, s)
            c = self._new(n, s, "function")
            for a in _args(n.args):
                c.bound.add(a)
            self._body(n.body, c)
            return
        if isinstance(n, ast.Lambda):
            self._defaults(n.args, s)
            c = self._new(n, s, "function")
            for a in _args(n.args):
                c.bound.add(a)
            self._visit(n.body, c)
            return
        if isinstance(n, ast.ClassDef):
            s.bound.add(n.name)
            for d in [*n.decorator_list, *n.bases, *(k.value for k in n.keywords)]:
                self._visit(d, s)
            c = self._new(n, s, "class")
            self._body(n.body, c)
            return
        if isinstance(n, COMPS):
            gens = n.generators
            self._visit(gens[0].iter, s)  # evaluated in the enclosing scope
            c = self._new(n, s, "comp")
            for i, g in enumerate(gens):
                _bind_targets(g.target, c.bound)
                self._visit(g.target, c)
                if i:
                    self._visit(g.iter, c)
                for cond in g.ifs:
                    self._visit(cond, c)
            elts = [n.key, n.value] if isinstance(n, ast.DictComp) else [n.elt]
            for e in elts:
                self._visit(e, c)
            return
        if isinstance(n, ast.NamedExpr):
            f = self._fn_scope(s)
            f.bound.add(n.target.id)
            f.names.append(n.target)
            self._visit(n.value, s)
            return
        if isinstance(n, (ast.Nonlocal, ast.Global)):
            s.declared.update(n.names)
            s.bound.update(n.names)
            if isinstance(n, ast.Nonlocal):
                s.nonlocals.append(n)
            return
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                s.bound.add((al.asname or al.name).split(".")[0])
            return
        if isinstance(n, ast.ExceptHandler) and n.name:
            s.bound.add(n.name)
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                s.bound.add(n.id)
            s.names.append(n)
            return
        for c in ast.iter_child_nodes(n):
            self._visit(c, s)

    def _defaults(self, args: ast.arguments, s: Scope) -> None:
        for d in [*args.defaults, *(k for k in args.kw_defaults if k is not None)]:
            self._visit(d, s)
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if a is not None and a.annotation is not None:
                self._visit(a.annotation, s)


def _args(args: ast.arguments) -> list[str]:
    return [a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs,
                            *([args.vararg] if args.vararg else []),
                            *([args.kwarg] if args.kwarg else [])]]  # fmt: skip


def walk_scopes(s: Scope) -> Iterator[Scope]:
    yield s
    for c in s.children:
        yield from walk_scopes(c)


INLINED = (ast.ListComp, ast.SetComp, ast.DictComp)  # PEP 709: no table of their own (3.12)


def _table_kids(s: Scope) -> list[Scope]:
    """A scope's children as CPython's symtable lists them: an inlined comprehension's own
    children hoisted into its parent; a generator expression keeps a table."""
    out: list[Scope] = []
    for c in s.children:
        out.extend(_table_kids(c) if isinstance(c.node, INLINED) else [c])
    return out


def _table_locals(s: Scope) -> set[str]:
    """The locals symtable reports for a scope: its own, its inlined comprehensions' targets
    (PEP 709 puts them in the parent's table), and a generator expression's hidden `.0`."""
    out = set(s.locals)
    for c in s.children:
        if isinstance(c.node, INLINED):
            out |= _table_locals(c)
    if isinstance(s.node, ast.GeneratorExp):
        out.add(".0")
    return out


def cross_check(src: str, sb: ScopeBuilder) -> list[str]:
    """This resolver against CPython's `symtable`, table by table: the same locals."""
    top = symtable.symtable(src, "x", "exec")
    tab = {t.get_name(): t for t in top.get_children()}["run"]
    bad: list[str] = []

    def walk(t: symtable.SymbolTable, s: Scope, path: str) -> None:
        theirs = {x.get_name() for x in t.get_symbols() if x.is_local() and not x.is_global()}
        mine = _table_locals(s)
        if theirs != mine:
            bad.append(f"{path}: {sorted(theirs ^ mine)}")
        kids, tkids = _table_kids(s), list(t.get_children())
        if len(kids) != len(tkids):
            bad.append(f"{path}: {len(tkids)} tables vs {len(kids)} scopes")
            return
        for ct, cs in zip(tkids, kids, strict=True):
            walk(ct, cs, f"{path}/{ct.get_name()}")

    walk(tab, sb.root, "run")
    return bad


def symtable_renames(src: str, sb: ScopeBuilder, lifted: Sequence[str]) -> list[str]:
    """INDEPENDENT of this resolver's chain walk: for every Name of a lifted name, CPython's
    symtable decides whether it means run()'s binding (the nearest enclosing table where the name
    is a plain local); it must agree with the rename this module makes. [] = it agrees."""
    top = symtable.symtable(src, "x", "exec")
    run_t = {t.get_name(): t for t in top.get_children()}["run"]
    lset = set(lifted)
    bad: list[str] = []

    def owner(stack: list[symtable.SymbolTable], name: str) -> symtable.SymbolTable | None:
        for t in reversed(stack):
            try:
                sym = t.lookup(name)
            except KeyError:
                continue
            if sym.is_global() or sym.is_declared_global():
                return None
            if sym.is_local() and not sym.is_free() and not sym.is_nonlocal():
                return t
        return None

    def names_of(s: Scope) -> list[ast.Name]:  # an inlined comprehension's names: its host's
        out = list(s.names)
        for c in s.children:
            if isinstance(c.node, INLINED):
                if c.bound & lset:
                    both = sorted(c.bound & lset)
                    bad.append(f"line {c.node.lineno}: a comprehension binds {both}")
                out.extend(names_of(c))
        return out

    def walk(stack: list[symtable.SymbolTable], s: Scope) -> None:
        for n in names_of(s):
            if n.id not in lset:
                continue
            here_s = s
            for c in walk_scopes(s):  # the Name's own scope (s, or an inlined comprehension)
                if n in c.names:
                    here_s = c
                    break
            mine = here_s.resolve(n.id) is sb.root
            theirs = owner(stack, n.id) is run_t
            if mine != theirs:
                bad.append(f"line {n.lineno}:{n.col_offset} {n.id}: symtable {theirs}, mine {mine}")
        for ct, cs in zip(list(stack[-1].get_children()), _table_kids(s), strict=True):
            walk([*stack, ct], cs)

    walk([run_t], sb.root)
    return bad


# --- the base's run() -----------------------------------------------------------------------------
@dataclass
class RunInfo:
    tree: ast.Module
    run: ast.FunctionDef
    loop: ast.While
    try_: ast.Try
    sb: ScopeBuilder


def parse_run(src: str) -> RunInfo:
    tree = ast.parse(src)
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    loops = [n for n in ast.walk(run) if isinstance(n, ast.While)
             and ast.unparse(n.test) == LOOP_TEST]  # fmt: skip
    if len(loops) != 1:
        raise SystemExit(f"expected one `while {LOOP_TEST}` in run(), found {len(loops)}")
    trys = [n for n in ast.walk(run) if isinstance(n, ast.Try) and loops[0] in n.body]
    if len(trys) != 1:
        raise SystemExit("expected the main loop directly inside one try:")
    return RunInfo(tree, run, loops[0], trys[0], ScopeBuilder(run))


def run_bindings(ri: RunInfo) -> dict[str, list[tuple[int, str]]]:
    """run()-scope names -> [(line, how)] for every binding of run()'s OWN variable."""
    out: dict[str, list[tuple[int, str]]] = {}
    for s in walk_scopes(ri.sb.root):
        for n in s.names:
            if isinstance(n.ctx, ast.Store) and s.resolve(n.id) is ri.sb.root:
                out.setdefault(n.id, []).append((n.lineno, "store"))
            elif isinstance(n.ctx, ast.Del) and s.resolve(n.id) is ri.sb.root:
                out.setdefault(n.id, []).append((n.lineno, "del"))
    for n in ast.walk(ri.run):
        if n is ri.run:
            continue
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ri.sb.owner.get(id(n)) is ri.sb.root:
                out.setdefault(n.name, []).append((n.lineno, "def"))
        elif isinstance(n, (ast.Import, ast.ImportFrom)) and ri.sb.owner.get(id(n)) is ri.sb.root:
            for al in n.names:
                out.setdefault((al.asname or al.name).split(".")[0], []).append(
                    (n.lineno, "import")
                )
        elif isinstance(n, ast.ExceptHandler) and n.name and ri.sb.owner.get(id(n)) is ri.sb.root:
            out.setdefault(n.name, []).append((n.lineno, "except"))
    for s in walk_scopes(ri.sb.root):
        for nl in s.nonlocals:
            for nm in nl.names:
                up = s.parent
                if s is not ri.sb.root and up is not None and up.resolve(nm) is ri.sb.root:
                    out.setdefault(nm, []).append((nl.lineno, "nonlocal"))
    return out


def lifted_names(ri: RunInfo, not_lifted: Sequence[str] = NOT_LIFTED,
                 extra: Sequence[str] = EXTRA_LIFTED) -> list[str]:  # fmt: skip
    """T1's set: run()'s variables bound before the loop and again inside it or after it, or
    declared nonlocal by a closure; never a refusal's / setup loop's reused name (NOT_LIFTED)."""
    b = run_bindings(ri)
    l0 = ri.loop.lineno
    out = []
    for nm, sites in sorted(b.items()):
        hows = {h for _, h in sites}
        if nm in not_lifted or hows & {"def", "import", "except"}:
            continue
        before = [ln for ln, h in sites if ln < l0 and h == "store"]
        later = [ln for ln, h in sites if ln >= l0 and h == "store"]
        if nm in extra or (before and (later or "nonlocal" in hows)):
            out.append(nm)
    return out


# --- the conditions -------------------------------------------------------------------------------
def conditions(ri: RunInfo, lifted: Sequence[str], aliased: Sequence[str]) -> list[str]:
    """Every precondition of LIFT and ALIAS on the base's run(); [] = all hold."""
    bad: list[str] = []
    b = run_bindings(ri)
    for n in ast.walk(ri.run):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in DYNAMIC:
            bad.append(f"line {n.lineno}: {n.func.id}() in run()")
        if isinstance(n, ast.ExceptHandler) and n.type is not None:
            names = {x.id for x in ast.walk(n.type) if isinstance(x, ast.Name)}
            if names & {"NameError", "UnboundLocalError", "BaseException"}:
                bad.append(f"line {n.lineno}: catches {sorted(names)}")
            if n.type is None:
                bad.append(f"line {n.lineno}: a bare except")
    for s in walk_scopes(ri.sb.root):
        if HS in s.bound or any(x.id == HS for x in s.names):
            bad.append(f"the name {HS!r} is already used in run()")
            break
    for nm in lifted:
        hows = {h for _, h in b.get(nm, [])}
        if hows & {"del", "def", "import", "except"}:
            bad.append(f"{nm}: bound by {sorted(hows)}")
    for nm in aliased:
        sites = b.get(nm, [])
        stores = [x for x in sites if x[1] == "store"]
        if len(stores) != 1 or len(sites) != 1:
            bad.append(f"{nm}: an alias needs exactly one binding, has {sites}")
        if nm in lifted:
            bad.append(f"{nm}: both lifted and aliased")
    for s in walk_scopes(ri.sb.root):
        if s.kind == "class":
            bad.append(f"line {s.node.lineno}: a class inside run()")  # type: ignore[attr-defined]
    return bad


# --- LIFT + ALIAS on the AST (what `check` compares against) --------------------------------------
class _Lift(ast.NodeTransformer):
    def __init__(self, ri: RunInfo, lifted: set[str], aliased: set[str]) -> None:
        self.ri, self.lifted, self.aliased = ri, lifted, aliased
        self.rename = {id(n) for s in walk_scopes(ri.sb.root) for n in s.names
                       if n.id in lifted and s.resolve(n.id) is ri.sb.root}  # fmt: skip
        self.alias_at = {id(n) for s in [ri.sb.root] for n in s.names
                         if n.id in aliased and isinstance(n.ctx, ast.Store)}  # fmt: skip

    def visit_Name(self, n: ast.Name) -> ast.AST:
        if id(n) in self.rename:
            return ast.Attribute(ast.Name(HS, ast.Load()), n.id, n.ctx)
        return n

    def visit_Nonlocal(self, n: ast.Nonlocal) -> ast.AST | None:
        keep = [x for x in n.names if x not in self.lifted or not self._outer(n, x)]
        if not keep:
            return None
        n.names = keep
        return n

    def _outer(self, n: ast.Nonlocal, name: str) -> bool:
        for s in walk_scopes(self.ri.sb.root):
            if n in s.nonlocals:
                return s.parent is not None and s.parent.resolve(name) is self.ri.sb.root
        return False

    def visit_AnnAssign(self, n: ast.AnnAssign) -> ast.AST | None:
        t = n.target
        if isinstance(t, ast.Name) and (id(t) in self.rename or id(t) in self.alias_at):
            if n.value is None:
                return None
            return self.visit(ast.Assign([t], n.value, lineno=n.lineno))
        return self.generic_visit(n)

    def visit_Assign(self, n: ast.Assign) -> ast.AST:
        al = [t for t in n.targets if isinstance(t, ast.Name) and id(t) in self.alias_at]
        n = self.generic_visit(n)  # type: ignore[assignment]
        if al:
            (t,) = al
            n.targets = [*n.targets, ast.Attribute(ast.Name(HS, ast.Load()), t.id, ast.Store())]
        return n


def lift_ast(ri: RunInfo, lifted: Sequence[str], aliased: Sequence[str]) -> ast.FunctionDef:
    run = copy.deepcopy(ri.run)
    ri2 = RunInfo(ri.tree, run, ri.loop, ri.try_, ScopeBuilder(run))  # node ids of the copy
    out = _Lift(ri2, set(lifted), set(aliased)).visit(run)
    body = out.body
    i = 1 if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
        else 0  # fmt: skip
    body.insert(
        i,
        ast.Assign(
            [ast.Name(HS, ast.Store())],
            ast.Call(ast.Name("HuntState", ast.Load()), [], []),
            lineno=0,
        ),
    )
    return out


# --- the text rewrites (derive) -------------------------------------------------------------------
class Edits:
    """Byte-exact text edits on a source (columns are UTF-8 byte offsets, as ast's)."""

    def __init__(self, src: str) -> None:
        self.lines = [ln.encode() for ln in src.splitlines(keepends=True)]
        self.ops: list[tuple[int, int, int, bytes]] = []  # (line0, col_from, col_to, new)

    def insert(self, line: int, col: int, text: str) -> None:
        self.ops.append((line - 1, col, col, text.encode()))

    def replace(self, line: int, c0: int, c1: int, text: str) -> None:
        self.ops.append((line - 1, c0, c1, text.encode()))

    def apply(self) -> str:
        for li, c0, c1, new in sorted(self.ops, key=lambda o: (o[0], o[1], o[2]), reverse=True):
            b = self.lines[li]
            self.lines[li] = b[:c0] + new + b[c1:]
        return b"".join(self.lines).decode()


def derive_lift(src: str, lifted: Sequence[str], aliased: Sequence[str]) -> str:
    return lift_edits(src, lifted, aliased).apply()


def lift_edits(src: str, lifted: Sequence[str], aliased: Sequence[str]) -> Edits:
    """LIFT + ALIAS as text edits on `src` (not yet applied)."""
    ri = parse_run(src)
    ed = Edits(src)
    root = ri.sb.root
    lset, aset = set(lifted), set(aliased)
    ann = {id(n.target): n for n in ast.walk(ri.run) if isinstance(n, ast.AnnAssign)}
    for s in walk_scopes(root):
        for n in s.names:
            if n.id in lset and s.resolve(n.id) is root:
                a = ann.get(id(n))
                if a is not None:  # name: T = v -> hs.name = v (the type is the class's)
                    if a.value is None:
                        raise SystemExit(f"line {a.lineno}: a bare annotation of {n.id}")
                    ed.replace(
                        n.end_lineno or n.lineno,
                        n.end_col_offset or 0,
                        a.annotation.end_col_offset or 0,
                        "",
                    )
                ed.insert(n.lineno, n.col_offset, f"{HS}.")
    for n in root.names:  # ALIAS: name = v -> name = hs.name = v
        if n.id in aset and isinstance(n.ctx, ast.Store):
            a = ann.get(id(n))
            stmt = a or next(x for x in ast.walk(ri.run) if isinstance(x, ast.Assign)
                             and any(t is n for t in x.targets))  # fmt: skip
            assert stmt.value is not None
            if a is not None:
                ed.replace(
                    n.end_lineno or n.lineno,
                    n.end_col_offset or 0,
                    a.annotation.end_col_offset or 0,
                    "",
                )
            ed.insert(stmt.value.lineno, stmt.value.col_offset, f"{HS}.{n.id} = ")
    for s in walk_scopes(root):
        for nl in s.nonlocals:
            keep = [
                x
                for x in nl.names
                if x not in lset or s.parent is None or s.parent.resolve(x) is not root
            ]
            if keep == nl.names:
                continue
            line = ed.lines[nl.lineno - 1]
            if keep:
                ed.replace(
                    nl.lineno, nl.col_offset, nl.end_col_offset or 0, "nonlocal " + ", ".join(keep)
                )
            else:
                ed.replace(nl.lineno, 0, len(line), "")
    body0 = ri.run.body[1] if isinstance(ri.run.body[0], ast.Expr) else ri.run.body[0]
    ed.insert(body0.lineno, 0, f"    {HS} = HuntState()\n")
    return ed


# --- OUTLINE --------------------------------------------------------------------------------------
def loop_signals(stmts: Sequence[ast.stmt]) -> Iterator[tuple[ast.stmt, str]]:
    """The loop-level `continue` / `break` of a section (not those of its own inner loops)."""

    def go(n: ast.AST, depth: int) -> Iterator[tuple[ast.stmt, str]]:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        if isinstance(n, ast.Continue) and depth == 0:
            yield n, TICK_DONE
        elif isinstance(n, ast.Break) and depth == 0:
            yield n, RUN_END
        if isinstance(n, LOOPS):
            for c in n.body:
                yield from go(c, depth + 1)
            for c in n.orelse:
                yield from go(c, depth)
            for c in [n.target, n.iter] if isinstance(n, (ast.For, ast.AsyncFor)) else [n.test]:
                yield from go(c, depth)
            return
        for c in ast.iter_child_nodes(n):
            yield from go(c, depth)

    for st in stmts:
        yield from go(st, 0)


def bound_in(stmts: Sequence[ast.stmt]) -> list[str]:
    """Names a section binds in ITS scope (not in its closures or comprehensions; a walrus in a
    comprehension binds here)."""
    holder = ast.FunctionDef("x", ast.arguments([], [], None, [], [], None, []), list(stmts), [],
                             None, None, [])  # fmt: skip
    sb = ScopeBuilder(holder)
    return sorted(sb.root.bound)


def loop_hazards(stmts: Sequence[ast.stmt]) -> list[str]:
    bad = []
    for st in stmts:
        for n in _walk_no_scopes(st):
            if isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom, ast.Await)):
                bad.append(f"line {n.lineno}: {type(n).__name__} in the loop body")
    return bad


def _walk_no_scopes(n: ast.AST) -> Iterator[ast.AST]:
    yield n
    for c in ast.iter_child_nodes(n):
        if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield from _walk_no_scopes(c)


def sections(
    loop: ast.While, src_lines: Sequence[str], spec: Sequence[tuple[str, str]] = SECTIONS
) -> list[tuple[str, list[ast.stmt]]]:
    starts = []
    for name, text in spec:
        k = text.count("\n") + 1  # a marker may span lines (each compared stripped)
        idx = [i for i, st in enumerate(loop.body)
               if "\n".join(x.strip() for x in src_lines[st.lineno - 1 : st.lineno - 1 + k])
               .startswith(text)]  # fmt: skip
        if len(idx) != 1:
            raise SystemExit(f"section {name}: {len(idx)} statements start with {text!r}")
        starts.append((name, idx[0]))
    if starts[0][1] != 0 or [i for _, i in starts] != sorted(i for _, i in starts):
        raise SystemExit("the sections must start at the loop's first statement, in order")
    out = []
    for k, (name, i0) in enumerate(starts):
        i1 = starts[k + 1][1] if k + 1 < len(starts) else len(loop.body)
        out.append((name, loop.body[i0:i1]))
    return out


def loop_annassigns(stmts: Sequence[ast.stmt]) -> list[ast.AnnAssign]:
    """The loop body's own annotated assignments (not its closures'): a step's `nonlocal` name
    cannot be annotated, so OUTLINE moves each annotation to the name's declaration."""
    out = []
    for st in stmts:
        for n in _walk_no_scopes(st):
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                out.append(n)
    return out


def loop_only_names(ri: RunInfo) -> list[str]:
    """run()-scope names whose every binding is inside the main loop's body: once OUTLINE moves
    them into the steps, run() must still DECLARE them (a bare annotation binds nothing), or the
    steps' `nonlocal` would find no binding (and a read before any assignment must stay an error,
    as it was)."""
    l0, l1 = ri.loop.lineno, ri.loop.end_lineno or ri.loop.lineno
    bound = set(bound_in(ri.loop.body))
    out = []
    for nm, sites in run_bindings(ri).items():
        if nm in bound and all(l0 <= ln <= l1 for ln, how in sites if how != "nonlocal"):
            out.append(nm)
    return sorted(out)


def _wrap(names: Sequence[str], indent: int, width: int = 100) -> list[list[str]]:
    """`nonlocal` lists that fit the line width (several statements: the same declaration)."""
    out: list[list[str]] = []
    cur: list[str] = []
    for n in names:
        if cur and indent + len("nonlocal ") + len(", ".join([*cur, n])) > width:
            out.append(cur)
            cur = []
        cur.append(n)
    return [*out, cur] if cur else out


def derive_outline(src: str, spec: Sequence[tuple[str, str]] = SECTIONS) -> str:
    return outline_edits(src, spec).apply()


def outline_edits(src: str, spec: Sequence[tuple[str, str]] = SECTIONS) -> Edits:
    """OUTLINE as text edits on `src` (not yet applied): the `while` line becomes the
    declarations, each section gets its def header (and its nonlocal line) above it, the loop-level
    continue / break their signals, the loop-level annotations go, and the driver follows the
    last section."""
    ri = parse_run(src)
    lines = src.splitlines(keepends=True)
    loop = ri.loop
    if loop.orelse:
        raise SystemExit("the main loop has an else: (a break would skip it)")
    secs = sections(loop, lines, spec)
    hz = loop_hazards(loop.body)
    if hz:
        raise SystemExit("; ".join(hz))
    ind = " " * loop.body[0].col_offset  # the loop body's indentation (the steps' bodies')
    dind = " " * loop.col_offset  # the defs' (the loop's own)
    ed = Edits(src)
    ann: dict[str, str] = {}
    prev_end = loop.lineno  # the `while` line; a section's text starts on the line after
    for k, (name, stmts) in enumerate(secs):
        for aa in loop_annassigns(stmts):  # name: T = v -> name = v (T goes to the declaration)
            if aa.value is None:
                raise SystemExit(f"line {aa.lineno}: a bare annotation in the loop body")
            ann.setdefault(aa.target.id, ast.unparse(aa.annotation))
            t = aa.target
            ed.replace(t.end_lineno or t.lineno, t.end_col_offset or 0,
                       aa.annotation.end_col_offset or 0, "")  # fmt: skip
        for node, sig in loop_signals(stmts):
            kw = "continue" if sig == TICK_DONE else "break"
            ed.replace(node.lineno, node.col_offset, node.col_offset + len(kw), f"return {sig}")
        nl = bound_in(stmts)
        head = ("\n" if k else "") + f"{dind}def step_{name}() -> str | None:\n"
        if name in STEP_DOCS:
            head += f'{ind}"""{STEP_DOCS[name]}"""\n'
        head += "".join(f"{ind}nonlocal {', '.join(g)}\n" for g in _wrap(nl, len(ind)))
        ed.insert(prev_end + 1, 0, head)
        prev_end = stmts[-1].end_lineno or stmts[-1].lineno
    names = [n for n, _ in secs]
    steps = (f"\n{dind}hunt_steps = (\n"
             + "".join(f'{dind}    ("{n}", step_{n}),\n' for n in names)
             + f"{dind})\n\n"
             f"{dind}def hunt_tick() -> str | None:\n"
             f"{ind}for _name, step_ in hunt_steps:\n"
             f"{ind}    sig_ = step_()\n"
             f"{ind}    if sig_ is not None:\n"
             f"{ind}        return sig_\n"
             f"{ind}return None\n\n"
             f"{dind}while {LOOP_TEST}:\n"
             f"{ind}if hunt_tick() == {RUN_END}:\n"
             f"{ind}    break\n")  # fmt: skip
    ed.insert(prev_end + 1, 0, steps)
    decl = "".join(f"{dind}{n}: {ann.get(n, 'Any')}\n" for n in loop_only_names(ri))
    if decl:
        decl = f"{dind}{DECL_COMMENT}\n{decl}\n"
    wl = ed.lines[loop.lineno - 1]
    ed.replace(loop.lineno, 0, len(wl), decl)  # the `while` line -> the declarations
    return ed


# --- check ----------------------------------------------------------------------------------------
def _strip_docstrings(fn: ast.AST) -> None:
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):  # fmt: skip
            n.body = n.body[1:] or [ast.Pass()]


def inline_steps(run: ast.FunctionDef, *, drive_ok: bool = False
                 ) -> tuple[ast.FunctionDef, list[str], list[str]]:  # fmt: skip
    """OUTLINE's inverse on the committed run(): the steps' bodies back into the loop, in the
    driver's order; returns (run, the step names, the conditions that failed). ``drive_ok``: a
    5b-2 drive branch around the loop is read as its else (the driver loop; `drive` proves the
    rest); else it is a failed condition (stage5b_ab: B must be 5b-1's rewrite alone)."""
    run, branch = undrive(run)
    bad: list[str] = []
    if branch is not None and not drive_ok:
        bad.append(f"NOT 5b-1's rewrite alone: a 5b-2 drive branch (if {DRIVE_TEST}, line "
                   f"{branch.lineno})")  # fmt: skip
    trys = [n for n in ast.walk(run) if isinstance(n, ast.Try)
            and any(isinstance(x, ast.While) and ast.unparse(x.test) == LOOP_TEST
                    for x in n.body)]  # fmt: skip
    if len(trys) != 1:
        return run, [], ["no driver loop inside a try:"]
    body = trys[0].body
    decls = [n for n in body if isinstance(n, ast.AnnAssign) and n.value is None
             and isinstance(n.target, ast.Name)]  # fmt: skip
    declared = {n.target.id for n in decls}  # type: ignore[union-attr]
    for n in decls:
        body.remove(n)
    defs = {n.name: n for n in body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("step_")}  # fmt: skip
    hs_ = [n for n in body
           if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "hunt_steps"]  # fmt: skip
    if len(hs_) != 1:
        return run, [], ["no hunt_steps tuple"]
    order = [ast.literal_eval(e.elts[0]) for e in hs_[0].value.elts]  # type: ignore[attr-defined]
    for e in hs_[0].value.elts:  # type: ignore[attr-defined]
        if ast.unparse(e.elts[1]) != f"step_{ast.literal_eval(e.elts[0])}":
            bad.append(f"hunt_steps: {ast.unparse(e)}")
    if set(order) != {k[5:] for k in defs}:
        bad.append(f"hunt_steps {order} vs the step defs {sorted(defs)}")
    tick = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == "hunt_tick"]
    want_tick = ("def hunt_tick() -> str | None:\n    for _name, step_ in hunt_steps:\n"
                 "        sig_ = step_()\n        if sig_ is not None:\n            return sig_\n"
                 "    return None")  # fmt: skip
    if len(tick) != 1 or ast.unparse(_nodoc(tick[0])) != want_tick:
        bad.append("hunt_tick is not the driver's exact form")
    loops = [n for n in body if isinstance(n, ast.While) and ast.unparse(n.test) == LOOP_TEST]
    want_loop = f"while {LOOP_TEST}:\n    if hunt_tick() == {RUN_END}:\n        break"
    if len(loops) != 1 or ast.unparse(loops[0]) != want_loop:
        bad.append("the loop is not the driver's exact form")
    new_body: list[ast.stmt] = []
    for name in order:
        fn = defs.get(f"step_{name}")
        if fn is None:
            continue
        fn = _nodoc(copy.deepcopy(fn))
        if ast.unparse(fn.returns) != "str | None" if fn.returns else True:
            bad.append(f"step_{name}: its return annotation")
        stmts = list(fn.body)
        declared: set[str] = set()
        while stmts and isinstance(stmts[0], ast.Nonlocal):  # the step's head (one or more)
            declared |= set(stmts[0].names)
            stmts = stmts[1:]
        if set(bound_in(stmts)) != declared:
            bad.append(f"step_{name}: binds {sorted(set(bound_in(stmts)) ^ declared)} "
                       "not as nonlocal (a step has no local of its own)")  # fmt: skip
        for st in stmts:
            for n in _walk_no_scopes(st):
                if isinstance(n, ast.Return):
                    pass
        new_body.extend(_unsignal(stmts, bad, name))
    for n in list(body):
        if n in defs.values() or n in hs_ or n in tick:
            body.remove(n)
    loops[0].body = new_body
    try:
        need = set(loop_only_names(RunInfo(ast.Module([run], []), run, loops[0], trys[0],
                                           ScopeBuilder(run))))  # fmt: skip
    except SystemExit as e:
        need = set()
        bad.append(str(e))
    if declared != need:
        bad.append(f"run()'s declarations: {sorted(declared ^ need)} differ from the names only "
                   "the steps bind")  # fmt: skip
    return run, order, bad


def undrive(run: ast.FunctionDef) -> tuple[ast.FunctionDef, ast.If | None]:
    """5b-2's inverse on a run(): its drive branch `if hook_drives(hook): <the drive> else: <the
    driver loop>` becomes the else alone (run() as 5b-1 left it). (a copy of run, the branch
    removed -- None: there was none)."""
    run = copy.deepcopy(run)
    for n in ast.walk(run):
        for fld in ("body", "orelse", "finalbody"):
            stmts = getattr(n, fld, None)
            if not isinstance(stmts, list):
                continue
            for i, st in enumerate(stmts):
                if isinstance(st, ast.If) and ast.unparse(st.test) == DRIVE_TEST:
                    stmts[i : i + 1] = st.orelse
                    return run, st
    return run, None


def _step_body(fn: ast.FunctionDef) -> list[ast.stmt]:
    """A step's statements after its docstring and its nonlocal head."""
    stmts = list(_nodoc(copy.deepcopy(fn)).body)
    while stmts and isinstance(stmts[0], ast.Nonlocal):
        stmts = stmts[1:]
    return stmts


def guard_problems(run: ast.FunctionDef, guarded: dict[str, str] = GUARDED) -> list[str]:
    """The facts the cursor relies on, on the committed steps: each GUARDED step's statements are
    `if` statements (no else) whose test is `hs.mode == "<mode>"`, alone or as the first term of
    an `and` -- so with another mode the step does nothing (no test holds, so nothing runs and the
    mode stays) -- and in the fight step every `return` is `return TICK_DONE` and its if ends with
    one (in mode fight a tick's mode work ends there, as 13.2's table says). [] = all hold."""
    steps = {n.name[5:]: n for n in ast.walk(run)
             if isinstance(n, ast.FunctionDef) and n.name.startswith("step_")}  # fmt: skip
    bad: list[str] = []
    for name, mode in guarded.items():
        fn = steps.get(name)
        if fn is None:
            bad.append(f"no step_{name}")
            continue
        want = f"{HS}.mode == {mode!r}"  # (ast.unparse quotes a string with ')
        body = _step_body(fn)
        for st in body:
            t = st.test if isinstance(st, ast.If) else None
            first = t.values[0] if isinstance(t, ast.BoolOp) and isinstance(t.op, ast.And) else t
            if t is None or st.orelse or first is None or ast.unparse(first) != want:  # type: ignore[union-attr]
                bad.append(f"step_{name}: {ast.unparse(st).splitlines()[0][:70]!r} is not an if "
                           f"on {want} (its guard)")  # fmt: skip
        if name == "fight" and body and isinstance(body[-1], ast.If):
            rets = [n for st in body for n in _walk_no_scopes(st) if isinstance(n, ast.Return)]
            if any(r.value is None or ast.unparse(r.value) != TICK_DONE for r in rets):
                bad.append("step_fight: a return that is not TICK_DONE")
            last = body[-1].body[-1] if body[-1].body else None
            if not (isinstance(last, ast.Return) and last.value is not None
                    and ast.unparse(last.value) == TICK_DONE):  # fmt: skip
                bad.append("step_fight: its if does not end with return TICK_DONE")
    return bad


class _Unflag(ast.NodeTransformer):
    """live-blocks 18: every statement list with each fly-first branch replaced by its else (or,
    ``take_body``, by its body: the program with the flag on)."""

    def __init__(self, take_body: bool = False, tests: Sequence[str] = FLY_FIRST_TESTS) -> None:
        self.n = 0
        self.empty: list[int] = []
        self.take_body = take_body
        self.tests = tuple(tests)

    def _stmts(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for st in stmts:
            if isinstance(st, ast.If) and ast.unparse(st.test) in self.tests:
                self.n += 1
                out.extend(self._stmts(st.body if self.take_body else st.orelse))
            else:
                out.append(self.visit(st))
        return out

    def generic_visit(self, node: ast.AST) -> ast.AST:
        for name, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(x, ast.stmt) for x in value):
                got = self._stmts(value)
                if not got:
                    self.empty.append(getattr(node, "lineno", 0))
                setattr(node, name, got)
            elif isinstance(value, list):
                setattr(node, name, [self.visit(x) if isinstance(x, ast.AST) else x for x in value])
            elif isinstance(value, ast.AST):
                setattr(node, name, self.visit(value))
        return node


def unflag(src: str, tests: Sequence[str] = FLY_FIRST_TESTS,
           added: Sequence[str] = FLY_FIRST_ADDED,
           params: Sequence[str] = ()) -> tuple[str, int]:  # fmt: skip
    """PURE (live-blocks 18): ``src`` with every fly-first branch (``if <tests>:``, anywhere) read
    as its else, and without the top-level statements named in ``added``; and how many branches it
    read. Unchanged text when there are none. Raises ValueError when a branch's removal leaves a
    body empty (a branch must REPLACE code or add to it). 18.15: ``params``, keyword-only
    parameters the family adds (default None), are dropped from every function's signature -- the
    comparison with the base then proves no use of them is left outside a branch."""
    tree = ast.parse(src)
    u = _Unflag(tests=tests)
    tree = u.visit(tree)
    if u.empty:
        raise ValueError(f"a fly-first branch leaves a body empty (line {u.empty[0]})")
    dropped = 0
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        keep = [(x, d) for x, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True)
                if x.arg not in params]  # fmt: skip
        if len(keep) != len(fn.args.kwonlyargs):
            for x, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults, strict=True):
                if x.arg in params and not (isinstance(d, ast.Constant) and d.value is None):
                    raise ValueError(f"{fn.name}: the family's keyword {x.arg} has no None default")
            dropped += len(fn.args.kwonlyargs) - len(keep)
            fn.args.kwonlyargs = [x for x, _d in keep]
            fn.args.kw_defaults = [d for _x, d in keep]

    def name_of(n: ast.stmt) -> str | None:
        if isinstance(n, ast.FunctionDef | ast.ClassDef | ast.AsyncFunctionDef):
            return n.name
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            return ast.unparse(n.targets[0])
        if isinstance(n, ast.AnnAssign):
            return ast.unparse(n.target)
        return None

    kept = [n for n in tree.body if name_of(n) not in added]
    if u.n == 0 and len(kept) == len(tree.body) and not dropped:
        return src, 0
    tree.body = kept
    return ast.unparse(tree), u.n


def unpick(src: str) -> tuple[str, int]:
    """PURE (live-blocks 18.15): ``src`` with the model-pick family read as its else (unflag with
    MODEL_PICK_TESTS / _ADDED / _PARAMS: 9.58's program); how many branches it read."""
    return unflag(src, MODEL_PICK_TESTS, MODEL_PICK_ADDED, MODEL_PICK_PARAMS)


def flag_check(base_src: str, new_src: str, tests: Sequence[str] = FLY_FIRST_HP_TESTS,
               added: Sequence[str] = FLY_FIRST_HP_ADDED, *,
               pick: bool = True) -> int:  # fmt: skip
    """live-blocks 18.11: with ONLY the ``tests`` branches read as their else and ``added`` left
    out, the WHOLE module is ``base_src``'s (FLAG_BASE: the runner s7ab measured), as ASTs,
    docstrings included. Prints each fact; rc 0 when it holds. 18.15: the model-pick family (a
    runner newer than FLAG_BASE's) is read as its else first (``pick``; `pick` proves it alone)."""
    if pick:
        new_src, n_mp = unpick(new_src)
        print(f"model-pick branches read as their else (live-blocks 18.15): {n_mp}; left out "
              f"{list(MODEL_PICK_ADDED)} and the keyword {list(MODEL_PICK_PARAMS)}")  # fmt: skip
    got, n = unflag(new_src, tests, added)
    print(f"{'/'.join(tests)} branches read as their else: {n}; left out {list(added)}")
    a, b = ast.parse(base_src), ast.parse(got)
    same = dump(a) == dump(b)
    print(f"the module == the base's (as ASTs): {'YES' if same else 'NO'}")
    if not same:
        import difflib

        ua, ub = ast.unparse(a).splitlines(), ast.unparse(b).splitlines()
        for ln in list(difflib.unified_diff(ua, ub, "base", "committed", lineterm="", n=2))[:60]:
            print("   ", ln)
    return 0 if same and n > 0 else 1


def pick_check(base_src: str, new_src: str) -> int:
    """live-blocks 18.15: with ONLY the model-pick branches read as their else, its module names
    and BoxWatch's keyword left out, the WHOLE module is ``base_src``'s (PICK_BASE: the 9.58 runner
    s8ab measured), as ASTs, docstrings included. Prints each fact; rc 0 when it holds."""
    got, n = unpick(new_src)
    print(f"{'/'.join(MODEL_PICK_TESTS)} branches read as their else: {n}; left out "
          f"{list(MODEL_PICK_ADDED)} and the keyword {list(MODEL_PICK_PARAMS)}")  # fmt: skip
    a, b = ast.parse(base_src), ast.parse(got)
    same = dump(a) == dump(b)
    print(f"the module == the base's (as ASTs): {'YES' if same else 'NO'}")
    if not same:
        import difflib

        ua, ub = ast.unparse(a).splitlines(), ast.unparse(b).splitlines()
        for ln in list(difflib.unified_diff(ua, ub, "base", "committed", lineterm="", n=2))[:60]:
            print("   ", ln)
    return 0 if same and n > 0 else 1


def drive_check(base_src: str, new_src: str) -> int:
    """5b-2's proof (live-blocks.md 14): with no drive the program is 5b-1's. Prints each fact,
    rc 0 when all hold. live-blocks 18: the file's fly-first branches are read as their else
    (18.15: and its model-pick family)."""
    new_src, n_ff = unflag(new_src)
    print(f"fly-first branches read as their else (live-blocks 18): {n_ff}")
    new_src, n_mp = unpick(new_src)
    print(f"model-pick branches read as their else (live-blocks 18.15): {n_mp}")
    base_tree, new_tree = ast.parse(base_src), ast.parse(new_src)

    def run_of(t: ast.Module) -> ast.FunctionDef:
        return next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == "run")

    base_run, new_run = run_of(base_tree), run_of(new_tree)
    got, branch = undrive(new_run)
    bad: list[str] = []
    want_loop = f"while {LOOP_TEST}:\n    if hunt_tick() == {RUN_END}:\n        break"
    if branch is None:
        bad.append(f"no drive branch (if {DRIVE_TEST}: ... else: the driver loop)")
    elif len(branch.orelse) != 1 or ast.unparse(branch.orelse[0]) != want_loop:
        bad.append("the drive branch's else is not exactly 5b-1's driver loop")
    same = dump(got) == dump(base_run)
    print(f"base: {DRIVE_BASE}'s run() (5b-1), lines {base_run.lineno}-{base_run.end_lineno}")
    print(f"the drive branch: {'line ' + str(branch.lineno) if branch else 'NONE'}; its "
          f"condition: {DRIVE_TEST}; its else: 5b-1's driver loop"
          f"{'' if not bad else ' -- NO: ' + '; '.join(bad)}")  # fmt: skip
    if branch is not None:
        calls = sorted({ast.unparse(c.func) for st in branch.body for c in ast.walk(st)
                        if isinstance(c, ast.Call)})  # fmt: skip
        print(f"the drive branch's body: {len(branch.body)} statements; it calls {calls}")
    print(f"run() without the drive branch == 5b-1's run() (as ASTs, docstrings included): "
          f"{'YES' if same else 'NO'}")  # fmt: skip
    if not same:
        import difflib

        a, b = ast.unparse(base_run).splitlines(), ast.unparse(got).splitlines()
        for ln in list(difflib.unified_diff(a, b, "5b-1", "committed", lineterm="", n=2))[:60]:
            print("   ", ln)

    def top(t: ast.Module) -> dict[str, str]:
        out: dict[str, str] = {}
        for n in t.body:
            if isinstance(n, ast.FunctionDef) and n.name == "run":
                continue
            key = getattr(n, "name", None)
            if key is None and isinstance(n, ast.Assign | ast.AnnAssign):
                tgt = n.targets[0] if isinstance(n, ast.Assign) else n.target
                key = ast.unparse(tgt)
            out[key or ast.unparse(n)[:60]] = dump(n)
        return out

    a, b = top(base_tree), top(new_tree)
    changed = sorted(k for k in a if a[k] != b.get(k))
    added = sorted(set(b) - set(a))
    kept = "unchanged" if not changed else f"CHANGED: {changed}"
    print(f"the module outside run(): 5b-1's statements {kept}; added {added}")
    extra = sorted(set(added) ^ set(DRIVE_ADDED))
    if extra:
        bad.append(f"the added statements are not DRIVE_ADDED: {extra}")
    print(f"the additions == DRIVE_ADDED: {'YES' if not extra else 'NO -- ' + bad[-1]}")
    gb = guard_problems(new_run)
    holds = "each acts only in its mode; step_fight ends a fight tick with TICK_DONE"
    print(f"the guarded steps ({', '.join(f'{k}: mode {v}' for k, v in GUARDED.items())}): "
          f"{holds if not gb else '; '.join(gb)}")  # fmt: skip
    names: list[str] = []
    for n in ast.walk(new_run):
        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "hunt_steps":
            names = [ast.literal_eval(e.elts[0]) for e in n.value.elts]  # type: ignore[attr-defined]
    consts = {ast.unparse(n.targets[0]): n.value for n in new_tree.body
              if isinstance(n, ast.Assign) and len(n.targets) == 1}  # fmt: skip
    sn = consts.get("STEP_NAMES")
    step_names = list(ast.literal_eval(sn)) if sn is not None else []
    print(f"STEP_NAMES == hunt_steps' names: {'YES' if names == step_names else 'NO'}")
    ok = same and not bad and not changed and not gb and names == step_names and bool(names)
    return 0 if ok else 1


def driver_loop(tree: ast.AST, fly_first: bool = False) -> ast.While:
    """For tests that reason about "the loop's statements": run()'s main loop as the driver PLAYS
    it -- the steps' bodies inlined in hunt_steps' order, `return TICK_DONE` as `continue`,
    `return RUN_END` as `break` (OUTLINE's inverse; `check` proves it is the same program). `tree`:
    run()'s FunctionDef or a module holding it; a run() not outlined: its own loop. live-blocks 18:
    the fly-first branches read as their else (today's runner), or with ``fly_first`` as their
    body (the runner with --fly-first)."""
    tree = _Unflag(take_body=fly_first).visit(copy.deepcopy(tree))
    run = tree if isinstance(tree, ast.FunctionDef) else next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "run")  # fmt: skip
    outlined = any(isinstance(n, ast.FunctionDef) and n.name == "hunt_tick" for n in ast.walk(run))
    got = inline_steps(run, drive_ok=True)[0] if outlined else run
    (loop,) = [n for n in ast.walk(got) if isinstance(n, ast.While)
               and ast.unparse(n.test) == LOOP_TEST]  # fmt: skip
    return loop


def _nodoc(fn: ast.FunctionDef) -> ast.FunctionDef:
    if fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant):
        fn.body = fn.body[1:]
    return fn


def _unsignal(stmts: list[ast.stmt], bad: list[str], name: str) -> list[ast.stmt]:
    class T(ast.NodeTransformer):
        def __init__(self) -> None:
            self.depth = 0

        def visit_FunctionDef(self, n: ast.FunctionDef) -> ast.AST:
            return n

        visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

        def visit_Lambda(self, n: ast.Lambda) -> ast.AST:
            return n

        def _loop(self, n: ast.AST) -> ast.AST:
            self.depth += 1
            n.body = [self.visit(x) for x in n.body]  # type: ignore[attr-defined]
            self.depth -= 1
            n.orelse = [self.visit(x) for x in n.orelse]  # type: ignore[attr-defined]
            return n

        visit_For = visit_While = visit_AsyncFor = _loop  # noqa: N815

        def visit_Return(self, n: ast.Return) -> ast.AST:
            v = ast.unparse(n.value) if n.value is not None else None
            if self.depth == 0 and v == TICK_DONE:
                return ast.Continue()
            if self.depth == 0 and v == RUN_END:
                return ast.Break()
            bad.append(f"step_{name}: a return {v} at line {n.lineno}")
            return n

        def visit_Continue(self, n: ast.Continue) -> ast.AST:
            if self.depth == 0:
                bad.append(f"step_{name}: a loop-level continue")
            return n

        visit_Break = visit_Continue  # noqa: N815

    t = T()
    return [t.visit(s) for s in stmts]


class _NoAnn(ast.NodeTransformer):
    """`name: T = v` -> `name = v` (a local's annotation is never evaluated), not in closures."""

    def visit_FunctionDef(self, n: ast.FunctionDef) -> ast.AST:
        return n

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Lambda(self, n: ast.Lambda) -> ast.AST:
        return n

    def visit_AnnAssign(self, n: ast.AnnAssign) -> ast.AST:
        if n.value is not None and isinstance(n.target, ast.Name):
            return ast.Assign([n.target], n.value, lineno=n.lineno)
        return n


def normalize_loop(run: ast.FunctionDef) -> None:
    for w in ast.walk(run):
        if isinstance(w, ast.While) and ast.unparse(w.test) == LOOP_TEST:
            w.body = [_NoAnn().visit(st) for st in w.body]


def dump(n: ast.AST) -> str:
    return ast.dump(n, annotate_fields=False, include_attributes=False)


def check(
    base_src: str,
    new_src: str,
    aliased: Sequence[str] = ALIASED,
    not_lifted: Sequence[str] = NOT_LIFTED,
    extra: Sequence[str] = EXTRA_LIFTED,
    *,
    drive_ok: bool = False,
) -> int:
    """``drive_ok`` (the CLI's): a 5b-2 drive branch is read as its else (inline_steps).
    live-blocks 18: the file's fly-first branches are read as their else (unflag; 18.15: and its
    model-pick family, unpick)."""
    new_src, n_ff = unflag(new_src)
    print(f"fly-first branches read as their else (live-blocks 18): {n_ff}")
    new_src, n_mp = unpick(new_src)
    print(f"model-pick branches read as their else (live-blocks 18.15): {n_mp}")
    ri = parse_run(base_src)
    lifted = lifted_names(ri, not_lifted, extra)
    cond = conditions(ri, lifted, aliased)
    cc = cross_check(base_src, ri.sb) + symtable_renames(base_src, ri.sb, lifted)
    want = lift_ast(ri, lifted, aliased)
    new_tree = ast.parse(new_src)
    new_run = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    outlined = any(isinstance(n, ast.FunctionDef) and n.name == "hunt_tick"
                   for n in ast.walk(new_run))  # fmt: skip
    got, order, bad = (inline_steps(new_run, drive_ok=drive_ok) if outlined
                       else (copy.deepcopy(new_run), [], []))  # fmt: skip
    _strip_docstrings(want)
    _strip_docstrings(got)
    normalize_loop(want)
    normalize_loop(got)
    cls = [n for n in new_tree.body if isinstance(n, ast.ClassDef) and n.name == "HuntState"]
    slots: list[str] = []
    if cls:
        for st in cls[0].body:
            if isinstance(st, ast.Assign) and ast.unparse(st.targets[0]) == "__slots__":
                slots = list(ast.literal_eval(st.value))
    missing = sorted((set(lifted) | set(aliased)) - set(slots))
    extra = sorted(set(slots) - set(lifted) - set(aliased))
    sigs = [x for x in new_tree.body if isinstance(x, ast.Assign)
            and ast.unparse(x.targets[0]) in (TICK_DONE, RUN_END)]  # fmt: skip
    print(f"base run(): lines {ri.run.lineno}-{ri.run.end_lineno}, loop {ri.loop.lineno}-"
          f"{ri.loop.end_lineno} ({len(ri.loop.body)} statements)")  # fmt: skip
    print(f"LIFT ({len(lifted)}): {' '.join(lifted)}")
    print(f"ALIAS ({len(aliased)}): {' '.join(aliased)}")
    print(f"OUTLINE ({len(order)} steps): {' '.join(order)}" if outlined
          else "OUTLINE: not applied (this file is LIFT + ALIAS only)")  # fmt: skip
    print(
        f"resolver vs symtable (each table's locals; each lifted Name's binding): "
        f"{'the same' if not cc else '; '.join(cc)}"
    )
    print(f"LIFT/ALIAS preconditions: {'all hold' if not cond else '; '.join(cond)}")
    print(f"OUTLINE conditions: {'all hold' if not bad else '; '.join(bad)}")
    print(f"HuntState.__slots__: missing {missing or 'none'}, extra {extra or 'none'}")
    print(f"signals: {sorted(ast.unparse(x.targets[0]) for x in sigs)}")
    same = dump(want) == dump(got)
    what = "OUTLINE(ALIAS(LIFT(base)))" if outlined else "ALIAS(LIFT(base))"
    print(f"run() == {what}: {'YES' if same else 'NO'}")
    if not same:
        a, b = ast.unparse(want).splitlines(), ast.unparse(got).splitlines()
        import difflib

        for ln in list(difflib.unified_diff(a, b, "expected", "committed", lineterm="", n=2))[:80]:
            print("   ", ln)
    others = _outside_run(base_src, new_src)
    print(f"the module outside run(): {others}")
    ok = same and not cond and not bad and not cc and not missing and not extra and len(sigs) == 2
    return 0 if ok and others.startswith("the same") else 1


def _outside_run(base_src: str, new_src: str) -> str:
    """Every top-level statement but run(), HuntState and the two signals: unchanged?"""

    def top(src: str) -> dict[str, str]:
        out = {}
        for n in ast.parse(src).body:
            key = getattr(n, "name", None) or ast.unparse(n)[:60]
            if (
                key in ("run", "HuntState", *DRIVE_ADDED)
                or (
                    isinstance(n, ast.Assign)
                    and ast.unparse(n.targets[0]) in (*INERT, *DRIVE_ADDED)
                )
                or (isinstance(n, ast.AnnAssign) and ast.unparse(n.target) in DRIVE_ADDED)
            ):
                # (5b-2's additions: `drive` checks them)
                continue
            out[key] = dump(n)
        return out

    a, b = top(base_src), top(new_src)
    diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return "the same" if not diff else f"DIFFERS: {diff}"


def git_show(rev: str, path: Path) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path.relative_to(ROOT)}"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("base")
    d.add_argument("out")
    d.add_argument("--steps", action="store_true", help="OUTLINE only (BASE is already lifted)")
    d.add_argument("--names", action="store_true", help="print the lifted names and stop")
    c = sub.add_parser("check")
    c.add_argument("--base", default=BASE_REV)
    c.add_argument("--file", default=str(TARGET))
    dv = sub.add_parser("drive", help="5b-2: with no drive, run() is 5b-1's (section 14)")
    dv.add_argument("--base", default=DRIVE_BASE)
    dv.add_argument("--file", default=str(TARGET))
    fl = sub.add_parser("flag", help="18.11: with fly_first_hp's branches as else, FLAG_BASE")
    fl.add_argument("--base", default=FLAG_BASE)
    fl.add_argument("--file", default=str(TARGET))
    pk = sub.add_parser("pick", help="18.15: with the model-pick branches as else, PICK_BASE")
    pk.add_argument("--base", default=PICK_BASE)
    pk.add_argument("--file", default=str(TARGET))
    a = ap.parse_args(argv)
    if a.cmd == "drive":
        return drive_check(git_show(a.base, TARGET), Path(a.file).read_text())
    if a.cmd == "flag":
        return flag_check(git_show(a.base, TARGET), Path(a.file).read_text())
    if a.cmd == "pick":
        return pick_check(git_show(a.base, TARGET), Path(a.file).read_text())
    if a.cmd == "derive":
        src = Path(a.base).read_text()
        if a.steps:
            Path(a.out).write_text(derive_outline(src))
            return 0
        ri = parse_run(src)
        lifted = lifted_names(ri)
        if a.names:
            print(" ".join(lifted))
            return 0
        bad = (
            conditions(ri, lifted, ALIASED)
            + cross_check(src, ri.sb)
            + symtable_renames(src, ri.sb, lifted)
        )
        if bad:
            print("refused:", "; ".join(bad))
            return 1
        Path(a.out).write_text(derive_lift(src, lifted, ALIASED))
        return 0
    return check(git_show(a.base, TARGET), Path(a.file).read_text(), drive_ok=True)


if __name__ == "__main__":
    sys.exit(main())
