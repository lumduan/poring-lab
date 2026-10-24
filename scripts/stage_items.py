#!/usr/bin/env python3
"""Stage Batt's TARGET items on a hunting map's floor, so they can be learnt from pixels (Batt
2026-10-24 ~16:0x, his reply to the 14:10 report: "try training the target drops -- Rough Elunium,
Rough Oridecon, Dead Branch -- for pickup accuracy").

They almost never drop: 0.07-0.75 per 100 kills (thief-payon.md 4c), and 4.03's 69 kills gave one.
So the Thief gives itself one of each (@item) and drops them by the inventory's KNOWN path
(gm_state.clear_loot with this tool's own icon set: only these items are loot). Spots are spread
over the hunt's own search area. At each spot the camera sees the items from OFFSETS (same-map @warp
steps: typed lines only, NO world click), STILL_S on each.

The 1-fps recorder (record_session, started beside this tool) banks the frames and the packets:
the floor items' exact cells and their drop and vanish times are the OFFLINE labels
(item_labels.py; docs/planning/item-class.md). Nothing here reads a packet (rule 1). Immunity is
ON for the whole session (`immune-on`, then a person's look at its frame). A relog clears it
afterwards (@monsterignore does not survive one).

    stage_items.py spots --map pay_fild07 --n 12 --seed S     OFFLINE: the spots (printed)
    stage_items.py cut SPEC                                    OFFLINE: the icon set (ICON_DIR)
    stage_items.py give                                        LIVE: @item each target once
    stage_items.py immune-on                                   LIVE: @monsterignore + a frame
    stage_items.py run --map pay_fild07 --n 12 --seed S --immune-confirmed     LIVE
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/dev/shm/poring-lab-demo")
VERSION = "stage@3"  # @2: --open (target-items.md 9b); @3: refuses while targets are held
# item id -> icon name (pinned pre-re item_db; Batt's four: Honey is Healing, Dead Branch Usable,
# the Roughs Etc). Dead Branch is NEVER used (it summons a monster): this tool only drags it.
TARGETS: dict[int, str] = {757: "rough_elunium", 756: "rough_oridecon", 604: "dead_branch",
                           518: "honey"}  # fmt: skip
ICON_DIR = ROOT / "data" / "thief" / "stage_icons"  # client pixels: data/, never committed
OFFSETS: list[tuple[int, int]] = [(0, 0), (3, 0), (0, 3), (-3, 0), (0, -3)]
STILL_S = 5.0  # frames at 1 fps: ~5 per offset
SPOT_SEP = 25  # cells between spots (Chebyshev): other ground, other light
WARP_SETTLE_S = 2.5
READY_MAX_S = 20.0  # a map change's loading screen took longer than 2.5 s (prt_fild08 -> 07)
CHAR = "thief"


def pick_spots(area: Any, n: int, seed: int, sep: int = SPOT_SEP,
               offsets: list[tuple[int, int]] = OFFSETS) -> list[tuple[int, int]]:  # fmt: skip
    """PURE: up to ``n`` cells of ``area`` (bool [y, x]) whose every offset is in ``area`` too, at
    least ``sep`` cells apart (Chebyshev), drawn in a seeded order."""
    h, w = area.shape
    cand = []
    for y, x in zip(*np.nonzero(area), strict=True):
        if all(0 <= x + dx < w and 0 <= y + dy < h and area[y + dy, x + dx] for dx, dy in offsets):
            cand.append((int(x), int(y)))
    order = np.random.default_rng(seed).permutation(len(cand))
    out: list[tuple[int, int]] = []
    for i in order:
        c = cand[int(i)]
        if all(max(abs(c[0] - o[0]), abs(c[1] - o[1])) >= sep for o in out):
            out.append(c)
            if len(out) == n:
                break
    return out


CANOPY_NORTH, CANOPY_AROUND = 6, 3  # cells: a tall model hides what stands NORTH of its base on
# screen (the camera looks north); the target-items study (9b) found 29 % of its items under trees


def open_area(
    area: Any, canopy: Any, north: int = CANOPY_NORTH, around: int = CANOPY_AROUND
) -> Any:
    """PURE: ``area`` minus the tall-model footprints ``canopy`` (bool [y, x]) widened by ``around``
    cells and by ``north`` cells towards +y (north), where an item would be drawn behind a tree."""
    h, w = canopy.shape
    grown = canopy.copy()
    ys, xs = np.nonzero(canopy)
    for dy in range(-around, north + 1):
        for dx in range(-around, around + 1):
            grown[np.clip(ys + dy, 0, h - 1), np.clip(xs + dx, 0, w - 1)] = True
    return area & ~grown


def search_area(map_: str) -> Any:
    """The hunt runner's own search area (dungeon_hunt.run: stand grid, 10 cells off every warp,
    the zones applied, the sealed-off parts cut, the main component)."""
    import hunt_core as hc
    import hunt_flow as hf
    import map_zones as mz
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod

    gat = gatmod.parse((cam.GAT_DIR / f"{map_}.gat").read_bytes())
    ok = stand_grid(map_, gat)
    warps = json.loads((ROOT / "data" / "kb" / "warps.json").read_text()).get(map_, [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    zones = mz.load(map_, shape=ok.shape)
    if zones is None:
        raise SystemExit(f"stage_items refused: no config/map_zones/{map_}.yaml")
    area = mz.apply(ok, hc.search_area(ok, keep, margin=10), zones)[1]
    cut = mz.sealed_off(ok, mz.route_grid(ok, zones))
    return hf.main_component(area & ~cut)


def cut(spec: Path) -> dict[str, Any]:
    """OFFLINE: the icon set from judged full-desktop PNGs with the inventory at its home. ``spec``
    (JSON): {"origin": [gx, gy], "icons": [{"png", "col", "row", "name"}]} -- every name one of
    TARGETS' (a person, or Claude on a judged screenshot, identified the slots)."""
    import gm_state
    from PIL import Image

    sp = json.loads(spec.read_text())
    gx, gy = sp["origin"]
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for it in sp["icons"]:
        if it["name"] not in TARGETS.values():
            raise SystemExit(f"stage_items cut: {it['name']!r} is not a target item")
        rgb = np.asarray(Image.open(it["png"]).convert("RGB"))[gy:, gx:]
        f = np.ascontiguousarray(rgb[..., ::-1])
        np.save(ICON_DIR / f"loot-{it['name']}.npy", gm_state.icon_crop(f, it["col"], it["row"]))
        out.append(it["name"])
    return {"cut": out, "dir": str(ICON_DIR)}


def _session(why: str) -> Any:
    import ro_agent as r

    return r.session(f"rule:stage-items-{why}")


def _check(screen: Any) -> None:
    import crusader as cr
    import ro_agent as r

    if not cr.check(screen, CHAR, CHAR)["ok"]:
        raise r.Stop("stage_items: not the Thief")


def _settle(screen: Any, max_s: float = READY_MAX_S) -> float:
    """After a @warp: wait until the Basic Info identity reads again (the first run's 2.5 s fixed
    wait checked the LOADING screen of a map change and stopped). Returns the seconds waited."""
    import crusader as cr
    import ro_agent as r

    t0 = time.monotonic()
    time.sleep(WARP_SETTLE_S)
    while not cr.check(screen, CHAR, CHAR)["ok"]:
        if time.monotonic() - t0 > max_s:
            raise r.Stop(f"stage_items: the identity did not read within {max_s} s of a @warp")
        time.sleep(0.5)
    return round(time.monotonic() - t0, 1)


def held_refusal(rows: Iterable[Sequence[Any]]) -> str | None:
    """PURE (stage@3, 2026-10-25): why a staging run must NOT start, or None. gm_state.clear_loot
    drops WHOLE stacks, so a target item already held goes to the floor with the staged copy and
    is lost: run c (2026-10-24 22:23) dropped Dead Branch 5, Rough Elunium 3, Rough Oridecon 2 and
    Honey 2 at its first spot, 4.04's natural Dead Branches and Rough Elunium among them. ``rows``
    = (nameid, amount) from the DB, its LAST SAVE: a pickup since then is not in it."""
    held = {int(i): int(n) for i, n in rows if int(i) in TARGETS and int(n) > 0}
    if not held:
        return None
    return (
        f"stage_items refused: the {CHAR} holds target items {held} (DB last save): "
        "clear_loot drops whole stacks, so they would be staged and lost (a person stores "
        "them first)"
    )


def _held_rows() -> list[Sequence[Any]]:
    """The Thief's target-item stacks from the lab DB (the experimenter's check, as
    dungeon_hunt's setup reads its stock; never a decision input of the agent)."""
    import crusader as cr
    import ro_agent as r

    name = json.loads((cr.data_dir(CHAR) / "char.json").read_text())["name"]
    cid = int(r.db_query(f"SELECT char_id FROM `char` WHERE name = {r.sql_str(name)};")[0][0])
    ids = ", ".join(str(i) for i in sorted(TARGETS))
    return list(r.db_query(f"SELECT nameid, amount FROM inventory WHERE char_id = {cid} "
                           f"AND nameid IN ({ids});"))  # fmt: skip


def give() -> None:
    """LIVE: one of each target (for the icon cut, then the inventory frames to judge)."""
    import bench
    import crusader as cr
    import ro_agent as r

    with _session("give") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        for iid in TARGETS:
            cr.gm_line(agent, screen, f"@item {iid} 1", CHAR, CHAR)
            time.sleep(0.8)
        bench.close_chat(agent, screen)
        print(r.to_png(screen.full(), r.SHOTS / "stage-give.png"))


def immune_on() -> None:
    """LIVE: @monsterignore (a TOGGLE: run it only on a fresh login, where it is off) + a frame
    for a person to read the confirmation line in the chat."""
    import crusader as cr
    import ro_agent as r

    with _session("immune") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        cr.gm_line(agent, screen, "@monsterignore", CHAR, CHAR)
        time.sleep(1.2)
        print(r.to_png(screen.full(), r.SHOTS / "stage-immune.png"))


def run(a: argparse.Namespace) -> int:
    import bench
    import crusader as cr
    import gm_state
    import ro_agent as r
    import ui_gate

    if not a.immune_confirmed:
        raise SystemExit(
            "stage_items refused: --immune-confirmed (a person read immune-on's frame)"
        )
    missing = [n for n in TARGETS.values() if not (ICON_DIR / f"loot-{n}.npy").exists()]
    if missing:
        raise SystemExit(f"stage_items refused: no icon for {missing} in {ICON_DIR} (cut)")
    why = held_refusal(_held_rows())
    if why:
        raise SystemExit(why)
    area = search_area(a.map)
    if a.open is not None:  # target-items.md 9b: stage on OPEN ground (the RSW's tall models)
        area = open_area(area, np.load(a.open))
    spots = pick_spots(area, a.n, a.seed)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-stage-items-{a.map}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    ev({"kind": "run_start", "version": VERSION, "map": a.map, "seed": a.seed, "spots": spots,
        "open": None if a.open is None else str(a.open),
        "offsets": OFFSETS, "still_s": STILL_S, "targets": TARGETS})  # fmt: skip
    reason = "done"
    with _session("run") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        try:
            for k, (x, y) in enumerate(spots):
                cr.gm_line(agent, screen, f"@warp {a.map} {x} {y}", CHAR, CHAR)
                ev({"kind": "warp", "spot": k, "at": [x, y], "settle_s": _settle(screen)})
                bench.close_chat(agent, screen)
                for iid in TARGETS:
                    cr.gm_line(agent, screen, f"@item {iid} 1", CHAR, CHAR)
                    time.sleep(0.8)
                bench.close_chat(agent, screen)
                res = gm_state.clear_loot(agent, screen, why=f"stage-{k}", refs_dir=ICON_DIR)
                names = sorted(d["item"] for d in res["dropped"])
                ev({"kind": "dropped", "spot": k, "at": [x, y], "items": names,
                    "unknown": res["unknown"]})  # fmt: skip
                if names != sorted(TARGETS.values()):
                    reason = f"spot {k}: dropped {names}, not the four"
                    break
                for dx, dy in OFFSETS:
                    if (dx, dy) != (0, 0):
                        cr.gm_line(agent, screen, f"@warp {a.map} {x + dx} {y + dy}", CHAR, CHAR)
                        _settle(screen)
                        bench.close_chat(agent, screen)
                    ev({"kind": "still", "spot": k, "at": [x + dx, y + dy], "s": STILL_S})
                    time.sleep(STILL_S)
                print(f"spot {k + 1}/{len(spots)} at {x},{y}: {names}", flush=True)
        except r.Stop as exc:
            reason = f"stop: {exc}"
        finally:
            ui_gate.ensure_clear(agent, screen, why="stage-end")
            print(r.to_png(screen.full(), r.SHOTS / f"stage-end-{a.label}.png"), flush=True)
    ev({"kind": "run_end", "reason": reason})
    evf.close()
    print(json.dumps({"sid": sid, "reason": reason, "spots": len(spots)}))
    return 0 if reason == "done" else 1


WATCH_DWELL_S = 30.0  # payf07-detector.md: still frames of monsters around an immune Thief


def watch_cells(lattice: list[dict[str, Any]], seed: int, max_cells: int) -> list[tuple[int, int]]:
    """PURE: the lattice's cells in a seeded order, cut at ``max_cells`` (successive seeds cover the
    map evenly when a time box cuts the list, as warp_watch's plan does)."""
    cells = [(int(c["x"]), int(c["y"])) for c in lattice]
    if len(set(cells)) != len(cells) or not cells:
        raise SystemExit("watch: an empty lattice or a repeated cell")
    order = np.random.default_rng(seed).permutation(len(cells))
    return [cells[int(i)] for i in order[:max_cells]]


def watch(a: argparse.Namespace) -> int:
    """LIVE (payf07-detector.md, Elder Willow is the thinnest class): the IMMUNE Thief warps over a
    lattice of three-check stand cells and dwells WATCH_DWELL_S at each while the 1-fps recorder
    (started beside this tool) banks the frames. Typed @warp lines only, no world click; the same
    recording path as the staged session, so its frames join TRAIN by the 3c rule."""
    import bench
    import crusader as cr
    import ro_agent as r
    import ui_gate

    if not a.immune_confirmed:
        raise SystemExit("stage_items watch refused: --immune-confirmed (a person read the frame)")
    cells = watch_cells(json.loads(a.lattice.read_text()), a.seed, a.max_cells)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-watch-{a.map}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    ev({"kind": "run_start", "version": VERSION, "what": "watch", "map": a.map, "seed": a.seed,
        "cells": cells, "dwell_s": a.dwell_s, "lattice": str(a.lattice)})  # fmt: skip
    reason = "done"
    t_end = time.monotonic() + a.max_minutes * 60
    with _session("watch") as (agent, screen):
        agent.wait_for_human()
        _check(screen)
        try:
            for k, (x, y) in enumerate(cells):
                if time.monotonic() > t_end:
                    reason = "time_box"
                    break
                cr.gm_line(agent, screen, f"@warp {a.map} {x} {y}", CHAR, CHAR)
                settle = _settle(screen)
                bench.close_chat(agent, screen)
                ev({"kind": "dwell", "i": k, "at": [x, y], "settle_s": settle, "s": a.dwell_s})
                time.sleep(a.dwell_s)
                print(f"cell {k + 1}/{len(cells)} at {x},{y}", flush=True)
        except r.Stop as exc:
            reason = f"stop: {exc}"
        finally:
            ui_gate.ensure_clear(agent, screen, why="watch-end")
            print(r.to_png(screen.full(), r.SHOTS / f"watch-end-{a.label}.png"), flush=True)
    ev({"kind": "run_end", "reason": reason})
    evf.close()
    print(json.dumps({"sid": sid, "reason": reason, "cells": len(cells)}))
    return 0 if reason in ("done", "time_box") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("spots")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--open", type=Path, default=None)
    p = sub.add_parser("cut")
    p.add_argument("spec", type=Path)
    sub.add_parser("give")
    sub.add_parser("immune-on")
    p = sub.add_parser("watch")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--lattice", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-cells", type=int, default=200)
    p.add_argument("--max-minutes", type=float, default=40.0)
    p.add_argument("--dwell-s", type=float, default=WATCH_DWELL_S)
    p.add_argument("--label", default="w")
    p.add_argument("--immune-confirmed", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("--map", default="pay_fild07")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--label", default="s")
    p.add_argument("--immune-confirmed", action="store_true")
    p.add_argument("--open", type=Path, default=None,
                   help="a canopy mask .npy (client-derived, /dev/shm): open ground")  # fmt: skip
    a = ap.parse_args()
    if a.cmd == "spots":
        area = search_area(a.map)
        if a.open is not None:
            area = open_area(area, np.load(a.open))
        print(json.dumps(pick_spots(area, a.n, a.seed)))
    elif a.cmd == "cut":
        print(json.dumps(cut(a.spec)))
    elif a.cmd == "give":
        give()
    elif a.cmd == "immune-on":
        immune_on()
    elif a.cmd == "watch":
        return watch(a)
    elif a.cmd == "run":
        return run(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
