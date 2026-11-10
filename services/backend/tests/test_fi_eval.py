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

SID = "20261111T090000-rdp-hunt-xmas02-fiT1"
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
