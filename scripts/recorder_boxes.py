#!/usr/bin/env python3
"""THE LIVE v1 DETECTOR ON A RECORDED SESSION, on CPU (docs/planning/rogue-xmas02.md 4A, X2).

    recorder_boxes.py predict SRC --out BOXES.jsonl [--model ONNX] [--threads 2] [--resume]
                              [--max-frames N] [--times ROWS.jsonl]
    recorder_boxes.py compare A.jsonl B.jsonl [--iou 0.5] --out JSON

``predict`` runs ``unit_detector.UnitDetector`` (the walk gate's CPU path: the v1 ONNX
``v1png-last-736x1280.onnx``, onnxruntime, conf 0.25, NMS IoU 0.5) on every frame of SRC and writes
one ``boxes.jsonl`` row per frame, the row human_demo.py logs live (scripts/human_demo.py
``_detect``), keyed by the frame's capture time plus its frame id:

    {"t": t_mono_ns, "frame_id": N, "ms": inference ms,
     "boxes": [[x0, y0, x1, y1, score, cls], ...]}          (game-region px, 1 / 3 decimals)

WHY boxes.jsonl and not predict_dir's JSON: the scorer (detector_vs_packets.py ``score --boxes`` /
``score-session``) reads exactly these rows and keys every capture by its CLOCK_MONOTONIC time,
the packets' clock; predict_dir's JSON keys frames by file stems that only a converter
(``from-predict``) turns into times. The same row format as the live log means one reader for the
live boxes and the CPU boxes, so the positive control compares them like with like. Rows are
appended and flushed one by one: a stopped run keeps what it did and ``--resume`` skips the frame
ids already written. A sidecar ``BOXES.jsonl.meta.json`` records the source, the model (sha256),
the settings, the counts and whether every frame of the source has a row.

SRC is either
- a RECORDER session (scripts/record_session.py), read through poring_dataset.frames: PNG
  (``manifest.json`` + ``shard-NNNNNN.tar`` holding ``NNNNNNNNN.png`` + ``NNNNNNNNN.json``
  {frame_id, t_mono_ns, ...}): each shard is STREAMED front to back (tarfile mode "r|", one read,
  nothing extracted to disk or /dev/shm); a frame is decoded once both of its members were read; a
  truncated shard ends at its cut and is reported. Or an RDP VIDEO session (ADR-0024: video.hevc +
  video.idx.csv): every frame's access unit decoded alone, keyed by the index's frame id and
  capture time; a stream cut short by its encoder ends at its cut and is reported. A stage-2
  session is read from its PNG unless PORING_FRAME_SOURCE=video (its twin); the meta records
  which (``frame_source``);
- or a FRAMES DIR whose file stems carry the capture time (human_demo.py's 5 Hz recorder:
  ``frames/NNNNN-<t ns>.jpg``), for the positive control on a human demo. ``--times ROWS.jsonl``
  keeps only the frames whose time is one of those rows' ``t`` (the demo's live captures).

``compare`` matches two box files at their SHARED capture times (each class on its own, greedy by
IoU, a pair at IoU >= --iou): how many boxes each side has, how many pair up, their IoU and score
differences, and the frames whose box sets agree.

A MAP-SCOPED model's rows (docs/planning/xmas02-detector.md 7, D1 / D2; tool gap T-6) carry its own
class names (one per tier species, e.g. ``mystcase``, ``cookie_xmas``), while the scorer counts
``monster`` only. ``class_collapse`` reads the model's committed CLASS LIST (the
build_frame_cache ``--class-list`` format: ``fixed`` names at fixed ids, ``monster_first_id``, one
class per entry of ``monsters``, optional ``appended``; plan 7's ``classes-xmas02.json`` is
``{"fixed": {"player": 0}, "monster_first_id": 1, ...}``; an entry may be a LIST of mob ids, one
merged class such as 6's ``cookie_any``) against the model's names in id order (its
``.names.json`` sidecar, which ``predict``'s meta records as ``names``) and maps every monster
class to ``monster``, keeping the others; ``collapse_rows`` applies it to rows (a class the model
does not have fails). detector_vs_packets.py ``--classes`` scores through it; without the flag a
row is scored as written (v1's ``player`` / ``monster`` / ``npc`` rows unchanged).

Pixels in only (rule 1): no packets, no client, no input, no GPU. The process lowers itself to
nice 19 before the worker starts (the worker inherits it); run it under the brief's cap as well:
``systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% nice -n 19``.
``--threads`` (default 2, the cap's two cores) is the worker's onnxruntime threads; the live
detector runs 8. Client pixels are never written: the output holds boxes only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from poring_dataset import frames as recorded  # noqa: E402

NICE = 19
THREADS = 2  # the brief's CPUQuota=200 %: two cores (the live detector runs unit_detector.THREADS)
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
# (the frame's meta: frame_id, t_mono_ns; its image bytes, or a loader that decodes it to BGR)
Frame = tuple[dict[str, Any], bytes | Callable[[], Any]]


# --- reading frames (pure parts on bytes) ------------------------------------------------------

ShardCut = recorded.ShardCut  # moved to poring_dataset.frames (2026-11-09), the same class


def iter_shard(path: Path) -> Iterator[tuple[dict[str, Any], bytes]]:
    """(meta, PNG bytes) per frame of ONE recorder shard, in member order, the tar STREAMED (mode
    "r|": read once, front to back, nothing extracted). A frame is yielded once both of its
    members (``NNNNNNNNN.png``, ``NNNNNNNNN.json``) were read; the json's ``frame_id`` must be the
    member key's. A CUT shard raises ShardCut AFTER the complete frames before it: a member cut
    short, a member left without its pair, or no end-of-archive marker (two zero blocks) where
    the members end -- tarfile ends a stream at a cut header silently, so the marker is read.
    (poring_dataset.frames.iter_png_shard since 2026-11-09.)"""
    try:
        yield from recorded.iter_png_shard(path)
    except ValueError as e:  # a json that names another frame than its member key
        raise SystemExit(str(e)) from e


def iter_session(session: Path, manifest: dict[str, Any], cuts: list[str] | None = None
                 ) -> Iterator[tuple[dict[str, Any], bytes]]:  # fmt: skip
    """Every frame's PNG bytes of a PNG recorder session, shard by shard in the manifest's order.
    A missing shard or a cut is noted in ``cuts`` (when given) and the next shard follows
    (mvp_watch_study's png_index keeps the same frames). A video session (ADR-0024) has no PNG and
    is refused (FrameSourceError): ``session_frames`` reads either."""
    try:
        yield from recorded.iter_png_session(session, manifest, cuts)
    except recorded.FrameSourceError:
        raise
    except ValueError as e:  # a json that names another frame than its member key
        raise SystemExit(str(e)) from e


def session_frames(session: Path, manifest: dict[str, Any], cuts: list[str] | None = None
                   ) -> Iterator[Frame]:  # fmt: skip
    """Every frame of a recorder session, PNG or video (poring_dataset.frames.iter_frames), as
    (meta, loader): a frame skipped by --resume is never decoded."""
    yield from recorded.iter_frames(session, manifest, cuts=cuts)


def frame_stem(name: str) -> tuple[int, int] | None:
    """PURE: ``NNNNN-<t ns>.jpg`` (human_demo's frame names) -> (frame number, t ns); else None."""
    stem, dot, ext = name.rpartition(".")
    if not dot or "." + ext.lower() not in IMAGE_EXTS:
        return None
    n, sep, t = stem.partition("-")
    if not sep or not n.isdigit() or not t.isdigit():
        return None
    return int(n), int(t)


def iter_frames_dir(directory: Path, times: set[int] | None = None) -> Iterator[Frame]:
    """(meta, image bytes) per ``NNNNN-<t ns>.<jpg|png>`` file of ``directory`` in name order
    (``ls`` of ONE directory, no walk); ``times``: only the files whose t is in it."""
    for name in sorted(os.listdir(directory)):
        parsed = frame_stem(name)
        if parsed is None or (times is not None and parsed[1] not in times):
            continue
        n, t = parsed
        yield {"frame_id": n, "t_mono_ns": t}, (directory / name).read_bytes()


def decode_bgr(data: Any) -> Any:
    """A PNG / JPEG as BGR uint8 (map_labels.read_png's and eval_latency's decoding: PIL RGB,
    channels reversed): the order UnitDetector.detect takes, as a live grab gives it. A loader (a
    recorder session's frame: poring_dataset.frames) is called instead: it decodes to BGR."""
    if callable(data):
        return data()
    from PIL import Image

    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def box_row(t: int, frame_id: int, ms: float, boxes: Iterable[Any]) -> dict[str, Any]:
    """PURE: human_demo's boxes.jsonl row (its rounding) plus the frame id."""
    return {"t": int(t), "frame_id": int(frame_id), "ms": round(float(ms), 1),
            "boxes": [[round(b.x0, 1), round(b.y0, 1), round(b.x1, 1), round(b.y1, 1),
                       round(b.score, 3), b.cls] for b in boxes]}  # fmt: skip


def read_rows(path: Path) -> list[dict[str, Any]]:
    """boxes.jsonl rows; a torn LAST line (a run killed mid-write) is dropped, any other bad
    line fails."""
    lines = path.read_text().splitlines() if path.exists() else []
    out = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1:
                break
            raise SystemExit(f"{path}:{i + 1}: not a JSON row") from None
    return out


# --- predicting ----------------------------------------------------------------------------------


def predict(frames: Iterable[Frame], detector: Any, out: Path, done: set[int] | None = None,
            max_frames: int | None = None, progress: Callable[[int, int], None] | None = None
            ) -> dict[str, Any]:  # fmt: skip
    """Every frame through ``detector`` (``detect(bgr)`` -> boxes, ``last_ms``), one row appended
    and flushed per frame to ``out``. ``done``: frame ids already written (skipped, not decoded);
    ``max_frames``: stop after this many NEW rows. Returns the counts."""
    done = set() if done is None else done
    new = skipped = 0
    seen: set[int] = set()
    stopped = False
    with out.open("a") as fh:
        for meta, data in frames:
            fid, t = int(meta["frame_id"]), int(meta["t_mono_ns"])
            if fid in seen:
                raise SystemExit(f"frame {fid} twice in the source")
            seen.add(fid)
            if fid in done:
                skipped += 1
                continue
            if max_frames is not None and new >= max_frames:
                stopped = True
                break
            boxes = detector.detect(decode_bgr(data))
            fh.write(json.dumps(box_row(t, fid, detector.last_ms, boxes)) + "\n")
            fh.flush()
            new += 1
            if progress is not None:
                progress(new, fid)
    return {"new_rows": new, "skipped_done": skipped, "frames_seen": len(seen),
            "stopped_at_max_frames": stopped}  # fmt: skip


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_session(src: Path) -> bool:
    """A recorder session: its manifest beside PNG shards or an RDP video (ADR-0024)."""
    shards = any(src.glob("shard-*.tar"))
    return (src / "manifest.json").exists() and (shards or (src / recorded.VIDEO_FILE).exists())


def cmd_predict(a: argparse.Namespace) -> dict[str, Any]:
    import unit_detector as ud

    src: Path = a.src
    out: Path = a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not a.resume:
        raise SystemExit(f"{out} exists: --resume to continue it, or remove it first")
    prior = read_rows(out) if a.resume else []
    if prior:  # rewrite without a torn last line before appending
        out.write_text("".join(json.dumps(r) + "\n" for r in prior))
    done = {int(r["frame_id"]) for r in prior}
    cuts: list[str] = []
    source = None
    if is_session(src):
        manifest = json.loads((src / "manifest.json").read_text())
        if manifest.get("format") not in ("png", recorded.VIDEO_FORMAT):
            raise SystemExit(f"{src}: format {manifest.get('format')!r}: only PNG or RDP video "
                             "sessions")  # fmt: skip
        source = recorded.frame_source(src, manifest)
        kind, sid = "recorder_session", str(manifest["session_id"])
        # the frames the source serves: PNG's manifest count; a video's index matched to its stream
        total = (manifest.get("frames") if source == "png"
                 else len(recorded.frame_refs(src, manifest, source=source)))  # fmt: skip
        frames: Iterable[Frame] = session_frames(src, manifest, cuts)
    elif src.is_dir():
        times = None if a.times is None else {int(r["t"]) for r in read_rows(a.times)}
        kind, sid = "frames_dir", src.parent.name if src.name == "frames" else src.name
        total = sum(1 for n in os.listdir(src) if (p := frame_stem(n)) is not None
                    and (times is None or p[1] in times))  # fmt: skip
        frames = iter_frames_dir(src, times)
    else:
        raise SystemExit(f"{src}: neither a recorder session nor a frames dir")
    now = os.nice(0)
    if now < NICE:
        os.nice(NICE - now)
    t_start = time.time()
    started = time.strftime("%FT%T%z")

    def progress(n: int, fid: int) -> None:
        if n % 50 == 0:
            rate = n / max(time.time() - t_start, 1e-9)
            print(f"{time.strftime('%T')} {n} new rows (frame {fid}), {rate:.2f} frames/s",
                  file=sys.stderr, flush=True)  # fmt: skip

    with ud.UnitDetector(model=a.model, threads=a.threads) as det:
        counts = predict(frames, det, out, done, a.max_frames, progress)
        names = list(det.names)
    rows = read_rows(out)
    meta = {"what": "v1 (unit_detector.UnitDetector, CPU ONNX) on every frame of a recorded "
                    "source: boxes.jsonl rows keyed by capture time (rogue-xmas02.md 4A)",
            "source": str(src), "kind": kind, "session_id": sid, "frame_source": source,
            "model": str(a.model), "model_sha256": sha256(a.model), "names": names,
            "conf": ud.CONF, "iou": ud.IOU, "threads": a.threads, "nice": os.nice(0),
            "frames_in_source": total, "rows": len(rows),
            "complete": total is not None and len({int(r["frame_id"]) for r in rows}) == total,
            "shard_cuts": cuts, "run": {**counts, "started": started,
                                        "ended": time.strftime("%FT%T%z"),
                                        "seconds": round(time.time() - t_start, 1)}}  # fmt: skip
    prev = out.with_name(out.name + ".meta.json")
    if a.resume and prev.exists():
        meta["earlier_runs"] = [*json.loads(prev.read_text()).get("earlier_runs", []),
                                json.loads(prev.read_text())["run"]]  # fmt: skip
    prev.write_text(json.dumps(meta, indent=1) + "\n")
    return meta


# --- a map-scoped model's classes, collapsed for the scorer (T-6) -------------------------------

SCORED_CLASS = "monster"  # the class detector_vs_packets counts (detector_vs_packets.py:513)


def class_collapse(classes: dict[str, Any], names: Sequence[str]) -> dict[str, str]:
    """PURE: the model's class name -> the class the scorer counts. The class list's MONSTER
    classes (ids ``monster_first_id`` .. + len(``monsters``)) become ``monster``; its ``fixed``
    and ``appended`` classes keep their names. ``names``: the model's names in id order. Refused
    (fail closed: the list is not this model's): ids that are not exactly 0..len(names)-1, a
    repeated id, a fixed / appended name that is not the model's name at its id, a monster class
    named like a fixed one, no ``player`` (our own box)."""
    fixed = {str(k): int(v) for k, v in (classes.get("fixed") or {}).items()}
    appended = {str(k): int(v) for k, v in (classes.get("appended") or {}).items()}
    monsters = list(classes.get("monsters") or [])
    first = int(classes["monster_first_id"])
    mids = list(range(first, first + len(monsters)))
    ids = [*fixed.values(), *mids, *appended.values()]
    if "player" not in fixed:
        raise SystemExit("the class list has no fixed 'player' class (our own box)")
    if sorted(ids) != list(range(len(names))):
        raise SystemExit(f"the class list's ids {sorted(ids)} are not the model's {len(names)} "
                         f"class ids 0..{len(names) - 1}: not this model's list")  # fmt: skip
    for name, cid in (*fixed.items(), *appended.items()):
        if names[cid] != name:
            raise SystemExit(f"class id {cid}: the list says {name!r}, the model {names[cid]!r}")
    out = {names[cid]: names[cid] for cid in (*fixed.values(), *appended.values())}
    for cid in mids:
        if names[cid] in out:
            raise SystemExit(f"monster class {cid} is named {names[cid]!r}, a kept class")
        out[names[cid]] = SCORED_CLASS
    return out


def collapse_rows(rows: Iterable[dict[str, Any]], mapping: dict[str, str]
                  ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: boxes.jsonl rows with each box's class (index 5) through ``mapping`` (new rows; the
    input is untouched). A class outside the mapping fails: the rows are another model's."""
    out = []
    for r in rows:
        boxes = []
        for b in r["boxes"]:
            if b[5] not in mapping:
                raise SystemExit(f"row t={r.get('t')}: class {b[5]!r} is not one of the model's "
                                 f"{sorted(mapping)}")  # fmt: skip
            boxes.append([*b[:5], mapping[b[5]], *b[6:]])
        out.append({**r, "boxes": boxes})
    return out


def class_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """PURE: boxes per class name over ``rows``."""
    c: dict[str, int] = {}
    for r in rows:
        for b in r["boxes"]:
            c[str(b[5])] = c.get(str(b[5]), 0) + 1
    return dict(sorted(c.items()))


# --- comparing two box files ---------------------------------------------------------------------


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_boxes(a: Sequence[Sequence[Any]], b: Sequence[Sequence[Any]], iou_min: float = 0.5
                ) -> list[tuple[int, int, float]]:  # fmt: skip
    """PURE: pairs (i, j, IoU) of SAME-class boxes, greedily by descending IoU, at >= iou_min."""
    cand = [(iou(x, y), i, j) for i, x in enumerate(a) for j, y in enumerate(b)
            if x[5] == y[5]]  # fmt: skip
    used_a: set[int] = set()
    used_b: set[int] = set()
    out = []
    for v, i, j in sorted(cand, key=lambda c: (-c[0], c[1], c[2])):
        if v >= iou_min and i not in used_a and j not in used_b:
            used_a.add(i)
            used_b.add(j)
            out.append((i, j, v))
    return out


def compare_rows(rows_a: Sequence[dict[str, Any]], rows_b: Sequence[dict[str, Any]],
                 iou_min: float = 0.5) -> dict[str, Any]:  # fmt: skip
    """PURE: the box agreement of two box files at their shared capture times."""
    by_a = {int(r["t"]): r["boxes"] for r in rows_a}
    by_b = {int(r["t"]): r["boxes"] for r in rows_b}
    shared = sorted(set(by_a) & set(by_b))
    n_a = n_b = n_pairs = same_sets = 0
    ious: list[float] = []
    dconf: list[float] = []
    per_cls: dict[str, dict[str, int]] = {}
    for t in shared:
        a, b = by_a[t], by_b[t]
        pairs = match_boxes(a, b, iou_min)
        n_a, n_b, n_pairs = n_a + len(a), n_b + len(b), n_pairs + len(pairs)
        same_sets += len(pairs) == len(a) == len(b)
        for i, j, v in pairs:
            ious.append(v)
            dconf.append(abs(float(a[i][4]) - float(b[j][4])))
        for side, boxes in (("a", a), ("b", b)):
            for x in boxes:
                per_cls.setdefault(str(x[5]), {"a": 0, "b": 0, "pairs": 0})[side] += 1
        for i, _j, _v in pairs:
            per_cls[str(a[i][5])]["pairs"] += 1

    def q(v: Sequence[float], p: float) -> float | None:
        return round(float(np.percentile(np.asarray(v, float), p)), 4) if v else None

    return {"shared_captures": len(shared), "only_a": len(set(by_a) - set(by_b)),
            "only_b": len(set(by_b) - set(by_a)), "iou_min": iou_min,
            "boxes_a": n_a, "boxes_b": n_b, "pairs": n_pairs,
            "paired_share_of_a": round(n_pairs / n_a, 4) if n_a else None,
            "paired_share_of_b": round(n_pairs / n_b, 4) if n_b else None,
            "captures_same_box_set": same_sets,
            "iou": {"median": q(ious, 50), "p5": q(ious, 5), "min": q(ious, 0)},
            "abs_score_diff": {"median": q(dconf, 50), "p95": q(dconf, 95), "max": q(dconf, 100)},
            "per_class": per_cls}  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    import unit_detector as ud

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("predict")
    p.add_argument("src", type=Path, help="a recorder session dir, or a frames dir (NNNNN-<t>.jpg)")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--model", type=Path, default=ud.MODEL)
    p.add_argument("--threads", type=int, default=THREADS)
    p.add_argument("--resume", action="store_true", help="continue OUT (skip its frame ids)")
    p.add_argument("--max-frames", type=int, default=None, help="stop after N new rows")
    p.add_argument("--times", type=Path, default=None,
                   help="frames dir only: keep the frames at these rows' t")  # fmt: skip
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    c.add_argument("--iou", type=float, default=0.5)
    c.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "predict":
        out = cmd_predict(a)
    else:
        out = {"a": str(a.a), "b": str(a.b),
               **compare_rows(read_rows(a.a), read_rows(a.b), a.iou)}  # fmt: skip
        a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
