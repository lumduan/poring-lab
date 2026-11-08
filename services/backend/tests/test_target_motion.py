"""scripts/target_motion.py (rogue-xmas02.md 4V): was a strike's target walking?"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import target_motion as tm  # noqa: E402

MS = 10**6


def appear(gid: int, t: int, x: int, y: int, x1: int | None = None, y1: int | None = None,
           speed: int = 200) -> dict[str, object]:  # fmt: skip
    return {"type": "entity_appear", "objtype": 5, "gid": gid, "t_mono_ns": t,
            "kind": "stand" if x1 is None else "move", "x": x, "y": y, "x1": x1, "y1": y1,
            "speed": speed}  # fmt: skip


def test_position_interpolates_a_move_and_stops() -> None:
    trs = tm.tracks([appear(1, 1000 * MS, 10, 10, 14, 10, speed=200),  # 4 cells in 800 ms
                     {"type": "entity_stop", "gid": 1, "t_mono_ns": 2000 * MS, "x": 14, "y": 10},
                     {"type": "entity_vanish", "gid": 1, "t_mono_ns": 3000 * MS}])  # fmt: skip
    tr = trs[1]
    assert tm.position(tr, 999 * MS) is None
    assert tm.position(tr, 1400 * MS) == (12.0, 10.0, True)  # half way, moving
    assert tm.position(tr, 1900 * MS) == (14.0, 10.0, False)  # arrived
    assert tm.position(tr, 2500 * MS) == (14.0, 10.0, False)  # stopped
    assert tm.position(tr, 3000 * MS) is None  # gone


def test_study_marks_a_walking_box_target_and_its_class() -> None:
    packets = [{"type": "self_move", "t_mono_ns": 500 * MS, "x0": 0, "y0": 0, "x1": 10, "y1": 10},
               appear(7, 900 * MS, 12, 10, 16, 10, speed=400),  # walking east, 1.6 s
               appear(8, 900 * MS, 10, 13)]  # standing  # fmt: skip
    events = [{"kind": "box_target", "struck": True, "t_ns": 1300 * MS,
               "verdict_from_grab_ms": 300},  # grab at 1000 ms
              {"kind": "strike", "by": "box", "t_ns": 1350 * MS, "rel": [3, 0]},
              {"kind": "strike", "by": "scan", "t_ns": 1400 * MS, "rel": [0, 3]}]  # fmt: skip
    rows = tm.study(events, packets, {1350 * MS: "D", 1400 * MS: "K"})
    box, scan = rows
    assert box["by"] == "box" and box["class"] == "D" and box["target"]["gid"] == 7
    assert box["target"]["moving_grab"] is True and box["target"]["moving_click"] is True
    assert box["target"]["moved_cells"] == 0.88  # 350 ms at 400 ms a cell
    assert scan["target"]["gid"] == 8 and scan["target"]["moving_grab"] is False
    assert tm.summary(rows) == {"walking:D": 1}
    assert tm.summary(rows, None) == {"standing:notD": 1, "walking:D": 1}


def test_no_monster_near_the_clicked_cell() -> None:
    packets = [{"type": "self_move", "t_mono_ns": 0, "x0": 0, "y0": 0, "x1": 10, "y1": 10},
               appear(9, 1, 30, 30)]  # fmt: skip
    rows = tm.study([{"kind": "strike", "by": "box", "t_ns": 5 * MS, "rel": [1, 0]}], packets)
    assert rows[0]["target"] is None and tm.summary(rows) == {"none:?": 1}
