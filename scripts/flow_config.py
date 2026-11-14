"""THE FLOW CONFIG for the runner side: every number and key a person may set (Batt 2026-11-13).

➡️ 2026-11-14 ~15:2x (Batt: "make them ALL blocks, no hardcoding like this"; live-blocks.md
section 12): the registry lives in ``poring_flow.settings`` (packages/poring_flow), so the project
model's lint, the catalogue and the browser read the same table as the runner. This module
re-exports it for the runner side: scripts/flow_run.py (the Run helper), scripts/flow_play.py (the
live block player), the stage tools, dungeon_hunt.py's --tune and their tests.

What changed with it:
- the settings are BLOCKS of a project (its tabs' variables: ``poring_flow.settings.node_values``,
  the map node's over Global's over the default); a Run reads them from the checked project;
- every field has a DEFAULT (``DEFAULTS``: our values); flow_run.FLOWS' ``defaults`` is derived;
- the settings FILE (settings/flowrun/config.json, its GET / PUT /flows/config) is gone: it was
  empty when it went ({"v": 2, "global": {}, "maps": {}}), so nothing was imported from it.
"""

from __future__ import annotations

from poring_flow.settings import (
    BLOCKS,
    BY_NAME,
    BY_VAR,
    DEFAULTS,
    FIELDS,
    GAME_PX,
    GROUPS,
    KEY_FIELDS,
    KEYS,
    KEYS_SRC,
    KINDS,
    NOT_SETTINGS,
    SWITCHES,
    TABS,
    VAR_NAMES,
    VERSION,
    Field,
    Level,
    NodeValues,
    argv,
    check_level,
    clash,
    doc_levels,
    flag_defaults,
    flag_value,
    in_use,
    keys_problem,
    node_values,
    norm,
    not_in_use_why,
    problem_of,
    registry,
    shown,
    with_keys,
)

__all__ = [
    "BLOCKS",
    "BY_NAME",
    "BY_VAR",
    "DEFAULTS",
    "FIELDS",
    "GAME_PX",
    "GROUPS",
    "KEY_FIELDS",
    "KEYS",
    "KEYS_SRC",
    "KINDS",
    "NOT_SETTINGS",
    "SWITCHES",
    "TABS",
    "VAR_NAMES",
    "VERSION",
    "Field",
    "Level",
    "NodeValues",
    "argv",
    "check_level",
    "clash",
    "doc_levels",
    "flag_defaults",
    "flag_value",
    "in_use",
    "keys_problem",
    "node_values",
    "norm",
    "not_in_use_why",
    "problem_of",
    "registry",
    "shown",
    "with_keys",
]
