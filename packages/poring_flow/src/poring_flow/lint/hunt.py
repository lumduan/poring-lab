"""Block parameters that are RULE VERSIONS, and blocks that attack the map block's targets
(ADR-0020 Amendment A 1 + 3, DRAFT; docs/planning/blocks-from-hunt-flow.md B1, 2026-10-21).

- `rule_version` (layer 1): a parameter with `choices` in the registry (the hunt block's strike,
  engage, dead, loot and search) takes one of them, as a literal. A rule version is `name@N`: its
  numbers are the ones PARAMS[N] ran (scripts/hunt_config.py); "the engine refuses an unknown rule
  version", and so does the linter, before approval.
- `needs_targets` (layer 2): a block that attacks the map block's TARGET species (13.3) runs in a
  map block, and that block lists its targets.
"""

from __future__ import annotations

from poring_flow import ir
from poring_flow.lint.common import Ctx


def check(ctx: Ctx) -> None:
    for site in ir.sites(ctx.flow):
        for a in ir.actions_in(site.stmt):
            blk = ctx.cat.blocks.get(a.block)
            if blk is None:
                continue  # unknown_block (layer 1)
            for p in blk.spec.params:
                if not p.choices or p.name not in a.params:
                    continue
                e = a.params[p.name]
                val = e.value if isinstance(e, ir.Lit) else None
                if not isinstance(val, str) or val not in p.choices:
                    shown = repr(val) if isinstance(val, str) else ctx.src(e)
                    ctx.add(
                        "rule_version",
                        "error",
                        1,
                        site.path,
                        f"{a.block}'s {p.name} takes a rule version ({', '.join(p.choices)}), "
                        f"not {shown}",
                    )
            if blk.spec.needs_targets:
                if site.block is None:
                    ctx.add(
                        "needs_targets",
                        "error",
                        2,
                        site.path,
                        f"{a.block} attacks the map block's TARGET species (13.3): it runs in a "
                        "map block",
                    )
                elif not site.block.targets:
                    ctx.add(
                        "needs_targets",
                        "error",
                        2,
                        site.path,
                        f"{a.block} attacks only the TARGET species, and {site.block.name} lists "
                        "none (13.3)",
                    )
