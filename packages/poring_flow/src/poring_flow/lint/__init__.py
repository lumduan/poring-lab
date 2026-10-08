"""The flow linter, layers 1-3 (ADR-0020 section 5, 13.5, 13.6.9).

`lint(flow, world=..., resolver=..., detector=...)` -> findings, each with its rule, severity,
layer, node path and message (`Finding.message` = "<path>: <text>"). Errors are short sentences
naming the node by its path; the owner reads the same text the LLM drafter gets back.

Inputs:
- `world`: the server's static data (map sheets, mobs, items; `poring_flow.sheet`). None means not
  loaded: the checks that need it are skipped, and the bindings check still fails closed.
- `resolver`: resolves an action's bindings for the target environment, raising
  `poring_skills.resolve.Unsupported`. `default_resolver(flow.target)` uses the real L1/L2/L3
  files; tests inject their own.
- `detector`: what perception can do today (species naming, measured species).

Layers 4-6 (approval, runtime, interlock) are not here: the preparation report (`poring_flow.prep`)
feeds approval; the interlock check of layer 6 is later work.
"""

from __future__ import annotations

from pathlib import Path

from poring_flow import ir
from poring_flow.catalogue import Catalogue, catalogue
from poring_flow.lint import events, loops, semantics, simulate, structure
from poring_flow.lint.common import Ctx, Detector, Finding, Resolver
from poring_flow.sheet import World

__all__ = ["Detector", "Finding", "Resolver", "default_resolver", "errors", "lint"]

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


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
) -> list[Finding]:
    ctx = Ctx(flow, cat or catalogue(), world, resolver, detector or Detector())
    structure.check(ctx)
    semantics.check(ctx)
    simulate.check(ctx)
    loops.check(ctx)
    events.check(ctx)
    return sorted(ctx.findings, key=lambda f: (f.layer, SEVERITY_ORDER[f.severity]))


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]
