#!/usr/bin/env python3
"""SCREEN-ONLY RUN RECORDS (Batt 2026-11-21, decision 2 = A: "a screen-only economy record for
every Run"). The packet judge (econ_dash.judge_session) needs the run's packets.jsonl.gz: a Run on a
PC the lab's sniffer does not capture (the live lab's, a learner's) has none, and every such record
was refused (the live lab's 21 Runs 11-20 09:41 .. 11-21 07:42: lab.sqlite 0 runs). A screen record
is what the bot itself read and did, from its session's events.jsonl:

- the window: run_start .. run_end (else the first .. last event), and its hours;
- kills (the runner's own kill events, by how each was read), deaths;
- loot steps, the picks they counted, the pickup clicks;
- the presses by role: Fly Wing, Butterfly Wing, potion; steals (the Knife swap's popups);
- the hotbar stock reads (first / last count per item) and the bag's weight at the start and end
  (the player's own reads, its *-play-<label> session).

NOT known from the screen: which items dropped or were picked, and the zeny. The page says so; a
screen record never pretends to be a packet record ("source": "screen"). The Fly Wing and the
Butterfly Wing are one item each (their role names it), so their use is priced from the item table;
a potion's item depends on the player's heal key, so potions are counted, not priced.

PURE functions (judge, entry, pool) and two loaders (load_session, play_events_of).
"""

from __future__ import annotations

import gzip
import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

SOURCE = "screen"
EXPORT_NAME = "screen-runs"  # the /economy page's export of every screen record (newest first)
EXPORT_MAX_RUNS = 200
NS = 1_000_000_000
FLY_WING, BUTTERFLY_WING = 601, 602
PRESS_ITEMS = {"fly": FLY_WING, "home": BUTTERFLY_WING}  # a press whose role names ONE item
SOURCE_WHY = (
    "screen only: read from the game screen, not verified by packets (no packet capture for this "
    "Run); which items were picked and the zeny are not known"
)
SCREEN_SUMS = ("loot_steps", "loot_picks", "pickup_clicks", "potions", "fly_wings",
               "butterfly_wings", "steals")  # fmt: skip


def _t(e: Mapping[str, Any]) -> int | None:
    t = e.get("t_ns")
    return t if isinstance(t, int) and not isinstance(t, bool) else None


def _int(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def judge(
    name: str,
    events: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    play_events: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """PURE: one hunt session's screen record. Raises ValueError when no event has a time."""
    import econ_dash as ed

    ev = list(events)
    ts = [t for e in ev if (t := _t(e)) is not None]
    if not ts:
        raise ValueError(f"{name}: no event with a time")
    rs = next((e for e in ev if e.get("kind") == "run_start" and _t(e) is not None), None)
    re_ = next((e for e in reversed(ev) if e.get("kind") == "run_end" and _t(e) is not None), None)
    t0 = _t(rs) if rs is not None else None
    t1 = _t(re_) if re_ is not None else None
    source = "run_start..run_end" if t0 is not None and t1 is not None else "first..last event"
    t0 = min(ts) if t0 is None else t0
    t1 = max(ts) if t1 is None or t1 < t0 else t1
    win = [e for e in ev if (t := _t(e)) is not None and t0 <= t <= t1]
    kinds = Counter(str(e.get("kind")) for e in win)
    presses = Counter(str(e.get("what")) for e in win if e.get("kind") == "press")
    kills_by = Counter(str(e.get("by") or "?") for e in win if e.get("kind") == "kill")
    steals = sum(1 for e in win if e.get("kind") == "press"
                 and e.get("what") == "equip" and e.get("why") == "popup")  # fmt: skip
    deaths = kinds["death"] or int(any(e.get("kind") == "player_end" and e.get("dead") for e in ev))
    stock: dict[str, dict[str, int]] = {}
    for e in win:
        if e.get("kind") == "stock" and isinstance(e.get("count"), int):
            s = stock.setdefault(str(_int(e.get("item"))), {"first": e["count"], "reads": 0})
            s["last"], s["reads"] = e["count"], s["reads"] + 1
    w = weight_ends(play_events, t0, t1)
    if w == [None, None]:  # the runner's own weight reads (a share of the most she can carry)
        rw = [round(float(e["share"]) * 100, 1) for e in win
              if e.get("kind") == "weight"
              and isinstance(e.get("share"), (int, float))]  # fmt: skip
        w = [rw[0], rw[-1]] if rw else w
    clock = ed.run_clock(name, ev, {"t0": t0, "t1": t1}, manifest)
    return {
        "session": name,
        "source": SOURCE,
        "map": (rs or {}).get("map") or manifest.get("map"),
        "char": (rs or {}).get("char") or manifest.get("char"),
        "strategy": (rs or {}).get("strategy") or manifest.get("strategy"),
        "version": manifest.get("version") or (rs or {}).get("version"),
        "window": {"t0": t0, "t1": t1, "source": source},
        "minutes": round((t1 - t0) / NS / 60, 3),
        "hours": (t1 - t0) / NS / 3600,
        "kills": kinds["kill"],
        "kills_by": dict(sorted(kills_by.items())),
        "deaths": deaths,
        "loot_steps": kinds["loot_step"],
        "loot_picks": sum(_int(e.get("picks")) for e in win if e.get("kind") == "loot_step"),
        "pickup_clicks": kinds["loot_click"],
        "presses": dict(sorted(presses.items())),
        "potions": presses["potion"],
        "fly_wings": presses["fly"],
        "butterfly_wings": presses["home"],
        "steals": steals,
        "stock": stock,
        "weight_start": w[0],
        "weight_end": w[1],
        "end": None if re_ is None else str(re_.get("reason") or "")[:300] or None,
        "started": clock["started"],
        "ended": clock["ended"],
        "flow": clock["flow"],
    }


WEIGHT_NEAR_S = 900  # a player's bag read counts for a hunt's start / end within this many s


def weight_ends(play_events: Iterable[Mapping[str, Any]], t0: int, t1: int) -> list[float | None]:
    """PURE: the bag's weight (%) at a hunt core's start and end from the PLAYER's reads: it reads
    the bag around each hunt core, not inside it (11-21: 38 % just before, 50 % just after). The
    last read at or before ``t0`` (else the first inside), the first at or after ``t1`` (else the
    last inside), each within WEIGHT_NEAR_S; None when there is none."""
    reads = sorted((t, float(e["weight_pct"])) for e in play_events
                   if e.get("kind") == "hp_read" and isinstance(e.get("weight_pct"), (int, float))
                   and not isinstance(e.get("weight_pct"), bool)
                   and (t := _t(e)) is not None)  # fmt: skip
    near = WEIGHT_NEAR_S * NS
    before = [w for t, w in reads if t0 - near <= t <= t0]
    inside = [w for t, w in reads if t0 < t < t1]
    after = [w for t, w in reads if t1 <= t <= t1 + near]
    start = before[-1] if before else (inside[0] if inside else None)
    end = after[0] if after else (inside[-1] if inside else None)
    return [start, end]


def screen_block(j: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the page's "screen" block of a record (what only a screen record carries)."""
    keys = ("kills_by", *SCREEN_SUMS, "presses", "stock", "weight_start", "weight_end", "end")
    return {k: j.get(k) for k in keys}


def entry(
    j: Mapping[str, Any], table: Mapping[str, Mapping[str, Any]], names: Mapping[str, str]
) -> dict[str, Any]:
    """PURE: a screen record as a /economy run entry (the packet entries' shape: no items, no
    species; the Fly Wing and Butterfly Wing uses priced) with its "screen" block."""
    import econ_dash as ed

    used = [PRESS_ITEMS[w] for w, n in (j.get("presses") or {}).items() if w in PRESS_ITEMS
            for _ in range(int(n))]  # fmt: skip
    cons, no_price = ed.consumable_rows(used, table, names)
    why: dict[str, Any] = {"source": SOURCE_WHY}
    if j.get("potions"):
        why["potions"] = (
            "the heal key's item is not named on a screen record: the potions are counted "
            "(screen.potions), not priced"
        )
    if no_price:
        why["consumables_no_price"] = f"no loaded NPC sells item(s) {no_price}: not in the cost"
    w = j["window"]
    out: dict[str, Any] = {
        "session": j.get("session"),
        "source": SOURCE,
        "dir": None,
        "map": j.get("map"),
        "char": j.get("char"),
        "strategy": j.get("strategy"),
        "version": j.get("version"),
        "window": {"t0_ns": int(w["t0"]), "t1_ns": int(w["t1"]), "source": w["source"]},
        "started": j.get("started"),
        "ended": j.get("ended"),
        "flow": j.get("flow"),
        "minutes": j.get("minutes"),
        "hours": float(j["hours"]),
        "hours_are": "the run's window (window.source); every count here is divided by it",
        "kills": int(j["kills"]),
        "deaths": int(j.get("deaths") or 0),
        "items": [],
        "species": [],
        "consumables": cons,
        "why": why,
        "screen": screen_block(j),
    }
    out["totals"] = ed.totals(out)
    return out


def pool(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the screen runs pooled (econ_dash.pool_runs) with their screen sums."""
    import econ_dash as ed

    out = ed.pool_runs(runs)
    blocks = [r.get("screen") or {} for r in runs]
    kb: Counter[str] = Counter()
    for b in blocks:
        kb.update({str(k): _int(v) for k, v in (b.get("kills_by") or {}).items()})
    out["source"] = SOURCE
    out["screen"] = {
        **{k: sum(_int(b.get(k)) for b in blocks) for k in SCREEN_SUMS},
        "kills_by": dict(sorted(kb.items())),
        "weight_start": None,
        "weight_end": None,
        "end": None,
    }
    return out


# --- loading (not pure) -------------------------------------------------------------------------


def _lines(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict):
                yield e


def screen_dir(session: str | Path, demo: Path, store: Path) -> Path | None:
    """The session's directory when it is a SCREEN session: its events.jsonl is there and no
    packets.jsonl.gz is, neither beside it nor in the store's copy. None: a packet session (or
    none at all), which the packet judge takes."""
    p = Path(session)
    cands = [p] if p.is_absolute() or p.is_dir() else []
    cands += [demo / p.name, store / p.name]
    d = next((c for c in cands if (c / "events.jsonl").is_file()), None)
    if d is None or any(
        (c / "packets.jsonl.gz").exists() for c in {d, demo / p.name, store / p.name}
    ):
        return None
    return d


def play_events_of(d: Path) -> list[dict[str, Any]]:
    """The player's own record beside a box Run's hunt core (``*-play-<label>`` for
    ``*-<label>-hunt<n>``): its hp_read lines only (the bag's weight); [] when there is none."""
    m = re.search(r"-(flowplay-[A-Za-z0-9_.-]+?)-hunt\d+$", d.name)
    if not m:
        return []
    for p in sorted(d.parent.glob(f"*-play-{m.group(1)}")):
        f = p / "events.jsonl"
        if f.is_file():
            return [e for e in _lines(f) if e.get("kind") == "hp_read" and "weight_pct" in e]
    return []


def load_session(d: Path) -> dict[str, Any]:
    """The screen record of the session directory ``d`` (judge over its files)."""
    try:
        manifest = json.loads((d / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    return judge(d.name, _lines(d / "events.jsonl"), manifest if isinstance(manifest, dict) else {},
                 play_events_of(d))  # fmt: skip
