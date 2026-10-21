#!/usr/bin/env python3
"""WARP AND WATCH: detector data from a map the detector has never seen (Batt 2026-10-21 ~09:1x,
ORC DUNGEON F1: "the detector is blind to these species, so no walking/clicking in the world. Use
"warp and watch": GM immune (@monsterignore), @warp to a lattice of stand cells over the walkable
area (three-check cells), dwell and record frames (5 Hz, q80, NAS, chunked shards) + packets;
distinct typed lines only (chat guard); UI gate on every line").

    warp_watch.py plan  --map M --lattice JSON --seed S [--dwell-s T] [--max-minutes N]   OFFLINE
    warp_watch.py run   --map M --lattice JSON --seed S --label L [--dwell-s T]
                        [--max-minutes N] [--back MAP,X,Y]                                 LIVE
    warp_watch.py judge SESSION_DIR [--view DX,DY]                                      OFFLINE

THE SESSION is collect_v2's natural dwells and nothing else: per lattice cell `@warp M x y`, a
settle, a dwell (collect_v2.Driver: no spawn block, no portal pass, NO world click -- the only
mouse use is the UI gate's own known steps and the chat input). collect_v2's rules hold:
- every GM line goes through ro_agent.gm (the UI gate, the foreground gate, the typing guard),
  peeking at the guard first so a refused 3rd identical line is never claimed as typed;
- the GM must be confirmed immune for THIS login (collect_v2's record) before any input;
- an immune GM that needs a heal or a revive after the start is a CONDITION FAILURE: recover and
  stop.
- SIGTERM and --max-minutes end the run between steps, cleanly.

THE CELLS come from a lattice file (``[{"x", "y", ...}]``): the three-check stand cells (client ∩
server walkable, outside every warp span and script-NPC touch area; memory "stand cells: three
checks"). The plan only orders them: a seeded shuffle, so successive blocks with new seeds cover
the map evenly when a time box cuts the list.

THE RECORDER: a separate process grabs the GAME_REGION at REC_HZ (5 Hz) and writes JPEG q80 into
tar shards (``shard-NNNNNN.tar``: ``<frame>.jpg`` + ``<frame>.json`` with frame_id and the host
CLOCK_MONOTONIC t_mono_ns the packets share) DIRECTLY on the NAS -- never the shared local disk
(CLAUDE.md rule 5). It stops itself (only the recording) when the NAS has < MIN_FREE_GB free.

AFTER THE RUN: the sniffer's events for the window, pseudonymised (record_session.write_packets:
other players' names and chat replaced, CLAUDE.md rule 9), go beside the shards as
packets.jsonl.gz; events.jsonl is the timeline; manifest.json says what is where. Packets are
OFFLINE ground truth only: nothing here reads them during the run.

THE JUDGE (offline, packets): the safety (requests, GM acts, acts on the GM, map changes not ours)
and, per species, the monsters seen: distinct units, unit-seconds on screen (|dx| <= 15, |dy| <=
11 cells of the GM at 1 Hz), and the GM cells they were seen from.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import io
import json
import os
import random
import signal
import sys
import tarfile
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

NAS_ROOT = Path("/mnt/poring-lab-datasets/detector-collection")
REC_HZ = 5.0
REC_QUALITY = 80
SHARD_BYTES = 256 << 20
MIN_FREE_GB = 20.0
DWELL_S = 30.0
VIEW = (15, 11)  # cells from the GM still on screen (the 1280 x 720 game region, judge only)


def load_lattice(path: Path) -> list[tuple[int, int]]:
    doc = json.loads(Path(path).read_text())
    rows = doc["cells"] if isinstance(doc, dict) else doc
    cells = [(int(c["x"]), int(c["y"])) for c in rows]
    if not cells or len(set(cells)) != len(cells):
        raise SystemExit(f"{path}: an empty lattice or a repeated cell")
    return cells


def make_plan(map_name: str, cells: Sequence[tuple[int, int]], seed: int, dwell_s: float,
              max_minutes: float) -> dict[str, Any]:  # fmt: skip
    """PURE: collect_v2.Driver's plan for natural dwells only, the cells in a seeded order."""
    import collect_v2 as cv

    order = list(cells)
    random.Random(f"{map_name}:{seed}").shuffle(order)
    per = dwell_s + cv.SAME_MAP_SETTLE_S
    fit = max(1, int((max_minutes * 60.0 - cv.ENTRY_SETTLE_S) // per))
    spots = [{"i": i, "cell": list(c)} for i, c in enumerate(order)]
    lines = [{"line": f"@warp {map_name} {c[0]} {c[1]}"} for c in order]
    return {"map": map_name, "seed": seed, "spots": spots, "blocks": [], "portal_passes": [],
            "timing_s": {"dwell": dwell_s, "block": 0.0, "portal": 0.0}, "lines": lines,
            "fits_in_time_box": min(fit, len(spots)),
            "estimate_min": round((cv.ENTRY_SETTLE_S + len(spots) * per) / 60.0, 1)}  # fmt: skip


class JpegShards:
    """Appends JPEG frames to shard-NNNNNN.tar files of at most ``max_bytes`` each."""

    def __init__(self, directory: Path, max_bytes: int = SHARD_BYTES) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.shards: list[str] = []
        self.frames = 0
        self.bytes = 0
        self._tar: tarfile.TarFile | None = None
        self._size = 0

    def _put(self, name: str, body: bytes) -> None:
        if self._tar is None or self._size >= self.max_bytes:
            self.close()
            self.shards.append(f"shard-{len(self.shards):06d}.tar")
            self._tar = tarfile.open(self.dir / self.shards[-1], "w")  # noqa: SIM115 -- close()
            self._size = 0
        info = tarfile.TarInfo(name)
        info.size, info.mtime = len(body), int(time.time())
        self._tar.addfile(info, io.BytesIO(body))
        self._size += len(body) + 1024
        self.bytes += len(body)

    def add(self, frame_id: int, t_mono_ns: int, jpeg: bytes) -> None:
        key = f"{frame_id:09d}"
        self._put(f"{key}.jpg", jpeg)
        self._put(f"{key}.json", json.dumps({"frame_id": frame_id, "t_mono_ns": t_mono_ns},
                                            sort_keys=True).encode())  # fmt: skip
        self.frames += 1

    def close(self) -> None:
        if self._tar is not None:
            self._tar.close()
            self._tar = None


def read_jpeg_shard(path: Path) -> list[tuple[dict[str, Any], bytes]]:
    """(meta, jpeg bytes) per frame, in shard order."""
    out, pending = [], {}
    with tarfile.open(path) as tar:
        for m in tar:
            key, _, ext = m.name.partition(".")
            fh = tar.extractfile(m)
            assert fh is not None
            pending.setdefault(key, {})[ext] = fh.read()
            if {"jpg", "json"} <= set(pending[key]):
                item = pending.pop(key)
                out.append((json.loads(item["json"]), item["jpg"]))
    return out


def _recorder(out: str, region: tuple[int, int, int, int], stop: Any, hz: float, quality: int,
              shard_bytes: int, min_free_gb: float) -> None:  # fmt: skip
    """The recorder process (see the module doc)."""
    import ro_agent as r
    from PIL import Image

    screen = r.Screen()
    w = JpegShards(Path(out), shard_bytes)
    k, why = 0, "stopped"
    try:
        while not stop.is_set():
            t0 = time.monotonic()
            if k % 50 == 0:
                st = os.statvfs(out)
                if st.f_bavail * st.f_frsize < min_free_gb * 1e9:
                    why = f"under {min_free_gb} GB free"
                    break
            t, img = screen.grab(*region)
            buf = io.BytesIO()
            rgb = np.ascontiguousarray(img[..., 2::-1])
            Image.fromarray(rgb).save(buf, format="JPEG", quality=quality)
            w.add(k, t, buf.getvalue())
            k += 1
            time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - t0)))
    finally:
        w.close()
        (Path(out) / "recorder.json").write_text(json.dumps(
            {"frames": w.frames, "bytes": w.bytes, "shards": w.shards, "hz": hz,
             "quality": quality, "region": list(region), "ended": why}))  # fmt: skip


def preflight(map_name: str) -> dict[str, Any]:
    """No input: the path's UI gate readiness, the immunity record, the operator's lease."""
    import collect_v2 as cv
    import ro_agent as r
    import ui_gate

    checks: dict[str, Any] = {}
    try:
        ui_gate._require_ready()
        checks["ui_gate"] = "ok"
    except r.Stop as exc:
        checks["ui_gate"] = str(exc)
    try:
        ok, why = cv.immunity_ok(cv.read_json(cv.IMMUNE), cv.gm_marker())
        checks["immunity"] = "ok" if ok else why
    except Exception as exc:  # noqa: BLE001 -- unknown = fail closed
        checks["immunity"] = f"unknown (fail closed): {exc}"
    h = r.backend_health()
    checks["mode"] = "ok" if h.get("mode") == "ASSIST" and not h.get("lease_active") else (
        f"mode {h.get('mode')} lease {h.get('lease_active')}")  # fmt: skip
    checks["nas"] = "ok" if NAS_ROOT.parent.is_dir() else f"{NAS_ROOT.parent} not mounted"
    return {"pass": all(v == "ok" for v in checks.values()), "checks": checks, "map": map_name}


def cmd_plan(a: argparse.Namespace) -> int:
    p = make_plan(a.map, load_lattice(a.lattice), a.seed, a.dwell_s, a.max_minutes)
    print(json.dumps({k: v for k, v in p.items() if k not in ("lines", "spots")}
                     | {"cells": len(p["spots"]), "first": p["spots"][:3]}))  # fmt: skip
    return 0


def cmd_run(a: argparse.Namespace) -> int:  # noqa: PLR0915
    import multiprocessing as mp

    import client_layout as cl
    import collect_v2 as cv
    import dataset_activity as act
    import gm_vitals as gv
    import record_session as rs
    import ro_agent as r
    import ui_gate

    p = make_plan(a.map, load_lattice(a.lattice), a.seed, a.dwell_s, a.max_minutes)
    pre = preflight(a.map)
    if not pre["pass"]:
        print(json.dumps({"ran": False, **pre}))
        return 2
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-{a.map}-{a.label}"
    out = NAS_ROOT / a.map / sid
    (out / "frames").mkdir(parents=True, exist_ok=False)
    stop = {"why": None}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(why="sigterm"))
    deadline = time.monotonic() + a.max_minutes * 60.0
    counts: dict[str, int] = {"gm_failures": 0, "gm_disabled": 0}
    limit = cv.guard_limit()
    ctx = mp.get_context("spawn")
    stop_rec = ctx.Event()
    region = tuple(r.game_region())
    rec = ctx.Process(target=_recorder, args=(str(out / "frames"), region, stop_rec, REC_HZ,
                                              REC_QUALITY, SHARD_BYTES, MIN_FREE_GB),
                      daemon=True)  # fmt: skip
    reason, t0, t1, layout = "not_started", r.ns(), 0, None
    with (out / "events.jsonl").open("a") as log, r.session("warp-watch") as (agent, screen):

        def note(event: str, **fields: Any) -> None:
            rec_ = {"t_mono_ns": r.ns(), "t_wall": time.strftime("%H:%M:%S"), "map": a.map,
                    "event": event, **fields}  # fmt: skip
            log.write(json.dumps(rec_, default=str) + "\n")
            log.flush()

        def send(text: str) -> bool:
            if counts["gm_disabled"]:
                return False
            n = cv.repeat_count(cv.guard_state(), text)
            if n >= limit:
                note("guard_would_refuse", gm_line=text, n=n)
                return False
            return bool(act.safe_gm(agent, screen, text, counts))

        def vitals() -> str | None:
            dead = r.is_state(screen, gv.DEAD_STATE)
            frame = r.grab_after(screen, r.game_region(), r.ns())
            return gv.vitals_action(gv.hp_fraction(frame), dead)

        def stopped() -> str | None:
            if stop["why"]:
                return str(stop["why"])
            if counts["gm_disabled"]:
                return "gm_disabled"
            return "max_minutes" if time.monotonic() >= deadline else None

        try:
            r.minimize_consoles(agent, screen)
            clean = ui_gate.ensure_clear(agent, screen, why="warp-watch:start")
            # the UI layout, read from pixels (no input): the labels' UI rects follow it
            lay = cl.read(cl._grab_rgb(screen), cl.load_templates())
            layout = next((n for n in cl.LAYOUTS if cl.matches(lay, n)), None)
            if layout is None:
                raise r.Stop(f"warp-watch: the client's UI layout is neither of {cl.LAYOUTS}")
            rec.start()
            t0 = r.ns()
            note("run_start", plan={k: v for k, v in p.items() if k != "lines"}, preflight=pre,
                 ui_gate=clean, sid=sid, region=list(region), ui_layout=layout)  # fmt: skip
            d = cv.Driver(p, send=send, idle=agent.idle, vitals=vitals, note=note,
                          stopped=stopped, ns=r.ns, live_block=None)  # fmt: skip
            reason = d.run(False)
            note("run_end", reason=reason, counts=dict(d.counts), gm=counts)
            if a.back and not counts["gm_disabled"]:
                bm, bx, by = a.back.split(",")
                ok = send(f"@warp {bm} {int(bx)} {int(by)}")
                note("back", gm_line=f"@warp {bm} {bx} {by}", ok=ok)
                time.sleep(cv.ENTRY_SETTLE_S)
        except r.Stop as exc:
            reason = f"stop: {exc}"
            note("run_end", reason=reason, gm=counts)
        finally:
            t1 = r.ns()
            stop_rec.set()
            rec.join(timeout=30)
    packets = 0
    with contextlib.suppress(Exception):
        events, _anchor = rs.write_packets(out, t0, t1)
        packets = len(events)
    man = {"sid": sid, "map": a.map, "seed": a.seed, "label": a.label, "reason": reason,
           "t0_ns": t0, "t1_ns": t1, "packets": packets, "rec_hz": REC_HZ,
           "quality": REC_QUALITY, "gm": counts, "dwell_s": a.dwell_s, "ui_layout": layout,
           "backend": "rdp", "size": [int(region[2]), int(region[3])],
           "recorder": json.loads((out / "frames" / "recorder.json").read_text())
           if (out / "frames" / "recorder.json").exists() else None}  # fmt: skip
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({"ran": True, "out": str(out), **{k: man[k] for k in
                      ("reason", "packets", "gm")}}))  # fmt: skip
    return 0 if reason in ("done", "max_minutes") else 1


def sightings(packets: Sequence[dict[str, Any]], t0: int, t1: int, view: tuple[int, int] = VIEW,
              step_ns: int = 1_000_000_000) -> dict[str, Any]:  # fmt: skip
    """PURE: per monster class (job), the distinct units seen and the unit-seconds within ``view``
    cells of the GM, sampled every ``step_ns`` over [t0, t1] (Timeline.frame_world)."""
    from poring_dataset.timeline import Timeline

    tl = Timeline(packets)
    units: dict[int, set[int]] = defaultdict(set)
    secs: Counter[int] = Counter()
    spots: dict[int, set[tuple[int, int]]] = defaultdict(set)
    t = t0
    while t <= t1:
        fw = tl.frame_world(t)
        if fw.self_pos is not None:
            sx, sy = fw.self_pos
            for e in fw.entities:
                if e.objtype != 5 or e.hidden:
                    continue
                if abs(e.x - sx) <= view[0] and abs(e.y - sy) <= view[1]:
                    units[e.job].add(e.gid)
                    secs[e.job] += 1
                    spots[e.job].add((int(sx), int(sy)))
        t += step_ns
    return {str(j): {"units": len(units[j]), "unit_seconds": secs[j], "from_cells": len(spots[j])}
            for j in sorted(units)}  # fmt: skip


def cmd_judge(a: argparse.Namespace) -> int:
    import collect_v2 as cv

    d = Path(a.session)
    man = json.loads((d / "manifest.json").read_text())
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        packets = [json.loads(x) for x in fh]
    timeline = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    safety = cv.judge(packets, timeline)
    view = tuple(int(v) for v in a.view.split(",")) if a.view else VIEW
    out = {"sid": man["sid"], "safety": safety,
           "sightings": sightings(packets, int(man["t0_ns"]), int(man["t1_ns"]), view)}  # fmt: skip
    (d / "judge.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run"):
        q = sub.add_parser(name)
        q.add_argument("--map", required=True)
        q.add_argument("--lattice", type=Path, required=True)
        q.add_argument("--seed", type=int, required=True)
        q.add_argument("--dwell-s", type=float, default=DWELL_S)
        q.add_argument("--max-minutes", type=float, default=50.0)
        if name == "run":
            q.add_argument("--label", required=True)
            q.add_argument("--back", default=None, help="MAP,X,Y: the @warp after the dwells")
    q = sub.add_parser("judge")
    q.add_argument("session")
    q.add_argument("--view", default=None)
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "judge": cmd_judge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
