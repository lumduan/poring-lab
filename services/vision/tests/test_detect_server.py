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
