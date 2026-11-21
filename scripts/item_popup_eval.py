#!/usr/bin/env python3
"""docs/planning/item-popup-reader.md sections 3-4: the item popup reader against the packets, on
the 720 recordings (popups 1:1). Every item that lands in the bag is a pickup_result packet (ok,
item_id, amount, t_mono_ns); the frames' t_mono_ns is the same clock.

    item_popup_eval.py calibrate [--sessions fiT1..fiT20] [--out JSON]   the icon offset and bars
    item_popup_eval.py score     --params JSON [--json]                   ONCE, every other fiT

The recordings are read in place, read-only (the NAS); no frame is written.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import io
import json
import re
import statistics
import sys
import tarfile
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import item_popup as ip  # noqa: E402

NAS = Path("/mnt/poring-lab-datasets")
FAMILY = re.compile(r"-rdp-hunt-xmas02-fiT(\d+)$")
WINDOW_S = 3.0
CALIB = range(1, 21)  # fiT1 .. fiT20 (section 4)
OFFSETS = [(dx, dy) for dx in range(6, 17) for dy in range(0, 9)]


def sessions(numbers: Sequence[int] | None = None, exclude: Sequence[int] = ()) -> list[Path]:
    out = []
    for d in NAS.iterdir():
        m = FAMILY.search(d.name)
        if m and (numbers is None or int(m.group(1)) in numbers) and int(m.group(1)) not in exclude:
            out.append(d)
    return sorted(out, key=lambda p: int(FAMILY.search(p.name).group(1)))  # type: ignore[union-attr]


def truths(session: Path) -> list[dict[str, Any]]:
    out = []
    with gzip.open(session / "packets.jsonl.gz", "rt", errors="replace") as fh:
        for ln in fh:
            try:
                p = json.loads(ln)
            except ValueError:
                continue
            if (
                p.get("type") == "pickup_result"
                and p.get("ok")
                and isinstance(p.get("t_mono_ns"), int)
            ):
                out.append(
                    {"t": p["t_mono_ns"], "id": int(p["item_id"]), "amount": int(p["amount"])}
                )
    return sorted(out, key=lambda r: r["t"])


def frames(session: Path, keep: Any = None) -> Iterator[tuple[int, np.ndarray]]:
    """(t_mono_ns, RGB) of every frame in time order; ``keep(t)`` False skips its PNG decode."""
    from PIL import Image

    for sh in sorted(session.glob("shard-*.tar")):
        with tarfile.open(sh) as tf:
            pngs: dict[str, tarfile.TarInfo] = {}
            for m in tf:
                if m.name.endswith(".png"):
                    pngs[m.name[:-4]] = m
                elif m.name.endswith(".json"):
                    t = int(json.load(tf.extractfile(m))["t_mono_ns"])  # type: ignore[arg-type]
                    pm = pngs.pop(m.name[:-5], None)
                    if pm is None or (keep is not None and not keep(t)):
                        continue
                    data = tf.extractfile(pm).read()  # type: ignore[union-attr]
                    yield t, np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def calibrate(paths: Sequence[Path], refs: str | None = None) -> dict[str, Any]:
    icons = ip.Icons.load(refs)
    want: list[tuple[np.ndarray, int]] = []  # (the box's 1:1 crop rows 0..POPUP_BOTTOM+1, truth id)
    lefts: Counter[int] = Counter()
    for s in paths:
        tr = truths(s)
        ts = [r["t"] for r in tr]

        def near(t: int, ts: list[int] = ts) -> bool:
            i = bisect.bisect_right(ts, t) - 1
            return i >= 0 and t - ts[i] <= WINDOW_S * 1e9

        seen: set[int] = set()
        for t, f in frames(s, near):
            i = bisect.bisect_right(ts, t) - 1
            if i in seen:
                continue
            p = ip.box_of(f)
            if p is None:
                continue
            seen.add(i)
            lefts[p.left] += 1
            want.append(
                (np.asarray(f[: ip.bs.POPUP_BOTTOM + 2, p.left : p.left + 60]), tr[i]["id"])
            )
    # the offset search on the pictures of the items that occur (the full set only at the end)
    occur = {tid for _, tid in want}
    keep = [k for k, g in enumerate(icons.ids) if occur & set(g)]
    sub = ip.Icons(icons.rgb[keep], icons.own[keep], tuple(icons.ids[k] for k in keep))
    full, icons = icons, sub
    scores = {}
    for off in OFFSETS:
        right, dist = 0, []
        for crop, tid in want:
            sq = crop[
                ip.bs.POPUP_TOP + off[1] : ip.bs.POPUP_TOP + off[1] + ip.ICON,
                off[0] : off[0] + ip.ICON,
            ]
            if sq.shape[:2] != (ip.ICON, ip.ICON):
                continue
            d = icons.distances(sq)
            best = int(np.argmin(d))
            right += tid in icons.ids[best]
            own = [float(d[k]) for k, g in enumerate(icons.ids) if tid in g]
            if own:
                dist.append(min(own))
        scores[off] = (right, statistics.median(dist) if dist else 1e9)
    off = max(scores, key=lambda o: (scores[o][0], -scores[o][1]))
    icons = full
    # the bars from the chosen offset: the true picture's distance vs the best wrong one's
    true_d, wrong_d = [], []
    for crop, tid in want:
        sq = crop[
            ip.bs.POPUP_TOP + off[1] : ip.bs.POPUP_TOP + off[1] + ip.ICON, off[0] : off[0] + ip.ICON
        ]
        d = icons.distances(sq)
        mine = [k for k, g in enumerate(icons.ids) if tid in g]
        if not mine:
            continue
        td = min(float(d[k]) for k in mine)
        wd = min(float(d[k]) for k, g in enumerate(icons.ids) if tid not in g)
        true_d.append(td)
        wrong_d.append(wd - td)
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))] if xs else None  # noqa: E731
    return {"sessions": [s.name for s in paths], "popups": len(want), "lefts": dict(lefts),
            "offset": list(off), "right_at_offset": scores[off][0],
            "true_dist": {"p50": q(true_d, 0.5), "p95": q(true_d, 0.95),
                          "max": max(true_d) if true_d else None},
            "margin_to_wrong": {"p05": q(wrong_d, 0.05), "p50": q(wrong_d, 0.5),
                                "min": min(wrong_d) if wrong_d else None},
            "top_offsets": sorted(((list(o), v[0], round(v[1], 2)) for o, v in scores.items()),
                                  key=lambda x: (-x[1], x[2]))[:5]}  # fmt: skip


def events_of(session: Path, icons: ip.Icons, count: ip.CountFont) -> list[dict[str, Any]]:
    """The reader over every frame of a session: one event per NEW popup (time, ids, amount)."""
    out: list[dict[str, Any]] = []
    prev: ip.Popup | None = None
    for t, f in frames(session):
        cur = ip.box_of(f)
        if ip.is_new(prev, cur) and cur is not None:
            it = icons.read(ip.icon_square(f, cur))
            box = np.full((34, 260, 3), 255, np.uint8)
            sub = f[
                ip.bs.POPUP_TOP - 2 : ip.bs.POPUP_BOTTOM + 2,
                cur.left : min(cur.right + 1, cur.left + 260),
            ]
            box[: sub.shape[0], : sub.shape[1]] = sub
            out.append({"t": t, "ids": list(it.ids) if it.ids else None, "why": it.why,
                        "dist": it.dist, "amount": ip.read_count(box, count)})  # fmt: skip
        prev = cur
    return out


def match(events: Sequence[dict[str, Any]], truth: Sequence[dict[str, Any]],
          window_s: float = WINDOW_S) -> dict[str, Any]:  # fmt: skip
    """PURE (section 3): each truth to the first unused event in [t, t + window]; the lines."""
    used: set[int] = set()
    rows = []
    prev_t: int | None = None
    for tr in truth:
        hit = next((k for k, e in enumerate(events) if k not in used
                    and tr["t"] <= e["t"] <= tr["t"] + window_s * 1e9), None)  # fmt: skip
        gap = None if prev_t is None else (tr["t"] - prev_t) / 1e9
        prev_t = tr["t"]
        if hit is None:
            rows.append({"found": False, "gap": gap})
            continue
        used.add(hit)
        e = events[hit]
        rows.append({"found": True, "gap": gap, "id_ok": bool(e["ids"]) and tr["id"] in e["ids"],
                     "id_unread": not e["ids"], "amount_ok": e["amount"] == tr["amount"],
                     "amount_unread": e["amount"] is None})  # fmt: skip
    found = [r for r in rows if r["found"]]
    spaced = [r for r in rows if r["gap"] is None or r["gap"] >= 2.0]
    return counts_lines({
        "truths": len(rows), "events": len(events), "matched": len(found),
        "id_ok": sum(r["id_ok"] for r in found), "id_unread": sum(r["id_unread"] for r in found),
        "amount_ok": sum(r["amount_ok"] for r in found),
        "amount_unread": sum(r["amount_unread"] for r in found),
        "spaced": len(spaced), "spaced_found": sum(r["found"] for r in spaced),
    })  # fmt: skip


def counts_lines(c: dict[str, int]) -> dict[str, Any]:
    """PURE: the counts and their four lines (None when a line has no denominator)."""

    def div(a: int, b: int) -> float | None:
        return a / b if b else None

    return {**c, "I1_id": div(c["id_ok"], c["matched"]),
            "I2_amount": div(c["amount_ok"], c["matched"]),
            "P_false": div(c["events"] - c["matched"], c["events"]),
            "R_spaced": div(c["spaced_found"], c["spaced"])}  # fmt: skip


BARS = {"I1_id": 0.97, "I2_amount": 0.97, "P_false": 0.02, "R_spaced": 0.85}


def verdict(lines: dict[str, Any]) -> dict[str, str]:
    """PURE: section 4's bars (P is a maximum, the rest minimums)."""
    out = {}
    for k, bar in BARS.items():
        v = lines.get(k)
        out[k] = "INCONCLUSIVE" if v is None else (
            "PASS" if (v <= bar if k == "P_false" else v >= bar) else "FAIL")  # fmt: skip
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("calibrate")
    c.add_argument("--out", type=Path)
    c.add_argument("--refs", help="slot_items' pictures (default: this checkout's data/)")
    sc = sub.add_parser("score")
    sc.add_argument("--refs")
    sc.add_argument("--count", type=Path, required=True, help="the learned count font (.npz)")
    sc.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "score":
        icons, count = ip.Icons.load(a.refs), ip.load_count(a.count)
        events: list[dict[str, Any]] = []
        truth: list[dict[str, Any]] = []
        per = {}
        for s_ in sessions(None, exclude=list(CALIB)):
            ev, tr = events_of(s_, icons, count), truths(s_)
            per[s_.name] = match(ev, tr)
            events += ev
            truth += tr
            print(s_.name, json.dumps(per[s_.name]), flush=True)
        keys = ("truths", "events", "matched", "id_ok", "id_unread", "amount_ok",
                "amount_unread", "spaced", "spaced_found")  # fmt: skip
        lines = counts_lines({k: sum(int(v[k]) for v in per.values()) for k in keys})
        got = {"lines": lines, "verdict": verdict(lines), "sessions": per}
        text = json.dumps(got, indent=1, default=str)
        if a.out:
            a.out.write_text(text)
        print(text)
        return 0
    if a.cmd == "calibrate":
        got = calibrate(sessions(list(CALIB)), a.refs)
        text = json.dumps(got, indent=1, default=str)
        if a.out:
            a.out.write_text(text)
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
