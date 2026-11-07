#!/usr/bin/env python3
"""Build the simple-bot hand-out for Batt's class, OUTSIDE the repo (a lab tool, not for students).

    UV_CACHE_DIR=/dev/shm/poring-lab-tmp/uv-simplebot UV_PYTHON_DOWNLOADS=never \\
        python3 teaching/simple-bot/make_kit.py

It writes /dev/shm/poring-lab-tmp/teaching-kit/ (and teaching-kit.zip beside it):
    simple_bot.py, README.md   copied from this folder, with NOTICE.md (which licence covers what)
    LICENSE, LICENSE-AGPL-3.0.txt   the repository's Apache-2.0 text and vision's AGPL-3.0 text
    v1.onnx                    the lab's v1 detector (/dev/shm/poring-lab-detector/model/...)
    samples/                   ~20 prt_fild08 frames from a hunt recording, each with >= 2 monster
                               boxes, + SOURCE.txt naming the recording and the frames

The samples are picked by running the kit's OWN simple_bot.py (through uv, so the kit is proven to
run) on an even spread of ~200 frames and keeping an even spread of the ones with >= 2 monsters.

The model and the frames are client-derived / weights: NEVER commit them (CLAUDE.md rule 4; this
folder's .gitignore refuses *.onnx, samples/ and *.zip). The frames directory is read with one
plain listing (no walk); the uv environment must live in RAM (UV_CACHE_DIR under /dev/shm: rule 7,
the host disk is shared with live capture).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = Path("/dev/shm/poring-lab-tmp/teaching-kit")
MODEL = Path("/dev/shm/poring-lab-detector/model/v1png-last-736x1280.onnx")
FRAMES = Path(
    "/mnt/poring-lab-datasets/hunt-recordings/20261106T111229-demo-hunt-flow56/frames"
)  # prt_fild08, 2026-11-06 11:12, 9,156 game-region JPEGs at 1280 x 720
SPREAD, KEEP, MIN_MONSTERS = 200, 20, 2
# the kit's licences (NOTICE.md): simple_bot.py Apache-2.0, v1.onnx AGPL-3.0 (ADR-0018)
LICENCES = (
    (HERE.parents[1] / "LICENSE", "LICENSE"),
    (HERE.parents[1] / "services" / "vision" / "LICENSE", "LICENSE-AGPL-3.0.txt"),
)
SHM = Path("/dev/shm")
SHM_LIMIT = 4 * 10**9  # the lab's /dev/shm total stays at or under 4 GB (rule 7)


def spread(items: Sequence[Any], n: int) -> list[Any]:
    """PURE: n items evenly spaced over the sequence (all of them when it has <= n)."""
    if len(items) <= n:
        return list(items)
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def pick_samples(rows: Sequence[dict[str, Any]], keep: int, min_monsters: int) -> list[str]:
    """PURE: from simple_bot's --json rows, the files with >= min_monsters monster boxes, `keep`
    of them evenly spaced (so the samples span the whole recording)."""
    good = [r["file"] for r in rows if sum(b[5] == "monster" for b in r["boxes"]) >= min_monsters]
    return spread(good, keep)


def shm_used() -> int:
    """Bytes in use on /dev/shm (the whole filesystem: every user's scratch counts)."""
    u = shutil.disk_usage(SHM)
    return u.total - u.free


def main(argv: Sequence[str] | None = None) -> int:
    """Build the kit: refuse unsafe settings, copy the files, pick the samples, zip it."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--frames", type=Path, default=FRAMES)
    ap.add_argument("--spread", type=int, default=SPREAD)
    ap.add_argument("--keep", type=int, default=KEEP)
    ap.add_argument("--threads", type=int, default=4, help="CPU threads for the detector")
    ap.add_argument("--force", action="store_true", help="replace an existing kit")
    args = ap.parse_args(argv)

    cache = os.environ.get("UV_CACHE_DIR", "")
    if not cache.startswith("/dev/shm/"):
        print(
            "refused: set UV_CACHE_DIR under /dev/shm (the uv env must not land on the shared "
            "disk)",
            file=sys.stderr,
        )
        return 2
    if not args.model.is_file():
        print(f"refused: no model at {args.model}", file=sys.stderr)
        return 2
    if shm_used() + 600 * 10**6 > SHM_LIMIT:  # the uv env (~300 MB) + the kit (~40 MB) + margin
        print(f"refused: /dev/shm holds {shm_used() / 1e9:.2f} GB already", file=sys.stderr)
        return 2
    out: Path = args.out
    if out.exists():
        if not args.force:
            print(f"refused: {out} exists (--force replaces it)", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    (out / "samples").mkdir(parents=True)
    for name in ("simple_bot.py", "README.md", "NOTICE.md"):
        shutil.copy2(HERE / name, out / name)
    for src, name in LICENCES:  # NOTICE.md says which file is under which (Batt 2026-11-07)
        shutil.copy2(src, out / name)
    shutil.copy2(args.model, out / "v1.onnx")

    frames = sorted(n for n in os.listdir(args.frames) if n.lower().endswith(".jpg"))  # one dir
    candidates = [str(args.frames / n) for n in spread(frames, args.spread)]
    report = out.parent / "teaching-kit-candidates.json"
    env = {**os.environ, "UV_PYTHON_DOWNLOADS": "never", "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        "uv",
        "run",
        "--quiet",
        "simple_bot.py",
        "--replay",
        *candidates,
        "--model",
        "v1.onnx",
        "--no-show",
        "--json",
        str(report),
        "--threads",
        str(args.threads),
    ]
    print(f"detecting on {len(candidates)} of {len(frames)} frames ...", flush=True)
    rc = subprocess.run(cmd, cwd=out, env=env, stdout=subprocess.DEVNULL).returncode
    if rc != 0:
        print(f"simple_bot failed (rc {rc})", file=sys.stderr)
        return 1
    rows = json.loads(report.read_text())
    report.unlink()
    picked = pick_samples(rows, args.keep, MIN_MONSTERS)
    lines = [
        f"prt_fild08 frames from the poring-lab recording {args.frames.parent.name}",
        f"picked: {len(picked)} of {len(rows)} spread frames with >= {MIN_MONSTERS} monster "
        "boxes (v1 model)",
        "",
    ]
    for i, f in enumerate(picked, 1):
        name = f"{i:02d}-{Path(f).name}"
        shutil.copy2(f, out / "samples" / name)
        lines.append(name)
    (out / "samples" / "SOURCE.txt").write_text("\n".join(lines) + "\n")
    zip_path = shutil.make_archive(str(out), "zip", out.parent, out.name)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(
        f"kit: {out} ({size / 1e6:.1f} MB, {len(picked)} samples); zip: {zip_path} "
        f"({Path(zip_path).stat().st_size / 1e6:.1f} MB)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
