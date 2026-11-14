#!/usr/bin/env python3
"""Run a host script with a PINNED runner text (live-blocks.md 13.5: an A/B whose arms differ ONLY
in scripts/dungeon_hunt.py).

flow_play.py puts scripts/ first on sys.path when it is imported, so no path order can pick
another runner file. This launcher instead reads the pinned TEXT, checks its sha256, compiles it
as the module `dungeon_hunt` with `__file__` = scripts/dungeon_hunt.py (the module computes ROOT
from it) and puts it in sys.modules BEFORE the script runs; every `import dungeon_hunt` in the
process then gets it. Everything else (flow_play, poring_flow, the backend's modules, the setting
blocks) is the checkout's own, the same for every arm.

    runner_pin.py --text F --sha256 HEX --record OUT.json -- scripts/flow_play.py play ...

It refuses (rc 2, before the script runs, so before any input) when the text's sha256 is not
HEX. The record (OUT.json) names the text it ran: its sha256, its size, and whether it has
5b-1's HuntState (an A/B's way to show which runner each arm played).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import types
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "dungeon_hunt.py"
PATHS = ("packages/poring_env/src", "packages/poring_dataset/src", "packages/poring_flow/src",
         "packages/poring_packets/src", "services/backend/src")  # fmt: skip


def pin(text: str, want_sha256: str) -> types.ModuleType:
    """Compile `text` as dungeon_hunt (its __file__ the checkout's runner path) into sys.modules;
    SystemExit(2) when its sha256 is not the pinned one."""
    got = hashlib.sha256(text.encode()).hexdigest()
    if got != want_sha256:
        print(f"runner_pin refused: the runner text's sha256 is {got}, not {want_sha256}",
              file=sys.stderr, flush=True)  # fmt: skip
        raise SystemExit(2)
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    for p in PATHS:
        if str(ROOT / p) not in sys.path:
            sys.path.append(str(ROOT / p))
    mod = types.ModuleType("dungeon_hunt")
    mod.__file__ = str(RUNNER)
    sys.modules["dungeon_hunt"] = mod  # before exec: its dataclasses look themselves up there
    exec(compile(text, str(RUNNER), "exec"), mod.__dict__)  # noqa: S102 -- the pinned runner
    return mod


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--" not in args:
        print("runner_pin: usage: --text F --sha256 HEX --record OUT -- SCRIPT ARGS...",
              file=sys.stderr)  # fmt: skip
        return 2
    i = args.index("--")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--text", required=True, help="the runner text to play (a file)")
    ap.add_argument("--sha256", required=True, help="its pinned sha256")
    ap.add_argument("--record", required=True, help="where to write what ran (json)")
    a = ap.parse_args(args[:i])
    script, rest = args[i + 1], args[i + 2 :]
    text = Path(a.text).read_text()
    mod = pin(text, a.sha256)
    Path(a.record).write_text(json.dumps({
        "text": a.text, "sha256": a.sha256, "bytes": len(text.encode()),
        "huntstate": hasattr(mod, "HuntState"),
        "hunt_steps_version": getattr(mod, "HUNT_STEPS_VERSION", None)}) + "\n")  # fmt: skip
    sys.argv = [script, *rest]
    runpy.run_path(script, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
