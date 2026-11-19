"""Who may play a Run (Batt 2026-11-18, ADR-0020 Amendment Q): "no need to lock the character's
name: a user should be free to create a character; teaching many at once, the same name for all
would confuse". ➡️ 2026-11-19 (Amendment R, Batt): "any the default, this machine too, and settable
in Settings ... on Settings, Save and it works at once": the mode and the characters a Run knows
live in the Settings page's store (settings/run-identity.json, poring_env.runidentity), read at
every check; no file = any; a GM line always proves the lab's own character."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from poring_env import runidentity as ri

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import crusader as cr  # noqa: E402
import flow_run as fr  # noqa: E402


@pytest.fixture()
def r() -> Any:
    """The ro_agent crusader imports when called (another test may have swapped the module)."""
    import importlib

    return importlib.import_module("ro_agent")


@pytest.fixture()
def store_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This test's Settings store (no file yet: the default)."""
    f = tmp_path / "settings" / ri.FILE_NAME
    f.parent.mkdir()
    monkeypatch.setattr(cr, "IDENTITY_FILE", f)
    return f


def char(cid: str, name: str, plate: Any) -> ri.Character:
    a = np.asarray(plate).astype(np.uint8)
    return ri.Character(id=cid, name=name, remembered="2026-11-19T01:00:00+00:00", w=a.shape[1],
                        h=a.shape[0], rgb=a.tobytes())  # fmt: skip


def save(f: Path, mode: str, *chars: ri.Character) -> None:
    f.write_text(ri.dumps(ri.Store(revision=1, mode=mode, characters=tuple(chars))))


def name_line(seed: int) -> Any:
    """A name line: dark ground, bright letters in a place of its own (int16, as crop gives)."""
    plate = np.zeros((ri.PLATE_H, ri.PLATE_W, 3), np.int16)
    plate[2:10, 5 + 20 * seed : 35 + 20 * seed] = 200
    return plate


def client_with(plate: Any) -> Any:
    """A client frame whose Basic Info name line (NAME_BOX) shows ``plate``."""
    return np.pad(plate, ((22, 0), (4, 0), (0, 0))).astype(np.uint8)


@pytest.fixture()
def no_refs(monkeypatch: pytest.MonkeyPatch, r: Any) -> list[str]:
    """A learner's install: no reference pictures of the lab's character (load_refs fails)."""
    calls: list[str] = []

    def missing(char: str = "crusader") -> Any:
        calls.append(char)
        raise FileNotFoundError(f"data/{char}/char.json")

    monkeypatch.setattr(cr, "load_refs", missing)
    monkeypatch.setattr(r, "black", lambda screen: False)
    return calls


# -- the store ------------------------------------------------------------------------------------


def test_no_file_is_any_with_nobody_remembered_every_install_and_the_lab(store_file: Path) -> None:
    assert not store_file.exists()
    assert cr.identity_store() == ri.DEFAULT and ri.DEFAULT.mode == ri.DEFAULT_MODE == "any"
    assert cr.run_identity() == "any" and cr.known_names() == []


def test_the_mode_is_read_at_every_check_no_restart(store_file: Path) -> None:
    save(store_file, "known")
    assert cr.run_identity() == "known"
    save(store_file, "any")  # a Save on the page: the very next read sees it
    assert cr.run_identity() == "any"


def test_an_unreadable_store_fails_every_run_in_words_never_falls_back_to_any(
    store_file: Path, no_refs: list[str], r: Any
) -> None:
    store_file.write_text('{"v": 1, "revision": 2, "mode": "anyone", "characters": []}')
    assert cr.run_identity() == cr.UNREADABLE
    got = cr.check(object(), "rogue", "thief", db=False)
    assert got["ok"] is False and "cannot be read" in got["why"] and "Settings page" in got["why"]
    assert "anyone" in got["why"]  # the problem in words


def test_the_store_parses_strictly() -> None:
    good = ri.Store(revision=3, mode="known", characters=(char("c_0000000a", "โร้ก", name_line(0)),))
    assert ri.parse(ri.dumps(good)) == good  # round trip, Thai name kept
    raw = json.loads(ri.dumps(good))
    for bad, words in (
        ({**raw, "v": 2}, "version"),
        ({**raw, "extra": 1}, "extra"),
        ({**raw, "mode": "all"}, "none of"),
        ({**raw, "revision": -1}, "revision"),
    ):
        assert words in str(ri.parse(json.dumps(bad)))  # fmt: skip
    first = raw["characters"][0]
    twice = {**raw, "characters": [first, {**first, "id": "c_0000000b", "name": "โร้ก"}]}
    assert "twice" in str(ri.parse(json.dumps(twice)))
    short = {**raw, "characters": [{**first, "rgb": base64.b64encode(b"12").decode()}]}
    assert "RGB" in str(ri.parse(json.dumps(short)))
    assert ri.parse("{") == "not JSON"


def test_a_name_is_any_script_but_no_control_character() -> None:
    assert ri.name_problem("Rogue76bd") is None and ri.name_problem("도적") is None
    assert ri.name_problem("") == "name_empty" and ri.name_problem(" a") == "name_spaces_at_ends"
    assert ri.name_problem("x" * 25) == "name_too_long" and ri.name_problem("ก" * 24) is None
    assert ri.name_problem("a\nb") == "name_control_character"
    assert ri.same_name("Rogue76BD", "rogue76bd")


# -- the modes ------------------------------------------------------------------------------------


def test_any_character_plays_a_run_without_any_reference_picture(
    store_file: Path, no_refs: list[str]
) -> None:
    got = cr.check(object(), "rogue", "thief", db=False)  # no file: any
    assert got["ok"] is True and got["who"] == "any" and no_refs == []
    save(store_file, "any")
    assert cr.check(object(), "swordman", "nobody", db=False)["ok"] is True


def test_any_still_fails_a_black_game_region(
    store_file: Path, monkeypatch: pytest.MonkeyPatch, no_refs: list[str], r: Any
) -> None:
    monkeypatch.setattr(r, "black", lambda screen: True)
    got = cr.check(object(), "rogue", "thief", db=False)
    assert got["ok"] is False and "black" in got["why"]


def test_mine_without_the_labs_pictures_refuses_in_words_and_a_gm_line_still_compares(
    store_file: Path, monkeypatch: pytest.MonkeyPatch, no_refs: list[str], r: Any
) -> None:
    save(store_file, "mine")
    got = cr.check(object(), "rogue", "thief", db=False)
    assert got["ok"] is False and "no reference pictures" in got["why"] and "Settings" in got["why"]
    save(store_file, "any")
    monkeypatch.setattr(r, "online_chars", lambda which: ["Thief8fce"])
    with pytest.raises(FileNotFoundError):  # db=True: a GM line's check, whatever the page says
        cr.check(object(), "rogue", "thief", db=True)
    assert no_refs == ["thief", "thief"]


def test_known_plays_only_a_remembered_character_and_refuses_another_servers(
    store_file: Path, monkeypatch: pytest.MonkeyPatch, r: Any
) -> None:
    """Batt 2026-11-18 ~22:1x: a Run was pressed twice on rog101, a character of another server;
    under known only the characters remembered on the Settings page play."""
    save(store_file, "known", char("c_0000000a", "Thief8fce", name_line(0)),
         char("c_0000000b", "Rogue5a3c", name_line(2)))  # fmt: skip
    chars = cr.known_chars()
    assert [n for _, n, _ in chars] == ["Thief8fce", "Rogue5a3c"]
    assert cr.known_match(client_with(name_line(0)), chars)["who"] == "Thief8fce"
    got = cr.known_match(client_with(name_line(2)), chars)
    assert got["ok"] and got["who"] == "Rogue5a3c"
    rog101 = name_line(1) // 2 + 30  # another server's character: no picture here
    got = cr.known_match(client_with(rog101), chars)
    assert got["ok"] is False and got["who"] is None and got["known"] == ["Thief8fce", "Rogue5a3c"]
    assert cr.known_match(client_with(name_line(0)), [])["ok"] is False  # nobody remembered
    monkeypatch.setattr(r, "black", lambda screen: False)
    monkeypatch.setattr(cr, "client_frame", lambda screen: client_with(name_line(2)))
    assert cr.check(object(), "rogue", "thief", db=False)["who"] == "Rogue5a3c"
    monkeypatch.setattr(cr, "client_frame", lambda screen: client_with(rog101))
    assert cr.check(object(), "rogue", "thief", db=False)["ok"] is False


def test_known_words_name_the_remembered_characters() -> None:
    assert cr.known_words(True, ["Thief8fce", "Rogue5a3c"]).startswith(
        "a character remembered on this install (its name line is one of: Thief8fce, Rogue5a3c)"
    )
    no = cr.known_words(False, ["Thief8fce"])
    assert "none of the characters remembered here (Thief8fce)" in no and "another server" in no
    assert "press Remember" in cr.known_words(False, [])


# -- the check's words and the helper's status ---------------------------------------------------


def test_the_check_line_says_any_character_not_the_labs_name() -> None:
    items = [{"id": "identity", "ok": True, "words": "the name plate reads Thief8fce and the job "
              "rogue (her references; no DB, as the player start)", "value": "Thief8fce, rogue"},
             {"id": "chat", "ok": True, "words": "the chat input is closed"}]  # fmt: skip
    line = fr.CHECK_MARK + json.dumps({"items": items, "ok": True})
    got = fr.parse_check_output(line, "any")
    ident = got["items"][0]
    assert ident["ok"] is True and "Thief8fce" not in json.dumps(ident)
    assert ident["words"] == cr.IDENTITY_ANY_WORDS and ident["value"] == "any character"
    assert "Settings page" in cr.IDENTITY_ANY_WORDS and "RUN_IDENTITY" not in cr.IDENTITY_ANY_WORDS
    assert fr.parse_check_output(line, "mine")["items"][0]["value"] == "Thief8fce, rogue"
    black = [{"id": "identity", "ok": False, "words": "the game region is black"}]
    still = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": black}), "any")
    assert still["items"][0]["ok"] is False  # a failure is never relabelled a pass


def test_a_run_log_reads_its_check_in_the_mode_it_started_with() -> None:
    rl = fr.RunLog(identity="any")
    items = [{"id": "identity", "ok": True, "words": "the name plate reads Thief8fce"}]
    rl.feed(fr.CHECK_MARK + json.dumps({"items": items, "ok": True}) + "\n")
    assert rl.check is not None and rl.check["items"][0]["value"] == "any character"


def test_the_helper_shows_the_mode_from_the_settings_page(tmp_path: Path, store_file: Path) -> None:
    h = tmp_path / "flowrun"
    h.mkdir()
    assert fr.Helper(h).status()["identity"] == "any"  # no file
    save(store_file, "known")
    assert fr.Helper(h).status()["identity"] == "known"
    store_file.write_text("{")
    assert fr.Helper(h).status()["identity"] == "unreadable"


def test_the_check_line_under_known_says_known_not_the_labs_name(store_file: Path) -> None:
    save(store_file, "known", char("c_0000000a", "Thief8fce", name_line(0)),
         char("c_0000000b", "Rogue5a3c", name_line(2)))  # fmt: skip
    items = [{"id": "identity", "ok": False, "words": "the name plate is not Thief8fce's (52 "
              "pixels differ): another character, or a window over it"}]  # fmt: skip
    got = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": items}), "known")
    assert got["items"][0]["ok"] is False and "another server" in got["items"][0]["words"]
    assert "Rogue5a3c" in got["items"][0]["words"]
    items[0].update(ok=True, words="the name plate reads Thief8fce")
    got = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": items}), "known")
    assert got["items"][0]["value"] == "a known character"


def test_no_env_word_is_read_any_more(
    store_file: Path, monkeypatch: pytest.MonkeyPatch, r: Any
) -> None:
    """.env's RUN_IDENTITY is retired (Amendment R): a leftover line changes nothing."""
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "mine"})
    assert cr.run_identity() == "any"
    assert not hasattr(cr, "IDENTITY_ENV") and not hasattr(cr, "identity_mode")


# -- Remember: the name line of the character on screen ------------------------------------------


def test_a_name_line_must_hold_still_and_show_letters() -> None:
    a = name_line(0)
    assert cr.plate_verdict(a, a.copy()) is None
    moved = a.copy()
    moved[2:10, 60:90] = 250  # the scene moved under it: no window there
    assert "changed between two looks" in str(cr.plate_verdict(a, moved))
    blank = np.full_like(a, 90)
    assert "blank" in str(cr.plate_verdict(blank, blank.copy()))


def test_read_plate_looks_twice_and_names_a_character_already_remembered(
    store_file: Path, monkeypatch: pytest.MonkeyPatch, r: Any
) -> None:
    monkeypatch.setattr(r, "away_now", lambda screen: None)
    monkeypatch.setattr(r, "black", lambda screen: False)
    monkeypatch.setattr(cr, "PLATE_GAP_S", 0.0)
    monkeypatch.setattr(cr, "client_frame", lambda screen: client_with(name_line(1)))
    got = cr.read_plate(object(), ri.DEFAULT)
    assert got["ok"] and got["same_as"] is None and (got["w"], got["h"]) == (116, 14)
    assert ri.plate_problem(got["w"], got["h"], got["rgb"]) is None
    pixels = np.frombuffer(base64.b64decode(got["rgb"]), np.uint8).reshape(14, 116, 3)
    assert np.array_equal(pixels, name_line(1).astype(np.uint8))
    known = ri.Store(revision=1, characters=(char("c_0000000a", "Rogue76bd", name_line(1)),))
    assert cr.read_plate(object(), known)["same_as"] == "Rogue76bd"
    monkeypatch.setattr(r, "away_now", lambda screen: "the taskbar is shown")
    got = cr.read_plate(object(), ri.DEFAULT)
    assert got["ok"] is False and "not on the screen" in got["why"] and "rgb" not in got


def test_write_plate_is_atomic_and_carries_the_request(tmp_path: Path) -> None:
    out = tmp_path / fr.PLATE_FILE
    cr.write_plate(out, "abc12345", {"ok": False, "why": "x"})
    assert json.loads(out.read_text()) == {"id": "abc12345", "ok": False, "why": "x"}
    assert [p.name for p in tmp_path.iterdir()] == [fr.PLATE_FILE]


def test_the_helper_takes_a_plate_request_and_nothing_else_with_it() -> None:
    ok = fr.parse_request(json.dumps({"id": "abcdef12", "action": "plate", "at": 1.0}))
    assert ok == {"id": "abcdef12", "action": "plate"}
    extra = json.dumps({"id": "abcdef12", "action": "plate", "flow": "project"})
    assert "nothing else" in str(fr.parse_request(extra))


class FakeProc:
    def __init__(self, rc: int | None) -> None:
        self.rc, self.pid = rc, 999_999

    def poll(self) -> int | None:
        return self.rc

    def wait(self, timeout: float | None = None) -> int:
        return self.rc or -9


def test_a_plate_reader_that_dies_or_hangs_answers_in_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h: Any = fr.Helper(tmp_path)
    h.plate_proc, h.plate_rid, h.plate_t = FakeProc(1), "rid00001", fr.time.monotonic()
    h.plate_tick()
    got = json.loads((tmp_path / fr.PLATE_FILE).read_text())
    assert got == {"id": "rid00001", "ok": False,
                   "why": "the name-line reader ended without a result (rc 1)"}  # fmt: skip
    killed: list[int] = []
    monkeypatch.setattr(fr.os, "killpg", lambda pid, sig: killed.append(pid))
    h.plate_proc, h.plate_rid, h.plate_t = FakeProc(None), "rid00002", -1e9
    h.plate_tick()
    assert killed == [999_999] and h.plate_proc is None
    assert "not read within 15 s" in json.loads((tmp_path / fr.PLATE_FILE).read_text())["why"]
    (tmp_path / fr.PLATE_FILE).write_text(json.dumps({"id": "rid00003", "ok": True}))
    h.plate_proc, h.plate_rid = FakeProc(0), "rid00003"
    h.plate_tick()  # its own result stays for the backend
    assert json.loads((tmp_path / fr.PLATE_FILE).read_text())["ok"] is True


def test_a_plate_request_is_served_even_while_a_run_plays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[str] = []
    h = fr.Helper(tmp_path)
    h.state = "running"
    monkeypatch.setattr(h, "plate_start", lambda rid: started.append(rid))
    h.handle({"id": "rid00004", "action": "plate"})
    assert started == ["rid00004"]


def test_the_plate_file_name_is_the_same_on_both_sides() -> None:
    from poring_backend import routes_identity

    assert routes_identity.PLATE_FILE == fr.PLATE_FILE
    assert routes_identity.PLATE_WAIT_S > fr.PLATE_TIMEOUT_S + fr.POLL_S
    box_w, box_h = cr.NAME_BOX[2] - cr.NAME_BOX[0], cr.NAME_BOX[3] - cr.NAME_BOX[1]
    assert (box_w, box_h) == (ri.PLATE_W, ri.PLATE_H)
