"""poring_dataset timeline / projection / labels / shards / metrics, on synthetic data."""

from pathlib import Path

import numpy as np
import pytest

from poring_dataset import labels as lb
from poring_dataset import metrics, projection, shards
from poring_dataset.mapcache import MapGrid
from poring_dataset.timeline import Timeline, tick_of

MS = 1_000_000
T0 = 700_000_000 * MS  # a host CLOCK_MONOTONIC in ns; server tick = t // 1e6 mod 2^32


def ev(t_ms: int, type_: str, **fields: object) -> dict[str, object]:
    return {"t_mono_ns": T0 + t_ms * MS, "type": type_, **fields}


def walled_grid() -> MapGrid:
    """20x20 floor with a wall at x=10, y in 5..14."""
    cells = bytearray(20 * 20)
    for y in range(5, 15):
        cells[10 + y * 20] = 1
    return MapGrid("lab", 20, 20, bytes(cells))


def test_world_at_follows_events_and_interpolates_walks() -> None:
    tick0 = tick_of(T0)
    events = [
        ev(0, "map_change", map="lab", x=5, y=5),
        ev(
            10,
            "entity_appear",
            kind="new",
            gid=7,
            char_id=0,
            objtype=5,
            job=1002,
            speed=200,
            name="Poring",
            x=2,
            y=2,
        ),  # fmt: skip
        ev(100, "self_move", server_tick=tick0 + 100, x0=5, y0=5, x1=8, y1=5),
        ev(900, "entity_vanish", gid=7, reason=0),
    ]
    tl = Timeline(events, snapshot_every=2)
    assert tl.frame_world(T0 + 50 * MS).self_pos == (5.0, 5.0)
    mid = tl.frame_world(T0 + 175 * MS).self_pos  # 75 ms into a 150 ms step
    assert mid == pytest.approx((5.5, 5.0))
    assert tl.frame_world(T0 + 600 * MS).self_pos == (8.0, 5.0)
    assert [e.gid for e in tl.frame_world(T0 + 500 * MS).entities] == [7]
    assert tl.frame_world(T0 + 1000 * MS).entities == ()


def test_walks_follow_the_real_path_around_walls() -> None:
    tick0 = tick_of(T0)
    events = [
        ev(0, "map_change", map="lab", x=8, y=10),
        ev(1, "self_move", server_tick=tick0 + 1, x0=8, y0=10, x1=12, y1=10),
    ]
    with_grid = Timeline(events, {"lab": walled_grid()})
    without = Timeline(events)
    # Straight through x=10 without the map; around the wall (y<5 or y>14) with it.
    xs_with = [with_grid.frame_world(T0 + t * MS).self_pos for t in range(1, 3000, 50)]
    assert all(not (round(p[0]) == 10 and 5 <= round(p[1]) <= 14) for p in xs_with if p)
    straight = [without.frame_world(T0 + t * MS).self_pos for t in range(1, 1000, 25)]
    assert any(round(p[0]) == 10 and round(p[1]) == 10 for p in straight if p)


def test_homography_fit_recovers_a_known_projection() -> None:
    h_true = np.array([[30.0, -12.0, 392.0], [8.0, -26.0, 330.0], [0.002, -0.004, 1.0]])
    cells = np.array([[dx, dy] for dx in range(-4, 5, 2) for dy in range(-4, 5, 2)], dtype=float)
    pixels = projection.project(h_true, cells)
    fit = projection.fit(cells, pixels + np.random.default_rng(3).normal(0, 0.5, pixels.shape))
    assert fit.median_px < 1.5 and fit.p95_px < 2.5
    assert np.allclose(
        projection.project(fit.h, [[1.0, 1.0]]), projection.project(h_true, [[1, 1]]), atol=2
    )
    with pytest.raises(ValueError):
        projection.fit_homography(cells[:3], pixels[:3])


def test_labels_hang_from_the_projected_feet_and_skip_the_gm() -> None:
    h = np.array([[30.0, 0, 392.0], [0, -30.0, 330.0], [0, 0, 1.0]])  # 30 px/cell, y up
    events = [
        ev(0, "login_accepted", aid=99, sex=0),
        ev(1, "map_change", map="lab", x=10, y=10),
        ev(
            2,
            "entity_appear",
            kind="new",
            gid=7,
            char_id=0,
            objtype=5,
            job=1002,
            speed=200,
            name="Poring",
            x=12,
            y=10,
        ),  # fmt: skip
        ev(
            3,
            "entity_appear",
            kind="new",
            gid=99,
            char_id=1,
            objtype=0,
            job=0,
            speed=150,
            name="GM",
            x=10,
            y=10,
        ),  # fmt: skip
    ]
    frame = Timeline(events).frame_world(T0 + 10 * MS)
    out = lb.labels_for(frame, h, (784, 625), exclude_gids=[99])
    assert [x.cls for x in out] == ["monster"]
    box = out[0]
    assert box.x0 + (box.x1 - box.x0) / 2 == pytest.approx(392 + 60)  # 2 cells right
    assert box.y1 == pytest.approx(330)  # feet on the projected cell
    cls, cx, cy, w, hh = box.yolo(784, 625).split()
    assert cls == "1" and 0 < float(cx) < 1 and 0 < float(w) < 1


def test_gm_windows() -> None:
    windows = lb.gm_windows([{"t_mono_ns": 5_000, "gm_command": True}, {"t_mono_ns": 9_000}])
    assert lb.in_windows(5_000 + 1_000_000_000, windows) and not lb.in_windows(4_999, windows)


def test_png_and_shards_round_trip(tmp_path: Path) -> None:
    rng = np.random.default_rng(5)
    frames = [rng.integers(0, 256, (25, 31, 3), dtype=np.uint8) for _ in range(5)]
    assert np.array_equal(shards.decode_png(shards.encode_png(frames[0])), frames[0])
    bgra = rng.integers(0, 256, (4, 6, 4), dtype=np.uint8)
    assert np.array_equal(shards.decode_png(shards.encode_png(bgra)), bgra)
    writer = shards.ShardWriter(tmp_path, max_bytes=3000)
    for i, img in enumerate(frames):
        writer.add(i, T0 + i, img, t_wall="x")
    writer.close()
    assert len(writer.shards) >= 2  # rotated by size
    back = [item for name in writer.shards for item in shards.read_shard(tmp_path / name)]
    assert [m["frame_id"] for m, _ in back] == list(range(5))
    assert all(np.array_equal(img, frames[m["frame_id"]]) for m, img in back)  # lossless
    path = shards.write_manifest(tmp_path, {"frames": 5})
    assert path.name == "manifest.json" and not list(tmp_path.glob(".*.tmp"))


def test_iou_and_greedy_matching() -> None:
    assert metrics.iou(("m", 0, 0, 10, 10), ("m", 0, 0, 10, 10)) == 1.0
    assert metrics.iou(("m", 0, 0, 10, 10), ("m", 5, 0, 15, 10)) == pytest.approx(1 / 3)
    truth = [("m", 0, 0, 10, 10), ("p", 20, 20, 30, 40)]
    pred = [("m", 1, 0, 11, 10), ("m", 50, 50, 60, 60), ("p", 21, 20, 31, 40)]
    m = metrics.match(truth, pred)
    assert (m.tp, m.fp, m.fn) == (2, 1, 0)
    assert m.precision == pytest.approx(2 / 3) and m.recall == 1.0 and m.mean_iou > 0.8


def test_decode_png_handles_every_row_filter() -> None:
    """Windows' PNGs (CopyFromScreen) use filters 1-4; a hand-built PNG exercises each."""
    import struct as st
    import zlib as zl

    rng = np.random.default_rng(9)
    rgb = rng.integers(0, 256, (5, 4, 3), dtype=np.uint8)
    rows, prev = [], np.zeros(12, dtype=np.int32)
    for y, kind in enumerate([0, 1, 2, 3, 4]):
        cur = rgb[y].reshape(-1).astype(np.int32)
        enc = np.zeros(12, dtype=np.int32)
        for x in range(12):
            a = int(cur[x - 3]) if x >= 3 else 0
            b = int(prev[x])
            c = int(prev[x - 3]) if x >= 3 else 0
            pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
            pred = [0, a, b, (a + b) // 2, a if pa <= pb and pa <= pc else (b if pb <= pc else c)][
                kind
            ]
            enc[x] = (int(cur[x]) - pred) & 0xFF
        rows.append(bytes([kind]) + enc.astype(np.uint8).tobytes())
        prev = cur

    def chunk(k: bytes, body: bytes) -> bytes:
        return st.pack(">I", len(body)) + k + body + st.pack(">I", zl.crc32(k + body))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", st.pack(">IIBBBBB", 4, 5, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zl.compress(b"".join(rows))) + chunk(b"IEND", b""))  # fmt: skip
    assert np.array_equal(shards.decode_png(png), rgb[:, :, ::-1])


def test_session_events_start_at_the_last_map_change_before_the_first_frame() -> None:
    from poring_dataset.timeline import session_events

    s = 1_000_000_000
    ev = [
        {"type": "map_change", "t_mono_ns": 10 * s, "map": "a"},
        {"type": "map_change", "t_mono_ns": 50 * s, "map": "b"},  # the anchor
        {"type": "entity_appear", "t_mono_ns": 60 * s, "gid": 7},  # before t0, still on screen
        {"type": "entity_stop", "t_mono_ns": 140 * s, "gid": 7},
        {"type": "entity_stop", "t_mono_ns": 300 * s, "gid": 7},  # after t1 + margin
    ]
    kept, anchor = session_events(ev, 100 * s, 200 * s)
    assert [e["t_mono_ns"] // s for e in kept] == [50, 60, 140]
    assert anchor == {"type": "map_change", "seconds_before_t0": 50.0}
    # out of the lookback: only the margin window, and no anchor
    kept, anchor = session_events(ev, 100 * s, 200 * s, lookback_ns=20 * s)
    assert [e["t_mono_ns"] // s for e in kept] == [140] and anchor is None
