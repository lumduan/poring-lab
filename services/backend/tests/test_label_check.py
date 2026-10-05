"""scripts/label_check.py: M5's automatic label check -- the masked NCC and the low-score buckets,
on synthetic arrays (rendering itself is test_render's)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def lc() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("label_check", SCRIPTS / "label_check.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ncc_ignores_brightness_and_contrast_but_not_the_pattern(lc: ModuleType) -> None:
    rng = np.random.default_rng(3)
    a = rng.uniform(0, 255, (20, 20))
    mask = np.ones((20, 20), bool)
    assert lc.ncc(a, a, mask) == pytest.approx(1.0)
    assert lc.ncc(a, 0.5 * a + 40, mask) == pytest.approx(1.0)  # map lighting / tint
    assert lc.ncc(a, 255 - a, mask) == pytest.approx(-1.0)
    assert abs(lc.ncc(a, rng.uniform(0, 255, (20, 20)), mask)) < 0.3  # the background
    tiny = np.zeros((20, 20), bool)
    tiny[:2, :2] = True
    assert lc.ncc(a, a, tiny) is None  # fewer than MIN_PIXELS opaque pixels
    assert lc.ncc(np.ones((20, 20)), a, mask) is None  # no variance


def test_a_low_score_is_occluded_ui_covered_or_a_bad_label(lc: ModuleType) -> None:
    box = (600.0, 400.0, 650.0, 450.0)
    assert lc.classify(box, [(640.0, 430.0, 690.0, 480.0)]) == "occluded"
    assert lc.classify((100.0, 100.0, 150.0, 150.0), []) == "ui_covered"  # Basic Information
    assert lc.classify(box, [(700.0, 400.0, 750.0, 450.0)]) == "bad_label"
