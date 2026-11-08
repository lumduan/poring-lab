---
doc_type: record
status: ACTIVE
date: 2026-10-09
---

# Scorers as used (verbatim records)

**Why this folder exists:** the scorers below scored PRE-REGISTERED runs in
`docs/demonstrations.md`, but they lived only in tmpfs (`/dev/shm/poring-lab-tmp/`), which a host
reboot wipes (the 2026-10-06 power cut did). Found 2026-10-09 by the ADR-0021 subagent: `walk17_score.py`'s
docstring cites `walk15_score.py`, which was in no commit. They are copied here BYTE FOR BYTE as
they were used (mtime and sha256 below), so every published number can be re-derived.

- **Verbatim, never edited:** fixes go into a NEW committed scorer (as `scripts/walk17_score.py`
  did), never into these files. They are excluded from ruff (`pyproject.toml`) for that reason.
- **How they ran:** from the repo root with the main `.venv`
  (`.venv/bin/python docs/records/scorers/walk15_score.py <session dir>`); some shell out to
  `uv run python scripts/demo_verify.py` / `demo_interruptions.py` as they did then. `walkN_score.py`
  scored walk@N's sessions; walk14_score.py and walk15_score.py are identical in size but differ in
  the rule name they select.
- Scripts that live under `scripts/` are the committed, tested tools; these are records.

| file | last modified (ICT) | sha256 (first 16) |
|---|---|---|
| `izdun_check.py` | 2026-10-09 13:26 | `de6bdd858827890e` |
| `walk7_score.py` | 2026-10-07 20:16 | `2ae7472ea18f968d` |
| `walk8_score.py` | 2026-10-07 23:00 | `9781c94de64e4507` |
| `walk9_score.py` | 2026-10-08 01:03 | `5d28124d6c20b8f3` |
| `availability.py` | 2026-10-08 10:23 | `5c1e1f2abfaaf2de` |
| `walk10_score.py` | 2026-10-08 03:09 | `301f0e40a2850602` |
| `walk11_score.py` | 2026-10-08 09:25 | `c299404187193f15` |
| `walk12_score.py` | 2026-10-08 15:32 | `5ceb807bc7b0b7bb` |
| `walk13_score.py` | 2026-10-08 21:30 | `5f472a6b2a765d70` |
| `walk14_score.py` | 2026-10-09 01:25 | `a7e874d65259646f` |
| `walk15_score.py` | 2026-10-09 04:30 | `ca0879e06dc52380` |
| `walk16_score.py` | 2026-10-09 08:40 | `90214debc1a67642` |
| `decision_hash.py` | 2026-10-08 15:40 | `d93daa4a48dd1c71` |
| `gpu_rec_r1_fingerprint.py` | 2026-11-08 18:19 | `ae2da14dbf5d1fbd` |

**Cited elsewhere:**
- `decision_hash.py`: demonstrations.md (the walk decision-code hash, cited as scratch)
- `availability.py`: docs/planning/training-cost.md
- `izdun_check.py`: demonstrations.md 3.29 (the iz_dun00 Hydra / safety / refusal checks)
- `gpu_rec_r1_fingerprint.py`: docs/planning/gpu-recording.md 8.1 (which colour convention
  reproduces round 1's `vpp-hevc420-q20` numbers; run 18:19-18:24 ICT from the worktree's
  `scripts/` on PYTHONPATH, its JSON sha256 `3232c1d6f198af7f`; reads the NAS sessions
  read-only: `python gpu_rec_r1_fingerprint.py OUT.json`)
