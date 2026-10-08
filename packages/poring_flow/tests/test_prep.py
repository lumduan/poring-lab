"""The preparation report and the AI-prep estimate (ADR-0020 13.3, 13.4; training-cost.md)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from poring_flow import ir, prep, pyview
from poring_flow.lint import Detector

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import byalan_world, farm_flow, farm_world, resolve_all  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "docs" / "planning" / "training-cost.md"

# Two map blocks on the Byalan maps that TARGET only two of the seven species (13.3's example).
BYALAN = """\
flow(
    ir=1,
    name="byalan_loop",
    max_runtime_s=7200,
    run_until_stopped=True,
    start=entry("upper", "in"),
    target=target(client="kro-20211103-prere", server="lab-rathena", locale="en", path=S2),
)


@map_block(map_id("iz_dun00"), entries=[entry_at("in", cell("iz_dun00", 100, 100))],
           targets=[mob(9201), mob(9202)])
def upper():
    attack_nearest(within=10)
    take_exit(walk_exit(cell("iz_dun00", 150, 150), to=entry("lower", "in")))


@map_block(map_id("iz_dun01"), entries=[entry_at("in", cell("iz_dun01", 100, 100))],
           targets=[mob(9201), mob(9202)])
def lower():
    attack_nearest(within=10)
    stop("done")
"""


def test_the_byalan_training_scope_is_all_7_species_not_the_2_targets() -> None:
    flow = pyview.parse(BYALAN)
    scope = prep.training_scope(flow, byalan_world())
    assert scope.species == (9201, 9202, 9203, 9204, 9205, 9206, 9207)
    assert scope.targets == (9201, 9202)
    assert len(scope.unlisted) == 5
    assert scope.fixed_classes == ("npc", "portal", "dying", "player")


def test_the_scope_adds_metamorphosis_and_species_named_by_events() -> None:
    w = farm_world()
    mobs = dict(w.mobs)
    mobs[9101] = mobs[9101].model_copy(update={"turns_into": [9150]})
    w = w.model_copy(update={"mobs": mobs})
    scope = prep.training_scope(farm_flow(), w)
    assert 9150 in scope.species  # what a spawned species turns into
    assert scope.named_by_events == (9109,)  # boss_seen's sees(BOSS)
    assert len(scope.species) == 8


def test_the_estimator_equals_a_hand_computation() -> None:
    """Byalan: 6 normal species + 1 static (d = 0.5), two new maps (training-cost.md section 5)."""
    c = prep.constants()
    species = {m: "normal" for m in (9201, 9202, 9203, 9204, 9205, 9206)} | {9207: "static"}
    e = prep.estimate(species, ["iz_dun00", "iz_dun01"])
    sum_d = 6 * 1.0 + 0.5
    train_per_species = 1500 * 30 * 0.146 / 3600  # B x E x k = 1.825 compute-h
    assert e.sum_d == sum_d == 6.5
    assert e.collect_s2_h == pytest.approx(6.5 * 1.0 * 1.3)  # 8.45 h of S2
    assert e.train_compute_h == pytest.approx(6.5 * train_per_species * 1.3)  # 15.42 compute-h
    assert e.map_prep_h == pytest.approx(2 * 4.0 * 1.3)  # 10.4 h: per NEW map (see the report)
    assert e.wall_h["night"] == pytest.approx(15.42125 / 0.63)  # ~24.5 h
    assert e.wall_h["day_effective"] == pytest.approx(15.42125 / 0.35)  # ~44.1 h
    assert e.wall_h["mix"] == pytest.approx(15.42125 / ((9 * 0.63 + 15 * 0.43) / 24))  # ~30.5 h
    assert (e.status, e.version) == (c.status, c.version) == ("ESTIMATE", 1)
    # training-cost.md section 5 rounds these to 8.5 h, 15.5 compute-h, 25 h night, 31 h mixed,
    # 44 h effective day: the same numbers within its rounding
    assert abs(e.collect_s2_h - 8.5) < 0.1 and abs(e.train_compute_h - 15.5) < 0.1
    assert abs(e.wall_h["night"] - 25) < 1 and abs(e.wall_h["mix"] - 31) < 1
    assert abs(e.wall_h["day_effective"] - 44) < 0.5


def test_a_measured_species_or_a_prepared_map_adds_nothing() -> None:
    flow = pyview.parse(BYALAN)
    all_new = prep.report(flow, byalan_world(), resolver=resolve_all)
    some = prep.report(
        flow,
        byalan_world(),
        resolver=resolve_all,
        detector=Detector(measured=frozenset({9201, 9202}), prepared_maps=frozenset({"iz_dun00"})),
    )
    assert all_new.estimate is not None and some.estimate is not None
    assert all_new.estimate.sum_d == 6.5 and some.estimate.sum_d == 4.5
    assert some.estimate.new_maps == ("iz_dun01",)


def test_the_report_lists_what_is_open_and_run_stays_disabled() -> None:
    rep = prep.report(farm_flow(), farm_world(), resolver=resolve_all)
    assert not rep.runnable()
    assert rep.summary() == "not runnable: 7 species untrained, 12 blocks unverified"
    assert rep.escape == {"town": "Fly Wing", "relay": "Fly Wing", "farm": "Fly Wing"}
    text = "\n".join(rep.lines())
    assert "Species to recognise: 7 (targets 3, ignore 2, unlisted 2) · new: 7" in text
    assert "constants ESTIMATE v1" in text and "[Run] disabled" in text


def test_the_constants_come_from_one_source_the_doc_points_to() -> None:
    """Q26: training-cost.md is the instrument; the data file is its machine-readable copy.
    The doc points to the file, and the doc's section 3 / 4 tables equal it (drift guard)."""
    c = prep.constants()
    doc = DOC.read_text()
    assert "packages/poring_flow/src/poring_flow/training_cost.json" in doc
    section = doc.split("## 3.")[1].split("## 5.")[0]

    def row(name: str) -> str:
        line = next(ln for ln in section.splitlines() if ln.startswith(f"| **{name}"))
        return line

    assert f"**{c.k_s_per_frame_epoch} s**" in row("k**")
    assert f"| {c.epochs} |" in row("E**")
    assert f"**≈ {c.collect_h_per_species:.1f} h**" in row("collect per species")
    assert f"**≈ {c.map_prep_h:g} h**" in row("map prep")
    assert f"| {c.contingency} |" in row("contingency")
    avail = row("availability")
    a = c.availability
    assert f"night {a['night']}, day {a['day']}" in avail
    assert f"night {a['night_effective']}, day {a['day_effective']}" in avail
    assert f"B = {c.budget_frames_per_species:,} training frames" in doc
    d = c.difficulty
    for cls, label in (
        ("similar", "similar to a known species"),
        ("static", "static"),
        ("normal", "normal"),
        ("boss_multi_form", "large multi-form boss"),
    ):
        assert re.search(rf"\| {label} \| {d[cls]} \|", section), cls
    assert f"**≈ {c.train_h_per_species:.1f} compute-h**" in row("train per species")


def test_the_package_data_files_are_never_gitignored() -> None:
    """The repo ignores every directory named data/ (rule 4): a package file there would pass
    locally and be missing from every commit (it happened once, on this package)."""
    import shutil
    import subprocess

    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("no git checkout")
    pkg = ROOT / "packages" / "poring_flow"
    for rel in (
        "src/poring_flow/training_cost.json",
        "src/poring_flow/blocks.yaml",
        "schema/flow.schema.json",
    ):
        res = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", str(pkg / rel)], check=False
        )
        assert res.returncode == 1, f"{rel} is gitignored"


def test_the_report_needs_no_gpl_data_in_the_repo() -> None:
    """Committed flows are data-free or synthetic (7.1): no real NPC / option key in fixtures."""
    for path in (Path(__file__).parent / "fixtures").glob("*.flow"):
        flow = pyview.parse(path.read_text())
        for r in [v for _, v in _refs(flow)]:
            if isinstance(r, ir.NpcRef | ir.OptionRef):
                assert re.fullmatch(r"[no]_[0-9a-z]{2,8}", r.key), (path.name, r.key)
            if isinstance(r, ir.MobRef | ir.ItemRef):
                assert 9000 <= r.id < 10000, (path.name, r.id)


def _refs(flow: ir.Flow) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for lit in flow.variables.values():
        vals = lit.value if isinstance(lit.value, list) else [lit.value]
        out += [("var", v) for v in vals]
    for site in ir.sites(flow):
        for _, e in ir.stmt_exprs(site.stmt):
            for x in ir.sub_exprs(e):
                if isinstance(x, ir.Lit):
                    vals = x.value if isinstance(x.value, list) else [x.value]
                    out += [(site.path, v) for v in vals]
        if isinstance(site.stmt, ir.TakeExit):
            out += [(site.path, o) for o in (site.stmt.exit.npc, *site.stmt.exit.options)]
    for b in flow.workflow.blocks if flow.workflow else []:
        out += [(b.name, m) for m in (*b.targets, *b.ignore)]
    return out
