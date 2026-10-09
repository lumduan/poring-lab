"""scripts/talk1_score.py (talk@1, offline): the target found by position, the menu cross-check
with L3, the choices by position, the clean close, the safety window and the per-scene bar, on
synthetic dialog events (the 2026-10-08 decoders' shapes; ids synthetic, menu strings invented)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
S = 1_000_000_000
AID, NPC, OTHER = 2_000_002, 110_000_123, 110_000_456
OPTS = ["About A", "About B ", "Goodbye"]  # a trailing space, as real menus have


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("talk1_score", ROOT / "scripts/talk1_score.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talk1_score"] = mod
    spec.loader.exec_module(mod)
    return mod


ts = load()


def ev(t_s: float, etype: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t_s * S), "type": etype, "server": "map", "dir": "sc", **f}


def base() -> list[dict[str, Any]]:
    return [
        ev(0.0, "login_accepted", aid=AID, sex=1),
        ev(0.1, "map_change", map="prt_church", x=100, y=70),
        ev(0.5, "entity_appear", kind="stand", gid=NPC, char_id=0, objtype=6, job=67, speed=200,
           name="", x=103, y=76, heading=0),
        ev(0.5, "entity_appear", kind="stand", gid=OTHER, char_id=0, objtype=6, job=67, speed=200,
           name="", x=103, y=71, heading=0),
    ]  # fmt: skip


def dialog(t: float, first: int = 2, end: int = 3, close: bool = True) -> list[dict[str, Any]]:
    out = [
        ev(t, "npc_contact", npc_gid=NPC, contact_type=1, dir="cs"),
        ev(t + 0.2, "npc_say", npc_gid=NPC, text="hello", raw_hex=""),
        ev(t + 0.2, "npc_wait", npc_gid=NPC),
        ev(t + 1.0, "npc_next_click", npc_gid=NPC, dir="cs"),
        ev(t + 1.2, "npc_menu", npc_gid=NPC, options=OPTS, raw_hex=""),
        ev(t + 2.0, "npc_choose", npc_gid=NPC, choice=first, cancelled=False, dir="cs"),
        ev(t + 2.2, "npc_say", npc_gid=NPC, text="about b", raw_hex=""),
        ev(t + 3.0, "npc_menu", npc_gid=NPC, options=OPTS, raw_hex=""),
        ev(t + 4.0, "npc_choose", npc_gid=NPC, choice=end, cancelled=False, dir="cs"),
        ev(t + 4.2, "npc_close", npc_gid=NPC),
    ]  # fmt: skip
    if close:
        out.append(ev(t + 5.0, "npc_close_click", npc_gid=NPC, dir="cs"))
    return out


def trial(k: int, t: float, **over: Any) -> dict[str, Any]:
    return {"k": k, "scene": "prt_church", "npc": "N#1", "npc_cell": [103, 76],
            "l3_options": OPTS, "intended": ["About B ", "Goodbye"], "t_start": int((t - 10) * S),
            "t_contact_click": int((t - 0.3) * S), "t_end": int((t + 20) * S),
            "runtime": {"closed": True}, **over}  # fmt: skip


def test_a_clean_dialog_succeeds() -> None:
    out = ts.judge([trial(0, 10.0)], base() + dialog(10.0))
    row = out["rows"][0]
    assert row["result"] == "success" and row["safety"] == {} and row["contact_to_close_s"] == 5.3


def test_each_failure_is_named() -> None:
    cases = [
        (dialog(10.0, first=1), trial(0, 10.0), "fail: wrong first choice (wanted 2)"),
        (dialog(10.0, end=1), trial(0, 10.0), "fail: the end option was not chosen"),
        (dialog(10.0, close=False), trial(0, 10.0), "fail: no clean close"),
        (dialog(10.0), trial(0, 10.0, l3_options=["X"]), "fail: menu differs from L3"),
        (dialog(10.0), trial(0, 10.0, t_contact_click=None), "fail: no contact click"),
        (dialog(10.0), trial(0, 10.0, npc_cell=[1, 1]), "fail: no single NPC on the L3 cell"),
        (dialog(10.0), trial(0, 10.0, runtime={"closed": False}), "fail: the runtime check"),
    ]
    for events, tr, want in cases:
        got = ts.judge([tr], base() + events)["rows"][0]["result"]
        assert got.startswith(want), (want, got)


def test_safety_counts_other_contacts_and_a_second_contact() -> None:
    events = base() + dialog(10.0)
    events.append(ev(12.5, "npc_contact", npc_gid=OTHER, contact_type=1, dir="cs"))
    events.append(ev(17.0, "npc_contact", npc_gid=NPC, contact_type=1, dir="cs"))
    events.append(ev(18.0, "attack_request", dir="cs"))
    events.sort(key=lambda e: e["t_mono_ns"])
    row = ts.judge([trial(0, 10.0)], events)["rows"][0]
    assert row["safety"] == {"npc_contact_other": 1, "npc_contact_again": 1, "attack_request": 1}


def test_the_bar_is_per_scene() -> None:
    events = base()
    trials = []
    for k in range(50):
        t = 100.0 + 60 * k
        events += dialog(t, first=1 if k < 2 else 2)  # two wrong choices
        trials.append(trial(k, t))
    out = ts.judge(trials, events)
    sc = out["scenes"]["prt_church"]
    assert sc["success"] == 48 and sc["verdict"] == "PASS" and sc["unsafe"] == 0
    assert ts.judge(trials[:10], events)["scenes"]["prt_church"]["verdict"].startswith("INCOMPLETE")
