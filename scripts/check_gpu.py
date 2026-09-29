"""GPU readiness check for the vision container. Exits non-zero on any failure; never fakes a pass.

    docker compose --profile vision run --rm vision python scripts/check_gpu.py

Checks: torch sees the GPU; the build is CUDA 13.0 with sm_120 kernels (RTX 5060 Ti = compute
capability 12.0 -- a cu126 wheel would fail with "no kernel image is available"); real kernels run
(matmul + conv2d, fp32 and fp16); and an ultralytics YOLO model built from its YAML (no weight
download) runs a forward pass on the GPU.
"""

import sys
import time
import traceback
from collections.abc import Callable

EXPECTED_CUDA = "13.0"
EXPECTED_ARCH = "sm_120"
results: list[tuple[str, bool, str]] = []


def check(name: str) -> Callable[[Callable[[], str]], None]:
    def run(fn: Callable[[], str]) -> None:
        try:
            detail = fn()
            results.append((name, True, detail))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()

    return run


def main() -> int:
    import torch

    @check("torch import / build")
    def _() -> str:
        cuda = torch.version.cuda
        assert cuda == EXPECTED_CUDA, f"torch CUDA {cuda} != {EXPECTED_CUDA} (wrong wheel index?)"
        return f"torch {torch.__version__}, CUDA {cuda}, cuDNN {torch.backends.cudnn.version()}"

    @check("CUDA device visible")
    def _() -> str:
        assert torch.cuda.is_available(), "cudaGetDeviceCount == 0 (runtime/driver/passthrough?)"
        return f"{torch.cuda.device_count()} device(s): {torch.cuda.get_device_name(0)}"

    @check(f"{EXPECTED_ARCH} in torch.cuda.get_arch_list()")
    def _() -> str:
        arches = torch.cuda.get_arch_list()
        major, minor = torch.cuda.get_device_capability(0)
        assert EXPECTED_ARCH in arches, f"{EXPECTED_ARCH} missing from {arches}"
        assert f"sm_{major}{minor}" in arches, f"device is sm_{major}{minor}, build has {arches}"
        return f"capability ({major}, {minor}); arch list {arches}"

    @check("kernels run (matmul + conv2d, fp32/fp16)")
    def _() -> str:
        dev = torch.device("cuda:0")
        timings = []
        for dtype in (torch.float32, torch.float16):
            a = torch.randn(2048, 2048, device=dev, dtype=dtype)
            x = torch.randn(1, 3, 720, 1280, device=dev, dtype=dtype)
            conv = torch.nn.Conv2d(3, 16, 3, padding=1).to(dev, dtype)
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            (a @ a).sum().item()
            conv(x).mean().item()
            torch.cuda.synchronize()
            timings.append(
                f"{str(dtype).removeprefix('torch.')} {1000 * (time.perf_counter() - t0):.1f} ms"
            )
        return ", ".join(timings)

    @check("ultralytics YOLO forward on GPU (yolo11n.yaml, no download)")
    def _() -> str:
        import ultralytics
        from ultralytics import YOLO

        model = YOLO("yolo11n.yaml").model.to("cuda:0").eval()
        with torch.inference_mode():
            out = model(torch.zeros(1, 3, 640, 640, device="cuda:0"))
        torch.cuda.synchronize()
        first = out[0] if isinstance(out, (list, tuple)) else out
        return f"ultralytics {ultralytics.__version__}, output {tuple(first.shape)}"

    if torch.cuda.is_available():
        used = torch.cuda.max_memory_allocated(0) / 2**20
        results.append(("peak VRAM (this process)", True, f"{used:.0f} MiB"))

    width = max(len(name) for name, _, _ in results)
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{'OK' if not failed else f'{len(failed)} check(s) FAILED'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
