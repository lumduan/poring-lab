"""scripts/recorder_boxes.py (rogue-xmas02.md 4A, X2's CPU predictor): the recorder shards read as
a stream (pairing, keying, the colour order, a cut shard), human_demo's frame names, the per-frame
rows keyed by capture time with a FAKE detector (no onnxruntime), --resume, and the box
comparison. Synthetic sessions only (ShardWriter, the recorder's own writer): no NAS, no client."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import recorder_boxes as rb  # noqa: E402

from poring_dataset.shards import ShardWriter, write_manifest  # noqa: E402

T0 = 2_635_688_478_193_796  # X2's t0_mono_ns: a real CLOCK_MONOTONIC magnitude


def frame(i: int) -> np.ndarray:
    """A tiny BGR frame whose three channels differ (so a swapped order shows)."""
    img = np.zeros((4, 6, 3), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 10 + i, 100 + i, 200 + i
    return img


def make_session(root: Path, n: int, max_bytes: int = 1 << 20) -> tuple[Path, dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    w = ShardWriter(root, max_bytes=max_bytes)
    for i in range(n):
        w.add(i, T0 + i * 1_000_000_000 + 7, frame(i), source="bus", bus_frame_id=40 + i)
    w.close()
    manifest = {"session_id": "20261105T225409-rdp-test", "backend": "rdp", "format": "png",
                "recorder_version": 6, "game_region": [80, 77, 1280, 720],
                "server": "lab-rathena", "shards": w.shards, "frames": n}  # fmt: skip
    write_manifest(root, manifest)
    return root, manifest


def test_the_shards_stream_in_order_paired_and_keyed_by_capture_time(tmp_path: Path) -> None:
    session, manifest = make_session(tmp_path / "s", 5, max_bytes=2_000)  # several shards
    assert len(manifest["shards"]) > 1
    got = list(rb.iter_session(session, manifest))
    assert [m["frame_id"] for m, _ in got] == [0, 1, 2, 3, 4]
    assert [m["t_mono_ns"] for m, _ in got] == [T0 + i * 1_000_000_000 + 7 for i in range(5)]
    for i, (_m, data) in enumerate(got):  # BGR in, the same BGR out (the live grab's order)
        assert np.array_equal(rb.decode_bgr(data), frame(i))


def test_a_cut_shard_keeps_the_frames_before_the_cut_and_says_so(tmp_path: Path) -> None:
    """Cut mid-data, mid-header, at a member boundary and just before the end marker: the
    complete frames before the cut are kept and the cut is reported (tarfile alone would end a
    stream at a cut header without a word)."""
    import tarfile

    session, manifest = make_session(tmp_path / "s", 4)
    shard = session / manifest["shards"][-1]
    data = shard.read_bytes()
    with tarfile.open(shard) as tar:
        members = tar.getmembers()
    third = members[4]  # frame 2's png header: frames 0 and 1 are complete before it
    for cut, keep in ((third.offset, 2), (third.offset + 100, 2), (third.offset_data + 10, 2),
                      (members[-1].offset_data + members[-1].size, 4)):  # fmt: skip
        shard.write_bytes(data[:cut])
        cuts: list[str] = []
        got = list(rb.iter_session(session, manifest, cuts))
        assert [m["frame_id"] for m, _ in got] == list(range(keep)), cut
        assert len(cuts) == 1 and manifest["shards"][-1] in cuts[0], (cut, cuts)
    shard.write_bytes(data)  # whole again: no cut
    cuts = []
    assert len(list(rb.iter_session(session, manifest, cuts))) == 4 and cuts == []
    manifest["shards"].append("shard-000099.tar")  # a listed shard that is not there
    cuts = []
    list(rb.iter_session(session, manifest, cuts))
    assert cuts[-1] == "shard-000099.tar: missing"


def test_human_demo_frame_names_carry_the_capture_time(tmp_path: Path) -> None:
    assert rb.frame_stem("00012-1724661859600409.jpg") == (12, 1724661859600409)
    assert rb.frame_stem("00012-1724661859600409.PNG") == (12, 1724661859600409)
    for bad in ("00012.jpg", "x-12.jpg", "00012-12a.jpg", "00012-12.txt", "notes"):
        assert rb.frame_stem(bad) is None
    for n, t in ((1, 300), (0, 200), (2, 400)):
        (tmp_path / f"{n:05d}-{t}.jpg").write_bytes(b"x%d" % n)
    (tmp_path / "readme.txt").write_text("skip")
    assert [m["t_mono_ns"] for m, _ in rb.iter_frames_dir(tmp_path)] == [200, 300, 400]
    assert [m["frame_id"] for m, _ in rb.iter_frames_dir(tmp_path, {400, 200})] == [0, 2]


@dataclass(frozen=True)
class FakeBox:
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    cls: str


class FakeDetector:
    """Boxes from the pixels: one ``monster`` box whose x0 is the frame's blue value (so a row
    shows which frame it was computed on, and in which channel order)."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_ms = 0.0

    def detect(self, img: Any) -> list[FakeBox]:
        self.calls += 1
        self.last_ms = 123.456
        b = float(img[0, 0, 0])
        return [FakeBox(b + 0.04, 2.06, b + 30.0, 40.0, 0.87654, "monster")]


def test_predict_writes_one_row_per_frame_keyed_by_time_and_resumes(tmp_path: Path) -> None:
    session, manifest = make_session(tmp_path / "s", 5)
    out = tmp_path / "boxes.jsonl"
    det = FakeDetector()
    counts = rb.predict(rb.iter_session(session, manifest), det, out, max_frames=2)
    assert counts["new_rows"] == 2 and counts["stopped_at_max_frames"] is True
    rows = rb.read_rows(out)
    assert rows[0] == {"t": T0 + 7, "frame_id": 0, "ms": 123.5,
                       "boxes": [[10.0, 2.1, 40.0, 40.0, 0.877, "monster"]]}  # fmt: skip
    done = {r["frame_id"] for r in rows}
    counts = rb.predict(rb.iter_session(session, manifest), det, out, done=done)
    assert counts == {"new_rows": 3, "skipped_done": 2, "frames_seen": 5,
                      "stopped_at_max_frames": False}  # fmt: skip
    rows = rb.read_rows(out)
    assert [r["frame_id"] for r in rows] == [0, 1, 2, 3, 4] and det.calls == 5
    # the blue channel (BGR index 0) of frame i is 10 + i: each row was computed on its own frame
    assert [r["boxes"][0][0] for r in rows] == [10.0, 11.0, 12.0, 13.0, 14.0]
    assert [r["t"] for r in rows] == [T0 + i * 1_000_000_000 + 7 for i in range(5)]


def test_a_repeated_frame_id_is_refused(tmp_path: Path) -> None:
    frames = [({"frame_id": 1, "t_mono_ns": 5}, b""), ({"frame_id": 1, "t_mono_ns": 6}, b"")]
    det = FakeDetector()
    det.detect = lambda img: []  # type: ignore[method-assign]
    with pytest.raises(SystemExit):
        rb.predict(iter(frames), det, tmp_path / "o.jsonl", done={1})


def test_a_torn_last_line_is_dropped_any_other_bad_line_fails(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    p.write_text('{"t": 1, "boxes": []}\n{"t": 2, "box')
    assert rb.read_rows(p) == [{"t": 1, "boxes": []}]
    p.write_text('{"t": 1, "bo\n{"t": 2, "boxes": []}\n')
    with pytest.raises(SystemExit):
        rb.read_rows(p)
    assert rb.read_rows(tmp_path / "absent.jsonl") == []


def test_compare_pairs_same_class_boxes_by_iou_at_shared_times() -> None:
    a: list[dict[str, Any]] = [
        {"t": 1, "boxes": [[0, 0, 10, 10, 0.9, "monster"], [50, 50, 60, 60, 0.5, "monster"]]},
        {"t": 2, "boxes": [[0, 0, 10, 10, 0.4, "npc"]]},
        {"t": 3, "boxes": []},
    ]
    b: list[dict[str, Any]] = [
        {"t": 1, "boxes": [[1, 0, 11, 10, 0.8, "monster"]]},
        {"t": 2, "boxes": [[0, 0, 10, 10, 0.4, "monster"]]},  # same place, another class
        {"t": 9, "boxes": []},
    ]
    ((i, j, v),) = rb.match_boxes(a[0]["boxes"], b[0]["boxes"])
    assert (i, j) == (0, 0) and v == pytest.approx(9 / 11)
    c = rb.compare_rows(a, b)
    assert (c["shared_captures"], c["only_a"], c["only_b"]) == (2, 1, 1)
    assert (c["boxes_a"], c["boxes_b"], c["pairs"]) == (3, 2, 1)
    assert c["captures_same_box_set"] == 0 and c["abs_score_diff"]["max"] == pytest.approx(0.1)
    assert c["per_class"] == {"monster": {"a": 2, "b": 2, "pairs": 1},
                              "npc": {"a": 1, "b": 0, "pairs": 0}}  # fmt: skip
    same = rb.compare_rows(a, a)
    assert same["captures_same_box_set"] == 3 and same["iou"]["min"] == 1.0


def test_the_meta_sidecar_says_whether_every_frame_has_a_row(tmp_path: Path,
                                                             monkeypatch: Any) -> None:  # fmt: skip
    """cmd_predict end to end with the fake detector (UnitDetector replaced): the sidecar names
    the session, the model's sha256 and completeness; a second run without --resume refuses."""
    import unit_detector as ud

    session, _m = make_session(tmp_path / "s", 3)
    model = tmp_path / "m.onnx"
    model.write_bytes(b"not a model")

    class Fake(FakeDetector):
        names = ("player", "monster", "npc")

        def __init__(self, **_kw: Any) -> None:
            super().__init__()

        def __enter__(self) -> Fake:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(ud, "UnitDetector", Fake)
    monkeypatch.setattr(os, "nice", lambda inc: 19)  # never renice the test process
    out = tmp_path / "o" / "boxes.jsonl"
    rb.main(["predict", str(session), "--out", str(out), "--model", str(model),
             "--max-frames", "2"])  # fmt: skip
    meta = json.loads((tmp_path / "o" / "boxes.jsonl.meta.json").read_text())
    assert (meta["kind"], meta["session_id"], meta["rows"], meta["complete"]) == (
        "recorder_session", "20261105T225409-rdp-test", 2, False)  # fmt: skip
    assert meta["model_sha256"] == rb.sha256(model) and meta["threads"] == rb.THREADS
    with pytest.raises(SystemExit):
        rb.main(["predict", str(session), "--out", str(out), "--model", str(model)])
    rb.main(["predict", str(session), "--out", str(out), "--model", str(model), "--resume"])
    meta = json.loads((tmp_path / "o" / "boxes.jsonl.meta.json").read_text())
    assert meta["rows"] == 3 and meta["complete"] is True and len(meta["earlier_runs"]) == 1
