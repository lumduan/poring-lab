"""poring_vision.predict_dir's host-side parts (gef10-eval.md AMENDMENT R2-2): frames read IN PLACE
from a tar shard by (path, offset, size), and the latency summary. No GPU, no torch."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from poring_vision import predict_dir as pd


def _shard(tmp_path: Path) -> tuple[Path, dict[str, dict[str, object]]]:
    """A real tar with two members; their data offsets as tarfile reports them."""
    path = tmp_path / "shard-000000.tar"
    with tarfile.open(path, "w") as tf:
        for name, data in (("000000001.png", b"\x89PNG one"), ("000000002.png", b"\x89PNG two!")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    refs = {}
    with tarfile.open(path) as tf:
        for m in tf:
            refs[f"s:{m.name[:-4]}"] = {"path": str(path), "offset": m.offset_data, "size": m.size}
    return path, refs


def test_read_ref_returns_the_member_bytes_in_place(tmp_path: Path) -> None:
    _path, refs = _shard(tmp_path)
    assert pd.read_ref(refs["s:000000001"]) == b"\x89PNG one"
    assert pd.read_ref(refs["s:000000002"]) == b"\x89PNG two!"
    short = dict(refs["s:000000002"], size=10_000)
    with pytest.raises(SystemExit):
        pd.read_ref(short)  # a short read is an error, never a frame


def test_load_refs_checks_every_entry(tmp_path: Path) -> None:
    _path, refs = _shard(tmp_path)
    good = tmp_path / "refs.json"
    good.write_text(json.dumps(refs))
    assert list(pd.load_refs(good)) == ["s:000000001", "s:000000002"]
    for bad in (
        {},
        [],
        {"k": {"path": "x", "offset": 0}},
        {"k": {"path": "x", "offset": 0, "size": 0}},
    ):
        f = tmp_path / "bad.json"
        f.write_text(json.dumps(bad))
        with pytest.raises(SystemExit):
            pd.load_refs(f)


def test_timing_summary_nearest_rank() -> None:
    ms = [float(x) for x in range(1, 201)]  # 1..200 ms
    s = pd.timing_summary(ms)
    assert s == {"n": 200, "p50": 100.0, "p95": 190.0, "mean": 100.5, "max": 200.0}
    assert pd.percentile([5.0], 95) == 5.0
    assert pd.timing_summary([]) == {"n": 0}


def test_images_and_refs_are_exclusive_and_one_is_required() -> None:
    with pytest.raises(SystemExit):
        pd.main(["--weights", "w.pt", "--out", "o.json"])
    with pytest.raises(SystemExit):
        pd.main(["--weights", "w.pt", "--images", "d", "--refs", "r.json", "--out", "o.json"])
