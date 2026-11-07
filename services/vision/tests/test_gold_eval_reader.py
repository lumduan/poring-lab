"""ADR-0018 route A (Batt 2026-11-07): scripts/gold_eval.py (Apache-2.0) reads frame-cache shards
with its OWN reader instead of importing poring_vision.shards. Here, on the AGPL side (which may
import Apache code, never the reverse), both readers must agree on the same shard: keys, offsets,
sizes, labels and sessions, in member order."""

from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path

import numpy as np

from poring_vision import shards

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import gold_eval  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + bytes(40)


def add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def test_gold_evals_reader_agrees_with_the_trainers(tmp_path: Path) -> None:
    shard = tmp_path / "shard-000000.tar"
    with tarfile.open(shard, "w") as tar:
        add(tar, "s1.000001.png", PNG)
        add(tar, "s1.000001.txt", b"1 0.5 0.25 0.1 0.2\n3 0.123457 0.9 0.05 0.07\n")
        add(tar, "s1.000001.json", json.dumps({"session": "s1"}).encode())
        add(tar, "s2.000007.jpg", b"\xff\xd8" + bytes(30))
        add(tar, "s2.000007.txt", b"")
        add(tar, "s2.000007.json", json.dumps({"session": "s2"}).encode())
        add(tar, "s3.000002.png", PNG + b"x")  # no labels, no session
    ours = gold_eval.index_cache_shard(shard)
    theirs = shards.index_shard(shard)
    assert [s.key for s in ours] == [s.key for s in theirs] == ["s1.000001", "s2.000007",
                                                                "s3.000002"]  # fmt: skip
    for a, b in zip(ours, theirs, strict=True):
        assert (a.shard, a.offset, a.size, a.session) == (b.shard, b.offset, b.size, b.session)
        assert a.labels.dtype == b.labels.dtype == np.float32
        assert np.array_equal(a.labels, b.labels) and a.labels.shape == b.labels.shape
    with shard.open("rb") as fh:  # the offsets point at the images' first bytes
        fh.seek(ours[0].offset)
        assert fh.read(ours[0].size) == PNG
