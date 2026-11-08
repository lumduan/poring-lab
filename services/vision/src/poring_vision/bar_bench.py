"""What does the PCIe path cost on this accelerator? (Batt 2026-11-08: "how much does the missing
Resizable BAR hurt training or the bot's detection?")

    python -m poring_vision.bar_bench --out /data/train/eval/bar-bench/bench.json \
        [--onnx /datasets/archive/models/xmas02-last-736x1280.onnx]

bot-server's Arc A380 runs with a 256 MiB BAR2: i915 could not resize it to 8 GiB (`-ENOSPC`, the
BIOS's bridge window). That window bounds what the CPU can map of VRAM. Copies issued through the
compute runtime use the GPU's own DMA engines instead. So this measures the paths our work uses,
on the accelerator `accel.current()` picks (ADR-0022, any vendor):

1. host -> device and device -> host copies, pageable and pinned, 1 MB to 512 MB;
2. device -> device (the card's own memory bandwidth, the reference);
3. square matmuls in FP32 / FP16 / BF16 (TFLOPS);
4. the detect server's input path for ONE 736 x 1280 frame:
   - its CPU float conversion (`detect_server.to_input`);
   - the float32 (11.3 MB) and uint8 (2.8 MB) copies to the card;
   - the conversion on the card;
5. with `--onnx`: OpenVINO's call on the accelerator for the same frame. `infer` covers the
   copy in + forward + copy out, next to `to_input` on the CPU;
6. with `--yolo`: one training step's forward + backward of that model at batch 4 on 736 x 1280,
   in FP32 and under BF16 autocast (no GradScaler, so it needs no float64: the Arc has none).
7. with `--mem-probe GB`: does memory ON THE CARD cost host memory too? The cgroup's
   memory.current and this process's RSS before, after allocating and touching GB on the card,
   and after freeing it (2026-11-08: a training run with 4.1 GB on the card held 5.6 GB of the
   worker's 6 GB host cap).

Every timed region ends with the accelerator's synchronize. Each figure is the median of `--reps`
after `--warmup` (the p90 is beside it).
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

SIZES_MB = (1, 4, 11, 45, 128, 256, 512)
FRAME_HW = (736, 1280)  # the detector's input (unit_detector / detect_server IMGSZ)


def stats(ms: list[float]) -> dict[str, float]:
    s = sorted(ms)
    return {"median_ms": statistics.median(s), "p90_ms": s[min(len(s) - 1, int(0.9 * len(s)))]}


def timeit(fn: Callable[[], Any], sync: Callable[[], None], warmup: int, reps: int) -> list[float]:
    for _ in range(warmup):
        fn()
    sync()
    out = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        sync()
        out.append((time.perf_counter() - t) * 1000.0)
    return out


def gbps(nbytes: int, ms: float) -> float:
    return nbytes / (ms / 1000.0) / 1e9


def copies(torch: Any, dev: str, sync: Callable[[], None], warmup: int, reps: int) -> list[dict]:
    rows = []
    for mb in SIZES_MB:
        n = mb * 1_000_000
        gpu = torch.empty(n, dtype=torch.uint8, device=dev)
        for kind in ("pageable", "pinned"):
            try:
                host = torch.empty(n, dtype=torch.uint8, pin_memory=(kind == "pinned"))
                host.fill_(1)
            except Exception as e:  # noqa: BLE001 -- a vendor without pinned host memory
                rows.append({"mb": mb, "kind": kind, "error": f"{type(e).__name__}: {e}"})
                continue
            h2d = stats(timeit(lambda g=gpu, h=host: g.copy_(h), sync, warmup, reps))
            d2h = stats(timeit(lambda g=gpu, h=host: h.copy_(g), sync, warmup, reps))
            rows.append({"mb": mb, "kind": kind,
                         "h2d": {**h2d, "gb_s": gbps(n, h2d["median_ms"])},
                         "d2h": {**d2h, "gb_s": gbps(n, d2h["median_ms"])}})  # fmt: skip
    return rows


def device_copy(torch: Any, dev: str, sync: Callable[[], None], warmup: int, reps: int) -> dict:
    n = 256 * 1_000_000
    a = torch.empty(n, dtype=torch.uint8, device=dev)
    b = torch.empty_like(a)
    st = stats(timeit(lambda: b.copy_(a), sync, warmup, reps))
    # a copy reads n and writes n bytes
    return {"mb": 256, **st, "gb_s_read_plus_write": gbps(2 * n, st["median_ms"])}


def matmuls(torch: Any, dev: str, sync: Callable[[], None], warmup: int, reps: int, n: int) -> dict:
    out = {}
    for name in ("float32", "float16", "bfloat16"):
        dt = getattr(torch, name)
        try:
            a = torch.randn(n, n, device=dev, dtype=dt)
            b = torch.randn(n, n, device=dev, dtype=dt)
            st = stats(timeit(lambda a=a, b=b: a @ b, sync, warmup, reps))
        except Exception as e:  # noqa: BLE001 -- a dtype the card lacks
            out[name] = {"error": f"{type(e).__name__}: {e}"}
            continue
        out[name] = {**st, "tflops": 2 * n**3 / (st["median_ms"] / 1000.0) / 1e12}
    return out


def frame_path(
    torch: Any, np: Any, dev: str, sync: Callable[[], None], warmup: int, reps: int
) -> dict[str, Any]:
    from poring_vision.detect_server import to_input

    h, w = FRAME_HW
    rng = np.random.default_rng(20261108)
    canvas = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    noop = lambda: None  # noqa: E731 -- the CPU step has nothing to synchronize
    x = to_input(canvas)
    res: dict[str, Any] = {"frame_hw": [h, w], "float32_mb": x.nbytes / 1e6,
                           "uint8_mb": canvas.nbytes / 1e6}  # fmt: skip
    res["cpu_to_input"] = stats(timeit(lambda: to_input(canvas), noop, warmup, reps))
    xf = torch.from_numpy(x)
    xu = torch.from_numpy(canvas)
    res["copy_float32"] = stats(timeit(lambda: xf.to(dev), sync, warmup, reps))
    res["copy_uint8"] = stats(timeit(lambda: xu.to(dev), sync, warmup, reps))

    def on_card() -> Any:
        t = xu.to(dev)
        return t[..., [2, 1, 0]].permute(2, 0, 1)[None].float() / 255.0

    res["uint8_copy_plus_card_convert"] = stats(timeit(on_card, sync, warmup, reps))
    return res


def openvino_call(onnx: Path, np: Any, warmup: int, reps: int, device: str) -> dict[str, Any]:
    import openvino as ov

    from poring_vision.detect_server import to_input

    core = ov.Core()
    t = time.perf_counter()
    compiled = core.compile_model(core.read_model(str(onnx)), device)
    compile_s = time.perf_counter() - t
    req = compiled.create_infer_request()
    h, w = FRAME_HW
    canvas = np.random.default_rng(20261108).integers(0, 256, size=(h, w, 3), dtype=np.uint8)
    x = to_input(canvas)
    noop = lambda: None  # noqa: E731 -- infer() returns when the result is on the host
    res: dict[str, Any] = {"onnx": onnx.name, "device": device, "compile_s": compile_s}
    res["cpu_to_input"] = stats(timeit(lambda: to_input(canvas), noop, warmup, reps))
    res["infer_prepared_input"] = stats(timeit(lambda: req.infer({0: x}), noop, warmup, reps))
    res["to_input_plus_infer"] = stats(
        timeit(lambda: req.infer({0: to_input(canvas)}), noop, warmup, reps)
    )
    return res


def tensors(out: Any) -> list[Any]:
    """Every tensor in a model's output: ultralytics' train-mode head returns a dict (8.4)."""
    if isinstance(out, dict):
        return [t for v in out.values() for t in tensors(v)]
    if isinstance(out, (list, tuple)):
        return [t for v in out for t in tensors(v)]
    return [out] if hasattr(out, "backward") else []


def yolo_step(
    torch: Any, weights: Path, dev: str, sync: Callable[[], None], warmup: int, reps: int
) -> dict[str, Any]:
    from ultralytics import YOLO

    model = YOLO(str(weights)).model.to(dev).float().train()
    for q in model.parameters():
        q.requires_grad_(True)
    x = torch.rand(4, 3, *FRAME_HW, device=dev)

    def step(dtype: Any | None) -> None:
        model.zero_grad(set_to_none=True)
        if dtype is None:
            out = model(x)
        else:
            with torch.autocast(device_type=dev.split(":")[0], dtype=dtype):
                out = model(x)
        sum(t.float().sum() for t in tensors(out)).backward()

    res: dict[str, Any] = {"weights": weights.name, "batch": 4, "hw": list(FRAME_HW),
                           "host_before": host_mem()}  # fmt: skip
    for name, dtype in (("float32", None), ("bfloat16_autocast", torch.bfloat16)):
        try:
            res[name] = stats(timeit(lambda d=dtype: step(d), sync, warmup, reps))
        except Exception as e:  # noqa: BLE001 -- report it, keep the others
            res[name] = {"error": f"{type(e).__name__}: {e}"}
    res["host_after"] = host_mem()  # the step's own host memory (11-08: the trainer held 5.2 GB)
    f32, b16 = res.get("float32", {}), res.get("bfloat16_autocast", {})
    if "median_ms" in f32 and "median_ms" in b16:
        res["bf16_speedup"] = f32["median_ms"] / b16["median_ms"]
    return res


def host_mem() -> dict[str, float | None]:
    """This container's cgroup memory and this process's RSS, in MiB (None where unreadable)."""

    def read(path: str) -> str | None:
        try:
            return Path(path).read_text()
        except OSError:
            return None

    cg = read("/sys/fs/cgroup/memory.current")
    status = read("/proc/self/status") or ""
    rss = next((int(ln.split()[1]) / 1024 for ln in status.splitlines()
                if ln.startswith("VmRSS:")), None)  # fmt: skip
    return {"cgroup_mib": None if cg is None else int(cg) / 2**20, "rss_mib": rss}


def mem_probe(
    torch: Any, dev: str, sync: Callable[[], None], gb: float, acc: Any
) -> dict[str, Any]:
    out: dict[str, Any] = {"gb": gb, "before": host_mem()}
    n = int(gb * 1e9)
    t = torch.empty(n, dtype=torch.uint8, device=dev)
    sync()
    out["allocated"] = host_mem()
    t.fill_(7)
    sync()
    out["touched"] = host_mem()
    del t
    acc.empty_cache()
    sync()
    out["freed"] = host_mem()
    b, a = out["before"]["cgroup_mib"], out["touched"]["cgroup_mib"]
    if b is not None and a is not None:
        out["host_mib_per_card_gb"] = (a - b) / gb
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--matmul-n", type=int, default=4096)
    ap.add_argument("--onnx", type=Path, default=None)
    ap.add_argument("--ov-device", default="GPU")
    ap.add_argument("--yolo", type=Path, default=None, help="weights for the training-step check")
    ap.add_argument("--only-yolo", action="store_true", help="skip sections 1-5")
    ap.add_argument("--mem-probe", type=float, default=None, help="GB on the card (7)")
    a = ap.parse_args(argv)

    import numpy as np
    import torch

    from poring_vision import accel

    acc = accel.current()
    dev, sync = acc.device, acc.synchronize
    report: dict[str, Any] = {"accel": accel.describe(acc), "torch": torch.__version__,
                              "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}  # fmt: skip
    if not a.only_yolo:
        report["copies"] = copies(torch, dev, sync, a.warmup, a.reps)
        report["device_copy"] = device_copy(torch, dev, sync, a.warmup, a.reps)
        report["matmul"] = {"n": a.matmul_n,
                            **matmuls(torch, dev, sync, a.warmup, a.reps, a.matmul_n)}  # fmt: skip
        report["frame"] = frame_path(torch, np, dev, sync, a.warmup, a.reps)
        acc.empty_cache()
    if a.mem_probe is not None:
        report["mem_probe"] = mem_probe(torch, dev, sync, a.mem_probe, acc)
    if a.yolo is not None:
        report["yolo_step"] = yolo_step(torch, a.yolo, dev, sync, a.warmup, a.reps)
        acc.empty_cache()
    if a.onnx is not None and not a.only_yolo:
        try:
            report["openvino"] = openvino_call(a.onnx, np, a.warmup, a.reps, a.ov_device)
        except Exception as e:  # noqa: BLE001 -- report it, keep the torch numbers
            report["openvino"] = {"error": f"{type(e).__name__}: {e}"}
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
