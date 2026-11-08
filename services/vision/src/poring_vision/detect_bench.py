"""Where does the detect server's forward spend its time on this card? (Batt 2026-11-08: "switch to
the detector that converts on the card, and make it fast".)

    python -m poring_vision.detect_bench --out /data/train/eval/detect-bench/RUN.json \
        --onnx /datasets/archive/models/xmas02-last-736x1280.onnx \
        --frames-tar /datasets/<session>/shard-000000.tar [--frames 20] [--reps 30] \
        [--hz 10 2] [--configs live,f16]

It compiles each deployed ONNX the way ``detect_server.OvNet`` does (the same PrePostProcessor for
``--ov-preproc gpu``, the same LATENCY hint), once per CONFIG:

- ``live``: what runs today (bot-server-migration.md 16a): the conversion on the card, FP32;
- ``f16``: the same with ``INFERENCE_PRECISION_HINT`` f16 (OpenVINO's own GPU default; the Arc's
  XMX units run only f16 / bf16 / int8);
- ``cpu32``: the old path (numpy conversion, FP32), for reference.

and times ``OvNet.forward`` on REAL frames (the recording's PNGs, padded to the canvas as the client
pads them) three ways:

1. back to back (``--reps`` calls, after warm-up);
2. paced at each ``--hz`` (the live bot asks on demand, a few times a second): between calls the
   card idles, and its clock may fall (``gt_act_freq_mhz``, sampled WHILE each call runs);
3. per frame against ``live``: the raw head's largest difference (box columns and scores of the
   anchors either side scores >= ``--conf``) and how many anchors cross ``--conf``. A box-level
   parity is the host's job (scripts/gpu_live_parity.py against a server in that config).

No socket, no client, no input: the forward alone, in the vision worker (a guarded ``execdev:``).
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import tarfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from poring_vision.bar_bench import stats
from poring_vision.detect_server import IMGSZ, OvNet, file_sha256

CONFIGS: dict[str, tuple[str, str]] = {  # name -> (ov_preproc, precision)
    "live": ("gpu", "f32"),
    "f16": ("gpu", "f16"),
    "cpu32": ("cpu", "f32"),
}
PAD = 114  # detector_worker.pad_canvas's grey
CONF = 0.25  # unit_detector.CONF
FREQ_GLOB = "/sys/class/drm/card*/gt_act_freq_mhz"


def parse_configs(text: str) -> list[str]:
    """PURE: "live,f16" -> ["live", "f16"]; unknown or repeated names refused."""
    names = [n.strip() for n in text.split(",") if n.strip()]
    bad = [n for n in names if n not in CONFIGS]
    if bad or not names or len(set(names)) != len(names):
        raise SystemExit(f"--configs {text!r}: distinct names from {sorted(CONFIGS)}")
    return names


def canvas_of(img: np.ndarray, hw: tuple[int, int] = IMGSZ) -> np.ndarray:
    """PURE: a (h, w, 3) uint8 frame of the canvas's width -> the (H, W, 3) canvas, the rows
    centred in grey PAD: detector_worker.pad_canvas when the scale is 1 (1280 x 720 -> 1280 x 736),
    the only case the lab records. Any other shape is refused (it would need the resize)."""
    h, w = img.shape[:2]
    if w != hw[1] or h > hw[0] or img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"frame {img.shape}: needs width {hw[1]} and at most {hw[0]} rows")
    top = (hw[0] - h) // 2
    out = np.full((hw[0], hw[1], 3), PAD, np.uint8)
    out[top : top + h] = img
    return out


def frames_from_tar(path: Path, k: int) -> list[np.ndarray]:
    """The first ``k`` PNG frames of a recording's shard, BGR uint8 (cv2, as the recorder wrote
    them), each as the canvas."""
    import cv2

    out: list[np.ndarray] = []
    with tarfile.open(path) as tar:
        for m in tar:
            if len(out) >= k:
                break
            if not m.isfile() or not m.name.endswith(".png"):
                continue
            fh = tar.extractfile(m)
            if fh is None:
                continue
            buf = np.frombuffer(io.BytesIO(fh.read()).getvalue(), np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if img is not None:
                out.append(canvas_of(img))
    if not out:
        raise SystemExit(f"{path}: no PNG frame")
    return out


def raw_diff(ref: np.ndarray, got: np.ndarray, conf: float = CONF) -> dict[str, float | int]:
    """PURE: two heads (1, 4 + nc, N) for the same frame. Over the anchors whose best class score
    is >= ``conf`` in EITHER: the largest |difference| of the box columns (px on the canvas) and of
    that best score, and how many anchors are >= ``conf`` in one head only (a box that could
    appear or vanish). ``n_ref`` / ``n_got``: the anchors at or above ``conf`` in each."""
    if ref.shape != got.shape:
        raise ValueError(f"shapes {ref.shape} and {got.shape}")
    sr, sg = ref[0, 4:].max(0), got[0, 4:].max(0)
    keep = (sr >= conf) | (sg >= conf)
    box = float(np.abs(ref[0, :4, keep] - got[0, :4, keep]).max()) if keep.any() else 0.0
    score = float(np.abs(sr[keep] - sg[keep]).max()) if keep.any() else 0.0
    return {"box_px": box, "score": score, "cross": int(((sr >= conf) != (sg >= conf)).sum()),
            "n_ref": int((sr >= conf).sum()), "n_got": int((sg >= conf).sum())}  # fmt: skip


def freq_reader(pattern: str = FREQ_GLOB) -> Callable[[], int | None]:
    """The card's actual clock now (MHz), or None where the sysfs file is not visible."""
    paths = sorted(glob.glob(pattern))

    def read() -> int | None:
        for p in paths:
            try:
                return int(Path(p).read_text().strip())
            except (OSError, ValueError):
                continue
        return None

    return read


def timed(net: OvNet, frames: Sequence[np.ndarray], reps: int, gap_s: float,
          freq: Callable[[], int | None]) -> dict[str, Any]:  # fmt: skip
    """``reps`` forwards over the frames in turn, ``gap_s`` apart (0: back to back). The conversion
    on the card (``gpu``) is timed as start_async + wait + the output read, with the card's clock
    read between the start and the wait, i.e. while the call runs; ``cpu`` is ``forward`` itself."""
    ms: list[float] = []
    mhz: list[int] = []
    for i in range(reps):
        if gap_s > 0:
            time.sleep(gap_s)
        f = frames[i % len(frames)]
        x = f[None] if net.preproc == "gpu" else None
        t = time.perf_counter()
        if x is None:
            net.forward(f)
        else:
            net.req.start_async({0: x})
            v = freq()
            net.req.wait()
            np.ascontiguousarray(net.req.get_output_tensor(0).data, dtype="<f4")
            if v is not None:
                mhz.append(v)
        ms.append((time.perf_counter() - t) * 1000.0)
    res: dict[str, Any] = {"reps": reps, "gap_s": gap_s, **stats(ms)}
    if mhz:
        res["mhz_median"] = float(np.median(mhz))
        res["mhz_min"] = int(min(mhz))
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--onnx", type=Path, action="append", required=True)
    ap.add_argument("--frames-tar", type=Path, required=True)
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--reps", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--hz", type=float, nargs="*", default=[10.0, 2.0])
    ap.add_argument("--configs", default="live,f16")
    ap.add_argument("--device", default="GPU")
    ap.add_argument("--conf", type=float, default=CONF)
    a = ap.parse_args(argv)
    names = parse_configs(a.configs)
    frames = frames_from_tar(a.frames_tar, a.frames)
    freq = freq_reader()
    report: dict[str, Any] = {"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                              "frames_tar": str(a.frames_tar), "frames": len(frames),
                              "mhz_idle": freq(), "models": {}}  # fmt: skip
    for onnx in a.onnx:
        sha = file_sha256(str(onnx))
        per: dict[str, Any] = {"sha256": sha}
        refs: list[np.ndarray] | None = None
        for name in names:
            preproc, precision = CONFIGS[name]
            t = time.perf_counter()
            net = OvNet(str(onnx), sha, a.device, precision=precision, preproc=preproc)
            row: dict[str, Any] = {"preproc": preproc, "precision": precision,
                                   "compile_s": round(time.perf_counter() - t, 2)}  # fmt: skip
            for f in frames[: a.warmup]:
                net.forward(f)
            row["back_to_back"] = timed(net, frames, a.reps, 0.0, freq)
            for hz in a.hz:
                row[f"paced_{hz:g}hz"] = timed(net, frames, a.reps, 1.0 / hz, freq)
            outs = [net.forward(f).copy() for f in frames]
            if refs is None:
                refs = outs
                row["vs"] = name
            else:
                diffs = [raw_diff(r, o, a.conf) for r, o in zip(refs, outs, strict=True)]
                row["vs"] = names[0]
                row["raw_diff"] = {"box_px_max": max(d["box_px"] for d in diffs),
                                   "score_max": max(d["score"] for d in diffs),
                                   "cross_total": sum(int(d["cross"]) for d in diffs),
                                   "n_ref_total": sum(int(d["n_ref"]) for d in diffs)}  # fmt: skip
            per[name] = row
            print(json.dumps({onnx.name: {name: row}}), flush=True)
            del net
        report["models"][onnx.name] = per
    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
