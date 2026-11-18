"""GPU readiness check for the VULKAN vision image (ADR-0022 Amendment 2026-11-18b: AMD's path, any
GPU through Vulkan). Exits non-zero on any failure; never fakes a pass.

Part of the AGPL-3.0 vision component (ADR-0018): it imports poring_vision and runs only inside the
vision image.

    python3 scripts/guarded_build.py 'run:vision@300=python scripts/check_webgpu.py'

(on a dedicated-amd host: guarded_build adds compose.amd.yaml, the Vulkan image and the card's
render node). scripts/check_gpu.py is the CUDA image's twin; this image has no torch.

Checks, the detect server's own path (poring_vision.detect_server --backend onnxruntime --device
webgpu):
- Vulkan sees a GPU with the CPU drivers kept out (poring_vision.vulkan: lavapipe would otherwise
  serve when no GPU is reachable, under the WebGPU name);
- onnxruntime's WebGPU provider loads v1's deployed ONNX from the storage folder with EVERY node on
  it (session.disable_cpu_ep_fallback: no node may slip to the CPU), never its silent CPU fallback;
- its output against the same file on onnxruntime's CPU provider (a sanity bound, not the box
  parity: scripts/gpu_live_parity.py does that on frames), and its forward time.
Reported, never a failure: what the check wrote at run time (Mesa's shader cache belongs in RAM).
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

# the starter model every install has (scripts/detector_setup.py; unit_detector.GPU_WEIGHTS v1), in
# the storage folder the vision containers mount read-only at /datasets
V1_ONNX = Path("/datasets/archive/models/v1png-last-736x1280.onnx")
ORT_MAX_DIFF = 1.0  # a sanity bound (wrong kernels give garbage), not the box parity
WATCHED = [Path.home() / ".cache", Path("/tmp")]
results: list[tuple[str, bool, str]] = []


def files_under(roots: list[Path]) -> dict[str, int]:
    out: dict[str, int] = {}
    for root in roots:
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file():
                    out[str(path)] = path.stat().st_size
    return out


def check(name: str) -> Callable[[Callable[[], str]], None]:
    def run(fn: Callable[[], str]) -> None:
        try:
            results.append((name, True, fn()))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()

    return run


def main() -> int:
    files_before = files_under(WATCHED)
    from poring_vision import vulkan

    os.environ[vulkan.DISABLE_KEY] = vulkan.without_cpu_drivers(os.environ.get(vulkan.DISABLE_KEY))

    @check("Vulkan sees a GPU (CPU drivers kept out)")
    def _() -> str:
        seen = vulkan.devices()
        assert seen is not None, "the Vulkan loader cannot be asked (no libvulkan.so.1)"
        gpus = vulkan.gpus(seen)
        assert gpus, (f"no GPU among {seen} (the card's render node /dev/dri/renderD* and its "
                      "group passed in? Mesa's driver for it in the image?)")  # fmt: skip
        return "; ".join(f"{d['name']} ({d['vendor']}, {d['type']})" for d in gpus)

    @check("onnxruntime WebGPU provider on the card (the detect server's path, v1's ONNX)")
    def _() -> str:
        import numpy as np
        import onnxruntime as ort

        assert V1_ONNX.is_file(), f"{V1_ONNX} missing: scripts/detector_setup.py installs v1"
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        t0 = time.perf_counter()
        try:
            gpu = ort.InferenceSession(str(V1_ONNX), so, providers=["WebGpuExecutionProvider"])
        except Exception as exc:  # onnxruntime retries on its CPU provider, which `so` refuses
            if "Conflicting session configuration" not in str(exc):
                raise
            raise AssertionError(
                "the WebGPU provider did not start (no adapter: the log above "
                "says why); its retry on the CPU provider is refused"
            ) from None
        load_s = time.perf_counter() - t0
        got = gpu.get_providers()
        assert got[0] == "WebGpuExecutionProvider", f"onnxruntime runs {got} (log above)"
        cpu = ort.InferenceSession(str(V1_ONNX), providers=["CPUExecutionProvider"])
        name = gpu.get_inputs()[0].name
        h, w = gpu.get_inputs()[0].shape[2:4]
        x = np.random.default_rng(0).random((1, 3, int(h), int(w)), dtype=np.float32)
        t0 = time.perf_counter()
        yg = gpu.run(None, {name: x})[0]
        first_s = time.perf_counter() - t0
        yc = cpu.run(None, {name: x})[0]
        for _ in range(3):
            gpu.run(None, {name: x})
        t0 = time.perf_counter()
        for _ in range(10):
            gpu.run(None, {name: x})
        ms = (time.perf_counter() - t0) * 100.0
        diff = float(np.max(np.abs(yg.astype(np.float64) - yc)))
        assert yg.shape == yc.shape and diff <= ORT_MAX_DIFF, f"{yg.shape}: WebGPU vs CPU {diff:g}"
        return (
            f"onnxruntime {ort.__version__}, {got}, every node on WebGPU; output "
            f"{tuple(yg.shape)}, max |WebGPU - CPU| {diff:.2g}; {ms:.1f} ms a forward (load "
            f"{load_s:.1f} s, first run {first_s:.1f} s)"
        )

    new_files = {p: n for p, n in files_under(WATCHED).items() if files_before.get(p) != n}
    shown = [f"{p} ({n / 2**20:.1f} MiB)" for p, n in sorted(new_files.items())][:12]
    results.append(("runtime new files (report only)", True, "; ".join(shown) or "none"))

    width = max(len(name) for name, _, _ in results)
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{'OK' if not failed else f'{len(failed)} check(s) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
