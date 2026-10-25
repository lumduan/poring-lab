"""poring_vision.train's opt-in augmentation override (docs/planning/payf07-detector.md 12f):
host-testable, no torch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from poring_vision.train import hyp_overrides


def test_hsv_s_is_opt_in_and_bounded() -> None:
    assert hyp_overrides(SimpleNamespace(hsv_s=None)) == {}  # ultralytics' default, as before
    assert hyp_overrides(SimpleNamespace(hsv_s=0.2)) == {"hsv_s": 0.2}
    assert hyp_overrides(SimpleNamespace(hsv_s=0.0)) == {"hsv_s": 0.0}
    for bad in (-0.1, 1.5):
        with pytest.raises(SystemExit):
            hyp_overrides(SimpleNamespace(hsv_s=bad))


def test_scale_is_opt_in_bounded_and_independent_of_hsv_s() -> None:
    # gef10-detector.md D7: the size cue survives a small rescale only
    assert hyp_overrides(SimpleNamespace(hsv_s=None, scale=None)) == {}
    assert hyp_overrides(SimpleNamespace(hsv_s=0.2, scale=0.1)) == {"hsv_s": 0.2, "scale": 0.1}
    assert hyp_overrides(SimpleNamespace(hsv_s=None, scale=0.0)) == {"scale": 0.0}
    for bad in (-0.1, 0.95):
        with pytest.raises(SystemExit):
            hyp_overrides(SimpleNamespace(hsv_s=None, scale=bad))
