#!/usr/bin/env python3
"""Install the typing-only foreground gate's templates into the HUMAN-ONLY settings store
(Batt, 2026-10-06; services/backend/src/poring_backend/foreground.py).

    foreground_template.py install rdp      the RDP/X template + its box
    foreground_template.py install stream   the console (S2, H.264) template
    foreground_template.py status           what is installed (sha256, shape, box)

Source: ro_agent's calibration in ``data/ro_agent/signatures/``:
  * ``client_title_active.{npy,json}`` -- cut while the client's title bar is ACTIVE on RDP
    (``ro_agent.py calibrate client_title_active``);
  * ``client_title_active@stream.npy`` -- the same box on the console stream, cut at the start of
    an S2 session (``ro_agent.py calibrate client_title_active@stream``).

Why a copy: vision mounts ``./data`` read-write, so a template there could be swapped by the agent.
The gate reads ONLY ``./settings/foreground/`` (mounted into the backend alone). Every write is
atomic (temp + rename: the backend's status loop reads these files), read back by sha256, and
appended to ``settings/foreground/install.log``. Client-derived pixels: never committed
(settings/ is gitignored).
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "ro_agent" / "signatures"
DEST = ROOT / "settings" / "foreground"
NAME = "client_title_active"
SIG_SCALE = 8  # poring_backend.signature.SIG_SCALE (checked by tests/test_foreground_template.py)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_copy(src: Path, dest: Path) -> str:
    data = src.read_bytes()
    tmp = dest.with_name(f".{dest.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    got = sha(dest)
    if got != hashlib.sha256(data).hexdigest():
        raise SystemExit(f"read-back differs: {dest}")
    return got


def expected_shape(box: list[int]) -> tuple[int, int]:
    _, _, w, h = box
    return math.ceil(h / SIG_SCALE), math.ceil(w / SIG_SCALE)


def install(which: str, src_dir: Path, dest_dir: Path) -> int:
    box_src = src_dir / f"{NAME}.json"
    npy_src = src_dir / (f"{NAME}.npy" if which == "rdp" else f"{NAME}@stream.npy")
    for p in (box_src, npy_src):
        if not p.exists():
            raise SystemExit(f"missing {p}: calibrate it with ro_agent.py first")
    box = json.loads(box_src.read_text())["box"]
    ref = np.load(npy_src)
    if ref.shape != expected_shape(box):
        raise SystemExit(f"{npy_src.name}: shape {ref.shape} does not fit box {box}")
    if not dest_dir.parent.is_dir():
        raise SystemExit(f"{dest_dir.parent} is missing (the settings store)")
    dest_dir.mkdir(exist_ok=True)
    done = {}
    if which == "rdp":
        done[f"{NAME}.json"] = atomic_copy(box_src, dest_dir / f"{NAME}.json")
    done[npy_src.name] = atomic_copy(npy_src, dest_dir / npy_src.name)
    line = json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "install": which,
                       "box": box, "sha256": done})  # fmt: skip
    with (dest_dir / "install.log").open("a") as fh:
        fh.write(line + "\n")
    print(line)
    return 0


def status(dest_dir: Path) -> int:
    for name in (f"{NAME}.json", f"{NAME}.npy", f"{NAME}@stream.npy"):
        path = dest_dir / name
        if not path.exists():
            print(f"{name:32s} MISSING")
            continue
        extra = np.load(path).shape if name.endswith(".npy") else json.loads(path.read_text())
        print(f"{name:32s} {sha(path)[:16]}  {extra}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("install")
    i.add_argument("which", choices=("rdp", "stream"))
    i.add_argument("--src", type=Path, default=SRC)
    sub.add_parser("status")
    a = ap.parse_args()
    if a.cmd == "install":
        return install(a.which, a.src, DEST)
    return status(DEST)


if __name__ == "__main__":
    sys.exit(main())
