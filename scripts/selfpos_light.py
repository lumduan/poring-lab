#!/usr/bin/env python3
"""The minimap readout over LIGHT strips (docs/planning/rogue-xmas02.md, X1b): labelled readout
crops from a live map, then the readers scored on them.

    selfpos_light.py collect --map xmas_dun02 --out DIR [--per-stand 8] [--every 1]   (LIVE)
    selfpos_light.py truth DIR        (offline: the sniffer's archive -> each crop's true cell)
    selfpos_light.py score DIR [--split all|even|odd] [--templates NPZ]

Why: on 2026-11-05 the Rogue's pilot on xmas_dun02 stopped because ``poring_env.selfpos`` reads
nothing over the map's pale floor tiles (``no_glyph``): the readout's digits are drawn OPAQUE
(white strokes ~250, a black drop shadow ~0) over a strip the scene shows through, and its strip
background estimate leaves out every pixel brighter than the ink level, so a pale floor (~200)
became "half a stroke" everywhere.

collect (live, the Rogue -- or any character with @warp -- standing on ``--map``):
  * stands = the map's patrol-route waypoints (config/routes/<map>.yaml, reviewed; every one is on
    the route grid, so each is a checked stand cell), or with ``--cells midpoints`` the cell
    halfway along each leg (fresh cells), every ``--every``-th one, in route order;
  * per stand: ``@warp <map> x y`` through crusader.gm_line (the identity check, the UI gate and
    the chat window check of every typed line), 1.5 s to land and the identity check passing
    again (the loading screen over; also before every typed line), then ``--per-stand`` grabs
    0.35 s apart. Each grab keeps only the readout rect padded by 2 px (a few hundred bytes:
    crops.npz), and the reader's answer on the full game region at that moment (samples.jsonl);
  * the end: ``@warp`` back to dungeon_hunt.CLEAR_STAND. No other input (no walking, no clicks).
truth (offline ground truth, ADR-0007: it labels, never reaches a reader): the sniffer's events of
  the collection window (record_session.packets_for); a crop's true cell is the LAST own
  ``map_change`` before its grab on the collected map, and the crop counts only when no own
  move / stop event lies between that warp and the grab (the character stood) and the warp landed
  where it was sent (else the stand is dropped, with its reason).
score: every labelled crop through a reader (``read_rect`` on the unpadded rect) -> exact, None
  (abstain, with reasons), WRONG (a read that is not the truth: the bar is 0), split by the strip's
  brightness (the scene median, light >= LIGHT_STRIP) and by stand index parity (even = the fitting
  half, odd = held out; X1b's pre-registration).

Scratch goes to /dev/shm (rule 7): the crops are client-derived pixels, never committed.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "packages" / "poring_env" / "src"))

from poring_env import selfpos as sp  # noqa: E402

PAD = 2  # px of context around the readout rect in each crop
LAND_S = 1.5  # after the typed @warp line, before the first grab (map load + camera settle)
READY_S = 8.0  # at most this long for the identity check to pass again after a warp
GRAB_GAP_S = 0.35
LIGHT_STRIP = 170.0  # a strip whose scene median is this bright counts as "light" in the scores


def scene_median(gray: np.ndarray) -> float:
    """The strip's scene grey: the median of the pixels that are neither the digits' strokes
    (>= 235) nor their shadows (<= 40) -- the opaque glyph pixels left out, whatever the floor."""
    scene = gray[(gray > 40) & (gray < 235)]
    return float(np.median(scene)) if scene.size else float(np.median(gray))


def collect(a: argparse.Namespace) -> int:
    import crusader as cr
    import dungeon_hunt as dh
    import map_routes
    import ro_agent as r

    routes = map_routes.load(a.map)
    if routes is None or not routes.routes:
        raise SystemExit(f"no reviewed route for {a.map}: config/routes/{a.map}.yaml")
    wps = [(int(c[0]), int(c[1])) for c in routes.routes[0].waypoints]
    if a.cells == "midpoints":  # X1b round 2's FRESH cells: halfway along each leg of the loop
        # (every leg is a straight run on the route grid, xmas02-prep.md section 3, so each
        # midpoint is a route-grid cell; none is a waypoint)
        legs = zip(wps, wps[1:] + wps[:1], strict=True)
        wps = [((x1 + x2) // 2, (y1 + y2) // 2) for (x1, y1), (x2, y2) in legs]
    stands = wps[:: a.every]
    first = a.start  # a resumed collection keeps the route's stand numbers (the split's parity)
    out: Path = a.out
    out.mkdir(parents=True, exist_ok=True)
    rx, ry, rw, rh = sp.default_rect()
    x0c, y0c, x1c, y1c = rx - PAD, ry - PAD, rx + rw + PAD, ry + rh + PAD
    templates = sp.load_digit_templates()
    crops: list[np.ndarray] = []
    samples: list[dict[str, Any]] = []
    t0 = r.ns()
    meta = {"map": a.map, "cells": a.cells, "stands": len(stands), "start": first,
            "per_stand": a.per_stand,
            "every": a.every,
            "rect": [rx, ry, rw, rh], "pad": PAD, "t0_mono_ns": t0,
            "t0_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z")}  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    gx, gy, gw, gh = r.game_region()
    with r.session("selfpos-light") as (agent, screen):

        def ready(why: str) -> float:
            """Wait (<= READY_S) until the identity check passes on a fresh frame: the map is drawn
            again after a warp's loading screen (2026-11-05 20:17, the first collection: a check
            1.5 s after the first warp onto xmas_dun02 read the loading screen and stopped)."""
            t_s = time.monotonic()
            while True:
                got = cr.check(screen, a.job, a.char)
                if got["ok"]:
                    return time.monotonic() - t_s
                if time.monotonic() - t_s > READY_S:
                    raise r.Stop(f"{why}: the identity check did not pass within {READY_S} s "
                                 f"({got}): nothing typed")  # fmt: skip
                time.sleep(0.25)

        def line(cmd: str) -> int:
            ready(cmd)
            t = r.ns()
            cr.gm_line(agent, screen, cmd, a.job, a.char)
            return t

        clean = False  # the home warp is typed only after a clean collection (2026-11-05 21:21:
        # the end path's line after a refused one ran the chat window check again on the same
        # unread state; with the then reader that pressed Enter and cycled F10)
        try:
            for i, (x, y) in enumerate(stands):
                if i < first:
                    continue
                t_cmd = line(f"@warp {a.map} {x} {y}")
                time.sleep(LAND_S)
                if i == first and a.clear:
                    line("@killmonster2")  # a still scene behind the strip, and no aggressor
                    time.sleep(LAND_S)
                landed_s = ready(f"stand {i}")  # the map drawn again before the first grab
                for k in range(a.per_stand):
                    t_grab, img = screen.grab(gx, gy, gw, gh)
                    bgr = np.ascontiguousarray(np.asarray(img)[..., :3])
                    reading = sp.read_minimap(bgr, templates, light=False)  # the base reader
                    crops.append(bgr[y0c:y1c, x0c:x1c].copy())
                    samples.append({"i": len(samples), "stand": i, "sent": [x, y], "k": k,
                                    "t_cmd_ns": t_cmd, "t_grab_ns": int(t_grab),
                                    "ready_s": round(landed_s, 2),
                                    "read": list(reading.xy) if reading.xy else None,
                                    "reason": reading.reason})  # fmt: skip
                    time.sleep(GRAB_GAP_S)
                ok = sum(1 for s in samples[-a.per_stand :] if s["read"] == [x, y])
                print(f"stand {i:3d} {x:3d},{y:3d}: base reader exact {ok}/{a.per_stand} "
                      f"({Counter(s['reason'] for s in samples[-a.per_stand:]).most_common(2)})",
                      flush=True)  # fmt: skip
            clean = True
        finally:
            t1 = r.ns()
            np.savez_compressed(out / "crops.npz", crops=np.stack(crops) if crops else np.zeros(0))
            with (out / "samples.jsonl").open("w") as fh:
                for s in samples:
                    fh.write(json.dumps(s) + "\n")
            meta.update({"t1_mono_ns": t1, "samples": len(samples)})
            (out / "meta.json").write_text(json.dumps(meta, indent=1))
            home = dh.CLEAR_STAND
            if clean:
                line(f"@warp {home[0]} {home[1]} {home[2]}")
            else:
                print("stopped: the home warp is NOT typed (the character stays where it is)",
                      flush=True)  # fmt: skip
    print(f"collected {len(samples)} crops at {len(stands)} stands -> {out}")
    return 0


def own_events(events: list[dict[str, Any]], gid: int) -> list[dict[str, Any]]:
    """Our own position events: every map_change and self_move (only ever ours), and the move /
    stop broadcasts that carry our block id."""
    keep = [e for e in events
            if e.get("type") in ("map_change", "self_move")
            or (e.get("type") in ("entity_stop", "move") and e.get("gid") == gid)]  # fmt: skip
    return sorted(keep, key=lambda e: int(e["t_mono_ns"]))


def label(samples: list[dict[str, Any]], events: list[dict[str, Any]], map_: str,
          gid: int) -> list[dict[str, Any]]:  # fmt: skip
    """Each sample's truth (see the module docstring); ``truth`` None with ``why`` when unusable."""
    ev = own_events(events, gid)
    times = [int(e["t_mono_ns"]) for e in ev]
    out = []
    for s in samples:
        j = bisect.bisect_right(times, int(s["t_grab_ns"])) - 1
        warp = next((ev[k] for k in range(j, -1, -1) if ev[k]["type"] == "map_change"), None)
        why = None
        if warp is None or int(warp["t_mono_ns"]) < int(s["t_cmd_ns"]):
            why = "no map_change after the typed @warp"
        elif warp.get("map", "").removesuffix(".gat") != map_:
            why = f"landed on {warp.get('map')}"
        elif [int(warp["x"]), int(warp["y"])] != s["sent"]:
            why = f"landed at {warp['x']},{warp['y']}"
        else:
            k0 = times.index(int(warp["t_mono_ns"]))
            if any(e["type"] != "map_change" for e in ev[k0 + 1 : j + 1]):
                why = "moved after the warp"
        out.append({**s, "truth": None if why else s["sent"], "why": why})
    return out


def truth(a: argparse.Namespace) -> int:
    import record_session as rs

    d: Path = a.dir
    meta = json.loads((d / "meta.json").read_text())
    samples = [json.loads(x) for x in (d / "samples.jsonl").read_text().splitlines() if x]
    events = rs.packets_for(int(meta["t0_mono_ns"]), int(meta["t1_mono_ns"]))
    with gzip.open(d / "packets.jsonl.gz", "wt") as fh:
        for e in events:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    labelled = label(samples, events, meta["map"], a.gid)
    with (d / "labelled.jsonl").open("w") as fh:
        for s in labelled:
            fh.write(json.dumps(s) + "\n")
    why = Counter(s["why"] or "ok" for s in labelled)
    print(json.dumps({"events": len(events), "samples": len(labelled), "labels": dict(why)}))
    return 0


def score_rows(labelled: list[dict[str, Any]], crops: np.ndarray, pad: int, reader: Any,
               split: str) -> dict[str, Any]:  # fmt: skip
    rows: dict[str, Counter[str]] = {"light": Counter(), "dark": Counter(), "all": Counter()}
    reasons: dict[str, Counter[str]] = {"light": Counter(), "dark": Counter()}
    wrong: list[dict[str, Any]] = []
    for s in labelled:
        if s["truth"] is None:
            continue
        if split != "all" and (s["stand"] % 2 == 0) != (split == "even"):
            continue
        c = crops[s["i"]]
        gray = sp.to_gray(c[pad:-pad, pad:-pad])
        kind = "light" if scene_median(gray) >= LIGHT_STRIP else "dark"
        rd = reader(gray)
        res = "none" if rd.xy is None else ("exact" if list(rd.xy) == s["truth"] else "wrong")
        for k in (kind, "all"):
            rows[k][res] += 1
        if res == "none":
            reasons[kind][rd.reason] += 1
        if res == "wrong":
            wrong.append({"i": s["i"], "truth": s["truth"], "read": list(rd.xy), "kind": kind})
    out: dict[str, Any] = {}
    for k, c in rows.items():
        n = sum(c.values())
        out[k] = {"n": n, **{r_: c[r_] for r_ in ("exact", "none", "wrong")},
                  "exact_rate": round(c["exact"] / n, 4) if n else None}  # fmt: skip
    out["none_reasons"] = {k: dict(v.most_common()) for k, v in reasons.items()}
    out["wrong"] = wrong[:20]
    return out


def score(a: argparse.Namespace) -> int:
    labelled: list[dict[str, Any]] = []
    parts, pad = [], PAD
    for d in a.dirs:  # a collection and its resumed parts: crop indices offset per part
        meta = json.loads((d / "meta.json").read_text())
        pad = int(meta["pad"])
        off = sum(len(c) for c in parts)
        parts.append(np.load(d / "crops.npz")["crops"])
        for x in (d / "labelled.jsonl").read_text().splitlines():
            if x:
                s = json.loads(x)
                labelled.append({**s, "i": s["i"] + off})
    crops = np.concatenate(parts)
    templates = sp.load_digit_templates(a.templates)
    res = {
        "split": a.split,
        "base": score_rows(labelled, crops, pad,
                           lambda g: sp.read_rect(g, templates, light=False), a.split),
        "with_light": score_rows(labelled, crops, pad,
                                 lambda g: sp.read_rect(g, templates, light=True),
                                 a.split),
    }  # fmt: skip
    print(json.dumps(res, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--map", required=True)
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--per-stand", type=int, default=8)
    c.add_argument("--every", type=int, default=1)
    c.add_argument("--start", type=int, default=0, help="resume at this stand number")
    c.add_argument("--cells", choices=["waypoints", "midpoints"], default="waypoints")
    c.add_argument("--job", default="rogue")
    c.add_argument("--char", default="thief", help="crusader.py's data dir for the identity check")
    c.add_argument("--no-clear", dest="clear", action="store_false")
    t = sub.add_parser("truth")
    t.add_argument("dir", type=Path)
    t.add_argument("--gid", type=int, default=2000002, help="our block id (the GM account's AID)")
    s = sub.add_parser("score")
    s.add_argument("dirs", type=Path, nargs="+")
    s.add_argument("--split", choices=["all", "even", "odd"], default="all")
    s.add_argument("--templates", type=Path, default=sp.DEFAULT_TEMPLATES)
    a = ap.parse_args(argv)
    return {"collect": collect, "truth": truth, "score": score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
