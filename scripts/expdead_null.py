"""3.87's null: how far two arms of the SAME rule drift apart per 4-run pool (offline, packets).

For banked runs (in pools of 4, in the order given), every dead engagement gets its kill -> loot
start time (the kill = the target's death vanish in packets; the loot start = the engagement's end
minus its loot step) and whether its dead call had a real death behind it
(flow_judge.dead_call_truth). Five k splits (parity + 4 balanced) per pool give the range of the
arm difference with no change between the arms.

`--max-min N` keeps only engagements whose first click falls in the run's first N minutes (3.87's
amendment: 4 x 55-min runs).

    PYTHONPATH=scripts:packages/poring_dataset/src .venv/bin/python scripts/expdead_null.py \
        [--max-min 55] SID1 ... SID12
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Callable

import arm_judge as aj
import flow_judge as fj
import search_study as ss

NS = 10**9
SPLITS: dict[str, Callable[[int], bool]] = {
    "parity": lambda k: k % 2 == 1,
    "mod4 12|30": lambda k: k % 4 in (1, 2),
    "mod4 01|23": lambda k: k % 4 in (0, 1),
    "mod8": lambda k: k % 8 < 4,
    "mod6": lambda k: k % 6 < 3,
}


def rows_of(sid: str, max_min: float) -> list[tuple[str, int, float | None, bool | None]]:
    """(sid, k, kill -> loot start s or None, dead call without a real death or None)."""
    s = aj.load(sid)
    van: dict[int, list[int]] = defaultdict(list)
    for e in s["packets"]:
        if e.get("type") == "entity_vanish" and int(e.get("reason", -1)) == 1:
            van[int(e.get("gid") or -1)].append(int(e["t_mono_ns"]))
    sess = ss.load_session(sid)
    with open(f"/dev/shm/poring-lab-demo/{sid}/flow_judge.json") as f:
        fjo = json.load(f)
    truth = fj.dead_call_truth(
        sess.events, sess.engagements, fjo["engagements_w"]["rows"], sess.t0, sess.w1
    )
    out: list[tuple[str, int, float | None, bool | None]] = []
    for x in s["engagements"]:
        if x.get("result") != "dead":
            continue
        if max_min and int(x["t_first_click"]) - sess.t0 > max_min * 60 * NS:
            continue
        k = int(x["k"])
        g = s["gid_by_k"].get(k)
        t_end = int(x.get("t_end") or 0)
        kl = None
        if g is not None:
            t0 = int(x.get("t_last_click") or x["t_first_click"]) - NS
            vs = [t for t in van.get(g, []) if t0 <= t <= t_end + 3 * NS]
            loot = x.get("loot") or {}
            if vs and loot.get("s") is not None and t_end:
                kl = (t_end - vs[0]) / NS - float(loot["s"])
        fd = None if k not in truth else truth[k][0] != "real"
        out.append((sid, k, kl, fd))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-min", type=float, default=0.0)
    ap.add_argument("sids", nargs="+")
    a = ap.parse_args()
    rows = [r for sid in a.sids for r in rows_of(sid, a.max_min)]
    rel_kl, d_fd = [], []
    for i in range(0, len(a.sids), 4):
        pool = [r for r in rows if r[0] in a.sids[i : i + 4]]
        for f in SPLITS.values():
            ka = [r[2] for r in pool if f(r[1]) and r[2] is not None]
            kb = [r[2] for r in pool if not f(r[1]) and r[2] is not None]
            ma, mb = sum(ka) / len(ka), sum(kb) / len(kb)
            rel_kl.append(round((ma - mb) / ((ma + mb) / 2), 3))
            fa = [r[3] for r in pool if f(r[1]) and r[3] is not None]
            fb = [r[3] for r in pool if not f(r[1]) and r[3] is not None]
            d_fd.append(round(sum(fa) / len(fa) / (sum(fb) / len(fb)), 3))
    rel_kl.sort()
    d_fd.sort()
    allk = sorted(r[2] for r in rows if r[2] is not None)
    allf = [r[3] for r in rows if r[3] is not None]
    print(
        "kill -> loot start: pooled mean",
        round(sum(allk) / len(allk), 2),
        "p50",
        round(allk[len(allk) // 2], 2),
        "p90",
        round(allk[int(0.9 * len(allk))], 2),
        "n",
        len(allk),
    )
    print("  arm split rel diff: min", rel_kl[0], "max", rel_kl[-1])
    print(
        "dead calls without a real death: pooled",
        round(sum(allf) / len(allf), 3),
        "; arm ratio min",
        d_fd[0],
        "max",
        d_fd[-1],
    )


if __name__ == "__main__":
    main()
