#!/usr/bin/env python3
"""walk@17 item 5: the TARGETED NPC-click test (docs/planning/npc-click-test.md; PROPOSED, built
offline, NOT RUN). Batt 2026-10-09 ~15:20 / ~15:50 / ~16:10 / ~16:15.

    npc_click_test.py plan  --map M --seed S [--npcs K]     OFFLINE: the probe / click plan (JSON)
    npc_click_test.py probe --map M --seed S [--npcs K]     hover only: the cursor map around NPCs
    npc_click_test.py click --map M --seed S [--npcs K] [--resume SESSION]
                                                            deliberate WALK-gated clicks beside NPCs

The NPCs come MECHANICALLY from L3 at run time (npc_noclick.load_l3_npcs: data/kb, never
committed): the K densest (most other L3 NPCs within DENSE_R cells) whose sprite is drawn. Each NPC
gets STANDS stand cells 3-5 cells away (seeded), from which:
- PROBE: points on the NPC's sprite (its projected feet and up it), its edges, below its feet, and
  the pick-safe point of every cell 1-2 away; each hovered REPS times (two motions, after a fresh
  park), read as Prober9 reads (walk@9's reader, the v3 references), plus a TIMED SERIES of
  READ_GRABS grabs (animation / codec refinement), the best reference's REAL colour score, the
  crops (crops/*.npz: client pixels, /dev/shm only) and the detector's boxes on the parked frame.
  Nothing is clicked.
- CLICK: cells 1-2 from the NPC, each clicked ONLY through cursor_gate.gated_click (WALK read twice:
  the walk rules' own gate), at the cell's tier-A pick-safe point (walk@12's points). The L3
  no-click layer's verdict is RECORDED, never applied (the arms are judged offline). After every
  click, the DIALOG POLICY (Batt's item 6): T2 (poring_env.npc_dialog) on two fresh frames; none ->
  go on; a dialog showing CLOSE on both -> Enter, then the windows gone on two frames; ANYTHING
  ELSE -> STOP FOR A PERSON (exit 7, the dialog left as it is; --resume continues the session).
GM commands only through ro_agent.gm (the typing guard applies): @warp to a known stand cell, never
/where (Batt's typing policy). Consecutive @warp lines always differ (the stands alternate).
Pixels in, input out: packets are never read here; npc_click_score.py judges the session offline.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import npc_click_score as ncs  # noqa: E402
import npc_noclick as nc  # noqa: E402

RULE = "npc-click@1"
PROBE_RULE, CLICK_RULE = ncs.PROBE, ncs.CLICK
Cell = tuple[int, int]
DENSE_R = 8  # density: other L3 NPCs within this many cells
NPCS_K = 6
STANDS = 2
STAND_RANGE = (3, 5)
REPS = 2  # each probe point hovered this many times (seeded order: the repeats apart in time)
READ_GRABS = 6  # the timed series: Prober9's 3 grabs (0.1 s apart) + 3 more
READ_GAP_S = 0.1
# ring 1: every walkable cell from BOTH stands; rings 2 and 3: this many each, stands alternating
# (ring 3 reaches past the PROVISIONAL footprint: the clicks the L3 layer would ALLOW)
RING2_CLICKS = RING3_CLICKS = 8
RING3_PROBES = ((3, 0), (-3, 0), (0, 3), (0, -3), (3, 3), (-3, 3), (3, -3), (-3, -3))
CONTROL_APART = 8  # the CONTROL spot: plain floor, every L3 NPC at least this far (Chebyshev)
CONTROL_SEARCH = 20  # ... within this of the pre-registered spot (or the first chosen NPC)
# the sprite: (du, dv) px from the projected feet; the vertical line, the edges, below the feet
SPRITE_POINTS = tuple((0.0, -float(d)) for d in range(0, 113, 14)) + tuple(
    (float(s * du), -float(dv)) for du in (17, 34, 51) for dv in (14, 42, 70) for s in (-1, 1)
) + ((0.0, 12.0), (0.0, 24.0), (-34.0, 12.0), (34.0, 12.0))  # fmt: skip
MAX_SPRITE_UP = 112.0  # every sprite point's screen extent above the feet (stand choice)
EXIT_STOP_PERSON = 7  # a dialog the policy may not close: a person closes it, then --resume
DIALOG_WAIT_S = 1.2  # after a click, before the first T2 frame
CLOSE_GONE_TRIES = 6


# --- the plan (pure) ----------------------------------------------------------------------------


def cheb(a: Sequence[int], b: Sequence[int]) -> int:
    return max(abs(int(a[0]) - int(b[0])), abs(int(a[1]) - int(b[1])))


def _walkable(walkable: Any, c: Cell) -> bool:
    return 0 <= c[1] < walkable.shape[0] and 0 <= c[0] < walkable.shape[1] and bool(
        walkable[c[1], c[0]])  # fmt: skip


def dense_npcs(npcs: Sequence[nc.StaticNpc], k: int = NPCS_K,
               radius: int = DENSE_R) -> list[nc.StaticNpc]:  # fmt: skip
    """The ``k`` NPCs with the most other NPCs within ``radius`` (Chebyshev), ties by cell."""

    def density(n: nc.StaticNpc) -> int:
        return sum(1 for o in npcs if o is not n and cheb(o.cell, n.cell) <= radius)

    return sorted(npcs, key=lambda n: (-density(n), n.cell))[:k]


def in_view(camera: Any, gat: Any, stand: Cell, cell: Cell, up: float = MAX_SPRITE_UP) -> bool:
    """The NPC's feet AND its sprite's top (``up`` px above) inside the work zone from ``stand``."""
    import work_zone as wz

    ((u, v),) = ncs.project_feet(camera, gat, stand, [cell])
    return bool(wz.in_work_zone(u, v) and wz.in_work_zone(u, v - up))


def stand_cells(walkable: Any, camera: Any, gat: Any, npc: Cell, others: Sequence[Cell],
                rng: random.Random, n: int = STANDS) -> list[Cell]:  # fmt: skip
    """``n`` walkable stands 3-5 cells from the NPC (Chebyshev), never next to another NPC, the
    NPC's sprite in view; seeded, the second from a different direction than the first."""
    lo, hi = STAND_RANGE
    cands = [(x, y) for y in range(npc[1] - hi, npc[1] + hi + 1)
             for x in range(npc[0] - hi, npc[0] + hi + 1)
             if lo <= cheb((x, y), npc) <= hi and _walkable(walkable, (x, y))
             and all(cheb((x, y), o) >= 2 for o in others)
             and in_view(camera, gat, (x, y), npc)]  # fmt: skip
    rng.shuffle(cands)
    out: list[Cell] = []
    for c in cands:
        side = (np.sign(c[0] - npc[0]), np.sign(c[1] - npc[1]))
        if all((np.sign(o[0] - npc[0]), np.sign(o[1] - npc[1])) != side for o in out):
            out.append(c)
        if len(out) == n:
            break
    return out


def probe_points(camera: Any, gat: Any, stand: Cell, npc: Cell) -> list[dict[str, Any]]:
    """The probe points from ``stand``: SPRITE_POINTS around the projected feet, then the tier-A
    pick-safe point of every cell 1-2 from the NPC and of RING3_PROBES (not the stand); only
    work-zone pixels."""
    import work_zone as wz

    from poring_dataset import picking

    ((fu, fv),) = ncs.project_feet(camera, gat, stand, [npc])
    out: list[dict[str, Any]] = []
    for du, dv in SPRITE_POINTS:
        u, v = fu + du, fv + dv
        if wz.in_work_zone(u, v):
            out.append({"kind": "sprite", "offset": [du, dv], "at": [round(u, 1), round(v, 1)]})
    near = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if (dx, dy) != (0, 0)]
    for dx, dy in [*near, *RING3_PROBES]:
        c = (npc[0] + dx, npc[1] + dy)
        if c != stand:
            rel = (c[0] - stand[0], c[1] - stand[1])
            pts = picking.safe_points(camera, gat, stand, rel, margin=6.0, grid=2.0, k=1)
            if pts and wz.in_work_zone(*pts[0]):
                u, v = pts[0]
                out.append({"kind": "cell", "offset": [dx, dy], "cell": list(c),
                            "at": [round(u, 1), round(v, 1)]})  # fmt: skip
    return out


def ring_cells(walkable: Any, npc: Cell, ring: int, npc_cells: Sequence[Cell]) -> list[Cell]:
    """The walkable cells at Chebyshev ``ring`` from the NPC that are no NPC's cell."""
    cs = [(npc[0] + dx, npc[1] + dy) for dy in range(-ring, ring + 1)
          for dx in range(-ring, ring + 1) if max(abs(dx), abs(dy)) == ring]  # fmt: skip
    return [c for c in cs if _walkable(walkable, c) and c not in npc_cells]


def npc_clicks(walkable: Any, npc: Cell, stands: Sequence[Cell], npc_cells: Sequence[Cell],
               rng: random.Random, ring2: int = RING2_CLICKS, ring3: int = RING3_CLICKS
               ) -> list[tuple[Cell, Cell]]:  # fmt: skip
    """(stand, cell) pairs for one NPC: every ring-1 cell from each of the two stands, then
    ``ring2`` / ``ring3`` seeded ring-2 / ring-3 cells split between the stands; ordered so the
    stands ALTERNATE (each click types its @warp, and the guard refuses identical lines in a row),
    the pairs shuffled within each stand."""
    a, b = stands[0], stands[1]
    r1 = [c for c in ring_cells(walkable, npc, 1, npc_cells) if c not in stands]
    far: list[Cell] = []
    for ring, n in ((2, ring2), (3, ring3)):
        cs = [c for c in ring_cells(walkable, npc, ring, npc_cells) if c not in stands]
        rng.shuffle(cs)
        far += cs[: n - n % 2]
    per = {a: [*r1, *far[0::2]], b: [*r1, *far[1::2]]}
    for v in per.values():
        rng.shuffle(v)
    n = min(len(per[a]), len(per[b]))
    out: list[tuple[Cell, Cell]] = []
    for i in range(n):
        out += [(a, per[a][i]), (b, per[b][i])]
    return out


def make_plan(map_name: str, npcs: Sequence[nc.StaticNpc], walkable: Any, camera: Any, gat: Any,
              seed: int, k: int = NPCS_K, reps: int = REPS, near: Cell | None = None,
              near_radius: int = 12) -> dict[str, Any]:  # fmt: skip
    """The whole plan: the chosen NPCs, their stands, the probe sequence (each point ``reps``
    times, seeded order per stand) and the click sequence (stands alternating per click).
    ``near``: a PRE-REGISTERED spot; only NPCs within ``near_radius`` of it are candidates."""
    rng = random.Random(seed)
    cells = [n.cell for n in npcs]
    pool = [n for n in npcs if near is None or cheb(n.cell, near) <= near_radius]
    chosen: list[dict[str, Any]] = []
    for n in dense_npcs(pool, k):
        others = [c for c in cells if c != n.cell]
        st = stand_cells(walkable, camera, gat, n.cell, others, rng)
        if len(st) < STANDS:  # two stands: the click arm alternates them (no repeated @warp)
            continue
        chosen.append({"npc": n.key, "cell": list(n.cell), "sprite": n.sprite,
                       "stands": [list(s) for s in st]})  # fmt: skip
    probes: list[dict[str, Any]] = []
    clicks: list[dict[str, Any]] = []
    for c in chosen:
        npc = (c["cell"][0], c["cell"][1])
        for s in c["stands"]:
            pts = probe_points(camera, gat, (s[0], s[1]), npc)
            seq = [dict(p, rep=r) for r in range(reps) for p in pts]
            rng.shuffle(seq)
            probes += [{"npc": c["npc"], "npc_cell": c["cell"], "stand": s, **p} for p in seq]
        stands = [(s[0], s[1]) for s in c["stands"]]
        pairs = npc_clicks(walkable, npc, stands, cells, rng)
        if pairs and clicks and list(pairs[0][0]) == clicks[-1]["stand"]:
            pairs = npc_clicks(walkable, npc, stands[::-1], cells, rng)  # start on the other one
        for stand, cell in pairs:
            clicks.append({"npc": c["npc"], "npc_cell": c["cell"], "stand": list(stand),
                           "cell": list(cell)})  # fmt: skip
    if not no_identical_in_a_row(click_warps(map_name, clicks)):
        raise SystemExit("the click plan would type the same @warp twice in a row")
    control = control_stand(walkable, cells, near or (tuple(chosen[0]["cell"]) if chosen
                                                      else None), rng)  # fmt: skip
    if control is not None:  # the registration / colour BASELINE: the walk cursor on plain floor
        centre = (control[0], control[1] + 3)
        pts = [dict(p, kind="control") for p in probe_points(camera, gat, control, centre)
               if p["kind"] == "cell"]  # fmt: skip
        seq = [dict(p, rep=r) for r in range(reps) for p in pts]
        rng.shuffle(seq)
        probes += [{"npc": "control", "npc_cell": list(centre), "stand": list(control), **p}
                   for p in seq]  # fmt: skip
    return {"map": map_name, "seed": seed, "npcs": chosen, "probes": probes, "clicks": clicks,
            "control": None if control is None else list(control)}  # fmt: skip


def control_stand(walkable: Any, npc_cells: Sequence[Cell], around: Cell | None,
                  rng: random.Random) -> Cell | None:  # fmt: skip
    """A seeded walkable cell within CONTROL_SEARCH of ``around`` with every L3 NPC at least
    CONTROL_APART away (and its probe ring walkable enough to read the walk cursor)."""
    if around is None:
        return None
    r = CONTROL_SEARCH
    cands = [(x, y) for y in range(around[1] - r, around[1] + r + 1)
             for x in range(around[0] - r, around[0] + r + 1)
             if _walkable(walkable, (x, y)) and _walkable(walkable, (x, y + 3))
             and all(cheb((x, y), c) >= CONTROL_APART for c in npc_cells)]  # fmt: skip
    return rng.choice(cands) if cands else None


def warp_lines(map_name: str, stands: Sequence[Sequence[int]]) -> list[str]:
    """The @warp lines a sequence of stands types: one per CHANGE of stand."""
    out: list[str] = []
    for s in stands:
        line = f"@warp {map_name} {s[0]} {s[1]}"
        if not out or out[-1] != line:
            out.append(line)
    return out


def click_warps(map_name: str, clicks: Sequence[dict[str, Any]]) -> list[str]:
    """The click arm warps before EVERY click (the last click may have walked)."""
    return [f"@warp {map_name} {c['stand'][0]} {c['stand'][1]}" for c in clicks]


def no_identical_in_a_row(lines: Sequence[str]) -> bool:
    """The typing guard refuses a 3rd identical line in a row; the plan never types even 2."""
    return all(a != b for a, b in zip(lines, lines[1:], strict=False))


# --- the dialog policy after a click (pure; Batt's item 6) ---------------------------------------


def dialog_action(a: Any, b: Any) -> str:
    """Two fresh T2 states (poring_env.npc_dialog.NpcUiState) -> "none" (no window on both),
    "close" (a dialog showing CLOSE, no menu, on both) or "stop:<why>" (a person closes it)."""
    if not (a.ok and b.ok):
        return f"stop:unread:{a.reason if not a.ok else b.reason}"
    if a.signature() != b.signature():
        return "stop:frames_disagree"
    if a.gone:
        return "none"
    if a.menu is not None:
        return "stop:menu"
    if a.dialog is not None and a.dialog.button == "close":
        return "close"
    return f"stop:dialog_{a.dialog.button if a.dialog is not None else 'unknown'}"


# --- live (never run by this branch) -----------------------------------------------------------


def read_series(pr: Any, u: float, v: float, n: int = READ_GRABS, gap: float = READ_GAP_S
                ) -> tuple[list[dict[str, Any]], dict[str, Any]]:  # fmt: skip
    """Prober9.read's grab, mask and match (walk@9's reader: animated pixels ignored), ``n`` times
    ``gap`` apart with no motion, each with the best reference's real colour; and the arrays."""
    import ro_agent as r
    import rule_run as rr
    import walk6 as w6

    gx, gy, _, _ = r.game_region()
    px, py = gx + round(u), gy + round(v)
    b = pr._crop(pr.background, u, v, 32)
    anim = pr._crop(pr.animated[..., None].astype(np.uint8), u, v, 32)[..., 0] > 0
    static_green = w6.green(pr._crop(pr.background, u, v, 60))
    reads: list[dict[str, Any]] = []
    aa, mm, big0 = [], [], None
    for g in range(n):
        if g:
            time.sleep(gap)
        big = pr.screen.grab(px - 60, py - 60, 120, 120)[1][..., :3]
        a = big[28:92, 28:92]
        mask = w6.cursor_mask(a, np.where(anim[..., None], a, b))
        ex = ncs.explain(pr.refs, a, mask)
        rd = {"g": g, "t_ns": r.ns(), "shape": ex["shape"], "iou": ex.get("iou"),
              "col": ex.get("col"), "best": ex.get("best"), "mask_px": int(mask.sum())}  # fmt: skip
        if g == 0:
            big0 = big
            fresh = np.where(static_green[..., None], 0, big).astype(big.dtype)
            comps = rr.green_components(fresh)
            rd["comps"] = [(x + px - 60 - gx, y + py - 60 - gy) for x, y, _ in comps]
            rd["marker_px"] = sum(c for *_, c in comps)
        reads.append(rd)
        aa.append(a)
        mm.append(mask)
    arrays = {"a": aa[0], "mask": mm[0], "a_series": np.stack(aa), "mask_series": np.stack(mm),
              "b": b, "anim": anim, "big": big0}  # fmt: skip
    return reads, arrays


class Session:
    """The session directory: demo.jsonl records, crops/, frames/, detections.jsonl, packets."""

    def __init__(self, kind: str, map_name: str, resume: str | None = None) -> None:
        import ro_agent as r

        from poring_env.demo import DemoLog, new_session_id

        self.sid = resume or new_session_id(f"npc-click-{kind}-{map_name}")
        self.log = DemoLog(self.sid)
        self.dir = self.log.dir
        (self.dir / "crops").mkdir(exist_ok=True)
        (self.dir / "frames").mkdir(exist_ok=True)
        self.t_first = r.ns()
        self.k = len(list((self.dir / "crops").glob("*.npz")))

    def crop(self, arrays: dict[str, Any]) -> str:
        name = f"crops/{self.k:05d}.npz"
        np.savez_compressed(self.dir / name, **{k: v for k, v in arrays.items() if v is not None})
        self.k += 1
        return name

    def done_clicks(self) -> set[int]:
        return {int(rec.action.intended.note.split()[1]) for rec in self.log.records()
                if rec.rule == CLICK_RULE and rec.action.intended.note}  # fmt: skip

    def append(self, rule: str, t0: int, action_type: Any, points: list[tuple[float, float]],
               intended: dict[str, Any], cue: str, evidence: dict[str, Any],
               map_name: str) -> None:  # fmt: skip
        import ro_agent as r

        from poring_env.demo import Action, DemoRecord, Intended, Outcome

        self.log.append(DemoRecord(
            session=self.sid, actor=f"rule:{RULE}", t_mono_ns=t0, t_done_ns=r.ns(),
            action=Action(type=action_type, points=points, intended=Intended(**intended)),
            cue=cue, rule=rule, scene=f"town:{map_name}",
            outcome=Outcome(evidence=evidence)))  # fmt: skip


def _ui_clear(io: Any) -> str:
    """Batt's item 6: judge the client's UI from pixels (T2, two fresh frames) -> dialog_action."""
    a, _ = io.observe()
    b, _ = io.observe()
    return dialog_action(a, b)


def run(
    kind: str,
    map_name: str,
    seed: int,
    k: int,
    resume: str | None,
    near: Cell | None = None,
    near_radius: int = 12,
    reps: int = REPS,
) -> int:
    import bench
    import cursor_gate
    import record_session
    import ro_agent as r
    import rule_run as rr
    import talk1
    import unit_detector
    import walk5 as w5

    from poring_env import npc_dialog as nd

    camera, gat = ncs.load_map(map_name)
    npcs, cov = nc.load_l3_npcs(map_name)
    plan = make_plan(
        map_name, npcs, gat.walkable(), camera, gat, seed, k, reps, near=near,
        near_radius=near_radius,
    )  # fmt: skip
    if not plan["npcs"]:
        raise SystemExit(f"no L3 NPC with two stands on {map_name} (coverage {cov})")
    layer = nc.NoClickLayer(npcs)
    templates = nd.load_templates(talk1.TEMPLATES)  # T2: the dialog policy needs it (fails closed)
    missing = [*templates.missing, *([] if nd.CLOSE in templates.images else [nd.CLOSE])]
    if missing:
        raise SystemExit(f"T2 templates missing {missing}: talk_calibrate.py cut (design time)")
    lock = record_session.read_lock(r.ROOT / "state")
    ses = Session(kind, map_name, resume)
    ses.log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena", rule=RULE,
                  mode=kind, map=map_name, seed=seed, near=near, npcs=plan["npcs"],
                  l3_coverage=cov,
                  footprint=nc.PROVISIONAL.source, read_grabs=READ_GRABS, reps=reps,
                  account="gm")  # fmt: skip
    # the packets at the end cover the WHOLE session, a resumed one included (the first t0 wins)
    ses.t_first = int(json.loads((ses.dir / "manifest.json").read_text())["t0_mono_ns"])
    det = unit_detector.UnitDetector() if kind == "probe" else None
    if det is not None:
        det.log_path = ses.dir / "detections.jsonl"
    ended, code = "complete", 0
    with r.session(f"rule:{RULE}") as (agent, screen):
        io = talk1.LiveIo(agent, screen, templates)
        if (why := _ui_clear(io)) != "none":
            raise SystemExit(f"the client's UI is not clear before the run ({why}): a person first")
        pr = cursor_gate.prober(agent, screen)
        here: list[int] | None = None
        first = True

        def go(stand: Sequence[int]) -> None:
            nonlocal here, first
            if here == list(stand):
                return
            r.gm(agent, screen, f"@warp {map_name} {stand[0]} {stand[1]}")
            time.sleep(rr.SCENE_ENTRY_S if first else rr.WARP_SETTLE_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            here, first = list(stand), False

        try:
            if kind == "probe":
                banked: set[tuple[int, int]] = set()
                for j, p in enumerate(plan["probes"]):
                    go(p["stand"])
                    w = w5.World(camera, gat, (p["stand"][0], p["stand"][1]))
                    if not pr.park():
                        continue
                    t0 = r.ns()
                    if tuple(p["stand"]) not in banked:  # one parked frame per stand: labels v2
                        banked.add(tuple(p["stand"]))
                        name = f"stand-{len(banked):03d}-{t0}.png"
                        r.to_png(pr.background, ses.dir / "frames" / name)
                    boxes, batch = [], None
                    if det is not None:
                        boxes = det.detect(pr.background)
                        batch = sum(1 for _ in (ses.dir / "detections.jsonl").open()) - 1
                    pr.hover(*p["at"])
                    reads, arrays = read_series(pr, *p["at"])
                    v = ncs.verdict(reads)
                    ev = {**p, "reads": reads, "verdict": v, "crop": ses.crop(arrays),
                          "det_batch": batch, "det_boxes": len(boxes),
                          "l3": layer.refuse_point(w, *p["at"])}  # fmt: skip
                    ses.append(
                        PROBE_RULE,
                        t0,
                        "other",
                        [tuple(p["at"])],
                        {
                            "kind": "npc",
                            "cell": tuple(p["npc_cell"]),
                            "approx_px": tuple(p["at"]),
                            "note": f"probe {j}",
                        },
                        "npc-click probe: hover only, never clicked",
                        ev,
                        map_name,
                    )
            else:
                done = ses.done_clicks()
                for j, c in enumerate(plan["clicks"]):
                    if j in done:
                        continue
                    here = None  # the click arm re-places the GM before EVERY click
                    go(c["stand"])
                    w = w5.World(camera, gat, (c["stand"][0], c["stand"][1]))
                    rel = (c["cell"][0] - c["stand"][0], c["cell"][1] - c["stand"][1])
                    import work_zone as wz

                    from poring_dataset import picking

                    pts = [
                        q
                        for q in picking.safe_points(
                            camera, gat, tuple(c["stand"]), rel, margin=6.0, k=20
                        )
                        if wz.in_work_zone(*q)
                    ]  # walk@12's tier-A points, work zone only
                    t0 = r.ns()
                    if not pts:
                        gate: dict[str, Any] = {"clicked": False, "why": "no_safe_point"}
                        at = None
                    else:
                        at = pts[0]
                        snap = screen.grab(*r.game_region())[1]
                        r.to_png(snap, ses.dir / "frames" / f"click-{j:04d}-{t0}.png")
                        gate = cursor_gate.gated_click(pr, at[0], at[1])  # WALK read twice
                    dialog: dict[str, Any] = {"action": "none"}
                    if gate.get("clicked"):
                        time.sleep(DIALOG_WAIT_S)
                        io.last_action = int(gate["t_click"])
                        io.parked = False
                        act = _ui_clear(io)
                        dialog = {"action": act}
                        if act == "close":
                            r.activate_client(agent, screen)
                            agent.keys("Enter")
                            io.last_action, io.parked = r.ns(), False
                            gone = any(_ui_clear(io) == "none" for _ in range(CLOSE_GONE_TRIES))
                            dialog["closed"] = gone
                            if not gone:
                                dialog["action"] = "stop:close_failed"
                    ev = {**c, "at": None if at is None else [round(at[0], 1), round(at[1], 1)],
                          "gate": gate, "dialog": dialog,
                          "l3": None if at is None else layer.refuse_point(w, *at)}  # fmt: skip
                    ses.append(
                        CLICK_RULE,
                        t0,
                        "walk",
                        [] if at is None else [(float(at[0]), float(at[1]))],
                        {"kind": "cell", "cell": tuple(c["cell"]), "note": f"click {j}"},
                        "npc-click: a WALK-gated click beside an NPC",
                        ev,
                        map_name,
                    )
                    if str(dialog["action"]).startswith("stop"):
                        ended, code = f"stopped_for_person:{dialog['action']}", EXIT_STOP_PERSON
                        print(json.dumps({"STOP": "a dialog the policy may not close is open: a "
                                          "person closes it, then --resume " + ses.sid,
                                          "why": dialog["action"]}), flush=True)  # fmt: skip
                        break
        finally:
            if det is not None:
                det.close()
            events, anchor = record_session.write_packets(ses.dir, ses.t_first, r.ns())
            ses.log.finish(ended=ended, packet_events=len(events), packet_anchor=anchor)
    print(json.dumps({"session": ses.sid, "ended": ended}))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("plan", "probe", "click"))
    ap.add_argument("--map", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--npcs", type=int, default=NPCS_K)
    ap.add_argument("--reps", type=int, default=REPS, help="hovers per probe point (pilot: 1)")
    ap.add_argument("--near", help="X,Y: the pre-registered spot (NPCs within --near-radius)")
    ap.add_argument("--near-radius", type=int, default=12)
    ap.add_argument("--resume", help="a stopped click session's id: continue its plan")
    a = ap.parse_args()
    near = None if not a.near else (int(a.near.split(",")[0]), int(a.near.split(",")[1]))
    if a.mode == "plan":
        camera, gat = ncs.load_map(a.map)
        npcs, cov = nc.load_l3_npcs(a.map)
        plan = make_plan(
            a.map,
            npcs,
            gat.walkable(),
            camera,
            gat,
            a.seed,
            a.npcs,
            near=near,
            near_radius=a.near_radius,
        )
        lines = warp_lines(a.map, [p["stand"] for p in plan["probes"]])
        print(json.dumps({"coverage": cov, "npcs": plan["npcs"], "probes": len(plan["probes"]),
                          "clicks": len(plan["clicks"]), "probe_warps": len(lines),
                          "click_warps_ok": no_identical_in_a_row(click_warps(a.map,
                                                                              plan["clicks"]))},
                         indent=1))  # fmt: skip
        return 0
    return run(a.mode, a.map, a.seed, a.npcs, a.resume, near, a.near_radius, a.reps)


if __name__ == "__main__":
    sys.exit(main())
