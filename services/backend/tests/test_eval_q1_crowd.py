"""scripts/eval_q1.py, xmas02-detector.md Amendment S5: Q1crowd (a box on ANY unit of its species
in its frame, by the packets, is not false), the units file (the crowd truth) and the party view
(the alarm's frame-by-frame numbers, reported). Synthetic keys, units and detections only."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import eval_q1 as q  # noqa: E402
from test_eval_q1 import CLS, LADY, MANIFEST, WARRIOR, all_good, crop, det, make_key  # noqa: E402

BOX = [100.0, 100.0, 140.0, 160.0]


def unit(mob: int, region: list[float] | None = None, kept_box: list[float] | None = None
         ) -> dict[str, Any]:  # fmt: skip
    return {"gid": 1, "mob": mob, "region": region, "kept_box": kept_box,
            "label": "kept" if kept_box else "crowd"}  # fmt: skip


def test_lies_on_a_kept_box_or_inside_a_region() -> None:
    assert q.lies_on([100, 100, 140, 160], [unit(LADY, None, [102, 100, 142, 160])]) == {LADY}
    assert q.lies_on([100, 100, 140, 160], [unit(LADY, None, [130, 100, 170, 160])]) == set()
    assert q.lies_on([100, 100, 140, 160], [unit(WARRIOR, [110, 110, 135, 140])]) == {WARRIOR}
    assert q.lies_on([100, 100, 140, 160], [unit(WARRIOR, [130, 100, 170, 160])]) == set()
    both = [unit(LADY, [90, 90, 150, 170]), unit(WARRIOR, None, [100, 100, 140, 160])]
    assert q.lies_on([100, 100, 140, 160], both) == {LADY, WARRIOR}


def crowd_world() -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """50 Lady crops (50 frames), each matched; 10 frames add a Lady box on another LADY unit
    (absolved), 5 on a Warrior unit, 3 on no unit (false), all inside the crop box; 2 frames a Lady
    box OUTSIDE every evaluated box on no unit (frame-wide only)."""
    key = make_key([crop("S", i, LADY, BOX) for i in range(1, 51)])
    frames, units = {}, {}
    inside = [112.0, 110.0, 152.0, 170.0]  # centre (132, 140): inside BOX, farther than the match
    for i in range(1, 51):
        fk = q.frame_key("S", i)
        frames[fk] = [det("lady_c", BOX)]
        us = [unit(LADY, None, BOX)]
        if i <= 10:
            frames[fk].append(det("lady_c", inside))
            us.append(unit(LADY, [108, 105, 160, 175]))
        elif i <= 15:
            frames[fk].append(det("lady_c", inside))
            us.append(unit(WARRIOR, [108, 105, 160, 175]))
        elif i <= 18:
            frames[fk].append(det("lady_c", inside))
        elif i <= 20:
            frames[fk].append(det("lady_c", [400, 400, 440, 460]))
        units[fk] = {"t": i * 1_000_000_000, "units": us}
    return key, frames, units


def test_q1crowd_absolves_boxes_on_units_of_the_species() -> None:
    key, frames, units = crowd_world()
    crops, _ = q.evaluated(key, all_good(key), all_good(key))
    plain = q.score(key, crops, frames, CLS)["Q1"]["per_species"]["lady_c"]
    assert (plain["matched"], plain["unmatched_in_boxes"], plain["pass"]) == (50, 18, False)
    row = q.crowd_score(key, crops, frames, CLS, units)["Q1crowd"]["per_species"]["lady_c"]
    assert row["in_boxes"] == {"unmatched": 18, "absolved": 10, "false": 8,
                               "false_on_other_species": 5, "false_on_no_unit": 3}  # fmt: skip
    assert (row["recall"], row["precision"], row["bar"], row["pass"]) == (1.0, 0.8621, True, True)
    assert row["frame_wide"]["unmatched"] == 20 and row["frame_wide"]["false"] == 10
    assert row["frame_wide"]["precision"] == round(50 / 60, 4)


def test_q1crowd_keeps_q1s_recall_and_its_integer_bar() -> None:
    key, frames, units = crowd_world()
    for i in range(21, 32):  # 11 of 50 unmatched: recall 39 / 50 = 0.78 < 0.80
        frames[q.frame_key("S", i)][0] = det("warrior_c", BOX)
    crops, _ = q.evaluated(key, all_good(key), all_good(key))
    row = q.crowd_score(key, crops, frames, CLS, units)["Q1crowd"]["per_species"]["lady_c"]
    assert row["matched"] == 39 and row["pass"] is False


def test_q1crowd_fails_closed_without_units() -> None:
    key, frames, units = crowd_world()
    del units[q.frame_key("S", 7)]
    crops, _ = q.evaluated(key, all_good(key), all_good(key))
    with pytest.raises(SystemExit, match="lacks 1 evaluated frames"):
        q.crowd_score(key, crops, frames, CLS, units)


def test_score_cli_adds_q1crowd_for_its_own_key(tmp_path: Path) -> None:
    key, frames, units = crowd_world()
    (tmp_path / "key.json").write_text(json.dumps(key))
    ans = list(all_good(key).values())
    for n in ("A", "B"):
        (tmp_path / f"{n}.json").write_text(json.dumps(ans))
    (tmp_path / "m.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "p.json").write_text(json.dumps({"weights": "w", "imgsz": 1280, "conf": 0.25,
                                                 "frames": frames}))  # fmt: skip
    sha = hashlib.sha256((tmp_path / "key.json").read_bytes()).hexdigest()
    (tmp_path / "u.json").write_text(json.dumps({"key_sha256": sha, "frames": units}))
    base = ["score", *(str(tmp_path / f) for f in ("key.json", "A.json", "B.json", "p.json")),
            "--cache-manifest", str(tmp_path / "m.json")]  # fmt: skip
    assert q.main([*base, "--out", str(tmp_path / "s0.json")]) == 0
    s0 = json.loads((tmp_path / "s0.json").read_text())
    assert "Q1crowd" not in s0 and "units" not in s0  # an old score's keys, unchanged
    assert q.main([*base, "--units", str(tmp_path / "u.json"), "--out", str(tmp_path / "s.json")]) \
        == 0  # fmt: skip
    s = json.loads((tmp_path / "s.json").read_text())
    assert s["Q1crowd"]["per_species"]["lady_c"]["pass"] is True
    assert s["Q1"] == s0["Q1"] and s["Q1c"] == s0["Q1c"]  # Q1 and Q1c unchanged beside it
    (tmp_path / "u2.json").write_text(json.dumps({"key_sha256": "0" * 64, "frames": units}))
    with pytest.raises(SystemExit, match="another key"):
        q.main([*base, "--units", str(tmp_path / "u2.json"), "--out", str(tmp_path / "x.json")])


GOB, KNIGHT = q.GOBLIN, 1251


def test_party_view_frames_visits_and_false_alarms() -> None:
    """t = 1..12 s: frames 1-2 no party; 3-6 a visit (a Goblin from 4, its first Goblin box at 5);
    7-11 no party (a gap > 5 s); 12 a knight alone (a visit with no Goblin)."""
    units, frames = {}, {}
    gob = [unit(GOB, [100, 100, 140, 160])]
    for t in range(1, 13):
        us = gob if 4 <= t <= 6 else [unit(KNIGHT, [300, 100, 400, 200])] if t in (3, 12) else []
        units[f"f{t:02d}"] = {"t": t * 1_000_000_000, "units": us}
        ds = []
        if t in (5, 6):
            ds.append({**det("g", BOX), "conf": 0.9 if t == 5 else 0.4})
        if t == 9:
            ds.append({**det("g", [600, 600, 640, 660]), "conf": 0.6})  # a false alarm
        frames[f"f{t:02d}"] = ds
    res = q.party_view(units, frames, "g")
    r = res["thresholds"]
    assert (r["0.25"]["goblin_frames"], r["0.25"]["goblin_frames_boxed"]) == (3, 2)
    assert r["0.7"]["goblin_frames_boxed"] == 1 and r["0.25"]["frame_recall"] == round(2 / 3, 4)
    assert (r["0.25"]["no_party_frames"], r["0.25"]["no_party_frames_boxed"]) == (7, 1)
    assert r["0.7"]["no_party_frames_boxed"] == 0
    assert res["goblin_boxes_lie"] == {"on_goblin": 2, "on_no_unit": 1}
    assert (res["visits"], res["visits_with_a_goblin"], res["first_box_delay_s"]) == (2, 1, [1.0])
    assert res["visits_boxed_within_2s"] == 1 and res["visits_never_boxed"] == 0
    del frames["f03"]
    with pytest.raises(SystemExit, match="lacks 1 units frames"):
        q.party_view(units, frames, "g")


def test_cmd_units_marks_each_unit_with_its_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import map_labels as ml

    params = tmp_path / "params.json"
    params.write_text(json.dumps({"x": 1}))
    psha = hashlib.sha256(params.read_bytes()).hexdigest()
    frames = [{"frame_id": 1, "t": 10, "kept": [{"gid": 5, "mob": GOB, "box": [1, 2, 3, 4]}],
               "excluded": [[6, GOB, "crowd"]]},
              {"frame_id": 2, "t": 20, "kept": [], "excluded": []},
              {"frame_id": 3, "excluded_frame": ["no_scene"]}]  # fmt: skip
    lf = tmp_path / "labels" / "S.json"
    lf.parent.mkdir()
    lf.write_text(json.dumps({"session": "S", "map": "xmas_dun02", "frames": frames}))
    key = {
        "params_sha256": psha,
        "crops": {"001": crop("S", 1, GOB, BOX)},
        "sources": [{"file": str(lf), "sha256": hashlib.sha256(lf.read_bytes()).hexdigest()}],
    }
    (tmp_path / "key.json").write_text(json.dumps(key))
    monkeypatch.setattr(ml, "load_params", lambda path, spec: {"offset_ms": 0})
    monkeypatch.setattr(ml, "session_labeler",
                        lambda path, spec: SimpleNamespace(size=(1280, 720)))  # fmt: skip
    seen: list[int] = []

    def units(lab: Any, p: Any, t: int, size: Any, grow: float) -> list[dict[str, Any]]:
        seen.append(t)
        assert grow == 6.0 and size == (1280, 720)
        return [
            {"gid": g, "mob": m, "region": [0, 0, 9, 9]}
            for g, m in ((5, GOB), (6, GOB), (7, KNIGHT))
        ]

    monkeypatch.setattr(ml, "frame_units", units)
    out = tmp_path / "u.json"
    base = ["units", str(tmp_path / "key.json"), "--params", str(params), "--out", str(out)]
    assert q.main(base) == 0
    doc = json.loads(out.read_text())
    us = doc["frames"][q.frame_key("S", 1)]["units"]
    assert [(u["gid"], u["label"], u["kept_box"]) for u in us] == \
        [(5, "kept", [1.0, 2.0, 3.0, 4.0]), (6, "crowd", None), (7, "unlisted", None)]  # fmt: skip
    assert seen == [10] and doc["key_sha256"] == hashlib.sha256(
        (tmp_path / "key.json").read_bytes()).hexdigest()  # fmt: skip
    assert q.main([*base[:-1], str(tmp_path / "all.json"), "--all-frames"]) == 0
    assert sorted(json.loads((tmp_path / "all.json").read_text())["frames"]) == \
        [q.frame_key("S", 1), q.frame_key("S", 2)]  # fmt: skip
    params.write_text(json.dumps({"x": 2}))
    with pytest.raises(SystemExit, match="the key's params"):
        q.main(base)
