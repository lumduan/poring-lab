"""scripts/chat_guard.py, the TYPING GUARD (ADR-0020 #10; Batt 2026-10-09 ~12:15: "Players type
/where once and are done; they don't interleave filler commands"): it REFUSES (and logs) a filler
line, a 3rd identical line in a row, a line inside the minimum interval, a /where inside the retry
interval or over the run's budget; it never waits a line out or inserts another; and ro_agent's
typing and where_fix route through it."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def load(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cg = load("chat_guard")
POL = {"refuse_identical_in_a_row": 3, "where_retry_s": 60, "where_budget_per_run": 4,
       "min_line_interval_s": 0.5}  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def guard(tmp_path: Path) -> Any:
    clock = Clock()
    paths = {"state_path": tmp_path / "s.json", "log": tmp_path / "g.jsonl"}

    def go(text: str, dt: float = 5.0, **kw: Any) -> bool:
        clock.t += dt
        return bool(cg.before_typing(text, pol=POL, clock=clock, **paths, **kw))

    def logged() -> list[dict[str, Any]]:
        return [json.loads(x) for x in paths["log"].read_text().splitlines()]

    return go, clock, paths, logged


def test_the_l2_policy_and_fact_are_recorded() -> None:
    pol = cg.policy()
    assert pol["refuse_identical_in_a_row"] == 3 and pol["no_separators"] is True
    assert pol["where_once_per_need"] is True and pol["where_retry_s"] >= 30


def test_a_filler_separator_is_refused_outright(guard: Any) -> None:
    go, _, _, logged = guard
    with pytest.raises(cg.ChatRefused) as e:
        go("/ex")
    assert e.value.rule == "filler"
    assert logged()[-1]["rule"] == "filler" and logged()[-1]["line"] == "/ex"


def test_a_third_identical_line_in_a_row_is_refused(guard: Any) -> None:
    go, _, _, _ = guard
    assert go("@killmonster2") and go("@killmonster2")
    with pytest.raises(cg.ChatRefused) as e:
        go("@killmonster2")
    assert e.value.rule == "repeat"
    assert go("@heal") and go("@killmonster2")  # another chat line resets it


def test_the_kinds_count_apart(guard: Any) -> None:
    go, _, _, _ = guard
    assert go("@item 909 1") and go("/sit") and go("@item 909 1")  # a slash line does NOT reset
    with pytest.raises(cg.ChatRefused, match="repeat"):
        go("@item 909 1")


def test_skip_mode_returns_false_and_types_nothing(guard: Any) -> None:
    go, _, _, logged = guard
    go("@heal")
    go("@heal")
    assert go("@heal", on_refuse="skip") is False
    assert logged()[-1] == {**logged()[-1], "event": "refused", "rule": "repeat"}


def test_the_minimum_interval_is_refused_not_waited(guard: Any) -> None:
    go, clock, _, _ = guard
    go("@heal")
    t = clock.t
    with pytest.raises(cg.ChatRefused) as e:
        go("@alive", dt=0.2)
    assert e.value.rule == "interval" and clock.t == t + 0.2  # nothing slept


def test_where_once_per_need_then_the_retry_interval_and_the_budget(guard: Any) -> None:
    go, _, paths, logged = guard
    cg.start_run("run-a", 2, state_path=paths["state_path"], log=paths["log"])
    assert go("/where", reason="route_start")
    with pytest.raises(cg.ChatRefused) as e:
        go("/where", dt=10.0, reason="retry")  # a quick retype: refused
    assert e.value.rule == "where_retry"
    assert go("/where", dt=61.0, reason="belief_in_doubt")
    with pytest.raises(cg.ChatRefused) as e:
        go("/where", dt=61.0)  # a 3rd /where in a row: refused whatever the interval (Batt)
    assert e.value.rule == "repeat"
    s = cg.summary(log=paths["log"], run_id="run-a")
    assert s["where"] == 2 and s["where_reasons"] == {"route_start": 1, "belief_in_doubt": 1}
    assert s["refused"] == {"where_retry": 1, "repeat": 1}
    assert [r["event"] for r in logged()][0] == "run_start"


def test_where_over_the_run_budget_is_refused(guard: Any) -> None:
    go, _, paths, _ = guard
    cg.start_run("run-b", 1, state_path=paths["state_path"], log=paths["log"])
    assert go("/where")
    assert go("/sit", dt=61.0)  # (an unrelated slash line; never typed as a separator)
    with pytest.raises(cg.ChatRefused) as e:
        go("/where", dt=61.0)
    assert e.value.rule == "where_budget"
    cg.start_run("run-c", 1, state_path=paths["state_path"], log=paths["log"])
    assert go("/where", dt=61.0)  # a new run, a new budget


def test_free_chat_is_never_logged_with_its_text(guard: Any) -> None:
    go, _, _, logged = guard
    go("hello there")
    go("hello there")
    with pytest.raises(cg.ChatRefused):
        go("hello there")
    assert logged()[-1]["line"] == "<chat>"


def test_a_bad_state_file_starts_fresh(guard: Any) -> None:
    go, _, paths, _ = guard
    paths["state_path"].write_text("{not json")
    assert go("/where")


# --- ro_agent and where_fix route through it ------------------------------------------------
@pytest.fixture
def ro(monkeypatch: pytest.MonkeyPatch) -> Any:
    r = load("ro_agent")
    typed: list[str] = []
    monkeypatch.setattr(r, "open_chat", lambda a, s: None)
    agent = type("A", (), {"type_text": lambda self, t: typed.append(t)})()
    return r, agent, typed


def test_chat_line_types_only_what_the_guard_allows(ro: Any, monkeypatch: pytest.MonkeyPatch
                                                    ) -> None:  # fmt: skip
    r, agent, typed = ro

    def refuse_ex(text: str, **kw: Any) -> bool:
        if text == "/ex":
            raise cg.ChatRefused("filler", "no")
        return True

    monkeypatch.setattr(cg, "before_typing", refuse_ex)
    assert r.chat_line(agent, None, "/where", reason="x")
    with pytest.raises(cg.ChatRefused):
        r.chat_line(agent, None, "/ex")
    assert typed == ["/where\n"]


def test_gm_skips_only_a_repeat(ro: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    r, agent, typed = ro
    rule = {"v": "repeat"}

    def refuse(text: str, **kw: Any) -> bool:
        raise cg.ChatRefused(rule["v"], "no")

    monkeypatch.setattr(cg, "before_typing", refuse)
    monkeypatch.setattr(r, "account", lambda w: (None, None, "gm"))
    monkeypatch.setattr(r, "online_chars", lambda w: {"gm"})
    monkeypatch.setattr(r, "black", lambda s: False)
    monkeypatch.setattr(r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(r, "STATE_DIR", Path("/dev/shm/poring-lab-tmp/test-ro-agent-state"))
    r.gm(agent, None, "@killmonster2")  # a repeat: skipped, no error
    rule["v"] = "interval"
    with pytest.raises(r.Stop):
        r.gm(agent, None, "@warp prt_fild08 1 1")  # anything else stops the caller
    assert typed == []


def test_fix_once_types_one_where_and_never_retypes(monkeypatch: pytest.MonkeyPatch) -> None:
    wf = load("where_fix")
    r = wf.r
    lines: list[str] = []
    areas = iter([np.zeros((10, 10, 3), np.uint8), np.ones((10, 10, 3), np.uint8)])
    monkeypatch.setattr(r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(r, "chat_line", lambda a, s, t, **k: lines.append(t) or True)
    monkeypatch.setattr(wf, "stable_area", lambda s: next(areas))
    monkeypatch.setattr(wf, "text_mask_v2", lambda a: a[..., 0] > 0)
    monkeypatch.setattr(wf, "newest_is_yellow", lambda a: True)
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    walk = np.ones((50, 50), bool)
    monkeypatch.setattr(wf, "parse_v2", lambda a, t: None)  # unparsed: NO retype
    got = wf.fix_once(None, None, {}, (10, 10), walk, reason="route_start")
    assert got["xy"] is None and got["rejects"] == ["unparsed"] and lines == ["/where"]
    areas = iter([np.zeros((10, 10, 3), np.uint8), np.ones((10, 10, 3), np.uint8)])
    monkeypatch.setattr(wf, "stable_area", lambda s: next(areas))
    monkeypatch.setattr(wf, "parse_v2", lambda a, t: (12, 9))
    assert wf.fix_once(None, None, {}, (10, 10), walk, reason="r")["xy"] == (12, 9)
    assert lines == ["/where", "/where"]  # one per call, never two


def test_fix_v2_fails_closed_on_its_refused_separator(monkeypatch: pytest.MonkeyPatch) -> None:
    wf = load("where_fix")
    r = wf.r

    def chat(a: Any, s: Any, text: str, **k: Any) -> bool:
        if text == "/ex":
            raise cg.ChatRefused("filler", "no")
        return True

    monkeypatch.setattr(r, "activate_client", lambda a, s: None)
    monkeypatch.setattr(r, "chat_line", chat)
    monkeypatch.setattr(wf.time, "sleep", lambda s: None)
    got = wf.fix_v2(None, None, {}, (10, 10), np.ones((50, 50), bool))
    assert got["xy"] is None and set(got["rejects"]) == {"guard:filler"}
