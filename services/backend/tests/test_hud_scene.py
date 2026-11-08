"""scripts/hud_scene.py's SceneTracker (Batt 2026-10-08, the retained H.264-style HUD scene): screen
objects never shift, world objects ride ONE global motion, detection only DISCOVERS changes, and a
still scene sends nothing but keyframes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
REGION, DESKTOP = (80, 77, 1280, 720), (1440, 900)
WINDOWS = [(0, 0, 220, 326), (1135, 14, 1266, 162)]


@pytest.fixture(scope="module")
def hs() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("hud_scene", SCRIPTS / "hud_scene.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hud_scene"] = mod  # its dataclass resolves its module by name
    spec.loader.exec_module(mod)
    return mod


def unit(cls: str, x: float, y: float, w: float = 30, h: float = 60, conf: float = 0.8) -> dict:
    return {"kind": "unit", "cls": cls, "conf": conf, "box": [x - w / 2, y - h, x + w / 2, y]}


def seen(t: Any, found: list[dict], floor: bool = False) -> dict | None:
    """Two detector passes on the same view: a new unit is drawn on the second (seen twice)."""
    first = t.observe(found, t.ref() if floor else t.offset.copy())
    assert first is None or not first["add"] or all(o["kind"] != "unit" for o in first["add"])
    return t.observe(found, t.ref() if floor else t.offset.copy())  # type: ignore[no-any-return]


def test_the_keyframe_holds_the_screen_anchored_zone_and_ui_windows(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    k = t.keyframe()
    kinds = [(o["kind"], o["anchor"]) for o in k["objects"]]
    assert kinds == [("zone", "screen"), ("window", "screen"), ("window", "screen")]
    assert k["objects"][1]["box"] == {
        "x": 80 / 1440,
        "y": 77 / 900,
        "w": 220 / 1440,
        "h": 326 / 900,
    }
    assert k["offset"] == {"x": 0.0, "y": 0.0}


def test_a_static_npc_rides_the_global_motion_and_sends_nothing_new(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    d = seen(t, [unit("npc", 700, 400)])
    assert d is not None and [o["cls"] for o in d["add"]] == ["npc"] and d["seq"] == 1
    assert not t.motion((0.1, -0.2))  # sub-threshold jitter: no motion, no message
    for _ in range(10):  # we walk: the scene scrolls 3 px a frame, the NPC with it
        assert t.motion((-3.0, 2.0))
    seen_at = np.array([700 - 30.0, 400 + 20.0])  # where the NPC now is on screen
    assert t.observe([unit("npc", *seen_at)], t.offset.copy()) is None  # matched, did not move
    assert t.seq == 1


def test_a_moving_monster_gets_a_move_and_a_missed_unit_is_removed(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t, [unit("monster", 600, 300), unit("npc", 900, 500)])
    d = t.observe([unit("monster", 620, 300), unit("npc", 900, 500)], t.offset.copy())
    assert d is not None and len(d["move"]) == 1 and d["add"] == [] and d["remove"] == []
    assert t.observe([unit("monster", 620, 300)], t.offset.copy()) is None  # npc missed once
    d = t.observe([unit("monster", 620, 300)], t.offset.copy())  # ... and twice: gone
    assert d is not None and len(d["remove"]) == 1


def test_a_still_scene_sends_no_deltas(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t, [unit("npc", 700, 400), unit("npc", 300, 450)])
    for _ in range(20):
        assert not t.motion((0.05, 0.0))
        assert t.observe([unit("npc", 701, 400), unit("npc", 300, 451)], t.offset.copy()) is None


def test_every_message_is_valid_protocol(hs: ModuleType) -> None:
    import json

    from poring_env.protocol import parse_display_to_backend

    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    for _ in range(50):  # far enough that world boxes leave [0, 1] at offset 0
        t.motion((-30.0, 0.0))
    sign = {"kind": "sign", "cls": "sign", "conf": None, "box": [601, 459, 758, 490]}
    t.observe([unit("npc", 700, 400), sign], t.offset.copy())  # the sign at once, the NPC held
    d = t.observe([unit("npc", 700, 400), sign], t.offset.copy())  # ... seen twice: drawn
    for msg in (
        {"type": "hud_scene", "t_mono_ns": 1, "frame_id": 3, **t.keyframe()},
        {"type": "hud_delta", "t_mono_ns": 1, "frame_id": 3, **d},
        {"type": "hud_motion", "t_mono_ns": 1, "frame_id": 3, "offset": t.offset_norm()},
    ):
        parse_display_to_backend(json.dumps(msg))
    assert d["add"][0]["box"]["x"] > 1.0  # a world box at offset 0 may leave the screen


# --- the floor model, dedupe and cadence (2026-10-08 night: the drift while walking) -----------
@pytest.fixture(scope="module")
def camera() -> object:
    import json

    from poring_dataset import camera as cam

    cj = json.loads((SCRIPTS.parent / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    return cam.camera_from_json(cj["camera"])


def test_the_ground_is_the_camera_models_floor(hs: ModuleType, camera: object) -> None:
    g = hs.Ground(camera)
    cells = np.random.default_rng(1).uniform(-8, 8, (40, 2))
    px = camera.project(cells)  # type: ignore[attr-defined]
    assert np.abs(g.to_screen(cells) - px).max() < 1e-6
    assert np.abs(g.to_floor(px) - cells).max() < 1e-6


def test_the_floor_flows_alike_under_the_indoor_camera(hs: ModuleType, camera: object) -> None:
    """Yaw and distance only rotate and scale the cells: the screen flow of a camera move is the
    same under the indoor camera (so the hud needs no map)."""
    from poring_dataset import camera as cam

    out, ind = hs.Ground(camera), hs.Ground(cam.camera_for_map(camera, True, 45.96, 273.0))  # type: ignore[arg-type]
    pts = np.array([[300.0, 150.0], [640.0, 362.0], [1000.0, 650.0], [200.0, 600.0]])
    d_out = np.array([0.7, -0.3])
    jo = out.flow(out.to_floor([out.target]), np.zeros(2))[1][0]
    ji = ind.flow(ind.to_floor([ind.target]), np.zeros(2))[1][0]
    d_in = np.linalg.solve(ji, jo @ d_out)
    f_out = out.to_screen(out.to_floor(pts) - d_out) - pts
    f_in = ind.to_screen(ind.to_floor(pts) - d_in) - pts
    assert np.abs(f_out - f_in).max() < 1e-3  # the Jacobians are finite differences
    # ... and it is NOT one 2-D shift: far rows move ~20 % less than near ones
    assert np.hypot(*f_out[0]) < 0.85 * np.hypot(*f_out[2])


def test_floor_motion_recovers_the_camera_move(hs: ModuleType, camera: object) -> None:
    g = hs.Ground(camera)
    patches = [(x, y) for y in (200, 290, 470, 560, 650) for x in (300, 520, 850, 1070)]
    fm = hs.FloorMotion(g, patches)
    d = np.array([0.31, -0.12])
    pts = np.array(patches, dtype=float)
    s = g.to_screen(g.to_floor(pts) - d) - pts
    s[3] += (25.0, -9.0)  # one patch on a walking monster: Huber keeps it out
    got = fm.from_patches(np.arange(len(pts)), s, np.ones(len(pts)))
    assert got is not None and np.abs(got - d).max() < 0.01
    assert fm.from_patches(np.arange(3), s[:3], np.ones(3)) is None  # too few: the fallback
    shift = g.to_screen(g.to_floor([fm.BAND_CENTRE]) - d)[0] - fm.BAND_CENTRE
    assert np.abs(fm.from_shift(shift) - d).max() < 0.02


def test_far_and_near_npcs_stay_on_their_sprites_while_walking(
    hs: ModuleType, camera: object
) -> None:
    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    far, near = np.array([700.0, 140.0]), np.array([500.0, 650.0])
    d = seen(t, [unit("npc", *far), unit("npc", *near)], floor=True)
    assert d is not None and len(d["add"]) == 2
    world = [g.to_floor([far])[0], g.to_floor([near])[0]]  # their floor points (camera at 0)
    step, corrections = np.array([0.0, 0.08]), 0  # walking: the camera moves 0.08 cell a frame
    for k in range(1, 26):
        cam = k * step
        truth = g.to_screen(np.array(world) - cam)
        shift = (truth[0] - g.to_screen(np.array(world) - cam + step)[0]).tolist()
        moved, delta = t.on_frame(shift, step)
        assert moved
        corrections += delta is not None
        for o, want in zip([o for o in t.objects.values() if o.anchor == "world"], truth,
                           strict=True):  # fmt: skip
            drawn = hs._foot(o.box) + t.offset
            assert np.hypot(*(drawn - want)) <= t.tuning.resid_px + 1e-6
    assert 0 < corrections <= 25
    # the global model, the same walk: the far NPC ends well off its sprite
    t2 = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t2, [unit("npc", *far), unit("npc", *near)])
    for k in range(1, 26):
        t2.motion(tuple(g.to_screen([world[1] - k * step])[0]
                        - g.to_screen([world[1] - (k - 1) * step])[0]))  # fmt: skip
    o_far = next(iter(o for o in t2.objects.values() if o.cls == "npc"))
    want_far = g.to_screen([world[0] - 25 * step])[0]
    assert np.hypot(*(hs._foot(o_far.box) + t2.offset - want_far)) > 10


def test_a_still_floor_scene_sends_nothing(hs: ModuleType, camera: object) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, hs.Ground(camera))
    seen(t, [unit("npc", 700, 400), unit("npc", 300, 450)], floor=True)
    for _ in range(20):
        assert t.on_frame((0.05, 0.0), np.array([0.001, 0.0])) == (False, None)
        assert t.observe([unit("npc", 701, 400), unit("npc", 300, 451)], t.ref()) is None
    assert t.seq == 1


def test_a_drifted_box_is_moved_not_doubled(hs: ModuleType) -> None:
    for tuning, doubled in ((hs.TUNING, False), (hs.LEGACY, True)):
        t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=tuning)
        t.observe([unit("npc", 700, 400)], t.offset.copy())
        t.observe([unit("npc", 700, 400)], t.offset.copy())  # drawn (seen twice), both tunings
        d = t.observe([unit("npc", 760, 410)], t.offset.copy())  # 61 px off: past match_px
        n = len([o for o in t.objects.values() if o.cls == "npc"])
        if doubled:  # the first cut: a second box, the stale one kept until missed twice
            assert d is not None and len(d["add"]) == 1 and n == 2
        else:
            assert d is not None and d["add"] == [] and len(d["move"]) == 1 and n == 1


def test_one_to_one_nearest_first(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t, [unit("npc", 500, 400), unit("npc", 530, 400)])
    ids = sorted(o.id for o in t.objects.values() if o.cls == "npc")
    # the first detection is nearer the second object: each still keeps its own
    assert t.observe([unit("npc", 518, 400), unit("npc", 531, 400)], t.offset.copy()) is not None
    assert sorted(o.id for o in t.objects.values() if o.cls == "npc") == ids


def test_a_missed_object_goes_after_one_pass_while_moving(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t, [unit("npc", 700, 400), unit("npc", 300, 450)])
    assert t.observe([unit("npc", 700, 400)], t.offset.copy()) is None  # still: one miss kept
    d = t.observe([unit("npc", 700, 400)], t.offset.copy(), moving=True)
    assert d is not None and len(d["remove"]) == 1
    seen(t, [unit("npc", 300, 450)])  # it is back: a new unit, seen twice
    d = t.observe([unit("npc", 700, 400)], t.offset.copy(), moving=True)
    assert d is not None and len(d["remove"]) == 1  # one miss while moving is enough


def test_a_sign_rides_its_npcs_floor(hs: ModuleType, camera: object) -> None:
    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    npc = unit("npc", 700, 400, h=80)  # box top 320
    sign = {"kind": "sign", "cls": "sign", "conf": None, "box": [640, 200, 790, 225]}
    t.observe([npc, sign], t.ref())  # a sign is drawn at once (no measured false signs)
    s = next(o for o in t.objects.values() if o.kind == "sign")
    assert s.lift == pytest.approx(400 - 225)
    alone = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    alone.observe([sign], alone.ref())
    assert next(o for o in alone.objects.values() if o.kind == "sign").lift == hs.SIGN_LIFT_PX


def test_the_cadence_runs_faster_while_moving(hs: ModuleType) -> None:
    c = hs.Cadence(hs.TUNING)
    still = np.zeros((90, 160), np.float32)
    c.ran(100.0, still)
    assert not c.due(100.0 + hs.TUNING.det_moving_s, still)  # still: the idle period
    assert c.due(100.0 + hs.TUNING.det_idle_s, still)
    assert c.due(100.0 + hs.TUNING.det_changed_s, still + 50)  # the frame changed
    c.last_motion = 100.2
    assert c.due(100.0 + hs.TUNING.det_moving_s, still)  # moving
    assert not c.moving(100.2 + hs.TUNING.moving_hold_s + 0.01)


def test_floor_corrections_are_valid_protocol(hs: ModuleType, camera: object) -> None:
    import json

    from poring_env.protocol import parse_display_to_backend

    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    seen(t, [unit("npc", 700, 140), unit("npc", 500, 650)], floor=True)
    msgs = []
    for _ in range(10):
        moved, delta = t.on_frame((0.0, -3.0), np.array([0.0, 0.12]))
        msgs += hs.frame_messages(t, 1, 3, moved, delta)
    assert any(m["type"] == "hud_delta" and m["move"] for m in msgs)
    for m in msgs:
        parse_display_to_backend(json.dumps(m))


# --- the offline sim (scripts/hud_scene_sim.py), end to end on a synthetic walk ------------------
def synthetic_walk(hs: ModuleType, camera: object, n: int = 70) -> dict:
    """A recording's caches without pixels: two NPCs (one far, one near), still, then the camera
    walks 0.08 cell a frame for 30 frames, then still. Truth = the camera model's projection."""
    import route_preview as rp

    g = hs.Ground(camera)
    world = g.to_floor(np.array([[700.0, 130.0], [480.0, 640.0]]))
    t = (np.arange(n) * 100_000_000 + 10**12).astype(np.int64)
    cams = np.cumsum([[0.0, 0.08] if 10 <= k < 40 else [0.0, 0.0] for k in range(n)], axis=0)
    units, shift, pshift = [], np.zeros((n, 2)), np.full((n, len(rp.PATCHES), 2), np.nan)
    pts = np.array(rp.PATCHES, dtype=float)
    band = np.array([hs.FloorMotion.BAND_CENTRE])
    gray = np.zeros((n, 90, 160), np.float16)
    for k in range(n):
        for x, y in g.to_screen(world - cams[k]):
            units.append([k, x - 15, y - 60, x + 15, y, 0.9, 2])
        if k:
            d = cams[k] - cams[k - 1]
            shift[k] = g.to_screen(g.to_floor(band) - d)[0] - band[0]
            pshift[k] = g.to_screen(g.to_floor(pts) - d) - pts
            if np.any(d):
                gray[k:] += 20  # the frame changed
    pq = np.where(np.isnan(pshift[..., 0]), 0.0, 1.0)
    motion = {"t": t, "shift": shift, "pshift": pshift, "pq": pq, "shift_hp": shift,
              "pshift_hp": pshift, "pq_hp": pq, "gray8": gray}  # fmt: skip
    truth = {"t": t, "units": np.array(units), "signs": np.zeros((0, 5)),
             "det_ms": np.full(n, 400.0), "sign_ms": np.full(n, 100.0)}  # fmt: skip
    return {"truth": truth, "motion": motion}


def test_the_sim_scores_the_floor_model_on_its_own_message_stream(
    hs: ModuleType, camera: object, tmp_path: Path
) -> None:
    sim = importlib.import_module("hud_scene_sim")
    cache = synthetic_walk(hs, camera)
    out = {}
    for v in (sim.Variant("legacy", hs.LEGACY), sim.Variant("chosen", hs.TUNING)):
        res = sim.simulate(tmp_path, cache, v, REGION, DESKTOP)
        types = [e["msg"]["type"] for e in res["log"]]
        assert types[0] == "hud_scene" and "hud_motion" in types
        assert [e["logged_ns"] for e in res["log"]] == sorted(e["logged_ns"] for e in res["log"])
        out[v.name] = sim.score(res["log"], cache, REGION, DESKTOP)
        moving = cache["motion"]["t"][np.hypot(*cache["motion"]["shift"].T) > 0]
        still = [e for e in res["log"] if e["msg"]["type"] == "hud_delta"
                 and not moving[0] <= e["msg"]["t_mono_ns"] <= moving[-1]]  # fmt: skip
        assert len(still) <= 2  # still: the first add, and the one settle pass after the walk
    walk = {k: o["offsets"]["npc:walking"] for k, o in out.items()}
    assert walk["chosen"]["p95_px"] <= hs.TUNING.resid_px + 1.0  # every frame on its sprite
    # one 2-D shift: the far NPC drifts between re-detections (measured 4.1 / 7.5 / 8.0 px here)
    assert walk["legacy"]["p95_px"] > 2 * walk["chosen"]["p95_px"]
    assert walk["legacy"]["max_px"] > 6
    assert out["chosen"]["doubled"] == 0


def test_the_process_loop_runs_end_to_end_offline(
    hs: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """serve() itself on synthetic bus frames (a texture scrolling 4 px a frame, then still), a fake
    detector, no backend: every message it logs is valid protocol, in seq order, and it ends."""
    import json
    import os
    import signal
    import time

    import ro_agent
    import unit_detector

    from poring_env.protocol import parse_display_to_backend

    rng = np.random.default_rng(5)
    tex = rng.random((900, 1700)).astype(np.float32)
    for _ in range(3):
        tex = (np.roll(tex, 1, 0) + tex + np.roll(tex, -1, 0)) / 3
        tex = (np.roll(tex, 1, 1) + tex + np.roll(tex, -1, 1)) / 3
    tex = ((tex - tex.min()) / (tex.max() - tex.min()) * 200 + 20).astype(np.uint8)
    n_frames, pos = 45, {"k": 0}

    def scroll(k: int) -> int:
        return 4 * min(k, 25)  # the camera walks for 25 frames, then stands

    class FakeScreen:
        def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray, int, str]:
            k = pos["k"]
            if k >= n_frames:
                raise KeyboardInterrupt  # the end of the recording: leaves serve() via finally
            pos["k"] += 1
            g = tex[100 : 100 + h, 200 + scroll(k) : 200 + scroll(k) + w]
            img = np.dstack([g, g, g, np.full_like(g, 255)])
            return time.monotonic_ns(), img, 1000 + k, "bus"

        def close(self) -> None:
            pass

    class FakeDetector:
        def __init__(self, threads: int = 2) -> None:
            pass

        def detect(self, img: np.ndarray) -> list[unit_detector.Box]:
            dx = -scroll(pos["k"] - 1)
            return [unit_detector.Box(600 + dx, 300, 630 + dx, 360, 0.9, "npc"),
                    unit_detector.Box(900 + dx, 500, 930 + dx, 560, 0.8, "npc")]  # fmt: skip

        def close(self) -> None:
            pass

    monkeypatch.setattr(hs, "STATE_DIR", tmp_path)
    monkeypatch.setattr(hs, "LOCK", tmp_path / "hud_scene.lock")
    monkeypatch.setattr(hs, "SCENE_LOG", tmp_path / "scene.jsonl")
    monkeypatch.setattr(os, "nice", lambda n: 0)
    monkeypatch.setattr(signal, "signal", lambda *a: None)
    monkeypatch.setattr(ro_agent, "Screen", FakeScreen)
    monkeypatch.setattr(ro_agent, "game_region", lambda: REGION)
    monkeypatch.setattr(ro_agent, "desktop", lambda: DESKTOP)
    monkeypatch.setattr(ro_agent, "backend_ws", lambda: "ws://127.0.0.1:9/internal/agent")
    monkeypatch.setattr(unit_detector, "UnitDetector", FakeDetector)
    with pytest.raises(KeyboardInterrupt):
        hs.serve(20.0, hs.TUNING)
    log, size = tmp_path / "scene.jsonl", -1
    for _ in range(50):  # the sender thread drains its queue
        if log.exists() and log.stat().st_size == size:
            break
        size = log.stat().st_size if log.exists() else -1
        time.sleep(0.1)
    msgs = [json.loads(line)["msg"] for line in log.read_text().splitlines()]
    types = {m["type"] for m in msgs}
    assert {"hud_scene", "hud_motion", "hud_delta"} <= types
    seq = None
    for m in msgs:
        parse_display_to_backend(json.dumps(m))
        if m["type"] == "hud_scene":
            seq = m["seq"]
        elif m["type"] == "hud_delta":
            assert seq is not None and m["seq"] == seq + 1  # no gap: a console never goes stale
            seq = m["seq"]


def test_a_box_cut_by_the_views_edge_gets_its_sprites_size(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    cut = {"kind": "unit", "cls": "npc", "conf": 0.8, "box": [600.0, 690.0, 634.0, 720.0]}
    seen(t, [cut])
    o = next(o for o in t.objects.values() if o.cls == "npc")
    assert o.box[3] == pytest.approx(690.0 + hs.SPRITE_PX["npc"][1])  # its feet are past the edge
    left = {"kind": "unit", "cls": "npc", "conf": 0.8, "box": [0.0, 300.0, 12.0, 375.0]}
    t2 = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t2, [left])
    o2 = next(o for o in t2.objects.values() if o.cls == "npc")
    assert o2.box[0] == pytest.approx(12.0 - hs.SPRITE_PX["npc"][0]) and o2.box[3] == 375.0


def test_a_floor_frame_without_a_camera_move_reads_the_scroll(
    hs: ModuleType, camera: object
) -> None:
    """The floor model never moves the offset without its camera (else the next frame pulls it
    back): no camera move given -> the scroll read at the band's centre."""
    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    t.observe([unit("npc", 700, 400)], t.ref())
    d = np.array([0.2, -0.1])
    band = np.array([hs.FloorMotion.BAND_CENTRE])
    shift = g.to_screen(g.to_floor(band) - d)[0] - band[0]
    assert t.on_frame(shift, None)[0]
    assert np.abs(t.cam - d).max() < 0.02


# --- seen twice (Batt 2026-10-09): a new unit is drawn only when a later pass sees it again -------
def test_a_new_unit_is_drawn_only_when_a_second_pass_sees_it(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    assert t.observe([unit("npc", 700, 400)], t.offset.copy()) is None  # held: no message at all
    assert [o["kind"] for o in t.keyframe()["objects"]] == ["zone", "window", "window"]
    d = t.observe([unit("npc", 703, 401)], t.offset.copy())
    assert d is not None and d["seq"] == 1 and [o["cls"] for o in d["add"]] == ["npc"]
    assert d["add"][0]["id"] > 0 and not t.candidates  # a wire id; the candidate is gone
    assert d["add"][0]["box"]["x"] == pytest.approx((80 + 703 - 15) / 1440)  # the 2nd pass's box


def test_a_one_off_detection_never_reaches_the_wire(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    seen(t, [unit("npc", 300, 450)])
    seq = t.seq
    flash = unit("npc", 900, 200, conf=0.27)
    assert t.observe([unit("npc", 300, 450), flash], t.offset.copy()) is None
    for _ in range(3):
        assert t.observe([unit("npc", 300, 450)], t.offset.copy()) is None
    assert t.seq == seq and not t.candidates and t.counts == {"held": 2, "confirmed": 1,
                                                              "expired": 1}  # fmt: skip
    world = [o for o in t.objects.values() if o.anchor == "world"]
    assert len(world) == 1 and world[0].box[0] == pytest.approx(285.0)


def test_the_window_is_counted_in_detector_passes(hs: ModuleType) -> None:
    from dataclasses import replace

    passes = [[unit("monster", 600, 300)], [], [unit("monster", 610, 300)],
              [unit("monster", 611, 300)]]  # fmt: skip
    for window, drawn_on in ((2, 3), (1, 4)):  # missed once: still a candidate / a new one
        t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=replace(hs.TUNING, seen_window=window))
        got = [t.observe(f, t.offset.copy()) is not None for f in passes]
        assert got.index(True) + 1 == drawn_on and got.count(True) == 1


def test_drawn_objects_behave_exactly_as_without_the_rule(hs: ModuleType) -> None:
    """The same passes with the rule on and off: once both drew the units, every later message is
    the same (moves, the dedupe of a drifted box, misses and removals)."""
    from dataclasses import replace

    on = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    off = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=replace(hs.TUNING, seen_twice=()))
    start = [unit("npc", 500, 400), unit("monster", 800, 300)]
    off.observe(start, off.offset.copy())
    seen(on, start)
    assert on.keyframe() == off.keyframe()
    passes = [
        ([unit("npc", 510, 400), unit("monster", 861, 310)], False),  # a move; a dedupe move
        ([unit("npc", 510, 400)], False),  # the monster missed once
        ([unit("npc", 530, 410)], True),  # ... and again, while moving: removed
        ([], False),
        ([], False),
    ]
    for found, moving in passes:
        for t in (on, off):
            t.motion((-3.0, 2.0))
        assert on.observe(found, on.offset.copy(), moving=moving) == off.observe(
            found, off.offset.copy(), moving=moving
        )
    assert on.keyframe() == off.keyframe() and on.seq == off.seq >= 3


def test_a_candidate_rides_the_floor_until_it_is_seen_again(hs: ModuleType, camera: object) -> None:
    """The camera walks ~150 px between the two passes: the candidate is matched where its floor
    point projects now (a plain match), not where it was first seen."""
    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    p = np.array([700.0, 300.0])
    assert t.observe([unit("npc", *p)], t.ref()) is None
    fl, step = g.to_floor([p])[0], np.array([0.0, 0.3])
    for k in range(1, 21):
        t.on_frame(g.to_screen([fl - k * step])[0] - g.to_screen([fl - (k - 1) * step])[0], step)
    now = g.to_screen([fl - 20 * step])[0]
    assert np.hypot(*(now - p)) > t.tuning.dedupe_px  # out of reach unless it rode the floor
    d = t.observe([unit("npc", *now)], t.ref(), moving=True)
    assert d is not None and len(d["add"]) == 1 and not t.candidates


def test_signs_are_drawn_at_once_and_the_rule_switches_off(hs: ModuleType) -> None:
    from dataclasses import replace

    sign = {"kind": "sign", "cls": "sign", "conf": None, "box": [601, 459, 758, 490]}
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    d = t.observe([sign], t.offset.copy())
    assert d is not None and [o["kind"] for o in d["add"]] == ["sign"]
    t2 = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=replace(hs.TUNING, seen_twice=()))
    d2 = t2.observe([unit("npc", 700, 400)], t2.offset.copy())
    assert d2 is not None and len(d2["add"]) == 1
    assert hs.LEGACY.seen_twice == () and hs.TUNING.seen_twice == ("unit",)


def test_the_sim_counts_flashes_and_the_first_box_delay(hs: ModuleType, tmp_path: Path) -> None:
    """hud_scene_sim's seen-twice measures on a hand-made log: a REAL unit drawn 5 frames after it
    appears, and a one-frame flash drawn for 6 frames."""
    sim = importlib.import_module("hud_scene_sim")
    n = 60
    t = (np.arange(n) * 100_000_000 + 10**12).astype(np.int64)
    units = [[k, 485, 340, 515, 400, 0.9, 2] for k in range(n)]  # A, all along
    units += [[k, 885, 440, 915, 500, 0.6, 2] for k in range(30, n)]  # B, from frame 30
    units.append([40, 285, 140, 315, 200, 0.3, 2])  # a flash on frame 40
    cache = {
        "truth": {"t": t, "units": np.array(units, dtype=float), "signs": np.zeros((0, 5))},
        "motion": {"t": t, "shift": np.zeros((n, 2)), "gray8": np.zeros((n, 2, 2))},
    }

    def obj(i: int, x0: float, y0: float) -> dict:
        box = {"x": (80 + x0) / 1440, "y": (77 + y0) / 900, "w": 30 / 1440, "h": 60 / 900}
        return {"id": i, "kind": "unit", "anchor": "world", "box": box, "cls": "npc"}

    def delta(k: int, seq: int, add: list, remove: list) -> dict:
        return {"logged_ns": int(t[k]), "msg": {"type": "hud_delta", "t_mono_ns": int(t[k]),
                "frame_id": k, "seq": seq, "add": add, "move": [], "remove": remove}}  # fmt: skip

    log = [{"logged_ns": int(t[0]), "msg": {"type": "hud_scene", "t_mono_ns": int(t[0]),
            "frame_id": 0, "seq": 0, "offset": {"x": 0.0, "y": 0.0},
            "objects": [obj(1, 485, 340)], "period_ms": 5000}},  # fmt: skip
           delta(35, 1, [obj(2, 885, 440)], []), delta(40, 2, [obj(3, 285, 140)], []),
           delta(46, 3, [], [3])]  # fmt: skip
    sc = sim.score(log, cache, REGION, DESKTOP, latency_ms=0.0)
    assert sc["fp"]["objects"] == 1 and sc["fp"]["box_frames"] == 6
    nu = sc["new_units"]
    assert nu["n"] == 1 and nu["never"] == 0
    assert nu["delay_s"]["median_s"] == pytest.approx(0.5) and nu["delay_frames"]["median_fr"] == 5
    assert sc["recall"] == {"real": 40 + 30, "drawn": 40 + 25}


# --- the confirming pass (Batt 2026-10-09 ~09:20): one extra look ~1 s after a new candidate -----
def drive(hs: ModuleType, found_at: Any, until: float, moving: Any = None, **tune: Any) -> dict:
    """serve()'s detector loop on a clock of 0.1-s steps, every pass instant: the cadence picks the
    pass (regular / confirm), the tracker observes what ``found_at(t)`` returns."""
    from dataclasses import replace

    tuning = replace(hs.TUNING, **tune)
    t, c = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=tuning), hs.Cadence(tuning)
    g8 = np.zeros((90, 160), np.float32)  # a still frame: no "changed" passes
    passes, drawn = [], {}
    for i in range(int(until * 10)):
        now = i / 10
        if moving is not None and moving(now):
            c.last_motion = now
        kind = c.kind(now, g8)
        if kind is None:
            continue
        c.ran(now, g8, kind)
        d = t.observe(found_at(now), t.offset.copy(), moving=c.moving(now))
        if t.fresh:
            c.held(now)
        passes.append((now, kind))
        for o in (d or {}).get("add", []):
            drawn[o["id"]] = now
    return {"tracker": t, "cadence": c, "passes": passes, "drawn": drawn}


def test_the_confirming_pass_runs_once_and_leaves_the_cadence_alone(hs: ModuleType) -> None:
    """Still scene: a unit first seen at 0 s is drawn by the confirming pass at 1 s, not at the
    next idle pass (5 s); the regular passes stay at 0 / 5 / 10 s; a unit new at 5 s gets its
    own."""

    def found(now: float) -> list[dict]:
        return [unit("npc", 700, 400)] + ([unit("npc", 300, 450)] if now >= 4.0 else [])

    r = drive(hs, found, 12.0)
    assert r["passes"] == [(0.0, "regular"), (1.0, "confirm"), (5.0, "regular"),
                           (6.0, "confirm"), (10.0, "regular")]  # fmt: skip
    assert sorted(r["drawn"].values()) == [1.0, 6.0]
    off = drive(hs, found, 12.0, confirm_s=0.0)  # the plain rule: the idle passes only
    assert off["passes"] == [(0.0, "regular"), (5.0, "regular"), (10.0, "regular")]
    assert sorted(off["drawn"].values()) == [5.0, 10.0]
    c = hs.Cadence(hs.TUNING)
    c.held(3.0)
    c.held(3.5)  # never more than one asked for: the first stands
    assert c.confirm_at == 4.0


def test_a_regular_pass_first_cancels_the_confirming_pass(hs: ModuleType) -> None:
    """Moving: the regular passes run every 0.5 s, so the unit is confirmed by the next regular
    pass and no confirming pass ever runs."""
    r = drive(hs, lambda now: [unit("npc", 700, 400)], 3.0, moving=lambda now: True)
    assert {k for _, k in r["passes"]} == {"regular"}
    assert list(r["drawn"].values()) == [0.5] and r["cadence"].confirm_at is None


def test_a_candidate_the_confirming_pass_does_not_see_is_never_drawn(hs: ModuleType) -> None:
    """A one-pass flash: the confirming pass at 1 s does not see it; it is never drawn, and it is
    gone once its window of passes has passed."""
    r = drive(hs, lambda now: [unit("npc", 900, 200, conf=0.27)] if now < 0.5 else [], 12.0)
    assert r["drawn"] == {} and r["tracker"].seq == 0
    assert [k for _, k in r["passes"]].count("confirm") == 1
    t = r["tracker"]
    assert not t.candidates and t.counts == {"held": 1, "confirmed": 0, "expired": 1}


def test_the_huds_boxes_come_from_the_arc_first_with_the_cpu_behind(hs: ModuleType) -> None:
    """Batt 2026-11-08 ("the GPU for detection, the box HUD too"): the HUD asks the vision worker's
    detect server first (GpuDetector), the same CPU detector behind it; --detector cpu = before."""
    assert hs.TUNING.detector == "gpu"
    src = (SCRIPTS / "hud_scene.py").read_text()
    assert "cpu_det = unit_detector.UnitDetector(threads=DET_THREADS)" in src
    assert 'det = unit_detector.GpuDetector(cpu_det, weights="v1")' in src
    assert 'if tuning.detector == "gpu":' in src and "detector=a.detector" in src
    assert 'stats["paths"][getattr(det, "last_path", "") or "cpu"] += 1' in src  # in the report
