#!/usr/bin/env python3
"""Which ITEM a hotbar slot shows, read from its icon's PIXELS (dungeon@9.47; matpilot's review,
round 15 #1, 2026-11-13: the start check read only the stack COUNT under each role's key, so with
the Fly Wing's key set to F1 -- the White Potions' slot -- it said "10 Fly Wings on F1", Run stayed
enabled, and the runner's escape would have drunk a potion instead of flying).

    OMP_NUM_THREADS=2 slot_items.py build [--grf PATH] [--decode-mixcrypt] [--kb DIR] [--all]
                      [--out NPZ]              (~25 s)
    slot_items.py read IMAGE... [--slots 0 3 7] [--refs NPZ]
    slot_items.py eval SESSION... [--shards first,last] [--refs NPZ] [--out JSON] [--strips DIR]

What the screen offers (measured 2026-11-13 21:31 ICT on the live Rogue's 1-row hotbar, the
1280 x 720 game region): the client draws the item's OWN ICON, the archive's 24 x 24 item bitmap
(``data/texture/<the UI folder>/item/<resource name>.bmp``, the name through
``data/idnum2itemresnametable.txt``), 1:1 at ICON_ORIGIN + PITCH x slot, its magenta key colour
transparent over the slot's white face; the stack count's black digits are drawn over its lower
right (hotbar_count's count box). Equipment in the bag shows its icon too (the Knife on F4); worn
equipment is not drawn (an empty slot, bare_steal's readout).

How (numpy only; PURE but for the CLI):
  1. the slot's 24 x 24 square is cut from the frame (BGR, game-region pixels), colour kept: four
     potions share one bottle and differ only in colour;
  2. every reference picture (``build``: the archive's bitmap, composited the way the client draws
     it -- the key colour shows the white face) is compared by the MEAN ABSOLUTE COLOUR DIFFERENCE
     over the square, the count box and the frame's top line left out (COMPARE: the digits change
     with the stack, the line is the slot's own);
  3. the best picture is named when its distance is at most NAME_MAX and it beats every RIVAL
     (a picture within RIVAL_RANGE) on the pixels that tell the two apart, by a LEAD of at least
     PAIR_LEAD -- a White Potion and a Blue Potion differ only in the liquid, a Butterfly Wing and a
     Green Butterfly Wing only in its hue, so the whole-square distance alone cannot separate a
     covered White Potion from a Blue one; two pictures that differ on fewer than DISCRIM_MIN
     pixels are ONE picture (a copy group). Otherwise the read is "cannot tell"
     (a dark frame, the cursor or a window over the slot, a skill, an item not in the
     references);
  4. shows: a role's item is "right" only when its id is in the named picture's group; a different
     item named is "wrong" (dungeon_hunt: "F1 shows a White Potion, not a Fly Wing"); an empty slot
     (hotbar_count's rule, on the slot's white face) is "empty"; else "unknown" (cannot tell).

The references are CLIENT-derived: built at run time from the archive (read in place, read-only;
grf_read via map_identity.Archive), written to data/slot_items/ (gitignored), never committed
(CLAUDE.md rule 4). Encrypted bitmaps (MIXCRYPT: 4,275 of the Thai archive's 6,497 item bitmaps)
need ``--decode-mixcrypt``, the lab's host-local study decoder (grf_read; never in the repo).
The item set is the server's (the local KB's data/kb/items.json, built from the pinned rAthena;
its English names give the words); ``--all`` takes every id of the archive's table instead.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FORMAT = 1
REFS = ROOT / "data" / "slot_items" / "refs.npz"
GRF = Path("/mnt/poring-thai-src/ro_thai/data.grf")
KB = ROOT / "data" / "kb"
TABLE = "data/idnum2itemresnametable.txt"
ITEM_BMP = re.compile(r"^data/texture/[^/]+/item/([^/]+)\.bmp$")  # the UI folder's item icons
SIZE = 24  # the item bitmap's side, drawn 1:1
ICON_ORIGIN = (246, 4)  # slot 0's icon, game-region px (measured: White Potion, Knife, Fly Wing,
# Butterfly Wing, Candy -- each one px off reads >= 38 worse)
KEY_MIN, KEY_MAX = 240, 15  # the key colour: R and B at least KEY_MIN, G at most KEY_MAX
FACE = 255.0  # the slot's face behind a transparent pixel (white; measured 255 on empty slots)
DARK = 40.0  # a square darker than this on average shows no slot (a load screen, a teleport)
FACE_MIN = 250.0  # an EMPTY slot's face (below its top line) reads at least this grey on average:
# 9,138 empty reads of 2,076 recorded frames, 1 % at 254.0 or less; the load screens' flat pictures
# that hotbar_count reads "empty" (no digit, no dark icon pixel: all nine slots of 11 frames)
# 189.5-240.9
NAME_MAX = 20.0  # the best picture's distance at most this to be named ...
# ... and it must beat every RIVAL (a picture within RIVAL_RANGE of it) on the pixels that tell the
# two apart -- where their composited squares differ by more than DIFF_PX (a colour's mean) -- by
# a LEAD of at least PAIR_LEAD: (the read's difference from the rival - from the best) / the two
# pictures' own difference there; 1 = the read is the best picture, 0 = halfway, -1 = the rival.
# Two pictures that differ on fewer than DISCRIM_MIN pixels are ONE picture (a copy group: the
# same icon, e.g. a Knife and its slotted twin). Measured on the live hotbar 2026-11-13 21:31: the
# least lead of the White Potion 0.96 (over the four other potions), the Butterfly Wing 0.81 (over
# the Green Butterfly Wing: their pictures differ by 37 on 74 pixels), Knife 0.99, Fly Wing 0.95,
# Candy 0.92
RIVAL_RANGE = 30.0
DIFF_PX = 30.0
DISCRIM_MIN = 6
PAIR_LEAD = 0.5
TOP_K = 12  # the rival test looks at so many best pictures


def _compare_mask() -> np.ndarray:
    """PURE: the square's pixels that are compared -- not the count box (hotbar_count's digits,
    in square coordinates), not row 0 (the slot frame's top line, drawn under the icon)."""
    import hotbar_count as hb

    keep = np.ones((SIZE, SIZE), bool)
    ox, oy = ICON_ORIGIN
    keep[max(0, hb.Y0 - oy) : max(0, hb.Y1 - oy), max(0, hb.X0 - ox) : max(0, hb.X1 - ox)] = False
    keep[0, :] = False
    return keep


COMPARE = _compare_mask()


def transparent(rgb: Any) -> np.ndarray:
    """PURE: the key-colour pixels of an RGB bitmap (not drawn: the slot's face shows)."""
    a = np.asarray(rgb)[..., :3].astype(np.int16)
    return np.asarray((a[..., 0] >= KEY_MIN) & (a[..., 1] <= KEY_MAX) & (a[..., 2] >= KEY_MIN))


def fit_square(rgb: Any) -> np.ndarray | None:
    """PURE: an item bitmap as the SIZE x SIZE square the slot draws (RGB uint8), the key colour
    where it is smaller; None when it is larger (no such icon is drawn 1:1)."""
    a = np.asarray(rgb)[..., :3].astype(np.uint8)
    h, w = a.shape[:2]
    if h > SIZE or w > SIZE:
        return None
    out = np.zeros((SIZE, SIZE, 3), np.uint8)
    out[..., 0] = out[..., 2] = 255
    out[:h, :w] = a
    return out


def composite(rgb: Any) -> np.ndarray:
    """PURE: a SIZE x SIZE item bitmap as the slot shows it (RGB float32): the key colour is the
    slot's white face."""
    a = np.asarray(rgb, np.float32)[..., :3].copy()
    a[transparent(rgb)] = FACE
    return a


@dataclass(frozen=True)
class SlotRefs:
    """The reference pictures and the item ids that draw them."""

    rgb: np.ndarray  # (P, SIZE, SIZE, 3) uint8: the bitmap, key colour included
    ids: tuple[tuple[int, ...], ...]  # picture -> its item ids (sorted)
    names: Mapping[int, str]  # item id -> its English name (the KB's), for the words
    resnames: tuple[str, ...]  # picture -> the archive bitmap's resource name (logs)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        comp = np.stack([composite(p) for p in self.rgb]) if len(self.rgb) else np.zeros(
            (0, SIZE, SIZE, 3), np.float32)  # fmt: skip
        object.__setattr__(self, "_flat", comp[:, COMPARE, :].reshape(len(comp), -1))
        object.__setattr__(self, "_pic_of", {i: p for p, ids in enumerate(self.ids) for i in ids})

    @classmethod
    def from_icons(cls, icons: Mapping[int, Any], names: Mapping[int, str] | None = None,
                   resnames: Mapping[int, str] | None = None,
                   meta: Mapping[str, Any] | None = None) -> SlotRefs:  # fmt: skip
        """PURE: refs from {item id: its RGB bitmap}; identical squares are one picture (their ids
        merged); a bitmap larger than SIZE, or one with no drawn pixel, is left out."""
        seen: dict[bytes, int] = {}
        pics: list[np.ndarray] = []
        ids: list[list[int]] = []
        res: list[str] = []
        for iid in sorted(icons):
            sq = fit_square(icons[iid])
            if sq is None or transparent(sq).all():
                continue
            key = composite(sq).astype(np.uint8).tobytes()
            if key in seen:
                ids[seen[key]].append(int(iid))
                continue
            seen[key] = len(pics)
            pics.append(sq)
            ids.append([int(iid)])
            res.append((resnames or {}).get(iid, str(iid)))
        if not pics:
            raise ValueError("no usable reference picture")
        nm = {int(k): str(v) for k, v in (names or {}).items()}
        return cls(np.stack(pics), tuple(tuple(sorted(i)) for i in ids), nm, tuple(res),
                   dict(meta or {}))  # fmt: skip

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flat = [i for ids in self.ids for i in ids]
        np.savez_compressed(
            path, rgb=self.rgb, ids=np.array(flat, np.int32),
            counts=np.array([len(i) for i in self.ids], np.int32),
            resnames=np.array(self.resnames),
            name_ids=np.array(sorted(self.names), np.int32),
            name_text=np.array([self.names[i] for i in sorted(self.names)]),
            meta=np.array(json.dumps({**self.meta, "format": FORMAT})),
        )  # fmt: skip

    @classmethod
    def load(cls, path: Path = REFS) -> SlotRefs:
        z = np.load(path)
        meta = json.loads(str(z["meta"]))
        if meta.get("format") != FORMAT:
            raise ValueError(f"{path}: format {meta.get('format')}, want {FORMAT}: rebuild it")
        flat = [int(x) for x in z["ids"]]
        ids, at = [], 0
        for n in z["counts"]:
            ids.append(tuple(flat[at : at + int(n)]))
            at += int(n)
        names = {int(i): str(t) for i, t in zip(z["name_ids"], z["name_text"], strict=True)}
        return cls(np.asarray(z["rgb"], np.uint8), tuple(ids), names,
                   tuple(str(x) for x in z["resnames"]), meta)  # fmt: skip

    def distances(self, square: Any) -> np.ndarray:
        """PURE: every picture's mean absolute colour difference from the RGB ``square`` over
        COMPARE."""
        o = np.asarray(square, np.float32)[COMPARE, :].reshape(1, -1)
        return np.asarray(np.abs(self._flat - o).mean(axis=1))  # type: ignore[attr-defined]

    def pair(self, square: Any, p: int, q: int) -> tuple[int, float]:
        """PURE: the rival test of pictures ``p`` and ``q`` on the RGB ``square``: (the pixels that
        tell them apart -- where their composited squares differ by more than DIFF_PX --, the
        read's LEAD of ``p`` over ``q`` there: (its mean colour difference from ``q`` - from
        ``p``) / the pictures' own mean difference there, in [-1, 1])."""
        f = self._flat  # type: ignore[attr-defined]
        a, b = f[p].reshape(-1, 3), f[q].reshape(-1, 3)
        apart = np.abs(a - b).mean(axis=1) > DIFF_PX
        n = int(apart.sum())
        if n == 0:
            return 0, 0.0
        o = np.asarray(square, np.float32)[COMPARE, :].reshape(-1, 3)[apart]
        e_p, e_q = float(np.abs(o - a[apart]).mean()), float(np.abs(o - b[apart]).mean())
        return n, (e_q - e_p) / float(np.abs(a[apart] - b[apart]).mean())

    def picture_of(self, item: int) -> int | None:
        return self._pic_of.get(int(item))  # type: ignore[attr-defined, no-any-return]

    def has(self, item: int) -> bool:
        return self.picture_of(item) is not None

    def name(self, item: int) -> str:
        return self.names.get(int(item), f"item {int(item)}")


@dataclass(frozen=True)
class SlotRead:
    """One slot's read: the item named (state "item"), an empty slot, or "cannot tell"."""

    slot: int
    state: str  # "item" | "empty" | "unread"
    ids: tuple[int, ...]  # the named picture's group's item ids (state "item"; else the best's)
    dist: float | None  # the best picture's distance
    next_dist: float | None  # the next DIFFERENT picture's
    next_ids: tuple[int, ...]
    why: str
    name: str | None = None  # the named item's English name (state "item")
    pair_lead: float | None = None  # the read's least lead over a rival (inf: no rival)

    @property
    def key(self) -> str:
        return f"F{self.slot + 1}"

    def record(self) -> dict[str, Any]:
        r = None if self.dist is None else round(self.dist, 1)
        n = None if self.next_dist is None else round(self.next_dist, 1)
        pm = self.pair_lead
        pm_ = None if pm is None else (round(pm, 2) if pm != float("inf") else "inf")
        return {"slot": self.slot, "key": self.key, "state": self.state, "name": self.name,
                "ids": list(self.ids[:8]), "dist": r, "next": n,
                "next_ids": list(self.next_ids[:4]), "pair_lead": pm_,
                "why": self.why}  # fmt: skip


def square_at(frame: Any, slot: int) -> np.ndarray | None:
    """PURE: slot ``slot``'s RGB square from a BGR game-region frame (None: outside it)."""
    import hotbar_count as hb

    x, y = ICON_ORIGIN[0] + hb.PITCH * slot, ICON_ORIGIN[1]
    img = np.asarray(frame)
    if x < 0 or y < 0 or y + SIZE > img.shape[0] or x + SIZE > img.shape[1]:
        return None
    return np.ascontiguousarray(img[y : y + SIZE, x : x + SIZE, 2::-1]).astype(np.float32)


def slot_empty(frame: Any, slot: int) -> bool:
    """PURE: hotbar_count's EMPTY slot (no digit and no icon) on a BGR game-region frame."""
    import hotbar_count as hb

    rows = max(hb.Y1, hb.ICON[3])  # the hotbar's rows only (a whole frame's grey costs ~20 ms)
    return hb.read_count(hb.gray(np.asarray(frame)[:rows]), slot, {}) == 0


def face_white(square: Any) -> bool:
    """PURE: the square (RGB) below the frame's top line reads as the slot's white face: an empty
    slot, not a load screen's flat picture where no hotbar is drawn."""
    return float(np.asarray(square, np.float32)[1:].mean()) >= FACE_MIN


def read_slot(frame: Any, slot: int, refs: SlotRefs) -> SlotRead:
    """PURE: which item slot ``slot`` of ``frame`` (BGR, game-region pixels) shows."""
    sq = square_at(frame, slot)
    if sq is None:
        return SlotRead(slot, "unread", (), None, None, (), "the slot is outside the frame")
    if float(sq.mean()) < DARK:
        return SlotRead(slot, "unread", (), None, None, (), "the slot is dark (a load screen, a "
                        "teleport's dark frames)")  # fmt: skip
    if slot_empty(frame, slot):
        if not face_white(sq):
            return SlotRead(slot, "unread", (), None, None, (), "no hotbar slot is drawn there (a "
                            "flat picture: a load screen?)")  # fmt: skip
        return SlotRead(slot, "empty", (), None, None, (), f"F{slot + 1} is empty")
    d = refs.distances(sq)
    order = [int(i) for i in np.argsort(d)]
    best = order[0]
    d1 = float(d[best])
    group, rivals = [best], []
    for p in order[1:TOP_K]:
        if float(d[p]) > d1 + RIVAL_RANGE:
            break
        n, lead = refs.pair(sq, best, p)
        if n < DISCRIM_MIN:
            group.append(p)
        else:
            rivals.append((p, lead))
    rest = next((p for p in order if p not in group), None)
    d2 = float(d[rest]) if rest is not None else float("inf")
    ids = tuple(sorted({i for p in group for i in refs.ids[p]}))
    nxt = refs.ids[rest] if rest is not None else ()
    label = refs.name(ids[0])
    pm = min((m for _p, m in rivals), default=float("inf"))
    if d1 > NAME_MAX:
        return SlotRead(slot, "unread", ids, d1, d2, nxt, f"F{slot + 1}'s icon matches no known "
                        f"item (the nearest, {label}, at {d1:.1f} > {NAME_MAX:g})", None,
                        pm)  # fmt: skip
    if pm < PAIR_LEAD:
        rv = next(p for p, m in rivals if m == pm)
        return SlotRead(slot, "unread", ids, d1, d2, nxt, f"F{slot + 1}'s icon matches two items "
                        f"alike ({label} and {refs.name(refs.ids[rv][0])}: a lead of {pm:.2f} "
                        f"where they differ, < {PAIR_LEAD:g})", None, pm)  # fmt: skip
    return SlotRead(slot, "item", ids, d1, d2, nxt, f"F{slot + 1} shows {article(label)} ({d1:.1f};"
                    f" the next item {d2:.1f})", label, pm)  # fmt: skip


def article(name: str) -> str:
    """PURE: "a White Potion", "an Apple" -- the words' article."""
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def decisive(reads: Sequence[SlotRead]) -> bool:
    """PURE: every read named an item or an empty slot (no "cannot tell")."""
    return all(r.state != "unread" for r in reads)


def read_slots_until(
    frame_fn: Callable[[], Any],
    slots: Iterable[int],
    refs: SlotRefs,
    wait_s: float,
    poll_s: float = 0.25,
) -> tuple[dict[int, SlotRead], int]:
    """Frames from ``frame_fn`` until every slot of ``slots`` reads decisively (an item or empty)
    or ``wait_s`` passes; each slot keeps its first decisive read (else its last). Returns the
    reads and the number of frames read."""
    want = sorted(set(slots))
    got: dict[int, SlotRead] = {}
    n = 0
    t0 = time.monotonic()
    while True:
        frame = frame_fn()
        n += 1
        for s in want:
            if s not in got or got[s].state == "unread":
                got[s] = read_slot(frame, s, refs)
        if decisive([got[s] for s in want]) or time.monotonic() - t0 >= wait_s:
            return got, n
        time.sleep(poll_s)


def shows(read: SlotRead | None, items: Iterable[int]) -> str:
    """PURE: what a read says of a role's item -- "right" (one of ``items`` is in the named
    picture's group), "wrong" (ANOTHER item is named), "empty" (no item on the slot) or "unknown"
    (cannot tell, or no read: no references)."""
    if read is None or read.state == "unread":
        return "unknown"
    if read.state == "empty":
        return "empty"
    return "right" if set(read.ids) & {int(i) for i in items} else "wrong"


# --- the build ----------------------------------------------------------------------------------


def parse_table(text: str) -> dict[int, str]:
    """PURE: idnum2itemresnametable.txt's ``id#resname#`` lines -> {id: resname}; the first line
    of an id wins; ``//`` lines and malformed lines are skipped."""
    out: dict[int, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        parts = line.split("#")
        if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip():
            out.setdefault(int(parts[0].strip()), parts[1].strip())
    return out


def kb_names(kb: Path = KB) -> dict[int, str] | None:
    """The server's items by the local KB (data/kb/items.json): {id: English name}; None when
    it does not read."""
    try:
        doc = json.loads((kb / "items.json").read_text())
    except (OSError, ValueError):
        return None
    return {int(k): str(v.get("name") or k) for k, v in doc.items() if str(k).isdigit()}


def build_refs(grf: Path, *, mixcrypt: bool,
               names: Mapping[int, str] | None) -> tuple[SlotRefs, dict[str, Any]]:  # fmt: skip
    """The references from the archive: each item id (``names``' ids; None = every id of the
    archive's table) -> its resource name -> its item bitmap."""
    from grf_read import norm_name
    from map_identity import Archive
    from PIL import Image

    icons: dict[int, np.ndarray] = {}
    res_of: dict[int, str] = {}
    report: dict[str, Any] = {"refused": 0, "unreadable": 0, "no_bitmap": 0, "too_big": 0}
    with grf.open("rb") as f:
        arc = Archive.open(f, mixcrypt=mixcrypt)
        raw = arc.read(TABLE)
        if raw is None:
            raise SystemExit(f"slot_items build: {TABLE} does not read ({arc.errors.get(TABLE)})")
        table = parse_table(raw.decode("cp949", errors="replace"))
        bmps: dict[str, str] = {}
        for key in arc.by_name:
            m = ITEM_BMP.match(key)
            if m:
                bmps.setdefault(m.group(1), key)
        want = sorted(table) if names is None else sorted(i for i in names if i in table)
        decoded: dict[str, np.ndarray | None] = {}
        for iid in want:
            key_ = bmps.get(norm_name(table[iid]))
            if key_ is None:
                report["no_bitmap"] += 1
                continue
            if key_ not in decoded:
                data = arc.read(key_)
                if data is None:
                    report["refused"] += 1
                    decoded[key_] = None
                    continue
                try:
                    decoded[key_] = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
                except OSError:
                    report["unreadable"] += 1
                    decoded[key_] = None
                    continue
                if fit_square(decoded[key_]) is None:
                    report["too_big"] += 1
            if (rgb := decoded[key_]) is not None:
                icons[iid] = rgb
                res_of[iid] = table[iid]
    meta = {"grf": str(grf), "grf_bytes": grf.stat().st_size, "mixcrypt": mixcrypt,
            "built": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ids_asked": len(want),
            "item_set": "all" if names is None else "the server's (KB)"}  # fmt: skip
    refs = SlotRefs.from_icons(icons, names or {}, res_of, meta)
    report.update(meta, ids=sum(len(i) for i in refs.ids), pictures=len(refs.ids))
    return refs, report


# --- the CLI ------------------------------------------------------------------------------------


def _load_frame(path: Path) -> np.ndarray:
    """A saved frame (PNG / JPG, RGB on disk; or a .npy BGR game region) as the runner's BGR game
    region (a 1440 x 900 session picture is cut at the lab's GAME_REGION 80,77)."""
    if path.suffix == ".npy":
        return np.ascontiguousarray(np.load(path)[..., :3])
    from PIL import Image

    a = np.asarray(Image.open(path).convert("RGB"))
    if a.shape[:2] == (900, 1440):
        a = a[77:797, 80:1360]
    return np.ascontiguousarray(a[..., ::-1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="the references from the client's archive")
    b.add_argument("--grf", type=Path, default=GRF)
    b.add_argument("--decode-mixcrypt", action="store_true",
                   help="encrypted bitmaps: the host-local study decoder (grf_read)")  # fmt: skip
    b.add_argument("--kb", type=Path, default=KB, help="the server's items (data/kb)")
    b.add_argument("--all", action="store_true", help="every id of the archive's table, not the "
                   "server's items")  # fmt: skip
    b.add_argument("--out", type=Path, default=REFS)
    rd = sub.add_parser("read", help="read saved frames (PNG/JPG game regions or .npy BGR)")
    rd.add_argument("images", nargs="+", type=Path)
    rd.add_argument("--slots", type=int, nargs="+", default=list(range(9)))
    rd.add_argument("--refs", type=Path, default=REFS)
    ev = sub.add_parser("eval", help="score recorded sessions (slot_items_eval.py)")
    ev.add_argument("sessions", nargs="+", help="NAS session names (or absolute paths)")
    ev.add_argument("--shards", default="first,last", help="first, last, mid or indexes")
    ev.add_argument("--refs", type=Path, default=REFS)
    ev.add_argument("--out", type=Path, default=None)
    ev.add_argument(
        "--strips",
        type=Path,
        default=None,
        help="one enlarged hotbar strip per "
        "session, for the person's layout check (client pixels: /dev/shm only)",
    )
    a = ap.parse_args(argv)
    if a.cmd == "build":
        names = None if a.all else kb_names(a.kb)
        if names is None and not a.all:
            raise SystemExit(f"slot_items build: no KB at {a.kb}/items.json (or pass --all)")
        refs, report = build_refs(a.grf, mixcrypt=a.decode_mixcrypt, names=names)
        refs.save(a.out)
        print(json.dumps({**report, "out": str(a.out)}, indent=1))
        return 0
    refs = SlotRefs.load(a.refs)
    if a.cmd == "read":
        for p in a.images:
            frame = _load_frame(p)
            for s in a.slots:
                print(json.dumps({"image": str(p), **read_slot(frame, s, refs).record()}))
        return 0
    import slot_items_eval as sie

    return sie.run(a.sessions, a.shards.split(","), refs, a.out, a.strips)


if __name__ == "__main__":
    raise SystemExit(main())
