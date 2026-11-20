"""scripts/screen_ab.py: s11scr, the screen-size comparison (docs/planning/screen-size-ab.md) --
the block's runs, the screen refusal before any input, the judged lines. NOT run live here."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_ab as sa  # noqa: E402

CELLS = ((10, 20), (30, 40))


def test_runs_play_the_box_arm_and_name_the_screen() -> None:
    runs = sa.runs_of("s11scr-1080", 3, "1080", CELLS)
    assert [r.label for r in runs] == ["s11scr-1080-r01B", "s11scr-1080-r02B", "s11scr-1080-r03B"]
    assert {r.arm for r in runs} == {sa.BOX_ARM}  # the same box in both blocks
    assert [r.warp for r in runs] == ["@warp xmas_dun02 10 20", "@warp xmas_dun02 30 40",
                                      "@warp xmas_dun02 10 20"]  # fmt: skip
    assert sa.runs_of("s11scr-720", 1, "720", CELLS)[0].label == "s11scr-720-r01A"
    with pytest.raises(ValueError):
        sa.runs_of("x", 0, "720", CELLS)
    with pytest.raises(ValueError):
        sa.runs_of("x", 1, "900", CELLS)


@pytest.mark.parametrize(
    ("screen", "env", "grab", "ok"),
    [
        ("1080", {"SESSION_SIZE": "1920x1080", "GAME_REGION": "0,0,1920,1080"}, (1920, 1080), True),
        ("720", {"SESSION_SIZE": "1280x720", "GAME_REGION": "0, 0, 1280, 720"}, (1280, 720), True),
        ("720", {"SESSION_SIZE": "1920x1080", "GAME_REGION": "0,0,1920,1080"}, (1920, 1080), False),
        (
            "1080",
            {"SESSION_SIZE": "1920x1080", "GAME_REGION": "80,77,1280,720"},
            (1920, 1080),
            False,
        ),
        ("1080", {"SESSION_SIZE": "1920x1080", "GAME_REGION": "0,0,1920,1080"}, (1280, 720), False),
        ("1080", {"SESSION_SIZE": "1920x1080", "GAME_REGION": "0,0,1920,1080"}, None, False),
        ("1080", {}, (1920, 1080), False),
    ],
)
def test_screen_problem(screen: str, env: dict[str, str], grab: Any, ok: bool) -> None:
    why = sa.screen_problem(screen, env, grab)
    assert (why is None) is ok, why


def _base() -> dict[str, Any]:
    return {
        "version": "9.60",
        "arms": {"B": {"project_hash": "h" * 64}},
        "vals": {"B": {"fly_first_land": True}},
        "runner_sha256": "s",
        "drive_base": "d",
    }


def test_plan_doc_one_box_every_run(tmp_path: Path) -> None:
    doc = sa.plan_doc("s11scr-1080", 3, 20, "1080", tmp_path, base=_base())
    assert isinstance(doc, dict)
    assert doc["screen_want"] == {"session": "1920x1080", "region": "0,0,1920,1080"}
    assert len(doc["runs"]) == 3
    for r in doc["runs"]:
        argv = r["argv"]
        assert argv[argv.index("--project-hash") + 1] == "h" * 64
        assert argv[argv.index("--max-s") + 1] == "1200"
        assert argv[argv.index("--label") + 1] == r["label"]
        assert "project-B" in argv[argv.index("--project") + 1]


def test_plan_doc_passes_a_refusal_on() -> None:
    assert sa.plan_doc("x", 1, 20, "720", Path("/nonexistent"), base="refused: why") == (
        "refused: why")  # type: ignore[arg-type]  # fmt: skip


def _run(kills_h: float, loot_h: float = 50.0, *, deaths: int = 0, minutes: float = 20.0,
         rc: int | None = 0, found: bool = True, end: str | None = "time",
         short: bool = False) -> dict[str, Any]:  # fmt: skip
    return {"found": found, "kills_h": kills_h, "loot_h": loot_h, "deaths": deaths,
            "minutes": minutes, "rc": rc, "end": end, "short": short}  # fmt: skip


def test_valid_runs() -> None:
    assert sa.valid(_run(100), 20)
    assert sa.valid(_run(100, minutes=16.0), 20)
    assert not sa.valid(_run(100, minutes=15.9), 20)
    assert sa.valid(_run(100, minutes=12.0, end="weight_home"), 20)  # a valid end, home
    assert not sa.valid(_run(100, rc=1), 20)
    assert not sa.valid(_run(100, found=False), 20)


def test_same_when_nothing_changed() -> None:
    a = [_run(130), _run(140), _run(120)]
    b = [_run(128), _run(142), _run(121)]
    v = sa.verdict(a, b, 20)
    assert v["verdict"] == "SAME", v
    assert v["lines"]["kills_h"]["verdict"] == "PASS"
    assert v["valid"] == [3, 3]


def test_worse_on_a_clear_kills_loss_and_names_the_line() -> None:
    a = [_run(130, 50), _run(132, 52), _run(128, 49)]
    b = [_run(100, 51), _run(102, 50), _run(98, 52)]  # kills down, loot unchanged
    v = sa.verdict(a, b, 20)
    assert v["verdict"] == "WORSE"
    assert v["lines"]["kills_h"]["verdict"] == "FAIL"
    assert v["lines"]["loot_h"]["verdict"] == "PASS"  # the loss is named, not blurred


def test_deaths_and_errors_lines() -> None:
    a = [_run(130), _run(130)]
    v = sa.verdict(a, [_run(130, deaths=1), _run(130)], 20)
    assert v["lines"]["deaths"]["verdict"] == "FAIL" and v["verdict"] == "WORSE"
    v = sa.verdict(a, [_run(130), _run(130, rc=1)], 20)
    assert v["lines"]["errors"]["verdict"] == "FAIL"
    v = sa.verdict([*a, _run(1, rc=1)], [_run(130), _run(130), _run(1, rc=1)], 20)
    assert v["lines"]["errors"]["verdict"] == "PASS"  # A erred as often


def test_inconclusive_under_two_valid_runs() -> None:
    v = sa.verdict([_run(130), _run(130, minutes=5)], [_run(130), _run(131)], 20)
    assert v["lines"]["kills_h"]["verdict"] == "INCONCLUSIVE"
    assert v["verdict"] == "INCONCLUSIVE"


def test_diag_of_counts_the_runner_records() -> None:
    s = 1_000_000_000
    ev = [
        {"t_ns": 0, "kind": "run_start"},
        {
            "t_ns": 1 * s,
            "kind": "box_target",
            "verdicts": ["unknown", "sword"],
            "struck": True,
            "det_ms": 20.0,
            "settle_ms": 1500,
        },
        {
            "t_ns": 2 * s,
            "kind": "box_target",
            "verdicts": ["unknown"],
            "struck": False,
            "det_ms": 30.0,
            "settle_ms": 2500,
        },
        {"t_ns": 3 * s, "kind": "strike", "end": "damage"},
        {"t_ns": 4 * s, "kind": "strike", "end": "bound"},
        {"t_ns": 5 * s, "kind": "kill", "by": "exp_line"},
        {"t_ns": 6 * s, "kind": "scan", "verdicts": {"unknown": 3, "clear": 1}},
        {"t_ns": 7 * s, "kind": "loot_step", "picks": 1, "hovers": 4},
        {"t_ns": 8 * s, "kind": "escape", "why": "garm"},
        {"t_ns": 3600 * s, "kind": "run_end"},
    ]
    d = sa.diag_of(ev)
    assert d["minutes"] == 60.0
    assert d["kills_h"] == 1.0 and d["strikes_per_kill"] == 2.0
    assert d["cursor_box"] == {"sword": 0.333, "unknown": 0.667}
    assert d["cursor_scan"] == {"clear": 0.25, "unknown": 0.75}
    assert d["struck_share"] == 0.5
    assert d["strike_end"] == {"bound": 0.5, "damage": 0.5}
    assert d["picks_per_step"] == 1.0 and d["hovers_per_step"] == 4.0
    assert d["escapes_h"] == {"garm": 1.0}
    assert d["det_ms_median"] == 25.0 and d["settle_ms_median"] == 2000.0


def test_diag_of_empty_is_safe() -> None:
    d = sa.diag_of([])
    assert d["kills_h"] is None and d["cursor_box"] == {} and d["strikes_per_kill"] is None


def test_a_block_names_its_model_xmas02sk_unless_8c_names_the_1080_one(tmp_path: Path) -> None:
    """xmas02-1080-detector.md 8c (Amendment 19): --model sets stage10's box model; the plan keeps
    it; the default is s11scr's."""
    import unit_detector as ud

    # s11scr's xmas02sk (a reference since 2026-11-20); xmas02v1080 the map's own (Amendment 24)
    assert sa.MODELS[0] == "xmas02sk" and "xmas02sk" in [
        m.gpu for m in ud.MAP_REFERENCES["xmas_dun02"]
    ]
    assert ud.MAP_MODELS["xmas_dun02"].gpu == "xmas02v1080"
    before = sa.s10.MODEL
    try:
        sa.use_model("xmas02v1080")
        assert sa.s10.MODEL == "xmas02v1080"
        assert sa.plan_doc("s12x", 3, 20, "1080", tmp_path, base=_base())["model"] == "xmas02v1080"
        with pytest.raises(ValueError):
            sa.use_model("v1")
    finally:
        sa.s10.MODEL = before


# --- goblin-alarm-1080.md 6: a block's PLAYER settings (rule A's alarm_near_px) ---------------
def test_player_sets_take_player_settings_only() -> None:
    assert sa.player_sets([]) == {}
    assert sa.player_sets(["alarm_near_px=60"]) == {"alarm_near_px": 60.0}
    assert sa.player_sets(["alarm_near_px=60", "alarm_near_score=0.9"]) == {
        "alarm_near_px": 60.0, "alarm_near_score": 0.9}  # fmt: skip
    assert "not a player setting" in sa.player_sets(["garm_confirm=3"])  # a runner's
    assert "not a player setting" in sa.player_sets(["fly_first_land=true"])
    assert "a setting's name" in sa.player_sets(["no_such_thing=1"])
    assert "a setting's name" in sa.player_sets(["alarm_near_px"])
    assert "given twice" in sa.player_sets(["alarm_near_px=60", "alarm_near_px=50"])
    assert "not a number" in sa.player_sets(["alarm_near_px=sixty"])
    assert isinstance(sa.player_sets(["alarm_near_px=900"]), str)  # outside 0..200


def test_a_player_set_block_differs_in_that_setting_alone() -> None:
    """The real box (stage10's B): rule A set, the runner's argv / box / keys / loop unchanged,
    the project hash new; the box's own text untouched."""
    import stage10_ab as s10

    from poring_flow import project as pj

    text = s10.arm_text("B", 20)
    got = sa.player_set_arm(text, {"alarm_near_px": 60.0}, 1200)
    assert isinstance(got, dict), got
    base = sa.s5c.vals_of(text)
    assert isinstance(base, dict) and base["alarm_near_px"] == 0.0  # OFF in the box
    assert got["vals"]["alarm_near_px"] == 60.0
    assert {k for k in got["vals"] if got["vals"][k] != base.get(k)} == {"alarm_near_px"}
    assert got["project_hash"] != pj.project_hash(pj.from_json(text))
    assert sa.with_player_sets(text, {}) == text
    # the same value as the box's: nothing to differ, still the box's settings
    same = sa.player_set_arm(text, {"alarm_near_score": 0.85}, 1200)
    assert isinstance(same, dict) and same["vals"] == base


def test_plan_doc_carries_the_block_s_player_settings(tmp_path: Path) -> None:
    import stage10_ab as s10

    text = s10.arm_text("B", 20)
    doc = sa.plan_doc("gob-b", 3, 20, "1080", tmp_path, base=_base(),
                      sets={"alarm_near_px": 60.0}, base_text=text)  # fmt: skip
    assert isinstance(doc, dict), doc
    assert doc["player_set"] == {"alarm_near_px": 60.0}
    assert doc["vals"]["B"]["alarm_near_px"] == 60.0
    h = doc["arm"]["project_hash"]
    assert h != "h" * 64
    for r in doc["runs"]:
        assert r["argv"][r["argv"].index("--project-hash") + 1] == h
    plain = sa.plan_doc("gob-a", 3, 20, "1080", tmp_path, base=_base())
    assert isinstance(plain, dict) and plain["player_set"] == {}


def _boss_run(minutes: float, false: int, true: int = 0) -> dict[str, Any]:
    boss = [{"false": True}] * false + [{"false": False}] * true
    return {"found": True, "rc": 0, "minutes": minutes, "boss": boss}


def test_the_false_boss_line() -> None:
    a = [_boss_run(20, 6), _boss_run(20, 5), _boss_run(20, 6)]  # 17 in 1 h
    b = [_boss_run(20, 1, 1), _boss_run(20, 0), _boss_run(20, 1)]  # 2 in 1 h
    line = sa.false_boss_line(a, b, 20)
    assert (line["a"], line["b"], line["a_per_h"], line["b_per_h"]) == (17, 2, 17.0, 2.0)
    assert line["verdict"] == "lower" and line["se"] == round((17 + 2) ** 0.5, 2)
    assert sa.false_boss_line(a, a, 20)["verdict"] == "not lower"
    assert sa.false_boss_line(a, b[:1], 20)["verdict"] == "INCONCLUSIVE"  # 1 valid run
    short = [_boss_run(5, 0), _boss_run(5, 0)]  # under 80 % of the time box: not valid
    assert sa.false_boss_line(a, short, 20)["verdict"] == "INCONCLUSIVE"
