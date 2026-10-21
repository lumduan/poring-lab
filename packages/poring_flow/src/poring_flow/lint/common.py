"""Shared pieces of the linter: findings, the context, constants of a flow, thresholds."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from poring_flow import ir
from poring_flow.catalogue import Catalogue
from poring_flow.effective import Merged, global_set, merge
from poring_flow.pyview import expr_src
from poring_flow.sheet import MapSheet, World
from poring_flow.zones import ZonesProvider

# READINESS (Batt 2026-10-09, ADR-0020 contradictions #6): a binding that is not there YET for the
# target environment (`resolve()` raised `Unsupported`). It is listed in the report and blocks the
# RUN (`poring_flow.runstart` refuses on it), never the design: a flow with readiness items can be
# designed, linted, simulated and approved; it becomes runnable as its bindings land.
Severity = Literal["error", "readiness", "warning", "info"]
# resolve(block, concept, params) raises poring_skills.resolve.Unsupported for a missing binding
Resolver = Callable[[str, str, dict[str, str]], None]


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: Severity
    layer: int  # 1 schema, 2 semantics, 3 simulation (section 5)
    path: str  # a node path (section 1 / 13.1), a map block, or "" for the whole workflow
    text: str
    ack: bool = False  # the owner acknowledges it at approval (section 5, 13.6.9)
    shown: str = ""  # the path as a person reads it (ir.PathNames, #3); `path` stays the node id

    @property
    def message(self) -> str:
        where = self.shown or self.path
        return f"{where}: {self.text}" if where else self.text


@dataclass(frozen=True)
class Detector:
    """What perception can do today (the preparation report and two lint rules read it)."""

    names_species: bool = False  # today's detector names player / monster / npc only (13.9)
    measured: frozenset[int] = frozenset()  # species trained AND measured (13.4)
    prepared_maps: frozenset[str] = frozenset()  # maps whose map prep is done (13.4)


@dataclass
class Ctx:
    flow: ir.Flow
    cat: Catalogue
    world: World | None
    resolver: Resolver | None
    detector: Detector
    zones: ZonesProvider | None = None  # Amendment A 4: None = not loaded (file checks skipped)
    findings: list[Finding] = field(default_factory=list)
    _seen: set[tuple[str, str, str]] = field(default_factory=set)
    _merged: dict[str, Merged] = field(default_factory=dict)
    _names: ir.PathNames | None = None

    def shown(self, path: str) -> str:
        """A node path in the grammar a person reads (#3): `maps.town.3`, `handlers.dead`."""
        if self._names is None:
            self._names = ir.PathNames(self.flow)
        return self._names(path)

    def add(
        self, rule: str, severity: Severity, layer: int, path: str, text: str, ack: bool = False
    ) -> None:
        key = (rule, path, text)
        if key not in self._seen:
            self._seen.add(key)
            self.findings.append(
                Finding(rule, severity, layer, path, text, ack, self.shown(path) if path else "")
            )

    @property
    def blocks(self) -> list[ir.MapBlock]:
        return list(self.flow.workflow.blocks) if self.flow.workflow else []

    def block(self, name: str) -> ir.MapBlock | None:
        return next((b for b in self.blocks if b.name == name), None)

    def merged(self, block: ir.MapBlock | None) -> Merged:
        key = block.name if block else ""
        if key not in self._merged:
            self._merged[key] = merge(self.flow, block) if block else global_set(self.flow)
        return self._merged[key]

    def sheet(self, map_id: str) -> MapSheet | None:
        return self.world.sheet(map_id) if self.world else None

    def src(self, e: Any) -> str:
        return expr_src(e, self.cat)


# --- constants of a flow ------------------------------------------------------------------------
def assigned_vars(flow: ir.Flow) -> set[str]:
    out: set[str] = set()
    for site in ir.sites(flow):
        st = site.stmt
        if isinstance(st, ir.SetVar | ir.ForEach):
            out.add(st.var)
        for a in ir.actions_in(st):
            if a.outcome_to:
                out.add(a.outcome_to)
        if isinstance(st, ir.WaitUntil) and st.outcome_to:
            out.add(st.outcome_to)
    return out


@dataclass
class Consts:
    flow: ir.Flow
    assigned: set[str]

    def value(self, e: Any) -> Any:
        """The constant value of an expression (a Lit's value), or None when not constant."""
        if isinstance(e, ir.Lit):
            return e.value
        if isinstance(e, ir.Var) and e.name not in self.assigned and e.name in self.flow.variables:
            return self.flow.variables[e.name].value
        return None

    def ref(self, e: Any, kind: type[Any]) -> Any:
        v = self.value(e)
        return v if isinstance(v, kind) else None

    def refs(self, e: Any, kind: type[Any]) -> list[Any] | None:
        """A list of references (a literal list, or a list of constant variables)."""
        v = self.value(e)
        if isinstance(v, list):
            return [r for r in v if isinstance(r, kind)]
        if isinstance(e, ir.ListE):
            out = []
            for i in e.items:
                r = self.ref(i, kind)
                if r is None:
                    return None
                out.append(r)
            return out
        return None

    def item(self, e: Any) -> int | None:
        r = self.ref(e, ir.ItemRef)
        return r.id if r else None


# --- thresholds ---------------------------------------------------------------------------------
FLIP = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}


@dataclass(frozen=True)
class Thr:
    sensor: str  # e.g. hp_percent
    key: str  # the sensor plus its arguments, canonical
    shown: str  # e.g. hp_percent()
    op: str  # with the sensor on the left
    value: float
    boolean: bool = False


def _sense_key(s: ir.Sense) -> str:
    args = {k: v.model_dump(mode="json") for k, v in s.args.items()}
    return f"{s.sensor}:{json.dumps(args, sort_keys=True)}"


def threshold(e: Any, ctx: Ctx, consts: Consts) -> Thr | None:
    """A condition of the form sensor OP number (either side), or a boolean sensor (negated)."""
    if isinstance(e, ir.Sense) and e.sensor in ctx.cat.sensors:
        if ctx.cat.sensors[e.sensor].spec.type == "bool":
            return Thr(e.sensor, _sense_key(e), ctx.src(e), "==", 1.0, True)
        return None
    if isinstance(e, ir.Not_) and isinstance(e.term, ir.Sense):
        t = threshold(e.term, ctx, consts)
        return Thr(t.sensor, t.key, t.shown, "==", 0.0, True) if t and t.boolean else None
    if not isinstance(e, ir.Cmp) or e.op in ("in", "not in"):
        return None
    left, right = e.left, e.right
    op: str = e.op
    if not isinstance(left, ir.Sense):
        left, right, op = right, left, FLIP[op]
    if not isinstance(left, ir.Sense) or left.sensor not in ctx.cat.sensors:
        return None
    v = consts.value(right)
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return Thr(left.sensor, _sense_key(left), ctx.src(left), op, float(v))


def num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(v)


@dataclass(frozen=True)
class Interval:
    lo: float
    lo_closed: bool
    hi: float
    hi_closed: bool

    def empty(self) -> bool:
        return self.lo > self.hi or (self.lo == self.hi and not (self.lo_closed and self.hi_closed))

    def meet(self, o: Interval) -> Interval:
        if self.lo > o.lo or (self.lo == o.lo and not self.lo_closed):
            lo, lc = self.lo, self.lo_closed
        else:
            lo, lc = o.lo, o.lo_closed
        if self.hi < o.hi or (self.hi == o.hi and not self.hi_closed):
            hi, hc = self.hi, self.hi_closed
        else:
            hi, hc = o.hi, o.hi_closed
        return Interval(lo, lc, hi, hc)

    def text(self, shown: str) -> str:
        parts = []
        if self.lo == self.hi and self.lo_closed and self.hi_closed:
            return f"{shown} == {num(self.lo)}"
        if not math.isinf(self.lo):
            parts.append(f"{shown} {'>=' if self.lo_closed else '>'} {num(self.lo)}")
        if not math.isinf(self.hi):
            parts.append(f"{shown} {'<=' if self.hi_closed else '<'} {num(self.hi)}")
        return " and ".join(parts) or shown


def interval(t: Thr) -> Interval | None:
    inf = math.inf
    v = t.value
    return {
        "<": Interval(-inf, False, v, False),
        "<=": Interval(-inf, False, v, True),
        ">": Interval(v, False, inf, False),
        ">=": Interval(v, True, inf, False),
        "==": Interval(v, True, v, True),
    }.get(t.op)


def sensors_in(e: Any) -> list[ir.Sense]:
    return [s for s in ir.sub_exprs(e) if isinstance(s, ir.Sense)]


def vars_in(e: Any) -> set[str]:
    return {v.name for v in ir.sub_exprs(e) if isinstance(v, ir.Var)}


def handler_exprs(h: ir.Handler) -> Iterator[tuple[str, Any]]:
    yield "when", h.when
    if h.until is not None:
        yield "until", h.until
    if h.rearm is not None:
        yield "rearm", h.rearm


def body_actions(
    stmts: list[Any], flow: ir.Flow, seen: set[str] | None = None
) -> list[ir.ActionStmt]:
    """Every action a body runs, through nested statements and called procedures."""
    seen = set() if seen is None else seen
    out: list[ir.ActionStmt] = []
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        out.extend(ir.actions_in(site.stmt))
        if isinstance(site.stmt, ir.CallProc) and site.stmt.proc not in seen:
            seen.add(site.stmt.proc)
            out.extend(body_actions(flow.procedures.get(site.stmt.proc, []), flow, seen))
    return out
