"""scripts/cursor_gate.py: a world click only after two allowed cursor reads; fails closed."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def cg() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("cursor_gate", SCRIPTS / "cursor_gate.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeProber:
    def __init__(self, shapes: list[str], parks: bool = True) -> None:
        self.shapes, self.parks, self.clicks = list(shapes), parks, []
        self.agent = self

    def park(self) -> bool:
        return self.parks

    def hover(self, u: float, v: float) -> None:
        pass

    def read(self, u: float, v: float) -> dict[str, Any]:
        return {"shape": self.shapes.pop(0)}

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


@pytest.fixture
def region(cg: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cg.r, "game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(cg.r, "ns", lambda: 7)


def test_clicks_only_after_two_allowed_reads(cg: ModuleType, region: None) -> None:
    pr = FakeProber(["walk", "walk"])
    assert cg.gated_click(pr, 100, 200) == {"clicked": True, "why": "ok", "shape": "walk",
                                            "t_click": 7}  # fmt: skip
    assert pr.clicks == [(180, 277)]
    refused = [(["sword"], "cursor_sword"), (["unknown"], "cursor_unknown"),
               (["talk"], "cursor_talk"), (["walk", "sword"], "recheck_sword")]  # fmt: skip
    for shapes, why in refused:
        pr = FakeProber(shapes)
        assert cg.gated_click(pr, 100, 200)["why"] == why and pr.clicks == []
    pr = FakeProber(["walk", "walk"], parks=False)
    assert cg.gated_click(pr, 100, 200)["why"] == "stale_background" and pr.clicks == []
    pr = FakeProber(["warp", "warp"])
    assert cg.gated_click(pr, 1, 2)["clicked"] is False  # warp only when the caller allows it
    assert cg.gated_click(FakeProber(["warp", "warp"]), 1, 2, allow=("warp",))["clicked"] is True


def test_fails_closed_off_rdp_and_without_references(cg: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(cg.GateUnavailable):
        cg.prober(None, None, backend="console")
    with pytest.raises(cg.GateUnavailable):
        cg.prober(None, None, refs_path=tmp_path / "missing.npz", backend="rdp")


# --- robust2: the default since Batt's 2026-10-13 switch (demonstrations.md 3.36) ---------------
class FakeRobustProber(FakeProber):
    classifier = "robust2"


def test_the_default_reader_is_robust2_and_v3_only_by_name(cg: ModuleType) -> None:
    assert cg.DEFAULT_CLASSIFIER == "robust2" and set(cg.CLASSIFIERS) == {"robust2", "v3"}
    with pytest.raises(cg.GateUnavailable, match="unknown cursor classifier"):
        cg.prober(None, None, backend="rdp", classifier="v4")


def test_robust2_walk_clicks_only_on_a_ring_free_walk_series(
    cg: ModuleType, region: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    w, u = "walk", "unknown"
    series = {"x": ([w, u, u, w, u, u], [0] * 6)}
    monkeypatch.setattr(cg, "read_series", lambda pr, a, b: series["x"])
    pr = FakeRobustProber([])
    got = cg.gated_click(pr, 100, 200)
    assert got["clicked"] is True and got["shape"] == "walk" and pr.clicks == [(180, 277)]
    # v3's hole: both read groups on blink frames read WALK twice; one ring grab refuses the click
    series["x"] = ([w, u, u, w, u, u], [0, 0, 210, 0, 0, 0])
    pr = FakeRobustProber([])
    got = cg.gated_click(pr, 100, 200)
    assert got["clicked"] is False and got["why"] == "robust2_noentry:ring" and pr.clicks == []
    series["x"] = ([u, u, u, w, w, w], [0] * 6)  # not read twice
    pr = FakeRobustProber([])
    assert cg.gated_click(pr, 100, 200)["why"] == "robust2_unknown:not_twice" and pr.clicks == []


def test_robust2_other_intents_keep_the_early_stop_reads(
    cg: ModuleType, region: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_series(*a: Any) -> Any:
        raise AssertionError("a TALK intent must not take the walk series")

    monkeypatch.setattr(cg, "read_series", no_series)
    pr = FakeRobustProber(["talk", "talk"])
    assert cg.gated_click(pr, 1, 2, allow=("talk",))["clicked"] is True


def test_the_series_grabs_and_masks_as_the_measured_harness_did(cg: ModuleType) -> None:
    """robust2 was measured on npc_click_test.read_series's grabs (cursor@2): the gate's series
    keeps the same crop, the same mask and the same count and gap."""
    gate = (SCRIPTS / "cursor_gate.py").read_text()
    harness = (SCRIPTS / "npc_click_test.py").read_text()
    lines = (
        "big = pr.screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]",
        "a = big[28:92, 28:92]",
        "mask = w6.cursor_mask(a, np.where(anim[..., None], a, b))",
        "anim = pr._crop(pr.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0",
    )
    for line in lines:
        assert line in gate and line in harness, line
    assert "READ_GRABS = 6" in harness and "READ_GAP_S = 0.1" in harness
    assert (cg.SERIES_GRABS, cg.SERIES_GAP_S) == (6, 0.1)
