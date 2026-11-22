"""The fi7 rule (scripts/fi7_rule.py; xmas02-items-1080.md Amendment 22, round 7): a floor_item box
under the 0.50 floor, or on the no-entry cursor ring (>= 30 pure-red px in its box + 6 px), is
dropped; every other class is untouched. Synthetic frames only."""

from __future__ import annotations

import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import fi7_rule as f7  # noqa: E402

RED = (220, 10, 12)  # pure red: R >= 150, G <= 30, B <= 30
ORANGE = (220, 120, 40)  # an item's red-ish colour that is NOT pure red


def frame(h: int = 100, w: int = 120) -> Any:
    return np.zeros((h, w, 3), dtype=np.uint8)


def ring(img: Any, cx: int, cy: int, r: int = 8, colour: tuple[int, int, int] = RED) -> Any:
    yy, xx = np.ogrid[: img.shape[0], : img.shape[1]]
    d = np.hypot(xx - cx, yy - cy)
    img[(d >= r - 1) & (d <= r + 1)] = colour
    return img


def det(box: list[float], conf: float = 0.9, cls: str = "floor_item") -> dict[str, Any]:
    return {"cls": cls, "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3], "conf": conf}


def test_the_constants_are_the_pre_registered_ones() -> None:
    assert (f7.FI7_FLOOR, f7.FI7_RING_RED, f7.FI7_PAD) == (0.50, 30, 6)
    assert (f7.RED_MIN_R, f7.RED_MAX_GB, f7.ITEM_CLASS) == (150, 30, "floor_item")


def test_ring_red_px_counts_pure_red_in_the_box_and_its_pad_clipped_to_the_image() -> None:
    img = ring(frame(), 60, 50)
    n = f7.ring_red_px(img, [50, 40, 71, 61], pad=0)  # the whole ring (radius 7-9) inside
    assert n >= 30
    assert f7.ring_red_px(img, [50, 40, 71, 61], pad=6) == n  # the pad adds no more red
    assert f7.ring_red_px(img, [53, 43, 67, 57], pad=6) == n  # a tight box: the pad reaches it
    assert f7.ring_red_px(img, [53, 43, 67, 57], pad=0) < n  # without the pad, part of it
    assert f7.ring_red_px(img, [0, 0, 10, 10], pad=6) == 0  # nothing red up there
    assert f7.ring_red_px(ring(frame(), 60, 50, colour=ORANGE), [52, 42, 68, 58]) == 0
    edge = frame()
    edge[0:4, 0:4] = RED  # 16 px in the image's corner
    assert f7.ring_red_px(edge, [2, 2, 6, 6], pad=6) == 16  # the window clipped at 0, never wraps
    assert f7.ring_red_px(edge, [-20, -20, -10, -10], pad=6) == 0  # wholly outside: nothing
    edge[96:100, 116:120] = RED
    assert f7.ring_red_px(edge, [114, 94, 118, 98], pad=6) == 16  # the far edge clipped too


def test_fi7_drop_floor_then_ring_and_only_floor_items() -> None:
    img = ring(frame(), 60, 50)
    on_ring = [53, 43, 67, 57]
    elsewhere = [10, 10, 24, 24]
    assert f7.fi7_drop(det(elsewhere, 0.50), img) is None  # exactly 0.50: kept
    assert f7.fi7_drop(det(elsewhere, 0.4999), img) == "floor"
    assert f7.fi7_drop(det(on_ring, 0.9), img) == "ring"
    assert f7.fi7_drop(det(on_ring, 0.3), img) == "floor"  # the floor is judged first
    assert f7.fi7_drop(det(on_ring, 0.9, cls="cruiser"), img) is None  # a monster: never
    assert f7.fi7_drop(det(on_ring, 0.1, cls="player"), None) is None
    assert f7.fi7_drop(det(on_ring, 0.9), img, ring_red=None) is None  # half B off
    assert f7.fi7_drop(det(elsewhere, 0.2), None, floor=None, ring_red=None) is None
    with pytest.raises(ValueError, match="pixels"):  # the ring needs the frame
        f7.fi7_drop(det(on_ring, 0.9), None)


def test_apply_rule_keeps_the_shape_and_loads_a_frame_only_when_needed() -> None:
    img = ring(frame(), 60, 50)
    doc = {
        "weights": "w.pt",
        "conf": 0.25,
        "frames": {
            "s.000000001": [
                det([53, 43, 67, 57], 0.9),
                det([5, 5, 15, 15], 0.8),
                det([53, 43, 67, 57], 0.95, cls="cruiser"),
            ],  # fmt: skip
            "s.000000002": [det([5, 5, 15, 15], 0.3), det([30, 30, 40, 40], 0.9, cls="player")],
            "s.000000003": [],
        },
    }
    calls: list[str] = []

    def load(refs: Any, key: str) -> Any:
        calls.append(key)
        return img

    out, summ = f7.apply_rule(doc, {}, load)
    assert (
        set(out) == set(doc)
        and out["weights"] == "w.pt"
        and set(out["frames"]) == set(doc["frames"])
    )
    assert [d["cls"] for d in out["frames"]["s.000000001"]] == ["floor_item", "cruiser"]
    assert out["frames"]["s.000000001"][0]["conf"] == 0.8  # the ring box gone, the other kept
    assert [d["cls"] for d in out["frames"]["s.000000002"]] == ["player"]  # under the floor
    assert out["frames"]["s.000000003"] == []
    assert summ["dropped"] == {"floor": 1, "ring": 1} and summ["kept_items"] == 1
    assert calls == ["s.000000001"] and summ["frames_loaded"] == 1  # frame 2's item: floor only
    assert (summ["floor"], summ["ring_red"], summ["pad"]) == (0.5, 30, 6)
    assert doc["frames"]["s.000000001"][0]["conf"] == 0.9 and len(doc["frames"]["s.000000001"]) == 3
    same, s0 = f7.apply_rule(doc, {}, load, floor=None, ring_red=None)
    assert same["frames"] == doc["frames"] and s0["dropped"] == {"floor": 0, "ring": 0}


def test_load_frame_reads_the_tar_member_under_the_storage_folder(tmp_path: Path) -> None:
    from PIL import Image

    img = ring(frame(), 60, 50)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    data = buf.getvalue()
    sess = tmp_path / "20261122T010000-rdp-xmas02-ifH5"
    sess.mkdir()
    tar = sess / "shard-000000.tar"
    with tarfile.open(tar, "w") as tf:
        info = tarfile.TarInfo("000000001.png")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    with tarfile.open(tar) as tf:
        member = tf.getmember("000000001.png")
        offset = member.offset_data
    refs = {"k.1": {"path": f"/datasets/{sess.name}/shard-000000.tar", "offset": offset,
                    "size": len(data)}}  # fmt: skip
    got = f7.load_frame(refs, "k.1", store=tmp_path)
    assert got.shape == (100, 120, 3) and np.array_equal(got, img)
    assert f7.host_path("/datasets/a/b.tar", tmp_path) == tmp_path / "a" / "b.tar"
    with pytest.raises(ValueError, match="not under"):
        f7.host_path("/elsewhere/a.tar", tmp_path)
    with pytest.raises(SystemExit, match="no frame k.2"):
        f7.load_frame(refs, "k.2", store=tmp_path)
    json.dumps(refs)  # refs.json's own shape


# --- C, the view edge (round 10, Amendment 36) ---------------------------------------------------


def test_the_view_edge_constants_are_amendment_36s_and_the_view_is_the_virtual_1080_one() -> None:
    import rec_paths

    assert (f7.FI10_EDGE, f7.FI10_TOP) == (12, 32)
    assert rec_paths.VIRTUAL_1080["game_region"][2:] == [f7.VIEW_W, f7.VIEW_H]


def test_edge_drop_judges_the_box_centre_against_each_band() -> None:
    def at(cx: float, cy: float, cls: str = "floor_item") -> dict[str, Any]:
        return det([cx - 8, cy - 8, cx + 8, cy + 8], cls=cls)

    assert not f7.edge_drop(at(640, 360))  # the middle
    assert f7.edge_drop(at(11, 360)) and not f7.edge_drop(at(12, 360))  # left: inside the band
    assert f7.edge_drop(at(1269, 360)) and not f7.edge_drop(at(1268, 360))  # right
    assert f7.edge_drop(at(640, 709)) and not f7.edge_drop(at(640, 708))  # bottom
    assert f7.edge_drop(at(640, 31)) and not f7.edge_drop(at(640, 32))  # top: its own 32 px
    assert f7.edge_drop(at(620, 24))  # round 9's wall ornament (ifH26 298-305)
    assert f7.edge_drop(at(1271, 444))  # round 9's object cut by the right edge (ifH23 328-335)
    assert not f7.edge_drop(at(5, 5, cls="monster"))  # every other class is untouched
    assert not f7.edge_drop(at(11, 360), edge=0, top=0)  # zero bands drop nothing


def test_apply_edge_keeps_the_document_shape_and_counts_its_drops() -> None:
    doc = {"weights": "w.pt", "frames": {
        "a": [det([600, 10, 640, 38]), det([600, 300, 640, 340])],  # top band, middle
        "b": [det([1262, 400, 1280, 440], cls="monster"), det([1262, 400, 1280, 440])],
        "c": []}}  # fmt: skip
    out, n = f7.apply_edge(doc)
    assert n == 2 and out["weights"] == "w.pt" and set(out["frames"]) == {"a", "b", "c"}
    assert out["frames"]["a"] == [doc["frames"]["a"][1]]
    assert out["frames"]["b"] == [doc["frames"]["b"][0]]  # the monster box stays
    assert doc["frames"]["a"][0] in doc["frames"]["a"]  # the input is not changed
