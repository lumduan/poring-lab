"""Linter layer 2: THE TICK made visible (live blocks stage 5c, Batt 2026-11-15: "dungeon_hunt.py
should be blocks the user sees and can edit himself"; docs/planning/live-blocks.md 15.3). The rules
are poring_flow.tick's (the ONE place the live player reads too), each an error on its block:

- tick_step: tick() holds the step blocks only, each once, in run()'s order; a SAFETY or REQUIRED
  step left out (the words name the step and what it protects); a step block outside tick();
- tick_place: a tick() where no hunt loop drives the hunt core; a call of tick().
"""

from __future__ import annotations

from poring_flow import tick as tk
from poring_flow.lint.common import Ctx


def check(ctx: Ctx) -> None:
    for i in tk.analyse(ctx.flow)[1]:
        ctx.add(i.rule, i.severity, 2, i.path, i.words)
