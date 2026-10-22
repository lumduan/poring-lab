#!/usr/bin/env python3
"""dungeon@1 (Batt 2026-10-22, the day run): the CRUSADER hunts Orc Dungeon F1 (orcsdun01) for
real, immunity OFF, with one of three pre-registered SUSTAIN strategies (docs/demonstrations.md
3.98, pre-registered BEFORE the first scored run):

- A, POTIONS: White Potion (F1) below 60 % HP (3.96's S2 pacing); Fly Wing (F2) below 25 % HP, or
  the HP falling faster than 200 HP/s while under 60 %;
- B, REST: potions and Fly Wings only in an emergency (below 30 % a potion; below 20 %, or mobbed
  = falling faster than 200 HP/s under 40 %, a Fly Wing); after a fight with HP under 60 %, walk to
  the nearest REST SPOT and sit (Insert) until HP reads 100 %; hit while sitting -> stand, fight;
- C, HEAL: B, plus Heal (F5, then a click on the drawn character) below 60 % HP while SP allows
  (34 SP = 11 %), repeated every 1.1 s while under 80 %; rests (as B) only when SP is short.
Every strategy re-casts Auto Guard by 3.96's S4b2 rule (F3, a TOGGLE: only when its icon is off).

ENGAGEMENT WITHOUT A TRAINED DETECTOR ("DEFEND-SCAN", Batt): orcsdun01's monsters are aggressive
and come to us; we fight in melee. A fight starts when the Battle Log shows a hit ON US ("taken",
battle_log.py) or the HP percent falls (2+ points within 1.5 s): the pointer hovers the cells
around the drawn character (ring 1, then ring 2; two motions each, cursor_sword's read) and on a
SWORD clicks there and re-clicks every 0.6 s until the client's lock arrow (arm C), bounded. The
fight then waits for our kill (a Base EXP line) and scans again while hits keep coming. After a
kill, a LOOT hover of the struck cell's 3 x 3 clicks only where the client drew its PICKUP hand.
Between fights the HEADING WALK (hunt_flow.heading_goal) searches; each walk click is made only
where the cursor reads clear (WALK / PICKUP); a SWORD there is engaged (by "walk_sword").

PIXELS IN, KEYS AND CLICKS OUT: HP / SP from Basic Info's percent text (hp_percent), the Battle
Log from the chat window (battle_log.py live, its own process), the position from the minimap's
readout (selfpos), the cursor from its pixels (cursor_sword), the Auto Guard icon (survive), the
death dialog's signature (gm_vitals). Nothing reads packets at decision time; the packets of the
run are written afterwards for the offline judge (dungeon_judge.py).

Hard bars (stop the run): a map change (a position jump without our Fly Wing, or a black screen
that stays), an unknown UI state (farm0.client_state, every UI_EVERY_S), an NPC contact (judged
offline; orcsdun01 has no script NPC). A DEATH is a RESULT: the run stops, the cause is recorded,
the dialog closes by its known step (its second button), then @alive + @heal.

    dungeon_hunt.py run --strategy A|B|C --minutes 45 --seed S [--label L]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/dev/shm/poring-lab-demo")
MAP = "orcsdun01"
VERSION = "dungeon@1"
REST_FILE = ROOT / "config" / "dungeon" / "orcsdun01.json"  # rest spots (static map knowledge)
Cell = tuple[int, int]

STRATEGIES: dict[str, dict[str, Any]] = {
    "A": {"potion_below": 0.60, "fly_below": 0.25, "fly_rate": 200.0, "fly_rate_below": 0.60,
          "rest_below": None, "heal_below": None},
    "B": {"potion_below": 0.30, "fly_below": 0.20, "fly_rate": 200.0, "fly_rate_below": 0.40,
          "rest_below": 0.60, "heal_below": None},
    "C": {"potion_below": 0.30, "fly_below": 0.20, "fly_rate": 200.0, "fly_rate_below": 0.40,
          "rest_below": 0.60, "heal_below": 0.60, "heal_until": 0.80, "heal_sp_min": 0.11},
}  # fmt: skip
KEYS = {"potion": "F1", "fly": "F2", "autoguard": "F3", "heal": "F5", "sit": "Insert",
        "stand": "Insert"}  # fmt: skip
MAX_HP = 5260
READ_HZ = 5.0
HEAL_GAP_S = 1.1  # Heal's after-cast delay is 1 s (pinned skill_db AL_HEAL AfterCastActDelay)
SELF_PX = (640, 330)  # the drawn character's body (client px): Heal's target click
FOOT_PX = (641, 362)  # the camera's projection of our own cell
BODY_UP = 26  # a monster's body above its cell's projected point (px): the hover point
FIGHT_TAKEN_S = 2.5  # a hit on us within this long = in a fight
HP_DROP_PTS, HP_DROP_S = 2, 1.5  # the HP percent falling this much this fast = a hit unseen
LOCK_NO_HIT_S = 3.5  # locked, but none of OUR hits in the log for this long -> scan again
LOCK_MAX_S = 25.0
BURST_GAP_S, BURST_MAX, BURST_MAX_S = 0.6, 4, 3.0  # arm C: re-click until the lock arrow
CURSOR_WAIT_S = 0.35
LOOT_MAX_HOVERS, LOOT_MAX_PICKS = 9, 5
PICKUP_MIN = 0.90  # cursor_sword: a drawn PICKUP hand
WALK_AHEAD = 7  # the walk click's target: this many path cells ahead (in view)
WALK_EVERY_S = 1.2
REST_NEAR = 1  # at the rest spot = within this many cells (Chebyshev)
REST_MAX_S = 300.0
UI_EVERY_S = 10.0
JUMP_CELLS = 20  # a position jump this large without our Fly Wing = a map change (stop)
WEIGHT_MAX = 0.48  # the setup refuses to start at or over this (natural regen stops at 50 %)
POTIONS_TO, WINGS_TO = 50, 15  # the setup's top-up (by @item, against the DB's last save)
BOX_EVERY_S, BOX_FRESH_S = 1.0, 1.5  # the box watcher's rhythm and how old a box may be
BOX_NEAR_PX = 110.0  # a box's foot within this of our cell's point = "near" (~3 cells across)


# --- pure decisions ----------------------------------------------------------------------------


@dataclass
class Sustain:
    hist: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=64))
    pots: list[float] = field(default_factory=list)
    pot_frac: float | None = None
    fly: float = -1e9
    heal: float = -1e9
    healing: bool = False


def rate_hp_s(hist: Sequence[tuple[float, float]], now: float, win: float = 2.0) -> float | None:
    """PURE: HP lost per second over the last ``win`` s (survive.rate_hp_s)."""
    pts = [(t, f) for t, f in hist if now - win <= t <= now]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < win / 2:
        return None
    (t0, f0), (t1, f1) = pts[0], pts[-1]
    return (f0 - f1) * MAX_HP / (t1 - t0)


def sustain(st: Sustain, now: float, hp: float, sp: float | None, strat: Mapping[str, Any]
            ) -> list[tuple[str, str]]:  # fmt: skip
    """PURE: the sustain keys to press now with why: the escape first (alone), then a potion,
    then Heal. ``hp`` / ``sp`` are shares (0..1); ``st`` is updated for what is returned."""
    st.hist.append((now, hp))
    rate = rate_hp_s(st.hist, now)
    if now - st.fly >= 3.0:
        why = None
        if hp < strat["fly_below"]:
            why = f"hp {hp:.2f}"
        elif rate is not None and rate > strat["fly_rate"] and hp < strat["fly_rate_below"]:
            why = f"rate {rate:.0f} at hp {hp:.2f}"
        if why:
            st.fly = now
            return [("fly", why)]
    out: list[tuple[str, str]] = []
    if hp < strat["potion_below"]:
        recent = [t for t in st.pots if now - t <= 2.0]
        rose = st.pot_frac is not None and hp > st.pot_frac + 0.01
        if (not st.pots or now - st.pots[-1] >= 0.7 or rose) and len(recent) < 3:
            st.pots.append(now)
            st.pot_frac = hp
            out.append(("potion", f"hp {hp:.2f}"))
            return out  # a potion this tick: Heal waits for its effect
    hb = strat.get("heal_below")
    if hb is not None and sp is not None and sp >= strat["heal_sp_min"]:
        if hp < hb:
            st.healing = True
        if st.healing and hp >= strat["heal_until"]:
            st.healing = False
        if st.healing and now - st.heal >= HEAL_GAP_S:
            st.heal = now
            out.append(("heal", f"hp {hp:.2f} sp {sp:.2f}"))
    elif hb is not None:
        st.healing = False
    return out


def rest_wanted(strat: Mapping[str, Any], hp: float, sp: float | None) -> bool:
    """PURE: after a fight, go and sit? B: HP under rest_below. C: the same, only when SP cannot
    pay for a Heal (Heal covers it otherwise). A never rests."""
    rb = strat.get("rest_below")
    if rb is None or hp >= rb:
        return False
    return not (strat.get("heal_below") is not None and sp is not None
                and sp >= strat["heal_sp_min"])  # fmt: skip


def ring(r_: int) -> list[Cell]:
    """PURE: the cells at Chebyshev distance r_ around (0, 0), the orthogonal ones first (a melee
    attacker stands there more often than on a diagonal), then clockwise from north."""
    cells = [(dx, dy) for dx in range(-r_, r_ + 1) for dy in range(-r_, r_ + 1)
             if max(abs(dx), abs(dy)) == r_]  # fmt: skip
    return sorted(cells, key=lambda c: (abs(c[0]) + abs(c[1]),
                                        math.atan2(c[0], c[1]) % (2 * math.pi)))  # fmt: skip


def hp_dropped(hist: Sequence[tuple[float, float]], now: float) -> bool:
    """PURE: the HP percent fell >= HP_DROP_PTS within HP_DROP_S (a hit the log did not show)."""
    pts = [f for t, f in hist if now - HP_DROP_S <= t <= now]
    return len(pts) >= 2 and (max(pts) - pts[-1]) * 100 >= HP_DROP_PTS - 1e-6


def pickup_seen(rec: Mapping[str, float]) -> bool:
    """PURE: the client drew its PICKUP hand (and no SWORD) at the hovered point."""
    import cursor_sword as csw

    return rec.get("pickup", 0.0) >= PICKUP_MIN and rec.get("sword", 0.0) < csw.SWORD_MIN


def nearest_spot(spots: Sequence[Cell], here: Cell) -> Cell | None:
    return min(spots, key=lambda s: max(abs(s[0] - here[0]), abs(s[1] - here[1])), default=None)


def walk_target(path: Sequence[Cell], ahead: int, fits: Any) -> tuple[int, Cell] | None:
    """PURE: the farthest path cell at most ``ahead`` steps along that ``fits`` (in view, off
    the UI, no zone crossed), else None."""
    for i in range(min(ahead, len(path) - 1), 0, -1):
        if fits(path[i]):
            return i, path[i]
    return None


# --- live ---------------------------------------------------------------------------------------


class BoxWatch:
    """The THIRD trigger (Batt: "or a v1 box is near"): the v1 CPU detector on a fresh frame every
    BOX_EVERY_S in its own thread (its worker process does the work), the monster boxes kept with
    their grab time. orcsdun01 zero-shot (orcsdun01-dungeon-prep.md 1): within 3 cells recall
    8-14 % pooled, precision 96-100 %: a box near us is believed, "no box" means nothing."""

    def __init__(self, screen: Any, region: tuple[int, int, int, int], r: Any) -> None:
        import threading

        import unit_detector

        self.det = unit_detector.UnitDetector()
        self.screen, self.region, self.r = screen, region, r
        self.lock = threading.Lock()
        self.last: tuple[float, list[Any]] = (0.0, [])
        self.halt = threading.Event()
        self.n = 0
        self.th = threading.Thread(target=self._loop, name="box-watch", daemon=True)
        self.th.start()

    def _loop(self) -> None:
        while not self.halt.is_set():
            t = time.monotonic()
            try:
                img = np.ascontiguousarray(self.screen.grab(*self.region)[1][..., :3])
                got = [b for b in self.det.detect(img) if b.cls == "monster"]
            except Exception:  # noqa: BLE001 -- a dead worker ends the watcher, not the run
                return
            with self.lock:
                self.last = (t, got)
                self.n += 1
            self.halt.wait(max(0.0, BOX_EVERY_S - (time.monotonic() - t)))

    def near(self, px: Sequence[float], max_px: float, fresh_s: float) -> tuple[float, ...] | None:
        with self.lock:
            t, got = self.last
        if time.monotonic() - t > fresh_s:
            return None
        best = None
        for b in got:
            d = math.hypot((b.x0 + b.x1) / 2 - px[0], b.y1 - px[1])
            if d <= max_px and (best is None or d < best[0]):
                best = (d, b.x0, b.y0, b.x1, b.y1)
        return None if best is None else best[1:]

    def stop(self) -> None:
        self.halt.set()
        self.th.join(timeout=3)


def load_rest_spots(path: Path = REST_FILE) -> list[Cell]:
    doc = json.loads(path.read_text())
    return [(int(c[0]), int(c[1])) for c in doc["rest_spots"]]


def run(a: argparse.Namespace) -> int:  # noqa: PLR0915, C901
    import bench
    import crusader as cr
    import cursor_sword as csw
    import farm0 as f0
    import gm_vitals as gv
    import hp_percent as hpp
    import hunt
    import hunt_core as hc
    import hunt_flow as hf
    import loot1
    import map_zones as mz
    import record_session as rs
    import ro_agent as r
    import survive as sv
    import ui_gate
    from anim_region import stand_grid

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env import selfpos

    strat = STRATEGIES[a.strategy]
    z = np.load(hpp.GLYPHS)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    agz = np.load(sv.AG_ICON)
    ag_t, ag_m = agz["template"], agz["mask"].astype(bool)
    sword_refs = csw.SwordRefs.load()
    digits = selfpos.load_digit_templates()
    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    kb = ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    try:
        zones = mz.load(MAP, shape=ok.shape)
    except mz.ZoneError as e:
        raise SystemExit(f"dungeon@1 refused: map zones: {e}") from None
    if zones is None:
        raise SystemExit("dungeon@1 refused: no config/map_zones/orcsdun01.yaml (the warp zones)")
    area = mz.apply(ok, hc.search_area(ok, keep, margin=10), zones)[1]
    okr = mz.route_grid(ok, zones)
    cut = mz.sealed_off(ok, okr)
    area = hf.main_component(area & ~cut)
    okr = okr & ~cut
    spots = load_rest_spots()
    for s_ in spots:
        if not okr[s_[1], s_[0]]:
            raise SystemExit(f"dungeon@1 refused: rest spot {s_} is not on the route grid")
    start = hunt.start_cell(area, a.seed, near=hf.area_centre(area))
    cj = json.loads((ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    gx0, gy0, gw, gh = r.game_region()
    rng = np.random.default_rng(a.seed)

    def in_view(u: float, v: float) -> bool:
        return 30 <= u < gw - 30 and 30 <= v < gh - 30 and not loot1.in_ui(u, v)

    def project(here: Cell | None, rel: Sequence[Cell]) -> Any:
        rel_ = np.asarray(rel, dtype=float)
        alt = (gat.relative_altitude(here, rel_) if here is not None
               else np.zeros(len(rel_)))  # fmt: skip
        return camera.project(rel_, alt)

    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-demo-dungeon-{a.strategy}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True, exist_ok=False)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    counts: Counter[str] = Counter()
    reason = "time_box"
    t0 = r.ns()
    with r.session(f"rule:dungeon-{a.strategy}") as (agent_raw, screen):
        agent_raw.wait_for_human()
        agent = hf.FrameGuard(agent_raw, (gx0, gy0, gw, gh), counts)
        got = cr.check(screen, "crusader")
        if not got["ok"]:
            raise r.Stop(f"identity {got}")
        ui_gate.ensure_clear(agent_raw, screen, why="dungeon-start")
        # the setup (the experimenter's restore, never a decision): full HP / SP, the stock topped
        # up against the DB's last save (an upper bound of what is carried), the weight checked
        name = json.loads((ROOT / "data" / "crusader" / "char.json").read_text())["name"]
        cid = int(r.db_query(f"SELECT char_id FROM `char` WHERE name = {r.sql_str(name)};")[0][0])
        inv = {int(i): int(n) for i, n in r.db_query(
            f"SELECT nameid, amount FROM inventory WHERE char_id = {cid} "
            "AND nameid IN (504, 601);")}  # fmt: skip
        setup = ["@heal"]
        if inv.get(504, 0) < POTIONS_TO:
            setup.append(f"@item 504 {POTIONS_TO - inv.get(504, 0)}")
        if inv.get(601, 0) < WINGS_TO:
            setup.append(f"@item 601 {WINGS_TO - inv.get(601, 0)}")
        setup.append(f"@warp {MAP} {start[0]} {start[1]}")
        for cmd in setup:
            cr.gm_line(agent_raw, screen, cmd, "crusader")
            time.sleep(3.0 if "@warp" in cmd else 0.8)
        bench.close_chat(agent_raw, screen)
        r.activate_client(agent_raw, screen)
        time.sleep(1.0)

        def frame() -> Any:
            return np.ascontiguousarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())[..., :3])

        import gm_state

        w_ = gm_state._weight(gm_state._frames(screen))
        share = gm_state.weight_share(w_)
        ev({"kind": "run_start", "strategy": a.strategy, "seed": a.seed, "version": VERSION,
            "minutes": a.minutes, "map": MAP, "start": list(start), "inv_db": inv,
            "setup": setup, "weight": w_, "params": strat, "rest_spots": spots})  # fmt: skip
        if share is not None and share >= WEIGHT_MAX:
            raise r.Stop(f"dungeon@1: weight {share:.2f} >= {WEIGHT_MAX} (a person first)")
        blt = hf.BattleLogTail(out / "battle_log_live.jsonl", owner_pid=__import__("os").getpid())
        boxes = BoxWatch(screen, (gx0, gy0, gw, gh), r) if a.boxes else None
        st = Sustain()
        ag_last = sv.load_ag_last()
        ag_absent: float | None = None
        here: Cell | None = None
        last_pos_t = time.monotonic()
        seen_lines = 0
        last_taken = -1e9
        last_ours = -1e9
        kills_seen: list[float] = []
        mode = "search"
        lock: dict[str, Any] | None = None
        sitting = False
        rest_since = 0.0
        last_ui = time.monotonic()
        last_walk = 0.0
        walk_st: dict[str, Any] = {"ang": float(rng.uniform(0, 2 * math.pi))}
        goal_path: list[Cell] | None = None
        fly_at = -1e9
        n_reads = 0
        pending_loot: Cell | None = None
        t_end = time.monotonic() + a.minutes * 60.0

        def press(what: str, why: str) -> None:
            agent_raw.keys(KEYS[what])
            counts[what] += 1
            ev({"kind": "press", "what": what, "key": KEYS[what], "why": why})

        def click_at(u: float, v: float, why: str) -> None:
            """Every world click of this runner: FrameGuard refuses one off the game frame."""
            x, y = gx0 + round(u), gy0 + round(v)
            agent.move(x + 4, y + 3)
            time.sleep(0.02)
            agent.move(x, y)
            time.sleep(0.05)
            agent.click(x, y)
            counts[f"click_{why}"] += 1

        def heal_self(why: str) -> None:
            press("heal", why)
            time.sleep(0.25)
            click_at(SELF_PX[0], SELF_PX[1], "heal_self")

        def hover(u: float, v: float) -> dict[str, Any]:
            return csw.check(agent, screen, sword_refs, gx0, gy0, u, v, wait_s=CURSOR_WAIT_S)

        def above(img: Any, u: float, v: float) -> Any:
            a_ = np.asarray(img)
            return a_[max(0, int(v) - 80): max(0, int(v) - 15),
                      max(0, int(u) - 45): max(0, int(u) + 45), :3]  # fmt: skip

        def strike(u: float, v: float, rel: Cell, by: str) -> bool:
            """arm C: click the SWORD point, re-click every BURST_GAP_S until the lock arrow."""
            ref = frame()
            click_at(u, v, "strike")
            t_c = time.monotonic()
            n, arrow = 1, None
            while time.monotonic() - t_c < BURST_MAX_S:
                time.sleep(0.08)
                if hf.arrow_new(above(ref, u, v), above(frame(), u, v)):
                    arrow = round(time.monotonic() - t_c, 2)
                    break
                if n < BURST_MAX and time.monotonic() - t_c >= n * BURST_GAP_S:
                    click_at(u, v, "strike_burst")
                    n += 1
            ev({"kind": "strike", "u": round(u, 1), "v": round(v, 1), "rel": list(rel),
                "clicks": n, "arrow_s": arrow, "end": "arrow" if arrow is not None else "bound",
                "by": by})  # fmt: skip
            return True

        def scan(purpose: str, cells: Sequence[Cell], stop_on: str
                 ) -> tuple[Cell, Any, dict[str, Any]] | None:  # fmt: skip
            """Hover each cell's point (defend: the body above it; loot: the cell); the first
            ``stop_on`` ("sword" / "pickup") ends the scan. Aborts when a fight starts (loot)."""
            t_s = time.monotonic()
            verdicts: Counter[str] = Counter()
            uv = project(here, cells)
            found = None
            for c, (u, v) in zip(cells, uv, strict=True):
                v_ = v - (BODY_UP if purpose == "defend" else 0)
                if not in_view(u, v_):
                    verdicts["off"] += 1
                    continue
                res = hover(u, v_)
                vd = "pickup" if pickup_seen(res["rec"]) else res["verdict"]
                verdicts[vd] += 1
                if vd == stop_on or (stop_on == "pickup" and vd == "sword"):
                    found = (c, (u, v_), res)
                    break
                if purpose == "loot" and time.monotonic() - last_taken < 1.0:
                    break
            ev({"kind": "scan", "purpose": purpose, "cells": sum(verdicts.values()),
                "verdicts": dict(verdicts), "found": None if found is None else
                [round(found[1][0], 1), round(found[1][1], 1)],
                "found_rel": None if found is None else list(found[0]),
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return found

        try:
            while time.monotonic() < t_end:
                tick = time.monotonic()
                img = frame()
                pct = hpp.read(img, glyphs)
                spp = hpp.read(img, glyphs, hpp.SP_DY)
                n_reads += 1
                dark = sv.dark_screen(img)
                ag_on = (sv.ag_present(img, ag_t, ag_m)
                         if n_reads % sv.AG_EVERY == 1 and not dark else None)  # fmt: skip
                dead = r.is_state(screen, gv.DEAD_STATE)
                pos = selfpos.read_minimap_xy(img, digits)
                if pos is not None:
                    p_ = (int(pos[0]), int(pos[1]))
                    if (here is not None and max(abs(p_[0] - here[0]), abs(p_[1] - here[1]))
                            > JUMP_CELLS and tick - fly_at > 6.0):  # fmt: skip
                        ev({"kind": "jump", "from": list(here), "to": list(p_)})
                        reason = "hard_bar: position jump (map change?)"
                        break
                    here, last_pos_t = p_, tick
                ev({"kind": "hp_read", "pct": pct, "sp_pct": spp, "dead": dead, "ag_on": ag_on,
                    "dark": dark, "pos": None if here is None else list(here)})  # fmt: skip
                if dead:
                    reason = "death"
                    ev(
                        {
                            "kind": "death",
                            "last_reads": [
                                [round(t, 2), round(f, 3)] for t, f in list(st.hist)[-40:]
                            ],
                        }
                    )
                    break
                # the Battle Log's new lines (its own process; pixels only)
                with blt.lock:
                    new = blt.lines[seen_lines:]
                    seen_lines = len(blt.lines)
                for ln in new:
                    typ = ln.get("type")
                    if typ == "taken":
                        last_taken = tick
                        if mode in ("search", "rest") or (mode == "fight" and lock is None):
                            ev({"kind": "engage", "by": "battle_log", "name": ln.get("name"),
                                "n": ln.get("n")})  # fmt: skip
                    elif typ == "damage":
                        last_ours = tick
                    elif typ == "base_exp":
                        kills_seen.append(tick)
                        ev({"kind": "kill", "by": "exp_line",
                            "name": None if lock is None else lock.get("name")})  # fmt: skip
                        if lock is not None:
                            pending_loot = lock["rel"]
                        lock = None
                if not blt.alive():
                    reason = "battle_log_reader_died"
                    break
                frac = None if pct is None else pct / 100.0
                spf = None if spp is None else spp / 100.0
                # sustain first (every strategy), then Auto Guard (S4b2)
                if frac is not None:
                    for what, why in sustain(st, tick, frac, spf, strat):
                        if what == "fly":
                            if sitting:
                                press("stand", "escape")
                                sitting = False
                            press("fly", why)
                            fly_at = time.monotonic()
                            ev({"kind": "escape", "how": "fly", "why": why})
                            lock, goal_path, pending_loot = None, None, None
                            mode = "search"
                            time.sleep(1.0)
                        elif what == "heal":
                            if sitting:
                                press("stand", "heal")
                                sitting = False
                            heal_self(why)
                        else:
                            press(what, why)
                if ag_on is not None:
                    if ag_on:
                        ag_absent = None
                        if ag_last < 0:
                            ag_last = time.monotonic()
                    else:
                        ag_absent = ag_absent if ag_absent is not None else tick
                        if tick - ag_absent >= sv.AG_ABSENT_S and tick - ag_last >= sv.AG_RECAST_S:
                            press("autoguard", "first cast" if ag_last < 0 else "recast")
                            ag_last = time.monotonic()
                            sv.save_ag_last(ag_last)
                            ag_absent = None
                # a fight?
                hit_now = tick - last_taken < FIGHT_TAKEN_S
                dropped = hp_dropped(st.hist, tick) and tick - fly_at > 2.0
                if dropped and not hit_now and mode in ("search", "rest"):
                    ev({"kind": "engage", "by": "hp_drop", "name": None})
                boxed = False
                if boxes is not None and mode in ("search", "rest") and not hit_now \
                        and not dropped:  # fmt: skip
                    near_ = boxes.near(FOOT_PX, BOX_NEAR_PX, BOX_FRESH_S)
                    if near_ is not None:
                        boxed = True
                        ev({"kind": "engage", "by": "box", "name": None,
                            "box": [round(x_, 1) for x_ in near_]})  # fmt: skip
                if hit_now or dropped or boxed:
                    if sitting:
                        press("stand", "hit while sitting")
                        sitting = False
                        ev({"kind": "rest_end", "why": "hit", "pct": pct, "sp_pct": spp})
                    if mode != "fight":
                        mode, goal_path = "fight", None
                # UI watch (the hard bar: an unknown UI state)
                if tick - last_ui >= UI_EVERY_S and mode != "fight":
                    last_ui = tick
                    cs = f0.client_state(agent_raw, screen)
                    if cs["decision"]["do"] != "clear":
                        r.to_png(cs["frame"], out / "stop-ui.png")
                        reason = f"hard_bar: unknown UI state {cs['decision']}"
                        break
                # --- FIGHT: locked, or scan for the attacker
                if mode == "fight":
                    if lock is not None:
                        since = tick - lock["t"]
                        idle = tick - max(last_ours, lock["t"])
                        if since > LOCK_MAX_S or (since > LOCK_NO_HIT_S and idle > LOCK_NO_HIT_S):
                            ev({"kind": "unlock", "why": "no hits" if since <= LOCK_MAX_S
                                else "max", "s": round(since, 1)})  # fmt: skip
                            lock = None
                    if lock is None:
                        found = scan("defend", ring(1), "sword") or scan("defend", ring(2), "sword")
                        if found is not None:
                            c, (u, v), _res = found
                            strike(u, v, c, "scan")
                            lock = {
                                "t": time.monotonic(),
                                "rel": c,
                                "cell": None if here is None else [here[0] + c[0], here[1] + c[1]],
                            }
                        elif tick - last_taken > FIGHT_TAKEN_S and not hp_dropped(st.hist, tick):
                            mode = "after"
                            ev({"kind": "fight_end", "kills": len(kills_seen)})
                    time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
                    continue
                if mode == "fight" or (lock is not None):
                    continue
                # --- AFTER a fight: loot, then rest or search
                if pending_loot is not None:
                    pl, pending_loot = pending_loot, None
                    cells = sorted(
                        {(pl[0] + dx, pl[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)},
                        key=lambda c: (abs(c[0] - pl[0]) + abs(c[1] - pl[1]), c),
                    )
                    picks, hovers = 0, 0
                    while picks < LOOT_MAX_PICKS and hovers < LOOT_MAX_HOVERS and cells:
                        if time.monotonic() - last_taken < 1.0:
                            break
                        found = scan("loot", cells, "pickup")
                        hovers += 1
                        if found is None:
                            break
                        c, (u, v), res = found
                        if res["verdict"] == "sword":
                            ev({"kind": "engage", "by": "loot_sword", "name": None})
                            strike(u, v, c, "loot_sword")
                            lock = {"t": time.monotonic(), "rel": c, "cell": None}
                            mode = "fight"
                            break
                        click_at(u, v, "loot")
                        ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                            "rel": list(c)})  # fmt: skip
                        picks += 1
                        time.sleep(0.9)  # the walk there and the pickup
                        # we now stand on c: the remaining cells relative to it
                        cells = [(x_ - c[0], y_ - c[1]) for x_, y_ in cells if (x_, y_) != c]
                    if mode == "fight":
                        continue
                if mode in ("after", "search") and frac is not None and not sitting \
                        and rest_wanted(strat, frac, spf):  # fmt: skip
                    mode, goal_path = "rest", None
                    rest_since = tick
                    ev({"kind": "rest_go", "pct": pct, "sp_pct": spp})
                if mode == "after":
                    mode = "search"
                # --- REST (B / C): to the nearest spot, sit until HP 100 %
                if mode == "rest":
                    if sitting:
                        full = pct is not None and pct >= 100
                        if full or tick - rest_since > REST_MAX_S:
                            press("stand", "full" if full else "rest max")
                            sitting = False
                            ev({"kind": "rest_end", "why": "full" if full else "max",
                                "pct": pct, "sp_pct": spp})  # fmt: skip
                            mode = "search"
                        time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
                        continue
                    if here is not None:
                        spot = nearest_spot(spots, here)
                        if (
                            spot is not None
                            and max(abs(spot[0] - here[0]), abs(spot[1] - here[1])) <= REST_NEAR
                        ):
                            press("sit", "at rest spot")
                            sitting = True
                            rest_since = tick
                            ev({"kind": "rest_start", "cell": list(here), "pct": pct,
                                "sp_pct": spp})  # fmt: skip
                            continue
                        if goal_path is None or goal_path[-1] != spot:
                            goal_path = hc.astar(okr, here, spot) if spot else None
                            ev(
                                {
                                    "kind": "rest_route",
                                    "to": list(spot) if spot else None,
                                    "len": None if goal_path is None else len(goal_path),
                                }
                            )
                            if goal_path is None:
                                mode = "search"
                # --- SEARCH: the heading walk
                if mode == "search" and here is not None and (
                        goal_path is None or len(goal_path) < 2
                        or max(abs(goal_path[-1][0] - here[0]),
                               abs(goal_path[-1][1] - here[1])) <= 2):  # fmt: skip
                    goal = hf.heading_goal(area, here, walk_st, rng)
                    goal_path = None if goal is None else hc.astar(okr, here, goal)
                    ev({"kind": "goal", "to": None if goal is None else list(goal),
                        "len": None if goal_path is None else len(goal_path),
                        "turn": walk_st.get("turn")})  # fmt: skip
                if mode in ("search", "rest") and here is not None and goal_path \
                        and tick - last_walk >= WALK_EVERY_S:  # fmt: skip
                    last_walk = tick
                    # the path from where we are now
                    if here in goal_path:
                        goal_path = goal_path[goal_path.index(here) :]
                    else:
                        goal_path = hc.astar(okr, here, goal_path[-1])
                    if goal_path and len(goal_path) >= 2:

                        def fits(c: Cell, h: Cell = here) -> bool:
                            u_, v_ = project(h, [(c[0] - h[0], c[1] - h[1])])[0]
                            return in_view(u_, v_) and mz.segment_violates(h, c, zones) is None

                        wt_ = walk_target(goal_path, WALK_AHEAD, fits)
                        if wt_ is not None:
                            _i, c = wt_
                            rel = (c[0] - here[0], c[1] - here[1])
                            u, v = project(here, [rel])[0]
                            res = hover(u, v)
                            if res["verdict"] == "clear":
                                click_at(u, v, "walk")
                                ev({"kind": "walk", "from": list(here), "to": list(c),
                                    "clicked": True, "why": mode})  # fmt: skip
                            elif res["verdict"] == "sword":
                                ev({"kind": "engage", "by": "walk_sword", "name": None})
                                strike(u, v - BODY_UP / 2, rel, "walk_sword")
                                lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                                mode = "fight"
                            else:
                                ev({"kind": "walk", "from": list(here), "to": list(c),
                                    "clicked": False, "why": "cursor unknown"})  # fmt: skip
                if here is None and tick - last_pos_t > 30.0:
                    reason = "position unread for 30 s"
                    break
                time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
        except r.Stop as exc:
            reason = f"stop: {exc}"
            raise
        finally:
            ev({"kind": "run_end", "reason": reason, "counts": dict(counts)})
            blt.stop()
            if boxes is not None:
                boxes.stop()
            if sitting:
                agent_raw.keys(KEYS["stand"])
            if reason == "death":
                x, y = gx0 + gv.RETURN_TO_GAME[0], gy0 + gv.RETURN_TO_GAME[1]
                agent_raw.move(x + 4, y + 3)
                time.sleep(0.08)
                agent_raw.move(x, y)
                time.sleep(0.3)
                agent_raw.click(x, y)  # the death dialog's known step (its second button)
                time.sleep(1.5)
                if r.is_state(screen, gv.DEAD_STATE):
                    raise r.Stop("dungeon@1: the death dialog stayed after its known step")
                for cmd in ("@alive", "@heal"):
                    cr.gm_line(agent_raw, screen, cmd, "crusader")
                    time.sleep(0.8)
                bench.close_chat(agent_raw, screen)
            print(r.to_png(screen.full(), out / "end.png"), flush=True)
    t1 = r.ns()
    evf.close()
    n_pk = -1
    try:
        events, _anchor = rs.write_packets(out, t0, t1)
        n_pk = len(events)
    except Exception as exc:  # noqa: BLE001 -- the run is still recorded; the judge says so
        print(f"packets not written: {exc!r}")
    man = {"sid": sid, "version": VERSION, "strategy": a.strategy, "seed": a.seed,
           "minutes": a.minutes, "reason": reason, "counts": dict(counts), "t0_ns": t0,
           "t1_ns": t1, "packets": n_pk, "params": strat}  # fmt: skip
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({"sid": sid, "reason": reason, "counts": dict(counts), "packets": n_pk}),
          flush=True)  # fmt: skip
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("run")
    t.add_argument("--strategy", required=True, choices=sorted(STRATEGIES))
    t.add_argument("--minutes", type=float, default=45.0)
    t.add_argument("--seed", type=int, required=True)
    t.add_argument("--label", default="r")
    t.add_argument(
        "--boxes",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="the v1 box watcher (the third trigger, 1 Hz in its own thread)",
    )
    a = ap.parse_args()
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
