"""Who may play a Run (Batt 2026-11-18, ADR-0020 Amendment Q): "no need to lock the character's
name: a user should be free to create a character; teaching many at once, the same name for all
would confuse". RUN_IDENTITY=any (every install's default) compares no name and no job on a Run's
player path; =mine keeps the name plate check; a GM line always proves the lab's own character."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import crusader as cr  # noqa: E402
import flow_run as fr  # noqa: E402


@pytest.fixture()
def r() -> Any:
    """The ro_agent crusader imports when called (another test may have swapped the module)."""
    import importlib

    return importlib.import_module("ro_agent")


def test_the_mode_any_by_default_mine_on_request_and_a_typo_is_strict() -> None:
    assert cr.identity_mode(None) == "any" and cr.identity_mode("") == "any"
    assert cr.identity_mode("any") == "any" and cr.identity_mode(" MINE ") == "mine"
    assert cr.identity_mode("anyone") == "mine"  # an unknown word never loosens the check


@pytest.fixture()
def no_refs(monkeypatch: pytest.MonkeyPatch, r: Any) -> list[str]:
    """A learner's install: no reference pictures of any character (load_refs fails)."""
    calls: list[str] = []

    def missing(char: str = "crusader") -> Any:
        calls.append(char)
        raise FileNotFoundError(f"data/{char}/char.json")

    monkeypatch.setattr(cr, "load_refs", missing)
    monkeypatch.setattr(r, "black", lambda screen: False)
    return calls


def test_any_character_plays_a_run_without_any_reference_picture(
    monkeypatch: pytest.MonkeyPatch, no_refs: list[str], r: Any
) -> None:
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "any"})
    got = cr.check(object(), "rogue", "thief", db=False)
    assert got["ok"] is True and got["who"] == "any" and no_refs == []
    monkeypatch.setattr(r, "env", lambda: {})  # unset: the same (every install's default)
    assert cr.check(object(), "swordman", "nobody", db=False)["ok"] is True


def test_any_still_fails_a_black_game_region(
    monkeypatch: pytest.MonkeyPatch, no_refs: list[str], r: Any
) -> None:
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "any"})
    monkeypatch.setattr(r, "black", lambda screen: True)
    got = cr.check(object(), "rogue", "thief", db=False)
    assert got["ok"] is False and "black" in got["why"]


def test_mine_and_every_gm_line_still_compare_the_name_plate(
    monkeypatch: pytest.MonkeyPatch, no_refs: list[str], r: Any
) -> None:
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "mine"})
    with pytest.raises(FileNotFoundError):
        cr.check(object(), "rogue", "thief", db=False)
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "any"})
    monkeypatch.setattr(r, "online_chars", lambda which: ["Thief8fce"])
    with pytest.raises(FileNotFoundError):  # db=True: a GM line's check, whatever RUN_IDENTITY says
        cr.check(object(), "rogue", "thief", db=True)
    assert no_refs == ["thief", "thief"]


def test_the_check_line_says_any_character_not_the_labs_name() -> None:
    items = [{"id": "identity", "ok": True, "words": "the name plate reads Thief8fce and the job "
              "rogue (her references; no DB, as the player start)", "value": "Thief8fce, rogue"},
             {"id": "chat", "ok": True, "words": "the chat input is closed"}]  # fmt: skip
    line = fr.CHECK_MARK + json.dumps({"items": items, "ok": True})
    got = fr.parse_check_output(line, "any")
    ident = got["items"][0]
    assert ident["ok"] is True and "Thief8fce" not in json.dumps(ident)
    assert ident["words"] == cr.IDENTITY_ANY_WORDS and ident["value"] == "any character"
    assert fr.parse_check_output(line, "mine")["items"][0]["value"] == "Thief8fce, rogue"
    black = [{"id": "identity", "ok": False, "words": "the game region is black"}]
    still = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": black}), "any")
    assert still["items"][0]["ok"] is False  # a failure is never relabelled a pass


def test_a_run_log_reads_its_check_in_the_mode_it_started_with() -> None:
    rl = fr.RunLog(identity="any")
    items = [{"id": "identity", "ok": True, "words": "the name plate reads Thief8fce"}]
    rl.feed(fr.CHECK_MARK + json.dumps({"items": items, "ok": True}) + "\n")
    assert rl.check is not None and rl.check["items"][0]["value"] == "any character"


def test_the_helper_shows_the_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r: Any) -> None:
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "mine"})
    assert fr.Helper(tmp_path).status()["identity"] == "mine"
    monkeypatch.setattr(r, "env", lambda: {})
    assert fr.Helper(tmp_path).status()["identity"] == "any"


def test_known_plays_only_a_character_this_install_cut_and_refuses_another_servers(
    monkeypatch: pytest.MonkeyPatch, r: Any
) -> None:
    """Batt 2026-11-18 ~22:1x: a Run was pressed twice on rog101, a character of another server;
    under RUN_IDENTITY=known only the characters cut here (init + cut-name) play."""
    import numpy as np

    plate = np.zeros((14, 116, 3), np.int16)
    mine = plate.copy()
    mine[2:10, 5:40] = 200  # Thief8fce's name, as cut
    other = plate.copy()
    other[2:10, 60:100] = 200  # a second known character
    chars = [("thief", "Thief8fce", mine), ("rogue2", "Rogue5a3c", other)]
    assert (
        cr.known_match(np.pad(mine, ((22, 0), (4, 0), (0, 0))).astype(np.uint8), chars)["who"]
        == "Thief8fce"
    )
    got = cr.known_match(np.pad(other, ((22, 0), (4, 0), (0, 0))).astype(np.uint8), chars)
    assert got["ok"] and got["who"] == "Rogue5a3c"
    rog101 = plate.copy()
    rog101[2:10, 20:80] = 120  # another server's character: no reference here
    got = cr.known_match(np.pad(rog101, ((22, 0), (4, 0), (0, 0))).astype(np.uint8), chars)
    assert got["ok"] is False and got["who"] is None and got["known"] == ["Thief8fce", "Rogue5a3c"]
    assert cr.known_match(plate.astype(np.uint8), [])["ok"] is False  # nothing cut: nobody plays
    monkeypatch.setattr(r, "env", lambda: {"RUN_IDENTITY": "known"})
    monkeypatch.setattr(r, "black", lambda screen: False)
    monkeypatch.setattr(cr, "known_chars", lambda: chars)
    monkeypatch.setattr(
        cr, "client_frame", lambda screen: np.pad(other, ((22, 0), (4, 0), (0, 0))).astype(np.uint8)
    )
    assert cr.check(object(), "rogue", "thief", db=False)["who"] == "Rogue5a3c"


def test_known_words_name_the_installs_characters() -> None:
    assert cr.known_words(True, ["Thief8fce", "Rogue5a3c"]).startswith(
        "a character this install knows (its name plate is one of: Thief8fce, Rogue5a3c)"
    )
    no = cr.known_words(False, ["Thief8fce"])
    assert "none of this install's characters (Thief8fce)" in no and "another server" in no
    assert cr.identity_mode("known") == "known"


def test_the_check_line_under_known_says_known_not_the_labs_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cr, "known_names", lambda: ["Thief8fce", "Rogue5a3c"])
    items = [{"id": "identity", "ok": False, "words": "the name plate is not Thief8fce's (52 "
              "pixels differ): another character, or a window over it"}]  # fmt: skip
    got = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": items}), "known")
    assert got["items"][0]["ok"] is False and "another server" in got["items"][0]["words"]
    items[0].update(ok=True, words="the name plate reads Thief8fce")
    got = fr.parse_check_output(fr.CHECK_MARK + json.dumps({"items": items}), "known")
    assert got["items"][0]["value"] == "a known character"
