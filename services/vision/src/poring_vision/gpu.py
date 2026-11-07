"""GPU setup: this host's accelerator, any vendor (ADR-0022), capped when the host is shared."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def configure_gpu(max_vram_fraction: float, acc: Any = None) -> str | None:
    """Pick the host's accelerator (``accel.current()``: $PORING_ACCEL, else the first of CUDA, XPU,
    MPS), cap this process's device memory at ``max_vram_fraction`` (R1 on a SHARED host: the GPU
    there also runs Frigate's detectors), and log what it is. Returns torch's device string
    ("cuda:0", "xpu:0", "mps"), or None when only the CPU is there."""
    from poring_vision import accel

    acc = acc if acc is not None else accel.current()
    if acc.kind == "cpu":
        log.warning("no accelerator (%s); running without a GPU", accel.describe(acc))
        return None
    capped = acc.cap(max_vram_fraction)
    log.info("accelerator %s, memory cap %s", accel.describe(acc),
             f"{max_vram_fraction * 100:.0f}%" if capped else "none")  # fmt: skip
    t = acc.torch
    if acc.kind == "cuda" and not getattr(getattr(t, "version", None), "hip", None):
        # NVIDIA: this torch build must carry the card's architecture (cu126 had no sm_120)
        major, minor = t.cuda.get_device_capability(acc.index)
        arch = f"sm_{major}{minor}"
        if arch not in t.cuda.get_arch_list():
            log.error("this torch build has no %s kernels -- expect 'no kernel image' errors", arch)
    return str(acc.device)
