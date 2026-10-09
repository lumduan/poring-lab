"""poring_env.ui_sets (2026-10-09): the per-path UI template sets and the S2 set's PROOF -- the lock
picks the path (rdp -> rdp, console -> s2, anything else refused), and the s2 set is ready only
while proof.json names every needed component as passed with the files' current sha256. Synthetic
files only: no client pixels."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from poring_env import ui_sets


def write_component(root: Path, component: str, seed: int = 0) -> None:
    """Every file of the component, with synthetic bytes (masks included)."""
    rng = np.random.default_rng(seed)
    for rel in ui_sets.COMPONENT_FILES[component]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            p.write_text(json.dumps({"seed": seed}))
        elif rel.endswith(".npz"):
            np.savez(p, a=rng.random(4))
        else:
            np.save(p, rng.random((3, 5)).astype(np.float32))


def prove(root: Path, component: str, passed: bool = True) -> dict[str, object]:
    before = ui_sets.file_hashes(root, component)
    return ui_sets.record(root, component, passed, {"frames": 9}, before, command="test")


def test_the_lock_picks_the_path_and_nothing_else() -> None:
    assert ui_sets.path_for_backend("rdp") == "rdp"
    assert ui_sets.path_for_backend("console") == "s2"
    for other in ("hold", "", "RDP", "s2", "moonlight"):
        with pytest.raises(ui_sets.UnknownPath):
            ui_sets.path_for_backend(other)
    base = Path("/x/data/ui_anchors")
    assert ui_sets.set_root(base, "rdp") == base  # the RDP set stays where it always was
    assert ui_sets.set_root(base, "s2") == base / "s2"
    with pytest.raises(ui_sets.UnknownPath):
        ui_sets.set_root(base, "console")


def test_the_gate_windows_and_component_files() -> None:
    assert ui_sets.GATE_WINDOWS == ("status", "skills", "inventory", "equipment")
    assert set(ui_sets.GATE_NEEDS) == {"windows", "t2"}
    assert "npc_dialog/params.json" in ui_sets.COMPONENT_FILES["t2"]
    assert set(ui_sets.COMPONENT_FILES["t2"]) < set(ui_sets.COMPONENT_FILES["t3"])  # T3 reads T2
    assert ui_sets.COMPONENT_FILES["gm_levels"] == ("gm_state/levels_1_1.npy",)


def test_no_proof_or_an_unproven_set_is_not_ready(tmp_path: Path) -> None:
    assert ui_sets.problems(tmp_path, ["windows"]) == [f"no valid proof.json in {tmp_path}"]
    write_component(tmp_path, "windows")
    assert ui_sets.problems(tmp_path, ["windows"])  # files present, never proven
    prove(tmp_path, "windows")
    assert ui_sets.problems(tmp_path, ["windows"]) == []
    assert ui_sets.problems(tmp_path, ["windows", "t2"]) == ["t2: not proven"]


def test_a_pass_records_every_files_hash_and_absence(tmp_path: Path) -> None:
    write_component(tmp_path, "windows")
    (tmp_path / "skills_mask.npy").unlink()  # a mask that was not cut: proven ABSENT
    line = prove(tmp_path, "windows")
    assert line["verdict"] == "PASS"
    doc = json.loads((tmp_path / ui_sets.PROOF_FILE).read_text())
    entry = doc["components"]["windows"]
    assert entry["pass"] is True and entry["evidence"] == {"frames": 9}
    assert set(entry["files"]) == set(ui_sets.COMPONENT_FILES["windows"])
    assert entry["files"]["skills_mask.npy"] is None and entry["files"]["skills.npy"]
    assert ui_sets.problems(tmp_path, ["windows"]) == []
    # a file ADDED after the proof is a change too
    np.save(tmp_path / "skills_mask.npy", np.ones((3, 5), np.float32))
    assert ui_sets.problems(tmp_path, ["windows"]) == [
        "windows: stale since the proof (skills_mask.npy)"
    ]
    log = (tmp_path / ui_sets.PROOF_LOG).read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])["component"] == "windows"


def test_a_template_edited_after_the_proof_is_stale(tmp_path: Path) -> None:
    write_component(tmp_path, "t2")
    prove(tmp_path, "t2")
    assert ui_sets.problems(tmp_path, ["t2"]) == []
    p = tmp_path / "npc_dialog" / "npc_dialog_next.npy"
    np.save(p, np.load(p) + 1)
    assert ui_sets.problems(tmp_path, ["t2"]) == [
        "t2: stale since the proof (npc_dialog/npc_dialog_next.npy)"
    ]
    p.unlink()  # removed: also stale
    assert "stale" in ui_sets.problems(tmp_path, ["t2"])[0]


def test_a_later_failure_removes_an_earlier_pass(tmp_path: Path) -> None:
    write_component(tmp_path, "gm_levels")
    write_component(tmp_path, "gm_notices")
    prove(tmp_path, "gm_levels")
    prove(tmp_path, "gm_notices")
    assert ui_sets.problems(tmp_path, ["gm_levels", "gm_notices"]) == []
    assert prove(tmp_path, "gm_levels", passed=False)["verdict"] == "FAIL"
    assert ui_sets.problems(tmp_path, ["gm_levels", "gm_notices"]) == ["gm_levels: not proven"]
    assert len((tmp_path / ui_sets.PROOF_LOG).read_text().splitlines()) == 3  # FAILs logged too


def test_templates_changed_during_the_prove_never_pass(tmp_path: Path) -> None:
    write_component(tmp_path, "windows", seed=1)
    before = ui_sets.file_hashes(tmp_path, "windows")
    write_component(tmp_path, "windows", seed=2)  # re-cut while the prove ran
    line = ui_sets.record(tmp_path, "windows", True, {}, before, command="test")
    assert line["verdict"].startswith("FAIL: the templates changed")
    assert ui_sets.problems(tmp_path, ["windows"]) == ["windows: not proven"]


def test_a_proof_without_files_or_of_another_shape_is_refused(tmp_path: Path) -> None:
    line = prove(tmp_path, "windows")  # nothing cut at all
    assert line["verdict"] == "FAIL: no template file to prove"
    write_component(tmp_path, "windows")
    prove(tmp_path, "windows")
    doc = json.loads((tmp_path / ui_sets.PROOF_FILE).read_text())
    doc["components"]["windows"]["files"].pop("status.npy")  # an older reader's file list
    (tmp_path / ui_sets.PROOF_FILE).write_text(json.dumps(doc))
    assert ui_sets.problems(tmp_path, ["windows"]) == [
        "windows: proof names another file list (re-prove)"
    ]
    doc["version"] = 99
    (tmp_path / ui_sets.PROOF_FILE).write_text(json.dumps(doc))
    assert ui_sets.problems(tmp_path, ["windows"])[0].startswith("no valid proof.json")
    (tmp_path / ui_sets.PROOF_FILE).write_text("{not json")
    assert ui_sets.problems(tmp_path, ["windows"])[0].startswith("no valid proof.json")
    doc["version"] = ui_sets.PROOF_VERSION
    doc["components"]["windows"]["pass"] = "yes"  # only a literal true passes
    (tmp_path / ui_sets.PROOF_FILE).write_text(json.dumps(doc))
    assert ui_sets.problems(tmp_path, ["windows"]) == ["windows: proof did not pass"]


def test_the_digest_follows_the_bytes_and_status_reports(tmp_path: Path) -> None:
    write_component(tmp_path, "windows")
    d1 = ui_sets.digest(tmp_path, ["windows"])
    assert d1 == ui_sets.digest(tmp_path, ["windows"])
    write_component(tmp_path, "windows", seed=5)
    assert ui_sets.digest(tmp_path, ["windows"]) != d1
    prove(tmp_path, "windows")
    st = ui_sets.status(tmp_path)
    assert st["proof"] is True and st["components"]["windows"]["ready"] is True
    assert st["components"]["windows"]["files_present"] == 8
    assert st["components"]["t2"]["ready"] is False and st["components"]["t2"]["files_present"] == 0
