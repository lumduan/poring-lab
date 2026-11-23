#!/bin/bash
# xmas02_items_8c_score.sh: xmas02-items-1080.md Amendment 47 -- section 8c in play at 1080, scored ONCE
# after the chain's last run. A = xmas02fi5 (the deployed loot model), B = xmas02fi9 + round 10's rule
# (the player's item_floor_1080 0.4, item_ring_1080 30, item_edge_1080 12, item_edge_top_1080 32).
#   usage: xmas02_items_8c_score.sh "A1+A2+A3[+..]" "B1+B2+B3[+..]"   (EVERY run of each arm, in order;
#          screen_ab counts an invalid one as an error and leaves it out of the means)
# The lines (section 8c):
#   loot/h   mean(B) - mean(A) > +2 SE (Welch, screen_ab's diff and se): PASS (better); else FAIL;
#   kills/h  mean(B) - mean(A) >= -2 SE: screen_ab's own line;
#   deaths   B <= A: screen_ab's own line;   errors: none new (screen_ab's own line);
#   any line INCONCLUSIVE (< 2 valid runs a side) -> the round's 8c is INCONCLUSIVE.
#   8c PASSES when all four pass.
set -u
cd /home/bot/docker/poring-lab
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp
O=/dev/shm/poring-lab-tmp/i1080/8c
mkdir -p $O
.venv/bin/python scripts/screen_ab.py score --a "$1" --b "$2" > $O/score-8c.out 2> $O/score-8c.err
rc=$?
echo "screen_ab score rc=$rc"
[ $rc -eq 0 ] || exit 2
python3 - "$O/score-8c.out" <<'PY'
import json, sys
text = open(sys.argv[1]).read()
doc = json.loads(text[text.index("{\n"):]) if "{\n" in text else json.loads(text)
lines = doc["verdict"]["lines"]
loot = lines["loot_h"]
if loot.get("verdict") == "INCONCLUSIVE":
    lv = "INCONCLUSIVE"
else:
    lv = "PASS" if loot["diff"] > 2 * loot["se"] else "FAIL"
out = {
    "loot_h": {**loot, "rule": "diff > +2 SE", "verdict_8c": lv},
    "kills_h": {**lines["kills_h"], "rule": "diff >= -2 SE"},
    "deaths": lines["deaths"],
    "errors": lines["errors"],
    "valid": doc["verdict"]["valid"],
}
states = [lv, lines["kills_h"]["verdict"], lines["deaths"]["verdict"], lines["errors"]["verdict"]]
out["verdict_8c"] = ("INCONCLUSIVE" if "INCONCLUSIVE" in states else
                     "PASS" if all(s == "PASS" for s in states) else "FAIL")
json.dump(out, open("/dev/shm/poring-lab-tmp/i1080/8c/verdict-8c.json", "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
PY
