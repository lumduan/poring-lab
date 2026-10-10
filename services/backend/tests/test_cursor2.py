"""cursor@2 (docs/demonstrations.md 3.36): the blind labelling sets (scripts/cursor2_truth.py) and
the scorer (scripts/cursor2_score.py), on synthetic `cursor_eval.py live` outputs (no client
pixels). The properties the bars rest on: every read is judged against the image it came from; a
WALK series that shows the no-entry sign fails 1b; a WALK series without agreement is never a pass;
too few probes is INCONCLUSIVE, never PASS."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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
def mods() -> tuple[ModuleType, ModuleType]:
    return _load("cursor2_truth"), _load("cursor2_score")


A, B = "20261010T150000-demo-npc-click-probe-alberta", "20261010T140000-demo-cursor-probe-sword"


def row(crop: str, kind: str, shapes: list[str], twice: str, r2: str | None = None,
        gate: str | None = None) -> dict[str, Any]:  # fmt: skip
    first = next((s for s in shapes[:3] if s != "unknown"), "unknown")
    g = gate if gate is not None else twice
    return {"crop": crop, "kind": kind,
            "current": {"shapes": shapes, "first": first, "twice": g},
            "robust": {"shapes": shapes, "first": first, "twice": twice},
            "robust2": {"shapes": shapes, "first": first, "twice": r2 or twice}}  # fmt: skip


W, T, S, U, N = "walk", "talk", "sword", "unknown", "noentry"


def lives(n_talk: int = 210, n_sword: int = 110, n_walk: int = 100) -> dict[str, Any]:
    ra = [row(f"crops/t{i:04d}.npz", "sprite", [T, U, U, T, U, U], T) for i in range(n_talk)]
    ra += [row(f"crops/w{i:04d}.npz", "cell", [W, U, U, W, U, U], W) for i in range(n_walk)]
    # cursor@1's failure: grab 0 shows the ring (read unknown), both reads land on blink frames
    # (the bare arrow, labelled walk) -> robust WALK; robust2 NOENTRY by the ring
    ra.append(row("crops/blink.npz", "cell", [U, W, U, W, U, U], W, r2=N))
    rb = [
        row(f"crops/s{i:04d}.npz", "sword", [S, U, U, S, U, U], S, gate=U) for i in range(n_sword)
    ]
    rb += [row(f"crops/c{i:04d}.npz", "control", [W, U, U, W, U, U], W) for i in range(20)]
    return {A: {"rows": ra}, B: {"rows": rb}}


def truth_of(crop: str) -> str:
    name = crop.split("/")[1]
    return {"t": T, "w": W, "s": S, "c": W, "b": N}[name[0]]


def labelled(m: tuple, lv: dict[str, Any], series: dict[str, str] | None = None) -> Any:
    tr, sc = m
    items = tr.image_items(lv)
    labels = {str(i): (truth_of(c) if g == 0 else W if c.endswith("blink.npz") else truth_of(c))
              for i, (_, c, g) in enumerate(items)}  # fmt: skip
    strips = tr.strip_items(lv)
    series = series or {}
    slab = {str(i): series.get(c, "no") for i, (_, c) in enumerate(strips)}
    img = sc.agree(items, labels, labels)
    ser = sc.agree(strips, slab, slab)
    return items, strips, img, ser


def test_the_image_set_holds_grab_0_and_every_read_grab_shuffled(mods: tuple) -> None:
    tr, _ = mods
    lv = {A: {"rows": [row("crops/x.npz", "cell", [U, W, U, U, U, W], W)]}}
    items = tr.image_items(lv)
    assert sorted(g for _, _, g in items) == [0, 1, 5]
    assert tr.read_grabs([U, U, U, U, U, U]) == []


def test_the_strip_set_is_every_robust2_walk_series_and_as_many_others(mods: tuple) -> None:
    tr, _ = mods
    lv = lives()
    strips = tr.strip_items(lv)
    walks = [r for x in lv.values() for r in x["rows"] if r["robust2"]["twice"] == W]
    assert len(strips) == 2 * len(walks)
    names = {c for _, c in strips}
    assert all(r["crop"] in names for r in walks)


def test_robust2_passes_where_robust_fails_as_written(mods: tuple) -> None:
    _, sc = mods
    lv = lives()
    _, _, img, ser = labelled(mods, lv)
    res = sc.score(lv, img, ser, B)
    assert any("blink.npz noentry->walk" in x for x in res["robust"]["1c_as_written"])
    assert not res["robust2"]["1c_as_written"]
    assert res["robust2"]["pooled"]["noentry"] == {"k": 1, "n": 1, "rate": 1.0, "ci": [0.207, 1.0]}
    assert res["verdict"] == "PASS", res["why"]
    assert res["robust2"]["per_map"]["alberta"]["talk"]["n"] == 210


def test_a_walk_series_showing_the_sign_fails_and_disagreement_is_inconclusive(mods: tuple) -> None:
    tr, sc = mods
    lv = lives()
    _, _, img, ser = labelled(mods, lv, {"crops/w0003.npz": "yes"})
    res = sc.score(lv, img, ser, B)
    assert res["verdict"] == "FAIL" and res["robust2"]["1b"]["errors"]
    strips = tr.strip_items(lv)
    a = {str(i): "no" for i in range(len(strips))}
    b = dict(a)
    k = next(i for i, (_, c) in enumerate(strips) if c == "crops/w0004.npz")
    b[str(k)] = "yes"
    res = sc.score(lv, img, sc.agree(strips, a, b), B)
    assert res["verdict"] == "INCONCLUSIVE" and res["robust2"]["1b"]["unclear"]


def test_a_read_judged_against_its_own_image(mods: tuple) -> None:
    """A read from grab 3 is judged against grab 3's label, not grab 0's."""
    _, sc = mods
    lv = lives()
    lv[A]["rows"].append(row("crops/t9999.npz", "sprite", [U, U, U, W, U, U], U))
    _, _, img, ser = labelled(mods, lv)
    img[(A, "crops/t9999.npz", 3)] = T  # the image the WALK read came from shows the bubble
    res = sc.score(lv, img, ser, B)
    assert res["robust2"]["1a"]["walk_on_other"] == 1 and res["verdict"] == "FAIL"


def test_too_few_probes_is_inconclusive_and_the_gate_margins_apply(mods: tuple) -> None:
    _, sc = mods
    lv = lives(n_talk=50)
    _, _, img, ser = labelled(mods, lv)
    assert sc.score(lv, img, ser, B)["verdict"] == "INCONCLUSIVE"
    lv = lives()
    for r in lv[B]["rows"]:
        r["current"]["twice"] = r["robust"]["twice"]  # the gate as good as robust2 on SWORD
    _, _, img, ser = labelled(mods, lv)
    res = sc.score(lv, img, ser, B)
    assert res["verdict"] == "FAIL" and any(w.startswith("3:") for w in res["why"])
