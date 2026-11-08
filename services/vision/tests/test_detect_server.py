"""poring_vision.detect_server: the GPU forward pass behind the host bot's detector (ADR-0005
Amendment 2026-11-07). A stand-in net replaces torch; the client is the host's own
``scripts/unit_detector.GpuDetector`` (Apache code imported by the AGPL component, allowed)."""

from __future__ import annotations

import contextlib
import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from poring_vision import detect_server as ds

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import unit_detector as ud  # noqa: E402

N_ANCH = 19320
FAKE_CPU = """
import json, struct, sys
while True:
    head = sys.stdin.buffer.read(8)
    if len(head) < 8:
        break
    h, w, _ = struct.unpack("<HHI", head)
    sys.stdin.buffer.read(h * w * 3)
    sys.stdout.write(json.dumps({"boxes": [[1.0, 2.0, 3.0, 4.0, 0.5, 0]], "ms": 1.0}) + "\\n")
    sys.stdout.flush()
"""


class FakeNet:
    """The canvas's mean grey decides one box's x, so a test can see the frame arrived."""

    def __init__(self, sha256: str, nc: int = 3) -> None:
        self.sha256 = sha256
        self.shape = (1, 4 + nc, N_ANCH)
        self.seen: list[np.ndarray] = []

    def forward(self, canvas: np.ndarray) -> np.ndarray:
        self.seen.append(canvas.copy())
        out = np.zeros(self.shape, "<f4")
        out[0, :4, 0] = (100.0 + float(canvas[8:728].mean()), 58.0, 20.0, 30.0)
        out[0, 5, 0] = 0.9  # class 1: monster
        return out


@pytest.fixture
def served(tmp_path: Path):  # type: ignore[no-untyped-def]
    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    d.chmod(0o700)
    net = FakeNet(ud.GPU_WEIGHTS["v1"].sha256)
    srv = ds.Server(d / "detect.sock", {"v1": net}, log=lambda _m: None)
    th = threading.Thread(target=srv.serve, daemon=True)
    th.start()
    t0 = time.monotonic()
    while not (d / "detect.sock").exists() and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    yield srv, net, d / "detect.sock"
    srv.stop.set()
    th.join(timeout=5)


def cpu_detector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ud.UnitDetector:
    worker = tmp_path / "fake_cpu.py"
    worker.write_text(FAKE_CPU)
    monkeypatch.setattr(ud, "WORKER", worker)
    model = tmp_path / "m-736x1280.onnx"
    model.write_text("x")
    return ud.UnitDetector(model=model, python=Path(sys.executable))


def test_the_host_client_and_the_real_server_end_to_end(  # type: ignore[no-untyped-def]
    served, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srv, net, sock = served
    with ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "v1", socket_path=sock) as det:
        frame = np.full((720, 1280, 3), 10, np.uint8)
        boxes = det.detect(frame)
        assert det.last_path == "gpu", det.last_reason
        assert boxes == [ud.Box(100.0, 35.0, 120.0, 65.0, 0.9, "monster")]  # mean grey 10
        # the canvas the server got: the frame, 8 grey rows above and below
        c = net.seen[0]
        assert c.shape == (736, 1280, 3) and (c[:8] == 114).all() and (c[8:728] == 10).all()
        det.detect(frame, prefer="cpu")
        assert det.last_path == "cpu" and srv.n["frames"] == 1
    t0 = time.monotonic()
    while srv.n["closed"] < 1 and time.monotonic() - t0 < 3:  # the server sees the client leave
        time.sleep(0.02)
    assert srv.n["closed"] == 1 and srv.n["conn"] == 1 and srv.n["bad"] == 0


def test_a_stopped_server_removes_its_socket_and_the_host_falls_back(  # type: ignore[no-untyped-def]
    served, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srv, _net, sock = served
    srv.stop.set()
    t0 = time.monotonic()
    while sock.exists() and time.monotonic() - t0 < 5:
        time.sleep(0.02)
    assert not sock.exists()
    with ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "v1", socket_path=sock) as det:
        assert det.detect(np.zeros((720, 1280, 3), np.uint8))[0].x0 == 1.0
        assert det.last_path == "cpu"


def raw_client(sock: Path, hello: dict[str, object]) -> tuple[socket.socket, dict[str, object]]:
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(5)
    c.connect(str(sock))
    c.sendall(json.dumps(hello).encode() + b"\n")
    return c, json.loads(c.makefile("rb").readline())


def test_an_unknown_model_or_protocol_is_refused(served) -> None:  # type: ignore[no-untyped-def]
    _srv, _net, sock = served
    for hello in ({"v": 1, "model": "orcs"}, {"v": 2, "model": "v1"}, {"model": "v1"}):
        c, doc = raw_client(sock, hello)
        assert doc["ok"] is False
        c.close()


def test_a_frame_of_another_size_closes_the_connection(served) -> None:  # type: ignore[no-untyped-def]
    srv, net, sock = served
    c, doc = raw_client(sock, {"v": 1, "model": "v1"})
    assert doc["ok"] is True and doc["shape"] == [1, 7, N_ANCH] and doc["imgsz"] == [736, 1280]
    c.sendall(struct.pack("<HHI", 720, 1280, 0) + bytes(1000))  # refused at the header
    # closed, nothing computed (a reset when our unread bytes were still in its buffer)
    with contextlib.suppress(ConnectionResetError):
        assert c.recv(10) == b""
    c.close()
    assert net.seen == [] and srv.n["bad"] == 1


def test_the_rate_is_bounded_whatever_the_client_does(tmp_path: Path) -> None:
    sleeps: list[float] = []
    now = [0.0]
    srv = ds.Server(tmp_path / "s.sock", {}, max_hz=10.0, log=lambda _m: None,
                    clock=lambda: now[0], sleep=sleeps.append)  # fmt: skip
    srv.last_fwd = 0.0
    now[0] = 0.04
    net = FakeNet("a" * 64)
    srv.nets = {"x": net}
    a, b = socket.socketpair()

    def client() -> None:  # the frame is bigger than the socket buffer: send while it reads
        a.sendall(json.dumps({"v": 1, "model": "x"}).encode() + b"\n")
        a.sendall(struct.pack("<HHI", 736, 1280, 0) + bytes(736 * 1280 * 3))
        a.shutdown(socket.SHUT_WR)
        while a.recv(1 << 20):  # drain the replies
            pass

    th = threading.Thread(target=client, daemon=True)
    th.start()
    srv.handle(b)
    b.close()
    th.join(timeout=5)
    a.close()
    assert sleeps == [pytest.approx(0.06)] and len(net.seen) == 1


def test_bind_removes_a_stale_socket_but_nothing_else(tmp_path: Path) -> None:
    p = tmp_path / "s.sock"
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(p))
    stale.close()
    srv = ds.Server(p, {}, log=lambda _m: None)
    srv.bind().close()
    assert (p.stat().st_mode & 0o777) == 0o600
    p.unlink()
    p.write_text("not a socket")
    with pytest.raises(SystemExit):
        srv.bind()
    assert p.read_text() == "not a socket"


def test_models_are_name_path_sha256() -> None:
    sha = "ab" * 32
    assert ds.parse_models([f"v1=/d/w/last.pt={sha}"]) == {"v1": ("/d/w/last.pt", sha)}
    for bad in ([f"v1=/d/last.pt={sha[:-1]}"], ["v1=/d/last.pt"], [f"=/p={sha}"],
                [f"v1=/a={sha}", f"v1=/b={sha}"]):  # fmt: skip
        with pytest.raises(SystemExit):
            ds.parse_models(bad)


def test_the_weights_are_checked_before_they_are_unpickled(tmp_path: Path) -> None:
    w = tmp_path / "last.pt"
    w.write_bytes(b"not the pinned file")
    with pytest.raises(SystemExit, match="sha256"):
        ds.TorchNet(str(w), "0" * 64, "cuda:0")  # torch is never imported: refused first


def test_the_server_step_runs_the_pinned_weights_on_the_workers_socket() -> None:
    step = ud.serve_step(600)
    cmd = step.split("=", 1)[1].split()
    assert cmd[:3] == ["python", "-m", "poring_vision.detect_server"]
    i = cmd.index("--model")
    models = ds.parse_models([cmd[k + 1] for k in range(i, len(cmd)) if cmd[k] == "--model"])
    assert {n: s for n, (_p, s) in models.items()} == {
        n: w.sha256 for n, w in ud.GPU_WEIGHTS.items()
    }


def test_the_host_client_reads_the_servers_own_forward_time(  # type: ignore[no-untyped-def]
    served, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _srv, _net, sock = served
    with ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "v1", socket_path=sock) as det:
        det.detect(np.full((720, 1280, 3), 10, np.uint8))
        assert det.last_path == "gpu" and isinstance(det.last_server_ms, float)
        assert det.last_server_ms >= 0.0
        det.detect(np.full((720, 1280, 3), 10, np.uint8), prefer="cpu")
        assert det.last_path == "cpu" and det.last_server_ms is None


# --- --ov-preproc (Batt 2026-11-08: the canvas's conversion on the GPU, bot-server-migration 16) --
# openvino is not on the host: a stand-in records what OvNet asks of it. The deployed numbers are
# the parent's parity run on the Arc (the command is in the commit's report).


def ppp_reference(canvas: np.ndarray, steps=ds.PPP_STEPS) -> np.ndarray:  # type: ignore[no-untyped-def]
    """PURE numpy mirror of OpenVINO running ``steps`` on the (1, H, W, 3) u8 BGR tensor in their
    order, then its implicit NHWC -> NCHW (as InputInfoImpl::build in 2026.4.1). Like OpenVINO,
    scale refuses a non-real type."""
    assert ds.PPP_TENSOR == ("u8", "NHWC", "BGR") and ds.PPP_MODEL_LAYOUT == "NCHW"
    x = canvas[None]
    colour = "BGR"
    for op, arg in steps:
        if op == "convert_element_type":
            x = x.astype({"f32": np.float32}[arg])
        elif op == "convert_color":
            assert (colour, arg) == ("BGR", "RGB")
            x, colour = x[..., ::-1], arg  # the C axis, last in NHWC
        elif op == "scale":
            if not np.issubdtype(x.dtype, np.floating):
                raise TypeError("Scale preprocessing can be applied to 'float' inputs.")
            x = x / np.float32(arg)
        else:
            raise ValueError(op)
    return np.ascontiguousarray(x.transpose(0, 3, 1, 2))


def test_the_device_steps_compute_to_input_exactly() -> None:
    rng = np.random.default_rng(20261108)
    frames = [rng.integers(0, 256, (736, 1280, 3), dtype=np.uint8) for _ in range(3)]
    frames.append(np.full((736, 1280, 3), 114, np.uint8))  # the letterbox grey
    edge = np.zeros((736, 1280, 3), np.uint8)
    edge[..., 0], edge[..., 2] = 255, 1  # blue full, red barely: a swapped channel shows at once
    frames.append(edge)
    for canvas in frames:
        want, got = ds.to_input(canvas), ppp_reference(canvas)
        assert got.shape == want.shape == (1, 3, 736, 1280) and got.dtype == np.float32
        assert float(np.abs(got - want).max()) < 1e-6


def test_the_reference_catches_a_wrong_step_list() -> None:
    """The positive case: the comparison above fails for each plausible mistake."""
    canvas = np.random.default_rng(7).integers(0, 256, (736, 1280, 3), dtype=np.uint8)
    want = ds.to_input(canvas)
    steps = dict(ds.PPP_STEPS)
    no_flip = tuple((op, a) for op, a in ds.PPP_STEPS if op != "convert_color")
    no_scale = tuple((op, a) for op, a in ds.PPP_STEPS if op != "scale")
    for wrong in (no_flip, no_scale):
        assert float(np.abs(ppp_reference(canvas, wrong) - want).max()) > 0.1
    scale_first = (("scale", steps["scale"]), *(s for s in ds.PPP_STEPS if s[0] != "scale"))
    with pytest.raises(TypeError):  # OpenVINO refuses it as well (scale needs a real type)
        ppp_reference(canvas, scale_first)


class FakeOv:
    """openvino + openvino.preprocess, recording: read_model, the PrePostProcessor calls in order,
    compile_model, and each infer's input."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.inputs: list[np.ndarray] = []
        fake = self

        class Rec:
            def __init__(self, where: str) -> None:
                self.where = where

            def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
                def call(*args: object) -> Rec:
                    fake.calls.append((self.where, name, *args))
                    return self

                return call

        class Info:
            def tensor(self) -> Rec:
                return Rec("tensor")

            def model(self) -> Rec:
                return Rec("model")

            def preprocess(self) -> Rec:
                return Rec("preprocess")

        class PrePostProcessor:
            def __init__(self, model: object) -> None:
                fake.calls.append(("ppp", model))

            def input(self) -> Info:
                return Info()

            def build(self) -> str:
                fake.calls.append(("build",))
                return "model+ppp"

        class Req:
            def infer(self, inputs: dict[int, np.ndarray]) -> None:
                assert list(inputs) == [0]
                fake.inputs.append(np.array(inputs[0]))

            def get_output_tensor(self, i: int):  # type: ignore[no-untyped-def]
                return type("T", (), {"data": np.zeros((1, 7, N_ANCH), np.float32)})()

        class Compiled:
            def create_infer_request(self) -> Req:
                return Req()

        class Core:
            def read_model(self, path: str) -> str:
                fake.calls.append(("read_model", path))
                return "model"

            def compile_model(self, model: object, device: str, cfg: dict[str, str]) -> Compiled:
                fake.calls.append(("compile_model", model, device, dict(cfg)))
                return Compiled()

        class Named:
            def __init__(self, kind: str) -> None:
                self.kind = kind

            def __getattr__(self, name: str) -> str:
                return f"{self.kind}.{name}"

        self.ov = type(sys)("openvino")
        self.ov.Core, self.ov.Type = Core, Named("Type")  # type: ignore[attr-defined]
        self.ov.Layout = lambda s: f"Layout({s})"  # type: ignore[attr-defined]
        self.pre = type(sys)("openvino.preprocess")
        self.pre.PrePostProcessor = PrePostProcessor  # type: ignore[attr-defined]
        self.pre.ColorFormat = Named("ColorFormat")  # type: ignore[attr-defined]
        self.ov.preprocess = self.pre  # type: ignore[attr-defined]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "openvino", self.ov)
        monkeypatch.setitem(sys.modules, "openvino.preprocess", self.pre)


def pinned_onnx(tmp_path: Path) -> tuple[str, str]:
    p = tmp_path / "m-736x1280.onnx"
    p.write_bytes(b"an onnx")
    return str(p), ds.file_sha256(str(p))


def test_gpu_preproc_compiles_the_steps_in_and_never_calls_to_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOv()
    fake.install(monkeypatch)

    def no_cpu_conversion(_c: np.ndarray) -> np.ndarray:
        raise AssertionError("--ov-preproc gpu called to_input")

    monkeypatch.setattr(ds, "to_input", no_cpu_conversion)
    path, sha = pinned_onnx(tmp_path)
    net = ds.OvNet(path, sha, "GPU", preproc="gpu")
    assert fake.calls == [
        ("read_model", path),
        ("ppp", "model"),
        ("tensor", "set_element_type", "Type.u8"),
        ("tensor", "set_layout", "Layout(NHWC)"),
        ("tensor", "set_color_format", "ColorFormat.BGR"),
        ("model", "set_layout", "Layout(NCHW)"),
        ("preprocess", "convert_element_type", "Type.f32"),  # PPP_STEPS, in order
        ("preprocess", "convert_color", "ColorFormat.RGB"),
        ("preprocess", "scale", 255.0),
        ("build",),
        # the precision the server ran before (FP32), unchanged by the mode
        ("compile_model", "model+ppp", "GPU",
         {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f32"}),
    ]  # fmt: skip
    assert net.shape == (1, 7, N_ANCH) and net.preproc == "gpu"
    canvas = np.random.default_rng(1).integers(0, 256, (736, 1280, 3), dtype=np.uint8)
    y = net.forward(canvas)
    x = fake.inputs[-1]  # the uint8 BGR canvas itself, batched: no conversion on the host
    assert x.dtype == np.uint8 and x.shape == (1, 736, 1280, 3) and np.array_equal(x[0], canvas)
    assert y.dtype == np.dtype("<f4") and y.shape == (1, 7, N_ANCH)


def test_cpu_preproc_is_the_server_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOv()
    fake.install(monkeypatch)
    path, sha = pinned_onnx(tmp_path)
    net = ds.OvNet(path, sha, "GPU")  # the default
    assert net.preproc == ds.OV_PREPROC_DEFAULT == "cpu"
    fp32 = {"PERFORMANCE_HINT": "LATENCY", "INFERENCE_PRECISION_HINT": "f32"}
    assert fake.calls == [("read_model", path), ("compile_model", "model", "GPU", fp32)]
    canvas = np.random.default_rng(2).integers(0, 256, (736, 1280, 3), dtype=np.uint8)
    net.forward(canvas)
    assert np.array_equal(fake.inputs[-1], ds.to_input(canvas))  # float32 (1, 3, H, W)


def test_an_unknown_preproc_or_weights_are_refused_before_openvino(tmp_path: Path) -> None:
    path, sha = pinned_onnx(tmp_path)
    with pytest.raises(SystemExit, match="ov-preproc"):
        ds.OvNet(path, sha, preproc="npu")  # openvino is never imported: refused first
    with pytest.raises(SystemExit, match="sha256"):
        ds.OvNet(path, "0" * 64, preproc="gpu")


class Recorded:
    """main()'s nets and server, without a GPU or a socket."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.nets: list[tuple[object, ...]] = []
        self.servers: list[dict[str, object]] = []
        rec = self

        class Net:
            def __init__(self, path: str, sha: str, device: str, imgsz: tuple[int, int],
                         precision: str, preproc: str) -> None:  # fmt: skip
                rec.nets.append((path, sha, device, imgsz, precision, preproc))
                self.sha256, self.shape = sha, (1, 7, N_ANCH)

        class Srv:
            def __init__(self, path: Path, nets: dict[str, object], imgsz: tuple[int, int],
                         max_hz: float, mode: dict[str, object]) -> None:  # fmt: skip
                rec.servers.append({"path": path, "nets": sorted(nets), "mode": mode})
                self.stop = threading.Event()

            def serve(self) -> None:
                pass

        monkeypatch.setattr(ds, "OvNet", Net)
        monkeypatch.setattr(ds, "Server", Srv)
        monkeypatch.setattr(ds.signal, "signal", lambda *_a: None)  # keep pytest's handlers


def test_main_takes_ov_preproc_and_records_the_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    sha = "ab" * 32
    base = ["--socket", "/detect/detect.sock", "--model", f"v1=/m/v1.onnx={sha}",
            "--backend", "openvino"]  # fmt: skip
    rec = Recorded(monkeypatch)
    assert ds.main([*base, "--ov-preproc", "gpu"]) == 0
    assert ds.main(base) == 0  # the default: cpu
    assert [n[5] for n in rec.nets] == ["gpu", "cpu"] and {n[4] for n in rec.nets} == {"f32"}
    assert [s["mode"] for s in rec.servers] == [
        {"backend": "openvino", "device": "GPU", "ov_preproc": m, "precision": "f32"}
        for m in ("gpu", "cpu")
    ]
    torch = ["--socket", "/s", "--model", f"v1=/m/v1.pt={sha}", "--ov-preproc", "gpu"]
    for bad in ([*base, "--ov-preproc", "npu"], torch):
        with pytest.raises(SystemExit):  # an unknown mode; the mode on the torch backend
            ds.main(bad)
    assert len(rec.nets) == 2  # nothing loaded for either


def test_the_openvino_serve_step_passes_ov_preproc_to_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unit_detector.py serve-cmd's step, parsed by the server's own main()."""
    rec = Recorded(monkeypatch)
    for mode in ("gpu", "cpu"):
        step = ud.serve_step_openvino(600, ov_preproc=mode)
        cmd = step.split("=", 1)[1].split()
        assert cmd[:3] == ["python", "-m", "poring_vision.detect_server"]
        assert ds.main(cmd[3:]) == 0
    assert [n[5] for n in rec.nets] == ["gpu", "gpu", "cpu", "cpu"]  # v1 + xmas02 each time
    assert [n[0] for n in rec.nets[:2]] == [f"{ud.NAS_MODELS}/{w.onnx}"
                                            for w in ud.GPU_WEIGHTS.values()]  # fmt: skip
    assert [s["mode"]["ov_preproc"] for s in rec.servers] == ["gpu", "cpu"]  # type: ignore[index]
    assert "--ov-preproc cpu" in ud.serve_step_openvino(600)  # the default, unchanged


def test_the_start_and_stats_lines_name_the_mode(tmp_path: Path) -> None:
    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    lines: list[str] = []
    mode = {"backend": "openvino", "device": "GPU", "ov_preproc": "gpu", "precision": "f32"}
    srv = ds.Server(d / "s.sock", {"v1": FakeNet("a" * 64)}, log=lines.append, mode=mode)
    th = threading.Thread(target=srv.serve, daemon=True)
    th.start()
    t0 = time.monotonic()
    while not lines and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    srv.stop.set()
    th.join(timeout=5)
    start, *rest = (json.loads(x) for x in lines)
    assert start["detect_server"] == "listening" and start["t"]
    assert {k: start[k] for k in mode} == mode
    stats = [r for r in rest if r["detect_server"] == "stats"]
    assert stats and all(r["ov_preproc"] == "gpu" for r in stats)
