"""hit_rate.py (Batt 2026-10-21, the Crusader re-spec loop: the hit rate per species is the
primary): the pure parts, and the positive case from REAL sessions (the Lv 1 Novice's misses in
farm@0 / farm@1, 2026-10-15)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import hit_rate as hr  # noqa: E402

S = 10**9
GM = hr.GM
ORC = 110000001


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def test_both_directions_are_counted_by_the_species_at_the_act() -> None:
    packets = [
        ev(1, "entity_appear", objtype=5, gid=ORC, job=1152),
        ev(2, "act", src_gid=GM, target_gid=ORC, kind="normal", damage=120, damage2=0),
        ev(3, "act", src_gid=GM, target_gid=ORC, kind="normal", damage=0, damage2=0),
        ev(4, "act", src_gid=GM, target_gid=ORC, kind="lucky_dodge", damage=0, damage2=0),
        ev(5, "act", src_gid=ORC, target_gid=GM, kind="normal", damage=-1, damage2=0),
        ev(6, "act", src_gid=ORC, target_gid=GM, kind="normal", damage=0, damage2=0),
        ev(7, "act", src_gid=GM, target_gid=900, kind="pickup", damage=0, damage2=0),
        ev(8, "act", src_gid=GM, target_gid=777, kind="normal", damage=5, damage2=0),
    ]
    r = hr.results(packets)
    assert [x["hit"] for x in r["ours"]] == [True, False, False]  # a perfect dodge is a miss
    assert [x["hit"] for x in r["theirs"]] == [True, False]  # -1: an amount hidden from us
    ours = hr.rates(r["ours"])
    assert ours["Orc Skeleton"] == {"n": 3, "hits": 1, "misses": 2, "rate": 0.3333,
                                    "wilson95": ours["Orc Skeleton"]["wilson95"]}  # fmt: skip
    assert list(ours) == ["Orc Skeleton", "all"]  # the pickup and the never-seen gid are not rows


@pytest.mark.skipif(not (hr.DEMO / "20261015T203231-demo-farm1" / "packets.jsonl.gz").exists(),
                    reason="the farm@1 session is not in /dev/shm")  # fmt: skip
def test_the_real_novices_misses() -> None:
    rows = hr.results(hr.load("20261015T201035-demo-farm0"))["ours"]
    rows += hr.results(hr.load("20261015T203231-demo-farm1"))["ours"]
    pooled = hr.rates(rows)["all"]
    assert (pooled["n"], pooled["misses"]) == (78, 12)  # 3 / 23 + 9 / 55, counted raw
