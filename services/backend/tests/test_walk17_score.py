"""scripts/walk17_score.py (walk@17, offline): walk15_score.py's counts for the rule walk@17, which
walk_readiness.py reads, plus walk@17's own: the /where lines of the run (the guard's log, its run
id = the session id) with their reasons, other runs' /where and refusals in the window, the
relocalisations by method against the packets, warp-area refusals and accidental map changes, and
the legs. On a synthetic session (the verifier's output written by hand)."""

from __future__ import annotations

import datetime as dt
import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
S = 1_000_000_000
GM = 2_000_002
SID = "20261009T150000-demo-walk17-alone-clean-indoor"
T0_WALL = dt.datetime(2026, 10, 9, 15, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=7)))


def load(name: str) -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = load("walk17_score")
wr = load("walk_readiness")


def route(i: int, t: float, status: str, cause: str | None, **evidence: Any) -> dict[str, Any]:
    return {"record_id": f"r{i}", "session": SID, "rule": "walk@17", "t_mono_ns": int(t * S),
            "t_done_ns": int((t + 20) * S),
            "action": {"type": "walk", "intended": {"kind": "route", "cell": [5, 5],
                                                    "note": f"route {i} from believed 1,1"}},
            "outcome": {"status": status, "cause": cause,
                        "evidence": {"events": [], "decline": None, **evidence}}}  # fmt: skip


def click(i: int, t: float, frm: list[int], cell: list[int]) -> dict[str, Any]:
    return {"record_id": f"c{i}", "session": SID, "rule": "walk@17/click", "t_mono_ns": int(t * S),
            "action": {"type": "walk", "intended": {"kind": "cell", "cell": cell}},
            "outcome": {"status": "success", "cause": None,
                        "evidence": {"believed_position": frm,
                                     "target": [{"tier": "A", "cell": [0, 0]}]}}}  # fmt: skip


def wall(seconds: float) -> str:
    return (T0_WALL + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S%z")


def session(tmp: Path) -> tuple[Path, Path]:
    d = tmp / SID
    d.mkdir()
    man = {"session_id": SID, "t0_mono_ns": 1 * S, "t1_mono_ns": 500 * S,
           "t0_wall": T0_WALL.timestamp(), "t1_wall": T0_WALL.timestamp() + 600,
           "where_budget": 56, "warp_map": "prt_church", "click_max_safe": 14,
           "warp_areas": [{"cell": [100, 56], "span": [7, 1], "to_map": "prontera"}]}  # fmt: skip
    (d / "manifest.json").write_text(json.dumps(man))
    fix_ok = {"ok": True, "method": "minimap", "to": [3, 4], "t": int(31 * S)}
    fix_bad = {"ok": True, "method": "where", "to": [9, 9], "t": int(61 * S)}
    held = {"ok": False, "method": "where", "rejects": ["held:where_retry"], "t": int(71 * S)}
    start = {"ok": True, "method": "where", "to": [1, 1], "t": int(11 * S),
             "reason": "walk@17 route_start_indoor"}  # fmt: skip
    warp_refusal = {"from": [1, 1], "end": [2, 1], "outcome": "no_safe_point",
                    "warp_area": [100, 56]}  # fmt: skip
    far_refusal = {"from": [1, 1], "end": [30, 1], "outcome": "no_safe_point",
                   "beyond_click_max": 14}  # fmt: skip
    r0 = route(0, 10, "success", None, start_fix=start, legs=1,
               events=[{"relocalise": fix_ok, "why": "no_move", "t": int(31 * S)},
                       warp_refusal])  # fmt: skip
    r1 = route(1, 50, "fail", "declined:relocalise_failed", decline="relocalise_failed", legs=3,
               legs_walked=2, leg_declined=2, waypoints=[[40, 1], [80, 1]],
               events=[{"relocalise": fix_bad, "why": "unconfirmed", "t": int(61 * S)},
                       {"relocalise": held, "why": "neighbour", "t": int(71 * S)},
                       far_refusal])  # fmt: skip
    routes = [r0, r1, route(2, 100, "success", None, legs=1),
              route(3, 150, "interrupted", "operator")]  # fmt: skip
    clicks = [click(0, 12, [1, 1], [4, 1]), click(1, 52, [1, 1], [13, 1])]
    (d / "demo.verified.jsonl").write_text("\n".join(json.dumps(x) for x in routes + clicks))
    (d / "demo.jsonl").write_text("\n".join(json.dumps(x) for x in routes + clicks))
    events = [
        {"t_mono_ns": 20 * S, "type": "act", "src_gid": GM, "kind": "normal"},
        {"t_mono_ns": 30 * S, "type": "entity_stop", "gid": GM, "x": 3, "y": 4},
        {"t_mono_ns": 60 * S, "type": "entity_stop", "gid": GM, "x": 7, "y": 7},
        {"t_mono_ns": 105 * S, "type": "map_change", "map": "prontera.gat", "x": 1, "y": 1},
        {"t_mono_ns": 900 * S, "type": "npc_contact"},  # after the window: not counted
    ]
    with gzip.open(d / "packets.jsonl.gz", "wt") as fh:
        fh.write("\n".join(json.dumps(e) for e in events))
    guard = tmp / "chat_guard.jsonl"
    rows = [
        {"t_wall": wall(-3600), "event": "exempted", "id": "3.29a", "line": "/where"},
        {"t_wall": wall(0), "event": "run_start", "run": SID, "where_budget": 56},
        {"t_wall": wall(11), "event": "where", "run": SID, "n": 1, "budget": 56,
         "reason": "walk@17 route_start_indoor"},
        {"t_wall": wall(61), "event": "where", "run": SID, "n": 2, "budget": 56,
         "reason": "walk@17 belief_in_doubt"},
        {"t_wall": wall(90), "event": "refused", "rule": "repeat", "line": "/where",
         "reason": "walk@17 belief_in_doubt"},
        {"t_wall": wall(95), "event": "refused", "rule": "repeat", "line": "@killmonster2"},
        {"t_wall": wall(300), "event": "where", "run": "default", "n": 1, "budget": 12,
         "reason": "where_fix.fix"},
        {"t_wall": wall(4000), "event": "where", "run": "default", "reason": "later"},
    ]  # fmt: skip
    guard.write_text("\n".join(json.dumps(x) for x in rows))
    return d, guard


def test_the_counts_and_walk17s_own_counters(tmp_path: Path) -> None:
    d, guard = session(tmp_path)
    first, inherited, own = sc.score(d, guard, run_verify=False)
    assert first["rule"] == "walk@17" and first["routes"] == 4 and first["interrupted"] == 1
    assert first["scored"] == {"success": 2, "fail": 1}
    assert first["fail_causes"] == {"declined:relocalise_failed": 1}
    assert first["SAFETY"] == {"GM_act:normal": 1}  # the late npc_contact is outside the window
    assert first["relocalisations"] == {"no_move:minimap:correct": 1, "unconfirmed:where:WRONG": 1,
                                        "neighbour:where:undecided": 1,
                                        "route_start:where:no_truth": 1}  # fmt: skip
    assert inherited["declines"] == {"relocalise_failed": 1}
    a = own["walk17_A_typing"]
    assert a["where_typed"] == 2 and a["where_budget"] == 56 and a["manifest_where_budget"] == 56
    assert a["where_reasons"] == {"walk@17 route_start_indoor": 1, "walk@17 belief_in_doubt": 1}
    assert a["where_other_runs_in_window"] == 1  # the "default" run's, inside the window only
    assert a["where_refused_by_rule"] == {"repeat": 1}
    assert a["guard_refusals_in_window"] == {"repeat:/where": 1, "repeat:@killmonster2": 1}
    assert a["exemptions_in_window (must be 0)"] == 0  # the 3.29a one was an hour before
    assert own["walk17_A_relocalisations_by_method"] == {"minimap:fix": 1, "where:fix": 2,
                                                         "where:held:where_retry": 1}  # fmt: skip
    b = own["walk17_B_warp_areas"]
    assert b["click_refusals_in_warp_area"] == 1 and b["walk_routes_warped_mid_route"] == 1
    assert b["warped"] == [{"route": "route 2 from believed 1,1", "maps": ["prontera"]}]
    c = own["walk17_C_legs"]
    assert c["routes_multi_leg"] == 1 and c["legs_planned"] == 5 and c["legs_walked"] == 4
    assert c["waypoints"] == 2 and c["declined_in_leg_2"] == 1
    assert c["click_refusals_beyond_click_max"] == 1 and c["farthest_click_cells"] == 12


def test_walk_readiness_reads_the_first_object(tmp_path: Path, capsys: Any) -> None:
    d, guard = session(tmp_path)
    sys.argv = ["walk17_score.py", str(d), "--guard-log", str(guard), "--no-verify"]
    assert sc.main() == 0
    row = wr.run_row("indoor clean", wr.first_object(capsys.readouterr().out))
    assert row["success"] == 2 and row["n"] == 3 and row["unsafe"] == 1
