"""iz_dun00 held-out (3.29) offline checks for Batt (2026-10-09 ~13:10), after the session closed:
1. the Hydra question: the server's monsters around the GM when /where read (165, 164) (Batt's 13:03
   screenshot), with species and offsets;
2. safety: attack_request / npc_contact / GM act normal|pickup over the run;
3. the gate's monster refusals vs the HUD's monster boxes alive then (their confidence), the gate's
   own scores not being logged in this run.
    python izdun_check.py SESSION_DIR
"""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "packages/poring_dataset/src")
from poring_dataset.labels import OBJTYPE_CLASS  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

S = Path(sys.argv[1])
mobs = json.load(open("data/kb/mobs.json"))
events = [json.loads(line) for line in gzip.open(S / "packets.jsonl.gz", "rt")]
tl = Timeline(events)
rows = [json.loads(line) for line in open(S / "demo.jsonl")]
GM = 2000002

# 1. when did a relocalisation put us on (165, 164)?
hits = []
for r in rows:
    for e in (r.get("outcome") or {}).get("evidence", {}).get("events", []) or []:
        rl = e.get("relocalise") or {}
        if rl.get("ok") and list(rl.get("to") or []) == [165, 164]:
            hits.append(int(e["t"]))
print("relocalised to (165,164) at:", len(hits))
for t in hits[:3]:
    fw = tl.frame_world(t)
    me = fw.self_pos
    near = sorted(((x.x - me[0], x.y - me[1], mobs.get(str(x.job), {}).get("name", x.job), x.gid)
                   for x in fw.entities if OBJTYPE_CLASS.get(x.objtype) == "monster"
                   and abs(x.x - me[0]) <= 15 and abs(x.y - me[1]) <= 15),
                  key=lambda v: abs(v[0]) + abs(v[1]))
    print(" t", t, "self", me, "monsters within 15:", [(round(a), round(b), n) for a, b, n, _ in near])

# 2. safety
man = json.load(open(S / "manifest.json"))
ev = [e for e in events if man["t0_mono_ns"] <= e["t_mono_ns"] <= man["t1_mono_ns"]]
safety = Counter(e["type"] for e in ev if e["type"] in ("attack_request", "npc_contact"))
safety.update("GM_act:" + str(e.get("kind")) for e in ev
              if e["type"] == "act" and int(e.get("src_gid", -1)) == GM and e.get("kind") in ("normal", "pickup"))
print("SAFETY over the run:", dict(safety))

# 3. refusals vs HUD boxes
hud = []
for log in ("/dev/shm/poring-lab-route/scene.jsonl.1", "/dev/shm/poring-lab-route/scene.jsonl"):
    p = Path(log)
    if p.exists():
        for line in p.open():
            try:
                hud.append(json.loads(line))
            except ValueError:
                pass
alive: dict[int, dict] = {}
timeline = []  # (t, {id: conf})
for m in hud:
    msg = m.get("msg", {})
    t = int(msg.get("t_mono_ns", m.get("logged_ns", 0)))
    if msg.get("type") == "hud_scene":
        alive = {o["id"]: o for o in msg.get("objects", []) if o.get("cls") == "monster"}
    elif msg.get("type") == "hud_delta":
        for o in msg.get("add", []):
            if o.get("cls") == "monster":
                alive[o["id"]] = o
        for i in msg.get("remove", []):
            alive.pop(i, None)
    timeline.append((t, {i: o.get("conf") for i, o in alive.items()}))
timeline.sort(key=lambda x: x[0])
import bisect  # noqa: E402
ts = [t for t, _ in timeline]
ref = Counter()
for r in rows:
    if r.get("rule") != "walk@15":
        continue
    for e in (r.get("outcome") or {}).get("evidence", {}).get("events", []) or []:
        if e.get("outcome") != "covered_unit_envelope":
            continue
        env = [t.get("envelope") for t in e.get("target", []) if t.get("envelope")]
        if not env or env[-1].get("nearest") != "monster":
            ref["refusal_nearest_not_monster"] += 1
            continue
        t = int(e["t"])
        i = bisect.bisect_right(ts, t) - 1
        confs = [c for c in (timeline[i][1].values() if i >= 0 else []) if c is not None]
        fw = tl.frame_world(t)
        me = fw.self_pos
        real = [x for x in fw.entities if OBJTYPE_CLASS.get(x.objtype) == "monster" and me
                and max(abs(x.x - me[0]), abs(x.y - me[1])) <= 15]
        key = ("server_monster_on_screen" if real else "NO_server_monster_on_screen")
        if not confs:
            ref[f"monster_refusal:{key}:hud_none"] += 1
        elif max(confs) < 0.30:
            ref[f"monster_refusal:{key}:hud_all_below_0.30"] += 1
        else:
            ref[f"monster_refusal:{key}:hud_some_>=0.30"] += 1
print("gate refusals:", dict(ref))
