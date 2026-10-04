"""poring_vision.shards: the training frame cache reader (host-testable, no torch)."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest

from poring_vision.shards import index_shard, load_split, parse_yolo, read_jpeg


def add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def make_cache(root: Path) -> Path:
    cache = root / "v0-test"
    cache.mkdir()
    sessions = {"s-a": "train", "s-b": "train", "s-c": "val"}
    with tarfile.open(cache / "shard-000000.tar", "w") as tar:
        for sid in sessions:
            for i in range(3):
                key = f"{sid}.{i:09d}"
                add(tar, f"{key}.jpg", f"JPEG-{key}".encode())
                add(tar, f"{key}.txt", b"1 0.5 0.5 0.1 0.2\n" if i else b"")
                add(tar, f"{key}.json", json.dumps({"session": sid, "frame_id": i}).encode())
    split = {"train": ["s-a", "s-b"], "val": ["s-c"], "test": []}
    rows = {sid: {"split": p, "shards": ["shard-000000.tar"]} for sid, p in sessions.items()}
    manifest = {"names": {"0": "player", "1": "monster", "2": "npc"}, "sessions": rows}
    (cache / "manifest.json").write_text(json.dumps(manifest))
    (cache / "split.json").write_text(json.dumps(split))
    return cache


def test_yolo_lines() -> None:
    arr = parse_yolo("1 0.5 0.5 0.1 0.2\n0 0.1 0.2 0.3 0.4\n")
    assert arr.shape == (2, 5) and arr.dtype == np.float32
    assert parse_yolo("").shape == (0, 5)
    with pytest.raises(ValueError):
        parse_yolo("1 0.5 0.5\n")


def test_index_and_read_one_seek(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    samples = index_shard(cache / "shard-000000.tar")
    assert len(samples) == 9
    s = samples[4]
    assert read_jpeg(s) == f"JPEG-{s.key}".encode()
    assert s.labels.shape == (1, 5) and samples[0].labels.shape == (0, 5)


def test_the_split_is_by_session(tmp_path: Path) -> None:
    cache = make_cache(tmp_path)
    train, names = load_split(cache, "train")
    val, _ = load_split(cache, "val")
    assert {s.session for s in train} == {"s-a", "s-b"} and len(train) == 6
    assert {s.session for s in val} == {"s-c"}
    assert names == {0: "player", 1: "monster", 2: "npc"}
    capped, _ = load_split(cache, "train", limit_per_session=2)
    assert len(capped) == 4
