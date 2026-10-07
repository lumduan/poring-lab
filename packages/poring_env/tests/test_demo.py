"""poring_env.demo: the demonstration log's schema and writer (docs/demonstrations.md)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from poring_env.demo import (
    Action,
    DemoLog,
    DemoRecord,
    FrameRef,
    Intended,
    new_session_id,
    read,
)

SESSION = "20261007T120000-demo-login-anchors"


def rec(**over: object) -> DemoRecord:
    base: dict[str, object] = {
        "session": SESSION,
        "actor": "claude-demo",
        "t_mono_ns": 123,
        "action": Action(type="attack_target", points=[(640.0, 360.0)],
                         intended=Intended(kind="monster", gid=110012875, approx_px=(640, 360))),
        "cue": "the Poring left of the GM, clicked at its body centre",
        "scene": "outdoor:prt_fild08",
    }  # fmt: skip
    base.update(over)
    return DemoRecord(**base)  # type: ignore[arg-type]


def test_a_record_round_trips_and_starts_pending(tmp_path: Path) -> None:
    log = DemoLog(SESSION, root=tmp_path)
    r = log.append(rec(frame=FrameRef(frame_id=7, source="bus", t_capture_ns=99,
                                      ref="snapshots/a.png")))  # fmt: skip
    back = log.records()
    assert back == [r]
    assert back[0].outcome.status == "pending" and back[0].schema_version == 1
    assert json.loads(log.path.read_text())["action"]["intended"]["gid"] == 110012875


@pytest.mark.parametrize("field", ["verdict", "secret"])
def test_unknown_fields_are_refused(field: str) -> None:
    with pytest.raises(ValidationError):
        rec(**{field: 1})


@pytest.mark.parametrize("actor", ["claude-demo", "human", "rule:walk@1", "bot:idle@0.3"])
def test_the_actors_share_one_schema(actor: str) -> None:
    assert rec(actor=actor).actor == actor


@pytest.mark.parametrize("actor", ["claude", "rule:walk", "bot:@1", "rule:walk@1; rm"])
def test_an_unknown_actor_is_refused(actor: str) -> None:
    with pytest.raises(ValidationError):
        rec(actor=actor)


def test_the_cue_is_one_or_two_lines() -> None:
    assert rec(cue="line one\nline two").cue.count("\n") == 1
    with pytest.raises(ValidationError):
        rec(cue="one\ntwo\nthree")


def test_a_record_is_immutable() -> None:
    r = rec()
    with pytest.raises(ValidationError):
        r.cue = "changed"  # type: ignore[misc]


def test_concurrent_appends_never_interleave(tmp_path: Path) -> None:
    log = DemoLog(SESSION, root=tmp_path)

    def write(k: int) -> None:
        for i in range(50):
            log.append(rec(t_mono_ns=k * 1000 + i, cue="x" * 250))

    threads = [threading.Thread(target=write, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    got = read(log.path)
    assert len(got) == 200 and len({r.record_id for r in got}) == 200


def test_snapshots_and_manifest(tmp_path: Path) -> None:
    log = DemoLog(SESSION, root=tmp_path)
    log.start(backend="rdp", lock_seq=191)
    log.start(backend="changed")  # the first t0 and meta are kept
    ref = log.snapshot("before 1/a", b"\x89PNG")
    assert ref == "snapshots/before_1_a.png" and (log.dir / ref).read_bytes() == b"\x89PNG"
    log.finish(records=0)
    man = json.loads((log.dir / "manifest.json").read_text())
    assert man["kind"] == "demo" and man["backend"] == "rdp" and man["records"] == 0
    assert "t1_mono_ns" in man


def test_session_ids_and_records_for_another_session(tmp_path: Path) -> None:
    sid = new_session_id("Login Anchors!")
    assert sid.endswith("-demo-login-anchors")
    with pytest.raises(ValueError):
        DemoLog("../../etc", root=tmp_path)
    with pytest.raises(ValueError):
        DemoLog(SESSION, root=tmp_path).append(rec(session=sid))


def test_an_interrupted_outcome_is_its_own_status() -> None:
    """Batt, 2026-10-07: a human took the lease mid-attempt -> neither pass nor fail."""
    from poring_env.demo import Outcome

    assert Outcome(status="interrupted", cause="human release_all").status == "interrupted"
