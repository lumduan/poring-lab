"""scripts/stage2_ab.py (live-blocks.md 3.2: stage 2's A/B, the runner alone vs the one box):
its PURE parts only -- the series' plan, its setup lines, the arms' commands, the score and the
pre-registered verdict. Nothing here reads a screen or opens an input path."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_hunt as dh  # noqa: E402
import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402
import stage2_ab as ab  # noqa: E402


def test_the_series_alternates_its_arms_and_its_warp_cells() -> None:
    runs = ab.series("s", 4)
    assert [r.arm for r in runs] == list("ABBAABBA")  # each pair's first arm alternates
    assert [r.pair for r in runs] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert [r.label for r in runs][:3] == ["s-r01A", "s-r02B", "s-r03B"]
    cells = dh.PATROL_START["xmas_dun02"]
    assert runs[0].warp == f"@warp xmas_dun02 {cells[0][0]} {cells[0][1]}"
    assert runs[1].warp == f"@warp xmas_dun02 {cells[1][0]} {cells[1][1]}"
    assert [r.arm for r in ab.series("s", 2, "ab")] == list("ABAB")
    with pytest.raises(ValueError):
        ab.series("s", 0)


def test_the_setup_lines_never_meet_the_chat_guard_and_top_up_only_under_a_floor() -> None:
    full = {"F9": 3, "F8": 10, "F1": 10}
    assert ab.topup_lines(full) == []
    assert ab.topup_lines({**full, "F9": 1}) == ["@item 602 2"]  # the Butterfly Wings under 2
    assert ab.topup_lines({**full, "F9": 2}) == []  # 2 left: no line
    assert ab.topup_lines({"F9": 0, "F8": 6, "F1": 3}) == ["@item 602 3", "@item 601 4",
                                                           "@item 504 7"]  # fmt: skip
    assert "did not read" in str(ab.topup_lines({**full, "F8": None}))
    # the worst case: every run's setup tops up the same item -- still never 3 identical lines
    typed: list[str] = []
    for r in ab.series("s", 6):
        typed += [r.warp, "@item 602 2"]
    assert ab.guard_ok(typed)
    assert not ab.guard_ok(["@warp a", "@warp a", "@warp a"])
    assert ab.guard_ok(["@warp a", "@warp a", "@item 1 1", "@warp a"])


def test_both_arms_take_the_same_runner_settings_and_the_old_run_path_argv(
    tmp_path: Path,
) -> None:
    doc = ab.plan_doc("s", 2, 20, "alternate", tmp_path / "series", config_dir=tmp_path)
    assert isinstance(doc, dict), doc
    assert doc["box_plays"] == ["boss_fly", "fly_hp", "potion"]
    assert doc["box_events"] == ["fly_away", "drink"] and doc["version"] == "9.49"
    vals = doc["vals"]
    assert vals["minutes"] == 20 and vals["heal_key"] == "F1" and vals["fly_key"] == "F8"
    a_run, b_run = doc["runs"][0], doc["runs"][1]
    assert (a_run["arm"], b_run["arm"]) == ("A", "B")
    folder = tmp_path / "series"
    # A: exactly the Run helper's runner command for that label and stop file (player mode)
    want_a = fr.command(fr.FLOWS["xmas_dun02_rogue"], "s-r01A", folder / "s-r01A.STOP", vals)
    assert a_run["argv"] == want_a and "--player-mode" in want_a
    assert want_a[want_a.index("--minutes") + 1] == "20"
    # B: the player of the box with those settings as its runner config, M minutes
    want_b = fr.play_command(folder / "project.json", "xmas_dun02", "s-r02B",
                             folder / "s-r02B.STOP", 1200, doc["project_hash"],
                             folder / "runner-config.json")  # fmt: skip
    assert b_run["argv"] == want_b
    # its hunt core's runner argv is A's but for its label and stop (the same settings)
    text = ab.project_text(20)
    assert json.loads(text)["max_runtime_s"] == 1200
    prep = fp.prepare(text, "xmas_dun02", 1200, runner_vals={"xmas_dun02": vals},
                      want_hash=doc["project_hash"])  # fmt: skip
    assert isinstance(prep, fp.Prepared)
    hunt = prep.runners["xmas_dun02"].argv("s-r02B-hunt1", folder / "s-r02B.STOP", None)
    sub = {"s-r01A": "s-r02B-hunt1", str(folder / "s-r01A.STOP"): str(folder / "s-r02B.STOP")}
    assert hunt == [sub.get(x, x) for x in want_a[9:]]  # want_a[:9]: nice, uv, the script, run
    assert not list(folder.parent.glob("series"))  # the plan writes nothing


def test_a_plan_refuses_before_any_input_when_the_box_cannot_play(
    tmp_path: Path, monkeypatch: Any
) -> None:
    d = json.loads(ab.PROJECT.read_text())
    surv = next(t for t in d["nodes"][0]["tabs"] if t["name"] == "survival")
    surv["defs"][0]["body"] = [{"kind": "wait_until", "cond": {"kind": "lit", "value": False},
                                "timeout_s": 1.0, "outcome_to": None}]  # fmt: skip
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(d))
    monkeypatch.setattr(ab, "PROJECT", bad)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path / "x", config_dir=tmp_path)
    assert isinstance(got, str) and "refused before any input" in got


# --- the score -----------------------------------------------------------------------------------
NS = 1_000_000_000


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * NS), "kind": kind, **kw}


def session(demo: Path, name: str, events: list[dict[str, Any]]) -> None:
    d = demo / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def runner_events(minutes: float, kills: int, *, potions: int = 0,
                  flies: tuple[str, ...] = (), deaths: int = 0, hp_low: int = 60,
                  loot: int = 0) -> list[dict[str, Any]]:  # fmt: skip
    out = [ev(0, "run_start"), ev(1, "hp_read", pct=100), ev(2, "hp_read", pct=hp_low)]
    out += [ev(3 + i, "kill") for i in range(kills)]
    out += [ev(3 + i, "loot_step") for i in range(loot)]
    out += [ev(5 + i, "press", what="potion", key="F1", why="hp 0.35") for i in range(potions)]
    for i, why in enumerate(flies):
        if why == "garm":
            out += [ev(9 + i, "garm_seen"), ev(9.3 + i, "press", what="fly", key="F8", why="boss")]
        else:
            out.append(ev(9 + i, "press", what="fly", key="F8", why=why))
    out += [ev(30, "death") for _ in range(deaths)]
    out.append(ev(minutes * 60, "run_end", reason="death" if deaths else "time_box"))
    return out


def test_fly_causes_from_the_runners_own_words_and_the_boxs() -> None:
    assert ab.fly_cause("box fly_away (hp_percent 100, sees_boss True)", False) == "boss"
    assert ab.fly_cause("box fly_away (hp_percent 24, sees_boss False)", False) == "hp"
    assert ab.fly_cause("boss", False) == "boss" and ab.fly_cause("boss", True) == "garm"
    assert ab.fly_cause("hp 0.18", False) == "hp" and ab.fly_cause("rate 300 at hp 0.4",
                                                                   False) == "rate"  # fmt: skip
    assert [ab.fly_cause(w, False) for w in ("pos_unread", "end", "unreach", "dead_end",
                                             "?")] == ["pos_unread", "end", "unreach", "stuck",
                                                       "other"]  # fmt: skip


def _series(tmp_path: Path, a_kills: list[int], b_kills: list[int], **b_extra: Any
            ) -> tuple[list[ab.Score], Path]:  # fmt: skip
    demo = tmp_path / "demo"
    runs = ab.series("s", len(a_kills))
    i_a = i_b = 0
    for r in runs:
        if r.arm == "A":
            session(demo, f"T-demo-dungeon-rogue-xmas_dun02-patrol-P2-{r.label}",
                    runner_events(20, a_kills[i_a], loot=a_kills[i_a]))  # fmt: skip
            i_a += 1
        else:
            session(demo, f"T-demo-dungeon-rogue-xmas_dun02-patrol-P2-{r.label}-hunt1",
                    runner_events(20, b_kills[i_b], loot=b_kills[i_b], **b_extra))  # fmt: skip
            session(demo, f"T-play-{r.label}", [
                ev(0, "run_start"), ev(5, "event", event="drink", **{"in": "hunt"}),
                ev(9, "event", event="fly_away", **{"in": "hunt"}),
                ev(1300, "run_end", reason="relocate_no_block", words="w")])  # fmt: skip
            i_b += 1
    docs = [{"label": r.label, "arm": r.arm, "pair": r.pair} for r in runs]
    return [ab.score_run(x, demo) for x in docs], demo


def test_the_score_reads_each_runs_runner_session_and_the_boxs_events(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    session(demo, "T-demo-dungeon-rogue-xmas_dun02-patrol-P2-s-r01A",
            runner_events(20, 50, potions=2, flies=("hp 0.18", "garm", "end"), hp_low=31,
                          loot=40))  # fmt: skip
    session(demo, "T-demo-dungeon-rogue-xmas_dun02-patrol-P2-s-r02B-hunt1",
            runner_events(20, 46, flies=("box fly_away (hp_percent 90, sees_boss True)",),
                          hp_low=44))  # fmt: skip
    session(
        demo,
        "T-play-s-r02B",
        [
            ev(5, "event", event="fly_away", **{"in": "hunt"}),
            ev(6, "event", event="drink"),  # outside the hunt: not B's
            ev(9, "run_end", reason="x", words="The time box ended."),
        ],
    )
    a = ab.score_run({"label": "s-r01A", "arm": "A", "pair": 1}, demo)
    b = ab.score_run({"label": "s-r02B", "arm": "B", "pair": 1}, demo)
    assert (a.found, a.minutes, a.kills, a.loot_steps, a.potions, a.hp_low) == (
        True, 20.0, 50, 40, 2, 31)  # fmt: skip
    assert a.flies == {"hp": 1, "garm": 1, "end": 1} and a.flies_no_end == 2
    assert a.per_h(a.kills) == 150.0
    assert (b.kills, b.flies, b.box_fired, b.words) == (46, {"boss": 1}, {"fly_away": 1},
                                                        "The time box ended.")  # fmt: skip
    assert "s-r02B" in ab.table([a, b]) and "fly_away 1" in ab.table([a, b])


def test_the_verdict_applies_the_pre_registered_bar(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    ok, _ = _series(tmp_path / "p", [150, 140, 160, 150], [148, 145, 152, 151])
    v = ab.verdict(ok, 20)
    assert v["verdict"] == "PASS" and v["pairs_valid"] == 4
    assert v["lines"]["deaths"] == {"A": 0, "B": 0, "pass": True}
    assert v["lines"]["kills_h"]["pairs"] == [-6.0, 15.0, -24.0, 3.0]  # B - A, kills / h
    # B dies: FAIL whatever the kills
    (tmp_path / "d").mkdir()
    dead, _ = _series(tmp_path / "d", [50, 50, 50], [50, 50, 50], deaths=1)
    assert ab.verdict(dead, 20)["verdict"] == "FAIL"
    # B much slower in every pair: FAIL on kills / h
    (tmp_path / "s").mkdir()
    slow, _ = _series(tmp_path / "s", [50, 52, 51], [30, 31, 29])
    out = ab.verdict(slow, 20)
    assert out["verdict"] == "FAIL" and out["lines"]["kills_h"]["pass"] is False
    # too many potions in B: FAIL; within the margin: not judged against
    (tmp_path / "q").mkdir()
    pots, _ = _series(tmp_path / "q", [50, 50, 50], [50, 50, 50], potions=3)  # 9 / h over A's 0
    assert ab.verdict(pots, 20)["lines"]["potions_h"]["pass"] is False
    # two pairs: kills / h not judged -> INCONCLUSIVE (nothing failed)
    (tmp_path / "t").mkdir()
    two, _ = _series(tmp_path / "t", [50, 50], [50, 50])
    t = ab.verdict(two, 20)
    assert t["verdict"] == "INCONCLUSIVE" and t["lines"]["kills_h"]["pass"] is None
    # a run that did not run its minutes is invalid and takes its pair out
    short = [*ok]
    short[0].minutes = 10.0
    assert ab.verdict(short, 20)["pairs_valid"] == 3 and short[0].label in ab.verdict(
        short, 20)["invalid"]  # fmt: skip


def test_the_warp_takes_the_other_cell_when_the_guards_own_history_would_refuse_it() -> None:
    # 2026-11-14 00:38: stage 1's two setups had typed the first cell twice (the guard's state
    # is per host), so the series' first warp would have been the 3rd identical line in a row
    a, b = ab.warp_lines(2, dh.PATROL_START["xmas_dun02"])
    hist = ab.guard_history({"chat": {"text": a, "count": 2}, "last_t": 1.0})
    assert hist == [a, a]
    assert ab.pick_warp(a, b, hist) == b
    assert ab.pick_warp(b, a, hist) == b  # the planned cell when it is not the repeated one
    assert ab.pick_warp(a, b, ab.guard_history({"chat": {"text": a, "count": 1}})) == a
    assert ab.guard_history({}) == [] and ab.guard_history({"chat": "x"}) == []


def test_the_setup_heals_her_when_her_hp_is_not_full_or_unread() -> None:
    # 2026-11-14 01:00: run 1 (A) died to the MVP; she respawned with almost no HP and run 2 (B)
    # met the player's built-in hp_critical at once
    assert ab.needs_heal(None) and ab.needs_heal(3) and ab.needs_heal(ab.HEAL_BELOW - 1)
    assert not ab.needs_heal(ab.HEAL_BELOW) and not ab.needs_heal(100)
    assert ab.guard_ok(["@warp xmas_dun02 7 21", "@heal", "@warp xmas_dun02 114 23", "@heal"])
