#!/usr/bin/env python3
"""M10: a model against Batt's hand-checked gold set (model-vs-hand), scored exactly like B6's
auto-vs-hand (scripts/label_iou.py: the same per-class greedy match at IoU >= 0.5).

    gold_eval.py extract SESSION              the hand-checked frames -> data/train/eval/gold/
                                              SESSION/frames/<frame_id>.png (+ index.json:
                                              frame_id -> t_mono_ns); vision sees /data/...
    gold_eval.py score SESSION PRED.json ...  per run: per class + overall TP/FP/FN, P, R, mean IoU
        [--metric position]                   POSITION only (phase3-plan §5f): centre in the hand
                                              box, same class, one-to-one by centre distance
        [--collapse-species]                  every predicted class but player / npc / warp ->
                                              monster first (a per-species model on v1's classes)
        [--gold-dir DIR]                      the session's gold directory (its index.json);
                                              default data/train/eval/gold/SESSION
        [--handcheck PATH]                    default data/qa/handcheck/SESSION.json, else the
                                              copy `label_iou.py pin` put in the NAS session
    gold_eval.py score-cache PRED.json ...    G2 (v2orc-vs-v1.md, gef10-eval.md R2-2): a frame
        [--cache DIR] [--session S]           cache's held-out session, its own YOLO labels read
        [--split test] [--metric position]    from the shards IN PLACE as the truth, species
                                              collapsed on both sides; every PRED in ONE command
    gold_eval.py refs --out REFS.json         predict_dir --refs for that session's frames
        [--cache DIR] [--session S]           (container paths: /mnt/poring-lab-datasets ->
                                              /datasets)

PRED.json comes from `python -m poring_vision.predict_dir` in the vision container (GPU, guarded).
The frames are client-derived pixels: they stay in data/ or on the NAS, never committed.

G1 (gef10-eval.md R2-2), v1 and the new model in one command:

    S=20261004T103815-console-s2-indoor-v2; G=/mnt/poring-lab-datasets/archive/train/eval/gold/$S
    gold_eval.py score $S --metric position --collapse-species --gold-dir $G \
        $G/pred-v1png-20261008.json NEW.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import tarfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_q1  # noqa: E402
import label_iou  # noqa: E402

from poring_dataset import frames as recorded  # noqa: E402
from poring_dataset.shards import encode_png  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
OUT = ROOT / "data" / "train" / "eval" / "gold"
# G2: v1's cache and its prt_fild08 held-out session (v2orc-vs-v1.md)
CACHE = NAS / ".framecache" / "v1png-20261008"
G2_SESSION = "20261004T054429-console-s2-outdoor"
KEEP = ("player", "npc", "warp")  # every other class is a monster species


def handcheck_path(session: str, datasets: Path = NAS) -> Path:
    """The hand-check: data/qa/handcheck/SESSION.json, else its pinned NAS copy."""
    local = label_iou.HANDCHECK / f"{session}.json"
    pinned = datasets / session / "handcheck.json"
    return local if local.exists() or not pinned.exists() else pinned


def hand_of(session: str, path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or handcheck_path(session)).read_text())  # type: ignore[no-any-return]


def extract(session: str, datasets: Path) -> int:
    hand = hand_of(session)
    want = {int(f["frame_id"]) for f in hand["frames"]}
    src = datasets / session
    manifest = json.loads((src / "manifest.json").read_text())
    dest = OUT / session / "frames"
    dest.mkdir(parents=True, exist_ok=True)
    index: dict[str, int] = {}
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        pairs: Any = H264Session(src).frames(sorted(want))
    else:  # PNG shards or an RDP video (ADR-0024): only the wanted frames are read and decoded
        refs = [r for r in recorded.frame_refs(src, manifest) if r.frame_id in want]
        pairs = ((r.meta(), recorded.read_ref(r)) for r in refs)
    for meta, img in pairs:
        fid = int(meta["frame_id"])
        if fid not in want or str(fid) in index:
            continue
        (dest / f"{fid}.png").write_bytes(encode_png(img))
        index[str(fid)] = int(meta["t_mono_ns"])
        if len(index) == len(want):
            break
    (OUT / session / "index.json").write_text(json.dumps(index, indent=1))
    missing = sorted(want - {int(k) for k in index})
    print(json.dumps({"session": session, "frames": len(index), "missing": missing,
                      "dir": str(dest)}))  # fmt: skip
    return 1 if missing else 0


def collapse(boxes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """PURE: every class but player / npc / warp becomes ``monster`` (G1 / G2: a per-species
    model scored on v1's classes; label_iou.CLASSES is player / monster / npc)."""
    return [{**b, "cls": b["cls"] if b["cls"] in KEEP else "monster"} for b in boxes]


def run_key(p: Mapping[str, Any], path: Path, out: Mapping[str, Any]) -> str:
    """The output key of one PRED: its weights (as before), its path too if two share them."""
    w = str(p["weights"])
    return w if w not in out else f"{w} ({path})"


def score(session: str, preds: list[Path], metric: str = "iou", *, collapse_species: bool = False,
          gold_dir: Path | None = None, handcheck: Path | None = None) -> int:  # fmt: skip
    hand = hand_of(session, handcheck)
    index = json.loads(((gold_dir or OUT / session) / "index.json").read_text())
    by_t = {int(t): fid for fid, t in index.items()}
    out: dict[str, Any] = {}
    for path in preds:
        p = json.loads(path.read_text())
        frames = p["frames"]
        if collapse_species:
            frames = {k: collapse(v) for k, v in frames.items()}
        scorer = label_iou.score_position if metric == "position" else label_iou.score
        result = scorer(hand, lambda t, f=frames: f.get(by_t.get(t, ""), None))
        extra = {"collapse_species": True} if collapse_species else {}
        out[run_key(p, path, out)] = {"conf": p["conf"], "imgsz": p["imgsz"], **extra, **result}
    print(json.dumps(out, indent=1))
    return 0


# --- G2: a frame cache's held-out session ----------------------------------------------------


# The frame cache's tar shards (scripts/build_frame_cache.py writes them): per frame <key>.png or
# <key>.jpg, <key>.txt (YOLO lines: cls cx cy w h, normalised) and <key>.json ({"session": ...}).
# gold_eval reads them with its OWN reader: this Apache-2.0 script imports nothing of the AGPL
# vision component (ADR-0018; Batt 2026-11-07 chose route A: until then it imported
# poring_vision.shards). services/vision/tests/test_gold_eval_reader.py checks that this reader and
# the trainer's (poring_vision.shards.index_shard) agree on the same shard.
CACHE_IMAGE_EXTS = ("png", "jpg")


@dataclass(frozen=True)
class CacheSample:
    key: str
    shard: Path
    offset: int  # the image's first byte inside the shard
    size: int
    labels: Any  # (n, 5) float32: cls cx cy w h, normalised
    session: str


def yolo_rows(text: str) -> Any:
    """PURE: YOLO detection lines -> an (n, 5) float32 array (n may be 0)."""
    rows = [line.split() for line in text.splitlines() if line.strip()]
    arr = np.asarray(rows, dtype=np.float32) if rows else np.zeros((0, 5), np.float32)
    if arr.ndim != 2 or arr.shape[1] != 5:
        raise ValueError(f"not YOLO detection lines: shape {arr.shape}")
    return arr


def index_cache_shard(path: Path) -> list[CacheSample]:
    """Every frame of a cache shard, in member order: the image's offset and size inside the tar
    (a read is one seek), its labels and its session. Only the small label members are read."""
    images: dict[str, tuple[int, int]] = {}
    labels: dict[str, Any] = {}
    sessions: dict[str, str] = {}
    with tarfile.open(path, "r") as tar:
        for m in tar:
            key, _, ext = m.name.rpartition(".")
            if ext in CACHE_IMAGE_EXTS:
                images[key] = (m.offset_data, m.size)
            elif ext in ("txt", "json"):
                fh = tar.extractfile(m)
                assert fh is not None
                text = fh.read().decode()
                if ext == "txt":
                    labels[key] = yolo_rows(text)
                else:
                    sessions[key] = str(json.loads(text).get("session", ""))
    empty = np.zeros((0, 5), np.float32)
    return [CacheSample(key, path, off, size, labels.get(key, empty), sessions.get(key, ""))
            for key, (off, size) in images.items()]  # fmt: skip


def png_size(head: bytes) -> tuple[int, int]:
    """PURE: (width, height) from a PNG's first 24 bytes (signature + IHDR)."""
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    w, h = struct.unpack(">II", head[16:24])
    return int(w), int(h)


def yolo_boxes(labels: Any, names: Mapping[int, str], size: tuple[int, int]
               ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: YOLO rows (cls cx cy w h, normalised) -> boxes in the frame's pixels."""
    w, h = size
    out = []
    for c, cx, cy, bw, bh in (tuple(float(v) for v in row) for row in labels):
        if int(c) not in names:
            raise ValueError(f"class id {int(c)} is not in the cache's names")
        out.append({"cls": names[int(c)], "x1": (cx - bw / 2) * w, "y1": (cy - bh / 2) * h,
                    "x2": (cx + bw / 2) * w, "y2": (cy + bh / 2) * h})  # fmt: skip
    return out


def cache_samples(cache: Path, session: str, split: str = "test"
                  ) -> tuple[list[Any], dict[int, str], dict[str, Any]]:  # fmt: skip
    """The session's samples in the cache (shard headers + label members only, read in place),
    sorted by key; the class names; the manifest. Fail closed on a split or count mismatch."""
    manifest = json.loads((cache / "manifest.json").read_text())
    if session not in json.loads((cache / "split.json").read_text())[split]:
        raise SystemExit(f"{session} is not in {cache.name}'s {split} split")
    row = manifest["sessions"][session]
    samples = [s for shard in row["shards"] for s in index_cache_shard(cache / shard)
               if s.session == session]  # fmt: skip
    if len(samples) != int(row["kept"]) or len({s.key for s in samples}) != len(samples):
        raise SystemExit(f"{session}: {len(samples)} samples in its shards, the manifest kept "
                         f"{row['kept']}")  # fmt: skip
    names = {int(k): str(v) for k, v in manifest["names"].items()}
    return sorted(samples, key=lambda s: s.key), names, manifest


def frame_size(sample: Any) -> tuple[int, int]:
    with sample.shard.open("rb") as fh:
        fh.seek(sample.offset)
        return png_size(fh.read(24))


def score_cache_truth(truth: Mapping[str, list[dict[str, Any]]],
                      preds: Sequence[tuple[Path, Mapping[str, Any]]], metric: str = "position"
                      ) -> dict[str, Any]:  # fmt: skip
    """PURE: each PRED against the same truth (key -> boxes), species collapsed on both sides;
    a PRED missing a frame is refused (an absent frame is never an empty one)."""
    keys = sorted(truth)
    hand = {"frames": [{"t_mono_ns": i, "boxes": collapse(truth[k])} for i, k in enumerate(keys)]}
    scorer: Callable[..., dict[str, Any]] = (
        label_iou.score_position if metric == "position" else label_iou.score
    )
    out: dict[str, Any] = {}
    for path, p in preds:
        frames = p["frames"]
        missing = [k for k in keys if k not in frames]
        if missing:
            raise SystemExit(f"{path}: {len(missing)} of {len(keys)} frames missing: {missing[:3]}")
        result = scorer(hand, lambda i, f=frames: collapse(f[keys[i]]))
        out[run_key(p, path, out)] = {"conf": p.get("conf"), "imgsz": p.get("imgsz"),
                                      "source": p.get("source"), **result}  # fmt: skip
    return out


def score_cache(preds: list[Path], cache: Path, session: str, split: str, metric: str) -> int:
    samples, names, manifest = cache_samples(cache, session, split)
    truth = {s.key: yolo_boxes(s.labels, names, frame_size(s)) for s in samples}
    loaded = [(p, json.loads(p.read_text())) for p in preds]
    res = score_cache_truth(truth, loaded, metric)
    print(json.dumps({"cache": str(cache), "cache_id": manifest.get("cache_id"),
                      "manifest_sha256": eval_q1.sha256_file(cache / "manifest.json"),
                      "session": session, "split": split, "frames": len(truth),
                      "truth_boxes": sum(len(v) for v in truth.values()),
                      "collapse_species": True, "metric": metric, "runs": res},
                     indent=1))  # fmt: skip
    return 0


def cache_refs(cache: Path, session: str, split: str, out: Path, host_root: Path,
               container_root: Path) -> int:  # fmt: skip
    samples, _names, _m = cache_samples(cache, session, split)
    refs = {s.key: {"path": eval_q1.to_container(s.shard, host_root, container_root),
                    "offset": s.offset, "size": s.size} for s in samples}  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(refs, indent=1) + "\n")
    print(json.dumps({"cache": str(cache), "session": session, "frames": len(refs),
                      "out": str(out)}))  # fmt: skip
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("session")
    ex.add_argument("--datasets", type=Path, default=NAS)
    sc = sub.add_parser("score")
    sc.add_argument("session")
    sc.add_argument("preds", type=Path, nargs="+")
    sc.add_argument("--metric", choices=("iou", "position"), default="iou")
    sc.add_argument(
        "--collapse-species",
        action="store_true",
        help="every predicted class but player / npc / warp -> monster",
    )
    sc.add_argument(
        "--gold-dir",
        type=Path,
        default=None,
        help="the session's gold dir (index.json); default data/train/eval/gold/S",
    )
    sc.add_argument("--handcheck", type=Path, default=None)
    for name in ("score-cache", "refs"):
        p = sub.add_parser(name)
        if name == "score-cache":
            p.add_argument("preds", type=Path, nargs="+")
            p.add_argument("--metric", choices=("iou", "position"), default="position")
        else:
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--host-root", type=Path, default=eval_q1.HOST_ROOT)
            p.add_argument("--container-root", type=Path, default=eval_q1.CONTAINER_ROOT)
        p.add_argument("--cache", type=Path, default=CACHE)
        p.add_argument("--session", default=G2_SESSION)
        p.add_argument("--split", default="test")
    a = ap.parse_args(argv)
    if a.cmd == "extract":
        return extract(a.session, a.datasets)
    if a.cmd == "score-cache":
        return score_cache(a.preds, a.cache, a.session, a.split, a.metric)
    if a.cmd == "refs":
        return cache_refs(a.cache, a.session, a.split, a.out, a.host_root, a.container_root)
    return score(a.session, a.preds, a.metric, collapse_species=a.collapse_species,
                 gold_dir=a.gold_dir, handcheck=a.handcheck)  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
