"""Check a recorded H.264 bitstream offline (Post-S2 round C2, 2026-10-04). Runs in the gamestream
container (PyAV lives only there), never while a stream needs the CPU:

    python3 -m s2spike.h264check /s2-rec/<id> [--seeks 20] [--seed 1]

1. DETERMINISM: decode <id>.h264 from byte 0, one access unit per packet exactly as the live
   client did (the same Decoder: low delay, slice threads), hash every frame (crc32 + adler32 of the
   BGRA bytes) and compare with <id>.hash.csv by frame_id. All equal = the bitstream IS the
   dataset; a dropped live hash is "missing", not a mismatch.
2. RANDOM ACCESS: for random target access units, a fresh decoder decodes from the IDR before the
   target up to it; the time to the target frame is what "jump to frame N" costs.
3. THROUGHPUT: the sequential pass's frames per second and decode CPU.

Writes <id>.check.json next to the recording and prints it. Exit 0 = deterministic and complete,
1 = a mismatch, 3 = no mismatch but incomplete (missing hashes or undecodable units).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import resource
import sys
import time
from pathlib import Path
from typing import Any

from .decode import Decoder, versions
from .h264rec import frame_digest


def read_index(path: Path) -> list[dict[str, int]]:
    with path.open() as f:
        return [{k: int(v) for k, v in row.items()} for row in csv.DictReader(f)]


def read_hashes(path: Path) -> dict[int, str]:
    with path.open() as f:
        return {int(r["frame_id"]): r["crc32_adler32"] for r in csv.DictReader(f)}


def digest(frame: Any) -> str:
    import numpy as np

    return frame_digest(np.ascontiguousarray(frame))


def check(base: Path, seeks: int = 20, seed: int = 1) -> dict[str, Any]:
    data = base.with_name(base.name + ".h264").read_bytes()
    rows = [r for r in read_index(base.with_name(base.name + ".idx.csv")) if r["au"] >= 0]
    live = read_hashes(base.with_name(base.name + ".hash.csv"))
    # 1 + 3: the sequential pass
    dec = Decoder()
    cpu0 = resource.getrusage(resource.RUSAGE_SELF)
    t0 = time.monotonic()
    compared = identical = missing = undecodable = extra = 0
    mismatches: list[int] = []
    frames_out = 0
    hash_s = 0.0  # time spent hashing: not decode throughput
    for row in rows:
        au = data[row["offset"] : row["offset"] + row["length"]]
        try:
            frames = dec.decode(au)
        except Exception:  # noqa: BLE001 -- counted
            undecodable += 1
            continue
        frames_out += len(frames)
        if row["frame_id"] < 0:
            extra += len(frames)  # the live decode failed here; nothing to compare
            continue
        for k, frame in enumerate(frames):
            fid = row["frame_id"] + k
            want = live.get(fid)
            if want is None:
                missing += 1
                continue
            compared += 1
            th = time.monotonic()
            got = digest(frame)
            hash_s += time.monotonic() - th
            if got == want:
                identical += 1
            elif len(mismatches) < 20:
                mismatches.append(fid)
    wall = time.monotonic() - t0
    cpu1 = resource.getrusage(resource.RUSAGE_SELF)
    cpu = (cpu1.ru_utime - cpu0.ru_utime) + (cpu1.ru_stime - cpu0.ru_stime)
    # 2: random access
    idrs = [i for i, r in enumerate(rows) if r["idr"] == 1]
    rng = random.Random(seed)
    seek_ms: list[float] = []
    seek_aus: list[int] = []
    for _ in range(seeks if idrs else 0):
        target = rng.randrange(idrs[0], len(rows))
        start = max(i for i in idrs if i <= target)
        t1 = time.monotonic()
        fresh = Decoder()  # a reader's jump: decode from the IDR, convert ONLY the target frame
        last: Any = None
        for row in rows[start : target + 1]:
            try:
                for frame in fresh.ctx.decode(fresh._packet(
                        data[row["offset"] : row["offset"] + row["length"]])):  # fmt: skip
                    last = frame
            except Exception:  # noqa: BLE001,S112 -- the sequential pass counts these
                continue
        if last is not None:
            last.to_ndarray(format="bgra")
        seek_ms.append((time.monotonic() - t1) * 1000)
        seek_aus.append(target - start + 1)

    def pct(xs: list[float], p: float) -> float | None:
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(p * len(xs)))], 1) if xs else None

    mismatch = compared - identical
    return {
        "recording": base.name, "versions": versions(), "bytes": len(data), "aus": len(rows),
        "idrs": len(idrs), "frames_decoded": frames_out, "compared": compared,
        "identical": identical, "mismatched": mismatch, "first_mismatches": mismatches,
        "missing_live_hash": missing, "undecodable_units": undecodable,
        "frames_without_live_frame": extra,
        "deterministic": mismatch == 0 and compared > 0,
        "complete": missing == 0 and undecodable == 0,
        # decode + BGRA conversion only (the hashing time is taken out)
        "decode_fps": round(frames_out / (wall - hash_s), 1) if wall > hash_s else None,
        "hash_ms_per_frame": round(hash_s * 1000 / compared, 2) if compared else None,
        "decode_cpu_s": round(cpu, 2), "decode_wall_s": round(wall, 2),
        "seek": {"n": len(seek_ms), "p50_ms": pct(seek_ms, 0.5), "p95_ms": pct(seek_ms, 0.95),
                 "max_ms": round(max(seek_ms), 1) if seek_ms else None,
                 "aus_p50": pct([float(a) for a in seek_aus], 0.5)},
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("recording", type=Path, help="the path without extension: /s2-rec/<id>")
    ap.add_argument("--seeks", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    result = check(a.recording, a.seeks, a.seed)
    out = a.recording.with_name(a.recording.name + ".check.json")
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result))
    if result["mismatched"]:
        return 1
    return 0 if result["complete"] and result["deterministic"] else 3


if __name__ == "__main__":
    sys.exit(main())
