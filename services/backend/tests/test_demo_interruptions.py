"""scripts/demo_interruptions.py: attempts a human interrupted are marked, never scored (Batt,
2026-10-07); the input log is read from its END in chunks (CLAUDE.md rule 5)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from poring_env.demo import Action, DemoLog, DemoRecord, Intended

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
SID = "20261007T140603-demo-window-alone-indoor"
T = 900_000_000_000_000
S = 10**9


@pytest.fixture(scope="module")
def di() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "demo_interruptions", SCRIPTS / "demo_interruptions.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["demo_interruptions"] = mod
    spec.loader.exec_module(mod)
    return mod


def write_log(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def test_human_events_are_found_from_the_end_in_small_chunks(
    di: ModuleType, tmp_path: Path
) -> None:
    log = tmp_path / "2026-10-07.jsonl"
    entries = [
        {"t_mono_ns": T + i * S, "source": "agent", "event": {"type": "key"}} for i in range(200)
    ]
    entries[50] = {"t_mono_ns": T + 50 * S, "source": "human", "event": {"type": "release_all"}}
    entries[150] = {"t_mono_ns": T + 150 * S, "source": "human", "event": {"type": "release_all"}}
    entries[190] = {"t_mono_ns": T + 190 * S, "source": "human", "event": {"type": "key"}}
    write_log(log, entries)
    got = di.human_events(log, T + 100 * S, T + 195 * S, chunk=300)  # tiny chunks: partial lines
    assert got == [(T + 150 * S, "release_all"), (T + 190 * S, "key")]
    assert di.human_events(log, T, T + 60 * S, chunk=300) == [(T + 50 * S, "release_all")]


def test_the_touched_attempt_and_the_next_are_marked(di: ModuleType, tmp_path: Path) -> None:
    log = DemoLog(SID, root=tmp_path)
    ids = []
    for i in range(5):
        log.append(
            DemoRecord(
                session=SID,
                actor="rule:harness@1",
                t_mono_ns=T + i * 10 * S - S,
                cue="close",
                action=Action(type="menu_shortcut", intended=Intended(kind="window")),
            )
        )
        rec = log.append(
            DemoRecord(
                session=SID,
                actor="rule:open_window@1",
                t_mono_ns=T + i * 10 * S,
                cue="t",
                action=Action(type="menu_shortcut", intended=Intended(kind="window")),
            )
        )
        ids.append(rec.record_id)
    marks = di.interrupted(log.dir, [(T + 23 * S, "release_all")])
    assert sorted(marks) == sorted([ids[2], ids[3]])  # attempt 2's span, and attempt 3
    assert "attempt 2" in marks[ids[2]]
    assert di.interrupted(log.dir, [(T + 45 * S, "release_all")]) == {
        ids[4]: f"human release_all at mono {T + 45 * S} (attempt 4)"
    }  # the last attempt has no next
