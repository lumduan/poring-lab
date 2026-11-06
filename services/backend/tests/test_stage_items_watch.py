"""scripts/stage_items.py `watch` beside a pausing recorder (stage@7; Batt 2026-11-06,
xmas02-detector.md Amendment D), driven OFFLINE through fakes on a fake clock: a dwell waits until
the recorder banks frames, a stand whose dwell a pause cut is warped to again and dwelt again
inside the new part, the waits stay outside the time box, --start-cell continues a stopped watch,
and a recorder that ends stops the watch. The recorder's state file is scripted by time."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import stage_items as si  # noqa: E402

CELLS = [{"x": 10, "y": 10}, {"x": 20, "y": 10}, {"x": 30, "y": 10}]


class _Stop(SystemExit):
    pass


class _World:
    """The fake clock (s), every GM line, and the recorder's script: t -> state dict or None."""

    def __init__(self, tmp: Path, script: Callable[[float], dict[str, Any] | None]) -> None:
        self.t = 0.0
        self.lines: list[str] = []
        self.state = tmp / "rec.json"
        self.script = script
        self.write()

    def ns(self) -> int:
        return int(self.t * 1e9)

    def write(self) -> None:
        doc = self.script(self.t)
        if doc is None:
            self.state.unlink(missing_ok=True)
        else:
            self.state.write_text(json.dumps({"beat_ns": self.ns(), **doc}))

    def sleep(self, s: float) -> None:
        self.t += s
        self.write()


def _install(monkeypatch: pytest.MonkeyPatch, tmp: Path,
             script: Callable[[float], dict[str, Any] | None]) -> _World:  # fmt: skip
    w = _World(tmp, script)
    r = types.ModuleType("ro_agent")
    r.Stop = _Stop  # type: ignore[attr-defined]
    r.SHOTS = tmp  # type: ignore[attr-defined]
    r.ns = w.ns  # type: ignore[attr-defined]
    r.to_png = lambda img, path: path  # type: ignore[attr-defined]

    @contextlib.contextmanager
    def session(name: str) -> Iterator[tuple[Any, Any]]:
        agent = types.SimpleNamespace(wait_for_human=lambda: None)
        yield agent, types.SimpleNamespace(full=lambda: np.zeros((2, 2, 4), np.uint8))

    r.session = session  # type: ignore[attr-defined]
    cr = types.ModuleType("crusader")
    cr.gm_line = lambda agent, screen, cmd, job, char: w.lines.append(cmd)  # type: ignore[attr-defined]
    cr.check = lambda screen, job, char: {"ok": True}  # type: ignore[attr-defined]
    bench = types.ModuleType("bench")
    bench.close_chat = lambda agent, screen: None  # type: ignore[attr-defined]
    ui = types.ModuleType("ui_gate")
    ui.ensure_clear = lambda agent, screen, why: {}  # type: ignore[attr-defined]
    for name, mod in (("ro_agent", r), ("crusader", cr), ("bench", bench), ("ui_gate", ui)):
        monkeypatch.setitem(sys.modules, name, mod)
    monkeypatch.setattr(si, "DEMO", tmp / "demo")
    monkeypatch.setattr(si, "RAM_ROOT", str(tmp.resolve()))
    monkeypatch.setattr(si.time, "sleep", w.sleep)
    monkeypatch.setattr(si.time, "monotonic", lambda: w.t)
    monkeypatch.setattr(si.time, "monotonic_ns", w.ns)
    monkeypatch.setattr(si, "watch_cells", lambda lat, seed, n: [(c["x"], c["y"]) for c in lat])
    return w


def _args(tmp: Path, w: _World | None, **kw: Any) -> argparse.Namespace:
    lat = tmp / "lattice.json"
    lat.write_text(json.dumps(CELLS))
    base = {"map": "xmas_dun02", "lattice": lat, "seed": 1, "max_cells": 99, "max_minutes": 30.0,
            "dwell_s": 30.0, "label": "t", "immune_confirmed": True, "spawn": None, "spawn_n": 1,
            "start_cell": 0, "recorder_state": w.state if w else None}  # fmt: skip
    return argparse.Namespace(**{**base, **kw})


def _events(tmp: Path) -> list[dict[str, Any]]:
    (d,) = (tmp / "demo").iterdir()
    return [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]


def _rec(session: str, since: float) -> dict[str, Any]:
    return {"state": "recording", "session": session, "since_ns": int(since * 1e9)}


def test_the_verdicts_and_the_coverage_rule() -> None:
    now = 100 * 10**9
    rec = {"state": "recording", "session": "A", "since_ns": 10 * 10**9, "beat_ns": now}
    assert si.rec_verdict(None, now) == "missing"
    assert si.rec_verdict(rec, now) == "recording"
    assert si.rec_verdict({**rec, "state": "paused"}, now) == "wait"
    assert si.rec_verdict({**rec, "state": "finishing"}, now) == "wait"
    assert si.rec_verdict({**rec, "state": "ended"}, now) == "ended"
    assert si.rec_verdict({**rec, "beat_ns": now - 11 * 10**9}, now) == "gone"  # a stale beat
    assert si.rec_covered(rec, rec, 20 * 10**9, now)
    assert not si.rec_covered(rec, {**rec, "session": "B", "since_ns": 90 * 10**9}, 20 * 10**9,
                              now)  # fmt: skip  # a new part inside the dwell
    assert not si.rec_covered(rec, {**rec, "since_ns": 30 * 10**9}, 20 * 10**9, now)
    assert not si.rec_covered(rec, {**rec, "state": "paused"}, 20 * 10**9, now)
    assert not si.rec_covered(rec, None, 20 * 10**9, now)


def test_a_pause_inside_a_dwell_re_warps_and_re_dwells_in_the_new_part(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Part A records until t = 50 s (inside stand 1's dwell), pauses, part B starts at t = 200 s:
    stand 1 is warped to again and dwelt again in B; stands 0 and 2 once each."""

    def script(t: float) -> dict[str, Any]:
        if t < 50.0:
            return _rec("A", 0.0)
        if t < 200.0:
            return {"state": "paused", "session": "A", "since_ns": int(50e9),
                    "reason": "io_guard: x"}  # fmt: skip
        return _rec("B", 200.0)

    w = _install(monkeypatch, tmp_path, script)
    assert si.watch(_args(tmp_path, w)) == 0
    assert w.lines == ["@warp xmas_dun02 10 10", "@warp xmas_dun02 20 10",
                       "@warp xmas_dun02 20 10", "@warp xmas_dun02 30 10"]  # fmt: skip
    ev = _events(tmp_path)
    dwells = [(e["i"], e["attempt"], e["rec_session"]) for e in ev if e["kind"] == "dwell"]
    assert dwells == [(0, 0, "A"), (1, 0, "A"), (1, 1, "B"), (2, 0, "B")]
    assert [e["i"] for e in ev if e["kind"] == "dwell_unrecorded"] == [1]
    (wait,) = [e for e in ev if e["kind"] == "recorder_wait"]
    assert wait["i"] == 1 and wait["session"] == "B" and 130.0 <= wait["s"] <= 140.0
    assert ev[-1]["reason"] == "done" and ev[-1]["waited_s"] == wait["s"]


def test_the_waits_stay_outside_the_time_box(monkeypatch: pytest.MonkeyPatch,
                                             tmp_path: Path) -> None:  # fmt: skip
    """A 1-min box holds the first stand's ~32.5 s and not a second one; a 10-min wait before the
    first dwell does not count against it."""
    w = _install(monkeypatch, tmp_path,
                 lambda t: {"state": "waiting"} if t < 600.0 else _rec("A", 600.0))  # fmt: skip
    assert si.watch(_args(tmp_path, w, max_minutes=1.0)) == 0
    ev = _events(tmp_path)
    assert [e["i"] for e in ev if e["kind"] == "dwell"] == [0, 1]
    assert ev[-1]["reason"] == "time_box" and ev[-1]["waited_s"] >= 590.0


def test_start_cell_continues_the_seeded_order(monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, lambda t: _rec("A", 0.0))
    assert si.watch(_args(tmp_path, w, start_cell=2)) == 0
    assert w.lines == ["@warp xmas_dun02 30 10"]
    assert _events(tmp_path)[0]["start_cell"] == 2
    with pytest.raises(SystemExit, match="start-cell"):
        si.watch(_args(tmp_path, w, start_cell=3))


def test_a_recorder_that_ends_or_never_comes_stops_the_watch(monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path,
                 lambda t: _rec("A", 0.0) if t < 40.0 else {"state": "ended",
                                                            "reason": "size_cap"})  # fmt: skip
    assert si.watch(_args(tmp_path, w)) == 1
    ev = _events(tmp_path)
    assert ev[-1]["reason"].startswith("recorder: the recorder is ended (size_cap)")
    assert [e["i"] for e in ev if e["kind"] == "dwell"] == [0, 1]  # stand 1's dwell: not recorded
    assert w.lines == ["@warp xmas_dun02 10 10", "@warp xmas_dun02 20 10"]
    for d in (tmp_path / "demo").iterdir():
        for f in d.iterdir():
            f.unlink()
        d.rmdir()
    w2 = _install(monkeypatch, tmp_path, lambda t: None)
    assert si.watch(_args(tmp_path, w2)) == 1
    assert _events(tmp_path)[-1]["reason"].startswith("recorder: no recorder state")
    assert w2.lines == ["@warp xmas_dun02 10 10"]  # waited REC_START_MAX_S at the first stand


def test_without_a_recorder_state_the_watch_is_stage6s(monkeypatch: pytest.MonkeyPatch,
                                                      tmp_path: Path) -> None:  # fmt: skip
    w = _install(monkeypatch, tmp_path, lambda t: None)
    assert si.watch(_args(tmp_path, None)) == 0
    assert w.lines == [f"@warp xmas_dun02 {c['x']} {c['y']}" for c in CELLS]
    assert [e.get("attempt") for e in _events(tmp_path) if e["kind"] == "dwell"] == [0, 0, 0]
    monkeypatch.setattr(si, "RAM_ROOT", "/dev/shm/")
    with pytest.raises(SystemExit, match="/dev/shm"):  # refused before anything is written
        si.watch(_args(tmp_path, w, recorder_state=Path("/var/tmp/stage-watch-test/rec.json")))
    assert not Path("/var/tmp/stage-watch-test").exists()
