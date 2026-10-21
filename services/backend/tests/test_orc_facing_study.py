"""The orcsdun01 facing study (docs/planning/orcsdun01-detector.md 3e DRAFT;
scripts/orc_facing_study.py): the pure parts on SYNTHETIC sprites / rows, plus a REAL positive case
from col3 (skipped when the local data is absent; client data is never committed)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_dataset import render as rd
from poring_dataset.camera import displayed_direction
from poring_dataset.sprites import Act, Layer, Motion, Spr

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import orc_facing_study as fs  # noqa: E402

N, NW, W, SW, S, SE, E, NE = range(8)


def paired_sheet() -> rd.SpriteSheet:
    """Five action groups whose 8 directions draw 4 distinct images in PAIRS (0 = 1, 2 = 3, 4 = 5,
    6 = 7), as every orcsdun01 walker / bat ACT does."""
    imgs = []
    for k in range(4):
        img = np.zeros((6, 4, 4), np.uint8)
        img[..., 3] = 255
        img[k, :, :3] = 200  # a different row lit per image
        imgs.append(img)
    actions = []
    for i in range(40):
        layer = Layer(0, -3, (i % 8) // 2, False, (255, 255, 255, 255), 1.0, 1.0, 0, 0, None, None)
        actions.append((Motion((layer,)), Motion((layer,))))
    act = Act((2, 5), tuple(actions), (), (4.0,) * 40)
    return rd.SpriteSheet(act, Spr((2, 1), tuple(imgs), 4, None))


def test_view_classes_pair_the_directions() -> None:
    sheet = paired_sheet()
    assert fs.view_classes(sheet, 0) == [(0, 1), (2, 3), (4, 5), (6, 7)]
    assert fs.view_classes(sheet, 1) == [(0, 1), (2, 3), (4, 5), (6, 7)]


def test_an_axis_heading_shares_its_image_with_the_clockwise_diagonal() -> None:
    """Why 3c's best-of-8 never named W, S or E: under displayed_direction (yaw 0) an axis heading
    draws the same image as its clockwise neighbour, and a max that keeps the first of equal scores
    returns the LOWER heading -- so only N could ever "agree" on an axis move."""
    classes = [(0, 1), (2, 3), (4, 5), (6, 7)]

    def cls(h: int) -> int:
        return fs.class_index(classes, displayed_direction(h, 0.0))

    assert cls(W) == cls(NW) and cls(S) == cls(SW) and cls(E) == cls(SE) and cls(N) == cls(NE)
    for h in (W, S, E):
        scores = {k: 1.0 if cls(k) == cls(h) else 0.0 for k in range(8)}
        assert max(scores, key=lambda k: scores[k]) == h - 1  # never h itself
    assert len({cls(h) for h in range(8)}) == 4


def test_the_quadrant_zero_convention() -> None:
    assert fs.quadrant(0, 3) == NW  # north -> NW
    assert fs.quadrant(3, 0) == NE  # east -> NE
    assert fs.quadrant(-3, 0) == NW  # west -> NW
    assert fs.quadrant(0, -3) == SW  # south -> SW
    assert [fs.quadrant(2, 2), fs.quadrant(-2, 2), fs.quadrant(-2, -2), fs.quadrant(2, -2)] == [
        NE, NW, SW, SE,
    ]  # fmt: skip
    assert fs.quadrant(5, -1) == SE and fs.quadrant(0, 0) is None


def row(state: str, source: str, d: tuple[int, int] | None = None, stand: int | None = None,
        scores: list[float | None] | None = None,
        episode: str = "e") -> dict[str, Any]:  # fmt: skip
    mv = None if d is None else {"d": list(d), "shape": fs.shape_of(*d), "whole": None}
    if mv is not None:
        from poring_packets.world import direction_toward

        mv["whole"] = direction_toward(*d)
    return {"state": state, "source": source, "move": mv, "stand_heading": stand, "mob": 1153,
            "classes": [[0, 1], [2, 3], [4, 5], [6, 7]], "episode": episode, "under_model": None,
            "class_scores": scores or [0.6, 0.1, 0.1, 0.1], "half": 1}  # fmt: skip


def test_fix2_heading_per_state() -> None:
    assert fs.fix2_heading(row("stand", "stand", stand=N)) == N  # the packet's heading as sent
    assert fs.fix2_heading(row("walk", "move", (7, -2))) == SE  # walking: the vector's quadrant
    # standing after the move: map_calc_dir first ((7, -2) is east by its 1:3 rule) -> NE's image
    assert fs.fix2_heading(row("stand", "move", (7, -2))) == NE
    assert fs.fix2_heading(row("stand", "move", (5, -3))) == SE  # a diagonal by the 1:3 rule
    assert fs.fix2_heading(row("stand", "move", (0, 4))) == NW  # north
    assert fs.fix2_heading(row("stand", "move", (-4, 0))) == NW  # west
    assert fs.fix2_heading(row("stand", "move", (0, -4))) == SW  # south


def test_paths_and_shapes() -> None:
    assert fs.diagonal_first(0, 0, 3, -1) == [(1, -1), (2, -1), (3, -1)]
    assert fs.straight_first(0, 0, 3, -1) == [(1, 0), (2, 0), (3, -1)]
    assert fs.step_headings((0, 0), fs.diagonal_first(0, 0, 3, -1)) == [SE, E, E]
    assert [fs.shape_of(0, 3), fs.shape_of(2, -2), fs.shape_of(3, 1)] == ["axis", "diagonal",
                                                                           "mixed"]  # fmt: skip
    assert fs.heading22(5, 3) == NE and fs.heading22(5, 2) == E and fs.heading22(5, 1) == E


def test_the_eye_azimuth_rule_puts_an_axis_heading_on_one_side() -> None:
    assert fs.act_floor(N, 0.0) == displayed_direction(N, 0.0)
    assert fs.act_floor(N, 5.0) == displayed_direction(NW, 0.0)  # right of the eye: NW's image
    assert fs.act_floor(N, -5.0) == displayed_direction(N, 0.0)
    assert fs.act_floor(NE, 5.0) in (displayed_direction(NE, 0.0), displayed_direction(N, 0.0))


def test_agreement_counts_decisive_rows_and_episodes() -> None:
    rules = fs.rules()
    rs = [
        row("stand", "move", (0, 4), scores=[0.1, 0.7, 0.1, 0.1], episode="a"),  # NW image: fix2
        row("stand", "move", (0, 4), scores=[0.1, 0.7, 0.1, 0.1], episode="a"),
        row("stand", "move", (0, 4), scores=[0.1, 0.12, 0.1, 0.1], episode="b"),  # not decisive
        row("stand", "move", (3, 0), scores=[0.1, 0.1, 0.1, 0.6], episode="c"),  # E/SE image
    ]
    t = fs.agree_table(rs, rules[fs.PROPOSED], 0.05, fs.category)
    assert t["all"]["n"] == 3 and t["all"]["agree"] == 2 and t["all"]["episodes"] == 2
    old = fs.agree_table(rs, rules[fs.FROZEN_1A], 0.05, fs.category)
    assert old["all"]["agree"] == 1  # the frozen 1a rule draws N's own image (N/NE) for "a"


def test_the_held_out_blocks_are_refused() -> None:
    for name in ("20261021T103231-orcsdun01-col1", "20261021T122650-orcsdun01-col2"):
        with pytest.raises(SystemExit):
            fs.refuse_held_out(Path("/x") / name)
    fs.refuse_held_out(Path("/x/20261021T142100-orcsdun01-col3"))


# --- REAL positive case (local data only: skipped elsewhere) ------------------------------------

COL3_NAS = "/mnt/poring-lab-datasets/detector-collection/orcsdun01/20261021T142100-orcsdun01-col3"
COL3 = Path(os.environ.get("PORING_COL3", COL3_NAS))
KB = Path(os.environ.get("PORING_KB", str(ROOT / "data" / "kb")))
PARAMS = {
    "offset_ms": 120.0,
    "anchors_px": {"1005": [1.0, -1.0], "1042": [0.0, -2.0], "1111": [1.0, -1.0]},
}  # 3c's frozen 1d / 1b values


def test_real_orc_after_an_east_move_shows_its_back() -> None:
    """col3 frame 1938 (half 1), Orc Zombie gid 110096085 standing after an EAST move (3, 0): the
    drawn view is the N/NE image (its back; checked by eye on the crop, 2026-10-21 22:0x), NCC
    0.688 against 0.102 for the E/SE image the frozen 1a rule draws. fix2 names the back."""
    if not (COL3 / "manifest.json").exists() or not (KB / "classes.json").exists():
        pytest.skip("col3 or the local KB is not here")
    import orc_labels_fix as olf

    sess = olf.Session.open(COL3, KB)
    if sess.lab.sheets(1153) is None:
        pytest.skip("the decoded sprites are not here")
    fs.prepare(sess, None, PARAMS, 1)
    ref = next(r for r in sess.refs if r.frame_id == 1938)
    rows, _dropped = fs.frame_rows(ref)
    got = next(r for r in rows if r["gid"] == 110096085)
    assert got["state"] == "stand" and got["move"]["d"] == [3, 0]
    drawn = fs.drawn_class(got)
    assert got["classes"][drawn] == [4, 5]  # ACT N / NE: the back view
    assert fs.decisive(got, 0.05) and got["class_scores"][drawn] > 0.6
    rules = fs.rules()
    assert fs.class_index(got["classes"], rules[fs.PROPOSED](got)) == drawn
    assert fs.class_index(got["classes"], rules[fs.FROZEN_1A](got)) != drawn
    json.dumps(got)  # a row is plain JSON
