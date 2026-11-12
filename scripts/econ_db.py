#!/usr/bin/env python3
"""RUN RECORDS IN ONE LOCAL SQLITE FILE (ADR-0025 phase 1; Batt 2026-11-12: "Do SQLite as you
recommend"): every judged run's COUNTS -- the very numbers scripts/econ_dash.py's per-run export
carries -- in one file per installation, for teaching economics across many runs. OFFLINE: it
reads banked session files only; nothing here reaches a bot. Standard library sqlite3 only.

    econ_db.py build  [--db PATH] [--data DIR] [--map MAP] SESSION [SESSION ...]
    econ_db.py update [--db PATH] [--data DIR] [--map MAP] SESSION [SESSION ...]
    econ_db.py list   [--db PATH] [--data DIR]
    econ_db.py export --format csv|json --out FILE [--runs SID ...] [--with-names]
                      [--db PATH] [--data DIR]
    econ_db.py dashboard --runs SID [SID ...] --name NAME [--db PATH] [--data DIR] [--out-dir DIR]

- build: judge each SESSION and (re)write its rows (a run already in the file is replaced);
- update: the same for the sessions NOT yet in the file (by session id); the others are left
  exactly as they are, so running it twice changes nothing;
- list: one JSON line per run;
- export: the runs' ids and counts for SHARING. CSV: the runs in FILE, and beside it FILE's stem
  + _items / _species / _consumables (UTF-8 with a BOM, for Excel). JSON: one file. No names
  unless --with-names, and then only from YOUR data/ at export time;
- dashboard: the SAME JSON `econ_dash.py export` writes (<out-dir>/NAME.json, default
  <data>/econ/dashboard/, which the /economy page reads), rebuilt from the file through
  econ_dash's own functions with the item table of today.

SESSION: a session directory or id, exactly as econ_dash.py export takes it
(dungeon_judge.session_dir). The file: --db, default <data>/econ/lab.sqlite (data/ is gitignored:
a `git pull` never touches it; never run `git clean -x`, which deletes it).

THE NUMBERS come from the existing judges, never re-derived here: build runs a session through
econ_dash.judge_session (dungeon_judge.judge + kills_loot, econ_row's uses and kill_mix) and
econ_dash's entry, refuses a run whose econ_dash.check disagrees with the judges, and stores the
entry's counts: per run (the window, hours, kills, deaths, map, character, flow, the runner's
version, the judges' code), per run x item (picked, stolen by Steal / Snatcher, income, other,
staged, dropped by our kills, picked of those), per run x species (kills), per run x consumable
(used). Items and monsters by NUMERIC id.

NAMES AND PRICES are not data of record here. The file holds no item or monster name and no price
table: names come from data/kb at export time (--with-names), prices from data/econ/items.json
when a dashboard is made. The only zeny figures stored are the per-run snapshot econ_dash's entry
carries -- `judge_value` (dungeon_judge.items_value) and `econ_row` (econ_row.measure's zeny
block) with the item table's sha256 -- kept as the cross-check's reference only. Like all of
data/, the file is local run-time data (CLAUDE.md rule 4): never committed.

THE SCHEMA VERSION lives in the file (PRAGMA user_version). On open, an older file is migrated
FORWARD in one transaction; a migration only adds (additive()) and never drops or rewrites a
user's rows. A NEWER file is refused with a plain message and never altered (its version is read
from the header, without opening it for writing). WAL mode; one transaction per run, so a crash
mid-build never leaves half a run.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_NAME = "lab.sqlite"
EXPORT_SCHEMA = "poring-lab.econ-runs.v1"
SQLITE_MAGIC = b"SQLite format 3\x00"


def default_db(data: Path = DATA) -> Path:
    return data / "econ" / DB_NAME


class DbError(Exception):
    """A refusal with a plain message for a person (printed as is; exit 1)."""


class NewerDatabase(DbError):
    """The file was made by a newer poring-lab: refused, never altered."""


def newer_message(path: Path, version: int) -> str:
    return (
        f"{path}: made by a newer poring-lab: pull the update (the file's schema version is "
        f"{version}, this code knows up to {latest()}). The file was not changed."
    )


# --- the schema: FORWARD-ONLY migrations ----------------------------------------------------------
# MIGRATIONS[n] takes a file from version n to n + 1 (PRAGMA user_version), together with the
# version bump in ONE transaction. A migration only ADDS -- a table, an index, a view, a column --
# and never drops, renames, deletes or rewrites a user's rows (ADR-0025 decision 3; additive() is
# checked before anything runs). A new version is APPENDED; a released one is never edited.

_RUNS = """
CREATE TABLE runs (
    session            TEXT PRIMARY KEY NOT NULL,  -- the session id (its directory's name)
    dir                TEXT,              -- the directory it was judged from (local; not shared)
    map                TEXT,
    char               TEXT,
    strategy           TEXT,
    version            TEXT,              -- the RUNNER's version (run_start), as the judge has it
    window_t0_ns       INTEGER NOT NULL,  -- the judged window, CLOCK_MONOTONIC ns
    window_t1_ns       INTEGER NOT NULL,
    window_source      TEXT NOT NULL,
    minutes            REAL,
    hours              REAL NOT NULL,     -- (t1 - t0) / 3600 s, unrounded: every count's divisor
    kills              INTEGER NOT NULL,
    deaths             INTEGER NOT NULL,
    started            TEXT,              -- the window on the wall clock (ICT), econ_dash.run_clock
    ended              TEXT,
    flow_runner        TEXT,
    flow_strategy      TEXT,
    flow_search        TEXT,
    flow_label         TEXT,
    flow_flags         TEXT NOT NULL DEFAULT '[]',  -- JSON list
    judge_why          TEXT NOT NULL DEFAULT '{}',  -- JSON: dungeon_judge's reasons, as written
    econ_why           TEXT NOT NULL DEFAULT '{}',  -- JSON: econ_row.measure's reasons
    items_table_sha256 TEXT,              -- the item table the run was judged with (16 hex)
    judge_value        TEXT,              -- JSON snapshot: dungeon_judge.items_value at build
    econ_row           TEXT,              -- JSON snapshot: econ_row.measure's zeny block at build
    judge_commit       TEXT,              -- the judges' code: git HEAD (+dirty), NULL without git
    built_at           TEXT NOT NULL,
    CHECK (window_t1_ns >= window_t0_ns),
    CHECK (kills >= 0 AND deaths >= 0)
)"""
_ITEMS = """
CREATE TABLE run_items (
    session           TEXT NOT NULL REFERENCES runs (session) ON DELETE CASCADE,
    item_id           INTEGER NOT NULL,
    picked            INTEGER NOT NULL,   -- a gain <= 2 s after our pickup request
    stolen            INTEGER NOT NULL,   -- stolen_steal + stolen_snatcher
    stolen_steal      INTEGER NOT NULL,
    stolen_snatcher   INTEGER NOT NULL,
    income            INTEGER NOT NULL,   -- picked + stolen: the bot's own gains
    other             INTEGER NOT NULL,   -- not income
    staged            INTEGER NOT NULL,   -- not income
    dropped           INTEGER NOT NULL,   -- units our kills dropped
    picked_of_dropped INTEGER NOT NULL,   -- of those, units our pickups took
    PRIMARY KEY (session, item_id),
    CHECK (stolen = stolen_steal + stolen_snatcher),
    CHECK (income = picked + stolen)
)"""
_SPECIES = """
CREATE TABLE run_species (
    session TEXT NOT NULL REFERENCES runs (session) ON DELETE CASCADE,
    mob_id  INTEGER NOT NULL,             -- -1: no monster appear before the kill
    kills   INTEGER NOT NULL,
    PRIMARY KEY (session, mob_id)
)"""
_CONSUMABLES = """
CREATE TABLE run_consumables (
    session TEXT NOT NULL REFERENCES runs (session) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    used    INTEGER NOT NULL,             -- OUR successful uses in the window
    PRIMARY KEY (session, item_id)
)"""

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (_RUNS, _ITEMS, _SPECIES, _CONSUMABLES),  # 1 (2026-11-12, ADR-0025 phase 1): the first schema
)


def latest() -> int:
    """The schema version this code writes: the number of migrations."""
    return len(MIGRATIONS)


_CREATES = ("CREATE TABLE ", "CREATE INDEX ", "CREATE UNIQUE INDEX ", "CREATE VIEW ")


def additive(stmt: str) -> bool:
    """PURE: True when a migration statement only ADDS: CREATE TABLE / INDEX / VIEW, or ALTER
    TABLE ... ADD [COLUMN]. Never DROP or RENAME; no DELETE / UPDATE / INSERT / trigger (a
    statement that does not start with one of those forms is refused). A foreign key's
    ``ON DELETE CASCADE`` inside a CREATE TABLE is a declaration, not a delete."""
    code = re.sub(r"--[^\n]*", " ", stmt)
    s = " ".join(code.split()).upper()
    if re.search(r"\b(DROP|RENAME)\b", s):
        return False
    return s.startswith(_CREATES) or bool(re.match(r"ALTER TABLE \S+ ADD (COLUMN )?\S", s))


def file_version(path: Path) -> int | None:
    """The schema version of the file at ``path``, read WITHOUT changing it: the header's
    user_version (offset 60). When a non-empty -wal log lies beside it, the log may be newer than
    the header, so SQLite is asked READ-ONLY. None when there is no file; an empty file is
    version 0 (SQLite's empty database). Refuses a file that is not SQLite."""
    try:
        with path.open("rb") as fh:
            head = fh.read(100)
    except FileNotFoundError:
        return None
    if not head:
        return 0
    if len(head) < 100 or not head.startswith(SQLITE_MAGIC):
        raise DbError(f"{path}: not a SQLite file. It was not changed.")
    version = int.from_bytes(head[60:64], "big", signed=True)
    wal = path.with_name(path.name + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        try:
            ro = sqlite3.connect(f"file:{quote(str(path.resolve()))}?mode=ro", uri=True)
            try:
                version = int(ro.execute("PRAGMA user_version").fetchone()[0])
            finally:
                ro.close()
        except sqlite3.Error as e:
            msg = f"{path}: cannot read its schema version ({e}). It was not changed."
            raise DbError(msg) from e
    return version


def migrate(con: sqlite3.Connection, path: Path) -> tuple[int, int]:
    """Bring the open file FORWARD to latest() in ONE transaction (all steps and the version bump,
    or nothing). Returns (version found, version now)."""
    steps = MIGRATIONS
    bad = [s for step in steps for s in step if not additive(s)]
    if bad:
        raise DbError(f"refused a migration that is not additive: {' '.join(bad[0].split())[:80]}")
    v = int(con.execute("PRAGMA user_version").fetchone()[0])
    if v == len(steps):
        return v, v
    con.execute("BEGIN IMMEDIATE")
    try:
        v = int(con.execute("PRAGMA user_version").fetchone()[0])  # again, under the write lock
        if v > len(steps):
            raise NewerDatabase(newer_message(path, v))
        for n in range(v, len(steps)):
            for stmt in steps[n]:
                con.execute(stmt)
        con.execute(f"PRAGMA user_version = {len(steps)}")
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return v, len(steps)


def connect(path: Path, create: bool = True) -> sqlite3.Connection:
    """The file at ``path`` (created when missing and ``create``), migrated FORWARD, in WAL mode,
    foreign keys on. A newer file is refused BEFORE it is opened for writing (NewerDatabase)."""
    v = file_version(path)
    if v is None and not create:
        raise DbError(f"{path}: no run records yet (econ_db.py build SESSION ...)")
    if v is not None and v > latest():
        raise NewerDatabase(newer_message(path, v))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        mode = str(con.execute("PRAGMA journal_mode = WAL").fetchone()[0]).lower()
        if mode != "wal":
            raise DbError(f"{path}: SQLite would not use WAL mode (journal_mode {mode})")
        migrate(con, path)
    except BaseException:
        con.close()
        raise
    return con


# --- rows -----------------------------------------------------------------------------------------

RUN_COLS = (
    "session",
    "dir",
    "map",
    "char",
    "strategy",
    "version",
    "window_t0_ns",
    "window_t1_ns",
    "window_source",
    "minutes",
    "hours",
    "kills",
    "deaths",
    "started",
    "ended",
    "flow_runner",
    "flow_strategy",
    "flow_search",
    "flow_label",
    "flow_flags",
    "judge_why",
    "econ_why",
    "items_table_sha256",
    "judge_value",
    "econ_row",
    "judge_commit",
    "built_at",
)
ITEM_COLS = (
    "item_id",
    "picked",
    "stolen",
    "stolen_steal",
    "stolen_snatcher",
    "income",
    "other",
    "staged",
    "dropped",
    "picked_of_dropped",
)
SPECIES_COLS = ("mob_id", "kills")
CONSUMABLE_COLS = ("item_id", "used")
CHILDREN = (
    ("run_items", "items", ITEM_COLS),
    ("run_species", "species", SPECIES_COLS),
    ("run_consumables", "consumables", CONSUMABLE_COLS),
)
# what a SHARED export leaves out of a run: the local directory, the judges' free-text reasons and
# the zeny snapshot (prices are rAthena-derived; a share carries ids and counts)
PRIVATE_RUN_COLS = ("dir", "judge_why", "econ_why", "items_table_sha256", "judge_value", "econ_row")
SHARE_RUN_COLS = tuple(c for c in RUN_COLS if c not in PRIVATE_RUN_COLS)


def _dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _loads(s: str | None) -> Any:
    return None if s is None else json.loads(s)


def sid_of(session: str) -> str:
    """The session id of a SESSION argument (a directory or an id), as econ_dash names it."""
    import dungeon_judge as dj

    return dj.session_dir(session).name


def record(
    j: Mapping[str, Any],
    entry: Mapping[str, Any],
    table_sha: str | None,
    commit: str | None,
    built_at: str,
) -> dict[str, Any]:
    """PURE: one judged run (econ_dash.judge_session ``j`` and its entry) as its rows -- the
    counts exactly as the entry has them, keyed by session id and numeric ids; no name, no price
    (the entry's own zeny snapshot aside)."""
    judged = j["judged"]
    w = entry["window"]
    flow = entry.get("flow") or {}
    run = {
        "session": str(entry["session"]),
        "dir": entry.get("dir"),
        "map": entry.get("map"),
        "char": entry.get("char"),
        "strategy": entry.get("strategy"),
        "version": entry.get("version"),
        "window_t0_ns": int(w["t0_ns"]),
        "window_t1_ns": int(w["t1_ns"]),
        "window_source": str(w["source"]),
        "minutes": entry.get("minutes"),
        "hours": float(entry["hours"]),
        "kills": int(entry["kills"]),
        "deaths": int(entry["deaths"]),
        "started": entry.get("started"),
        "ended": entry.get("ended"),
        "flow_runner": flow.get("runner"),
        "flow_strategy": flow.get("strategy"),
        "flow_search": flow.get("search"),
        "flow_label": flow.get("label"),
        "flow_flags": _dumps(list(flow.get("flags") or [])),
        "judge_why": _dumps(dict(judged.get("why") or {})),
        "econ_why": _dumps(dict((judged.get("economics") or {}).get("why") or {})),
        "items_table_sha256": table_sha,
        "judge_value": _dumps(entry.get("judge_value")),
        "econ_row": _dumps(entry.get("econ_row")),
        "judge_commit": commit,
        "built_at": built_at,
    }
    return {
        "run": run,
        "items": [{c: int(it[c]) for c in ITEM_COLS} for it in entry["items"]],
        "species": [{c: int(s[c]) for c in SPECIES_COLS} for s in entry["species"]],
        "consumables": [{c: int(x[c]) for c in CONSUMABLE_COLS} for x in entry["consumables"]],
    }


def _insert(
    con: sqlite3.Connection, table: str, cols: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    con.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


def has_run(con: sqlite3.Connection, sid: str) -> bool:
    return con.execute("SELECT 1 FROM runs WHERE session = ?", (sid,)).fetchone() is not None


def write_record(con: sqlite3.Connection, rec: Mapping[str, Any], replace: bool) -> str:
    """ONE transaction per run: its run row and every item / species / consumable row, or none of
    them (a failure rolls back, and a run being replaced keeps its old rows). Returns "added",
    "rebuilt", or "skipped" (already there and not ``replace``)."""
    sid = rec["run"]["session"]
    con.execute("BEGIN IMMEDIATE")
    try:
        had = has_run(con, sid)
        if had and not replace:
            con.execute("ROLLBACK")
            return "skipped"
        if had:
            for table, _key, _cols in CHILDREN:
                con.execute(f"DELETE FROM {table} WHERE session = ?", (sid,))
            con.execute("DELETE FROM runs WHERE session = ?", (sid,))
        _insert(con, "runs", RUN_COLS, [rec["run"]])
        for table, key, cols in CHILDREN:
            _insert(con, table, ("session", *cols), [{"session": sid, **r} for r in rec[key]])
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return "rebuilt" if had else "added"


def judge_commit(root: Path = ROOT) -> str | None:
    """The judges' code as git names it: HEAD's short id, "+dirty" when tracked files under
    scripts/ or packages/ differ from it; None without git or outside a checkout."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=True
        ).stdout.strip()

    try:
        head = git("rev-parse", "--short=12", "HEAD")
        dirty = git("status", "--porcelain", "--untracked-files=no", "--", "scripts", "packages")
    except (OSError, subprocess.SubprocessError):
        return None
    return (head + ("+dirty" if dirty else "")) or None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def ingest(
    con: sqlite3.Connection,
    sessions: Sequence[str],
    data: Path = DATA,
    map_name: str | None = None,
    replace: bool = True,
) -> list[dict[str, Any]]:
    """build (``replace``) or update: judge each session through econ_dash and write its rows,
    one transaction per run. A run econ_dash.check disagrees with, or a session that cannot be
    read, is refused (reported, nothing written for it); update skips a session id already in
    the file without judging it."""
    import econ_dash as ed

    tpath, tdoc, _names, _mobs = ed.sources(data)  # the item table is required, as for export
    table = tdoc["items"]
    sha = ed.table_sha(tpath)
    commit = judge_commit()
    out: list[dict[str, Any]] = []
    for s in sessions:
        sid = sid_of(s)
        if not replace and has_run(con, sid):
            out.append({"session": sid, "result": "skipped", "why": "already in the file"})
            continue
        try:
            j = ed.judge_session(s, table, map_name, data / "econ" / "maps.json")
        except OSError as e:
            out.append({"session": sid, "result": "refused", "why": f"{type(e).__name__}: {e}"})
            continue
        entry = ed.entry_of(j, table, {}, {})
        bad = ed.check(entry)
        if bad:
            out.append({"session": sid, "result": "refused", "why": {"cross_check_failed": bad}})
            continue
        rec = record(j, entry, sha, commit, _now())
        result = write_record(con, rec, replace)
        out.append(
            {
                "session": sid,
                "result": result,
                "hours": rec["run"]["hours"],
                "kills": rec["run"]["kills"],
                "items": len(rec["items"]),
                "species": len(rec["species"]),
                "consumables": len(rec["consumables"]),
            }
        )
    return out


# --- reading back ---------------------------------------------------------------------------------


def stored(con: sqlite3.Connection, sid: str) -> dict[str, Any]:
    """One run's stored rows: {"run": {...}, "items": [...], "species": [...], "consumables":
    [...]}, children ordered by id. Raises DbError when the run is not in the file."""
    r = con.execute(f"SELECT {', '.join(RUN_COLS)} FROM runs WHERE session = ?", (sid,)).fetchone()
    if r is None:
        raise DbError(f"run {sid} is not in the file (econ_db.py list; build or update it first)")
    out: dict[str, Any] = {"run": dict(zip(RUN_COLS, tuple(r), strict=True))}
    for table, key, cols in CHILDREN:
        rows = con.execute(
            f"SELECT {', '.join(cols)} FROM {table} WHERE session = ? ORDER BY {cols[0]}", (sid,)
        ).fetchall()
        out[key] = [dict(zip(cols, tuple(x), strict=True)) for x in rows]
    return out


def judged_of(rows: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: a run's stored rows back in econ_dash.judge_session's shape (the judge's row, the
    drops, the uses, the directory, the clock) -- what econ_dash.entry_of composes an entry from."""
    run = rows["run"]
    econ = dict(_loads(run["econ_row"]) or {})
    econ["why"] = _loads(run["econ_why"]) or {}
    econ["kill_mix"] = {str(s["mob_id"]): int(s["kills"]) for s in rows["species"]}
    judged = {
        "session": run["session"],
        "map": run["map"],
        "char": run["char"],
        "strategy": run["strategy"],
        "version": run["version"],
        "window": {
            "t0": int(run["window_t0_ns"]),
            "t1": int(run["window_t1_ns"]),
            "source": run["window_source"],
        },
        "minutes": run["minutes"],
        "kills": int(run["kills"]),
        "deaths": int(run["deaths"]),
        "items": [
            {
                "item_id": int(it["item_id"]),
                "picked": int(it["picked"]),
                "stolen": int(it["stolen_steal"]),
                "snatched": int(it["stolen_snatcher"]),
                "other": int(it["other"]),
                "staged": int(it["staged"]),
            }
            for it in rows["items"]
        ],
        "economics": econ,
        "why": _loads(run["judge_why"]) or {},
        "value": _loads(run["judge_value"]),
    }
    drops = {
        int(it["item_id"]): {"dropped": int(it["dropped"]), "picked": int(it["picked_of_dropped"])}
        for it in rows["items"]
        if it["dropped"] or it["picked_of_dropped"]
    }
    used = [int(c["item_id"]) for c in rows["consumables"] for _ in range(int(c["used"]))]
    clock = {
        "started": run["started"],
        "ended": run["ended"],
        "flow": {
            "runner": run["flow_runner"],
            "strategy": run["flow_strategy"],
            "search": run["flow_search"],
            "label": run["flow_label"],
            "flags": _loads(run["flow_flags"]) or [],
        },
    }
    return {"judged": judged, "drops": drops, "used": used, "where": run["dir"], "clock": clock}


def run_ids(con: sqlite3.Connection) -> list[str]:
    return [str(r[0]) for r in con.execute("SELECT session FROM runs ORDER BY session")]


def listing(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute(
        """SELECT r.session, r.map, r.char, r.minutes, r.kills, r.deaths,
                  COALESCE(SUM(i.income), 0), r.built_at, r.judge_commit
           FROM runs r LEFT JOIN run_items i ON i.session = r.session
           GROUP BY r.session ORDER BY r.session"""
    ).fetchall()
    keys = ("session", "map", "char", "minutes", "kills", "deaths", "income_units", "built_at",
            "judge_commit")  # fmt: skip
    return [dict(zip(keys, tuple(r), strict=True)) for r in rows]


class CrossCheckFailed(DbError):
    def __init__(self, bad: Mapping[str, Sequence[str]]) -> None:
        self.bad = dict(bad)
        super().__init__(json.dumps({"cross_check_failed": self.bad}, indent=1))


def dashboard(con: sqlite3.Connection, sids: Sequence[str], name: str, data: Path = DATA
              ) -> dict[str, Any]:  # fmt: skip
    """The econ_dash export document of these runs, from the file: each entry composed by
    econ_dash.entry_of from the stored counts with the item table and names of today, pooled and
    wrapped by econ_dash.document -- the same functions `econ_dash.py export` uses. Every entry
    passes econ_dash.check, or nothing is returned (CrossCheckFailed; when the item table changed
    since the run was built, the hint says to build it again)."""
    import econ_dash as ed

    tpath, tdoc, names, mobs = ed.sources(data)
    table = tdoc["items"]
    sha = ed.table_sha(tpath)
    runs: list[dict[str, Any]] = []
    bad: dict[str, list[str]] = {}
    for s in sids:
        rows = stored(con, sid_of(s))
        entry = ed.entry_of(judged_of(rows), table, names, mobs)
        problems = ed.check(entry)
        if problems:
            built = rows["run"]["items_table_sha256"]
            if built != sha:
                problems.append(
                    f"the item table changed since this run was built ({built} -> {sha}): "
                    f"econ_db.py build {rows['run']['session']} again"
                )
            bad[str(rows["run"]["session"])] = problems
        runs.append(entry)
    if bad:
        raise CrossCheckFailed(bad)
    return ed.document(runs, name, tpath, tdoc, names, mobs)


# --- exports for sharing --------------------------------------------------------------------------


def share_rows(
    con: sqlite3.Connection, sids: Sequence[str] | None = None, names: Any = None
) -> list[dict[str, Any]]:
    """The runs (all, or ``sids``) as shareable records: ids and counts (SHARE_RUN_COLS, the
    children's counts); ``names`` (item_name, mob_name) adds a name to each child row."""
    want = run_ids(con) if not sids else [sid_of(s) for s in sids]
    have = set(run_ids(con))
    missing = [s for s in want if s not in have]
    if missing:
        raise DbError(f"not in the file: {missing} (econ_db.py list)")
    out = []
    for sid in want:
        rows = stored(con, sid)
        run: dict[str, Any] = {c: rows["run"][c] for c in SHARE_RUN_COLS}
        run["flow_flags"] = _loads(run["flow_flags"]) or []
        for _table, key, _cols in CHILDREN:
            kids = [dict(r) for r in rows[key]]
            if names is not None:
                item_name, mob_name = names
                for k in kids:
                    k["name"] = (
                        mob_name(k["mob_id"]) if key == "species" else item_name(k["item_id"])
                    )
            run[key] = kids
        out.append(run)
    return out


def local_names(data: Path = DATA) -> tuple[Any, Any]:
    """(item id -> name, mob id -> name) from YOUR data/ (the KB, else the item table), the way
    econ_dash names them; None where data/ has no name."""
    import econ_dash as ed
    import econ_items

    names = ed._names(data / "kb" / "items.json")
    mobs = ed._names(data / "kb" / "mobs.json")
    try:
        table = econ_items.load(data / "econ" / "items.json")["items"]
    except FileNotFoundError:
        table = {}
    return (lambda i: ed._name(int(i), names, table)), (lambda m: mobs.get(str(m)))


def _atomic(path: Path, write: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    write(tmp)
    tmp.replace(path)
    return path


def csv_paths(out: Path) -> dict[str, Path]:
    """The CSV files of an export: the runs in ``out``, the children beside it."""
    paths = {"runs": out}
    for _table, key, _cols in CHILDREN:
        paths[key] = out.with_name(f"{out.stem}_{key}{out.suffix or '.csv'}")
    return paths


def export(runs: Sequence[Mapping[str, Any]], fmt: str, out: Path, with_names: bool,
           db_version: int) -> list[Path]:  # fmt: skip
    """Write the shareable records as JSON (one file) or CSV (one file per table)."""
    if fmt == "json":
        doc = {
            "schema": EXPORT_SCHEMA,
            "exported_at": _now(),
            "db_schema_version": db_version,
            "names": with_names,
            "is": "judged counts per run (ids and counts; hours = the judged window); no prices",
            "runs": list(runs),
        }
        text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
        return [_atomic(out, lambda p: p.write_text(text, encoding="utf-8"))]
    if fmt != "csv":
        raise DbError(f"--format {fmt!r}: csv or json")
    paths = csv_paths(out)
    run_cols = list(SHARE_RUN_COLS)
    written = []

    def table_writer(cols: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> Any:
        def w(p: Path) -> None:
            with p.open("w", newline="", encoding="utf-8-sig") as fh:
                wr = csv.DictWriter(fh, fieldnames=list(cols))
                wr.writeheader()
                wr.writerows(rows)

        return w

    flat = [{**{c: r[c] for c in run_cols}, "flow_flags": " ".join(r["flow_flags"])} for r in runs]
    written.append(_atomic(paths["runs"], table_writer(run_cols, flat)))
    for _table, key, cols in CHILDREN:
        kcols = ["session", *cols, *(["name"] if with_names else [])]
        rows = [{"session": r["session"], **k} for r in runs for k in r[key]]
        written.append(_atomic(paths[key], table_writer(kcols, rows)))
    return written


# --- the command line -----------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--db", type=Path, default=None, help="default: <data>/econ/lab.sqlite")
        p.add_argument(
            "--data",
            type=Path,
            default=DATA,
            help="the data directory (econ/items.json, kb/) (default: the repo's)",
        )

    for cmd in ("build", "update"):
        p = sub.add_parser(cmd)
        p.add_argument("sessions", nargs="+", help="session directories or ids")
        p.add_argument("--map", default=None, help="the runs' map (default: run_start's)")
        common(p)
    common(sub.add_parser("list"))
    x = sub.add_parser("export")
    x.add_argument("--format", choices=("csv", "json"), required=True)
    x.add_argument("--out", type=Path, required=True)
    x.add_argument("--runs", nargs="+", default=None, help="session ids (default: every run)")
    x.add_argument("--with-names", action="store_true", help="names from YOUR data/, not shared")
    common(x)
    d = sub.add_parser("dashboard")
    d.add_argument("--runs", nargs="+", required=True, help="session ids")
    d.add_argument("--name", required=True)
    d.add_argument("--out-dir", type=Path, default=None, help="default: <data>/econ/dashboard")
    common(d)
    a = ap.parse_args(argv)
    db = a.db or default_db(a.data)
    try:
        return _run(a, db)
    except DbError as e:
        print(str(e), file=sys.stderr)
        return 1
    except FileNotFoundError as e:  # the item table (econ_items.load names the command to run)
        print(str(e), file=sys.stderr)
        return 1


def _run(a: argparse.Namespace, db: Path) -> int:
    import econ_dash as ed

    if a.cmd == "dashboard" and not ed.valid_name(a.name):
        raise DbError(f"--name {a.name!r}: [A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}")
    if a.cmd in ("build", "update"):
        ed.sources(a.data)  # the item table first: a missing one creates no file
    con = connect(db, create=a.cmd in ("build", "update"))
    try:
        if a.cmd in ("build", "update"):
            res = ingest(con, a.sessions, a.data, a.map, replace=a.cmd == "build")
            for r in res:
                print(json.dumps(r, ensure_ascii=False))
            print(json.dumps({"db": str(db), "runs": len(run_ids(con))}))
            return 1 if any(r["result"] == "refused" for r in res) else 0
        if a.cmd == "list":
            print(
                json.dumps({"db": str(db), "schema_version": latest(), "runs": len(run_ids(con))})
            )
            for row in listing(con):
                print(json.dumps(row, ensure_ascii=False))
            return 0
        if a.cmd == "export":
            names = local_names(a.data) if a.with_names else None
            runs = share_rows(con, a.runs, names)
            paths = export(runs, a.format, a.out, a.with_names, latest())
            print(json.dumps({"runs": len(runs), "out": [str(p) for p in paths]}))
            if a.with_names:
                print(
                    "note: names are run-time data from your data/ (rAthena / client-derived): "
                    "keep this export local, never commit or publish it",
                    file=sys.stderr,
                )
            return 0
        doc = dashboard(con, a.runs, a.name, a.data)
        path = ed.write(doc, a.out_dir or a.data / "econ" / "dashboard")
        print(
            json.dumps({"out": str(path), "bytes": path.stat().st_size, "runs": len(doc["runs"])})
        )
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
