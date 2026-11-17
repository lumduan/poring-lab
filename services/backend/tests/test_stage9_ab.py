"""scripts/stage9_ab.py: s9ab, the Goblin model's live A/B (live-blocks.md 18.15) -- the ready-made
box naming xmas02 (A, xmas02-gb) against it naming xmas02sk (B): the plan's refusals before any
input (the arms differ in the box's model alone; the four proofs), the packets' truth of a boss Fly
Wing (on screen, S7.1's post-vanish windows), the party's visits, the judged lines (deaths, false
Fly Wings an hour against the pre-registered margin, the model each run loaded). NOT run live."""

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
import stage9_ab as ab  # noqa: E402
import unit_detector as ud  # noqa: E402

S = 1_000_000_000


def _bases() -> dict[str, str]:
    try:
        return {k: hc.git_show(rev, hc.TARGET) for k, rev in (
            ("drive", hc.DRIVE_BASE), ("check", hc.BASE_REV), ("flag", hc.FLAG_BASE),
            ("pick", hc.PICK_BASE))}  # fmt: skip
    except (subprocess.CalledProcessError, OSError):
        pytest.skip("git cannot show the bases here (a shallow checkout)")


# --- the plan ------------------------------------------------------------------------------------
def test_the_plan_alternates_two_copies_differing_in_the_boxs_model_alone(tmp_path: Path) -> None:
    doc = ab.plan_doc("s", 4, 20, "alternate", tmp_path / "s", bases=_bases(), seeds=3)
    assert isinstance(doc, dict), doc
    assert [r["arm"] for r in doc["runs"]] == ["A", "B", "B", "A", "A", "B", "B", "A"]
    assert doc["vals"]["A"] == doc["vals"]["B"]
    assert doc["vals"]["A"]["fly_first"] is True and doc["vals"]["A"]["fly_first_hp"] is True
    ma, mb = (doc["arms"][x]["box"]["box_model"] for x in ("A", "B"))
    assert (ma["id"], mb["id"]) == ("xmas02", "xmas02sk")
    assert ma["file"] == ud.MAP_REFERENCES["xmas_dun02"][0].onnx
    assert mb["file"] == ud.MAP_MODELS["xmas_dun02"].onnx
    assert "alarm" not in ma and mb["alarm"] == [
        "garm_baby",
        "g_gobline_xmas",
        "knight_of_windstorm",
    ]
    assert {k for k in set(ma) | set(mb) if ma.get(k) != mb.get(k)} <= set(ab.MODEL_KEYS)
    assert doc["pick_base"] == hc.PICK_BASE and doc["bar"]["false_fly_margin_h"] == 6.2
    for r in doc["runs"]:
        assert str(tmp_path / "s" / f"runner-config-{r['arm']}.json") in r["argv"]


def test_the_arms_differ_in_their_use_model_alone() -> None:
    a, b = ab.arm_doc("A", 20), ab.arm_doc("B", 20)
    assert ab.box_difference(a, b) is None
    assert "does not name xmas02sk" in str(ab.box_difference(a, a))
    off = json.loads(json.dumps(b))
    next(t for t in off["nodes"][0]["tabs"] if t["name"] == "safety")["vars"]["fly_first_hp"] = {
        "kind": "lit", "value": False}  # fmt: skip
    assert "fly_first_hp = True" in str(ab.box_difference(a, off))
    other = json.loads(json.dumps(b))
    other["max_runtime_s"] = 60
    assert "more than its use_model" in str(ab.box_difference(a, other))


def test_the_model_check_refuses_anything_but_the_models_own_facts() -> None:
    a, b = ab.arm_doc("A", 20), ab.arm_doc("B", 20)
    import flow_play as fp

    from poring_flow import project as pj

    box = {}
    for x, d in (("A", a), ("B", b)):
        text = pj.to_json(pj.validate(d))
        box[x] = fp.prepare(text, ab.NODE, 1200).runners[ab.NODE].box_kwargs()  # type: ignore[union-attr]
    assert ab.model_problems(box) is None
    bad = json.loads(json.dumps(box))
    bad["B"]["box_model"]["strikes"] = ["mystcase"]
    assert "differ beyond" in str(ab.model_problems(bad))
    bad = json.loads(json.dumps(box))
    bad["B"]["box_model"]["alarm"] = ["garm_baby"]
    assert "alarm classes" in str(ab.model_problems(bad))
    bad = json.loads(json.dumps(box))
    bad["A"]["box_model"]["file"] = "xmas02-last-736x1280.onnx"  # the 11-07 model: rollback only
    assert "is not a model the runner's box detector loads" in str(ab.model_problems(bad))
    bad = json.loads(json.dumps(box))
    bad["B"]["box_recipes"] = {}
    assert "besides box_model" in str(ab.model_problems(bad))


def test_the_plan_refuses_an_old_runner_a_failed_pick_proof_or_no_margin(tmp_path: Path) -> None:
    bases = _bases()
    text = hc.TARGET.read_text()
    old = text.replace('MODEL_PICK_VERSION = "9.59"', 'MODEL_PICK_VERSION = "9.58"', 1)
    got = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=old, bases=bases, seeds=0)
    assert isinstance(got, str) and "is not dungeon@9.59" in got
    bent = text.replace("FF_REARM_S = 1.0", "FF_REARM_S = 1.5", 1)  # a 9.57 line, no branch
    got2 = ab.plan_doc("s", 1, 20, "alternate", tmp_path, runner_text=bent, bases=bases, seeds=0)
    assert isinstance(got2, str) and "huntstate_check" in got2 and "fails" in got2
    got3 = ab.plan_doc("s", 1, 20, "alternate", tmp_path, bases=bases, seeds=0,
                       bar={**ab.BAR, "false_fly_margin_h": None})  # fmt: skip
    assert isinstance(got3, str) and "margin is not set" in got3


# --- the truth -----------------------------------------------------------------------------------
def _packets(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    base = [{"type": "map_change", "map": "xmas_dun02.gat", "x": 100, "y": 100, "t_mono_ns": 1 * S}]
    return sorted([*base, *extra], key=lambda p: p["t_mono_ns"])


def _appear(gid: int, job: int, x: int, y: int, t: float) -> dict[str, Any]:
    return {"type": "entity_appear", "gid": gid, "job": job, "objtype": 5, "kind": "stand",
            "x": x, "y": y, "x1": None, "y1": None, "speed": 400, "effect_state": 0, "name": "u",
            "heading": 0, "move_start_tick": None, "t_mono_ns": int(t * S)}  # fmt: skip


def _vanish(gid: int, reason: int, t: float) -> dict[str, Any]:
    return {"type": "entity_vanish", "gid": gid, "reason": reason, "t_mono_ns": int(t * S)}


def _ff(t: float, src: str = "alarm", cls: str | None = "garm_baby", **kw: Any) -> dict[str, Any]:
    sight = {"t_ns": int(t * S), "cls": cls, "score": 0.9} if src == "alarm" else None
    return {"kind": "fly_first", "what": "fly", "why": "garm" if src == "alarm" else "boss",
            "src": src, "t_read_ns": int((t + 0.2) * S), "t_key_ns": int((t + 0.2) * S),
            "sight": sight, "t_ns": int((t + 0.3) * S), **kw}  # fmt: skip


def test_the_truth_sees_an_alarm_unit_on_screen_and_the_post_vanish_window() -> None:
    pk = _packets(_appear(7, 1515, 103, 104, 2), _appear(8, 1607, 100, 140, 2),
                  _appear(9, 1249, 101, 101, 2), _vanish(7, 1, 20))  # fmt: skip
    tr = ab.Truth(pk)
    assert tr.units_at(10 * S) == [1515]  # the Goblin 40 cells north is off screen; a Myst Case
    assert tr.units_at(10 * S, ab.PARTY) == []  # is no alarm species
    assert tr.units_at(22 * S) == [] and tr.post_vanish(22 * S) and not tr.post_vanish(26 * S)
    flies = ab.boss_flies_of([_ff(10), _ff(22), _ff(30), _ff(40, src="line"),
                              {**_ff(50), "sight": {"hp": True}, "src": "hp"}], tr)  # fmt: skip
    assert [(f.src, f.units, f.post_vanish, f.false) for f in flies] == [
        ("alarm", [1515], False, False), ("alarm", [], True, False), ("alarm", [], False, True),
        ("line", [], False, True)]  # fmt: skip
    assert flies[3].t_ns == int(40.2 * S)  # a line's moment: its read
    dead = ab.boss_flies_of([_ff(30)], tr, deaths=[int(29 * S)])
    assert dead[0].after_death and dead[0].false is None  # after her death: not judged


def test_a_party_visit_and_the_time_to_its_fly_wing() -> None:
    pk = _packets(_appear(8, 1607, 104, 103, 5), _vanish(8, 0, 9),
                  _appear(9, 1251, 105, 99, 30), _vanish(9, 1, 31))  # fmt: skip
    tr = ab.Truth(pk)
    flies = ab.boss_flies_of([_ff(6.5, cls="g_gobline_xmas")], tr)
    vis = ab.visits_of(tr, 1 * S, 40 * S, flies, step_s=0.5)
    assert len(vis) == 2
    # the Goblin appears at 5 s; the first sample that sees it is 5.5 s (the world FRAME_LAG_S
    # earlier, 5.38 s); its Fly Wing's key at 6.7 s
    assert vis[0]["fly_cls"] == "g_gobline_xmas" and vis[0]["to_fly_s"] == pytest.approx(1.2)
    assert vis[1]["fly_src"] is None and vis[1]["to_fly_s"] is None


def test_the_on_screen_envelope_meets_the_game_region() -> None:
    assert ab.on_screen(640, 360) and ab.on_screen(-50, 360) and ab.on_screen(640, 840)
    assert not ab.on_screen(-60, 360) and not ab.on_screen(640, -11) and not ab.on_screen(640, 843)
    proj = ab.camera_project()
    u, v = proj([[0.0, 0.0]])[0]
    assert ab.on_screen(float(u), float(v))  # she is on screen


# --- the verdict ---------------------------------------------------------------------------------
def _sc(label: str, arm: str, pair: int, n_false: int = 0, **kw: Any) -> ab.Score9:
    base = {"found": True, "minutes": 20.0, "kills": 70, "loot_steps": 30, "openers": 60,
            "gaps_ms": [200.0] * 50, "kinds": {"hp_read": 6000, "kill": 70, "drive": 2},
            "drive_starts": 1, "drive_ends": [{"kind": "drive", "what": "end",
                                               "ended": "run_end", "passed": {}}],
            "box_models": [[ud.GPU_WEIGHTS[ab.WEIGHTS[arm]].onnx, ab.WEIGHTS[arm]]],
            "boss": [ab.BossFly(i * S, i * S, "alarm", "garm", "garm_baby", [], False)
                     for i in range(n_false)]}  # fmt: skip
    base.update(kw)
    s = ab.Score9(label, arm, pair)
    for k, v in base.items():
        setattr(s, k, v)
    return s


def test_the_false_fly_line_the_model_line_and_deaths_are_judged() -> None:
    kinds = {"hp_read", "kill"}
    ok = [_sc(f"r{i}{x}", x, i, n_false=1 if x == "A" else 3) for i in (1, 2, 3, 4)
          for x in ("A", "B")]  # fmt: skip
    v = ab.verdict(ok, 20, kinds)
    assert v["verdict"] == "PASS", v["lines"]
    fl = v["lines"]["false_flies_h"]
    assert (fl["A"]["false_h"], fl["B"]["false_h"], fl["margin_h"]) == (3.0, 9.0, 6.2)
    over = [_sc(f"r{i}{x}", x, i, n_false=1 if x == "A" else 4) for i in (1, 2, 3, 4)
            for x in ("A", "B")]  # fmt: skip
    assert ab.verdict(over, 20, kinds)["lines"]["false_flies_h"]["pass"] is False
    wrong = [*ok[:7], _sc("r4B", "B", 4, box_models=[[ud.MAP_REFERENCES["xmas_dun02"][0].onnx,
                                                      "xmas02gb"]])]  # fmt: skip
    vw = ab.verdict(wrong, 20, kinds)
    assert vw["verdict"] == "FAIL" and "r4B" in vw["lines"]["model"]["problems"][0]
    dead = [*ok[:7], _sc("r4B", "B", 4, n_false=3, deaths=1)]
    vd = ab.verdict(dead, 20, kinds)
    assert vd["verdict"] == "FAIL" and vd["lines"]["deaths"]["pass"] is False  # judged here
    both = [*ok[:6], _sc("r4A", "A", 4, n_false=1, deaths=1), _sc("r4B", "B", 4, n_false=3,
                                                                  deaths=1)]  # fmt: skip
    assert ab.verdict(both, 20, kinds)["lines"]["deaths"]["pass"] is True  # <=, not <
    rep = v["lines"]["report"]["alarm"]
    assert rep["B"]["boss_by_src"] == {"alarm": 12} and rep["B"]["sightings_by_cls"] == {
        "garm_baby": 12}  # fmt: skip


def test_the_margin_is_the_larger_of_the_spread_and_the_poisson_bound() -> None:
    got = ab.margin_of([0.0, 3.0, 15.0, 3.0], hours=1.33)
    assert got["sd_h"] == pytest.approx(6.652, abs=0.001)  # the sample SD of the four rates
    assert got["sd_based_h"] == pytest.approx(2 * (2 / 4) ** 0.5 * 6.652, abs=0.01)
    assert got["margin_h"] == 9.5  # rounded up to 0.1
    calm = ab.margin_of([0.0, 0.0, 0.0], hours=1.0)  # no false one banked: one over the hours
    assert calm["pooled_h"] == 1.0 and calm["margin_h"] == pytest.approx(2.5)
