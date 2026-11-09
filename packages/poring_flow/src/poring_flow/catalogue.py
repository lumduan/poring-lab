"""The block catalogue: the registry (blocks.yaml) joined with the L1 concepts (ADR-0020 section 2).

- One action block per L1 concept (a few concepts have more than one block, e.g. `walk_away` is a
  `nav.walk_to`), plus the sensors (2.3) and the L1 concepts excluded with a reason.
- Each entry carries its L1 status. A block or sensor whose concept is not in L1 is UNKNOWN; a core
  block (no input) is CORE. Open question 1's proposal: a run needs every action block's concept
  `verified` for the active environment, so the catalogue marks what is not.
- `document()` is the one JSON document served to the editor and given to the LLM drafter.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env
from pydantic import BaseModel, ConfigDict, Field, model_validator

from poring_skills.schema import CONCEPT_ID, Concept, load_l1

_CFG = ConfigDict(extra="forbid", frozen=True)
ParamType = Literal[
    "cell",
    "map",
    "npc",
    "option",
    "item",
    "items",
    "mob",
    "skill",
    "window",
    "int",
    "float",
    "bool",
    "str",
    "value",
]
Status = Literal["verified", "unverified", "unknown", "core"]

# Python-view names that are not blocks or sensors (7.2's helpers and constants).
REF_CONSTRUCTORS = ("cell", "npc", "option", "item", "mob", "skill", "map_id", "window")
HELPERS = (
    "flow",
    "target",
    "entry",
    "entry_at",
    "entry_anywhere",
    "map_block",
    "on",
    "extend",
    "disable",
    "take_exit",
    "walk_exit",
    "npc_warp",
    "item_warp",
    "wait_until",
    "wait",  # wait(seconds): the "wait N seconds" block (2026-11-09)
    "stop",
    "bounded",
    "known",
    "range",
    "zones",  # map_block(..., zones=zones(map, sha256=...)): the map node's zones (Amendment A 4)
)
CONSTANTS = {
    "OK": "ok",
    "FAILED": "failed",
    "UNSUPPORTED": "unsupported",
    "INTERRUPTED": "interrupted",
    "REFUSED": "refused",
    "CRITICAL": "critical",
    "SURVIVAL": "survival",
    "UPKEEP": "upkeep",
    "RESUME": "resume",
    "SKIP_BLOCK": "skip_block",
    "RESTART_FLOW": "restart_flow",
    "RELOCATE": "relocate",
    "STOP": "stop",
    "CONTINUE": "continue",
    "INSERT": "insert",
    "PREEMPT": "preempt",
    "S2": "s2",
    "RDP": "rdp",
}
RESERVED = ("main",)  # the plain flow's node path root


RULE_VERSION = r"^[a-z][a-z0-9_]*@[0-9]{1,4}$"  # name@N: PARAMS[N]'s numbers (hunt_config.py)
OPTION = r"^[a-z][a-z0-9_]*$"  # a plain OPTION value: no @N, no numbers travel with it


class ParamSpec(BaseModel):
    model_config = _CFG
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: ParamType
    required: bool = False
    positional: bool = False
    # Amendment A 1 (2026-10-21, B1): a parameter that picks a RULE VERSION lists the versions a
    # person may pick (their numbers travel with them, read-only); `group` is its group in the
    # editor (Batt D2: one hunt block with groups). The linter refuses any other value.
    group: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    choices: list[str] = []
    # An OPTION parameter (Batt 2026-10-22, the hunt block's `engage_source`): a plain value that
    # picks an engine behaviour which is NOT a hunt_flow PARAMS rule, so it has no version and no
    # numbers (hunt_config.py never exports it). `default` is what an ABSENT parameter means: an
    # option with a default is never required, so a flow written before it keeps its JSON and
    # its hash. The linter refuses any value not in `options` (lint/hunt.py `param_option`).
    options: list[str] = []
    default: str | None = None
    note: str | None = None  # the editor's text beside an option parameter (what each value does)

    @model_validator(mode="after")
    def _choices(self) -> ParamSpec:
        import re

        if self.choices and self.type != "str":
            raise ValueError(f"{self.name}: choices are rule versions, a str parameter's")
        bad = [c for c in self.choices if not re.match(RULE_VERSION, c)]
        if bad or len(set(self.choices)) != len(self.choices):
            raise ValueError(f"{self.name}: choices are distinct name@N rule versions: {bad}")
        if self.options:
            if self.choices:
                raise ValueError(f"{self.name}: rule versions (choices) or options, not both")
            if self.type != "str":
                raise ValueError(f"{self.name}: options are plain values, a str parameter's")
            bad = [o for o in self.options if not re.match(OPTION, o)]
            if bad or len(set(self.options)) != len(self.options):
                raise ValueError(f"{self.name}: options are distinct plain names: {bad}")
        if self.default is not None:
            if self.default not in self.options:
                raise ValueError(f"{self.name}: the default is one of its options")
            if self.required:
                raise ValueError(f"{self.name}: an option with a default is not required")
        return self


class AssumeSpec(BaseModel):
    model_config = _CFG
    sensor: str
    skill: int | None = None
    op: Literal[">=", ">"]
    value: int
    why: str


class BlockSpec(BaseModel):
    model_config = _CFG
    concept: str = Field(pattern=CONCEPT_ID)
    kind: Literal["action", "core"] = "action"
    params: list[ParamSpec] = []
    timeout_s: float = Field(gt=0, le=600)
    profile: Literal["anywhere", "atomic"] = "anywhere"
    long: bool = False
    moves: Literal["none", "to_cell", "near"] = "none"
    changes_map: Literal["never", "always", "by_item", "escape"] = "never"
    adds_weight: bool = False
    insertable: bool = False
    irreversible: str | None = None
    kafra: Literal["save", "storage", "teleport", "cart"] | None = None
    assume: list[AssumeSpec] = []
    affects: dict[str, Literal["+", "-", "~"]] = {}
    types: bool = False
    # it attacks the map block's TARGET species only (13.3): it runs in a map block with targets
    needs_targets: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _positional_first(self) -> BlockSpec:
        seen_kw = False
        for p in self.params:
            if p.positional and seen_kw:
                raise ValueError("positional parameters come first")
            seen_kw = seen_kw or not p.positional
        return self


class SensorSpec(BaseModel):
    model_config = _CFG
    concept: str | None = Field(default=None, pattern=CONCEPT_ID)
    type: Literal["percent", "int", "bool", "mob", "map", "cell"]
    passive: bool
    drift: bool = False
    cue: bool = False
    params: list[ParamSpec] = []
    range: tuple[float, float] | None = None
    resolution: float | None = None
    danger: Literal["low", "high"] | None = None
    note: str | None = None


class Registry(BaseModel):
    model_config = _CFG
    version: int
    blocks: dict[str, BlockSpec]
    sensors: dict[str, SensorSpec]
    excluded: dict[str, str]


class CatalogueBlock(BaseModel):
    model_config = _CFG
    name: str
    spec: BlockSpec
    status: Status
    purpose: str | None = None  # from L1
    preconditions: list[str] = []  # from L1
    runtime_outcome: str | None = None  # L1's runtime (screen) check
    bindings_needed: list[str] = []  # from L1


class CatalogueSensor(BaseModel):
    model_config = _CFG
    name: str
    spec: SensorSpec
    status: Status


class Catalogue(BaseModel):
    model_config = _CFG
    version: int
    blocks: dict[str, CatalogueBlock]
    sensors: dict[str, CatalogueSensor]
    excluded: dict[str, str]
    constants: dict[str, str]
    helpers: list[str]

    def names(self) -> set[str]:
        """Every catalogue name a flow may not reuse (no shadowing, 7.2)."""
        return (
            set(self.blocks)
            | set(self.sensors)
            | set(REF_CONSTRUCTORS)
            | set(HELPERS)
            | set(self.constants)
            | set(RESERVED)
        )

    def concept(self, block: str) -> str | None:
        b = self.blocks.get(block)
        return b.spec.concept if b else None


@cache
def registry() -> Registry:
    text = (resources.files("poring_flow") / "blocks.yaml").read_text(encoding="utf-8")
    return Registry.model_validate(yaml.safe_load(text))


def _status(concept: str | None, l1: dict[str, Concept], core: bool = False) -> Status:
    if core:
        return "core"
    if concept is None or concept not in l1:
        return "unknown"
    return "verified" if l1[concept].status == "verified" else "unverified"


def build(l1: dict[str, Concept] | None = None, reg: Registry | None = None) -> Catalogue:
    l1 = load_l1() if l1 is None else l1
    reg = registry() if reg is None else reg
    blocks: dict[str, CatalogueBlock] = {}
    for name, spec in reg.blocks.items():
        c = l1.get(spec.concept)
        blocks[name] = CatalogueBlock(
            name=name,
            spec=spec,
            status=_status(spec.concept, l1, spec.kind == "core"),
            purpose=c.purpose if c else None,
            preconditions=list(c.preconditions) if c else [],
            runtime_outcome=c.outcome.runtime.signal if c else None,
            bindings_needed=list(c.bindings_needed) if c else [],
        )
    sensors = {
        name: CatalogueSensor(name=name, spec=spec, status=_status(spec.concept, l1))
        for name, spec in reg.sensors.items()
    }
    return Catalogue(
        version=reg.version,
        blocks=blocks,
        sensors=sensors,
        excluded=dict(reg.excluded),
        constants=dict(CONSTANTS),
        helpers=list(HELPERS) + list(REF_CONSTRUCTORS),
    )


@cache
def catalogue() -> Catalogue:
    return build()


def coverage(cat: Catalogue | None = None, l1: dict[str, Concept] | None = None) -> list[str]:
    """L1 concepts that are neither a block's, a sensor's nor excluded (empty = covered)."""
    cat = catalogue() if cat is None else cat
    l1 = load_l1() if l1 is None else l1
    placed = {b.spec.concept for b in cat.blocks.values()}
    placed |= {s.spec.concept for s in cat.sensors.values() if s.spec.concept}
    return sorted(set(l1) - placed - set(cat.excluded))


def document(cat: Catalogue | None = None) -> dict[str, Any]:
    """The catalogue as ONE JSON-able document (the editor and the LLM drafter read it)."""
    cat = catalogue() if cat is None else cat
    return cat.model_dump(mode="json")
