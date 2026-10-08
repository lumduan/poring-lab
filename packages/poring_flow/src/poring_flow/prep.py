"""The preparation report and the AI-preparation estimate (ADR-0020 13.3, 13.4).

- The TRAINING SCOPE of a workflow is every species spawned on its maps (and what they turn into),
  every species an event names, and the fixed classes, not only its TARGETS (13.3).
- The estimate uses training-cost.md's planning formula. Its constants are read from ONE
  machine-readable source, `poring_flow/data/training_cost.json`, which that document points to
  (Batt's Q26 proposal); nothing here restates a number. Compute hours and wall-clock hours are
  reported separately; wall = compute / availability.
- The editor never starts preparation work (13.4): this is the operator's to-do list.

Formula, applied as training-cost.md section 5 applies it (the contingency multiplies every part,
map prep included; section 1's formula text leaves that ambiguous):

    map prep  = new maps x map_prep_h x contingency
    collect   = sum(d_s) x collect_h_per_species x contingency          (S2 hours)
    train     = sum(d_s) x (budget x epochs x k / 3600) x contingency     (compute hours)
    wall[w]   = train / availability[w]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from typing import Any

from pydantic import BaseModel, ConfigDict

from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.lint import Detector, Finding, Resolver, lint
from poring_flow.lint.common import Consts, assigned_vars, handler_exprs
from poring_flow.lint.simulate import escape_kind
from poring_flow.sheet import World

FIXED_CLASSES = ("npc", "portal", "dying", "player")  # phase3-plan.md section 4


class Constants(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    doc: str
    version: int
    date: str
    status: str
    budget_frames_per_species: int
    epochs: int
    k_s_per_frame_epoch: float
    collect_h_per_species: float
    map_prep_h: float
    contingency: float
    availability: dict[str, float]
    mix_hours: dict[str, float]
    difficulty: dict[str, float]

    @property
    def train_h_per_species(self) -> float:
        return self.budget_frames_per_species * self.epochs * self.k_s_per_frame_epoch / 3600


@cache
def constants() -> Constants:
    text = (resources.files("poring_flow") / "data" / "training_cost.json").read_text("utf-8")
    return Constants.model_validate(json.loads(text))


@dataclass(frozen=True)
class Estimate:
    version: int
    status: str  # ESTIMATE until measured (training-cost.md section 6)
    species: tuple[tuple[int, str, float], ...]  # (mob id, difficulty class, d_s)
    sum_d: float
    new_maps: tuple[str, ...]
    map_prep_h: float
    collect_s2_h: float
    train_compute_h: float
    wall_h: dict[str, float]  # per availability window, and "mix" (night + day hours)


def estimate(
    new_species: dict[int, str], new_maps: list[str], c: Constants | None = None
) -> Estimate:
    """new_species: {mob id: difficulty class}; species already trained AND measured add nothing."""
    c = constants() if c is None else c
    rows = tuple((m, cls, c.difficulty[cls]) for m, cls in sorted(new_species.items()))
    sum_d = sum(d for _, _, d in rows)
    train = sum_d * c.train_h_per_species * c.contingency
    wall = {w: train / a for w, a in c.availability.items()}
    hours = sum(c.mix_hours.values())
    mix = sum(c.mix_hours[w] * c.availability[w] for w in c.mix_hours) / hours
    wall["mix"] = train / mix
    return Estimate(
        version=c.version,
        status=c.status,
        species=rows,
        sum_d=sum_d,
        new_maps=tuple(sorted(new_maps)),
        map_prep_h=len(new_maps) * c.map_prep_h * c.contingency,
        collect_s2_h=sum_d * c.collect_h_per_species * c.contingency,
        train_compute_h=train,
        wall_h=wall,
    )


# --- the training scope (13.3) ------------------------------------------------------------------
@dataclass(frozen=True)
class Scope:
    species: tuple[int, ...]  # every species to recognise
    targets: tuple[int, ...]
    ignore: tuple[int, ...]
    unlisted: tuple[int, ...]
    named_by_events: tuple[int, ...]
    fixed_classes: tuple[str, ...] = FIXED_CLASSES
    missing_maps: tuple[str, ...] = ()  # maps without a sheet: their species are unknown


def training_scope(flow: ir.Flow, world: World) -> Scope:
    consts = Consts(flow, assigned_vars(flow))
    blocks = list(flow.workflow.blocks) if flow.workflow else []
    spawned: set[int] = set()
    missing: list[str] = []
    for m in sorted({b.map.map for b in blocks}):
        sh = world.sheet(m)
        if sh is None:
            missing.append(m)
            continue
        spawned |= set(sh.spawned())
    turned: set[int] = set()
    todo = list(spawned)
    while todo:  # metamorphosis, transitively
        mob = world.mobs.get(todo.pop())
        for t in mob.turns_into if mob else []:
            if t not in spawned | turned:
                turned.add(t)
                todo.append(t)
    named: set[int] = set()
    for _, h, _, _ in ir.handler_bodies(flow):
        for _, e in handler_exprs(h):
            for s in ir.sub_exprs(e):
                if isinstance(s, ir.Sense) and s.sensor in ("sees", "count_visible"):
                    r = consts.ref(s.args.get("mob"), ir.MobRef)
                    if r is not None:
                        named.add(r.id)
    targets = {m.id for b in blocks for m in b.targets}
    ignore = {m.id for b in blocks for m in b.ignore}
    everything = spawned | turned | named | targets | ignore
    return Scope(
        species=tuple(sorted(everything)),
        targets=tuple(sorted(targets)),
        ignore=tuple(sorted(ignore - targets)),
        unlisted=tuple(sorted(everything - targets - ignore)),
        named_by_events=tuple(sorted(named)),
        missing_maps=tuple(missing),
    )


# --- the report (13.4) ----------------------------------------------------------------------------
@dataclass
class Report:
    flow: str
    environment: str
    scope: Scope
    new_species: dict[int, str]
    windows: dict[str, str] = field(default_factory=dict)  # window -> ok | MISSING (reason)
    npc_dialogs: dict[str, str] = field(default_factory=dict)  # block path -> ok | UNSUPPORTED
    routes_open: list[str] = field(default_factory=list)  # route findings
    badges: dict[str, str] = field(default_factory=dict)  # block -> verified | unverified | ...
    unsupported: list[str] = field(default_factory=list)  # binding findings
    escape: dict[str, str] = field(default_factory=dict)  # map block -> its hp_critical escape
    estimate: Estimate | None = None

    def open_items(self) -> list[str]:
        out = [f"species {m} untrained" for m in sorted(self.new_species)]
        out += [f"window {w}: {s}" for w, s in sorted(self.windows.items()) if s != "ok"]
        out += [f"npc dialog {p}: {s}" for p, s in sorted(self.npc_dialogs.items()) if s != "ok"]
        out += [f"route {r}" for r in self.routes_open]
        out += [
            f"block {b} {s}"
            for b, s in sorted(self.badges.items())
            if s not in ("verified", "core")
        ]
        return out

    def runnable(self) -> bool:
        """Run stays disabled while any item is open (proposal; open question 25)."""
        return not self.open_items()

    def summary(self) -> str:
        if self.runnable():
            return "runnable"
        species = len(self.new_species)
        blocks = sum(s not in ("verified", "core") for s in self.badges.values())
        rest = len(self.open_items()) - species - blocks
        parts = [f"{species} species untrained", f"{blocks} blocks unverified"]
        if rest:
            parts.append(f"{rest} other items open")
        return "not runnable: " + ", ".join(parts)

    def lines(self) -> list[str]:
        """The text panel of 13.4 (the editor renders the same data)."""
        s, e = self.scope, self.estimate
        new = ", ".join(f"d{d:g}" for _, _, d in e.species) if e else ""
        out = [
            f"Prepare: {self.flow} · {self.environment}",
            f"Species to recognise: {len(s.species)} (targets {len(s.targets)}, ignore "
            f"{len(s.ignore)}, unlisted {len(s.unlisted)}) · new: {len(self.new_species)}"
            + (f" ({new})" if new else ""),
            "UI windows: "
            + (" · ".join(f"{w} {st}" for w, st in sorted(self.windows.items())) or "none"),
            "NPC dialogs: "
            + (" · ".join(f"{p} {st}" for p, st in sorted(self.npc_dialogs.items())) or "none"),
            f"Routes: {len(self.routes_open)} open · Blocks: "
            f"{sum(v == 'verified' for v in self.badges.values())} verified, "
            f"{sum(v not in ('verified', 'core') for v in self.badges.values())} not",
        ]
        if e is not None:
            win = ", ".join(f"{k} {v:.1f} h" for k, v in e.wall_h.items())
            out += [
                f"AI preparation (training-cost.md, constants {e.status} v{e.version}):",
                f"  map prep ≈ {e.map_prep_h:.1f} h · collect ≈ {e.collect_s2_h:.1f} h (S2) · "
                f"compute ≈ {e.train_compute_h:.1f} h",
                f"  wall: {win}",
            ]
        out.append(
            f"[Run] {'enabled' if self.runnable() else 'disabled'}: "
            f"{len(self.open_items())} items open"
        )
        return out


def report(
    flow: ir.Flow,
    world: World,
    *,
    resolver: Resolver | None = None,
    detector: Detector | None = None,
    cat: Catalogue | None = None,
    findings: list[Finding] | None = None,
) -> Report:
    from poring_skills.resolve import Unsupported

    cat = cat or catalogue()
    det = detector or Detector()
    findings = (
        findings
        if findings is not None
        else lint(flow, world=world, resolver=resolver, detector=det, cat=cat)
    )
    scope = training_scope(flow, world)
    new: dict[int, str] = {
        m: (world.mobs[m].difficulty if m in world.mobs else "normal")
        for m in scope.species
        if m not in det.measured
    }
    blocks = list(flow.workflow.blocks) if flow.workflow else []
    maps = sorted({b.map.map for b in blocks})
    rep = Report(flow=flow.name, environment=_env(flow), scope=scope, new_species=new)
    consts = Consts(flow, assigned_vars(flow))
    for site in ir.sites(flow):
        for a in ir.actions_in(site.stmt):
            cb = cat.blocks.get(a.block)
            if cb is None:
                continue
            rep.badges[a.block] = cb.status
            status = "ok"
            if resolver is not None and cb.status != "core":
                try:
                    resolver(a.block, a.concept, _params(a, consts))
                except Unsupported as u:
                    status = f"UNSUPPORTED ({u.layer} {u.key})"
                    rep.badges[a.block] = "unsupported here"
            for need in cb.bindings_needed:
                if need.startswith("L2.window."):
                    w = need.removeprefix("L2.window.")
                    rep.windows[w] = "ok" if status == "ok" else f"MISSING {status}"
            if a.block in (
                "talk_npc",
                "choose_menu",
                "set_save_point",
                "kafra_store",
                "kafra_withdraw",
                "kafra_teleport",
            ):
                rep.npc_dialogs[site.path] = status
        if isinstance(site.stmt, ir.TakeExit) and site.stmt.exit.kind == "npc_warp":
            rep.npc_dialogs[site.path] = "ok"
    rep.routes_open = [f.message for f in findings if f.rule == "routes" and f.severity == "error"]
    rep.unsupported = [f.message for f in findings if f.rule == "bindings"]
    for b in blocks:
        k = escape_kind(world.sheet(b.map.map))
        rep.escape[b.name] = {
            "fly_wing": "Fly Wing",
            "butterfly_wing": "Butterfly Wing",
            "none": "NONE: stops the run",
        }.get(k or "", "unknown (no map flags)")
    rep.estimate = estimate(new, [m for m in maps if m not in det.prepared_maps])
    return rep


def _env(flow: ir.Flow) -> str:
    t = flow.target
    return f"{t.server} / {t.client} / {t.locale} / {t.path}"


def _params(a: ir.ActionStmt, consts: Consts) -> dict[str, str]:
    from poring_flow.lint.semantics import _params as p

    return p(a, consts)


def as_dict(e: Estimate) -> dict[str, Any]:
    return {
        "version": e.version,
        "status": e.status,
        "sum_d": e.sum_d,
        "map_prep_h": e.map_prep_h,
        "collect_s2_h": e.collect_s2_h,
        "train_compute_h": e.train_compute_h,
        "wall_h": dict(e.wall_h),
    }
