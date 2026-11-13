"""Linter layer 2: the box's MODEL and its monsters' RECIPES (live blocks stage 4a, Batt
2026-11-13: "break the core into functions, e.g. attack_myst_case, attack_cookie"; docs/planning/
live-blocks.md 3.4, ADR-0020 Amendment H). The rules are poring_flow.recipes' (the ONE place the
live player reads too); here they become findings, each named by its rule:

- use_model_place (error): use_model stands in a map node's main, one statement, before its
  dungeon_hunt; one per main;
- use_model_model (error): it names, as text, a LIVE detector of models.yaml trained for the map,
  that names the monsters the runner strikes;
- recipe_model (error): a monster's recipe (a function attack_<class>) with no use_model;
- recipe_class (error): attack_<class> names a class the model lacks, or one the runner never
  strikes (garm_baby: its Fly Wing rule);
- recipe_input / recipe_priority (error): a recipe takes (t, priority=N): its target first, the
  priority a number above 0, at most 10;
- recipe_target / recipe_step / recipe_order (error): its body is the primitives on its own input,
  the hunt core's knife_on() / knife_back() and use_skill, in an order the runner plays
  (recipes.SHAPES; each mistake named);
- recipe_skill (warning; an error without a hotbar key): use_skill(key=...) in a recipe is linted
  and does not play live in 4a (4b);
- recipe_primitive / recipe_call (error): the primitives stand only in a recipe, and no block
  calls a recipe (the hunt core asks it at its lock);
- recipe_default (info): a monster the runner strikes with no recipe: the runner's own.
"""

from __future__ import annotations

from poring_flow import recipes as rc
from poring_flow.lint.common import Ctx


def check(ctx: Ctx) -> None:
    for i in rc.analyse(ctx.flow)[1]:
        ctx.add(i.rule, i.severity, 2, i.path, i.words)
