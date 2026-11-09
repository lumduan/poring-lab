#!/usr/bin/env python3
"""Export a recorded session's frames + auto-labels for the console's /qa page (Phase 2, B5).

    qa_export.py SESSION_DIR [--every 5] [--max 40] [--offset-ms auto|MS] [--sheet OUT.png]

* Labels: Timeline(packets) at (frame time - the backend's packet->frame offset), projected with the
  session backend's calibrated default camera (poring_dataset/camera_<backend>.json), per-class v0
  boxes; frames inside a GM-command window are skipped.
* Offset `auto`: the newest benchmark run (by its start time, never its file name) of the SAME
  backend and the same client + paint path as the session (docs/benchmarks/*.json, outdoor
  packet_to_frame p50): an S2 session (bus) never takes V3's X-painted number. A frame shows the
  world as it was that long ago.
* Bundle: services/frontend/.qa-local/<session>/ (gitignored, .dockerignore'd, dev route only) --
  frames as lossless PNG + labels.json; index.json lists the sessions.
* --mark-gold SESSION_ID (alone): mark that exported session as the gold set; /qa opens on it.
* --sheet: also an offline contact sheet with the boxes drawn (for reports), e.g. in /dev/shm.
* Any format: PNG shards, an H.264 session (Batt 2026-10-04: the console default) read through
  poring_dataset.h264 -- evenly spread frames, freeze spans excluded, each frame verified against
  the live decode -- or an RDP video session (ADR-0024: the rdp default; poring_dataset.frames,
  every ``--every``-th frame as for PNG). The bundle itself is always PNG, so /qa does not change.
* Indoor maps (Post-S2 round B1): the camera rotated by the client's own rule (camera.py); the
  client's indoorrswtable.txt must be extracted into the GAT dir, else the export refuses (fail
  closed: an outdoor camera on an indoor map gave the invalid 2026-10-04 indoor labels). Hidden NPC
  classes and warp portals are not labelled; each box carries its sprite `facing`.
* A session marked INVALID (dataset_ship.py mark-invalid: the manifest's "validity") is refused
  unless --allow-invalid.
* WARP-AND-WATCH sessions (scripts/warp_watch.py, 2026-10-21): ``frames/shard-NNNNNN.tar`` with
  ``<frame>.jpg`` + ``<frame>.json`` members (JPEG q80, 5 Hz) and a manifest of their own (sid,
  t0_ns / t1_ns, backend, size, ui_layout, rec_hz). The labels take the game-region size from the
  manifest, the UI rectangles of the RECORDED layout (client_layout.RECTS[ui_layout], not the
  frozen standard set: the hunting layout uncovers rows the standard one hides), and, with no
  recording config, the packet->frame offset labels_v2's demo sessions use for their backend
  (rdp: xfreerdp's newest benchmark run). An unknown or missing layout fails closed.
* HUMAN DEMONSTRATIONS (scripts/human_demo.py, 2026-10-16; orcsdun01-detector.md 3f): the frames
  are JPEG FILES ``<k>-<t_mono_ns>.jpg`` (the capture time; the same ro_agent.Screen grab as
  warp_watch, 5 Hz q80) in the manifest's ``frames_dir`` (the NAS's human-demos/<sid>/frames), the
  packets beside the manifest. A demo records no UI layout: it is labelled in
  ``HUMAN_DEMO_LAYOUT``'s rectangles, and a frame is usable only where the pixels say it shows
  that layout (``layout_check``: client_layout.read). Its game-region size is its first frame's.
"""

import argparse
import gzip
import io
import json
import sys
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from poring_dataset import frames as recorded  # noqa: E402
from poring_dataset import mapcache  # noqa: E402
from poring_dataset.camera import load_indoor_table, map_camera, projector_for  # noqa: E402
from poring_dataset.labels import gm_windows, in_windows, labels_for, labels_for_v1  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.render import K_NOSTALRO, SpriteSheet, load_scene  # noqa: E402
from poring_dataset.shards import encode_png  # noqa: E402
from poring_dataset.sprites import parse_act, parse_spr  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402
from poring_dataset.ui_layout import UI_RECTS  # noqa: E402

# v1 (M5): the decoded monster sprites (sprite_catalog.py --decode-mixcrypt; RAM, study only) and
# the KB's job table (kb_build.py). Both are local, never committed.
SPRITE_DIR = Path("/dev/shm/poring-lab-tmp/sprites/data/sprite/몬스터")  # sprite_catalog.py --work
KB_CLASSES = ROOT / "data" / "kb" / "classes.json"
# The CLIENT's sprite stem per monster id (scripts/npc_sprites.py mob-names, from jobname.lub;
# local, never committed). For 1011, 1051, 1053 and 1184 it is NOT rAthena's aegis name
# (labels-v2-plan 7.6): an aegis lookup finds no files there, and the label falls back to v0's
# 44 x 40 box.
KB_SPRITE_NAMES = ROOT / "data" / "kb" / "monster_sprite_names.json"


def job_aegis() -> dict[int, str]:
    """job id -> aegis name, over every map in the KB's class table."""
    table = json.loads(KB_CLASSES.read_text())
    return {int(job): row["aegis"] for rows in table.values() for job, row in rows.items()}


def sprite_stems(path: Path | None = None) -> dict[int, str | None]:
    """job id -> the client's sprite stem (lower case), from KB_SPRITE_NAMES; None for a species the
    table lists without a client name. {} when the table is absent (the aegis name decides)."""
    p = KB_SPRITE_NAMES if path is None else path
    if not p.exists():
        return {}
    doc = json.loads(p.read_text())
    rows = doc.get("mobs", doc) if isinstance(doc, dict) else {}
    out: dict[int, str | None] = {}
    for job, row in rows.items():
        stem = row.get("stem") if isinstance(row, dict) else None
        out[int(job)] = str(stem).lower() if stem else None
    return out


class Sheets:
    """job -> the species' OPAQUE SpriteSheet (None: no name or no decoded SPR / ACT).

    The file stem: the CLIENT's own name (``stems``, KB_SPRITE_NAMES) when that table lists the
    species, else the aegis name (``aegis``, classes.json). A species with neither, a table row
    without a client name, or a stem whose files are not decoded gets None -- never a guessed file
    -- and is recorded in ``missing`` (job -> reason) so a report says which species keep v0's box.
    """

    def __init__(self, directory: Path = SPRITE_DIR, *, stems: dict[int, str | None] | None = None,
                 aegis: dict[int, str] | None = None) -> None:  # fmt: skip
        self.directory = directory
        self.aegis = job_aegis() if aegis is None else aegis
        self.stems = sprite_stems() if stems is None else stems
        self.cache: dict[int, SpriteSheet | None] = {}
        self.missing: dict[int, str] = {}

    def stem(self, job: int) -> tuple[str | None, str]:
        """(the file stem, where it came from: client_table | aegis), or (None, why not)."""
        if job in self.stems:
            s = self.stems[job]
            return (s, "client_table") if s else (None, "no_client_name")
        if job in self.aegis:
            return self.aegis[job].lower(), "aegis"
        return None, "no_name"

    def __call__(self, job: int | None) -> SpriteSheet | None:
        if job is None:
            return None
        if job not in self.cache:
            name, source = self.stem(job)
            sheet = None
            if name is None:
                self.missing[job] = source
            else:
                act, spr = self.directory / f"{name}.act", self.directory / f"{name}.spr"
                if act.exists() and spr.exists():
                    sheet = SpriteSheet(parse_act(act.read_bytes()), parse_spr(spr.read_bytes()))
                else:
                    self.missing[job] = f"no_files:{source}"
            self.cache[job] = sheet
        return self.cache[job]


# --- warp-and-watch sessions (scripts/warp_watch.py) ---------------------------------------------

# the manifest keys scripts/warp_watch.py writes (a recorded session has session_id / game_region /
# shards or format instead)
WARP_WATCH_KEYS = ("sid", "t0_ns", "t1_ns", "backend", "size", "rec_hz")
UiRects = tuple[tuple[int, int, int, int], ...]  # (x, y, w, h), poring_dataset.ui_layout's form


def is_warp_watch(manifest: dict[str, Any]) -> bool:
    """A warp_watch.py session's manifest (JPEG tar shards under frames/)."""
    return all(k in manifest for k in WARP_WATCH_KEYS)


# --- human demonstrations (scripts/human_demo.py) -------------------------------------------------

HUMAN_DEMO_LAYOUT = "hunt"  # the layout Batt plays in (verified per frame: layout_check)


def is_human_demo(manifest: dict[str, Any]) -> bool:
    """A human_demo.py session's manifest: its frames are JPEG files in ``frames_dir``."""
    return (manifest.get("kind") == "demo" and bool(manifest.get("frames_dir"))
            and str(manifest.get("actor") or "").startswith("human:"))  # fmt: skip


def file_refs(frames_dir: Path) -> list["JpegRef"]:
    """Every ``<k>-<t_mono_ns>.jpg`` of ONE frames directory (a listing, never a walk) as a JpegRef
    over the whole file (offset 0), in recording order."""
    out = []
    for p in frames_dir.glob("*.jpg"):
        k, sep, t = p.stem.partition("-")
        if not sep or not k.isdigit() or not t.isdigit():
            raise SystemExit(f"{p}: not a <k>-<t_mono_ns>.jpg frame")
        out.append(JpegRef(int(k), int(t), p, 0, p.stat().st_size))
    return sorted(out, key=lambda r: r.frame_id)


def frame_refs(session: Path, manifest: dict[str, Any]) -> list["JpegRef"]:
    """A JPEG session's frames, either kind: warp_watch's tar shards or a human demo's files."""
    if is_warp_watch(manifest):
        return jpeg_index(session, manifest)
    if is_human_demo(manifest):
        return file_refs(Path(manifest["frames_dir"]))
    raise SystemExit(f"{session_id(manifest)}: neither a warp_watch session nor a human demo")


def layout_check(manifest: dict[str, Any], templates: Path | None = None) -> Any:
    """None when the session records its layout (nothing to check per frame); for a human demo, a
    function BGR frame -> True when client_layout.read (pixels) says it shows HUMAN_DEMO_LAYOUT.
    Fail closed: no templates, no check -> SystemExit."""
    if not is_human_demo(manifest):
        return None
    import client_layout

    root = templates if templates is not None else client_layout.TEMPLATES
    if not root.exists():
        raise SystemExit(f"{root}: the layout templates are not here (a human demo's frames are "
                         "usable only where their layout is read from pixels)")  # fmt: skip
    tm = client_layout.load_templates(root)
    import chat_window  # the recorded frames show the chat window of their date

    chat = chat_window.for_sid(session_id(manifest))

    def check(bgr: np.ndarray) -> bool:
        state = client_layout.read(np.ascontiguousarray(bgr[:, :, 2::-1]), tm, chat=chat)
        return bool(client_layout.matches(state, HUMAN_DEMO_LAYOUT))

    return check


def session_id(manifest: dict[str, Any]) -> str:
    return str(manifest.get("session_id") or manifest.get("sid"))


def ui_rects_for(manifest: dict[str, Any]) -> UiRects:
    """The client's static UI windows of the session, (x, y, w, h): a warp_watch session's RECORDED
    layout (client_layout.RECTS, x0 y0 x1 y1 there); a human demo's HUMAN_DEMO_LAYOUT (checked per
    frame: layout_check); any other session the frozen standard set (ui_layout.UI_RECTS,
    unchanged). FAIL CLOSED: a warp_watch manifest without a known layout."""
    if is_human_demo(manifest):
        import client_layout

        return tuple((x0, y0, x1 - x0, y1 - y0)
                     for x0, y0, x1, y1 in client_layout.RECTS[HUMAN_DEMO_LAYOUT])  # fmt: skip
    if not is_warp_watch(manifest):
        return UI_RECTS
    import client_layout

    name = manifest.get("ui_layout")
    if name not in client_layout.RECTS:
        raise SystemExit(f"{session_id(manifest)}: ui_layout {name!r} is not one of "
                         f"{sorted(client_layout.RECTS)}: the UI rectangles are "
                         "unknown")  # fmt: skip
    return tuple((x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in client_layout.RECTS[name])


def recording_config(manifest: dict[str, Any]) -> dict[str, Any]:
    """What auto_offset_ms matches on: the recording's own config, else (a warp_watch session has
    none) labels_v2's demo rule for the backend (rdp -> xfreerdp)."""
    if manifest.get("config"):
        return dict(manifest["config"])
    backend = str(manifest.get("backend") or "rdp")
    return {"backend": backend, "client": {"name": "xfreerdp" if backend == "rdp" else None}}


@dataclass(frozen=True, slots=True)
class JpegRef:
    """One warp_watch frame: its meta and where its JPEG bytes lie in a tar shard."""

    frame_id: int
    t_mono_ns: int
    shard: Path
    offset: int
    size: int


def jpeg_shards(session: Path, manifest: dict[str, Any] | None = None) -> list[Path]:
    """The session's JPEG tar shards, in recording order (the recorder's own list when it wrote
    one, else frames/shard-*.tar sorted by name -- the recorder numbers them in order)."""
    rec = (manifest or {}).get("recorder") or {}
    if rec.get("shards"):
        return [session / "frames" / str(n) for n in rec["shards"]]
    return sorted((session / "frames").glob("shard-*.tar"))


def jpeg_index(session: Path, manifest: dict[str, Any] | None = None) -> list[JpegRef]:
    """Every frame of a warp_watch session (tar headers and the small json members only; no JPEG
    byte is read), in recording order (frame_id). The recorder rotates a shard between ANY two
    members, so a frame's jpg and json may lie in two shards: they are paired across shards. A
    json without its jpg (a cut shard) is skipped."""
    jpgs: dict[str, tuple[Path, int, int]] = {}
    metas: dict[str, dict[str, Any]] = {}
    for shard in jpeg_shards(session, manifest):
        with tarfile.open(shard) as tar:
            for m in tar:
                key, _, ext = m.name.partition(".")
                if ext == "jpg":
                    jpgs[key] = (shard, m.offset_data, m.size)
                elif ext == "json":
                    fh = tar.extractfile(m)
                    assert fh is not None
                    metas[key] = json.loads(fh.read())
    out = [JpegRef(int(metas[k]["frame_id"]), int(metas[k]["t_mono_ns"]), *jpgs[k])
           for k in set(jpgs) & set(metas)]  # fmt: skip
    return sorted(out, key=lambda r: r.frame_id)


def read_jpeg(ref: JpegRef) -> np.ndarray:
    """The frame as BGR (one seek and read of its JPEG bytes), like the PNG / H.264 readers."""
    from PIL import Image

    with ref.shard.open("rb") as fh:
        fh.seek(ref.offset)
        data = fh.read(ref.size)
    if len(data) != ref.size:
        raise ValueError(f"{ref.shard}@{ref.offset}: short read ({len(data)} of {ref.size} bytes)")
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    return np.ascontiguousarray(rgb[:, :, ::-1])


def jpeg_frames(
    session: Path, manifest: dict[str, Any], every: int = 1
) -> Iterator[tuple[dict[str, Any], np.ndarray]]:
    """Every ``every``-th frame of a warp_watch session as (meta{frame_id, t_mono_ns}, BGR)."""
    for i, ref in enumerate(jpeg_index(session, manifest)):
        if i % every:
            continue
        yield {"frame_id": ref.frame_id, "t_mono_ns": ref.t_mono_ns}, read_jpeg(ref)


BUNDLES = ROOT / "services" / "frontend" / ".qa-local"
COLOURS = {"player": (255, 200, 60), "monster": (60, 220, 255), "npc": (120, 255, 120)}  # BGR


def client_key(config: dict[str, Any]) -> tuple[str, str, str]:
    """(backend, client name, paint path) -- what decides when a frame shows the world."""
    client = config.get("client") or {}
    return (str(config.get("backend")), str(client.get("name")), str(client.get("paint") or "x11"))


def auto_offset_ms(config: dict[str, Any], runs_dir: Path | None = None) -> tuple[float, str]:
    """(packet->frame p50 of the newest matching run, its run_id)."""
    want = client_key(config)
    best: tuple[str, float, str] | None = None
    for path in (runs_dir or ROOT / "docs" / "benchmarks").glob("*.json"):
        res = json.loads(path.read_text())
        if "scenes" not in res or client_key(res.get("config", {})) != want:
            continue
        p50 = res["scenes"].get("outdoor", {}).get("packet_to_frame_ms", {}).get("p50")
        started = str(res.get("t_wall_start", ""))
        if isinstance(p50, int | float) and (best is None or started > best[0]):
            best = (started, float(p50), str(res.get("run_id", path.stem)))
    if best is None:
        raise SystemExit(f"no benchmark run for {want}: pass --offset-ms")
    return best[1], best[2]


def draw(img: np.ndarray, boxes: list[dict[str, Any]]) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    for b in boxes:
        x0, y0 = max(0, int(b["x1"])), max(0, int(b["y1"]))
        x1, y1 = min(w - 1, int(b["x2"])), min(h - 1, int(b["y2"]))
        colour = COLOURS.get(b["cls"], (255, 255, 255))
        for t in range(2):
            out[y0 + t, x0 : x1 + 1] = colour
            out[y1 - t, x0 : x1 + 1] = colour
            out[y0 : y1 + 1, x0 + t] = colour
            out[y0 : y1 + 1, x1 - t] = colour
    return out


class Labeler:
    """A session's auto-labels at any frame time (qa_export and label_iou.py share it)."""

    def __init__(self, session: Path, offset_ms: str = "auto", *, allow_invalid: bool = False,
                 labels: str = "v0", k: float = K_NOSTALRO):  # fmt: skip
        if labels not in ("v0", "v1"):
            raise SystemExit(f"unknown labels {labels!r}")
        self.labels, self.k = labels, k
        self.sheets = Sheets() if labels == "v1" else None
        self.manifest = json.loads((session / "manifest.json").read_text())
        self.ui_rects = ui_rects_for(self.manifest)  # the recorded layout's (warp_watch)
        validity = self.manifest.get("validity") or {}
        if validity.get("status") == "INVALID" and not allow_invalid:
            raise SystemExit(f"{session.name} is marked INVALID ({validity.get('reason')}): "
                             "--allow-invalid")  # fmt: skip
        self.camera_path = camera_file(self.manifest["backend"])
        if not self.camera_path.exists():
            be = self.manifest["backend"]
            raise SystemExit(f"no calibrated camera for {be}: run "
                             f"scripts/calibrate_projection.py --backend {be} --save")  # fmt: skip
        self.camera = json.loads(self.camera_path.read_text())
        self.indoor = load_indoor_table()  # fail closed: indoor maps need the client's table
        self.projectors: dict[str | None, tuple[Any, str, float | None]] = {}
        self.offset_run = None
        if offset_ms == "auto":
            self.offset_ms, self.offset_run = auto_offset_ms(recording_config(self.manifest))
        else:
            self.offset_ms = float(offset_ms)
        packets = session / "packets.jsonl.gz"
        states = session / "packets.states.jsonl.gz"  # v1: headings + effect states (M3 sidecar)
        with gzip.open(states if labels == "v1" and states.exists() else packets, "rt") as fh:
            events = [json.loads(line) for line in fh]
        self.timeline = Timeline(events, mapcache.load(prere=True))
        self.windows = gm_windows(events)
        if is_warp_watch(self.manifest):
            self.size = (int(self.manifest["size"][0]), int(self.manifest["size"][1]))
        elif is_human_demo(self.manifest):
            from PIL import Image

            first = file_refs(Path(self.manifest["frames_dir"]))
            if not first:
                raise SystemExit(f"{session.name}: no frame in {self.manifest['frames_dir']}")
            with Image.open(first[0].shard) as im:  # the header only
                self.size = (int(im.width), int(im.height))
        else:
            region = self.manifest["game_region"]
            self.size = (region[2], region[3])

    @classmethod
    def from_events(cls, events: list[dict[str, Any]], backend: str, size: tuple[int, int],
                    offset_ms: float, *, labels: str = "v1", k: float = K_NOSTALRO,
                    ui_rects: UiRects = UI_RECTS) -> "Labeler":  # fmt: skip
        """The same boxes for packets already in memory: a DEMO session has no recording manifest
        (demo_verify's attack branch, docs/demonstrations.md 3.3)."""
        self = cls.__new__(cls)
        self.labels, self.k = labels, k
        self.ui_rects = ui_rects
        self.sheets = Sheets() if labels == "v1" else None
        self.manifest = {"backend": backend}
        self.camera_path = camera_file(backend)
        if not self.camera_path.exists():
            raise SystemExit(f"no calibrated camera for {backend}")
        self.camera = json.loads(self.camera_path.read_text())
        self.indoor = load_indoor_table()
        self.projectors = {}
        self.offset_run, self.offset_ms = None, float(offset_ms)
        self.timeline = Timeline(events, mapcache.load(prere=True))
        self.windows = gm_windows(events)
        self.size = size
        return self

    def boxes(self, t: int) -> list[dict[str, Any]] | None:
        """The boxes of a frame captured at ``t`` (None inside a GM-command window)."""
        if in_windows(t, self.windows):
            return None
        world = self.timeline.frame_world(t - int(self.offset_ms * 1e6))
        if world.map not in self.projectors:
            projector, which = projector_for(self.camera, world.map, indoor_table=self.indoor)
            cam = map_camera(self.camera, world.map, self.indoor)
            self.projectors[world.map] = (projector, which, None if cam is None else cam.yaw)
        projector, _, yaw = self.projectors[world.map]
        if self.labels == "v1" and world.self_pos is not None and world.map is not None:
            tw = t - int(self.offset_ms * 1e6)
            scene = load_scene(self.camera, world.map, world.self_pos, indoor_table=self.indoor)
            assert self.sheets is not None
            boxes = labels_for_v1(world, projector, self.size, scene=scene,
                                  state=lambda gid: self.timeline.state(gid, tw),
                                  sheet=self.sheets, k=self.k, camera_yaw=yaw,
                                  ui_rects=self.ui_rects)  # fmt: skip
        else:
            boxes = labels_for(world, projector, self.size, camera_yaw=yaw, ui_rects=self.ui_rects)
        return [
            {"x1": b.x0, "y1": b.y0, "x2": b.x1, "y2": b.y1, "cls": b.cls, "gid": b.gid,
             "facing": b.facing, "kind": b.kind, "state": b.state, "phase_known": b.phase_known}
            for b in boxes
        ]  # fmt: skip


def session_frames(
    session: Path, manifest: dict[str, Any], *, every: int, limit: int
) -> Iterator[tuple[dict[str, Any], np.ndarray]]:
    """A session's frames as (meta{frame_id, t_mono_ns}, BGR GAME_REGION image), any format.
    PNG, or an RDP video (ADR-0024; poring_dataset.frames): every ``every``-th frame. H.264 (Batt
    2026-10-04: the console default): ``limit`` x 2 frames spread evenly over the session, freeze
    spans excluded, each GOP decoded once and every frame checked against the live decode
    (poring_dataset.h264) -- GM windows thin them later. warp_watch (JPEG shards): every
    ``every``-th frame."""
    if is_warp_watch(manifest):
        yield from jpeg_frames(session, manifest, every)
        return
    if (manifest.get("format") or "png") == "h264":
        from poring_dataset.h264 import H264Session

        stream = H264Session(session)
        yield from stream.frames(stream.sample(limit * 2))
        return
    yield from recorded.iter_bgr(session, manifest, every=every, strict=True)


def mark_gold(index_path: Path, session_id: str) -> None:
    """Mark ONE exported session as the gold set (/qa opens on it unless a link names another):
    the B6 hand-check was twice done on the wrong session, 2026-10-04 and 10-05."""
    index = json.loads(index_path.read_text())
    if not any(s["id"] == session_id for s in index["sessions"]):
        raise SystemExit(f"{session_id} is not exported (no entry in {index_path})")
    for s in index["sessions"]:
        s["gold"] = s["id"] == session_id
    index_path.write_text(json.dumps(index, indent=1))
    if json.loads(index_path.read_text()) != index:
        raise SystemExit("index read-back differs")


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--mark-gold":  # qa_export.py --mark-gold SESSION_ID
        mark_gold(BUNDLES / "index.json", sys.argv[2])
        print(f"gold set: {sys.argv[2]}")
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--offset-ms", default="auto")
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--allow-invalid", action="store_true")
    a = ap.parse_args()
    lab = Labeler(a.session, a.offset_ms, allow_invalid=a.allow_invalid)
    manifest, size = lab.manifest, lab.size
    out_dir = BUNDLES / session_id(manifest)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_out: list[dict[str, Any]] = []
    sheet: list[np.ndarray] = []
    for meta, img in session_frames(a.session, manifest, every=a.every, limit=a.max):
        if len(frames_out) >= a.max:
            break
        t = int(meta["t_mono_ns"])
        boxes = lab.boxes(t)
        if boxes is None:
            continue
        name = f"{meta['frame_id']:09d}.png"
        (out_dir / name).write_bytes(encode_png(img))
        frames_out.append({"file": name, "frame_id": meta["frame_id"], "t_mono_ns": t,
                           "boxes": boxes})  # fmt: skip
        if a.sheet and len(sheet) < 12:
            sheet.append(draw(img, boxes))
    (out_dir / "labels.json").write_text(json.dumps({
        "session": session_id(manifest), "size": list(size), "offset_ms": lab.offset_ms,
        "offset_run": lab.offset_run, "camera": lab.camera_path.name,
        "projection": sorted({which for _, which, _ in lab.projectors.values()}),
        "frames": frames_out,
    }))  # fmt: skip
    index_path = BUNDLES / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"sessions": []}
    sid = session_id(manifest)
    was_gold = any(s.get("gold") for s in index["sessions"] if s["id"] == sid)
    index["sessions"] = [s for s in index["sessions"] if s["id"] != sid]
    index["sessions"].append({"id": sid, "title": f"{sid} ({manifest['backend']})",
                              "frames": len(frames_out), "gold": was_gold})  # fmt: skip
    index_path.write_text(json.dumps(index, indent=1))
    if a.sheet and sheet:
        cols = 3
        blank = np.zeros_like(sheet[0])
        rows = []
        for i in range(0, len(sheet), cols):
            row = sheet[i : i + cols]
            rows.append(np.hstack(row + [blank] * (cols - len(row))))
        a.sheet.write_bytes(encode_png(np.vstack(rows)))
    labelled = sum(1 for f in frames_out if f["boxes"])
    print(json.dumps({"bundle": str(out_dir), "frames": len(frames_out), "with_boxes": labelled,
                      "offset_ms": lab.offset_ms, "offset_run": lab.offset_run}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
