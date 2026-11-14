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
    assert 'if hs.reason == "death" and not player:' in run_src
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
    # dungeon@9.47: + player_slots (test_slot_items.py checks it)
    assert {k: v for k, v in on.items()
            if k not in ("player_mode", "player_map", "player_slots")} == off  # fmt: skip
    i_start = SRC.index('ev({"kind": "run_start", "strategy": a.strategy')
    assert '**({"player_mode": fixes_of(a)["player_mode"]} if player else {}),' in SRC[i_start:]
    # dungeon@9.46: the map read's rule, and the read itself in run_start
    import minimap_id as mi

    assert on["player_map"] == [mi.MATCH_MIN, mi.NAME_MIN, mi.MARGIN_MIN, dh.PLAYER_MAP_S,
                                dh.PLAYER_MAP_UNREAD, "9.46"]  # fmt: skip
    assert '"player_map": None if map_read is None else map_read.record()' in SRC[i_start:]


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
    loop = SRC[SRC.index("keep_n = None") :]
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
    i_end = run_src.index("counts = hs.counts = Counter()", i_blk)
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


# --- dungeon@9.35b: the Butterfly Wing home at the end (Batt 2026-11-12) -------------------------


def test_each_character_has_a_home_key_that_no_other_key_takes() -> None:
    import bare_steal as bs

    assert dh.HOME_KEY == "F8" and dh.PLAYER_HOME_ITEM == 602
    for char, conf in dh.CHARS_CONF.items():
        assert conf["home_key"] == dh.HOME_KEY, char
        assert "home" not in conf["keys"], char  # the lab's own keys are unchanged
        assert dh.HOME_KEY not in conf["keys"].values(), char
    assert dh.HOME_KEY not in dh.HEAL_CANDY_KEYS.values() and dh.HOME_KEY != bs.EQUIP_KEY
    assert dh.hotbar_slot(dh.HOME_KEY) == 7


def test_the_home_key_is_checked_before_any_input() -> None:
    rogue = dh.CHARS_CONF["rogue"]
    keys = rogue["keys"]
    ns = dh.argparse.Namespace

    assert dh.player_home_refused(ns(player_mode=False), rogue, keys, None) is None
    assert "goes with --player-mode" in str(
        dh.player_home_refused(ns(player_mode=False, player_home_key="F9"), rogue, keys, None)
    )
    assert dh.player_home_refused(ns(player_mode=True), rogue, keys, None) is None
    assert dh.player_home_refused(ns(player_mode=True, player_home_key="F9"), rogue, keys,
                                  None) is None  # fmt: skip
    why = dh.player_home_refused(ns(player_mode=True, player_home_key="F2"), rogue, keys, None)
    assert why is not None and "fly" in why  # the Fly Wing's key
    candy = {**keys, **dh.HEAL_CANDY_KEYS}
    assert "cane" in str(dh.player_home_refused(ns(player_mode=True, player_home_key="F6"),
                                                rogue, candy, None))  # fmt: skip
    assert "--steal-opener" in str(dh.player_home_refused(ns(player_mode=True), rogue, keys, "F8"))
    for bad in ("Insert", "F10", "8"):
        assert "row-1" in str(dh.player_home_refused(ns(player_mode=True, player_home_key=bad),
                                                     rogue, keys, None))  # fmt: skip
    assert dh.player_home_refused(ns(player_mode=True), {"keys": keys}, keys, None) is None  # none
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_hk = run_src.index("why_hk = player_home_refused(a, conf, keys_, opener_key)")
    assert run_src.index("keys_ = {**keys_, **HEAL_CANDY_KEYS}") < i_hk  # the candies' keys too
    assert i_hk < run_src.index("with r.session(")
    i_join = run_src.index('keys_ = {**keys_, "home": home_key}')
    blk = run_src[run_src.rindex("    if player:\n", 0, i_join) : i_join]
    assert "home_key = " in blk  # the home key joins the run's keys under --player-mode only


def test_run_refuses_a_home_key_without_player_mode_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--player-home-key", "F9")
    assert a.player_home_key == "F9" and _ns(monkeypatch).player_home_key is None
    monkeypatch.undo()

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert "dungeon@9.35b refused" in str(exc.value) and "--player-mode" in str(exc.value)


def test_the_end_skips_without_a_key_dead_or_on_a_hard_bar() -> None:
    assert dh.player_home_skip("time_box", "F8") is None
    assert dh.player_home_skip("stock_keep: 1 Fly Wing(s) left, kept for the end", "F8") is None
    assert "no Butterfly Wing key" in str(dh.player_home_skip("time_box", None))
    assert "dead" in str(dh.player_home_skip("death", "F8"))
    assert "hard bar" in str(dh.player_home_skip("hard_bar: position jump (map change?)", "F8"))
    assert dh.player_home_count_why(1) is None and dh.player_home_count_why(7) is None
    assert "did not read" in str(dh.player_home_count_why(None))
    assert "count 0" in str(dh.player_home_count_why(0))


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.log: list[str] = []

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def _home(clock: _Clock, counts: list[int | None], seen: Any, *, key: str | None = "F8",
          reason: str = "time_box", seated: bool = False) -> dict[str, Any]:  # fmt: skip
    reads = list(counts)

    def read_count() -> int | None:
        clock.log.append("read")
        return reads.pop(0) if reads else None

    return dh.player_home_end(
        key, reason, seated, read_count=read_count,
        press=lambda: clock.log.append("press"), stand=lambda: clock.log.append("stand"),
        basic_info=lambda: seen(clock.t), sleep=clock.sleep, now=clock.now)  # fmt: skip


def test_the_end_presses_the_butterfly_wing_once_with_a_count_of_one_or_more() -> None:
    c = _Clock()
    rec = _home(c, [2], lambda t: not 0.5 <= t < 3.9)  # a load screen 0.5-3.9 s after the press
    assert c.log == ["read", "press"] and rec["pressed"] is True and rec["count"] == 2
    assert rec["why"] == "2 on the hotbar" and rec["stood"] is False
    assert rec["load_s"] == pytest.approx(0.6) and rec["back_s"] == pytest.approx(4.0)
    # a count that reads on the third try (the end Fly Wing's dark frames)
    c = _Clock()
    rec = _home(c, [None, None, 1], lambda t: t > 2.0)
    assert c.log == ["read", "read", "read", "press"] and rec["count"] == 1
    # seated: she stands first, then the wing
    c = _Clock()
    rec = _home(c, [3], lambda t: True, seated=True)
    assert c.log == ["read", "stand", "press"] and rec["stood"] is True
    assert rec["load_s"] is None and rec["back_s"] is None  # no load seen: recorded ...
    assert rec["waited_s"] <= dh.PLAYER_HOME_LOAD_S + 2 * dh.PLAYER_HOME_POLL_S  # ... not waited


def test_the_end_presses_nothing_on_zero_unread_no_key_death_or_a_hard_bar() -> None:
    for counts, why in (([0], "count 0"), ([], "did not read")):
        c = _Clock()
        rec = _home(c, counts, lambda t: True)
        assert "press" not in c.log and rec["pressed"] is False and why in rec["why"]
    c = _Clock()
    _home(c, [], lambda t: True)
    assert c.log == ["read"] * dh.STOCK_TRIES  # an unread count is retried, then given up
    for kw in ({"key": None}, {"reason": "death"}, {"reason": "hard_bar: unknown UI state x"}):
        c = _Clock()
        rec = _home(c, [5], lambda t: True, **kw)
        assert c.log == [] and rec["pressed"] is False and rec["count"] is None, kw
    c = _Clock()
    rec = _home(c, [5], lambda t: False)  # the load never ends: the wait is capped, one press
    assert c.log.count("press") == 1 and rec["back_s"] is None
    assert rec["waited_s"] == pytest.approx(dh.PLAYER_HOME_WAIT_S, abs=dh.PLAYER_HOME_POLL_S)


def _ancestors(node: ast.AST) -> list[ast.AST]:
    out: list[ast.AST] = []
    while node in PARENT:
        node = PARENT[node]
        out.append(node)
    return out


def test_the_home_press_is_on_the_player_path_only_and_types_nothing() -> None:
    run_ = _func("run")
    presses = [n for n in ast.walk(run_) if isinstance(n, ast.Call) and _call_name(n) == "press"
               and n.args and isinstance(n.args[0], ast.Constant)
               and n.args[0].value == "home"]  # fmt: skip
    # dungeon@9.50 (live-blocks.md stage 3): the second is the box's way home's port (call_keys,
    # under `if box_home ...`), pressed only through box_call("home"), which only home_press calls
    # -- on the same player path as the runner's own press below
    assert len(presses) == 2
    port = [p for p in presses if any(isinstance(up, ast.If) and ast.unparse(up.test)
                                      == "box_home and home_key is not None"
                                      for up in _ancestors(p))]  # fmt: skip
    assert len(port) == 1
    presses = [p for p in presses if p is not port[0]]
    box_calls = [n for n in ast.walk(run_) if isinstance(n, ast.Call)
                 and _call_name(n) == "box_call" and n.args and isinstance(n.args[0], ast.Constant)
                 and n.args[0].value == "home"]  # fmt: skip
    assert len(box_calls) == 1
    home_press = next(up for up in _ancestors(box_calls[0]) if isinstance(up, ast.FunctionDef))
    assert home_press.name == "home_press" and presses[0] in list(ast.walk(home_press))
    node: ast.AST = presses[0]
    in_player_else = False
    while node in PARENT:
        up = PARENT[node]
        if isinstance(up, ast.If) and _is_not_player(up.test) and any(node is s for s in up.orelse):
            in_player_else = True
        node = up
    assert in_player_else  # the else of `if not player:` (the lab's end warp is its body)
    assert not _player_never_runs(presses[0])
    calls = [n for n in ast.walk(run_) if isinstance(n, ast.Call)
             and _call_name(n) == "player_home_end"]  # fmt: skip
    assert len(calls) == 1
    end_src = ast.get_source_segment(SRC, _func("player_home_end")) or ""
    for word in ("typed_line", "gm_line", "close_chat", "type_text", '"@'):
        assert word not in end_src, word
    run_src = ast.get_source_segment(SRC, run_) or ""
    assert (
        '"kind": "player_home"' in run_src
        and '**({"player_home_key": home_key} if player else {}),' in run_src
    )


# --- dungeon@9.35c: the start check reads no lab DB under --player-mode ------------------------


def test_the_check_without_the_db_never_asks_who_is_online(monkeypatch: pytest.MonkeyPatch) -> None:
    import crusader as cr

    asked: list[str] = []
    fake = types.SimpleNamespace(online_chars=lambda which: asked.append(which) or ["Someone"],
                                 black=lambda screen: False)  # fmt: skip
    monkeypatch.setitem(sys.modules, "ro_agent", fake)
    monkeypatch.setattr(cr, "load_refs", lambda char: ("Me", None, {}))
    monkeypatch.setattr(cr, "client_frame", lambda screen: None)
    monkeypatch.setattr(cr, "identity", lambda frame, ref, jobs, job: {"ok": True, "job": job})
    assert cr.check(object(), "rogue", "thief", db=False) == {"ok": True, "job": "rogue"}
    assert asked == []  # a public server has no DB of ours: never asked
    # the lab's default still asks, and refuses another character online
    got = cr.check(object(), "rogue", "thief")
    assert asked == ["gm"] and got["ok"] is False and "online on the GM account" in got["why"]


def test_the_run_start_passes_db_off_under_player_mode() -> None:
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    assert 'got = cr.check(screen, conf["job"], crk, db=not player)' in run_src
    # the only other check in run() is the setup's @warp wait, which a player run never reaches
    # (player_plan gives it no line)
    assert run_src.count("cr.check(") == 2


# --- dungeon@9.41 (Batt 2026-11-13): the map's two exits ---------------------------------------
def test_the_weight_exit_ends_the_run_only_over_its_limit() -> None:
    due = dh.weight_home_due
    assert due(None, 0.99, True) is None  # off
    assert due(0.50, 0.50, False) is None  # "over 50 %": 50 % itself goes on
    assert "0.51 > 0.50" in str(due(0.50, 0.51, False))
    assert due(0.50, 0.30, True) is None  # a READ weight wins over a stale red read
    assert "red" in str(due(0.50, None, True))  # unread, but the client draws it red (>= 50 %)
    assert due(0.60, None, True) is None  # red says >= 50 %, not over 60 %
    assert due(0.50, None, False) is None


def test_the_exits_go_with_player_mode_and_a_sane_limit() -> None:
    ns = types.SimpleNamespace
    assert dh.exits_refused(ns(player_mode=True, weight_home=0.5, respawn=True)) is None
    assert dh.exits_refused(ns(player_mode=False, weight_home=None, respawn=False)) is None
    assert "player-mode" in str(
        dh.exits_refused(ns(player_mode=False, weight_home=0.5, respawn=False))
    )
    assert "player-mode" in str(
        dh.exits_refused(ns(player_mode=False, weight_home=None, respawn=True))
    )
    assert "outside" in str(dh.exits_refused(ns(player_mode=True, weight_home=0.05, respawn=False)))
    assert "outside" in str(dh.exits_refused(ns(player_mode=True, weight_home=1.5, respawn=False)))
    # 2026-11-13: the respawn point is the person's (another server's menu), inside the picture
    ok = ns(player_mode=True, weight_home=None, respawn=True, respawn_at=(600, 500))
    assert dh.exits_refused(ok) is None
    assert "goes with --respawn" in str(
        dh.exits_refused(ns(player_mode=True, weight_home=None, respawn=False, respawn_at=(1, 1)))
    )
    assert "off the game picture" in str(
        dh.exits_refused(ns(player_mode=True, weight_home=None, respawn=True, respawn_at=(1280, 5)))
    )


def _respawn(clock: _Clock, dead: Any, seen: Any) -> dict[str, Any]:
    return dh.respawn_end(
        dead=lambda: dead(clock.t),
        press=lambda: clock.log.append("press"),
        basic_info=lambda: seen(clock.t),
        sleep=clock.sleep,
        now=clock.now,
    )


def test_the_respawn_presses_once_while_the_dialog_reads_and_waits_for_the_town() -> None:
    c = _Clock()
    # the press at t=1.0 (after RESPAWN_SETTLE_S); the dialog gone 0.5 s later, a load 1-6 s
    rec = _respawn(c, lambda t: t < 1.5, lambda t: not 2.0 <= t < 7.0)
    assert c.log == ["press"] and rec["pressed"] is True and "why" not in rec
    assert rec["dialog_gone_s"] == pytest.approx(0.5) and rec["load_s"] == pytest.approx(1.0)
    assert rec["back_s"] == pytest.approx(6.0)


def test_the_respawn_presses_nothing_without_the_dialog_and_never_twice() -> None:
    c = _Clock()
    rec = _respawn(c, lambda t: False, lambda t: True)
    assert c.log == [] and rec["pressed"] is False and "does not read" in rec["why"]
    c = _Clock()
    rec = _respawn(c, lambda t: True, lambda t: True)  # the dialog stays
    assert c.log == ["press"] and "stayed" in rec["why"]
    c = _Clock()
    rec = _respawn(c, lambda t: t < 1.5, lambda t: True)  # gone, but no load: still here?
    assert c.log == ["press"] and "no load screen" in rec["why"]
    c = _Clock()
    rec = _respawn(c, lambda t: t < 1.5, lambda t: t < 2.0)  # a load that never ends
    assert c.log == ["press"] and "did not end" in rec["why"]


def test_the_respawn_button_is_the_dialogs_first_one_inside_its_box() -> None:
    import gm_vitals as gv

    x0, y0, w, h = gv.DEAD_BOX
    for x, y in (dh.MOVE_TO_SAVE, gv.RETURN_TO_GAME):
        assert x0 < x < x0 + w and y0 < y < y0 + h
    assert dh.MOVE_TO_SAVE[0] == gv.RETURN_TO_GAME[0] and dh.MOVE_TO_SAVE[1] < gv.RETURN_TO_GAME[1]


def test_the_respawn_is_on_the_player_path_only_behind_its_flag_and_types_nothing() -> None:
    run_ = _func("run")
    calls = [
        n for n in ast.walk(run_) if isinstance(n, ast.Call) and _call_name(n) == "respawn_end"
    ]
    assert len(calls) == 1
    node: ast.AST = calls[0]
    in_player_else = flagged = False
    while node in PARENT:
        up = PARENT[node]
        if isinstance(up, ast.If) and _is_not_player(up.test) and any(node is s for s in up.orelse):
            in_player_else = True
        if isinstance(up, ast.If) and "respawn" in (ast.get_source_segment(SRC, up.test) or ""):
            flagged = True
        node = up
    assert in_player_else and flagged
    for fn in ("respawn_end", "weight_home_due"):
        src = ast.get_source_segment(SRC, _func(fn)) or ""
        for word in ("typed_line", "gm_line", "close_chat", "type_text", '"@'):
            assert word not in src, (fn, word)


def test_the_record_carries_the_exits_only_when_on(monkeypatch: Any) -> None:
    base = dh.fixes_of(_ns(monkeypatch))
    assert "weight_home" not in base and "respawn" not in base
    on = dh.fixes_of(_ns(monkeypatch, "--player-mode", "--weight-home", "0.5", "--respawn"))
    assert on["weight_home"] == 0.5 and on["respawn"] is True
    # player_map: dungeon@9.46; player_slots: dungeon@9.47
    pm = ("weight_home", "respawn", "player_mode", "player_map", "player_slots")
    assert {k: v for k, v in on.items() if k not in pm} == {
        k: v for k, v in base.items() if k != "player_mode"
    }


def test_run_refuses_the_exits_without_player_mode_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--respawn")
    monkeypatch.undo()

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert "dungeon@9.41 refused" in str(exc.value) and "--player-mode" in str(exc.value)


def test_the_fly_key_is_a_free_row1_key_and_the_record_names_it(monkeypatch: Any) -> None:
    keys = dh.CHARS_CONF["rogue"]["keys"]
    assert dh.fly_key_refused(None, keys, "F4") is None
    assert dh.fly_key_refused("F8", keys, "F4") is None
    assert dh.fly_key_refused("F2", keys, "F4") is None  # its own default
    assert "row-1" in str(dh.fly_key_refused("F12", keys, "F4"))
    assert "potion" in str(dh.fly_key_refused("F1", keys, "F4"))
    assert "--steal-opener" in str(dh.fly_key_refused("F4", keys, "F4"))
    assert dh.fixes_of(_ns(monkeypatch, "--fly-key", "F8"))["fly_key"] == "F8"
    assert "fly_key" not in dh.fixes_of(_ns(monkeypatch))


# --- dungeon@9.42 (Batt 2026-11-13 ~13:3x: "everything a user can set again or edit; nothing
# fixed, we only put the defaults"): the heal key, the dagger key, the Knife swap's numbers -------
def test_the_persons_heal_and_dagger_keys_join_the_key_map() -> None:
    keys = dh.CHARS_CONF["rogue"]["keys"]
    got, why = dh.person_keys(keys, "F6", "F7")
    assert why is None and got["potion"] == "F6" and got["equip"] == "F7"
    assert keys["potion"] == "F1" and keys["equip"] == "F5"  # the character's own map: unchanged
    assert dh.person_keys(keys, None, None) == (dict(keys), None)
    assert "--heal-key" in str(dh.person_keys(keys, "F10", None)[1])
    assert "--dagger-key" in str(dh.person_keys(keys, None, "Enter")[1])


def test_no_two_of_the_runs_keys_alike() -> None:
    run_keys = {"potion": "F1", "fly": "F8", "equip": "F5", "home": "F9", "sit": "Insert",
                "stand": "Insert"}  # fmt: skip
    assert dh.keys_clash(run_keys, "F4") is None  # sit / stand share Insert by design
    assert "F4 is set for --steal-opener and fly" in str(
        dh.keys_clash({**run_keys, "fly": "F4"}, "F4")
    )
    assert "F5 is set for equip and potion" in str(
        dh.keys_clash({**run_keys, "potion": "F5"}, None)
    )


def test_the_knife_numbers_go_with_bare_steal_inside_their_ranges(monkeypatch: Any) -> None:
    ok = _ns(monkeypatch, "--bare-steal", "--knife-max-s", "0.2", "--knife-hp-min", "0.35")
    assert dh.knife_numbers_refused(ok) is None
    rec = dh.fixes_of(ok)
    assert rec["knife_max_s"] == 0.2 and rec["knife_hp_min"] == 0.35
    assert "--bare-steal" in str(dh.knife_numbers_refused(_ns(monkeypatch, "--knife-max-s", "1")))
    assert "outside" in str(
        dh.knife_numbers_refused(_ns(monkeypatch, "--bare-steal", "--knife-max-s", "30"))
    )
    assert "outside" in str(
        dh.knife_numbers_refused(_ns(monkeypatch, "--bare-steal", "--knife-hp-min", "0.1"))
    )
    keys = dh.fixes_of(_ns(monkeypatch, "--heal-key", "F6", "--dagger-key", "F7"))
    assert keys["heal_key"] == "F6" and keys["dagger_key"] == "F7"
    assert "heal_key" not in dh.fixes_of(_ns(monkeypatch))


# --- dungeon@9.43 (Batt 2026-11-13 ~14:2x: the heal and escape numbers are the person's) -------
def test_the_survival_numbers_replace_the_strategys_inside_their_ranges(monkeypatch: Any) -> None:
    p2 = dh.STRATEGIES["P2"]
    a = _ns(monkeypatch, "--potion-below", "0.55", "--fly-below", "0.25", "--fly-rate", "120",
            "--fly-rate-below", "0.65")  # fmt: skip
    assert dh.survival_refused(a) is None
    st = dh.with_survival(p2, a)
    assert (st["potion_below"], st["fly_below"], st["fly_rate"], st["fly_rate_below"]) == (
        0.55, 0.25, 120.0, 0.65)  # fmt: skip
    assert p2["potion_below"] == 0.40  # the strategy itself is unchanged
    assert dh.with_survival(p2, _ns(monkeypatch)) == dict(p2)  # no flag: the strategy's own
    rec = dh.fixes_of(a)
    assert rec["potion_below"] == 0.55 and rec["fly_rate"] == 120.0
    for flag, v in (("--potion-below", "0.95"), ("--fly-below", "0.01"), ("--fly-rate", "10"),
                    ("--fly-rate-below", "1.2")):  # fmt: skip
        assert "outside" in str(dh.survival_refused(_ns(monkeypatch, flag, v))), flag
    # sustain() uses them: a potion at 0.50 HP with --potion-below 0.55, none with the default
    s_ = dh.Sustain()
    assert ("potion", "hp 0.50") in dh.sustain(s_, 10.0, 0.50, None, {**st, "max_hp": 5070})
    assert dh.sustain(dh.Sustain(), 10.0, 0.50, None, {**p2, "max_hp": 5070}) == []


def test_run_refuses_a_clash_of_the_persons_keys_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    for argv, word in ((("--heal-key", "F2"), "F2 is set for fly and potion"),
                       (("--bare-steal", "--knife-max-s", "30"), "outside"),
                       (("--fly-below", "0.9"), "--fly-below 0.9 is outside")):  # fmt: skip
        a = _ns(monkeypatch, *argv)
        monkeypatch.undo()

        def no_session(*_: Any, **__: Any) -> Any:
            raise AssertionError("a session was opened")

        monkeypatch.setattr(r, "session", no_session)
        with pytest.raises(SystemExit) as exc:
            dh.run(a)
        assert "refused" in str(exc.value) and word in str(exc.value), str(exc.value)
        monkeypatch.undo()


def test_run_refuses_a_taken_fly_key_before_any_input(monkeypatch: Any) -> None:
    import ro_agent as r

    a = _ns(monkeypatch, "--fly-key", "F1")
    monkeypatch.undo()

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "session", no_session)
    with pytest.raises(SystemExit) as exc:
        dh.run(a)
    assert "refused" in str(exc.value) and "potion" in str(exc.value)


def test_the_respawn_presses_the_confirmation_once_only_while_it_reads() -> None:
    """2026-11-13 11:57 (live): this client asks "go back to your savepoint?" after the menu."""
    c = _Clock()
    # the menu reads until the press (t=1.0); the confirmation reads from 1.5 s to the OK; a load
    rec = dh.respawn_end(
        dead=lambda: c.t <= 1.0,
        press=lambda: c.log.append("press"),
        basic_info=lambda: not 2.5 <= c.t < 6.0,
        confirm_reads=lambda: c.t >= 1.5 and "ok" not in c.log,
        confirm_press=lambda: c.log.append("ok"),
        sleep=c.sleep,
        now=c.now,
    )
    assert c.log == ["press", "ok"] and rec["confirm"] == "pressed" and "why" not in rec
    assert rec["back_s"] is not None
    c = _Clock()  # a server that asks nothing: no OK pressed, the load still counts
    rec = dh.respawn_end(
        dead=lambda: c.t <= 1.0,
        press=lambda: c.log.append("press"),
        basic_info=lambda: not 2.0 <= c.t < 5.0,
        confirm_reads=lambda: False,
        confirm_press=lambda: c.log.append("ok"),
        sleep=c.sleep,
        now=c.now,
    )
    assert c.log == ["press"] and rec["confirm"] == "none seen" and rec["back_s"] is not None


def test_the_confirm_point_is_a_point_or_none(monkeypatch: Any) -> None:
    a = _ns(monkeypatch, "--player-mode", "--respawn", "--respawn-confirm-at", "none")
    assert a.respawn_confirm_at == "none" and dh.exits_refused(a) is None
    a = _ns(monkeypatch, "--player-mode", "--respawn", "--respawn-confirm-at", "714,405")
    assert a.respawn_confirm_at == (714, 405) and dh.fixes_of(a)["respawn_confirm_at"] == [714, 405]
    ns = types.SimpleNamespace
    off = ns(player_mode=True, weight_home=None, respawn=False, respawn_confirm_at=(1, 1))
    assert "goes with --respawn" in str(dh.exits_refused(off))


# --- (g) dungeon@9.46: the map she stands on, from the minimap's picture, before ANY input --------

KEY = (255, 0, 255)


def _bitmap(seed: int) -> np.ndarray:
    """A SYNTHETIC minimap bitmap (no client picture in git): random 8 px blocks, a key strip."""
    rng = np.random.default_rng(seed)
    img = np.kron(rng.integers(0, 230, (8, 8, 3), dtype=np.uint8), np.ones((8, 8, 1), np.uint8))
    img[:, :19] = KEY
    return img


def _map_refs() -> Any:
    import minimap_id as mi

    return mi.MapRefs.from_pictures({"xmas_dun02": mi.render_picture(_bitmap(1)),
                                     "geffen": mi.render_picture(_bitmap(2))})  # fmt: skip


class MapScreen:
    """A screen that can only be grabbed (and closed), showing ``seed``'s minimap (None: none)."""

    def __init__(self, seed: int | None) -> None:
        import minimap_id as mi

        self.calls: list[str] = []
        self.img = np.full((720, 1280, 4), 120, np.uint8)
        if seed is not None:
            g, d = mi.render_picture(_bitmap(seed))
            x, y = 1136 + mi.PIC_OFFSET[0], 18 + mi.PIC_OFFSET[1]
            sq = self.img[y : y + mi.PIC_SIZE, x : x + mi.PIC_SIZE, :3].astype(np.float32)
            a = 0.7 * d[..., None]
            self.img[y : y + mi.PIC_SIZE, x : x + mi.PIC_SIZE, :3] = (a * g[..., None]
                                                                       + (1 - a) * sq)  # fmt: skip

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        self.calls.append("grab_meta")
        return 1, self.img[y : y + h, x : x + w], -1, "x11"

    def close(self) -> None:
        self.calls.append("close")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the map read asked the screen for {name!r}")


def _no_input(monkeypatch: Any, seed: int | None) -> MapScreen:
    import ro_agent as r

    screen = MapScreen(seed)

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    class NoAgent:
        def __init__(self, *_: Any, **__: Any) -> None:
            raise AssertionError("an Agent was made")

    monkeypatch.setattr(r, "session", no_session)
    monkeypatch.setattr(r, "Agent", NoAgent)
    monkeypatch.setattr(r, "Screen", lambda: screen)
    monkeypatch.setattr(dh, "PLAYER_MAP_S", 0.3)
    return screen


REGION = (0, 0, 1280, 720)


def test_the_start_refuses_another_map_before_any_input(monkeypatch: Any) -> None:
    screen = _no_input(monkeypatch, 2)  # she stands in "geffen"
    with pytest.raises(SystemExit) as exc:
        dh.player_start_map("xmas_dun02", _map_refs(), REGION)
    assert str(exc.value).startswith(
        "dungeon@9.46 refused: --player-mode: the screen shows geffen, not xmas_dun02: walk or "
        "warp her there first (a person)"
    )
    assert "read from the minimap" in str(exc.value)
    assert set(screen.calls) == {"grab_meta", "close"} and screen.calls[-1] == "close"


def test_the_start_goes_on_when_the_minimap_is_the_runs_map(monkeypatch: Any) -> None:
    screen = _no_input(monkeypatch, 1)
    rd = dh.player_start_map("xmas_dun02", _map_refs(), REGION)
    assert rd.map == "xmas_dun02" and screen.calls == ["grab_meta", "close"]  # its first frame
    assert rd.record()["map"] == "xmas_dun02"


def test_a_start_that_cannot_tell_refuses_or_warns_by_the_rule(monkeypatch: Any,
                                                              capsys: Any) -> None:  # fmt: skip
    _no_input(monkeypatch, None)  # no minimap drawn (a load screen, an indoor map)
    assert dh.PLAYER_MAP_UNREAD == "refuse"  # the held-out set's decision (player-mode.md)
    with pytest.raises(SystemExit, match="does not show that she is on xmas_dun02"):
        dh.player_start_map("xmas_dun02", _map_refs(), REGION)
    monkeypatch.setattr(dh, "PLAYER_MAP_UNREAD", "warn")
    rd = dh.player_start_map("xmas_dun02", _map_refs(), REGION)
    out = capsys.readouterr().out
    assert rd.map is None and "WARNING: --player-mode: is she on xmas_dun02?" in out
    # another map still refuses under "warn"
    _no_input(monkeypatch, 2)
    with pytest.raises(SystemExit, match="the screen shows geffen"):
        dh.player_start_map("xmas_dun02", _map_refs(), REGION)


def test_no_references_refuse_with_the_build_command(monkeypatch: Any) -> None:
    screen = _no_input(monkeypatch, 1)
    with pytest.raises(SystemExit, match="minimap_id.py build"):
        dh.player_start_map("xmas_dun02", None, REGION)
    assert "grab_meta" not in screen.calls  # no references: no frame is even read
    assert dh.load_map_refs(Path("/nonexistent/refs.npz")) is None


def test_the_map_is_read_after_the_check_and_before_the_session() -> None:
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_ck = run_src.index('if getattr(a, "cmd", "run") == "check":')
    i_ret = run_src.index("return 0", i_ck)
    i_map = run_src.index("map_read = player_start_map(map_, map_refs, (gx0, gy0, gw, gh)) if "
                          "player else None")  # fmt: skip
    assert i_ret < i_map < run_src.index("out.mkdir(") < run_src.index("with r.session(")
    assert run_src.index("map_refs = load_map_refs() if player else None") < i_ck
    # the check gets the same references
    assert "map_refs=map_refs" in run_src[i_ck:i_ret]
    f = _func("player_start_map")
    calls = {_call_name(n) for n in ast.walk(f) if isinstance(n, ast.Call)}
    no_input = {"session", "Agent", "keys", "click", "move", "ensure_clear", "select_tab"}
    assert "Screen" in calls and not calls & (no_input | {"typed_line"})
