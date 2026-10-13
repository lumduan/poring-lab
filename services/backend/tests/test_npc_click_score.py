"""scripts/npc_click_score.py (walk@17 item 5, offline): detector recall vs packet truth, the L3
layer replayed on a walk session, walk@12's TALK-cell memory vs the NPC cells, the colour check's
shift test, and the targeted test's judge -- on SYNTHETIC sessions (ids invented, no client
pixels: the committed camera on a synthetic flat GAT)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
S = 1_000_000_000
AID, FLAG, GUIDE = 2_000_002, 110_000_071, 110_000_070


def load(name: str) -> ModuleType:
    sys.path.insert(0, str(ROOT / "scripts"))
    sys.path.insert(0, str(ROOT / "packages/poring_dataset/src"))
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


nc = load("npc_noclick")
ncs = load("npc_click_score")


def camera() -> Any:
    from poring_dataset import camera as cam

    cj = json.loads(ncs.CAMERA_JSON.read_text())
    return cam.camera_from_json(cj["camera"])


def flat_gat(size: int = 300) -> Any:
    from poring_dataset import gat as gatmod

    return gatmod.Gat(size, size, "1.2", np.zeros((size, size), gatmod.TILE))


CAM_GAT = (camera(), flat_gat())


def ev(t_s: float, etype: str, **f: Any) -> dict[str, Any]:
    return {"t_mono_ns": int(t_s * S), "type": etype, "server": "map", "dir": "sc", **f}


def town(x: int, y: int) -> list[dict[str, Any]]:
    """We stand on (x, y) in prontera; a job-722 flag on (155, 190), the guide (105) on (154, 187),
    a hidden NPC (111), a portal (45) and an NPC sent with an invisibility option: never drawn."""
    npc = {"kind": "stand", "char_id": 0, "objtype": 6, "speed": 200, "name": "", "heading": 4}
    return [ev(0.0, "login_accepted", aid=AID, sex=1),
            ev(0.1, "map_change", map="prontera.gat", x=x, y=y),
            ev(0.2, "entity_appear", gid=FLAG, job=722, x=155, y=190, **npc),
            ev(0.2, "entity_appear", gid=GUIDE, job=105, x=154, y=187, **npc),
            ev(0.2, "entity_appear", gid=110_000_111, job=111, x=150, y=185, **npc),
            ev(0.2, "entity_appear", gid=110_000_045, job=45, x=150, y=186, **npc),
            ev(0.2, "entity_appear", gid=110_000_705, job=705, x=151, y=185, effect_state=2,
               **npc)]  # fmt: skip


def write_session(d: Path, events: list[dict[str, Any]], records: list[dict[str, Any]],
                  map_name: str = "prontera") -> Path:  # fmt: skip
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps({"map": map_name}))
    (d / "demo.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    with gzip.open(d / "packets.jsonl.gz", "wt") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return d


def flat_projector(cj: Any, m: str) -> Any:
    cam = camera()
    return (lambda offsets, origin: cam.project(offsets)), "flat"


def feet(pos: tuple[int, int], cell: tuple[int, int]) -> tuple[float, float]:
    ((u, v),) = camera().project(np.array([[cell[0] - pos[0], cell[1] - pos[1]]], dtype=float))
    return float(u), float(v)


def test_static_npcs_keep_drawn_npcs_only() -> None:
    got = ncs.static_npcs(town(155, 185))
    assert sorted(got) == [GUIDE, FLAG] and got[FLAG]["job"] == 722
    assert got[FLAG]["cell"] == (155, 190) and got[FLAG]["map"] == "prontera"


def test_recall_per_job_against_packet_truth() -> None:
    u, v = feet((155, 185), (154, 187))
    batches = [{"id": 0, "t_frame": 1 * S, "boxes": [[u - 17, v - 74, u + 17, v, 0.6, "npc"]]},
               {"id": 1, "t_frame": 2 * S, "boxes": []}]  # fmt: skip
    out = ncs.recall(town(155, 185), batches, projector_for=flat_projector)
    assert out["per_job"]["105"]["k"] == 1 and out["per_job"]["105"]["n"] == 2
    assert out["per_job"]["722"] == {"k": 0, "n": 2, "rate": 0.0,
                                     "ci95": out["per_job"]["722"]["ci95"]}  # fmt: skip
    assert out["npc_sightings"]["k"] == 1 and out["npc_sightings"]["n"] == 4
    assert out["per_gid"][str(GUIDE)]["max_score"] == 0.6 and out["bank"] == [0, 1]
    assert "111" not in out["per_job"] and "45" not in out["per_job"]


def test_a_box_sees_an_npc_by_its_feet_only() -> None:
    assert ncs.box_sees([100, 100, 140, 200, 0.5, "monster"], (120.0, 200.0))
    assert ncs.box_sees([100, 100, 140, 200, 0.5, "monster"], (150.0, 210.0))  # grown by 20 px
    assert not ncs.box_sees([100, 100, 140, 200, 0.5, "monster"], (300.0, 200.0))


def route(k: int, events: list[dict[str, Any]], goal: list[int]) -> dict[str, Any]:
    return {
        "record_id": f"r{k}",
        "rule": "walk@15",
        "t_mono_ns": 1,
        "outcome": {"status": "success", "evidence": {"goal": goal, "events": events}},
    }


def test_replay_l3_refuses_the_contact_click_only_with_the_npc_in_l3(tmp_path: Path) -> None:
    t_click = int(5 * S)
    events = [*town(161, 192), ev(5.17, "npc_contact", npc_gid=FLAG, contact_type=1, dir="cs")]
    steps = [{"from": [161, 192], "end": [156, 192], "clicked": True, "t_click": t_click,
              "target": [{"at": [464.9, 360.9], "shape": "walk"}]},
             {"from": [161, 192], "end": [166, 192], "clicked": True, "t_click": int(9 * S),
              "target": [{"at": [900.0, 360.0], "shape": "walk"}]}]  # fmt: skip
    d = write_session(tmp_path / "s", events, [route(0, steps, [150, 192])])
    flag = nc.StaticNpc("prontera", (155, 190), "test:flag", "722", "test")
    out = ncs.replay_l3(d, layers={"with": nc.NoClickLayer([flag]),
                                   "without": nc.NoClickLayer([])},
                        camera_gat=CAM_GAT)  # fmt: skip
    assert out["clicks"] == 2 and len(out["contacts"]) == 1
    c = out["contacts"][0]
    assert c["contact_gid"] == FLAG and c["with"] is True and c["without"] is False
    assert out["with"]["clicks_refused"] == 1 and out["with"]["contacts_refused"] == 1
    assert out["without"]["clicks_refused"] == 0
    assert out["with"]["scored_routes_with_a_refused_click"] == 1


def test_remembered_talk_cells_are_the_floor_cell_under_the_read(tmp_path: Path) -> None:
    """walk@12's memory stores the cell the picking model puts under the TALK pixel. A read on the
    flag's sprite 22 px above its feet is remembered one row BEHIND it."""
    pos = (155, 185)
    u, v = feet(pos, (155, 190))
    picked_feet = [155, 190]
    above = [155, 191]
    steps = [
        {
            "from": list(pos),
            "end": [155, 190],
            "clicked": False,
            "target": [{"at": [u, v], "shape": "talk"}],
            "talk_cells": [picked_feet],
        },
        {
            "from": list(pos),
            "end": [155, 191],
            "clicked": False,
            "target": [{"at": [u, v - 22.6], "shape": "talk"}],
            "talk_cells": [above],
        },
    ]
    d = write_session(tmp_path / "s", town(*pos), [route(0, steps, [155, 191])])
    out = ncs.remembered(d, camera_gat=CAM_GAT)
    assert out["talk_reads"] == 2 and out["reproduced"] == 2
    assert out["remembered_is_npc_cell"] == 1 and out["offset_cells"]["0,1"] == 1


def bubble_refs() -> Any:
    """Synthetic references: a 'talk' blob of horizontal 1-px stripes (a 1 px vertical shift
    flips every colour) x3, and a 'walk' square x3; their masks."""
    import walk6 as w6

    a = np.full((6, 64, 64, 3), 128, np.uint8)
    m = np.zeros((6, 64, 64), bool)
    yy, xx = np.mgrid[0:64, 0:64]
    blob = ((xx - 32) / 14.0) ** 2 + ((yy - 30) / 10.0) ** 2 <= 1
    for i in range(3):
        a[i][blob] = np.where((yy[blob] % 2)[:, None] == 0, 250, 10)
        m[i] = blob
    sq = (abs(xx - 36) < 6) & (abs(yy - 36) < 9)
    for i in range(3, 6):
        a[i][sq] = 200
        m[i] = sq
    return w6.CursorRefs(a, m, ["talk"] * 3 + ["walk"] * 3)


def test_a_one_pixel_shift_fails_the_colour_check_and_best_shift_finds_it() -> None:
    refs = bubble_refs()
    a, m = refs.a[0].astype(np.uint8), refs.m[0]
    assert refs.match(a, m)["shape"] == "talk"
    sa, sm = np.roll(a, 1, 0), np.roll(m, 1, 0)
    got = ncs.explain(refs, sa, sm)
    assert got["shape"] == "unknown" and got["col"] == 0.0  # walk6's placeholder ...
    assert got["best"]["iou"] >= 0.6 and got["best"]["col"] < 0.85  # ... the REAL colour
    assert ncs.best_shift(refs, sa, sm) == {"shift": [0, -1], "iou": 1.0, "col": 1.0}
    out = ncs.refs_shift(refs, "talk", "", shifts=((0, 0), (0, 1)), src=[""] * 6)
    assert out["0,0"]["read"] == {"talk": 3} and out["0,1"]["read"] == {"unknown": 3}


def test_verdict_is_prober9s_first_three_grabs() -> None:
    def reads(*shapes: str) -> list[dict[str, str]]:
        return [{"shape": s} for s in shapes]

    assert ncs.verdict(reads("unknown", "talk", "unknown")) == "talk"
    assert ncs.verdict(reads("unknown", "unknown", "unknown", "talk")) == "unknown"


def probe(k: int, pos: tuple[int, int], at: tuple[float, float], shapes: list[str],
          best_iou: float) -> dict[str, Any]:  # fmt: skip
    reads = [{"shape": s, "iou": best_iou, "col": 0.0,
              "best": {"cls": "talk", "iou": best_iou, "col": 0.7}} for s in shapes]  # fmt: skip
    return {"record_id": f"p{k}", "rule": ncs.PROBE, "t_mono_ns": int(3 * S),
            "outcome": {"evidence": {"npc": "test:flag", "npc_cell": [155, 190],
                                     "stand": list(pos), "kind": "sprite", "offset": [0, -14],
                                     "at": list(at), "reads": reads}}}  # fmt: skip


def click(k: int, pos: tuple[int, int], cell: list[int], at: tuple[float, float],
          t_click: int | None, why: str = "ok") -> dict[str, Any]:  # fmt: skip
    gate = {"clicked": t_click is not None, "why": why, "t_click": t_click}
    return {"record_id": f"c{k}", "rule": ncs.CLICK, "t_mono_ns": int(4 * S),
            "outcome": {"evidence": {"npc": "test:flag", "npc_cell": [155, 190],
                                     "stand": list(pos), "cell": cell, "at": list(at),
                                     "gate": gate, "dialog": {"action": "none"}}}}  # fmt: skip


def test_score_reads_clicks_and_the_l3_arms(tmp_path: Path) -> None:
    pos = (155, 185)
    fu, fv = feet(pos, (155, 190))
    events = [*town(*pos),
              ev(10.1, "npc_contact", npc_gid=FLAG, contact_type=1, dir="cs"),
              ev(20.2, "self_move_request", x=150, y=180, dir="cs")]  # fmt: skip
    recs = [
        probe(0, pos, (fu, fv - 14), ["talk"], 0.95),
        probe(1, pos, (fu, fv - 28), ["unknown"] * 3, 0.88),
        click(0, pos, [156, 191], (fu + 30, fv - 30), int(10 * S)),
        click(1, pos, [150, 180], (fu - 300, fv + 200), int(20 * S)),
        click(2, pos, [156, 189], (fu + 30, fv + 20), None, "cursor_unknown"),
    ]
    d = write_session(tmp_path / "s", events, recs)
    flag = nc.StaticNpc("prontera", (155, 190), "test:flag", "722", "test")
    out = ncs.score(d, layers={"with": nc.NoClickLayer([flag]), "without": nc.NoClickLayer([])},
                    camera_gat=CAM_GAT)  # fmt: skip
    assert out["probes"] == 2 and out["probes_off_stand"] == 0
    assert out["talk_read_rate"]["all"]["k"] == 1 and out["talk_read_rate"]["all"]["n"] == 2
    assert out["colour_fail_rate"]["all"]["k"] == 1
    assert out["remembered_cell_offset"] == {"0,1": 1}  # 14 px up the sprite: the row behind
    assert out["click_outcomes"] == {"npc_contact": 1, "self_move_request": 1,
                                     "not_clicked:cursor_unknown": 1}  # fmt: skip
    assert out["walk_read_but_contact"]["ring/1"]["k"] == 1
    arm = out["l3_arms"]["with"]
    assert arm["contacts_refused"]["k"] == 1 and arm["contacts_left_with_layer"] == 0
    assert (
        arm["contact_rate_among_allowed"]["k"] == 0 and arm["contact_rate_among_allowed"]["n"] == 1
    )
    assert out["colour_fail_causes"] == {"no_later_grab_passed": 1}  # no crop, no refs: timing only
    assert out["l3_arms"]["without"]["contacts_left_with_layer"] == 1


def test_score_sorts_a_colour_fail_by_what_restores_it(tmp_path: Path) -> None:
    """A probe whose saved crop is a reference moved by 1 px: C1 (a shift) restores it, blurred
    references do not."""
    refs = bubble_refs()
    pos = (155, 185)
    fu, fv = feet(pos, (155, 190))
    rec = probe(0, pos, (fu, fv - 14), ["unknown"] * 6, 0.88)
    rec["outcome"]["evidence"]["crop"] = "crops/00000.npz"
    d = write_session(tmp_path / "s", town(*pos), [rec])
    (d / "crops").mkdir()
    a, m = refs.a[0].astype(np.uint8), refs.m[0]
    np.savez_compressed(d / "crops/00000.npz", a=np.roll(a, 1, 0), mask=np.roll(m, 1, 0))
    out = ncs.score(d, layers={}, camera_gat=CAM_GAT, refs=refs)
    assert out["colour_fail_causes"] == {"no_later_grab_passed": 1, "C1_restored_by_shift": 1,
                                         "C2_not_by_blur": 1}  # fmt: skip


def test_a_resumed_click_arm_is_scored_in_segments(tmp_path: Path) -> None:
    """3.32a amendment: each run of a resumed session (records > SEGMENT_GAP_S apart) is reported
    apart, with its gate (robust2 = the 6-grab series, else v3) and the safety of ITS window."""
    pos = (155, 185)
    fu, fv = feet(pos, (155, 190))
    gap = ncs.SEGMENT_GAP_S + 60
    recs = []
    for k, (t, robust) in enumerate([(4, False), (19, False), (4 + gap, True), (19 + gap, True)]):
        rec = click(k, pos, [150, 180], (fu - 300, fv + 200), int((t + 1) * S))
        rec["t_mono_ns"] = int(t * S)
        rec["outcome"]["evidence"]["gate"]["shape"] = "walk"
        if robust:
            rec["outcome"]["evidence"]["gate"]["shapes"] = ["walk"] * 6
        recs.append(rec)
    events = [*town(*pos),
              ev(5.2, "self_move_request", x=150, y=180, dir="cs"),
              ev(20.2, "self_move_request", x=150, y=180, dir="cs"),
              ev(5.2 + gap, "self_move_request", x=150, y=180, dir="cs"),
              ev(20.2 + gap, "attack_request", target_gid=1, dir="cs")]  # fmt: skip
    d = write_session(tmp_path / "s", events, recs)
    out = ncs.score(d, layers={"none": nc.NoClickLayer([])}, camera_gat=CAM_GAT)
    segs = out["segments"]
    assert [s["records"] for s in segs] == [2, 2]
    assert [s["gate"] for s in segs] == [["v3"], ["robust2"]]
    assert segs[0]["safety"]["attack_request"] == 0 and segs[1]["safety"]["attack_request"] == 1
    assert segs[0]["click_outcomes"] == {"self_move_request": 2}
    assert segs[1]["click_outcomes"] == {"self_move_request": 1, "nothing": 1}
    assert out["click_outcomes"] == {"self_move_request": 3, "nothing": 1}  # the whole arm
