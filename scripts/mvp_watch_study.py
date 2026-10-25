#!/usr/bin/env python3
"""OFFLINE study for scripts/mvp_watch.py (docs/planning/orclord-recognizer.md): the per-frame truth
from the packets, the crops a recognizer is fitted on, and the held-out score.

    mvp_watch_study.py truth SESSION --layout standard|hunt [--map MAP] --out TRUTH.json
    mvp_watch_study.py fit   --watch S --watch-truth T --events E --pilot S T [--extra S T]...
                             --work DIR --out MODEL.npz        DEV only (section 3 + Amendment B)
    mvp_watch_study.py score --model MODEL.npz --sha256 HEX --watch S --watch-truth T --events E
                             --pilot S T [--supplement S T]... --out SCORE.json   HELD-OUT, once
    mvp_watch_study.py entries --model MODEL.npz --sha256 HEX --watch S --watch-truth T --events E
                             --hunt S T [--hunt S T]... --out SCORE.json   ROUND 2 (10), once

OFFLINE ONLY (ADR-0007: packets are ground truth, never an input at decision time). Reads a
recorder session (manifest, PNG tar shards, packets.jsonl.gz), the client's GAT and the decoded
sprites (client-derived: /dev/shm only, never committed) and the local KB. No client, no GPU, no
input. The projection is the label pipeline's own (payf07-detector.md 4-5): the fitted RDP camera
with the map's GAT altitude, predict_sprite's box for the Timeline state, 1d = 120 ms and k = 0.14
(payf07's frozen params, the same recording path), labels_for_v1's on-screen and UI rules.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ORC_LORD, ORC_ARCHERS = 1190, (1189, 1473)
MVP_PARTY = (ORC_LORD, *ORC_ARCHERS)
NEGATIVE_SPECIES = {1023: "Orc Warrior", 1273: "Orc Lady", 1686: "Orc Baby", 1031: "Poporing",
                    1079: "Blue Plant", 1080: "Green Plant"}  # fmt: skip
NAMES = {ORC_LORD: "Orc Lord", 1189: "Orc Archer", 1473: "Orc Archer (G)", **NEGATIVE_SPECIES}
OFFSET_MS = 120.0  # 1d: payf07's frozen params (P1, the same RDP frame bus, PNG recorder v5)
K = 0.14  # payf07's frozen k
MAP = "gef_fild10"
SETTLE_NS = 5_000_000_000  # a map change: the loading screen and the settle (payf07 4f)
GM_WINDOW_NS = 2_000_000_000  # labels.gm_windows
# Amendment A (orclord-recognizer.md, DEV frames 110-112, 335-336, 346): the client keeps drawing a
# dying unit (and the Orc Lord's aura) after its vanish packet, and draws the aura at a spawn before
# the 1d-shifted Timeline has the unit. Frames this close to a party unit's vanish / appearance are
# neither positive nor negative.
AFTER_VANISH_NS = 4_000_000_000
AROUND_APPEAR_NS = (500_000_000, 1_000_000_000)  # before, after a "new" appearance
SPRITES = Path("/dev/shm/poring-lab-tmp/gef10-prep/sprites/data/sprite/몬스터")
SPRITE_NAMES = Path("/dev/shm/poring-lab-tmp/gef10-prep/kb-sprites/monster_sprite_names.json")
MAIN = Path("/home/batt/docker/poring-lab")  # the main checkout: data/kb and the mapcache


@dataclass(frozen=True)
class Unit:
    gid: int
    job: int
    box: tuple[float, float, float, float]  # the predicted sprite box, unclipped
    state: str
    cell: tuple[float, float]
    in_view: bool  # labels_for_v1's rule: >= half the box on screen, < half under the UI


# --- pure parts -------------------------------------------------------------------------------


def frame_flags(
    t: int,
    map_changes: Sequence[int],
    gm: Sequence[int],
    party_vanish: Sequence[int] = (),
    party_new: Sequence[int] = (),
) -> list[str]:
    """Why a frame is special: within SETTLE_NS after a map change (``settle``), within
    GM_WINDOW_NS after a GM command (``gm``), within AFTER_VANISH_NS after an MVP-party unit's
    vanish or around its appearance (``party_edge``: Amendment A, neither positive nor negative)."""
    out = []
    if any(0 <= t - c <= SETTLE_NS for c in map_changes):
        out.append("settle")
    if any(0 <= t - g <= GM_WINDOW_NS for g in gm):
        out.append("gm")
    before, after = AROUND_APPEAR_NS
    if any(0 <= t - v <= AFTER_VANISH_NS for v in party_vanish) or any(
        -before <= t - a <= after for a in party_new
    ):
        out.append("party_edge")
    return out


def party_times(events: Iterable[dict[str, Any]]) -> tuple[list[int], list[int]]:
    """(vanish times, "new" appearance times) of every MVP-party unit (by its gid's job)."""
    party: set[int] = set()
    vanish, new = [], []
    for e in events:
        if e.get("type") == "entity_appear" and e.get("job") in MVP_PARTY:
            party.add(int(e["gid"]))
            if e.get("kind") == "new":
                new.append(int(e["t_mono_ns"]))
        elif e.get("type") == "entity_vanish" and e.get("gid") in party:
            vanish.append(int(e["t_mono_ns"]))
    return sorted(vanish), sorted(new)


def in_view(box: tuple[float, float, float, float], size: tuple[int, int],
            ui_rects: Sequence[tuple[int, int, int, int]]) -> bool:  # fmt: skip
    """labels_for_v1's visibility rule (half the box on screen, under half behind the UI)."""
    from poring_dataset.ui_layout import covered_fraction

    x0, y0, x1, y1 = box
    w, h = size
    bw, bh = x1 - x0, y1 - y0
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    on_screen = cx1 - cx0 >= bw / 2 and cy1 - cy0 >= bh / 2
    xywh = tuple((a, b, c - a, d - b) for a, b, c, d in ui_rects)
    return bool(on_screen and covered_fraction(box, xywh) < 0.5)


def episodes(rows: Sequence[dict[str, Any]], jobs: Iterable[int] = MVP_PARTY,
             gap_s: float = 3.0) -> list[dict[str, Any]]:  # fmt: skip
    """The in-view episodes of the MVP party: maximal runs of frames with at least one unit of
    ``jobs`` in view, split where no such frame occurs for more than ``gap_s``. Each episode:
    its first / last frame time, the frame ids, and whether the Orc Lord itself was in view."""
    want = set(jobs)
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for r in rows:
        seen = [u for u in r["units"] if u["job"] in want and u["in_view"]]
        if not seen:
            continue
        t = int(r["t"])
        if cur is None or (t - cur["t1"]) / 1e9 > gap_s:
            cur = {"t0": t, "t1": t, "frames": [], "lord": False}
            out.append(cur)
        cur["t1"] = t
        cur["frames"].append(int(r["frame_id"]))
        cur["lord"] = cur["lord"] or any(u["job"] == ORC_LORD for u in seen)
    return out


def png_index(session: Path, manifest: dict[str, Any]) -> list[Any]:
    """map_labels.png_index, tolerant of a TRUNCATED last shard (a recording stopped by its IO
    guard mid-write, e.g. 20261025T204315-rdp-rogue-s1): the complete members before the cut are
    kept, a frame missing its png or json is dropped."""
    import tarfile

    import qa_export

    pngs: dict[str, tuple[Path, int, int]] = {}
    metas: dict[str, dict[str, Any]] = {}
    for name in manifest["shards"]:
        shard = session / str(name)
        if not shard.exists():
            continue
        try:
            with tarfile.open(shard) as tar:
                for m in tar:
                    key, _, ext = m.name.partition(".")
                    if ext == "png" and m.offset_data + m.size <= shard.stat().st_size:
                        pngs[key] = (shard, m.offset_data, m.size)
                    elif ext == "json":
                        fh = tar.extractfile(m)
                        assert fh is not None
                        metas[key] = json.loads(fh.read())
        except (tarfile.ReadError, EOFError, json.JSONDecodeError):
            continue  # the cut: what was read before it stays
    out = [qa_export.JpegRef(int(metas[k]["frame_id"]), int(metas[k]["t_mono_ns"]), *pngs[k])
           for k in set(pngs) & set(metas)]  # fmt: skip
    return sorted(out, key=lambda r: r.frame_id)


# --- the truth ----------------------------------------------------------------------------------


def _events(session: Path) -> list[dict[str, Any]]:
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


def truth(session: Path, layout: str, *, kb: Path, mapcache_dir: Path,
          offset_ms: float = OFFSET_MS, map_name: str = MAP) -> dict[str, Any]:  # fmt: skip
    """Per frame of a recorder session: every monster's predicted sprite box (unclipped), its
    Timeline state and whether it is in view, at the frame's capture time - 1d. Units are kept on
    ``map_name`` only (Amendment 10a: round 2's watch is on prt_fild08; the projection reads that
    map's GAT from the same GAT_DIR, nothing else changes)."""
    import client_layout
    import map_labels as ml
    import qa_export

    from poring_dataset import mapcache
    from poring_dataset.camera import load_indoor_table, map_key
    from poring_dataset.labels import ONE_SHOT, STATE_ACTION
    from poring_dataset.projection import camera_file
    from poring_dataset.render import Actor, MonsterAction, load_scene, predict_sprite
    from poring_dataset.timeline import Timeline

    qa_export.KB_CLASSES = kb / "classes.json"
    sheets = qa_export.Sheets(SPRITES, stems=qa_export.sprite_stems(SPRITE_NAMES))
    manifest = json.loads((session / "manifest.json").read_text())
    ml.check_recording(manifest)
    refs = png_index(session, manifest)
    events = _events(session)
    tl = Timeline(events, mapcache.load(mapcache_dir, prere=True), snapshot_every=32)
    camera = json.loads(camera_file("rdp").read_text())
    indoor = load_indoor_table()
    size = (int(manifest["game_region"][2]), int(manifest["game_region"][3]))
    rects = client_layout.RECTS[layout]
    changes = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change")
    gm = sorted(int(e["t_mono_ns"]) for e in events if e.get("gm_command"))
    vanish, new = party_times(events)
    rows = []
    for ref in refs:
        t = int(ref.t_mono_ns)
        tw = t - int(offset_ms * 1e6)
        world = tl.frame_world(tw)
        row: dict[str, Any] = {"frame_id": ref.frame_id, "t": t, "map": world.map,
                               "self": world.self_pos,
                               "flags": frame_flags(t, changes, gm, vanish, new),
                               "units": [], "players": 0}  # fmt: skip
        rows.append(row)
        if world.self_pos is None or not world.map or map_key(world.map) != map_name:
            continue
        scene = load_scene(camera, world.map, world.self_pos, indoor_table=indoor)
        for ent in world.entities:
            if ent.hidden:
                continue
            if ent.objtype == 0 and ent.gid != world.aid:
                row["players"] += 1
            if ent.objtype != 5:
                continue
            sh = sheets(ent.job)
            st = tl.state(ent.gid, tw)
            if sh is None or st is None:
                row["units"].append({"gid": ent.gid, "job": ent.job, "box": None,
                                     "state": None, "in_view": False})  # fmt: skip
                continue
            action = STATE_ACTION.get(st.state, MonsterAction.IDLE)
            elapsed = st.elapsed_ms if action in ONE_SHOT else None
            heading = st.facing if st.facing is not None else (ent.heading or 0)
            pred = predict_sprite(Actor((float(ent.x), float(ent.y)), int(heading), action,
                                        elapsed_ms=elapsed, duration_ms=st.duration_ms),
                                  sh, scene, K)  # fmt: skip
            if pred is None:
                continue
            box = tuple(round(float(v), 1) for v in pred.box)
            row["units"].append({"gid": ent.gid, "job": ent.job, "box": box, "state": st.state,
                                 "cell": (round(ent.x, 2), round(ent.y, 2)),
                                 "in_view": in_view(box, size, rects)})  # fmt: skip
    return {"session": manifest["session_id"], "layout": layout, "offset_ms": offset_ms, "k": K,
            "size": size, "map": map_name, "frames": rows,
            "missing_sheets": sheets.missing}  # fmt: skip


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    """Counts: frames, frames with each species in view, the MVP party's episodes."""
    rows = doc["frames"]
    target = str(doc.get("map", MAP))
    on_map = [r for r in rows if r["map"] and r["map"].startswith(target)]
    per = Counter()
    units = Counter()
    for r in on_map:
        jobs = {u["job"] for u in r["units"] if u["in_view"]}
        for j in jobs:
            per[NAMES.get(j, str(j))] += 1
        for u in r["units"]:
            if u["in_view"]:
                units[NAMES.get(u["job"], str(u["job"]))] += 1
    party = [r for r in on_map if any(u["in_view"] and u["job"] in MVP_PARTY for u in r["units"])]
    lord = [r for r in on_map if any(u["in_view"] and u["job"] == ORC_LORD for u in r["units"])]
    return {"frames": len(rows), "on_map": len(on_map), "frames_with": dict(per),
            "boxes_in_view": dict(units), "party_frames": len(party), "lord_frames": len(lord),
            "episodes": len(episodes(on_map))}  # fmt: skip


# --- the split (orclord-recognizer.md section 3) -----------------------------------------------

DEV_CELLS = frozenset(range(8))
HELD_CELLS = frozenset(range(8, 15))
PILOT_DEV_S = 300.0
RECALL_S = 1.1  # the episode's first or second recorded frame (1 fps)
EPISODE_GAP_S = 3.0


def watch_times(events_path: Path) -> tuple[list[int], list[int]]:
    """(spawn times, @killmonster2 times) of the watch's events.jsonl (CLOCK_MONOTONIC ns)."""
    rows = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    spawns = [int(r["t_ns"]) for r in rows if r.get("kind") == "spawn"]
    kills = [int(r["t_ns"]) for r in rows if r.get("kind") == "killmonster2"]
    return spawns, kills


def cell_of(t: int, spawns: Sequence[int]) -> int:
    """The lattice cell a watch frame belongs to: the last spawn at or before it (-1: before)."""
    import bisect

    return bisect.bisect_right(spawns, t) - 1


def on_map(row: dict[str, Any], map_name: str = MAP) -> bool:
    return bool(row["map"]) and str(row["map"]).startswith(map_name)


def party_in_view(row: dict[str, Any]) -> bool:
    return any(u["in_view"] and u["job"] in MVP_PARTY for u in row["units"])


def party_on_screen(row: dict[str, Any], size: tuple[int, int] = (1280, 720)) -> bool:
    for u in row["units"]:
        if u["job"] in MVP_PARTY and u["box"] is not None:
            x0, y0, x1, y1 = u["box"]
            if x1 > 0 and y1 > 0 and x0 < size[0] and y0 < size[1]:
                return True
    return False


def kind_of(row: dict[str, Any]) -> str:
    """pos: the party in view; neg: no party box even partly on screen and not a party edge
    (Amendment A); edge: neither."""
    if party_in_view(row):
        return "pos"
    if not party_on_screen(row) and "party_edge" not in row["flags"]:
        return "neg"
    return "edge"


def pilot_part(rows: Sequence[dict[str, Any]], dev_s: float = PILOT_DEV_S) -> dict[int, str]:
    """frame_id -> dev | held for a hunting session's frames on the map (section 3)."""
    on = [r for r in rows if on_map(r)]
    if not on:
        return {}
    t0 = int(on[0]["t"])
    return {int(r["frame_id"]): ("dev" if (int(r["t"]) - t0) / 1e9 < dev_s else "held") for r in on}


def cell_scores(seq: Sequence[tuple[float, str, bool]], recall_s: float = RECALL_S,
                gap_s: float = EPISODE_GAP_S) -> dict[str, Any]:  # fmt: skip
    """One cell's frames in time order as (t_s, kind, seen) -> its episodes (runs of pos frames
    split by > gap_s without one), each with its delay (first seen pos frame - first pos frame;
    None: never seen) and whether it is within recall_s."""
    eps: list[dict[str, Any]] = []
    last = None
    for t, kind, seen in seq:
        if kind != "pos":
            continue
        if last is None or t - last > gap_s:
            eps.append({"t0": t, "delay": None, "frames": 0})
        last = t
        e = eps[-1]
        e["frames"] += 1
        if seen and e["delay"] is None:
            e["delay"] = round(t - e["t0"], 3)
    for e in eps:
        e["within"] = e["delay"] is not None and e["delay"] <= recall_s
        e["first_frame"] = e["delay"] == 0.0
    return {"episodes": eps}


def fp_rate(n_fp: int, n_frames: int, fps: float = 1.0) -> float | None:
    """False positives per 10 min of frames recorded at ``fps``."""
    return None if n_frames == 0 else n_fp / n_frames * 600.0 * fps


# --- frames ---------------------------------------------------------------------------------------


def half_frames(session: Path, keep: set[int], out: Path) -> tuple[Any, list[int]]:
    """Decode the kept frames once into a half-res memmap (out, /dev/shm): (array, frame ids).
    A memmap left by an earlier run with the same frame ids is reused."""
    import map_labels as ml

    ids_path = out.with_name(out.name + ".ids.json")
    if out.exists() and ids_path.exists():
        ids = json.loads(ids_path.read_text())
        if set(ids) == keep:
            arr = np.load(out, mmap_mode="r")
            if len(arr) == len(ids):
                return arr, ids
    manifest = json.loads((session / "manifest.json").read_text())
    refs = [r for r in png_index(session, manifest) if r.frame_id in keep]
    arr = np.lib.format.open_memmap(out, mode="w+", dtype=np.uint8, shape=(len(refs), 360, 640, 3))
    for i, r in enumerate(refs):
        arr[i] = ml.read_png(r)[::2, ::2]
    arr.flush()
    ids = [r.frame_id for r in refs]
    ids_path.write_text(json.dumps(ids))
    return arr, ids


# --- the fit (DEV only) ---------------------------------------------------------------------------


def _box_mask(box: Sequence[float], pad_side: float, pad_bottom: float, pad_top: float = 0.0
              ) -> tuple[slice, slice]:  # fmt: skip
    x0, y0, x1, y1 = (v / 2 for v in box)
    w, h = x1 - x0, y1 - y0
    ya, yb = int(max(0, y0 - pad_top * h)), int(min(360, y1 + pad_bottom * h))
    xa, xb = int(max(0, x0 - pad_side * w)), int(min(640, x1 + pad_side * w))
    return slice(ya, yb), slice(xa, xb)


def colour_hists(watch: Any, wids: list[int], rows: dict[int, dict[str, Any]],
                 spawns: Sequence[int], kills: Sequence[int], changes: Sequence[int],
                 cells: Iterable[int], ui: npt.NDArray[np.bool_]) -> dict[str, Any]:  # fmt: skip
    """The body LUT's histograms from the watch: the party's FOREGROUND pixels (each cell's
    background = the median of its frames without units, before the spawn and after the kill, at
    the same camera), the other species' foreground, and the background."""
    import mvp_watch as mw

    nb = mw.NBINS
    hp, ho, hn = np.zeros(nb), np.zeros(nb), np.zeros(nb)
    t_of = {fid: int(rows[fid]["t"]) for fid in wids}
    pos_of = {fid: i for i, fid in enumerate(wids)}
    for c in cells:
        s, k = spawns[c], kills[c]
        prev = max(m for m in changes if m < s)
        nxt = min((m for m in changes if m > k), default=10**30)
        bg_ids = [f for f in wids if prev + 4e9 < t_of[f] < s or k + 3e9 < t_of[f] < nxt]
        dw_ids = [f for f in wids if s + 1e9 < t_of[f] < k]
        if not bg_ids:
            continue
        bg = np.median(np.stack([watch[pos_of[f]] for f in bg_ids]).astype(np.int16), axis=0)
        for f in dw_ids:
            img = np.asarray(watch[pos_of[f]])
            q = mw.lut_index(img)
            fg = (np.abs(img.astype(np.int16) - bg).max(axis=2) > 30) & ~ui
            pm, pz, om = (np.zeros((360, 640), bool) for _ in range(3))
            for u in rows[f]["units"]:
                if u["box"] is None:
                    continue
                if u["job"] in MVP_PARTY:
                    pm[_box_mask(u["box"], 0.1, 0.15)] = True
                    pz[_box_mask(u["box"], 0.4, 0.4, 0.2)] = True
                else:
                    om[_box_mask(u["box"], 0.05, 0.05)] = True
            hp += np.bincount(q[fg & pm & ~om], minlength=nb)
            ho += np.bincount(q[fg & om & ~pm], minlength=nb)
            hn += np.bincount(q[~pz & ~ui & ~om][::4], minlength=nb)
        for f in bg_ids:
            hn += np.bincount(mw.lut_index(np.asarray(watch[pos_of[f]]))[~ui], minlength=nb)
    return {"hP": hp, "hO": ho, "hN": hn}


def blur3(h: npt.NDArray[np.float64], passes: int = 1) -> npt.NDArray[np.float64]:
    """A [1, 2, 1] / 4 blur along each axis of the 32^3 colour histogram."""
    a = h.reshape(32, 32, 32).astype(np.float64)
    for _ in range(passes):
        for ax in range(3):
            p = np.pad(a, [(1, 1) if i == ax else (0, 0) for i in range(3)], mode="edge")

            def sl(o: int, ax: int = ax) -> tuple[slice, ...]:
                return tuple(slice(o, o + 32) if i == ax else slice(None) for i in range(3))

            a = 0.25 * p[sl(0)] + 0.5 * p[sl(1)] + 0.25 * p[sl(2)]
    out: npt.NDArray[np.float64] = a.reshape(-1)
    return out


def llr_of(pos: npt.NDArray[np.float64], neg: npt.NDArray[np.float64], passes: int = 1,
           min_pos: float = 3.0, floor: float = -3.0) -> npt.NDArray[np.float32]:  # fmt: skip
    """The colour log-likelihood ratio, blurred; a bin with under ``min_pos`` (blurred) positive
    pixels gets ``floor`` (an unseen colour is never evidence FOR the party)."""
    bp, bn = blur3(pos, passes), blur3(neg, passes)
    out = np.log((bp / bp.sum() + 1e-9) / (bn / bn.sum() + 1e-9))
    out[bp < min_pos] = floor
    return np.maximum(out, floor).astype(np.float32)


def logreg(x: npt.NDArray[np.float32], y: npt.NDArray[np.float64], wts: npt.NDArray[np.float64],
           l2: float = 1.0, iters: int = 12) -> tuple[npt.NDArray[np.float32], float]:  # fmt: skip
    """Weighted L2 logistic regression by Newton steps on standardised features; returns the
    weights and bias in the raw features' units."""
    mu, sd = x.mean(0), x.std(0) + 1e-3
    z = np.hstack([(x - mu) / sd, np.ones((len(x), 1), np.float32)]).astype(np.float64)
    w = np.zeros(z.shape[1])
    reg = l2 * np.r_[np.ones(len(w) - 1), 0.0]
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(z @ w, -30, 30)))
        g = z.T @ (wts * (p - y)) + reg * w
        hess = (z * (wts * p * (1 - p))[:, None]).T @ z + np.diag(reg)
        w -= np.linalg.solve(hess, g)
    wf = (w[:-1] / sd).astype(np.float32)
    return wf, float(w[-1] - (w[:-1] * mu / sd).sum())


@dataclass
class Item:
    feats: npt.NDArray[np.float32]
    valid: npt.NDArray[np.bool_]
    kind: str  # pos | neg | edge | hunt
    party: list[tuple[int, int]]  # the party units' window cells (top-left)
    aura: float
    zone: npt.NDArray[np.bool_]  # windows whose foot is in mvp_watch.SELF_ZONE


def make_items(frames: Any, fids: Sequence[int], rows: dict[int, dict[str, Any]],
               model: Any, rects: Any, hunt: bool) -> list[Item]:  # fmt: skip
    import mvp_watch as mw

    out = []
    for i, fid in enumerate(fids):
        half = np.asarray(frames[i])
        if not mw.game_view(half, model):
            continue
        m = mw.scores(half, model, rects)
        row = rows[fid]
        party = []
        for u in row["units"]:
            if u["job"] in MVP_PARTY and u["in_view"] and u["box"]:
                x0, _, x1, y1 = (v / 2 for v in u["box"])
                party.append(mw.foot_window((x0 + x1) / 2, y1))
        out.append(Item(m["feats"], m["valid"], "hunt" if hunt else kind_of(row), party,
                        float(m["aura_map"].max()), m["zone"]))  # fmt: skip
    return out


def train_party(items: Sequence[Item], rounds: int = 2, seed: int = 0, l2: float = 1.0
                ) -> tuple[npt.NDArray[np.float32], float]:  # fmt: skip
    """Positives: each party unit's window and its 4 neighbours; negatives: random windows of
    every frame away from the party, then ``rounds`` of hard negatives (each negative frame's
    top 20 windows scoring above -2)."""
    import mvp_watch as mw

    rng = np.random.default_rng(seed)
    xp, xn = [], []
    for it in items:
        wv = mw.window_vectors(it.feats)
        oh, ow = wv.shape[:2]
        near = np.zeros((oh, ow), bool)
        for cy, cx in it.party:
            near[max(0, cy - 2) : cy + 3, max(0, cx - 2) : cx + 3] = True
            for dy, dx in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= cy + dy < oh and 0 <= cx + dx < ow:
                    xp.append(wv[cy + dy, cx + dx])
        if it.kind == "edge":
            continue
        cand = np.argwhere(it.valid & ~near)
        if len(cand):
            n = 60 if it.kind == "pos" else 150
            pick = cand[rng.choice(len(cand), min(len(cand), n), replace=False)]
            xn.extend(wv[pick[:, 0], pick[:, 1]])
    pos, neg = np.array(xp, np.float32), np.array(xn, np.float32)
    w, b = np.zeros(1, np.float32), 0.0
    for r in range(rounds + 1):
        x = np.vstack([pos, neg])
        y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
        wts = np.r_[np.full(len(pos), len(neg) / len(pos) * 0.5), np.ones(len(neg))]
        w, b = logreg(x, y, wts, l2)
        if r == rounds:
            break
        hard = []
        for it in items:
            if it.kind not in ("neg", "hunt"):
                continue
            sm = mw.window_scores(it.feats, w.reshape(mw.N_FEATURES, *mw.WIN), b)
            sm[~it.valid] = -np.inf
            wv = mw.window_vectors(it.feats)
            for j in np.argsort(sm, axis=None)[-20:]:
                yy, xx = divmod(int(j), sm.shape[1])
                if sm[yy, xx] > -2:
                    hard.append(wv[yy, xx])
        if hard:
            neg = np.vstack([neg, np.array(hard, np.float32)])
    return w.reshape(mw.N_FEATURES, *mw.WIN), b


AURA_THR = 0.08  # Amendment B: the aura rule's frozen threshold (DEV hunting max 0.065)
LIN_MARGIN = 1.0  # Amendment B: the party threshold = the DEV negatives' max + this
BODY_HUNT_W, BODY_OTHER_W = 10.0, 5.0  # the body LUT's weights of hunting / other-species pixels


def _rows(path: Path) -> dict[int, dict[str, Any]]:
    return {int(r["frame_id"]): r for r in json.loads(path.read_text())["frames"]}


def _changes(session: Path) -> list[int]:
    return sorted(int(e["t_mono_ns"]) for e in _events(session) if e.get("type") == "map_change")


def cmd_fit(a: argparse.Namespace) -> dict[str, Any]:
    """DEV only: the watch's cells 0-7 (and before the first spawn), the pilot's first 300 s on
    the map, and every --extra hunting session (Amendment B)."""
    import mvp_watch as mw

    a.work.mkdir(parents=True, exist_ok=True)
    wrows = _rows(a.watch_truth)
    spawns, kills = watch_times(a.events)
    dev_w = {f for f, r in wrows.items()
             if on_map(r) and cell_of(int(r["t"]), spawns) in DEV_CELLS | {-1}}  # fmt: skip
    watch, wids = half_frames(a.watch, dev_w, a.work / "watch-dev.npy")
    hunts = []
    for i, (session, tpath) in enumerate([a.pilot, *(a.extra or [])]):
        rows = _rows(Path(tpath))
        part = pilot_part(list(rows.values()))
        keep = {f for f, v in part.items() if v == "dev"} if i == 0 else set(part)
        if any(party_on_screen(rows[f]) for f in keep):
            raise SystemExit(f"{session}: an MVP-party unit is on screen in a hunting frame")
        arr, ids = half_frames(Path(session), keep, a.work / f"hunt-{i}.npy")
        hunts.append((arr, ids, rows))
    ui_std = mw.rect_mask((360, 640), mw.STANDARD_RECTS)
    ui_hunt = mw.rect_mask((360, 640), mw.HUNT_RECTS)
    changes = _changes(a.watch)
    h = colour_hists(watch, wids, wrows, spawns, kills, changes, sorted(DEV_CELLS), ui_std)
    hh = np.zeros(mw.NBINS)
    for arr, _, _ in hunts:
        for img in arr:
            hh += np.bincount(mw.lut_index(np.asarray(img))[~ui_hunt], minlength=mw.NBINS)
    body = llr_of(h["hP"], h["hN"] + BODY_HUNT_W * hh + BODY_OTHER_W * h["hO"])
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    title = np.median(
        np.stack(
            [
                np.asarray(arr[j])[y0:y1, x0:x1].astype(np.float32).mean(axis=2)
                for arr, _, _ in hunts
                for j in range(0, len(arr), 10)
            ]
        ),
        axis=0,
    )
    zero = np.zeros((mw.N_FEATURES, *mw.WIN), np.float32)
    model0 = mw.Model(body_lut=body, lin_w=zero, lin_b=0.0, lin_thr=0.0, aura_thr=AURA_THR,
                      title=title.astype(np.float32))  # fmt: skip
    items = make_items(watch, wids, wrows, model0, mw.STANDARD_RECTS, hunt=False)
    for arr, ids, rows in hunts:
        items += make_items(arr, ids, rows, model0, mw.HUNT_RECTS, hunt=True)
    w, b = train_party(items)
    out_best, in_best = [], []  # each frame's best window outside / inside SELF_ZONE
    for it in items:
        sm = mw.window_scores(it.feats, w, b)
        sm[~it.valid] = -np.inf
        out_best.append(float(np.where(it.zone, -np.inf, sm).max()))
        in_best.append(float(np.where(it.zone, sm, -np.inf).max()))
    is_neg = [it.kind in ("neg", "hunt") for it in items]
    lin_thr = max(s for s, n in zip(out_best, is_neg, strict=True) if n) + LIN_MARGIN
    zone_thr = max(s for s, n in zip(in_best, is_neg, strict=True) if n) + LIN_MARGIN
    penalty = max(0.0, zone_thr - lin_thr)
    model = mw.Model(body_lut=body, lin_w=w, lin_b=b, lin_thr=lin_thr, aura_thr=AURA_THR,
                     title=title.astype(np.float32), zone_penalty=penalty)  # fmt: skip
    sha = mw.save(a.out, model)
    best = [max(o, i - penalty) for o, i in zip(out_best, in_best, strict=True)]
    negs = [s for s, n in zip(best, is_neg, strict=True) if n]
    pos = [(s, it.aura) for s, it in zip(best, items, strict=True) if it.kind == "pos"]
    neg_aura = max(it.aura for it in items if it.kind in ("neg", "hunt"))
    recall = float(np.mean([s >= lin_thr or au >= AURA_THR for s, au in pos]))
    pixels = {k: int(v.sum()) for k, v in h.items()} | {"hunt": int(hh.sum())}
    return {"model": str(a.out), "sha256": sha, "lin_thr": round(lin_thr, 4), "lin_b": round(b, 4),
            "zone_thr": round(zone_thr, 4), "zone_penalty": round(penalty, 4),
            "aura_thr": AURA_THR, "dev_items": dict(Counter(it.kind for it in items)),
            "dev_neg_max_party": round(max(negs), 4), "dev_neg_max_aura": round(neg_aura, 4),
            "dev_pos_recall_in_sample": round(recall, 4), "colour_pixels": pixels}  # fmt: skip


def _full_frames(session: Path, keep: set[int]) -> Iterable[tuple[int, int, Any]]:
    import map_labels as ml

    manifest = json.loads((session / "manifest.json").read_text())
    for r in png_index(session, manifest):
        if r.frame_id in keep:
            yield r.frame_id, int(r.t_mono_ns), ml.read_png(r)


def cmd_score(a: argparse.Namespace) -> dict[str, Any]:
    """HELD-OUT, once: the watch's cells 8-14, the pilot after its first 300 s; --supplement
    sessions (Amendment B) are reported apart. decide() on the FULL frames, timed."""
    import mvp_watch as mw

    model = mw.load(a.model, a.sha256)
    ms: list[float] = []
    wrows = _rows(a.watch_truth)
    spawns, _ = watch_times(a.events)
    held = {f for f, r in wrows.items() if on_map(r) and cell_of(int(r["t"]), spawns) in HELD_CELLS}
    per_cell: dict[int, list[tuple[float, str, bool]]] = {}
    gap = {"n": 0, "fp": 0, "fp_frames": []}
    pos_frames = {"n": 0, "seen": 0, "lord_n": 0, "lord_seen": 0}
    for fid, t, img in _full_frames(a.watch, held):
        v, dt = mw.timed(img, model, ui_rects=mw.STANDARD_RECTS)
        ms.append(dt)
        row = wrows[fid]
        kind = kind_of(row)
        c = cell_of(t, spawns)
        per_cell.setdefault(c, []).append((t / 1e9, kind, bool(v["seen"])))
        if kind == "neg":
            gap["n"] += 1
            if v["seen"]:
                gap["fp"] += 1
                gap["fp_frames"].append([fid, v["cue"], v["where"]])
        elif kind == "pos":
            pos_frames["n"] += 1
            pos_frames["seen"] += int(v["seen"])
            if any(u["in_view"] and u["job"] == ORC_LORD for u in row["units"]):
                pos_frames["lord_n"] += 1
                pos_frames["lord_seen"] += int(v["seen"])
    cells = {c: cell_scores(seq) for c, seq in sorted(per_cell.items())}
    first = {c: d["episodes"][0] for c, d in cells.items() if d["episodes"]}
    later = [e for d in cells.values() for e in d["episodes"][1:]]
    hunting = []
    for name, (session, tpath) in [("pilot", a.pilot)] + [
        (f"supplement:{Path(s).name}", (s, t)) for s, t in (a.supplement or [])
    ]:
        rows = _rows(Path(tpath))
        part = pilot_part(list(rows.values()))
        keep = {f for f, v in part.items() if v == "held"} if name == "pilot" else set(part)
        if any(party_on_screen(rows[f]) for f in keep):
            raise SystemExit(f"{session}: an MVP-party unit is on screen in a hunting frame")
        n, fp, fps, reasons = 0, 0, [], Counter()
        for fid, _, img in _full_frames(Path(session), keep):
            v, dt = mw.timed(img, model, ui_rects=mw.HUNT_RECTS)
            ms.append(dt)
            n += 1
            reasons[str(v["reason"])] += 1
            if v["seen"]:
                fp += 1
                fps.append([fid, v["cue"], v["where"], v["aura"], v["party"]])
        hunting.append({"name": name, "frames": n, "fp": fp, "fp_per_10min": fp_rate(fp, n),
                        "fp_frames": fps, "reasons": dict(reasons)})  # fmt: skip
    n_cells = len(first)
    within = sum(e["within"] for e in first.values())
    lat = np.array(ms)
    return {
        "model": str(a.model), "sha256": model.sha256,
        "cells": {str(c): e for c, e in first.items()},
        "recall_within_1s": round(within / n_cells, 4) if n_cells else None,
        "cells_within": within, "cells_n": n_cells,
        "first_frame_recall": round(sum(e["first_frame"] for e in first.values()) / n_cells, 4)
        if n_cells else None,
        "reentries": {"n": len(later), "within": sum(e["within"] for e in later),
                      "never": sum(e["delay"] is None for e in later)},
        "pos_frames": pos_frames,
        "watch_gap": gap | {"fp_per_10min": fp_rate(gap["fp"], gap["n"])},
        "hunting": hunting,
        "latency_ms": {"calls": len(lat), "p50": round(float(np.percentile(lat, 50)), 2),
                       "p95": round(float(np.percentile(lat, 95)), 2),
                       "max": round(float(lat.max()), 2)},
        "bars": {
            "recall_within_1s>=0.95": n_cells > 0 and within / n_cells >= 0.95,
            "pilot_fp_per_10min<=1": (hunting[0]["fp_per_10min"] or 0.0) <= 1.0,
            "latency_p95<=60ms": float(np.percentile(lat, 95)) <= 60.0,
        },
    }  # fmt: skip


# --- round 2: the aura rule alone on EDGE ENTRIES (orclord-recognizer.md section 10 + 10a) -------
#
# Written and tested on synthetic cases BEFORE any round-2 frame was scored (Amendment 10a).
# - The recipe: mvp_watch.decide(frame, model, cues=ROUND2_CUES) with the round-1 model.
# - An ENTRY is a hop of orclord_edge_watch.py at which the Orc Lord or an archer goes from not in
#   view to in view (round 1's truth rule, kind_of == "pos"): the last frame before the hop's @warp
#   is not "pos", and a frame of the hop's window is. The window runs from the hop's settle (its
#   event, written after the settle) to the next hop's @warp (the next map change) or the cell's
#   @killmonster2, whichever comes first.
# - Its delay = t(the first "pos" frame of the window that is seen) - t(the window's first "pos"
#   frame), on "pos" frames only (as round 1's cell_scores). Within 1 s = delay <= RECALL_S, round
#   1's constant unchanged (1.1 s: frame-spacing jitter; at 2 fps the entry's first three frames);
#   the strict delay <= 1.0 s is reported beside it.
# - The hunting negatives: every frame on the map whose kind is "neg" (no party box even partly on
#   screen, no party_edge: round 1's FP definition). Frames with a party unit are LISTED, never
#   counted. The recorder skips a 1-fps tick whose picture is unchanged (manifest
#   unchanged_skipped), so a stored frame stands for itself and the skipped ticks after it
#   (stream_frames). The bar's minutes and false positives are counted on that 1-fps stream (round
#   1's count / frames x 600 at 1 fps, the skipped ticks included: the hunting time); the stored-
#   frames-only rate is reported beside it.

ROUND2_CUES = ("aura",)  # section 10: the aura rule alone
ROUND2_RECALL = 0.95  # bar 1
ROUND2_FP_PER_10MIN = 1.0  # bar 2
ROUND2_MIN_MINUTES = 120.0  # section 10: ">= 2 h" of hunting negatives


def hop_windows(events: Sequence[dict[str, Any]],
                map_changes: Sequence[int]) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the edge watch's events.jsonl rows (time order) and the recording's map-change times
    -> one window per ``hop``: ``warp`` = the last map change at or before the hop's event and after
    the previous event (None: no such @warp), ``settle`` = the hop event's time (written after the
    settle), ``end`` = the first map change after the settle or the next @killmonster2, whichever
    comes first (None: the recording's end)."""
    import bisect

    mc = sorted(int(t) for t in map_changes)
    kills = sorted(int(e["t_ns"]) for e in events if e.get("kind") == "killmonster2")
    out: list[dict[str, Any]] = []
    prev: int | None = None
    for e in events:
        t = int(e["t_ns"])
        if e.get("kind") == "hop":
            k = bisect.bisect_right(mc, t)
            warp = mc[k - 1] if k and (prev is None or mc[k - 1] > prev) else None
            ends = [mc[k]] if k < len(mc) else []
            kk = bisect.bisect_right(kills, t)
            if kk < len(kills):
                ends.append(kills[kk])
            out.append({"i": int(e["i"]), "j": int(e["j"]), "at": list(e.get("at") or []),
                        "dist": e.get("dist"), "warp": warp, "settle": t,
                        "end": min(ends) if ends else None})  # fmt: skip
        prev = t
    return out


def entries_of(windows: Sequence[dict[str, Any]],
               frames: Sequence[tuple[int, int, str, bool, bool]],
               recall_s: float = RECALL_S) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: hop windows (hop_windows) and the watch's frames as (t_ns, frame_id, kind, seen,
    lord: the Orc Lord itself in view) -> each window with ``before`` (the kind of the last frame
    before its @warp), ``entry``, its first in-view frame, ``delay`` (s; None: never seen on a
    "pos" frame of the window), ``within`` (<= recall_s), ``within_1s`` (<= 1.0, strict),
    ``early`` (a seen "edge" frame of the window before the first "pos" one: reported only) and
    ``pre_settle`` ("pos" frames between the @warp and the settle, and how many were seen:
    reported only, outside the window)."""
    seq = sorted(frames)
    out = []
    for w in windows:
        r = dict(w)
        warp, settle, end = w["warp"], w["settle"], w["end"]
        before = [f for f in seq if warp is not None and f[0] < warp]
        r["before"] = before[-1][2] if before else None
        win = [f for f in seq if f[0] >= settle and (end is None or f[0] < end)]
        pos = [f for f in win if f[2] == "pos"]
        pre = [f for f in seq if warp is not None and warp <= f[0] < settle and f[2] == "pos"]
        r.update(frames=len(win), pos=len(pos), seen_pos=sum(f[3] for f in pos),
                 pre_settle=[len(pre), sum(f[3] for f in pre)])  # fmt: skip
        r["entry"] = warp is not None and r["before"] != "pos" and bool(pos)
        r.update(first=None, t_first=None, lord_first=None, delay=None, within=False,
                 within_1s=False, first_frame=False, early=False)  # fmt: skip
        if pos:
            t0 = pos[0][0]
            r.update(first=pos[0][1], t_first=t0, lord_first=pos[0][4])
            hit = next((f for f in pos if f[3]), None)
            if hit is not None:
                d = round((hit[0] - t0) / 1e9, 3)
                r.update(delay=d, within=d <= recall_s, within_1s=d <= 1.0, first_frame=d == 0.0)
            r["early"] = any(f[3] and f[2] == "edge" for f in win if f[0] < t0)
        out.append(r)
    return out


def stream_frames(ts: Sequence[int], fps: float) -> list[int]:
    """PURE: a recording's stored frame times (ns, time order) -> how many ticks of its ``fps``
    stream each stored frame stands for: itself and the unchanged ticks the recorder skipped
    before the next stored frame (round(gap x fps), at least 1; the last frame 1)."""
    out = []
    for a, b in zip(ts, ts[1:], strict=False):
        out.append(max(1, round((int(b) - int(a)) / 1e9 * fps)))
    if ts:
        out.append(1)
    return out


def pool_hunting(sessions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """PURE: per-session hunting counts -> the pooled rates. Each session: ``fps``,
    ``neg_frames`` / ``fp`` (stored frames) and ``neg_ticks`` / ``fp_ticks`` (its 1-fps stream,
    stream_frames). Minutes = ticks / fps / 60; the rates are per 10 min."""
    neg_min = sum(s["neg_ticks"] / s["fps"] / 60.0 for s in sessions)
    stored_min = sum(s["neg_frames"] / s["fps"] / 60.0 for s in sessions)
    fp_ticks = sum(s["fp_ticks"] for s in sessions)
    fp = sum(s["fp"] for s in sessions)
    return {
        "minutes": round(neg_min, 2), "fp_ticks": fp_ticks,
        "fp_per_10min": round(fp_ticks / neg_min * 10.0, 4) if neg_min else None,
        "stored_minutes": round(stored_min, 2), "fp_stored": fp,
        "fp_per_10min_stored": round(fp / stored_min * 10.0, 4) if stored_min else None,
    }  # fmt: skip


def _party_units(row: dict[str, Any]) -> list[list[Any]]:
    return [[u["job"], u["gid"], u["box"], u["in_view"], u.get("state")] for u in row["units"]
            if u["job"] in MVP_PARTY]  # fmt: skip


def cmd_entries(a: argparse.Namespace) -> dict[str, Any]:
    """ROUND 2, once (section 10 + 10a): the edge watch's entries and the hunting negatives, with
    decide(..., cues=ROUND2_CUES) on the FULL frames, timed."""
    import mvp_watch as mw

    model = mw.load(a.model, a.sha256)
    ms: list[float] = []
    wdoc = json.loads(a.watch_truth.read_text())
    wmap = str(wdoc.get("map", MAP))
    wrects = mw.HUNT_RECTS if wdoc["layout"] == "hunt" else mw.STANDARD_RECTS
    wrows = {int(r["frame_id"]): r for r in wdoc["frames"]}
    events = [json.loads(x) for x in a.events.read_text().splitlines() if x.strip()]
    windows = hop_windows(events, _changes(a.watch))
    keep = {f for f, r in wrows.items() if on_map(r, wmap)}
    frames: list[tuple[int, int, str, bool, bool]] = []
    per = {"pos": [0, 0], "lord": [0, 0], "neg": [0, 0], "edge": [0, 0]}
    watch_fp: list[list[Any]] = []
    for fid, t, img in _full_frames(a.watch, keep):
        v, dt = mw.timed(img, model, ui_rects=wrects, cues=ROUND2_CUES)
        ms.append(dt)
        row = wrows[fid]
        kind = kind_of(row)
        lord = any(u["in_view"] and u["job"] == ORC_LORD for u in row["units"])
        seen = bool(v["seen"])
        frames.append((t, fid, kind, seen, lord))
        per[kind][0] += 1
        per[kind][1] += int(seen)
        if lord:
            per["lord"][0] += 1
            per["lord"][1] += int(seen)
        if kind == "neg" and seen:
            watch_fp.append([fid, t, v["aura"], v["where"]])
    wins = entries_of(windows, frames)
    ents = [w for w in wins if w["entry"]]
    n = len(ents)
    within = sum(w["within"] for w in ents)
    hunting = []
    for session, tpath in a.hunt:
        doc = json.loads(Path(tpath).read_text())
        hmap = str(doc.get("map", MAP))
        rows = sorted(doc["frames"], key=lambda r: int(r["t"]))
        manifest = json.loads((Path(session) / "manifest.json").read_text())
        fps = float(manifest.get("fps_cap") or 1.0)
        ticks = dict(zip((int(r["frame_id"]) for r in rows),
                         stream_frames([int(r["t"]) for r in rows], fps), strict=True))  # fmt: skip
        by_id = {int(r["frame_id"]): r for r in rows}
        keep = {f for f, r in by_id.items() if on_map(r, hmap)}
        s: dict[str, Any] = {"session": Path(session).name, "fps": fps, "on_map": len(keep),
                             "neg_frames": 0, "neg_ticks": 0, "fp": 0, "fp_ticks": 0,
                             "fp_frames": [], "party_frames": [], "reasons": Counter(),
                             "skipped_in_manifest": manifest.get("unchanged_skipped"),
                             "skipped_counted": sum(ticks.values()) - len(ticks)}  # fmt: skip
        for fid, t, img in _full_frames(Path(session), keep):
            v, dt = mw.timed(img, model, ui_rects=mw.HUNT_RECTS, cues=ROUND2_CUES)
            ms.append(dt)
            row = by_id[fid]
            kind = kind_of(row)
            s["reasons"][str(v["reason"])] += 1
            if kind != "neg":
                s["party_frames"].append([fid, t, kind, bool(v["seen"]), v["aura"], v["where"],
                                          row["flags"], _party_units(row)])  # fmt: skip
                continue
            s["neg_frames"] += 1
            s["neg_ticks"] += ticks[fid]
            if v["seen"]:
                s["fp"] += 1
                s["fp_ticks"] += ticks[fid]
                s["fp_frames"].append([fid, t, v["aura"], v["where"], ticks[fid]])
        s["reasons"] = dict(s["reasons"])
        s["minutes"] = round(s["neg_ticks"] / fps / 60.0, 2)
        hunting.append(s)
    pooled = pool_hunting(hunting)
    lat = np.array(ms)
    return {
        "model": str(a.model), "sha256": model.sha256, "cues": list(ROUND2_CUES),
        "recall_s": RECALL_S, "watch_map": wmap, "watch_layout": wdoc["layout"],
        "windows": wins,
        "entries_n": n, "entries_within": within,
        "entries_within_1s_strict": sum(w["within_1s"] for w in ents),
        "entries_first_frame": sum(w["first_frame"] for w in ents),
        "entries_recall": round(within / n, 4) if n else None,
        "watch_frames": {k: {"n": v[0], "seen": v[1]} for k, v in per.items()},
        "watch_neg_positives": watch_fp,
        "hunting": hunting, "hunting_pooled": pooled,
        "latency_ms": {"calls": len(lat), "p50": round(float(np.percentile(lat, 50)), 2),
                       "p95": round(float(np.percentile(lat, 95)), 2),
                       "max": round(float(lat.max()), 2)},
        "bars": {
            "entries_recall_within_1s>=0.95": n > 0 and within / n >= ROUND2_RECALL,
            "hunting_fp_per_10min<=1": pooled["fp_per_10min"] is not None
            and pooled["fp_per_10min"] <= ROUND2_FP_PER_10MIN,
        },
        "hunting_minutes>=120": pooled["minutes"] >= ROUND2_MIN_MINUTES,
    }  # fmt: skip


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("truth")
    p.add_argument("session", type=Path)
    p.add_argument("--layout", choices=("standard", "hunt"), required=True)
    p.add_argument("--kb", type=Path, default=MAIN / "data" / "kb")
    p.add_argument(
        "--mapcache-dir",
        type=Path,
        default=MAIN / "packages/poring_dataset/src/poring_dataset/_generated",
    )
    p.add_argument("--map", default=MAP, help="keep units on this map (Amendment 10a)")
    p.add_argument("--out", type=Path, required=True)
    q = sub.add_parser("entries")
    q.add_argument("--model", type=Path, required=True)
    q.add_argument("--sha256", required=True)
    q.add_argument("--watch", type=Path, required=True)
    q.add_argument("--watch-truth", type=Path, required=True)
    q.add_argument("--events", type=Path, required=True)
    q.add_argument("--hunt", nargs=2, action="append", required=True,
                   metavar=("SESSION", "TRUTH"))  # fmt: skip
    q.add_argument("--out", type=Path, required=True)
    for name in ("fit", "score"):
        q = sub.add_parser(name)
        q.add_argument("--watch", type=Path, required=True)
        q.add_argument("--watch-truth", type=Path, required=True)
        q.add_argument("--events", type=Path, required=True)
        q.add_argument("--pilot", nargs=2, metavar=("SESSION", "TRUTH"), required=True)
        q.add_argument("--out", type=Path, required=True)
        if name == "fit":
            q.add_argument("--extra", nargs=2, action="append", metavar=("SESSION", "TRUTH"))
            q.add_argument("--work", type=Path, required=True)
        else:
            q.add_argument("--model", type=Path, required=True)
            q.add_argument("--sha256", required=True)
            q.add_argument("--supplement", nargs=2, action="append", metavar=("SESSION", "TRUTH"))
    a = ap.parse_args(argv)
    if a.cmd == "truth":
        doc = truth(a.session, a.layout, kb=a.kb, mapcache_dir=a.mapcache_dir, map_name=a.map)
        doc["summary"] = summary(doc)
        a.out.write_text(json.dumps(doc) + "\n")
        print(json.dumps(doc["summary"], indent=1))
    elif a.cmd == "fit":
        rep = cmd_fit(a)
        print(json.dumps(rep, indent=1))
    elif a.cmd == "entries":
        rep = cmd_entries(a)
        a.out.write_text(json.dumps(rep, indent=1) + "\n")
        brief = {k: v for k, v in rep.items() if k not in ("windows", "hunting")}
        print(json.dumps(brief, indent=1))
    else:
        rep = cmd_score(a)
        a.out.write_text(json.dumps(rep, indent=1) + "\n")
        print(json.dumps({k: v for k, v in rep.items() if k != "cells"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
