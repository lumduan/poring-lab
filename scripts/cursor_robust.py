#!/usr/bin/env python3
"""A ROBUST cursor classifier behind walk6.CursorRefs' interface (Batt 2026-10-09 ~19:30: "the
cursor-classifier robustness work is a priority"). OFFLINE CANDIDATE: nothing imports it by
default; the gate switches only by an explicit flag (docs/planning/cursor-robust.md section 6).

walk6.CursorRefs.match (the gate today) asks two things of the observed cursor mask D (|A - B| on
the hotspot's component, animated pixels removed): its IoU with a reference mask at ONE position
(>= 0.6), then the colour on the overlap (>= 0.85 of the pixels within 40). Both depend on things
that are not the cursor:
- the mask depends on the BACKGROUND (a white bubble on a light floor loses its fill: hollow) and
  on the ANIMATION exclusion (the cursor's pixels over a bobbing Poring are removed from D);
- the colour is compared on the overlap at a fixed registration, so a 1-px offset puts outline
  on fill and fails it (docs/planning/npc-click-test.md section 3).

This classifier separates the questions:
1. PROTOTYPES: every reference, its mask trimmed to the CLASS CONSENSUS (pixels that at least
   FREQ_MIN of its class's references share): the Poring outlines and portal swirls that the
   walk@6 calibration baked into SWORD / WARP references are not the cursor; a "reference" with
   nothing left (indoor/100: a sword label on a mask away from the hotspot) is dropped.
2. Per prototype and per shift (dx, dy) in [-R, R]^2 (misregistration):
   - rec  = the share of the prototype's INTERIOR pixels whose colour in the observed crop A is
            within TOL (max channel): the cursor's OWN pixels, read on A, not on D -- the
            background and the mask do not enter;
   - prec = the share of D inside the prototype's support grown by 1 px: TWO-SIDED, extra
            content (the no-entry ring over the arrow, a sprite merged in) lowers it;
   - cov  = the share of the prototype's support present in D: the cursor really changed these
            pixels (not a background that happens to look like it).
   score = min(rec, prec), the best shift.
3. The decision, asymmetric (fail closed): the LEADER s* is the class with the best score among
   the pairs with cov >= COV_MIN; every OTHER class competes with its best score over ALL pairs
   (no coverage needed: a no-entry ring on a background of its own colour leaves only the arrow
   in D, yet its colours are in A). shape = s* only if its score >= FLOORS[s*] AND score - (the
   best competitor) >= MARGINS[s*]. Anything else is UNKNOWN (why: low_score / ambiguous:<class>
   / no_match / no_cursor). WALK carries the strictest margin: a walk click over a unit is the
   unsafe direction.

Fails closed like the gate: UNKNOWN is never a click. Pure numpy; client pixels (the references)
stay in data/ and /dev/shm, never in git.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REFS_V3 = ROOT / "data/walk6/cursor_refs_rdp_v3.npz"  # client pixels: data/, never committed
CROP = 64  # walk6's crop: 64 x 64, the hotspot at (32, 32)
R = 2  # shift search radius, px (a 1-px offset reproduced the live TALK failure; 2 for margin)
TOL = 40  # colour tolerance, max channel (walk6.COL_TOL)
FREQ_MIN = 0.15  # a reference pixel is the cursor's if >= this share of its class has it
MIN_PX = 12  # walk6.MIN_CURSOR_PX: fewer observed (or prototype) pixels = no cursor
COV_MIN = 0.25  # at least this share of the prototype's support must be in D
PREC_MIN = 0.5  # stage 2 (the colour) only where prec >= this: below every floor - margin
BATCH = 16  # stage 2 evaluates the candidate pairs in batches of 16, 64, 256, ...
INTERIOR_MIN = 0.25  # a support whose 4-eroded interior is smaller than this share: use it whole
# The decision thresholds, set from `cursor_eval.py floors` (leave-one-out on the 644 kept v3
# references, NO perturbation; 2026-10-09, before any perturbed read was scored): each floor sits
# >= 0.12 above the highest score any OTHER class's reference reached for that class (walk 0.707,
# talk 0.663, sword 0.511, pickup 0.660, noentry 0.457, warp 0.584). The clickable shapes (walk;
# warp for a portal intent) get the widest margins. Every floor - margin >= PREC_MIN (a test).
FLOORS = {"walk": 0.85, "talk": 0.78, "sword": 0.65, "pickup": 0.80, "noentry": 0.70,
          "warp": 0.75}  # fmt: skip
MARGINS = {"walk": 0.25, "talk": 0.15, "sword": 0.15, "pickup": 0.15, "noentry": 0.15,
           "warp": 0.20}  # fmt: skip
DEFAULT_FLOOR, DEFAULT_MARGIN = 0.80, 0.20  # a class not listed above


def _erode4(s: Any) -> Any:
    """4-neighbour erosion; the crop border counts as outside."""
    e = s.copy()
    e[1:, :] &= s[:-1, :]
    e[:-1, :] &= s[1:, :]
    e[:, 1:] &= s[:, :-1]
    e[:, :-1] &= s[:, 1:]
    e[0, :] = e[-1, :] = False
    e[:, 0] = e[:, -1] = False
    return e


def _dilate8(s: Any) -> Any:
    d = s.copy()
    h, w = s.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                d[max(dy, 0) : h + min(dy, 0), max(dx, 0) : w + min(dx, 0)] |= s[
                    max(-dy, 0) : h + min(-dy, 0), max(-dx, 0) : w + min(-dx, 0)
                ]
    return d


def _pack(masks: Any) -> Any:
    """(n, 64, 64) bool -> (n, 64) uint64, bit x of word y = mask[y, x]."""
    m = np.asarray(masks, dtype=bool)
    w = np.uint64(1) << np.arange(CROP, dtype=np.uint64)
    return (m.astype(np.uint64) * w).sum(-1, dtype=np.uint64)


def consensus_supports(m: Any, cls: Sequence[str], freq_min: float = FREQ_MIN) -> Any:
    """Each reference mask trimmed to the pixels that at least ``freq_min`` of its class's
    references share (the cursor is drawn at the hotspot; what moved behind it is not)."""
    m = np.asarray(m, dtype=bool)
    out = np.zeros_like(m)
    labels = np.asarray(cls)
    for c in sorted(set(cls)):
        idx = np.nonzero(labels == c)[0]
        freq = m[idx].mean(0)
        out[idx] = m[idx] & (freq >= freq_min)[None]
    return out


class RobustRefs:
    """The robust classifier. ``match(a, mask)`` returns walk6's dict ("shape", "iou", "col") plus
    "score", "second" (class, score), "margin", "shift", "ref", "why" (for unknown).

    Two stages per read: (1) prec and cov for EVERY prototype at every shift, from the mask alone
    (bit-packed rows, popcounts); (2) the colour recall only where it can change a decision:
    the pairs (prototype, shift) with prec >= PREC_MIN, per class in decreasing prec (prec bounds
    the score from above), classes in decreasing upper bound, stopping once no remaining pair can
    lift the class's lead above the current leader's or its competitor score into the widest
    margin below the leader. So the leader's score and every competitor score inside that
    window are exact whenever >= PREC_MIN; a value below PREC_MIN is reported as a lower bound
    (often 0), which changes no decision because every floor minus its margin is >= PREC_MIN (a
    test pins it). ``exhaustive=True`` computes every pair (the tests compare the two)."""

    def __init__(self, a: Any, m: Any, cls: Sequence[str], src: Sequence[str] | None = None,
                 floors: dict[str, float] | None = None,
                 margins: dict[str, float] | None = None, r: int = R) -> None:  # fmt: skip
        a = np.asarray(a)[..., :3]
        self.cls_all = [str(c) for c in cls]
        self.src_all = [str(s) for s in src] if src is not None else [""] * len(self.cls_all)
        self.floors = dict(FLOORS if floors is None else floors)
        self.margins = dict(MARGINS if margins is None else margins)
        self.r = r
        self.max_margin = max([*self.margins.values(), DEFAULT_MARGIN])
        sup = consensus_supports(m, self.cls_all)
        valid = [i for i in range(len(self.cls_all)) if int(sup[i].sum()) >= MIN_PX]
        self.dropped = sorted(set(range(len(self.cls_all))) - set(valid))
        keep = valid
        self.ref = np.array(keep, dtype=np.int64)  # prototype -> reference index
        self.classes = sorted({self.cls_all[i] for i in keep})
        self.pcls = np.array([self.classes.index(self.cls_all[i]) for i in keep], dtype=np.int64)
        pw = CROP + 2 * r
        self.pw = pw
        inner_l, i_idx, i_col = [], [], []
        for j in keep:
            s = sup[j]
            inner = _erode4(s)
            if inner.sum() < max(MIN_PX // 2, INTERIOR_MIN * s.sum()):
                inner = s
            ys, xs = np.nonzero(inner)
            i_idx.append((ys + r) * pw + (xs + r))
            i_col.append(a[j][ys, xs].astype(np.int16))
            inner_l.append(len(ys))
        self.i_n = np.array(inner_l, dtype=np.int64)
        self.i_seg = np.concatenate([[0], np.cumsum(self.i_n)[:-1]]).astype(np.int64)
        self.i_idx = np.concatenate(i_idx)
        self.i_col = np.concatenate(i_col)
        self.i_ch = [np.ascontiguousarray(self.i_col[:, c]) for c in range(3)]
        self.s_bits = _pack(sup[keep])  # (prototypes, 64) uint64: bit x of row y
        self.d_bits = _pack(np.stack([_dilate8(sup[j]) for j in keep]))
        self.s_n = sup[keep].reshape(len(keep), -1).sum(1).astype(np.float64)
        self.by_class = [np.nonzero(self.pcls == c)[0] for c in range(len(self.classes))]
        self.shifts = [(dx, dy) for dy in range(-r, r + 1) for dx in range(-r, r + 1)]
        self.offsets = np.array([dy * pw + dx for dx, dy in self.shifts], dtype=np.int64)

    @classmethod
    def load(cls, path: Path = REFS_V3, **kw: Any) -> RobustRefs:
        z = np.load(path)
        src = [str(s) for s in z["src"]] if "src" in z.files else None
        return cls(z["a"], z["m"], [str(c) for c in z["cls"]], src, **kw)

    def __len__(self) -> int:
        return len(self.ref)

    def _mask_terms(self, m: Any) -> tuple[Any, Any, int]:
        """prec and cov, (prototypes, shifts), from the mask alone: popcounts of the prototype's
        (grown) support AND the mask shifted by (dx, dy) (row y + dy, column x + dx)."""
        r = self.r
        rows = _pack(np.asarray(m, dtype=bool)[None])[0]
        pad = np.zeros(CROP + 2 * r, np.uint64)
        pad[r : r + CROP] = rows
        dsh = np.empty((len(self.shifts), CROP), np.uint64)
        for k, (dx, dy) in enumerate(self.shifts):
            row = pad[r + dy : r + dy + CROP]
            dsh[k] = row >> np.uint64(dx) if dx >= 0 else row << np.uint64(-dx)
        n_d = max(int(np.asarray(m).sum()), 1)
        ys = np.nonzero(rows)[0]
        lo, hi = (max(int(ys[0]) - r, 0), min(int(ys[-1]) + r + 1, CROP)) if len(ys) else (0, 0)
        sb, db, dw = self.s_bits[:, None, lo:hi], self.d_bits[:, None, lo:hi], dsh[None, :, lo:hi]
        cov = np.bitwise_count(sb & dw).sum(-1) / self.s_n[:, None]
        prec = np.bitwise_count(db & dw).sum(-1) / n_d
        return prec, cov, n_d

    def _planes(self, a: Any) -> list[Any]:
        """The observed crop, padded by r (outside never matches), one flat plane per channel."""
        big = np.full((3, self.pw, self.pw), -4096, np.int16)
        big[:, self.r : self.r + CROP, self.r : self.r + CROP] = np.moveaxis(
            np.asarray(a)[..., :3], -1, 0
        )
        return [big[c].reshape(-1) for c in range(3)]

    def _rec(self, planes: list[Any], ks: Any, ss: Any) -> Any:
        """The colour recall of prototype ks[i] at shift ss[i]."""
        if not len(ks):
            return np.zeros(0)
        lens = self.i_n[ks]
        starts = np.concatenate([[0], np.cumsum(lens)[:-1]])
        pos = np.arange(int(lens.sum())) - np.repeat(starts - self.i_seg[ks], lens)
        gi = self.i_idx[pos] + np.repeat(self.offsets[ss], lens)
        ok = np.abs(planes[0][gi] - self.i_ch[0][pos]) < TOL
        ok &= np.abs(planes[1][gi] - self.i_ch[1][pos]) < TOL
        ok &= np.abs(planes[2][gi] - self.i_ch[2][pos]) < TOL
        return np.add.reduceat(ok.astype(np.int32), starts) / lens

    def scores(self, a: Any, mask: Any, exclude: Iterable[int] = (),
               exhaustive: bool = False) -> dict[str, Any]:  # fmt: skip
        """Per CLASS, two maxima of min(rec, prec) over (prototype, shift) pairs:
        - "lead": over the pairs with cov >= COV_MIN (the shape is really there);
        - "comp": over EVERY pair. A competitor needs no coverage: a shape whose colours are all
          in A and which explains D is an alternative even where D misses most of it (a no-entry
          ring on a background of its own colour leaves only the arrow in D).
        Each with its (prototype, shift index, rec, prec, cov) in "lead_at" / "comp_at". The fast
        path is exact for every value that can change a decision (see the class docstring)."""
        m = np.asarray(mask, dtype=bool)
        prec, cov, n_d = self._mask_terms(m)
        cand = np.ones_like(prec, dtype=bool) if exhaustive else prec >= PREC_MIN
        drop = {int(x) for x in exclude}
        if drop:
            cand[[k for k, j in enumerate(self.ref) if int(j) in drop]] = False
        planes = self._planes(a)
        n_c = len(self.classes)
        lead, comp = np.zeros(n_c), np.zeros(n_c)
        lead_at: list[Any] = [None] * n_c
        comp_at: list[Any] = [None] * n_c
        per = []
        for rows in self.by_class:
            kk, ss = np.nonzero(cand[rows])
            ks = rows[kk]
            order = np.argsort(-prec[ks, ss], kind="stable")
            per.append((ks[order], ss[order]))
        pairs = 0
        top = 0.0
        for c in sorted(range(n_c), key=lambda c: -prec[per[c][0][0], per[c][1][0]]
                        if len(per[c][0]) else 0.0):  # fmt: skip
            ks, ss = per[c]
            pr, cv = prec[ks, ss], cov[ks, ss]
            bl = bc = 0.0
            i, step = 0, BATCH
            while i < len(ks):
                # a pair can still matter if it may lift this class's lead above the leader's,
                # or its competitor score into the widest margin below the leader
                bound = -1.0 if exhaustive else min(max(bl, top), max(bc, top - self.max_margin))
                if pr[i] <= bound:
                    break
                stop = len(ks) if exhaustive else i + int(np.searchsorted(-pr[i:], -bound))
                j = min(i + step, stop)
                got = self._rec(planes, ks[i:j], ss[i:j])
                sc = np.minimum(got, pr[i:j])
                pairs += j - i
                g = int(np.argmax(sc))
                if sc[g] > bc or comp_at[c] is None:
                    bc = float(sc[g])
                    comp_at[c] = (int(ks[i + g]), int(ss[i + g]), float(got[g]), float(pr[i + g]),
                                  float(cv[i + g]))  # fmt: skip
                ok = cv[i:j] >= COV_MIN
                if ok.any():
                    g = int(np.argmax(np.where(ok, sc, -1.0)))
                    if sc[g] > bl or lead_at[c] is None:
                        bl = float(sc[g])
                        lead_at[c] = (int(ks[i + g]), int(ss[i + g]), float(got[g]),
                                      float(pr[i + g]), float(cv[i + g]))  # fmt: skip
                i, step = j, step * 4
            lead[c], comp[c] = bl, bc
            top = max(top, bl)
        return {"lead": lead, "comp": comp, "lead_at": lead_at, "comp_at": comp_at, "n_d": n_d,
                "pairs": pairs}  # fmt: skip

    def class_scores(self, a: Any, mask: Any, exclude: Iterable[int] = ()) -> dict[str, Any]:
        """{class: (lead, comp)}, exhaustive (the floors analysis)."""
        s = self.scores(a, mask, exclude, exhaustive=True)
        return {c: (float(s["lead"][k]), float(s["comp"][k])) for k, c in enumerate(self.classes)}

    def match(self, a: Any, mask: Any, exclude: Iterable[int] = (),
              exhaustive: bool = False) -> dict[str, Any]:  # fmt: skip
        m = np.asarray(mask, dtype=bool)
        if int(m.sum()) < MIN_PX:
            return {"shape": "unknown", "why": "no_cursor", "iou": 0.0, "col": 0.0, "score": 0.0}
        s = self.scores(a, m, exclude, exhaustive)
        c1 = int(np.argmax(s["lead"]))
        name = self.classes[c1]
        score = float(s["lead"][c1])
        others = [c for c in range(len(self.classes)) if c != c1]
        c2 = max(others, key=lambda c: s["comp"][c]) if others else c1
        second = [self.classes[c2], round(float(s["comp"][c2]), 3)] if others else ["", 0.0]
        margin = score - float(second[1])
        if score < PREC_MIN or s["lead_at"][c1] is None:
            # no prototype reaches the stage-2 bound (the fast path reports 0)
            return {"shape": "unknown", "why": "no_match", "iou": 0.0, "col": 0.0,
                    "score": round(score, 3), "second": second}  # fmt: skip
        k1, sh, rec, prec, cov = s["lead_at"][c1]
        dx, dy = self.shifts[sh]
        cov_px = cov * float(self.s_n[k1])
        iou = cov_px / max(s["n_d"] + float(self.s_n[k1]) - cov_px, 1.0)
        out: dict[str, Any] = {
            "shape": name, "iou": round(iou, 3), "col": round(rec, 3), "score": round(score, 3),
            "prec": round(prec, 3), "cov": round(cov, 3), "second": second,
            "margin": round(margin, 3), "shift": [dx, dy], "ref": int(self.ref[k1]),
        }  # fmt: skip
        if score < self.floors.get(name, DEFAULT_FLOOR):
            out.update(shape="unknown", why="low_score", best=name)
        elif margin < self.margins.get(name, DEFAULT_MARGIN):
            out.update(shape="unknown", why=f"ambiguous:{second[0]}", best=name)
        return out


def timing(refs: RobustRefs, a: Any, mask: Any, n: int = 20) -> float:
    """Median wall time of one match, ms."""
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        refs.match(a, mask)
        ts.append((time.perf_counter() - t0) * 1000)
    return float(np.median(ts))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("npz", nargs="*", type=Path, help="crops with arrays a + mask (or a + b)")
    ap.add_argument("--refs", type=Path, default=REFS_V3)
    args = ap.parse_args()
    refs = RobustRefs.load(args.refs)
    print(json.dumps({"refs": len(refs.cls_all), "prototypes": len(refs),
                      "dropped": [refs.src_all[i] for i in refs.dropped]}))  # fmt: skip
    for p in args.npz:
        z = np.load(p)
        a = z["a"][28:92, 28:92] if z["a"].shape[0] == 120 else z["a"]
        if "mask" in z.files:
            mask = z["mask"]
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import walk6 as w6

            mask = w6.cursor_mask(a, z["b"])
        out = refs.match(a, mask)
        print(json.dumps({"npz": str(p), **out}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
