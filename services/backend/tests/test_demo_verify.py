"""scripts/demo_verify.py: a synthetic demo session judged end to end (docs/demonstrations.md)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

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
    log.append(DemoRecord(session=SID, actor=actor, t_mono_ns=t0, t_done_ns=t0 + 30 * 10**9,
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
