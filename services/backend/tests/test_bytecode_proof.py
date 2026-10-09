"""scripts/bytecode_proof.py: the positive cases -- a real code change in the import graph FAILS
(named), a declared harness change PASSES, a change of line numbers only PASSES, a changed constant
FAILS -- on two tiny source trees."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "bytecode_proof.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bytecode_proof", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bytecode_proof"] = mod
    spec.loader.exec_module(mod)
    return mod


bp = load()
RULE = "import helper\nLIMIT = 3\n\n\ndef decide(x):\n    return helper.gate(x) and x < LIMIT\n"
HELPER = "def gate(x):\n    return x > 0\n\n\ndef run(n):\n    return [n]\n"


def tree(root: Path, rule: str = RULE, helper: str = HELPER) -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "rule.py").write_text(rule)
    (root / "scripts" / "helper.py").write_text(helper)
    return root


def proof(old: Path, new: Path, harness: set[str] = frozenset()) -> dict[str, object]:  # type: ignore[assignment]
    return bp.compare(bp.fingerprints(old, "rule", []), bp.fingerprints(new, "rule", []),
                      set(harness))  # fmt: skip


def test_identical_trees_pass(tmp_path: Path) -> None:
    got = proof(tree(tmp_path / "a"), tree(tmp_path / "b"))
    assert got["verdict"] == "PASS" and got["changed"] == []


def test_a_decision_change_fails_by_name(tmp_path: Path) -> None:
    got = proof(
        tree(tmp_path / "a"), tree(tmp_path / "b", helper=HELPER.replace("x > 0", "x >= 0"))
    )
    assert got["verdict"] == "FAIL" and got["undeclared_changes"] == ["helper.gate"]


def test_a_declared_harness_change_passes(tmp_path: Path) -> None:
    got = proof(tree(tmp_path / "a"), tree(tmp_path / "b", helper=HELPER.replace("[n]", "[n, n]")),
                {"helper.run"})  # fmt: skip
    assert got["verdict"] == "PASS" and got["changed"] == ["helper.run"]


def test_moved_lines_pass_and_a_constant_fails(tmp_path: Path) -> None:
    moved = "# a comment\n# another\n" + RULE
    assert proof(tree(tmp_path / "a"), tree(tmp_path / "b", rule=moved))["verdict"] == "PASS"
    got = proof(tree(tmp_path / "c"), tree(tmp_path / "d", rule=RULE.replace("= 3", "= 4")))
    assert got["verdict"] == "FAIL" and got["undeclared_changes"] == ["rule.LIMIT"]


def test_a_changed_dict_constant_fails(tmp_path: Path) -> None:
    rule = RULE + 'PORTAL = {"cell": (1, 2)}\n'
    got = proof(tree(tmp_path / "a", rule=rule),
                tree(tmp_path / "b", rule=rule.replace("(1, 2)", "(1, 3)")))  # fmt: skip
    assert got["verdict"] == "FAIL" and got["undeclared_changes"] == ["rule.PORTAL"]
