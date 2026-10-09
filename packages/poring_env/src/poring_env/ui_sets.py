"""Per-path UI template sets and their PROOF (2026-10-09; collect@1's preflight found the blocker:
the UI gate's templates are RDP-cut, so every typed line on S2 was refused).

The client's UI is the same on both display paths, but its PIXELS are not: RDP (progressive) and
the S2 console stream (H.264) soften text and edges differently. So every template the mandatory
UI gate (``scripts/ui_gate.py``) and the GM fixed-state check (``scripts/gm_state.py``) read exists
once per path, under one root each, with the same sub-layout:

    rdp   data/ui_anchors/                 (unchanged: the sets cut and proven on RDP)
    s2    data/ui_anchors/s2/              (cut from banked S2 frames; docs/operations/
                                            s2-gate-templates.md)

The capture-backend lock (ADR-0009) picks the path: ``BACKEND=rdp`` -> rdp, ``console`` -> s2,
anything else (``hold``, a malformed lock) -> refused. Never a fallback from one path to the other.

The s2 set is used ONLY when it is COMPLETE and PROVEN: ``data/ui_anchors/s2/proof.json``, written
only by the prove commands on a PASS, names each component's result and the sha256 of every file
that component's readers load (``None`` = the file was absent when it was proven, so a file added
later is a change too). A missing component, a failed one, or any file whose bytes differ from the
proof (a re-cut, an edit, a swap) -> not ready, and the caller refuses (fail closed). The rdp set
carries no proof file: its proofs are the 2026-10-07 / 2026-10-09 records (docs/demonstrations.md
3.30, open_window@1), and its behaviour is unchanged.

Pure: paths, hashes and JSON; no pixels, no lock reading (the caller passes the lock's backend).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from poring_env import npc_dialog as nd

PATHS = ("rdp", "s2")
BACKEND_PATH = {"rdp": "rdp", "console": "s2"}
S2_SUBDIR = "s2"
PROOF_FILE = "proof.json"
PROOF_LOG = "proof-log.jsonl"
PROOF_VERSION = 1

# The four windows the UI gate looks for at their homes (ADR-0011 anchors; open_window@1).
GATE_WINDOWS = ("status", "skills", "inventory", "equipment")

_T2_FILES = (
    f"{nd.TEMPLATE_DIR.name}/{nd.PARAMS_FILE}",
    *(
        f"{nd.TEMPLATE_DIR.name}/{name}{suffix}.npy"
        for name in (*nd.WINDOW_NAMES, *nd.BUTTON_NAMES, *nd.ARROW_NAMES)
        for suffix in ("", "_mask")
    ),
)

# Every file each component's readers may load, relative to the set's root. A component's proof
# hashes exactly this list, so a reader that starts loading another file needs a new proof.
COMPONENT_FILES: dict[str, tuple[str, ...]] = {
    # ui_gate.windows_at_home: each window's title-text template and its stable mask
    "windows": tuple(f"{w}{s}.npy" for w in GATE_WINDOWS for s in ("", "_mask")),
    # poring_env.npc_dialog (talk@1 T2): the two windows, the buttons, the arrows, the rules
    "t2": _T2_FILES,
    # poring_env.menu_text (T3): its glyphs, read on the rows T2 places
    "t3": ("menu_glyphs.npz", *_T2_FILES),
    # gm_state: the level lines at Base Lv 1 / Job Lv 1
    "gm_levels": ("gm_state/levels_1_1.npy",),
    # gm_state: the level-change notices, each a template + the mask of its own pixels
    "gm_notices": (
        "gm_state/badge.npy",
        "gm_state/badge_mask.npy",
        "gm_state/levelup_icon.npy",
        "gm_state/levelup_mask.npy",
    ),
}
COMPONENTS = tuple(COMPONENT_FILES)

# What each consumer needs proven before it reads the s2 set.
GATE_NEEDS = ("windows", "t2")
GM_LEVELS_NEEDS = ("gm_levels",)
GM_NOTICES_NEEDS = ("gm_notices",)


class UnknownPath(ValueError):
    """The lock names no path with a template set (``hold``, malformed): refuse."""


def path_for_backend(backend: str) -> str:
    """The template set for the lock's BACKEND: rdp -> "rdp", console -> "s2"; else UnknownPath."""
    try:
        return BACKEND_PATH[backend]
    except KeyError:
        raise UnknownPath(f"no UI template set for the lock's backend {backend!r}") from None


def set_root(anchors_root: Path, path: str) -> Path:
    """The set's directory: rdp = ``anchors_root`` itself (data/ui_anchors), s2 = its ``s2/``."""
    if path == "rdp":
        return anchors_root
    if path == "s2":
        return anchors_root / S2_SUBDIR
    raise UnknownPath(f"unknown template path {path!r} (one of {PATHS})")


def sha256_file(path: Path) -> str | None:
    """The file's sha256, or None when it does not exist."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    return hashlib.sha256(data).hexdigest()


def file_hashes(root: Path, component: str) -> dict[str, str | None]:
    """{relative path: sha256 | None} over the component's file list, as it is NOW."""
    return {rel: sha256_file(root / rel) for rel in COMPONENT_FILES[component]}


def read_proof(root: Path) -> dict[str, Any] | None:
    """The proof document, or None when absent / unreadable / of another version."""
    try:
        doc = json.loads((root / PROOF_FILE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("version") != PROOF_VERSION:
        return None
    if not isinstance(doc.get("components"), dict):
        return None
    return doc


def problems(root: Path, needs: Iterable[str]) -> list[str]:
    """Why the set at ``root`` is NOT ready for ``needs`` (empty = complete and proven): no proof
    file, a component missing / not passed, a file missing that the proof requires, or any file
    whose bytes differ from the proof (stale)."""
    doc = read_proof(root)
    if doc is None:
        return [f"no valid {PROOF_FILE} in {root}"]
    out: list[str] = []
    for comp in needs:
        entry = doc["components"].get(comp)
        if not isinstance(entry, dict):
            out.append(f"{comp}: not proven")
            continue
        if entry.get("pass") is not True:
            out.append(f"{comp}: proof did not pass")
            continue
        proven = entry.get("files")
        if not isinstance(proven, dict) or set(proven) != set(COMPONENT_FILES[comp]):
            out.append(f"{comp}: proof names another file list (re-prove)")
            continue
        if not any(proven.values()):
            out.append(f"{comp}: proof covers no file")
            continue
        now = file_hashes(root, comp)
        stale = sorted(rel for rel, h in now.items() if h != proven[rel])
        if stale:
            out.append(f"{comp}: stale since the proof ({', '.join(stale)})")
    return out


def digest(root: Path, needs: Iterable[str]) -> str:
    """A short digest of the files ``needs`` cover (a cache key for templates loaded from them)."""
    h = hashlib.sha256()
    for comp in needs:
        for rel, sha in sorted(file_hashes(root, comp).items()):
            h.update(f"{rel}={sha}\n".encode())
    return h.hexdigest()[:16]


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def record(root: Path, component: str, passed: bool, evidence: Mapping[str, Any],
           before: Mapping[str, str | None], *, command: str) -> dict[str, Any]:  # fmt: skip
    """Called ONLY by a prove command, after it ran on the files hashed in ``before`` (taken
    before the templates were loaded). PASS -> the component is written with the files' hashes;
    FAIL -> any earlier entry for it is REMOVED (a later failure must not leave an older pass
    standing). Templates that changed during the prove -> recorded as a FAIL. Every call is
    appended to proof-log.jsonl. Returns the log line."""
    if component not in COMPONENT_FILES:
        raise ValueError(f"unknown component {component!r}")
    after = file_hashes(root, component)
    verdict = "PASS" if passed else "FAIL"
    if dict(before) != after:
        passed, verdict = False, "FAIL: the templates changed during the prove"
    if passed and not any(after.values()):
        passed, verdict = False, "FAIL: no template file to prove"
    root.mkdir(parents=True, exist_ok=True)
    doc = read_proof(root) or {"version": PROOF_VERSION, "components": {}}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if passed:
        doc["components"][component] = {
            "pass": True,
            "verdict": verdict,
            "proved_at": stamp,
            "command": command,
            "evidence": dict(evidence),
            "files": after,
        }
    else:
        doc["components"].pop(component, None)
    _write_atomic(root / PROOF_FILE, json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n")
    line = {"t": stamp, "component": component, "verdict": verdict, "command": command,
            "evidence": dict(evidence), "files": after}  # fmt: skip
    with (root / PROOF_LOG).open("a") as fh:
        fh.write(json.dumps(line, sort_keys=True, default=str) + "\n")
    return line


def status(root: Path) -> dict[str, Any]:
    """Per component: proven / stale / missing (for a person; ``ui_gate.py status``)."""
    doc = read_proof(root)
    out: dict[str, Any] = {"root": str(root), "proof": doc is not None, "components": {}}
    for comp in COMPONENTS:
        present = sum(1 for h in file_hashes(root, comp).values() if h)
        why = problems(root, [comp])
        entry = doc["components"].get(comp) if doc is not None else None
        out["components"][comp] = {
            "files_present": present,
            "ready": not why,
            "why": why,
            "proved_at": entry.get("proved_at") if isinstance(entry, dict) else None,
        }
    return out
