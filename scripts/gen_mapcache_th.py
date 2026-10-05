#!/usr/bin/env python3
"""rathena-th's map cache (the Thai-data experiment, Batt 2026-10-05), made by rAthena's OWN
mapcache tool from the Thai client's GRF.

    gen_mapcache_th.py [--grf /mnt/poring-thai-src/ro_thai/data.grf] [--jobs 4]

* rAthena at the pinned SHA (the tarball scripts/gen_packet_tables.py fetched and verified against
  packages/poring_packets/src/poring_packets/tables.lock.json) is compiled in a THROWAWAY container
  of the toolchain image (poring-lab/rathena-build:local): --network none, a tmpfs work dir, our
  uid. Only `common` and the `mapcache` tool are built.
* The tool reads the GRF READ-ONLY (bind-mounted :ro) through rAthena's own grfio, which decodes
  the GRF's encrypted map entries itself (we run it; none of its code is copied). It caches every
  map of the pinned db/map_index.txt that the GRF holds; the maps it does not find are listed.
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

SCRIPT = """set -euo pipefail
cd /work
tar -xzf /in/rathena.tar.gz
cd rathena-{ref}
./configure --enable-prere > /work/configure.log 2>&1 || {{ tail -30 /work/configure.log; exit 3; }}
make -j{jobs} common > /work/make.log 2>&1 || {{ tail -40 /work/make.log; exit 4; }}
make -C src/tool mapcache >> /work/make.log 2>&1 || {{ tail -40 /work/make.log; exit 5; }}
mkdir -p db/import && cp db/import-tmpl/map_index.txt db/import/map_index.txt
printf 'grf: /in/data.grf\\n' > /work/grf-files.txt
./mapcache -grf /work/grf-files.txt -cache /out/map_cache.dat -rebuild > /out/mapcache.log 2>&1
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
        for line in GRF_SHA_FILE.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*").endswith(grf.name):
                recorded = parts[0]
    st = grf.stat()
    return {"path": str(grf), "bytes": st.st_size, "mtime": int(st.st_mtime),
            "sha256_recorded": recorded}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--grf", type=Path, default=GRF)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    if subprocess.run(["docker", "image", "inspect", gpt.IMAGE], capture_output=True).returncode:
        sys.exit(f"{gpt.IMAGE} missing: build it through the IO guard (gen_packet_tables.py)")
    ra = json.loads(gpt.LOCK.read_text())["inputs"]["rathena"]
    tgz = gpt.WORK / f"rathena-{ra['ref']}.tar.gz"
    gpt.WORK.mkdir(parents=True, exist_ok=True)
    gpt.fetch(ra["url"], tgz, ra["sha256"])  # verified against the lock (fetched if absent)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for stale in ("map_cache.dat", "mapcache.log"):
        (SCRATCH / stale).unlink(missing_ok=True)
    t0 = time.time()
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", "HOME=/work", "--tmpfs", "/work:rw,size=1500m,exec,mode=1777",
        "-v", f"{a.grf.resolve()}:/in/data.grf:ro", "-v", f"{tgz}:/in/rathena.tar.gz:ro",
        "-v", f"{SCRATCH}:/out", gpt.IMAGE, "bash", "-c", SCRIPT.format(ref=ra["ref"], jobs=a.jobs),
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"mapcache container failed (rc {proc.returncode}):\n{proc.stdout[-3000:]}"
                 f"\n{proc.stderr[-2000:]}")  # fmt: skip
    data = (SCRATCH / "map_cache.dat").read_bytes()
    maps = mapcache.parse(data)  # the format check: header size, every map inflates to xs*ys
    log = (SCRATCH / "mapcache.log").read_text(errors="replace")
    missing = sorted(set(NOT_FOUND.findall(log)))
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
        "not_found": missing,
    }  # fmt: skip
    (OUT_DIR / "mapcache-th.lock.json").write_text(json.dumps(lock, indent=1) + "\n")
    print(json.dumps({k: lock[k] for k in ("seconds", "output")}, indent=1))
    print(f"maps not in the GRF (they fall back to the stock caches): {len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
