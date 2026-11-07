#!/usr/bin/env python3
"""Push the poring-lab agent from ubuntu-docker to bot-server: its memory, its history, its five
skills and Batt's global CLAUDE.md under the bot-server preface (docs/planning/bot-server-cutover.md
Phase B; docs/operations/bot-server-handover.md). Run on ubuntu-docker; every copy is a push
(bot-server has no access back, Batt 2026-11-07).

    python3 scripts/agent_sync.py --dry-run      # the commands, nothing sent
    python3 scripts/agent_sync.py                # push, then read CLAUDE.md back

What it does, in order (each rsync under guarded_build's IO guard at the 2026-10-28 small-IO rule,
paced to 15 MB/s, the same as the first copy):
  1. memory/   -> the same folder there, made IDENTICAL (`--delete` inside memory/ only: until the
                  cutover's check passes, ubuntu-docker's memory is the record);
  2. history   -> every *.jsonl with `--append`: only the new tail of a growing transcript is read
                  and sent (`--append-verify` would re-read the whole 2 GB transcript on the shared
                  disk); then every other file, never deleting anything there;
  3. skills    -> each of migration_check.SKILLS, identical;
  4. CLAUDE.md -> the preface (docs/operations/bot-server-claude-preface.md), a `---` line and the
                  global CLAUDE.md verbatim; the old file kept as CLAUDE.md.bak-<UTC time>; read
                  back by sha256.

Then run `migration_check.py manifest` here and `check` there (Phase B), with no memory written in
between: the check wants the memory identical.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import migration_check as mc  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
REMOTE = "bot@192.168.1.228"
SSH = ["ssh", "-o", "BatchMode=yes"]
HOME = Path.home()
SRC_PROJECT = HOME / ".claude" / "projects" / "-home-batt-docker-poring-lab"
DST_PROJECT = "/home/bot/.claude/projects/-home-bot-docker-poring-lab"
SRC_SKILLS = HOME / ".claude" / "skills"
DST_SKILLS = "/home/bot/.claude/skills"
GLOBAL = HOME / ".claude" / "CLAUDE.md"
PREFACE = REPO / "docs" / "operations" / "bot-server-claude-preface.md"
RSYNC = ["rsync", "-a", "--bwlimit=15000", "-e", "ssh -o BatchMode=yes"]


def claude_md(preface: str, global_text: str) -> str:
    """PURE: the preface, a separator line, then Batt's text verbatim (migration_check's rule)."""
    if not preface.startswith(mc.PREFACE_MARK):
        raise SystemExit(f"{PREFACE}: must start with {mc.PREFACE_MARK!r}")
    return preface.rstrip("\n") + "\n\n---\n\n" + global_text


def copies() -> list[tuple[str, list[str]]]:
    """The rsync steps, (label, argv), in order."""
    steps = [
        ("agent-memory", [*RSYNC, "--delete", f"{SRC_PROJECT}/memory/",
                          f"{REMOTE}:{DST_PROJECT}/memory/"]),
        ("agent-history-tails", [*RSYNC, "--append", "--exclude=/memory/", "--include=*/",
                                 "--include=*.jsonl", "--exclude=*", f"{SRC_PROJECT}/",
                                 f"{REMOTE}:{DST_PROJECT}/"]),
        ("agent-history-rest", [*RSYNC, "--exclude=/memory/", "--exclude=*.jsonl",
                                f"{SRC_PROJECT}/", f"{REMOTE}:{DST_PROJECT}/"]),
    ]  # fmt: skip
    for skill in mc.SKILLS:
        steps.append((f"agent-skill-{skill}", [*RSYNC, "--delete", f"{SRC_SKILLS}/{skill}/",
                                               f"{REMOTE}:{DST_SKILLS}/{skill}/"]))  # fmt: skip
    return steps


PUSH_CLAUDE_MD = (
    "set -e; cd ~/.claude; "
    '[ -f CLAUDE.md ] && cp -p CLAUDE.md "CLAUDE.md.bak-$(date -u +%Y%m%dT%H%M%SZ)"; '
    "cat > CLAUDE.md.tmp; mv CLAUDE.md.tmp CLAUDE.md; sha256sum CLAUDE.md"
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the commands; send nothing")
    a = ap.parse_args(argv)
    text = claude_md(PREFACE.read_text(), GLOBAL.read_text())
    want = hashlib.sha256(text.encode()).hexdigest()
    if a.dry_run:
        for label, cmd in copies():
            print(f"{label}: {' '.join(cmd)}")
        print(f"CLAUDE.md: {len(text)} chars, sha256 {want[:12]} -> {REMOTE}: {PUSH_CLAUDE_MD}")
        return 0
    import guarded_build as gb  # the IO guard (VM 103's capture services)

    for label, cmd in copies():
        guard = gb.Guard(gb.cgroup_paths(), 30.0, 10.0, sustain=30.0)
        if not gb.run_process(label, cmd, guard):
            print(f"{label}: STOPPED/FAILED (worst stall {guard.worst}); nothing after it ran")
            return 1
        print(f"{label}: OK (worst stall {guard.worst[0]:.1f}%)", flush=True)
    r = subprocess.run([*SSH, REMOTE, PUSH_CLAUDE_MD], input=text, capture_output=True, text=True,
                       check=False)  # fmt: skip
    got = r.stdout.split()[0] if r.returncode == 0 and r.stdout else ""
    print(f"CLAUDE.md: sha256 sent {want[:12]}, read back {got[:12] or r.stderr.strip()!r}")
    return 0 if got == want else 1


if __name__ == "__main__":
    raise SystemExit(main())
