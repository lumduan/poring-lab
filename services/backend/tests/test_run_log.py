"""The Run log (Batt 2026-11-21): "What she does" kept as history -- the settings' format
(poring_env.runlog), the helper's keeper (flow_run.StoryKeeper) and its CCTV-like retention."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import flow_run as fr  # noqa: E402

from poring_env import runlog as rl  # noqa: E402

T0 = dt.datetime(2026, 11, 21, 11, 26, 42, tzinfo=dt.timezone(dt.timedelta(hours=7)))


def test_the_default_records_nothing_and_the_format_round_trips() -> None:
    assert rl.DEFAULT.record is False and rl.DEFAULT.folder == "logs/bot"
    assert rl.DEFAULT.max_total_mb == 100
    s = rl.Store(revision=3, record=True, folder="/mnt/nas/bot-logs", max_total_mb=250)
    assert rl.parse(rl.dumps(s)) == s
    assert isinstance(rl.parse("{}"), str) and isinstance(rl.parse("nope"), str)
    bad = json.loads(rl.dumps(s))
    assert isinstance(rl.parse(json.dumps({**bad, "extra": 1})), str)
    assert isinstance(rl.parse(json.dumps({**bad, "record": "yes"})), str)


def test_the_folder_and_the_cap_are_checked() -> None:
    assert rl.folder_problem("logs/bot") is None and rl.folder_problem("/mnt/nas/x") is None
    assert rl.folder_problem("") == "folder_empty" and rl.folder_problem("/") == "folder_root"
    assert rl.folder_problem("logs/../../etc") == "folder_dotdot"
    assert rl.folder_problem("a\nb") == "folder_bad_character"
    assert rl.folder_problem("x" * 600) == "folder_too_long"
    assert rl.max_problem(100) is None and rl.max_problem(0) == "max_out_of_range"
    assert rl.max_problem(1.5) == "max_not_a_whole_number" and rl.max_problem(True) is not None


def test_a_run_folder_is_named_by_its_start_and_the_oldest_goes_first() -> None:
    assert rl.run_dir_name(T0, "11211126") == "20261121-112642-11211126"
    assert rl.run_dir_name(T0) == "20261121-112642"
    mb = 1024 * 1024
    runs = [("20261121-090000-a", 40 * mb), ("20261120-090000-b", 40 * mb),
            ("20261121-120000-c", 40 * mb), ("not-a-run", 999 * mb)]  # fmt: skip
    # 120 MB of Runs over a 100 MB cap: the OLDEST (by its start) goes; other names never
    assert rl.plan_deletes(runs, 100 * mb) == ["20261120-090000-b"]
    assert rl.plan_deletes(runs, 50 * mb) == ["20261120-090000-b", "20261121-090000-a"]
    # the Run being written never goes, even when it alone is over the cap
    assert rl.plan_deletes(runs, 30 * mb, keep=("20261120-090000-b",)) == [
        "20261121-090000-a", "20261121-120000-c"]  # fmt: skip
    assert rl.plan_deletes(runs, 500 * mb) == []


def test_the_keeper_records_nothing_without_the_setting(tmp_path: Path) -> None:
    (tmp_path / "settings").mkdir()
    k = fr.StoryKeeper(tmp_path / "settings", tmp_path, "11211126", T0)
    assert not k.recording and k.problem is None
    k.write({"t_s": 1, "words": "x"})  # nothing, no error
    (tmp_path / "settings" / rl.FILE_NAME).write_text("not json")
    k = fr.StoryKeeper(tmp_path / "settings", tmp_path, "11211126", T0)
    assert not k.recording and "not recorded" in str(k.problem)


def test_the_keeper_writes_both_files_and_keeps_the_total_under_the_cap(tmp_path: Path) -> None:
    sd = tmp_path / "settings"
    sd.mkdir()
    (sd / rl.FILE_NAME).write_text(rl.dumps(rl.Store(revision=1, record=True,
                                                     max_total_mb=1)))  # fmt: skip
    base = tmp_path / "logs" / "bot"
    old = base / "20261120-080000-old"
    old.mkdir(parents=True)
    (old / rl.STORY_JSONL).write_bytes(b"x" * (1024 * 1024))  # 1 MB: with a new Run, over
    other = base / "keep-me"
    other.mkdir()
    (other / "notes.txt").write_text("a person's file")
    k = fr.StoryKeeper(sd, tmp_path, "11211126", T0)
    assert k.recording and k.dir == base / "20261121-112642-11211126"
    lv = fr.Live(wall_minus_mono_s=1_000_000.0, sink=k.write)
    lv.feed({"t_ns": 5_000_000_000, "kind": "kill", "of": "mystcase", "by": "exp_line"})
    k.close()
    k.retain()
    rows = [json.loads(x) for x in (k.dir / rl.STORY_JSONL).read_text().splitlines()]
    assert rows and rows[-1]["words"].startswith("a kill: mystcase") and rows[-1]["at"]
    assert "a kill: mystcase" in (k.dir / rl.STORY_TEXT).read_text()
    # the oldest Run went (over the 1 MB cap); a folder not named like a Run stays
    assert not old.exists() and k.deleted == ["20261120-080000-old"]
    assert (other / "notes.txt").exists()
    assert k.summary()["recording"] and k.summary()["lines"] == len(rows)


def test_a_fire_line_says_the_reading_and_the_rule() -> None:
    e = {"kind": "event", "event": "bag_full", "reading": {"weight_percent": 50},
         "when": "weight_percent() >= 50"}  # fmt: skip
    assert fr.event_words(e) == (
        "the box's function bag_full fires: weight_percent 50 (its rule: weight_percent() >= 50)"
    )
    assert fr.event_words({"kind": "event", "event": "x"}) == "the box's function x fires"
