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
* --sheet: also an offline contact sheet with the boxes drawn (for reports), e.g. in /dev/shm.
"""

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from poring_dataset import mapcache  # noqa: E402
from poring_dataset.camera import projector_for  # noqa: E402
from poring_dataset.labels import gm_windows, in_windows, labels_for  # noqa: E402
from poring_dataset.projection import camera_file  # noqa: E402
from poring_dataset.shards import encode_png, read_shard  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("session", type=Path)
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--offset-ms", default="auto")
    ap.add_argument("--sheet", type=Path)
    a = ap.parse_args()
    manifest = json.loads((a.session / "manifest.json").read_text())
    camera_path = camera_file(manifest["backend"])
    if not camera_path.exists():
        backend = manifest["backend"]
        raise SystemExit(f"no calibrated camera for {backend}: run "
                         f"scripts/calibrate_projection.py --backend {backend} --save")  # fmt: skip
    camera = json.loads(camera_path.read_text())
    projectors: dict[str | None, tuple[Any, str]] = {}  # per map: camera + GAT, or homography
    offset_run = None
    if a.offset_ms == "auto":
        offset_ms, offset_run = auto_offset_ms(manifest["config"])
    else:
        offset_ms = float(a.offset_ms)
    with gzip.open(a.session / "packets.jsonl.gz", "rt") as fh:
        events = [json.loads(line) for line in fh]
    timeline = Timeline(events, mapcache.load(prere=True))
    windows = gm_windows(events)
    size = (manifest["game_region"][2], manifest["game_region"][3])
    out_dir = BUNDLES / manifest["session_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_out: list[dict[str, Any]] = []
    sheet: list[np.ndarray] = []
    n = 0
    for shard in manifest["shards"]:
        for meta, img in read_shard(a.session / shard):
            n += 1
            if (n - 1) % a.every or len(frames_out) >= a.max:
                continue
            t = int(meta["t_mono_ns"])
            if in_windows(t, windows):
                continue
            world = timeline.frame_world(t - int(offset_ms * 1e6))
            if world.map not in projectors:
                projectors[world.map] = projector_for(camera, world.map)
            projector, _ = projectors[world.map]
            boxes = [
                {"x1": b.x0, "y1": b.y0, "x2": b.x1, "y2": b.y1, "cls": b.cls, "gid": b.gid}
                for b in labels_for(world, projector, size)
            ]
            name = f"{meta['frame_id']:09d}.png"
            (out_dir / name).write_bytes(encode_png(img))
            frames_out.append({"file": name, "frame_id": meta["frame_id"], "t_mono_ns": t,
                               "boxes": boxes})  # fmt: skip
            if a.sheet and len(sheet) < 12:
                sheet.append(draw(img, boxes))
    (out_dir / "labels.json").write_text(json.dumps({
        "session": manifest["session_id"], "size": list(size), "offset_ms": offset_ms,
        "offset_run": offset_run, "camera": camera_path.name,
        "projection": sorted({which for _, which in projectors.values()}),
        "frames": frames_out,
    }))  # fmt: skip
    index_path = BUNDLES / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"sessions": []}
    index["sessions"] = [s for s in index["sessions"] if s["id"] != manifest["session_id"]]
    index["sessions"].append({"id": manifest["session_id"],
                              "title": f"{manifest['session_id']} ({manifest['backend']})",
                              "frames": len(frames_out)})  # fmt: skip
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
                      "offset_ms": offset_ms, "offset_run": offset_run}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
