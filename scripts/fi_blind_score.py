#!/usr/bin/env python3
"""Score T2-items, the blind check of the floor-item labels on xmas_dun02 (docs/planning/
xmas02-detector.md Amendment O.5, ACCEPTED by O1 2026-11-10; tool T-O3), PER STRATUM, against the
pack's answer key (scripts/fi_labels.py pack). The key never reaches a labeller.

    fi_blind_score.py --key KEY.json ANSWERS_1.json ANSWERS_2.json [--both-good OUT.json]
                      [--out JSON]

THE BARS (gef10-detector.md 8, unchanged), from EACH labeller:
- good box = q1 "yes" AND q2 "good", on the 40 ITEM crops (strata N, F, M): >= 0.90;
- item-present right = q1 "yes" on an item crop, "no" on an E crop ("unsure" is wrong; a missing
  answer is wrong), on ALL 60 crops: >= 0.95.
Per stratum reported (N near, F far, M under a model, E empty: its plain and hard halves apart).

THE PRE-REGISTERED FALLBACKS (O.5, each labeller), only when the pooled bars fail:
- FALLBACK_NEAR: N's good box < 0.90 while F and M each pass (good >= 0.90) and the bars hold on
  the pack without N's crops -> frames with a kept label within 1 cell of her do not train;
- FALLBACK_MODEL: M's good box < 0.90 while N and F each pass and the bars hold without M's crops
  -> frames with an under-model label do not train.
- Anything else: FAIL -> no item class this round (reported to Batt).
The round's verdict: PASS when both labellers pass; the ONE fallback when every labeller passes or
needs that same fallback; FAIL otherwise (one labeller needing NEAR and the other MODEL is not a
pre-registered case). An empty stratum never passes.

The evaluation's pack (O.9, the key's ``eval_test``): no bars; ``--both-good`` writes the item
crops BOTH labellers answered yes / good: the EVALUATED crops of I1 (scripts/fi_eval.py).
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
ITEM_STRATA = ("N", "F", "M")
FALLBACK = {"N": "FALLBACK_NEAR", "M": "FALLBACK_MODEL"}


def _norm(x: Any) -> str:
    return str(x if x is not None else "").strip().lower()


def tally(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Any]],
          drop: Sequence[str] = ()) -> dict[str, Counter[str]]:  # fmt: skip
    """PURE: per stratum (and ``all``) the counts of one labeller, without the ``drop`` strata."""
    c: dict[str, Counter[str]] = {"all": Counter()}
    for crop, k in key["crops"].items():
        s = str(k["stratum"])
        if s in drop:
            continue
        item = k["truth"] == "item"
        x = answers.get(crop, {})
        q1, q2 = _norm(x.get("q1")), _norm(x.get("q2"))
        right = (q1 == "yes") if item else (q1 == "no")
        for cc in (c.setdefault(s, Counter()), c["all"]):
            cc["n"] += 1
            cc["n_item"] += item
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
                cc[f"right_{k.get('kind', 'plain')}"] += right
                cc[f"n_{k.get('kind', 'plain')}"] += 1
    return c


def shares(cc: Counter[str]) -> dict[str, Any]:
    good = cc["good"] / cc["n_item"] if cc["n_item"] else None
    present = cc["present_right"] / cc["n"] if cc["n"] else None
    return {**{k: int(v) for k, v in sorted(cc.items())},
            "good_share": None if good is None else round(good, 4),
            "present_right_share": None if present is None else round(present, 4)}  # fmt: skip


def bars_hold(cc: Counter[str]) -> bool:
    """PURE: both pooled bars on these counts (no item crop: never)."""
    return (cc["n_item"] > 0 and cc["good"] / cc["n_item"] >= GOOD_BAR
            and cc["present_right"] / cc["n"] >= PRESENT_BAR)  # fmt: skip


def stratum_passes(c: Mapping[str, Counter[str]], s: str) -> bool:
    cc = c.get(s)
    return bool(cc and cc["n_item"] and cc["good"] / cc["n_item"] >= GOOD_BAR)


def labeller(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: one labeller's per-stratum numbers and verdict (PASS / FALLBACK_* / FAIL)."""
    c = tally(key, answers)
    out: dict[str, Any] = {"per_stratum": {s: shares(cc) for s, cc in sorted(c.items())}}
    if bars_hold(c["all"]):
        return {**out, "verdict": "PASS"}
    for s, name in FALLBACK.items():
        others = [x for x in ITEM_STRATA if x != s]
        if stratum_passes(c, s) or not all(stratum_passes(c, x) for x in others):
            continue
        rest = tally(key, answers, drop=(s,))["all"]
        if bars_hold(rest):
            return {**out, "verdict": name, "without": s, "bars_without": shares(rest)}
    return {**out, "verdict": "FAIL"}


def round_verdict(verdicts: Sequence[str]) -> str:
    """PURE (O.5): PASS when all pass; one fallback when every labeller passes or needs it."""
    if not verdicts or "FAIL" in verdicts:
        return "FAIL"
    need = {v for v in verdicts if v != "PASS"}
    if not need:
        return "PASS"
    return need.pop() if len(need) == 1 else "FAIL"


def both_good(key: Mapping[str, Any], answers: Sequence[Mapping[str, Mapping[str, Any]]]
              ) -> list[str]:  # fmt: skip
    """PURE: the ITEM crops EVERY labeller answered q1 yes and q2 good (O.9: EVALUATED)."""

    def ok(x: Mapping[str, Any]) -> bool:
        return _norm(x.get("q1")) == "yes" and _norm(x.get("q2")) == "good"

    return [c for c, k in sorted(key["crops"].items())
            if k["truth"] == "item" and all(ok(a.get(c, {})) for a in answers)]  # fmt: skip


def score(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Mapping[str, Any]]]
          ) -> dict[str, Any]:  # fmt: skip
    """PURE: per labeller, the round's verdict (T2-items) or none (the evaluation's pack), the
    agreement and the both-good crops."""
    per = {w: labeller(key, an) for w, an in answers.items()}
    res: dict[str, Any] = {
        "per_labeller": per,
        "pack": "evaluation (O.9)" if key.get("eval_test") else "T2-items",
    }
    if key.get("eval_test"):
        res["verdict"] = None
    else:
        res["verdict"] = round_verdict([r["verdict"] for r in per.values()])
        if len(answers) != 2:
            res["verdict"] = "FAIL"
            res["why"] = f"{len(answers)} labellers, O.5 needs two"
    vals = list(answers.values())
    if len(vals) == 2:
        x, y = vals
        res["agreement"] = {q: sum(_norm(x.get(c, {}).get(q)) == _norm(y.get(c, {}).get(q))
                                   for c in key["crops"]) for q in ("q1", "q2")}  # fmt: skip
        res["agreement"]["n"] = len(key["crops"])
    res["both_good"] = len(both_good(key, vals))
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
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    key = json.loads(a.key.read_text())
    ans = {str(p): load_answers(p) for p in a.answers}
    res = score(key, ans)
    if a.both_good:
        a.both_good.write_text(json.dumps(both_good(key, list(ans.values()))))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
