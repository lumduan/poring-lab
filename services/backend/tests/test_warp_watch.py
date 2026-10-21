"""warp_watch (Batt 2026-10-21, ORC DUNGEON F1: "warp and watch" collection, no world click): the
pure parts -- the plan (collect_v2.Driver's natural dwells only, a seeded order) and the JPEG
shards the recorder writes on the NAS."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import collect_v2 as cv  # noqa: E402
import warp_watch as ww  # noqa: E402

CELLS = [(10 + 12 * i, 20 + 12 * j) for i in range(5) for j in range(4)]


def test_the_plan_is_natural_dwells_only_in_a_seeded_order() -> None:
    p = ww.make_plan("orcsdun01", CELLS, seed=1, dwell_s=30.0, max_minutes=10.0)
    assert p["blocks"] == [] and p["portal_passes"] == []  # never a spawn, never a portal
    assert sorted(tuple(s["cell"]) for s in p["spots"]) == sorted(CELLS)
    assert [ln["line"] for ln in p["lines"]] == [
        f"@warp orcsdun01 {s['cell'][0]} {s['cell'][1]}" for s in p["spots"]]  # fmt: skip
    assert len({ln["line"] for ln in p["lines"]}) == len(p["lines"])  # distinct typed lines
    again = ww.make_plan("orcsdun01", CELLS, seed=1, dwell_s=30.0, max_minutes=10.0)
    other = ww.make_plan("orcsdun01", CELLS, seed=2, dwell_s=30.0, max_minutes=10.0)
    assert again["spots"] == p["spots"] and other["spots"] != p["spots"]
    per = 30.0 + cv.SAME_MAP_SETTLE_S
    assert p["fits_in_time_box"] == int((600 - cv.ENTRY_SETTLE_S) // per)


def test_the_driver_runs_the_plan_without_a_block_and_stops_on_time() -> None:
    p = ww.make_plan("orcsdun01", CELLS[:3], seed=1, dwell_s=1.0, max_minutes=1.0)
    sent: list[str] = []
    notes: list[str] = []
    now = [0.0]

    def idle(s: float) -> None:
        now[0] += s

    d = cv.Driver(p, send=lambda t: sent.append(t) or True, idle=idle, vitals=lambda: None,
                  note=lambda ev, **_: notes.append(ev), stopped=lambda: None,
                  clock=lambda: now[0], live_block=None)  # fmt: skip
    assert d.run(False) == "done"
    assert sent == [ln["line"] for ln in p["lines"]]  # only the warps: no @monster, no kill
    assert notes.count("dwell_start") == 3


def test_jpeg_shards_round_trip(tmp_path: Path) -> None:
    w = ww.JpegShards(tmp_path, max_bytes=3000)
    for k in range(5):
        w.add(k, 1000 + k, bytes([k]) * 1500)
    w.close()
    assert w.frames == 5 and len(w.shards) >= 2  # rolled over by size
    got = [m for s in w.shards for m in ww.read_jpeg_shard(tmp_path / s)]
    assert [(m["frame_id"], m["t_mono_ns"]) for m, _ in got] == [(k, 1000 + k) for k in range(5)]
    assert [b for _, b in got] == [bytes([k]) * 1500 for k in range(5)]


def test_a_lattice_file_is_read_and_a_repeat_refused(tmp_path: Path) -> None:
    f = tmp_path / "l.json"
    f.write_text(json.dumps([{"x": 1, "y": 2}, {"x": 3, "y": 4, "walkable_in_view": 9}]))
    assert ww.load_lattice(f) == [(1, 2), (3, 4)]
    f.write_text(json.dumps({"cells": [{"x": 1, "y": 2}, {"x": 1, "y": 2}]}))
    try:
        ww.load_lattice(f)
    except SystemExit:
        pass
    else:
        raise AssertionError("a repeated cell must be refused")
