"""scripts/m4_spawns.py --check-client: nothing is recorded unless the RO client is on screen
(2026-10-04: a console stream showed the Windows sign-in screen and a minute of it was recorded)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def m4() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("m4_spawns", SCRIPTS / "m4_spawns.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("distance", "ok"),
    [(3.0, True), (30.4, True), (40.0, True), (40.1, False), (120.0, False)],
)
def test_the_client_gate_takes_an_active_or_inactive_title_only(
    m4: ModuleType, monkeypatch: pytest.MonkeyPatch, distance: float, ok: bool
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(m4.r, "distance", lambda s, state, after_ns=None: calls.append(state)
                        or distance)  # fmt: skip
    assert m4.client_on_screen(object()) == (ok, distance)
    assert calls == ["client_title_active"]


def test_the_gate_sends_no_input_and_saves_no_screenshot(
    m4: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeScreen:
        closed = False

        def close(self) -> None:
            FakeScreen.closed = True

    def forbidden(*a: object, **k: object) -> None:
        raise AssertionError("the gate must not act or write a screenshot")

    monkeypatch.setattr(m4.r, "Screen", FakeScreen)
    monkeypatch.setattr(m4.r, "distance", lambda s, state, after_ns=None: 99.0)
    monkeypatch.setattr(m4.r, "to_png", forbidden)
    monkeypatch.setattr(m4.r, "Agent", forbidden)
    assert m4.check_client() == 1
    assert FakeScreen.closed


def test_far_blocks_take_pre_chosen_cells_spread_over_the_list(m4: ModuleType) -> None:
    cells = {"scenes": {"outdoor": {"top": [{"cell": [i, 100]} for i in range(16)],
                                    "centre": [], "bottom": []}}}  # fmt: skip
    used: dict[str, int] = {}
    assert m4.far_cell(cells, "outdoor-1", "outdoor", used) is None  # a near block
    assert m4.far_cell(None, "outdoor-top", "outdoor", used) is None  # no --cells
    picks = [m4.far_cell(cells, "outdoor-top", "outdoor", used) for _ in range(4)]
    assert picks == [[0, 100], [2, 100], [4, 100], [6, 100]]  # every len/8-th, nearest first
    with pytest.raises(SystemExit, match="no candidate"):
        m4.far_cell(cells, "outdoor-centre", "outdoor", used)


def test_a_spot_moves_the_scene_and_the_other_scenes_reset(m4: ModuleType) -> None:
    import bench

    saved = (dict(bench.SCENES), dict(bench.RESET_VIA))
    try:
        m4.apply_spot("indoor=104,122")
        assert bench.SCENES["indoor"] == ("prt_church", 104, 122)
        assert bench.RESET_VIA["outdoor"] == "prt_church 104 122"
        with pytest.raises(SystemExit):
            m4.apply_spot("nowhere=1,2")
    finally:
        bench.SCENES.clear()
        bench.SCENES.update(saved[0])
        bench.RESET_VIA.clear()
        bench.RESET_VIA.update(saved[1])
