#!/usr/bin/env python3
"""Re-decode a recorded session's packets with the CURRENT decoder (Phase 3 M3 states) from the
banked captures, as a sidecar next to the session on the NAS.

    replay_states.py SESSION [SESSION ...] [--datasets /mnt/poring-lab-datasets] [--dry-run]

Why: the M3 decoders (the ZC_NOTIFY_ACT family, ZC_CHANGE_DIRECTION, the vanish reason as dying)
went live on 2026-10-04 21:09; every session recorded before that has a packets.jsonl.gz without
them. The raw captures are banked in the sniffer's `captures` volume for 7 days (or 20 GB), so
this must run before they rotate out.

Per session:
1. its monotonic window [t0 - 30 min, t1 + 5 s] (the recorder's own lookback for the last map
   change) is mapped to wall time (this host's uptime spans the session, checked);
2. the hourly capture files covering it are replayed INSIDE the sniffer container, which runs the
   current poring_packets (`python -m poring_packets.replay`, validation accounts from
   config/environments.yaml). The pcapng is redacted (no login ids or passwords), and nothing but
   decoded events leaves the container;
3. the events are windowed exactly as the recorder windows them (timeline.session_events) and
   pseudonymised with the recorder's own pseudonymiser (other players' names and chat);
4. the sidecar `packets.states.jsonl.gz` goes into the session through
   `dataset_ship.py add-sidecar` (re-hashed on the NAS, checksums and INDEX updated).

A check before writing: the replay must reproduce the original file's entity appearances (the
same block ids). Otherwise nothing is written and the session is reported.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset_ship  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402

from poring_dataset.timeline import session_events  # noqa: E402

SNIFFER = "poring-lab-sniffer-1"
SIDECAR = "packets.states.jsonl.gz"
VALIDATION_AIDS = (2000001, 2000002)  # config/environments.yaml: the agent and the validation GM
NAME = re.compile(r"capture-(\d{8}T\d{6})Z\.pcapng$")


def captures() -> list[tuple[float, str]]:
    """(UTC start epoch, path) of every banked pcapng, oldest first."""
    out = subprocess.run(["docker", "exec", SNIFFER, "ls", "/captures"], capture_output=True,
                         text=True, check=True).stdout.split()  # fmt: skip
    files = []
    for name in out:
        m = NAME.match(name)
        if m:
            start = time.mktime(time.strptime(m.group(1), "%Y%m%dT%H%M%S")) - time.timezone
            files.append((start, f"/captures/{name}"))
    return sorted(files)


def covering(files: list[tuple[float, str]], lo_wall: float, hi_wall: float) -> list[str]:
    """The files whose span [start, next start) meets [lo_wall, hi_wall]."""
    out = []
    for i, (start, path) in enumerate(files):
        end = files[i + 1][0] if i + 1 < len(files) else float("inf")
        if start <= hi_wall and end >= lo_wall:
            out.append(path)
    return out


def replay(paths: list[str]) -> list[dict[str, Any]]:
    cmd = ["docker", "exec", SNIFFER, "python", "-m", "poring_packets.replay", *paths]
    for aid in VALIDATION_AIDS:
        cmd += ["--validation-aid", str(aid)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"replay failed: {res.stderr.strip()[-400:]}")
    return [json.loads(line) for line in res.stdout.splitlines() if line.strip()]


def appear_ids(events: list[dict[str, Any]]) -> set[int]:
    return {int(e["gid"]) for e in events if e.get("type") == "entity_appear"}


def one(session: Path, files: list[tuple[float, str]], dry_run: bool) -> dict[str, Any]:
    manifest = json.loads((session / "manifest.json").read_text())
    t0, t1 = int(manifest["t0_mono_ns"]), int(manifest["t1_mono_ns"])
    lookback = record_session.LOOKBACK_S * 1_000_000_000
    mono_now, wall_now = r.ns(), time.time()
    if (mono_now - t0) / 1e9 > float(Path("/proc/uptime").read_text().split()[0]):
        raise RuntimeError("the session predates this boot: monotonic -> wall is unknown")
    lo_wall = wall_now - (mono_now - (t0 - lookback)) / 1e9 - 60
    hi_wall = wall_now - (mono_now - t1) / 1e9 + 65
    paths = covering(files, lo_wall, hi_wall)
    if not paths:
        raise RuntimeError("no banked capture covers the session (rotated out?)")
    events = replay(paths)
    windowed, anchor = session_events(events, t0, t1, lookback_ns=lookback)
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        original = [json.loads(line) for line in fh]
    missing = appear_ids(original) - appear_ids(windowed)
    kinds: dict[str, int] = {}
    for e in windowed:
        kinds[str(e.get("type"))] = kinds.get(str(e.get("type")), 0) + 1
    row: dict[str, Any] = {"session": session.name, "captures": [Path(p).name for p in paths],
                           "events": len(windowed), "original_events": len(original),
                           "missing_appear_ids": len(missing), "types": kinds,
                           "anchor": anchor}  # fmt: skip
    if missing:
        row["written"] = False
        row["why"] = f"{len(missing)} block ids of the original are missing from the replay"
        return row
    if dry_run:
        row["written"] = False
        return row
    pseudo = record_session.pseudonymiser()
    tmp = Path("/dev/shm/poring-lab-tmp/replay-states") / session.name
    tmp.mkdir(parents=True, exist_ok=True)
    out = tmp / SIDECAR
    with gzip.open(out, "wt") as fh:
        for e in windowed:
            fh.write(json.dumps(pseudo(e), sort_keys=True) + "\n")
    row["sidecar"] = dataset_ship.add_sidecar(session, out)
    out.unlink()
    row["written"] = True
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--datasets", type=Path, default=dataset_ship.NAS_ROOT)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    files = captures()
    rc = 0
    for sid in a.sessions:
        try:
            row = one(a.datasets / sid, files, a.dry_run)
        except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
            row, rc = {"session": sid, "written": False, "error": str(exc)}, 1
        print(json.dumps(row), flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
