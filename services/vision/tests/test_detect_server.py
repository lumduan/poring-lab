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
    srv.last_dec["x"] = 0.0  # this model's last forward (dungeon@9.29c: the gap is per model)
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
    net = ds.OvNet(path, sha, "GPU", preproc="cpu")  # the old path, still selectable
    assert net.preproc == "cpu" and ds.OV_PREPROC_DEFAULT == "gpu"
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
    assert ds.main(base) == 0  # the default: gpu (since the 11-08 parity run)
    assert ds.main([*base, "--ov-preproc", "cpu"]) == 0
    assert [n[5] for n in rec.nets] == ["gpu", "gpu", "cpu"] and {n[4] for n in rec.nets} == {"f32"}
    assert [s["mode"] for s in rec.servers] == [
        {"backend": "openvino", "device": "GPU", "ov_preproc": m, "precision": "f32"}
        for m in ("gpu", "gpu", "cpu")
    ]
    torch = ["--socket", "/s", "--model", f"v1=/m/v1.pt={sha}", "--ov-preproc", "gpu"]
    for bad in ([*base, "--ov-preproc", "npu"], torch):
        with pytest.raises(SystemExit):  # an unknown mode; the mode on the torch backend
            ds.main(bad)
    assert len(rec.nets) == 3  # nothing loaded for either


def test_main_takes_ov_precision_and_records_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """--ov-precision (bot-server-migration.md 19): the hint reaches every OvNet and the start
    line; f32 stays the default; torch refuses it."""
    sha = "ab" * 32
    base = ["--socket", "/detect/detect.sock", "--model", f"v1=/m/v1.onnx={sha}",
            "--backend", "openvino"]  # fmt: skip
    rec = Recorded(monkeypatch)
    assert ds.main([*base, "--ov-precision", "f16"]) == 0
    assert ds.main(base) == 0
    assert [n[4] for n in rec.nets] == ["f16", "f32"]
    assert [s["mode"]["precision"] for s in rec.servers] == ["f16", "f32"]  # type: ignore[index]
    torch = ["--socket", "/s", "--model", f"v1=/m/v1.pt={sha}", "--ov-precision", "f16"]
    for bad in ([*base, "--ov-precision", "bf16"], torch):
        with pytest.raises(SystemExit):
            ds.main(bad)
    assert len(rec.nets) == 2
    step = ud.serve_step_openvino(600, ov_precision="f16")
    assert ds.main(step.split("=", 1)[1].split()[3:]) == 0  # serve-cmd's step, parsed here
    assert [n[4] for n in rec.nets[2:]] == ["f16"] * len(ud.GPU_WEIGHTS)  # every served model


def test_gpu_clock_reads_the_cards_floor(tmp_path: Path) -> None:
    card = tmp_path / "card1"
    card.mkdir()
    for key, v in (("min", 2450), ("RP0", 2450), ("act", 0)):
        (card / f"gt_{key}_freq_mhz").write_text(f"{v}\n")
    pattern = str(tmp_path / "card*" / "gt_{}_freq_mhz")
    assert ds.gpu_clock(pattern) == {"min": 2450, "RP0": 2450, "act": 0}
    (card / "gt_act_freq_mhz").unlink()
    assert ds.gpu_clock(pattern) is None  # a card without all three files
    assert ds.gpu_clock(str(tmp_path / "none*" / "gt_{}_freq_mhz")) is None


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
    n_w = len(ud.GPU_WEIGHTS)  # every served model, each time
    assert [n[5] for n in rec.nets] == ["gpu"] * n_w + ["cpu"] * n_w
    assert [n[0] for n in rec.nets[:n_w]] == [f"{ud.NAS_MODELS}/{w.onnx}"
                                            for w in ud.GPU_WEIGHTS.values()]  # fmt: skip
    assert [s["mode"]["ov_preproc"] for s in rec.servers] == ["gpu", "cpu"]  # type: ignore[index]
    assert "--ov-preproc gpu" in ud.serve_step_openvino(600)  # the default since the parity run


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
    assert "gpu_clock" in start  # the card's clock floor (or None where sysfs shows no card)
    stats = [r for r in rest if r["detect_server"] == "stats"]
    assert stats and all(r["ov_preproc"] == "gpu" for r in stats)
    assert all(r["precision"] == "f32" and "gpu_clock" in r for r in stats)


# --- the gate (dungeon@9.29c; Batt 2026-11-11: a fast HUD that does not slow the decisions) -----


def gate_server(max_hz: float = 1e6, hud_wait_s: float = 5.0) -> ds.Server:
    return ds.Server(Path("/nonexistent"), {}, max_hz=max_hz, log=lambda _m: None,
                     hud_wait_s=hud_wait_s)  # fmt: skip


def until(cond, timeout: float = 3.0) -> bool:  # type: ignore[no-untyped-def]
    t0 = time.monotonic()
    while not cond():
        if time.monotonic() - t0 > timeout:
            return False
        time.sleep(0.005)
    return True


def test_a_decision_goes_before_hud_calls_that_have_not_started() -> None:
    """One HUD forward runs, two more HUD calls wait, then a decision call arrives: the decision
    gets the card next, the waiting HUD calls after it."""
    srv = gate_server()
    order: list[str] = []
    go = {k: threading.Event() for k in ("h2", "h3", "d")}

    def hud(name: str) -> None:
        assert srv.enter_hud(srv.clock()) is None
        order.append(name)
        go[name].wait(5)
        srv.leave(ds.HUD)

    def decision() -> None:
        srv.enter_decision()
        order.append("d")
        go["d"].wait(5)
        srv.leave(ds.DECISION)

    assert srv.enter_hud(srv.clock()) is None  # H1 has the card
    ths = [threading.Thread(target=hud, args=(n,), daemon=True) for n in ("h2", "h3")]
    for th in ths:
        th.start()
    time.sleep(0.1)  # both HUD calls are at the gate before the decision
    td = threading.Thread(target=decision, daemon=True)
    td.start()
    assert until(lambda: len(srv.queue) == 1)
    assert order == []  # nobody runs beside H1
    srv.leave(ds.HUD)  # H1's forward ends
    assert until(lambda: order == ["d"])
    time.sleep(0.05)
    assert order == ["d"]  # the HUD calls still wait: the card is the decision's
    go["d"].set()
    assert until(lambda: len(order) == 2)
    first = order[1]
    go[first].set()
    assert until(lambda: len(order) == 3) and sorted(order[1:]) == ["h2", "h3"]
    go[order[2]].set()
    for th in (*ths, td):
        th.join(timeout=5)
    assert not srv.busy and not srv.queue and srv.pending == 0


def test_a_hud_call_that_cannot_start_in_time_is_skipped_with_its_reason() -> None:
    srv = gate_server(max_hz=10.0, hud_wait_s=0.05)  # the --max-hz gap: 100 ms
    srv.enter_decision()  # a decision forward runs
    t0 = time.monotonic()
    assert srv.enter_hud(srv.clock()) == "busy"
    assert 0.04 <= time.monotonic() - t0 < 1.0  # it waited its bound, then gave up
    srv.leave(ds.DECISION, "v1")
    assert srv.enter_hud(srv.clock()) == "gap"  # 50 ms < the 100-ms gap after that forward
    srv.last_any = -1e18
    for held in ("queue", "pending"):  # a decision call queued, or sleeping out its gap
        if held == "queue":
            srv.queue.append(0)
        else:
            srv.pending = 1
        assert srv.enter_hud(srv.clock()) == "decision"
        srv.queue.clear()
        srv.pending = 0
    assert not srv.busy  # a skipped HUD call never holds the card
    srv2 = gate_server(max_hz=10.0, hud_wait_s=0.3)
    srv2.enter_decision()
    srv2.leave(ds.DECISION, "v1")
    t1 = time.monotonic()
    assert srv2.enter_hud(srv2.clock()) is None  # inside its bound: it waits the gap out
    assert 0.08 <= time.monotonic() - t1 < 0.3 and srv2.busy


def frame_client(sock: Path, hello: dict[str, object]) -> tuple[socket.socket, object]:
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(5)
    c.connect(str(sock))
    c.sendall(json.dumps(hello).encode() + b"\n")
    f = c.makefile("rb")
    assert json.loads(f.readline())["ok"] is True
    return c, f


def send_frame(c: socket.socket, f, value: int, body: int) -> dict[str, object]:  # type: ignore[no-untyped-def]
    c.sendall(struct.pack("<HHI", 736, 1280, 0) + bytes([value]) * (736 * 1280 * 3))
    head = json.loads(f.readline())
    if "skipped" not in head:
        assert len(f.read(body)) == body
    return head  # type: ignore[no-any-return]


def run_server(tmp_path: Path, net: object, **kw: object):  # type: ignore[no-untyped-def]
    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    d.chmod(0o700)
    srv = ds.Server(d / "detect.sock", {"v1": net}, log=lambda _m: None, **kw)  # type: ignore[arg-type]
    th = threading.Thread(target=srv.serve, daemon=True)
    th.start()
    assert until(lambda: (d / "detect.sock").exists())
    return srv, th, d / "detect.sock"


class SlowNet(FakeNet):
    """A forward of ``fwd_s``: the canvas's first byte says whose frame it was."""

    def __init__(self, sha256: str, fwd_s: float) -> None:
        super().__init__(sha256)
        self.fwd_s = fwd_s
        self.runs: list[tuple[int, float, float]] = []
        self.inside = 0
        self.most_inside = 0

    def forward(self, canvas: np.ndarray) -> np.ndarray:
        self.inside += 1
        self.most_inside = max(self.most_inside, self.inside)
        t0 = time.monotonic()
        time.sleep(self.fwd_s)
        self.inside -= 1
        self.runs.append((int(canvas[0, 0, 0]), t0, time.monotonic()))
        return np.zeros(self.shape, "<f4")


def hud_storm(sock: Path, halt: threading.Event, heads: list[dict[str, object]],
              body: int, n: int = 1) -> list[threading.Thread]:  # fmt: skip
    """``n`` HUD clients, each sending frames back to back."""

    def one() -> None:
        c, f = frame_client(sock, {"v": 1, "model": "v1", "prio": "hud"})
        with c:
            while not halt.is_set():
                heads.append(send_frame(c, f, 200, body))

    ths = [threading.Thread(target=one, daemon=True) for _ in range(n)]
    for th in ths:
        th.start()
    return ths


def decision_frame(c: socket.socket, f, body: int) -> float:  # type: ignore[no-untyped-def]
    head = send_frame(c, f, 10, body)
    assert "skipped" not in head  # a decision frame is never skipped
    return float(head["wait_ms"])  # type: ignore[arg-type]


# the decision client's pauses before each call (past --max-hz's 100-ms gap after its own last
# forward): every phase of the HUD client's cycle
PAUSES = tuple(0.1 + k * 0.0127 for k in range(10))
FWD_S = 0.03  # the stand-in forward
BODY = 4 * 7 * N_ANCH


def old_rules(srv: ds.Server) -> None:
    """The server before the gate: one queue, and --max-hz's gap after a forward of ANY kind."""

    class AnyGap(dict):  # type: ignore[type-arg]
        def get(self, _key: object, _default: object = None) -> float:
            return srv.last_any  # every model's gap runs from the last forward of any kind

    def enter_hud(_t_in: float) -> None:
        srv.enter_decision()
        gap = srv.last_any + srv.min_gap - srv.clock()
        if gap > 0:
            srv.sleep(gap)

    srv.last_dec = AnyGap()
    srv.enter_hud = enter_hud  # type: ignore[method-assign,assignment]


def test_a_decision_waits_at_most_for_the_hud_forward_in_flight(tmp_path: Path) -> None:
    """The HUD client sends frames back to back (the deployed --max-hz 10); the decision client's
    every call, at every phase of the HUD's cycle, waits at the gate for at most the ONE HUD
    forward in flight (+ scheduling slack); the card never runs two forwards at once."""
    net = SlowNet(ud.GPU_WEIGHTS["v1"].sha256, FWD_S)
    srv, th, sock = run_server(tmp_path, net, hud_wait_s=1.0)
    halt, heads = threading.Event(), []  # type: ignore[var-annotated]
    (storm,) = hud_storm(sock, halt, heads, BODY)
    try:
        assert until(lambda: srv.n["hud"] >= 2)
        c, f = frame_client(sock, {"v": 1, "model": "v1"})  # a client before the gate: no prio
        with c:
            waits = []
            for pause in PAUSES:
                time.sleep(pause)
                waits.append(decision_frame(c, f, BODY))
    finally:
        halt.set()
        storm.join(timeout=5)
        srv.stop.set()
        th.join(timeout=10)
    assert max(waits) <= FWD_S * 1000.0 + 45.0, waits
    assert net.most_inside == 1  # one forward at a time on the card
    tags = [tag for tag, _t0, _t1 in net.runs]
    assert tags.count(10) == len(PAUSES) and tags.count(200) >= len(PAUSES)  # HUD ran between
    assert srv.n["bad"] == 0 and srv.fatal is None


def storm_waits(tmp_path: Path, priority: bool) -> list[float]:
    """Three HUD clients send frames back to back (no --max-hz gap); the decision client's waits
    at every phase. ``priority`` False: HUD calls queue like decision calls (no gate)."""
    net = SlowNet(ud.GPU_WEIGHTS["v1"].sha256, 0.08)  # slow: one forward stands apart from two
    srv, th, sock = run_server(tmp_path, net, max_hz=1e6, hud_wait_s=1.0)
    if not priority:
        srv.enter_hud = lambda _t_in: srv.enter_decision()  # type: ignore[method-assign,assignment,func-returns-value]
    halt, heads = threading.Event(), []  # type: ignore[var-annotated]
    storm = hud_storm(sock, halt, heads, BODY, n=3)
    waits = []
    try:
        assert until(lambda: srv.n["hud"] >= 3)
        c, f = frame_client(sock, {"v": 1, "model": "v1"})
        with c:
            for k in range(8):
                time.sleep(k * 0.0127)
                waits.append(decision_frame(c, f, BODY))
    finally:
        halt.set()
        for t in storm:
            t.join(timeout=5)
        srv.stop.set()
        th.join(timeout=10)
    assert net.most_inside == 1 and srv.fatal is None
    return waits


def test_queued_hud_calls_never_go_before_a_decision(tmp_path: Path) -> None:
    """Three HUD clients hammer the card: a decision waits for at most the ONE HUD forward in
    flight. The positive case: without the gate (HUD calls queued like decisions) the same
    decision waits behind more than one."""
    (tmp_path / "gate").mkdir()
    (tmp_path / "none").mkdir()
    gated = storm_waits(tmp_path / "gate", priority=True)
    fifo = storm_waits(tmp_path / "none", priority=False)
    assert max(gated) <= 80.0 + 45.0, gated
    assert max(fifo) > 80.0 + 45.0, fifo


def waits_right_after_hud_forwards(tmp_path: Path, old: bool) -> list[float]:
    """Each decision frame sent the moment a HUD forward ends (the HUD client back to back)."""
    net = SlowNet(ud.GPU_WEIGHTS["v1"].sha256, 0.02)
    srv, th, sock = run_server(tmp_path, net, hud_wait_s=1.0)
    if old:
        old_rules(srv)
    halt, heads = threading.Event(), []  # type: ignore[var-annotated]
    (storm,) = hud_storm(sock, halt, heads, BODY)
    waits = []
    try:
        c, f = frame_client(sock, {"v": 1, "model": "v1"})
        with c:
            for _ in range(6):
                n0 = len(net.runs)
                assert until(lambda n0=n0: len(net.runs) > n0 and net.runs[-1][0] == 200)
                waits.append(decision_frame(c, f, BODY))
    finally:
        halt.set()
        storm.join(timeout=5)
        srv.stop.set()
        th.join(timeout=10)
    return waits


def test_a_decision_right_after_a_hud_forward_does_not_wait(tmp_path: Path) -> None:
    """s73's mechanism (rogue-xmas02.md 4CI) and its positive case: before the gate, a decision
    right after a HUD forward slept out the rest of --max-hz's 100-ms gap; now it does not."""
    (tmp_path / "new").mkdir()
    (tmp_path / "old").mkdir()
    new = waits_right_after_hud_forwards(tmp_path / "new", old=False)
    old = waits_right_after_hud_forwards(tmp_path / "old", old=True)
    assert max(new) <= 30.0, new
    assert min(old) >= 60.0, old  # the old server: ~100 ms minus the frame's own transfer


def test_several_connections_at_once_and_one_too_many(served) -> None:  # type: ignore[no-untyped-def]
    """Before 9.29c a second client queued unanswered in listen(1)'s backlog and a later connect
    failed with BlockingIOError (O13). Now MAX_CONN connections are served at once; one past
    them is closed unanswered (its client falls back to its CPU)."""
    srv, _net, sock = served
    conns = [frame_client(sock, {"v": 1, "model": "v1", **({"prio": "hud"} if k % 2 else {})})
             for k in range(ds.MAX_CONN)]  # fmt: skip
    extra = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    extra.settimeout(5)
    extra.connect(str(sock))
    extra.sendall(json.dumps({"v": 1, "model": "v1"}).encode() + b"\n")
    with contextlib.suppress(ConnectionResetError):  # (a reset: our hello was still unread)
        assert extra.makefile("rb").readline() == b""
    extra.close()
    assert srv.n["refused"] == 1 and srv.n["conn"] == ds.MAX_CONN + 1
    for c, f in conns:
        f.close()  # (the makefile holds the socket open too)
        c.close()
    assert until(lambda: srv.n["closed"] == ds.MAX_CONN)
    c, _f = frame_client(sock, {"v": 1, "model": "v1"})  # room again
    c.close()


class Card:
    """One card behind several stand-in nets: how many forwards ran at once."""

    def __init__(self) -> None:
        self.inside = 0
        self.most = 0
        self.lock = threading.Lock()


class CardNet(FakeNet):
    def __init__(self, sha256: str, fwd_s: float, card: Card, tag: str) -> None:
        super().__init__(sha256)
        self.fwd_s, self.card, self.tag = fwd_s, card, tag
        self.runs: list[str] = []

    def forward(self, canvas: np.ndarray) -> np.ndarray:
        with self.card.lock:
            self.card.inside += 1
            self.card.most = max(self.card.most, self.card.inside)
        time.sleep(self.fwd_s)
        with self.card.lock:
            self.card.inside -= 1
        self.runs.append(self.tag)
        return np.zeros(self.shape, "<f4")


def test_two_models_decide_at_once_beside_a_hud_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The coordinator's case (2026-11-12): the runner's species model (the box watcher) and the
    floor-item model (a loot path) decide at once, the species model's HUD twin beside them, all
    host clients (GpuDetector) on ONE server. No call falls back (no BlockingIOError, no
    timeout); each decision waits for at most the forward in flight plus the other model's
    decision queued before it -- never behind HUD calls; one forward at a time on the card."""
    card = Card()
    nets = {
        "v1": CardNet(ud.GPU_WEIGHTS["v1"].sha256, FWD_S, card, "species"),
        "xmas02fi4": CardNet(ud.GPU_WEIGHTS["xmas02fi4"].sha256, FWD_S, card, "item"),
    }
    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    d.chmod(0o700)
    srv = ds.Server(d / "detect.sock", nets, log=lambda _m: None)  # type: ignore[arg-type]
    th = threading.Thread(target=srv.serve, daemon=True)
    th.start()
    assert until(lambda: (d / "detect.sock").exists())
    sock = d / "detect.sock"
    frame = np.full((720, 1280, 3), 10, np.uint8)
    species = ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "v1", socket_path=sock)
    item = ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "xmas02fi4", socket_path=sock)
    twin = species.hud_twin()
    halt = threading.Event()
    got: dict[str, list[tuple[str, float | None]]] = {"species": [], "item": []}

    def decide(det: ud.GpuDetector, key: str, step: float) -> None:
        for k in range(10):
            time.sleep(0.1 + k * step)  # past its own model's gap; every phase of the others
            det.detect(frame)
            got[key].append((det.last_path, det.last_wait_ms))

    def hud() -> None:
        while not halt.is_set():
            twin.detect(frame)  # back to back while it gets boxes (the runner's waits 0.2 s)
            if twin.last_path != "gpu":
                time.sleep(0.01)

    hud_th = threading.Thread(target=hud, daemon=True)
    hud_th.start()
    try:
        assert until(lambda: twin.counts["gpu"] >= 1)
        ths = [
            threading.Thread(target=decide, args=(species, "species", 0.0127), daemon=True),
            threading.Thread(target=decide, args=(item, "item", 0.0093), daemon=True),
        ]
        for t in ths:
            t.start()
        for t in ths:
            t.join(timeout=30)
    finally:
        halt.set()
        hud_th.join(timeout=5)
        twin.close()
        species.close()
        item.close()
        srv.stop.set()
        th.join(timeout=10)
    for key in ("species", "item"):
        assert [p for p, _w in got[key]] == ["gpu"] * 10, (key, got[key])
    assert species.reasons == {} and item.reasons == {}  # nothing fell back to the CPU
    waits = [float(w) for key in got for _p, w in got[key] if w is not None]
    assert len(waits) == 20
    assert max(waits) <= 2 * FWD_S * 1000.0 + 45.0, waits  # the forward in flight + one decision
    assert card.most == 1  # one forward at a time on the card, whatever the model
    assert nets["xmas02fi4"].runs.count("item") == 10 and twin.counts["gpu"] >= 1
    assert twin.reasons.get("TimeoutError") is None  # skipped in time, never timed out
    assert srv.n["conn"] == 3 and srv.n["refused"] == 0 and srv.fatal is None


def decision_sleeps(tmp_path: Path, last_any: float, last_x: float) -> list[float]:
    """One old-style decision frame (model x) through handle() at t = 40 ms (fake clock): its
    sleeps, after a forward of any kind at ``last_any`` and model x's last at ``last_x``."""
    sleeps: list[float] = []
    srv = ds.Server(tmp_path / "s.sock", {}, max_hz=10.0, log=lambda _m: None,
                    clock=lambda: 0.04, sleep=sleeps.append)  # fmt: skip
    srv.last_any, srv.last_dec["x"] = last_any, last_x
    net = FakeNet("a" * 64)
    srv.nets = {"x": net}
    a, b = socket.socketpair()

    def client() -> None:
        a.sendall(json.dumps({"v": 1, "model": "x"}).encode() + b"\n")
        a.sendall(struct.pack("<HHI", 736, 1280, 0) + bytes(736 * 1280 * 3))
        a.shutdown(socket.SHUT_WR)
        while a.recv(1 << 20):
            pass

    th = threading.Thread(target=client, daemon=True)
    th.start()
    srv.handle(b)
    b.close()
    th.join(timeout=5)
    a.close()
    assert len(net.seen) == 1
    return sleeps


def test_a_decision_never_sleeps_out_a_gap_a_hud_forward_started(tmp_path: Path) -> None:
    """s73 (rogue-xmas02.md 4CI): a decision right after a HUD forward slept the rest of the
    100-ms --max-hz gap. Now the gap runs from the last DECISION forward only."""
    assert decision_sleeps(tmp_path, 0.0, -1e18) == []  # a HUD / another model's forward 40 ms ago
    assert decision_sleeps(tmp_path, 0.0, -0.05) == [pytest.approx(0.01)]  # x's own, 90 ms ago
    assert decision_sleeps(tmp_path, 0.0, 0.0) == [pytest.approx(0.06)]  # x's own, as before


def test_hellos_old_and_new(served) -> None:  # type: ignore[no-untyped-def]
    """An old client's hello (no prio) gets exactly the old reply; a "hud" or "decision" hello
    gets its prio echoed; anything else is refused."""
    _srv, _net, sock = served
    c, doc = raw_client(sock, {"v": 1, "model": "v1"})
    assert set(doc) == {"ok", "model", "sha256", "imgsz", "shape"} and doc["ok"] is True
    c.close()
    for prio in ("hud", "decision"):
        c, doc = raw_client(sock, {"v": 1, "model": "v1", "prio": prio})
        assert doc["ok"] is True and doc["prio"] == prio
        c.close()
    for bad in ({"v": 1, "model": "v1", "prio": "urgent"}, {"v": 1, "model": ["v1"]}):
        c, doc = raw_client(sock, bad)
        assert doc["ok"] is False
        c.close()


def test_a_skipped_hud_frame_keeps_its_connection(tmp_path: Path) -> None:
    net = FakeNet(ud.GPU_WEIGHTS["v1"].sha256)
    srv, th, sock = run_server(tmp_path, net, hud_wait_s=0.03)
    body = 4 * 7 * N_ANCH
    try:
        c, f = frame_client(sock, {"v": 1, "model": "v1", "prio": "hud"})
        with c:
            srv.enter_decision()  # the card is a decision's
            head = send_frame(c, f, 200, body)
            assert head["skipped"] == "busy" and set(head) == {"skipped", "wait_ms"}
            srv.leave(ds.DECISION)
            time.sleep(0.12)  # past the --max-hz gap after that forward
            head = send_frame(c, f, 200, body)  # the same connection, served this time
            assert head["shape"] == [1, 7, N_ANCH] and "wait_ms" in head
    finally:
        srv.stop.set()
        th.join(timeout=10)
    assert srv.n["hud_skipped"] == 1 and srv.n["hud"] == 1 and len(net.seen) == 1


def test_a_failing_forward_still_ends_the_server(tmp_path: Path) -> None:
    """As before the threads: an unexpected failure of the forward stops the server (the guarded
    step ends, serve() raises it) instead of only its connection."""

    class Broken(FakeNet):
        def forward(self, canvas: np.ndarray) -> np.ndarray:
            raise RuntimeError("device lost")

    d = tmp_path / "gd"
    d.mkdir(mode=0o700)
    d.chmod(0o700)
    srv = ds.Server(d / "detect.sock", {"v1": Broken(ud.GPU_WEIGHTS["v1"].sha256)},
                    log=lambda _m: None)  # fmt: skip
    raised: list[BaseException] = []

    def serve() -> None:
        try:
            srv.serve()
        except RuntimeError as exc:
            raised.append(exc)

    th = threading.Thread(target=serve, daemon=True)
    th.start()
    assert until(lambda: (d / "detect.sock").exists())
    c, f = frame_client(d / "detect.sock", {"v": 1, "model": "v1"})
    with c:
        c.sendall(struct.pack("<HHI", 736, 1280, 0) + bytes(736 * 1280 * 3))
        assert f.readline() == b""  # closed, no reply
    th.join(timeout=10)
    assert not th.is_alive() and not (d / "detect.sock").exists()
    assert [str(e) for e in raised] == ["device lost"] and srv.fatal is raised[0]


def test_the_hud_twin_end_to_end_skipped_frames_and_never_the_cpu(  # type: ignore[no-untyped-def]
    served, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """unit_detector.GpuDetector.hud_twin (dungeon@9.29c): a second connection that declares
    "hud"; a skipped frame gives no boxes and no CPU call, keeps the connection and does not mark
    the GPU down; closing the twin leaves the decisions' detector and its CPU worker running."""
    srv, _net, sock = served
    srv.hud_wait_s = 0.03
    frame = np.full((720, 1280, 3), 10, np.uint8)
    with ud.GpuDetector(cpu_detector(tmp_path, monkeypatch), "v1", socket_path=sock) as det:
        assert det.prio is None and "prio" not in det.info()
        twin = det.hud_twin()
        assert twin.prio == "hud" and twin.cpu is det.cpu and twin.info()["prio"] == "hud"
        assert twin.detect(frame) == det.detect(frame)  # the same model, the same decoding
        assert twin.last_path == "gpu" and det.last_path == "gpu" and srv.n["conn"] == 2
        assert isinstance(twin.last_wait_ms, float) and isinstance(det.last_wait_ms, float)
        time.sleep(0.12)  # past the --max-hz gap after the decision's forward
        srv.enter_decision()  # the card is a decision's: the twin's next frame is skipped
        sock_before = twin.sock
        assert twin.detect(frame) == []
        srv.leave(ds.DECISION)
        assert twin.last_path == "none" and str(twin.last_reason).startswith("skipped: busy")
        assert twin.sock is sock_before and twin.down_until < 0  # kept, not marked down
        assert twin.counts == {"gpu": 1, "none": 1} and twin.reasons == {"skipped": 1}
        assert twin.detect(frame, prefer="cpu") == [] and twin.last_path == "none"  # never CPU
        time.sleep(0.12)
        assert twin.detect(frame) and twin.last_path == "gpu"  # the same connection again
        assert srv.n["conn"] == 2
        log = tmp_path / "hud.jsonl"
        twin.log_path = log
        time.sleep(0.12)  # HUD after HUD: the --max-hz gap as well
        twin.detect(frame)
        row = json.loads(log.read_text())
        assert row["path"] == "gpu" and isinstance(row["wait_ms"], float)
        twin.close()
        assert twin.sock is None
        assert det.detect(frame, prefer="cpu")[0].x0 == 1.0  # the CPU worker still runs
        assert det.detect(frame) and det.last_path == "gpu"
    assert srv.n["hud_skipped"] == 1 and srv.n["bad"] == 0
