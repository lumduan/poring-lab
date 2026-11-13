#!/usr/bin/env python3
"""The scorer of minimap_id (dungeon@9.46): recorded frames, read by the SAME read_map /
map_verdict the check and the runner use, against the true map from the session's own packets.

    minimap_id.py eval SPEC.json [--expect MAP] [--refs NPZ] [--out JSON]

SPEC: a JSON list of sessions (NAS names under /mnt/poring-lab-datasets, or absolute paths):
  {"kind": "shards", "path": S, "per_shard": N, "shards": [i, ...]}  -- the recorder's PNG shards:
      N frames spread over each listed shard (tar members are seeked, never extracted to disk);
  {"kind": "frames", "path": S}  -- a demo's frames/<name>-<t_mono_ns>.png;
  {"kind": "files", "path": S, "names": [...], "label": MAP}  -- named pictures of a known map
      (a hunt's strike-*.jpg, a session's end.png).
The TRUE map is the packets' last map_change (the validation account) before the frame's
t_mono_ns: offline ground truth only (CLAUDE.md rule 1 -- it never reaches the reader). A frame
less than LOAD_BEFORE_S before or LOAD_AFTER_S after a map change is not labelled (the load).

Everything is read in place, read-only, paced; nothing is written but the --out rows (no frame,
no crop). The rows carry session names, scores and words only.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import tarfile
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

NAS = Path("/mnt/poring-lab-datasets")
LOAD_BEFORE_S, LOAD_AFTER_S = 2.0, 5.0  # the load screen: ~1-3 s on the lab
PACE_S = 0.05  # between two frames read from the NAS


def map_changes(sess: Path) -> list[tuple[int, str]]:
    """The session's map changes (t_mono_ns, map), the validation account's, in time order."""
    p = sess / "packets.jsonl.gz"
    out: list[tuple[int, str]] = []
    if not p.exists():
        return out
    with gzip.open(p, "rt") as f:
        for line in f:
            if '"map_change"' not in line:
                continue
            d = json.loads(line)
            if d.get("type") == "map_change" and d.get("validation_account", True):
                out.append((int(d["t_mono_ns"]), str(d["map"]).removesuffix(".gat")))
    return sorted(out)


def true_map(changes: list[tuple[int, str]], t_ns: int) -> str | None:
    """PURE: the map at ``t_ns`` (None: before any change, or inside a load's window)."""
    lab = None
    for t, m in changes:
        dt = (t_ns - t) / 1e9
        if -LOAD_BEFORE_S < dt < LOAD_AFTER_S:
            return None
        if t <= t_ns:
            lab = m
    return lab


def _bgr(data: bytes) -> np.ndarray | None:
    from PIL import Image

    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    if a.shape[:2] == (900, 1440):
        a = a[77:797, 80:1360]
    if a.shape[:2] != (720, 1280):
        return None
    return np.ascontiguousarray(a[..., ::-1])


def frames(item: dict[str, Any]) -> Iterator[tuple[str, str | None, np.ndarray]]:
    """(source, true map, BGR frame) for one SPEC item."""
    raw = str(item["path"])
    sess = Path(raw) if raw.startswith("/") else NAS / raw
    kind = item["kind"]
    if kind == "files":
        for n in item["names"]:
            p = sess / n
            if p.exists():
                img = _bgr(p.read_bytes())
                if img is not None:
                    yield f"{sess.name}/{n}", item.get("label"), img
        return
    ch = map_changes(sess)
    if kind == "frames":
        for p in sorted((sess / "frames").glob("*.png")):
            m = re.search(r"-(\d{12,})\.png$", p.name)
            img = _bgr(p.read_bytes())
            if img is not None:
                yield f"{sess.name}/frames/{p.name}", (true_map(ch, int(m.group(1))) if m
                                                       else None), img  # fmt: skip
            time.sleep(PACE_S)
        return
    tars = sorted(p for p in sess.iterdir() if p.name.startswith("shard-"))
    pick = item.get("shards")
    for i in range(len(tars)) if pick is None else [i for i in pick if i < len(tars)]:
        with tarfile.open(tars[i]) as t:
            mem = t.getmembers()
            pngs = [m for m in mem if m.name.endswith(".png")]
            metas = {m.name[:-5]: m for m in mem if m.name.endswith(".json")}
            n = int(item.get("per_shard", 2))
            idx = sorted(set(np.linspace(0, len(pngs) - 1, n + 2)[1:-1].astype(int).tolist()))
            for j in idx if pngs else []:
                m = pngs[j]
                mf = t.extractfile(metas[m.name[:-4]])
                pf = t.extractfile(m)
                if mf is None or pf is None:
                    continue
                meta = json.loads(mf.read())
                img = _bgr(pf.read())
                if img is not None:
                    yield (f"{sess.name}/{tars[i].name}/{m.name}",
                           true_map(ch, int(meta["t_mono_ns"])), img)  # fmt: skip
                time.sleep(PACE_S)


def table(rows: list[dict[str, Any]]) -> str:
    """PURE: the confusion table (true map x map read, "?" = cannot tell) as text."""
    cols = sorted({str(r["read"] or "?") for r in rows}, key=lambda c: (c == "?", c))
    trues = sorted({str(r["true"]) for r in rows})
    cnt = Counter((str(r["true"]), str(r["read"] or "?")) for r in rows)
    w = max([len(c) for c in cols + trues] + [5])
    lines = ["true \\ read".ljust(w + 2) + " ".join(c.rjust(w) for c in cols)]
    for t in trues:
        lines.append(t.ljust(w + 2) + " ".join(str(cnt[(t, c)] or ".").rjust(w) for c in cols))
    return "\n".join(lines)


def run(spec_path: Path, refs: Any, expect: str, out: Path | None) -> int:
    import minimap_id as mi

    spec = json.loads(spec_path.read_text())
    rows: list[dict[str, Any]] = []
    t0 = time.time()
    for item in spec:
        try:
            for src, lab, img in frames(item):
                rd = mi.read_map(img, refs)
                ok, words = mi.map_verdict(rd, expect, refs)
                rows.append({"src": src, "true": lab, "read": rd.map, "names": list(rd.names[:6]),
                             "score": round(rd.score, 4), "next": round(rd.next_score, 4),
                             "next_names": list(rd.next_names[:3]), "why": rd.why,
                             "expect": expect, "ok": ok, "words": words})  # fmt: skip
        except (OSError, tarfile.TarError, ValueError, KeyError) as e:
            print(f"skipped {item.get('path')}: {e!r}"[:200], flush=True)
    lab = [r for r in rows if r["true"] is not None]
    print(f"{len(rows)} frames, {len(lab)} labelled ({time.time() - t0:.0f} s)")
    print(table(lab))
    named_ok = sum(1 for r in lab if r["read"] is not None and r["true"] in r["names"])
    wrong = [r for r in lab if r["read"] is not None and r["true"] not in r["names"]]
    print(f"named right {named_ok}, named WRONG {len(wrong)}, cannot tell "
          f"{sum(1 for r in lab if r['read'] is None)}")  # fmt: skip
    vt = Counter((r["true"] == expect, r["ok"]) for r in lab)
    print(f"expect {expect}: on {expect} frames tick {vt[(True, True)]} / cross "
          f"{vt[(True, False)]} / ? {vt[(True, None)]}; on other maps tick "
          f"{vt[(False, True)]} / cross {vt[(False, False)]} / ? {vt[(False, None)]}")  # fmt: skip
    for r in wrong[:20]:
        print("WRONG", r["src"], r["true"], "->", r["read"], r["score"], r["next"])
    if out is not None:
        out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return 0
