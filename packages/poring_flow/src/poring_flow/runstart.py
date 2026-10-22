"""The run-start check: the gate a LIVE run passes before its first input (ADR-0020 section 5:
"the linter re-runs at run start"; Batt 2026-10-09, contradictions #6: an unsupported binding is a
READINESS item that blocks the RUN, not the design).

Nothing starts a live run yet: MW2 is SIMULATE only and the live executor is MW3. So this module is
the check MW3's executor must call before its first input; it is added now so that the readiness
severity has its enforcement point in code, tested, and not only in prose.

- It re-lints the flow against the CURRENT static data and bindings (they may have changed since
  the flow was linted or approved) and refuses on any ERROR and any READINESS item.
- It fails closed: no static data (no map sheets) or no resolver is a refusal, never a pass,
  because the linter would then skip the very checks the run depends on.
- If an approved hash is given, the flow's hash must equal it (approval binds a hash, section 6).
- The flow's `max_runtime_s` must not exceed the CONFIGURED maximum run time (Batt 2026-10-09,
  contradictions #17: a Settings value, not a constant), given as `runtime_max_s`; without a
  configured value the run is refused.
- A flow whose map nodes name ZONES (Amendment A 4, DRAFT, 2026-10-21) is refused without a zones
  provider (`zones_provider`): the file checks would be skipped. With one, the linter refuses a
  changed, missing, unreadable or unnamed file. (B1 keeps a flow WITHOUT zones references runnable
  without a provider; the live executor (B4) passes one always, so that a file the node does not
  name is caught.)
- A flow that hunts with the MELEE RING (the hunt block's engage_source `melee_ring`, Batt
  2026-10-22; lint/hunt.py) is refused unless the run's ATTESTED environment (`server`: the
  interlock's attested server id, which only the run knows) is the lab's own server
  (`lint.hunt.LAB_SERVERS`) and the flow's target, and unless the static data the species check
  read is that server's. Never allowed by default: no attested server is a refusal. The linter
  already refuses the design on another target server, an IGNORE list or a non-target species.
- Simulation is design time and is NOT gated: `runtime.Sim` and `trace.simulate` run a flow that
  has readiness items (that is how a flow is designed before its bindings land).
"""

from __future__ import annotations

from dataclasses import dataclass

from poring_flow import ir
from poring_flow.catalogue import catalogue
from poring_flow.lint import Detector, Finding, Resolver, lint
from poring_flow.lint.hunt import LAB_SERVERS, MELEE_RING, melee_ring_paths
from poring_flow.sheet import World
from poring_flow.zones import ZonesProvider


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    flow_hash: str
    errors: tuple[str, ...]  # the design errors' messages
    readiness: tuple[str, ...]  # the readiness items' messages (bindings not there yet)
    reasons: tuple[str, ...]  # other refusals: no static data, no resolver, a hash mismatch

    def summary(self) -> str:
        if self.allowed:
            return "run allowed"
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error{'s' * (len(self.errors) != 1)}")
        if self.readiness:
            parts.append(f"{len(self.readiness)} readiness item{'s' * (len(self.readiness) != 1)}")
        parts += list(self.reasons)
        return "run refused: " + ", ".join(parts)


class RunRefused(Exception):  # noqa: N818 -- a refusal, named for what the caller sees
    def __init__(self, verdict: Verdict) -> None:
        super().__init__(verdict.summary())
        self.verdict = verdict


def verdict(
    flow: ir.Flow,
    findings: list[Finding],
    *,
    world_loaded: bool,
    resolver_given: bool,
    runtime_max_s: int | None,
    approved_hash: str | None = None,
    zones_loaded: bool = False,
    server: str | None = None,
    world_server: str | None = None,
) -> Verdict:
    """The gate's verdict from findings already computed (the editor shows it beside the lint).
    `runtime_max_s` is the CONFIGURED maximum run time (#17): None refuses (fail closed).
    `zones_loaded`: the findings were computed with a zones provider. `server`: the run's ATTESTED
    environment (None: not known here); `world_server`: the server of the static data linted
    against. Both matter only to a melee-ring hunt."""
    h = ir.flow_hash(flow)
    reasons = []
    reasons += _melee_ring(flow, server, world_server)
    if not world_loaded:
        reasons.append("no static data: references and routes are unchecked")
    if not resolver_given:
        reasons.append("no resolver: bindings are unchecked")
    blocks = flow.workflow.blocks if flow.workflow else []
    if not zones_loaded and any(b.zones is not None for b in blocks):
        reasons.append("no zones data: the map nodes' zones references are unchecked")
    if runtime_max_s is None:
        reasons.append("no configured maximum run time")
    elif flow.max_runtime_s > runtime_max_s and not any(f.rule == "runtime_max" for f in findings):
        reasons.append(
            f"max_runtime_s {flow.max_runtime_s} is above the configured maximum {runtime_max_s}"
        )
    if approved_hash is not None and approved_hash != h:
        reasons.append(f"the flow's hash {h[:12]} is not the approved {approved_hash[:12]}")
    errs = tuple(f.message for f in findings if f.severity == "error")
    ready = tuple(f.message for f in findings if f.severity == "readiness")
    return Verdict(not (errs or ready or reasons), h, errs, ready, tuple(reasons))


def check(
    flow: ir.Flow,
    *,
    world: World | None,
    resolver: Resolver | None,
    detector: Detector | None = None,
    approved_hash: str | None = None,
    runtime_max_s: int | None = None,
    zones_provider: ZonesProvider | None = None,
    server: str | None = None,
) -> Verdict:
    """Re-lint NOW and return the verdict (no exception). `runtime_max_s`: the configured
    maximum run time (#17); without one the run is refused. `zones_provider`: the map zones.
    `server`: the ATTESTED environment the run would act on (a melee-ring hunt needs the lab's)."""
    findings = lint(
        flow,
        world=world,
        resolver=resolver,
        detector=detector,
        runtime_max_s=runtime_max_s,
        zones_provider=zones_provider,
    )
    return verdict(
        flow,
        findings,
        world_loaded=world is not None,
        resolver_given=resolver is not None,
        runtime_max_s=runtime_max_s,
        approved_hash=approved_hash,
        zones_loaded=zones_provider is not None,
        server=server,
        world_server=world.server if world is not None else None,
    )


def require(
    flow: ir.Flow,
    *,
    world: World | None,
    resolver: Resolver | None,
    detector: Detector | None = None,
    approved_hash: str | None = None,
    runtime_max_s: int | None = None,
    zones_provider: ZonesProvider | None = None,
    server: str | None = None,
) -> Verdict:
    """The call a live run makes before its first input: returns the verdict, or raises
    `RunRefused` (with every reason) when the run may not start. `server`: the ATTESTED
    environment (the interlock's attested server id)."""
    v = check(
        flow,
        world=world,
        resolver=resolver,
        detector=detector,
        approved_hash=approved_hash,
        runtime_max_s=runtime_max_s,
        zones_provider=zones_provider,
        server=server,
    )
    if not v.allowed:
        raise RunRefused(v)
    return v


def _melee_ring(flow: ir.Flow, server: str | None, world_server: str | None) -> list[str]:
    """A melee-ring hunt starts only on the lab's own server, attested (never by default)."""
    paths = melee_ring_paths(flow, {n: b.spec for n, b in catalogue().blocks.items()})
    if not paths:
        return []
    lab = ", ".join(sorted(LAB_SERVERS))
    what = f"{len(paths)} hunt{'s' * (len(paths) != 1)} with engage_source {MELEE_RING}"
    out = []
    if server is None:
        out.append(f"{what}: no attested environment (a melee-ring hunt starts only on {lab})")
    elif server not in LAB_SERVERS:
        out.append(f"{what}: the attested environment {server} is not the lab's ({lab})")
    elif server != flow.target.server:
        out.append(f"{what}: the attested environment {server} is not the flow's target "
                   f"{flow.target.server}")  # fmt: skip
    if world_server is not None and world_server != flow.target.server:
        out.append(f"{what}: the species were checked on {world_server}'s static data, not on "
                   f"{flow.target.server}'s")  # fmt: skip
    return out
