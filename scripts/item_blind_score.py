#!/usr/bin/env python3
"""Score the blind labellers of an ITEM pack against its answer key (docs/planning/item-class.md
section 5, pre-registered 2026-10-23 a46893d). Per map, from EACH labeller:
- "good box" = q1 yes AND q2 good, on the ITEM crops: bar >= GOOD_BAR (0.90);
- "item-present right" = q1 yes on an item crop, q1 no on a negative crop ("unsure" is wrong),
  on ALL crops: bar >= PRESENT_BAR (0.95).
A map passes when both bars hold for every labeller. The key never reaches a labeller.

    item_blind_score.py --key KEY.json ANSWERS_A.json ANSWERS_B.json [--both-good OUT.json]

``--both-good`` writes the item crops both labellers judged q1 yes + q2 good (the EVALUATED
labels of ../docs/benchmarks/item-class.md when run on the seed-6 pack).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

GOOD_BAR = 0.90
PRESENT_BAR = 0.95


def _norm(x: Any) -> str:
    return str(x if x is not None else "").strip().lower()


def per_map(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: one labeller's numbers per map: the item crops' good share, the present-right share
    over all crops, the counts, and the pass of both bars. A missing answer counts as wrong."""
    c: dict[str, Counter[str]] = {}
    for crop, k in key["crops"].items():
        m = str(k["map"])
        item = k["truth"] == "item"
        x = answers.get(crop, {})
        q1, q2 = _norm(x.get("q1")), _norm(x.get("q2"))
        cc = c.setdefault(m, Counter())
        cc["n"] += 1
        cc["n_item"] += item
        cc["n_neg"] += not item
        right = (q1 == "yes") if item else (q1 == "no")
        cc["present_right"] += right
        if item:
            cc["good"] += q1 == "yes" and q2 == "good"
            cc["loose"] += q1 == "yes" and q2 == "loose"
            cc["off"] += q1 == "yes" and q2 == "off"
            cc["item_no"] += q1 == "no"
            cc["item_unsure"] += q1 == "unsure"
        else:
            cc["neg_yes"] += q1 == "yes"
            cc["neg_unsure"] += q1 == "unsure"
    out = {}
    for m, cc in sorted(c.items()):
        good = cc["good"] / cc["n_item"] if cc["n_item"] else 0.0
        present = cc["present_right"] / cc["n"] if cc["n"] else 0.0
        out[m] = {
            **{k: int(v) for k, v in sorted(cc.items())},
            "good_share": round(good, 4),
            "present_right_share": round(present, 4),
            "pass": cc["n_item"] > 0 and good >= GOOD_BAR and present >= PRESENT_BAR,
        }
    return out


def both_good(
    key: Mapping[str, Any],
    a: Mapping[str, Mapping[str, Any]],
    b: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """PURE: the ITEM crops both labellers answered q1 yes and q2 good."""

    def ok(x: Mapping[str, Any]) -> bool:
        return _norm(x.get("q1")) == "yes" and _norm(x.get("q2")) == "good"

    return [
        c
        for c, k in key["crops"].items()
        if k["truth"] == "item" and ok(a.get(c, {})) and ok(b.get(c, {}))
    ]


def score(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Mapping[str, Any]]]
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: per labeller per map, the map verdicts (every labeller passes), the agreement."""
    res: dict[str, Any] = {"per_labeller": {w: per_map(key, an) for w, an in answers.items()}}
    maps = sorted({str(k["map"]) for k in key["crops"].values()})
    res["map_pass"] = {
        m: all(r.get(m, {}).get("pass", False) for r in res["per_labeller"].values()) for m in maps
    }
    if len(answers) == 2:
        x, y = answers.values()
        res["agreement"] = {
            q: sum(_norm(x.get(c, {}).get(q)) == _norm(y.get(c, {}).get(q)) for c in key["crops"])
            for q in ("q1", "q2")
        }
        res["agreement"]["n"] = len(key["crops"])
        res["both_good"] = len(both_good(key, x, y))
    return res


def load_answers(path: Path) -> dict[str, dict[str, Any]]:
    return {str(x["crop"]).zfill(3): x for x in json.loads(path.read_text())}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("answers", type=Path, nargs="+")
    ap.add_argument("--both-good", type=Path)
    a = ap.parse_args(argv)
    key = json.loads(a.key.read_text())
    ans = {str(p): load_answers(p) for p in a.answers}
    res = score(key, ans)
    if a.both_good and len(ans) == 2:
        x, y = ans.values()
        a.both_good.write_text(json.dumps(both_good(key, x, y)))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
