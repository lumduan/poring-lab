"""Linter layer 2: the HUNT LOOP, the hunt core's steps as live blocks (live blocks stage 5b-2,
Batt 2026-11-13: "break the runner into blocks"; docs/planning/live-blocks.md 13.4 and 14). The
rules are poring_flow.huntloop's (the ONE place the live player reads too); here they become
findings, each an error named by its rule, on the block it is about:

- hunt_primitive: a hunt block (find_target, choose_target, walk_to_target, look, fight, use_skill)
  outside the hunt loop (the recipe primitives outside a recipe and the loop: recipe_primitive);
- hunt_loop_place / hunt_loop_input: hunt_loop(t) on a map node whose main runs dungeon_hunt, with
  one input, the target;
- hunt_statement: in the loop, its blocks and if / while / repeat / for / set / break / continue /
  return only (no wait, press_key, call, stop or exit: the runner plays nothing else there);
- hunt_sensor: no sensor in its conditions but known(t);
- hunt_target: a block's target is a variable (find_target()'s value);
- hunt_spin: every while begins with t = find_target() and holds, at its top level, a block that
  plays the fight to its end on t (fight, wait_kill, loot): else it could spin with no step taken;
- hunt_skill: use_skill presses a declared role key (dungeon_hunt's heal key) between two steps.
"""

from __future__ import annotations

from poring_flow import huntloop as hl
from poring_flow.lint.common import Ctx


def check(ctx: Ctx) -> None:
    for i in hl.analyse(ctx.flow)[1]:
        ctx.add(i.rule, i.severity, 2, i.path, i.words)
