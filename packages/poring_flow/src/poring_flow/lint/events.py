"""Linter layer 3, events (section 5's "3 · events" row and 13.6.9).

Where 13.6.9 is stricter (a same-sensor tie is an ERROR, not a warning), it wins. Ties need the
same class AND the same rank (Batt 2026-10-09, contradictions #14); events at different ranks are
ordered, and only an INFO says so.

Interpretation (reported, not decided here): section 5 requires "a rearm or a cooldown" on every
handler, while 13.6.8's own defaults give `dead`, `unexpected_map` and `unintended_engagement`
neither. The rule here is satisfied by any re-fire bound: `rearm`, `until`, `cooldown_s`,
`max_per_min`, `max_per_run`, or a condition made only of momentary CUE sensors (a cue cannot
hold on every tick). A plain level condition with none of them is the error.
"""

from __future__ import annotations

import math
from typing import Any

from poring_flow import ir
from poring_flow.always_on import BUILT_IN
from poring_flow.effective import Effective
from poring_flow.lint.common import (
    Consts,
    Ctx,
    Thr,
    assigned_vars,
    body_actions,
    handler_exprs,
    interval,
    num,
    sensors_in,
    threshold,
)
from poring_flow.lint.simulate import _changes_map, escape_kind

LOW = ("<", "<=")
HIGH = (">", ">=")
FINISH = "finish_target"


def check(ctx: Ctx) -> None:
    consts = Consts(ctx.flow, assigned_vars(ctx.flow))
    for issue in _merge_issues(ctx):
        ctx.add(issue[0], "error", 3, issue[1], issue[2])
    _safety_critical(ctx, consts)
    for label, h, block, _ in ir.handler_bodies(ctx.flow):
        _handler(ctx, consts, label, h, block)
    for b in ctx.blocks:
        for ev in b.events:
            if isinstance(ev, ir.Extend):
                _extension(ctx, ir.event_label(ev, b), ev, b)
    _ties(ctx, consts)
    for b in ctx.blocks:
        for ev in b.events:
            if isinstance(ev, ir.Override):
                g = next((h for h in ctx.flow.handlers if h.name == ev.event.name), None)
                if g is not None:
                    _class_change(ctx, b, ev, g)
                    _looser(ctx, consts, b, ev, g)
            if isinstance(ev, ir.Override | ir.Add) and ev.event.name == "unintended_engagement":
                _engagement(ctx, consts, b, ev)


def _merge_issues(ctx: Ctx) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for b in ctx.blocks:
        out += [(i.rule, i.path, i.text) for i in ctx.merged(b).issues]
    return out


# --- the fixed safety-critical set (13.6.1, 13.6.9; always on, contradictions #15) -------------
LIMITS = ("max_per_run", "max_per_min", "max_fires_per_10min")


def _safety_critical(ctx: Ctx, consts: Consts) -> None:
    """NOT WEAKENED (Batt 2026-10-09, contradictions #15): the compiler adds dead, hp_critical and
    unexpected_map to every flow (always_on.py), so a flow that leaves one out gets the built-in.
    A flow that writes one may only make it STRICTER than the built-in; each way it is weaker is an
    ERROR at the event's node path."""
    for h in ctx.flow.handlers:
        if h.name in BUILT_IN:
            for text in weakened(ctx, consts, h, BUILT_IN[h.name]):
                ctx.add("safety_critical", "error", 3, h.name, text)
    for b in ctx.blocks:  # a map node's replacement (the project model's strict override)
        for ev in b.events:
            if isinstance(ev, ir.Override) and ev.strict and ev.event.name in BUILT_IN:
                label = ir.event_label(ev, b)
                for text in weakened(ctx, consts, ev.event, BUILT_IN[ev.event.name]):
                    ctx.add("safety_critical", "error", 3, label, text)


def weakened(ctx: Ctx, consts: Consts, h: ir.Handler, d: ir.Handler) -> list[str]:
    """Every way a written safety-critical event `h` is weaker than its built-in `d`."""
    k = h.name
    out: list[str] = []
    if h.priority != "critical":
        out.append(f"{k} is safety-critical: its class is critical, not {h.priority}")
    if h.mode != "preempt":
        out.append(f"{k} is safety-critical: it pre-empts")
    if h.rank is not None and h.rank != ir.DEFAULT_RANK[k]:
        out.append(
            f"{k} is safety-critical: its rank is fixed ({ir.DEFAULT_RANK[k]}, 13.6.3), not "
            f"{h.rank}"
        )
    if h.then not in (d.then, "stop"):
        out.append(f"{k} is safety-critical: then is {d.then} or stop, not {h.then}")
    if h.when != d.when:
        th, td = threshold(h.when, ctx, consts), threshold(d.when, ctx, consts)
        ih = interval(th) if th is not None and not th.boolean else None
        idd = interval(td) if td is not None and not td.boolean else None
        if th is not None and td is not None and th.key == td.key and ih and idd:
            if idd.meet(ih) != idd:  # the built-in's range must lie inside the written one
                out.append(
                    f"{k} is safety-critical: when {ctx.src(h.when)} fires later than the "
                    f"built-in {ctx.src(d.when)}"
                )
        else:
            out.append(f"{k} is safety-critical: its trigger is the built-in {ctx.src(d.when)}")
    if (h.until, h.rearm) != (d.until, d.rearm):
        fixed = (
            f"rearm={ctx.src(d.rearm)}"
            if d.rearm is not None
            else "none: it re-arms when its trigger clears"
        )
        out.append(f"{k} is safety-critical: its re-arm is the built-in's ({fixed})")
    for lim in LIMITS:
        vh, vd = getattr(h, lim), getattr(d, lim)
        if vd is not None and (vh is None or vh > vd):
            shown = "unlimited" if vh is None else str(vh)
            out.append(
                f"{k} is safety-critical: {lim} {shown} loosens the built-in {vd}: it may only "
                "be tightened"
            )
    if h.cooldown_s > d.cooldown_s:
        out.append(
            f"{k} is safety-critical: cooldown_s {num(h.cooldown_s)} loosens the built-in "
            f"{num(d.cooldown_s)}: it may only be tightened"
        )
    want = [a.block for a in d.body if isinstance(a, ir.ActionStmt)]
    got = [a.block if isinstance(a, ir.ActionStmt) else a.kind for a in h.body]
    if k == "hp_critical" and got != want:
        out.append("hp_critical's body is fixed: escape()")
    elif got[: len(want)] != want:
        steps = ", ".join(f"{b}()" for b in want)
        out.append(f"{k}'s body starts with the built-in {steps}: steps may only follow it")
    return out


# --- one handler ------------------------------------------------------------------------------
def _cue_only(ctx: Ctx, e: Any) -> bool:
    ss = sensors_in(e)
    return bool(ss) and all(
        s.sensor in ctx.cat.sensors and ctx.cat.sensors[s.sensor].spec.cue for s in ss
    )


def _handler(ctx: Ctx, consts: Consts, label: str, h: ir.Handler, b: ir.MapBlock | None) -> None:
    flow = ctx.flow
    if (
        h.until is None
        and h.rearm is None
        and h.cooldown_s == 0
        and h.max_per_min is None
        and (h.max_per_run is None and not _cue_only(ctx, h.when))
    ):
        ctx.add(
            "rearm", "error", 3, label, "no re-arm and no cooldown: it would fire on every tick"
        )
    for _, e in handler_exprs(h):
        for s in sensors_in(e):
            spec = ctx.cat.sensors.get(s.sensor)
            if spec is not None and not spec.spec.passive:
                ctx.add(
                    "passive_only",
                    "error",
                    3,
                    label,
                    f"{s.sensor}() is an active sensor: never in an event condition",
                )
    acts = body_actions(h.body, flow)
    _hysteresis(ctx, consts, label, h)
    t = threshold(h.when, ctx, consts)
    if t is not None and not t.boolean and t.op in LOW + HIGH:
        toward = "-" if t.op in LOW else "+"
        for a in acts:
            blk = ctx.cat.blocks.get(a.block)
            if blk is not None and blk.spec.affects.get(t.sensor) == toward:
                verb = "lowers" if toward == "-" else "raises"
                ctx.add(
                    "retrigger",
                    "warning",
                    3,
                    label,
                    f"{a.block} {verb} {t.shown}, which can re-trigger {h.name}",
                )
    for a in acts:
        if a.on_fail == "continue" and a.outcome_to is None:
            ctx.add(
                "failure_path",
                "warning",
                3,
                label,
                f"{a.block} continues on failure and nothing reads its outcome: a failure "
                "goes unnoticed",
            )
    if h.priority == "critical":
        for a in acts:
            blk = ctx.cat.blocks.get(a.block)
            if blk is not None and blk.spec.long:
                ctx.add(
                    "critical_long",
                    "warning",
                    3,
                    label,
                    f"{a.block} is a long action inside a critical event",
                )
    if h.mode == "insert":
        for a in acts:
            blk = ctx.cat.blocks.get(a.block)
            if blk is not None and not blk.spec.insertable:
                ctx.add(
                    "insert_body",
                    "error",
                    3,
                    label,
                    f"{a.block} cannot be inserted: make the event pre-empt",
                )
    if h.then not in ("relocate", "stop"):
        sheets = (
            [ctx.sheet(b.map.map)] if b else [ctx.sheet(x.map.map) for x in ctx.blocks] or [None]
        )
        for a in acts:
            what = next((w for s in sheets if (w := _changes_map(ctx, consts, a, s))), None)
            if (
                a.block == "escape"
                and any(escape_kind(s) == "fly_wing" for s in sheets)
                and (what is None)
            ):
                continue
            if what:
                ctx.add(
                    "relocating",
                    "error",
                    3,
                    label,
                    f"{what} changes the map: then the event must relocate or stop",
                )
                break
    _event_species(ctx, consts, label, h, b)


def _extension(ctx: Ctx, label: str, ev: ir.Extend, b: ir.MapBlock) -> None:
    g = next((h for h in ctx.flow.handlers if h.name == ev.key), BUILT_IN.get(ev.key))
    if g is None:
        return
    for a in body_actions(ev.steps, ctx.flow):
        spec = ctx.cat.blocks.get(a.block)
        if spec is None:
            continue
        if g.priority == "critical" and spec.spec.long:
            ctx.add(
                "critical_long",
                "warning",
                3,
                label,
                f"{a.block} is a long action inside a critical event",
            )
        if g.mode == "insert" and not spec.spec.insertable:
            ctx.add(
                "insert_body",
                "error",
                3,
                label,
                f"{a.block} cannot be inserted: make the event pre-empt",
            )


# --- hysteresis pairs (13.6.9) ------------------------------------------------------------------
def _never(ctx: Ctx, t: Thr) -> bool:
    spec = ctx.cat.sensors[t.sensor].spec
    iv = interval(t)
    if spec.range is None or iv is None:
        return False
    lo, hi = spec.range
    return iv.meet(type(iv)(lo, True, hi, True)).empty()


def _hysteresis(ctx: Ctx, consts: Consts, label: str, h: ir.Handler) -> None:
    start = threshold(h.when, ctx, consts)
    for field, stop_e in (("until", h.until), ("rearm", h.rearm)):
        if stop_e is None:
            continue
        stop = threshold(stop_e, ctx, consts)
        for which, t, e in (("when", start, h.when), (field, stop, stop_e)):
            if t is not None and not t.boolean and _never(ctx, t):
                lo, hi = ctx.cat.sensors[t.sensor].spec.range or (0, 0)
                ctx.add(
                    "hysteresis",
                    "error",
                    3,
                    label,
                    f"{which} {ctx.src(e)} can never hold: {t.shown} reads {num(lo)}..{num(hi)}",
                )
                return
        if start is None or stop is None or start.key != stop.key:
            continue
        s_src, p_src = ctx.src(h.when), ctx.src(stop_e)
        if start.boolean:
            if start.value == stop.value:
                ctx.add(
                    "same_direction",
                    "error",
                    3,
                    label,
                    f"{field} {p_src} does not end {s_src}: the stop must be its negation",
                )
            continue
        if start.op not in LOW + HIGH or stop.op not in LOW + HIGH:
            continue
        low = start.op in LOW
        s = num(start.value)
        if (stop.op in LOW) == low:
            side = "above" if low else "below"
            ctx.add(
                "same_direction",
                "error",
                3,
                label,
                f"{field} {p_src} does not end {s_src}: the stop must lie {side} {s}",
            )
            continue
        a, b = interval(start), interval(stop)
        if a is not None and b is not None and not a.meet(b).empty():
            need = f"exceed {s}" if low else f"lie below {s}"
            ctx.add(
                "hysteresis",
                "error",
                3,
                label,
                f"{field} {p_src} overlaps when {s_src}: the stop threshold must {need}",
            )
            continue
        gap = stop.value - start.value if low else start.value - stop.value
        res = ctx.cat.sensors[start.sensor].spec.resolution
        if res is not None and gap < res:
            ctx.add(
                "hysteresis",
                "warning",
                3,
                label,
                f"the band between when {s_src} and {field} {p_src} is narrower than the "
                f"readout's resolution ({num(res)})",
            )


# --- ties: two effective events of one class (13.6.2 step 4; 13.6.9) -----------------------------
# Batt 2026-10-09 (contradictions #14, after #13's rank): a tie needs the same class AND the same
# rank. Only then can arrival order decide, so only then is it a WARNING (different sensors: they
# queue first in, first out) or an ERROR (overlapping on the same sensor, 13.6.2 step 4). Two
# events of one class at different ranks are ordered already: an INFO says which runs first.
def _ties(ctx: Ctx, consts: Consts) -> None:
    scopes: list[tuple[str, list[Effective], bool]] = [("global", ctx.merged(None).active(), True)]
    scopes += [(b.name, ctx.merged(b).active(), False) for b in ctx.blocks]
    for scope, events, is_global in scopes:
        for i, a in enumerate(events):
            for b in events[i + 1 :]:
                if a.handler.priority != b.handler.priority:
                    continue
                if a.key in ir.SAFETY_CRITICAL and b.key in ir.SAFETY_CRITICAL:
                    continue  # their order is fixed (13.6.2 step 3)
                if not is_global and a.source == "global" and b.source == "global":
                    continue  # reported once, at global scope
                _tie(ctx, consts, scope, a, b)


def _tie(ctx: Ctx, consts: Consts, scope: str, a: Effective, b: Effective) -> None:
    """`a` precedes `b` in the effective order (effective.order_key)."""
    cls = a.handler.priority
    ta, tb = threshold(a.handler.when, ctx, consts), threshold(b.handler.when, ctx, consts)
    region = None
    if ta is not None and tb is not None and ta.key == tb.key:
        ia, ib = interval(ta), interval(tb)
        if ia is None or ib is None:
            return
        both = ia.meet(ib)
        if both.empty():
            return  # never due together
        region = ta.shown if ta.boolean else both.text(ta.shown)
    on = f" on {region}" if region else ""
    if ir.place_in_class(a.handler) != ir.place_in_class(b.handler):
        ra, rb = ir.rank_of(a.handler), ir.rank_of(b.handler)
        why = "safety-critical first" if a.key in ir.SAFETY_CRITICAL else f"rank {ra} before {rb}"
        ctx.add(
            "ties",
            "info",
            3,
            scope,
            f"{a.key} and {b.key} are both {cls}{on}: {a.key} runs first when both are due ({why})",
        )
        return
    r = ir.rank_of(a.handler)
    if region:
        ctx.add("ties", "error", 3, scope, f"{a.key} and {b.key} are both {cls} at rank {r}{on}")
        return
    ctx.add(
        "ties",
        "warning",
        3,
        scope,
        f"{a.key} and {b.key} are both {cls} at rank {r} on different sensors: they queue "
        "first in, first out",
    )


# --- overrides: class change, looser on a harder map --------------------------------------------
def _class_change(ctx: Ctx, b: ir.MapBlock, ev: ir.Override, g: ir.Handler) -> None:
    old, new = ir.CLASSES.index(g.priority), ir.CLASSES.index(ev.event.priority)
    if old == new:
        return
    k = ev.event.name
    others = [e for e in ctx.merged(b).active() if e.key != k]
    rank = {e.key: ir.CLASSES.index(e.handler.priority) for e in others}
    if new > old:
        hit = [e.key for e in others if old < rank[e.key] <= new]
        tail = (
            f": {_and(hit)} no longer {'waits' if len(hit) == 1 else 'wait'} for it" if hit else ""
        )
    else:
        hit = [e.key for e in others if new < rank[e.key] <= old]
        tail = f": it now pre-empts {_and(hit)}" if hit else ""
    ctx.add(
        "class_change",
        "warning",
        3,
        b.name,
        f"{k} moved from {g.priority} to {ev.event.priority}{tail}",
    )


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"


def base_level(ctx: Ctx, consts: Consts) -> int | None:
    for a in ctx.flow.assumes:
        if isinstance(a, ir.Cmp) and isinstance(a.left, ir.Sense) and a.left.sensor == "base_level":
            v = consts.value(a.right)
            if isinstance(v, int) and not isinstance(v, bool) and a.op in (">=", "=="):
                return v
            if isinstance(v, int) and not isinstance(v, bool) and a.op == ">":
                return v + 1
    return None


def harder(ctx: Ctx, consts: Consts, map_id: str) -> tuple[str | None, bool]:
    """(why the map is HARDER, whether the level criterion was skipped) from its L3 sheet."""
    sheet = ctx.sheet(map_id)
    if sheet is None or ctx.world is None:
        return None, False
    mobs = ctx.world.mobs
    spawned = sheet.spawned()
    aggressive = [m for m in spawned if m in mobs and mobs[m].aggressive]
    if aggressive:
        return f"{map_id} spawns an aggressive species (mob {aggressive[0]})", False
    if sheet.boss_lines():
        return f"{map_id} has a boss spawn line (mob {sheet.boss_lines()[0]})", False
    base = base_level(ctx, consts)
    if base is None:
        return None, True
    above = [(mobs[m].level, m) for m in spawned if m in mobs and mobs[m].level > base]
    if above:
        lvl, m = max(above)
        return (
            f"{map_id} spawns mob {m} at level {lvl}, above the character's base level {base}",
            False,
        )
    return None, False


def _looser(ctx: Ctx, consts: Consts, b: ir.MapBlock, ev: ir.Override, g: ir.Handler) -> None:
    o = ev.event
    k = o.name
    aspects: list[str] = []
    ts_o, ts_g = threshold(o.when, ctx, consts), threshold(g.when, ctx, consts)
    danger = None
    if ts_o and ts_g and ts_o.key == ts_g.key and not ts_o.boolean:
        danger = ctx.cat.sensors[ts_o.sensor].spec.danger
        if (danger == "low" and ts_o.value < ts_g.value) or (
            danger == "high" and ts_o.value > ts_g.value
        ):
            aspects.append(
                f"{k} {ts_o.op} {num(ts_o.value)} is looser than the global "
                f"{ts_g.op} {num(ts_g.value)}"
            )
    for field in ("until", "rearm"):
        eo, eg = getattr(o, field), getattr(g, field)
        if danger is None or eo is None or eg is None:
            continue
        po, pg = threshold(eo, ctx, consts), threshold(eg, ctx, consts)
        if (
            po
            and pg
            and po.key == pg.key
            and po.key == (ts_o.key if ts_o else None)
            and (
                (danger == "low" and po.value < pg.value)
                or (danger == "high" and po.value > pg.value)
            )
        ):
            aspects.append(
                f"{k} {field} {po.op} {num(po.value)} is looser than the global "
                f"{field} {pg.op} {num(pg.value)}"
            )
    for lim in ("max_per_run", "max_per_min", "max_fires_per_10min", "cooldown_s"):
        vo, vg = getattr(o, lim), getattr(g, lim)
        lo = math.inf if vo is None else float(vo)
        lg = math.inf if vg is None else float(vg)
        if lo > lg:
            shown = "unlimited" if vo is None else num(float(vo))
            aspects.append(f"{k} {lim} {shown} is looser than the global {num(lg)}")
    if not aspects:
        return
    why, skipped = harder(ctx, consts, b.map.map)
    if why is not None:
        for a in aspects:
            ctx.add("looser_harder", "warning", 3, b.name, f"{a}, and {why}", ack=True)
    elif skipped:
        ctx.add(
            "looser_harder",
            "info",
            3,
            b.name,
            f"{k} is looser than the global; whether {b.map.map} is harder was judged without "
            "the level criterion: the character's base level is not in assumes",
        )


# --- the engagement policy (13.9) ---------------------------------------------------------------
def _finished_species(stmts: list[Any], consts: Consts) -> list[int]:
    out: list[int] = []
    for site in ir.walk(stmts, "x", root="x", scope="main", block=None):
        st = site.stmt
        if not isinstance(st, ir.If) or not isinstance(st.cond, ir.Cmp):
            continue
        c = st.cond
        if not (isinstance(c.left, ir.Sense) and c.left.sensor == "engaged_species"):
            continue
        finishes = any(isinstance(s, ir.ActionStmt) and s.block == FINISH for s in st.then)
        if not finishes:
            continue
        if c.op == "in":
            refs = consts.refs(c.right, ir.MobRef) or []
            out += [r.id for r in refs]
        elif c.op == "==":
            r = consts.ref(c.right, ir.MobRef)
            out += [r.id] if r else []
    return out


def _engagement(ctx: Ctx, consts: Consts, b: ir.MapBlock, ev: ir.Override | ir.Add) -> None:
    label = ir.event_label(ev, b)
    body = ev.event.body
    uses_species = any(
        isinstance(x, ir.Sense) and x.sensor == "engaged_species"
        for site in ir.walk(body, "x", root="x", scope="main", block=None)
        for _, e in ir.stmt_exprs(site.stmt)
        for x in ir.sub_exprs(e)
    )
    if uses_species and not ctx.detector.names_species:
        ctx.add(
            "engagement_policy",
            "warning",
            3,
            b.name,
            f"{label} decides by species, and the detector cannot name species yet: the run "
            "applies its most cautious branch",
        )
    mobs = ctx.world.mobs if ctx.world else {}
    base = base_level(ctx, consts)
    for mid in _finished_species(body, consts):
        m = mobs.get(mid)
        if m is None:
            continue
        reasons = []
        if m.aggressive:
            reasons.append("it is aggressive")
        if m.chases:
            reasons.append("it chases")
        if base is not None and m.level > base:
            reasons.append(f"it is level {m.level}, above the character's {base}")
        for r in reasons:
            ctx.add(
                "engagement_policy",
                "warning",
                3,
                b.name,
                f"{FINISH} for mob {mid}: {r} (L3 mob data)",
            )


# --- species an event names (13.6.9) -------------------------------------------------------------
def _event_species(
    ctx: Ctx, consts: Consts, label: str, h: ir.Handler, b: ir.MapBlock | None
) -> None:
    if not ctx.blocks:
        return
    maps = [b.map.map] if b else sorted({x.map.map for x in ctx.blocks})
    sheets = [ctx.sheet(m) for m in maps]
    if any(s is None for s in sheets):
        return
    for _, e in handler_exprs(h):
        for s in sensors_in(e):
            if s.sensor not in ("sees", "count_visible"):
                continue
            mob = consts.ref(s.args.get("mob"), ir.MobRef)
            if mob is None:
                continue
            if not any(mob.id in sh.spawned() for sh in sheets if sh is not None):
                ctx.add(
                    "event_species",
                    "warning",
                    3,
                    label,
                    f"mob {mob.id} is in no spawn line of {', '.join(maps)}",
                )
