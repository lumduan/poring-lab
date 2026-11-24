"""item_tally_check.py LABEL: econ-bag-count.md Amendment 9's check of the item tally on the dev
client, scored ONCE after the run (written and committed before it).

One screen_ab run LABEL (its series with the Run's bag count ON: the tally starts only after the
start count). Its records:
  - the player's own folder /dev/shm/poring-lab-demo/<time>-play-<LABEL>-r01B (events.jsonl): the
    tally's records (item_gained, items_tally, items_adjust) and the census records;
  - the hunt core folder(s) <time>-...-<LABEL>-r01B-hunt<N> (packets.jsonl.gz): the truth -- each
    successful inventory gain (pickup_result ok: item_id, amount, t_mono_ns -- the host's
    CLOCK_MONOTONIC, the records' t_ns clock), as dungeon_judge.item_gains reads them;
  - screen_ab's record of the run (/dev/shm/poring-lab-tmp/screen-ab/<LABEL>): how it ended
    (series.log) and the Run's own lines (<LABEL>-r01B.log: the tally's start / stop lines).

PLUMBING conditions (Amendment 9; all must hold -> PASS, else FAIL):
  P1 the run played to its time box: play rc 0 (series.log "ended rc 0"), no error;
  P2 the tally started (no "item tally is off" / "did not start" / "stopped early" line) and wrote
     >= 1 item_gained while the packets show >= 1 gain in its window (a positive case);
  P3 the tally's totals were recorded at the end (items_tally), and items_adjust when both counts
     read.
REPORTED, not judged (the reader's own accuracy bar at 1080 is item-popup-reader.md's round 5):
  each packet gain matched to the nearest unmatched tally gain with the same item id among its ids,
  from 1.0 s before to 3.0 s after it: recall (packet gains matched / packet gains in the tally's
  window), precision (tally gains with an item matched / tally gains with an item), amounts equal
  of matched, tally gains whose item did not read, the totals (tally count vs packet amount), and
  the end count's adjustment; the median lag (tally - packet) of matched gains.
Writes /dev/shm/poring-lab-tmp/item-tally/check-<LABEL>.json and prints it. Read-only otherwise.
Run from the repo root with the main .venv.
"""

from __future__ import annotations

import gzip
import json
import statistics
import sys
from pathlib import Path

DEMO = Path("/dev/shm/poring-lab-demo")
SA = Path("/dev/shm/poring-lab-tmp/screen-ab")
OUT = Path("/dev/shm/poring-lab-tmp/item-tally")
NS = 10**9
BEFORE_S, AFTER_S = 1.0, 3.0
BAD_LINES = ("item tally is off", "item tally did not start", "item tally stopped early")


def jsonl(p: Path) -> list[dict]:
    op = gzip.open if p.suffix == ".gz" else open
    with op(p, "rt") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def main() -> int:
    label = sys.argv[1]
    run = f"-{label}-r01B"
    dirs = [p for p in DEMO.iterdir() if p.is_dir()]
    play = sorted(p for p in dirs if p.name.endswith(f"-play{run}"))
    hunts = sorted(
        p for p in dirs if "-hunt" in p.name and p.name.rsplit("-hunt", 1)[0].endswith(run)
    )
    assert len(play) == 1 and hunts, (play, hunts)
    ev = jsonl(play[0] / "events.jsonl")
    gains = [e for e in ev if e.get("kind") == "item_gained"]
    totals = [e for e in ev if e.get("kind") == "items_tally"]
    adjust = [e for e in ev if e.get("kind") == "items_adjust"]
    says = (SA / label / f"{label}-r01B.log").read_text().splitlines()
    bad = [s for s in says if any(b in s for b in BAD_LINES)]
    started = any("the item tally: each item popup is counted" in s for s in says)
    series = (SA / label / "series.log").read_text()
    rc0 = f"{label}-r01B ended rc 0" in series
    # the window: the hunt core's start (after the start count and the tally's start) .. the
    # tally's totals (it stops before the end count; else the player's last record)
    t0 = min(int(e["t_ns"]) for h in hunts for e in jsonl(h / "events.jsonl")
             if e.get("kind") == "run_start")  # fmt: skip
    t_end = int(totals[-1]["t_ns"]) if totals else int(ev[-1]["t_ns"])
    pk = [e for h in hunts for e in jsonl(h / "packets.jsonl.gz")
          if e.get("type") == "pickup_result" and e.get("ok")]  # fmt: skip
    truth = sorted((int(e["t_mono_ns"]), int(e.get("item_id") or 0), int(e.get("amount") or 1))
                   for e in pk if t0 <= int(e["t_mono_ns"]) <= t_end)  # fmt: skip
    keyed = [g for g in gains if g.get("key")]
    used: set[int] = set()
    matched: list[tuple[tuple[int, int, int], dict]] = []
    for t, item, amount in truth:
        best = None
        for i, g in enumerate(keyed):
            if i in used or item not in (g.get("ids") or []):
                continue
            d = (int(g["t_ns"]) - t) / NS
            if -BEFORE_S <= d <= AFTER_S and (best is None or abs(d) < abs(best[1])):
                best = (i, d)
        if best is not None:
            used.add(best[0])
            matched.append(((t, item, amount), keyed[best[0]]))
    lags = [(int(g["t_ns"]) - t) / NS for (t, _i, _a), g in matched]
    doc = {
        "check": "econ-bag-count.md Amendment 9",
        "label": label,
        "play": play[0].name,
        "hunts": [h.name for h in hunts],
        "P1_rc0": rc0,
        "P2_started": started and not bad and bool(gains) and bool(truth),
        "P2_bad_lines": bad,
        "P3_totals": bool(totals),
        "P3_adjust": bool(adjust) or "no items_adjust (a count did not read)",
        "tally_gains": len(gains),
        "tally_gains_item_unread": len(gains) - len(keyed),
        "packet_gains": len(truth),
        "matched": len(matched),
        "recall": round(len(matched) / len(truth), 3) if truth else None,
        "precision": round(len(matched) / len(keyed), 3) if keyed else None,
        "amounts_equal": sum(1 for (_t, _i, a), g in matched if g.get("amount") == a),
        "amounts_unread": sum(1 for _m, g in matched if g.get("amount") is None),
        "tally_total": int(totals[-1].get("total") or 0) if totals else None,
        "packet_total": sum(a for _t, _i, a in truth),
        "lag_s_median": round(statistics.median(lags), 2) if lags else None,
        "unmatched_packet": [
            [round((t - t0) / NS, 1), i, a]
            for (t, i, a) in truth
            if not any(m[0] == (t, i, a) for m in matched)
        ][:40],
        "unmatched_tally": [
            [round((int(g["t_ns"]) - t0) / NS, 1), g.get("key"), g.get("amount")]
            for k, g in enumerate(keyed)
            if k not in used
        ][:40],
        "adjust": adjust[-1] if adjust else None,
    }
    doc["verdict"] = ("PASS" if doc["P1_rc0"] and doc["P2_started"] and doc["P3_totals"]
                      else "FAIL")  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"check-{label}.json").write_text(json.dumps(doc, indent=1, default=str))
    print(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
