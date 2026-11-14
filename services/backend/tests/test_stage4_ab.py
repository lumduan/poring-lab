"""scripts/stage4_ab.py (live-blocks.md 3.4: stage 4a's A/B, the stage-3 box vs the stage-4a box, an
equivalence check): its PURE parts only -- the series' plan, the arms' commands, the score and the
pre-registered verdict. Nothing here reads a screen or opens an input path."""

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
import stage4_ab as ab  # noqa: E402

from poring_flow import recipes as rc  # noqa: E402


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * 1e9), "kind": kind, **kw}


def session(demo: Path, name: str, events: list[dict[str, Any]]) -> None:
    d = demo / name
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def runner_events(minutes: float, kills: int, steals: int, *, loot: int | None = None,
                  openers: int | None = None, deaths: int = 0, asks: bool = False,
                  mismatch: int = 0, species: tuple[str, ...] = ("mystcase", "cookie"),
                  ) -> list[dict[str, Any]]:  # fmt: skip
    """One runner session: kills, loot steps, a Knife cycle per steal (an opener, then the swap
    back on the popup 1.4 s later), extra openers with no steal, a box strike per opener (its
    species from ``species``, in turn) and -- ``asks`` (B4) -- a recipe record at each lock."""
    out = [ev(0, "run_start")]
    out += [ev(10 + i, "kill") for i in range(kills)]
    out += [ev(11 + i, "loot_step") for i in range(kills if loot is None else loot)]
    n_open = steals if openers is None else openers
    for i in range(n_open):
        t = 20 + 3 * i
        sp = species[i % len(species)]
        out.append(ev(t - 0.5, "box_target", struck=True, pick={"species": sp, "d": 100}))
        if asks:
            out.append(ev(t - 0.4, "recipe", species=sp, by="box", knife=True,
                          function=f"attack_{sp}", **({"mismatch": True} if i < mismatch
                                                      else {})))  # fmt: skip
        out.append(ev(t, "bare", what="opener", ok=True, ms=300))
        if i < steals:
            out.append(ev(t + 1.4, "bare", what="equip", why="popup", ok=True, ms=250))
    out += [ev(40, "death") for _ in range(deaths)]
    out.append(ev(minutes * 60, "run_end", reason="death" if deaths else "time_box"))
    out.append(ev(minutes * 60 + 1, "player_home", pressed=True, back_s=4.0))
    return out


def test_the_series_alternates_b3_and_b4_with_stage2_abs_warp_cells() -> None:
    runs = ab.series("s", 4)
    assert [r.arm for r in runs] == ["B3", "B4", "B4", "B3", "B3", "B4", "B4", "B3"]
    assert [r.label for r in runs][:3] == ["s-r01B3", "s-r02B4", "s-r03B4"]
    assert [r.warp for r in runs] == [r.warp for r in s2.series("s", 4)]  # the same setup lines


def test_both_arms_play_through_the_player_with_the_same_runner_settings(tmp_path: Path) -> None:
    folder = tmp_path / "series"
    doc = ab.plan_doc("s", 2, 20, "alternate", folder)
    assert isinstance(doc, dict), doc
    assert doc["version"] == "9.51" == rc.VERSION
    b3, b4 = doc["arms"]["B3"], doc["arms"]["B4"]
    assert (b3["box_model"], b3["box_recipes"]) == (None, {})
    assert b4["box_model"] == "xmas02" and b4["default_species"] == []
    assert set(b4["box_recipes"]) == {"mystcase", "cruiser", "cookie", "cookie_xmas"}
    assert set(b4["box_plays"]) == set(b3["box_plays"]) | {"model", "recipes"}
    assert b4["box_roles"] == b3["box_roles"] and b4["box_events"] == b3["box_events"]
    for r in doc["runs"]:
        assert r["argv"] == fr.play_command(
            folder / f"project-{r['arm']}.json", "xmas_dun02", r["label"],
            folder / f"{r['label']}.STOP", 1200, doc["arms"][r["arm"]]["project_hash"],
            folder / "runner-config.json")  # fmt: skip
    argvs = []
    for arm, path in ab.PROJECTS.items():
        text = s2.project_text(20, path)
        prep = fp.prepare(text, "xmas_dun02", 1200, runner_vals={"xmas_dun02": doc["vals"]},
                          want_hash=doc["arms"][arm]["project_hash"])  # fmt: skip
        assert isinstance(prep, fp.Prepared)
        argvs.append(prep.runners["xmas_dun02"].argv("x-hunt1", folder / "x.STOP", None))
    assert argvs[0] == argvs[1]  # the same runner argv: only the box's arguments differ
    assert not folder.exists()  # the plan writes nothing


def test_b4_must_be_todays_technique() -> None:
    today = {"function": "attack_cookie", "steps": list(ab.TODAY), "knife": True, "priority": 1.0}
    assert ab.not_today({"cookie": today}, []) is None
    assert ab.not_today({"cookie": {**today, "priority": None}}, ["mystcase"]) is None
    plain = {**today, "steps": list(rc.PLAIN_SHAPE), "knife": False}
    assert "not today's" in str(ab.not_today({"cookie": plain}, []))
    assert "priority 3" in str(ab.not_today({"cookie": {**today, "priority": 3}}, []))
    assert "no recipe at all" in str(ab.not_today({}, ["cookie"]))
    assert tuple(ab.TODAY) == rc.KNIFE_SHAPE


def test_the_score_reads_the_recipes_and_the_species_of_the_strikes(tmp_path: Path) -> None:
    demo = tmp_path / "demo"
    session(demo, "T-demo-dungeon-rogue-xmas_dun02-patrol-P2-s-r02B4-hunt1",
            runner_events(20, 40, 12, loot=30, openers=14, asks=True, mismatch=1))  # fmt: skip
    session(demo, "T-play-s-r02B4", [ev(9, "run_end", reason="max_runtime", words="w")])
    sc = ab.score_run({"label": "s-r02B4", "arm": "B4", "pair": 1}, demo)
    assert (sc.kills, sc.loot_steps, sc.openers, sc.steals) == (40, 30, 14, 12)
    assert (sc.recipes, sc.recipe_mismatch, sc.recipe_no_knife) == (14, 1, 0)
    assert sc.recipe_species == {"mystcase": 7, "cookie": 7} == sc.struck_species
    doc = sc.doc()
    assert doc["loot_h"] == 90.0 and doc["openers_h"] == 42.0 and doc["steals_h"] == 36.0
    assert "s-r02B4" in ab.table([sc])


def _series(tmp_path: Path, b3: list[dict[str, Any]], b4: list[dict[str, Any]]) -> list[Any]:
    demo = tmp_path / "demo"
    runs = ab.series("s", len(b3))
    i = {"B3": 0, "B4": 0}
    for r in runs:
        kw = (b3 if r.arm == "B3" else b4)[i[r.arm]]
        i[r.arm] += 1
        session(
            demo,
            f"T-demo-dungeon-rogue-xmas_dun02-patrol-P2-{r.label}-hunt1",
            runner_events(20, **{**kw, "asks": r.arm == "B4" and kw.get("asks", True)}),
        )
    return [ab.score_run({"label": r.label, "arm": r.arm, "pair": r.pair}, demo) for r in runs]


def test_the_verdict_applies_the_pre_registered_bar(tmp_path: Path) -> None:
    same = [{"kills": 50, "steals": 15}] * 4
    (tmp_path / "p").mkdir()
    v = ab.verdict(_series(tmp_path / "p", same, same), 20)
    assert v["verdict"] == "PASS" and v["pairs_valid"] == 4, v
    assert v["lines"]["recipes"]["pass"] is True and v["lines"]["recipes"]["B4_asked"] == 60
    assert v["lines"]["openers_h"] == {"B3": 45.0, "B4": 45.0, "pass": True}
    rep = v["lines"]["report"]
    assert (
        rep["struck_species"]["B3"] == rep["struck_species"]["B4"] == {"cookie": 28, "mystcase": 32}
    )
    assert rep["recipe_species_B4"] == {"cookie": 28, "mystcase": 32}
    # fewer loot steps in every pair: FAIL on loot / h
    (tmp_path / "l").mkdir()
    few = [{"kills": 50, "steals": 15, "loot": n} for n in (30, 32, 28)]
    out = ab.verdict(_series(tmp_path / "l", same[:3], few), 20)
    assert out["verdict"] == "FAIL" and out["lines"]["loot_h"]["pass"] is False
    # more openers than the margin (a swap a lock where B3 swapped fewer): FAIL
    (tmp_path / "o").mkdir()
    more = [{"kills": 50, "steals": 15, "openers": 22}] * 3
    out = ab.verdict(_series(tmp_path / "o", same[:3], more), 20)
    assert out["lines"]["openers_h"]["pass"] is False and out["verdict"] == "FAIL"
    # a lock's answer was not the plan: FAIL (the recipes line)
    (tmp_path / "m").mkdir()
    odd = [{"kills": 50, "steals": 15, "mismatch": 1}, *same[:2]]
    out = ab.verdict(_series(tmp_path / "m", same[:3], odd), 20)
    assert out["lines"]["recipes"]["pass"] is False
    # B4 struck but never asked the box: FAIL
    (tmp_path / "n").mkdir()
    silent = [{"kills": 50, "steals": 15, "asks": False}, *same[:2]]
    out = ab.verdict(_series(tmp_path / "n", same[:3], silent), 20)
    assert out["lines"]["recipes"]["pass"] is False
    # a death more in B4: FAIL
    (tmp_path / "d").mkdir()
    dead = [{"kills": 50, "steals": 15, "deaths": 1}, *same[:2]]
    out = ab.verdict(_series(tmp_path / "d", same[:3], dead), 20)
    assert out["lines"]["deaths"]["pass"] is False
    # two pairs: kills, steals and loot not judged -> INCONCLUSIVE
    (tmp_path / "t").mkdir()
    t = ab.verdict(_series(tmp_path / "t", same[:2], same[:2]), 20)
    assert t["verdict"] == "INCONCLUSIVE" and t["lines"]["kills_h"]["pass"] is None
    assert ab.BAR["openers_h_share"] == 0.20 and ab.BAR["min_pairs"] == 3
