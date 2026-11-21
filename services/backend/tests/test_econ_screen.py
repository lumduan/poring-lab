"""SCREEN-ONLY RUN RECORDS (scripts/econ_screen.py; Batt 2026-11-21, decision 2 = A: "a screen-only
economy record for every Run"). A Run with no packet file (the live lab's PC, a learner's) was
refused by the packet judge (the live lab: 21 Runs, 0 records). Now it is judged from its own
events into its own table (screen_runs), never mixed with a packet record, and the /economy page's
export of every screen record (screen-runs) is written after each new one."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import econ_db as edb  # noqa: E402
import econ_screen as es  # noqa: E402
import test_econ_db as tedb  # noqa: E402  (the packet sessions' synthetic data)

S = 10**9
T0 = 1_000 * S


@pytest.fixture
def lab(tmp_path: Path) -> SimpleNamespace:
    """A packet session (test_econ_db's synthetic r1) and its data, beside the screen ones."""
    data = tmp_path / "data"
    tedb.write_data(data)
    s1 = tedb.write_session(tmp_path / "sessions", "20261112T010000-synthetic-r1",
                            *tedb.a_session(100.0, tedb.PLAN_1, tedb.USES_1))  # fmt: skip
    return SimpleNamespace(data=data, s1=s1, db=tmp_path / "db" / "lab.sqlite")


def cli(lab: SimpleNamespace, *args: str) -> int:
    return edb.main([*args, "--db", str(lab.db), "--data", str(lab.data)])


def screen_events(kills: int = 3, flies: int = 2) -> list[dict[str, Any]]:
    ev: list[dict[str, Any]] = [
        {"t_ns": T0 - 5 * S, "kind": "hp_read", "pct": 100},  # before run_start: not counted
        {"t_ns": T0 - 4 * S, "kind": "kill", "by": "exp_line"},
        {"t_ns": T0, "kind": "run_start", "map": "xmas_dun02", "char": "rogue", "strategy": "P2"},
        {"t_ns": T0 + 10 * S, "kind": "stock", "item": 601, "count": 40},
    ]
    t = T0 + 20 * S
    for i in range(kills):
        ev += [{"t_ns": t, "kind": "kill", "by": "exp_line" if i else "inferred"},
               {"t_ns": t + S, "kind": "loot_step", "picks": 1 if i else 0},
               {"t_ns": t + 2 * S, "kind": "loot_click", "cell": [1, 2]}]  # fmt: skip
        t += 60 * S
    for _ in range(flies):
        ev.append({"t_ns": t, "kind": "press", "what": "fly", "key": "F8"})
        t += 5 * S
    ev += [{"t_ns": t, "kind": "press", "what": "potion", "key": "F1"},
           {"t_ns": t + S, "kind": "press", "what": "equip", "why": "popup"},
           {"t_ns": t + 2 * S, "kind": "stock", "item": 601, "count": 38},
           {"t_ns": T0 + 3600 * S, "kind": "run_end", "reason": "time_box"},
           {"t_ns": T0 + 3601 * S, "kind": "press", "what": "home"}]  # fmt: skip  # after the end
    return ev


def write_screen_session(root: Path, name: str, ev: list[dict[str, Any]]) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    (d / "manifest.json").write_text(json.dumps({"sid": name, "version": "dungeon@8.7"}))
    return d


def test_judge_counts_what_the_screen_saw_in_the_window() -> None:
    j = es.judge("20261121T054933-demo-x-P2-flowplay-a-hunt1", screen_events(), {},
                 [{"t_ns": T0 - 60 * S, "kind": "hp_read", "weight_pct": 38},
                  {"t_ns": T0 + 3700 * S, "kind": "hp_read", "weight_pct": 50}])  # fmt: skip
    assert j["window"] == {"t0": T0, "t1": T0 + 3600 * S, "source": "run_start..run_end"}
    assert j["hours"] == 1.0 and j["kills"] == 3 and j["kills_by"] == {"exp_line": 2, "inferred": 1}
    assert (j["loot_steps"], j["loot_picks"], j["pickup_clicks"]) == (3, 2, 3)
    assert (j["fly_wings"], j["potions"], j["butterfly_wings"], j["steals"]) == (2, 1, 0, 1)
    assert j["stock"] == {"601": {"first": 40, "last": 38, "reads": 2}}
    assert (j["weight_start"], j["weight_end"]) == (38.0, 50.0)  # the player's reads around it
    assert j["end"] == "time_box" and j["map"] == "xmas_dun02" and j["source"] == "screen"
    assert j["started"] == "2026-11-21 05:49:33"  # the session id's time + the window's offset


def test_weight_reads_count_only_near_the_hunt() -> None:
    far = [{"t_ns": T0 - 2000 * S, "kind": "hp_read", "weight_pct": 10}]
    assert es.weight_ends(far, T0, T0 + 10 * S) == [None, None]
    inside = [{"t_ns": T0 + S, "kind": "hp_read", "weight_pct": 20},
              {"t_ns": T0 + 5 * S, "kind": "hp_read", "weight_pct": 25}]  # fmt: skip
    assert es.weight_ends(inside, T0, T0 + 10 * S) == [20.0, 25.0]


def test_a_session_without_events_time_is_refused() -> None:
    with pytest.raises(ValueError):
        es.judge("x", [{"kind": "kill"}], {})


def test_the_entry_has_no_items_prices_only_the_one_item_roles() -> None:
    j = es.judge("s", screen_events(), {})
    table = {"601": {"type": "Delayconsume", "npc_buy": 60, "npc_buy_dc10": 46, "sell": 30}}
    e = es.entry(j, table, {"601": "Fly Wing"})
    assert e["items"] == [] and e["species"] == [] and e["source"] == "screen"
    assert [(c["item_id"], c["used"], c["npc_buy"]) for c in e["consumables"]] == [(601, 2, 60)]
    assert "potions" in e["why"] and "not verified by packets" in e["why"]["source"]
    assert e["screen"]["pickup_clicks"] == 3 and e["totals"]["cost"] == 120
    pooled = es.pool([e, e])
    assert pooled["kills"] == 6 and pooled["screen"]["pickup_clicks"] == 6
    assert pooled["screen"]["kills_by"] == {"exp_line": 4, "inferred": 2}


def test_update_records_a_screen_session_beside_packet_runs_and_exports_it(
    lab: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "20261121T054933-demo-x-P2-flowplay-a-hunt1"
    sd = write_screen_session(tmp_path / "demo", name, screen_events())
    assert es.screen_dir(sd, tmp_path / "demo", tmp_path / "store") == sd
    assert es.screen_dir(lab.s1, tmp_path / "demo", tmp_path / "store") is None  # it has packets
    assert cli(lab, "update", str(lab.s1), str(sd)) == 0
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert [o.get("result") for o in out[:2]] == ["added", "added"]
    assert out[1]["source"] == "screen" and out[2] == {"db": str(lab.db), "runs": 1,
                                                       "screen_runs": 1}  # fmt: skip
    # no --export: only the screen records' export (an older helper's call still fills the page)
    assert [o.get("source") for o in out[3:]] == ["screen"]
    doc = json.loads((lab.data / "econ" / "dashboard" / "screen-runs.json").read_text())
    assert doc["schema"] == "poring-lab.econ-dashboard.v1" and doc["source"] == "screen"
    assert [r["session"] for r in doc["runs"]] == [sd.name]
    assert doc["runs"][0]["items"] == [] and doc["pooled"]["screen"]["pickup_clicks"] == 3
    # again: skipped, no new export line; a packet run and a screen run never mix
    assert cli(lab, "update", str(sd)) == 0
    again = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert again[0]["result"] == "skipped" and len(again) == 2
    con = sqlite3.connect(lab.db)
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert con.execute("SELECT kills, pickup_clicks, fly_wings FROM screen_runs").fetchall() == [
        (3, 3, 2)]  # fmt: skip
    con.close()


def test_export_names_the_packet_runs_and_list_shows_both(
    lab: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sd = write_screen_session(
        tmp_path / "demo", "20261121T060000-demo-y-hunt1", screen_events(1, 0)
    )
    assert cli(lab, "update", str(lab.s1), str(sd), "--export", "flowplay-test-1") == 0
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert {o.get("source") for o in out if "export" in o} == {"packets", "screen"}
    assert (lab.data / "econ" / "dashboard" / "flowplay-test-1.json").is_file()
    assert cli(lab, "list") == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x.get("source") for x in lines[1:]] == [None, "screen"]
    assert cli(lab, "dashboard", "--screen", "--name", "mine") == 0
    assert (lab.data / "econ" / "dashboard" / "mine.json").is_file()


def test_after_run_command_passes_the_runs_label_for_the_export() -> None:
    argv = edb.after_run_command(["/x/s1"], export="flowplay-poring-lab-live-11211126")
    assert argv[-2:] == ["--export", "flowplay-poring-lab-live-11211126"]
    assert "--export" not in edb.after_run_command(["/x/s1"])


@pytest.mark.skipif(not list(Path("/dev/shm/poring-lab-demo").glob("*11210548-hunt1")),
                    reason="the banked live session is not on this host")  # fmt: skip
def test_the_real_live_session_judges_as_its_panel_said() -> None:
    """Batt's live Run 11210548 (2026-11-21 05:49-07:42): the Run panel showed 255 kills, 27
    pickups, 79 Fly Wings; the hotbar read 138 -> 60; the bag 38 % -> 50 % (weight_home)."""
    d = next(Path("/dev/shm/poring-lab-demo").glob("*11210548-hunt1"))
    j = es.load_session(d)
    assert (j["kills"], j["pickup_clicks"], j["fly_wings"]) == (255, 27, 79)
    assert j["stock"]["601"]["first"] == 138 and j["stock"]["601"]["last"] == 60
    assert (j["weight_start"], j["weight_end"]) == (38.0, 50.0)
