#!/usr/bin/env python3
"""Build a training frame cache: TAR SHARDS on the NAS (Phase 3 Part D, Batt 2026-10-04).

    build_frame_cache.py --train S [S ...] --val S [S ...] [--test S [S ...]]
                         [--cache-id ID] [--every 15] [--max-per-session N] [--labels v0]
                         [--out /mnt/poring-lab-datasets/.framecache] [--shard-mb 512]
                         [--quality 95]

Batt's rules (2026-10-04): vision reads the NAS READ-ONLY, and a frame cache is SHARDED (large
files), never one file per frame on the shared disk. So:
- this runs on the HOST (it needs poring_dataset + PyAV; vision may not import them, test_guards);
- each session is decoded in ONE sequential pass (H264Session.iter_every: no seeking, the offline
  seek re-measure) or read shard by shard (PNG sessions); every ``--every``-th usable frame
  (freeze spans excluded) is kept;
- labels come from qa_export's Labeler (the same as /qa and label_iou: the backend's camera, the
  packet->frame offset, GM-command windows skipped). Frames on any map other than the session's
  scene maps (prt_fild08, prt_church) are skipped (p3-outdoor-b's stray minutes in prontera);
- frames are written as JPEG q95 + YOLO txt + json into ~512 MB tar shards under
  ``<out>/<cache_id>/``. That is a dot-directory on the NAS root: dataset_ship's
  sessions/status/prune skip it by design. Each shard is written as ``.part``, renamed, then
  re-hashed from the NAS (read back);
- the split is BY SESSION (adjacent frames leak). The gold hand-checked session goes to ``test``
  only.

Nothing lands on the root disk: frames are encoded in memory, and the shards go straight to the
NAS.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_export  # noqa: E402

from poring_dataset.labels import CLASSES  # noqa: E402
from poring_dataset.shards import read_shard  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
OUT = NAS / ".framecache"
SCENE_MAPS = {"prt_fild08", "prt_church"}
GOLD = "20261004T103815-console-s2-indoor-v2"


def session_frames(
    session: Path, manifest: dict[str, Any], every: int
) -> Iterator[tuple[Any, Any]]:
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        yield from H264Session(session).iter_every(every)
        return
    n = 0
    for shard in manifest["shards"]:
        for meta, img in read_shard(session / shard):
            n += 1
            if not (n - 1) % every:
                yield meta, img


def yolo_lines(boxes: list[dict[str, Any]], w: int, h: int) -> str:
    out = []
    for b in boxes:
        x0, y0 = max(0.0, b["x1"]), max(0.0, b["y1"])
        x1, y1 = min(float(w), b["x2"]), min(float(h), b["y2"])
        if x1 <= x0 or y1 <= y0:
            continue
        out.append(f"{CLASSES[b['cls']]} {(x0 + x1) / 2 / w:.6f} {(y0 + y1) / 2 / h:.6f} "
                   f"{(x1 - x0) / w:.6f} {(y1 - y0) / h:.6f}")  # fmt: skip
    return "\n".join(out) + ("\n" if out else "")


def jpeg(img_bgr: np.ndarray, quality: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img_bgr[:, :, ::-1])).save(buf, "JPEG", quality=quality)
    return buf.getvalue()


class ShardSink:
    """Rotating tar shards, each written as .part, renamed, and re-hashed from the NAS."""

    def __init__(self, directory: Path, max_bytes: int) -> None:
        self.dir, self.max_bytes = directory, max_bytes
        self.n, self.tar, self.path, self.size = 0, None, None, 0
        self.done: dict[str, dict[str, Any]] = {}
        self.members = 0

    def _open(self) -> None:
        self.path = self.dir / f"shard-{self.n:06d}.tar"
        self.tar = tarfile.open(self.path.with_suffix(".tar.part"), "w")  # noqa: SIM115
        self.size, self.members = 0, 0
        self.n += 1

    def add(self, key: str, files: dict[str, bytes]) -> str:
        if self.tar is None or self.size >= self.max_bytes:
            self.close()
            self._open()
        assert self.tar is not None and self.path is not None
        for ext, data in files.items():
            info = tarfile.TarInfo(f"{key}.{ext}")
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            self.tar.addfile(info, io.BytesIO(data))
            self.size += len(data) + 1024
            self.members += 1
        return self.path.name

    def close(self) -> None:
        if self.tar is None or self.path is None:
            return
        self.tar.close()
        part = self.path.with_suffix(".tar.part")
        part.replace(self.path)
        h = hashlib.sha256()
        with self.path.open("rb") as fh:  # read back from the NAS
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        self.done[self.path.name] = {"sha256": h.hexdigest(), "bytes": self.path.stat().st_size,
                                     "members": self.members}  # fmt: skip
        self.tar, self.path = None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--val", nargs="+", required=True)
    ap.add_argument("--test", nargs="*", default=[])
    ap.add_argument("--cache-id", default=None)
    ap.add_argument("--labels", choices=("v0",), default="v0")
    ap.add_argument("--every", type=int, default=15)
    ap.add_argument("--max-per-session", type=int, default=None)
    ap.add_argument("--datasets", type=Path, default=NAS)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--shard-mb", type=int, default=512)
    ap.add_argument("--quality", type=int, default=95)
    a = ap.parse_args()
    split = {"train": a.train, "val": a.val, "test": a.test}
    seen = [s for ss in split.values() for s in ss]
    if len(seen) != len(set(seen)):
        raise SystemExit("a session is in two splits: the split is BY SESSION")
    if GOLD in a.train or GOLD in a.val:
        raise SystemExit(f"{GOLD} is the hand-checked gold set: test only")
    cache_id = a.cache_id or f"{a.labels}-{time.strftime('%Y%m%dT%H%M%S')}"
    directory = a.out / cache_id
    if directory.exists():
        raise SystemExit(f"{directory} exists: pick another --cache-id")
    directory.mkdir(parents=True)
    sink = ShardSink(directory, a.shard_mb << 20)
    sessions: dict[str, Any] = {}
    t0 = time.monotonic()
    for part, ids in split.items():
        for sid in ids:
            path = a.datasets / sid
            manifest = json.loads((path / "manifest.json").read_text())
            labeler = qa_export.Labeler(path)
            w, h = labeler.size
            row = {"split": part, "format": manifest.get("format") or "png", "kept": 0,
                   "gm_window": 0, "off_scene": 0, "boxes": 0, "shards": []}  # fmt: skip
            for meta, img in session_frames(path, manifest, a.every):
                t = int(meta["t_mono_ns"])
                world_map = labeler.timeline.frame_world(t - int(labeler.offset_ms * 1e6)).map
                if world_map not in SCENE_MAPS:
                    row["off_scene"] += 1
                    continue
                boxes = labeler.boxes(t)
                if boxes is None:
                    row["gm_window"] += 1
                    continue
                key = f"{sid}.{int(meta['frame_id']):09d}"
                info = {"session": sid, "frame_id": int(meta["frame_id"]), "t_mono_ns": t,
                        "map": world_map, "labels": a.labels}  # fmt: skip
                shard = sink.add(key, {"jpg": jpeg(img, a.quality),
                                       "txt": yolo_lines(boxes, w, h).encode(),
                                       "json": json.dumps(info).encode()})  # fmt: skip
                if shard not in row["shards"]:
                    row["shards"].append(shard)
                row["kept"] += 1
                row["boxes"] += len(boxes)
                if a.max_per_session and row["kept"] >= a.max_per_session:
                    break
            sessions[sid] = row
            print(json.dumps({sid: row}), flush=True)
    sink.close()
    manifest = {
        "cache_id": cache_id, "labels": a.labels, "every": a.every, "quality": a.quality,
        "names": {v: k for k, v in sorted(CLASSES.items(), key=lambda kv: kv[1])},
        "split": split, "sessions": sessions, "shards": sink.done, "gold": GOLD,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "seconds": round(time.monotonic() - t0, 1),
    }  # fmt: skip
    for name, doc in (("manifest.json", manifest), ("split.json", split)):
        tmp = directory / f".{name}.part"
        tmp.write_text(json.dumps(doc, indent=1) + "\n")
        tmp.replace(directory / name)
        json.loads((directory / name).read_text())  # read back
    print(json.dumps({"cache": str(directory), "frames": sum(r["kept"] for r in sessions.values()),
                      "shards": len(sink.done), "seconds": manifest["seconds"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
