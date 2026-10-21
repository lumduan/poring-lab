#!/usr/bin/env python3
"""Score the blind labellers against the answer key (docs/planning/orcsdun01-detector.md section
5's bars; Batt 2026-10-21: "a contact sheet per species checked by two blind labeller agents"). A
species passes when EACH labeller calls >= GOOD_BAR of its crops "good" AND names the right species
on >= SPECIES_BAR of them. The key never reaches a labeller (it lives outside the pack).

    blind_score.py --key KEY.json ANSWERS.json [ANSWERS.json ...] [--both-good OUT.json]

Committed 2026-10-21 for round 2 (round 1's copy lived only in scratch: scorers are committed). Its
positive case: round 1's answers (blind-A / blind-B on the col1 key) reproduce the 12:10 table
exactly (orcsdun01-detector.md 5a; agreement 218 / 201 / 213 of 225, 157 crops good for both).
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
SPECIES_BAR = 0.95
NAMES = {1111: "Drainliar", 1082: "White Plant", 1042: "Steel Chonchon", 1084: "Black Mushroom",
         1153: "Orc Zombie", 1005: "Familiar", 1002: "Poring", 1152: "Orc Skeleton"}  # fmt: skip


def per_species(key: Mapping[str, Any], answers: Mapping[str, Mapping[str, Any]]
                ) -> dict[int, dict[str, Any]]:  # fmt: skip
    """PURE: one labeller's numbers per species (the key's mob id): n, good %, species-right %,
    the q1 "no" / q2 "off" / q2 "loose" counts, and the pass of section 5's two bars."""
    letters = {str(k).upper(): int(v) for k, v in key["letters"].items()}
    c: dict[int, Counter[str]] = {}
    for crop, k in key["crops"].items():
        m = int(k["mob"])
        x = answers.get(crop, {})
        cc = c.setdefault(m, Counter())
        cc["n"] += 1
        cc["good"] += x.get("q2") == "good"
        cc["no"] += x.get("q1") == "no"
        cc["off"] += x.get("q2") == "off"
        cc["loose"] += x.get("q2") == "loose"
        cc["species_ok"] += letters.get(str(x.get("q3", "")).strip().upper()) == m
    out = {}
    for m, cc in c.items():
        n = cc["n"]
        good, sp = cc["good"] / n, cc["species_ok"] / n
        out[m] = {"n": n, "good": round(good, 4), "species": round(sp, 4), "no": cc["no"],
                  "off": cc["off"], "loose": cc["loose"],
                  "pass": good >= GOOD_BAR and sp >= SPECIES_BAR}  # fmt: skip
    return out


def both_good(key: Mapping[str, Any], a: Mapping[str, Mapping[str, Any]],
              b: Mapping[str, Mapping[str, Any]]) -> list[str]:  # fmt: skip
    """PURE: the crops both labellers called good with the right species (gold-set candidates)."""
    letters = {str(k).upper(): int(v) for k, v in key["letters"].items()}

    def ok(x: Mapping[str, Any], m: int) -> bool:
        return x.get("q2") == "good" and letters.get(str(x.get("q3", "")).upper()) == m

    return [c for c, k in key["crops"].items()
            if ok(a.get(c, {}), int(k["mob"])) and ok(b.get(c, {}), int(k["mob"]))]  # fmt: skip


def load_answers(path: Path) -> dict[str, dict[str, Any]]:
    return {str(x["crop"]): x for x in json.loads(path.read_text())}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("answers", type=Path, nargs="+")
    ap.add_argument("--both-good", type=Path)
    a = ap.parse_args(argv)
    key = json.loads(a.key.read_text())
    ans = {str(p): load_answers(p) for p in a.answers}
    res: dict[str, Any] = {"per_labeller": {}, "species_pass": {}}
    for who, an in ans.items():
        res["per_labeller"][who] = {
            NAMES.get(m, str(m)): v for m, v in per_species(key, an).items()
        }
    for name in next(iter(res["per_labeller"].values())):
        res["species_pass"][name] = all(r[name]["pass"] for r in res["per_labeller"].values())
    if len(ans) == 2:
        x, y = ans.values()
        n = len(key["crops"])

        def same(c: str, q: str) -> bool:
            return str(x.get(c, {}).get(q)).upper() == str(y.get(c, {}).get(q)).upper()

        res["agreement"] = {q: sum(same(c, q) for c in key["crops"]) for q in ("q1", "q2", "q3")}
        res["agreement"]["n"] = n
        bg = both_good(key, x, y)
        res["both_good_right_species"] = len(bg)
        if a.both_good:
            a.both_good.write_text(json.dumps(bg))
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
