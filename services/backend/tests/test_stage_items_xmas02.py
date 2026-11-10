"""scripts/stage_items.py stage@8 (docs/planning/xmas02-detector.md Amendment O.6 / O.11, ACCEPTED
by O1 2026-11-10; tool T-O4): xmas_dun02 stages O.11's 12 floor-item ids in balanced groups of 6,
its spots ONLY on the watch lattice's TRAIN stands with every stand outside 3a's TEST blocks, one
@killmonster2 at each spot (the MVP clock), and ``cut-grf --check`` reports the masked set's write
gate offline without writing. Pure parts and the run's GM lines through fakes; the real map's spot
check runs only where its KB and client data are present."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import stage_items as si  # noqa: E402
import watch_lattice as wl  # noqa: E402

O11_IDS = [911, 912, 538, 539, 1098, 507, 529, 998, 722, 530, 756, 12001]  # O.11's twelve
# Amendment O3: Scell 911 out; the 13th, Cold Scroll 688, is ambiguous with Holy Scroll 12001's icon
# (2.34 < ICON_AMBIGUOUS 20), so the 14th by the ranking, 11002, joins
O3_IDS = [912, 538, 539, 1098, 507, 529, 998, 722, 530, 756, 12001, 11002]


def test_xmas02_set_is_o3s_twelve_ids_in_groups_of_six() -> None:
    ms = si.map_set("xmas_dun02")
    assert list(ms.items) == O3_IDS and len(set(ms.items.values())) == 12
    assert 911 not in ms.items and 688 not in ms.items  # O3: Scell out; the 13th unusable
    assert O3_IDS[:11] == [i for i in O11_IDS if i != 911]  # O.11's order kept
    assert ms.per_spot == 6 and ms.offsets == ((0, 0), (3, 0), (0, 3)) and ms.pile
    assert ms.clear == "spot" and ms.test_rule == wl.TEST_RULE == (26, 3, 5)
    assert ms.stands is not None and ms.stands.name == "lattice-train.json"
    assert str(ms.stands).startswith("/dev/shm/")  # client-derived (the GAT's stands)
    assert ms.icon_dir == si.ICON_DIR / "xmas_dun02" and ms.spot_sep == si.SPOT_SEP
    assert not ms.needs_open and not ms.npc_keep
    g = si.item_groups(O3_IDS, 18, 6, seed=2611)
    assert set(Counter(i for x in g for i in x).values()) == {9}  # 108 = 12 x 9


def test_the_other_maps_are_unchanged() -> None:
    gef = si.map_set("gef_fild10")
    assert gef.stands is None and gef.test_rule is None and gef.clear == "end"
    pay = si.map_set("pay_fild07")
    assert pay.stands is None and pay.clear == "none" and pay.spot_sep == si.SPOT_SEP


def test_pick_stands_keeps_every_stand_off_test_blocks() -> None:
    """3a: a stand is TEST when (x // 26 + 3 (y // 26)) mod 5 == 0; a spot whose own cell or a
    view (+3, 0) / (0, +3) is in a TEST block is never drawn; the pile and views must be in the
    area; the draw is seeded and >= sep apart."""
    area = np.ones((260, 260), bool)
    cells = [(x, y) for x in range(5, 255, 7) for y in range(5, 255, 7)]
    ms = si.map_set("xmas_dun02")
    need, views = si.spot_cells(ms), ms.offsets
    got = si.pick_stands(cells, area, 18, 7, need, views, (26, 3, 5), 25)
    assert len(got) == 18 and got == si.pick_stands(cells, area, 18, 7, need, views,
                                                    (26, 3, 5), 25)  # fmt: skip
    assert got != si.pick_stands(cells, area, 18, 8, need, views, (26, 3, 5), 25)
    for i, (x, y) in enumerate(got):
        assert (x, y) in cells
        assert not any(wl.is_test((x + dx, y + dy)) for dx, dy in views)
        for b in got[i + 1 :]:
            assert max(abs(x - b[0]), abs(y - b[1])) >= 25
    t = (77, 10)  # block (2, 0): TRAIN; its views (80, 10) block (3, 0) and (77, 13): TRAIN
    assert not any(wl.is_test((t[0] + dx, t[1] + dy)) for dx, dy in views)
    assert si.pick_stands([t], area, 5, 0, need, views, (26, 3, 5), 1) == [t]
    bad = (129, 10)  # block (4, 0): TRAIN; its (+3, 0) view (132, 10) is block (5, 0): TEST
    assert not wl.is_test(bad) and wl.is_test((132, 10))
    assert si.pick_stands([bad], area, 5, 0, need, views, (26, 3, 5), 1) == []
    assert si.pick_stands([bad], area, 5, 0, need, views, None, 1) == [bad]
    hole = area.copy()
    hole[11, 77] = False  # the drop pile's (0, +1) cell is not walkable
    assert si.pick_stands([t], hole, 5, 0, need, views, (26, 3, 5), 1) == []


def test_lattice_cells_reads_the_watch_lattice(tmp_path: Path) -> None:
    p = tmp_path / "lattice-train.json"
    p.write_text(json.dumps([{"x": 72, "y": 16}, {"x": 82, "y": 16}]))
    assert si.lattice_cells(p) == [(72, 16), (82, 16)]
    with pytest.raises(SystemExit, match="watch_lattice"):
        si.lattice_cells(tmp_path / "missing.json")


def test_spots_plan_for_xmas02() -> None:
    spots = [(50 + 30 * i, 60) for i in range(18)]
    p = si.spots_plan("xmas_dun02", spots, seed=2611)
    assert p["floor_items"] == 108 and p["stands"] == 54 and p["clear"] == "spot"
    assert set(p["counts"].values()) == {9} and all(len(g) == 6 for g in p["groups"])


def _masked(rng: np.random.Generator) -> np.ma.MaskedArray:
    t = rng.integers(20, 230, (16, 14)).astype(np.float32)
    item = np.zeros((16, 14), bool)
    item[2:14, 4:13] = True
    return np.ma.MaskedArray(t, mask=~item)


def test_own_set_nearest_flags_look_alike_templates() -> None:
    rng = np.random.default_rng(4)
    a = _masked(rng)
    b = np.ma.MaskedArray(a.data + 1.0, mask=a.mask)  # nearly the same icon
    c = _masked(rng)
    got = si.own_set_nearest({"a": a, "b": b, "c": c})
    assert got["a"][0] == "b" and got["a"][1] <= 1.0 and got["c"][1] > 20.0


def _xmas_inputs_or_skip() -> None:
    from poring_dataset import camera as cam
    from poring_dataset import mapcache

    ms = si.map_set("xmas_dun02")
    kb = si.ROOT / "data" / "kb"
    need = [kb / "warps.json", kb / "route.json", cam.GAT_DIR / "xmas_dun02.gat", ms.stands]
    if not all(p is not None and p.exists() for p in need):
        pytest.skip("xmas_dun02's KB (data/kb) or client data (/dev/shm) is not here")
    try:
        mapcache.load(prere=True)
    except mapcache.MapCacheError:
        pytest.skip("the server map cache is not generated (scripts/gen_mapcache.py)")


def test_xmas02_spots_are_train_stands_off_test_blocks_and_warps() -> None:
    """The real map (skipped without its data): 18 spots, each a lattice TRAIN stand, every
    stand (spot + views) outside 3a's TEST blocks, the views and the 3 x 3 pile walkable on the
    client GAT and the server's map cache, >= 10 cells off every warp span, >= SPOT_SEP apart."""
    _xmas_inputs_or_skip()
    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_dataset import mapcache

    ms = si.map_set("xmas_dun02")
    assert ms.stands is not None
    spots = si.plan_spots("xmas_dun02", 18, 2611101, None)
    assert len(spots) == 18 and spots == si.plan_spots("xmas_dun02", 18, 2611101, None)
    train = set(si.lattice_cells(ms.stands))
    warps = json.loads((si.ROOT / "data" / "kb" / "warps.json").read_text())["xmas_dun02"]
    server = mapcache.load(prere=True)["xmas_dun02"]
    walk = gatmod.parse((cam.GAT_DIR / "xmas_dun02.gat").read_bytes()).walkable()
    for i, (x, y) in enumerate(spots):
        assert (x, y) in train
        assert not any(wl.is_test((x + dx, y + dy)) for dx, dy in ms.offsets)
        for w in warps:
            gap = max(abs(x - w["x"]) - w["span_x"], abs(y - w["y"]) - w["span_y"])
            assert gap > si.SEARCH_MARGIN, (x, y, w)
        for b in spots[i + 1 :]:
            assert max(abs(x - b[0]), abs(y - b[1])) >= si.SPOT_SEP
        for dx, dy in si.spot_cells(ms):
            assert walk[y + dy, x + dx] and not server.nopass(x + dx, y + dy), (x + dx, y + dy)


def test_cut_grf_check_reports_the_gate_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """stage@8: ``cut-grf --check`` on synthetic BMPs: the missing screen-cut references and
    every other refusal (a tiny icon's < 40 item pixels) are REPORTED apart, nothing is written;
    without --check the same gate refuses."""
    import gm_state
    from PIL import Image

    rng = np.random.default_rng(9)
    items = {911: "scell", 912: "zargon"}
    icons = tmp_path / "bmp"
    icons.mkdir()
    lines = []
    for iid, name in items.items():
        rgb = np.zeros((24, 24, 3), np.uint8)
        rgb[...] = (255, 0, 255)
        if name == "scell":
            rgb[4:9, 4:10] = rng.integers(20, 230, (5, 6, 3), dtype=np.uint8)  # 30 item pixels
        else:
            rgb[1:20, 2:18] = rng.integers(20, 230, (19, 16, 3), dtype=np.uint8)
        Image.fromarray(rgb).save(icons / f"res{iid}.bmp")
        lines.append(f"{iid}#res{iid}#")
    table = tmp_path / "table.txt"
    table.write_bytes("\n".join(lines).encode("cp949"))
    out_dir = tmp_path / "icons-out"
    ms = si.map_set("xmas_dun02")
    monkeypatch.setitem(si.MAP_SETS, "xmas_dun02", si.replace(ms, items=items, icon_dir=out_dir))
    monkeypatch.setattr(
        gm_state, "load_loot_refs", lambda: {"slot": ("empty", np.full((16, 14), 30.0, np.float32))}
    )
    got = si.cut_grf("xmas_dun02", table, icons, check=True)
    assert got["check"] is True and got["written"] == []
    assert got["screen_refs_missing"] == ["scell", "zargon"]
    assert got["items"]["scell"] == 30 and got["items"]["zargon"] > 40
    assert got["other_refusals"] == ["scell: 30 item pixels < 40"]
    assert set(got["own_set_nearest"]) == {"scell", "zargon"}
    assert got["own_set_ambiguous"] == [] and got["passes_once_screen_cut"] is False
    assert not out_dir.exists()
    with pytest.raises(SystemExit, match="refused"):
        si.cut_grf("xmas_dun02", table, icons)
    assert not out_dir.exists()


def test_cut_grf_check_predicts_the_sets_own_ambiguous_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """O3's case: two items of the set whose grey icons nearly match (Cold Scroll / Holy Scroll
    read 2.34 apart) are both "unknown" to clear_loot: --check names the pair and says the set
    will not pass once screen-cut; a set without such a pair (and no other refusal) will."""
    import gm_state
    from PIL import Image

    rng = np.random.default_rng(11)
    base = np.zeros((24, 24, 3), np.uint8)
    base[...] = (255, 0, 255)
    base[1:20, 2:18] = rng.integers(20, 230, (19, 16, 3), dtype=np.uint8)
    other = base.copy()
    other[1:20, 2:18] = rng.integers(20, 230, (19, 16, 3), dtype=np.uint8)
    twin = base.copy()
    twin[1:20, 2:18] = np.clip(twin[1:20, 2:18].astype(int) + 2, 0, 255).astype(np.uint8)
    icons = tmp_path / "bmp"
    icons.mkdir()
    for name, img in (("r1", base), ("r2", twin), ("r3", other)):
        Image.fromarray(img).save(icons / f"{name}.bmp")
    table = tmp_path / "table.txt"
    table.write_bytes(b"12001#r1#\n688#r2#\n11002#r3#\n")
    monkeypatch.setattr(
        gm_state, "load_loot_refs", lambda: {"slot": ("empty", np.full((16, 14), 30.0, np.float32))}
    )
    ms = si.map_set("xmas_dun02")
    out = tmp_path / "out"
    both = {12001: "holy_scroll", 688: "cold_scroll"}
    monkeypatch.setitem(si.MAP_SETS, "xmas_dun02", si.replace(ms, items=both, icon_dir=out))
    got = si.cut_grf("xmas_dun02", table, icons, check=True)
    assert got["other_refusals"] == [] and got["passes_once_screen_cut"] is False
    assert [x.split(":")[0] for x in got["own_set_ambiguous"]] == ["cold_scroll", "holy_scroll"]
    fine = {12001: "holy_scroll", 11002: "orleans_book"}
    monkeypatch.setitem(si.MAP_SETS, "xmas_dun02", si.replace(ms, items=fine, icon_dir=out))
    got = si.cut_grf("xmas_dun02", table, icons, check=True)
    assert got["own_set_ambiguous"] == [] and got["passes_once_screen_cut"] is True
    assert not out.exists()
