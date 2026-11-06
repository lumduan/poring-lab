"""The teaching kit's simple_bot.py (teaching/simple-bot/): its PURE parts only.

The script is a stand-alone PEP 723 file for students' Windows PCs; it is loaded here by path. Only
numpy and the standard library are needed: cv2, onnxruntime, mss and the win32 modules are lazy
imports, and nothing here captures the screen or sends input.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
KIT = ROOT / "teaching" / "simple-bot"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"teaching_{name}", KIT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


sb = _load("simple_bot")
kit = _load("make_kit")
Box = sb.Box
CHAR = (sb.CHAR_X, sb.CHAR_Y)


def mon(cx: float, foot_y: float, w: float = 40, h: float = 40, score: float = 0.9) -> object:
    """A monster box of size w x h whose feet stand at (cx, foot_y)."""
    return Box(cx - w / 2, foot_y - h, cx + w / 2, foot_y, score, "monster")


# ---- the safety gate: local server only --------------------------------------------------------


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "127.8.9.1", "::1", "10.1.2.3", "172.16.0.5", "172.31.255.1",
           "192.168.1.13", "::ffff:127.0.0.1", "::ffff:192.168.0.2", "fe80::1%eth0"],
)  # fmt: skip
def test_loopback_and_private_addresses_are_local(ip: str) -> None:
    assert sb.remote_is_local(ip)
    assert sb.check_connections([ip])[0]


@pytest.mark.parametrize("ip", ["8.8.8.8", "172.32.0.1", "203.104.1.1", "2001:4860::8888",
                                "::ffff:8.8.8.8", "not-an-ip", ""])  # fmt: skip
def test_public_or_bad_addresses_are_not_local(ip: str) -> None:
    assert not sb.remote_is_local(ip)


def test_one_public_connection_fails_the_whole_check_and_is_named() -> None:
    ok, why = sb.check_connections(["127.0.0.1", "192.168.1.13", "203.104.1.1"])
    assert not ok and "203.104.1.1" in why and "PUBLIC" in why


def test_no_connection_fails() -> None:
    ok, why = sb.check_connections([])
    assert not ok and "no ESTABLISHED connection" in why


def test_all_local_passes() -> None:
    ok, why = sb.check_connections(["127.0.0.1", "127.0.0.1", "192.168.1.13"])
    assert ok and why == "3 connection(s), all local"


def test_the_fail_safe_corner_is_the_primary_screens_top_left_only() -> None:
    assert sb.in_corner(0, 0) and sb.in_corner(2, 2)
    assert not sb.in_corner(3, 0) and not sb.in_corner(500, 1)
    assert not sb.in_corner(-1200, 0)  # a monitor left of the primary one is not the corner


# ---- --act / --watch refuse off Windows, before any heavy import ---------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="the refusal path is the non-Windows one")
@pytest.mark.parametrize("mode", ["--act", "--watch"])
def test_live_modes_refuse_off_windows(mode: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert sb.main([mode, "--model", "v1.onnx"]) == 2
    err = capsys.readouterr().err
    assert f"{mode} refused" in err and "only on Windows" in err and "--replay" in err


def test_no_mode_means_watch_and_is_refused_off_windows(capsys: pytest.CaptureFixture[str]) -> None:
    if sys.platform == "win32":
        pytest.skip("the refusal path is the non-Windows one")
    assert sb.main([]) == 2
    assert "--watch refused" in capsys.readouterr().err


def test_live_refusal_is_empty_on_windows() -> None:
    assert sb.live_refusal("act", "win32") == ""
    assert "linux" in sb.live_refusal("act", "linux")


def test_the_heavy_libraries_stay_unimported() -> None:
    for name in ("cv2", "onnxruntime", "mss", "win32gui", "win32api", "psutil"):
        assert not hasattr(sb, name), name


# ---- detect: letterbox, unletterbox, NMS, decode ----------------------------------------------


def test_a_1280x720_frame_is_padded_8_rows_top_and_bottom_not_scaled() -> None:
    img = np.zeros((720, 1280, 3), np.uint8)
    img[..., 2] = 255  # pure red in BGR
    x, s, left, top = sb.letterbox(img, (736, 1280))
    assert x.shape == (1, 3, 736, 1280) and x.dtype == np.float32
    assert (s, left, top) == (1.0, 0, 8)
    assert np.allclose(x[0, :, :8], 114 / 255) and np.allclose(x[0, :, -8:], 114 / 255)
    assert np.allclose(x[0, 0, 8:-8], 1.0) and np.allclose(x[0, 2, 8:-8], 0.0)  # RGB order


def test_a_small_frame_is_scaled_up_then_boxes_map_back() -> None:
    img = np.full((360, 640, 3), 50, np.uint8)
    x, s, left, top = sb.letterbox(img, (736, 1280))
    assert (s, left, top) == (2.0, 0, 8)
    model_px = np.array([[100.0, 108.0, 300.0, 208.0]])
    assert np.allclose(sb.unletterbox(model_px, s, left, top), [[50, 50, 150, 100]])


def test_unletterbox_undoes_side_padding() -> None:
    # a tall picture leaves free space LEFT and RIGHT: the x padding is removed, then the scale
    img = np.zeros((736, 640, 3), np.uint8)
    _, s, left, top = sb.letterbox(img, (736, 1280))
    assert (s, left, top) == (1.0, 320, 0)
    assert np.allclose(sb.unletterbox(np.array([[330.0, 10, 340, 20]]), s, left, top),
                       [[10, 10, 20, 20]])  # fmt: skip


def test_nms_keeps_the_best_of_overlapping_boxes_and_separate_ones() -> None:
    boxes = np.array([[0, 0, 100, 100], [5, 5, 105, 105], [200, 200, 260, 260], [2, 0, 100, 98]])
    scores = np.array([0.6, 0.9, 0.5, 0.7])
    assert sb.nms(boxes, scores, 0.5) == [1, 2]
    assert sb.nms(boxes[:1], scores[:1], 0.5) == [0]
    assert sb.nms(np.zeros((0, 4)), np.zeros(0), 0.5) == []


def test_nms_keeps_overlaps_below_the_threshold() -> None:
    boxes = np.array([[0, 0, 100, 100], [60, 0, 160, 100]])  # IoU 40 / 160 = 0.25
    assert sorted(sb.nms(boxes, np.array([0.8, 0.7]), 0.5)) == [0, 1]
    assert sb.nms(boxes, np.array([0.8, 0.7]), 0.2) == [0]


def test_decode_reads_the_yolo_layout_per_class_nms_and_maps_to_the_frame() -> None:
    # (1, 4 + 3, N): rows cx, cy, w, h, then player / monster / npc scores
    cands = [
        (100, 108, 40, 40, 0.0, 0.90, 0.0),  # monster
        (102, 110, 40, 40, 0.0, 0.80, 0.0),  # the same monster again: NMS drops it
        (100, 108, 40, 40, 0.70, 0.0, 0.0),  # a player on the same spot: another class, kept
        (500, 300, 20, 30, 0.0, 0.10, 0.0),  # below CONF: dropped
    ]
    out = np.array(cands, np.float32).T[None]
    boxes = sb.decode(out, 1.0, 0, 8)
    assert [(b.cls, b.score) for b in sorted(boxes, key=lambda b: b.cls)] == [
        ("monster", 0.9), ("player", 0.7)]  # fmt: skip
    m = next(b for b in boxes if b.cls == "monster")
    assert (m.x0, m.y0, m.x1, m.y1) == (80.0, 80.0, 120.0, 120.0)  # top padding 8 removed
    with pytest.raises(ValueError, match="classes"):
        sb.decode(np.zeros((1, 6, 5), np.float32), 1.0, 0, 0)


# ---- decide: target choice -----------------------------------------------------------------------


def test_only_monsters_and_the_nearest_one() -> None:
    far, near = mon(900, 500), mon(700, 420)
    assert sb.choose_target([far, near]) == near
    assert sb.choose_target([Box(600, 300, 650, 380, 0.9, "npc"), far]) == far
    assert sb.choose_target([Box(900, 400, 940, 470, 0.9, "player")]) is None
    assert sb.choose_target([]) is None


def test_monsters_under_the_ui_windows_are_dropped() -> None:
    minimap = mon(1200, 100)  # centre under the minimap
    chat = mon(300, 680)  # under the chat window
    basic = mon(100, 120)  # under Basic Info
    free = mon(1000, 500)
    targets, dropped = sb.sort_boxes([minimap, chat, basic, free])
    assert targets == [free]
    assert {why for _, why in dropped} == {"under minimap", "under chat", "under basic_info"}


def test_a_monster_whose_click_point_is_under_a_window_is_dropped() -> None:
    # centre above the chat window's top edge (578), its lower centre below it
    b = Box(280, 530, 340, 610, 0.9, "monster")
    assert sb.zone_at(*b.centre) == "" and sb.zone_at(*b.hit_point) == "chat"
    targets, dropped = sb.sort_boxes([b])
    assert targets == [] and dropped[0][1] == "click point off limits"


def test_a_monster_touching_another_player_or_an_npc_is_refused() -> None:
    m1, m2 = mon(800, 450), mon(500, 300)
    player = Box(810, 400, 850, 470, 0.8, "player")  # overlaps m1
    npc = Box(470, 250, 510, 320, 0.8, "npc")  # overlaps m2
    targets, dropped = sb.sort_boxes([m1, m2, player, npc])
    assert targets == []
    assert sorted(why for _, why in dropped) == ["touches a npc", "touches a player"]


def test_a_monster_hitting_our_own_character_is_still_a_target() -> None:
    me = Box(620, 290, 660, 362, 0.9, "player")  # feet at (640, 362): ourselves
    m = mon(670, 370)  # overlaps our box
    assert sb.is_self(me) and sb.overlaps(m, me)
    assert sb.choose_target([me, m]) == m


# ---- the north column, clicks and wander points -------------------------------------------------


def test_a_ground_click_straight_north_is_shifted_sideways() -> None:
    assert sb.avoid_north_column((645, 200)) == (675, 200)
    assert sb.avoid_north_column((633, 100)) == (603, 100)
    assert sb.avoid_north_column((640, 359)) == (670, 359)


def test_other_ground_clicks_are_unchanged() -> None:
    assert sb.avoid_north_column((640, 400)) == (640, 400)  # south
    assert sb.avoid_north_column((651, 200)) == (651, 200)  # 11 px aside: not the column
    assert sb.avoid_north_column((640, 360)) == (640, 360)  # our own cell (dy = 0)


def test_the_first_motion_is_10_to_15_px_from_the_target() -> None:
    rng = random.Random(3)
    for _ in range(200):
        ax, ay = sb.approach_point((640, 400), rng)
        assert 9 <= sb.dist((ax, ay), (640, 400)) <= 16
    assert sb.approach_point((0, 0), rng)[0] >= 1  # kept inside the client area


def test_wander_points_are_150_250_px_away_clickable_and_never_due_north() -> None:
    rng = random.Random(7)
    for _ in range(300):
        pt = sb.wander_point(rng)
        assert pt is not None and sb.clickable(pt)
        assert sb.WANDER_MIN_PX - 1 <= sb.dist(pt, CHAR) <= sb.WANDER_MAX_PX + sb.NORTH_SHIFT_PX
        assert not (abs(pt[0] - sb.CHAR_X) < sb.NORTH_COLUMN_PX and pt[1] < sb.CHAR_Y)


def test_clickable_refuses_the_edges_and_the_windows() -> None:
    assert sb.clickable((640, 400))
    assert not sb.clickable((5, 400)) and not sb.clickable((1275, 400))
    assert not sb.clickable((100, 100)) and not sb.clickable((300, 700))


# ---- decide: the state machine on scripted detections --------------------------------------------


def test_search_attack_loot_search_with_the_click_points() -> None:
    d = sb.Decider(random.Random(11))
    s = d.step([], 0.0)  # nothing seen: wander
    assert s.state == "SEARCH" and len(s.clicks) == 1 and s.line == ((640, 360), s.clicks[0])
    wander = s.clicks[0]
    assert sb.WANDER_MIN_PX - 1 <= sb.dist(wander, CHAR) <= sb.WANDER_MAX_PX + 31
    assert d.step([], 1.0).clicks == []  # the same wander point: no new click yet

    m = mon(760, 430)
    a = d.step([m], 1.5)  # a monster: attack it at once, on its lower centre
    assert a.state == "ATTACK" and a.target == m and a.clicks == [m.hit_point]
    assert m.hit_point == (760, 418) and a.line == ((640, 360), (760, 418))
    assert d.step([m], 2.0).clicks == []  # 0.5 s later: no re-click
    m2 = mon(770, 432)  # it moved a little: still our target
    a2 = d.step([m2, mon(300, 300)], 2.6)  # 1.1 s since the click: click again
    assert a2.state == "ATTACK" and a2.target == m2 and a2.clicks == [m2.hit_point]

    gone = d.step([], 3.0)  # unseen 0.4 s: wait, no click
    assert gone.state == "ATTACK" and gone.clicks == [] and "unseen" in gone.note
    assert d.step([], 4.0).state == "ATTACK"  # 1.4 s: still waiting

    loot1 = d.step([], 4.2)  # unseen 1.6 s > 1.5: it died -> loot at its last feet
    assert loot1.state == "LOOT" and loot1.clicks == [(770, 432)]
    assert d.step([], 4.5).clicks == []  # 0.3 s: wait
    loot2 = d.step([], 4.75)  # >= 0.5 s after the first: the second click, same point
    assert loot2.state == "LOOT" and loot2.clicks == [(770, 432)]
    assert d.step([], 5.2).state == "LOOT"  # waiting for the pick-up walk (0.8 s)
    back = d.step([], 5.6)
    assert back.state == "SEARCH" and len(back.clicks) == 1  # a fresh wander point at once


def test_loot_goes_straight_to_a_new_monster_after_the_pickup() -> None:
    d = sb.Decider(random.Random(1))
    m = mon(800, 420)
    d.step([m], 0.0)
    d.step([], 1.6)  # unseen 1.6 s -> LOOT click 1
    d.step([], 2.2)  # LOOT click 2
    nxt = mon(500, 450)
    r = d.step([nxt], 3.1)  # the pick-up wait (0.8 s) is over: SEARCH sees it at once
    assert r.state == "ATTACK" and r.target == nxt and r.clicks == [nxt.hit_point]


def test_a_loot_point_straight_north_is_shifted() -> None:
    d = sb.Decider(random.Random(1))
    m = mon(642, 250)  # straight north of us
    a = d.step([m], 0.0)
    assert a.clicks == [m.hit_point] == [(642, 238)]  # an attack click is NOT shifted
    r = d.step([], 2.0)
    assert r.state == "LOOT" and r.clicks == [(672, 250)]  # the ground click is


def test_a_new_monster_far_from_the_target_is_not_the_target() -> None:
    d = sb.Decider(random.Random(1))
    m = mon(800, 450)
    d.step([m], 0.0)
    r = d.step([mon(400, 300)], 0.5)  # another monster far away: our target is unseen
    assert r.state == "ATTACK" and r.target == m and r.clicks == []


def test_attack_gives_up_after_20_s() -> None:
    d = sb.Decider(random.Random(1))
    m = mon(800, 450)
    d.step([m], 0.0)
    assert d.step([m], 19.0).state == "ATTACK"
    r = d.step([m], 20.5)
    assert r.state == "SEARCH" and r.clicks == [] and "gave up" in r.note


# ---- make_kit's pure picks ---------------------------------------------------------------------


def test_make_kit_spreads_evenly_and_keeps_frames_with_two_monsters() -> None:
    assert kit.spread(list(range(10)), 5) == [0, 2, 4, 6, 8]
    assert kit.spread([1, 2], 5) == [1, 2]
    rows = [{"file": f"f{i}", "boxes": [[0, 0, 1, 1, 0.9, "monster"]] * (i % 3)}
            for i in range(30)]  # fmt: skip
    picked = kit.pick_samples(rows, 5, 2)
    assert len(picked) == 5 and all(int(f[1:]) % 3 == 2 for f in picked)
    assert picked[0] == "f2" and picked[-1] != "f29"


# --- --logs / --log-file (Batt 2026-11-06: "print logs, so I know where it is stuck") -------------


def test_logs_are_off_by_default_and_on_with_logs_or_a_log_file(tmp_path: Path) -> None:
    import logging

    sb.setup_logs(False)
    assert sb.LOG.level == logging.WARNING and len(sb.LOG.handlers) == 1  # warnings still show
    sb.setup_logs(True)
    assert sb.LOG.level == logging.DEBUG and not sb.LOG.propagate
    log = tmp_path / "bot.log"
    sb.setup_logs(False, str(log))  # a log file implies --logs
    assert sb.LOG.level == logging.DEBUG and len(sb.LOG.handlers) == 2
    sb.LOG.info("window found: %r (pid %s)", "Ragnarok", 4321)
    for h in sb.LOG.handlers:
        h.flush()
    line = log.read_text(encoding="utf-8").strip()
    assert line.endswith("INFO    window found: 'Ragnarok' (pid 4321)")
    assert line[2] == ":" and line[8] == "."  # HH:MM:SS.mmm first
    sb.setup_logs(False)


def test_the_command_line_takes_logs_and_a_log_file() -> None:
    a = sb.parse_args(["--watch", "--logs", "--log-file", "run.log"])
    assert a.logs and a.log_file == "run.log"
    b = sb.parse_args(["--act"])
    assert not b.logs and b.log_file is None


def test_a_refused_live_mode_is_logged_with_its_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log = tmp_path / "act.log"
    if sys.platform == "win32":
        pytest.skip("the live modes run on Windows")
    assert sb.main(["--act", "--log-file", str(log)]) == 2
    text = log.read_text(encoding="utf-8")
    assert "simple_bot act: python" in text and "options:" in text
    assert "--act refused" in capsys.readouterr().err
    sb.setup_logs(False)
