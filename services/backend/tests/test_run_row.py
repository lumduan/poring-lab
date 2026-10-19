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


def test_kill_to_loot_start_and_the_end_reason() -> None:
    """Batt 2026-10-19 overnight's standard columns: kill -> loot start (3.87's ruler: the kill's
    vanish packet -> the loot step's start) and the run's end reason. Synthetic, then a REAL
    positive case: v43 run 4 (stopped on a lost input ack; 98 dead calls with a loot step)."""
    S = rr.NS
    ev = [{"type": "entity_vanish", "reason": 1, "gid": 7, "t_mono_ns": 10 * S},
          {"type": "entity_vanish", "reason": 0, "gid": 8, "t_mono_ns": 10 * S}]  # fmt: skip
    e1 = {"k": 1, "result": "dead", "t_first_click": 9 * S, "t_last_click": 9 * S,
          "t_end": 13 * S, "loot": {"s": 2.0}}  # fmt: skip
    e2 = {"k": 2, "result": "dead", "t_first_click": 9 * S, "t_end": 13 * S,
          "loot": {"s": 1.0}}  # gid 8 did not die (reason 0)  # fmt: skip
    e3 = {"k": 3, "result": "skipped_risky", "t_first_click": 9 * S, "t_end": 13 * S}
    engs = [e1, e2, e3]
    assert rr.kill_to_loot_start(ev, engs, {1: 7, 2: 8, 3: 7}) == [1.0]
    sid = "20261019T184304-demo-hunt-flow43"
    if not (rr.DEMO / sid / "flow_judge.json").exists():
        pytest.skip("the v43 session is not banked on this host")
    r = rr.row(sid)
    assert r["kill -> loot start mean / p50 s"] == "0.91 / 0.46 (n 98)"
    assert r["end reason"] == "stopped:Stop: no input_ack within 3 s"


def test_pool_sums_counts_and_averages_rates() -> None:
    """The pooled column (the night report's bot-vs-Batt table): counts summed and fractions
    re-taken from the sums, rates the mean of the runs, n-weighted kill -> loot start."""
    a = {
        "session": "A",
        "engagements": 10,
        "landing within 5 s": "8/10 = 80.0 % (49.0-94.3)",
        "kills / h": 100.0,
        "kills per sighting": 4.0,
        "seen / 10 min": 25.0,
        "free targets attacked <= 10 s": "30 % (n 10)",
        "steer moving share": "40 %",
        "seen -> click p50 s": 3.0,
        "death -> next p50 s": 1.0,
        "dead calls without a real death": "2/8 = 25.0 %",
        "loot picked / dropped (looters)": "6/10 = 60 % (1)",
        "reversals / min": 8.0,
        "reversals outside loot / min": 7.0,
        "Creamy hits (requests)": "1 (2)",
        "Creamy hits / h": 1.0,
        "hard bars NPC / map / other": "0 / 0 / 0",
        "kill -> loot start mean / p50 s": "1.00 / 0.50 (n 10)",
        "end reason": "time_box",
    }
    b = {
        **a,
        "session": "B",
        "engagements": 30,
        "landing within 5 s": "27/30 = 90.0 % (x)",
        "kills / h": 200.0,
        "free targets attacked <= 10 s": "50 % (n 30)",
        "steer moving share": "60 %",
        "seen -> click p50 s": 2.0,
        "dead calls without a real death": "3/22 = 13.6 %",
        "loot picked / dropped (looters)": "14/20 = 70 % (3)",
        "Creamy hits (requests)": "0 (0)",
        "Creamy hits / h": 0.0,
        "kill -> loot start mean / p50 s": "2.00 / 1.50 (n 30)",
        "end reason": "stopped:farmstop:x",
    }
    p = rr.pool([a, b])
    assert p["session"] == "pooled (2 runs)" and p["engagements"] == 40
    assert p["landing within 5 s"].startswith("35/40 = 87.5 % (")
    assert p["kills / h"] == 150.0 and p["s per kill"] == 24.0
    assert p["free targets attacked <= 10 s"] == "45 % (n 40)"
    assert p["steer moving share"] == "50 %" and p["seen -> click p50 s"] == 2.5
    assert p["dead calls without a real death"] == "5/30 = 16.7 %"
    assert p["loot picked / dropped (looters)"] == "20/30 = 67 % (4)"
    assert p["Creamy hits (requests)"] == "1 (2)" and p["Creamy hits / h"] == 0.5
    assert p["hard bars NPC / map / other"] == "0 / 0 / 0"
    assert p["kill -> loot start mean / p50 s"] == "1.75 / 1.00 (n 40)"
    assert p["end reason"] == "time_box x1, stopped:farmstop:x x1"
    assert "pooled (2 runs)" in rr.box_table([("BATT demo", rr.BATT), (p["session"], p)])
