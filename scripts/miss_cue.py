#!/usr/bin/env python3
"""The MISS cue: the client's "Miss" text for a monster's swing at us, from PIXELS (study for
dungeon@9.1; docs/planning/gef10-miss-cue.md). Today's defend-scan trigger waits for a HIT on us
(Battle Log "taken") or the HP percent falling. The Rogue has FLEE 192: the orcs land 7.6 % of
their swings (292 of 3,850 in the ten allowed runs), so the first hit comes several swings after
the attack began. Every swing that misses makes the client draw "Miss": a human sees it at once.

WHAT THE CLIENT DRAWS (measured on the a2 recording and Batt's 5 Hz demo, section 1 of the doc):
- a small light-grey serif "Miss" (about 30 x 10 px, a dark drop shadow), fixed size, fading;
- drawn above the ATTACKER, not above us: its x follows the attacker's cell (dx -1 -> about
  -35 px, dx +1 -> about +45 px from the screen centre); a melee orc stands beside us, so the text
  appears in a band around our head; it rises as it ages and several stack while an orc keeps
  swinging;
- it appears about MISS_DELAY_S after the server's act packet (the orc's attack motion, 864-900
  ms) and stays up to ~3 s, rising (clearly matched while young: VISIBLE_FROM_S..VISIBLE_TO_S).

THE DETECTOR (pure; numpy only):
- ROI: the band where a melee attacker's Miss is drawn (game-region px, ROI);
- feature: "bright and neutral" = clip(min(B, G, R) - FEAT_LO, 0, FEAT_SPAN) / FEAT_SPAN: the
  text is light grey on grass / dirt / leaves whose blue channel stays low; red damage numbers on
  us and yellow totals read 0 on it;
- score: the best zero-mean normalised cross-correlation (FFT) of the feature with a TEMPLATE
  averaged from real Miss texts (cut LOCALLY from the tuning recordings into data/miss_cue/:
  client pixels, gitignored, never committed);
- an early exit when the ROI holds fewer than MIN_INK bright-neutral pixels (most frames);
- ``miss_over_us(frame) -> bool`` = score >= THRESHOLD; ``read(frame)`` gives the score and where.

THE TRUTH (offline only; packets never reach the runner): an ``act`` with target_gid == our AID
and damage 0 (kind "normal") is a monster's MISS on us; damage > 0 is a hit (a red number);
lucky_dodge draws "Lucky" (another word: reported apart). A frame is POSITIVE when a miss's packet
lies VISIBLE_FROM_S..VISIBLE_TO_S before it; NEGATIVE when no act on us lies within NEG_GAP_S of
it; the hard negatives are the frames on which no Miss can be drawn but something else is (our
damage numbers, a red number on us, the Steal shout, a potion, notices, a fight scene).

    miss_cue.py cut --seed SESSION:FRAME_ID:X,Y [--out data/miss_cue]   the template, from TUNE
    miss_cue.py validate --split tune|test [--out FILE]                 per-frame scores vs truth
    miss_cue.py validate --split test2 --open-held-back     the held-back runs (the parent's step)
    miss_cue.py latency [--session S] [--n 200]                         ms per call (CPU)
    miss_cue.py demo [--session SID]                 Batt's 5 Hz demo: per-event recall, FP / min
    miss_cue.py gain [--recall R] [--out FILE]       packets: what the trigger would gain

The split was fixed before any result was read: TUNE = a2, a3, a4 (the template, the threshold);
TEST = a7, a8, a5b, b1, c1, c2, c3. a9, a10, a11 and w3 are held back (never opened here).
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import json
import statistics
import sys
import tarfile
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "miss_cue"  # client pixels: gitignored (/data/*), never committed
TEMPLATE = OUT_DIR / "template.npy"
NAS = Path("/mnt/poring-lab-datasets")
REC = Path("/dev/shm/poring-lab-rec")
DEMO = Path("/dev/shm/poring-lab-demo")
CACHE = Path("/dev/shm/poring-lab-tmp/miss-cue")  # RAM: shard offset indexes
AID = 2000002
NS = 1_000_000_000

# game-region px (1280 x 720): the band a melee attacker's Miss is drawn in. Text centres of the
# a2 positives: x 576..704 and y 183..310 (10-90 %), 383..704 / 156..321 (2-98 %); the ROI holds
# centres x 537..743, y 137..333 (the template is 34 x 14)
ROI = (520, 130, 760, 340)  # x0, y0, x1, y1
FEAT_LO, FEAT_SPAN = 130, 90
INK = 0.25  # a feature value this high is "ink"
MIN_INK = 40  # fewer ink pixels in the ROI than this: no text there (early exit, score 0)
THRESHOLD = 0.60  # TUNE: non-Miss max 0.443 + a 0.15 margin; fixed before TEST was opened (doc 2)
TEMPLATE_HW = (14, 34)

# truth windows (s after the act packet), measured on TUNE + Batt's 5 Hz demo (doc section 1)
MISS_DELAY_S = 0.75  # first seen 0.7-0.8 s after the packet (5 Hz demo)
VISIBLE_FROM_S, VISIBLE_TO_S = 0.8, 1.8  # the 5 Hz demo: seen 0.7 .. ~2.0 s, most 0.8 .. 1.8 s
MAYBE_FROM_S, MAYBE_TO_S = 0.3, 3.3  # a Miss MAY be on screen (appearing / old, high): not judged
NEG_GAP_S = 3.0  # NEGATIVE: no act on us within +-this
HARD = {  # class -> (lo, hi) s after the event in which its text / bubble is on screen
    "hit_on_us": (0.8, 2.0),  # a red damage number (beside us, above the attacker)
    "our_attack": (0.2, 1.8),  # our damage numbers above the monster
    "lucky": (0.8, 2.0),  # "Lucky": a swing at us too, another word
    "steal": (0.0, 2.0),  # the Steal skill's shout bubble above our head
    "potion": (0.0, 2.0),  # our White Potion
    "notice": (0.0, 3.0),  # item obtained / weight / chat lines and bubbles
    "level": (0.0, 3.0),  # a base / job level change
}
TUNE = ("20261025T221059-rdp-rogue-a2", "20261025T224840-rdp-rogue-a3",
        "20261025T232619-rdp-rogue-a4")  # fmt: skip
TEST = ("20261026T010738-rdp-rogue-a7", "20261026T023132-rdp-rogue-a8",
        "20261026T031208-rdp-rogue-a5b", "20261026T104146-rdp-rogue-b1",
        "20261026T120547-rdp-rogue-c1", "20261026T124432-rdp-rogue-c2",
        "20261026T130310-rdp-rogue-c3")  # fmt: skip
HELD_BACK = ("a9", "a10", "a11", "w3")  # TEST2 of the detector: never opened by this study
TEST2 = ("20261026T044312-rdp-rogue-a9", "20261026T052148-rdp-rogue-a10",
         "20261026T055949-rdp-rogue-a11", "20261026T112924-rdp-w3")  # fmt: skip
_OPEN_HELD_BACK = [False]  # only `validate --split test2 --open-held-back` (the parent's step)


# --- the detector (PURE) -------------------------------------------------------------------------


Image = npt.NDArray[np.uint8]
Floats = npt.NDArray[np.float32]


@dataclass(frozen=True)
class MissRead:
    score: float  # the best NCC in the ROI (0 when the ROI holds no ink)
    x: int | None  # the matched text's centre (game-region px), None without a match
    y: int | None
    ink: int  # bright-neutral pixels in the ROI


def feature(img: Image) -> Floats:
    """PURE: "bright and neutral" in [0, 1] per pixel: (min(B, G, R) - FEAT_LO) / FEAT_SPAN."""
    m = img[..., :3].min(axis=2).astype(np.float32)
    out: Floats = np.clip((m - FEAT_LO) / FEAT_SPAN, 0.0, 1.0)
    return out


def _fast_len(n: int) -> int:
    best = 1 << (n - 1).bit_length()
    for a in (3, 5, 9, 15, 25, 27, 45, 75, 81):
        m = a
        while m < n:
            m *= 2
        best = min(best, m)
    return best


def ncc_map(img: Floats, tpl: Floats) -> Floats:
    """PURE: the zero-mean normalised cross-correlation of ``tpl`` at every valid position of
    ``img`` (both 2-D). A flat window (std < 0.02) scores 0."""
    th, tw = tpl.shape
    h, w = img.shape
    if h < th or w < tw:
        return np.zeros((0, 0), np.float32)
    tz = tpl.astype(np.float64) - float(tpl.mean())
    tn = float(np.sqrt((tz * tz).sum())) or 1.0
    fh, fw = _fast_len(h), _fast_len(w)
    spec = np.fft.rfft2(img, (fh, fw)) * np.conj(np.fft.rfft2(tz, (fh, fw)))
    corr = np.fft.irfft2(spec, (fh, fw))[: h - th + 1, : w - tw + 1]
    i64 = img.astype(np.float64)
    s1 = np.pad(i64, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s2 = np.pad(i64 * i64, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def win(s: Any) -> Any:
        return s[th:, tw:] - s[:-th, tw:] - s[th:, :-tw] + s[:-th, :-tw]

    n = th * tw
    var = win(s2) - win(s1) ** 2 / n
    out = corr / (np.sqrt(np.maximum(var, 1e-12)) * tn)
    out[var < (0.02**2) * n] = 0.0
    res: Floats = out.astype(np.float32)
    return res


def read(frame_bgr: Image, tpl: Floats, roi: Sequence[int] = ROI) -> MissRead:
    """PURE: the Miss cue on one game-region frame (BGR or BGRA, 1280 x 720)."""
    x0, y0, x1, y1 = roi
    f = feature(frame_bgr[y0:y1, x0:x1])
    ink = int((f >= INK).sum())
    if ink < MIN_INK:
        return MissRead(0.0, None, None, ink)
    s = ncc_map(f, tpl)
    if s.size == 0:
        return MissRead(0.0, None, None, ink)
    k = int(np.argmax(s))
    yy, xx = divmod(k, s.shape[1])
    th, tw = tpl.shape
    return MissRead(round(float(s.flat[k]), 4), x0 + xx + tw // 2, y0 + yy + th // 2, ink)


_TPL: dict[str, Floats] = {}


def load_template(path: Path = TEMPLATE) -> Floats:
    """The cut template (cached per path). Raises FileNotFoundError until ``cut`` has run."""
    key = str(path)
    if key not in _TPL:
        _TPL[key] = np.load(path).astype(np.float32)
    return _TPL[key]


def miss_score(frame_bgr: Image, tpl: Floats | None = None) -> float:
    """PURE given the template: the cue's score on one frame (0..1)."""
    return read(frame_bgr, load_template() if tpl is None else tpl).score


def miss_over_us(frame_bgr: Image, tpl: Floats | None = None, threshold: float = THRESHOLD
                 ) -> bool:  # fmt: skip
    """PURE given the template: True when a monster's "Miss" is drawn in the band around us."""
    return miss_score(frame_bgr, tpl) >= threshold


# --- truth from the packets (PURE) ---------------------------------------------------------------


def _t(e: Mapping[str, Any]) -> int:
    return int(e["t_mono_ns"])


def truth_events(packets: Iterable[Mapping[str, Any]], runner: Iterable[Mapping[str, Any]] = ()
                 ) -> dict[str, list[int]]:  # fmt: skip
    """PURE: event times (ns) by class: miss (a monster's swing at us that missed), hit_on_us,
    lucky, our_attack (our damaging acts), potion, notice (pickup results, chat lines), level, and
    steal (the runner's own steal events, its t_ns: the same host monotonic clock)."""
    out: dict[str, list[int]] = defaultdict(list)
    for e in packets:
        ty = e.get("type")
        if ty == "act":
            kind = e.get("kind")
            if kind in ("pickup", "sit", "stand"):
                continue
            dmg = int(e.get("damage") or 0)
            if e.get("target_gid") == AID:
                if kind == "lucky_dodge":
                    out["lucky"].append(_t(e))
                elif dmg == 0:
                    out["miss"].append(_t(e))
                else:
                    out["hit_on_us"].append(_t(e))
            elif e.get("src_gid") == AID:
                out["our_attack" if dmg > 0 else "our_miss"].append(_t(e))
        elif ty == "use_item_result":
            out["potion"].append(_t(e))
        elif ty in ("pickup_result", "chat"):
            out["notice"].append(_t(e))
        elif ty == "stat_change" and e.get("name") in ("base_level", "job_level"):
            out["level"].append(_t(e))
    for e in runner:
        if e.get("kind") in ("steal", "press") and (e.get("kind") == "steal"
                                                    or e.get("what") == "steal"):  # fmt: skip
            out["steal"].append(int(e["t_ns"]))
    return {k: sorted(v) for k, v in out.items()}


def _within(ts: Sequence[int], t: int, lo_s: float, hi_s: float) -> bool:
    """PURE: an event of ``ts`` lies lo_s..hi_s seconds BEFORE t (t - event in [lo, hi])."""
    i = bisect.bisect_left(ts, t - int(hi_s * NS))
    return i < len(ts) and ts[i] <= t - int(lo_s * NS)


def label(t: int, ev: Mapping[str, Sequence[int]]) -> str:
    """PURE: a frame's class at capture time t:
    - "pos": a miss's packet lies VISIBLE_FROM_S..VISIBLE_TO_S before it (its text on screen);
    - "skip": a miss lies MAYBE_FROM_S..MAYBE_TO_S before it (its text may be just appearing or
      fading: not judged);
    - else a hard-negative class of HARD (no Miss can be on screen, something else is), in order;
    - "fight": an act on us within NEG_GAP_S (a fight scene: sprites swinging, no Miss on screen);
    - "neg": nothing of the above."""
    miss = ev.get("miss", ())
    if _within(miss, t, VISIBLE_FROM_S, VISIBLE_TO_S):
        return "pos"
    if _within(miss, t, MAYBE_FROM_S, MAYBE_TO_S):
        return "skip"
    for cls, (lo, hi) in HARD.items():
        if _within(ev.get(cls, ()), t, lo, hi):
            return cls
    on_us = sorted([*miss, *ev.get("hit_on_us", ()), *ev.get("lucky", ())])
    if _within(on_us, t, -NEG_GAP_S, NEG_GAP_S):
        return "fight"
    return "neg"


# --- the gain estimate from the packets (PURE given time_budget's engagements) -------------------


def engagement_gain(eng: Mapping[str, Any], theirs: Sequence[tuple[int, int, int]],
                    delay_s: float, recall: float, post_s: float) -> dict[str, Any]:  # fmt: skip
    """PURE: one engagement the monster opened (time_budget: approach_by "attacked"):
    - today: the trigger is the first HIT on us (any monster) in [t_approach, t_respond];
    - with the cue: the first swing (any monster, hit or miss) in that span whose text is seen;
      each miss is seen with probability ``recall`` (expected value over the swing order), a hit
      always (today's trigger stays), MISS_DELAY_S-like ``delay_s`` after its packet;
    - the response moves earlier by the trigger's gain, the time after the trigger kept (today's
      t_respond - first hit; ``post_s`` when today had no hit before the response), never later.
    Damage saved = the damage on us between the new response and today's."""
    ta, tr = int(eng["t_approach"]), int(eng["t_respond"])
    sw = [(t, d) for t, _s, d in theirs if ta <= t <= tr]
    hit = next((t for t, d in sw if d > 0), None)
    post = (tr - hit) / NS if hit is not None else post_s
    # expected new trigger: swing k (a miss) is the first one seen with prob (1-r)^k * r
    p_none, exp_t = 1.0, 0.0
    for t, d in sw:
        p = 1.0 if d > 0 else recall
        exp_t += p_none * p * ((t - ta) / NS + delay_s)
        p_none *= 1.0 - p
        if p_none <= 1e-9:
            break
    old_resp = (tr - ta) / NS
    exp_t += p_none * old_resp  # never seen: today's response
    new_resp = min(old_resp, exp_t + post)
    t_new = ta + int(new_resp * NS)
    saved = sum(d for t, d in sw if t_new < t <= tr)
    return {
        "react_s": round(old_resp, 3), "new_react_s": round(new_resp, 3),
        "gain_s": round(old_resp - new_resp, 3),
        "first_hit_s": None if hit is None else round((hit - ta) / NS, 3),
        "swings": len(sw), "misses_before_hit": sum(1 for t, d in sw
                                                    if d == 0 and (hit is None or t < hit)),
        "damage_unanswered": sum(d for _t_, d in sw), "damage_saved": saved,
    }  # fmt: skip


# --- loading (not pure) --------------------------------------------------------------------------


def rec_dir(sid: str) -> Path:
    if sid.rsplit("-", 1)[-1] in HELD_BACK and not _OPEN_HELD_BACK[0]:
        raise SystemExit(f"{sid}: held back for the detector's TEST2, never opened here")
    d = REC / sid
    return d if (d / "manifest.json").exists() else NAS / sid


def shard_index(sid: str) -> list[dict[str, Any]]:
    """[{t, frame_id, shard, off, size}] in time order: the PNG offsets of a recording's tar shards
    (headers only are read; cached in RAM under CACHE)."""
    cache = CACHE / "idx" / f"{sid}.json"
    if cache.exists():
        return json.loads(cache.read_text())["frames"]  # type: ignore[no-any-return]
    d = rec_dir(sid)
    man = json.loads((d / "manifest.json").read_text())
    rows: dict[str, dict[str, Any]] = {}
    for sh in man["shards"]:
        with open(d / sh, "rb") as fh, tarfile.open(fileobj=fh, mode="r:") as tar:
            for mem in tar:
                key, _, ext = mem.name.partition(".")
                r = rows.setdefault(key, {})
                if ext == "png":
                    r.update(shard=sh, off=mem.offset_data, size=mem.size)
                elif ext == "json":
                    f = tar.extractfile(mem)
                    assert f is not None
                    meta = json.loads(f.read())
                    r.update(frame_id=meta["frame_id"], t=meta["t_mono_ns"])
    frames = sorted((r for r in rows.values() if "off" in r and "t" in r), key=lambda r: r["t"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"session": sid, "dir": str(d), "frames": frames}))
    return frames


def load_frame(sid: str, row: Mapping[str, Any]) -> Image:
    from poring_dataset.shards import decode_png

    with open(rec_dir(sid) / row["shard"], "rb") as fh:
        fh.seek(int(row["off"]))
        return decode_png(fh.read(int(row["size"])))


def load_packets(sid: str) -> list[dict[str, Any]]:
    with gzip.open(rec_dir(sid) / "packets.jsonl.gz", "rt") as fh:
        return sorted((json.loads(x) for x in fh), key=_t)


def _stamp_s(name: str) -> float:
    """PURE: a session name's leading YYYYmmddTHHMMSS as epoch seconds (UTC; only differences)."""
    import calendar

    return float(calendar.timegm(time.strptime(name[:15], "%Y%m%dT%H%M%S")))


def runner_events(sid: str) -> list[dict[str, Any]]:
    """The runner's events of the same run (its demo session: same tag, started within 10 s)."""
    tag = sid.rsplit("-", 1)[-1]
    if not DEMO.exists():
        return []
    for d in sorted(DEMO.iterdir()):
        if not (d.name.endswith(f"-{tag}") and "-demo-dungeon" in d.name):
            continue
        if abs(_stamp_s(d.name) - _stamp_s(sid)) <= 10 and (d / "events.jsonl").exists():
            return [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if x]
    return []


# --- CLI -----------------------------------------------------------------------------------------


def _positive_rows(sid: str, lo: float, hi: float) -> list[dict[str, Any]]:
    ev = truth_events(load_packets(sid))
    return [r for r in shard_index(sid) if _within(ev.get("miss", ()), int(r["t"]), lo, hi)]


def cmd_cut(a: argparse.Namespace) -> int:
    sid, fid, xy = a.seed.split(":")
    x, y = (int(v) for v in xy.split(","))
    rows = {int(r["frame_id"]): r for r in shard_index(sid)}
    th, tw = TEMPLATE_HW
    seed = feature(load_frame(sid, rows[int(fid)])[y : y + th, x : x + tw])
    tpl = seed
    picks: list[dict[str, Any]] = []
    for it in range(a.iterations):
        acc = np.zeros(TEMPLATE_HW, np.float64)
        picks = []
        sessions = a.sessions.split(",")
        cap = max(1, a.max_n // len(sessions))  # the same share from every session
        for s in sessions:
            if s not in TUNE:
                raise SystemExit(f"{s}: the template is cut from TUNE sessions only")
            n0 = len(picks)
            for r in _positive_rows(s, VISIBLE_FROM_S - 0.2, VISIBLE_TO_S + 0.4):
                img = load_frame(s, r)
                x0, y0, x1, y1 = ROI
                f = feature(img[y0 - 40 : y1, x0 - 40 : x1 + 40])
                m = ncc_map(f, tpl)
                k = int(np.argmax(m))
                yy, xx = divmod(k, m.shape[1])
                if float(m.flat[k]) < a.min_score:
                    continue
                acc += f[yy : yy + th, xx : xx + tw]
                picks.append({"session": s, "frame_id": int(r["frame_id"]),
                              "x": x0 - 40 + xx, "y": y0 - 40 + yy,
                              "score": round(float(m.flat[k]), 3)})  # fmt: skip
                if len(picks) - n0 >= cap:
                    break
        if not picks:
            raise SystemExit("no instance matched the seed")
        tpl = (acc / len(picks)).astype(np.float32)
        print(f"iteration {it + 1}: {len(picks)} instances", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "template.npy", tpl)
    (out / "template.json").write_text(json.dumps({
        "seed": a.seed, "sessions": a.sessions.split(","), "n": len(picks),
        "iterations": a.iterations, "min_score": a.min_score, "roi": ROI,
        "feature": {"lo": FEAT_LO, "span": FEAT_SPAN}, "shape": list(tpl.shape),
        "instances": picks, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }, indent=1))  # fmt: skip
    print(f"template {tpl.shape} from {len(picks)} instances -> {out}/template.npy")
    for row in tpl:
        print("".join(" .:-=+*#%@"[min(9, int(v * 10))] for v in row))
    return 0


def score_session(sid: str, tpl: Floats, every: int = 1) -> list[dict[str, Any]]:
    pk = load_packets(sid)
    ev = truth_events(pk, runner_events(sid))
    out = []
    for r in shard_index(sid)[::every]:
        t = int(r["t"])
        cls = label(t, ev)  # "skip" frames are scored too: the labels can be re-cut offline
        m = read(load_frame(sid, r), tpl)
        out.append({"t": t, "frame_id": r["frame_id"], "cls": cls, "score": m.score,
                    "x": m.x, "y": m.y})  # fmt: skip
    return out


def summarise(rows: Sequence[Mapping[str, Any]], threshold: float) -> dict[str, Any]:
    """PURE: per class: frames, fired, rate; negatives: FP per minute at the recordings' 1 fps."""
    by: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r["cls"] != "skip":
            by[str(r["cls"])].append(float(r["score"]))
    out: dict[str, Any] = {"threshold": threshold}
    for cls, v in sorted(by.items()):
        fired = sum(s >= threshold for s in v)
        out[cls] = {"frames": len(v), "fired": fired, "rate": round(fired / len(v), 4)}
    ts = sorted(int(r["t"]) for r in rows if r["cls"] == "neg")
    gaps = [b - a for a, b in zip(ts, ts[1:], strict=False) if 0 < b - a < 3 * NS]
    sec = statistics.median(gaps) / NS if gaps else 1.0
    if "neg" in out:
        mins = out["neg"]["frames"] * sec / 60
        out["neg"]["minutes"] = round(mins, 1)
        out["neg"]["fp_per_min"] = round(out["neg"]["fired"] / mins, 3) if mins else None
    return out


def cmd_validate(a: argparse.Namespace) -> int:
    tpl = load_template(Path(a.template))
    if a.split == "test2" and not a.open_held_back:
        raise SystemExit("test2 is held back: pass --open-held-back (the parent's final check)")
    _OPEN_HELD_BACK[0] = a.split == "test2"
    sids = {"tune": TUNE, "test": TEST, "test2": TEST2}[a.split]
    rows: list[dict[str, Any]] = []
    per: dict[str, Any] = {}
    for sid in sids:
        t0 = time.time()
        rs = score_session(sid, tpl, a.every)
        for r in rs:
            r["session"] = sid
        rows += rs
        per[sid] = summarise(rs, a.threshold)
        print(sid, round(time.time() - t0, 1), "s", json.dumps(per[sid]), flush=True)
    res = {"split": a.split, "sessions": list(sids), "threshold": a.threshold,
           "pooled": summarise(rows, a.threshold), "per_session": per}  # fmt: skip
    sweep = {}
    for th in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
        s = summarise(rows, th)
        sweep[str(th)] = {k: (v["rate"] if isinstance(v, dict) else v) for k, v in s.items()}
    res["sweep"] = sweep
    print(json.dumps(res["pooled"], indent=1))
    print(json.dumps(sweep, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps({**res, "rows": rows}))
    return 0


def cmd_latency(a: argparse.Namespace) -> int:
    tpl = load_template(Path(a.template))
    rows = shard_index(a.session)
    step = max(1, len(rows) // a.n)
    imgs = [load_frame(a.session, r) for r in rows[::step][: a.n]]
    ms = []
    for img in imgs:
        t = time.perf_counter()
        read(img, tpl)
        ms.append((time.perf_counter() - t) * 1000)
    ms.sort()

    def q(f: float) -> float:
        return round(ms[int(f * (len(ms) - 1))], 2)

    print(json.dumps({"n": len(ms), "ms_p50": q(0.5), "ms_p90": q(0.9), "ms_p99": q(0.99),
                      "ms_max": round(ms[-1], 2)}))  # fmt: skip
    return 0


def event_recall(frames: Sequence[tuple[int, float]], misses: Sequence[int],
                 on_us: Sequence[int], threshold: float, quiet_s: float = 3.0
                 ) -> dict[str, Any]:  # fmt: skip
    """PURE: per-EVENT recall on a 5 Hz recording. The judged events are the misses on us with no
    act on us in the quiet_s before them (the first swing of an attack: the trigger's case); an
    event is seen when a frame VISIBLE_FROM_S - 0.1 .. VISIBLE_TO_S + 0.2 after it fires (frames
    after the NEXT act on us + MISS_DELAY_S are left out: they may show that one's text). The
    latency is from the packet to the first firing frame."""
    ft = [t for t, _s in frames]
    seen, lat, judged = 0, [], 0
    for t in misses:
        i = bisect.bisect_left(on_us, t)
        if i > 0 and t - on_us[i - 1] < quiet_s * NS:
            continue
        nxt = on_us[i + 1] if i + 1 < len(on_us) else None
        lo = t + int((VISIBLE_FROM_S - 0.1) * NS)
        hi = t + int((VISIBLE_TO_S + 0.2) * NS)
        if nxt is not None:
            hi = min(hi, nxt + int(MISS_DELAY_S * NS))
        if hi <= lo:
            continue
        judged += 1
        j = bisect.bisect_left(ft, lo)
        while j < len(ft) and ft[j] <= hi:
            if frames[j][1] >= threshold:
                seen += 1
                lat.append((ft[j] - t) / NS)
                break
            j += 1
    return {
        "events": judged,
        "seen": seen,
        "recall": round(seen / judged, 3) if judged else None,
        "latency_s_median": round(statistics.median(lat), 2) if lat else None,
        "latency_s_p90": round(sorted(lat)[int(0.9 * (len(lat) - 1))], 2) if lat else None,
    }


def cmd_demo(a: argparse.Namespace) -> int:
    """Batt's human demo (5 Hz JPEG q80 frames on the NAS): per-event recall at the runner's rate
    and FP per minute on its negative frames. JPEG lowers the scores: a conservative check."""
    from PIL import Image as PILImage

    tpl = load_template(Path(a.template))
    d = DEMO / a.session
    man = json.loads((d / "manifest.json").read_text())
    fdir = Path(man["frames_dir"])
    with gzip.open(d / "packets.jsonl.gz", "rt") as fh:
        ev = truth_events(json.loads(x) for x in fh)
    names = sorted(p.name for p in fdir.iterdir() if p.suffix == ".jpg")
    rows: list[dict[str, Any]] = []
    for nm in names:
        t = int(nm.split("-")[1].split(".")[0])
        cls = label(t, ev)
        img = np.asarray(PILImage.open(fdir / nm).convert("RGB"))[:, :, ::-1]
        rows.append({"t": t, "cls": cls, "score": read(img, tpl).score})
    on_us = sorted([*ev.get("miss", ()), *ev.get("hit_on_us", ()), *ev.get("lucky", ())])
    frames = [(int(r["t"]), float(r["score"])) for r in rows]
    res = {"session": a.session, "frames": len(rows), "codec": "jpeg q80 (5 Hz)",
           "per_frame": {str(th): summarise([r for r in rows if r["cls"] != "skip"], th)
                         for th in (a.threshold, 0.6, 0.65)},
           "per_event": {str(th): event_recall(frames, ev.get("miss", ()), on_us, th)
                         for th in (a.threshold, 0.6, 0.65)},
           "lucky_events": {str(th): event_recall(frames, ev.get("lucky", ()), on_us, th)
                            for th in (a.threshold, 0.6)}}  # fmt: skip
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


GAIN_RUNS = ("a2", "a3", "a4", "a7", "a8", "a5b", "b1", "c1", "c2", "c3")


def cmd_gain(a: argparse.Namespace) -> int:
    import dungeon_judge as dj
    import time_budget as tb

    sids = [d.name for d in sorted(DEMO.iterdir())
            if "-demo-dungeon-rogue-gef_fild10-" in d.name
            and d.name.rsplit("-", 1)[-1] in GAIN_RUNS]  # fmt: skip
    per_run: dict[str, Any] = {}
    allg: list[dict[str, Any]] = []
    for sid in sids:
        ev, pk, man = dj.load(sid)
        t0, t1, _src = dj.window(ev, man, pk)
        eng = tb.engagements(pk, t0, t1, tb.Track(pk))
        eng = [e for e in eng if e["approach_by"] == "attacked"]  # it swung first
        _ours, theirs = tb.acts(pk, tb.monsters(pk))
        posts = []
        for e in eng:
            hit = next((t for t, _s, d in theirs
                        if e["t_approach"] <= t <= e["t_respond"] and d > 0), None)  # fmt: skip
            if hit is not None:
                posts.append((e["t_respond"] - hit) / NS)
        post_s = statistics.median(posts) if posts else 5.0
        gs = [engagement_gain(e, theirs, a.delay, a.recall, post_s) for e in eng]
        allg += gs
        per_run[sid.rsplit("-", 1)[-1]] = _gain_stats(gs, (t1 - t0) / NS)
    res = {"delay_s": a.delay, "recall": a.recall, "runs": per_run,
           "pooled": _gain_stats(allg, None)}  # fmt: skip
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    return 0


def _gain_stats(gs: Sequence[Mapping[str, Any]], seconds: float | None) -> dict[str, Any]:
    def med(k: str, rows: Sequence[Mapping[str, Any]] = gs) -> float | None:
        v = [float(r[k]) for r in rows if r[k] is not None]
        return round(statistics.median(v), 2) if v else None

    hit = [g for g in gs if g["first_hit_s"] is not None]
    saved = sum(int(g["damage_saved"]) for g in gs)
    out: dict[str, Any] = {
        "engagements_opened_by_monster": len(gs),
        "with_a_hit_before_our_response": len(hit),
        "react_s_median": med("react_s"), "new_react_s_median": med("new_react_s"),
        "gain_s_median": med("gain_s"), "gain_s_mean": round(statistics.mean(
            [float(g["gain_s"]) for g in gs]), 2) if gs else None,
        "first_hit_after_first_swing_s_median": med("first_hit_s", hit),
        "misses_before_first_hit_median": med("misses_before_hit", hit),
        "damage_unanswered_total": sum(int(g["damage_unanswered"]) for g in gs),
        "damage_saved_total": saved,
    }  # fmt: skip
    if seconds:
        out["damage_saved_per_hour"] = round(saved * 3600 / seconds)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut")
    c.add_argument("--seed", required=True, help="SESSION:FRAME_ID:X,Y (the text's top-left - 2)")
    c.add_argument("--sessions", default=",".join(TUNE))
    c.add_argument("--out", default=str(OUT_DIR))
    c.add_argument("--min-score", type=float, default=0.75)
    c.add_argument("--max-n", type=int, default=400)
    c.add_argument("--iterations", type=int, default=2)
    v = sub.add_parser("validate")
    v.add_argument("--split", choices=("tune", "test", "test2"), required=True)
    v.add_argument("--open-held-back", action="store_true", help="test2 only: the parent's step")
    v.add_argument("--template", default=str(TEMPLATE))
    v.add_argument("--threshold", type=float, default=THRESHOLD)
    v.add_argument("--every", type=int, default=1)
    v.add_argument("--out")
    lt = sub.add_parser("latency")
    lt.add_argument("--session", default=TUNE[0])
    lt.add_argument("--template", default=str(TEMPLATE))
    lt.add_argument("--n", type=int, default=200)
    dm = sub.add_parser("demo")
    dm.add_argument("--session", default="20261026T095021-demo-human-demo-gef10")
    dm.add_argument("--template", default=str(TEMPLATE))
    dm.add_argument("--threshold", type=float, default=THRESHOLD)
    dm.add_argument("--out")
    g = sub.add_parser("gain")
    g.add_argument("--delay", type=float, default=MISS_DELAY_S + 0.2)
    g.add_argument("--recall", type=float, default=0.5)
    g.add_argument("--out")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "packages" / "poring_dataset" / "src"))
    return int({"cut": cmd_cut, "validate": cmd_validate, "latency": cmd_latency,
                "demo": cmd_demo, "gain": cmd_gain}[a.cmd](a))  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
