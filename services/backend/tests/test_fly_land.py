"""dungeon@9.60 --fly-first-land (docs/planning/live-blocks.md 18.16 / 18.17): the stale re-fire.

After a Fly Wing the frames still show the old place for a while; s9ab flew again on an alarm
sighting grabbed 0.29-0.45 s after the previous key (9 of 31 boss Fly Wings, 0 alarm units on
screen at each). With the setting, every Fly Wing's key moves a land floor to key + FF_LAND_S and a
latched sighting counts only when grabbed after it. Offline, no game: run()'s own closures BY
EXECUTION (press, ff_inside, step_survive's head; test_fly_first's harnesses), the record, the flag,
the setting, and the proof that the flag off is c694f0f4's runner."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import huntstate_check as hc  # noqa: E402


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name[:-3], Path(__file__).with_name(name))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TFF = _load("test_fly_first.py")  # run()'s closures by execution: press, ff_inside, the tick head
SRC = hc.TARGET.read_text()


def _quiet(f: Any, *a: Any, **k: Any) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = f(*a, **k)
    return int(rc), out.getvalue()


# --- the pure parts -------------------------------------------------------------------------------
def test_the_floor_is_the_later_of_the_last_fly_wing_and_its_landing() -> None:
    assert dh.FLY_LAND is True and dh.FLY_LAND_VERSION == "9.60" and dh.FF_LAND_S == 0.75
    assert dh.ff_floor(10.0, None) == 10.0  # the switch off: 9.59's rule exactly
    assert dh.ff_floor(10.0, 10.6) == 10.6 and dh.ff_floor(11.0, 10.6) == 11.0
    seen = (10.4, TFF.dog(0.9), 3, True)  # grabbed 0.4 s after a key at 10.0 (the old place)
    assert dh.ff_sighting(seen, 12.3, dh.ff_floor(10.2, None)) is seen  # 9.59: it re-fires
    assert dh.ff_sighting(seen, 12.3, dh.ff_floor(10.2, 10.0 + dh.FF_LAND_S)) is None
    fresh = (12.2, TFF.dog(0.9), 1, True)  # r07B's: grabbed 2.22 s after the key
    assert dh.ff_sighting(fresh, 12.3, dh.ff_floor(10.2, 10.0 + dh.FF_LAND_S)) is fresh


def test_the_record_and_the_flag() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": False}  # fmt: skip
    on = dh.fixes_of(dh.argparse.Namespace(**base, fly_first=True, fly_first_land=True))
    assert on["fly_first_land"] == [dh.FF_LAND_S, "9.60"]
    for kw in ({"fly_first": True, "fly_first_land": False}, {"fly_first": False,
                                                              "fly_first_land": True}):  # fmt: skip
        assert "fly_first_land" not in dh.fixes_of(dh.argparse.Namespace(**base, **kw))
    assert "--fly-first-land" in SRC and dh.tune_values(["FF_LAND_S=1.0"]) == (
        {"FF_LAND_S": 1.0}, None)  # fmt: skip
    assert dh.tune_values(["FF_LAND_S=5"])[1] is not None  # outside its range (0.2 .. 2.0)


# --- press(): every Fly Wing moves the floor, by execution --------------------------------------
def test_every_fly_wing_moves_the_floor_and_records_it_only_with_the_switch() -> None:
    keys: list[str] = []
    evs: list[dict[str, Any]] = []
    ns = TFF._press_ns(True, keys, evs, fly_first_hp=True)
    ns["fly_first_land"] = True
    press = TFF.closure("press", ns)
    for why in ("garm", "rate 1200 at hp 0.40", "end"):  # boss, HP (fly_first_hp), the end's
        t0 = time.monotonic_ns()
        press("fly", why)
        rec = [e for e in evs if e["kind"] == "fly_first" and e["what"] == "land"][-1]
        assert t0 <= rec["t_key_ns"] <= time.monotonic_ns()
        assert ns["ff"]["land"] == pytest.approx(rec["t_key_ns"] / 1e9 + dh.FF_LAND_S)
        assert rec["floor_ns"] == pytest.approx(rec["t_key_ns"] + dh.FF_LAND_S * 1e9, abs=2)
    land = ns["ff"]["land"]
    press("potion", "hp 40")  # another key: the floor stays
    assert ns["ff"]["land"] == land
    assert sum(1 for e in evs if e.get("what") == "land") == 3
    # the switch off: no floor, no record -- 9.59's press exactly (test_fly_first's cases)
    evs_off: list[dict[str, Any]] = []
    ns_off = TFF._press_ns(True, [], evs_off, fly_first_hp=True)
    TFF.closure("press", ns_off)("fly", "garm")
    assert ns_off["ff"]["land"] is None and not [e for e in evs_off if e.get("what") == "land"]


# --- the reads gated by the floor, by execution ------------------------------------------------
def test_the_read_inside_refuses_a_sighting_from_before_the_landing() -> None:
    now = time.monotonic()
    key = now - 2.3  # the last Fly Wing's key; hs.fly_at is set ~0.2 s after it
    stale = (key + 0.4, TFF.dog(0.9), 3, True)  # grabbed on the old place's last frames
    p: list[tuple[str, str]] = []
    ns = TFF._read_ns(stale, key + 0.2, p, [])
    assert ns["ff_inside"](now) is True and p == [("fly", "garm")]  # 9.59: the stale re-fire
    p2: list[tuple[str, str]] = []
    ns2 = TFF._read_ns(stale, key + 0.2, p2, [])
    ns2["ff"]["land"] = key + dh.FF_LAND_S
    assert ns2["ff_inside"](now) is False and p2 == []  # 9.60: refused
    fresh = (key + 2.22, TFF.dog(0.9), 1, True)
    p3: list[tuple[str, str]] = []
    ns3 = TFF._read_ns(fresh, key + 0.2, p3, [])
    ns3["ff"]["land"] = key + dh.FF_LAND_S
    assert ns3["ff_inside"](now) is True and p3 == [("fly", "garm")]  # a fresh one still flies


def test_the_tick_head_refuses_a_sighting_from_before_the_landing() -> None:
    now = time.monotonic()
    key = now - 2.3
    for seen, land, want in (((key + 0.4, TFF.dog(0.9), 3, True), None, ["alarm"]),  # 9.59
                             ((key + 0.4, TFF.dog(0.9), 3, True), key + dh.FF_LAND_S, []),
                             ((key + 2.22, TFF.dog(0.9), 1, True), key + dh.FF_LAND_S,
                              ["alarm"])):  # fmt: skip
        flies: list[tuple[Any, str]] = []
        ns = TFF._tick_ns(seen=seen, line=None, box_boss=True, fly_at=key + 0.2, flies=flies)
        ns["ff"]["land"] = land
        TFF._head_fn(ns)()
        assert [src for _s, src in flies] == want, (seen[0] - key, land)


# --- the proofs -----------------------------------------------------------------------------------
def _base(rev: str) -> str:
    try:
        return hc.git_show(rev, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {rev} here (a shallow checkout)")


def test_every_fly_land_change_is_a_branch_whose_else_is_959s_code() -> None:
    text, n = hc.unland(SRC)
    assert n == 7 and "FLY_LAND" not in text and "fly_first_land" not in text
    rc, out = _quiet(hc.land_check, _base(hc.LAND_BASE), SRC)
    assert rc == 0 and "the module == the base's (as ASTs): YES" in out, out
    for check, base in ((hc.pick_check, hc.PICK_BASE), (hc.flag_check, hc.FLAG_BASE)):
        rc_x, out_x = _quiet(check, _base(base), SRC)
        assert rc_x == 0 and "fly-land branches read as their else (live-blocks 18.17): 7" in out_x
    rc_d, out_d = _quiet(hc.drive_check, _base(hc.DRIVE_BASE), SRC)
    rc_c, out_c = _quiet(hc.check, _base(hc.BASE_REV), SRC, drive_ok=True)
    assert rc_d == 0 and rc_c == 0, out_d + out_c
    bent = SRC.replace("FF_REARM_S = 1.0", "FF_REARM_S = 1.5", 1)  # a 9.57 line, no branch
    assert _quiet(hc.land_check, _base(hc.LAND_BASE), bent)[0] == 1
