"""Read a training frame cache: tar shards on the NAS, mounted READ-ONLY (Phase 3 Part D).

The host writes it (scripts/build_frame_cache.py); vision only reads it. A cache directory holds:
    manifest.json        cache_id, names (class id -> name), split, per-session rows, shard sha256s
    split.json           {"train": [session ids], "val": [...], "test": [...]} -- BY SESSION
    shard-NNNNNN.tar     per frame: <key>.jpg (JPEG q95, the 1280x720 game region),
                         <key>.txt (YOLO lines: cls cx cy w h, normalised), <key>.json (meta)

Pure tarfile + numpy (host-testable without torch). A sample keeps the JPEG's byte offset inside
its shard, so a read is one seek; the labels are parsed up front (they are small).
"""

from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True, slots=True)
class Sample:
    key: str
    shard: Path
    offset: int  # the JPEG's first byte inside the shard
    size: int
    labels: npt.NDArray[np.float32]  # (n, 5): cls cx cy w h, normalised
    session: str


EMPTY = np.zeros((0, 5), np.float32)


def parse_yolo(text: str) -> npt.NDArray[np.float32]:
    rows = [line.split() for line in text.splitlines() if line.strip()]
    if not rows:
        return np.zeros((0, 5), np.float32)
    arr = np.asarray(rows, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 5:
        raise ValueError(f"not YOLO detection lines: shape {arr.shape}")
    return arr


def index_shard(path: Path) -> list[Sample]:
    """Every frame in a shard: the JPEG's offset/size and the parsed labels (in member order)."""
    jpgs: dict[str, tuple[int, int]] = {}
    labels: dict[str, npt.NDArray[np.float32]] = {}
    sessions: dict[str, str] = {}
    with tarfile.open(path, "r") as tar:
        for m in tar:
            key, _, ext = m.name.rpartition(".")
            if ext == "jpg":
                jpgs[key] = (m.offset_data, m.size)
            elif ext in ("txt", "json"):
                fh = tar.extractfile(m)
                assert fh is not None
                data = fh.read().decode()
                if ext == "txt":
                    labels[key] = parse_yolo(data)
                else:
                    sessions[key] = str(json.loads(data).get("session", ""))
    return [
        Sample(key, path, off, size, labels.get(key, EMPTY), sessions.get(key, ""))
        for key, (off, size) in jpgs.items()
    ]


def read_jpeg(sample: Sample) -> bytes:
    with sample.shard.open("rb") as fh:
        fh.seek(sample.offset)
        data = fh.read(sample.size)
    if len(data) != sample.size:
        raise OSError(f"{sample.shard.name}: short read for {sample.key}")
    return data


def load_split(
    cache: Path,
    split: str,
    *,
    limit_per_session: int | None = None,
    sessions: list[str] | None = None,
) -> tuple[list[Sample], dict[int, str]]:
    """The samples of one split (in shard order) and the class names; ``sessions`` narrows the
    split to those sessions (an evaluation per session, e.g. the gold set alone)."""
    manifest = json.loads((cache / "manifest.json").read_text())
    wanted = set(json.loads((cache / "split.json").read_text())[split])
    if sessions is not None:
        unknown = set(sessions) - wanted
        if unknown:
            raise ValueError(f"not in the {split} split: {sorted(unknown)}")
        wanted = set(sessions)
    names = {int(k): str(v) for k, v in manifest["names"].items()}
    shards = sorted({s for sid in wanted for s in manifest["sessions"][sid]["shards"]})
    out: list[Sample] = []
    per_session: dict[str, int] = {}
    for shard in shards:
        for s in index_shard(cache / shard):
            if s.session not in wanted:
                continue
            n = per_session.get(s.session, 0)
            if limit_per_session is not None and n >= limit_per_session:
                continue
            per_session[s.session] = n + 1
            out.append(s)
    return out, names
