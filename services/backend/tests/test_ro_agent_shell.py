"""scripts/ro_agent.py: the agent's own terminal (Batt, 2026-10-03) -- found only by its exact
"poring-lab shell" tab, and used only after a pixel-verified NON-elevated check. No Windows here."""

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def ro() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ro_agent", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def screen_with(colour: tuple[int, int, int] | None, run: int, y: int = 300) -> np.ndarray:
    bgra = np.full((900, 1440, 4), 12, np.uint8)
    if colour is not None:
        bgra[y : y + 18, 100 : 100 + run, :3] = colour[::-1]  # RGB -> BGR
    return bgra


def test_marker_colour(ro: ModuleType) -> None:
    assert ro.marker_colour(screen_with(ro.MARKER_GREEN, 360)) == "green"
    assert ro.marker_colour(screen_with(ro.MARKER_RED, 360)) == "red"
    assert ro.marker_colour(screen_with(ro.MARKER_GREEN, 40)) is None  # a word, not the marker
    assert ro.marker_colour(screen_with(None, 0)) is None
    both = screen_with(ro.MARKER_RED, 360, y=200)
    both[500:518, 100:460, :3] = ro.MARKER_GREEN[::-1]
    assert ro.marker_colour(both) == "green"  # the newest (bottom-most) line wins


def test_the_elevation_check_is_red_for_an_administrator(ro: ModuleType) -> None:
    check = ro.ELEVATION_CHECK
    assert "IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)" in check
    assert check.index("DarkRed") < check.index("else") < check.index("DarkGreen")


def test_the_agents_shell_is_preferred_over_any_powershell_tab(ro: ModuleType) -> None:
    assert ro.CONSOLE_TEMPLATES[False][0] == ro.SHELL_TEMPLATE
    assert ro.SHELL_TEMPLATE not in ro.CONSOLE_TEMPLATES[True]  # never an elevated console's
