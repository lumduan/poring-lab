"""scripts/rule_run.py walk@3 (docs/demonstrations.md 3.5): the two-motion hover, the systematic
stop, and the hover constants mirrored in the L2 binding (drift)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from poring_skills.resolve import load_l2

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture(scope="module")
def rr() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("rule_run", SCRIPTS / "rule_run.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rule_run"] = module
    spec.loader.exec_module(module)
    return module


class FakeAgent:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))


class FakeScreen:
    def __init__(self) -> None:
        self.grabs: list[tuple[int, int, int, int]] = []

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        self.grabs.append((x, y, w, h))
        return 0, np.zeros((h, w, 4), np.uint8)


def test_the_hover_is_two_motion_events_ending_on_the_cell(
    rr: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One jump drew the marker 0/18 times, a second move 18/18 (probe 2026-10-07)."""
    monkeypatch.setattr(rr.time, "sleep", lambda s: None)
    agent, screen = FakeAgent(), FakeScreen()
    assert rr.hover_marker(agent, screen, 500, 400) == 0
    assert agent.moves == [(497, 397), (500, 400)]
    assert len(screen.grabs) == 1 and screen.grabs[0][:2] == (500 - 45, 400 - 45)


def test_systematic_decline_needs_k_identical_declines_in_a_row(rr: ModuleType) -> None:
    k = rr.SYSTEMATIC_K
    assert rr.systematic_decline(["no_marker"] * (k - 1)) is None
    assert rr.systematic_decline(["no_marker"] * k) == "no_marker"
    assert rr.systematic_decline([None] * k) is None
    assert rr.systematic_decline(["no_marker"] * (k - 1) + [None]) is None
    assert rr.systematic_decline(["no_selfpos"] + ["no_marker"] * (k - 1)) is None
    assert rr.systematic_decline([None] + ["no_marker"] * k) == "no_marker"


def test_the_hover_constants_match_the_l2_binding(rr: ModuleType) -> None:
    import empty_cell as ec

    cue = load_l2("kro-20211103-prere")["cue"]["walk_marker"]
    hover = cue["hover"]
    assert hover["approach_px"] == rr.HOVER_APPROACH_PX
    assert hover["approach_s"] == rr.HOVER_APPROACH_S
    assert hover["settle_s"] == rr.HOVER_S
    assert cue["rdp"]["min_marker_px"] == ec.MIN_MARKER_PX_V2
    assert cue["rdp"]["crop_px"] == ec.CROP[2] == ec.CROP[3]
    assert "s2" not in cue  # not calibrated on the console path: resolution fails closed


def test_open_window_order_is_seeded_and_balanced(rr: ModuleType) -> None:
    order = rr.window_order(50, 20261010)
    assert order == rr.window_order(50, 20261010) and order != rr.window_order(50, 1)
    counts = {w: order.count(w) for w in rr.WINDOWS4}
    assert sorted(counts.values()) == [12, 12, 13, 13]


def test_open_window_chords_come_from_l2_and_a_refusal_is_a_decline(rr: ModuleType) -> None:
    assert rr.window_keys("status") == ["AltLeft", "KeyA"]
    assert rr.window_keys("equipment") == ["AltLeft", "KeyQ"]

    class Refusing:
        def chord(self, *codes: str) -> None:
            raise rr.r.Stop("bot keys refused: client_not_foreground")

    class Pressing:
        def __init__(self) -> None:
            self.chords: list[tuple[str, ...]] = []

        def chord(self, *codes: str) -> None:
            self.chords.append(codes)

    did = rr.window_rule(Refusing(), ["AltLeft", "KeyA"])
    assert did["rule_decline"].startswith("refused: bot keys refused")
    agent = Pressing()
    assert rr.window_rule(agent, ["AltLeft", "KeyS"]) == {}
    assert agent.chords == [("AltLeft", "KeyS")]


def test_a_rerun_replays_the_interrupted_attempts_situations(
    rr: ModuleType, tmp_path: Path
) -> None:
    from poring_env.demo import Action, DemoLog, DemoRecord, Intended

    sid = "20261007T131457-demo-walk-alone-outdoor"
    log = DemoLog(sid, root=tmp_path)
    for i in range(4):
        log.append(
            DemoRecord(
                session=sid,
                actor="rule:harness@1",
                t_mono_ns=i * 10 + 1,
                cue="h",
                action=Action(type="gm", intended=Intended(kind="other")),
            )
        )
        log.append(
            DemoRecord(
                session=sid,
                actor="rule:walk@3",
                t_mono_ns=i * 10 + 2,
                cue="w",
                scene="outdoor:prt_fild08",
                action=Action(
                    type="walk",
                    intended=Intended(
                        kind="cell",
                        cell=(i, -i),
                        relative=True,
                        note=f"harness spot {260 + i},{100 + i}",
                    ),
                ),
            )
        )
    picked = rr.rerun_records(log.dir, [1, 3], "outdoor")
    assert [p.action.intended.cell for p in picked] == [(1, -1), (3, -3)]
    assert [rr.harness_spot(p) for p in picked] == [(261, 101), (263, 103)]
    with pytest.raises(SystemExit, match="does not match"):
        rr.rerun_records(log.dir, [1], "indoor")


# --- walk@4 (demonstrations 3.7): dead reckoning + altitude, the marker CONFIRMS or CORRECTS ----
class LinearCamera:
    """u = 640 + 30 x, v = 360 + 20 y (altitude ignored): enough to test the control flow."""

    def project(self, cells: np.ndarray, alt: object = None) -> np.ndarray:
        cells = np.asarray(cells, dtype=float)
        return np.stack([640 + 30 * cells[:, 0], 360 + 20 * cells[:, 1]], axis=1)


class FlatGrid:
    def relative_altitude(self, origin: object, cells: np.ndarray) -> np.ndarray:
        return np.zeros(len(cells))


class MarkerScreen:
    """Draws a 9x9 green_v2 marker centred on the next programmed centroid (client px), or none."""

    def __init__(self, rr: ModuleType, centroids: list[tuple[float, float] | None]) -> None:
        self.rr, self.centroids, self.grabs = rr, list(centroids), 0

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        self.grabs += 1
        img = np.zeros((h, w, 4), np.uint8)
        c = self.centroids.pop(0) if self.centroids else None
        if c is not None:
            gx, gy, _, _ = self.rr.r.game_region()
            cx, cy = round(c[0] + gx - x), round(c[1] + gy - y)
            img[cy - 4 : cy + 5, cx - 4 : cx + 5, :3] = (110, 200, 110)  # BGR, green_v2
        return 0, img


class ClickAgent:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[tuple[int, int]] = []

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


@pytest.fixture
def w4(rr: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setattr(rr.time, "sleep", lambda s: None)
    monkeypatch.setattr(rr.r, "game_region", lambda: (80, 77, 1280, 720))
    monkeypatch.setattr(rr, "MIN_MARKER_PX", 60)
    return rr


def expected(rr: ModuleType, rel: tuple[int, int], k: tuple[int, int]) -> tuple[float, float]:
    cells = np.array([(rel[0] + dx, rel[1] + dy) for dx, dy in rr.NB9], dtype=float)
    e = rr.expected_centroids(LinearCamera().project(cells), np.zeros(9), "indoor")
    return float(e[rr.NB9.index(k)][0]), float(e[rr.NB9.index(k)][1])


def test_walk4_clicks_when_the_marker_confirms_the_target(w4: ModuleType) -> None:
    rel = (3, -2)
    screen = MarkerScreen(w4, [expected(w4, rel, (0, 0))])
    agent = ClickAgent()
    did = w4.walk4_rule(agent, screen, LinearCamera(), FlatGrid(), (100, 100), (103, 98), "indoor")
    assert "decline" not in did and len(agent.clicks) == 1
    assert agent.clicks[0] == (80 + 640 + 90, 77 + 360 - 40)  # the target's projected centre


def test_walk4_corrects_once_when_the_marker_shows_a_neighbour(w4: ModuleType) -> None:
    rel = (3, -2)
    screen = MarkerScreen(w4, [expected(w4, rel, (1, 0)), expected(w4, rel, (0, 0))])
    agent = ClickAgent()
    did = w4.walk4_rule(agent, screen, LinearCamera(), FlatGrid(), (100, 100), (103, 98), "indoor")
    assert [h["cell"] for h in did["hovers"]] == [(1, 0), (0, 0)]
    assert agent.clicks == [(80 + 640 + 90 - 30, 77 + 360 - 40)]  # moved by P_T - P_(1,0)


def test_walk4_tries_in_cell_alternates_then_declines(w4: ModuleType) -> None:
    rel = (3, -2)
    screen = MarkerScreen(w4, [None, None, expected(w4, rel, (0, 0))])
    agent = ClickAgent()
    did = w4.walk4_rule(agent, screen, LinearCamera(), FlatGrid(), (100, 100), (103, 98), "indoor")
    assert len(did["hovers"]) == 3 and len(agent.clicks) == 1
    assert agent.clicks[0] == (80 + 640 + 90 - 9, 77 + 360 - 40)  # 3rd hover: -0.3 cell along x
    none = MarkerScreen(w4, [None] * 9)
    agent2 = ClickAgent()
    did2 = w4.walk4_rule(agent2, none, LinearCamera(), FlatGrid(), (100, 100), (103, 98), "indoor")
    assert did2["decline"] == "no_confirmation" and len(did2["hovers"]) == w4.MAX_HOVERS
    assert agent2.clicks == []


def test_walk4_bias_matches_the_l2_binding(rr: ModuleType) -> None:
    cue = load_l2("kro-20211103-prere")["cue"]["walk_marker"]["rdp"]["centroid_bias"]
    for mode, (b0, beta) in rr.CENTROID_BIAS.items():
        assert (tuple(cue[mode]["b0"]), tuple(cue[mode]["beta_per_alt"])) == (b0, beta)
