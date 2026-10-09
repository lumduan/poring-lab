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
- Simulation is design time and is NOT gated: `runtime.Sim` and `trace.simulate` run a flow that
  has readiness items (that is how a flow is designed before its bindings land).
"""

from __future__ import annotations

from dataclasses import dataclass

from poring_flow import ir
from poring_flow.lint import Detector, Finding, Resolver, lint
from poring_flow.sheet import World


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
) -> Verdict:
    """The gate's verdict from findings already computed (the editor shows it beside the lint).
    `runtime_max_s` is the CONFIGURED maximum run time (#17): None refuses (fail closed)."""
    h = ir.flow_hash(flow)
    reasons = []
    if not world_loaded:
        reasons.append("no static data: references and routes are unchecked")
    if not resolver_given:
        reasons.append("no resolver: bindings are unchecked")
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
) -> Verdict:
    """Re-lint NOW and return the verdict (no exception). `runtime_max_s`: the configured
    maximum run time (#17); without one the run is refused."""
    findings = lint(
        flow, world=world, resolver=resolver, detector=detector, runtime_max_s=runtime_max_s
    )
    return verdict(
        flow,
        findings,
        world_loaded=world is not None,
        resolver_given=resolver is not None,
        runtime_max_s=runtime_max_s,
        approved_hash=approved_hash,
    )


def require(
    flow: ir.Flow,
    *,
    world: World | None,
    resolver: Resolver | None,
    detector: Detector | None = None,
    approved_hash: str | None = None,
    runtime_max_s: int | None = None,
) -> Verdict:
    """The call a live run makes before its first input: returns the verdict, or raises
    `RunRefused` (with every reason) when the run may not start."""
    v = check(
        flow,
        world=world,
        resolver=resolver,
        detector=detector,
        approved_hash=approved_hash,
        runtime_max_s=runtime_max_s,
    )
    if not v.allowed:
        raise RunRefused(v)
    return v
