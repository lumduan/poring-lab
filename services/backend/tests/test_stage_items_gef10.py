"""scripts/stage_items.py stage@5 (gef10-eyes-loot.md E3): the item set per MAP. gef_fild10 stages
its drop set in balanced groups on open ground; pay_fild07's set (the default) is unchanged. Pure
functions on synthetic data; the spot check on the real map runs only where the local KB and the
client data (/dev/shm) are present, and skips cleanly otherwise."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import stage_items as si  # noqa: E402

GEF10_IDS = {7053: "cyfar", 931: "orcish_voucher", 938: "sticky_mucus", 519: "milk",
             910: "garlet", 998: "iron", 7126: "large_jellopy", 756: "rough_oridecon",
             511: "green_herb", 7270: "nursing_bottle", 1301: "axe"}  # fmt: skip


def test_gef10_set_is_the_drop_set_with_its_own_icon_dir() -> None:
    """The eleven items gef_fild10's hunts dropped (ids: data/kb/items.json + drops.json,
    gef10-prep.md 1a); its own icons in data/ (client pixels, never committed)."""
    ms = si.map_set("gef_fild10")
    assert ms.items == GEF10_IDS and list(ms.items) == list(GEF10_IDS)
    assert ms.icon_dir != si.ICON_DIR and "data" in ms.icon_dir.parts
    assert ms.per_spot == 6 and ms.clear == "end"
    assert ms.pile and ms.needs_open and ms.npc_keep
    assert ms.offsets[0] == (0, 0) and set(ms.offsets) <= set(si.OFFSETS)  # existing offsets only
    assert (0, -3) not in ms.offsets  # the pile would lie behind our own sprite
    assert len(si.spot_cells(ms)) == 11  # the 3 x 3 pile + (3, 0) and (0, 3)
    assert si.LOOT_LIFE_S > 60.0  # a floor item lives 60 s


def test_pay_fild07_defaults_are_unchanged() -> None:
    """stage@1-4's behaviour: the four targets every spot in TARGETS' order, the five offsets,
    no pile, no NPC margin, no @killmonster2; any other map falls back to it."""
    ms = si.map_set("pay_fild07")
    assert ms.items is si.TARGETS and ms.icon_dir == si.ICON_DIR
    assert ms.per_spot == 4 and ms.offsets == tuple(si.OFFSETS) and ms.clear == "none"
    assert not (ms.pile or ms.needs_open or ms.npc_keep)
    assert si.map_set("prt_fild08") is si.DEFAULT_SET
    assert si.spot_cells(ms) == sorted(si.OFFSETS)
    for seed in (0, 7, 8):
        assert si.item_groups(list(si.TARGETS), 12, 4, seed) == [[757, 756, 604, 518]] * 12
    assert si.held_refusal([(7053, 30), (931, 9)]) is None  # the default set: pay's targets only


def test_item_groups_are_balanced_seeded_and_distinct() -> None:
    ids = list(GEF10_IDS)
    g = si.item_groups(ids, 22, 6, seed=2610)
    assert len(g) == 22 and all(len(x) == 6 == len(set(x)) for x in g)
    assert all(x == [i for i in ids if i in x] for x in g)  # typed in the set's order
    assert set(Counter(i for x in g for i in x).values()) == {12}  # 132 = 11 x 12
    assert g == si.item_groups(ids, 22, 6, seed=2610)
    assert g != si.item_groups(ids, 22, 6, seed=2611)
    for n in (1, 5, 7, 13):
        c = Counter(i for x in si.item_groups(ids, n, 6, seed=3) for i in x)
        counts = [c.get(i, 0) for i in ids]
        assert max(counts) - min(counts) <= 1 and sum(counts) == 6 * n
    with pytest.raises(SystemExit):
        si.item_groups(ids, 3, 0, seed=0)


def test_held_refusal_reads_the_maps_set() -> None:
    """On gef_fild10 the hunts' own loot is in the set: clear_loot would drop those whole stacks
    with the staged copies, so a held Cyfar refuses (the store step first)."""
    why = si.held_refusal([(7053, 159), (931, 79), (504, 9)], GEF10_IDS)
    assert why is not None and "{7053: 159, 931: 79}" in why
    assert si.held_refusal([(504, 9), (7053, 0)], GEF10_IDS) is None


def test_canopy_mask_marks_the_box_of_tall_models_only() -> None:
    """A tall model (top above CANOPY_MIN_TOP) marks floor(min) .. ceil(max) of its vertex cells;
    a model whose top is exactly the bar or lower marks nothing; boxes are clipped to the map."""
    tall = (np.array([[2.4, 3.6], [4.2, 5.1]]), np.array([0.0, 10.5]))
    low = (np.array([[10.0, 10.0], [12.0, 12.0]]), np.array([0.0, 10.0]))
    edge = (np.array([[-2.0, 18.5], [1.5, 22.0]]), np.array([3.0, 40.0]))
    m = si.canopy_mask([tall, low, edge, (np.zeros((0, 2)), np.zeros(0))], (20, 20))
    want = np.zeros((20, 20), dtype=bool)
    want[3:7, 2:6] = True  # x 2..5, y 3..6
    want[18:20, 0:3] = True  # x 0..2 (clipped), y 18..19 (clipped)
    assert (m == want).all()


def test_canopy_rule_reproduces_stage2s_pay_fild07_mask() -> None:
    """The positive case: the rule rebuilds the mask stage@2 staged with (stage-c, target-items.md
    10.1) cell for cell, from the client's RSW (client data in /dev/shm; skipped without it)."""
    ms = si.map_set("pay_fild07")
    ref = Path("/dev/shm/poring-lab-tmp/payf07/canopy.npy")
    from poring_dataset import camera as cam

    need = [ref, ms.rsw, ms.models, cam.GAT_DIR / "pay_fild07.gat"]
    if not all(p is not None and p.exists() for p in need):
        pytest.skip("pay_fild07's client data is not in /dev/shm")
    assert ms.rsw is not None and ms.models is not None
    got = si.build_canopy("pay_fild07", ms.rsw, ms.models)
    assert int((got ^ np.load(ref)).sum()) == 0 and int(got.sum()) == 74319


def test_icon_clashes_guard_the_stock() -> None:
    """A staged icon within 6.0 of a kept / empty reference would make clear_loot drop the stock;
    two staged icons within 3.0 would merge. Other shapes are not compared."""
    base = np.full((16, 14), 100.0, np.float32)
    new = {"a": base, "b": base + 2.0, "c": base + 50.0}
    stock = {"white_potion": base + 5.0, "slot": np.zeros((16, 14)), "odd": np.zeros((4, 4))}
    got = si.icon_clashes(new, stock)
    assert ("a", "white_potion", 5.0) in got and ("b", "white_potion", 3.0) in got
    assert ("a", "b", 2.0) in got
    assert not [x for x in got if "c" in x[:2] or "odd" in x[:2] or "slot" in x[:2]]
    assert si.icon_clashes({"c": base + 50.0}, stock) == []


def test_spots_plan_counts_and_stands() -> None:
    spots = [(100, 100), (150, 100), (200, 100)]
    p = si.spots_plan("gef_fild10", spots, seed=1)
    assert p["floor_items"] == 18 and p["stands"] == 9 and p["clear"] == "end"
    assert sum(p["counts"].values()) == 18 and max(p["counts"].values()) <= 2
    assert all(len(g) == 6 for g in p["groups"])
    assert si.stands(spots, ((0, 0), (3, 0)))[:2] == [[100, 100], [103, 100]]
    pay = si.spots_plan("pay_fild07", spots, seed=1)
    assert pay["groups"] == [list(si.TARGETS.values())] * 3 and pay["clear"] == "none"


def _gef10_inputs_or_skip() -> None:
    from poring_dataset import camera as cam
    from poring_dataset import mapcache

    ms = si.map_set("gef_fild10")
    kb = si.ROOT / "data" / "kb"
    need = [kb / f for f in ("route.json", "first_workflow.json", "warps.json", "npc_cells.json")]
    need += [cam.GAT_DIR / "gef_fild10.gat", ms.rsw, ms.models]
    if not all(p is not None and p.exists() for p in need):
        pytest.skip("gef_fild10's KB (data/kb) or client data (/dev/shm) is not here")
    try:
        mapcache.load(prere=True)
    except mapcache.MapCacheError:
        pytest.skip("the server map cache is not generated (scripts/gen_mapcache.py)")


def test_gef10_spots_are_open_ground_away_from_warps_npcs_and_zones(tmp_path: Path) -> None:
    """The real map (skipped without its data): every spot's views AND its 3 x 3 pile lie on
    open ground (outside the widened canopy), on cells client and server both walk, outside every
    zone; spots keep >= 10 cells from warp spans and NPC cells and >= SPOT_SEP from each other."""
    _gef10_inputs_or_skip()
    import yaml

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import mapcache

    ms = si.map_set("gef_fild10")
    assert ms.rsw is not None and ms.models is not None
    canopy = si.build_canopy("gef_fild10", ms.rsw, ms.models)
    path = tmp_path / "canopy.npy"
    np.save(path, canopy)
    with pytest.raises(SystemExit):
        si.plan_spots("gef_fild10", 5, 0, None)  # open ground only
    spots = si.plan_spots("gef_fild10", 22, 2610, path)
    assert len(spots) == 22 and spots == si.plan_spots("gef_fild10", 22, 2610, path)
    kb = si.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text())["gef_fild10"]
    npcs = si.npc_cells("gef_fild10")
    zones = yaml.safe_load((si.ROOT / "config/map_zones/gef_fild10.yaml").read_text())["no_enter"]
    grown = ~si.open_area(np.ones_like(canopy), canopy)
    server = mapcache.load(prere=True)["gef_fild10"]
    walk = gatmod.parse((cam.GAT_DIR / "gef_fild10.gat").read_bytes()).walkable()
    for i, (x, y) in enumerate(spots):
        for w in warps:
            gap = max(abs(x - w["x"]) - w["span_x"], abs(y - w["y"]) - w["span_y"])
            assert gap > si.SEARCH_MARGIN, (x, y, w)
        assert all(max(abs(x - nx), abs(y - ny)) > si.SEARCH_MARGIN for nx, ny in npcs)
        for b in spots[i + 1 :]:
            assert max(abs(x - b[0]), abs(y - b[1])) >= si.SPOT_SEP
        for dx, dy in si.spot_cells(ms):
            cx, cy = x + dx, y + dy
            assert not grown[cy, cx] and walk[cy, cx] and not server.nopass(cx, cy), (cx, cy)
            for z in zones:
                xs, ys = [q[0] for q in z["polygon"]], [q[1] for q in z["polygon"]]
                assert not (min(xs) <= cx <= max(xs) and min(ys) <= cy <= max(ys)), z["id"]
