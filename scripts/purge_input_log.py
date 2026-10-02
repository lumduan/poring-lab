#!/usr/bin/env python3
"""Purge human typing from the input and transfer logs (2026-10-02). Counts only, never content.

Until the console had a secret-typing toggle, every key a human typed through the web console was
logged with its code, so a password typed there (a game login, a UAC prompt) is reconstructable
from data/input_log. A paste also logged its length and a digest (the full sha256 before
2026-10-01, a 12-hex prefix since); either one confirms a guessed password offline.

    purge_input_log.py            # dry run: per-file counts of what WOULD change
    purge_input_log.py --apply    # rewrite in place (same inode, EXCLUSIVE flock)

What changes:
  * input_log: a human "key" line whose code produces a character (letters, digits, punctuation,
    Space, the numpad) is DELETED. The log can't tell a password from other typing, so every one
    goes. Kept: the human keys that type nothing (Enter, Tab, arrows, modifiers, F-keys...), every
    mouse line, every bot line (bot credentials were always sensitive batches), and already
    redacted secret keys.
  * input_log: a human "clipboard_paste" line keeps its place but loses chars/bytes/sha256
    ({"type": "clipboard_paste", "redacted": true}).
  * transfer_log: a "paste" line loses size and sha256 (size 0, sha256 null, "redacted": true).
    Uploads and downloads (files) keep their sha256.

Safe while the backend runs: its appends hold a SHARED flock (poring_backend.input_log.DailyJsonl)
and this holds an EXCLUSIVE one while it rewrites, in place; the O_APPEND writer continues at the
new end of file. Run it under `ionice -c3` (rule 5: the disk is shared with live capture).
"""

import argparse
import fcntl
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
# KeyboardEvent.code values that put a character into a text field.
PRINTABLE = re.compile(
    r"^(Key[A-Z]|Digit[0-9]|Numpad([0-9]|Decimal|Divide|Multiply|Subtract|Add|Comma|Equal)"
    r"|Space|Minus|Equal|BracketLeft|BracketRight|Backslash|Semicolon|Quote|Backquote|Comma"
    r"|Period|Slash|Intl[A-Za-z]+)$"
)


def input_line(line: str, counts: Counter[str]) -> str | None:
    """The line to keep (maybe redacted), or None to delete it."""
    try:
        rec: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        counts["unparsable_kept"] += 1
        return line
    event = rec.get("event") or {}
    if rec.get("source") != "human":
        return line
    if event.get("type") == "key":
        counts["human_keys"] += 1
        if PRINTABLE.match(str(event.get("code", ""))):
            counts["human_printable_keys_deleted"] += 1
            return None
        return line
    leaks = any(k in event for k in ("chars", "bytes", "sha256"))
    if event.get("type") == "clipboard_paste" and leaks:
        counts["human_pastes_redacted"] += 1
        rec["event"] = {"type": "clipboard_paste", "redacted": True}
        return json.dumps(rec, separators=(",", ":"))
    return line


def transfer_line(line: str, counts: Counter[str]) -> str | None:
    try:
        rec: dict[str, Any] = json.loads(line)
    except json.JSONDecodeError:
        counts["unparsable_kept"] += 1
        return line
    if rec.get("action") == "paste" and (rec.get("sha256") or rec.get("size")):
        counts["paste_audits_redacted"] += 1
        rec.update(size=0, sha256=None, redacted=True)
        return json.dumps(rec, separators=(",", ":"))
    return line


def purge_file(path: Path, rule: Any, apply: bool) -> Counter[str]:
    counts: Counter[str] = Counter()
    with path.open("r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)  # the backend's appends wait (they hold LOCK_SH)
        try:
            lines = fh.read().splitlines()
            kept = [out for line in lines if (out := rule(line, counts)) is not None]
            counts["lines_before"] = len(lines)
            counts["lines_after"] = len(kept)
            changed = kept != lines
            if apply and changed:
                fh.seek(0)
                fh.write("".join(f"{line}\n" for line in kept))
                fh.truncate()
                fh.flush()
                os.fsync(fh.fileno())
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="rewrite the files (default: dry run)")
    ap.add_argument("--data", type=Path, default=DATA, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    total: Counter[str] = Counter()
    for sub, rule in (("input_log", input_line), ("transfer_log", transfer_line)):
        for path in sorted((a.data / sub).glob("*.jsonl")):
            counts = purge_file(path, rule, a.apply)
            total.update({k: v for k, v in counts.items() if not k.startswith("lines_")})
            interesting = {k: v for k, v in sorted(counts.items()) if v}
            print(f"{sub}/{path.name}: {interesting}")
    verb = "PURGED" if a.apply else "dry run (nothing written; --apply to purge)"
    print(f"{verb}: {dict(sorted(total.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
