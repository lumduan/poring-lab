#!/usr/bin/env python3
"""Extract rAthena's map caches for poring_dataset (Phase 2 walkability) from the PINNED source.

Same input as scripts/gen_packet_tables.py: the rAthena tarball at RATHENA_REF, sha256-checked
against packages/poring_packets/.../tables.lock.json. Only these four files are taken:

    db/import-tmpl/map_cache.dat -> import   (rAthena's `make import` copies import-tmpl to import)
    db/pre-re/map_cache.dat      -> pre-re   (the lab runs prere=yes: prt_fild08, prt_church)
    db/re/map_cache.dat          -> re
    db/map_cache.dat             -> base     (new_4-1 and 1285 others)

They are server data, written to poring_dataset/_generated/ (gitignored); their sha256 is in the
committed mapcache.lock.json. Downloads go to /dev/shm (rule 7).

    python3 scripts/gen_mapcache.py                # fetch (if needed), extract, verify the lock
    python3 scripts/gen_mapcache.py --update-lock  # after a deliberate RATHENA_REF change
"""

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from gen_packet_tables import LOCK as PACKET_LOCK  # noqa: E402
from gen_packet_tables import WORK, fetch  # noqa: E402

PKG = REPO / "packages" / "poring_dataset" / "src" / "poring_dataset"
OUT = PKG / "_generated"
LOCK = PKG / "mapcache.lock.json"
MEMBERS = {
    "import": ("db/import-tmpl/map_cache.dat", "map_cache.import.dat"),
    "pre-re": ("db/pre-re/map_cache.dat", "map_cache.pre-re.dat"),
    "re": ("db/re/map_cache.dat", "map_cache.re.dat"),
    "base": ("db/map_cache.dat", "map_cache.base.dat"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-lock", action="store_true")
    args = ap.parse_args()
    ra = json.loads(PACKET_LOCK.read_text())["inputs"]["rathena"]
    WORK.mkdir(parents=True, exist_ok=True)
    tgz = WORK / f"rathena-{ra['ref']}.tar.gz"
    fetch(ra["url"], tgz, ra["sha256"])
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    with tarfile.open(tgz) as t:
        names = {m.name.split("/", 1)[1]: m for m in t.getmembers() if "/" in m.name}
        for key, (member, out_name) in MEMBERS.items():
            fh = t.extractfile(names[member])
            assert fh is not None
            data = fh.read()
            (OUT / out_name).write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            files[key] = {"name": out_name, "member": member, "sha256": digest, "bytes": len(data)}
    current = {"rathena_ref": ra["ref"], "files": files}
    if args.update_lock or not LOCK.exists():
        LOCK.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        print(f"wrote {LOCK.relative_to(REPO)}")
        return 0
    locked = json.loads(LOCK.read_text())
    if locked != current:
        print("map caches differ from mapcache.lock.json (use --update-lock deliberately)")
        return 1
    print("map caches extracted and match the lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
