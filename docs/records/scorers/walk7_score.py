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
routes = sorted([r for r in rows if r.get("rule") == "walk@7"], key=lambda r: r["t_mono_ns"])
inter = [r for r in routes if r["outcome"]["status"] == "interrupted"]
ok = [r for r in routes if r["outcome"]["status"] != "interrupted"][:50]
segs = [r for r in rows if r.get("rule") == "walk@7/segment" and r["outcome"]["status"] != "interrupted"]
events = [json.loads(l) for l in gzip.open(S / "packets.jsonl.gz", "rt")]
safety = Counter(e["type"] for e in events if e["type"] in ("attack_request", "npc_contact"))
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
print(json.dumps({"session": S.name, "routes": len(routes), "interrupted": len(inter),
  "scored": dict(Counter(r["outcome"]["status"] for r in ok)),
  "fail_causes": dict(Counter(r["outcome"]["cause"] for r in ok if r["outcome"]["status"] == "fail")),
  "SAFETY": dict(safety), "segments": dict(Counter(s["outcome"]["status"] for s in segs)),
  "seg_fail": dict(Counter(s["outcome"]["cause"] for s in segs if s["outcome"]["status"] != "success")),
  "substitutes": dict(subs), "waited_s_total": round(sum(waits), 1), "routes_that_waited": sum(1 for x in waits if x),
  "relocalisations": {f"{k[0]}:{k[1]}": v for k, v in rel.items()}}, indent=1))
