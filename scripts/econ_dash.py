#!/usr/bin/env python3
"""THE ECONOMY DASHBOARD's export (Batt 2026-11-11: "make a dashboard page of business results
(P&L), because I will teach economics too"): per run AND pooled, the COUNTS the console's
/economy page shows and recomputes its P&L from. OFFLINE: it reads banked session files only and
writes one JSON under data/ (gitignored); nothing here reaches a bot.

    econ_dash.py export SESSION [SESSION ...] --name NAME [--map MAP] [--data DIR] [--out-dir DIR]
    econ_dash.py list [--out-dir DIR]

SESSION: a session DIRECTORY (events.jsonl, packets.jsonl.gz, manifest.json; e.g. an archived run
under the NAS's scratch-archive/<date>/demo-sessions/) or a session id (dungeon_judge.session_dir:
/dev/shm while fresh, else the NAS). NAME: [A-Za-z0-9][A-Za-z0-9_.-]{0,63}; the file is
<out-dir>/NAME.json (default data/econ/dashboard/, which the backend serves read-only at
GET /economy/data/NAME).

EVERY NUMBER comes from the existing judges (docs/econ/economics.md); nothing is re-derived:
- the window (hours), kills, deaths and every item GAIN by its cause: dungeon_judge.judge (a
  dungeon run: run_start..run_end; a survival trial: its manifest's times). picked = a gain
  <= 2 s after our pickup request; stolen = Steal (a gain <= 1.5 s after a Steal's SP fall) +
  Snatcher (a gain <= 1 s after our own attack act, dungeon@8); "other" and "staged" gains are
  listed and are NOT income (dungeon_judge.INCOME);
- the drops of OUR kills per item, and how many of them our pickups took: dungeon_judge.kills_loot
  (the very kill rows judge measures; amounts from econ_row.floor_amounts);
- kills per species: econ_row.measure's kill_mix (econ_row.kill_species: the job of the latest
  monster appear before the kill);
- consumables per item: econ_row.uses (OUR use_item_result successes, aid filter), the kind from
  econ_row.consumable_kind (by item id and the db type);
- prices from econ_items' table (data/econ/items.json): `sell` (NPC sell, 0 when Trade NoSell),
  `sell_oc10` (Overcharge Lv 10), `npc_buy` (the cheapest loaded shop), `npc_buy_dc10` (Discount
  Lv 10 at the cheapest shop that gives it), `weight`, `type`;
- display names from the KB (data/kb/items.json, data/kb/mobs.json), else the item table. Names
  are run-time data in whatever language the server's data has: the export never matches one.

Everything here is identified by NUMERIC id. Item / monster names and prices are GPL- or
client-derived run-time data (CLAUDE.md rule 4): written to data/ only, never committed.
Missing data is null with the reason in "why" -- never invented.

The export carries COUNTS (and the hours they are divided by), not only rates, so the page can
recompute every rate with prices a person edits in the browser. It also carries this script's own
totals, cross-checked against dungeon_judge's item value and econ_row's costs on every export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCHEMA = "poring-lab.econ-dashboard.v1"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")  # the backend's rule too


def valid_name(name: str) -> bool:
    """PURE: an export's name: a fixed character set, no path separator, no leading dot."""
    return bool(NAME_RE.fullmatch(name))


# --- pure parts ----------------------------------------------------------------------------------


def drops_by_item(
    kill_rows: Sequence[Mapping[str, Any]],
    fates: Mapping[int, Mapping[str, Any]],
    amounts: Mapping[int, int],
) -> dict[int, dict[str, int]]:
    """PURE: item id -> {dropped: units our kills dropped, picked: of those, units our pickups
    took (fate "picked")} -- econ_row.measure's dropped_items / picked_items, per item id."""
    out: dict[int, dict[str, int]] = defaultdict(lambda: {"dropped": 0, "picked": 0})
    for r in kill_rows:
        for f in r.get("drops", ()):
            x = fates[f]
            n = int(amounts.get(f, 1))
            q = out[int(x.get("item_id") or -1)]
            q["dropped"] += n
            if x.get("fate") == "picked":
                q["picked"] += n
    return {k: dict(v) for k, v in sorted(out.items())}


def _name(iid: int, names: Mapping[str, str], table: Mapping[str, Mapping[str, Any]]) -> str | None:
    n = names.get(str(iid)) or (table.get(str(iid)) or {}).get("name")
    return None if n is None else str(n)


def item_rows(
    gains: Sequence[Mapping[str, Any]],
    drops: Mapping[int, Mapping[str, int]],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[int]]:
    """PURE: one row per item id that was gained (any cause) or dropped by our kills, with its
    counts and prices; ``gains``: dungeon_judge's items_rows. Returns (rows, unpriced ids). Rows
    are ordered by income units, then units dropped, then id (never by a name)."""
    by: dict[int, dict[str, Any]] = {}
    for g in gains:
        iid = int(g["item_id"])
        by[iid] = {
            "picked": int(g.get("picked", 0)),
            "stolen_steal": int(g.get("stolen", 0)),
            "stolen_snatcher": int(g.get("snatched", 0)),
            "other": int(g.get("other", 0)),
            "staged": int(g.get("staged", 0)),
        }
    for iid in drops:
        by.setdefault(
            int(iid),
            {"picked": 0, "stolen_steal": 0, "stolen_snatcher": 0, "other": 0, "staged": 0},
        )
    rows, unpriced = [], []
    for iid, c in by.items():
        t = table.get(str(iid))
        if t is None:
            unpriced.append(iid)
        d = drops.get(iid, {})
        stolen = c["stolen_steal"] + c["stolen_snatcher"]
        rows.append(
            {
                "item_id": iid,
                "name": _name(iid, names, table),
                "type": None if t is None else t.get("type"),
                "weight": None if t is None else t.get("weight"),
                "sellable": None if t is None else bool(t.get("sellable", True)),
                "sell": None if t is None else int(t.get("sell") or 0),
                "sell_oc": None if t is None else int(t.get("sell_oc10") or 0),
                "picked": c["picked"],
                "stolen": stolen,
                "stolen_steal": c["stolen_steal"],
                "stolen_snatcher": c["stolen_snatcher"],
                "income": c["picked"] + stolen,
                "other": c["other"],
                "staged": c["staged"],
                "dropped": int(d.get("dropped", 0)),
                "picked_of_dropped": int(d.get("picked", 0)),
            }
        )
    rows.sort(key=lambda r: (-r["income"], -r["dropped"], r["item_id"]))
    return rows, sorted(unpriced)


def species_rows(kill_mix: Mapping[str, int], mobs: Mapping[str, str]) -> list[dict[str, Any]]:
    """PURE: kills per species (econ_row's kill_mix: mob id -> kills; -1 = no monster appear
    before the kill), most kills first, then id."""
    rows = [
        {"mob_id": int(k), "name": mobs.get(str(k)), "kills": int(v)} for k, v in kill_mix.items()
    ]
    return sorted(rows, key=lambda r: (-r["kills"], r["mob_id"]))


# dungeon@9.31 (--heal-candy; Batt 2026-11-11: heal with Candy and Candy Cane, not White Potions):
# no NPC sells either, so a run eats ones it LOOTED -- their cost is the NPC sale it gives up (the
# table's `sell`; no Discount applies to a sale). Every other item no NPC sells keeps no price.
FORGONE_SALE_IDS = frozenset({529, 530})  # Candy, Candy Cane


def consumable_rows(
    used: Iterable[int], table: Mapping[str, Mapping[str, Any]], names: Mapping[str, str]
) -> tuple[list[dict[str, Any]], list[int]]:
    """PURE: one row per item id we used (econ_row.uses' ids), with the NPC buy prices; returns
    (rows, ids no NPC sells -- their cost is left out, as econ_row.measure does). The candies of
    FORGONE_SALE_IDS are priced at the NPC sale they forgo (`price_basis` says which)."""
    import econ_row as er

    n = Counter(int(i) for i in used)
    rows, no_price = [], []
    for iid, k in n.items():
        t = table.get(str(iid))
        buy = None if t is None or t.get("npc_buy") is None else int(t["npc_buy"])
        basis = "npc_buy"
        if buy is None and iid in FORGONE_SALE_IDS and t is not None and t.get("sell") is not None:
            buy, basis = int(t["sell"]), "forgone_sale"
        if buy is None:
            no_price.append(iid)
        dc = None if buy is None else int((t or {}).get("npc_buy_dc10") or buy)
        rows.append(
            {
                "item_id": iid,
                "name": _name(iid, names, table),
                "type": None if t is None else t.get("type"),
                "kind": er.consumable_kind(t, iid),
                "used": k,
                "npc_buy": buy,
                "npc_buy_dc": dc,
                "price_basis": basis if buy is not None else None,
            }
        )
    rows.sort(key=lambda r: (-r["used"], r["item_id"]))
    return rows, sorted(no_price)


def totals(run: Mapping[str, Any]) -> dict[str, Any]:
    """PURE: the P&L of one run (or the pool) at the table's prices -- the page's defaults:
    gross = sum (picked + stolen) x price, cost = sum used x price, per hour = / hours;
    net = gross - cost; best = gross at Overcharge - cost at Discount."""
    h = float(run["hours"])
    g = sum(r["income"] * r["sell"] for r in run["items"] if r["sell"] is not None)
    g_oc = sum(r["income"] * r["sell_oc"] for r in run["items"] if r["sell_oc"] is not None)
    c = sum(r["used"] * r["npc_buy"] for r in run["consumables"] if r["npc_buy"] is not None)
    c_dc = sum(
        r["used"] * r["npc_buy_dc"] for r in run["consumables"] if r["npc_buy_dc"] is not None
    )

    def ph(z: float) -> float | None:
        return round(z / h, 1) if h > 0 else None

    return {
        "income_units": sum(r["income"] for r in run["items"]),
        "picked_units": sum(r["picked"] for r in run["items"]),
        "stolen_units": sum(r["stolen"] for r in run["items"]),
        "gross": g,
        "gross_oc": g_oc,
        "cost": c,
        "cost_dc": c_dc,
        "gross_h": ph(g),
        "gross_oc_h": ph(g_oc),
        "cost_h": ph(c),
        "cost_dc_h": ph(c_dc),
        "net_h": ph(g - c),
        "net_best_h": ph(g_oc - c_dc),
        "kills_h": round(run["kills"] / h, 2) if h > 0 else None,
    }


def run_entry(
    judged: Mapping[str, Any],
    kill_rows: Sequence[Mapping[str, Any]],
    fates: Mapping[int, Mapping[str, Any]],
    packets: Sequence[Mapping[str, Any]],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    mobs: Mapping[str, str],
    where: str | None = None,
) -> dict[str, Any]:
    """PURE: one run's dashboard entry from dungeon_judge.judge's row (``judged``), the same kill
    rows and fates (dungeon_judge.kills_loot) and the packets (amounts, item uses)."""
    drops, used = counts_of(judged, kill_rows, fates, packets)
    return entry_from_counts(judged, drops, used, table, names, mobs, where)


def counts_of(
    judged: Mapping[str, Any],
    kill_rows: Sequence[Mapping[str, Any]],
    fates: Mapping[int, Mapping[str, Any]],
    packets: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, dict[str, int]], list[int]]:
    """PURE: the two counts an entry takes from the packets: our kills' drops per item id
    (drops_by_item) and the item id of each of OUR successful uses in the judged window
    (econ_row.uses)."""
    import dungeon_judge as dj
    import econ_row as er

    w = judged["window"]
    drops = drops_by_item(kill_rows, fates, er.floor_amounts(packets))
    used = [iid for _t, iid in er.uses(packets, int(w["t0"]), int(w["t1"]), dj.AID)]
    return drops, used


def entry_from_counts(
    judged: Mapping[str, Any],
    drops: Mapping[int, Mapping[str, int]],
    used: Sequence[int],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    mobs: Mapping[str, str],
    where: str | None = None,
) -> dict[str, Any]:
    """PURE: one run's dashboard entry from the judged row and its counts (counts_of) -- names and
    prices from ``table`` / ``names`` / ``mobs``. scripts/econ_db.py rebuilds an entry from its
    stored counts through this very function (ADR-0025)."""
    import dungeon_judge as dj

    why: dict[str, Any] = dict(judged.get("why") or {})
    econ = judged.get("economics") or {}
    why.update({f"econ_row.{k}": v for k, v in (econ.get("why") or {}).items()})
    w = judged["window"]
    items, unpriced = item_rows(judged.get("items") or [], drops, table, names)
    if unpriced:
        why["unpriced_items"] = (
            f"not in the item table (econ_items.py build): {unpriced}; "
            "their price is null and they are left out of the zeny"
        )
    cons, no_price = consumable_rows(used, table, names)
    if no_price:
        why["consumables_no_price"] = (
            f"no loaded NPC sells item(s) {no_price}: npc_buy is null "
            "and they are left out of the cost"
        )
    if not used:
        why["consumables"] = "no successful item use of ours in the window (use_item_result)"
    sp = species_rows(econ.get("kill_mix") or {}, mobs)
    if any(s["mob_id"] == -1 for s in sp):
        why["species_unknown"] = "a kill with no monster appear before it: species id -1"
    out: dict[str, Any] = {
        "session": judged.get("session"),
        "dir": where,
        "map": judged.get("map"),
        "char": judged.get("char"),
        "strategy": judged.get("strategy"),
        "version": judged.get("version"),
        "window": {"t0_ns": int(w["t0"]), "t1_ns": int(w["t1"]), "source": w["source"]},
        "minutes": judged.get("minutes"),
        "hours": (int(w["t1"]) - int(w["t0"])) / dj.NS / 3600,  # unrounded: the page divides by it
        "hours_are": "the judged window (window.source); every count here is divided by it",
        "kills": int(judged["kills"]),
        "deaths": int(judged.get("deaths") or 0),
        "items": items,
        "species": sp,
        "consumables": cons,
        "econ_row": {
            k: econ.get(k)
            for k in (
                "picked_value",
                "picked_value_oc",
                "dropped_value",
                "gross_h",
                "gross_h_oc",
                "cost",
                "cost_dc",
                "cost_h",
                "net_h",
                "net_h_best",
                "other_pickups",
            )
        },
        "econ_row_is": (
            "econ_row.measure: the PICKED drops of our kills only (no stolen items), "
            "the costs as here"
        ),
        "judge_value": judged.get("value"),
        "why": why,
    }
    out["totals"] = totals(out)
    return out


def check(run: Mapping[str, Any]) -> list[str]:
    """PURE: this export's own totals against the judges that own each figure (empty = agree):
    gross / gross OC == dungeon_judge.items_value (picked + stolen + snatched at NPC sell / OC),
    cost / cost DC == econ_row.measure's, our kills' drops and pickups == econ_row's counts."""
    bad = []
    t, jv, e = run["totals"], run.get("judge_value") or {}, run.get("econ_row") or {}
    if "value" in jv and (t["gross"], t["gross_oc"]) != (jv["value"], jv["value_oc"]):
        bad.append(f"gross {t['gross']}/{t['gross_oc']} != judge {jv['value']}/{jv['value_oc']}")
    # 2026-11-12 (Batt's own run ate 3 Candies and 2 Candy Canes): econ_row prices only what an NPC
    # sells; the candies' FORGONE SALE (FORGONE_SALE_IDS) is this export's own addition, so like is
    # compared with like -- the shop-priced part only
    fg = sum(
        int(r["used"]) * int(r["npc_buy"])
        for r in run.get("consumables") or []
        if r.get("price_basis") == "forgone_sale" and r.get("npc_buy") is not None
    )  # a sale gets no Discount: the same amount in both columns
    if e.get("cost") is not None and (float(t["cost"]) - fg, float(t["cost_dc"]) - fg) != (
        float(e["cost"]),
        float(e["cost_dc"]),
    ):
        bad.append(
            f"cost {t['cost']}/{t['cost_dc']} (of which forgone sales {fg}) != econ_row "
            f"{e['cost']}/{e['cost_dc']}"
        )
    pv = sum(r["picked_of_dropped"] * r["sell"] for r in run["items"] if r["sell"] is not None)
    if e.get("picked_value") is not None and float(pv) != float(e["picked_value"]):
        bad.append(f"picked drops value {pv} != econ_row {e['picked_value']}")
    return bad


def pool_runs(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """PURE: the runs pooled: every count summed per item / species / consumable id, the hours
    summed (each rate is the summed count / the summed hours); prices are the table's."""
    items: dict[int, dict[str, Any]] = {}
    sums = (
        "picked",
        "stolen",
        "stolen_steal",
        "stolen_snatcher",
        "income",
        "other",
        "staged",
        "dropped",
        "picked_of_dropped",
    )
    for r in runs:
        for it in r["items"]:
            q = items.setdefault(it["item_id"], {**it, **dict.fromkeys(sums, 0)})
            for f in sums:
                q[f] += it[f]
    sp: Counter[int] = Counter()
    names: dict[int, str | None] = {}
    cons: dict[int, dict[str, Any]] = {}
    for r in runs:
        for s in r["species"]:
            sp[s["mob_id"]] += s["kills"]
            names[s["mob_id"]] = s["name"]
        for c in r["consumables"]:
            q = cons.setdefault(c["item_id"], {**c, "used": 0})
            q["used"] += c["used"]
    why: dict[str, Any] = {}
    for r in runs:
        for k, v in (r.get("why") or {}).items():
            why.setdefault(k, {})[str(r.get("session"))] = v
    out: dict[str, Any] = {
        "session": f"pooled ({len(runs)} runs)",
        "runs": len(runs),
        "sessions": [r.get("session") for r in runs],
        "started": min((str(r["started"]) for r in runs if r.get("started")), default=None),
        "ended": max((str(r["ended"]) for r in runs if r.get("ended")), default=None),
        "flow": None,  # each run's own flow is in its entry
        "map": ", ".join(sorted({str(r.get("map")) for r in runs})),
        "char": ", ".join(sorted({str(r.get("char")) for r in runs})),
        "minutes": round(sum(float(r.get("minutes") or 0) for r in runs), 3),
        "hours": sum(float(r["hours"]) for r in runs),
        "hours_are": "the runs' judged windows summed; every count here is divided by it",
        "kills": sum(int(r["kills"]) for r in runs),
        "deaths": sum(int(r["deaths"]) for r in runs),
        "items": sorted(items.values(), key=lambda r: (-r["income"], -r["dropped"], r["item_id"])),
        "species": sorted(
            ({"mob_id": k, "name": names[k], "kills": v} for k, v in sp.items()),
            key=lambda r: (-r["kills"], r["mob_id"]),
        ),
        "consumables": sorted(cons.values(), key=lambda r: (-r["used"], r["item_id"])),
        "why": why,
    }
    out["totals"] = totals(out)
    return out


# --- loading (not pure) --------------------------------------------------------------------------


def _names(path: Path) -> dict[str, str]:
    """id -> display name from a KB file ({id: {name: ...}}), {} when absent."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {str(k): str(v["name"]) for k, v in doc.items() if isinstance(v, dict) and v.get("name")}


def run_clock(
    session_name: str,
    events: Sequence[Mapping[str, Any]],
    window: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """PURE (Batt 2026-11-11: "show when each run started and ended, and which flow the bot ran"):
    the judged window's start and end on the WALL clock (ICT, as the session id is written:
    YYYYMMDDTHHMMSS), from the session id's time plus the window's offsets from run_start, and the
    flow: the runner's version, strategy, search, the run's label (the session id's tail) and its
    flags (the manifest's fixes). Missing parts are None, never guessed."""
    import datetime as dt

    out: dict[str, Any] = {"started": None, "ended": None, "flow": None}
    rs = next((e for e in events if e.get("kind") == "run_start"), None)
    try:
        base = dt.datetime.strptime(session_name[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        base = None
    if base is not None and rs is not None and rs.get("t_ns") is not None:
        t_rs = int(rs["t_ns"])
        for key, t in (("started", window.get("t0")), ("ended", window.get("t1"))):
            if t is not None:
                out[key] = (base + dt.timedelta(seconds=(int(t) - t_rs) / 1e9)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
    strategy = (rs or {}).get("strategy") or manifest.get("strategy")
    search = (rs or {}).get("search") or manifest.get("search")
    tail = session_name[16:]
    if strategy and f"-{strategy}-" in tail:
        tail = tail.split(f"-{strategy}-", 1)[1]
    out["flow"] = {
        "runner": manifest.get("version"),
        "strategy": strategy,
        "search": search,
        "label": tail or None,
        "flags": sorted((manifest.get("fixes") or {}).keys()),
    }
    return out


def judge_session(
    session: str,
    table: Mapping[str, Mapping[str, Any]],
    map_name: str | None = None,
    maps_path: Path | None = None,
) -> dict[str, Any]:
    """One session (a directory or an id) through dungeon_judge.judge and its kill rows: what an
    entry is made of BEFORE names and prices -- {"judged": judge's row, "drops" / "used":
    counts_of, "where": the directory read, "clock": run_clock}."""
    import dungeon_judge as dj

    ev, pk, man = dj.load(session)
    mp = (
        map_name
        or next((e.get("map") for e in ev if e.get("kind") == "run_start"), None)
        or man.get("map")
        or dj.MAP
    )
    t0, t1 = human_window(man)
    judged = dj.judge(ev, pk, table, man, map_name=mp, drop_order=dj.drop_order_of(mp, maps_path),
                      t0=t0, t1=t1)  # fmt: skip
    if t0 is not None:
        judged["window"]["source"] = HUMAN_WINDOW
    judged["session"] = dj.session_dir(session).name
    w = judged["window"]
    krows, fates = dj.kills_loot(pk, int(w["t0"]), int(w["t1"]))
    drops, used = counts_of(judged, krows, fates, pk)
    return {
        "judged": judged,
        "drops": drops,
        "used": used,
        "where": str(dj.session_dir(session)),
        "clock": run_clock(str(judged["session"]), ev, w, man),
    }


HUMAN_WINDOW = (
    "manifest t0_live_ns..t_end_ns (a human demo: his first input to the recording's end)"
)


def human_window(man: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """PURE (Batt 2026-11-12: "record my stats on the economy page too"): a PLAYED human demo
    (human_demo.py) is judged from his first input (t0_live_ns) to the recording's end (t_end_ns),
    dungeon_judge's ``--live`` rule, never from arming (minutes of waiting before he started) nor
    through the aftercare's warp and @heal. (None, None) for every other session: unchanged."""
    t0, t1 = man.get("t0_live_ns"), man.get("t_end_ns")
    if not (isinstance(t0, int) and isinstance(t1, int)) or t1 <= t0:
        return None, None
    return t0, t1


def entry_of(
    j: Mapping[str, Any],
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    mobs: Mapping[str, str],
) -> dict[str, Any]:
    """PURE: a judged session (judge_session's shape) as its dashboard entry."""
    entry = entry_from_counts(j["judged"], j["drops"], j["used"], table, names, mobs, j["where"])
    entry.update(j["clock"])
    return entry


def export_run(
    session: str,
    table: Mapping[str, Mapping[str, Any]],
    names: Mapping[str, str],
    mobs: Mapping[str, str],
    map_name: str | None = None,
    maps_path: Path | None = None,
) -> dict[str, Any]:
    """One session (a directory or an id) through dungeon_judge.judge and its kill rows."""
    return entry_of(judge_session(session, table, map_name, maps_path), table, names, mobs)


def table_sha(path: Path) -> str:
    """The item table's identity as the export records it (sha256, 16 hex)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def sources(data: Path = DATA) -> tuple[Path, dict[str, Any], dict[str, str], dict[str, str]]:
    """(the item table's path, its document, the KB's item names, the KB's monster names) under
    ``data``; the table is required (econ_items.load raises with the command to run)."""
    import econ_items

    tpath = data / "econ" / "items.json"
    tdoc = econ_items.load(tpath)
    return tpath, tdoc, _names(data / "kb" / "items.json"), _names(data / "kb" / "mobs.json")


def build(
    sessions: Sequence[str], name: str, data: Path = DATA, map_name: str | None = None
) -> dict[str, Any]:
    tpath, tdoc, names, mobs = sources(data)
    table = tdoc["items"]
    runs = [
        export_run(s, table, names, mobs, map_name, data / "econ" / "maps.json") for s in sessions
    ]
    return document(runs, name, tpath, tdoc, names, mobs)


def document(
    runs: Sequence[Mapping[str, Any]],
    name: str,
    tpath: Path,
    tdoc: Mapping[str, Any],
    names: Mapping[str, str],
    mobs: Mapping[str, str],
) -> dict[str, Any]:
    """The export document around its run entries: the sources, the price rules, the runs and
    the pool (pool_runs)."""
    import econ_items

    meta = tdoc.get("meta") or {}
    return {
        "schema": SCHEMA,
        "name": name,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sources": {
            "items_table": {
                "path": str(tpath),
                "rathena_ref": meta.get("rathena_ref"),
                "mode": meta.get("mode"),
                "built_at": meta.get("built_at"),
                "sha256": table_sha(tpath),
            },
            "item_names": "data/kb/items.json" if names else "the item table (no KB names)",
            "mob_names": "data/kb/mobs.json" if mobs else None,
            "judges": "dungeon_judge.judge + kills_loot, econ_row.uses / kill_mix",
        },
        "rules": {
            "overcharge": {
                "level": int(meta.get("oc_level") or econ_items.OC_LV),
                "rate_pct": econ_items.skill_rate(econ_items.OC_LV),
                "min_price": econ_items.MIN_SHOP_SELL,
                "source": "pc_modifysellvalue, pc.cpp:5708-5719",
            },
            "discount": {
                "level": int(meta.get("dc_level") or econ_items.DC_LV),
                "rate_pct": econ_items.skill_rate(econ_items.DC_LV),
                "min_price": econ_items.MIN_SHOP_BUY,
                "source": "pc_modifybuyvalue, pc.cpp:5689-5703",
            },
        },
        "runs": list(runs),
        "pooled": pool_runs(runs),
    }


def write(doc: Mapping[str, Any], out_dir: Path) -> Path:
    """Atomic write, then read back."""
    name = str(doc["name"])
    if not valid_name(name):
        raise ValueError(f"bad export name {name!r}: [A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    tmp = out_dir / f".{name}.json.part"
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    tmp.replace(path)
    back = json.loads(path.read_text())
    if back.get("schema") != SCHEMA or len(back.get("runs") or []) != len(doc["runs"]):
        raise RuntimeError(f"{path}: read-back mismatch")
    return path


def listing(out_dir: Path) -> list[dict[str, Any]]:
    out = []
    for p in sorted(out_dir.glob("*.json")) if out_dir.is_dir() else []:
        if not valid_name(p.stem):
            continue
        try:
            doc = json.loads(p.read_text())
            pooled = doc.get("pooled") or {}
            out.append(
                {
                    "name": p.stem,
                    "runs": len(doc.get("runs") or []),
                    "hours": pooled.get("hours"),
                    "kills": pooled.get("kills"),
                    "exported_at": doc.get("exported_at"),
                    "bytes": p.stat().st_size,
                }
            )
        except (OSError, ValueError) as e:
            out.append({"name": p.stem, "error": f"{type(e).__name__}: {e}"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("export")
    x.add_argument("sessions", nargs="+", help="session directories or ids")
    x.add_argument("--name", required=True)
    x.add_argument("--map", default=None, help="the runs' map (default: run_start's / manifest's)")
    x.add_argument(
        "--data",
        type=Path,
        default=DATA,
        help="the data directory with econ/items.json and kb/ (default: the repo's)",
    )
    x.add_argument("--out-dir", type=Path, default=None, help="default: <data>/econ/dashboard")
    ls_ = sub.add_parser("list")
    ls_.add_argument("--out-dir", type=Path, default=DATA / "econ" / "dashboard")
    a = ap.parse_args()
    if a.cmd == "list":
        for row in listing(a.out_dir):
            print(json.dumps(row, ensure_ascii=False))
        return 0
    if not valid_name(a.name):
        ap.error(f"--name {a.name!r}: [A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}")
    doc = build(a.sessions, a.name, a.data, a.map)
    bad = {r["session"]: check(r) for r in doc["runs"] if check(r)}
    if bad:  # a disagreement with the judges is reported and nothing is written
        print(json.dumps({"cross_check_failed": bad}, indent=1), file=sys.stderr)
        return 1
    path = write(doc, a.out_dir or a.data / "econ" / "dashboard")
    summary = [
        {
            "session": r["session"],
            "hours": r["hours"],
            "kills": r["kills"],
            **{
                k: r["totals"][k]
                for k in (
                    "kills_h",
                    "picked_units",
                    "stolen_units",
                    "gross_h",
                    "gross_oc_h",
                    "cost_h",
                    "cost_dc_h",
                    "net_h",
                    "net_best_h",
                )
            },
        }
        for r in [*doc["runs"], doc["pooled"]]
    ]
    print(
        json.dumps(
            {"out": str(path), "bytes": path.stat().st_size, "rows": summary},
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
