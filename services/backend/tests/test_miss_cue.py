"""scripts/miss_cue.py: the "Miss" text a monster's swing at us makes the client draw, from pixels.
The cue is the best zero-mean NCC of a light-grey ("bright and neutral") text template inside the
band around our head. Synthetic glyphs stand in for the client's text (client pixels are never
committed); the truth labels and the gain estimate are checked on synthetic packet times."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
NS = 1_000_000_000
TEXT = (212, 208, 205)  # BGR: light grey, the Miss text's colour
SHADOW = (30, 40, 40)
RED = (40, 40, 220)  # BGR: a damage number on us


@pytest.fixture(scope="module")
def mc() -> ModuleType:
    spec = importlib.util.spec_from_file_location("miss_cue", SCRIPTS / "miss_cue.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # a dataclass needs its module registered
    spec.loader.exec_module(mod)
    return mod


# a 10 x 30 glyph mask: "M", "i", "s", "s" as strokes (1 = ink)
GLYPH = np.zeros((10, 30), bool)
GLYPH[:, 0] = GLYPH[:, 6] = True  # M's legs
GLYPH[1:5, 1:6] = np.eye(4, 5, dtype=bool) | np.fliplr(np.eye(4, 5, dtype=bool))  # M's V
GLYPH[0, 10] = True  # the i's dot
GLYPH[3:, 10] = True  # the i's stem
for x0 in (14, 22):  # two "s": top, middle, bottom bars + the two sides
    GLYPH[3, x0 : x0 + 5] = GLYPH[6, x0 : x0 + 5] = GLYPH[9, x0 : x0 + 5] = True
    GLYPH[3:7, x0] = GLYPH[6:10, x0 + 4] = True
# another word of white text (a name label / white digits): blocks, no M-i-s-s strokes
OTHER = np.zeros((10, 30), bool)
for x0 in (0, 8, 16, 24):
    OTHER[:, x0 : x0 + 2] = OTHER[0, x0 : x0 + 6] = OTHER[9, x0 : x0 + 6] = True


def scene(seed: int = 0) -> np.ndarray:
    """A 1280 x 720 BGR grass-like scene: green / brown texture, blue channel low."""
    rng = np.random.default_rng(seed)
    img = np.empty((720, 1280, 3), np.uint8)
    base = rng.integers(60, 120, (720, 1280))
    img[..., 0] = np.clip(base - 30, 0, 255)  # B
    img[..., 1] = np.clip(base + 60, 0, 255)  # G
    img[..., 2] = np.clip(base + 40, 0, 255)  # R
    return img


def draw(img: np.ndarray, mask: np.ndarray, x: int, y: int, colour: tuple[int, int, int],
         shadow: bool = True) -> np.ndarray:  # fmt: skip
    """``mask`` drawn with its top-left at (x, y), a 1-px drop shadow right / below."""
    out = img.copy()
    h, w = mask.shape
    if shadow:
        sh = np.zeros_like(mask)
        sh[1:, 1:] = mask[:-1, :-1]
        out[y : y + h, x : x + w][sh & ~mask] = SHADOW
    out[y : y + h, x : x + w][mask] = colour
    return out


@pytest.fixture(scope="module")
def tpl(mc: ModuleType) -> np.ndarray:
    """The template as `cut` builds it: the feature map of a text instance, 2 px padding."""
    img = draw(scene(99), GLYPH, 602, 252, TEXT)
    t: np.ndarray = mc.feature(img[250:264, 600:634])
    assert t.shape == mc.TEMPLATE_HW
    return t


def test_ncc_of_a_template_on_itself_is_one(mc: ModuleType, tpl: np.ndarray) -> None:
    s = mc.ncc_map(tpl, tpl)
    assert s.shape == (1, 1) and s[0, 0] == pytest.approx(1.0, abs=1e-4)


def test_a_flat_window_scores_zero(mc: ModuleType, tpl: np.ndarray) -> None:
    flat = np.full((40, 80), 0.5, np.float32)
    assert float(mc.ncc_map(flat, tpl).max()) == 0.0


@pytest.mark.parametrize("pos", [(560, 150), (640, 220), (700, 300)])
def test_positive_miss_in_the_band(mc: ModuleType, tpl: np.ndarray, pos: tuple[int, int]) -> None:
    img = draw(scene(1), GLYPH, *pos, TEXT)
    r = mc.read(img, tpl)
    assert r.score >= mc.THRESHOLD and mc.miss_over_us(img, tpl)
    assert abs(r.x - (pos[0] + 15)) <= 3 and abs(r.y - (pos[1] + 5)) <= 3


def test_positive_survives_a_fade(mc: ModuleType, tpl: np.ndarray) -> None:
    """A fading text: halfway to the background, still bright and neutral enough."""
    img = draw(scene(2), GLYPH, 620, 200, (175, 172, 170))
    assert mc.miss_over_us(img, tpl)


def test_negative_plain_scene_exits_early(mc: ModuleType, tpl: np.ndarray) -> None:
    r = mc.read(scene(3), tpl)
    assert r.score == 0.0 and r.ink < mc.MIN_INK and not mc.miss_over_us(scene(3), tpl)


def test_hard_negative_red_number_is_not_ink(mc: ModuleType, tpl: np.ndarray) -> None:
    """A red damage number on us (same strokes even): the feature reads it as no ink."""
    img = draw(scene(4), GLYPH, 630, 230, RED)
    assert mc.read(img, tpl).score == 0.0


def test_hard_negative_other_white_text(mc: ModuleType, tpl: np.ndarray) -> None:
    """White text of another shape (a name label, white digits): below the threshold."""
    img = draw(scene(5), OTHER, 610, 240, TEXT)
    assert not mc.miss_over_us(img, tpl)


def test_hard_negative_bright_blob(mc: ModuleType, tpl: np.ndarray) -> None:
    """A light-grey rock: bright and neutral but no strokes."""
    img = scene(6)
    yy, xx = np.ogrid[:720, :1280]
    img[(yy - 240) ** 2 / 30**2 + (xx - 640) ** 2 / 45**2 <= 1] = (190, 195, 200)
    assert not mc.miss_over_us(img, tpl)


@pytest.mark.parametrize("pos", [(620, 40), (610, 390), (300, 220), (900, 220)])
def test_text_outside_the_band_is_ignored(mc: ModuleType, tpl: np.ndarray,
                                         pos: tuple[int, int]) -> None:  # fmt: skip
    """A Miss far from us (a ranged attacker, the notice area, our name label below the HP bar)."""
    img = draw(scene(7), GLYPH, *pos, TEXT)
    assert not mc.miss_over_us(img, tpl)


def test_bgra_frames_are_accepted(mc: ModuleType, tpl: np.ndarray) -> None:
    img = draw(scene(8), GLYPH, 640, 220, TEXT)
    bgra = np.concatenate([img, np.full((720, 1280, 1), 255, np.uint8)], axis=2)
    assert mc.read(bgra, tpl).score == pytest.approx(mc.read(img, tpl).score)


# --- truth labels --------------------------------------------------------------------------------


def test_label_classes(mc: ModuleType) -> None:
    ev = {"miss": [100 * NS], "hit_on_us": [200 * NS], "our_attack": [300 * NS],
          "steal": [400 * NS]}  # fmt: skip
    assert mc.label(100 * NS + int(1.0 * NS), ev) == "pos"
    assert mc.label(100 * NS + int(0.6 * NS), ev) == "skip"  # the text may be appearing
    assert mc.label(100 * NS + int(2.3 * NS), ev) == "skip"  # fading: not judged
    assert mc.label(100 * NS + int(0.2 * NS), ev) == "fight"  # swung, nothing drawn yet
    assert mc.label(100 * NS + int(3.0 * NS), ev) == "skip"  # an old text, high above: not judged
    assert mc.label(200 * NS + int(1.2 * NS), ev) == "hit_on_us"
    assert mc.label(300 * NS + int(1.0 * NS), ev) == "our_attack"
    assert mc.label(400 * NS + int(0.5 * NS), ev) == "steal"
    assert mc.label(50 * NS, ev) == "neg"
    assert mc.label(200 * NS - int(1.0 * NS), ev) == "fight"  # a hit on us 1 s away


def test_truth_events_from_packets(mc: ModuleType) -> None:
    aid = mc.AID
    pk = [
        {"type": "act", "t_mono_ns": 1, "src_gid": 7, "target_gid": aid, "damage": 0,
         "kind": "normal"},
        {"type": "act", "t_mono_ns": 2, "src_gid": 7, "target_gid": aid, "damage": 90,
         "kind": "normal"},
        {"type": "act", "t_mono_ns": 3, "src_gid": 7, "target_gid": aid, "damage": 0,
         "kind": "lucky_dodge"},
        {"type": "act", "t_mono_ns": 4, "src_gid": aid, "target_gid": 7, "damage": 150,
         "kind": "multi_hit"},
        {"type": "act", "t_mono_ns": 5, "src_gid": aid, "target_gid": 9, "damage": 0,
         "kind": "pickup"},
        {"type": "use_item_result", "t_mono_ns": 6},
    ]  # fmt: skip
    ev = mc.truth_events(pk, [{"kind": "steal", "t_ns": 8}])
    assert ev["miss"] == [1] and ev["hit_on_us"] == [2] and ev["lucky"] == [3]
    assert ev["our_attack"] == [4] and ev["potion"] == [6] and ev["steal"] == [8]
    assert "pickup" not in ev


# --- the gain estimate ---------------------------------------------------------------------------


def test_gain_with_a_perfect_cue(mc: ModuleType) -> None:
    """Swings at 0 (miss), 1.5 (miss), 3 (hit), 9 (hit); we answered at 10, 7 s after the hit.
    Seen on the first miss (+1 s): the answer moves to 1 + 7 = 8 s; the hit at 9 s is saved."""
    eng = {"t_approach": 0, "t_respond": 10 * NS}
    theirs = [(0, 7, 0), (int(1.5 * NS), 7, 0), (3 * NS, 7, 120), (9 * NS, 7, 100)]
    g = mc.engagement_gain(eng, theirs, delay_s=1.0, recall=1.0, post_s=5.0)
    assert g["first_hit_s"] == 3.0 and g["misses_before_hit"] == 2
    assert g["new_react_s"] == pytest.approx(8.0) and g["gain_s"] == pytest.approx(2.0)
    assert g["damage_unanswered"] == 220 and g["damage_saved"] == 100


def test_gain_with_a_blind_cue_is_zero(mc: ModuleType) -> None:
    eng = {"t_approach": 0, "t_respond": 10 * NS}
    theirs = [(0, 7, 0), (int(1.5 * NS), 7, 0), (3 * NS, 7, 120)]
    g = mc.engagement_gain(eng, theirs, delay_s=1.0, recall=0.0, post_s=5.0)
    assert g["gain_s"] == 0.0 and g["damage_saved"] == 0


def test_gain_never_makes_the_answer_later(mc: ModuleType) -> None:
    """No hit before our answer (we found it another way): post_s from the run, capped."""
    eng = {"t_approach": 0, "t_respond": 2 * NS}
    theirs = [(0, 7, 0)]
    g = mc.engagement_gain(eng, theirs, delay_s=1.0, recall=1.0, post_s=5.0)
    assert g["new_react_s"] == 2.0 and g["gain_s"] == 0.0
