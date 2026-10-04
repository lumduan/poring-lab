#!/usr/bin/env python3
"""Full determinism pass on H.264 dataset sessions, on the HOST (Batt 2026-10-04: H.264 is the
default dataset format; the check moved off the live stream).

    dataset_check.py SESSION [SESSION ...] [--datasets /mnt/poring-lab-datasets]

Per session:
  * the decoder build must be the recording's (stream.done.json "versions": PyAV, libavcodec,
    libswscale) -- else the checksums are not comparable and the session is reported, not judged;
  * the whole stream is decoded once, from the first IDR, one access unit per packet exactly as the
    live client did (poring_dataset.h264.new_decoder), and EVERY decoded frame is compared with the
    live client's checksum;
  * decode throughput (frames/s, decode + BGRA conversion + checksum, one process).

Results go to data/bench/h264/<session>.check.json (gitignored) -- NEVER into the session's NAS
directory: it is shipped and checksummed (dataset_ship), and a write there would break its record.
Exit 0 = every session identical and complete, 1 = a mismatch, 3 = incomplete or not comparable.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dataset_ship  # noqa: E402

from poring_dataset import h264  # noqa: E402

OUT = ROOT / "data" / "bench" / "h264"


def check(session: Path) -> dict[str, Any]:
    import av

    try:
        s = h264.H264Session(session)
    except h264.DecoderMismatch as exc:
        return {"session": session.name, "comparable": False, "reason": str(exc)}
    data = (session / "stream.h264").read_bytes()
    first = next((i for i, u in enumerate(s.units) if u.idr), len(s.units))
    ctx = h264.new_decoder()
    compared = identical = missing = undecodable = 0
    mismatches: list[int] = []
    t0 = time.monotonic()
    for u in s.units[first:]:
        try:
            out = list(ctx.decode(av.Packet(data[u.offset : u.offset + u.length])))
        except av.error.FFmpegError:
            undecodable += 1
            continue
        if not out:
            undecodable += 1
            continue
        want = s.hashes.get(u.frame_id)
        if want is None:
            missing += 1
            continue
        compared += 1
        got = h264.frame_digest(np.ascontiguousarray(out[0].to_ndarray(format="bgra")))
        if got == want:
            identical += 1
        elif len(mismatches) < 20:
            mismatches.append(u.frame_id)
    wall = time.monotonic() - t0
    return {
        "session": session.name, "comparable": True, "versions": h264.decoder_versions(),
        "units": len(s.units), "skipped_before_first_idr": first, "compared": compared,
        "identical": identical, "mismatched": compared - identical,
        "first_mismatches": mismatches, "missing_hash": missing, "undecodable": undecodable,
        "deterministic": compared > 0 and identical == compared,
        "complete": missing == 0 and undecodable == 0 and first == 0,
        "decode_fps": round(compared / wall, 1) if wall > 0 else None,
        "wall_s": round(wall, 1), "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("sessions", nargs="+")
    ap.add_argument("--datasets", type=Path, default=dataset_ship.NAS_ROOT)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for name in a.sessions:
        path = Path(name) if "/" in name else a.datasets / name
        result = check(path)
        (OUT / f"{path.name}.check.json").write_text(json.dumps(result, indent=1) + "\n")
        print(json.dumps(result))
        results.append(result)
    if any(r.get("comparable") and r["mismatched"] for r in results):
        return 1
    if any(not r.get("comparable") or not r["complete"] for r in results):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
