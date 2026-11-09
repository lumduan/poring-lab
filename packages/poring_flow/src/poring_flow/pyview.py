"""The Python view: a restricted SUBSET of Python 3.12, PARSED with `ast` and NEVER run (7.2).

- `parse(source)` -> Flow. The source is never executed, compiled to bytecode or imported: it has
  no imports, so it would not even run. `ast.parse` (which builds an AST only) is the single entry
  point. Everything outside the allow-list is refused with its line and column, as
  `line L, col C: <construct> is not allowed in a flow (<why>)` (up to 50 errors).
- `print_flow(flow)` -> the CANONICAL Python. IR -> Python -> IR is identical, and Python -> IR ->
  Python is identical for canonical Python; arbitrary user Python maps to the canonical form.
- Hostile-input limits: 64 KiB, 2,000 lines, bracket depth and indentation pre-checked with
  `tokenize`, at most 5,000 AST nodes and 16 levels of statement nesting. The SUBPROCESS sandbox
  of 7.2 (CPU / memory limits, a timeout) is F3 work and not built here.

Additions to 7.2's allow-list, each needed by 13.6.8's example or by the IR (all reported):
- `map_block(...)` and `extend(...)` decorators, `disable(...)` calls, `overrides=` / `scope=`
  (13.6.8 names these itself);
- `In` / `NotIn` against a literal list or tuple (13.6.8 uses `in`; 7.2 refuses it);
- the bare `_` as a `for` target: `for _ in range(n)` is the `repeat` block (7.2 has no form for
  it);
- `x = block(...)` stores the block's outcome (`outcome_to`, 2.2).
Comments are dropped (open question 12). The printer heads each part with a section comment in
matpilot's style (`# --- Config ---`, Setup, Functions, Map blocks, Events, Main: 2026-11-09,
flows-studio.md section 3); the parser drops them like any comment, so the round trips hold.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any

from poring_flow import ir
from poring_flow.catalogue import CONSTANTS, Catalogue, catalogue

MAX_BYTES = 64 * 1024
MAX_LINES = 2000
MAX_NODES = 5000
MAX_NESTING = 16
MAX_BRACKETS = 32
MAX_ERRORS = 50
LINE = 100
ASCII_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

ALLOWED = (
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.If,
    ast.While,
    ast.For,
    ast.Break,
    ast.Continue,
    ast.Pass,
    ast.FunctionDef,
    ast.Call,
    ast.Name,
    ast.Constant,
    ast.Compare,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.List,
    ast.Tuple,
    ast.keyword,
    ast.arguments,
    ast.Load,
    ast.Store,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.FloorDiv,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)
WHY = {
    "Import": "no imports: the block API is flat names",
    "ImportFrom": "no imports: the block API is flat names",
    "Attribute": "the block API is flat names",
    "Subscript": "no indexing: lists are literal",
    "Slice": "no indexing: lists are literal",
    "Lambda": "no functions as values",
    "ClassDef": "no classes",
    "AsyncFunctionDef": "no async code",
    "Await": "no async code",
    "AsyncWith": "no async code",
    "AsyncFor": "no async code",
    "Yield": "no generators",
    "YieldFrom": "no generators",
    "Return": "procedures return nothing",
    "Global": "variables are flow-global already",
    "Nonlocal": "variables are flow-global already",
    "With": "no context managers",
    "Try": "failures are outcomes, not exceptions",
    "TryStar": "failures are outcomes, not exceptions",
    "Raise": "use stop(reason)",
    "Assert": "use stop(reason) or assumes",
    "Delete": "variables live for the whole run",
    "Match": "use if / elif",
    "TypeAlias": "no types",
    "AnnAssign": "no annotations",
    "NamedExpr": "no assignment inside an expression",
    "IfExp": "use an if statement",
    "ListComp": "no comprehensions",
    "SetComp": "no comprehensions",
    "DictComp": "no comprehensions",
    "GeneratorExp": "no comprehensions",
    "JoinedStr": "no f-strings: text is never built",
    "FormattedValue": "no f-strings: text is never built",
    "Starred": "arguments are listed one by one",
    "Dict": "no dictionaries",
    "Set": "no sets",
    "Pow": "only + - * // %",
    "MatMult": "only + - * // %",
    "Div": "use // (whole numbers)",
    "BitAnd": "no bit operators",
    "BitOr": "no bit operators",
    "BitXor": "no bit operators",
    "LShift": "no shift operators",
    "RShift": "no shift operators",
    "Invert": "no bit operators",
    "UAdd": "write the number",
    "Is": "use == or !=",
    "IsNot": "use == or !=",
}


class ParseError(ValueError):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = messages


def _at(node: ast.AST) -> str:
    return f"line {getattr(node, 'lineno', 0)}, col {getattr(node, 'col_offset', -1) + 1}"


class _Stop(Exception):
    """Raised once MAX_ERRORS is reached."""


@dataclass
class _Ctx:
    cat: Catalogue
    errors: list[str] = field(default_factory=list)
    variables: dict[str, ir.Lit] = field(default_factory=dict)
    procedures: set[str] = field(default_factory=set)
    handlers: set[str] = field(default_factory=set)  # global handler names (the event keys)
    blocks: set[str] = field(default_factory=set)
    in_block: bool = False
    loops: int = 0

    def err(self, node: ast.AST, msg: str) -> None:
        self.errors.append(f"{_at(node)}: {msg}")
        if len(self.errors) >= MAX_ERRORS:
            raise _Stop

    def refuse(self, node: ast.AST, construct: str, why: str) -> None:
        self.err(node, f"{construct} is not allowed in a flow ({why})")


class _Bad(Exception):
    """A construct already reported: abandon this subtree."""


# --- pre-checks ---------------------------------------------------------------------------------
def _precheck(source: str) -> list[str]:
    size = len(source.encode("utf-8"))
    if size > MAX_BYTES:
        return [f"line 1, col 1: the source is {size} bytes; at most {MAX_BYTES}"]
    lines = source.count("\n") + 1
    if lines > MAX_LINES:
        return [f"line {MAX_LINES + 1}, col 1: the source has {lines} lines; at most {MAX_LINES}"]
    depth = indent = 0
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.NAME and not tok.string.isascii():
                # ast.parse NFKC-normalises identifiers, so a look-alike would alias a catalogue
                # name AFTER parsing: refuse it on the raw token (7.2)
                return [
                    f"line {tok.start[0]}, col {tok.start[1] + 1}: name {tok.string!r} is not "
                    "allowed in a flow (names are ASCII only)"
                ]
            if tok.type == tokenize.OP and tok.string in "([{":
                depth += 1
                if depth > MAX_BRACKETS:
                    return [
                        f"line {tok.start[0]}, col {tok.start[1] + 1}: brackets nested "
                        f"deeper than {MAX_BRACKETS}"
                    ]
            elif tok.type == tokenize.OP and tok.string in ")]}":
                depth -= 1
            elif tok.type == tokenize.INDENT:
                indent += 1
                if indent > MAX_NESTING:
                    return [
                        f"line {tok.start[0]}, col 1: statements nested deeper than {MAX_NESTING}"
                    ]
            elif tok.type == tokenize.DEDENT:
                indent -= 1
    except (tokenize.TokenError, IndentationError, SyntaxError) as e:
        return [f"line 1, col 1: the source does not tokenize ({type(e).__name__})"]
    return []


def _allow_list(tree: ast.Module, ctx: _Ctx) -> None:
    """Refuse every node type outside the allow-list, and the literal / name rules."""
    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > MAX_NODES:
            ctx.err(tree, f"more than {MAX_NODES} syntax nodes")
            return
        name = type(node).__name__
        if not isinstance(node, ALLOWED):
            ctx.refuse(node, name, WHY.get(name, "not in the allow-list"))
            continue
        if isinstance(node, ast.Name) and node.id.startswith("_") and node.id != "_":
            ctx.refuse(node, f"name {node.id}", "a name starting with _ is refused")
        elif isinstance(node, ast.Name) and not (node.id == "_" or ASCII_NAME.match(node.id)):
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
        elif isinstance(node, ast.FunctionDef):
            a = node.args
            if a.args or a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg or a.defaults:
                ctx.refuse(node, f"def {node.name} with arguments", "procedures take none")
            if node.returns is not None or getattr(node, "type_params", []):
                ctx.refuse(node, f"def {node.name} with annotations", "no annotations")
        elif isinstance(node, ast.While | ast.For) and node.orelse:
            ctx.refuse(node, f"{type(node).__name__.lower()}...else", "loops have no else")


def _nesting(stmts: list[ast.stmt], depth: int = 1) -> int:
    deepest = depth if stmts else depth - 1
    for s in stmts:
        for body in (getattr(s, "body", None), getattr(s, "orelse", None)):
            if isinstance(body, list) and body and isinstance(body[0], ast.stmt):
                deepest = max(deepest, _nesting(body, depth + 1))
    return deepest


# --- the parser ---------------------------------------------------------------------------------
# Python-import ALIASES (Batt 2026-10-09, ADR-0020 contradictions #7): an old name imports as the
# one block, with a warning; the IR, the catalogue and every printed view know only the new name.
ALIASES = {"close_npc_dialog": "close_dialog"}


class AliasWarning(UserWarning):
    """A Python view used an alias name: it was imported as the one block (ALIASES)."""


def _aliases(tree: ast.Module) -> list[str]:
    """Rename every call to an alias in place (the AST is only read, never run); one warning per
    call, by line and column."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            new = ALIASES.get(node.func.id)
            if new is not None:
                out.append(
                    f"{_at(node)}: {node.func.id}() is an alias of {new}(): imported as {new}"
                )
                node.func.id = new
    return out


def parse(source: str, cat: Catalogue | None = None, warnings: list[str] | None = None) -> ir.Flow:
    """Restricted Python -> the flow IR. Never runs the source. Warnings (an alias name, #7) are
    appended to `warnings` when given, else issued as `AliasWarning`s."""
    pre = _precheck(source)
    if pre:
        raise ParseError(pre)
    try:
        tree = ast.parse(source, mode="exec", type_comments=False)
    except SyntaxError as e:
        msg = f"line {e.lineno or 0}, col {e.offset or 0}: syntax error ({e.msg})"
        raise ParseError([msg]) from None
    except (RecursionError, MemoryError, ValueError) as e:
        msg = f"line 1, col 1: the source cannot be parsed ({type(e).__name__})"
        raise ParseError([msg]) from None
    alias_warnings = _aliases(tree)
    if warnings is not None:
        warnings.extend(alias_warnings)
    else:
        import warnings as py_warnings

        for w in alias_warnings:
            py_warnings.warn(w, AliasWarning, stacklevel=2)
    ctx = _Ctx(cat or catalogue())
    try:
        _allow_list(tree, ctx)
        if not ctx.errors and _nesting(tree.body) > MAX_NESTING + 1:
            ctx.err(tree, f"statements nested deeper than {MAX_NESTING}")
        if ctx.errors:
            raise ParseError(ctx.errors)
        data = _module(tree, ctx)
    except _Stop:
        raise ParseError(ctx.errors) from None
    if ctx.errors or data is None:
        raise ParseError(ctx.errors or ["line 1, col 1: no flow(...)"])
    try:
        return ir.validate(data)
    except ir.FlowError as e:
        raise ParseError(e.messages) from None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _kw(call: ast.Call) -> dict[str, ast.expr]:
    return {k.arg: k.value for k in call.keywords if k.arg is not None}


def _module(tree: ast.Module, ctx: _Ctx) -> dict[str, Any] | None:
    body = list(tree.body)
    doc: str | None = None
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and (isinstance(body[0].value.value, str))
    ):
        doc = body[0].value.value
        body = body[1:]
    first = body[0] if body else None
    config = _config_run(body)
    if config:
        rest = body[len(config) :]
    elif (
        not isinstance(first, ast.Expr)
        or not isinstance(first.value, ast.Call)
        or (_call_name(first.value) != "flow")
    ):
        ctx.err(first or tree, "the flow starts with its Config (FLOW_NAME = ...) or flow(...)")
        return None
    else:
        rest = body[1:]
    names = ctx.cat.names()

    # pass 1: the names every body may refer to
    defined: dict[str, str] = {}
    for st in rest:
        if isinstance(st, ast.FunctionDef):
            if st.name in names:
                ctx.err(st, f"def {st.name} shadows a catalogue name")
            if st.name in defined:
                ctx.err(st, f"{st.name} is defined twice")
            deco = st.decorator_list
            kind = "procedure"
            if len(deco) > 1:
                ctx.refuse(st, f"def {st.name} with {len(deco)} decorators", "at most one")
                continue
            if deco:
                dname = _call_name(deco[0])
                if dname not in ("on", "map_block", "extend"):
                    ctx.refuse(
                        deco[0], "this decorator", "only on(...), map_block(...), extend(...)"
                    )
                    continue
                kind = {"on": "handler", "map_block": "block", "extend": "extend"}[dname]
                if kind == "handler" and "scope" in _kw(deco[0]):  # type: ignore[arg-type]
                    kind = "map_handler"
            defined[st.name] = kind
    ctx.procedures = {n for n, k in defined.items() if k == "procedure"}
    ctx.handlers = {n for n, k in defined.items() if k == "handler"}
    ctx.blocks = {n for n, k in defined.items() if k == "block"}

    out: dict[str, Any] = {}
    # a bad head value is recorded (ctx.err): parse() raises ParseError with it
    with contextlib.suppress(_Bad):
        if config:
            _config_head(config, ctx, out, doc)
        else:
            _flow_head(first.value, ctx, out, doc)  # type: ignore[union-attr]
    procedures: dict[str, Any] = {}
    handlers: list[Any] = []
    blocks: dict[str, dict[str, Any]] = {}
    main: list[Any] = []
    pending_events: list[tuple[str, dict[str, Any]]] = []
    for st in rest:
        try:
            if isinstance(st, ast.Assign) and not main and _is_decl(st, ctx):
                name = st.targets[0].id  # type: ignore[attr-defined]
                if name in names or name in defined:
                    ctx.err(st, f"{name} shadows a catalogue or definition name")
                ctx.variables[name] = ir.Lit.model_validate(_literal(st.value, ctx))
            elif isinstance(st, ast.FunctionDef):
                dkind = defined.get(st.name)
                if dkind == "procedure":
                    procedures[st.name] = _body(st.body, ctx)
                elif dkind == "handler":
                    handlers.append(_handler(st, ctx, scoped=False)[1])
                elif dkind == "map_handler":
                    pending_events.append(_handler(st, ctx, scoped=True))
                elif dkind == "block":
                    blocks[st.name] = _map_block(st, ctx)
                elif dkind == "extend":
                    pending_events.append(_extend(st, ctx))
            elif isinstance(st, ast.Expr) and _call_name(st.value) == "disable":
                pending_events.append(_disable(st.value, ctx))  # type: ignore[arg-type]
            else:
                main.extend(_body([st], ctx))
        except _Bad:
            continue
    for scope, ev in pending_events:
        if scope in blocks:
            blocks[scope].setdefault("events", []).append(ev)
    out["variables"] = {k: v.model_dump(mode="json") for k, v in ctx.variables.items()}
    out["procedures"] = procedures
    out["handlers"] = handlers
    workflow = out.pop("_workflow", None)
    if blocks or workflow:
        if main:
            ctx.err(rest[0], "a flow has exactly one of main statements and map blocks")
        out["workflow"] = {**(workflow or {}), "blocks": list(blocks.values())}
    else:
        out["main"] = main
    return out


def _is_decl(st: ast.Assign, ctx: _Ctx) -> bool:
    """A top-level `NAME = <literal>` of a NEW name, before any main statement: a variable."""
    if len(st.targets) != 1 or not isinstance(st.targets[0], ast.Name):
        return False
    if st.targets[0].id in ctx.variables:
        return False
    return _call_name(st.value) not in set(ctx.cat.blocks) | {"wait_until", "wait"}


# The Config constants (2026-11-09, flows-studio.md section 3): the flow's head as a real program's
# settings, one per line, in place of the flow(...) call (which is still read). CONSTANT -> the
# flow(...) argument; CLIENT / SERVER / LOCALE / PATH are target(...)'s.
CONFIG = {
    "FLOW_NAME": "name",
    "DESCRIPTION": "description",
    "IR_VERSION": "ir",
    "MAX_RUNTIME_S": "max_runtime_s",
    "WHERE_BUDGET": "where_budget",
    "RUN_UNTIL_STOPPED": "run_until_stopped",
    "START": "start",
    "STOP_WHEN": "stop_when",
    "ASSUMES": "assumes",
}
TARGET_CONFIG = {"CLIENT": "client", "SERVER": "server", "LOCALE": "locale", "PATH": "path"}


def _config_run(body: list[ast.stmt]) -> list[ast.Assign]:
    """The leading `CONSTANT = value` statements of a Config head (empty: a flow(...) head)."""
    run: list[ast.Assign] = []
    for st in body:
        if (
            isinstance(st, ast.Assign)
            and len(st.targets) == 1
            and isinstance(st.targets[0], ast.Name)
            and (st.targets[0].id in CONFIG or st.targets[0].id in TARGET_CONFIG)
        ):
            run.append(st)
        else:
            break
    return run


def _config_head(run: list[ast.Assign], ctx: _Ctx, out: dict[str, Any], doc: str | None) -> None:
    kw: dict[str, ast.expr] = {}
    tkw: dict[str, ast.expr] = {}
    for st in run:
        name = st.targets[0].id  # type: ignore[attr-defined]
        into, key = (kw, CONFIG[name]) if name in CONFIG else (tkw, TARGET_CONFIG[name])
        if key in into:
            ctx.err(st, f"{name} is set twice")
        into[key] = st.value
    _head(kw, tkw if tkw else None, run[0], ctx, out, doc)


def _flow_head(call: ast.Call, ctx: _Ctx, out: dict[str, Any], doc: str | None) -> None:
    if call.args:
        ctx.err(call, "flow(...) takes keyword arguments only")
    kw = _kw(call)
    tkw: dict[str, ast.expr] | None = None
    if "target" in kw:
        t = kw.pop("target")
        if _call_name(t) != "target" or t.args:  # type: ignore[attr-defined]
            ctx.err(t, "target=target(client=..., server=..., locale=..., path=S2)")
        else:
            tkw = _kw(t)  # type: ignore[arg-type]
    _head(kw, tkw, call, ctx, out, doc)


def _head(
    kw: dict[str, ast.expr],
    tkw: dict[str, ast.expr] | None,
    where: ast.AST,
    ctx: _Ctx,
    out: dict[str, Any],
    doc: str | None,
) -> None:
    """The flow's head from its arguments (flow(...) or the Config constants: the same IR)."""
    allowed = {
        "ir",
        "name",
        "description",
        "max_runtime_s",
        "where_budget",
        "target",
        "assumes",
        "stop_when",
        "run_until_stopped",
        "start",
    }
    for k in kw:
        if k not in allowed:
            ctx.err(kw[k], f"flow(...) has no argument {k}")
    for k in ("ir", "name", "max_runtime_s", "where_budget"):
        if k in kw:
            out[k] = _const(kw[k], ctx)
    if "description" in kw:
        out["description"] = _const(kw["description"], ctx)
    elif doc is not None:
        out["description"] = doc
    if tkw is not None:
        tgt = {k: _const(v, ctx) for k, v in tkw.items() if k != "path"}
        if "path" in tkw:
            tgt["path"] = _path(tkw["path"], ctx)
        out["target"] = tgt
    if "assumes" in kw:
        a = kw["assumes"]
        if not isinstance(a, ast.List | ast.Tuple):
            ctx.err(a, "assumes is a list of conditions")
        else:
            out["assumes"] = [_expr_or_skip(e, ctx) for e in a.elts]
    if "stop_when" in kw:
        out["stop_when"] = _expr_or_skip(kw["stop_when"], ctx)
    wf: dict[str, Any] = {}
    if "start" in kw:
        b, e = _start(kw["start"], ctx)
        wf["start_block"], wf["start_entry"] = b, e
    if "run_until_stopped" in kw:
        wf["run_until_stopped"] = _const(kw["run_until_stopped"], ctx)
    if wf:
        out["_workflow"] = wf


def _expr_or_skip(node: ast.expr, ctx: _Ctx) -> Any:
    try:
        return _expr(node, ctx)
    except _Bad:
        return {"kind": "lit", "value": False}


def _const(node: ast.expr, ctx: _Ctx) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int | float)
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    ctx.err(node, "a constant (a number, text, True or False) is needed here")
    raise _Bad


def _path(node: ast.expr, ctx: _Ctx) -> str:
    """The target's path: the text "S2" / "RDP" (the Config constant, a plain Python string since
    2026-11-09), or the bare name S2 / RDP (flow(...) and older text)."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in ("S2", "RDP")
    ):
        return CONSTANTS[node.value]
    return _constant(node, ctx, ("S2", "RDP"))


def _start(node: ast.expr, ctx: _Ctx) -> tuple[str, str]:
    """The workflow's start: ("block", "entry") (the Config constant, a plain Python tuple since
    2026-11-09), or entry("block", "entry") (flow(...) and older text)."""
    if isinstance(node, ast.Tuple | ast.List):
        parts = node.elts
        if len(parts) == 2 and all(
            isinstance(x, ast.Constant) and isinstance(x.value, str) for x in parts
        ):
            return parts[0].value, parts[1].value  # type: ignore[attr-defined]
        ctx.err(node, 'START = ("block", "entry") is needed here')
        raise _Bad
    return _entry_ref(node, ctx)


def _constant(node: ast.expr, ctx: _Ctx, allowed: tuple[str, ...]) -> str:
    if isinstance(node, ast.Name) and node.id in allowed:
        return CONSTANTS[node.id]
    ctx.err(node, f"one of {', '.join(allowed)} is needed here")
    raise _Bad


def _name_arg(node: ast.expr, ctx: _Ctx, what: str) -> str:
    if isinstance(node, ast.Name) and ASCII_NAME.match(node.id):
        return node.id
    ctx.err(node, f"{what} is a plain name here")
    raise _Bad


# --- references and literals ----------------------------------------------------------------------
REF_ARGS = {
    "cell": (("map", str), ("x", int), ("y", int)),
    "npc": (("key", str),),
    "option": (("key", str),),
    "item": (("id", int),),
    "mob": (("id", int),),
    "skill": (("id", int), ("level", int)),
    "map_id": (("map", str),),
    "window": (("name", str),),
}
REF_KIND = {"map_id": "map"}


def _ref(call: ast.Call, ctx: _Ctx) -> dict[str, Any]:
    name = call.func.id  # type: ignore[attr-defined]
    spec = REF_ARGS[name]
    vals: dict[str, Any] = {}
    if len(call.args) > len(spec):
        ctx.err(call, f"{name}(...) takes {len(spec)} arguments")
        raise _Bad
    for (pname, _), node in zip(spec, call.args, strict=False):
        vals[pname] = _const(node, ctx)
    for k, node in _kw(call).items():
        if k not in dict(spec) or k in vals:
            ctx.err(node, f"{name}(...) has no argument {k} here")
            raise _Bad
        vals[k] = _const(node, ctx)
    for pname, typ in spec:
        if pname in vals and not (
            isinstance(vals[pname], typ) and not isinstance(vals[pname], bool)
        ):
            ctx.err(call, f"{name}(...): {pname} is a {typ.__name__}")
            raise _Bad
    return {"kind": REF_KIND.get(name, name), **vals}


def _literal(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    """A variable's initial value: a constant, a reference, or a list of references."""
    if isinstance(node, ast.List | ast.Tuple):
        refs = []
        for e in node.elts:
            if _call_name(e) not in REF_ARGS:
                ctx.err(e, "a list variable holds references (cell, npc, item, mob, ...)")
                raise _Bad
            refs.append(_ref(e, ctx))  # type: ignore[arg-type]
        return {"kind": "lit", "value": refs}
    if _call_name(node) in REF_ARGS:
        return {"kind": "lit", "value": _ref(node, ctx)}  # type: ignore[arg-type]
    return {"kind": "lit", "value": _const(node, ctx)}


# --- expressions --------------------------------------------------------------------------------
CMP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.In: "in",
    ast.NotIn: "not in",
}
ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.FloorDiv: "//", ast.Mod: "%"}
OUTCOME_CONSTANTS = ("OK", "FAILED", "UNSUPPORTED", "INTERRUPTED", "REFUSED")


def _expr(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    if isinstance(node, ast.Constant):
        if node.value is None:
            ctx.err(node, "None is not a value here")
            raise _Bad
        return {"kind": "lit", "value": node.value}
    if isinstance(node, ast.Name):
        if node.id in OUTCOME_CONSTANTS:
            return {"kind": "outcome", "value": CONSTANTS[node.id]}
        if node.id in ctx.variables:
            return {"kind": "var", "name": node.id}
        ctx.err(node, f"{node.id} is not a flow variable")
        raise _Bad
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return {"kind": "not", "term": _expr(node.operand, ctx)}
        if (
            isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, int | float)
            and (not isinstance(node.operand.value, bool))
        ):
            return {"kind": "lit", "value": -node.operand.value}
        return {
            "kind": "arith",
            "op": "-",
            "left": {"kind": "lit", "value": 0},
            "right": _expr(node.operand, ctx),
        }
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        return {"kind": op, "terms": [_expr(v, ctx) for v in node.values]}
    if isinstance(node, ast.Compare):
        parts = [node.left, *node.comparators]
        cmps = []
        for i, cop in enumerate(node.ops):
            sym = CMP[type(cop)]
            right = parts[i + 1]
            if sym in ("in", "not in") and not isinstance(right, ast.List | ast.Tuple | ast.Name):
                ctx.err(right, f"{sym} needs a literal list or a list variable")
                raise _Bad
            cmps.append(
                {"kind": "cmp", "op": sym, "left": _expr(parts[i], ctx), "right": _expr(right, ctx)}
            )
        return cmps[0] if len(cmps) == 1 else {"kind": "and", "terms": cmps}
    if isinstance(node, ast.BinOp):
        return {
            "kind": "arith",
            "op": ARITH[type(node.op)],
            "left": _expr(node.left, ctx),
            "right": _expr(node.right, ctx),
        }
    if isinstance(node, ast.List | ast.Tuple):
        items = [_expr(e, ctx) for e in node.elts]
        if items and all(i["kind"] == "lit" and isinstance(i["value"], dict) for i in items):
            return {"kind": "lit", "value": [i["value"] for i in items]}
        if not items:
            return {"kind": "lit", "value": []}
        return {"kind": "list", "items": items}
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name in REF_ARGS:
            return {"kind": "lit", "value": _ref(node, ctx)}
        if name == "known":
            if len(node.args) != 1 or node.keywords:
                ctx.err(node, "known(...) takes one value")
                raise _Bad
            return {"kind": "sense", "sensor": "known", "args": {"value": _expr(node.args[0], ctx)}}
        if name in ctx.cat.sensors:
            params = ctx.cat.sensors[name].spec.params
            return {"kind": "sense", "sensor": name, "args": _args(node, params, name, ctx)}
        if name in ctx.cat.blocks:
            action = _action(node, ctx)
            return {"kind": "do", "action": action}
        ctx.err(node, f"{name}(...) is not a sensor, a block or a reference")
        raise _Bad
    ctx.refuse(node, type(node).__name__, "not an expression a flow can hold")
    raise _Bad


def _args(
    call: ast.Call, params: Any, name: str, ctx: _Ctx, extra: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Positional and keyword arguments matched to a catalogue signature."""
    out: dict[str, Any] = {}
    positional = [p for p in params if p.positional]
    if len(call.args) > len(positional):
        ctx.err(call, f"{name}(...) takes at most {len(positional)} positional arguments")
        raise _Bad
    for p, node in zip(positional, call.args, strict=False):
        out[p.name] = _expr(node, ctx)
    known = {p.name for p in params}
    for k, node in _kw(call).items():
        if k in extra:
            continue
        if k not in known:
            ctx.err(node, f"{name}(...) has no parameter {k}")
            raise _Bad
        if k in out:
            ctx.err(node, f"{name}(...) got {k} twice")
            raise _Bad
        out[k] = _expr(node, ctx)
    missing = [p.name for p in params if p.required and p.name not in out]
    if missing:
        ctx.err(call, f"{name}(...) needs {', '.join(missing)}")
        raise _Bad
    return out


def _action(call: ast.Call, ctx: _Ctx, outcome_to: str | None = None) -> dict[str, Any]:
    name = call.func.id  # type: ignore[attr-defined]
    spec = ctx.cat.blocks[name].spec
    params = _args(call, spec.params, name, ctx, extra=("timeout_s", "on_fail", "note"))
    kw = _kw(call)
    out: dict[str, Any] = {
        "kind": "action",
        "block": name,
        "concept": spec.concept,
        "params": params,
        "timeout_s": spec.timeout_s,
    }
    if "timeout_s" in kw:
        out["timeout_s"] = _const(kw["timeout_s"], ctx)
    if "on_fail" in kw:
        out["on_fail"] = _constant(kw["on_fail"], ctx, ("STOP", "CONTINUE"))
    if "note" in kw:
        out["note"] = _const(kw["note"], ctx)
    if outcome_to:
        out["outcome_to"] = outcome_to
    return out


# --- statements ---------------------------------------------------------------------------------
def _body(stmts: list[ast.stmt], ctx: _Ctx) -> list[Any]:
    out: list[Any] = []
    for st in stmts:
        try:
            out.extend(_stmt(st, ctx))
        except _Bad:
            continue
    return out


def _stmt(st: ast.stmt, ctx: _Ctx) -> list[Any]:
    if isinstance(st, ast.Pass):
        return []
    if isinstance(st, ast.Break | ast.Continue):
        if not ctx.loops:
            ctx.err(st, f"{type(st).__name__.lower()} outside a loop")
            raise _Bad
        return [{"kind": "break" if isinstance(st, ast.Break) else "continue"}]
    if isinstance(st, ast.Expr):
        return [_call_stmt(st.value, ctx)]
    if isinstance(st, ast.Assign):
        if len(st.targets) != 1 or not isinstance(st.targets[0], ast.Name):
            ctx.refuse(st, "this assignment", "exactly one plain name on the left")
            raise _Bad
        name = st.targets[0].id
        if name not in ctx.variables:
            ctx.err(st, f"{name} is not a flow variable: declare it at the top with its value")
            raise _Bad
        cname = _call_name(st.value)
        if cname in ctx.cat.blocks:
            return [_action(st.value, ctx, outcome_to=name)]  # type: ignore[arg-type]
        if cname == "wait_until":
            return [_wait_until(st.value, ctx, outcome_to=name)]  # type: ignore[arg-type]
        if cname == "wait":
            ctx.err(st, f"wait(seconds) has no outcome: {name} = wait_until(False, timeout_s=...)")
            raise _Bad
        return [{"kind": "set", "var": name, "value": _expr(st.value, ctx)}]
    if isinstance(st, ast.AugAssign):
        if not isinstance(st.target, ast.Name) or type(st.op) not in (ast.Add, ast.Sub):
            ctx.refuse(st, "this augmented assignment", "only name += value or name -= value")
            raise _Bad
        name = st.target.id
        if name not in ctx.variables:
            ctx.err(st, f"{name} is not a flow variable")
            raise _Bad
        op = ARITH[type(st.op)]
        return [
            {
                "kind": "set",
                "var": name,
                "value": {
                    "kind": "arith",
                    "op": op,
                    "left": {"kind": "var", "name": name},
                    "right": _expr(st.value, ctx),
                },
            }
        ]
    if isinstance(st, ast.If):
        return [
            {
                "kind": "if",
                "cond": _expr(st.test, ctx),
                "then": _body(st.body, ctx),
                "orelse": _body(st.orelse, ctx),
            }
        ]
    if isinstance(st, ast.While):
        test = st.test
        out: dict[str, Any] = {"kind": "while"}
        if _call_name(test) == "bounded":
            call: ast.Call = test  # type: ignore[assignment]
            if len(call.args) != 1:
                ctx.err(call, "bounded(cond, max_iter=..., max_s=...)")
                raise _Bad
            for k, v in _kw(call).items():
                if k not in ("max_iter", "max_s"):
                    ctx.err(v, f"bounded(...) has no argument {k}")
                    raise _Bad
                out[k] = _const(v, ctx)
            test = call.args[0]
        out["cond"] = _expr(test, ctx)
        ctx.loops += 1
        try:
            out["body"] = _body(st.body, ctx)
        finally:
            ctx.loops -= 1
        return [out]
    if isinstance(st, ast.For):
        return [_for(st, ctx)]
    if isinstance(st, ast.FunctionDef):
        ctx.refuse(st, f"def {st.name} here", "procedures and events are top level only")
        raise _Bad
    ctx.refuse(st, type(st).__name__, "not a flow statement")
    raise _Bad


def _for(st: ast.For, ctx: _Ctx) -> dict[str, Any]:
    if not isinstance(st.target, ast.Name):
        ctx.refuse(st.target, "this loop target", "a plain name")
        raise _Bad
    it = st.iter
    ctx.loops += 1
    try:
        body = _body(st.body, ctx)
    finally:
        ctx.loops -= 1
    if st.target.id == "_":
        if _call_name(it) != "range" or len(it.args) != 1 or it.keywords:  # type: ignore[attr-defined]
            ctx.err(st, "for _ in range(n) is the repeat block: one argument")
            raise _Bad
        return {"kind": "repeat", "times": _expr(it.args[0], ctx), "body": body}  # type: ignore[attr-defined]
    var = st.target.id
    if var not in ctx.variables:
        ctx.err(st.target, f"{var} is not a flow variable: declare it at the top with its value")
        raise _Bad
    if _call_name(it) == "range":
        call: ast.Call = it  # type: ignore[assignment]
        args = [_expr(a, ctx) for a in call.args]
        if not 1 <= len(args) <= 3 or call.keywords:
            ctx.err(call, "range(...) takes 1 to 3 arguments")
            raise _Bad
        zero, one = {"kind": "lit", "value": 0}, {"kind": "lit", "value": 1}
        start, stop, step = (
            (zero, args[0], one)
            if len(args) == 1
            else ((args[0], args[1], one) if len(args) == 2 else tuple(args))
        )
        items: dict[str, Any] = {"kind": "range", "start": start, "stop": stop, "step": step}
    elif isinstance(it, ast.List | ast.Tuple | ast.Name):
        items = _expr(it, ctx)
        if items["kind"] not in ("lit", "var"):
            ctx.err(it, "for ... in: a range, a literal list of references, or a list variable")
            raise _Bad
    else:
        ctx.err(it, "for ... in: a range, a literal list of references, or a list variable")
        raise _Bad
    return {"kind": "for", "var": var, "items": items, "body": body}


def _call_stmt(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    name = _call_name(node)
    if name is None:
        ctx.refuse(node, type(node).__name__, "a statement is a call to a block or a procedure")
        raise _Bad
    call: ast.Call = node  # type: ignore[assignment]
    if name in ctx.cat.blocks:
        return _action(call, ctx)
    if name == "wait_until":
        return _wait_until(call, ctx)
    if name == "wait":
        return _wait(call, ctx)
    if name == "stop":
        if len(call.args) != 1 or call.keywords:
            ctx.err(call, 'stop("reason") takes one reason')
            raise _Bad
        return {"kind": "stop", "reason": _const(call.args[0], ctx)}
    if name == "take_exit":
        if len(call.args) != 1 or call.keywords:
            ctx.err(call, "take_exit(...) takes one exit")
            raise _Bad
        return {"kind": "take_exit", "exit": _exit(call.args[0], ctx)}
    if name in ctx.procedures:
        if call.args or call.keywords:
            ctx.err(call, f"{name}() takes no arguments")
            raise _Bad
        return {"kind": "call", "proc": name}
    if name in ctx.cat.sensors:
        ctx.err(call, f"{name}() is a sensor: use it in a condition")
        raise _Bad
    ctx.err(call, f"{name}(...) is not a block, a procedure or a flow statement")
    raise _Bad


def _wait(call: ast.Call, ctx: _Ctx) -> dict[str, Any]:
    """`wait(seconds)`: the "wait N seconds" block, the printer's form of
    `wait_until(False, timeout_s=N)` (the same IR)."""
    arg = call.args[0] if len(call.args) == 1 and not call.keywords else None
    secs = arg.value if isinstance(arg, ast.Constant) else None
    if isinstance(secs, bool) or not isinstance(secs, int | float):
        ctx.err(call, "wait(seconds) takes one number of seconds, e.g. wait(1)")
        raise _Bad
    return {"kind": "wait_until", "cond": {"kind": "lit", "value": False}, "timeout_s": secs}


def _wait_until(call: ast.Call, ctx: _Ctx, outcome_to: str | None = None) -> dict[str, Any]:
    kw = _kw(call)
    if len(call.args) != 1 or "timeout_s" not in kw or set(kw) - {"timeout_s"}:
        ctx.err(call, "wait_until(cond, timeout_s=...) needs its timeout")
        raise _Bad
    out = {
        "kind": "wait_until",
        "cond": _expr(call.args[0], ctx),
        "timeout_s": _const(kw["timeout_s"], ctx),
    }
    if outcome_to:
        out["outcome_to"] = outcome_to
    return out


def _entry_ref(node: ast.expr, ctx: _Ctx) -> tuple[str, str]:
    if _call_name(node) != "entry" or len(node.args) != 2 or node.keywords:  # type: ignore[attr-defined]
        ctx.err(node, 'entry("block", "entry") is needed here')
        raise _Bad
    b, e = (_const(a, ctx) for a in node.args)  # type: ignore[attr-defined]
    return str(b), str(e)


def _exit(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    name = _call_name(node)
    if name not in ("walk_exit", "npc_warp", "item_warp"):
        ctx.err(node, "take_exit(walk_exit(...) | npc_warp(...) | item_warp(...))")
        raise _Bad
    call: ast.Call = node  # type: ignore[assignment]
    kw = _kw(call)
    if "to" not in kw:
        ctx.err(call, f'{name}(...) needs to=entry("block", "entry")')
        raise _Bad
    for k in kw:
        if k not in ("to", "timeout_s"):
            ctx.err(kw[k], f"{name}(...) has no argument {k}")
            raise _Bad
    b, e = _entry_ref(kw["to"], ctx)
    out: dict[str, Any] = {"kind": name, "to_block": b, "to_entry": e}
    if "timeout_s" in kw:
        out["timeout_s"] = _const(kw["timeout_s"], ctx)
    need = {"walk_exit": 1, "npc_warp": 2, "item_warp": 1}[name]
    if len(call.args) != need:
        ctx.err(call, f"{name}(...) takes {need} positional argument(s)")
        raise _Bad
    first = _expr(call.args[0], ctx)
    if name == "walk_exit":
        out["warp"] = first.get("value") if first["kind"] == "lit" else None
    elif name == "npc_warp":
        out["npc"] = first.get("value") if first["kind"] == "lit" else None
        opts = _expr(call.args[1], ctx)
        out["options"] = opts.get("value") if opts["kind"] == "lit" else None
    else:
        out["item"] = first.get("value") if first["kind"] == "lit" else first
    return out


# --- definitions --------------------------------------------------------------------------------
HANDLER_KW = (
    "until",
    "rearm",
    "priority",
    "rank",  # IR 2 (#13): the rank inside the class; left out = 13.6.3's table order
    "mode",
    "then",
    "escalate",
    "max_insert_fails",
    "cooldown_s",
    "max_per_min",
    "max_fires_per_10min",
    "max_per_run",
    "overrides",
    "key",
    "scope",
)


def _handler(fn: ast.FunctionDef, ctx: _Ctx, scoped: bool) -> tuple[str, dict[str, Any]]:
    deco: ast.Call = fn.decorator_list[0]  # type: ignore[assignment]
    if len(deco.args) != 1:
        ctx.err(deco, "on(condition, priority=..., ...) takes one condition")
        raise _Bad
    kw = _kw(deco)
    h: dict[str, Any] = {"when": _expr(deco.args[0], ctx)}
    for k, v in kw.items():
        if k not in HANDLER_KW:
            ctx.err(v, f"on(...) has no argument {k}")
            raise _Bad
        if k in ("until", "rearm"):
            h[k] = _expr(v, ctx)
        elif k == "priority":
            h[k] = _constant(v, ctx, ("CRITICAL", "SURVIVAL", "UPKEEP"))
        elif k == "mode":
            h[k] = _constant(v, ctx, ("INSERT", "PREEMPT"))
        elif k == "then":
            h[k] = _constant(v, ctx, ("RESUME", "SKIP_BLOCK", "RESTART_FLOW", "RELOCATE", "STOP"))
        elif k == "escalate":
            h[k] = _name_arg(v, ctx, "escalate")
        elif k in ("overrides", "scope") or k == "key":
            pass
        else:
            h[k] = _const(v, ctx)
    h["body"] = _body(fn.body, ctx)
    if not scoped:
        if "overrides" in kw or "key" in kw:
            ctx.err(deco, "overrides= and key= need scope=")
            raise _Bad
        h["name"] = fn.name
        return "", h
    scope = _name_arg(kw["scope"], ctx, "scope")
    if scope not in ctx.blocks:
        ctx.err(kw["scope"], f"scope={scope}: there is no map block {scope}")
        raise _Bad
    if "overrides" in kw:
        h["name"] = _name_arg(kw["overrides"], ctx, "overrides")
        return scope, {"kind": "override", "event": h, "label": fn.name}
    h["name"] = str(_const(kw["key"], ctx)) if "key" in kw else fn.name
    return scope, {"kind": "add", "event": h, "label": fn.name}


def _extend(fn: ast.FunctionDef, ctx: _Ctx) -> tuple[str, dict[str, Any]]:
    deco: ast.Call = fn.decorator_list[0]  # type: ignore[assignment]
    kw = _kw(deco)
    if len(deco.args) != 1 or "scope" not in kw or set(kw) - {"scope", "max_per_run"}:
        ctx.err(deco, "extend(event, scope=block, max_per_run=...)")
        raise _Bad
    scope = _name_arg(kw["scope"], ctx, "scope")
    if scope not in ctx.blocks:
        ctx.err(kw["scope"], f"scope={scope}: there is no map block {scope}")
        raise _Bad
    ev: dict[str, Any] = {
        "kind": "extend",
        "key": _name_arg(deco.args[0], ctx, "the event"),
        "steps": _body(fn.body, ctx),
        "label": fn.name,
    }
    if "max_per_run" in kw:
        ev["max_per_run"] = _const(kw["max_per_run"], ctx)
    return scope, ev


def _disable(call: ast.Call, ctx: _Ctx) -> tuple[str, dict[str, Any]]:
    kw = _kw(call)
    if len(call.args) != 1 or set(kw) != {"scope"}:
        ctx.err(call, "disable(event, scope=block)")
        raise _Bad
    scope = _name_arg(kw["scope"], ctx, "scope")
    if scope not in ctx.blocks:
        ctx.err(kw["scope"], f"scope={scope}: there is no map block {scope}")
        raise _Bad
    return scope, {"kind": "disable", "key": _name_arg(call.args[0], ctx, "the event")}


def _map_block(fn: ast.FunctionDef, ctx: _Ctx) -> dict[str, Any]:
    deco: ast.Call = fn.decorator_list[0]  # type: ignore[assignment]
    if len(deco.args) != 1 or _call_name(deco.args[0]) != "map_id":
        ctx.err(deco, 'map_block(map_id("..."), entries=[...], ...)')
        raise _Bad
    out: dict[str, Any] = {"name": fn.name, "map": _ref(deco.args[0], ctx)}  # type: ignore[arg-type]
    for k, v in _kw(deco).items():
        if k == "entries":
            if not isinstance(v, ast.List | ast.Tuple):
                ctx.err(v, "entries is a list of entry_at(...) / entry_anywhere(...)")
                raise _Bad
            out["entries"] = [_entry(e, ctx) for e in v.elts]
        elif k in ("targets", "ignore"):
            lit = _expr(v, ctx)
            if lit["kind"] != "lit" or not isinstance(lit["value"], list):
                ctx.err(v, f"{k} is a literal list of mob(...)")
                raise _Bad
            out[k] = lit["value"]
        elif k == "resume_here":
            out[k] = _const(v, ctx)
        elif k == "zones":
            out[k] = _zones(v, ctx)
        else:
            ctx.err(v, f"map_block(...) has no argument {k}")
            raise _Bad
    was = ctx.in_block
    ctx.in_block = True
    try:
        out["main"] = _body(fn.body, ctx)
    finally:
        ctx.in_block = was
    return out


def _zones(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    """`zones("<map>", sha256="<64 hex>")`: the map node's zones file (Amendment A 4)."""
    call = node if isinstance(node, ast.Call) else None
    if (
        call is None
        or _call_name(call) != "zones"
        or len(call.args) != 1
        or set(_kw(call)) != {"sha256"}
    ):
        ctx.err(node, 'zones="..." is zones("<map>", sha256="<the file\'s sha256>")')
        raise _Bad
    m, sha = _const(call.args[0], ctx), _const(_kw(call)["sha256"], ctx)
    if not isinstance(m, str) or not isinstance(sha, str):
        ctx.err(call, "zones(...) takes the map and the sha256 as strings")
        raise _Bad
    return {"map": m, "sha256": sha}


def _entry(node: ast.expr, ctx: _Ctx) -> dict[str, Any]:
    name = _call_name(node)
    call: ast.Call = node  # type: ignore[assignment]
    kw = _kw(call) if name else {}
    if name == "entry_at" and len(call.args) == 2 and set(kw) <= {"radius"}:
        if _call_name(call.args[1]) != "cell":
            ctx.err(call.args[1], 'entry_at("name", cell(...)) takes a literal cell')
            raise _Bad
        out = {"name": _const(call.args[0], ctx), "at": _ref(call.args[1], ctx)}  # type: ignore[arg-type]
    elif name == "entry_anywhere" and len(call.args) == 1 and set(kw) <= {"radius"}:
        out = {"name": _const(call.args[0], ctx), "at": None}
    else:
        ctx.err(node, 'entry_at("name", cell(...)) or entry_anywhere("name")')
        raise _Bad
    if "radius" in kw:
        out["radius"] = _const(kw["radius"], ctx)
    return out


# --- the printer --------------------------------------------------------------------------------
PREC = {"or": 1, "and": 2, "not": 3, "cmp": 4, "+": 5, "-": 5, "*": 6, "//": 6, "%": 6}
CONST_OF = {v: k for k, v in CONSTANTS.items()}


def _s(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


def _num(v: Any) -> str:
    if isinstance(v, bool):
        return "True" if v else "False"
    return repr(v)


def _secs(v: float) -> str:
    """A FLOAT field in seconds (timeouts, cooldowns): whole seconds without ".0" (`wait(1)`, as the
    block says). Read back, the float field takes the int as the same float, so the IR, its JSON
    and its hash are unchanged. Never used for a literal VALUE (an int literal stays an int)."""
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def _ref_src(r: Any) -> str:
    if isinstance(r, ir.CellRef):
        return f"cell({_s(r.map)}, {r.x}, {r.y})"
    if isinstance(r, ir.MapRef):
        return f"map_id({_s(r.map)})"
    if isinstance(r, ir.NpcRef | ir.OptionRef):
        return f"{r.kind}({_s(r.key)})"
    if isinstance(r, ir.SkillRef):
        return f"skill({r.id})" if r.level is None else f"skill({r.id}, level={r.level})"
    if isinstance(r, ir.WindowRef):
        return f"window({_s(r.name)})"
    return f"{r.kind}({r.id})"


def _lit_src(v: Any) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_ref_src(r) for r in v) + "]"
    if isinstance(v, str):
        return _s(v)
    if isinstance(v, bool | int | float):
        return _num(v)
    return _ref_src(v)


def _prec(e: Any) -> int:
    if isinstance(e, ir.Logic):
        return PREC[e.kind]
    if isinstance(e, ir.Not_):
        return 3
    if isinstance(e, ir.Cmp):
        return 4
    if isinstance(e, ir.Arith):
        return PREC[e.op]
    if (
        isinstance(e, ir.Lit)
        and isinstance(e.value, int | float)
        and not isinstance(e.value, bool)
        and e.value < 0
    ):
        return 7
    return 9


def expr_src(e: Any, cat: Catalogue | None = None) -> str:
    cat = cat or catalogue()

    def wrap(child: Any, need: int) -> str:
        s = expr_src(child, cat)
        return f"({s})" if _prec(child) < need else s

    if isinstance(e, ir.Lit):
        return _lit_src(e.value)
    if isinstance(e, ir.Var):
        return e.name
    if isinstance(e, ir.OutcomeLit):
        return e.value.upper()
    if isinstance(e, ir.ListE):
        return "[" + ", ".join(expr_src(i, cat) for i in e.items) + "]"
    if isinstance(e, ir.Logic):
        p = PREC[e.kind]
        return f" {e.kind} ".join(wrap(t, p + 1) for t in e.terms)
    if isinstance(e, ir.Not_):
        return f"not {wrap(e.term, 3)}"
    if isinstance(e, ir.Cmp):
        return f"{wrap(e.left, 5)} {e.op} {wrap(e.right, 5)}"
    if isinstance(e, ir.Arith):
        p = PREC[e.op]
        return f"{wrap(e.left, p)} {e.op} {wrap(e.right, p + 1)}"
    if isinstance(e, ir.Sense):
        if e.sensor == "known":
            return f"known({expr_src(e.args['value'], cat)})"
        spec = cat.sensors[e.sensor].spec if e.sensor in cat.sensors else None
        return f"{e.sensor}({_call_args(e.args, spec.params if spec else [], cat)})"
    if isinstance(e, ir.Do):
        return _action_call(e.action, cat)
    raise TypeError(type(e))


def _call_args(args: dict[str, Any], params: Any, cat: Catalogue) -> str:
    parts: list[str] = []
    order = [p.name for p in params]
    positional = True
    for p in params:
        if p.name not in args:
            positional = positional and not p.positional
            if p.positional:
                positional = False
            continue
        val = expr_src(args[p.name], cat)
        if p.positional and positional:
            parts.append(val)
        else:
            positional = False
            parts.append(f"{p.name}={val}")
    for k in args:  # unknown parameters (the linter reports them) keep their keyword
        if k not in order:
            parts.append(f"{k}={expr_src(args[k], cat)}")
    return ", ".join(parts)


def _action_call(a: ir.ActionStmt, cat: Catalogue) -> str:
    spec = cat.blocks[a.block].spec if a.block in cat.blocks else None
    args = _call_args(a.params, spec.params if spec else [], cat)
    extra = []
    if spec is None or a.timeout_s != spec.timeout_s:
        extra.append(f"timeout_s={_secs(a.timeout_s)}")
    if a.on_fail != "stop":
        extra.append("on_fail=CONTINUE")
    if a.note is not None:
        extra.append(f"note={_s(a.note)}")
    return f"{a.block}({', '.join(p for p in [args, *extra] if p)})"


def _fit(head: str, args: list[str], indent: str, tail: str = "") -> list[str]:
    """`head(arg, ...)` on one line, or one argument per line when it is too long."""
    one = f"{indent}{head}({', '.join(args)}){tail}"
    if len(one) <= LINE or not args:
        return [one]
    inner = indent + "    "
    return [f"{indent}{head}(", *[f"{inner}{a}," for a in args], f"{indent}){tail}"]


def _exit_src(x: ir.Exit, cat: Catalogue) -> str:
    to = f"to=entry({_s(x.to_block)}, {_s(x.to_entry)})"
    tail = "" if x.timeout_s == 120 else f", timeout_s={_secs(x.timeout_s)}"
    if x.kind == "walk_exit" and x.warp is not None:
        return f"walk_exit({_ref_src(x.warp)}, {to}{tail})"
    if x.kind == "npc_warp" and x.npc is not None:
        opts = "[" + ", ".join(_ref_src(o) for o in x.options) + "]"
        return f"npc_warp({_ref_src(x.npc)}, {opts}, {to}{tail})"
    item = x.item.name if isinstance(x.item, ir.Var) else _ref_src(x.item)
    return f"item_warp({item}, {to}{tail})"


def _stmts(body: list[Any], indent: str, cat: Catalogue) -> list[str]:
    if not body:
        return [f"{indent}pass"]
    out: list[str] = []
    for st in body:
        out.extend(_stmt_src(st, indent, cat))
    return out


def _is_plain_wait(st: ir.WaitUntil) -> bool:
    """wait_until(False, timeout_s=N) without an outcome: the "wait N seconds" block."""
    c = st.cond
    return (
        st.outcome_to is None
        and isinstance(c, ir.Lit)
        and isinstance(c.value, bool)
        and c.value is False
    )


def _stmt_src(st: Any, ind: str, cat: Catalogue) -> list[str]:
    if isinstance(st, ir.ActionStmt):
        call = _action_call(st, cat)
        return [f"{ind}{st.outcome_to} = {call}" if st.outcome_to else f"{ind}{call}"]
    if isinstance(st, ir.If):
        out = [f"{ind}if {expr_src(st.cond, cat)}:", *_stmts(st.then, ind + "    ", cat)]
        orelse = st.orelse
        while len(orelse) == 1 and isinstance(orelse[0], ir.If):
            nested = orelse[0]
            out += [
                f"{ind}elif {expr_src(nested.cond, cat)}:",
                *_stmts(nested.then, ind + "    ", cat),
            ]
            orelse = nested.orelse
        if orelse:
            out += [f"{ind}else:", *_stmts(orelse, ind + "    ", cat)]
        return out
    if isinstance(st, ir.While):
        cond = expr_src(st.cond, cat)
        if st.max_iter is not None or st.max_s is not None:
            kws = [f"max_iter={st.max_iter}"] if st.max_iter is not None else []
            kws += [f"max_s={_secs(st.max_s)}"] if st.max_s is not None else []
            cond = f"bounded({cond}, {', '.join(kws)})"
        return [f"{ind}while {cond}:", *_stmts(st.body, ind + "    ", cat)]
    if isinstance(st, ir.WaitUntil):
        if _is_plain_wait(st):  # the "wait N seconds" block, in its own words (wait(1))
            return [f"{ind}wait({_secs(st.timeout_s)})"]
        call = f"wait_until({expr_src(st.cond, cat)}, timeout_s={_secs(st.timeout_s)})"
        return [f"{ind}{st.outcome_to} = {call}" if st.outcome_to else f"{ind}{call}"]
    if isinstance(st, ir.Repeat):
        return [
            f"{ind}for _ in range({expr_src(st.times, cat)}):",
            *_stmts(st.body, ind + "    ", cat),
        ]
    if isinstance(st, ir.ForEach):
        if isinstance(st.items, ir.Range):
            r = st.items
            zero = (
                isinstance(r.start, ir.Lit)
                and r.start.value == 0
                and not isinstance(r.start.value, bool)
            )
            one = (
                isinstance(r.step, ir.Lit)
                and r.step.value == 1
                and not isinstance(r.step.value, bool)
            )
            parts = (
                [expr_src(r.stop, cat)]
                if zero and one
                else (
                    [expr_src(r.start, cat), expr_src(r.stop, cat)]
                    if one
                    else [expr_src(r.start, cat), expr_src(r.stop, cat), expr_src(r.step, cat)]
                )
            )
            it = f"range({', '.join(parts)})"
        else:
            it = expr_src(st.items, cat)
        return [f"{ind}for {st.var} in {it}:", *_stmts(st.body, ind + "    ", cat)]
    if isinstance(st, ir.SetVar):
        v = st.value
        if (
            isinstance(v, ir.Arith)
            and v.op in "+-"
            and isinstance(v.left, ir.Var)
            and (v.left.name == st.var)
        ):
            return [f"{ind}{st.var} {v.op}= {expr_src(v.right, cat)}"]
        return [f"{ind}{st.var} = {expr_src(v, cat)}"]
    if isinstance(st, ir.CallProc):
        return [f"{ind}{st.proc}()"]
    if isinstance(st, ir.Stop):
        return [f"{ind}stop({_s(st.reason)})"]
    if isinstance(st, ir.Break_):
        return [f"{ind}break"]
    if isinstance(st, ir.Continue_):
        return [f"{ind}continue"]
    if isinstance(st, ir.TakeExit):
        return [f"{ind}take_exit({_exit_src(st.exit, cat)})"]
    raise TypeError(type(st))


def _on_args(h: ir.Handler, cat: Catalogue) -> list[str]:
    args = [expr_src(h.when, cat)]
    if h.until is not None:
        args.append(f"until={expr_src(h.until, cat)}")
    if h.rearm is not None:
        args.append(f"rearm={expr_src(h.rearm, cat)}")
    args.append(f"priority={CONST_OF[h.priority]}")
    if h.rank is not None:
        args.append(f"rank={h.rank}")
    if h.mode != "preempt":
        args.append(f"mode={CONST_OF[h.mode]}")
    if h.then != "resume":
        args.append(f"then={CONST_OF[h.then]}")
    if h.escalate is not None:
        args.append(f"escalate={h.escalate}")
    if h.max_insert_fails != 3:
        args.append(f"max_insert_fails={h.max_insert_fails}")
    if h.cooldown_s != 0:
        args.append(f"cooldown_s={_secs(h.cooldown_s)}")
    if h.max_per_min is not None:
        args.append(f"max_per_min={h.max_per_min}")
    if h.max_fires_per_10min != 10:
        args.append(f"max_fires_per_10min={h.max_fires_per_10min}")
    if h.max_per_run is not None:
        args.append(f"max_per_run={h.max_per_run}")
    return args


def _def(decorator: list[str], name: str, body: list[Any], cat: Catalogue) -> list[str]:
    return [*decorator, f"def {name}():", *_stmts(body, "    ", cat)]


EVENTS = "Events"
RULE_WIDTH = 42  # a section rule's length: the 384 px pane shows ~43 characters (matpilot)


def section_rule(title: str) -> str:
    """A section heading in matpilot's style: `# --- Main ---...`, RULE_WIDTH characters."""
    return f"# --- {title} ".ljust(RULE_WIDTH, "-")


# The first lines and the section rules fit the studio's Python pane (384 px) and a phone:
# matpilot measured ~43 monospace characters after the gutter (2026-11-09 round 3), so every
# generated comment line is at most RULE_WIDTH (42); code lines are left as they are.
GENERATED = [
    "# Made by poring-lab from blocks.",
    "# Read by the flow engine, never run.",
]


def _head_args(flow: ir.Flow, cat: Catalogue, config: bool) -> list[tuple[str, str]]:
    """The flow's head as (flow(...) argument, its source), in the printer's order. `config`: as
    the Config constants, where the start is a plain tuple."""
    head = [("name", _s(flow.name))]
    if flow.description:
        head.append(("description", _s(flow.description)))
    head += [("ir", str(flow.ir)), ("max_runtime_s", str(flow.max_runtime_s))]
    if flow.where_budget != ir.WHERE_BUDGET_DEFAULT:
        head.append(("where_budget", str(flow.where_budget)))
    wf = flow.workflow
    if wf is not None:
        if wf.run_until_stopped:
            head.append(("run_until_stopped", "True"))
        pair = f"{_s(wf.start_block)}, {_s(wf.start_entry)}"
        head.append(("start", f"({pair})" if config else f"entry({pair})"))
    if flow.stop_when is not None:
        head.append(("stop_when", expr_src(flow.stop_when, cat)))
    if flow.assumes:
        head.append(("assumes", "[" + ", ".join(expr_src(a, cat) for a in flow.assumes) + "]"))
    return head


def _config_lines(flow: ir.Flow, cat: Catalogue) -> list[str]:
    """The Config section: the head as UPPER_CASE constants, one per line, as a robot program's
    settings (2026-11-09). A flow with a VARIABLE named like a constant keeps the flow(...) call,
    so its Python still reads back exactly."""
    t = flow.target
    target = [("client", _s(t.client)), ("server", _s(t.server)), ("locale", _s(t.locale))]
    if set(flow.variables) & (set(CONFIG) | set(TARGET_CONFIG)):
        target.append(("path", CONST_OF[t.path]))
        args = [f"{k}={v}" for k, v in _head_args(flow, cat, config=False)]
        args.append("target=target(" + ", ".join(f"{k}={v}" for k, v in target) + ")")
        return ["flow(", *[f"    {a}," for a in args], ")"]
    names = {v: k for k, v in CONFIG.items()}
    tnames = {v: k for k, v in TARGET_CONFIG.items()}
    # every constant is a plain Python value (a learner may run the Config): "S2", ("town", "a")
    target.append(("path", _s(CONST_OF[t.path])))
    lines = [f"{names[k]} = {v}" for k, v in _head_args(flow, cat, config=True)]
    return lines + [f"{tnames[k]} = {v}" for k, v in target]


def print_flow(flow: ir.Flow, cat: Catalogue | None = None) -> str:
    """The canonical Python view of a flow, in sections (Config, Setup, Functions, Map blocks,
    Events, Main; an empty one is left out)."""
    cat = cat or catalogue()
    wf = flow.workflow
    # (is a def, its lines, its SECTION): matpilot's sections (flows-studio.md section 3), so a
    # learner reads the same shape on /flows as on a robot's Python; comments, so the parser
    # drops them and every round trip is unchanged
    chunks: list[tuple[bool, list[str], str]] = [(False, _config_lines(flow, cat), "Config")]
    if flow.variables:
        lines = [f"{k} = {_lit_src(v.value)}" for k, v in flow.variables.items()]
        chunks.append((False, lines, "Setup"))
    for name, body in flow.procedures.items():
        chunks.append((True, _def([], name, body, cat), "Functions"))
    for b in wf.blocks if wf else []:
        args = [_ref_src(b.map)]
        ents = []
        for e in b.entries:
            radius = "" if e.radius == 2 else f", radius={e.radius}"
            ents.append(
                f"entry_at({_s(e.name)}, {_ref_src(e.at)}{radius})"
                if e.at
                else f"entry_anywhere({_s(e.name)}{radius})"
            )
        args.append("entries=[" + ", ".join(ents) + "]")
        if b.targets:
            args.append("targets=" + _lit_src(list(b.targets)))
        if b.ignore:
            args.append("ignore=" + _lit_src(list(b.ignore)))
        if not b.resume_here:
            args.append("resume_here=False")
        if b.zones is not None:
            args.append(f"zones=zones({_s(b.zones.map)}, sha256={_s(b.zones.sha256)})")
        block_def = _def(_fit("@map_block", args, ""), b.name, b.main, cat)
        chunks.append((True, block_def, "Map blocks"))
    for h in flow.handlers:
        chunks.append((True, _def(_fit("@on", _on_args(h, cat), ""), h.name, h.body, cat), EVENTS))
    for b in wf.blocks if wf else []:
        for ev in b.events:
            label = ir.event_label(ev, b)
            if isinstance(ev, ir.Disable):
                line = f"disable({ev.key}, scope={b.name})"
                if not chunks[-1][0] and chunks[-1][1][-1].startswith("disable("):
                    chunks[-1][1].append(line)
                else:
                    chunks.append((False, [line], EVENTS))
            elif isinstance(ev, ir.Extend):
                args = [ev.key, f"scope={b.name}"]
                if ev.max_per_run is not None:
                    args.append(f"max_per_run={ev.max_per_run}")
                chunks.append((True, _def(_fit("@extend", args, ""), label, ev.steps, cat), EVENTS))
            elif isinstance(ev, ir.Override):
                args = [*_on_args(ev.event, cat), f"overrides={ev.event.name}", f"scope={b.name}"]
                ev_def = _def(_fit("@on", args, ""), label, ev.event.body, cat)
                chunks.append((True, ev_def, EVENTS))
            else:
                args = _on_args(ev.event, cat)
                if ev.event.name != label:
                    args.append(f"key={_s(ev.event.name)}")
                args.append(f"scope={b.name}")
                ev_def = _def(_fit("@on", args, ""), label, ev.event.body, cat)
                chunks.append((True, ev_def, EVENTS))
    if flow.main is not None:
        chunks.append((False, _stmts(flow.main, "", cat), "Main"))
    out: list[str] = list(GENERATED)
    prev_def = False
    prev_section = ""
    for is_def, lines, section in chunks:
        if out:  # two blank lines around a definition, one otherwise (PEP 8)
            out += ["", ""] if is_def or prev_def else [""]
        if section != prev_section:
            out.append(section_rule(section))
        out += lines
        prev_def, prev_section = is_def, section
    return "\n".join(out) + "\n"
