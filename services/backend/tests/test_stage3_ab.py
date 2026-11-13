"""scripts/stage3_ab.py (live-blocks.md 3.3: stage 3's A/B, the stage-2 box vs the stage-3 box): its
PURE parts only -- the series' plan, the arms' commands, the score and the pre-registered verdict.
Nothing here reads a screen or opens an input path."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_play as fp  # noqa: E402
import flow_run as fr  # noqa: E402
import stage2_ab as s2  # noqa: E402
import stage3_ab as ab  # noqa: E402


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * 1e9), "kind": kind, **kw}


def session(demo: Path, name: str, events: list[dict[str, Any]]) -> None:
    d = demo / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def runner_events(minutes: float, kills: int, steals: int, *, fails: int = 0, deaths: int = 0,
                  respawned: bool = True, home: bool = True, weight: float = 0.42,
                  weight_end: str | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """One runner session: kills, a Knife cycle per steal (the opener, then the swap back on the
    popup 1.4 s later), failed openers, a weight read, the player end (a death's respawn, or the
    way home)."""
    out = [ev(0, "run_start")]
    out += [ev(10 + i, "kill") for i in range(kills)]
    for i in range(steals):
        t = 20 + 3 * i
        out += [
            ev(t, "bare", what="opener", ok=True, ms=300),
            ev(t + 1.4, "bare", what="equip", why="popup", ok=True, ms=250),
        ]
    out += [ev(15 + i, "bare", what="opener", ok=False, ms=900) for i in range(fails)]
    out.append(ev(30, "weight", share=weight, red=False))
    if weight_end is not None:
        out.append(ev(31, "weight_home", share=weight, by=weight_end))
    out += [ev(40, "death") for _ in range(deaths)]
    end = "death" if deaths else ("weight_home: x" if weight_end else "time_box")
    out.append(ev(minutes * 60, "run_end", reason=end))
    if deaths:
        out.append(ev(minutes * 60 + 1, "player_respawn", pressed=True,
                      back_s=3.2 if respawned else None))  # fmt: skip
    else:
        out.append(ev(minutes * 60 + 1, "player_home", pressed=home, back_s=4.0 if home else None))
    return out


def test_the_series_alternates_b2_and_b3_with_stage2_abs_warp_cells() -> None:
    runs = ab.series("s", 4)
    assert [r.arm for r in runs] == ["B2", "B3", "B3", "B2", "B2", "B3", "B3", "B2"]
    assert [r.label for r in runs][:3] == ["s-r01B2", "s-r02B3", "s-r03B3"]
    assert [r.warp for r in runs] == [r.warp for r in s2.series("s", 4)]  # the same setup lines


def test_both_arms_play_through_the_player_with_the_same_runner_settings(tmp_path: Path) -> None:
    folder = tmp_path / "series"
    doc = ab.plan_doc("s", 2, 20, "alternate", folder, config_dir=tmp_path)
    assert isinstance(doc, dict), doc
    assert doc["version"] == "9.50"
    b2, b3 = doc["arms"]["B2"], doc["arms"]["B3"]
    assert (b2["box_plays"], b2["box_roles"], b2["calls"]) == (
        ["boss_fly", "fly_hp", "potion"], {}, {})  # fmt: skip
    assert set(b3["box_plays"]) == {"boss_fly", "fly_hp", "potion", "knife", "respawn",
                                    "weight_home", "home_end"}  # fmt: skip
    assert b3["box_events"] == ["fly_away", "drink", "bag_full"]
    for r in doc["runs"]:
        assert r["argv"] == fr.play_command(
            folder / f"project-{r['arm']}.json", "xmas_dun02", r["label"],
            folder / f"{r['label']}.STOP", 1200, doc["arms"][r["arm"]]["project_hash"],
            folder / "runner-config.json")  # fmt: skip
    # the two hunt cores' runner argv are the same (the same settings, the same five keys)
    argvs = []
    for arm, path in ab.PROJECTS.items():
        text = s2.project_text(20, path)
        prep = fp.prepare(text, "xmas_dun02", 1200, runner_vals={"xmas_dun02": doc["vals"]},
                          want_hash=doc["arms"][arm]["project_hash"])  # fmt: skip
        assert isinstance(prep, fp.Prepared)
        argvs.append(prep.runners["xmas_dun02"].argv("x-hunt1", folder / "x.STOP", None))
    assert argvs[0] == argvs[1]
    assert not folder.exists()  # the plan writes nothing


def test_the_score_reads_the_knife_the_exits_and_the_weight(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    session(
        demo,
        "T-demo-dungeon-rogue-xmas_dun02-patrol-P2-s-r02B3-hunt1",
        [
            *runner_events(20, 40, 12, fails=1, weight=0.52, weight_end="box"),
            ev(5, "box_call", role="knife_on"),
            ev(6, "box_call", role="knife_back"),
        ],
    )
    session(demo, "T-play-s-r02B3", [ev(5, "event", event="bag_full", **{"in": "hunt"}),
                                     ev(9, "run_end", reason="home", words="w")])  # fmt: skip
    sc = ab.score_run({"label": "s-r02B3", "arm": "B3", "pair": 1}, demo)
    assert (sc.kills, sc.openers, sc.opener_fails, sc.swaps_back, sc.steals) == (40, 12, 1, 12, 12)
    assert sc.steal_s == [1.4] * 12 and sc.equip_ms == [250] * 12
    assert (sc.home_pressed, sc.home_arrived, sc.weight_max, sc.weight_end) == (1, 1, 0.52, "box")
    assert sc.calls == {"knife_on": 1, "knife_back": 1} and sc.box_fired == {"bag_full": 1}
    doc = sc.doc()
    assert doc["steals_h"] == 36.0 and doc["swap_fails_h"] == 3.0 and doc["steal_s_median"] == 1.4
    assert "s-r02B3" in ab.table([sc])


def _series(tmp_path: Path, b2: list[dict[str, Any]], b3: list[dict[str, Any]]) -> list[Any]:
    demo = tmp_path / "demo"
    runs = ab.series("s", len(b2))
    i = {"B2": 0, "B3": 0}
    for r in runs:
        kw = (b2 if r.arm == "B2" else b3)[i[r.arm]]
        i[r.arm] += 1
        session(demo, f"T-demo-dungeon-rogue-xmas_dun02-patrol-P2-{r.label}-hunt1",
                runner_events(20, **kw))  # fmt: skip
    return [ab.score_run({"label": r.label, "arm": r.arm, "pair": r.pair}, demo) for r in runs]


def test_the_verdict_applies_the_pre_registered_bar(tmp_path: Path) -> None:
    same = [{"kills": 50, "steals": 15}] * 4
    (tmp_path / "p").mkdir()
    v = ab.verdict(_series(tmp_path / "p", same, same), 20)
    assert v["verdict"] == "PASS" and v["pairs_valid"] == 4
    assert v["not_exercised"] == ["respawn", "weight"]  # no death, no heavy bag: not judged
    assert v["lines"]["home"] == {"B2": 1.0, "B3": 1.0, "pass": True}
    rep = v["lines"]["report"]
    assert rep["steal_share"] == {"B2": 1.0, "B3": 1.0} and rep["steal_s_median"]["B3"] == 1.4
    # fewer steals in every pair: FAIL on steals / h
    (tmp_path / "s").mkdir()
    few = [{"kills": 50, "steals": s} for s in (8, 9, 7)]
    out = ab.verdict(_series(tmp_path / "s", same[:3], few), 20)
    assert out["verdict"] == "FAIL" and out["lines"]["steals_h"]["pass"] is False
    # B3 died and did not arrive: FAIL (respawn, and deaths)
    (tmp_path / "d").mkdir()
    dead = [{"kills": 50, "steals": 15, "deaths": 1, "respawned": False}, *same[:2]]
    out = ab.verdict(_series(tmp_path / "d", same[:3], dead), 20)
    assert out["lines"]["respawn"]["pass"] is False and out["verdict"] == "FAIL"
    # a heavy bag the RUNNER ended in B3 (not the box's event): FAIL on the weight line
    (tmp_path / "w").mkdir()
    heavy = [{"kills": 50, "steals": 15, "weight": 0.55, "weight_end": "runner"}, *same[:2]]
    out = ab.verdict(_series(tmp_path / "w", same[:3], heavy), 20)
    assert out["lines"]["weight"]["pass"] is False
    # the box's weight home: a valid run though it ended early
    (tmp_path / "e").mkdir()
    early = [{"kills": 20, "steals": 6, "weight": 0.52, "weight_end": "box"}, *same[:2]]
    scores = _series(tmp_path / "e", same[:3], early)
    scores[1].minutes = 8.0  # it went home after 8 minutes
    out = ab.verdict(scores, 20)
    assert out["pairs_valid"] == 3 and out["lines"]["weight"]["pass"] is True
    # failed swaps over the margin: FAIL
    (tmp_path / "f").mkdir()
    bad = [{"kills": 50, "steals": 15, "fails": 2}] * 3  # 6 / h over B2's 0
    out = ab.verdict(_series(tmp_path / "f", same[:3], bad), 20)
    assert out["lines"]["swap_fails_h"]["pass"] is False
    # two pairs: kills and steals not judged -> INCONCLUSIVE
    (tmp_path / "t").mkdir()
    t = ab.verdict(_series(tmp_path / "t", same[:2], same[:2]), 20)
    assert t["verdict"] == "INCONCLUSIVE" and t["lines"]["kills_h"]["pass"] is None
    assert ab.BAR["weight_line"] == 0.50 and ab.VERSION == "9.50"
