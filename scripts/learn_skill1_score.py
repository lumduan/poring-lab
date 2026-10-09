#!/usr/bin/env python3
"""Score a learn_skill@1 session OFFLINE (docs/demonstrations.md 3.34): the packets judge what
scripts/learn_skill1.py did from pixels. Never fed back into a run (ADR-0007).

    learn_skill1_score.py SESSION_DIR
    learn_skill1_score.py --packets FILE [FILE ...] --n N [--t0 NS] [--t1 NS] [--start-points 9]
        one trial over the packet files (default: all of it; a positive case, e.g. 3.34's banked
        looks: the start points come from the events before --t0 unless given)

Per trial, inside the RULE's window (trials.json: t_rule_start .. t_rule_end; the harness's GM
lines and restores fall outside it):
* skill_up_request (CZ_UPGRADE_SKILLLEVEL 0x0112) for Basic Skill (skill 1): exactly N, and none
  for any other skill;
* the LAST skill_update (ZC_SKILLINFO_UPDATE 0x010E) for skill 1: level N; no skill_update for any
  other skill;
* the LAST stat_change skill_point at or after the first request: START - N;
* SAFETY: no attack_request and no npc_contact;
* the start: the last stat_change skill_point BEFORE the window must be START (9, after the
  harness's @joblevelup 9); anything else makes the trial INVALID (a harness problem, not the
  rule's), and so does a harness stop before the rule ran.
The rule's own runtime claim (its points read START - N after OK, no decline) is compared with the
server: "success" needs both; a runtime claim the server contradicts is a false positive.
Requests OUTSIDE the rule's window but inside the trial are counted (the harness must send none).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SKILL_ID = 1  # Basic Skill: the server's id in the decoded skill packets
START = 9  # the points the harness gives (@joblevelup 9 from Job Lv 1)


def _t(e: dict[str, Any]) -> int:
    return int(e["t_mono_ns"])


def _of(events: Sequence[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return sorted((e for e in events if e.get("type") == kind), key=_t)


def _skill_points(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in _of(events, "stat_change") if e.get("name") == "skill_point"]


def judge_trial(events: Sequence[dict[str, Any]], n: int, t0: int, t1: int, *,
                start_points: int | None = None, runtime: dict[str, Any] | None = None,
                decline: str | None = None, t_trial: tuple[int, int] | None = None,
                start: int = START) -> dict[str, Any]:  # fmt: skip
    """One trial's verdict from the packets of the rule's window [t0, t1]."""
    win = [e for e in events if t0 <= _t(e) <= t1]
    reqs = _of(win, "skill_up_request")
    req1 = [e for e in reqs if int(e.get("skill_id", -1)) == SKILL_ID]
    req_other = sorted({int(e.get("skill_id", -1)) for e in reqs} - {SKILL_ID})
    ups = _of(win, "skill_update")
    up1 = [e for e in ups if int(e.get("skill_id", -1)) == SKILL_ID]
    up_other = sorted({int(e.get("skill_id", -1)) for e in ups} - {SKILL_ID})
    sp = _skill_points(events)
    if start_points is None:
        before = [e for e in sp if _t(e) < t0]
        start_points = int(before[-1]["value"]) if before else None
    first = _t(req1[0]) if req1 else None
    after = [e for e in sp if first is not None and first <= _t(e) <= t1]
    last_sp = int(after[-1]["value"]) if after else None
    lists = _of(win, "skill_list")
    last_list = lists[-1].get("skills") if lists else None
    list_level = None
    list_others: list[int] = []
    if isinstance(last_list, list):
        lv = [int(s.get("level", 0)) for s in last_list if int(s.get("skill_id", -1)) == SKILL_ID]
        list_level = lv[0] if lv else 0
        list_others = sorted(int(s["skill_id"]) for s in last_list
                             if int(s.get("skill_id", -1)) != SKILL_ID
                             and int(s.get("level", 0)) > 0)  # fmt: skip
    unsafe = Counter(str(e["type"]) for e in win
                     if e.get("type") in ("attack_request", "npc_contact"))  # fmt: skip
    outside = 0
    if t_trial is not None:
        outside = sum(1 for e in _of(events, "skill_up_request")
                      if t_trial[0] <= _t(e) <= t_trial[1] and not t0 <= _t(e) <= t1)  # fmt: skip
    row: dict[str, Any] = {
        "n": n, "requests": len(req1), "requests_other_skills": req_other,
        "update_level": int(up1[-1]["level"]) if up1 else None, "updates_other_skills": up_other,
        "start_points": start_points, "points_after": last_sp, "list_level": list_level,
        "list_other_skills": list_others, "unsafe": dict(unsafe),
        "requests_outside_rule": outside,
    }  # fmt: skip
    causes: list[str] = []
    if len(req1) != n:
        causes.append(f"requests {len(req1)} != {n}")
    if req_other:
        causes.append(f"requests for other skills {req_other}")
    if row["update_level"] != n:
        causes.append(f"skill_update level {row['update_level']} != {n}")
    if up_other:
        causes.append(f"skill_update for other skills {up_other}")
    if last_sp != start - n:
        causes.append(f"skill_point {last_sp} != {start - n}")
    if unsafe:
        causes.append(f"unsafe {dict(unsafe)}")
    if outside:
        causes.append(f"{outside} request(s) outside the rule's window")
    server_ok = not causes
    row["server"] = "ok" if server_ok else "; ".join(causes)
    if start_points != start:
        row["result"] = f"invalid: start points {start_points} (want {start})"
        return row
    if runtime is None and decline is None:  # a positive case: no runtime claim to compare
        row["result"] = "server_ok" if server_ok else "server_fail: " + row["server"]
        return row
    claimed = decline is None and (runtime or {}).get("points_after") == start - n
    row["runtime_claim"] = "applied" if claimed else f"declined: {decline}"
    if claimed and server_ok:
        row["result"] = "success"
    elif claimed:
        row["result"] = "fail: runtime claimed applied, the server disagrees (false positive)"
    elif server_ok:
        row["result"] = "fail: applied on the server, the runtime check missed it"
    else:
        row["result"] = f"fail: declined ({decline})"
    return row


def judge(trials: Sequence[dict[str, Any]], events: Sequence[dict[str, Any]],
          start: int = START) -> dict[str, Any]:  # fmt: skip
    rows: list[dict[str, Any]] = []
    for tr in trials:
        base = {"k": tr.get("k"), "n": tr.get("n")}
        rule = tr.get("rule")
        if tr.get("t_rule_start") is None or tr.get("t_rule_end") is None or rule is None:
            rows.append({**base, "result": f"invalid: harness stop before the rule "
                                           f"({str(tr.get('stop'))[:160]})"})  # fmt: skip
            continue
        row = judge_trial(
            events, int(tr["n"]), int(tr["t_rule_start"]), int(tr["t_rule_end"]),
            runtime=rule.get("runtime") or {}, decline=rule.get("decline"),
            t_trial=(int(tr["t_start"]), int(tr.get("t_end") or tr["t_rule_end"])), start=start,
        )  # fmt: skip
        if tr.get("stop"):
            row["harness_stop_after_rule"] = str(tr["stop"])[:160]
        rows.append({**base, **row})
    results = Counter(str(x["result"]).split(":")[0] for x in rows)
    valid = [x for x in rows if not str(x["result"]).startswith("invalid")]
    by_n: dict[int, Counter[str]] = {}
    for x in valid:
        by_n.setdefault(int(x["n"]), Counter())[str(x["result"]).split(":")[0]] += 1
    return {
        "trials": len(rows), "valid": len(valid),
        "success": sum(1 for x in valid if x["result"] == "success"),
        "results": dict(results),
        "fail_causes": dict(Counter(str(x["result"]) for x in valid if x["result"] != "success")),
        "unsafe": sum(sum(x.get("unsafe", {}).values()) for x in rows),
        "false_positives": sum(1 for x in valid if "false positive" in str(x["result"])),
        "by_n": {str(k): dict(v) for k, v in sorted(by_n.items())},
        "rows": rows,
    }  # fmt: skip


def read_events(path: Path) -> list[dict[str, Any]]:
    with gzip.open(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("session", type=Path, nargs="?")
    ap.add_argument("--packets", type=Path, nargs="+", help="packets.jsonl.gz file(s): one trial")
    ap.add_argument("--n", type=int)
    ap.add_argument("--t0", type=int, help="the trial window's start (t_mono_ns; default first)")
    ap.add_argument("--t1", type=int, help="the trial window's end (default the last event)")
    ap.add_argument("--start-points", type=int, default=None)
    a = ap.parse_args()
    if a.packets is not None:
        if a.n is None:
            ap.error("--packets needs --n")
        seen: set[str] = set()
        events = []
        for path in a.packets:  # overlapping windows of the same sniffer stream: each event once
            for e in read_events(path):
                key = json.dumps(e, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    events.append(e)
        if not events:
            raise SystemExit(f"{a.packets}: no events")
        t0 = a.t0 if a.t0 is not None else min(map(_t, events))
        t1 = a.t1 if a.t1 is not None else max(map(_t, events))
        row = judge_trial(events, a.n, t0, t1, start_points=a.start_points)
        print(json.dumps({"packets": [str(x) for x in a.packets], "events": len(events),
                          "window": [t0, t1], **row}, indent=1))  # fmt: skip
        return 0 if row["result"] == "server_ok" else 1
    if a.session is None:
        ap.error("SESSION_DIR or --packets")
    trials = json.loads((a.session / "trials.json").read_text())
    out = judge(trials, read_events(a.session / "packets.jsonl.gz"))
    rows = out.pop("rows")
    print(json.dumps({"session": a.session.name, **out}, indent=1, default=str))
    for x in rows:
        print(json.dumps(x, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
