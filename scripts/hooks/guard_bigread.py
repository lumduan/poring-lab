#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash): no whole-file reads of session transcripts or big local files.

Why (CLAUDE.md rule 5): this host's root disk is ONE virtual disk shared with live quant capture.
Twice (2026-10-02 and -03) a grep over the ~330 MB session transcript loaded it; the first time
quant-postgres went to a 24 % IO stall. A memory note did not stop the repeat, so this refuses it
mechanically, like guard_docker.py refuses unguarded docker steps.

A TARGET is
  - a session transcript: any *.jsonl under ~/.claude (after realpath, so a subagent's
    tasks/*.output symlink counts; a Bash background output is a regular file and does not), or
  - a regular file over BIG_BYTES (50 MB) on a disk-backed filesystem. RAM filesystems
    (/dev/shm, /proc …) and network ones (the NAS's nfs4 mounts) are not the shared disk.

REFUSES (exit 2, reason on stderr)
  - a reader (grep, rg, cat, awk, sed, sort, wc, sha256sum, less …) with a target operand or
    `<` input; a recursive grep/rg/ag whose root is inside ~/.claude, or whose root contains it
    (rg/ag only with --hidden/-u: they skip dot-dirs by default); `find … -exec <reader>` there;
  - head/tail/dd on a target WITHOUT a byte bound of at most BOUND_BYTES (64 MB): `head -c N`,
    `tail -c N` and `dd … bs=X count=Y` pass; `-n` (a JSONL line can be megabytes), `tail -c +K`,
    `head -c -K` and dd without count= are refused.
ALLOWS ls / stat / du / file on anything, every read of a small file, and e.g.
    tail -c 5000000 <transcript> | LC_ALL=C grep -F needle
`ionice -c3` is accepted but not required: this host's disk scheduler is `none`, which ignores
I/O priorities, so only a byte bound actually protects the disk (Batt, 2026-10-03).

SEES THROUGH what guard_docker.py sees through (the shared scripts/hooks/_shell.py). CANNOT SEE:
paths built at run time ($VAR other than $HOME, $(…), xargs) or reads by a program
(`python -c 'open(…).read()'`) -- the stated boundary.

FAIL DIRECTION: unreadable hook input or an unparsable command -> allow (a guard that blocks every
Bash call is worse, and docker's guard keeps its own regex fallback).
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # see guard_docker.py: never fail open
from _shell import SHELLS, segments, strip_heredocs, unwrap  # noqa: E402

BIG_BYTES = 50 << 20
BOUND_BYTES = 64 << 20
GLOB_CAP = 200
READERS = frozenset(
    {"grep", "egrep", "fgrep", "zgrep", "rg", "ag", "cat", "tac", "awk", "gawk", "mawk", "sed",
     "jq", "wc", "sort", "uniq", "cut", "nl", "strings", "od", "xxd", "hexdump", "less", "more",
     "sha256sum", "sha1sum", "md5sum", "b2sum", "cmp", "diff", "zcat", "bat"}
)  # fmt: skip
RECURSIVE = {"grep", "egrep", "fgrep", "zgrep"}
# Filesystems that are not the shared virtual disk.
NOT_DISK = frozenset(
    {"tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue",
     "securityfs", "debugfs", "tracefs", "pstore", "bpf", "efivarfs", "configfs", "fusectl",
     "hugetlbfs", "autofs", "binfmt_misc", "nfs", "nfs4", "cifs", "smb3", "9p", "fuse.sshfs"}
)  # fmt: skip
SIZE = re.compile(r"^(\d+)([A-Za-z]*)$")
UNITS = {
    "": 1, "c": 1, "w": 2, "b": 512, "kB": 1000, "K": 1024, "KiB": 1024, "k": 1024,
    "MB": 1000**2, "M": 1 << 20, "MiB": 1 << 20, "GB": 1000**3, "G": 1 << 30, "GiB": 1 << 30,
}  # fmt: skip
BOUNDED = "tail -c 5000000 <file> | LC_ALL=C grep -F <needle>   (or head -c N, dd bs=1M count=N)"


def home() -> Path:
    return Path(os.path.expanduser("~"))


def claude_dir() -> Path:
    return Path(os.path.realpath(home() / ".claude"))


def fs_type(path: str) -> str:
    """The filesystem type of ``path`` (longest mount-point prefix in /proc/mounts)."""
    best, kind = "", ""
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mnt = parts[1].replace("\\040", " ")
                inside = path == mnt or path.startswith(mnt.rstrip("/") + "/")
                if inside and len(mnt) >= len(best):
                    best, kind = mnt, parts[2]
    except OSError:
        return ""
    return kind


def is_transcript(real: str) -> bool:
    base = str(claude_dir())
    return real.endswith(".jsonl") and real.startswith(base + os.sep)


def target_reason(real: str) -> str | None:
    """Why reading ``real`` (already realpath'd) whole is refused, or None."""
    if is_transcript(real):
        return "a session transcript"
    try:
        st = os.stat(real)
    except OSError:
        return None
    if not os.path.isfile(real) or st.st_size <= BIG_BYTES:
        return None
    if fs_type(real) in NOT_DISK:
        return None
    return f"{st.st_size / (1 << 20):.0f} MB on the shared disk"


def expand(word: str, cwd: str) -> list[str]:
    """Shell-ish expansion of one operand: ~, $HOME, globs; relative to the command's cwd."""
    h = str(home())
    if word == "~" or word.startswith("~/"):
        word = h + word[1:]
    word = word.replace("${HOME}", h).replace("$HOME", h)
    if "$" in word:
        return []  # built at run time: outside what a hook can see
    if not os.path.isabs(word):
        word = os.path.join(cwd, word)
    if any(c in word for c in "*?["):
        return sorted(glob.glob(word, recursive="**" in word))[:GLOB_CAP]
    return [word]


def size_arg(text: str) -> int | None:
    """head/tail/dd sizes (`5000000`, `2M`, `64MB`, `1K`). None = unparsable or signed."""
    m = SIZE.match(text)
    if not m or m.group(2) not in UNITS:
        return None
    return int(m.group(1)) * UNITS[m.group(2)]


def operands(words: list[str]) -> tuple[list[str], list[str]]:
    """(plain operands, input-redirect files) of one simple command; output redirects dropped."""
    plain: list[str] = []
    inputs: list[str] = []
    skip_next = False
    take_input = False
    for w in words[1:]:
        if skip_next:
            skip_next = False
            continue
        if take_input:
            inputs.append(w)
            take_input = False
            continue
        if w == "<":
            take_input = True
        elif w.startswith("<") and not w.startswith("<<"):
            inputs.append(w[1:])
        elif re.match(r"^\d*>>?$|^&>>?$", w):
            skip_next = True  # `> file`, `2>> file`, `&> file`
        elif re.match(r"^\d*>>?|^&>>?", w):
            continue  # `>file`, `2>/dev/null`
        elif not w.startswith("-") or w == "-":
            plain.append(w)
    return plain, inputs


def bounded(head: str, words: list[str]) -> bool:
    """True when head/tail/dd reads at most BOUND_BYTES of its file."""
    args = words[1:]
    if head == "dd":
        kv = dict(a.split("=", 1) for a in args if "=" in a)
        if "count" not in kv:
            return False
        count = size_arg(kv["count"])
        bs = size_arg(kv.get("ibs", kv.get("bs", "512")))
        if count is None or bs is None:
            return False
        total = count if "count_bytes" in kv.get("iflag", "") else count * bs
        return total <= BOUND_BYTES
    limit: int | None = None
    i = 0
    while i < len(args):
        a = args[i]
        value = None
        if a in ("-c", "--bytes") and i + 1 < len(args):
            value = args[i + 1]
            i += 1
        elif a.startswith("--bytes="):
            value = a.split("=", 1)[1]
        elif a.startswith("-c") and len(a) > 2:
            value = a[2:]
        if value is not None:
            limit = size_arg(value)  # `+K` / `-K` (from-offset, all-but) do not parse: unbounded
        i += 1
    return limit is not None and limit <= BOUND_BYTES


def recursive_root_reason(head: str, words: list[str], real: str) -> str | None:
    """A recursive read rooted inside ~/.claude, or above it (a walk that would reach it)."""
    base = str(claude_dir())
    flags = [w for w in words[1:] if w.startswith("-")]
    if head in RECURSIVE:
        recursive = any(
            f in ("-r", "-R", "--recursive", "--dereference-recursive")
            or (not f.startswith("--") and ("r" in f[1:] or "R" in f[1:]))
            for f in flags
        )
    else:  # rg / ag walk directories by default, but skip dot-dirs unless told otherwise
        recursive = True
    if not recursive or not os.path.isdir(real):
        return None
    if real == base or real.startswith(base + os.sep):
        return "session transcripts (a recursive read inside ~/.claude)"
    hidden = any(f in ("--hidden", "-.", "--unrestricted") or re.match(r"^-u+$", f) for f in flags)
    if base.startswith(real.rstrip(os.sep) + os.sep) and (head in RECURSIVE or hidden):
        return "session transcripts (a recursive read that walks into ~/.claude)"
    return None


def classify_words(words: list[str], cwd: str, depth: int = 0) -> str | None:
    words = unwrap(words)
    if not words:
        return None
    head = words[0].rsplit("/", 1)[-1]
    if head in SHELLS and "-c" in words[1:] and depth < 4:
        idx = words.index("-c", 1)
        return classify(words[idx + 1], cwd, depth + 1) if idx + 1 < len(words) else None
    if head == "find" and any(w in ("-exec", "-execdir") for w in words):
        execs = {w.rsplit("/", 1)[-1] for w in words}
        roots = [w for w in words[1:] if not w.startswith("-")][:1]
        for root in roots:
            for real in (os.path.realpath(p) for p in expand(root, cwd)):
                base = str(claude_dir())
                if execs & READERS and (real == base or real.startswith(base + os.sep)):
                    return "`find … -exec` over session transcripts (~/.claude)"
        return None
    if head == "dd":
        files = [w.split("=", 1)[1] for w in words[1:] if w.startswith("if=")]
        _, inputs = operands(words)
        candidates = files + inputs
    elif head in READERS or head in ("head", "tail"):
        plain, inputs = operands(words)
        candidates = plain + inputs
    else:
        return None
    for cand in candidates:
        for path in expand(cand, cwd):
            real = os.path.realpath(path)
            if head in RECURSIVE or head in ("rg", "ag"):
                why = recursive_root_reason(head, words, real)
                if why:
                    return f"`{head}` would read {why}"
            why = target_reason(real)
            if why is None:
                continue
            if head in ("head", "tail", "dd") and bounded(head, words):
                continue
            shown = path if len(path) <= 120 else "…" + path[-117:]
            return f"`{head}` would read {shown} ({why}) whole"
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
        f"BLOCKED by poring-lab's big-read guard (CLAUDE.md rule 5): {reason}. The root disk is "
        "shared with live capture; read a bounded byte range instead: "
        f"{BOUNDED}. ls/stat/du are fine.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
