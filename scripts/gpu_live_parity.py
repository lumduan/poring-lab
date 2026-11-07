#!/usr/bin/env python3
"""The live GPU path's positive case (docs/planning/gpu-live-detector.md section 6): the same
frames through the CPU detector and through ``unit_detector.GpuDetector`` (the vision worker's
detect server), with the DEPLOYED models (``for_map`` / ``for_map_gpu``: v1, and xmas_dun02's
xmas02 with its species collapsed).

    gpu_live_parity.py --refs REFS.json --out OUT.json [--maps prt_fild08,xmas_dun02]
                       [--wait-s 240] [--soak-s 300 --soak-hz 2]

PARITY, per map: each frame's CPU boxes (``det.cpu.detect``) and GPU boxes (``det.detect`` with
``last_path == "gpu"``; a fallback -- an R3 pause window, a timeout -- is logged with its reason
and the frame is tried again every second, up to ``--wait-s``). Boxes match one to one at IoU >=
``--iou`` (0.7) with the SAME class and species, greedy from the best pair. Reported: matched /
CPU boxes, matched / GPU boxes, the largest coordinate difference of a matched pair, the GPU call
times (host clock, the frame to the decoded boxes, socket included).
SOAK: the last map's detector at ``--soak-hz`` for ``--soak-s``, the live bot's way (the GPU,
falling back by itself): each call's time, path and reason, so R3's OFF windows show as fallbacks
and the ON windows as the GPU again.
Frames come from the NAS tar shards (refs as predict_dir writes them). No client, no input.
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu_parity import CONTAINER, HOST, iou  # noqa: E402


def match_same_class(cpu: Sequence[Sequence[Any]], gpu: Sequence[Sequence[Any]],
                     thr: float) -> list[tuple[int, int, float]]:  # fmt: skip
    """PURE: one-to-one (cpu index, gpu index, IoU) at IoU >= thr between rows
    [x0, y0, x1, y1, score, cls, species] of the same cls and species, greedy from the best."""
    pairs = sorted(((iou(c[:4], g[:4]), i, j) for i, c in enumerate(cpu)
                    for j, g in enumerate(gpu) if (c[5], c[6]) == (g[5], g[6])),
                   reverse=True)  # fmt: skip
    used_c: set[int] = set()
    used_g: set[int] = set()
    out = []
    for v, i, j in pairs:
        if v < thr:
            break
        if i in used_c or j in used_g:
            continue
        used_c.add(i)
        used_g.add(j)
        out.append((i, j, v))
    return out


def rows(boxes: Sequence[Any]) -> list[list[Any]]:
    return [[b.x0, b.y0, b.x1, b.y1, b.score, b.cls, b.species] for b in boxes]


def pct(vals: Sequence[float], q: float) -> float | None:
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(q * len(s)))], 2) if s else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--refs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--maps", default="prt_fild08,xmas_dun02")
    ap.add_argument("--iou", type=float, default=0.7)
    ap.add_argument("--wait-s", type=float, default=240.0)
    ap.add_argument("--soak-s", type=float, default=300.0)
    ap.add_argument("--soak-hz", type=float, default=2.0)
    a = ap.parse_args(argv)
    import numpy as np
    import unit_detector as ud
    from PIL import Image

    refs = json.loads(a.refs.read_text())
    frames = []
    for key, ref in refs.items():
        with open(ref["path"].replace(CONTAINER, HOST, 1), "rb") as fh:
            fh.seek(int(ref["offset"]))
            data = fh.read(int(ref["size"]))
        frames.append((key, np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))[..., ::-1]))
    out: dict[str, Any] = {"refs": str(a.refs), "frames": len(frames), "iou": a.iou,
                           "started": time.strftime("%FT%T%z"), "maps": {}}  # fmt: skip
    det = None
    for map_name in a.maps.split(","):
        det = ud.for_map_gpu(map_name)
        n_c = n_g = n_m = 0
        worst = 0.0
        ms: list[float] = []
        falls: list[dict[str, Any]] = []
        unserved = 0
        for key, img in frames:
            cpu = rows(det.cpu.detect(img))
            t_end = time.monotonic() + a.wait_s
            while True:
                t0 = time.monotonic()
                got = det.detect(img)
                if det.last_path == "gpu":
                    ms.append(det.last_ms)
                    break
                falls.append({"t": round(time.time(), 1), "key": key,
                              "reason": det.last_reason,
                              "s": round(time.monotonic() - t0, 3)})  # fmt: skip
                if time.monotonic() >= t_end or det.disabled is not None:
                    got = None
                    break
                time.sleep(1.0)
            if got is None:
                unserved += 1
                continue
            gpu = rows(got)
            m = match_same_class(cpu, gpu, a.iou)
            n_c, n_g, n_m = n_c + len(cpu), n_g + len(gpu), n_m + len(m)
            for i, j, _v in m:
                worst = max(worst, *(abs(float(cpu[i][k]) - float(gpu[j][k])) for k in range(4)))
        out["maps"][map_name] = {
            "weights": det.weights, "onnx": det.model.name, "cpu_boxes": n_c, "gpu_boxes": n_g,
            "matched": n_m, "of_cpu": round(n_m / n_c, 4) if n_c else None,
            "of_gpu": round(n_m / n_g, 4) if n_g else None, "max_coord_diff_px": round(worst, 2),
            "gpu_ms_p50": pct(ms, 0.5), "gpu_ms_p95": pct(ms, 0.95),
            "gpu_ms_mean": round(statistics.fmean(ms), 2) if ms else None,
            "unserved_frames": unserved, "fallbacks": len(falls),
            "fallback_reasons": dict(Counter(str(f["reason"]).split(":")[0] for f in falls)),
            "fallback_log": falls[:200], "detector": det.info(),
        }  # fmt: skip
        brief = {k: v for k, v in out["maps"][map_name].items()
                 if k not in ("fallback_log", "detector")}  # fmt: skip
        print(json.dumps({map_name: brief}), flush=True)
        if map_name != a.maps.split(",")[-1]:
            det.close()
    if det is not None and a.soak_s > 0:
        period = 1.0 / a.soak_hz
        calls: list[dict[str, Any]] = []
        t_end = time.monotonic() + a.soak_s
        i = 0
        while time.monotonic() < t_end:
            t0 = time.monotonic()
            det.detect(frames[i % len(frames)][1])
            calls.append({"t": round(time.time(), 2), "path": det.last_path, "ms": det.last_ms,
                          "wall_ms": round((time.monotonic() - t0) * 1e3, 1),
                          "reason": det.last_reason})  # fmt: skip
            i += 1
            time.sleep(max(0.0, period - (time.monotonic() - t0)))
        gpu_ms = [c["ms"] for c in calls if c["path"] == "gpu"]
        wall_fb = [c["wall_ms"] for c in calls if c["path"] == "cpu"]
        out["soak"] = {"hz": a.soak_hz, "seconds": a.soak_s, "calls": len(calls),
                       "paths": dict(Counter(c["path"] for c in calls)),
                       "reasons": dict(Counter(str(c["reason"]).split(":")[0] for c in calls
                                               if c["path"] == "cpu")),
                       "gpu_ms_p50": pct(gpu_ms, 0.5), "gpu_ms_p95": pct(gpu_ms, 0.95),
                       "fallback_wall_ms_p50": pct(wall_fb, 0.5),
                       "fallback_wall_ms_max": max(wall_fb) if wall_fb else None,
                       "log": calls}  # fmt: skip
        print(json.dumps({"soak": {k: v for k, v in out["soak"].items() if k != "log"}}),
              flush=True)  # fmt: skip
    if det is not None:
        det.close()
    out["ended"] = time.strftime("%FT%T%z")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
