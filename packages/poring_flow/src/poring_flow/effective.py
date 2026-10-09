"""The merge rule: a map block's EFFECTIVE event set (ADR-0020 13.6.2).

For the current map block B, in this order:
1. start from the global events (the flow's `handlers`), by key, plus the ALWAYS-ON safety events
   the flow does not write (`always_on.BUILT_IN`: dead, hp_critical, unexpected_map; Batt
   2026-10-09, contradictions #15), state `built_in`;
2. apply B's map events, at most one per key:
   - DISABLE k: k global and not safety-critical; removed;
   - OVERRIDE k: k global and not safety-critical; replaced, all of it;
   - EXTEND k: k global; an ordinary k runs the map steps, then the global body; a
     safety-critical k runs the global body, then the map steps (Batt, 2026-10-08); limits: the
     tighter of the two;
   - ADD k: k not global;
3. order by class (critical > survival > upkeep; the guards above, the main flow below); inside
   critical, dead > hp_critical > unexpected_map (13.6.3) lead; then by RANK inside the class (IR 2,
   Batt 2026-10-09, contradictions #13: an explicit rank, else 13.6.3's table order, so
   unintended_engagement before hp_low); only equal ranks keep their declaration order.

The effective set is DERIVED, never stored: the flow hash covers it. Disabled events stay in the
result with `active=False`, because the editor and the runtime display show them (13.7).
The problems found while merging are returned as `MergeIssue`s; the linter reports them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from poring_flow.always_on import added
from poring_flow.ir import (
    CLASSES,
    SAFETY_CRITICAL,
    Add,
    Disable,
    Extend,
    Flow,
    Handler,
    MapBlock,
    Override,
    StmtT,
    event_key,
    event_label,
    place_in_class,
)

State = Literal["built_in", "inherited", "overridden", "extended", "disabled", "added"]


@dataclass(frozen=True)
class Effective:
    key: str
    state: State
    handler: Handler  # the definition that runs (the global one, or the map's)
    label: str  # the node path of that definition
    extension: tuple[StmtT, ...] = ()
    extension_label: str | None = None
    extension_after: bool = False  # safety-critical: the map steps run AFTER the global body
    max_per_run: int | None = None  # merged: the tighter of the global and the extension
    global_handler: Handler | None = None  # what an override replaced
    built_in: bool = False  # the global definition is the engine's always-on one (#15)

    @property
    def active(self) -> bool:
        return self.state != "disabled"

    @property
    def source(self) -> Literal["global", "map"]:
        return "map" if self.state in ("overridden", "added") else "global"


@dataclass(frozen=True)
class MergeIssue:
    rule: Literal["scope", "safety_critical"]
    path: str
    text: str


@dataclass
class Merged:
    events: list[Effective] = field(default_factory=list)
    issues: list[MergeIssue] = field(default_factory=list)

    def active(self) -> list[Effective]:
        return [e for e in self.events if e.active]

    def by_key(self, key: str) -> Effective | None:
        return next((e for e in self.events if e.key == key), None)


def _tighter(a: int | None, b: int | None) -> int | None:
    vals = [v for v in (a, b) if v is not None]
    return min(vals) if vals else None


def order_key(e: Effective, index: int) -> tuple[int, int, int, int]:
    """(class, the safety-critical lead, the rank inside the class, declaration order)."""
    return (CLASSES.index(e.handler.priority), *place_in_class(e.handler), index)


def _global(flow: Flow) -> dict[str, Effective]:
    """The global events by key: the always-on built-ins the flow does not write, then its own."""
    out = {
        h.name: Effective(h.name, "built_in", h, h.name, max_per_run=h.max_per_run, built_in=True)
        for h in added(flow)
    }
    for h in flow.handlers:
        out[h.name] = Effective(h.name, "inherited", h, h.name, max_per_run=h.max_per_run)
    return out


def global_set(flow: Flow) -> Merged:
    out = Merged(events=list(_global(flow).values()))
    _order(out)
    return out


def _order(m: Merged) -> None:
    indexed = list(enumerate(m.events))
    indexed.sort(key=lambda p: order_key(p[1], p[0]))
    m.events = [e for _, e in indexed]


def merge(flow: Flow, block: MapBlock) -> Merged:
    out = Merged()
    by_key = _global(flow)
    glob = {k: e.handler for k, e in by_key.items()}
    builtin = {k for k, e in by_key.items() if e.built_in}
    order = list(by_key)
    seen: set[str] = set()
    b = block.name
    for ev in block.events:
        k = event_key(ev)
        if k in seen:
            out.issues.append(MergeIssue("scope", b, f"two map events on {k}: at most one per key"))
            continue
        seen.add(k)
        critical = k in SAFETY_CRITICAL
        if isinstance(ev, Add):
            if k in glob:
                out.issues.append(
                    MergeIssue("scope", b, f"add {k}: {k} is a global event: override it instead")
                )
                continue
            by_key[k] = Effective(
                k, "added", ev.event, event_label(ev, block), max_per_run=ev.event.max_per_run
            )
            order.append(k)
            continue
        verb = {Override: "override", Extend: "extend", Disable: "disable"}[type(ev)]
        if k not in glob:
            out.issues.append(MergeIssue("scope", b, f"{verb} {k}: there is no global event {k}"))
            continue
        g = glob[k]
        if isinstance(ev, Disable):
            if critical:
                out.issues.append(
                    MergeIssue(
                        "safety_critical",
                        b,
                        f"{k} is safety-critical: it can be extended, never disabled",
                    )
                )
                continue
            by_key[k] = Effective(
                k, "disabled", g, g.name, max_per_run=g.max_per_run, built_in=k in builtin
            )
        elif isinstance(ev, Override):
            if critical:
                out.issues.append(
                    MergeIssue(
                        "safety_critical",
                        b,
                        f"{k} is safety-critical: it can be extended, never overridden",
                    )
                )
                continue
            by_key[k] = Effective(
                k,
                "overridden",
                ev.event,
                event_label(ev, block),
                max_per_run=ev.event.max_per_run,
                global_handler=g,
            )
        else:
            if (
                ev.max_per_run is not None
                and g.max_per_run is not None
                and (ev.max_per_run > g.max_per_run)
            ):
                out.issues.append(
                    MergeIssue(
                        "safety_critical" if critical else "scope",
                        b,
                        f"extend {k}: max_per_run {ev.max_per_run} loosens the global "
                        f"{g.max_per_run}: an extension may only tighten",
                    )
                )
            by_key[k] = Effective(
                k,
                "extended",
                g,
                g.name,
                extension=tuple(ev.steps),
                extension_label=event_label(ev, block),
                extension_after=critical,
                max_per_run=_tighter(g.max_per_run, ev.max_per_run),
                built_in=k in builtin,
            )
    out.events = [by_key[k] for k in order]
    _order(out)
    return out
