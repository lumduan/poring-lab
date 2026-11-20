"""A Run's options on this bot server: what it does after a CODE error (Batt 2026-11-19).

Batt: "every time it stops by an error of the code -- not a logic error, a death or the game
dropping out -- the bot should check the character and run on by itself if she is ready to hunt;
make it a retry option." The file is ``settings/flowrun/options.json`` (the Run helper's folder):

    {"v": 1, "retry_max": 3, "retry_wait_s": 20, "bag_count": true}

``bag_count`` (Batt 2026-11-20, Economy option b-i; docs/planning/econ-bag-count.md): the Run
counts the bag at its start and its end (after a Stop too: "count, then stop"; a second Stop
skips it) and writes the Run's economy for the /economy page. On by default; off = no count.

- WRITER: the backend only (routes_flowrun PUT /flows/run/options), from the /flows page behind
  the same human-only gate as Run (routes_settings.write_gate).
- READER: the live player (scripts/flow_play.py) at each retry, so a change applies to the run
  that is playing.
- NO FILE, or one that does not parse = the defaults (a retry option loosens nothing: it never
  presses before the start check has passed again).

Pure (stdlib only), shared by the backend and the host scripts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE_NAME = "options.json"
VERSION = 1
RETRY_MAX_RANGE = (0, 20)  # 0 = off
RETRY_WAIT_RANGE = (5, 600)  # seconds before the check, so a passing hiccup can clear
DEFAULT_RETRY_MAX = 3
DEFAULT_RETRY_WAIT_S = 20
DEFAULT_BAG_COUNT = True


@dataclass(frozen=True)
class RunOptions:
    retry_max: int = DEFAULT_RETRY_MAX
    retry_wait_s: int = DEFAULT_RETRY_WAIT_S
    bag_count: bool = DEFAULT_BAG_COUNT

    def as_json(self) -> dict[str, Any]:
        return {"v": VERSION, "retry_max": self.retry_max, "retry_wait_s": self.retry_wait_s,
                "bag_count": self.bag_count}  # fmt: skip


DEFAULTS = RunOptions()


def _int_in(v: Any, lo_hi: tuple[int, int]) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if lo_hi[0] <= v <= lo_hi[1] else None


def parse(doc: Any) -> tuple[RunOptions | None, str | None]:
    """PURE: the options of a document, or (None, why)."""
    if not isinstance(doc, dict):
        return None, "not an object"
    extra = set(doc) - {"v", "retry_max", "retry_wait_s", "bag_count"}
    if extra:
        return None, f"unknown keys: {', '.join(sorted(extra))}"
    rm = _int_in(doc.get("retry_max", DEFAULT_RETRY_MAX), RETRY_MAX_RANGE)
    if rm is None:
        return None, f"retry_max: a whole number {RETRY_MAX_RANGE[0]}..{RETRY_MAX_RANGE[1]}"
    rw = _int_in(doc.get("retry_wait_s", DEFAULT_RETRY_WAIT_S), RETRY_WAIT_RANGE)
    if rw is None:
        return None, f"retry_wait_s: whole seconds {RETRY_WAIT_RANGE[0]}..{RETRY_WAIT_RANGE[1]}"
    bag = doc.get("bag_count", DEFAULT_BAG_COUNT)
    if not isinstance(bag, bool):
        return None, "bag_count: true or false"
    return RunOptions(rm, rw, bag), None


def load(folder: Path) -> RunOptions:
    """The options in ``folder`` (the Run helper's), else the defaults."""
    try:
        got, _why = parse(json.loads((folder / FILE_NAME).read_text()))
    except (OSError, ValueError):
        return DEFAULTS
    return got or DEFAULTS


def words(o: RunOptions) -> str:
    """The option in a person's words (the Run's log, the page)."""
    if o.retry_max == 0:
        return "after a code error the run ends (retry off)"
    return (
        f"after a code error she is checked again in {o.retry_wait_s} s and hunts on if "
        f"ready, at most {o.retry_max} time{'s' if o.retry_max != 1 else ''} a run"
    )
