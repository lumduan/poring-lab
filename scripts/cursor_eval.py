#!/usr/bin/env python3
"""OFFLINE evaluation of the cursor classifiers (docs/planning/cursor-robust.md): the gate's
walk6.CursorRefs.match ("current") and cursor_robust.RobustRefs.match ("robust"), on the SAME
perturbed reads, leave-one-out. Nothing here touches the client.

    cursor_eval.py audit    [--refs V3]                        the references' quality
    cursor_eval.py floors   [--refs V3] [--raw DIR]           LOO class scores -> floors / margins
    cursor_eval.py perturb  [--refs V3] [--raw DIR] [--out DIR] [--walk-sample N] [--seed S]
                            [--only "COND;COND..."] [--neighbours K]
    cursor_eval.py table    OUT/summary.json                    markdown tables (both classifiers)
    cursor_eval.py report   [--out DIR]                        pooled groups + why unknown
    cursor_eval.py replay   --labels LABELS.json [--refs V3]   banked crops (a + b or mask)
    cursor_eval.py live     SESSION [--labels L.json]          a live probe session, both, offline
    cursor_eval.py sheet    SESSION [--out DIR] [--verdict S]  labelling sheets (/dev/shm)

The reads are built from the references' OWN calibration hovers (client pixels, /dev/shm only):
- each reference's raw parked background B (walk5-cal/shapes-*/NNN-B.npy, cursor-diag-npc/*.npz
  "b" + "anim", walk6-cal/pickup2/sweep/NNN.npz "b") gives the cursor's own pixels, the SPRITE:
  |A - B| > SPRITE_DIFF, minus the green chevrons, trimmed to the class consensus (what moved
  behind the cursor is not the cursor);
- the sprite is composited (moved by an integer or sub-pixel shift) over its own B or over a
  background PATCH cut from a banked frame (PATCHES: grass, stone, a Poring, an NPC, UI), then
  both A and B pass the same codec-like perturbation (Gaussian blur, JPEG, per-channel noise,
  each image independently), and the mask is Prober9's: walk6.cursor_mask(A, B with the animated
  pixels taken from A);
- "bob" conditions animate a Poring between the two parked frames and the hover (Prober9's
  ANIM_S exclusion) by moving its pixels 1-2 px.
Leave-one-out: the probe's own reference is excluded from both classifiers (``--neighbours K``
also excludes the K hovers before and after it in the same calibration sweep).
Outputs (JSONL + summary JSON) go to --out (default /dev/shm/poring-lab-tmp/cursor-eval).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cursor_robust as cr  # noqa: E402

RAW = Path("/dev/shm/poring-lab-tmp")  # the calibration hovers (client pixels, /dev/shm only)
DEMO = Path("/dev/shm/poring-lab-demo")
OUT = RAW / "cursor-eval"
SPRITE_DIFF = 30  # |A - B| summed over the channels: the cursor's own pixels (walk6 uses 60)
SEED = 20261009
SHAPES = ("walk", "talk", "sword", "pickup", "noentry", "warp")
# Background patches: (frame, hotspot x, y) in client pixels of banked frames (the frames stay in
# /dev/shm; only these coordinates are in git). Session ids as docs/demonstrations.md cites them.
_OUT_F = "20261009T111132-demo-walk16-alone-crowd-outdoor/snapshots/000-route-before.png"
_IN_F = "20261009T093115-demo-walk16-alone-crowd-indoor/snapshots/000-route-before.png"
_TOWN_F = "20261009T140625-demo-walk15-heldout-a-clean-town/snapshots/048-route-before.png"
_DUN_F = "20261009T123810-demo-walk15-heldout-clean-dungeon/snapshots/000-route-before.png"
_NPC_F = "20261009T154531-demo-talk-cal-garnet/frames/0000-277195532533507.png"
PATCHES: dict[str, tuple[str, int, int]] = {
    "grass": (_OUT_F, 900, 500),
    "green_grass": (_OUT_F, 1150, 220),
    "poring_body": (_OUT_F, 575, 282),
    "poring_feet": (_OUT_F, 575, 292),
    "church_floor": (_IN_F, 900, 620),
    "church_carpet": (_IN_F, 760, 300),
    "church_pew": (_IN_F, 450, 450),
    "poring_church": (_IN_F, 723, 412),
    "npc_church": (_NPC_F, 750, 370),
    "town_stone": (_TOWN_F, 1000, 520),
    "town_flag": (_TOWN_F, 420, 330),
    "npc_town": (_TOWN_F, 390, 450),
    "dungeon": (_DUN_F, 1000, 480),
    "ui_window": (_OUT_F, 100, 40),
    "ui_chat": (_OUT_F, 150, 575),
    "ui_skills": (_OUT_F, 80, 200),
}
# the Porings for "bob": the patch, and a plain patch of the same floor to put under it
BOB = {"poring_body": "grass", "poring_feet": "grass", "poring_church": "church_floor"}


# --- the calibration hovers ----------------------------------------------------------------------


@dataclass
class Source:
    a: Any  # (64, 64, 3) uint8 BGR, the hover crop
    b: Any  # the parked background
    anim: Any  # animated pixels (cursor_diag's npc hovers) or None
    cls: str
    src: str


def load_sources(refs_path: Path, raw: Path = RAW) -> tuple[list[Source], Any]:
    z = np.load(refs_path)
    out = []
    for a, c, s in zip(z["a"], z["cls"], z["src"], strict=True):
        kind, k = str(s).split("/", 1)
        anim = None
        if kind in ("outdoor", "indoor"):
            d = raw / f"walk5-cal/shapes-{kind}"
            b = np.load(d / f"{int(k):03d}-B.npy")[..., :3]
            araw = np.load(d / f"{int(k):03d}-A.npy")[..., :3]
        elif kind == "npc":
            n = np.load(raw / "cursor-diag-npc" / k)
            araw, b, anim = n["a"], n["b"], n["anim"]
        elif kind == "pickup2":
            n = np.load(raw / f"walk6-cal/pickup2/sweep/{int(k):03d}.npz")
            araw, b = n["a"][28:92, 28:92], n["b"]
        else:
            raise ValueError(f"unknown reference source {s}")
        if not np.array_equal(araw, a):
            raise ValueError(f"{s}: the raw hover differs from the reference")
        out.append(Source(np.asarray(a), np.asarray(b)[..., :3], anim, str(c), str(s)))
    return out, z["m"]


def green(c: Any) -> Any:
    """walk6.green (the chevrons' pale green, BGR), without importing the rule stack."""
    b, g, r = (c[..., i].astype(int) for i in range(3))
    return (g - r > 50) & (g - b > 35) & (r > 60) & (b > 60) & (g > 150)


def sprites(srcs: Sequence[Source], masks: Any) -> list[tuple[Any, Any]]:
    """(alpha, colour) per reference: its own pixels against its raw parked background, trimmed
    to its class's consensus (cursor_robust.FREQ_MIN)."""
    cls = [s.cls for s in srcs]
    freq: dict[str, Any] = {}
    for c in set(cls):
        idx = [i for i, x in enumerate(cls) if x == c]
        freq[c] = np.asarray(masks)[idx].mean(0)
    out = []
    for s in srcs:
        d = np.abs(s.a.astype(int) - s.b.astype(int)).sum(-1) > SPRITE_DIFF
        alpha = d & ~green(s.a) & (freq[s.cls] >= cr.FREQ_MIN)
        out.append((alpha, s.a))
    return out


def load_patches(demo: Path = DEMO) -> dict[str, Any]:
    from PIL import Image

    frames: dict[str, Any] = {}
    out = {}
    for name, (f, x, y) in PATCHES.items():
        if f not in frames:
            frames[f] = np.asarray(Image.open(demo / f).convert("RGB"))[..., ::-1]  # BGR
        out[name] = np.ascontiguousarray(frames[f][y - 32 : y + 32, x - 32 : x + 32])
    return out


# --- perturbations (pure) -------------------------------------------------------------------------


def shift_int(x: Any, dx: int, dy: int) -> Any:
    """Move the content by (dx, dy), zero fill."""
    out = np.zeros_like(x)
    h, w = x.shape[:2]
    out[max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)] = x[
        max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)
    ]
    return out


def composite(alpha: Any, colour: Any, bg: Any, dx: float = 0.0, dy: float = 0.0) -> Any:
    """The sprite drawn over ``bg``, moved by (dx, dy); a fractional move is bilinear (an edge
    pixel blends sprite and background, as a resampling pass would)."""
    ix, iy = int(np.floor(dx)), int(np.floor(dy))
    fx, fy = dx - ix, dy - iy
    al = alpha.astype(float)
    pre = colour.astype(float) * al[..., None]
    al, pre = shift_int(al, ix, iy), shift_int(pre, ix, iy)
    if fx:
        al = (1 - fx) * al + fx * shift_int(al, 1, 0)
        pre = (1 - fx) * pre + fx * shift_int(pre, 1, 0)
    if fy:
        al = (1 - fy) * al + fy * shift_int(al, 0, 1)
        pre = (1 - fy) * pre + fy * shift_int(pre, 0, 1)
    out = bg.astype(float) * (1 - al[..., None]) + pre
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def blur(img: Any, sigma: float) -> Any:
    rad = max(1, int(np.ceil(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
    k /= k.sum()
    x = img.astype(float)
    for ax in (0, 1):
        p = np.pad(x, [(rad, rad) if a == ax else (0, 0) for a in range(3)], mode="reflect")
        x = sum(k[i] * np.take(p, range(i, i + x.shape[ax]), axis=ax) for i in range(len(k)))
    return np.clip(np.rint(x), 0, 255).astype(np.uint8)


def jpeg(img: Any, q: int) -> Any:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(img[..., ::-1])).save(buf, "JPEG", quality=q)
    return np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))[..., ::-1].copy()


def noise(img: Any, sd: float, rng: Any) -> Any:
    return np.clip(np.rint(img + rng.normal(0, sd, img.shape)), 0, 255).astype(np.uint8)


def poring_pixels(patch: Any) -> Any:
    """A Poring's pink body (BGR) grown by 1 px for its outline."""
    b, g, r = (patch[..., i].astype(int) for i in range(3))
    return cr._dilate8((r > 200) & (r - g > 50) & (b - g > -10) & (b > 110))


def bob_frames(patch: Any, floor: Any, amp: int) -> tuple[Any, Any, Any]:
    """Two parked frames and the hover's background with the Poring moved by 0, amp, -amp px
    (its pixels over a plain patch of the same floor): B1, B2, A's background."""
    pm = poring_pixels(patch)

    def at(dy: int) -> Any:
        m = shift_int(pm, 0, dy)
        return np.where(m[..., None], shift_int(patch, 0, dy), floor)

    return at(0), at(amp), at(-amp)


# --- the conditions -------------------------------------------------------------------------------


def conditions() -> dict[str, dict[str, Any]]:
    """Every perturbation: {name: spec}. The spec keys: bg ("own" or a patch), shift, codec
    (blur / jpeg / noise), bob (patch, amp)."""
    c: dict[str, dict[str, Any]] = {"stored": {"stored": True}, "own": {"bg": "own"}}
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (2, 0), (0, 2),
                   (-2, 0), (0, -2)):  # fmt: skip
        c[f"shift{dx:+d},{dy:+d}"] = {"bg": "own", "shift": (dx, dy)}
    for dx, dy in ((0.5, 0.0), (0.0, 0.5), (0.5, 0.5)):
        c[f"subpx{dx},{dy}"] = {"bg": "own", "shift": (dx, dy)}
    for s in (0.5, 0.8, 1.2):
        c[f"blur{s}"] = {"bg": "own", "codec": ("blur", s)}
    for q in (90, 70, 50):
        c[f"jpeg{q}"] = {"bg": "own", "codec": ("jpeg", q)}
    for sd in (5, 10, 20, 30):
        c[f"noise{sd}"] = {"bg": "own", "codec": ("noise", sd)}
    for p in PATCHES:
        c[f"bg:{p}"] = {"bg": p}
        c[f"bg:{p}+jpeg80"] = {"bg": p, "codec": ("jpeg", 80)}
    for p in ("grass", "town_stone", "poring_body", "npc_church", "church_floor"):
        c[f"bg:{p}+shift+1,+0"] = {"bg": p, "shift": (1, 0)}
        c[f"bg:{p}+blur0.8"] = {"bg": p, "codec": ("blur", 0.8)}
    for p in BOB:
        for amp in (1, 2):
            c[f"bob:{p}:{amp}"] = {"bg": p, "bob": amp}
    return c


def make_read(spec: dict[str, Any], src: Source, sprite: tuple[Any, Any], ref_mask: Any,
              patches: dict[str, Any], rng: Any) -> tuple[Any, Any]:  # fmt: skip
    """(A, mask) as Prober9 would see them."""
    import walk6 as w6

    if spec.get("stored"):
        return src.a, ref_mask
    alpha, colour = sprite
    anim = src.anim if spec["bg"] == "own" else None
    if spec.get("bob"):
        b1, b2, abg = bob_frames(patches[spec["bg"]], patches[BOB[spec["bg"]]], spec["bob"])
        bg, b = abg, b2
        anim = np.abs(b1.astype(int) - b2.astype(int)).sum(-1) > 60  # walk10.ANIM_DIFF
    else:
        bg = src.b if spec["bg"] == "own" else patches[spec["bg"]]
        b = bg
    dx, dy = spec.get("shift", (0, 0))
    a = composite(alpha, colour, bg, dx, dy)
    codec = spec.get("codec")
    if codec:
        kind, v = codec
        if kind == "blur":
            a, b = blur(a, v), blur(b, v)
        elif kind == "jpeg":
            a, b = jpeg(a, v), jpeg(b, v)
        else:
            a, b = noise(a, v, rng), noise(b, v, rng)
    b_mod = np.where(anim[..., None], a, b) if anim is not None else b
    return a, w6.cursor_mask(a, b_mod)


# --- the classifiers ------------------------------------------------------------------------------


class Current:
    """walk6.CursorRefs.match, leave-one-out, plus the REAL colour of the best-IoU reference and
    the best colour among the references with IoU >= MIN_IOU (walk6 reports col 0.0 for every
    unknown: a placeholder)."""

    def __init__(self, refs_path: Path) -> None:
        import walk6 as w6

        z = np.load(refs_path)
        self.w6 = w6
        self.a, self.m, self.cls = z["a"], z["m"], [str(c) for c in z["cls"]]
        self._key: tuple[int, ...] | None = None
        self._refs: Any = None

    def refs(self, exclude: Sequence[int]) -> Any:
        key = tuple(sorted(exclude))
        if key != self._key:
            keep = np.ones(len(self.cls), bool)
            keep[list(key)] = False
            self._refs = self.w6.CursorRefs(
                self.a[keep], self.m[keep], [c for c, k in zip(self.cls, keep, strict=True) if k]
            )
            self._key = key
        return self._refs

    def match(self, a: Any, mask: Any, exclude: Sequence[int] = ()) -> dict[str, Any]:
        refs = self.refs(exclude)
        out = dict(refs.match(a, mask))
        m = np.asarray(mask, dtype=bool)
        if m.sum():
            inter = (refs.m & m).reshape(len(refs.cls), -1).sum(1)
            union = (refs.m | m).reshape(len(refs.cls), -1).sum(1)
            iou = inter / np.maximum(union, 1)
            a16 = np.asarray(a)[..., :3].astype(np.int16)
            j = int(np.argmax(iou))
            cand = sorted({j, *(int(k) for k in np.nonzero(iou >= self.w6.MIN_IOU)[0])})
            ov = refs.m[cand] & m[None]
            ok = (np.abs(a16[None] - refs.a[cand]).max(-1) < self.w6.COL_TOL) & ov
            col = ok.reshape(len(cand), -1).sum(1) / np.maximum(ov.reshape(len(cand), -1).sum(1), 1)
            out["best"] = [
                refs.cls[j],
                round(float(iou[j]), 3),
                round(float(col[cand.index(j)]), 3),
            ]
            shape_ok = [float(c) for k, c in zip(cand, col, strict=True)
                        if iou[k] >= self.w6.MIN_IOU]  # fmt: skip
            out["best_col"] = round(max(shape_ok, default=0.0), 3)
        return out


def neighbours(srcs: Sequence[Source], i: int, k: int) -> list[int]:
    """The probe and the k hovers before / after it in its calibration sweep."""
    kind, idx = srcs[i].src.split("/", 1)
    if k <= 0 or not idx.isdigit():
        return [i]
    want = {f"{kind}/{int(idx) + d}" for d in range(-k, k + 1)}
    return [j for j, s in enumerate(srcs) if s.src in want]


def probes(srcs: Sequence[Source], robust: cr.RobustRefs, walk_n: int, seed: int) -> list[int]:
    """Every non-walk reference the robust classifier keeps (a dropped one is no cursor), and a
    seeded sample of the walk references."""
    rng = np.random.default_rng(seed)
    walk = [i for i, s in enumerate(srcs) if s.cls == "walk"]
    pick = sorted(rng.choice(walk, size=min(walk_n, len(walk)), replace=False).tolist())
    keep = set(robust.ref.tolist())
    return sorted([i for i, s in enumerate(srcs) if s.cls != "walk" and i in keep] + pick)


# --- commands -------------------------------------------------------------------------------------


def cmd_floors(args: argparse.Namespace) -> dict[str, Any]:
    """Leave-one-out on the STORED references (no perturbation): every class's exact score for
    every reference, the floor that keeps every other class's probes below it, and the margin
    distribution. This sets cursor_robust.FLOORS / MARGINS BEFORE any perturbation is scored."""
    z = np.load(args.refs)
    a, m, cls = z["a"], z["m"], [str(c) for c in z["cls"]]
    robust = cr.RobustRefs.load(args.refs)
    rows = []
    for i in robust.ref.tolist():
        rows.append({"i": i, "cls": cls[i], "per": robust.class_scores(a[i], m[i], exclude=[i])})
    out: dict[str, Any] = {
        "probes": len(rows),
        "dropped": [str(z["src"][i]) for i in robust.dropped],
    }
    for c in robust.classes:
        own = np.array([r["per"][c][0] for r in rows if r["cls"] == c])
        lead_o = np.array([r["per"][c][0] for r in rows if r["cls"] != c])
        comp_o = np.array([r["per"][c][1] for r in rows if r["cls"] != c])
        gap = np.array([r["per"][c][0] - max(v[1] for k, v in r["per"].items() if k != c)
                        for r in rows if r["cls"] == c])  # fmt: skip
        out[c] = {"n": len(own), "own_min": round(float(own.min()), 3),
                  "own_p05": round(float(np.percentile(own, 5)), 3),
                  "own_median": round(float(np.median(own)), 3),
                  "other_lead_max": round(float(lead_o.max()), 3),
                  "other_comp_max": round(float(comp_o.max()), 3),
                  "gap_min": round(float(gap.min()), 3),
                  "gap_p05": round(float(np.percentile(gap, 5)), 3),
                  "below_floor": int((own < cr.FLOORS.get(c, cr.DEFAULT_FLOOR)).sum()),
                  "gap_below_margin": int((gap < cr.MARGINS.get(c, cr.DEFAULT_MARGIN)).sum()),
                  }  # fmt: skip
        worst = max((r for r in rows if r["cls"] != c), key=lambda r: r["per"][c][0])
        out[c]["other_lead_max_from"] = [worst["cls"], str(z["src"][worst["i"]])]
    return out


def cmd_audit(args: argparse.Namespace) -> dict[str, Any]:
    """The references' quality: per class, the masks that the class consensus trims by more than
    30 % (something that moved behind the cursor, or a stale parked frame) or that are under a
    quarter of the class's median size (a fragment), each with the OTHER class whose core region
    it overlaps most (a stale no-entry sign under a walk label looks like "noentry")."""
    z = np.load(args.refs)
    m, cls, src = z["m"], [str(c) for c in z["cls"]], [str(s) for s in z["src"]]
    sup = cr.consensus_supports(m, cls)
    region = {c: np.asarray(m)[[i for i, x in enumerate(cls) if x == c]].mean(0) >= 0.5
              for c in set(cls)}  # fmt: skip
    out: dict[str, Any] = {}
    for c in sorted(set(cls)):
        idx = [i for i, x in enumerate(cls) if x == c]
        med = float(np.median([m[i].sum() for i in idx]))
        rows = []
        for i in idx:
            kept = float(sup[i].sum()) / max(int(m[i].sum()), 1)
            like = {o: float((m[i] & region[o]).sum()) / max(int((m[i] | region[o]).sum()), 1)
                    for o in region if o != c}  # fmt: skip
            o_best = max(like, key=lambda o: like[o])
            if kept < 0.7 or m[i].sum() < 0.25 * med:
                rows.append({"src": src[i], "mask_px": int(m[i].sum()), "kept": round(kept, 3),
                             "looks_like": [o_best, round(like[o_best], 3)]})  # fmt: skip
        out[c] = {"n": len(idx), "flagged": len(rows), "rows": rows}
    return out


def cmd_perturb(args: argparse.Namespace) -> dict[str, Any]:
    srcs, masks = load_sources(args.refs, args.raw)
    spr = sprites(srcs, masks)
    patches = load_patches(args.demo)
    robust = cr.RobustRefs.load(args.refs)
    current = Current(args.refs)
    conds = conditions()
    if args.only:  # ";"-separated: condition names contain commas
        conds = {k: v for k, v in conds.items() if k in set(args.only.split(";"))}
    plist = probes(srcs, robust, args.walk_sample, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    log = (args.out / "reads.jsonl").open("w")
    summ: dict[str, dict[str, dict[str, Counter[str]]]] = {
        "current": defaultdict(lambda: defaultdict(Counter)),
        "robust": defaultdict(lambda: defaultdict(Counter)),
    }
    t_rob: list[float] = []
    t0 = time.time()
    for n, i in enumerate(plist):
        ex = neighbours(srcs, i, args.neighbours)
        for k, (name, spec) in enumerate(conds.items()):
            rng = np.random.default_rng([args.seed, i, k])
            a, mask = make_read(spec, srcs[i], spr[i], masks[i], patches, rng)
            cur = current.match(a, mask, ex)
            t = time.perf_counter()
            rob = robust.match(a, mask, ex)
            t_rob.append(time.perf_counter() - t)
            summ["current"][name][srcs[i].cls][cur["shape"]] += 1
            summ["robust"][name][srcs[i].cls][rob["shape"]] += 1
            log.write(json.dumps({"i": i, "src": srcs[i].src, "cls": srcs[i].cls, "cond": name,
                                  "mask_px": int(np.asarray(mask).sum()), "current": cur,
                                  "robust": rob}) + "\n")  # fmt: skip
        if n % 25 == 0:
            print(f"{n}/{len(plist)} probes, {time.time() - t0:.0f} s", file=sys.stderr)
    log.close()
    res = {"probes": len(plist), "per_class": dict(Counter(srcs[i].cls for i in plist)),
           "neighbours": args.neighbours, "conditions": list(conds),
           "robust_ms": {"median": round(1000 * float(np.median(t_rob)), 2),
                         "p95": round(1000 * float(np.percentile(t_rob, 95)), 2)},
           "summary": {c: {k: {s: dict(v) for s, v in d.items()} for k, d in x.items()}
                       for c, x in summ.items()}}  # fmt: skip
    (args.out / "summary.json").write_text(json.dumps(res, indent=1))
    return {k: v for k, v in res.items() if k != "summary"}


def wrong(counts: dict[str, int], true: str) -> int:
    return sum(v for k, v in counts.items() if k not in (true, "unknown"))


def table(summary: dict[str, Any], conds: Sequence[str] | None = None) -> str:
    """Per condition: per shape 'read / unknown / WRONG' for current | robust, and the
    cross-shape errors spelled out (true->read xN)."""
    s = summary["summary"]
    names = conds or summary["conditions"]
    shapes = [c for c in SHAPES if any(c in s["current"][n] for n in names)]
    head = "| condition | " + " | ".join(shapes) + " | cross-shape errors (current ; robust) |"
    lines = [head, "|" + "---|" * (len(shapes) + 2)]
    for n in names:
        cells = []
        errs: dict[str, list[str]] = {"current": [], "robust": []}
        for c in shapes:
            parts = []
            for clf in ("current", "robust"):
                d = s[clf][n].get(c, {})
                tot = sum(d.values())
                if not tot:
                    parts.append("-")
                    continue
                parts.append(f"{d.get(c, 0)}/{d.get('unknown', 0)}/{wrong(d, c)}")
                errs[clf] += [f"{c}->{k} x{v}" for k, v in d.items() if k not in (c, "unknown")]
            cells.append(" \\| ".join(parts))
        e = "; ".join(", ".join(errs[k]) or "0" for k in ("current", "robust"))
        lines.append(f"| {n} | " + " | ".join(cells) + f" | {e} |")
    return "\n".join(lines)


def totals(summary: dict[str, Any], conds: Sequence[str]) -> dict[str, Any]:
    """Pooled over ``conds``: per classifier and shape, read / unknown / wrong, and WALK-from-X."""
    out: dict[str, Any] = {}
    for clf in ("current", "robust"):
        t: dict[str, Counter[str]] = defaultdict(Counter)
        for n in conds:
            for c, d in summary["summary"][clf][n].items():
                t[c].update(d)
        out[clf] = {c: {"n": sum(d.values()), "read": d.get(c, 0), "unknown": d.get("unknown", 0),
                        "wrong": wrong(d, c), "walk_from": d.get("walk", 0) if c != "walk" else 0}
                    for c, d in t.items()}  # fmt: skip
    return out


GROUPS: dict[str, Callable[[str], bool]] = {
    "stored (pure LOO)": lambda n: n == "stored",
    "own background": lambda n: n == "own",
    "integer shift 1-2 px": lambda n: n.startswith("shift"),
    "sub-pixel shift": lambda n: n.startswith("subpx"),
    "blur 0.5-1.2": lambda n: n.startswith("blur"),
    "jpeg 90-50": lambda n: n.startswith("jpeg"),
    "noise sd 5-20": lambda n: n in ("noise5", "noise10", "noise20"),
    "noise sd 30": lambda n: n == "noise30",
    "other backgrounds": lambda n: n.startswith("bg:") and "+" not in n,
    "other backgrounds + jpeg80": lambda n: n.startswith("bg:") and n.endswith("+jpeg80"),
    "background + 1 px / blur": lambda n: n.startswith("bg:") and ("+shift" in n or "+blur" in n),
    "animated Poring (bob)": lambda n: n.startswith("bob:"),
}


def reasons(reads: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Why each classifier said UNKNOWN. current: no_cursor / shape (best IoU < MIN_IOU) /
    colour (IoU >= MIN_IOU, the best colour among those < MIN_COL: the REAL colour, not the
    0.0 placeholder) with the median real colour; robust: its own ``why``."""
    cur: Counter[str] = Counter()
    rob: Counter[str] = Counter()
    cols: list[float] = []
    for r in reads:
        c = r["current"]
        if c["shape"] == "unknown":
            if c.get("why") == "no_cursor":
                cur["no_cursor"] += 1
            elif c.get("best", [None, 0.0])[1] < 0.6:
                cur["shape(iou<0.6)"] += 1
            else:
                cur["colour(iou>=0.6)"] += 1
                cols.append(c.get("best_col", 0.0))
        w = r["robust"]
        if w["shape"] == "unknown":
            rob[w.get("why", "?").split(":")[0]] += 1
    return {"current": dict(cur), "current_colour_median": round(float(np.median(cols)), 3)
            if cols else None, "robust": dict(rob)}  # fmt: skip


def cmd_report(args: argparse.Namespace) -> dict[str, Any]:
    """Pooled per GROUP of conditions: per shape read / unknown / wrong for both classifiers,
    the cross-shape errors, WALK-from-X, and why each said unknown."""
    reads = [json.loads(x) for x in (args.out / "reads.jsonl").read_text().splitlines()]
    out: dict[str, Any] = {}
    for g, f in GROUPS.items():
        rs = [r for r in reads if f(r["cond"])]
        if not rs:
            continue
        row: dict[str, Any] = {"reads": len(rs)}
        for clf in ("current", "robust"):
            t: dict[str, Counter[str]] = defaultdict(Counter)
            for r in rs:
                t[r["cls"]][r[clf]["shape"]] += 1
            row[clf] = {c: f"{d.get(c, 0)}/{d.get('unknown', 0)}/{wrong(d, c)} of {sum(d.values())}"
                        for c, d in sorted(t.items())}  # fmt: skip
            row[clf + "_errors"] = sorted(
                f"{r['cls']}->{r[clf]['shape']} {r['src']} {r['cond']}"
                for r in rs
                if r[clf]["shape"] not in (r["cls"], "unknown")
            )
        row["why_unknown"] = reasons(rs)
        out[g] = row
    return out


def cmd_replay(args: argparse.Namespace) -> dict[str, Any]:
    """Banked crops with by-eye labels: {"path": "shape", ...} (crop npz: a (64 or 120 px) + b
    or mask, and anim when present). No leave-one-out: these crops are not references."""
    import walk6 as w6

    labels = json.loads(Path(args.labels).read_text())
    robust = cr.RobustRefs.load(args.refs)
    current = Current(args.refs)
    rows = []
    for p, want in labels.items():
        z = np.load(p)
        a = z["a"][28:92, 28:92] if z["a"].shape[0] == 120 else z["a"]
        if "mask" in z.files:
            mask = z["mask"]
        else:
            b = z["b"]
            mask = w6.cursor_mask(a, np.where(z["anim"][..., None], a, b) if "anim" in z.files
                                  else b)  # fmt: skip
        rows.append({"npz": p, "label": want, "current": current.match(a, mask),
                     "robust": robust.match(a, mask)})  # fmt: skip
    res: dict[str, Any] = {"crops": len(rows)}
    for clf in ("current", "robust"):
        t: dict[str, Counter[str]] = defaultdict(Counter)
        for r in rows:
            t[r["label"]][r[clf]["shape"]] += 1
        res[clf] = {k: dict(v) for k, v in t.items()}
    res["rows"] = rows
    return res


def series_verdicts(shapes: Sequence[str], grabs: int = 3) -> tuple[str, str]:
    """Prober9's two reads from a 6-grab series: each the first non-unknown shape of its ``grabs``
    grabs (the hover read: grabs 0-2; the no-motion re-read: grabs 3-5)."""
    first = next((s for s in shapes[:grabs] if s != "unknown"), "unknown")
    again = next((s for s in shapes[grabs : 2 * grabs] if s != "unknown"), "unknown")
    return first, again


def cmd_live(args: argparse.Namespace) -> dict[str, Any]:
    """A LIVE session's saved crops (npc_click_test.py probe, cursor_probe.py sword): both
    classifiers on every grab of every series, offline. Per probe kind: the first read's shape
    and "read twice" (the gate's click condition) for each classifier; with --labels
    ({crop: shape}, by eye, blind), the cross-shape errors."""
    ses = Path(args.summary)
    recs = [json.loads(x) for x in (ses / "demo.jsonl").read_text().splitlines() if x.strip()]
    labels = json.loads(Path(args.labels).read_text()) if args.labels else {}
    robust = cr.RobustRefs.load(args.refs)
    current = Current(args.refs)
    rows = []
    for rec in recs:
        ev = (rec.get("outcome") or {}).get("evidence") or {}
        if "crop" not in ev:
            continue
        z = np.load(ses / ev["crop"])
        out: dict[str, Any] = {"crop": ev["crop"], "kind": ev.get("kind", "?"),
                               "label": labels.get(ev["crop"])}  # fmt: skip
        for name, clf in (("current", current), ("robust", robust)):
            shapes = [clf.match(a, m)["shape"] for a, m in
                      zip(z["a_series"], z["mask_series"], strict=True)]  # fmt: skip
            first, again = series_verdicts(shapes)
            out[name] = {"shapes": shapes, "first": first, "twice": first if first == again
                         else "unknown"}  # fmt: skip
        rows.append(out)
    res: dict[str, Any] = {"session": ses.name, "probes": len(rows)}
    for name in ("current", "robust"):
        by: dict[str, Counter[str]] = defaultdict(Counter)
        twice: dict[str, Counter[str]] = defaultdict(Counter)
        for r in rows:
            by[r["kind"]][r[name]["first"]] += 1
            twice[r["kind"]][r[name]["twice"]] += 1
        res[name] = {"first": {k: dict(v) for k, v in by.items()},
                     "twice": {k: dict(v) for k, v in twice.items()}}  # fmt: skip
        lab = [r for r in rows if r["label"]]
        res[name]["labelled"] = len(lab)
        res[name]["cross_shape"] = sorted(
            f"{r['label']}->{r[name]['first']} {r['crop']}" for r in lab
            if r[name]["first"] not in (r["label"], "unknown"))  # fmt: skip
        res[name]["walk_from_other"] = sum(
            1
            for r in lab
            if r["label"] != "walk" and "walk" in (r[name]["first"], r[name]["twice"])
        )
    (args.out / f"live-{ses.name}.json").parent.mkdir(parents=True, exist_ok=True)
    (args.out / f"live-{ses.name}.json").write_text(json.dumps({**res, "rows": rows}))
    return res


def cmd_sheet(args: argparse.Namespace) -> dict[str, Any]:
    """Labelling sheets for a live session: the first grab of each crop, 2x, 10 per row, 50 a
    page, NO classifier output on them. Every crop (blind), or with --verdict SHAPE only the
    crops whose ROBUST first read is SHAPE (from cursor_eval.py live's JSON in --out): a page
    that claims one shape, to flag the odd one out (the safety check). PNGs + the crop order in
    --out (/dev/shm: client pixels)."""
    from PIL import Image

    ses = Path(args.summary)
    names = sorted(f"crops/{p.name}" for p in (ses / "crops").glob("*.npz"))
    tag = "all"
    if args.verdict:
        live = json.loads((args.out / f"live-{ses.name}.json").read_text())
        want = {r["crop"] for r in live["rows"] if r["robust"]["first"] == args.verdict}
        names = [n for n in names if n in want]
        tag = args.verdict
    args.out.mkdir(parents=True, exist_ok=True)
    pages = []
    for k in range(0, len(names), 50):
        tiles = [np.load(ses / n)["a"][..., ::-1] for n in names[k : k + 50]]
        while len(tiles) % 10:
            tiles.append(np.zeros((64, 64, 3), np.uint8))
        rows = [np.concatenate(tiles[i : i + 10], 1) for i in range(0, len(tiles), 10)]
        page = args.out / f"sheet-{ses.name}-{tag}-{k // 50:03d}.png"
        img = np.concatenate(rows, 0)
        Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(page)
        pages.append(str(page))
    order = args.out / f"sheet-{ses.name}-{tag}.json"
    order.write_text(json.dumps(names))
    return {"crops": len(names), "pages": pages, "order": str(order)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "cmd", choices=("audit", "floors", "perturb", "table", "replay", "report", "live", "sheet")
    )
    ap.add_argument("summary", nargs="?", type=Path, help="summary.json (table) or SESSION dir")
    ap.add_argument("--refs", type=Path, default=cr.REFS_V3)
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--demo", type=Path, default=DEMO)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--walk-sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--only", default="")
    ap.add_argument("--neighbours", type=int, default=0)
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--verdict", default="", help="sheet: only the robust reader's SHAPE reads")
    args = ap.parse_args()
    fn: dict[str, Callable[[argparse.Namespace], Any]] = {
        "audit": cmd_audit, "floors": cmd_floors, "perturb": cmd_perturb, "replay": cmd_replay,
        "report": cmd_report, "live": cmd_live, "sheet": cmd_sheet}  # fmt: skip
    if args.cmd == "table":
        print(table(json.loads(Path(args.summary).read_text())))
        return 0
    print(json.dumps(fn[args.cmd](args), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
