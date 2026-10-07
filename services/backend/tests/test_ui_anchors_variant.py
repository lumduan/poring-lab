"""scripts/ui_anchors_tool.py variant: a new locale's frame only ever NARROWS a stored mask
(2026-10-03, the Thai pack): the template stays, earlier variants' verdicts stay."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ui_anchors_tool.py"


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("ui_anchors_tool", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_locale_variant_drops_the_title_text_and_keeps_old_drops(tool: ModuleType) -> None:
    tmpl = np.full((15, 200), 90.0, np.float32)
    tmpl[3:12, 10:120] = 230.0  # "Basic Information"
    old_mask = np.ones_like(tmpl)
    old_mask[:, 190:] = 0.0  # a translucent edge an earlier scene variant dropped
    thai = tmpl.copy()
    thai[3:12, 10:120] = 90.0
    thai[3:12, 10:95] = 230.0  # the Thai title: other glyphs, another width
    new = tool.add_variant({"basic_info": tmpl}, {"basic_info": old_mask}, {"basic_info": thai})
    mask = new["basic_info"]
    assert mask[:, 190:].sum() == 0  # the old drop is kept
    assert mask[3:12, 95:120].sum() == 0  # where the two titles differ: dropped
    assert mask[0, 0] == 1 and mask[14, 150] == 1  # the frame around it: kept
    assert tool.add_variant({"x": tmpl}, {}, {"x": tmpl[:, :10]}) == {}  # wrong shape: ignored


def test_a_png_frame_comes_back_in_the_live_grabs_channel_order(
    tool: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-07: client_frame flipped decode_png's BGR once more, so templates cut from a PNG
    did not match live (BGRA) frames: a red window must stay red."""
    from poring_dataset.shards import encode_png

    monkeypatch.setattr(tool.r, "game_region", lambda: (80, 77, 8, 4))
    bgr = np.zeros((4, 8, 3), np.uint8)
    bgr[..., 2] = 200  # pure red, in BGR order like a live grab
    bgr[0, 0] = (10, 20, 30)
    png = tmp_path / "client.png"
    png.write_bytes(encode_png(bgr))
    assert np.array_equal(tool.client_frame(str(png)), bgr)
    full = np.zeros((90, 100, 3), np.uint8)
    full[77:81, 80:88] = bgr  # a full-screen shot: the client area is cut out
    png.write_bytes(encode_png(full))
    assert np.array_equal(tool.client_frame(str(png)), bgr)
