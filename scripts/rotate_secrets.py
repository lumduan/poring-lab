#!/usr/bin/env python3
"""Rotate lab secrets in .env without ever printing them (or putting them on an argv).

    rotate_secrets.py rotate VAR [VAR ...]
    rotate_secrets.py set NAME=value [...]     non-secret settings only (refuses secret names)

Known variables and their generators:
    DB_PASSWORD, DB_ROOT_PASSWORD   hex32. The running MariaDB is changed FIRST (ALTER USER for
                                    ragnarok@% / root@localhost / root@%, authenticated with the
                                    db container's current root password, SQL on stdin), and each
                                    new password is verified with a fresh login (option file on
                                    stdin) before .env is touched.
    RATHENA_SERVER_PASSWORD         hex23 (char/map keep it in 24-byte buffers).
    RATHENA_TEST_PASSWORD           16 alphanumerics (rathena's entrypoint rule).
    WIN_LAB_PASSWORD                20 alphanumerics, at least one upper, lower and digit
                                    (Windows complexity).
    The Thai-data experiment's rathena-th + db-th (2026-10-05), FIRST-TIME ONLY (refused once its
    db-th container exists: rotating a live database's password is not implemented for it):
    DB_TH_PASSWORD, DB_TH_ROOT_PASSWORD hex32; RATHENA_TH_SERVER_USER srv_+hex8,
    RATHENA_TH_SERVER_PASSWORD hex23; RATHENA_TH_AGENT_USER tha_+hex8, RATHENA_TH_GM_USER
    thv_+hex8 (login ids live in .env only), RATHENA_TH_{AGENT,GM}_PASSWORD 16 alphanumerics.

.env is rewritten atomically (temp file + rename, mode 600); only variable NAMES are printed.
After rotating DB_* or RATHENA_*: recreate db + rathena (+ the sniffer, which shares rathena's
network namespace), e.g.
    python3 scripts/guarded_build.py --sustain 30 --spike 25 start:db,rathena@180
"""

import argparse
import os
import secrets
import string
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
DB = "poring-lab-db-1"
ALNUM = string.ascii_letters + string.digits


def _alnum(n: int) -> str:
    return "".join(secrets.choice(ALNUM) for _ in range(n))


def _complex(n: int) -> str:
    while True:
        v = _alnum(n)
        if (
            any(c.islower() for c in v)
            and any(c.isupper() for c in v)
            and any(c.isdigit() for c in v)
        ):
            return v


GENERATORS: dict[str, Callable[[], str]] = {
    "DB_PASSWORD": lambda: secrets.token_hex(16),
    "DB_ROOT_PASSWORD": lambda: secrets.token_hex(16),
    "RATHENA_SERVER_PASSWORD": lambda: secrets.token_hex(16)[:23],
    "RATHENA_TEST_PASSWORD": lambda: _alnum(16),
    "WIN_LAB_PASSWORD": lambda: _complex(20),
    # rathena-th / db-th (first-time only, see TH_FIRST_TIME)
    "DB_TH_PASSWORD": lambda: secrets.token_hex(16),
    "DB_TH_ROOT_PASSWORD": lambda: secrets.token_hex(16),
    "RATHENA_TH_SERVER_USER": lambda: "srv_" + secrets.token_hex(4),
    "RATHENA_TH_SERVER_PASSWORD": lambda: secrets.token_hex(16)[:23],
    "RATHENA_TH_AGENT_USER": lambda: "tha_" + secrets.token_hex(4),
    "RATHENA_TH_AGENT_PASSWORD": lambda: _alnum(16),
    "RATHENA_TH_GM_USER": lambda: "thv_" + secrets.token_hex(4),
    "RATHENA_TH_GM_PASSWORD": lambda: _alnum(16),
}
TH_FIRST_TIME = frozenset(n for n in GENERATORS if n.startswith(("DB_TH_", "RATHENA_TH_")))
DB_TH = "poring-lab-db-th-1"


def container_exists(name: str) -> bool:
    r = subprocess.run(["docker", "container", "inspect", name], capture_output=True)
    return r.returncode == 0


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v
    return out


def rewrite_env(text: str, updates: dict[str, str]) -> str:
    """Replace `KEY=...` lines in place (first occurrence; comments untouched), append missing
    keys at the end. Values never contain newlines (the generators guarantee it)."""
    lines = text.splitlines()
    done: set[str] = set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates and key not in done:
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    return "\n".join(lines) + "\n"


def write_env_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".env.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _db_exec(script: str, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "exec", "-i", DB, "sh", "-c", script],
        input=stdin, capture_output=True, text=True,
    )  # fmt: skip


def _login_ok(user: str, password: str) -> bool:
    cnf = f"[client]\nuser={user}\npassword={password}\n"
    r = _db_exec('exec mariadb --defaults-extra-file=/dev/stdin -N -e "SELECT 1"', cnf)
    return r.returncode == 0 and r.stdout.strip() == "1"


def alter_db(new: dict[str, str]) -> None:
    """Change the running MariaDB first; .env is only written if this succeeds."""
    stmts = []
    if "DB_PASSWORD" in new:
        stmts.append(f"ALTER USER 'ragnarok'@'%' IDENTIFIED BY '{new['DB_PASSWORD']}';")
    if "DB_ROOT_PASSWORD" in new:
        for host in ("localhost", "%"):
            stmts.append(f"ALTER USER 'root'@'{host}' IDENTIFIED BY '{new['DB_ROOT_PASSWORD']}';")
    stmts.append("FLUSH PRIVILEGES;")
    r = _db_exec('MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot', "\n".join(stmts))
    if r.returncode != 0:
        sys.exit(f"ALTER USER failed (exit {r.returncode}); .env unchanged")
    if "DB_PASSWORD" in new and not _login_ok("ragnarok", new["DB_PASSWORD"]):
        sys.exit("new ragnarok password does not log in; .env unchanged -- investigate before use")
    if "DB_ROOT_PASSWORD" in new and not _login_ok("root", new["DB_ROOT_PASSWORD"]):
        sys.exit("new root password does not log in; .env unchanged -- investigate before use")


def write_verified(env_path: Path, updates: dict[str, str]) -> None:
    """Rewrite .env, then READ IT BACK: every updated key must parse to exactly its new value."""
    write_env_atomic(env_path, rewrite_env(env_path.read_text(), updates))
    back = parse_env(env_path.read_text())
    wrong = [k for k, v in updates.items() if back.get(k) != v]
    if wrong:
        sys.exit(f"read-back mismatch after writing .env: {wrong}")


SECRET_HINTS = ("PASSWORD", "SECRET", "TOKEN", "KEY", "_USER")


def set_values(pairs: list[str], env_path: Path = ENV) -> list[str]:
    """Non-secret settings (e.g. RDP_GFX=progressive, GAME_REGION=...), verified by read-back.
    Secret-looking names are refused: those are generated by `rotate`, never typed."""
    updates: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or not name or "\n" in value:
            sys.exit(f"expected NAME=value, got {pair!r}")
        if name in GENERATORS or any(h in name.upper() for h in SECRET_HINTS):
            sys.exit(f"{name} looks secret: use `rotate`, never type a secret")
        updates[name] = value
    write_verified(env_path, updates)
    return list(updates)


def rotate(names: list[str], env_path: Path = ENV) -> list[str]:
    unknown = [n for n in names if n not in GENERATORS]
    if unknown:
        sys.exit(f"no generator for {unknown}; known: {sorted(GENERATORS)}")
    if TH_FIRST_TIME & set(names) and container_exists(DB_TH):
        sys.exit(f"{DB_TH} exists: the TH secrets are first-time only (its database already holds "
                 "them); .env unchanged")  # fmt: skip
    new = {n: GENERATORS[n]() for n in names}
    if {"DB_PASSWORD", "DB_ROOT_PASSWORD"} & new.keys():
        alter_db({k: v for k, v in new.items() if k.startswith("DB_")})
    write_verified(env_path, new)
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rotate")
    r.add_argument("names", nargs="+")
    st = sub.add_parser("set")
    st.add_argument("pairs", nargs="+", metavar="NAME=value")
    a = ap.parse_args()
    if a.cmd == "set":
        print("set in .env and read back:", " ".join(set_values(a.pairs)))
        return
    changed = rotate(a.names)
    print("rotated in .env and read back (values not shown):", " ".join(changed))


if __name__ == "__main__":
    main()
