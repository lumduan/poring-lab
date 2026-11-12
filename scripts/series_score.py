#!/usr/bin/env python3
"""Pooled per-arm scores of an A / B pilot series (rogue-xmas02.md 4DD, the night series; 4DH's
base), from each run's committed-scorer outputs.

    series_score.py --arm A=DIR,DIR,... --arm B=DIR,DIR,... [--decide B:A] [--min-gain 0.03]

Each DIR holds one run's scorer outputs (the chain's score.sh writes them per label):
- ``judge.json``: ``dungeon_judge.py row SESSION`` (kills, hours, deaths, the items by fate);
- ``speed.json`` (optional): ``detect_speed.py SESSION`` (D1: ``gpu_ms_p95``);
- ``refusals.json`` (optional): ``walk_refusals.py SESSION`` (W1: ``ignored`` / ``requests``).

Pooled = summed counts over summed hours (``judge.hours``, the judge's own unrounded divisor), never
a mean of per-run rates. Income is the judge's own measure (``dungeon_judge.items_value``): the
units the bot gained itself (picked + stolen + snatched) at the Overcharge Lv 10 NPC sell price
(``econ_items``' ``sell_oc10``). "Common" is the same sum over items with ``sell_oc10`` below
COMMON_MAX (3000 z: 4CR's measure, so a single rare drop cannot decide a pair); the rarer items are
listed. On p84 + p85, p92 + p93, p94 + p95 and p96 + p97 this reproduces the figures recorded in
4CX / 4DC / 4DE within 5 z/h.

``--decide B:A`` applies 4DD's bars: D1 pooled kills / h of B >= A x (1 + --min-gain); D2 pooled
common z/h of B >= A; no harm: deaths of B <= deaths of A, W1 of B <= 3.5 % pooled, D1 p95 <= 35 ms
on every run of both arms. Fewer than --min-runs complete runs in an arm is NO_VERDICT (4DD).
Each run's MVP sightings (distinct Stormy Knight gids in view, its packets) and deaths are
REPORTED per run (4DI), never deciding.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

COMMON_MAX = 3000  # z at Overcharge: items below it are "common" (4CR)
KNIGHT = 1251  # Stormy Knight (sk_flee_score.KNIGHT): the map's MVP, sightings REPORTED (4DI)
INCOME = ("picked", "stolen", "snatched")  # dungeon_judge.INCOME: the bot's own gains
W1_MAX, D1_MAX_MS = 0.035, 35.0  # the base's no-harm bars (4CR / 4DD)


def mvp_sightings(packets: Sequence[Mapping[str, Any]], job: int = KNIGHT) -> int:
    """PURE (4DI): how many distinct MVP gids came into view in a run (``entity_appear``)."""
    return len({int(p["gid"]) for p in packets
                if p.get("type") == "entity_appear" and p.get("job") == job})  # fmt: skip


def arm_score(
    runs: Sequence[Mapping[str, Any]], table: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    """PURE: one arm pooled. ``runs``: per run {"judge": ..., "speed": ... | None,
    "refusals": ... | None}; ``table``: econ_items' items by id (str)."""
    hours = sum(float(r["judge"]["hours"]) for r in runs)
    kills = sum(int(r["judge"]["kills"]) for r in runs)
    deaths = sum(int(r["judge"].get("deaths") or 0) for r in runs)
    gross = common = units = 0
    rare: dict[str, int] = {}
    unpriced: set[int] = set()
    for r in runs:
        for it in r["judge"].get("items") or []:
            n = sum(int(it.get(f, 0)) for f in INCOME)
            if not n:
                continue
            units += n
            p = table.get(str(it["item_id"]))
            if p is None:
                unpriced.add(int(it["item_id"]))
                continue
            oc = int(p.get("sell_oc10") or 0)
            gross += n * oc
            if oc < COMMON_MAX:
                common += n * oc
            else:
                name = str(it.get("name") or it["item_id"])
                rare[name] = rare.get(name, 0) + n
    req = sum(int((r.get("refusals") or {}).get("requests") or 0) for r in runs)
    ign = sum(int((r.get("refusals") or {}).get("ignored") or 0) for r in runs)
    d1 = [(r.get("speed") or {}).get("gpu_ms_p95") for r in runs]
    mvp = [r.get("mvp") for r in runs]
    per = (lambda x: round(x / hours, 1)) if hours > 0 else (lambda x: None)  # noqa: E731
    return {
        "runs": len(runs), "hours": round(hours, 4), "kills": kills, "deaths": deaths,
        "kills_h": per(kills), "gross_oc_h": per(gross), "common_h": per(common),
        "items_h": per(units), "rare": dict(sorted(rare.items())), "unpriced": sorted(unpriced),
        "w1": None if not req else round(ign / req, 4), "w1_counts": [ign, req],
        "d1_p95": d1, "mvp_seen": mvp, "deaths_by_run": [int(r["judge"].get("deaths") or 0)
                                                          for r in runs],
    }  # fmt: skip


def decide(
    b: Mapping[str, Any], a: Mapping[str, Any], min_gain: float = 0.03, min_runs: int = 4
) -> dict[str, Any]:
    """PURE: 4DD's decision of arm ``b`` against arm ``a``: JOIN (every bar passes), FLAG, or
    NO_VERDICT (an arm with fewer than ``min_runs`` runs, or a number missing)."""
    if b["runs"] < min_runs or a["runs"] < min_runs:
        return {"verdict": "NO_VERDICT", "why": f"fewer than {min_runs} runs in an arm"}
    need = ("kills_h", "common_h")
    if any(x[k] is None for x in (a, b) for k in need):
        return {"verdict": "NO_VERDICT", "why": "a pooled number is missing"}
    d1s = [v for v in list(a["d1_p95"]) + list(b["d1_p95"]) if v is not None]
    bars = {
        "D1_kills_h": b["kills_h"] >= a["kills_h"] * (1 + min_gain),
        "D2_common_h": b["common_h"] >= a["common_h"],
        "harm_deaths": b["deaths"] <= a["deaths"],
        "harm_w1": b["w1"] is not None and b["w1"] <= W1_MAX,
        "harm_d1_p95": len(d1s) == a["runs"] + b["runs"] and all(v <= D1_MAX_MS for v in d1s),
    }
    return {
        "verdict": "JOIN" if all(bars.values()) else "FLAG",
        "bars": bars,
        "kills_h_gain": round(b["kills_h"] / a["kills_h"] - 1, 4) if a["kills_h"] else None,
        "kills_h_bar": round(a["kills_h"] * (1 + min_gain), 2),
    }


def load_run(d: Path, demo_roots: Sequence[Path] = ()) -> dict[str, Any]:
    def opt(name: str) -> Any:
        f = d / name
        return json.loads(f.read_text()) if f.exists() else None

    judge = json.loads((d / "judge.json").read_text())
    mvp = None  # 4DI: from the session's own packets, when its directory is found
    sid = judge.get("session")
    for root in demo_roots:
        pk = root / str(sid) / "packets.jsonl.gz"
        if sid and pk.exists():
            with gzip.open(pk, "rt") as fh:
                mvp = mvp_sightings([json.loads(x) for x in fh if '"entity_appear"' in x])
            break
    return {"dir": str(d), "judge": judge, "speed": opt("speed.json"),
            "refusals": opt("refusals.json"), "mvp": mvp}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arm", action="append", required=True, metavar="NAME=DIR,DIR,...")
    ap.add_argument("--decide", default=None, metavar="B:A")
    ap.add_argument("--min-gain", type=float, default=0.03)
    ap.add_argument("--min-runs", type=int, default=4)
    ap.add_argument("--demo-root", action="append", type=Path, default=None,
                    help="where the sessions are (for the MVP sightings); default "
                    "/dev/shm/poring-lab-demo")  # fmt: skip
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import econ_items

    t = econ_items.load()
    table = t.get("items", t)
    arms: dict[str, dict[str, Any]] = {}
    for spec in a.arm:
        name, _, dirs = spec.partition("=")
        if not name or not dirs:
            ap.error(f"--arm {spec!r}: want NAME=DIR,DIR,...")
        roots = a.demo_root or [Path("/dev/shm/poring-lab-demo")]
        runs = [load_run(Path(x), roots) for x in dirs.split(",") if x]
        arms[name] = arm_score(runs, table)
        print(json.dumps({"arm": name, **arms[name]}))
    if a.decide:
        b, _, base = a.decide.partition(":")
        if b not in arms or base not in arms:
            ap.error(f"--decide {a.decide!r}: both arms must be given")
        got = decide(arms[b], arms[base], a.min_gain, a.min_runs)
        print(json.dumps({"decide": a.decide, **got}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
