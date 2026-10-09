#!/usr/bin/env python3
"""Score one walk@17 session OFFLINE (docs/demonstrations.md 3.32): the packets judge what
scripts/walk17.py did from pixels. Never fed back into a run (ADR-0007).

    walk17_score.py SESSION_DIR [--guard-log data/ro_agent/chat_guard.jsonl] [--no-verify]

walk15_score.py's approach (3.26; the scorer every walk@13-16 result was read with), for the rule
"walk@17": demo_interruptions.py and demo_verify.py first (unless --no-verify), then the FIRST 50
route records not interrupted are scored. It prints several JSON objects in a row; the FIRST holds
the counts walk_readiness.py reads ("scored", "SAFETY": every GM act and every live request is
listed; walk_readiness counts only the defined kinds).

walk@17's own counters (the last object):
- A, TYPING: the /where lines the typing guard logged for this run (its run id is the session id),
  with their reasons; any /where in the session's window from ANOTHER run; the guard's refusals in
  the window by rule; exemptions in the window (walk@17 has none: any is a policy breach). The
  relocalisations by method (minimap / where) and outcome (vs the packets: correct / WRONG;
  refused or held: undecided), the route-start fixes included.
- B, WARP AREAS: walk clicks refused inside a warp area; walk (non-portal) routes during which the
  server changed our map (an accidental warp), with the maps.
- C, LONG WALKS: routes walked as more than one leg, the legs planned and walked, the leg that
  declined, the waypoints; clicks refused beyond CLICK_MAX_SAFE; the farthest click (Chebyshev,
  from the believed cell).
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "poring_dataset" / "src"))
from poring_dataset import verify as V  # noqa: E402

RULE = "walk@17"
GM_AID = 2000002
FIRST = 50
GUARD_LOG = ROOT / "data" / "ro_agent" / "chat_guard.jsonl"
WALL_SLACK_S = 1.0  # the guard log's wall times have one-second resolution


def jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def verify(session: Path) -> None:
    """The offline verifier, as the earlier scorers ran it (in this interpreter: no env build)."""
    for script in ("demo_interruptions.py", "demo_verify.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), str(session)], cwd=ROOT,
                       check=True, capture_output=True)  # fmt: skip


def load(session: Path) -> dict[str, Any]:
    rows = jsonl(session / "demo.verified.jsonl")
    man = json.loads((session / "manifest.json").read_text())
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(x) for x in fh if x.strip()]
    events = [e for e in events if man["t0_mono_ns"] <= e["t_mono_ns"] <= man["t1_mono_ns"]]
    routes = sorted((r for r in rows if r.get("rule") == RULE), key=lambda r: r["t_mono_ns"])
    ok = [r for r in routes if r["outcome"]["status"] != "interrupted"][:FIRST]
    segs = [r for r in rows if r.get("rule") == f"{RULE}/click"
            and r["outcome"]["status"] != "interrupted"]  # fmt: skip
    orig = {r["record_id"]: r for r in jsonl(session / "demo.jsonl")}
    return {"session": session.name, "rows": rows, "man": man, "events": events,
            "routes": routes, "ok": ok, "segs": segs, "orig": orig}  # fmt: skip


def ev(r: dict[str, Any]) -> dict[str, Any]:
    return dict(r["outcome"].get("evidence") or {})


def relocalisations(s: dict[str, Any]) -> Counter[str]:
    """Every relocalisation of the scored routes (the route-start fix too), by why, method and
    outcome against the packets: correct / WRONG for a fix (no_truth: no server position before
    it), undecided for none."""
    out: Counter[str] = Counter()
    for r in s["ok"]:
        e = ev(r)
        found = [(x.get("why"), x["relocalise"], x.get("t")) for x in e.get("events", [])
                 if "relocalise" in x]  # fmt: skip
        if e.get("start_fix"):
            found.append(("route_start", e["start_fix"], e["start_fix"].get("t")))
        for why, rl, t in found:
            method = rl.get("method", "?")
            if not rl.get("ok"):
                out[f"{why}:{method}:undecided"] += 1
                continue
            true = V.position_before(s["events"], int(t), GM_AID) if t is not None else None
            verdict = ("no_truth" if true is None
                       else "correct" if list(true) == rl.get("to") else "WRONG")  # fmt: skip
            out[f"{why}:{method}:{verdict}"] += 1
    return out


def counts(s: dict[str, Any]) -> dict[str, Any]:
    """The first object: walk15_score.py's counts, for the rule walk@17."""
    ok, segs, events = s["ok"], s["segs"], s["events"]
    safety = Counter("GM_act:" + str(e.get("kind")) for e in events
                     if e["type"] == "act" and int(e.get("src_gid", -1)) == GM_AID)  # fmt: skip
    safety.update("request(live):" + e["type"] for e in events
                  if e["type"] in ("attack_request", "npc_contact"))  # fmt: skip
    tiers: Counter[str] = Counter()
    for sg in segs:
        o = ev(s["orig"].get(sg["record_id"], sg))
        tg = [t for t in o.get("target", []) if isinstance(t, dict)]
        named = any(t.get("cell") == [0, 0] for t in tg)
        tier = tg[-1].get("tier") if tg else None
        tiers[f"{tier}:{'named' if named else 'unnamed'}:{sg['outcome']['status']}"] += 1
    waits = [ev(r).get("waited_s", 0) or 0 for r in ok]
    return {
        "session": s["session"], "rule": RULE, "clicks_by_tier": dict(tiers),
        "routes": len(s["routes"]),
        "interrupted": sum(1 for r in s["routes"] if r["outcome"]["status"] == "interrupted"),
        "scored": dict(Counter(r["outcome"]["status"] for r in ok)),
        "fail_causes": dict(Counter(r["outcome"]["cause"] for r in ok
                                    if r["outcome"]["status"] == "fail")),
        "SAFETY": dict(safety),
        "segments": dict(Counter(x["outcome"]["status"] for x in segs)),
        "seg_fail": dict(Counter(x["outcome"]["cause"] for x in segs
                                 if x["outcome"]["status"] != "success")),
        "substitutes": dict(Counter(r["outcome"]["cause"] for r in ok if ev(r).get("substitute"))),
        "waited_s_total": round(sum(waits), 1), "routes_that_waited": sum(1 for x in waits if x),
        "relocalisations": dict(relocalisations(s)),
    }  # fmt: skip


def _walk(o: Any, acc: Counter[str]) -> None:
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("ui_refused", "talk_refused") and v:
                acc[k] += len(v) if isinstance(v, list) else 1
            if k == "outcome" and v in ("covered_talk_cell", "no_safe_point"):
                acc[v] += 1
            _walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            _walk(v, acc)


def inherited(s: dict[str, Any]) -> dict[str, Any]:
    """walk@12-14's decisions, as walk15_score.py reports them."""
    acc: Counter[str] = Counter()
    _walk(list(s["orig"].values()), acc)
    per: Counter[str] = Counter()
    w14: Counter[str] = Counter()
    blocked = {"route": 0, "unit": 0}
    for r in s["ok"]:
        e = ev(r)
        per["routes_with_replans"] += 1 if e.get("replans") else 0
        per["replans"] += int(e.get("replans") or 0)
        per["npc_substitute_routes"] += 1 if e.get("npc_substitute") else 0
        if e.get("sides"):
            w14["routes_with_sides"] += 1
            w14["routes_with_sides_success"] += r["outcome"]["status"] == "success"
        for x in e.get("events", []):
            if "replan" in x:
                blocked["route"] += len(x["blocked"]["route"])
                blocked["unit"] += len(x["blocked"]["unit"])
            per["replan_none"] += "replan_none" in x
            none_found = "npc_substitute" in x and x["npc_substitute"] is None
            per["npc_substitute_none_found"] += none_found
            if "taken_check" in x:
                per["taken_checks"] += 1
                per["taken_on_it" if x["on_it"] else "taken_nobody_on_it"] += 1
            per["steps_with_signs"] += bool(x.get("signs"))
            if "side" in x:
                w14["side_tried" if x["side"] else "side_none_found"] += 1
            w14["side_reached"] += "side_reached" in x
    ok = s["ok"]
    success = [r for r in ok if r["outcome"]["status"] == "success"]
    return {
        "walk12_decisions_inherited": dict(acc),
        "manifest_end": {k: s["man"].get(k) for k in ("ended", "reason", "exit_code")},
        "walk13_changes": {k: v for k, v in per.items() if v},
        "cells_blocked_by_replans": blocked,
        "success_causes (substitutes reported apart)": dict(Counter(
            r["outcome"]["cause"] for r in success if r["outcome"]["cause"])),
        "STRICT success (no substitute of either kind)": sum(
            1 for r in success if not ev(r).get("substitute") and not ev(r).get("npc_substitute")),
        "declines": dict(Counter(ev(r)["decline"] for r in ok if ev(r).get("decline"))),
        "walk14_changes": {k: v for k, v in w14.items() if v},
    }  # fmt: skip


def wall(row: dict[str, Any]) -> float | None:
    try:
        return dt.datetime.strptime(str(row["t_wall"]), "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except (KeyError, ValueError):
        return None


def typing(s: dict[str, Any], guard_log: Path) -> dict[str, Any]:
    """A: the typing guard's log for this run (its id = the session id) and the session's window."""
    man, sid = s["man"], s["session"]
    rows = jsonl(guard_log) if guard_log.exists() else []
    lo = float(man.get("t0_wall", 0)) - WALL_SLACK_S
    hi = float(man.get("t1_wall", float("inf"))) + WALL_SLACK_S
    window = [x for x in rows if (t := wall(x)) is not None and lo <= t <= hi]
    ours = [x for x in rows if x.get("event") == "where" and x.get("run") == sid]
    others = [x for x in window if x.get("event") == "where" and x.get("run") != sid]
    refused = [x for x in window if x.get("event") == "refused"]
    start = next((x for x in rows if x.get("event") == "run_start" and x.get("run") == sid), None)
    return {
        "where_budget": None if start is None else start.get("where_budget"),
        "where_typed": len(ours),
        "where_reasons": dict(Counter(str(x.get("reason")) for x in ours)),
        "where_other_runs_in_window": len(others),
        "guard_refusals_in_window": dict(Counter(
            f"{x.get('rule')}:{x.get('line')}" for x in refused)),
        "where_refused_by_rule": dict(Counter(
            str(x.get("rule")) for x in refused if x.get("line") == "/where")),
        "exemptions_in_window (must be 0)": sum(1 for x in window
                                                if x.get("event") == "exempted"),
        "manifest_where_budget": man.get("where_budget"),
    }  # fmt: skip


def relocalise_methods(s: dict[str, Any]) -> dict[str, Any]:
    """A: every relocalisation (the route-start fixes too) by method and its first reject."""
    by: Counter[str] = Counter()
    for r in s["ok"]:
        e = ev(r)
        rls = [x["relocalise"] for x in e.get("events", []) if "relocalise" in x]
        rls += [e["start_fix"]] if e.get("start_fix") else []
        for rl in rls:
            how = "fix" if rl.get("ok") else ((rl.get("rejects") or ["none"])[0])
            by[f"{rl.get('method', '?')}:{how}"] += 1
    return dict(by)


def warps(s: dict[str, Any]) -> dict[str, Any]:
    """B: click-step refusals inside a warp area; walk routes during which our map changed."""
    refusals = 0
    mid: list[dict[str, Any]] = []
    for r in s["ok"]:
        e = ev(r)
        refusals += sum(1 for x in e.get("events", []) if x.get("warp_area"))
        if e.get("to_map") is not None:
            continue  # a portal route: the map change is its goal
        t0, t1 = int(r["t_mono_ns"]), int(r.get("t_done_ns") or r["t_mono_ns"])
        maps = [str(x.get("map", "")).removesuffix(".gat") for x in s["events"]
                if x.get("type") == "map_change" and t0 <= int(x["t_mono_ns"]) <= t1]  # fmt: skip
        if maps:
            mid.append({"route": r["action"]["intended"].get("note"), "maps": maps})
    return {"click_refusals_in_warp_area": refusals, "walk_routes_warped_mid_route": len(mid),
            "warped": mid, "warp_map": s["man"].get("warp_map"),
            "warp_areas": len(s["man"].get("warp_areas") or [])}  # fmt: skip


def legs(s: dict[str, Any]) -> dict[str, Any]:
    """C: legs and waypoints; clicks refused beyond CLICK_MAX_SAFE; the farthest click."""
    out: Counter[str] = Counter()
    for r in s["ok"]:
        e = ev(r)
        n = int(e.get("legs") or 1)
        out["routes_multi_leg"] += n > 1
        out["legs_planned"] += n
        out["legs_walked"] += int(e.get("legs_walked") or (1 if n == 1 else 0))
        out["waypoints"] += len(e.get("waypoints") or [])
        out["routes_no_waypoint"] += e.get("decline") == "no_waypoint"
        if e.get("leg_declined"):
            out[f"declined_in_leg_{e['leg_declined']}"] += 1
        beyond = [x for x in e.get("events", []) if x.get("beyond_click_max")]
        out["click_refusals_beyond_click_max"] += len(beyond)
    far = 0
    for sg in s["segs"]:
        o = ev(s["orig"].get(sg["record_id"], sg))
        frm, cell = o.get("believed_position"), sg["action"]["intended"].get("cell")
        if frm and cell:
            far = max(far, max(abs(cell[0] - frm[0]), abs(cell[1] - frm[1])))
    return {**{k: v for k, v in out.items() if v}, "farthest_click_cells": far,
            "click_max_safe": s["man"].get("click_max_safe")}  # fmt: skip


def score(session: Path, guard_log: Path = GUARD_LOG, *, run_verify: bool = True
          ) -> list[dict[str, Any]]:  # fmt: skip
    if run_verify:
        verify(session)
    s = load(session)
    return [counts(s), inherited(s),
            {"walk17_A_typing": typing(s, guard_log),
             "walk17_A_relocalisations_by_method": relocalise_methods(s),
             "walk17_B_warp_areas": warps(s), "walk17_C_legs": legs(s)}]  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path)
    ap.add_argument("--guard-log", type=Path, default=GUARD_LOG)
    ap.add_argument("--no-verify", action="store_true", help="demo.verified.jsonl is current")
    a = ap.parse_args()
    for obj in score(a.session, a.guard_log, run_verify=not a.no_verify):
        print(json.dumps(obj, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
