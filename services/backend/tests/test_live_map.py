"""The live map on /flows (Batt 2026-11-21: "while a Run plays, a map like the minimap: where the
bot is as a green dot, the monsters it sees as red dots"): the player places the detector's monster
boxes on the map from her cell (flow_play.Sight, on the once-a-second hp_read record); the helper
keeps her map, her trail and those cells for the page (flow_run.Live). Display only."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402


def fake_uv() -> Any:
    """A linear stand-in for the camera (one cell = 40 px east, 30 px north): the test knows the
    answer, and the real projection's agreement is measured on a session (the commit message)."""
    import numpy as np

    return np.array([(640 + dx * 40, 400 - dy * 30) for dx, dy in dh.BOX_GRID], dtype=float)


def box(cx: float, foot: float, cls: str = "monster", species: str | None = "cruiser") -> Any:
    return types.SimpleNamespace(x0=cx - 15, y0=foot - 50, x1=cx + 15, y1=foot, score=0.9,
                                 cls=cls, species=species)  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_sight_places_monster_boxes_from_her_cell() -> None:
    clk = Clock()
    s = fp.Sight(uv=fake_uv, clock=clk)
    s.add([box(640 + 3 * 40, 400 - 2 * 30), box(640, 400, cls="player", species=None),
           box(600, 430, cls="item", species="apple"),
           box(640 - 40, 400 + 30, species=None)])  # fmt: skip
    # her own box, an item: never a red dot; a monster with no species is "monster"
    assert s.cells((100, 50)) == [[103, 52, "cruiser"], [99, 49, "monster"]]
    assert s.cells(None) == [] and s.cells(("x", 1)) == []
    clk.t += fp.SIGHT_MAX_AGE_S + 0.1  # the detector's last read is too old: no dot
    assert s.cells((100, 50)) == []
    s.add([])  # a read with no monster: none
    assert s.cells((100, 50)) == []


def test_a_failing_projection_never_stops_a_run() -> None:
    def broken() -> Any:
        raise RuntimeError("no camera")

    s = fp.Sight(uv=broken, clock=Clock())
    s.add([box(700, 380)])
    assert s.cells((10, 10)) == []


def test_the_hook_puts_the_cells_on_the_hp_record_once_a_second() -> None:
    recs: list[dict[str, Any]] = []
    player = types.SimpleNamespace(rec=types.SimpleNamespace(ev=recs.append))
    s = fp.Sight(uv=fake_uv, clock=Clock())
    hook = fp.HuntHook(player, fp.HuntResult(), sight=s)  # type: ignore[arg-type]
    s.add([box(640 + 40, 400)])
    hook.event({"kind": "hp_read", "pct": 90, "pos": [20, 30]}, 1.0)
    hook.event({"kind": "hp_read", "pct": 90, "pos": [21, 30]}, 1.5)  # within the second: not kept
    hook.event({"kind": "hp_read", "pct": 88, "pos": [22, 30]}, 2.1)
    assert [r["mobs"] for r in recs] == [[[21, 30, "cruiser"]], [[23, 30, "cruiser"]]]
    plain = fp.HuntHook(player, fp.HuntResult())  # type: ignore[arg-type]  # no sight: as before
    plain.event({"kind": "hp_read", "pct": 90, "pos": [20, 30]}, 9.0)
    assert "mobs" not in recs[-1]


def test_seen_boxes_feeds_the_sight_and_restores(monkeypatch: Any) -> None:
    import unit_detector as ud

    def fake_detect(self: Any, img: Any) -> list[Any]:
        return [box(640, 400 - 30)]

    monkeypatch.setattr(ud.GpuDetector, "detect", fake_detect)
    monkeypatch.setattr(ud.UnitDetector, "detect", fake_detect)
    s = fp.Sight(uv=fake_uv, clock=Clock())
    with fp.seen_boxes(fp.Seen(), s):
        ud.GpuDetector.detect(types.SimpleNamespace(), None)  # type: ignore[arg-type]
    assert s.cells((50, 60)) == [[50, 61, "cruiser"]]  # the detector's read reached the sight
    assert ud.GpuDetector.detect is fake_detect  # restored


def test_the_helper_keeps_her_map_trail_and_the_monsters() -> None:
    lv = fr.Live()
    s = 10**12
    lv.feed({"kind": "hp_read", "t_ns": s, "pct": 100, "map": "xmas_dun02"})
    for i, p in enumerate(([100, 50], [100, 50], [101, 50], [102, 51])):
        lv.feed({"kind": "hp_read", "t_ns": s + (i + 1) * 10**9, "pct": 100, "pos": p,
                 "mobs": [[105, 52, "cruiser"], ["bad"], [99, 49]]})  # fmt: skip
    lv.feed({"kind": "walk", "t_ns": s + 6 * 10**9, "to": [104, 52]})
    out = lv.summary()
    assert out["map"] == "xmas_dun02" and out["pos"] == [102, 51]
    assert out["trail"] == [[100, 50], [101, 50], [102, 51]]  # one a change
    assert out["mobs"] == [[105, 52, "cruiser"], [99, 49, "monster"]] and out["mobs_age_s"] == 2.0
    lv.feed({"kind": "hunt_end", "t_ns": s + 7 * 10**9, "n": 1})
    assert lv.summary()["mobs"] is None  # no hunt core: no monster on the map
    lv.feed({"kind": "hp_read", "t_ns": s + 8 * 10**9, "pct": 100, "map": "aldebaran"})
    out = lv.summary()  # another map: her cells there are another picture
    assert out["map"] == "aldebaran" and out["trail"] == [] and out["pos"] is None
    assert fr.sight_mobs(None) is None and fr.sight_mobs([]) == []
    assert len(fr.sight_mobs([[1, 2, "m"]] * 99) or []) == fr.SIGHT_MAX_MOBS == fp.SIGHT_MAX


def test_the_trail_is_capped() -> None:
    lv = fr.Live()
    for i in range(fr.TRAIL_N + 30):
        lv.feed({"kind": "hp_read", "t_ns": 10**12 + i, "pos": [i, 0]})
    tr = lv.summary()["trail"]
    assert len(tr) == fr.TRAIL_N and tr[-1] == [fr.TRAIL_N + 29, 0]
