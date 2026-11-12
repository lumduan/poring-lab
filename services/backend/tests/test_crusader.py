"""crusader.py (Batt 2026-10-21: the name + job check before every command on the dedicated
Crusader, a 2nd character on the GM account): the pure identity check."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import crusader as cr  # noqa: E402


def frame(name_val: int, job_val: int) -> np.ndarray:
    f = np.zeros((720, 1280, 3), np.uint8)
    x0, y0, x1, y1 = cr.NAME_BOX
    f[y0:y1, x0:x1] = name_val
    x0, y0, x1, y1 = cr.JOB_BOX
    f[y0:y1, x0:x1] = job_val
    return f


def test_only_the_right_name_and_job_pass() -> None:
    ref = frame(200, 100)
    name_ref = cr.crop(ref, cr.NAME_BOX)
    jobs = {"novice": cr.crop(ref, cr.JOB_BOX), "swordman": cr.crop(frame(200, 30), cr.JOB_BOX)}
    assert cr.identity(ref, name_ref, jobs, "novice")["ok"]
    other = cr.identity(frame(90, 100), name_ref, jobs, "novice")  # another character's name
    assert (other["ok"], other["why"]) == (False, "name")
    wrong_job = cr.identity(ref, name_ref, jobs, "swordman")  # still a Novice on screen
    assert (wrong_job["ok"], wrong_job["why"]) == (False, "job")
    assert not cr.identity(ref, name_ref, jobs, "crusader")["ok"]  # no reference yet: refused


def test_a_few_noisy_pixels_still_match_but_a_changed_line_does_not() -> None:
    ref = frame(200, 100)
    name_ref = cr.crop(ref, cr.NAME_BOX)
    jobs = {"novice": cr.crop(ref, cr.JOB_BOX)}
    noisy = ref.copy()
    noisy[23, 5 : 5 + cr.MATCH] = 0  # MATCH codec-noise pixels
    assert cr.identity(noisy, name_ref, jobs, "novice")["ok"]
    noisy[24, 5:6] = 0  # one more
    assert not cr.identity(noisy, name_ref, jobs, "novice")["ok"]
    assert cr.differing(name_ref, name_ref[:, :-1]) > cr.MATCH  # a shape mismatch never matches


def test_each_test_character_has_its_own_data_dir_and_jobs(tmp_path, monkeypatch) -> None:
    """2026-10-24: the Thief (slot 3) gets the same guard; the Crusader stays the default."""
    import json

    assert cr.CHARS["thief"] == ("novice", "thief", "rogue")
    assert cr.CHARS["crusader"] == cr.JOBS
    assert cr.data_dir() == cr.DATA and cr.data_dir("thief").name == "thief"
    try:
        cr.data_dir("knight")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown character must be refused")
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    d = tmp_path / "data" / "thief"
    d.mkdir(parents=True)
    (d / "char.json").write_text(json.dumps({"name": "T"}))
    ref = frame(200, 100)
    np.save(d / "ref_name.npy", cr.crop(ref, cr.NAME_BOX))
    np.save(d / "ref_job_thief.npy", cr.crop(ref, cr.JOB_BOX))
    np.save(d / "ref_job_swordman.npy", cr.crop(ref, cr.JOB_BOX))  # not a Thief job: never loaded
    name, name_ref, jobs = cr.load_refs("thief")
    assert name == "T" and sorted(jobs) == ["thief"]
    assert cr.identity(ref, name_ref, jobs, "thief")["ok"]


def test_gm_line_skip_types_nothing_when_the_guard_refuses(monkeypatch, tmp_path) -> None:
    """2026-10-24: on_refuse="skip" is chat_guard's own option for an idempotent GM command (@heal):
    a refused line is NOT typed and the caller is told; the default still stops."""
    import types

    import chat_guard
    import ro_agent

    typed: list[str] = []
    fake_agent = types.SimpleNamespace(type_text=typed.append)
    monkeypatch.setattr(cr, "check", lambda screen, job, char: {"ok": True, "job": job})
    monkeypatch.setattr(ro_agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(ro_agent, "activate_client", lambda a, s: None)
    monkeypatch.setattr(ro_agent, "open_chat", lambda a, s: typed.append("<open>"))
    monkeypatch.setattr(ro_agent, "log", lambda m: None)
    refuse = {"on": True}

    def before(text, reason=None, on_refuse="raise"):
        if refuse["on"]:
            if on_refuse == "skip":
                return False
            raise chat_guard.ChatRefused("repeat", "the 3rd identical line")
        return True

    monkeypatch.setattr(chat_guard, "before_typing", before)
    got = cr.gm_line(fake_agent, None, "@heal", "thief", "thief", on_refuse="skip")
    assert got["typed"] is False and typed == []
    with pytest.raises(ro_agent.Stop):
        cr.gm_line(fake_agent, None, "@heal", "thief", "thief")
    refuse["on"] = False
    got = cr.gm_line(fake_agent, None, "@heal", "thief", "thief", on_refuse="skip")
    assert got["typed"] is True and typed == ["<open>", "@heal\n"]


def test_init_writes_a_learners_char_file_and_never_over_one(tmp_path) -> None:
    """new-lab-host.md 11.1: a learner's own character on a server of someone else's."""
    import json

    d = tmp_path / "thief"
    got = cr.init_char(d, "Someone", 2)
    assert "name" not in got and got["slot"] == 2  # the name is not printed back
    rec = json.loads((d / "char.json").read_text())
    assert rec["name"] == "Someone" and rec["slot"] == 2 and len(rec["made"]) == 10
    with pytest.raises(SystemExit, match="exists already"):
        cr.init_char(d, "Other")
    assert json.loads((d / "char.json").read_text())["name"] == "Someone"  # untouched
    with pytest.raises(SystemExit, match="empty"):
        cr.init_char(tmp_path / "crusader", "  ")
    cr.init_char(tmp_path / "c2", "X")  # no slot given: none written
    assert "slot" not in json.loads((tmp_path / "c2" / "char.json").read_text())
