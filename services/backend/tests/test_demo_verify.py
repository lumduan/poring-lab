"""scripts/demo_verify.py: a synthetic demo session judged end to end (docs/demonstrations.md)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from poring_env.demo import Action, DemoLog, DemoRecord, Intended

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "demo_verify.py"
SID = "20261007T123000-demo-login-alone"
T = 900_000_000_000_000


@pytest.fixture(scope="module")
def dv() -> ModuleType:
    spec = importlib.util.spec_from_file_location("demo_verify", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def attempt(log: DemoLog, t0: int, actor: str = "rule:login@1") -> None:
    log.append(DemoRecord(session=log.session, actor=actor, t_mono_ns=t0, t_done_ns=t0 + 30 * 10**9,
                          rule="login@1" if actor != "rule:harness@1" else None,
                          action=Action(type="login" if actor != "rule:harness@1" else "logout",
                                        intended=Intended(kind="login", note="gm")),
                          cue="login@1"))  # fmt: skip


def test_a_session_is_judged_and_summarised(
    dv: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    log = DemoLog(SID, root=tmp_path)
    events = []
    for i in range(20):
        t0 = T + i * 60 * 10**9
        attempt(log, t0 - 10**9, "rule:harness@1")
        attempt(log, t0)
        if i != 7:  # attempt 7 never reaches the map server
            events.append({"t_mono_ns": t0 + 4 * 10**9, "type": "login_accepted", "aid": 2000002})
            events.append({"t_mono_ns": t0 + 5 * 10**9, "type": "char_selected", "map": "m.gat"})
            events.append({"t_mono_ns": t0 + 6 * 10**9, "type": "map_enter", "x": 1, "y": 1})
        else:
            events.append({"t_mono_ns": t0 + 4 * 10**9, "type": "login_accepted", "aid": 2000002})
    with gzip.open(log.dir / "packets.jsonl.gz", "wt") as fh:
        fh.writelines(json.dumps(e) + "\n" for e in events)
    monkeypatch.setattr(sys, "argv", ["demo_verify.py", str(log.dir)])
    assert dv.main() == 0
    out = json.loads(capsys.readouterr().out)["rules"]["login@1"]
    assert (out["attempts"], out["verified_success"], out["fail"]) == (20, 19, 1)
    assert out["fail_causes"] == {"no char_selected within 60 s": 1}
    assert out["verdict"] == "PASS" and out["seconds_p50"] == 30.0
    verified = [json.loads(x) for x in (log.dir / "demo.verified.jsonl").read_text().splitlines()]
    assert len(verified) == 40  # the harness's records are kept, unscored
    assert {v["outcome"]["status"] for v in verified if v["actor"] == "rule:harness@1"} == {
        "pending"
    }


def walk(t0: int) -> DemoRecord:
    action = Action(
        type="walk",
        points=[(640.0, 300.0)],
        intended=Intended(kind="cell", cell=(6, 0), relative=True),
    )
    return DemoRecord(
        session="20261007T131457-demo-walk-alone-outdoor",
        actor="rule:walk@3",
        t_mono_ns=t0,
        t_done_ns=t0 + 10**9,
        rule="walk@3",
        cue="walk@3",
        action=action,
    )


def test_a_walk_window_ends_where_the_next_attempt_starts(dv: ModuleType) -> None:
    """2026-10-07, before walk@3 was scored: the walk branch did not pass t_end, so the NEXT
    attempt's @warp (a map change) could land inside this walk's arrival window."""
    s = 10**9
    events = [
        {"t_mono_ns": T - s, "type": "map_change", "map": "m.gat", "x": 100, "y": 100},
        {"t_mono_ns": T + s // 3, "type": "self_move_request", "x": 106, "y": 100},
        {"t_mono_ns": T + 4 * s // 10, "type": "self_move", "x0": 100, "y0": 100, "x1": 106,
         "y1": 100},
        {"t_mono_ns": T + 25 * s // 10, "type": "map_change", "map": "m.gat", "x": 90, "y": 90},
    ]  # fmt: skip
    aids = {"gm": 2000002, "player": 2000001}
    rec = walk(T)
    assert dv.judge(rec, events, aids, T + 2 * s).status == "success"
    leaked = dv.judge(rec, events, aids, None)
    assert (leaked.status, leaked.cause) == ("ambiguous", "map_change during the walk")


class FakeAnchors:
    """status is 'on screen' when the snapshot's first pixel is white."""

    templates = {"status": object()}

    def locate(self, frame: Any) -> dict[str, tuple[int, int]]:
        return {"status": (185, 300)} if int(frame[0, 0, 0]) == 255 else {}


@pytest.mark.parametrize(
    ("before", "after", "status", "cause"),
    [
        (0, 255, "success", None),
        (0, 0, "fail", "the window did not appear"),
        (255, 255, "ambiguous", "the window was already open before the shortcut"),
    ],
)
def test_a_window_shortcut_is_judged_on_its_snapshots(
    dv: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    before: int, after: int, status: str, cause: str | None,
) -> None:  # fmt: skip
    import numpy as np

    from poring_dataset.shards import encode_png
    from poring_env.demo import FrameRef

    monkeypatch.setattr(dv, "window_registry", lambda: FakeAnchors())
    (tmp_path / "snapshots").mkdir()
    for name, value in (("b", before), ("a", after)):
        (tmp_path / "snapshots" / f"{name}.png").write_bytes(
            encode_png(np.full((4, 4, 3), value, np.uint8))
        )
    rec = DemoRecord(
        session=SID, actor="rule:open_window@1", t_mono_ns=T, rule="open_window@1", cue="t",
        frame=FrameRef(source="x11", ref="snapshots/b.png"),
        frame_after=FrameRef(source="x11", ref="snapshots/a.png"),
        action=Action(type="menu_shortcut", keys=["AltLeft+KeyA"],
                      intended=Intended(kind="window", window="status")),
    )  # fmt: skip
    v = dv.judge(rec, [], {"gm": 1, "player": 2}, None, tmp_path)
    assert (v.status, v.cause) == (status, cause)
    party = Intended(kind="window", window="party")
    other = rec.model_copy(
        update={"action": Action(type="menu_shortcut", keys=["AltLeft+KeyZ"], intended=party)}
    )
    assert dv.judge(other, [], {}, None, tmp_path).cause == "no cut anchor for party"


def test_interrupted_attempts_are_neither_pass_nor_fail_and_reruns_merge(
    dv: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dirs = []
    for k, (sid, n, missing) in enumerate(
        [(SID, 20, {7}), ("20261007T150000-demo-login-rerun", 2, set())]
    ):
        log = DemoLog(sid, root=tmp_path)
        events = []
        recs = []
        for i in range(n):
            t0 = T + (k * 1000 + i) * 60 * 10**9
            attempt(log, t0)
            recs.append(read_last(log))
            if i not in missing:
                events += [
                    {
                        "t_mono_ns": t0 + s * 10**9,
                        "type": e,
                        "aid": 2000002,
                        "map": "m.gat",
                        "x": 1,
                        "y": 1,
                    }
                    for s, e in ((4, "login_accepted"), (5, "char_selected"), (6, "map_enter"))
                ]
        with gzip.open(log.dir / "packets.jsonl.gz", "wt") as fh:
            fh.writelines(json.dumps(e) + "\n" for e in events)
        if k == 0:  # attempt 7 failed, but a human interrupted it (and attempt 8)
            (log.dir / "interrupted.json").write_text(
                json.dumps(
                    {recs[7].record_id: "human release_all", recs[8].record_id: "human release_all"}
                )
            )
        dirs.append(str(log.dir))
    monkeypatch.setattr(sys, "argv", ["demo_verify.py", *dirs])
    assert dv.main() == 0
    out = json.loads(capsys.readouterr().out)["rules"]["login@1"]
    assert (out["attempts"], out["interrupted"], out["verified_success"], out["fail"]) == (
        20,
        2,
        20,
        0,
    )
    assert out["verdict"] == "PASS"
    verified = [
        json.loads(x) for x in (Path(dirs[0]) / "demo.verified.jsonl").read_text().splitlines()
    ]
    assert sum(v["outcome"]["status"] == "interrupted" for v in verified) == 2


def read_last(log: DemoLog) -> DemoRecord:
    from poring_env.demo import read

    return read(log.path)[-1]


def test_a_walk5_route_is_judged_by_where_the_packets_put_us_at_its_end(dv: ModuleType) -> None:
    s = 10**9
    route = DemoRecord(
        session=SID, actor="rule:walk@5", t_mono_ns=T, t_done_ns=T + 9 * s, rule="walk@5",
        cue="route", action=Action(type="walk", intended=Intended(kind="route", cell=(110, 120))),
    )  # fmt: skip
    events = [
        {"t_mono_ns": T - s, "type": "map_change", "map": "m.gat", "x": 100, "y": 120},
        {"t_mono_ns": T + 2 * s, "type": "self_move", "x0": 100, "y0": 120, "x1": 105, "y1": 120},
        {"t_mono_ns": T + 5 * s, "type": "self_move", "x0": 105, "y0": 120, "x1": 110, "y1": 120},
    ]
    aids = {"gm": 2000002, "player": 2000001}
    assert dv.judge(route, events, aids, None).status == "success"
    short = events[:2]
    v = dv.judge(route, short, aids, None)
    assert (v.status, v.cause, v.evidence["end"]) == (
        "fail",
        "the route ended elsewhere",
        [105, 120],
    )
