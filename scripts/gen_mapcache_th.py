#!/usr/bin/env python3
"""rathena-th's map cache (the Thai-data experiment, Batt 2026-10-05), made by rAthena's OWN
mapcache tool from the Thai client's GRF.

    gen_mapcache_th.py [--grf /mnt/poring-thai-src/ro_thai/data.grf] [--jobs 4] [--maps M ...]

* rAthena at the pinned SHA (the tarball scripts/gen_packet_tables.py fetched and verified against
  packages/poring_packets/src/poring_packets/tables.lock.json) is compiled in a THROWAWAY container
  of the toolchain image (poring-lab/rathena-build:local): --network none, a tmpfs work dir, our
  uid. Only `common` and the `mapcache` tool are built.
* The tool reads the maps from a data_dir: rAthena's grfio refuses this 2026 GRF outright (a
  stored file name longer than its buffer: "...new_dragonbreath_water_11_clock.str is too long",
  2026-10-05). So OUR reader (scripts/grf_read.py) extracts only the lab's maps (--maps: .gat and
  .rsw) into /dev/shm; the encrypted RSWs (prt_fild08, iz_dun00/01 are MIXCRYPT) go through the
  host-local STUDY decoder (offline files, local output, never committed). The tool caches those
  maps; every other map falls back to the stock caches at rathena-th's start (db/import is read
  first). A map the GRF lacks is listed in the lock.
* Output (CLIENT-DERIVED: gitignored data/, never committed; the pre-commit hook refuses
  map_cache*.dat): data/mapcache-th/map_cache.dat + mapcache-th.lock.json (the GRF's identity, the
  tarball's and the output's sha256, the map count and the not-found list). rathena-th mounts the
  directory read-only; its entrypoint installs the file as db/import/map_cache.dat.
* A ~2 min compile (-j4) in tmpfs plus the GATs/RSWs read from the NAS: after market close, with
  the pressure sampler watching (CLAUDE.md rule 5).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_packet_tables as gpt  # noqa: E402

from poring_dataset import mapcache  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GRF = Path("/mnt/poring-thai-src/ro_thai/data.grf")
GRF_SHA_FILE = Path("/mnt/poring-thai-src/_windows-ro_thai.sha256")  # verified at the 10-03 copy
OUT_DIR = ROOT / "data" / "mapcache-th"
SCRATCH = Path("/dev/shm/poring-lab-tmp/mapcache-th")

LAB_MAPS = ("prontera", "prt_fild08", "prt_church", "izlude", "iz_dun00", "iz_dun01")
SCRIPT = """set -euo pipefail
exec 2> /out/trace.log
set -x
cd /work
tar -xzf /in/rathena.tar.gz
cd rathena-{ref}
./configure --enable-prere > /out/configure.log 2>&1 || {{ tail -30 /out/configure.log; exit 3; }}
make -j{jobs} common > /out/make.log 2>&1 || {{ tail -40 /out/make.log; exit 4; }}
make -C src/tool mapcache >> /out/make.log 2>&1 || {{ tail -40 /out/make.log; exit 5; }}
# The pinned tool resets its header at the start of EACH list directory in -rebuild mode (db/,
# then db/import/): a list in db/ only ends as "0 maps now in cache" over the data. So db/ gets an
# empty list and db/import/ ours.
: > db/lab_maps.txt
mkdir -p db/import && cp /in/thai/lab_maps.txt db/import/lab_maps.txt
printf 'data_dir: /in/thai/\\n' > /work/grf-files.txt
./mapcache -grf /work/grf-files.txt -list lab_maps.txt -cache /out/map_cache.dat -rebuild \\
  > /out/mapcache.log 2>&1
"""
NOT_FOUND = re.compile(r"Map '(?:\x1b\[[0-9;]*m)?([A-Za-z0-9_@.-]+)(?:\x1b\[[0-9;]*m)?' not found")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def grf_identity(grf: Path) -> dict[str, object]:
    """The GRF's recorded sha256 (from the copy's own checksum file: no 3.3 GB re-read) + size."""
    recorded = None
    if GRF_SHA_FILE.exists():
        for line in GRF_SHA_FILE.read_text(encoding="utf-8-sig").splitlines():  # a Windows BOM
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*").endswith(grf.name):
                recorded = parts[0]
    st = grf.stat()
    return {"path": str(grf), "bytes": st.st_size, "mtime": int(st.st_mtime),
            "sha256_recorded": recorded}  # fmt: skip


def extract_maps(grf: Path, maps: list[str], dest: Path) -> list[str]:
    """data/<map>.gat and .rsw of each map into dest (the tool's data_dir); the maps found."""
    import grf_read

    found = []
    (dest / "data").mkdir(parents=True, exist_ok=True)
    with grf.open("rb") as f:
        entries = grf_read.iter_entries(f, grf_read.read_header(f))
        by_name = {grf_read.norm_name(e.name): e for e in entries if e.is_file}
        for m in maps:
            entries = [by_name.get(f"data/{m}.{ext}") for ext in ("gat", "rsw")]
            if entries[0] is None:
                continue
            for e in entries:
                if e is not None:
                    data = grf_read.read_entry(f, e, decode_des=True, decode_mixcrypt=True)
                    (dest / "data" / grf_read.norm_name(e.name).split("/")[-1]).write_bytes(data)
            found.append(m)
    (dest / "lab_maps.txt").write_text("".join(f"{m}\n" for m in found))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--grf", type=Path, default=GRF)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--maps", nargs="+", default=list(LAB_MAPS))
    a = ap.parse_args()
    if subprocess.run(["docker", "image", "inspect", gpt.IMAGE], capture_output=True).returncode:
        sys.exit(f"{gpt.IMAGE} missing: build it through the IO guard (gen_packet_tables.py)")
    ra = json.loads(gpt.LOCK.read_text())["inputs"]["rathena"]
    tgz = gpt.WORK / f"rathena-{ra['ref']}.tar.gz"
    gpt.WORK.mkdir(parents=True, exist_ok=True)
    gpt.fetch(ra["url"], tgz, ra["sha256"])  # verified against the lock (fetched if absent)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for stale in ("map_cache.dat", "mapcache.log", "trace.log", "configure.log", "make.log"):
        (SCRATCH / stale).unlink(missing_ok=True)
    thai = SCRATCH / "thai"
    found = extract_maps(a.grf, a.maps, thai)
    absent = sorted(set(a.maps) - set(found))
    t0 = time.time()
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/work", "--tmpfs", "/work:rw,size=1500m,exec,mode=1777",
        "-v", f"{thai}:/in/thai:ro", "-v", f"{tgz}:/in/rathena.tar.gz:ro",
        "-v", f"{SCRATCH}:/out", gpt.IMAGE, "bash", "-c", SCRIPT.format(ref=ra["ref"], jobs=a.jobs),
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        trace = (SCRATCH / "trace.log").read_text(errors="replace")[-2000:] if (
            SCRATCH / "trace.log").exists() else ""  # fmt: skip
        sys.exit(f"mapcache container failed (rc {proc.returncode}):\n{proc.stdout[-3000:]}"
                 f"\n{proc.stderr[-2000:]}\n--- trace (logs in {SCRATCH}):\n{trace}")  # fmt: skip
    data = (SCRATCH / "map_cache.dat").read_bytes()
    maps = mapcache.parse(data)  # the format check: header size, every map inflates to xs*ys
    log = (SCRATCH / "mapcache.log").read_text(errors="replace")
    missing = sorted(set(NOT_FOUND.findall(log)) | set(absent))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / ".map_cache.dat.tmp"
    tmp.write_bytes(data)
    tmp.replace(OUT_DIR / "map_cache.dat")
    if (OUT_DIR / "map_cache.dat").read_bytes() != data:
        sys.exit("read-back of data/mapcache-th/map_cache.dat differs")
    lock = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seconds": round(time.time() - t0),
        "grf": grf_identity(a.grf), "rathena": {"ref": ra["ref"], "tarball_sha256": ra["sha256"]},
        "output": {"name": "map_cache.dat", "bytes": len(data),
                   "sha256": sha256(OUT_DIR / "map_cache.dat"), "maps": len(maps)},
        "maps_requested": a.maps,
        "not_found": missing,
    }  # fmt: skip
    (OUT_DIR / "mapcache-th.lock.json").write_text(json.dumps(lock, indent=1) + "\n")
    print(json.dumps({k: lock[k] for k in ("seconds", "output")}, indent=1))
    print(f"maps not in the GRF (they fall back to the stock caches): {len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
