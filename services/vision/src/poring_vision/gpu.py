"""GPU setup for a container that SHARES the card with Frigate (NVR) and Ollama."""

import logging

log = logging.getLogger(__name__)


def configure_gpu(max_vram_fraction: float) -> str | None:
    """Cap this process's VRAM and log what the torch build supports. Returns a device string, or
    None when CUDA is unavailable (the loop still runs; detection would fall back to CPU)."""
    import torch

    if not torch.cuda.is_available():
        log.warning("CUDA unavailable (torch %s); running without a GPU", torch.__version__)
        return None
    # Hard cap so a runaway allocation can never starve Frigate's detectors on the same card.
    torch.cuda.set_per_process_memory_fraction(max_vram_fraction, 0)
    major, minor = torch.cuda.get_device_capability(0)
    arch = f"sm_{major}{minor}"
    arches = torch.cuda.get_arch_list()
    log.info(
        "GPU %s (%s), torch %s CUDA %s, arch list %s, VRAM cap %.0f%%",
        torch.cuda.get_device_name(0),
        arch,
        torch.__version__,
        torch.version.cuda,
        arches,
        max_vram_fraction * 100,
    )
    if arch not in arches:
        log.error("this torch build has no %s kernels -- expect 'no kernel image' errors", arch)
    return "cuda:0"
