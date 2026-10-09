#!/usr/bin/env python3
"""Copy the extracted map GATs to `data/gat`, the MW2 editor's read-only GAT mount (Batt, 10-09).

The backend's /flows simulate reads the GATs from /lab-gat (compose.dev.yaml: `./data/gat`,
read-only; routes_flows.PORING_GAT_DIR). The extraction itself lives in /dev/shm
(poring_dataset.camera.GAT_DIR) and is gone after a reboot, while the backend restarts at boot, so
the mount takes a copy on disk. GATs are client-derived: `data/` is gitignored and the pre-commit
hook refuses map files.

    flows_gat.py [--src DIR] [--dst data/gat]

Each file is written as `.part`, renamed, then re-hashed (read back). Files already identical are
left alone; nothing is deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "poring_dataset" / "src"))
from poring_dataset.camera import GAT_DIR  # noqa: E402

DST = ROOT / "data" / "gat"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(src: Path, dst: Path) -> list[tuple[str, str, str]]:
    """(name, what happened, sha256 prefix) per GAT in ``src``."""
    if not src.is_dir():
        raise SystemExit(f"{src}: no GAT extraction here (re-extract after a reboot: grf_read)")
    dst.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str, str, str]] = []
    for f in sorted(src.glob("*.gat")):
        want = sha256(f)
        target = dst / f.name
        if target.exists() and sha256(target) == want:
            out.append((f.name, "same", want[:12]))
            continue
        part = target.with_name(target.name + ".part")
        part.write_bytes(f.read_bytes())
        os.replace(part, target)
        if sha256(target) != want:
            raise SystemExit(f"{target}: read-back hash differs")
        out.append((f.name, "copied", want[:12]))
    if not out:
        raise SystemExit(f"{src}: no *.gat files")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--src", type=Path, default=GAT_DIR)
    ap.add_argument("--dst", type=Path, default=DST)
    a = ap.parse_args()
    for name, what, digest in publish(a.src, a.dst):
        print(f"{name:24} {what:7} {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
