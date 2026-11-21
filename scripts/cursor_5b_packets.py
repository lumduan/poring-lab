#!/usr/bin/env python3
"""cursor-1080.md 5b (Amendment 8 and 9's packet measures; REPORTED, they decide nothing): what each
box strike click became, from the lab's own packets (packets.jsonl.gz in every hunt core; the
sniffer's t_mono_ns and the runner's t_ns share the host's CLOCK_MONOTONIC).

Per box strike (the runner's ``strike`` event, ``by: box``; its t_ns is the hover's start: the
cursor check, then the click), in its window -- until the next box strike, at most WINDOW_S:
  - "attacked": an attack request came. Most come after ONE walk request: the client walks her into
    range itself, then asks the attack (the 1080 pilots: a median ~1.1 s after the hover's start,
    0.35 s at the fastest = the cursor wait);
  - "walked": walk requests and no attack request: the click met the ground (a stale box's cost);
  - "none": neither.
  - the time from the box (the newest world detection before the hover) to the attack request.

    cursor_5b_packets.py [--arm A=c5b-A1+c5b-A2+c5b-A3 ...] [--json]
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

WINDOW_S = 6.0
ATTACK, WALK = "attack_request", "self_move_request"


def strike_fates(strikes: Sequence[Mapping[str, Any]], attacks: Sequence[int],
                 walks: Sequence[int], det: Sequence[int]) -> dict[str, Any]:  # fmt: skip
    """PURE: the box strikes' fates (request and detection times sorted, ns)."""
    box = sorted(int(e["t_ns"]) for e in strikes
                 if e.get("kind") == "strike" and e.get("by") == "box"
                 and isinstance(e.get("t_ns"), int))  # fmt: skip
    fate = {"attacked": 0, "walked": 0, "none": 0}
    lost_walks = 0
    hover_to_attack: list[float] = []
    box_to_attack: list[float] = []
    for j, t in enumerate(box):
        end = t + int(WINDOW_S * 1e9)
        if j + 1 < len(box):
            end = min(end, box[j + 1])
        ia = bisect.bisect_left(attacks, t)
        ta = attacks[ia] if ia < len(attacks) and attacks[ia] < end else None
        nw = bisect.bisect_left(walks, end) - bisect.bisect_left(walks, t)
        if ta is not None:
            fate["attacked"] += 1
            hover_to_attack.append((ta - t) / 1e9)
            i = bisect.bisect_right(det, t) - 1
            if i >= 0:
                box_to_attack.append((ta - det[i]) / 1e9)
        elif nw:
            fate["walked"] += 1
            lost_walks += nw
        else:
            fate["none"] += 1
    n = len(box)

    def qs(xs: list[float]) -> dict[str, Any]:
        xs = sorted(xs)

        def q(p: float) -> float | None:
            return round(xs[min(len(xs) - 1, int(p * len(xs)))], 3) if xs else None

        return {"n": len(xs), "p50": q(0.5), "p90": q(0.9),
                "mean": round(statistics.fmean(xs), 3) if xs else None}  # fmt: skip

    return {
        "strikes": n, **fate,
        "attack_share": round(fate["attacked"] / n, 3) if n else None,
        "walk_share": round(fate["walked"] / n, 3) if n else None,
        "walks_without_attack": lost_walks,
        "hover_to_attack_s": qs(hover_to_attack), "box_to_attack_s": qs(box_to_attack),
    }  # fmt: skip


def merge(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the counts summed over runs (the shares and times recomputed by the caller's raw)."""
    keys = ("strikes", "attacked", "walked", "none", "walks_without_attack")
    out = {k: sum(int(p.get(k) or 0) for p in parts) for k in keys}
    n = out["strikes"]
    out["attack_share"] = round(out["attacked"] / n, 3) if n else None
    out["walk_share"] = round(out["walked"] / n, 3) if n else None
    return out


def session_fates(d: Path) -> dict[str, Any] | None:
    pk = d / "packets.jsonl.gz"
    if not pk.is_file():
        return None
    attacks, walks = [], []
    with gzip.open(pk, "rt", errors="replace") as fh:
        for ln in fh:
            try:
                p = json.loads(ln)
            except ValueError:
                continue
            t = p.get("t_mono_ns")
            if isinstance(t, int):
                if p.get("type") == ATTACK:
                    attacks.append(t)
                elif p.get("type") == WALK:
                    walks.append(t)
    ev, det = [], []
    for name, sink in (("events.jsonl", ev), ("detections.jsonl", det)):
        f = d / name
        if f.is_file():
            for ln in f.read_text(errors="replace").splitlines():
                try:
                    x = json.loads(ln)
                except ValueError:
                    continue
                if name == "events.jsonl" and x.get("kind") == "strike":
                    sink.append(x)
                elif name == "detections.jsonl" and isinstance(x.get("t_ns"), int):
                    sink.append(x["t_ns"])
    return strike_fates(ev, sorted(attacks), sorted(walks), sorted(det))


def main(argv: Sequence[str] | None = None) -> int:
    import cursor_5b_score as c5
    import stage2_ab as s2

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--arm", action="append", default=[], metavar="X=L1+L2+L3")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    arms = {k: list(v) for k, v in c5.DEFAULT.items()}
    for it in a.arm:
        k, _, v = it.partition("=")
        arms[k] = v.split("+")
    out: dict[str, Any] = {}
    for arm, labels in arms.items():
        parts = []
        for lab in labels:
            for d in sorted(s2.DEMO.glob(f"*-{lab}-r01B-hunt*")):
                got = session_fates(d)
                if got is not None:
                    parts.append({"session": d.name, **got})
        out[arm] = {"runs": parts, "all": merge(parts)}
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        for arm, v in out.items():
            print(
                arm,
                json.dumps(v["all"]),
                "box->attack p50 by run",
                [p["box_to_attack_s"]["p50"] for p in v["runs"]],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
