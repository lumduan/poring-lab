"""scripts/slot_items.py + dungeon_hunt's start (dungeon@9.47; matpilot's review 2026-11-13, round
15 #1): WHICH ITEM a hotbar slot shows, read from its icon's pixels, and a player's start that
refuses BEFORE ANY INPUT when a role's key shows another item. Synthetic icons only: the client's
item pictures are client-derived (data/slot_items/, never in git)."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import hotbar_count as hb  # noqa: E402
import slot_items as si  # noqa: E402

SRC = (ROOT / "scripts" / "dungeon_hunt.py").read_text()
TREE = ast.parse(SRC)
KEY = (255, 0, 255)


def icon(seed: int) -> np.ndarray:
    """A SYNTHETIC 24 x 24 item bitmap: a key-colour border, random 6 px blocks inside."""
    rng = np.random.default_rng(seed)
    img = np.zeros((24, 24, 3), np.uint8)
    img[:] = KEY
    img[3:21, 3:21] = np.kron(rng.integers(0, 200, (3, 3, 3), dtype=np.uint8),
                              np.ones((6, 6, 1), np.uint8))  # fmt: skip
    return img


def twin(base: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    """``base`` with one 5 x 5 patch recoloured: two potions that differ only in the liquid."""
    out = base.copy()
    out[8:13, 8:13] = colour
    return out


POTION = icon(1)
NAMES = {504: "White Potion", 601: "Fly Wing", 602: "Butterfly Wing", 1201: "Knife",
         1202: "Knife", 529: "Candy", 530: "Candy Cane", 505: "Blue Potion"}  # fmt: skip
ICONS = {504: POTION, 601: icon(2), 602: icon(3), 1201: icon(4), 1202: icon(4), 529: icon(5),
         530: icon(6), 505: twin(POTION, (20, 40, 230))}  # fmt: skip


def refs() -> si.SlotRefs:
    return si.SlotRefs.from_icons(ICONS, NAMES)


def frame_with(slots: dict[int, np.ndarray | str], bg: int = 120) -> np.ndarray:
    """A BGR game-region frame: each slot's square drawn as the client draws it (the icon over the
    white face; "empty": the white face alone)."""
    f = np.full((720, 1280, 3), bg, np.uint8)
    for s, what in slots.items():
        x, y = si.ICON_ORIGIN[0] + hb.PITCH * s, si.ICON_ORIGIN[1]
        sq = np.full((24, 24, 3), 255.0) if isinstance(what, str) else si.composite(what)
        f[y : y + 24, x : x + 24] = sq[..., ::-1].astype(np.uint8)
    return f


def no_digits(monkeypatch: pytest.MonkeyPatch, counts: dict[int, int | None]) -> None:
    """hotbar_count's digit read faked by slot (its templates are client pixels, never in git)."""
    monkeypatch.setattr(hb, "read_count", lambda gray, slot, tpl: counts.get(slot))


# --- (a) the reader ------------------------------------------------------------------------------


def test_each_icon_is_named_where_the_client_draws_it(monkeypatch: pytest.MonkeyPatch) -> None:
    no_digits(monkeypatch, {0: 10, 3: 1, 6: 4, 7: 10, 8: 3})
    f = frame_with({0: POTION, 3: ICONS[1201], 6: ICONS[529], 7: ICONS[601], 8: ICONS[602]})
    r = refs()
    got = {s: si.read_slot(f, s, r) for s in (0, 3, 6, 7, 8)}
    assert {s: g.name for s, g in got.items()} == {0: "White Potion", 3: "Knife", 6: "Candy",
                                                   7: "Fly Wing", 8: "Butterfly Wing"}  # fmt: skip
    assert all(g.state == "item" and g.dist == 0.0 for g in got.values())
    assert got[3].ids == (1201, 1202)  # one picture, two ids: a copy group
    assert got[0].why.startswith("F1 shows a White Potion")
    # one pixel off reads worse than the bar: the origin is the measured one, not a search
    shifted = np.roll(f, 1, axis=1)
    assert si.read_slot(shifted, 7, r).dist > si.read_slot(f, 7, r).dist


def test_two_potions_that_differ_only_in_the_liquid(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole square tells them apart by little; the pixels that differ decide (the rival
    test). A liquid half covered (a cursor, a damage number) is "cannot tell", never the other."""
    no_digits(monkeypatch, {0: 10, 1: 10, 2: 10})
    covered = POTION.copy()
    covered[8:13, 8:13] = (np.asarray(POTION[10, 10], int) + (20, 40, 230)) // 2
    f = frame_with({0: POTION, 1: ICONS[505], 2: covered})
    r = refs()
    white, blue, half = (si.read_slot(f, s, r) for s in (0, 1, 2))
    assert (white.name, blue.name) == ("White Potion", "Blue Potion")
    assert white.next_dist is not None and white.next_dist < 20  # close as whole squares ...
    assert white.pair_lead is not None and white.pair_lead >= si.PAIR_LEAD  # ... apart here
    assert half.state == "unread" and "two items alike" in half.why


def test_empty_dark_flat_and_unknown_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    no_digits(monkeypatch, {0: 0, 1: 0, 2: 7, 3: 5})
    f = frame_with({0: "empty", 2: icon(99)})  # slot 1: the flat grey of a load screen
    f[4:28, 246 + 3 * 29 : 270 + 3 * 29] = 10  # slot 3: a teleport's dark frame
    r = refs()
    e, flat, unknown, dark = (si.read_slot(f, s, r) for s in range(4))
    assert e.state == "empty" and e.why == "F1 is empty"
    assert flat.state == "unread" and "no hotbar slot is drawn" in flat.why  # not "empty"
    assert unknown.state == "unread" and "matches no known item" in unknown.why
    assert dark.state == "unread" and "dark" in dark.why
    assert si.read_slot(f[:20], 0, r).state == "unread"  # outside the frame


def test_shows_is_right_wrong_empty_or_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    no_digits(monkeypatch, {0: 10, 1: 0, 2: 10})
    f = frame_with({0: POTION, 1: "empty", 2: icon(77)})
    r = refs()
    potion, empty, unknown = (si.read_slot(f, s, r) for s in range(3))
    assert si.shows(potion, [504]) == "right" and si.shows(potion, [601]) == "wrong"
    assert si.shows(empty, [601]) == "empty" and si.shows(unknown, [601]) == "unknown"
    assert si.shows(None, [601]) == "unknown"


def test_a_slot_is_read_again_until_it_is_decisive(monkeypatch: pytest.MonkeyPatch) -> None:
    no_digits(monkeypatch, {0: 10, 7: 10})
    dark = frame_with({})
    dark[:] = 5
    frames = [dark, frame_with({0: POTION, 7: ICONS[601]})]
    got, n = si.read_slots_until(lambda: frames.pop(0) if len(frames) > 1 else frames[0],
                                 [0, 7], refs(), wait_s=2.0, poll_s=0.0)  # fmt: skip
    assert n == 2 and got[0].name == "White Potion" and got[7].name == "Fly Wing"


def test_the_references_round_trip_and_the_table_parses(tmp_path: Path) -> None:
    r = refs()
    p = tmp_path / "refs.npz"
    r.save(p)
    back = si.SlotRefs.load(p)
    assert back.ids == r.ids and back.names == r.names and np.array_equal(back.rgb, r.rgb)
    assert back.has(504) and back.picture_of(1202) == back.picture_of(1201)
    assert back.name(999) == "item 999"
    table = "// a comment\n504#potion_w#\n504#again#\nbad line\n601#wing#\n"
    assert si.parse_table(table) == {504: "potion_w", 601: "wing"}
    big = np.zeros((25, 24, 3), np.uint8)
    assert si.fit_square(big) is None
    small = si.fit_square(np.zeros((20, 20, 3), np.uint8))
    assert small is not None and si.transparent(small)[20:].all()
    with pytest.raises(ValueError):
        si.SlotRefs.from_icons({1: np.full((24, 24, 3), KEY, np.uint8)})  # nothing drawn
    np.savez(tmp_path / "old.npz", meta=np.array('{"format": 0}'))
    with pytest.raises(ValueError, match="rebuild"):
        si.SlotRefs.load(tmp_path / "old.npz")


def test_the_compared_pixels_leave_out_the_count_and_the_top_line() -> None:
    keep = si.COMPARE
    assert not keep[0].any()  # the slot frame's top line
    ox, oy = si.ICON_ORIGIN
    assert not keep[hb.Y0 - oy :, hb.X0 - ox :].any()  # the count's digits (lower right)
    assert keep[1 : hb.Y0 - oy, :].all() and keep[:, : hb.X0 - ox][1:].all()


# --- (b) the runner's words and rules ------------------------------------------------------------


def _read(monkeypatch: pytest.MonkeyPatch, what: np.ndarray | str, count: int = 10) -> Any:
    no_digits(monkeypatch, {0: 0 if isinstance(what, str) else count})
    return si.read_slot(frame_with({0: what}), 0, refs())


def test_the_role_words(monkeypatch: pytest.MonkeyPatch) -> None:
    r = refs()
    right = dh.slot_role_state("fly", "F1", _read(monkeypatch, ICONS[601]), r)
    assert right == ("right", "F1 shows a Fly Wing (read from its icon)")
    wrong = dh.slot_role_state("fly", "F1", _read(monkeypatch, POTION), r)
    assert wrong == ("wrong", "F1 shows a White Potion, not a Fly Wing: set the Fly Wing's key "
                     "to the Fly Wing's slot")  # fmt: skip
    st, w = dh.slot_role_state("opener", "F1", _read(monkeypatch, POTION), r)
    assert st == "wrong" and w.startswith("F1 shows a White Potion, not the Knife")
    assert dh.slot_role_state("home", "F1", _read(monkeypatch, "empty"), r) == (
        "empty",
        "F1 is empty",
    )
    st, w = dh.slot_role_state("potion", "F1", _read(monkeypatch, icon(55)), r)
    assert st == "unknown" and w.startswith("cannot tell whether F1 shows a White Potion")
    st, w = dh.slot_role_state("fly", "F8", None, None)
    assert st == "unknown" and "slot_items.py build --decode-mixcrypt" in w
    assert dh.SLOT_ROLES["fly"].items == (dh.STOCK_ITEMS["fly"],)
    assert dh.SLOT_ROLES["potion"].items == (dh.STOCK_ITEMS["potion"],)
    assert dh.SLOT_ROLES["home"].items == (dh.PLAYER_HOME_ITEM,)
    assert {dh.SLOT_ROLES[k].items[0] for k in ("cane", "candy")} == set(
        dh.HEAL_CANDY_ITEMS.values()
    )


def test_another_item_always_refuses_and_cannot_tell_by_the_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok = {"fly": ("right", "F8 shows a Fly Wing"), "cane": ("empty", "F6 is empty")}
    assert dh.player_slots_refused(ok) is None  # an empty slot is the count rules'
    wrong = {**ok, "potion": ("wrong", "F1 shows a Fly Wing, not a White Potion: ...")}
    assert dh.player_slots_refused(wrong) == "F1 shows a Fly Wing, not a White Potion: ..."
    unknown = {**ok, "home": ("unknown", "cannot tell whether F9 shows a Butterfly Wing (x)")}
    assert dh.PLAYER_SLOT_UNREAD == "refuse"  # the recorded frames' decision (player-mode.md)
    why = dh.player_slots_refused(unknown)
    assert why is not None and why.endswith(f"within {dh.PLAYER_SLOT_S} s: a person first")
    assert dh.player_slots_warning(unknown) is None
    monkeypatch.setattr(dh, "PLAYER_SLOT_UNREAD", "warn")
    assert dh.player_slots_refused(unknown) is None
    assert (dh.player_slots_warning(unknown) or "").startswith("WARNING: --player-mode: cannot")
    assert dh.player_slots_refused({**unknown, **wrong}) is not None  # another item still refuses


def test_the_roles_read_at_a_start() -> None:
    keys = {"potion": "F1", "fly": "F8", "home": "F9", "equip": "F5", "sit": "Insert",
            "cane": "F6", "candy": "F7"}  # fmt: skip
    assert dh.slot_role_keys(keys, False, None, False) == {"fly": "F8", "potion": "F1",
                                                           "home": "F9"}  # fmt: skip
    assert dh.slot_role_keys(keys, True, "F4", True) == {
        "fly": "F8",
        "potion": "F1",
        "home": "F9",
        "cane": "F6",
        "candy": "F7",
        "opener": "F4",
    }
    no_home = {k: v for k, v in keys.items() if k != "home"}
    assert "home" not in dh.slot_role_keys(no_home, False, "F4", False)  # no --bare-steal: no Knife


# --- (c) the start: before any input -------------------------------------------------------------


class SlotScreen:
    """A screen that can only be grabbed (and closed)."""

    def __init__(self, img: np.ndarray) -> None:
        self.calls: list[str] = []
        self.img = np.concatenate([img, np.full(img.shape[:2] + (1,), 255, np.uint8)], axis=2)

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        self.calls.append("grab_meta")
        return 1, self.img[y : y + h, x : x + w], -1, "x11"

    def close(self) -> None:
        self.calls.append("close")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the slot read asked the screen for {name!r}")


def _no_input(monkeypatch: pytest.MonkeyPatch, img: np.ndarray) -> SlotScreen:
    import ro_agent as r

    screen = SlotScreen(img)

    def no_session(*_: Any, **__: Any) -> Any:
        raise AssertionError("a session was opened")

    class NoAgent:
        def __init__(self, *_: Any, **__: Any) -> None:
            raise AssertionError("an Agent was made")

    monkeypatch.setattr(r, "session", no_session)
    monkeypatch.setattr(r, "Agent", NoAgent)
    monkeypatch.setattr(r, "Screen", lambda: screen)
    monkeypatch.setattr(dh, "PLAYER_SLOT_S", 0.3)
    return screen


REGION = (0, 0, 1280, 720)
LIVE = {0: POTION, 3: ICONS[1201], 4: "empty", 7: ICONS[601], 8: ICONS[602]}  # 2026-11-13's bar
COUNTS = {0: 10, 3: 1, 4: 0, 7: 10, 8: 3}
ROLES = {"fly": "F8", "potion": "F1", "home": "F9", "opener": "F4"}


def test_the_start_refuses_a_wrong_key_before_any_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """matpilot's case: the Fly Wing's key on F1, the White Potions' slot."""
    no_digits(monkeypatch, COUNTS)
    screen = _no_input(monkeypatch, frame_with(LIVE))
    with pytest.raises(SystemExit) as exc:
        dh.player_start_slots({**ROLES, "fly": "F1", "potion": "F8"}, refs(), REGION)
    assert str(exc.value) == (
        "dungeon@9.47 refused: --player-mode: F1 shows a White Potion, not a Fly Wing: set the "
        "Fly Wing's key to the Fly Wing's slot; F8 shows a Fly Wing, not a White Potion: set the "
        "heal item's key to the White Potion's slot")  # fmt: skip
    assert set(screen.calls) == {"grab_meta", "close"} and screen.calls[-1] == "close"


def test_the_start_goes_on_with_every_role_on_its_item(monkeypatch: pytest.MonkeyPatch) -> None:
    no_digits(monkeypatch, COUNTS)
    screen = _no_input(monkeypatch, frame_with(LIVE))
    rec = dh.player_start_slots(ROLES, refs(), REGION)
    assert {k: v["verdict"] for k, v in rec.items()} == dict.fromkeys(ROLES, "right")
    assert rec["fly"]["key"] == "F8" and rec["fly"]["read"]["name"] == "Fly Wing"
    assert screen.calls == ["grab_meta", "close"]  # its first frame was decisive


def test_a_start_that_cannot_tell_refuses_or_warns_by_the_rule(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    no_digits(monkeypatch, COUNTS)
    _no_input(monkeypatch, frame_with({**LIVE, 7: icon(42)}))  # F8: no known item's icon
    with pytest.raises(SystemExit, match="cannot tell whether F8 shows a Fly Wing"):
        dh.player_start_slots(ROLES, refs(), REGION)
    monkeypatch.setattr(dh, "PLAYER_SLOT_UNREAD", "warn")
    rec = dh.player_start_slots(ROLES, refs(), REGION)
    assert rec["fly"]["verdict"] == "unknown" and rec["fly"]["read"]["state"] == "unread"
    assert "WARNING: --player-mode: cannot tell whether F8" in capsys.readouterr().out


def test_no_references_refuse_with_the_build_command(monkeypatch: pytest.MonkeyPatch) -> None:
    screen = _no_input(monkeypatch, frame_with(LIVE))
    with pytest.raises(SystemExit, match="slot_items.py build"):
        dh.player_start_slots(ROLES, None, REGION)
    assert "grab_meta" not in screen.calls  # no references: no frame is even read
    assert dh.load_slot_refs(Path("/nonexistent/refs.npz")) is None


def _func(name: str) -> ast.FunctionDef:
    (f,) = [n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name]
    return f


def _call_name(call: ast.Call) -> str | None:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def test_the_slots_are_read_after_the_check_and_before_the_session() -> None:
    run_src = ast.get_source_segment(SRC, _func("run")) or ""
    i_ck = run_src.index('if getattr(a, "cmd", "run") == "check":')
    i_ret = run_src.index("return 0", i_ck)
    i_map = run_src.index("map_read = player_start_map(")
    i_slot = run_src.index("slot_read = (player_start_slots(slot_roles, slot_refs, ")
    assert i_ret < i_map < i_slot < run_src.index("out.mkdir(") < run_src.index("with r.session(")
    assert run_src.index("slot_refs = load_slot_refs() if player else None") < i_ck
    assert "slot_refs=slot_refs" in run_src[i_ck:i_ret]  # the check reads with the same ones
    no_input = {"session", "Agent", "keys", "key", "click", "move", "press", "ensure_clear",
                "select_tab", "typed_line", "send", "send_many"}  # fmt: skip
    for name in ("player_start_slots", "read_role_slots", "slot_role_state",
                 "player_slots_refused", "slot_role_keys"):  # fmt: skip
        calls = {_call_name(n) for n in ast.walk(_func(name)) if isinstance(n, ast.Call)}
        assert not calls & no_input, (name, calls & no_input)
    assert "Screen" in {_call_name(n) for n in ast.walk(_func("player_start_slots"))
                        if isinstance(n, ast.Call)}  # fmt: skip


def test_the_record_and_the_version() -> None:
    import runner_flow_export as rfe

    base = {"plant_sweep": False, "box_ignore": 2, "ag_match": 40.0, "walk_trust": True,
            "rest": "spot", "npc_guard": True, "miss_cue": False}  # fmt: skip
    on = dh.fixes_of(dh.argparse.Namespace(**base, player_mode=True))
    assert on["player_slots"] == [si.NAME_MAX, si.PAIR_LEAD, dh.PLAYER_SLOT_S,
                                  dh.PLAYER_SLOT_UNREAD, "9.47"]  # fmt: skip
    assert "player_slots" not in dh.fixes_of(dh.argparse.Namespace(**base))
    i_start = SRC.index('ev({"kind": "run_start", "strategy": a.strategy')
    assert '**({"player_slots": slot_read} if player else {}),' in SRC[i_start:]
    assert dh.SLOT_ITEMS_VERSION == "9.47" and dh.VERSION == "dungeon@8.7"
    assert rfe.feature_version(dh) == "dungeon@9.53"  # the fast alarm (live-blocks 11.2)
