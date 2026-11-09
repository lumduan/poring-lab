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
    mvp_watch_study.py dev   --watch S --watch-truth T --events E --pilot S T [--extra S T]...
                             --work DIR [--model MODEL.npz --sha256 HEX] --out DEV.json   DEV only

PER BOSS (docs/planning/stormy-knight-recognizer.md B1): every subcommand takes ``--boss PROFILE``
(scripts/mvp_profiles.py), default ``orclord`` = the Orc Lord study's values, unchanged (every
command line in orclord-recognizer.md works as written); ``--boss stormy`` = the Stormy Knight
(1251) + Garm Baby (1515) + Christmas Goblin (1607) on xmas_dun02. The party, the names, the map,
the sprites' defaults, the DEV / HELD-OUT cells and the fit's aura recipe come from the profile.
A truth names its profile (``boss``; none = orclord) and fit / score / entries refuse another's;
the model names its own (mvp_watch.save). A profile's ``lone`` jobs (stormy: Garm Baby, a regular
spawn too) may appear in its hunting recordings: those frames are left out of the negatives and
reported apart (section 3's Garm Baby caveat); any other party unit there still refuses.

THE ROUND (stormy-knight-recognizer.md 7 + 9): ``fit`` / ``score`` / ``dev`` take ``--round``,
default 1 = every split above, unchanged. ``--round 2`` = the Stormy Knight's round 2: every
on-map frame of the watch (all its cells) and of every hunting session is DEV for ``fit`` / ``dev``
and HELD-OUT for ``score`` (the pilot is no longer cut at 300 s). The model's version names its
round (``stormy-v2``) and ``score --round R`` refuses a model of another round. ``fit --aura
or|and|off`` (default ``or``, the v1 recipe) is recorded in the model (mvp_watch ``aura_mode``),
so decide() and ``score`` follow the MODEL; ``--aura-margin M`` sets the aura threshold to the DEV
negatives' max + M, rounded up to 0.01 (round 1's recipe, written by hand then). ``dev`` decides
exactly the frames ``fit`` takes (DEV only) from the fit's half-res memmaps (decide_half on the
memmap = decide on the full frame): the in-sample / leave-one-session-out numbers. Without
``--model`` it only decodes the memmaps (run it in its own memory scope first: a tmpfs page is
charged to the scope that writes it).

THE CHAT WINDOW OF THE SESSION'S DATE (B1): the client's chat window moved on 2026-11-05 (docked
bottom-left, six lines: (0, 585, 600, 720); chat_window.for_sid). ``truth --chat auto`` (the
default) takes it from the session id, as detector_vs_packets.py score-session does: the in-view
rule's UI windows are the layout's with that chat window (a window wholly inside another dropped:
covered_fraction sums overlaps), recorded in the truth (``chat``). fit / score / entries then mask
decide()'s UI with the truth's own layout and chat window (mask_rects). Every session before
20261105T12 gets the legacy window, which IS client_layout's and mvp_watch's: the Orc Lord's
truths and masks are unchanged; a truth without ``chat`` is read with the legacy window.

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
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mvp_profiles  # noqa: E402

# the Orc Lord's values (mvp_profiles.ORCLORD): every helper's default, unchanged since round 1
ORCLORD = mvp_profiles.ORCLORD
ORC_LORD, ORC_ARCHERS = ORCLORD.boss, ORCLORD.summons
MVP_PARTY = ORCLORD.party
NEGATIVE_SPECIES = dict(ORCLORD.negatives)
NAMES = dict(ORCLORD.names)
OFFSET_MS = 120.0  # 1d: payf07's frozen params (P1, the same RDP frame bus, PNG recorder v5)
K = 0.14  # payf07's frozen k
MAP = ORCLORD.map
SETTLE_NS = 5_000_000_000  # a map change: the loading screen and the settle (payf07 4f)
GM_WINDOW_NS = 2_000_000_000  # labels.gm_windows
# Amendment A (orclord-recognizer.md, DEV frames 110-112, 335-336, 346): the client keeps drawing a
# dying unit (and the Orc Lord's aura) after its vanish packet, and draws the aura at a spawn before
# the 1d-shifted Timeline has the unit. Frames this close to a party unit's vanish / appearance are
# neither positive nor negative.
AFTER_VANISH_NS = 4_000_000_000
AROUND_APPEAR_NS = (500_000_000, 1_000_000_000)  # before, after a "new" appearance
SPRITES = ORCLORD.sprites  # gef_fild10's decoded sprites (the --boss orclord default)
SPRITE_NAMES = ORCLORD.sprite_names
# the main checkout: data/kb and the mapcache (its owner's home: /home/batt on VM 103, /home/bot
# on bot-server)
MAIN = Path.home() / "docker" / "poring-lab"


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


def party_times(events: Iterable[dict[str, Any]], jobs: Collection[int] = MVP_PARTY
                ) -> tuple[list[int], list[int]]:  # fmt: skip
    """(vanish times, "new" appearance times) of every MVP-party unit (by its gid's job)."""
    party: set[int] = set()
    vanish, new = [], []
    for e in events:
        if e.get("type") == "entity_appear" and e.get("job") in jobs:
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
             gap_s: float = 3.0, boss: int = ORC_LORD) -> list[dict[str, Any]]:  # fmt: skip
    """The in-view episodes of the MVP party: maximal runs of frames with at least one unit of
    ``jobs`` in view, split where no such frame occurs for more than ``gap_s``. Each episode:
    its first / last frame time, the frame ids, and whether the boss itself was in view
    (``lord``: the Orc Lord's key, kept for every profile)."""
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
        cur["lord"] = cur["lord"] or any(u["job"] == boss for u in seen)
    return out


def png_index(session: Path, manifest: dict[str, Any]) -> list[Any]:
    """map_labels.png_index, tolerant of a TRUNCATED last shard (a recording stopped by its IO
    guard mid-write, e.g. 20261025T204315-rdp-rogue-s1): the complete members before the cut are
    kept, a frame missing its png or json is dropped (poring_dataset.frames.frame_refs, its
    default). The MVP watch fits colour cues on lossless frames: a VIDEO recording is REFUSED
    (ADR-0024: PNG required until this study passes its parity on decoded frames; a stage-2
    session is read as its video twin only with PORING_FRAME_SOURCE=video, the parity run)."""
    from poring_dataset import frames as recorded

    why = recorded.png_required(manifest, "mvp_watch_study")
    if why:
        raise SystemExit(why)
    return recorded.frame_refs(session, manifest)


# --- the truth ----------------------------------------------------------------------------------


def _events(session: Path) -> list[dict[str, Any]]:
    with gzip.open(session / "packets.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


@dataclass
class TruthStack:
    """What ``truth_row`` projects with: the Timeline, the sprite sheets, the RDP camera, the
    indoor table, the frame size, the layout's UI rectangles and the frame-flag times."""

    tl: Any
    sheets: Any
    camera: dict[str, Any]
    indoor: Any
    size: tuple[int, int]
    rects: Any
    changes: list[int]
    gm: list[int]
    vanish: list[int]
    new: list[int]


def stack_times(events: Sequence[dict[str, Any]], jobs: Collection[int] = MVP_PARTY
                ) -> tuple[list[int], list[int], list[int], list[int]]:  # fmt: skip
    """PURE: the frame-flag times of a session's packets: (map changes, GM commands, the party's
    vanishes, the party's "new" appearances); ``jobs`` = the profile's party."""
    changes = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change")
    gm = sorted(int(e["t_mono_ns"]) for e in events if e.get("gm_command"))
    vanish, new = party_times(events, jobs)
    return changes, gm, vanish, new


def truth_stack(events: list[dict[str, Any]], layout: str, size: tuple[int, int], *, kb: Path,
                mapcache_dir: Path, sprites: Path = SPRITES,
                sprite_names: Path = SPRITE_NAMES,
                jobs: Collection[int] = MVP_PARTY) -> TruthStack:  # fmt: skip
    """The projection stack of ``truth`` for a session's packets (also used at other capture
    times than a recorder's frames: scripts/detector_vs_packets.py). ``sprites`` / ``sprite_names``:
    the decoded monster sprites (sprite_catalog.py --work .../data/sprite/몬스터) and the client
    stems (npc_sprites.py mob-names) of the session's map; the defaults are gef_fild10's prep
    dir of 2026-10-25, which is GONE from /dev/shm (its NAS copy:
    scratch-archive/2026-11-03/gef10-prep). ``jobs``: the party whose vanishes / appearances
    flag ``party_edge`` (the profile's; the Orc Lord's by default)."""
    import client_layout
    import qa_export

    from poring_dataset import mapcache
    from poring_dataset.camera import load_indoor_table
    from poring_dataset.projection import camera_file
    from poring_dataset.timeline import Timeline

    qa_export.KB_CLASSES = kb / "classes.json"
    sheets = qa_export.Sheets(sprites, stems=qa_export.sprite_stems(sprite_names))
    tl = Timeline(events, mapcache.load(mapcache_dir, prere=True), snapshot_every=32)
    camera = json.loads(camera_file("rdp").read_text())
    indoor = load_indoor_table()
    rects = client_layout.RECTS[layout]
    changes, gm, vanish, new = stack_times(events, jobs)
    return TruthStack(tl, sheets, camera, indoor, size, rects, changes, gm, vanish, new)


def truth_row(stack: TruthStack, t: int, frame_id: int | None, offset_ms: float = OFFSET_MS,
              map_name: str = MAP,
              self_offset_ms: float | None = None) -> dict[str, Any]:  # fmt: skip
    """One capture time ``t``: every monster's predicted sprite box (unclipped), its Timeline
    state and whether it is in view, at t - 1d (``truth``'s row).

    ``self_offset_ms`` (xmas02-detector.md Amendment J, 2026-11-07): the CAMERA (our own position,
    which the view is centred on) is taken at t - self_offset_ms instead of t - 1d; the monsters
    stay at t - 1d. ``row["self"]`` stays at t - 1d (the motion split reads it); ``row["camera"]``
    is the position the scene was built on. None: the camera at t - 1d, as before."""
    from poring_dataset.camera import map_key
    from poring_dataset.labels import ONE_SHOT, STATE_ACTION
    from poring_dataset.render import Actor, MonsterAction, load_scene, predict_sprite

    tl, sheets = stack.tl, stack.sheets
    tw = t - int(offset_ms * 1e6)
    world = tl.frame_world(tw)
    camera = world.self_pos
    if self_offset_ms is not None:
        cam = tl.frame_world(t - int(self_offset_ms * 1e6))
        camera = cam.self_pos if cam.map == world.map else None
    row: dict[str, Any] = {"frame_id": frame_id, "t": t, "map": world.map,
                           "self": world.self_pos, "camera": camera,
                           "flags": frame_flags(t, stack.changes, stack.gm, stack.vanish,
                                                stack.new),
                           "units": [], "players": 0}  # fmt: skip
    if world.self_pos is None or camera is None or not world.map or \
            map_key(world.map) != map_name:  # fmt: skip
        return row
    scene = load_scene(stack.camera, world.map, camera, indoor_table=stack.indoor)
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
                             "in_view": in_view(box, stack.size, stack.rects)})  # fmt: skip
    return row


def truth_doc(stack: TruthStack, frames: Iterable[tuple[int, int]], *, session: str, layout: str,
              prof: mvp_profiles.BossProfile = ORCLORD, offset_ms: float = OFFSET_MS,
              map_name: str | None = None) -> dict[str, Any]:  # fmt: skip
    """The truth of (capture time, frame id) ``frames`` on ``stack``, for the boss profile
    ``prof``: units kept on ``map_name`` (default: the profile's hunting map; it must be one of
    the profile's maps). Refuses when a party species has no decoded sprite sheet: its units
    would get no box, and every party frame would read as a negative."""
    map_name = prof.map if map_name is None else map_name
    if map_name not in prof.maps:
        raise SystemExit(f"--boss {prof.name}: --map {map_name} is not one of {prof.maps}")
    lost = {j: prof.names.get(j, str(j)) for j in prof.party if stack.sheets(j) is None}
    if lost:
        raise SystemExit(f"--boss {prof.name}: no decoded sprite for the party {lost} "
                         f"({stack.sheets.missing}): give --sprites / --sprite-names")  # fmt: skip
    rows = [truth_row(stack, int(t), int(fid), offset_ms, map_name) for t, fid in frames]
    return {"session": session, "layout": layout, "offset_ms": offset_ms, "k": K,
            "size": stack.size, "map": map_name, "frames": rows,
            "missing_sheets": stack.sheets.missing, "boss": prof.name}  # fmt: skip


def ui_rects_for(layout: str, sid: str, chat: str = "auto") -> dict[str, Any]:
    """The in-view rule's UI windows for a RECORDED session: the layout's (client_layout.RECTS)
    with the chat window of ``chat`` (detector_vs_packets.chat_rect_for: auto = the session's
    date), nested windows dropped. {"rects", "chat": {"rect", "how", "nested_dropped"}}."""
    import detector_vs_packets as dv

    rect, how = dv.chat_rect_for(sid, chat)
    rects, dropped = dv.nested_rects(dv.session_rects(layout, rect))
    return {"rects": rects, "chat": {"rect": list(rect), "how": how, "nested_dropped": dropped}}


def mask_rects(doc: dict[str, Any]) -> tuple[tuple[int, int, int, int], ...]:
    """decide()'s UI mask for a truth's frames: mvp_watch's rectangles of the truth's layout with
    the chat window the truth used (none recorded: the legacy window, mvp_watch's own)."""
    import client_layout
    import mvp_watch as mw

    rects = list(mw.STANDARD_RECTS if doc.get("layout") == "standard" else mw.HUNT_RECTS)
    chat = doc.get("chat")
    if chat:
        a, b, c, d = (int(v) for v in chat["rect"])
        rects[client_layout.CHAT_INDEX] = (a, b, c, d)
    return tuple(rects)


def truth(session: Path, layout: str, *, kb: Path, mapcache_dir: Path,
          offset_ms: float = OFFSET_MS, map_name: str | None = None, sprites: Path | None = None,
          sprite_names: Path | None = None, prof: mvp_profiles.BossProfile = ORCLORD,
          chat: str = "auto") -> dict[str, Any]:  # fmt: skip
    """Per frame of a recorder session: every monster's predicted sprite box (unclipped), its
    Timeline state and whether it is in view, at the frame's capture time - 1d. Units are kept on
    ``map_name`` only (Amendment 10a: round 2's watch is on prt_fild08; the projection reads that
    map's GAT from the same GAT_DIR, nothing else changes). ``prof``: the boss profile (its party
    flags ``party_edge``; its map and sprites are the defaults). ``chat``: the chat window
    (ui_rects_for; auto = the session's date). Refuses a map whose GAT is not extracted
    (load_scene would project on FLAT ground without it, silently)."""
    import map_labels as ml

    from poring_dataset.camera import GAT_DIR

    gat = GAT_DIR / f"{prof.map if map_name is None else map_name}.gat"
    if not gat.exists():
        raise SystemExit(f"{gat}: the map's GAT is not extracted (PORING_GAT_DIR; "
                         "xmas02-prep.md 9: grf_read.py extract ... --out "
                         "/dev/shm/poring-lab-tmp/gat)")  # fmt: skip
    manifest = json.loads((session / "manifest.json").read_text())
    ml.check_recording(manifest)
    refs = png_index(session, manifest)
    events = _events(session)
    size = (int(manifest["game_region"][2]), int(manifest["game_region"][3]))
    stack = truth_stack(events, layout, size, kb=kb, mapcache_dir=mapcache_dir,
                        sprites=prof.sprites if sprites is None else sprites,
                        sprite_names=prof.sprite_names if sprite_names is None else sprite_names,
                        jobs=prof.party)  # fmt: skip
    ui = ui_rects_for(layout, str(manifest["session_id"]), chat)
    stack.rects = ui["rects"]
    doc = truth_doc(stack, ((int(r.t_mono_ns), r.frame_id) for r in refs),
                    session=manifest["session_id"], layout=layout, prof=prof,
                    offset_ms=offset_ms, map_name=map_name)  # fmt: skip
    doc["chat"] = ui["chat"]
    return doc


def summary(doc: dict[str, Any], prof: mvp_profiles.BossProfile = ORCLORD) -> dict[str, Any]:
    """Counts: frames, frames with each species in view, the MVP party's episodes (``lord``: the
    profile's boss, the Orc Lord's key kept)."""
    rows = doc["frames"]
    target = str(doc.get("map", prof.map))
    on_map = [r for r in rows if r["map"] and r["map"].startswith(target)]
    per = Counter()
    units = Counter()
    for r in on_map:
        jobs = {u["job"] for u in r["units"] if u["in_view"]}
        for j in jobs:
            per[prof.names.get(j, str(j))] += 1
        for u in r["units"]:
            if u["in_view"]:
                units[prof.names.get(u["job"], str(u["job"]))] += 1
    party = [r for r in on_map if any(u["in_view"] and u["job"] in prof.party for u in r["units"])]
    lord = [r for r in on_map if any(u["in_view"] and u["job"] == prof.boss for u in r["units"])]
    return {"frames": len(rows), "on_map": len(on_map), "frames_with": dict(per),
            "boxes_in_view": dict(units), "party_frames": len(party), "lord_frames": len(lord),
            "episodes": len(episodes(on_map, prof.party, boss=prof.boss))}  # fmt: skip


# --- the split (orclord-recognizer.md section 3) -----------------------------------------------

DEV_CELLS = ORCLORD.dev_cells  # the Orc Lord's (a profile's dev_cells / held_cells)
HELD_CELLS = ORCLORD.held_cells
PILOT_DEV_S = 300.0
RECALL_S = 1.1  # the episode's first or second recorded frame (1 fps)
EPISODE_GAP_S = 3.0
# the splits (``--round``): 1 = the pre-registered cells and the pilot's first 300 s (every study
# so far); 2 = stormy-knight-recognizer.md 7: whole sessions, every watch cell, DEV or HELD-OUT
ROUNDS = (1, 2)
PART_FRAMES = 1000  # round 2's memmaps: parts of <= 1000 half-res frames (0.69 GB; rule 7)


def watch_times(events_path: Path, boss: int | None = None) -> tuple[list[int], list[int]]:
    """(spawn times, @killmonster2 times) of the watch's events.jsonl (CLOCK_MONOTONIC ns). With
    ``boss``, a spawn of another mob (its ``mob`` field) refuses: another boss's watch."""
    rows = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    if boss is not None:
        other = sorted({str(r["mob"]) for r in rows if r.get("kind") == "spawn"
                        and r.get("mob") is not None and int(r["mob"]) != boss})  # fmt: skip
        if other:
            raise SystemExit(f"{events_path}: spawns of {other}, not the boss {boss}")
    spawns = [int(r["t_ns"]) for r in rows if r.get("kind") == "spawn"]
    kills = [int(r["t_ns"]) for r in rows if r.get("kind") == "killmonster2"]
    return spawns, kills


def cell_of(t: int, spawns: Sequence[int]) -> int:
    """The lattice cell a watch frame belongs to: the last spawn at or before it (-1: before)."""
    import bisect

    return bisect.bisect_right(spawns, t) - 1


def on_map(row: dict[str, Any], map_name: str = MAP) -> bool:
    return bool(row["map"]) and str(row["map"]).startswith(map_name)


def party_in_view(row: dict[str, Any], jobs: Collection[int] = MVP_PARTY) -> bool:
    return any(u["in_view"] and u["job"] in jobs for u in row["units"])


def party_on_screen(row: dict[str, Any], size: tuple[int, int] = (1280, 720),
                    jobs: Collection[int] = MVP_PARTY) -> bool:  # fmt: skip
    for u in row["units"]:
        if u["job"] in jobs and u["box"] is not None:
            x0, y0, x1, y1 = u["box"]
            if x1 > 0 and y1 > 0 and x0 < size[0] and y0 < size[1]:
                return True
    return False


def kind_of(row: dict[str, Any], jobs: Collection[int] = MVP_PARTY) -> str:
    """pos: the party in view; neg: no party box even partly on screen and not a party edge
    (Amendment A); edge: neither."""
    if party_in_view(row, jobs):
        return "pos"
    if not party_on_screen(row, jobs=jobs) and "party_edge" not in row["flags"]:
        return "neg"
    return "edge"


def pilot_part(rows: Sequence[dict[str, Any]], dev_s: float = PILOT_DEV_S,
               map_name: str = MAP) -> dict[int, str]:  # fmt: skip
    """frame_id -> dev | held for a hunting session's frames on the map (section 3)."""
    on = [r for r in rows if on_map(r, map_name)]
    if not on:
        return {}
    t0 = int(on[0]["t"])
    return {int(r["frame_id"]): ("dev" if (int(r["t"]) - t0) / 1e9 < dev_s else "held") for r in on}


def watch_split(wrows: dict[int, dict[str, Any]], spawns: Sequence[int], map_name: str,
                prof: mvp_profiles.BossProfile, round_: int, part: str) -> set[int]:  # fmt: skip
    """PURE: the watch frames of ``part`` (dev | held) in round ``round_``. Round 1: the
    profile's DEV cells and the frames before the first spawn / its HELD-OUT cells; round 2: every
    frame on the map, whichever part (the whole watch is one side of the split)."""
    if part not in ("dev", "held") or round_ not in ROUNDS:
        raise ValueError(f"part {part!r}, round {round_!r}")
    on = {f for f, r in wrows.items() if on_map(r, map_name)}
    if round_ == 2:
        return on
    cells = prof.dev_cells | {-1} if part == "dev" else prof.held_cells
    return {f for f in on if cell_of(int(wrows[f]["t"]), spawns) in cells}


def hunt_split(rows: Sequence[dict[str, Any]], map_name: str, pilot: bool, round_: int,
               part: str) -> set[int]:  # fmt: skip
    """PURE: a hunting session's frames of ``part`` (dev | held). Round 1: the PILOT's first
    PILOT_DEV_S on the map (dev) or the rest (held), every other session whole (--extra in fit,
    --supplement in score); round 2: every session whole."""
    if part not in ("dev", "held") or round_ not in ROUNDS:
        raise ValueError(f"part {part!r}, round {round_!r}")
    split = pilot_part(rows, map_name=map_name)
    if round_ == 2 or not pilot:
        return set(split)
    return {f for f, v in split.items() if v == part}


def colour_cells(prof: mvp_profiles.BossProfile, round_: int, spawns: Sequence[int],
                 kills: Sequence[int]) -> list[int]:  # fmt: skip
    """The watch cells the body LUT's colours come from: the DEV cells (round 1), every cell
    with a spawn and its @killmonster2 (round 2)."""
    if round_ == 2:
        return list(range(min(len(spawns), len(kills))))
    return sorted(prof.dev_cells)


def version_round(version: str) -> int:
    """A model version's round: ``<profile>-v<N>`` (orclord-v1, stormy-v1: 1; stormy-v2: 2)."""
    head, sep, tail = version.rpartition("-v")
    if not sep or not head or not tail.isdigit():
        raise ValueError(f"model version {version!r} is not <profile>-v<N>")
    return int(tail)


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


def hunt_negatives(rows: dict[int, dict[str, Any]], keep: set[int], session: Any,
                   prof: mvp_profiles.BossProfile = ORCLORD
                   ) -> tuple[set[int], set[int]]:  # fmt: skip
    """A hunting session's kept frames -> (its negatives, its ``lone`` frames). Any party unit
    but the profile's ``lone`` jobs on screen refuses (the boss must be dead by the schedule).
    Without lone jobs (orclord) every kept frame is a negative, as before; with them (stormy:
    Garm Baby's own spawn) a frame that is not ``neg`` by kind_of is a lone frame, reported apart
    (stormy-knight-recognizer.md 3, the Garm Baby caveat), never a negative."""
    strict = [j for j in prof.party if j not in prof.lone]
    if any(party_on_screen(rows[f], jobs=strict) for f in keep):
        raise SystemExit(f"{session}: an MVP-party unit is on screen in a hunting frame")
    if not prof.lone:
        return set(keep), set()
    lone = {f for f in keep if kind_of(rows[f], prof.party) != "neg"}
    return set(keep) - lone, lone


def lone_report(rows: dict[int, dict[str, Any]], lone: set[int], seen: dict[int, bool],
                n_frames: int, prof: mvp_profiles.BossProfile) -> dict[str, Any]:  # fmt: skip
    """PURE: the lone jobs' frames of a hunting session (hunt_negatives) and the decision on
    each -> their counts, their in-view episodes and how many of those a positive would flee
    from (per 10 min of the session's ``n_frames`` decided frames: one Fly Wing each)."""
    ordered = sorted((rows[f] for f in lone), key=lambda r: int(r["t"]))
    eps = episodes(ordered, prof.lone, gap_s=EPISODE_GAP_S, boss=prof.boss)
    fled = sum(any(seen.get(f, False) for f in e["frames"]) for e in eps)
    return {"jobs": list(prof.lone), "frames": len(lone),
            "pos": sum(kind_of(r, prof.party) == "pos" for r in ordered),
            "seen": sum(bool(seen.get(f, False)) for f in lone), "episodes": len(eps),
            "episodes_seen": fled, "episodes_seen_per_10min": fp_rate(fled, n_frames)}  # fmt: skip


def truth_of(path: Path, prof: mvp_profiles.BossProfile) -> dict[str, Any]:
    """A truth file for ``prof``: refuses another profile's (``boss``; none = orclord)."""
    doc: dict[str, Any] = json.loads(path.read_text())
    boss = str(doc.get("boss", ORCLORD.name))
    if boss != prof.name:
        raise SystemExit(f"{path}: a --boss {boss} truth, not {prof.name}")
    return doc


# --- frames ---------------------------------------------------------------------------------------


class Frames:
    """Half-res frames kept in several memmap PARTS, read as one sequence (len, [i], iter): a
    session longer than PART_FRAMES stays within rule 7's 1 GB per scratch item."""

    def __init__(self, parts: Sequence[Any]) -> None:
        self.parts = list(parts)
        self.starts = [0]
        for p in self.parts:
            self.starts.append(self.starts[-1] + len(p))

    def __len__(self) -> int:
        return self.starts[-1]

    def __getitem__(self, i: int) -> Any:
        import bisect

        if not -len(self) <= i < len(self):
            raise IndexError(i)
        i %= len(self)
        k = bisect.bisect_right(self.starts, i) - 1
        return self.parts[k][i - self.starts[k]]

    def __iter__(self) -> Any:
        for p in self.parts:
            yield from p


def part_paths(out: Path, n: int, part_frames: int) -> list[Path]:
    """The memmap parts of ``n`` frames: <stem>.p0.npy, <stem>.p1.npy, ..."""
    k = max(1, -(-n // part_frames))
    return [out.with_name(f"{out.stem}.p{j}.npy") for j in range(k)]


def half_frames(session: Path, keep: set[int], out: Path,
                part_frames: int | None = None) -> tuple[Any, list[int]]:  # fmt: skip
    """Decode the kept frames once into a half-res memmap (out, /dev/shm): (array, frame ids).
    A memmap left by an earlier run with the same frame ids is reused. ``part_frames``: write
    parts of at most that many frames (part_paths) and return them as one Frames (round 2);
    None: one file, as before."""
    import map_labels as ml

    ids_path = out.with_name(out.name + ".ids.json")
    if ids_path.exists():
        ids = json.loads(ids_path.read_text())
        if set(ids) == keep and part_frames is None and out.exists():
            arr = np.load(out, mmap_mode="r")
            if len(arr) == len(ids):
                return arr, ids
        if set(ids) == keep and part_frames is not None:
            paths = part_paths(out, len(ids), part_frames)
            if all(q.exists() for q in paths):
                got = Frames([np.load(q, mmap_mode="r") for q in paths])
                if len(got) == len(ids):
                    return got, ids
    manifest = json.loads((session / "manifest.json").read_text())
    refs = [r for r in png_index(session, manifest) if r.frame_id in keep]
    if part_frames is None:
        arr = np.lib.format.open_memmap(out, mode="w+", dtype=np.uint8,
                                        shape=(len(refs), 360, 640, 3))  # fmt: skip
        for i, r in enumerate(refs):
            arr[i] = ml.read_png(r)[::2, ::2]
        arr.flush()
        ids = [r.frame_id for r in refs]
        ids_path.write_text(json.dumps(ids))
        return arr, ids
    parts = []
    for j, q in enumerate(part_paths(out, len(refs), part_frames)):
        chunk = refs[j * part_frames : (j + 1) * part_frames]
        mm = np.lib.format.open_memmap(q, mode="w+", dtype=np.uint8,
                                       shape=(len(chunk), 360, 640, 3))  # fmt: skip
        for i, r in enumerate(chunk):
            mm[i] = ml.read_png(r)[::2, ::2]
        mm.flush()
        del mm
        parts.append(np.load(q, mmap_mode="r"))
    ids = [r.frame_id for r in refs]
    ids_path.write_text(json.dumps(ids))
    return Frames(parts), ids


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
                 cells: Iterable[int], ui: npt.NDArray[np.bool_],
                 jobs: Collection[int] = MVP_PARTY) -> dict[str, Any]:  # fmt: skip
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
                if u["job"] in jobs:
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


LOGREG_WHOLE_MAX = 250_000  # rows: every fit before round 2 (the Orc Lord's ~0.2 M) stays whole
LOGREG_CHUNK = 32_768  # rows per block above it (~100 MB of float64 a block, not ~4 GB)


def logreg(x: npt.NDArray[np.float32], y: npt.NDArray[np.float64], wts: npt.NDArray[np.float64],
           l2: float = 1.0, iters: int = 12,
           chunk: int | None = None) -> tuple[npt.NDArray[np.float32], float]:  # fmt: skip
    """Weighted L2 logistic regression by Newton steps on standardised features; returns the
    weights and bias in the raw features' units. Up to LOGREG_WHOLE_MAX rows (every fit before
    round 2) it runs on the whole standardised matrix, exactly as before; above (or with
    ``chunk`` given) it sums the gradient and the Hessian over blocks of ``chunk`` rows: the same
    Newton steps to rounding, in ~100 MB instead of two float64 copies of the matrix."""
    n = len(x)
    if chunk is None and n > LOGREG_WHOLE_MAX:
        chunk = LOGREG_CHUNK
    if chunk is not None and chunk < n:
        return _logreg_blocks(x, y, wts, l2, iters, chunk)
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


def _logreg_blocks(x: npt.NDArray[np.float32], y: npt.NDArray[np.float64],
                   wts: npt.NDArray[np.float64], l2: float, iters: int,
                   chunk: int) -> tuple[npt.NDArray[np.float32], float]:  # fmt: skip
    """logreg's Newton steps with the sums taken block by block (float64 accumulators)."""
    n, d = x.shape
    blocks = [slice(i, min(n, i + chunk)) for i in range(0, n, chunk)]
    acc = np.zeros(d)
    for b in blocks:
        acc += x[b].sum(0, dtype=np.float64)
    mu = acc / n
    acc[:] = 0.0
    for b in blocks:
        acc += ((x[b] - mu) ** 2).sum(0)
    sd = np.sqrt(acc / n) + 1e-3

    def z_of(b: slice) -> npt.NDArray[np.float64]:
        return np.hstack([(x[b] - mu) / sd, np.ones((b.stop - b.start, 1))])

    w = np.zeros(d + 1)
    reg = l2 * np.r_[np.ones(d), 0.0]
    for _ in range(iters):
        g = reg * w
        hess = np.diag(reg)
        for b in blocks:
            z = z_of(b)
            p = 1.0 / (1.0 + np.exp(-np.clip(z @ w, -30, 30)))
            g += z.T @ (wts[b] * (p - y[b]))
            hess += (z * (wts[b] * p * (1 - p))[:, None]).T @ z
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
               model: Any, rects: Any, hunt: bool,
               jobs: Collection[int] = MVP_PARTY) -> list[Item]:  # fmt: skip
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
            if u["job"] in jobs and u["in_view"] and u["box"]:
                x0, _, x1, y1 = (v / 2 for v in u["box"])
                party.append(mw.foot_window((x0 + x1) / 2, y1))
        out.append(Item(m["feats"], m["valid"], "hunt" if hunt else kind_of(row, jobs), party,
                        float(m["aura_map"].max()), m["zone"]))  # fmt: skip
    return out


def train_party(items: Sequence[Item], rounds: int = 2, seed: int = 0, l2: float = 1.0,
                stats: dict[str, Any] | None = None
                ) -> tuple[npt.NDArray[np.float32], float]:  # fmt: skip
    """Positives: each party unit's window and its 4 neighbours; negatives: random windows of
    every frame away from the party, then ``rounds`` of hard negatives (each negative frame's
    top 20 windows scoring above -2). The kept windows are COPIES: a view into a frame's window
    vectors held all of them (~4.5 MB a frame; the Orc Lord's fit was OOM-killed under 4 GB).
    The training matrix is built once and grown by each round's hard negatives (the rows and
    their order as before: positives, random negatives, then each round's hard ones), so a
    round-2 fit's ~0.5 M windows are held once, not three times. ``stats``: filled with the row
    counts (pos, neg, hard per round)."""
    import mvp_watch as mw

    rng = np.random.default_rng(seed)
    xp: list[Any] = []
    xn: list[Any] = []
    for it in items:
        wv = mw.window_vectors(it.feats)
        oh, ow = wv.shape[:2]
        near = np.zeros((oh, ow), bool)
        for cy, cx in it.party:
            near[max(0, cy - 2) : cy + 3, max(0, cx - 2) : cx + 3] = True
            for dy, dx in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= cy + dy < oh and 0 <= cx + dx < ow:
                    xp.append(wv[cy + dy, cx + dx].copy())  # a view keeps the frame's wv
        if it.kind == "edge":
            continue
        cand = np.argwhere(it.valid & ~near)
        if len(cand):
            n = 60 if it.kind == "pos" else 150
            pick = cand[rng.choice(len(cand), min(len(cand), n), replace=False)]
            xn.append(wv[pick[:, 0], pick[:, 1]])  # a copy (fancy indexing), one block a frame
    dim = mw.N_FEATURES * mw.WIN[0] * mw.WIN[1]
    pos = np.array(xp, np.float32).reshape(-1, dim)
    x = np.vstack([pos, *(np.asarray(v, np.float32).reshape(-1, dim) for v in xn)])
    del xn, xp
    n_pos = len(pos)
    if stats is not None:
        stats.update(pos=n_pos, neg=len(x) - n_pos, hard=[])
    w, b = np.zeros(1, np.float32), 0.0
    for r in range(rounds + 1):
        n_neg = len(x) - n_pos
        y = np.r_[np.ones(n_pos), np.zeros(n_neg)]
        wts = np.r_[np.full(n_pos, n_neg / n_pos * 0.5), np.ones(n_neg)]
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
                    hard.append(wv[yy, xx].copy())  # a view would keep every frame's wv (4.5 MB)
        if stats is not None:
            stats["hard"].append(len(hard))
        if hard:
            x = np.vstack([x, np.array(hard, np.float32)])
    return w.reshape(mw.N_FEATURES, *mw.WIN), b


AURA_THR = ORCLORD.aura_thr  # Amendment B: the aura rule's frozen threshold (DEV hunting max 0.065)
LIN_MARGIN = 1.0  # Amendment B: the party threshold = the DEV negatives' max + this
AURA_MARGIN = 0.015  # Amendment B / stormy 5b: the aura threshold = the DEV negatives' max + this
BODY_HUNT_W, BODY_OTHER_W = 10.0, 5.0  # the body LUT's weights of hunting / other-species pixels


def _rows(path: Path, prof: mvp_profiles.BossProfile = ORCLORD) -> dict[int, dict[str, Any]]:
    return {int(r["frame_id"]): r for r in truth_of(path, prof)["frames"]}


def _rects(path: Path, prof: mvp_profiles.BossProfile) -> tuple[tuple[int, int, int, int], ...]:
    return mask_rects(truth_of(path, prof))


def _map_of(path: Path, prof: mvp_profiles.BossProfile) -> str:
    """The map a truth kept its units on (truth --map; none recorded: the profile's)."""
    return str(json.loads(path.read_text()).get("map", prof.map))


def profile_of(a: argparse.Namespace) -> mvp_profiles.BossProfile:
    return mvp_profiles.get(getattr(a, "boss", None) or mvp_profiles.DEFAULT)


def fit_recipe(a: argparse.Namespace, prof: mvp_profiles.BossProfile) -> dict[str, Any]:
    """The fit's aura recipe: the profile's, each value replaced by its command-line override
    (--aura-thr, --ring, --ring-cell, --ring-dy, --aura-rule); a placeholder left None refuses."""
    ring, rule = getattr(a, "ring", None), getattr(a, "aura_rule", None)
    over = {"aura_thr": getattr(a, "aura_thr", None), "ring_cell": getattr(a, "ring_cell", None),
            "ring_dy": getattr(a, "ring_dy", None),
            "ring": None if ring is None else tuple(float(v) for v in ring),
            "aura_rule": None if rule is None else tuple(int(v) for v in rule)}  # fmt: skip
    try:
        return prof.recipe(**over)
    except ValueError as e:
        raise SystemExit(str(e)) from None


def aura_fields(recipe: dict[str, Any], prof: mvp_profiles.BossProfile,
                round_: int = 1) -> dict[str, Any]:  # fmt: skip
    """The model's aura fields of a resolved recipe, its profile and its version
    (``<name>-v<round>``: the Orc Lord's ``orclord-v1``, as before; round 2's ``stormy-v2``)."""
    return {"ring": tuple(float(v) for v in recipe["ring"]), "ring_cell": int(recipe["ring_cell"]),
            "ring_dy": float(recipe["ring_dy"]),
            "aura_rule": tuple(int(v) for v in recipe["aura_rule"]),
            "profile": prof.name, "version": f"{prof.name}-v{round_}"}  # fmt: skip


def aura_threshold(neg_max: float, margin: float) -> float:
    """PURE: the aura threshold from the DEV negatives' max: max + margin, rounded UP to 0.01
    (round 1's 0.0417 + 0.015 -> 0.06, stormy-knight-recognizer.md 5b)."""
    import math

    return math.ceil(round((neg_max + margin) * 100.0, 9)) / 100.0


def seen_rule(party: float, aura: float, lin_thr: float, aura_thr: float, mode: str,
              aura_and: float = 0.5) -> bool:  # fmt: skip
    """PURE: mvp_watch.decide's ``seen`` from a frame's best party and aura scores, by the
    model's aura mode (or / and / off; mvp_watch.and_threshold)."""
    if party >= lin_thr:
        return True
    if mode == "off":
        return False
    if mode == "and":
        return aura >= aura_thr and party >= lin_thr - (1.0 - aura_and) * abs(lin_thr)
    return aura >= aura_thr


def memmap_names(watch: Path, sessions: Sequence[Any], round_: int) -> tuple[str, list[str]]:
    """The fit's / dev's memmap file names: round 1's ``watch-dev.npy`` / ``hunt-<i>.npy`` (as
    before); round 2's by session id, so the leave-one-out fits share one --work."""
    if round_ == 1:
        return "watch-dev.npy", [f"hunt-{i}.npy" for i in range(len(sessions))]
    return (f"watch-{Path(watch).name}.npy",
            [f"hunt-{Path(s).name}.npy" for s in sessions])  # fmt: skip


def _round(a: argparse.Namespace) -> int:
    r = int(getattr(a, "round", None) or 1)
    if r not in ROUNDS:
        raise SystemExit(f"--round {r}: not one of {ROUNDS}")
    return r


def _parts(round_: int) -> int | None:
    return PART_FRAMES if round_ == 2 else None


def _changes(session: Path) -> list[int]:
    return sorted(int(e["t_mono_ns"]) for e in _events(session) if e.get("type") == "map_change")


def cmd_fit(a: argparse.Namespace) -> dict[str, Any]:
    """DEV only: the watch's cells 0-7 (and before the first spawn), the pilot's first 300 s on
    the map, and every --extra hunting session (Amendment B). Per boss: the profile's DEV cells,
    party and aura recipe (fit_recipe). ``--round 2``: the whole watch and every whole hunting
    session (watch_split, hunt_split), the memmaps by session id in parts (rule 7), the version
    ``<profile>-v2``. ``--aura``: the model's aura mode; ``--aura-margin``: the aura threshold
    from the DEV negatives' max (aura_threshold)."""
    import mvp_watch as mw

    prof = profile_of(a)
    round_ = _round(a)
    mode = str(getattr(a, "aura", None) or "or")
    aura_and = float(getattr(a, "aura_and", None) or mw.AURA_AND)
    margin = getattr(a, "aura_margin", None)
    if mode not in mw.AURA_MODES:
        raise SystemExit(f"--aura {mode}: not one of {mw.AURA_MODES}")
    if prof is ORCLORD and mode != "or":
        raise SystemExit("--boss orclord keeps the v1 format: --aura or")
    if margin is not None and getattr(a, "aura_thr", None) is not None:
        raise SystemExit("--aura-margin sets the aura threshold from DEV: not with --aura-thr")
    recipe = fit_recipe(a, prof)
    aura_thr = float(recipe["aura_thr"])
    a.work.mkdir(parents=True, exist_ok=True)
    wrows = _rows(a.watch_truth, prof)
    wmap = _map_of(a.watch_truth, prof)
    spawns, kills = watch_times(a.events, prof.boss)
    # round 1: cells 0-7 and the frames before the first spawn; round 2: the whole watch
    dev_w = watch_split(wrows, spawns, wmap, prof, round_, "dev")
    sessions = [a.pilot, *(a.extra or [])]
    wname, hnames = memmap_names(a.watch, [s for s, _ in sessions], round_)
    watch, wids = half_frames(a.watch, dev_w, a.work / wname, _parts(round_))
    hunts = []
    lone_left: dict[str, int] = {}
    for i, (session, tpath) in enumerate(sessions):
        rows = _rows(Path(tpath), prof)
        keep = hunt_split(list(rows.values()), _map_of(Path(tpath), prof), i == 0, round_, "dev")
        keep, lone = hunt_negatives(rows, keep, session, prof)
        if prof.lone:
            lone_left[Path(session).name] = len(lone)
        arr, ids = half_frames(Path(session), keep, a.work / hnames[i], _parts(round_))
        hunts.append((arr, ids, rows, _rects(Path(tpath), prof)))
    wrects = _rects(a.watch_truth, prof)  # the Orc Lord's ow1: STANDARD_RECTS, as before
    ui_watch = mw.rect_mask((360, 640), wrects)
    changes = _changes(a.watch)
    h = colour_hists(watch, wids, wrows, spawns, kills, changes,
                     colour_cells(prof, round_, spawns, kills), ui_watch, prof.party)  # fmt: skip
    hh = np.zeros(mw.NBINS)
    for arr, _, _, hrects in hunts:  # the Orc Lord's pilots: HUNT_RECTS, as before
        ui_hunt = mw.rect_mask((360, 640), hrects)
        for img in arr:
            hh += np.bincount(mw.lut_index(np.asarray(img))[~ui_hunt], minlength=mw.NBINS)
    body = llr_of(h["hP"], h["hN"] + BODY_HUNT_W * hh + BODY_OTHER_W * h["hO"])
    x0, y0, x1, y1 = (v // mw.STEP for v in mw.TITLE_BOX)
    title = np.median(
        np.stack(
            [
                np.asarray(arr[j])[y0:y1, x0:x1].astype(np.float32).mean(axis=2)
                for arr, _, _, _ in hunts
                for j in range(0, len(arr), 10)
            ]
        ),
        axis=0,
    )
    zero = np.zeros((mw.N_FEATURES, *mw.WIN), np.float32)
    aura = aura_fields(recipe, prof, round_)
    model0 = mw.Model(body_lut=body, lin_w=zero, lin_b=0.0, lin_thr=0.0, aura_thr=aura_thr,
                      title=title.astype(np.float32), **aura)  # fmt: skip
    items = make_items(watch, wids, wrows, model0, wrects, hunt=False, jobs=prof.party)
    for arr, ids, rows, hrects in hunts:
        items += make_items(arr, ids, rows, model0, hrects, hunt=True, jobs=prof.party)
    neg_aura = max(it.aura for it in items if it.kind in ("neg", "hunt"))
    if margin is not None:  # round 2: the aura threshold from DEV (the negatives' max + margin)
        aura_thr = aura_threshold(neg_aura, float(margin))
    train: dict[str, Any] = {}
    w, b = train_party(items, stats=train)
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
    model = mw.Model(body_lut=body, lin_w=w, lin_b=b, lin_thr=lin_thr, aura_thr=aura_thr,
                     title=title.astype(np.float32), zone_penalty=penalty, aura_mode=mode,
                     aura_and=aura_and, **aura)  # fmt: skip
    sha = mw.save(a.out, model)
    best = [max(o, i - penalty) for o, i in zip(out_best, in_best, strict=True)]
    negs = [s for s, n in zip(best, is_neg, strict=True) if n]
    pos = [(s, it.aura) for s, it in zip(best, items, strict=True) if it.kind == "pos"]
    recall = float(np.mean([seen_rule(s, au, lin_thr, aura_thr, mode, aura_and)
                            for s, au in pos]))  # fmt: skip
    pixels = {k: int(v.sum()) for k, v in h.items()} | {"hunt": int(hh.sum())}
    rep = {"model": str(a.out), "sha256": sha, "lin_thr": round(lin_thr, 4), "lin_b": round(b, 4),
           "zone_thr": round(zone_thr, 4), "zone_penalty": round(penalty, 4),
           "aura_thr": aura_thr, "dev_items": dict(Counter(it.kind for it in items)),
           "dev_neg_max_party": round(max(negs), 4), "dev_neg_max_aura": round(neg_aura, 4),
           "dev_pos_recall_in_sample": round(recall, 4), "colour_pixels": pixels}  # fmt: skip
    if prof is not ORCLORD or round_ != 1:  # the Orc Lord's report keeps its keys
        rep |= {"boss": prof.name, "lone_frames_left_out": lone_left,
                "recipe": {k: list(v) if isinstance(v, tuple) else v
                           for k, v in recipe.items()}}  # fmt: skip
        rep |= {"round": round_, "version": model.version, "aura_mode": mode,
                "aura_margin": margin, "train_rows": train,
                "dev_frames": {"watch": len(wids),
                               **{Path(s).name: len(ids) for (s, _), (_, ids, _, _)
                                  in zip(sessions, hunts, strict=True)}}}  # fmt: skip
        if mode == "and":
            rep["aura_and"] = aura_and
            rep["and_thr"] = round(mw.and_threshold(model), 4)
    return rep


def _full_frames(session: Path, keep: set[int]) -> Iterable[tuple[int, int, Any]]:
    import map_labels as ml

    manifest = json.loads((session / "manifest.json").read_text())
    for r in png_index(session, manifest):
        if r.frame_id in keep:
            yield r.frame_id, int(r.t_mono_ns), ml.read_png(r)


def cmd_score(a: argparse.Namespace) -> dict[str, Any]:
    """HELD-OUT, once: the watch's cells 8-14, the pilot after its first 300 s; --supplement
    sessions (Amendment B) are reported apart. decide() on the FULL frames, timed, by the
    model's own recipe (its aura mode too). Per boss: the profile's HELD-OUT cells (stormy: 8-15)
    and party; the model must be the profile's. ``--round 2``: the whole watch (every cell) and
    the whole pilot are HELD-OUT, and the model must be a round-2 one (version_round)."""
    import mvp_watch as mw

    prof = profile_of(a)
    round_ = _round(a)
    try:
        model = mw.load(a.model, a.sha256, profile=prof.name)
    except mw.ModelUnavailable as e:
        raise SystemExit(str(e)) from None
    if version_round(model.version) != round_:
        raise SystemExit(f"{a.model}: a {model.version} model, not a round-{round_} one")
    ms: list[float] = []
    wrows = _rows(a.watch_truth, prof)
    wmap = _map_of(a.watch_truth, prof)
    spawns, _ = watch_times(a.events, prof.boss)
    # round 1: the HELD-OUT cells; round 2: the whole (held-out) watch
    held = watch_split(wrows, spawns, wmap, prof, round_, "held")
    per_cell: dict[int, list[tuple[float, str, bool]]] = {}
    gap = {"n": 0, "fp": 0, "fp_frames": []}
    pos_frames = {"n": 0, "seen": 0, "lord_n": 0, "lord_seen": 0}
    wrects = _rects(a.watch_truth, prof)  # the Orc Lord's ow1: STANDARD_RECTS, as before
    for fid, t, img in _full_frames(a.watch, held):
        v, dt = mw.timed(img, model, ui_rects=wrects)
        ms.append(dt)
        row = wrows[fid]
        kind = kind_of(row, prof.party)
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
            if any(u["in_view"] and u["job"] == prof.boss for u in row["units"]):
                pos_frames["lord_n"] += 1
                pos_frames["lord_seen"] += int(v["seen"])
    cells = {c: cell_scores(seq) for c, seq in sorted(per_cell.items())}
    first = {c: d["episodes"][0] for c, d in cells.items() if d["episodes"]}
    later = [e for d in cells.values() for e in d["episodes"][1:]]
    hunting = []
    for name, (session, tpath) in [("pilot", a.pilot)] + [
        (f"supplement:{Path(s).name}", (s, t)) for s, t in (a.supplement or [])
    ]:
        rows = _rows(Path(tpath), prof)
        keep = hunt_split(list(rows.values()), _map_of(Path(tpath), prof), name == "pilot",
                          round_, "held")  # fmt: skip
        keep, lone = hunt_negatives(rows, keep, session, prof)
        hrects = _rects(Path(tpath), prof)  # the Orc Lord's pilot / s1: HUNT_RECTS, as before
        n, fp, fps, reasons = 0, 0, [], Counter()
        lone_seen: dict[int, bool] = {}
        for fid, _, img in _full_frames(Path(session), keep | lone):
            v, dt = mw.timed(img, model, ui_rects=hrects)
            ms.append(dt)
            if fid in lone:  # a lone summon's own spawn (stormy: Garm Baby): reported apart
                lone_seen[fid] = bool(v["seen"])
                continue
            n += 1
            reasons[str(v["reason"])] += 1
            if v["seen"]:
                fp += 1
                fps.append([fid, v["cue"], v["where"], v["aura"], v["party"]])
        h = {"name": name, "frames": n, "fp": fp, "fp_per_10min": fp_rate(fp, n),
             "fp_frames": fps, "reasons": dict(reasons)}  # fmt: skip
        if prof.lone:
            h["lone"] = lone_report(rows, lone, lone_seen, n + len(lone), prof)
        hunting.append(h)
    n_cells = len(first)
    within = sum(e["within"] for e in first.values())
    lat = np.array(ms)
    return {
        "model": str(a.model), "sha256": model.sha256,
        **({} if prof is ORCLORD else {"boss": prof.name, "held_cells": sorted(prof.held_cells)}),
        **({} if round_ == 1 else {"round": round_, "held_cells": "all", "version": model.version,
                                   "aura_mode": model.aura_mode}),
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


def _top(rows: Sequence[tuple[int, float, float]], k: int = 5) -> dict[str, Any]:
    """The ``k`` highest party and aura scores of (frame id, party, aura) negatives."""
    by_p = sorted(rows, key=lambda r: -r[1])[:k]
    by_a = sorted(rows, key=lambda r: -r[2])[:k]
    return {"party": [[f, p, au] for f, p, au in by_p], "aura": [[f, p, au] for f, p, au in by_a]}


def cmd_dev(a: argparse.Namespace) -> dict[str, Any]:
    """DEV ONLY (stormy-knight-recognizer.md 9): exactly the frames ``fit --round R`` takes (the
    same watch_split / hunt_split / hunt_negatives, the same memmaps in --work), decided with a
    model from the half-res memmaps (decide_half on a memmap frame = decide on the full frame).
    The watch's cells (first-episode delay, within RECALL_S), its gap frames, and per hunting
    session the false positives per 10 min and its lone frames. Every number is IN-SAMPLE for the
    sessions the model was fitted on; a session left out of its fit gives the leave-one-out rate.
    It cannot tell a held-out session from a DEV one: never give it one (the caller's split).
    Without --model: decode the memmaps only (its own memory scope, before the fits)."""
    import mvp_watch as mw

    prof = profile_of(a)
    round_ = _round(a)
    model = None
    if a.model is not None:
        if not a.sha256:
            raise SystemExit("dev --model needs --sha256")
        try:
            model = mw.load(a.model, a.sha256, profile=prof.name)
        except mw.ModelUnavailable as e:
            raise SystemExit(str(e)) from None
    a.work.mkdir(parents=True, exist_ok=True)
    wrows = _rows(a.watch_truth, prof)
    wmap = _map_of(a.watch_truth, prof)
    spawns, _ = watch_times(a.events, prof.boss)
    dev_w = watch_split(wrows, spawns, wmap, prof, round_, "dev")
    sessions = [a.pilot, *(a.extra or [])]
    wname, hnames = memmap_names(a.watch, [s for s, _ in sessions], round_)
    watch, wids = half_frames(a.watch, dev_w, a.work / wname, _parts(round_))
    hunts = []
    for i, (session, tpath) in enumerate(sessions):
        rows = _rows(Path(tpath), prof)
        keep = hunt_split(list(rows.values()), _map_of(Path(tpath), prof), i == 0, round_, "dev")
        keep, lone = hunt_negatives(rows, keep, session, prof)
        arr, ids = half_frames(Path(session), keep, a.work / hnames[i], _parts(round_))
        larr, lids = (None, [])
        if lone:
            larr, lids = half_frames(Path(session), lone, a.work / f"lone-{hnames[i]}",
                                     _parts(round_))  # fmt: skip
        hunts.append((Path(session).name, arr, ids, larr, lids, rows, lone,
                      _rects(Path(tpath), prof)))  # fmt: skip
    decoded = {"watch": len(wids), **{h[0]: [len(h[2]), len(h[4])] for h in hunts}}
    rep: dict[str, Any] = {"round": round_, "boss": prof.name, "split": "dev", "decoded": decoded}
    if model is None:
        return rep
    wrects = _rects(a.watch_truth, prof)
    per_cell: dict[int, list[tuple[float, str, bool]]] = {}
    gap: dict[str, Any] = {"n": 0, "fp": 0, "fp_frames": []}
    pos_frames = {"n": 0, "seen": 0, "lord_n": 0, "lord_seen": 0}
    gap_scores: list[tuple[int, float, float]] = []
    for i, fid in enumerate(wids):
        v = mw.decide_half(np.asarray(watch[i]), model, wrects)
        row = wrows[fid]
        kind = kind_of(row, prof.party)
        t = int(row["t"])
        per_cell.setdefault(cell_of(t, spawns), []).append((t / 1e9, kind, bool(v["seen"])))
        if kind == "neg":
            gap["n"] += 1
            if v["party"] is not None:
                gap_scores.append((fid, float(v["party"]), float(v["aura"])))
            if v["seen"]:
                gap["fp"] += 1
                gap["fp_frames"].append([fid, v["cue"], v["where"], v["aura"], v["party"]])
        elif kind == "pos":
            pos_frames["n"] += 1
            pos_frames["seen"] += int(v["seen"])
            if any(u["in_view"] and u["job"] == prof.boss for u in row["units"]):
                pos_frames["lord_n"] += 1
                pos_frames["lord_seen"] += int(v["seen"])
    cells = {c: cell_scores(seq) for c, seq in sorted(per_cell.items())}
    first = {c: d["episodes"][0] for c, d in cells.items() if d["episodes"]}
    later = [e for d in cells.values() for e in d["episodes"][1:]]
    hunting = []
    for name, arr, ids, larr, lids, rows, lone, hrects in hunts:
        n, fp, fps, reasons = 0, 0, [], Counter()
        neg_scores: list[tuple[int, float, float]] = []
        for i, fid in enumerate(ids):
            v = mw.decide_half(np.asarray(arr[i]), model, hrects)
            n += 1
            reasons[str(v["reason"])] += 1
            if v["party"] is not None:
                neg_scores.append((fid, float(v["party"]), float(v["aura"])))
            if v["seen"]:
                fp += 1
                fps.append([fid, v["cue"], v["where"], v["aura"], v["party"]])
        hrep: dict[str, Any] = {"session": name, "frames": n, "fp": fp,
                                "fp_per_10min": fp_rate(fp, n), "fp_frames": fps,
                                "reasons": dict(reasons), "top": _top(neg_scores)}  # fmt: skip
        if prof.lone:
            lone_seen = {fid: bool(mw.decide_half(np.asarray(larr[i]), model, hrects)["seen"])
                         for i, fid in enumerate(lids)} if larr is not None else {}  # fmt: skip
            hrep["lone"] = lone_report(rows, lone, lone_seen, n + len(lone), prof)
        hunting.append(hrep)
    within = sum(e["within"] for e in first.values())
    rep |= {
        "model": str(a.model), "sha256": model.sha256, "version": model.version,
        "aura_mode": model.aura_mode, "aura_thr": model.aura_thr,
        "lin_thr": round(model.lin_thr, 4), "zone_penalty": round(model.zone_penalty, 4),
        "cells": {str(c): e for c, e in first.items()}, "cells_n": len(first),
        "cells_within": within,
        "first_frame": sum(e["first_frame"] for e in first.values()),
        "reentries": {"n": len(later), "within": sum(e["within"] for e in later),
                      "never": sum(e["delay"] is None for e in later)},
        "pos_frames": pos_frames,
        "watch_gap": gap | {"fp_per_10min": fp_rate(gap["fp"], gap["n"]),
                            "top": _top(gap_scores)},
        "hunting": hunting,
    }  # fmt: skip
    if model.aura_mode == "and":
        rep["and_thr"] = round(mw.and_threshold(model), 4)
    return rep


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


def _party_units(row: dict[str, Any], jobs: Collection[int] = MVP_PARTY) -> list[list[Any]]:
    return [[u["job"], u["gid"], u["box"], u["in_view"], u.get("state")] for u in row["units"]
            if u["job"] in jobs]  # fmt: skip


def cmd_entries(a: argparse.Namespace) -> dict[str, Any]:
    """ROUND 2, once (section 10 + 10a): the edge watch's entries and the hunting negatives, with
    decide(..., cues=ROUND2_CUES) on the FULL frames, timed. Per boss: the profile's party; the
    model must be the profile's."""
    import mvp_watch as mw

    prof = profile_of(a)
    try:
        model = mw.load(a.model, a.sha256, profile=prof.name)
    except mw.ModelUnavailable as e:
        raise SystemExit(str(e)) from None
    ms: list[float] = []
    wdoc = truth_of(a.watch_truth, prof)
    wmap = str(wdoc.get("map", prof.map))
    wrects = mask_rects(wdoc)  # the truth's layout (and chat window), as before
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
        kind = kind_of(row, prof.party)
        lord = any(u["in_view"] and u["job"] == prof.boss for u in row["units"])
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
        doc = truth_of(Path(tpath), prof)
        hmap = str(doc.get("map", prof.map))
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
        hrects = mask_rects(doc)  # the Orc Lord's a1-a6 (hunt, legacy chat): HUNT_RECTS
        for fid, t, img in _full_frames(Path(session), keep):
            v, dt = mw.timed(img, model, ui_rects=hrects, cues=ROUND2_CUES)
            ms.append(dt)
            row = by_id[fid]
            kind = kind_of(row, prof.party)
            s["reasons"][str(v["reason"])] += 1
            if kind != "neg":
                s["party_frames"].append([fid, t, kind, bool(v["seen"]), v["aura"], v["where"],
                                          row["flags"], _party_units(row, prof.party)])  # fmt: skip
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
        **({} if prof is ORCLORD else {"boss": prof.name}),
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


def parser() -> argparse.ArgumentParser:
    """The command line (every subcommand takes --boss, default orclord)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def boss_arg(q: argparse.ArgumentParser) -> None:
        q.add_argument("--boss", choices=sorted(mvp_profiles.PROFILES),
                       default=mvp_profiles.DEFAULT,
                       help="the boss profile (scripts/mvp_profiles.py; %(default)s)")  # fmt: skip

    p = sub.add_parser("truth")
    boss_arg(p)
    p.add_argument("session", type=Path)
    p.add_argument("--layout", choices=("standard", "hunt"), required=True)
    p.add_argument("--kb", type=Path, default=MAIN / "data" / "kb")
    p.add_argument(
        "--mapcache-dir",
        type=Path,
        default=MAIN / "packages/poring_dataset/src/poring_dataset/_generated",
    )
    p.add_argument("--map", default=None,
                   help="keep units on this map (Amendment 10a; default: the profile's hunting "
                   "map: orclord gef_fild10, stormy xmas_dun02)")  # fmt: skip
    p.add_argument("--sprites", type=Path, default=None,
                   help="the decoded monster sprites (default: the profile's)")  # fmt: skip
    p.add_argument("--sprite-names", type=Path, default=None,
                   help="the client stems (default: the profile's)")  # fmt: skip
    p.add_argument("--chat", default="auto",
                   help="the chat window: auto (the session's date, chat_window.for_sid), "
                   "legacy, standard, X0,Y0,X1,Y1")  # fmt: skip
    p.add_argument("--out", type=Path, required=True)
    q = sub.add_parser("entries")
    boss_arg(q)
    q.add_argument("--model", type=Path, required=True)
    q.add_argument("--sha256", required=True)
    q.add_argument("--watch", type=Path, required=True)
    q.add_argument("--watch-truth", type=Path, required=True)
    q.add_argument("--events", type=Path, required=True)
    q.add_argument("--hunt", nargs=2, action="append", required=True,
                   metavar=("SESSION", "TRUTH"))  # fmt: skip
    q.add_argument("--out", type=Path, required=True)
    for name in ("fit", "score", "dev"):
        q = sub.add_parser(name)
        boss_arg(q)
        q.add_argument("--round", type=int, choices=ROUNDS, default=1,
                       help="the split: 1 = the pre-registered cells and the pilot's "
                       "first 300 s; 2 = whole sessions (stormy-knight-recognizer.md 7; "
                       "%(default)s)")  # fmt: skip
        q.add_argument("--watch", type=Path, required=True)
        q.add_argument("--watch-truth", type=Path, required=True)
        q.add_argument("--events", type=Path, required=True)
        q.add_argument("--pilot", nargs=2, metavar=("SESSION", "TRUTH"), required=True)
        q.add_argument("--out", type=Path, required=True)
        if name == "dev":
            q.add_argument("--extra", nargs=2, action="append", metavar=("SESSION", "TRUTH"))
            q.add_argument("--work", type=Path, required=True)
            q.add_argument("--model", type=Path, default=None)
            q.add_argument("--sha256", default=None)
        elif name == "fit":
            q.add_argument("--extra", nargs=2, action="append", metavar=("SESSION", "TRUTH"))
            q.add_argument("--work", type=Path, required=True)
            q.add_argument("--aura", choices=("or", "and", "off"), default="or",
                           help="how the model combines its cues (mvp_watch aura_mode; "
                           "%(default)s = the v1 recipe)")  # fmt: skip
            q.add_argument("--aura-and", type=float, default=0.5,
                           help="--aura and: the party's share of its threshold the aura path "
                           "needs (%(default)s)")  # fmt: skip
            q.add_argument("--aura-margin", type=float, default=None,
                           help="the aura threshold = the DEV negatives' max + this, rounded up "
                           "to 0.01 (round 2; default: the profile's / --aura-thr)")  # fmt: skip
            # the aura recipe (default: the profile's; a None placeholder must be given here)
            q.add_argument("--aura-thr", type=float, default=None)
            q.add_argument("--ring", type=float, nargs=4, default=None,
                           metavar=("A", "B", "AI", "BI"), help="half-res px")  # fmt: skip
            q.add_argument("--ring-cell", type=int, default=None)
            q.add_argument("--ring-dy", type=float, default=None)
            q.add_argument("--aura-rule", type=int, nargs=2, default=None,
                           metavar=("G_MIN", "DIFF"),
                           help="G >= G_MIN, G - R and G - B >= DIFF")  # fmt: skip
        else:
            q.add_argument("--model", type=Path, required=True)
            q.add_argument("--sha256", required=True)
            q.add_argument("--supplement", nargs=2, action="append", metavar=("SESSION", "TRUTH"))
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.cmd == "truth":
        prof = profile_of(a)
        doc = truth(a.session, a.layout, kb=a.kb, mapcache_dir=a.mapcache_dir, map_name=a.map,
                    sprites=a.sprites, sprite_names=a.sprite_names, prof=prof,
                    chat=a.chat)  # fmt: skip
        doc["summary"] = summary(doc, prof)
        a.out.write_text(json.dumps(doc) + "\n")
        print(json.dumps(doc["summary"], indent=1))
    elif a.cmd == "fit":
        rep = cmd_fit(a)
        print(json.dumps(rep, indent=1))
    elif a.cmd == "dev":
        rep = cmd_dev(a)
        a.out.write_text(json.dumps(rep, indent=1) + "\n")
        print(json.dumps({k: v for k, v in rep.items() if k not in ("cells", "hunting")}, indent=1))
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
