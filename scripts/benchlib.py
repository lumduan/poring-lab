"""Pure helpers for the capture-backend benchmark (docs/benchmarks/SPEC.md): no I/O, unit-tested.

* percentiles the SPEC way: nearest rank over ALL trials, a miss (no frame within the cap) counting
  as +inf, reported as ">cap";
* PSNR / SSIM of UI crops against the lossless reference (numpy only);
* the run's config hash;
* markdown tables.
"""

import hashlib
import json
import math
import statistics
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

SPEC_VERSION = 1
MISS = math.inf
QUANTILES = (0.50, 0.75, 0.90, 0.95, 0.99)


def nearest_rank(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile: the smallest value with at least q of the data at or below it."""
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def delay_summary(
    delays_ms: Sequence[float], trials: int, cap_ms: float = 1500.0
) -> dict[str, Any]:
    """{matched, trials, p50..p99}: every trial counts; unmatched ones are misses (> cap)."""
    if len(delays_ms) > trials:
        raise ValueError(f"{len(delays_ms)} delays for {trials} trials")
    values = [d if d <= cap_ms else MISS for d in delays_ms] + [MISS] * (trials - len(delays_ms))
    out: dict[str, Any] = {"matched": sum(1 for v in values if v != MISS), "trials": trials}
    for q in QUANTILES:
        value = nearest_rank(values, q)
        out[f"p{round(q * 100)}"] = None if math.isnan(value) else fmt_ms(value, cap_ms)
    return out


def fmt_ms(value: float, cap_ms: float = 1500.0) -> float | str:
    return f">{cap_ms:g}" if value == MISS or value > cap_ms else round(value, 1)


def fps_summary(per_second: Sequence[int]) -> dict[str, float | None]:
    """Delivered frames per second during motion: median and p10/p90 (as measure_motion.py)."""
    if not per_second:
        return {"median": None, "p10": None, "p90": None}
    if len(per_second) < 10:
        return {"median": float(statistics.median(per_second)), "p10": None, "p90": None}
    q = statistics.quantiles(per_second, n=10)
    return {"median": float(statistics.median(per_second)), "p10": q[0], "p90": q[8]}


# --- fidelity -------------------------------------------------------------------------------------

Image = npt.NDArray[np.uint8]


def _luma(img: Image) -> npt.NDArray[np.float64]:
    """BGR(A) or grey -> float luma (BT.601), the channel text legibility lives in."""
    a = img.astype(np.float64)
    if a.ndim == 2:
        return a
    b, g, r = a[..., 0], a[..., 1], a[..., 2]
    return 0.114 * b + 0.587 * g + 0.299 * r


def psnr(reference: Image, test: Image) -> float:
    """PSNR in dB over all channels (inf when identical)."""
    if reference.shape != test.shape:
        raise ValueError(f"shape mismatch {reference.shape} vs {test.shape}")
    mse = float(np.mean((reference.astype(np.float64) - test.astype(np.float64)) ** 2))
    return math.inf if mse == 0 else 10 * math.log10(255.0**2 / mse)


def _gaussian(size: int = 11, sigma: float = 1.5) -> npt.NDArray[np.float64]:
    ax = np.arange(size) - (size - 1) / 2
    g = np.exp(-(ax**2) / (2 * sigma**2))
    k: npt.NDArray[np.float64] = np.outer(g, g)
    return np.asarray(k / k.sum(), dtype=np.float64)


def _filter(img: npt.NDArray[np.float64], k: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """'valid' 2-D correlation via sliding windows (no scipy on the host)."""
    from numpy.lib.stride_tricks import sliding_window_view

    windows = sliding_window_view(img, k.shape)
    return np.asarray(np.einsum("ijkl,kl->ij", windows, k), dtype=np.float64)


def ssim(reference: Image, test: Image) -> float:
    """Mean SSIM of the luma (Wang et al. 2004: 11x11 Gaussian, sigma 1.5, K1 .01, K2 .03)."""
    if reference.shape != test.shape:
        raise ValueError(f"shape mismatch {reference.shape} vs {test.shape}")
    x, y = _luma(reference), _luma(test)
    if min(x.shape) < 11:
        raise ValueError("crop smaller than the 11x11 SSIM window")
    k = _gaussian()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mx, my = _filter(x, k), _filter(y, k)
    sxx = _filter(x * x, k) - mx * mx
    syy = _filter(y * y, k) - my * my
    sxy = _filter(x * y, k) - mx * my
    num = (2 * mx * my + c1) * (2 * sxy + c2)
    den = (mx * mx + my * my + c1) * (sxx + syy + c2)
    return float(np.mean(num / den))


# --- config hash and tables -----------------------------------------------------------------------


def config_hash(config: dict[str, Any]) -> str:
    """12 hex of sha256 over canonical JSON: same config -> same hash, across machines."""
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def markdown_table(columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    def cell(v: Any) -> str:
        if v is None:
            return "–"
        if isinstance(v, float):
            return "inf" if math.isinf(v) else f"{v:g}"
        return str(v).replace("|", "\\|")

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)
