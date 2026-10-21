"""The hunt block and the map node's zones in the linter (ADR-0020 Amendment A, DRAFT;
blocks-from-hunt-flow.md B1, 2026-10-21): ONE PASSING AND ONE FAILING FIXTURE PER NEW RULE, each
failing one with its exact message, and the coverage test that names a new rule without fixtures.

The base flow (fixtures/hunt_field.flow) hunts on a SYNTHETIC field map behind its zones and walks
out to a synthetic town. Every map, cell, id and sha256 here is made up; the zones provider is a
synthetic stand-in for scripts/flow_zones.py (its own test runs the real loader).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from poring_flow import ir, pyview, runstart
from poring_flow.lint import Finding, lint
from poring_flow.sheet import Mob, Spawn, Warp, World
from poring_flow.zones import ZoneInfo, ZonesProvider, ZonesUnreadable

sys.path.insert(0, str(Path(__file__).parent))
from flow_synthetic import FIXTURES, ITEMS, resolve_all, sheet  # noqa: E402

SRC = (FIXTURES / "hunt_field.flow").read_text()
SHA = "5a" * 32
OTHER_SHA = "c3" * 32
WALL = frozenset((100, y) for y in range(0, 50))  # a short wall: the exit stays reachable
CUT = frozenset((100, y) for y in range(0, 200))  # a wall across the whole map: the exit is cut off
SPAWN_9101 = frozenset((x, y) for x in range(60, 63) for y in range(60, 63))
HUNT = "maps.field.0.body.0"


def world() -> World:
    return World(
        server="lab-rathena",
        sheets={
            "field_9": sheet(
                "field_9",
                spawns=[
                    Spawn(mob=9101, count=20, area=(60, 60, 62, 62)),
                    Spawn(mob=9102, count=10),
                ],
                warps=[Warp(x=150, y=150, to_map="town_9", to_x=10, to_y=10)],
            ),
            "town_9": sheet("town_9", town=True),
        },
        mobs={9101: Mob(id=9101, level=5), 9102: Mob(id=9102, level=6)},
        items=ITEMS,
    )


def zones(
    closed: frozenset[tuple[int, int]] = WALL,
    no_enter: frozenset[tuple[int, int]] = frozenset(),
    sha: str = SHA,
    files: tuple[str, ...] = ("field_9",),
    broken: bool = False,
) -> ZonesProvider:
    def get(map_id: str) -> ZoneInfo | None:
        if map_id not in files:
            return None
        if broken:
            raise ZonesUnreadable("config/map_zones/field_9.yaml: unknown key(s) ['no_crosss']")
        return ZoneInfo(map=map_id, sha256=sha, closed=closed | no_enter, no_enter=no_enter)

    return get


def flow(*subs: tuple[str, str]) -> ir.Flow:
    src = SRC
    for old, new in subs:
        assert old in src, old
        src = src.replace(old, new, 1)
    return pyview.parse(src)


@dataclass
class Case:
    rule: str
    source: Callable[[], ir.Flow]
    provider: ZonesProvider | None
    expected: list[str]  # [] = the passing fixture
    ok: Callable[[], ir.Flow] = field(default=lambda: flow())  # the passing twin
    ok_provider: ZonesProvider | None = field(default_factory=zones)


NO_TARGETS = ("    targets=[mob(9101), mob(9102)],\n", "")
CASES = [
    Case(
        "rule_version",
        lambda: flow(('loot="gm_scan_one_pass@51"', 'loot="gm_scan@49"')),
        zones(),
        [
            f"{HUNT}: hunt's loot takes a rule version (gm_fast_scan@54, gm_scan_one_pass@51, "
            "gm_scan@50), not 'gm_scan@49'"
        ],
        ok=lambda: flow(('loot="gm_scan_one_pass@51"', 'loot="gm_scan@50"')),
    ),
    Case(
        "needs_targets",
        lambda: flow(NO_TARGETS),
        zones(),
        [f"{HUNT}: hunt attacks only the TARGET species, and field lists none (13.3)"],
    ),
    Case(
        "zones_map",
        lambda: flow(('zones=zones("field_9"', 'zones=zones("town_9"')),
        zones(),
        ["maps.field: its zones name map town_9; the block is on field_9"],
    ),
    Case(
        "zones_unreadable",
        flow,
        zones(broken=True),
        [
            "maps.field: the zones file of field_9 is refused by its loader: "
            "config/map_zones/field_9.yaml: unknown key(s) ['no_crosss']"
        ],
    ),
    Case(
        "zones_missing",
        flow,
        zones(files=()),
        ["maps.field: it names zones 5a5a5a5a5a5a, and field_9 has no zones file"],
    ),
    Case(
        "zones_changed",
        flow,
        zones(sha=OTHER_SHA),
        [
            "maps.field: it names zones 5a5a5a5a5a5a; the file is now c3c3c3c3c3c3: a person "
            "reviews the change and the flow is approved again"
        ],
    ),
    Case(
        "zones_unreferenced",
        lambda: flow(('    zones=zones("field_9", sha256="' + SHA + '"),\n', "")),
        zones(),
        [
            "maps.field: field_9 has a zones file (5a5a5a5a5a5a): the map node must name it "
            "(zones=zones(...))"
        ],
        # the passing twin: no reference and no file
        ok=lambda: flow(('    zones=zones("field_9", sha256="' + SHA + '"),\n', "")),
        ok_provider=zones(files=()),
    ),
    Case(
        "zones_entry",
        flow,
        zones(no_enter=frozenset({(20, 20), (21, 20)})),
        ["maps.field: entry south at (20, 20) is inside a no-enter area of its zones"],
    ),
    Case(
        "zones_exit",
        flow,
        zones(closed=CUT),
        [
            "maps.field.1: the walk exit at (150, 150) lies behind the zones: no entry reaches it "
            "once they close their cells"
        ],
    ),
    Case(
        "zones_exit",
        flow,
        zones(closed=WALL | {(150, 150)}),
        ["maps.field.1: the walk exit at (150, 150) is closed by the zones"],
    ),
    Case(
        "zones_targets",
        flow,
        zones(closed=WALL | SPAWN_9101),
        [
            "maps.field: every spawn cell of target mob 9101 on field_9 is closed by the zones: "
            "the block never reaches it"
        ],
    ),
]


def messages(f: ir.Flow, provider: ZonesProvider | None, rule: str) -> list[str]:
    found: list[Finding] = lint(f, world=world(), resolver=resolve_all, zones_provider=provider)
    return sorted(x.message for x in found if x.rule == rule)


@pytest.mark.parametrize("case", CASES, ids=[f"{c.rule}-{i}" for i, c in enumerate(CASES)])
def test_each_new_rule_fails_its_fixture_with_the_exact_message(case: Case) -> None:
    assert messages(case.source(), case.provider, case.rule) == sorted(case.expected)


@pytest.mark.parametrize("case", CASES, ids=[f"{c.rule}-{i}" for i, c in enumerate(CASES)])
def test_each_new_rule_passes_its_twin(case: Case) -> None:
    assert messages(case.ok(), case.ok_provider, case.rule) == []


def test_every_new_rule_has_a_fixture() -> None:
    from poring_flow.lint import hunt, zones

    rules: set[str] = set()
    for mod in (hunt, zones):
        text = Path(mod.__file__).read_text()  # type: ignore[arg-type]
        rules |= set(re.findall(r'"([a-z_]+)",\s*"(?:error|warning|info|readiness)"', text))
    assert rules == {c.rule for c in CASES}


def test_the_base_flow_is_clean_of_errors_and_round_trips() -> None:
    f = flow()
    found = lint(f, world=world(), resolver=resolve_all, zones_provider=zones())
    assert [x.message for x in found if x.severity == "error"] == []
    assert pyview.print_flow(f) == SRC
    assert ir.from_json(ir.to_json(f)) == f
    assert f.workflow is not None and f.workflow.blocks[0].zones == ir.ZonesRef(
        map="field_9", sha256=SHA
    )


def test_a_hunt_outside_a_map_block_needs_one() -> None:
    head = (
        'flow(ir=2, name="t", max_runtime_s=600, target=target(client="kro-20211103-prere", '
        'server="lab-rathena", locale="en", path=RDP))\n'
    )
    call = (
        'hunt(strike="arm_c@32", engage_on_the_way="on_the_way@19", dead="exp_line@48", '
        'loot="gm_scan@50", search="heading_coverage@22")\n'
    )
    got = messages(pyview.parse(head + call), None, "needs_targets")
    assert got == [
        "main.0: hunt attacks the map block's TARGET species (13.3): it runs in a map block"
    ]


def test_a_flow_without_zones_keeps_its_json_and_hash() -> None:
    """No IR bump: an absent reference is left out of the canonical JSON (ir.MapBlock)."""
    f = flow(('    zones=zones("field_9", sha256="' + SHA + '"),\n', ""))
    assert '"zones"' not in ir.to_json(f)
    assert '"zones":{"map":"field_9"' in ir.to_json(flow())
    assert ir.flow_hash(f) != ir.flow_hash(flow())


def test_the_run_start_check_refuses_named_zones_without_a_provider() -> None:
    f = flow()
    common = {"world": world(), "resolver": resolve_all, "runtime_max_s": 14_400}
    none = runstart.check(f, **common)  # type: ignore[arg-type]
    assert not none.allowed
    assert none.reasons == ("no zones data: the map nodes' zones references are unchecked",)
    ok = runstart.check(f, zones_provider=zones(), **common)  # type: ignore[arg-type]
    assert ok.allowed, ok.summary()
    changed = runstart.check(f, zones_provider=zones(sha=OTHER_SHA), **common)  # type: ignore[arg-type]
    assert not changed.allowed and len(changed.errors) == 1


def test_choices_are_rule_versions_of_a_str_parameter() -> None:
    from pydantic import ValidationError

    from poring_flow.catalogue import ParamSpec

    with pytest.raises(ValidationError, match="name@N"):
        ParamSpec(name="loot", type="str", choices=["gm_scan"])
    with pytest.raises(ValidationError, match="str parameter"):
        ParamSpec(name="loot", type="int", choices=["gm_scan@50"])
    with pytest.raises(ValidationError, match="distinct"):
        ParamSpec(name="loot", type="str", choices=["gm_scan@50", "gm_scan@50"])
