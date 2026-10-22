"""The orcsdun01 label fix (docs/planning/orcsdun01-detector.md 3b; scripts/orc_labels_fix.py,
poring_dataset.rsw, timeline.walk_rule_facing): the pure parts on SYNTHETIC bytes / packets /
frames, plus REAL positive cases from the local data (skipped when it is absent; client data is
never committed)."""

from __future__ import annotations

import json
import math
import os
import struct
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_dataset import camera as cm
from poring_dataset import render as rd
from poring_dataset import rsw
from poring_dataset.sprites import Act, Layer, Motion, Spr
from poring_dataset.timeline import ActorState, Timeline, walk_rule_facing
from poring_packets.world import World

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import label_check  # noqa: E402
import orc_camera_check as occ  # noqa: E402
import orc_label_sheets as ols  # noqa: E402
import orc_labels_fix as olf  # noqa: E402

CAMERA_JSON = cm.load_camera_json(Path(cm.__file__).parent / "camera_console.json")
OUTDOOR = cm.map_camera(CAMERA_JSON, "prt_fild08", frozenset())
MS = 1_000_000


# --- the RSW / RSM reader and the model boxes (1c) ---------------------------------------------


def s40(text: str, n: int = 40) -> bytes:
    return text.encode().ljust(n, b"\0")


def synthetic_rsw(models: Iterable[tuple[str, tuple[float, ...], tuple[float, ...],
                                         tuple[float, ...]]],
                  extra_kind: int | None = None) -> bytes:  # fmt: skip
    """RSW 2.1: the header, then one light, one sound, one effect and the given models."""
    out = b"GRSW" + bytes([2, 1]) + s40("") + s40("m.gnd") + s40("m.gat") + s40("")
    out += struct.pack("<f", 0.0) + struct.pack("<ifff", 0, 1.0, 2.0, 50.0) + struct.pack("<I", 3)
    out += struct.pack("<ii", 45, 45) + struct.pack("<6f", *([0.5] * 6)) + struct.pack("<f", 0.5)
    out += struct.pack("<4i", 0, 0, 0, 0)
    objs = [
        struct.pack("<i", 2) + s40("light", 80) + struct.pack("<7f", *([1.0] * 7)),
        struct.pack("<i", 3)
        + s40("snd", 80)
        + s40("a.wav", 80)
        + struct.pack("<4fIIff", 0, 0, 0, 1, 10, 10, 50, 4),
        struct.pack("<i", 4) + s40("fx", 80) + struct.pack("<3fIf4f", 0, 0, 0, 7, 1, 0, 0, 0, 0),
    ]
    for name, pos, rot, scale in models:
        objs.append(struct.pack("<i", 1) + s40(name) + struct.pack("<ifi", 0, 1.0, 0)
                    + s40(name + ".rsm", 80) + s40("node", 80)
                    + struct.pack("<9f", *pos, *rot, *scale))  # fmt: skip
    if extra_kind is not None:
        objs.append(struct.pack("<i", extra_kind))
    return out + struct.pack("<I", len(objs)) + b"".join(objs)


def synthetic_rsm(vertices: np.ndarray, *, scale: tuple[float, float, float] = (1, 1, 1),
                  t2: tuple[float, float, float] = (0, 0, 0)) -> bytes:  # fmt: skip
    """RSM 1.4, ONE node (identity 3x3), the given vertices, no faces, no keys."""
    out = b"GRSM" + bytes([1, 4]) + struct.pack("<II", 0, 0) + b"\xff" + b"\0" * 16
    out += struct.pack("<I", 0) + s40("root") + struct.pack("<I", 1)
    out += s40("root") + s40("") + struct.pack("<I", 0)
    out += struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1)
    out += struct.pack("<3f", 0, 0, 0) + struct.pack("<3f", *t2)
    out += struct.pack("<f3f3f", 0.0, 0, 1, 0, *scale)
    out += struct.pack("<I", len(vertices)) + np.asarray(vertices, "<f4").tobytes()
    out += struct.pack("<III", 0, 0, 0)  # texture vertices, faces, rotation keys
    return out + b"\0" * 8


def box_vertices(x: float, y: float, z: float) -> np.ndarray:
    """A box x wide, y tall (RO's y points DOWN: from -y to 0), z deep, centred on x / z."""
    return np.array([[sx * x / 2, sy, sz * z / 2] for sx in (-1, 1) for sy in (-y, 0.0)
                     for sz in (-1, 1)], dtype=float)  # fmt: skip


def test_the_rsw_lists_its_models_past_the_other_objects() -> None:
    data = synthetic_rsw([("tree", (10.0, -2.0, -20.0), (0.0, 90.0, 0.0), (1.5, 1.5, 1.5))])
    r = rsw.parse_rsw(data)
    assert r.version == (2, 1) and (r.gnd, r.gat) == ("m.gnd", "m.gat")
    assert r.objects == {"model": 1, "light": 1, "sound": 1, "effect": 1}
    (m,) = r.models
    assert (m.index, m.name, m.model_file, m.node) == (3, "tree", "tree.rsm", "node")
    assert (m.position, m.rotation, m.scale) == ((10.0, -2.0, -20.0), (0.0, 90.0, 0.0),
                                                 (1.5, 1.5, 1.5))  # fmt: skip
    with pytest.raises(rsw.RswError, match="unknown type 9"):
        rsw.parse_rsw(synthetic_rsw([], extra_kind=9))
    with pytest.raises(rsw.RswError, match="magic"):
        rsw.parse_rsw(b"GRSX" + data[4:])


def test_the_rsm_mesh_sits_on_the_ground_centred_and_scaled() -> None:
    verts = box_vertices(4, 10, 2) + np.array([7.0, 3.0, -5.0])  # off-centre in the file
    m = rsw.parse_rsm(synthetic_rsm(verts, scale=(2, 1, 1), t2=(100, 100, 100)))
    assert m.version == (1, 4) and len(m.nodes) == 1 and m.trailing == 8
    pts = rsw.model_space(m)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    assert lo == pytest.approx((-4, -10, -1)) and hi == pytest.approx((4, 0, 1))  # x scaled 2x
    with pytest.raises(rsw.RswError, match="only 1.x"):
        rsw.parse_rsm(b"GRSM" + bytes([2, 2]) + b"\0" * 64)


def test_the_instance_places_rotates_and_scales_on_the_map() -> None:
    mesh = rsw.parse_rsm(synthetic_rsm(box_vertices(10, 4, 2)))
    model = rsw.RswModel(0, "m", "m.rsm", "n", (25.0, 0.0, -50.0), (0.0, 90.0, 0.0),
                         (1.0, 1.0, 1.0))  # fmt: skip
    w = rsw.world_points(mesh, model, (200, 200))  # the map centre is (500, 500) world units
    lo, hi = w.min(axis=0), w.max(axis=0)
    assert (hi - lo) == pytest.approx((2, 4, 10))  # 90 degrees about y swaps x and z
    assert ((lo + hi) / 2)[[0, 2]] == pytest.approx((525, 450))
    cells, alt = rsw.to_cells(w)
    assert cells.mean(axis=0) == pytest.approx((525 / 5 - 0.5, 450 / 5 - 0.5))
    assert alt.min() == pytest.approx(0) and alt.max() == pytest.approx(4)  # y down -> up


def test_a_model_box_is_its_projected_vertices() -> None:
    assert OUTDOOR is not None
    cells = np.array([[99.5, 99.5]] * 2, dtype=float)
    scene = rd.Scene(OUTDOOR, (99.5, 99.5))
    box = rsw.screen_box(scene, cells, np.array([0.0, 20.0]))
    assert box is not None
    assert box[0] == pytest.approx(OUTDOOR.cx) and box[3] == pytest.approx(OUTDOOR.cy)
    assert box[1] < OUTDOOR.cy - 10  # 20 world units up draws higher
    assert rsw.overlaps((0, 0, 10, 10), (9, 9, 20, 20))
    assert not rsw.overlaps((0, 0, 10, 10), (10, 0, 20, 10))  # touching is not overlapping


# --- 1a: the facing from the walk direction ----------------------------------------------------


def ev(t_ms: int, etype: str, **kw: Any) -> dict[str, Any]:
    return {"type": etype, "t_mono_ns": t_ms * MS, **kw}


def appear(t: int, gid: int, x: int, y: int, heading: int = 4, **kw: Any) -> dict[str, Any]:
    return ev(t, "entity_appear", objtype=5, gid=gid, job=1153, x=x, y=y, name="m", speed=200,
              heading=heading, effect_state=0, **kw)  # fmt: skip


def move(t: int, gid: int, x0: int, y0: int, x1: int, y1: int, start: int) -> dict[str, Any]:
    return ev(t, "entity_appear", objtype=5, gid=gid, job=1153, x=x0, y=y0, x1=x1, y1=y1,
              move_start_tick=start, name="m", speed=200, effect_state=0)  # fmt: skip


def world_at(events: list[dict[str, Any]], t_ms: int) -> World:
    w = World()
    for e in events:
        if e["t_mono_ns"] <= t_ms * MS:
            w.apply(e["type"], e)
    return w


def test_an_ended_move_faces_from_to_until_a_turn() -> None:
    # (10,10) -> (15,12) from tick 10000 at 200 ms / cell: 2 diagonal + 3 straight = 1160 ms. The
    # LAST STEP is east (heading 6, the Timeline's facing); the move from -> to is diagonal by the
    # game's 1:3 rule: direction_toward(5, 2) = 7 (north-east)
    evs = [appear(9_000, 7, 10, 10, heading=4), move(9_990, 7, 10, 10, 15, 12, 10_000),
           ev(13_000, "entity_turn", gid=7, heading=2)]  # fmt: skip
    assert walk_rule_facing(world_at(evs, 10_500), 7, 10_500 * MS, None) is None  # walking
    assert walk_rule_facing(world_at(evs, 11_159), 7, 11_159 * MS, None) is None  # 1 ms short
    assert walk_rule_facing(world_at(evs, 11_160), 7, 11_160 * MS, None) == (7, "walk_rule")
    assert walk_rule_facing(world_at(evs, 12_900), 7, 12_900 * MS, None) == (7, "walk_rule")
    assert walk_rule_facing(world_at(evs, 13_000), 7, 13_000 * MS, None) is None  # the turn
    tl = Timeline(evs)
    st = tl.state(7, 12_000 * MS)
    assert st is not None and (st.facing, st.facing_from) == (6, "walk")  # the last step
    assert tl.walk_rule_facings(12_000 * MS) == {7: (7, "walk_rule")}
    assert tl.walk_rule_facings(9_500 * MS) == {}  # no move seen: the Timeline's facing


def test_a_stopped_move_and_an_attack() -> None:
    evs = [appear(9_000, 8, 20, 20), move(9_990, 8, 20, 20, 26, 20, 10_000),
           ev(10_500, "entity_stop", gid=8, x=22, y=20),
           appear(9_000, 9, 30, 30), move(9_990, 9, 30, 30, 30, 34, 10_000),
           appear(9_000, 5, 31, 36),
           ev(12_000, "act", kind="normal", src_gid=9, target_gid=5, server_tick=12_000,
              src_speed=500, damage=0, damage2=0, dmotion=0)]  # fmt: skip
    w = world_at(evs, 11_000)
    assert walk_rule_facing(w, 8, 11_000 * MS, None) == (6, "walk_rule")  # cut: from -> to east
    assert walk_rule_facing(world_at(evs, 11_900), 9, 11_900 * MS, None) == (0, "walk_rule")
    assert walk_rule_facing(world_at(evs, 12_100), 9, 12_100 * MS, None) is None  # attacked
    assert walk_rule_facing(world_at(evs, 12_100), 99, 12_100 * MS, None) is None  # not in sight


def act_state(state: str, facing: int | None, source: str | None = "walk") -> ActorState:
    return ActorState(1, 0, state, facing, source, 0.0, 0.0, 1153, 0)  # type: ignore[arg-type]


def test_facing_for_keeps_the_timeline_while_walking() -> None:
    rule = (7, "walk_rule")
    assert olf.facing_for(act_state("walk", 6), 4, rule) == (6, "timeline:walk")
    assert olf.facing_for(act_state("idle", 6), 4, rule) == (7, "walk_rule")
    assert olf.facing_for(act_state("idle", 6, "appear"), 4, None) == (6, "timeline:appear")
    assert olf.facing_for(act_state("idle", None, None), 3, None) == (3, "timeline:None")


# --- the fit (0): the visible-pixel NCC, the edge rule ----------------------------------------


def test_the_visible_pixel_ncc_equals_the_plain_one_and_ignores_hidden_pixels() -> None:
    rng = np.random.default_rng(5)
    h, w, r = 24, 18, 6
    template = rng.uniform(0, 255, (h, w))
    mask = rng.uniform(0, 1, (h, w)) > 0.3
    observed = rng.uniform(0, 255, (h + 2 * r, w + 2 * r))
    full = np.ones(observed.shape, bool)
    assert olf.shift_ncc_valid(observed, full, template, mask, r) == pytest.approx(
        occ.shift_ncc(observed, template, mask, r), abs=1e-9, nan_ok=True
    )
    valid = rng.uniform(0, 1, observed.shape) > 0.25
    grid = olf.shift_ncc_valid(observed, valid, template, mask, r)
    for dx, dy in ((0, 0), (-6, 6), (3, -2)):
        win = observed[r + dy : r + dy + h, r + dx : r + dx + w]
        vis = valid[r + dy : r + dy + h, r + dx : r + dx + w]
        assert grid[r + dy, r + dx] == pytest.approx(label_check.ncc(win, template, mask & vis),
                                                     abs=1e-9)  # fmt: skip


def textured_sheet(seed: int = 1, ramp: bool = False) -> rd.SpriteSheet:
    """One textured 16 x 24 body standing on the anchor, every action and direction: random grey
    pixels, or (``ramp``) a left-to-right ramp whose NCC falls off smoothly with the offset."""
    rng = np.random.default_rng(seed)
    img = np.zeros((24, 16, 4), np.uint8)
    if ramp:
        img[..., :3] = (np.arange(16) * 16).astype(np.uint8)[None, :, None]
    else:
        img[..., :3] = rng.integers(0, 256, (24, 16, 1), dtype=np.uint8)
    img[2:, 1:15, 3] = 255
    layer = Layer(0, -12, 0, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, None, None)
    act = Act((2, 5), tuple((Motion((layer,)),) for _ in range(40)), (), (4.0,) * 40)
    return rd.SpriteSheet(act, Spr((2, 1), (img,), 1, None))


def planted(sheet: rd.SpriteSheet, dx: int, dy: int,
            noise: bool = True) -> tuple[Any, rd.SpritePrediction]:  # fmt: skip
    """A grey 1280 x 720 frame (noise, or flat) with the predicted sprite drawn (dx, dy) px off."""
    assert OUTDOOR is not None
    scene = rd.Scene(OUTDOOR, (100.0, 100.0))
    pred = rd.predict_sprite(rd.Actor((102.0, 101.0), 0, elapsed_ms=0.0), sheet, scene, 0.14)
    assert pred is not None
    rng = np.random.default_rng(9)
    frame = rng.uniform(0, 255, (720, 1280)) if noise else np.full((720, 1280), 128.0)
    i0, j0 = math.floor(pred.box[0]), math.floor(pred.box[1])
    i1, j1 = math.ceil(pred.box[2]), math.ceil(pred.box[3])
    grey, opaque = label_check.rendered(sheet, pred.action_index, 0, pred.anchor_px, pred.scale,
                                        (i0, j0, i1, j1))  # fmt: skip
    win = frame[j0 + dy : j1 + dy, i0 + dx : i1 + dx]
    win[opaque] = 0.6 * grey[opaque] + 30.0
    return frame, pred


def test_the_fit_finds_the_drawn_offset_on_visible_pixels_and_flags_the_edge() -> None:
    sheet = textured_sheet()
    frame, pred = planted(sheet, 3, -2)
    valid = np.ones(frame.shape, bool)
    best = olf.fit_label(frame, valid, sheet, pred, 6)
    assert best is not None and best[1:3] == (3, -2) and best[0] == pytest.approx(1.0)
    assert not olf.at_edge(best[1], best[2], 6)
    # a UI window over the sprite's top half: hidden pixels are ignored, the fit still holds
    j_mid = int((pred.box[1] + pred.box[3]) / 2)
    valid[:j_mid, :] = False
    frame2 = frame.copy()
    frame2[:j_mid, :] = 255.0
    best2 = olf.fit_label(frame2, valid, sheet, pred, 6)
    assert best2 is not None and best2[1:3] == (3, -2) and best2[0] == pytest.approx(1.0)
    smooth = textured_sheet(ramp=True)
    far, pred_far = planted(smooth, 9, 0, noise=False)  # beyond +-6: the best is on the edge
    got = olf.fit_label(far, np.ones(far.shape, bool), smooth, pred_far, 6)
    assert got is not None and olf.at_edge(got[1], got[2], 6)
    box = olf.motion_box(sheet, pred, 0)
    assert box == pytest.approx(pred.box)


def test_visibility_is_v1s_rule() -> None:
    rects = ((0, 0, 100, 100),)
    assert olf.visible((200, 200, 240, 260), (1280, 720), rects)
    assert not olf.visible((-30, 200, 10, 260), (1280, 720), rects)  # under half on screen
    assert not olf.visible((10, 10, 60, 60), (1280, 720), rects)  # under the UI
    assert olf.valid_map((8, 4), ((2, 1, 3, 2),)).sum() == 32 - 6


def test_the_fix_applies_on_orcsdun01_only() -> None:
    from types import SimpleNamespace

    from poring_dataset.timeline import FrameWorld

    def at(tw: int) -> Any:
        return FrameWorld(tw, "prt_fild08.gat", None, (1.0, 1.0), ()), (), {}

    def at_world(tw: int) -> Any:
        return (World(), *at(tw))

    lab = SimpleNamespace(timeline=SimpleNamespace(at=at, at_world=at_world, events=()),
                          size=(64, 48), ui_rects=())  # fmt: skip
    params = {"offset_ms": 120.0, "anchors_px": {}, "fit_px": {"1153": 6}, "tau": 0.092}
    for rule in olf.RULES:
        fixer = olf.FixLabeler(lab, params, occluders=object(), rule=rule)  # type: ignore[arg-type]
        got = fixer.frame(10**9, np.zeros((48, 64, 3), np.uint8))
        assert got is not None and not got.applies and got.kept == [] and got.excluded == []


def test_the_offset_sweep_picks_the_smallest_median() -> None:
    assert olf.pick_offset({0: 5.0, 50: 2.0, 100: 2.0, 150: None}) == 50  # a tie: the smaller
    assert olf.pick_offset({0: None}) is None
    assert olf.fine_grid(150) == [100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
    assert olf.fine_grid(0)[0] == 0 and olf.fine_grid(1000)[-1] == 1000
    assert olf.median_xy([{"dx": 1, "dy": -4, "best": 0.5}, {"dx": 3, "dy": -2, "best": 0.7},
                          {"dx": 2, "dy": -3, "best": 0.6}])["dx"] == 2  # fmt: skip


def test_the_test_block_is_never_read() -> None:
    with pytest.raises(SystemExit, match="TEST block"):
        olf.refuse_test_block(Path("/x/20261021T122650-orcsdun01-col2"))
    olf.refuse_test_block(Path("/x/20261021T142100-orcsdun01-col3"))


def test_shifted_moves_box_and_anchor() -> None:
    sheet = textured_sheet()
    _frame, pred = planted(sheet, 0, 0)
    s = olf.shifted(pred, 2.5, -4.0)
    assert s.box == pytest.approx((pred.box[0] + 2.5, pred.box[1] - 4, pred.box[2] + 2.5,
                                   pred.box[3] - 4))  # fmt: skip
    assert s.anchor_px == pytest.approx((pred.anchor_px[0] + 2.5, pred.anchor_px[1] - 4))
    assert olf.shifted(pred, 0, 0) is pred


def test_the_blind_grid_pages_and_tiles() -> None:
    assert [list(p) for p in ols.grid_pages(45)] == [list(range(20)), list(range(20, 40)),
                                                     list(range(40, 45))]  # fmt: skip
    crops = [(f"{i:03d}", np.full((40, 60, 3), i * 10, np.uint8)) for i in range(1, 7)]
    g = ols.blind_grid(crops)
    assert g.shape == (2 * ols.GRID_TILE[1], ols.GRID_COLS * ols.GRID_TILE[0], 3)


# --- fix 2 (3f): the drawn view, 2b next_move, 2c ambiguous_view --------------------------------

N, NW, W, SW, S, SE, E, NE = range(8)
PAIRED = [(0, 1), (2, 3), (4, 5), (6, 7)]  # every orcsdun01 walker / bat ACT (3e finding 0)


def at_world(evs: list[dict[str, Any]], t_ms: int) -> tuple[Any, ...]:
    return Timeline(evs).at_world(t_ms * MS)


def test_at_world_is_at_with_the_world_first() -> None:
    evs = [appear(9_000, 7, 10, 10, heading=4), move(9_990, 7, 10, 10, 15, 12, 10_000)]
    tl = Timeline(evs)
    w, *rest = tl.at_world(12_000 * MS)
    assert isinstance(w, World) and tuple(rest) == tl.at(12_000 * MS)


def test_the_move_vector_is_the_walk_rules_move() -> None:
    evs = [appear(9_000, 7, 10, 10, heading=4), move(9_990, 7, 10, 10, 15, 12, 10_000),
           appear(9_000, 8, 20, 20), move(9_990, 8, 20, 20, 26, 20, 10_000),
           ev(10_500, "entity_stop", gid=8, x=22, y=20),
           appear(9_000, 9, 40, 40, heading=2)]  # fmt: skip
    assert olf.move_vector(world_at(evs, 9_995), 7, 9_995 * MS) is None  # not started yet
    assert olf.move_vector(world_at(evs, 10_500), 7, 10_500 * MS) == (5, 2)  # walking
    assert olf.move_vector(world_at(evs, 12_000), 7, 12_000 * MS) == (5, 2)  # arrived
    assert olf.move_vector(world_at(evs, 11_000), 8, 11_000 * MS) == (6, 0)  # cut: the planned move
    assert olf.move_vector(world_at(evs, 12_000), 9, 12_000 * MS) is None  # appeared standing
    assert olf.move_vector(world_at(evs, 12_000), 99, 12_000 * MS) is None  # not in sight


def test_fix2_facing_per_state() -> None:
    """(ii) walking: the vector's quadrant; (iii) after the move: map_calc_dir, an axis taken to
    its diagonal (north -> NW, east -> NE, south -> SW, west -> NW); (i) else the Timeline's."""
    walk, idle = act_state("walk", E), act_state("idle", E)
    assert olf.fix2_facing(walk, 4, None, (7, -2)) == (SE, "fix2:walk")
    assert olf.fix2_facing(walk, 4, None, (0, 3)) == (NW, "fix2:walk")
    assert olf.fix2_facing(idle, 4, (E, "walk_rule"), (7, -2)) == (NE, "fix2:after_move")
    for d, want in (((3, 0), NE), ((0, 3), NW), ((0, -3), SW), ((-3, 0), NW), ((5, -3), SE)):
        assert olf.fix2_facing(idle, 4, (0, "walk_rule"), d) == (want, "fix2:after_move")
    # no ended move (a newer turn, or appeared standing): the Timeline's facing, as 1a's fallback
    assert olf.fix2_facing(idle, 4, None, (3, 0)) == (E, "timeline:walk")
    assert olf.fix2_facing(act_state("idle", N, "appear"), N, None, None) == (N, "timeline:appear")
    assert olf.fix2_facing(act_state("idle", None, None), 3, None, None) == (3, "timeline:None")


def test_next_move_is_a_move_packet_strictly_after_and_within_150_ms() -> None:
    evs = [appear(9_000, 7, 10, 10), move(13_000, 7, 10, 10, 12, 10, 13_010),
           ev(12_950, "entity_vanish", gid=8, reason=0),
           {**move(14_000, 8, 1, 1, 2, 2, 14_010), "kind": "move"},  # as the decoder writes it
           appear(12_960, 7, 10, 10, kind="stand")]  # fmt: skip
    nm = olf.NextMoves(evs)
    assert nm.times == {7: [13_000 * MS], 8: [14_000 * MS]}  # moves only: no stand / vanish
    assert nm.soon(7, 12_900 * MS) and nm.soon(7, 12_851 * MS)
    assert not nm.soon(7, 12_850 * MS)  # exactly 150 ms before: not within
    assert not nm.soon(7, 13_000 * MS)  # the packet itself is already applied at its own time
    assert not nm.soon(8, 12_900 * MS) and not nm.soon(99, 12_900 * MS)


def test_ambiguous_view_is_a_mixed_move_whose_two_images_differ() -> None:
    # (6, -1): the vector's quadrant is SE; map_calc_dir says east -> NE's image: two images
    assert olf.ambiguous_view((6, -1), NE, PAIRED, 0.0)
    # (5, 2): quadrant NE, map_calc_dir NE: one image
    assert not olf.ambiguous_view((5, 2), NE, PAIRED, 0.0)
    # axis and diagonal moves are never ambiguous (the two rules agree by construction)
    assert not olf.ambiguous_view((3, 0), NE, PAIRED, 0.0)
    assert not olf.ambiguous_view((-2, -2), SW, PAIRED, 0.0)
    # a species whose ACT draws SE and NE alike (the plants' two images) has nothing to confuse
    assert not olf.ambiguous_view((6, -1), NE, [(0, 1, 2, 3), (4, 5, 6, 7)], 0.0)


def test_the_fix2_rule_chooses_and_excludes() -> None:
    evs = [appear(9_000, 7, 10, 10, heading=4), move(9_990, 7, 10, 10, 15, 12, 10_000),
           move(12_950, 7, 15, 12, 17, 12, 12_960),  # its next move
           appear(9_000, 8, 30, 30, heading=4), move(9_990, 8, 30, 30, 36, 29, 10_000),
           appear(9_000, 9, 40, 40, heading=2)]  # fmt: skip
    rule = olf.FacingRule.for_events("fix2", evs)
    rule.classes = lambda sheet, job, group: PAIRED  # type: ignore[method-assign,assignment]
    one_a = olf.FacingRule.for_events("1a", evs)
    tl = Timeline(evs)

    def choose(r: olf.FacingRule, gid: int, t_ms: int) -> tuple[tuple[int, str], str | None]:
        w, fw, states, rules = tl.at_world(t_ms * MS)
        e = next(x for x in fw.entities if x.gid == gid)
        st = next(s for s in states if s.gid == gid)
        return r.choose(w, e, st, rules, t_ms * MS, None, 0.0)  # type: ignore[arg-type]

    assert choose(rule, 7, 10_500) == ((NE, "fix2:walk"), None)  # (5, 2) walked
    assert choose(rule, 7, 12_000) == ((NE, "fix2:after_move"), None)
    assert choose(rule, 7, 12_900) == ((NE, "fix2:after_move"), "next_move")  # 2b: 50 ms before
    assert choose(one_a, 7, 12_900) == ((NE, "walk_rule"), None)  # 1a has no 2b
    # (6, -1) arrived: map_calc_dir east -> NE's image, the vector's quadrant SE's: 2c
    assert choose(rule, 8, 12_000) == ((NE, "fix2:after_move"), "ambiguous_view")
    assert choose(rule, 8, 10_500) == ((SE, "fix2:walk"), None)  # walking: one rule, no 2c
    assert choose(rule, 9, 12_000) == ((W, "timeline:appear"), None)  # (i) appeared standing
    with pytest.raises(SystemExit):
        olf.FacingRule.for_events("best_of_8", evs)


# --- REAL positive cases (local data only: skipped elsewhere) -----------------------------------

RSW = Path("/dev/shm/poring-lab-tmp/orc/gat/data/orcsdun01.rsw")
MODELS = Path("/dev/shm/poring-lab-tmp/orc-labels-fix/grf/data/model")
GAT = cm.GAT_DIR / "orcsdun01.gat"
COL3 = Path("/mnt/poring-lab-datasets/detector-collection/orcsdun01/20261021T142100-orcsdun01-col3")
KB = Path(os.environ.get("PORING_KB", str(ROOT / "data" / "kb")))


def test_real_model_boxes_sit_on_the_drawn_models() -> None:
    """col3 frame 9135 (the GM at 144,128): the projected boxes of RSW objects 83 (an orc flag),
    46 (a brazier) and 84 (a firewood pile) were checked by eye against the drawn models on the
    frame (2026-10-21, the 1c verification): each box sits on its model."""
    if not (RSW.exists() and MODELS.exists() and GAT.exists()):
        pytest.skip("the orcsdun01 RSW / RSM / GAT are not extracted here")
    from poring_dataset import gat as gatmod

    occl = olf.Occluders(RSW, MODELS)
    cam_json = json.loads((Path(cm.__file__).parent / "camera_rdp.json").read_text())
    cam = cm.map_camera(cam_json, "orcsdun01", frozenset())
    assert cam is not None
    scene = rd.Scene(cam, (144.0, 128.0), gatmod.parse(GAT.read_bytes()))
    boxes = dict(occl.boxes(scene))
    want = {83: (929.8, 30.0, 1015.1, 207.2), 46: (622.1, 586.3, 696.4, 693.6),
            84: (1184.3, 345.9, 1278.0, 405.5)}  # fmt: skip
    for index, box in want.items():
        assert boxes[index] == pytest.approx(box, abs=1.0)
    assert occl.hit(scene, (950.0, 150.0, 960.0, 170.0)) == 83
    assert occl.hit(scene, (700.0, 300.0, 720.0, 330.0)) is None


def test_real_walker_is_drawn_at_the_new_offset_not_the_old() -> None:
    """col3 frame 684, Orc Zombie gid 110096093 walking one move through the whole sweep: the
    rendered walk sprite lands 1 px from the packet position at 150 ms and 12 px at 400 ms (the
    old 375.9 ms's neighbourhood): the 1d sweep's own data."""
    if not (COL3 / "manifest.json").exists() or not (KB / "classes.json").exists():
        pytest.skip("col3 or the local KB is not here")
    if not (RSW.exists() and MODELS.exists()):
        pytest.skip("the orcsdun01 RSW / RSM are not extracted here")
    sess = olf.Session.open(COL3, KB)
    occl = olf.Occluders(RSW, MODELS)
    ref = next(r for r in sess.refs if r.frame_id == 684)
    found = olf.walker_samples(sess, ref.t_mono_ns, list(olf.COARSE_MS), occl)
    assert 110096093 in found
    import qa_export

    bgr = qa_export.read_jpeg(ref)
    err = {}
    for ms in (150, 400):
        e, pred = found[110096093][ms]
        bo = occ.best_offset(bgr, sess.lab.sheets(e.job), pred, olf.SEARCH_PX)
        assert bo is not None
        err[ms] = math.hypot(bo[1], bo[2])
    assert err[150] <= 2.0 and err[400] >= 8.0


def test_real_fix2_draws_the_back_of_an_orc_after_an_east_move() -> None:
    """THE REAL POSITIVE CASE of fix 2 (3f), through the labeller's own facing path: col3 frame 1938
    (3e's by-eye case), Orc Zombie gid 110096085 standing after an EAST move (3, 0) shows its
    BACK (the N / NE image). fix 2 draws NE (its back) and scores high AT the projected place;
    the frozen 1a rule draws E (the E / SE image, the cleaver side) and scores low."""
    if not (COL3 / "manifest.json").exists() or not (KB / "classes.json").exists():
        pytest.skip("col3 or the local KB is not here")
    import qa_export

    sess = olf.Session.open(COL3, KB)
    sheet = sess.lab.sheets(1153)
    if sheet is None:
        pytest.skip("the decoded sprites are not here")
    ref = next(r for r in sess.refs if r.frame_id == 1938)
    tw = ref.t_mono_ns - 120 * MS  # 3c's frozen 1d
    replay, world, states, rules = sess.lab.timeline.at_world(tw)
    e = next(x for x in world.entities if x.gid == 110096085)
    st = next(x for x in states if x.gid == e.gid)
    scene = sess.scene(world)
    assert scene is not None and st.state == "idle"
    assert olf.move_vector(replay, e.gid, tw) == (3, 0)
    fix2 = sess.facing_rule("fix2")
    (h2, src2), why = fix2.choose(replay, e, st, rules, tw, sheet, scene.camera.yaw)
    (h1, src1), _ = sess.facing_rule("1a").choose(replay, e, st, rules, tw, sheet, scene.camera.yaw)
    assert (h2, src2, why) == (NE, "fix2:after_move", None) and (h1, src1) == (E, "walk_rule")
    classes = fix2.classes(sheet, 1153, 0)
    assert classes == PAIRED
    p2, p1 = (olf.predict(e, st, sheet, scene, h, {}) for h in (h2, h1))
    assert p2 is not None and p1 is not None
    assert classes[olf._fs().class_index(classes, p2.direction)] == (4, 5)  # the back view
    bgr = qa_export.read_jpeg(ref)
    s2, s1 = label_check.score(bgr, sheet, p2), label_check.score(bgr, sheet, p1)
    assert s2 is not None and s1 is not None
    assert s2 > 0.5 and s1 < olf.TAU  # measured 0.629 vs 0.060 (2026-10-22)
