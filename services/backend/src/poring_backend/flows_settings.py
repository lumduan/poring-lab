"""The flows' run-time limits: the INTERFACE the /flows routes read (Batt 2026-10-09, ADR-0020
contradictions #17: max_runtime_s is NOT hard-coded).

    runtime_limits(state) -> (default_s, max_s)

- `default_s`: what a NEW flow starts with (the editor's "New"), in seconds.
- `max_s`: the most a flow may set; the linter reports a flow above it (an ERROR) and the run-start
  check (`poring_flow.runstart`, `runtime_max_s=`) refuses it. No configured maximum = refuse.

Both are human settings: a global default and maximum on the Settings page, human-only writes like
the environments store (`settings/`, the backend only; the console's Origin and CSRF token; an
audit log of every change). That store and its page are ANOTHER piece of work, built against this
function. Until it lands, this returns Batt's defaults: 4 h and 24 h.

A flow's own `max_runtime_s` lives in the flow, a file the browser exports and imports, so its
change shows in the flow's JSON diff; a change of the global values is the store's audit log.
"""

from __future__ import annotations

from typing import Any

DEFAULT_S = 14_400  # 4 h (Batt 2026-10-09)
MAX_S = 86_400  # 24 h (Batt 2026-10-09)


def runtime_limits(state: Any) -> tuple[int, int]:
    """(default_s, max_s) for flows, from the human settings; the defaults until the Settings
    store provides them. `state` is the backend's AppState (unused until then)."""
    del state
    return DEFAULT_S, MAX_S
