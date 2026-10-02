"""Append-only JSONL log of every input decision: ``<data_dir>/input_log/YYYY-MM-DD.jsonl`` (UTC).

One line per submitted event -- accepted or dropped -- plus one per synthetic release, each tagged
``source=human|bot``. This is research data (human demonstrations, bot behaviour, mux arbitration);
a mouse-heavy session writes on the order of 1 GB/day, so rotation/compression is a TODO for when
it matters.
"""

import fcntl
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pydantic import BaseModel, ConfigDict

from poring_env.protocol import Mode


class InputLogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    t_mono_ns: int
    t_wall: str
    source: str
    mode: Mode
    accepted: bool
    reason: str
    synthetic: bool
    frame_id: int
    event: dict[str, Any]


def wall_clock_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class DailyJsonl:
    """``<directory>/YYYY-MM-DD.jsonl``, one file per UTC day, line-buffered appends.

    Each append holds a SHARED flock, so ``scripts/purge_input_log.py`` can rewrite a file the
    backend still has open (an EXCLUSIVE flock, in place, same inode) without interleaving lines;
    the O_APPEND writer then continues at the new end of file."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._day: str | None = None
        self._fh: TextIO | None = None

    @property
    def directory(self) -> Path:
        return self._dir

    def append(self, day: str, line: str) -> None:
        if day != self._day or self._fh is None:
            self.close()
            self._dir.mkdir(parents=True, exist_ok=True)
            # Line-buffered: each record reaches the file as soon as it is written.
            self._fh = (self._dir / f"{day}.jsonl").open("a", encoding="utf-8", buffering=1)
            self._day = day
        fcntl.flock(self._fh, fcntl.LOCK_SH)
        try:
            self._fh.write(line + "\n")
            self._fh.flush()
        finally:
            fcntl.flock(self._fh, fcntl.LOCK_UN)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


class InputLog(DailyJsonl):
    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir / "input_log")

    def write(self, record: InputLogRecord) -> None:
        self.append(record.t_wall[:10], record.model_dump_json())
