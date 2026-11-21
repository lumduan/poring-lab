"""cursor-1080.md Amendment 8 (Batt 2026-11-21: "see it, click to strike at once; the arrow over
its head means it is locked"): 5b's arm C. At a point inside a FRESH monster box the sword check
reads at most 0.10 s and an undecided read strikes; every other hover is the runner's own check.
A player setting, off by default; the runner file stays byte-identical."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_play as fp  # noqa: E402

from poring_flow import settings as st  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def mob(x0: float, y0: float) -> Any:
    return types.SimpleNamespace(x0=x0, y0=y0, x1=x0 + 40, y1=y0 + 50, cls="monster",
                                 species="cruiser", score=0.9)  # fmt: skip


def sight_with(clk: Clock) -> Any:
    s = fp.Sight(uv=lambda: None, clock=clk)
    s.add([mob(500, 300)])
    return s


def fake_check(verdict: str, calls: list[float]) -> Any:
    def check(agent: Any, screen: Any, sw: Any, gx0: int, gy0: int, u: float, v: float, *,
              wait_s: float, **k: Any) -> dict[str, Any]:  # fmt: skip
        calls.append(wait_s)
        return {"verdict": verdict, "reads": [verdict], "ms": 10}

    return check


def on() -> dict[str, Any]:
    return {**st.flag_defaults(), "cursor_click_on_sight": True}


def test_off_by_default_a_player_switch() -> None:
    f = st.BY_NAME["cursor_click_on_sight"]
    assert f.kind == "switch" and f.optional and f.player and not f.flag
    assert st.DEFAULTS["cursor_click_on_sight"] is False


def test_inside_a_fresh_box_an_undecided_look_strikes_after_0_10_s(monkeypatch: Any) -> None:
    import cursor_sword as csw

    calls: list[float] = []
    monkeypatch.setattr(csw, "check", fake_check("unknown", calls))
    clk = Clock()
    s = sight_with(clk)
    with fp.click_on_sight(on(), s):
        got = csw.check(None, None, None, 0, 0, 520, 330, wait_s=1.0)
    assert got["verdict"] == "sword" and got["on_sight"] is True and calls == [fp.SIGHT_LOOK_S]


def test_the_walk_arrow_still_stops_a_click_and_outside_boxes_are_untouched(
    monkeypatch: Any,
) -> None:
    import cursor_sword as csw

    calls: list[float] = []
    monkeypatch.setattr(csw, "check", fake_check("clear", calls))
    clk = Clock()
    s = sight_with(clk)
    with fp.click_on_sight(on(), s):
        assert csw.check(None, None, None, 0, 0, 520, 330, wait_s=1.0)["verdict"] == "clear"
    monkeypatch.setattr(csw, "check", fake_check("unknown", calls := []))
    with fp.click_on_sight(on(), s):
        far = csw.check(None, None, None, 0, 0, 900, 100, wait_s=0.35)  # no monster box there
    assert far["verdict"] == "unknown" and "on_sight" not in far and calls == [0.35]


def test_a_stale_read_is_not_fresh(monkeypatch: Any) -> None:
    import cursor_sword as csw

    calls: list[float] = []
    monkeypatch.setattr(csw, "check", fake_check("unknown", calls))
    clk = Clock()
    s = sight_with(clk)
    clk.t += fp.SIGHT_BOX_AGE_S + 0.1
    with fp.click_on_sight(on(), s):
        got = csw.check(None, None, None, 0, 0, 520, 330, wait_s=0.35)
    assert got["verdict"] == "unknown" and calls == [0.35]


def test_off_and_restored(monkeypatch: Any) -> None:
    import cursor_sword as csw

    calls: list[float] = []
    orig = fake_check("unknown", calls)
    monkeypatch.setattr(csw, "check", orig)
    s = sight_with(Clock())
    with fp.click_on_sight({**st.flag_defaults()}, s):
        assert csw.check is orig
    with fp.click_on_sight(on(), s):
        assert csw.check is not orig
    assert csw.check is orig


def test_item_model_reads_never_replace_the_monsters() -> None:
    clk = Clock()
    s = sight_with(clk)
    item_det = types.SimpleNamespace(names=["floor_item"])
    mob_det = types.SimpleNamespace(names=["cruiser", "mystcase", "floor_item"])
    assert fp.items_only(item_det) and not fp.items_only(mob_det)
    assert not fp.items_only(types.SimpleNamespace())  # no names: treated as a monster model
    assert s.box_at(520, 330)
