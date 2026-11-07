"""scripts/agent_sync.py: the agent's push to bot-server deletes only inside memory/ and the skills,
appends to growing transcripts, and builds the CLAUDE.md that migration_check accepts (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import agent_sync as asy  # noqa: E402
import migration_check as mc  # noqa: E402


def test_the_claude_md_it_builds_is_the_one_the_check_accepts() -> None:
    preface = asy.PREFACE.read_text()
    text = asy.claude_md(preface, "Batt's rules\n\nverbatim\n")
    assert text.startswith(mc.PREFACE_MARK) and text.endswith("Batt's rules\n\nverbatim\n")
    src = {"memory": {}, "history": {}, "sessions": {}, "skills": {},
           "claude_md": "Batt's rules\n\nverbatim\n"}  # fmt: skip
    rows = {r["item"]: r["status"] for r in mc.claude_rows(src, {**src, "claude_md": text})}
    assert rows["agent: Batt's CLAUDE.md verbatim under the bot-server preface"] == "PASS"
    with pytest.raises(SystemExit, match="must start with"):
        asy.claude_md("# some other preface\n", "x")


def test_deletes_stay_inside_memory_and_the_skills_and_transcripts_only_grow() -> None:
    steps = dict(asy.copies())
    assert list(steps)[:3] == ["agent-memory", "agent-history-tails", "agent-history-rest"]
    assert len(steps) == 3 + len(mc.SKILLS)
    for label, cmd in steps.items():
        src, dst = cmd[-2], cmd[-1]
        assert dst.startswith(f"{asy.REMOTE}:/home/bot/.claude/"), label
        assert src.endswith("/") and dst.endswith("/"), label  # contents, never a nested copy
        if "--delete" in cmd:
            assert label == "agent-memory" or label.startswith("agent-skill-"), label
            assert dst.endswith(("/memory/", *(f"/skills/{s}/" for s in mc.SKILLS))), label
    tails, rest = steps["agent-history-tails"], steps["agent-history-rest"]
    assert "--append" in tails and "--append-verify" not in tails  # never re-read the 2 GB file
    assert tails.index("--exclude=/memory/") < tails.index("--include=*/")  # first match wins
    assert "--exclude=*.jsonl" in rest and "--exclude=/memory/" in rest
    assert all("--bwlimit=15000" in cmd for cmd in steps.values())
