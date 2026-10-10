#!/usr/bin/env python3
"""cursor@2's scorer (docs/demonstrations.md 3.36), written and tested BEFORE the runs.

    cursor2_score.py --live DIR --truth DIR --labels-a F --labels-b F --strips-a F --strips-b F
                     --sword SESSION SESSION...

Inputs: `cursor_eval.py live` per session (the three readers' per-grab shapes and series
verdicts; robust2 = the robust reader + the no-entry ring), `cursor2_truth.py sheets` (items.json,
strips.json) and the two blind labellers' answers ({index: label}). Truth per image and per series
= both labellers agree, else UNCLEAR (excluded, counted).

The bars (robust2; the gate = "current" and the robust reader beside it):
1a per image: every read judged against the label of the image it came from: 0 cross-shape
   errors and 0 WALK on an image labelled anything else.
1b per series (robust2 only): 0 WALK verdicts on a series that both labellers say shows the
   no-entry sign on ANY grab; a WALK series without agreement makes 1b INCONCLUSIVE.
1c cursor@1's bar 1 as written (the grab-0 label vs the series verdict): REPORTED, not a bar.
2  TALK: arm A sprite points, grab 0 labelled talk: read twice >= 0.85 (>= 200 probes).
3  SWORD: arm B box points, grab 0 labelled sword: >= 0.40 (>= 100 probes) and >= the gate + 0.25.
4  WALK: arm A cell points + arm B controls, grab 0 labelled walk: >= 0.95, >= the gate - 0.02.
5  NOENTRY: grab 0 labelled noentry: the verdict noentry (REPORTED).
Every bar is also reported per map (the held-out map on its own line).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

READERS = ("current", "robust", "robust2")
TALK_BAR, SWORD_BAR, SWORD_GAIN, WALK_BAR, WALK_SLACK = 0.85, 0.40, 0.25, 0.95, 0.02
TALK_MIN_N, SWORD_MIN_N = 200, 100


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 3), round((c + h) / d, 3)]


def agree(items: list[Any], a: dict[str, str], b: dict[str, str]) -> dict[tuple[Any, ...], str]:
    """{item: label} where both labellers agree; 'unclear' otherwise (or when either is unclear)."""
    out = {}
    for i, it in enumerate(items):
        x, y = a.get(str(i)), b.get(str(i))
        out[tuple(it)] = x if (x == y and x is not None) else "unclear"
    return out


def map_of(session: str) -> str:
    return session.rsplit("-probe-", 1)[-1] if "-probe-" in session else session


def _first_grabs(shapes: list[str]) -> list[int]:
    out = []
    for lo, hi in ((0, 3), (3, 6)):
        g = next((i for i in range(lo, hi) if shapes[i] != "unknown"), None)
        if g is not None:
            out.append(g)
    return out


def rate(rows: list[dict[str, Any]], reader: str, want: str) -> dict[str, Any]:
    k = sum(1 for r in rows if r[reader]["twice"] == want)
    n = len(rows)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci": wilson(k, n)}


def score(lives: dict[str, dict[str, Any]], img: dict[tuple[Any, ...], str],
          ser: dict[tuple[Any, ...], str], sword: str) -> dict[str, Any]:  # fmt: skip
    res: dict[str, Any] = {"images": dict(Counter(img.values())),
                           "series": dict(Counter(ser.values()))}  # fmt: skip
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for ses, live in sorted(lives.items()):
        m = "sword" if ses == sword else map_of(ses)
        g = groups.setdefault(m, {"talk": [], "sword": [], "walk": [], "noentry": []})
        for r in live["rows"]:
            t0 = img.get((ses, r["crop"], 0))
            if ses == sword:
                if r["kind"] == "sword" and t0 == "sword":
                    g["sword"].append(r)
                if r["kind"] == "control" and t0 == "walk":
                    g["walk"].append(r)
            else:
                if r["kind"] == "sprite" and t0 == "talk":
                    g["talk"].append(r)
                if r["kind"] == "cell" and t0 == "walk":
                    g["walk"].append(r)
            if t0 == "noentry":
                g["noentry"].append(r)
    for reader in READERS:
        cross, walk_other, judged, unclear = [], 0, 0, 0
        as_written = []
        series_err, series_unclear, walk_series = [], [], 0
        for ses, live in sorted(lives.items()):
            for r in live["rows"]:
                sh = r[reader]["shapes"]
                for g in _first_grabs(sh):
                    t = img.get((ses, r["crop"], g))
                    if t in (None, "unclear"):
                        unclear += 1
                        continue
                    judged += 1
                    if sh[g] != t:
                        cross.append(f"{ses[:15]} {r['crop']} g{g} {t}->{sh[g]}")
                        walk_other += sh[g] == "walk"
                t0 = img.get((ses, r["crop"], 0))
                v = r[reader]["twice"]
                if t0 not in (None, "unclear") and v not in ("unknown", t0):
                    as_written.append(f"{ses[:15]} {r['crop']} {t0}->{v}")
                if reader == "robust2" and v == "walk":
                    walk_series += 1
                    s = ser.get((ses, r["crop"]))
                    if s == "yes":
                        series_err.append(f"{ses[:15]} {r['crop']}")
                    elif s != "no":
                        series_unclear.append(f"{ses[:15]} {r['crop']} {s}")
        out: dict[str, Any] = {
            "1a": {"cross_shape": cross, "walk_on_other": walk_other, "reads_judged": judged,
                   "reads_on_unclear": unclear},
            "1c_as_written": as_written,
        }  # fmt: skip
        if reader == "robust2":
            out["1b"] = {"walk_series": walk_series, "errors": series_err,
                         "unclear": series_unclear}  # fmt: skip
        pooled: dict[str, list[dict[str, Any]]] = {"talk": [], "sword": [], "walk": [],
                                                   "noentry": []}  # fmt: skip
        per_map: dict[str, Any] = {}
        for m, g in sorted(groups.items()):
            per_map[m] = {k: rate(v, reader, k) for k, v in g.items() if v}
            for k in pooled:
                pooled[k] += g[k]
        out["pooled"] = {k: rate(v, reader, k) for k, v in pooled.items()}
        out["per_map"] = per_map
        res[reader] = out
    res["verdict"], res["why"] = verdict(res)
    return res


def verdict(res: dict[str, Any]) -> tuple[str, list[str]]:
    r2, gate = res["robust2"], res["current"]
    p, pg = r2["pooled"], gate["pooled"]
    fail, inconclusive = [], []
    if r2["1a"]["cross_shape"] or r2["1a"]["walk_on_other"]:
        fail.append("1a: a read differs from its image's label")
    if r2["1b"]["errors"]:
        fail.append("1b: WALK on a series showing the no-entry sign")
    if r2["1b"]["unclear"]:
        inconclusive.append("1b: a WALK series without the labellers' agreement")
    if p["talk"]["n"] < TALK_MIN_N or p["sword"]["n"] < SWORD_MIN_N:
        inconclusive.append("too few labelled talk or sword probes")
    else:
        if p["talk"]["rate"] < TALK_BAR:
            fail.append("2: TALK below 0.85")
        if (
            p["sword"]["rate"] < SWORD_BAR
            or p["sword"]["rate"] < (pg["sword"]["rate"] or 0) + SWORD_GAIN
        ):
            fail.append("3: SWORD below 0.40 or under the gate + 0.25")
    if (
        p["walk"]["n"] == 0
        or p["walk"]["rate"] < WALK_BAR
        or (p["walk"]["rate"] < (pg["walk"]["rate"] or 0) - WALK_SLACK)
    ):
        fail.append("4: WALK below 0.95 or under the gate - 0.02")
    if fail:
        return "FAIL", fail + inconclusive
    if inconclusive:
        return "INCONCLUSIVE", inconclusive
    return "PASS", []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    for k in ("labels-a", "labels-b", "strips-a", "strips-b"):
        ap.add_argument(f"--{k}", type=Path, required=True)
    ap.add_argument("--sword", required=True, help="arm B's session name")
    ap.add_argument("sessions", nargs="+")
    a = ap.parse_args()
    lives = {s: json.loads((a.live / f"live-{s}.json").read_text()) for s in a.sessions}
    items = json.loads((a.truth / "items.json").read_text())
    strips = json.loads((a.truth / "strips.json").read_text())

    def load(p: Path) -> dict[str, str]:
        d: dict[str, str] = json.loads(p.read_text())
        return d

    img = agree(items, load(a.labels_a), load(a.labels_b))
    ser = agree(strips, load(a.strips_a), load(a.strips_b))
    res = score(lives, img, ser, a.sword)
    print(json.dumps(res, indent=1))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[res["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
