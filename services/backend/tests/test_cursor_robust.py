"""scripts/cursor_robust.py (the ROBUST cursor classifier candidate, docs/planning/cursor-robust.md)
and the pure parts of scripts/cursor_eval.py, on SYNTHETIC cursors (no client pixels): outlined
sprites drawn over textured floors, as walk6's fakes are. The properties that matter for the gate:
a 1-px offset, a hollow mask and an animated background no longer turn a cursor UNKNOWN; no shape
ever reads as another; a no-entry sign whose ring vanishes into its background is never WALK."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mods() -> tuple[ModuleType, ModuleType, ModuleType]:
    sys.path.insert(0, str(SCRIPTS))
    for name in ("walk5", "walk6"):
        _load(name)
    return _load("cursor_robust"), sys.modules["walk6"], _load("cursor_eval")


# --- synthetic sprites (BGR): a light fill inside a dark 1-px outline, hotspot at (32, 32) --------
WHITE, STEEL, RED, BLACK = (235, 225, 225), (245, 245, 250), (30, 30, 220), (20, 20, 20)
GREY = (140, 135, 150)


def _disc(cx: float, cy: float, rx: float, ry: float) -> set[tuple[int, int]]:
    yy, xx = np.mgrid[-32:32, -32:32]
    m = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0
    return {
        (int(x), int(y)) for y, x in zip(*np.nonzero(m), strict=True) for x, y in [(x - 32, y - 32)]
    }


def _outlined(fill: set[tuple[int, int]], colour: tuple[int, int, int]) -> list[Any]:
    """The fill shaded by a diagonal pattern (every third pixel grey, as the client's sprites are
    shaded: a 1-px offset then puts unlike pixels on each other) inside a dark 1-px outline."""
    edge = {
        (x, y)
        for x, y in fill
        if any((x + dx, y + dy) not in fill for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    }
    inner = fill - edge
    shade = {(x, y) for x, y in inner if (x + y) % 3 == 0}
    return [(sorted(inner - shade), colour), (sorted(shade), GREY), (sorted(edge), BLACK)]


ARROW = {(dx, dy) for dy in range(0, 20) for dx in range(0, dy // 2 + 2)}
BUBBLE = _disc(-6, -6, 12, 8)
GLOVE = _disc(-6, -4, 7, 10) | _disc(2, -10, 4, 6)
BLADE = {(k + e, k) for k in range(0, 20) for e in (-1, 0, 1)} | {(dx, 5) for dx in range(-3, 9)}
RING = {(x, y) for x, y in _disc(6, 10, 13, 13) if (x - 6) ** 2 + (y - 10) ** 2 >= 9.5**2}
SLASH = {(x, y) for x, y in _disc(6, 10, 12, 12) if abs((x - 6) - (y - 10)) <= 1}
SPRITES: dict[str, list[Any]] = {
    "walk": _outlined(ARROW, WHITE),
    "talk": _outlined(BUBBLE, WHITE),
    "pickup": _outlined(GLOVE, STEEL),
    "sword": _outlined(BLADE, STEEL),
    "noentry": _outlined(ARROW, WHITE) + [(sorted(RING | SLASH), RED)],
}


def floor(seed: int, light: bool = False) -> np.ndarray:
    """A textured floor; ``light`` is within 60 (summed) of the white fill: a hollow mask."""
    yy, xx = np.mgrid[0:64, 0:64]
    img = np.zeros((64, 64, 3), np.uint8)
    base = (215, 208, 210) if light else (40, 60, 80)
    for c in range(3):
        img[..., c] = base[c] + (xx * (3 + c + seed) + yy * (5 + 2 * c + seed)) % (
            8 if light else 30
        )
    return img


def draw(bg: np.ndarray, shape: str, dx: int = 0, dy: int = 0) -> np.ndarray:
    a = bg.copy()
    for pts, colour in SPRITES[shape]:
        for x, y in pts:
            yy, xx = 32 + y + dy, 32 + x + dx
            if 0 <= yy < 64 and 0 <= xx < 64:
                a[yy, xx] = colour
    return a


def refs(mods: tuple, shapes: tuple[str, ...] = tuple(SPRITES), per: int = 4,
         extra: list[tuple[np.ndarray, np.ndarray, str]] = ()) -> tuple[Any, Any]:  # fmt: skip
    """(robust, current) built from ``per`` hovers per shape over different floors."""
    cr, w6, _ = mods
    a, m, cls = [], [], []
    for s in shapes:
        for k in range(per):
            b = floor(k)
            h = draw(b, s)
            a.append(h)
            m.append(w6.cursor_mask(h, b))
            cls.append(s)
    for h, mk, c in extra:
        a.append(h)
        m.append(mk)
        cls.append(c)
    return cr.RobustRefs(a, m, cls), w6.CursorRefs(a, m, cls)


def read(mods: tuple, refs_: Any, a: np.ndarray, b: np.ndarray, anim: Any = None) -> dict:
    _, w6, _ = mods
    b_mod = np.where(anim[..., None], a, b) if anim is not None else b
    return dict(refs_.match(a, w6.cursor_mask(a, b_mod)))


# --- the classifier -------------------------------------------------------------------------------
def test_every_shape_reads_itself_on_a_new_floor_through_walk6s_interface(mods: tuple) -> None:
    robust, current = refs(mods)
    for s in SPRITES:
        b = floor(9)
        out = read(mods, robust, draw(b, s), b)
        assert out["shape"] == s, out
        assert {"shape", "iou", "col"} <= set(out) and out["shift"] == [0, 0]
        assert read(mods, current, draw(b, s), b)["shape"] == s  # the gate agrees here


def test_a_one_pixel_offset_fails_the_gate_but_not_the_robust_reader(mods: tuple) -> None:
    """npc-click-test.md section 3: a 1-px misregistration puts outline on fill; walk6's colour
    check fails at a still-good IoU. The robust reader searches +-2 px and reports the shift."""
    robust, current = refs(mods)
    b = floor(9)
    for s, (dx, dy) in (("talk", (1, 0)), ("talk", (0, -1)), ("walk", (1, 1)), ("sword", (2, 0))):
        a = draw(b, s, dx, dy)
        assert read(mods, current, a, b)["shape"] == "unknown"
        out = read(mods, robust, a, b)
        assert out["shape"] == s and out["shift"] == [dx, dy], out


def test_a_hollow_mask_on_a_light_floor_still_reads_by_the_cursors_own_colours(mods: tuple) -> None:
    """A white bubble on a floor within 60 of its fill: |A - B| keeps only the outline."""
    cr, w6, _ = mods
    robust, _ = refs(mods)
    b = floor(3, light=True)
    a = draw(b, "talk")
    mask = w6.cursor_mask(a, b)
    filled = sum(1 for _ in BUBBLE)
    assert mask.sum() < 0.6 * filled  # hollow
    assert robust.match(a, mask)["shape"] == "talk"


def test_animated_pixels_removed_from_the_mask_do_not_hide_the_cursor(mods: tuple) -> None:
    """Prober9 drops the animated pixels (a bobbing Poring) from |A - B|: a third of the sword's
    mask gone still reads SWORD (the colour is read on A; coverage needs only COV_MIN). (A band
    that SPLITS the cursor near the hotspot leaves walk6.cursor_mask a fragment: that is the mask,
    not the classifier; cursor-robust.md section 2.)"""
    robust, _ = refs(mods)
    b = floor(9)
    a = draw(b, "sword")
    anim = np.zeros((64, 64), bool)
    anim[44:56, :] = True  # the blade's lower half over animated pixels
    _, w6, _ = mods
    assert (
        w6.cursor_mask(a, np.where(anim[..., None], a, b)).sum() < 0.7 * w6.cursor_mask(a, b).sum()
    )
    assert read(mods, robust, a, b, anim)["shape"] == "sword"


def test_extra_content_in_the_mask_is_never_the_arrow(mods: tuple) -> None:
    """Two-sided: a sprite merged into the arrow's mask lowers prec; unknown, not walk."""
    robust, _ = refs(mods)
    b = floor(9)
    a = draw(b, "walk")
    a[44:60, 36:56] = (200, 60, 200)  # something drawn next to the arrow, touching it
    out = read(mods, robust, a, b)
    assert out["shape"] == "unknown"


def test_a_no_entry_sign_whose_ring_matches_its_background_is_never_walk(mods: tuple) -> None:
    """The ring and slash on a background of their own red: |A - B| is the arrow alone, a perfect
    WALK by mask. The no-entry prototype's colours are all in A, so it competes without
    coverage: ambiguous -> UNKNOWN (fail closed). The gate today reads it WALK."""
    cr, w6, _ = mods
    robust, current = refs(mods)
    b = np.zeros((64, 64, 3), np.uint8)
    b[...] = RED
    a = draw(b, "noentry")
    mask = w6.cursor_mask(a, b)
    out = robust.match(a, mask)
    assert out["shape"] == "unknown" and out["why"].startswith("ambiguous:"), out
    assert current.match(a, mask)["shape"] == "walk"  # the documented gap in the gate today
    b2 = floor(9)
    assert read(mods, robust, draw(b2, "noentry"), b2)["shape"] == "noentry"


def test_no_shape_reads_as_another_under_shifts_noise_and_floors(mods: tuple) -> None:
    robust, _ = refs(mods)
    rng = np.random.default_rng(7)
    wrong = []
    for s in SPRITES:
        for seed in (11, 12):
            for light in (False, True):
                b = floor(seed, light)
                for dx, dy in ((0, 0), (1, 0), (-1, 1), (2, -2)):
                    a = draw(b, s, dx, dy)
                    a = np.clip(a + rng.normal(0, 4, a.shape), 0, 255).astype(np.uint8)
                    got = read(mods, robust, a, b)["shape"]
                    if got not in (s, "unknown"):
                        wrong.append((s, got, seed, light, dx, dy))
    assert wrong == []


def test_no_cursor_and_no_match_are_unknown(mods: tuple) -> None:
    robust, _ = refs(mods)
    b = floor(9)
    assert robust.match(b, np.zeros((64, 64), bool))["why"] == "no_cursor"
    a = b.copy()
    a[10:30, 10:30] = (0, 200, 0)  # a square: no cursor shape
    out = read(mods, robust, a, b)
    assert out["shape"] == "unknown" and out["why"] in ("no_match", "low_score")


def test_the_class_consensus_trims_what_moved_behind_the_cursor(mods: tuple) -> None:
    """A sword reference with a moving blob baked into its mask (walk@6's single parked frame) is
    trimmed to the sword; a 'reference' whose mask misses the class altogether is dropped."""
    cr, w6, _ = mods
    b = floor(5)
    h = draw(b, "sword")
    polluted = w6.cursor_mask(h, b)
    blob = np.zeros((64, 64), bool)
    blob[38:52, 20:34] = True
    polluted = polluted | blob
    stray = np.zeros((64, 64), bool)
    stray[2:10, 50:60] = True
    robust, _ = refs(mods, per=8, extra=[(h, polluted, "sword"), (h, stray, "sword")])
    n = len(robust.cls_all)
    assert n - 1 in robust.dropped and n - 2 not in robust.dropped
    k = int(np.nonzero(robust.ref == n - 2)[0][0])
    sup = np.unpackbits(robust.s_bits[k].view(np.uint8), bitorder="little").reshape(64, 64)
    assert not sup[blob & ~w6.cursor_mask(h, b)].any()


def test_the_fast_path_decides_exactly_as_the_exhaustive_one(mods: tuple) -> None:
    cr, _, _ = mods
    robust, _ = refs(mods)
    rng = np.random.default_rng(3)
    for s in SPRITES:
        for dx, dy in ((0, 0), (1, 0), (0, 2), (-2, -1)):
            b = floor(int(rng.integers(0, 20)), bool(rng.integers(0, 2)))
            a = np.clip(draw(b, s, dx, dy) + rng.normal(0, 6, (64, 64, 3)), 0, 255)
            a = a.astype(np.uint8)
            f, e = read(mods, robust, a, b), None
            _, w6, _ = mods
            e = robust.match(a, w6.cursor_mask(a, b), exhaustive=True)
            assert f["shape"] == e["shape"] and f.get("why") == e.get("why")
            if e["score"] >= cr.PREC_MIN:
                assert f["score"] == e["score"]


def test_leave_one_out_by_exclude_and_the_thresholds_contract(mods: tuple) -> None:
    cr, _, _ = mods
    robust, _ = refs(mods, per=1)
    b = floor(9)
    a = draw(b, "pickup")
    _, w6, _ = mods
    k = robust.cls_all.index("pickup")
    assert robust.match(a, w6.cursor_mask(a, b))["shape"] == "pickup"
    assert robust.match(a, w6.cursor_mask(a, b), exclude=[k])["shape"] == "unknown"
    # a competitor below PREC_MIN is reported as a lower bound: no decision may depend on it
    for c, f in cr.FLOORS.items():
        assert f - cr.MARGINS[c] >= cr.PREC_MIN, c
    assert cr.DEFAULT_FLOOR - cr.DEFAULT_MARGIN >= cr.PREC_MIN
    assert cr.MARGINS["walk"] == max(cr.MARGINS.values())  # the clickable shape: strictest
    assert cr.FLOORS["walk"] == max(cr.FLOORS.values())


# --- the evaluator's pure parts ------------------------------------------------------------------
def test_composite_moves_the_sprite_and_blends_a_half_pixel(mods: tuple) -> None:
    _, _, ce = mods
    bg = np.full((64, 64, 3), 50, np.uint8)
    col = np.full((64, 64, 3), 250, np.uint8)
    alpha = np.zeros((64, 64), bool)
    alpha[30:34, 30:34] = True
    a = ce.composite(alpha, col, bg, 2, -1)
    assert (a[29:33, 32:36] == 250).all() and a[33, 32, 0] == 50
    h = ce.composite(alpha, col, bg, 0.5, 0)
    assert h[31, 30, 0] == 150 and h[31, 31, 0] == 250 and h[31, 34, 0] == 150


def test_blur_jpeg_noise_and_bob_keep_shapes(mods: tuple) -> None:
    _, _, ce = mods
    img = floor(4)
    assert ce.blur(img, 0.8).shape == img.shape
    assert abs(float(ce.blur(img, 0.8).mean()) - float(img.mean())) < 2
    assert ce.jpeg(img, 70).shape == img.shape and ce.jpeg(img, 70).dtype == np.uint8
    n = ce.noise(img, 10, np.random.default_rng(0))
    assert 5 < float(np.abs(n.astype(int) - img).mean()) < 12
    patch = floor(2)
    patch[20:40, 20:40] = (160, 150, 240)  # a pink blob (BGR)
    b1, b2, abg = ce.bob_frames(patch, floor(2), 2)
    assert not np.array_equal(b1, b2) and not np.array_equal(b2, abg)
    assert (np.abs(b1.astype(int) - b2.astype(int)).sum(-1) > 60).any()


def test_neighbours_and_the_table(mods: tuple) -> None:
    _, _, ce = mods
    srcs = [
        ce.Source(None, None, None, "walk", s)
        for s in ("outdoor/4", "outdoor/5", "outdoor/6", "indoor/5", "npc/x.npz")
    ]
    assert ce.neighbours(srcs, 1, 1) == [0, 1, 2]
    assert ce.neighbours(srcs, 4, 3) == [4] and ce.neighbours(srcs, 1, 0) == [1]
    summary = {"conditions": ["own"], "summary": {
        "current": {"own": {"walk": {"walk": 8, "unknown": 1, "talk": 1}}},
        "robust": {"own": {"walk": {"walk": 10}}}}}  # fmt: skip
    t = ce.table(summary)
    assert "8/1/1 \\| 10/0/0" in t and "walk->talk x1; 0" in t
    tot = ce.totals(summary, ["own"])
    assert tot["current"]["walk"]["wrong"] == 1 and tot["robust"]["walk"]["read"] == 10


def test_series_verdicts_are_the_gates_two_reads(mods: tuple) -> None:
    _, _, ce = mods
    u, w, t = "unknown", "walk", "talk"
    assert ce.series_verdicts([u, w, u, u, u, w]) == (w, w)
    assert ce.series_verdicts([u, u, u, w, w, w]) == (u, w)
    assert ce.series_verdicts([t, w, w, u, u, u]) == (t, u)


def test_live_scores_both_classifiers_on_a_sessions_crops(mods: tuple, tmp_path: Path) -> None:
    """A synthetic live session (npc_click_test / cursor_probe layout): demo.jsonl records whose
    evidence names a crop with a 6-grab series; labels by crop."""
    import argparse
    import json

    cr, w6, ce = mods
    a, m, cls = [], [], []
    for s in SPRITES:
        for k in range(3):
            b = floor(k)
            h = draw(b, s)
            a.append(h)
            m.append(w6.cursor_mask(h, b))
            cls.append(s)
    refs = tmp_path / "refs.npz"
    np.savez_compressed(refs, a=np.array(a), m=np.array(m), cls=np.array(cls),
                        src=np.array([f"syn/{i}" for i in range(len(cls))]))  # fmt: skip
    ses = tmp_path / "ses"
    (ses / "crops").mkdir(parents=True)
    recs = []
    for i, (s, kind, dx) in enumerate((("talk", "sprite", 1), ("walk", "control", 0))):
        b = floor(9)
        h = draw(b, s, dx, 0)
        mk = w6.cursor_mask(h, b)
        np.savez_compressed(ses / "crops" / f"{i:05d}.npz", a=h, mask=mk,
                            a_series=np.stack([h] * 6), mask_series=np.stack([mk] * 6))  # fmt: skip
        recs.append({"outcome": {"evidence": {"crop": f"crops/{i:05d}.npz", "kind": kind}}})
    (ses / "demo.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"crops/00000.npz": "talk", "crops/00001.npz": "walk"}))
    args = argparse.Namespace(
        summary=ses, labels=labels, refs=refs, out=tmp_path / "out", verdict=""
    )
    res = ce.cmd_live(args)
    assert res["probes"] == 2
    assert res["robust"]["twice"]["sprite"] == {"talk": 1}  # the 1-px offset bubble, read twice
    assert res["current"]["first"]["sprite"] == {"unknown": 1}
    assert res["robust"]["cross_shape"] == [] and res["robust"]["walk_from_other"] == 0
    assert res["robust"]["twice"]["control"] == {"walk": 1}
    args.verdict = "talk"
    sheet = ce.cmd_sheet(args)
    assert sheet["crops"] == 1 and json.loads(Path(sheet["order"]).read_text()) == [
        "crops/00000.npz"
    ]


def test_the_sword_probe_plan_is_on_the_box_with_controls_beside_it(mods: tuple) -> None:
    probe = _load("cursor_probe")
    attack = ((0.5, 1.0, -8.0), (0.5, 0.5, 0.0), (0.5, 0.3, 0.0))
    pts = probe.sword_points((600, 300, 640, 340), attack)
    sword = [p for p in pts if p["kind"] == "sword"]
    ctrl = [p for p in pts if p["kind"] == "control"]
    assert len(sword) == 3 + len(probe.GRID)
    assert sword[0]["at"] == (620.0, 332.0)  # loot@1's first attack point: the feet, 8 px up
    assert all(600 <= p["at"][0] <= 640 and 300 <= p["at"][1] <= 340 for p in sword)
    assert ctrl and all(abs(p["at"][0] - 620) == probe.CONTROL_OFF * 40 for p in ctrl)
    assert {p["side"] for p in ctrl} == {1, -1}
    assert all(
        (i + 1) % probe.CONTROL_EVERY == 0 for i, p in enumerate(pts) if p["kind"] == "control"
    )
    kept = probe.usable(pts, lambda u, v: u < 610)  # a "UI window" over the left
    assert kept and all(p["at"][0] >= 610 for p in kept)
    assert probe.usable([{"at": (30.0, 300.0)}], lambda u, v: False) == []  # the grab leaves


# --- robust2: the no-entry RING over the series (cursor@2) ----------------------------------------
def test_the_ring_counts_red_cursor_pixels_inside_the_mask_only(mods: tuple) -> None:
    """The ring is red CURSOR pixels: the no-entry sign carries them; the arrow, the bubble, the
    glove and the blade carry none; a red floor outside the cursor mask adds none."""
    cr, w6, _ = mods
    b = floor(3)
    for shape in SPRITES:
        a = draw(b, shape)
        n = cr.ring_pixels(a, w6.cursor_mask(a, b))
        assert (n >= cr.RING_MIN) == (shape == "noentry"), (shape, n)
    red = np.zeros((64, 64, 3), np.uint8)
    red[...] = RED
    red[20:44, 20:44] = (40, 60, 80)  # the hotspot's surroundings plain, the rest red floor
    a = draw(red, "walk")
    assert cr.ring_pixels(a, w6.cursor_mask(a, red)) == 0


def test_a_blink_frame_in_a_no_entry_series_never_reads_walk(mods: tuple) -> None:
    """cursor@1's bar-1 failure: both read groups land on the blink (the bare arrow) -> read twice
    says WALK. One ring grab anywhere in the series makes it NOENTRY."""
    cr, _, _ = mods
    w, u, n = "walk", "unknown", "noentry"
    assert cr.series_verdict([w, u, u, w, u, u], [0, 0, 210, 0, 0, 0]) == (n, "ring")
    assert cr.series_verdict([w, u, u, w, u, u], [0, 1, 6, 0, 3, 0]) == (w, "twice")
    assert cr.series_verdict([u, u, u, w, w, w], [0] * 6) == (u, "not_twice")
    assert cr.series_verdict(["talk", u, u, "talk", u, u], [0] * 6) == ("talk", "twice")
    assert cr.series_verdict([w, u, u, w, u, u], [0, 0, 0, 0, 0, cr.RING_MIN]) == (n, "ring")
    with pytest.raises(ValueError):
        cr.series_verdict([w] * 6, [0] * 5)


def test_live_reports_robust2_and_a_blink_series_is_noentry(mods: tuple, tmp_path: Path) -> None:
    """cmd_live on a synthetic no-entry series whose read groups start on blink frames: robust
    reads it WALK twice (cursor@1's failure); robust2 reads NOENTRY by the ring."""
    import argparse
    import json

    cr, w6, ce = mods
    a, m, cls = [], [], []
    for s in SPRITES:
        for k in range(3):
            b = floor(k)
            h = draw(b, s)
            a.append(h)
            m.append(w6.cursor_mask(h, b))
            cls.append(s)
    refs = tmp_path / "refs.npz"
    np.savez_compressed(refs, a=np.array(a), m=np.array(m), cls=np.array(cls),
                        src=np.array([f"syn/{i}" for i in range(len(cls))]))  # fmt: skip
    ses = tmp_path / "ses"
    (ses / "crops").mkdir(parents=True)
    b = floor(9)
    series = [draw(b, s) for s in ("walk", "walk", "noentry", "walk", "noentry", "noentry")]
    masks = [w6.cursor_mask(h, b) for h in series]
    np.savez_compressed(ses / "crops" / "00000.npz", a=series[0], mask=masks[0],
                        a_series=np.stack(series), mask_series=np.stack(masks))  # fmt: skip
    rec = {"outcome": {"evidence": {"crop": "crops/00000.npz", "kind": "cell"}}}
    (ses / "demo.jsonl").write_text(json.dumps(rec) + "\n")
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"crops/00000.npz": "noentry"}))
    args = argparse.Namespace(summary=ses, labels=labels, refs=refs, out=tmp_path / "out",
                              verdict="")  # fmt: skip
    res = ce.cmd_live(args)
    assert res["robust"]["twice"]["cell"] == {"walk": 1}
    assert res["robust"]["walk_from_other"] == 1
    assert res["robust2"]["twice"]["cell"] == {"noentry": 1}
    assert res["robust2"]["walk_from_other"] == 0 and res["robust2"]["cross_shape"] == []
    row = json.loads((tmp_path / "out" / "live-ses.json").read_text())["rows"][0]
    assert row["robust2"]["why"] == "ring"
    assert sum(r >= cr.RING_MIN for r in row["robust2"]["rings"]) == 3
