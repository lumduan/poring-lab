"""cursor_learn (ADR-0020 Amendment V, Batt 2026-11-19: "fix cause C"): a Run learns THIS
client's own walk arrow, by its SHAPE, so the colour readers know its colours. Batt's Thai client
draws the arrow in other colours than the lab's references (walk recall 0.53-0.93 vs 0.94-0.99).

Synthetic cursors (no client pixels are committed); one check on the lab's references skips where
they are not on this host. Moves only: the learning never clicks or types."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import cursor_learn as cl  # noqa: E402
import cursor_robust as cr  # noqa: E402
import cursor_sword as csw  # noqa: E402

LAB = (230, 200, 205)  # BGR: the lab references' arrow colour (synthetic)
HIS = (60, 40, 250)  # another client's arrow: every channel > TOL away on two of them


def arrow_mask() -> np.ndarray:
    """A synthetic arrow: tip at the hotspot (32, 32), reaching right and down (walk: x -2..+21,
    y -2..+29)."""
    m = np.zeros((64, 64), bool)
    for dy in range(0, 26):
        m[32 + dy, 32 : 32 + 1 + dy * 3 // 4] = True
    return m


def bar_mask() -> np.ndarray:
    """A synthetic sword: a thick diagonal bar through the hotspot."""
    m = np.zeros((64, 64), bool)
    for t in range(-18, 26):
        m[32 + t - 1 : 32 + t + 2, 32 + t - 1 : 32 + t + 2] = True
    return m


def blob_mask() -> np.ndarray:
    """A synthetic hand: a round blob up-left of the hotspot."""
    yy, xx = np.mgrid[0:64, 0:64]
    return (yy - 24) ** 2 + (xx - 24) ** 2 <= 100


def texture(seed: int = 3) -> np.ndarray:
    """A static floor of muted colours (no green: walk6.green marks the walk marker)."""
    rng = np.random.default_rng(seed)
    t = rng.integers(60, 120, (64, 64, 3)).astype(np.uint8)
    t[..., 1] = t[..., 2] // 2
    return t


def paint(bg: np.ndarray, mask: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    out = bg.copy()
    out[mask] = colour
    return out


def refs() -> cr.RobustRefs:
    """Lab-like references: arrows, bars and blobs in the lab's colour over a few floors."""
    a, m, cls = [], [], []
    for k in range(6):
        for name, mk in (("walk", arrow_mask), ("sword", bar_mask), ("pickup", blob_mask)):
            mask = mk()
            a.append(paint(texture(k), mask, LAB))
            m.append(mask)
            cls.append(name)
    return cr.RobustRefs(np.stack(a), np.stack(m), cls)


@pytest.fixture(autouse=True)
def _no_learned() -> Any:
    csw.LEARNED.clear()
    yield
    csw.LEARNED.clear()


def test_the_arrow_is_told_by_its_shape_alone() -> None:
    rf = refs()
    sc = cl.shape_scores(rf, arrow_mask())
    assert sc["walk"] == pytest.approx(1.0) and cl.is_walk_arrow(sc)
    assert not cl.is_walk_arrow(cl.shape_scores(rf, bar_mask()))
    assert not cl.is_walk_arrow(cl.shape_scores(rf, blob_mask()))
    assert not cl.is_walk_arrow({"walk": 0.96, "sword": 0.90})  # too close to another shape
    assert not cl.is_walk_arrow({"walk": 0.90, "sword": 0.10})  # not the arrow enough


def test_a_capture_keeps_only_the_cursor_s_own_pixels() -> None:
    rf = refs()
    sw = csw.SwordRefs(rf)
    bg, still = texture(9), np.zeros((64, 64), bool)
    verdict, got = cl.judge(rf, sw, paint(bg, arrow_mask(), HIS), bg, still)
    assert verdict == "kept" and got is not None
    cut, mask = got
    assert (mask == arrow_mask()).all()
    assert (cut[mask] == HIS).all() and (cut[~mask] == 0).all()  # the floor is never kept
    assert cl.judge(rf, sw, bg, bg, still)[0] == "no_cursor"
    assert cl.judge(rf, sw, paint(bg, bar_mask(), HIS), bg, still)[0] == "shape"
    # a sword drawn in the lab's own colours, shaped like the arrow: the sword guard refuses it
    sw_only = cr.RobustRefs(np.stack([paint(texture(k), arrow_mask(), LAB) for k in range(4)]),
                            np.stack([arrow_mask()] * 4), ["sword"] * 4)  # fmt: skip
    assert cl.judge(rf, csw.SwordRefs(sw_only), paint(bg, arrow_mask(), LAB), bg, still)[0] == (
        "sword"
    )


def test_the_learned_arrow_is_read_as_clear_where_the_lab_s_is_not() -> None:
    rf = refs()
    crop = paint(texture(11), arrow_mask(), HIS)
    base = csw.SwordRefs(rf)
    assert csw.verdict(base.recalls(crop)) == "unknown"  # the lab's colours: not this client's
    for _ in range(csw.LEARN_MIN - 1):
        csw.LEARNED.append((paint(np.zeros((64, 64, 3), np.uint8), arrow_mask(), HIS),
                            arrow_mask()))  # fmt: skip
    assert csw.learned_refs() is None  # fewer than LEARN_MIN: not used
    csw.LEARNED.append((paint(np.zeros((64, 64, 3), np.uint8), arrow_mask(), HIS), arrow_mask()))
    both = csw.SwordRefs(rf, extra=csw.learned_refs())
    rec = both.recalls(crop)
    assert rec["walk"] == pytest.approx(1.0) and csw.verdict(rec) == "clear"
    lab_crop = paint(texture(12), arrow_mask(), LAB)
    assert both.recalls(lab_crop) == base.recalls(lab_crop)  # the lab's own arrow: as before


class FakeClient:
    """A still floor; the client draws HIS arrow where the pointer is (moves only)."""

    def __init__(self, scroll: bool = False) -> None:
        rng = np.random.default_rng(5)
        self.floor = rng.integers(60, 120, (720, 1280, 3)).astype(np.uint8)
        self.floor[..., 1] = self.floor[..., 2] // 2
        self.pointer = (0, 0)
        self.scroll, self.calls, self.n = scroll, [], 0

    # the agent
    def move(self, x: int, y: int) -> None:
        self.calls.append(("move", x, y))
        self.pointer = (x, y)

    # the screen
    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        self.n += 1
        f = np.roll(self.floor, self.n * 7, axis=1) if self.scroll else self.floor.copy()
        px, py = self.pointer
        m = arrow_mask()
        ys, xs = np.nonzero(m)
        ok = (
            (py - 32 + ys >= 0) & (py - 32 + ys < 720) & (px - 32 + xs >= 0) & (px - 32 + xs < 1280)
        )
        f[(py - 32 + ys)[ok], (px - 32 + xs)[ok]] = HIS
        crop = f[y : y + h, x : x + w]
        return 0, np.dstack([crop, np.full(crop.shape[:2], 255, np.uint8)])


class FakeR:
    @staticmethod
    def game_region() -> tuple[int, int, int, int]:
        return 0, 0, 1280, 720

    @staticmethod
    def virtual_active() -> bool:
        return False


def test_a_run_learns_the_client_s_arrow_with_moves_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    fake = FakeClient()
    res = cl.learn(fake, fake, FakeR, refs=refs())
    assert res["used"] and res["kept"] == len(cl.POINTS) * cl.GRABS == len(csw.LEARNED)
    assert {c[0] for c in fake.calls} == {"move"}  # never a click, never a key
    assert fake.calls[-1][1:] == cl.PARK  # the pointer is parked off the points at the end
    assert "learned this client's own walk arrow" in cl.words(res)
    crop = paint(texture(13), arrow_mask(), HIS)
    assert csw.verdict(csw.SwordRefs(refs(), extra=csw.learned_refs()).recalls(crop)) == "clear"


def test_a_scrolling_scene_teaches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cl.time, "sleep", lambda s: None)
    csw.LEARNED.append((np.zeros((64, 64, 3), np.uint8), arrow_mask()))  # an older Run's
    fake = FakeClient(scroll=True)
    res = cl.learn(fake, fake, FakeR, refs=refs())
    assert not res["used"] and csw.LEARNED == [] and csw.learned_refs() is None
    assert cl.words(res).startswith("WARNING (the Run plays on)")


def test_the_lab_s_own_arrows_pass_the_shape_bar_and_no_other_cursor_does() -> None:
    """The pre-registration (2026-11-19), on the lab's references, leave-one-out: 421 of 491
    walk arrows pass, none of the 154 others."""
    if not cr.REFS_V3.exists():
        pytest.skip("the lab's cursor references are not on this host")
    z = np.load(cr.REFS_V3)
    m, cls = np.asarray(z["m"], bool), [str(c) for c in z["cls"]]
    rf = cr.RobustRefs(z["a"], m, cls)
    passed = {c: 0 for c in set(cls)}
    for i in range(len(cls)):
        if m[i].sum() < cr.MIN_PX:
            continue
        prec, cov, _ = rf._mask_terms(m[i])
        f = np.where(prec + cov > 0, 2 * prec * cov / np.maximum(prec + cov, 1e-9), 0.0)
        f[rf.ref == i, :] = 0  # leave one out
        sc = {c: float(f[rf.by_class[k]].max()) for k, c in enumerate(rf.classes)}
        passed[cls[i]] += cl.is_walk_arrow(sc)
    assert passed["walk"] == 421 and sum(v for c, v in passed.items() if c != "walk") == 0
