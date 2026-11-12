---
doc_type: decision
hypothesis: null
status: "ACCEPTED (decided by Batt 2026-11-12); phase 1 BUILT 2026-11-12 (scripts/econ_db.py: the file, build / update / list / export / dashboard); phase 2 NOT BUILT"
role: null
verdict_date: 2026-11-12
verdict_ticket: null
supersedes: null
related: [0023-learner-mode.md, ../planning/flows-save-load.md, ../econ/economics.md, ../setup/new-lab-host.md]
next_action: "Phase 2 (Implementation, below): the /economy page reading data/econ/lab.sqlite through a read-only backend route (today it still reads the JSON exports), the pooled views from the file, and an update after each judged run."
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
  is judged. (➡️ Phase 1, 2026-11-12: only `econ_db.py build` / `update` write it; nothing writes
  it by itself after a run yet. That is phase 2, see Implementation.)
- It can be opened in DB Browser for SQLite, pandas, or as CSV in Excel, for teaching economics
  across many runs.
- The lab's MariaDB stays the game server's own (rAthena: characters, items). Run records never go
  into it.

## Implementation (phase 1, BUILT 2026-11-12)

Written 2026-11-12 12:14 ICT from `date`. The code is `scripts/econ_db.py` (standard-library
`sqlite3` only, no new dependency); the tests are `services/backend/tests/test_econ_db.py`.

**The numbers come from the existing judges, not from new code.** `build` runs each session through
`econ_dash.judge_session` (`dungeon_judge.judge` + `kills_loot`, `econ_row`'s uses and kill mix) and
`econ_dash.entry_of`, exactly as `econ_dash.py export` does. A run whose `econ_dash.check` disagrees
with the judges is refused and not written. The file then stores that entry's COUNTS. To allow
this, econ_dash's per-run code was split with no change in behaviour:
- `counts_of`: the drops and item uses taken from the packets;
- `entry_from_counts`: the entry composed from the counts and the prices;
- `judge_session` / `entry_of`: judging, then composing;
- `sources` / `document` / `table_sha`: the export document around its runs.

`test_econ_dash.py` is unchanged and passes. The real p84 export (written at 10:04 by the code
before the split) was reproduced from the file in every key except `exported_at` and the export
name.

**The file:** `--db`, default `<data>/econ/lab.sqlite`. It is gitignored like all of `data/`, and so
are its `-wal` / `-shm` files (a test runs `git check-ignore`). WAL mode, foreign keys on.

**The tables, schema version 1** (one row per run, then per run x item / species / consumable;
items and monsters by NUMERIC id):

| Table | Key | Columns |
|---|---|---|
| `runs` | `session` (the session id) | `dir`, `map`, `char`, `strategy`, `version` (the RUNNER's, as the judge has it), `window_t0_ns`, `window_t1_ns`, `window_source`, `minutes`, `hours` (unrounded: every count's divisor), `kills`, `deaths`, `started`, `ended` (wall clock, ICT), `flow_runner`, `flow_strategy`, `flow_search`, `flow_label`, `flow_flags` (JSON), `judge_why`, `econ_why` (JSON: the judges' reasons), `items_table_sha256`, `judge_value`, `econ_row` (JSON snapshot, below), `judge_commit` (git HEAD of the judges' code, `+dirty` when scripts/ or packages/ differ; NULL without git), `built_at` |
| `run_items` | (`session`, `item_id`) | `picked`, `stolen` (= `stolen_steal` + `stolen_snatcher`, CHECKed), `stolen_steal`, `stolen_snatcher`, `income` (= picked + stolen, CHECKed), `other`, `staged` (both not income), `dropped` (by our kills), `picked_of_dropped` |
| `run_species` | (`session`, `mob_id`) | `kills` (`mob_id` -1: no monster appear before the kill) |
| `run_consumables` | (`session`, `item_id`) | `used` (OUR successful uses in the window) |

**Names and prices are not data of record in the file.** It has no name column and no price
column:
- names come from `data/kb` (else the item table) at export time, and only with `--with-names`;
- prices come from `data/econ/items.json` when a dashboard is made.

The only zeny figures stored are the per-run snapshot that econ_dash's entry already carries:
- `judge_value`: `dungeon_judge.items_value`;
- `econ_row`: econ_row.measure's zeny block;
- `items_table_sha256`: the item table they were computed with.

That snapshot is kept as the reference for the cross-check, never read as prices. The file is local
run-time data like all of `data/` (CLAUDE.md rule 4), never committed.

**The command line:**

    econ_db.py build  [--db PATH] [--data DIR] [--map MAP] SESSION ...   (re)judge and write these runs
    econ_db.py update [--db PATH] [--data DIR] [--map MAP] SESSION ...   only session ids not in the file
    econ_db.py list   [--db PATH]                                        one JSON line per run
    econ_db.py export --format csv|json --out FILE [--runs SID ...] [--with-names]
    econ_db.py dashboard --runs SID ... --name NAME [--out-dir DIR]      econ_dash's JSON, from the file

- SESSION is a directory or an id, as for `econ_dash.py export`.
- **Exports for sharing** carry ids and counts:
  - every `runs` column except `dir`, the two `*_why` columns and the zeny snapshot;
  - all the child counts.

  CSV gives four files: `FILE` (the runs), and `<stem>_items`, `<stem>_species` and
  `<stem>_consumables` beside it, in UTF-8 with a BOM for Excel. JSON gives one file, schema
  `poring-lab.econ-runs.v1`.
- `dashboard` composes each entry with `econ_dash.entry_of`, from the stored counts and today's
  item table and names. It pools with `econ_dash.pool_runs`, wraps with `econ_dash.document`,
  checks every run with `econ_dash.check`, and writes with `econ_dash.write`.
  - So its JSON is the JSON `econ_dash.py export` writes (tested on synthetic runs and on the
    real p57 + p58).
  - When the item table changed after a run was built, the check fails. The command then writes
    nothing and says to `build` that run again.

**The migration rule:**
- `MIGRATIONS[n]` takes a file from version n to n + 1 (`PRAGMA user_version`). Every step and the
  version bump run in ONE transaction: a failure leaves the file at its old version with its rows
  (tested).
- A migration only ADDS: `CREATE TABLE / INDEX / VIEW`, or `ALTER TABLE ... ADD COLUMN`. It never
  drops, renames, deletes or rewrites a user's rows. `additive()` checks every statement before
  anything runs.
- A new version is appended; a released one is never edited.
- A NEWER file is refused with "made by a newer poring-lab: pull the update" and never altered:
  - its version is read from the file header, without opening the file for writing;
  - a non-empty `-wal` beside it is read read-only, since the log can be newer than the header.

  The test checks that the file is unchanged byte for byte and that no `-wal` / `-shm` appears.
- A file that is not SQLite is refused unchanged. A version-0 file (empty, or someone's own
  tables) gets our tables beside its rows.

**Writes:** one writer at a time (`BEGIN IMMEDIATE`, 30 s busy timeout). Each run is written in
ONE transaction: its run row and every child row, or none of them.
- A failure in the middle rolls back. This was tested with a duplicate key, a CHECK and a Python
  error inside the transaction.
- A run being rebuilt keeps its old rows when the rebuild fails.
- `update` judges nothing that is already there.

**Phase 2 (NOT BUILT):**
1. The `/economy` page reads the file through a read-only backend route (public listener only, like
   `routes_economy.py`). Until then it keeps reading the JSON exports, which `econ_dash.py export`
   or `econ_db.py dashboard` write.
2. Pooled views from the file: per map, character, flow label or flag set, and per hour over the
   summed judged hours. They are additive SQL views (a migration), or pooled through
   `econ_dash.pool_runs`.
3. An `update` after each judged run (the night chain's ship / score step), so that the file
   "appears when a run is judged" (Consequences).
