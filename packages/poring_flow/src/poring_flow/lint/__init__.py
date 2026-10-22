"""The flow linter, layers 1-3 (ADR-0020 section 5, 13.5, 13.6.9).

`lint(flow, world=..., resolver=..., detector=...)` -> findings, each with its rule, severity,
layer, node path and message (`Finding.message` = "<path>: <text>"). Errors are short sentences
naming the node by its path; the owner reads the same text the LLM drafter gets back.

Severities: `error` (the design is wrong: it cannot be approved), `readiness` (an unsupported
binding: listed, it blocks the RUN, not the design; Batt 2026-10-09, contradictions #6), `warning`,
`info`. `blocking()` is what the run-start check refuses on (`poring_flow.runstart`).

Inputs:
- `world`: the server's static data (map sheets, mobs, items; `poring_flow.sheet`). None means not
  loaded: the checks that need it are skipped, and the bindings check still fails closed.
- `resolver`: resolves an action's bindings for the target environment, raising
  `poring_skills.resolve.Unsupported`. `default_resolver(flow.target)` uses the real L1/L2/L3
  files; tests inject their own.
- `detector`: what perception can do today (species naming, measured species).
- `zones`: the map zones provider (`poring_flow.zones`, Amendment A 4): each map's zones file, as
  the loader reads it. None means not loaded: the file checks are skipped, and the run-start check
  refuses a flow that names zones (fail closed).
- `routes`: the patrol routes provider (`poring_flow.patrol`, Batt 2026-10-22): each map's routes
  file, as the loader reads it. None means not loaded: a patrol hunt's file checks are skipped,
  and the run-start check refuses a flow with one (fail closed).

Layers 4-6 (approval, runtime, interlock) are not here: the preparation report (`poring_flow.prep`)
feeds approval; the interlock check of layer 6 is later work.
"""

from __future__ import annotations

from pathlib import Path

from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.lint import events, hunt, loops, semantics, simulate, structure, where, zones
from poring_flow.lint.common import Ctx, Detector, Finding, Resolver
from poring_flow.patrol import RoutesProvider
from poring_flow.sheet import World
from poring_flow.zones import ZonesProvider

__all__ = [
    "Detector",
    "Finding",
    "Resolver",
    "blocking",
    "default_resolver",
    "errors",
    "lint",
    "readiness",
]

SEVERITY_ORDER = {"error": 0, "readiness": 1, "warning": 2, "info": 3}


def default_resolver(target: ir.Target, l3_root: Path | None = None) -> Resolver:
    """poring_skills.resolve for the flow's target (client, server, locale, path), fail closed."""
    from poring_skills.resolve import L3_DIR, ActiveEnv, Unsupported, resolve
    from poring_skills.schema import load_l1

    env = ActiveEnv(target.client, target.server, target.locale, target.path)
    l1 = load_l1()
    root = L3_DIR if l3_root is None else l3_root

    def res(block: str, concept: str, params: dict[str, str]) -> None:
        if concept not in l1:
            raise Unsupported(concept, "L1", concept, "not written in L1 yet")
        resolve(l1[concept], env, params, l3_root=root)

    return res


def lint(
    flow: ir.Flow,
    *,
    world: World | None = None,
    resolver: Resolver | None = None,
    detector: Detector | None = None,
    cat: Catalogue | None = None,
    runtime_max_s: int | None = None,
    zones_provider: ZonesProvider | None = None,
    routes_provider: RoutesProvider | None = None,
) -> list[Finding]:
    """`runtime_max_s`: the CONFIGURED maximum run time (#17; the backend's
    `flows_settings.runtime_limits`); None skips that check here (the run-start check refuses
    without one). `zones_provider`: the map zones (Amendment A 4); None skips the file checks.
    `routes_provider`: the patrol routes (7d); None skips a patrol hunt's file checks."""
    ctx = Ctx(flow, cat or catalogue(), world, resolver, detector or Detector(), zones_provider,
              routes=routes_provider)  # fmt: skip
    if runtime_max_s is not None and flow.max_runtime_s > runtime_max_s:
        ctx.add(
            "runtime_max",
            "error",
            1,
            "",
            f"max_runtime_s {flow.max_runtime_s} is above the configured maximum {runtime_max_s} "
            "(the Settings page)",
        )
    structure.check(ctx)
    semantics.check(ctx)
    simulate.check(ctx)
    loops.check(ctx)
    events.check(ctx)
    where.check(ctx)  # the /where budget (#10)
    hunt.check(ctx)  # rule versions, options; targets (2026-10-21); melee ring, patrol route
    zones.check(ctx)  # the map node's zones (Amendment A 4, 2026-10-21)
    return sorted(ctx.findings, key=lambda f: (f.layer, SEVERITY_ORDER[f.severity]))


def errors(findings: list[Finding]) -> list[Finding]:
    """The design errors (approval refuses them). Readiness items are NOT errors (#6)."""
    return [f for f in findings if f.severity == "error"]


def readiness(findings: list[Finding]) -> list[Finding]:
    """Bindings not there yet for the target environment: the run waits for them (#6)."""
    return [f for f in findings if f.severity == "readiness"]


def blocking(findings: list[Finding]) -> list[Finding]:
    """What the run-start check refuses on: every error and every readiness item."""
    return [f for f in findings if f.severity in ("error", "readiness")]
