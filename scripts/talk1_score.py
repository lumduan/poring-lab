#!/usr/bin/env python3
"""Score a talk@1 session OFFLINE (docs/demonstrations.md 3.30): the packets judge what the rule
did from pixels. Never fed back into a run (ADR-0007). Committed before any talk@1 trial.

    talk1_score.py SESSION_DIR

SESSION_DIR holds the harness's trials.json and the session's packets.jsonl.gz. A trial record:
    {"k", "scene", "npc" (the L3 name), "npc_cell" [x, y], "l3_options" [...],
     "intended" [first option text, end option text], "t_start", "t_contact_click" (or None),
     "t_end", "runtime": {"closed": bool}}

Per trial, in order (the first failing check names the cause):
1. the TARGET: the NPC entity standing on the L3 cell when the contact click was made (matched by
   position on the server; never by name);
2. CONTACT: our npc_contact on that gid within CONTACT_S of the click;
3. MENU: its first npc_menu equals the L3 option list (else "menu differs from L3": the static data
   is wrong);
4. CHOICES: our first npc_choose on the target picks the intended option's 1-based position in that
   menu, and a later one picks the end option's position in ITS menu;
5. CLOSE: the server's npc_close, then OUR npc_close_click, after the last choice; no npc_say /
   npc_menu from the target after that click;
6. the runtime check (pixels) agrees (the windows gone), and the close click came within BUDGET_S
   of the contact click.
SAFETY over the whole trial: an npc_contact on any other gid, a second contact on the target after
its close click, any attack_request, any GM act of kind normal or pickup.
The bar (3.30): >= 48 / 50 per scene AND zero safety events.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/poring_dataset/src"))
import walk_readiness  # noqa: E402

GM_AID = 2000002
S = 1_000_000_000
CONTACT_S = 5.0
BUDGET_S = 120.0
BAR = (48, 50)


def target_gid(timeline: Any, cell: list[int], t_ns: int) -> int | None:
    """The NPC on ``cell`` at ``t_ns`` (the server's world state), None if none or several."""
    from poring_dataset.labels import OBJTYPE_CLASS

    fw = timeline.frame_world(t_ns)
    on = [e for e in fw.entities if OBJTYPE_CLASS.get(e.objtype) == "npc"
          and (round(e.x), round(e.y)) == (cell[0], cell[1])]  # fmt: skip
    return int(on[0].gid) if len(on) == 1 else None


def _of(events: list[dict[str, Any]], etype: str, t0: int, t1: int) -> list[dict[str, Any]]:
    return [e for e in events if e.get("type") == etype and t0 <= int(e["t_mono_ns"]) <= t1]


def safety(events: list[dict[str, Any]], tr: dict[str, Any], gid: int | None,
           t_close: int | None) -> dict[str, int]:  # fmt: skip
    out = Counter()
    t0, t1 = int(tr["t_start"]), int(tr["t_end"])
    for e in _of(events, "npc_contact", t0, t1):
        if gid is None or int(e["npc_gid"]) != gid:
            out["npc_contact_other"] += 1
        elif t_close is not None and int(e["t_mono_ns"]) > t_close:
            out["npc_contact_again"] += 1
    out["attack_request"] += len(_of(events, "attack_request", t0, t1))
    acts = _of(events, "act", t0, t1)
    out["act_normal_or_pickup"] += sum(
        1
        for e in acts
        if int(e.get("src_gid", -1)) == GM_AID and e.get("kind") in ("normal", "pickup")
    )
    return {k: v for k, v in out.items() if v}


def judge_trial(events: list[dict[str, Any]], tr: dict[str, Any], timeline: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"k": tr["k"], "scene": tr["scene"], "npc": tr["npc"]}
    click = tr.get("t_contact_click")
    gid = target_gid(timeline, tr["npc_cell"], int(click)) if click is not None else None
    t_end = int(tr["t_end"])
    close_ns: int | None = None

    def done(result: str) -> dict[str, Any]:
        row["result"] = result
        row["safety"] = safety(events, tr, gid, close_ns)
        return row

    if click is None:
        return done("fail: no contact click (approach / contact)")
    click = int(click)
    if gid is None:
        return done("fail: no single NPC on the L3 cell at the click")
    mine = [
        e
        for e in events
        if int(e.get("npc_gid", -1)) == gid and click <= int(e["t_mono_ns"]) <= t_end
    ]
    contact = [e for e in mine if e["type"] == "npc_contact"
               and int(e["t_mono_ns"]) - click <= CONTACT_S * S]  # fmt: skip
    if not contact:
        return done("fail: no contact on the target")
    menus = [e for e in mine if e["type"] == "npc_menu"]
    chooses = [e for e in mine if e["type"] == "npc_choose"]
    if not menus:
        return done("fail: no menu")
    if list(menus[0]["options"]) != list(tr["l3_options"]):
        row["menu"] = menus[0]["options"]
        return done("fail: menu differs from L3")
    first, end_text = tr["intended"]
    want1 = menus[0]["options"].index(first) + 1
    if not chooses or int(chooses[0]["choice"]) != want1:
        row["choices"] = [int(c["choice"]) for c in chooses]
        return done(f"fail: wrong first choice (wanted {want1})")
    later = [c for c in chooses[1:]]
    end_ok = False
    for c in later:
        before = [m for m in menus if int(m["t_mono_ns"]) <= int(c["t_mono_ns"])]
        if before and end_text in before[-1]["options"] \
                and int(c["choice"]) == before[-1]["options"].index(end_text) + 1:  # fmt: skip
            end_ok = True
            break
    if not end_ok:
        row["choices"] = [int(c["choice"]) for c in chooses]
        return done("fail: the end option was not chosen")
    last_choice = int(chooses[-1]["t_mono_ns"])
    closes = [e for e in mine if e["type"] == "npc_close" and int(e["t_mono_ns"]) >= last_choice]
    clicks = [e for e in mine if e["type"] == "npc_close_click"
              and closes and int(e["t_mono_ns"]) >= int(closes[0]["t_mono_ns"])]  # fmt: skip
    if not clicks:
        return done("fail: no clean close (server close + our close click)")
    close_ns = int(clicks[0]["t_mono_ns"])
    after = [
        e for e in mine if e["type"] in ("npc_say", "npc_menu") and int(e["t_mono_ns"]) > close_ns
    ]
    if after:
        return done("fail: the dialog went on after our close")
    row["contact_to_close_s"] = round((close_ns - click) / S, 2)
    if not (tr.get("runtime") or {}).get("closed"):
        return done("fail: the runtime check did not see the windows gone")
    if (close_ns - click) / S > BUDGET_S:
        return done("fail: too slow")
    return done("success")


def judge(trials: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    from poring_dataset.timeline import Timeline

    tl = Timeline(events)
    rows = [judge_trial(events, tr, tl) for tr in trials]
    out: dict[str, Any] = {"scenes": {}}
    for scene in sorted({r["scene"] for r in rows}):
        rs = [r for r in rows if r["scene"] == scene]
        ok = sum(1 for r in rs if r["result"] == "success")
        unsafe = sum(sum(r["safety"].values()) for r in rs)
        lo, hi = walk_readiness.wilson(ok, len(rs))
        verdict = ("INCOMPLETE: fewer than 50 trials" if len(rs) < BAR[1]
                   else "PASS" if ok >= BAR[0] and unsafe == 0 else "FAIL")  # fmt: skip
        times = sorted(r["contact_to_close_s"] for r in rs if "contact_to_close_s" in r)
        out["scenes"][scene] = {
            "trials": len(rs), "success": ok, "ci95": [round(lo, 4), round(hi, 4)],
            "unsafe": unsafe, "verdict": verdict,
            "causes": dict(Counter(r["result"] for r in rs if r["result"] != "success")),
            "contact_to_close_s": ({"median": times[len(times) // 2],
                                    "p95": times[int(0.95 * (len(times) - 1))]}
                                   if times else None),
        }  # fmt: skip
    out["rows"] = rows
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path)
    a = ap.parse_args()
    trials = json.loads((a.session / "trials.json").read_text())
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as f:
        events = sorted((json.loads(line) for line in f if line.strip()),
                        key=lambda e: int(e["t_mono_ns"]))  # fmt: skip
    out = judge(trials, events)
    rows = out.pop("rows")
    print(json.dumps({"session": a.session.name, **out}, indent=1))
    for r in rows:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
