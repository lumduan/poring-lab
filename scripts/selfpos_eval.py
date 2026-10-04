#!/usr/bin/env python3
"""Evaluate the minimap readout reader (Phase 3 T0) on HELD-OUT sessions against packet truth.

    selfpos_eval.py [SESSION ...] [--per-session 1500] [--mapcache DIR] [--cache DIR]
                    [--templates data/ui_anchors/minimap_digits.npz] [--out OUT.json]
                    [--reads EARLIER.jsonl] [--legacy-map-lookup]

* Sessions: default outdoor-c, outdoor-d and indoor-c, never used for calibration; a session the
  templates were calibrated on is refused (their meta lists them).
* Frames: --per-session spread evenly over each session (poring_dataset.h264, freeze spans out),
  read with poring_vision.selfpos.read_minimap on the full game region -- the runtime path.
* Truth and classes: the calibration's own rules, read from the templates' meta (the packet->frame
  offset rule, --guard-ms, --load-ms): STANDING (no walk of our own within the guard) or WALKING.
  Left out: GM-command windows, map loading, frames without a position, maps the calibration never
  saw. On maps where the client draws no minimap (indoor) the right answer is None: reported apart.
* Scores per session, pooled, and an A/A split (even / odd sample index, two disjoint halves):
    standing: exact rate, abstain (None) rate, wrong-read rate
    walking:  within-1-cell rate (Chebyshev, against the true cell rounded), abstain, wrong reads
* PRE-REGISTERED (Phase 3 T0, before any held-out frame was read; never moved): PASS needs, pooled,
  >= 99 % exact on standing frames AND >= 97 % within one cell on walking frames.
* Error modes: every wrong read (truth, read, digit diffs, time to the nearest walk), abstain
  reasons per class. Per-frame records go to OUT.jsonl next to OUT.json (/dev/shm, rule 7).
* --reads: re-score an earlier run's reads (its OUT.jsonl) against the truth, decoding nothing:
  for a TRUTH fix only -- the reads, the reader and its thresholds stay what they were.
  --legacy-map-lookup reproduces the truth of the first registered run (2026-10-04), whose walks
  followed the straight fallback path (see selfpos_calibrate.with_packet_names).

Offline only: the packets label, they never reach the reader. Runs at nice 10.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "services" / "vision" / "src"))
import selfpos_calibrate as cal  # noqa: E402

from poring_dataset import mapcache  # noqa: E402
from poring_vision import selfpos  # noqa: E402

STANDING_EXACT_MIN = 0.99  # pre-registered
WALKING_WITHIN1_MIN = 0.97  # pre-registered


def frame_class(truth: cal.FrameTruth, meta: dict[str, Any]) -> str:
    if truth.kind == "excluded":
        return f"excluded:{truth.why}"
    if truth.map not in meta["window_shown_share"]:
        return "excluded:map_not_in_calibration"
    if truth.map not in meta["readout_maps"]:
        return "no_readout_map"
    return truth.kind


def error(read: tuple[int, int], pos: tuple[float, float]) -> int:
    ex, ey = (cal.cell_of(v) for v in pos)
    return max(abs(read[0] - ex), abs(read[1] - ey))


def read_session(
    session: Path, n: int, templates: selfpos.DigitTemplates, cache: Path | None
) -> list[dict[str, Any]]:
    """The reader over ``n`` frames spread over the session: one record per frame, no truth."""
    from poring_dataset.h264 import H264Session

    stream = H264Session(session)
    ids = stream.sample(n)
    index = {fid: i for i, fid in enumerate(ids)}
    rx, ry, rw, rh = cal.ROI
    records, strips = [], []
    t0 = time.monotonic()
    for fmeta, img in stream.frames(ids, verify=False, crop=True):
        reading = selfpos.read_minimap(img, templates)
        strips.append(img[ry : ry + rh, rx : rx + rw].copy())
        records.append({
            "session": session.name, "i": index[fmeta["frame_id"]], "frame_id": fmeta["frame_id"],
            "t_mono_ns": int(fmeta["t_mono_ns"]),
            "read": None if reading.xy is None else list(reading.xy), "reason": reading.reason,
            "glyphs": [[g.x, g.digit, round(g.score, 3), round(g.margin, 3)]
                       for g in reading.glyphs],
        })  # fmt: skip
    print(f"  {session.name}: {len(records)} frames in {time.monotonic() - t0:.0f} s",
          file=sys.stderr)  # fmt: skip
    if cache is not None and strips:
        cache.mkdir(parents=True, exist_ok=True)
        ids_arr = np.array([r["frame_id"] for r in records])
        t_arr = np.array([r["t_mono_ns"] for r in records])
        path = cache / f"{session.name}-n{n}-roi.npz"
        np.savez(path, frame_ids=ids_arr, t_ns=t_arr, strips=np.stack(strips))
    return records


def score_session(
    records: list[dict[str, Any]], truth: cal.SessionTruth, meta: dict[str, Any]
) -> None:
    """Truth, class and outcome of every read record of one session (in place)."""
    for rec in records:
        tr = truth.at(int(rec["t_mono_ns"]))
        rec.update(
            cls=frame_class(tr, meta),
            map=tr.map,
            walk_dt_ms=tr.walk_dt_ms,
            truth=None if tr.pos is None else [round(tr.pos[0], 3), round(tr.pos[1], 3)],
        )
        rec.pop("outcome", None)
        rec.pop("err", None)
        read = rec["read"]
        if rec["cls"] in ("standing", "walking"):
            if read is None:
                rec["outcome"] = "abstain"
            else:
                err = error((read[0], read[1]), tr.pos)  # type: ignore[arg-type]
                ok = err == 0 if rec["cls"] == "standing" else err <= 1
                rec["outcome"], rec["err"] = ("ok" if ok else "wrong"), err
        elif rec["cls"] == "no_readout_map":
            rec["outcome"] = "abstain" if read is None else "wrong"


def summarise(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cls in ("standing", "walking", "no_readout_map"):
        rows = [r for r in records if r["cls"] == cls]
        c = Counter(r["outcome"] for r in rows)
        n = len(rows)
        out[cls] = {"n": n, **{k: c.get(k, 0) for k in ("ok", "abstain", "wrong")},
                    **{f"{k}_rate": (c.get(k, 0) / n if n else None)
                       for k in ("ok", "abstain", "wrong")}}  # fmt: skip
    out["excluded"] = dict(Counter(r["cls"] for r in records if r["cls"].startswith("excluded")))
    st, wk = out["standing"]["ok_rate"], out["walking"]["ok_rate"]
    out["pass"] = bool(st is not None and wk is not None and st >= STANDING_EXACT_MIN
                       and wk >= WALKING_WITHIN1_MIN)  # fmt: skip
    return out


def pct(v: float | None) -> str:
    return "   n/a" if v is None else f"{100 * v:6.2f}"


def table(groups: dict[str, dict[str, Any]]) -> str:
    head = (
        f"{'group':<22}{'stand n':>8}{'exact%':>8}{'none%':>8}{'wrong%':>8}"
        f"{'walk n':>8}{'<=1%':>8}{'none%':>8}{'wrong%':>8}{'noMM n':>8}{'none%':>8}  verdict"
    )
    lines = [head, "-" * len(head)]
    for name, s in groups.items():
        st, wk, nm = s["standing"], s["walking"], s["no_readout_map"]
        lines.append(
            f"{name:<22}{st['n']:>8}{pct(st['ok_rate']):>8}{pct(st['abstain_rate']):>8}"
            f"{pct(st['wrong_rate']):>8}{wk['n']:>8}{pct(wk['ok_rate']):>8}"
            f"{pct(wk['abstain_rate']):>8}{pct(wk['wrong_rate']):>8}{nm['n']:>8}"
            f"{pct(nm['abstain_rate']):>8}  {'PASS' if s['pass'] else 'FAIL'}"
        )
    return "\n".join(lines)


def error_modes(records: list[dict[str, Any]]) -> dict[str, Any]:
    wrong = [r for r in records if r.get("outcome") == "wrong"]
    confusions: Counter[str] = Counter()
    for r in wrong:
        if r["truth"] is None or r["read"] is None:
            continue
        truth = [str(cal.cell_of(v)) for v in r["truth"]]
        for t_s, r_s in zip(truth, (str(v) for v in r["read"]), strict=True):
            if len(t_s) != len(r_s):
                confusions[f"length {t_s}->{r_s}"] += 1
                continue
            for a, b in zip(t_s, r_s, strict=True):
                if a != b:
                    confusions[f"{a}->{b}"] += 1
    abstain: dict[str, Counter[str]] = {}
    for r in records:
        if r.get("outcome") == "abstain":
            abstain.setdefault(r["cls"], Counter())[r["reason"]] += 1
    return {
        "wrong_reads": [{k: r[k] for k in ("session", "frame_id", "cls", "map", "truth", "read",
                                           "err", "walk_dt_ms", "glyphs")} for r in wrong],
        "digit_confusions": dict(confusions.most_common()),
        "abstain_reasons": {k: dict(v.most_common()) for k, v in abstain.items()},
        "wrong_by_walk_dt_ms": dict(Counter(
            "in_walk" if (r["walk_dt_ms"] or 0) == 0 else
            ("<=500" if r["walk_dt_ms"] <= 500 else ">500") for r in wrong)),
    }  # fmt: skip


def main() -> int:
    os.nice(10)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="*", default=list(cal.HELD_OUT))
    ap.add_argument("--per-session", type=int, default=1500)
    ap.add_argument("--templates", type=Path, default=cal.OUT)
    ap.add_argument("--mapcache", type=Path, default=mapcache.GENERATED)
    ap.add_argument("--cache", type=Path, default=cal.SCRATCH / "selfpos-cache")
    ap.add_argument("--out", type=Path, default=cal.SCRATCH / "selfpos_eval.json")
    ap.add_argument(
        "--reads",
        type=Path,
        help="re-score the reads of an earlier run (its OUT.jsonl) without decoding",
    )
    ap.add_argument(
        "--legacy-map-lookup",
        action="store_true",
        help="the truth as first registered: walks on the straight fallback path",
    )
    a = ap.parse_args()
    templates = selfpos.load_digit_templates(a.templates)
    trained = set(templates.meta.get("training_sessions", []))
    sessions = [cal.resolve_session(s) for s in a.sessions]
    leaked = [s.name for s in sessions if s.name in trained]
    if leaked:
        raise SystemExit(f"these sessions were used for calibration: {leaked}")
    maps = mapcache.load(a.mapcache, prere=True)
    earlier: list[dict[str, Any]] = []
    if a.reads is not None:
        earlier = [json.loads(line) for line in a.reads.read_text().splitlines() if line]
        if a.reads.resolve() == a.out.with_suffix(".jsonl").resolve():
            raise SystemExit("--reads would be overwritten: give another --out")

    records: list[dict[str, Any]] = []
    truth_info = {}
    for session in sessions:
        if a.reads is None:
            recs = read_session(session, a.per_session, templates, a.cache)
        else:
            recs = [r for r in earlier if r["session"] == session.name]
        truth = cal.SessionTruth(session, maps, offset_ms="auto",
                                 guard_ms=templates.meta["guard_ms"],
                                 load_ms=templates.meta["load_ms"],
                                 packet_names=not a.legacy_map_lookup)  # fmt: skip
        truth_info[session.name] = {"offset_ms": truth.offset_ms, "offset_run": truth.offset_run,
                                    "aid_source": truth.aid_source,
                                    "aid_found": truth.aid is not None}  # fmt: skip
        score_session(recs, truth, templates.meta)
        records += recs

    groups = {s.name.split("-p3-")[-1]: summarise([r for r in records if r["session"] == s.name])
              for s in sessions}  # fmt: skip
    groups["POOLED"] = summarise(records)
    groups["A (even)"] = summarise([r for r in records if r["i"] % 2 == 0])
    groups["B (odd)"] = summarise([r for r in records if r["i"] % 2 == 1])
    report = {
        "pre_registered": {"standing_exact_min": STANDING_EXACT_MIN,
                           "walking_within1_min": WALKING_WITHIN1_MIN},
        "verdict": "PASS" if groups["POOLED"]["pass"] else "FAIL",
        "sessions": [s.name for s in sessions],
        "per_session": a.per_session,
        "templates": str(a.templates),
        "training_sessions": sorted(trained),
        "reads_from": None if a.reads is None else str(a.reads),
        "map_lookup": "legacy (straight fallback path)" if a.legacy_map_lookup else "walkable path",
        "truth": truth_info,
        "groups": groups,
        "errors": error_modes(records),
    }  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=1))
    with a.out.with_suffix(".jsonl").open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
    print(table(groups))
    print(f"\nverdict (pooled, pre-registered >= {STANDING_EXACT_MIN:.0%} exact standing, "
          f">= {WALKING_WITHIN1_MIN:.0%} within 1 walking): {report['verdict']}")  # fmt: skip
    keys = ("digit_confusions", "abstain_reasons", "wrong_by_walk_dt_ms")
    print(json.dumps({k: report["errors"][k] for k in keys}, indent=1))
    print(f"report: {a.out}  frames: {a.out.with_suffix('.jsonl')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
