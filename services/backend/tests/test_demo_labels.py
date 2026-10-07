"""scripts/demo_labels.py: weak point labels from VERIFIED demo outcomes only (§4)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from poring_env.demo import Action, DemoRecord, FrameRef, Intended, Outcome

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "demo_labels.py"
SID = "20261007T131457-demo-walk-alone-outdoor"
T = 900_000_000_000_000


@pytest.fixture(scope="module")
def dl() -> ModuleType:
    spec = importlib.util.spec_from_file_location("demo_labels", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def rec(i: int, kind: str, status: str, actor: str = "rule:walk@3", gid: int | None = None,
        points: tuple[tuple[float, float], ...] = ((640.0, 300.0),)) -> DemoRecord:  # fmt: skip
    return DemoRecord(
        session=SID,
        actor=actor,
        t_mono_ns=T + i * 10**9,
        frame=FrameRef(source="x11", t_capture_ns=T + i * 10**9, ref=f"snapshots/{i:03d}.png"),
        action=Action(
            type=kind,
            points=list(points),  # type: ignore[arg-type]
            intended=Intended(kind="cell" if gid is None else "monster", gid=gid),
        ),  # fmt: skip
        cue="test",
        rule="walk@3",
        scene="outdoor:prt_fild08",
        outcome=Outcome(status=status, verifier="verify@1", evidence={"mob_id": 1002}),  # type: ignore[arg-type]
    )


def test_only_verified_successes_with_a_click_become_labels(dl: ModuleType, tmp_path: Path) -> None:
    session = tmp_path / SID
    session.mkdir()
    records = [
        rec(0, "walk", "success"),
        rec(1, "walk", "fail"),
        rec(2, "walk", "ambiguous"),
        rec(3, "walk", "pending"),
        rec(4, "walk", "success", points=()),  # a declined attempt never clicked
        rec(5, "logout", "success", actor="rule:harness@1"),
        rec(6, "attack_target", "success", gid=110003),
        rec(7, "attack_target", "success", gid=None),  # no target gid: not a label
        rec(8, "login", "success"),
        rec(9, "walk", "success", actor="bot:idle@0.3"),  # the bot's own actions: same schema
    ]
    (session / "demo.verified.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records)
    )
    out, labels = dl.export(session, tmp_path / "labels")
    assert [(x["polarity"], x["record_id"]) for x in labels] == [
        ("negative", records[0].record_id),
        ("positive", records[6].record_id),
        ("negative", records[9].record_id),
    ]
    pos = labels[1]
    assert (pos["gid"], pos["mob_id"], pos["box"], pos["source"], pos["weak"]) == (
        110003, 1002, None, "demo", True)  # fmt: skip
    assert labels[0]["frame"]["ref"] == "snapshots/000.png" and labels[0]["point"] == [640.0, 300.0]
    assert [json.loads(x) for x in out.read_text().splitlines()] == labels


def test_an_unverified_session_is_refused(dl: ModuleType, tmp_path: Path) -> None:
    session = tmp_path / SID
    session.mkdir()
    (session / "demo.jsonl").write_text(rec(0, "walk", "pending").model_dump_json() + "\n")
    with pytest.raises(SystemExit, match="run demo_verify.py first"):
        dl.export(session, tmp_path / "labels")
