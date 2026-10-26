#!/usr/bin/env python3
"""THE LIVE DETECTOR AGAINST THE PACKET TRUTH, on a human demo (docs/planning/gef10-round2.md 4).

    detector_vs_packets.py score DEMO_DIR [--map gef_fild10] [--layout hunt] [--window-s 898]
                                 --out JSON [--pairs PAIRS.json]

A human demo (scripts/human_demo.py) logs the CPU unit detector's boxes on fresh grabs
(``boxes.jsonl``: {"t": capture CLOCK_MONOTONIC ns, "ms": inference ms, "boxes": [[x0, y0, x1,
y1, conf, cls], ...]}, game-region px) and the packets (``packets.jsonl.gz``, the same clock).
At each logged capture time t this scores the detector's ``monster`` boxes against the monsters
the packets put on screen, projected exactly as scripts/mvp_watch_study.py ``truth`` does
(``truth_row``: the Timeline at t - 1d, 1d = 120 ms, predict_sprite's box, k 0.14, the RDP
camera, labels_for_v1's in-view rule with the layout's UI rectangles).

- RECALL: the truth boxes IN VIEW whose box contains the centre of a detector ``monster`` box
  (any detection: a box can serve two overlapping units), per species, by the Chebyshev distance
  from our character (cells, rounded: 0-5, 6-10, 11-15, 16+), by the unit's state and by whether
  our character moved in the 500 ms before tw. A ONE-TO-ONE recall (each detection serves one
  unit, nearest centre first: label_iou.match_position's rule) is reported beside it.
- PRECISION: the ``monster`` boxes whose centre lies in SOME monster's predicted box (in view or
  not). The rest are split into: on a unit in its die animation, on our own character (labels
  v2's self box, 34 x 74 + 4 px at our projected anchor), elsewhere.
- FIRST SIGHT: per unit episode (consecutive in-view captures, gaps <= 2 s), whether and how long
  after it came into view the detector first hit it, and its distance then.
- LATENCY: the ``ms`` field (the detector's inference time), median / p95.

Captures are scored only on the map, outside 5 s after a map change and 2 s after a GM command
(mvp_watch_study.frame_flags). OFFLINE ONLY (ADR-0007: packets are ground truth, never an input at
decision time): no frame, no client, no GPU, no input. Reads the decoded sprites and the GAT
(client-derived, /dev/shm only) and the local KB (data/kb, never committed).
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Box = tuple[float, float, float, float]
MAIN = Path("/home/batt/docker/poring-lab")
SPECIES = {1273: "Orc Lady", 1023: "Orc Warrior", 1031: "Poporing", 1686: "Orc Baby"}
DIST_BINS = ((0, 5, "0-5"), (6, 10, "6-10"), (11, 15, "11-15"), (16, 10**6, "16+"))
SELF_MOVE_NS = 500_000_000  # our character moved in the 500 ms before tw: "moving"
EPISODE_GAP_NS = 2_000_000_000  # first sight: a unit's in-view captures this close are one episode
SKIP_FLAGS = ("settle", "gm")  # mvp_watch_study.frame_flags: a map change's settle, a GM command
NEAR_PX = 16.0  # a false detection whose centre lies this close to a unit's box: "near_unit"
CONF_STEPS = (0.25, 0.4, 0.5, 0.6)  # REPORTED: recall / precision with the boxes >= each conf
HUNT_CHAT = (0, 532, 600, 626)  # client_layout.RECTS["hunt"]'s chat window (game-region px)


# --- pure parts -------------------------------------------------------------------------------


def centre(b: Sequence[float]) -> tuple[float, float]:
    return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0


def contains(box: Sequence[float], pt: tuple[float, float]) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def dist_bin(d: float) -> str:
    """The distance bin of ``d`` cells (Chebyshev, rounded half up)."""
    r = int(np.floor(d + 0.5))
    for lo, hi, name in DIST_BINS:
        if lo <= r <= hi:
            return name
    raise ValueError(d)


def chebyshev(a: Sequence[float], b: Sequence[float]) -> float:
    return max(abs(float(a[0]) - float(b[0])), abs(float(a[1]) - float(b[1])))


def one_to_one(truth: Sequence[Sequence[float]], dets: Sequence[Sequence[float]]) -> set[int]:
    """The truth indices matched ONE-TO-ONE: a pair when the detection's centre lies inside the
    truth box, greedily by ascending centre distance (label_iou.match_position's rule)."""
    pairs = []
    for i, t in enumerate(truth):
        tc = centre(t)
        for j, d in enumerate(dets):
            dc = centre(d)
            if contains(t, dc):
                pairs.append((((dc[0] - tc[0]) ** 2 + (dc[1] - tc[1]) ** 2) ** 0.5, i, j))
    used_t: set[int] = set()
    used_d: set[int] = set()
    for _d, i, j in sorted(pairs):
        if i not in used_t and j not in used_d:
            used_t.add(i)
            used_d.add(j)
    return used_t


def score_capture(units: Sequence[dict[str, Any]], dets: Sequence[Sequence[float]],
                  dying: Sequence[Box] = (), self_box: Box | None = None,
                  ) -> tuple[list[dict[str, Any]], list[str]]:  # fmt: skip
    """PURE: one capture. ``units``: truth_row's units (``box`` None: no sheet). Returns (the
    in-view units, each with ``hit`` (any detection's centre in its box) and ``hit_1to1``), and
    one verdict per detection: ``tp`` (in some unit's box, in view or not), else ``dying``,
    ``self``, ``near_unit`` (within NEAR_PX of a unit's box) or ``other``)."""
    view = [u for u in units if u.get("box") is not None and u.get("in_view")]
    boxed = [u["box"] for u in units if u.get("box") is not None]
    centres = [centre(d) for d in dets]
    matched = one_to_one([u["box"] for u in view], dets)
    out = [{**u, "hit": any(contains(u["box"], c) for c in centres), "hit_1to1": i in matched}
           for i, u in enumerate(view)]  # fmt: skip
    verdicts = []
    for c in centres:
        if any(contains(b, c) for b in boxed):
            verdicts.append("tp")
        elif any(contains(b, c) for b in dying):
            verdicts.append("dying")
        elif self_box is not None and contains(self_box, c):
            verdicts.append("self")
        elif any(contains((b[0] - NEAR_PX, b[1] - NEAR_PX, b[2] + NEAR_PX, b[3] + NEAR_PX), c)
                 for b in boxed):  # fmt: skip
            verdicts.append("near_unit")
        else:
            verdicts.append("other")
    return out, verdicts


def rate(hits: int, n: int) -> float | None:
    return round(hits / n, 3) if n else None


def tally(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: recall of in-view unit rows (``hit``, ``hit_1to1``)."""
    n = len(rows)
    h = sum(1 for r in rows if r["hit"])
    h1 = sum(1 for r in rows if r["hit_1to1"])
    return {"n": n, "hit": h, "recall": rate(h, n), "hit_1to1": h1, "recall_1to1": rate(h1, n)}


def species_key(job: int) -> str:
    return f"{job} {SPECIES[job]}" if job in SPECIES else "other"


def episodes(rows: Sequence[dict[str, Any]], gap_ns: int = EPISODE_GAP_NS
             ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: per gid, its in-view rows (t, hit, dist, job) cut into episodes at gaps > ``gap_ns``:
    first in-view t, first hit t (None: never hit), the distance at the first in-view row."""
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["gid"], r["t"])):
        by[int(r["gid"])].append(r)
    out = []
    for gid, rs in by.items():
        cur: list[dict[str, Any]] = []
        for r in [*rs, None]:
            if cur and (r is None or r["t"] - cur[-1]["t"] > gap_ns):
                first_hit = next((x["t"] for x in cur if x["hit"]), None)
                out.append({"gid": gid, "job": cur[0]["job"], "t0": cur[0]["t"],
                            "t1": cur[-1]["t"], "captures": len(cur),
                            "dist0": cur[0]["dist"], "first_hit": first_hit,
                            "delay_s": None if first_hit is None
                            else round((first_hit - cur[0]["t"]) / 1e9, 3)})  # fmt: skip
                cur = []
            if r is not None:
                cur.append(r)
    return out


def percentile(values: Sequence[float], q: float) -> float | None:
    return round(float(np.percentile(np.asarray(values, float), q)), 1) if values else None


# --- the session ------------------------------------------------------------------------------


def read_boxes(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cmd_score(a: argparse.Namespace) -> dict[str, Any]:
    import gef10_items
    import mvp_watch_study as mws

    from poring_dataset.camera import map_key
    from poring_dataset.render import Actor, MonsterAction, anchor_and_depth, load_scene
    from poring_dataset.render import predict_sprite as predict

    demo: Path = a.demo
    manifest = json.loads((demo / "manifest.json").read_text())
    t0 = int(manifest["t0_live_ns"])
    t1 = t0 + int(a.window_s * 1e9)
    caps = read_boxes(demo / "boxes.jsonl")
    win = [c for c in caps if t0 <= int(c["t"]) <= t1]
    with gzip.open(demo / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    size = (1280, 720)
    stack = mws.truth_stack(events, a.layout, size, kb=a.kb, mapcache_dir=a.mapcache_dir)
    if a.chat_rect is not None:  # the demo's chat window was dragged (measured on its frames)
        new = tuple(int(v) for v in a.chat_rect.split(","))
        if a.layout != "hunt" or len(new) != 4:
            raise SystemExit("--chat-rect X0,Y0,X1,Y1 replaces the hunt layout's chat window")
        stack.rects = tuple(new if tuple(r) == HUNT_CHAT else tuple(r) for r in stack.rects)
    by_conf = {c: {"hit": 0, "n": 0, "tp": 0, "dets": 0} for c in CONF_STEPS}
    off_ns = int(mws.OFFSET_MS * 1e6)
    skipped: Counter[str] = Counter()
    unit_rows: list[dict[str, Any]] = []
    verdicts: Counter[str] = Counter()
    det_species: Counter[str] = Counter()
    frames_any_view = frames_view_none = 0
    no_sheet: Counter[int] = Counter()
    pairs = []
    for c in win:
        t = int(c["t"])
        row = mws.truth_row(stack, t, None, mws.OFFSET_MS, a.map)
        if not row["map"] or map_key(row["map"]) != a.map or row["self"] is None:
            skipped["off_map"] += 1
            continue
        if any(f in row["flags"] for f in SKIP_FLAGS):
            skipped["flag:" + "+".join(f for f in row["flags"] if f in SKIP_FLAGS)] += 1
            continue
        tw = t - off_ns
        scene = load_scene(stack.camera, row["map"], row["self"], indoor_table=stack.indoor)
        me = anchor_and_depth(scene, (float(row["self"][0]), float(row["self"][1])))[0]
        sbox = gef10_items.self_box(me)
        dying: list[Box] = []
        for st in stack.tl.states(tw):
            sh = None if st.state != "dying" or st.job is None else stack.sheets(st.job)
            if sh is None:
                continue
            act = Actor((float(st.x), float(st.y)), int(st.facing or 0), MonsterAction.DIE,
                        elapsed_ms=st.elapsed_ms, duration_ms=st.duration_ms)  # fmt: skip
            p = predict(act, sh, scene, mws.K)
            if p is not None:
                dying.append(tuple(float(v) for v in p.box))  # type: ignore[arg-type]
        dets = [b[:4] for b in c["boxes"] if b[5] == "monster"]
        for u in row["units"]:
            if u.get("box") is None:
                no_sheet[int(u["job"])] += 1
        scored, vs = score_capture(row["units"], dets, dying, sbox)
        verdicts.update(vs)
        for cf in CONF_STEPS:
            keep = [b[:4] for b in c["boxes"] if b[5] == "monster" and float(b[4]) >= cf]
            sc, vc = score_capture(row["units"], keep, dying, sbox)
            acc = by_conf[cf]
            acc["n"] += len(sc)
            acc["hit"] += sum(1 for u in sc if u["hit"])
            acc["dets"] += len(vc)
            acc["tp"] += vc.count("tp")
        for d, v in zip(dets, vs, strict=True):
            if v == "tp":
                dc = centre(d)
                hit = [u for u in row["units"] if u.get("box") is not None
                       and contains(u["box"], dc)]  # fmt: skip
                det_species[species_key(int(hit[0]["job"]))] += 1
        before = stack.tl.frame_world(tw - SELF_MOVE_NS).self_pos
        moving = before != row["self"]
        if scored:
            frames_any_view += 1
            if not dets:
                frames_view_none += 1
        for u in scored:
            unit_rows.append({"t": t, "gid": int(u["gid"]), "job": int(u["job"]),
                              "state": u["state"], "hit": u["hit"], "hit_1to1": u["hit_1to1"],
                              "dist": round(chebyshev(u["cell"], row["self"]), 2),
                              "moving": moving})  # fmt: skip
        if a.pairs is not None:
            pairs.append({"t": t, "self": row["self"], "moving": moving, "dets": c["boxes"],
                          "verdicts": vs, "units": scored, "dying": dying,
                          "self_box": sbox})  # fmt: skip
    per_species: dict[str, Any] = {}
    for key in [*(species_key(j) for j in SPECIES), "other"]:
        rs = [r for r in unit_rows if species_key(r["job"]) == key]
        per_species[key] = {**tally(rs), "by_distance": {
            name: tally([r for r in rs if dist_bin(r["dist"]) == name]) for *_x, name in DIST_BINS},
            "jobs": dict(Counter(str(r["job"]) for r in rs))}  # fmt: skip
    eps = episodes(unit_rows)
    delays = [e["delay_s"] for e in eps if e["delay_s"] is not None]
    ms_all = [float(c["ms"]) for c in win]
    n_det = sum(verdicts.values())
    return {
        "what": "the live detector's monster boxes (boxes.jsonl) against the packet truth "
                "(mvp_watch_study.truth_row) at each logged capture time",
        "demo": manifest["session_id"], "map": a.map, "layout": a.layout,
        "window": {"t0_live_ns": t0, "seconds": a.window_s, "captures_logged": len(caps),
                   "captures_in_window": len(win), "skipped": dict(skipped),
                   "captures_scored": len(win) - sum(skipped.values())},
        "offset_ms": mws.OFFSET_MS, "k": mws.K,
        "latency_ms": {"n": len(ms_all), "median": percentile(ms_all, 50),
                       "p95": percentile(ms_all, 95), "max": max(ms_all) if ms_all else None},
        "recall_all": tally(unit_rows),
        "per_species": per_species,
        "by_distance": {name: tally([r for r in unit_rows if dist_bin(r["dist"]) == name])
                        for *_x, name in DIST_BINS},
        "by_state": {s: tally([r for r in unit_rows if r["state"] == s])
                     for s in sorted({str(r["state"]) for r in unit_rows})},
        "by_self_motion": {k: tally([r for r in unit_rows if r["moving"] is v])
                           for k, v in (("moving", True), ("still", False))},
        "precision": {"detections": n_det, "tp": verdicts.get("tp", 0),
                      "precision": rate(verdicts.get("tp", 0), n_det),
                      "fp_on_dying_unit": verdicts.get("dying", 0),
                      "fp_on_self": verdicts.get("self", 0),
                      "fp_near_a_unit_16px": verdicts.get("near_unit", 0),
                      "fp_elsewhere": verdicts.get("other", 0),
                      "tp_by_species": dict(det_species)},
        "by_conf": {str(cf): {"recall": rate(v["hit"], v["n"]),
                              "precision": rate(v["tp"], v["dets"]), **v}
                    for cf, v in by_conf.items()},
        "ui_rects": [list(r) for r in stack.rects],
        "frames": {"with_a_monster_in_view": frames_any_view,
                   "of_them_no_detection_at_all": frames_view_none},
        "first_sight": {"episodes": len(eps), "detected": len(delays),
                        "never_detected": len(eps) - len(delays),
                        "delay_s_median": round(statistics.median(delays), 2) if delays else None,
                        "delay_s_p90": percentile(delays, 90),
                        "by_first_distance": {name: {
                            "episodes": sum(1 for e in eps if dist_bin(e["dist0"]) == name),
                            "detected": sum(1 for e in eps if dist_bin(e["dist0"]) == name
                                            and e["delay_s"] is not None)}
                            for *_x, name in DIST_BINS}},
        "no_sheet_units": {str(k): v for k, v in sorted(no_sheet.items())},
        "missing_sheets": {str(k): v for k, v in stack.sheets.missing.items()},
        "_pairs": pairs if a.pairs is not None else None,
    }  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("score")
    p.add_argument("demo", type=Path)
    p.add_argument("--map", default="gef_fild10")
    p.add_argument("--layout", choices=("standard", "hunt"), default="hunt")
    p.add_argument("--window-s", type=float, default=898.0)
    p.add_argument("--kb", type=Path, default=MAIN / "data" / "kb")
    p.add_argument(
        "--mapcache-dir",
        type=Path,
        default=MAIN / "packages/poring_dataset/src/poring_dataset/_generated",
    )
    p.add_argument("--pairs", type=Path, default=None, help="every scored capture (by-eye)")
    p.add_argument(
        "--chat-rect",
        default=None,
        help="X0,Y0,X1,Y1: the chat window where the demo had it (hunt layout)",
    )
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    out = cmd_score(a)
    pairs = out.pop("_pairs")
    if a.pairs is not None:
        a.pairs.write_text(json.dumps(pairs) + "\n")
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
