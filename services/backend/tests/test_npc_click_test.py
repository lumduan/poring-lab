"""scripts/npc_click_test.py (walk@17 item 5's targeted test; built offline, NOT run): the plan
from L3 (densest NPCs, stands, probe points, clicks), the guard-safe @warp order, Batt's dialog
policy after a click, and the reader's fidelity to Prober9 -- on synthetic data only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "packages/poring_dataset/src"))
nct = _load("npc_click_test", SCRIPTS / "npc_click_test.py")
nc = sys.modules["npc_noclick"]


def camera() -> Any:
    from poring_dataset import camera as cam

    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    return cam.camera_from_json(cj["camera"])


def flat_gat(size: int = 120) -> Any:
    from poring_dataset import gat as gatmod

    return gatmod.Gat(size, size, "1.2", np.zeros((size, size), gatmod.TILE))


def npc(cell: tuple[int, int], sprite: str = "105") -> Any:
    return nc.StaticNpc("town", cell, f"test:{cell[0]},{cell[1]}", sprite, "test")


NPCS = [npc((50, 50)), npc((53, 52), "722"), npc((47, 55)), npc((90, 20))]


def test_the_densest_npcs_come_first_and_near_limits_the_pool() -> None:
    got = [n.cell for n in nct.dense_npcs(NPCS, k=3)]
    assert got == [(47, 55), (50, 50), (53, 52)]  # the cluster (2 neighbours each), ties by cell
    assert [n.cell for n in nct.dense_npcs(NPCS, k=4)][-1] == (90, 20)  # alone: last
    plan = nct.make_plan("town", NPCS, flat_gat().walkable(), camera(), flat_gat(), 7, k=6,
                         near=(90, 20), near_radius=5)  # fmt: skip
    assert [n["cell"] for n in plan["npcs"]] == [[90, 20]]


def test_an_npc_not_drawn_is_never_probed_but_still_keeps_stands_away() -> None:
    hidden = nc.StaticNpc("town", (90, 20), "test:hidden", "705", "test", "conditional")
    plan = nct.make_plan("town", [*NPCS[:3], hidden], flat_gat().walkable(), camera(), flat_gat(),
                         7, k=6, near=(90, 20), near_radius=5)  # fmt: skip
    assert plan["npcs"] == []  # the only NPC near the spot is sent invisible: nothing to probe


@pytest.fixture(scope="module")
def plan() -> dict[str, Any]:
    g = flat_gat()
    return nct.make_plan("town", NPCS, g.walkable(), camera(), g, 20261160, k=3)


def test_stands_are_3_to_5_away_never_beside_another_npc_and_in_view(plan: dict) -> None:
    cells = [n.cell for n in NPCS]
    for n in plan["npcs"]:
        assert len(n["stands"]) == nct.STANDS
        for s in n["stands"]:
            assert 3 <= nct.cheb(s, n["cell"]) <= 5
            assert all(nct.cheb(s, c) >= 2 for c in cells if list(c) != n["cell"])
            assert nct.in_view(camera(), flat_gat(), tuple(s), tuple(n["cell"]))


def test_every_probe_point_is_hovered_reps_times_in_the_work_zone(plan: dict) -> None:
    from collections import Counter

    import work_zone as wz

    seen = Counter((p["npc"], tuple(p["stand"]), p["kind"], tuple(p["offset"]))
                   for p in plan["probes"])  # fmt: skip
    assert set(seen.values()) == {nct.REPS}
    assert all(wz.in_work_zone(*p["at"]) for p in plan["probes"])
    kinds = Counter(p["kind"] for p in plan["probes"])
    assert kinds["sprite"] > 0 and kinds["cell"] > 0
    # the cell probes never sit on the NPC itself, and every one names its cell
    assert all(p["offset"] != [0, 0] and "cell" in p for p in plan["probes"] if p["kind"] == "cell")


def test_clicks_alternate_stands_and_never_hit_an_npc_or_a_stand(plan: dict) -> None:
    cells = [list(n.cell) for n in NPCS]
    clicks = plan["clicks"]
    assert clicks and nct.no_identical_in_a_row(nct.click_warps("town", clicks))
    for c in clicks:
        assert c["cell"] not in cells and 1 <= nct.cheb(c["cell"], c["npc_cell"]) <= 3
        assert c["cell"] not in [n["stands"] for n in plan["npcs"] if n["cell"] == c["npc_cell"]][0]
    first = plan["npcs"][0]
    ring1 = [c for c in clicks if c["npc"] == first["npc"]
             and nct.cheb(c["cell"], first["cell"]) == 1]  # fmt: skip
    # every ring-1 cell is clicked once from EACH stand
    assert {nct.cheb(c["cell"], c["npc_cell"]) for c in clicks} == {1, 2, 3}
    by_cell: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for c in ring1:
        by_cell.setdefault(tuple(c["cell"]), set()).add(tuple(c["stand"]))
    assert by_cell and all(len(v) == 2 for v in by_cell.values())


def test_the_control_spot_is_plain_floor_far_from_every_npc(plan: dict) -> None:
    ctl = plan["control"]
    assert ctl is not None and all(nct.cheb(ctl, n.cell) >= nct.CONTROL_APART for n in NPCS)
    probes = [p for p in plan["probes"] if p["kind"] == "control"]
    assert probes and all(p["stand"] == ctl and p["npc"] == "control" for p in probes)


def test_the_plan_is_seeded() -> None:
    g = flat_gat()
    a = nct.make_plan("town", NPCS, g.walkable(), camera(), g, 5, k=2)
    b = nct.make_plan("town", NPCS, g.walkable(), camera(), g, 5, k=2)
    c = nct.make_plan("town", NPCS, g.walkable(), camera(), g, 6, k=2)
    assert a == b and a != c


def test_a_plan_that_stands_or_walks_in_a_warp_span_is_refused_never_filtered(
    plan: dict, tmp_path: Path
) -> None:
    stand, click, ctl = plan["npcs"][0]["stands"][0], plan["clicks"][0]["cell"], plan["control"]

    def hits(what: str, cell: Any, w: dict) -> bool:
        return any(c.startswith(f"{what} {tuple(cell)} ") for c in nct.warp_conflicts(plan, [w]))

    def portal(x: int, y: int, sx: int = 0, sy: int = 0) -> dict:
        return {"x": x, "y": y, "span_x": sx, "span_y": sy, "name": "p1", "to_map": "elsewhere"}

    # the trigger area is |dx| <= span_x and |dy| <= span_y: its edge counts, one past it does not
    assert hits("stand", stand, portal(stand[0] + 1, stand[1], sx=1))
    assert not hits("stand", stand, portal(stand[0] + 2, stand[1], sx=1))
    assert not hits("stand", stand, portal(stand[0], stand[1] + 2, sy=1))
    assert hits("click", click, portal(*click)) and hits("control", ctl, portal(*ctl))
    assert f"stand {tuple(stand)} in p1 -> elsewhere" in nct.warp_conflicts(plan, [portal(*stand)])
    # the check REFUSES; it never changes the plan
    before = json.dumps(plan, sort_keys=True)
    (tmp_path / "route.json").write_text(json.dumps({"warps": {"town": [portal(*stand)]}}))
    with pytest.raises(SystemExit, match="inside a warp span"):
        nct.check_warps("town", plan, tmp_path)
    assert json.dumps(plan, sort_keys=True) == before
    # clear -> no refusal; a map L3 does not list -> refused (unknown is not clear)
    (tmp_path / "route.json").write_text(json.dumps({"warps": {"town": []}}))
    nct.check_warps("town", plan, tmp_path)
    with pytest.raises(SystemExit, match="lists no warps"):
        nct.check_warps("elsewhere", plan, tmp_path)


def test_warp_lines_type_only_changes_of_stand() -> None:
    assert nct.warp_lines("m", [[1, 2], [1, 2], [3, 4], [1, 2]]) == [
        "@warp m 1 2",
        "@warp m 3 4",
        "@warp m 1 2",
    ]
    assert not nct.no_identical_in_a_row(["@warp m 1 2", "@warp m 1 2"])


# --- the dialog policy (Batt's item 6) ---------------------------------------------------------


def state(ok: bool = True, dialog: str | None = None, menu: bool = False,
          reason: str = "ok") -> Any:  # fmt: skip
    from poring_env import npc_dialog as nd

    d = None if dialog is None else nd.DialogView((201, 101, 278, 178),
                                                  None if dialog == "none" else dialog,
                                                  (233, 155, 42, 20), 0.0, {})  # fmt: skip
    m = None
    if menu:
        m = nd.MenuView((201, 301, 278, 118), ((212, 326, 243, 15),), ("plain",), None, False,
                        False, False, None, (187, 95, 42, 20), (233, 95, 42, 20),
                        (0, 0, 1, 1), (0, 0, 1, 1), 0.0)  # fmt: skip
    return nd.NpcUiState(ok, reason, 1.0, d, m)


def test_dialog_policy_closes_only_a_close_dialog_on_two_frames() -> None:
    assert nct.dialog_action(state(), state()) == "none"
    assert nct.dialog_action(state(dialog="close"), state(dialog="close")) == "close"
    assert nct.dialog_action(state(dialog="next"), state(dialog="next")) == "stop:dialog_next"
    assert nct.dialog_action(state(dialog="none", menu=True),
                             state(dialog="none", menu=True)) == "stop:menu"  # fmt: skip
    assert nct.dialog_action(state(dialog="close"), state()) == "stop:frames_disagree"
    assert nct.dialog_action(state(ok=False, reason="uncertain"),
                             state()).startswith("stop:unread")  # fmt: skip


# --- the reader is Prober9's ---------------------------------------------------------------------


class FakeScreen:
    def __init__(self, img: np.ndarray) -> None:
        self.img = img

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, np.ndarray]:
        pad = np.pad(self.img, ((200, 200), (200, 200), (0, 0)))
        return 0, pad[y + 200 : y + 200 + h, x + 200 : x + 200 + w]


def test_read_series_reads_exactly_what_prober9_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("walk5", "walk6", "reloc2", "where_fix", "walk7", "walk8", "walk9", "walk10"):
        if name not in sys.modules:
            _load(name, SCRIPTS / f"{name}.py")
    w6, w10 = sys.modules["walk6"], sys.modules["walk10"]
    f = _load("fakes_walk6_nct", HERE / "test_walk6.py")
    r = sys.modules["ro_agent"]
    monkeypatch.setattr(r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(nct.time, "sleep", lambda s: None)
    bg = f.background(720, 1280)
    for shape, (u, v) in (("walk", (400, 300)), ("sword", (700, 420))):
        live = bg.copy()
        f.paint(live, u, v, shape)
        refs = f.refs_for(w6, ["walk", "sword"])
        pr = w10.Prober9(None, FakeScreen(live), refs)
        pr.background = bg
        pr.animated = np.zeros(bg.shape[:2], bool)
        want = pr.read(float(u), float(v))
        reads, arrays = nct.read_series(pr, float(u), float(v), n=3)
        assert reads[0]["shape"] == want["shape"] == shape
        assert reads[0]["iou"] == want["iou"] and reads[0]["marker_px"] == want["marker_px"]
        assert len(reads) == 3 and arrays["a_series"].shape == (3, 64, 64, 3)
        assert reads[0]["best"]["cls"] == shape and arrays["mask"].sum() > 0
