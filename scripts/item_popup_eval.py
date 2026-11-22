#!/usr/bin/env python3
"""docs/planning/item-popup-reader.md sections 3-4: the item popup reader against the packets, on
the 720 recordings (popups 1:1). Every item that lands in the bag is a pickup_result packet (ok,
item_id, amount, t_mono_ns); the frames' t_mono_ns is the same clock.

    item_popup_eval.py calibrate [--out JSON]                        the icon offset and bars
    item_popup_eval.py learn-count --out NPZ [--set calib]           the count font (round 2)
    item_popup_eval.py score --set old|r2|r3 --count NPZ [--out JSON] ONCE per held-out set

Sets: calib = fiT1-fiT20; old = every other fiT (round 1's one score, used since); r2 = round 2's
held-out (Amendment 2): every other 720 recording with packets, R2_FAMILY. Round 2 reads one event
per popup shown (item_popup.Tracker). r3 = round 3's held-out (Amendment 5): 41 unread 720
recordings (stagings, Batt's own play, natural play), pinned by the sha256 of their names.

The recordings are read in place, read-only (the NAS); no frame is written.

    item_popup_eval.py score-events --watch DIR.. --sessions NAME.. [--out JSON] [--sizes]
Amendment 6 (section 4's 1080 run-time check, set w1080): the EVENTS `item_popup.py watch` wrote
beside dev 1080 Runs, against each session's packets in its window (manifest t0..t1). Refused
unless every session lies inside a watcher's span, and below the held-out's minimums (>= 250
pickups, >= 4 sessions); --sizes counts them from the packets only, reading no event.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
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
# round 2's held-out (item-popup-reader.md RESULT + Amendment 2): the other 720 recordings with
# packets -- xmas02 xw* and fs* (fsTa / fsTn / fsH too), rogue-*, thief-*
R2_FAMILY = re.compile(r"-rdp-(xmas02-(xw|fs)[\w-]*|rogue-[\w-]+|thief-[\w-]+)$")
# round 3's held-out (Amendment 5): 41 unread 720 recordings with packets (stagings, Batt's own
# play, natural play), PINNED by the sha256 of their names (name order, one per line, each ending
# in a newline): a later recording that matches the pattern cannot change the set
R3_FAMILY = re.compile(
    r"-rdp-(stage-items-[bc]|stage-gef10-e3[bx]?|watch-w\d+|ow\d+|w\d+|fp\d+[a-z]?"
    r"|s2-xmas_dun02-p\d+|sk-watch\d+|gb-gw\d+|flee-xmas02-sk|human-xmas02-batt\w+"
    r"|hunt-xmas02-(p\d+|bs\d+|fiH\d+(-ABORTED)?)|xmas02-(x\d+|xp\d+|xmw\d+|sk\d+a))$"
)
R3_SHA256 = "d2bf7aa0fb4c67d033a0e233bf462460cfe32e602b396ec00bf70c2a264cc2b7"
REPEAT_S = 6.0  # a truth whose previous truth is the same item <= this before: a "repeat"
OFFSETS = [(dx, dy) for dx in range(6, 17) for dy in range(0, 9)]


def sessions(numbers: Sequence[int] | None = None, exclude: Sequence[int] = ()) -> list[Path]:
    out = []
    for d in NAS.iterdir():
        m = FAMILY.search(d.name)
        if m and (numbers is None or int(m.group(1)) in numbers) and int(m.group(1)) not in exclude:
            out.append(d)
    return sorted(out, key=lambda p: int(FAMILY.search(p.name).group(1)))  # type: ignore[union-attr]


def session_set(name: str) -> list[Path]:
    """The sessions of a named set, in order; only those with packets and a frame shard."""
    if name == "calib":
        return sessions(list(CALIB))
    if name == "old":
        return sessions(None, exclude=list(CALIB))
    if name not in ("r2", "r3"):
        raise ValueError(f"unknown set {name!r}")
    fam = R2_FAMILY if name == "r2" else R3_FAMILY
    out = sorted((d for d in NAS.iterdir() if fam.search(d.name)
                  and (d / "packets.jsonl.gz").is_file() and any(d.glob("shard-*.tar"))),
                 key=lambda p: p.name)  # fmt: skip
    if name == "r3":
        pinned([d.name for d in out], R3_SHA256)
    return out


def names_sha256(names: Sequence[str]) -> str:
    """PURE: the sha256 of session names, one per line, each ending in a newline."""
    return hashlib.sha256("".join(f"{n}\n" for n in names).encode()).hexdigest()


def pinned(names: Sequence[str], sha: str) -> None:
    """PURE: refuse a set whose names are not the pre-registered list."""
    got = names_sha256(names)
    if got != sha:
        raise SystemExit(f"the set's {len(names)} sessions hash {got[:12]}, not the "
                         f"pre-registered {sha[:12]}: refused")  # fmt: skip


def part_of(name: str) -> str:
    """PURE: a session's part for the beside-counts: stagings, Batt's own play, natural play."""
    if "-rdp-stage-" in name or "-rdp-xmas02-fs" in name:
        return "stagings"
    if "-rdp-human-" in name:
        return "own_play"
    return "natural"


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
    """Round 2: the reader over every frame of a session, one event per popup SHOWN (Tracker)."""
    tr = ip.Tracker(icons, count)
    out: list[dict[str, Any]] = []
    for t, f in frames(session):
        out += [e.doc() for e in tr.feed(t, f)]
    return out + [e.doc() for e in tr.flush()]


def popups_with_truth(paths: Sequence[Path]) -> list[tuple[np.ndarray, int, int]]:
    """(text_box crop, truth id, truth amount) of the first frame with a box <= WINDOW_S after
    each pickup_result (calibrate's pairing)."""
    out = []
    for s in paths:
        tr = truths(s)
        ts = [r["t"] for r in tr]

        def near(t: int, ts: list[int] = ts) -> bool:
            i = bisect.bisect_right(ts, t) - 1
            return i >= 0 and t - ts[i] <= WINDOW_S * 1e9

        seen: set[int] = set()
        for t, f in frames(s, near):
            i = bisect.bisect_right(ts, t) - 1
            p = ip.box_of(f)
            if i in seen or p is None:
                continue
            seen.add(i)
            out.append((ip.text_box(f, p).copy(), tr[i]["id"], tr[i]["amount"]))
        print(s.name, len(out), flush=True)
    return out


def match(events: Sequence[dict[str, Any]], truth: Sequence[dict[str, Any]],
          window_s: float = WINDOW_S) -> dict[str, Any]:  # fmt: skip
    """PURE (section 3): each truth to the first unused event in [t, t + window]; the lines."""
    used: set[int] = set()
    rows = []
    prev_t: int | None = None
    prev_id: int | None = None
    for tr in truth:
        hit = next((k for k, e in enumerate(events) if k not in used
                    and tr["t"] <= e["t"] <= tr["t"] + window_s * 1e9), None)  # fmt: skip
        gap = None if prev_t is None else (tr["t"] - prev_t) / 1e9
        repeat = gap is not None and gap <= REPEAT_S and tr["id"] == prev_id
        prev_t, prev_id = tr["t"], tr["id"]
        if hit is None:
            rows.append({"found": False, "gap": gap, "repeat": repeat})
            continue
        used.add(hit)
        e = events[hit]
        rows.append({"found": True, "gap": gap, "repeat": repeat, "why": e.get("why"),
                     "id_ok": bool(e["ids"]) and tr["id"] in e["ids"],
                     "id_unread": not e["ids"], "amount_ok": e["amount"] == tr["amount"],
                     "amount_unread": e["amount"] is None})  # fmt: skip
    found = [r for r in rows if r["found"]]
    spaced = [r for r in rows if r["gap"] is None or r["gap"] >= 2.0]
    by_why: dict[str, list[int]] = {}  # round 3's beside-count: the event's why -> [matched, right]
    for r in found:
        k = by_why.setdefault(str(r["why"]), [0, 0])
        k[0] += 1
        k[1] += int(r["id_ok"])
    return counts_lines({"by_why": by_why,
        "truths": len(rows), "events": len(events), "matched": len(found),
        "id_ok": sum(r["id_ok"] for r in found), "id_unread": sum(r["id_unread"] for r in found),
        "amount_ok": sum(r["amount_ok"] for r in found),
        "amount_unread": sum(r["amount_unread"] for r in found),
        "spaced": len(spaced), "spaced_found": sum(r["found"] for r in spaced),
        "repeats": sum(r["repeat"] for r in rows),
        "repeats_found": sum(r["found"] for r in rows if r["repeat"]),
    })  # fmt: skip


def counts_lines(c: dict[str, Any]) -> dict[str, Any]:
    """PURE: the counts and their four lines (None when a line has no denominator)."""

    def div(a: int, b: int) -> float | None:
        return a / b if b else None

    return {**c, "I1_id": div(c["id_ok"], c["matched"]),
            "I2_amount": div(c["amount_ok"], c["matched"]),
            "P_false": div(c["events"] - c["matched"], c["events"]),
            "R_spaced": div(c["spaced_found"], c["spaced"])}  # fmt: skip


def beside(per: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """PURE (round 3, Amendment 5; no bars): I1 apart for each part (stagings, Batt's own play,
    natural play), and the reads by why ("ok", "lead", "same"), each with how many were right."""
    parts: dict[str, list[int]] = {}
    whys: dict[str, list[int]] = {}
    for name, v in per.items():
        k = parts.setdefault(part_of(name), [0, 0])
        k[0] += int(v["matched"])
        k[1] += int(v["id_ok"])
        for w, (n, ok) in v.get("by_why", {}).items():
            kw = whys.setdefault(w, [0, 0])
            kw[0] += int(n)
            kw[1] += int(ok)
    return {
        "I1_by_part": {
            p: {"matched": n, "id_ok": ok, "I1": ok / n if n else None}
            for p, (n, ok) in sorted(parts.items())
        },
        "reads_by_why": {w: {"matched": n, "right": ok} for w, (n, ok) in sorted(whys.items())},
    }


BARS = {"I1_id": 0.97, "I2_amount": 0.97, "P_false": 0.02, "R_spaced": 0.85}

# Amendment 6: set w1080's minimums (its sessions are taken in time order until both are met)
W1080_MIN_TRUTHS = 250
W1080_MIN_SESSIONS = 4


def session_window(session: Path) -> tuple[int, int]:
    """A recording's span on the host clock (its manifest's t0_mono_ns .. t1_mono_ns)."""
    m = json.loads((session / "manifest.json").read_text())
    return int(m["t0_mono_ns"]), int(m["t1_mono_ns"])


def in_window(rows: Sequence[dict[str, Any]], t0: int, t1: int, pad_s: float = 0.0
              ) -> list[dict[str, Any]]:  # fmt: skip
    """PURE: the rows whose t lies in [t0, t1 + pad_s], in time order."""
    return sorted((r for r in rows if t0 <= int(r["t"]) <= t1 + pad_s * 1e9),
                  key=lambda r: int(r["t"]))  # fmt: skip


def covered(window: tuple[int, int], spans: Sequence[tuple[int, int]]) -> bool:
    """PURE: a session window lies inside one watcher span (its start .. its end)."""
    return any(a <= window[0] and window[1] <= b for a, b in spans)


def watch_dir(d: Path) -> tuple[tuple[int, int] | None, list[dict[str, Any]], dict[str, Any]]:
    """A watcher's folder: its span (meta's start .. summary's end; None while it runs), its
    events, its summary."""
    meta = json.loads((d / "meta.json").read_text())
    summ = json.loads((d / "summary.json").read_text()) if (d / "summary.json").is_file() else {}
    span = None
    if summ.get("t_end_mono_ns"):
        span = (int(meta["t_start_mono_ns"]), int(summ["t_end_mono_ns"]))
    evs = []
    p = d / "events.jsonl"
    if p.is_file():
        for ln in p.read_text().splitlines():
            if ln.strip():
                evs.append(json.loads(ln))
    return span, evs, summ


def score_events(sessions: Sequence[Path], watches: Sequence[Path], sizes_only: bool = False
                 ) -> dict[str, Any]:  # fmt: skip
    """Amendment 6's score of set w1080 (see the module's docstring)."""
    spans, events, summaries = [], [], {}
    for d in watches:
        span, evs, summ = watch_dir(d)
        if span is not None:
            spans.append(span)
        events += evs
        summaries[d.name] = summ
    sizes = {}
    for s_ in sessions:
        w = session_window(s_)
        if not covered(w, spans):
            raise SystemExit(f"{s_.name}: no finished watcher span covers {w}: refused")
        sizes[s_.name] = len(in_window(truths(s_), *w))
    total = sum(sizes.values())
    size_ok = total >= W1080_MIN_TRUTHS and len(sessions) >= W1080_MIN_SESSIONS
    if sizes_only:
        return {"sizes": sizes, "truths": total, "sessions": len(sessions), "size_ok": size_ok}
    if not size_ok:
        need = f">= {W1080_MIN_TRUTHS} and >= {W1080_MIN_SESSIONS}"
        raise SystemExit(
            f"w1080 below its minimums ({total} pickups, {len(sessions)} sessions; {need}): refused"
        )
    per = {}
    for s_ in sessions:
        t0, t1 = session_window(s_)
        per[s_.name] = match(in_window(events, t0, t1, WINDOW_S), in_window(truths(s_), t0, t1))
    keys = ("truths", "events", "matched", "id_ok", "id_unread", "amount_ok", "amount_unread",
            "spaced", "spaced_found", "repeats", "repeats_found")  # fmt: skip
    lines = counts_lines({k: sum(int(v[k]) for v in per.values()) for k in keys})
    return {"set": "w1080", "lines": lines, "verdict": verdict(lines),
            "beside": {**beside(per), "watchers": summaries}, "sessions": per}  # fmt: skip


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
    lc = sub.add_parser("learn-count", help="the count font from a set's popups (calib only)")
    lc.add_argument("--set", default="calib", choices=["calib"])
    lc.add_argument("--out", type=Path, required=True, help="the font (.npz, under data/)")
    sc = sub.add_parser("score")
    sc.add_argument("--set", required=True, choices=["calib", "old", "r2", "r3"])
    sc.add_argument("--refs")
    sc.add_argument("--count", type=Path, required=True, help="the learned count font (.npz)")
    sc.add_argument("--out", type=Path)
    se = sub.add_parser("score-events", help="Amendment 6: set w1080, the watcher's events")
    se.add_argument("--watch", type=Path, nargs="+", required=True, help="the watchers' folders")
    se.add_argument("--sessions", nargs="+", required=True, help="the NAS sessions, by name")
    se.add_argument("--sizes", action="store_true", help="count the pickups only (no event read)")
    se.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "score-events":
        got = score_events([NAS / n for n in a.sessions], a.watch, a.sizes)
        text = json.dumps(got, indent=1, default=str)
        if a.out:
            a.out.write_text(text)
        print(text)
        return 0
    if a.cmd == "score":
        icons, count = ip.Icons.load(a.refs), ip.load_count(a.count)
        per = {}
        for s_ in session_set(a.set):
            ev, tr = events_of(s_, icons, count), truths(s_)
            per[s_.name] = match(ev, tr)
            print(s_.name, json.dumps(per[s_.name]), flush=True)
        keys = ("truths", "events", "matched", "id_ok", "id_unread", "amount_ok",
                "amount_unread", "spaced", "spaced_found", "repeats", "repeats_found")  # fmt: skip
        lines = counts_lines({k: sum(int(v[k]) for v in per.values()) for k in keys})
        got = {
            "set": a.set,
            "lines": lines,
            "verdict": verdict(lines),
            "beside": beside(per),
            "sessions": per,
        }
        text = json.dumps(got, indent=1, default=str)
        if a.out:
            a.out.write_text(text)
        print(text)
        return 0
    if a.cmd == "learn-count":
        got = popups_with_truth(session_set(a.set))
        font = ip.learn_count([b for b, _, _ in got], [m for _, _, m in got])
        ip.save_count(font, a.out)
        reads = Counter(
            "ok" if ip.read_count(b, font) == m else (
                "unread" if ip.read_count(b, font) is None else "wrong")
            for b, _, m in got)  # fmt: skip
        print(json.dumps({"popups": len(got), "amounts": Counter(m for _, _, m in got),
                          "tail": len(font.tail), "digits": sorted(font.digits),
                          "self_read": reads}, default=str))  # fmt: skip
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
