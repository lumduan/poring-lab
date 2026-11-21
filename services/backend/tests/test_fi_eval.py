"""T-O5 (scripts/fi_eval.py; docs/planning/xmas02-detector.md Amendment O.9, ACCEPTED by O1
2026-11-10): the bars I1-I5 from --eval-test label files, predictions and the evaluated crops.
The positive case: a STAGED frame list with a known count per bar (synthetic boxes only), and each
bar's minimum count turning it into NO VERDICT, never a pass."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import fi_eval as fe  # noqa: E402

SID = "20261111T090000-rdp-hunt-xmas02-fiT4"
ANCHOR = (-4.0, 2.0)
S = 1_000_000_000
AROUND = [550.0, 300.0, 730.0, 450.0]  # the 5 x 5 around her (pixels)


def det(b: list[float], conf: float = 0.9, cls: str = "floor_item") -> dict[str, Any]:
    return {"cls": cls, "x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3], "conf": conf}


def box_at(cx: float, cy: float) -> list[float]:
    return [cx - 5.5, cy - 6.0, cx + 5.5, cy + 6.0]


class Staged:
    """A staged fiT label file and its predictions, built frame by frame."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.kills: list[dict[str, Any]] = []
        self.pred: dict[str, list[dict[str, Any]]] = {}
        self.crops: list[dict[str, Any]] = []

    def frame(self, status: str = "keep", items: list[dict[str, Any]] | None = None,
              floor: list[dict[str, Any]] | None = None, dets: list[dict[str, Any]] | None = None,
              n_near: int | None = None) -> int:  # fmt: skip
        fid = len(self.frames) + 1
        floor = floor or []
        self.frames.append({"frame_id": fid, "t": fid * S, "status": status, "reasons": [],
                            "items": items or [], "floor": floor, "around_box": AROUND,
                            "n_near": len(floor) if n_near is None else n_near})  # fmt: skip
        self.pred[fe.frame_key(SID, fid)] = dets or []
        return fid

    def item_frame(self, floor_id: int, cx: float, cy: float, boxed: bool,
                   status: str = "keep") -> tuple[int, list[float]]:  # fmt: skip
        b = box_at(cx, cy)
        near = [cx - 4 - 50, cy + 2 - 40, cx - 4 + 50, cy + 2 + 40]
        fid = self.frame(status, [{"floor_id": floor_id, "item_id": 911, "box": b}],
                         [{"floor_id": floor_id, "item_id": 911, "phase": "on", "pred_box": b,
                           "near_box": near}],
                         [det([x + 1 for x in b])] if boxed else [])  # fmt: skip
        return fid, b

    def doc(self) -> dict[str, Any]:
        return {
            "session": SID,
            "eval_test": True,
            "params_sha256": "p",
            "model": {"sha256": "m"},
            "frames": self.frames,
            "kills": self.kills,
        }


def staged() -> Staged:
    """The staged list (known counts):
    - I1: 40 evaluated crops on 40 item frames, 36 boxed -> recall 36 / 40 = 0.90 PASS;
    - I1 precision: those 36 TRUE boxes, + 2 FALSE (far from every item, on item frames 1-2) and
      the 2 boxes of the item-free frames below (FALSE: no item within 1 cell), + 1 AMBIGUOUS
      (beside item 3, not on it); one box below conf 0.25 and one of another class do not count
      -> 36 / 40 = 0.90 PASS;
    - I2: 25 drops of our kills, each first kept in one of the item frames 1-25 (22 boxed: the
      unboxed crops are 23-26) -> 22 / 25 = 0.88 PASS; a 26th drop with no kept frame ignored;
      one more drop on (0,+1), never labelled;
    - I3: 600 item-free kept frames, 2 with a box (one inside the 5 x 5) -> 2 / 600 = 0.0033 <=
      0.005 PASS and 1 / 600 = 0.0017 <= 0.002 PASS;
    - I4: 50 kills without a drop, 2 with a box in the death cell's 3 x 3 -> 0.04 <= 0.05 PASS.
    """
    st = Staged()
    for i in range(40):
        boxed = not 22 <= i < 26
        fid, b = st.item_frame(1000 + i, 100.0 + 25 * i % 1000, 200.0 + 3 * i, boxed)
        st.crops.append({"crop": f"{i:03d}", "session": SID, "frame_id": fid,
                         "floor_id": 1000 + i, "box": b})  # fmt: skip
    st.pred[fe.frame_key(SID, 1)].append(det(box_at(1200.0, 650.0)))  # FALSE
    st.pred[fe.frame_key(SID, 2)].append(det(box_at(1100.0, 80.0)))  # FALSE
    f3 = st.frames[2]["floor"][0]
    beside = box_at(f3["near_box"][0] + 20, f3["near_box"][1] + 20)  # inside 1 cell, not on it
    st.pred[fe.frame_key(SID, 3)].append(det(beside))
    st.pred[fe.frame_key(SID, 4)].append(det(box_at(1200.0, 650.0), conf=0.2))  # below 0.25
    st.pred[fe.frame_key(SID, 5)].append(det(box_at(1200.0, 650.0), cls="cruiser"))  # not ours
    for i in range(25):
        st.kills.append({"t": i * S, "drops": [1000 + i], "rel": [1, 0], "i4": None})
    st.kills.append({"t": 99 * S, "drops": [5555], "rel": [1, 0], "i4": None})  # never labelled
    st.kills.append({"t": 98 * S, "drops": [6666], "rel": [0.0, 1.0], "i4": None})  # behind her
    for i in range(600):
        dets = []
        if i == 0:
            dets = [det(box_at(640.0 + ANCHOR[0], 380.0 + ANCHOR[1]))]  # in the 5 x 5
        elif i == 1:
            dets = [det(box_at(100.0, 100.0))]  # elsewhere
        st.frame("keep", [], [], dets)
    for i in range(50):
        fid = st.frame("exclude", [], [], [], n_near=None)  # an I4 frame (not judged)
        st.frames[-1]["n_near"] = None
        box3 = [600.0, 340.0, 700.0, 420.0]
        if i < 2:
            st.pred[fe.frame_key(SID, fid)] = [det(box_at(650.0 + ANCHOR[0], 380.0 + ANCHOR[1]))]
        st.kills.append({"t": (200 + i) * S, "drops": [], "rel": [1, 0],
                         "i4": {"frame_id": fid, "box3": box3}})  # fmt: skip
    return st


def lat_ok() -> dict[str, Any]:
    return {"gpu_ms": [20.0] * 190 + [30.0] * 10, "cpu": {"fi": {"n": 200, "p95": 180.0},
                                                         "gb": {"n": 200, "p95": 170.0}},
            "cpu_item": "fi", "cpu_deployed": "gb"}  # fmt: skip


def test_the_staged_list_gives_its_known_counts() -> None:
    st = staged()
    res = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, lat_ok())
    r = res["per_predictions"]["gpu"]
    assert (r["i1_recall"]["num"], r["i1_recall"]["den"], r["i1_recall"]["verdict"]) == (
        36,
        40,
        "PASS",
    )
    p = r["i1_precision"]
    assert (p["true"], p["false"], p["ambiguous"], p["verdict"]) == (36, 4, 1, "PASS")
    assert (r["i2"]["num"], r["i2"]["den"], r["i2"]["verdict"]) == (22, 25, "PASS")
    assert r["i2"]["drops_behind_her"] == 1 and r["i2"]["behind_with_a_kept_label"] == 0
    assert r["i3"]["frames"] == 600
    assert (r["i3"]["any"]["num"], r["i3"]["any"]["verdict"]) == (2, "PASS")
    assert (r["i3"]["around_5x5"]["num"], r["i3"]["around_5x5"]["verdict"]) == (1, "PASS")
    assert (r["i4"]["num"], r["i4"]["den"], r["i4"]["verdict"]) == (2, 50, "PASS")
    assert res["i5"]["gpu"]["p95_ms"] == 20.0 and res["i5"]["gpu"]["verdict"] == "PASS"
    cpu = res["i5"]["cpu"]
    assert cpu["ratio"] == round(180 / 170, 4) and cpu["verdict"] == "PASS"
    assert res["verdict"] == "PASS"


def test_each_bar_fails_on_its_own_count() -> None:
    st = staged()
    for fid in (7, 8, 9):  # recall 33 / 40 = 0.825 < 0.85
        st.pred[fe.frame_key(SID, fid)] = []
    r = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, lat_ok())
    g = r["per_predictions"]["gpu"]
    assert g["i1_recall"]["verdict"] == "FAIL" and g["i1_recall"]["num"] == 33
    assert g["i2"]["num"] == 19 and g["i2"]["verdict"] == "FAIL"  # 19 / 25 = 0.76 < 0.80
    assert r["verdict"] == "FAIL"
    st = staged()
    st.pred[fe.frame_key(SID, 50)] = [det(box_at(640.0 + ANCHOR[0], 380.0 + ANCHOR[1]))]
    g = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR,
                    lat_ok())["per_predictions"]["gpu"]  # fmt: skip
    assert g["i3"]["any"]["num"] == 3 and g["i3"]["any"]["verdict"] == "PASS"  # 3/600 = 0.005
    assert g["i3"]["around_5x5"]["num"] == 2 and g["i3"]["around_5x5"]["verdict"] == "FAIL"
    st = staged()
    i4 = [k for k in st.kills if k["i4"]][2]
    st.pred[fe.frame_key(SID, i4["i4"]["frame_id"])] = [det(box_at(646.0, 382.0))]
    g = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR,
                    lat_ok())["per_predictions"]["gpu"]  # fmt: skip
    assert g["i4"]["num"] == 3 and g["i4"]["verdict"] == "FAIL"  # 3 / 50 = 0.06 > 0.05
    lat = lat_ok()
    lat["cpu"]["fi"]["p95"] = 190.0  # 190 / 170 = 1.118 > 1.10
    assert fe.i5(lat["gpu_ms"], lat["cpu"], "fi", "gb")["cpu"]["verdict"] == "FAIL"
    assert fe.i5([40.0] * 200, None, None, None)["gpu"]["verdict"] == "FAIL"


def test_short_counts_are_no_verdict_never_a_pass() -> None:
    st = staged()
    crops = st.crops[:39]
    st.kills = [k for k in st.kills if not k["drops"]][:39]
    st.frames = st.frames[: 40 + 300]  # the 40 item frames + 300 item-free ones
    st.pred[fe.frame_key(SID, 42)] = []  # one box left on them (inside the 5 x 5)
    res = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}}, crops, ANCHOR, lat_ok())
    g = res["per_predictions"]["gpu"]
    assert g["i1_recall"]["verdict"] == "NO_VERDICT" and g["i1_recall"]["den"] == 39
    assert g["i2"]["verdict"] == "NO_VERDICT" and g["i2"]["den"] == 0
    assert g["i3"]["any"]["verdict"] == "PASS" and g["i3"]["frames"] == 300  # 1 / 300
    assert g["i3"]["around_5x5"]["verdict"] == "NO_VERDICT"  # 300 < 500
    assert g["i4"]["verdict"] == "NO_VERDICT" and g["i4"]["den"] == 39
    assert res["verdict"] == "NO_VERDICT"
    assert fe.i5([20.0] * 199, None, None, None)["gpu"]["verdict"] == "NO_VERDICT"
    assert fe.i5(None, None, None, None)["cpu"]["verdict"] == "NO_VERDICT"


def test_every_prediction_set_must_pass_and_a_missing_frame_refuses() -> None:
    st = staged()
    worse = {k: list(v) for k, v in st.pred.items()}
    for fid in range(1, 10):
        worse[fe.frame_key(SID, fid)] = []
    res = fe.evaluate([st.doc()], {"gpu": {"frames": st.pred}, "onnx": {"frames": worse}},
                      st.crops, ANCHOR, lat_ok())  # fmt: skip
    assert res["per_predictions"]["gpu"]["i1_recall"]["verdict"] == "PASS"
    assert res["per_predictions"]["onnx"]["i1_recall"]["verdict"] == "FAIL"
    assert res["verdict"] == "FAIL"
    del worse[fe.frame_key(SID, 600)]
    with pytest.raises(SystemExit, match="no prediction"):
        fe.evaluate([st.doc()], {"onnx": {"frames": worse}}, st.crops, ANCHOR, lat_ok())


def test_matching_and_cell_point() -> None:
    a = [100.0, 100.0, 111.0, 112.0]
    assert fe.matches([101.0, 101.0, 112.0, 113.0], a)  # IoU high
    assert fe.matches([90.0, 90.0, 120.0, 125.0], a)  # its centre lies in a
    assert not fe.matches([112.0, 100.0, 123.0, 112.0], a)
    assert fe.cell_point([100.0, 100.0, 110.0, 110.0], ANCHOR) == (109.0, 103.0)
    assert fe.boxes_of([det(a), det(a, 0.24), det(a, cls="cruiser")]) == [a]
    assert fe.nearest_rank([1.0, 2.0, 3.0, 4.0], 95) == 4.0


def test_main_reads_the_files(tmp_path: Path) -> None:
    st = staged()
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"anchor_px": list(ANCHOR)}))
    doc = {**st.doc(), "params": str(params)}
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps(doc))
    pred = tmp_path / "pred.json"
    pred.write_text(json.dumps({"frames": st.pred, "timing_ms": {
        "per_frame": {str(i): 20.0 for i in range(200)}}}))  # fmt: skip
    key = {"eval_test": True, "crops": {c["crop"]: {"truth": "item", **c} for c in st.crops}}
    kp = tmp_path / "key.json"
    kp.write_text(json.dumps(key))
    both = tmp_path / "both.json"
    both.write_text(json.dumps([c["crop"] for c in st.crops]))
    lat = tmp_path / "lat.json"
    lat.write_text(json.dumps(lat_ok()["cpu"]))
    out = tmp_path / "out.json"
    assert fe.main(["--labels", str(lab), "--predictions", f"gpu={pred}", "--key", str(kp),
                    "--evaluated", str(both), "--gpu-timing", str(pred), "--cpu-latency",
                    str(lat), "--cpu-item", "fi", "--cpu-deployed", "gb", "--out",
                    str(out)]) == 0  # fmt: skip
    assert json.loads(out.read_text())["verdict"] == "PASS"
    kp.write_text(json.dumps({**key, "eval_test": False}))
    with pytest.raises(SystemExit, match="evaluation's pack"):
        fe.main(["--labels", str(lab), "--predictions", f"gpu={pred}", "--key", str(kp),
                 "--evaluated", str(both), "--out", str(out)])  # fmt: skip
    lab.write_text(json.dumps({**doc, "eval_test": False}))
    with pytest.raises(SystemExit, match="eval-test"):
        fe.main(["--labels", str(lab), "--predictions", f"gpu={pred}", "--key", str(kp),
                 "--evaluated", str(both), "--out", str(out)])  # fmt: skip


def test_cpu_latency_reads_eval_latencys_own_output() -> None:
    # O14: eval_latency.py nests the per-model summaries under "ms"; fi_eval read only the bare map
    summ = {"fi": {"n": 300, "p95": 757.3}, "gb": {"n": 300, "p95": 726.1}}
    assert fe.cpu_latency_models({"what": "x", "frames": 300, "ms": summ}) == summ
    assert fe.cpu_latency_models(summ) == summ
    out = fe.i5(None, fe.cpu_latency_models({"ms": summ}), "fi", "gb")["cpu"]
    assert out["ratio"] == round(757.3 / 726.1, 4)


def _crop(sid: str, fid: int, box: list[float]) -> dict[str, Any]:
    return {"session": sid, "frame_id": fid, "floor_id": fid, "box": box}


def test_o15_i1_strata_split_aura_and_no_aura() -> None:
    """O15: I1a (aura: fiT4-6 + fsTa, >= 40) and I1n (no aura: fsTn, >= 30), each >= 0.85, with
    the sources counted and Batt's 95 % beside them; a crop of neither stratum refuses."""
    box = [10.0, 10.0, 30.0, 30.0]
    a1, a2 = "20261111T020000-rdp-hunt-xmas02-fiT4", "20261110T233000-rdp-xmas02-fsTa"
    n1 = "20261110T230000-rdp-xmas02-fsTn"
    crops = ([_crop(a1, i, box) for i in range(20)] + [_crop(a2, 100 + i, box) for i in range(20)]
             + [_crop(n1, 200 + i, box) for i in range(30)])  # fmt: skip
    pred = {fe.frame_key(c["session"], c["frame_id"]): [box] for c in crops}
    for c in crops[:2] + crops[40:45]:  # 2 aura misses (38 / 40), 5 no-aura misses (25 / 30)
        pred[fe.frame_key(c["session"], c["frame_id"])] = []
    got = fe.i1_strata(crops, pred)
    assert got["aura"]["num"] == 38 and got["aura"]["verdict"] == "PASS"
    assert got["aura"]["target_095"] is True
    assert got["aura"]["by_source"] == {"fiT4": {"hit": 18, "n": 20}, "fsTa": {"hit": 20, "n": 20}}
    assert got["no_aura"]["num"] == 25 and got["no_aura"]["verdict"] == "FAIL"
    assert got["no_aura"]["min_rows"] == 30
    short = fe.i1_strata(crops[:40] + crops[40:60], pred)  # 20 no-aura crops: under 30
    assert short["no_aura"]["verdict"] == "NO_VERDICT"
    with pytest.raises(SystemExit, match="no stratum"):
        fe.i1_strata([_crop("20261110T105312-rdp-hunt-xmas02-fiT1", 1, box)], pred)


def test_o15_i5_gpu_is_the_server_forward_time_against_the_deployed() -> None:
    fi, gb = {"n": 300, "p95": 16.51}, {"n": 300, "p95": 16.85}  # O14's own numbers
    got = fe.i5_server(fi, gb)
    assert got["verdict"] == "PASS" and got["ratio"] == round(16.51 / 16.85, 4)
    assert fe.i5_server({"n": 300, "p95": 19.0}, gb)["verdict"] == "FAIL"  # 1.13 x
    assert fe.i5_server({"n": 300, "p95": 36.0}, {"n": 300, "p95": 35.0})["verdict"] == "FAIL"
    assert fe.i5_server({"n": 150, "p95": 16.0}, gb)["verdict"] == "NO_VERDICT"
    assert fe.i5_server(None, gb)["verdict"] == "NO_VERDICT"


def test_o17_round3_strata_name_its_fresh_held_out() -> None:
    box = [10.0, 10.0, 30.0, 30.0]
    a7, n3 = "20261111T090000-rdp-hunt-xmas02-fiT7", "20261111T043000-rdp-xmas02-fsTn3"
    crops = [_crop(a7, i, box) for i in range(40)] + [_crop(n3, 100 + i, box) for i in range(30)]
    pred = {fe.frame_key(c["session"], c["frame_id"]): [box] for c in crops}
    got = fe.i1_strata(crops, pred, "r3")
    assert got["aura"]["num"] == 40 and got["no_aura"]["num"] == 30
    assert got["no_aura"]["by_source"] == {"fsTn3": {"hit": 30, "n": 30}}
    with pytest.raises(SystemExit, match="no stratum"):  # round 2's names are not round 3's
        fe.i1_strata([_crop("20261110T221931-rdp-xmas02-fsTn", 1, box)], pred, "r3")


def test_o22_round5_has_one_aura_off_stratum_with_its_sources() -> None:
    """O22 (round 5, the aura OFF): ONE pooled stratum "aura_off" (the fresh pilots fiH1 / fiH2 and
    the staging fsH1, >= 40 crops, >= 0.85), its sources counted apart; no no-aura stratum (the
    whole held-out is aura-off); a crop of another round refuses."""
    box = [10.0, 10.0, 30.0, 30.0]
    h1, s1 = "20261112T010000-rdp-hunt-xmas02-fiH1", "20261112T013000-rdp-xmas02-fsH1"
    crops = [_crop(h1, i, box) for i in range(25)] + [_crop(s1, 100 + i, box) for i in range(20)]
    pred = {fe.frame_key(c["session"], c["frame_id"]): [box] for c in crops}
    for c in crops[:3]:
        pred[fe.frame_key(c["session"], c["frame_id"])] = []
    got = fe.i1_strata(crops, pred, "r5")
    assert set(got) == {"aura_off"}
    assert got["aura_off"]["num"] == 42 and got["aura_off"]["den"] == 45
    assert got["aura_off"]["verdict"] == "PASS" and got["aura_off"]["min_rows"] == 40
    assert got["aura_off"]["by_source"] == {"fiH1": {"hit": 22, "n": 25},
                                            "fsH1": {"hit": 20, "n": 20}}  # fmt: skip
    with pytest.raises(SystemExit, match="no stratum"):
        fe.i1_strata([_crop("20261111T153427-rdp-hunt-xmas02-fiT13", 1, box)], pred, "r5")


# --- round 6 (xmas02-items-1080.md 8a, the 1080 item round; T-I4) ---------------------------------

R6_H1, R6_H2 = "20261121T050000-rdp-xmas02-ifH1", "20261121T060000-rdp-xmas02-ifH2"
R6_S1 = "20261121T070000-rdp-xmas02-ifsH1"


def staged_as(sid: str) -> Staged:
    """The staged list, every frame, crop and prediction renamed to the session ``sid``."""
    st = staged()
    st.pred = {k.replace(SID, sid): v for k, v in st.pred.items()}
    st.crops = [{**c, "session": sid} for c in st.crops]
    return st


def r6_latency() -> dict[str, Any]:
    return {**lat_ok(), "gpu_server_item": {"n": 300, "p95": 17.0},
            "gpu_server_deployed": {"n": 300, "p95": 16.67}, "comparator": "xmas02fi5"}  # fmt: skip


def test_r6_names_and_its_own_bar_values() -> None:
    assert fe.R6_HELD_OUT == (
        "-xmas02-ifH1",
        "-xmas02-ifH2",
        "-xmas02-ifH3",
        "-xmas02-ifH4",
        "-xmas02-ifsH1",
        "-xmas02-ifsH2",
    )  # + Amendment 16
    assert fe.STRATA["r6"] == (fe.R6_HELD_OUT, (), fe.R6_PILOTS)
    b = fe.bars_of("r6")
    assert (b["i1_recall"], b["i1_precision"]) == (0.90, 0.95)
    assert {k: v for k, v in b.items() if k not in ("i1_recall", "i1_precision")} == {
        k: v for k, v in fe.BARS.items() if k not in ("i1_recall", "i1_precision")
    }
    for rnd in (None, "r2", "r3", "r4", "r5"):  # rounds 2-5 keep their bars
        assert fe.bars_of(rnd) is fe.BARS
    assert fe.BARS["i1_recall"] == 0.85 and fe.BARS["i1_precision"] == 0.85


def test_r6_i1h_is_the_pooled_held_out_at_0_90_with_natural_and_staging_apart() -> None:
    box = [10.0, 10.0, 30.0, 30.0]
    crops = ([_crop(R6_H1, i, box) for i in range(25)] + [_crop(R6_H2, 100 + i, box)
             for i in range(10)] + [_crop(R6_S1, 200 + i, box) for i in range(20)])  # fmt: skip
    pred = {fe.frame_key(c["session"], c["frame_id"]): [box] for c in crops}
    for c in crops[:2] + crops[35:38]:  # natural 33 / 35, staging 17 / 20: pooled 50 / 55
        pred[fe.frame_key(c["session"], c["frame_id"])] = []
    got = fe.i1_strata(crops, pred, "r6", fe.bars_of("r6"))
    assert set(got) == {"i1h"} and got["i1h"]["bar"] == 0.9
    assert (got["i1h"]["num"], got["i1h"]["den"], got["i1h"]["verdict"]) == (50, 55, "PASS")
    assert got["i1h"]["by_source"] == {"ifH1": {"hit": 23, "n": 25}, "ifH2": {"hit": 10, "n": 10},
                                       "ifsH1": {"hit": 17, "n": 20}}  # fmt: skip
    pred[fe.frame_key(R6_H2, 100)] = []  # 49 / 55 = 0.891: FAIL at 0.90 (a PASS at 0.85)
    assert fe.i1_strata(crops, pred, "r6", fe.bars_of("r6"))["i1h"]["verdict"] == "FAIL"
    assert fe.i1_strata(crops, pred, "r6")["i1h"]["verdict"] == "PASS"  # BARS' 0.85
    apart = fe.i1_apart(crops, pred, fe.STRATA_APART["r6"])
    assert (apart["natural"]["num"], apart["natural"]["den"]) == (32, 35)
    assert (apart["staging"]["num"], apart["staging"]["den"]) == (17, 20)
    assert apart["natural"]["target_095"] is False and "verdict" not in apart["natural"]
    with pytest.raises(SystemExit, match="no stratum"):  # round 5's held-out is not round 6's
        fe.i1_strata([_crop("20261112T093311-rdp-hunt-xmas02-fiH1", 1, box)], pred, "r6")
    short = fe.i1_strata(crops[:39], pred, "r6", fe.bars_of("r6"))
    assert short["i1h"]["verdict"] == "NO_VERDICT"  # under 40 evaluated crops


def test_r6_evaluate_uses_its_bars_and_the_comparator() -> None:
    """The staged list as ifH1 (natural drops: I2-I4 read it), its four FALSE boxes cleared and
    four more TRUE boxes (a second box on items 10-13): I1h 36 / 40 = 0.90 PASS, precision 40 / 40
    PASS (>= 40 boxes), I5 vs the comparator PASS -> PASS. One more miss: I1h 35 / 40 = 0.875
    FAILS at 0.90 (it passed round 5's 0.85); the four FALSE boxes back: precision 40 / 44 =
    0.909 FAILS at 0.95."""

    def more_true(st: Staged) -> Staged:
        for fid in (10, 11, 12, 13):
            k = fe.frame_key(R6_H1, fid)
            st.pred[k] = [*st.pred[k], st.pred[k][0]]
        return st

    st = more_true(staged_as(R6_H1))
    for fid in (1, 2):
        st.pred[fe.frame_key(R6_H1, fid)] = st.pred[fe.frame_key(R6_H1, fid)][:1]
    for fid in (41, 42):
        st.pred[fe.frame_key(R6_H1, fid)] = []
    doc = {**st.doc(), "session": R6_H1}
    res = fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, r6_latency(), "r6")
    g = res["per_predictions"]["gpu"]
    assert g["i1_strata"]["i1h"]["num"] == 36 and g["i1_strata"]["i1h"]["verdict"] == "PASS"
    assert (g["i1_precision"]["true"], g["i1_precision"]["false"]) == (40, 0)
    assert g["i1_precision"]["bar"] == 0.95 and g["i1_precision"]["verdict"] == "PASS"
    assert g["i1_apart"]["natural"]["den"] == 40 and g["i1_apart"]["staging"]["den"] == 0
    assert g["i2"]["den"] == 25 and g["i3"]["frames"] == 600 and g["i4"]["den"] == 50
    assert res["i5"]["gpu"]["verdict"] == "PASS" and res["i5"]["comparator"] == "xmas02fi5"
    assert res["i5"]["gpu"]["ratio"] == round(17.0 / 16.67, 4)
    assert res["verdict"] == "PASS"
    st.pred[fe.frame_key(R6_H1, 7)] = []
    res = fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, r6_latency(), "r6")
    assert res["per_predictions"]["gpu"]["i1_strata"]["i1h"]["verdict"] == "FAIL"
    assert res["verdict"] == "FAIL"
    st = more_true(staged_as(R6_H1))  # the four FALSE boxes kept: 40 / 44 = 0.909 < 0.95
    res = fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, r6_latency(), "r6")
    p = res["per_predictions"]["gpu"]["i1_precision"]
    assert (p["true"], p["false"], p["verdict"]) == (40, 4, "FAIL")
    assert (
        fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, r6_latency(), None)[
            "per_predictions"
        ]["gpu"]["i1_precision"]["verdict"]
        == "PASS"
    )  # 0.85
    lat = {**r6_latency(), "gpu_server_item": {"n": 300, "p95": 19.0}}  # 1.14 x the comparator
    assert fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, lat,
                       "r6")["i5"]["gpu"]["verdict"] == "FAIL"  # fmt: skip
    lat = {**r6_latency(), "gpu_server_item": {"n": 150, "p95": 16.0}}
    assert fe.evaluate([doc], {"gpu": {"frames": st.pred}}, st.crops, ANCHOR, lat,
                       "r6")["i5"]["gpu"]["verdict"] == "NO_VERDICT"  # fmt: skip


def _r6_files(tmp_path: Path, **change: Any) -> list[str]:
    """fi_eval's round-6 inputs on disk (1080 label file, params, key, predictions, I5)."""
    st = staged_as(R6_H1)
    params = tmp_path / "items-params-1080.json"
    pscreen = change.get("pscreen", "1080")
    params.write_text(json.dumps({"anchor_px": list(ANCHOR), "screen": pscreen}))
    doc = {**st.doc(), "session": change.get("session", R6_H1), "params": str(params),
           "screen": change.get("screen", "1080")}  # fmt: skip
    if doc["screen"] is None:
        del doc["screen"]
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps(doc))
    pred = tmp_path / "pred.json"
    pred.write_text(json.dumps({"frames": st.pred}))
    key = {"eval_test": True, "screen": "1080", "round": change.get("round", 6),
           "crops": {c["crop"]: {"truth": "item", **c} for c in st.crops}}  # fmt: skip
    kp = tmp_path / "key.json"
    kp.write_text(json.dumps(key))
    both = tmp_path / "both.json"
    both.write_text(json.dumps([c["crop"] for c in st.crops]))
    item, comp = tmp_path / "gpu-new.json", tmp_path / "gpu-fi5.json"
    item.write_text(json.dumps({"models": {"xmas02fi6": {"server": {"n": 300, "p95": 17.0}}}}))
    comp.write_text(json.dumps({"models": {"xmas02fi5": {"server": {"n": 300, "p95": 16.67}}}}))
    lat = tmp_path / "lat.json"
    lat.write_text(json.dumps({"ms": {"xmas02fi6": {"n": 300, "p95": 650.0},
                                      "xmas02fi5": {"n": 300, "p95": 651.2}}}))  # fmt: skip
    servers = [str(comp), str(item)] if change.get("swap") else [str(item), str(comp)]
    return ["--labels", str(lab), "--predictions", f"gpu={pred}", "--key", str(kp),
            "--evaluated", str(both), "--strata", "r6", "--gpu-server", *servers,
            "--cpu-latency", str(lat), "--cpu-item", "xmas02fi6", "--out",
            str(tmp_path / "out.json")]  # fmt: skip


def test_r6_main_reads_1080_inputs_only_and_needs_the_comparator(tmp_path: Path) -> None:
    args = _r6_files(tmp_path)
    assert fe.main([*args, "--comparator", "xmas02fi5"]) == 0
    out = json.loads((tmp_path / "out.json").read_text())
    assert out["bars"]["i1_recall"] == 0.9 and out["strata"] == "r6"
    assert out["i5"]["cpu"]["deployed_p95_ms"] == 651.2 and out["i5"]["comparator"] == "xmas02fi5"
    assert out["i5"]["gpu"]["deployed_p95_ms"] == 16.67
    with pytest.raises(SystemExit, match="--comparator"):  # r6 needs it
        fe.main(args)
    r5 = [x if x != "r6" else "r5" for x in args]
    with pytest.raises(SystemExit, match="--comparator"):  # and only r6 takes it
        fe.main([*r5, "--comparator", "xmas02fi5"])
    with pytest.raises(SystemExit, match="compares with --comparator"):
        fe.main([*args, "--comparator", "xmas02fi5", "--cpu-deployed", "xmas02gb"])
    with pytest.raises(SystemExit, match="the second file must hold xmas02fi5"):
        fe.main([*_r6_files(tmp_path, swap=True), "--comparator", "xmas02fi5"])
    for change, match in (({"screen": None}, "720 label files"),
                          ({"session": "20261112T093311-rdp-hunt-xmas02-fiH1"}, "held-out"),
                          ({"pscreen": "720"}, "not 1080 params"),
                          ({"round": 5}, "not round 6's pack")):  # fmt: skip
        with pytest.raises(SystemExit, match=match):
            fe.main([*_r6_files(tmp_path, **change), "--comparator", "xmas02fi5"])
    assert fe.round_inputs_refusal("r5", [{"session": "x"}], {}, {}) is None  # r2-r5: unchanged


# --- round 7 (xmas02-items-1080.md Amendment 22: xmas02fi6 + the fi7 rule; a NEW held-out) --------

R7_H5 = "20261122T010000-rdp-xmas02-ifH5"
R7_H10 = "20261122T020000-rdp-xmas02-ifH10"


def test_r7_names_strata_and_bars() -> None:
    assert tuple(f"-xmas02-ifH{i}" for i in range(5, 11)) == fe.R7_PILOTS
    assert fe.R7_STAGING == ("-xmas02-ifsH3", "-xmas02-ifsH4")
    assert (*fe.R7_PILOTS, *fe.R7_STAGING) == fe.R7_HELD_OUT
    assert fe.STRATA["r7"] == (fe.R7_HELD_OUT, (), fe.R7_PILOTS)
    assert fe.STRATA_NAMES["r7"] == ("i1h", "") and fe.SCREEN_OF["r7"] == "1080"
    assert fe.STRATA_APART["r7"] == {"natural": fe.R7_PILOTS, "staging": fe.R7_STAGING}
    assert dict(fe.bars_of("r7")) == dict(fe.bars_of("r6"))  # section 8a's bars, unchanged
    assert not set(fe.R7_HELD_OUT) & set(fe.R6_HELD_OUT)  # a NEW held-out
    assert fe.on_suffix(R7_H10, fe.R7_HELD_OUT) and not fe.on_suffix(R7_H10, fe.R6_HELD_OUT)


def test_rule_args_refusal() -> None:
    assert fe.rule_args_refusal(None, None, None, None) is None
    assert fe.rule_args_refusal(0.5, 30, None, Path("refs.json")) is None
    assert fe.rule_args_refusal(0.5, None, None, None) is None  # the floor alone needs no frame
    assert "--refs" in str(fe.rule_args_refusal(0.5, 30, None, None))
    assert "(0, 1]" in str(fe.rule_args_refusal(1.5, None, None, None))
    assert "at least 1" in str(fe.rule_args_refusal(None, 0, None, Path("refs.json")))
    assert "--ring-pad goes with" in str(fe.rule_args_refusal(0.5, None, 6, None))


def _round_files(tmp_path: Path, sid: str, strata: str, rnd: int) -> list[str]:
    """fi_eval's inputs for a 1080 round on disk (_r6_files' shape, any session / round)."""
    st = staged_as(sid)
    params = tmp_path / "items-params-1080.json"
    params.write_text(json.dumps({"anchor_px": list(ANCHOR), "screen": "1080"}))
    doc = {**st.doc(), "session": sid, "params": str(params), "screen": "1080"}
    lab = tmp_path / "l.json"
    lab.write_text(json.dumps(doc))
    pred = tmp_path / "pred.json"
    pred.write_text(json.dumps({"frames": st.pred}))
    key = {"eval_test": True, "screen": "1080", "round": rnd,
           "crops": {c["crop"]: {"truth": "item", **c} for c in st.crops}}  # fmt: skip
    kp = tmp_path / "key.json"
    kp.write_text(json.dumps(key))
    both = tmp_path / "both.json"
    both.write_text(json.dumps([c["crop"] for c in st.crops]))
    item, comp = tmp_path / "gpu-new.json", tmp_path / "gpu-fi5.json"
    item.write_text(json.dumps({"models": {"xmas02fi6": {"server": {"n": 300, "p95": 17.0}}}}))
    comp.write_text(json.dumps({"models": {"xmas02fi5": {"server": {"n": 300, "p95": 16.67}}}}))
    lat = tmp_path / "lat.json"
    lat.write_text(json.dumps({"ms": {"xmas02fi6": {"n": 300, "p95": 650.0},
                                      "xmas02fi5": {"n": 300, "p95": 651.2}}}))  # fmt: skip
    return ["--labels", str(lab), "--predictions", f"gpu={pred}", "--key", str(kp),
            "--evaluated", str(both), "--strata", strata, "--gpu-server", str(item), str(comp),
            "--cpu-latency", str(lat), "--cpu-item", "xmas02fi6", "--comparator", "xmas02fi5",
            "--out", str(tmp_path / "out.json")]  # fmt: skip


def test_r7_the_rule_drops_the_ring_box_and_the_faint_one_before_the_bars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The staged list as ifH5: its I3 frames 41 (a box inside her 5 x 5) and 42 (elsewhere).
    Frame 41's recorded picture shows the no-entry cursor ring around that box: with the rule
    (--item-floor 0.50 --ring-red 30) I3 goes 2 -> 1 frames with a box and 1 -> 0 in her 5 x 5;
    the 0.2 box on frame 4 falls under the floor; I1's 36 / 40 is unchanged. Without the
    options the result is round 6's code path, unchanged."""
    import fi7_rule as f7
    import numpy as np

    args = _round_files(tmp_path, R7_H5, "r7", 7)
    assert fe.main(args) == 0
    plain = json.loads((tmp_path / "out.json").read_text())["per_predictions"]["gpu"]
    assert (plain["i3"]["any"]["num"], plain["i3"]["around_5x5"]["num"]) == (2, 1)
    assert "rule" not in plain

    ring_key = fe.frame_key(R7_H5, 41)
    cx, cy = 640.0 + ANCHOR[0], 380.0 + ANCHOR[1]  # the staged box's centre
    loaded: list[str] = []

    def fake_load(refs: Any, key: str) -> Any:
        loaded.append(key)
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        if key == ring_key:
            yy, xx = np.ogrid[:720, :1280]
            d = np.hypot(xx - cx, yy - cy)
            img[(d >= 7) & (d <= 9)] = (220, 10, 12)  # the ring, pure red
        return img

    monkeypatch.setattr(f7, "load_frame", fake_load)
    refs = tmp_path / "refs.json"
    refs.write_text("{}")
    assert fe.main([*args, "--item-floor", "0.5", "--ring-red", "30", "--refs", str(refs)]) == 0
    out = json.loads((tmp_path / "out.json").read_text())
    g = out["per_predictions"]["gpu"]
    assert (g["i3"]["any"]["num"], g["i3"]["around_5x5"]["num"]) == (1, 0)
    assert g["i3"]["frames"] == plain["i3"]["frames"] == 600
    assert g["i1_strata"]["i1h"]["num"] == plain["i1_strata"]["i1h"]["num"] == 36
    assert g["rule"]["dropped"] == {"floor": 1, "ring": 1}
    assert (g["rule"]["floor"], g["rule"]["ring_red"], g["rule"]["pad"]) == (0.5, 30, 6)
    assert ring_key in loaded and g["rule"]["frames_loaded"] == len(loaded)
    assert out["strata"] == "r7" and out["bars"]["i1_recall"] == 0.9
    with pytest.raises(SystemExit, match="--refs"):
        fe.main([*args, "--ring-red", "30"])


def test_r7_reads_its_own_new_held_out_and_pack_only(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="not --strata r7's held-out"):  # round 6's ifH1
        fe.main(_round_files(tmp_path, R6_H1, "r7", 7))
    with pytest.raises(SystemExit, match="not round 7's pack"):
        fe.main(_round_files(tmp_path, R7_H5, "r7", 6))
    full = _round_files(tmp_path, R7_H5, "r7", 7)
    no_comp = [x for x in full if x not in ("--comparator", "xmas02fi5")]
    with pytest.raises(SystemExit, match="--comparator"):  # r7 needs it, as r6
        fe.main(no_comp)
