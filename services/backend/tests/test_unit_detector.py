"""scripts/unit_detector.py: the class ids map to names by an explicit list (gef10-eval.md R2-2).

v1's three names stay the default, so the live detector is unchanged; a 26-class model gets its
names from the constructor or a sidecar next to its ONNX; an id beyond the names fails closed.
The worker is a stand-in that answers with fixed class ids (no onnxruntime here).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import unit_detector as ud  # noqa: E402

FAKE_WORKER = """
import json, struct, sys
ids = json.loads(open(sys.argv[1]).read())
while True:
    head = sys.stdin.buffer.read(8)
    if len(head) < 8:
        break
    h, w, _ = struct.unpack("<HHI", head)
    sys.stdin.buffer.read(h * w * 3)
    boxes = [[1.0, 2.0, 3.0, 4.0, 0.9, c] for c in ids]
    sys.stdout.write(json.dumps({"boxes": boxes, "ms": 1.5}) + "\\n")
    sys.stdout.flush()
"""
GEF10 = ["player", "npc", "warp", *(f"species_{i}" for i in range(3, 26))]


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "fake_worker.py"
    path.write_text(FAKE_WORKER)
    monkeypatch.setattr(ud, "WORKER", path)
    return path


def model_answering(tmp_path: Path, ids: list[int]) -> Path:
    """The fake worker reads the class ids to answer from the 'model' file."""
    model = tmp_path / "m-736x1280.onnx"
    model.write_text(json.dumps(ids))
    return model


def detect(model: Path, **kw: object) -> list[ud.Box]:
    with ud.UnitDetector(model=model, python=Path(sys.executable), **kw) as det:  # type: ignore[arg-type]
        return det.detect(np.zeros((4, 6, 3), np.uint8))


def test_v1_names_are_the_default_and_unchanged(worker: Path, tmp_path: Path) -> None:
    assert ud.NAMES == ("player", "monster", "npc")
    boxes = detect(model_answering(tmp_path, [1, 2, 0]))
    assert [b.cls for b in boxes] == ["monster", "npc", "player"]
    assert (boxes[0].x0, boxes[0].score) == (1.0, 0.9)


def test_an_id_beyond_the_names_fails_closed(worker: Path, tmp_path: Path) -> None:
    with pytest.raises(ud.ClassNamesMismatch, match="class id 22 is beyond its 3 names"):
        detect(model_answering(tmp_path, [1, 22]))
    assert issubclass(ud.ClassNamesMismatch, ud.DetectorUnavailable)  # rules must not click


def test_a_26_class_model_by_argument(worker: Path, tmp_path: Path) -> None:
    boxes = detect(model_answering(tmp_path, [22, 0, 25]), names=GEF10)
    assert [b.cls for b in boxes] == ["species_22", "player", "species_25"]
    with pytest.raises(ud.ClassNamesMismatch, match="class id 26"):
        detect(model_answering(tmp_path, [26]), names=GEF10)


def test_a_26_class_model_by_sidecar_list_or_manifest_names(worker: Path, tmp_path: Path) -> None:
    model = model_answering(tmp_path, [2, 21])
    side = ud.sidecar(model)
    assert side == tmp_path / "m-736x1280.names.json"
    side.write_text(json.dumps(GEF10))
    assert [b.cls for b in detect(model)] == ["warp", "species_21"]
    side.write_text(json.dumps({str(i): n for i, n in enumerate(GEF10)}))  # a manifest's names
    assert [b.cls for b in detect(model)] == ["warp", "species_21"]


def test_the_argument_wins_over_the_sidecar(tmp_path: Path) -> None:
    model = model_answering(tmp_path, [])
    ud.sidecar(model).write_text(json.dumps(GEF10))
    assert ud.names_for(model, ["a", "b", "c"]) == ("a", "b", "c")
    assert ud.names_for(model) == tuple(GEF10)
    assert ud.names_for(tmp_path / "other.onnx") == ud.NAMES


@pytest.mark.parametrize(
    "doc",
    [[], ["a", ""], ["a", "a"], {"0": "a", "2": "b"}, {"x": "a"}, {"0": "a", "00": "b"}],
)
def test_bad_names_are_refused(doc: object) -> None:
    with pytest.raises(ValueError):
        ud.parse_names(doc)  # type: ignore[arg-type]


def test_a_bad_sidecar_refuses_the_detector(worker: Path, tmp_path: Path) -> None:
    model = model_answering(tmp_path, [0])
    ud.sidecar(model).write_text(json.dumps({"0": "player", "2": "npc"}))
    with pytest.raises(ValueError, match="without a gap"):
        ud.UnitDetector(model=model, python=Path(sys.executable))


# --- the map-scoped model (Batt 2026-11-07: "use it"; xmas02-detector.md T-11) ------------------

XMAS02 = ["player", "npc", "warp", "mystcase", "cruiser", "cookie", "cookie_xmas"]
SPECIES = {s: "monster" for s in XMAS02[3:]}


def test_sixteen_threads_by_batts_decision() -> None:
    assert ud.THREADS == 16  # 2026-11-07; cpu-detector-speed.md 1 (never onnxruntime's auto)


def test_classes_renamed_to_one_name_share_one_nms_group() -> None:
    assert ud.nms_groups(XMAS02, SPECIES) == [0, 1, 2, 3, 3, 3, 3]
    assert ud.nms_groups(XMAS02, {}) == list(range(7))  # no collapse: one group per class
    assert ud.nms_groups(["a", "b", "c"], {"a": "x", "c": "x"}) == [0, 1, 0]


def test_collapse_renames_keeps_the_species_and_sends_the_groups(
    worker: Path, tmp_path: Path
) -> None:
    model = model_answering(tmp_path, [5, 6, 0, 3])
    with ud.UnitDetector(model=model, python=Path(sys.executable), names=XMAS02,
                         collapse=SPECIES) as det:  # fmt: skip
        boxes = det.detect(np.zeros((4, 6, 3), np.uint8))
        assert det.proc.args[-1] == "[0, 1, 2, 3, 3, 3, 3]"  # the worker's 6th argument
    assert [(b.cls, b.species) for b in boxes] == [
        ("monster", "cookie"),
        ("monster", "cookie_xmas"),
        ("player", None),
        ("monster", "mystcase"),
    ]
    plain = detect(model, names=XMAS02)  # no collapse: the names as they are, no groups argument
    assert [b.cls for b in plain] == ["cookie", "cookie_xmas", "player", "mystcase"]


def test_a_collapse_name_the_model_lacks_fails_closed(worker: Path, tmp_path: Path) -> None:
    with pytest.raises(ud.ClassNamesMismatch, match="not its classes"):
        detect(model_answering(tmp_path, [0]), names=XMAS02, collapse={"poring": "monster"})


def test_for_map_pins_the_file_and_falls_back_to_v1(
    worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "model").mkdir()
    onnx = tmp_path / "model" / "x-736x1280.onnx"
    onnx.write_text(json.dumps([6]))
    ud.sidecar(onnx).write_text(json.dumps(XMAS02))
    py = Path(sys.executable)
    monkeypatch.setitem(ud.MAP_MODELS, "test_map",
                        ud.MapModel(onnx.name, ud.file_sha256(onnx), SPECIES))  # fmt: skip
    with ud.for_map("test_map", env=tmp_path, python=py) as det:
        assert det.model == onnx
        assert [(b.cls, b.species) for b in det.detect(np.zeros((2, 2, 3), np.uint8))] == [
            ("monster", "cookie_xmas")
        ]
    onnx.write_text(json.dumps([5]))  # a different file under the pinned name
    with pytest.raises(ud.DetectorUnavailable, match="is not the deployed"):
        ud.for_map("test_map", env=tmp_path, python=py)
    with pytest.raises(ud.DetectorUnavailable, match="missing"):
        ud.for_map("xmas_dun02", env=tmp_path / "nowhere", python=py)
    v1 = model_answering(tmp_path, [1])
    with ud.for_map("prt_fild08", env=tmp_path, python=py, model=v1) as det:  # no entry: v1
        assert det.collapse == {} and [b.cls for b in det.detect(np.zeros((2, 2, 3), np.uint8))] \
            == ["monster"]  # fmt: skip
    with ud.for_map(None, env=tmp_path, python=py, model=v1) as det:
        assert det.collapse == {}


def test_the_deployed_xmas02_entry() -> None:
    spec = ud.MAP_MODELS["xmas_dun02"]
    assert spec.onnx == "xmas02-last-736x1280.onnx"
    assert spec.sha256.startswith("293dca92")  # xmas02-eval.md AMENDMENT 3's export
    assert sorted(spec.collapse) == sorted(XMAS02[3:]) and set(spec.collapse.values()) == {
        "monster"
    }


def test_the_worker_suppresses_a_group_together() -> None:
    import detector_worker as dw

    # two anchors on one sprite (cookie 0.9, cookie_xmas 0.8) + a far cruiser; 7 classes
    rows = []
    for (cx, cy), cid, sc in [((100, 100), 5, 0.9), ((102, 101), 6, 0.8), ((400, 300), 4, 0.7)]:
        scores = [0.0] * 7
        scores[cid] = sc
        rows.append([cx, cy, 40, 60, *scores])
    out = np.asarray(rows, np.float32).T[None]  # (1, 4 + nc, N)
    per_class = dw.decode(out, 1.0, 0, 0, 0.25, 0.5)
    grouped = dw.decode(out, 1.0, 0, 0, 0.25, 0.5, [0, 1, 2, 3, 3, 3, 3])
    assert sorted(int(r[5]) for r in per_class) == [4, 5, 6]  # the double box
    assert sorted(int(r[5]) for r in grouped) == [4, 5]  # one box, its own (higher) class
    assert [r for r in grouped if r[5] == 5] == [r for r in per_class if r[5] == 5]


# --- the GPU path (gpu-live-detector.md option A; ADR-0005 Amendment 2026-11-07) ---------------
# The host may not import poring_vision (ADR-0018), so a stand-in speaks the detect server's
# protocol here; services/vision/tests/test_detect_server.py runs the real server against this
# same client.
import os  # noqa: E402
import socket  # noqa: E402
import struct  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import detector_worker as dw  # noqa: E402

N_ANCH = 19320  # 736 x 1280 at strides 8 / 16 / 32


def head_out(nc: int, boxes: list[tuple[float, float, float, float, int, float]]) -> np.ndarray:
    """A raw head output (1, 4 + nc, N): each (cx, cy, w, h, class, score) in CANVAS pixels."""
    out = np.zeros((1, 4 + nc, N_ANCH), np.float32)
    for k, (cx, cy, w, h, c, sc) in enumerate(boxes):
        out[0, :4, k] = (cx, cy, w, h)
        out[0, 4 + c, k] = sc
    return out


class FakeServer:
    """The detect server's protocol: hello, then per frame a JSON line + float32 bytes. ``mode``:
    ok | silent (accepts, never answers: a paused worker) | silent_frames | wrong_sha | bad_shape
    | nan | close_after_one."""

    def __init__(self, path: Path, out: np.ndarray, mode: str = "ok",
                 weights: str = "v1") -> None:  # fmt: skip
        self.path, self.out, self.mode, self.weights = path, out, mode, weights
        self.conns = 0
        self.frames = 0
        self.srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.srv.bind(str(path))
        self.srv.listen(4)
        self.srv.settimeout(0.2)
        self.halt = threading.Event()
        self.held: list[socket.socket] = []
        self.th = threading.Thread(target=self.loop, daemon=True)
        self.th.start()

    def loop(self) -> None:
        while not self.halt.is_set():
            try:
                c, _ = self.srv.accept()
            except TimeoutError:
                continue
            self.conns += 1
            if self.mode == "silent":
                self.held.append(c)
                continue
            try:
                self.serve(c)
            except OSError:
                pass
            finally:
                c.close()

    def serve(self, c: socket.socket) -> None:
        c.settimeout(5)
        f = c.makefile("rb")
        doc = json.loads(f.readline())
        sha = ud.GPU_WEIGHTS[self.weights].sha256
        if self.mode == "wrong_sha":
            sha = "0" * 64
        c.sendall(json.dumps({"ok": True, "model": doc["model"], "sha256": sha,
                              "imgsz": [736, 1280], "shape": list(self.out.shape)}).encode()
                  + b"\n")  # fmt: skip
        while True:
            head = f.read(8)
            if len(head) < 8:
                return
            h, w, _ = struct.unpack("<HHI", head)
            f.read(h * w * 3)
            self.frames += 1
            if self.mode == "silent_frames":
                time.sleep(1.0)
                return
            out = self.out
            if self.mode == "bad_shape":
                out = out[:, :, :100]
            if self.mode == "nan":
                out = out.copy()
                out[0, 0, 0] = np.nan
            c.sendall(json.dumps({"shape": list(out.shape), "ms": 1.0}).encode() + b"\n"
                      + np.ascontiguousarray(out, "<f4").tobytes())  # fmt: skip
            if self.mode == "close_after_one":
                return

    def stop(self) -> None:
        self.halt.set()
        self.th.join(timeout=2)
        self.srv.close()
        for c in self.held:
            c.close()


@pytest.fixture
def private(tmp_path: Path) -> Path:
    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    d.chmod(0o700)
    return d


def gpu_det(model: Path, sock: Path, names: object = None, collapse: object = None,
            **kw: object) -> ud.GpuDetector:  # fmt: skip
    cpu = ud.UnitDetector(model=model, python=Path(sys.executable), names=names,  # type: ignore[arg-type]
                          collapse=collapse)  # type: ignore[arg-type]  # fmt: skip
    return ud.GpuDetector(cpu, kw.pop("weights", "v1"), socket_path=sock,  # type: ignore[arg-type]
                          **kw)  # type: ignore[arg-type]  # fmt: skip


FRAME = np.zeros((720, 1280, 3), np.uint8)
# one monster box, centre (100, 58) in the canvas = (100, 50) in the frame (8 px of top padding)
ONE_MONSTER = head_out(3, [(100.0, 58.0, 20.0, 30.0, 1, 0.9)])


def test_anchors_of_the_deployed_input() -> None:
    assert ud.anchors((736, 1280)) == N_ANCH
    assert ud.IMGSZ == (736, 1280)


def test_letterbox_is_pad_canvas_then_to_input_as_before() -> None:
    img = np.random.default_rng(3).integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    x, s, left, top = dw.letterbox(img, (736, 1280))
    canvas = np.full((736, 1280, 3), 114, np.uint8)
    canvas[8:728] = img
    old = canvas[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    assert (s, left, top) == (1.0, 0, 8) and np.array_equal(x, old)
    c2, *_ = dw.pad_canvas(img, (736, 1280))
    assert np.array_equal(c2, canvas)


def test_gpu_boxes_are_decoded_by_the_cpu_workers_own_code(worker: Path, tmp_path: Path,
                                                         private: Path) -> None:  # fmt: skip
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER)
    try:
        with gpu_det(model_answering(tmp_path, [0]), sock) as det:
            boxes = det.detect(FRAME)
            assert det.last_path == "gpu" and det.counts == {"gpu": 1}
            assert boxes == [ud.Box(90.0, 35.0, 110.0, 65.0, 0.9, "monster")]
            assert det.detect(FRAME) == boxes and srv.conns == 1  # one connection, kept
    finally:
        srv.stop()


def test_no_server_gives_the_cpus_boxes_and_retries_later(worker: Path, tmp_path: Path,
                                                         private: Path) -> None:  # fmt: skip
    now = [100.0]
    with gpu_det(model_answering(tmp_path, [1]), private / "detect.sock",
                 clock=lambda: now[0]) as det:  # fmt: skip
        assert det.detect(FRAME) == [ud.Box(1.0, 2.0, 3.0, 4.0, 0.9, "monster")]
        assert det.last_path == "cpu" and det.counts == {"fallback": 1}
        assert det.reasons == {"FileNotFoundError": 1}
        det.detect(FRAME)
        assert det.last_reason == "down"  # not retried within GPU_RETRY_S
        assert det.reasons == {"FileNotFoundError": 1}
        now[0] += ud.GPU_RETRY_S
        srv = FakeServer(private / "detect.sock", ONE_MONSTER)
        try:
            det.detect(FRAME)
            assert det.last_path == "gpu"  # back on the GPU after the retry time
        finally:
            srv.stop()


@pytest.mark.parametrize("mode", ["silent", "silent_frames"])
def test_a_paused_or_stuck_server_times_out_to_the_cpu(
    worker: Path, tmp_path: Path, private: Path, mode: str
) -> None:
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER, mode=mode)
    try:
        with gpu_det(model_answering(tmp_path, [1]), sock, call_s=0.1, hello_s=0.1) as det:
            t = time.monotonic()
            boxes = det.detect(FRAME)
            assert time.monotonic() - t < 0.8
            assert det.last_path == "cpu" and boxes[0].x0 == 1.0
            assert det.reasons == {"TimeoutError": 1} and det.disabled is None
    finally:
        srv.stop()


@pytest.mark.parametrize("mode", ["bad_shape", "nan"])
def test_a_reply_of_another_shape_or_not_finite_is_refused(
    worker: Path, tmp_path: Path, private: Path, mode: str
) -> None:
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER, mode=mode)
    try:
        with gpu_det(model_answering(tmp_path, [1]), sock) as det:
            assert det.detect(FRAME)[0].x0 == 1.0 and det.last_path == "cpu"
            assert det.reasons == {"GpuUnavailable": 1}
    finally:
        srv.stop()


def test_other_weights_turn_the_gpu_off_for_the_run(worker: Path, tmp_path: Path,
                                                    private: Path) -> None:  # fmt: skip
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER, mode="wrong_sha")
    try:
        with gpu_det(model_answering(tmp_path, [1]), sock, clock=lambda: 1e9) as det:
            det.detect(FRAME)
            assert det.disabled is not None and "sha256" in det.disabled
            det.detect(FRAME)
            assert det.last_reason == "disabled" and srv.conns == 1
    finally:
        srv.stop()


def test_a_symlink_in_the_directory_is_refused_never_followed(worker: Path, tmp_path: Path,
                                                              private: Path) -> None:  # fmt: skip
    real = tmp_path / "elsewhere.sock"
    srv = FakeServer(real, ONE_MONSTER)
    try:
        (private / "detect.sock").symlink_to(real)
        with gpu_det(model_answering(tmp_path, [1]), private / "detect.sock") as det:
            assert det.detect(FRAME)[0].x0 == 1.0
            assert det.disabled is not None and "not a socket of ours" in det.disabled
            time.sleep(0.3)
            assert srv.conns == 0  # never connected through the link
    finally:
        srv.stop()


def test_a_directory_others_can_write_is_refused(worker: Path, tmp_path: Path,
                                                 private: Path) -> None:  # fmt: skip
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER)
    try:
        private.chmod(0o777)
        with gpu_det(model_answering(tmp_path, [1]), sock) as det:
            det.detect(FRAME)
            assert det.last_path == "cpu" and "private directory" in str(det.disabled)
            assert srv.conns == 0
    finally:
        private.chmod(0o700)
        srv.stop()


def test_prefer_cpu_forces_the_cpu(worker: Path, tmp_path: Path, private: Path) -> None:
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER)
    try:
        with gpu_det(model_answering(tmp_path, [1]), sock) as det:
            det.detect(FRAME, prefer="cpu")
            assert det.last_path == "cpu" and det.counts == {"cpu": 1} and srv.conns == 0
    finally:
        srv.stop()


def test_a_connection_the_server_closed_is_reopened_once(worker: Path, tmp_path: Path,
                                                         private: Path) -> None:  # fmt: skip
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER, mode="close_after_one")
    try:
        with gpu_det(model_answering(tmp_path, [1]), sock) as det:
            det.detect(FRAME)
            time.sleep(0.1)
            det.detect(FRAME)
            assert det.counts == {"gpu": 2} and srv.conns == 2 and det.reasons == {}
    finally:
        srv.stop()


def test_the_species_collapse_holds_on_the_gpu_path(worker: Path, tmp_path: Path,
                                                    private: Path) -> None:  # fmt: skip
    # a cookie and a christmas cookie on one sprite: per class NMS keeps both, the collapse one
    out = head_out(7, [(100.0, 58.0, 20.0, 30.0, 5, 0.9), (101.0, 58.0, 20.0, 30.0, 6, 0.8)])
    sock = private / "detect.sock"
    srv = FakeServer(sock, out, weights="xmas02")
    try:
        collapse = ud.MAP_MODELS["xmas_dun02"].collapse
        with gpu_det(model_answering(tmp_path, [1]), sock, names=XMAS02, collapse=collapse,
                     weights="xmas02") as det:  # fmt: skip
            boxes = det.detect(FRAME)
            assert [(b.cls, b.species) for b in boxes] == [("monster", "cookie")]
    finally:
        srv.stop()


def test_each_batch_is_logged_with_its_path(worker: Path, tmp_path: Path, private: Path) -> None:
    with gpu_det(model_answering(tmp_path, [1]), private / "detect.sock") as det:
        det.log_path = tmp_path / "det.jsonl"
        det.detect(FRAME)
        row = json.loads(det.log_path.read_text())
        assert row["path"] == "cpu" and row["boxes"] == [[1.0, 2.0, 3.0, 4.0, 0.9, "monster"]]
        assert row["prefer"] == "gpu" and row["reason"].startswith("FileNotFoundError")
        assert abs(row["t_wall"] - time.time()) < 60  # the wall clock: R3's log lines


def test_for_map_gpu_takes_the_maps_own_weights(
    worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "model").mkdir()
    onnx = tmp_path / "model" / "x-736x1280.onnx"
    onnx.write_text("[1]")
    monkeypatch.setitem(ud.MAP_MODELS, "test_map", ud.MapModel(
        onnx.name, ud.file_sha256(onnx), {}, gpu="xmas02"))  # fmt: skip
    monkeypatch.setitem(ud.MAP_MODELS, "cpu_only", ud.MapModel(onnx.name, ud.file_sha256(onnx), {}))
    py = Path(sys.executable)
    with ud.for_map_gpu("test_map", env=tmp_path, python=py) as det:
        assert det.weights == "xmas02"
    with ud.for_map_gpu("cpu_only", env=tmp_path, python=py) as det:
        assert det.disabled == "no GPU weights"
        det.detect(FRAME)
        assert det.last_path == "cpu"
    with pytest.raises(ud.DetectorUnavailable):
        ud.for_map_gpu("prt_fild08", env=tmp_path, python=py, model=onnx)


def test_the_deployed_gpu_weights_and_the_server_step() -> None:
    assert ud.MAP_MODELS["xmas_dun02"].gpu == "xmas02"
    assert ud.GPU_WEIGHTS["v1"].sha256.startswith("03d5397961")
    assert ud.GPU_WEIGHTS["xmas02"].sha256.startswith("5c5bb67a74")
    step = ud.serve_step(1800)
    assert step.startswith("execdev:vision@1800=python -m poring_vision.detect_server ")
    assert "--socket /detect/detect.sock" in step
    for name, w in ud.GPU_WEIGHTS.items():
        assert f"--model {name}={w.path}={w.sha256}" in step
    assert str(ud.GPU_SOCKET) == "/dev/shm/poring-lab-detect/detect.sock"
    assert os.path.basename(ud.SERVER_SOCKET) == ud.GPU_SOCKET.name


def test_the_openvino_backend_serves_the_deployed_onnx_by_its_pin(
    worker: Path, tmp_path: Path, private: Path
) -> None:
    """ADR-0022: a vendor-neutral backend runs the ONNX itself; its pinned sha256 is accepted, any
    other is refused (the GPU turns off for the run)."""
    sock = private / "detect.sock"

    srv = FakeServer(sock, ONE_MONSTER)
    try:
        pinned = ud.GPU_WEIGHTS["v1"]
        assert pinned.onnx == "v1png-last-736x1280.onnx" and pinned.onnx_sha256.startswith(
            "32b448a1"
        )
        assert ud.GPU_WEIGHTS["xmas02"].onnx_sha256 == ud.MAP_MODELS["xmas_dun02"].sha256
        with gpu_det(model_answering(tmp_path, [1]), sock) as det:
            det.spec = ud.GpuWeights(pinned.path, "b" * 64, pinned.onnx, pinned.sha256)
            det.detect(FRAME)  # the server says the .pt sha; it is the "onnx" pin here: accepted
            assert det.last_path == "gpu"
            det._drop()
            det.spec = ud.GpuWeights(pinned.path, "b" * 64, pinned.onnx, "c" * 64)
            det.detect(FRAME)  # neither pin: refused
            assert det.disabled is not None and "sha256 in" in det.disabled
    finally:
        srv.stop()


def test_the_openvino_serve_step_runs_in_the_worker_and_pins_each_onnx(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Batt 2026-11-07: the OpenVINO server runs IN the Intel worker (a guarded execdev step), the
    deployed ONNX from the NAS (read-only /datasets), each by its pinned sha256."""
    step = ud.serve_step_openvino(900)
    assert step.startswith("execdev:vision@900=python -m poring_vision.detect_server --backend "
                           "openvino --device GPU --socket /detect/detect.sock")  # fmt: skip
    for name, w in ud.GPU_WEIGHTS.items():
        assert f"--model {name}={ud.NAS_MODELS}/{w.onnx}={w.onnx_sha256}" in step
    assert ud.main(["serve-cmd", "--backend", "openvino", "--seconds", "900"]) == 0
    assert capsys.readouterr().out.strip() == (
        f"python3 scripts/guarded_build.py --threshold 30 --sustain 30 '{step}'")  # fmt: skip
    with pytest.raises(SystemExit):
        ud.main(["serve-cmd", "--backend", "openvino"])  # a time box is required


def test_serve_cmd_passes_ov_preproc_and_keeps_the_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Batt 2026-11-08: the canvas's conversion on the GPU (detect_server --ov-preproc). The step
    always names the mode; the default is gpu since the 11-08 parity run (boxes 1.000)."""
    assert ud.OV_PREPROC_DEFAULT == "gpu"
    assert " --ov-preproc gpu --ov-precision f32 --model " in ud.serve_step_openvino(900)
    assert " --ov-preproc cpu --ov-precision f32 --model " in ud.serve_step_openvino(
        900, ov_preproc="cpu")  # fmt: skip
    gpu = ud.serve_step_openvino(900, ov_preproc="gpu")
    assert " --socket /detect/detect.sock --ov-preproc gpu --ov-precision f32 --model " in gpu
    assert ud.main(["serve-cmd", "--backend", "openvino", "--seconds", "900",
                    "--ov-preproc", "gpu"]) == 0  # fmt: skip
    assert capsys.readouterr().out.strip() == (
        f"python3 scripts/guarded_build.py --threshold 30 --sustain 30 '{gpu}'")  # fmt: skip
    assert ud.main(["serve-cmd", "--seconds", "900"]) == 0  # torch: no such flag in its step
    assert "--ov-preproc" not in capsys.readouterr().out
    with pytest.raises(SystemExit):  # torch converts on the card: the flag is refused there
        ud.main(["serve-cmd", "--seconds", "900", "--ov-preproc", "gpu"])
    with pytest.raises(SystemExit):
        ud.main(["serve-cmd", "--backend", "openvino", "--seconds", "900", "--ov-preproc", "npu"])
    with pytest.raises(ValueError):
        ud.serve_step_openvino(900, ov_preproc="npu")


def test_serve_cmd_passes_ov_precision(capsys: pytest.CaptureFixture[str]) -> None:
    """2026-11-08 (bot-server-migration.md 19): the server's inference precision, always named;
    f32 stays the default until the f16 box parity passes."""
    assert ud.OV_PRECISION_DEFAULT == "f32"
    f16 = ud.serve_step_openvino(900, ov_precision="f16")
    assert " --ov-preproc gpu --ov-precision f16 --model " in f16
    assert ud.main(["serve-cmd", "--backend", "openvino", "--seconds", "900",
                    "--ov-precision", "f16"]) == 0  # fmt: skip
    assert capsys.readouterr().out.strip() == (
        f"python3 scripts/guarded_build.py --threshold 30 --sustain 30 '{f16}'")  # fmt: skip
    assert ud.main(["serve-cmd", "--seconds", "900"]) == 0  # torch: no such flag in its step
    assert "--ov-precision" not in capsys.readouterr().out
    with pytest.raises(SystemExit):  # torch runs FP32: the flag is refused there
        ud.main(["serve-cmd", "--seconds", "900", "--ov-precision", "f16"])
    with pytest.raises(SystemExit):
        ud.main(["serve-cmd", "--backend", "openvino", "--seconds", "900", "--ov-precision", "i8"])
    with pytest.raises(ValueError):
        ud.serve_step_openvino(900, ov_precision="bf16")


def test_the_servers_own_forward_time_is_kept_per_gpu_call(worker: Path, tmp_path: Path,
                                                           private: Path) -> None:  # fmt: skip
    sock = private / "detect.sock"
    srv = FakeServer(sock, ONE_MONSTER)
    try:
        with gpu_det(model_answering(tmp_path, [0]), sock) as det:
            assert det.last_server_ms is None
            det.detect(FRAME)
            assert det.last_path == "gpu" and det.last_server_ms == 1.0  # the reply's "ms"
            det.detect(FRAME, prefer="cpu")
            assert det.last_path == "cpu" and det.last_server_ms is None
    finally:
        srv.stop()
