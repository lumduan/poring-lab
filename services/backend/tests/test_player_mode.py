"""dungeon_hunt.py --player-mode (dungeon@9.35, docs/planning/player-mode.md; Batt 2026-11-12):
the hunt as a normal player on a public rAthena that permits bots (ADR-0023's declared mode). The
run types NO line -- every line the runner types goes through ONE guard (typed_line) -- reads
nothing from the lab's DB, starts where the person left the character, with her own stock, and
ends by its own Fly Wing escape only."""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
TREE = ast.parse(SRC)
BASE = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
        "rest": "spot", "npc_guard": True, "miss_cue": False}  # fmt: skip


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    out: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


PARENT = _parents(TREE)


def _func(name: str) -> ast.FunctionDef:
    (f,) = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return f


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _flag_calls(flag: str) -> list[ast.Call]:
    return [n for n in ast.walk(TREE) if isinstance(n, ast.Call)
            and _call_name(n) == "add_argument" and n.args
            and isinstance(n.args[0], ast.Constant) and n.args[0].value == flag]  # fmt: skip


def _enclosing_def(node: ast.AST) -> str:
    while node in PARENT:
        node = PARENT[node]
        if isinstance(node, ast.FunctionDef):
            return node.name
    return "<module>"


def _is_player(e: ast.expr) -> bool:
    return isinstance(e, ast.Name) and e.id == "player"


def _is_not_player(e: ast.expr) -> bool:
    return isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.Not) and _is_player(e.operand)


def _player_never_runs(node: ast.AST) -> bool:
    """True when ``node`` sits in a branch --player-mode never takes: the body of `if not player`
    (or `if X and not player`), or the else of `if player` (or `if X or player`)."""
    while node in PARENT:
        up = PARENT[node]
        if isinstance(up, ast.If):
            t = up.test
            in_body = any(node is s for s in up.body)
            in_else = any(node is s for s in up.orelse)
            off = _is_not_player(t) or (isinstance(t, ast.BoolOp) and isinstance(t.op, ast.And)
                                        and any(_is_not_player(v) for v in t.values))  # fmt: skip
            on = _is_player(t) or (isinstance(t, ast.BoolOp) and isinstance(t.op, ast.Or)
                                   and any(_is_player(v) for v in t.values))  # fmt: skip
            if (in_body and off) or (in_else and on):
                return True
        node = up
    return False


def _stmt_of(node: ast.AST) -> tuple[ast.stmt, list[ast.stmt]]:
    """The statement holding ``node`` and the statement list it belongs to."""
    while node in PARENT:
        up = PARENT[node]
        for field in ("body", "orelse", "finalbody", "handlers"):
            seq = getattr(up, field, None)
            if isinstance(seq, list) and any(node is s for s in seq):
                return node, seq  # type: ignore[return-value]
        node = up
    raise AssertionError("no statement")


def _emptied_before(stmt: ast.stmt, seq: list[ast.stmt]) -> bool:
    """A `for cmd in setup:` loop whose list was just passed through player_plan(setup, player)."""
    i = next(k for k, s in enumerate(seq) if s is stmt)
    for s in reversed(seq[:i]):
        call = s.value if isinstance(s, ast.Assign | ast.Expr) else None
        name = _call_name(call) if isinstance(call, ast.Call) else None
        if isinstance(s, ast.Assign) and isinstance(call, ast.Call) and name == "player_plan":
            return len(call.args) == 2 and _is_player(call.args[1])
        if isinstance(s, ast.Expr) and name == "player_chat_closed":
            continue
        return False
    return False


# --- (a) the source scan: ONE typing path ---------------------------------------------------------


def test_every_typing_call_in_the_runner_is_the_guards_own() -> None:
    """A line is typed only through typed_line: any other call of a typing API (crusader.gm_line,
    ro_agent's chat_line / gm / open_chat / say / type_line / console_*, Agent.type_text /
    type_secret) anywhere in dungeon_hunt.py fails here: a new "@" call site must use the guard."""
    hits = [(n.lineno, _call_name(n), _enclosing_def(n)) for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and _call_name(n) in dh.TYPING_CALLS]  # fmt: skip
    assert [(name, where) for _, name, where in hits] == [("gm_line", "typed_line")], hits
    # the names are the real APIs (a typo would make the scan blind)
    apis = (ROOT / "scripts" / "ro_agent.py").read_text() + (ROOT / "scripts" / "crusader.py"
                                                              ).read_text()  # fmt: skip
    for name in dh.TYPING_CALLS:
        assert f"def {name}(" in apis, name


def test_every_guard_call_names_its_mode() -> None:
    """Each typed_line call passes player_mode: run()'s pass the run's own flag (`player`), the
    lab-only clear-bag subcommand's pass False; nothing else calls it."""
    calls = [n for n in ast.walk(TREE) if isinstance(n, ast.Call) and _call_name(n) == "typed_line"]
    assert calls
    for c in calls:
        kw = {k.arg: k.value for k in c.keywords}
        assert "player_mode" in kw, c.lineno
        where = _enclosing_def(c)
        if where == "clear_bag":
            v = kw["player_mode"]
            assert isinstance(v, ast.Constant) and v.value is False, c.lineno
        else:
            assert where in ("run", "setup_line") and _is_player(kw["player_mode"]), c.lineno
    # clear-bag has no --player-mode: only the run parser carries the flag
    flags = _flag_calls("--player-mode")
    assert len(flags) == 1 and isinstance(flags[0].func, ast.Attribute)
    assert isinstance(flags[0].func.value, ast.Name) and flags[0].func.value.id == "t"


def test_no_line_is_typed_on_any_player_mode_path() -> None:
    """(c) Every place run() could type -- typed_line, setup_line, and bench.close_chat (an Enter
    that would SEND text left in an open chat input) -- sits in a branch --player-mode never takes,
    or runs a plan player_plan just emptied (with the chat input checked closed first)."""
    run_ = _func("run")
    setup_line = next(n for n in ast.walk(run_)
                      if isinstance(n, ast.FunctionDef) and n.name == "setup_line")  # fmt: skip
    seen: dict[str, int] = {}
    for n in ast.walk(run_):
        if not isinstance(n, ast.Call):
            continue
        name = _call_name(n)
        if name not in ("typed_line", "setup_line", "close_chat"):
            continue
        seen[name] = seen.get(name, 0) + 1
        if name == "typed_line" and _enclosing_def(n) == "setup_line":
            continue  # covered by every setup_line call below
        if _player_never_runs(n):
            continue
        stmt, seq = _stmt_of(n)
        if name == "setup_line":  # inside `for cmd in setup:` -- an emptied plan
            loop = PARENT[stmt]
            assert isinstance(loop, ast.For) and isinstance(loop.iter, ast.Name), n.lineno
            assert loop.iter.id == "setup", n.lineno
            loop_stmt, loop_seq = _stmt_of(loop)
            assert _emptied_before(loop_stmt, loop_seq), n.lineno
        elif name == "close_chat":  # the setup's one reached by a player: the input checked shut
            i = next(k for k, s in enumerate(seq) if s is stmt)  # right before it, past the
            j = i - 1  # (emptied) setup loop, the check itself
            while j >= 0 and isinstance(seq[j], ast.For) and ast.unparse(seq[j].iter) == "setup":
                j -= 1
            s_j = seq[j]
            assert isinstance(s_j, ast.Expr) and isinstance(s_j.value, ast.Call), n.lineno
            assert _call_name(s_j.value) == "player_chat_closed", n.lineno
        else:
            raise AssertionError(f"line {n.lineno}: a {name} call a player run can reach")
    assert seen["typed_line"] >= 4 and seen["setup_line"] >= 3 and seen["close_chat"] >= 4, seen
    assert setup_line is not None


def test_the_player_mode_steps_come_before_any_input_and_the_db_is_not_read() -> None:
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_ref = run_src.index('raise SystemExit(f"dungeon@{PLAYER_MODE_VERSION} refused: {why_pm}")')
    assert i_ref < run_src.index("with r.session(")
    i_chat = run_src.index('player_chat_closed("at the start")')
    assert i_chat < run_src.index('cl_.select_tab(agent_raw, screen, "battle")')
    # the lab DB is read only on the lab's path
    q = [n for n in ast.walk(_func("run")) if isinstance(n, ast.Call)
         and _call_name(n) in ("db_query", "sql_str")]  # fmt: skip
    assert q and all(_player_never_runs(n) for n in q)
    # the stock, the cell and the weight are read and judged before the run's start record
    i_start = run_src.index('ev({"kind": "run_start"')
    for s in ("why_pst = player_stock_refused(before, heal_items)",
              "why_pc = player_start_refused(map_, here0, okr, area)",
              "why_pw = player_weight_refused(share, overweight_red(fr1[0]))"):  # fmt: skip
        assert run_src.index(s) < i_start, s
    # the death dialog's click and @alive / @heal are the lab's; a player's is left to the person
    assert 'if reason == "death" and not player:' in run_src
    assert '"kind": "player_end"' in run_src


# --- (b) the guard --------------------------------------------------------------------------------


def test_the_guard_refuses_every_line_under_player_mode_and_passes_it_otherwise() -> None:
    assert dh.line_refused("@warp prt_fild08 268 107", False) is None
    assert dh.line_refused("@heal", False) is None
    for line in ("@warp xmas_dun02 100 207", "@heal", "@item 601 5", "  @killmonster2"):
        why = dh.line_refused(line, True)
        assert why is not None and "GM command" in why and "NOT typed" in why
        assert line.split()[0] in why
    assert "public chat" in str(dh.line_refused("hello", True))  # no chat line either
    assert dh.line_refused("", True) is not None


def test_typed_line_stops_before_any_key_under_player_mode(monkeypatch: Any) -> None:
    import ro_agent as r

    calls: list[tuple[Any, ...]] = []

    def gm_line(agent: Any, screen: Any, line: str, job: str, char: str = "crusader",
                on_refuse: str = "raise") -> dict[str, Any]:  # fmt: skip
        calls.append((agent, screen, line, job, char, on_refuse))
        return {"ok": True, "typed": True}

    fake = types.ModuleType("crusader")
    fake.gm_line = gm_line  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "crusader", fake)
    with pytest.raises(r.Stop) as exc:
        dh.typed_line("A", "S", "@warp prt_fild08 268 107", "rogue", "thief", player_mode=True)
    assert "dungeon@9.35 refused" in str(exc.value) and "@warp" in str(exc.value)
    assert calls == []  # nothing reached the typing path
    got = dh.typed_line("A", "S", "@heal", "rogue", "thief", player_mode=False, on_refuse="skip")
    assert got == {"ok": True, "typed": True}
    assert calls == [("A", "S", "@heal", "rogue", "thief", "skip")]


# --- (c) the setup plan ---------------------------------------------------------------------------


def test_the_setup_plan_of_a_player_has_no_line() -> None:
    stand = [*dh.level_lines(105, 99), "@heal", "@item 504 10", "@item 601 20"]
    maps = dh.map_setup_lines("xmas_dun02", (100, 207), True, "1002:1", (98, 205))
    for lines in (stand, maps, stand + maps, []):
        assert dh.player_plan(lines, True) == []
        assert dh.player_plan(lines, False) == lines
    assert not [x for x in dh.player_plan(stand + maps, True) if x.startswith("@")]
    assert dh.level_lines(None, 99) == []  # no DB read: no level hold
    assert dh.level_lines(105, 99) == ["@baselevelup -6"]  # the lab's unchanged


# --- (d) the refused flags ------------------------------------------------------------------------


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


def test_the_flag_is_off_by_default_and_refuses_the_gm_flags(monkeypatch: Any) -> None:
    a0 = _ns(monkeypatch)
    assert a0.player_mode is False and dh.player_mode_refused(a0) is None
    assert dh.player_mode_refused(_ns(monkeypatch, "--player-mode")) is None
    # the lab may still use every one of them without the flag
    assert dh.player_mode_refused(_ns(monkeypatch, "--clear-map", "--stage-mob", "1002")) is None
    for extra, flag in ((["--clear-map"], "--clear-map"),
                        (["--stage-mob", "1002:1"], "--stage-mob"),
                        (["--stage-mob", "1002", "--stage-at", "98,205"], "--stage-at"),
                        (["--start-cell", "100,207"], "--start-cell"),
                        (["--engage", "melee_ring"], "--engage melee_ring")):  # fmt: skip
        why = dh.player_mode_refused(_ns(monkeypatch, "--player-mode", *extra))
        assert why is not None and flag in why, (extra, why)
    both = dh.player_mode_refused(_ns(monkeypatch, "--player-mode", "--clear-map",
                                      "--start-cell", "1,2"))  # fmt: skip
    assert "--clear-map" in str(both) and "--start-cell" in str(both)
    assert {f for _, f, _ in dh.PLAYER_REFUSED} == {"--clear-map", "--stage-mob", "--stage-at",
                                                    "--start-cell"}  # fmt: skip


def test_run_refuses_them_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--player-mode", "--clear-map")
    monkeypatch.undo()  # the real run, the real argv

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert "dungeon@9.35 refused" in str(exc.value) and "--clear-map" in str(exc.value)


# --- (e) the record -------------------------------------------------------------------------------


def test_the_record_carries_player_mode_only_when_on() -> None:
    off = dh.fixes_of(dh.argparse.Namespace(**BASE))
    assert "player_mode" not in off
    assert dh.fixes_of(dh.argparse.Namespace(**BASE, player_mode=False)) == off
    on = dh.fixes_of(dh.argparse.Namespace(**BASE, player_mode=True))
    assert on["player_mode"] == [5, 5, 1, "9.35"]
    assert on["player_mode"] == [dh.PLAYER_MIN_WINGS, dh.PLAYER_MIN_HEALS, dh.PLAYER_WINGS_KEEP,
                                 dh.PLAYER_MODE_VERSION]  # fmt: skip
    assert {k: v for k, v in on.items() if k != "player_mode"} == off
    i_start = SRC.index('ev({"kind": "run_start", "strategy": a.strategy')
    assert '**({"player_mode": fixes_of(a)["player_mode"]} if player else {}),' in SRC[i_start:]


def test_the_help_states_the_minimums() -> None:
    (flag,) = _flag_calls("--player-mode")
    help_ = next(ast.literal_eval(k.value) for k in flag.keywords if k.arg == "help")
    assert f"below {dh.PLAYER_MIN_WINGS} Fly Wings / {dh.PLAYER_MIN_HEALS} heal items" in help_
    assert f">= {round(dh.WEIGHT_MAX * 100)} %%" in help_
    assert f"Fly Wings read {dh.PLAYER_WINGS_KEEP}" in help_


# --- the start: the person's stock, weight and cell -----------------------------------------------


def test_the_stock_she_brings_must_reach_the_minimums() -> None:
    fly, pot = dh.STOCK_ITEMS["fly"], dh.STOCK_ITEMS["potion"]
    assert dh.player_stock_refused({fly: 5, pot: 5}, [pot]) is None
    assert "did not read" in str(dh.player_stock_refused({fly: None, pot: 5}, [pot]))
    assert "at least 5" in str(dh.player_stock_refused({fly: 4, pot: 30}, [pot]))
    assert "at least 5" in str(dh.player_stock_refused({fly: 9, pot: 4}, [pot]))
    assert "did not read" in str(dh.player_stock_refused({fly: 9, pot: None}, [pot]))
    heal = [i for _, i in dh.HEAL_ORDER]  # --heal-candy: canes + candies + potions together
    assert dh.player_stock_refused({fly: 5, 530: 2, 529: 2, pot: 1}, heal) is None
    assert dh.player_stock_refused({fly: 5, 530: 2, 529: 2, pot: 0}, heal) is not None
    assert dh.player_stock_refused({fly: 5, 530: 9, 529: None, pot: 0}, heal) is not None
    assert dh.PLAYER_MIN_WINGS > dh.POS_FLY_MAX + dh.PLAYER_WINGS_KEEP  # + one real escape


def test_the_weight_must_read_under_the_regen_line() -> None:
    assert dh.player_weight_refused(0.30, False) is None
    assert dh.player_weight_refused(None, False) is not None
    assert dh.player_weight_refused(0.30, True) is not None  # the red (>= 50 %) line
    assert "lighten" in str(dh.player_weight_refused(dh.WEIGHT_MAX, False))


def test_she_must_stand_on_the_route_grid_in_reach_of_the_search_area() -> None:
    okr = np.zeros((40, 60), bool)
    okr[5:15, 5:30] = True  # the main part
    okr[30:35, 40:50] = True  # an island the walk cannot reach
    area = np.zeros_like(okr)
    area[8:12, 10:25] = True
    assert dh.player_start_refused("m", (6, 6), okr, area) is None  # outside the area: walks in
    assert "did not read" in str(dh.player_start_refused("m", None, okr, area))
    assert "is she on m" in str(dh.player_start_refused("m", (70, 6), okr, area))
    assert "route grid" in str(dh.player_start_refused("m", (2, 2), okr, area))
    assert "reaches" in str(dh.player_start_refused("m", (45, 32), okr, area))


def test_the_run_ends_while_one_fly_wing_is_left() -> None:
    fly, pot = dh.STOCK_ITEMS["fly"], dh.STOCK_ITEMS["potion"]
    assert dh.player_wings_low(fly, 1) and dh.player_wings_low(fly, 0)
    assert not dh.player_wings_low(fly, 2) and not dh.player_wings_low(fly, None)
    assert not dh.player_wings_low(pot, 1)
    loop = SRC[SRC.index("keep_n: int | None = None") :]
    assert loop.index("if player and player_wings_low(item_, n_):") < loop.index(
        'reason = f"stock_keep: {keep_n} Fly Wing(s) left, kept for the end"'
    )


# --- dungeon@9.35b: the boss-map warning (Batt 2026-11-12: "a warning only") ----------------------


def test_the_boss_warning_names_the_kb_bosses_when_the_guard_is_off() -> None:
    line = dh.player_boss_warning("m_x", ("Made Boss", "Made Boss Table"), False)
    assert line is not None and line.startswith("WARNING: --player-mode on m_x")
    assert "Made Boss, Made Boss Table" in line and "--engage-screen / --garm-fly" in line
    assert line.endswith("the run goes on") and "\n" not in line  # one plain line
    assert dh.player_boss_warning("m_x", ("Made Boss",), True) is None  # the guard is on
    assert dh.player_boss_warning("m_x", (), False) is None  # no boss spawn: nothing to say
    unknown = dh.player_boss_warning("m_x", None, False)  # the KB did not read
    assert unknown is not None and "unknown" in unknown and unknown.startswith("WARNING")
    assert dh.player_boss_warning("m_x", None, True) is None


def test_the_boss_spawns_come_from_the_kb_as_the_boss_walk_names_them(tmp_path: Path) -> None:
    import json

    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "spawns.json").write_text(json.dumps({"m_x": [
        {"id": 9001, "name": "Made Boss", "boss": True},
        {"id": 9002, "name": "Made Minion"},
    ], "m_y": [{"id": 9002, "name": "Made Minion"}]}))  # fmt: skip
    (kb / "mobs.json").write_text(json.dumps({"9001": {"name": "Made Boss Table"}}))
    assert dh.player_boss_spawns("m_x", kb) == ("Made Boss", "Made Boss Table")
    assert dh.player_boss_spawns("m_y", kb) == ()  # no boss spawn on that map
    assert dh.player_boss_spawns("m_x", tmp_path / "none") is None  # no KB: unknown, no refusal
    (kb / "mobs.json").write_text("{not json")
    assert dh.player_boss_spawns("m_x", kb) is None


def test_the_boss_warning_is_printed_before_any_input_and_never_refuses() -> None:
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_blk = run_src.index("pb_rec: dict[str, Any] | None = None")
    i_end = run_src.index("counts: Counter[str] = Counter()", i_blk)
    blk = run_src[i_blk:i_end]
    assert i_end < run_src.index("with r.session(")  # printed before any input
    assert "    if player:\n" in blk and "print(pb_line, flush=True)" in blk
    assert "raise" not in blk and "SystemExit" not in blk and "Stop" not in blk  # a warning only
    guard = 'bool(getattr(a, "engage_screen", False) or getattr(a, "garm_fly", False))'
    assert guard in blk
    # the event goes into the run's record right after its start record
    i_start = run_src.index('ev({"kind": "run_start"')
    i_ev = run_src.index("        if pb_rec is not None:  # dungeon@9.35b")
    assert i_start < i_ev and run_src.index("ev(pb_rec)") > i_ev
    assert '"kind": "player_boss_warning"' in blk and '"guard": pb_guard' in blk
