"""scripts/route_preview.py: the LIVE route preview is anchored to WHAT THE SCREEN SHOWS (Batt
2026-10-08). The camera's world position comes from the scene's measured scroll; the line starts at
the feet measured on the frame (the HP/SP bar under them); at rest the camera snaps to the rule's
cell. Synthetic frames reproduce the measured client behaviour: the camera LAGS the character."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
J = np.array([[34.4, -35.7], [-25.2, -24.3]])  # px per cell, the indoor camera's at our cell
ANCHOR = np.array([640.75, 361.89])
H, W = 720, 1280


@pytest.fixture(scope="module")
def rp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("route_preview", SCRIPTS / "route_preview.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["route_preview"] = mod
    spec.loader.exec_module(mod)
    return mod


class Cam:  # a flat camera with the indoor camera's local Jacobian
    def project(self, cells: Any, alt: Any = None) -> np.ndarray:
        return ANCHOR + np.asarray(cells, dtype=float) @ J.T


@pytest.fixture(scope="module")
def world() -> np.ndarray:
    """A large smooth random texture (BGR), the floor the camera looks at."""
    rng = np.random.default_rng(7)
    base = rng.random((1100, 1700)).astype(np.float32)
    for _ in range(3):  # box-blur, separable
        base = (np.roll(base, 1, 0) + base + np.roll(base, -1, 0)) / 3
        base = (np.roll(base, 1, 1) + base + np.roll(base, -1, 1)) / 3
    g = (base - base.min()) / (base.max() - base.min())
    img = (np.stack([g * 120 + 40, g * 130 + 50, g * 140 + 60], -1)).astype(np.uint8)
    return img  # muted colours: never the bar's green or blue


def frame(world: np.ndarray, cam_px: np.ndarray, feet_px: np.ndarray | None,
          bar_offset: tuple[float, float]) -> np.ndarray:  # fmt: skip
    """The screen with the camera at world px offset cam_px (relative to the start), our bar under
    the feet at feet_px (screen px)."""
    ox, oy = int(round(200 + cam_px[0])), int(round(200 + cam_px[1]))
    img = world[oy : oy + H, ox : ox + W].copy()
    if feet_px is not None:
        bx, by = feet_px[0] + bar_offset[0], feet_px[1] + bar_offset[1]
        x0, y0 = int(round(bx - 30)), int(round(by - 4.5))
        img[y0 : y0 + 4, x0 : x0 + 60] = (60, 200, 40)  # the green HP row (BGR)
        img[y0 + 4 : y0 + 9, x0 : x0 + 60] = (220, 90, 40)  # the blue SP row
    return img


def test_the_scene_shift_is_measured_sub_pixel(rp: ModuleType, world: np.ndarray) -> None:
    a = frame(world, np.zeros(2), None, rp.BAR_OFFSET)
    b = frame(world, np.array([-7.0, 5.0]), None, rp.BAR_OFFSET)  # the camera moved up-left
    dx, dy = rp.scene_shift(a, b)
    assert dx == pytest.approx(7.0, abs=0.75) and dy == pytest.approx(-5.0, abs=0.75)


def test_the_feet_are_found_from_the_bar(rp: ModuleType, world: np.ndarray) -> None:
    img = frame(world, np.zeros(2), ANCHOR + np.array([31.0, -18.0]), rp.BAR_OFFSET)
    f = rp.find_feet(img, ANCHOR)
    assert f is not None and np.hypot(f[0] - ANCHOR[0] - 31, f[1] - ANCHOR[1] + 18) <= 1.0
    assert rp.find_feet(frame(world, np.zeros(2), None, rp.BAR_OFFSET), ANCHOR) is None


def walk(rp: ModuleType, world: np.ndarray, core: Any) -> list[dict[str, Any]]:
    """Stand on (100,100); walk 2 cells east, the camera LAGGING half a cell; stop; catch up."""
    t = 0
    out = []
    p, c = np.array([100.0, 100.0]), np.array([100.0, 100.0])
    traj = [(p.copy(), c.copy())] * 3
    for k in range(1, 9):  # the character moves 0.25 cell a frame, the camera trails
        pk = np.array([100.0 + 0.25 * k, 100.0])
        ck = np.array([max(100.0, pk[0] - 0.5), 100.0])
        traj.append((pk, ck))
    for k in range(1, 4):  # stopped: the camera catches up
        traj.append((np.array([102.0, 100.0]), np.array([min(102.0, 101.5 + 0.25 * k), 100.0])))
    traj += [(np.array([102.0, 100.0]), np.array([102.0, 100.0]))] * 14
    for k, (pk, ck) in enumerate(traj):
        cam_px = J @ (ck - np.array([100.0, 100.0]))
        feet = ANCHOR + J @ (pk - ck)
        if k == 10:
            core.snap((102, 100))  # the rule's belief after the step (applied at rest)
        msg = core.step(t, frame(world, cam_px, feet, rp.BAR_OFFSET))
        out.append(
            {"msg": msg, "c_true": ck, "feet": feet, "c": None if core.c is None else core.c.copy()}
        )
        t += 50_000_000
    return out


def px(pt: dict[str, Any]) -> np.ndarray:
    return np.array([pt["x"] * 1440 - 80, pt["y"] * 900 - 77])


def test_the_camera_follows_the_measured_scroll_and_the_line_starts_at_the_feet(
    rp: ModuleType, world: np.ndarray
) -> None:
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(106, 100)], (106, 100))
    frames = walk(rp, world, core)
    for f in frames[3:11]:  # walking: the camera LAGS the character
        assert np.abs(f["c"] - f["c_true"]).max() < 0.12  # the camera's cell, from the scroll
        start = px(f["msg"]["points"][0])
        assert f["msg"]["points"][0]["kind"] == "feet"
        assert np.hypot(*(start - f["feet"])) <= 1.5  # the line starts at the feet on THIS frame
    mid = frames[7]
    assert np.hypot(*(mid["feet"] - ANCHOR)) > 15  # the feet really were off the anchor mid-walk
    goal = next(px(p) for p in mid["msg"]["points"] if p["kind"] == "goal")
    true_goal = ANCHOR + J @ (np.array([106.0, 100.0]) - mid["c_true"])
    assert np.hypot(*(goal - true_goal)) <= 4.0  # the goal ring glued to the floor
    assert np.abs(frames[-1]["c"] - [102.0, 100.0]).max() < 0.02  # at rest: the rule's cell
    assert frames[-1]["msg"]["passed"] == [] or all(
        s["age_ms"] < 400 for s in frames[-1]["msg"]["passed"]
    )


def test_no_message_before_a_route_and_clear_sends_an_empty_live_preview(
    rp: ModuleType, world: np.ndarray
) -> None:
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    assert core.step(0, frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)) is None
    core.set_route((100, 100), [(104, 100)], (104, 100))
    assert core.step(1, frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)) is not None
    empty = rp.message(core.clear(), "t")
    assert empty["live"] is True and empty["points"] == []
    assert core.step(2, frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)) is None


def test_the_route_is_cut_where_it_leaves_the_view_and_ui_windows_travel_as_clip(
    rp: ModuleType, world: np.ndarray
) -> None:
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(140, 100)], (140, 100))  # 40 cells east: off screen
    m = core.step(0, frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET))
    assert m is not None
    assert not any(p["kind"] == "goal" for p in m["points"])  # an off-screen goal is not drawn
    assert len(m["clip"]) == len(rp.UI_WINDOWS)


def test_the_message_is_a_valid_display_only_route_preview(
    rp: ModuleType, world: np.ndarray
) -> None:
    from poring_env.protocol import RoutePreview

    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(104, 100)], (104, 100), click=(102, 100))
    frames = walk(rp, world, core)
    msg = RoutePreview.model_validate_json(json.dumps(rp.message(dict(frames[6]["msg"]), "t")))
    assert msg.live and msg.points[0].kind == "feet" and msg.passed and msg.clip
    assert msg.t_mono_ns == 6 * 50_000_000  # stamped with the FRAME's capture time


def test_a_step_belief_waits_for_its_move_but_a_where_fix_applies_at_rest(
    rp: ModuleType, world: np.ndarray
) -> None:
    """2026-10-08: the rule's belief arrived before the move started, and an immediate snap put the
    camera a whole step ahead."""
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(104, 100)], (104, 100))
    still = frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)
    core.snap((102, 100))  # said at click time: the character has not moved yet
    for k in range(6):
        core.step(k * 50_000_000, still)
    assert np.allclose(core.c, [100.0, 100.0])  # still standing: the belief waits
    core.snap_fix((101, 100))  # a /where fix says where we stand now
    for k in range(6, 30):
        core.step(k * 50_000_000, still)
    assert np.abs(core.c - [101.0, 100.0]).max() < 0.02


def test_a_correction_at_a_stop_eases_in_over_200_ms_never_a_jump(
    rp: ModuleType, world: np.ndarray
) -> None:
    """Batt 2026-10-08: any residual correction at a stop eases in (EASE_S), instead of snapping."""
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(104, 100)], (104, 100))
    still = frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)
    t, goals = 0, []
    for _ in range(4):
        core.step(t, still)
        t += 50_000_000
    core.snap_fix((101, 100))  # the camera was a cell off: the fix says so
    for _ in range(30):
        m = core.step(t, still)
        goals.append(px(next(p for p in m["points"] if p["kind"] == "goal")))
        t += 50_000_000
    old, new = ANCHOR + J @ np.array([4.0, 0.0]), ANCHOR + J @ np.array([3.0, 0.0])
    steps = np.linalg.norm(np.diff(np.array(goals), axis=0), axis=1)
    assert steps.max() <= 0.3 * np.linalg.norm(new - old)  # no single-frame jump
    assert np.hypot(*(goals[-1] - new)) <= 1.0  # it arrives at the corrected place
    assert any(np.hypot(*(g - old)) > 2 and np.hypot(*(g - new)) > 2 for g in goals)  # in between


def test_an_engine_walk_waits_for_motion_after_the_click_and_a_dead_click_stands_down(
    rp: ModuleType, world: np.ndarray
) -> None:
    """2026-10-08 13:45: armed before the rule's hover, a noise frame passed for the onset and
    the engine pulled the camera a whole step ahead. Now: onset only after the click, two clear
    frames running; nothing moving for 2.5 s = a dead click."""
    core = rp.PreviewCore(Cam(), None, (80, 77, W, H), (1440, 900), "t")
    core.set_route((100, 100), [(104, 100)], (104, 100))
    still = frame(world, np.zeros(2), ANCHOR, rp.BAR_OFFSET)
    t = 0
    for _ in range(4):
        core.step(t, still)
        t += 50_000_000
    core.walk((100, 100), [(101, 100), (102, 100)], 150.0, t)
    for _ in range(70):  # 3.5 s and the character never moves
        core.step(t, still)
        t += 50_000_000
    assert core.engine is None  # stood down
    assert np.abs(core.c - [100.0, 100.0]).max() < 0.02  # and never pulled the camera
