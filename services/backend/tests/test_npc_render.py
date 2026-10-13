"""scripts/npc_render.py (the NPC render path, Batt 2026-10-13) and npc_render_measure.py's pure
parts, on SYNTHETIC sprites, KBs, input logs and frames built here, and the committed camera fits
(real sprites, GATs and L3 data are client / GPL data and never enter the repository)."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str) -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


nr = _load("npc_render")
nm = _load("npc_render_measure")

from poring_dataset import camera as cm  # noqa: E402
from poring_dataset import render as rd  # noqa: E402
from poring_dataset.sprites import Act, Layer, Motion, Spr  # noqa: E402

CAM_JSON = cm.load_camera_json(ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
OUT = cm.map_camera(CAM_JSON, "town", frozenset())
ME = (100.0, 100.0)


def body(h: int, w: int, value: int = 200) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = value
    img[2:, 1:-1, 3] = 255  # a margin row / column left transparent
    rng = np.random.default_rng(w)  # a texture of its own per frame, so frames never alias
    img[2:, 1:-1, 0] = rng.integers(40, 250, (h - 2, w - 2), dtype=np.uint8)
    return img


def sheet(frames: int = 2) -> rd.SpriteSheet:
    """One idle group x 8 directions; motion m is a body 8 + 4 m px wide (the union is the widest)
    and 30 px tall, standing on the anchor."""
    images = tuple(body(30, 8 + 4 * m, 120 + 20 * m) for m in range(frames))
    acts = tuple(
        tuple(
            Motion((Layer(0, -15, m, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, None, None),))
            for m in range(frames)
        )
        for _ in range(8)
    )
    return rd.SpriteSheet(Act((2, 5), acts, (), (4.0,) * 8), Spr((2, 1), images, len(images), None))


SHEET = sheet()


def sheets(job: int) -> tuple[str, rd.SpriteSheet] | None:
    return ("synthetic", SHEET) if job == 46 else None


sheets.stems = {46: "synthetic", 47: "missing"}  # type: ignore[attr-defined]


def npc(
    cell: tuple[int, int],
    sprite: int = 46,
    drawn: Any = True,
    dir_: int | None = 4,
    sprite_class: str | None = "npc",
) -> Any:
    return nr.L3Npc(f"npc/a.txt:{cell[0]}", "town", cell, dir_, sprite, drawn, sprite_class)


def scene() -> rd.Scene:
    assert OUT is not None
    return rd.Scene(OUT, ME)


# --- the render -----------------------------------------------------------------------------------


def test_a_drawn_npc_is_rendered_as_the_union_of_its_idle_frames() -> None:
    res = nr.render_scene([npc((102, 100))], scene(), sheets, nr.DEFAULT_K)
    assert len(res.rendered) == 1 and res.complete
    r = res.rendered[0]
    s = r.pred.scale
    assert r.motions == 2 and r.pred.motion is None and not r.pred.phase_known  # the envelope
    # the widest frame (10 opaque px of 12) sets the box; 28 opaque rows stand on the anchor
    assert r.box[2] - r.box[0] == pytest.approx(10 * s, abs=1.0)
    assert r.box[3] - r.box[1] == pytest.approx(28 * s, abs=1.0)
    au, av = r.pred.anchor_px
    assert r.contains(au, av - 10 * s) and r.in_box(au, av - 10 * s)
    assert not r.contains(au + 20 * s, av - 10 * s) and r.distance(au + 20 * s, av - 10 * s) > 0
    assert res.hits(au, av - 10 * s) == [r] and res.hits(au + 200, av) == []


def test_the_provisional_hit_box_is_wider_than_the_drawn_sprite() -> None:
    res = nr.render_scene([npc((102, 100))], scene(), sheets)
    r = res.rendered[0]
    au, av = r.pred.anchor_px
    x0, y0, x1, y1 = r.hit_box()
    assert (x0, x1) == (au - nr.HIT_HALF_W, au + nr.HIT_HALF_W)
    assert (y0, y1) == (r.box[1] - nr.HIT_TOP, av + nr.HIT_BELOW)
    beside = (au + 30.0, av - 10.0)  # outside the slim drawn body, inside the clickable box
    assert not r.contains(*beside) and r.in_hit_box(*beside)
    assert res.no_click(*beside) is r and res.no_click(au + 60.0, av) is None
    assert res.no_click(au, av + 12.0) is r and res.no_click(au, av + 30.0) is None


def test_fail_closed_unsupported_conditional_and_undrawn_npcs() -> None:
    npcs = [
        npc((102, 100)),
        npc((98, 100), dir_=None),
        npc((96, 100), sprite=47),
        npc((95, 100), sprite=48),
        npc((104, 100), drawn="conditional"),
        npc((106, 100), drawn=False),
        npc((108, 100), sprite=45),
        npc((101, 98), sprite_class="hidden"),
    ]
    res = nr.render_scene(npcs, scene(), sheets)
    assert [r.npc.cell for r in res.rendered] == [(102, 100)]
    assert [n.cell for n in res.conditional] == [(104, 100)]  # listed apart, never rendered
    assert sorted(n.cell for n in res.undrawn) == [(101, 98), (106, 100), (108, 100)]
    why = {n.cell: w for n, w, _a in res.unsupported}
    assert why == {
        (98, 100): "no_facing",
        (96, 100): "sprite_files_missing",
        (95, 100): "not_in_sprite_table",
    }
    assert not res.complete and len(res.unsupported_near()) == 3
    summary = res.summary()
    assert summary["complete"] is False and summary["unsupported_far"] == 0
    assert {u["why"] for u in summary["unsupported_near"]} == set(why.values())


def test_an_unsupported_npc_beyond_the_area_does_not_block_one_inside_does() -> None:
    res = nr.render_scene([npc((102, 100)), npc((180, 100), dir_=None)], scene(), sheets)
    assert [n.cell for n in res.beyond_area] == [(180, 100)]  # never sent, never drawn
    assert res.complete and not res.unsupported
    # 10 cells east is inside the area and on screen (~340 px right of us): it blocks
    res = nr.render_scene([npc((102, 100)), npc((110, 100), dir_=None)], scene(), sheets)
    assert not res.complete and res.unsupported_near()[0][1] == "no_facing"


def test_an_npc_beyond_the_server_area_is_not_drawn_even_on_screen() -> None:
    near, beyond = npc((100 + nr.AREA_SIZE, 100)), npc((100, 100 + nr.AREA_SIZE + 1))
    res = nr.render_scene([near, beyond], scene(), sheets)
    assert [r.npc.cell for r in res.rendered] == [near.cell]
    assert res.beyond_area == [beyond]
    lifted = nr.render_scene([near, beyond], scene(), sheets, area=None)
    assert sorted(r.npc.cell for r in lifted.rendered) == sorted([near.cell, beyond.cell])


def test_the_script_facing_turns_the_drawn_direction() -> None:
    a = nr.render_scene([npc((102, 100), dir_=4)], scene(), sheets).rendered[0]
    b = nr.render_scene([npc((102, 100), dir_=0)], scene(), sheets).rendered[0]
    assert a.pred.direction == cm.displayed_direction(4, OUT.yaw)  # type: ignore[union-attr]
    assert b.pred.direction != a.pred.direction


def kb_dir(tmp: Path, maps: dict[str, Any], complete: bool = True) -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "first_workflow.json").write_text(json.dumps({"maps": maps}))
    (tmp / "npc_cells.json").write_text(
        json.dumps({"maps": {m: {"complete": complete} for m in maps}})
    )
    return tmp


def test_render_refuses_what_it_cannot_load(tmp_path: Path) -> None:
    kb = kb_dir(
        tmp_path / "kb",
        {
            "town": {
                "npcs": [
                    {
                        "key": "npc/a.txt:1",
                        "x": 102,
                        "y": 100,
                        "dir": 4,
                        "sprite": 46,
                        "drawn": True,
                    }
                ]
            }
        },
    )
    gat = tmp_path / "gat"
    gat.mkdir()
    with pytest.raises(nr.Unsupported) as e:
        nr.render("town", ME, "vnc", kb_dir=kb, sheets=sheets, gat_dir=gat)
    assert e.value.reason == "camera_path_unknown"
    with pytest.raises(nr.Unsupported) as e:
        nr.render("town", ME, "rdp", kb_dir=kb, sheets=sheets, gat_dir=gat, camera_json={})
    assert e.value.reason == "camera_missing"
    with pytest.raises(nr.Unsupported) as e:
        nr.render("elsewhere", ME, "rdp", kb_dir=kb, sheets=sheets, gat_dir=gat)
    assert e.value.reason == "map_not_in_kb"
    with pytest.raises(nr.Unsupported) as e:
        nr.render("town", ME, "rdp", kb_dir=kb, sheets=sheets, gat_dir=gat)
    assert e.value.reason == "gat_missing"
    (gat / "town.gat").write_bytes(b"")
    with pytest.raises(nr.Unsupported) as e:
        nr.render("town", ME, "s2", kb_dir=kb, sheets=sheets, gat_dir=gat)
    assert e.value.reason == "indoor_table_missing"


def test_l3_reads_the_facing_and_the_completeness_flag(tmp_path: Path) -> None:
    kb = kb_dir(
        tmp_path,
        {
            "town": {
                "npcs": [
                    {
                        "key": "npc/a.txt:1",
                        "x": 5,
                        "y": 6,
                        "dir": 2,
                        "sprite": 46,
                        "drawn": "conditional",
                    },
                    {"key": "npc/a.txt:2", "x": 7, "y": 8, "sprite": 47, "drawn": True},
                ]
            }
        },
        complete=False,
    )
    npcs, complete = nr.l3_npcs("town", kb)
    assert [(n.cell, n.dir, n.drawn) for n in npcs] == [
        ((5, 6), 2, "conditional"),
        ((7, 8), None, True),
    ]
    assert complete is False


# --- template matching ----------------------------------------------------------------------------


def paste(frame: np.ndarray, r: Any, dx: int, dy: int, motion: int = 1) -> None:
    """Draw the rendered motion into the frame, shifted by (dx, dy)."""
    i0, j0 = math.floor(r.box[0]), math.floor(r.box[1])
    i1, j1 = math.ceil(r.box[2]), math.ceil(r.box[3])
    grey, opaque = nr.rendered_grey(SHEET, r.pred, motion, (i0, j0, i1, j1))
    sub = frame[j0 + dy : j1 + dy, i0 + dx : i1 + dx]
    sub[opaque] = np.clip(grey[opaque], 0, 255)[:, None].astype(np.uint8)


def test_match_offset_finds_a_shifted_sprite() -> None:
    r = nr.render_scene([npc((102, 100))], scene(), sheets).rendered[0]
    rng = np.random.default_rng(20261013)
    frame = rng.integers(0, 60, (720, 1280, 3), dtype=np.uint8)
    paste(frame, r, 5, -3)
    m = nr.match_offset(frame, SHEET, r.pred, radius=12)
    assert m is not None and (m.dx, m.dy, m.motion) == (5, -3, 1) and m.score > 0.95
    assert m.score_at_zero is not None and m.score_at_zero < 0.5 and not m.edge
    far = nr.match_offset(frame, SHEET, r.pred, radius=2)  # the true offset is outside
    assert far is not None and far.score < 0.5  # never a confident match
    one = nr.match_offset(frame, sheet(1), r.pred, radius=12)  # a 1-frame sheet: motion 0 only
    assert one is not None and one.motion == 0 and one.score < 0.9


def test_masked_ncc_is_one_on_the_template_and_ignores_brightness() -> None:
    rng = np.random.default_rng(1)
    t = rng.random((6, 5))
    mask = np.ones((6, 5), bool)
    mask[0, 0] = False
    img = rng.random((20, 20))
    img[7:13, 4:9] = 2.0 * t + 3.0  # the same pattern, brighter and with more contrast
    ncc = nr.masked_ncc(img, t, mask)
    assert ncc.shape == (15, 16)
    assert np.unravel_index(int(np.nanargmax(ncc)), ncc.shape) == (7, 4)
    assert ncc[7, 4] == pytest.approx(1.0)


# --- the camera-state guard -----------------------------------------------------------------------


def match(dx: int, dy: int, score: float = 0.8, edge: bool = False) -> Any:
    return nr.Match(dx, dy, score, None, 0, edge)


def test_pixel_camera_check() -> None:
    assert nr.pixel_camera_check([match(1, -1), match(0, 2), None])[0] == "default"
    assert nr.pixel_camera_check([match(1, -1), match(30, 4)])[0] == "off"
    assert nr.pixel_camera_check([match(1, -1), match(30, 4, score=0.2)])[0] == "unknown"
    assert nr.pixel_camera_check([match(1, 0), match(0, 0, edge=True)])[0] == "unknown"


def rec(t: int, event: dict[str, Any], accepted: bool = True) -> dict[str, Any]:
    return {"t_mono_ns": t, "accepted": accepted, "source": "human", "event": event}


def test_camera_log_rotation_resets_on_a_map_change_zoom_does_not() -> None:
    evs = nr.camera_events(
        [
            rec(10, {"type": "mouse_button", "button": "right", "action": "down"}),
            rec(11, {"type": "mouse_button", "button": "right", "action": "up"}),
            rec(12, {"type": "mouse_button", "button": "left", "action": "down"}),
            rec(
                13, {"type": "wheel", "dy": 1}, accepted=False
            ),  # dropped: never reached the client
        ]
    )
    assert [e.kind for e in evs] == ["rotate"]
    log = nr.CameraLog(evs, map_changes=[50])
    assert log.state_at(5)[0] == "default"
    assert log.state_at(20)[0] == "rotated" and log.state_at(60)[0] == "default"
    zoom = nr.CameraLog(nr.camera_events([rec(70, {"type": "wheel", "dy": -2})]), [50, 90])
    assert zoom.state_at(100)[0] == "zoomed"  # fail closed: no known reset


def test_read_input_window_reads_only_the_window(tmp_path: Path) -> None:
    path = tmp_path / "2026-10-13.jsonl"
    with path.open("w") as fh:
        for i in range(5000):
            fh.write(
                json.dumps(
                    {
                        "t_mono_ns": 1_000_000_000 * i,
                        "t_wall": "x",
                        "source": "bot",
                        "accepted": True,
                        "event": {"type": "mouse_move"},
                    }
                )
                + "\n"
            )
    got = nr.read_input_window(path, 2_000_000_000_000, 2_010_000_000_000, slack_ns=0)
    assert [r["t_mono_ns"] // 1_000_000_000 for r in got] == list(range(2000, 2011))
    assert nr.read_input_window(path, 0, 0, slack_ns=0)[0]["t_mono_ns"] == 0


# --- npc_render_measure's pure parts --------------------------------------------------------------


def test_box_distance_and_dilation_curve() -> None:
    assert nm.box_distance((0, 0, 10, 10), 5, 5) == 0.0
    assert nm.box_distance((0, 0, 10, 10), 13, 14) == pytest.approx(5.0)
    rows = [
        {"label": "talk", "d": 0.0},
        {"label": "talk", "d": 6.0},
        {"label": "walk", "d": 3.0},
        {"label": "noentry", "d": 40.0},
        {"label": "none", "d": 0.0},
    ]
    curve = {c["d_px"]: c for c in nm.dilation_curve(rows, "d")}
    assert (curve[0]["talk_covered"], curve[0]["other_inside"]) == (1, 0)
    assert (curve[4]["talk_covered"], curve[4]["other_inside"]) == (1, 1)
    assert (curve[8]["talk_share"], curve[8]["other_n"]) == (1.0, 2)  # "none" is not counted


def test_grab0_labels_and_probes(tmp_path: Path) -> None:
    items = tmp_path / "items.json"
    labels = tmp_path / "labels.json"
    items.write_text(json.dumps([["s", "crops/1.npz", 0], ["s", "crops/1.npz", 3]]))
    labels.write_text(json.dumps({"0": "talk", "1": "walk"}))
    assert nm.grab0_labels(items, labels) == {
        ("s", "crops/1.npz", 0): "talk",
        ("s", "crops/1.npz", 3): "walk",
    }
    ev = {
        "at": [10.0, 20.0],
        "kind": "sprite",
        "stand": [1, 2],
        "npc_cell": [3, 4],
        "crop": "crops/1.npz",
        "reads": [{"g": 0, "t_ns": 77}],
    }
    lines = [
        {"rule": nm.PROBE_RULE, "t_mono_ns": 5, "outcome": {"evidence": ev}},
        {"rule": "other", "t_mono_ns": 6, "outcome": {"evidence": ev}},
    ]
    (tmp_path / "demo.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    got = list(nm.probes(tmp_path))
    assert got == [
        {
            "t_ns": 77,
            "at": [10.0, 20.0],
            "kind": "sprite",
            "stand": [1, 2],
            "npc_cell": [3, 4],
            "crop": "crops/1.npz",
        }
    ]


def test_standing_cell_needs_the_same_whole_cell_before() -> None:
    worlds = {
        0: ("town", (5.0, 6.0)),
        500_000_000: ("town", (5.0, 6.0)),
        1_000_000_000: ("town", (5.5, 6.0)),
        1_500_000_000: ("town", (6.0, 6.0)),
    }

    class Sess:
        def world(self, t: int) -> Any:
            m, pos = worlds.get(t, ("town", (6.0, 6.0)))
            return SimpleNamespace(map=m, self_pos=pos)

    assert nm.standing_cell(Sess(), 500_000_000) == ("town", (5, 6))
    assert nm.standing_cell(Sess(), 1_000_000_000) is None  # mid-step
    assert nm.standing_cell(Sess(), 1_500_000_000) is None  # it just arrived


def test_linear_fit_and_stats_recover_a_shift_that_grows_to_the_right() -> None:
    rows = [
        {"u": u, "v": 360.0, "dx": 2.0 + 0.01 * (u - 640.0), "dy": -1.0}
        for u in np.linspace(100, 1200, 12)
    ]
    fit = nm.linear_fit(rows, "dx")
    assert fit is not None and fit["a_px"] == pytest.approx(2.0) and fit["b_per_100px_u"] == 1.0
    st = nm.dist_stats([{"dx": 1, "dy": 0}, {"dx": 0, "dy": 7}])
    assert (st["n"], st["within_3px"], st["within_12px"]) == (2, 0.5, 1.0)
    assert nm.pick(list(range(10)), 3) == [0, 4, 9]
