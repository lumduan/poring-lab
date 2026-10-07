"""poring_skills.schema: the L1 concepts load, obey the schema, and the generated doc is current."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from poring_skills.schema import Concept, Domain, load_l1

ROOT = Path(__file__).resolve().parents[3]


def concept(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "ui.open_window",
        "purpose": "p",
        "steps": ["s"],
        "outcome": {
            "runtime": {"kind": "screen", "signal": "anchor"},
            "offline": {"kind": "none", "signal": "client side"},
        },
    }
    base.update(over)
    return base


def test_every_l1_file_loads_and_ids_are_unique() -> None:
    concepts = load_l1()
    assert len(concepts) >= 30
    assert {
        "session.login",
        "nav.walk_to",
        "combat.attack_target",
        "npc.choose",
        "trade.sell",
        "storage.deposit",
        "item.refine",
        "char.respawn",
    } <= set(concepts)
    # a pass on ONE path is recorded but never flips the status (rdp AND s2 needed)
    for c in concepts.values():
        paths = {v.path for v in c.verified_on}
        assert c.status == ("verified" if paths == {"rdp", "s2"} else "unverified"), c.id


def test_every_workflow_wave_is_covered() -> None:
    waves = {c.workflow_wave for c in load_l1().values()}
    assert {1, 2, 3, 4} <= waves


def test_a_runtime_check_never_reads_packets() -> None:
    with pytest.raises(ValidationError, match="ADR-0007"):
        bad = {
            "runtime": {"kind": "packets", "signal": "x"},
            "offline": {"kind": "none", "signal": "y"},
        }
        Concept.model_validate(concept(outcome=bad))


def test_verified_needs_an_alone_test_pass_on_both_paths() -> None:
    rdp = {
        "client": "kro-20211103-prere",
        "server": "lab-rathena",
        "locale": "en",
        "path": "rdp",
        "session": "s",
        "rule": "open_window@1",
        "date": "2026-10-07",
    }
    with pytest.raises(ValidationError, match="BOTH"):
        Concept.model_validate(concept(status="verified", verified_on=[rdp]))
    ok = Concept.model_validate(
        concept(status="verified", verified_on=[rdp, {**rdp, "path": "s2"}])
    )
    assert ok.status == "verified"


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "Open.window"},
        {"bindings_needed": ["L1.x"]},
        {"bindings_needed": ["L2.Window"]},
        {"steps": []},
        {"surprise": 1},
    ],
)
def test_schema_refusals(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Concept.model_validate(concept(**bad))


def test_a_domain_holds_only_its_own_ids() -> None:
    with pytest.raises(ValidationError):
        Domain.model_validate({"domain": "nav", "concepts": [concept()]})


def test_the_generated_doc_is_current() -> None:
    script = ROOT / "scripts" / "gen_knowledge_doc.py"
    res = subprocess.run(
        [sys.executable, str(script), "--check"], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr
