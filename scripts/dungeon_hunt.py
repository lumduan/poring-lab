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
import contextlib
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
VERSION = "dungeon@2"  # @1 = the 11:41 pilot; @2 = + Batt's loot list + sweep
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
LOOT_MAX_HOVERS, LOOT_MAX_PICKS, LOOT_MAX_S = 30, 10, 25.0  # one loot step's bounds
SWEEP_X, SWEEP_Y = 8, 6  # the sweep's cells: those in view around us (camera_rdp: 34 / 24 px)
SWEEP_DIFF = 15.0  # a cell's 24 x 20 grey patch changed by this mean |diff| since the fight began
SWEEP_MAX = 10  # at most this many changed cells hovered per sweep
PICKUP_MIN = 0.90  # cursor_sword: a drawn PICKUP hand
WALK_AHEAD = 7  # the walk click's target: this many path cells ahead (in view)
WALK_EVERY_S = 1.2
REST_NEAR = 1  # at the rest spot = within this many cells (Chebyshev)
REST_MAX_S = 300.0
REST_WALK_MAX_S = 120.0  # 3.98 Amendment B: the spot not reached in this long -> sit where we are
UI_EVERY_S = 10.0
JUMP_CELLS = 20  # a position jump this large without our Fly Wing = a map change (stop)
WEIGHT_MAX = 0.48  # the setup refuses to start at or over this (natural regen stops at 50 %)
POTIONS_TO, WINGS_TO = 40, 15  # the setup's top-up (by @item, against the DB's last save)
CLEAR_AT = 0.40  # the setup drops the Etc tab (loot only) at or over this weight share ...
CLEAR_STAND = ("prt_fild08", 268, 107)  # ... on the Crusader's open-field stand (no monster)
ARROW_UP = 150  # the lock arrow's search band: 150..10 px above the strike point
QUICK_S = 0.25  # guard_tick: an HP read at most this often inside a long action
MAX_SHOTS = 40  # strike frames kept per run (JPEG, the session dir)
NOENTRY_RED = 25  # red pixels in the 64 x 64 cursor crop: the client's no-entry ring
CARVE_R = 2  # Amendment C: a stalled walk target's 5 x 5 leaves the route grid for the run
IDLE_MAX_S = 45.0  # Amendment D: searching this long with no walk click and no move = stuck
STUCK_STALLS = 4  # Amendment C: this many stalls within 60 s at one cell = stuck -> a Fly Wing
STALL_CLICKS = 2  # walk clicks from the same cell without moving: turn, re-plan, scan ring 1
BOX_EVERY_S, BOX_FRESH_S = 1.0, 1.5  # the box watcher's rhythm and how old a box may be
SELF_BOX = (610, 268, 672, 375)  # client px: our own drawn Crusader (a box centred here is us)
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


def route(base: Any, carved: Any, here: Cell, goal: Cell) -> list[Cell] | None:
    """A* on ``base`` minus the ``carved`` cells, with OUR cell held and the base grid restored
    within CARVE_R of it (standing there proves the carved block reachable; hunt_flow's
    approach_path holds our cell for the same reason). Amendment D: without it, run 2 stood 20 min
    at 45,60 -- every route from inside a stall's carve came back None."""
    import hunt_core as hc

    b = np.asarray(base, dtype=bool)
    g = b & ~np.asarray(carved, dtype=bool)
    h, w = g.shape
    y0, y1 = max(0, here[1] - CARVE_R), min(h, here[1] + CARVE_R + 1)
    x0, x1 = max(0, here[0] - CARVE_R), min(w, here[0] + CARVE_R + 1)
    g[y0:y1, x0:x1] = b[y0:y1, x0:x1]
    g[here[1], here[0]] = True
    return hc.astar(g, here, goal)  # type: ignore[no-any-return]


def carve(mask: Any, c: Sequence[int], r_: int) -> None:
    """The (2 r_ + 1)^2 square around ``c`` set in ``mask`` (clipped to the map)."""
    h, w = mask.shape
    mask[max(0, c[1] - r_) : min(h, c[1] + r_ + 1), max(0, c[0] - r_) : min(w, c[0] + r_ + 1)] = (
        True
    )


def turn_heading(st: dict[str, Any]) -> None:
    """The search heading turned by 90 degrees (a wall the client shows, or a stall)."""
    st["ang"] = float(st.get("ang", 0.0)) + math.pi / 2


def self_box(cx: float, cy: float) -> bool:
    """PURE: a box centred on OUR drawn Crusader (the camera centres it: foot (641, 362), head ~280)
    -- v1 never saw a Crusader in training and boxes it as a monster (3.98 run 1, 12:11)."""
    x0, y0, x1, y1 = SELF_BOX
    return x0 <= cx <= x1 and y0 <= cy <= y1


def red_px(crop: Any) -> int:
    """PURE: the no-entry ring's red pixels in a cursor crop (BGR): R high, G and B low."""
    a = np.asarray(crop)[..., :3].astype(np.int16)
    b, g, r_ = a[..., 0], a[..., 1], a[..., 2]
    return int(((r_ >= 170) & (g <= 90) & (b <= 90)).sum())


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


def cheb2(a: Sequence[int], b: Sequence[int] | None) -> int:
    return 0 if b is None else max(abs(a[0] - b[0]), abs(a[1] - b[1]))


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
        # its OWN grab helper: ro_agent.Screen is one pipe, not thread-safe (pilot 3, 12:02: the
        # main loop's grab and this thread's interleaved and the pipe's framing broke)
        self.screen, self.region, self.r = r.Screen(), region, r
        del screen
        self.lock = threading.Lock()
        self.last: tuple[float, list[Any]] = (0.0, [])
        self.halt = threading.Event()
        self.n = 0
        self.n_self = 0
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
            if self_box((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2):
                self.n_self += 1  # 3.98 run 1 (12:11): v1 boxes our OWN Crusader as a monster
                continue
            d = math.hypot((b.x0 + b.x1) / 2 - px[0], b.y1 - px[1])
            if d <= max_px and (best is None or d < best[0]):
                best = (d, b.x0, b.y0, b.x1, b.y1)
        return None if best is None else best[1:]

    def stop(self) -> None:
        self.halt.set()
        self.th.join(timeout=3)
        with contextlib.suppress(Exception):
            self.screen.proc.terminate()


def first_item(kinds: Sequence[str]) -> int | None:
    """PURE: the first slot of the ETC tab that is not empty -- every Etc item is loot for the
    Crusader (potions and Fly Wings live in Use, the gear in Eqp)."""
    return next((i for i, k in enumerate(kinds) if k != "empty"), None)


def clear_etc(agent: Any, screen: Any, *, why: str, max_drops: int = 40) -> dict[str, Any]:
    """Drop every stack of the inventory's ETC tab by gm_state.clear_loot's own known path (the
    tab label, two motions; a drag onto open ground; Enter on the quantity prompt matched to its
    OK button first; the tab must change after each drop), r.Stop on anything unexpected."""
    import gm_state as gs
    import ro_agent as r
    import ui_gate

    refs = gs.load_loot_refs()
    ok_ref = np.load(gs.LOOT_DIR / "prompt_ok.npy")
    region = r.game_region()
    out: dict[str, Any] = {"dropped": 0}

    def frame() -> Any:
        return np.ascontiguousarray(r.grab_after(screen, region, r.ns())[..., :3])

    def prompt_shown(f: Any) -> bool:
        x, y, w, h = gs.PROMPT_OK_BOX
        return float(np.abs(gs.to_gray(f)[y : y + h, x : x + w] - ok_ref).mean()) <= gs.PROMPT_MATCH

    def inv_open() -> bool:
        return "inventory" in ui_gate.windows_at_home(
            frame(), ui_gate._registry(ui_gate._require_ready())
        )

    # the chord is a TOGGLE (11:5x: a run of this opened on an open inventory, CLOSED it, and its
    # tab click and drag went to the field): start clear, open, and READ it open before a click
    ui_gate.ensure_clear(agent, screen, why=f"{why}:etc-start")
    r.activate_client(agent, screen)
    agent.chord(*ui_gate.window_keys("inventory"))
    time.sleep(1.0)
    try:
        if not inv_open():
            raise r.Stop(f"clear_etc ({why}): the inventory did not read open after its chord")
        gs._tab(agent, screen, "etc")
        fails = 0
        n = gs.INV_COLS * gs.INV_ROWS
        while out["dropped"] < max_drops:
            if not inv_open():
                raise r.Stop(f"clear_etc ({why}): the inventory closed during the drops")
            f = frame()
            crops = [gs.icon_crop(f, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            i = first_item([gs.classify_icon(c, refs)[0] for c in crops])
            if i is None:
                break
            cx, cy = gs.slot_centre(i % gs.INV_COLS, i // gs.INV_COLS)
            x1, y1 = r.at(cx, cy)
            x2, y2 = r.at(*gs.DROP_AT)
            agent.move(x1 + 3, y1 + 3)
            time.sleep(0.15)
            agent.move(x1, y1)
            time.sleep(0.6)
            agent.drag(x1, y1, x2, y2, steps=12)
            time.sleep(1.0)
            f2 = frame()
            if prompt_shown(f2):
                r.activate_client(agent, screen)
                agent.chord("Enter")
                time.sleep(1.0)
                f2 = frame()
                if prompt_shown(f2):
                    raise r.Stop(f"clear_etc ({why}): the quantity prompt stayed open")
            after = [gs.icon_crop(f2, c % gs.INV_COLS, c // gs.INV_COLS) for c in range(n)]
            if not gs.tab_changed(crops, after, i):
                fails += 1
                if fails >= 2:
                    raise r.Stop(f"clear_etc ({why}): slot {i} did not drop twice")
                continue
            out["dropped"] += 1
    finally:
        r.activate_client(agent, screen)
        agent.chord(*ui_gate.window_keys("inventory"))
        time.sleep(1.0)
        ui_gate.ensure_clear(agent, screen, why=f"{why}:etc")
    return out


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
        import gm_state

        w0 = gm_state._weight(gm_state._frames(screen))
        cleared: dict[str, Any] | None = None
        if (gm_state.weight_share(w0) or 0.0) >= CLEAR_AT:
            cr.gm_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                       f"{CLEAR_STAND[2]}", "crusader")  # fmt: skip
            time.sleep(3.0)
            bench.close_chat(agent_raw, screen)
            cleared = clear_etc(agent_raw, screen, why="dungeon-setup")
        setup.append(f"@warp {MAP} {start[0]} {start[1]}")
        for cmd in setup:
            cr.gm_line(agent_raw, screen, cmd, "crusader")
            time.sleep(3.0 if "@warp" in cmd else 0.8)
        bench.close_chat(agent_raw, screen)
        r.activate_client(agent_raw, screen)
        time.sleep(1.0)

        def frame() -> Any:
            return np.ascontiguousarray(r.grab_after(screen, (gx0, gy0, gw, gh), r.ns())[..., :3])

        w_ = gm_state._weight(gm_state._frames(screen))
        share = gm_state.weight_share(w_)
        ev({"kind": "run_start", "strategy": a.strategy, "seed": a.seed, "version": VERSION,
            "minutes": a.minutes, "map": MAP, "start": list(start), "inv_db": inv,
            "setup": setup, "weight": w_, "weight_before": w0, "cleared": cleared,
            "params": strat, "rest_spots": spots})  # fmt: skip
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
        walk_from: Cell | None = None
        stall = 0
        carved = np.zeros_like(okr, dtype=bool)  # Amendment C: cells the client would not walk to
        idle_pos: Cell | None = None
        idle_since = time.monotonic()
        last_walk_click = time.monotonic()
        stalls_here: list[float] = []
        noentry_n = 0
        goal_path: list[Cell] | None = None
        fly_at = -1e9
        n_reads = 0
        loot_list: list[tuple[Cell, float]] = []  # Batt 11:5x: the GM's cell at EVERY kill
        fight_ref: dict[str, Any] | None = None  # the frame + our cell when the fight began
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
            res = csw.check(agent, screen, sword_refs, gx0, gy0, u, v, wait_s=CURSOR_WAIT_S)
            # pilot 3 (12:0x): the client's NO-ENTRY cursor (its arrow inside a red ring) read
            # "clear" over a cliff, and 4 walk clicks sent no request: the ring's red decides
            red = red_px(csw.crop_at(screen, gx0, gy0, u, v))
            res["red"] = red
            if red >= NOENTRY_RED and res["verdict"] == "clear":
                res["verdict"] = "noentry"
            return res

        def above(img: Any, u: float, v: float) -> Any:
            """Where the client draws its lock arrow over the target: an orc's head is higher than
            a Poring's (the pilot's 11:41 strikes never saw it in hunt_flow's 80..15 px band)."""
            a_ = np.asarray(img)
            return a_[max(0, int(v) - ARROW_UP): max(0, int(v) - 10),
                      max(0, int(u) - 50): max(0, int(u) + 50), :3]  # fmt: skip

        escaped = [False]
        last_quick = [0.0]

        def guard_tick() -> bool:
            """Sustain INSIDE a long action (a scan's hovers, a strike's burst): a fresh HP / SP
            read and the strategy's keys at most every QUICK_S; True once we flew away (the caller
            stops). The same Sustain state as the main loop's reads."""
            now_ = time.monotonic()
            if now_ - last_quick[0] < QUICK_S:
                return escaped[0]
            last_quick[0] = now_
            img_ = frame()
            p_, s_ = hpp.read(img_, glyphs), hpp.read(img_, glyphs, hpp.SP_DY)
            ev({"kind": "hp_read", "pct": p_, "sp_pct": s_, "quick": True})
            if p_ is None:
                return escaped[0]
            for what_, why_ in sustain(st, now_, p_ / 100.0, None if s_ is None else s_ / 100.0,
                                       strat):  # fmt: skip
                if what_ == "fly":
                    press("fly", why_)
                    ev({"kind": "escape", "how": "fly", "why": why_, "inside": True})
                    escaped[0] = True
                elif what_ == "heal":
                    heal_self(why_)
                else:
                    press(what_, why_)
            return escaped[0]

        n_shots = [0]

        def strike(u: float, v: float, rel: Cell, by: str) -> bool:
            """arm C: click the SWORD point, re-click every BURST_GAP_S until the lock arrow;
            the HP is read between the clicks (guard_tick)."""
            ref = frame()
            t_click = r.ns()
            click_at(u, v, "strike")
            t_c = time.monotonic()
            n, arrow = 1, None
            cur = ref
            while time.monotonic() - t_c < BURST_MAX_S:
                time.sleep(0.06)
                cur = frame()
                if hf.arrow_new(above(ref, u, v), above(cur, u, v)):
                    arrow = round(time.monotonic() - t_c, 2)
                    break
                if guard_tick():
                    break
                if n < BURST_MAX and time.monotonic() - t_c >= n * BURST_GAP_S:
                    click_at(u, v, "strike_burst")
                    n += 1
            if n_shots[0] < MAX_SHOTS:  # evidence frames for the judge's eye (the session dir)
                n_shots[0] += 1
                from PIL import Image

                Image.fromarray(np.asarray(cur)[..., ::-1]).save(
                    out / f"strike-{n_shots[0]:03d}.jpg", quality=80)  # fmt: skip
            # stamped at the FIRST click (the judge's landing window starts there), the end
            # time beside it (pilot 11:42: the end stamp put the attack before the window)
            ev({"t_ns": t_click, "t_end_ns": r.ns(), "kind": "strike", "u": round(u, 1),
                "v": round(v, 1), "rel": list(rel),
                "clicks": n, "arrow_s": arrow, "end": "arrow" if arrow is not None else
                ("escape" if escaped[0] else "bound"), "by": by,
                "shot": n_shots[0] if n_shots[0] <= MAX_SHOTS else None})  # fmt: skip
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
                if guard_tick():
                    break
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

        def read_here() -> Cell | None:
            xy = selfpos.read_minimap_xy(frame(), digits)
            return None if xy is None else (int(xy[0]), int(xy[1]))

        def patch(img_: Any, u: float, v: float) -> Any:
            a_ = np.asarray(img_)[..., :3].astype(np.float32).mean(axis=2)
            y0_, x0_ = int(v) - 14, int(u) - 12
            if y0_ < 0 or x0_ < 0 or y0_ + 20 > a_.shape[0] or x0_ + 24 > a_.shape[1]:
                return None
            return a_[y0_ : y0_ + 20, x0_ : x0_ + 24]

        def loot_step(lst: list[tuple[Cell, float]], ref: dict[str, Any] | None) -> str:
            """Batt 2026-10-22 11:5x (his 11:44 clip: an item left in a mob fight). After the
            fight: (1) the LOOT LIST -- the union of the 5 x 5 around our cell at EVERY kill of
            the fight (items do not move; <= 55 s old), walkable and outside the zones, nearest
            first; (2) the SWEEP -- every cell in view whose image changed since the fight began
            (the fight's first frame, re-projected from our cell then). Each cell is hovered at
            its ground point; a PICKUP hand is clicked, a SWORD engaged ("fight"), anything else
            passed. Bounded by LOOT_MAX_HOVERS / LOOT_MAX_PICKS / LOOT_MAX_S."""
            nonlocal here, lock, mode
            t_s = time.monotonic()
            hovered: set[Cell] = set()
            picks = 0
            out_: dict[str, Any] = {"kind": "loot_step", "list_kills": len(lst)}
            if here is None:
                ev({**out_, "end": "no_position"})
                return "none"
            plan = {(g[0] + dx, g[1] + dy) for g, t_ in lst if t_s - t_ <= 55.0
                    for dx in range(-2, 3) for dy in range(-2, 3)}  # fmt: skip
            plan = {c for c in plan if 0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0]
                    and ok[c[1], c[0]] and not mz.in_no_enter(zones, c)}  # fmt: skip
            out_["planned"] = len(plan)

            def visit(c: Cell, why: str) -> str:
                nonlocal here, lock, mode, picks
                assert here is not None
                rel = (c[0] - here[0], c[1] - here[1])
                u, v = project(here, [rel])[0]
                hovered.add(c)
                if not in_view(u, v):
                    return "off"
                res = hover(u, v)
                if guard_tick():
                    return "escape"
                if res["verdict"] == "sword":
                    ev({"kind": "engage", "by": "loot_sword", "name": None})
                    strike(u, v - BODY_UP, rel, "loot_sword")
                    lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                    mode = "fight"
                    return "fight"
                if pickup_seen(res["rec"]):
                    d_ = max(abs(rel[0]), abs(rel[1]))
                    click_at(u, v, "loot")
                    ev({"kind": "loot_click", "u": round(u, 1), "v": round(v, 1),
                        "rel": list(rel), "cell": list(c), "why": why})  # fmt: skip
                    picks += 1
                    time.sleep(0.45 + 0.2 * d_)  # the walk there and the pickup
                    here = read_here() or c
                return "ok"

            end = "done"
            while picks < LOOT_MAX_PICKS and len(hovered) < LOOT_MAX_HOVERS:
                todo = sorted(plan - hovered, key=lambda c: (cheb2(c, here), c))
                if not todo or time.monotonic() - t_s > LOOT_MAX_S:
                    break
                if time.monotonic() - last_taken < 1.0:
                    end = "hit"
                    break
                got = visit(todo[0], "list")
                if got in ("fight", "escape"):
                    end = got
                    break
            out_["list_hovered"] = len(hovered)
            sweep_n, changed = 0, []
            if end == "done" and ref is not None and here is not None:
                img_now = frame()
                for dx in range(-SWEEP_X, SWEEP_X + 1):
                    for dy in range(-SWEEP_Y, SWEEP_Y + 1):
                        c = (here[0] + dx, here[1] + dy)
                        if c in hovered or not (
                            0 <= c[0] < ok.shape[1] and 0 <= c[1] < ok.shape[0]
                        ):
                            continue
                        if not ok[c[1], c[0]] or mz.in_no_enter(zones, c) or (dx, dy) == (0, 0):
                            continue
                        u, v = project(here, [(dx, dy)])[0]
                        h0 = ref["here"]
                        u0, v0 = project(h0, [(c[0] - h0[0], c[1] - h0[1])])[0]
                        if not in_view(u, v):
                            continue
                        pa, pb = patch(ref["img"], u0, v0), patch(img_now, u, v)
                        if pa is None or pb is None:
                            continue
                        diff = float(np.abs(pa - pb).mean())
                        if diff >= SWEEP_DIFF:
                            changed.append((diff, c))
                changed.sort(key=lambda dc: (cheb2(dc[1], here), -dc[0]))
                for _diff, c in changed[:SWEEP_MAX]:
                    if picks >= LOOT_MAX_PICKS or time.monotonic() - t_s > LOOT_MAX_S:
                        break
                    if time.monotonic() - last_taken < 1.0:
                        end = "hit"
                        break
                    got = visit(c, "sweep")
                    sweep_n += 1
                    if got in ("fight", "escape"):
                        end = got
                        break
            ev({**out_, "hovered": len(hovered), "picks": picks, "sweep_changed": len(changed),
                "sweep_hovered": sweep_n, "end": end,
                "ms": round((time.monotonic() - t_s) * 1e3)})  # fmt: skip
            return "fight" if end == "fight" else "done"

        try:
            while time.monotonic() < t_end:
                tick = time.monotonic()
                if escaped[0]:  # a Fly Wing inside a scan or a strike (guard_tick)
                    escaped[0] = False
                    fly_at = tick
                    lock, goal_path = None, None
                    loot_list, fight_ref = [], None
                    mode = "search"
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
                taken_new = None
                for ln in new:
                    typ = ln.get("type")
                    if typ == "taken":
                        last_taken = tick
                        taken_new = taken_new or ln
                    elif typ == "damage":
                        last_ours = tick
                    elif typ == "base_exp":
                        kills_seen.append(tick)
                        ev({"kind": "kill", "by": "exp_line", "gm": None if here is None
                            else list(here)})  # fmt: skip
                        if here is not None:  # the loot list: the 5 x 5 around us at this death
                            loot_list.append((here, tick))
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
                            lock, goal_path = None, None
                            loot_list, fight_ref = [], None  # far away now
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
                near_ = None
                if boxes is not None and mode != "fight" and not sitting:  # a box never
                    near_ = boxes.near(FOOT_PX, BOX_NEAR_PX, BOX_FRESH_S)  # stands us up
                if (hit_now or dropped or near_ is not None) and mode != "fight":
                    # ONE engage event per fight, by what started it
                    if taken_new is not None:
                        ev({"kind": "engage", "by": "battle_log", "name": taken_new.get("name"),
                            "n": taken_new.get("n")})  # fmt: skip
                    elif hit_now:
                        ev({"kind": "engage", "by": "battle_log", "name": None, "late": True})
                    elif dropped:
                        ev({"kind": "engage", "by": "hp_drop", "name": None})
                    else:
                        ev({"kind": "engage", "by": "box", "name": None,
                            "box": [round(x_, 1) for x_ in near_ or ()]})  # fmt: skip
                    if sitting:
                        press("stand", "hit while sitting")
                        sitting = False
                        ev({"kind": "rest_end", "why": "hit", "pct": pct, "sp_pct": spp})
                    mode, goal_path = "fight", None
                    if fight_ref is None and here is not None:  # the sweep's "before"
                        fight_ref = {"img": img, "here": here, "t": tick}
                # UI watch (the hard bar: an unknown UI state)
                if tick - last_ui >= UI_EVERY_S and mode != "fight":
                    last_ui = tick
                    cs = f0.client_state(agent_raw, screen)
                    if cs["decision"]["do"] != "clear":
                        r.to_png(cs["frame"], out / "stop-ui.png")
                        reason = f"hard_bar: unknown UI state {cs['decision']}"
                        break
                # Amendment E: a fight, a loot step or a rest is activity, never idle (run 3: a
                # fight in place + a 25-s loot step read as 45 s of idle and cost a Fly Wing)
                if mode != "search":
                    idle_since = tick
                # --- FIGHT: locked, or scan for the attacker
                if mode == "fight":
                    if lock is not None:
                        since = tick - lock["t"]
                        idle = tick - max(last_ours, lock["t"])
                        if since > LOCK_MAX_S or (since > LOCK_NO_HIT_S and idle > LOCK_NO_HIT_S):
                            ev({"kind": "unlock", "why": "no hits" if since <= LOCK_MAX_S
                                else "max", "s": round(since, 1)})  # fmt: skip
                            lock = None
                    quiet = tick - last_taken > FIGHT_TAKEN_S and not hp_dropped(st.hist, tick)
                    if lock is None and quiet and kills_seen and kills_seen[-1] > tick - 3.0:
                        # pilot 4: after a kill with no hit for 2.5 s, rings 1 + 2 took 8.6 s to
                        # find nobody -- end the fight; the loot step's hovers still see a SWORD
                        mode = "after"
                        ev({"kind": "fight_end", "kills": len(kills_seen), "why": "quiet kill"})
                        continue
                    if lock is None:
                        found = scan("defend", ring(1), "sword")
                        if found is None and not quiet:  # ring 2 only while hits still come
                            found = scan("defend", ring(2), "sword")
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
                if mode == "after" and (loot_list or fight_ref is not None):
                    got_ = loot_step(loot_list, fight_ref)
                    idle_since = time.monotonic()
                    if got_ == "fight":
                        continue
                    loot_list, fight_ref = [], None
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
                        at_spot = spot is not None and cheb2(spot, here) <= REST_NEAR
                        late = tick - rest_since > REST_WALK_MAX_S  # Amendment B (3.98)
                        if at_spot or late:
                            press("sit", "at rest spot" if at_spot else "rest spot not reached")
                            sitting = True
                            rest_since = tick
                            ev({"kind": "rest_start", "cell": list(here), "pct": pct,
                                "sp_pct": spp, "spot": None if spot is None else list(spot),
                                "fallback": not at_spot})  # fmt: skip
                            continue
                        if goal_path is None or goal_path[-1] != spot:
                            goal_path = route(okr, carved, here, spot) if spot else None
                            ev(
                                {
                                    "kind": "rest_route",
                                    "to": list(spot) if spot else None,
                                    "len": None if goal_path is None else len(goal_path),
                                }
                            )
                            if goal_path is None:
                                mode = "search"
                # Amendment D: the IDLE watchdog -- searching with no walk click, no fight and no
                # move for IDLE_MAX_S = stuck (the routing fails, or the client will not walk)
                if here != idle_pos or mode != "search":
                    idle_pos, idle_since = here, tick
                elif tick - max(idle_since, last_walk_click) > IDLE_MAX_S:
                    ev({"kind": "stuck", "at": None if here is None else list(here), "why": "idle"})
                    press("fly", "idle")
                    fly_at = time.monotonic()
                    ev({"kind": "escape", "how": "fly", "why": "idle"})
                    idle_pos, idle_since, goal_path = None, tick, None
                    loot_list, fight_ref = [], None
                    time.sleep(1.0)
                    continue
                # --- SEARCH: the heading walk
                if mode == "search" and here is not None and (
                        goal_path is None or len(goal_path) < 2
                        or max(abs(goal_path[-1][0] - here[0]),
                               abs(goal_path[-1][1] - here[1])) <= 2):  # fmt: skip
                    goal = hf.heading_goal(area & ~carved, here, walk_st, rng)
                    goal_path = None if goal is None else route(okr, carved, here, goal)
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
                        goal_path = route(okr, carved, here, goal_path[-1])
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
                                stall = stall + 1 if walk_from == here else 0
                                if walk_from != here:
                                    stalls_here.clear()
                                walk_from = here
                                if stall >= STALL_CLICKS:  # clicks that did not move us
                                    ev({"kind": "stall", "at": list(here), "to": list(c)})
                                    turn_heading(walk_st)
                                    goal_path, stall = None, 0
                                    # Amendment C (run 1, 12:3x: 57 stalls at 27,75 -- the turn was
                                    # undone by the next goal's same route): the target the client
                                    # will not walk to leaves the route grid for the run
                                    carve(carved, c, CARVE_R)
                                    stalls_here.append(tick)
                                    if (
                                        sum(1 for t_ in stalls_here if tick - t_ <= 60.0)
                                        >= STUCK_STALLS
                                    ):
                                        ev({"kind": "stuck", "at": list(here)})
                                        press("fly", "stuck")
                                        fly_at = time.monotonic()
                                        ev({"kind": "escape", "how": "fly", "why": "stuck"})
                                        stalls_here.clear()
                                        loot_list, fight_ref = [], None
                                        time.sleep(1.0)
                                        continue
                                    # monsters that only MISS write no log line: look around
                                    found = scan("defend", ring(1), "sword")
                                    if found is not None:
                                        c2, (u2, v2), _r2 = found
                                        ev({"kind": "engage", "by": "stall_scan", "name": None})
                                        strike(u2, v2, c2, "stall_scan")
                                        lock = {"t": time.monotonic(), "rel": c2, "cell": None}
                                        mode = "fight"
                                    continue
                                click_at(u, v, "walk")
                                last_walk_click = tick
                                ev({"kind": "walk", "from": list(here), "to": list(c),
                                    "clicked": True, "why": mode})  # fmt: skip
                            elif res["verdict"] == "sword":
                                ev({"kind": "engage", "by": "walk_sword", "name": None})
                                strike(u, v - BODY_UP / 2, rel, "walk_sword")
                                lock = {"t": time.monotonic(), "rel": rel, "cell": list(c)}
                                mode = "fight"
                            else:
                                ev({"kind": "walk", "from": list(here), "to": list(c),
                                    "clicked": False, "why": f"cursor {res['verdict']}",
                                    "red": res.get("red")})  # fmt: skip
                                if res["verdict"] == "noentry":
                                    noentry_n += 1
                                    if noentry_n >= 2:  # the client calls it a wall: turn
                                        turn_heading(walk_st)
                                        goal_path, noentry_n = None, 0
                if here is None and tick - last_pos_t > 30.0:
                    reason = "position unread for 30 s"
                    break
                time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
        except r.Stop as exc:
            reason = f"stop: {exc}"
            raise
        except KeyboardInterrupt:  # the parent's SIGINT (a run stopped by hand): say so
            reason = "stopped_by_parent"
            raise
        finally:
            ev({"kind": "run_end", "reason": reason, "counts": dict(counts)})
            blt.stop()
            if boxes is not None:
                boxes.stop()
                ev({"kind": "box_watch", "frames": boxes.n, "self_boxes_skipped": boxes.n_self})
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
            if reason != "death":  # 13:19: a stopped run left the Crusader at 30 % HP among
                # orcs with no runner: after run_end (outside the measured window) it goes home
                try:
                    cr.gm_line(agent_raw, screen, f"@warp {CLEAR_STAND[0]} {CLEAR_STAND[1]} "
                               f"{CLEAR_STAND[2]}", "crusader")  # fmt: skip
                    time.sleep(3.0)
                    bench.close_chat(agent_raw, screen)
                except Exception as exc:  # noqa: BLE001 -- recorded; the next setup checks again
                    print(f"end warp failed: {exc!r}", flush=True)
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
