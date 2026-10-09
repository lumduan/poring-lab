"""scripts/loot1_score.py (loot@1, offline): the target's server death, P3's distance, a drop
trial's verdict (success, a runtime false positive, a pickup the runtime missed, too slow), the
loot-phase safety window and the bar's first-20 rule, on synthetic events (test_loot_truth's
shapes)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
S = 1_000_000_000
AID = 2_000_002


def load() -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("loot1_score", ROOT / "scripts/loot1_score.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loot1_score"] = mod
    spec.loader.exec_module(mod)
    return mod


ls = load()


def ev(t_s: float, etype: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t_s * S), "type": etype, "server": "map", "dir": "sc", **f}


def kill_and_drop(t: float, gid: int, cell: tuple[int, int], fid: int,
                  picked: float | None) -> list[dict[str, Any]]:  # fmt: skip
    x, y = cell
    out = [
        ev(t - 5, "entity_appear", kind="stand", gid=gid, char_id=0, objtype=5, job=1002,
           speed=400, name="", x=x, y=y, heading=0),
        ev(t, "entity_vanish", gid=gid, reason=1),
        ev(t, "floor_item_appear", kind="fall", floor_id=fid, item_id=909, item_type=3,
           identified=True, x=x, y=y, sub_x=6, sub_y=6, amount=1, drop_effect=False),
    ]  # fmt: skip
    if picked is not None:
        out += [
            ev(picked, "act", src_gid=AID, target_gid=fid, server_tick=0, src_speed=0, dmotion=0,
               damage=0, damage2=0, div=0, action=1, kind="pickup", sp_damage=False),
            ev(picked, "pickup_result", index=5, amount=1, item_id=909, identified=True,
               item_type=3, result=0, reason="ok", ok=True, refine=0),
            ev(picked, "floor_item_vanish", floor_id=fid),
        ]  # fmt: skip
    return out


def trial(k: int, t: float, px_cell: tuple[int, int], click: float | None,
          obtained: bool) -> dict[str, Any]:  # fmt: skip
    return {
        "k": k, "spot": [100, 100], "kill": "vanished", "found": True, "here": [100, 101],
        "attacks": [int((t - 4) * S)], "t_end": int((t + 15) * S),
        "death": {"cell": list(px_cell), "reason": "ok"},
        "pickup_click": None if click is None else {"t": int(click * S)},
        "runtime": {"obtained": obtained, "weight_rose": obtained, "cue": False},
    }  # fmt: skip


def base() -> list[dict[str, Any]]:
    return [ev(0.0, "login_accepted", aid=AID, sex=1),
            ev(0.1, "map_change", map="prt_fild08", x=100, y=100)]  # fmt: skip


def test_verdicts_per_drop_trial() -> None:
    events = base()
    trials = []
    cases = [  # (server death cell, pixel cell, click, server pickup, runtime obtained)
        ((101, 102), (101, 102), 14.0, 14.5, True),  # success, P3 exact
        ((102, 102), (101, 102), 44.0, 44.5, False),  # a pickup the runtime check missed
        ((99, 100), (99, 101), 74.0, None, True),  # runtime false positive; P3 within 1
        ((100, 98), (100, 98), 160.0, 160.5, True),  # too slow (> 45 s after the death)
    ]
    for k, (cell, px, click, picked, obtained) in enumerate(cases):
        t = 10.0 + 30 * k
        events += kill_and_drop(t, 110_000_000 + k, cell, 500 + k, picked)
        trials.append(trial(k, t, px, click, obtained))
        if k == 3:
            trials[-1]["t_end"] = int(170 * S)
    out = ls.judge(trials, events, None, first=4)
    res = [r["result"] for r in out["rows"]]
    assert res == ["success", "fail: server pickup the runtime check missed",
                   "fail: runtime obtained, no server pickup (false positive)",
                   "fail: too slow"]  # fmt: skip
    assert [r["p3"] for r in out["rows"]] == [0, 1, 1, 0]
    assert out["verdict"] == "FAIL" and out["success"] == 1


def test_fewer_drop_trials_than_the_bar_is_inconclusive_and_safety_counts() -> None:
    events = base() + kill_and_drop(10.0, 110_000_001, (101, 101), 501, 12.0)
    events.append(ev(11.0, "attack_request", dir="cs"))  # inside the loot phase
    events.append(ev(5.0, "attack_request", dir="cs"))  # the kill phase: excluded
    out = ls.judge([trial(0, 10.0, (101, 101), 11.5, True)], events, None, first=20)
    assert out["verdict"].startswith("INCONCLUSIVE") and out["unsafe"] == 1
    assert out["rows"][0]["safety"] == {"attack_request": 1}


def test_no_drop_is_not_a_drop_trial_and_two_deaths_are_never_guessed() -> None:
    events = base()
    events += kill_and_drop(10.0, 110_000_001, (101, 101), 501, None)
    events = [e for e in events if e["type"] != "floor_item_appear"]  # it dropped nothing
    out = ls.judge([trial(0, 10.0, (101, 101), None, False)], events, None, first=1)
    assert out["drop_trials"] == 0
    two = base() + kill_and_drop(10.0, 1, (101, 101), 501, None)
    two += kill_and_drop(10.5, 2, (102, 101), 502, None)
    out = ls.judge([trial(0, 10.0, (101, 101), None, False)], two, None, first=1)
    assert out["rows"][0]["server"] == "ambiguous"
