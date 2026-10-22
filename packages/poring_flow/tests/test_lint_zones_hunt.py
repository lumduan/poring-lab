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
# The melee ring (Batt 2026-10-22): the base flow hunts with it and passes (both species spawning
# on field_9 are TARGETS, no IGNORE list, the lab's server); each refusal changes ONE thing.
# (the Python view prints it in the registry's order: after engage_on_the_way, in the engage group)
EOW = 'engage_on_the_way="on_the_way@19",'
MELEE = (EOW, f'{EOW} engage_source="melee_ring",')
ONE_TARGET = ("    targets=[mob(9101), mob(9102)],\n", "    targets=[mob(9101)],\n")
WITH_IGNORE = (
    "    targets=[mob(9101), mob(9102)],\n",
    "    targets=[mob(9101)],\n    ignore=[mob(9102)],\n",
)
SHARED = ('server="lab-rathena"', 'server="community-bot-testing"')
RING = "hunt's engage_source melee_ring strikes EVERY monster in melee range"
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
        "param_option",
        lambda: flow((EOW, f'{EOW} engage_source="cursor",')),
        zones(),
        [
            f"{HUNT}: hunt's engage_source takes one of (detector, melee_ring; absent = detector), "
            "not 'cursor'"
        ],
        ok=lambda: flow((EOW, f'{EOW} engage_source="detector",')),
    ),
    Case(
        "melee_ring_server",
        lambda: flow(MELEE, SHARED),
        zones(),
        [
            f"{HUNT}: {RING}: it runs only on the lab's own server (lab-rathena), not on "
            "community-bot-testing (no kill-stealing on a shared server)"
        ],
        ok=lambda: flow(MELEE),
    ),
    Case(
        "melee_ring_ignore",
        lambda: flow(MELEE, WITH_IGNORE),
        zones(),
        [f"{HUNT}: {RING}, and field has an IGNORE list (mob 9102): refused on a map with one"],
        ok=lambda: flow(MELEE),
    ),
    Case(
        "melee_ring_species",
        lambda: flow(MELEE, ONE_TARGET),
        zones(),
        [
            f"{HUNT}: {RING}, and mob 9102 can be on field_9 without being a TARGET of field: "
            "refused on a map with a non-target species"
        ],
        ok=lambda: flow(MELEE),
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


# --- the melee ring (Batt 2026-10-22): the default, the fail-closed species data, the run start ---
def test_engage_source_absent_means_detector_and_keeps_the_flows_json() -> None:
    """Not required: a hunt written before the option is a detector hunt, with its JSON and hash."""
    from poring_flow.catalogue import catalogue
    from poring_flow.lint.hunt import engage_source, melee_ring_paths

    spec = catalogue().blocks["hunt"].spec
    base, ring = flow(), flow(MELEE)
    assert '"engage_source"' not in ir.to_json(base)
    assert melee_ring_paths(base, {"hunt": spec}) == []
    assert melee_ring_paths(ring, {"hunt": spec}) == ["field.0.body.0"]  # node ids (HUNT shown)
    hunt_of = next(
        a for s in ir.sites(base) if s.path == "field.0.body.0" for a in ir.actions_in(s.stmt)
    )
    assert engage_source(hunt_of, spec) == "detector"
    found = lint(ring, world=world(), resolver=resolve_all, zones_provider=zones())
    assert [x.message for x in found if x.severity == "error"] == []
    assert pyview.print_flow(ring) == SRC.replace(*MELEE)  # the Python view round-trips it
    assert ir.from_json(ir.to_json(ring)) == ring


def test_melee_ring_counts_what_the_targets_turn_into() -> None:
    """A TARGET that turns into a non-target (Pupa -> Creamy's shape, synthetic ids) is a
    non-target on the map: Mob.turns_into, transitively, as prep.py's training scope reads it."""
    w = world()
    mobs = {**w.mobs, 9102: Mob(id=9102, level=6, turns_into=[9103]), 9103: Mob(id=9103, level=7)}
    w2 = w.model_copy(update={"mobs": mobs})
    found = lint(flow(MELEE), world=w2, resolver=resolve_all, zones_provider=zones())
    assert [x.message for x in found if x.rule == "melee_ring_species"] == [
        f"{HUNT}: {RING}, and mob 9103 can be on field_9 without being a TARGET of field: "
        "refused on a map with a non-target species"
    ]


@pytest.mark.parametrize("missing", ["no world", "no sheet"])
def test_melee_ring_without_the_maps_species_list_is_refused(missing: str) -> None:
    """Fail closed: with no spawn list for the map nothing proves every species is a TARGET."""
    w = None if missing == "no world" else world().model_copy(update={"sheets": {}})
    found = lint(flow(MELEE), world=w, resolver=resolve_all, zones_provider=zones())
    assert [x.message for x in found if x.rule == "melee_ring_species"] == [
        f"{HUNT}: {RING}: no map sheet for field_9 is loaded, so nothing proves every species "
        "there is a TARGET (refused, fail closed)"
    ]


def test_a_detector_hunt_meets_no_melee_ring_rule() -> None:
    """The refusals are the melee ring's only: the same map, ignore list and server are fine for
    the default (the detector's own target / ignore handling is unchanged)."""
    for f in (flow(ONE_TARGET), flow(WITH_IGNORE), flow(SHARED)):
        found = lint(f, world=world(), resolver=resolve_all, zones_provider=zones())
        assert not [x for x in found if x.rule.startswith("melee_ring")]


def test_the_run_start_check_refuses_a_melee_ring_hunt_off_the_attested_lab() -> None:
    """The attested environment is known only at run time: no attested server, another server,
    or static data of another server each refuse; never allowed by default."""
    common = {"world": world(), "resolver": resolve_all, "runtime_max_s": 14_400,
              "zones_provider": zones()}  # fmt: skip
    ring = flow(MELEE)
    ok = runstart.check(ring, server="lab-rathena", **common)  # type: ignore[arg-type]
    assert ok.allowed, ok.summary()
    none = runstart.check(ring, **common)  # type: ignore[arg-type]
    assert not none.allowed and none.reasons == (
        "1 hunt with engage_source melee_ring: no attested environment (a melee-ring hunt starts "
        "only on lab-rathena)",
    )
    other = runstart.check(ring, server="community-bot-testing", **common)  # type: ignore[arg-type]
    assert other.reasons == (
        "1 hunt with engage_source melee_ring: the attested environment community-bot-testing is "
        "not the lab's (lab-rathena)",
    )
    sample = runstart.check(
        ring,
        server="lab-rathena",
        **{**common, "world": world().model_copy(update={"server": "sample"})},  # type: ignore[arg-type]
    )
    assert sample.reasons == (
        "1 hunt with engage_source melee_ring: the species were checked on sample's static data, "
        "not on lab-rathena's",
    )
    # a detector hunt needs no attested server here (unchanged)
    assert runstart.check(flow(), **common).allowed  # type: ignore[arg-type]
    with pytest.raises(runstart.RunRefused, match="no attested environment"):
        runstart.require(ring, **common)  # type: ignore[arg-type]


def test_options_are_plain_values_with_a_default_that_is_not_required() -> None:
    from pydantic import ValidationError

    from poring_flow.catalogue import ParamSpec

    ok = ParamSpec(name="engage_source", type="str", options=["detector", "melee_ring"],
                   default="detector")  # fmt: skip
    assert not ok.required and ok.default == "detector"
    with pytest.raises(ValidationError, match="plain names"):
        ParamSpec(name="x", type="str", options=["melee_ring@1"])
    with pytest.raises(ValidationError, match="not both"):
        ParamSpec(name="x", type="str", options=["a"], choices=["a@1"])
    with pytest.raises(ValidationError, match="one of its options"):
        ParamSpec(name="x", type="str", options=["a"], default="b")
    with pytest.raises(ValidationError, match="not required"):
        ParamSpec(name="x", type="str", required=True, options=["a"], default="a")
    with pytest.raises(ValidationError, match="str parameter"):
        ParamSpec(name="x", type="int", options=["a"])
