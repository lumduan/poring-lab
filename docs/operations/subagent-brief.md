---
doc_type: runbook
hypothesis: null
status: ACTIVE
role: null
verdict_date: null
verdict_ticket: null
supersedes: null
related: [../../CLAUDE.md]
next_action: "Paste the block below into every subagent brief (Batt, 2026-10-07)."
---

# The subagent brief: shared-disk and safety rules every subagent inherits

Batt, 2026-10-07: **subagents inherit the shared-disk rules.**

- A subagent does not read CLAUDE.md on its own, so the parent PASTES the block below into
  every brief.
- **Why:** the host's one virtual disk is shared with live 24/7 capture (CLAUDE.md rule 5).
- **The trigger:** on 2026-10-07 a decoder subagent working in a git worktree ran `uv run`, which
  builds a fresh `.venv` (thousands of small files) on the shared disk. The IO guard aborted a
  training step at 14:24 (quant-postgres IO stall 29.3 %).
  - That stall could NOT be attributed: the worktree was deleted, the IO-baseline sampler was not
    running, and the `.venv` was most likely built near the subagent's start, ~30 min earlier.
  - The rule stands regardless: a fresh env or build on the shared disk is exactly the IO the
    guards exist to prevent.

## The block to paste

```text
SHARED-DISK AND SAFETY RULES (poring-lab, CLAUDE.md rules 1-10; you inherit all of them)
- The host disk is shared with live capture. Nothing heavy or many-small-files on it:
  - no .venv, node_modules, builds, caches or extracted trees in the repo or a worktree;
  - Python in a worktree: export UV_PROJECT_ENVIRONMENT=/dev/shm/poring-lab-venvs/<your-name>
    UV_LINK_MODE=copy before any `uv run` / `uv sync` (the env lives in RAM; delete it when done);
  - npm/pnpm/json2ts and similar: install into /dev/shm only, never on disk;
  - scratch, test temp, caches: export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/dev/shm/poring-lab-tmp;
    pytest -p no:cacheprovider --basetemp="$TMPDIR/pytest"; mypy --cache-dir=/dev/null;
    ruff --no-cache.
- Docker: never raw docker / docker compose (create, start, restart, build, pull, up). Only the
  guarded steps (scripts/guarded_build.py), and only when the brief says so. `docker exec` into
  frontend-dev for lint/typecheck is allowed.
- The hooks apply to you too:
  - guard_docker (raw docker refused);
  - guard_bigread (no grep/cat/... of *.jsonl under ~/.claude or files > 50 MB; byte ranges only);
  - guard_walk (no find/du/rg/tree/ls -R/recursive grep outside the repo; use git ls-files /
    git grep inside it).
  Never route around a hook (python subprocess, $(...)).
- No live actions unless the brief says so: no ro_agent / Windows / GUI input, no GPU jobs, no
  sniffer rebuild.
- Never commit client-derived or GPL-derived data. The pre-commit locale-pack guard refuses
  quoted UI words; rename, never bypass (no --no-verify).
- Conventional commits on your worktree branch; do not push or merge; report the SHAs.
- Before you finish: delete your /dev/shm env and scratch, and say what you left behind.
```

## For the parent
- After merging a subagent's branch, remove its worktree and branch. Delete its `/dev/shm`
  leftovers.
- When a guard trips while a subagent runs, note the subagent's timeline in the report. Its
  activity is part of the host's IO.
