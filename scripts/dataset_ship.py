#!/usr/bin/env python3
"""Ship recorded sessions from the VM's local disk to the TrueNAS cold store (ADR-0010).

    dataset_ship.py ship [SESSION ...] [--root DIR] [--dest DIR] [--force-market]
    dataset_ship.py status [--root DIR] [--dest DIR]
    dataset_ship.py prune [--older-than 365d] [--apply] [--dest DIR]
    dataset_ship.py pin SESSION_ID --reason TEXT [--dest DIR]
    dataset_ship.py mark-invalid SESSION_ID --reason TEXT [--dest DIR]

Where things live:
* Local root (record_session.py's default --out): /home/batt/poring-lab-rec. It is on the disk
  shared with live capture, so it is a BUFFER, capped: recording refuses / stops when the
  filesystem has < 140 GB free or > 20 GB of sessions are still unshipped (local_caps()).
* NAS root: /mnt/poring-lab-datasets (NFS, docs/operations/nas-sink.md). Written host-side only.
  It was never mounted into a container (an NFS hang must not freeze a lab service) until Batt's
  decision 4 (2026-10-04): vision alone mounts it READ-ONLY, soft (compose `datasets-nas`), for
  training; no lab service writes through it.

ship, per session (one with a manifest.json: a finished recording), in this order:
  1. sha256 of every file except the manifest -> checksums.sha256 (sha256sum format);
  2. rsync -a --partial --timeout=60 --bwlimit to <dest>/<session_id>/, at ionice -c3, stopped by
     the quant IO guard on a breach (a re-run resumes: --partial). The guard's rule follows --root
     (guard_rule, Batt 2026-10-29): above 30 % for 30 s only when the sessions are on tmpfs, the
     tolerant rule (above 10 % for 30 s, or above 25 % once) on a disk;
  3. re-hash on the NAS: every file must match, and the manifest must arrive byte-identical;
  4. the NAS manifest gets storage: {nas_path, verified_at, files, bytes, checksums_sha256};
  5. one line appended to <dest>/INDEX.jsonl (where each session lives);
  6. ONLY THEN the local copy is deleted. With --keep-local (2026-10-09: banking the tmpfs demo
     sessions, which the scorers and the labels-v2 tools still read) step 6 is skipped.
  Any failure before 6 keeps the local copy. Refused during SET hours (09:30-17:00 Asia/Bangkok,
  weekdays: the quant stack's busy window) unless --force-market, and when --dest is not a
  mounted filesystem (the NAS is down: never fill the empty mount-point directory instead).

prune: NAS sessions older than --older-than (default 365d, from the session id's timestamp). DRY RUN
unless --apply. A `pin` file in a session directory (benchmark evidence, hand-labelled sets)
means never pruned; `pin` writes one with its reason.

The manifest is excluded from checksums.sha256 because step 4 rewrites it; its integrity is
checked byte-for-byte in step 3 instead, and storage.checksums_sha256 chains to the data files.

mark-invalid (Post-S2 round B6', 2026-10-04): a shipped session whose LABELS are known wrong (the
indoor set fitted with the outdoor camera) is marked in its NAS manifest -- "validity": {status
INVALID, reason, marked_at} -- and in INDEX.jsonl. It is KEPT (Batt: keep it): the data files and
their checksums are untouched; qa_export refuses it unless told otherwise.
"""

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROOT = Path("/home/batt/poring-lab-rec")
NAS_ROOT = Path("/mnt/poring-lab-datasets")
MIN_FREE_BYTES = 140 * 10**9
MAX_UNSHIPPED_BYTES = 20 * 10**9
BWLIMIT_KBPS = 40000  # rsync --bwlimit (KiB/s): ~40 MB/s, a fraction of the disk's throughput
RETENTION_DAYS = 365
CHECKSUMS = "checksums.sha256"
MANIFEST = "manifest.json"
INDEX = "INDEX.jsonl"
PIN = "pin"
BANGKOK = ZoneInfo("Asia/Bangkok")
SESSION_TIME = re.compile(r"^(\d{8}T\d{6})-")


class Refused(Exception):
    """A precondition failed: nothing was changed."""


def now() -> dt.datetime:
    """The wall clock (tests replace it)."""
    return dt.datetime.now(tz=BANGKOK)


def in_set_hours(when: dt.datetime | None = None) -> bool:
    """SET's trading window, 09:30-17:00 Bangkok time, Monday to Friday (holidays not modelled)."""
    t = (when or now()).astimezone(BANGKOK)
    return t.weekday() < 5 and dt.time(9, 30) <= t.time() < dt.time(17, 0)


# --- local caps (record_session.py uses these too) ------------------------------------------------


def tree_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def free_bytes(path: Path) -> int:
    """Free space on the filesystem holding ``path`` (or its nearest existing parent)."""
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    st = os.statvfs(probe)
    return st.f_bavail * st.f_frsize


def unshipped_bytes(root: Path) -> int:
    """Everything under the local root is unshipped: ship deletes what it has verified."""
    return tree_bytes(root) if root.exists() else 0


def local_caps(
    root: Path,
    *,
    min_free: int = MIN_FREE_BYTES,
    max_unshipped: int = MAX_UNSHIPPED_BYTES,
    extra: int = 0,
    unshipped: int | None = None,
) -> str | None:
    """Why recording into ``root`` must not start / continue, or None. ``extra``: bytes the running
    recording has added since ``unshipped`` was measured (so the tree isn't walked every frame)."""
    free = free_bytes(root)
    if free < min_free:
        return f"only {free / 1e9:.0f} GB free under {root} (floor {min_free / 1e9:.0f} GB)"
    pending = (unshipped_bytes(root) if unshipped is None else unshipped) + extra
    if pending > max_unshipped:
        return (
            f"{pending / 1e9:.1f} GB unshipped under {root} (cap {max_unshipped / 1e9:.0f} GB): "
            "run scripts/dataset_ship.py ship"
        )
    return None


# --- sessions ------------------------------------------------------------------------------------


def sessions(root: Path) -> list[Path]:
    """Session directories under ``root`` (finished or not), oldest first by name."""
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def finished(session: Path) -> bool:
    return (session / MANIFEST).is_file()


def read_manifest(session: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((session / MANIFEST).read_text())
    return data


def write_manifest(session: Path, manifest: dict[str, Any]) -> None:
    """The same atomic write as poring_dataset.shards.write_manifest (temp file + rename)."""
    tmp = session / f".{MANIFEST}.tmp"
    tmp.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    tmp.replace(session / MANIFEST)


def data_files(session: Path) -> list[str]:
    """Relative POSIX paths of the files checksums.sha256 covers: all but the manifest, the
    checksum file itself and temp files."""
    out = []
    for p in session.rglob("*"):
        rel = p.relative_to(session).as_posix()
        keep = rel not in (MANIFEST, CHECKSUMS) and not p.name.startswith(".")
        if keep and p.is_file() and not p.is_symlink():
            out.append(rel)
    return sorted(out)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_checksums(session: Path) -> dict[str, str]:
    sums = {rel: sha256_file(session / rel) for rel in data_files(session)}
    text = "".join(f"{digest}  {rel}\n" for rel, digest in sums.items())
    tmp = session / f".{CHECKSUMS}.tmp"
    tmp.write_text(text)
    tmp.replace(session / CHECKSUMS)
    return sums


def read_checksums(path: Path) -> dict[str, str]:
    sums = {}
    for line in path.read_text().splitlines():
        digest, _, rel = line.partition("  ")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not rel:
            raise ValueError(f"malformed line in {path}: {line[:80]!r}")
        sums[rel] = digest
    return sums


def verify(local: Path, remote: Path, sums: dict[str, str]) -> list[str]:
    """Problems with the NAS copy (empty = verified): every checksummed file re-hashed there, the
    checksum file and the manifest byte-identical to the local ones."""
    problems = []
    for rel, digest in sums.items():
        target = remote / rel
        if not target.is_file():
            problems.append(f"missing on the NAS: {rel}")
        elif sha256_file(target) != digest:
            problems.append(f"checksum mismatch on the NAS: {rel}")
    for name in (CHECKSUMS, MANIFEST):
        target = remote / name
        if not target.is_file() or target.read_bytes() != (local / name).read_bytes():
            problems.append(f"{name} differs on the NAS")
    return problems


# --- transfer ------------------------------------------------------------------------------------


Guard = Any  # guarded_build.Guard: breach() -> (cgroup, pct, rule) | None


# The IO rule by where the data sits (Batt 2026-10-28 ~13:2x, gef10-detector.md 13y; moved here from
# record_session.py 2026-10-29, which re-exports it): data in RAM puts nothing on the disk shared
# with capture, so its job stops only on SUSTAINED stall (above 30 % for 30 s); the host's own
# 1-5 s bursts tripped the one-spike rule within minutes (10 of 11 hunt recorders on 10-26). Data
# on a disk keeps the tolerant rule (above 10 % for 30 s, or above 25 % once).
# A ship follows its sessions' root (Batt 2026-10-29, rogue-gef10.md AK-4): on 10-28 a ship from
# /dev/shm was cut at 17:04:54 by a 29.0 % quant-postgres spike under the one-spike rule.
DISK_RULE: dict[str, Any] = {"threshold": 10.0, "sustain": 30.0, "spike": 25.0}
RAM_RULE: dict[str, Any] = {"threshold": 30.0, "sustain": 30.0, "spike": None}


def fs_type(path: Path, mounts: str | None = None) -> str:
    """The filesystem type of the mount holding ``path`` (the longest mount-point prefix in
    /proc/mounts); "" when none matches. ``path`` need not exist yet."""
    text = Path("/proc/mounts").read_text() if mounts is None else mounts
    target = str(path.resolve())
    best, fstype = "", ""
    for line in text.splitlines():
        f = line.split()
        if len(f) < 3:
            continue
        mnt = f[1].replace("\\040", " ")
        inside = target == mnt or target.startswith(mnt.rstrip("/") + "/")
        if inside and len(mnt) >= len(best):
            best, fstype = mnt, f[2]
    return fstype


def guard_rule(root: Path, mounts: str | None = None) -> dict[str, Any]:
    """RAM_RULE when ``root`` is on tmpfs, else DISK_RULE (fail safe: unknown = disk)."""
    return RAM_RULE if fs_type(root, mounts) == "tmpfs" else DISK_RULE


def load_guard(root: Path, mounts: str | None = None) -> Guard:
    """The quant IO guard, with the rule for the sessions' root (guard_rule)."""
    spec = importlib.util.spec_from_file_location(
        "guarded_build", ROOT / "scripts" / "guarded_build.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rule = guard_rule(root, mounts)
    return module.Guard(module.cgroup_paths(), rule["threshold"], 10.0, sustain=rule["sustain"],
                        spike=rule["spike"])  # fmt: skip


def rsync_argv(src: Path, dst: Path, bwlimit: int) -> list[str]:
    argv = ["rsync", "-a", "--partial", "--timeout=60", f"--bwlimit={bwlimit}"]
    argv += [f"{src}/", f"{dst}/"]
    if shutil.which("ionice"):
        argv = ["ionice", "-c3", *argv]
    return argv


def transfer(src: Path, dst: Path, bwlimit: int, guard: Guard | None) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen(rsync_argv(src, dst, bwlimit)) as proc:
        while proc.poll() is None:
            hit = guard.breach() if guard is not None else None
            if hit:
                proc.terminate()
                proc.wait(timeout=30)
                raise Refused(f"IO guard: {hit[0]} {hit[1]:.1f}% ({hit[2]}); re-run to resume")
            time.sleep(1.0)
        if proc.returncode != 0:
            raise Refused(f"rsync exited {proc.returncode}; the local copy is kept")


def append_index(dest: Path, record: dict[str, Any]) -> None:
    """One JSON line per event, appended with a single write (this tool is the only writer)."""
    line = (json.dumps(record, sort_keys=True) + "\n").encode()
    fd = os.open(dest / INDEX, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def check_dest(dest: Path, allow_plain_dir: bool) -> None:
    if not dest.is_dir():
        raise Refused(f"{dest} does not exist: is the NAS mounted? (docs/operations/nas-sink.md)")
    if not allow_plain_dir and not os.path.ismount(dest):
        raise Refused(f"{dest} is not a mounted filesystem: the NAS is not mounted")


def ship_one(session: Path, dest: Path, *, bwlimit: int, guard: Guard | None,
             keep_local: bool = False) -> dict[str, Any]:  # fmt: skip
    if not finished(session):
        raise Refused(f"{session.name}: no manifest.json (still recording, or it crashed)")
    manifest = read_manifest(session)
    sid = str(manifest.get("session_id") or session.name)
    remote = dest / sid
    sums = write_checksums(session)  # 1
    transfer(session, remote, bwlimit, guard)  # 2
    problems = verify(session, remote, sums)  # 3
    if problems:
        raise Refused(f"{sid}: NOT verified, local copy kept: " + "; ".join(problems[:5]))
    stamp = now().isoformat(timespec="seconds")
    total = sum((session / rel).stat().st_size for rel in sums)
    storage = {
        "nas_path": str(remote),
        "verified_at": stamp,
        "files": len(sums),
        "bytes": total,
        "checksums_sha256": sha256_file(remote / CHECKSUMS),
    }
    write_manifest(remote, {**manifest, "storage": storage})  # 4
    # 5
    append_index(dest, {"event": "shipped", "session_id": sid, "from": socket.gethostname(),
                        **storage})  # fmt: skip
    if read_manifest(remote).get("storage", {}).get("verified_at") != stamp:
        raise Refused(f"{sid}: the NAS manifest did not keep storage.verified_at; local kept")
    if not keep_local:  # 6 (--keep-local: a working copy stays, e.g. a tmpfs session in use)
        shutil.rmtree(session)
    return {"session_id": sid, "nas_path": str(remote), "files": len(sums), "bytes": total,
            "local_kept": keep_local}  # fmt: skip


@contextlib.contextmanager
def single_run(root: Path) -> Iterator[None]:
    """One ship at a time per local root."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".ship.lock").open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused("another dataset_ship.py ship is running") from None
        yield


def resolve(root: Path, names: list[str]) -> list[Path]:
    if not names:
        return [s for s in sessions(root) if finished(s)]
    out = []
    for name in names:
        path = Path(name)
        path = path if path.is_dir() else root / name
        if not path.is_dir():
            raise Refused(f"no session {name!r} under {root}")
        out.append(path)
    return out


def cmd_ship(a: argparse.Namespace, guard_factory: Callable[[Path], Guard | None]) -> int:
    if in_set_hours() and not a.force_market:
        raise Refused("SET hours (09:30-17:00 Bangkok, weekdays): not shipping (--force-market)")
    check_dest(a.dest, a.dest_is_dir_for_tests)
    todo = resolve(a.root, a.sessions)
    if not todo:
        print("nothing to ship")
        return 0
    rc = 0
    with single_run(a.root):
        guard = guard_factory(a.root)
        if guard is not None:
            print(f"IO guard: {guard.describe()} (sessions under {a.root})", file=sys.stderr)
        for session in todo:
            try:
                print(json.dumps(ship_one(session, a.dest, bwlimit=a.bwlimit, guard=guard,
                                          keep_local=a.keep_local)))  # fmt: skip
            except Refused as exc:
                print(f"KEPT {session.name}: {exc}", file=sys.stderr)
                rc = 1
                if str(exc).startswith("IO guard"):
                    break  # the disk is busy: don't start the next one
    return rc


# --- status / prune / pin -------------------------------------------------------------------------


def session_age_days(session: Path) -> float:
    m = SESSION_TIME.match(session.name)
    if m:
        started = dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=BANGKOK)
    else:
        started = dt.datetime.fromtimestamp(session.stat().st_mtime, tz=BANGKOK)
    return (now() - started).total_seconds() / 86400


def human(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 10**8 else f"{n / 1e6:.1f} MB"


def cmd_status(a: argparse.Namespace) -> int:
    rows = []
    for s in sessions(a.root):
        state = "unshipped" if finished(s) else "recording/incomplete"
        rows.append((s.name, "local", state, tree_bytes(s), ""))
    mounted = a.dest.is_dir() and (a.dest_is_dir_for_tests or os.path.ismount(a.dest))
    if mounted:
        for s in sessions(a.dest):
            m = read_manifest(s) if finished(s) else {}
            verified = m.get("storage", {}).get("verified_at")
            state = f"verified {verified}" if verified else "UNVERIFIED"
            note = "pinned" if (s / PIN).exists() else ""
            rows.append((s.name, "nas", state, tree_bytes(s), note))
    for name, where, state, size, note in rows:
        print(f"{name:44} {where:5} {state:36} {human(size):>10} {note}".rstrip())
    pending = unshipped_bytes(a.root)
    print(
        f"local {a.root}: {human(pending)} unshipped (cap {human(a.max_unshipped)}), "
        f"{human(free_bytes(a.root))} free (floor {human(a.min_free)})"
    )
    print(f"nas {a.dest}: " + ("mounted" if mounted else "NOT mounted"))
    return 0


def parse_days(text: str) -> float:
    m = re.fullmatch(r"(\d+)d", text)
    if m is None:
        raise argparse.ArgumentTypeError("use days, e.g. 365d")
    return float(m.group(1))


def cmd_prune(a: argparse.Namespace) -> int:
    check_dest(a.dest, a.dest_is_dir_for_tests)
    for s in sessions(a.dest):
        age = session_age_days(s)
        if age <= a.older_than:
            continue
        if (s / PIN).exists():
            print(f"pinned    {s.name} ({age:.0f} d): kept")
            continue
        if not a.apply:
            print(f"would delete {s.name} ({age:.0f} d, {human(tree_bytes(s))})")
            continue
        size = tree_bytes(s)
        shutil.rmtree(s)
        append_index(a.dest, {"event": "pruned", "session_id": s.name, "bytes": size,
                              "pruned_at": now().isoformat(timespec="seconds")})  # fmt: skip
        print(f"deleted   {s.name} ({age:.0f} d, {human(size)})")
    if not a.apply:
        print("dry run: nothing deleted (--apply to delete)")
    return 0


SIDECAR_NAME = re.compile(r"^packets\.[a-z0-9_]+\.jsonl\.gz$")


def add_sidecar(session: Path, src: Path) -> dict[str, Any]:
    """Add a re-derived file (e.g. packets.states.jsonl.gz, scripts/replay_states.py) to a SHIPPED
    session: copied in under a temporary name, re-hashed ON the NAS, renamed, then its line joins
    checksums.sha256 and INDEX.jsonl gets an event. Never replaces a file that is there already:
    the shipped data stays exactly what was verified (2026-10-04, Phase 3 M3)."""
    if not SIDECAR_NAME.match(src.name):
        raise Refused(f"{src.name}: a sidecar is packets.<kind>.jsonl.gz")
    if not (session / CHECKSUMS).is_file():
        raise Refused(f"{session.name} has no {CHECKSUMS}: not a shipped session")
    dest = session / src.name
    if dest.exists():
        raise Refused(f"{dest} exists: a sidecar is never replaced")
    want = sha256_file(src)
    tmp = session / f".{src.name}.part"
    shutil.copyfile(src, tmp)
    if sha256_file(tmp) != want:  # read back from the NAS
        tmp.unlink()
        raise Refused(f"{src.name}: the NAS copy hashes differently")
    tmp.replace(dest)
    sums = read_checksums(session / CHECKSUMS)
    sums[src.name] = want
    text = "".join(f"{digest}  {rel}\n" for rel, digest in sums.items())
    part = session / f".{CHECKSUMS}.tmp"
    part.write_text(text)
    part.replace(session / CHECKSUMS)
    if read_checksums(session / CHECKSUMS).get(src.name) != want:
        raise Refused("checksums.sha256 did not read back")
    record = {"event": "sidecar", "session_id": session.name, "file": src.name,
              "sha256": want, "bytes": dest.stat().st_size,
              "added_at": now().isoformat(timespec="seconds")}  # fmt: skip
    append_index(session.parent, record)
    return record


def cmd_pin(a: argparse.Namespace) -> int:
    check_dest(a.dest, a.dest_is_dir_for_tests)
    session = a.dest / a.session
    if not session.is_dir():
        raise Refused(f"no session {a.session!r} on the NAS")
    stamp = now().isoformat(timespec="seconds")
    (session / PIN).write_text(json.dumps({"pinned_at": stamp, "reason": a.reason}) + "\n")
    append_index(a.dest, {"event": "pinned", "session_id": a.session, "reason": a.reason,
                          "pinned_at": stamp})  # fmt: skip
    print(f"pinned {a.session}")
    return 0


def cmd_mark_invalid(a: argparse.Namespace) -> int:
    check_dest(a.dest, a.dest_is_dir_for_tests)
    session = a.dest / a.session
    if not (session / MANIFEST).is_file():
        raise Refused(f"no shipped session {a.session!r} on the NAS")
    stamp = now().isoformat(timespec="seconds")
    manifest = read_manifest(session)
    manifest["validity"] = {"status": "INVALID", "reason": a.reason, "marked_at": stamp}
    write_manifest(session, manifest)
    if read_manifest(session).get("validity", {}).get("status") != "INVALID":
        raise Refused(f"{a.session}: the manifest did not read back INVALID")
    append_index(a.dest, {"event": "invalidated", "session_id": a.session, "reason": a.reason,
                          "marked_at": stamp})  # fmt: skip
    print(f"marked INVALID {a.session} (kept; data files untouched)")
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=LOCAL_ROOT, help="local session root")
    common.add_argument("--dest", type=Path, default=NAS_ROOT, help="NAS session root")
    common.add_argument("--dest-is-dir-for-tests", action="store_true", help=argparse.SUPPRESS)
    ship = sub.add_parser("ship", parents=[common])
    ship.add_argument("sessions", nargs="*", help="session ids or paths (default: all finished)")
    ship.add_argument("--force-market", action="store_true", help="ship during SET hours")
    ship.add_argument("--keep-local", action="store_true",
                      help="keep the local copy after the verified NAS copy")  # fmt: skip
    ship.add_argument("--bwlimit", type=int, default=BWLIMIT_KBPS, help="rsync --bwlimit, KiB/s")
    ship.add_argument("--no-io-guard", action="store_true", help=argparse.SUPPRESS)
    status = sub.add_parser("status", parents=[common])
    status.add_argument("--min-free", type=int, default=MIN_FREE_BYTES, help=argparse.SUPPRESS)
    status.add_argument("--max-unshipped", type=int, default=MAX_UNSHIPPED_BYTES,
                        help=argparse.SUPPRESS)  # fmt: skip
    prune = sub.add_parser("prune", parents=[common])
    prune.add_argument("--older-than", type=parse_days, default=float(RETENTION_DAYS))
    prune.add_argument("--apply", action="store_true", help="really delete (default: dry run)")
    pin = sub.add_parser("pin", parents=[common])
    pin.add_argument("session")
    pin.add_argument("--reason", required=True)
    invalid = sub.add_parser("mark-invalid", parents=[common])
    invalid.add_argument("session")
    invalid.add_argument("--reason", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        if a.cmd == "ship":
            return cmd_ship(a, (lambda _root: None) if a.no_io_guard else load_guard)
        if a.cmd == "status":
            return cmd_status(a)
        if a.cmd == "prune":
            return cmd_prune(a)
        if a.cmd == "mark-invalid":
            return cmd_mark_invalid(a)
        return cmd_pin(a)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
