"""scripts/eval_latency.py (gef10-eval.md AMENDMENT R2-2): the CPU latency harness's own parts --
container -> host paths, the nearest-rank summary, the rotating model order, frames read in place,
and the loop with a fake detector (no onnxruntime)."""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import eval_latency as el  # noqa: E402


def test_host_path_maps_the_container_mount_only() -> None:
    assert (
        el.host_path("/datasets/x/shard-000000.tar")
        == "/mnt/poring-lab-datasets/x/shard-000000.tar"
    )
    assert el.host_path("/mnt/poring-lab-datasets/y.tar") == "/mnt/poring-lab-datasets/y.tar"
    assert el.host_path("/datasetsX/z") == "/datasetsX/z"


def test_summary_and_rotation() -> None:
    s = el.summary([float(x) for x in range(1, 201)])
    assert (s["p50"], s["p95"], s["max"]) == (100.0, 190.0, 200.0)
    assert el.summary([]) == {"n": 0}
    assert [el.rotation(["v1", "new"], i) for i in range(3)] == [["v1", "new"], ["new", "v1"],
                                                                  ["v1", "new"]]  # fmt: skip


def _png_shard(tmp_path: Path) -> dict[str, dict[str, Any]]:
    from PIL import Image

    path = tmp_path / "shard-000000.tar"
    with tarfile.open(path, "w") as tf:
        for i, colour in enumerate(((255, 0, 0), (0, 0, 255))):
            buf = io.BytesIO()
            Image.new("RGB", (4, 3), colour).save(buf, format="PNG")
            info = tarfile.TarInfo(f"{i:09d}.png")
            info.size = len(buf.getvalue())
            tf.addfile(info, io.BytesIO(buf.getvalue()))
    with tarfile.open(path) as tf:
        return {f"s.{m.name[:-4]}": {"path": str(path), "offset": m.offset_data, "size": m.size}
                for m in tf}  # fmt: skip


def test_frames_are_read_in_place_as_bgr(tmp_path: Path) -> None:
    refs = _png_shard(tmp_path)
    red = el.read_frame(refs["s.000000000"])
    assert red.shape == (3, 4, 3) and tuple(red[0, 0]) == (0, 0, 255)  # BGR: red is the last byte


def test_run_interleaves_the_models_on_the_same_frames(tmp_path: Path) -> None:
    refs = _png_shard(tmp_path)
    calls: list[tuple[str, int]] = []

    class Fake:
        def __init__(self, path: Path) -> None:
            self.name, self.last_ms, self.closed = path.name, 0.0, False

        def detect(self, img: Any) -> list[int]:
            calls.append((self.name, int(np.asarray(img)[0, 0, 2])))
            self.last_ms = 10.0 if self.name == "a.onnx" else 30.0
            return [1, 2]

        def close(self) -> None:
            self.closed = True

    out = el.run(refs, {"a": Path("a.onnx"), "b": Path("b.onnx")}, Fake)
    assert calls == [("a.onnx", 255), ("b.onnx", 255), ("b.onnx", 0), ("a.onnx", 0)]
    assert out["a"]["p50"] == 10.0 and out["b"]["p95"] == 30.0
    assert out["a"]["n"] == 2 and out["a"]["boxes"] == 4
