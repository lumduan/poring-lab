#!/usr/bin/env python3
"""MAP-PARAMETERISED MONSTER LABELS for RECORDER sessions: the orcsdun01 o3h rule on another map
(docs/planning/payf07-detector.md, PRE-REGISTERED 2026-10-24 18:25:24 ICT, 7ed0422, before this
was built). The rule is scripts/orc_labels_fix.py's (fix 2 facing, 2b / 2c, the fit, o3h); this
module adds what another map and another recording path need, and never changes orcsdun01's.

    map_labels.py offset    PART... --out JSON                     4b: 1d, FIT only
    map_labels.py threshold PART... --offset JSON --out JSON       4e: o3h's T_h, FIT only
    map_labels.py freeze --offset JSON --threshold JSON --out PARAMS
    map_labels.py check     PART... --params PARAMS --out JSON     5: C1 / C2 (T1 on TEST, or a
                                                                   TRAIN session's own C1, 3c)
    map_labels.py labels    PART    --params PARAMS --out JSON     the kept labels (no pixels)
    map_labels.py pack      LABELS.json... --seed 21 --pack-dir DIR --key-dir DIR
                            --instructions TXT --instructions-sha256 HEX       6: T2's pack

A PART is a session directory, optionally restricted to the staged session's spots:
``DIR`` or ``DIR:spots=0-7``. The map's spec (MAPS) names its FIT and TEST parts; the measuring
commands refuse TEST, and ``labels`` / ``pack`` refuse TEST too (the evaluation's TEST labels are a
later step).

OFFLINE ONLY (ADR-0007: packets are ground truth for labels, never an agent input): the session's
packets, its PNG tar shards (read-only, NAS), the decoded sprites, the map's RSW / RSM models and a
local KB (client- and GPL-derived: /dev/shm only, never committed). No GPU, no client, no input.

The candidate frames (4f): the map is the spec's at tw = t - 1d and at t; no map change in
[t - 5 s, t]; our character's Timeline position the same at every 100 ms from tw - 1 s to t;
outside the GM windows; the staged session outside each spot's inventory span [first drop - 20 s,
last drop result + 5 s]; the hunting layout read from pixels (client_layout) per frame.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import io
import json
import random
import shutil
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import orc_camera_check as occ  # noqa: E402
import orc_labels_fix as olf  # noqa: E402
import qa_export  # noqa: E402

from poring_dataset.camera import map_key  # noqa: E402
from poring_dataset.labels import in_windows  # noqa: E402
from poring_dataset.render import anchor_and_depth  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

Box = tuple[float, float, float, float]
TMP = Path("/dev/shm/poring-lab-tmp/payf07")
STILL_BACK_NS = 1_000_000_000  # 4f: still from tw - 1 s ...
STILL_STEP_NS = 100_000_000  # ... checked every 100 ms up to t
MAP_CHANGE_NS = 5_000_000_000  # 4f: no map change in [t - 5 s, t]
INV_BEFORE_NS = 20_000_000_000  # 4f: the staged inventory span, first drop - 20 s ...
INV_AFTER_NS = 5_000_000_000  # ... last drop result + 5 s
SWEEP_MAX_MS = 500  # 4b: the 1d sweep's upper edge (Amendment A 18:35:20; attempt 1: 1,000)
COARSE_MS = tuple(range(0, SWEEP_MAX_MS + 1, 50))
MIN_WALKER_SAMPLES = 50  # 4b's stop
T_H_PERCENTILE = 5.0  # 4e: the clear kept labels' p5
C1_BAR = 0.050  # T1 (5): unrounded
C2_BAR_PX = 4.0  # every species is ground (1b)
C2_MIN_LABELS = 20
OWN_C1_MIN = 50  # 3c: a session's own C1 needs >= 50 standing labels scored
T2_PER_SPECIES = 30
T2_SALT = "payf07"
LABELS = "payf07-o3h"
ENGAGED = "engaged"  # Amendment B (18:54:50): a fight with our character near the label's time
ENGAGED_BACK_NS = 3_000_000_000
ENGAGED_FWD_NS = 1_000_000_000


@dataclass(frozen=True)
class MapSpec:
    """One map's label inputs (payf07-detector.md 1-4)."""

    name: str
    cells: tuple[int, int]
    rsw: Path
    models: Path
    species: tuple[int, ...]  # the map's spawn species (the tier's)
    walkers: tuple[int, ...]  # 1d's mobile species
    fit_px: int
    staged: str  # the staged session's id
    fit: dict[str, frozenset[int] | None]  # session id -> its FIT spots (None: the whole session)
    test: dict[str, frozenset[int] | None]
    kb: Path
    sprites: Path


PAYF07 = MapSpec(
    name="pay_fild07",
    cells=(400, 400),
    rsw=TMP / "grf" / "data" / "pay_fild07.rsw",
    models=TMP / "grf" / "data" / "model",
    species=(1033, 1010, 1116, 1060, 1031, 1080),
    walkers=(1033, 1116, 1060, 1031, 1010),
    fit_px=6,
    staged="20261024T170356-rdp-stage-items-b",
    fit={"20261024T170356-rdp-stage-items-b": frozenset(range(8)),
         "20261024T123622-rdp-thief-t1b": None},
    test={"20261024T170356-rdp-stage-items-b": frozenset(range(8, 12)),
          "20261024T131838-rdp-thief-t2": None},
    kb=TMP / "kb",
    sprites=TMP / "sprites-all",
)  # fmt: skip
MAPS = {"pay_fild07": PAYF07}


# --- pure parts -------------------------------------------------------------------------------


def parse_part(text: str) -> tuple[Path, frozenset[int] | None]:
    """``DIR`` -> (DIR, None); ``DIR:spots=0-7`` / ``DIR:spots=0,2,5-6`` -> (DIR, {spots})."""
    path, sep, rest = text.partition(":spots=")
    if not sep:
        return Path(text), None
    spots: set[int] = set()
    for chunk in rest.split(","):
        lo, dash, hi = chunk.partition("-")
        if not lo.isdigit() or (dash and not hi.isdigit()):
            raise SystemExit(f"{text!r}: spots are N, N-M or a comma list of them")
        spots.update(range(int(lo), int(hi if dash else lo) + 1))
    return Path(path), frozenset(spots)


def overlaps_role(sid: str, spots: frozenset[int] | None,
                  role: dict[str, frozenset[int] | None]) -> bool:  # fmt: skip
    """The part (session, spots or the whole session) shares a frame with ``role``'s parts."""
    if sid not in role:
        return False
    rs = role[sid]
    return rs is None or spots is None or bool(spots & rs)


def inside_role(sid: str, spots: frozenset[int] | None,
                role: dict[str, frozenset[int] | None]) -> bool:  # fmt: skip
    """Every frame of the part lies in ``role``'s parts."""
    if sid not in role:
        return False
    rs = role[sid]
    return rs is None or (spots is not None and spots <= rs)


def spot_starts(events: Iterable[dict[str, Any]]) -> list[int]:
    """The staged session's spot starts (3a): the ``map_change`` times followed by at least one
    ``drop_request`` before the next ``map_change``, in time order."""
    out: list[int] = []
    last: int | None = None
    dropped = False
    for e in sorted(events, key=lambda e: int(e["t_mono_ns"])):
        if e.get("type") == "map_change":
            if last is not None and dropped:
                out.append(last)
            last, dropped = int(e["t_mono_ns"]), False
        elif e.get("type") == "drop_request" and last is not None:
            dropped = True
    if last is not None and dropped:
        out.append(last)
    return out


def spot_of(t: int, starts: Sequence[int]) -> int | None:
    """The spot index of time ``t`` (None before the first spot)."""
    i = bisect.bisect_right(starts, t) - 1
    return i if i >= 0 else None


def inventory_spans(events: Iterable[dict[str, Any]], starts: Sequence[int]
                    ) -> list[tuple[int, int]]:  # fmt: skip
    """4f: per spot, [its first ``drop_request`` - 20 s, its last ``drop_result`` (or request)
    + 5 s]."""
    by: dict[int, list[int]] = defaultdict(list)
    for e in events:
        if e.get("type") in ("drop_request", "drop_result"):
            k = spot_of(int(e["t_mono_ns"]), starts)
            if k is not None:
                by[k].append(int(e["t_mono_ns"]))
    return [(min(ts) - INV_BEFORE_NS, max(ts) + INV_AFTER_NS) for _k, ts in sorted(by.items())]


def still_times(tw: int, t: int, back: int = STILL_BACK_NS,
                step: int = STILL_STEP_NS) -> list[int]:  # fmt: skip
    """The times our character must stand at one place (4f): every ``step`` from tw - back to t,
    both ends included."""
    out = list(range(tw - back, t, step))
    return out + [t]


def same_place(points: Sequence[tuple[float, float] | None]) -> bool:
    return bool(points) and points[0] is not None and all(p == points[0] for p in points)


def recent(times: Sequence[int], t: int, window: int) -> bool:
    """A time of ``times`` (sorted) lies in [t - window, t]."""
    i = bisect.bisect_left(times, t - window)
    return i < len(times) and times[i] <= t


def sweep_fine(best: int) -> list[int]:
    """4b's fine grid: 10 ms within +-50 of the coarse best, clipped to the sweep (Amendment A)."""
    return olf.fine_grid(best, lo=COARSE_MS[0], hi=COARSE_MS[-1])


def engagement_times(events: Iterable[dict[str, Any]], aid: int) -> dict[int, list[int]]:
    """Amendment B: per unit, the times of an ``act`` between it and our character (either
    direction) or of our ``attack_request`` on it, sorted."""
    out: dict[int, list[int]] = defaultdict(list)
    for e in events:
        kind = e.get("type")
        if kind == "act":
            src, dst = e.get("src_gid"), e.get("target_gid")
            if src == aid and dst is not None and dst != aid:
                out[int(dst)].append(int(e["t_mono_ns"]))
            elif dst == aid and src is not None and src != aid:
                out[int(src)].append(int(e["t_mono_ns"]))
        elif kind == "attack_request" and e.get("target_gid") is not None:
            out[int(e["target_gid"])].append(int(e["t_mono_ns"]))
    return {g: sorted(ts) for g, ts in out.items()}


def is_engaged(times: dict[int, list[int]], gid: int, tw: int, back: int = ENGAGED_BACK_NS,
               fwd: int = ENGAGED_FWD_NS) -> bool:  # fmt: skip
    """Amendment B: an engagement time of ``gid`` lies in [tw - back, tw + fwd]."""
    ts = times.get(gid, [])
    i = bisect.bisect_left(ts, tw - back)
    return i < len(ts) and ts[i] <= tw + fwd


@dataclass
class EngagedRule(olf.FacingRule):
    """fix 2's facing and 2b / 2c (orc_labels_fix.FacingRule), then Amendment B's ``engaged``."""

    times: dict[int, list[int]] = field(default_factory=dict)

    def choose(self, world: Any, e: Any, st: Any, rules: Any, tw: int, sheet: Any,
               yaw: float) -> tuple[tuple[int, str], str | None]:  # fmt: skip
        facing, why = super().choose(world, e, st, rules, tw, sheet, yaw)
        if why is None and is_engaged(self.times, e.gid, tw):
            return facing, ENGAGED
        return facing, why


def percentile(values: Sequence[float], q: float) -> float:
    """numpy's linear percentile, rounded to 3 decimals (4e: frozen to 3 decimals)."""
    return round(float(np.percentile(np.asarray(values, float), q)), 3)


def c2_summary(rows: Sequence[dict[str, Any]], bar: float = C2_BAR_PX,
               min_n: int = C2_MIN_LABELS) -> dict[str, Any]:  # fmt: skip
    """C2 (5) for one species: median |dx|, |dy| <= bar with >= min_n labels."""
    offs = [r for r in rows if r.get("dx") is not None]
    out: dict[str, Any] = {"n": len(offs), "bar_px": bar}
    if not offs:
        return {**out, "verdict": "NO_VERDICT"}
    adx = statistics.median(abs(r["dx"]) for r in offs)
    ady = statistics.median(abs(r["dy"]) for r in offs)
    out.update({"median_abs_dx": adx, "median_abs_dy": ady,
                "median_dx": statistics.median(r["dx"] for r in offs),
                "median_dy": statistics.median(r["dy"] for r in offs),
                "best_ncc_median": round(statistics.median(r["best"] for r in offs), 3),
                })  # fmt: skip
    if len(offs) < min_n:
        out["verdict"] = "NO_VERDICT"
    else:
        out["verdict"] = "PASS" if adx <= bar and ady <= bar else "FAIL"
    return out


def t1_summary(rows: Sequence[dict[str, Any]], species: Sequence[int],
               tau: float = olf.TAU) -> dict[str, Any]:  # fmt: skip
    """T1 (5): C1 pooled over ``species`` (bar <= 0.050, unrounded), per species; C2 per species
    (a FAIL is a STOP, not the verdict)."""
    mine = [r for r in rows if int(r["mob"]) in species]
    by: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in mine:
        by[int(r["mob"])].append(r)
    pooled = occ.c1_summary(mine, tau)
    scored, bad = pooled["scored"], pooled["bad_label"]
    ratio = bad / scored if scored else None
    c2 = {str(m): c2_summary(by[m]) for m in sorted(by)}
    stops = sorted(m for m, v in c2.items() if v["verdict"] == "FAIL")
    return {
        "c1": {"bar": f"bad_label / scored <= {C1_BAR} pooled over {list(species)} (unrounded)",
               "pooled": pooled, "ratio": ratio,
               "per_species": {str(m): occ.c1_summary(by[m], tau) for m in sorted(by)}},
        "c2": {"bar": f"median |dx|, |dy| <= {C2_BAR_PX} px, species with >= {C2_MIN_LABELS}",
               "per_species": c2, "stop_species": stops},
        "T1": "NO_VERDICT" if ratio is None else "PASS" if ratio <= C1_BAR else "FAIL",
        "c2_stop": bool(stops),
        "other_species_rows": len(rows) - len(mine),
    }  # fmt: skip


def own_c1_verdict(summary: dict[str, Any]) -> str:
    """3c's join rule for a TRAIN session: its own C1 <= 0.050 on >= 50 standing labels."""
    scored = summary["c1"]["pooled"]["scored"]
    if scored < OWN_C1_MIN:
        return "NOT_ADDED_TOO_FEW"
    return "ADDED" if summary["c1"]["ratio"] <= C1_BAR else "NOT_ADDED_C1"


def t2_order(items: Sequence[dict[str, Any]], seed: int, mob: int) -> list[dict[str, Any]]:
    """6: one species' pool sorted by (session, frame, gid), shuffled by
    ``random.Random(f"payf07:{seed}:{mob}")``."""
    order = sorted(items, key=lambda it: (it["session"], it["frame_id"], it["gid"]))
    random.Random(f"{T2_SALT}:{seed}:{mob}").shuffle(order)
    return order


def frame_exclusions(world: Any, scene: Any, size: tuple[int, int], spec_species: Sequence[int],
                     class_species: Sequence[int], aid: int | None) -> list[str]:  # fmt: skip
    """4g: what keeps a frame from being labelled whole besides its monster labels: a warp / NPC
    in view, another player in view, a monster of a species outside the tier or the classes."""
    out = []
    w, h = size
    for e in world.entities:
        if e.hidden:
            continue
        u = anchor_and_depth(scene, (e.x, e.y))[0]
        if not (0 <= u[0] < w and 0 <= u[1] < h):
            continue
        if e.objtype == 6:
            out.append("warp_in_view")
        elif e.objtype == 0 and e.gid != aid:
            out.append("other_player")
        elif e.objtype == 5 and e.job not in spec_species and e.job not in class_species:
            out.append(f"unchecked_species:{e.job}")
    return sorted(set(out))


# --- the session ------------------------------------------------------------------------------


def png_index(session: Path, manifest: dict[str, Any]) -> list[qa_export.JpegRef]:
    """Every frame of a recorder session (tar headers and the json members only), in frame order;
    a frame's png and json may lie in two shards."""
    pngs: dict[str, tuple[Path, int, int]] = {}
    metas: dict[str, dict[str, Any]] = {}
    for name in manifest["shards"]:
        shard = session / str(name)
        with tarfile.open(shard) as tar:
            for m in tar:
                key, _, ext = m.name.partition(".")
                if ext == "png":
                    pngs[key] = (shard, m.offset_data, m.size)
                elif ext == "json":
                    fh = tar.extractfile(m)
                    assert fh is not None
                    metas[key] = json.loads(fh.read())
    out = [qa_export.JpegRef(int(metas[k]["frame_id"]), int(metas[k]["t_mono_ns"]), *pngs[k])
           for k in set(pngs) & set(metas)]  # fmt: skip
    return sorted(out, key=lambda r: r.frame_id)


def read_png(ref: qa_export.JpegRef) -> npt.NDArray[np.uint8]:
    """One frame as BGR (one seek and read of its PNG bytes)."""
    from PIL import Image

    with ref.shard.open("rb") as fh:
        fh.seek(ref.offset)
        data = fh.read(ref.size)
    if len(data) != ref.size:
        raise ValueError(f"{ref.shard}@{ref.offset}: short read")
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def check_recording(manifest: dict[str, Any]) -> None:
    """3c's recording path (fail closed)."""
    want = {"backend": "rdp", "recorder_version": 5, "format": "png",
            "game_region": [80, 77, 1280, 720], "server": "lab-rathena"}  # fmt: skip
    bad = {k: manifest.get(k) for k, v in want.items() if manifest.get(k) != v}
    if bad:
        raise SystemExit(f"{manifest.get('session_id')}: not the recording path of 3c: {bad}")


def use_kb(spec: MapSpec) -> None:
    qa_export.KB_CLASSES = spec.kb / "classes.json"
    qa_export.KB_SPRITE_NAMES = spec.kb / "monster_sprite_names.json"


@dataclass
class RecSession:
    """A recorder session (or some of the staged session's spots) as orc_labels_fix.Session's
    interface: lab, refs, sid, dwells, scene(), layout_ok(), facing_rule(), candidates()."""

    path: Path
    spec: MapSpec
    spots: frozenset[int] | None
    lab: qa_export.Labeler
    refs: list[qa_export.JpegRef]
    sid: str
    layout: Any
    starts: list[int] = field(default_factory=list)
    inventory: list[tuple[int, int]] = field(default_factory=list)
    map_changes: list[int] = field(default_factory=list)
    dwells: list[tuple[int, int]] = field(default_factory=list)  # (orc's report reads len())
    dropped: Counter[str] = field(default_factory=Counter)

    @classmethod
    def open(cls, part: str, spec: MapSpec, layout_templates: Path) -> RecSession:
        path, spots = parse_part(part)
        manifest = json.loads((path / "manifest.json").read_text())
        check_recording(manifest)
        sid = qa_export.session_id(manifest)
        use_kb(spec)
        lab = qa_export.Labeler(path, str(olf.OLD_OFFSET_MS), labels="v1", k=olf.K)
        import client_layout

        lab.ui_rects = tuple((x0, y0, x1 - x0, y1 - y0)
                             for x0, y0, x1, y1 in client_layout.RECTS["hunt"])  # fmt: skip
        lab.sheets = qa_export.Sheets(directory=spec.sprites)
        tl = lab.timeline
        lab.timeline = Timeline(tl.events, tl.maps, snapshot_every=32, die_ms=tl.die_ms,
                                default_die_ms=tl.default_die_ms)  # fmt: skip
        occ.cache_compose()
        olf._speed_up()
        events = lab.timeline.events
        starts = spot_starts(events) if sid == spec.staged else []
        if spots is not None and sid != spec.staged:
            raise SystemExit(f"{sid}: spots exist only in the staged session {spec.staged}")
        tm = client_layout.load_templates(layout_templates)

        def check(bgr: npt.NDArray[np.uint8]) -> bool:
            state = client_layout.read(np.ascontiguousarray(bgr[:, :, 2::-1]), tm)
            return bool(client_layout.matches(state, "hunt"))

        changes = sorted(int(e["t_mono_ns"]) for e in events if e.get("type") == "map_change")
        return cls(path, spec, spots, lab, png_index(path, manifest), sid, check, starts,
                   inventory_spans(events, starts) if starts else [], changes)  # fmt: skip

    @property
    def name(self) -> str:
        if self.spots is None:
            return self.sid
        return f"{self.sid}:spots={','.join(str(s) for s in sorted(self.spots))}"

    def layout_ok(self, bgr: npt.NDArray[np.uint8]) -> bool:
        return bool(self.layout(bgr))

    def facing_rule(self, rule: str) -> olf.FacingRule:
        """fix 2 + Amendment B (``engaged``), our character's id from the Timeline."""
        base = olf.FacingRule.for_events(rule, self.lab.timeline.events)
        events = self.lab.timeline.events
        aid = self.lab.timeline.frame_world(self.refs[-1].t_mono_ns).aid if self.refs else None
        fights = any(e.get("type") in ("act", "attack_request") for e in events)
        if aid is None and fights:
            raise SystemExit(f"{self.sid}: our character's id is unknown (Amendment B needs it)")
        times = engagement_times(events, int(aid)) if aid is not None else {}  # no fight: none
        return EngagedRule(base.rule, base.moves, base.classes, times)

    def scene(self, world: Any) -> Any:
        if world.self_pos is None or not world.map or map_key(world.map) != self.spec.name:
            return None
        return occ.scene_for(self.lab, world.map, world.self_pos)

    def spot(self, t: int) -> int | None:
        return spot_of(t, self.starts) if self.starts else None

    def candidate(self, ref: qa_export.JpegRef, offset_ms: float) -> str | None:
        """None when the frame is a candidate (4f's packet-side rules), else the reason."""
        t = ref.t_mono_ns
        tw = t - int(offset_ms * 1e6)
        if self.starts:
            k = self.spot(t)
            if k is None:
                return "before_first_spot"
            if self.spots is not None and k not in self.spots:
                return "other_spot"
            if in_windows(t, self.inventory) or in_windows(tw, self.inventory):
                return "inventory_window"
        if in_windows(t, self.lab.windows):
            return "gm_window"
        if recent(self.map_changes, t, MAP_CHANGE_NS):
            return "map_change"
        tl = self.lab.timeline
        first, last = tl.frame_world(tw - STILL_BACK_NS), tl.frame_world(t)
        if not first.map or map_key(first.map) != self.spec.name or not last.map or \
                map_key(last.map) != self.spec.name:  # fmt: skip
            return "other_map"
        if first.self_pos is None or first.self_pos != last.self_pos:
            return "self_moving"
        pts = [tl.frame_world(x).self_pos for x in still_times(tw, t)[1:-1]]
        if not same_place([first.self_pos, *pts, last.self_pos]):
            return "self_moving"
        return None

    def candidates_at(self, offset_ms: float) -> list[qa_export.JpegRef]:
        out = []
        self.dropped = Counter()
        for ref in self.refs:
            why = self.candidate(ref, offset_ms)
            if why is None:
                out.append(ref)
            else:
                self.dropped[why] += 1
        return out


def refuse(sess: RecSession, role: str) -> None:
    spec = sess.spec
    if role == "fit" and not inside_role(sess.sid, sess.spots, spec.fit):
        raise SystemExit(f"{sess.name}: not a FIT part (payf07-detector.md 3b): refused")
    if role == "not_test" and overlaps_role(sess.sid, sess.spots, spec.test):
        raise SystemExit(f"{sess.name}: shares frames with TEST (3b): refused")


def occluders(spec: MapSpec) -> olf.Occluders:
    return olf.Occluders(spec.rsw, spec.models, spec.cells)


# --- 4b: 1d on FIT ----------------------------------------------------------------------------


def _offset_frame(ref: qa_export.JpegRef) -> tuple[list[tuple[int, int, dict[int, float]]], str]:
    sess, occl = olf._JOB["sess"], olf._JOB["occluders"]
    found = olf.walker_samples(sess, ref.t_mono_ns, list(COARSE_MS), occl)
    if not found:
        return [], "no_walker"
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return [], "ui_layout_mismatch"
    out = []
    for gid, by in found.items():
        errs = {}
        for ms, (e, pred) in by.items():
            bo = occ.best_offset(bgr, sess.lab.sheets(e.job), pred, olf.SEARCH_PX)
            if bo is not None:
                errs[ms] = float(np.hypot(bo[1], bo[2]))
        out.append((ref.frame_id, gid, errs))
    return out, "sampled"


def _offset_fine(job: tuple[qa_export.JpegRef, list[int]]) -> list[tuple[int, dict[int, float]]]:
    ref, gids = job
    sess, occl = olf._JOB["sess"], olf._JOB["occluders"]
    bgr = read_png(ref)
    out: dict[int, dict[int, float]] = defaultdict(dict)
    for ms in olf._JOB["fine"]:
        found = olf.walkers_at(sess, ref.t_mono_ns, ms, occl)
        for gid in gids:
            got = found.get(gid)
            if got is None or got[1] is None:
                continue
            bo = occ.best_offset(bgr, sess.lab.sheets(got[0].job), got[1], olf.SEARCH_PX)
            if bo is not None:
                out[gid][ms] = float(np.hypot(bo[1], bo[2]))
    return list(out.items())


def cmd_offset(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    occl = occluders(spec)
    errs: dict[int, list[float]] = defaultdict(list)
    per_part: dict[str, Any] = {}
    samples: list[tuple[RecSession, qa_export.JpegRef, int, dict[int, float]]] = []
    sessions = [RecSession.open(p, spec, a.layout_templates) for p in a.parts]
    for sess in sessions:  # --diagnostic: any non-TEST part, never frozen (9b)
        refuse(sess, "not_test" if a.diagnostic else "fit")
    for sess in sessions:  # the coarse sweep: still from the sweep's edge (1,000 ms) to t
        refs = sess.candidates_at(SWEEP_MAX_MS)
        olf._JOB.update(sess=sess, occluders=occl, walkers=spec.walkers, reader=read_png)
        why: Counter[str] = Counter()
        n = 0
        ref_of = {r.frame_id: r for r in refs}
        for rows, w in olf.run_parallel(_offset_frame, refs, a.workers):
            why[w] += 1
            for fid, gid, by in rows:
                n += 1
                samples.append((sess, ref_of[fid], gid, by))
                for ms, v in by.items():
                    errs[ms].append(v)
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sorted(sess.dropped.items())),
                               "frames_by_outcome": dict(why), "samples": n}  # fmt: skip
    curve = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None
             for ms in COARSE_MS}  # fmt: skip
    best_coarse = olf.pick_offset(curve)
    result: dict[str, Any] = {
        "what": "4b: 1d, the packet -> frame offset on the recorder path (RDP bus, 1 fps PNG)",
        "map": spec.name, "parts": [s.name for s in sessions], "measured_at": olf.now_ict(),
        "commit": olf.git_head(), "walkers": list(spec.walkers), "samples": len(samples),
        "sweep_ms": [COARSE_MS[0], COARSE_MS[-1]], "amendment": "A (2026-10-24 18:35:20 ICT)",
        "diagnostic": bool(a.diagnostic),
        "per_part": per_part, "curve_coarse_median_px": {str(k): v for k, v in curve.items()},
        "curve_coarse_n": {str(k): len(errs[k]) for k in COARSE_MS},
        "best_coarse_ms": best_coarse,
    }  # fmt: skip
    stop = None
    if len(samples) < MIN_WALKER_SAMPLES:
        stop = f"{len(samples)} walker samples < {MIN_WALKER_SAMPLES}"
    elif best_coarse is None or best_coarse in (COARSE_MS[0], COARSE_MS[-1]):
        stop = f"the best coarse offset {best_coarse} is at the sweep's edge"
    if stop is not None:
        result.update({"STOP": stop, "offset_ms": None})
        return result
    fine = [ms for ms in sweep_fine(best_coarse) if ms not in COARSE_MS]
    by_sess: dict[int, list[tuple[qa_export.JpegRef, int]]] = defaultdict(list)
    for sess, ref, gid, _by in samples:
        by_sess[id(sess)].append((ref, gid))
    for sess in sessions:
        jobs: dict[int, tuple[qa_export.JpegRef, list[int]]] = {}
        for ref, gid in by_sess.get(id(sess), []):
            jobs.setdefault(ref.frame_id, (ref, []))[1].append(gid)
        olf._JOB.update(sess=sess, occluders=occl, walkers=spec.walkers, fine=fine)
        for rows in olf.run_parallel(_offset_fine, list(jobs.values()), a.workers):
            for _gid, by in rows:
                for ms, v in by.items():
                    errs[ms].append(v)
    full = {ms: round(statistics.median(errs[ms]), 3) if errs[ms] else None
            for ms in sorted(set(COARSE_MS) | set(fine))}  # fmt: skip
    best = olf.pick_offset({ms: full[ms] for ms in sweep_fine(best_coarse)})
    species: Counter[str] = Counter()
    for sess, ref, gid, _by in samples:
        ent = next((e for e in sess.lab.timeline.frame_world(ref.t_mono_ns).entities
                    if e.gid == gid), None)  # fmt: skip
        species[str(ent.job if ent is not None else "?")] += 1
    result.update({
        "curve_median_px": {str(k): v for k, v in full.items()},
        "curve_n": {str(k): len(errs[k]) for k in full},
        "curve_p25_p75_px": {str(k): [round(float(np.percentile(errs[k], 25)), 2),
                                      round(float(np.percentile(errs[k], 75)), 2)]
                             for k in full if errs[k]},
        "samples_by_species": dict(sorted(species.items())),
        "units": len({(id(s), g) for s, _r, g, _b in samples}),
        "offset_ms": best, "occluders": occl.provenance(),
    })  # fmt: skip
    return result


# --- 4e: T_h on FIT (and 4c's reported anchors) ------------------------------------------------


def labeler_for(sess: RecSession, params: dict[str, Any], occl: olf.Occluders,
                occlusion: str, fit_all: bool = False) -> olf.FixLabeler:  # fmt: skip
    fl = olf.FixLabeler(sess.lab, params, occl, rule="fix2", occlusion=occlusion,
                        fit_all=fit_all, map_name=sess.spec.name)  # fmt: skip
    fl.facing = sess.facing_rule("fix2")  # Amendment B
    return fl


def _fates_frame(ref: qa_export.JpegRef) -> tuple[list[dict[str, Any]], str]:
    sess: RecSession = olf._JOB["sess"]
    fl: olf.FixLabeler = olf._JOB["labeler"]
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return [], "ui_layout_mismatch"
    ff = fl.frame(ref.t_mono_ns, bgr)
    if ff is None or not ff.applies:
        return [], "no_scene"
    rows = [{"frame_id": ref.frame_id, "gid": f.gid, "mob": f.mob, "under": f.under,
             "pre": f.pre, "fail": f.fail, "ncc": None if f.fit is None else round(f.fit[0], 4),
             "dx": None if f.fit is None else f.fit[1], "dy": None if f.fit is None else f.fit[2]}
            for f in ff.fates]  # fmt: skip
    return rows, "labelled"


def provisional(offset: dict[str, Any], spec: MapSpec) -> dict[str, Any]:
    return {"offset_ms": float(offset["offset_ms"]), "anchors_px": {},
            "fit_px": {str(m): spec.fit_px for m in spec.species}, "tau": olf.TAU}  # fmt: skip


def cmd_threshold(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    if (a.offset is None) == (a.proposed_offset_ms is None):
        raise SystemExit("one of --offset (a measured 1d) or --proposed-offset-ms (9b)")
    if a.offset is not None:
        offset = json.loads(a.offset.read_text())
        if offset.get("offset_ms") is None or offset.get("diagnostic"):
            raise SystemExit("1d stopped (or a diagnostic): no offset to measure T_h at")
    else:
        offset = {"offset_ms": float(a.proposed_offset_ms), "proposal": a.proposal}
    params = provisional(offset, spec)
    occl = occluders(spec)
    sessions = [RecSession.open(p, spec, a.layout_templates) for p in a.parts]
    for sess in sessions:
        refuse(sess, "fit")
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    for sess in sessions:
        refs = sess.candidates_at(params["offset_ms"])
        olf._JOB.update(sess=sess, labeler=labeler_for(sess, params, occl, "1c", fit_all=True))
        why: Counter[str] = Counter()
        n0 = len(rows)
        for r, w in olf.run_parallel(_fates_frame, refs, a.workers):
            why[w] += 1
            rows += [{**x, "part": sess.name} for x in r]
        per_part[sess.name] = {"frames": len(sess.refs), "candidates": len(refs),
                               "dropped": dict(sorted(sess.dropped.items())),
                               "frames_by_outcome": dict(why), "fates": len(rows) - n0}  # fmt: skip
    mine = [r for r in rows if r["mob"] in spec.species]
    clear = [r["ncc"] for r in mine if not r["under"] and r["pre"] is None and r["fail"] is None]
    under = [r["ncc"] for r in mine if r["under"] and r["pre"] is None and r["fail"] is None]
    if not clear:
        raise SystemExit("4e: no clear kept label on FIT")
    t_h = percentile(clear, T_H_PERCENTILE)

    def dist(v: Sequence[float]) -> dict[str, Any]:
        return {"n": len(v), **({f"p{q}": percentile(v, q) for q in (5, 25, 50, 75, 95)}
                                if v else {})}  # fmt: skip

    per_species = {}
    for m in spec.species:
        rs = [r for r in mine if r["mob"] == m]
        per_species[str(m)] = {
            "fates": len(rs),
            "clear_kept": dist([r["ncc"] for r in rs if not r["under"] and r["pre"] is None
                                and r["fail"] is None]),
            "under_fit_passes": dist([r["ncc"] for r in rs if r["under"] and r["pre"] is None
                                      and r["fail"] is None]),
            "under_share": round(sum(r["under"] for r in rs) / len(rs), 4) if rs else None,
            "excluded_pre": dict(Counter(str(r["pre"]) for r in rs if r["pre"] is not None)),
            "fails": dict(Counter(f"{'under' if r['under'] else 'clear'}:{r['fail']}"
                                  for r in rs if r["fail"] is not None and r["pre"] is None)),
            # 4c: the median fit offset of clear kept labels (REPORTED; no anchor is applied)
            "fit_offset_median_px": [statistics.median(r["dx"] for r in rs if r["dx"] is not None
                                                       and not r["under"] and r["fail"] is None
                                                       and r["pre"] is None)
                                     if any(r["dx"] is not None and not r["under"] and
                                            r["fail"] is None and r["pre"] is None for r in rs)
                                     else None,
                                     statistics.median(r["dy"] for r in rs if r["dy"] is not None
                                                       and not r["under"] and r["fail"] is None
                                                       and r["pre"] is None)
                                     if any(r["dy"] is not None and not r["under"] and
                                            r["fail"] is None and r["pre"] is None for r in rs)
                                     else None],
        }  # fmt: skip
    return {
        "what": "4e: o3h's T_h = the pooled p5 of the fit NCC of FIT's kept labels CLEAR of every "
                "model box (fix 2, 2b / 2c, the fit at +-6 px, tau, not at the edge)",
        "map": spec.name, "parts": [s.name for s in sessions], "measured_at": olf.now_ict(),
        "commit": olf.git_head(), "offset_ms": params["offset_ms"], "o3h_tau": t_h,
        "offset_source": offset.get("proposal") or str(a.offset),
        "clear_kept": dist(clear), "under_fit_passes": dist(under),
        "under_below_t_h": sum(1 for v in under if v < t_h), "per_species": per_species,
        "per_part": per_part, "other_species_fates": len(rows) - len(mine),
    }  # fmt: skip


def cmd_freeze(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    th = json.loads(a.threshold.read_text())
    if a.proposed or a.decision:  # 10a: 1d stopped; a proposed offset (NOT frozen), or the
        if a.offset is not None or "offset_source" not in th:  # decision that adopts it
            raise SystemExit("--proposed / --decision take a T_h measured at a proposed offset")
        off = {"offset_ms": th["offset_ms"], "parts": [th["offset_source"]]}
        if a.decision:
            status = "FROZEN"
            off_file: dict[str, Any] = {"offset_file": None, "offset_sha256": None,
                                        "decision": a.decision}  # fmt: skip
        else:
            status = f"PROPOSED_NOT_FROZEN: {th['offset_source']}"
            off_file = {"offset_file": None, "offset_sha256": None}
    else:
        off = json.loads(a.offset.read_text())
        if off.get("offset_ms") is None or off.get("diagnostic") or \
                float(th["offset_ms"]) != float(off["offset_ms"]):  # fmt: skip
            raise SystemExit("T_h must be measured at 1d's frozen offset")
        status = "FROZEN"
        off_file = {"offset_file": str(a.offset), "offset_sha256": olf.sha256_file(a.offset)}
    occl = occluders(spec)
    return {
        "labels": LABELS, "status": status, "plan": "docs/planning/payf07-detector.md 4",
        "map": spec.name,
        "map_cells": list(spec.cells), "frozen_at": olf.now_ict(), "commit": olf.git_head(),
        "measured_on": off["parts"], "offset_ms": float(off["offset_ms"]), "anchors_px": {},
        "fit_px": {str(m): spec.fit_px for m in spec.species}, "tau": olf.TAU, "k": olf.K,
        "search_px": olf.SEARCH_PX, "o3h_tau": float(th["o3h_tau"]), "facing_rule": "fix2",
        "occlusion": "o3h", "occluders": occl.provenance(),
        **off_file,
        "threshold_file": str(a.threshold), "threshold_sha256": olf.sha256_file(a.threshold),
    }  # fmt: skip


def load_params(path: Path, spec: MapSpec) -> dict[str, Any]:
    p = json.loads(path.read_text())
    if p.get("labels") != LABELS or p.get("map") != spec.name:
        raise SystemExit(f"{path}: not a {LABELS} parameter file for {spec.name}")
    return p


def frozen_occluders(params: dict[str, Any], spec: MapSpec) -> olf.Occluders:
    occl = occluders(spec)
    prov = occl.provenance()
    if prov["rsw_sha256"] != params["occluders"]["rsw_sha256"] or \
            occl.files != params["occluders"]["model_files_sha256"]:  # fmt: skip
        raise SystemExit("the RSW / RSM files differ from the frozen ones")
    return occl


# --- 5: the check (C1 / C2 on the PREDICTION) -------------------------------------------------


def cmd_check(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    params = load_params(a.params, spec)
    if params.get("status") != "FROZEN":
        raise SystemExit(f"{a.params}: {params.get('status')}: T1 runs on FROZEN parameters only")
    occl = frozen_occluders(params, spec)
    off_ms = float(params["offset_ms"])
    rows: list[dict[str, Any]] = []
    per_part: dict[str, Any] = {}
    dropped_all: Counter[str] = Counter()
    for part in a.parts:
        sess = RecSession.open(part, spec, a.layout_templates)
        if overlaps_role(sess.sid, sess.spots, spec.fit) and not a.allow_fit:
            raise SystemExit(f"{sess.name}: a FIT part (the parameters' own data): --allow-fit")
        refs = sess.candidates_at(off_ms)
        olf._JOB.update(sess=sess, occluders=occl, offset_ms=off_ms, anchors={},
                        facing_rule=sess.facing_rule("fix2"), occlusion="o3h",
                        tau=float(params["tau"]), o3h_tau=float(params["o3h_tau"]),
                        fit_px={int(k): int(v) for k, v in params["fit_px"].items()},
                        reader=read_png)  # fmt: skip
        prow: list[dict[str, Any]] = []
        dropped: Counter[str] = Counter()
        for r, d, _sn in olf.run_parallel(olf._check_rows, refs, a.workers):
            prow += [{**x, "part": sess.name} for x in r]
            dropped.update(d)
        prow.sort(key=lambda r: (r["frame_id"], r["gid"]))
        summ = t1_summary(prow, spec.species)
        per_part[sess.name] = {
            "frames": len(sess.refs), "candidates": len(refs),
            "candidate_drops": dict(sorted(sess.dropped.items())),
            "dropped": {k: v for k, v in sorted(dropped.items()) if ":" not in k},
            "c1": summ["c1"]["pooled"], "c1_ratio": summ["c1"]["ratio"],
            "c1_per_species": summ["c1"]["per_species"], "c2": summ["c2"]["per_species"],
            "own_c1": own_c1_verdict(summ),
        }  # fmt: skip
        rows += prow
        dropped_all.update(dropped)
    summ = t1_summary(rows, spec.species)

    def by_species(reason: str) -> dict[str, int]:
        return dict(sorted((k.split(":", 1)[1], v) for k, v in dropped_all.items()
                           if k.startswith(f"{reason}:")))  # fmt: skip

    if a.rows is not None:
        a.rows.write_text(json.dumps(rows) + "\n")
    motion = Counter(bool(r.get("self_moving")) for r in rows)
    return {
        "what": "5: C1 / C2 on the payf07-o3h PREDICTION (fix 2 facing, 1d, no anchor, no fit), "
                "o3h's under-box rule, 2b / 2c",
        "map": spec.name, "parts": a.parts, "checked_at": olf.now_ict(),
        "commit": olf.git_head(), "params": str(a.params),
        "params_sha256": olf.sha256_file(a.params), "offset_ms": off_ms,
        "o3h_tau": params["o3h_tau"], "tau": olf.TAU, "k": olf.K,
        **summ,
        "dropped": {k: v for k, v in sorted(dropped_all.items()) if ":" not in k},
        "occluded_model_by_species": by_species("occluded_model"),
        "under_model_kept_by_species": by_species("under_model_kept"),
        "next_move_by_species": by_species(olf.NEXT_MOVE),
        "ambiguous_view_by_species": by_species(olf.AMBIGUOUS),
        "engaged_by_species": by_species(ENGAGED),
        "facing_agreement": olf.agreement(rows),
        "self_moving_rows": motion.get(True, 0),
        "per_part": per_part,
    }  # fmt: skip


# --- the labels (no pixels in the output) -----------------------------------------------------


def _label_frame(ref: qa_export.JpegRef) -> dict[str, Any]:
    sess: RecSession = olf._JOB["sess"]
    fl: olf.FixLabeler = olf._JOB["labeler"]
    classes: Sequence[int] = olf._JOB["classes"]
    row: dict[str, Any] = {
        "frame_id": ref.frame_id,
        "t": ref.t_mono_ns,
        "shard": ref.shard.name,
        "offset": ref.offset,
        "size": ref.size,
        "spot": sess.spot(ref.t_mono_ns),
    }
    bgr = read_png(ref)
    if not sess.layout_ok(bgr):
        return {**row, "excluded_frame": ["ui_layout_mismatch"], "whole": False}
    ff = fl.frame(ref.t_mono_ns, bgr)
    if ff is None or not ff.applies:
        return {**row, "excluded_frame": ["no_scene"], "whole": False}
    tw = ref.t_mono_ns - fl.offset_ns
    world = sess.lab.timeline.frame_world(tw)
    scene = sess.scene(world)
    frame_ex = frame_exclusions(world, scene, sess.lab.size, sess.spec.species, classes,
                                world.aid)  # fmt: skip
    under = {f.gid: f.under for f in ff.fates}
    kept = [{"gid": k.gid, "mob": k.mob, "box": [round(v, 1) for v in k.box],
             "ncc": k.ncc, "dx": k.dx, "dy": k.dy, "motion": k.motion, "heading": k.heading,
             "facing_from": k.facing_from, "state": k.state, "under": under.get(k.gid)}
            for k in ff.kept]  # fmt: skip
    return {**row, "kept": kept, "excluded": [list(x) for x in ff.excluded],
            "hidden": ff.hidden, "excluded_frame": frame_ex,
            "whole": not ff.excluded and not frame_ex}  # fmt: skip


def count_labels(frames: Sequence[dict[str, Any]], species: Sequence[int],
                 drop_species: Sequence[int] = ()) -> dict[str, Any]:  # fmt: skip
    """Per species: kept labels in any frame / in frames kept WHOLE; exclusions by reason; the
    whole frames. ``drop_species``: species that are NOT classes (7: Green Plant's fallback), so a
    frame where one is kept or excluded is not whole either (``unchecked_species``)."""
    kept: Counter[int] = Counter()
    whole_lab: Counter[int] = Counter()
    excl: dict[int, Counter[str]] = defaultdict(Counter)
    frame_ex: Counter[str] = Counter()
    whole = 0
    labelled = 0
    for f in frames:
        if "kept" not in f:
            frame_ex.update(f.get("excluded_frame", []))
            continue
        labelled += 1
        mobs = [k["mob"] for k in f["kept"]] + [x[1] for x in f["excluded"]]
        dropped = bool(set(mobs) & set(drop_species))
        is_whole = f["whole"] and not dropped
        for k in f["kept"]:
            kept[k["mob"]] += 1
            if is_whole:
                whole_lab[k["mob"]] += 1
        for _g, mob, why in f["excluded"]:
            excl[mob][why] += 1
        frame_ex.update(f["excluded_frame"])
        if dropped:
            frame_ex["unchecked_species:dropped_class"] += 1
        whole += is_whole
    return {
        "frames_labelled": labelled, "frames_whole": whole,
        "frame_exclusions": dict(sorted(frame_ex.items())),
        "per_species": {str(m): {"kept": kept[m], "kept_in_whole_frames": whole_lab[m],
                                 "excluded": dict(sorted(excl[m].items()))}
                        for m in sorted(set(species) | set(kept) | set(excl))},
        "kept_total": sum(kept[m] for m in species),
        "kept_in_whole_frames_total": sum(whole_lab[m] for m in species),
    }  # fmt: skip


def cmd_labels(a: argparse.Namespace) -> dict[str, Any]:
    spec = MAPS[a.map]
    params = load_params(a.params, spec)
    occl = frozen_occluders(params, spec)
    sess = RecSession.open(a.parts[0], spec, a.layout_templates)
    refuse(sess, "not_test")
    classes = json.loads(a.classes.read_text())["monsters"]
    refs = sess.candidates_at(float(params["offset_ms"]))
    olf._JOB.update(sess=sess, labeler=labeler_for(sess, params, occl, "o3h"), classes=classes)
    frames = olf.run_parallel(_label_frame, refs, a.workers)
    gp = 1080
    out = {
        "what": f"the {LABELS} labels (no pixels): kept fitted boxes per candidate frame",
        "labels": LABELS, "params_status": params.get("status"), "map": spec.name,
        "part": sess.name, "session": sess.sid,
        "labelled_at": olf.now_ict(), "commit": olf.git_head(), "params": str(a.params),
        "params_sha256": olf.sha256_file(a.params), "frames_recorded": len(sess.refs),
        "candidates": len(refs), "candidate_drops": dict(sorted(sess.dropped.items())),
        "counts_green_plant_class": count_labels(frames, spec.species),
        "counts_green_plant_not_class": count_labels(frames, [m for m in spec.species if m != gp],
                                                     drop_species=[gp]),
        "frames": frames,
    }  # fmt: skip
    return out


# --- 6: the T2 pack ---------------------------------------------------------------------------


REFERENCE_PRT = (1002, 1082, 1063, 1008, 1113, 1018)  # Poring, White Plant + prt_fild08's others


def cmd_pack(a: argparse.Namespace) -> dict[str, Any]:
    import orc_label_sheets as ols

    spec = MAPS[a.map]
    instr = a.instructions.read_bytes()
    sha = hashlib.sha256(instr).hexdigest()
    if sha != a.instructions_sha256:
        raise SystemExit(f"{a.instructions}: sha256 {sha}, not the pre-registered one")
    pool: dict[int, list[dict[str, Any]]] = defaultdict(list)
    sources = []
    params_sha = set()
    statuses: set[str] = set()
    for path in a.labels:
        doc = json.loads(path.read_text())
        if doc.get("labels") != LABELS:
            raise SystemExit(f"{path}: not {LABELS} labels")
        if overlaps_role(doc["session"], parse_part(doc["part"])[1], spec.test):
            raise SystemExit(f"{doc['part']}: TEST is not in T2's pool")
        params_sha.add(doc["params_sha256"])
        statuses.add(str(doc.get("params_status")))
        sources.append({"part": doc["part"], "file": str(path), "sha256": olf.sha256_file(path)})
        root = Path(a.session_root)
        for f in doc["frames"]:
            for k in f.get("kept", []):
                pool[int(k["mob"])].append({
                    "session": doc["session"], "frame_id": f["frame_id"], "gid": k["gid"],
                    "mob": k["mob"], "box": k["box"], "ncc": k["ncc"], "under": k["under"],
                    "state": k["state"], "spot": f.get("spot"), "t": f["t"],
                    "ref": (str(root / doc["session"] / f["shard"]), f["offset"], f["size"]),
                })  # fmt: skip
    if len(params_sha) != 1:
        raise SystemExit(f"the labels come from {len(params_sha)} parameter files")
    tier = [m for m in spec.species if m != 1080 or len(pool.get(1080, [])) >= T2_PER_SPECIES]
    chosen: list[dict[str, Any]] = []
    per = {}
    for mob in tier:
        pick = t2_order(pool.get(mob, []), a.seed, mob)[:T2_PER_SPECIES]
        per[str(mob)] = {"pool": len(pool.get(mob, [])), "sampled": len(pick)}
        chosen += pick
    random.Random(f"{T2_SALT}:{a.seed}:order").shuffle(chosen)
    pack, key_dir = a.pack_dir, a.key_dir
    if pack.resolve() == key_dir.resolve() or key_dir.resolve().is_relative_to(pack.resolve()):
        raise SystemExit("the key must live outside the pack")
    (pack / "crops").mkdir(parents=True, exist_ok=True)
    key_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[tuple[str, int, int], npt.NDArray[np.uint8]] = {}
    for it in sorted(chosen, key=lambda x: x["ref"]):
        r = it["ref"]
        if r not in frames:
            frames[r] = read_png(qa_export.JpegRef(it["frame_id"], it["t"], Path(r[0]), r[1],
                                                   r[2]))[:, :, ::-1]  # fmt: skip
    size = (1280, 720)
    key_crops, names, enlarged = {}, [], []
    for i, it in enumerate(chosen, 1):
        x0, y0, x1, y1 = ols.crop_box(it["box"], size)
        img = ols.draw_box(frames[it["ref"]][y0:y1, x0:x1], it["box"], (x0, y0))
        big = ols.enlarge(img)
        num = f"{i:03d}"
        ols.save_png(pack / "crops" / f"{num}.png", big)
        enlarged.append((num, big))
        names.append(f"{num}.png")
        key_crops[num] = {k: it[k] for k in ("mob", "session", "frame_id", "gid", "box", "ncc",
                                             "under", "state", "spot")}  # fmt: skip
    use_kb(spec)
    sheets = qa_export.Sheets(directory=spec.sprites)
    ref_mobs = list(spec.species) + list(REFERENCE_PRT)
    ref_mobs = ref_mobs[:12] if len(ref_mobs) > 12 else ref_mobs
    letters = ols.letters_for(ref_mobs, a.seed)
    ols.save_png(
        pack / "reference.png",
        ols.reference_sheet({m: sheets(m) for m in ref_mobs}, letters, views="multi"),
    )
    grids = []
    for page, idx in enumerate(ols.grid_pages(len(enlarged)), 1):
        gname = f"grids/grid_{page:02d}.png"
        ols.save_png(pack / gname, ols.blind_grid([enlarged[i] for i in idx]))
        grids.append(gname)
    (pack / "pack.json").write_text(json.dumps({
        "crops": names, "grids": grids, "reference": "reference.png", "letters": sorted(letters),
        "box": "the green rectangle drawn just outside the label box",
        "questions": ols.QUESTIONS}, indent=1) + "\n")  # fmt: skip
    shutil.copyfile(a.instructions, pack / "instructions.txt")
    key = {"labels": LABELS, "seed": a.seed, "per_species_target": T2_PER_SPECIES,
           "letters": letters, "crops": key_crops, "tier_species": tier,
           "per_species": per, "sources": sources, "params_sha256": params_sha.pop(),
           "params_status": sorted(statuses),
           "instructions_sha256": sha, "built_at": olf.now_ict(), "commit": olf.git_head(),
           "note": "THE ANSWER KEY: never give it (or this directory) to a blind labeller",
           }  # fmt: skip
    (key_dir / "answer_key.json").write_text(json.dumps(key, indent=1) + "\n")
    return {"pack": str(pack), "key": str(key_dir / "answer_key.json"), "crops": len(names),
            "per_species": per, "tier_species": tier, "letters": len(letters),
            "params_status": key["params_status"],
            "grids": len(grids)}  # fmt: skip


# --- CLI --------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    layout = Path("/home/batt/docker/poring-lab/data/ui_anchors/layout")

    def common(p: argparse.ArgumentParser, parts: bool = True) -> None:
        p.add_argument("--map", default="pay_fild07", choices=sorted(MAPS))
        if parts:
            p.add_argument("parts", nargs="+")
            p.add_argument("--workers", type=int, default=1)
            p.add_argument("--layout-templates", type=Path, default=layout)
        p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("offset")
    common(p)
    p.add_argument("--diagnostic", action="store_true",
                   help="9b: any non-TEST part; reported, never frozen")  # fmt: skip
    p = sub.add_parser("threshold")
    common(p)
    p.add_argument("--offset", type=Path, default=None)
    p.add_argument("--proposed-offset-ms", type=float, default=None)
    p.add_argument("--proposal", default=None, help="the proposal's name (9b)")
    p = sub.add_parser("freeze")
    common(p, parts=False)
    p.add_argument("--offset", type=Path, default=None)
    p.add_argument("--threshold", type=Path, required=True)
    p.add_argument("--proposed", action="store_true",
                   help="10a: write the proposal's parameters, NOT frozen")  # fmt: skip
    p.add_argument("--decision", default=None,
                   help="10a: FREEZE the proposed offset (cite the amendment)")  # fmt: skip
    p = sub.add_parser("check")
    common(p)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--rows", type=Path, default=None)
    p.add_argument("--allow-fit", action="store_true", help="report C1 on FIT (not T1)")
    p = sub.add_parser("labels")
    common(p)
    p.add_argument("--params", type=Path, required=True)
    p.add_argument("--classes", type=Path, default=ROOT / "config/detector/classes-v2orc.json")
    p = sub.add_parser("pack")
    p.add_argument("--map", default="pay_fild07", choices=sorted(MAPS))
    p.add_argument("labels", nargs="+", type=Path)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--pack-dir", type=Path, required=True)
    p.add_argument("--key-dir", type=Path, required=True)
    p.add_argument("--instructions", type=Path, required=True)
    p.add_argument("--instructions-sha256", required=True)
    p.add_argument("--session-root", default="/mnt/poring-lab-datasets")
    p.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "labels" and len(a.parts) != 1:
        raise SystemExit("labels: one PART per run")
    run = {"offset": cmd_offset, "threshold": cmd_threshold, "freeze": cmd_freeze,
           "check": cmd_check, "labels": cmd_labels, "pack": cmd_pack}  # fmt: skip
    out = run[a.cmd](a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    brief = {k: v for k, v in out.items() if k != "frames"}
    print(json.dumps(brief, indent=1)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
