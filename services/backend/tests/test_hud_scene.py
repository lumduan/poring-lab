"""scripts/hud_scene.py's SceneTracker (Batt 2026-10-08, the retained H.264-style HUD scene): screen
objects never shift, world objects ride ONE global motion, detection only DISCOVERS changes, and a
still scene sends nothing but keyframes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

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
    d = t.observe([unit("npc", 700, 400)], t.offset.copy())
    assert d is not None and [o["cls"] for o in d["add"]] == ["npc"] and d["seq"] == 1
    assert not t.motion((0.1, -0.2))  # sub-threshold jitter: no motion, no message
    for _ in range(10):  # we walk: the scene scrolls 3 px a frame, the NPC with it
        assert t.motion((-3.0, 2.0))
    seen_at = np.array([700 - 30.0, 400 + 20.0])  # where the NPC now is on screen
    assert t.observe([unit("npc", *seen_at)], t.offset.copy()) is None  # matched, did not move
    assert t.seq == 1


def test_a_moving_monster_gets_a_move_and_a_missed_unit_is_removed(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("monster", 600, 300), unit("npc", 900, 500)], t.offset.copy())
    d = t.observe([unit("monster", 620, 300), unit("npc", 900, 500)], t.offset.copy())
    assert d is not None and len(d["move"]) == 1 and d["add"] == [] and d["remove"] == []
    assert t.observe([unit("monster", 620, 300)], t.offset.copy()) is None  # npc missed once
    d = t.observe([unit("monster", 620, 300)], t.offset.copy())  # ... and twice: gone
    assert d is not None and len(d["remove"]) == 1


def test_a_still_scene_sends_no_deltas(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("npc", 700, 400), unit("npc", 300, 450)], t.offset.copy())
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
    d = t.observe([unit("npc", 700, 400), sign], t.offset.copy())
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
    d = t.observe([unit("npc", *far), unit("npc", *near)], t.ref())
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
    t2.observe([unit("npc", *far), unit("npc", *near)], t2.offset.copy())
    for k in range(1, 26):
        t2.motion(tuple(g.to_screen([world[1] - k * step])[0]
                        - g.to_screen([world[1] - (k - 1) * step])[0]))  # fmt: skip
    o_far = next(iter(o for o in t2.objects.values() if o.cls == "npc"))
    want_far = g.to_screen([world[0] - 25 * step])[0]
    assert np.hypot(*(hs._foot(o_far.box) + t2.offset - want_far)) > 10


def test_a_still_floor_scene_sends_nothing(hs: ModuleType, camera: object) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, hs.Ground(camera))
    t.observe([unit("npc", 700, 400), unit("npc", 300, 450)], t.ref())
    for _ in range(20):
        assert t.on_frame((0.05, 0.0), np.array([0.001, 0.0])) == (False, None)
        assert t.observe([unit("npc", 701, 400), unit("npc", 300, 451)], t.ref()) is None
    assert t.seq == 1


def test_a_drifted_box_is_moved_not_doubled(hs: ModuleType) -> None:
    for tuning, doubled in ((hs.TUNING, False), (hs.LEGACY, True)):
        t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, tuning=tuning)
        t.observe([unit("npc", 700, 400)], t.offset.copy())
        d = t.observe([unit("npc", 760, 410)], t.offset.copy())  # 61 px off: past match_px
        n = len([o for o in t.objects.values() if o.cls == "npc"])
        if doubled:  # the first cut: a second box, the stale one kept until missed twice
            assert d is not None and len(d["add"]) == 1 and n == 2
        else:
            assert d is not None and d["add"] == [] and len(d["move"]) == 1 and n == 1


def test_one_to_one_nearest_first(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("npc", 500, 400), unit("npc", 530, 400)], t.offset.copy())
    ids = sorted(o.id for o in t.objects.values() if o.cls == "npc")
    # the first detection is nearer the second object: each still keeps its own
    assert t.observe([unit("npc", 518, 400), unit("npc", 531, 400)], t.offset.copy()) is not None
    assert sorted(o.id for o in t.objects.values() if o.cls == "npc") == ids


def test_a_missed_object_goes_after_one_pass_while_moving(hs: ModuleType) -> None:
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t.observe([unit("npc", 700, 400), unit("npc", 300, 450)], t.offset.copy())
    assert t.observe([unit("npc", 700, 400)], t.offset.copy()) is None  # still: one miss kept
    d = t.observe([unit("npc", 700, 400)], t.offset.copy(), moving=True)
    assert d is not None and len(d["remove"]) == 1
    t.observe([unit("npc", 300, 450)], t.offset.copy())
    d = t.observe([unit("npc", 700, 400)], t.offset.copy(), moving=True)
    assert d is not None and len(d["remove"]) == 1  # one miss while moving is enough


def test_a_sign_rides_its_npcs_floor(hs: ModuleType, camera: object) -> None:
    g = hs.Ground(camera)
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS, g)
    npc = unit("npc", 700, 400, h=80)  # box top 320
    sign = {"kind": "sign", "cls": "sign", "conf": None, "box": [640, 200, 790, 225]}
    t.observe([npc, sign], t.ref())
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
    t.observe([unit("npc", 700, 140), unit("npc", 500, 650)], t.ref())
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
