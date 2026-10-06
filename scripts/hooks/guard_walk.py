#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash): no filesystem WALKS outside the repo and RAM filesystems.

Why (CLAUDE.md rule 5; Batt, 2026-10-06): this host's root disk is ONE virtual disk shared with
live quant capture, and /mnt holds the NAS automounts. A `find /` ran on it three times; memory
notes did not stop the repeats, so this refuses them mechanically, like guard_docker.py and
guard_bigread.py.

A WALKER is
  find, du, rg, ag, fd/fdfind, tree, `ls -R`, and grep/egrep/fgrep/zgrep with -r/-R/
  --recursive/--dereference-recursive/-d recurse.
Its ROOTS are its path operands (default "."), resolved against the command's cwd: ~, $HOME and
$PWD are expanded; a glob is cut at its first wildcard (never expanded: listing /mnt/* would
trigger the automounts); then realpath.

REFUSES (exit 2, reason on stderr) a walker whose root
  1. is / itself;
  2. is /mnt or anything under it (the NAS automounts);
  3. is on a network or automount filesystem (nfs, nfs4, cifs, smb3, sshfs, autofs, …);
  4. is on a disk-backed filesystem (the root LV, Docker's overlays on it, the other local disk)
     and NOT inside the repo -- RAM filesystems (/dev/shm, /run, /proc …) are fine;
  5. cannot be seen ($VAR other than HOME/PWD, $(…)): a walk whose root is unknown is refused.
ALLOWS every walk inside the repo (no symlink in it leads out, checked 2026-10-06) and on RAM
filesystems; and every non-walking command (ls, stat, findmnt, df, git ls-files …).

SEES THROUGH what the other hooks see through (scripts/hooks/_shell.py: ; && | ( ) $( ),
wrappers like sudo/nice/timeout, `bash -c`, heredocs fed to a shell). CANNOT SEE: walks by a
program (`python -c 'os.walk("/")'`), `xargs` feeding paths, tar/rsync/cp -r -- the stated
boundary; don't route around it.

FAIL DIRECTION: unreadable hook input or an unparsable command -> allow (a guard that blocks
every Bash call is worse; guard_docker.py keeps its own regex fallback).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # see guard_docker.py: never fail open
from _shell import SHELLS, segments, strip_heredocs, unwrap  # noqa: E402

GREPS = frozenset({"grep", "egrep", "fgrep", "zgrep"})
WALKERS = frozenset({"find", "du", "rg", "ag", "fd", "fdfind", "tree", "ls"}) | GREPS
NETWORK = frozenset(
    {"nfs", "nfs4", "cifs", "smb3", "smbfs", "9p", "fuse.sshfs", "sshfs", "autofs", "ceph",
     "glusterfs", "fuse.rclone", "davfs", "fuse.davfs", "afs", "lustre"}
)  # fmt: skip
RAM = frozenset(
    {"tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue",
     "securityfs", "debugfs", "tracefs", "pstore", "bpf", "efivarfs", "configfs", "fusectl",
     "hugetlbfs", "binfmt_misc", "nsfs"}
)  # fmt: skip
# Options that take a VALUE (the next word when not attached), per tool; anything else is a flag.
SHORT_WITH_VALUE = {
    "grep": "efmABCdD", "rg": "efgjmMtTABCrdE", "ag": "ABCGgmp", "fd": "etEdxXjSc",
    "tree": "LPIoHT", "ls": "ITw", "du": "dBtX",
}  # fmt: skip
LONG_WITH_VALUE = frozenset(
    {"--regexp", "--file", "--max-count", "--after-context", "--before-context", "--context",
     "--directories", "--devices", "--include", "--exclude", "--exclude-dir", "--label",
     "--glob", "--iglob", "--type", "--type-not", "--type-add", "--type-clear", "--threads",
     "--max-depth", "--maxdepth", "--max-filesize", "--max-columns", "--encoding", "--replace",
     "--context-separator", "--path-separator", "--pre", "--pre-glob", "--sort", "--sortr",
     "--colors", "--engine", "--dfa-size-limit", "--regex-size-limit", "--ignore-file",
     "--field-context-separator", "--field-match-separator", "--extension", "--exec",
     "--exec-batch", "--size", "--changed-within", "--changed-before", "--block-size",
     "--threshold", "--exclude-from", "--time", "--time-style", "--ignore", "--hide", "--width",
     "--tabsize", "--format", "--filelimit", "--charset", "--timefmt", "--search-path"}
)  # fmt: skip
FIND_GLOBAL = frozenset({"-H", "-L", "-P"})
SAFE_HINT = (
    "Walks are allowed inside the repo and on RAM filesystems (/dev/shm). Name a specific path, "
    "or use ls / stat / findmnt / df / git ls-files."
)


def repo_root() -> str:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    base = env if env else str(Path(__file__).resolve().parents[2])
    return os.path.realpath(base)


def mounts() -> list[tuple[str, str]]:
    """(mount point, fs type) from /proc/mounts, in order (a later stacked mount wins)."""
    out: list[tuple[str, str]] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3:
                    out.append((parts[1].replace("\\040", " "), parts[2]))
    except OSError:
        pass
    return out


def fs_type(path: str) -> str:
    """The filesystem type of ``path``: the longest mount-point prefix (the last one wins)."""
    best, kind = "", ""
    for mnt, typ in mounts():
        inside = path == mnt or path.startswith(mnt.rstrip("/") + "/")
        if inside and len(mnt) >= len(best):
            best, kind = mnt, typ
    return kind


def inside(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def resolve(word: str, cwd: str) -> str | None:
    """A root operand as a real path, or None when it is built at run time."""
    home = os.path.expanduser("~")
    if word == "~" or word.startswith("~/"):
        word = home + word[1:]
    for var, value in (("${HOME}", home), ("$HOME", home), ("${PWD}", cwd), ("$PWD", cwd)):
        word = word.replace(var, value)
    if "$" in word or "`" in word:
        return None
    cut = min((i for i, c in enumerate(word) if c in "*?["), default=-1)
    if cut >= 0:  # a glob: walk-equivalent to its fixed prefix's directory; never expanded
        word = word[:cut]
        word = word if word.endswith("/") else os.path.dirname(word) or "."
    if not os.path.isabs(word):
        word = os.path.join(cwd, word)
    plain = os.path.normpath(word)
    if plain == "/" or inside(plain, "/mnt"):
        return plain  # judged by name: realpath would lstat into /mnt and fire an automount
    return os.path.realpath(plain)


def root_reason(real: str, repo: str) -> str | None:
    """Why walking from ``real`` is refused, or None."""
    if real == "/":
        return "the whole filesystem (/)"
    if inside(real, "/mnt"):
        return f"{real} (the NAS automounts under /mnt)"
    kind = fs_type(real)
    if kind in NETWORK:
        return f"{real} (a network mount, {kind})"
    if kind in RAM or inside(real, repo):
        return None
    return f"{real} (the shared disk, {kind or 'unknown fs'}, outside the repo)"


def parse(tool: str, args: list[str]) -> tuple[list[str], list[str]]:
    """(flags, positionals) of a grep/rg/ag/fd/tree/ls/du command line."""
    short = SHORT_WITH_VALUE.get("grep" if tool in GREPS else tool, "")
    flags: list[str] = []
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1 :])
            break
        if a.startswith("--"):
            flags.append(a)
            if "=" not in a and a in LONG_WITH_VALUE:
                if i + 1 < len(args):
                    flags.append(args[i + 1])
                i += 1
        elif a.startswith("-") and len(a) > 1:
            flags.append(a)
            for j, c in enumerate(a[1:], start=1):
                if c in short:
                    if j == len(a) - 1 and i + 1 < len(args):
                        flags.append(args[i + 1])
                        i += 1
                    break
        else:
            pos.append(a)
        i += 1
    return flags, pos


def letters(flag: str, short: str) -> str:
    """The option letters of a bundled short flag, up to the first one that takes a value
    (`-rn` -> "rn"; `-eroot` -> "e": "root" is -e's value, not -r -o -o -t)."""
    if not flag.startswith("-") or flag.startswith("--"):
        return ""
    out = ""
    for c in flag[1:]:
        out += c
        if c in short:
            break
    return out


def walk_roots(words: list[str]) -> list[str] | None:
    """The roots this command walks, or None when it does not walk."""
    tool = words[0].rsplit("/", 1)[-1]
    args = words[1:]
    if tool not in WALKERS:
        return None
    if tool == "find":
        i = 0
        while i < len(args) and (args[i] in FIND_GLOBAL or args[i].startswith(("-O", "-D"))):
            i += 2 if args[i] == "-D" else 1
        roots: list[str] = []
        while i < len(args) and not args[i].startswith(("-", "(", "!", ",")):
            roots.append(args[i])
            i += 1
        return roots or ["."]
    flags, pos = parse(tool, args)
    short = SHORT_WITH_VALUE.get("grep" if tool in GREPS else tool, "")
    if tool == "ls":
        if not any(f == "--recursive" or "R" in letters(f, short) for f in flags):
            return None
        return pos or ["."]
    if tool in ("du", "tree"):
        return pos or ["."]
    if tool in GREPS:
        recursive = any(
            f in ("--recursive", "--dereference-recursive", "--directories=recurse")
            or "r" in letters(f, short)
            or "R" in letters(f, short)
            for f in flags
        ) or ("recurse" in flags and ("-d" in flags or "--directories" in flags))
        if not recursive:
            return None
    if tool in ("fd", "fdfind"):
        search = [flags[k + 1] for k, f in enumerate(flags[:-1]) if f == "--search-path"]
        search += [f.split("=", 1)[1] for f in flags if f.startswith("--search-path=")]
        return search + pos[1:] or ["."]  # fd PATTERN [PATH...]
    pattern_given = tool in GREPS | {"rg"} and any(
        f in ("--regexp", "--file")
        or f.startswith(("--regexp=", "--file="))
        or letters(f, short)[-1:] in ("e", "f")
        for f in flags
    )
    no_pattern = tool == "rg" and ("--files" in flags or "--type-list" in flags)
    if not (pattern_given or no_pattern):
        pos = pos[1:]  # the first positional is the pattern
    return pos or ["."]


def classify_words(words: list[str], cwd: str, depth: int = 0) -> str | None:
    words = unwrap(words)
    if not words:
        return None
    head = words[0].rsplit("/", 1)[-1]
    if head in SHELLS and "-c" in words[1:] and depth < 4:
        idx = words.index("-c", 1)
        return classify(words[idx + 1], cwd, depth + 1) if idx + 1 < len(words) else None
    roots = walk_roots(words)
    if roots is None:
        return None
    repo = repo_root()
    for root in roots:
        real = resolve(root, cwd)
        if real is None:
            return f"`{head}` walks from `{root}`, which is built at run time (a hook can't see it)"
        why = root_reason(real, repo)
        if why:
            return f"`{head}` would walk {why}"
    return None


def classify(command: str, cwd: str | None = None, depth: int = 0) -> str | None:
    cwd = cwd or os.getcwd()
    stripped, shell_bodies = strip_heredocs(command)
    try:
        simple = segments(stripped)
    except ValueError:
        return None  # unparsable: fail open (see FAIL DIRECTION)
    for words in simple:
        reason = classify_words(words, cwd, depth)
        if reason:
            return reason
    for body in shell_bodies:
        reason = classify(body, cwd, depth + 1)
        if reason:
            return reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "")
        cwd = payload.get("cwd") or os.getcwd()
    except Exception:  # noqa: BLE001 -- unreadable input: fail open
        return 0
    if not isinstance(command, str) or not command or not isinstance(cwd, str):
        return 0
    try:
        reason = classify(command, cwd)
    except Exception:  # noqa: BLE001 -- a bug here must not block every Bash call
        return 0
    if reason is None:
        return 0
    print(
        f"BLOCKED by poring-lab's walk guard (CLAUDE.md rule 5): {reason}. The root disk is shared "
        f"with live capture and /mnt is the NAS. {SAFE_HINT}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
