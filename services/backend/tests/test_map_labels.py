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


# --- gef_fild10 (docs/planning/gef10-detector.md, PROPOSED 3e31b01) ---------------------------


def test_gef10_roles_split_the_watch_by_cell_and_refuse_s7_s8_by_name() -> None:
    spec = ml.GEF10
    w = spec.staged
    assert spec.is_fit(w, frozenset(range(11)))
    assert not spec.is_fit(w, frozenset({10, 11}))
    assert spec.is_test(w, frozenset({11})) and spec.is_test(w, None)
    assert not spec.is_test(w, frozenset(range(11)))
    assert spec.is_fit("20261025T200922-rdp-rogue-pilot", None)
    assert spec.is_fit("20261025T203115-rdp-rogue-pilot2", None)
    for sid in ("20261026T010101-rdp-rogue-a7", "20261026T020202-rdp-rogue-a8",
                "20261026T010101-rdp-rogue-s7", "20261026T020202-rdp-rogue-s8"):  # fmt: skip
        assert spec.is_test(sid, None) and not spec.is_fit(sid, None)  # Amendment D: a7, a8
    for sid in ("20261025T204315-rdp-rogue-s1", "20261025T230000-rdp-rogue-a1",
                "20261025T230000-rdp-rogue-a6", "20261026T040000-rdp-rogue-a9"):  # fmt: skip
        assert not spec.is_test(sid, None) and not spec.is_fit(sid, None)  # TRAIN by 3c
    for sid, spots in spec.fit.items():
        assert not spec.is_test(sid, spots)
    # pay_fild07 keeps its own roles, and no name rule
    assert not ml.PAYF07.is_test("20261026T010101-rdp-rogue-s7", None)
    assert ml.PAYF07.labels == ml.LABELS == "payf07-o3h" and spec.labels == "gef10-o3h-e"


def test_watch_cells_are_every_map_change_to_the_map() -> None:
    events = [
        _ev("map_change", 5, map="prt_fild08.gat"),  # another map: not a cell
        _ev("map_change", 10, map="gef_fild10.gat"), _ev("chat", 20),
        _ev("map_change", 70, map="gef_fild10.gat"),
        _ev("drop_request", 80),
        _ev("map_change", 130, map="gef_fild10"),
    ]  # fmt: skip
    assert ml.cell_starts(events, "gef_fild10") == [10 * S, 70 * S, 130 * S]
    assert ml.staged_starts(ml.GEF10, events) == [10 * S, 70 * S, 130 * S]
    assert ml.staged_starts(ml.PAYF07, events) == [70 * S]  # stage_items' rule: drops follow


def test_heading_toward_is_map_calc_dir() -> None:
    assert ml.heading_toward((10, 10), (10, 15)) == 0  # north
    assert ml.heading_toward((10, 10), (5, 10)) == 2  # west
    assert ml.heading_toward((10, 10), (10, 5)) == 4  # south
    assert ml.heading_toward((10, 10), (15, 10)) == 6  # east
    assert ml.heading_toward((10, 10), (13, 13)) == 7  # north-east
    assert ml.heading_toward((10, 10), (10, 10)) is None


def _rule(variant: str, monkeypatch: pytest.MonkeyPatch, why: dict[int, str | None]) -> Any:
    def base(self: Any, world: Any, e: Any, *_a: Any) -> Any:
        return (3, "fix2:after_move"), why.get(e.gid)

    monkeypatch.setattr(olf.FacingRule, "choose", base)
    return ml.EngagedLabelRule("fix2", olf.NextMoves(()), olf.ViewClasses(),
                               {1: [S], 2: [S], 3: [S], 4: [S]}, variant=variant)  # fmt: skip


def _unit(gid: int, x: float = 10, y: float = 10) -> Any:
    return SimpleNamespace(gid=gid, x=x, y=y)


def test_engaged_label_rule_e0_is_amendment_b(monkeypatch: pytest.MonkeyPatch) -> None:
    rule = _rule("E0", monkeypatch, {1: "next_move"})
    st = SimpleNamespace(state="idle")
    world = SimpleNamespace(self_x=12, self_y=10)
    assert rule.choose(world, _unit(1), st, {}, S, None, 0.0)[1] == "next_move"
    assert rule.choose(world, _unit(2), st, {}, S, None, 0.0) == ((3, "fix2:after_move"),
                                                                  ml.ENGAGED)  # fmt: skip
    assert rule.choose(world, _unit(9), st, {}, S, None, 0.0)[1] is None  # not engaged
    assert rule.engaged_now == set()


def test_engaged_label_rule_e1_e2(monkeypatch: pytest.MonkeyPatch) -> None:
    why = {1: "next_move", 3: "ambiguous_view"}
    idle, walk = SimpleNamespace(state="idle"), SimpleNamespace(state="walk")
    world = SimpleNamespace(self_x=12, self_y=10)  # our character 2 cells east
    e1 = _rule("E1", monkeypatch, why)
    assert e1.choose(world, _unit(2), idle, {}, S, None, 0.0) == ((3, "engaged:fix2:after_move"),
                                                                  None)  # fmt: skip
    assert e1.choose(world, _unit(3), idle, {}, S, None, 0.0)[1] == "ambiguous_view"  # 2c kept
    assert e1.engaged_now == {2}
    e2 = _rule("E2", monkeypatch, why)
    assert e2.choose(world, _unit(2), idle, {}, S, None, 0.0) == ((6, "engaged:toward_self"), None)
    assert e2.choose(world, _unit(3), idle, {}, S, None, 0.0) == (
        (6, "engaged:toward_self"),
        None,
    )  # 2c does not apply
    assert e2.choose(world, _unit(1), idle, {}, S, None, 0.0)[1] == "next_move"  # 2b does
    assert e2.choose(world, _unit(4), walk, {}, S, None, 0.0) == (
        (3, "engaged:fix2:after_move"),
        None,
    )  # walking: fix 2
    assert e2.engaged_now == {2, 3, 4}
    e2.choose(world, _unit(9), idle, {}, 2 * S, None, 0.0)  # a new timeline time resets it
    assert e2.engaged_now == set()
    with pytest.raises(SystemExit):
        _rule("E9", monkeypatch, {}).choose(world, _unit(2), idle, {}, S, None, 0.0)


def test_without_box_masks_a_grown_box() -> None:
    import numpy as np

    valid = np.ones((10, 20), bool)
    out = ml.without_box(valid, (5.0, 2.0, 7.0, 4.0), pad=1)
    assert valid.all()  # a copy
    assert not out[1:5, 4:8].any() and out[0].all() and out[:, :4].all() and out[:, 8:].all()
    edge = ml.without_box(valid, (-5.0, -5.0, 2.0, 2.0), pad=0)
    assert not edge[0:2, 0:2].any() and edge[2:, :].all()


def test_envelope_redraws_every_frame_of_another_action() -> None:
    class Act:
        def action_index(self, group: int, direction: int) -> int:
            return group * 8 + direction

    class Sheet:
        act = Act()

        def motions(self, ai: int) -> int:
            return 2

        def extent(self, ai: int, m: int) -> Any:
            return (-10.0, -20.0, 10.0, 0.0) if m == 0 else (-12.0, -18.0, 8.0, 2.0)

    from poring_dataset.render import SpritePrediction

    pred = SpritePrediction((0, 0, 1, 1), (100.0, 200.0), 2.0, 50.0, 0, 3, 3, 1, True, "opaque")
    p = ml.envelope(Sheet(), pred, 2)  # ATTACK, direction 3
    assert p.action == 2 and p.action_index == 19 and p.motion is None and not p.phase_known
    assert p.box == (100 - 24.0, 200 - 40.0, 100 + 20.0, 200 + 4.0)
    assert p.anchor_px == pred.anchor_px and p.scale == pred.scale


def test_engaged_selection_offset_bar_and_ties() -> None:
    def r(v: str, ncc: float | None, dx: int = 0, dy: int = 0, pre: str | None = None,
          fail: str | None = None) -> dict[str, Any]:  # fmt: skip
        return {"variant": v, "ncc": ncc, "dx": dx, "dy": dy, "pre": pre, "fail": fail}

    rows = ([r("E1", 0.6)] * 3 + [r("E1", 0.2)] * 5 + [r("E1", None, fail="crowd")]
            + [r("E2", 0.7, 1, 1)] * 6 + [r("E2", 0.7, 5, 0, pre="next_move")]
            + [r("E3", 0.9, 4, 5)] * 9)  # fmt: skip
    sel = ml.engaged_selection(rows, 0.5)
    per = sel["per_variant"]
    assert per["E1"]["kept"] == 3 and per["E1"]["fates"] == 9 and per["E1"]["qualifies"]
    assert per["E2"]["kept"] == 6 and per["E2"]["qualifies"]
    assert per["E3"]["kept"] == 9 and not per["E3"]["qualifies"]  # wanders: median 4 / 5 px
    assert sel["chosen"] == "E2"
    tie = [r("E1", 0.6)] * 4 + [r("E2", 0.6)] * 4
    assert ml.engaged_selection(tie, 0.5, ("E1", "E2"))["chosen"] == "E1"  # the simpler
    assert ml.engaged_selection([r("E3", 0.9, 3, 3)], 0.5)["chosen"] == "E0"
    assert ml.engaged_selection([], 0.5)["chosen"] == "E0"


def _item(s: str, f: int, g: int, mob: int, engaged: bool = False) -> dict[str, Any]:
    return {"session": s, "frame_id": f, "gid": g, "mob": mob, "engaged": engaged}


def test_t2_sample_payf07_unchanged() -> None:
    """The pre-gef10 inline rule: Green Plant in the tier with >= 30, the first 30 of t2_order,
    one shuffle by payf07:{seed}:order."""
    pool = {1033: [_item("a", f, 1, 1033) for f in range(40)],
            1080: [_item("a", f, 2, 1080) for f in range(29)]}  # fmt: skip
    chosen, per, tier = ml.t2_sample(pool, ml.PAYF07, 21)
    assert 1080 not in tier and 1033 in tier and per["1033"] == {"pool": 40, "sampled": 30}
    want = ml.t2_order(pool[1033], 21, 1033)[:30]
    random.Random("payf07:21:order").shuffle(want)
    assert [(c["frame_id"], c["gid"]) for c in chosen] == [(w["frame_id"], w["gid"]) for w in want]
    pool[1080].append(_item("a", 99, 2, 1080))
    assert 1080 in ml.t2_sample(pool, ml.PAYF07, 21)[2]


def test_t2_sample_gef10_strata() -> None:
    pool = {1273: [_item("a", f, 1, 1273, engaged=f % 2 == 0) for f in range(100)],
            1023: [_item("a", f, 2, 1023, engaged=True) for f in range(40)]
                  + [_item("a", f, 3, 1023) for f in range(29)]}  # fmt: skip
    chosen, per, tier = ml.t2_sample(pool, ml.GEF10, 31)
    assert tier == [1273]  # 1023 has 29 N labels (< 30): not in the tier (D4)
    assert per == {"1273:N": {"pool": 50, "sampled": 30}, "1273:E": {"pool": 50, "sampled": 30}}
    assert sum(1 for c in chosen if c["stratum"] == "E" and c["engaged"]) == 30
    assert sum(1 for c in chosen if c["stratum"] == "N" and not c["engaged"]) == 30
    n_items = [it for it in pool[1273] if not it["engaged"]]
    want = sorted(n_items, key=lambda it: (it["session"], it["frame_id"], it["gid"]))
    random.Random("gef10:31:1273:N").shuffle(want)
    assert ml.t2_order(n_items, 31, 1273, "gef10", "N") == want


def test_frame_exclusions_dying_in_view(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml, "anchor_and_depth", lambda scene, cell: ((cell[0], cell[1]), 0.0))
    world = SimpleNamespace(entities=[])
    assert ml.frame_exclusions(world, None, (1280, 720), (), (), None, [(2000, 10)]) == []
    assert ml.frame_exclusions(world, None, (1280, 720), (), (), None,
                               [(2000, 10), (100, 100)]) == ["dying_in_view"]  # fmt: skip


def test_count_engaged_and_box_geometry() -> None:
    frames = [{"kept": [{"mob": 1273, "engaged": True}, {"mob": 1273}], "whole": True},
              {"kept": [{"mob": 1273, "engaged": True}, {"mob": 1023, "engaged": True}],
               "whole": False}, {"excluded_frame": ["ui_layout_mismatch"]}]  # fmt: skip
    assert ml.count_engaged(frames) == {"1023": {"kept": 1, "kept_in_whole_frames": 0},
                                        "1273": {"kept": 2, "kept_in_whole_frames": 1}}  # fmt: skip
    g = ml.box_geometry([{"w": float(w), "h": 2.0 * w} for w in range(1, 11)])
    assert g["n"] == 10 and g["w"]["p50"] == 5.5 and g["h"]["p50"] == 11.0
    assert ml.box_geometry([]) == {"n": 0}


def test_freeze_needs_the_engaged_selection_at_the_same_offset_and_t_h(tmp_path: Path) -> None:
    import argparse
    import json

    th = tmp_path / "th.json"
    th.write_text(json.dumps({"o3h_tau": 0.5, "offset_ms": 120.0, "offset_source": "P1"}))
    base = {"map": "gef_fild10", "threshold": th, "offset": None, "proposed": True,
            "decision": None, "engaged_variant": None}  # fmt: skip
    with pytest.raises(SystemExit, match="engaged"):
        ml.cmd_freeze(argparse.Namespace(**base, engaged=None))
    sel = tmp_path / "sel.json"
    sel.write_text(json.dumps({"chosen": "E2", "t_h": 0.4, "offset_ms": 120.0}))
    with pytest.raises(SystemExit, match="same 1d and T_h"):
        ml.cmd_freeze(argparse.Namespace(**base, engaged=sel))


def test_fit_diagnostic_check_refuses_every_non_fit_part(tmp_path: Path) -> None:
    """gef10 13: C1 under PROPOSED parameters only on FIT parts, refused before anything is read
    (a TEST cell, s7 / s8 by name, a TRAIN session)."""
    import argparse
    import json

    params = tmp_path / "params.json"
    params.write_text(json.dumps({"labels": "gef10-o3h-e", "map": "gef_fild10",
                                  "status": "PROPOSED_NOT_FROZEN: P1"}))  # fmt: skip
    for part in ("/nonexistent/20261025T195325-rdp-ow1:spots=10-11",
                 "/nonexistent/20261026T010101-rdp-rogue-a7",
                 "/nonexistent/20261025T204315-rdp-rogue-s1"):  # fmt: skip
        a = argparse.Namespace(map="gef_fild10", params=params, parts=[part], fit_diagnostic=True)
        with pytest.raises(SystemExit, match="FIT parts only"):
            ml.cmd_check(a)
    a = argparse.Namespace(map="gef_fild10", params=params, parts=["/x"], fit_diagnostic=False)
    with pytest.raises(SystemExit, match="FROZEN parameters only"):
        ml.cmd_check(a)


def test_amendment_a_the_watch_reads_the_4_row_layout() -> None:
    """gef10 Amendment A: the watch's frames are candidates in the 4-row / expanded layout (either
    tab), with the standard rectangles; every other session keeps the hunting layout."""
    assert ml.GEF10.layouts == {ml.GEF10_WATCH: "rows4"} and ml.PAYF07.layouts == {}
    assert ml.LAYOUT_RECTS == {"hunt": "hunt", "rows4": "standard"}
    hunt = {"rows": 1, "panel": "collapsed", "tab": "battle"}
    four = {"rows": 4, "panel": "expanded", "tab": "battle"}
    assert ml.layout_matches(hunt, "hunt") and not ml.layout_matches(four, "hunt")
    assert ml.layout_matches(four, "rows4") and ml.layout_matches({**four, "tab": "regular"},
                                                                  "rows4")  # fmt: skip
    assert not ml.layout_matches(hunt, "rows4")
    assert not ml.layout_matches({**four, "panel": None}, "rows4")
    with pytest.raises(SystemExit):
        ml.layout_matches(hunt, "other")


def test_amendment_c_facing_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """gef10 Amendment C (2d): a unit whose facing has NO source is excluded, except an engaged
    unit under E2 / E3 that is drawn toward our character; 2b / 2c keep their names."""

    def base(self: Any, world: Any, e: Any, *_a: Any) -> Any:
        return (0, "timeline:None"), ("next_move" if e.gid == 1 else None)

    monkeypatch.setattr(olf.FacingRule, "choose", base)
    idle, walk = SimpleNamespace(state="idle"), SimpleNamespace(state="walk")
    world = SimpleNamespace(self_x=12, self_y=10)
    times = {1: [S], 2: [S]}  # 1 and 2 engaged; 9 not

    def rule(v: str) -> Any:
        return ml.EngagedLabelRule("fix2", olf.NextMoves(()), olf.ViewClasses(), times, variant=v)

    for v in ("E0", "E1", "E2", "E3"):
        assert rule(v).choose(world, _unit(9), idle, {}, S, None, 0.0)[1] == ml.FACING_UNKNOWN
        assert rule(v).choose(world, _unit(1), idle, {}, S, None, 0.0)[1] == "next_move"
    assert rule("E0").choose(world, _unit(2), idle, {}, S, None, 0.0)[1] == ml.ENGAGED
    e1 = rule("E1")
    assert e1.choose(world, _unit(2), idle, {}, S, None, 0.0)[1] == ml.FACING_UNKNOWN
    assert e1.engaged_now == set()
    e2 = rule("E2")
    assert e2.choose(world, _unit(2), idle, {}, S, None, 0.0) == ((6, "engaged:toward_self"), None)
    assert e2.engaged_now == {2}
    assert e2.choose(world, _unit(2), walk, {}, 2 * S, None, 0.0)[1] == ml.FACING_UNKNOWN
    assert e2.engaged_now == set()
    on_us = SimpleNamespace(self_x=10, self_y=10)
    assert rule("E3").choose(on_us, _unit(2), idle, {}, S, None, 0.0)[1] == ml.FACING_UNKNOWN
    # pay_fild07's rule (EngagedRule) is unchanged: no 2d
    pay = ml.EngagedRule("fix2", olf.NextMoves(()), olf.ViewClasses(), times)
    assert pay.choose(world, _unit(9), idle, {}, S, None, 0.0)[1] is None
