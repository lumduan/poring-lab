"""The map-parameterised labels (docs/planning/payf07-detector.md; scripts/map_labels.py): the pure
parts on SYNTHETIC packets / rows, and the orcsdun01 defaults it must not change."""

from __future__ import annotations

import json
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


_NO_TERRAIN = SimpleNamespace(terrain=None)  # a frozen occluder set without 4f's terrain


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
    ml.check_recording({**good, "recorder_version": 6})  # T-3 (xmas02-detector.md 3c): v6 too
    ml.check_recording({**good, "recorder_version": 7})  # ADR-0024: v7's PNG, and its video
    ml.check_recording({**good, "recorder_version": 7, "format": "vpp-hevc444-10-q20"})
    for k, v in (("backend", "console"), ("format", "h264"), ("format", None),
                 ("recorder_version", 4), ("recorder_version", 8), ("recorder_version", None),
                 ("game_region", [80, 77, 1440, 900]), ("server", "lab-rathena-th")):  # fmt: skip
        with pytest.raises(SystemExit, match="not the recording path of 3c"):
            ml.check_recording({**good, k: v})
    bare = {k: v for k, v in good.items() if k != "recorder_version"}
    with pytest.raises(SystemExit, match="recorder_version"):
        ml.check_recording(bare)


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
                "20261025T230000-rdp-rogue-a6"):  # fmt: skip
        assert not spec.is_test(sid, None) and not spec.is_fit(sid, None)  # TRAIN by 3c
    # ROUND 2 (gef10-round2.md): a9 is TEST2 now (it was a 3c candidate in round 1)
    assert spec.is_test("20261026T040000-rdp-rogue-a9", None)
    assert not spec.is_round1_test("20261026T040000-rdp-rogue-a9", None)
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


def test_freeze_needs_the_engaged_selection_at_the_same_offset_and_t_h(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse
    import json
    import types

    # The rule under test reads no client data: gef10's occluders (no terrain) without the map's
    # RSW, which lived in /dev/shm until its scratch was archived (2026-11-03).
    monkeypatch.setattr(ml, "occluders", lambda spec: types.SimpleNamespace(terrain=None))
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


# --- gef10 ROUND 2: the pickup-notice exclusion in C1 (docs/planning/gef10-round2.md) ----------


def _ground(h: int = 720, w: int = 1280, seed: int = 11) -> Any:
    import numpy as np

    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[..., 0] = rng.integers(60, 140, (h, w))
    img[..., 1] = rng.integers(80, 160, (h, w))
    img[..., 2] = rng.integers(40, 110, (h, w))
    return img


def _draw_notice(img: Any, x0: int, y0: int, x1: int, y1: int) -> None:
    """The client's notice (test_gef10_r2_measure.draw_notice): white, a grey line inside."""
    img[y0:y1, x0:x1] = 255
    g = (192, 192, 192)
    img[y0 + 2, x0 + 4 : x1 - 4] = g
    img[y1 - 3, x0 + 4 : x1 - 4] = g
    img[y0 + 4 : y1 - 4, x0 + 2] = g
    img[y0 + 4 : y1 - 4, x1 - 3] = g
    img[y0 + 5 : y0 + 25, x0 + 15 : x0 + 35] = (120, 90, 200)
    for k in range(x0 + 45, x1 - 20, 9):
        img[y0 + 10 : y0 + 20, k : k + 5] = 0


def test_notice_hits_is_any_overlap() -> None:
    n = (541.0, 76.0, 800.0, 106.0)
    assert ml.notice_hits((500.0, 28.0, 565.0, 118.0), [n])  # 13r's Orc Warrior: the box's top
    assert not ml.notice_hits((500.0, 106.0, 565.0, 150.0), [n])  # touching is no overlap
    assert not ml.notice_hits((470.0, 28.0, 541.0, 118.0), [n])
    assert not ml.notice_hits((500.0, 28.0, 565.0, 118.0), [])


def _round2_job(monkeypatch: pytest.MonkeyPatch, boxes: dict[int, tuple[float, ...]],
                frame: Any) -> Any:  # fmt: skip
    """A fake session for orc_labels_fix._check_rows: one standing candidate per gid at ``boxes``
    (job 1023), the frame ``frame``; scoring stubbed (c1 0.5 > tau: never low)."""
    ents = {g: SimpleNamespace(gid=g, job=1023, x=10.0 + g, y=10.0, objtype=5, hidden=False)
            for g in boxes}  # fmt: skip
    cands = [(ents[g], None, "sheet", SimpleNamespace(box=b), (0, "fix2:test"))
             for g, b in boxes.items()]  # fmt: skip
    world = SimpleNamespace(entities=list(ents.values()), self_pos=(5, 5))
    scene = SimpleNamespace(camera=SimpleNamespace(yaw=0.0))

    def standing(sess: Any, tw: int, anchors: Any, occl: Any, dropped: Any, rule: Any,
                 under: Any) -> Any:  # fmt: skip
        return world, scene, {}, list(cands)

    monkeypatch.setattr(olf, "standing_candidates", standing)
    monkeypatch.setattr(olf.label_check, "score", lambda bgr, sheet, pred: 0.5)
    monkeypatch.setattr(olf.occ, "best_offset", lambda *a, **k: None)
    monkeypatch.setattr(olf, "predict", lambda *a, **k: None)
    tl = SimpleNamespace(frame_world=lambda t: SimpleNamespace(self_pos=(5, 5)))
    sess = SimpleNamespace(layout_ok=lambda bgr: True, lab=SimpleNamespace(timeline=tl))
    olf._JOB.clear()
    olf._JOB.update(sess=sess, occluders=None, offset_ms=120.0, anchors={},
                    facing_rule=None, occlusion="1c", reader=lambda ref: frame)  # fmt: skip
    return SimpleNamespace(frame_id=505, t_mono_ns=10 * S)


def _no_notice(dropped: Any) -> bool:
    return not any(k.startswith("notice") or k == "frame_with_notice" for k in dropped)


def test_round2_excludes_a_label_under_a_notice_and_round1_scores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive case (13r's shape: a box whose top lies under the notice at x 541-799,
    y 77-104) is excluded as ``notice`` under round 2 and scored as before without it; a box
    16 px beside the notice is scored either way and marked ``notice_near``; a box far away
    is scored either way."""
    frame = _ground()
    _draw_notice(frame, 541, 76, 800, 106)
    boxes = {1: (520.0, 28.0, 585.0, 118.0),  # under the notice
             2: (300.0, 300.0, 360.0, 370.0),  # far away
             3: (470.0, 60.0, 530.0, 130.0)}  # 11 px left of it: near, not over  # fmt: skip
    ref = _round2_job(monkeypatch, boxes, frame)
    rows, dropped, _seen = olf._check_rows(ref)  # round 1: no frame rule
    assert [r["gid"] for r in rows] == [1, 2, 3] and _no_notice(dropped)
    assert all("notice_near" not in r for r in rows)
    olf._JOB["frame_rule"] = ml.NoticeRule()
    rows2, dropped2, _ = ml._check_rows_round2(ref)
    assert [r["gid"] for r in rows2] == [2, 3]
    assert dropped2["notice"] == 1 and dropped2["notice:1023"] == 1
    assert dropped2["frame_with_notice"] == 1
    assert {r["gid"]: r["notice_near"] for r in rows2} == {2: False, 3: True}
    assert olf._JOB["frame_rule"].last == [(541.0, 76.0, 800.0, 106.0)]
    # the same frame WITHOUT a notice: round 2 scores every row, adds nothing
    ref = _round2_job(monkeypatch, boxes, _ground())
    olf._JOB["frame_rule"] = ml.NoticeRule()
    rows3, dropped3, _ = ml._check_rows_round2(ref)
    assert [r["gid"] for r in rows3] == [1, 2, 3] and _no_notice(dropped3)
    assert all("notice_near" not in r for r in rows3)
    olf._JOB.clear()


def test_round2_rule_under_model_candidates_are_dropped_before_their_fit() -> None:
    """The rule filters the under-model list too (o3h: before the fit), and leaves None alone."""
    import numpy as np

    frame = _ground()
    _draw_notice(frame, 541, 76, 732, 106)
    e = SimpleNamespace(job=1273)
    over = (e, None, None, SimpleNamespace(box=(600.0, 90.0, 650.0, 160.0)), (0, ""))
    clear = (e, None, None, SimpleNamespace(box=(100.0, 300.0, 150.0, 370.0)), (0, ""))
    from collections import Counter

    d: Counter[str] = Counter()
    rule = ml.NoticeRule()
    c, u = rule(np.ascontiguousarray(frame), [clear], [over, clear], d)
    assert c == [clear] and u == [clear] and d["notice:1273"] == 1
    c, u = rule(frame, [over], None, Counter())
    assert c == [] and u is None


def test_c1_rule_refusals() -> None:
    """round2: gef_fild10 only, never round 1's spent TEST; TEST2 (a9-a11) under round2 only;
    round1 everywhere else as before; an unknown rule fails."""
    gef, pay = ml.GEF10, ml.PAYF07
    ml.c1_rule_refusals(gef, "round1", ["/x/20261025T221059-rdp-rogue-a2"])
    ml.c1_rule_refusals(gef, "round2", ["/x/20261025T221059-rdp-rogue-a2",
                                        f"/x/{ml.GEF10_WATCH}:spots=0-10"])  # fmt: skip
    ml.c1_rule_refusals(gef, "round1", ["/x/20261026T010738-rdp-rogue-a7"])  # T1's own (13r)
    for sid in ("20261026T044312-rdp-rogue-a9", "20261026T052148-rdp-rogue-a10",
                "20261026T055949-rdp-rogue-a11"):  # fmt: skip
        ml.c1_rule_refusals(gef, "round2", [f"/x/{sid}"])
        with pytest.raises(SystemExit, match="TEST2"):
            ml.c1_rule_refusals(gef, "round1", [f"/x/{sid}"])
    for part in ("/x/20261026T010738-rdp-rogue-a7", "/x/20261026T020202-rdp-rogue-a8",
                 f"/x/{ml.GEF10_WATCH}:spots=11-14", f"/x/{ml.GEF10_WATCH}:spots=10-11",
                 f"/x/{ml.GEF10_WATCH}"):  # fmt: skip
        with pytest.raises(SystemExit, match="spent"):
            ml.c1_rule_refusals(gef, "round2", [part])
    # T-8 (xmas02-detector.md): round2 now also runs on xmas_dun02; still never on pay_fild07
    with pytest.raises(SystemExit, match="gef_fild10 / xmas_dun02 only, not pay_fild07"):
        ml.c1_rule_refusals(pay, "round2", ["/x/20261024T173322-rdp-thief-s1"])
    with pytest.raises(SystemExit, match="c1-rule"):
        ml.c1_rule_refusals(gef, "round3", [])


def test_round2_test2_is_refused_like_test_and_round1_test_is_unchanged() -> None:
    spec = ml.GEF10
    for sid in ("20261026T044312-rdp-rogue-a9", "20261026T052148-rdp-rogue-a10",
                "20261026T055949-rdp-rogue-a11", "20261026T120000-rdp-w3"):  # fmt: skip
        assert spec.is_test(sid, None) and not spec.is_round1_test(sid, None)
    assert not spec.is_test("20261026T014529-rdp-w2", None)  # w2 stays TRAIN
    for sid in ("20261025T213953-rdp-rogue-a1", "20261026T002500-rdp-rogue-a6"):
        assert not spec.is_test(sid, None)  # a1 is not a11's prefix match, a6 stays TRAIN-able
    assert spec.is_round1_test("20261026T010738-rdp-rogue-a7", None)
    assert ml.PAYF07.test2_suffixes == ()


def test_check_c1_rule_flag_defaults_to_round1(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    seen: dict[str, Any] = {}

    def fake(a: argparse.Namespace) -> dict[str, Any]:
        seen["rule"] = a.c1_rule
        raise SystemExit(0)

    monkeypatch.setattr(ml, "cmd_check", fake)
    for argv, want in ((["check", "/x", "--params", "p", "--out", "o"], "round1"),
                       (["check", "/x", "--params", "p", "--out", "o", "--c1-rule", "round2"],
                        "round2")):  # fmt: skip
        with pytest.raises(SystemExit):
            ml.main(argv)
        assert seen["rule"] == want
    with pytest.raises(SystemExit):
        ml.main(["check", "/x", "--params", "p", "--out", "o", "--c1-rule", "round3"])


def test_round3_test3_is_refused_by_name() -> None:
    """gef10-round3.md 2: e3b (the staged session of 2026-10-29) is TEST3, held out by NAME; E3
    stays readable (TRAIN, its spots 0-3 also FIT under round 3)."""
    spec = ml.GEF10
    assert spec.is_test("20261029T110813-rdp-stage-gef10-e3b", None)
    assert spec.is_test("20261029T110813-rdp-stage-gef10-e3b", frozenset({2}))
    assert not spec.is_test("20261028T151136-rdp-stage-gef10-e3", None)
    assert not spec.is_round1_test("20261029T110813-rdp-stage-gef10-e3b", None)
    assert ml.PAYF07.test3_suffixes == ()


def test_round3_staged_sessions_have_their_own_kind() -> None:
    """gef10-round3.md 5: E3 / e3b are stage_items sessions (a spot = a first warp followed by
    drops; the two view warps after it are not spots), the watch keeps one cell per map change;
    any other session has no spots. E3's spots 0-3 are FIT for the item anchor."""
    spec = ml.GEF10
    e3, e3b = "20261028T151136-rdp-stage-gef10-e3", "20261029T110813-rdp-stage-gef10-e3b"
    assert spec.staged_kind_of(spec.staged) == "watch"
    assert spec.staged_kind_of(e3) == "items" and spec.staged_kind_of(e3b) == "items"
    assert spec.staged_kind_of("20261027T015515-rdp-rogue-e4") is None
    events = [
        _ev("map_change", 10, map="gef_fild10.gat"), _ev("drop_request", 40),
        _ev("map_change", 60, map="gef_fild10.gat"),  # view (3, 0): no drop
        _ev("map_change", 70, map="gef_fild10.gat"),  # view (0, 3)
        _ev("map_change", 90, map="gef_fild10.gat"), _ev("drop_request", 120),
        _ev("map_change", 140, map="gef_fild10.gat"),
    ]  # fmt: skip
    assert ml.starts_of("items", "gef_fild10", events) == [10 * S, 90 * S]
    assert ml.starts_of("watch", "gef_fild10", events) == [10 * S, 60 * S, 70 * S, 90 * S, 140 * S]
    assert ml.staged_starts(spec, events) == ml.starts_of("watch", "gef_fild10", events)
    assert spec.is_fit(e3, frozenset({0, 3})) and not spec.is_fit(e3, frozenset({4}))
    assert not spec.is_fit(e3b, frozenset({0}))
    assert ml.PAYF07.staged_extra == {}


# --- gef10-eval.md AMENDMENT R2-2: TEST2's evaluation labels and pack (--eval-test2) ------------
# Session NAMES only: no frame, label or packet of TEST2 / TEST / TEST3 is read; every label
# document below is synthetic.

A9 = "20261026T044312-rdp-rogue-a9"
A10 = "20261026T052148-rdp-rogue-a10"
A11 = "20261026T055949-rdp-rogue-a11"
W3 = "20261026T112924-rdp-w3"
A7 = "20261026T010738-rdp-rogue-a7"
A2 = "20261025T221059-rdp-rogue-a2"
E3B = "20261029T110813-rdp-stage-gef10-e3b"
PILOT = "20261025T200922-rdp-rogue-pilot"


def _why(spec: Any, sid: str, spots: frozenset[int] | None = None) -> str:
    why = ml.eval_test2_refusal(spec, sid, spots)
    assert why is not None, sid
    return why


def test_eval_test2_refusal_accepts_test2_only() -> None:
    gef = ml.GEF10
    for sid in (A9, A10, A11, W3):
        assert ml.eval_test2_refusal(gef, sid, None) is None
    for sid, spots in ((A7, None), ("20261026T020202-rdp-rogue-a8", None),
                       ("20261026T010101-rdp-rogue-s7", None), (ml.GEF10_WATCH, None),
                       (ml.GEF10_WATCH, frozenset({11, 12})),
                       (ml.GEF10_WATCH, frozenset({10, 11}))):  # fmt: skip
        assert "round 1's TEST is spent" in _why(gef, sid, spots)
    assert "TEST3" in _why(gef, E3B) and "TEST3" in _why(gef, E3B, frozenset({0}))
    for sid, spots in ((A2, None), (PILOT, None), ("20261026T014529-rdp-w2", None),
                       ("20261025T213953-rdp-rogue-a1", None),
                       (ml.GEF10_WATCH, frozenset(range(11))),
                       ("20261028T151136-rdp-stage-gef10-e3", frozenset({0}))):  # fmt: skip
        assert "not a TEST2 part" in _why(gef, sid, spots)  # FIT, TRAIN (a1 is not a11)
    assert "gef_fild10's only" in _why(ml.PAYF07, A9)


def _labels_args(tmp_path: Path, part: str, status: str | None = "FROZEN",
                 map_name: str = "gef_fild10", **flag: Any) -> Any:  # fmt: skip
    import argparse
    import json

    params = tmp_path / "params.json"
    labels = "gef10-o3h-e" if map_name == "gef_fild10" else ml.LABELS
    params.write_text(json.dumps({"labels": labels, "map": map_name, "status": status,
                                  "offset_ms": 120.0}))  # fmt: skip
    classes = tmp_path / "classes.json"
    classes.write_text(json.dumps({"monsters": [1273, 1023]}))
    return argparse.Namespace(map=map_name, params=params, parts=[part], classes=classes,
                              layout_templates=None, workers=1, **flag)  # fmt: skip


def test_labels_eval_test2_refusals_before_anything_is_read(tmp_path: Path) -> None:
    """Every refusal fires on the part's NAME or the parameters' status, before a session is
    opened (the parts do not exist)."""
    for part, match in ((f"/x/{A9}", "gef_fild10's only"),):
        with pytest.raises(SystemExit, match=match):
            ml.cmd_labels(_labels_args(tmp_path, part, map_name="pay_fild07", eval_test2=True))
    for part, match in ((f"/x/{A2}", "not a TEST2 part"), (f"/x/{PILOT}", "not a TEST2 part"),
                        (f"/x/{A7}", "spent"), (f"/x/{ml.GEF10_WATCH}:spots=11-14", "spent"),
                        (f"/x/{E3B}", "TEST3")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.cmd_labels(_labels_args(tmp_path, part, eval_test2=True))
    for status in ("PROPOSED_NOT_FROZEN: P1", None):
        with pytest.raises(SystemExit, match="FROZEN parameters only"):
            ml.cmd_labels(_labels_args(tmp_path, f"/x/{A9}", status=status, eval_test2=True))


def _fake_session(monkeypatch: pytest.MonkeyPatch, sid: str, spec: Any = ml.GEF10) -> list[str]:
    """cmd_labels' readers replaced: the session ``sid`` (as its manifest names it), two candidate
    frames, the labeller's frames synthetic."""
    from collections import Counter

    opened: list[str] = []
    sess = SimpleNamespace(sid=sid, spots=None, name=sid, refs=[1, 2, 3],
                           dropped=Counter({"self_moving": 1}), spec=spec,
                           candidates_at=lambda off: [1, 2])  # fmt: skip

    def fake_open(part: str, spec: Any, layout_templates: Any) -> Any:
        opened.append(part)
        return sess

    monkeypatch.setattr(ml.RecSession, "open", staticmethod(fake_open))
    monkeypatch.setattr(ml, "frozen_occluders", lambda params, spec: _NO_TERRAIN)
    monkeypatch.setattr(ml, "labeler_for", lambda *a, **k: "labeler")
    frames = [_frame([1273], []), _frame([1023], [])]
    monkeypatch.setattr(olf, "run_parallel", lambda func, refs, workers: frames)
    return opened


LABELS_KEYS = ["what", "labels", "params_status", "map", "part", "session", "labelled_at",
               "commit", "params", "params_sha256", "frames_recorded", "candidates",
               "candidate_drops", "counts", "counts_engaged", "frames"]  # fmt: skip


def test_labels_eval_test2_accepts_a_test2_part_under_frozen_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for sid in (A9, A10, A11, W3):
        opened = _fake_session(monkeypatch, sid)
        a = _labels_args(tmp_path, f"/x/{sid}", eval_test2=True)
        out = ml.cmd_labels(a)
        assert opened == [f"/x/{sid}"]
        assert out["eval_test2"] is True and out["session"] == sid
        assert out["params_status"] == "FROZEN"
        assert out["classes"] == str(a.classes)
        assert out["classes_sha256"] == olf.sha256_file(a.classes)
        assert out["counts"]["per_species"]["1273"]["kept"] == 1
        assert list(out) == LABELS_KEYS[:13] + ["eval_test2", "classes", "classes_sha256"] + \
            LABELS_KEYS[13:]  # fmt: skip
    # the manifest's session id is checked too: a renamed TRAIN directory is refused
    _fake_session(monkeypatch, A2)
    with pytest.raises(SystemExit, match="not a TEST2 part"):
        ml.cmd_labels(_labels_args(tmp_path, f"/x/{A9}", eval_test2=True))
    olf._JOB.clear()


def test_labels_without_the_flag_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                              ) -> None:  # fmt: skip
    """No flag (or a namespace without the attribute): TEST2 is refused by NAME as before, a
    TRAIN part labels under any status as before, and the output gains no key."""
    _fake_session(monkeypatch, A9)
    for flag in ({}, {"eval_test2": False}):
        with pytest.raises(SystemExit, match=r"shares frames with TEST \(3b\)"):
            ml.cmd_labels(_labels_args(tmp_path, f"/x/{A9}", **flag))
    _fake_session(monkeypatch, A2)
    for flag in ({}, {"eval_test2": False}):
        out = ml.cmd_labels(_labels_args(tmp_path, f"/x/{A2}", status="PROPOSED_NOT_FROZEN: P1",
                                         **flag))  # fmt: skip
        assert list(out) == LABELS_KEYS and out["session"] == A2
    olf._JOB.clear()


def test_eval_test2_flags_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(name: str) -> Any:
        def run(a: Any) -> Any:
            seen[name] = (a.eval_test2, getattr(a, "per_species", "absent"))
            raise SystemExit(0)

        return run

    monkeypatch.setattr(ml, "cmd_labels", fake("labels"))
    monkeypatch.setattr(ml, "cmd_pack", fake("pack"))
    lab = ["labels", f"/x/{A9}", "--map", "gef_fild10", "--params", "p", "--out", "o"]
    pack = ["pack", "l.json", "--map", "gef_fild10", "--seed", "35", "--pack-dir", "pk",
            "--key-dir", "k", "--instructions", "i", "--instructions-sha256", "h",
            "--out", "o"]  # fmt: skip
    flags = ["--eval-test2", "--per-species", "60"]
    for argv, name, want in ((lab, "labels", (False, "absent")),
                             (lab + ["--eval-test2"], "labels", (True, "absent")),
                             (pack, "pack", (False, None)),
                             (pack + flags, "pack", (True, 60))):  # fmt: skip
        with pytest.raises(SystemExit):
            ml.main(argv)
        assert seen[name] == want


def _pack_args(tmp_path: Path, labels: list[Path], **kw: Any) -> Any:
    import argparse
    import hashlib

    instr = tmp_path / "instructions.txt"
    instr.write_text("synthetic instructions\n")
    base = {"map": "gef_fild10", "labels": labels, "seed": 35, "pack_dir": tmp_path / "pack",
            "key_dir": tmp_path / "key", "instructions": instr,
            "instructions_sha256": hashlib.sha256(instr.read_bytes()).hexdigest(),
            "session_root": "/nas", "min_fit": None, "exclude_key": None}  # fmt: skip
    return argparse.Namespace(**{**base, **kw})


def test_pack_flag_refusals_before_anything_is_read(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    for kw, match in (({"eval_test2": False, "per_species": 60}, "only with --eval-test2"),
                      ({"per_species": 60}, "only with --eval-test2"),
                      ({"eval_test2": True, "per_species": 60, "map": "pay_fild07"},
                       "gef_fild10's only"),
                      ({"eval_test2": True, "per_species": None}, "--per-species N"),
                      ({"eval_test2": True}, "--per-species N"),
                      ({"eval_test2": True, "per_species": 0}, "--per-species N")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.cmd_pack(_pack_args(tmp_path, [], instructions=missing, **kw))
    with pytest.raises(FileNotFoundError):  # no flag: on to the instructions, as before
        ml.cmd_pack(_pack_args(tmp_path, [], instructions=missing))


def _label_doc(tmp_path: Path, sid: str, kept: list[list[tuple[int, bool, float, bool]]],
               part: str | None = None, eval_test2: bool = True,
               params_sha: str = "f" * 64) -> Path:  # fmt: skip
    """A synthetic label file: per frame, its kept labels as (mob, engaged, ncc, under)."""
    import json

    frames = [{"frame_id": i, "t": (i + 1) * S, "shard": "shard-000000.tar", "offset": 512 * i,
               "size": 100, "spot": None,
               "kept": [{"gid": 1000 + j, "mob": m, "box": [100.0, 100.0, 140.0, 160.0],
                         "ncc": ncc, "under": under, "state": "idle", "engaged": eng}
                        for j, (m, eng, ncc, under) in enumerate(ks)]}
              for i, ks in enumerate(kept)]  # fmt: skip
    doc = {"labels": "gef10-o3h-e", "session": sid, "part": part or sid,
           "params_sha256": params_sha, "params_status": "FROZEN", "frames": frames,
           **({"eval_test2": True} if eval_test2 else {})}  # fmt: skip
    path = tmp_path / f"{(part or sid).replace(':', '_')}-{int(eval_test2)}.json"
    path.write_text(json.dumps(doc))
    return path


def test_pack_pool_eval_test2_takes_test2_label_files_only(tmp_path: Path) -> None:
    one = [[(1273, False, 0.9, False)]]
    good = [_label_doc(tmp_path, sid, one) for sid in (A9, A10, A11, W3)]
    pool, sources, shas, statuses = ml.pack_pool(good, ml.GEF10, "/nas", eval_test2=True)
    assert len(pool[1273]) == 4 and [s["part"] for s in sources] == [A9, A10, A11, W3]
    assert pool[1273][0]["ref"] == (f"/nas/{A9}/shard-000000.tar", 0, 100)
    assert shas == {"f" * 64} and statuses == {"FROZEN"}
    for path, match in ((_label_doc(tmp_path, A2, one), "not a TEST2 part"),
                        (_label_doc(tmp_path, PILOT, one), "not a TEST2 part"),
                        (_label_doc(tmp_path, ml.GEF10_WATCH, one,
                                    part=f"{ml.GEF10_WATCH}:spots=0-10"), "not a TEST2 part"),
                        (_label_doc(tmp_path, A7, one), "spent"),
                        (_label_doc(tmp_path, ml.GEF10_WATCH, one,
                                    part=f"{ml.GEF10_WATCH}:spots=11-14"), "spent"),
                        (_label_doc(tmp_path, E3B, one), "TEST3"),
                        (_label_doc(tmp_path, A9, one, eval_test2=False),
                         "not made by labels --eval-test2")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.pack_pool([good[0], path], ml.GEF10, "/nas", eval_test2=True)
    # without the flag: TEST2 is refused like any TEST, TRAIN / FIT are taken (as before)
    with pytest.raises(SystemExit, match="TEST is not in T2's pool"):
        ml.pack_pool([good[0]], ml.GEF10, "/nas")
    train = [_label_doc(tmp_path, A2, one, eval_test2=False), _label_doc(tmp_path, PILOT, one)]
    assert len(ml.pack_pool(train, ml.GEF10, "/nas")[0][1273]) == 2


def test_eval_test2_sample_every_species_n_per_stratum() -> None:
    """No conditional tier: every map species with one kept label is drawn; per species and
    stratum the first N of t2_order (salt gef10, the stratum in the seed), then T2's shuffle."""
    pool = {1273: [_item(A9, f, 1, 1273, engaged=f % 3 == 0) for f in range(90)],  # N 60 / E 30
            1023: [_item(A10, 5, 2, 1023)],  # one N label
            1190: [_item(W3, f, 3, 1190, engaged=True) for f in range(4)],  # E only
            1002: [_item(A9, f, 4, 1002) for f in range(9)]}  # not the map's  # fmt: skip
    chosen, per, species = ml.eval_test2_sample(pool, ml.GEF10, 35, 60)
    assert species == [1273, 1023, 1190]
    assert per == {"1273:N": {"pool": 60, "sampled": 60}, "1273:E": {"pool": 30, "sampled": 30},
                   "1023:N": {"pool": 1, "sampled": 1}, "1023:E": {"pool": 0, "sampled": 0},
                   "1190:N": {"pool": 0, "sampled": 0},
                   "1190:E": {"pool": 4, "sampled": 4}}  # fmt: skip
    assert len(chosen) == 95 and all(c["mob"] != 1002 for c in chosen)
    assert ml.t2_sample(pool, ml.GEF10, 35)[2] == [1273]  # T2's tier would drop 1023 and 1190
    chosen2, per2, _ = ml.eval_test2_sample(pool, ml.GEF10, 35, 2)
    assert {k: v["sampled"] for k, v in per2.items()} == {
        "1273:N": 2, "1273:E": 2, "1023:N": 1, "1023:E": 0, "1190:N": 0, "1190:E": 2,
    }  # fmt: skip
    assert all(bool(c["engaged"]) == (c["stratum"] == "E") for c in chosen2)
    want: list[dict[str, Any]] = []
    for mob in (1273, 1023, 1190):
        for st in ("N", "E"):
            items = ml.stratum_of(pool[mob], st)
            want += [{**it, "stratum": st} for it in ml.t2_order(items, 35, mob, "gef10", st)[:2]]
    random.Random("gef10:35:order").shuffle(want)
    assert chosen2 == want
    with pytest.raises(SystemExit, match="at least 1"):
        ml.eval_test2_sample(pool, ml.GEF10, 35, 0)


KEY_KEYS = ["labels", "seed", "per_species_target", "candidates", "letters", "crops",
            "tier_species", "per_species", "sources", "params_sha256", "params_status",
            "instructions_sha256", "built_at", "commit", "note", "min_fit", "removed_from_pool",
            "exclude_keys"]  # fmt: skip
PACK_OUT_KEYS = ["pack", "key", "crops", "per_species", "tier_species", "letters",
                 "params_status", "removed_from_pool", "grids"]  # fmt: skip


def _pack_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    """cmd_pack's pixel readers replaced: a grey frame, no sprites, a stub reference sheet."""
    import numpy as np
    import orc_label_sheets as ols

    monkeypatch.setattr(ml, "read_png", lambda ref: np.full((720, 1280, 3), 90, np.uint8))
    monkeypatch.setattr(ml, "use_kb", lambda spec: None)
    monkeypatch.setattr(ml.qa_export, "Sheets", lambda directory: lambda mob: None)
    stub = np.zeros((8, 8, 3), np.uint8)
    monkeypatch.setattr(ols, "reference_sheet", lambda sheets, letters, views="one": stub)


def test_pack_eval_test2_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The evaluation pack from two synthetic TEST2 label files: the weak_fit floor as before,
    every species with a kept label, N per species and stratum, the key's records."""
    import json

    _pack_fakes(monkeypatch)
    a9 = [[(1273, False, 0.9, False), (1273, True, 0.9, False)] for _ in range(5)]
    a9[0].append((1189, False, 0.5, False))  # weak fit, clear of a model: leaves the pool
    a10 = [[(1023, False, 0.9, False)] for _ in range(3)]
    a10[0].append((1686, True, 0.8, False))
    labels = [_label_doc(tmp_path, A9, a9), _label_doc(tmp_path, A10, a10)]
    a = _pack_args(tmp_path, labels, eval_test2=True, per_species=2, min_fit=0.636)
    out = ml.cmd_pack(a)
    key = json.loads((tmp_path / "key" / "answer_key.json").read_text())
    assert key["eval_test2"] is True and key["per_species_target"] == 2 and key["seed"] == 35
    assert list(key) == KEY_KEYS + ["eval_test2"]
    assert key["tier_species"] == [1273, 1023, 1686]
    assert {k: v["sampled"] for k, v in key["per_species"].items()} == {
        "1273:N": 2, "1273:E": 2, "1023:N": 2, "1023:E": 0, "1686:N": 0, "1686:E": 1,
    }  # fmt: skip
    assert key["removed_from_pool"]["1189"] == {"weak_fit": 1, "judged_before": 0}
    assert key["min_fit"] == 0.636 and key["params_status"] == ["FROZEN"]
    assert len(key["crops"]) == 7 and out["crops"] == 7
    assert all(c["samples"] == [c["stratum"]] and c["engaged"] == (c["stratum"] == "E")
               for c in key["crops"].values())  # fmt: skip
    assert {c["session"] for c in key["crops"].values()} == {A9, A10}
    assert out["eval_test2"] is True and out["per_species_target"] == 2
    assert list(out) == PACK_OUT_KEYS + ["per_species_target", "eval_test2"]
    assert len(list((tmp_path / "pack" / "crops").iterdir())) == 7


def test_pack_without_the_flag_is_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            ) -> None:  # fmt: skip
    """No flag: T2's tier (>= 30 N labels), 30 per species and stratum, the key's fields and the
    output's exactly as before (no eval_test2, per_species_target 30)."""
    import json

    _pack_fakes(monkeypatch)
    a2 = [[(1273, False, 0.9, False)] for _ in range(32)] + [[(1023, False, 0.9, False)]]
    labels = [_label_doc(tmp_path, A2, a2, eval_test2=False)]
    for flag in ({}, {"eval_test2": False, "per_species": None}):
        out = ml.cmd_pack(_pack_args(tmp_path, labels, seed=31, **flag))
        key = json.loads((tmp_path / "key" / "answer_key.json").read_text())
        assert list(key) == KEY_KEYS and list(out) == PACK_OUT_KEYS
        assert key["per_species_target"] == ml.T2_PER_SPECIES == 30
        assert key["tier_species"] == [1273]  # 1023 has 1 N label (< 30): conditional
        assert key["per_species"] == {"1273:N": {"pool": 32, "sampled": 30},
                                      "1273:E": {"pool": 0, "sampled": 0}}  # fmt: skip
        assert out["crops"] == 30


# --- xmas_dun02 (docs/planning/xmas02-detector.md; its tool gaps T-1, T-2, T-3, T-8, T-9) -------
# Session NAMES only: no xmas_dun02 recording is read (X2 is TEST; the others do not exist yet).
# The positive cases on real data read gef_fild10's w2 (a TRAIN session) and X2's MANIFEST only.

X2 = ml.XMAS02_X2
XW1 = "20261106T120000-rdp-xmas02-xw1"  # the names record_session gives `--label xmas02-xw1`
XW2 = "20261106T130000-rdp-xmas02-xw2"
XW5 = "20261106T140000-rdp-xmas02-xw5"
XP1 = "20261106T150000-rdp-xmas02-xp1"
XTEST = (XW5, XP1, X2)
NAS = Path("/mnt/poring-lab-datasets")
W2 = "20261026T014529-rdp-w2"  # gef_fild10's immune lattice watch (TRAIN)
LEGACY_CHAT = (0, 532, 600, 626)
STANDARD_CHAT = (0, 585, 600, 720)


def _old_rects(layout: str) -> tuple[tuple[int, int, int, int], ...]:
    """map_labels' rectangles BEFORE T-1: client_layout.RECTS of the layout, as they were."""
    import client_layout

    return tuple(tuple(r) for r in client_layout.RECTS[ml.LAYOUT_RECTS[layout]])


def test_t1_older_sessions_keep_their_rectangles_exactly() -> None:
    """Every session before the 2026-11-05 cutover (the maps' own role tables and names, the
    gef10 TEST / TEST2 names): the rectangles are RECTS's, bit for bit, in both layouts; their chat
    window is the legacy one (0, 532, 600, 626) and nothing is nested."""
    sids = {s for spec in (ml.PAYF07, ml.GEF10) for s in (*spec.fit, *spec.test,
                                                         *spec.staged_extra)}  # fmt: skip
    sids |= {W2, A2, A7, A9, A10, A11, W3, E3B, PILOT, "20261105T115959-rdp-last-legacy"}
    for sid in sorted(sids):
        for layout in ("hunt", "rows4"):
            got = ml.session_ui_rects(sid, layout)
            assert got == _old_rects(layout), (sid, layout)
            assert got[4] == LEGACY_CHAT


def test_t1_sessions_from_the_cutover_use_the_standard_chat_window() -> None:
    """From 20261105T12 on (X2, every xmas02 session): the 2026-11-05 standard chat window, and
    notice_left (0, 668, 50, 720), which it holds whole, is dropped (covered_fraction sums)."""
    for sid in ("20261105T120000-rdp-first-standard", X2, XW1, XW5):
        for layout in ("hunt", "rows4"):
            old = _old_rects(layout)
            got = ml.session_ui_rects(sid, layout)
            assert got == (*old[:4], STANDARD_CHAT, old[6]), (sid, layout)
            assert (0, 668, 50, 720) not in got


def test_t1_session_labeler_sets_the_sessions_rectangles(monkeypatch: pytest.MonkeyPatch) -> None:
    """session_labeler takes the session id from the MANIFEST (the frame cache calls it with
    (path, spec) only) and writes the rectangles as (x, y, w, h)."""

    class FakeLabeler:
        def __init__(self, path: Path, *_a: Any, **_k: Any) -> None:
            self.manifest = {"session_id": path.name}
            self.ui_rects: Any = None
            self.timeline = SimpleNamespace(events=[], maps={}, die_ms={}, default_die_ms=0)

    monkeypatch.setattr(ml.qa_export, "Labeler", FakeLabeler)
    monkeypatch.setattr(ml.qa_export, "Sheets", lambda directory: directory)
    monkeypatch.setattr(ml, "use_kb", lambda spec: None)
    monkeypatch.setattr(ml, "Timeline", lambda *a, **k: "timeline")

    def xywh(rects: Any) -> tuple[tuple[int, int, int, int], ...]:
        return tuple((x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in rects)

    old = ml.session_labeler(Path("/x") / W2, ml.GEF10)
    assert old.ui_rects == xywh(_old_rects("hunt")) and old.sheets == ml.GEF10.sprites
    four = ml.session_labeler(Path("/x") / ml.GEF10_WATCH, ml.GEF10, "rows4")
    assert four.ui_rects == xywh(_old_rects("rows4"))
    new = ml.session_labeler(Path("/x") / XW1, ml.XMAS02)
    assert new.ui_rects == xywh(ml.session_ui_rects(XW1)) and (0, 585, 600, 135) in new.ui_rects
    assert len(new.ui_rects) == 6


@pytest.mark.skipif(not (NAS / W2 / "packets.jsonl.gz").exists(), reason="the NAS is absent")
def test_t1_positive_case_a_real_gef10_session() -> None:
    """A REAL gef_fild10 session (w2, TRAIN: manifest + packets, no frame): the label stack's
    rectangles are RECTS's (the code before T-1) in both layouts, and its recording path passes."""
    from dataclasses import replace

    from poring_dataset import mapcache

    kbs = (ROOT / "data" / "kb", Path("/home/batt/docker/poring-lab/data/kb"))
    kb = next((p for p in kbs if (p / "classes.json").exists()), None)
    if kb is None:
        pytest.skip("data/kb is absent")
    try:
        mapcache.load(prere=True)
    except mapcache.MapCacheError:
        pytest.skip("the generated map cache is absent (a worktree's package sources)")
    ml.check_recording(json.loads((NAS / W2 / "manifest.json").read_text()))
    spec = replace(ml.GEF10, kb=kb)
    for layout in ("hunt", "rows4"):
        lab = ml.session_labeler(NAS / W2, spec, layout)
        assert lab.ui_rects == tuple((x0, y0, x1 - x0, y1 - y0)
                                     for x0, y0, x1, y1 in _old_rects(layout))  # fmt: skip


X2_MANIFEST = NAS / X2 / "manifest.json"


@pytest.mark.skipif(not X2_MANIFEST.exists(), reason="the NAS is absent")
def test_t3_positive_case_x2s_manifest_passes() -> None:
    """T-3's positive case: X2's manifest (recorder v6; ITS MANIFEST ONLY, X2 is TEST) is on the
    recording path now; the same manifest at v5 and v7 (ADR-0024) passes and at v8 is refused
    (the rule: a recorder version nobody has read is refused)."""
    m = json.loads(X2_MANIFEST.read_text())
    assert m["recorder_version"] == 6 and m["session_id"] == X2
    ml.check_recording(m)
    ml.check_recording({**m, "recorder_version": 5})
    ml.check_recording({**m, "recorder_version": 7})
    with pytest.raises(SystemExit, match="recorder_version"):
        ml.check_recording({**m, "recorder_version": 8})


def test_t2_xmas02_spec() -> None:
    spec = ml.MAPS["xmas_dun02"]
    assert spec is ml.XMAS02 and spec.name == "xmas_dun02" and spec.cells == (260, 260)
    assert spec.species == (1249, 1248, 1265, 1246, 1515, 1607)  # 1b / D3; 1251 is OUT
    assert spec.conditional == (1515, 1607) and 1251 not in spec.species
    assert spec.walkers == (1249, 1248, 1265, 1246, 1515) and spec.fit_px == 6
    assert spec.labels == "xmas02-o3h-t" and spec.t2_salt == "xmas02" and spec.t2_seed == 51
    assert spec.dying_rule and not spec.engaged_labels and spec.engaged_fixed == "E0"
    assert spec.reference == (1251, 1002, 1062)  # 6: + Stormy Knight, Poring, Santa Poring
    assert len(list(spec.species) + list(spec.reference)) <= 12  # cmd_pack's reference cap
    x = Path("/dev/shm/poring-lab-tmp/xmas-det")
    assert spec.rsw == x / "grf/data/xmas_dun02.rsw" and spec.models == x / "grf/data/model"
    assert spec.kb == x / "kb-sprites" and spec.kb_classes == ROOT / "data/kb/classes.json"
    assert spec.sprites == x / "sprites/data/sprite/몬스터"
    assert spec.layouts == {} and spec.staged_kind_of(XW1) is None
    assert spec.plan == "docs/planning/xmas02-detector.md"
    assert ml.strata_for(spec) == (None,)  # one T2 stratum (E0: no engaged label)
    # the older maps keep their KB layout and rules
    assert ml.PAYF07.kb_classes is None and ml.GEF10.kb_classes is None
    assert ml.PAYF07.engaged_fixed is None and ml.GEF10.engaged_fixed is None


def test_t2_use_kb_reads_the_classes_from_data_kb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ml.qa_export, "KB_CLASSES", None)
    monkeypatch.setattr(ml.qa_export, "KB_SPRITE_NAMES", None)
    ml.use_kb(ml.XMAS02)
    assert ml.qa_export.KB_CLASSES == ROOT / "data/kb/classes.json"
    assert ml.qa_export.KB_SPRITE_NAMES == ml.XD / "kb-sprites/monster_sprite_names.json"
    ml.use_kb(ml.GEF10)  # unchanged: both from the map's KB directory
    assert ml.qa_export.KB_CLASSES == ml.G10 / "kb/classes.json"
    assert ml.qa_export.KB_SPRITE_NAMES == ml.G10 / "kb/monster_sprite_names.json"


def test_t2_xmas02_roles_by_name() -> None:
    """3b: FIT = xw1, TEST = xw5, xp1, X2 -- all by NAME; TRAIN (xw2-xw4, xw6, xw7) neither."""
    spec = ml.XMAS02
    assert spec.is_fit(XW1, None) and not spec.is_test(XW1, None) and spec.overlaps_fit(XW1, None)
    for sid in XTEST:
        assert spec.is_test(sid, None) and spec.is_round1_test(sid, None)
        assert not spec.is_fit(sid, None) and not spec.overlaps_fit(sid, None)
    for k in (2, 3, 4, 6, 7, 10, 11, 15, 51):
        sid = f"20261106T16000{k % 10}-rdp-xmas02-xw{k}"
        assert not spec.is_test(sid, None) and not spec.is_fit(sid, None), sid  # xw15 is not xw5
    for sid in ("20261106T160000-rdp-xmas02-xp10", "20261106T160000-rdp-xmas02-x2",
                "20261106T160000-rdp-xmas02-xw1b"):  # fmt: skip
        assert not spec.is_test(sid, None) and not spec.is_fit(sid, None), sid
    # the other maps' names are nothing here, and xmas02's nothing there
    assert not spec.is_test(A7, None) and not spec.is_fit(PILOT, None)
    for sid in (XW1, *XTEST):
        assert not ml.GEF10.is_test(sid, None) and not ml.GEF10.is_fit(sid, None)
        assert not ml.PAYF07.is_test(sid, None) and not ml.PAYF07.is_fit(sid, None)
    assert ml.GEF10.fit_suffixes == () and ml.GEF10.overlaps_fit(ml.GEF10_WATCH, None)


def _ns(**kw: Any) -> Any:
    import argparse

    return argparse.Namespace(**kw)


def test_t2_measuring_commands_refuse_test_by_name_before_reading() -> None:
    """offset / threshold / engaged refuse a TEST (or non-FIT) part by its NAME before anything is
    read: the paths do not exist, so a read would raise FileNotFoundError instead."""
    common = {"map": "xmas_dun02", "layout_templates": None, "workers": 1}
    for sid in (*XTEST, XW2):
        with pytest.raises(SystemExit, match="not a FIT part"):
            ml.cmd_offset(_ns(**common, parts=[f"/x/{sid}"], diagnostic=False))
        with pytest.raises(SystemExit, match="not a FIT part"):
            ml.cmd_threshold(_ns(**common, parts=[f"/x/{sid}"], offset=None,
                                 proposed_offset_ms=120.0, proposal="P1"))  # fmt: skip
    for sid in XTEST:  # 9b's diagnostic reads any non-TEST part, never TEST
        with pytest.raises(SystemExit, match="shares frames with TEST"):
            ml.cmd_offset(_ns(**common, parts=[f"/x/{sid}"], diagnostic=True))
    with pytest.raises(SystemExit, match="does not label engaged units"):  # E0: no selection
        ml.cmd_engaged(_ns(**common, parts=[f"/x/{XW1}"], variants=["E1"]))
    # gef_fild10's engaged selection refuses its TEST by NAME before reading too (new here)
    for part in (f"/x/{A7}", f"/x/{A9}", f"/x/{ml.GEF10_WATCH}:spots=11"):
        with pytest.raises(SystemExit, match="not a FIT part"):
            ml.cmd_engaged(_ns(**{**common, "map": "gef_fild10"}, parts=[part], variants=["E1"]))


def test_t2_the_fit_name_passes_the_name_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """xw1 (FIT by NAME) gets past the refusals to the reading (a missing path: the open fails),
    and the manifest's id is checked again after the open."""
    monkeypatch.setattr(ml, "occluders", lambda spec: "occluders")
    with pytest.raises(FileNotFoundError):
        ml.cmd_offset(_ns(map="xmas_dun02", parts=[f"/nonexistent/{XW1}"], diagnostic=False,
                          layout_templates=None, workers=1))  # fmt: skip
    sess = SimpleNamespace(sid=X2, spots=None, name=X2, spec=ml.XMAS02)
    monkeypatch.setattr(ml.RecSession, "open", staticmethod(lambda p, spec, lt: sess))
    with pytest.raises(SystemExit, match="not a FIT part"):  # a renamed TEST directory
        ml.cmd_offset(_ns(map="xmas_dun02", parts=[f"/x/{XW1}"], diagnostic=False,
                          layout_templates=None, workers=1))  # fmt: skip


def _xparams(tmp_path: Path, status: str | None = "FROZEN") -> Path:
    p = tmp_path / "xparams.json"
    p.write_text(json.dumps({"labels": "xmas02-o3h-t", "map": "xmas_dun02", "status": status,
                             "offset_ms": 120.0, "o3h_tau": 0.5, "tau": olf.TAU,
                             "fit_px": {"1249": 6}, "anchors_px": {}}))  # fmt: skip
    return p


def _xlabels_args(tmp_path: Path, part: str, status: str | None = "FROZEN", **flag: Any) -> Any:
    classes = tmp_path / "classes.json"
    classes.write_text(json.dumps({"monsters": [1249, 1248, 1265, 1246]}))
    return _ns(map="xmas_dun02", params=_xparams(tmp_path, status), parts=[part],
               classes=classes, layout_templates=None, workers=1, **flag)  # fmt: skip


def test_t2_labels_refuse_test_by_name_and_label_fit_and_train(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for sid in XTEST:
        with pytest.raises(SystemExit, match=r"shares frames with TEST \(3b\)"):
            ml.cmd_labels(_xlabels_args(tmp_path, f"/nonexistent/{sid}"))
    for sid in (XW1, XW2):  # FIT (VAL, T2's pool) and TRAIN are labelled
        opened = _fake_session(monkeypatch, sid, ml.XMAS02)
        out = ml.cmd_labels(_xlabels_args(tmp_path, f"/x/{sid}", status="PROPOSED_NOT_FROZEN"))
        assert opened == [f"/x/{sid}"] and out["map"] == "xmas_dun02"
        assert list(out) == LABELS_KEYS and "eval_test" not in out
    _fake_session(monkeypatch, X2, ml.XMAS02)  # a TEST directory renamed: the manifest's id
    with pytest.raises(SystemExit, match="shares frames with TEST"):
        ml.cmd_labels(_xlabels_args(tmp_path, f"/x/{XW2}"))
    olf._JOB.clear()


def _xdoc(tmp_path: Path, sid: str, mobs: list[int], flag: str | None = None,
          n: int = 1) -> Path:  # fmt: skip
    frames = [{"frame_id": i, "t": (i + 1) * S, "shard": "shard-000000.tar", "offset": 512 * i,
               "size": 100, "spot": None,
               "kept": [{"gid": 1000 + j, "mob": m, "box": [100.0, 100.0, 140.0, 160.0],
                         "ncc": 0.9, "under": False, "state": "idle"}
                        for j, m in enumerate(mobs)]}
              for i in range(n)]  # fmt: skip
    doc = {"labels": "xmas02-o3h-t", "map": "xmas_dun02", "session": sid, "part": sid,
           "params_sha256": "e" * 64, "params_status": "FROZEN", "frames": frames,
           **({flag: True} if flag else {})}  # fmt: skip
    path = tmp_path / f"{sid}-{flag}.json"
    path.write_text(json.dumps(doc))
    return path


def test_t2_pack_refuses_test_and_any_seed_but_51(tmp_path: Path) -> None:
    good = _xdoc(tmp_path, XW2, [1249])
    pool, *_ = ml.pack_pool([good, _xdoc(tmp_path, XW1, [1248])], ml.XMAS02, "/nas")
    assert sorted(pool) == [1248, 1249]
    for sid in XTEST:
        with pytest.raises(SystemExit, match="TEST is not in T2's pool"):
            ml.pack_pool([good, _xdoc(tmp_path, sid, [1249])], ml.XMAS02, "/nas")
    missing = tmp_path / "missing.txt"
    for seed in (21, 50, 52, 53):
        with pytest.raises(SystemExit, match="T2 seed is 51"):
            ml.cmd_pack(_pack_args(tmp_path, [good], map="xmas_dun02", seed=seed,
                                   instructions=missing))  # fmt: skip
    with pytest.raises(FileNotFoundError):  # seed 51: on to the instructions
        ml.cmd_pack(_pack_args(tmp_path, [good], map="xmas_dun02", seed=51, instructions=missing))
    with pytest.raises(FileNotFoundError):  # gef10 / payf07 pin no seed (unchanged)
        ml.cmd_pack(_pack_args(tmp_path, [good], seed=52, instructions=missing))


def test_t2_the_cache_refuses_test_label_files(tmp_path: Path) -> None:
    """build_frame_cache --labels map (MapLabelInputs): an xmas02 TEST label file is never cached;
    a TRAIN one is taken (its join rule is the own-C1 check's)."""
    import hashlib

    import build_frame_cache as bfc

    params = _xparams(tmp_path)
    sha = hashlib.sha256(params.read_bytes()).hexdigest()

    def args(*docs: Path) -> Any:
        return _ns(map_params=params, map_params_sha256=sha, map_labels=list(docs), own_c1=None)

    def doc(sid: str) -> Path:
        p = _xdoc(tmp_path, sid, [1249])
        d = json.loads(p.read_text())
        p.write_text(json.dumps({**d, "params_sha256": sha}))
        return p

    mli = bfc.MapLabelInputs.from_args(args(doc(XW2)))
    assert mli.spec is ml.XMAS02 and list(mli.docs) == [XW2]
    assert mli.provenance["rule"] == "xmas02-o3h-t-all"
    for sid in XTEST:
        with pytest.raises(SystemExit, match="never cached"):
            bfc.MapLabelInputs.from_args(args(doc(XW2), doc(sid)))


def test_t2_frame_exclusions_stormy_knight_is_unchecked(monkeypatch: pytest.MonkeyPatch) -> None:
    """4h: Stormy Knight (OUT of the tier) makes its frame unchecked_species; Garm Baby and the
    Goblin are the map's (conditional) species, labelled; Santa Poring's model is scenery."""
    monkeypatch.setattr(ml, "anchor_and_depth", lambda scene, cell: ((cell[0], cell[1]), 0.0))

    def ent(gid: int, job: int) -> Any:
        return SimpleNamespace(gid=gid, objtype=5, job=job, x=50, y=50, hidden=False)

    tier = [1249, 1248, 1265, 1246]
    world = SimpleNamespace(entities=[ent(1, 1249), ent(2, 1515), ent(3, 1607)])
    assert ml.frame_exclusions(world, None, (1280, 720), ml.XMAS02.species, tier, 9) == []
    world.entities.append(ent(4, 1251))
    got = ml.frame_exclusions(world, None, (1280, 720), ml.XMAS02.species, tier, 9)
    assert got == ["unchecked_species:1251"]


def test_t2_t2_sample_conditional_species_need_30_and_one_stratum() -> None:
    pool = {1249: [_item(XW2, f, 1, 1249) for f in range(40)],
            1515: [_item(XW2, f, 2, 1515) for f in range(29)],
            1607: [_item(XW2, f, 3, 1607) for f in range(30)]}  # fmt: skip
    chosen, per, tier = ml.t2_sample(pool, ml.XMAS02, 51)
    # the four common species are always the tier (in the spec's order); D3: a conditional one
    # with >= 30 kept labels joins it (the Goblin's 30), one with 29 does not (Garm Baby)
    assert tier == [1249, 1248, 1265, 1246, 1607]
    assert per["1249"] == {"pool": 40, "sampled": 30}
    assert per["1607"] == {"pool": 30, "sampled": 30}
    assert all(c["stratum"] is None for c in chosen) and len(chosen) == 60
    want = ml.t2_order(pool[1249], 51, 1249, "xmas02")[:30]
    assert {(c["frame_id"], c["gid"]) for c in chosen if c["mob"] == 1249} == {
        (w["frame_id"], w["gid"]) for w in want}  # fmt: skip
    order = sorted(pool[1249], key=lambda it: (it["session"], it["frame_id"], it["gid"]))
    random.Random("xmas02:51:1249").shuffle(order)
    assert ml.t2_order(pool[1249], 51, 1249, "xmas02") == order


def _xsession(events: list[dict[str, Any]] | None = None) -> Any:
    lab = SimpleNamespace(timeline=SimpleNamespace(events=events or []), size=(1280, 720),
                          ui_rects=tuple((x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1
                                         in ml.session_ui_rects(XW1)))  # fmt: skip
    return ml.RecSession(Path("/x") / XW1, ml.XMAS02, None, lab, [], XW1, None)


def test_t2_the_label_stack_is_e0_with_amendments_b_and_c() -> None:
    """4a / 4i (D11): xmas02 runs gef10's stack (EngagedLabelRule / EngagedLabeler) at the FIXED
    E0: 2d (facing_unknown) applies, engaged units are excluded, the crowded flag is recorded for
    T_h's set (Amendment B); pay_fild07 keeps its plain rule."""
    sess = _xsession()
    rule = sess.facing_rule("fix2")
    assert isinstance(rule, ml.EngagedLabelRule) and rule.variant == "E0"
    params = {"offset_ms": 120.0, "fit_px": {"1249": 6}, "tau": olf.TAU, "anchors_px": {}}
    fl = ml.labeler_for(sess, params, "occl", "o3h")
    assert isinstance(fl, ml.EngagedLabeler) and fl.variant == "E0"
    assert isinstance(fl.facing, ml.EngagedLabelRule) and fl.facing.variant == "E0"
    assert ml.XMAS02.labels_engaged_rule() and ml.GEF10.labels_engaged_rule()
    assert not ml.PAYF07.labels_engaged_rule()
    pay = ml.RecSession(Path("/x/p"), ml.PAYF07, None, sess.lab, [], "p", None)
    assert type(pay.facing_rule("fix2")) is ml.EngagedRule
    assert type(ml.labeler_for(pay, params, "occl", "o3h")) is olf.FixLabeler
    for v in ("E1", "E2", "E3"):  # never another variant on xmas02
        with pytest.raises(SystemExit, match="its rule is E0"):
            ml.labeler_for(sess, {**params, "engaged_variant": v}, "occl", "o3h")


def test_t2_freeze_fixes_e0_without_a_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                ) -> None:  # fmt: skip
    prov = {"rsw_sha256": "a5104e37", "model_files_sha256": {}}
    occl = SimpleNamespace(provenance=lambda: prov, terrain=object())  # xmas_dun02: terrain on
    monkeypatch.setattr(ml, "occluders", lambda spec: occl)
    th = tmp_path / "th.json"
    th.write_text(
        json.dumps(
            {
                "o3h_tau": 0.55,
                "offset_ms": 120.0,
                "offset_source": "D12",
                "terrain": {"rule": "o3h-t", "rule_tau": 0.55},
            }
        )
    )  # 4f: adopted (2026-11-06 17:27, Amendment G)
    base = {"map": "xmas_dun02", "threshold": th, "offset": None, "proposed": False,
            "decision": "Amendment X (D12: 120 ms)"}  # fmt: skip
    out = ml.cmd_freeze(_ns(**base, engaged=None, engaged_variant=None))
    assert out["status"] == "FROZEN" and out["labels"] == "xmas02-o3h-t"
    assert out["occlusion"] == "o3h-t" and out["o3h_tau"] == 0.55
    assert out["engaged_variant"] == "E0" and out["dying_in_view"] is True
    assert out["engaged_fixed_by"] == "docs/planning/xmas02-detector.md 4i (D11)"
    assert out["map_cells"] == [260, 260] and out["anchors_px"] == {}
    assert out["fit_px"] == {str(m): 6 for m in ml.XMAS02.species}
    again = ml.cmd_freeze(_ns(**base, engaged=None, engaged_variant="E0"))
    assert again["engaged_variant"] == "E0"
    for kw in ({"engaged": th, "engaged_variant": None},
               {"engaged": None, "engaged_variant": "E2"}):  # fmt: skip
        with pytest.raises(SystemExit, match="engaged units are E0"):
            ml.cmd_freeze(_ns(**base, **kw))
    th.write_text(json.dumps({"o3h_tau": 0.55, "offset_ms": 120.0, "offset_source": "D12",
                              "terrain": {"rule": "o3h", "rule_tau": 0.55}}))  # fmt: skip
    with pytest.raises(SystemExit, match="named 'xmas02-o3h-t'"):  # a rule the name does not say
        ml.cmd_freeze(_ns(**base, engaged=None, engaged_variant=None))


# --- T-8: the pickup-notice rule on xmas_dun02 ------------------------------------------------


def test_t8_c1_rules_per_map() -> None:
    """xmas_dun02 is checked under round2 ONLY (its C1 drops a label under a notice, 4h / 5); its
    TEST is read by T1 (nothing is spent); gef_fild10 and pay_fild07 are as before."""
    x = ml.XMAS02
    ml.c1_rule_refusals(x, "round2", [f"/x/{s}" for s in (*XTEST, XW1, XW2)])
    with pytest.raises(SystemExit, match=r"round1: gef_fild10 / pay_fild07 only, not xmas_dun02"):
        ml.c1_rule_refusals(x, "round1", [f"/x/{XW5}"])
    assert ml.GEF10.c1_rules == ("round1", "round2") and ml.PAYF07.c1_rules == ("round1",)
    assert ml.GEF10.test_spent and not x.test_spent and not ml.PAYF07.test_spent
    with pytest.raises(SystemExit, match="spent"):
        ml.c1_rule_refusals(ml.GEF10, "round2", [f"/x/{A7}"])


def test_t8_the_notice_band_lies_clear_of_the_standard_chat_window() -> None:
    """The notice band (gef_fild10's, top centre) and the 2026-11-05 chat window never meet, so
    the rule and the session's UI windows exclude different labels."""
    import chat_window
    import gef10_r2_measure as r2m

    y0, y1, x0, x1 = r2m.NOTICE_BAND
    cx0, cy0, cx1, cy1 = chat_window.STANDARD.rect
    assert y1 < cy0 and (cx0, cy0, cx1, cy1) == STANDARD_CHAT


def test_t8_a_myst_case_under_a_notice_is_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule is the map's own species' too: a Myst Case box under the notice is ``notice``."""
    frame = _ground()
    _draw_notice(frame, 541, 76, 800, 106)
    ref = _round2_job(monkeypatch, {1: (520.0, 28.0, 585.0, 118.0),
                                    2: (300.0, 300.0, 360.0, 370.0)}, frame)  # fmt: skip
    olf._JOB["frame_rule"] = ml.NoticeRule()
    real = olf.standing_candidates  # the stub's units are job 1023: re-tag them as Myst Cases

    def myst(*a: Any, **k: Any) -> Any:
        world, scene, rules, cands = real(*a, **k)
        for c in cands:
            c[0].job = 1249
        return world, scene, rules, cands

    monkeypatch.setattr(olf, "standing_candidates", myst)
    rows, dropped, _ = ml._check_rows_round2(ref)
    assert [r["gid"] for r in rows] == [2] and dropped["notice:1249"] == 1
    olf._JOB.clear()


def _check_fakes(monkeypatch: pytest.MonkeyPatch, sid: str, spec: Any) -> None:
    sess = SimpleNamespace(sid=sid, spots=None, name=sid, refs=[1, 2], spec=spec,
                           dropped={}, candidates_at=lambda off: [1, 2],
                           facing_rule=lambda rule, variant=None: "rule")  # fmt: skip
    monkeypatch.setattr(ml.RecSession, "open", staticmethod(lambda p, spec, lt: sess))
    monkeypatch.setattr(ml, "frozen_occluders", lambda params, spec: _NO_TERRAIN)
    monkeypatch.setattr(olf, "run_parallel", lambda func, refs, workers: [])


def test_t8_check_runs_round2_on_xmas02_and_records_where_the_band_was_measured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = _xparams(tmp_path)
    _check_fakes(monkeypatch, XW5, ml.XMAS02)
    a = _ns(map="xmas_dun02", params=params, parts=[f"/x/{XW5}"], c1_rule="round2",
            allow_fit=False, fit_diagnostic=False, rows=None, layout_templates=None,
            workers=1)  # fmt: skip
    out = ml.cmd_check(a)
    assert out["c1_rule"]["name"] == "round2" and out["T1"] == "NO_VERDICT"
    assert out["c1_rule"]["notice_band_measured_on"] == "gef_fild10"
    assert "xmas_dun02" in out["c1_rule"]["what"]
    with pytest.raises(SystemExit, match="round1"):
        ml.cmd_check(_ns(**{**vars(a), "c1_rule": "round1"}))
    _check_fakes(monkeypatch, XW1, ml.XMAS02)  # FIT is the parameters' own data
    with pytest.raises(SystemExit, match="--allow-fit"):
        ml.cmd_check(_ns(**{**vars(a), "parts": [f"/x/{XW1}"]}))
    olf._JOB.clear()


def test_t8_gef10s_round2_record_gains_no_key(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:  # fmt: skip
    params = tmp_path / "gparams.json"
    params.write_text(json.dumps({"labels": "gef10-o3h-e", "map": "gef_fild10",
                                  "status": "FROZEN", "offset_ms": 120.0, "tau": olf.TAU,
                                  "o3h_tau": 0.636, "fit_px": {"1273": 6}}))  # fmt: skip
    _check_fakes(monkeypatch, A9, ml.GEF10)
    out = ml.cmd_check(_ns(map="gef_fild10", params=params, parts=[f"/x/{A9}"], c1_rule="round2",
                           allow_fit=False, fit_diagnostic=False, rows=None,
                           layout_templates=None, workers=1))  # fmt: skip
    assert list(out["c1_rule"]) == ["name", "what", "detector", "band_y0_y1_x0_x1",
                                    "top_rows_read", "overlap", "excluded",
                                    "excluded_by_species", "frames_with_notice",
                                    "scored_rows_near_notice_16px",
                                    "scored_rows_near_notice_bad"]  # fmt: skip
    olf._JOB.clear()


# --- T-9: the per-map evaluation flag (--eval-test on xmas_dun02) -----------------------------


def test_t9_eval_flags_are_per_map() -> None:
    x = ml.XMAS02
    for sid in XTEST:
        assert ml.eval_part_refusal(x, sid, None, "eval_test") is None
    for sid in (XW1, XW2, A9):
        assert "not a TEST part" in str(ml.eval_part_refusal(x, sid, None, "eval_test"))
    want2 = "--eval-test2 is gef_fild10's only, not xmas_dun02's"
    assert ml.eval_part_refusal(x, X2, None, "eval_test2") == want2
    want = "--eval-test is xmas_dun02's only, not gef_fild10's"
    assert ml.eval_part_refusal(ml.GEF10, A9, None, "eval_test") == want
    assert ml.eval_map_refusal(ml.PAYF07, "eval_test") is not None
    assert ml.eval_test2_refusal(ml.GEF10, A9, None) is None  # gef10's rule, unchanged
    assert x.eval_suffixes == x.test_suffixes and ml.GEF10.eval_suffixes == ml.GEF10.test2_suffixes
    with pytest.raises(SystemExit, match="one evaluation flag at a time"):
        ml.eval_flag_of(_ns(eval_test=True, eval_test2=True))
    assert ml.eval_flag_of(_ns()) is None and ml.eval_flag_of(_ns(eval_test=True)) == "eval_test"


def test_t9_labels_eval_test_refusals_before_reading(tmp_path: Path) -> None:
    for sid, match in ((XW1, "not a TEST part"), (XW2, "not a TEST part"),
                       (A9, "not a TEST part")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.cmd_labels(_xlabels_args(tmp_path, f"/nonexistent/{sid}", eval_test=True))
    with pytest.raises(SystemExit, match="xmas_dun02's only"):
        ml.cmd_labels(_labels_args(tmp_path, f"/x/{A9}", eval_test=True))  # on gef_fild10
    with pytest.raises(SystemExit, match="gef_fild10's only"):
        ml.cmd_labels(_xlabels_args(tmp_path, f"/x/{X2}", eval_test2=True))
    for status in ("PROPOSED_NOT_FROZEN: P1", None):
        with pytest.raises(SystemExit, match="--eval-test labels TEST under FROZEN parameters"):
            ml.cmd_labels(_xlabels_args(tmp_path, f"/x/{XW5}", status=status, eval_test=True))


def test_t9_labels_eval_test_labels_a_test_part(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for sid in XTEST:
        opened = _fake_session(monkeypatch, sid, ml.XMAS02)
        a = _xlabels_args(tmp_path, f"/x/{sid}", eval_test=True)
        out = ml.cmd_labels(a)
        assert opened == [f"/x/{sid}"] and out["eval_test"] is True and out["session"] == sid
        assert "eval_test2" not in out and out["classes_sha256"] == olf.sha256_file(a.classes)
        assert list(out) == LABELS_KEYS[:13] + ["eval_test", "classes", "classes_sha256"] + \
            LABELS_KEYS[13:]  # fmt: skip
    _fake_session(monkeypatch, XW2, ml.XMAS02)  # TRAIN behind a TEST name: the manifest's id
    with pytest.raises(SystemExit, match="not a TEST part"):
        ml.cmd_labels(_xlabels_args(tmp_path, f"/x/{XW5}", eval_test=True))
    olf._JOB.clear()


def test_t9_pack_eval_test_refusals(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"
    for kw, match in (({"eval_test": True, "per_species": 30, "seed": 53}, "draws 60"),
                      ({"eval_test": True, "per_species": None, "seed": 53}, "--per-species N"),
                      ({"eval_test": True, "per_species": 60, "seed": 51}, "pack seed is 53"),
                      ({"eval_test2": True, "per_species": 60, "seed": 53}, "gef_fild10's only"),
                      ({"per_species": 60, "seed": 51}, "only with --eval-test2 / --eval-test"),
                      ):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.cmd_pack(_pack_args(tmp_path, [], map="xmas_dun02", instructions=missing, **kw))
    with pytest.raises(SystemExit, match="xmas_dun02's only"):  # on gef_fild10
        ml.cmd_pack(_pack_args(tmp_path, [], eval_test=True, per_species=60, instructions=missing))
    with pytest.raises(FileNotFoundError):  # the pre-registered draw: on to the instructions
        ml.cmd_pack(_pack_args(tmp_path, [], map="xmas_dun02", eval_test=True, per_species=60,
                               seed=53, instructions=missing))  # fmt: skip


def test_t9_pack_pool_eval_test_takes_test_label_files_only(tmp_path: Path) -> None:
    good = [_xdoc(tmp_path, sid, [1249], "eval_test") for sid in XTEST]
    pool, sources, *_ = ml.pack_pool(good, ml.XMAS02, "/nas", eval_flag="eval_test")
    assert len(pool[1249]) == 3 and [s["part"] for s in sources] == list(XTEST)
    for path, match in ((_xdoc(tmp_path, XW1, [1249], "eval_test"), "not a TEST part"),
                        (_xdoc(tmp_path, XW2, [1249], "eval_test"), "not a TEST part"),
                        (_xdoc(tmp_path, X2, [1249]), "not made by labels --eval-test"),
                        (_xdoc(tmp_path, XW5, [1249], "eval_test2"),
                         "not made by labels --eval-test")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            ml.pack_pool([good[0], path], ml.XMAS02, "/nas", eval_flag="eval_test")


def test_t9_pack_eval_test_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _pack_fakes(monkeypatch)
    labels = [_xdoc(tmp_path, XW5, [1249, 1248], "eval_test", n=70),
              _xdoc(tmp_path, X2, [1265, 1515], "eval_test", n=3)]  # fmt: skip
    out = ml.cmd_pack(_pack_args(tmp_path, labels, map="xmas_dun02", eval_test=True,
                                 per_species=60, seed=53, min_fit=0.5))  # fmt: skip
    key = json.loads((tmp_path / "key" / "answer_key.json").read_text())
    assert key["eval_test"] is True and key["seed"] == 53 and key["per_species_target"] == 60
    assert "eval_test2" not in key and "candidates" not in key  # one stratum
    assert list(key) == [k for k in KEY_KEYS if k != "candidates"] + ["eval_test"]
    assert key["tier_species"] == [1249, 1248, 1265, 1515]  # every species with a kept label
    assert {k: v["sampled"] for k, v in key["per_species"].items()} == {
        "1249": 60, "1248": 60, "1265": 3, "1515": 3}  # fmt: skip
    assert out["crops"] == 126 and out["eval_test"] is True and out["per_species_target"] == 60
    assert all("stratum" not in c for c in key["crops"].values())


def test_t9_eval_test_flag_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(name: str) -> Any:
        def run(a: Any) -> Any:
            seen[name] = (a.eval_test, a.eval_test2)
            raise SystemExit(0)

        return run

    monkeypatch.setattr(ml, "cmd_labels", fake("labels"))
    monkeypatch.setattr(ml, "cmd_pack", fake("pack"))
    lab = ["labels", f"/x/{XW5}", "--map", "xmas_dun02", "--params", "p", "--out", "o",
           "--eval-test"]  # fmt: skip
    pack = ["pack", "l.json", "--map", "xmas_dun02", "--seed", "53", "--pack-dir", "pk",
            "--key-dir", "k", "--instructions", "i", "--instructions-sha256", "h", "--out", "o",
            "--eval-test", "--per-species", "60"]  # fmt: skip
    for argv, name in ((lab, "labels"), (pack, "pack")):
        with pytest.raises(SystemExit):
            ml.main(argv)
        assert seen[name] == (True, False)
