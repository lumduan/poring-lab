#!/usr/bin/env python3
"""Monster NAME TAGS: the client's own species label, drawn under a hovered (or attack-locked)
monster -- the species check for hunting attack clicks (Batt 2026-10-16 ~19:50: the size gate
cannot tell a Creamy, a non-target, from a Poring; both measure ~39 x 36 px).

The tag is dark text with a light outline, centred under the sprite, ~20-50 px below the box's
bottom; it appears ~0.4-0.8 s after the pointer stops on the monster. Templates are cut from RAW
live frames (the recordings are JPEG q80: thin outlined letters break), labelled by the packets
(the species of the mob nearest the hovered cell), and kept in data/nametags (gitignored: client
pixels, rule 4).

    nametag.py cut [--minutes 6] [--warp X Y] [--map M]
                                                no clicks: hover monsters, cut the raw tag
                                                regions (the warp lands on M, default prt_fild08)
    nametag.py build [--map M]                  label the cuts by packets, write the templates
    nametag.py check [--map M]                  leave-one-out confusion

PER MAP (2026-10-24, the Thief's Payon field): prt_fild08 keeps its files and its five species
exactly; any other map labels by the KB's names of its spawn species (data/kb) and keeps its cuts'
records and templates under data/nametags/<map>/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

DARK_MAX = 60  # a letter's core: every channel at most this (the tag is DARK text, 20:3x probe)
LIGHT_MIN = 150  # its outline: every channel at least this, within 2 px
TAG_BELOW = (-6, 55)  # the search band below the box's bottom (px)
TAG_HALF_W = 70  # half the band's width around the box centre
MIN_WORD_W = 25  # a name is wider than the cursor tip that can enter the band (14 px)
HOVER_S = 0.6  # the tag showed 0.5 s after the pointer stopped (20:3x probe)
MATCH_MIN = 0.72  # template agreement (IoU of the letter cores) to accept a name
TARGET_NAMES = ("Poring", "Lunatic", "Pupa", "Drops")  # prt_fild08's spawn table (farm0.TARGETS)
HOME_MAP = "prt_fild08"  # the original map: its files sit at data/nametags/ itself
PRT_FILD08_NAMES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy"}


def map_dir(root: Path, map_name: str) -> Path:
    """data/nametags for prt_fild08 (unchanged), data/nametags/<map> for any other map."""
    d = root / "data" / "nametags"
    return d if map_name == HOME_MAP else d / map_name


def species_names(map_name: str, spawns: dict[str, Any], mobs: dict[str, Any]) -> dict[int, str]:
    """PURE: the mob id -> name table that labels a map's cuts: prt_fild08's fixed five; else every
    species spawning on the map (the KB's spawns.json + mobs.json)."""
    if map_name == HOME_MAP:
        return dict(PRT_FILD08_NAMES)
    return {int(sp["id"]): str(mobs[str(sp["id"])]["name"]) for sp in spawns.get(map_name, [])
            if str(sp["id"]) in mobs}  # fmt: skip


def letter_mask(a: Any) -> Any:
    """PURE: the tag's letter cores -- DARK pixels with a light pixel within 2 px (the client draws
    monster names as dark text with a light outline: the 20:3x hover probe); dark scenery without
    a light rim (shadows, tree trunks) does not count."""
    a = np.asarray(a)[..., :3].astype(np.int16)
    dark = a.max(-1) <= DARK_MAX
    light = a.min(-1) >= LIGHT_MIN
    pad = np.pad(light, 2)
    near = np.zeros_like(light)
    h, w = light.shape
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near |= pad[2 + dy : 2 + dy + h, 2 + dx : 2 + dx + w]
    return dark & near


def word_box(mask: Any) -> tuple[int, int, int, int] | None:
    """PURE: the bounding box (x0, y0, x1, y1) of the widest word-like run of letters: components
    merged horizontally (gaps <= 3 px), 6-16 px tall, 12-90 px wide; None if there is none."""
    m = np.asarray(mask, dtype=bool)
    d = m.copy()
    for dx in (1, 2, 3):
        d[:, dx:] |= m[:, :-dx]
        d[:, :-dx] |= m[:, dx:]
    h, w = d.shape
    lab = np.zeros((h, w), np.int32)
    best: tuple[int, int, int, int] | None = None
    n = 0
    for y0, x0 in zip(*np.nonzero(d), strict=True):
        if lab[y0, x0]:
            continue
        n += 1
        q = deque([(int(y0), int(x0))])
        lab[y0, x0] = n
        ys, xs = [], []
        while q:
            y, x = q.popleft()
            ys.append(y)
            xs.append(x)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < h and 0 <= xx < w and d[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
        bx = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        bw, bh = bx[2] - bx[0], bx[3] - bx[1]
        if 6 <= bh <= 16 and 12 <= bw <= 90 and (best is None or bw > best[2] - best[0]):
            best = bx
    return best


def match(mask: Any, templates: dict[str, Any], min_iou: float = MATCH_MIN
          ) -> tuple[str | None, float]:  # fmt: skip
    """PURE: the template whose letter cores best agree with the word in ``mask`` (IoU, the word
    and the template aligned at every shift of +-2 px); (name, iou), name None below ``min_iou``."""
    wb = word_box(mask)
    if wb is None:
        return None, 0.0
    word = np.asarray(mask, dtype=bool)[wb[1] : wb[3], wb[0] : wb[2]]
    best: tuple[str | None, float] = (None, 0.0)
    for name, tpl in templates.items():
        t = np.asarray(tpl, dtype=bool)
        H, W = max(word.shape[0], t.shape[0]) + 4, max(word.shape[1], t.shape[1]) + 4
        a = np.zeros((H, W), bool)
        a[2 : 2 + word.shape[0], 2 : 2 + word.shape[1]] = word
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                b = np.zeros((H, W), bool)
                y0, x0 = 2 + dy, 2 + dx
                if y0 < 0 or x0 < 0 or y0 + t.shape[0] > H or x0 + t.shape[1] > W:
                    continue
                b[y0 : y0 + t.shape[0], x0 : x0 + t.shape[1]] = t
                u = int((a | b).sum())
                iou = int((a & b).sum()) / u if u else 0.0
                if iou > best[1]:
                    best = (name, iou)
    return (best[0], best[1]) if best[1] >= min_iou else (None, best[1])


def band(img: Any, box: Any) -> Any:
    """The tag search band under ``box`` (client px; a box with x0 y0 x1 y1) from a game frame."""
    a = np.asarray(img)
    cx = (box.x0 + box.x1) / 2
    y0 = int(box.y1 + TAG_BELOW[0])
    y1 = int(box.y1 + TAG_BELOW[1])
    x0 = int(cx - TAG_HALF_W)
    x1 = int(cx + TAG_HALF_W)
    return a[max(0, y0) : max(0, y1), max(0, x0) : max(0, x1), :3]


def load_templates(path: Path | None = None) -> dict[str, Any]:
    import ro_agent as r

    p = path or (r.ROOT / "data" / "nametags" / "templates.npz")
    if not p.exists():
        return {}
    z = np.load(p)
    return {k: z[k] for k in z.files}


# --- the live cut (no clicks) ------------------------------------------------------------------


def cut(minutes: float, warp: tuple[int, int] | None, map_name: str = HOME_MAP) -> int:
    import bench
    import farm0 as f0
    import farm1 as f1
    import loot1
    import ro_agent as r
    import unit_detector

    out = map_dir(r.ROOT, map_name) / "cuts"
    out.mkdir(parents=True, exist_ok=True)
    gx0, gy0, gw, gh = r.game_region()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    log = (out / f"cuts-{stamp}.jsonl").open("a")
    n = 0
    with r.session("rule:nametag-cut@1") as (agent, screen):
        f0.stop_on_takeover(agent)
        if warp is not None:
            r.gm(agent, screen, f"@warp {map_name} {warp[0]} {warp[1]}")
            time.sleep(2.5)
            bench.close_chat(agent, screen)
        det = unit_detector.UnitDetector()
        deadline = time.monotonic() + minutes * 60
        while time.monotonic() < deadline:
            t_, img = screen.grab(gx0, gy0, gw, gh)
            boxes = [b for b in det.detect(img) if b.cls == "monster"
                     and not loot1.in_ui(*f1.centre(b))]  # fmt: skip
            if not boxes:
                time.sleep(0.5)
                continue
            for b in boxes[:4]:
                u, v = f1.centre(b)
                agent.move(gx0 + round(u) - 12, gy0 + round(v) - 12)  # two motions: drawn
                time.sleep(0.08)
                agent.move(gx0 + round(u), gy0 + round(v))
                time.sleep(HOVER_S)
                t2, img2 = screen.grab(gx0, gy0, gw, gh)
                reg = band(img2, b)
                m = letter_mask(reg)
                wb = word_box(m)
                if wb is None:
                    continue
                n += 1
                name = f"cut-{stamp}-{n:04d}"  # unique per session (20:22's were overwritten)
                np.save(out / f"{name}.npy", np.asarray(reg))
                log.write(
                    json.dumps(
                        {
                            "name": name,
                            "t": int(t2),
                            "u": round(u, 1),
                            "v": round(v, 1),
                            "box": [b.x0, b.y0, b.x1, b.y1],
                            "word": list(wb),
                        }
                    )
                    + "\n"
                )
                log.flush()
            agent.move(gx0 + gw - 60, gy0 + gh // 2)
            time.sleep(0.3)
    print(json.dumps({"cuts": n, "dir": str(out)}))
    return 0


def labelled_words(map_name: str = HOME_MAP) -> dict[str, list[Any]]:
    """Every cut labelled by the packets (the species of the live mob nearest the hovered cell):
    {species: [its word's letter mask]}."""
    import flow_judge as fj
    import hunt_core as hc
    import record_session as rs
    import ro_agent as r

    d = map_dir(r.ROOT, map_name) / "cuts"
    recs = [
        json.loads(x) for f in sorted(d.glob("cuts-*.jsonl")) for x in f.read_text().splitlines()
    ]
    if not recs:
        raise SystemExit("no cuts")
    t0, t1 = min(x["t"] for x in recs) - int(30e9), max(x["t"] for x in recs) + int(5e9)
    events = sorted(rs.session_packets(t0, t1)[0], key=lambda e: int(e["t_mono_ns"]))
    pos, life = hc.walk_positions(events), fj.alive(events)
    gm_track, _ = fj.gm_track(events)
    pick = fj.picker(map_name)
    kb = r.ROOT / "data" / "kb"
    names = species_names(map_name, json.loads((kb / "spawns.json").read_text()),
                          json.loads((kb / "mobs.json").read_text()))  # fmt: skip
    by: dict[str, list[Any]] = {}
    for x in recs:
        gm = fj.at(gm_track, x["t"])
        if gm is None:
            continue
        b = x["box"]
        cell = pick(gm, ((b[0] + b[2]) / 2, b[3]))
        if cell is None:
            continue
        best = None
        for g in pos:
            if not fj.present(life, g, x["t"]):
                continue
            c = fj.mob_at(pos, g, x["t"])
            if (
                c is not None
                and fj.cheb(c, cell) <= 2
                and (best is None or fj.cheb(c, cell) < best[0])
            ):
                best = (fj.cheb(c, cell), g)
        if best is None:
            continue
        job = next((int(e.get("job", -1)) for e in reversed(events)
                    if e.get("type") == "entity_appear" and fj.gid_of(e) == best[1]
                    and int(e["t_mono_ns"]) <= x["t"]), -1)  # fmt: skip
        sp = names.get(job)
        if sp is None:
            continue
        m = letter_mask(np.load(d / f"{x['name']}.npy"))
        wb = word_box(m)
        if wb is not None and wb[2] - wb[0] >= MIN_WORD_W:  # not the cursor's tip
            by.setdefault(sp, []).append(m[wb[1] : wb[3], wb[0] : wb[2]])
    return by


def template_of(words: list[Any]) -> Any:
    """PURE: the majority of the letter masks, top-left aligned."""
    h = max(w.shape[0] for w in words)
    w_ = max(w.shape[1] for w in words)
    acc = np.zeros((h, w_), float)
    for w in words:
        acc[: w.shape[0], : w.shape[1]] += w
    return acc / len(words) >= 0.5


def build(map_name: str = HOME_MAP) -> int:
    """A template per species from the packet-labelled cuts."""
    import ro_agent as r

    by = labelled_words(map_name)
    tpl = {sp: template_of(v) for sp, v in by.items()}
    np.savez(map_dir(r.ROOT, map_name) / "templates.npz", **tpl)
    print(json.dumps({sp: len(v) for sp, v in by.items()}))
    return 0


def check(map_name: str = HOME_MAP) -> int:
    """Leave one out: each labelled word matched against templates built without it."""
    by = labelled_words(map_name)
    conf: dict[str, dict[str, int]] = {}
    for sp, words in by.items():
        for k, w in enumerate(words):
            tpl = {s2: template_of([x for j2, x in enumerate(v) if not (s2 == sp and j2 == k)])
                   for s2, v in by.items() if len(v) - (1 if s2 == sp else 0) > 0}  # fmt: skip
            m = np.zeros((w.shape[0] + 10, w.shape[1] + 10), bool)
            m[5 : 5 + w.shape[0], 5 : 5 + w.shape[1]] = w
            name, _iou = match(m, tpl)
            conf.setdefault(sp, {})
            conf[sp][str(name)] = conf[sp].get(str(name), 0) + 1
    print(json.dumps(conf))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--minutes", type=float, default=6.0)
    c.add_argument("--warp", type=int, nargs=2, default=None)
    for sp_ in (c, sub.add_parser("build"), sub.add_parser("check")):
        sp_.add_argument("--map", default=HOME_MAP)
    a = ap.parse_args()
    if a.cmd == "cut":
        return cut(a.minutes, tuple(a.warp) if a.warp else None, a.map)
    if a.cmd == "check":
        return check(a.map)
    return build(a.map)


if __name__ == "__main__":
    sys.exit(main())
