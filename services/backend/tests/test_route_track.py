"""route_track: the player's cell track from a recording of her own play (docs/planning/
waypoints-npc-recording.md Amendment 8) -- per-frame minimap reads judged against their neighbours
(walkable, consistent with the max walking speed, two vote counts, excursions), gaps filled with
map_routes' shortest walkable path timed by walking time, splits where a gap cannot be filled, and
the track handed to path_blocks.thin. Every grid and frame here is SYNTHETIC (no client data)."""

from __future__ import annotations

import dataclasses
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
import map_routes as mr  # noqa: E402
import map_zones as mz  # noqa: E402
import path_blocks as pb  # noqa: E402
import route_track as rt  # noqa: E402

H, W = 40, 40
DT = 0.2  # 5 fps


def fix_grid() -> Any:
    """40 x 40 cells, [y, x], y north: the walkable square x, y 2..37, a WALL at x 20 for y 2..30
    (its gap: y 31..37), and a SEALED ROOM x 31..37, y 2..9 (walls x 30 and y 10, no door)."""
    ok = np.zeros((H, W), dtype=bool)
    ok[2:38, 2:38] = True
    ok[2:31, 20] = False
    ok[2:11, 30] = False
    ok[10, 30:38] = False
    return ok


def walk(cells: Any, t0: float = 0.0, dt: float = DT) -> list[tuple[Any, ...]]:
    return [(t0 + k * dt, c, "ok") for k, c in enumerate(cells)]


def line(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    return mr.seg_cells(a, b)


def sources(tr: rt.Track) -> list[str]:
    return [f.source for f in tr.frames]


# --- settings and input ---------------------------------------------------------------------------


def test_the_defaults_are_settings_and_usable() -> None:
    s = rt.DEFAULTS
    assert (s.max_speed, s.slack, s.window, s.max_gap_s, s.min_support) == (10.0, 2, 3, 2.0, 1)
    assert rt.settings_problem(s) is None
    # 10 cells/s is RO's default walk (150 ms a cell) made 1.5x faster
    assert 1 / s.max_speed == pytest.approx(0.150 / 1.5)


@pytest.mark.parametrize("change", [
    {"max_speed": 0}, {"max_speed": math.nan}, {"max_speed": True}, {"slack": -1},
    {"slack": 1.5}, {"window": 0}, {"max_gap_s": 0.0}, {"max_gap_s": math.inf},
    {"min_support": -1}, {"min_support": 7},
])  # fmt: skip
def test_unusable_settings_are_refused(change: dict[str, Any]) -> None:
    s = dataclasses.replace(rt.DEFAULTS, **change)
    assert rt.settings_problem(s) is not None
    with pytest.raises(rt.TrackError, match="settings"):
        rt.build_track(walk(line((5, 5), (9, 5))), fix_grid(), settings=s)
    assert rt.settings_problem("not settings") == "not track settings"


@pytest.mark.parametrize("reads, msg", [
    ([(0.4, (5, 5)), (0.2, (5, 5))], "time order"),
    ([(0.0, (5, 5, 1))], "not \\(x, y\\)"),
    ([(0.0, (5, -1))], "whole numbers"),
    ([(0.0, (5.0, 5))], "whole numbers"),
    ([(math.nan, (5, 5))], "finite"),
    ([(0.0,)], "is not"),
    ([(0.0, (5, 5), 3)], "reason"),
])  # fmt: skip
def test_bad_reads_are_refused(reads: list[Any], msg: str) -> None:
    with pytest.raises(rt.TrackError, match=msg):
        rt.build_track(reads, fix_grid())


def test_a_bad_grid_is_refused_and_lists_from_json_are_cells() -> None:
    with pytest.raises(rt.TrackError, match="2-D"):
        rt.build_track(walk([(5, 5)]), np.ones(5, dtype=bool))
    tr = rt.build_track([(0.0, [5, 5], "ok"), (0.2, [6, 5], None)], fix_grid())
    assert [f.cell for f in tr.frames] == [(5, 5), (6, 5)]
    assert tr.frames[1].reason is None


# --- accepted reads -------------------------------------------------------------------------------


def test_a_clean_walk_is_read_frame_for_frame() -> None:
    cells = line((5, 5), (15, 12))
    tr = rt.build_track(walk(cells), fix_grid())
    assert sources(tr) == ["read"] * len(cells)
    assert [f.cell for f in tr.frames] == cells
    assert {f.segment for f in tr.frames} == {0}
    assert tr.splits == () and tr.segments == 1
    assert tr.summary()["sources"] == {"read": len(cells), "dropped": 0, "filled": 0,
                                       "unfilled": 0}  # fmt: skip


def test_a_lone_misread_is_dropped_and_filled_from_its_neighbours() -> None:
    cells = line((5, 5), (15, 5))
    reads = walk(cells)
    reads[4] = (reads[4][0], (30, 30), "ok")  # a digit misread: 21 cells off in 0.2 s
    tr = rt.build_track(reads, fix_grid())
    f = tr.frames[4]
    assert (f.raw, f.drop, f.source, f.gap, f.cell, f.segment) == (
        (30, 30),
        "outlier",
        "filled",
        "filled",
        cells[4],
        0,
    )
    assert tr.summary()["drops"] == {"outlier": 1}


def test_cells_she_cannot_stand_on_are_dropped() -> None:
    cells = line((15, 33), (25, 33))  # past the wall's end (x 20, y <= 30)
    reads = walk(cells)
    reads[3] = (reads[3][0], (20, 12), "ok")  # on the wall
    reads[6] = (reads[6][0], (55, 33), "ok")  # off the 40 x 40 map
    tr = rt.build_track(reads, fix_grid())
    assert (tr.frames[3].drop, tr.frames[6].drop) == ("not_walkable", "off_map")
    assert (tr.frames[3].cell, tr.frames[6].cell) == (cells[3], cells[6])
    assert sources(tr).count("filled") == 2


def test_no_read_is_not_a_drop() -> None:
    cells = line((5, 5), (12, 5))
    reads = walk(cells)
    reads[2] = (reads[2][0], None, "no_glyph")
    tr = rt.build_track(reads, fix_grid())
    f = tr.frames[2]
    assert (f.raw, f.reason, f.drop, f.source, f.cell) == (None, "no_glyph", None, "filled",
                                                          cells[2])  # fmt: skip
    assert tr.summary()["raw"] == {"cell": len(cells) - 1, "none": 1}
    assert tr.summary()["drops"] == {}


def test_a_burst_up_to_the_window_is_outvoted() -> None:
    cells = line((5, 5), (19, 5))
    reads = walk(cells)
    for k in (5, 6, 7):  # three reads agreeing on the same wrong cell
        reads[k] = (reads[k][0], (5, 30), "ok")
    tr = rt.build_track(reads, fix_grid())
    assert [tr.frames[k].drop for k in (5, 6, 7)] == ["outlier"] * 3
    assert [tr.frames[k].cell for k in (5, 6, 7)] == cells[5:8]
    assert tr.splits == ()


def test_a_longer_burst_is_an_excursion() -> None:
    """Six agreeing misreads (1.2 s) win their own votes; out and back faster than walking within
    max_gap_s is still impossible: dropped, and the gap filled."""
    cells = line((3, 5), (19, 5)) + line((19, 6), (19, 15))
    reads = walk(cells)
    burst = range(6, 12)
    for k in burst:
        reads[k] = (reads[k][0], (5, 30), "ok")
    tr = rt.build_track(reads, fix_grid())
    assert [tr.frames[k].drop for k in burst] == ["excursion"] * 6
    assert [tr.frames[k].cell for k in burst] == cells[6:12]
    assert tr.splits == () and tr.segments == 1
    # the same burst at a window of 6 is outvoted instead
    tr6 = rt.build_track(reads, fix_grid(), settings=dataclasses.replace(rt.DEFAULTS, window=6))
    assert [tr6.frames[k].drop for k in burst] == ["outlier"] * 6


def test_a_real_jump_keeps_both_sides_and_splits_the_track() -> None:
    """A Fly Wing or a GM warp: far, then walking on -- each side keeps its own votes."""
    a = line((5, 5), (5, 14))
    b = line((28, 34), (35, 34))
    reads = walk(a) + walk(b, t0=len(a) * DT)
    tr = rt.build_track(reads, fix_grid())
    assert sources(tr) == ["read"] * len(reads)
    assert tr.splits == (rt.Split(len(a) * DT, "jump"),)
    assert [f.segment for f in tr.frames] == [0] * len(a) + [1] * len(b)
    assert tr.summary()["splits"] == {"jump": 1} and tr.segments == 2


def test_a_lone_read_is_unconfirmed_unless_min_support_is_0() -> None:
    reads = [(0.0, None, "no_glyph"), (0.2, (5, 5), "ok"), (0.4, None, "no_glyph")]
    tr = rt.build_track(reads, fix_grid())
    assert tr.frames[1].drop == "unconfirmed"
    assert sources(tr) == ["unfilled", "dropped", "unfilled"]
    assert [f.gap for f in tr.frames] == ["no_track"] * 3 and tr.segments == 0
    lone = rt.build_track(
        reads, fix_grid(), settings=dataclasses.replace(rt.DEFAULTS, min_support=0)
    )
    assert sources(lone) == ["unfilled", "read", "unfilled"]
    assert [f.gap for f in lone.frames] == ["track_start", None, "track_end"]


def test_far_neighbours_do_not_vote() -> None:
    """Two reads 5 s apart (beyond max_gap_s) cannot vouch for each other."""
    reads = [(0.0, (5, 5), "ok"), (5.0, (6, 5), "ok")]
    tr = rt.build_track(reads, fix_grid())
    assert [f.drop for f in tr.frames] == ["unconfirmed", "unconfirmed"]


def test_a_good_read_beside_a_burst_keeps_its_place() -> None:
    """At a stay's start the first count drops the two good reads (the burst outvotes them); the
    second count, against the reads the first accepted, keeps them."""
    good = line((5, 5), (14, 5))
    reads = walk(good)
    for k in (2, 3, 4):
        reads[k] = (reads[k][0], (5, 30), "ok")
    first = [i for i in range(len(reads))
             if rt._judge(i, list(range(len(reads))), [r[0] for r in reads],
                          [r[1] for r in reads], rt.DEFAULTS) is None]  # fmt: skip
    assert 0 not in first and 1 not in first  # the first count alone would lose them
    tr = rt.build_track(reads, fix_grid())
    assert sources(tr)[:2] == ["read", "read"]
    assert [tr.frames[k].drop for k in (2, 3, 4)] == ["outlier"] * 3
    assert [f.cell for f in tr.frames] == good


# --- gaps -----------------------------------------------------------------------------------------


def around_the_wall() -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """West of the wall's end, then east of it (the wall x 20 ends at y 30)."""
    return line((10, 28), (18, 28)), line((22, 28), (30, 28))


def test_a_gap_is_filled_along_the_walkable_path_not_through_the_wall() -> None:
    west, east = around_the_wall()
    gap = 6  # frames with no read: 1.4 s from the last read to the next
    reads = walk(west) + [(len(west) * DT + k * DT, None, "no_glyph") for k in range(gap)]
    reads += walk(east, t0=(len(west) + gap) * DT)
    tr = rt.build_track(reads, fix_grid())
    path = mr.leg_path(fix_grid(), west[-1], east[0])
    assert path is not None and len(path) - 1 > mr.cheb(west[-1], east[0])  # a detour
    filled = [f.cell for f in tr.frames if f.source == "filled"]
    assert len(filled) == gap
    assert all(c in path for c in filled)
    assert [path.index(c) for c in filled] == sorted(path.index(c) for c in filled)
    assert all(fix_grid()[c[1], c[0]] for c in filled)
    assert not any(c[0] == 20 and c[1] <= 30 for c in filled)
    assert tr.splits == () and tr.segments == 1


def test_a_fill_is_timed_by_walking_time() -> None:
    diag = [(0, 0), (1, 1), (2, 1)]  # 1.4 then 1.0
    assert rt.path_cell(diag, 0.0) == (0, 0)
    assert rt.path_cell(diag, 0.5) == (1, 1)  # 1.2 of 2.4: nearer 1.4 than 0
    assert rt.path_cell(diag, 1.0) == (2, 1)
    assert rt.path_cell([(0, 0), (1, 0)], 0.5) == (0, 0)  # a tie: the earlier
    assert rt.path_cell([(3, 3)], 0.7) == (3, 3)


def test_a_gap_longer_than_max_gap_stays_unfilled_and_splits() -> None:
    a = line((5, 5), (10, 5))
    b = line((13, 5), (18, 5))
    gap = 12  # 2.6 s
    reads = walk(a) + [(len(a) * DT + k * DT, None, "no_glyph") for k in range(gap)]
    reads += walk(b, t0=(len(a) + gap) * DT)
    tr = rt.build_track(reads, fix_grid())
    mid = tr.frames[len(a) : len(a) + gap]
    assert {(f.source, f.gap, f.cell, f.segment) for f in mid} == {
        ("unfilled", "gap_too_long", None, None)
    }
    assert [s.why for s in tr.splits] == ["gap_too_long"] and tr.segments == 2
    longer = rt.build_track(
        reads, fix_grid(), settings=dataclasses.replace(rt.DEFAULTS, max_gap_s=3.0)
    )
    assert {f.source for f in longer.frames[len(a) : len(a) + gap]} == {"filled"}


def test_a_gap_with_no_walkable_path_splits() -> None:
    """Into the sealed room: the reads agree (2 cells in 0.4 s), the grid has no way in."""
    outside = line((29, 15), (29, 5))
    inside = line((31, 5), (31, 2))
    reads = walk(outside) + [(len(outside) * DT, None, "no_glyph")]
    reads += walk(inside, t0=(len(outside) + 1) * DT)
    tr = rt.build_track(reads, fix_grid())
    assert tr.frames[len(outside)].gap == "no_path"
    assert [s.why for s in tr.splits] == ["no_path"]
    assert sources(tr).count("read") == len(outside) + len(inside)


def test_a_path_longer_than_the_walk_allows_splits() -> None:
    west, east = around_the_wall()
    path = mr.leg_path(fix_grid(), west[-1], east[0])
    assert path is not None
    steps = len(path) - 1
    s = rt.DEFAULTS
    # a gap whose reach covers the straight jump but not the detour
    dt = (steps - 1 - s.slack) / s.max_speed
    assert mr.cheb(west[-1], east[0]) <= rt.reach(dt) < steps
    t_b = (len(west) - 1) * DT + dt
    reads = walk(west) + [((len(west) - 1) * DT + dt / 2, None, "no_glyph")]
    reads += walk(east, t0=t_b)
    tr = rt.build_track(reads, fix_grid())
    assert tr.frames[len(west)].gap == "too_far"
    assert [x.why for x in tr.splits] == ["too_far"]


def test_a_jump_across_a_gap_is_a_jump() -> None:
    a = line((5, 5), (5, 12))
    b = line((30, 35), (35, 35))
    reads = walk(a) + [(len(a) * DT, None, "no_glyph")] + walk(b, t0=(len(a) + 1) * DT)
    tr = rt.build_track(reads, fix_grid())
    assert tr.frames[len(a)].gap == "jump"
    assert [x.why for x in tr.splits] == ["jump"]


def test_zones_keep_the_fill_out_of_a_no_enter_area() -> None:
    a, b = line((5, 20), (10, 20)), line((14, 20), (19, 20))
    gap = 5
    reads = walk(a) + [(len(a) * DT + k * DT, None, "no_glyph") for k in range(gap)]
    reads += walk(b, t0=(len(a) + gap) * DT)
    box = ((11, 18), (13, 18), (13, 22), (11, 22))
    zones = mz.Zones("fix", "Batt", "2026-11-22", no_enter=(mz.NoEnter("pond", "a pond", box),))
    plain = rt.build_track(reads, fix_grid())
    kept_out = rt.build_track(reads, fix_grid(), zones)
    crossed = [f.cell for f in plain.frames if f.source == "filled"]
    assert any(c is not None and mz.in_polygon(c, box) for c in crossed)  # through the pond
    filled = [f.cell for f in kept_out.frames if f.source == "filled"]
    assert len(filled) == gap
    assert not any(c is not None and mz.in_polygon(c, box) for c in filled)


def test_frames_outside_the_track_are_not_filled() -> None:
    cells = line((5, 5), (10, 5))
    reads = [(0.0, None, "no_glyph"), (0.2, (36, 36), "ok")]
    reads += walk(cells, t0=0.4) + [(0.4 + len(cells) * DT, None, "no_glyph")]
    tr = rt.build_track(reads, fix_grid())
    first, second, last = tr.frames[0], tr.frames[1], tr.frames[-1]
    assert (first.source, first.gap) == ("unfilled", "track_start")
    assert (second.source, second.drop, second.gap) == ("dropped", "outlier", "track_start")
    assert (last.source, last.gap, last.cell) == ("unfilled", "track_end", None)


def test_the_track_is_deterministic_and_its_summary_adds_up() -> None:
    west, east = around_the_wall()
    reads = walk(west) + [(len(west) * DT + k * DT, None, "x") for k in range(4)]
    reads += walk(east, t0=(len(west) + 4) * DT)
    reads[3] = (reads[3][0], (30, 5), "ok")
    one, two = rt.build_track(reads, fix_grid()), rt.build_track(list(reads), fix_grid())
    assert one == two
    s = one.summary()
    assert sum(s["sources"].values()) == s["frames"] == len(reads)
    assert set(s["sources"]) == set(rt.SOURCES)
    json.dumps(s)  # plain data


# --- to path_blocks -------------------------------------------------------------------------------


def test_to_reads_feed_path_blocks_thin() -> None:
    cells = line((5, 33), (25, 33))
    reads = walk(cells)
    reads[7] = (reads[7][0], None, "no_glyph")
    reads[9] = (reads[9][0], (35, 35), "ok")
    tr = rt.build_track(reads, fix_grid())
    out = tr.to_reads("town_1")
    assert len(out) == len(reads)
    assert all(r[4] for r in out)  # every frame has a cell here: read or filled
    assert [(r[2], r[3]) for r in out] == cells
    th = pb.thin(out)
    assert len(th.runs) == 1 and th.runs[0].map == "town_1"
    assert th.runs[0].points[0].cell == (5, 33) and th.runs[0].points[-1].cell == (25, 33)
    assert th.dropped == 0


def test_unfilled_frames_go_unconfirmed_and_a_segment_can_be_taken_alone() -> None:
    a = line((5, 5), (5, 14))
    b = line((28, 34), (35, 34))
    reads = [(0.0, None, "no_glyph")] + walk(a, t0=DT) + walk(b, t0=(len(a) + 1) * DT)
    tr = rt.build_track(reads, fix_grid())
    out = tr.to_reads("town_1")
    assert out[0] == (0.0, "town_1", None, None, False)
    assert pb.thin(out).dropped == 1
    seg1 = tr.to_reads("town_1", segment=1)
    assert [(r[2], r[3]) for r in seg1] == b
    assert [p.cell for p in pb.thin(seg1).runs[0].points][0] == b[0]
    with pytest.raises(rt.TrackError, match="map"):
        tr.to_reads("")


# --- the frames: which ones, and the 1280x720 view ------------------------------------------------


def test_the_picker_takes_the_first_frame_at_or_after_each_tick() -> None:
    times = [k * 40_000_000 for k in range(31)]  # 25 fps, 1.2 s
    assert rt.pick_times(times, 0.2) == [0, 5, 10, 15, 20, 25, 30]
    times = [k * 33_333_333 for k in range(14)]  # 30 fps: the first frame AT OR AFTER a tick
    assert rt.pick_times(times, 0.2) == [0, 7, 13]  # 6 and 12 are a few ns early
    # a stall: the next frame is taken, and the ticks stay on the first frame's grid
    times = [0, 100_000_000, 1_050_000_000, 1_210_000_000, 1_390_000_000, 1_400_000_000]
    assert rt.pick_times(times, 0.2) == [0, 2, 3, 5]
    with pytest.raises(rt.TrackError):
        rt.Picker(0.0)


def test_a_1280x720_frame_is_read_as_it_is() -> None:
    img = np.zeros((720, 1280, 3), np.uint8)
    out, how = rt.game_view(img, {})
    assert out is img and "as recorded" in how


def test_a_1080_frame_is_read_through_the_virtual_client() -> None:
    from poring_env import selfpos
    from poring_env.clientview import Panel

    rng = np.random.default_rng(7)
    img = rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8)
    _, (vx, vy, pw, ph), anchor = rt.MINIMAP_PANEL
    rx, ry = Panel.anchored("minimap", (vx, vy, pw, ph), "tr", (1920, 1080)).real_xy
    assert (rx, ry) == (1920 - (1280 - vx), vy)  # stuck to the top-right corner
    out, how = rt.game_view(img, {})
    assert out.shape == (720, 1280, 3) and "anchored" in how
    assert np.array_equal(out[vy : vy + ph, vx : vx + pw], img[ry : ry + ph, rx : rx + pw])
    x, y, w, h = selfpos.default_rect()  # the readout lies inside the minimap's panel
    assert vx <= x and x + w <= vx + pw and vy <= y and y + h <= vy + ph


def test_a_recording_s_own_client_view_is_used_when_it_places_the_minimap() -> None:
    img = np.zeros((1080, 1920, 3), np.uint8)
    img[40:200, 1700:1850] = 200  # the minimap where THIS recording's view put it
    cv = {"rect": [0, 0, 1920, 1080], "mode": "fullscreen", "world_scale": 1.5,
          "world_centre": [960.0, 540.0],
          "panels": [{"name": "minimap", "virtual": [1130, 10, 150, 160], "real_xy": [1700, 40]},
                     {"name": "cursor", "virtual": [0, 0, 68, 68], "real_xy": [5, 5]}]}  # fmt: skip
    out, how = rt.game_view(img, {"client_view": cv})
    assert "client_view" in how
    assert (out[10:170, 1130:1280] == 200).all()
    no_minimap = {**cv, "panels": [p for p in cv["panels"] if p["name"] != "minimap"]}
    _, how2 = rt.game_view(img, {"client_view": no_minimap})
    assert "anchored" in how2


def test_the_minimap_panel_is_ro_agents() -> None:
    import ro_agent

    assert rt.MINIMAP_PANEL in ro_agent.LAB_PANELS
    assert rt.VIRTUAL_W == 1280 and rt.VIRTUAL_H == 720


# --- the CLI's track and the DEV check's numbers --------------------------------------------------


def test_the_track_command_writes_frames_and_a_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cells = line((5, 5), (15, 5))
    raw = tmp_path / "raw.jsonl"
    rows = []
    for k, c in enumerate(cells):
        x, y = (None, None) if k == 4 else c
        rows.append(
            {
                "i": k,
                "frame": 100 + k,
                "t_mono_ns": 10**9 + k * 2 * 10**8,
                "t": k * DT,
                "x": x,
                "y": y,
                "reason": "ok" if x is not None else "no_glyph",
            }
        )
    raw.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(rt, "load_grid", lambda m, d, g=False: (fix_grid(), "synthetic"))
    out = tmp_path / "track.jsonl"
    assert rt.main(["track", str(raw), "--map", "fix.gat", "--mapcache", str(tmp_path),
                    "--t-to", str(8 * DT + 0.01), "--out", str(out)]) == 0  # fmt: skip
    lines = [json.loads(s) for s in out.read_text().splitlines()]
    frames, summary = lines[:-1], lines[-1]
    assert len(frames) == 9 and all(f["kind"] == "frame" for f in frames)
    assert frames[4]["source"] == "filled" and frames[4]["cell"] == list(cells[4])
    assert frames[4]["frame"] == 104 and frames[4]["t_mono_ns"] == rows[4]["t_mono_ns"]
    assert summary["kind"] == "summary" and summary["map"] == "fix"
    assert summary["sources"]["filled"] == 1 and summary["grid"]["source"] == "synthetic"
    assert rt.main(["track", str(raw), "--map", "fix", "--mapcache", str(tmp_path),
                    "--window", "0", "--out", str(out)]) == 1  # fmt: skip


@dataclasses.dataclass
class FakeTruth:
    map: str | None
    pos: tuple[float, float] | None


def test_check_rows_and_summary() -> None:
    frames = [
        {"t_mono_ns": 1, "raw": [10, 10], "cell": [10, 10], "source": "read", "drop": None},
        {"t_mono_ns": 2, "raw": None, "cell": [11, 10], "source": "filled", "drop": None},
        {"t_mono_ns": 3, "raw": [40, 10], "cell": [12, 10], "source": "filled",
         "drop": "outlier"},
        {"t_mono_ns": 4, "raw": None, "cell": None, "source": "unfilled", "drop": None},
        {"t_mono_ns": 5, "raw": [10, 10], "cell": [10, 10], "source": "read", "drop": None},
        {"t_mono_ns": 6, "raw": [10, 10], "cell": [10, 10], "source": "read", "drop": None},
    ]  # fmt: skip
    truths = {1: FakeTruth("fix.gat", (10.0, 10.0)), 2: FakeTruth("fix.gat", (11.4, 10.0)),
              3: FakeTruth("fix.gat", (12.0, 10.0)), 4: FakeTruth("fix.gat", (13.0, 10.0)),
              5: FakeTruth("other.gat", (10.0, 10.0)), 6: FakeTruth(None, None)}  # fmt: skip
    cls = {1: "standing", 2: "walking", 3: "walking", 4: "walking", 5: "standing",
           6: "excluded:gm_window"}  # fmt: skip

    def classify(tr: FakeTruth) -> str:
        return next(cls[k] for k, v in truths.items() if v is tr)

    def err(c: tuple[int, int], pos: Any) -> int:
        return max(abs(c[0] - math.floor(pos[0] + 0.5)), abs(c[1] - math.floor(pos[1] + 0.5)))

    rows = rt.check_rows(frames, truths.__getitem__, classify, err, "fix")
    assert [r["cls"] for r in rows] == ["standing", "walking", "walking", "walking",
                                        "excluded:other_map", "excluded:gm_window"]  # fmt: skip
    s = rt.check_summary(rows)
    a = s["all"]
    assert a["n"] == 4
    assert a["raw"]["cells"] == 2 and a["raw"]["coverage"] == 0.5
    assert a["raw"]["exact"] == 0.5 and a["raw"]["wrong_gt1"] == 1
    assert a["track"]["cells"] == 3 and a["track"]["coverage"] == 0.75
    assert a["track"]["exact"] == 1.0
    assert a["track_by_source"]["filled"]["cells"] == 2
    assert a["dropped_reads"] == {"n": 1, "exact": 0, "within1": 0, "wrong_gt1": 1}
    assert s["standing"]["n"] == 1 and s["walking"]["n"] == 3
    assert s["not_scored"] == {"excluded:other_map": 1, "excluded:gm_window": 1}
    assert "walking" in rt.check_table(s)
