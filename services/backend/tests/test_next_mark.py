"""The next-target MARK (scripts/next_mark.py; docs/planning/next-target-mark.md Amendment 3): the
player side's re-find for the runner's own --queue, swapped in for one hunt core."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "packages/poring_flow/src"))

import dungeon_hunt as dh  # noqa: E402
import next_mark as nm  # noqa: E402


def _qb(fx: float, fy: float, sp: str | None = "cookie", w: float = 30.0, h: float = 50.0) -> Any:
    """A detector box whose FOOT is (fx, fy) (test_dungeon_hunt's _qb)."""
    return NS(x0=fx - w / 2, y0=fy - h, x1=fx + w / 2, y1=fy, score=0.9, cls="monster", species=sp)


def _flat(here: nm.Cell, rel: nm.Cell) -> tuple[float, float]:
    """A flat test camera: 40 px a cell east, 30 px a cell south, her cell at FOOT_PX."""
    return dh.FOOT_PX[0] + 40.0 * rel[0], dh.FOOT_PX[1] + 30.0 * rel[1]


def _next(queue: Any, boxes: Any, aim: Any, *, trail: nm.CellTrail | None = None,
          accept: Any = None, now: float = 10.0, conf: nm.MarkConf | None = None,
          project: Any = None, values: Any = None, log: Any = None) -> dict[str, Any]:  # fmt: skip
    return nm.mark_next(queue, values, (lambda: boxes), accept or (lambda f: None), aim,
                        dh.QUEUE_MATCH_PX, order_of=dh.bq_order, own=dh.self_box,
                        trail=trail or nm.CellTrail(), project=project, now=now,
                        conf=conf or nm.MarkConf(), log=log)  # fmt: skip


def test_trail_gives_her_cell_at_a_time_and_keeps_still_cells_once() -> None:
    tr = nm.CellTrail(keep=3)
    assert tr.at(1.0) is None and tr.latest() is None
    tr.add(1.0, (10, 10))
    tr.add(1.2, (10, 10))  # still: one entry, its newest time
    tr.add(2.0, (11, 10))
    tr.add(1.5, (50, 50))  # out of order: ignored
    tr.add(2.5, None)  # no read: ignored
    assert tr.cells == [(10, 10), (11, 10)] and tr.ts == [1.2, 2.0]
    assert tr.at(0.5) == (10, 10) and tr.at(1.9) == (10, 10) and tr.at(2.0) == (11, 10)
    tr.add(3.0, (12, 10))
    tr.add(4.0, (13, 10))
    assert tr.cells == [(11, 10), (12, 10), (13, 10)] and tr.latest() == (13, 10)  # keep=3


def test_predict_foot_follows_her_step_and_keeps_the_box_offset() -> None:
    foot = (dh.FOOT_PX[0] + 40.0 * 3 + 5, dh.FOOT_PX[1] + 30.0 * -2 - 4)  # rel (3, -2) + offset
    # she did not move / anything unknown: the entry's own pixels
    assert nm.predict_foot(foot, (3, -2), (10, 10), (10, 10), _flat) == (foot, 0)
    assert nm.predict_foot(foot, None, (10, 10), (12, 10), _flat) == (foot, 0)
    assert nm.predict_foot(foot, (3, -2), None, (12, 10), _flat) == (foot, 0)
    assert nm.predict_foot(foot, (3, -2), (10, 10), (12, 10), None) == (foot, 2)
    # she stepped 2 east: the monster (world 13, 8) is now rel (1, -2), the +5 / -4 offset kept
    pred, moved = nm.predict_foot(foot, (3, -2), (10, 10), (12, 10), _flat)
    assert moved == 2
    assert pred == (dh.FOOT_PX[0] + 40.0 * 1 + 5, dh.FOOT_PX[1] + 30.0 * -2 - 4)


def test_mark_next_keeps_bq_next_contract_on_the_runner_s_own_cases() -> None:
    """The runner's own bq_next cases (test_dungeon_hunt) give the same answers through the mark
    when she did not move and every entry is still boxed: the mark changes only the re-find."""
    E = dh.QEntry
    sword = lambda b: ((10.0, 20.0), ["sword"])  # noqa: E731
    got = _next([], [], sword)
    assert got["what"] == "empty" and got["n"] == 0 and got["entry"] is None
    near_ = E(foot=(700, 400), species="poor", t=9, t0=9)
    far_ = E(foot=(1000, 300), species="rich", t=9, t0=9)
    fresh = [_qb(710, 400), _qb(1000, 310)]
    got = _next([near_, far_], fresh, sword)
    assert got["what"] == "pick" and got["entry"] is near_ and got["point"] == (10.0, 20.0)
    assert got["rank"] == 0 and got["moved_px"] == 10.0 and got["box"] is fresh[0]
    far_atk = dh.replace(far_, attacking=True)
    assert _next([near_, far_atk], fresh, sword)["entry"] is far_atk  # attacking first
    got = _next([near_, far_], fresh, sword, values={"rich": 900.0, "poor": 10.0})
    assert got["entry"] is far_  # --value-target's order
    got = _next([near_, far_], fresh, sword, accept=lambda f: "far" if f[0] < 800 else None)
    assert got["entry"] is far_ and got["why"] == ["far"]  # the skips pass over the near one
    # a NAMED box the runner refuses to aim (no SWORD): the mark tries the next entry, where the
    # runner's bq_next stopped at the first; both report the aimed entry's verdicts
    verd = iter([(None, ["walk"]), ((5.0, 6.0), ["sword"])])
    got = _next([near_, far_], fresh, lambda b: next(verd))
    assert got["what"] == "pick" and got["entry"] is far_ and got["why"] == ["verdict"]


def test_mark_next_refinds_after_her_step_where_bq_next_loses_it() -> None:
    """She stepped 2 cells east after the queue last saw the entry: every pixel moved 80 px west;
    the runner's re-find (60 px of the old foot) loses it, the mark finds the box where it now
    is."""
    tr = nm.CellTrail()
    tr.add(8.0, (10, 10))
    tr.add(9.5, (12, 10))
    e = dh.QEntry(foot=_flat((10, 10), (5, 0)), species="cookie", t=8.5, t0=8.0, rel=(5, 0))
    now_foot = _flat((12, 10), (3, 0))  # 80 px west of the old foot
    boxes = [_qb(*now_foot)]
    sword = lambda b: ((nm.foot_of(b)[0], nm.foot_of(b)[1] - 20), ["sword"])  # noqa: E731
    old = dh.bq_next([e], None, lambda: boxes, lambda f: None, sword)
    assert old["what"] == "refind_fail" and old["why"] == ["gone"]
    got = _next([e], boxes, sword, trail=tr, project=_flat)
    assert got["what"] == "pick" and got["box"] is boxes[0] and got["entry"] is e


def test_mark_next_hovers_the_predicted_spot_when_no_box_is_there() -> None:
    """No box at the entry's spot (the detector missed it): the spot itself goes to the runner's
    accept and aim (a SWORD there strikes it); at most hover_max such spots a pick; an entry older
    than ttl_s is dropped; the mark logs how each entry went."""
    E = dh.QEntry
    a = E(foot=(700, 400), species="cookie", t=9.0, t0=9.0)
    b = E(foot=(900, 450), species="cruiser", t=9.0, t0=9.0)
    c = E(foot=(500, 300), species="cookie", t=9.0, t0=9.0)
    aimed: list[Any] = []

    def no_sword(bx: Any) -> Any:
        aimed.append(bx)
        return None, ["walk"]

    logs: list[dict[str, Any]] = []
    got = _next([a, b, c], [], no_sword, log=logs.append)
    assert got["what"] == "refind_fail" and got["why"] == ["verdict", "verdict", "gone"]
    assert len(aimed) == 2 and all(isinstance(x, nm.SynthBox) for x in aimed)  # hover_max 2
    assert nm.foot_of(aimed[0]) == (700.0, 400.0) and aimed[0].species == "cookie"
    assert logs[-1]["what"] == "refind_fail" and [t["how"] for t in logs[-1]["tried"]] == [
        "predicted", "predicted", "gone"]  # fmt: skip
    got = _next([a], [], lambda bx: ((700.0, 380.0), ["sword"]))
    assert got["what"] == "pick" and isinstance(got["box"], nm.SynthBox) and got["entry"] is a
    got = _next([a], None, lambda bx: ((700.0, 380.0), ["sword"]))  # no detection came: the spot
    assert got["what"] == "pick" and got["why"] == ["no_detection"]
    got = _next([a], [], no_sword, conf=nm.MarkConf(hover_max=0))
    assert got["what"] == "refind_fail" and got["why"] == ["gone"]  # spots off: bq_next's own
    old = dh.replace(a, t=1.0)
    got = _next([old, b], [], lambda bx: ((1.0, 2.0), ["sword"]), now=10.0)
    assert got["entry"] is b and got["why"] == ["old"]  # 9 s > ttl 8 s: dropped
    got = _next([a], [], lambda bx: ((1.0, 2.0), ["sword"]), accept=lambda f: "unreachable")
    assert got["what"] == "refind_fail" and got["why"] == ["unreachable"]  # the box path's skips


def test_mark_next_aims_at_most_aim_max_entries() -> None:
    E = dh.QEntry
    q = [E(foot=(600 + 50 * i, 400), species="cookie", t=9.0, t0=9.0) for i in range(5)]
    boxes = [_qb(600 + 50 * i, 400) for i in range(5)]
    n = [0]

    def no(bx: Any) -> Any:
        n[0] += 1
        return None, ["walk"]

    got = _next(q, boxes, no)
    assert n[0] == nm.AIM_MAX and got["what"] == "refind_fail" and got["why"][-1] == "aim_max"


def test_marking_swaps_bq_next_for_one_hunt_core_only_when_on() -> None:
    saved = dh.bq_next
    tr = nm.CellTrail()
    with nm.marking(dh, {"mark": True, "queue": False}, tr, None):
        assert dh.bq_next is saved  # the queue (its body) is off: unchanged
    with nm.marking(dh, {"mark": False, "queue": True}, tr, None):
        assert dh.bq_next is saved
    logs: list[dict[str, Any]] = []
    with nm.marking(dh, {"mark": True, "queue": True, "mark_ttl_s": 5.0, "mark_hover_max": 1},
                    tr, None, logs.append, clock=lambda: 10.0):  # fmt: skip
        assert dh.bq_next is not saved
        e = dh.QEntry(foot=(700, 400), species="cookie", t=9.0, t0=9.0)
        got = dh.bq_next([e], None, lambda: [], lambda f: None, lambda b: ((1.0, 2.0), ["sword"]))
        assert got["what"] == "pick" and isinstance(got["box"], nm.SynthBox)
    assert dh.bq_next is saved  # put back
    assert logs[0] == {"kind": "mark", "what": "on", "version": nm.MARK_VERSION, "ttl_s": 5.0,
                       "hover_max": 1, "projection": False}  # fmt: skip
    assert logs[1]["kind"] == "mark" and logs[1]["what"] == "pick"


def test_runner_projection_is_the_runner_s_own_on_the_lab_map() -> None:
    """The mark's projection equals the runner's (camera_rdp.json + the map's GAT altitudes) where
    the GAT is on this install; none -> None (the entry's own pixels)."""
    assert nm.runner_projection("no_such_map_xyz") is None
    from poring_dataset import camera as cam

    if not (cam.GAT_DIR / "xmas_dun02.gat").exists():
        return  # this install has no lab GAT (the client's data is never committed)
    import drop_blobs

    pr = nm.runner_projection("xmas_dun02")
    assert pr is not None
    ref = drop_blobs.Projector("xmas_dun02")
    here = (114, 30)
    for rel in ((0, 0), (3, -2), (-5, 4)):
        u, v = pr(here, rel)
        ru, rv = ref.project(here, [(here[0] + rel[0], here[1] + rel[1])])[0]
        assert abs(u - ru) < 1e-6 and abs(v - rv) < 1e-6
    u0, v0 = pr(here, (0, 0))
    assert abs(u0 - dh.FOOT_PX[0]) < 3 and abs(v0 - dh.FOOT_PX[1]) < 3


def test_the_mark_s_settings_are_the_player_s_and_need_the_queue() -> None:
    from poring_flow import settings as st

    by = {f.name: f for f in st.FIELDS}
    for n in ("mark", "mark_ttl_s", "mark_hover_max"):
        assert by[n].player and not by[n].flag and not by[n].tune
    assert st.DEFAULTS["mark"] is False  # off until its A/B passes
    assert st.DEFAULTS["mark_ttl_s"] == nm.TTL_S and st.DEFAULTS["mark_hover_max"] == nm.HOVER_MAX
    assert not st.in_use("mark", {**st.DEFAULTS, "mark": True})  # needs the runner's queue
    assert st.in_use("mark", {**st.DEFAULTS, "mark": True, "queue": True})
    assert nm.conf_of(st.DEFAULTS) == nm.MarkConf()
