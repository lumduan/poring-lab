"""scripts/ui_mask.py (Batt 2026-10-09 ~16:10): the NPC dialog's CUT-IN illustration is client UI
while a dialog is open -- or while its state cannot be read (fail closed) -- for the detector, the
HUD and the walk gate. The geometry, the fail-closed rule, the lazy reader, the HUD's filter on a
synthetic scene, and the offline check on banked guide frames (skipped where they are absent)."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from poring_env.npc_dialog import DialogView, MenuView, NpcUiState

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
REGION, DESKTOP = (80, 77, 1280, 720), (1440, 900)
WINDOWS = [(0, 0, 220, 326), (1135, 14, 1266, 162)]
# The v0-PNG detector's "monster 0.31" on the prontera guide's cut-in (the hand on the spear):
# 120 / 120 dialog-open frames of the 2026-10-09 talk-cal sessions, never on a closed one
PHANTOM = (983.9, 598.7, 1032.6, 644.0)
DEMO = Path("/dev/shm/poring-lab-demo")
HELD_OUT = {  # sessions the T2 templates were NOT cut from; frames: open ..., closed ...
    "20261009T154802-demo-talk-cal-guide": ("0000", "0026", "0053", "0054", "0059"),
    "20261009T160329-demo-talk-cal-guide": ("0000", "0011"),
}
TEMPLATES = Path(os.environ.get("NPC_DIALOG_TEMPLATES", ROOT / "data/ui_anchors/npc_dialog"))


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def um() -> ModuleType:
    return _load("ui_mask")


@pytest.fixture(scope="module")
def hs() -> ModuleType:
    return _load("hud_scene")


def dialog_state(origin: tuple[int, int] = (201, 101)) -> NpcUiState:
    d = DialogView((*origin, 278, 178), "next", (origin[0] + 233, origin[1] + 155, 42, 20), 0.5,
                   {})  # fmt: skip
    return NpcUiState(True, "ok", 0.9, dialog=d)


def menu_state() -> NpcUiState:
    m = MenuView((201, 301, 278, 118), (), (), None, False, False, False, None, (0, 0, 1, 1),
                 (0, 0, 1, 1), (0, 0, 1, 1), (0, 0, 1, 1), 0.5)  # fmt: skip
    return NpcUiState(True, "ok", 0.9, menu=m)


GONE = NpcUiState(True, "ok", 0.9)


# --- geometry ------------------------------------------------------------------------------------


def test_the_static_part_is_todays_mask_point_for_point(um: Any) -> None:
    wz, rp = um.wz, um.route_preview
    assert [n for n, _ in um.STATIC_WINDOWS] == list(wz.WINDOW_NAMES)
    assert [tuple(b) for _, b in um.STATIC_WINDOWS] == [tuple(map(float, b))
                                                        for b in rp.UI_WINDOWS]  # fmt: skip
    no_dialog = um.from_state(GONE)
    for u in range(-15, 1300, 9):
        for v in range(-15, 740, 9):
            assert um.STATIC.in_work_zone(u, v) == wz.in_work_zone(u, v), (u, v)
            assert no_dialog.in_work_zone(u, v) == wz.in_work_zone(u, v), (u, v)
            assert um.STATIC.window_at(u, v, 12) == wz.ui_window_at(u, v, 12), (u, v)


def test_the_cutin_region_holds_the_measured_guide_box(um: Any) -> None:
    br = um.CUTIN_BOTTOM_RIGHT
    assert um.inside_share(um.CUTIN_GUIDE, br) == 1.0
    assert um.inside_share(PHANTOM, um.CUTIN_GUIDE) == 1.0  # the phantom lies on the art
    assert br[2:] == (um.GAME_W, um.GAME_H)  # anchored to the bottom-right corner
    # the guide's extent from the corner (323 x 471 px), grown by CUTIN_BR_GROW
    gw, gh = um.GAME_W - um.CUTIN_GUIDE[0], um.GAME_H - um.CUTIN_GUIDE[1]
    assert (gw, gh) == (323, 471)
    assert (um.GAME_W - br[0], um.GAME_H - br[1]) == (round(1.25 * gw), round(1.25 * gh))
    # it never reaches our character (its feet at the screen centre, ~(640, 362))
    assert br[0] > 640 + 200
    assert [n for n, _ in um.CUTIN_REGIONS] == ["cutin_bottom_right"]


def test_a_masked_cutin_leaves_the_work_zone_with_the_margin(um: Any) -> None:
    open_ = um.from_state(dialog_state())
    closed = um.from_state(GONE)
    u, v = (PHANTOM[0] + PHANTOM[2]) / 2, (PHANTOM[1] + PHANTOM[3]) / 2
    assert open_.window_at(u, v) == "cutin_bottom_right" and not open_.in_work_zone(u, v)
    assert closed.window_at(u, v) is None and closed.in_work_zone(u, v)
    x0, y0 = um.CUTIN_BOTTOM_RIGHT[:2]
    m = um.wz.MARGIN_PX
    assert not open_.in_work_zone(x0 - m, 400) and open_.in_work_zone(x0 - m - 1, 400)
    assert not open_.in_work_zone(1000, y0 - m) and open_.in_work_zone(1000, y0 - m - 1)
    # the static windows stay masked either way
    assert open_.window_at(100, 100) == closed.window_at(100, 100) == "basic_info"


# --- the fail-closed rule ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "cutin", "why"),
    [
        (None, True, "unreadable:no_state"),
        (NpcUiState(False, "npc_dialog_uncertain", 0.0), True, "unreadable:npc_dialog_uncertain"),
        (NpcUiState(False, "no_templates: npc_dialog", 0.0), True,
         "unreadable:no_templates: npc_dialog"),
        (NpcUiState(False, "button_unknown", 0.0), True, "unreadable:button_unknown"),
        ("dialog", True, "dialog_open"),
        ("menu", True, "dialog_open"),
        (GONE, False, "no_dialog"),
    ],
)  # fmt: skip
def test_only_a_certain_no_dialog_unmasks_the_cutin(um: Any, state: Any, cutin: bool,
                                                    why: str) -> None:  # fmt: skip
    st = dialog_state() if state == "dialog" else menu_state() if state == "menu" else state
    m = um.from_state(st)
    assert (m.cutin, m.why) == (cutin, why)
    assert bool(m.cutin_regions) == cutin
    assert m.dialog_seen == (why == "dialog_open")  # a positive read, not fail-closed


def test_read_mask_fails_closed_without_templates_or_on_a_reader_error(
    um: Any, monkeypatch: Any
) -> None:
    frame = np.zeros((720, 1280, 3), np.uint8)
    monkeypatch.setattr(um, "load_dialog_templates", lambda *a, **k: None)
    m, st = um.read_mask(frame)
    assert (m.cutin, m.why, st) == (True, "unreadable:no_templates", None)

    def boom(*_: Any) -> Any:
        raise RuntimeError("reader failed")

    m, st = um.read_mask(frame, templates=object(), reader=boom)
    assert (m.cutin, m.why, st) == (True, "unreadable:RuntimeError", None)
    m, st = um.read_mask(frame, templates=object(), reader=lambda *_: GONE)
    assert (m.cutin, m.why) == (False, "no_dialog") and st is GONE


def test_missing_template_files_fail_closed(um: Any, tmp_path: Path) -> None:
    um._templates.pop(str(tmp_path), None)
    assert um.load_dialog_templates(tmp_path) is None  # no params.json: not loadable
    # the real reader with an EMPTY template set: not ok (no_templates) -> masked
    from poring_env.npc_dialog import DialogTemplates

    m, st = um.read_mask(np.zeros((720, 1280, 3), np.uint8), templates=DialogTemplates({}))
    assert m.cutin and m.why.startswith("unreadable:no_templates") and not st.ok


# --- detections ----------------------------------------------------------------------------------


def test_detections_inside_a_masked_cutin_are_ui_and_nothing_else_is(um: Any) -> None:
    open_, closed = um.from_state(dialog_state()), um.from_state(GONE)
    x0 = um.CUTIN_BOTTOM_RIGHT[0]
    straddle_40 = (x0 - 30, 400, x0 + 20, 440)  # 40 % inside: a unit partly behind the edge
    straddle_60 = (x0 - 20, 400, x0 + 30, 440)  # 60 % inside
    over_window = (20, 20, 60, 60)  # the static windows never drop a detection (as before)
    boxes = [PHANTOM, straddle_40, straddle_60, over_window, (600, 300, 640, 360)]
    kept, masked = open_.split(boxes)
    assert masked == [PHANTOM, straddle_60]
    assert kept == [straddle_40, over_window, (600, 300, 640, 360)]
    assert closed.split(boxes) == (boxes, [])
    assert um.STATIC.split(boxes) == (boxes, [])
    # the shapes the callers hold: hud_scene's dicts and the detector's Box objects
    from types import SimpleNamespace

    det = SimpleNamespace(x0=PHANTOM[0], y0=PHANTOM[1], x1=PHANTOM[2], y1=PHANTOM[3])
    assert open_.split([{"box": list(PHANTOM)}, det]) == ([], [{"box": list(PHANTOM)}, det])


# --- CutinWatch: read only when needed, reuse while the region looks the same --------------------


class Reader:
    def __init__(self, state: Any = None) -> None:
        self.state = state if state is not None else dialog_state((205, 99))
        self.calls: list[Any] = []

    def __call__(self, frame: Any, templates: Any, hints: Any) -> Any:
        self.calls.append(hints)
        if isinstance(self.state, Exception):
            raise self.state
        return self.state


def test_the_watch_reads_only_when_something_lies_over_the_cutin(um: Any) -> None:
    now = [100.0]
    rd = Reader()
    w = um.CutinWatch(templates=object(), reader=rd, clock=lambda: now[0])
    frame = np.full((720, 1280, 3), 90, np.uint8)
    kept, masked, m = w.filter(frame, [(300, 300, 340, 360)])
    assert (kept, masked, m.why, rd.calls) == ([(300, 300, 340, 360)], [], "not_read", [])
    assert w.stats["skipped"] == 1
    kept, masked, m = w.filter(frame, [PHANTOM, (300, 300, 340, 360)])
    assert masked == [PHANTOM] and m.why == "dialog_open" and len(rd.calls) == 1
    assert rd.calls[0] is None  # no hint before the first read
    # the same region again: the read is reused
    w.filter(frame, [PHANTOM])
    assert len(rd.calls) == 1 and w.stats["reused"] == 1
    # a drawn box over the region makes a read needed too (the HUD's objects)
    w2 = um.CutinWatch(templates=object(), reader=Reader(GONE), clock=lambda: now[0])
    _, _, m2 = w2.filter(frame, [], also=[PHANTOM])
    assert m2.why == "no_dialog" and w2.stats["reads"] == 1
    # only what a read can change: a box under half inside is kept either way, so no read
    x0 = um.CUTIN_BOTTOM_RIGHT[0]
    w3 = um.CutinWatch(templates=object(), reader=Reader(), clock=lambda: now[0])
    assert w3.filter(frame, [(x0 - 30, 400, x0 + 20, 440)])[2].why == "not_read"
    # a gate's click point: inside the region grown by its margin
    assert w3.lazy(frame, points=[(x0 - 13, 400)], margin=12).why == "not_read"
    assert w3.lazy(frame, points=[(x0 - 12, 400)], margin=12).why == "dialog_open"
    assert (w3.stats["reads"], w3.stats["skipped"]) == (1, 2)


def test_the_watch_rereads_when_the_region_changes_or_the_read_ages(um: Any) -> None:
    now = [100.0]
    rd = Reader()
    w = um.CutinWatch(templates=object(), reader=rd, clock=lambda: now[0])
    frame = np.full((720, 1280, 3), 90, np.uint8)
    w.mask(frame)
    small = frame.copy()
    small[600:640, 980:1030] = 200  # a unit-sized change in the region: below REGION_CHANGE
    w.mask(small)
    assert len(rd.calls) == 1
    art = frame.copy()
    x0, y0, x1, y1 = (int(c) for c in um.CUTIN_GUIDE)
    art[y0:y1, x0:x1] = 30  # a cut-in appearing: ~45 % of the region changes by 60 levels
    w.mask(art)
    assert len(rd.calls) == 2
    assert rd.calls[1] == {"npc_dialog": (205, 99)}  # the last place is the hint
    now[0] += um.MAX_AGE_S + 0.01
    w.mask(art)
    assert len(rd.calls) == 3 and w.stats["reads"] == 3 and len(w.stats["read_ms"]) == 3


def test_the_watch_fails_closed(um: Any) -> None:
    frame = np.zeros((720, 1280, 3), np.uint8)
    w = um.CutinWatch(templates=object(), reader=Reader(RuntimeError("x")))  # type: ignore[arg-type]
    kept, masked, m = w.filter(frame, [PHANTOM])
    assert (kept, masked, m.cutin, m.why) == ([], [PHANTOM], True, "unreadable:RuntimeError")
    w = um.CutinWatch(templates=object(), reader=Reader(NpcUiState(False, "row_background", 0)))
    assert w.filter(frame, [PHANTOM])[1] == [PHANTOM]


# --- the HUD's filter on a synthetic scene -------------------------------------------------------


def unit(cls: str, box: tuple[float, ...], conf: float = 0.8) -> dict[str, Any]:
    return {"kind": "unit", "cls": cls, "conf": conf, "box": list(box)}


def two_passes(t: Any, found: list[dict[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    """Two detector passes on the same view (seen twice: a new unit is drawn on the second)."""
    out = [t.observe(found, t.offset.copy(), **kw), t.observe(found, t.offset.copy(), **kw)]
    return [d for d in out if d is not None]


def test_the_hud_never_draws_a_cutin_phantom_while_a_dialog_is_open(um: Any, hs: Any) -> None:
    br = [um.CUTIN_BOTTOM_RIGHT]
    phantom, npc = unit("monster", PHANTOM, 0.31), unit("npc", (685, 330, 715, 400))
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    deltas = two_passes(t, [phantom, npc], masked=br)
    added = [o for d in deltas for o in d["add"]]
    assert [o["cls"] for o in added] == ["npc"]  # the real unit is drawn, the phantom never
    assert not [c for c in t.candidates.values() if c.cls == "monster"]
    # the positive case: without the mask the same detections draw the phantom
    t2 = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    added2 = [o for d in two_passes(t2, [phantom, npc]) for o in d["add"]]
    assert sorted(o["cls"] for o in added2) == ["monster", "npc"]


def test_the_hud_removes_a_drawn_box_once_the_cutin_is_masked(um: Any, hs: Any) -> None:
    br = [um.CUTIN_BOTTOM_RIGHT]
    phantom, npc = unit("monster", PHANTOM, 0.31), unit("npc", (685, 330, 715, 400))
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    two_passes(t, [phantom, npc])  # drawn before the mask applied (e.g. an unreadable moment)
    ids = {o.cls: i for i, o in t.objects.items() if o.anchor == "world"}
    d = t.observe([phantom, npc], t.offset.copy(), masked=br)
    assert d is not None and d["remove"] == [ids["monster"]] and not d["add"]
    assert ids["npc"] in t.objects and ids["monster"] not in t.objects
    # a candidate (seen once) inside the region goes silently
    t3 = hs.SceneTracker(REGION, DESKTOP, WINDOWS)
    t3.observe([phantom], t3.offset.copy())
    assert len(t3.candidates) == 1
    assert t3.observe([], t3.offset.copy(), masked=br) is None and not t3.candidates


def test_the_hud_judges_a_drawn_box_where_the_frame_shows_it(um: Any, hs: Any) -> None:
    """A box drawn at offset 0 that the scene's motion carried into the region is removed; one the
    motion carried out of it stays."""
    br = [um.CUTIN_BOTTOM_RIGHT]
    t = hs.SceneTracker(REGION, DESKTOP, WINDOWS)  # global motion (no floor model)
    two_passes(t, [unit("npc", (500, 300, 540, 370))])
    (i,) = [i for i, o in t.objects.items() if o.anchor == "world"]
    assert t.world_rects(t.offset.copy()) == [(500.0, 300.0, 540.0, 370.0)]
    assert t.observe([], t.offset.copy(), masked=br) is None  # still outside: nothing
    t.motion((500.0, 250.0))  # the scene scrolled: the NPC is now drawn at (1000, 550)
    assert t.world_rects(t.offset.copy()) == [(1000.0, 550.0, 1040.0, 620.0)]
    d = t.observe([], t.offset.copy(), masked=br)
    assert d is not None and d["remove"] == [i]


# --- offline: the banked guide frames (held-out sessions; skipped where they are absent) --------


def _banked() -> list[tuple[str, Path, bool]]:
    if not (TEMPLATES / "params.json").exists():
        pytest.skip(f"no T2 templates at {TEMPLATES} (NPC_DIALOG_TEMPLATES)")
    um = sys.modules.get("ui_mask") or _load("ui_mask")
    out = []
    for name, picks in HELD_OUT.items():
        if not (DEMO / name / "frames").is_dir():
            pytest.skip(f"banked session {name} is not in {DEMO}")
        for _, p, lab in um._labelled_frames(DEMO / name):
            if p.name[:4] in picks:
                assert lab is not None
                out.append((name, p, bool(lab.dialog or lab.menu)))
    return out


def test_banked_guide_frames_the_cutin_phantom_is_masked_on_every_open_frame(um: Any) -> None:
    """On held-out RDP frames of the prontera guide's dialog: the reader agrees with the packets,
    and every unit box the detector draws over the cut-in is masked while the dialog is open. The
    CPU detector runs when it is available (2 threads, a handful of frames); without it the
    detector's recorded phantom box stands in on the open frames."""
    import talk_calibrate as tc

    from poring_env import npc_dialog as nd

    frames = _banked()
    t = nd.load_templates(TEMPLATES)
    det: Any = None
    try:
        import unit_detector

        det = unit_detector.UnitDetector(threads=2)
    except Exception:  # noqa: BLE001 -- recorded boxes instead (said in the docstring)
        det = None
    opened = closed = 0
    try:
        for name, path, is_open in frames:
            frame = tc.load_frame(path)
            m, st = um.read_mask(frame, t)
            assert st is not None and st.ok, (name, path.name, m.why)
            assert m.why == ("dialog_open" if is_open else "no_dialog"), (name, path.name)
            if det is not None:
                boxes = [(b.x0, b.y0, b.x1, b.y1) for b in det.detect(frame) if b.cls != "player"]
            else:
                boxes = [PHANTOM] if is_open else []
            over = [b for b in boxes if um.inside_share(b, um.CUTIN_GUIDE) > 0]
            if is_open:
                opened += 1
                assert over, (name, path.name, "the phantom was expected on an open frame")
                assert all(m.masking(b) for b in over), (name, path.name, over)
            else:
                closed += 1
                assert not m.cutin and not over, (name, path.name, over)
    finally:
        if det is not None:
            det.close()
    assert opened >= 4 and closed >= 2
