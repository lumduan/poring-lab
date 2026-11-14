"""dungeon_hunt.py --loot-recheck (dungeon@9.36, rogue-xmas02.md 4DA): the deferred item re-check.

4CZ: --loot-items' loot step asked the item model ~2-3 s after the kill, before ~43 % of the drops
were drawn (the settle study: seen by 2 s 25 / 53, 3 s 30, 5 s 38, 6 s 42). The loot step stays
9.33; each kill's 5 x 5 cells stay PENDING for RECHECK_S, and while one is and she is calm the main
loop asks the same model on a fresh frame at most every RECHECK_EVERY_S; an item in a pending
kill's cells is looted the loot step's seen-items way. The pure helpers are tested here, the wiring
by source scans (the runner's loop needs the live client)."""

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
TREE = ast.parse(SRC)
BASE = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": False,
        "rest": "spot", "npc_guard": False}  # fmt: skip


def _nested(name: str) -> str:
    """The source of the function ``name`` defined inside run (the runner's closures)."""
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SRC, node) or ""
    raise AssertionError(f"no function {name}")


# --- the pending set ------------------------------------------------------------------------------


def test_the_constants_are_the_pre_registered_ones() -> None:
    assert (dh.RECHECK_S, dh.RECHECK_EVERY_S, dh.RECHECK_R) == (7.0, 1.0, 2)
    assert dh.LOOT_RECHECK_VERSION == "9.36"


def test_a_pending_kill_expires_at_recheck_s_and_at_an_escape() -> None:
    k = dh.PendingKill((10, 10), 100.0)
    keep, gone = dh.recheck_split([k], 100.0 + dh.RECHECK_S - 0.01, -1e9)
    assert keep == [k] and gone == []
    keep, gone = dh.recheck_split([k], 100.0 + dh.RECHECK_S, -1e9)
    assert keep == [] and gone == [(k, "time")]
    # a Fly Wing / a walk-away after the kill: she left those cells on purpose
    keep, gone = dh.recheck_split([k], 101.0, 100.5)
    assert keep == [] and gone == [(k, "escape")]
    keep, gone = dh.recheck_split([k], 101.0, 99.0)  # an escape BEFORE the kill: still pending
    assert keep == [k] and gone == []
    old, new = dh.PendingKill((1, 1), 90.0), dh.PendingKill((2, 2), 99.0)
    keep, gone = dh.recheck_split([old, new], 98.0, -1e9)
    assert keep == [new] and gone == [(old, "time")]  # each kill on its own clock


def test_two_kills_in_one_tick_stay_two() -> None:
    a_, b_ = dh.PendingKill((5, 5), 1.0), dh.PendingKill((5, 5), 1.0)
    assert a_ != b_ and a_ in [a_] and b_ not in [a_]  # eq=False: identity, never the fields
    hits = dh.recheck_match([a_, b_], [(5, 5)])
    assert len(hits) == 2


def test_the_kill_cells_are_the_loot_steps_five_by_five() -> None:
    cells = dh.kill_cells((10, 10))
    assert len(cells) == 25 and (8, 8) in cells and (12, 12) in cells and (13, 10) not in cells
    blocked = {(10, 10), (11, 10)}
    fits = lambda c: c not in blocked  # noqa: E731 -- the loot step's walkable / zone filter
    assert dh.kill_cells((10, 10), fits) == cells - blocked


def test_a_seen_item_inside_a_pending_kills_cells_matches_outside_does_not() -> None:
    a_, b_ = dh.PendingKill((10, 10), 1.0), dh.PendingKill((30, 30), 2.0)
    assert dh.recheck_match([a_, b_], [(12, 12)]) == [a_]  # the 5 x 5's corner
    assert dh.recheck_match([a_, b_], [(13, 10)]) == []  # one cell outside it
    assert dh.recheck_match([a_, b_], [(31, 29), (9, 11)]) == [a_, b_]  # pending order
    assert dh.recheck_match([a_], [(12, 12)], lambda c: c != (12, 12)) == []  # not a plan cell
    assert dh.recheck_match([], [(10, 10)]) == []


def test_the_plan_is_the_seen_items_path_over_the_matched_kills() -> None:
    a_, b_ = dh.PendingKill((10, 10), 1.0), dh.PendingKill((30, 30), 2.0)
    hits, order = dh.recheck_plan([a_, b_], [(11, 10)])
    assert hits == [a_] and order[0] == (11, 10) and len(order) == dh.LOOT_ITEMS_HOVERS
    assert all(c in dh.kill_cells(a_.cell) for c in order)  # never outside the matched kills
    assert order == dh.items_plan([(11, 10)], dh.kill_cells(a_.cell))  # the loot step's order
    assert dh.recheck_plan([a_, b_], [(20, 20)]) == ([], [])
    # an item at the 5 x 5's edge: its neighbours outside the kill's cells are not hovered
    _, edge = dh.recheck_plan([a_], [(12, 12)])
    assert edge[0] == (12, 12) and all(max(abs(c[0] - 10), abs(c[1] - 10)) <= 2 for c in edge)


def test_the_check_is_due_every_recheck_every_s() -> None:
    assert dh.recheck_due(5.0, -1e9)  # never asked: due
    assert not dh.recheck_due(5.0 + dh.RECHECK_EVERY_S - 0.01, 5.0)
    assert dh.recheck_due(5.0 + dh.RECHECK_EVERY_S, 5.0)


def test_calm_is_hunting_with_no_lock_no_hit_and_no_boss_window() -> None:
    ok_ = {"mode": "search", "locked": False, "calm": True, "since_taken": 9.0,
           "avoiding": False}  # fmt: skip
    assert dh.recheck_calm(**ok_)
    for k, v in (("mode", "fight"), ("mode", "after"), ("mode", "rest"), ("locked", True),
                 ("calm", False), ("avoiding", True)):  # fmt: skip
        assert not dh.recheck_calm(**{**ok_, k: v}), (k, v)
    assert not dh.recheck_calm(**{**ok_, "since_taken": dh.FIGHT_TAKEN_S})  # within it: no
    assert dh.recheck_calm(**{**ok_, "since_taken": dh.FIGHT_TAKEN_S + 0.01})
    assert dh.FIGHT_TAKEN_S > dh.CALM_S  # the runner's calm alone would allow a hit 2.0-2.5 s ago


def test_a_fight_or_a_hit_yields_everything_else_is_done() -> None:
    assert dh.recheck_outcome("fight", 0, 1) == ("fight", False)
    assert dh.recheck_outcome("hit", 0, 0) == ("hit", False)
    assert dh.recheck_outcome("done", 1, 2) == ("looted", True)
    assert dh.recheck_outcome("done", 0, 2) == ("empty", True)
    assert dh.recheck_outcome("done", 0, 0) == ("off", True)
    assert dh.recheck_outcome("escape", 0, 1) == ("escape", True)


# --- the flag, its refusal and its record ---------------------------------------------------------


def test_the_fixes_record_is_written_only_when_on() -> None:
    on = dh.fixes_of(dh.argparse.Namespace(**BASE, loot_items="xmas02fi5", loot_recheck=True))
    assert on["loot_recheck"] == [7.0, 1.0, "9.36"]
    off = dh.fixes_of(dh.argparse.Namespace(**BASE, loot_items="xmas02fi5", loot_recheck=False))
    assert "loot_recheck" not in off
    assert "loot_recheck" not in dh.fixes_of(dh.argparse.Namespace(**BASE))


def test_the_refusal_without_loot_items() -> None:
    assert dh.loot_recheck_refused(True, None) == "--loot-recheck goes with --loot-items"
    assert dh.loot_recheck_refused(True, "") is not None
    assert dh.loot_recheck_refused(True, "xmas02fi5") is None
    assert dh.loot_recheck_refused(False, None) is None


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
    assert _ns(monkeypatch).loot_recheck is False
    assert _ns(monkeypatch, "--loot-recheck").loot_recheck is True
    assert _ns(monkeypatch, "--loot-recheck", "--no-loot-recheck").loot_recheck is False


def test_run_refuses_it_without_loot_items_before_any_session(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--loot", "trim", "--loot-recheck")
    monkeypatch.undo()

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert str(exc.value) == "dungeon@9.36 refused: --loot-recheck goes with --loot-items"
    run_src = _nested("run")
    i_ref = run_src.index('raise SystemExit(f"dungeon@{LOOT_RECHECK_VERSION} refused: {why_rk}")')
    assert i_ref < run_src.index("with r.session(")


# --- the wiring (source scans) --------------------------------------------------------------------


def test_the_recheck_never_sleeps_in_the_loop() -> None:
    """Not due -> no check, never a wait: no sleep in the recheck's own code or its hooks; the
    only sleep is recheck_visit's pickup walk, the loot step's visit() line itself."""
    for name in ("recheck_tick", "recheck_prune", "loot_fits"):
        assert "sleep(" not in _nested(name), name
    visit_r = _nested("recheck_visit")
    assert visit_r.count("sleep(") == 1
    assert "time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup" in visit_r
    v1 = _nested("loot_step_v1")
    assert "time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup" in v1  # the same line
    for hook in (
        "if rk_on and rk_pending:  # dungeon@9.36: the pending kills age out every tick\n"
        "                    recheck_prune(tick)\n",
        "if rk_on and rk_pending and recheck_tick(tick, calm):\n"
        "                    continue  # it hovered (or a fight began): a fresh tick reads the "
        "signs first\n",
        "if rk_on:  # dungeon@9.36: the loot step just asked the item model (with a\n"
        '                        rk_st["last"] = time.monotonic()  # position): the recheck '
        "waits its 1 s\n",
    ):
        assert SRC.count(hook) == 1, hook
        assert "sleep(" not in hook


def test_recheck_visit_is_the_loot_steps_visit_step_for_step() -> None:
    v1 = _nested("loot_step_v1")
    visit = v1[v1.index("            def visit(c: Cell, why: str) -> str:") :]
    visit = visit[: visit.index("\n            seen_items")]
    visit_r = _nested("recheck_visit")
    steps = ("rel = (c[0] - hs.here[0], c[1] - hs.here[1])", "u, v = project(hs.here, [rel])[0]",
             "if not in_view(u, v):", 'return "off"', "if guard_tick():", 'return "escape"',
             '== "sword":', 'strike(u, v - BODY_UP, rel, "loot_sword")',
             'hs.lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}', 'hs.mode = "fight"',
             'if pickup_seen(res', "d_ = max(abs(rel[0]), abs(rel[1]))", 'click_at(u, v, "loot")',
             'counts["loot_click"] += 1', "time.sleep(0.45 + 0.2 * d_)",
             "hs.here = read_here() or c", 'return "ok"')  # fmt: skip
    for body in (visit, visit_r):
        at = [body.index(s) for s in steps]
        assert at == sorted(at), body[:80]  # every step, in the loot step's order
    assert "hover(u, v)" in visit_r and visit_r.count("click_at(") == 1
    assert '"why": "recheck"' in visit_r  # its loot clicks say where they came from


def test_the_loot_step_is_unchanged_and_the_kills_are_registered_at_both_kill_sites() -> None:
    v1 = SRC[SRC.index("        def loot_step_v1(") : SRC.index("        def tadv(")]
    assert "rk_" not in v1 and "recheck" not in v1  # 9.33's loot step: no hook inside it
    assert SRC.count("kill_aim_set(tick)") == 2  # 9.32's pin: unchanged
    reg = "rk_pending.append(PendingKill(hs.here, tick))"
    assert SRC.count(reg) == 2
    i_exp = SRC.index('ev({"kind": "kill", "by": "exp_line"')
    i_gap = SRC.index('ev({"kind": "kill", "by": "hit_gap"')
    i_1, i_2 = SRC.index(reg), SRC.index(reg, SRC.index(reg) + 1)
    assert i_exp < i_1 < i_gap < i_2  # the exp-line kill, then the hit-gap kill
    for i_ in (i_1, i_2):
        assert "if rk_on:" in SRC[i_ - 120 : i_]  # behind the flag
    # the scan's pickup is not a kill: no pending entry there
    i_hand = SRC.index("hs.loot_list.append((hs.here, time.monotonic()))")
    assert reg not in SRC[i_hand - 400 : i_hand + 200]


def test_the_hook_runs_after_the_fight_branch_before_the_after_block() -> None:
    i_fight = SRC.index("                if hs.mode == \"fight\" or (hs.lock is not None):\n"
                        "                    continue\n")  # fmt: skip
    i_hook = SRC.index("if rk_on and rk_pending and recheck_tick(tick, calm):")
    i_after = SRC.index("                # --- AFTER a fight: loot, then rest or search")
    i_loot = SRC.index("got_ = loot_step(hs.loot_list, hs.fight_ref)")
    i_last = SRC.index('rk_st["last"] = time.monotonic()')
    assert i_fight < i_hook < i_after < i_loot < i_last
    assert SRC.index('if getattr(a, "kill_gap", False) and counts["loot_click"] > clicks0_:') \
        > i_last  # fmt: skip
    i_prune = SRC.index("                    recheck_prune(tick)\n")
    assert i_prune < SRC.index("# --- FIGHT: locked, or scan for the attacker") < i_hook
    tick_ = _nested("recheck_tick")
    assert tick_.count("item_det.detect(frame())") == 1  # ONE detection, on a fresh frame
    i_calm = tick_.index("if not recheck_calm(")
    i_due = tick_.index("if not recheck_due(")
    i_det = tick_.index("item_det.detect(frame())")
    assert i_calm < i_due < i_det  # calm and due BEFORE the model is asked
    assert "recheck_visit(" in tick_ and "hover(" not in tick_.replace("recheck_visit(", "")
    for cap in (
        "LOOT_MAX_PICKS",
        "LOOT_MAX_HOVERS",
        "LOOT_TRIM_HOVERS",
        "LOOT_MAX_S",
        "time.monotonic() - hs.last_taken < 1.0",
    ):  # the loot step's own bounds
        assert cap in tick_, cap
    for kind in ('"kind": "recheck"', '"kill_age_s"', '"seen"', '"looted"', '"picks"', '"end"'):
        assert kind in tick_, kind
    assert '"kind": "recheck_expired", "kill_age_s"' in _nested("recheck_prune")


def test_the_flag_off_changes_nothing() -> None:
    """Every use of the recheck's state in the main loop (and at the run's end) sits under an
    ``if rk_on ...`` test (False unless the flag): the default run is today's."""
    run_node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(run_node):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    loop = next(n for n in ast.walk(run_node) if isinstance(n, ast.While)
                and "t_end" in (ast.get_source_segment(SRC, n.test) or ""))  # fmt: skip
    names = {"rk_pending", "rk_st", "recheck_tick", "recheck_prune", "PendingKill"}
    uses = [n for n in ast.walk(run_node) if isinstance(n, ast.Name) and n.id in names]
    in_loop = 0
    for n in uses:
        chain, p = [], parent.get(n)
        while p is not None and p is not run_node:
            chain.append(p)
            p = parent.get(p)
        if not any(isinstance(c, ast.While) and c is loop for c in chain) and not any(
                isinstance(c, ast.Try) for c in chain):  # fmt: skip
            continue  # the definitions and closures before the loop
        if any(isinstance(c, ast.FunctionDef) for c in chain):
            continue
        guard = [c for c in chain if isinstance(c, ast.If)
                 and (ast.get_source_segment(SRC, c.test) or "").startswith("rk_on")]  # fmt: skip
        assert guard, ast.get_source_segment(SRC, chain[0])
        in_loop += 1
    assert in_loop >= 6  # the prune, the hook, the loot step's clock, two kills, the end count
    assert 'rk_on = bool(getattr(a, "loot_recheck", False))' in _nested("run")


def test_the_recheck_maps_items_on_its_wider_grid() -> None:
    """4DA amendment (before p94 / p95): +-8 cells; item_rels_on == item_rels on ITEM_GRID."""
    assert len(dh.RECHECK_GRID) == 17 * 17 and (8, -8) in dh.RECHECK_GRID
    assert set(dh.ITEM_GRID) <= set(dh.RECHECK_GRID)

    class B:
        cls, species, score = dh.LOOT_ITEMS_CLASS, None, 0.9

        def __init__(self, x: float, y: float) -> None:
            self.x0, self.y0, self.x1, self.y1 = x - 5, y - 5, x + 5, y + 5

    uv = [(100.0 * dx, 100.0 * dy) for dx, dy in dh.RECHECK_GRID]
    far = B(700.0, 0.0)  # (7, 0): outside ITEM_GRID, inside RECHECK_GRID
    assert dh.item_rels_on([far], uv, dh.RECHECK_GRID) == [(7, 0)]
    near_uv = [(100.0 * dx, 100.0 * dy) for dx, dy in dh.ITEM_GRID]
    assert dh.item_rels_on([B(200.0, 100.0)], near_uv, dh.ITEM_GRID) == dh.item_rels(
        [B(200.0, 100.0)], near_uv
    )
    src = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
    assert "project(h_, RECHECK_GRID)" in src
