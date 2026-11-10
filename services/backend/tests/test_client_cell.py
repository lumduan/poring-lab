"""scripts/client_cell.py (rogue-xmas02.md Study S-LF5): where the CLIENT drew the Rogue, from the
runner's monster boxes and the packets' monster cells. A linear stub camera for the synthetic
cases, the runner's real camera (camera_rdp.json, flat floor) for one REAL detection copied from
p53 (894.65 s: the two boxes, the two server monsters; numbers only, no pixels)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "packages/poring_dataset/src"))

import client_cell as cc  # noqa: E402

S = 1_000_000_000
MS = 1_000_000
US, MOB, MOB2 = 2000002, 110000001, 110000002
PX_X, PX_Y, CX, CY = 34.0, 27.0, 640.0, 362.0  # the stub: ~the runner's camera near the centre

Arr = npt.NDArray[np.float64]


def stub_project(off: Arr, alt: Arr) -> Arr:
    return np.c_[CX + PX_X * off[:, 0], CY - PX_Y * off[:, 1]]


def flat(cells: Arr) -> Arr:
    return np.zeros(len(cells))


def foot(cell: tuple[float, float], centre: tuple[int, int]) -> tuple[float, float]:
    """Where the stub draws a monster on ``cell`` with the camera on ``centre``."""
    return CX + PX_X * (cell[0] - centre[0]), CY - PX_Y * (cell[1] - centre[1])


def box(cell: tuple[float, float], centre: tuple[int, int]) -> list[Any]:
    u, v = foot(cell, centre)
    return [u - 18, v - 100, u + 18, v, 0.95, "monster"]


def pk(t: float, typ: str, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), "type": typ, **kw}


def move(t: float, a: tuple[int, int], b: tuple[int, int]) -> dict[str, Any]:
    return pk(t, "self_move", server_tick=int(t * S) // MS, x0=a[0], y0=a[1], x1=b[0], y1=b[1])


def stand(t: float, gid: int, x: int, y: int) -> dict[str, Any]:
    return pk(t, "entity_appear", gid=gid, objtype=5, kind="stand", x=x, y=y, speed=400,
              name="Myst Case", job=1249)  # fmt: skip


def det(t: float, boxes: list[list[Any]]) -> dict[str, Any]:
    return {"t_ns": int(t * S), "ms": 0.0, "boxes": boxes}


# --- fit_centre ---------------------------------------------------------------------------------


def test_fit_finds_the_drawn_centre_not_the_guess() -> None:
    mobs = [(117.0, 185.0), (105.0, 189.0)]
    feet = [foot(m, (104, 189)) for m in mobs]
    f = cc.fit_centre(feet, mobs, (104, 192), stub_project, flat)
    assert f.best == (104, 189)
    assert f.matched == 2 and f.n_boxes == 2
    assert f.cost < 1.0 and f.cost_guess == 2 * cc.CAP_PX  # both boxes ~81 px off at the guess


def test_fit_ignores_a_false_box() -> None:
    mobs = [(110.0, 190.0), (100.0, 195.0)]
    feet = [foot(m, (105, 192)) for m in mobs] + [(200.0, 650.0)]  # no monster there
    f = cc.fit_centre(feet, mobs, (105, 192), stub_project, flat)
    assert f.best == (105, 192) and f.matched == 2 and f.n_boxes == 3
    assert f.cost == f.cost_guess == round(cc.CAP_PX, 1)  # the false box costs the cap anywhere


def test_fit_with_the_runners_camera_on_p53s_real_detection() -> None:
    """p53 894.649 s (grab): monster feet (1101.6, 450.9) and (681.25, 366.0); the server monsters
    at grab - 0.16 s: a Myst Case at (117, 185) and the Cruiser at (105, 189); our server cell
    (104, 192). Flat floor here (the GAT is client data, never committed): the real fit (with the
    GAT) gave (104, 189) at 9 / 9 px against 82 / 76 px at (104, 192)."""
    from poring_dataset import camera as cam

    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    f = cc.fit_centre([(1101.6, 450.9), (681.25, 366.0)], [(117.0, 185.0), (105.0, 189.0)],
                      (104, 192), camera.project, flat)  # fmt: skip
    assert f.best == (104, 189)
    assert f.matched == 2 and f.cost_guess - f.cost > 100


# --- votes / verdict / read_verdicts ------------------------------------------------------------


def fit_row(t: float, srv: tuple[int, int], best: tuple[int, int], matched: int,
            cost: float = 10.0, cost_guess: float = 120.0) -> dict[str, Any]:  # fmt: skip
    if best == srv:
        cost_guess = cost
    return {"t_ns": int(t * S), "srv": srv, "walking": False, "standing": True,
            "fit": cc.Fit(best, cost, cost_guess, matched, matched)}  # fmt: skip


def test_votes_need_a_match_a_margin_and_the_same_server_cell() -> None:
    srv = (104, 192)
    fits = [fit_row(10.0, srv, (104, 189), 2),
            fit_row(10.5, srv, (104, 189), 1, cost=50.0, cost_guess=60.0),  # margin 10 < 30
            fit_row(11.0, srv, (104, 189), 0),  # nothing matched
            fit_row(11.2, (100, 100), (104, 189), 2),  # another server cell
            fit_row(13.0, srv, (104, 189), 2),  # outside the window
            fit_row(10.8, srv, srv, 1)]  # fmt: skip
    assert cc.votes(fits, int(10.4 * S), srv) == {(104, 189): 2, srv: 1}


def test_verdict_desync_misread_unjudged() -> None:
    srv = (104, 192)
    assert cc.verdict({(104, 189): 3, srv: 1}, srv, read=(104, 189)) == ("client", (104, 189))
    assert cc.verdict({(104, 189): 1, srv: 3}, srv, read=(104, 189)) == ("server", srv)
    assert cc.verdict({(104, 189): 1}, srv, read=(104, 189)) == ("unjudged", None)  # one box
    # the off votes must sit by the read ...
    assert cc.verdict({(108, 192): 4}, srv, read=(104, 189)) == ("unjudged", None)
    # ... and agree with each other: two scattered off cells do not add up (p51 1166 s)
    assert cc.verdict({(84, 94): 1, (85, 92): 1, (83, 96): 1}, (83, 96)) == ("unjudged", None)
    assert cc.verdict({(84, 94): 1, (85, 94): 1}, (83, 96)) == ("client", (85, 94))


def test_read_verdicts_judge_slf_wrong_rows() -> None:
    srv = (104, 192)
    t0 = 100 * S
    fits = [fit_row(t, srv, (104, 189), 2) for t in (994.6, 995.6, 996.6)]
    fits += [fit_row(1199.5, (50, 50), (50, 50), 2)]
    wrong = [{"t": 895.13, "pos": [104, 189], "true": [104, 192]},  # the client drew it: desync
             {"t": 1099.6, "pos": [50, 54], "true": [50, 50]},  # the server cell holds: misread
             {"t": 500.0, "pos": [1, 1], "true": [9, 9]}]  # no fit: unjudged  # fmt: skip
    got = [r["verdict"] for r in cc.read_verdicts(wrong, fits, t0)]
    assert got == ["desync", "misread", "unjudged"]
    assert cc.read_verdicts(wrong[:1], fits, t0)[0]["client_cell"] == [104, 189]


# --- detection_fits + walk_rows on a synthetic run -----------------------------------------------


def desync_run() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """p53's shape: at 10.0 s her own hit (src_speed 233), at 10.017 s the walk ack (105,188) ->
    (104,192) (4 cells, ~0.66 s); the client stops after its first step (104,189) and the camera
    stays there; at 16.0 s our stop at (104,192) (the server's confirmation). A control walk at
    20.0 s that the client follows."""
    packets = [stand(1.0, MOB, 105, 189), stand(1.0, MOB2, 117, 185),
               move(2.0, (100, 188), (105, 188)),
               pk(10.0, "act", src_gid=US, target_gid=MOB, damage=200, src_speed=233, dmotion=432),
               move(10.017, (105, 188), (104, 192)),
               pk(10.037, "act", src_gid=MOB, target_gid=US, damage=0, src_speed=1296, dmotion=0),
               pk(16.0, "entity_stop", gid=US, x=104, y=192),
               move(20.0, (104, 192), (106, 192)),
               pk(24.0, "entity_stop", gid=US, x=106, y=192)]  # fmt: skip
    mobs = [(105, 189), (117, 185)]
    dets = [det(t, [box(m, (104, 189)) for m in mobs]) for t in (11.5, 12.5, 13.5, 14.5)]
    dets += [det(t, [box(m, (106, 192)) for m in mobs]) for t in (21.5, 22.5)]
    return packets, dets


def test_walk_rows_find_the_short_walk_and_its_context() -> None:
    packets, dets = desync_run()
    fits = cc.detection_fits(dets, packets, stub_project, flat)
    assert all(r["fit"].matched == 2 for r in fits)
    rows = cc.walk_rows(packets, fits, 0, 30 * S)
    by_t = {round(r["t_ns"] / S, 3): r for r in rows}
    w = by_t[10.017]
    assert w["outcome"] == "short" and w["client"] == [104, 189] and w["confirmed"] == [104, 192]
    assert w["own_motion_ms"] == [17] and w["miss_ms"] == [20] and w["flinch_ms"] == []
    assert by_t[20.0]["outcome"] == "followed" and by_t[20.0]["client"] == [106, 192]
    assert by_t[2.0]["outcome"] == "unknown"  # no fit after it


def test_walk_rows_need_the_servers_confirmation() -> None:
    packets, dets = desync_run()
    packets = [p for p in packets if not (p["type"] == "entity_stop" and p["t_mono_ns"] == 16 * S)]
    packets.append(move(16.0, (103, 192), (104, 194)))  # the server stopped her elsewhere
    fits = cc.detection_fits(dets, packets, stub_project, flat)
    w = next(r for r in cc.walk_rows(packets, fits, 0, 30 * S) if r["t_ns"] == int(10.017 * S))
    assert w["confirmed"] == [103, 192] and w["outcome"] == "unknown"


# --- floor_walkoffs ------------------------------------------------------------------------------


def strike(t: float, clicks: int, rel: tuple[int, int] = (-1, 3)) -> dict[str, Any]:
    return {"t_ns": int(t * S), "t_end_ns": int((t + 1.8) * S), "kind": "strike", "by": "box",
            "rel": list(rel), "clicks": clicks}  # fmt: skip


def test_floor_walkoffs_count_a_reclick_that_walks_off_a_live_target() -> None:
    packets = [stand(1.0, MOB, 105, 189),
               pk(5.36, "self_move_request", x=105, y=188), move(5.36, (106, 186), (105, 188)),
               pk(5.63, "attack_request", target_gid=MOB),
               pk(5.8, "act", src_gid=US, target_gid=MOB, damage=190),
               pk(6.76, "self_move_request", x=104, y=192),  # the re-click: 3 cells off it
               pk(12.56, "act", src_gid=US, target_gid=MOB, damage=190)]  # fmt: skip
    rows = cc.floor_walkoffs([strike(5.0, 2)], packets)
    assert len(rows) == 1
    r = rows[0]
    assert r["walk_to"] == [104, 192] and r["off_cells"] == 3.0 and r["dist"] == 3
    assert r["next_hit_s"] == 5.8 and r["vanish_s"] is None
    # one click: a later walk is the client chasing, not counted
    assert cc.floor_walkoffs([strike(5.0, 1)], packets) == []
    # a walk beside the target (the client's own move-to-attack) is not a walk-off
    beside = [p if p.get("x") != 104 else {**p, "x": 104, "y": 190} for p in packets]
    assert cc.floor_walkoffs([strike(5.0, 2)], beside) == []
    # the target died right after: not counted
    dead = [*packets, pk(6.9, "entity_vanish", gid=MOB, reason=1)]
    assert cc.floor_walkoffs([strike(5.0, 2)], dead) == []


def test_strike_firsts_time_the_first_request_and_bands() -> None:
    packets = [pk(5.36, "self_move_request", x=105, y=188),
               pk(5.63, "attack_request", target_gid=MOB)]  # fmt: skip
    rows = cc.strike_firsts([strike(5.0, 2), strike(9.0, 1, rel=(0, 6)), strike(20.0, 1, (1, 0))],
                            packets)  # fmt: skip
    got = [(r["band"], r["reclicked"], r["first_s"]) for r in rows]
    assert got == [("2-3", True, 0.36), ("4+", False, None), ("0-1", False, None)]
    s = cc.summary([{"walks": [], "reads": [], "floor_walkoffs": [], "n_fits": 0, "n_within1": 0,
                     "strikes": rows}])  # fmt: skip
    assert s["strikes"]["2-3"] == {"n": 1, "reclicked": 1, "no_request": 0, "first_p50_s": 0.36,
                                   "first_max_s": 0.36}  # fmt: skip
    assert s["strikes"]["4+"]["no_request"] == 1
