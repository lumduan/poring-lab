"""labels_v2 (docs/planning/labels-v2-plan.md): warps from L3 confirmed by the packets, NPCs per
sprite, the cut-in, region verification, our own death, decoration sites, coverage, the portal
measurement helpers -- synthetic worlds through the real camera model (no client data)."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from poring_dataset import labels_v2 as lv
from poring_dataset.camera import Camera
from poring_dataset.render import Scene
from poring_dataset.timeline import EntityState, FrameWorld

CAM = Camera(0.0, math.radians(44.44), 400.0, math.radians(15.0), 640.0, 360.0)
SIZE = (1280, 720)
NO_UI: tuple[tuple[int, int, int, int], ...] = ()


def ent(gid: int, objtype: int, job: int, x: float, y: float, hidden: bool = False,
        heading: int | None = 0) -> EntityState:  # fmt: skip
    return EntityState(gid=gid, objtype=objtype, job=job, name="", x=x, y=y, moving=False,
                       heading=heading, hidden=hidden)  # fmt: skip


def frame(*ents: EntityState, pos: tuple[float, float] = (100.0, 100.0)) -> FrameWorld:
    return FrameWorld(t_ns=0, map="m.gat", aid=7, self_pos=pos, entities=ents)


def scene(pos: tuple[float, float] = (100.0, 100.0)) -> Scene:
    return Scene(CAM, pos, None)


# --- geometry ------------------------------------------------------------------------------------


def test_ground_offset_inverts_the_camera() -> None:
    for dx, dy in [(0.0, 0.0), (3.0, 2.0), (-6.5, 4.0), (5.0, -3.0)]:
        ((u, v),) = CAM.project(np.array([[dx, dy]]))
        got = lv.ground_offset(CAM, float(u), float(v))
        assert got is not None and got == pytest.approx((dx, dy), abs=1e-6)
    assert lv.ground_offset(CAM, 640.0, -5000.0) is None  # above the horizon: no ground


def test_portal_box_is_the_projected_ring() -> None:
    sc = scene()
    box = lv.portal_box(sc, (100.0, 103.0), lv.PortalShape(7.0, 0.0, False, ""))
    assert box is not None
    (u, v), z = lv.project_cell(sc, (100.0, 103.0))
    assert (box[0] + box[2]) / 2 == pytest.approx(u, abs=0.5)  # symmetric left / right
    width = box[2] - box[0]
    assert width == pytest.approx(2 * 7.0 * lv.px_per_world(sc, z), rel=0.05)
    assert 0.6 < (box[3] - box[1]) / width < 0.8  # a ground circle: ~ sin(pitch) = 0.70
    taller = lv.portal_box(sc, (100.0, 103.0), lv.PortalShape(7.0, 10.0, False, ""))
    assert taller is not None and taller[1] < box[1] and taller[3] == pytest.approx(box[3])


def test_self_label_sits_at_the_camera_target() -> None:
    lab = lv.self_label(frame(), scene())
    assert lab is not None and lab.kind == "self" and lab.gid == 7
    assert ((lab.x0 + lab.x1) / 2, lab.y1) == pytest.approx((640.0, 360.0))


# --- warps ---------------------------------------------------------------------------------------

ROUTE = {"warps": {"m": [{"x": 102, "y": 103, "span_x": 2, "span_y": 1},
                         {"x": 140, "y": 100, "span_x": 1, "span_y": 1}]}}  # fmt: skip


def test_l3_warps_fail_closed_on_an_unknown_map() -> None:
    assert lv.l3_warps(ROUTE, "m.gat") == (lv.WarpCell(102, 103, 2, 1), lv.WarpCell(140, 100, 1, 1))
    assert lv.l3_warps(ROUTE, "other") is None and lv.l3_warps(ROUTE, None) is None
    assert lv.WarpCell(102, 103, 2, 1).area_contains(104, 102)


def warps(*ents: EntityState, vis: dict[str, str] | None = None, **kw: Any) -> lv.WarpResult:
    return lv.warp_labels(frame(*ents), scene(), SIZE, lv.l3_warps(ROUTE, "m"), visibility=vis,
                          ui_rects=NO_UI, **kw)  # fmt: skip


def test_a_visible_confirmed_portal_is_a_warp_label() -> None:
    r = warps(ent(5, 6, 45, 102, 103), vis={"m:102,103": "visible"})
    assert [(lab.cls, lab.kind, lab.source, lab.gid) for lab in r.labels] == [
        ("warp", "portal", "l3+packets", 5)]  # fmt: skip
    assert r.excluded == () and r.l3_only == (lv.WarpCell(140, 100, 1, 1),)
    assert r.labels[0].yolo(*SIZE).startswith("3 ")  # the one new head


def test_portal_visibility_rules() -> None:
    portal = ent(5, 6, 45, 102, 103)
    occ = warps(portal, vis={"m:102,103": "occluded"})
    assert occ.labels == () and len(occ.occluded) == 1 and occ.excluded == ()
    assert warps(portal, vis={"m:102,103": "partial"}).excluded == ("warp_partial:m:102,103",)
    assert warps(portal).excluded == ("warp_visibility_unknown:m:102,103",)  # no table: closed


def test_unconfirmed_and_unseen_portals_exclude_the_frame() -> None:
    stray = warps(ent(6, 6, 45, 98, 104), ent(5, 6, 45, 102, 103), vis={"m:102,103": "visible"})
    assert stray.excluded == ("portal_unconfirmed:m:98,104",) and len(stray.labels) == 1
    unseen = warps()  # L3 lists (102, 103) on screen, in range, and the packets show nothing
    assert unseen.excluded == ("l3_warp_unseen:102,103",)
    hidden = warps(ent(5, 6, 139, 102, 103))  # a hidden warp: sent as job 139, never drawn
    assert hidden.excluded == () and hidden.labels == ()
    far = lv.warp_labels(frame(pos=(120.0, 100.0)), scene((120.0, 100.0)), SIZE,
                         lv.l3_warps(ROUTE, "m"), ui_rects=NO_UI, area_cells=5)  # fmt: skip
    assert not any(e.startswith("l3_warp_unseen") for e in far.excluded)  # beyond the area


def test_a_portal_mostly_under_the_ui_is_covered_not_labelled() -> None:
    r = lv.warp_labels(frame(ent(5, 6, 45, 102, 103)), scene(), SIZE, lv.l3_warps(ROUTE, "m"),
                       visibility={"m:102,103": "visible"},
                       ui_rects=((0, 0, 1280, 720),))  # fmt: skip
    assert r.labels == () and len(r.covered) == 1


# --- NPCs per sprite -----------------------------------------------------------------------------


def npcs(*ents: EntityState, sheet: Any = None, measured: Any = None, **kw: Any) -> lv.NpcResult:
    ui = kw.pop("ui", NO_UI)
    return lv.npc_labels(frame(*ents), scene(), SIZE, sheet=sheet or (lambda job: None),
                         measured=measured or {}, k=0.14, ui_rects=ui, **kw)  # fmt: skip


def test_npc_box_from_its_sprite(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    def fake_predict(actor, sheet, sc, k):  # type: ignore[no-untyped-def]
        seen.append((actor.cell, actor.heading, actor.action, actor.elapsed_ms))
        return SimpleNamespace(box=(600.0, 200.0, 650.0, 290.0), box_kind="opaque")

    monkeypatch.setattr(lv, "predict_sprite", fake_predict)
    r = npcs(ent(9, 6, 105, 101, 103, heading=2), sheet=lambda job: object())
    assert [(lab.cls, lab.job, lab.kind) for lab in r.labels] == [("npc", 105, "sprite_opaque")]
    assert seen == [((101.0, 103.0), 2, 0, None)]  # idle, phase unknown: the envelope
    assert r.excluded == ()


def test_npc_measured_extent_scales_with_depth() -> None:
    sc = scene()
    r = npcs(ent(9, 6, 722, 100, 104), measured={722: (-40.0, -150.0, 40.0, 0.0)})
    (u, v), z = lv.project_cell(sc, (100.0, 104.0))
    s = lv.px_per_world(sc, z) * 0.14
    lab = r.labels[0]
    assert lab.kind == "measured" and (lab.x0, lab.y0, lab.y1) == pytest.approx(
        (u - 40 * s, v - 150 * s, v))  # fmt: skip


def test_an_unsized_npc_excludes_the_frame_and_hidden_classes_are_skipped() -> None:
    r = npcs(ent(9, 6, 92, 101, 102), ent(10, 6, 111, 99, 101), ent(11, 6, 45, 99, 99),
             ent(12, 6, 139, 98, 99), ent(13, 6, 80, 100, 98, hidden=True))  # fmt: skip
    assert [(lab.gid, lab.kind) for lab in r.labels] == [(9, "unsized")]
    assert r.excluded == ("npc_unsized:92",)
    covered = npcs(ent(9, 6, 92, 101, 102), ui=((0, 0, 1280, 720),))
    assert covered.labels == () and len(covered.covered) == 1 and covered.excluded == ()


# --- the cut-in, assembly ------------------------------------------------------------------------

GUIDE = "prontera:105:154,187"
RECT = (957.0, 249.0, 1183.0, 720.0)


def test_cutin_states() -> None:
    table: dict[str, lv.Rect | None] = {GUIDE: RECT, "prt_church:67:103,76": None}
    assert lv.cutin_for(False, GUIDE, table) == lv.Cutin(False)
    assert lv.cutin_for(True, GUIDE, table).rect == RECT
    church = "prt_church:67:103,76"
    assert lv.cutin_for(True, church, table) == lv.Cutin(True, None, church)
    assert lv.cutin_for(True, "x:1:2,3", table).excluded == ("cutin_unmeasured",)
    assert lv.cutin_for(True, None, table).excluded == ("cutin_unmeasured",)
    assert lv.cutin_for(True, GUIDE, table, unavailable=[GUIDE]).excluded == (
        "cutin_region_unavailable",)  # fmt: skip
    assert lv.npc_key("prontera.gat", ent(1, 6, 105, 154, 187)) == GUIDE


def test_assemble_moves_boxes_behind_a_shown_cutin_to_shadow() -> None:
    under = lv.V2Label("npc", 1000, 400, 1040, 480, gid=1, job=92, kind="unsized")
    free = lv.V2Label("monster", 100, 400, 140, 440, gid=2, job=1002)
    res = lv.NpcResult((under,), (), ("npc_unsized:92",))
    fr = lv.assemble(5, frame(), [free], res, lv.WarpResult(), lv.Cutin(True, RECT, GUIDE),
                     extra_excluded=("self_dead",))  # fmt: skip
    assert fr.labels == (free,) and fr.shadow == (under,)
    assert fr.excluded == ("self_dead",)  # the unsized NPC is hidden: no hole any more
    assert not fr.trainable and fr.projected == (free, under)
    clean = lv.assemble(5, frame(), [free], lv.NpcResult(), lv.WarpResult(), lv.Cutin(False))
    assert clean.trainable


def test_from_v1_drops_npc_boxes_and_carries_the_job() -> None:
    box = {"x1": 1, "y1": 2, "x2": 3, "y2": 4}
    boxes = [{"cls": "monster", "gid": 3, "kind": "opaque", **box},
             {"cls": "npc", "gid": 4, "kind": "v0", **box}]  # fmt: skip
    (lab,) = lv.from_v1(boxes, {3: 1161})
    assert (lab.cls, lab.gid, lab.job, lab.kind) == ("monster", 3, 1161, "opaque")


# --- verification --------------------------------------------------------------------------------


def test_verify_region() -> None:
    unit = lv.V2Label("monster", 500, 300, 540, 340, gid=3)
    portal = lv.V2Label("warp", 800, 300, 880, 360, gid=4)
    v = lv.verify_region((520, 320, 560, 360), [unit, portal], SIZE, ui_rects=NO_UI)
    assert (v.accepted, v.reason, v.against) == (False, "unit", (3,))
    assert lv.verify_region((850, 330, 900, 370), [unit, portal], SIZE, ui_rects=NO_UI).reason \
        == "warp"  # fmt: skip
    near = (555.0, 300.0, 590.0, 340.0)  # 15 px right of the unit: inside the margin
    assert lv.verify_region(near, [unit], SIZE, ui_rects=NO_UI).reason == "unit"
    assert lv.verify_region(near, [unit], SIZE, ui_rects=NO_UI, margin=5).accepted
    assert lv.verify_region((10, 10, 50, 50), [], SIZE, ui_rects=((0, 0, 100, 100),)).reason == "ui"
    inside = lv.verify_region((1000, 500, 1050, 550), [], SIZE, ui_rects=NO_UI, cutin=RECT)
    assert (inside.accepted, inside.reason) == (False, "cutin")
    assert lv.verify_region((1000, 500, 1050, 550), [], SIZE, ui_rects=NO_UI, cutin=RECT,
                            allow_cutin=True).accepted  # fmt: skip
    assert lv.verify_region((-200, -200, -100, -100), [], SIZE).reason == "off_screen"
    assert lv.verify_region((300, 300, 340, 340), [unit], SIZE, ui_rects=NO_UI).reason \
        == "background"  # fmt: skip


# --- our own death -------------------------------------------------------------------------------


def ev(t: int, typ: str, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": t, "type": typ, **kw}


def test_self_dead_spans() -> None:
    events = [ev(1, "entity_vanish", gid=7, reason=1), ev(2, "entity_vanish", gid=8, reason=1),
              ev(3, "chat", gm_command=True), ev(5, "map_change", map="m.gat"),
              ev(6, "entity_vanish", gid=7, reason=0),  # out of sight, not dead
              ev(7, "entity_vanish", gid=7, reason=1),
              ev(8, "stat_change", name="hp", value=20, gm_command=False),
              ev(9, "stat_change", name="hp", value=40, gm_command=True),
              ev(10, "entity_vanish", gid=7, reason=1)]  # fmt: skip
    assert lv.self_dead_spans(events, 7, end_ns=99) == [(1, 5), (7, 9), (10, 99)]
    assert lv.self_dead_spans(events, None) == []


# --- decoration sites, coverage ------------------------------------------------------------------


def test_sites_cluster_and_need_many_sightings_from_several_places() -> None:
    pts = [lv.Sighting("m", 174.0 + 0.1 * i, 175.5, 0.3, (44.0, 40.0), (160 + i % 4, 165))
           for i in range(12)]  # fmt: skip
    pts += [lv.Sighting("m", 150.0, 150.0, 0.5, (40.0, 40.0), (160, 165)),
            lv.Sighting("other", 174.0, 175.5, 0.5, (40.0, 40.0), (160, 165))]  # fmt: skip
    sites = lv.cluster_sites(pts)
    assert [(s.map, s.n, s.positions, s.accepted) for s in sites] == [
        ("m", 12, 4, True), ("m", 1, 1, False), ("other", 1, 1, False)]  # fmt: skip
    assert sites[0].x == pytest.approx(174.55)


def test_coverage_counts_frames_per_class_species_and_sprite() -> None:
    mon = lv.V2Label("monster", 0, 0, 1, 1, gid=1, job=1161)
    mon2 = lv.V2Label("monster", 0, 0, 1, 1, gid=2, job=1161)
    npc = lv.V2Label("npc", 0, 0, 1, 1, gid=3, job=105, kind="unsized")
    a = lv.Frame(1, "iz_dun00.gat", (mon, mon2), (), ())
    b = lv.Frame(2, "prontera.gat", (npc,), (), ("npc_unsized:105", "npc_unsized:92"))
    cov = lv.Coverage()
    cov.add(a)
    cov.add(b)
    other = lv.Coverage()
    other.add(a)
    cov.merge(other)
    d = cov.as_dict()
    assert (d["frames"], d["trainable"], d["only_npc_unsized"]) == (3, 2, 1)
    assert d["species_frames"] == {"1161": 2} and d["species_instances"] == {"1161": 4}
    assert d["npc_frames"] == {"105": 1} and d["excluded_frames"] == {"npc_unsized": 1}
    assert d["trainable_maps"] == {"iz_dun00": 2} and d["class_frames"]["monster"] == 2


# --- the portal measurement helpers --------------------------------------------------------------


def test_median_crop_and_bright_extent_find_the_disc() -> None:
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[-40:41, -40:41]
    disc = (xx / 20.0) ** 2 + (yy / 14.0) ** 2 <= 1.0  # a 41 x 29 px ellipse at the anchor
    crops = []
    for i in range(6):
        c = rng.normal(60.0, 15.0, disc.shape)
        c[disc] = 220.0
        c[:, : 10 + i] = np.nan  # masked differently in each crop (the GM, the UI)
        crops.append(c)
    med = lv.median_crop(crops)
    assert np.isnan(med[:, :10]).all() and np.isfinite(med[:, 20:]).all()
    assert lv.bright_extent(med, (40, 40)) == (-20, -14, 21, 15)
    assert lv.bright_extent(med, (40, 40), threshold=250.0) is None
    assert lv.otsu(np.r_[np.full(50, 10.0), np.full(50, 200.0)]) == pytest.approx(10.0, abs=6)
