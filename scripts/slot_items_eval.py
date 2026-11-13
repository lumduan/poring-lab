#!/usr/bin/env python3
"""The scorer of slot_items (dungeon@9.47; docs/planning/player-mode.md "The items on the keys"):
recorded sessions' hotbars, every slot read by the SAME read_slot the check and the runner use.

    slot_items.py eval SESSION... [--shards first,last] [--refs NPZ] [--out JSON]

SESSION: a recorder session's name under /mnt/poring-lab-datasets (or an absolute path): its PNG
shards are read in place, read-only (tar members are seeked, never extracted to disk), EVERY frame
of the listed shards ("first", "last", "mid" or an index), so consecutive frames are 1 s apart.

THE LABELS: a recording keeps one hotbar layout (the runner never moves an item between keys), so
each slot's TRUE item is the item its reads name in at least LABEL_MIN frames (a slot whose reads
never name an item has none: an empty slot, or a skill). A person confirms each recording's layout
from an enlarged strip (the --strips folder) BEFORE the scores count: a layout item that is not
what the strip shows makes every read of that slot wrong. An "empty" read on a labelled slot is a
used-up stack or worn equipment, not an error.

THE SCORES:
  - the confusion, true item -> read (the item, "empty", "unread" -- cannot tell -- or ANOTHER
    item: the danger);
  - the skill / never-item slots: what their reads named (an item there is the danger too);
  - the START windows: WINDOW consecutive frames (WINDOW s at the recorder's 1 fps; a live start
    reads ~4 frames a second for PLAYER_SLOT_S) inside one shard; a window DECIDES when every
    labelled slot has an item or "empty" read in it (read_slots_until's rule). An undecided window
    is a MAP CHANGE when one of its frames has at least MAP_CHANGE_MIN of the nine slots unread
    (the client dims the screen, then draws its load screen: no hotbar at all).
Nothing is written but the --out rows (no frame, no crop) and the --strips pictures (client
pixels: scratch only, /dev/shm, never committed).
"""

from __future__ import annotations

import io
import json
import tarfile
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

NAS = Path("/mnt/poring-lab-datasets")
ROWS = 40  # the hotbar's rows of the game region (its counts end at row 33)
COLS = 520  # ... and its nine slots' columns (slot 8's count ends at column 504)
LABEL_MIN = 3  # a slot's true item: named in at least this many frames of the recording
WINDOW = 3  # a start window: this many consecutive frames (1 s apart)
MAP_CHANGE_MIN = 7  # an undecided window with a frame this many slots unread: a map change
PACE_S = 0.02  # between two frames read from the NAS


def _bgr_strip(data: bytes) -> np.ndarray | None:
    """A recorded PNG (RGB, the 1280 x 720 game region) as the runner's BGR hotbar strip."""
    from PIL import Image

    a = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    if a.shape[:2] != (720, 1280):
        return None
    return np.ascontiguousarray(a[:ROWS, :COLS, ::-1])


def strips(session: str, shards: Sequence[str]) -> Iterator[tuple[dict[str, Any], np.ndarray]]:
    """Every frame's hotbar strip of the listed shards, in order: ({session, shard, member})."""
    sess = Path(session) if session.startswith("/") else NAS / session
    names = json.loads((sess / "manifest.json").read_text())["shards"]
    pick: list[int] = []
    for s in shards:
        i = {"first": 0, "last": len(names) - 1, "mid": len(names) // 2}.get(s)
        pick.append(int(s) if i is None else i)
    for i in sorted(set(pick)):
        with tarfile.open(sess / names[i], "r:") as tf:
            for m in tf.getmembers():
                if not m.name.endswith(".png"):
                    continue
                fh = tf.extractfile(m)
                strip = None if fh is None else _bgr_strip(fh.read())
                if strip is not None:
                    yield {"session": sess.name, "shard": i, "member": m.name}, strip
                time.sleep(PACE_S)


def frame_of(strip: np.ndarray) -> np.ndarray:
    """PURE: a hotbar strip as a game-region frame (the rows below it black)."""
    f = np.zeros((ROWS, 1280, 3), np.uint8)
    f[:, : strip.shape[1]] = strip
    return f


def labels(metas: Sequence[dict[str, Any]], reads: Sequence[dict[int, Any]]) -> dict[Any, str]:
    """PURE: (session, slot) -> the item its reads name in at least LABEL_MIN frames (the most
    named one)."""
    named: dict[tuple[str, int], Counter[str]] = {}
    for m, rd in zip(metas, reads, strict=True):
        for s, r in rd.items():
            if r.state == "item":
                named.setdefault((m["session"], s), Counter())[str(r.name)] += 1
    return {k: c.most_common(1)[0][0] for k, c in named.items() if c.most_common(1)[0][1]
            >= LABEL_MIN}  # fmt: skip


def outcome(read: Any, truth: str | None) -> str:
    """PURE: a read against the slot's true item: the item's name (right), "empty", "unread",
    or "WRONG <name>" (another item)."""
    if read.state != "item":
        return str(read.state)
    return str(read.name) if read.name == truth else f"WRONG {read.name}"


def score(metas: Sequence[dict[str, Any]], reads: Sequence[dict[int, Any]],
          lab: dict[Any, str]) -> dict[str, Any]:  # fmt: skip
    """PURE: the confusion, the never-item slots and the start windows (module docstring)."""
    conf: dict[str, Counter[str]] = {}
    other: Counter[str] = Counter()
    for m, rd in zip(metas, reads, strict=True):
        for s, r in rd.items():
            truth = lab.get((m["session"], s))
            if truth is None:
                other["WRONG " + str(r.name) if r.state == "item" else str(r.state)] += 1
            else:
                conf.setdefault(truth, Counter())[outcome(r, truth)] += 1
    win: Counter[str] = Counter()
    undecided: list[dict[str, Any]] = []
    for i in range(len(metas) - WINDOW + 1):
        seg = {(metas[j]["session"], metas[j]["shard"]) for j in range(i, i + WINDOW)}
        if len(seg) != 1:
            continue
        sess = metas[i]["session"]
        slots = [s for s in range(9) if (sess, s) in lab]
        ok = all(any(reads[j][s].state != "unread" for j in range(i, i + WINDOW)) for s in slots)
        if ok:
            win["decided"] += 1
            continue
        change = any(sum(reads[j][s].state == "unread" for s in range(9)) >= MAP_CHANGE_MIN
                     for j in range(i, i + WINDOW))  # fmt: skip
        win["map change" if change else "UNDECIDED"] += 1
        undecided.append({**metas[i], "map_change": change})
    wrong = sum(n for c in conf.values() for k, n in c.items() if k.startswith("WRONG"))
    wrong += sum(n for k, n in other.items() if k.startswith("WRONG"))
    return {"frames": len(metas), "confusion": {k: dict(v.most_common()) for k, v in
                                                 sorted(conf.items())},
            "never_item_slots": dict(other.most_common()), "windows": dict(win),
            "wrong": wrong, "undecided": undecided,
            "layouts": {f"{s} F{k + 1}": v for (s, k), v in sorted(lab.items())}}  # fmt: skip


def run(sessions: Sequence[str], shards: Sequence[str], refs: Any, out: Path | None,
        strips_dir: Path | None = None) -> int:  # fmt: skip
    import slot_items as si

    metas: list[dict[str, Any]] = []
    reads: list[dict[int, Any]] = []
    shown: set[str] = set()
    for sess in sessions:
        for meta, strip in strips(sess, shards):
            frame = frame_of(strip)
            metas.append(meta)
            reads.append({s: si.read_slot(frame, s, refs) for s in range(9)})
            if strips_dir is not None and meta["session"] not in shown and all(
                    r.state != "unread" for s, r in reads[-1].items() if s != 2):  # fmt: skip
                from PIL import Image

                strips_dir.mkdir(parents=True, exist_ok=True)
                big = Image.fromarray(strip[:, 230:, ::-1]).resize(
                    (870, 120), Image.Resampling.NEAREST
                )
                big.save(strips_dir / f"{meta['session']}.png")
                shown.add(meta["session"])
        print(json.dumps({"session": sess, "frames": len(metas)}), flush=True)
    lab = labels(metas, reads)
    got = score(metas, reads, lab)
    print(json.dumps({k: v for k, v in got.items() if k != "undecided"}, indent=1))
    print(json.dumps({"undecided": got["undecided"]}))
    if out is not None:
        rows = [{**m, **{f"F{s + 1}": r.record() for s, r in rd.items()}}
                for m, rd in zip(metas, reads, strict=True)]  # fmt: skip
        out.write_text(json.dumps({"summary": got, "rows": rows}))
    return 0
