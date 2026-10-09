#!/usr/bin/env python3
"""loot@1 (docs/demonstrations.md 3.20, run plan 3.20a): kill, then loot WITHOUT new training -- a
hover-scan for the PICKUP cursor around the pixel death cell, checked by the weight readout (P1)
or the "item obtained" chat cue (P5).

    loot1.py p3  --n 10 --seed 20261110    P3's positive case: the pixel death cell of each kill
    loot1.py run --n 40 --seed 20261111    the trials; the first 20 DROP trials are scored offline

One trial, on prt_fild08 at a fresh spot (a seeded list of open cells >= 6 apart):
  1. @killmonster2, @alive, @heal, @warp to the spot, @monster Poring 1 beside the GM.
  2. A sampler thread detects units on every frame it can (the CPU detector) until the target
     vanishes; the target is the monster nearest the GM's feet, then tracked frame to frame.
  3. The KILL (3.20 step 3, deliberate): a click on the target only where the cursor reads the
     SWORD twice (the proven monster positive case's rule, never a box centre), again after
     REATTACK_S if it still lives; the GM's own cell from the MINIMAP readout (two equal reads on
     fresh frames, passive: no /where is ever typed, Batt 2026-10-09) once it stands and fights.
  4. Death from pixels: the target unseen for GONE_FRAMES frames and GONE_S after an attack. Its
     cell: poring_dataset.deathcell (the last sightings' feet through the picking model).
  5. LOOT (the rule under test): the 3 x 3 cells around the death cell, the server's drop pattern
     first (deathcell.scan_order); per cell one hover with two motions; a click needs the cursor
     to read PICKUP twice (no other shape is allowed), walk@11's unit gate, and a point clear of
     the client's UI windows. The first such point is clicked.
  6. The runtime check, within CHECK_S of the click: the weight readout (P1, two equal reads) rises,
     OR the chat cue (P5) reads "got". Either is enough at run time; both are recorded.
Packets are never read here (rule 1): they judge the session offline (loot1_score.py).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chat_cue  # noqa: E402
import gm_state  # noqa: E402
import record_session  # noqa: E402
import ro_agent as r  # noqa: E402
import rule_run as rr  # noqa: E402
import ui_mask  # noqa: E402
import walk5 as w5  # noqa: E402
import walk6 as w6  # noqa: E402
import walk10 as w10  # noqa: E402
import walk11 as w11  # noqa: E402

from poring_dataset import deathcell as dcm  # noqa: E402
from poring_env.demo import DemoLog, new_session_id  # noqa: E402

RULE = "loot@1"
MAP = "prt_fild08"
PORING = 1002
REGION = (245, 85, 295, 130)  # x0, y0, x1, y1 cells: the spots' area (open field, near 3.19's)
CLEAR = 4  # a spot's +-4 square is walkable: the spawn lands within 3 cells, the scan within 1 more
APART = 6  # spots this far apart (Chebyshev): no item of an earlier trial is in reach
SPAWN_WAIT_S = 2.0
SPAWN_PX = 220.0  # the Poring lands within 3 cells of the GM: its feet this close to the GM's
TRACK_PX = 45.0  # frame to frame, the target's feet move less than this (400 ms per cell)
# Pilot 2026-10-09 15:00 (3.20a step 0): the spawned Poring WANDERS (2-12 cells from the spot, a
# step every ~6-7 s) and the sampler runs at ~2 fps on the CPU, so a fixed 45 px gate lost it after
# its first move and the sword probes kept hovering a stale box. The gate now grows with the time
# since the last sighting, and a probe needs a FRESH and STILL box.
MOVE_PX_S = 110.0  # ~2.5 cells/s (400 ms per cell) x ~40 px per cell, on screen
TRACK_MAX_PX = 160.0  # never wider than this, however long unseen
FIND_S = 6.0  # the spawn is looked for on EVERY frame this long (the pilot judged one frame)
FRESH_S = 0.5  # a probe only on a box seen this recently ...
STILL_PX = 6.0  # ... whose feet moved less than this since the sighting before it ...
STILL_GAP_S = 1.5  # ... taken at most this long before it
NO_CLICK_S = 30.0  # found but no sword-gated click within this: "no_sword" / "never_still"
GONE_FRAMES = 3  # deathcell's rule
GONE_S = 1.0  # and at least this long unseen, after an attack (the detector misses a frame or two)
KILL_S = 30.0  # no vanish within this of the first attack click: "no_kill"
REATTACK_S = 8.0  # still visible this long after an attack click: one more sword-gated click
FIX_AFTER_S = 1.5  # the minimap read once the GM has walked up (<= 3 cells at 150 ms) and fights
PLAUSIBLE_CELLS = 6  # a readout farther than this from the spot is refused (never a guess)
CHECK_S = 5.0
BUDGET_S = 20.0  # death -> pickup click (3.20: reported)
TOO_SLOW_S = 45.0  # death -> pickup click beyond this: FAILURE "too slow" (judged offline too)
UI_PAD = 12.0  # px around the client's UI windows: never a click there
FOOT_LIFT = 4.0  # rec@0b: the foot pixel 4 px up before the pick (the sprite's shadow line)
ATTACK_POINTS = ((0.5, 1.0, -8.0), (0.5, 0.5, 0.0), (0.5, 0.3, 0.0))  # box fractions + dv px
CURSOR_REFS_V3 = r.ROOT / "data/walk6/cursor_refs_rdp_v3.npz"
Cell = tuple[int, int]


# --- pure parts (tested) ------------------------------------------------------------------------


def spots(walkable: Any, seed: int, n: int, region: tuple[int, int, int, int] = REGION,
          clear: int = CLEAR, apart: int = APART) -> list[Cell]:  # fmt: skip
    """``n`` spots in ``region`` whose +-clear square is walkable, every pair >= apart, in a
    seeded order. Fewer when the region cannot hold n."""
    x0, y0, x1, y1 = region
    cands = []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            sq = walkable[y - clear : y + clear + 1, x - clear : x + clear + 1]
            if sq.shape == (2 * clear + 1, 2 * clear + 1) and bool(sq.all()):
                cands.append((x, y))
    random.Random(seed).shuffle(cands)
    out: list[Cell] = []
    for c in cands:
        if all(max(abs(c[0] - o[0]), abs(c[1] - o[1])) >= apart for o in out):
            out.append(c)
            if len(out) == n:
                break
    return out


def foot_of(box: Any) -> tuple[float, float]:
    return (box.x0 + box.x1) / 2, float(box.y1)


def nearest(boxes: list[Any], p: tuple[float, float], within: float) -> Any | None:
    best, bd = None, within
    for b in boxes:
        fx, fy = foot_of(b)
        d = float(np.hypot(fx - p[0], fy - p[1]))
        if d <= bd:
            best, bd = b, d
    return best


def find_spawn(frames: list[tuple[int, list[Any]]], gm_feet: tuple[float, float],
               within: float = SPAWN_PX) -> tuple[int, Any] | None:  # fmt: skip
    """The first frame with a monster box whose feet are within ``within`` of the GM's: (its
    index, the box nearest the GM there). Every frame counts, not only the last."""
    for i, (_t, boxes) in enumerate(frames):
        b = nearest(boxes, gm_feet, within)
        if b is not None:
            return i, b
    return None


@dataclass
class Track:
    """The target over the sampler's frames: the monster box nearest its last feet."""

    foot: tuple[float, float]
    sightings: list[dcm.Sighting] = field(default_factory=list)
    last_box: Any = None
    last_seen_ns: int | None = None

    def gate_px(self, t_ns: int) -> float:
        """How far the feet may have moved since the last sighting (the target wanders)."""
        if self.last_seen_ns is None:
            return TRACK_PX
        dt = max(0.0, (t_ns - self.last_seen_ns) / 1e9)
        return min(TRACK_MAX_PX, max(TRACK_PX, MOVE_PX_S * dt))

    def update(self, t_ns: int, monsters: list[Any]) -> None:
        b = nearest(monsters, self.foot, self.gate_px(t_ns))
        if b is None:
            self.sightings.append(dcm.Sighting(t_ns, None))
            return
        self.foot = foot_of(b)
        self.last_box, self.last_seen_ns = b, t_ns
        self.sightings.append(
            dcm.Sighting(t_ns, (b.x0, b.y0, b.x1, b.y1), float(getattr(b, "score", 1.0)))
        )

    def gone(self, now_ns: int, since_ns: int | None) -> bool:
        """Seen AFTER ``since_ns`` (the first attack click), then unseen for GONE_FRAMES frames and
        GONE_S. A target the detector lost right after the click never counts as dead."""
        if since_ns is None or self.last_seen_ns is None or self.last_seen_ns <= since_ns:
            return False
        tail = 0
        for s in reversed(self.sightings):
            if s.box is not None:
                break
            tail += 1
        return tail >= GONE_FRAMES and (now_ns - self.last_seen_ns) / 1e9 >= GONE_S

    def still(self, now_ns: int) -> dict[str, Any] | None:
        """The last box, if it may be probed: seen within FRESH_S, and its feet moved less than
        STILL_PX since the sighting before it (taken at most STILL_GAP_S earlier). A probe on a
        stale or moving box hovers empty ground (the pilot); None means wait."""
        seen = [s for s in self.sightings if s.box is not None]
        if len(seen) < 2 or self.last_seen_ns is None:
            return None
        age = (now_ns - self.last_seen_ns) / 1e9
        a, b = seen[-2], seen[-1]
        gap = (b.t_ns - a.t_ns) / 1e9
        fa = ((a.box[0] + a.box[2]) / 2, a.box[3])
        fb = ((b.box[0] + b.box[2]) / 2, b.box[3])
        moved = float(np.hypot(fb[0] - fa[0], fb[1] - fa[1]))
        if age > FRESH_S or gap > STILL_GAP_S or moved >= STILL_PX:
            return None
        return {"age_ms": round(age * 1000), "moved_px": round(moved, 1),
                "gap_ms": round(gap * 1000)}  # fmt: skip


def in_ui(u: float, v: float, pad: float = UI_PAD, mask: Any = None) -> bool:
    """Over a UI region grown by ``pad`` (edges count). ``mask``: a ui_mask.UiMask read on the
    decision frame (the NPC dialog's cut-in while a dialog is open, Batt 2026-10-09); None = the
    client's static windows only (route_preview.UI_WINDOWS), exactly as before."""
    return (ui_mask.STATIC if mask is None else mask).window_at(u, v, pad) is not None


def runtime_obtained(weight_before: tuple[int, int] | None, weight_after: tuple[int, int] | None,
                     cue: bool) -> dict[str, Any]:  # fmt: skip
    """3.20 step 5: the weight readout rose (>= 1 step) OR the chat cue read "got"."""
    rose = (weight_before is not None and weight_after is not None
            and weight_after[0] > weight_before[0])  # fmt: skip
    return {"obtained": bool(rose or cue), "weight_rose": bool(rose), "cue": bool(cue)}


# --- the live parts -----------------------------------------------------------------------------


class Sampler(threading.Thread):
    """Detects units on every frame it can, on its own grab helper, until stopped."""

    def __init__(self, det: Any) -> None:
        super().__init__(daemon=True)
        self.det = det
        self.frames: list[tuple[int, list[Any]]] = []
        self.lock = threading.Lock()
        self.halt = threading.Event()
        self.error: str | None = None

    def run(self) -> None:
        screen = r.Screen()
        try:
            while not self.halt.is_set():
                t, img = screen.grab(*r.game_region())
                boxes = [b for b in self.det.detect(img) if b.cls == "monster"]
                with self.lock:
                    self.frames.append((t, boxes))
        except Exception as exc:  # noqa: BLE001 -- reported, never silent
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            screen.close()

    def since(self, k: int) -> list[tuple[int, list[Any]]]:
        with self.lock:
            return self.frames[k:]

    def stop(self) -> None:
        self.halt.set()
        self.join(timeout=10)


@dataclass
class Rig:
    agent: Any
    screen: Any
    pr: Any
    det: Any
    camera: Any
    gat: Any
    walkable: Any
    digits: Any  # the minimap digit templates (selfpos)
    glyphs: Any
    cues: dict[str, Any]
    hud: Any = None  # operator_hud.HudSender: DISPLAY ONLY (Batt 2026-10-09 ~19:30)


def hud(rig: Rig, line: str, boxes: Sequence[Any] = ()) -> None:
    """The operator HUD's decision log for loot@1 (Batt: "why I did not see bot action in the log"):
    a plain-words line and the target's box. Display only: it never decides, never stops a trial
    (operator_hud swallows every error)."""
    h = rig.hud
    if h is None:
        return
    with contextlib.suppress(Exception):
        h.note(line)
        h.send(boxes=[b for b in boxes if b is not None], force=True)


def _reads(hit: dict[str, Any]) -> str:
    return " ".join(f"{p[2]}{'/' + p[3] if p[3] else ''}" for p in hit.get("tried", [])) or "-"


def frame_bgr(rig: Rig) -> Any:
    return rig.screen.grab(*r.game_region())[1]


def weight_now(rig: Rig) -> tuple[int, int] | None:
    from poring_env import weight as wt

    reads = [wt.read_weight(frame_bgr(rig)[..., :3], rig.glyphs) for _ in range(2)]
    return wt.stable_value(reads)


def sword_click(rig: Rig, box: Any) -> dict[str, Any]:
    """One deliberate attack: a point on the target's box where the cursor reads SWORD twice."""
    tried = []
    for fx, fy, dv in ATTACK_POINTS:
        u = box.x0 + fx * (box.x1 - box.x0)
        v = box.y0 + fy * (box.y1 - box.y0) + dv
        if in_ui(u, v) or not rig.pr.park():
            continue
        rig.pr.hover(u, v)
        first = rig.pr.read(u, v)["shape"]
        again = rig.pr.read(u, v)["shape"] if first == "sword" else None
        tried.append([round(u, 1), round(v, 1), first, again])
        if first == "sword" and again == "sword":
            gx, gy, _, _ = r.game_region()
            t = r.ns()
            rig.agent.click(gx + round(u), gy + round(v))  # the DELIBERATE attack (kill phase)
            return {"clicked": True, "t": t, "at": [round(u, 1), round(v, 1)], "tried": tried}
    return {"clicked": False, "tried": tried}


def minimap_cell(rig: Rig, spot: Cell) -> dict[str, Any]:
    """The GM's cell from the minimap readout (poring_env.selfpos, T0; RDP-checked 2026-10-09): two
    equal reads on fresh frames, walkable, within PLAUSIBLE_CELLS of the spot. Nothing is typed."""
    from poring_env import selfpos

    reads = []
    for _ in range(2):
        got = selfpos.read_minimap(frame_bgr(rig)[..., :3], rig.digits)
        reads.append(got.xy)
        time.sleep(0.15)
    a, b = reads
    if a is None or a != b:
        return {"xy": None, "why": "unread" if a is None else "disagree", "reads": reads}
    x, y = a
    if not (0 <= y < rig.walkable.shape[0] and 0 <= x < rig.walkable.shape[1]) \
            or not rig.walkable[y, x]:  # fmt: skip
        return {"xy": None, "why": "not_walkable", "reads": reads}
    if max(abs(x - spot[0]), abs(y - spot[1])) > PLAUSIBLE_CELLS:
        return {"xy": None, "why": "implausible", "reads": reads}
    return {"xy": (x, y), "why": "ok", "reads": reads}


def kill(rig: Rig, spot: Cell, trial: dict[str, Any]) -> tuple[Track | None, Cell | None]:
    """Spawn, find, attack until it vanishes. Returns the track and the GM's cell (where@2)."""
    import bench

    # Plain, every trial: never varied to dodge the client's repeat counter (Batt's typing policy,
    # 2026-10-09 ~12:15). Four other lines stand between two @monster lines anyway.
    r.gm(rig.agent, rig.screen, f"@monster {PORING} 1")
    bench.close_chat(rig.agent, rig.screen)
    r.activate_client(rig.agent, rig.screen)
    sampler = Sampler(rig.det)
    sampler.start()
    try:
        time.sleep(SPAWN_WAIT_S)
        gm_feet = tuple(rig.camera.project(np.zeros((1, 2)), np.zeros(1))[0])
        t_find = r.ns()
        hit: tuple[int, Any] | None = None
        frames: list[tuple[int, list[Any]]] = []
        while hit is None and (r.ns() - t_find) / 1e9 <= FIND_S:
            frames = sampler.since(0)
            hit = find_spawn(frames, gm_feet)
            if hit is None:
                time.sleep(0.1)
        trial["find"] = {"frames": len(frames), "s": round((r.ns() - t_find) / 1e9, 2)}
        if hit is None:
            trial["found"] = "no_frames" if not frames else False
            return None, None
        trial["found"] = True
        idx, target = hit
        hud(rig, f"trial {trial['k']}: target found", [target])
        track = Track(foot_of(target))
        track.update(frames[idx][0], [target])
        k = idx + 1
        attacks: list[dict[str, Any]] = []
        here: Cell | None = None
        t_first: int | None = None
        while True:
            new = sampler.since(k)
            k += len(new)
            for t, boxes in new:
                track.update(t, boxes)
            now = r.ns()
            last_attack = attacks[-1]["t"] if attacks else None
            if track.gone(now, t_first):
                break
            if t_first is not None and (now - t_first) / 1e9 > KILL_S:
                trial["kill"] = "no_kill"
                return track, here
            if t_first is None and (now - t_find) / 1e9 > NO_CLICK_S:
                trial["kill"] = "no_sword" if trial.get("attack_tries") else "never_still"
                hud(rig, f"trial {trial['k']}: {trial['kill']} (no sword-gated click in 30 s)")
                return track, here
            again = last_attack is None or (now - last_attack) / 1e9 > REATTACK_S
            ready = track.still(now) if again else None
            if ready is not None:
                hit = sword_click(rig, track.last_box)
                hit["box"] = ready
                verdict = "ATTACK click" if hit["clicked"] else "no sword"
                hud(rig, f"probe {_reads(hit)} -> {verdict}", [track.last_box])
                trial.setdefault("attack_tries", []).append(hit)
                if hit["clicked"]:
                    attacks.append(hit)
                    t_first = t_first or hit["t"]
                elif t_first is None and len(trial["attack_tries"]) >= 6:
                    trial["kill"] = "no_sword"
                    return track, here
            fighting = t_first is not None and (now - t_first) / 1e9 > FIX_AFTER_S
            if "where" not in trial and fighting:
                got = minimap_cell(rig, spot)
                trial["where"] = got
                here = got["xy"]  # no fix: no guess (once more after the death, then no loot)
                continue
            time.sleep(0.05)
        trial["kill"] = "vanished"
        trial["attacks"] = [a["t"] for a in attacks]
        hud(rig, f"trial {trial['k']}: target gone from the pixels")
        if here is None:  # it died before the read, or that read failed: the GM stands still now
            got = minimap_cell(rig, spot)
            trial["where_after"] = got
            here = got["xy"]
        return track, here
    finally:
        sampler.stop()
        trial["sampler"] = {"frames": len(sampler.frames), "error": sampler.error}


def death_of(rig: Rig, track: Track, here: Cell) -> dcm.DeathCell:
    from poring_dataset import picking

    def cell_of(foot: tuple[float, float], _i: int) -> Cell | None:
        off = picking.pick_cells(rig.camera, rig.gat, here,
                                 np.array([[foot[0], foot[1] - FOOT_LIFT]]))[0]  # fmt: skip
        if abs(int(off[0])) > 1000:
            return None
        return (here[0] + int(off[0]), here[1] + int(off[1]))

    return dcm.death_cell(track.sightings, cell_of, gone_frames=GONE_FRAMES)


def loot(rig: Rig, here: Cell, dead: dcm.DeathCell, trial: dict[str, Any]) -> None:
    """3.20 step 4 + 5: the PICKUP hover-scan, the gates, one click, the runtime check."""
    assert dead.cell is not None and dead.gone_ns is not None
    w = w5.World(rig.camera, rig.gat, here)
    before_w = weight_now(rig)
    trial["weight_before"] = before_w
    scan: list[dict[str, Any]] = []
    trial["scan"] = scan
    for cell in dcm.scan_order(dead.cell, 1):
        if not w.walkable[cell[1], cell[0]]:
            scan.append({"cell": list(cell), "skip": "not_walkable"})
            continue
        u, v = (float(c) for c in w.project([cell])[0])
        if in_ui(u, v):
            scan.append({"cell": list(cell), "skip": "ui"})
            continue
        if not rig.pr.park():
            scan.append({"cell": list(cell), "skip": "stale_background"})
            continue
        rig.pr.hover(u, v)
        first = rig.pr.read(u, v)["shape"]
        again = rig.pr.read(u, v)["shape"] if first == "pickup" else None
        row: dict[str, Any] = {"cell": list(cell), "at": [round(u, 1), round(v, 1)],
                               "shape": first, "again": again}  # fmt: skip
        scan.append(row)
        hud(rig, f"scan {cell[0]},{cell[1]}: {first}{'/' + again if again else ''}")
        if first != "pickup" or again != "pickup":
            continue
        ok, env = w11.unit_check(rig.pr, w, u, v)
        row["envelope"] = env
        if not ok:
            row["refused"] = "unit_envelope"
            continue
        before = frame_bgr(rig)
        gx, gy, _, _ = r.game_region()
        t_click = r.ns()
        rig.agent.click(gx + round(u), gy + round(v))  # the LOOT click
        trial["pickup_click"] = {
            "t": t_click, "cell": list(cell), "at": [round(u, 1), round(v, 1)],
            "after_death_s": round((t_click - dead.gone_ns) / 1e9, 2),
        }  # fmt: skip
        hud(rig, f"PICKUP click on {cell[0]},{cell[1]}")
        check(rig, before, before_w, t_click, trial)
        hud(rig, f"runtime: {trial.get('runtime')}")
        return
    trial["pickup_click"] = None


def check(rig: Rig, before: Any, before_w: tuple[int, int] | None, t_click: int,
          trial: dict[str, Any]) -> None:  # fmt: skip
    """CHECK_S after the click: the weight (two equal reads) and the chat cue, every ~0.3 s."""
    cue, after_w, cue_read = False, None, None
    rgb0 = before[..., 2::-1]
    while (r.ns() - t_click) / 1e9 < CHECK_S:
        img = frame_bgr(rig)
        cue_read = chat_cue.check(rgb0, img[..., 2::-1], rig.cues)
        cue = cue or bool(cue_read["cue"])
        w_now = weight_now(rig)
        if w_now is not None:
            after_w = w_now
        got = runtime_obtained(before_w, after_w, cue)
        if got["weight_rose"] and cue:
            break
        time.sleep(0.3)
    trial["weight_after"] = after_w
    trial["cue_read"] = cue_read
    trial["runtime"] = runtime_obtained(before_w, after_w, cue)


def rig_up(agent: Any, screen: Any) -> Rig:
    import unit_detector

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos
    from poring_env import weight as wt

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])  # prt_fild08 is outdoor
    det = unit_detector.UnitDetector()  # fails closed: no detector, no run
    w11.UNITS["detector"] = det
    w11.UNITS["ms_per_cell"] = w11.map_ms_per_cell(MAP)
    pr = w10.Prober9(agent, screen, w6.CursorRefs.load(CURSOR_REFS_V3))
    glyphs = wt.load_weight_glyphs(r.ROOT / wt.DEFAULT_TEMPLATES)
    import operator_hud

    sender = operator_hud.HudSender(agent, region=r.game_region(), desktop=r.desktop(), label=RULE,
                                    ttl_ms=operator_hud.RULE_TTL_MS)  # fmt: skip
    return Rig(agent, screen, pr, det, camera, gat, gat.walkable(),
               selfpos.load_digit_templates(), glyphs, chat_cue.load_cues(), sender)  # fmt: skip


def run(mode: str, n: int, seed: int) -> int:
    import bench

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    plan = spots(gat.walkable(), seed, n)
    if len(plan) < n:
        raise SystemExit(f"only {len(plan)} spots of {n} fit the region")
    sid = new_session_id(f"loot1-{mode}")
    log = DemoLog(sid)
    lock = record_session.read_lock(r.ROOT / "state")
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
              account="gm", mode=mode, n=n, seed=seed, map=MAP, spots=[list(s) for s in plan],
              gone_frames=GONE_FRAMES, gone_s=GONE_S, check_s=CHECK_S, budget_s=BUDGET_S,
              too_slow_s=TOO_SLOW_S)  # fmt: skip
    print(json.dumps({"session": sid, "rule": RULE, "mode": mode, "n": n, "seed": seed}),
          flush=True)  # fmt: skip
    t_first = r.ns()
    trials: list[dict[str, Any]] = []
    with r.session(f"rule:{RULE}") as (agent, screen):
        rig = rig_up(agent, screen)
        try:
            for k, spot in enumerate(plan):
                trial: dict[str, Any] = {"k": k, "spot": list(spot), "t_start": r.ns()}
                trials.append(trial)
                for cmd in ("@killmonster2", "@alive", "@heal", f"@warp {MAP} {spot[0]} {spot[1]}"):
                    r.gm(agent, screen, cmd)
                time.sleep(rr.SCENE_ENTRY_S)
                # the GM's FIXED TEST STATE (Batt 2026-10-09 ~16:00): a kill levels the GM up, so
                # every trial starts at Base / Job Lv 1, checked from pixels and recorded
                trial["gm_state"] = gm_state.ensure_fixed(agent, screen, why=f"{RULE}:trial{k}",
                                                          out_dir=log.dir / "gm_state")  # fmt: skip
                hud(rig, f"trial {k}: spot {spot[0]},{spot[1]} ({mode})")
                track, here = kill(rig, spot, trial)
                if track is None or trial.get("kill") != "vanished" or here is None:
                    trial["t_end"] = r.ns()
                    print(json.dumps({k_: trial.get(k_) for k_ in ("k", "found", "kill")}),
                          flush=True)  # fmt: skip
                    continue
                dead = death_of(rig, track, here)
                hud(rig, f"death cell {dead.cell} ({dead.reason})")
                trial["here"] = list(here)
                trial["death"] = {
                    "cell": None if dead.cell is None else list(dead.cell),
                    "reason": dead.reason, "confidence": round(dead.confidence, 3),
                    "last_seen_ns": dead.last_seen_ns, "gone_ns": dead.gone_ns,
                    "cells": [None if c is None else list(c) for c in dead.cells],
                }  # fmt: skip
                if mode == "run" and dead.cell is not None:
                    loot(rig, here, dead, trial)
                trial["t_end"] = r.ns()
                print(json.dumps({k_: trial.get(k_) for k_ in
                                  ("k", "kill", "death", "pickup_click", "runtime")},
                                 default=str), flush=True)  # fmt: skip
        finally:
            r.gm(agent, screen, "@killmonster2")
            bench.close_chat(agent, screen)
            rig.det.close()
            if rig.hud is not None:
                rig.hud.clear()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "trials.json").write_text(json.dumps(trials, default=str))
    log.finish(packet_events=len(events), packet_anchor=anchor, trials=len(trials))
    print(json.dumps({"session": sid, "trials": len(trials), "dir": str(log.dir)}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("mode", choices=("p3", "run"))
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    a = ap.parse_args()
    for p in (CURSOR_REFS_V3, chat_cue.CUES):
        if not p.exists():
            raise SystemExit(f"{p} missing (design-time calibration)")
    return run(a.mode, a.n, a.seed)


if __name__ == "__main__":
    sys.exit(main())
