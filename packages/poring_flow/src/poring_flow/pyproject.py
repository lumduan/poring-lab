"""The PROJECT's Python view (format 3; docs/planning/project-model.md section 4): ONE FILE PER
TAB, plus `project.py` for the project's head and its graph. Parsed with `ast` and never run, under
pyview's rules (7.2's allow-list, the hostile-input limits), so every file round-trips: project ->
files -> project is identical, per file and for the whole project.

    project.py          the Config (FLOW_NAME, MAX_RUNTIME_S, START, STOP_WHEN, CLIENT, ...),
                        node("xmas_dun02", kind="map", pos=(560, 0), tabs=["main"]) per node,
                        edge("character", "xmas_dun02", entry="here") per edge
    global/keys.py      def fly_wing():
                            press_key("F8")
    global/safety.py    @on(hp_percent() < 30, rearm=hp_percent() > 50, priority=SURVIVAL, ...)
                        def hp_low():
                            heal()
    login/main.py       def main():
                            login(server="lab-rathena", credential="lab_gm")
    xmas_dun02/main.py  @map_node("xmas_dun02", entries=[entry_anywhere("here")], zones=...)
                        def main():
                            ...

The spellings (the engine owns them, section 4):
- every file starts with the generated lines and `from poring_flow.learner import *` (the stub
  that names every block, pyview's learner shape); a node's file then imports Global
  (`from global_ import *`: `global` is a Python keyword, so the module takes PEP 8's trailing
  underscore; its files are global/<tab>.py) and every other tab of its node but main
  (`from .hunt import *`). The parser removes exactly these import lines; a node's names are its
  tabs' and Global's whatever the imports say (section 3).
- a tab's variables are `NAME = <literal>` lines (Setup), its functions and events defs in their
  order (Functions / Events), the main tab's program `def main():` last (Main); a map node's main
  carries the node's map data: `@map_node("<map>", entries=[...], targets=[...], ignore=[...],
  resume_here=False, zones=zones("<map>", sha256="..."))`.
- a function: `def go(cell, times=3, *rest, **opts):` (required inputs first, defaults literal);
  a call `go(cell("m", 1, 2), times=4)`; a function's value `x = pick(3)` / `if left() > 0:`;
  `return` / `return x` inside a def; an event `@on(<when>, priority=..., ...)` above a def
  without inputs (pyview's on(...) arguments).
- a def or a variable of a node that OVERRIDES Global's says so in the comment line above it
  (`# overrides Global's fly_wing (tab keys)`); the parser ignores comments.
- a login's credential that is not a plain name is printed `"<redacted>"` (a project never holds a
  secret; the lint says so and the view never echoes one).
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any

from poring_flow import ir, pyview
from poring_flow import settings as setting_reg
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.project import (
    GLOBAL,
    LOGIN_BLOCK,
    MAIN,
    TAB_NAME,
    GlobalNode,
    MapNode,
    NodeT,
    Project,
    ProjectError,
    Tab,
    defs_of,
    dump,
    secret_like,
    validate,
)

PROJECT_FILE = "project.py"
LEARNER = f"from {pyview.LEARNER_MODULE} import *"
GLOBAL_MODULE = "global_"
GLOBAL_IMPORT = f"from {GLOBAL_MODULE} import *  # Global's tabs"
REDACTED = "<redacted>"
KINDS = ("login", "character", "map", "global")
CONFIG = {
    "FLOW_NAME": "name",
    "DESCRIPTION": "description",
    "MAX_RUNTIME_S": "max_runtime_s",
    "WHERE_BUDGET": "where_budget",
    "START": "start",
    "STOP_WHEN": "stop_when",
    "ASSUMES": "assumes",
}
TARGET_CONFIG = pyview.TARGET_CONFIG


@dataclass(frozen=True)
class PyFile:
    node: str  # "" for project.py
    tab: str
    path: str
    text: str

    def doc(self) -> dict[str, str]:
        return {"node": self.node, "tab": self.tab, "path": self.path, "text": self.text}


def file_path(node: str, tab: str) -> str:
    return f"{node}/{tab}.py"


# --- the printer --------------------------------------------------------------------------------
def _redacted(p: Project) -> Project:
    """The project with every login credential that is not a plain name shown as REDACTED."""
    data = dump(p)
    hit = False

    def walk(o: Any) -> None:
        nonlocal hit
        if isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            if o.get("kind") == "action" and o.get("block") == LOGIN_BLOCK:
                c = (o.get("params") or {}).get("credential")
                if isinstance(c, dict) and (c.get("kind") != "lit" or secret_like(c.get("value"))):
                    o["params"]["credential"] = {"kind": "lit", "value": REDACTED}
                    hit = True
            for v in o.values():
                walk(v)

    walk(data)
    return Project.model_validate(data) if hit else p


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() and abs(v) < 1e15 else repr(float(v))


def _params(d: Any) -> str:
    parts = [
        q.name if q.default is None else f"{q.name}={pyview._lit_src(q.default.value)}"
        for q in d.params
    ]
    if d.varargs:
        parts.append(f"*{d.varargs}")
    if d.kwargs:
        parts.append(f"**{d.kwargs}")
    return ", ".join(parts)


def _def_lines(d: Any, cat: Catalogue) -> list[str]:
    deco: list[str] = []
    if d.on is not None:
        h = ir.Handler(name=d.name, body=list(d.body), **dict(d.on))
        deco = pyview._fit("@on", pyview._on_args(h, cat), "")
    return [*deco, f"def {d.name}({_params(d)}):", *pyview._stmts(list(d.body), "    ", cat)]


def _map_args(n: MapNode) -> list[str]:
    args = [pyview._s(n.map.map)]
    ents = []
    for e in n.entries:
        radius = "" if e.radius == 2 else f", radius={e.radius}"
        ents.append(
            f"entry_at({pyview._s(e.name)}, {pyview._ref_src(e.at)}{radius})"
            if e.at
            else f"entry_anywhere({pyview._s(e.name)}{radius})"
        )
    args.append("entries=[" + ", ".join(ents) + "]")
    if n.targets:
        args.append("targets=" + pyview._lit_src(list(n.targets)))
    if n.ignore:
        args.append("ignore=" + pyview._lit_src(list(n.ignore)))
    if not n.resume_here:
        args.append("resume_here=False")
    if n.zones is not None:
        args.append(f"zones=zones({pyview._s(n.zones.map)}, sha256={pyview._s(n.zones.sha256)})")
    return args


def _override(name: str, gdefs: dict[str, Any]) -> list[str]:
    g = gdefs.get(name)
    return [f"# overrides Global's {name} (tab {g.tab})"] if g is not None else []


def vars_in_order(t: Tab) -> list[tuple[str, ir.Lit]]:
    """A tab's variables as its file and its blocks show them: the ordinary ones in their
    order, then the settings in the registry's (poring_flow.settings: the page's order)."""
    rank = {f.var: i for i, f in enumerate(setting_reg.FIELDS)}
    plain = [(k, v) for k, v in t.vars.items() if k not in rank]
    ranked = sorted(((k, v) for k, v in t.vars.items() if k in rank), key=lambda kv: rank[kv[0]])
    return plain + ranked


def setting_notes(p: Project, cat: Catalogue | None = None) -> dict[str, dict[str, str]]:
    """The setting blocks' notes the lint computes (lint/settings.py notes: a block not used in a
    Run of this box, a safety switch off), by "node/tab/var"; {} when the project does not compile
    (the lint says why)."""
    from poring_flow.lint import settings as setting_rules
    from poring_flow.project import compile_project

    try:
        c = compile_project(p, cat)
    except ProjectError:
        return {}
    return setting_rules.notes(p, c)


def setting_tail(f: setting_reg.Field, v: Any, note: dict[str, str] | None = None) -> str:
    """A setting line's comment: its words and how to read the value, then what the lint says of
    THIS block (matpilot round 20 #3, #4a): "⚠ off: ..." while a safety switch is off, "· not used
    here: the drink event plays it" while the box or another setting stops it."""
    out = f"  {setting_reg.comment(f, v)}"
    if note and note.get("safety"):
        out += f" · ⚠ off: {note['safety']}"
    if note and note.get("unused"):
        out += f" · {note['unused']}"
    return out


def print_tab(p: Project, n: NodeT, t: Tab, cat: Catalogue | None = None,
              notes: dict[str, dict[str, str]] | None = None) -> str:  # fmt: skip
    """One tab's file (the module docstring). ``notes``: the setting blocks' (setting_notes; None:
    computed here, so a tab printed alone reads as it does among the project's files)."""
    cat = cat or catalogue()
    if notes is None:
        notes = setting_notes(p, cat)
    gdefs = {} if isinstance(n, GlobalNode) else defs_of(p.global_node)
    head = [*pyview.GENERATED, LEARNER]
    if not isinstance(n, GlobalNode) and p.global_node is not None:
        head.append(GLOBAL_IMPORT)
    head += [f"from .{x.name} import *" for x in n.tabs if x.name not in (t.name, MAIN)]
    chunks: list[tuple[bool, list[str], str]] = []
    if t.vars:
        lines: list[str] = []
        for k, v in vars_in_order(t):
            # a SETTING (live-blocks.md 12): a plain assignment with its words as a comment
            f = setting_reg.BY_VAR.get(k)
            note = (notes or {}).get(f"{n.id}/{t.name}/{k}")
            tail = setting_tail(f, v.value, note) if f is not None and f.block else ""
            lines += [*_override(k, gdefs), f"{k} = {pyview._lit_src(v.value)}{tail}"]
        chunks.append((False, lines, "Setup"))
    for d in t.defs:
        section = "Events" if d.on is not None else "Functions"
        chunks.append((True, [*_override(d.name, gdefs), *_def_lines(d, cat)], section))
    if t.main is not None:
        deco = pyview._fit("@map_node", _map_args(n), "") if isinstance(n, MapNode) else []
        body = pyview._stmts(list(t.main), "    ", cat)
        chunks.append((True, [*deco, "def main():", *body], "Main"))
    out = list(head)
    prev_def, prev = False, ""
    for is_def, lines, section in chunks:
        out += ["", ""] if is_def or prev_def else [""]
        if section != prev:
            out.append(pyview.section_rule(section))
        out += lines
        prev_def, prev = is_def, section
    return "\n".join(out) + "\n"


def print_project_file(p: Project, cat: Catalogue | None = None) -> str:
    cat = cat or catalogue()
    cfg = [f"FLOW_NAME = {pyview._s(p.name)}"]
    if p.description:
        cfg.append(f"DESCRIPTION = {pyview._s(p.description)}")
    cfg.append(f"MAX_RUNTIME_S = {p.max_runtime_s}")
    if p.where_budget != ir.WHERE_BUDGET_DEFAULT:
        cfg.append(f"WHERE_BUDGET = {p.where_budget}")
    cfg.append(f"START = {pyview._s(p.start)}")
    if p.stop_when is not None:
        cfg.append(f"STOP_WHEN = {pyview.expr_src(p.stop_when, cat)}")
    if p.assumes:
        cfg.append("ASSUMES = [" + ", ".join(pyview.expr_src(a, cat) for a in p.assumes) + "]")
    t = p.target
    cfg += [
        f"CLIENT = {pyview._s(t.client)}",
        f"SERVER = {pyview._s(t.server)}",
        f"LOCALE = {pyview._s(t.locale)}",
        f"PATH = {pyview._s(pyview.CONST_OF[t.path])}",
    ]
    nodes = []
    for n in p.nodes:
        tabs = "[" + ", ".join(pyview._s(x.name) for x in n.tabs) + "]"
        pos = f"({_num(n.pos.x)}, {_num(n.pos.y)})"
        nodes.append(f"node({pyview._s(n.id)}, kind={pyview._s(n.kind)}, pos={pos}, tabs={tabs})")
    out = [*pyview.GENERATED, LEARNER, "", pyview.section_rule("Config"), *cfg, "",
           pyview.section_rule("Nodes"), *nodes]  # fmt: skip
    if p.edges:
        out += ["", pyview.section_rule("Edges")]
        for e in p.edges:
            entry = f", entry={pyview._s(e.entry)}" if e.entry is not None else ""
            out.append(f"edge({pyview._s(e.from_)}, {pyview._s(e.to)}{entry})")
    return "\n".join(out) + "\n"


def print_files(p: Project, cat: Catalogue | None = None) -> list[PyFile]:
    """Every tab's file, node by node in the project's order, then project.py."""
    cat = cat or catalogue()
    shown = _redacted(p)
    notes = setting_notes(p, cat)
    files = [
        PyFile(n.id, t.name, file_path(n.id, t.name), print_tab(shown, n, t, cat, notes))
        for n in shown.nodes
        for t in n.tabs
    ]
    files.append(PyFile("", "", PROJECT_FILE, print_project_file(shown, cat)))
    return files


# --- the parser ---------------------------------------------------------------------------------
def _tree(source: str, what: str) -> ast.Module:
    pre = pyview._precheck(source)
    if pre:
        raise pyview.ParseError([f"{what}: {m}" for m in pre])
    try:
        tree = ast.parse(source, mode="exec", type_comments=False)
    except SyntaxError as e:
        raise pyview.ParseError(
            [f"{what}: line {e.lineno or 0}, col {e.offset or 0}: syntax error ({e.msg})"]
        ) from None
    except (RecursionError, MemoryError, ValueError) as e:
        raise pyview.ParseError(
            [f"{what}: the source cannot be parsed ({type(e).__name__})"]
        ) from None
    _strip_imports(tree)
    return tree


def _strip_imports(tree: ast.Module) -> None:
    """Remove exactly the view's import lines (the module docstring): the learner stub, Global,
    and a sibling tab; any other import stays, and the allow-list refuses it."""
    keep = []
    for st in tree.body:
        if (
            isinstance(st, ast.ImportFrom)
            and len(st.names) == 1
            and st.names[0].name == "*"
            and st.names[0].asname is None
            and (
                (st.level == 0 and st.module in (pyview.LEARNER_MODULE, GLOBAL_MODULE))
                or (st.level == 1 and st.module is not None and re.match(TAB_NAME, st.module))
            )
        ):
            continue
        keep.append(st)
    tree.body = keep


ALLOWED = (*pyview.ALLOWED, ast.arg, ast.Return)


def _allow_list(tree: ast.Module, ctx: pyview._Ctx) -> None:
    """pyview's allow-list, with a def's inputs (positional, defaults, *args, **kwargs) and
    `return` allowed (the project model)."""
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > pyview.MAX_NODES:
            ctx.err(tree, f"more than {pyview.MAX_NODES} syntax nodes")
            return
        name = type(node).__name__
        if not isinstance(node, ALLOWED):
            ctx.refuse(node, name, pyview.WHY.get(name, "not in the allow-list"))
            continue
        if isinstance(node, ast.FunctionDef):
            a = node.args
            if a.posonlyargs or a.kwonlyargs or a.kw_defaults:
                ctx.refuse(node, f"def {node.name} with / or keyword-only inputs",
                           "inputs are plain, then *args, then **kwargs")  # fmt: skip
            if node.returns is not None or getattr(node, "type_params", []):
                ctx.refuse(node, f"def {node.name} with annotations", "no annotations")
            continue
        if isinstance(node, ast.arg):
            if node.annotation is not None:
                ctx.refuse(node, f"input {node.arg} with an annotation", "no annotations")
            elif node.arg.startswith("_") or not pyview.ASCII_NAME.match(node.arg):
                ctx.refuse(node, f"input {node.arg!r}", "names are ASCII letters, digits and _")
            continue
        if isinstance(node, ast.Return):
            continue
        _one(node, ctx)


def _one(node: ast.AST, ctx: pyview._Ctx) -> None:
    """pyview's per-node literal / name / call rules (its allow-list's body for one node)."""
    import math

    if isinstance(node, ast.Name) and node.id.startswith("_") and node.id != "_":
        ctx.refuse(node, f"name {node.id}", "a name starting with _ is refused")
    elif isinstance(node, ast.Name) and not (node.id == "_" or pyview.ASCII_NAME.match(node.id)):
        ctx.refuse(node, f"name {node.id!r}", "names are ASCII letters, digits and _")
    elif isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool) or v is None:
            pass
        elif isinstance(v, int) and abs(v) > 1_000_000_000:
            ctx.refuse(node, "this integer", "at most 1,000,000,000")
        elif isinstance(v, float) and not math.isfinite(v):
            ctx.refuse(node, "this number", "numbers are finite")
        elif isinstance(v, str) and len(v) > ir.MAX_STR:
            ctx.refuse(node, "this string", f"at most {ir.MAX_STR} characters")
        elif not isinstance(v, bool | int | float | str):
            ctx.refuse(node, f"a {type(v).__name__} constant", "numbers, text, True/False")
    elif isinstance(node, ast.List | ast.Tuple) and len(node.elts) > ir.MAX_LIST:
        ctx.refuse(node, "this list", f"at most {ir.MAX_LIST} elements")
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            ctx.refuse(node, "this call", "the callee is a plain name")
        for kw in node.keywords:
            if kw.arg is None:
                ctx.refuse(kw, "**kwargs", "arguments are listed one by one")
    elif isinstance(node, ast.While | ast.For) and node.orelse:
        ctx.refuse(node, f"{type(node).__name__.lower()}...else", "loops have no else")


@dataclass
class _Names:
    """A file's own top-level names (pass 1)."""

    functions: list[str]
    events: list[str]
    variables: list[str]


def _names(tree: ast.Module) -> _Names:
    out = _Names([], [], [])
    for st in tree.body:
        if isinstance(st, ast.FunctionDef) and st.name != MAIN:
            deco = st.decorator_list
            is_event = bool(deco) and pyview._call_name(deco[0]) == "on"
            (out.events if is_event else out.functions).append(st.name)
        elif (
            isinstance(st, ast.Assign)
            and len(st.targets) == 1
            and isinstance(st.targets[0], ast.Name)
        ):
            out.variables.append(st.targets[0].id)
    return out


def _ctx(cat: Catalogue, functions: set[str], variables: set[str]) -> pyview._Ctx:
    ctx = pyview._Ctx(cat, project=True)
    ctx.procedures = set(functions)
    ctx.variables = {v: ir.Lit(value=0) for v in variables}
    return ctx


def _def(st: ast.FunctionDef, ctx: pyview._Ctx) -> dict[str, Any]:
    a = st.args
    inputs = [x.arg for x in a.args] + [x.arg for x in (a.vararg, a.kwarg) if x is not None]
    ctx.inputs, ctx.in_def, ctx.loops = set(inputs), True, 0
    try:
        defaults: list[Any] = [None] * (len(a.args) - len(a.defaults))
        for dnode in a.defaults:
            try:
                defaults.append(pyview._literal(dnode, ctx))
            except pyview._Bad:
                defaults.append(None)
        params = [{"name": x.arg, "default": d} for x, d in zip(a.args, defaults, strict=True)]
        out: dict[str, Any] = {
            "name": st.name,
            "params": params,
            "varargs": a.vararg.arg if a.vararg else None,
            "kwargs": a.kwarg.arg if a.kwarg else None,
            "on": None,
        }
        deco = st.decorator_list
        if len(deco) > 1:
            ctx.refuse(st, f"def {st.name} with {len(deco)} decorators", "at most one")
        if deco:
            if pyview._call_name(deco[0]) != "on":
                ctx.refuse(deco[0], "this decorator", "only on(...) above a function")
                raise pyview._Bad
            call: ast.Call = deco[0]  # type: ignore[assignment]
            for k in pyview._kw(call):
                if k in ("overrides", "key", "scope"):
                    ctx.err(call, f"on(...) has no argument {k} here: a node's def of Global's "
                            "name IS its override")  # fmt: skip
                    raise pyview._Bad
            _, h = pyview._handler(st, ctx, scoped=False)
            out["body"] = h.pop("body")
            h.pop("name", None)
            out["on"] = h
        else:
            out["body"] = pyview._body(st.body, ctx)
        return out
    finally:
        ctx.inputs, ctx.in_def = set(), False


def _map_node(call: ast.expr, ctx: pyview._Ctx) -> dict[str, Any]:
    if (
        pyview._call_name(call) != "map_node"
        or not isinstance(call, ast.Call)
        or len(call.args) != 1
    ):
        ctx.err(call, '@map_node("<map>", entries=[...], ...) above def main()')
        raise pyview._Bad
    m = call.args[0]
    if pyview._call_name(m) == "map_id":
        ref = pyview._ref(m, ctx)  # type: ignore[arg-type]
    else:
        mid = pyview._const(m, ctx)
        if not isinstance(mid, str):
            ctx.err(m, "map_node(...)'s map is its id, as text")
            raise pyview._Bad
        ref = {"kind": "map", "map": mid}
    out: dict[str, Any] = {"map": ref}
    for k, v in pyview._kw(call).items():
        if k == "entries":
            if not isinstance(v, ast.List | ast.Tuple):
                ctx.err(v, "entries is a list of entry_at(...) / entry_anywhere(...)")
                raise pyview._Bad
            out["entries"] = [pyview._entry(e, ctx) for e in v.elts]
        elif k in ("targets", "ignore"):
            lit = pyview._expr(v, ctx)
            if lit["kind"] != "lit" or not isinstance(lit["value"], list):
                ctx.err(v, f"{k} is a literal list of mob(...)")
                raise pyview._Bad
            out[k] = lit["value"]
        elif k == "resume_here":
            out[k] = pyview._const(v, ctx)
        elif k == "zones":
            out[k] = pyview._zones(v, ctx)
        else:
            ctx.err(v, f"map_node(...) has no argument {k}")
            raise pyview._Bad
    return out


def parse_tab_source(
    source: str,
    *,
    kind: str,
    tab: str,
    functions: set[str],
    variables: set[str],
    what: str = "",
    cat: Catalogue | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One tab's file -> (the tab's JSON, a map node main's map data or None). `functions` /
    `variables`: the names visible on its node BESIDES this file's own (its other tabs', and
    Global's for a node's file). Raises pyview.ParseError (line, col: message)."""
    cat = cat or catalogue()
    what = what or file_path("?", tab)
    tree = _tree(source, what)
    own = _names(tree)
    ctx = _ctx(cat, functions | set(own.functions), variables | set(own.variables))
    try:
        _allow_list(tree, ctx)
        if not ctx.errors and pyview._nesting(tree.body) > pyview.MAX_NESTING + 1:
            ctx.err(tree, f"statements nested deeper than {pyview.MAX_NESTING}")
        if ctx.errors:
            raise pyview.ParseError([f"{what}: {m}" for m in ctx.errors])
        out: dict[str, Any] = {"name": tab, "main": None, "defs": [], "vars": {}}
        map_data: dict[str, Any] | None = None
        for st in tree.body:
            try:
                if isinstance(st, ast.Assign):
                    if len(st.targets) != 1 or not isinstance(st.targets[0], ast.Name):
                        ctx.refuse(st, "this assignment", "a variable is NAME = <a literal>")
                        continue
                    name = st.targets[0].id
                    if name in out["vars"]:
                        ctx.err(st, f"{name} is set twice")
                        continue
                    out["vars"][name] = pyview._literal(st.value, ctx)
                elif isinstance(st, ast.FunctionDef) and st.name == MAIN:
                    if tab != MAIN or kind == "global":
                        ctx.err(st, "def main() is the main tab's program (Global has none)")
                        continue
                    if out["main"] is not None:
                        ctx.err(st, "def main() is written twice")
                        continue
                    if st.args.args or st.args.vararg or st.args.kwarg:
                        ctx.err(st, "def main() takes no inputs")
                        continue
                    deco = st.decorator_list
                    if kind == "map":
                        if len(deco) != 1:
                            ctx.err(st, 'a map node\'s main is @map_node("<map>", entries=[...], '
                                    "...) def main()")  # fmt: skip
                            continue
                        map_data = _map_node(deco[0], ctx)
                    elif deco:
                        ctx.refuse(deco[0], "this decorator", f"a {kind} node's main has none")
                        continue
                    ctx.inputs, ctx.in_def, ctx.loops = set(), False, 0
                    out["main"] = pyview._body(st.body, ctx)
                elif isinstance(st, ast.FunctionDef):
                    out["defs"].append(_def(st, ctx))
                else:
                    ctx.refuse(st, type(st).__name__, "a tab holds variables and defs; the "
                               "program is def main() on the main tab")  # fmt: skip
            except pyview._Bad:
                continue
        if tab == MAIN and kind != "global" and out["main"] is None:
            ctx.err(tree, "the main tab's program: def main(): ... (empty: pass)")
            if kind == "map":
                ctx.err(tree, 'a map node\'s main is @map_node("<map>", entries=[...]) def main()')
    except pyview._Stop:
        pass
    if ctx.errors:
        raise pyview.ParseError([f"{what}: {m}" for m in ctx.errors])
    return out, map_data


def _visible(
    p_nodes: dict[str, Any], node_id: str, skip_tab: str | None
) -> tuple[set[str], set[str]]:
    """(functions, variables) a node's file sees besides its own: its other tabs', and Global's."""
    fns: set[str] = set()
    vs: set[str] = set()
    n = p_nodes[node_id]
    for tab, names in n["names"].items():
        if tab != skip_tab:
            fns |= set(names.functions)
            vs |= set(names.variables)
    if node_id != GLOBAL and GLOBAL in p_nodes:
        for names in p_nodes[GLOBAL]["names"].values():
            fns |= set(names.functions)
            vs |= set(names.variables)
    return fns, vs


def _project_head(source: str, cat: Catalogue, gvars: set[str]) -> dict[str, Any]:
    tree = _tree(source, PROJECT_FILE)
    ctx = _ctx(cat, set(), gvars)
    pyview._allow_list(tree, ctx)
    if ctx.errors:
        raise pyview.ParseError([f"{PROJECT_FILE}: {m}" for m in ctx.errors])
    out: dict[str, Any] = {"format": "poring-lab.project", "version": 3, "nodes": [], "edges": []}
    target: dict[str, Any] = {}
    seen: set[str] = set()
    for st in tree.body:
        try:
            if (
                isinstance(st, ast.Assign)
                and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)
                and (st.targets[0].id in CONFIG or st.targets[0].id in TARGET_CONFIG)
            ):
                name = st.targets[0].id
                if name in seen:
                    ctx.err(st, f"{name} is set twice")
                seen.add(name)
                if name in TARGET_CONFIG:
                    key = TARGET_CONFIG[name]
                    target[key] = pyview._path(st.value, ctx) if key == "path" else (
                        pyview._const(st.value, ctx))  # fmt: skip
                elif name == "STOP_WHEN":
                    out["stop_when"] = pyview._expr(st.value, ctx)
                elif name == "ASSUMES":
                    if not isinstance(st.value, ast.List | ast.Tuple):
                        ctx.err(st.value, "ASSUMES is a list of conditions")
                        continue
                    out["assumes"] = [pyview._expr(e, ctx) for e in st.value.elts]
                else:
                    out[CONFIG[name]] = pyview._const(st.value, ctx)
            elif isinstance(st, ast.Expr) and pyview._call_name(st.value) == "node":
                out["nodes"].append(_node_line(st.value, ctx))  # type: ignore[arg-type]
            elif isinstance(st, ast.Expr) and pyview._call_name(st.value) == "edge":
                out["edges"].append(_edge_line(st.value, ctx))  # type: ignore[arg-type]
            else:
                ctx.refuse(st, type(st).__name__, "project.py holds the Config, node(...) and "
                           "edge(...) lines")  # fmt: skip
        except pyview._Bad:
            continue
    if ctx.errors:
        raise pyview.ParseError([f"{PROJECT_FILE}: {m}" for m in ctx.errors])
    out["target"] = target
    return out


def _node_line(call: ast.Call, ctx: pyview._Ctx) -> dict[str, Any]:
    kw = pyview._kw(call)
    if len(call.args) != 1 or set(kw) != {"kind", "pos", "tabs"}:
        ctx.err(call, 'node("<id>", kind="map", pos=(x, y), tabs=["main", ...])')
        raise pyview._Bad
    node_id, kind = pyview._const(call.args[0], ctx), pyview._const(kw["kind"], ctx)
    pos, tabs = kw["pos"], kw["tabs"]
    if not isinstance(pos, ast.Tuple) or len(pos.elts) != 2 or not isinstance(tabs, ast.List):
        ctx.err(call, 'node("<id>", kind="map", pos=(x, y), tabs=["main", ...])')
        raise pyview._Bad
    x, y = (pyview._const(v, ctx) for v in pos.elts)
    return {"id": node_id, "kind": kind, "pos": {"x": x, "y": y},
            "tabs": [pyview._const(t, ctx) for t in tabs.elts]}  # fmt: skip


def _edge_line(call: ast.Call, ctx: pyview._Ctx) -> dict[str, Any]:
    kw = pyview._kw(call)
    if len(call.args) != 2 or set(kw) - {"entry"}:
        ctx.err(call, 'edge("<from>", "<to>", entry="<entry>")')
        raise pyview._Bad
    out = {"from": pyview._const(call.args[0], ctx), "to": pyview._const(call.args[1], ctx)}
    if "entry" in kw:
        out["entry"] = pyview._const(kw["entry"], ctx)
    return out


def parse_files(files: dict[str, str], cat: Catalogue | None = None) -> Project:
    """Every file (path -> text) -> the project. Raises pyview.ParseError or ProjectError."""
    cat = cat or catalogue()
    if PROJECT_FILE not in files:
        raise pyview.ParseError([f"{PROJECT_FILE}: missing (the Config, nodes and edges)"])
    trees: dict[str, ast.Module] = {}
    for path, text in files.items():
        if path != PROJECT_FILE:
            trees[path] = _tree(text, path)
    # pass 1: the names each node's tabs define (the head's node list says which files exist)
    pre = _project_head_nodes(files[PROJECT_FILE], cat)
    nodes: dict[str, Any] = {}
    for n in pre:
        names = {}
        for tab in n["tabs"]:
            path = file_path(n["id"], tab)
            if path not in trees:
                raise pyview.ParseError([f"{path}: missing (project.py lists the tab)"])
            names[tab] = _names(trees[path])
        nodes[n["id"]] = {"node": n, "names": names}
    extra = sorted(set(trees) - {file_path(n["id"], t) for n in pre for t in n["tabs"]})
    if extra:
        raise pyview.ParseError([f"{extra[0]}: no node in project.py lists this tab"])
    gvars: set[str] = set()
    if GLOBAL in nodes:
        for names in nodes[GLOBAL]["names"].values():
            gvars |= set(names.variables)
    head = _project_head(files[PROJECT_FILE], cat, gvars)
    out_nodes = []
    for n in head["nodes"]:
        tabs = []
        map_data: dict[str, Any] | None = None
        for tab in n["tabs"]:
            path = file_path(n["id"], tab)
            fns, vs = _visible(nodes, n["id"], tab)
            t, md = parse_tab_source(files[path], kind=n["kind"], tab=tab, functions=fns,
                                     variables=vs, what=path, cat=cat)  # fmt: skip
            tabs.append(t)
            map_data = md or map_data
        node = {"id": n["id"], "kind": n["kind"], "pos": n["pos"], "tabs": tabs}
        if n["kind"] == "map":
            if map_data is None:
                where = file_path(n["id"], MAIN)
                raise pyview.ParseError(
                    [f'{where}: a map node\'s main is @map_node("<map>", entries=[...]) def main()']
                )
            node.update(map_data)
        out_nodes.append(node)
    head["nodes"] = out_nodes
    return validate(head)


def _project_head_nodes(source: str, cat: Catalogue) -> list[dict[str, Any]]:
    """project.py's node(...) lines only (pass 1: before Global's variables are known)."""
    tree = _tree(source, PROJECT_FILE)
    ctx = _ctx(cat, set(), set())
    out = []
    for st in tree.body:
        if isinstance(st, ast.Expr) and pyview._call_name(st.value) == "node":
            try:
                out.append(_node_line(st.value, ctx))  # type: ignore[arg-type]
            except pyview._Bad:
                continue
    if ctx.errors:
        raise pyview.ParseError([f"{PROJECT_FILE}: {m}" for m in ctx.errors])
    for n in out:
        if n["kind"] not in KINDS or not isinstance(n["id"], str):
            raise pyview.ParseError([f"{PROJECT_FILE}: node {n['id']!r}: kind is one of "
                                     f"{', '.join(KINDS)}"])  # fmt: skip
    return out


def parse_tab(
    p: Project, node_id: str, tab: str, source: str, cat: Catalogue | None = None
) -> Project:
    """One tab's file edited -> the project with that tab (and a map node main's map data)
    replaced. The node's other tabs and Global give the names it may use."""
    cat = cat or catalogue()
    node = p.node(node_id)
    if node is None or node.tab(tab) is None:
        raise ProjectError([])
    data = dump(p)
    names: dict[str, Any] = {}
    for nd in data["nodes"]:
        names[nd["id"]] = {"node": nd, "names": {
            t["name"]: _Names([d["name"] for d in t["defs"] if d["on"] is None],
                              [d["name"] for d in t["defs"] if d["on"] is not None],
                              list(t["vars"])) for t in nd["tabs"]}}  # fmt: skip
    fns, vs = _visible(names, node_id, tab)
    t, md = parse_tab_source(source, kind=node.kind, tab=tab, functions=fns, variables=vs,
                             what=file_path(node_id, tab), cat=cat)  # fmt: skip
    for nd in data["nodes"]:
        if nd["id"] == node_id:
            nd["tabs"] = [t if x["name"] == tab else x for x in nd["tabs"]]
            if md is not None:
                nd.update(md)
    return validate(json.loads(json.dumps(data)))


def python_doc(p: Project, cat: Catalogue | None = None) -> dict[str, Any]:
    """POST /flows/python's document."""
    from poring_flow.project import shown_hash

    return {"project_hash": shown_hash(p), "files": [f.doc() for f in print_files(p, cat)]}
