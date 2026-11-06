#!/usr/bin/env python3
"""THE LIVE DETECTOR AGAINST THE PACKET TRUTH, on a human demo (docs/planning/gef10-round2.md 4)
or on a recorder session (docs/planning/rogue-xmas02.md 4A, X2).

    detector_vs_packets.py score DEMO_DIR [--map gef_fild10] [--layout hunt] [--window-s 898]
                                 --out JSON [--pairs PAIRS.json] [--boxes BOXES.jsonl]
                                 [--sprites DIR --sprite-names JSON]
    detector_vs_packets.py score-session SESSION --boxes BOXES.jsonl --map xmas_dun02
                                 --sprites DIR --sprite-names JSON --out JSON [--layout hunt]
                                 [--chat auto|legacy|standard|X0,Y0,X1,Y1] [--ui-boxes drop|keep]
                                 [--preflight: the inputs checked, nothing scored]
    detector_vs_packets.py from-predict PRED.json --out BOXES.jsonl

``score-session`` (rogue-xmas02.md Amendment A) scores a RECORDER session (record_session.py: PNG
tar shards, ``packets.jsonl.gz``) with the SAME per-capture rule as ``score`` (one shared loop,
``score_captures``): the captures are the session's frames, at their own ``t_mono_ns``, with the
boxes ``recorder_boxes.py predict`` wrote for them (one row per frame: a missing or a foreign row
is refused). Its per-map parts: the scored species of ``--map`` (SPECIES_BY_MAP; xmas_dun02: Myst
Case, Cruiser, Cookie, Christmas Cookie) and the REPORTED ones (REPORTED_BY_MAP: Garm Baby, the
Stormy Knight, the Christmas Goblin); the UI windows of the session's layout with the chat window
OF ITS DATE (chat_window.for_sid: the 2026-11-05 standard from 20261105T12 on); the sprites of its
map (``--sprites`` / ``--sprite-names``, never the gone gef10 default). Detections at least half
behind those UI windows are left out (``--ui-boxes drop``, Amendment A: "boxes and labels inside
the UI windows ... are left out"; the labels' own in-view rule, mirrored) and counted. It adds
the hallucination frames (our character under EFST_ILLUSION, rAthena's Hallucination icon 34, from
the packets' status changes: counted, reported, never removed) and Amendment A's bar (BAR_4A).

A MAP-SCOPED model (xmas02-detector.md 7, D1 / D2; tool gap T-6) writes its own class names into
the rows (one per tier species). ``--classes LIST`` (``score`` and ``score-session``) collapses
them to ``monster`` before anything is scored: ``recorder_boxes.class_collapse`` of the model's
committed class list against its names in id order (``--names NAMES.json``, its sidecar; else the
boxes' ``.meta.json`` ``names``, which ``recorder_boxes.py predict`` writes). The output then
records ``class_collapse`` (the list, its sha256, the names, the boxes per class before). Without
the flag nothing changes: v1's rows are scored as written.

``from-predict`` (gef10-eval.md AMENDMENT R2-2) turns poring_vision.predict_dir's output on the
demo's own frames (``frames/NNNNN-<t ns>.jpg``: the stem carries the capture time) into
``boxes.jsonl`` rows, every species class collapsed to ``monster`` (player, npc, warp kept), so a
NEW model is scored by ``score --boxes``. Those times are the recorder's frame times, not a live
grab's; ``ms`` is predict_dir's per-frame wall time when it ran with --timing, else None.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Box = tuple[float, float, float, float]
MAIN = Path("/home/batt/docker/poring-lab")
# the species scored one by one, per map (everything else is "other"); X2's four common species
# (rogue-xmas02.md 4A; mob ids from the KB's classes.json for xmas_dun02, xmas02-prep.md 6)
SPECIES_BY_MAP: dict[str, dict[int, str]] = {
    "gef_fild10": {1273: "Orc Lady", 1023: "Orc Warrior", 1031: "Poporing", 1686: "Orc Baby"},
    "xmas_dun02": {1249: "Myst Case", 1248: "Cruiser", 1265: "Cookie", 1246: "Christmas Cookie"},
}
# reported beside them, never in a bar (4A: "Garm Baby, the MVP, the Goblins: reported only";
# the KB names 1515 "Baby Hatii"; 1607 is the MVP's slave G_GOBLINE_XMAS, sprite gobline_xmas)
REPORTED_BY_MAP: dict[str, dict[int, str]] = {
    "gef_fild10": {},
    "xmas_dun02": {1515: "Garm Baby", 1251: "Stormy Knight", 1607: "Christmas Goblin"},
}
SPECIES = SPECIES_BY_MAP["gef_fild10"]
EFST_ILLUSION = 34  # rAthena e985006 status.hpp enum efst_type: SC_HALLUCINATION's icon
UI_HALF = 0.5  # a detection this much behind the UI windows is left out (the labels' in-view rule)
# Amendment A's bar (rogue-xmas02.md 4A): each scored species with >= MIN labels: recall >= RECALL;
# the pooled precision of the class-agnostic "monster" class >= PRECISION
BAR_4A = {"min_labels": 30, "recall": 0.80, "precision": 0.80}
# a recorder session the X2 rule reads (map_labels.check_recording's path; v6 differs from v5 in
# its IO-guard rule only, e5d892f -- the frame clock and the frame bus are v5's)
SESSION_WANT = {"backend": "rdp", "format": "png", "game_region": [80, 77, 1280, 720],
                "server": "lab-rathena"}  # fmt: skip
SESSION_VERSIONS = (5, 6)
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


def precision_of(verdicts: Counter[str]) -> dict[str, Any]:
    """PURE: the precision of a set of detection verdicts (``score_capture``'s: tp / dying /
    self / near_unit / other). xmas02-eval.md P4A pools the STILL captures' counts of X2 + xp1."""
    n, tp = sum(verdicts.values()), verdicts.get("tp", 0)
    return {"detections": n, "tp": tp, "precision": rate(tp, n)}


def species_key(job: int, names: dict[int, str] | None = None) -> str:
    table = SPECIES if names is None else names
    return f"{job} {table[job]}" if job in table else "other"


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


def xywh(rects: Sequence[Sequence[int]]) -> tuple[tuple[int, int, int, int], ...]:
    """PURE: (x0, y0, x1, y1) rectangles -> poring_dataset.ui_layout's (x, y, w, h)."""
    return tuple((int(a), int(b), int(c) - int(a), int(d) - int(b)) for a, b, c, d in rects)


def behind_ui(box: Sequence[float], rects: Sequence[Sequence[int]], half: float = UI_HALF
              ) -> bool:  # fmt: skip
    """PURE: at least ``half`` of the box lies behind the UI windows (the labels' in-view rule,
    mvp_watch_study.in_view: a box under half behind the UI is in view)."""
    from poring_dataset.ui_layout import covered_fraction

    x0, y0, x1, y1 = (float(v) for v in box[:4])
    return covered_fraction((x0, y0, x1, y1), xywh(rects)) >= half


def nested_rects(rects: Sequence[Sequence[int]]
                 ) -> tuple[tuple[tuple[int, int, int, int], ...], list[list[int]]]:  # fmt: skip
    """PURE: (the rectangles without those lying wholly inside another, the dropped ones).
    covered_fraction SUMS the windows' overlaps (it assumes they meet at their edges only); the
    2026-11-05 standard chat window (0, 585, 600, 720) holds the hunting layout's notice_left
    (0, 668, 50, 720) whole, so a box there would count twice. The union is unchanged."""
    rs = [tuple(int(v) for v in r) for r in rects]
    kept: list[tuple[int, int, int, int]] = []
    dropped: list[list[int]] = []
    for i, r in enumerate(rs):
        inside = any(j != i and o[0] <= r[0] and o[1] <= r[1] and o[2] >= r[2] and o[3] >= r[3]
                     and (o != r or j < i) for j, o in enumerate(rs))  # fmt: skip
        if inside:
            dropped.append(list(r))
        else:
            kept.append(r)  # type: ignore[arg-type]
    return tuple(kept), dropped


def chat_rect_for(sid: str, chat: str = "auto") -> tuple[tuple[int, int, int, int], str]:
    """(the chat window's UI rectangle for a RECORDED session, how it was chosen): ``auto`` = the
    window of the session's date (chat_window.for_sid: the 2026-11-05 standard from 20261105T12
    on, the frozen legacy window before); ``legacy`` / ``standard``; or ``X0,Y0,X1,Y1`` measured
    on the session's frames."""
    import chat_window

    if chat == "auto":
        g = chat_window.for_sid(sid)
        name = "standard" if g == chat_window.STANDARD else "legacy"
        return tuple(g.rect), f"auto:{name} (chat_window.for_sid)"  # type: ignore[return-value]
    if chat in chat_window.GEOMETRIES:
        return tuple(chat_window.GEOMETRIES[chat].rect), chat  # type: ignore[return-value]
    try:
        vals = tuple(int(v) for v in chat.split(","))
    except ValueError:
        vals = ()
    if len(vals) != 4 or not (vals[0] < vals[2] and vals[1] < vals[3]):
        raise SystemExit(f"--chat {chat!r}: auto, legacy, standard or X0,Y0,X1,Y1")
    return (vals[0], vals[1], vals[2], vals[3]), "measured"


def session_rects(layout: str, chat_rect: Sequence[int]) -> list[tuple[int, int, int, int]]:
    """The layout's UI windows (client_layout.RECTS: the hunting rows) with ``chat_rect`` as the
    chat window."""
    import client_layout

    rects = [tuple(int(v) for v in r) for r in client_layout.RECTS[layout]]
    rects[client_layout.CHAT_INDEX] = tuple(int(v) for v in chat_rect)
    return rects  # type: ignore[return-value]


def check_session(manifest: dict[str, Any]) -> None:
    """The recording path X2 reads (fail closed): RDP PNG at 1280 x 720 on the lab server,
    recorder v5 or v6."""
    bad = {k: manifest.get(k) for k, v in SESSION_WANT.items() if manifest.get(k) != v}
    if manifest.get("recorder_version") not in SESSION_VERSIONS:
        bad["recorder_version"] = manifest.get("recorder_version")
    if bad:
        raise SystemExit(f"{manifest.get('session_id')}: not the recording path X2 reads: {bad}")


def session_captures(frames: Sequence[tuple[int, int]], rows: Sequence[dict[str, Any]],
                     allow_partial: bool = False
                     ) -> tuple[list[dict[str, Any]], dict[str, int]]:  # fmt: skip
    """PURE: the session's frames (frame_id, t_mono_ns) joined to the box rows BY CAPTURE TIME
    (a row's own frame_id, when it has one, must agree). A row at a time the session does not
    have, a repeated time or a mismatched frame id is refused; a frame without a row is refused
    unless ``allow_partial`` (then counted). Returns the rows in time order and the coverage."""
    want = {int(t): int(fid) for fid, t in frames}
    if len(want) != len(frames):
        raise SystemExit("the session repeats a capture time")
    by_t: dict[int, dict[str, Any]] = {}
    for r in rows:
        t = int(r["t"])
        if t in by_t:
            raise SystemExit(f"two box rows at t {t}")
        if t not in want:
            raise SystemExit(f"a box row at t {t}: no such frame in the session (another source?)")
        if "frame_id" in r and int(r["frame_id"]) != want[t]:
            raise SystemExit(f"the box row at t {t} says frame {r['frame_id']}, the session "
                             f"{want[t]}")  # fmt: skip
        by_t[t] = r
    missing = len(want) - len(by_t)
    if missing and not allow_partial:
        raise SystemExit(f"{missing} of {len(want)} frames have no box row (finish the predictor "
                         f"with --resume, or --allow-partial to score what there is)")  # fmt: skip
    return [by_t[t] for t in sorted(by_t)], {"frames_in_session": len(want),
                                              "frames_with_boxes": len(by_t),
                                              "frames_without_boxes": missing}  # fmt: skip


def hallucination_spans(events: Sequence[dict[str, Any]], efst: int = EFST_ILLUSION
                        ) -> dict[int, list[tuple[int, int]]]:  # fmt: skip
    """PURE: per gid, the [start, end) times its status icon ``efst`` was on, from the packets'
    status changes: on -> off; a timed "on" (0x0983) ends by its remaining time at the latest;
    an "on" never switched off runs to the end (2**63)."""
    end_of_time = 2**63
    spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    open_: dict[int, tuple[int, int]] = {}  # gid -> (start, expiry)
    mine = [e for e in events
            if e.get("type") == "status_change" and int(e.get("efst", -1)) == efst]  # fmt: skip
    rows = sorted(mine, key=lambda e: int(e["t_mono_ns"]))
    for e in rows:
        g, t = int(e["gid"]), int(e["t_mono_ns"])
        remain = e.get("remain_ms")
        expiry = t + int(remain) * 1_000_000 if remain is not None else end_of_time
        if g in open_ and open_[g][1] <= t:  # it ran out before this event
            spans[g].append((open_[g][0], open_[g][1]))
            del open_[g]
        if e.get("on"):
            start = open_[g][0] if g in open_ else t
            open_[g] = (start, expiry)
        elif g in open_:
            spans[g].append((open_[g][0], min(t, open_[g][1])))
            del open_[g]
    for g, (start, expiry) in open_.items():
        spans[g].append((start, expiry))
    return dict(spans)


def in_spans(spans: Sequence[tuple[int, int]], t: int) -> bool:
    return any(a <= t < b for a, b in spans)


def bar_4a(per_species: dict[str, Any], species: dict[int, str], tp: int, n_det: int,
           rule: dict[str, float] = BAR_4A) -> dict[str, Any]:  # fmt: skip
    """PURE: rogue-xmas02.md Amendment A's bar. Each scored species with >= min_labels in-view
    labels: recall (any detection's centre in its box: score_capture's ``hit``) >= recall; the
    pooled precision (``tp`` of ``n_det`` monster detections) >= precision. Exact integer
    comparisons (no rounding). PASS needs every scored species and the precision; no species with
    enough labels: NO_BAR (the bar cannot be applied; the parent decides)."""
    r_pct, p_pct = round(rule["recall"] * 100), round(rule["precision"] * 100)
    rows: dict[str, Any] = {}
    for job, name in species.items():
        key = f"{job} {name}"
        got = per_species.get(key) or {"n": 0, "hit": 0}
        n, h = int(got["n"]), int(got["hit"])
        enough = n >= rule["min_labels"]
        rows[key] = {"n": n, "hit": h, "recall": rate(h, n), "in_bar": enough,
                     "pass": (h * 100 >= r_pct * n) if enough else None}  # fmt: skip
    prec_pass = n_det > 0 and tp * 100 >= p_pct * n_det
    in_bar = [r for r in rows.values() if r["in_bar"]]
    if not in_bar:
        verdict = "NO_BAR"
    elif all(r["pass"] for r in in_bar) and prec_pass:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    failed = [k for k, r in rows.items() if r["pass"] is False]
    text = (
        "rogue-xmas02.md 4A: recall >= {recall} for each species with >= {min_labels} "
        "labels AND pooled monster precision >= {precision}"
    ).format(**rule)
    if not prec_pass:
        failed.append("precision")
    return {"rule": text, **rule, "species": rows,
            "precision": {"detections": n_det, "tp": tp, "precision": rate(tp, n_det),
                          "pass": prec_pass},
            "verdict": verdict, "failed": failed}  # fmt: skip


# --- the session ------------------------------------------------------------------------------


def read_boxes(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def collapse_classes(caps: list[dict[str, Any]], classes: Path | None, names: Path | None,
                     boxes_meta: dict[str, Any] | None
                     ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:  # fmt: skip
    """T-6: ``caps`` with a map-scoped model's species classes collapsed to ``monster`` (the
    class list ``classes`` against the model's names: ``names``, else the boxes' meta), and the
    provenance; ``classes`` None: the rows unchanged and no provenance (v1)."""
    if classes is None:
        if names is not None:
            raise SystemExit("--names goes with --classes")
        return caps, None
    import hashlib

    import recorder_boxes as rb
    import unit_detector as ud

    if names is not None:
        model_names, source = ud.parse_names(json.loads(names.read_text()), str(names)), str(names)
    elif boxes_meta is not None and boxes_meta.get("names"):
        model_names, source = ud.parse_names(list(boxes_meta["names"])), "the boxes' .meta.json"
    else:
        raise SystemExit("--classes needs the model's names: --names NAMES.json, or the boxes' "
                         ".meta.json (recorder_boxes.py predict)")  # fmt: skip
    mapping = rb.class_collapse(json.loads(classes.read_text()), model_names)
    out = rb.collapse_rows(caps, mapping)
    sha = hashlib.sha256(classes.read_bytes()).hexdigest()
    prov = {"classes": str(classes), "classes_sha256": sha, "names_from": source,
            "names": list(model_names),
            "to_monster": sorted(k for k, v in mapping.items() if v == rb.SCORED_CLASS),
            "boxes_by_class_before": rb.class_counts(caps),
            "boxes_by_class_after": rb.class_counts(out)}  # fmt: skip
    return out, prov


KEPT_CLASSES = ("player", "npc", "warp")  # every other class is a monster species


def predict_rows(pred: dict[str, Any]) -> list[dict[str, Any]]:
    """PURE: predict_dir's {"frames": {"NNNNN-<t ns>": [{cls, x1, y1, x2, y2, conf}]}} (and its
    optional "timing_ms") -> boxes.jsonl rows in time order, species collapsed to ``monster``."""
    per = ((pred.get("timing_ms") or {}).get("per_frame")) or {}
    rows = []
    for stem, dets in pred["frames"].items():
        _n, sep, t = stem.partition("-")
        if not sep or not t.isdigit():
            raise SystemExit(f"{stem}: not a demo frame name (NNNNN-<t ns>)")
        boxes = [[float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"]), float(d["conf"]),
                  d["cls"] if d["cls"] in KEPT_CLASSES else "monster"] for d in dets]  # fmt: skip
        rows.append({"t": int(t), "ms": per.get(stem), "boxes": boxes})
    return sorted(rows, key=lambda r: r["t"])


@dataclass
class ScoreConfig:
    """What ``score_captures`` projects and scores with."""

    map_name: str
    layout: str
    kb: Path
    mapcache_dir: Path
    sprites: Path
    sprite_names: Path
    rects: Sequence[Sequence[int]] | None = None  # None: client_layout.RECTS[layout]
    ui_boxes: str = "keep"  # "drop": detections >= half behind the UI windows are left out
    require_sheets: bool = False  # refuse when a scored species has no decoded sprite
    # before nested_rects (its in-view changes are counted)
    raw_rects: Sequence[tuple[int, int, int, int]] | None = None
    pairs: bool = False


def score_captures(caps: Sequence[dict[str, Any]], events: list[dict[str, Any]],
                   size: tuple[int, int], cfg: ScoreConfig) -> dict[str, Any]:  # fmt: skip
    """THE per-capture loop of ``score`` and ``score-session``: at each capture time t of
    ``caps`` (boxes.jsonl rows), the monsters the packets put on screen (truth_row) against the
    rows' ``monster`` boxes. Returns ``body`` (score's own keys), ``extra`` (the hallucination
    and UI-box counts), ``skipped`` and ``pairs``."""
    import gef10_items
    import mvp_watch_study as mws

    from poring_dataset.camera import map_key
    from poring_dataset.render import Actor, MonsterAction, anchor_and_depth, load_scene
    from poring_dataset.render import predict_sprite as predict

    stack = mws.truth_stack(events, cfg.layout, size, kb=cfg.kb, mapcache_dir=cfg.mapcache_dir,
                            sprites=cfg.sprites, sprite_names=cfg.sprite_names)  # fmt: skip
    if cfg.rects is not None:
        stack.rects = tuple(tuple(int(v) for v in r) for r in cfg.rects)
    species = SPECIES_BY_MAP.get(cfg.map_name, {})
    reported = REPORTED_BY_MAP.get(cfg.map_name, {})
    names = {**species, **reported}
    if cfg.require_sheets:
        lost = {j: n for j, n in species.items() if stack.sheets(j) is None}
        if lost:
            raise SystemExit(f"no decoded sprite for the scored species {lost} in {cfg.sprites} "
                             f"(names {cfg.sprite_names}): {stack.sheets.missing}")  # fmt: skip
    halluc = hallucination_spans(events)
    by_conf = {c: {"hit": 0, "n": 0, "tp": 0, "dets": 0} for c in CONF_STEPS}
    off_ns = int(mws.OFFSET_MS * 1e6)
    skipped: Counter[str] = Counter()
    unit_rows: list[dict[str, Any]] = []
    verdicts: Counter[str] = Counter()
    det_species: Counter[str] = Counter()
    frames_any_view = frames_view_none = 0
    no_sheet: Counter[int] = Counter()
    pairs = []
    ui_left: Counter[str] = Counter()
    halluc_caps = 0
    halluc_verdicts: Counter[str] = Counter()
    # xmas02-eval.md P4A: the precision on STILL captures (no move of ours in the 500 ms before)
    motion_verdicts: dict[str, Counter[str]] = {"moving": Counter(), "still": Counter()}
    nested_changed = 0
    for c in caps:
        t = int(c["t"])
        row = mws.truth_row(stack, t, None, mws.OFFSET_MS, cfg.map_name)
        if not row["map"] or map_key(row["map"]) != cfg.map_name or row["self"] is None:
            skipped["off_map"] += 1
            continue
        if any(f in row["flags"] for f in SKIP_FLAGS):
            skipped["flag:" + "+".join(f for f in row["flags"] if f in SKIP_FLAGS)] += 1
            continue
        tw = t - off_ns
        aid = stack.tl.frame_world(tw).aid
        hallucinating = aid is not None and in_spans(halluc.get(int(aid), ()), tw)
        halluc_caps += hallucinating
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
        monster = [b for b in c["boxes"] if b[5] == "monster"]
        if cfg.ui_boxes == "drop":
            kept = [b for b in monster if not behind_ui(b, stack.rects)]
            left = [b[:4] for b in monster if behind_ui(b, stack.rects)]
            if left:
                _s, v_left = score_capture(row["units"], left, dying, sbox)
                ui_left["detections"] += len(left)
                ui_left["of_them_tp"] += v_left.count("tp")
        else:
            kept = monster
            ui_left["behind_ui_kept"] += sum(1 for b in monster if behind_ui(b, stack.rects))
        if cfg.raw_rects is not None:
            for u in row["units"]:
                if u.get("box") is not None and u["in_view"] != mws.in_view(
                    u["box"], stack.size, cfg.raw_rects
                ):
                    nested_changed += 1
        dets = [b[:4] for b in kept]
        for u in row["units"]:
            if u.get("box") is None:
                no_sheet[int(u["job"])] += 1
        scored, vs = score_capture(row["units"], dets, dying, sbox)
        verdicts.update(vs)
        if hallucinating:
            halluc_verdicts.update(vs)
        for cf in CONF_STEPS:
            keep = [b[:4] for b in kept if float(b[4]) >= cf]
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
                det_species[species_key(int(hit[0]["job"]), names)] += 1
        before = stack.tl.frame_world(tw - SELF_MOVE_NS).self_pos
        moving = before != row["self"]
        motion_verdicts["moving" if moving else "still"].update(vs)
        if scored:
            frames_any_view += 1
            if not dets:
                frames_view_none += 1
        for u in scored:
            unit_rows.append({"t": t, "gid": int(u["gid"]), "job": int(u["job"]),
                              "state": u["state"], "hit": u["hit"], "hit_1to1": u["hit_1to1"],
                              "dist": round(chebyshev(u["cell"], row["self"]), 2),
                              "moving": moving, "hallucination": hallucinating})  # fmt: skip
        if cfg.pairs:
            pairs.append({"t": t, "self": row["self"], "moving": moving, "dets": c["boxes"],
                          "verdicts": vs, "units": scored, "dying": dying,
                          "self_box": sbox, "hallucination": hallucinating})  # fmt: skip
    per_species: dict[str, Any] = {}
    for key in [*(species_key(j, names) for j in names), "other"]:
        rs = [r for r in unit_rows if species_key(r["job"], names) == key]
        per_species[key] = {**tally(rs), "by_distance": {
            name: tally([r for r in rs if dist_bin(r["dist"]) == name]) for *_x, name in DIST_BINS},
            "jobs": dict(Counter(str(r["job"]) for r in rs))}  # fmt: skip
    eps = episodes(unit_rows)
    delays = [e["delay_s"] for e in eps if e["delay_s"] is not None]
    ms_all = [float(c["ms"]) for c in caps if c.get("ms") is not None]
    n_det = sum(verdicts.values())
    body = {
        "offset_ms": mws.OFFSET_MS, "k": mws.K,
        "latency_ms": {"n": len(ms_all), "median": percentile(ms_all, 50) if ms_all else None,
                       "p95": percentile(ms_all, 95) if ms_all else None,
                       "max": max(ms_all) if ms_all else None},
        "recall_all": tally(unit_rows),
        "per_species": per_species,
        "by_distance": {name: tally([r for r in unit_rows if dist_bin(r["dist"]) == name])
                        for *_x, name in DIST_BINS},
        "by_state": {s: tally([r for r in unit_rows if r["state"] == s])
                     for s in sorted({str(r["state"]) for r in unit_rows})},
        "by_self_motion": {k: tally([r for r in unit_rows if r["moving"] is v])
                           for k, v in (("moving", True), ("still", False))},
        "precision_by_self_motion": {k: precision_of(v) for k, v in motion_verdicts.items()},
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
    }  # fmt: skip
    status_events = sum(1 for e in events if e.get("type") == "status_change")
    extra = {
        "species_scored": {str(j): n for j, n in species.items()},
        "species_reported": {str(j): n for j, n in reported.items()},
        "ui_boxes": {"rule": cfg.ui_boxes, "half": UI_HALF, **dict(ui_left)},
        "hallucination": {
            "efst": EFST_ILLUSION,
            "status_change_events": status_events,
            "efst_events": sum(1 for e in events if e.get("type") == "status_change"
                               and int(e.get("efst", -1)) == EFST_ILLUSION),
            "captures": halluc_caps,
            "recall_on": tally([r for r in unit_rows if r["hallucination"]]),
            "recall_off": tally([r for r in unit_rows if not r["hallucination"]]),
            "precision_on": {"detections": sum(halluc_verdicts.values()),
                             "tp": halluc_verdicts.get("tp", 0),
                             "precision": rate(halluc_verdicts.get("tp", 0),
                                               sum(halluc_verdicts.values()))},
            "note": "our character under EFST_ILLUSION (the packets' status changes); counted "
                    "and reported, never removed (rogue-xmas02.md 4A). Its sensor is the status "
                    "decoder (0x0196 / 0x0983): no live Hallucination has been decoded yet",
        },
    }  # fmt: skip
    if cfg.raw_rects is not None:
        extra["nested_ui_rects"] = {
            "dropped": nested_rects(cfg.raw_rects)[1],
            "unit_in_view_changed": nested_changed,
        }
    return {"body": body, "extra": extra, "skipped": skipped, "pairs": pairs,
            "n_det": n_det, "tp": verdicts.get("tp", 0), "species": species}  # fmt: skip


def cmd_score(a: argparse.Namespace) -> dict[str, Any]:
    import client_layout

    demo: Path = a.demo
    manifest = json.loads((demo / "manifest.json").read_text())
    t0 = int(manifest["t0_live_ns"])
    t1 = t0 + int(a.window_s * 1e9)
    caps = read_boxes(a.boxes if a.boxes is not None else demo / "boxes.jsonl")
    caps, collapse = collapse_classes(caps, getattr(a, "classes", None),
                                      getattr(a, "names", None), None)  # fmt: skip
    win = [c for c in caps if t0 <= int(c["t"]) <= t1]
    with gzip.open(demo / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    rects = tuple(tuple(r) for r in client_layout.RECTS[a.layout])
    if a.chat_rect is not None:  # the demo's chat window was dragged (measured on its frames)
        new = tuple(int(v) for v in a.chat_rect.split(","))
        if a.layout != "hunt" or len(new) != 4:
            raise SystemExit("--chat-rect X0,Y0,X1,Y1 replaces the hunt layout's chat window")
        rects = tuple(new if tuple(r) == HUNT_CHAT else tuple(r) for r in rects)
    cfg = ScoreConfig(a.map, a.layout, a.kb, a.mapcache_dir, a.sprites, a.sprite_names,
                      rects=rects, pairs=a.pairs is not None)  # fmt: skip
    res = score_captures(win, events, (1280, 720), cfg)
    skipped = res["skipped"]
    return {
        "what": "the live detector's monster boxes (boxes.jsonl) against the packet truth "
                "(mvp_watch_study.truth_row) at each logged capture time",
        "demo": manifest["session_id"], "map": a.map, "layout": a.layout,
        "window": {"t0_live_ns": t0, "seconds": a.window_s, "captures_logged": len(caps),
                   "captures_in_window": len(win), "skipped": dict(skipped),
                   "captures_scored": len(win) - sum(skipped.values())},
        "boxes": str(a.boxes) if a.boxes is not None else "boxes.jsonl (the live detector)",
        **res["body"], **res["extra"], "sprites": str(a.sprites),
        **({"class_collapse": collapse} if collapse is not None else {}),
        "_pairs": res["pairs"] if a.pairs is not None else None,
    }  # fmt: skip


def projection_inputs(map_name: str, mapcache_dir: Path, sprites: Path, sprite_names: Path,
                      kb: Path) -> dict[str, Any]:  # fmt: skip
    """The client-derived inputs the truth projection reads, checked (fail closed): the map's GAT
    in GAT_DIR (load_scene would fall back to FLAT ground without it, silently), the map in the
    server map cache, a decoded sprite for every scored species (reported ones: listed)."""
    import hashlib

    import qa_export

    from poring_dataset import mapcache
    from poring_dataset.camera import GAT_DIR

    gat = GAT_DIR / f"{map_name}.gat"
    if not gat.exists():
        raise SystemExit(f"{gat}: the map's GAT is not extracted (xmas02-prep.md 9: "
                         f"grf_read.py extract ... --out /dev/shm/poring-lab-tmp/gat)")  # fmt: skip
    if map_name not in mapcache.load(mapcache_dir, prere=True):
        raise SystemExit(f"{map_name}: not in the map cache under {mapcache_dir}")
    qa_export.KB_CLASSES = kb / "classes.json"
    sheets = qa_export.Sheets(sprites, stems=qa_export.sprite_stems(sprite_names))
    species = SPECIES_BY_MAP.get(map_name, {})
    reported = REPORTED_BY_MAP.get(map_name, {})
    have = {j: sheets(j) is not None for j in (*species, *reported)}
    lost = {j: n for j, n in species.items() if not have[j]}
    if lost:
        raise SystemExit(f"no decoded sprite for the scored species {lost} in {sprites} "
                         f"(names {sprite_names}): {sheets.missing}")  # fmt: skip
    return {"gat": str(gat), "gat_sha256": hashlib.sha256(gat.read_bytes()).hexdigest(),
            "sprites": {f"{j} {n}": have[j] for j, n in {**species, **reported}.items()},
            "sprite_problems": {str(k): v for k, v in sheets.missing.items()}}  # fmt: skip


def cmd_score_session(a: argparse.Namespace) -> dict[str, Any]:
    import mvp_watch_study as mws

    session: Path = a.session
    manifest = json.loads((session / "manifest.json").read_text())
    check_session(manifest)
    sid = str(manifest["session_id"])
    boxes_meta = None
    if a.boxes is not None:
        meta_path = a.boxes.with_name(a.boxes.name + ".meta.json")
        boxes_meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
    if boxes_meta is not None and boxes_meta.get("session_id") != sid:
        raise SystemExit(f"{a.boxes}: its meta says session {boxes_meta.get('session_id')!r}, "
                         f"not {sid!r}")  # fmt: skip
    index = mws.png_index(session, manifest)
    frames = [(int(r.frame_id), int(r.t_mono_ns)) for r in index]
    inputs = projection_inputs(a.map, a.mapcache_dir, a.sprites, a.sprite_names, a.kb)
    chat_rect, chat_how = chat_rect_for(sid, a.chat)
    raw = session_rects(a.layout, chat_rect)
    rects, dropped = nested_rects(raw)
    if a.preflight:  # the inputs only: nothing projected, nothing scored
        have = None if a.boxes is None or not a.boxes.exists() else read_boxes(a.boxes)
        cov = None if have is None else session_captures(frames, have, allow_partial=True)[1]
        return {"preflight": "ok", "session": sid, "map": a.map, "layout": a.layout,
                "frames_indexed": len(index), "manifest_frames": manifest.get("frames"),
                "boxes": None if a.boxes is None else str(a.boxes), "coverage": cov,
                "boxes_meta": boxes_meta, "chat": {"rect": list(chat_rect), "chosen": chat_how},
                "ui_rects": [list(r) for r in rects], "nested_ui_rects_dropped": dropped,
                **inputs, "_pairs": None,
                **({"class_collapse": collapse_classes([], a.classes, a.names, boxes_meta)[1]}
                   if getattr(a, "classes", None) is not None else {})}  # fmt: skip
    if a.boxes is None:
        raise SystemExit("--boxes is required (only --preflight runs without it)")
    caps, coverage = session_captures(frames, read_boxes(a.boxes), a.allow_partial)
    caps, collapse = collapse_classes(caps, getattr(a, "classes", None),
                                      getattr(a, "names", None), boxes_meta)  # fmt: skip
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    size = (int(manifest["game_region"][2]), int(manifest["game_region"][3]))
    cfg = ScoreConfig(a.map, a.layout, a.kb, a.mapcache_dir, a.sprites, a.sprite_names,
                      rects=rects, ui_boxes=a.ui_boxes, require_sheets=True,
                      raw_rects=raw if dropped else None,
                      pairs=a.pairs is not None)  # fmt: skip
    res = score_captures(caps, events, size, cfg)
    skipped = res["skipped"]
    body = res["body"]
    return {
        "what": "v1's monster boxes (recorder_boxes.py predict) against the packet truth "
                "(mvp_watch_study.truth_row) at each recorded frame's capture time "
                "(rogue-xmas02.md 4A)",
        "session": sid, "map": a.map, "layout": a.layout,
        "chat": {"rect": list(chat_rect), "chosen": chat_how},
        "window": {"t0_mono_ns": manifest.get("t0_mono_ns"),
                   "t1_mono_ns": manifest.get("t1_mono_ns"), **coverage,
                   "shard_frames_indexed": len(index), "skipped": dict(skipped),
                   "captures_scored": len(caps) - sum(skipped.values())},
        "boxes": str(a.boxes), "boxes_meta": boxes_meta, "sprites": str(a.sprites),
        "sprite_names": str(a.sprite_names), "projection_inputs": inputs,
        **body, **res["extra"],
        "bar_4a": bar_4a(body["per_species"], res["species"], res["tp"], res["n_det"]),
        **({"class_collapse": collapse} if collapse is not None else {}),
        "_pairs": res["pairs"] if a.pairs is not None else None,
    }  # fmt: skip


def collapse_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--classes", type=Path, default=None,
                   help="a map-scoped model's class list: its species classes count as "
                        "'monster' (T-6); default: the rows as written (v1)")  # fmt: skip
    p.add_argument("--names", type=Path, default=None,
                   help="--classes: the model's names in id order (.names.json); default: the "
                        "boxes' .meta.json names")  # fmt: skip


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
    p.add_argument(
        "--boxes",
        type=Path,
        default=None,
        help="boxes.jsonl rows to score (default: DEMO/boxes.jsonl, v1 live)",
    )
    p.add_argument(
        "--sprites",
        type=Path,
        default=None,
        help="the decoded monster sprites (default: mvp_watch_study.SPRITES, gef10's)",
    )
    p.add_argument(
        "--sprite-names",
        type=Path,
        default=None,
        help="the client stems (default: mvp_watch_study.SPRITE_NAMES)",
    )
    collapse_flags(p)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("score-session", help="a recorder session (rogue-xmas02.md 4A)")
    p.add_argument("session", type=Path, help="record_session.py's dir (manifest + PNG shards)")
    p.add_argument("--boxes", type=Path, default=None, help="recorder_boxes.py predict's rows")
    p.add_argument(
        "--preflight",
        action="store_true",
        help="check the inputs (session, GAT, map cache, sprites, rows) and stop",
    )
    p.add_argument("--map", required=True)
    p.add_argument("--layout", choices=("standard", "hunt"), default="hunt")
    p.add_argument(
        "--chat",
        default="auto",
        help="the chat window: auto (chat_window.for_sid), legacy, standard, X0,Y0,X1,Y1",
    )
    p.add_argument(
        "--ui-boxes",
        choices=("drop", "keep"),
        default="drop",
        help="detections >= half behind the UI windows: left out (4A) or kept",
    )
    p.add_argument("--sprites", type=Path, required=True, help="the map's decoded sprites")
    p.add_argument("--sprite-names", type=Path, required=True, help="their client stems")
    p.add_argument("--kb", type=Path, default=MAIN / "data" / "kb")
    p.add_argument(
        "--mapcache-dir",
        type=Path,
        default=MAIN / "packages/poring_dataset/src/poring_dataset/_generated",
    )
    p.add_argument("--allow-partial", action="store_true", help="score frames that have rows")
    p.add_argument("--pairs", type=Path, default=None, help="every scored capture (by-eye)")
    collapse_flags(p)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("from-predict")
    p.add_argument("pred", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "from-predict":
        rows = predict_rows(json.loads(a.pred.read_text()))
        a.out.write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(json.dumps({"rows": len(rows), "out": str(a.out)}))
        return 0
    if a.cmd == "score":
        import mvp_watch_study as mws

        a.sprites = mws.SPRITES if a.sprites is None else a.sprites
        a.sprite_names = mws.SPRITE_NAMES if a.sprite_names is None else a.sprite_names
        out = cmd_score(a)
    else:
        out = cmd_score_session(a)
    pairs = out.pop("_pairs")
    if a.pairs is not None:
        a.pairs.write_text(json.dumps(pairs) + "\n")
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
