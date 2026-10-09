#!/usr/bin/env python3
"""Score a loot@1 session OFFLINE (docs/demonstrations.md 3.20 / 3.20a): the packets judge what
scripts/loot1.py did from pixels. Never fed back into a run (ADR-0007).

    loot1_score.py SESSION_DIR [--first 20]

Per trial:
* the TARGET's death: the "died" vanish (loot_truth.death_cells) of a Poring after the trial's
  first attack click and before its end, within TARGET_CELLS of the spot; none = "no server
  death"; more than one = "ambiguous" (never guessed);
* P3 (mode p3 and run): the pixel death cell vs the server's: exact / within 1 / farther;
* its DROPS: the floor items that fell from that death (loot_truth.ledger);
* a DROP TRIAL succeeds when the runtime check said obtained, the server confirms OUR pickup of
  one of those drops (our pickup act, pickup_result ok, the item's vanish) after the loot click,
  and the click came within TOO_SLOW_S of the server's death. A runtime "obtained" without a
  server pickup is a FAILURE, and so is a server pickup the runtime check missed;
* SAFETY in the loot phase (the server death to the trial's end): attack_request, npc_contact and
  our act of kind normal. The kill phase's attacks are deliberate and excluded.
The bar (3.20): >= 19 of the FIRST 20 drop trials; fewer than 20 drop trials = inconclusive.
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import loot_truth as lt  # noqa: E402

GM_AID = 2000002
PORING = 1002
TARGET_CELLS = 5  # the Poring spawns within 3 cells of the GM, who stands on the spot
S = 1_000_000_000
TOO_SLOW_S = 45.0
BAR = (19, 20)


def cheb(a: Any, b: Any) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def target_death(trial: dict[str, Any], deaths: list[dict[str, Any]]) -> dict[str, Any]:
    attacks = trial.get("attacks") or []
    if not attacks:
        return {"why": "no attack"}
    t0, t1 = int(attacks[0]), int(trial.get("t_end") or attacks[0] + 60 * S)
    near = [d for d in deaths if t0 <= d["t_ns"] <= t1 and d["cell"] is not None
            and d.get("job") in (PORING, None)
            and cheb(d["cell"], trial["spot"]) <= TARGET_CELLS]  # fmt: skip
    if not near:
        return {"why": "no server death"}
    if len(near) > 1:
        return {"why": "ambiguous", "gids": [d["gid"] for d in near]}
    return {"death": near[0]}


def judge(trials: list[dict[str, Any]], events: list[dict[str, Any]],
          weights: dict[str, int] | None = None,
          first: int = BAR[1]) -> dict[str, Any]:  # fmt: skip
    led = lt.ledger(events, GM_AID)
    deaths = led["deaths"]
    items = led["floor_items"]
    rows: list[dict[str, Any]] = []
    p3 = Counter()
    for tr in trials:
        row: dict[str, Any] = {"k": tr["k"], "kill": tr.get("kill"), "found": tr.get("found")}
        rows.append(row)
        if tr.get("kill") != "vanished":
            continue
        td = target_death(tr, deaths)
        if "death" not in td:
            row["server"] = td["why"]
            p3["no_server_target"] += 1
            continue
        d = td["death"]
        row["server_death"] = {"gid": d["gid"], "cell": list(d["cell"]), "t_ns": d["t_ns"]}
        px = (tr.get("death") or {}).get("cell")
        if px is None:
            row["p3"] = "no pixel cell: " + str((tr.get("death") or {}).get("reason")
                                                 or ("no /where fix" if not tr.get("here")
                                                     else "none"))  # fmt: skip
            p3["no_pixel_cell"] += 1
        else:
            dist = cheb(px, d["cell"])
            row["p3"] = dist
            p3["exact" if dist == 0 else "within_1" if dist == 1 else "farther"] += 1
        drops = [it for it in items if it["kind"] == "fall" and it["death"] == d["gid"]]
        row["drops"] = [{"item": it["item_id"], "cell": list(it["cell"]),
                         "offset": it["offset"], "picked_by": it["picked_by"],
                         "confirmed": it["confirmed"]} for it in drops]  # fmt: skip
        if not drops:
            continue
        row["drop_trial"] = True
        click = tr.get("pickup_click")
        rt = tr.get("runtime") or {}
        ours = [it for it in drops if it["confirmed"] and click is not None
                and it.get("picked_ns", 0) >= int(click["t"])]  # fmt: skip
        slow = click is not None and (int(click["t"]) - d["t_ns"]) / S > TOO_SLOW_S
        row["death_to_click_s"] = (None if click is None
                                   else round((int(click["t"]) - d["t_ns"]) / S, 2))  # fmt: skip
        row["runtime"] = rt
        row["server_pickup"] = bool(ours)
        if click is None:
            row["result"] = "fail: no pickup click (" + _why_no_click(tr) + ")"
        elif rt.get("obtained") and ours and not slow:
            row["result"] = "success"
        elif rt.get("obtained") and not ours:
            row["result"] = "fail: runtime obtained, no server pickup (false positive)"
        elif ours and not rt.get("obtained"):
            row["result"] = "fail: server pickup the runtime check missed"
        elif slow:
            row["result"] = "fail: too slow"
        else:
            row["result"] = "fail: clicked, nothing picked up"
        if weights is not None and ours:
            w = weights.get(str(ours[0]["item_id"]))
            row["item_weight"] = w
            row["sub_resolution"] = w is not None and w < 10
        row["left_behind"] = sum(1 for it in drops if it["picked_by"] != GM_AID)
        row["safety"] = safety(events, d["t_ns"], int(tr.get("t_end") or d["t_ns"]))
    drop_rows = [x for x in rows if x.get("drop_trial")]
    scored = drop_rows[:first]
    ok = sum(1 for x in scored if x["result"] == "success")
    unsafe = sum(sum(x["safety"].values()) for x in scored)
    clicks = [x["death_to_click_s"] for x in scored if x.get("death_to_click_s") is not None]
    sig = Counter()
    for x in scored:
        if x.get("server_pickup"):
            rt = x["runtime"]
            sig["confirmed"] += 1
            sig["weight_rose"] += bool(rt.get("weight_rose"))
            sig["cue"] += bool(rt.get("cue"))
            sig["either"] += bool(rt.get("obtained"))
    if len(scored) < first:
        verdict = f"INCONCLUSIVE: {len(scored)} drop trials < {first}"
    else:
        verdict = "PASS" if ok >= BAR[0] and unsafe == 0 else "FAIL"
    return {
        "trials": len(trials), "kills_vanished": sum(1 for x in rows if x["kill"] == "vanished"),
        "kill_outcomes": dict(Counter(str(x["kill"]) for x in rows)),
        "p3": dict(p3), "drop_trials": len(drop_rows), "scored": len(scored), "success": ok,
        "unsafe": unsafe, "verdict": verdict,
        "results": dict(Counter(x["result"] for x in scored)),
        "signals_on_confirmed": dict(sig),
        "death_to_click_s": ({"median": round(statistics.median(clicks), 2),
                              "p95": round(sorted(clicks)[int(0.95 * (len(clicks) - 1))], 2)}
                             if clicks else None),  # fmt: skip
        "rows": rows,
    }  # fmt: skip


def _why_no_click(tr: dict[str, Any]) -> str:
    scan = tr.get("scan") or []
    shapes = Counter(str(s.get("shape") or s.get("skip")) for s in scan)
    refused = sum(1 for s in scan if s.get("refused"))
    return f"{len(scan)} cells, shapes {dict(shapes)}, unit refusals {refused}"


def safety(events: list[dict[str, Any]], t0: int, t1: int) -> dict[str, int]:
    out = Counter()
    for e in events:
        t = int(e["t_mono_ns"])
        if not t0 <= t <= t1:
            continue
        if e.get("type") in ("attack_request", "npc_contact"):
            out[e["type"]] += 1
        elif (e.get("type") == "act" and int(e.get("src_gid", -1)) == GM_AID
              and e.get("kind") == "normal"):  # fmt: skip
            out["act_normal"] += 1
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path)
    ap.add_argument("--first", type=int, default=BAR[1])
    a = ap.parse_args()
    trials = json.loads((a.session / "trials.json").read_text())
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as f:
        events = [json.loads(line) for line in f if line.strip()]
    kb = Path(__file__).resolve().parents[1] / "data/kb/items.json"
    weights = ({k: int(v["weight"]) for k, v in json.loads(kb.read_text()).items()}
               if kb.exists() else None)  # fmt: skip
    out = judge(trials, events, weights, a.first)
    rows = out.pop("rows")
    print(json.dumps({"session": a.session.name, **out}, indent=1, default=str))
    for x in rows:
        print(json.dumps(x, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
