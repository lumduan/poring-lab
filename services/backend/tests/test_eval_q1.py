"""scripts/eval_q1.py: gef10-eval.md's Q1 / E1 scorer (AMENDMENT R2-2) and predict_dir's refs.

Synthetic cases pin every rule (EVALUATED, one-to-one per frame, the precision denominator, the bar
at 50, the strata, the splits, the look-alike confusion, the refs). The POSITIVE CASE on real data
(scorers-must-be-committed) is round 2's T2 pack (TRAIN labels, never TEST): it skips when the
scratch files or the NAS are absent.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import eval_q1 as q  # noqa: E402

LADY, WARRIOR, LORD, ARCHER = 1273, 1023, 1190, 1189
MANIFEST: dict[str, Any] = {
    "cache_id": "synthetic",
    "names": {"0": "player", "1": "npc", "2": "warp", "3": "lady_c", "4": "warrior_c",
              "5": "lord_c", "6": "archer_c"},
    "classes": {"mode": "species", "list": "x.json", "sha256": "0" * 64,
                "fixed": {"player": 0, "npc": 1, "warp": 2}, "monster_first_id": 3,
                "monsters": [LADY, WARRIOR, LORD, ARCHER]},
}  # fmt: skip
CLS = q.class_map(MANIFEST)
LETTERS = {"A": LADY, "B": WARRIOR, "C": LORD, "D": ARCHER}


def crop(session: str, fid: int, mob: int, box: list[float], stratum: str = "N",
         under: bool | None = False) -> dict[str, Any]:  # fmt: skip
    return {"mob": mob, "session": session, "frame_id": fid, "gid": 1, "box": box,
            "under": under, "stratum": stratum, "engaged": stratum == "E"}  # fmt: skip


def make_key(crops: list[dict[str, Any]]) -> dict[str, Any]:
    return {"letters": dict(LETTERS), "tier_species": [LADY, WARRIOR, LORD, ARCHER],
            "crops": {f"{i:03d}": c for i, c in enumerate(crops, 1)}}  # fmt: skip


def all_good(key: dict[str, Any]) -> dict[str, dict[str, Any]]:
    letter = {int(m): k for k, m in key["letters"].items()}
    return {c: {"crop": c, "q1": "yes", "q2": "good", "q3": letter[int(k["mob"])]}
            for c, k in key["crops"].items()}  # fmt: skip


def det(cls: str, box: list[float], dx: float = 0.0) -> dict[str, Any]:
    return {"cls": cls, "x1": box[0] + dx, "y1": box[1], "x2": box[2] + dx, "y2": box[3],
            "conf": 0.9}  # fmt: skip


def run(key: dict[str, Any], frames: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    crops, _why = q.evaluated(key, all_good(key), all_good(key))
    return q.score(key, crops, frames, CLS)


BOX = [100.0, 100.0, 140.0, 160.0]


# --- the refs ---------------------------------------------------------------------------------


def test_frame_key_is_the_cache_member_naming() -> None:
    assert q.frame_key("20261026T044312-rdp-x", 7) == "20261026T044312-rdp-x.000000007"
    assert q.frame_key("S", 123456789) == "S.123456789"


def test_container_path_maps_the_nas_and_refuses_anything_else() -> None:
    p = Path("/mnt/poring-lab-datasets/S/shard-000001.tar")
    assert q.to_container(p) == "/datasets/S/shard-000001.tar"
    with pytest.raises(SystemExit, match="not under"):
        q.to_container(Path("/dev/shm/S/shard-000001.tar"))


def test_latency_frames_are_a_seeded_shuffle_of_the_sorted_keys() -> None:
    keys = [q.frame_key("S", i) for i in range(300)]
    pick = q.latency_keys(reversed(keys), 35)
    assert len(pick) == 200 and len(set(pick)) == 200 and set(pick) <= set(keys)
    assert pick == q.latency_keys(keys, 35)  # input order does not matter
    assert pick != q.latency_keys(keys, 36)
    assert q.latency_keys(keys[:50], 35, 200) == q.latency_keys(keys[:50], 35, 50)  # fewer: all


def _shard(path: Path, frames: list[int]) -> dict[int, tuple[int, int]]:
    """A recorder-like shard: <frame_id 9 digits>.png (PNG signature) + .json per frame."""
    with tarfile.open(path, "w") as tar:
        for fid in frames:
            for ext, data in (("png", b"\x89PNG\r\n\x1a\n" + bytes(40)),
                              ("json", json.dumps({"frame_id": fid}).encode())):  # fmt: skip
                info = tarfile.TarInfo(f"{fid:09d}.{ext}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    out = {}
    with tarfile.open(path) as tar:
        for m in tar:
            if m.name.endswith(".png"):
                out[int(m.name.split(".")[0])] = (m.offset_data, m.size)
    return out


def _labels(tmp: Path, nas: Path) -> tuple[Path, dict[str, Any]]:
    sess = "20261026T000000-rdp-t"
    (nas / sess).mkdir(parents=True)
    where = _shard(nas / sess / "shard-000000.tar", [5, 6, 7])
    doc = {"session": sess, "part": sess, "frames": [
        {"frame_id": f, "shard": "shard-000000.tar", "offset": where[f][0], "size": where[f][1]}
        for f in (5, 6, 7)]}  # fmt: skip
    lab = tmp / "labels" / f"{sess}.json"
    lab.parent.mkdir()
    lab.write_text(json.dumps(doc))
    key = make_key([crop(sess, 7, LADY, BOX), crop(sess, 5, WARRIOR, BOX, "E"),
                    crop(sess, 7, LORD, BOX)])  # fmt: skip
    key["sources"] = [{"part": sess, "file": f"labels/{sess}.json",
                       "sha256": hashlib.sha256(lab.read_bytes()).hexdigest()}]  # fmt: skip
    (tmp / "key").mkdir()
    (tmp / "key" / "answer_key.json").write_text(json.dumps(key))
    return tmp / "key" / "answer_key.json", doc


def test_refs_name_exactly_the_crop_frames_in_container_paths(tmp_path: Path) -> None:
    nas = tmp_path / "nas"
    key_path, doc = _labels(tmp_path, nas)
    out = tmp_path / "refs.json"
    assert q.main(["refs", str(key_path), "--out", str(out), "--session-root", str(nas),
                   "--host-root", str(nas), "--latency-200", "35"]) == 0  # fmt: skip
    refs = json.loads(out.read_text())
    sess = doc["session"]
    assert list(refs) == [q.frame_key(sess, 5), q.frame_key(sess, 7)]  # frame 6 carries no crop
    row7 = next(f for f in doc["frames"] if f["frame_id"] == 7)
    assert refs[q.frame_key(sess, 7)] == {
        "path": f"/datasets/{sess}/shard-000000.tar",
        "offset": row7["offset"],
        "size": row7["size"],
    }
    lat = json.loads((tmp_path / "refs-latency200-seed35.json").read_text())
    assert sorted(lat) == sorted(refs)  # fewer than 200 frames: all of them


def test_refs_refuse_a_changed_label_file_and_a_wrong_member(tmp_path: Path) -> None:
    nas = tmp_path / "nas"
    key_path, doc = _labels(tmp_path, nas)
    lab = tmp_path / "labels" / f"{doc['session']}.json"
    good = lab.read_text()
    lab.write_text(good + " ")
    with pytest.raises(SystemExit, match="sha256"):
        q.main(["refs", str(key_path), "--out", str(tmp_path / "r.json"),
                "--session-root", str(nas), "--host-root", str(nas)])  # fmt: skip
    # the label file points frame 7 at frame 6's bytes: the member's own name refuses it
    bad = json.loads(good)
    f6 = next(f for f in bad["frames"] if f["frame_id"] == 6)
    for f in bad["frames"]:
        if f["frame_id"] == 7:
            f["offset"] = f6["offset"]
    lab.write_text(json.dumps(bad))
    key = json.loads(key_path.read_text())
    key["sources"][0]["sha256"] = hashlib.sha256(lab.read_bytes()).hexdigest()
    key_path.write_text(json.dumps(key))
    with pytest.raises(SystemExit, match="is frame 6"):
        q.main(["refs", str(key_path), "--out", str(tmp_path / "r.json"),
                "--session-root", str(nas), "--host-root", str(nas)])  # fmt: skip


def test_refs_refuse_a_shard_that_is_not_there(tmp_path: Path) -> None:
    nas = tmp_path / "nas"
    key_path, doc = _labels(tmp_path, nas)
    (nas / doc["session"] / "shard-000000.tar").unlink()
    with pytest.raises(SystemExit, match="does not exist"):
        q.main(["refs", str(key_path), "--out", str(tmp_path / "r.json"),
                "--session-root", str(nas), "--host-root", str(nas)])  # fmt: skip


def test_member_frame_id_reads_the_tar_name() -> None:
    assert q.member_frame_id(b"000000024.png" + bytes(499)) == 24
    assert q.member_frame_id(b"frames/000000024.png" + bytes(492)) == 24
    assert q.member_frame_id(b"S.000000024.png" + bytes(497)) is None  # another naming: no claim


# --- the class map ----------------------------------------------------------------------------


def test_class_map_reads_the_training_cache_manifest() -> None:
    assert CLS == {LADY: "lady_c", WARRIOR: "warrior_c", LORD: "lord_c", ARCHER: "archer_c"}
    bad = json.loads(json.dumps(MANIFEST))
    bad["names"]["4"] = "lady_c"
    with pytest.raises(SystemExit, match="share a class name"):
        q.class_map(bad)
    bad = json.loads(json.dumps(MANIFEST))
    bad["names"]["0"] = "lady_c"
    with pytest.raises(SystemExit, match="fixed"):
        q.class_map(bad)
    with pytest.raises(SystemExit, match="per-species"):
        q.class_map({"names": {"0": "player", "1": "monster", "2": "npc"}})


def test_class_map_ids_of_the_committed_gef10_list() -> None:
    """gef10-eval.md "The model": ids 21-25 are Orc Lady, Orc Warrior, Orc Baby, Orc Lord, Orc
    Archer; Poporing 19, Green Plant 20 (the names are the KB's: placeholders here)."""
    cl = json.loads((ROOT / "config/detector/classes-v2orc-payf07-gef10.json").read_text())
    n = cl["monster_first_id"] + len(cl["monsters"])
    man = {"names": {str(i): f"c{i}" for i in range(n)},
           "classes": {"mode": "species", **cl}}  # fmt: skip
    for k, v in cl["fixed"].items():
        man["names"][str(v)] = k
    m = q.class_map(man)
    assert [m[x] for x in (1273, 1023, 1686, 1190, 1189, 1031, 1080)] == [
        "c21", "c22", "c23", "c24", "c25", "c19", "c20"]  # fmt: skip


GEF10_MANIFEST = Path(
    "/mnt/poring-lab-datasets/.framecache/v2orc-payf07-gef10-20261026/manifest.json"
)


@pytest.mark.skipif(not GEF10_MANIFEST.exists(), reason="the NAS cache is not mounted")
def test_class_map_of_the_real_training_cache() -> None:
    """The model's names are the KB's aegis names, lower case: Orc Warrior is ``ork_warrior``."""
    man = json.loads(GEF10_MANIFEST.read_text())
    sha = hashlib.sha256((ROOT / man["classes"]["list"]).read_bytes()).hexdigest()
    assert man["classes"]["sha256"] == sha
    assert sha.startswith("66de5684") and sha.endswith("a7ff747c2")  # gef10-eval.md's list
    m = q.class_map(man)
    assert {m[x] for x in (1273, 1023, 1686, 1190, 1189, 1031, 1080)} == {
        man["names"][str(i)] for i in (21, 22, 23, 24, 25, 19, 20)}  # fmt: skip
    assert m[1023].startswith("ork") and m[1031] == man["names"]["19"]


# --- EVALUATED --------------------------------------------------------------------------------


def test_evaluated_needs_both_labellers_yes_good_and_the_species() -> None:
    key = make_key([crop("S", i, LADY, BOX) for i in range(7)])
    a, b = all_good(key), all_good(key)
    a["001"]["q1"] = "no"
    b["002"]["q2"] = "loose"
    a["003"]["q3"] = "B"  # Orc Warrior's letter
    b["004"]["q3"] = "unsure"
    del a["005"]
    b["006"]["q3"] = " a "  # the letter is read like blind_score's
    crops, why = q.evaluated(key, a, b)
    assert crops == ["006", "007"]
    assert why["not_evaluated_by"] == {
        "A": {"missing_answer": 1, "q1_not_yes": 1, "q3_not_the_species": 1},
        "B": {"q2_not_good": 1, "q3_not_the_species": 1}}  # fmt: skip


# --- the scores -------------------------------------------------------------------------------


def test_one_to_one_per_frame_nearest_centre_first() -> None:
    """Two Orc Lady crops overlap; ONE detection centred in both matches the nearer one only."""
    near, far = [100.0, 100.0, 140.0, 160.0], [110.0, 100.0, 170.0, 160.0]
    key = make_key([crop("S", 1, LADY, near), crop("S", 1, LADY, far)])
    res = run(key, {q.frame_key("S", 1): [det("lady_c", [112, 120, 128, 140])]})
    lady = res["Q1"]["per_species"]["lady_c"]
    assert (lady["evaluated"], lady["matched"], lady["unmatched_in_boxes"]) == (2, 1, 0)
    assert (lady["recall"], lady["precision"]) == (0.5, 1.0)


def test_precision_counts_only_class_s_detections_inside_evaluated_boxes() -> None:
    lady, warrior, unevaluated = BOX, [300.0, 100.0, 340.0, 160.0], [500.0, 100.0, 540.0, 160.0]
    key = make_key([crop("S", 1, LADY, lady), crop("S", 1, WARRIOR, warrior),
                    crop("S", 1, LORD, unevaluated)])  # fmt: skip
    a, b = all_good(key), all_good(key)
    a["003"]["q2"] = "off"  # the Orc Lord crop is NOT evaluated
    frames = {q.frame_key("S", 1): [
        det("lady_c", lady),  # matches the Orc Lady
        det("lady_c", warrior),  # a look-alike on the evaluated Orc Warrior: counts against Lady
        det("lady_c", unevaluated),  # inside a box that is not evaluated: not scored
        det("lady_c", [900, 600, 940, 660]),  # elsewhere: not scored
        det("warrior_c", lady, dx=5),  # a Warrior box on the Lady: counts against Warrior
    ]}  # fmt: skip
    crops, _ = q.evaluated(key, a, b)
    res = q.score(key, crops, frames, CLS)["Q1"]
    lady_r, war_r = res["per_species"]["lady_c"], res["per_species"]["warrior_c"]
    assert (lady_r["matched"], lady_r["unmatched_in_boxes"], lady_r["precision"]) == (1, 1, 0.5)
    assert lady_r["recall"] == 1.0
    assert (war_r["matched"], war_r["unmatched_in_boxes"]) == (0, 1)
    assert (war_r["recall"], war_r["precision"]) == (0.0, 0.0)
    assert res["confusion"] == {"lady_c": {"lady_c": 1}, "warrior_c": {"lady_c": 1}}
    assert "lord_c" not in res["per_species"]


def test_a_duplicate_detection_counts_against_precision() -> None:
    key = make_key([crop("S", 1, LADY, BOX)])
    res = run(key, {q.frame_key("S", 1): [det("lady_c", BOX), det("lady_c", BOX, dx=3)]})
    lady = res["Q1"]["per_species"]["lady_c"]
    assert (lady["matched"], lady["unmatched_in_boxes"], lady["precision"]) == (1, 1, 0.5)


def test_the_bar_needs_50_evaluated_crops_and_both_numbers_at_0_80() -> None:
    def case(n: int, hits: int, dups: int) -> dict[str, Any]:
        key = make_key([crop("S", i, LADY, BOX) for i in range(n)])
        frames = {q.frame_key("S", i): ([det("lady_c", BOX)] if i < hits else [])
                  + ([det("lady_c", BOX, dx=2)] if i < dups else []) for i in range(n)}  # fmt: skip
        return run(key, frames)["Q1"]

    at = case(50, 40, 10)  # recall 40/50 = 0.80, precision 40/50 = 0.80: exactly the bar
    lady = at["per_species"]["lady_c"]
    assert (lady["recall"], lady["precision"], lady["bar"], lady["pass"]) == (0.8, 0.8, True, True)
    assert at["species_with_bar"] == ["lady_c"] and at["all_bars_pass"] is True
    low_r = case(50, 39, 0)["per_species"]["lady_c"]
    assert low_r["pass"] is False
    low_p = case(50, 50, 13)["per_species"]["lady_c"]  # 50 / 63 = 0.794
    assert low_p["recall"] == 1.0 and low_p["pass"] is False
    few = case(49, 49, 0)
    lady49 = few["per_species"]["lady_c"]
    assert (lady49["bar"], lady49["pass"]) == (False, None)
    assert few["species_with_bar"] == [] and few["all_bars_pass"] is None  # never read as a pass


def test_strata_n_is_q1_e_is_e1_and_a_match_counts_for_its_own_stratum() -> None:
    n_box, e_box = [100.0, 100.0, 160.0, 160.0], [110.0, 100.0, 170.0, 160.0]
    key = make_key([crop("S", 1, LADY, n_box, "N"), crop("S", 1, LADY, e_box, "E"),
                    crop("S", 2, WARRIOR, BOX, "E")])  # fmt: skip
    frames = {q.frame_key("S", 1): [det("lady_c", n_box), det("lady_c", e_box)],
              q.frame_key("S", 2): []}  # fmt: skip
    res = run(key, frames)
    n, e = res["Q1"]["per_species"], res["E1"]["per_species"]
    assert set(n) == {"lady_c"} and set(e) == {"lady_c", "warrior_c"}
    # the E detection's centre also lies in the N box; it matched its E crop, so it is not an N FP
    assert (n["lady_c"]["matched"], n["lady_c"]["unmatched_in_boxes"]) == (1, 0)
    assert (e["lady_c"]["matched"], e["lady_c"]["precision"]) == (1, 1.0)
    assert (e["warrior_c"]["recall"], e["warrior_c"]["precision"]) == (0.0, None)
    assert res["strata_overlap"]["frames_both_strata"] == 1
    assert res["strata_overlap"]["matched_detections_also_in_other_stratum"] == 2


def test_splits_by_session_and_under_a_model() -> None:
    key = make_key([crop("a9", 1, LADY, BOX, under=True), crop("a10", 1, LADY, BOX, under=False),
                    crop("a10", 2, LADY, BOX, under=None)])  # fmt: skip
    frames = {q.frame_key("a9", 1): [det("lady_c", BOX)], q.frame_key("a10", 1): [],
              q.frame_key("a10", 2): [det("lady_c", BOX)]}  # fmt: skip
    res = run(key, frames)["Q1"]
    by_s = {k: v["lady_c"]["recall"] for k, v in res["split_session"].items()}
    by_u = {k: v["lady_c"]["recall"] for k, v in res["split_under"].items()}
    assert by_s == {"a10": 0.5, "a9": 1.0}
    assert by_u == {"clear": 0.0, "under": 1.0, "unknown": 1.0}
    assert "pass" not in res["split_session"]["a9"]["lady_c"]  # splits decide nothing


def test_look_alike_groups_report_what_each_crop_was_seen_as() -> None:
    key = make_key([crop("S", 1, LORD, BOX), crop("S", 2, LORD, BOX), crop("S", 3, ARCHER, BOX)])
    frames = {q.frame_key("S", 1): [det("warrior_c", BOX)], q.frame_key("S", 2): [],
              q.frame_key("S", 3): [det("archer_c", BOX)]}  # fmt: skip
    res = run(key, frames)["Q1"]
    assert res["look_alike"]["lord_warrior_archer"] == {
        "lord_c": {"none": 1, "warrior_c": 1}, "archer_c": {"archer_c": 1}}  # fmt: skip
    assert res["per_species"]["lord_c"]["recall"] == 0.0


def test_a_species_without_a_class_is_reported_apart() -> None:
    blue = 1079
    key = make_key([crop("S", 1, LADY, BOX), crop("S", 1, blue, [300, 100, 340, 160])])
    key["letters"]["E"] = blue
    a = all_good(key)
    crops, _ = q.evaluated(key, a, a)
    res = q.score(key, crops, {q.frame_key("S", 1): [det("lady_c", [300, 100, 340, 160])]}, CLS)
    q1 = res["Q1"]
    assert set(q1["per_species"]) == {"lady_c"} and set(q1["not_a_class"]) == {"unlisted:1079"}
    assert q1["per_species"]["lady_c"]["unmatched_in_boxes"] == 1  # ANY evaluated box counts


def test_a_missing_prediction_frame_is_refused_never_empty() -> None:
    key = make_key([crop("S", 1, LADY, BOX)])
    with pytest.raises(SystemExit, match="lacks 1 evaluated frames"):
        run(key, {})


def test_pred_settings_and_foreign_classes_are_refused(tmp_path: Path) -> None:
    p = tmp_path / "p.json"
    names = MANIFEST["names"].values()
    p.write_text(json.dumps({"weights": "w", "imgsz": 1280, "conf": 0.3, "frames": {}}))
    with pytest.raises(SystemExit, match="settings"):
        q.load_pred(p, names, any_settings=False)
    assert q.load_pred(p, names, any_settings=True)["conf"] == 0.3
    p.write_text(json.dumps({"weights": "w", "imgsz": 1280, "conf": 0.25,
                             "frames": {"k": [det("monster", BOX)]}}))  # fmt: skip
    with pytest.raises(SystemExit, match="not the manifest's"):
        q.load_pred(p, names, any_settings=False)


def test_score_cli_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    key = make_key([crop("S", 1, LADY, BOX), crop("S", 2, WARRIOR, BOX, "E")])
    (tmp_path / "key.json").write_text(json.dumps(key))
    ans = list(all_good(key).values())
    (tmp_path / "A.json").write_text(json.dumps(ans))
    (tmp_path / "B.json").write_text(json.dumps(ans))
    (tmp_path / "m.json").write_text(json.dumps(MANIFEST))
    pred = {
        "weights": "w.pt",
        "imgsz": 1280,
        "conf": 0.25,
        "frames": {q.frame_key("S", 1): [det("lady_c", BOX)], q.frame_key("S", 2): []},
    }
    (tmp_path / "p.json").write_text(json.dumps(pred))
    out = tmp_path / "score.json"
    assert (
        q.main(
            [
                "score",
                *(str(tmp_path / f) for f in ("key.json", "A.json", "B.json", "p.json")),
                "--cache-manifest",
                str(tmp_path / "m.json"),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    res = json.loads(out.read_text())
    assert res["evaluated_crops"] == 2 and res["q1_all_bars_pass"] is None
    assert res["Q1"]["per_species"]["lady_c"]["recall"] == 1.0
    assert res["E1"]["per_species"]["warrior_c"]["recall"] == 0.0
    assert res["class_map"][str(LADY)] == "lady_c"
    assert json.loads(capsys.readouterr().out)["Q1"]["lady_c"] == [1, 1.0, 1.0, None]


# --- the POSITIVE CASE on real data: round 2's T2 pack (TRAIN labels) --------------------------

T2 = Path("/dev/shm/poring-lab-tmp/gef10-det")
T2_KEY = T2 / "t2-key/answer_key.json"
T2_A, T2_B = T2 / "t2-answers/A.json", T2 / "t2-answers/B.json"
REAL = all(p.exists() for p in (T2_KEY, T2_A, T2_B, GEF10_MANIFEST))


@pytest.fixture(scope="module")
def t2() -> dict[str, Any]:
    key = json.loads(T2_KEY.read_text())
    a, b = q.blind_score.load_answers(T2_A), q.blind_score.load_answers(T2_B)
    crops, why = q.evaluated(key, a, b)
    return {"key": key, "crops": crops, "why": why,
            "cls": q.class_map(json.loads(GEF10_MANIFEST.read_text()))}  # fmt: skip


def _detector(t2: dict[str, Any], cls_of: Any, dx: float = 0.0) -> dict[str, list[Any]]:
    key = t2["key"]
    frames: dict[str, list[Any]] = {q.frame_key(c["session"], c["frame_id"]): []
                                    for c in key["crops"].values()}  # fmt: skip
    for c in t2["crops"]:
        k = key["crops"][c]
        frames[q.frame_key(k["session"], k["frame_id"])].append(
            det(cls_of(int(k["mob"])), [float(v) for v in k["box"]], dx)
        )
    return frames


@pytest.mark.skipif(not REAL, reason="round 2's T2 key / answers or the NAS cache are absent")
def test_t2_refs_resolve_every_crop_frame_on_the_nas(tmp_path: Path) -> None:
    out = tmp_path / "refs.json"
    assert q.main(["refs", str(T2_KEY), "--out", str(out), "--latency-200", "35"]) == 0
    refs = json.loads(out.read_text())
    key = json.loads(T2_KEY.read_text())
    assert sorted(refs) == sorted({q.frame_key(c["session"], c["frame_id"])
                                   for c in key["crops"].values()})  # fmt: skip
    assert len(refs) == 225 and all(r["path"].startswith("/datasets/") for r in refs.values())
    lat = json.loads((tmp_path / "refs-latency200-seed35.json").read_text())
    assert list(lat) == q.latency_keys(refs, 35) and len(lat) == 200


@pytest.mark.skipif(not REAL, reason="round 2's T2 key / answers or the NAS cache are absent")
def test_t2_a_perfect_detector_scores_one_everywhere(t2: dict[str, Any]) -> None:
    """13q: 245 of 246 crops are good with the right species for BOTH labellers (A answered
    "unsure" on one Orc Baby). Detections = the evaluated crops' own boxes and classes."""
    assert len(t2["crops"]) == 245
    assert t2["why"]["not_evaluated_by"] == {"A": {"q3_not_the_species": 1}, "B": {}}
    res = q.score(t2["key"], t2["crops"], _detector(t2, t2["cls"].__getitem__), t2["cls"])
    n = {s: (v["evaluated"], v["recall"], v["precision"], v["pass"])
         for s, v in res["Q1"]["per_species"].items()}  # fmt: skip
    c = t2["cls"]
    assert n == {c[m]: (29 if m == 1686 else 30, 1.0, 1.0, None)
                 for m in (1273, 1023, 1031, 1686, 1190, 1189, 1080)}  # fmt: skip
    e = {s: (v["evaluated"], v["recall"], v["precision"])
         for s, v in res["E1"]["per_species"].items()}  # fmt: skip
    assert e == {c[1273]: (30, 1.0, 1.0), c[1023]: (6, 1.0, 1.0)}
    assert res["Q1"]["all_bars_pass"] is None  # 30 per species: no bar exists on T2


@pytest.mark.skipif(not REAL, reason="round 2's T2 key / answers or the NAS cache are absent")
def test_t2_a_shifted_or_wrong_class_detector_scores_zero(t2: dict[str, Any]) -> None:
    shifted = q.score(t2["key"], t2["crops"], _detector(t2, t2["cls"].__getitem__, dx=2000.0),
                      t2["cls"])  # fmt: skip
    for st in ("Q1", "E1"):
        for v in shifted[st]["per_species"].values():
            assert (v["recall"], v["precision"]) == (0.0, None)  # nothing inside a box
    # every crop detected in place, as the NEXT species' class (Orc Lady -> Orc Warrior, ...)
    mobs = [1273, 1023, 1031, 1686, 1190, 1189, 1080]
    wrong = q.score(t2["key"], t2["crops"],
                    _detector(t2, lambda m: t2["cls"][mobs[(mobs.index(m) + 1) % len(mobs)]]),
                    t2["cls"])  # fmt: skip
    for st in ("Q1", "E1"):
        for v in wrong[st]["per_species"].values():
            assert v["recall"] == 0.0 and v["matched"] == 0
    assert wrong["Q1"]["confusion"][t2["cls"][1190]] == {t2["cls"][1189]: 30}  # Lord seen as Archer
