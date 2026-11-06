"""The live detector against the packet truth (scripts/detector_vs_packets.py,
docs/planning/gef10-round2.md 4): the pure parts on SYNTHETIC boxes (no packets, no pixels)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import detector_vs_packets as dv  # noqa: E402

S = 1_000_000_000


def unit(gid: int, box: Any, job: int = 1273, in_view: bool = True) -> dict[str, Any]:
    return {"gid": gid, "job": job, "box": box, "state": "idle", "cell": (10, 10),
            "in_view": in_view}  # fmt: skip


def test_dist_bins_are_rounded_chebyshev_cells() -> None:
    assert dv.chebyshev((10, 10), (13, 5.4)) == 4.6
    assert [dv.dist_bin(d) for d in (0, 5.4, 5.5, 10.49, 10.5, 15.4, 15.5, 30)] == [
        "0-5", "0-5", "6-10", "6-10", "11-15", "11-15", "16+", "16+"]  # fmt: skip
    with pytest.raises(ValueError):
        dv.dist_bin(-3)


def test_recall_is_any_detection_centre_in_the_box_and_one_to_one_beside() -> None:
    """Two overlapping units and ONE detection between them: both are hit (the brief's recall),
    one is matched one-to-one (the nearer centre); a unit out of view is not scored."""
    a = unit(1, (100, 100, 160, 180))
    b = unit(2, (130, 100, 190, 180))
    far = unit(3, (600, 100, 660, 180), in_view=False)
    det = [(150, 110, 170, 170)]  # centre (160, 140): inside a (its edge) and b, b's centre
    rows, verdicts = dv.score_capture([a, b, far], det)
    assert [(r["gid"], r["hit"], r["hit_1to1"]) for r in rows] == [(1, True, False),
                                                                   (2, True, True)]  # fmt: skip
    assert verdicts == ["tp"]


def test_precision_verdicts_tp_dying_self_other() -> None:
    """A detection on a unit out of view is still a true one (the sprite is drawn); the rest are
    split: on a dying unit, on our own character, elsewhere."""
    off = unit(1, (0, 0, 40, 40), in_view=False)
    nosheet = {"gid": 2, "job": 1023, "box": None, "in_view": False}
    dets = [
        (10, 10, 30, 30),
        (300, 300, 320, 320),
        (630, 330, 650, 380),
        (900, 500, 920, 520),
        (45, 10, 65, 30),
    ]  # the last: centre (55, 20), 15 px right of the unit's box
    rows, verdicts = dv.score_capture([off, nosheet], dets, dying=[(290, 290, 330, 330)],
                                      self_box=(620, 300, 660, 380))  # fmt: skip
    assert rows == [] and verdicts == ["tp", "dying", "self", "other", "near_unit"]


def test_the_precision_split_by_our_motion_counts_every_verdict_once() -> None:
    """xmas02-eval.md P4A: precision on the STILL captures. Every verdict but tp counts against
    it; an empty split has no precision (not zero)."""
    still = dv.Counter(["tp", "tp", "tp", "dying", "self", "other", "near_unit"])
    assert dv.precision_of(still) == {"detections": 7, "tp": 3, "precision": 0.429}
    assert dv.precision_of(dv.Counter()) == {"detections": 0, "tp": 0, "precision": None}
    src = Path(dv.__file__).read_text()
    assert src.count('motion_verdicts["moving" if moving else "still"].update(vs)') == 1
    assert src.index("moving = before != row") < src.index('motion_verdicts["moving" if')


def test_a_unit_with_no_detection_is_a_miss() -> None:
    rows, verdicts = dv.score_capture([unit(1, (100, 100, 160, 180))], [])
    assert rows[0]["hit"] is False and rows[0]["hit_1to1"] is False and verdicts == []
    assert dv.tally(rows) == {"n": 1, "hit": 0, "recall": 0.0, "hit_1to1": 0, "recall_1to1": 0.0}
    assert dv.tally([])["recall"] is None


def test_episodes_cut_at_gaps_and_time_the_first_hit() -> None:
    rows = [
        {"gid": 7, "job": 1023, "t": 0 * S, "hit": False, "dist": 12.0},
        {"gid": 7, "job": 1023, "t": 1 * S, "hit": False, "dist": 11.0},
        {"gid": 7, "job": 1023, "t": 2 * S, "hit": True, "dist": 10.0},
        {"gid": 7, "job": 1023, "t": 10 * S, "hit": False, "dist": 4.0},  # a new episode: > 2 s
        {"gid": 8, "job": 1031, "t": 1 * S, "hit": True, "dist": 3.0},
    ]  # fmt: skip
    eps = dv.episodes(rows)
    got = sorted((e["gid"], e["t0"], e["captures"], e["dist0"], e["delay_s"]) for e in eps)
    assert got == [(7, 0, 3, 12.0, 2.0), (7, 10 * S, 1, 4.0, None), (8, 1 * S, 1, 3.0, 0.0)]


def test_species_keys_and_percentiles() -> None:
    assert dv.species_key(1273) == "1273 Orc Lady" and dv.species_key(1190) == "other"
    assert dv.percentile([100.0, 200.0, 300.0], 50) == 200.0 and dv.percentile([], 95) is None


def test_predict_rows_turn_a_new_models_output_into_box_rows() -> None:
    """gef10-eval.md AMENDMENT R2-2: predict_dir on the demo's frames (NNNNN-<t ns>.jpg) ->
    boxes.jsonl rows in time order; species collapsed to ``monster``; ms from --timing."""
    pred = {
        "frames": {
            "00002-300": [{"cls": "orc_lady", "x1": 1, "y1": 2, "x2": 3, "y2": 4, "conf": 0.9}],
            "00001-200": [{"cls": "player", "x1": 5, "y1": 6, "x2": 7, "y2": 8, "conf": 0.8},
                          {"cls": "poporing", "x1": 9, "y1": 9, "x2": 11, "y2": 12, "conf": 0.3}],
        },
        "timing_ms": {"per_frame": {"00001-200": 21.5}},
    }  # fmt: skip
    rows = dv.predict_rows(pred)
    assert [r["t"] for r in rows] == [200, 300]
    assert rows[0]["boxes"] == [[5.0, 6.0, 7.0, 8.0, 0.8, "player"],
                                [9.0, 9.0, 11.0, 12.0, 0.3, "monster"]]  # fmt: skip
    assert rows[1]["boxes"][0][5] == "monster" and rows[0]["ms"] == 21.5 and rows[1]["ms"] is None
    with pytest.raises(SystemExit):
        dv.predict_rows({"frames": {"frame-x": []}})


# --- the recorder-session path (rogue-xmas02.md 4A, X2) ------------------------------------------


def test_the_species_of_each_map_scored_and_reported() -> None:
    """X2's four common species are scored; Garm Baby, the MVP and its Goblin are reported; the
    gef10 default (SPECIES, species_key without a table) is unchanged."""
    xmas = {1249: "Myst Case", 1248: "Cruiser", 1265: "Cookie", 1246: "Christmas Cookie"}
    assert dv.SPECIES_BY_MAP["xmas_dun02"] == xmas
    reported = {1515: "Garm Baby", 1251: "Stormy Knight", 1607: "Christmas Goblin"}
    assert dv.REPORTED_BY_MAP["xmas_dun02"] == reported
    assert dv.SPECIES_BY_MAP["gef_fild10"] == dv.SPECIES
    assert dv.REPORTED_BY_MAP["gef_fild10"] == {}
    names = {**dv.SPECIES_BY_MAP["xmas_dun02"], **dv.REPORTED_BY_MAP["xmas_dun02"]}
    assert dv.species_key(1246, names) == "1246 Christmas Cookie"
    assert dv.species_key(1251, names) == "1251 Stormy Knight"
    assert dv.species_key(1273, names) == "other" and dv.species_key(1273) == "1273 Orc Lady"


def test_the_chat_window_follows_the_sessions_date() -> None:
    """chat_window.for_sid: the 2026-11-05 standard (docked, 6 lines) from 20261105T12 on, the
    frozen legacy window before; a name or a measured rectangle overrides."""
    rect, how = dv.chat_rect_for("20261105T225409-rdp-xmas02-x2")
    assert rect == (0, 585, 600, 720) and how == "auto:standard (chat_window.for_sid)"
    assert dv.chat_rect_for("20261026T095021-demo-human-demo-gef10")[0] == dv.HUNT_CHAT
    assert dv.chat_rect_for("20261105T115959-rdp-x")[0] == dv.HUNT_CHAT
    assert dv.chat_rect_for("20261026T095021-x", "standard")[0] == (0, 585, 600, 720)
    assert dv.chat_rect_for("20261105T225409-x", "0,615,600,709") == ((0, 615, 600, 709),
                                                                       "measured")  # fmt: skip
    for bad in ("0,615,600", "600,615,0,709", "big", "1,2,3,x"):
        with pytest.raises(SystemExit):
            dv.chat_rect_for("20261105T225409-x", bad)


def test_the_hunting_rows_with_the_standard_chat_window_and_no_double_count() -> None:
    """The standard chat window holds notice_left whole: covered_fraction would count it twice,
    so it is dropped (the union is the same); the legacy window holds nothing."""
    rects = dv.session_rects("hunt", (0, 585, 600, 720))
    assert rects[4] == (0, 585, 600, 720) and rects[0] == (0, 0, 220, 143)
    kept, dropped = dv.nested_rects(rects)
    assert dropped == [[0, 668, 50, 720]] and len(kept) == 6
    assert dv.nested_rects(dv.session_rects("hunt", dv.HUNT_CHAT))[1] == []
    assert dv.nested_rects([(0, 0, 10, 10), (0, 0, 10, 10)]) == (((0, 0, 10, 10),),
                                                                  [[0, 0, 10, 10]])  # fmt: skip
    # a box in the corner: half of it under the chat window -> behind the UI (left out)
    box = (20, 690, 60, 750)  # 40 x 60; 30 rows on screen under the window, 30 below the frame
    assert dv.behind_ui(box, kept) and dv.behind_ui(box, rects)
    assert not dv.behind_ui((20, 560, 60, 600), kept)  # 15 of 40 rows under it
    assert dv.behind_ui((20, 560, 60, 600, 0.9, "monster"), kept, half=0.3)


def test_a_session_is_the_x2_recording_path_or_refused() -> None:
    ok = {"session_id": "s", "backend": "rdp", "format": "png", "recorder_version": 6,
          "game_region": [80, 77, 1280, 720], "server": "lab-rathena"}  # fmt: skip
    dv.check_session(ok)
    dv.check_session({**ok, "recorder_version": 5})
    for bad in ({"recorder_version": 4}, {"format": "h264"}, {"backend": "console"},
                {"game_region": [0, 0, 1920, 1080]}):  # fmt: skip
        with pytest.raises(SystemExit):
            dv.check_session({**ok, **bad})


def test_box_rows_join_the_sessions_frames_by_capture_time() -> None:
    frames = [(0, 100), (1, 200), (2, 300)]
    rows = [{"t": 300, "frame_id": 2, "boxes": []}, {"t": 100, "boxes": []}]
    with pytest.raises(SystemExit):  # frame 1 has no row
        dv.session_captures(frames, rows)
    caps, cov = dv.session_captures(frames, rows, allow_partial=True)
    assert [c["t"] for c in caps] == [100, 300]
    assert cov == {"frames_in_session": 3, "frames_with_boxes": 2, "frames_without_boxes": 1}
    for bad in ([{"t": 150, "boxes": []}],  # no such frame: another session's rows
                [{"t": 200, "frame_id": 7, "boxes": []}],  # the frame id disagrees
                [{"t": 100, "boxes": []}, {"t": 100, "boxes": []}]):  # fmt: skip
        with pytest.raises(SystemExit):
            dv.session_captures(frames, bad, allow_partial=True)
    with pytest.raises(SystemExit):
        dv.session_captures([(0, 100), (1, 100)], [])


def test_hallucination_spans_from_our_status_changes() -> None:
    """EFST_ILLUSION (34) on -> off; a timed "on" ends by its remaining time at the latest; an
    "on" never switched off runs on; other statuses and units are kept apart."""
    ms = 1_000_000

    def ev(t: int, gid: int, on: bool, efst: int = 34, remain: int | None = None
           ) -> dict[str, Any]:  # fmt: skip
        return {"type": "status_change", "t_mono_ns": t, "gid": gid, "efst": efst, "on": on,
                "remain_ms": remain}  # fmt: skip

    events = [ev(1000 * ms, 7, True), ev(5000 * ms, 7, False),
              ev(8000 * ms, 7, True, remain=2000),  # never switched off: 2 s
              ev(9000 * ms, 9, True), ev(9500 * ms, 7, False, efst=58),
              {"type": "act", "t_mono_ns": 1}]  # fmt: skip
    spans = dv.hallucination_spans(events)
    assert spans[7] == [(1000 * ms, 5000 * ms), (8000 * ms, 10000 * ms)]
    assert spans[9] == [(9000 * ms, 2**63)]
    assert dv.in_spans(spans[7], 4999 * ms) and not dv.in_spans(spans[7], 5000 * ms)
    assert dv.in_spans(spans[7], 9999 * ms) and not dv.in_spans(spans[7], 10_000 * ms)
    assert dv.hallucination_spans([ev(1, 7, False)]) == {}


def test_the_4a_bar_exact_at_its_edges() -> None:
    sp = {"1249 Myst Case": 30, "1248 Cruiser": 30, "1265 Cookie": 29, "1246 Christmas Cookie": 0}
    species = dv.SPECIES_BY_MAP["xmas_dun02"]

    def per(hits: dict[str, int]) -> dict[str, Any]:
        return {k: {"n": n, "hit": hits.get(k, 0)} for k, n in sp.items()}

    good = per({"1249 Myst Case": 24, "1248 Cruiser": 30, "1265 Cookie": 0})  # 24 / 30 = 0.80
    bar = dv.bar_4a(good, species, tp=80, n_det=100)
    assert bar["verdict"] == "PASS" and bar["failed"] == []
    assert bar["species"]["1265 Cookie"] == {"n": 29, "hit": 0, "recall": 0.0, "in_bar": False,
                                             "pass": None}  # fmt: skip
    low = per({"1249 Myst Case": 23, "1248 Cruiser": 30})  # 23 / 30 = 0.767
    assert dv.bar_4a(low, species, 80, 100)["failed"] == ["1249 Myst Case"]
    bar = dv.bar_4a(good, species, tp=79, n_det=100)
    assert bar["verdict"] == "FAIL" and bar["failed"] == ["precision"]
    assert dv.bar_4a(good, species, 0, 0)["verdict"] == "FAIL"
    none = {k: {"n": 29, "hit": 29} for k in sp}
    assert dv.bar_4a(none, species, 100, 100)["verdict"] == "NO_BAR"


def test_score_session_reads_a_recorder_session(tmp_path: Path, monkeypatch: Any) -> None:
    """The session path's plumbing on a SYNTHETIC recorder session (ShardWriter; the projection
    stubbed: it needs the client's GAT and sprites, /dev/shm only): every frame, in time order,
    its rows from recorder_boxes; the frame size from the manifest; the hunting rows with the
    chat window of the session's date, notice_left dropped; UI boxes left out; the sprites
    required; Amendment A's bar from the body. A foreign sidecar is refused."""
    import gzip
    import json

    import numpy as np

    from poring_dataset.shards import ShardWriter, write_manifest

    session = tmp_path / "20261105T225409-rdp-xmas02-test"
    w = ShardWriter(session)
    ts = [10_000 + 1000 * i for i in range(4)]
    for i, t in enumerate(ts):
        w.add(i, t, np.zeros((2, 2, 3), np.uint8))
    w.close()
    write_manifest(session, {"session_id": session.name, "backend": "rdp", "format": "png",
                             "recorder_version": 6, "game_region": [80, 77, 1280, 720],
                             "server": "lab-rathena", "shards": w.shards, "frames": 4,
                             "t0_mono_ns": ts[0], "t1_mono_ns": ts[-1]})  # fmt: skip
    with gzip.open(session / "packets.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"type": "map_change", "t_mono_ns": 1}) + "\n")
    boxes = tmp_path / "boxes.jsonl"
    boxes.write_text("".join(json.dumps({"t": t, "frame_id": i, "ms": 1.0, "boxes": []}) + "\n"
                             for i, t in reversed(list(enumerate(ts)))))  # fmt: skip
    seen: dict[str, Any] = {}

    def fake(caps: Any, events: Any, size: Any, cfg: Any) -> dict[str, Any]:
        seen.update(caps=caps, events=events, size=size, cfg=cfg)
        per = {"1249 Myst Case": {"n": 40, "hit": 36}}
        return {"body": {"per_species": per}, "extra": {"hallucination": {}},
                "skipped": dv.Counter({"off_map": 1}), "pairs": [], "n_det": 10, "tp": 9,
                "species": dv.SPECIES_BY_MAP["xmas_dun02"]}  # fmt: skip

    monkeypatch.setattr(dv, "score_captures", fake)
    monkeypatch.setattr(dv, "projection_inputs", lambda *a: {"gat": "checked"})
    out = tmp_path / "score.json"
    argv = ["score-session", str(session), "--boxes", str(boxes), "--map", "xmas_dun02",
            "--sprites", str(tmp_path), "--sprite-names", str(tmp_path / "n.json"),
            "--out", str(out)]  # fmt: skip
    assert dv.main(argv) == 0
    doc = json.loads(out.read_text())
    assert [c["t"] for c in seen["caps"]] == ts and seen["size"] == (1280, 720)
    cfg = seen["cfg"]
    assert cfg.map_name == "xmas_dun02" and cfg.ui_boxes == "drop" and cfg.require_sheets
    assert (0, 585, 600, 720) in cfg.rects and (0, 668, 50, 720) not in cfg.rects
    assert doc["chat"] == {"rect": [0, 585, 600, 720],
                           "chosen": "auto:standard (chat_window.for_sid)"}  # fmt: skip
    assert doc["window"]["frames_with_boxes"] == 4 and doc["window"]["captures_scored"] == 3
    assert doc["bar_4a"]["species"]["1249 Myst Case"]["pass"] is True
    assert doc["bar_4a"]["verdict"] == "PASS"  # one species in the bar, 36 / 40; 9 / 10
    assert doc["projection_inputs"] == {"gat": "checked"}
    pre = tmp_path / "pre.json"
    pre_argv = [*argv[:-1], str(pre), "--preflight"]
    seen.clear()
    assert dv.main(pre_argv) == 0 and seen == {}  # nothing scored
    pdoc = json.loads(pre.read_text())
    assert pdoc["preflight"] == "ok" and pdoc["frames_indexed"] == 4
    assert pdoc["coverage"]["frames_with_boxes"] == 4 and pdoc["nested_ui_rects_dropped"] == [
        [0, 668, 50, 720]]  # fmt: skip
    (tmp_path / "boxes.jsonl.meta.json").write_text(json.dumps({"session_id": "another"}))
    with pytest.raises(SystemExit):
        dv.main(argv)


def test_the_projection_refuses_a_map_without_its_gat(tmp_path: Path, monkeypatch: Any) -> None:
    """load_scene falls back to FLAT ground when the GAT is missing (a host reboot wipes
    /dev/shm): the session path refuses instead."""
    import poring_dataset.camera as camera

    monkeypatch.setattr(camera, "GAT_DIR", tmp_path)
    with pytest.raises(SystemExit, match="GAT is not extracted"):
        dv.projection_inputs("xmas_dun02", tmp_path, tmp_path, tmp_path / "n.json", tmp_path)


# --- T-6: a map-scoped model's species collapsed to monster (xmas02-detector.md 7) --------------


def _session_with_boxes(tmp_path: Path, rows_cls: list[str], names: list[str] | None) -> Any:
    """A synthetic recorder session (4 frames) and boxes rows whose one box per frame has the
    class ``rows_cls[i]``; ``names``: the predictor's meta (None: no meta)."""
    import gzip
    import json

    import numpy as np

    from poring_dataset.shards import ShardWriter, write_manifest

    session = tmp_path / "20261106T120000-rdp-xmas02-xw9"
    w = ShardWriter(session)
    ts = [10_000 + 1000 * i for i in range(4)]
    for i, t in enumerate(ts):
        w.add(i, t, np.zeros((2, 2, 3), np.uint8))
    w.close()
    write_manifest(session, {"session_id": session.name, "backend": "rdp", "format": "png",
                             "recorder_version": 6, "game_region": [80, 77, 1280, 720],
                             "server": "lab-rathena", "shards": w.shards, "frames": 4})  # fmt: skip
    with gzip.open(session / "packets.jsonl.gz", "wt") as fh:
        fh.write(json.dumps({"type": "map_change", "t_mono_ns": 1}) + "\n")
    boxes = tmp_path / f"boxes-{len(list(tmp_path.iterdir()))}.jsonl"
    boxes.write_text("".join(json.dumps({"t": t, "frame_id": i, "ms": 1.0,
                                         "boxes": [[10, 10, 50, 80, 0.9, rows_cls[i]],
                                                   [60, 10, 90, 80, 0.8, "player"]]}) + "\n"
                             for i, t in enumerate(ts)))  # fmt: skip
    if names is not None:
        boxes.with_name(boxes.name + ".meta.json").write_text(json.dumps(
            {"session_id": session.name, "names": names}))  # fmt: skip
    return session, boxes


def test_score_session_collapses_a_map_models_species_and_v1_is_unchanged(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The species rows with --classes reach the scorer EXACTLY as v1's ``monster`` rows do (so
    they score identically); v1's rows without the flag reach it as written and the output has
    no class_collapse key; the names come from the boxes' meta or --names; v1's names against
    the species list are refused."""
    import json

    seen: list[Any] = []

    def fake(caps: Any, events: Any, size: Any, cfg: Any) -> dict[str, Any]:
        seen.append(caps)
        return {"body": {"per_species": {}}, "extra": {}, "skipped": dv.Counter(), "pairs": [],
                "n_det": 0, "tp": 0, "species": dv.SPECIES_BY_MAP["xmas_dun02"]}  # fmt: skip

    monkeypatch.setattr(dv, "score_captures", fake)
    monkeypatch.setattr(dv, "projection_inputs", lambda *a: {"gat": "checked"})
    classes = tmp_path / "classes-xmas02.json"
    classes.write_text(json.dumps({"fixed": {"player": 0}, "monster_first_id": 1,
                                   "monsters": [1249, 1248, 1265, 1246]}))  # fmt: skip
    names = ["player", "mystcase", "cruiser", "cookie", "cookie_xmas"]
    v1_session, v1_boxes = _session_with_boxes(tmp_path / "v1", ["monster"] * 4, None)
    sp_session, sp_boxes = _session_with_boxes(
        tmp_path / "sp", ["mystcase", "cruiser", "cookie", "cookie_xmas"], names
    )

    def run(session: Path, boxes: Path, *extra: str) -> dict[str, Any]:
        out = tmp_path / "score.json"
        argv = ["score-session", str(session), "--boxes", str(boxes), "--map", "xmas_dun02",
                "--sprites", str(tmp_path), "--sprite-names", str(tmp_path / "n.json"),
                "--out", str(out), *extra]  # fmt: skip
        assert dv.main(argv) == 0
        return dict(json.loads(out.read_text()))

    v1 = run(v1_session, v1_boxes)
    assert "class_collapse" not in v1
    sp = run(sp_session, sp_boxes, "--classes", str(classes))
    assert seen[0] == seen[1]  # the scorer gets the same rows: the same score
    col = sp.pop("class_collapse")
    assert col["names_from"] == "the boxes' .meta.json" and col["to_monster"] == sorted(names[1:])
    assert col["boxes_by_class_after"] == {"monster": 4, "player": 4}
    assert col["boxes_by_class_before"]["cookie_xmas"] == 1
    for k in ("boxes", "boxes_meta", "session"):
        sp.pop(k), v1.pop(k)
    assert sp == v1  # nothing else differs
    side = tmp_path / "model.names.json"
    side.write_text(json.dumps(names))
    sp_session2, sp_boxes2 = _session_with_boxes(tmp_path / "sp2", ["cookie"] * 4, None)
    with pytest.raises(SystemExit, match="names"):  # no meta, no --names
        run(sp_session2, sp_boxes2, "--classes", str(classes))
    assert run(sp_session2, sp_boxes2, "--classes", str(classes), "--names",
               str(side))["class_collapse"]["names_from"] == str(side)  # fmt: skip
    v1_names = tmp_path / "v1.names.json"
    v1_names.write_text(json.dumps(["player", "monster", "npc"]))
    with pytest.raises(SystemExit):  # v1's names are not this list's model
        run(v1_session, v1_boxes, "--classes", str(classes), "--names", str(v1_names))
    with pytest.raises(SystemExit):  # --names alone
        run(v1_session, v1_boxes, "--names", str(v1_names))
    pre = run(sp_session, sp_boxes, "--classes", str(classes), "--preflight")
    assert pre["preflight"] == "ok" and pre["class_collapse"]["to_monster"] == sorted(names[1:])


GEF10R2 = Path("/mnt/poring-lab-datasets/archive/train/eval/gef10-r2")
GEF10R2_NAMES = Path("/dev/shm/poring-lab-detector/model/gef10r2-last-736x1280.names.json")


def test_real_gef10_round2_species_rows_collapse_to_the_published_rows() -> None:
    """A REAL species-named model output (no map-scoped recorder_boxes output exists yet, and X2's
    rows are TEST): gef10 round 2's 26-class predict_dir run on Batt's demo (gef10-eval.md, its
    names sidecar d263f379..., the committed class list classes-v2orc-payf07-gef10.json). Its rows
    WITH the model's names, collapsed through the class list, are exactly the published
    demo-boxes-gef10r2.jsonl that from-predict wrote (the rows behind recall 0.397 / precision
    0.577): the list-based collapse and from-predict's agree on every box."""
    if not (GEF10R2 / "demo-pred-gef10r2.json").exists() or not GEF10R2_NAMES.exists():
        pytest.skip("the gef10 round-2 predictions or the model's names are not here")
    import hashlib
    import json

    import recorder_boxes as rb

    assert hashlib.sha256(GEF10R2_NAMES.read_bytes()).hexdigest().startswith("d263f379")
    pred = json.loads((GEF10R2 / "demo-pred-gef10r2.json").read_text())
    per = ((pred.get("timing_ms") or {}).get("per_frame")) or {}
    named = sorted(({"t": int(stem.partition("-")[2]), "ms": per.get(stem),
                     "boxes": [[float(d["x1"]), float(d["y1"]), float(d["x2"]), float(d["y2"]),
                                float(d["conf"]), d["cls"]] for d in dets]}
                    for stem, dets in pred["frames"].items()), key=lambda r: r["t"])  # fmt: skip
    classes = json.loads((ROOT / "config/detector/classes-v2orc-payf07-gef10.json").read_text())
    mapping = rb.class_collapse(classes, json.loads(GEF10R2_NAMES.read_text()))
    got = rb.collapse_rows(named, mapping)
    published = dv.read_boxes(GEF10R2 / "demo-boxes-gef10r2.jsonl")
    assert len(got) == len(published) == len(pred["frames"]) > 4000
    assert got == published == dv.predict_rows(pred)
    species = rb.class_counts(named)
    assert sum(v for k, v in species.items() if k not in ("player", "npc", "warp")) == \
        rb.class_counts(got)["monster"]  # fmt: skip
