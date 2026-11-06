"""scripts/record_session.py's pause and resume (Batt 2026-11-06 ~14:0x, xmas02-detector.md
Amendment D): the SUSTAINED rule on a disk sink (no one-spike stop), the market-open windows, the
calm wait before a resume, and the parts loop with its budgets and its state file. Offline: a fake
clock, a fake calm guard and a fake part recorder; no lock, no screen, no packets.

Positive case from a REAL stop: xw1 attempt 1 (20261106T115507-rdp-xmas02-xw1) was cut at 12:00 by
one 28.3 % quant-ticker-engine spike under the tolerant disk rule; the sustained rule does not stop
on that spike and does stop on 30 s above 30 %."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str) -> Any:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def rs() -> Any:
    return _load("record_session")


BKK = dt.timezone(dt.timedelta(hours=7))


def test_the_market_open_windows_are_rule_5s(rs: Any) -> None:
    fri = dt.date(2026, 11, 6)  # a Friday
    at = lambda d, h, m, s=0: dt.datetime(d.year, d.month, d.day, h, m, s, tzinfo=BKK)  # noqa: E731
    assert fri.weekday() == 4
    assert rs.in_open_window(at(fri, 9, 30)) and rs.in_open_window(at(fri, 10, 14, 59))
    assert not rs.in_open_window(at(fri, 10, 15)) and not rs.in_open_window(at(fri, 9, 29, 59))
    assert rs.in_open_window(at(fri, 14, 0)) and rs.in_open_window(at(fri, 14, 44, 59))
    assert not rs.in_open_window(at(fri, 14, 45)) and not rs.in_open_window(at(fri, 13, 59, 59))
    assert not rs.in_open_window(at(fri, 12, 30)) and not rs.in_open_window(at(fri, 17, 0))
    sat = dt.date(2026, 11, 7)
    assert not rs.in_open_window(at(sat, 14, 10)) and not rs.in_open_window(at(sat, 9, 45))
    utc = dt.datetime(2026, 11, 6, 7, 10, tzinfo=dt.UTC)  # 14:10 ICT
    assert rs.in_open_window(utc)


def test_the_sustained_rule_is_explicit_and_the_default_keeps_the_sinks(rs: Any) -> None:
    assert rs.SUSTAINED_RULE == {"threshold": 30.0, "sustain": 30.0, "spike": None}
    assert rs.io_rule(argparse.Namespace(io_rule="sustained")) is rs.SUSTAINED_RULE
    assert rs.io_rule(argparse.Namespace(io_rule="auto")) is None
    assert rs.io_rule(argparse.Namespace()) is None  # an old caller: the sink's rule
    assert rs.RESUMABLE == ("io_guard:", "market_window")
    src = (SCRIPTS / "record_session.py").read_text()
    assert src.count("guard = load_guard(a.out, io_rule(a))") == 2  # png and h264


def test_the_xw1_spike_does_not_stop_the_sustained_rule_and_30_s_above_30_does(
    rs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gb = _load("guarded_build")
    clock = {"t": 0.0}
    monkeypatch.setattr(gb.time, "monotonic", lambda: clock["t"])

    def run(rule: dict[str, Any], stall_pct: list[float]) -> Any:
        f = tmp_path / "io.pressure"
        total = 0
        f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
        clock["t"] = 0.0
        g = gb.Guard({"quant-ticker-engine": f}, rule["threshold"], 10.0,
                     sustain=rule["sustain"], spike=rule["spike"])  # fmt: skip
        g.breach()
        for pct in stall_pct:
            clock["t"] += 1.0
            total += int(pct * 1e4)
            f.write_text(f"some avg10=0 total=0\nfull avg10=0 avg60=0 avg300=0 total={total}\n")
            hit = g.breach()
            if hit:
                return hit
        return None

    # 12:00's trip: the 10-s window's mean reached 28.3 % (one burst of ~3 s near 95 %)
    xw1 = [2.0] * 20 + [95.0, 95.0, 95.0] + [2.0] * 40
    hit = run(rs.DISK_RULE, xw1)
    assert hit is not None and "spike above 25.0%" in hit[2]  # what stopped attempt 1
    assert run(rs.SUSTAINED_RULE, xw1) is None
    hit = run(rs.SUSTAINED_RULE, [2.0] * 20 + [40.0] * 60)
    assert hit is not None and "above 30.0% for" in hit[2]


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


class _Calm:
    """A calm guard whose breach() follows a script of busy intervals on the fake clock."""

    window = 10.0

    def __init__(self, clock: _Clock, busy: list[tuple[float, float]]) -> None:
        self.clock, self.busy = clock, busy

    def breach(self) -> Any:
        t = self.clock.t
        return ("cg", 40.0, "x") if any(a <= t < b for a, b in self.busy) else None


def _wait(rs: Any, first: bool, busy: list[tuple[float, float]], budget: float = 3600.0,
          opening: Any = None) -> tuple[bool, float]:  # fmt: skip
    c = _Clock()
    return rs.wait_ready(first, budget, guard_factory=lambda: _Calm(c, busy), clock=c,
                         sleep=c.sleep, opening=opening or (lambda: False))  # fmt: skip


def test_a_first_part_waits_only_for_an_open_window(rs: Any) -> None:
    assert _wait(rs, True, [(0.0, 9999.0)]) == (True, 0.0)  # no calm guard before a first part
    c = _Clock()
    ok, w = rs.wait_ready(True, 3600.0, clock=c, sleep=c.sleep, opening=lambda: c.t < 42.0)
    assert ok and w == 42.0


def test_a_resume_waits_for_60_s_of_calm_and_at_least_120_s(rs: Any) -> None:
    assert _wait(rs, False, []) == (True, 120.0)  # calm all along: RESUME_MIN_S decides
    assert _wait(rs, False, [(0.0, 100.0)]) == (True, 160.0)  # calm from 100 s: + CALM_S
    assert _wait(rs, False, [(0.0, 30.0), (100.0, 101.0)]) == (True, 161.0)  # a burst resets it
    ok, w = _wait(rs, False, [(0.0, 9999.0)], budget=500.0)
    assert not ok and w > 500.0  # the pause budget runs out
    c = _Clock()
    ok, _ = rs.wait_ready(False, 3600.0, guard_factory=lambda: _Calm(c, []), clock=c,
                          sleep=c.sleep, opening=lambda: c.t < 300.0)  # fmt: skip
    assert ok and c.t == 360.0  # an open window counts as busy


def test_a_signal_ends_the_wait(rs: Any) -> None:
    rs.STOP["flag"] = True
    try:
        assert _wait(rs, False, [])[0] is False
    finally:
        rs.STOP["flag"] = False


def _args(**kw: Any) -> argparse.Namespace:
    base = {"format": "png", "seconds": 2400.0, "max_bytes": 5 << 30, "resume": 4,
            "io_rule": "sustained", "label": "xmas02-xw1"}  # fmt: skip
    return argparse.Namespace(**{**base, **kw})


class _Parts:
    """A fake part recorder: each call returns the next scripted (seconds, bytes, stop_reason)."""

    def __init__(self, rs: Any, script: list[Any]) -> None:
        self.rs, self.script = rs, script
        self.calls: list[argparse.Namespace] = []

    def __call__(self, a: argparse.Namespace) -> dict[str, Any]:
        self.calls.append(a)
        item = self.script[len(self.calls) - 1]
        if isinstance(item, BaseException):
            raise item
        sec, b, why = item
        sid = f"2026110{len(self.calls)}T150000-rdp-{a.label}"
        self.rs.set_state("recording", session=sid, part=a.part)
        doc = json.loads(self.rs.STATE["path"].read_text())
        assert doc["state"] == "recording" and doc["session"] == sid and doc["part"] == a.part
        return {"dir": f"/rec/{sid}", "frames": int(sec), "bytes": b, "seconds": sec,
                "stop_reason": why}  # fmt: skip


@pytest.fixture()
def state(rs: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "rec.json"
    monkeypatch.setitem(rs.STATE, "path", path)
    monkeypatch.setitem(rs.STATE, "doc", {})
    waits: list[bool] = []
    monkeypatch.setattr(
        rs, "wait_ready", lambda first, budget: (waits.append(first), (True, 7.0))[1]
    )
    rs._waits = waits
    return path


def test_parts_resume_after_an_io_stop_with_the_budgets_left(rs: Any, state: Path) -> None:
    rec = _Parts(rs, [(300.0, 1 << 30, "io_guard: cg 41.0% (above 30.0% for 30s)"),
                      (900.0, 2 << 30, "market_window: a market-open window began"),
                      (600.0, 1 << 30, "stopped by signal")])  # fmt: skip
    out = rs.record_parts(_args(), rec)
    assert [c.part for c in rec.calls] == [0, 1, 2]
    assert [c.seconds for c in rec.calls] == [2400.0, 2100.0, 1200.0]
    assert [c.max_bytes for c in rec.calls] == [5 << 30, 4 << 30, 2 << 30]
    assert rs._waits == [True, False, False]  # only the resumes wait for calm
    assert out["parts"] == 3 and out["end"] == "stopped by signal" and out["paused_s"] == 21.0
    assert out["bytes"] == 4 << 30 and out["frames"] == 1800
    doc = json.loads(state.read_text())
    assert doc["state"] == "ended" and doc["reason"] == "stopped by signal"


def test_parts_end_on_a_final_stop_the_resume_cap_or_a_refusal(rs: Any, state: Path) -> None:
    io = (60.0, 1 << 20, "io_guard: cg 31.0% (above 30.0% for 30s)")
    for script, kw, parts, end in (
        ([(60.0, 1 << 20, "size_cap")], {}, 1, "size_cap"),
        ([(60.0, 1 << 20, "local_cap: only 99 GB free")], {}, 1, "local_cap: only 99 GB free"),
        ([io, io, io], {"resume": 1}, 2, io[2]),  # at most --resume resumes
        (
            [io, rs.r.Stop("not recording: only 99 GB free")],
            {},
            1,
            "refused: not recording: only 99 GB free",
        ),
        ([(2400.0, 1 << 20, io[2])], {}, 1, io[2]),  # the duration is used up: no resume
    ):
        out = rs.record_parts(_args(**kw), _Parts(rs, script))
        assert (out["parts"], out["end"]) == (parts, end), script
        assert json.loads(state.read_text())["state"] == "ended"
    with pytest.raises(rs.r.Stop, match="png"):
        rs.record_parts(_args(format="h264"), _Parts(rs, []))


def test_the_record_loop_beats_and_ends_a_part_at_an_open_window() -> None:
    """The png loop (live code, not run here): the state says recording from just before the first
    grab, beats every frame, says finishing as the loop ends, and a resuming recording ends its
    part when a market-open window begins."""
    src = (SCRIPTS / "record_session.py").read_text()
    loop = src[src.index("def record(a") : src.index("def write_control")]
    assert loop.count('set_state("recording", session=session_id') == 1
    assert loop.index('set_state("recording"') < loop.index("while time.monotonic() < t_end")
    assert loop.count("            beat()\n") == 1
    assert 'set_state("finishing", reason=stop_reason)' in loop
    assert "if resume and in_open_window():" in loop
