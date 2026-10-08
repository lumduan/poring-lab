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
