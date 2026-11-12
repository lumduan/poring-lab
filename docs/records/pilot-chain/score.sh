#!/bin/bash
# score.sh LABEL: every scorer of the night on /dev/shm/poring-lab-demo/*xmas02-LABEL -> /dev/shm/poring-lab-tmp/LABEL/
set -u
L=$1
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
S=$(ls -d /dev/shm/poring-lab-demo/*xmas02-"$L" | head -1)
O=/dev/shm/poring-lab-tmp/$L
SID=$(basename "$S")
P=.venv/bin/python
$P scripts/dungeon_judge.py row "$SID" --map xmas_dun02 > "$O/judge.json" 2> "$O/judge.err"
$P scripts/lock_study.py "$S" --out "$O/lock.json" > /dev/null 2> "$O/lock.err"
$P scripts/detect_speed.py "$S" > "$O/speed.json"
K=$(python3 -c "import json; print(json.load(open('$O/judge.json'))['kills'])")
$P scripts/sight_supply.py "$S" --kills "$K" > "$O/supply.json"
$P scripts/quick_drop_study.py "$S" --lock "$O/lock.json" > "$O/held.json"
$P scripts/walk_refusals.py "$S" --lock "$O/lock.json" > "$O/refusals.json"
python3 - "$S" "$O" <<'EOF'
import json, sys, collections
S, O = sys.argv[1], sys.argv[2]
j = json.load(open(f"{O}/judge.json")); l = json.load(open(f"{O}/lock.json"))[0]
sp = json.load(open(f"{O}/speed.json")); su = json.load(open(f"{O}/supply.json"))
h = json.load(open(f"{O}/held.json")); r = json.load(open(f"{O}/refusals.json"))
ev = [json.loads(x) for x in open(f"{S}/events.jsonl")]; k = collections.Counter(e["kind"] for e in ev)
st = {e["t_ns"]: e for e in ev if e["kind"] == "strike"}
print("E1 kills", j["kills"], "per_h", j["kills_h"], "min", j["minutes"], "deaths", j["deaths"], "hp_min", j["hp_min_pct"],
      "fly", j["fly_wings"], "hard_pass", j["hard_bars"]["pass"], "npc", j["hard_bars"]["npc_contacts"],
      "stalls", k["stall"], "strikes", j["strikes"]["n"])
far = [s for s in l["strikes"] if s["far"]]
print("F1 far", len(far), "far D", sum(s["class"] == "D" for s in far),
      "share", round(sum(s["class"] == "D" for s in far) / max(1, len(far)), 3))
byd = collections.defaultdict(lambda: [0, 0])
for s in l["strikes"]:
    e = st.get(s["t_ns"])
    if not e:
        continue
    d = max(abs(e["rel"][0]), abs(e["rel"][1]))
    g = "0-1" if d <= 1 else "2-6" if d <= 6 else "7-8" if d <= 8 else "9+"
    byd[g][0] += 1; byd[g][1] += s["class"] == "D"
print("class D by distance (n, D):", dict(sorted(byd.items())))
print("classes", l["classes"], "own-body", l["self_recheck"]["own_body_strikes"], "own_d", l["self_recheck"]["own_body_d"],
      "F3", l["far_strikes"]["far_walking"])
print("D1 gpu p50/p95", sp["gpu_ms_p50"], sp["gpu_ms_p95"], "share", sp["gpu_share"], "calls", sp["calls"],
      "box_targets", sp["box_targets"], "struck", sp["struck"], "boxes_after p50", sp["boxes_after_ms_p50"],
      "verdict p50", sp["verdict_from_grab_ms_p50"])
print("supply seen", su["seen"], "per10", su["seen_per_10min"], "K/S", su["kills_per_seen"], su["by_species"])
print("held on D", h["d"], h["held_median_s"], h["held_total_s"])
print("refusals: req", r["requests"], "ignored", r["ignored"], "stuck_s", r["stuck_total_s"], r["stuck_spans"], r["box_strikes"])
print("reach_skip events", k["reach_skip"], "boss_guard", k["boss_guard"], "escape", [e.get("why") for e in ev if e["kind"] == "escape"])
print("items", [(i["name"], i["total"]) for i in j["items"]])
EOF
