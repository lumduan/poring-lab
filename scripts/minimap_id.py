#!/usr/bin/env python3
"""Which MAP the game screen shows, read from the minimap's PICTURE (dungeon@9.46; Batt
2026-11-13 "do it": the start check passed her Geffen cell (119, 40) as xmas_dun02's open ground).

    OMP_NUM_THREADS=2 minimap_id.py build [--grf PATH] [--decode-mixcrypt] [--mapcache-dir DIR]
                      [--all] [--out NPZ]        (~30 s; every BLAS thread: 74 s, no better)
    minimap_id.py read IMAGE... [--expect MAP] [--refs NPZ]
    minimap_id.py eval SPEC.json [--expect MAP] [--refs NPZ] [--out JSON]

What the screen offers (measured 2026-11-13, docs/planning/player-mode.md "The map's name"): the
client writes no map name anywhere in play -- the minimap's readout under it is the cell only. But
the minimap draws the MAP'S OWN PICTURE, the archive's per-map minimap bitmap (``<texture
folder>/map/<map>.bmp``, the name through ``data/resnametable.txt``, as every resource): at the
lab's zoom the WHOLE map, scaled into a PIC_SIZE square at the minimap window's origin +
PIC_OFFSET. Its magenta key colour (255, 0, 255) is transparent, every other pixel is drawn
translucent over the scene, and the NPC marks and her own arrow are drawn on top.

How (numpy only; PURE but for the CLI):
  1. the square is cut from the frame (BGR, game-region pixels) and turned grey;
  2. every reference picture (``build``: the archive's bitmap, rendered the way the client draws
     it -- the key colour out, box-scaled to PIC_SIZE) is scored by the normalised cross-
     correlation over ITS OWN drawn pixels (the key pixels show the scene and say nothing). A
     correlation is blind to the translucency (a gain) and to a flat scene behind (an offset);
  3. the best picture is named when it scores at least NAME_MIN and beats the next DIFFERENT
     picture by MARGIN_MIN (two pictures at least COPY_NCC alike, e.g. prontera / pprontera, are
     one: a copy group, every server map that draws it). Otherwise the read is None: "cannot tell"
     (a load screen, an indoor map without a minimap, a window over it, a zoomed-in view, or a map
     whose picture is not in the references);
  4. map_verdict: the run's map is TICKED only when it is (in) the named picture's group AND the
     score reaches MATCH_MIN; another map named = "she is on X, not <map>"; else "cannot tell".

The references are CLIENT-derived: built at run time from the archive (read in place, read-only;
grf_read via map_identity.Archive), written to data/minimap_refs/ (gitignored), never committed
(CLAUDE.md rule 4). Encrypted bitmaps (MIXCRYPT: 629 of the Thai archive's 731, xmas_dun02's
among them) need ``--decode-mixcrypt``, the lab's host-local study decoder (grf_read; never in
the repo); without it those maps have no reference and read "cannot tell".
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FORMAT = 1
REFS = ROOT / "data" / "minimap_refs" / "refs.npz"
GRF = Path("/mnt/poring-thai-src/ro_thai/data.grf")
WINDOW = "minimap"  # poring_env.ui_anchors' window; CAPTURE_ORIGINS gives its home
# the picture's square from the window's origin (1136, 18), measured 2026-11-13 on 4 frames each
# of 6 maps (xmas_dun02, gef_fild10, pay_fild07, prt_fild08, orcsdun01, alberta): the best mean
# correlation of every size 122-132 x 122-132 at every offset +-4 px (0.832; 129 x 127 at (0, -1)
# 0.826, 128 x 128 at (0, -2) 0.800)
PIC_OFFSET = (1, -1)
PIC_SIZE = 127
KEY_MIN, KEY_MAX = 250, 5  # the key colour: R and B at least KEY_MIN, G at most KEY_MAX
COVER_MIN = 0.99  # a scaled reference pixel is DRAWN when this share of its source is not key
PIXELS_MIN = 0.10  # a picture drawn on fewer of the square's pixels is no reference
FLAT_STD = 4.0  # a square this flat (grey std) shows no picture: a load screen, a black frame
NAME_MIN = 0.40  # the best picture scores at least this to be named ...
MARGIN_MIN = 0.15  # ... and beats the next different picture by this much
MATCH_MIN = 0.60  # the run's map is ticked only at this score (and the name's margin)
COPY_NCC = 0.95  # two reference pictures this alike are ONE picture (a copy group)
# what a verdict's number is (matpilot round 16 #10): every score is said with its scale and the
# threshold it is measured against, never bare
SCALE = "where 1.00 is the same picture"
NAMED = f"a map is named at {NAME_MIN:.2f} or more, {MARGIN_MIN:.2f} ahead of the next"
TOP_K = 12  # the copy test looks at so many best pictures
MAP_BMP = re.compile(r"(?:^|/)map/([^/]+)\.bmp$")  # an archive / resnametable minimap name


def gray_bgr(img: Any) -> np.ndarray:
    """Grey of a BGR(A) image (the runner's frames), float32."""
    f = np.asarray(img)[..., :3].astype(np.float32)
    return np.asarray(0.114 * f[..., 0] + 0.587 * f[..., 1] + 0.299 * f[..., 2], np.float32)


def gray_rgb(img: Any) -> np.ndarray:
    """Grey of an RGB image (an archive bitmap, a PNG read by PIL), float32."""
    f = np.asarray(img)[..., :3].astype(np.float32)
    return np.asarray(0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2], np.float32)


def home_origin() -> tuple[int, int]:
    """The minimap window's measured origin in the 1280x720 game region (right-anchored)."""
    from poring_env.ui_anchors import CAPTURE_ORIGINS

    return CAPTURE_ORIGINS[WINDOW]


def render_picture(rgb: Any, size: int = PIC_SIZE) -> tuple[np.ndarray, np.ndarray]:
    """PURE: an archive minimap bitmap (H, W, 3 RGB uint8) as the client draws it in the whole-
    map view: (grey (size, size) float32, drawn (size, size) bool). The key colour is not drawn;
    each scaled pixel is the mean of its source's drawn pixels (a box filter, the key left out),
    and it counts as drawn when at least COVER_MIN of its source is."""
    a = np.asarray(rgb)[..., :3].astype(np.float32)
    drawn = ~((a[..., 0] >= KEY_MIN) & (a[..., 1] <= KEY_MAX) & (a[..., 2] >= KEY_MIN))
    w = drawn.astype(np.float32)
    h0, w0 = w.shape
    # box-scale by exact area: each output pixel averages the source rows / columns it covers
    ry = _box_matrix(h0, size)
    rx = _box_matrix(w0, size)
    cover = ry @ w @ rx.T
    num = np.stack([ry @ (a[..., c] * w) @ rx.T for c in range(3)], -1)
    col = num / np.maximum(cover, 1e-6)[..., None]
    return gray_rgb(col), cover >= COVER_MIN


def _box_matrix(n_in: int, n_out: int) -> np.ndarray:
    """(n_out, n_in): the area share of each source cell in each output cell (rows sum to 1)."""
    m = np.zeros((n_out, n_in), np.float32)
    scale = n_in / n_out
    for o in range(n_out):
        lo, hi = o * scale, (o + 1) * scale
        for i in range(int(lo), min(n_in, int(np.ceil(hi)))):
            m[o, i] = min(hi, i + 1) - max(lo, i)
    return m / m.sum(1, keepdims=True)


@dataclass(frozen=True)
class MapRefs:
    """The reference pictures and the server map names that draw them."""

    names: tuple[str, ...]  # server map names (sorted)
    pic_of: tuple[int, ...]  # name -> picture index
    pic_names: tuple[str, ...]  # picture -> the archive bitmap's name (words, logs)
    grey: np.ndarray  # (P, S, S) float32
    drawn: np.ndarray  # (P, S, S) bool
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        p, s = self.grey.shape[0], self.grey.shape[1]
        g = self.grey.reshape(p, -1).astype(np.float64)
        m = self.drawn.reshape(p, -1).astype(np.float64)
        n = m.sum(1)
        mean = (g * m).sum(1) / np.maximum(n, 1)
        gc = (g - mean[:, None]) * m
        object.__setattr__(self, "_m", m)
        object.__setattr__(self, "_n", n)
        object.__setattr__(self, "_gc", gc)
        object.__setattr__(self, "_vg", (gc * gc).sum(1))
        object.__setattr__(self, "size", s)

    @classmethod
    def from_pictures(cls, pictures: Mapping[str, tuple[Any, Any]],
                      names: Mapping[str, str] | None = None,
                      meta: Mapping[str, Any] | None = None) -> MapRefs:  # fmt: skip
        """PURE: refs from {picture name: (grey, drawn)} and {server map: picture name} (default:
        every picture is its own map). Pictures drawn on fewer than PIXELS_MIN of the square are
        left out; identical pictures are merged."""
        names = {k: k for k in pictures} if names is None else dict(names)
        keep: dict[str, int] = {}
        greys: list[np.ndarray] = []
        drawns: list[np.ndarray] = []
        pic_names: list[str] = []
        seen: dict[bytes, int] = {}
        for pn in sorted(pictures):
            g, d = pictures[pn]
            g = np.asarray(g, np.float32)
            d = np.asarray(d, bool)
            if d.mean() < PIXELS_MIN:
                continue
            key = np.round(g * d, 1).tobytes() + np.packbits(d).tobytes()
            if key in seen:
                keep[pn] = seen[key]
                continue
            seen[key] = keep[pn] = len(greys)
            greys.append(g)
            drawns.append(d)
            pic_names.append(pn)
        ns = sorted(m for m, pn in names.items() if pn in keep)
        if not greys:
            raise ValueError("no usable reference picture")
        return cls(tuple(ns), tuple(keep[names[m]] for m in ns), tuple(pic_names),
                   np.stack(greys), np.stack(drawns), dict(meta or {}))  # fmt: skip

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path, names=np.array(self.names), pic_of=np.array(self.pic_of, np.int32),
            pic_names=np.array(self.pic_names),
            grey=np.clip(np.round(self.grey), 0, 255).astype(np.uint8), drawn=self.drawn,
            meta=np.array(json.dumps({**self.meta, "format": FORMAT})),
        )  # fmt: skip

    @classmethod
    def load(cls, path: Path = REFS) -> MapRefs:
        z = np.load(path)
        meta = json.loads(str(z["meta"]))
        if meta.get("format") != FORMAT:
            raise ValueError(f"{path}: format {meta.get('format')}, want {FORMAT}: rebuild it")
        return cls(tuple(str(x) for x in z["names"]), tuple(int(x) for x in z["pic_of"]),
                   tuple(str(x) for x in z["pic_names"]), z["grey"].astype(np.float32),
                   z["drawn"].astype(bool), meta)  # fmt: skip

    def scores(self, square: Any) -> np.ndarray:
        """PURE: every picture's correlation with the grey ``square`` over its drawn pixels."""
        o = np.asarray(square, np.float64).reshape(-1)
        m, n, gc, vg = self._m, self._n, self._gc, self._vg  # type: ignore[attr-defined]
        so, so2 = m @ o, m @ (o * o)
        vo = so2 - so * so / np.maximum(n, 1)
        out = (gc @ o) / np.sqrt(np.maximum(vg * vo, 1e-9))
        return np.asarray(np.where((vg > 0) & (vo > 0), out, 0.0))

    def alike(self, p: int, q: int) -> float:
        """PURE: two pictures' correlation over the pixels both draw (the copy test)."""
        both = self.drawn[p] & self.drawn[q]
        if both.sum() < 2:
            return 0.0
        a = self.grey[p][both].astype(np.float64)
        b = self.grey[q][both].astype(np.float64)
        a, b = a - a.mean(), b - b.mean()
        d = float(np.sqrt((a * a).sum() * (b * b).sum()))
        return float((a * b).sum() / d) if d > 0 else 1.0

    def maps_of(self, pics: Iterable[int]) -> tuple[str, ...]:
        """The server maps that draw these pictures, the shortest name first (prontera before
        pprontera: the one a person knows)."""
        ps = set(pics)
        got = [m for m, p in zip(self.names, self.pic_of, strict=True) if p in ps]
        return tuple(sorted(got, key=lambda m: (len(m), m)))

    def has(self, map_: str) -> bool:
        return map_ in self.names


@dataclass(frozen=True)
class MapRead:
    """One frame's read: the map named (None: cannot tell) and why."""

    map: str | None  # the named picture's first server map (its group in ``names``)
    names: tuple[str, ...]  # every server map that draws the best picture
    score: float  # the best picture's correlation
    next_score: float  # the next DIFFERENT picture's
    next_names: tuple[str, ...]
    picture: str | None  # the best picture's archive name
    why: str

    @property
    def margin(self) -> float:
        return self.score - self.next_score

    def record(self) -> dict[str, Any]:
        return {"map": self.map, "names": list(self.names[:8]), "score": round(self.score, 3),
                "next": round(self.next_score, 3), "next_names": list(self.next_names[:4]),
                "picture": self.picture, "why": self.why}  # fmt: skip


def unread(why: str) -> MapRead:
    """PURE: a read that saw no picture at all."""
    return MapRead(None, (), 0.0, 0.0, (), None, why)


def square_at(frame: Any, origin: tuple[int, int] | None = None) -> np.ndarray | None:
    """PURE: the picture's grey square from a BGR game-region frame (None: outside the frame)."""
    ox, oy = home_origin() if origin is None else origin
    x, y = ox + PIC_OFFSET[0], oy + PIC_OFFSET[1]
    img = np.asarray(frame)
    if x < 0 or y < 0 or y + PIC_SIZE > img.shape[0] or x + PIC_SIZE > img.shape[1]:
        return None
    return gray_bgr(img[y : y + PIC_SIZE, x : x + PIC_SIZE].copy())


def read_map(frame: Any, refs: MapRefs, origin: tuple[int, int] | None = None) -> MapRead:
    """PURE: which map ``frame`` (BGR, game-region pixels) shows, by its minimap picture."""
    sq = square_at(frame, origin)
    if sq is None:
        return unread("the minimap's square is outside the frame")
    if sq.shape != (refs.size, refs.size):
        return unread(f"the references are {refs.size} px, the square {PIC_SIZE}: rebuild them")
    if float(sq.std()) < FLAT_STD:
        return unread("no minimap picture (a flat square: a load screen, or no minimap)")
    sc = refs.scores(sq)
    order = [int(i) for i in np.argsort(-sc)]
    best = order[0]
    group = [best] + [p for p in order[1:TOP_K] if refs.alike(best, p) >= COPY_NCC]
    rest = [p for p in order if p not in group]
    nxt = rest[0] if rest else None
    s1 = float(sc[best])
    s2 = float(sc[nxt]) if nxt is not None else 0.0
    names = refs.maps_of(group)
    nn = refs.maps_of([nxt]) if nxt is not None else ()
    pic = refs.pic_names[best]
    label = names[0] if names else pic
    if s1 < NAME_MIN:
        return MapRead(None, names, s1, s2, nn, pic, f"no map's picture matches the minimap (the "
                       f"best, {label}'s, has a match score of {s1:.2f}, {SCALE} and "
                       f"{NAMED})")  # fmt: skip
    if s1 - s2 < MARGIN_MIN:
        return MapRead(None, names, s1, s2, nn, pic, f"two maps' pictures match the minimap alike "
                       f"({label}'s with a match score of {s1:.2f} and {nn[0] if nn else '?'}'s "
                       f"with {s2:.2f}, {SCALE} and {NAMED})")  # fmt: skip
    return MapRead(label, names, s1, s2, nn, pic, f"the minimap is {label}'s (a match score of "
                   f"{s1:.2f}, {SCALE}; the next map's picture scores {s2:.2f})")  # fmt: skip


def map_verdict(read: MapRead, map_: str, refs: MapRefs | None) -> tuple[bool | None, str]:
    """PURE (dungeon@9.46): the run's map from a read -- True only when ``map_`` draws the named
    picture and it scores at least MATCH_MIN; False when another map is named; None: cannot
    tell (the words say why)."""
    if refs is None or not refs.has(map_):
        return None, (f"no minimap reference for {map_} (build them: python3 scripts/"
                      "minimap_id.py build)")  # fmt: skip
    if read.map is None:
        return None, f"the map is not read from the minimap: {read.why}"
    if map_ in read.names:
        copies = [m for m in read.names if m != map_]
        also = f"; the same picture as {', '.join(copies[:4])}" if copies else ""
        if read.score < MATCH_MIN:
            return None, (f"the minimap looks like {map_}'s, but only weakly (it matches {map_}'s "
                          f"map picture with a match score of {read.score:.2f}, {SCALE} and the "
                          f"run's map needs {MATCH_MIN:.2f} or more{also})")  # fmt: skip
        return True, (f"the minimap is {map_}'s (it matches {map_}'s map picture with a match "
                      f"score of {read.score:.2f}, {SCALE} and the run's map needs "
                      f"{MATCH_MIN:.2f} or more; the next map's picture scores "
                      f"{read.next_score:.2f}{also})")  # fmt: skip
    # matpilot round 16 #10: a bare "0.47" said nothing to a reader (a teacher, a child): the words
    # say what was read, what the number is and what it is measured against. The run's map is not
    # in the named group, so its own picture scores at most the next different picture's
    own = "scores" if map_ in read.next_names else "scores at most"
    return False, (f"she is on {read.map}, not {map_} (the minimap shows {read.map}'s map picture "
                   f"with a match score of {read.score:.2f}, {SCALE} and {NAMED}; {map_}'s "
                   f"picture {own} {read.next_score:.2f})")  # fmt: skip


def decisive(reads: Sequence[MapRead]) -> MapRead | None:
    """PURE: the first read that names a map (None: none did)."""
    return next((r for r in reads if r.map is not None), None)


def read_until(frame_fn: Any, refs: MapRefs, wait_s: float, poll_s: float = 0.25,
               clock: Any = time.monotonic,
               sleep: Any = time.sleep) -> tuple[MapRead, int]:  # fmt: skip
    """Frames from ``frame_fn`` until one names a map or ``wait_s`` passes: (the last read, the
    frames read). A frame mid-effect or with a mark over the picture can read "cannot tell"; a
    standing start reads on its first frame (docs/planning/player-mode.md)."""
    t0 = clock()
    n = 0
    while True:
        rd = read_map(frame_fn(), refs)
        n += 1
        if rd.map is not None or clock() - t0 >= wait_s:
            return rd, n
        sleep(poll_s)


# --- build (the references from the client's archive) ---------------------------------------------


def server_maps(mapcache_dir: Path | None) -> list[str] | None:
    """The server's map names (the lab's pre-re map cache), or None when it does not load."""
    try:
        from poring_dataset import mapcache

        grids = mapcache.load(mapcache_dir or mapcache.GENERATED, prere=True)
    except Exception:  # noqa: BLE001 -- a missing cache = every picture by its own name
        return None
    return sorted(grids)


def bmp_aliases(table: Mapping[str, str]) -> dict[str, str]:
    """PURE: resnametable lines for minimap bitmaps -> {asked map: opened picture}."""
    out: dict[str, str] = {}
    for asked, opened in table.items():
        a, o = MAP_BMP.search(asked), MAP_BMP.search(opened)
        if a and o:
            out.setdefault(a.group(1), o.group(1))
    return out


def build_refs(grf: Path, *, mixcrypt: bool, maps: Sequence[str] | None,
               size: int = PIC_SIZE) -> tuple[MapRefs, dict[str, Any]]:  # fmt: skip
    """The references from the archive: each server map (``maps``; None = every bitmap by its
    own name) -> its minimap bitmap through resnametable -> render_picture."""
    from map_identity import RESNAME, Archive, parse_resnametable
    from PIL import Image

    pictures: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    report: dict[str, Any] = {"refused": {}, "unreadable": {}}
    with grf.open("rb") as f:
        arc = Archive.open(f, mixcrypt=mixcrypt)
        raw = arc.read(RESNAME)
        table = parse_resnametable(raw.decode("cp949", errors="replace")) if raw else {}
        aliases = bmp_aliases(table)
        bmps: dict[str, str] = {}
        for key in arc.by_name:
            m = MAP_BMP.search(key)
            if m and key.startswith("data/texture/"):
                bmps.setdefault(m.group(1), key)
        want = sorted(bmps) if maps is None else list(maps)
        names = {m: aliases.get(m, m) for m in want if aliases.get(m, m) in bmps}
        for pic in sorted(set(names.values())):
            data = arc.read(bmps[pic])
            if data is None:
                report["refused"][pic] = arc.errors.get(bmps[pic], "?")
                continue
            try:
                rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
            except OSError as e:
                report["unreadable"][pic] = str(e)
                continue
            pictures[pic] = render_picture(rgb, size)
    meta = {"grf": str(grf), "grf_bytes": grf.stat().st_size, "mixcrypt": mixcrypt,
            "size": size, "built": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "maps_asked": len(want), "pictures": len(pictures)}  # fmt: skip
    refs = MapRefs.from_pictures(pictures, {m: p for m, p in names.items() if p in pictures},
                                 meta)  # fmt: skip
    report.update(meta, maps=len(refs.names), unique_pictures=len(refs.pic_names),
                  refused_n=len(report["refused"]),
                  unreadable_n=len(report["unreadable"]))  # fmt: skip
    return refs, report


# --- the CLI ------------------------------------------------------------------------------------


def _load_frame(path: Path) -> np.ndarray:
    """A saved frame (PNG / JPG, RGB on disk) as the runner's BGR game region (a 1440x900
    session picture is cut at the lab's GAME_REGION 80,77)."""
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
    b.add_argument("--mapcache-dir", type=Path, default=None)
    b.add_argument("--all", action="store_true", help="every bitmap by its own name, not the "
                   "server's map list")  # fmt: skip
    b.add_argument("--out", type=Path, default=REFS)
    rd = sub.add_parser("read", help="read saved frames (PNG/JPG game regions)")
    rd.add_argument("images", nargs="+", type=Path)
    rd.add_argument("--expect", default=None)
    rd.add_argument("--refs", type=Path, default=REFS)
    ev = sub.add_parser("eval", help="score recorded frames (minimap_id_eval.py)")
    ev.add_argument("spec", type=Path)
    ev.add_argument("--expect", default="xmas_dun02")
    ev.add_argument("--refs", type=Path, default=REFS)
    ev.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        maps = None if a.all else server_maps(a.mapcache_dir)
        refs, report = build_refs(a.grf, mixcrypt=a.decode_mixcrypt, maps=maps)
        refs.save(a.out)
        print(json.dumps({**{k: v for k, v in report.items() if k not in ("refused",
                                                                          "unreadable")},
                          "out": str(a.out), "map_list": "all" if maps is None else
                          "the server's map cache"}, indent=1))  # fmt: skip
        return 0
    if a.cmd == "read":
        refs = MapRefs.load(a.refs)
        for p in a.images:
            got = read_map(_load_frame(p), refs)
            row: dict[str, Any] = {"image": str(p), **got.record()}
            if a.expect:
                ok, words = map_verdict(got, a.expect, refs)
                row.update(expect=a.expect, ok=ok, words=words)
            print(json.dumps(row))
        return 0
    import minimap_id_eval as mie

    return mie.run(a.spec, MapRefs.load(a.refs), a.expect, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
