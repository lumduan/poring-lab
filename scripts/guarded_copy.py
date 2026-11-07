#!/usr/bin/env python3
"""Run a COPY command (rsync; never a delete) under guarded_build's IO guard, the 2026-10-28
small-IO rule: a capture cgroup above 30 % IO stall for 30 s stops it (SIGINT).

    python3 scripts/guarded_copy.py LABEL -- rsync -a --bwlimit=15000 SRC DST

Used 2026-11-07 to copy the agent's history to bot-server (docs/operations/bot-server-handover.md);
the same for the cutover's re-sync. The output goes to $TMPDIR/poring-guarded-<LABEL>.log.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guarded_build as gb  # noqa: E402


def main(argv: list[str]) -> int:
    if "--" not in argv or argv.index("--") != 1 or len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    label, cmd = argv[0], argv[2:]
    guard = gb.Guard(gb.cgroup_paths(), 30.0, 10.0, sustain=30.0)
    print(f"rule: {guard.describe()}; watching: {', '.join(guard.paths)}", flush=True)
    ok = gb.run_process(label, cmd, guard)
    print(f"{label}: {'OK' if ok else 'STOPPED/FAILED'}; worst stall {guard.worst}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
