"""scripts/run_row.py (Batt 2026-10-18 night): the standard run row -- one column per run, the
night's rulers, beside Batt's demo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import run_row as rr  # noqa: E402

S = 10**9


def ev(t: float, typ: str, **kw: object) -> dict:
    return {"type": typ, "t_mono_ns": int(t * S), **kw}


def test_creamy_counts_by_the_job_at_that_moment() -> None:
    """rAthena reuses a dead mob's id: a Poring on a Creamy's old id is not a Creamy hit."""
    g = 110000001
    evs = [ev(0, "entity_appear", gid=g, objtype=5, job=1018),
           ev(1, "attack_request", target_gid=g),
           ev(1.2, "act", src_gid=rr.GM, target_gid=g, damage=40),
           ev(1.3, "act", src_gid=rr.GM, target_gid=g, damage=0),  # a miss: no hit
           ev(2, "entity_vanish", gid=g, reason=1),
           ev(5, "entity_appear", gid=g, objtype=5, job=1002),  # the id reused by a Poring
           ev(6, "attack_request", target_gid=g),
           ev(6.2, "act", src_gid=rr.GM, target_gid=g, damage=40)]  # fmt: skip
    assert rr.creamy(evs, 0, 10 * S) == (1, 1)
    assert rr.creamy(evs, int(1.1 * S), 10 * S) == (1, 0)  # the window


def test_box_table_has_every_standard_column() -> None:
    out = rr.box_table([("BATT demo", rr.BATT), ("run", {"kills / h": 1.0})])
    lines = out.splitlines()
    assert lines[0].startswith("┌") and lines[-1].startswith("└")
    assert len(lines) == len(rr.BATT) + 4
    for name in ("free targets attacked <= 10 s", "steer moving share",
                 "dead calls without a real death", "Creamy hits (requests)",
                 "Creamy hits / h"):  # fmt: skip
        assert any(name in x for x in lines)
    assert len({len(x) for x in lines}) == 1  # every line the same width


def test_a_real_run_row() -> None:
    """v38 run 4 (a REAL session): the row agrees with flow_judge and the packets."""
    sid = "20261018T172605-demo-hunt-flow38"
    if not (rr.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v38 session is not banked on this host")
    r = rr.row(sid)
    assert r["engagements"] == 142 and r["kills / h"] == 133.8
    assert r["landing within 5 s"].startswith("117/142 = 82.4 %")
    assert r["dead calls without a real death"] == "23/138 = 16.7 %"
    assert r["Creamy hits (requests)"] == "0 (0)" and r["Creamy hits / h"] == 0.0
    assert r["hard bars NPC / map / other"] == "0 / 0 / 0"
    assert r["steer moving share"] == "40 %" and r["s per kill"] == 26.9


def test_creamy_hits_per_hour_positive_case() -> None:
    """Batt 2026-10-19 (the steer walk-guard change's cost): Creamy hits per hour of the judged
    window. POSITIVE case: v39 run 3 (a REAL session) had 8 Creamy hits from 7 requests."""
    import json

    sid = "20261019T000720-demo-hunt-flow39"
    if not (rr.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v39 session is not banked on this host")
    r = rr.row(sid)
    w = float(json.loads((rr.DEMO / sid / "flow_judge.json").read_text())["window_s"])
    assert r["Creamy hits (requests)"] == "8 (7)"
    assert r["Creamy hits / h"] == round(8 / (w / 3600), 2) and 7.5 < r["Creamy hits / h"] < 8.5
