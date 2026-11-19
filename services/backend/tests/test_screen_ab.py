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
