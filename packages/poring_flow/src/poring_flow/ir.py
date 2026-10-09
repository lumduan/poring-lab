"""The flow IR: ONE typed, versioned Pydantic model (ADR-0020 sections 1, 2 and 13).

Everything else is a view of it: blocks (the editor, later), restricted Python (`pyview`), JSON
(`to_json` / `from_json` here). The linter checks only this, and the executor runs only this.

- `extra="forbid"`, frozen, the style of `poring_skills/schema.py`.
- Text is never stored: keys and ids only (ADR-0012). The views show text from the active locale
  pack and the local L3 data.
- Canonical JSON (sorted keys, no insignificant whitespace, UTF-8, NFC) and `flow_hash` = sha256 of
  it. Node ids are structural paths computed here (`node_paths`), never stored.
- Map blocks are in IR 1 (Batt, 2026-10-08, open question 16): a flow has EXACTLY ONE of `main`
  (a plain flow, the course's first steps) and `workflow` (map blocks joined by typed exits).
- The effective event set of a map block is DERIVED (`poring_flow.effective`), never stored, so the
  hash covers it.

Deviations from the ADR's illustrative sketch (each one reported, none decided silently):
- `Do` (an action used as an expression: `if choose_menu(X) != OK:`, section 2.2 / 7.2) and
  `OutcomeLit` (`OK`, `FAILED`, ...) are explicit expression kinds;
- `ListE`: a list holding variables (`all_except=[WING, POTION]`); an all-constant list is a `Lit`;
- `Range`: `for i in range(...)` (7.2) needs an iterable that is not a literal list;
- `Cmp` also takes `in` / `not in` against a literal list (13.6.8's example uses `in`; 7.2 refuses
  `In`, an inconsistency of the ADR);
- `Exit.item` takes a variable as well as an item reference (13.6.8 passes `WING`);
- `Override`, `Extend` and `Add` carry an optional `label`: the Python view's function name
  (`farm_hp_low`), which is also the event's node path;
- `until` and `rearm` are exclusive (13.6.7: `until` for repeating events, `rearm` for one-shot).

IR VERSIONS (section 1: "a breaking change is a new version with a converter, never a silent
edit"):
- IR 2 (Batt 2026-10-09, contradictions #13): `Handler.rank`, an explicit rank INSIDE an event
  class. `None` means 13.6.3's table order (`DEFAULT_RANK`: unintended_engagement 4 before hp_low
  5, ...; any other key `USER_RANK`). Equal classes still never pre-empt each other: the rank
  orders their queue, and only events of equal rank queue first in, first out.
- IR 2 also carries `Flow.where_budget` (Batt 2026-10-09, contradictions #10; added before IR 2
  was released): the per-run budget of ACTIVE position reads (/where), default 12.
- IR 1 is CONVERTED on load (`upgrade`): every handler gets `rank: None`, the flow gets the
  default `where_budget`, nothing else changes. Its
  meaning changes (equal-class events were FIFO only), so the converted flow is IR 2 and its hash
  is a new one (no flow was approved under IR 1: MW2 runs nothing). Any other version is refused
  with a message naming the versions this engine reads.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from poring_skills.schema import CONCEPT_ID

CFG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NAME = r"^[A-Za-z][A-Za-z0-9_]{0,47}$"  # ASCII only (7.2: identifier normalisation)
FLOW_NAME = r"^[a-z][a-z0-9_]{0,47}$"
MAP_ID = r"^[A-Za-z0-9_@.\-]{1,40}$"
KEY = r"^[A-Za-z0-9_.\-]{1,64}$"  # an L3 / L4 key
IR_VERSION = 2  # IR 1 converts on load (`upgrade`); see the module docstring
# A SANITY CAP on hostile input, not the policy (Batt 2026-10-09, contradictions #17: NOT
# hard-coded). The policy is CONFIGURED: a global default (4 h) and maximum (24 h) on the Settings
# page, given to the linter and the run-start check as `runtime_max_s`. Was 86_400 (24 h), the
# provisional bound of open question 8.
MAX_RUNTIME_S = 604_800  # 7 days
# The per-run /where budget (Batt 2026-10-09, contradictions #10): how many ACTIVE position reads
# (position(), current_map(), read_position, a relocation's read) a run may make. They TYPE /where,
# which players almost never do; passive sources come first. 12 = about three an hour over the
# default 4 h run (proposed by Claude; each flow may set its own).
WHERE_BUDGET_DEFAULT = 12
WHERE_BUDGET_MAX = 1000
MAX_STR = 200
MAX_LIST = 100
MAX_JSON_BYTES = 1 << 20  # imported JSON is hostile input (7.1)
MAX_JSON_DEPTH = 256
# Fixed in code, never user-editable (13.6.1; hp_critical added by Batt, 2026-10-08, Q29).
SAFETY_CRITICAL = ("dead", "hp_critical", "unexpected_map")  # in their critical order (13.6.3)
CLASSES = ("critical", "survival", "upkeep")  # highest first; the built-in guards sit above
# The rank INSIDE a class (Batt 2026-10-09, contradictions #13): 13.6.3's table order by default;
# a lower rank runs first. The safety-critical three always lead their class in this order (13.6.2
# step 3) and their rank is fixed; any other key defaults to USER_RANK, after the table's events.
DEFAULT_RANK = {
    "dead": 1,
    "hp_critical": 2,
    "unexpected_map": 3,
    "unintended_engagement": 4,
    "hp_low": 5,
    "weight": 6,
}
USER_RANK = 50
MAX_RANK = 99
OUTCOMES = ("ok", "failed", "unsupported", "interrupted", "refused")

Int = Annotated[int, Field(ge=-1_000_000_000, le=1_000_000_000)]
Str = Annotated[str, Field(max_length=MAX_STR)]
Coord = Annotated[int, Field(ge=0, le=2047)]


# --- typed references: keys and ids, never display text (ADR-0012) ------------------------------
class MapRef(BaseModel):
    model_config = CFG
    kind: Literal["map"] = "map"
    map: str = Field(pattern=MAP_ID)


class CellRef(BaseModel):
    model_config = CFG
    kind: Literal["cell"] = "cell"
    map: str = Field(pattern=MAP_ID)
    x: Coord
    y: Coord


class NpcRef(BaseModel):
    model_config = CFG
    kind: Literal["npc"] = "npc"
    key: str = Field(pattern=KEY)  # an L3 key


class OptionRef(BaseModel):
    model_config = CFG
    kind: Literal["option"] = "option"
    key: str = Field(pattern=KEY)  # an L3 / L4 key


class ItemRef(BaseModel):
    model_config = CFG
    kind: Literal["item"] = "item"
    id: int = Field(ge=1, le=10_000_000)


class MobRef(BaseModel):
    model_config = CFG
    kind: Literal["mob"] = "mob"
    id: int = Field(ge=1, le=10_000_000)


class SkillRef(BaseModel):
    model_config = CFG
    kind: Literal["skill"] = "skill"
    id: int = Field(ge=1, le=100_000)
    level: int | None = Field(default=None, ge=1, le=20)


class WindowRef(BaseModel):
    model_config = CFG
    kind: Literal["window"] = "window"
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")  # an ADR-0011 anchor name


Ref = Annotated[
    MapRef | CellRef | NpcRef | OptionRef | ItemRef | MobRef | SkillRef | WindowRef,
    Field(discriminator="kind"),
]
REF_TYPES = (MapRef, CellRef, NpcRef, OptionRef, ItemRef, MobRef, SkillRef, WindowRef)


# --- expressions --------------------------------------------------------------------------------
class Lit(BaseModel):
    model_config = CFG
    kind: Literal["lit"] = "lit"
    value: bool | Int | float | Str | Ref | Annotated[list[Ref], Field(max_length=MAX_LIST)]


class Var(BaseModel):
    model_config = CFG
    kind: Literal["var"] = "var"
    name: str = Field(pattern=NAME)


class OutcomeLit(BaseModel):  # OK, FAILED, ... (2.2)
    model_config = CFG
    kind: Literal["outcome"] = "outcome"
    value: Literal["ok", "failed", "unsupported", "interrupted", "refused"]


class ListE(BaseModel):  # a list holding variables; an all-constant list is a Lit
    model_config = CFG
    kind: Literal["list"] = "list"
    items: list[Expr] = Field(min_length=1, max_length=MAX_LIST)

    @model_validator(mode="after")
    def _not_all_constant(self) -> ListE:
        if all(isinstance(i, Lit) for i in self.items):
            raise ValueError("a list of constants is a lit, not a list expression")
        return self


class Logic(BaseModel):
    model_config = CFG
    kind: Literal["and", "or"]
    terms: list[Expr] = Field(min_length=2, max_length=MAX_LIST)


class Not_(BaseModel):  # noqa: N801 -- the sketch's name
    model_config = CFG
    kind: Literal["not"] = "not"
    term: Expr


class Sense(BaseModel):
    model_config = CFG
    kind: Literal["sense"] = "sense"
    sensor: str = Field(pattern=NAME)  # a catalogue sensor, e.g. hp_percent
    args: dict[Annotated[str, Field(pattern=NAME)], Expr] = {}


class Cmp(BaseModel):
    model_config = CFG
    kind: Literal["cmp"] = "cmp"
    op: Literal["==", "!=", "<", "<=", ">", ">=", "in", "not in"]
    left: Expr
    right: Expr


class Arith(BaseModel):
    model_config = CFG
    kind: Literal["arith"] = "arith"
    op: Literal["+", "-", "*", "//", "%"]
    left: Expr
    right: Expr


class Do(BaseModel):  # an action block used as an expression: its outcome (2.2)
    model_config = CFG
    kind: Literal["do"] = "do"
    action: ActionStmt


Expr = Annotated[
    Lit | Var | OutcomeLit | ListE | Sense | Cmp | Logic | Not_ | Arith | Do,
    Field(discriminator="kind"),
]


class Range(BaseModel):  # `for i in range(start, stop, step)` (7.2)
    model_config = CFG
    kind: Literal["range"] = "range"
    start: Expr
    stop: Expr
    step: Expr


# --- statements ---------------------------------------------------------------------------------
class ActionStmt(BaseModel):
    model_config = CFG
    kind: Literal["action"] = "action"
    block: str = Field(pattern=NAME)  # catalogue name, e.g. walk_to
    concept: str = Field(pattern=CONCEPT_ID)  # its L1 concept (core.* for core blocks)
    params: dict[Annotated[str, Field(pattern=NAME)], Expr] = {}
    timeout_s: float = Field(gt=0, le=600)
    on_fail: Literal["stop", "continue"] = "stop"
    outcome_to: str | None = Field(default=None, pattern=NAME)  # a variable receiving the outcome
    note: str | None = Field(default=None, max_length=MAX_STR)


class If(BaseModel):
    model_config = CFG
    kind: Literal["if"] = "if"
    cond: Expr
    then: list[Stmt] = []
    orelse: list[Stmt] = []


class While(BaseModel):
    model_config = CFG
    kind: Literal["while"] = "while"
    cond: Expr
    body: list[Stmt] = []
    max_iter: int | None = Field(default=None, ge=1, le=100_000)
    max_s: float | None = Field(default=None, gt=0, le=MAX_RUNTIME_S)


class WaitUntil(BaseModel):
    model_config = CFG
    kind: Literal["wait_until"] = "wait_until"
    cond: Expr
    timeout_s: float = Field(gt=0, le=3600)  # mandatory
    outcome_to: str | None = Field(default=None, pattern=NAME)


class Repeat(BaseModel):
    model_config = CFG
    kind: Literal["repeat"] = "repeat"
    times: Expr
    body: list[Stmt] = []


class ForEach(BaseModel):
    model_config = CFG
    kind: Literal["for"] = "for"
    var: str = Field(pattern=NAME)
    items: Annotated[Lit | Var | Range, Field(discriminator="kind")]
    body: list[Stmt] = []


class SetVar(BaseModel):
    model_config = CFG
    kind: Literal["set"] = "set"
    var: str = Field(pattern=NAME)
    value: Expr


class CallProc(BaseModel):
    model_config = CFG
    kind: Literal["call"] = "call"
    proc: str = Field(pattern=NAME)


class Stop(BaseModel):
    model_config = CFG
    kind: Literal["stop"] = "stop"
    reason: str = Field(pattern=r"^[a-z_]{1,40}$")


class Break_(BaseModel):  # noqa: N801
    model_config = CFG
    kind: Literal["break"] = "break"


class Continue_(BaseModel):  # noqa: N801
    model_config = CFG
    kind: Literal["continue"] = "continue"


# --- exits and entries (13.1) --------------------------------------------------------------------
class Exit(BaseModel):
    model_config = CFG
    kind: Literal["walk_exit", "npc_warp", "item_warp", "death_respawn"]
    warp: CellRef | None = None  # walk_exit: a cell of an L3 warp on this map
    npc: NpcRef | None = None  # npc_warp: an NPC on this map (L3)
    options: list[OptionRef] = Field(default=[], max_length=10)  # the menu path, by key
    item: Annotated[ItemRef | Var, Field(discriminator="kind")] | None = None  # item_warp
    to_block: str = Field(pattern=NAME)
    to_entry: str = Field(pattern=NAME)
    timeout_s: float = Field(default=120, gt=0, le=600)

    @model_validator(mode="after")
    def _shape(self) -> Exit:
        if self.kind == "death_respawn":
            raise ValueError("death_respawn is derived from the dead event, never authored")
        given = {
            "warp": self.warp is not None,
            "npc": self.npc is not None,
            "options": bool(self.options),
            "item": self.item is not None,
        }
        need = {"walk_exit": {"warp"}, "npc_warp": {"npc", "options"}, "item_warp": {"item"}}
        wanted = need[self.kind]
        missing = sorted(k for k in wanted if not given[k])
        extra = sorted(k for k, v in given.items() if v and k not in wanted)
        if missing or extra:
            raise ValueError(
                f"{self.kind} takes {', '.join(sorted(wanted))} (missing "
                f"{missing or 'none'}, not allowed {extra or 'none'})"
            )
        return self


class TakeExit(BaseModel):  # a statement: leaves the map block
    model_config = CFG
    kind: Literal["take_exit"] = "take_exit"
    exit: Exit


Stmt = Annotated[
    ActionStmt
    | If
    | While
    | WaitUntil
    | Repeat
    | ForEach
    | SetVar
    | CallProc
    | Stop
    | Break_
    | Continue_
    | TakeExit,
    Field(discriminator="kind"),
]


class Entry(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)
    at: CellRef | None = None  # an L3 arrival cell; None = anywhere (a relocation target)
    radius: int = Field(default=2, ge=0, le=15)


# --- events (2.5, extended by 13.6) ---------------------------------------------------------------
class Handler(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)  # the event KEY across scopes, e.g. hp_low
    when: Expr  # START: passive sensors only (linter)
    until: Expr | None = None  # STOP: the body repeats until it holds (the hysteresis pair)
    rearm: Expr | None = None  # one-shot events (2.5)
    priority: Literal["critical", "survival", "upkeep"]
    # IR 2: the rank inside the class (lower first); None = 13.6.3's table order (`rank_of`)
    rank: int | None = Field(default=None, ge=1, le=MAX_RANK)
    mode: Literal["insert", "preempt"] = "preempt"
    escalate: str | None = Field(default=None, pattern=NAME)  # insert: a procedure, as a pre-empt
    max_insert_fails: int = Field(default=3, ge=1, le=10)
    cooldown_s: float = Field(default=0, ge=0, le=3600)
    max_per_min: int | None = Field(default=None, ge=1, le=60)
    max_fires_per_10min: int = Field(default=10, ge=1, le=100)
    max_per_run: int | None = Field(default=None, ge=1, le=100)
    then: Literal["resume", "skip_block", "restart_flow", "relocate", "stop"] = "resume"
    body: list[Stmt] = Field(min_length=1)

    @model_validator(mode="after")
    def _shape(self) -> Handler:
        if self.until is not None and self.rearm is not None:
            raise ValueError("until (a repeating event) and rearm (a one-shot event) are exclusive")
        if self.escalate is not None and self.mode != "insert":
            raise ValueError("escalate belongs to an insert event")
        return self


def rank_of(h: Handler) -> int:
    """A handler's rank inside its class: its own, else 13.6.3's table order (#13)."""
    return h.rank if h.rank is not None else DEFAULT_RANK.get(h.name, USER_RANK)


def place_in_class(h: Handler) -> tuple[int, int]:
    """Where an event sits INSIDE its class, the one definition the effective order, the
    executor's queue and the ties rule share: the safety-critical three lead `critical` in their
    fixed order (13.6.2 step 3), then the rank (#13). Equal places keep their arrival order."""
    lead = len(SAFETY_CRITICAL)
    if h.priority == "critical" and h.name in SAFETY_CRITICAL:
        lead = SAFETY_CRITICAL.index(h.name)
    return lead, rank_of(h)


class Override(BaseModel):  # map scope: replaces the global event of the same key
    model_config = CFG
    kind: Literal["override"] = "override"
    event: Handler
    label: str | None = Field(default=None, pattern=NAME)


class Extend(BaseModel):  # map scope: adds steps to the global event of the same key
    model_config = CFG
    kind: Literal["extend"] = "extend"
    key: str = Field(pattern=NAME)
    steps: list[Stmt] = Field(min_length=1)
    max_per_run: int | None = Field(default=None, ge=1, le=100)  # may only tighten
    label: str | None = Field(default=None, pattern=NAME)


class Disable(BaseModel):  # map scope: the global event does not run on this block
    model_config = CFG
    kind: Literal["disable"] = "disable"
    key: str = Field(pattern=NAME)


class Add(BaseModel):  # map scope: a map-only event (its key is not global)
    model_config = CFG
    kind: Literal["add"] = "add"
    event: Handler
    label: str | None = Field(default=None, pattern=NAME)


MapEvent = Annotated[Override | Extend | Disable | Add, Field(discriminator="kind")]


# --- the map block and the workflow (13.1) --------------------------------------------------------
class MapBlock(BaseModel):
    model_config = CFG
    name: str = Field(pattern=NAME)  # one map may hold several blocks (town_out, town_back)
    map: MapRef
    entries: list[Entry] = Field(min_length=1, max_length=20)
    targets: list[MobRef] = Field(default=[], max_length=MAX_LIST)  # attack only these (13.3)
    ignore: list[MobRef] = Field(default=[], max_length=MAX_LIST)  # never attack these
    events: list[MapEvent] = Field(default=[], max_length=50)  # 13.6
    main: list[Stmt] = Field(min_length=1)  # every path ends in take_exit or stop
    resume_here: bool = True  # the relocation target for its map (13.6.6)

    @model_validator(mode="before")
    @classmethod
    def _labels(cls, data: Any) -> Any:
        """Fill every map event's label (its node path and Python function name) by default:
        <block>_<key> for an override or an extension, the key for an added event. So a label is
        always stored and the views round-trip exactly."""
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            return data
        events = []
        for ev in data["events"]:
            kind = ev.get("kind") if isinstance(ev, dict) else None
            if kind in ("override", "extend", "add") and ev.get("label") is None:
                inner = ev.get("event")
                key = (
                    ev.get("key")
                    if kind == "extend"
                    else (inner.get("name") if isinstance(inner, dict) else None)
                )
                if isinstance(key, str):
                    label = key if kind == "add" else f"{data.get('name')}_{key}"
                    ev = {**ev, "label": label}
            events.append(ev)
        return {**data, "events": events}


class Workflow(BaseModel):
    model_config = CFG
    start_block: str = Field(pattern=NAME)
    start_entry: str = Field(pattern=NAME)
    blocks: list[MapBlock] = Field(min_length=1, max_length=100)
    run_until_stopped: bool = False  # an explicit choice for an unbounded loop (13.5)


# --- the flow -----------------------------------------------------------------------------------
class Target(BaseModel):
    model_config = CFG
    client: str = Field(pattern=KEY)  # the L2 build, e.g. kro-20211103-prere
    server: str = Field(pattern=KEY)  # the environment id, e.g. lab-rathena
    locale: str = Field(pattern=KEY)  # the L4 pack, e.g. en
    path: Literal["s2", "rdp"] = "s2"  # ADR-0014: S2 is the bot's primary path


class Flow(BaseModel):
    model_config = CFG
    ir: Literal[2]  # IR 1 converts on load (`upgrade`)
    name: str = Field(pattern=FLOW_NAME)
    description: str = Field(default="", max_length=500)
    target: Target
    assumes: list[Expr] = Field(default=[], max_length=50)  # character facts, sensed before input
    max_runtime_s: int = Field(ge=1, le=MAX_RUNTIME_S)
    # #10: the run's /where budget (lint warns above it; the run report counts every read)
    where_budget: int = Field(default=WHERE_BUDGET_DEFAULT, ge=0, le=WHERE_BUDGET_MAX)
    stop_when: Expr | None = None
    variables: dict[Annotated[str, Field(pattern=NAME)], Lit] = {}
    procedures: dict[Annotated[str, Field(pattern=NAME)], list[Stmt]] = {}
    handlers: list[Handler] = Field(default=[], max_length=50)  # the GLOBAL events
    main: list[Stmt] | None = None
    workflow: Workflow | None = None

    @model_validator(mode="after")
    def _one_body(self) -> Flow:
        if (self.main is None) == (self.workflow is None):
            raise ValueError("a flow has exactly one of main and workflow")
        if self.main is not None and not self.main:
            raise ValueError("main needs at least one statement")
        return self


for _model in (
    Lit,
    ListE,
    Logic,
    Not_,
    Sense,
    Cmp,
    Arith,
    Do,
    Range,
    ActionStmt,
    If,
    While,
    WaitUntil,
    Repeat,
    ForEach,
    SetVar,
    TakeExit,
    Exit,
    Handler,
    Override,
    Extend,
    Add,
    MapBlock,
    Workflow,
    Flow,
):
    _model.model_rebuild()

StmtT = (
    ActionStmt
    | If
    | While
    | WaitUntil
    | Repeat
    | ForEach
    | SetVar
    | CallProc
    | Stop
    | Break_
    | Continue_
    | TakeExit
)
ExprT = Lit | Var | OutcomeLit | ListE | Sense | Cmp | Logic | Not_ | Arith | Do
MapEventT = Override | Extend | Disable | Add


# --- labels and node paths ----------------------------------------------------------------------
def event_label(ev: MapEventT, block: MapBlock) -> str:
    """A map event's node path: its Python view function name (13.6.9's messages use it)."""
    if isinstance(ev, Disable):
        return block.name
    if isinstance(ev, Extend):
        return ev.label or f"{block.name}_{ev.key}"
    if isinstance(ev, Override):
        return ev.label or f"{block.name}_{ev.event.name}"
    return ev.label or ev.event.name


def event_key(ev: MapEventT) -> str:
    return ev.key if isinstance(ev, Extend | Disable) else ev.event.name


@dataclass(frozen=True)
class Site:
    """One statement with its structural path and context."""

    path: str
    stmt: StmtT
    root: str  # main, a procedure, a handler / map event label, or a map block name
    scope: Literal["main", "procedure", "handler", "block", "map_event", "extension"]
    block: MapBlock | None  # the map block a block statement or a map event belongs to
    loops: int  # enclosing loops
    depth: int  # statement nesting depth (1 = top level)


def child_bodies(stmt: StmtT) -> list[tuple[str, list[Any], bool]]:
    """(field, statements, is_loop_body) for every nested body of a statement."""
    if isinstance(stmt, If):
        return [("then", stmt.then, False), ("orelse", stmt.orelse, False)]
    if isinstance(stmt, While | Repeat | ForEach):
        return [("body", stmt.body, True)]
    return []


def walk(
    stmts: list[Any],
    prefix: str,
    *,
    root: str,
    scope: Any,
    block: MapBlock | None,
    loops: int = 0,
    depth: int = 1,
) -> Iterator[Site]:
    for i, stmt in enumerate(stmts):
        path = f"{prefix}.{i}"
        yield Site(path, stmt, root, scope, block, loops, depth)
        for field, body, is_loop in child_bodies(stmt):
            yield from walk(
                body,
                f"{path}.{field}",
                root=root,
                scope=scope,
                block=block,
                loops=loops + is_loop,
                depth=depth + 1,
            )


def handler_bodies(flow: Flow) -> Iterator[tuple[str, Handler, MapBlock | None, MapEventT | None]]:
    """(label, handler, block, map event) for every global handler and every map handler."""
    for h in flow.handlers:
        yield h.name, h, None, None
    for b in flow.workflow.blocks if flow.workflow else []:
        for ev in b.events:
            if isinstance(ev, Override | Add):
                yield event_label(ev, b), ev.event, b, ev


def sites(flow: Flow) -> Iterator[Site]:
    """Every statement of the flow, in a fixed order, with its node path."""
    if flow.main is not None:
        yield from walk(flow.main, "main", root="main", scope="main", block=None)
    for name, body in flow.procedures.items():
        yield from walk(body, name, root=name, scope="procedure", block=None)
    for label, h, block, _ in handler_bodies(flow):
        scope = "handler" if block is None else "map_event"
        yield from walk(h.body, label, root=label, scope=scope, block=block)
    for b in flow.workflow.blocks if flow.workflow else []:
        yield from walk(b.main, b.name, root=b.name, scope="block", block=b)
        for ev in b.events:
            if isinstance(ev, Extend):
                lab = event_label(ev, b)
                yield from walk(ev.steps, lab, root=lab, scope="extension", block=b)


def sub_exprs(expr: ExprT) -> Iterator[ExprT]:
    """The expression and every expression inside it (into a `do` action's parameters too)."""
    yield expr
    if isinstance(expr, ListE | Logic):
        children: list[Any] = list(expr.items if isinstance(expr, ListE) else expr.terms)
    elif isinstance(expr, Not_):
        children = [expr.term]
    elif isinstance(expr, Sense):
        children = list(expr.args.values())
    elif isinstance(expr, Cmp | Arith):
        children = [expr.left, expr.right]
    elif isinstance(expr, Do):
        children = list(expr.action.params.values())
    else:
        children = []
    for c in children:
        yield from sub_exprs(c)


def stmt_exprs(stmt: StmtT) -> list[tuple[str, ExprT]]:
    """(field, expression) for the expressions a statement holds directly."""
    if isinstance(stmt, ActionStmt):
        return [(f"params.{k}", v) for k, v in stmt.params.items()]
    if isinstance(stmt, If | While | WaitUntil):
        return [("cond", stmt.cond)]
    if isinstance(stmt, Repeat):
        return [("times", stmt.times)]
    if isinstance(stmt, SetVar):
        return [("value", stmt.value)]
    if isinstance(stmt, ForEach):
        if isinstance(stmt.items, Range):
            return [
                ("items.start", stmt.items.start),
                ("items.stop", stmt.items.stop),
                ("items.step", stmt.items.step),
            ]
        return [("items", stmt.items)]
    if isinstance(stmt, TakeExit) and isinstance(stmt.exit.item, Var):
        return [("exit.item", stmt.exit.item)]
    return []


def actions_in(stmt: StmtT) -> Iterator[ActionStmt]:
    """Every action a statement runs, its `do` expressions included (not nested statements)."""
    if isinstance(stmt, ActionStmt):
        yield stmt
    for _, e in stmt_exprs(stmt):
        for sub in sub_exprs(e):
            if isinstance(sub, Do):
                yield sub.action


def count_nodes(flow: Flow) -> int:
    n = 0
    for site in sites(flow):
        n += 1
        for _, e in stmt_exprs(site.stmt):
            n += sum(1 for _ in sub_exprs(e))
    for _, h, _, _ in handler_bodies(flow):
        exprs: list[ExprT | None] = [h.when, h.until, h.rearm]
        for x in exprs:
            if x is not None:
                n += sum(1 for _ in sub_exprs(x))
    return n


# --- the node-path grammar a person reads (Batt 2026-10-09, ADR-0020 contradictions #3) ----------
class PathNames:
    """ONE grammar for the node paths printed in every message (lint findings, schema errors):
    named nodes by name, statements by index.

        main.4                               the plain main flow
        procedures.<name>.2                  a procedure
        handlers.<key>  / handlers.<key>.1   a global event (written, or the always-on built-in)
        maps.<block> / maps.<block>.3        a map block (by its NAME: two blocks may share a map)
        maps.<block>.events.<key>.0          a map event (override, add, extend) of that block
        variables.<NAME>                     a flow variable
        global                               the global pairs (the ties rule)

    It prints the structural node ids (`sites()`: `town.3`, `drink.0`, `farm_hp_low.0`), which
    stay the editor's and the trace's keys; only what a person reads changes ("messages only")."""

    def __init__(self, flow: Flow) -> None:
        roots: dict[str, str] = {"main": "main", "global": "global"}
        for name in flow.variables:
            roots[name] = f"variables.{name}"
        for name in flow.procedures:
            roots[name] = f"procedures.{name}"
        for k in SAFETY_CRITICAL:  # always on (always_on.py): global even when not written
            roots[k] = f"handlers.{k}"
        for h in flow.handlers:
            roots[h.name] = f"handlers.{h.name}"
        for b in flow.workflow.blocks if flow.workflow else []:
            roots[b.name] = f"maps.{b.name}"
            for ev in b.events:
                if not isinstance(ev, Disable):
                    roots[event_label(ev, b)] = f"maps.{b.name}.events.{event_key(ev)}"
        self.roots = roots

    def __call__(self, path: str) -> str:
        root, sep, rest = path.partition(".")
        pre = self.roots.get(root)
        return pre + sep + rest if pre is not None else path


# --- canonical JSON and the hash ------------------------------------------------------------------
class FlowError(ValueError):
    """An IR that does not validate: one `path: message` line per problem."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages


def _nfc(obj: Any) -> Any:
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [_nfc(v) for v in obj]
    if isinstance(obj, dict):
        return {_nfc(k): _nfc(v) for k, v in obj.items()}
    return obj


def canonical_json(flow: Flow) -> str:
    """Sorted keys, no insignificant whitespace, UTF-8 (not ASCII-escaped), NFC strings."""
    data = _nfc(flow.model_dump(mode="json"))
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def flow_hash(flow: Flow) -> str:
    return hashlib.sha256(canonical_json(flow).encode("utf-8")).hexdigest()


def to_json(flow: Flow) -> str:
    return canonical_json(flow)


def _depth(text: str) -> int:
    """The bracket depth of a JSON text, outside strings (a linear pre-check)."""
    depth = deepest = 0
    in_str = esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif ch in "]}":
            depth -= 1
    return deepest


def from_json(raw: str | bytes) -> Flow:
    """Imported JSON is hostile input: size-capped, depth-checked, schema-validated."""
    size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
    if size > MAX_JSON_BYTES:
        raise FlowError([f"flow: {size} bytes; at most {MAX_JSON_BYTES}"])
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if _depth(text) > MAX_JSON_DEPTH:
        raise FlowError([f"flow: nested deeper than {MAX_JSON_DEPTH}"])
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as e:
        raise FlowError([f"flow: not JSON ({type(e).__name__})"]) from None
    return validate(_nfc(data))


def upgrade(data: Any) -> Any:
    """The IR 1 -> IR 2 converter (section 1; #13): only the version changes, and every handler's
    rank is left out, which IR 2 reads as 13.6.3's table order (`rank: None`). Another version is
    refused with a message; a non-dict is left to the schema."""
    if not isinstance(data, dict) or "ir" not in data:
        return data
    v = data["ir"]
    if v == IR_VERSION and not isinstance(v, bool):
        return data
    if v == 1 and not isinstance(v, bool):
        return {**data, "ir": IR_VERSION}
    shown = json.dumps(v)[:20] if isinstance(v, str | int | float | bool) or v is None else "?"
    raise FlowError(
        [
            f"flow: ir: IR version {shown} is not supported: this engine reads IR "
            f"{IR_VERSION} (and converts IR 1)"
        ]
    )


def validate(data: Any) -> Flow:
    data = upgrade(data)
    try:
        return Flow.model_validate(data)
    except ValidationError as e:
        raise FlowError([_message(data, err) for err in e.errors()]) from None


_BODIES = ("then", "orelse", "body", "steps")


def _message(data: Any, err: Any) -> str:
    """A pydantic error as `node path: field: message`, discriminator tags dropped.

    Paths follow the printed grammar (`PathNames`, #3): main.<i>, procedures.<name>.<i>,
    handlers.<name>.<i>, maps.<block>.<i>, nested then / orelse / body.
    """
    loc = list(err["loc"])
    node: Any = data
    path: list[str] = []
    fields: list[str] = []
    i = 0

    def skip_tag(j: int) -> int:
        if isinstance(node, dict) and j + 1 < len(loc) and loc[j + 1] == node.get("kind"):
            return j + 1
        return j

    while i < len(loc):
        part = loc[i]
        nxt = loc[i + 1] if i + 1 < len(loc) else None
        if fields:
            fields.append(str(part))
        elif isinstance(node, list) and isinstance(part, int):
            node = node[part] if part < len(node) else None
            path.append(str(part))
            i = skip_tag(i)
        elif isinstance(node, dict) and isinstance(part, str):
            child = node.get(part)
            top = not path
            if top and part == "main" and isinstance(child, list):
                path.append("main")
            elif top and part == "procedures" and isinstance(child, dict) and nxt in child:
                path.append(f"procedures.{nxt}")  # the printed grammar (#3, PathNames)
                child, i = child[nxt], i + 1
            elif top and part == "handlers" and isinstance(child, list) and isinstance(nxt, int):
                item = child[nxt] if nxt < len(child) else None
                name = item.get("name") if isinstance(item, dict) else None
                path.append(f"handlers.{name}" if name else f"handlers.{nxt}")
                child, i = item, i + 1
            elif top and part == "workflow" and nxt == "blocks" and isinstance(child, dict):
                blocks = child.get("blocks")
                j = loc[i + 2] if i + 2 < len(loc) else None
                if isinstance(blocks, list) and isinstance(j, int) and j < len(blocks):
                    item = blocks[j]
                    name = item.get("name") if isinstance(item, dict) else None
                    path.append(f"maps.{name}" if name else f"maps.{j}")
                    child, i = item, i + 2
                    if loc[i + 1 : i + 2] == ["main"]:
                        child, i = item.get("main") if isinstance(item, dict) else None, i + 1
                else:
                    fields.append(part)
            elif path and part in _BODIES and isinstance(child, list):
                if not (len(path) == 1 and part == "body"):  # a handler's body: <label>.<i>
                    path.append(part)
            else:
                fields.append(part)
            node = child
            i = skip_tag(i)
        else:
            fields.append(str(part))
            node = None
        i += 1
    where = ".".join(path) or "flow"
    what = ".".join(fields)
    msg = str(err["msg"]).removeprefix("Value error, ")
    return f"{where}: {what}: {msg}" if what else f"{where}: {msg}"


# --- the generated JSON Schema (drift-tested, like the wire protocol's) ---------------------------
SCHEMA_PATH = "packages/poring_flow/schema/flow.schema.json"


def json_schema() -> str:
    return json.dumps(Flow.model_json_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    """`poring-flow-schema > packages/poring_flow/schema/flow.schema.json` (test_schema.py)."""
    import sys

    sys.stdout.write(json_schema())


if __name__ == "__main__":
    main()
