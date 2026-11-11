"""--unreach-escape (dungeon@9.26, rogue-xmas02.md Study S-UA; Batt 2026-11-11, 4BT item 1): the
PURE trigger rule, the escape's marks, walk targets and decision, the flag OFF by default and its
fixes record, the runner's wiring, and the scorer (scripts/unreach_score.py) on p57's REAL trap --
its numbers copied from the session (NAS scratch-archive/2026-11-11/demo-sessions/
20261111T082037-...-xmas02-p57: events.jsonl, battle_log_live.jsonl, packets.jsonl.gz)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import unreach_score as us  # noqa: E402

NS = 1_000_000_000
L = dh.NoHitLock


def lk(t0: float, t1: float, cell: tuple[int, int] | None, n: int, sign: float) -> dh.NoHitLock:
    return L(t0=t0, t1=t1, cell=cell, n=n, sign_t=sign)


# --- the trigger (PURE) -----------------------------------------------------------------------


def test_unreach_constants_are_the_studys_pick() -> None:
    """Study S-UA's rule picked K = 3 (K = 2 had 3 false triggers, 2 of them harmful) and W = 90
    (the largest W with 0 false at K = 3); the escape's cells are 1 apart at most."""
    assert (dh.UNREACH_K, dh.UNREACH_W_S, dh.UNREACH_TOL) == (3, 90.0, 1)
    assert (dh.UNREACH_MARK_S, dh.UNREACH_MARK_R) == (120.0, 1)
    assert (dh.UNREACH_WALK_R, dh.UNREACH_AWAY, dh.UNREACH_TRIES) == (12, 9, 3)
    assert (dh.UNREACH_GRACE_S, dh.UNREACH_AGAIN_S, dh.UNREACH_VERSION) == (2.5, 120.0, "9.26")


def test_unreach_trigger_fires_on_three_no_hit_locks_on_one_cell() -> None:
    locks = [lk(0.0, 4.0, (99, 206), 5, 1.0), lk(6.0, 10.0, (99, 206), 6, 7.0),
             lk(12.0, 16.0, (100, 206), 7, 14.0)]  # fmt: skip
    tr = dh.unreach_trigger(locks, [])
    assert tr == {"locks": 3, "cells": [[99, 206], [99, 206], [100, 206]], "span_s": 16.0,
                  "n": [5, 6, 7], "t0": 0.0, "t1": 16.0}  # fmt: skip
    assert dh.unreach_trigger(locks[:2], []) is None  # fewer than K
    assert dh.unreach_trigger(locks[:2], [], k=2) is not None
    # only the NEWEST k count: an old lock elsewhere before them changes nothing
    assert dh.unreach_trigger([lk(-9.0, -5.0, (10, 10), 4, -6.0), *locks], []) == tr


def test_unreach_trigger_each_condition_breaks_the_chain() -> None:
    base = [lk(0.0, 4.0, (99, 206), 5, 1.0), lk(6.0, 10.0, (99, 206), 6, 7.0),
            lk(12.0, 16.0, (100, 206), 7, 14.0)]  # fmt: skip
    assert dh.unreach_trigger(base, []) is not None

    def with_(i: int, **kw: object) -> list[dh.NoHitLock]:
        out = list(base)
        d = {f: getattr(out[i], f) for f in ("t0", "t1", "cell", "n", "sign_t")}
        d.update(kw)
        out[i] = L(**d)  # type: ignore[arg-type]
        return out

    assert dh.unreach_trigger(with_(2, n=8), []) is None  # a strike between: not consecutive
    assert dh.unreach_trigger(with_(2, cell=(101, 206)), []) is None  # x spread 2
    assert dh.unreach_trigger(with_(1, cell=(99, 208)), []) is None  # y spread 2
    assert dh.unreach_trigger(with_(0, cell=None), []) is None  # a cell unknown
    assert dh.unreach_trigger(base, [], w=15.9) is None  # longer than W
    assert dh.unreach_trigger(base, [], w=16.0) is not None
    assert dh.unreach_trigger(with_(0, sign_t=-0.5), []) is None  # lock 1: no sign in its span
    assert dh.unreach_trigger(with_(1, sign_t=4.0), []) is None  # lock 2: the sign is lock 1's
    assert dh.unreach_trigger(with_(1, sign_t=4.01), []) is not None  # after lock 1's end: ok
    assert dh.unreach_trigger(with_(2, sign_t=16.5), []) is None  # after its own end
    assert dh.unreach_trigger(base, [8.0]) is None  # one damage line of ours in the span
    assert dh.unreach_trigger(base, [-0.1, 16.1]) is not None  # ours outside the span: fine


def test_unreach_marks_and_the_scan_cells() -> None:
    m = dh.unreach_marks({}, [[99, 206], [100, 206]], until=200.0)
    assert len(m) == 12 and m[(98, 205)] == 200.0 and m[(101, 207)] == 200.0  # 3 x 4 block
    assert dh.unreach_marked(m, (98, 205), 199.9) and not dh.unreach_marked(m, (98, 205), 200.0)
    assert not dh.unreach_marked(m, (102, 206), 100.0) and not dh.unreach_marked(m, None, 0.0)
    m2 = dh.unreach_marks(m, [[98, 205]], until=150.0)  # an earlier until never shortens a mark
    assert m2[(98, 205)] == 200.0 and m2[(97, 204)] == 150.0
    ring1 = dh.ring(1)
    here = (100, 207)
    kept = dh.unreach_scan_cells(ring1, here, m, 100.0)
    assert set(ring1) - set(kept) == {(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0)}
    assert kept == [c for c in ring1 if c in kept]  # the ring's own order kept
    assert dh.unreach_scan_cells(ring1, None, m, 100.0) == ring1  # no position: no skip
    assert dh.unreach_scan_cells(ring1, here, m, 300.0) == ring1  # expired


def test_unreach_walk_targets_go_far_from_the_attacker_cells() -> None:
    """A corridor y = 207 (x 90-115) and a column x = 108 (y 195-215): the cells >= 9 from the
    chain's cells, the farthest from them first, then the nearest to us; at most ``limit``."""
    open_ = {(x, 207) for x in range(90, 116)} | {(108, y) for y in range(195, 216)}
    here, cells = (100, 207), [[99, 206], [100, 206]]
    got = dh.unreach_walk_targets(here, cells, lambda c: c in open_, lambda c: True)
    assert got == [(112, 207), (111, 207), (108, 195)]  # gap 12, then two of 11: nearer first
    assert all(min(max(abs(c[0] - a[0]), abs(c[1] - a[1])) for a in cells) >= 9 for c in got)
    # the server answers no click east of x = 109: gap 11, gap 10, then the nearest of gap 9
    assert dh.unreach_walk_targets(here, cells, lambda c: c in open_, lambda c: c[0] < 110) == [
        (108, 195), (108, 196), (108, 215)]  # fmt: skip
    assert dh.unreach_walk_targets(here, cells, lambda c: c in open_, lambda c: True, limit=1) == [
        (112, 207)]  # fmt: skip
    assert dh.unreach_walk_targets(here, cells, lambda c: False, lambda c: True) == []
    assert dh.unreach_walk_targets(here, [], lambda c: True, lambda c: True) == []
    # nothing in a corridor 3 cells long is 9 away: the Fly Wing's case
    short = {(x, 207) for x in range(98, 104)}
    assert dh.unreach_walk_targets(here, cells, lambda c: c in short, lambda c: True) == []


def test_unreach_action_walks_then_flies() -> None:
    assert dh.unreach_action((100, 207), (112, 207), [], 500.0) == ("walk", "away")
    assert dh.unreach_action((100, 207), None, [], 500.0) == ("fly", "no_cell")
    assert dh.unreach_action(None, None, [], 500.0) == ("fly", "no_position")
    assert dh.unreach_action((100, 207), (112, 207), [400.0], 500.0) == ("fly", "again")
    assert dh.unreach_action((100, 207), (112, 207), [380.0], 500.0) == ("walk", "away")  # 120 s


def test_unreach_escape_is_refused_without_its_partners() -> None:
    assert dh.unreach_refused(True, True) is None
    assert "--reach-check" in str(dh.unreach_refused(False, True))
    assert "--engage-screen" in str(dh.unreach_refused(True, False))
    src = Path(dh.__file__).read_text()
    i_r = src.index('raise SystemExit(f"dungeon@9.26 refused: {why_ua}")')
    assert i_r < src.index("typed: list[str] = []")  # before the setup types anything


# --- OFF by default, the fixes record, the wiring --------------------------------------------


def test_unreach_escape_is_off_by_default_and_recorded_in_the_fixes() -> None:
    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": True,
            "walk_ahead": dh.WALK_AHEAD, "walk_through": False, "reach_check": True,
            "engage_screen": True}  # fmt: skip
    ns = argparse.Namespace
    assert "unreach_escape" not in dh.fixes_of(ns(**base))
    assert "unreach_escape" not in dh.fixes_of(ns(**base, unreach_escape=False))
    rec = dh.fixes_of(ns(**base, unreach_escape=True))
    assert rec["unreach_escape"] == [3, 90.0, 1, 120.0, 12, 9, 120.0, "9.26"]
    rest = {k: v for k, v in rec.items() if k != "unreach_escape"}
    assert rest == dh.fixes_of(ns(**base))  # its own key only
    src = Path(dh.__file__).read_text()
    flag = '"--unreach-escape",\n        action=argparse.BooleanOptionalAction,\n'
    flag += "        default=False,"
    assert flag in src
    assert src.count('unreach_on = getattr(a, "unreach_escape", False)') == 1
    assert src.count('"fixes": fixes_of(a)') == 2  # run_start and the manifest both record it


def _body(src: str, start: str, stop: str) -> str:
    b = src[src.index(start) :]
    return b[: b.index(stop, len(start))]


def test_unreach_escape_is_wired_only_behind_its_flag() -> None:
    """Every runtime use sits behind ``unreach_on``: the HP-drop sign, the no-hit unlock (record,
    trigger, escape, then ``continue``), the defend scan's skip and the box path's skip (in
    --reach-check's reach test). The escape clicks only through click_at after a hover that read
    clear, or presses the Fly Wing through press(); no other input."""
    src = Path(dh.__file__).read_text()
    assert src.count("unreach_on") == 5  # its definition + 4 guarded uses
    assert "                if unreach_on and dropped:\n                    ua_drop_t = tick" in src
    # the no-hit unlock: the event first, then the record + trigger, then the lock goes
    nh = _body(src, '                            ev({"kind": "unlock", "why": "no hits" if since',
               "                        elif getattr(a, \"quick_drop\", False)")  # fmt: skip
    i_on = nh.index("if unreach_on and since <= LOCK_MAX_S:  # dungeon@9.26 (Study S-UA)")
    i_rec = nh.index("ua_locks.append(ua_lock(lock, tick))")
    i_tr = nh.index("tr_u = unreach_trigger(ua_locks, ours_ticks)")
    i_clear = nh.index("ua_locks.clear()")
    i_esc = nh.index("act_u = unreach_escape(tr_u, tick)")
    i_mode = nh.index('mode = "search"')
    i_cont = nh.index("continue")
    i_lock = nh.rindex("lock = None")
    assert i_on < i_rec < i_tr < i_clear < i_esc < i_mode < i_cont < i_lock
    assert "last_walk = tick + UNREACH_GRACE_S" in nh and "fly_at = time.monotonic()" in nh
    # the scan's skip and the box path's skip
    sc = _body(src, "        def scan(purpose: str, cells: Sequence[Cell], stop_on: str",
               "        def read_here()")  # fmt: skip
    i_ws = sc.index("kept = drop_false(cells, false_rel, t_s)")
    i_ua = sc.index('if purpose == "defend" and unreach_on and ua_marks:')
    assert i_ws < i_ua < sc.index("uv = project(here, cells)")
    assert "unreach_scan_cells(cells, here, ua_marks, t_s)" in sc
    ur = _body(src, "        def unreachable(here_: Cell | None, foot: Sequence[float]) -> bool:",
               "        def box_fight_done()")  # fmt: skip
    i_m = ur.index("if unreach_on and unreach_marked(ua_marks, sp_, time.monotonic()):")
    assert ur.index("sp_ = reach_pick[kp_]") < i_m < ur.index("key_ = (here_, sp_)")
    # the escape: hover -> clear -> click_at; else the Fly Wing; no direct input
    es = _body(src, "        def unreach_escape(tr: Mapping[str, Any], tick_: float) -> str:",
               "        ex_rec: Any = None")  # fmt: skip
    for word in (".click(", "agent.", "keys(", "sleep("):
        assert word not in es, word
    i_h = es.index('vd_ = str(hover(u_t, v_t)["verdict"])')
    i_c = es.index('if vd_ == "clear":')
    i_a = es.index("action, why_ = unreach_action(h_, to_, ua_walks, tick_)")
    i_k = es.index('click_at(u_w, v_w, "walk")')
    i_f = es.index('press("fly", "unreach")')
    assert i_h < i_c < i_a < i_k < i_f
    assert 'unreach_walk_targets(h_, tr["cells"], ua_fits, ua_reach)' in es
    assert "wkp_u.click_walk_ok(reach_grid, h[0], h[1], c_[0], c_[1])" in es
    assert 'note_move(rel_, "walk")' in es  # 9.22's dead reckoning sees it as a walk click
    assert "walk_pick_ok(picked_cell(camera, gat, h, (u_, v_)), c_, okr)" in es
    for key in (
        '"kind": "unreach"',
        '"t0_ns"',
        '"cells": tr["cells"]',
        '"span_s": tr["span_s"]',
        '"action": action',
        '"to": None if to_ is None else list(to_), "tried": tried_',
    ):
        assert key in es, key


# --- the scorer on p57's REAL trap --------------------------------------------------------------

P57_T0 = 324929913910687  # run_start
P57_ME, P57_CRUISER = 2000002, 110063213
# 811.5 s - 840 s: the Rogue's attack requests at the Cruiser (every ~1.2 s), each answered in the
# same ms by her entity_stop on (100,207); the Cruiser's acts on her (damage 0 but one 159)
P57_REQ = [325741424185341, 325742657614061, 325743858450100, 325745059113668, 325746292372262,
           325747493566557, 325748727038581, 325749960373427, 325751193958002, 325752494224410,
           325753727610986, 325754961195407, 325756162931339, 325757395699371, 325758629395802,
           325759863481831, 325761096271255, 325762330539851, 325763562905145, 325764764119522,
           325765997187254, 325767198242655, 325768431879662, 325769664822987]  # fmt: skip
P57_STOP = [325741424326539, 325742657764529, 325743858566019, 325745059247802, 325746292527967,
            325747493718660, 325748727178813, 325749960553372, 325751194080515, 325752494336064,
            325753727742675, 325754961311561, 325756163088728, 325757395831997, 325758629505431,
            325759863643616, 325761096381377, 325762330681566, 325763563047178, 325764764258213,
            325765997346914, 325767198385156, 325768432050899, 325769664978394]  # fmt: skip
P57_ACT = [(325739723566154, 0), (325741019409649, 0), (325742315766105, 0),
           (325743611722542, 0), (325744924667385, 0), (325746223473184, 0),
           (325747519950567, 0), (325748815358339, 0), (325750113495456, 159),
           (325751423928371, 0), (325752724500189, 0), (325756024043370, 0),
           (325757324416504, 0), (325758623751562, 0), (325759919883837, 0),
           (325761215463826, 0), (325762512235647, 0), (325763808252131, 0),
           (325765104697313, 0), (325766403837966, 0), (325767699612248, 0),
           (325768996141975, 0)]  # fmt: skip
# the runner's events: the held cell (main reads, as logged), strikes (t_ns, t_end_ns, rel),
# unlocks, Miss cues; the Battle Log's one taken line
P57_EVENTS = [
    ("hp", 325737556133486, [107, 208]),
    ("strike", 325741089160230, 325743052068160, [-2, -2]),  # the box strike: here still stale
    ("miss_cue", 325743116712139),
    ("hp", 325743144075500, [100, 207]),
    ("unlock", 325746768399417),
    ("strike", 325748642867441, 325749275801926, [-1, -1]),
    ("miss_cue", 325749343325537),
    ("unlock", 325752965933872),
    ("strike", 325755071157349, 325758688129372, [-1, -1]),
    ("miss_cue", 325758755124286),
    ("miss_cue", 325761757687197),
    ("unlock", 325762376472450),
    ("strike", 325763361019433, 325764509380841, [0, -1]),
    ("miss_cue", 325764604862558),
    ("unlock", 325768195541843),
]
P57_TAKEN = [325751463803052]


def p57_packets() -> list[dict[str, object]]:
    pk: list[dict[str, object]] = []
    pk += [{"type": "attack_request", "t_mono_ns": t, "target_gid": P57_CRUISER} for t in P57_REQ]
    pk += [{"type": "entity_stop", "t_mono_ns": t, "gid": P57_ME, "x": 100, "y": 207}
           for t in P57_STOP]  # fmt: skip
    pk += [{"type": "act", "t_mono_ns": t, "src_gid": P57_CRUISER, "target_gid": P57_ME,
            "damage": d} for t, d in P57_ACT]  # fmt: skip
    return sorted(pk, key=lambda p: int(str(p["t_mono_ns"])))


def p57_events() -> list[dict[str, object]]:
    out: list[dict[str, object]] = [{"t_ns": P57_T0, "kind": "run_start"}]
    for row in P57_EVENTS:
        if row[0] == "hp":
            out.append({"t_ns": row[1], "kind": "hp_read", "pct": 69, "pos": row[2]})
        elif row[0] == "strike":
            out.append({"t_ns": row[1], "t_end_ns": row[2], "kind": "strike", "rel": row[3]})
        elif row[0] == "unlock":
            out.append({"t_ns": row[1], "kind": "unlock", "why": "no hits", "s": 3.6})
        else:
            out.append({"t_ns": row[1], "kind": "miss_cue", "score": 0.8})
    return out


def test_p57_real_trap_is_found_by_the_packets() -> None:
    got = us.traps(p57_packets(), P57_ME)
    assert len(got) == 1
    tp = got[0]
    assert tp["gid"] == P57_CRUISER and tp["start_ns"] == P57_REQ[0]
    assert round((tp["start_ns"] - P57_T0) / NS, 2) == 811.51
    assert tp["requests"] == 24 and tp["stopped"] == 24  # every request answered by her stop
    assert tp["acts_on_us"] == 20 and tp["hits_on_us"] == 1 and tp["damage_on_us"] == 159
    assert tp["s"] == 28.2
    # one damaging act of ours on it splits the span there: 12.3 s + 14.7 s, each under TRAP_S
    hit = {"type": "act", "t_mono_ns": P57_REQ[10] + 1, "src_gid": P57_ME,
           "target_gid": P57_CRUISER, "damage": 200}  # fmt: skip
    assert us.traps(sorted([*p57_packets(), hit], key=lambda p: int(str(p["t_mono_ns"]))),
                    P57_ME) == []  # fmt: skip
    assert us.traps(p57_packets(), None) == []


def test_p57_real_trap_fires_the_trigger_at_its_third_lock() -> None:
    """The box strike's lock (811.2 s) used the stale held cell (107,208): its cell (105,206) is
    not the others', so the chain is locks 2-4 -- (99,206), (99,206), (100,206) -- and the trigger
    fires at the 4th unlock, 838.28 s: 26.8 s after the trap's first request."""
    lines = [{"t_ns": t, "type": "taken"} for t in P57_TAKEN]
    locks = us.no_hit_locks(p57_events(), lines)
    assert [lk_.cell for lk_ in locks] == [(105, 206), (99, 206), (99, 206), (100, 206)]
    assert [lk_.n for lk_ in locks] == [1, 2, 3, 4]
    trs = us.replay(locks, [], dh.UNREACH_K, dh.UNREACH_W_S)
    assert len(trs) == 1
    tr = trs[0]
    assert tr["cells"] == [[99, 206], [99, 206], [100, 206]] and tr["n"] == [2, 3, 4]
    assert round(tr["t1"] * NS) == 325768195541843 and tr["span_s"] == 18.9
    j = us.judge(round(tr["t0"] * NS), round(tr["t1"] * NS), p57_packets(), P57_ME)
    assert j["verdict"] == "trap" and j["attacker"] == P57_CRUISER and j["our_hits"] == 0
    tp = us.traps(p57_packets(), P57_ME)[0]
    assert us.catch_s(tp, trs) == 26.8
    # K = 2 fires one lock earlier (locks 2-3, at 832.46 s); K = 4 never here (lock 1's cell)
    trs2 = us.replay(locks, [], 2, 90.0)
    assert round((trs2[0]["t1"] * NS - P57_T0) / NS, 2) == 832.46
    assert us.replay(locks, [], 4, 90.0) == []
    # a damage line of ours inside the chain's span: no trigger
    assert us.replay(locks, [tr["t0"] + 5.0], 3, 90.0) == []


def test_judge_classes() -> None:
    pk = p57_packets()
    assert us.judge(P57_REQ[0], P57_REQ[-1], pk, P57_ME)["verdict"] == "trap"
    ours = {"type": "act", "t_mono_ns": P57_REQ[3], "src_gid": P57_ME, "target_gid": 7,
            "damage": 150}  # fmt: skip
    assert us.judge(P57_REQ[0], P57_REQ[-1], [*pk, ours], P57_ME)["verdict"] == "harmful"
    no_req = [p for p in pk if p["type"] != "attack_request"]
    assert us.judge(P57_REQ[0], P57_REQ[-1], no_req, P57_ME)["verdict"] == "helpless"
    assert us.judge(P57_REQ[0], P57_REQ[-1], [], P57_ME)["verdict"] == "quiet"


def test_the_rule_picks_the_smallest_k_then_the_largest_w() -> None:
    rows = [{"k": 2, "w": 30.0, "false": 3, "caught_all": True},
            {"k": 3, "w": 15.0, "false": 0, "caught_all": False},
            {"k": 3, "w": 30.0, "false": 0, "caught_all": True},
            {"k": 3, "w": 90.0, "false": 0, "caught_all": True},
            {"k": 4, "w": 30.0, "false": 0, "caught_all": True}]  # fmt: skip
    got = us.pick(rows)
    assert (got["k"], got["w"]) == (3, 90.0) and got["how"].startswith("eligible")
    no_zero = [{**r, "false": r["false"] + 1} for r in rows]
    got = us.pick(no_zero)
    assert (got["k"], got["w"]) == (3, 30.0) and "no eligible" in got["how"]
    assert us.pick([{**r, "caught_all": False} for r in rows])["k"] is None


def test_score_reads_a_live_unreach_event() -> None:
    """score(): a runner ``unreach`` event is judged on its own span and its outcome is read from
    the packets (the walk's request and landing, the attacker's acts after it)."""
    ev = p57_events()
    t_fire = 325768195541843
    ev.append({"t_ns": t_fire + 5_000_000, "kind": "unreach", "t0_ns": 325749275801926,
               "locks": 3, "cells": [[99, 206], [99, 206], [100, 206]], "span_s": 18.9,
               "action": "walk", "why": "away", "to": [112, 200]})  # fmt: skip
    pk = p57_packets()
    pk = [p for p in pk if int(str(p["t_mono_ns"])) <= t_fire]  # the walk ended the trap
    pk += [{"type": "self_move_request", "t_mono_ns": t_fire + 300_000_000, "x": 112, "y": 200},
           {"type": "self_move", "t_mono_ns": t_fire + 300_100_000, "x0": 100, "y0": 207,
            "x1": 112, "y1": 200}]  # fmt: skip
    run = {"name": "p57x", "events": ev, "lines": [], "packets": pk, "t0": P57_T0,
           "t_end": t_fire + 70 * NS, "gid": P57_ME, "ours": []}  # fmt: skip
    res = us.score([run])
    esc = res["runs"][0]["escapes"]
    assert len(esc) == 1
    e = esc[0]
    assert e["verdict"] == "trap" and e["action"] == "walk"
    assert e["walk_sent"] and e["walk_to"] == [112, 200] and e["walk_err"] == 0
    assert e["ended"] and e["attacker_acts_after"] == 0 and not e["fly_60s"]
    assert res["pooled"]["escapes"] == 1 and res["pooled"]["escapes_false"] == 0
