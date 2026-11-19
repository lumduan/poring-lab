"""A Run's retry option after a code error (Batt 2026-11-19): its format, bounds and default."""

import json
from pathlib import Path

from poring_env import runoptions as ro


def test_no_file_or_a_broken_one_is_the_default(tmp_path: Path) -> None:
    assert ro.load(tmp_path) == ro.DEFAULTS == ro.RunOptions(3, 20)
    (tmp_path / ro.FILE_NAME).write_text("{")
    assert ro.load(tmp_path) == ro.DEFAULTS
    (tmp_path / ro.FILE_NAME).write_text(json.dumps({"v": 1, "retry_max": 0, "retry_wait_s": 60}))
    assert ro.load(tmp_path) == ro.RunOptions(0, 60)


def test_the_bounds_and_the_words() -> None:
    assert ro.parse({"retry_max": 21})[0] is None and ro.parse({"retry_max": True})[0] is None
    assert ro.parse({"retry_wait_s": 4})[0] is None and ro.parse({"retry_wait_s": 601})[0] is None
    assert "unknown keys" in str(ro.parse({"retry": 3})[1])
    assert ro.parse({})[0] == ro.DEFAULTS
    assert "retry off" in ro.words(ro.RunOptions(0, 20))
    assert ro.words(ro.RunOptions(1, 30)).endswith("at most 1 time a run")
    assert "in 30 s" in ro.words(ro.RunOptions(5, 30))
