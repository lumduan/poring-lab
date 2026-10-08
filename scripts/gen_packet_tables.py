"""Generate the RO packet length tables for poring_packets at BUILD time (ADR-0007).

Batt 2026-10-01: generated from pinned sources at build time, never committed.

Only this generator and its checksums are committed (packages/poring_packets/tables.lock.json); the
derived table (`_generated/lengths.json`) is not. Inputs are pinned and SHA-256-checked:

  * rAthena source at RATHENA_REF (the server's own definitions)        -> primary
  * OpenKore tables/kRO/Ragexe_2021_11_03/recvpackets.txt (the client's) -> fills gaps + cross-check

How the rAthena side is read (no hand-copied numbers):
  1. `g++ -E` over the packet headers, with the exact flags of the map-server build, inside a
     throwaway container of the cached rathena build stage (`poring-lab/rathena-build:local`, which
     has the toolchain). Everything runs in a tmpfs.
  2. The host pairs every active `HEADER_<NAME> = id` with an active `struct PACKET_<NAME>` and
     writes a C++ dumper printing `sizeof` for each (-1 if the struct has a PacketLength field),
     plus a replay of the map-server's packet_db (clif_packetdb.hpp + clif_shuffle.hpp, last write
     wins), keeping only entries that have a handler -- the plain `packet(id,len)` lines are mostly
     stale server->client lengths.
  3. A second container run compiles and runs the dumper.

Merge rule (Batt 2026-10-01: rAthena first, OpenKore fills gaps):
  client->server  map: rAthena's packet_db handlers only (complete). login/char: CA_/CH_ structs,
                  and OpenKore for the few the servers parse by hand without a struct (CH_ENTER
                  0x0065 is read field by field in char_clif.cpp).
  server->client  rAthena struct sizes (AC_/HC_/ZC_) where they exist, otherwise OpenKore
  An id known to both must agree. Disagreements are written to the lock; the generator fails if a
  decoded (first-slice) id disagrees, or if the disagreement set differs from the committed lock
  (drift), unless --accept-drift.

    python3 scripts/gen_packet_tables.py            # verify inputs, generate, compare with the lock
    python3 scripts/gen_packet_tables.py --update-lock

The build-stage image must exist; build it through the IO guard, never directly:
    python3 scripts/guarded_build.py --sustain 30 --spike 25 \
        target:rathena:build:poring-lab/rathena-build:local
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "packages" / "poring_packets"
LOCK = PKG / "src" / "poring_packets" / "tables.lock.json"
OUT = PKG / "src" / "poring_packets" / "_generated" / "lengths.json"
IMAGE = "poring-lab/rathena-build:local"
WORK = Path(os.environ.get("POR_GEN_DIR", "/dev/shm/poring-lab-pktgen"))

# Ids the decoder interprets (docs/phase1-plan.md section 4; then Phase 3 M3, the ZC_NOTIFY_ACT
# family + ZC_CHANGE_DIRECTION; then 2026-10-07, decode.MAP_SC / MAP_CS: NPC dialogs, shops,
# stat/skill points, equipment, item use, CZ_REQUEST_ACT2): any disagreement here is fatal.
# None of the 2026-10-07 ids is in the lock's disagreement list (checked 2026-10-07), so adding
# them changes neither the output nor the lock. The same holds for the 2026-10-08 loot@1 ids (floor
# items, the pickup request/result, the drop; checked 2026-10-08).
DECODED = {
    0x0064, 0x0AC4, 0x083E, 0x0065, 0x082D, 0x006B, 0x0B72, 0x0066, 0x0AC5, 0x0436, 0x0283, 0x02EB,
    0x007D, 0x0360, 0x007F, 0x035F, 0x0087, 0x0088, 0x09FD, 0x09FE, 0x09FF, 0x0080, 0x0091, 0x0AC7,
    0x00B0, 0x00B1, 0x0ACB, 0x080E, 0x00F3, 0x008D, 0x008E, 0x0096, 0x09DE, 0x09DF, 0x009A, 0x01C3,
    0x0108, 0x0109, 0x017E, 0x017F, 0x02C1,
    0x008A, 0x02E1, 0x08C8, 0x009C,
    0x00B4, 0x00B5, 0x00B6, 0x00B7, 0x0142, 0x01D4, 0x00C4, 0x0B77, 0x00CA, 0x00C7, 0x00CB, 0x00BC,
    0x010E, 0x0B32, 0x0999, 0x099A, 0x01C8,
    0x0090, 0x00B8, 0x00B9, 0x0146, 0x0143, 0x01D5, 0x00C5, 0x00C8, 0x00C9, 0x00BB, 0x0112, 0x0998,
    0x00AB, 0x0439, 0x0437,
    0x0ADD, 0x009D, 0x00A1, 0x0B41, 0x00AF, 0x0362, 0x0363,
}  # fmt: skip
CS_PREFIXES = {"CA": "login", "CH": "char", "CZ": "map"}
SC_PREFIXES = {"AC": "login", "HC": "char", "ZC": "map"}

FLAGS = (
    "-std=c++17 -I/work/src -I/work/src/common -I/work/src/map -I/work/3rdparty/libconfig "
    "-I/work/3rdparty/rapidyaml/src -I/work/3rdparty/rapidyaml/ext/c4core/src "
    "-I/work/3rdparty/json/include -I/usr/include/mariadb -I/usr/include/mariadb/mysql -DHAS_TLS "
    "-DHAVE_GETADDRINFO -DHAVE_SETRLIMIT -DHAVE_STRNLEN -DHAVE_MONOTONIC_CLOCK "
    "-DPACKETVER={packetver}{prere}"
)
# map/packets.hpp and common/packets.hpp share the include guard PACKETS_HPP (the servers never
# include both), so the map server and login/char are read as two separate translation units.
TUS = {
    "map": (
        '#include "map/clif.hpp"\n#include "map/packets.hpp"\n#include "map/packets_struct.hpp"\n'
    ),
    "common": '#include "common/packets.hpp"\n',
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, dest: Path, want: str | None) -> str:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:  # noqa: S310 (pinned https URLs)
            dest.write_bytes(r.read())
    got = sha256(dest)
    if want and got != want:
        sys.exit(f"checksum mismatch for {url}: {got} != {want} (lock)")
    return got


def container(script: str, mounts: list[str]) -> str:
    cmd = ["docker", "run", "--rm", "--network", "none", "--tmpfs", "/work:size=1g,exec"]
    for m in mounts:
        cmd += ["-v", m]
    cmd += [IMAGE, "bash", "-c", script]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"container step failed:\n{proc.stderr[-4000:]}")
    return proc.stdout


def parse_preprocessed(text: str) -> dict[str, tuple[int, bool]]:
    """NAME -> (header id, variable?) for each active HEADER_NAME paired with struct PACKET_NAME."""
    headers: dict[str, int] = {}
    for m in re.finditer(r"const\s+int16\s+HEADER_(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*;", text):
        headers[m.group(1)] = int(m.group(2), 0)
    structs: dict[str, bool] = {}
    for m in re.finditer(r"struct\s+PACKET_(\w+)\s*\{(.*?)\}\s*__attribute__", text, re.S):
        structs[m.group(1)] = bool(re.search(r"\b[pP]acket[lL](?:ength|en)\b", m.group(2)))
    return {n: (headers[n], structs[n]) for n in headers if n in structs}


def dumper_source(tu: str, pairs: dict[str, tuple[int, bool]]) -> str:
    lines = [
        "#include <cstdio>",
        TUS[tu],
        "#define DUMP_DB(cmd, length, func) "
        'std::printf("db %d %d %s\\n", (int)(cmd), (int)(length), #func);',
        "#define packetdb_addpacket(cmd, length, func, ...) DUMP_DB(cmd, length, func)",
        "int main() {",
    ]
    for name, (_, variable) in sorted(pairs.items()):
        size = "-1" if variable else f"(int)sizeof(struct PACKET_{name})"
        lines.append(f'  std::printf("struct {name} %d %d\\n", (int)HEADER_{name}, {size});')
    if tu == "map":
        lines += ['#include "map/clif_packetdb.hpp"', '#include "map/clif_shuffle.hpp"']
    lines += ["  return 0;", "}"]
    return "\n".join(lines) + "\n"


def main() -> int:  # noqa: PLR0912, PLR0915
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-lock", action="store_true")
    ap.add_argument("--accept-drift", action="store_true")
    args = ap.parse_args()
    lock = json.loads(LOCK.read_text())
    inputs = lock["inputs"]
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        sys.exit(f"{IMAGE} missing: build it through the IO guard (see this script's docstring)")

    WORK.mkdir(parents=True, exist_ok=True)
    ra = inputs["rathena"]
    tgz = WORK / f"rathena-{ra['ref']}.tar.gz"
    got_ra = fetch(ra["url"], tgz, None if args.update_lock else ra["sha256"])
    ok_ = inputs["openkore_recvpackets"]
    rp = WORK / "recvpackets.txt"
    got_ok = fetch(ok_["url"], rp, None if args.update_lock else ok_["sha256"])

    src_dir = WORK / "src"
    if not (src_dir / "src" / "map" / "clif_packetdb.hpp").exists():
        src_dir.mkdir(exist_ok=True)
        with tarfile.open(tgz) as t:
            members = [m for m in t.getmembers() if re.search(r"/(src|3rdparty)/", m.name)]
            for m in members:
                m.name = m.name.split("/", 1)[1]
            t.extractall(src_dir, members=members, filter="data")
    flags = FLAGS.format(packetver=lock["packetver"], prere=" -DPRERE" if lock["prere"] else "")
    dumped = ""
    pairs: dict[str, tuple[int, bool]] = {}
    for tu, include in TUS.items():
        (WORK / f"headers_{tu}.cpp").write_text(include)
        pre = container(
            f"cp -r /src/. /work/ && g++ {flags} -E -P /gen/headers_{tu}.cpp",
            [f"{src_dir}:/src:ro", f"{WORK}:/gen:ro"],
        )
        tu_pairs = parse_preprocessed(pre)
        pairs.update(tu_pairs)
        (WORK / f"dump_{tu}.cpp").write_text(dumper_source(tu, tu_pairs))
        dumped += container(
            f"cp -r /src/. /work/ && g++ {flags} -w -o /work/dump /gen/dump_{tu}.cpp && /work/dump",
            [f"{src_dir}:/src:ro", f"{WORK}:/gen:ro"],
        )

    cs: dict[str, dict[int, int]] = {"login": {}, "char": {}, "map": {}}
    sc: dict[str, dict[int, int]] = {"login": {}, "char": {}, "map": {}}
    for line in dumped.splitlines():
        kind, *rest = line.split()
        if kind == "struct":
            name, pid, length = rest[0], int(rest[1]), int(rest[2])
            if name[:2] in CS_PREFIXES:
                cs[CS_PREFIXES[name[:2]]][pid] = length
            elif name[:2] in SC_PREFIXES:
                sc[SC_PREFIXES[name[:2]]][pid] = length
        elif kind == "db" and rest[2] not in ("nullptr", "NULL", "0"):
            cs["map"][int(rest[0])] = int(rest[1])  # last write wins, as in packetdb_readdb

    client: dict[int, int] = {}
    for line in rp.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"[0-9A-Fa-f]{4}", parts[0]):
            client[int(parts[0], 16)] = int(parts[1])

    entries: list[dict[str, object]] = []
    disagreements: list[str] = []
    for direction, table in (("cs", cs), ("sc", sc)):
        for server, ids in table.items():
            for pid, length in sorted(ids.items()):
                other = client.get(pid)
                if other is not None and other != length:
                    disagreements.append(f"{direction}:{server}:{pid:#06x}:{length}!={other}")
                entries.append({"server": server, "dir": direction, "id": pid, "len": length,
                                "source": "rathena"})  # fmt: skip
    gaps = [("login", "cs", cs), ("char", "cs", cs)] + [
        (s, "sc", sc) for s in ("login", "char", "map")
    ]
    for server, direction, table in gaps:  # gaps from the client's own table
        for pid, length in sorted(client.items()):
            if pid not in table[server]:
                entries.append({"server": server, "dir": direction, "id": pid, "len": length,
                                "source": "openkore"})  # fmt: skip

    fatal = sorted({d for d in disagreements if int(d.split(":")[2], 16) in DECODED})
    doc = {"rathena_ref": ra["ref"], "packetver": lock["packetver"], "prere": lock["prere"],
           "openkore_commit": ok_["commit"], "entries": entries}  # fmt: skip
    body = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    out_sha = hashlib.sha256(body).hexdigest()
    counts = {k: sum(1 for e in entries if e["source"] == k) for k in ("rathena", "openkore")}
    print(f"rathena pairs {len(pairs)}, entries {counts}, disagreements {len(disagreements)}, "
          f"fatal (decoded ids) {len(fatal)}")  # fmt: skip
    for d in fatal:
        print("  FATAL", d)
    if fatal:
        return 1
    if args.update_lock:
        inputs["rathena"]["sha256"], inputs["openkore_recvpackets"]["sha256"] = got_ra, got_ok
        lock.update({"output_sha256": out_sha, "disagreements": sorted(disagreements)})
        LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    else:
        if sorted(disagreements) != lock.get("disagreements") and not args.accept_drift:
            print("disagreement set differs from the lock (drift): --update-lock to accept")
            return 1
        if out_sha != lock.get("output_sha256"):
            print(f"output checksum {out_sha} != lock {lock.get('output_sha256')}")
            return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(body)
    print(f"wrote {OUT.relative_to(REPO)} sha256 {out_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
