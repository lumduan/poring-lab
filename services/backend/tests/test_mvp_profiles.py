"""The MVP watch per BOSS (docs/planning/stormy-knight-recognizer.md B1): the profile table (the Orc
Lord's values unchanged, the Stormy Knight's added), the study's --boss on every subcommand, the
model file's profile (round trip, fail closed on a mismatch, the Orc Lord's v1 format kept), the
per-model aura rule, and the truth path for the stormy profile on SYNTHETIC packets (no client
data: the sprite projection is stubbed)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import mvp_profiles as mp  # noqa: E402
import mvp_watch as mw  # noqa: E402
import mvp_watch_study as st  # noqa: E402

ORC_NEG = {1023: "Orc Warrior", 1273: "Orc Lady", 1686: "Orc Baby", 1031: "Poporing",
           1079: "Blue Plant", 1080: "Green Plant"}  # fmt: skip
XMAS_NEG = {1249: "Myst Case", 1248: "Cruiser", 1265: "Cookie", 1246: "Christmas Cookie"}


# --- the profile table ----------------------------------------------------------------------------


def test_orclord_profile_is_the_orc_lord_study_unchanged() -> None:
    p = mp.get("orclord")
    assert p is mp.ORCLORD and mp.DEFAULT == "orclord"
    assert (p.boss, p.summons, p.party) == (1190, (1189, 1473), (1190, 1189, 1473))
    assert dict(p.negatives) == ORC_NEG and list(p.negatives) == list(ORC_NEG)
    names = {1190: "Orc Lord", 1189: "Orc Archer", 1473: "Orc Archer (G)", **ORC_NEG}
    assert dict(p.names) == names and list(p.names) == list(names)
    assert p.map == "gef_fild10" and p.maps == ("gef_fild10", "prt_fild08")  # round 2 on prt_fild08
    assert p.dev_cells == frozenset(range(8)) and p.held_cells == frozenset(range(8, 15))
    assert p.lone == ()
    assert (p.aura_thr, p.ring, p.ring_cell, p.ring_dy, p.aura_rule) == \
        (0.08, (27.0, 15.0, 17.0, 8.0), 3, 8.0, (236, 25))  # fmt: skip
    assert p.sprites == Path("/dev/shm/poring-lab-tmp/gef10-prep/sprites/data/sprite/몬스터")
    assert p.sprite_names == Path(
        "/dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/monster_sprite_names.json")  # fmt: skip
    # the study's module constants (every helper's default) are the Orc Lord's, as before
    assert (st.ORC_LORD, st.ORC_ARCHERS, st.MVP_PARTY) == (1190, (1189, 1473), (1190, 1189, 1473))
    assert st.NEGATIVE_SPECIES == ORC_NEG and names == st.NAMES and list(st.NAMES) == list(names)
    assert st.MAP == "gef_fild10" and st.AURA_THR == 0.08
    assert sorted(st.DEV_CELLS) == list(range(8)) and sorted(st.HELD_CELLS) == list(range(8, 15))
    assert p.sprites == st.SPRITES and p.sprite_names == st.SPRITE_NAMES
    # ... and the model's defaults are its aura recipe (the frozen v1: orclord-recognizer.md 4b)
    m = mw.Model(body_lut=np.zeros(1, np.float32), lin_w=np.zeros(1, np.float32), lin_b=0.0,
                 lin_thr=0.0, aura_thr=0.08, title=np.zeros(1, np.float32))  # fmt: skip
    assert (m.ring, m.ring_cell, m.ring_dy, m.aura_rule) == (p.ring, p.ring_cell, p.ring_dy,
                                                             p.aura_rule)  # fmt: skip
    assert (m.profile, m.version, mw.AURA_RULE) == ("orclord", "orclord-v1", (236, 25))
    assert p.recipe() == {"aura_thr": 0.08, "ring": (27.0, 15.0, 17.0, 8.0), "ring_cell": 3,
                          "ring_dy": 8.0, "aura_rule": (236, 25)}  # fmt: skip


def test_stormy_profile_and_its_placeholders() -> None:
    p = mp.get("stormy")
    assert p is mp.STORMY
    assert (p.boss, p.summons, p.party) == (1251, (1515, 1607), (1251, 1515, 1607))
    assert dict(p.negatives) == XMAS_NEG
    assert dict(p.names) == {1251: "Stormy Knight", 1515: "Garm Baby", 1607: "Christmas Goblin",
                             **XMAS_NEG}  # fmt: skip
    assert p.map == "xmas_dun02" and p.maps == ("xmas_dun02",)
    # section 3, pre-registered: DEV = cells 0-7, HELD-OUT = cells 8-15 (16 cells, 8 / 8 to pass)
    assert p.dev_cells == frozenset(range(8)) and p.held_cells == frozenset(range(8, 16))
    assert p.lone == (1515,)  # Garm Baby: also its own 30-min spawn (the caveat)
    assert str(p.sprites).endswith("2026-11-05/x1/sprites/data/sprite/몬스터")
    # the aura recipe is NOT fitted: every field a placeholder, and the recipe refuses
    assert (p.aura_thr, p.ring, p.ring_cell, p.ring_dy, p.aura_rule) == (None,) * 5
    every = "aura_thr, ring, ring_cell, ring_dy, aura_rule not fitted yet"
    with pytest.raises(ValueError, match=every):
        p.recipe()
    with pytest.raises(ValueError, match="ring_dy"):
        p.recipe(aura_thr=0.1, ring=(30.0, 16.0, 19.0, 9.0), ring_cell=3, aura_rule=(236, 25))
    got = p.recipe(aura_thr=0.1, ring=(30.0, 16.0, 19.0, 9.0), ring_cell=3, ring_dy=9.0,
                   aura_rule=(236, 25), nose=1)  # fmt: skip
    assert got == {"aura_thr": 0.1, "ring": (30.0, 16.0, 19.0, 9.0), "ring_cell": 3,
                   "ring_dy": 9.0, "aura_rule": (236, 25)}  # fmt: skip
    with pytest.raises(KeyError, match="orclord, stormy"):
        mp.get("nose")


def test_the_runner_picks_the_profile_of_its_hunting_map() -> None:
    assert mp.for_map("xmas_dun02") is mp.STORMY and mp.for_map("xmas_dun02.gat") is mp.STORMY
    assert mp.for_map("gef_fild10") is mp.ORCLORD
    assert mp.for_map("prt_fild08") is None  # a watch map only: no boss is hunted there
    assert mw.default_model("stormy") == mw.MODEL_DIR / "stormy-v1.npz"
    assert mw.default_model() == mw.DEFAULT_MODEL == mw.MODEL_DIR / "orclord-v1.npz"
    for bad in ("../x", "Stormy", "a b", ""):
        with pytest.raises(ValueError):
            mw.default_model(bad)


def _kb() -> tuple[dict[str, Any], dict[str, Any]]:
    spawns = {
        "xmas_dun02": [
            {"id": 1246, "name": "Christmas Cookie", "boss": False},
            {"id": 1249, "name": "Myst Case", "boss": False},
            {"id": 1515, "name": "Garm Baby", "boss": False},
            {"id": 1251, "name": "Stormy Knight", "boss": True},
            {"id": 1265, "name": "Cookie", "boss": False},
            {"id": 1248, "name": "Cruiser", "boss": False},
        ],
        "gef_fild10": [{"id": 1190, "name": "Orc Lord", "boss": True},
                       *({"id": i, "name": n, "boss": False} for i, n in ORC_NEG.items()),
                       {"id": 1079, "name": "Blue Plant", "boss": False}],
    }  # fmt: skip
    slave = "@NPC_SUMMONSLAVE"
    skills = {
        "1251": [{"info": "Stormy Knight" + slave, "vals": ["1607", "", "", "", ""]},
                 {"info": "Stormy Knight" + slave, "vals": ["1515", "", "", "", ""]},
                 {"info": "Stormy Knight@NPC_EARTHQUAKE", "vals": ["9999"]}],
        "1190": [{"info": "Orc Lord" + slave, "vals": ["1473"]},
                 {"info": "Orc Lord" + slave, "vals": ["1189", ""]}],
    }  # fmt: skip
    return spawns, skills


def test_kb_party_derives_the_profiles_from_spawns_and_summon_skills() -> None:
    spawns, skills = _kb()
    assert mp.kb_party("xmas_dun02", spawns, skills) == {
        "bosses": [1251], "summons": [1515, 1607], "others": [1246, 1248, 1249, 1265],
        "lone": [1515]}  # fmt: skip
    assert mp.matches_kb(mp.STORMY, spawns, skills) == []
    assert mp.matches_kb(mp.ORCLORD, spawns, skills) == []
    spawns["xmas_dun02"].append({"id": 1247, "name": "Antonio", "boss": False})
    assert mp.matches_kb(mp.STORMY, spawns, skills) == [
        "others: profile [1246, 1248, 1249, 1265] != KB [1246, 1247, 1248, 1249, 1265]"
    ]


KB_DIRS = [Path(os.environ["PORING_KB_DIR"])] if os.environ.get("PORING_KB_DIR") else []
KB_DIRS.append(ROOT / "data" / "kb")


def test_profiles_agree_with_the_local_kb() -> None:
    """The real KB (data/kb, local, GPL-derived, never committed); skips without it."""
    kb = next((d for d in KB_DIRS if (d / "spawns.json").exists()), None)
    if kb is None:
        pytest.skip("no local KB (data/kb is gitignored; PORING_KB_DIR points at one)")
    spawns = json.loads((kb / "spawns.json").read_text())
    skills = json.loads((kb / "mob_skills.json").read_text())
    for prof in mp.PROFILES.values():
        assert mp.matches_kb(prof, spawns, skills) == [], prof.name


# --- --boss on every subcommand -------------------------------------------------------------------

# orclord-recognizer.md 9 and 11's command lines, as written (paths shortened)
ORC_LINES = {
    "truth": ["truth", "D/ow1", "--layout", "standard", "--out", "T/ow1-truth.json"],
    "truth2": ["truth", "D/ow2", "--layout", "hunt", "--map", "prt_fild08", "--out", "T/o.json"],
    "fit": ["fit", "--watch", "D/ow1", "--watch-truth", "T/ow1.json", "--events", "E",
            "--pilot", "D/p", "T/p.json", "--extra", "D/p2", "T/p2.json", "--work", "T/fit",
            "--out", "T/model/orclord-v1.npz"],
    "score": ["score", "--model", "M", "--sha256", "43179452", "--watch", "D/ow1",
              "--watch-truth", "T/ow1.json", "--events", "E", "--pilot", "D/p", "T/p.json",
              "--supplement", "D/s1", "T/s1.json", "--out", "T/score.json"],
    "entries": ["entries", "--model", "M", "--sha256", "43179452", "--watch", "D/ow2",
                "--watch-truth", "T/ow2.json", "--events", "E", "--hunt", "D/a1", "T/a1.json",
                "--out", "T/r2.json"],
}  # fmt: skip


def test_every_subcommand_takes_boss_and_defaults_to_the_orc_lord() -> None:
    ap = st.parser()
    for key, line in ORC_LINES.items():
        a = ap.parse_args(line)
        assert a.boss == "orclord" and st.profile_of(a) is mp.ORCLORD, key
        b = ap.parse_args([*line, "--boss", "stormy"])
        assert b.boss == "stormy" and st.profile_of(b) is mp.STORMY, key
        with pytest.raises(SystemExit):
            ap.parse_args([*line, "--boss", "orc"])
    a = ap.parse_args(ORC_LINES["truth"])
    assert (a.map, a.sprites, a.sprite_names) == (None, None, None)  # -> the profile's
    assert st.profile_of(argparse.Namespace()) is mp.ORCLORD  # a Namespace without --boss


def test_fit_recipe_defaults_overrides_and_placeholders() -> None:
    ap = st.parser()
    a = ap.parse_args(ORC_LINES["fit"])
    assert st.fit_recipe(a, mp.ORCLORD) == mp.ORCLORD.recipe()
    b = ap.parse_args([*ORC_LINES["fit"], "--boss", "stormy"])
    with pytest.raises(SystemExit, match="stormy: aura_thr, ring, ring_cell, ring_dy, aura_rule"):
        st.fit_recipe(b, mp.STORMY)
    c = ap.parse_args([*ORC_LINES["fit"], "--boss", "stormy", "--aura-thr", "0.1", "--ring", "30",
                       "16", "19", "9", "--ring-cell", "3", "--ring-dy", "9",
                       "--aura-rule", "220", "10"])  # fmt: skip
    r = st.fit_recipe(c, mp.STORMY)
    assert r == {"aura_thr": 0.1, "ring": (30.0, 16.0, 19.0, 9.0), "ring_cell": 3,
                 "ring_dy": 9.0, "aura_rule": (220, 10)}  # fmt: skip
    f = st.aura_fields(r, mp.STORMY)
    assert (f["profile"], f["version"], f["aura_rule"]) == ("stormy", "stormy-v1", (220, 10))
    assert st.aura_fields(mp.ORCLORD.recipe(), mp.ORCLORD)["version"] == "orclord-v1"


# --- the model file names its profile -------------------------------------------------------------


def _title() -> np.ndarray:
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    g = np.zeros((y1 - y0, x1 - x0), np.float32)
    g[:, ::4] = 200.0
    return g


def _model(**kw: Any) -> mw.Model:
    base: dict[str, Any] = dict(
        body_lut=np.zeros(mw.NBINS, np.float32),
        lin_w=np.zeros((mw.N_FEATURES, *mw.WIN), np.float32), lin_b=-10.0, lin_thr=0.0,
        aura_thr=0.08, title=_title(),
    )  # fmt: skip
    base.update(kw)
    return mw.Model(**base)


LEGACY_MEMBERS = {"body_lut.npy", "lin_w.npy", "title.npy", "scalars.npy", "ring.npy",
                  "version.npy"}  # fmt: skip


def test_orclord_model_keeps_the_v1_format_and_loads_as_orclord(tmp_path: Path) -> None:
    p = tmp_path / "orclord-v1.npz"
    sha = mw.save(p, _model())
    assert set(zipfile.ZipFile(p).namelist()) == LEGACY_MEMBERS  # no profile member: v1's bytes
    back = mw.load(p, sha, profile="orclord")
    assert (back.profile, back.aura_rule, back.version) == ("orclord", (236, 25), "orclord-v1")
    assert mw.load(p).profile == "orclord"  # no profile asked: any
    with pytest.raises(mw.ModelUnavailable, match="a 'orclord' model, not 'stormy'"):
        mw.load(p, sha, profile="stormy")
    with pytest.raises(ValueError, match="v1 format"):  # v1 cannot carry another aura rule
        mw.save(tmp_path / "x.npz", _model(aura_rule=(220, 10)))
    with pytest.raises(mw.ModelUnavailable, match="missing"):
        mw.load(None, profile="nonesuch")  # its default path data/mvp_watch/nonesuch-v1.npz


def test_stormy_model_round_trip_and_fail_closed_mismatch(tmp_path: Path) -> None:
    m = _model(profile="stormy", version="stormy-v1", aura_rule=(220, 10),
               ring=(30.0, 16.0, 19.0, 9.0), ring_dy=9.0)  # fmt: skip
    p = tmp_path / "stormy-v1.npz"
    sha = mw.save(p, m)
    assert set(zipfile.ZipFile(p).namelist()) == LEGACY_MEMBERS | {"profile.npy", "aura_rule.npy"}
    back = mw.load(p, sha, profile="stormy")
    assert (back.profile, back.version, back.aura_rule) == ("stormy", "stormy-v1", (220, 10))
    assert (back.ring, back.ring_dy, back.ring_cell) == ((30.0, 16.0, 19.0, 9.0), 9.0, 3)
    with pytest.raises(mw.ModelUnavailable, match="a 'stormy' model, not 'orclord'"):
        mw.load(p, sha, profile="orclord")  # the Orc Lord's runner never loads a Knight model
    with pytest.raises(mw.ModelUnavailable, match="sha256"):
        mw.load(p, "0" * 64, profile="stormy")
    assert mw.save(tmp_path / "again.npz", m) == sha  # deterministic bytes


RIM_YG = (60, 230, 215)  # BGR: a yellow-green rim (G 230, R 215): under the Orc Lord's G >= 236


def _frame(model: mw.Model, foot: tuple[int, int] = (900, 500),
           colour: tuple[int, int, int] = RIM_YG) -> np.ndarray:  # fmt: skip
    """A plain field frame with the game's title bar and an aura ring around ``foot``."""
    f = np.zeros((720, 1280, 3), np.uint8)
    f[:, :] = (40, 90, 80)
    x0, y0, x1, y1 = mw.TITLE_BOX
    grey = np.repeat(np.repeat(model.title, 2, axis=0), 2, axis=1)
    f[y0:y1, x0:x1] = grey[: y1 - y0, : x1 - x0, None].astype(np.uint8)
    yy, xx = np.mgrid[0:720, 0:1280]
    r = ((xx - foot[0]) / 54.0) ** 2 + ((yy - foot[1] + 16) / 30.0) ** 2
    f[(r <= 1.0) & (r >= 0.55)] = colour
    return f


def test_decide_reads_the_models_own_aura_rule(tmp_path: Path) -> None:
    orc = _model()
    knight = _model(profile="stormy", aura_rule=(220, 10))
    f = _frame(orc)
    assert mw.decide(f, orc)["seen"] is False  # the Orc Lord's rule rejects the colour
    v = mw.decide(f, knight)
    assert v["seen"] is True and v["cue"] == "aura"
    assert abs(v["where"][0] - 900) <= 12 and abs(v["where"][1] - 500) <= 16
    p = tmp_path / "k.npz"
    mw.save(p, knight)
    assert mw.decide(f, mw.load(p, profile="stormy"))["seen"] is True


# --- the truth path for the stormy profile, on synthetic packets ---------------------------------

MS = 1_000_000
T0 = 700_000_000 * MS
AID = 2000001


def _ev(t_ms: int, type_: str, **fields: object) -> dict[str, object]:
    return {"t_mono_ns": T0 + t_ms * MS, "type": type_, **fields}


def _appear(t_ms: int, gid: int, job: int, x: int, y: int) -> dict[str, object]:
    return _ev(t_ms, "entity_appear", kind="new", gid=gid, char_id=0, objtype=5, job=job,
               speed=200, name=str(job), x=x, y=y, heading=0)  # fmt: skip


def _events() -> list[dict[str, object]]:
    return [
        _ev(-6001, "login_accepted", aid=AID, sex=0),  # > SETTLE_NS before the frames
        _ev(-6000, "map_change", map="xmas_dun02.gat", x=100, y=100),
        _appear(1000, 11, 1251, 103, 100),  # the Knight, 3 cells east: in view
        _appear(1000, 12, 1515, 98, 101),  # a Garm Baby beside us: in view
        _appear(1000, 13, 1607, 140, 100),  # a Goblin 40 cells east: off screen
        _appear(1000, 14, 1249, 100, 96),  # a Myst Case 4 cells south: in view
        _ev(8000, "entity_vanish", gid=11, reason=0),
        _ev(8000, "entity_vanish", gid=12, reason=0),
        _ev(8000, "entity_vanish", gid=13, reason=0),
    ]


class _Sheets:
    def __init__(self, have: set[int]) -> None:
        self.have, self.missing = have, {}

    def __call__(self, job: int | None) -> object | None:
        return object() if job in self.have else None


def _stub_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scene is our own cell; a unit's box is 80 x 100 px, its feet 40 px per cell east and
    30 px per cell south of the screen centre (640, 360): no camera, GAT or sprite needed."""
    from poring_dataset import render

    def scene(camera: Any, map_name: str, player: Any, **kw: Any) -> Any:
        return player

    def predict(actor: Any, sheet: Any, sc: Any, k: float) -> Any:
        fx = 640 + 40 * (actor.cell[0] - sc[0])
        fy = 360 + 30 * (sc[1] - actor.cell[1])
        return SimpleNamespace(box=(fx - 40, fy - 100, fx + 40, fy))

    monkeypatch.setattr(render, "load_scene", scene)
    monkeypatch.setattr(render, "predict_sprite", predict)


def _stack(prof: mp.BossProfile, sheets: _Sheets) -> st.TruthStack:
    from poring_dataset.timeline import Timeline

    events = _events()
    changes, gm, vanish, new = st.stack_times(events, prof.party)
    return st.TruthStack(Timeline(events), sheets, {}, None, (1280, 720), mw.HUNT_RECTS,
                         changes, gm, vanish, new)  # fmt: skip


FRAMES = [(T0 + t * MS, i) for i, t in enumerate((300, 1300, 3000, 9000, 14000))]


def test_stormy_truth_on_synthetic_packets(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_projection(monkeypatch)
    prof = mp.STORMY
    stack = _stack(prof, _Sheets(set(prof.party) | set(prof.negatives)))
    assert (stack.new, stack.vanish) == ([T0 + 1000 * MS] * 3, [T0 + 8000 * MS] * 3)
    doc = st.truth_doc(stack, FRAMES, session="s", layout="hunt", prof=prof)
    assert (doc["boss"], doc["map"], doc["size"]) == ("stormy", "xmas_dun02", (1280, 720))
    rows = doc["frames"]
    view = [{u["job"]: u["in_view"] for u in r["units"]} for r in rows]
    assert view[0] == {} and view[4] == {1249: True}
    assert view[1] == view[2] == {1251: True, 1515: True, 1607: False, 1249: True}
    assert [r["flags"] for r in rows] == [[], ["party_edge"], [], ["party_edge"], []]
    assert [st.kind_of(r, prof.party) for r in rows] == ["neg", "pos", "pos", "edge", "neg"]
    assert [st.kind_of(r) for r in rows] == ["neg", "edge", "neg", "edge", "neg"]  # orclord's party
    s = st.summary(doc, prof)
    assert s["frames_with"] == {"Stormy Knight": 2, "Garm Baby": 2, "Myst Case": 4}
    assert (s["party_frames"], s["lord_frames"], s["episodes"], s["on_map"]) == (2, 2, 1, 5)
    eps = st.episodes([r for r in rows if st.on_map(r, "xmas_dun02")], prof.party, boss=prof.boss)
    assert [(e["frames"], e["lord"]) for e in eps] == [([1, 2], True)]
    # the Orc Lord's profile on the same packets: no party edge, and not its map
    orc = _stack(mp.ORCLORD, _Sheets(set(mp.ORCLORD.party)))
    assert (orc.new, orc.vanish) == ([], [])
    with pytest.raises(SystemExit, match="--map xmas_dun02 is not one of"):
        st.truth_doc(orc, FRAMES, session="s", layout="hunt", map_name="xmas_dun02")
    # a party species without a decoded sprite refuses (its frames would all read negative)
    with pytest.raises(SystemExit, match="no decoded sprite for the party .*Christmas Goblin"):
        st.truth_doc(_stack(prof, _Sheets({1251, 1515})), FRAMES, session="s", layout="hunt",
                     prof=prof)  # fmt: skip


def test_a_truth_names_its_boss_and_another_profile_refuses_it(tmp_path: Path) -> None:
    new = tmp_path / "stormy-truth.json"
    new.write_text(json.dumps({"boss": "stormy", "map": "xmas_dun02", "frames": []}))
    old = tmp_path / "ow1-truth.json"  # a truth from before B1: no "boss", the Orc Lord's
    old.write_text(json.dumps({"frames": [{"frame_id": 3, "t": 0}]}))
    assert st.truth_of(new, mp.STORMY)["map"] == "xmas_dun02"
    assert st._rows(old) == {3: {"frame_id": 3, "t": 0}}
    with pytest.raises(SystemExit, match="a --boss stormy truth, not orclord"):
        st._rows(new)
    with pytest.raises(SystemExit, match="a --boss orclord truth, not stormy"):
        st._rows(old, mp.STORMY)
    assert st._map_of(old, mp.STORMY) == "xmas_dun02" and st._map_of(new, mp.ORCLORD) == \
        "xmas_dun02"  # fmt: skip


def test_watch_events_of_another_boss_refuse(tmp_path: Path) -> None:
    ev = tmp_path / "events.jsonl"
    ev.write_text("".join(json.dumps(r) + "\n" for r in (
        {"kind": "spawn", "t_ns": 10, "mob": 1190}, {"kind": "killmonster2", "t_ns": 20},
        {"kind": "spawn", "t_ns": 30}, {"kind": "killmonster2", "t_ns": 40})))  # fmt: skip
    assert st.watch_times(ev) == ([10, 30], [20, 40])
    assert st.watch_times(ev, 1190) == ([10, 30], [20, 40])  # a spawn without "mob" passes
    with pytest.raises(SystemExit, match=r"spawns of \['1190'\], not the boss 1251"):
        st.watch_times(ev, 1251)


# --- the hunting negatives: the Garm Baby caveat --------------------------------------------------


def _row(fid: int, units: list[dict[str, Any]], flags: list[str] | None = None) -> dict[str, Any]:
    return {"frame_id": fid, "t": fid * 1_000_000_000, "map": "xmas_dun02.gat", "units": units,
            "flags": flags or []}  # fmt: skip


def _u(job: int, box: tuple[float, ...] | None, in_view: bool) -> dict[str, Any]:
    return {"job": job, "box": box, "in_view": in_view}


def test_hunt_negatives_leave_lone_summons_out_and_refuse_the_boss() -> None:
    rows = {0: _row(0, [_u(1249, (300, 300, 380, 400), True)]),
            1: _row(1, [_u(1515, (600, 200, 680, 300), True)]),  # a lone Garm Baby in view
            2: _row(2, [_u(1515, (600, 200, 680, 300), True)]),
            3: _row(3, [_u(1515, (1250, 200, 1330, 300), False)]),  # partly on screen: edge
            4: _row(4, [], ["party_edge"]),  # just after its vanish (Amendment A)
            8: _row(8, [_u(1515, (600, 200, 680, 300), True)]),  # a second episode (> 3 s)
            9: _row(9, [_u(1249, (300, 300, 380, 400), True)])}  # fmt: skip
    keep = set(rows)
    neg, lone = st.hunt_negatives(rows, keep, "s", mp.STORMY)
    assert (neg, lone) == ({0, 9}, {1, 2, 3, 4, 8})
    rep = st.lone_report(rows, lone, {1: False, 2: True, 8: False}, len(keep), mp.STORMY)
    assert rep == {"jobs": [1515], "frames": 5, "pos": 3, "seen": 1, "episodes": 2,
                   "episodes_seen": 1, "episodes_seen_per_10min": st.fp_rate(1, 7)}  # fmt: skip
    # the Orc Lord's profile: a Garm Baby is not its party, every kept frame is a negative
    assert st.hunt_negatives(rows, keep, "s") == (keep, set())
    # the Knight (or a Goblin) in a hunting frame refuses: the boss must be dead by the schedule
    rows[5] = _row(5, [_u(1607, (1200, 200, 1290, 300), False)])
    with pytest.raises(SystemExit, match="s: an MVP-party unit is on screen in a hunting frame"):
        st.hunt_negatives(rows, set(rows), "s", mp.STORMY)
    rows[5] = _row(5, [_u(1189, (100, 200, 180, 300), True)])  # an Orc Archer: the Orc Lord's
    with pytest.raises(SystemExit, match="an MVP-party unit is on screen"):
        st.hunt_negatives(rows, set(rows), "s")


# --- the chat window of the session's date -------------------------------------------------------

# the Orc Lord study's sessions (orclord-recognizer.md 1, 4b, 10a): all before 2026-11-05
ORC_SIDS = ("20261025T195325-rdp-ow1", "20261025T200922-rdp-rogue-pilot",
            "20261025T203115-rdp-rogue-pilot2", "20261025T204315-rdp-rogue-s1",
            "20261026T000413-rdp-ow2", "20261025T213953-rdp-rogue-a1")  # fmt: skip
LEGACY_CHAT, CHAT_1105 = (0, 532, 600, 626), (0, 585, 600, 720)


def test_the_orc_lords_sessions_keep_their_ui_windows_and_masks() -> None:
    import client_layout

    own = {"standard": mw.STANDARD_RECTS, "hunt": mw.HUNT_RECTS}
    for layout, rects in own.items():
        assert (
            rects == client_layout.RECTS[layout] and rects[client_layout.CHAT_INDEX] == LEGACY_CHAT
        )
        assert st.mask_rects({"layout": layout}) == rects  # a truth from before B1: no "chat"
        for sid in ORC_SIDS:
            ui = st.ui_rects_for(layout, sid)
            assert ui["rects"] == client_layout.RECTS[layout], (layout, sid)
            assert ui["chat"] == {"rect": list(LEGACY_CHAT), "nested_dropped": [],
                                  "how": "auto:legacy (chat_window.for_sid)"}  # fmt: skip
            assert st.mask_rects({"layout": layout, "chat": ui["chat"]}) == rects
    a = st.parser().parse_args(ORC_LINES["truth"])
    assert a.chat == "auto"


def test_a_xmas02_session_gets_the_docked_chat_window_in_truth_and_mask() -> None:
    sid = "20261109T080000-rdp-xmas02-w1"
    ui = st.ui_rects_for("hunt", sid)
    assert ui["chat"]["rect"] == list(CHAT_1105) and ui["chat"]["how"].startswith("auto:standard")
    assert ui["chat"]["nested_dropped"] == [[0, 668, 50, 720]]  # notice_left lies inside it
    assert CHAT_1105 in ui["rects"] and LEGACY_CHAT not in ui["rects"]
    assert st.ui_rects_for("hunt", sid, "legacy")["chat"]["rect"] == list(LEGACY_CHAT)
    # the in-view rule: a unit on the chat window's lower lines is behind the UI now
    box = (300.0, 600.0, 380.0, 700.0)
    assert st.in_view(box, (1280, 720), mw.HUNT_RECTS) is True
    assert st.in_view(box, (1280, 720), ui["rects"]) is False
    # decide()'s mask: the truth's chat window, the rest of the layout as mvp_watch's
    rects = st.mask_rects({"layout": "hunt", "chat": ui["chat"]})
    assert rects[4] == CHAT_1105 and rects[:4] + rects[5:] == mw.HUNT_RECTS[:4] + mw.HUNT_RECTS[5:]
    m = _model()
    f = _frame(m, foot=(300, 700), colour=(150, 250, 180))  # an aura-coloured ring in the chat
    assert mw.decide(f, m, ui_rects=mw.HUNT_RECTS)["seen"] is True  # the legacy mask misses it
    assert mw.decide(f, m, ui_rects=rects)["seen"] is False


def test_a_truth_without_the_maps_gat_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_scene would project on flat ground without the GAT, silently: refused before the
    session is even read."""
    from poring_dataset import camera

    monkeypatch.setattr(camera, "GAT_DIR", tmp_path)
    kw: dict[str, Any] = {"kb": tmp_path, "mapcache_dir": tmp_path}
    with pytest.raises(SystemExit, match="xmas_dun02.gat: the map's GAT is not extracted"):
        st.truth(tmp_path / "no-session", "hunt", prof=mp.STORMY, **kw)
    with pytest.raises(SystemExit, match="prt_fild08.gat: the map's GAT"):
        st.truth(tmp_path / "no-session", "hunt", map_name="prt_fild08", **kw)
