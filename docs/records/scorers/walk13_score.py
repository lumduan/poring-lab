"""Score one walk@7 session per 3.12: the first 50 not interrupted, safety, segments, substitutes,
patience, re-localisations (vs packets)."""
import json, sys, gzip, subprocess
from collections import Counter
from pathlib import Path
sys.path.insert(0, "scripts")
from poring_dataset import verify as V
S = Path(sys.argv[1])
subprocess.run(["uv", "run", "python", "scripts/demo_interruptions.py", str(S)], check=True, capture_output=True)
subprocess.run(["uv", "run", "python", "scripts/demo_verify.py", str(S)], check=True, capture_output=True)
rows = [json.loads(l) for l in open(S / "demo.verified.jsonl")]
routes = sorted([r for r in rows if r.get("rule") == "walk@13"], key=lambda r: r["t_mono_ns"])
inter = [r for r in routes if r["outcome"]["status"] == "interrupted"]
ok = [r for r in routes if r["outcome"]["status"] != "interrupted"][:50]
segs = [r for r in rows if r.get("rule") == "walk@13/click" and r["outcome"]["status"] != "interrupted"]
events = [json.loads(l) for l in gzip.open(S / "packets.jsonl.gz", "rt")]
man = json.load(open(S / "manifest.json"))
events = [e for e in events if man["t0_mono_ns"] <= e["t_mono_ns"] <= man["t1_mono_ns"]]  # the run's window
safety = Counter("GM_act:" + str(e.get("kind")) for e in events if e["type"] == "act" and int(e.get("src_gid", -1)) == 2000002)
safety.update("request(live):" + e["type"] for e in events if e["type"] in ("attack_request", "npc_contact"))
subs = Counter(r["outcome"]["cause"] for r in ok if r["outcome"]["evidence"].get("substitute"))
waits = [r["outcome"]["evidence"].get("waited_s", 0) for r in ok]
rel = Counter(); 
for r in ok:
    for e in r["outcome"]["evidence"].get("events", []):
        if "relocalise" in e:
            rl = e["relocalise"]
            if not rl.get("ok"): rel[(e.get("why"), "undecided")] += 1; continue
            true = V.position_before(events, e["t"], 2000002)
            rel[(e.get("why"), "correct" if true and list(true) == rl["to"] else "WRONG")] += 1
orig = {json.loads(l)["record_id"]: json.loads(l) for l in open(S / "demo.jsonl")}
tiers = Counter()
for sg in segs:
    o = orig[sg["record_id"]]["outcome"]["evidence"]
    tg = [t for t in o.get("target", []) if isinstance(t, dict)]
    named = any(t.get("cell") == [0, 0] for t in tg)
    tier = tg[-1].get("tier") if tg else None
    tiers[f"{tier}:{'named' if named else 'unnamed'}:{sg['outcome']['status']}"] += 1
print(json.dumps({"session": S.name, "clicks_by_tier": dict(tiers), "routes": len(routes), "interrupted": len(inter),
  "scored": dict(Counter(r["outcome"]["status"] for r in ok)),
  "fail_causes": dict(Counter(r["outcome"]["cause"] for r in ok if r["outcome"]["status"] == "fail")),
  "SAFETY": dict(safety), "segments": dict(Counter(s["outcome"]["status"] for s in segs)),
  "seg_fail": dict(Counter(s["outcome"]["cause"] for s in segs if s["outcome"]["status"] != "success")),
  "substitutes": dict(subs), "waited_s_total": round(sum(waits), 1), "routes_that_waited": sum(1 for x in waits if x),
  "relocalisations": {f"{k[0]}:{k[1]}": v for k, v in rel.items()}}, indent=1))
raw = [json.loads(l) for l in open(S / "demo.jsonl")]
def _walk(o, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("ui_refused", "talk_refused") and v: acc[k] += len(v) if isinstance(v, list) else 1
            if k == "outcome" and v in ("covered_talk_cell", "no_safe_point"): acc[v] += 1
            _walk(v, acc)
    elif isinstance(o, list):
        for v in o: _walk(v, acc)
acc = Counter(); _walk(raw, acc)
print(json.dumps({"walk12_decisions_inherited": dict(acc), "manifest_end": {k: man.get(k) for k in ("ended", "reason", "exit_code")}}))
# --- walk@13 (3.24): per change, how often it acted; the strict count ---------------------------
per = Counter()
blocked_route = blocked_unit = 0
for r in ok:
    ev = r["outcome"]["evidence"]
    per["routes_with_replans"] += 1 if ev.get("replans") else 0
    per["replans"] += int(ev.get("replans") or 0)
    if ev.get("npc_substitute"):
        per["npc_substitute_routes"] += 1
    for e in ev.get("events", []):
        if "replan" in e:
            blocked_route += len(e["blocked"]["route"]); blocked_unit += len(e["blocked"]["unit"])
        if "replan_none" in e:
            per["replan_none"] += 1
        if "npc_substitute" in e and e["npc_substitute"] is None:
            per["npc_substitute_none_found"] += 1
        if "taken_check" in e:
            per["taken_checks"] += 1
            per["taken_on_it" if e["on_it"] else "taken_nobody_on_it"] += 1
        if e.get("signs"):
            per["steps_with_signs"] += 1
causes = Counter(r["outcome"]["cause"] for r in ok if r["outcome"]["status"] == "success" and r["outcome"]["cause"])
strict = sum(1 for r in ok if r["outcome"]["status"] == "success" and not r["outcome"]["evidence"].get("substitute")
             and not r["outcome"]["evidence"].get("npc_substitute"))
declines = Counter(r["outcome"]["evidence"].get("decline") for r in ok if r["outcome"]["evidence"].get("decline"))
print(json.dumps({"walk13_changes": dict(per), "cells_blocked_by_replans": {"route": blocked_route, "unit": blocked_unit},
                  "success_causes (substitutes reported apart)": dict(causes),
                  "STRICT success (no substitute of either kind)": strict,
                  "declines": dict(declines)}, indent=1))
