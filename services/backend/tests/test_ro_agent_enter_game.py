"""ro_agent.enter_game and the REMEMBERED SLOT (2026-11-13): the client re-selects the last slot
played. On the GM account that is usually the Rogue, not the .env character, so ``recover gm``
twice reported "the character never came online" (and relaunched the client once) while the
Rogue was online. ``recover`` now accepts any of the account's characters; every other caller
keeps the strict check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
CHARS = ["Valcd8bd6", "Crus4b7e2", "Thief8fce"]  # the GM account's slots; .env names the first


def load() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("ro_agent", SCRIPTS / "ro_agent.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ro_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


class Screen:
    def full(self) -> None:  # the not-online picture (to_png is stubbed)
        return None


class Agent:
    def __init__(self) -> None:
        self.keys_sent: list[str] = []

    def keys(self, *names: str) -> None:
        self.keys_sent.extend(names)


@pytest.fixture
def ro(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[str]]:
    r = load()
    logged: list[str] = []
    monkeypatch.setattr(r, "account", lambda w: ("user", "pw", CHARS[0]))
    monkeypatch.setattr(r, "account_chars", lambda w: list(CHARS))
    monkeypatch.setattr(r, "online_chars", lambda w: ["Thief8fce"])  # the remembered slot
    monkeypatch.setattr(r, "ensure_window", lambda *a, **k: None)
    monkeypatch.setattr(r, "black", lambda s: False)
    monkeypatch.setattr(r, "ensure_chat_window", lambda *a, **k: logged.append("chat_window"))
    monkeypatch.setattr(r, "log", logged.append)
    monkeypatch.setattr(r, "to_png", lambda *a, **k: None)
    return r, logged


def test_any_char_accepts_the_remembered_rogue(ro: tuple[Any, list[str]]) -> None:
    r, logged = ro
    agent = Agent()
    r.enter_game(agent, Screen(), "gm", any_char=True)
    assert agent.keys_sent == ["Enter"]
    assert any("Thief8fce" in line and "online=1 and drawing" in line for line in logged)
    assert logged[-1] == "chat_window"  # the chat-window check still runs at every entry


def test_default_stays_strict_on_the_env_character(
    ro: tuple[Any, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    r, _ = ro
    monkeypatch.setattr(r.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 50))  # the 40 s wait ends at once
    monkeypatch.setattr(r.time, "monotonic", lambda: float(next(clock)))
    with pytest.raises(r.Stop, match="never came online"):
        r.enter_game(Agent(), Screen(), "gm")  # expects Valcd8bd6; only the Rogue is online


def test_any_char_ignores_a_character_of_another_account(
    ro: tuple[Any, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    r, _ = ro
    monkeypatch.setattr(r, "online_chars", lambda w: ["SomeoneElse"])
    monkeypatch.setattr(r.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 50))
    monkeypatch.setattr(r.time, "monotonic", lambda: float(next(clock)))
    with pytest.raises(r.Stop, match="never came online"):
        r.enter_game(Agent(), Screen(), "gm", any_char=True)


def test_recover_passes_any_char() -> None:
    src = (SCRIPTS / "ro_agent.py").read_text()
    body = src[src.index("def recover(") : src.index("def status(")]
    assert "login(agent, screen, which, any_char=True)" in body
