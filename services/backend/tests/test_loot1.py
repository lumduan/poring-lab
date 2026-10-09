"""scripts/loot1.py (loot@1, demonstrations 3.20 / 3.20a): the pure parts -- the spots, the target
track and its death rule, the UI exclusion and the runtime check's combination."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[2].parent / "scripts"
S = 1_000_000_000


@pytest.fixture(scope="module")
def loot1() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("loot1", SCRIPTS / "loot1.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loot1"] = mod
    spec.loader.exec_module(mod)
    return mod


def box(u: float, v: float, score: float = 0.9) -> Any:
    return SimpleNamespace(x0=u - 15, y0=v - 30, x1=u + 15, y1=v, score=score, cls="monster")


def test_spots_are_open_apart_seeded_and_fresh(loot1: Any) -> None:
    walk = np.ones((200, 300), dtype=bool)
    walk[100:110, 260:270] = False  # an obstacle in the region
    a = loot1.spots(walk, 7, 30)
    assert a == loot1.spots(walk, 7, 30) and a != loot1.spots(walk, 8, 30)
    assert len(a) == 30 and len(set(a)) == 30
    for i, p in enumerate(a):
        x0, y0, x1, y1 = loot1.REGION
        assert x0 <= p[0] <= x1 and y0 <= p[1] <= y1
        c = loot1.CLEAR
        assert walk[p[1] - c : p[1] + c + 1, p[0] - c : p[0] + c + 1].all()
        for q in a[:i]:
            assert max(abs(p[0] - q[0]), abs(p[1] - q[1])) >= loot1.APART
    assert len(loot1.spots(walk, 7, 10_000)) < 10_000  # fewer when the region cannot hold n


def test_the_track_follows_the_nearest_box_and_misses_far_ones(loot1: Any) -> None:
    t = loot1.Track((640.0, 400.0))
    t.update(1 * S, [box(650, 405), box(900, 400)])
    assert t.foot == (650.0, 405.0)
    t.update(2 * S, [box(900, 400)])  # only a far box: not the target
    assert t.sightings[-1].box is None and t.last_seen_ns == 1 * S


def test_death_needs_a_sighting_after_the_attack_then_frames_and_time_unseen(loot1: Any) -> None:
    t = loot1.Track((640.0, 400.0))
    t.update(10 * S, [box(640, 400)])
    attack = 11 * S
    for k in range(5):  # the detector lost it right after the click: never "dead"
        t.update(attack + k * S // 5, [])
    assert not t.gone(attack + 2 * S, attack)
    t.update(13 * S, [box(642, 401)])  # seen fighting after the click
    t.update(13 * S + S // 5, [])
    t.update(13 * S + 2 * S // 5, [])
    assert not t.gone(13 * S + S // 2, attack)  # 2 frames
    t.update(13 * S + 3 * S // 5, [])
    assert not t.gone(13 * S + 3 * S // 5, attack)  # 3 frames but 0.6 s
    assert t.gone(14 * S + S // 10, attack)  # 3 frames and >= GONE_S
    assert not t.gone(14 * S + S // 10, None)  # no attack, no death


def test_ui_windows_are_never_clicked(loot1: Any) -> None:
    x0, y0, x1, y1 = loot1.ui_mask.route_preview.UI_WINDOWS[0]
    assert loot1.in_ui((x0 + x1) / 2, (y0 + y1) / 2)
    assert loot1.in_ui(x1 + loot1.UI_PAD - 1, y0 + 1)
    assert not loot1.in_ui(640, 384)


def test_in_ui_without_a_mask_is_the_old_static_rule(loot1: Any) -> None:
    """2026-10-09: in_ui delegates to ui_mask; with no mask it is the old formula, point for point
    (every window edge +- 2 px, and a grid over the client)."""
    windows = loot1.ui_mask.route_preview.UI_WINDOWS

    def old(u: float, v: float, pad: float = loot1.UI_PAD) -> bool:
        return any(x0 - pad <= u <= x1 + pad and y0 - pad <= v <= y1 + pad
                   for x0, y0, x1, y1 in windows)  # fmt: skip

    pts = [(float(u), float(v)) for u in range(-20, 1300, 7) for v in range(-20, 740, 7)]
    for x0, y0, x1, y1 in windows:
        for e in (-2.0, -1.0, 0.0, 1.0, 2.0):
            for pad in (0.0, loot1.UI_PAD):
                pts += [(x0 - pad + e, (y0 + y1) / 2), (x1 + pad + e, (y0 + y1) / 2),
                        ((x0 + x1) / 2, y0 - pad + e), ((x0 + x1) / 2, y1 + pad + e)]  # fmt: skip
    for u, v in pts:
        assert loot1.in_ui(u, v) == old(u, v), (u, v)
        assert loot1.in_ui(u, v, 0.0) == old(u, v, 0.0), (u, v)


def test_in_ui_with_a_dialog_mask_refuses_the_cutin(loot1: Any) -> None:
    """The patch point: a mask read with an open dialog makes the cut-in region UI; a certain
    "no dialog" leaves it a click point (the guide's phantom box centre, 2026-10-09)."""
    um = loot1.ui_mask
    u, v = 1008.0, 621.0
    open_ = um.UiMask(cutin=True, why="dialog_open")
    assert not loot1.in_ui(u, v)
    assert loot1.in_ui(u, v, mask=open_)
    assert not loot1.in_ui(u, v, mask=um.UiMask(cutin=False, why="no_dialog"))
    x0 = um.CUTIN_BOTTOM_RIGHT[0]
    assert loot1.in_ui(x0 - loot1.UI_PAD, 400, mask=open_)  # the grown edge counts
    assert not loot1.in_ui(x0 - loot1.UI_PAD - 1, 400, mask=open_)


def test_either_runtime_signal_is_enough(loot1: Any) -> None:
    f = loot1.runtime_obtained
    assert f((737, 2030), (738, 2030), False) == {"obtained": True, "weight_rose": True,
                                                  "cue": False}  # fmt: skip
    assert f((737, 2030), (737, 2030), True)["obtained"]  # sub-resolution: the cue alone
    assert not f((737, 2030), (737, 2030), False)["obtained"]
    assert not f(None, (738, 2030), False)["obtained"]  # no baseline: weight cannot count
    assert not f((737, 2030), (736, 2030), False)["obtained"]


def test_the_gm_cell_comes_from_two_equal_minimap_reads(
    loot1: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3.20a amendment (Batt 2026-10-09): no /where in loot@1; the minimap readout, passive."""
    from poring_env import selfpos

    walk = np.ones((200, 300), dtype=bool)
    frame = np.zeros((4, 4, 4), np.uint8)
    rig = SimpleNamespace(screen=SimpleNamespace(grab=lambda *a: (0, frame)), walkable=walk,
                          digits=None)  # fmt: skip
    monkeypatch.setattr(loot1.time, "sleep", lambda s: None)
    monkeypatch.setattr(loot1.r, "game_region", lambda: (0, 0, 4, 4))
    for reads, want in (([(270, 104), (270, 104)], "ok"), ([(270, 104), (271, 104)], "disagree"),
                        ([None, None], "unread"), ([(290, 104)] * 2, "implausible")):  # fmt: skip
        it = iter(reads)
        monkeypatch.setattr(selfpos, "read_minimap",
                            lambda img, t, it=it: SimpleNamespace(xy=next(it)))  # fmt: skip
        got = loot1.minimap_cell(rig, (271, 103))
        assert got["why"] == want and (got["xy"] is not None) == (want == "ok"), got


def test_the_gate_grows_with_the_time_unseen_and_is_capped(loot1: Any) -> None:
    """Pilot 2026-10-09: the spawned Poring wanders; a fixed 45 px gate lost it after one step."""
    t = loot1.Track((640.0, 400.0))
    t.update(1 * S, [box(640, 400)])
    t.update(1 * S + S // 5, [box(700, 400)])  # 60 px in 0.2 s: farther than a Poring walks
    assert t.foot == (640.0, 400.0)
    t.update(2 * S, [box(740, 400)])  # 100 px, 1 s after the last sighting: followed
    assert t.foot == (740.0, 400.0)
    t.update(30 * S, [box(740 + loot1.TRACK_MAX_PX + 5, 400)])  # never wider than the cap
    assert t.foot == (740.0, 400.0)


def test_a_probe_needs_a_fresh_and_still_box(loot1: Any) -> None:
    t = loot1.Track((640.0, 400.0))
    t.update(1 * S, [box(640, 400)])
    assert t.still(1 * S) is None  # one sighting cannot show it stands
    t.update(1 * S + S // 2, [box(642, 401)])
    got = t.still(1 * S + S // 2 + S // 10)
    assert got is not None and got["moved_px"] < loot1.STILL_PX
    assert t.still(1 * S + S // 2 + S) is None  # 1 s old: stale
    t.update(2 * S, [box(660, 401)])  # it walks
    assert t.still(2 * S) is None
    t.update(2 * S + S // 2, [])
    t.update(3 * S, [box(661, 401)])  # stands again, but the sighting before is 1.0 s old: ok
    assert t.still(3 * S) is not None
    t.update(5 * S, [box(661, 401)])  # 2 s between the two sightings: not proof of standing
    assert t.still(5 * S) is None


def test_the_spawn_is_looked_for_on_every_frame(loot1: Any) -> None:
    feet = (640.0, 400.0)
    near, far = box(660, 410), box(640 + loot1.SPAWN_PX + 30, 400)
    frames = [(1 * S, []), (2 * S, [far, near]), (3 * S, [])]
    assert loot1.find_spawn(frames, feet) == (1, near)  # the pilot judged only the last frame
    assert loot1.find_spawn([(1 * S, [far])], feet) is None
    assert loot1.find_spawn([], feet) is None


def test_the_spawn_line_is_never_varied(loot1: Any) -> None:
    """Batt's typing policy (2026-10-09): no line is altered to dodge the repeat counter."""
    src = (SCRIPTS / "loot1.py").read_text()
    assert 'f"@monster {PORING} 1"' in src and "'0' *" not in src


def test_the_hud_is_display_only_and_never_raises(loot1: Any) -> None:
    """Batt 2026-10-09 ~19:30: loot@1 tells the operator HUD what it does; display only."""

    class Hud:
        def __init__(self) -> None:
            self.lines: list[str] = []
            self.boxes: list[list[Any]] = []

        def note(self, line: str) -> None:
            self.lines.append(line)

        def send(self, boxes: list[Any], force: bool) -> bool:
            self.boxes.append(boxes)
            raise RuntimeError("a HUD failure must never reach the trial")

    rig = SimpleNamespace(hud=Hud())
    loot1.hud(rig, "trial 0: target found", [box(640, 400), None])
    assert rig.hud.lines == ["trial 0: target found"] and len(rig.hud.boxes[0]) == 1
    loot1.hud(SimpleNamespace(hud=None), "nothing to send")  # no HUD: no-op
    hit = {"tried": [[1.0, 2.0, "unknown", None], [1.0, 3.0, "sword", "sword"]]}
    assert loot1._reads(hit) == "unknown sword/sword"
