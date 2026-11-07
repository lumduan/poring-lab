"""poring_vision.accel (ADR-0022): the host's accelerator, any vendor, from fake torch builds; and
the detect server's OpenVINO backend from a fake openvino (no GPU stack on the host)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_vision import accel
from poring_vision import detect_server as ds


class NS(types.SimpleNamespace):
    pass


def fake_torch(cuda: bool = False, xpu: bool = False, mps: bool = False, hip: str | None = None,
               calls: list[Any] | None = None) -> Any:  # fmt: skip
    log = calls if calls is not None else []

    def dev(kind: str, ok: bool) -> NS:
        return NS(
            is_available=lambda: ok,
            device_count=lambda: 2,
            get_device_name=lambda i: f"{kind}-card-{i}",
            set_per_process_memory_fraction=lambda f, i: log.append((kind, "cap", f, i)),
            max_memory_reserved=lambda i: 3 * 2**20,
            max_memory_allocated=lambda i: 2 * 2**20,
            reset_peak_memory_stats=lambda i: log.append((kind, "reset", i)),
            get_device_properties=lambda i: NS(total_memory=8 * 2**30),
            synchronize=lambda: log.append((kind, "sync")),
            empty_cache=lambda: log.append((kind, "empty")),
            get_rng_state_all=lambda: [f"{kind}-rng"],
            set_rng_state_all=lambda s: log.append((kind, "rng", s)),
        )

    return NS(__version__="9.9", cuda=dev("cuda", cuda), xpu=dev("xpu", xpu),
              backends=NS(mps=NS(is_available=lambda: mps)), mps=NS(synchronize=lambda: None),
              version=NS(cuda="13.0" if cuda and not hip else None, hip=hip, xpu=None))  # fmt: skip


@pytest.mark.parametrize(
    ("kw", "kind", "device", "ul"),
    [
        ({"cuda": True, "xpu": True}, "cuda", "cuda:0", 0),  # auto: CUDA first
        ({"xpu": True}, "xpu", "xpu:0", "xpu"),  # Intel (bot-server's Arc)
        ({"cuda": True, "hip": "6.4"}, "cuda", "cuda:0", 0),  # AMD ROCm: the same torch.cuda API
        ({"mps": True}, "mps", "mps", "mps"),
        ({}, "cpu", "cpu", "cpu"),
    ],
)
def test_auto_takes_the_first_available(kw: dict[str, Any], kind: str, device: str,
                                        ul: Any) -> None:  # fmt: skip
    acc = accel.select("auto", fake_torch(**kw))
    assert (acc.kind, acc.device, acc.ultralytics_device) == (kind, device, ul)


def test_a_named_accelerator_is_used_or_refused_never_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = fake_torch(cuda=True, xpu=True)
    assert accel.select("xpu", t).kind == "xpu"
    monkeypatch.setenv(accel.ACCEL_ENV, "xpu")
    assert accel.select(None, t).kind == "xpu"  # $PORING_ACCEL
    with pytest.raises(SystemExit, match="not available"):
        accel.select("xpu", fake_torch(cuda=True))
    with pytest.raises(SystemExit, match="one of"):
        accel.select("tpu", t)


def test_memory_sync_and_rng_go_to_the_vendors_namespace() -> None:
    calls: list[Any] = []
    acc = accel.select("xpu", fake_torch(xpu=True, cuda=True, calls=calls))
    assert acc.cap(0.25) is True
    acc.synchronize()
    acc.empty_cache()
    acc.reset_peak()
    acc.set_rng_state(["s"])
    assert calls == [("xpu", "cap", 0.25, 0), ("xpu", "sync"), ("xpu", "empty"),
                     ("xpu", "reset", 0), ("xpu", "rng", ["s"])]  # fmt: skip
    assert (acc.peak_mib(), acc.peak_allocated_mib(), acc.total_mib()) == (3.0, 2.0, 8192.0)
    assert acc.rng_state() == ["xpu-rng"] and acc.device_count() == 2
    assert accel.describe(acc)["name"] == "xpu-card-0"


def test_the_cpu_has_no_cap_no_memory_and_no_device_rng() -> None:
    acc = accel.select("cpu", fake_torch())
    assert acc.cap(0.25) is False and acc.peak_mib() is None and acc.rng_state() == []
    acc.set_rng_state([])  # nothing to restore: no call, no error
    assert acc.device_count() == 0


def test_configure_gpu_returns_the_device_and_caps_it() -> None:
    from poring_vision.gpu import configure_gpu

    calls: list[Any] = []
    acc = accel.select("xpu", fake_torch(xpu=True, calls=calls))
    assert configure_gpu(0.5, acc) == "xpu:0" and ("xpu", "cap", 0.5, 0) in calls
    assert configure_gpu(0.5, accel.select("cpu", fake_torch())) is None


def test_the_openvino_backend_runs_the_pinned_onnx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    onnx = tmp_path / "m.onnx"
    onnx.write_bytes(b"not really an onnx")
    seen: dict[str, Any] = {}

    class Req:
        def infer(self, inputs: dict[int, np.ndarray]) -> None:
            seen["x"] = inputs[0]

        def get_output_tensor(self, i: int) -> Any:
            return NS(data=np.zeros((1, 7, 19320), np.float32) + float(seen["x"].mean()))

    class Core:
        def read_model(self, path: str) -> str:
            seen["path"] = path
            return "model"

        def compile_model(self, model: str, device: str, cfg: dict[str, str]) -> Any:
            seen["device"], seen["cfg"] = device, cfg
            return NS(create_infer_request=Req)

    monkeypatch.setitem(sys.modules, "openvino", NS(Core=Core))
    net = ds.OvNet(str(onnx), ds.file_sha256(str(onnx)), "GPU")
    assert net.shape == (1, 7, 19320) and seen["device"] == "GPU"
    assert seen["cfg"]["INFERENCE_PRECISION_HINT"] == "f32"
    canvas = np.zeros((736, 1280, 3), np.uint8)
    canvas[..., 2] = 255  # red in BGR -> channel 0 after the RGB flip
    net.forward(canvas)
    x = seen["x"]
    assert x.shape == (1, 3, 736, 1280) and x.dtype == np.float32
    assert x[0, 0].max() == 1.0 and x[0, 2].max() == 0.0  # the CPU worker's RGB order and scale
    with pytest.raises(SystemExit, match="sha256"):
        ds.OvNet(str(onnx), "0" * 64, "GPU")


def test_mixed_precision_only_where_the_scaler_can_run() -> None:
    """2026-11-07: the Arc A380 has no float64 and AMP's GradScaler needs it: FP32 there."""
    nvidia = accel.select("cuda", fake_torch(cuda=True))
    assert nvidia.has_fp64() and nvidia.amp_ok()
    arc = fake_torch(xpu=True)
    arc.xpu.get_device_properties = lambda i: NS(total_memory=6 * 2**30, has_fp64=False)
    acc = accel.select("xpu", arc)
    assert acc.has_fp64() is False and acc.amp_ok() is False
    big = fake_torch(xpu=True)
    big.xpu.get_device_properties = lambda i: NS(total_memory=24 * 2**30, has_fp64=True)
    assert accel.select("xpu", big).amp_ok() is True
    assert accel.select("cpu", fake_torch()).amp_ok() is False
