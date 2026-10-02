"""scripts/benchlib.py: the benchmark's arithmetic (docs/benchmarks/SPEC.md)."""

import importlib.util
import math
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "benchlib.py"


@pytest.fixture(scope="module")
def bl() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchlib", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nearest_rank_matches_the_tables_already_published(bl: ModuleType) -> None:
    # 2026-10-01 AVCthin @ new_4-1: 39 matched of 40 -> p75 269, p90 439, p95 1370 (nearest rank).
    values = list(range(1, 41))
    assert bl.nearest_rank(values, 0.5) == 20
    assert bl.nearest_rank(values, 0.75) == 30
    assert bl.nearest_rank(values, 0.95) == 38
    assert math.isnan(bl.nearest_rank([], 0.5))


def test_delay_summary_counts_misses_as_beyond_the_cap(bl: ModuleType) -> None:
    out = bl.delay_summary([100.0] * 35 + [1600.0], trials=40)
    assert out["matched"] == 35 and out["trials"] == 40  # the 1.6 s one is a miss too
    assert out["p50"] == 100.0 and out["p75"] == 100.0
    assert out["p90"] == ">1500" and out["p99"] == ">1500"
    with pytest.raises(ValueError):
        bl.delay_summary([1.0, 2.0], trials=1)


def test_fps_summary(bl: ModuleType) -> None:
    out = bl.fps_summary([30] * 50 + [29] * 5 + [28] * 5)
    assert out["median"] == 30 and out["p10"] <= 29 and out["p90"] == 30
    assert bl.fps_summary([])["median"] is None


def test_psnr_and_ssim(bl: ModuleType) -> None:
    rng = np.random.default_rng(1)
    img = rng.integers(0, 256, (40, 60, 3), dtype=np.uint8)
    assert bl.psnr(img, img) == math.inf
    assert bl.ssim(img, img) == pytest.approx(1.0)
    noisy = np.clip(img.astype(int) + rng.integers(-8, 9, img.shape), 0, 255).astype(np.uint8)
    assert 28 < bl.psnr(img, noisy) < 40
    assert 0.5 < bl.ssim(img, noisy) < 1.0
    blurred = ((img.astype(int) + np.roll(img, 1, axis=1)) // 2).astype(np.uint8)
    assert bl.ssim(img, blurred) < bl.ssim(img, noisy) or bl.psnr(img, blurred) < 40
    with pytest.raises(ValueError):
        bl.ssim(img, img[:, :50])


def test_config_hash_is_canonical(bl: ModuleType) -> None:
    a = {"backend": "rdp", "codec": "progressive", "fps_limit": 30}
    b = {"fps_limit": 30, "codec": "progressive", "backend": "rdp"}
    assert bl.config_hash(a) == bl.config_hash(b) and len(bl.config_hash(a)) == 12
    assert bl.config_hash(a) != bl.config_hash({**a, "codec": "AVCthin"})


def test_markdown_table(bl: ModuleType) -> None:
    md = bl.markdown_table(["a", "b"], [[1.5, None], ["x|y", math.inf]])
    assert md.splitlines() == ["| a | b |", "|---|---|", "| 1.5 | – |", "| x\\|y | inf |"]
