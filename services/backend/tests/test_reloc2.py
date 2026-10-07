"""scripts/reloc2.py (re-localisation v2, demonstrations 3.12): altitude as evidence, not an
obstacle. A fake terrain with raised pews and a fake probe that shows what the client draws from
the TRUE cell (the same geometry the rule predicts with: this tests the elimination, the live
alone-test relocalise@2 tests the geometry)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def r2() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "reloc2"):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules["reloc2"]


class Cam:
    """The indoor RDP camera, linearised (camera_rdp.json, prt_church, 2026-10-07): one cell along
    x = (+34.4, -25.2) px, along y = (-35.8, -24.3) px, one GAT altitude unit = 7.2 px up."""

    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        c = np.asarray(cells, dtype=float).reshape(-1, 2)
        a = np.zeros(len(c)) if alt is None else np.asarray(alt, dtype=float)
        return np.stack([640.8 + 34.4 * c[:, 0] - 35.8 * c[:, 1],
                         361.9 - 25.2 * c[:, 0] - 24.3 * c[:, 1] - 7.2 * a], axis=1)  # fmt: skip


class Gat:
    def __init__(self, walk: np.ndarray, alt: np.ndarray) -> None:
        self.w, self.altitude = walk, alt

    def walkable(self) -> np.ndarray:
        return self.w

    def relative_altitude(self, origin: Any, rel: Any) -> np.ndarray:
        rel = np.asarray(rel, dtype=float).reshape(-1, 2)
        out = []
        for dx, dy in rel:
            x, y = int(origin[0] + dx), int(origin[1] + dy)
            inside = 0 <= y < self.altitude.shape[0] and 0 <= x < self.altitude.shape[1]
            out.append(self.altitude[y, x] - self.altitude[origin[1], origin[0]] if inside else 0.0)
        return np.asarray(out)


def pews(n: int = 40) -> tuple[np.ndarray, np.ndarray]:
    """A nave: two blocks of short raised pews (walkable, +5) with an aisle, side walls. The pew
    rows are IRREGULAR: with a strict period the probes see the same thing from cells one period
    apart, and v2 rightly refuses to choose (a true alias, never a guess)."""
    walk = np.ones((n, n), dtype=bool)
    alt = np.zeros((n, n))
    for y in (6, 9, 13, 16, 20, 22, 26, 29):
        alt[y, 9:15] = 5.0
        alt[y, 18:24] = 5.0
    walk[:, 6] = False
    walk[:, 27] = False
    return walk, alt


def run(r2: ModuleType, monkeypatch: pytest.MonkeyPatch, walk: np.ndarray, alt: np.ndarray,
        true: tuple[int, int], belief: tuple[int, int]) -> dict[str, Any]:  # fmt: skip
    w = r2.w5.World(Cam(), Gat(walk, alt), true)
    truth = r2.w5.World(Cam(), Gat(walk, alt), true)

    def probe(agent: Any, screen: Any, u: float, v: float, mask: Any) -> dict[str, Any]:
        best = None  # what the client draws from the TRUE cell under pixel (u, v)
        for o in r2.OFFSETS + [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]:
            pu, pv = truth.camera.project(np.array([o], dtype=float), None)[0]
            d = abs(pu - u) + abs(pv - v)
            if best is None or d < best[0]:
                best = (d, o)
        assert best is not None
        kind, what = r2.predict(truth, true, best[1], (u, v))
        if kind == "blocked":
            return {"comps": [], "marker_px": 0, "noentry": 1.0}
        return {"comps": [tuple(p) for p in what[1] + 1.5], "marker_px": 120, "noentry": 0.0}

    monkeypatch.setattr(r2.w5, "probe", probe)
    w.position = belief
    return r2.relocalise(None, None, w, None, (100, 60, 1180, 680))  # type: ignore[arg-type]


def test_among_the_pews_v1_cannot_probe_and_v2_finds_the_truth(
    r2: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    walk, alt = pews()
    true, belief = (15, 13), (17, 14)
    cands = [(belief[0] + dx, belief[1] + dy) for dy in range(-2, 3) for dx in range(-2, 3)]
    offsets = [(dx, dy) for dy in range(-5, 6) for dx in range(-6, 7) if max(abs(dx), abs(dy)) >= 2]
    assert r2.w5.best_probe(cands, walk, alt, offsets) is None  # v1: no flat split -> 0 probes
    got = run(r2, monkeypatch, walk, alt, true, belief)
    assert got["ok"] and got["to"] == list(true), got
    assert 1 <= len(got["probes"]) <= r2.PROBES


def test_a_featureless_floor_fails_without_a_guess(
    r2: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    walk, alt = np.ones((40, 40), dtype=bool), np.zeros((40, 40))
    got = run(r2, monkeypatch, walk, alt, (20, 20), (21, 20))
    assert not got["ok"] and got["left"] > 1, got  # every candidate looks the same: no decision


def test_a_truth_three_cells_off_is_in_the_set_from_the_start(
    r2: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a +-2 set this truth was OUTSIDE it, and elimination left one WRONG survivor (18, 13)
    instead of nobody: widening only on "nobody fits" was unsafe."""
    walk, alt = pews()
    got = run(r2, monkeypatch, walk, alt, (14, 13), (17, 13))
    assert got["ok"] and got["to"] == [14, 13], got


def test_a_periodic_layout_is_a_true_alias_and_v2_declines(
    r2: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pews every 3 rows: (15, 13) and (15, 16) look the same from every probe in reach."""
    walk, alt = np.ones((40, 40), dtype=bool), np.zeros((40, 40))
    for y in range(6, 34, 3):
        alt[y, 8:30] = 5.0
    got = run(r2, monkeypatch, walk, alt, (15, 13), (17, 14))
    assert not got["ok"] and got["left"] >= 2, got
