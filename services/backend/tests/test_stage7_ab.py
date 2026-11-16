"""scripts/stage7_ab.py: s7ab, the Fly Wing first's live A/B (live-blocks.md 18.7) -- today's runner
(A) against --fly-first (B) on the same box: the plan's refusals before any input, the fly-first
line from the runner's records, the packets and the input log, deaths reported never judged, the
economy, and 18.2's measure. NOT run live here."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import huntstate_check as hc  # noqa: E402
import stage7_ab as ab  # noqa: E402

S = 1_000_000_000


def _bases() -> tuple[str, str]:
    try:
        return hc.git_show(hc.DRIVE_BASE, hc.TARGET), hc.git_show(hc.BASE_REV, hc.TARGET)
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git cannot show the bases here (a shallow checkout)")


def test_the_plan_alternates_the_arms_on_one_box_differing_in_fly_first_alone(
    tmp_path: Path,
) -> None:
    drive_base, check_base = _bases()
    doc = ab.plan_doc("s", 4, 20, "alternate", tmp_path / "s", base_text=drive_base,
                      check_base=check_base, seeds=3)  # fmt: skip
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B", "B", "A"]
    assert doc["vals"]["A"]["fly_first"] is False and doc["vals"]["B"]["fly_first"] is True
    assert {k for k in doc["vals"]["A"] if doc["vals"]["A"][k] != doc["vals"]["B"][k]} == {
        "fly_first"
    }
    assert (
        doc["arms"]["A"]["box"] == doc["arms"]["B"]["box"]
        and doc["arms"]["A"]["loop"] == "hunt_loop"
    )
    assert doc["bar"] is ab.BAR and ab.BAR["fly_bound_s"] == ab.FLY_BOUND_S == 0.35
    for r in doc["runs"]:
        assert str(tmp_path / "s" / f"project-{r['arm']}.json") in r["argv"]
        assert str(tmp_path / "s" / f"runner-config-{r['arm']}.json") in r["argv"]


def test_the_arms_differ_in_their_fly_first_block_alone() -> None:
    a, b = ab.arm_doc("A", 20), ab.arm_doc("B", 20)
    assert ab.box_difference(a, b) is None
    assert "does not hold fly_first = True" in str(ab.box_difference(a, a))
    other = json.loads(json.dumps(b))
    other["max_runtime_s"] = 60
    assert "more than its fly_first block" in str(ab.box_difference(a, other))
    v = {arm: ab.vals_of(ab.arm_text(arm, 20)) for arm in "AB"}
    assert isinstance(v["A"], dict) and isinstance(v["B"], dict)
    assert v["A"]["fly_first"] is False and v["B"]["fly_first"] is True


def test_the_plan_refuses_a_runner_that_is_not_9_57_or_whose_proofs_fail(tmp_path: Path) -> None:
    drive_base, check_base = _bases()
    text = hc.TARGET.read_text()
    old = text.replace('FLY_FIRST_VERSION = "9.57"', 'FLY_FIRST_VERSION = "9.56"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=old, base_text=drive_base,
                      check_base=check_base, seeds=0)  # fmt: skip
    assert isinstance(got, str) and "is not dungeon@9.57" in got
    bent = text.replace('press("fly", "boss")\n', 'press("fly", "boss!")\n', 1)
    got2 = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=bent, base_text=drive_base,
                       check_base=check_base, seeds=0)  # fmt: skip
    assert isinstance(got2, str) and "huntstate_check drive fails" in got2


# --- the fly-first line ---------------------------------------------------------------------------
def _fly(t_key: int, t_read: int | None = None, why: str = "garm") -> dict[str, Any]:
    return {"kind": "fly_first", "what": "fly", "why": why, "src": "alarm",
            "t_read_ns": t_read, "t_key_ns": t_key, "sight": {"score": 0.74}}  # fmt: skip


def test_each_fly_is_judged_by_its_keys_and_its_request() -> None:
    ev = [_fly(10 * S, 10 * S - 20_000_000), _fly(20 * S, 19 * S), _fly(30 * S, 30 * S),
          _fly(40 * S, 40 * S), _fly(50 * S, 50 * S)]  # fmt: skip
    pk = [{"type": "use_item_request", "t_mono_ns": 10 * S + 80_000_000},  # 0.08 s: ok
          {"type": "use_item_request", "t_mono_ns": 20 * S + 70_000_000},
          {"type": "use_item_request", "t_mono_ns": 40 * S + 500_000_000},  # 0.5 s: over the bound
          {"type": "entity_vanish", "gid": ab.SELF_GID, "reason": 1,
           "t_mono_ns": 49 * S}]  # fmt: skip
    downs = [ab.KeyDown(19 * S + 500_000_000, 19 * S + 550_000_000, "F5")]  # a dagger key between
    got = ab.flies_of(ev, pk, downs)
    assert [f.ok() for f in got] == [True, False, False, False, None]
    assert got[1].keys_before == ["F5"] and got[2].request_s is None and got[3].request_s == 0.5
    assert got[4].after_death is True  # pressed after her death: reported, not judged


def test_the_input_log_gives_the_bots_key_downs_by_their_send_time() -> None:
    lines = [
        json.dumps(
            {
                "t_mono_ns": 105,
                "source": "bot",
                "accepted": True,
                "event": {"t_mono_ns": 100, "type": "key", "code": "F5", "action": "down"},
            },
            separators=(",", ":"),
        ),  # fmt: skip
        json.dumps(
            {
                "t_mono_ns": 205,
                "source": "bot",
                "accepted": True,
                "event": {"t_mono_ns": 200, "type": "key", "code": "F5", "action": "up"},
            },
            separators=(",", ":"),
        ),  # fmt: skip
        json.dumps(
            {
                "t_mono_ns": 305,
                "source": "human",
                "accepted": True,
                "event": {"t_mono_ns": 300, "type": "key", "code": "F8", "action": "down"},
            },
            separators=(",", ":"),
        ),  # fmt: skip
        json.dumps(
            {
                "t_mono_ns": 405,
                "source": "bot",
                "accepted": True,
                "event": {"t_mono_ns": 400, "type": "key", "code": "F8", "action": "down"},
            },
            separators=(",", ":"),
        ),  # fmt: skip
    ]
    assert ab.key_downs(lines, 0, 10**9) == [ab.KeyDown(100, 105, "F5"), ab.KeyDown(400, 405, "F8")]
    assert ab.key_downs(lines, 150, 10**9) == [ab.KeyDown(400, 405, "F8")]


def _sc(label: str, arm: str, pair: int, **kw: Any) -> ab.Score7:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70, "drive": 2},
            "drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end",
                                               "ended": "run_end", "passed": {}}]}  # fmt: skip
    base.update(kw)
    s = ab.Score7(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def _ok_fly() -> ab.Fly:
    return ab.Fly(10 * S, 10 * S, "garm", "alarm", 0.08)


def test_the_bar_judges_the_fly_first_line_and_only_reports_deaths() -> None:
    kinds = {"hp_read", "kill"}
    ok = [_sc(f"r{i}{x}", x, i, **({"flies_ff": [_ok_fly()]} if x == "B" else {}))
          for i in (1, 2, 3, 4) for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    assert v["lines"]["fly_first"]["pass"] is True and v["lines"]["fly_first"]["judged"] == 4
    assert "deaths" not in {k for k in v["lines"] if k != "report"}  # reported, never judged
    more = [*ok[:-1], _sc("r4B", "B", 4, deaths=2, flies_ff=[_ok_fly()])]
    v2 = ab.verdict(more, 20, kinds)
    assert v2["verdict"] == "PASS" and v2["lines"]["report"]["deaths"]["B"] == 2
    bad = [*ok[:-1], _sc("r4B", "B", 4, flies_ff=[ab.Fly(1, 1, "garm", "alarm", None)])]
    assert ab.verdict(bad, 20, kinds)["verdict"] == "FAIL"
    none = [_sc(f"r{i}{x}", x, i) for i in (1, 2, 3, 4) for x in ("A", "B")]
    v3 = ab.verdict(none, 20, kinds)
    assert v3["verdict"] == "INCONCLUSIVE" and v3["lines"]["fly_first"]["pass"] is None
    assert ab.verdict(ok[:4], 20, kinds)["verdict"] == "INCONCLUSIVE"  # 2 valid pairs only
    kind_new = [*ok[:-1], _sc("r4B", "B", 4, flies_ff=[_ok_fly()],
                              kinds={"hp_read": 1, "fly_first": 3})]  # fmt: skip
    assert ab.verdict(kind_new, 20, kinds)["lines"]["kinds"]["pass"] is True  # fly-first's own


def test_the_economy_is_the_dashboards_with_steals(monkeypatch: pytest.MonkeyPatch) -> None:
    """live-blocks 18.10 #4: the per-run z/h and each arm's are econ_db.totals_of's (the
    dashboard's gross / cost / net WITH Steal and Snatcher income), each arm's valid runs pooled."""
    import econ_db as edb

    assert ab.econ_pick({"gross_h": 50207.3, "cost_h": 6998.0, "net_h": 43209.3, "x": 1}) == {
        "gross_h": 50207.3, "cost_h": 6998.0, "net_h": 43209.3}  # fmt: skip
    assert ab.econ_pick(None) is None
    seen: list[list[str]] = []

    def fake(sids: list[str], **_k: object) -> dict[str, object]:
        seen.append(list(sids))
        return {"runs": {s: {} for s in sids}, "missing": [],
                "pooled": ({"gross_h": 1.0, "cost_h": 0.5, "net_h": 0.5}
                           if sids else None)}  # fmt: skip

    monkeypatch.setattr(edb, "totals_of", fake)
    s = [_sc(f"r{i}{x}", x, i, sessions=[f"sid-{i}{x}"]) for i in (1, 2) for x in ("A", "B")]
    s.append(_sc("r3A", "A", 3, minutes=5.0, sessions=["sid-short"]))  # not valid: not pooled
    got = ab.econ_arms(s, 20)
    assert seen == [["sid-1A", "sid-2A"], ["sid-1B", "sid-2B"]]
    assert got["A"] == {"gross_h": 1.0, "cost_h": 0.5, "net_h": 0.5, "runs": 2, "missing": []}
    rep = ab.report_of(s, 20, econ=got)
    assert rep["B"]["econ_with_steals"]["net_h"] == 0.5


def test_the_measure_of_18_2_reads_the_keys_and_the_requests(tmp_path: Path) -> None:
    d = tmp_path / "sess"
    d.mkdir()
    with gzip.open(d / "packets.jsonl.gz", "wt") as f:
        for p in ({"type": "time_sync", "t_mono_ns": 1 * S},
                  {"type": "use_item_request", "t_mono_ns": 2 * S + 24_000_000},
                  {"type": "equip_request", "t_mono_ns": 3 * S + 30_000_000},
                  {"type": "time_sync", "t_mono_ns": 9 * S}):  # fmt: skip
            f.write(json.dumps(p) + "\n")
    log = tmp_path / "log.jsonl"
    rows = [(2 * S, 2 * S - 50_000_000, "F8"), (3 * S, 3 * S - 50_000_000, "F5")]
    log.write_text("".join(json.dumps({"t_mono_ns": acc, "source": "bot", "accepted": True,
                                       "event": {"t_mono_ns": sent, "type": "key", "code": c,
                                                 "action": "down"}}, separators=(",", ":")) + "\n"
                           for acc, sent, c in rows))  # fmt: skip
    got = ab.request_delays([d], [log])
    assert got["F8"]["n"] == 1 and got["F8"]["from_accept_ms"]["median"] == 24.0
    assert got["F8"]["from_send_ms"]["max"] == 74.0 and got["F5"]["from_accept_ms"]["max"] == 30.0
