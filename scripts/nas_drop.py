#!/usr/bin/env python3
"""Temporary, least-privilege SMB drops on the NAS for the Dell, with read-backs (Batt, 2026-10-03;
docs/operations/nas-sink.md section 5). Stdlib only; runs `midclt` over `ssh root@192.168.1.6`.

    nas_drop.py open NAME --dataset tank-main/poring-lab/<ds> [--subdir P] --host IP [--rw]
                [--unlock]
        One AUTHENTICATED share (the NAS user's own credentials; never guest -- Windows 11 refuses
        guest SMB anyway, error 1272): read-only unless --rw, not browsable, hostsallow IP,
        hostsdeny ALL, tagged with the nas_drop marker. --rw on a readonly dataset needs
        --unlock: a snapshot `pre-drop-<stamp>` FIRST, then readonly OFF, each read back.
    nas_drop.py close NAME [--lock]
        Deletes ONLY a share carrying the marker; reads back that it is gone and lists any SMB
        session still on it. --lock: readonly ON + `@pristine-<stamp>` on its dataset, read back.
    nas_drop.py status
        The marked shares that are open now.

Every open/close takes a Frigate reading (docker inspect StartedAt/RestartCount on the NAS) before
and after: the pool also holds every app's data. Prints JSON (ids, flags, readings), never data.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import subprocess
import sys
import time
from typing import Any

NAS = "root@192.168.1.6"
ROOT_DS = "tank-main/poring-lab"
MARKER = "TEMPORARY poring-lab nas_drop"
FRIGATE = "ix-frigate-frigate-1"
NAME_RE = re.compile(r"^poring-[a-z0-9-]{1,40}$")


class DropError(SystemExit):
    def __init__(self, msg: str) -> None:
        super().__init__(f"STOP: {msg}")


def nas(cmd: str) -> str:
    res = subprocess.run(["ssh", "-o", "ConnectTimeout=10", NAS, cmd], capture_output=True,
                         text=True, timeout=120, check=False)  # fmt: skip
    if res.returncode != 0:
        raise DropError(f"NAS command failed ({res.returncode}): {cmd[:80]}: {res.stderr.strip()}")
    return res.stdout


def midclt(method: str, *args: Any) -> Any:
    out = nas(" ".join(["midclt", "call", method, *(shlex.quote(json.dumps(a)) for a in args)]))
    return json.loads(out) if out.strip() else None


def frigate() -> str:
    fmt = "{{.State.StartedAt}} restarts={{.RestartCount}} {{.State.Status}}"
    return nas(f"docker inspect -f {shlex.quote(fmt)} {FRIGATE}").strip()


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M")


def share(name: str) -> dict[str, Any] | None:
    found = midclt("sharing.smb.query", [["name", "=", name]])
    return found[0] if found else None


def dataset(name: str) -> dict[str, Any]:
    found = midclt("pool.dataset.query", [["id", "=", name]])
    if not found:
        raise DropError(f"no dataset {name}")
    return found[0]  # type: ignore[no-any-return]


def is_readonly(ds: dict[str, Any]) -> bool:
    return str(ds["readonly"]["value"]).upper() == "ON"


def snapshot(ds_name: str, snap: str) -> None:
    midclt("zfs.snapshot.create", {"dataset": ds_name, "name": snap})
    listed = nas(f"zfs list -H -o name -t snapshot {shlex.quote(f'{ds_name}@{snap}')}").strip()
    if listed != f"{ds_name}@{snap}":
        raise DropError(f"snapshot {ds_name}@{snap} not read back")


def set_readonly(ds_name: str, on: bool) -> None:
    midclt("pool.dataset.update", ds_name, {"readonly": "ON" if on else "OFF"})
    if is_readonly(dataset(ds_name)) != on:
        raise DropError(f"{ds_name} readonly did not read back {'ON' if on else 'OFF'}")


def cmd_open(name: str, ds_name: str, subdir: str, host: str, rw: bool, unlock: bool) -> int:
    if not NAME_RE.match(name):
        raise DropError(f"share names are poring-<a-z0-9->: {name!r}")
    if not ds_name.startswith(ROOT_DS + "/"):
        raise DropError(f"only datasets under {ROOT_DS}/ ({ds_name})")
    if subdir.startswith("/") or ".." in subdir.split("/"):
        raise DropError(f"--subdir must be relative, without '..' ({subdir})")
    ipaddress.IPv4Address(host)
    if share(name) is not None:
        raise DropError(f"a share named {name} already exists")
    ds = dataset(ds_name)
    path = ds["mountpoint"] + (f"/{subdir}" if subdir else "")
    nas(f"test -d {shlex.quote(path)}")
    before = frigate()
    unlocked = None
    if rw and is_readonly(ds):
        if not unlock:
            raise DropError(f"{ds_name} is readonly: --rw needs --unlock (snapshot first)")
        unlocked = f"pre-drop-{stamp()}"
        snapshot(ds_name, unlocked)  # BEFORE anything can be written
        set_readonly(ds_name, False)
    spec = {
        "name": name, "path": path, "purpose": "MULTI_PROTOCOL_NFS", "ro": not rw,
        "guestok": False, "browsable": False, "hostsallow": [host], "hostsdeny": ["ALL"],
        "comment": f"{MARKER}: {name} for {host}, {time.strftime('%F %T')}; "
                   f"close with nas_drop.py close {name}",
    }  # fmt: skip
    midclt("sharing.smb.create", spec)
    back = share(name)
    wanted = {k: spec[k] for k in ("path", "ro", "guestok", "browsable", "hostsallow", "hostsdeny")}
    if back is None or any(back.get(k) != v for k, v in wanted.items()) or not back.get("enabled"):
        raise DropError(f"share {name} did not read back as created: {back}")
    result = {"opened": name, "id": back["id"], **wanted, "unlocked_after_snapshot": unlocked}
    print(json.dumps({**result, "frigate_before": before, "frigate_after": frigate()}, indent=1))
    return 0


def dataset_of(path: str) -> str:
    """The deepest poring-lab dataset whose mountpoint holds ``path``."""
    found = midclt("pool.dataset.query", [["id", "^", ROOT_DS + "/"]])
    best = ""
    for ds in found or []:
        mp = ds["mountpoint"]
        if (path == mp or path.startswith(mp + "/")) and len(ds["id"]) > len(best):
            best = ds["id"]
    if not best:
        raise DropError(f"no {ROOT_DS} dataset holds {path}")
    return best


def cmd_close(name: str, lock: bool) -> int:
    found = share(name)
    if found is None:
        print(json.dumps({"closed": name, "note": "no such share (already closed)"}))
        return 0
    if MARKER not in str(found.get("comment", "")):
        raise DropError(f"share {name} is not a nas_drop share: never touched")
    before = frigate()
    midclt("sharing.smb.delete", found["id"])
    if share(name) is not None:
        raise DropError(f"share {name} still exists after the delete")
    sessions = [ln for ln in nas("smbstatus -S || true").splitlines() if name in ln]
    locked = None
    if lock:
        ds_name = dataset_of(found["path"])
        set_readonly(ds_name, True)
        locked = f"{ds_name}@pristine-{stamp()}"
        snapshot(ds_name, locked.split("@", 1)[1])
    print(json.dumps({"closed": name, "id": found["id"], "sessions_left": sessions,
                      "locked": locked, "frigate_before": before, "frigate_after": frigate()},
                     indent=1))  # fmt: skip
    return 0


def cmd_status() -> int:
    shares = midclt("sharing.smb.query") or []
    open_ = [{k: s.get(k) for k in ("id", "name", "path", "ro", "hostsallow")}
             for s in shares if MARKER in str(s.get("comment", ""))]  # fmt: skip
    print(json.dumps({"open_drops": open_}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    op = sub.add_parser("open")
    op.add_argument("name")
    op.add_argument("--dataset", required=True)
    op.add_argument("--subdir", default="")
    op.add_argument("--host", required=True)
    op.add_argument("--rw", action="store_true")
    op.add_argument("--unlock", action="store_true")
    cl = sub.add_parser("close")
    cl.add_argument("name")
    cl.add_argument("--lock", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "open":
        return cmd_open(a.name, a.dataset, a.subdir, a.host, a.rw, a.unlock)
    if a.cmd == "close":
        return cmd_close(a.name, a.lock)
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
