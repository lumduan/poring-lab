---
doc_type: decision
hypothesis: null
status: ACCEPTED (decided by Batt 2026-11-12; NOT BUILT yet -- after the flows Save / Load)
role: null
verdict_date: 2026-11-12
verdict_ticket: null
supersedes: null
related: [0023-learner-mode.md, ../planning/flows-save-load.md]
next_action: "Build after docs/planning/flows-save-load.md: scripts/econ_db.py (build / update / export) writing data/econ/lab.sqlite from the run folders, the /economy page reading it, CSV / JSON exports for sharing."
---

# ADR-0025: Run records in ONE local SQLite file (not PostgreSQL)

Written 2026-11-12 11:17 ICT from `date`.

## Context

- **Batt (2026-11-12, translated):** "If we give this to other people and teach others, where
  should their system keep it -- SQLite or PostgreSQL? Recommend one." Then, after the
  recommendation: "Do SQLite as you recommend. Do it after the flows Save / Load."
- **Today:** each run's raw folder holds `events.jsonl`, `packets.jsonl.gz` and the detections,
  in /dev/shm and then on the NAS. `scripts/econ_dash.py export` judges runs into
  `data/econ/dashboard/<name>.json`, and the /economy page reads those files. Prices come from
  `data/econ/items.json` and `maps.json`, which are rAthena- and client-derived and gitignored.
- **The learners** (ADR-0023): mostly one PC each, and every extra thing to install loses some.
- **Batt's rule of the same day:** a `git pull` must never overwrite or break a user's own data
  or config.

## Decision

1. **One SQLite file per installation: `data/econ/lab.sqlite`** (gitignored, like all of
   `data/`). It uses Python's standard `sqlite3`, so there is no server, no container and no
   password. One file to copy, back up or hand in.
2. **The raw run folders stay the source of truth.** The database is BUILT from them, so it can
   always be rebuilt (`build`) or brought up to date (`update`: new runs only, by session id).
3. **The schema is versioned inside the file** (`PRAGMA user_version`). The code migrates an older
   file FORWARD at start, inside a transaction. A migration never drops or rewrites a user's rows.
   A file from a NEWER version is refused with a plain message ("made by a newer poring-lab:
   pull the update"), never altered.
4. **Writes:** one writer at a time, in WAL mode. This suits our rate: one runner, a few rows a
   second.
5. **Sharing goes through files, not the database:** CSV / JSON exports (a run, a pair, a class
   summary) can be shared, like the flows (docs/planning/flows-save-load.md).
   - Only derived NUMBERS the user produced may be shared.
   - Item or monster tables from rAthena (GPL) or the client never go into a shared export or into
     git (CLAUDE.md rule 4). An export carries ids and counts, and names only when the user's own
     data/ supplies them locally.
6. **PostgreSQL only if one of these becomes true:**
   - several students' bots write AT THE SAME TIME on one shared server;
   - a web dashboard is used by many people at once;
   - the data grows to tens of GB.
   The storage layer is kept small (plain SQL, one module), so a later move stays possible.

## Consequences

- A learner needs nothing new: the file appears the first time `econ_db.py build` runs or a run
  is judged.
- It can be opened in DB Browser for SQLite, pandas, or as CSV in Excel, for teaching economics
  across many runs.
- The lab's MariaDB stays the game server's own (rAthena: characters, items). Run records never go
  into it.
