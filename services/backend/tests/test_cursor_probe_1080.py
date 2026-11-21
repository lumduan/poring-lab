"""scripts/cursor_probe_1080.py (cursor-1080.md Phase 1): the hover probes' pure parts, the live
loop against fakes (moves only, reads stored on new frames only), and the offline analysis."""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import cursor_probe_1080 as cp  # noqa: E402
import cursor_sword as csw  # noqa: E402


def test_its_constants_are_the_runner_s_own() -> None:
    """The probe hovers where, how far and how long the byte-pinned runner does."""
    text = (SCRIPTS / "dungeon_hunt.py").read_text()

    def const(name: str) -> str:
        m = re.search(rf"^{name} = (.+?)(  #|$)", text, re.M)
        assert m, name
        return m.group(1).strip()

    assert eval(const("FOOT_PX")) == cp.FOOT_PX  # noqa: S307 -- a literal of the pinned file
    assert float(const("BOX_TARGET_PX")) == cp.REACH_PX
    assert float(const("CURSOR_WAIT_S")) == cp.RUNNER_WINDOW_S
    import dungeon_hunt as dh

    box = (600.0, 200.0, 640.0, 260.0, 0.9, "cookie_xmas")
    assert dh.box_hover_points(box)[0] == cp.hover_point(box)
    import cursor_learn as cl

    assert cp.APPROACH == cl.APPROACH and cp.PARK == cl.PARK


def test_targets_are_picked_by_band_inside_the_runner_s_reach() -> None:
    near = (620.0, 320.0, 660.0, 360.0, 0.9, "monster")  # centre (640, 340): 22 px
    far = (780.0, 300.0, 820.0, 340.0, 0.8, "monster")  # centre (800, 320): 164 px
    beyond = (1000.0, 300.0, 1040.0, 340.0, 0.8, "monster")  # 380 px: out of reach
    rng = random.Random(1)
    assert cp.pick_target([near, far, beyond], "far", rng) == (1, (800.0, 320.0))
    assert cp.pick_target([near, far, beyond], "near", rng) == (0, (640.0, 340.0))
    assert cp.pick_target([beyond], "far", rng) is None


def test_only_the_runner_s_monster_boxes_are_targets() -> None:
    """cursor-1080.md Amendment 3: her own "player" box (and an NPC's) is never hovered -- the
    first P1 picked it on 116 of 120 hovers."""
    me = (622.5, 287.8, 658.7, 362.1, 0.96, "player")  # her own box, 37 px from her point
    npc = (780.0, 300.0, 820.0, 340.0, 0.9, "npc")
    mon = (700.0, 300.0, 740.0, 340.0, 0.7, "monster")
    rng = random.Random(3)
    for _ in range(20):
        assert cp.pick_target([me, npc], "near", rng) is None
        assert cp.pick_target([me, npc], "far", rng) is None
        assert cp.pick_target([me, npc, mon], "near", rng) == (2, (720.0, 320.0))
    assert cp.TARGET_CLS == "monster"
    assert cp.band(cp.dist(800.0, 320.0)) == "far" and cp.band(119.9) == "near"


def test_walk_points_stay_clear_of_every_box_and_of_the_panels() -> None:
    boxes = [(700.0, 200.0, 740.0, 260.0, 0.9, "a"), (450.0, 400.0, 490.0, 460.0, 0.9, "b")]
    pts = cp.walk_points(boxes, random.Random(3), n=6)
    assert len(pts) == 6
    for u, v in pts:
        assert 80 <= u <= 1200 and 170 <= v <= 560
        for b in boxes:
            p, q = cp.hover_point(b)
            assert ((u - p) ** 2 + (v - q) ** 2) ** 0.5 >= cp.WALK_CLEAR_PX
        r = ((u - cp.FOOT_PX[0]) ** 2 + ((v - cp.FOOT_PX[1]) / 0.7) ** 2) ** 0.5
        assert cp.WALK_RING[0] - 0.5 <= r <= cp.WALK_RING[1] + 0.5


def test_a_walk_read_is_the_arrow_never_the_hand() -> None:
    assert cp.is_walk_read({"sword": 0.3, "walk": 0.95, "pickup": 0.1})
    assert not cp.is_walk_read({"sword": 0.3, "walk": 0.95, "pickup": 0.97})  # the hand: loot
    assert not cp.is_walk_read({"sword": 0.65, "walk": 0.95, "pickup": 0.1})
    assert not cp.is_walk_read({"sword": 0.3, "walk": 0.80, "pickup": 0.1})


def test_the_frame_counters() -> None:
    got = cp.frame_stats([10, 10, 11, 12, 12, 14], [0.0, 20.0, 40.0, 60.0, 80.0, 100.0])
    assert got == {"reads": 6, "fps": 40.0, "new_per_s": 30.0, "repeat_share": 0.4}
    assert cp.frame_stats([3], [0.0])["fps"] is None


def _r(t: float, verdict: str, real: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"t_ms": t, "verdict": verdict, **({"real": real} if real else {})}


def test_the_runner_s_decision_is_replayed_inside_its_window() -> None:
    reads = [_r(150, "unknown"), _r(300, "unknown"), _r(420, "sword")]
    assert cp.runner_replay(reads) == "unknown"  # the sword came after 0.35 s
    assert cp.runner_replay(reads, 1.0) == "sword"
    assert cp.first_ms(reads, "sword") == 420.0 and cp.first_ms(reads, "clear") is None


def test_each_hover_class_from_its_reads() -> None:
    none = {"sword": [0.3, 0, 0], "walk": [0.4, 0, 0], "pickup": [0.1, 0, 0]}
    assert cp.classify([_r(150, "unknown", none), _r(400, "sword")], []) == "sword_at_point"
    off = {**none, "sword": [0.82, 24, -8]}
    assert cp.classify([_r(150, "unknown", off)], []) == "sword_offset"
    near = {**none, "sword": [0.82, 4, 2]}  # within OFFSET_PX: not elsewhere
    assert cp.classify([_r(150, "unknown", near)], []) == "nothing"
    assert cp.classify([_r(150, "clear", none)], []) == "walk_at_point"
    old = {**none, "walk": [0.97, 2, 1]}
    assert cp.classify([_r(150, "unknown", none)], [old]) == "old_place"
    assert cp.classify([_r(150, "unknown", none)], [none]) == "nothing"


def test_the_summary_per_mode_and_band() -> None:
    def hv(band: str, runner: str, cls: str, fs: float | None) -> dict[str, Any]:
        return {"mode": "stand", "band": band, "runner": runner, "runner_at": runner,
                "class": cls, "first_sword_ms": fs, "first_read_ms": 30.0,
                "frames": {"fps": 20.0, "repeat_share": 0.5}}  # fmt: skip

    s = cp.summarise([hv("far", "unknown", "sword_at_point", 520.0),
                      hv("far", "sword", "sword_at_point", 250.0),
                      hv("near", "sword", "sword_at_point", 200.0)])  # fmt: skip
    assert s["stand/far"]["n"] == 2 and s["stand/far"]["runner_unknown_share"] == 0.5
    assert s["stand/far"]["first_sword_ms"] == {"median": 250.0, "p90": 520.0, "n": 2}
    assert s["stand/near"]["runner"] == {"sword": 1}


def test_the_real_search_finds_a_sword_off_the_point() -> None:
    """A SWORD reference pasted 20 px right and 12 px up of the real box's centre is found
    there (the offset's signs are the hotspot's from the real point)."""
    import cursor_robust as cr

    if not cr.REFS_V3.exists():
        pytest.skip("no cursor references on this host (client pixels, gitignored)")
    z = np.load(cr.REFS_V3)
    i = next(k for k, c in enumerate(z["cls"]) if str(c) == "sword")
    sw = csw.SwordRefs(cr.RobustRefs.load(), exclude_ref=[i])
    box = np.full((160, 160, 3), 37, np.uint8)
    oy, ox = 80 - 12 - 32, 80 + 20 - 32
    box[oy : oy + 64, ox : ox + 64] = np.asarray(z["a"][i])[..., :3]
    got = cp.real_search(sw, box, 4)
    assert got["sword"][0] >= csw.SWORD_MIN and got["sword"][1:] == [20, -12]


class FakeAgent:
    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []
        self.clicks: list[tuple[int, int]] = []

    def move(self, x: int, y: int) -> None:
        self.moves.append((x, y))

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class FakeScreen:
    """Each grab advances a clock; the bus frame id changes every third grab."""

    def __init__(self) -> None:
        self.n = 0
        self.boxes: list[tuple[int, int, int, int]] = []

    def grab_meta(self, x: int, y: int, w: int, h: int) -> tuple[int, Any, int, str]:
        self.n += 1
        self.boxes.append((x, y, w, h))
        return 0, np.full((h, w, 4), self.n % 250, np.uint8), self.n // 6, "bus"


def test_a_hover_moves_only_and_stores_new_frames_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cp, "_real_point", lambda r, u, v: (int(u * 1.5), int(v * 1.5)))
    monkeypatch.setattr(cp, "READ_GAP_S", 0.0)
    agent, screen = FakeAgent(), FakeScreen()
    rec, arr = cp.probe_hover(agent, screen, None, 100_000, 0, 700.0, 300.0, (900, 400),
                              read_s=0.05)  # fmt: skip
    assert agent.clicks == [] and agent.moves == [(100_000 + 697, 298), (100_000 + 700, 300)]
    assert screen.boxes[0] == (100_000 + 700 - 32, 300 - 32, 64, 64)  # the reader's crop
    assert screen.boxes[1] == (1050 - 80, 450 - 80, 160, 160)  # the real box at the real point
    assert screen.boxes[2] == (900 - 80, 400 - 80, 160, 160)  # the previous point at the start
    stored = [r for r in rec["reads"] if r["stored"]]
    assert 0 < len(stored) < len(rec["reads"])  # repeated frames keep their times only
    assert arr["v"].shape == (len(stored), 64, 64, 3) and arr["r"].shape[1:] == (160, 160, 3)
    assert arr["p"].shape[0] == 2  # the previous point at the start and (by the end) 0.35 s
    assert rec["real_xy"] == [1050, 450] and rec["prev_xy"] == [900, 400]


def test_a_walk_click_only_where_the_arrow_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    reads = iter(
        [
            {"verdict": "unknown", "rec": {"sword": 0.3, "walk": 0.4, "pickup": 0.1}},
            {"verdict": "clear", "rec": {"sword": 0.3, "walk": 0.5, "pickup": 0.95}},
            {"verdict": "clear", "rec": {"sword": 0.3, "walk": 0.97, "pickup": 0.1}},
        ]
    )
    monkeypatch.setattr(csw, "check", lambda *a, **k: {**next(reads), "ms": 300})
    monkeypatch.setattr(csw, "crop_at", lambda *a: np.zeros((64, 64, 3), np.uint8))

    class Again:  # the no-motion re-read: the arrow again
        def recalls(self, crop: Any) -> dict[str, float]:
            return {"sword": 0.3, "walk": 0.96, "pickup": 0.1}

    agent = FakeAgent()
    got = cp.walk_click(agent, None, Again(), 100_000, 0, [], random.Random(2))
    assert got["tried"] == 3 and len(agent.clicks) == 1  # not on the unknown, not on the hand
    u, v = got["clicked"]
    assert agent.clicks[0] == (100_000 + round(u), round(v))


def test_no_walk_click_when_the_re_read_loses_the_arrow(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = {"verdict": "clear", "rec": {"sword": 0.3, "walk": 0.97, "pickup": 0.1}}
    monkeypatch.setattr(csw, "check", lambda *a, **k: {**ok, "ms": 300})
    monkeypatch.setattr(csw, "crop_at", lambda *a: np.zeros((64, 64, 3), np.uint8))

    class Lost:  # a monster walked under the point between the reads
        def recalls(self, crop: Any) -> dict[str, float]:
            return {"sword": 0.8, "walk": 0.5, "pickup": 0.1}

    agent = FakeAgent()
    got = cp.walk_click(agent, None, Lost(), 100_000, 0, [], random.Random(2))
    assert got["clicked"] is None and agent.clicks == [] and got["tried"] == cp.WALK_TRIES


def test_the_live_steps_refuse_without_the_immunity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cp, "OUT", tmp_path)
    with pytest.raises(SystemExit, match="immune"):
        cp.main(["hovers", "--label", "x", "--mode", "stand"])
    with pytest.raises(SystemExit, match="immune"):
        cp.main(["frames", "--label", "x", "--mode", "walk"])


class FakeRefs:
    """SWORD when the crop's mean is 200, the WALK arrow at 120, else nothing."""

    def recalls(self, crop: Any) -> dict[str, float]:
        m = float(np.asarray(crop).mean())
        return {"sword": 0.9 if m == 200 else 0.3, "pickup": 0.1,
                "walk": 0.95 if m == 120 else 0.4}  # fmt: skip


def test_the_analysis_of_stored_hovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "L"
    d.mkdir()

    def store(i: int, band: str, vals: list[int], times: list[float]) -> None:
        reads = [{"t_ms": t, "fid": k, "fid_real": k, "stored": True}
                 for k, t in enumerate(times)]  # fmt: skip
        reads.insert(1, {"t_ms": times[0] + 5, "fid": 0, "fid_real": 0, "stored": False})
        v = np.stack([np.full((64, 64, 3), x, np.uint8) for x in vals])
        r = np.stack([np.full((160, 160, 3), 50, np.uint8) for _ in vals])
        np.savez_compressed(d / f"h{i:03d}.npz", v=v, r=r, p=np.zeros((0, 160, 160, 3), np.uint8))
        (d / f"h{i:03d}.json").write_text(json.dumps(
            {"i": i, "mode": "stand", "band": band, "dist": 150.0, "u": 1.0, "v": 2.0,
             "real_xy": [0, 0], "prev_xy": None, "reads": reads}))  # fmt: skip

    store(0, "far", [50, 50, 200], [150.0, 300.0, 450.0])  # a sword after the runner's window
    store(1, "near", [200, 50], [150.0, 200.0])  # a sword at once
    store(2, "far", [50, 120], [150.0, 300.0])  # the walk arrow: nothing under the point
    monkeypatch.setattr(csw.SwordRefs, "load", classmethod(lambda cls, *a: FakeRefs()))
    got = cp.analyse("L", stride=48, workers=1, root=tmp_path)
    g = got["groups"]
    assert got["hovers"] == 3
    assert g["stand/far"]["runner"] == {"unknown": 1, "clear": 1}
    assert g["stand/far"]["runner_at_1s"] == {"sword": 1, "clear": 1}
    assert g["stand/far"]["classes"] == {"sword_at_point": 1, "walk_at_point": 1}
    assert g["stand/near"]["first_sword_ms"]["median"] == 150.0
    rows = [json.loads(x) for x in (d / "analysed.jsonl").read_text().splitlines()]
    assert rows[0]["reads"][1]["verdict"] == "unknown"  # the repeat keeps the last verdict
    # the reader's crop against the real pixels at the point: 0 until the 200 read
    assert rows[0]["reads"][0]["vr_diff"] == 0.0 and rows[0]["vr_diff_max"] == 150.0
    assert rows[0]["black_max"] == 0.0
