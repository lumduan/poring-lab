"""scripts/cursor_sword.py (Batt 2026-10-18, decision 2 option b): the client's own SWORD cursor
as a detector-independent unit check at loot and walk click points."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import cursor_sword as cs  # noqa: E402


def test_one_read_says_sword_clear_or_unknown() -> None:
    assert cs.verdict({"sword": 0.80, "walk": 0.40, "pickup": 0.10}) == "sword"
    assert cs.verdict({"sword": 0.40, "walk": 1.00, "pickup": 0.05}) == "clear"  # the arrow
    assert cs.verdict({"sword": 0.70, "walk": 0.55, "pickup": 1.00}) == "clear"  # the hand
    assert cs.verdict({"sword": 0.65, "walk": 0.90, "pickup": 0.05}) == "unknown"  # arrow-ish
    assert cs.verdict({"sword": 0.30, "walk": 0.30, "pickup": 0.30}) == "unknown"  # not drawn
    # a SWORD reading wins over a drawn hand or arrow (the unsafe direction is a missed sword)
    assert cs.verdict({"sword": 0.76, "walk": 0.90, "pickup": 0.95}) == "sword"


def test_the_series_fails_toward_safety() -> None:
    assert cs.series(["unknown", "clear"]) == "clear"
    assert cs.series(["clear", "sword"]) == "sword"  # any sword read: no click
    assert cs.series(["unknown", "unknown"]) == "unknown"  # never drawn: no click either
    assert cs.series([]) == "unknown"


def test_the_check_only_moves_never_clicks() -> None:
    src = Path(cs.__file__).read_text()
    body = src[src.index("def check(") :]
    assert ".click(" not in body and body.count("agent.move(") == 2  # two motions


def test_leave_one_out_on_the_references() -> None:
    """Every SWORD crop reads sword, no other crop reads sword, and no SWORD crop reads clear;
    the hand reads clear (else no loot click could pass). The reference itself is excluded."""
    import cursor_robust as cr

    if not cr.REFS_V3.exists():
        pytest.skip("no cursor references on this host (client pixels, gitignored)")
    refs = cr.RobustRefs.load()
    z = np.load(cr.REFS_V3)
    cls = [str(c) for c in z["cls"]]
    idx = [i for i, c in enumerate(cls) if c in ("sword", "pickup")]
    idx += [i for i, c in enumerate(cls) if c not in ("sword", "pickup")][::7]
    for i in idx:
        v = cs.verdict(cs.SwordRefs(refs, exclude_ref=[i]).recalls(z["a"][i]))
        if cls[i] == "sword":
            assert v == "sword", (i, cls[i], v)
        else:
            assert v != "sword", (i, cls[i], v)
        if cls[i] == "pickup":
            assert v == "clear", (i, v)
