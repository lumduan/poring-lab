"""The Run log: what "What she does" says, kept as HISTORY (Batt 2026-11-21).

Batt: "keep the logs of What she does as history, so they can be looked at later; set it on the
/settings page: whether to record (the default: not), the folder (the default logs/bot/<named by
the run's start time>; a NAS folder if wanted), and a retention by the logs' total size, e.g.
100 MB: when full, the oldest is written over, like a CCTV camera." He teaches log keeping and log
analysis (in quant work, trade logs feed the backtests), so each Run is kept twice: JSON lines to
analyse, plain text to read.

The settings are ONE file of the human-only settings store, ``settings/run-log.json``:

    {"v": 1, "revision": 2, "record": true, "folder": "logs/bot", "max_total_mb": 100}

- WRITER: the backend only (routes_runlog.py), on a person's Save (routes_settings.write_gate).
- READER: the Run helper (scripts/flow_run.py), at every Run's start: a Save applies to the next
  Run.
- NO FILE = the default: not recorded. A file that does not parse: not recorded either (the Run
  plays on; its story says why), never a guess.
- ``folder``: absolute, or relative to the install's checkout; no ``..`` part (a person gives an
  absolute path instead). Each Run gets its own folder in it, named by its start time
  (``run_dir_name``): ``story.jsonl`` and ``story.log``.
- Retention (``plan_deletes``): after a Run starts and when it ends, while the Run folders in
  ``folder`` hold more than ``max_total_mb``, the OLDEST is deleted -- only folders named like a
  Run's (RUN_DIR_RE), never the Run being written, never any other file.

This module is pure (stdlib only): the format, its limits and its checks, shared by the backend
and the helper so the two cannot drift.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

FILE_NAME = "run-log.json"
VERSION = 1
DEFAULT_FOLDER = "logs/bot"
DEFAULT_MAX_MB = 100
MAX_MB_LO, MAX_MB_HI = 1, 1_000_000  # 1 MB .. ~1 TB
MAX_FOLDER = 512
STORY_JSONL, STORY_TEXT = "story.jsonl", "story.log"
# a Run's folder: its start time (the server's zone), then the helper's run id
RUN_DIR_RE = re.compile(r"\d{8}-\d{6}(-[A-Za-z0-9_]{1,40})?")


@dataclass(frozen=True)
class Store:
    revision: int = 0
    record: bool = False
    folder: str = DEFAULT_FOLDER
    max_total_mb: int = DEFAULT_MAX_MB

    def as_json(self) -> dict[str, Any]:
        return {"v": VERSION, "revision": self.revision, "record": self.record,
                "folder": self.folder, "max_total_mb": self.max_total_mb}  # fmt: skip


DEFAULT = Store()


def folder_problem(folder: Any) -> str | None:
    """PURE: why ``folder`` cannot be the Run log's folder (None: it can)."""
    if not isinstance(folder, str) or not folder.strip():
        return "folder_empty"
    if len(folder) > MAX_FOLDER:
        return "folder_too_long"
    if any(c in folder for c in "\x00\n\r"):
        return "folder_bad_character"
    parts = [p for p in folder.replace("\\", "/").split("/") if p]
    if ".." in parts:
        return "folder_dotdot"
    if not parts:
        return "folder_root"
    return None


def max_problem(mb: Any) -> str | None:
    """PURE: why ``mb`` cannot be the total size cap (None: it can)."""
    if isinstance(mb, bool) or not isinstance(mb, int):
        return "max_not_a_whole_number"
    if not MAX_MB_LO <= mb <= MAX_MB_HI:
        return "max_out_of_range"
    return None


def parse(text: str) -> Store | str:
    """PURE: the store, or why the text is not one."""
    try:
        d = json.loads(text)
    except ValueError:
        return "not JSON"
    if not isinstance(d, dict) or d.get("v") != VERSION:
        return f"not version {VERSION}"
    if set(d) - {"v", "revision", "record", "folder", "max_total_mb"}:
        return "unknown keys"
    rev, rec = d.get("revision"), d.get("record")
    folder, mb = d.get("folder"), d.get("max_total_mb")
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 0:
        return "bad revision"
    if not isinstance(rec, bool):
        return "bad record"
    why = folder_problem(folder) or max_problem(mb)
    if why:
        return why
    assert isinstance(mb, int)  # max_problem passed
    return Store(revision=rev, record=rec, folder=str(folder), max_total_mb=mb)


def dumps(store: Store) -> str:
    return json.dumps(store.as_json(), indent=1) + "\n"


def run_dir_name(start: dt.datetime, run_id: str | None = None) -> str:
    """PURE: a Run's folder name: its start time (as given: the server's zone) and its id."""
    rid = re.sub(r"[^A-Za-z0-9_]", "_", run_id or "")[:40]
    return start.strftime("%Y%m%d-%H%M%S") + (f"-{rid}" if rid else "")


def plan_deletes(entries: Iterable[tuple[str, int]], cap_bytes: int,
                 keep: Sequence[str] = ()) -> list[str]:  # fmt: skip
    """PURE: the Run folders to delete, OLDEST first (their names sort by start time), until the
    total size is at most ``cap_bytes``. Only names like a Run's folder count or go; ``keep``
    (the Run being written) never goes."""
    runs = sorted((n, int(b)) for n, b in entries if RUN_DIR_RE.fullmatch(n))
    total = sum(b for _, b in runs)
    out: list[str] = []
    for n, b in runs:
        if total <= cap_bytes:
            break
        if n in keep:
            continue
        out.append(n)
        total -= b
    return out


def story_record(line: Mapping[str, Any], at_iso: str | None) -> dict[str, Any]:
    """PURE: one story line as kept in story.jsonl: its clock time (ISO, the server's zone), the
    Run's seconds and the words."""
    return {"at": at_iso, "t_s": line.get("t_s"), "words": line.get("words")}


def story_text(line: Mapping[str, Any]) -> str:
    """PURE: one story line as kept in story.log: clock time, Run time (m:ss), the words."""
    t = line.get("t_s")
    run = f"{int(t) // 60}:{int(t) % 60:02d}" if isinstance(t, (int, float)) else "-"
    return f"{line.get('at') or '--:--:--'}  {run:>6}  {line.get('words') or ''}"
