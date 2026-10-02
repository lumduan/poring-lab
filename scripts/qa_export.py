#!/usr/bin/env python3
"""Export a recorded session's frames + auto-labels for the console's /qa page (Phase 2, B5).

    qa_export.py SESSION_DIR [--every 5] [--max 40] [--offset-ms auto|MS] [--sheet OUT.png]

* Labels: Timeline(packets) at (frame time - the backend's packet->frame offset), projected with the
  calibrated default camera (poring_dataset/camera_default.json), per-class v0 boxes; frames inside
  a GM-command window are skipped.
* Offset `auto`: the newest benchmark run of the session's backend (docs/benchmarks/*.json,
  outdoor packet_to_frame p50). A frame shows the world as it was that long ago.
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
from poring_dataset.labels import gm_windows, in_windows, labels_for  # noqa: E402
from poring_dataset.shards import encode_png, read_shard  # noqa: E402
from poring_dataset.timeline import Timeline  # noqa: E402

CAMERA = ROOT / "packages" / "poring_dataset" / "src" / "poring_dataset" / "camera_default.json"
BUNDLES = ROOT / "services" / "frontend" / ".qa-local"
COLOURS = {"player": (255, 200, 60), "monster": (60, 220, 255), "npc": (120, 255, 120)}  # BGR


def auto_offset_ms(backend: str) -> float:
    runs = sorted((ROOT / "docs" / "benchmarks").glob("*.json"))
    for path in reversed(runs):
        res = json.loads(path.read_text())
        if res.get("config", {}).get("backend") != backend:
            continue
        p50 = res["scenes"].get("outdoor", {}).get("packet_to_frame_ms", {}).get("p50")
        if isinstance(p50, int | float):
            return float(p50)
    raise SystemExit(f"no benchmark run for backend {backend}: pass --offset-ms")


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
    if not CAMERA.exists():
        raise SystemExit("no calibrated camera: run scripts/calibrate_projection.py --save first")
    camera = json.loads(CAMERA.read_text())
    h = np.array(camera["h"], dtype=float)
    offset_ms = auto_offset_ms(manifest["backend"]) if a.offset_ms == "auto" else float(a.offset_ms)
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
            boxes = [
                {"x1": b.x0, "y1": b.y0, "x2": b.x1, "y2": b.y1, "cls": b.cls, "gid": b.gid}
                for b in labels_for(world, h, size)
            ]
            name = f"{meta['frame_id']:09d}.png"
            (out_dir / name).write_bytes(encode_png(img))
            frames_out.append({"file": name, "frame_id": meta["frame_id"], "t_mono_ns": t,
                               "boxes": boxes})  # fmt: skip
            if a.sheet and len(sheet) < 12:
                sheet.append(draw(img, boxes))
    (out_dir / "labels.json").write_text(json.dumps({
        "session": manifest["session_id"], "size": list(size), "offset_ms": offset_ms,
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
                      "offset_ms": offset_ms}))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
