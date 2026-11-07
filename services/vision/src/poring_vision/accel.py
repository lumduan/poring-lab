"""Vendor-neutral accelerators (ADR-0022, Batt 2026-11-07: "do not lock the bot to one GPU vendor").
The ONE module that knows which vendor a host has; nothing else calls ``torch.cuda`` directly.

    acc = accel.current()       # chosen once: $PORING_ACCEL = auto | cuda | xpu | mps | cpu
    acc.kind                    # "cuda" (NVIDIA, and AMD ROCm builds), "xpu" (Intel), "mps", "cpu"
    acc.device                  # torch's device string: "cuda:0", "xpu:0", "mps", "cpu"
    acc.ultralytics_device      # what ultralytics takes: 0, "xpu", "mps", "cpu"
    acc.cap(0.25); acc.peak_mib(); acc.total_mib(); acc.synchronize(); acc.empty_cache()
    acc.rng_state(); acc.set_rng_state(states)

``auto`` takes the first available of cuda, xpu, mps, else the CPU. A named kind that is not
available is refused (SystemExit), never silently replaced. torch is imported lazily, so this
module stays importable on the host without the GPU stack.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

ACCEL_ENV = "PORING_ACCEL"
KINDS = ("cuda", "xpu", "mps", "cpu")
AUTO_ORDER = ("cuda", "xpu", "mps")
_CURRENT: Accel | None = None


def available(torch: Any, kind: str) -> bool:
    """PURE in its argument: is ``kind`` usable with this torch build on this host?"""
    if kind == "cpu":
        return True
    if kind == "cuda":
        return bool(torch.cuda.is_available())
    if kind == "xpu":
        return hasattr(torch, "xpu") and bool(torch.xpu.is_available())
    if kind == "mps":
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        return mps is not None and bool(mps.is_available())
    raise ValueError(f"unknown accelerator {kind!r} (one of {KINDS})")


@dataclass
class Accel:
    kind: str
    torch: Any = field(repr=False, default=None)
    index: int = 0

    @property
    def device(self) -> str:
        return f"{self.kind}:{self.index}" if self.kind in ("cuda", "xpu") else self.kind

    @property
    def ultralytics_device(self) -> int | str:
        return self.index if self.kind == "cuda" else self.kind

    def _ns(self) -> Any:
        """torch.cuda / torch.xpu / torch.mps, or None for the CPU."""
        if self.kind == "cpu" or self.torch is None:
            return None
        return getattr(self.torch, self.kind, None)

    def _call(self, name: str, *args: Any, default: Any = None) -> Any:
        fn = getattr(self._ns(), name, None)
        return fn(*args) if callable(fn) else default

    def name(self) -> str:
        if self.kind in ("cuda", "xpu"):
            return str(self._call("get_device_name", self.index, default=self.kind))
        return self.kind

    def device_count(self) -> int:
        if self.kind == "cpu":
            return 0
        return int(self._call("device_count", default=1))

    def has_fp64(self) -> bool:
        """Does the device run float64? Intel's Arc A-series does not (2026-11-07: AMP's
        GradScaler computes its inverse scale in float64 and crashed there; Intel's FP64
        emulation failed the same call with a Level Zero error)."""
        if self.kind == "xpu":
            props = self._call("get_device_properties", self.index)
            return bool(getattr(props, "has_fp64", True))
        return self.kind != "mps"  # MPS has no float64 either

    def amp_ok(self) -> bool:
        """May training use mixed precision (FP16 autocast + GradScaler)? Not on the CPU, and not
        where the scaler's float64 cannot run (then the training is FP32)."""
        return self.kind in ("cuda", "xpu") and self.has_fp64()

    def cap(self, fraction: float) -> bool:
        """Cap this process's device memory (a SHARED host's rule R1); False when the backend has
        no per-process cap (logged; a dedicated host needs none)."""
        if self.kind not in ("cuda", "xpu"):
            return False
        fn = getattr(self._ns(), "set_per_process_memory_fraction", None)
        if not callable(fn):
            log.warning("%s has no per-process memory cap in this torch build", self.kind)
            return False
        fn(fraction, self.index)
        return True

    def peak_mib(self) -> float | None:
        if self.kind not in ("cuda", "xpu"):
            return None
        v = self._call("max_memory_reserved", self.index)
        return None if v is None else round(float(v) / 2**20, 1)

    def peak_allocated_mib(self) -> float | None:
        if self.kind not in ("cuda", "xpu"):
            return None
        v = self._call("max_memory_allocated", self.index)
        return None if v is None else round(float(v) / 2**20, 1)

    def reset_peak(self) -> None:
        if self.kind in ("cuda", "xpu"):
            self._call("reset_peak_memory_stats", self.index)

    def total_mib(self) -> float | None:
        props = self._call("get_device_properties", self.index) if self.kind in ("cuda", "xpu") \
            else None  # fmt: skip
        return None if props is None else round(float(props.total_memory) / 2**20, 1)

    def synchronize(self) -> None:
        if self.kind != "cpu":
            self._call("synchronize")

    def empty_cache(self) -> None:
        if self.kind != "cpu":
            self._call("empty_cache")

    def rng_state(self) -> list[Any]:
        """The device RNG states for an exact resume ([] on the CPU or without one)."""
        if self.kind not in ("cuda", "xpu"):
            return []
        return list(self._call("get_rng_state_all", default=[]) or [])

    def set_rng_state(self, states: list[Any]) -> None:
        if states and self.kind in ("cuda", "xpu"):
            self._call("set_rng_state_all", states)


def select(prefer: str | None = None, torch: Any = None) -> Accel:
    """The accelerator: ``prefer`` (else $PORING_ACCEL, else "auto"). ``torch``: tests."""
    want = (prefer or os.environ.get(ACCEL_ENV) or "auto").strip().lower()
    if want != "auto" and want not in KINDS:
        raise SystemExit(f"{ACCEL_ENV}={want!r}: one of auto, {', '.join(KINDS)}")
    if torch is None:
        import torch as torch_mod

        torch = torch_mod
    if want == "auto":
        kind = next((k for k in AUTO_ORDER if available(torch, k)), "cpu")
    elif available(torch, want):
        kind = want
    else:
        raise SystemExit(f"{ACCEL_ENV}={want}: not available with this torch build on this host")
    return Accel(kind, torch)


def current() -> Accel:
    """The process's accelerator, chosen once (select() with the environment)."""
    global _CURRENT
    if _CURRENT is None:
        _CURRENT = select()
    return _CURRENT


def describe(acc: Accel) -> dict[str, Any]:
    """For logs and run summaries: what ran where."""
    t = acc.torch
    out: dict[str, Any] = {"kind": acc.kind, "device": acc.device, "name": acc.name(),
                           "torch": getattr(t, "__version__", None)}  # fmt: skip
    version = getattr(t, "version", None)
    for attr in ("cuda", "hip", "xpu"):
        v = getattr(version, attr, None)
        if v:
            out[attr] = v
    return out
