"""scripts/slf_score.py (rogue-xmas02.md Study S-LF, Amendment R): the light-floor reader's measures
on a SYNTHETIC run in the sessions' own schema (events.jsonl + packets), one case per definition.
The real-session positive case (p40-p47 pooled, p47's spans and wing) is in the report of the
commit that added it: it needs the banked sessions on the NAS."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import slf_score as sl  # noqa: E402

S = 1_000_000_000
US = 2000002


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def rd(t: float, how: str, pos: tuple[int, int] | None, **kw: Any) -> dict[str, Any]:
    return ev(t, "hp_read", pct=100, rd=how, pos=None if pos is None else list(pos), **kw)


def pk(t: float, typ: str, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), "type": typ, **kw}


def move(t: float, a: tuple[int, int], b: tuple[int, int]) -> dict[str, Any]:
    return pk(t, "self_move", x0=a[0], y0=a[1], x1=b[0], y1=b[1])


def run() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """0.5 s: we walk (10,10) -> (12,10). 3.0 s: the first read after a 1.8-s block is held back
    (LF-1 logs it); 3.4-4.4 s: six failed reads (a persistent span) with a stale walk click at
    3.9 s that walks us 4 cells; 6.0 s: a fresh read 4 cells off while standing (WRONG); 7.0 s: a
    server pin moves us 4 cells and the read 0.02 s later still shows the old cell (NOT wrong);
    8.0 s: the pos_unread escape, 0.5 s after a sent walk click."""
    a, b = (12, 10), (16, 10)
    events = [ev(0.0, "run_start"), rd(1.0, "base", a), rd(1.2, "base", a),
              ev(1.3, "walk", clicked=True, **{"from": list(a), "to": [14, 10]}),  # fresh, unsent
              rd(3.0, "unconfirmed", a, held=[12, 10], held_dt=1.8),
              rd(3.2, "light", a, lf2="ok"),
              *[rd(3.4 + 0.2 * i, "light_failed:uncovered_ink", a) for i in range(6)],
              ev(3.5, "reach_skip", here=list(a)),
              ev(3.9, "walk", clicked=True, **{"from": list(a), "to": [16, 11]}),  # stale
              rd(4.6, "base", b), rd(6.0, "light", (20, 10)), rd(7.02, "base", b),
              ev(7.5, "walk", clicked=True, **{"from": list(b), "to": [18, 10]}),  # sent
              ev(8.0, "stuck", why="pos_unread", at=list(b)), ev(8.1, "jump"),
              ev(9.0, "run_end")]  # fmt: skip
    packets = [move(0.5, (10, 10), a),
               pk(4.0, "self_move_request", x=16, y=10), move(4.0, a, b),
               pk(7.0, "entity_stop", gid=US, x=20, y=10),
               pk(7.6, "self_move_request", x=18, y=10)]  # fmt: skip
    return events, packets


def test_reads_spans_and_their_kinds() -> None:
    events, packets = run()
    r = sl.analyse(events, packets, "syn")
    s = r["summary"]
    assert s["reads"] == 13 and s["fresh_share"] == round(6 / 13, 4)
    assert s["failures"] == {"light_failed:uncovered_ink": 6, "unconfirmed": 1}
    sp1, sp2 = r["spans"]
    # the held-back read: unconfirmed only, LATE by LF-1's own dt, closed 0.2 s later
    assert (sp1["t"], sp1["attrib_s"], sp1["gap_s"], sp1["n_failed"]) == (3.0, 0.2, 2.0, 1)
    assert sp1["unconfirmed_only"] and sp1["late"] and sp1["late_basis"] == "lf1"
    assert not sp1["persistent"]
    # six failed reads: persistent, closed by the base read at 4.6 s
    assert (sp2["t"], sp2["attrib_s"], sp2["n_failed"], sp2["persistent"]) == (3.4, 1.2, 6, True)
    assert sp2["closed_by"] == "fresh" and not sp2["late"] and not sp2["unconfirmed_only"]
    assert s["persistent"]["n"] == 1 and s["persistent"]["s"] == 1.2
    assert s["unconfirmed_only"]["n"] == 1 and s["late"]["n"] == 1
    # without LF-1's held_dt the late test falls back to the gap to the previous main read
    old = [{k: v for k, v in e.items() if k not in ("held", "held_dt")} for e in events]
    sp_old = sl.analyse(old, packets)["spans"][0]
    assert sp_old["late"] and sp_old["late_basis"] == "main_gap"
    assert sp_old["prev_read_gap_s"] == 1.8


def test_walks_classed_with_here_and_landing_errors() -> None:
    r = sl.analyse(*run())
    w_fresh, w_stale, w_sent = r["walks"]
    assert (w_fresh["class"], w_fresh["sent"]) == ("fresh", False)  # no request within the window
    # the stale walk: here (12,10) vs the packets at its request (12,10); landed (16,10) vs (16,11)
    assert (w_stale["class"], w_stale["sent"], w_stale["here_err"], w_stale["err"]) == (
        "reader", True, 0, 1)  # fmt: skip
    assert w_stale["in_unconfirmed_only"] is False and w_stale["in_late"] is False
    assert (w_sent["class"], w_sent["age_s"], w_sent["sent"]) == ("fresh", 0.48, True)
    s = r["summary"]
    assert s["stale_walks"]["n"] == 1 and s["stale_walks"]["unsent"] == 0
    assert s["walks"]["fresh"]["n"] == 2 and s["walks"]["fresh"]["unsent_share"] == 0.5
    # a walk event logged > 0.6 s after a fresh read with no failed read between: BLOCKED
    late_walk = ev(1.9, "walk", clicked=True, **{"from": [12, 10], "to": [14, 10]})
    events, packets = run()
    assert sl.analyse(sorted([*events, late_walk], key=lambda e: e["t_ns"]),
                      packets)["walks"][1]["class"] == "blocked"  # fmt: skip
    # the reach skip inside the persistent span: stale, here error 0
    assert r["reach_skips"] == [{"t": 3.5, "class": "reader", "age_s": 0.3, "here_err": 0}]


def test_the_escape_and_the_wrong_reads() -> None:
    r = sl.analyse(*run())
    (esc,) = r["escapes"]
    # here (16,10); the pin put us at (20,10) at 7.0 s: 4 cells; the last fresh read 0.98 s before
    assert (esc["t"], esc["here_err"], esc["since_fresh_s"]) == (8.0, 4, 0.98)
    assert esc["walk_sent_lt_2s"]  # the 7.5-s walk click was sent (LF-4's case)
    # 6.0 s: standing on (16,10) since 4.6 s (1.4 s), read (20,10): WRONG; 7.02 s: 0.02 s after
    # the pin -- not standing, not counted
    assert [(w["t"], w["still_s"]) for w in r["wrong"]] == [(6.0, 1.4)]
    assert r["summary"]["wrong_standing"] == 1 and r["summary"]["jumps"] == 1
    # LF-1 / LF-2 fields
    assert r["held"] == [{"t": 3.0, "held": [12, 10], "held_dt": 1.8, "lf2": None,
                          "rd": "unconfirmed", "err": 0, "standing": True}]  # fmt: skip
    assert r["lf2"] == {"ok": 1}
    assert r["summary"]["held"] == {"n": 1, "late": 1, "within1": 1, "err_p50": 0}


def test_still_cell_rule_and_the_quantile() -> None:
    pts = [(0, (1, 1)), (5 * S, (1, 1)), (10 * S, (2, 1)), (20 * S, (2, 1))]
    ch = sl.change_times(pts)
    assert ch == [0, 10 * S]  # a repeated cell (a pin on the same cell) is no change
    assert sl.still_s(ch, 15 * S) == 5.0 and sl.still_s(ch, 9 * S) == 9.0
    assert sl.still_s(ch, -1) is None
    assert sl.q([5, 1, 3, 2], 0.5) == 3  # the study's upper median
    assert sl.q([], 0.5) is None


def test_pooled_summary_sums_runs() -> None:
    events, packets = run()
    r = sl.analyse(events, packets)
    pooled = sl.summary([r, r])
    assert pooled["runs"] == 2 and pooled["reads"] == 26 and pooled["persistent"]["n"] == 2
    assert pooled["stale_walks"]["n"] == 2 and pooled["pos_unread_escapes"] == 2


def test_lf4_unread_step_outcomes() -> None:
    """LF-4 (dungeon@9.22): the runner's ``unread_step`` events as it writes them. Escape 1 waits
    for a young walk click, steps once (sent; the client walks us 2 cells west) and ends FRESH;
    escape 2 steps twice (the first unsent), then the wing; escape 3 is refused (no safe step)."""
    a = (20, 10)
    events = [ev(0.0, "run_start"), rd(1.0, "base", a),
              ev(21.0, "unread_step", event="wait", why="walk_sent", age_s=0.1,
                 since_read_s=20.0),
              ev(23.0, "unread_step", event="step", n=1, rel=[-2, 0], u=572.5, v=362.0,
                 verdicts=["clear"], dir={"by": "walk", "rel": [7, 0], "age_s": 2.1},
                 held=list(a), cands=[list(a)], since_read_s=22.0),
              ev(24.0, "unread_step", event="fresh", steps=1, s=3.0, at=[18, 10],
                 held=list(a)),
              rd(24.0, "base", (18, 10)),
              ev(50.0, "unread_step", event="step", n=1, rel=[0, 2], verdicts=["clear"]),
              ev(52.0, "unread_step", event="step", n=2, rel=[0, 2], verdicts=["clear"]),
              ev(54.0, "unread_step", event="wing", steps=2, s=4.0, why="steps"),
              ev(54.0, "stuck", why="pos_unread", at=[18, 10]),
              ev(80.0, "unread_step", event="refused", steps=0, s=0.0, why="zone_near"),
              ev(90.0, "run_end")]  # fmt: skip
    b, c = (18, 10), (18, 12)
    packets = [move(0.5, (21, 10), a),
               pk(23.05, "self_move_request", x=18, y=10), move(23.05, a, b),
               pk(52.1, "self_move_request", x=18, y=12), move(52.1, b, c)]  # fmt: skip
    r = sl.analyse(events, packets, "syn")
    st1, fresh, st2a, st2b, wing, refused = r["lf4"][1:]
    assert r["lf4"][0] == {"t": 21.0, "event": "wait", "why": "walk_sent", "steps": None}
    assert (st1["sent"], st1["req"], st1["err"], st1["true"]) == (True, [18, 10], 0, [20, 10])
    assert (fresh["event"], fresh["steps"], fresh["err"]) == ("fresh", 1, 0)
    assert (st2a["sent"], st2a["err"]) == (False, None)  # no request: not sent
    assert (st2b["sent"], st2b["err"]) == (True, 0)
    assert (wing["event"], wing["why"], wing["steps"]) == ("wing", "steps", 2)
    assert (refused["why"], refused["steps"]) == ("zone_near", 0)
    s = r["summary"]["lf4"]
    assert s == {"events": {"wait": 1, "step": 3, "fresh": 1, "wing": 1, "refused": 1},
                 "steps": 3, "steps_sent": 2, "step_err_p50": 0, "fresh_after_step": 1,
                 "fresh_in_wait": 0, "fresh_err_gt2": 0, "wings": 1,
                 "refused": {"zone_near": 1}}  # fmt: skip
    # a run without the flag: an empty LF-4 block, nothing else changes
    base = sl.analyse(*run())
    assert base["lf4"] == [] and base["summary"]["lf4"]["steps"] == 0
    assert sl.summary([base, r])["lf4"]["steps"] == 3
