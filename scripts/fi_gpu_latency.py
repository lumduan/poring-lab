#!/usr/bin/env python3
"""I5's GPU measure for the floor-item model (docs/planning/xmas02-detector.md O13 / O15): the
runner's path, GpuDetector through the RUNNING detect server, over the same frames for each model.

    fi_gpu_latency.py REFS.json OUT.json MODEL

- REFS.json: fi_labels.py refs output (frame key -> recorded frame), already the sample to use.
- MODEL: one of ONNX below. ONE model a run: the detect server serves one client connection at a
  time (O13: a second client got BlockingIOError and its CPU fallback loaded the host).
- OUT.json: per model the GpuDetector call ms (host clock, as D1) and the server's own forward ms
  (``last_server_ms``), each as eval_latency.summary, and the path counts (gpu / cpu fallback).
  O15's bar reads the SERVER time: the call time adds ~35 ms of this harness to every model.
Kept verbatim from O13's scratch copy (only this docstring and the argument check are new).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_latency as el  # noqa: E402
import unit_detector as ud  # noqa: E402

M = Path("/dev/shm/poring-lab-detector/model")
ONNX = {"xmas02fi": "xmas02fi-last-736x1280.onnx", "xmas02gb": "xmas02gb-last-736x1280.onnx"}


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[3] not in ONNX:
        raise SystemExit(f"usage: fi_gpu_latency.py REFS.json OUT.json MODEL ({sorted(ONNX)})")
    refs = json.loads(Path(sys.argv[1]).read_text())
    keys = sorted(refs)
    only = [sys.argv[3]]
    dets = {n: ud.GpuDetector(ud.UnitDetector(model=M / ONNX[n]), weights=n) for n in only}
    ms: dict[str, list[float]] = {n: [] for n in dets}
    paths: dict[str, dict[str, int]] = {n: {} for n in dets}
    server: dict[str, list[float]] = {n: [] for n in dets}
    try:
        for i, k in enumerate(keys):
            img = el.read_frame(refs[k])
            for n in el.rotation(list(dets), i):
                dets[n].detect(img)
                p = dets[n].last_path
                paths[n][p] = paths[n].get(p, 0) + 1
                if p == "gpu":
                    ms[n].append(float(dets[n].last_ms))
                    if dets[n].last_server_ms is not None:
                        server[n].append(float(dets[n].last_server_ms))
    finally:
        for d in dets.values():
            d.cpu.close()
    out = {
        "reasons": {n: dict(dets[n].reasons) for n in dets},
        "disabled": {n: dets[n].disabled for n in dets},
        "what": "O13 / O15 I5 GPU: GpuDetector call ms (host clock, as D1) and server forward ms",
        "frames": len(keys),
        "models": {
            n: {"call": el.summary(ms[n]), "server": el.summary(server[n]), "paths": paths[n]}
            for n in dets
        },
    }
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
