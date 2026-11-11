#!/usr/bin/env python3
"""The floor-item model's evaluation on the held-out fiT (docs/planning/xmas02-detector.md
Amendment O.9, ACCEPTED by O1 2026-11-10; tool T-O5): the bars I1-I5 from the frozen labels
(scripts/fi_labels.py label --eval-test), their packets' kills and drops (in the same files), the
model's predictions (poring_vision.predict_dir on scripts/fi_labels.py refs) and the blind
labellers' evaluated crops (scripts/fi_blind_score.py --both-good on the seed-63 pack).

    fi_eval.py --labels L1.json L2.json [L3.json] --predictions gpu=PRED.json [onnx=PRED2.json]
               --key KEY.json --evaluated BOTH_GOOD.json
               [--gpu-timing PRED.json] [--cpu-latency LAT.json --cpu-item NAME
               --cpu-deployed NAME] --out JSON

Every bar must pass for EVERY prediction set; a bar with fewer rows than its minimum is NO
VERDICT, never a pass (O.9). A box counts when its class is ``floor_item`` and its conf >= 0.25.
A box MATCHES a target box when their IoU >= 0.3 or the box's centre lies in it. A box's CELL point
is its centre minus the frozen anchor (O.1b: the drawn centre = the projected point + the anchor).

- I1 recall: of the EVALUATED crops (both labellers yes / good), the share with a matching box on
  their frame: >= 0.85 on >= 40 crops. I1 precision: over every box on every judged frame of fiT
  (kept or excluded: "a covered item is not a false box"), TRUE when it matches an item on the
  floor (its label box, else its predicted box; any phase), FALSE when its cell point lies in no
  floor item's 1-cell neighbourhood (the projected +-1.5-cell square), else AMBIGUOUS (reported,
  outside the ratio): TRUE / (TRUE + FALSE) >= 0.85 on >= 40 such boxes.
- I2 per episode: the drops of OUR kills with >= 1 kept-label frame, boxed in their FIRST such
  frame (a box matching the label): >= 0.80 on >= 20 episodes (short: NO VERDICT, fiT3 next; a
  second short count stays NO VERDICT). Beside: the drops on (0,+1) (behind her).
- I3 false items: fiT's kept frames with no floor item in any phase: frames with a box <= 1 / 200
  (>= 200 frames), with a box whose cell point lies in the 5 x 5 around her <= 1 / 500 (>= 500).
- I4 the runner's moments: our kills WITHOUT a drop, the first frame 2.0-3.0 s after the death: a
  box whose cell point lies in the death cell's 3 x 3 in <= 5 % of them (>= 40 kills).
- I5 latency: the GPU call p95 <= 35 ms (predict_dir --timing, >= 200 calls); the CPU ONNX p95 <=
  1.10 x the deployed xmas02gb's in ONE interleaved run (scripts/eval_latency.py, >= 200 each).

ROUND 2 (Amendment O15, 2026-11-10 night; ``--strata r2``, the tests written before any score):
- I1 recall by STRATUM, each >= 0.85: I1a, the AURA (the Base 99 Rogue: the pilots fiT4-fiT6 and
  the near staging fsTa, pooled, >= 40 crops) and I1n, NO AURA (the Base 60 Crusader's near
  staging fsTn, >= 30 crops). Each source's count is reported, and Batt's 95 % beside each
  stratum (a target, not a bar). The pooled I1 recall is reported only.
- I2, I3 and I4 read the pilots (fiT4-fiT6) only; I1 precision reads all five.
- I5 GPU (O14 had no verdict: its call-time harness adds ~35 ms to every model): the detect
  server's forward p95 (scripts/fi_gpu_latency.py, one model a run, the same frames), <= 1.10 x
  the deployed xmas02gb's AND <= 35 ms, on >= 200 calls each (``--gpu-server``).
OFFLINE: JSON files only (no pixel, no packet read here, no GPU).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

Box = Sequence[float]
CLASS = "floor_item"
CONF = 0.25
IOU_MATCH = 0.3
BARS = {
    "i1_recall": 0.85,
    "i1_precision": 0.85,
    "i2": 0.80,
    "i3_any": 1 / 200,
    "i3_5x5": 1 / 500,
    "i4": 0.05,
    "i5_gpu_p95_ms": 35.0,
    "i5_cpu_ratio": 1.10,
}
# Amendment O15 (round 2): the strata by session NAME (map_labels.XMAS02_FIT)
R2_AURA = ("-rdp-hunt-xmas02-fiT4", "-rdp-hunt-xmas02-fiT5", "-rdp-hunt-xmas02-fiT6",
           "-rdp-xmas02-fsTa")  # fmt: skip
R2_NOAURA = ("-rdp-xmas02-fsTn",)
R2_PILOTS = ("-rdp-hunt-xmas02-fiT4", "-rdp-hunt-xmas02-fiT5", "-rdp-hunt-xmas02-fiT6")
# Amendment O17 (round 3): its fresh held-out, the same bars (``--strata r3``)
R3_PILOTS = ("-rdp-hunt-xmas02-fiT7", "-rdp-hunt-xmas02-fiT8", "-rdp-hunt-xmas02-fiT9")
R3_AURA = (*R3_PILOTS, "-rdp-xmas02-fsTa3", "-rdp-xmas02-fsTa4")  # O17e: fsTa4 too
R3_NOAURA = ("-rdp-xmas02-fsTn3",)
# Amendment O20 (round 4): its fresh held-out
R4_PILOTS = ("-rdp-hunt-xmas02-fiT10", "-rdp-hunt-xmas02-fiT11", "-rdp-hunt-xmas02-fiT12",
             "-rdp-hunt-xmas02-fiT13")  # fmt: skip
R4_AURA = (*R4_PILOTS, "-rdp-xmas02-fsTa4")
R4_NOAURA = ("-rdp-xmas02-fsTn4",)
# O22 (round 5, Batt 2026-11-11: the aura OFF): the whole held-out is aura-off -- ONE stratum
R5_PILOTS = ("-rdp-hunt-xmas02-fiH1", "-rdp-hunt-xmas02-fiH2")
R5_AURA_OFF = (*R5_PILOTS, "-rdp-xmas02-fsH1")
STRATA = {"r2": (R2_AURA, R2_NOAURA, R2_PILOTS), "r3": (R3_AURA, R3_NOAURA, R3_PILOTS),
          "r4": (R4_AURA, R4_NOAURA, R4_PILOTS), "r5": (R5_AURA_OFF, (), R5_PILOTS)}  # fmt: skip
STRATA_NAMES = {"r5": ("aura_off", "")}  # the default: ("aura", "no_aura")
R2_TARGET = 0.95  # Batt 2026-11-10 night: "toward 95 %" -- reported, not a bar
MINS = {
    "i1_recall": 40,
    "i1n_recall": 30,
    "i1_precision": 40,
    "i2": 20,
    "i3_any": 200,
    "i3_5x5": 500,
    "i4": 40,
    "i5": 200,
}


def iou(a: Box, b: Box) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def centre(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def inside(p: Sequence[float], b: Box) -> bool:
    return b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3]


def matches(box: Box, target: Box) -> bool:
    """PURE (O.9): IoU >= 0.3 or the box's centre lies in the target."""
    return iou(box, target) >= IOU_MATCH or inside(centre(box), target)


def cell_point(box: Box, anchor: Sequence[float]) -> tuple[float, float]:
    c = centre(box)
    return c[0] - float(anchor[0]), c[1] - float(anchor[1])


def boxes_of(dets: Sequence[Mapping[str, Any]], conf: float = CONF) -> list[list[float]]:
    """PURE: the floor_item boxes >= ``conf`` of one frame's predict_dir detections."""
    return [[float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"])] for d in dets
            if d.get("cls") == CLASS and float(d.get("conf", 0.0)) >= conf]  # fmt: skip


def ratio_bar(num: int, den: int, bar: float, minimum: int, higher: bool) -> dict[str, Any]:
    """PURE: a share and its verdict: NO_VERDICT below ``minimum`` rows; PASS when the share is
    >= ``bar`` (``higher``) or <= ``bar`` (a rate)."""
    out: dict[str, Any] = {
        "num": num,
        "den": den,
        "bar": round(bar, 6),
        "min_rows": minimum,
        "share": None if den == 0 else round(num / den, 4),
    }
    if den < minimum:
        return {**out, "verdict": "NO_VERDICT"}
    ok = num / den >= bar if higher else num / den <= bar
    return {**out, "verdict": "PASS" if ok else "FAIL"}


def frame_key(sid: str, frame_id: int) -> str:
    return f"{sid}.{int(frame_id):09d}"


def judged(f: Mapping[str, Any]) -> bool:
    """A frame the label pass judged (its scene and layout read)."""
    return f.get("n_near") is not None


def i1_recall(crops: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]]
              ) -> dict[str, Any]:  # fmt: skip
    """PURE: the evaluated crops (session, frame_id, box) boxed by a matching prediction."""
    hit = [
        c
        for c in crops
        if any(matches(b, c["box"]) for b in pred[frame_key(c["session"], c["frame_id"])])
    ]
    return {**ratio_bar(len(hit), len(crops), BARS["i1_recall"], MINS["i1_recall"], True),
            "missed": [f"{c['session']}:{c['frame_id']}:{c.get('floor_id')}" for c in crops
                       if c not in hit]}  # fmt: skip


def floor_targets(f: Mapping[str, Any]) -> list[tuple[Box | None, Box]]:
    """PURE: (target box, 1-cell neighbourhood) of every floor item of a judged frame: its label
    box when the frame has one, else its predicted box (None when it has none)."""
    fitted = {int(it["floor_id"]): it["box"] for it in f.get("items", [])}
    return [(fitted.get(int(r["floor_id"]), r.get("pred_box")), r["near_box"])
            for r in f.get("floor", [])]  # fmt: skip


def i1_precision(docs: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]],
                 anchor: Sequence[float]) -> dict[str, Any]:  # fmt: skip
    """PURE: every box on every judged frame: TRUE / FALSE / AMBIGUOUS (module docstring)."""
    true = false = amb = 0
    for doc in docs:
        for f in doc["frames"]:
            if not judged(f):
                continue
            targets = floor_targets(f)
            for b in pred[frame_key(doc["session"], f["frame_id"])]:
                if any(t is not None and matches(b, t) for t, _n in targets):
                    true += 1
                elif not any(inside(cell_point(b, anchor), n) for _t, n in targets):
                    false += 1
                else:
                    amb += 1
    return {
        **ratio_bar(true, true + false, BARS["i1_precision"], MINS["i1_precision"], True),
        "true": true,
        "false": false,
        "ambiguous": amb,
    }


def episodes(doc: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """PURE (I2): the drops of our kills with >= 1 kept-label frame, each with its FIRST such
    frame and label box; and the (0,+1) drops beside (behind her)."""
    by_floor: dict[int, tuple[int, Mapping[str, Any], Mapping[str, Any]]] = {}
    for f in doc["frames"]:
        if f["status"] != "keep":
            continue
        for it in f["items"]:
            fid = int(it["floor_id"])
            if fid not in by_floor or int(f["t"]) < by_floor[fid][0]:
                by_floor[fid] = (int(f["t"]), f, it)
    eps, behind, behind_labelled = [], 0, 0
    for k in doc.get("kills", []):
        on_back = k.get("rel") is not None and [round(x) for x in k["rel"]] == [0, 1]
        for fid in k["drops"]:
            behind += on_back
            if int(fid) in by_floor:
                _t, f, it = by_floor[int(fid)]
                behind_labelled += on_back
                eps.append({"session": doc["session"], "floor_id": int(fid),
                            "frame_id": f["frame_id"], "box": it["box"],
                            "age_s": it.get("age_s"), "behind": on_back})  # fmt: skip
    drops = sum(len(k["drops"]) for k in doc.get("kills", []))
    return eps, {"drops_of_our_kills": drops, "drops_behind_her": behind,
                 "behind_with_a_kept_label": behind_labelled}  # fmt: skip


def i2(docs: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]]) -> dict[str, Any]:
    eps: list[dict[str, Any]] = []
    side = {"drops_of_our_kills": 0, "drops_behind_her": 0, "behind_with_a_kept_label": 0}
    for doc in docs:
        e, s = episodes(doc)
        eps += e
        for k in side:
            side[k] += s[k]
    hit = [
        e
        for e in eps
        if any(matches(b, e["box"]) for b in pred[frame_key(e["session"], e["frame_id"])])
    ]
    return {**ratio_bar(len(hit), len(eps), BARS["i2"], MINS["i2"], True), **side,
            "missed": [f"{e['session']}:{e['frame_id']}:{e['floor_id']}" for e in eps
                       if e not in hit]}  # fmt: skip


def i3(docs: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]],
       anchor: Sequence[float]) -> dict[str, Any]:  # fmt: skip
    """PURE: fiT's kept frames with no floor item in any phase."""
    n = any_box = near = 0
    for doc in docs:
        for f in doc["frames"]:
            if f["status"] != "keep" or f.get("n_near") != 0 or f.get("floor"):
                continue
            n += 1
            bs = pred[frame_key(doc["session"], f["frame_id"])]
            any_box += bool(bs)
            near += any(inside(cell_point(b, anchor), f["around_box"]) for b in bs)
    return {
        "frames": n,
        "any": ratio_bar(any_box, n, BARS["i3_any"], MINS["i3_any"], False),
        "around_5x5": ratio_bar(near, n, BARS["i3_5x5"], MINS["i3_5x5"], False),
    }


def i4(docs: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]],
       anchor: Sequence[float]) -> dict[str, Any]:  # fmt: skip
    """PURE: our kills WITHOUT a drop, their first frame 2.0-3.0 s after the death."""
    n = boxed = no_frame = 0
    for doc in docs:
        for k in doc.get("kills", []):
            if k["drops"]:
                continue
            fr = k.get("i4")
            if fr is None or fr.get("box3") is None:
                no_frame += 1
                continue
            n += 1
            bs = pred[frame_key(doc["session"], fr["frame_id"])]
            boxed += any(inside(cell_point(b, anchor), fr["box3"]) for b in bs)
    return {
        **ratio_bar(boxed, n, BARS["i4"], MINS["i4"], False),
        "kills_without_drop_no_frame": no_frame,
    }


def nearest_rank(values: Sequence[float], q: float) -> float:
    """PURE: predict_dir's / eval_latency's percentile (nearest rank)."""
    s = sorted(values)
    return float(s[max(1, math.ceil(q / 100 * len(s))) - 1])


def cpu_latency_models(doc: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    """eval_latency.py writes its per-model summaries under "ms" (O14 found it: the file was passed
    as its "ms" block by hand). Accept that output as it is, or a bare {model: summary} map."""
    ms = doc.get("ms")
    return ms if isinstance(ms, Mapping) else doc


def i5(gpu_ms: Sequence[float] | None, cpu: Mapping[str, Mapping[str, Any]] | None,
       item: str | None, deployed: str | None) -> dict[str, Any]:  # fmt: skip
    out: dict[str, Any] = {}
    if gpu_ms is None:
        out["gpu"] = {"verdict": "NO_VERDICT", "why": "no --gpu-timing"}
    else:
        p95 = nearest_rank(gpu_ms, 95) if gpu_ms else None
        v = ("NO_VERDICT" if len(gpu_ms) < MINS["i5"] or p95 is None
             else "PASS" if p95 <= BARS["i5_gpu_p95_ms"] else "FAIL")  # fmt: skip
        out["gpu"] = {"n": len(gpu_ms), "p95_ms": p95, "bar_ms": BARS["i5_gpu_p95_ms"],
                      "min_rows": MINS["i5"], "verdict": v}  # fmt: skip
    if cpu is None or item is None or deployed is None:
        out["cpu"] = {
            "verdict": "NO_VERDICT",
            "why": "no --cpu-latency / --cpu-item / --cpu-deployed",
        }
    else:
        a, b = cpu[item], cpu[deployed]
        n = min(int(a.get("n", 0)), int(b.get("n", 0)))
        ratio = float(a["p95"]) / float(b["p95"]) if n else None
        v = ("NO_VERDICT" if n < MINS["i5"] or ratio is None
             else "PASS" if ratio <= BARS["i5_cpu_ratio"] else "FAIL")  # fmt: skip
        out["cpu"] = {
            "n": n,
            "item_p95_ms": a.get("p95"),
            "deployed_p95_ms": b.get("p95"),
            "ratio": None if ratio is None else round(ratio, 4),
            "bar": BARS["i5_cpu_ratio"],
            "min_rows": MINS["i5"],
            "verdict": v,
        }
    return out


def needed_keys(docs: Sequence[Mapping[str, Any]], crops: Sequence[Mapping[str, Any]]
                ) -> set[str]:  # fmt: skip
    keys = {frame_key(d["session"], f["frame_id"]) for d in docs for f in d["frames"] if judged(f)}
    keys |= {frame_key(d["session"], k["i4"]["frame_id"]) for d in docs
             for k in d.get("kills", []) if k.get("i4")}  # fmt: skip
    keys |= {frame_key(c["session"], c["frame_id"]) for c in crops}
    return keys


def predictions(doc: Mapping[str, Any], need: set[str]) -> dict[str, list[list[float]]]:
    """PURE: predict_dir's frames -> floor_item boxes per key; refuses a missing needed frame
    (fail closed: a frame without a prediction is never 'no box')."""
    frames = doc["frames"]
    missing = sorted(need - set(frames))
    if missing:
        raise SystemExit(f"{len(missing)} needed frames have no prediction (e.g. {missing[:3]})")
    return {k: boxes_of(frames[k]) for k in need}


def on_suffix(sid: str, suffixes: Sequence[str]) -> bool:
    return any(sid.endswith(x) for x in suffixes)


def i1_strata(crops: Sequence[Mapping[str, Any]], pred: Mapping[str, Sequence[Box]],
              rnd: str = "r2") -> dict[str, Any]:  # fmt: skip
    """PURE (O15): I1a (aura) and I1n (no aura) recall, each with its own minimum, the source
    counts and Batt's 95 % target; a crop of neither stratum refuses (fail closed)."""
    other = sorted({c["session"] for c in crops
                    if not on_suffix(c["session"], STRATA[rnd][0] + STRATA[rnd][1])})  # fmt: skip
    if other:
        raise SystemExit(f"--strata {rnd}: crops of no stratum: {other}")
    out: dict[str, Any] = {}
    names = STRATA_NAMES.get(rnd, ("aura", "no_aura"))
    for name, sfx, mins in ((names[0], STRATA[rnd][0], MINS["i1_recall"]),
                            (names[1], STRATA[rnd][1], MINS["i1n_recall"])):  # fmt: skip
        if not sfx:  # O22: a round with one stratum
            continue
        cs = [c for c in crops if on_suffix(c["session"], sfx)]
        r = i1_recall(cs, pred)
        r.update(ratio_bar(r["num"], r["den"], BARS["i1_recall"], mins, True))  # its own minimum
        by_src: dict[str, list[int]] = {}
        for c in cs:
            src = next(x for x in sfx if c["session"].endswith(x)).rsplit("-", 1)[-1]
            hit = f"{c['session']}:{c['frame_id']}:{c.get('floor_id')}" not in r["missed"]
            by_src.setdefault(src, [0, 0])
            by_src[src][0] += hit
            by_src[src][1] += 1
        r["by_source"] = {k: {"hit": v[0], "n": v[1]} for k, v in sorted(by_src.items())}
        r["target_095"] = None if r["share"] is None else r["share"] >= R2_TARGET
        out[name] = r
    return out


def i5_server(fi: Mapping[str, Any] | None, gb: Mapping[str, Any] | None) -> dict[str, Any]:
    """PURE (O15): the detect server's forward p95 of the item model vs the deployed xmas02gb's
    (fi_gpu_latency.py summaries {n, p95, ...}): <= 1.10 x AND <= 35 ms, >= 200 calls each."""
    if fi is None or gb is None:
        return {"verdict": "NO_VERDICT", "why": "no --gpu-server"}
    n = min(int(fi.get("n", 0)), int(gb.get("n", 0)))
    ratio = float(fi["p95"]) / float(gb["p95"]) if n and float(gb["p95"]) > 0 else None
    ok = (ratio is not None and ratio <= BARS["i5_cpu_ratio"]
          and float(fi["p95"]) <= BARS["i5_gpu_p95_ms"])  # fmt: skip
    v = "NO_VERDICT" if n < MINS["i5"] or ratio is None else "PASS" if ok else "FAIL"
    return {"n": n, "item_p95_ms": fi.get("p95"), "deployed_p95_ms": gb.get("p95"),
            "ratio": None if ratio is None else round(ratio, 4), "bar_ratio": BARS["i5_cpu_ratio"],
            "bar_ms": BARS["i5_gpu_p95_ms"], "min_rows": MINS["i5"], "verdict": v}  # fmt: skip


def evaluate(docs: Sequence[Mapping[str, Any]], preds: Mapping[str, Mapping[str, Any]],
             crops: Sequence[Mapping[str, Any]], anchor: Sequence[float],
             latency: Mapping[str, Any], strata: str | None = None) -> dict[str, Any]:  # fmt: skip
    """PURE: every bar for every prediction set, and the verdict (PASS only when every bar of
    every set passes; any NO_VERDICT and no FAIL: NO_VERDICT). ``strata`` "r2" (O15): I1 by
    stratum, I2-I4 on the pilots only, I5 GPU from the detect server's forward time."""
    need = needed_keys(docs, crops)
    per: dict[str, Any] = {}
    verdicts: list[str] = []
    pilots = (docs if strata not in STRATA
              else [d for d in docs if on_suffix(d["session"], STRATA[strata][2])])  # fmt: skip
    for name, doc in preds.items():
        pr = predictions(doc, need)
        r = {
            "i1_recall": i1_recall(crops, pr),
            "i1_precision": i1_precision(docs, pr, anchor),
            "i2": i2(pilots, pr),
            "i3": i3(pilots, pr, anchor),
            "i4": i4(pilots, pr, anchor),
        }
        if strata in STRATA:
            r["i1_strata"] = i1_strata(crops, pr, strata)
            r["i1_recall"]["note"] = "pooled, reported only (O15: I1a / I1n decide)"
            i1v = [v["verdict"] for v in r["i1_strata"].values()]  # O22: one or two strata
        else:
            i1v = [r["i1_recall"]["verdict"]]
        per[name] = r
        verdicts += i1v + [r["i1_precision"]["verdict"], r["i2"]["verdict"],
                           r["i3"]["any"]["verdict"], r["i3"]["around_5x5"]["verdict"],
                           r["i4"]["verdict"]]  # fmt: skip
    lat = i5(latency.get("gpu_ms"), latency.get("cpu"), latency.get("cpu_item"),
             latency.get("cpu_deployed"))  # fmt: skip
    if strata in STRATA:
        lat["gpu_call_reported"] = lat["gpu"]
        lat["gpu"] = i5_server(latency.get("gpu_server_item"), latency.get("gpu_server_deployed"))
    verdicts += [lat["gpu"]["verdict"], lat["cpu"]["verdict"]]
    v = "FAIL" if "FAIL" in verdicts else "NO_VERDICT" if "NO_VERDICT" in verdicts else "PASS"
    return {"per_predictions": per, "i5": lat, "verdict": v}


def evaluated_crops(key: Mapping[str, Any], both: Sequence[str]) -> list[dict[str, Any]]:
    """PURE: the EVALUATED crops' rows (session, frame, floor id, box) from the eval pack's key."""
    if not key.get("eval_test"):
        raise SystemExit("--key: the evaluation's pack (fi_labels.py pack --eval-test) only")
    out = []
    for c in both:
        k = key["crops"][c]
        if k["truth"] != "item":
            raise SystemExit(f"crop {c}: not an item crop")
        out.append({"crop": c, "session": k["session"], "frame_id": k["frame_id"],
                    "floor_id": k["floor_id"], "box": k["box"]})  # fmt: skip
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--labels", type=Path, nargs="+", required=True)
    ap.add_argument("--predictions", nargs="+", required=True, help="NAME=predict_dir.json")
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--evaluated", type=Path, required=True, help="fi_blind_score --both-good")
    ap.add_argument("--gpu-timing", type=Path, default=None, help="predict_dir --timing output")
    ap.add_argument("--cpu-latency", type=Path, default=None,
                    help="eval_latency.py output (or a bare {model: summary})")  # fmt: skip
    ap.add_argument("--cpu-item", default=None)
    ap.add_argument("--strata", choices=sorted(STRATA), default=None,
                    help="O15 / O17: a round's strata")  # fmt: skip
    ap.add_argument(
        "--gpu-server",
        type=Path,
        nargs=2,
        default=None,
        metavar=("ITEM", "DEPLOYED"),
        help="O15: fi_gpu_latency.py outputs, the item model's then xmas02gb's",
    )
    ap.add_argument("--cpu-deployed", default=None)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    docs = [json.loads(p.read_text()) for p in a.labels]
    params = {d["params_sha256"] for d in docs}
    models = {d.get("model", {}).get("sha256") for d in docs}
    if not all(d.get("eval_test") for d in docs) or len(params) != 1 or len(models) != 1:
        raise SystemExit("--labels: fiT --eval-test label files, one params file, one model")
    anchor = json.loads(Path(docs[0]["params"]).read_text())["anchor_px"]
    preds = {}
    for spec in a.predictions:
        name, sep, path = spec.partition("=")
        if not sep or name in preds:
            raise SystemExit(f"--predictions {spec!r}: NAME=FILE, each name once")
        preds[name] = json.loads(Path(path).read_text())
    crops = evaluated_crops(json.loads(a.key.read_text()), json.loads(a.evaluated.read_text()))
    latency: dict[str, Any] = {"cpu_item": a.cpu_item, "cpu_deployed": a.cpu_deployed}
    if a.gpu_timing is not None:
        latency["gpu_ms"] = list(
            json.loads(a.gpu_timing.read_text())["timing_ms"]["per_frame"].values()
        )
    if a.cpu_latency is not None:
        latency["cpu"] = cpu_latency_models(json.loads(a.cpu_latency.read_text()))
    if a.gpu_server is not None:
        fi_d, gb_d = (json.loads(p.read_text())["models"] for p in a.gpu_server)
        latency["gpu_server_item"] = next(iter(fi_d.values()))["server"]
        latency["gpu_server_deployed"] = next(iter(gb_d.values()))["server"]
    res = evaluate(docs, preds, crops, anchor, latency, a.strata)
    res.update(
        {
            "what": "O.9: the floor-item model's bars I1-I5",
            "model": models.pop(),
            "params_sha256": params.pop(),
            "labels": [str(p) for p in a.labels],
        }
    )
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
