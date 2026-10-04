"""GPU readiness check for the vision container. Exits non-zero on any failure; never fakes a pass.

Part of the AGPL-3.0 vision component (ADR-0018): it imports ultralytics and runs only inside the
vision image.

    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        'run:vision@600=python scripts/check_gpu.py'

(a raw `docker compose run` is refused by the repo's hook and scripts/dev.sh: it goes through the IO
guard like any other container start.)

Checks: torch sees the GPU; the VRAM cap the loop applies (VISION_MAX_VRAM_FRACTION, through
poring_vision.gpu.configure_gpu -- the card is shared with Frigate and Ollama) is ENFORCED: an
allocation over it is refused by torch's allocator before it reaches the driver, a small one is
fine; the build is CUDA 13.0 with sm_120 kernels (RTX 5060 Ti = compute capability 12.0 -- a cu126
wheel would fail with "no kernel image is available"); real kernels run (matmul + conv2d, fp32 and
fp16); and an ultralytics YOLO model built from its YAML runs a forward pass on the GPU.
No weights are baked into the image: an audit hook REPORTS (never fails on) any network fetch or new
file a check causes -- e.g. ultralytics downloading something at run time (Batt, 2026-10-03).
"""

import os
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

EXPECTED_CUDA = "13.0"
EXPECTED_ARCH = "sm_120"
results: list[tuple[str, bool, str]] = []
NETWORK: list[str] = []  # every outbound connection / URL request, in order
WATCHED = [Path(os.environ.get("YOLO_CONFIG_DIR", "/tmp/ultralytics")), Path.home() / ".cache",
           Path.home() / ".config", Path("/tmp")]  # fmt: skip


def _audit(event: str, args: tuple[object, ...]) -> None:
    if event == "urllib.Request":
        NETWORK.append(f"urllib {args[0]}")
    elif event == "socket.connect" and len(args) > 1:
        NETWORK.append(f"connect {args[1]}")
    elif event == "socket.getaddrinfo" and args:
        NETWORK.append(f"resolve {args[0]}")


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
            detail = fn()
            results.append((name, True, detail))
        except Exception as exc:
            results.append((name, False, f"{type(exc).__name__}: {exc}"))
            traceback.print_exc()

    return run


def main() -> int:
    sys.addaudithook(_audit)
    files_before = files_under(WATCHED)
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

    @check("VRAM cap enforced (VISION_MAX_VRAM_FRACTION, the loop's own configure_gpu)")
    def _() -> str:
        from poring_vision.gpu import configure_gpu

        fraction = float(os.environ.get("VISION_MAX_VRAM_FRACTION", "0.25"))
        assert configure_gpu(fraction) == "cuda:0", "configure_gpu found no GPU"
        total = torch.cuda.get_device_properties(0).total_memory
        free, _ = torch.cuda.mem_get_info(0)
        over = int((fraction + 0.05) * total)
        try:
            torch.empty(over, dtype=torch.uint8, device="cuda:0")
        except torch.OutOfMemoryError:
            pass  # refused by the caching allocator (the cap), before any cudaMalloc
        else:
            raise AssertionError(f"{over >> 20} MiB (over the cap) was allocated")
        small = min(256 << 20, int(0.25 * free))  # never squeeze Frigate/Ollama to prove a point
        probe = torch.empty(small, dtype=torch.uint8, device="cuda:0")
        del probe
        torch.cuda.empty_cache()
        mib = 1 << 20
        return (
            f"cap {fraction:.0%} = {fraction * total / mib:.0f} of {total / mib:.0f} MiB; "
            f"{over / mib:.0f} MiB refused; {small / mib:.0f} MiB ok; "
            f"card free {free / mib:.0f} MiB"
        )

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
    # Reported, never a failure: what the checks fetched or wrote at run time.
    new_files = {p: n for p, n in files_under(WATCHED).items() if files_before.get(p) != n}
    fetched = sorted({line for line in NETWORK if not line.startswith("connect /")})
    results.append(("runtime network fetches (report only)", True, "; ".join(fetched) or "none"))
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
