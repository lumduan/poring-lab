"""dungeon_hunt.py --loot-memory (dungeon@9.37, rogue-xmas02.md 4DB): the item model looks during
fights; the next loot step takes the remembered cells.

p94 (4DB): 9.36's recheck ran ONCE in 71 pending kills -- its calm rule (search mode, no lock, no
hit for 2.5 s) is almost never true within 7 s of a kill on xmas_dun02, the next monster is engaged
at once. 9.37 only LOOKS (no click, no sleep): while a kill is younger than MEMORY_S the item model
runs on a fresh frame at most every MEMORY_EVERY_S, in any mode but sitting; item cells inside a
young kill's 5 x 5 cells are remembered for MEMORY_KEEP_S; the NEXT loot step hovers its own seen
items plus the remembered cells and clears those it visited; calm with cells left -> 9.36's
recheck_visit path. The pure helpers are tested here, the wiring by source scans (the runner's loop
needs the live client)."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
TREE = ast.parse(SRC)
LINES = SRC.split("\n")
BASE = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": False,
        "rest": "spot", "npc_guard": False}  # fmt: skip
# loot_step_v1 as 9.36 left it (120 lines, commit 1ac1506c): 9.37 adds two `if lm_on ...` blocks
# (each with its comment lines) and changes nothing else in it
V1_936_SHA256 = "ea4fb46d28c7199109bd0d7f9a2e73e5b27c78fca9e5af928e8a79befb0d830d"
MEMORY_NAMES = {"lm_kills", "lm_mem", "lm_st", "memory_kill", "memory_prune", "memory_look",
                "memory_tick", "memory_merge", "memory_clear"}  # fmt: skip


def _fn(name: str) -> ast.FunctionDef:
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no function {name}")


def _nested(name: str) -> str:
    """The source of the function ``name`` (the runner's closures included)."""
    return ast.get_source_segment(SRC, _fn(name)) or ""


def _src(node: ast.AST) -> str:
    return ast.get_source_segment(SRC, node) or ""


def _parents(root: ast.AST) -> dict[ast.AST, ast.AST]:
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    return parent


def _chain(n: ast.AST, parent: dict[ast.AST, ast.AST], stop: ast.AST) -> list[ast.AST]:
    out, p = [], parent.get(n)
    while p is not None and p is not stop:
        out.append(p)
        p = parent.get(p)
    return out


def _lm_guarded(chain: list[ast.AST]) -> bool:
    return any(isinstance(c, ast.If) and _src(c.test).startswith("lm_on") for c in chain)


def _k(cell: tuple[int, int], t: float) -> Any:
    return dh.PendingKill(cell, t)


# --- the constants, the look's due-ness -----------------------------------------------------------


def test_the_constants_are_the_pre_registered_ones() -> None:
    assert (dh.MEMORY_S, dh.MEMORY_EVERY_S, dh.MEMORY_KEEP_S) == (7.0, 1.0, 30.0)  # 4DB amendment
    assert dh.LOOT_MEMORY_VERSION == "9.37"
    assert dh.MEMORY_S == dh.RECHECK_S  # the same 7 s window as 9.36's pending kills


def test_the_look_is_due_while_a_kill_is_young_once_a_second_never_sitting() -> None:
    kills = [_k((10, 10), 100.0)]
    assert dh.memory_look_due(101.0, -1e9, kills, False)  # never looked: due
    assert not dh.memory_look_due(101.0, -1e9, kills, True)  # sitting: never
    assert not dh.memory_look_due(101.0, -1e9, [], False)  # no kill: never
    assert dh.memory_look_due(100.0 + dh.MEMORY_S - 0.01, -1e9, kills, False)
    assert not dh.memory_look_due(100.0 + dh.MEMORY_S, -1e9, kills, False)  # the kill is old
    assert not dh.memory_look_due(103.0 + dh.MEMORY_EVERY_S - 0.01, 103.0, kills, False)
    assert dh.memory_look_due(103.0 + dh.MEMORY_EVERY_S, 103.0, kills, False)
    old, young = _k((1, 1), 90.0), _k((2, 2), 99.0)
    assert dh.memory_look_due(100.0, -1e9, [old, young], False)  # ANY young kill


# --- remember / expire / merge / clear (pure) -----------------------------------------------------


def test_an_item_inside_a_young_kills_cells_is_remembered_outside_it_is_not() -> None:
    a_, b_ = _k((10, 10), 100.0), _k((30, 30), 101.0)
    mem, new, kept = dh.memory_remember({}, [(12, 12), (13, 10), (31, 29)], [a_, b_], 102.0)
    assert new == [(12, 12), (31, 29)] and kept == new  # (13, 10): one cell outside the 5 x 5
    assert set(mem) == {(12, 12), (31, 29)}
    assert mem[(12, 12)] == dh.Remembered(102.0, frozenset(dh.kill_cells((10, 10))))
    assert mem[(31, 29)].plan == frozenset(dh.kill_cells((30, 30)))
    # a kill MEMORY_S old is not looked at any more: its cells remember nothing
    mem2, new2, _ = dh.memory_remember({}, [(12, 12)], [a_], 100.0 + dh.MEMORY_S)
    assert mem2 == {} and new2 == []
    # the loot step's plan filter: a cell off the map / not walkable / in a zone is passed by
    fits = lambda c: c != (12, 12)  # noqa: E731
    assert dh.memory_remember({}, [(12, 12)], [a_], 102.0, fits)[0] == {}
    assert dh.memory_remember({}, [(11, 11)], [a_], 102.0, fits)[0][(11, 11)].plan == frozenset(
        dh.kill_cells((10, 10), fits)
    )
    assert dh.memory_remember({}, [(10, 10)], [], 102.0) == ({}, [], [])


def test_a_re_seen_cell_is_re_timed_not_new_and_its_plan_grows() -> None:
    a_, b_ = _k((10, 10), 100.0), _k((13, 10), 104.0)
    mem, new, _ = dh.memory_remember({}, [(12, 10)], [a_], 101.0)
    assert new == [(12, 10)]
    mem2, new2, kept2 = dh.memory_remember(mem, [(12, 10), (12, 10)], [a_, b_], 105.0)
    assert new2 == [] and kept2 == [(12, 10)]  # seen again (twice in one look: once)
    assert mem2[(12, 10)].t == 105.0  # its LAST sighting
    assert mem2[(12, 10)].plan == frozenset(dh.kill_cells((10, 10)) | dh.kill_cells((13, 10)))
    assert mem[(12, 10)].t == 101.0  # pure: the old memory is untouched


def test_a_remembered_cell_expires_keep_s_after_its_last_sighting_or_at_an_escape() -> None:
    m = dh.Remembered(100.0, frozenset({(10, 10)}))
    mem = {(10, 10): m}
    assert dh.memory_expire(mem, 100.0 + dh.MEMORY_KEEP_S - 0.01, -1e9) == (mem, [], [])
    assert dh.memory_expire(mem, 100.0 + dh.MEMORY_KEEP_S, -1e9) == ({}, [(10, 10)], [])
    assert dh.memory_expire(mem, 101.0, 100.5) == ({}, [], [(10, 10)])  # seen before a Fly Wing
    assert dh.memory_expire(mem, 101.0, 99.0) == (mem, [], [])  # an escape BEFORE it: kept
    now_ = 103.0  # (1, 1) seen one second past the keep, (2, 2) four seconds ago
    two = {(1, 1): dh.Remembered(now_ - dh.MEMORY_KEEP_S - 1.0, frozenset()),
           (2, 2): dh.Remembered(now_ - 4.0, frozenset())}  # fmt: skip
    keep, old, esc = dh.memory_expire(two, now_, -1e9)
    assert list(keep) == [(2, 2)] and old == [(1, 1)] and esc == []  # each on its own clock


def test_the_merge_puts_the_remembered_cells_after_the_steps_own_in_items_plan_order() -> None:
    k_far, k_near = (30, 30), (14, 10)
    mem = {(31, 30): dh.Remembered(100.0, frozenset(dh.kill_cells(k_far))),
           (15, 10): dh.Remembered(101.0, frozenset(dh.kill_cells(k_near)))}  # fmt: skip
    own = [(11, 10), (12, 10)]
    order, rem = dh.memory_merge(own, mem, (10, 10))
    assert rem == [(15, 10), (31, 30)]  # nearest her first
    assert order[:2] == own  # the step's own items first, unchanged
    near = dh.items_plan([(15, 10)], dh.kill_cells(k_near))
    far = dh.items_plan([(31, 30)], dh.kill_cells(k_far))
    assert order[2:] == [c for c in near + far if c not in own]  # each over its OWN kills' cells
    assert len(order) == len(set(order))  # one cell once
    # the step saw nothing itself: the remembered cells alone (never "no_items")
    alone, _ = dh.memory_merge([], mem, (10, 10))
    assert alone == near + far and alone[0] == (15, 10)
    # a remembered cell that is also one of the step's own: hovered once, in its own place
    dup, _ = dh.memory_merge([(15, 10)], mem, (10, 10))
    assert dup.count((15, 10)) == 1 and dup[0] == (15, 10)
    assert dh.memory_merge(own, {}, (10, 10)) == (own, [])


def test_the_cells_a_loot_visited_are_cleared_the_rest_stay() -> None:
    mem = {(1, 1): dh.Remembered(1.0, frozenset()), (5, 5): dh.Remembered(2.0, frozenset())}
    assert dh.memory_clear(mem, {(1, 1), (2, 2)}) == {(5, 5): mem[(5, 5)]}  # (2, 2): a neighbour
    assert dh.memory_clear(mem, [(1, 1), (5, 5)]) == {}
    assert dh.memory_clear(mem, set()) == mem
    assert set(mem) == {(1, 1), (5, 5)}  # pure


def test_a_whole_cycle_look_remember_merge_clear() -> None:
    """A kill at t 100 with nothing to see at the loot step (+2 s); a look in the next fight (+4 s)
    boxes its drop; the next loot step (+15 s) hovers it after its own and clears it."""
    kill = _k((20, 20), 100.0)
    mem, new, _ = dh.memory_remember({}, [(21, 20)], [kill], 104.0)
    assert new == [(21, 20)]
    mem, old, esc = dh.memory_expire(mem, 115.0, -1e9)
    assert (21, 20) in mem and old == esc == []  # 11 s after its sighting: kept
    order, rem = dh.memory_merge([(30, 30)], mem, (28, 28))
    assert rem == [(21, 20)] and order[0] == (30, 30) and (21, 20) in order
    assert dh.memory_clear(mem, set(order)) == {}


# --- the flag, its refusal and its record ---------------------------------------------------------


def test_the_fixes_record_is_written_only_when_on() -> None:
    on = dh.fixes_of(dh.argparse.Namespace(**BASE, loot_items="xmas02fi5", loot_memory=True))
    assert on["loot_memory"] == [7.0, 1.0, 30.0, "9.37"]
    assert "loot_recheck" not in on  # independent of --loot-recheck
    off = dh.fixes_of(dh.argparse.Namespace(**BASE, loot_items="xmas02fi5", loot_memory=False))
    assert "loot_memory" not in off
    assert "loot_memory" not in dh.fixes_of(dh.argparse.Namespace(**BASE))


def test_the_refusal_without_loot_items() -> None:
    assert dh.loot_memory_refused(True, None) == "--loot-memory goes with --loot-items"
    assert dh.loot_memory_refused(True, "") is not None
    assert dh.loot_memory_refused(True, "xmas02fi5") is None
    assert dh.loot_memory_refused(False, None) is None


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


def test_the_flag_is_off_by_default(monkeypatch: Any) -> None:
    assert _ns(monkeypatch).loot_memory is False
    assert _ns(monkeypatch, "--loot-memory").loot_memory is True
    assert _ns(monkeypatch, "--loot-memory", "--no-loot-memory").loot_memory is False
    both = _ns(monkeypatch, "--loot-memory")
    assert both.loot_recheck is False  # p96 / p97: --loot-memory without --loot-recheck


def test_run_refuses_it_without_loot_items_before_any_session(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--loot", "trim", "--loot-memory")
    monkeypatch.undo()

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert str(exc.value) == "dungeon@9.37 refused: --loot-memory goes with --loot-items"
    run_src = _nested("run")
    i_ref = run_src.index('raise SystemExit(f"dungeon@{LOOT_MEMORY_VERSION} refused: {why_lm}")')
    assert i_ref < run_src.index("with r.session(")


# --- the wiring (source scans) --------------------------------------------------------------------


def test_the_look_never_sleeps_clicks_or_hovers() -> None:
    """It only LOOKS: no sleep, no hover, no click, no key in the look or its bookkeeping; the calm
    path's only waits are recheck_visit's own (9.36's pickup walk), never one of its own."""
    for name in ("memory_look", "memory_prune", "memory_kill", "memory_tick"):
        body = _nested(name)
        assert "sleep(" not in body, name
    look = _nested("memory_look")
    for act in ("hover(", "click_at(", "strike(", "press(", "agent.", "recheck_visit("):
        assert act not in look, act
    hook = SRC[SRC.index("                if lm_on:\n                    memory_prune(tick)\n") :]
    hook = hook[: hook.index("                if hud_tx is not None")]
    assert "sleep(" not in hook and hook.count("memory_look(tick)") == 1


def test_the_look_runs_in_any_mode_but_sitting_before_the_fight_branch() -> None:
    hook = ("                if lm_on:\n"
            "                    memory_prune(tick)\n"
            "                    if lm_kills and not sitting:\n"
            "                        memory_look(tick)\n")  # fmt: skip
    assert SRC.count(hook) == 1
    i_hook = SRC.index(hook)
    i_prune_936 = SRC.index("                    recheck_prune(tick)\n")
    i_fight = SRC.index("                # --- FIGHT: locked, or scan for the attacker")
    i_fight_if = SRC.index('                if mode == "fight":\n', i_fight)
    assert i_prune_936 < i_hook < i_fight < i_fight_if  # before the fight branch: fights looked at
    i_loop = SRC.index("            while time.monotonic() < t_end:")
    assert i_loop < i_hook
    # no mode test guards it (search, fight, after, a walk to rest): only sitting stops it -- the
    # hook is a statement of the loop's own body, its one inner test `lm_kills and not sitting`
    run_node = _fn("run")
    loop = next(n for n in ast.walk(run_node) if isinstance(n, ast.While)
                and "t_end" in _src(n.test))  # fmt: skip
    outer = [n for n in loop.body if isinstance(n, ast.If) and _src(n.test) == "lm_on"
             and "memory_look(tick)" in _src(n)]  # fmt: skip
    assert len(outer) == 1
    inner = [n for n in outer[0].body if isinstance(n, ast.If)]
    assert [_src(n.test) for n in inner] == ["lm_kills and not sitting"]
    assert "mode" not in hook
    look = _nested("memory_look")
    assert "mode ==" not in look and "mode !=" not in look and "mode in" not in look
    assert 'memory_look_due(tick_, lm_st["last"], lm_kills, sitting)' in look
    assert "not sitting" in _nested("memory_look_due")


def test_the_look_is_one_detection_on_a_fresh_frame_over_the_wide_grid() -> None:
    look = _nested("memory_look")
    assert look.count("item_det.detect(frame())") == 1
    i_due = look.index("if not memory_look_due(")
    i_clock = look.index('lm_st["last"] = t_l')
    i_det = look.index("item_det.detect(frame())")
    assert i_due < i_clock < i_det  # due BEFORE the model is asked
    assert "item_rels_on(item_det.detect(frame()), project(h_, RECHECK_GRID)," in look
    assert "memory_remember(lm_mem, seen_m, lm_kills, t_l, loot_fits)" in look
    # its event only when a cell is NEWLY remembered, never on every look
    i_new = look.index("if new_:")
    assert look.index('"kind": "memory_look"') > i_new and look.count('"kind": "memory_look"') == 1
    for key in ('"seen":', '"kept":', '"new":'):
        assert key in look, key
    assert 'counts["memory_looks"] += 1' in look and 'counts["memory_fail"] += 1' in look


def test_the_kills_are_registered_at_both_kill_sites_behind_the_flag() -> None:
    reg = "memory_kill(here, tick)"
    assert SRC.count(reg) == 2
    i_exp = SRC.index('ev({"kind": "kill", "by": "exp_line"')
    i_gap = SRC.index('ev({"kind": "kill", "by": "hit_gap"')
    i_1, i_2 = SRC.index(reg), SRC.index(reg, SRC.index(reg) + 1)
    assert i_exp < i_1 < i_gap < i_2
    for i_ in (i_1, i_2):
        assert "if lm_on:" in SRC[i_ - 100 : i_]
        assert "loot_list.append((here, tick))" in SRC[i_ - 700 : i_]  # where the loot list grows
    assert "lm_kills.append(PendingKill(cell_k, t_k))" in _nested("memory_kill")
    prune = _nested("memory_prune")
    assert "recheck_split(lm_kills, tick_, esc_t, MEMORY_S)" in prune  # pruned at MEMORY_S
    assert "memory_expire(lm_mem, tick_, esc_t)" in prune
    assert '"kind": "memory_expired", "cells": len(cells_)' in prune
    # the escapes are 9.36's own
    assert "max(fly_at, house_click_t, max(boss_walks, default=-1e9)," in prune


def test_the_loot_step_is_9_36s_plus_two_marked_blocks() -> None:
    """Every line of 9.36's loot_step_v1 is still there, in its order: with the two `if lm_on`
    blocks (and their comment lines) taken out, the function is byte for byte 9.36's."""
    node = _fn("loot_step_v1")
    drop: set[int] = set()
    ifs = [n for n in ast.walk(node) if isinstance(n, ast.If) and _src(n.test).startswith("lm_on")]
    assert len(ifs) == 2
    for n in ifs:
        drop |= set(range(n.lineno, (n.end_lineno or n.lineno) + 1))
        above, j = [], n.lineno - 1  # its comment lines, right above it (line numbers from 1)
        while LINES[j - 1].strip().startswith("#"):
            above.append(j)
            j -= 1
        assert above and "dungeon@9.37" in LINES[above[-1] - 1]  # marked as 9.37's
        drop |= set(above)
    kept = [LINES[i - 1] for i in range(node.lineno, (node.end_lineno or 0) + 1) if i not in drop]
    assert hashlib.sha256("\n".join(kept).encode()).hexdigest() == V1_936_SHA256
    v1 = _nested("loot_step_v1")
    assert "rk_" not in v1 and "recheck" not in v1  # 9.36's pin: no recheck hook inside it
    # the merge sits after 9.33's own plan and before its "no_items" return
    i_own = v1.index("order_items = items_plan(seen_items, plan)")
    i_items = v1.index('out_["items"] = {"seen": [list(c_) for c_ in seen_items],')
    i_merge = v1.index("order_items, lm_rem = memory_merge(order_items, lm_mem, here)")
    i_none = v1.index("if not order_items:  # nothing near the kills: no hover at all")
    assert i_own < i_items < i_merge < i_none
    assert 'out_["items"]["remembered"] = [list(c_) for c_ in lm_rem]' in v1
    assert 'out_["items"]["hover"] = [list(c_) for c_ in order_items]' in v1[i_merge:i_none]
    # the clear: after the hovers, before the step's own event
    i_clear = v1.index("kept_lm = memory_clear(lm_mem, hovered)")
    i_loop = v1.index('got = visit(todo[0], "list")')
    i_ev = v1.index('ev({**out_, "hovered": len(hovered), "hovers": n_hov,')
    assert i_loop < i_clear < i_ev
    assert v1.count("item_det.detect(frame())") == 1  # still ONE detection a loot step


def test_the_calm_path_is_9_36s_after_the_fight_branch_before_the_after_block() -> None:
    i_fight = SRC.index("                if mode == \"fight\" or (lock is not None):\n"
                        "                    continue\n")  # fmt: skip
    i_rk = SRC.index("if rk_on and rk_pending and recheck_tick(tick, calm):")
    i_hook = SRC.index("if lm_on and lm_mem and memory_tick(tick, calm):")
    i_after = SRC.index("                # --- AFTER a fight: loot, then rest or search")
    assert i_fight < i_rk < i_hook < i_after
    tick_ = _nested("memory_tick")
    assert "item_det" not in tick_  # no detection: the hover itself checks the cell
    i_calm = tick_.index("if not recheck_calm(mode, lock is not None, calm_, tick_ - last_taken,")
    i_visit = tick_.index("got_m = recheck_visit(todo_[0], rs)")
    assert i_calm < i_visit and tick_.count("recheck_visit(") == 1
    assert "hover(" not in tick_.replace("recheck_visit(", "")
    for cap in ("LOOT_MAX_PICKS", "LOOT_MAX_HOVERS", "LOOT_TRIM_HOVERS", "LOOT_MAX_S",
                "time.monotonic() - last_taken < 1.0"):  # fmt: skip
        assert cap in tick_, cap
    assert "memory_merge([], lm_mem, h_)" in tick_
    assert 'kept_m = memory_clear(lm_mem, rs["hovered"])' in tick_
    assert '"kind": "memory_loot"' in tick_
    # the loot step's detection restarts the look clock (as 9.36's)
    i_loot = SRC.index("got_ = loot_step(loot_list, fight_ref)")
    i_clock = SRC.index('lm_st["last"] = time.monotonic()  # next look waits its 1 s')
    i_settle = SRC.index('if getattr(a, "kill_gap", False) and counts["loot_click"] > clicks0_:')
    assert i_loot < i_clock < i_settle


def test_the_flag_off_changes_nothing() -> None:
    """Every use of the memory's state and closures in the main loop, at the run's end and inside
    the loot step sits under an ``if lm_on ...`` test (False unless the flag): the default run is
    today's."""
    run_node = _fn("run")
    parent = _parents(run_node)
    loop = next(n for n in ast.walk(run_node) if isinstance(n, ast.While)
                and "t_end" in _src(n.test))  # fmt: skip
    in_loop = 0
    for n in ast.walk(run_node):
        if not (isinstance(n, ast.Name) and n.id in MEMORY_NAMES):
            continue
        chain = _chain(n, parent, run_node)
        if not any(c is loop for c in chain) and not any(isinstance(c, ast.Try) for c in chain):
            continue  # the definitions and closures before the loop
        if any(isinstance(c, ast.FunctionDef) for c in chain):
            continue  # the closures (loot_step_v1's are checked below)
        assert _lm_guarded(chain), _src(chain[0])
        in_loop += 1
    assert in_loop >= 9  # the prune, the look, two kills, the calm hook, the clock, the end count
    v1 = _fn("loot_step_v1")
    p1 = _parents(v1)
    in_v1 = 0
    for n in ast.walk(v1):
        if isinstance(n, ast.Name) and n.id in MEMORY_NAMES | {"lm_on", "lm_rem", "kept_lm"}:
            if n.id == "lm_on":
                continue
            assert _lm_guarded(_chain(n, p1, v1)), _src(n)
            in_v1 += 1
    assert in_v1 >= 6
    assert 'lm_on = bool(getattr(a, "loot_memory", False))' in _nested("run")
    end = SRC[SRC.index("if lm_on:  # dungeon@9.37: cells still remembered at the end") :]
    assert end.index('counts["memory_left"] = len(lm_mem)') < end.index('ev({"kind": "run_end"')
