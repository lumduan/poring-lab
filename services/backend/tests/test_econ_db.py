"""RUN RECORDS IN ONE LOCAL SQLITE FILE (scripts/econ_db.py, ADR-0025 phase 1, Batt 2026-11-12):
the stored counts equal econ_dash's per-run export for the same sessions, the dashboard rebuilt
from the file equals `econ_dash.py export`, update is idempotent by session id, a failed write
leaves no half run, the schema version migrates FORWARD and a newer file is refused unchanged,
WAL, the shareable exports (ids and counts; no names by default), and the file is gitignored.
Synthetic sessions are built the way test_econ_dash.py builds them, with SYNTHETIC ids, prices
and names (92xxx / 93xxx; "made-up-*"); the REAL case reads banked sessions and is skipped when
they are absent."""

from __future__ import annotations

import csv
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import dungeon_judge as dj  # noqa: E402
import econ_dash as ed  # noqa: E402
import econ_db as edb  # noqa: E402
import econ_items as ei  # noqa: E402

S = 10**9
A = dj.AID
LOOT_A, LOOT_B, UNPRICED = 92001, 92002, 92200  # synthetic item ids
POTION, NO_SHOP = 92100, 92300  # synthetic consumables (a db type Healing; one no NPC sells)
MOB_X, MOB_Y = 93001, 93002  # synthetic species


def _row(
    sell: int, typ: str = "Etc", weight: float = 1.0, buy: int | None = None
) -> dict[str, Any]:
    """A synthetic item-table row, its derived prices by econ_items' own rules."""
    return {
        "name": None,
        "type": typ,
        "weight": weight,
        "sellable": True,
        "sell": sell,
        "sell_oc10": ei.overcharge(sell),
        "npc_buy": buy,
        "npc_buy_dc10": None if buy is None else ei.discount(buy),
    }


TABLE = {
    str(LOOT_A): _row(40, weight=2.0),
    str(LOOT_B): _row(7),
    str(POTION): _row(25, "Healing", 7.0, buy=50),
    str(NO_SHOP): _row(1, "Usable"),
}
ITEM_NAMES = {str(LOOT_A): {"name": "made-up-a"}, str(POTION): {"name": "made-up-p"}}
MOB_NAMES = {str(MOB_X): {"name": "made-up-x"}}

# (species, item it drops, picked?, a Snatcher gain of this item inside the attack)
PLAN_1 = [
    (MOB_X, LOOT_A, True, None),
    (MOB_X, LOOT_A, False, None),
    (MOB_X, LOOT_B, True, LOOT_A),
    (MOB_Y, LOOT_B, True, UNPRICED),
]
PLAN_2 = [(MOB_Y, LOOT_B, True, None), (MOB_Y, LOOT_A, True, LOOT_B), (MOB_X, LOOT_B, False, None)]
USES_1 = [
    (400, POTION, A),
    (700, POTION, A),
    (401, POTION, 123),
    (800, NO_SHOP, A),
    (1801, POTION, A),
]
USES_2 = [(300, POTION, A)]


def pk(t: float, **kw: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t * S), **kw}


def ev(t: float, kind: str, **kw: Any) -> dict[str, Any]:
    return {"t_ns": int(t * S), "kind": kind, **kw}


def a_session(
    t0: float,
    plan: list[tuple[int, int, bool, int | None]],
    uses: list[tuple[float, int, int]],
    death_at: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A 30-minute Rogue run (test_econ_dash.a_session's packets): per kill an appear, our attack
    request and act, one drop, the vanish; a pickup when ``picked``; a Snatcher gain inside the
    attack; one unexplained gain (not income); item uses (ours and somebody else's; one after the
    run's end); a death of ours when ``death_at``."""
    events = [
        ev(
            t0, "run_start", strategy="P2", seed=1, version="dungeon@t", map="testmap", char="rogue"
        ),
        ev(t0 + 1800, "run_end", reason="time_box", counts={}),
    ]
    packets: list[dict[str, Any]] = []
    for k, (mob, item, picked, snatch) in enumerate(plan):
        t, g, f = t0 + 60 + 300 * k, 1000 + k, 5000 + k
        packets += [
            pk(t - 10, type="entity_appear", gid=g, objtype=5, x=10, y=10, job=mob),
            pk(t - 0.5, type="attack_request", target_gid=g, action=7, kind="repeat",
               is_attack=True),
            pk(t, type="act", src_gid=A, target_gid=g, damage=300, kind="normal", action=0),
            pk(t + 0.2, type="floor_item_appear", kind="fall", floor_id=f, item_id=item, x=10,
               y=10, amount=1, identified=True, sub_x=0, sub_y=0),
            pk(t + 0.5, type="entity_vanish", gid=g, reason=1),
        ]  # fmt: skip
        if snatch is not None:
            packets.append(pk(t + 0.3, type="pickup_result", ok=True, item_id=snatch, amount=1))
        if picked:
            packets += [
                pk(t + 2, type="pickup_request", floor_id=f),
                pk(t + 2.1, type="pickup_result", ok=True, item_id=item, amount=1),
                pk(t + 2.1, type="floor_item_vanish", floor_id=f),
            ]
    packets.append(pk(t0 + 1500, type="pickup_result", ok=True, item_id=LOOT_B, amount=1))
    for dt, iid, aid in uses:
        packets.append(pk(t0 + dt, type="use_item_result", item_id=iid, aid=aid, ok=True))
    if death_at is not None:
        packets.append(pk(t0 + death_at, type="entity_vanish", gid=A, reason=1))
    return events, sorted(packets, key=lambda e: e["t_mono_ns"])


def write_session(
    root: Path, sid: str, events: list[dict[str, Any]], packets: list[dict[str, Any]]
) -> Path:
    d = root / sid
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    with gzip.open(d / "packets.jsonl.gz", "wt") as fh:
        fh.writelines(json.dumps(p) + "\n" for p in packets)
    man = {"map": "testmap", "char": "rogue", "version": "dungeon@t",
           "fixes": {"flag_b": [1], "flag_a": [2]}}  # fmt: skip
    (d / "manifest.json").write_text(json.dumps(man))
    return d


def write_data(data: Path, table: dict[str, Any] = TABLE) -> None:
    """A synthetic data/: the item table (econ_items' shape) and the KB's names."""
    (data / "econ").mkdir(parents=True, exist_ok=True)
    (data / "kb").mkdir(parents=True, exist_ok=True)
    meta = {"rathena_ref": "synthetic", "mode": "pre-re", "built_at": "2026-11-12T00:00:00+0700"}
    (data / "econ" / "items.json").write_text(json.dumps({"meta": meta, "items": table}))
    (data / "kb" / "items.json").write_text(json.dumps(ITEM_NAMES))
    (data / "kb" / "mobs.json").write_text(json.dumps(MOB_NAMES))


@pytest.fixture
def lab(tmp_path: Path) -> SimpleNamespace:
    data = tmp_path / "data"
    write_data(data)
    root = tmp_path / "sessions"
    s1 = write_session(root, "20261112T010000-synthetic-r1", *a_session(100.0, PLAN_1, USES_1))
    s2 = write_session(
        root, "20261112T020000-synthetic-r2", *a_session(5000.0, PLAN_2, USES_2, death_at=900)
    )
    return SimpleNamespace(data=data, s1=s1, s2=s2, db=tmp_path / "db" / "lab.sqlite")


def cli(lab: SimpleNamespace, *args: str) -> int:
    return edb.main([*args, "--db", str(lab.db), "--data", str(lab.data)])


def built(lab: SimpleNamespace, *sessions: Path) -> sqlite3.Connection:
    con = edb.connect(lab.db)
    res = edb.ingest(con, [str(s) for s in sessions], lab.data)
    assert [r["result"] for r in res] == ["added"] * len(sessions), res
    return con


def counts_of_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """The counts of an econ_dash entry, the shape db_counts gives."""
    keys = ("session", "dir", "map", "char", "strategy", "version", "minutes", "hours", "kills",
            "deaths", "started", "ended", "window", "flow")  # fmt: skip
    return {
        "run": {k: entry[k] for k in keys},
        "items": {it["item_id"]: {c: it[c] for c in edb.ITEM_COLS[1:]} for it in entry["items"]},
        "species": {s["mob_id"]: s["kills"] for s in entry["species"]},
        "consumables": {c["item_id"]: c["used"] for c in entry["consumables"]},
    }


def db_counts(con: sqlite3.Connection, sid: str) -> dict[str, Any]:
    r = edb.stored(con, sid)
    run = r["run"]
    flags = json.loads(run["flow_flags"])
    return {
        "run": {
            **{
                k: run[k]
                for k in (
                    "session",
                    "dir",
                    "map",
                    "char",
                    "strategy",
                    "version",
                    "minutes",
                    "hours",
                    "kills",
                    "deaths",
                    "started",
                    "ended",
                )
            },
            "window": {
                "t0_ns": run["window_t0_ns"],
                "t1_ns": run["window_t1_ns"],
                "source": run["window_source"],
            },
            "flow": {
                "runner": run["flow_runner"],
                "strategy": run["flow_strategy"],
                "search": run["flow_search"],
                "label": run["flow_label"],
                "flags": flags,
            },
        },
        "items": {it["item_id"]: {c: it[c] for c in edb.ITEM_COLS[1:]} for it in r["items"]},
        "species": {s["mob_id"]: s["kills"] for s in r["species"]},
        "consumables": {c["item_id"]: c["used"] for c in r["consumables"]},
    }


def dump(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of our tables, read-only."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {t: sorted(con.execute(f"SELECT * FROM {t}").fetchall())
                for t in ("runs", "run_items", "run_species", "run_consumables")}  # fmt: skip
    finally:
        con.close()


# --- the cross-check: the file's counts ARE econ_dash's ------------------------------------------


def test_the_stored_counts_equal_econ_dash_per_run_export(lab: SimpleNamespace) -> None:
    con = built(lab, lab.s1, lab.s2)
    for d in (lab.s1, lab.s2):
        entry = ed.export_run(str(d), TABLE, {}, {})
        assert ed.check(entry) == []
        assert db_counts(con, d.name) == counts_of_entry(entry)
        # plain SQL, as a learner would ask it
        k, h, inc = con.execute(
            "SELECT r.kills, r.hours, SUM(i.income) FROM runs r JOIN run_items i "
            "ON i.session = r.session WHERE r.session = ? GROUP BY r.session",
            (d.name,),
        ).fetchone()
        assert (k, h, inc) == (entry["kills"], entry["hours"], entry["totals"]["income_units"])
    r1 = db_counts(con, lab.s1.name)  # the plan by hand (test_econ_dash's run): never by a name
    assert (r1["run"]["kills"], r1["run"]["deaths"], r1["run"]["hours"]) == (4, 0, 0.5)
    assert r1["items"][LOOT_A] == {"picked": 1, "stolen": 1, "stolen_steal": 0,
                                   "stolen_snatcher": 1, "income": 2, "other": 0, "staged": 0,
                                   "dropped": 2, "picked_of_dropped": 1}  # fmt: skip
    assert (r1["items"][LOOT_B]["other"], r1["items"][UNPRICED]["income"]) == (1, 1)
    assert r1["species"] == {MOB_X: 3, MOB_Y: 1}
    assert r1["consumables"] == {POTION: 2, NO_SHOP: 1}  # ours in the window only
    assert r1["run"]["flow"]["flags"] == ["flag_a", "flag_b"]
    r2 = db_counts(con, lab.s2.name)
    assert (r2["run"]["kills"], r2["run"]["deaths"]) == (3, 1)
    run = edb.stored(con, lab.s1.name)["run"]
    assert run["items_table_sha256"] == ed.table_sha(lab.data / "econ" / "items.json")
    assert (
        json.loads(run["judge_value"])["value"]
        == ed.export_run(str(lab.s1), TABLE, {}, {})["judge_value"]["value"]
    )
    assert run["judge_commit"] is None or len(run["judge_commit"].split("+")[0]) == 12


def test_the_dashboard_from_the_file_is_the_same_json_econ_dash_writes(
    lab: SimpleNamespace, tmp_path: Path
) -> None:
    con = built(lab, lab.s1, lab.s2)
    sessions = [str(lab.s1), str(lab.s2)]
    want = ed.build(sessions, "pair", lab.data)
    got = edb.dashboard(con, [lab.s1.name, lab.s2.name], "pair", lab.data)
    for doc in (want, got):
        doc.pop("exported_at")
    assert json.dumps(got, indent=1) == json.dumps(want, indent=1)  # every key, in order
    assert got["runs"][0]["species"][0]["name"] == "made-up-x"  # names from data/ at query time
    con.close()
    out = tmp_path / "dash"
    assert cli(lab, "dashboard", "--runs", lab.s1.name, lab.s2.name, "--name", "p1",
               "--out-dir", str(out)) == 0  # fmt: skip
    doc = json.loads((out / "p1.json").read_text())
    assert doc["schema"] == ed.SCHEMA and doc["pooled"]["kills"] == 7
    assert doc["pooled"]["totals"] == want["pooled"]["totals"]


def test_the_dashboard_refuses_when_the_item_table_changed(
    lab: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(lab, lab.s1).close()
    write_data(lab.data, {**TABLE, str(LOOT_A): _row(41, weight=2.0)})  # a price edited
    out = tmp_path / "dash"
    assert cli(lab, "dashboard", "--runs", lab.s1.name, "--name", "x", "--out-dir", str(out)) == 1
    err = capsys.readouterr().err
    assert "item table changed" in err and f"econ_db.py build {lab.s1.name}" in err
    assert not out.exists()  # nothing written
    assert cli(lab, "build", str(lab.s1)) == 0  # re-judged at today's prices
    assert cli(lab, "dashboard", "--runs", lab.s1.name, "--name", "x", "--out-dir", str(out)) == 0


# --- build / update -------------------------------------------------------------------------------


def test_update_adds_only_session_ids_not_yet_in_the_file(
    lab: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli(lab, "update", str(lab.s1)) == 0
    first = dump(lab.db)
    assert len(first["runs"]) == 1
    assert cli(lab, "update", str(lab.s1), str(lab.s1)) == 0
    assert cli(lab, "update", lab.s1.name) == 0  # by id: skipped before any session file is read
    assert dump(lab.db) == first  # nothing changed, built_at included
    capsys.readouterr()
    assert cli(lab, "update", str(lab.s1), str(lab.s2)) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [(x.get("session"), x.get("result")) for x in lines[:2]] == [
        (lab.s1.name, "skipped"),
        (lab.s2.name, "added"),
    ]
    after = dump(lab.db)
    assert len(after["runs"]) == 2
    assert [r for r in after["runs"] if r[0] == lab.s1.name] == first["runs"]


def test_build_rebuilds_a_run_in_place(lab: SimpleNamespace) -> None:
    con = built(lab, lab.s1)
    before = db_counts(con, lab.s1.name)
    res = edb.ingest(con, [str(lab.s1)], lab.data)
    assert [r["result"] for r in res] == ["rebuilt"]
    assert edb.run_ids(con) == [lab.s1.name] and db_counts(con, lab.s1.name) == before


def test_a_failed_write_leaves_no_half_run(lab: SimpleNamespace) -> None:
    """One transaction per run: a failure after the run row (a duplicate key, a CHECK, a Python
    error mid-insert, as a crash would) leaves no part of it, and a run being rebuilt keeps its
    old rows."""
    con = edb.connect(lab.db)
    j = ed.judge_session(str(lab.s1), TABLE)
    rec = edb.record(j, ed.entry_of(j, TABLE, {}, {}), "sha", None, "now")
    sid = lab.s1.name
    dup = {**rec, "species": [*rec["species"], rec["species"][0]]}
    bad_count = {**rec, "items": [{**rec["items"][0], "income": rec["items"][0]["income"] + 1}]}
    crash = {**rec, "consumables": [{"item_id": POTION}]}  # KeyError inside the transaction
    for broken, exc in ((dup, sqlite3.IntegrityError), (crash, KeyError)):
        with pytest.raises(exc):
            edb.write_record(con, broken, replace=True)
        assert edb.run_ids(con) == []
        assert all(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
                   for t, _k, _c in edb.CHILDREN)  # fmt: skip
    assert edb.write_record(con, rec, replace=True) == "added"
    before = edb.stored(con, sid)
    for broken, exc in ((dup, sqlite3.IntegrityError), (bad_count, sqlite3.IntegrityError),
                        (crash, KeyError)):  # fmt: skip
        with pytest.raises(exc):
            edb.write_record(con, broken, replace=True)
        assert edb.stored(con, sid) == before
    assert edb.write_record(con, rec, replace=False) == "skipped"


def test_a_session_that_cannot_be_read_is_refused_and_nothing_is_written(
    lab: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli(lab, "build", str(tmp_path / "20261112T030000-missing"), str(lab.s1)) == 1
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x.get("result") for x in lines[:2]] == ["refused", "added"]
    assert [r[0] for r in dump(lab.db)["runs"]] == [lab.s1.name]


def test_no_item_table_refuses_before_any_file_is_made(
    lab: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty-data"
    empty.mkdir()
    db = tmp_path / "x" / "lab.sqlite"
    assert edb.main(["build", str(lab.s1), "--db", str(db), "--data", str(empty)]) == 1
    assert "econ_items.py build" in capsys.readouterr().err and not db.exists()


def test_list_and_a_missing_file(lab: SimpleNamespace, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(lab, "list") == 1 and "no run records yet" in capsys.readouterr().err
    assert not lab.db.exists()  # a reader never creates the file
    built(lab, lab.s1, lab.s2).close()
    assert cli(lab, "list") == 0
    head, *rows = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert head["runs"] == 2 and head["schema_version"] == edb.latest()
    assert [(r["session"], r["kills"], r["income_units"]) for r in rows] == [
        (lab.s1.name, 4, 5),  # LOOT_A 2 + LOOT_B 2 + UNPRICED 1 (the "other" gain is out)
        (lab.s2.name, 3, 3),
    ]


# --- the schema version: forward only; a newer file refused, unchanged ----------------------------


def _tables(path: Path) -> set[str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()


def _version(path: Path) -> int:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return int(con.execute("PRAGMA user_version").fetchone()[0])
    finally:
        con.close()


def test_an_empty_file_becomes_version_1_in_wal_mode(lab: SimpleNamespace) -> None:
    lab.db.parent.mkdir(parents=True)
    lab.db.touch()  # version 0: SQLite's empty database
    assert edb.file_version(lab.db) == 0
    con = edb.connect(lab.db)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    con.close()
    assert edb.latest() == 1 and _version(lab.db) == 1
    assert {"runs", "run_items", "run_species", "run_consumables"} <= _tables(lab.db)
    raw = sqlite3.connect(lab.db)  # WAL is the file's own mode, not only this connection's
    assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    raw.close()


def test_a_version_0_file_keeps_its_own_rows(lab: SimpleNamespace) -> None:
    lab.db.parent.mkdir(parents=True)
    raw = sqlite3.connect(lab.db)
    raw.execute("CREATE TABLE notes (t TEXT)")
    raw.execute("INSERT INTO notes VALUES ('mine')")
    raw.commit()
    raw.close()
    edb.connect(lab.db).close()
    con = sqlite3.connect(lab.db)
    assert con.execute("SELECT t FROM notes").fetchall() == [("mine",)]
    con.close()
    assert _version(lab.db) == 1 and "runs" in _tables(lab.db)


def test_an_older_file_is_migrated_forward_and_keeps_every_row(
    lab: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    built(lab, lab.s1).close()
    before = dump(lab.db)
    v2 = (*edb.MIGRATIONS, ("ALTER TABLE runs ADD COLUMN note TEXT",
                            "CREATE INDEX runs_by_map ON runs (map)"))  # fmt: skip
    monkeypatch.setattr(edb, "MIGRATIONS", v2)
    con = edb.connect(lab.db)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 2
    assert con.execute("SELECT note FROM runs").fetchall()[0][0] is None
    con.close()
    after = dump(lab.db)
    assert after["runs"] == [r + (None,) for r in before["runs"]]  # the new column only
    assert {k: v for k, v in after.items() if k != "runs"} == {
        k: v for k, v in before.items() if k != "runs"
    }


def test_a_failed_migration_rolls_back_whole(
    lab: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    built(lab, lab.s1).close()
    before = dump(lab.db)
    broken = (*edb.MIGRATIONS, ("CREATE TABLE extra (x INTEGER)", "CREATE TABLE broken ("))
    monkeypatch.setattr(edb, "MIGRATIONS", broken)
    with pytest.raises(sqlite3.OperationalError):
        edb.connect(lab.db)
    assert _version(lab.db) == 1 and "extra" not in _tables(lab.db)  # the bump rolled back too
    assert dump(lab.db) == before


def test_migrations_only_add(lab: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    assert all(edb.additive(s) for step in edb.MIGRATIONS for s in step)
    for ok in ("ALTER TABLE runs ADD COLUMN note TEXT", "CREATE INDEX i ON runs (map)",
               "CREATE VIEW v AS SELECT 1", "create table t (x int)"):  # fmt: skip
        assert edb.additive(ok), ok
    for bad in ("DROP TABLE runs", "DELETE FROM runs", "UPDATE runs SET kills = 0",
                "ALTER TABLE runs RENAME TO r2", "ALTER TABLE runs RENAME COLUMN kills TO k",
                "ALTER TABLE runs DROP COLUMN kills", "INSERT INTO runs DEFAULT VALUES",
                "CREATE TRIGGER t AFTER INSERT ON runs BEGIN DELETE FROM runs; END",
                "-- a comment\nDROP TABLE runs", "CREATE TABLE x AS SELECT 1; DROP TABLE runs",
                "REPLACE INTO runs DEFAULT VALUES"):  # fmt: skip
        assert not edb.additive(bad), bad
    built(lab, lab.s1).close()
    before = dump(lab.db)
    monkeypatch.setattr(edb, "MIGRATIONS", (*edb.MIGRATIONS, ("DROP TABLE run_species",)))
    with pytest.raises(edb.DbError, match="not additive"):
        edb.connect(lab.db)
    assert dump(lab.db) == before and _version(lab.db) == 1


def test_a_newer_file_is_refused_and_never_altered(
    lab: SimpleNamespace, capsys: pytest.CaptureFixture[str]
) -> None:
    built(lab, lab.s1).close()
    raw = sqlite3.connect(lab.db)
    raw.execute(f"PRAGMA user_version = {edb.latest() + 1}")  # a newer poring-lab's file
    raw.close()
    before = lab.db.read_bytes()
    files = sorted(p.name for p in lab.db.parent.iterdir())
    with pytest.raises(edb.NewerDatabase, match="made by a newer poring-lab: pull the update"):
        edb.connect(lab.db)
    capsys.readouterr()
    export = ("export", "--format", "json", "--out", str(lab.db.parent / "x.json"))
    for args in (("list",), ("update", str(lab.s2)), ("build", str(lab.s2)), export):
        assert cli(lab, *args) == 1, args
        assert "made by a newer poring-lab: pull the update" in capsys.readouterr().err
    assert lab.db.read_bytes() == before  # byte for byte
    assert sorted(p.name for p in lab.db.parent.iterdir()) == files  # no -wal / -shm, no export


def test_the_version_is_read_from_the_log_when_the_header_is_older(lab: SimpleNamespace) -> None:
    """In WAL mode a new user_version sits in the -wal log until a checkpoint: the header alone
    would say the old one. The check asks SQLite read-only then, and still changes nothing."""
    built(lab, lab.s1).close()
    holder = sqlite3.connect(lab.db, isolation_level=None)
    holder.execute("PRAGMA wal_autocheckpoint = 0")
    holder.execute(f"PRAGMA user_version = {edb.latest() + 1}")
    try:
        before = lab.db.read_bytes()
        assert int.from_bytes(before[60:64], "big") == edb.latest()  # the header is older
        assert edb.file_version(lab.db) == edb.latest() + 1
        with pytest.raises(edb.NewerDatabase):
            edb.connect(lab.db)
        assert lab.db.read_bytes() == before
    finally:
        holder.close()


def test_a_file_that_is_not_sqlite_is_refused_unchanged(lab: SimpleNamespace) -> None:
    lab.db.parent.mkdir(parents=True)
    lab.db.write_bytes(b"my own notes, not a database\n" * 10)
    before = lab.db.read_bytes()
    with pytest.raises(edb.DbError, match="not a SQLite file"):
        edb.connect(lab.db)
    assert lab.db.read_bytes() == before


# --- exports for sharing: ids and counts, names only on request -----------------------------------


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def test_exports_carry_ids_and_counts_and_no_names_by_default(
    lab: SimpleNamespace, tmp_path: Path
) -> None:
    con = built(lab, lab.s1, lab.s2)
    want = {sid: db_counts(con, sid) for sid in (lab.s1.name, lab.s2.name)}
    con.close()
    out = tmp_path / "share" / "class.csv"
    assert cli(lab, "export", "--format", "csv", "--out", str(out)) == 0
    paths = edb.csv_paths(out)
    assert sorted(p.name for p in paths.values()) == [
        "class.csv", "class_consumables.csv", "class_items.csv", "class_species.csv"]  # fmt: skip
    cols, runs = _read_csv(paths["runs"])
    assert cols == list(edb.SHARE_RUN_COLS)
    assert not set(edb.PRIVATE_RUN_COLS) & set(cols)  # no local path, no zeny snapshot
    assert [(r["session"], int(r["kills"]), float(r["hours"])) for r in runs] == [
        (sid, want[sid]["run"]["kills"], want[sid]["run"]["hours"]) for sid in want
    ]
    cols, items = _read_csv(paths["items"])
    assert cols == ["session", *edb.ITEM_COLS]
    got = {(r["session"], int(r["item_id"])): {c: int(r[c]) for c in edb.ITEM_COLS[1:]}
           for r in items}  # fmt: skip
    assert got == {(sid, iid): v for sid in want for iid, v in want[sid]["items"].items()}
    cols, species = _read_csv(paths["species"])
    assert cols == ["session", "mob_id", "kills"]
    assert {(r["session"], int(r["mob_id"])): int(r["kills"]) for r in species} == {
        (sid, m): k for sid in want for m, k in want[sid]["species"].items()
    }
    cols, cons = _read_csv(paths["consumables"])
    assert cols == ["session", "item_id", "used"] and len(cons) == 3
    jout = tmp_path / "share" / "class.json"
    assert cli(lab, "export", "--format", "json", "--out", str(jout)) == 0
    doc = json.loads(jout.read_text())
    assert doc["schema"] == edb.EXPORT_SCHEMA and doc["names"] is False
    assert [r["session"] for r in doc["runs"]] == list(want)
    r1 = doc["runs"][0]
    assert {it["item_id"]: {c: it[c] for c in edb.ITEM_COLS[1:]} for it in r1["items"]} == want[
        lab.s1.name
    ]["items"]
    assert r1["flow_flags"] == ["flag_a", "flag_b"]
    for p in [*paths.values(), jout]:
        text = p.read_text(encoding="utf-8-sig")
        assert "made-up-" not in text and str(lab.s1.parent) not in text  # no names, no paths
        assert '"name"' not in text and ",name" not in text


def test_an_export_with_names_reads_them_from_local_data(
    lab: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(lab, lab.s1).close()
    out = tmp_path / "local.json"
    assert cli(lab, "export", "--format", "json", "--out", str(out), "--with-names") == 0
    assert "keep this export local" in capsys.readouterr().err
    r = json.loads(out.read_text())["runs"][0]
    assert {it["item_id"]: it["name"] for it in r["items"]} == {
        LOOT_A: "made-up-a", LOOT_B: None, UNPRICED: None}  # fmt: skip
    assert {s["mob_id"]: s["name"] for s in r["species"]} == {MOB_X: "made-up-x", MOB_Y: None}
    assert {c["item_id"]: c["name"] for c in r["consumables"]} == {POTION: "made-up-p",
                                                                   NO_SHOP: None}  # fmt: skip
    cout = tmp_path / "local.csv"
    assert cli(lab, "export", "--format", "csv", "--out", str(cout), "--with-names") == 0
    cols, rows = _read_csv(edb.csv_paths(cout)["items"])
    assert cols[-1] == "name" and {r["name"] for r in rows} == {"made-up-a", ""}


def test_an_export_of_chosen_runs_and_of_an_unknown_one(
    lab: SimpleNamespace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    built(lab, lab.s1, lab.s2).close()
    out = tmp_path / "one.json"
    assert cli(lab, "export", "--format", "json", "--out", str(out), "--runs", str(lab.s2)) == 0
    assert [r["session"] for r in json.loads(out.read_text())["runs"]] == [lab.s2.name]
    assert cli(lab, "export", "--format", "json", "--out", str(out), "--runs", "nope") == 1
    assert "not in the file" in capsys.readouterr().err


def test_the_file_holds_no_names_and_no_price_columns(lab: SimpleNamespace) -> None:
    """Names and prices are run-time data from data/ (CLAUDE.md rule 4): the file stores ids
    and counts; the only zeny is the per-run judge snapshot."""
    con = built(lab, lab.s1, lab.s2)  # data/ HAS names: none may land in the file
    cols = {
        c[1]
        for t in ("runs", "run_items", "run_species", "run_consumables")
        for c in con.execute(f"PRAGMA table_info({t})")
    }
    assert not cols & {"name", "sell", "sell_oc", "npc_buy", "npc_buy_dc", "price", "weight"}
    con.close()
    for rows in dump(lab.db).values():
        assert not any("made-up-" in str(v) for row in rows for v in row)


def test_the_default_file_is_gitignored() -> None:
    assert edb.default_db() == ROOT / "data" / "econ" / "lab.sqlite"
    if shutil.which("git") is None:
        pytest.skip("no git here")
    for name in ("lab.sqlite", "lab.sqlite-wal", "lab.sqlite-shm"):
        r = subprocess.run(
            ["git", "-C", str(ROOT), "check-ignore", "-q", f"data/econ/{name}"], check=False
        )
        if r.returncode == 128:
            pytest.skip("not a git checkout")
        assert r.returncode == 0, f"data/econ/{name} is NOT gitignored"


# --- a REAL case (read at test time; skipped when absent) -----------------------------------------

ARCHIVE = Path("/mnt/poring-lab-datasets/scratch-archive/2026-11-11/demo-sessions")
P57 = ARCHIVE / "20261111T082037-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p57"
P58 = ARCHIVE / "20261111T084908-demo-dungeon-rogue-xmas_dun02-patrol-P2-xmas02-p58"
_ITEMS_ENV = os.environ.get("PORING_LAB_ECON_ITEMS")  # a worktree: the main checkout's table
REAL_DATA = Path(_ITEMS_ENV).parents[1] if _ITEMS_ENV else ROOT / "data"


@pytest.mark.skipif(
    not (P57 / "packets.jsonl.gz").exists()
    or not (P58 / "packets.jsonl.gz").exists()
    or not (REAL_DATA / "econ" / "items.json").exists(),
    reason="the xmas02 p57 / p58 archive or the item table is not here",
)
def test_real_xmas02_p57_p58_through_the_file(tmp_path: Path) -> None:
    """The banked p57 + p58 (test_econ_dash's hand-checked pair: 35 + 65 kills, 29 + 57 gains):
    the file's counts equal econ_dash's, and its dashboard equals `econ_dash.py export`."""
    con = edb.connect(tmp_path / "lab.sqlite")
    res = edb.ingest(con, [str(P57), str(P58)], REAL_DATA)
    assert [r["result"] for r in res] == ["added", "added"]
    table = ed.sources(REAL_DATA)[1]["items"]
    for d, kills, income in ((P57, 35, 29), (P58, 65, 57)):
        entry = ed.export_run(str(d), table, {}, {}, None, REAL_DATA / "econ" / "maps.json")
        assert db_counts(con, d.name) == counts_of_entry(entry)
        assert entry["kills"] == kills and entry["totals"]["income_units"] == income
    want = ed.build([str(P57), str(P58)], "real", REAL_DATA)
    got = edb.dashboard(con, [P57.name, P58.name], "real", REAL_DATA)
    for doc in (want, got):
        doc.pop("exported_at")
    assert got == want
    con.close()
