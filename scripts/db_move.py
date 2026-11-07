#!/usr/bin/env python3
"""Move the lab's MariaDB (accounts, characters, inventories, the chat log) from ubuntu-docker to
bot-server, byte for byte (docs/planning/bot-server-cutover.md Phase B 2-3).

    python3 scripts/db_move.py dump --out /dev/shm/poring-lab-tmp/migr/db.sql      # ubuntu-docker
    scp -p that file to bot-server's /dev/shm/poring-lab-tmp/migr/
    python3 scripts/db_move.py restore --in /dev/shm/poring-lab-tmp/migr/db.sql    # bot-server
    python3 scripts/migration_check.py check ... --phase final   # row counts + CHECKSUM TABLE

- The dump is `mariadb-dump --single-transaction --default-character-set=binary`: the bytes as
  stored (Thai is tis620 end to end; `chatlog.message` is VARBINARY), never re-encoded.
- The file holds the accounts' password hashes: mode 600, in RAM (/dev/shm), and deleted by the
  caller once the check passes (a gated delete). The root password goes to the client on stdin as
  an option file, never on an argv.
- restore stops nothing itself: rathena and its sniffer must be stopped first (the script refuses
  while rathena runs), and started again after.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migration_check as mc  # noqa: E402

DB = "poring-lab-db-1"
RATHENA = "poring-lab-rathena-1"
IN_CONTAINER = "/tmp/poring-lab-move.sql"


def option_file(env: dict[str, str]) -> str:
    """PURE: the client option file with the root password (sent on stdin)."""
    return f"[client]\nuser=root\npassword={env.get('DB_ROOT_PASSWORD', '')}\n"


def dump_cmd(db: str) -> list[str]:
    """PURE: a consistent, byte-exact dump of the lab database (schema + data + routines)."""
    return ["docker", "exec", "-i", DB, "mariadb-dump", "--defaults-extra-file=/dev/stdin",
            "--single-transaction", "--default-character-set=binary", "--routines", "--triggers",
            "--events", "--hex-blob", "--databases", db]  # fmt: skip


def restore_cmd() -> list[str]:
    """PURE: replay the copied dump inside the db container, bytes as dumped."""
    return ["docker", "exec", "-i", DB, "mariadb", "--defaults-extra-file=/dev/stdin",
            "--default-character-set=binary", "-e", f"source {IN_CONTAINER}"]  # fmt: skip


def running(name: str) -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name],
                       capture_output=True, text=True, check=False)  # fmt: skip
    return r.stdout.strip() == "true"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("restore")
    r.add_argument("--in", dest="src", type=Path, required=True)
    a = ap.parse_args(argv)
    env = mc.parse_env((mc.REPO / ".env").read_text())
    db = env.get("DB_NAME", "ragnarok")
    if a.cmd == "dump":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            p = subprocess.run(dump_cmd(db), input=option_file(env).encode(), stdout=fh,
                               stderr=subprocess.PIPE, check=False)  # fmt: skip
        if p.returncode != 0:
            print(f"dump FAILED rc {p.returncode}: {p.stderr.decode(errors='replace')[:300]}")
            return 1
        tail = a.out.read_bytes()[-200:].decode(errors="replace")
        ok = "Dump completed" in tail
        print(f"dump {a.out}: {a.out.stat().st_size} bytes, sha256 {mc.sha256_file(a.out)[:12]}, "
              f"{'complete' if ok else 'NO completion line'}")  # fmt: skip
        return 0 if ok else 1
    if running(RATHENA):
        print(f"restore REFUSED: {RATHENA} is running (stop rathena and the sniffer first)")
        return 3
    print(f"restore {a.src}: {a.src.stat().st_size} bytes, sha256 {mc.sha256_file(a.src)[:12]}")
    cp = subprocess.run(["docker", "cp", str(a.src), f"{DB}:{IN_CONTAINER}"],
                        capture_output=True, text=True, check=False)  # fmt: skip
    if cp.returncode != 0:
        print(f"docker cp FAILED: {cp.stderr.strip()[:200]}")
        return 1
    try:
        p2 = subprocess.run(restore_cmd(), input=option_file(env), capture_output=True,
                            text=True, check=False)  # fmt: skip
    finally:
        subprocess.run(["docker", "exec", DB, "rm", "-f", IN_CONTAINER], check=False)
    print(f"restore rc {p2.returncode} {(p2.stdout + p2.stderr).strip()[:300]}")
    return p2.returncode


if __name__ == "__main__":
    raise SystemExit(main())
