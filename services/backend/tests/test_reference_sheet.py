"""scripts/reference_sheet.py (docs/planning/xmas02-detector.md 6, tool gap T-10): T2's multi-view
reference sheet built on its own for a map's list -- the pack's drawing and letters, the stems
never guessed, the answer-key letters kept off stdout -- plus a REAL positive case on xmas_dun02's
decoded sprites (/dev/shm at run time, skipped when absent; client data is never committed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import orc_label_sheets as ols  # noqa: E402
import qa_export  # noqa: E402
import reference_sheet as rs  # noqa: E402

XMAS = (1249, 1248, 1265, 1246, 1515, 1607, 1251, 1002, 1062)


def test_the_xmas02_preset_is_plan_6s_list_in_the_packs_order() -> None:
    """Myst Case, Cruiser, Cookie, Christmas Cookie, Garm Baby, Christmas Goblin, Stormy Knight
    (the map's species), then Poring and Santa Poring (the reference): 9 letters, A-I."""
    assert rs.PRESETS["xmas_dun02"] == XMAS
    assert sorted(ols.letters_for(list(XMAS), 51)) == list("ABCDEFGHI")


def test_the_list_is_refused_when_it_cannot_be_drawn() -> None:
    for bad in ([], [1249, 1249], list(range(1000, 1027))):
        with pytest.raises(SystemExit):
            rs.check_mobs(bad)
    assert rs.check_mobs((1249, 1062)) == [1249, 1062]


class FakeSheets:
    """qa_export.Sheets' interface: the listed stems have a sheet; any other id is missing."""

    def __init__(self, directory: Path, *, stems: dict[int, str | None], aegis: Any) -> None:
        self.stems, self.missing = stems, {}

    def stem(self, job: int) -> tuple[str | None, str]:
        return (self.stems.get(job), "client_table") if job in self.stems else (None, "no_name")

    def __call__(self, job: int) -> Any:
        if job not in self.stems:
            self.missing[job] = "no_name"
            return None
        return SimpleNamespace(stem=self.stems[job])


def test_build_draws_the_packs_sheet_with_the_packs_letters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The drawing is orc_label_sheets.reference_sheet(views multi) under letters_for(mobs,
    seed): what map_labels.py pack draws for spec.species + spec.reference. Santa Poring's sheet
    comes by its client stem (poring_); a species without a sprite stops the build; the
    letters go to --letters-out only, never to stdout."""
    names = tmp_path / "monster_sprite_names.json"
    names.write_text(json.dumps({"mobs": {"1002": {"stem": "poring"}, "1062": {"stem": "poring_"},
                                          "1249": {"stem": "mystcase"}}}))  # fmt: skip
    seen: dict[str, Any] = {}

    def draw(sheets: Any, letters: Any, scale: int = 3, views: str = "one") -> Any:
        seen.update(sheets=sheets, letters=letters, views=views)
        return np.full((10, 20, 3), 110, np.uint8)

    monkeypatch.setattr(qa_export, "Sheets", FakeSheets)
    monkeypatch.setattr(ols, "reference_sheet", draw)
    rgb, letters = rs.build([1249, 1002, 1062], tmp_path, names, 51)
    assert rgb.shape == (10, 20, 3) and seen["views"] == "multi"
    assert letters == seen["letters"] == ols.letters_for([1249, 1002, 1062], 51)
    assert seen["sheets"][1062].stem == "poring_"
    with pytest.raises(SystemExit, match="no decoded sprite"):
        rs.build([1249, 1265], tmp_path, names, 51)
    with pytest.raises(SystemExit, match="sprite names"):
        rs.build([1249], tmp_path, tmp_path / "none.json", 51)
    out, key = tmp_path / "scratch" / "reference.png", tmp_path / "key" / "letters.json"
    argv = ["--mobs", "1249", "1002", "1062", "--sprites", str(tmp_path), "--sprite-names",
            str(names), "--seed", "51", "--out", str(out), "--letters-out", str(key)]  # fmt: skip
    assert rs.main(argv) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["size"] == [20, 10] and printed["species"] == 3 and "letters" not in printed
    assert out.exists() and json.loads(key.read_text())["letters"] == letters


SPRITES = Path("/dev/shm/poring-lab-tmp/xmas-det/sprites/data/sprite/몬스터")
NAMES = Path("/dev/shm/poring-lab-tmp/xmas-det/kb-sprites/monster_sprite_names.json")


def test_real_xmas02_reference_renders_every_listed_species(tmp_path: Path) -> None:
    """The decoded xmas_dun02 sprites (X1's archive merged with Poring / Santa Poring): all 9
    species of the preset draw (Santa Poring by its stem poring_), and the two Cookies -- one
    figure, two palettes -- differ in colour as the instructions say: Cookie's clothes pale
    GREEN, Christmas Cookie's RED (the share of their idle pixels where green beats red)."""
    if not (SPRITES.exists() and NAMES.exists()):
        pytest.skip("xmas_dun02's decoded sprites are not here")
    from poring_dataset.render import MonsterAction
    from poring_dataset.sprites import compose_frame

    rgb, letters = rs.build(XMAS, SPRITES, NAMES, 51)
    assert sorted(letters.values()) == sorted(XMAS) and rgb.ndim == 3
    tiles_h = rgb.shape[0] // 5  # 9 species, 2 to a row: 5 rows
    assert rgb.shape[0] == 5 * tiles_h
    sheets = qa_export.Sheets(SPRITES, stems=qa_export.sprite_stems(NAMES), aegis={})
    assert sheets.stem(1062) == ("poring_", "client_table")

    def green_share(mob: int) -> float:
        s = sheets(mob)
        assert s is not None
        img = compose_frame(s.spr, s.act, s.act.action_index(MonsterAction.IDLE, 0), 0)[0]
        px = img[img[..., 3] > 0][:, :3].astype(int)
        return float(np.mean(px[:, 1] > px[:, 0]))

    assert green_share(1265) > 0.3 and green_share(1246) < 0.05
