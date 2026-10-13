"""scripts/label_quality.py (Batt 2026-10-13, decision 11): the auto-labels against the hand-checked
gold set, gap by gap. SYNTHETIC boxes and units only -- never client pixels or recorded sessions
(CLAUDE.md rule 4)."""

import importlib.util
import io
import json
import random
import sys
import tarfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # the dataclasses resolve their annotations through it
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def lq() -> ModuleType:
    return load("label_quality")


def b(cls: str, x1: float, y1: float, x2: float, y2: float, gid: int | None = None) -> dict:
    return {"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "gid": gid}


def unit(
    cls: str,
    foot: tuple[float, float],
    *,
    sprite: tuple[float, float, float, float] | None = None,
    state: str = "idle",
    scale: float = 1.0,
) -> dict[str, Any]:
    """A unit's facts as frame_facts writes them: v0's class box hanging from the foot point, and
    (monsters) a v1 sprite box = foot + scale * sprite extent."""
    u, v = foot
    w, h = {"monster": (44.0, 40.0), "npc": (34.0, 74.0), "player": (34.0, 74.0)}[cls]
    e: dict[str, Any] = {
        "cls": cls,
        "hidden": False,
        "drawn": True,
        "foot_px": [u, v],
        "v0_box": [u - w / 2, v - h, u + w / 2, v],
        "state": state,
        "sheet": sprite is not None,
    }
    if sprite is not None:
        x0, y0, x1, y1 = sprite
        e["v1_pred"] = {
            "box": [u + scale * x0, v + scale * y0, u + scale * x1, v + scale * y1],
            "anchor_px": [u, v],
            "scale": scale,
            "extent": list(sprite),
            "motion_extents": [list(sprite)],
            "idle_extent": [-20.0, -30.0, 20.0, 10.0],
            "phase_known": False,
        }
    return e


# --- the matching is label_iou's, pair for pair --------------------------------------------------


def test_score_reproduces_label_iou_on_random_boxes(lq: ModuleType) -> None:
    li = load("label_iou")
    rng = random.Random(20261013)
    frames, auto = [], {}
    for t in range(40):
        hand = []
        for _ in range(rng.randint(0, 6)):
            cls = rng.choice(["monster", "npc", "player"])
            x, y = rng.uniform(0, 1200), rng.uniform(0, 650)
            hand.append(b(cls, x, y, x + 44, y + 40))
        pred = []
        for h in hand:
            if rng.random() < 0.8:
                dx, dy, s = rng.uniform(-25, 25), rng.uniform(-25, 25), rng.uniform(0.7, 1.5)
                cx, cy = (h["x1"] + h["x2"]) / 2 + dx, (h["y1"] + h["y2"]) / 2 + dy
                pred.append(b(h["cls"], cx - 22 * s, cy - 20 * s, cx + 22 * s, cy + 20 * s))
        if rng.random() < 0.3:
            pred.append(b("monster", 600, 300, 640, 340))
        frames.append({"frame_id": t, "t_mono_ns": t, "hand": hand, "v1": pred})
        auto[t] = pred
    hand_doc = {"frames": [{"t_mono_ns": f["t_mono_ns"], "boxes": f["hand"]} for f in frames]}
    for metric, theirs in (("iou", li.score), ("position", li.score_position)):
        ours = lq.score(frames, lambda f: f["v1"], metric)
        ref = theirs(hand_doc, lambda t: auto[t])
        for c in ("player", "monster", "npc"):
            for key in ("tp", "fp", "fn", "precision", "recall"):
                assert ours["per_class"][c][key] == ref["per_class"][c][key], (metric, c, key)
        assert ours["overall"] == {k: ref["overall"][k] for k in ours["overall"]}


def test_pair_geometry_is_auto_minus_hand(lq: ModuleType) -> None:
    g = lq.pair_geometry((100.0, 100.0, 144.0, 140.0), (102.0, 90.0, 162.0, 150.0))
    assert g["dx"] == pytest.approx(10.0) and g["dy"] == pytest.approx(0.0)
    assert g["d_bottom"] == pytest.approx(10.0) and g["d_top"] == pytest.approx(-10.0)
    assert g["w_ratio"] == pytest.approx(60 / 44) and g["h_ratio"] == pytest.approx(60 / 40)
    assert g["iou"] == pytest.approx(42 * 40 / (44 * 40 + 60 * 60 - 42 * 40))
    assert g["centre_in"] is True


def test_provenance_reads_what_batt_did_to_the_shown_box(lq: ModuleType) -> None:
    shown = [
        b("monster", 0, 0, 44, 40, gid=1),
        b("monster", 100, 0, 144, 40, gid=2),
        b("monster", 200, 0, 244, 40, gid=3),
    ]
    assert lq.provenance(b("monster", 0, 0, 44, 40, gid=1), shown) == "accepted"
    assert lq.provenance(b("monster", 100, 12, 144, 52, gid=2), shown) == "moved"
    assert lq.provenance(b("monster", 200, 0, 260, 46, gid=3), shown) == "resized"
    assert lq.provenance(b("monster", 300, 0, 344, 40), shown) == "added"
    assert lq.provenance(b("monster", 0, 0, 44, 40, gid=9), shown) == "added"
    assert lq.provenance(b("monster", 0, 0, 44, 40, gid=1), None) == "unknown"


def test_link_unit_takes_the_gid_else_the_nearest_unit_within_reach(lq: ModuleType) -> None:
    f = {
        "entities": {
            "7": unit("monster", (100, 100)),
            "8": unit("monster", (300, 100)),
            "9": unit("npc", (110, 100)),
        }
    }
    assert lq.link_unit(b("monster", 0, 0, 1, 1, gid=8), f) == ("8", 0.0)
    gid, d = lq.link_unit(b("monster", 80, 70, 120, 110), f)  # v0 centre of 7: (100, 80)
    assert gid == "7" and d == pytest.approx(10.0)
    assert lq.link_unit(b("monster", 500, 500, 544, 540), f) == (None, None)


# --- relabel: the labels re-derived from the unit facts, with each knob --------------------------


def frame_with_units() -> dict[str, Any]:
    ents = {
        "1": unit("monster", (640, 300), sprite=(-25.0, -40.0, 25.0, 12.0), scale=1.2),
        "2": unit("npc", (900, 400)),
        # under the chat window (0, 528, 600, 98): dropped by the UI rule
        "3": unit("monster", (300, 600), sprite=(-25.0, -40.0, 25.0, 12.0)),
        # a monster without a sprite sheet keeps v0's box
        "4": unit("monster", (800, 200)),
        # inside the minimap rectangle (1128, 8, 152, 152)
        "5": unit("monster", (1200, 100), sprite=(-25.0, -40.0, 25.0, 12.0)),
        # less than half on screen at the right edge
        "6": unit("monster", (1290, 400), sprite=(-25.0, -40.0, 25.0, 12.0)),
    }
    f: dict[str, Any] = {"frame_id": 0, "entities": ents, "self_moving": True, "hand": []}
    v1 = []
    for gid in ("1", "2", "4"):
        e = ents[gid]
        r = e["v1_pred"]["box"] if "v1_pred" in e else e["v0_box"]
        v1.append(b(e["cls"], *r, gid=int(gid)))
    f["v1"] = v1
    f["self_lag_shift"] = {"125": {g: [60.0, -5.0] for g in ents}}
    return f


def test_relabel_reproduces_the_frame_and_turns_each_knob(lq: ModuleType) -> None:
    f = frame_with_units()
    assert lq.same_boxes(lq.relabel(f, "v1"), f["v1"])
    gids = lambda boxes: sorted(x["gid"] for x in boxes)  # noqa: E731
    assert gids(lq.relabel(f, "v1", ui_off=frozenset({"chat"}))) == [1, 2, 3, 4]
    assert gids(lq.relabel(f, "v1", ui_off=frozenset({"minimap"}))) == [1, 2, 4, 5]
    moved = {x["gid"]: x for x in lq.relabel(f, "v1", lag_ms=125)}
    assert moved[1]["x1"] == pytest.approx(f["v1"][0]["x1"] + 60.0)
    assert moved[1]["y1"] == pytest.approx(f["v1"][0]["y1"] - 5.0)
    resized = {x["gid"]: x for x in lq.relabel(f, "v1", monster_box=lq.resized_box(44.0, 40.0))}
    assert resized[1]["x2"] - resized[1]["x1"] == pytest.approx(44.0)
    assert resized[4]["x2"] - resized[4]["x1"] == pytest.approx(44.0)  # v0's box: untouched


def test_walk_idle_box_only_changes_walking_units(lq: ModuleType) -> None:
    idle = unit("monster", (100, 100), sprite=(-25.0, -50.0, 25.0, 5.0), state="idle", scale=2.0)
    walk = dict(idle, state="walk")
    assert lq.walk_idle_box(idle) == tuple(idle["v1_pred"]["box"])
    assert lq.walk_idle_box(walk) == (60.0, 40.0, 140.0, 120.0)  # 100 + 2 * (-20, -30, 20, 10)


# --- causes and what-ifs -------------------------------------------------------------------------


def test_causes_name_the_self_shift_the_ui_window_and_the_deleted_box(lq: ModuleType) -> None:
    f = frame_with_units()
    m1 = f["v1"][0]
    f["hand"] = [
        b("monster", m1["x1"] + 60, m1["y1"], m1["x2"] + 60, m1["y2"], gid=1),  # shifted 60 px
        b("monster", 280, 560, 320, 600, gid=3),  # seen through the chat window
    ]
    c = lq.causes([f], "v1", "position")
    assert c["fn"] == {"self_moving_shift": 1, "ui_window:chat": 1}
    assert c["fp"] == {"self_moving_shift": 1, "no_hand_box:idle": 1}
    f["self_moving"] = False
    assert lq.causes([f], "v1", "position")["fn"]["unit_position:idle"] == 1


def test_what_ifs_count_the_errors_each_fix_removes(lq: ModuleType) -> None:
    f = frame_with_units()
    m1 = f["v1"][0]
    f["hand"] = [
        b("monster", m1["x1"] + 60, m1["y1"] - 5, m1["x2"] + 60, m1["y2"] - 5, gid=1),
        b("monster", 270, 540, 330, 600, gid=3),
    ]
    ifs = [
        lq.WhatIf("as_is", "-", False, lambda fr: fr["v1"]),
        lq.WhatIf("lag", "own walk", True, lambda fr: lq.relabel(fr, "v1", lag_ms=125)),
        lq.WhatIf("chat", "UI", False, lambda fr: lq.relabel(fr, "v1", ui_off=frozenset({"chat"}))),
    ]
    rows = {r["name"]: r for r in lq.run_what_ifs([f], ifs)}
    assert rows["as_is"]["position"]["fn"] == 2 and rows["as_is"]["position"]["fp"] == 2
    assert rows["lag"]["delta"]["position_errors_removed"] == 2  # its FN and its FP
    assert rows["chat"]["delta"]["position_errors_removed"] == 1
    assert (rows["lag"]["rank"], rows["chat"]["rank"]) == (1, 2)


def test_lofo_never_corrects_a_frame_with_its_own_boxes(lq: ModuleType) -> None:
    pairs = [
        {"frame_id": fid, "provenance": "moved", "state": "idle", "self_moving": False, "dy": -dy}
        for fid, dy in ((1, 2.0), (2, 4.0), (3, 9.0))
    ]
    per, all_ = lq.lofo_offset(pairs, "dy")
    assert per == {1: 6.5, 2: 5.5, 3: 3.0}
    assert all_ == 4.0


def test_fit_line_and_describe(lq: ModuleType) -> None:
    fit = lq.fit_line([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 5.0, 7.0])
    assert (fit["slope"], fit["intercept"], fit["r2"]) == (2.0, 1.0, 1.0)
    d = lq.describe([1.0, 2.0, 3.0, 4.0, 100.0])
    assert (d["n"], d["median"], d["p90"]) == (5, 3.0, 100.0)


def test_census_frame_counts_each_exposure(lq: ModuleType) -> None:
    f = frame_with_units()
    f["v1"][0]["state"] = "walk"
    c = lq.census_frame(f, lag_ms=125)
    assert c["monsters"] == 2 and c["walking"] == 1
    assert c["ui_dropped:chat"] == 1 and c["ui_dropped:minimap"] == 1
    assert c["edge_dropped"] == 1  # unit 6: visible, but less than half on screen
    assert c["self_shift_px"] == pytest.approx((60.0**2 + 5.0**2) ** 0.5)


# --- the reproduction proof: the cache's own YOLO txt --------------------------------------------


def test_compare_boxes_passes_equal_lists_and_catches_a_one_pixel_shift(lq: ModuleType) -> None:
    ours = [("monster", (10.0, 10.0, 54.0, 50.0)), ("npc", (100.0, 0.0, 134.0, 74.0))]
    yolo = "\n".join(
        f"{lq.CLASSES.index(c)} {(r[0] + r[2]) / 2 / 1280:.6f} {(r[1] + r[3]) / 2 / 720:.6f} "
        f"{(r[2] - r[0]) / 1280:.6f} {(r[3] - r[1]) / 720:.6f}"
        for c, r in reversed(ours)
    )
    same = lq.compare_boxes(ours, lq.parse_yolo(yolo))
    assert same["equal"] and same["max_edge_px"] < 0.01
    off = lq.compare_boxes([("monster", (11.0, 10.0, 55.0, 50.0)), ours[1]], lq.parse_yolo(yolo))
    assert not off["equal"] and off["unmatched_ours"] == 1


def test_cache_txt_reads_only_the_wanted_members(lq: ModuleType, tmp_path: Path) -> None:
    shard = tmp_path / "shard-000000.tar"
    with tarfile.open(shard, "w") as tar:
        for fid in (1, 2, 3):
            for ext, data in (
                ("png", b"\x00" * 64),
                ("txt", f"1 0.5 0.5 0.1 0.1 # {fid}".encode()),
                ("json", json.dumps({"frame_id": fid}).encode()),
            ):
                info = tarfile.TarInfo(f"S.{fid:09d}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    got = lq.cache_txt(shard, "S", [1, 3, 7])
    assert sorted(got) == [1, 3] and got[3].endswith("# 3")


# --- the constants repeated from the labeller stay equal to it -----------------------------------


def test_repeated_constants_match_the_labeller(lq: ModuleType) -> None:
    from poring_dataset import labels, ui_layout

    assert lq.UI_RECTS_PX == ui_layout.UI_RECTS
    assert len(lq.UI_NAMES) == len(ui_layout.UI_RECTS)
    assert {k: (float(w), float(h)) for k, (w, h) in labels.BOX_PX.items()} == lq.V0_BOX_PX
    assert lq.MAX_UI_COVER == labels.MAX_UI_COVER
    assert tuple(sorted(labels.CLASSES, key=labels.CLASSES.__getitem__)) == lq.CLASSES
    bfc = load("build_frame_cache")
    assert set(lq.SCENE_MAPS) == set(bfc.SCENE_MAPS)


# --- the dead-GM walk signature and a detector's misses ------------------------------------------


def test_dead_span_walks_flags_a_walk_inside_a_hits_damage_motion(lq: ModuleType) -> None:
    s = 1_000_000_000
    events = [
        {"t_mono_ns": 10 * s, "type": "act", "target_gid": 7, "damage": 6, "dmotion": 796},
        {
            "t_mono_ns": 10 * s + 153_000_000,
            "type": "self_move",
            "x0": 98,
            "y0": 109,
            "x1": 94,
            "y1": 108,
        },
        {"t_mono_ns": 30 * s, "type": "self_move", "x0": 1, "y0": 1, "x1": 2, "y1": 2},
        {"t_mono_ns": 40 * s, "type": "act", "target_gid": 7, "damage": 3, "dmotion": 500},
        {"t_mono_ns": 45 * s, "type": "act", "target_gid": 9, "damage": 3, "dmotion": 5000},
    ]
    spans = [(12 * s, 20 * s), (46 * s, 1 << 62)]
    rows = lq.dead_span_walks(events, 7, spans, 0)
    first, second = rows
    assert first["start_s"] == 12.0 and first["end_s"] == 20.0
    assert first["last_walk"] == {
        "from": [98, 109],
        "to": [94, 108],
        "ms_before_death": 1847,
        "ms_after_last_hit": 153,
        "in_damage_motion": True,
    }
    assert second["end_s"] is None
    assert second["last_walk"]["to"] == [2, 2] and second["last_walk"]["in_damage_motion"] is False


def test_model_misses_splits_by_the_labels_own_misses_and_the_dead_gm(lq: ModuleType) -> None:
    alive = frame_with_units()
    alive["self_moving"] = False
    m1 = alive["v1"][0]
    alive["hand"] = [
        b("monster", m1["x1"], m1["y1"], m1["x2"], m1["y2"], gid=1),
        b("monster", 270, 540, 330, 600, gid=3),
    ]
    dead = dict(frame_with_units(), frame_id=1, self_dead=True, self_moving=False)
    dead["hand"] = [b("monster", 100, 100, 144, 140, gid=1)]
    preds = {"0": [], "1": [b("monster", 200, 0, 244, 40)]}
    r = lq.model_misses([alive, dead], preds)
    assert (r["tp"], r["fp"], r["fn"]) == (0, 1, 3)
    assert r["fn_by_label_cause_gm_alive"] == {"label_hit": 1, "ui_window:chat": 1}
    assert r["by_gm"]["gm_dead"] == {"frames": 1, "tp": 0, "fn": 1, "fp": 1}
    assert r["gm_dead_fp_offset_to_nearest_hand"]["dx"]["median"] == 100.0
    assert r["gm_dead_fp_offset_to_nearest_hand"]["dy"]["median"] == -100.0


def test_peek_refuses_to_write_pixels_outside_dev_shm(lq: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="/dev/shm only"):
        lq.peek("S", 1.0, Path("/tmp/x.png"), tmp_path, tmp_path, 0.14)
