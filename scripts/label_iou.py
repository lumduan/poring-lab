#!/usr/bin/env python3
"""B6: score the auto-labels against Batt's hand-checked set (Post-S2 round Part D, 2026-10-04).

    label_iou.py pin SESSION                     the hand-check -> the NAS session, pinned
    label_iou.py score SESSION [--update-bench]  auto-labels vs the hand-check, per class

* The hand-check is what the /qa editor saved through the backend: data/qa/handcheck/<SESSION>.json
  (boxes in game-region pixels; every reviewed frame is "accepted" or "edited").
* pin: copies it into the shipped session on the NAS as handcheck.json, reads it back by sha256,
  and pins the session (dataset_ship.py pin --reason handcheck): a hand-labelled set is never
  pruned.
* score: re-derives the auto-labels for the SAME frames with qa_export's Labeler (the same camera,
  indoor rule, offset and filters as the bundle the human saw), then metrics.match(truth,
  predicted, IoU >= 0.5) per class -> precision, recall, mean IoU, and overall. Frames inside a GM
  window have no auto-labels and are skipped (counted).
* --update-bench: writes the overall mean IoU (and the per-class detail) as `label_iou` into the
  NEWEST benchmark run of the same backend + client + paint path (qa_export's rule) and regenerates
  the running table (bench.py table).

The session is read from the NAS (--datasets) or a local recording root (--root).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dataset_ship  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.metrics import Box, match  # noqa: E402

HANDCHECK = ROOT / "data" / "qa" / "handcheck"
BENCH = ROOT / "docs" / "benchmarks"
CLASSES = ("player", "monster", "npc")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_session(name: str, datasets: Path, root: Path) -> Path:
    for base in (datasets, root):
        if (base / name / "manifest.json").exists():
            return base / name
    raise SystemExit(f"no session {name} under {datasets} or {root}")


def cmd_pin(a: argparse.Namespace) -> int:
    src = HANDCHECK / f"{a.session}.json"
    if not src.exists():
        raise SystemExit(f"no hand-check saved for {a.session} ({src})")
    session = a.datasets / a.session
    if not (session / "manifest.json").exists():
        raise SystemExit(f"{a.session} is not shipped to {a.datasets} yet")
    dst = session / "handcheck.json"
    tmp = session / ".handcheck.json.tmp"
    tmp.write_bytes(src.read_bytes())
    tmp.replace(dst)
    if sha256(dst) != sha256(src):
        raise SystemExit("the NAS copy did not read back identical")
    rc = dataset_ship.main(["pin", a.session, "--reason", "handcheck", "--dest", str(a.datasets)])
    print(json.dumps({"pinned": a.session, "sha256": sha256(dst), "dataset_ship": rc}))
    return rc


def boxes_of(items: list[dict[str, Any]]) -> list[Box]:
    return [(str(b["cls"]), float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"]))
            for b in items]  # fmt: skip


def score(hand: dict[str, Any], auto_for: Any) -> dict[str, Any]:
    """Per class and overall: TP/FP/FN, precision, recall, mean IoU (``auto_for(t)`` -> the
    auto-label dicts of a frame, or None inside a GM window)."""
    per: dict[str, dict[str, Any]] = {c: {"tp": 0, "fp": 0, "fn": 0, "ious": []} for c in CLASSES}
    frames = skipped = 0
    for f in hand["frames"]:
        auto = auto_for(int(f["t_mono_ns"]))
        if auto is None:
            skipped += 1
            continue
        frames += 1
        truth, pred = boxes_of(f["boxes"]), boxes_of(auto)
        for c in CLASSES:
            m = match([b for b in truth if b[0] == c], [b for b in pred if b[0] == c], 0.5)
            per[c]["tp"] += m.tp
            per[c]["fp"] += m.fp
            per[c]["fn"] += m.fn
            per[c]["ious"] += list(m.ious)

    def summary(d: dict[str, Any]) -> dict[str, Any]:
        tp, fp, fn, ious = d["tp"], d["fp"], d["fn"], d["ious"]
        return {"tp": tp, "fp": fp, "fn": fn,
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                "mean_iou": round(sum(ious) / len(ious), 3) if ious else None}  # fmt: skip

    overall = {"tp": 0, "fp": 0, "fn": 0, "ious": []}
    for d in per.values():
        for k in ("tp", "fp", "fn", "ious"):
            overall[k] += d[k]
    return {"frames": frames, "skipped_gm_window": skipped,
            "per_class": {c: summary(d) for c, d in per.items()},
            "overall": summary(overall), "threshold": 0.5}  # fmt: skip


def newest_run(config: dict[str, Any]) -> Path | None:
    want = qa_export.client_key(config)
    best: tuple[str, Path] | None = None
    for path in BENCH.glob("*.json"):
        res = json.loads(path.read_text())
        if "scenes" not in res or qa_export.client_key(res.get("config", {})) != want:
            continue
        started = str(res.get("t_wall_start", ""))
        if best is None or started > best[0]:
            best = (started, path)
    return None if best is None else best[1]


def match_position(truth: list[Box], predicted: list[Box]) -> tuple[int, int, int, list[float]]:
    """POSITION-ONLY match (phase3-plan §5f): a pair is a candidate when the classes match and the
    predicted box's CENTRE lies inside the truth box; one-to-one, greedily by ascending centre
    distance. Returns (tp, fp, fn, the matched centre distances in px)."""

    def centre(b: Box) -> tuple[float, float]:
        return (b[1] + b[3]) / 2.0, (b[2] + b[4]) / 2.0

    pairs = []
    for i, t in enumerate(truth):
        for j, p in enumerate(predicted):
            cx, cy = centre(p)
            if t[0] == p[0] and t[1] <= cx <= t[3] and t[2] <= cy <= t[4]:
                tx, ty = centre(t)
                pairs.append((((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5, i, j))
    used_t: set[int] = set()
    used_p: set[int] = set()
    dists: list[float] = []
    for dist, i, j in sorted(pairs):
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        dists.append(dist)
    return len(dists), len(predicted) - len(dists), len(truth) - len(dists), dists


def score_position(hand: dict[str, Any], auto_for: Any) -> dict[str, Any]:
    """Per class and overall: TP/FP/FN, precision, recall, and the matched centre distances
    (median, p90) of the POSITION-ONLY match (§5f); frames inside a GM window are skipped."""
    per: dict[str, dict[str, Any]] = {c: {"tp": 0, "fp": 0, "fn": 0, "d": []} for c in CLASSES}
    frames = skipped = 0
    for f in hand["frames"]:
        auto = auto_for(int(f["t_mono_ns"]))
        if auto is None:
            skipped += 1
            continue
        frames += 1
        truth, pred = boxes_of(f["boxes"]), boxes_of(auto)
        for c in CLASSES:
            tp, fp, fn, d = match_position([b for b in truth if b[0] == c],
                                           [b for b in pred if b[0] == c])  # fmt: skip
            per[c]["tp"] += tp
            per[c]["fp"] += fp
            per[c]["fn"] += fn
            per[c]["d"] += d

    def summary(d: dict[str, Any]) -> dict[str, Any]:
        tp, fp, fn, dist = d["tp"], d["fp"], d["fn"], sorted(d["d"])
        return {"tp": tp, "fp": fp, "fn": fn,
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                "centre_px_median": round(dist[len(dist) // 2], 2) if dist else None,
                "centre_px_p90": round(dist[min(len(dist) - 1, int(0.9 * len(dist)))], 2)
                if dist else None}  # fmt: skip

    overall = {"tp": 0, "fp": 0, "fn": 0, "d": []}
    for d in per.values():
        for k in ("tp", "fp", "fn", "d"):
            overall[k] += d[k]
    return {"frames": frames, "skipped_gm_window": skipped, "metric": "position",
            "per_class": {c: summary(d) for c, d in per.items()},
            "overall": summary(overall)}  # fmt: skip


def cmd_score(a: argparse.Namespace) -> int:
    path = HANDCHECK / f"{a.session}.json"
    if not path.exists():
        raise SystemExit(f"no hand-check saved for {a.session} ({path})")
    hand = json.loads(path.read_text())
    session = find_session(a.session, a.datasets, a.root)
    lab = qa_export.Labeler(session, a.offset_ms, labels=a.labels,
                            **({"k": a.k} if a.k is not None else {}))  # fmt: skip
    result = {"session": a.session, "handcheck_sha256": sha256(path),
              "camera": lab.camera_path.name, "offset_ms": lab.offset_ms,
              "labels": a.labels, "k": lab.k,
              **(score_position(hand, lab.boxes) if a.metric == "position"
                 else score(hand, lab.boxes))}  # fmt: skip
    if a.update_bench and a.metric == "position":
        raise SystemExit("--update-bench records the IoU metric only")
    if a.update_bench:
        run = newest_run(lab.manifest["config"])
        if run is None:
            raise SystemExit("no benchmark run of this backend + client + paint path")
        res = json.loads(run.read_text())
        # v0 keeps its key (the baseline); v1 gets its own, never overwriting v0's
        res["label_iou" if a.labels == "v0" else f"label_iou_{a.labels}"] = {
            "mean_iou": result["overall"]["mean_iou"], "session": a.session,
            "per_class": result["per_class"], "frames": result["frames"],
        }  # fmt: skip
        run.write_text(json.dumps(res, indent=1) + "\n")
        import bench

        bench.cmd_table()
        result["bench_run"] = run.name
    print(json.dumps(result, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pin", "score"):
        p = sub.add_parser(name)
        p.add_argument("session")
        p.add_argument("--datasets", type=Path, default=dataset_ship.NAS_ROOT)
        p.add_argument("--root", type=Path, default=dataset_ship.LOCAL_ROOT)
        if name == "score":
            p.add_argument("--offset-ms", default="auto")
            p.add_argument("--update-bench", action="store_true")
            p.add_argument("--labels", choices=("v0", "v1"), default="v0")
            p.add_argument("--k", type=float, default=None, help="v1: M4's k (default nostalro)")
            p.add_argument(
                "--metric",
                choices=("iou", "position"),
                default="iou",
                help="position: centre-in-box, one-to-one by distance (§5f)",
            )
    a = ap.parse_args(argv)
    return cmd_pin(a) if a.cmd == "pin" else cmd_score(a)


if __name__ == "__main__":
    sys.exit(main())
