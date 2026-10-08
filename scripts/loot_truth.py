#!/usr/bin/env python3
"""loot@1's OFFLINE truth from packet events (ADR-0007: it judges, it never feeds a rule): which
monsters died where, what fell where, and what WE picked up -- from a replay's events.jsonl
(guarded_build.py replay:, the 2026-10-08 floor-item decoders) or a session's packets.jsonl.gz.

    loot_truth.py EVENTS.jsonl[.gz] [--from-ns T0 --to-ns T1 | --manifest SESSION/manifest.json]
                  [--aid 2000002] [--json]

* deaths: every entity_vanish with reason "died": the unit, the time, and its cell then
  (poring_dataset.timeline: where it fell -- the P3 truth);
* floor items: every floor_item_appear (kind "fall" = a fresh drop, "in_sight" = one already
  there), its fate (vanished, and who acted "pickup" on it) and, for a fall within
  DROP_WINDOW_S of a death and DROP_RADIUS cells of its cell, that death and the offset;
* OUR pickups: our act of kind pickup on a floor id, then our pickup_result ok for the same item
  within RESULT_WINDOW_S, then the floor item's vanish: "confirmed" only when all three hold.

Since the 2026-10-08 17:51 sniffer rebuild the LIVE sniffer carries these decoders: a session's own
packets.jsonl.gz works (P2 proven live, 20261008T210930-demo-safety-check-pickup); pass --aid.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

DROP_WINDOW_S = 1.5  # a kill's drops fall at once (delay_battle_damage yes) or 0.5 s after
DROP_RADIUS = 2  # cells: the drop pattern's neighbours, plus a free-cell search of 1
RESULT_WINDOW_S = 2.0
S = 1_000_000_000


def read_events(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt") if path.suffix == ".gz" else path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def self_aid(events: Iterable[Mapping[str, Any]]) -> int | None:
    """Our block id: login_accepted's aid, else the inferred one (poring_dataset.timeline)."""
    evs = list(events)
    for e in evs:
        if e.get("type") == "login_accepted":
            return int(e["aid"])
    from poring_dataset.timeline import infer_self_aid

    return infer_self_aid(evs)


def death_cells(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every "died" vanish with the unit's cell at that moment (the Timeline's position: walks
    interpolated). The cell is None when the unit was never placed."""
    from poring_dataset.timeline import Timeline

    tl = Timeline(events)
    out = []
    for e in events:
        if e.get("type") != "entity_vanish" or int(e.get("reason", -1)) != 1:
            continue
        t = int(e["t_mono_ns"])
        st = tl.state(int(e["gid"]), t)
        cell = None if st is None else (int(round(st.x)), int(round(st.y)))
        out.append({"gid": int(e["gid"]), "t_ns": t, "cell": cell,
                    "job": None if st is None else st.job})  # fmt: skip
    return out


def ledger(events: list[dict[str, Any]], aid: int | None) -> dict[str, Any]:
    events = sorted(events, key=lambda e: int(e["t_mono_ns"]))
    deaths = death_cells(events)
    items: dict[int, dict[str, Any]] = {}
    results = [e for e in events if e.get("type") == "pickup_result"]
    for e in events:
        t, etype = int(e["t_mono_ns"]), e.get("type")
        if etype == "floor_item_appear":
            fid = int(e["floor_id"])
            if fid in items:
                continue  # seen again (back in sight): keep the first entry
            row: dict[str, Any] = {
                "floor_id": fid, "t_ns": t, "kind": e["kind"], "item_id": int(e["item_id"]),
                "amount": int(e["amount"]), "cell": (int(e["x"]), int(e["y"])),
                "death": None, "offset": None, "vanished_ns": None, "picked_by": None,
                "our_request_ns": None, "our_result": None, "confirmed": False,
            }  # fmt: skip
            if e["kind"] == "fall":
                near = [d for d in deaths if d["cell"] is not None
                        and 0 <= t - d["t_ns"] <= DROP_WINDOW_S * S
                        and max(abs(d["cell"][0] - row["cell"][0]),
                                abs(d["cell"][1] - row["cell"][1])) <= DROP_RADIUS]  # fmt: skip
                if near:
                    d = near[-1]
                    row["death"] = d["gid"]
                    row["offset"] = (row["cell"][0] - d["cell"][0], row["cell"][1] - d["cell"][1])
            items[fid] = row
        elif etype == "floor_item_vanish" and int(e["floor_id"]) in items:
            items[int(e["floor_id"])]["vanished_ns"] = t
        elif etype == "pickup_request" and int(e["floor_id"]) in items:
            items[int(e["floor_id"])]["our_request_ns"] = t
        elif etype == "act" and e.get("kind") == "pickup" and int(e["target_gid"]) in items:
            row = items[int(e["target_gid"])]
            row["picked_by"] = int(e["src_gid"])
            row["picked_ns"] = t
            if aid is not None and int(e["src_gid"]) == aid:
                ok = [r for r in results if r.get("ok") and int(r["item_id"]) == row["item_id"]
                      and 0 <= int(r["t_mono_ns"]) - t <= RESULT_WINDOW_S * S]  # fmt: skip
                if ok:
                    row["our_result"] = {"t_ns": int(ok[0]["t_mono_ns"]),
                                         "amount": int(ok[0]["amount"])}  # fmt: skip
    for row in items.values():
        ours = aid is not None and row["picked_by"] == aid and row["our_result"] is not None
        gone = row["vanished_ns"] is not None and row["vanished_ns"] >= row.get("picked_ns", 0)
        row["confirmed"] = bool(ours and gone)
    falls = [r for r in items.values() if r["kind"] == "fall"]
    return {
        "aid": aid, "deaths": deaths, "floor_items": list(items.values()),
        "summary": {
            "deaths": len(deaths), "falls": len(falls),
            "falls_from_a_death": sum(1 for r in falls if r["death"] is not None),
            "offsets": sorted({str(r["offset"]) for r in falls if r["offset"] is not None}),
            "our_pickups_confirmed": sum(1 for r in items.values() if r["confirmed"]),
            "our_pickup_acts": sum(1 for r in items.values() if r["picked_by"] == aid),
            "our_pickup_requests": sum(1 for e in events if e.get("type") == "pickup_request"),
            "pickup_results_ok": sum(1 for r in results if r.get("ok")),
            "pickup_results_failed": sum(1 for r in results if not r.get("ok")),
        },
    }  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("events", type=Path)
    ap.add_argument("--from-ns", type=int)
    ap.add_argument("--to-ns", type=int)
    ap.add_argument("--manifest", type=Path, help="a demo session's manifest: its t0/t1 window")
    ap.add_argument("--aid", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    events = read_events(a.events)
    t0, t1 = a.from_ns, a.to_ns
    if a.manifest:
        m = json.loads(a.manifest.read_text())
        t0, t1 = int(m["t0_mono_ns"]), int(m["t1_mono_ns"])
    aid = a.aid if a.aid is not None else self_aid(events)
    out = ledger(events, aid)  # the whole file: positions need the history before t0
    if t0 is not None or t1 is not None:
        lo, hi = t0 or 0, t1 or 2**63

        def keep(r: Mapping[str, Any]) -> bool:
            return lo <= int(r["t_ns"]) <= hi

        out["deaths"] = [d for d in out["deaths"] if keep(d)]
        out["floor_items"] = [r for r in out["floor_items"] if keep(r)]
        out["window_ns"] = [lo, hi]
    if a.json:
        print(json.dumps(out, indent=1))
        return 0
    print(f"our aid {aid}; summary (whole file) {json.dumps(out['summary'])}")
    for d in out["deaths"]:
        print(f"  died  #{d['gid']} job {d['job']} at {d['cell']}  t {d['t_ns']}")
    for r in out["floor_items"]:
        print(f"  {r['kind']:<8} #{r['floor_id']} item {r['item_id']} x{r['amount']} at "
              f"{r['cell']}  death {r['death']} offset {r['offset']}  picked by {r['picked_by']}"
              f"  our result {r['our_result']}  vanished {r['vanished_ns']}  "
              f"CONFIRMED {r['confirmed']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
