"""nametag: the name-tag letter mask, word box and template match (pure parts)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import nametag as nt  # noqa: E402


def _word(img: np.ndarray, x: int, y: int, pattern: list[str]) -> None:
    """Draw letters: '#' = white core with a dark outline around it."""
    for dy, row in enumerate(pattern):
        for dx, ch in enumerate(row):
            if ch == "#":
                img[y + dy - 1 : y + dy + 2, x + dx - 1 : x + dx + 2] = (20, 20, 20)
    for dy, row in enumerate(pattern):
        for dx, ch in enumerate(row):
            if ch == "#":
                img[y + dy, x + dx] = (250, 250, 250)


PAT = ["#.#.###.#..", "#.#.#...#..", "###.##..#..", "#.#.#...#..", "#.#.###.###",
       "#.#.#...#..", "#.#.###.###"]  # fmt: skip


def test_the_letter_mask_needs_an_outline_and_the_word_box_finds_the_word() -> None:
    img = np.full((60, 140, 3), (90, 140, 60), np.uint8)  # grass
    img[5:15, 5:30] = (245, 245, 245)  # white scenery without an outline
    _word(img, 40, 30, PAT)
    m = nt.letter_mask(img)
    assert not m[8, 10] and m[30, 40]
    wb = nt.word_box(m)
    assert wb is not None and wb[0] <= 40 and wb[2] >= 50 and 29 <= wb[1] <= 31


def test_a_word_matches_its_own_template_and_not_another() -> None:
    img = np.full((60, 140, 3), (90, 140, 60), np.uint8)
    _word(img, 40, 30, PAT)
    m = nt.letter_mask(img)
    wb = nt.word_box(m)
    assert wb is not None
    tpl = m[wb[1] : wb[3], wb[0] : wb[2]]
    other = np.zeros_like(tpl)
    other[:, ::2] = True
    name, iou = nt.match(m, {"Poring": tpl, "Creamy": other})
    assert name == "Poring" and iou > 0.9
    name, _ = nt.match(m, {"Creamy": other})
    assert name is None
