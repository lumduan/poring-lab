"""dungeon_hunt.py check (dungeon@9.45; Batt 2026-11-13 "do it"): /flows' start checklist ticked
from the GAME SCREEN before Run. It takes run's own flags, runs run()'s preamble, then READS the
player start's checks -- it sends NO input: no key, click, move, line, window or tab. Each line is
decided by the same function the runner's own start uses."""

from __future__ import annotations

import ast
import re
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_run as fr  # noqa: E402
import ro_agent as r0  # noqa: E402

AGENT0, SESSION0 = r0.Agent, r0.session  # the real ones (a check's process replaces them)

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
TREE = ast.parse(SRC)
# every API that sends input (ro_agent's Agent and session, its key / click / move calls, the UI
# gate's closing steps, the chat tab's select) or types a line (TYPING_CALLS)
INPUT_CALLS = dh.TYPING_CALLS | {
    "Agent", "session", "keys", "key", "click", "double_click", "move", "move_to", "press",
    "drag", "wheel", "release_all", "send", "send_many", "send_input", "ensure_clear",
    "select_tab", "activate_client", "close_chat", "open_window", "close_window",
    "wait_for_human", "clear_etc", "typed_line",
}  # fmt: skip
CHECK_FUNCS = ("start_check", "_wings_line", "_heals_line", "_home_line", "_knife_line",
               "_dagger_line", "check_used", "check_item", "check_verdict", "read_start_map",
               "player_map_verdict")  # fmt: skip


def _func(name: str) -> ast.FunctionDef:
    (f,) = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return f


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _flow_argv() -> list[str]:
    argv = fr.check_command(fr.FLOWS["xmas_dun02_rogue"])
    return argv[argv.index("scripts/dungeon_hunt.py") + 2 :]


# --- (a) structure: no input path ----------------------------------------------------------------


def test_the_check_calls_no_input_api() -> None:
    """Every function of the check: no call of an input or typing API, no agent anywhere."""
    for name in CHECK_FUNCS:
        f = _func(name)
        calls = {_call_name(n) for n in ast.walk(f) if isinstance(n, ast.Call)}
        assert not calls & INPUT_CALLS, (name, sorted(calls & INPUT_CALLS))
        names = {n.id for n in ast.walk(f) if isinstance(n, ast.Name)}
        assert not names & {"agent", "agent_raw", "Agent"}, name
        args = [a.arg for a in f.args.args]
        assert "agent" not in args and "agent_raw" not in args, name


def test_the_check_returns_before_the_session_and_its_folder() -> None:
    """run()'s check branch comes after every preamble refusal and before the session, the
    session folder and its events file: a check makes no session and opens no agent."""
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_ck = run_src.index('if getattr(a, "cmd", "run") == "check":')
    i_ret = run_src.index("return 0", i_ck)
    for later in ("with r.session(", "out.mkdir(", '(out / "events.jsonl")', "BoxWatch(",
                  "oh.HudSender("):  # fmt: skip
        assert i_ret < run_src.index(later), later
    for earlier in ('raise SystemExit(f"dungeon@{PLAYER_MODE_VERSION} refused: {why_pm}")',
                    'raise SystemExit(f"dungeon@{PERSON_KEYS_VERSION} refused: {why_kc}")',
                    "okr = okr & ~cut", "digits = selfpos.load_digit_templates()"):  # fmt: skip
        assert run_src.index(earlier) < i_ck, earlier
    (node,) = [n for n in ast.walk(_func("run")) if isinstance(n, ast.If)
               and ast.unparse(n.test) == "getattr(a, 'cmd', 'run') == 'check'"]  # fmt: skip
    calls = {_call_name(n) for n in ast.walk(node) if isinstance(n, ast.Call)}
    assert {"Screen", "start_check"} <= calls and not calls & INPUT_CALLS, calls
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    assert not names & {"agent", "agent_raw", "Agent"}
    assert isinstance(node.body[-1], ast.Return)


def test_check_takes_runs_own_flags_and_no_flag_of_its_own() -> None:
    main = _func("main")
    own = [n for n in main.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
           and _call_name(n.value) == "add_parser" and n.value.args
           and ast.literal_eval(n.value.args[0]) == "check"]  # fmt: skip
    assert len(own) == 1  # a bare expression: no name to add a flag of its own to
    kw = {k.arg: k.value for k in own[0].value.keywords}  # type: ignore[attr-defined]
    assert ast.unparse(kw["parents"]) == "[t]"  # run's parser: every flag, every default


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> dict[str, Any]:
    import ro_agent as r

    monkeypatch.setattr(r, "Agent", AGENT0)  # undone after the test: no_input_guard replaces it
    monkeypatch.setattr(r, "session", SESSION0)
    got: dict[str, Any] = {}

    def fake_run(a: Any) -> int:
        got["a"] = a
        if r.Agent is AGENT0:  # a run's own path: never constructed here (it would connect)
            assert r.session is SESSION0
            return 0
        for what, make in (("agent", lambda: r.Agent("x")), ("session", lambda: r.session("x"))):
            try:
                make()
            except SystemExit as e:
                got[what] = str(e)
        return 0

    monkeypatch.setattr(dh, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["dungeon_hunt.py", *argv])
    assert dh.main() == 0
    return got


def test_a_checks_process_can_open_no_agent_or_session(monkeypatch: pytest.MonkeyPatch) -> None:
    got = _main(monkeypatch, "check", *_flow_argv())
    a = got["a"]
    assert a.cmd == "check" and a.player_mode and a.steal_opener == "F4" and a.fly_key == "F8"
    assert "sends no input" in got["agent"] and "sends no input" in got["session"]
    # the same flags as a run take the same values
    ran = _main(monkeypatch, "run", *_flow_argv())["a"]
    assert {k: v for k, v in vars(a).items() if k != "cmd"} == \
        {k: v for k, v in vars(ran).items() if k != "cmd"}  # fmt: skip
    assert "agent" not in _main(monkeypatch, "run", *_flow_argv())  # a run's own path: unchanged


def test_check_goes_with_player_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = [x for x in _flow_argv() if x != "--player-mode"]
    with pytest.raises(SystemExit, match="check goes with --player-mode"):
        _main(monkeypatch, "check", *argv)


# --- (b) a check run, with a fake screen ---------------------------------------------------------


class FakeScreen:
    """A screen that can only be grabbed: anything else it is asked fails the test."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.img = np.full((720, 1280, 4), 230, np.uint8)

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        self.calls.append("grab_meta")
        return 1, self.img[y : y + h, x : x + w], -1, "x11"

    def grab(self, x: int, y: int, w: int, h: int) -> tuple[int, Any]:
        self.calls.append("grab")
        return 1, self.img[y : y + h, x : x + w]

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the check asked the screen for {name!r}")


def _ctx(**kw: Any) -> Any:
    keys = {"potion": "F1", "fly": "F8", "home": "F9", "equip": "F5", "sit": "Insert",
            "stand": "Insert"}  # fmt: skip
    g = np.ones((40, 120), bool)
    base = dict(map_="xmas_dun02", conf=dh.CHARS_CONF["rogue"], crk="thief", keys=keys,
                stock_items=dict(dh.STOCK_ITEMS), heal_candy=False, opener="F4", bare=True,
                explore=False, okr=g, area=g, digits=None, region=(0, 0, 1280, 720))  # fmt: skip
    return dh.CheckCtx(**{**base, **kw})


def _readers(monkeypatch: pytest.MonkeyPatch, counts: dict[int, int | None], *,
             chat_open: bool = False, cell: tuple[int, int] | None = (7, 21),
             weight: list[int] | None = None) -> list[str]:  # fmt: skip
    """The readers' pixel work faked (their templates are client-derived, never in git); the
    decisions stay the runner's. ro_agent's Agent and session refuse: a check never needs them."""
    import crusader as cr
    import gm_state
    import hotbar_count as hb
    import ro_agent as r

    from poring_env import selfpos

    made: list[str] = []

    class NoAgent:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            made.append("Agent")
            raise AssertionError("an Agent was made")

    def no_session(*_a: Any, **_k: Any) -> Any:
        made.append("session")
        raise AssertionError("a session was opened")

    monkeypatch.setattr(r, "Agent", NoAgent)
    monkeypatch.setattr(r, "session", no_session)
    monkeypatch.setattr(r, "game_region", lambda: (0, 0, 1280, 720))
    monkeypatch.setattr(r, "is_state", lambda screen, state, after_ns=None: chat_open)
    monkeypatch.setattr(
        cr, "check", lambda screen, job, char, db=True: {"ok": db is False, "why": "db asked"}
    )
    monkeypatch.setattr(cr, "load_refs", lambda char: ("Rogue", None, {}))
    monkeypatch.setattr(gm_state, "_weight", lambda frames: weight)
    monkeypatch.setattr(hb, "load", lambda path=None: {})
    monkeypatch.setattr(hb, "read_count", lambda gray, slot, tpl: counts.get(slot))
    xy = types.SimpleNamespace(xy=cell, mode="base")
    monkeypatch.setattr(selfpos, "read_minimap", lambda img, digits, rect=None, light=False: xy)
    monkeypatch.setattr(dh, "PLAYER_POS_S", 0.3)
    return made


GOOD = {0: 10, 7: 12, 8: 3, 3: None, 4: 0}  # F1 potions, F8 wings, F9 butterfly, F4 knife, F5


def test_a_check_run_sends_nothing_and_ticks_every_line(monkeypatch: pytest.MonkeyPatch) -> None:
    made = _readers(monkeypatch, GOOD, weight=[300, 1000])
    screen = FakeScreen()
    got = dh.start_check(screen, _ctx())
    assert made == []  # no Agent, no session
    assert set(screen.calls) <= {"grab", "grab_meta"} and screen.calls
    ids = [i["id"] for i in got["items"]]
    assert ids == [x for x in dh.CHECK_IDS if x in ids] and set(ids) == set(dh.CHECK_IDS)
    by = {i["id"]: i for i in got["items"]}
    # without minimap references the map line is never a tick (matpilot 2026-11-13: a cell is
    # no proof of the map): "?"
    assert by["cell"]["ok"] is None and "is she on" in by["cell"]["words"]
    assert all(i["ok"] is True for i in got["items"] if i["id"] != "cell"), got["items"]
    assert got["ok"] is None and got["refuses"] is False and got["version"] == "9.45"
    assert by["wings"]["value"] == "12 Fly Wings on F8"
    assert by["heals"]["value"] == "10 heal items on F1"
    assert by["home"]["value"] == "3 Butterfly Wings on F9" and by["home"]["refuses"] is False
    assert by["weight"]["value"] == "30 %" and by["cell"]["value"] == "(7, 21)"
    # the map line says what it knows: a cell, and no references to read the map's name by
    assert "no minimap reference for xmas_dun02" in by["cell"]["words"]
    assert "minimap_id.py build" in by["cell"]["words"]
    assert got["used"]["fly_key"] == "F8" and got["used"]["PLAYER_MIN_WINGS"] == 5


def test_each_line_fails_with_the_runners_own_words(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = {0: 2, 7: 3, 8: 0, 3: 0, 4: None}  # 2 potions, 3 wings, no butterfly, F4 / F5 wrong
    _readers(monkeypatch, bad, chat_open=True, cell=(500, 500), weight=[480, 1000])
    got = dh.start_check(FakeScreen(), _ctx())
    by = {i["id"]: i for i in got["items"]}
    assert by["chat"]["ok"] is False and by["chat"]["words"] == dh.player_chat_refused(True, "now")
    assert by["wings"]["words"] == dh.player_wings_refused({601: 3})
    assert by["heals"]["words"] == dh.player_heals_refused({504: 2}, [504])
    assert by["weight"]["ok"] is False and "never dropped" in by["weight"]["words"]
    assert by["cell"]["ok"] is False and "is she on xmas_dun02" in by["cell"]["words"]
    assert by["home"]["ok"] is False and by["home"]["refuses"] is False  # the runner goes on
    assert by["knife"]["ok"] is False and "EMPTY" in by["knife"]["words"]
    assert by["dagger"]["ok"] is False and "shows an icon" in by["dagger"]["words"]
    assert got["ok"] is False and got["refuses"] is True
    # an unread count: the runner refuses it too (never a guess); the home line is only unread
    _readers(monkeypatch, {0: None, 7: None, 8: None, 3: None, 4: 0}, weight=[300, 1000])
    by = {i["id"]: i for i in dh.start_check(FakeScreen(), _ctx())["items"]}
    assert by["wings"]["ok"] is False and "did not read" in by["wings"]["words"]
    assert by["home"]["ok"] is None and "did not read" in by["home"]["words"]


def test_no_knife_lines_without_the_knife_swap_and_a_read_error_is_not_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _readers(monkeypatch, GOOD, weight=None)
    got = dh.start_check(FakeScreen(), _ctx(bare=False, opener=None))
    ids = [i["id"] for i in got["items"]]
    assert "knife" not in ids and "dagger" not in ids
    by = {i["id"]: i for i in got["items"]}
    assert by["weight"]["ok"] is False  # an unread weight: the runner refuses it (fail closed)
    import ro_agent as r

    def frozen(*_a: Any, **_k: Any) -> Any:
        raise r.FrozenStream("no frame newer than the action within 1.5 s")

    monkeypatch.setattr(r, "is_state", frozen)
    by = {i["id"]: i for i in dh.start_check(FakeScreen(), _ctx())["items"]}
    assert by["chat"]["ok"] is None and "not read from the screen" in by["chat"]["words"]


def test_the_verdict() -> None:
    it = dh.check_item
    assert dh.check_verdict([it("a", True, ""), it("b", True, "")]) == {
        "ok": True,
        "refuses": False,
    }
    assert dh.check_verdict([it("a", True, ""), it("b", None, "")])["ok"] is None
    v = dh.check_verdict([it("a", None, ""), it("home", False, "", refuses=False)])
    assert v == {"ok": False, "refuses": False}  # a warning line: the runner goes on
    assert dh.check_verdict([it("a", False, "")]) == {"ok": False, "refuses": True}
    assert dh.check_verdict([])["ok"] is None


def test_the_split_stock_rules_are_the_old_one() -> None:
    for counts, heal in (({601: 4, 504: 9}, [504]), ({601: 9, 504: 2}, [504]),
                         ({601: None, 504: 9}, [504]), ({601: 9, 504: None}, [504]),
                         ({601: 9, 530: 2, 529: 2, 504: 1}, [530, 529, 504]),
                         ({601: 9, 504: 9}, [504])):  # fmt: skip
        want = dh.player_wings_refused(counts) or dh.player_heals_refused(counts, heal)
        assert dh.player_stock_refused(counts, heal) == want
    assert dh.player_heal_items(False) == [504] and dh.player_heal_items(True) == [530, 529, 504]
    assert dh.stock_slots({"potion": 504, "fly": 601}, {"potion": "F1", "fly": "F8"}) == {
        504: 0, 601: 7}  # fmt: skip
    assert dh.player_chat_refused(False, "x") is None


def test_the_check_ids_are_the_pages_checklist_ids() -> None:
    """/flows' checklist (lib/flow/config.ts startChecklist) has a line for each id the check
    ticks, with the same id."""
    ts = (ROOT / "services/frontend/src/lib/flow/config.ts").read_text()
    body = ts[ts.index("export const CHECKLIST_IDS") : ts.index("];", ts.index("CHECKLIST_IDS"))]
    assert re.findall(r'"([a-z_]+)"', body) == list(dh.CHECK_IDS)
    assert dh.CHECK_MARK == fr.CHECK_MARK


def test_the_feature_version_is_the_checks() -> None:
    import runner_flow_export as rfe

    assert dh.LIVE_CHECK_VERSION == "9.45" and dh.VERSION == "dungeon@8.7"
    assert dh.MAP_IDENTITY_VERSION == "9.46"  # the map line's reader (minimap_id)
    assert rfe.feature_version(dh) == "dungeon@9.46"


# --- (c) dungeon@9.46: the map line, from the minimap's picture -----------------------------------


def _bitmap(seed: int) -> np.ndarray:
    """A SYNTHETIC minimap bitmap (no client picture in git): random 8 px blocks, a key strip."""
    rng = np.random.default_rng(seed)
    img = np.kron(rng.integers(0, 230, (8, 8, 3), dtype=np.uint8), np.ones((8, 8, 1), np.uint8))
    img[:, :19] = (255, 0, 255)
    return img


def _paint(screen: FakeScreen, seed: int) -> FakeScreen:
    """``seed``'s picture drawn where the client draws the minimap, translucent over the scene."""
    import minimap_id as mi

    g, d = mi.render_picture(_bitmap(seed))
    x, y = 1136 + mi.PIC_OFFSET[0], 18 + mi.PIC_OFFSET[1]
    sq = screen.img[y : y + mi.PIC_SIZE, x : x + mi.PIC_SIZE, :3].astype(np.float32)
    a = 0.7 * d[..., None]
    screen.img[y : y + mi.PIC_SIZE, x : x + mi.PIC_SIZE, :3] = a * g[..., None] + (1 - a) * sq
    return screen


def _refs() -> Any:
    import minimap_id as mi

    return mi.MapRefs.from_pictures({"xmas_dun02": mi.render_picture(_bitmap(1)),
                                     "geffen": mi.render_picture(_bitmap(2))})  # fmt: skip


def test_the_map_line_ticks_only_on_the_runs_minimap(monkeypatch: pytest.MonkeyPatch) -> None:
    made = _readers(monkeypatch, GOOD, weight=[300, 1000])
    monkeypatch.setattr(dh, "PLAYER_MAP_S", 0.3)
    screen = _paint(FakeScreen(), 1)
    got = dh.start_check(screen, _ctx(map_refs=_refs()))
    by = {i["id"]: i for i in got["items"]}
    assert made == [] and set(screen.calls) <= {"grab", "grab_meta"}
    assert by["cell"]["ok"] is True and by["cell"]["value"] == "(7, 21)"
    assert by["cell"]["words"].startswith("the minimap is xmas_dun02's")
    assert "her cell (7, 21) is on xmas_dun02's open ground" in by["cell"]["words"]
    assert got["ok"] is True and got["refuses"] is False  # every line ticked


def test_the_map_line_crosses_another_map_before_its_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    # 19:02 ICT 2026-11-13: she stood in Geffen at (119, 40), a cell on xmas_dun02's open ground
    _readers(monkeypatch, GOOD, cell=(119, 40), weight=[300, 1000])
    monkeypatch.setattr(dh, "PLAYER_MAP_S", 0.3)
    got = dh.start_check(_paint(FakeScreen(), 2), _ctx(map_refs=_refs()))
    by = {i["id"]: i for i in got["items"]}
    assert by["cell"]["ok"] is False and by["cell"]["refuses"] is True
    assert by["cell"]["words"].startswith("she is on geffen, not xmas_dun02 (read from the minimap")
    assert by["cell"]["words"].endswith("walk or warp her to xmas_dun02 first")
    assert by["cell"]["value"] == "(119, 40)"  # the line keeps the cell
    assert got["ok"] is False and got["refuses"] is True


def test_the_map_line_asks_a_person_when_it_cannot_tell(monkeypatch: pytest.MonkeyPatch) -> None:
    _readers(monkeypatch, GOOD, weight=[300, 1000])
    monkeypatch.setattr(dh, "PLAYER_MAP_S", 0.3)
    screen = FakeScreen()  # no minimap drawn: a flat square
    by = {i["id"]: i for i in dh.start_check(screen, _ctx(map_refs=_refs()))["items"]}
    assert by["cell"]["ok"] is None and by["cell"]["value"] == "(7, 21)"
    w = by["cell"]["words"]
    assert w.startswith("the map is not read from the minimap: no minimap picture")
    assert "look at the game -- is she on xmas_dun02?" in w
    assert "the runner refuses a start that cannot tell" in w
    assert screen.calls.count("grab_meta") >= 2  # it read frames for PLAYER_MAP_S, no more
