"""scripts/weapon_swap_study.py: a weapon-swap hunt's swaps against its steals and kills."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import weapon_swap_study as ws  # noqa: E402

S = ws.NS
AID, MOB = 7, 101  # made-up ids


def test_a_knife_opener_kill_with_its_steal_and_the_swap_back() -> None:
    names = {10: "weak", 2: "main", -1: "main"}
    pk = [
        {"t_mono_ns": 1 * S, "type": "equip_result", "index": 10, "location": 2},  # the Knife on
        *({"t_mono_ns": (2 + i) * S // 2 * 2, "type": "act", "src_gid": AID, "target_gid": MOB,
           "damage": 68} for i in range(3)),  # three knife hits at 2, 4, 6 s
        {"t_mono_ns": int(6.5 * S), "type": "pickup_result"},  # the steal (no pickup request)
        {"t_mono_ns": int(7.9 * S), "type": "equip_result", "index": 2, "location": 2},  # back
        {"t_mono_ns": 9 * S, "type": "act", "src_gid": AID, "target_gid": MOB, "damage": 184},
    ]  # fmt: skip
    rows = ws.kill_rows(pk, [(int(9.5 * S), MOB)], AID, names, "main")
    assert len(rows) == 1
    r = rows[0]
    assert (r["first"], r["last"], r["hits"], r["weak_hits"]) == ("weak", "main", 4, 3)
    assert r["steal"] and r["weak_hits_before_steal"] == 3 and r["steal_to_main_s"] == 1.4
    # a gain right after OUR pickup request is a pickup, not a steal
    pk2 = [*pk, {"t_mono_ns": int(6.0 * S), "type": "pickup_request"}]
    r2 = ws.kill_rows(pk2, [(int(9.5 * S), MOB)], AID, names, "main")[0]
    assert not r2["steal"] and r2["steal_to_main_s"] is None
    s = ws.summary(rows, "main")
    assert s["with_steal"] == 1 and s["first_last"] == {"weak->main": 1}
