#!/usr/bin/env python3
"""WHY dungeon_hunt's walk cursor reads UNKNOWN on gef_fild10 (2026-10-26; the measurement behind
docs/planning/gef10-cursor-unknown.md). OFFLINE only: banked session files and recordings; nothing
here reaches a runner.

    cursor_unknown.py events TAG [TAG ...]       the walk decisions vs the GM's motion (packets),
                                                 the monsters at the target, the trust estimate
    cursor_unknown.py frames TAG [TAG ...] [--per-run N]
                                                 the recording's frames while the pointer rests
                                                 at a walk decision's hover point: the cursor's
                                                 recalls there (live WALK subset, full WALK set),
                                                 the no-entry ring's red, an arrow drawn off it
    cursor_unknown.py loop                       Batt's loop vs the NPCs and the delegated zones

A TAG names a gef_fild10 Rogue run (a2 ... = /dev/shm/poring-lab-demo/*-dungeon-rogue-gef_fild10-
B-<TAG>; its recording /mnt/poring-lab-datasets/*-rdp-rogue-<TAG>, or /dev/shm/poring-lab-rec
while unshipped). The detector's round-2 TEST2 recordings (a9, a10, a11, any w3) are REFUSED by
name (gef10-eval.md amendment R2); their events are not read either.

DEFINITIONS (written before the split was counted, 2026-10-26 ~11:2x ICT):
- a WALK DECISION is a runner "walk" event (clicked, or refused with why "cursor <verdict>");
- its READ START is the event time minus READ_UNKNOWN_S (a refused read ran its whole 0.35-s
  window, then one red-pixel crop) or minus READ_CLICK_S (a clicked one: the first CLEAR read, then
  the 0.07-s click);
- the MOTION STATE at the read start, from the packets (flow_judge.gm_track: our self_moves at
  150 ms a cell): "moving" (the server walk is under way), else the time since the server walk
  ended (frames show it ~0.45 s later): "stop<1s", "stop1-2s", "stand>=2s"; "none" before any;
- a MONSTER AT THE TARGET: a live monster (entity_appear .. entity_vanish) whose packet cell
  (hunt_core.walk_positions) at the read start or 0.45 s before it is the target ("on"), within
  1 cell ("ring1"), or 2-3 cells south of it within 1 column ("front": its body is drawn up over
  the target's point);
- a FRAME's cause (frames whose time lies after the read start and before the pointer's next
  action, the hover point re-projected from the event's from / to cells exactly as the runner
  does): "noentry ring" (red px >= NOENTRY_RED), "sword", "wide arrow" (the live reader: clear),
  "narrow arrow" (the full WALK set: clear, the live subset: not), "partial" (full-set WALK recall
  0.6 .. 0.85), "arrow off the point" (a live-subset WALK >= 0.85 within 4-16 px of the point: the
  cursor still drawn where the pointer was), "no arrow".
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
import tarfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT  # where data/ (L3, the cursor references) and the generated map cache live: --data-root
DEMO = Path("/dev/shm/poring-lab-demo")
NAS = Path("/mnt/poring-lab-datasets")
REC_SHM = Path("/dev/shm/poring-lab-rec")
REC_DISK = Path.home() / "poring-lab-rec"  # recordings go here since 2026-10-29 (rule 7)
OUT = Path("/dev/shm/poring-lab-tmp/cursor-unknown")
MAP = "gef_fild10"
NS = 1_000_000_000
READ_UNKNOWN_S, READ_CLICK_S = 0.37, 0.15
LAG_S = 0.45  # frames lag the server (frames-lag-server-half-second)
TEST2 = ("a9", "a10", "a11")  # gef10-eval.md amendment R2: the detector's held-out runs
PTR_KINDS = ("walk", "scan", "strike", "engage", "loot_step", "loot_click", "stall", "steal")
Cell = tuple[int, int]


# --- pure ---------------------------------------------------------------------------------------


def refused_tag(tag: str) -> bool:
    """PURE: a TEST2 run (a9 / a10 / a11) or any w3 watch: never read here."""
    return tag in TEST2 or tag.startswith("w3") or tag.endswith("-w3")


def read_start(e: Mapping[str, Any]) -> int:
    """PURE: a walk decision's read start (ns), from its event time (the module's definitions)."""
    back = READ_CLICK_S if e.get("clicked") else READ_UNKNOWN_S
    return int(e["t_ns"]) - int(back * NS)


def motion_state(t: int, moving: Sequence[tuple[int, int]]) -> tuple[str, float | None]:
    """PURE: (state, seconds since the server walk ended) at ``t`` from the sorted moving spans."""
    i = bisect.bisect_right([m[0] for m in moving], t) - 1
    if i < 0:
        return "none", None
    if moving[i][1] > t:
        return "moving", 0.0
    s = (t - moving[i][1]) / NS
    return ("stop<1s" if s < 1.0 else "stop1-2s" if s < 2.0 else "stand>=2s"), s


def near_kind(to: Sequence[int], c: Sequence[int]) -> str | None:
    """PURE: a monster cell ``c`` against the walk target ``to``: "on", "ring1", "front" or None."""
    dx, dy = c[0] - to[0], c[1] - to[1]
    d = max(abs(dx), abs(dy))
    if d == 0:
        return "on"
    if d <= 1:
        return "ring1"
    if abs(dx) <= 1 and -3 <= dy <= -2:
        return "front"
    return None


def alive_spans(packets: Sequence[Mapping[str, Any]]) -> dict[int, list[list[int | None]]]:
    """PURE: gid -> [[appear, vanish or None], ...] of every monster."""
    sp: dict[int, list[list[int | None]]] = defaultdict(list)
    for e in packets:
        typ = e.get("type")
        if typ == "entity_appear" and e.get("objtype") == 5:
            g = int(e["gid"])
            if not sp[g] or sp[g][-1][1] is not None:
                sp[g].append([int(e["t_mono_ns"]), None])
        elif typ == "entity_vanish" and int(e.get("gid", -1)) in sp:
            g = int(e["gid"])
            if sp[g] and sp[g][-1][1] is None:
                sp[g][-1][1] = int(e["t_mono_ns"])
    return dict(sp)


def monster_at(to: Sequence[int], t: int, pos: Mapping[int, Sequence[tuple[int, Cell, int]]],
               alive: Mapping[int, Sequence[Sequence[int | None]]]) -> str | None:  # fmt: skip
    """PURE: the closest kind ("on" < "ring1" < "front") of a live monster at the target at ``t``
    or ``t`` - LAG_S (the drawn picture), or None."""
    rank = {"on": 0, "ring1": 1, "front": 2}
    best = None
    for g, spans in alive.items():
        lst = pos.get(g) or []
        tt = [q[0] for q in lst]
        for t_ in (t, t - int(LAG_S * NS)):
            if not any(a <= t_ and (b is None or t_ < b) for a, b in spans):  # type: ignore[operator]
                continue
            i = bisect.bisect_right(tt, t_) - 1
            if i < 0:
                continue
            k = near_kind(to, lst[i][1])
            if k is not None and (best is None or rank[k] < rank[best]):
                best = k
    return best


def frame_cause(rec_live: Mapping[str, float], rec_full: Mapping[str, float], red: int,
                walk_off: float, noentry_red: int = 25) -> str:  # fmt: skip
    """PURE: one frame's cause at the hover point (the module's definitions)."""
    import cursor_sword as csw

    if red >= noentry_red:
        return "noentry ring"
    if csw.verdict(dict(rec_live)) == "sword" or csw.verdict(dict(rec_full)) == "sword":
        return "sword"
    if csw.verdict(dict(rec_live)) == "clear":
        return "wide arrow"
    if csw.verdict(dict(rec_full)) == "clear":
        return "narrow arrow"
    if float(rec_full.get("walk", 0.0)) >= 0.6:
        return "partial"
    if walk_off >= csw.DRAWN_MIN:
        return "arrow off the point"
    return "no arrow"


def share(c: Mapping[str, int]) -> str:
    n = sum(c.values()) or 1
    return "; ".join(f"{k} {v} ({100 * v / n:.1f} %)" for k, v in Counter(c).most_common())


# --- loading ------------------------------------------------------------------------------------


def session(tag: str) -> str:
    if refused_tag(tag):
        raise SystemExit(f"refused: {tag} is a TEST2 run (gef10-eval.md amendment R2)")
    hits = sorted(p.name for p in DEMO.iterdir()
                  if p.name.endswith(f"-dungeon-rogue-{MAP}-B-{tag}"))  # fmt: skip
    if len(hits) != 1:
        raise SystemExit(f"{tag}: {len(hits)} sessions in {DEMO}")
    return hits[0]


def recording(tag: str) -> Path:
    if refused_tag(tag):
        raise SystemExit(f"refused: {tag} is a TEST2 recording (gef10-eval.md amendment R2)")
    for base in (REC_SHM, REC_DISK, NAS):
        if base.is_dir():
            hits = sorted(p for p in base.iterdir() if p.name.endswith(f"-rdp-rogue-{tag}"))
            if len(hits) == 1 and (hits[0] / "manifest.json").exists():
                return hits[0]
    raise SystemExit(f"{tag}: no recording found")


def decisions(tags: Sequence[str]) -> list[dict[str, Any]]:
    """Every walk decision of the runs with its read start, motion state, target monster and the
    hover point (u, v) re-projected as the runner does."""
    import dungeon_judge as dj
    import flow_judge as fj
    import hunt_core as hc
    import numpy as np

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                  .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    rows = []
    for tag in tags:
        ev, pk, _man = dj.load(session(tag))
        _pts, moving = fj.gm_track(pk)
        pos = hc.walk_positions(pk)
        alive = alive_spans(pk)
        for e in (x for x in ev if x.get("kind") == "walk"):
            t0 = read_start(e)
            st, since = motion_state(t0, moving)
            here, to = e["from"], e["to"]
            rel = np.asarray([(to[0] - here[0], to[1] - here[1])], dtype=float)
            u, v = camera.project(rel, gat.relative_altitude(tuple(here), rel))[0]
            rows.append({"run": tag, "t": int(e["t_ns"]), "t0": t0, "clicked": bool(e["clicked"]),
                         "why": str(e.get("why")), "red": e.get("red"), "from": here, "to": to,
                         "state": st, "since": since, "u": float(u), "v": float(v),
                         "monster": monster_at(to, t0, pos, alive)})  # fmt: skip
    return rows


def trust_estimate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """walk_trust.trust_why on every refused UNKNOWN decision (the runner's grids rebuilt as in
    dungeon_hunt.run; carving is not replayed, the box watcher is not known: both make the live
    trust stricter than this estimate)."""
    import dungeon_hunt as dh
    import map_zones as mz
    import numpy as np
    import walk_trust as wt
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    zones = mz.load(MAP, shape=ok.shape)
    okr = mz.route_grid(ok, zones)
    okr = okr & ~mz.sealed_off(ok, okr)
    npcs = dh.trust_npcs_for(MAP, DATA)
    carved = np.zeros_like(okr)
    why: Counter[str] = Counter()
    mon: Counter[str] = Counter()
    for r in rows:
        if r["clicked"] or r["why"] != "cursor unknown":
            continue
        red = int(r.get("red") or 0)
        tw = wt.trust_why(tuple(r["from"]), tuple(r["to"]), route_ok=okr, carved=carved,
                          zones=zones, npcs=npcs)  # fmt: skip
        act, w = wt.decide("unknown", red, trusted=tw is None, enabled=True,
                           noentry_red=dh.NOENTRY_RED)  # fmt: skip
        key = w if act != "refuse" else f"refused: {tw}"
        why[key] += 1
        if act == "click":
            mon[r["monster"] or "none"] += 1
    return {"unknown": sum(why.values()), "outcome": dict(why), "clicked_monster": dict(mon)}


def set_data_root(root: Path) -> None:
    """Point L3 (data/kb) and the server map cache at ``root`` before anything imports them."""
    global DATA
    DATA = root
    import npc_noclick

    from poring_dataset import mapcache

    npc_noclick.KB_DIR = root / "data" / "kb"
    mapcache.GENERATED = root / "packages/poring_dataset/src/poring_dataset/_generated"


# --- the commands -------------------------------------------------------------------------------


def cmd_events(tags: Sequence[str]) -> int:
    rows = decisions(tags)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "decisions.json").write_text(json.dumps(rows))
    outcome = Counter(r["why"] if not r["clicked"] else "clicked" for r in rows)
    print(f"runs {list(tags)}: {len(rows)} walk decisions, {share(outcome)}")
    unk = [r for r in rows if r["why"] == "cursor unknown"]
    print(f"\nUNKNOWN by motion state at the read: {share(Counter(r['state'] for r in unk))}")
    print("unknown share per state:")
    for s in ("moving", "stop<1s", "stop1-2s", "stand>=2s", "none"):
        n = sum(1 for r in rows if r["state"] == s)
        k = sum(1 for r in unk if r["state"] == s)
        if n:
            print(f"  {s:10s} {k:5d} / {n:5d} = {100 * k / n:.1f} %")
    print("unknown share by whole seconds since the server stop (not moving):")
    for b in range(7):
        sel = [r for r in rows if r["state"] != "moving" and r["since"] is not None
               and min(int(r["since"]), 6) == b]  # fmt: skip
        k = sum(1 for r in sel if r["why"] == "cursor unknown")
        if sel:
            print(f"  {b}{'+' if b == 6 else ''} s: {k:4d} / {len(sel):4d} = "
                  f"{100 * k / len(sel):.1f} %")  # fmt: skip
    prev: dict[str, str] = {}
    by_prev: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        p = prev.get(r["run"], "none")
        by_prev[p]["unknown" if r["why"] == "cursor unknown" else "other"] += 1
        prev[r["run"]] = "clicked" if r["clicked"] else r["why"]
    print("after the previous decision:", {k: dict(v) for k, v in by_prev.items()})
    print(f"\nmonster at the target, clicked: "
          f"{share(Counter(r['monster'] or 'none' for r in rows if r['clicked']))}")  # fmt: skip
    print(f"monster at the target, unknown: {share(Counter(r['monster'] or 'none' for r in unk))}")
    print(f"red px >= 25 on an unknown read: {sum(1 for r in unk if (r['red'] or 0) >= 25)}")
    est = trust_estimate(rows)
    print(f"\n--walk-trust on the {est['unknown']} unknowns: {share(est['outcome'])}")
    print(f"  the monster at those clicked: {share(est['clicked_monster'])}")
    return 0


def _frame_index(rec: Path) -> list[tuple[int, str, str]]:
    man = json.loads((rec / "manifest.json").read_text())
    idx = []
    for sh in man["shards"]:
        with tarfile.open(rec / sh) as tar:
            for m in tar:
                if m.name.endswith(".json"):
                    fh = tar.extractfile(m)
                    assert fh is not None
                    meta = json.loads(fh.read())
                    idx.append((int(meta["t_mono_ns"]), sh, m.name[:-5] + ".png"))
    return sorted(idx)


def cmd_frames(tags: Sequence[str], per_run: int, seed: int) -> int:
    import random

    import cursor_robust as cr
    import cursor_sword as csw
    import dungeon_hunt as dh
    import dungeon_judge as dj
    import numpy as np

    from poring_dataset.shards import decode_png

    refs = cr.RobustRefs.load(DATA / "data/walk6/cursor_refs_rdp_v3.npz")
    live = csw.SwordRefs(refs)
    keep_subset = csw.WALK_SUBSET
    csw.WALK_SUBSET = 1
    full = csw.SwordRefs(refs)
    csw.WALK_SUBSET = keep_subset
    rnd = random.Random(seed)
    out = []
    for tag in tags:
        rows = [r for r in decisions([tag])]
        if per_run and len(rows) > per_run:
            rows = sorted(rnd.sample(rows, per_run), key=lambda r: r["t"])
        ev, _pk, _m = dj.load(session(tag))
        ptr = sorted(int(e["t_ns"]) - int((e.get("ms") or 0) * 1e6) - int(
            (READ_UNKNOWN_S + 0.08 if e["kind"] == "walk" else 0.05) * NS)
            for e in ev if e.get("kind") in PTR_KINDS)  # fmt: skip
        rec = recording(tag)
        idx = _frame_index(rec)
        tt = [x[0] for x in idx]
        want: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            j = bisect.bisect_right(ptr, r["t"])
            hi = ptr[j] if j < len(ptr) else r["t"] + NS
            if r["clicked"]:
                hi = min(hi, r["t"])
            for k in range(bisect.bisect_left(tt, r["t0"]), bisect.bisect_right(tt, hi)):
                want[idx[k]].append(r)
        by_shard: dict[str, dict[str, Any]] = defaultdict(dict)
        for key, lst in want.items():
            by_shard[key[1]][key[2]] = (key, lst)
        for sh, names in sorted(by_shard.items()):
            with tarfile.open(rec / sh) as tar:
                for m in tar:
                    if m.name not in names:
                        continue
                    fh = tar.extractfile(m)
                    assert fh is not None
                    img = decode_png(fh.read())
                    key, lst = names[m.name]
                    for r in lst:
                        u, v = round(r["u"]), round(r["v"])
                        big = img[v - 48 : v + 48, u - 48 : u + 48, :3]
                        if big.shape[:2] != (96, 96):
                            continue
                        c64 = np.ascontiguousarray(big[16:80, 16:80])
                        rl, rf = live.recalls(c64), full.recalls(c64)
                        off = max(live.recalls(np.ascontiguousarray(
                            big[16 + dy: 80 + dy, 16 + dx: 80 + dx]))["walk"]
                            for dy in range(-16, 17, 8) for dx in range(-16, 17, 8)
                            if abs(dx) > 4 or abs(dy) > 4)  # fmt: skip
                        red = dh.red_px(c64)
                        out.append({"run": tag, "t": r["t"], "clicked": r["clicked"],
                                    "state": r["state"], "dt": (key[0] - r["t0"]) / NS,
                                    "live": rl, "full": rf, "red": red, "off": off,
                                    "cause": frame_cause(rl, rf, red, off)})  # fmt: skip
        print(f"{tag}: {len(rows)} decisions, {len(want)} frames", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frames_scored.json").write_text(json.dumps(out))
    bands = ((0.0, 0.37), (0.37, 0.7), (0.7, 99.0))
    for lo, hi in bands:
        sel = [f for f in out if not f["clicked"] and lo <= f["dt"] < hi]
        print(f"\nunknown decisions, frames {lo:.2f}-{hi:.2f} s after the read start "
              f"(n={len(sel)}): {share(Counter(f['cause'] for f in sel))}")  # fmt: skip
        for s in ("moving", "stop<1s", "stop1-2s", "stand>=2s"):
            ss = [f for f in sel if f["state"] == s]
            if ss:
                print(f"  {s:10s} n={len(ss):4d}: {share(Counter(f['cause'] for f in ss))}")
    print("\nclear share of single frames by time since the read start (unknown decisions):")
    for lo, hi in ((0, 0.2), (0.2, 0.37), (0.37, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.2),
                   (1.2, 9)):  # fmt: skip
        sel = [f for f in out if not f["clicked"] and lo <= f["dt"] < hi]
        if sel:
            live_c = sum(1 for f in sel if csw.verdict(f["live"]) == "clear" and f["red"] < 25)
            full_c = sum(1 for f in sel if csw.verdict(f["full"]) == "clear" and f["red"] < 25)
            n_ = len(sel)
            print(f"  {lo:.2f}-{hi:.2f} s: n={n_:4d}  live clear {100 * live_c / n_:.0f} %"
                  f"  full-set clear {100 * full_c / n_:.0f} %")  # fmt: skip
    return 0


def cmd_loop() -> int:
    import hunt_core as hc
    import hunt_flow as hf
    import map_zones as mz
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    zones = mz.load(MAP, shape=ok.shape)
    warps = json.loads((DATA / "data/kb/warps.json").read_text()).get(MAP, [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    area = mz.apply(ok, hc.search_area(ok, keep, margin=10), zones)[1]
    okr = mz.route_grid(ok, zones)
    cut = mz.sealed_off(ok, okr)
    area = hf.main_component(area & ~cut)
    okr = okr & ~cut
    npcs = [(int(n["x"]), int(n["y"])) for n in json.loads(
        (DATA / "data/kb/npc_cells.json").read_text())["maps"][MAP]["npcs"]]  # fmt: skip
    doc = json.loads((ROOT / "config/routes/gef_fild10-batt-loop.json").read_text())
    wps = [(int(c[0]), int(c[1])) for c in doc["waypoints"]]

    def dn(c: Cell) -> int:
        return min(max(abs(c[0] - x), abs(c[1] - y)) for x, y in npcs)

    n = len(wps)
    print(f"{n} waypoints; NPCs {npcs}")
    bad_wp = []
    for i, c in enumerate(wps):
        f = []
        if dn(c) <= 3:
            f.append(f"{dn(c)} cells from an NPC")
        zs = [zones.no_enter[k].id for k in sorted(mz.polys_at(zones, c))]
        if zs:
            f.append(f"inside {','.join(zs)}")
        if not okr[c[1], c[0]]:
            f.append("off the route grid")
        if not area[c[1], c[0]]:
            f.append("off the search area")
        if f:
            bad_wp.append(i)
            print(f"  waypoint {i} {c}: {'; '.join(f)}")
    near3 = 0
    zone_legs = 0
    for i in range(n):
        a, b = wps[i], wps[(i + 1) % n]
        seg = mz.supercover(a, b, closed=True)
        path = hc.astar(okr, a, b) if okr[a[1], a[0]] and okr[b[1], b[0]] else None
        d_seg = min(dn(c) for c in seg)
        d_path = None if path is None else min(dn(c) for c in path)
        home = mz.polys_at(zones, a)
        enters = sorted({zones.no_enter[k].id for c in seg for k in mz.polys_at(zones, c) - home})
        if mz.polys_at(zones, a) or mz.polys_at(zones, b):
            enters = sorted(
                set(enters)
                | {zones.no_enter[k].id for k in mz.polys_at(zones, a) | mz.polys_at(zones, b)}
            )
        nonwalk = sum(1 for c in seg if not ok[c[1], c[0]])
        f = []
        if d_seg <= 3 or (d_path is not None and d_path <= 3):
            near3 += 1
            f.append(f"straight line {d_seg} / A* route {d_path} cells from an NPC")
        if enters:
            zone_legs += 1
            f.append(f"touches no-enter {','.join(enters)}")
        if path is None:
            f.append("no A* route on the route grid")
        if nonwalk:
            f.append(f"{nonwalk} of {len(seg)} straight cells not walkable (A* goes round)")
        if f:
            print(f"  leg {i} {a} -> {b}: {'; '.join(f)}")
    print(
        f"\nwaypoints flagged: {len(bad_wp)} {bad_wp}; legs within 3 cells of an NPC: {near3}; "
        f"legs touching a no-enter zone: {zone_legs} (of {n})"
    )
    print(
        f"min NPC distance over all straight legs: "
        f"{min(dn(c) for i in range(n) for c in mz.supercover(wps[i], wps[(i + 1) % n]))}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument(
        "--data-root",
        type=Path,
        default=ROOT,
        help="the checkout whose data/ and generated map cache are read (a worktree "
        "has neither: pass the main checkout)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("events")
    e.add_argument("tags", nargs="+")
    f = sub.add_parser("frames")
    f.add_argument("tags", nargs="+")
    f.add_argument("--per-run", type=int, default=300)
    f.add_argument("--seed", type=int, default=7)
    sub.add_parser("loop")
    a = ap.parse_args()
    set_data_root(a.data_root)
    if a.cmd == "events":
        return cmd_events(a.tags)
    if a.cmd == "frames":
        return cmd_frames(a.tags, a.per_run, a.seed)
    return cmd_loop()


if __name__ == "__main__":
    raise SystemExit(main())
