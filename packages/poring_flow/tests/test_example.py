"""Batt's example (ADR-0020 13.6.8) as a synthetic fixture: its effective event sets equal 13.6.8's
table, and it lints with EXACTLY the expected findings (13.8, MW1's acceptance)."""

from __future__ import annotations

import sys
from pathlib import Path

from poring_flow import ir
from poring_flow.effective import merge
from poring_flow.lint import lint

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import farm_flow, farm_world, resolve_all  # noqa: E402

# 13.6.8's table: (key, class) -> state per block. "global" = inherited.
TABLE = {
    ("dead", "critical"): ("global", "global", "global"),
    ("hp_critical", "critical"): ("global", "global", "global"),
    ("unexpected_map", "critical"): ("global", "extended", "global"),
    ("unintended_engagement", "survival"): ("global", "global", "overridden"),
    ("hp_low", "survival"): ("disabled", "global", "overridden"),
    ("weight", "upkeep"): ("disabled", "global", "global"),
    ("boss_seen", "survival"): (None, None, "added"),
}
STATE = {
    "inherited": "global",
    "extended": "extended",
    "overridden": "overridden",
    "disabled": "disabled",
    "added": "added",
}


def test_the_effective_sets_equal_the_13_6_8_table() -> None:
    flow = farm_flow()
    assert flow.workflow is not None
    for col, block in enumerate(flow.workflow.blocks):
        merged = merge(flow, block)
        assert merged.issues == []
        got = {(e.key, e.handler.priority): STATE[e.state] for e in merged.events}
        want = {k: v[col] for k, v in TABLE.items() if v[col] is not None}
        assert got == want, block.name


def test_the_merged_details_follow_the_table() -> None:
    flow = farm_flow()
    assert flow.workflow is not None
    town, relay, farm = flow.workflow.blocks
    # town disables the combat events and no others
    assert [e.key for e in merge(flow, town).active()] == [
        "dead",
        "hp_critical",
        "unexpected_map",
        "unintended_engagement",
    ]
    # relay: unexpected_map EXTENDED, its map steps run AFTER the global body (safety-critical)
    um = merge(flow, relay).by_key("unexpected_map")
    assert um is not None and um.extension_after and um.extension_label == "relay_recover"
    assert [s.block for s in um.extension if isinstance(s, ir.ActionStmt)] == ["close_dialog"]
    # farm: hp_low OVERRIDDEN to < 70 until > 90; the engagement by species; boss_seen ADDED
    m = merge(flow, farm)
    hp = m.by_key("hp_low")
    assert hp is not None and hp.label == "farm_hp_low" and hp.handler.mode == "insert"
    assert hp.handler.when == ir.Cmp(
        op="<", left=ir.Sense(sensor="hp_percent"), right=ir.Lit(value=70)
    )
    eng = m.by_key("unintended_engagement")
    assert eng is not None and eng.label == "farm_engagement" and eng.handler.then == "relocate"
    boss = m.by_key("boss_seen")
    assert boss is not None and boss.source == "map" and boss.handler.then == "relocate"
    # order: class first; inside critical dead > hp_critical > unexpected_map (13.6.3); then the
    # RANK inside the class (IR 2, Batt 2026-10-09, #13): unintended_engagement (4) before hp_low
    # (5), boss_seen last (a user event: 50), although hp_low is declared first
    assert [e.key for e in m.active()] == [
        "dead",
        "hp_critical",
        "unexpected_map",
        "unintended_engagement",
        "hp_low",
        "boss_seen",
        "weight",
    ]
    assert [ir.rank_of(e.handler) for e in m.active()] == [1, 2, 3, 4, 5, 50, 6]
    # dead keeps 1 per run everywhere
    assert all(merge(flow, b).by_key("dead").max_per_run == 1 for b in (town, relay, farm))  # type: ignore[union-attr]


# Every finding the example carries, each explained. The example "already carries the fixes"
# (13.1) for the faults 13.5 / 13.6.9 illustrate; these are the ones it still has.
EXPECTED = sorted(
    [
        # 13.5 NPC rule, L1 preconditions: storage needs Basic Skill 6; nothing assumes it
        (
            "warning",
            "town.2: kafra_store needs skill_level(skill(1)) >= 6 (storage.deposit: Basic "
            "Skill level 6): add it to the flow's assumes",
        ),
        # 13.5 species lists: map_3 spawns two species on neither list; the boss is aggressive
        ("info", "farm: mob 9104 spawns on map_3 and is on neither list: treated as IGNORE"),
        ("info", "farm: mob 9109 spawns on map_3 and is on neither list: treated as IGNORE"),
        (
            "warning",
            "farm: mob 9109 is aggressive and ignored: it attacks, the bot never answers, the "
            "HP events decide",
        ),
        # 13.5 save point: a death before town.1 sets it respawns at an unknown save point (WARNING)
        (
            "warning",
            "dead: a death at town.0 respawns at the save point, which nothing sets before it: "
            "set it first, or assert it",
        ),
        # 13.5 weight: nothing in farm picks items up, so the weight exit cannot fire (Q21's case)
        (
            "warning",
            "farm.0: weight_percent() < 50 can change only by picking up items, and nothing in "
            "farm picks any up",
        ),
        (
            "info",
            "farm.0: weight_percent() < 50: at 50 % and above, natural HP and SP regeneration "
            "has already stopped",
        ),
        # 13.5 keep lists: store-all keeps the Butterfly Wings and potions, not the escape's Fly
        # Wings
        (
            "warning",
            "town.2: storing everything also stores the Fly Wings that hp_critical's escape "
            "uses: add them to the keep list",
        ),
        # 13.6.9 ties: these four were WARNINGs ("on different sensors: they queue") until
        # Batt 2026-10-09 (contradictions #13 + #14): each pair has two different ranks, so its
        # order is decided, and an INFO says which runs first
        (
            "info",
            "global: unintended_engagement and hp_low are both survival: unintended_engagement "
            "runs first when both are due (rank 4 before 5)",
        ),
        (
            "info",
            "farm: unintended_engagement and hp_low are both survival: unintended_engagement "
            "runs first when both are due (rank 4 before 5)",
        ),
        (
            "info",
            "farm: hp_low and boss_seen are both survival: hp_low runs first when both are due "
            "(rank 5 before 50)",
        ),
        (
            "info",
            "farm: unintended_engagement and boss_seen are both survival: unintended_engagement "
            "runs first when both are due (rank 4 before 50)",
        ),
        # 13.9 / 13.6.9: a species policy while today's detector cannot name species
        (
            "warning",
            "farm: farm_engagement decides by species, and the detector cannot name species "
            "yet: the run applies its most cautious branch",
        ),
    ]
)


def test_batts_example_lints_with_exactly_the_expected_findings() -> None:
    got = sorted(
        (f.severity, f.message) for f in lint(farm_flow(), world=farm_world(), resolver=resolve_all)
    )
    assert got == EXPECTED
    assert not [f for f in EXPECTED if f[0] == "error"]  # approvable: no errors
    # #14: the four ties WARNINGs of this example are gone (each pair is ordered by rank)
    ties = [(sev, m) for sev, m in got if "are both survival" in m]
    assert len(ties) == 4 and {sev for sev, _ in ties} == {"info"}


def test_the_example_is_unsupported_today_on_the_real_bindings(tmp_path: Path) -> None:
    """With the real L1/L2 files and no generated L3 data, the bindings fail closed."""
    from poring_flow.lint import default_resolver

    flow = farm_flow()
    msgs = [
        f.message
        for f in lint(flow, world=farm_world(), resolver=default_resolver(flow.target, tmp_path))
        if f.rule == "bindings"
    ]
    assert (
        "town.0: walk_to is unsupported here: L3 binding L3.map.walkability (no L3 bindings for "
        "lab-rathena)" in msgs
    )
    assert any(m.startswith("farm.0.body.0: attack_nearest is unsupported here") for m in msgs)
