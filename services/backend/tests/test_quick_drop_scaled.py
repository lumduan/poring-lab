"""dungeon_hunt.py --quick-drop-scaled (dungeon@9.38, rogue-xmas02.md 4DG; Batt 2026-11-12: "test a
stricter --quick-drop"): with --quick-drop, the lock's no-hit window after the strike's arrow grows
with the strike's distance in cells, 2.0 s + 0.2 s a cell, at most 3.5 s. OFF by default; the
default path (and --quick-drop without it) is unchanged."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
BASE = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
        "rest": "spot", "npc_guard": True, "miss_cue": False}  # fmt: skip


def test_the_constants_are_the_walk_up_and_the_plain_unlock() -> None:
    assert (dh.QUICK_PER_CELL, dh.QUICK_HIT_MAX_S, dh.QUICK_SCALED_VERSION) == (0.2, 3.5, "9.38")
    assert dh.QUICK_PER_CELL == dh.FAR_PER_CELL_S  # the walk-up's measured time a cell
    assert dh.QUICK_HIT_MAX_S == dh.LOCK_NO_HIT_S  # longer never fires: "no hits" comes first
    assert (dh.QUICK_ARROW_S, dh.QUICK_HIT_S, dh.QUICK_RETRY) == (2.0, 2.0, 2)  # unchanged


def test_the_window_grows_with_the_distance_up_to_the_cap() -> None:
    w = dh.quick_hit_window
    assert w((0, 0)) == pytest.approx(2.0)
    assert w((1, -1)) == pytest.approx(2.2) and w((0, 2)) == pytest.approx(2.4)
    assert w((-6, 3)) == pytest.approx(3.2) and w((7, 1)) == pytest.approx(3.4)  # Chebyshev
    assert w((-8, 6)) == dh.QUICK_HIT_MAX_S and w((0, 20)) == dh.QUICK_HIT_MAX_S  # the cap
    widths = [w((c, 0)) for c in range(0, 16)]
    assert widths == sorted(widths)  # never shorter for a farther target


def test_the_window_is_never_shorter_than_the_default_rules() -> None:
    """The default hit_s: QUICK_HIT_S, or max(QUICK_HIT_S, far_window) with --far-single."""
    for c in range(0, 20):
        for rel in ((c, 0), (0, -c), (c, c)):
            far_w = dh.far_window(rel)
            default = dh.QUICK_HIT_S if far_w is None else max(dh.QUICK_HIT_S, far_w)
            assert dh.quick_hit_window(rel, far_w) >= default, rel
            assert dh.quick_hit_window(rel, None) >= dh.QUICK_HIT_S
    assert dh.quick_hit_window((1, 0), 3.0) == 3.0  # a longer far window wins


def test_a_far_strike_keeps_its_lock_where_the_default_dropped_it() -> None:
    """The shape of 4DG's kept case: a 7-cell strike whose first hit of ours shows 2.9 s after its
    arrow (the walk-up); made-up times on the runner's clock."""
    t_click, arrow_t, hit_seen = 100.0, 100.6, 103.5
    old = max(dh.QUICK_HIT_S, dh.far_window((7, 1)) or 0.0)  # 2.4 s
    new = dh.quick_hit_window((7, 1), dh.far_window((7, 1)))  # 3.4 s
    tick = 103.2  # before the hit is seen
    assert dh.quick_no_hit(arrow_t, -1e9, t_click, tick, old)  # the default: dropped here
    assert not dh.quick_no_hit(arrow_t, -1e9, t_click, tick, new)  # scaled: still waiting
    assert not dh.quick_no_hit(arrow_t, hit_seen, t_click, 104.5, new)  # the hit: kept
    # a near strike with no hit drops 0.2 s a cell later, as before otherwise
    assert not dh.quick_no_hit(arrow_t, -1e9, t_click, 102.7, dh.quick_hit_window((1, 0)))
    assert dh.quick_no_hit(arrow_t, -1e9, t_click, 102.9, dh.quick_hit_window((1, 0)))


def _ns(monkeypatch: Any, *extra: str) -> Any:
    got: dict[str, Any] = {}

    def fake_run(a: Any) -> int:
        got["a"] = a
        return 0

    monkeypatch.setattr(dh, "run", fake_run)
    argv = ["dungeon_hunt.py", "run", "--strategy", "P2", "--seed", "1", "--char", "rogue",
            "--map", "xmas_dun02", "--search", "patrol", *extra]  # fmt: skip
    monkeypatch.setattr(sys, "argv", argv)
    assert dh.main() == 0
    return got["a"]


def test_the_flag_is_off_by_default_and_needs_quick_drop(monkeypatch: Any) -> None:
    a0 = _ns(monkeypatch)
    assert a0.quick_drop_scaled is False and dh.quick_scaled_refused(a0) is None
    assert dh.quick_scaled_refused(_ns(monkeypatch, "--quick-drop")) is None
    assert dh.quick_scaled_refused(_ns(monkeypatch, "--quick-drop", "--quick-drop-scaled")) is None
    why = dh.quick_scaled_refused(_ns(monkeypatch, "--quick-drop-scaled"))
    assert why is not None and "--quick-drop" in why


def test_run_refuses_it_without_quick_drop_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--quick-drop-scaled")
    monkeypatch.undo()  # the real run, the real argv

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert "dungeon@9.38 refused" in str(exc.value) and "--quick-drop" in str(exc.value)
    run_src = SRC[SRC.index("def run(") :]
    assert run_src.index("why_qs = quick_scaled_refused(a)") < run_src.index("with r.session(")


def test_the_record_carries_it_only_when_on() -> None:
    off = dh.fixes_of(dh.argparse.Namespace(**BASE, quick_drop=True))
    assert "quick_drop_scaled" not in off
    assert dh.fixes_of(dh.argparse.Namespace(**BASE, quick_drop=True,
                                             quick_drop_scaled=False)) == off  # fmt: skip
    on = dh.fixes_of(dh.argparse.Namespace(**BASE, quick_drop=True, quick_drop_scaled=True))
    assert on["quick_drop_scaled"] == [0.2, 3.5, "9.38"]
    assert on["quick_drop_scaled"] == [dh.QUICK_PER_CELL, dh.QUICK_HIT_MAX_S,
                                       dh.QUICK_SCALED_VERSION]  # fmt: skip
    assert {k: v for k, v in on.items() if k != "quick_drop_scaled"} == off
    assert on["quick_drop"] == [2.0, 2.0, 2]


def test_the_default_path_is_unchanged() -> None:
    """The pinned lines stay as they were; the scaled window reaches the fight loop's existing
    quick_no_hit call only through last_strike["hit_s"], set from ``qh_s``, which is None unless
    --quick-drop and --quick-drop-scaled are both on."""
    assert "hit_s=QUICK_HIT_S if far_w is None else max(QUICK_HIT_S, far_w)," in SRC
    assert "burst_s = QUICK_ARROW_S if quick else BURST_MAX_S" in SRC
    call = ('                        elif getattr(a, "quick_drop", False) and last_strike and '
            "quick_no_hit(\n"
            '                                last_strike.get("arrow_t"), last_ours, '
            'last_strike["t_click"],\n'
            '                                tick, last_strike.get("hit_s", QUICK_HIT_S)):'
            "  # fmt: skip\n")  # fmt: skip
    assert call in SRC
    assert SRC.count("quick_hit_window(") == 2  # its definition + the strike's one use
    assert ("            qh_s = (quick_hit_window(rel, far_w)\n"
            '                    if quick and getattr(a, "quick_drop_scaled", False) else None)'
            in SRC)  # fmt: skip
    assert (
        "            if qh_s is not None:  # dungeon@9.38: the fight loop's quick_no_hit "
        'reads it from here\n                last_strike["hit_s"] = qh_s\n'
    ) in SRC
    # last_strike["hit_s"] has no other writer
    tree = ast.parse(SRC)
    writes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Subscript) and ast.unparse(t) == "last_strike['hit_s']"
    ]
    assert len(writes) == 1
    # the flag is read only by the record, the refusal and the strike's window
    assert SRC.count('"quick_drop_scaled"') == 4  # fixes_of (x2), quick_scaled_refused, strike
    # the strike event carries the window only when it is set
    assert '**({"quick_hit_s": round(qh_s, 2)} if qh_s is not None else {}),' in SRC


# --- the offline analysis behind the constants (scripts/quick_drop_scaled_study.py, 4DG) ---------


def test_the_study_uses_the_runners_rule() -> None:
    import quick_drop_scaled_study as qs

    assert (qs.QUICK_HIT_S, qs.LOCK_NO_HIT_S) == (dh.QUICK_HIT_S, dh.LOCK_NO_HIT_S)
    for c in range(0, 16):
        far_w = dh.far_window((c, 0))
        used = dh.QUICK_HIT_S if far_w is None else max(dh.QUICK_HIT_S, far_w)
        got = qs.scaled_window(c, dh.QUICK_PER_CELL, dh.QUICK_HIT_MAX_S, used)
        assert got == pytest.approx(dh.quick_hit_window((c, 0), far_w)), c


def test_the_study_reads_a_drop_and_judges_the_scaled_window() -> None:
    import quick_drop_scaled_study as qs

    ns = qs.NS
    aid, mob, other = 7, 101, 102  # made-up ids
    t0 = 1000 * ns
    events = [
        {"t_ns": t0, "kind": "strike", "rel": [7, 1], "by": "box", "clicks": 1, "arrow_s": 0.2},
        {"t_ns": t0 + int(3.0 * ns), "kind": "unlock", "why": "quick", "s": 2.4},
        {"t_ns": t0 + int(3.0 * ns), "kind": "quick_drop", "why": "no_hit", "rearm": True, "n": 1},
        {"t_ns": t0 + int(10 * ns), "kind": "strike", "rel": [1, 0], "by": "scan", "clicks": 4},
        {"t_ns": t0 + int(13 * ns), "kind": "quick_drop", "why": "no_arrow", "rearm": True, "n": 1},
        {"t_ns": t0 + int(14 * ns), "kind": "strike", "rel": [0, 1], "by": "scan", "clicks": 1},
    ]  # fmt: skip
    packets = [
        {"t_mono_ns": t0 + int(1.4 * ns), "type": "attack_request", "target_gid": mob},
        {"t_mono_ns": t0 + int(2.9 * ns), "type": "act", "kind": "normal", "src_gid": aid,
         "target_gid": mob},
        {"t_mono_ns": t0 + int(3.4 * ns), "type": "act", "kind": "multi_hit", "src_gid": aid,
         "target_gid": mob},
        {"t_mono_ns": t0 + int(3.5 * ns), "type": "act", "kind": "normal", "src_gid": 9,
         "target_gid": aid},  # a monster's act on us: not ours
        {"t_mono_ns": t0 + int(14.5 * ns), "type": "act", "kind": "normal", "src_gid": aid,
         "target_gid": other},
    ]  # fmt: skip
    lines = [{"t_ns": t0 + int(3.2 * ns), "t_emit_ns": t0 + int(3.3 * ns), "type": "damage"}]
    rows = qs.drop_rows(events, packets, lines, aid)
    assert len(rows) == 2
    hit, arr = rows
    assert hit["why"] == "no_hit" and hit["cells"] == 7 and hit["request_s"] == 1.4
    assert hit["next_act_s"] == 0.4 and hit["next_on_own_target"] is True
    assert hit["new_strike_first"] is False and hit["given_up"] is True
    assert hit["line_after_arrow"] == [2.7, 2.9]  # the arrow at 3.0 - 2.4 s: [0.6 - 0.2, 0.6]
    assert qs.scaled_outcome(hit, 0.2, 3.5) == "kept"  # W 3.4 >= 2.9 + the tail lag
    assert qs.scaled_outcome(hit, 0.0, 2.0) == "drops"  # the default's 2.4 s: dropped
    assert arr["why"] == "no_arrow" and arr["request_s"] is None
    assert arr["next_act_s"] == 1.5 and arr["new_strike_first"] is True  # the next strike's act
    assert qs.scaled_outcome(arr, 0.2, 3.5) == "unchanged"
    # a window past LOCK_NO_HIT_S never keeps a later hit: the plain unlock takes the lock first
    late = {**hit, "line_after_arrow": [4.0, 4.2]}
    assert qs.scaled_outcome(late, 1.0, 10.0) == "plain_unlock"
    assert qs.scaled_outcome(late, 0.2, 3.5) == "drops"
