"""The PROJECT model, format 3 (Batt 2026-11-13; docs/planning/project-model.md): what /maps and
/flows edit and save. Nodes on /maps (a login, a choose-character, one per map, and Global), each
with tabs (one main + the user's), functions like Python (inputs with defaults, *args, **kwargs,
return values), events as functions with a trigger, and Batt's override rule: on a node, a name is
the node's definition first, then Global's, everywhere on that node (inside Global's functions and
events too: virtual dispatch).

- `Project` (section 2 of the doc, exactly: `extra="forbid"`, frozen, as ir.py), `from_json` with
  ir.py's hostile-input caps, `canonical_json` / `project_hash` as IR 2's (sorted keys, no
  whitespace, NFC; a field absent by default -- a map node's `zones`, an edge's `entry` -- stays
  out). `validate` adds the SHAPE rules the doc states (main tabs, tab names, one namespace per
  node, parameters, events, return, exits, edges, Global, start) as `ProjectError` problems, each
  with its node, tab and path.
- EXECUTION is IR 2's: `compile_project` turns the project into ONE internal IR flow (the
  engine's execution form; nothing user-facing reads it), so every IR 2 rule of the linter, the
  simulators and their safety semantics hold unchanged (event classes, the safety-critical three,
  relocation, the save point, exit placement, functions that press keys, dungeon_hunt, inserts).
  How names compile (section 3's semantics, exactly):
  * the map nodes become map blocks (the node id is the block's name), Global's functions,
    variables and events the flow's procedures, variables and global events;
  * a NODE's own functions and variables become procedures / flow variables of their own (an
    internal name when another node or Global has the same one); its events override Global's of
    the same name (IR 2's Override; a safety-critical one a STRICT override, the "not weakened"
    rule), or are its own (IR 2's Add); a plain function named like a Global event replaces that
    event there (IR 2's Disable: refused for the safety-critical three);
  * VIRTUAL DISPATCH by specialisation: when Global's function or event reaches (through Global's
    calls and variables) a name a node overrides, that node gets its own copy of it whose names
    resolve on the node (Global's event an override on that node, marked `dispatched`). Code runs
    on the node where it was entered (a block changes only through an exit, which ends a main, or
    a relocation, which ends everything), so resolving per node when compiling is the run's own
    resolution;
  * login and character nodes are not compiled: their session blocks are SIMULATED (section 5,
    `simulate`), and Run starts on a map node (section 6);
  * the START (Batt 2026-11-13 ~21:4x, "START > map xmas_dun02, one box is enough; login and
    choosing the character come later"): `start` is a login node (the session path, by edges), or
    a MAP node: the run starts where she stands on it (a person put her there), at its first entry,
    with no session; login and character nodes are then optional and `edges` may be empty.
  Findings and the trace come back in the project's terms: `node`, `tab`, `path`
  "<node>/<tab>/<site>" (`site` IR 2's path inside the tab: "main.2", "heal.0"); an internal name
  in a text reads as the user's.
- `runner_keys(project, node_id)`: the Run button's five keys from that node's functions (the
  home key from dungeon_hunt's optional `home` role first, else the node's item warp by function).

The Python view of a project (one file per tab) is `poring_flow.pyproject`.
"""

from __future__ import annotations

import hashlib
import json
import keyword
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    model_serializer,
    model_validator,
)

from poring_flow import ir

FORMAT = "poring-lab.project"
VERSION = 3
CFG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NODE_ID = ir.NAME
TAB_NAME = r"^[a-z][a-z0-9_]{0,19}$"
MAIN = "main"
GLOBAL = "global"
# The tab the engine's ALWAYS-ON safety events show under (always_on.py: dead, hp_critical,
# unexpected_map, when Global writes none of them): "global/built_in/dead.0". Refused as a tab name.
BUILT_IN_TAB = "built_in"
MAX_NODES = 100
MAX_TABS = 30
MAX_DEFS = 200
MAX_POS = 1_000_000
# Section 5 (credentials by NAME, never a secret): the lab's two accounts as ro_agent knows them
# (.env prefixes RATHENA_GM_* / RATHENA_AGENT_*; scripts/ro_agent.py account(which)).
CREDENTIALS = ("lab_gm", "lab_player")
CREDENTIAL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
LAB_SERVER = "lab-rathena"  # the one server the bot may act on (ADR-0006, ADR-0016)
# The Maps page's session mock (services/frontend/src/lib/maps/session.ts SESSION_S): seconds
SESSION_S = {"start": 1.0, "login": 6.0, "character": 4.0}
MAX_SLOT = 15  # session.ts MAX_SLOT
CHAR_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _]{0,22}$")  # session.ts CHAR_NAME (rAthena's)
LOGIN_BLOCK = "login"
CHARACTER_BLOCK = "choose_character"
SESSION_BLOCKS = (LOGIN_BLOCK, CHARACTER_BLOCK)

# Python's names a tab may not take (section 2: "not a Python keyword or built-in"), FIXED here so
# the browser checks the same list (GET /flows/catalogue tab_name_rule): the keywords and soft
# keywords, and the built-ins of Python 3.12 that a tab name could spell (lowercase).
PY_BUILTINS = (
    "abs", "aiter", "all", "anext", "any", "ascii", "bin", "bool", "breakpoint", "bytearray",
    "bytes", "callable", "chr", "classmethod", "compile", "complex", "copyright", "credits",
    "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec", "exit", "filter", "float",
    "format", "frozenset", "getattr", "globals", "hasattr", "hash", "help", "hex", "id", "input",
    "int", "isinstance", "issubclass", "iter", "len", "license", "list", "locals", "map", "max",
    "memoryview", "min", "next", "object", "oct", "open", "ord", "pow", "print", "property",
    "quit", "range", "repr", "reversed", "round", "set", "setattr", "slice", "sorted",
    "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
)  # fmt: skip
REFUSED_TAB_NAMES = tuple(
    sorted(
        {k for k in (*keyword.kwlist, *keyword.softkwlist) if re.match(TAB_NAME, k)}
        | set(PY_BUILTINS)
        | {GLOBAL, BUILT_IN_TAB}
    )
)


def tab_name_rule() -> dict[str, Any]:
    """The tab-name rule the browser checks too (section 2)."""
    return {
        "pattern": TAB_NAME,
        "main": MAIN,
        "refused": list(REFUSED_TAB_NAMES),
        "also": "not a function's, a variable's or another tab's name of the same node; main "
        "only as the main tab (first; Global has none)",
    }


# --- the models (section 2) ----------------------------------------------------------------------
class Pos(BaseModel):
    model_config = CFG
    x: float = Field(ge=-MAX_POS, le=MAX_POS)
    y: float = Field(ge=-MAX_POS, le=MAX_POS)


class Trigger(BaseModel):
    """An event's trigger: IR 2's Handler but its name and body (the def's)."""

    model_config = CFG
    when: ir.Expr
    until: ir.Expr | None = None
    rearm: ir.Expr | None = None
    priority: Literal["critical", "survival", "upkeep"]
    rank: int | None = Field(default=None, ge=1, le=ir.MAX_RANK)
    mode: Literal["insert", "preempt"] = "preempt"
    escalate: str | None = Field(default=None, pattern=ir.NAME)
    max_insert_fails: int = Field(default=3, ge=1, le=10)
    cooldown_s: float = Field(default=0, ge=0, le=3600)
    max_per_min: int | None = Field(default=None, ge=1, le=60)
    max_fires_per_10min: int = Field(default=10, ge=1, le=100)
    max_per_run: int | None = Field(default=None, ge=1, le=100)
    then: Literal["resume", "skip_block", "restart_flow", "relocate", "stop"] = "resume"

    @model_validator(mode="after")
    def _shape(self) -> Trigger:
        if self.until is not None and self.rearm is not None:
            raise ValueError("until (a repeating event) and rearm (a one-shot event) are exclusive")
        if self.escalate is not None and self.mode != "insert":
            raise ValueError("escalate belongs to an insert event")
        return self


class Def(BaseModel):
    """A function (`on` None) or an EVENT (a trigger: no inputs; its name is its event key)."""

    model_config = CFG
    name: str = Field(pattern=ir.NAME)
    params: list[ir.Param] = Field(default=[], max_length=ir.MAX_ARGS)
    varargs: str | None = Field(default=None, pattern=ir.NAME)
    kwargs: str | None = Field(default=None, pattern=ir.NAME)
    body: list[ir.Stmt] = Field(min_length=1)
    on: Trigger | None = None

    @model_validator(mode="after")
    def _shape(self) -> Def:
        ir.check_params(self.params, self.varargs, self.kwargs)
        if self.on is not None and (self.params or self.varargs or self.kwargs):
            raise ValueError(
                f"{self.name} is an event (it has a trigger): an event takes no inputs, no "
                "*args and no **kwargs"
            )
        return self

    def inputs(self) -> list[str]:
        return [p.name for p in self.params] + [n for n in (self.varargs, self.kwargs) if n]


class Tab(BaseModel):
    model_config = CFG
    name: str = Field(pattern=TAB_NAME)
    main: list[ir.Stmt] | None = None  # the main tab's program; None on every other tab
    defs: list[Def] = Field(default=[], max_length=MAX_DEFS)
    vars: dict[Annotated[str, Field(pattern=ir.NAME)], ir.Lit] = Field(default={}, max_length=200)


class _Node(BaseModel):
    model_config = CFG
    id: str = Field(pattern=NODE_ID)
    pos: Pos
    tabs: list[Tab] = Field(default=[], max_length=MAX_TABS)

    def tab(self, name: str) -> Tab | None:
        return next((t for t in self.tabs if t.name == name), None)

    @property
    def main(self) -> list[Any]:
        t = self.tab(MAIN)
        return list(t.main or []) if t is not None else []


class LoginNode(_Node):
    kind: Literal["login"] = "login"


class CharacterNode(_Node):
    kind: Literal["character"] = "character"


class GlobalNode(_Node):
    kind: Literal["global"] = "global"


class MapNode(_Node):
    kind: Literal["map"] = "map"
    map: ir.MapRef
    entries: list[ir.Entry] = Field(min_length=1, max_length=20)
    targets: list[ir.MobRef] = Field(default=[], max_length=ir.MAX_LIST)
    ignore: list[ir.MobRef] = Field(default=[], max_length=ir.MAX_LIST)
    zones: ir.ZonesRef | None = None  # absent from the JSON when none (section 2)
    resume_here: bool = True

    @model_serializer(mode="wrap")
    def _absent_zones(self, handler: SerializerFunctionWrapHandler) -> Any:
        data = handler(self)
        if self.zones is None and isinstance(data, dict):
            data.pop("zones", None)
        return data


Node = Annotated[LoginNode | CharacterNode | MapNode | GlobalNode, Field(discriminator="kind")]
NodeT = LoginNode | CharacterNode | MapNode | GlobalNode


class Edge(BaseModel):
    """The SESSION path (section 2.4): login -> character -> the start map node (its entry)."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
    from_: str = Field(alias="from", pattern=NODE_ID)
    to: str = Field(pattern=NODE_ID)
    entry: str | None = Field(default=None, pattern=ir.NAME)  # absent from the JSON when none

    @model_serializer(mode="wrap")
    def _absent_entry(self, handler: SerializerFunctionWrapHandler) -> Any:
        data = handler(self)
        if self.entry is None and isinstance(data, dict):
            data.pop("entry", None)
        return data


class Project(BaseModel):
    model_config = CFG
    format: Literal["poring-lab.project"]
    version: Literal[3]
    name: str = Field(pattern=ir.FLOW_NAME)
    description: str = Field(default="", max_length=500)
    target: ir.Target
    max_runtime_s: int = Field(ge=1, le=ir.MAX_RUNTIME_S)
    where_budget: int = Field(default=ir.WHERE_BUDGET_DEFAULT, ge=0, le=ir.WHERE_BUDGET_MAX)
    # `false` (a literal) = run until stopped: IR 2's explicit choice for an unbounded workflow
    # (13.5's `run_until_stopped`); `compile_project` says so
    stop_when: ir.Expr | None = None
    assumes: list[ir.Expr] = Field(default=[], max_length=50)
    # where Simulate and Run start: a login node (the session path), or a map node (she is on it)
    start: str = Field(pattern=NODE_ID)
    nodes: list[Node] = Field(min_length=1, max_length=MAX_NODES)
    edges: list[Edge] = Field(default=[], max_length=MAX_NODES)

    def node(self, node_id: str) -> NodeT | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    @property
    def global_node(self) -> GlobalNode | None:
        return next((n for n in self.nodes if isinstance(n, GlobalNode)), None)

    @property
    def map_nodes(self) -> list[MapNode]:
        return [n for n in self.nodes if isinstance(n, MapNode)]


for _model in (Trigger, Def, Tab, LoginNode, CharacterNode, MapNode, GlobalNode, Project):
    _model.model_rebuild()


# --- where a problem or a finding is (the browser's node / tab / path) ---------------------------
@dataclass(frozen=True)
class Where:
    """`node` "" = the whole project; `tab` "" = the node itself; `site` IR 2's path inside the tab
    ("main.2", "heal.0", "hp_low.0.then.1"), a def's name, or a project field ("edges.1")."""

    node: str = ""
    tab: str = ""
    site: str = ""

    @property
    def path(self) -> str:
        parts = [p for p in (self.node, self.tab, self.site) if p]
        return "/".join(parts)


@dataclass(frozen=True)
class Problem:
    where: Where
    message: str

    @property
    def text(self) -> str:
        return f"{self.where.path}: {self.message}" if self.where.path else self.message

    def doc(self) -> dict[str, str]:
        w = self.where
        return {"node": w.node, "tab": w.tab, "path": w.path, "message": self.message}


class ProjectError(ValueError):
    """A project that does not validate: one problem per line, each with its node and tab."""

    def __init__(self, problems: list[Problem]) -> None:
        self.problems = problems[:100]
        self.messages = [p.text for p in self.problems]
        super().__init__("\n".join(self.messages))


# --- canonical JSON and the hash (as IR 2's) ------------------------------------------------------
def dump(project: Project) -> dict[str, Any]:
    data = project.model_dump(mode="json", by_alias=True, context=ir.PROJECT_JSON)
    return ir._nfc(data)  # type: ignore[no-any-return]


def canonical_json(project: Project) -> str:
    """Sorted keys, no insignificant whitespace, UTF-8 (not ASCII-escaped), NFC strings."""
    return json.dumps(
        dump(project), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def project_hash(project: Project) -> str:
    return hashlib.sha256(canonical_json(project).encode("utf-8")).hexdigest()


def to_json(project: Project) -> str:
    return canonical_json(project)


def from_json(raw: str | bytes) -> Project:
    """Imported JSON is hostile input: size-capped, depth-checked, schema- and shape-validated."""
    size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
    if size > ir.MAX_JSON_BYTES:
        raise ProjectError([Problem(Where(), f"{size} bytes; at most {ir.MAX_JSON_BYTES}")])
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    if ir._depth(text) > ir.MAX_JSON_DEPTH:
        raise ProjectError([Problem(Where(), f"nested deeper than {ir.MAX_JSON_DEPTH}")])
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as e:
        raise ProjectError([Problem(Where(), f"not JSON ({type(e).__name__})")]) from None
    return validate(ir._nfc(data))


def validate(data: Any) -> Project:
    if isinstance(data, dict) and "ir" in data and "format" not in data:
        raise ProjectError(
            [
                Problem(
                    Where(),
                    "the flow format changed: a project (format 3); IR 2 flows are not "
                    "converted (docs/planning/project-model.md section 8)",
                )
            ]  # fmt: skip
        )
    if isinstance(data, dict) and data.get("format") == FORMAT and data.get("version") != VERSION:
        v = data.get("version")
        shown = json.dumps(v)[:20] if isinstance(v, str | int | float | bool) or v is None else "?"
        raise ProjectError(
            [
                Problem(
                    Where(), f"version {shown} is not supported: this engine reads format {VERSION}"
                )
            ]  # fmt: skip
        )
    try:
        project = Project.model_validate(data)
    except ValidationError as e:
        raise ProjectError([_pydantic_problem(data, err) for err in e.errors()]) from None
    problems = shape(project)
    if problems:
        raise ProjectError(problems)
    return project


def _pydantic_problem(data: Any, err: Any) -> Problem:
    """A pydantic error as node / tab / the path inside the tab: field: message."""
    loc = list(err["loc"])
    node_id = tab_name = ""
    site: list[str] = []
    fields: list[str] = []
    cur: Any = data
    i = 0
    while i < len(loc):
        part = loc[i]
        if isinstance(cur, list) and isinstance(part, int) and part < len(cur):
            nxt = cur[part]
        else:
            nxt = cur.get(part) if isinstance(cur, dict) and isinstance(part, str) else None
        if isinstance(cur, dict) and part == cur.get("kind") and not isinstance(part, int):
            i += 1  # a discriminator tag
            continue
        if not node_id and part == "nodes" and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            j = loc[i + 1]
            item = nxt[j] if isinstance(nxt, list) and j < len(nxt) else None
            node_id = str(item.get("id")) if isinstance(item, dict) and item.get("id") else f"#{j}"
            cur, i = item, i + 2
            continue
        if node_id and not tab_name and part == "tabs" and i + 1 < len(loc):
            j = loc[i + 1]
            item = nxt[j] if isinstance(nxt, list) and isinstance(j, int) and j < len(nxt) else None
            tab_name = str(item.get("name")) if isinstance(item, dict) and item.get("name") else (
                f"#{j}")  # fmt: skip
            cur, i = item, i + 2
            continue
        if tab_name and not site and part == "defs" and i + 1 < len(loc):
            j = loc[i + 1]
            item = nxt[j] if isinstance(nxt, list) and isinstance(j, int) and j < len(nxt) else None
            site.append(str(item.get("name")) if isinstance(item, dict) else f"#{j}")
            cur, i = item, i + 2
            if loc[i : i + 1] == ["body"]:
                cur, i = cur.get("body") if isinstance(cur, dict) else None, i + 1
            continue
        if tab_name and not site and part == "main":
            site.append("main")
            cur, i = nxt, i + 1
            continue
        if site and not fields and (isinstance(part, int) or part in ("then", "orelse", "body")):
            site.append(str(part))
        else:
            fields.append(str(part))
        cur = nxt
        i += 1
    msg = str(err["msg"]).removeprefix("Value error, ")
    what = ".".join(fields)
    return Problem(Where(node_id, tab_name, ".".join(site)), f"{what}: {msg}" if what else msg)


# --- the shape rules (section 2) -----------------------------------------------------------------
def body_sites(stmts: list[Any], prefix: str) -> Iterator[ir.Site]:
    return ir.walk(stmts, prefix, root=prefix.split(".")[0], scope="main", block=None)


def tab_sites(tab: Tab) -> Iterator[tuple[str, ir.Site]]:
    """(the def's name or "main", site) for every statement of a tab."""
    if tab.main is not None:
        for s in body_sites(list(tab.main), MAIN):
            yield MAIN, s
    for d in tab.defs:
        for s in body_sites(list(d.body), d.name):
            yield d.name, s


def namespace(node: NodeT) -> dict[str, tuple[str, str]]:
    """A node's names (all its tabs: ONE namespace, section 3) -> (tab, "def" | "var")."""
    out: dict[str, tuple[str, str]] = {}
    for t in node.tabs:
        for d in t.defs:
            out.setdefault(d.name, (t.name, "def"))
        for v in t.vars:
            out.setdefault(v, (t.name, "var"))
    return out


def shape(p: Project) -> list[Problem]:
    out: list[Problem] = []

    def bad(where: Where, msg: str) -> None:
        out.append(Problem(where, msg))

    seen: dict[str, int] = {}
    for i, n in enumerate(p.nodes):
        if n.id in seen:
            bad(Where(n.id), f"two nodes are named {n.id} (nodes {seen[n.id]} and {i})")
        seen.setdefault(n.id, i)
    globals_ = [n for n in p.nodes if isinstance(n, GlobalNode)]
    if len(globals_) > 1:
        bad(Where(), f"{len(globals_)} Global nodes: a project has at most one")
    for n in p.nodes:
        if isinstance(n, GlobalNode) and n.id != GLOBAL:
            bad(Where(n.id), f'the Global node\'s id is "{GLOBAL}", not {n.id}')
        if n.id == GLOBAL and not isinstance(n, GlobalNode):
            bad(Where(n.id), f'"{GLOBAL}" is the Global node\'s id: a {n.kind} node cannot take it')
        _tabs(n, bad)
        _names(n, bad)
        _bodies(n, bad)
    _edges(p, bad)
    start = p.node(p.start)
    if start is None:
        bad(Where(site="start"), f"start names no node ({p.start})")
    elif not isinstance(start, LoginNode | MapNode):
        bad(Where(site="start"), f"start is a login node or a map node (she stands on it), not the "
            f"{start.kind} node {p.start}")  # fmt: skip
    return out


def _tabs(n: NodeT, bad: Any) -> None:
    names = namespace(n)
    seen: set[str] = set()
    for i, t in enumerate(n.tabs):
        w = Where(n.id, t.name)
        if t.name in seen:
            bad(w, f"two tabs are named {t.name}")
        seen.add(t.name)
        if t.name == BUILT_IN_TAB:
            bad(w, f"{t.name} is the engine's: its always-on safety events show under it")
        elif t.name in REFUSED_TAB_NAMES:
            bad(w, f"{t.name} is a Python keyword or built-in name: a tab cannot take it")
        if t.name in names and t.name != MAIN:
            tab, what = names[t.name]
            word = "function" if what == "def" else "variable"
            bad(w, f"{t.name} is the name of a {word} (tab {tab}): a tab cannot take it")
        if isinstance(n, GlobalNode):
            if t.name == MAIN:
                bad(w, "Global has no main tab: its tabs hold functions, events and variables")
            elif t.main is not None:
                bad(w, "only a main tab holds a program (main): Global has none")
            continue
        if i == 0 and t.name != MAIN:
            bad(w, f"the first tab of {n.id} is its main tab (named main), not {t.name}")
        if t.name == MAIN and i != 0:
            bad(w, "main is the node's first tab")
        if t.name == MAIN and t.main is None:
            bad(w, "the main tab holds the node's program: main is a list (empty while drafting)")
        if t.name != MAIN and t.main is not None:
            bad(w, "only the main tab holds a program: this tab's main is null")
    if not isinstance(n, GlobalNode) and not any(t.name == MAIN for t in n.tabs):
        bad(Where(n.id), f"{n.id} has no main tab: every node has one (Batt's iron rule)")


def _names(n: NodeT, bad: Any) -> None:
    """One namespace per node: a name twice (two tabs, or a function and a variable) is an error
    naming both tabs."""
    first: dict[str, tuple[str, str]] = {}
    for t in n.tabs:
        entries = [(d.name, "function") for d in t.defs] + [(v, "variable") for v in t.vars]
        for name, what in entries:
            if name in first:
                tab, was = first[name]
                where = f"tab {tab}" if tab != t.name else "this tab"
                bad(
                    Where(n.id, t.name, name),
                    f"{name} is defined twice on {n.id}: a {was} in {where} and a {what} in tab "
                    f"{t.name} (a node's tabs are one namespace)",
                )
            else:
                first[name] = (t.name, what)


def _bodies(n: NodeT, bad: Any) -> None:
    for t in n.tabs:
        for root, s in tab_sites(t):
            w = Where(n.id, t.name, s.path)
            if isinstance(s.stmt, ir.Return) and root == MAIN:
                bad(w, "return belongs inside a function (a def), not in main")
            if isinstance(s.stmt, ir.TakeExit) and not isinstance(n, MapNode):
                bad(w, f"take_exit leaves a map: it belongs on a map node, not the {n.kind} node")


def _edges(p: Project, bad: Any) -> None:
    out_of: dict[str, int] = {}
    for i, e in enumerate(p.edges):
        w = Where(site=f"edges.{i}")
        a, b = p.node(e.from_), p.node(e.to)
        if a is None or b is None:
            bad(w, f"the edge {e.from_} -> {e.to} names no node {e.from_ if a is None else e.to}")
            continue
        if e.from_ in out_of:
            bad(w, f"{e.from_} has two edges out (edges {out_of[e.from_]} and {i}): the session "
                "path is one chain")  # fmt: skip
        out_of.setdefault(e.from_, i)
        pair = (a.kind, b.kind)
        if pair == ("login", "character"):
            if e.entry is not None:
                bad(w, "an edge to a character node names no entry")
        elif pair == ("character", "map"):
            assert isinstance(b, MapNode)
            if e.entry is None:
                bad(w, f"the edge into the map node {b.id} names its entry")
            elif e.entry not in {x.name for x in b.entries}:
                bad(w, f"{b.id} has no entry {e.entry}")
        else:
            bad(w, f"edges join login -> character -> map; {a.kind} -> {b.kind} is not one (map "
                "-> map is an exit, a take_exit statement; Global has no edges)")  # fmt: skip


# --- the session path -----------------------------------------------------------------------------
@dataclass(frozen=True)
class SessionPath:
    login: LoginNode | None
    character: CharacterNode | None
    map: MapNode | None
    entry: str | None

    @property
    def map_start(self) -> bool:
        """The run starts on the map node itself (she stands on it): no login, no character."""
        return self.login is None and self.map is not None


def start_map(p: Project) -> MapNode | None:
    """The start when it is a MAP node (Batt 2026-11-13: "START > map xmas_dun02"), else None."""
    n = p.node(p.start)
    return n if isinstance(n, MapNode) else None


def session_path(p: Project) -> SessionPath:
    """start (a login node) -> its edge -> a character node -> its edge -> a map node (an entry);
    a MAP start is the map node itself at its first entry, with no session."""
    m0 = start_map(p)
    if m0 is not None:
        return SessionPath(None, None, m0, m0.entries[0].name)
    nxt = {e.from_: e for e in p.edges}
    start = p.node(p.start)
    login = start if isinstance(start, LoginNode) else None
    e1 = nxt.get(login.id) if login else None
    char = p.node(e1.to) if e1 else None
    character = char if isinstance(char, CharacterNode) else None
    e2 = nxt.get(character.id) if character else None
    m = p.node(e2.to) if e2 else None
    map_node = m if isinstance(m, MapNode) else None
    return SessionPath(login, character, map_node, e2.entry if e2 and map_node else None)


def session_action(node: NodeT, block: str) -> ir.ActionStmt | None:
    """The node main's one session block (login / choose_character), if its main is just that."""
    main = node.main
    if len(main) == 1 and isinstance(main[0], ir.ActionStmt) and main[0].block == block:
        return main[0]
    return None


def lit_str(e: Any) -> str | None:
    return e.value if isinstance(e, ir.Lit) and isinstance(e.value, str) else None


def lit_int(e: Any) -> int | None:
    if isinstance(e, ir.Lit) and isinstance(e.value, int) and not isinstance(e.value, bool):
        return e.value
    return None


def secret_like(value: Any) -> bool:
    """A credential that is not a plain name: it may be a secret, so it is never echoed."""
    return not (isinstance(value, str) and CREDENTIAL_NAME.match(value))


# --- defs of a node -------------------------------------------------------------------------------
@dataclass(frozen=True)
class Defined:
    node: str
    tab: str
    name: str
    d: Def | None  # None: a variable
    lit: ir.Lit | None = None


def defs_of(n: NodeT | None) -> dict[str, Defined]:
    out: dict[str, Defined] = {}
    for t in n.tabs if n else []:
        for d in t.defs:
            out.setdefault(d.name, Defined(n.id, t.name, d.name, d))  # type: ignore[union-attr]
        for v, lit in t.vars.items():
            out.setdefault(v, Defined(n.id, t.name, v, None, lit))  # type: ignore[union-attr]
    return out


@dataclass
class Compiled:
    """A project as the engine runs it (`compile_project`)."""

    project: Project
    flow: ir.Flow | None  # None: no map node (nothing to run; the session alone is simulated)
    roots: dict[str, Where] = field(default_factory=dict)  # IR node-path root -> the project's
    display: dict[str, str] = field(default_factory=dict)  # internal name -> the user's
    context: dict[str, str] = field(default_factory=dict)  # a dispatched copy's root -> its node
    dispatched: set[tuple[str, str]] = field(default_factory=set)  # (node, event key)
    labels: dict[tuple[str, str], str] = field(default_factory=dict)  # (block, key) -> its label
    disabled: set[tuple[str, str]] = field(default_factory=set)  # (node, key): a plain function
    session: SessionPath | None = None
    run_until_stopped: bool = False

    def where(self, ir_path: str) -> Where:
        """An IR node path (`ir.sites`) in the project's terms."""
        if not ir_path:
            return Where()
        root, sep, rest = ir_path.partition(".")
        root = root.split(":", 1)[0]
        w = self.roots.get(root)
        if w is None:
            return Where(site=ir_path)
        if not w.tab:  # a map node itself (its main's statements: the main tab)
            if not rest:
                return w
            return Where(w.node, MAIN, f"{MAIN}.{rest}")
        site = w.site + (sep + rest if rest else "")
        return Where(w.node, w.tab, site)

    def text(self, s: str) -> str:
        """A text with every IR node path IR 2 prints (`maps.town.3`, `handlers.dead`) in the
        project's terms and every internal name read as the user's."""
        s = _PRINTED.sub(self._printed, s)
        if not self.display:
            return s
        return _NAME_TOKEN.sub(lambda m: self.display.get(m.group(0), m.group(0)), s)

    def _printed(self, m: re.Match[str]) -> str:
        kind, root, rest = m.group(1), m.group(2), m.group(3)
        if kind == "maps" and rest.startswith(".events."):
            key, _, tail = rest[len(".events.") :].partition(".")
            label = self.labels.get((root, key))
            if label is None:
                return m.group(0)
            return self.where(label + (f".{tail}" if tail else "")).path
        return self.where(root + rest).path or m.group(0)


_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_PRINTED = re.compile(
    r"\b(maps|handlers|procedures)\.([A-Za-z][A-Za-z0-9_]*)((?:\.[A-Za-z0-9_]+)*)"
)


# --- the compiler (the module docstring) ----------------------------------------------------------
Ctx = tuple[Literal["global", "node", "dispatch"], str]  # (how names resolve, the node)
GLOBAL_CTX: Ctx = ("global", "")


class _Compiler:
    def __init__(self, p: Project, cat: Any) -> None:
        self.p = p
        self.cat = cat
        self.g = p.global_node
        self.gdefs = defs_of(self.g)
        self.maps = p.map_nodes
        self.ndefs = {n.id: defs_of(n) for n in self.maps}
        self.out = Compiled(project=p, flow=None)
        self.taken: set[str] = {n.id for n in self.maps}
        self.taken |= set(ir.SAFETY_CRITICAL) | {MAIN, GLOBAL}
        self.taken |= set(cat.names())
        self.gname: dict[str, str] = {}  # Global's function / variable -> its IR name
        self.nname: dict[tuple[str, str], str] = {}  # (node, its own name) -> its IR name
        self.spec: dict[tuple[str, str], str] = {}  # (node, Global's function) -> its copy
        self.local: dict[str, str] = {}  # a parameter's name -> its IR name (every function)
        self.missing: dict[str, str] = {}
        self.reach: dict[str, set[str]] = {}

    # names ---------------------------------------------------------------------------------------
    def alloc(self, user: str, *prefer: str) -> str:
        """A free IR name: the first preference that is free, else the last with a number."""
        cands = [c[:48] for c in (prefer or (user,))]
        for c in cands:
            if c not in self.taken and re.match(ir.NAME, c):
                return self._take(c, user)
        base = cands[-1][:44] if re.match(r"^[A-Za-z]", cands[-1]) else f"n{cands[-1]}"[:44]
        k = 2
        while f"{base}_{k}" in self.taken:
            k += 1
        return self._take(f"{base}_{k}", user)

    def _take(self, name: str, user: str) -> str:
        self.taken.add(name)
        if name != user:
            self.out.display[name] = user
        return name

    def overridden(self, node: str) -> set[str]:
        return set(self.ndefs.get(node, {})) & set(self.gdefs)

    def _refs(self, d: Defined) -> set[str]:
        """Every name a Global definition refers to itself (calls, values, variables)."""
        out: set[str] = set()
        if d.d is None:
            return out
        stmts = [s.model_dump(mode="json", context=ir.PROJECT_JSON) for s in d.d.body]
        extra: list[Any] = []
        if d.d.on is not None:
            t = d.d.on
            extra = [x.model_dump(mode="json") for x in (t.when, t.until, t.rearm) if x is not None]
            if t.escalate:
                out.add(t.escalate)
        _names_in({"stmts": stmts, "extra": extra}, out, self.cat)
        return out - set(d.d.inputs())

    def reaches(self, name: str) -> set[str]:
        """The names Global's `name` reaches through Global's own definitions."""
        if name not in self.reach:
            self.reach[name] = set()
            seen, todo = set(), [name]
            while todo:
                n = todo.pop()
                if n in seen or n not in self.gdefs:
                    continue
                seen.add(n)
                for r in self._refs(self.gdefs[n]):
                    if r not in seen:
                        todo.append(r)
                        self.reach[name].add(r)
        return self.reach[name]

    def needs(self, node: str, name: str) -> bool:
        """Global's `name` runs differently on `node`: it reaches a name the node overrides."""
        return bool(self.reaches(name) & self.overridden(node)) and name not in self.overridden(
            node
        )

    def resolve(self, ctx: Ctx, name: str, want: str) -> str:
        """The IR name `name` means here (want "def" | "var"); a name nothing defines here keeps
        the user's spelling when nothing else has it (the linter then names it)."""
        mode, node = ctx
        own = self.ndefs.get(node, {}) if mode != "global" else {}
        d: Defined | None = None
        where = ""
        if mode == "node" and name in own:
            d, where = own[name], "node"
        elif name in self.gdefs:
            d, where = (own[name], "node") if name in own else (self.gdefs[name], "global")
        if d is None or ((d.d is None) != (want == "var")) or (d.d is not None and d.d.on):
            return self.unresolved(name)
        if where == "node":
            return self.nname[(node, name)]
        if mode != "global" and want == "def" and self.needs(node, name):
            return self.spec[(node, name)]
        return self.gname[name]

    def unresolved(self, name: str) -> str:
        if name not in self.missing:
            self.missing[name] = name if name not in self.taken else self.alloc(name, f"{name}_x")
        return self.missing[name]

    def local_name(self, name: str) -> str:
        if name not in self.local:
            self.local[name] = self.alloc(name, name, f"{name}_arg")
        return self.local[name]

    # bodies ---------------------------------------------------------------------------------------
    def stmts(self, body: list[Any], ctx: Ctx, locals_: dict[str, str]) -> list[Any]:
        rw = _Rewriter(self, ctx, locals_)
        return [rw.stmt(s.model_dump(mode="json", context=ir.PROJECT_JSON)) for s in body]

    def expr(self, e: Any, ctx: Ctx) -> Any:
        return _Rewriter(self, ctx, {}).expr(e.model_dump(mode="json", context=ir.PROJECT_JSON))

    def function(self, d: Def, ctx: Ctx) -> tuple[list[Any], dict[str, Any] | None]:
        locals_ = {n: self.local_name(n) for n in d.inputs()}
        body = self.stmts(list(d.body), ctx, locals_)
        if not d.inputs():
            return body, None
        sig = {
            "params": [
                {"name": locals_[q.name], "default": q.default.model_dump(mode="json")
                 if q.default is not None else None} for q in d.params
            ],
            "varargs": locals_[d.varargs] if d.varargs else None,
            "kwargs": locals_[d.kwargs] if d.kwargs else None,
        }  # fmt: skip
        return body, sig

    def handler(self, d: Def, ctx: Ctx) -> dict[str, Any]:
        assert d.on is not None
        t = d.on
        h = t.model_dump(mode="json")
        for k in ("when", "until", "rearm"):
            if getattr(t, k) is not None:
                h[k] = self.expr(getattr(t, k), ctx)
        if t.escalate is not None:
            h["escalate"] = self.resolve(ctx, t.escalate, "def")
        h["name"] = d.name
        h["body"] = self.stmts(list(d.body), ctx, {})
        return h

    # the flow -------------------------------------------------------------------------------------
    def run(self) -> Compiled:
        p, out = self.p, self.out
        out.session = session_path(p)
        gevents = {n: x for n, x in self.gdefs.items() if x.d is not None and x.d.on is not None}
        self.taken |= set(gevents)
        for name, x in self.gdefs.items():  # Global first: its names stay as written
            if name not in gevents:
                self.gname[name] = self.alloc(name)
                out.roots[self.gname[name]] = Where(GLOBAL, x.tab, name)
        for key, x in gevents.items():
            out.roots[key] = Where(GLOBAL, x.tab, key)
        for k in ir.SAFETY_CRITICAL:
            if k not in gevents:
                out.roots[k] = Where(GLOBAL, BUILT_IN_TAB, k)
        out.roots[GLOBAL] = Where(GLOBAL)
        for n in self.maps:
            out.roots[n.id] = Where(n.id)
            for name, x in self.ndefs[n.id].items():
                if x.d is not None and x.d.on is not None:
                    continue  # an event: its label below
                self.nname[(n.id, name)] = self.alloc(name, name, f"{n.id}__{name}")
                out.roots[self.nname[(n.id, name)]] = Where(n.id, x.tab, name)
        for n in self.maps:  # the copies Global's functions need on a node (virtual dispatch)
            for name, x in self.gdefs.items():
                if name not in gevents and x.d is not None and self.needs(n.id, name):
                    ir_name = self.alloc(name, f"{n.id}__{name}")
                    self.spec[(n.id, name)] = ir_name
                    out.roots[ir_name] = Where(GLOBAL, x.tab, name)
                    out.context[ir_name] = n.id
        for n in self.maps:  # every parameter's IR name, now that the module names are taken
            for x in self.ndefs[n.id].values():
                for q in x.d.inputs() if x.d else []:
                    self.local_name(q)
        for x in self.gdefs.values():
            for q in x.d.inputs() if x.d else []:
                self.local_name(q)
        if not self.maps:
            return out
        variables: dict[str, Any] = {}
        procedures: dict[str, Any] = {}
        signatures: dict[str, Any] = {}
        for name, x in self.gdefs.items():
            if x.lit is not None:
                variables[self.gname[name]] = x.lit.model_dump(mode="json")
            elif x.d is not None and x.d.on is None:
                procedures[self.gname[name]], sig = self.function(x.d, GLOBAL_CTX)
                if sig:
                    signatures[self.gname[name]] = sig
        for (node, name), ir_name in self.spec.items():
            d = self.gdefs[name].d
            assert d is not None
            procedures[ir_name], sig = self.function(d, ("dispatch", node))
            if sig:
                signatures[ir_name] = sig
        handlers = [self.handler(x.d, GLOBAL_CTX) for x in gevents.values() if x.d is not None]
        blocks = [self.block(n, gevents, variables, procedures, signatures) for n in self.maps]
        sp = out.session
        start = sp.map if sp is not None and sp.map is not None else self.maps[0]
        entry = sp.entry if sp is not None and sp.map is not None and sp.entry else (
            start.entries[0].name)  # fmt: skip
        out.run_until_stopped = isinstance(p.stop_when, ir.Lit) and p.stop_when.value is False
        stop_when = None
        if p.stop_when is not None and not out.run_until_stopped:
            stop_when = self.expr(p.stop_when, GLOBAL_CTX)
        data = {
            "ir": ir.IR_VERSION,
            "name": p.name,
            "description": p.description,
            "target": p.target.model_dump(mode="json"),
            "assumes": [self.expr(a, GLOBAL_CTX) for a in p.assumes],
            "max_runtime_s": p.max_runtime_s,
            "where_budget": p.where_budget,
            "stop_when": stop_when,
            "variables": variables,
            "procedures": procedures,
            "signatures": signatures,
            "handlers": handlers,
            "workflow": {
                "start_block": start.id,
                "start_entry": entry,
                "blocks": blocks,
                "run_until_stopped": out.run_until_stopped,
            },
        }
        try:
            out.flow = ir.validate(data)
        except ir.FlowError as e:
            raise ProjectError([Problem(Where(), f"the engine cannot run it: {out.text(m)}")
                                for m in e.messages]) from None  # fmt: skip
        return out

    def block(
        self,
        n: MapNode,
        gevents: dict[str, Defined],
        variables: dict[str, Any],
        procedures: dict[str, Any],
        signatures: dict[str, Any],
    ) -> dict[str, Any]:
        out = self.out
        ctx: Ctx = ("node", n.id)
        own = self.ndefs[n.id]
        for name, x in own.items():
            ir_name = self.nname.get((n.id, name))
            if ir_name is None:
                continue
            if x.lit is not None:
                variables[ir_name] = x.lit.model_dump(mode="json")
            elif x.d is not None:
                procedures[ir_name], sig = self.function(x.d, ctx)
                if sig:
                    signatures[ir_name] = sig
        events: list[dict[str, Any]] = []
        for key, x in own.items():
            if x.d is None:
                continue
            if x.d.on is None:
                if key in gevents or key in ir.SAFETY_CRITICAL:  # a plain function: no event here
                    events.append({"kind": "disable", "key": key})
                    out.disabled.add((n.id, key))
                continue
            h = self.handler(x.d, ctx)
            if key in gevents or key in ir.SAFETY_CRITICAL:
                label = self.alloc(key, f"{n.id}_{key}")
                events.append({"kind": "override", "event": h, "label": label,
                               "strict": key in ir.SAFETY_CRITICAL})  # fmt: skip
            else:
                label = self.alloc(key, key, f"{n.id}_{key}")
                events.append({"kind": "add", "event": h, "label": label})
            out.roots[label] = Where(n.id, x.tab, key)
            out.labels[(n.id, key)] = label
        for key, x in gevents.items():
            if key in own or x.d is None or not self.needs(n.id, key):
                continue
            label = self.alloc(key, f"{n.id}_{key}")
            events.append({"kind": "override", "event": self.handler(x.d, ("dispatch", n.id)),
                           "label": label, "strict": key in ir.SAFETY_CRITICAL})  # fmt: skip
            out.roots[label] = Where(GLOBAL, x.tab, key)
            out.context[label] = n.id
            out.labels[(n.id, key)] = label
            out.dispatched.add((n.id, key))
        main = self.stmts(n.main, ctx, {}) or [{"kind": "stop", "reason": "empty_main"}]
        b: dict[str, Any] = {
            "name": n.id,
            "map": n.map.model_dump(mode="json"),
            "entries": [e.model_dump(mode="json") for e in n.entries],
            "targets": [m.model_dump(mode="json") for m in n.targets],
            "ignore": [m.model_dump(mode="json") for m in n.ignore],
            "events": events,
            "main": main,
            "resume_here": n.resume_here,
        }
        if n.zones is not None:
            b["zones"] = n.zones.model_dump(mode="json")
        return b


def _proc_params(cat: Any, block: str) -> set[str]:
    b = cat.blocks.get(block)
    return {q.name for q in b.spec.params if q.type == "proc"} if b is not None else set()


def _names_in(obj: Any, out: set[str], cat: Any) -> None:
    """Every name a statement / expression JSON refers to (calls, values, variables)."""
    if isinstance(obj, list):
        for v in obj:
            _names_in(v, out, cat)
        return
    if not isinstance(obj, dict):
        return
    kind = obj.get("kind")
    if kind in ("call", "callv"):
        out.add(obj["proc"])
    elif kind == "var":
        out.add(obj["name"])
    elif kind in ("set", "for"):
        out.add(obj["var"])
    elif kind == "action":
        if obj.get("outcome_to"):
            out.add(obj["outcome_to"])
        for k in _proc_params(cat, obj.get("block", "")):
            v = (obj.get("params") or {}).get(k)
            if isinstance(v, dict) and v.get("kind") == "lit" and isinstance(v.get("value"), str):
                out.add(v["value"])
    elif kind == "wait_until" and obj.get("outcome_to"):
        out.add(obj["outcome_to"])
    elif kind == "take_exit" and isinstance(obj.get("exit"), dict) and obj["exit"].get("proc"):
        out.add(obj["exit"]["proc"])
    for k, v in obj.items():
        if k != "kind" and isinstance(v, dict | list):
            _names_in(v, out, cat)


class _Rewriter:
    """A body's JSON with every name the IR name it means here (`_Compiler.resolve`)."""

    def __init__(self, c: _Compiler, ctx: Ctx, locals_: dict[str, str]) -> None:
        self.c, self.ctx, self.locals = c, ctx, locals_

    def fn(self, name: str) -> str:
        return self.c.resolve(self.ctx, name, "def")

    def var(self, name: str) -> str:
        return self.locals.get(name) or self.c.resolve(self.ctx, name, "var")

    def kw(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {self.c.local_name(k): self.expr(v) for k, v in kwargs.items()}

    def stmt(self, s: dict[str, Any]) -> dict[str, Any]:
        s = dict(s)
        kind = s["kind"]
        if kind == "action":
            procs = _proc_params(self.c.cat, s["block"])
            params = {}
            for k, v in (s.get("params") or {}).items():
                if k in procs and v.get("kind") == "lit" and isinstance(v.get("value"), str):
                    params[k] = {"kind": "lit", "value": self.fn(v["value"])}
                else:
                    params[k] = self.expr(v)
            s["params"] = params
            if s.get("outcome_to"):
                s["outcome_to"] = self.var(s["outcome_to"])
        elif kind in ("if", "while", "wait_until"):
            s["cond"] = self.expr(s["cond"])
            if kind == "wait_until" and s.get("outcome_to"):
                s["outcome_to"] = self.var(s["outcome_to"])
        elif kind == "repeat":
            s["times"] = self.expr(s["times"])
        elif kind == "for":
            s["var"] = self.var(s["var"])
            items = dict(s["items"])
            if items["kind"] == "range":
                for k in ("start", "stop", "step"):
                    items[k] = self.expr(items[k])
            else:
                items = self.expr(items)
            s["items"] = items
        elif kind == "set":
            s["var"] = self.var(s["var"])
            s["value"] = self.expr(s["value"])
        elif kind == "call":
            s["proc"] = self.fn(s["proc"])
            s["args"] = [self.expr(a) for a in s.get("args", [])]
            s["kwargs"] = self.kw(s.get("kwargs", {}))
        elif kind == "return" and s.get("value") is not None:
            s["value"] = self.expr(s["value"])
        elif kind == "take_exit":
            x = dict(s["exit"])
            if x.get("proc"):
                x["proc"] = self.fn(x["proc"])
            if isinstance(x.get("item"), dict) and x["item"].get("kind") == "var":
                x["item"] = {"kind": "var", "name": self.var(x["item"]["name"])}
            s["exit"] = x
        for body in ("then", "orelse", "body"):
            if isinstance(s.get(body), list):
                s[body] = [self.stmt(b) for b in s[body]]
        return s

    def expr(self, e: dict[str, Any]) -> dict[str, Any]:
        e = dict(e)
        kind = e["kind"]
        if kind == "var":
            e["name"] = self.var(e["name"])
        elif kind == "callv":
            e["proc"] = self.fn(e["proc"])
            e["args"] = [self.expr(a) for a in e.get("args", [])]
            e["kwargs"] = self.kw(e.get("kwargs", {}))
        elif kind == "list":
            e["items"] = [self.expr(i) for i in e["items"]]
        elif kind in ("and", "or"):
            e["terms"] = [self.expr(t) for t in e["terms"]]
        elif kind == "not":
            e["term"] = self.expr(e["term"])
        elif kind == "sense":
            e["args"] = {k: self.expr(v) for k, v in (e.get("args") or {}).items()}
        elif kind in ("cmp", "arith"):
            e["left"], e["right"] = self.expr(e["left"]), self.expr(e["right"])
        elif kind == "do":
            e["action"] = self.stmt(e["action"])
        return e


def compile_project(p: Project, cat: Any = None) -> Compiled:
    """The project as ONE internal IR flow (the module docstring)."""
    from poring_flow.catalogue import catalogue

    return _Compiler(p, cat or catalogue()).run()


# --- the linter (layers 1-3 on the compiled IR, plus the project's own rules) ---------------------
def environments(path: Any = None) -> dict[str, str] | None:
    """config/environments.yaml's environments: id -> status (the Settings page's list, ADR-0006);
    None when the file is not there (the login's server is then unchecked, and the lint says so)."""
    from pathlib import Path

    import yaml  # type: ignore[import-untyped]  # no stubs in the dev env

    p = Path(path) if path is not None else Path(__file__).resolve().parents[4] / "config" / (
        "environments.yaml")  # fmt: skip
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return {str(e["id"]): str(e.get("status", "")) for e in data["environments"]}
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        return None


@dataclass(frozen=True)
class PFinding:
    """A finding in the project's terms."""

    rule: str
    severity: Literal["error", "readiness", "warning", "info"]
    layer: int
    where: Where
    text: str
    ack: bool = False

    @property
    def message(self) -> str:
        return f"{self.where.path}: {self.text}" if self.where.path else self.text

    def doc(self) -> dict[str, Any]:
        w = self.where
        return {"rule": self.rule, "severity": self.severity, "layer": self.layer,
                "path": w.path, "node": w.node, "tab": w.tab, "text": self.text,
                "message": self.message, "ack": self.ack}  # fmt: skip

    def finding(self) -> Any:
        from poring_flow.lint.common import Finding

        return Finding(self.rule, self.severity, self.layer, self.where.path, self.text,
                       self.ack, self.where.path)  # fmt: skip


SEVERITY_ORDER = {"error": 0, "readiness": 1, "warning": 2, "info": 3}
SIMULATED = "simulated only: Run starts on a map node; the bot's real login is ro_agent's"


def _project_rules(
    p: Project, c: Compiled, cat: Any, envs: dict[str, str] | None
) -> list[PFinding]:
    out: list[PFinding] = []

    def add(rule: str, sev: Any, where: Where, text: str, layer: int = 1) -> None:
        out.append(PFinding(rule, sev, layer, where, text))

    reserved = cat.names()
    gdefs = defs_of(p.global_node)
    for n in p.nodes:
        names = defs_of(n)
        for name, x in names.items():
            w = Where(n.id, x.tab, name)
            if name in reserved:
                add("names", "error", w, f"{name} is a catalogue name (a block, a sensor or a "
                    "helper): a function or a variable cannot reuse it")  # fmt: skip
            g = gdefs.get(name) if not isinstance(n, GlobalNode) else None
            if g is not None:
                kinds = (_kind(x), _kind(g))
                if kinds == ("function", "event"):
                    if isinstance(n, MapNode):
                        add("event_disabled", "warning", w, f"{name} is a plain function on "
                            f"{n.id}: Global's event {name} does not run there")  # fmt: skip
                elif kinds[0] != kinds[1]:
                    add("names", "error", w, f"{name} overrides Global's {kinds[1]} {name} (tab "
                        f"{g.tab}) with a {kinds[0]}: an override keeps its kind")  # fmt: skip
            if x.d is not None:
                visible = set(names) | (set(gdefs) if not isinstance(n, GlobalNode) else set())
                for q in x.d.inputs():
                    if q in visible or q in reserved:
                        add("names", "error", w, f"{name}'s input {q} has the name of a "
                            "function, a variable or a catalogue name: rename it")  # fmt: skip
        if isinstance(n, MapNode) and not n.main:
            add("empty_main", "error", Where(n.id, MAIN), f"the main of {n.id} is empty: it "
                "needs at least one block (every path ends in take_exit or stop)")  # fmt: skip
    _session_rules(p, add, envs)
    for node, key in sorted(c.dispatched):
        g = gdefs.get(key)
        add("dispatch", "info", Where(node), f"Global's event {key} runs on {node} with {node}'s "
            f"own {', '.join(sorted(_reached(c, key, node)))} (an override; tab "
            f"{g.tab if g else '?'})", layer=3)  # fmt: skip
    return out


def _kind(x: Defined) -> str:
    if x.d is None:
        return "variable"
    return "event" if x.d.on is not None else "function"


def _reached(c: Compiled, key: str, node: str) -> set[str]:
    comp = _Compiler(c.project, _cat())
    return comp.reaches(key) & comp.overridden(node)


def _cat() -> Any:
    from poring_flow.catalogue import catalogue

    return catalogue()


def _session_rules(p: Project, add: Any, envs: dict[str, str] | None) -> None:
    for n in p.nodes:
        for t in n.tabs:
            for root, s in tab_sites(t):
                for a in ir.actions_in(s.stmt):
                    if a.block not in SESSION_BLOCKS:
                        continue
                    kind = "login" if a.block == LOGIN_BLOCK else "character"
                    if n.kind != kind or t.name != MAIN or root != MAIN:
                        add(
                            "session_place",
                            "error",
                            Where(n.id, t.name, s.path),
                            f"{a.block}(...) belongs on a {kind} node's main ({SIMULATED})",
                        )
    for n in p.nodes:
        if isinstance(n, LoginNode | CharacterNode):
            block = LOGIN_BLOCK if isinstance(n, LoginNode) else CHARACTER_BLOCK
            act = session_action(n, block)
            if act is None:
                shown = ('login(server="lab-rathena", credential="lab_gm")'
                         if block == LOGIN_BLOCK else "choose_character()")  # fmt: skip
                add("session_main", "error", Where(n.id, MAIN), f"a {n.kind} node's main is one "
                    f"{shown} ({SIMULATED})")  # fmt: skip
            elif block == LOGIN_BLOCK:
                _login(p, n, act, add, envs)
            else:
                _character(n, act, add)
            if any(t.defs or t.vars for t in n.tabs):
                add("session_defs", "warning", Where(n.id), f"{n.id}'s functions and variables "
                    f"never run: a {n.kind} node runs only its main ({SIMULATED})")  # fmt: skip
    sp = session_path(p)
    if p.map_nodes and sp.map is None:
        add("session_path", "error", Where(site="edges"), "the session path is not complete: "
            "start (a login node) -> a character node -> a map node's entry, by edges (Simulate "
            "from login follows it); or start on a map node, where she stands")  # fmt: skip
    if sp.map_start:
        unused = [n.id for n in p.nodes if isinstance(n, LoginNode | CharacterNode)]
        if unused or p.edges:
            what = f"the nodes {', '.join(unused)}" if unused else "the edges"
            add("session_path", "warning", Where(site="start"), f"start is the map node {p.start}: "
                f"the run starts where she stands there; {what} are not played (a login start "
                "plays the session)")  # fmt: skip


def _login(p: Project, n: NodeT, a: ir.ActionStmt, add: Any, envs: dict[str, str] | None) -> None:
    w = Where(n.id, MAIN, "main.0")
    server = lit_str(a.params.get("server"))
    if server is None:
        add("session_server", "error", w, "login's server is an environment id, written as text")
    elif envs is None:
        add("session_server", "warning", w, "the environment list (config/environments.yaml) "
            "is not here: login's server is unchecked")  # fmt: skip
    elif server not in envs:
        add("session_server", "error", w, f"login's server {server} is not an environment of the "
            f"Settings page ({', '.join(envs)})")  # fmt: skip
    elif server != LAB_SERVER:
        add("session_server", "warning", w, f"login's server {server} ({envs[server]}) is not the "
            f"lab's rAthena ({LAB_SERVER}): the simulation plays it, the bot never acts there "
            "(ADR-0006, ADR-0016)")  # fmt: skip
    if server is not None and server != p.target.server:
        add("session_server", "warning", w, f"the project targets {p.target.server}, the login "
            f"is {server}: the run is checked against the project's server")  # fmt: skip
    cred = a.params.get("credential")
    value = cred.value if isinstance(cred, ir.Lit) else None
    if not isinstance(value, str):
        add("session_credential", "error", w, f"login's credential is a NAME, one of "
            f"{', '.join(CREDENTIALS)}")  # fmt: skip
    elif secret_like(value):  # never echoed: it may be a secret
        add(
            "session_credential",
            "error",
            w,
            "login's credential looks like a secret, not a "
            "name: a project never holds a secret (name one of "
            f"{', '.join(CREDENTIALS)}; ro_agent reads the account from the server's .env)",
        )
    elif value not in CREDENTIALS:
        add("session_credential", "error", w, f"login's credential {value} is not one of the "
            f"lab's: {', '.join(CREDENTIALS)}")  # fmt: skip


def _character(n: NodeT, a: ir.ActionStmt, add: Any) -> None:
    w = Where(n.id, MAIN, "main.0")
    if "slot" in a.params:
        slot = lit_int(a.params["slot"])
        if slot is None or not 1 <= slot <= MAX_SLOT:
            add("session_character", "error", w, f"choose_character's slot is a number 1-"
                f"{MAX_SLOT} (absent: the slot the client remembers)")  # fmt: skip
    if "name" in a.params:
        name = lit_str(a.params["name"])
        if name is None or not CHAR_NAME.match(name):
            add("session_character", "error", w, "choose_character's name: letters, digits, "
                "spaces and _ only, at most 23 (absent: the account's own)")  # fmt: skip


def project_lint(
    p: Project,
    *,
    world: Any = None,
    resolver: Any = None,
    detector: Any = None,
    cat: Any = None,
    runtime_max_s: int | None = None,
    zones_provider: Any = None,
    routes_provider: Any = None,
    envs: dict[str, str] | None = None,
    compiled: Compiled | None = None,
) -> tuple[Compiled, list[PFinding]]:
    """Every finding: the project's own rules, and IR 2's linter on the compiled flow (in the
    project's terms). `envs` None: config/environments.yaml from the repo."""
    from poring_flow.lint import lint

    cat = cat or _cat()
    c = compiled or compile_project(p, cat)
    envs = envs if envs is not None else environments()
    # (finding, its text without the dispatched copy's "on <node>: ") -- one finding per text
    found = [(f, f.text) for f in _project_rules(p, c, cat, envs)]
    if c.flow is not None:
        for g in lint(c.flow, world=world, resolver=resolver, detector=detector, cat=cat,
                      runtime_max_s=runtime_max_s, zones_provider=zones_provider,
                      routes_provider=routes_provider):  # fmt: skip
            raw = c.text(g.text)
            root = g.path.partition(".")[0]
            text = f"on {c.context[root]}: {raw}" if root in c.context else raw
            pf = PFinding(g.rule, g.severity, g.layer, c.where(g.path), text, g.ack)
            found.append((pf, raw))
    seen: set[tuple[str, str, str]] = set()
    out: list[PFinding] = []
    for f, raw in found:
        key = (f.rule, f.where.path, raw)
        if key not in seen:
            seen.add(key)
            out.append(f)
    out.sort(key=lambda f: (f.layer, SEVERITY_ORDER[f.severity]))
    return c, out


def has_secret(p: Project) -> bool:
    """A login's credential that is not a plain name: the project may hold a secret, so neither
    its hash nor the credential is ever returned (ADR-0004 c: even a digest can confirm a guess)."""
    for n in p.nodes:
        for t in n.tabs:
            for _, s in tab_sites(t):
                for a in ir.actions_in(s.stmt):
                    if a.block == LOGIN_BLOCK and "credential" in a.params:
                        v = a.params["credential"]
                        if not (isinstance(v, ir.Lit) and isinstance(v.value, str)) or (
                            secret_like(v.value)
                        ):
                            return True
    return False


def shown_hash(p: Project) -> str | None:
    return None if has_secret(p) else project_hash(p)


def effective_doc(c: Compiled) -> dict[str, list[dict[str, Any]]]:
    """Each map node's event set as it runs there (13.6.2), each event where it is written."""
    from poring_flow.effective import merge

    out: dict[str, list[dict[str, Any]]] = {}
    flow = c.flow
    if flow is None or flow.workflow is None:
        return out
    for b in flow.workflow.blocks:
        rows = []
        for e in merge(flow, b).events:
            dispatched = (b.name, e.key) in c.dispatched
            rows.append({
                "key": e.key,
                "state": "inherited" if dispatched else e.state,
                "dispatched": dispatched,  # Global's event, run with this node's overrides
                "priority": e.handler.priority,
                "rank": ir.rank_of(e.handler),
                "mode": e.handler.mode,
                "path": c.where(e.label).path,
                "active": e.active,
                "safety_critical": e.key in ir.SAFETY_CRITICAL,
                "built_in": e.built_in,
            })  # fmt: skip
        out[b.name] = rows
    return out


def lint_doc(
    p: Project,
    *,
    world: Any,
    resolver: Any,
    detector: Any = None,
    runtime_max_s: int | None = None,
    zones_provider: Any = None,
    routes_provider: Any = None,
    envs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """POST /flows/lint's document (the browser reads counts, findings, run, project_hash)."""

    c, findings = project_lint(
        p, world=world, resolver=resolver, detector=detector, runtime_max_s=runtime_max_s,
        zones_provider=zones_provider, routes_provider=routes_provider, envs=envs,
    )  # fmt: skip
    from poring_flow import live

    # matpilot round 16 #1: the page's run verdict is the LIVE player's (live.verdict), the same the
    # Run route uses: a `bindings` readiness item on a hunt core is answered by the runner, so it is
    # shown as answered (info), never as "1 not ready" beside a Run that plays it
    own = live.own_binding_paths(c) if c.flow is not None else set()
    docs = []
    for f in findings:
        d = f.doc()
        if f.rule == "bindings" and f.severity == "readiness" and f.where.path in own:
            d = {**d, "severity": "info", "answered": True,
                 "message": f"{d['message']} -- answered: the live player plays this block with "
                            "the runner (its own binding)"}  # fmt: skip
        docs.append(d)
    zero = {"error": 0, "readiness": 0, "warning": 0, "info": 0}
    counts = dict(zero)
    by_node: dict[str, dict[str, int]] = {}
    for f, d in zip(findings, docs, strict=True):
        counts[d["severity"]] += 1
        by_node.setdefault(f.where.node, dict(zero))[d["severity"]] += 1
    if c.flow is not None:
        v = live.verdict(
            c, findings, world=world, resolver_given=resolver is not None,
            runtime_max_s=runtime_max_s, zones_loaded=zones_provider is not None,
            routes_loaded=routes_provider is not None,
        )  # fmt: skip
        run = {"allowed": v.allowed, "summary": c.text(v.summary()),
               "reasons": [c.text(r) for r in v.reasons]}  # fmt: skip
    else:
        why = "no map node: nothing runs (Run starts on a map node)"
        run = {"allowed": False, "summary": f"run refused: {why}", "reasons": [why]}
    # matpilot round 17 N1: per map node with a hunt core, what the box plays there in a box run
    # and which run settings / runner handlers that replaces (live.takeovers, hunt_plan's rule)
    box: dict[str, Any] = {}
    if c.flow is not None and c.flow.workflow is not None:
        for b in c.flow.workflow.blocks:
            doc = live.takeovers(c.flow, b.name, lambda s: c.where(s).path)
            if doc is not None:
                box[b.name] = doc
    return {
        "project_hash": shown_hash(p),
        "findings": docs,
        "counts": counts,
        "by_node": by_node,
        "run": run,
        "box": box,
        "effective": effective_doc(c),
        "world": {
            "server": world.server if world is not None else None,
            "maps": sorted(world.sheets) if world is not None else [],
        },
    }


def maps_of(c: Compiled) -> list[str]:
    """Every map the project names (for the sheets to load)."""
    from poring_flow import editor

    return editor.maps_of(c.flow) if c.flow is not None else []


# --- SIMULATE (section 5: the session as the Maps page's mock, then the map flow) ----------------
def session_steps(p: Project, sp: SessionPath) -> list[dict[str, Any]]:
    """The login and the character choice as play steps (session.ts's mock times): nothing logs
    in or types; Run starts on a map node."""
    assert sp.login is not None and sp.character is not None
    login = session_action(sp.login, LOGIN_BLOCK)
    char = session_action(sp.character, CHARACTER_BLOCK)
    t_login = SESSION_S["start"] + SESSION_S["login"]
    t_char = t_login + SESSION_S["character"]
    server = lit_str(login.params.get("server")) if login else None
    cred = lit_str(login.params.get("credential")) if login else None
    slot = lit_int(char.params.get("slot")) if char else None
    name = lit_str(char.params.get("name")) if char else None
    return [
        {"kind": "login", "t0": 0.0, "t1": t_login, "block": None, "map": None,
         "node": Where(sp.login.id, MAIN, "main.0").path, "session_node": sp.login.id,
         "action": LOGIN_BLOCK, "outcome": "ok" if login else "failed", "server": server,
         "credential": cred if cred is not None and not secret_like(cred) else None,
         "phases": [{"what": "start", "t0": 0.0, "t1": SESSION_S["start"]},
                    {"what": "login", "t0": SESSION_S["start"], "t1": t_login}],
         "simulated": True},
        {"kind": "character", "t0": t_login, "t1": t_char, "block": None, "map": None,
         "node": Where(sp.character.id, MAIN, "main.0").path, "session_node": sp.character.id,
         "action": CHARACTER_BLOCK, "outcome": "ok" if char else "failed", "slot": slot,
         "name": name, "simulated": True,
         "enters": {"block": sp.map.id if sp.map else None, "entry": sp.entry}},
    ]  # fmt: skip


def simulate(
    p: Project,
    world: Any,
    scenario: Any = None,
    cat: Any = None,
    compiled: Compiled | None = None,
) -> dict[str, Any]:
    """The trace (poring_flow.trace's document) of the project: from the login node (the session
    mock, then the start map's entry through the edges), from a MAP start (its first entry, no
    session: `session` null), or from the scenario's map node. `block` is a map node's id; a step's
    `node` is "<node>/<tab>/<site>". ValueError: nothing to run from there (the route's
    invalid_scenario)."""
    from poring_flow.trace import Scenario

    cat = cat or _cat()
    c = compiled or compile_project(p, cat)
    sc = scenario or Scenario()
    start_node = p.node(sc.start_block) if sc.start_block else p.node(p.start)
    steps: list[dict[str, Any]] = []
    t0 = 0.0
    run_sc = sc
    session: dict[str, Any] | None = None
    if isinstance(start_node, MapNode):
        pass  # a map start or the scenario's map node: no session, the map flow from its entry
    elif sc.start_block is None or isinstance(start_node, LoginNode):
        sp = c.session or session_path(p)
        if sp.login is None or sp.character is None or sp.map is None or sp.entry is None:
            raise ValueError("no session path: start (a login node) -> a character node -> a map "
                             "node's entry, by edges")  # fmt: skip
        steps = session_steps(p, sp)
        t0 = steps[-1]["t1"]
        run_sc = sc.model_copy(update={"start_block": sp.map.id, "start_entry": sp.entry})
        session = {"login": sp.login.id, "character": sp.character.id, "map": sp.map.id,
                   "entry": sp.entry, "length_s": t0}  # fmt: skip
    else:
        raise ValueError(f"{sc.start_block} is no map node (Run and Simulate start on one)")
    if c.flow is None:
        raise ValueError("no map node: nothing to simulate after the session")
    sim = _ProjectSim(c, world, run_sc, cat, t0)
    doc: dict[str, Any] = dict(sim.result())
    doc["play"] = [*steps, *doc["play"]]
    for st in doc["play"]:
        if st.get("proc"):
            st["proc"] = c.text(st["proc"])
    for st in steps:
        doc["nodes"][st["node"]] = {"runs": 1, "total_s": round(st["t1"] - st["t0"], 1),
                                    "first_t": st["t0"], "last_t": st["t1"], "last": st["outcome"],
                                    "outcomes": {st["outcome"]: 1}}  # fmt: skip
    doc["nodes"] = dict(sorted(doc["nodes"].items()))
    for ev in doc["events"]:
        if ev["kind"] in ("interrupted", "block", "relocate"):
            ev["what"] = c.where(ev["what"]).path or ev["what"]
    for r in doc["where"]["reads"]:
        r["reason"] = c.where(r["reason"]).path or r["reason"]
    doc["notes"] = sorted({c.text(n) for n in doc["notes"]})
    doc["session"] = session
    doc["scenario"] = sc.model_dump(mode="json")
    return doc


def _sim_class() -> Any:
    from poring_flow.trace import TraceSim

    class ProjectSim(TraceSim):
        """TraceSim on the compiled flow, its node paths in the project's terms."""

        def __init__(self, c: Compiled, world: Any, sc: Any, cat: Any, start_t: float) -> None:
            assert c.flow is not None
            super().__init__(c.flow, world, sc, cat, start_t=start_t)
            self.paths = {k: c.where(v).path for k, v in self.paths.items()}
            self.do_paths = {k: c.where(v).path for k, v in self.do_paths.items()}

    return ProjectSim


def _ProjectSim(c: Compiled, world: Any, sc: Any, cat: Any, start_t: float) -> Any:  # noqa: N802
    return _sim_class()(c, world, sc, cat, start_t)


# --- Run's keys (section 6) -----------------------------------------------------------------------
RUNNER_KEY_FIELDS = ("heal_key", "fly_key", "home_key", "knife_key", "dagger_key")


@dataclass(frozen=True)
class RunnerKeys:
    keys: dict[str, str] | None  # the five keys (scripts/flow_config.KEY_FIELDS), or None
    problems: list[str]
    functions: dict[str, str] = field(default_factory=dict)  # key field -> the function's name


def runner_keys(p: Project, node_id: str, compiled: Compiled | None = None) -> RunnerKeys:
    """The Run request's five hotbar keys, read from the functions the node's dungeon_hunt names
    (heal, fly, knife_on, knife_back, and home when it names one; Batt 2026-11-13, the one box),
    else (home) the node's item warp by function: resolved on THAT node (its override first, then
    Global's), through calls with literal arguments, to exactly one press_key each, every key a
    different hotbar key. Stage 3 (live-blocks.md 3.3): a knife or home function that is a BODY of
    presses and waits gives its FIRST press (functions.role_key)."""
    from poring_flow import functions as fn

    node = p.node(node_id)
    if not isinstance(node, MapNode):
        return RunnerKeys(None, [f"{node_id} is no map node: Run belongs to a map node"])
    c = compiled or compile_project(p)
    flow = c.flow
    block = next((b for b in flow.workflow.blocks if b.name == node_id), None) if (
        flow is not None and flow.workflow) else None  # fmt: skip
    if flow is None or block is None:
        return RunnerKeys(None, [f"{node_id} does not compile"])
    hunts = [a for s in ir.walk(block.main, block.name, root=block.name, scope="block",
                                block=block) for a in ir.actions_in(s.stmt)
             if a.block == fn.RUNNER_BLOCK]  # fmt: skip
    problems: list[str] = []
    names: dict[str, str] = {}
    if not hunts:
        problems.append(f"{node_id}'s main has no dungeon_hunt (hunt with the runner): Run "
                        "belongs to a map node whose main holds one")  # fmt: skip
    else:
        roles = [fn.role_functions(a) for a in hunts]
        if any(r != roles[0] for r in roles[1:]):
            problems.append(f"{node_id}'s dungeon_hunt blocks name different functions")
        for role, field_name in fn.ROLES.items():
            name = roles[0].get(role)
            if name is None:
                problems.append(f"dungeon_hunt's {role} names no function")
            else:
                names[field_name] = name
        home = roles[0].get(fn.HOME_ROLE)
        if home is not None:  # the runner flies home on this function's key
            names[fn.HOME_FIELD] = home
    wings = [x.proc for b, _, x in fn.item_warps(flow) if b.name == node_id and x.proc]
    if fn.HOME_FIELD in names:
        pass
    elif not wings:
        problems.append(f"{node_id} has no Butterfly Wing home: dungeon_hunt's home names no "
                        "function and the map has no item warp by function")  # fmt: skip
    elif len(set(wings)) > 1:
        problems.append(f"{node_id}'s item warps run different functions: one home key")
    else:
        names["home_key"] = wings[0]
    keys: dict[str, str] = {}
    hotbar = fn.hotbar_keys()
    role_of = {f: r for r, f in fn.ALL_ROLES.items()}
    for field_name in RUNNER_KEY_FIELDS:
        name = names.get(field_name)
        if name is None:
            continue
        # stage 3 (live-blocks.md 3.3): a knife / home BODY's key is its first press
        key, why = fn.role_key(flow, name, role_of.get(field_name, ""))
        if key is None:
            problems.append(f"{field_name}: {c.text(why)}")
        elif key not in hotbar:
            problems.append(f"{field_name}: {c.text(name)} presses {key}, not a hotbar key")
        else:
            keys[field_name] = key
    seen: dict[str, str] = {}
    for f, k in keys.items():
        if k in seen:
            problems.append(f"{seen[k]} and {f} are both {k}: each key its own")
        seen.setdefault(k, f)
    shown = {f: c.text(n) for f, n in names.items()}
    if problems or len(keys) != len(RUNNER_KEY_FIELDS):
        return RunnerKeys(None, problems or ["not every key resolves"], shown)
    return RunnerKeys({f: keys[f] for f in RUNNER_KEY_FIELDS}, [], shown)


# --- the generated JSON Schema (drift-tested, like the IR's) --------------------------------------
SCHEMA_PATH = "packages/poring_flow/schema/project.schema.json"


def json_schema() -> str:
    schema = Project.model_json_schema(by_alias=True)
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    """`python -m poring_flow.project > packages/poring_flow/schema/project.schema.json`."""
    import sys

    sys.stdout.write(json_schema())


if __name__ == "__main__":
    main()
