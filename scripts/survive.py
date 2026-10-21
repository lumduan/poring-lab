#!/usr/bin/env python3
"""The Crusader's survival skills (docs/demonstrations.md 3.96, pre-registered 2026-10-21 18:03
BEFORE this was built; Batt 2026-10-21: "HP read from Basic Info (pixel), potion on a hotkey below a
threshold, Fly Wing escape below a lower threshold or when more than N monsters are on us; Auto
Guard re-cast on expiry; Endure when mobbed (optional). DEATH = stop the run, record the cause").

PIXELS IN, KEYS OUT. The rules read the HP as Basic Info's PERCENT text (hp_percent.read;
3.96b's S1b -- the bar's length failed S1, 3.96 run log), its rate of fall over the last
RATE_WIN_S, the death dialog's signature (3.96b's S6b: the @ko variant cut on this client) and
the clock since our own casts; an unreadable percent is None and no rule acts on it. They
press the hotkeys F1 (White Potion), F2 (Fly Wing), F3 (Auto Guard, cast level 10), F4 (Endure).
Today's detector cannot see orcsdun01's species, so no rule counts attackers from boxes: "more than
N monsters on us" is carried by the HP's RATE of fall (3.96).

    survive.py trial --set T-S2|T-S3|T-S6|T-regen --pack C|E|none [--seconds 180] [--label L]

A trial (3.96's test bed, prt_fild08, immunity OFF, the Crusader standing still): `@monster`
packs beside it through crusader.gm_line (the name + job check), the rules of its set for
--seconds or until an escape or a death, then `@killmonster2`, `@heal`, `@warp` back. A death
STOPS the trial: the cause is recorded, the dialog is closed ONLY by its known step (its second
button, "return to game"; never Enter, never the first button), and only then `@alive` / `@heal`.
Every HP read and key press goes to the session's events.jsonl; the packets
(record_session.write_packets) are the truth the offline judge scores against. Nothing here reads
packets at decision time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEMO = Path("/dev/shm/poring-lab-demo")
MAX_HP = 5260  # the Crusader's verified MaxHP (crusader-orcsdun01.md 2b): HP/s from the bar
T_POT = 0.60  # S2: HP below this share -> F1
T_FLY = 0.25  # S3: HP below this share -> F2
RATE_FLY = 200.0  # S3: HP/s of fall over RATE_WIN_S -> F2 (~ a 4-5-orc pack)
RATE_ENDURE = 100.0  # S5: HP/s of fall -> F4
RATE_WIN_S = 2.0
POT_GAP_S = 0.7  # S2: no second F1 within this unless the bar rose since the last press
POT_MAX = 3  # S2: at most this many F1 ...
POT_MAX_WIN_S = 2.0  # ... in this many seconds
FLY_GAP_S = 3.0
AG_RECAST_S = 300.0  # S4b: Auto Guard lasts 300 s (skill_db CR_AUTOGUARD Duration1); a TOGGLE
AG_ABSENT_S = 1.0  # S4b: the icon absent on every read for this long before F3 (3.96c)
AG_ICON = Path(__file__).resolve().parents[1] / "data" / "crusader" / "ag_icon.npz"  # gitignored
AG_X = (1230, 1235)  # the status column's x range for the icon's left edge (cut at 1232)
AG_Y = (160, 430)  # its y range (the icons stack downward under the minimap)
AG_MATCH = 30.0  # grey masked mean |diff|: on 0-14, absent 50.2 (19:3x frames; the midpoint)
AG_EVERY = 3  # the icon is checked on every 3rd read
ENDURE_S = 37.0  # S5: Endure 10 lasts 37 s (skill_db SM_ENDURE Duration1), cooldown 10 s
READ_HZ = 5.0
KEYS = {"potion": "F1", "fly": "F2", "autoguard": "F3", "endure": "F4"}
SETS = {
    "T-S2": {"S1", "S2", "S4", "S6"},
    "T-S3": {"S1", "S3", "S6"},
    "T-S6": {"S1", "S6"},
    "T-regen": {"S1"},
}  # fmt: skip  (T-regen here = standing only; walking is not built: see 3.96's run log)
PACKS = {
    "C": [(1153, 3), (1152, 2)],
    "E": [(1153, 3), (1152, 2), (1111, 1)],
    "F": [(1153, 5), (1152, 3), (1111, 2)],
    "none": [],
}  # fmt: skip  (F: 3.96c)
STAND = ("prt_fild08", 268, 107)  # detector_check's scene: open field (3.96 amendment 18:4x)


@dataclass
class State:
    hist: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=64))
    pots: list[float] = field(default_factory=list)
    pot_frac: float | None = None  # the bar at the last F1
    fly: float = -1e9
    ag: float = -1e9
    ag_absent_since: float | None = None
    endure: float = -1e9


def rate_hp_s(hist: Sequence[tuple[float, float]], now: float, max_hp: float = MAX_HP,
              win: float = RATE_WIN_S) -> float | None:  # fmt: skip
    """PURE: HP lost per second over the last ``win`` s of bar reads (positive = falling); None
    until the reads span at least half the window."""
    pts = [(t, f) for t, f in hist if now - win <= t <= now]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < win / 2:
        return None
    (t0, f0), (t1, f1) = pts[0], pts[-1]
    return (f0 - f1) * max_hp / (t1 - t0)


def _grey(a: Any) -> Any:
    a = np.asarray(a)[..., :3].astype(np.float32)
    return a[..., 0] * 0.114 + a[..., 1] * 0.587 + a[..., 2] * 0.299


def ag_present(client_bgr: Any, tmpl: Any, mask: Any) -> bool:
    """PURE: Auto Guard's status icon anywhere in the right-hand status column (its template, in
    grey, on its own bright pixels: masked mean |diff| <= AG_MATCH)."""
    from numpy.lib.stride_tricks import sliding_window_view

    x0, x1 = AG_X
    y0, y1 = AG_Y
    reg = _grey(np.asarray(client_bgr)[y0 : y1 + 32, x0 : x1 + 32])
    win = sliding_window_view(reg, (32, 32))  # (ny, nx, 32, 32)
    d = np.abs(win[..., mask] - _grey(tmpl)[mask]).mean(axis=-1)
    return bool(d.min() <= AG_MATCH)


def decide(st: State, now: float, frac: float, rules: set[str],
           ag_on: bool | None = None) -> list[tuple[str, str]]:  # fmt: skip
    """PURE: the hotkeys to press now, with why. The escape first (it ends the trial); then a
    potion; Auto Guard's re-cast; Endure. ``st`` is updated for what is returned."""
    out: list[tuple[str, str]] = []
    st.hist.append((now, frac))
    rate = rate_hp_s(st.hist, now)
    if "S3" in rules and now - st.fly >= FLY_GAP_S:
        why = ("hp" if frac < T_FLY else
               "rate" if rate is not None and rate > RATE_FLY else None)  # fmt: skip
        if why:
            st.fly = now
            return [("fly", f"{why}: frac {frac:.3f} rate {rate}")]
    if "S2" in rules and frac < T_POT:
        recent = [t for t in st.pots if now - t <= POT_MAX_WIN_S]
        rose = st.pot_frac is not None and frac > st.pot_frac + 0.01
        gap_ok = not st.pots or now - st.pots[-1] >= POT_GAP_S or rose
        if gap_ok and len(recent) < POT_MAX:
            st.pots.append(now)
            st.pot_frac = frac
            out.append(("potion", f"frac {frac:.3f}"))
    if "S4" in rules and ag_on is not None:
        # S4b (3.96c): Auto Guard is a TOGGLE -- F3 only when its icon has been ABSENT on every read
        # for AG_ABSENT_S and, after a cast of ours, its 300 s have passed
        if ag_on:
            st.ag_absent_since = None
        else:
            st.ag_absent_since = st.ag_absent_since if st.ag_absent_since is not None else now
            if now - st.ag_absent_since >= AG_ABSENT_S and now - st.ag >= AG_RECAST_S:
                first = st.ag < 0
                st.ag = now
                st.ag_absent_since = None
                out.append(("autoguard", "first cast" if first else "recast"))
    if "S5" in rules and rate is not None and rate > RATE_ENDURE and now - st.endure >= ENDURE_S:
        st.endure = now
        out.append(("endure", f"rate {rate:.0f}"))
    return out


# --- live ---------------------------------------------------------------------------------------


def trial(a: argparse.Namespace) -> int:  # noqa: PLR0915
    import bench
    import crusader as cr
    import gm_vitals as gv
    import hp_percent as hpp
    import record_session as rs
    import ro_agent as r
    import ui_gate

    rules = SETS[a.set]
    z = np.load(hpp.GLYPHS)
    glyphs = {("%" if k == "pct" else k[1:]): z[k] for k in z.files}
    agz = np.load(AG_ICON)
    ag_t, ag_m = agz["template"], agz["mask"].astype(bool)
    sid = f"{time.strftime('%Y%m%dT%H%M%S')}-demo-crusader-survival-{a.set}-{a.pack}-{a.label}"
    out = DEMO / sid
    out.mkdir(parents=True, exist_ok=False)
    evf = (out / "events.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        evf.write(json.dumps({"t_ns": r.ns(), **rec}) + "\n")
        evf.flush()

    t0 = r.ns()
    reason = "time_box"
    counts = {"reads": 0, "potion": 0, "fly": 0, "autoguard": 0, "endure": 0}
    with r.session(f"rule:crusader-survival-{a.set}") as (agent, screen):
        agent.wait_for_human()
        got = cr.check(screen, "crusader")
        if not got["ok"]:
            raise r.Stop(f"identity {got}")
        ui_gate.ensure_clear(agent, screen, why="survive-start")
        x0, y0, w0, h0 = r.game_region()
        start_pct = hpp.read(r.grab_after(screen, (x0, y0, w0, h0), r.ns()), glyphs)
        if start_pct != 100 or r.is_state(screen, gv.DEAD_STATE):
            raise r.Stop(f"survive: not a clean start (HP read {start_pct}, dead dialog?)")
        ev({"kind": "start_check", "pct": start_pct})
        if a.topup > 0:  # 3.96c: the potions back to 50 (weight under 50 %: regen not stopped)
            cr.gm_line(agent, screen, f"@item 504 {int(a.topup)}", "crusader")
            ev({"kind": "topup", "potions": int(a.topup)})
        for mob, n in PACKS[a.pack]:
            cr.gm_line(agent, screen, f"@monster {mob} {n}", "crusader")
            ev({"kind": "spawn", "mob": mob, "n": n})
        bench.close_chat(agent, screen)
        r.activate_client(agent, screen)
        st = State()
        gx, gy, gw, gh = r.game_region()
        t_end = time.monotonic() + a.seconds
        try:
            while time.monotonic() < t_end:
                tick = time.monotonic()
                frame = r.grab_after(screen, (gx, gy, gw, gh), r.ns())
                pct = hpp.read(frame, glyphs)
                bar = gv.hp_fraction(frame)
                # S4b's icon on every AG_EVERY-th read (~0.6 s apart: the rule needs >= 1 s absent)
                check_ag = "S4" in rules and counts["reads"] % AG_EVERY == 1
                ag_on = ag_present(frame, ag_t, ag_m) if check_ag else None
                dead = r.is_state(screen, gv.DEAD_STATE)
                counts["reads"] += 1
                ev({"kind": "hp_read", "frac": None if pct is None else pct / 100.0, "pct": pct,
                    "bar": round(bar, 4), "dead": dead, "ag_on": ag_on})  # fmt: skip
                if dead and "S6" in rules:
                    reason = "death"
                    last = [[round(t, 2), round(f, 4)] for t, f in list(st.hist)[-50:]]
                    ev({"kind": "death", "last_reads": last})
                    break
                if pct is None:
                    counts["unread"] = counts.get("unread", 0) + 1
                    time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
                    continue
                for what, why in decide(st, time.monotonic(), pct / 100.0, rules, ag_on):
                    agent.keys(KEYS[what])
                    counts[what] += 1
                    ev({"kind": "press", "what": what, "key": KEYS[what], "why": why})
                    if what == "fly":
                        reason = "escape"
                if reason == "escape":
                    time.sleep(2.0)
                    break
                time.sleep(max(0.0, 1.0 / READ_HZ - (time.monotonic() - tick)))
        finally:
            ev({"kind": "trial_end", "reason": reason, "counts": counts})
            if reason == "death":
                # the known step only: the dialog's second button ("return to game")
                x, y = gx + gv.RETURN_TO_GAME[0], gy + gv.RETURN_TO_GAME[1]
                agent.move(x + 4, y + 3)
                time.sleep(0.08)
                agent.move(x, y)
                time.sleep(0.3)
                agent.click(x, y)
                time.sleep(1.5)
                if r.is_state(screen, gv.DEAD_STATE):
                    raise r.Stop("survive: the death dialog stayed after its known step")
            for cmd in (["@alive"] if reason == "death" else []) + ["@killmonster2", "@heal"]:
                cr.gm_line(agent, screen, cmd, "crusader")
                time.sleep(0.8)
            if reason == "escape" or a.pack != "none":
                cr.gm_line(agent, screen, f"@warp {STAND[0]} {STAND[1]} {STAND[2]}", "crusader")
                time.sleep(3.0)
            bench.close_chat(agent, screen)
            print(r.to_png(screen.full(), r.SHOTS / f"survive-{sid}.png"))
    t1 = r.ns()
    evf.close()
    n_pk = 0
    try:
        events, _anchor = rs.write_packets(out, t0, t1)
        n_pk = len(events)
    except Exception as exc:  # noqa: BLE001 -- the trial is still recorded; the judge says so
        n_pk = -1
        print(f"packets not written: {exc!r}")
    man = {"sid": sid, "set": a.set, "rules": sorted(rules), "pack": a.pack, "seconds": a.seconds,
           "reason": reason, "counts": counts, "t0_ns": t0, "t1_ns": t1, "packets": n_pk,
           "thresholds": {"T_POT": T_POT, "T_FLY": T_FLY, "RATE_FLY": RATE_FLY,
                          "RATE_ENDURE": RATE_ENDURE, "MAX_HP": MAX_HP}}  # fmt: skip
    (out / "manifest.json").write_text(json.dumps(man, indent=1))
    print(json.dumps({"sid": sid, "reason": reason, "counts": counts, "packets": n_pk}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trial")
    t.add_argument("--set", required=True, choices=sorted(SETS))
    t.add_argument("--pack", required=True, choices=sorted(PACKS))
    t.add_argument("--seconds", type=float, default=180.0)
    t.add_argument("--label", default="t")
    t.add_argument("--topup", type=int, default=0, help="@item 504 N at the start (3.96c)")
    a = ap.parse_args()
    return trial(a)


if __name__ == "__main__":
    raise SystemExit(main())
