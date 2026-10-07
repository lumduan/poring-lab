"""L1 concepts: what an RO action IS, independent of client, server and language (Batt, 2026-10-07).

The four layers (ADR-0012's policy / anchor / locale split, extended to the whole game):
- **L1 concept** (this module + l1/*.yaml): the action, its steps in game terms, its
  preconditions, failure modes and game rules, and the OUTCOME that proves it worked. It never
  changes across servers; exceptions are marked.
- **L2 client:** how a client build does it on screen (shortcuts, window anchors, dialog vs
  window, PACKETVER packets).
- **L3 server:** where and with what (NPC positions, shops, warps, Kafra options, job-change
  scripts). Generated locally from the server's own files; never committed when GPL.
- **L4 locale:** on-screen text via the locale-pack keys (ADR-0011/0012).

Every L1 entry starts UNVERIFIED: written from memory, which may mix renewal, pre-renewal and
regional versions. It becomes verified only through the demonstration method (docs/
demonstrations.md): its rule passes a pre-registered alone-test on RDP AND on S2. Then
`verified_on` records the client build, server, locale, path and session.

Each outcome carries two checks:
- `runtime`: what the library checks on the SCREEN after acting (packets are never decision
  input, ADR-0007);
- `offline`: what the packet verifier checks afterwards (poring_dataset.verify) for tests and
  labels.
"""

from __future__ import annotations

from importlib import resources
from typing import Literal

import yaml  # type: ignore[import-untyped]  # no stubs in the dev env
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CONFIG = ConfigDict(extra="forbid", frozen=True)
CONCEPT_ID = r"^[a-z]+\.[a-z_]+$"
BINDING = r"^L[234]\.[a-z_]+(\.[a-z_]+)*$"


class Check(BaseModel):
    model_config = _CONFIG
    kind: Literal["screen", "packets", "none"]
    signal: str = Field(min_length=1, max_length=300)
    verifier: str | None = None  # e.g. poring_dataset.verify.verify_login


class Outcome(BaseModel):
    model_config = _CONFIG
    runtime: Check
    offline: Check

    @model_validator(mode="after")
    def _kinds(self) -> Outcome:
        if self.runtime.kind == "packets":
            raise ValueError("a runtime check never reads packets (ADR-0007): screen or none")
        if self.offline.kind == "screen":
            raise ValueError("the offline check is the packet verifier (or none)")
        return self


class VerifiedOn(BaseModel):
    model_config = _CONFIG
    client: str  # the L2 client build, e.g. kro-20211103-prere
    server: str  # the environment id, e.g. lab-rathena
    locale: str  # the L4 locale pack, e.g. en
    path: Literal["rdp", "s2"]
    session: str  # the alone-test's demo session id
    rule: str  # name@version
    date: str


class Concept(BaseModel):
    model_config = _CONFIG
    id: str = Field(pattern=CONCEPT_ID)
    purpose: str = Field(min_length=1, max_length=200)
    params: list[str] = []
    steps: list[str] = Field(min_length=1)
    preconditions: list[str] = []
    failure_modes: list[str] = []
    game_rules: list[str] = []
    outcome: Outcome
    bindings_needed: list[str] = []
    exceptions: list[str] = []
    workflow_wave: int | None = Field(default=None, ge=1, le=4)  # None: not on the example route
    status: Literal["unverified", "verified"] = "unverified"
    verified_on: list[VerifiedOn] = []
    references: list[str] = []  # facts only, never copied text

    @field_validator("bindings_needed")
    @classmethod
    def _bindings(cls, v: list[str]) -> list[str]:
        import re

        bad = [b for b in v if not re.match(BINDING, b)]
        if bad:
            raise ValueError(f"binding keys are L2./L3./L4. dotted lower-case names: {bad}")
        return v

    @model_validator(mode="after")
    def _verified(self) -> Concept:
        paths = {v.path for v in self.verified_on}
        if self.status == "verified" and paths != {"rdp", "s2"}:
            raise ValueError(f"{self.id}: verified needs an alone-test pass on BOTH rdp and s2")
        return self


class Domain(BaseModel):
    model_config = _CONFIG
    domain: str = Field(pattern=r"^[a-z]+$")
    concepts: list[Concept] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids(self) -> Domain:
        wrong = [c.id for c in self.concepts if not c.id.startswith(self.domain + ".")]
        if wrong:
            raise ValueError(f"{self.domain}: ids must start with '{self.domain}.': {wrong}")
        return self


def load_l1() -> dict[str, Concept]:
    """Every L1 concept, by id (unique across the domain files)."""
    out: dict[str, Concept] = {}
    folder = resources.files("poring_skills") / "l1"
    for entry in sorted(folder.iterdir(), key=lambda p: p.name):
        if not entry.name.endswith(".yaml"):
            continue
        dom = Domain.model_validate(yaml.safe_load(entry.read_text(encoding="utf-8")))
        if dom.domain != entry.name.removesuffix(".yaml"):
            raise ValueError(f"{entry.name}: domain {dom.domain!r} must match the file name")
        for c in dom.concepts:
            if c.id in out:
                raise ValueError(f"duplicate L1 id {c.id}")
            out[c.id] = c
    return out
