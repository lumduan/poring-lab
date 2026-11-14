"""scripts/stage5b_ab.py and scripts/runner_pin.py: stage 5b-1's live A/B (live-blocks.md 13.5) --
the runner as eb160ee1 had it (A) against 5b-1's (B), the same box, arms differing ONLY in the
runner's text (each pinned by its sha256 and loaded by the launcher)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import huntstate_check as hc  # noqa: E402
import runner_pin as rp  # noqa: E402
import stage5b_ab as ab  # noqa: E402


def _base() -> str:
    try:
        return hc.git_show(hc.BASE_REV, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip(f"git cannot show {hc.BASE_REV} here (a shallow checkout)")


def test_the_pinned_a_text_is_eb160ee1s_runner() -> None:
    assert ab.sha(_base()) == ab.A_SHA256 and ab.BASE_REV == "eb160ee1"


def test_each_arm_runs_flow_play_through_the_launcher_with_its_own_text(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 2, 20, "alternate", tmp_path / "s", _base(), hc.TARGET.read_text())
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A"]
    assert doc["runner_sha256"]["A"] == ab.A_SHA256
    assert doc["runner_sha256"]["B"] == ab.sha(hc.TARGET.read_text()) != ab.A_SHA256
    assert doc["vals"]["alarm_fast"] is True and doc["bar"] is ab.BAR
    for r in doc["runs"]:
        argv = r["argv"]
        i = argv.index("scripts/runner_pin.py")
        assert argv[i + 1 : i + 3] == ["--text", str(tmp_path / "s" / f"runner-{r['arm']}.py")]
        assert argv[i + 4] == doc["runner_sha256"][r["arm"]]
        j = argv.index("--")
        assert argv[j + 1 : j + 3] == ["scripts/flow_play.py", "play"]  # play_command's own rest
        assert "--project-hash" in argv and doc["project_hash"] in argv
    a_runs = [r["argv"] for r in doc["runs"] if r["arm"] == "A"]
    b_runs = [r["argv"] for r in doc["runs"] if r["arm"] == "B"]
    strip = {str(tmp_path / "s" / "runner-A.py"), str(tmp_path / "s" / "runner-B.py"),
             *doc["runner_sha256"].values()}  # fmt: skip
    norm = [[x for x in v if x not in strip and "-r0" not in x] for v in a_runs + b_runs]
    assert all(v == norm[0] for v in norm)  # the same command but the text and the labels


def test_the_plan_refuses_a_b_that_is_not_as_rewrite_or_a_wrong_a(tmp_path: Path) -> None:
    base = _base()
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s", base, base)  # B = A unrewritten
    assert isinstance(got, str) and "B is not the 5b-1 rewrite of A" in got
    good = hc.TARGET.read_text()
    bent = good.replace('hs.mode = "search"', 'hs.mode = "rest"', 1)  # one decision changed
    assert bent != good
    got2 = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s", base, bent)
    assert isinstance(got2, str) and "B is not the 5b-1 rewrite of A" in got2
    got3 = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "s", base + "\n", hc.TARGET.read_text())
    assert got3 == "refused before any input: A's text (eb160ee1) is not the pinned one"


def test_the_base_texts_kinds_and_the_argv_wrap() -> None:
    kinds = ab.base_kinds(_base())
    assert {"run_start", "run_end", "hp_read", "kill", "engage", "walk", "loot_step"} <= kinds
    argv = ["nice", "-n", "10", "uv", "run", "python", "scripts/flow_play.py", "play", "--x", "1"]
    assert ab.pin_argv(argv, Path("/t/r.py"), "ab" * 32, Path("/t/r.json")) == [
        "nice", "-n", "10", "uv", "run", "python", "scripts/runner_pin.py", "--text", "/t/r.py",
        "--sha256", "ab" * 32, "--record", "/t/r.json", "--", "scripts/flow_play.py", "play",
        "--x", "1"]  # fmt: skip


def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score5b:
    sc = ab.Score5b(label, arm, pair, found=True)
    for k, v in kw.items():
        setattr(sc, k, v)
    return sc


def _pairs(b_gap: float = 201.0, **b_kw: Any) -> list[ab.Score5b]:
    out = []
    for p in (1, 2, 3):
        common = {"minutes": 20.0, "openers": 40, "kinds": {"hp_read": 6000, "kill": 50}}
        out.append(_sc(f"a{p}", "A", p, kills=50 + p, loot_steps=60, gaps_ms=[201.0] * 99 + [400],
                       **common))  # fmt: skip
        out.append(_sc(f"b{p}", "B", p, kills=51 + p, loot_steps=61,
                       gaps_ms=[b_gap] * 99 + [400], **{**common, **b_kw}))  # fmt: skip
    return out


def test_the_bar_passes_on_three_good_pairs_and_judges_every_line() -> None:
    v = ab.verdict(_pairs(), 20.0, {"hp_read", "kill"})
    assert v["verdict"] == "PASS", v
    lines = v["lines"]
    assert lines["pace"]["A"]["median"] == 201.0 and lines["pace"]["pass"] is True
    assert lines["kills_h"]["pass"] is True and lines["loot_h"]["pass"] is True
    assert lines["openers_h"]["pass"] is True and lines["kinds"]["pass"] is True


def test_a_slower_tick_a_new_record_kind_or_a_runner_error_fails_it() -> None:
    assert ab.verdict(_pairs(b_gap=215.0), 20.0, {"hp_read", "kill"})["lines"]["pace"]["pass"] \
        is False  # fmt: skip
    new = _pairs(kinds={"hp_read": 6000, "kill": 50, "tick_step": 3})
    v = ab.verdict(new, 20.0, {"hp_read", "kill"})
    assert v["verdict"] == "FAIL" and v["lines"]["kinds"]["new_in_B"] == ["tick_step"]
    err = _pairs()
    err[1].error = "AttributeError: 'HuntState' object has no attribute 'x'"
    v2 = ab.verdict(err, 20.0, {"hp_read", "kill"})
    assert v2["verdict"] == "FAIL" and v2["lines"]["errors"]["pass"] is False
    few = _pairs(openers=60)  # +50 %: out of +-20 %
    assert ab.verdict(few, 20.0, {"hp_read", "kill"})["lines"]["openers_h"]["pass"] is False


def test_deaths_count_over_every_run_that_played_and_two_pairs_are_inconclusive() -> None:
    s = _pairs()[:4] + [_sc("b3", "B", 3, minutes=3.0, deaths=1), _sc("a3", "A", 3, minutes=20.0)]
    v = ab.verdict(s, 20.0, {"hp_read", "kill"})
    assert v["lines"]["deaths"] == {"A": 0, "B": 1, "pass": False} and v["verdict"] == "FAIL"
    ok = _pairs()[:4]
    v2 = ab.verdict(ok, 20.0, {"hp_read", "kill"})
    assert v2["verdict"] == "INCONCLUSIVE" and v2["lines"]["kills_h"]["pass"] is None


def test_the_score_reads_the_tick_gaps_kinds_and_a_traceback() -> None:
    sc = ab.Score5b("x", "B", 1)
    ab.score_pace(sc, [{"kind": "hp_read", "t_ns": 0}, {"kind": "kill"},
                       {"kind": "hp_read", "t_ns": 200_000_000},
                       {"kind": "hp_read", "t_ns": 450_000_000}])  # fmt: skip
    assert sc.gaps_ms == [200.0, 250.0] and sc.kinds == {"hp_read": 3, "kill": 1}
    ab.score_errors(sc, "x\nTraceback (most recent call last):\n  ...\nKeyError: 'mode'\n", [])
    assert sc.error == "KeyError: 'mode'"
    sc2 = ab.Score5b("y", "B", 1)
    ab.score_errors(sc2, "", [{"kind": "hunt_end", "error": "dungeon@9.35 refused: ..."}])
    assert sc2.error is None  # a start refusal is no runner error
    assert ab.pace([]) == {"median": None, "p95": None, "n": 0}


# --- the launcher ---------------------------------------------------------------------------------
def _launch(tmp_path: Path, text: str, sha256: str) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "probe.py"
    script.write_text(
        "import sys, json\n"
        "import dungeon_hunt as dh\n"
        "print(json.dumps({'file': dh.__file__, 'root': str(dh.ROOT), 'argv': sys.argv,\n"
        "                  'hs': hasattr(dh, 'HuntState')}))\n")  # fmt: skip
    (tmp_path / "runner.py").write_text(text)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "runner_pin.py"), "--text",
         str(tmp_path / "runner.py"), "--sha256", sha256, "--record", str(tmp_path / "rec.json"),
         "--", str(script), "--flag", "1"],
        cwd=ROOT, capture_output=True, text=True, timeout=120)  # fmt: skip


def test_the_launcher_loads_the_pinned_text_as_the_checkouts_runner(tmp_path: Path) -> None:
    base = _base()
    out = _launch(tmp_path, base, ab.sha(base))
    assert out.returncode == 0, out.stderr[-2000:]
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["file"] == str(rp.RUNNER) and got["root"] == str(ROOT)  # ROOT from the real path
    assert got["hs"] is False  # eb160ee1's runner: no HuntState
    assert got["argv"][1:] == ["--flag", "1"]
    rec = json.loads((tmp_path / "rec.json").read_text())
    assert rec["sha256"] == ab.A_SHA256 and rec["huntstate"] is False


def test_the_launcher_refuses_a_text_whose_sha256_is_not_the_pinned_one(tmp_path: Path) -> None:
    out = _launch(tmp_path, "X = 1\n", "0" * 64)
    assert out.returncode == 2 and "runner_pin refused" in out.stderr
    assert not (tmp_path / "rec.json").exists() and out.stdout == ""  # the script never ran
