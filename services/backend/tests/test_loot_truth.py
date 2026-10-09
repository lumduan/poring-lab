"""scripts/loot_truth.py (loot@1, offline truth): deaths, drops and OUR confirmed pickups from
synthetic packet events (the 2026-10-08 floor-item decoders' event shapes; ids synthetic)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("loot_truth", ROOT / "scripts" / "loot_truth.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loot_truth"] = mod
    spec.loader.exec_module(mod)
    return mod


lt = load()
S = 1_000_000_000
AID, MOB, OTHER = 2_000_002, 110_000_777, 2_000_001


def ev(t_s: float, etype: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t_s * S), "type": etype, "server": "map", "dir": "sc", **f}


def appear(t: float, gid: int, x: int, y: int) -> dict[str, Any]:
    return ev(t, "entity_appear", kind="stand", gid=gid, char_id=0, objtype=5, job=1002,
              speed=400, name="", x=x, y=y, heading=0)  # fmt: skip


def fall(t: float, fid: int, item: int, x: int, y: int) -> dict[str, Any]:
    return ev(t, "floor_item_appear", kind="fall", floor_id=fid, item_id=item, item_type=3,
              identified=True, x=x, y=y, sub_x=6, sub_y=6, amount=1, drop_effect=False)  # fmt: skip


def scene() -> list[dict[str, Any]]:
    return [
        ev(0.0, "login_accepted", aid=AID, sex=1),
        ev(0.1, "map_change", map="prt_fild08", x=150, y=199),
        appear(1.0, MOB, 150, 200),
        ev(5.0, "entity_vanish", gid=MOB, reason=1),
        fall(5.0, 501, 9101, 150, 200),  # first drop: ON the death cell
        fall(5.0, 502, 9102, 151, 199),  # second: SE
        fall(9.0, 503, 9103, 40, 40),  # unrelated: far away
        ev(7.0, "pickup_request", floor_id=501, dir="cs"),
        ev(7.3, "act", src_gid=AID, target_gid=501, server_tick=0, src_speed=0, dmotion=0,
           damage=0, damage2=0, div=0, action=1, kind="pickup", sp_damage=False),
        ev(7.3, "pickup_result", index=5, amount=1, item_id=9101, identified=True, item_type=3,
           result=0, reason="ok", ok=True, refine=0),
        ev(7.3, "floor_item_vanish", floor_id=501),
        ev(8.0, "act", src_gid=OTHER, target_gid=502, server_tick=0, src_speed=0, dmotion=0,
           damage=0, damage2=0, div=0, action=1, kind="pickup", sp_damage=False),
        ev(8.0, "floor_item_vanish", floor_id=502),
    ]  # fmt: skip


def test_deaths_drops_and_a_confirmed_pickup() -> None:
    out = lt.ledger(scene(), lt.self_aid(scene()))
    assert out["aid"] == AID
    assert out["deaths"] == [{"gid": MOB, "t_ns": 5 * S, "cell": (150, 200), "job": 1002}]
    rows = {r["floor_id"]: r for r in out["floor_items"]}
    assert rows[501]["death"] == MOB and rows[501]["offset"] == (0, 0)
    assert rows[502]["offset"] == (1, -1)  # the server's SE
    assert rows[503]["death"] is None
    assert rows[501]["confirmed"] is True and rows[501]["our_request_ns"] == 7 * S
    assert rows[502]["picked_by"] == OTHER and rows[502]["confirmed"] is False
    s = out["summary"]
    assert (s["deaths"], s["falls"], s["falls_from_a_death"]) == (1, 3, 2)
    assert (s["our_pickups_confirmed"], s["our_pickup_acts"], s["pickup_results_ok"]) == (1, 1, 1)


def test_a_pickup_without_the_inventory_result_is_not_confirmed() -> None:
    events = [e for e in scene() if e["type"] != "pickup_result"]
    rows = {r["floor_id"]: r for r in lt.ledger(events, AID)["floor_items"]}
    assert rows[501]["picked_by"] == AID and rows[501]["confirmed"] is False


def test_an_item_result_for_another_item_does_not_confirm() -> None:
    events = [dict(e, item_id=9999) if e["type"] == "pickup_result" else e for e in scene()]
    rows = {r["floor_id"]: r for r in lt.ledger(events, AID)["floor_items"]}
    assert rows[501]["our_result"] is None and rows[501]["confirmed"] is False


def test_a_late_drop_is_not_attributed_to_the_death() -> None:
    events = [*scene(), fall(5.0 + lt.DROP_WINDOW_S + 0.1, 504, 9104, 150, 200)]
    rows = {r["floor_id"]: r for r in lt.ledger(events, AID)["floor_items"]}
    assert rows[504]["death"] is None


def test_a_drop_sent_just_before_the_died_vanish_is_attributed() -> None:
    """loot@1 pilot 2 (2026-10-09 15:06): the server sent the Poring's drop 0.24 s BEFORE its
    "died" vanish; the ledger linked it to no death. Up to DROP_BEFORE_S before counts."""
    early = fall(5.0 - 0.24, 505, 9105, 150, 200)
    too_early = fall(5.0 - lt.DROP_BEFORE_S - 0.1, 506, 9106, 150, 200)
    rows = {r["floor_id"]: r for r in lt.ledger([*scene(), early, too_early], AID)["floor_items"]}
    assert rows[505]["death"] == MOB and rows[505]["offset"] == (0, 0)
    assert rows[506]["death"] is None
