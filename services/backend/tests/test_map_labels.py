"""The map-parameterised labels (docs/planning/payf07-detector.md; scripts/map_labels.py): the pure
parts on SYNTHETIC packets / rows, and the orcsdun01 defaults it must not change."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import map_labels as ml  # noqa: E402
import orc_labels_fix as olf  # noqa: E402

S = 1_000_000_000


def test_parse_part() -> None:
    assert ml.parse_part("/x/sess") == (Path("/x/sess"), None)
    assert ml.parse_part("/x/sess:spots=0-7") == (Path("/x/sess"), frozenset(range(8)))
    assert ml.parse_part("/x/s:spots=0,2,5-6") == (Path("/x/s"), frozenset({0, 2, 5, 6}))
    with pytest.raises(SystemExit):
        ml.parse_part("/x/s:spots=a-b")


def test_roles_fit_and_test_are_disjoint() -> None:
    spec = ml.PAYF07
    staged = spec.staged
    assert ml.inside_role(staged, frozenset(range(8)), spec.fit)
    assert not ml.inside_role(staged, frozenset({7, 8}), spec.fit)
    assert ml.overlaps_role(staged, frozenset({7, 8}), spec.test)
    assert not ml.overlaps_role(staged, frozenset(range(8)), spec.test)
    assert ml.overlaps_role(staged, None, spec.test)  # the whole staged session holds TEST spots
    assert ml.overlaps_role("20261024T131838-rdp-thief-t2", None, spec.test)
    assert ml.inside_role("20261024T123622-rdp-thief-t1b", None, spec.fit)
    assert not ml.overlaps_role("20261024T173322-rdp-thief-s1", None, spec.test)
    for sid, spots in spec.fit.items():
        assert not ml.overlaps_role(sid, spots, spec.test)


def _ev(kind: str, t: float, **kw: Any) -> dict[str, Any]:
    return {"type": kind, "t_mono_ns": int(t * S), **kw}


def test_spot_starts_need_drops_and_inventory_spans() -> None:
    events = [
        _ev("map_change", 0),  # the run's start: no drops before the next change -> not a spot
        _ev("map_change", 10), _ev("drop_request", 40), _ev("drop_result", 41),
        _ev("drop_request", 50), _ev("drop_result", 51),
        _ev("map_change", 70), _ev("map_change", 87),  # two offsets of spot 0
        _ev("map_change", 100), _ev("drop_request", 130), _ev("drop_result", 131),
        _ev("map_change", 150),
    ]  # fmt: skip
    starts = ml.spot_starts(events)
    assert starts == [10 * S, 100 * S]
    assert ml.spot_of(5 * S, starts) is None
    assert ml.spot_of(90 * S, starts) == 0
    assert ml.spot_of(140 * S, starts) == 1
    spans = ml.inventory_spans(events, starts)
    assert spans == [(20 * S, 56 * S), (110 * S, 136 * S)]


def test_still_times_and_same_place() -> None:
    ts = ml.still_times(10 * S, 10 * S + 500_000_000)
    assert ts[0] == 9 * S and ts[-1] == 10 * S + 500_000_000
    assert all(b - a <= ml.STILL_STEP_NS for a, b in zip(ts, ts[1:], strict=False))
    assert ml.same_place([(1.0, 2.0), (1.0, 2.0)])
    assert not ml.same_place([(1.0, 2.0), (1.5, 2.0)])
    assert not ml.same_place([None, None])
    assert not ml.same_place([])


def test_recent_map_change() -> None:
    times = [10 * S, 50 * S]
    assert ml.recent(times, 12 * S, 5 * S)
    assert ml.recent(times, 15 * S, 5 * S)  # the window's edge counts
    assert not ml.recent(times, 16 * S, 5 * S)
    assert not ml.recent(times, 9 * S, 5 * S)  # a change AFTER the frame does not


def test_percentile_is_numpy_linear_rounded() -> None:
    vals = [i / 100 for i in range(101)]
    assert ml.percentile(vals, 5) == 0.05
    assert ml.percentile([0.1, 0.2], 50) == 0.15


def _row(mob: int, c1: float, why: str | None = None, dx: int = 0, dy: int = 0) -> dict[str, Any]:
    return {"mob": mob, "c1": c1, "why_low": why, "dx": dx, "dy": dy, "best": 0.7}


def test_t1_bar_is_inclusive_and_pooled_over_the_map_species() -> None:
    sp = (1033, 1010)
    rows = [_row(1033, 0.5) for _ in range(19)] + [_row(1033, 0.01, "bad_label")]
    assert ml.t1_summary(rows, sp)["T1"] == "PASS"  # 1 / 20 = 0.050 <= 0.050
    rows2 = rows + [_row(1010, 0.01, "bad_label")]
    assert ml.t1_summary(rows2, sp)["T1"] == "FAIL"  # 2 / 21
    rows3 = rows + [_row(1002, 0.01, "bad_label")]  # another map's species is not pooled
    s3 = ml.t1_summary(rows3, sp)
    assert s3["T1"] == "PASS" and s3["other_species_rows"] == 1
    occluded = rows + [_row(1033, 0.01, "occluded")]  # only bad_label counts, as orcsdun01's C1
    assert ml.t1_summary(occluded, sp)["T1"] == "PASS"
    assert ml.t1_summary([], sp)["T1"] == "NO_VERDICT"


def test_c2_stop_needs_twenty_labels() -> None:
    far = [_row(1060, 0.5, dx=6, dy=0) for _ in range(19)]
    assert ml.c2_summary(far)["verdict"] == "NO_VERDICT"
    assert ml.c2_summary(far + [_row(1060, 0.5, dx=6)])["verdict"] == "FAIL"
    near = [_row(1060, 0.5, dx=4, dy=-4) for _ in range(20)]
    assert ml.c2_summary(near)["verdict"] == "PASS"
    s = ml.t1_summary(far + [_row(1060, 0.5, dx=6)], (1060,))
    assert s["c2_stop"] and s["c2"]["stop_species"] == ["1060"]


def test_own_c1_join_rule() -> None:
    def summ(scored: int, bad: int) -> dict[str, Any]:
        return {"c1": {"pooled": {"scored": scored}, "ratio": bad / scored if scored else None}}

    assert ml.own_c1_verdict(summ(49, 0)) == "NOT_ADDED_TOO_FEW"
    assert ml.own_c1_verdict(summ(100, 5)) == "ADDED"
    assert ml.own_c1_verdict(summ(100, 6)) == "NOT_ADDED_C1"


def test_t2_order_is_seeded_and_independent_of_input_order() -> None:
    items = [{"session": s, "frame_id": f, "gid": g, "mob": 1033}
             for s in ("a", "b") for f in range(20) for g in (1, 2)]  # fmt: skip
    shuffled = list(items)
    random.Random(3).shuffle(shuffled)
    o1 = ml.t2_order(items, 21, 1033)
    assert o1 == ml.t2_order(shuffled, 21, 1033)
    assert o1 != ml.t2_order(items, 22, 1033)
    want = sorted(items, key=lambda it: (it["session"], it["frame_id"], it["gid"]))
    random.Random("payf07:21:1033").shuffle(want)
    assert o1 == want


def _frame(kept: list[int], excl: list[int], whole: bool = True) -> dict[str, Any]:
    return {"kept": [{"mob": m, "gid": i} for i, m in enumerate(kept)],
            "excluded": [[100 + i, m, "unfit"] for i, m in enumerate(excl)],
            "excluded_frame": [], "whole": whole and not excl}  # fmt: skip


def test_count_labels_and_the_green_plant_fallback() -> None:
    frames = [_frame([1033, 1080], []), _frame([1033], [1010]), _frame([1060], []),
              {"excluded_frame": ["ui_layout_mismatch"], "whole": False}]  # fmt: skip
    c = ml.count_labels(frames, (1033, 1010, 1060, 1080))
    assert c["frames_labelled"] == 3 and c["frames_whole"] == 2
    assert c["per_species"]["1033"] == {"kept": 2, "kept_in_whole_frames": 1, "excluded": {}}
    assert c["per_species"]["1010"]["excluded"] == {"unfit": 1}
    assert c["frame_exclusions"] == {"ui_layout_mismatch": 1}
    d = ml.count_labels(frames, (1033, 1010, 1060), drop_species=[1080])
    assert d["frames_whole"] == 1  # the Green Plant frame is not whole when it is not a class
    assert d["per_species"]["1033"]["kept_in_whole_frames"] == 0
    assert d["kept_total"] == 3


def test_frame_exclusions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml, "anchor_and_depth", lambda scene, cell: ((cell[0], cell[1]), 0.0))

    def ent(gid: int, objtype: int, job: int, x: float, y: float) -> Any:
        return SimpleNamespace(gid=gid, objtype=objtype, job=job, x=x, y=y, hidden=False)

    world = SimpleNamespace(
        entities=[
            ent(1, 5, 1033, 10, 10),
            ent(2, 6, 45, 2000, 10),
            ent(3, 0, 4001, 50, 50),
            ent(9, 5, 1002, 60, 60),
        ]
    )
    assert ml.frame_exclusions(world, None, (1280, 720), (1033,), (1002,), aid=3) == []
    world.entities.append(ent(4, 6, 45, 100, 100))  # a warp portal in view
    world.entities.append(ent(5, 5, 1200, 100, 100))  # a species with no class
    world.entities.append(ent(6, 0, 4001, 10, 10))  # another player
    got = ml.frame_exclusions(world, None, (1280, 720), (1033,), (1002,), aid=3)
    assert got == ["other_player", "unchecked_species:1200", "warp_in_view"]


def test_check_recording_fails_closed() -> None:
    good = {"backend": "rdp", "recorder_version": 5, "format": "png", "session_id": "x",
            "game_region": [80, 77, 1280, 720], "server": "lab-rathena"}  # fmt: skip
    ml.check_recording(good)
    for k, v in (("backend", "console"), ("format", "h264"), ("recorder_version", 4)):
        with pytest.raises(SystemExit):
            ml.check_recording({**good, k: v})


def test_orcsdun01_defaults_unchanged() -> None:
    """The hooks map_labels needs keep orcsdun01's behaviour: decide's o3h threshold defaults to
    3i's 0.48, and the module's map / walkers / reader are orcsdun01's."""
    assert olf.O3H_TAU == 0.48 and olf.MAP == "orcsdun01" and olf.WALKERS == (1153, 1152)
    f = olf.LabelFate(1, 1153, True, None, (0.47, 0, 0, 0), None, box=(0, 0, 1, 1))
    kept, out = olf.decide([f], "o3h", False)
    assert not kept and out == [(1, 1153, olf.OCCLUDED)]
    kept, out = olf.decide([f], "o3h", False, o3h_tau=0.40)
    assert [k.gid for k in kept] == [1] and not out
    olf._JOB.clear()
    assert olf._JOB.get("reader", olf.qa_export.read_jpeg) is olf.qa_export.read_jpeg


def test_amendment_a_sweep_is_0_to_500() -> None:
    assert ml.COARSE_MS[0] == 0 and ml.COARSE_MS[-1] == 500 and len(ml.COARSE_MS) == 11
    assert ml.sweep_fine(150) == list(range(100, 201, 10))
    assert ml.sweep_fine(500) == list(range(450, 501, 10))  # clipped to the sweep
    assert ml.sweep_fine(0) == list(range(0, 51, 10))


def test_t1_refuses_parameters_that_are_not_frozen(tmp_path: Path) -> None:
    """9b: the proposal's parameters label TRAIN provisionally, but T1 never runs on them."""
    import argparse
    import json

    for status in ("PROPOSED_NOT_FROZEN: P1", None):
        params = tmp_path / "params.json"
        params.write_text(json.dumps({"labels": ml.LABELS, "map": "pay_fild07", "status": status}))
        a = argparse.Namespace(map="pay_fild07", params=params, parts=["/nonexistent"])
        with pytest.raises(SystemExit, match="FROZEN parameters only"):
            ml.cmd_check(a)


def test_amendment_b_engagement() -> None:
    aid = 7
    events = [
        {"type": "act", "src_gid": 7, "target_gid": 100, "t_mono_ns": 10 * S},
        {"type": "act", "src_gid": 200, "target_gid": 7, "t_mono_ns": 20 * S},
        {"type": "act", "src_gid": 300, "target_gid": 400, "t_mono_ns": 20 * S},  # not ours
        {"type": "attack_request", "target_gid": 500, "t_mono_ns": 30 * S},
        {"type": "act", "src_gid": 7, "target_gid": 7, "t_mono_ns": 5 * S},  # self (a skill)
    ]
    times = ml.engagement_times(events, aid)
    assert times == {100: [10 * S], 200: [20 * S], 500: [30 * S]}
    assert ml.is_engaged(times, 100, 13 * S)  # 3 s after: still engaged
    assert not ml.is_engaged(times, 100, 13 * S + 1)
    assert ml.is_engaged(times, 100, 9 * S)  # 1 s before the fight starts
    assert not ml.is_engaged(times, 100, 9 * S - 1)
    assert not ml.is_engaged(times, 300, 20 * S) and not ml.is_engaged(times, 400, 20 * S)
    assert ml.is_engaged(times, 500, 30 * S)


def test_engaged_rule_adds_its_reason_after_2b_2c(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def base(self: Any, world: Any, e: Any, *_a: Any) -> Any:
        calls.append(e.gid)
        return (3, "fix2:walk"), ("next_move" if e.gid == 1 else None)

    monkeypatch.setattr(olf.FacingRule, "choose", base)
    rule = ml.EngagedRule("fix2", olf.NextMoves(()), olf.ViewClasses(), {1: [S], 2: [S]})
    e1, e2, e3 = (SimpleNamespace(gid=g) for g in (1, 2, 3))
    assert rule.choose(None, e1, None, {}, S, None, 0.0)[1] == "next_move"  # 2b keeps its name
    assert rule.choose(None, e2, None, {}, S, None, 0.0)[1] == ml.ENGAGED
    assert rule.choose(None, e3, None, {}, S, None, 0.0)[1] is None


def test_round2_pool_drops_weak_clear_fits_and_judged_crops() -> None:
    """11: the frozen T_h on every label (a weak fit NOT under a model leaves the pool; one under
    a model was already gated by o3h) and an earlier round's crops leave the pool."""

    def it(s, f, g, ncc, under):
        return {"session": s, "frame_id": f, "gid": g, "ncc": ncc, "under": under}

    items = [it("a", 1, 7, 0.12, False), it("a", 2, 7, 0.80, False), it("a", 3, 8, 0.30, True),
             it("b", 1, 9, 0.90, False), it("b", 2, 9, 0.479, False)]  # fmt: skip
    kept, cut = ml.round2_pool(items, 0.479, {("b", 1, 9)})
    assert [(k["session"], k["frame_id"]) for k in kept] == [("a", 2), ("a", 3), ("b", 2)]
    assert cut == {"weak_fit": 1, "judged_before": 1}
    kept0, cut0 = ml.round2_pool(items, None, set())
    assert kept0 == items and cut0 == {"weak_fit": 0, "judged_before": 0}
