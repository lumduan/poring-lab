#!/usr/bin/env python3
"""agent-demo@1: the AGENT plays a competition round itself (Batt, 2026-10-17).

Batt's three-way competition: his recorded demo vs the agent vs the bot. The agent (Claude) plays
10 minutes step by step from screenshots, one command at a time. Every input goes through the bot's
own path (the internal channel, source=bot, the mux) and gates:
- attack: the client's NAME TAG must read a target under the pointer before the click
  (hunt-flow@16's rule: Poring / Lunatic / Pupa / Drops), then a burst until the client's attack
  arrow (<= 3 more clicks, 0.6 s apart, the tag re-read before each);
- walk: the walk guard (hunt-flow@16: not within 120 px of the GM, no pink within 80 px), no monster
  box within 40 px, robust2's WALK series from a standstill (cursor_gate) -- while the GM walks
  (the background moves) the guard and the unit check alone, the bot's moving rule;
- loot: the cursor reads PICKUP twice (cursor_gate.gated_click), no monster box within 30 px.

PACKET-ASSISTED (ADR-0007 Amendment D, Batt 2026-10-17): this tool, and only this tool, reads the
sniffer's archive DURING play (record_session's read-only path), on the lab rAthena only, passively,
and shows the agent monster positions / species, our cell, floor items and deaths. Everything it
produces is labelled packet-assisted. The bot never imports it (test_agent_play.py pins that).
The hard bars are watched live from the same packets (an NPC contact, a non-target hit or a map
change ends the session at once) and judged offline as for every session.

    agent_play.py serve --seed S [--minutes 10] [--round R]   the session (run it in the background)
    agent_play.py look                                        -> an annotated frame + JSON
    agent_play.py strike U V [--gid G] [--why T] [--fact T]   (client px of the game region)
    agent_play.py walk U V [--why T] [--fact T]
    agent_play.py loot U V [--why T] [--fact T]
    agent_play.py wait S
    agent_play.py status | end
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import socket
import sys
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

SOCK = Path("/dev/shm/poring-lab-tmp/agent-play.sock")
LOOK_DIR = Path("/dev/shm/poring-lab-tmp/agent-play")
RULE = "agent-demo"
MAP = "prt_fild08"
GM_GID = 2000002
SELF_MS_CELL = 150.0  # the GM's walk (hunt@5's packets)
SPECIES = {1002: "Poring", 1063: "Lunatic", 1008: "Pupa", 1113: "Drops", 1018: "Creamy"}
TARGET_JOBS = (1002, 1063, 1008, 1113)  # farm0.TARGETS: prt_fild08's spawn table
TAG_WAIT_S = 1.2
BURST_MAX = 3
BURST_GAP_S = 0.6
WALK_UNIT_PX = 40.0
LOOT_UNIT_PX = 30.0
POLL_S = 1.0
Cell = tuple[int, int]


# --- the packet world (PURE: fed events, asked for a snapshot) ------------------------------------


def mob_cell_at(rec: dict[str, Any], t_ns: int) -> tuple[float, float]:
    """PURE: a mob's cell at ``t_ns`` -- its standing cell, or along its move from (x, y) toward
    (x1, y1) at ``speed`` ms a cell (Chebyshev steps), stopped at the destination."""
    x, y = float(rec["x"]), float(rec["y"])
    if rec.get("x1") is None or rec.get("t_move") is None:
        return x, y
    x1, y1 = float(rec["x1"]), float(rec["y1"])
    n = max(abs(x1 - x), abs(y1 - y))
    if n == 0:
        return x1, y1
    done = min(n, max(0.0, (t_ns - int(rec["t_move"])) / 1e6 / float(rec.get("speed") or 150)))
    return x + (x1 - x) * done / n, y + (y1 - y) * done / n


class LiveWorld:
    """PURE (fed events in time order): what the packets say now -- our cell, the live mobs, the
    floor items, the deaths, and the hard bars seen since ``t0``."""

    def __init__(self) -> None:
        self.mobs: dict[int, dict[str, Any]] = {}
        self.items: dict[int, dict[str, Any]] = {}
        self.deaths: dict[int, int] = {}
        self.hit: dict[int, int] = {}  # gid -> our last damaging act
        self.me: dict[str, Any] | None = None
        self.last_t = 0
        self.t0: int | None = None
        self.bars: list[str] = []

    def feed(self, events: Iterable[dict[str, Any]]) -> None:
        for e in events:
            t = int(e.get("t_mono_ns", 0))
            if t <= self.last_t:
                continue
            self.last_t = t
            typ = e.get("type")
            gid = e.get("gid")
            if typ == "entity_appear" and gid is not None and int(gid) != GM_GID:
                moving = e.get("x1") is not None
                self.mobs[int(gid)] = {
                    "job": e.get("job"), "x": e.get("x"), "y": e.get("y"),
                    "x1": e.get("x1") if moving else None, "y1": e.get("y1") if moving else None,
                    "t_move": t if moving else None, "speed": e.get("speed"),
                }  # fmt: skip
            elif typ == "entity_stop" and gid is not None:
                if int(gid) == GM_GID:
                    self.me = {"x": e["x"], "y": e["y"], "x1": None, "y1": None, "t_move": None}
                elif int(gid) in self.mobs:
                    self.mobs[int(gid)].update(x=e["x"], y=e["y"], x1=None, y1=None, t_move=None)
            elif typ == "entity_vanish" and gid is not None:
                m = self.mobs.pop(int(gid), None)
                if int(e.get("reason", -1)) == 1 and m is not None:
                    self.deaths[int(gid)] = t
            elif typ == "self_move":
                self.me = {"x": e["x0"], "y": e["y0"], "x1": e["x1"], "y1": e["y1"],
                           "t_move": t, "speed": SELF_MS_CELL}  # fmt: skip
            elif typ == "map_change":
                self.me = {"x": e.get("x"), "y": e.get("y"), "x1": None, "y1": None,
                           "t_move": None}  # fmt: skip
                self.mobs.clear()
                self.items.clear()
                if self.t0 is not None and t >= self.t0:
                    self.bars.append("map_change")
            elif typ == "floor_item_appear":
                self.items[int(e["floor_id"])] = {"x": e["x"], "y": e["y"], "sub_x": e.get("sub_x"),
                                                  "sub_y": e.get("sub_y"), "t": t}  # fmt: skip
            elif typ == "floor_item_vanish":
                self.items.pop(int(e["floor_id"]), None)
            elif typ == "act" and int(e.get("src_gid") or 0) == GM_GID:
                tg = int(e.get("target_gid") or 0)
                if int(e.get("damage") or 0) > 0:
                    self.hit[tg] = t
                    job = (self.mobs.get(tg) or {}).get("job")
                    if (self.t0 is not None and t >= self.t0 and job is not None
                            and int(job) not in TARGET_JOBS):  # fmt: skip
                        self.bars.append(f"non_target_hit:{job}")
            elif typ == "npc_contact" and self.t0 is not None and t >= self.t0:
                self.bars.append("npc_contact")

    def snapshot(self, t_ns: int) -> dict[str, Any]:
        me = None if self.me is None else mob_cell_at(self.me, t_ns)
        mobs = []
        for gid, m in self.mobs.items():
            c = mob_cell_at(m, t_ns)
            mobs.append({"gid": gid, "job": m.get("job"),
                         "species": SPECIES.get(int(m.get("job") or 0), f"job{m.get('job')}"),
                         "cell": [round(c[0], 1), round(c[1], 1)],
                         "moving": m.get("x1") is not None and tuple(c) != (m["x1"], m["y1"]),
                         "hit_s_ago": None if gid not in self.hit
                         else round((t_ns - self.hit[gid]) / 1e9, 1)})  # fmt: skip
        if me is not None:
            mobs.sort(key=lambda m: max(abs(m["cell"][0] - me[0]), abs(m["cell"][1] - me[1])))
        items = [
            {
                "floor_id": f,
                "cell": [i["x"], i["y"]],
                "sub": [i.get("sub_x"), i.get("sub_y")],
                "age_s": round((t_ns - i["t"]) / 1e9, 1),
            }
            for f, i in self.items.items()
        ]
        deaths = [{"gid": g, "s_ago": round((t_ns - t) / 1e9, 1)} for g, t in self.deaths.items()
                  if t_ns - t < 15e9]  # fmt: skip
        return {"me": None if me is None else [round(me[0], 1), round(me[1], 1)], "mobs": mobs,
                "items": items, "deaths": deaths, "bars": list(self.bars)}  # fmt: skip


def self_moving(me: dict[str, Any] | None, t_ns: int) -> bool:
    """PURE: our GM is still walking its last self_move at ``t_ns`` (the packets' view)."""
    if me is None or me.get("x1") is None:
        return False
    c = mob_cell_at(me, t_ns)
    return (round(c[0]), round(c[1])) != (int(me["x1"]), int(me["y1"]))


def nearest_box(boxes: Sequence[Any], u: float, v: float, max_px: float) -> Any:
    """PURE: the monster box whose centre is nearest (u, v) within ``max_px``, else None."""
    best = None
    for b in boxes:
        d = math.hypot((b.x0 + b.x1) / 2 - u, (b.y0 + b.y1) / 2 - v)
        if d <= max_px and (best is None or d < best[0]):
            best = (d, b)
    return None if best is None else best[1]


def item_px_offset(sub: Sequence[Any] | None) -> tuple[float, float]:
    """PURE: a floor item's sub-cell offset in cells (the client draws it at cell + sub/16 - 0.5),
    (0, 0) when unknown."""
    if not sub or sub[0] is None or sub[1] is None:
        return 0.0, 0.0
    return float(sub[0]) / 16.0 - 0.5, float(sub[1]) / 16.0 - 0.5


# --- the client: send a command to the session --------------------------------------------------


def send(req: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(str(SOCK))
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return json.loads(buf.decode() or "{}")


# --- the session ---------------------------------------------------------------------------------


def serve(a: argparse.Namespace) -> int:  # noqa: PLR0915
    import multiprocessing as mp

    import bench
    import chat_guard
    import cursor_gate
    import farm0 as f0
    import gm_state
    import hunt
    import hunt_core as hc
    import hunt_flow as hf
    import loot1
    import nametag
    import operator_hud
    import record_session
    import ro_agent as r
    import route_demo
    import route_preview
    import rule_run as rr
    import unit_detector
    import walk5 as w5
    from anim_region import stand_grid
    from PIL import Image, ImageDraw

    from poring_dataset import camera as cam
    from poring_dataset import gat as gatmod
    from poring_env.demo import DemoLog, new_session_id

    # Amendment D's scope, checked before anything moves
    h = r.backend_health()
    env = h.get("environment") or {}
    if env.get("server") != "lab-rathena" or env.get("state") != "green":
        raise SystemExit("agent-demo refused: packets are read only on the attested lab rAthena "
                         f"({env.get('server')} / {env.get('state')})")  # fmt: skip
    if h.get("mode") != "ASSIST" or h.get("lease_active"):
        raise SystemExit(f"agent-demo refused: mux {h.get('mode')}, lease {h.get('lease_active')}")
    ok_imm, why_imm = f0.immunity_confirmed()
    if not ok_imm:
        raise SystemExit(f"agent-demo refused: the GM is not confirmed immune ({why_imm})")
    lock = record_session.read_lock(r.ROOT / "state")
    if str(lock.backend) != "rdp" or lock.phase != "steady":
        raise SystemExit(f"agent-demo refused: the lock says {lock.backend}/{lock.phase}")

    gat = gatmod.parse((cam.GAT_DIR / f"{MAP}.gat").read_bytes())
    ok = stand_grid(MAP, gat)
    kb = r.ROOT / "data" / "kb"
    warps = json.loads((kb / "warps.json").read_text()).get(MAP, [])
    npcs = json.loads((kb / "npc_cells.json").read_text())["maps"].get(MAP, {}).get("npcs", [])
    keep = [(w["x"], w["y"], w["span_x"], w["span_y"]) for w in warps]
    keep += [(n["x"], n["y"], 1, 1) for n in npcs]
    area = hc.search_area(ok, keep, margin=10)
    start = hunt.start_cell(area, a.seed)
    cj = json.loads((r.ROOT / "packages/poring_dataset/src/poring_dataset/camera_rdp.json")
                    .read_text())  # fmt: skip
    camera = cam.camera_from_json(cj["camera"])
    world = w5.World(camera, gat, start)
    gx0, gy0, gw, gh = r.game_region()
    templates = nametag.load_templates()
    ui_rects = [(x0 - 4, y0 - 4, x1 + 4, y1 + 4) for x0, y0, x1, y1 in route_preview.UI_WINDOWS]

    def in_view(u: float, v: float) -> bool:
        return 0 <= u < gw and 0 <= v < gh and not loot1.in_ui(u, v)

    sid = new_session_id(RULE)
    log = DemoLog(sid)
    frames_dir = hf.REC_ROOT / sid / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    LOOK_DIR.mkdir(parents=True, exist_ok=True)
    log.start(backend=str(lock.backend), lock_seq=lock.seq, server="lab-rathena",
              rule=f"{RULE}@1", account="gm", map=MAP, minutes=a.minutes, seed=a.seed,
              start=list(start), round=a.round, packet_assisted=True, actor="agent",
              scored=True, immunity=why_imm, frames_dir=str(frames_dir),
              gm_profile="hunt-flow")  # fmt: skip
    print(json.dumps({"session": sid, "round": a.round, "start": time.strftime("%H:%M:%S")}),
          flush=True)  # fmt: skip
    events_f = (log.dir / "events.jsonl").open("a")
    clicks_f = (log.dir / "clicks.jsonl").open("a")

    def ev(rec: dict[str, Any]) -> None:
        events_f.write(json.dumps({"t_ns": r.ns(), **rec}, default=str) + "\n")
        events_f.flush()

    def click_log(rec: dict[str, Any]) -> None:
        clicks_f.write(json.dumps(rec, default=str) + "\n")
        clicks_f.flush()

    live = LiveWorld()
    halt = threading.Event()
    t_first = r.ns()

    def poll() -> None:
        while not halt.is_set():
            with contextlib.suppress(Exception):
                t_ = r.ns()
                evs_ = record_session._events_since(t_first - 120_000_000_000, 125.0,
                                                    t_first - 120_000_000_000, t_)  # fmt: skip
                # R1: the shards come unordered; LiveWorld skips anything older than its last
                # event, so an unsorted feed dropped mobs and floor items
                live.feed(sorted(evs_, key=lambda e: int(e.get("t_mono_ns", 0))))
            halt.wait(POLL_S)

    ctx = mp.get_context("spawn")
    stop_rec = ctx.Event()
    rec = ctx.Process(target=route_demo._record, args=(str(frames_dir), (gx0, gy0, gw, gh),
                                                       stop_rec, hf.REC_HZ, hf.REC_QUALITY),
                      daemon=True)  # fmt: skip
    engagements: list[dict[str, Any]] = []
    state: dict[str, Any] = {"t_move0": None, "deadline": None, "ended": None, "looks": 0}
    sampler = None
    with r.session(f"rule:{RULE}@1") as (agent, screen):
        f0.stop_on_takeover(agent)
        hud_tok = operator_hud.enable(f"{RULE} {a.round} (packet-assisted)", agent=agent)
        det = unit_detector.UnitDetector()
        rec.start()
        poller = threading.Thread(target=poll, daemon=True)
        poller.start()
        srv = None
        try:
            pr = cursor_gate.prober(agent, screen)
            chat_guard.start_run(f"{RULE}-{sid}")
            before = gm_state.ensure_fixed(agent, screen, why=f"{RULE}:before",
                                           out_dir=log.dir / "gm_state", profile="hunt-flow",
                                           loot=True)  # fmt: skip
            ev({"kind": "gm_state_before", **f0._brief(before)})
            r.gm(agent, screen, f"@warp {MAP} {start[0]} {start[1]}")
            time.sleep(rr.SCENE_ENTRY_S)
            bench.close_chat(agent, screen)
            r.activate_client(agent, screen)
            sampler = loot1.Sampler(det)
            sampler.start()
            ev({"kind": "ready", "start": list(start)})

            def frame() -> Any:
                return screen.grab(gx0, gy0, gw, gh)[1]

            def boxes_now() -> list[Any]:
                fr = sampler.since(max(0, len(sampler.frames) - 1)) if sampler else []
                return list(fr[-1][1]) if fr else []

            def project(cell: Sequence[float]) -> tuple[float, float] | None:
                snap = live.snapshot(r.ns())
                me = snap["me"]
                if me is None:
                    return None
                return hf.frac_project(world, me, cell)

            def move(u: float, v: float) -> None:
                agent.move(gx0 + round(u) - 12, gy0 + round(v) - 12)  # two motions: drawn
                time.sleep(0.06)
                agent.move(gx0 + round(u), gy0 + round(v))
                state["ptr"] = (u, v)

            def read_tag(u: float, v: float) -> tuple[str | None, int, float, float]:
                """The tag under the pointer within TAG_WAIT_S; the pointer FOLLOWS the nearest
                fresh detector box (> 10 px away) while it hops (R0 attempt 1: a hopping Poring
                left a still pointer, 6 of 7 reads empty). Returns where the pointer ended."""
                t_a = time.monotonic()
                move(u, v)
                while time.monotonic() - t_a < TAG_WAIT_S:
                    time.sleep(0.1)
                    b = nearest_box(boxes_now(), u, v, 60.0)
                    if b is not None:
                        cu, cv = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
                        if math.hypot(cu - u, cv - v) > 10 and in_view(cu, cv):
                            u, v = cu, cv
                            agent.move(gx0 + round(u), gy0 + round(v))
                    img = frame()
                    bands = hf.tag_boxes(b, (u, v), True)[0 if b is not None else 1 :]
                    for bb in bands:
                        name, _iou = nametag.match(nametag.letter_mask(nametag.band(img, bb)),
                                                   templates)  # fmt: skip
                        if name is not None:
                            return name, round((time.monotonic() - t_a) * 1000), u, v
                return None, round((time.monotonic() - t_a) * 1000), u, v

            def resolve(q: dict[str, Any]) -> tuple[float, float] | None:
                """The aim point NOW (the agent decides seconds earlier): a monster by its packet
                gid -> its projected cell -> the nearest detector box there; a floor item by its
                floor id (cell + sub offset); a cell; else the given client px."""
                snap = live.snapshot(r.ns())
                if q.get("gid") is not None:
                    m = next((x for x in snap["mobs"] if x["gid"] == int(q["gid"])), None)
                    p = None if m is None else project(m["cell"])
                    if p is None:
                        return None
                    b = nearest_box(boxes_now(), p[0], p[1] - 10, 70.0)
                    return ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2) if b else (p[0], p[1] - 10)
                if q.get("fid") is not None:
                    it = next((x for x in snap["items"] if x["floor_id"] == int(q["fid"])), None)
                    if it is None:
                        return None
                    ox, oy = item_px_offset(it["sub"])
                    return project((it["cell"][0] + ox, it["cell"][1] + oy))
                if q.get("cx") is not None:
                    return project((float(q["cx"]), float(q["cy"])))
                if q.get("u") is None:
                    return None
                return float(q["u"]), float(q["v"])

            def above(img: Any, u: float, v: float) -> Any:
                a_ = np.asarray(img)
                return a_[max(0, int(v) - 80): max(0, int(v) - 15),
                          max(0, int(u) - 45): max(0, int(u) + 45), :3]  # fmt: skip

            def first_move() -> None:
                if state["t_move0"] is None:
                    state["t_move0"] = time.monotonic()
                    state["deadline"] = state["t_move0"] + a.minutes * 60
                    live.t0 = r.ns()
                    ev({"kind": "loop_start"})

            def do_attack(q: dict[str, Any]) -> dict[str, Any]:
                t_s = time.monotonic()  # R0: every empty tag read was while the GM walked
                while self_moving(live.me, r.ns()) and time.monotonic() - t_s < 1.5:
                    time.sleep(0.1)
                p = resolve(q)
                if p is None:
                    return {"clicked": False, "why": "gone"}
                u, v = p
                if not in_view(u, v):
                    return {"clicked": False, "why": "off_view", "u": round(u), "v": round(v)}
                first_move()
                tag, ms, u, v = read_tag(u, v)
                if tag not in nametag.TARGET_NAMES:
                    ev({"kind": "tag_refused", "tag": tag, "ms": ms, "u": u, "v": v,
                        "why": q.get("why"), "fact": q.get("fact")})  # fmt: skip
                    return {"clicked": False, "why": "tag", "tag": tag, "ms": ms}
                ref = above(frame(), u, v)
                tc = r.ns()
                agent.click(gx0 + round(u), gy0 + round(v))
                gid = q.get("gid")
                snap = live.snapshot(tc)
                tgt = next((m for m in snap["mobs"] if gid is not None and m["gid"] == int(gid)),
                           None)  # fmt: skip
                me = snap["me"] or list(start)
                pred = tgt["cell"] if tgt else me
                click_log({"t": tc, "u": round(u, 1), "v": round(v, 1), "kind": "strike",
                           "branch": "agent", "tag": tag, "read_ms": ms, "gid": gid,
                           "why": q.get("why"), "fact": q.get("fact")})  # fmt: skip
                n, arrow_s = 1, None
                t0c = time.monotonic()
                while n <= BURST_MAX:
                    time.sleep(BURST_GAP_S)
                    if hf.arrow_new(ref, above(frame(), u, v)):
                        arrow_s = round(time.monotonic() - t0c, 2)
                        break
                    if n == BURST_MAX:
                        break
                    tag2, _, u, v = read_tag(u, v)
                    if tag2 not in nametag.TARGET_NAMES:
                        break
                    tb = r.ns()
                    agent.click(gx0 + round(u), gy0 + round(v))
                    click_log({"t": tb, "u": round(u, 1), "v": round(v, 1),
                               "kind": "strike_burst", "n": n + 1, "tag": tag2})  # fmt: skip
                    n += 1
                eng = {"k": len(engagements), "track": gid, "t_first_click": tc,
                       "pred_cell": pred, "here": me, "clicks": n, "result": "clicked",
                       "t_end": r.ns(), "hovers": [{"clicked": tc}], "tag": tag,
                       "why": q.get("why"), "fact": q.get("fact")}  # fmt: skip
                engagements.append(eng)
                ev({"kind": "engagement", "k": eng["k"], "gid": gid, "clicks": n,
                    "arrow_s": arrow_s})  # fmt: skip
                return {"clicked": True, "tag": tag, "tag_ms": ms, "clicks": n, "arrow_s": arrow_s}

            def do_walk(q: dict[str, Any]) -> dict[str, Any]:
                p = resolve(q)
                if p is None:
                    return {"clicked": False, "why": "no_point"}
                u, v = p
                if not in_view(u, v) and q.get("cx") is not None:
                    # a far cell: the same direction, 260 px from the GM's sprite
                    du, dv = u - hf.GM_SPRITE_PX[0], v - hf.GM_SPRITE_PX[1]
                    k = 260.0 / max(1e-6, math.hypot(du, dv))
                    u, v = hf.GM_SPRITE_PX[0] + du * k, hf.GM_SPRITE_PX[1] + dv * k
                if not in_view(u, v):
                    return {"clicked": False, "why": "off_view"}
                rg = 80
                x0, y0 = max(0, int(u) - rg), max(0, int(v) - rg)
                x1, y1 = min(gw, int(u) + rg + 1), min(gh, int(v) + rg + 1)
                crop = screen.grab(gx0 + x0, gy0 + y0, x1 - x0, y1 - y0)[1]
                share = hf.pink_share(
                    crop, (x0, y0), u, v, rg, hf.GUARD_EXCLUDE, ui_rects, state.get("ptr")
                )  # not our own drawn cursor
                why = hf.walk_guard_why(u, v, share, 120.0, 0.001)
                if why is not None:
                    return {"clicked": False, "why": f"guard_{why}"}
                if nearest_box(boxes_now(), u, v, WALK_UNIT_PX) is not None:
                    return {"clicked": False, "why": "unit_near"}
                first_move()
                moving = self_moving(live.me, r.ns())
                if not moving:
                    res = cursor_gate.gated_click(pr, u, v)
                    if not res.get("clicked") and "stale" not in str(res.get("why")):
                        return {"clicked": False, "why": res.get("why")}
                    if not res.get("clicked"):
                        moving = True  # the background moved: the bot's moving rule
                    tc = int(res.get("t_click") or r.ns())
                if moving:
                    tc = r.ns()
                    agent.click(gx0 + round(u), gy0 + round(v))
                state["ptr"] = (u, v)
                to_ = None
                if q.get("cx") is not None:
                    to_ = [round(float(q["cx"])), round(float(q["cy"]))]
                click_log({"t": tc, "u": round(u, 1), "v": round(v, 1), "kind": "walk",
                           "gate": "guard+units" if moving else "cursor",
                           **({"to": to_} if to_ else {}),
                           "why": q.get("why"), "fact": q.get("fact")})  # fmt: skip
                return {"clicked": True, "gate": "guard+units" if moving else "cursor"}

            def do_loot(q: dict[str, Any]) -> dict[str, Any]:
                p = resolve(q)
                if p is None:
                    return {"clicked": False, "why": "gone"}
                u, v = p
                if not in_view(u, v):
                    return {"clicked": False, "why": "off_view"}
                if nearest_box(boxes_now(), u, v, LOOT_UNIT_PX) is not None:
                    return {"clicked": False, "why": "unit_near"}
                first_move()
                res = cursor_gate.gated_click(pr, u, v, allow=("pickup",))
                if res.get("clicked"):
                    click_log({"t": int(res["t_click"]), "u": round(u, 1), "v": round(v, 1),
                               "kind": "loot", "why": q.get("why"),
                               "fact": q.get("fact")})  # fmt: skip
                return {"clicked": bool(res.get("clicked")), "why": res.get("why"),
                        "shape": res.get("shape")}  # fmt: skip

            def do_look(_q: dict[str, Any]) -> dict[str, Any]:
                img = np.asarray(frame())[..., :3][..., ::-1]  # BGRA -> RGB
                pil = Image.fromarray(np.ascontiguousarray(img))
                dr = ImageDraw.Draw(pil)
                for x in range(100, gw, 100):
                    dr.line([(x, 0), (x, gh)], fill=(60, 60, 60), width=1)
                    dr.text((x + 2, 2), str(x), fill=(255, 255, 255))
                for y in range(100, gh, 100):
                    dr.line([(0, y), (gw, y)], fill=(60, 60, 60), width=1)
                    dr.text((2, y + 2), str(y), fill=(255, 255, 255))
                bx = []
                for i, b in enumerate(boxes_now()):
                    dr.rectangle([b.x0, b.y0, b.x1, b.y1], outline=(0, 255, 255), width=2)
                    dr.text((b.x0, b.y0 - 12), f"b{i}", fill=(0, 255, 255))
                    bx.append({"i": i, "u": round((b.x0 + b.x1) / 2), "v": round((b.y0 + b.y1) / 2),
                               "w": round(b.x1 - b.x0), "h": round(b.y1 - b.y0),
                               "conf": round(float(b.score), 2)})  # fmt: skip
                snap = live.snapshot(r.ns())
                mobs = []
                for m in snap["mobs"][:12]:
                    p = project(m["cell"])
                    d = (
                        None
                        if snap["me"] is None
                        else max(
                            abs(m["cell"][0] - snap["me"][0]), abs(m["cell"][1] - snap["me"][1])
                        )
                    )
                    row = {**{k: m[k] for k in ("gid", "species", "cell", "moving", "hit_s_ago")},
                           "d": None if d is None else round(d, 1)}  # fmt: skip
                    if p is not None:
                        row["u"], row["v"] = round(p[0]), round(p[1])
                        col = (255, 220, 0) if m["job"] in TARGET_JOBS else (255, 0, 255)
                        dr.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=col, width=2)
                        dr.text((p[0] + 8, p[1] - 6), f"{m['species'][:2]}{m['gid'] % 1000}",
                                fill=col)  # fmt: skip
                    mobs.append(row)
                items = []
                for it in snap["items"]:
                    ox, oy = item_px_offset(it["sub"])
                    p = project((it["cell"][0] + ox, it["cell"][1] + oy))
                    row = dict(it)
                    if p is not None:
                        row["u"], row["v"] = round(p[0]), round(p[1])
                        dr.rectangle([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5],
                                     outline=(0, 255, 0), width=2)  # fmt: skip
                    items.append(row)
                dr.line(
                    [
                        (hf.GM_SPRITE_PX[0] - 8, hf.GM_SPRITE_PX[1]),
                        (hf.GM_SPRITE_PX[0] + 8, hf.GM_SPRITE_PX[1]),
                    ],
                    fill=(255, 0, 0),
                    width=2,
                )
                state["looks"] += 1
                png = LOOK_DIR / f"look-{state['looks']:03d}.jpg"
                pil.save(png, quality=85)
                mx, my, mw, mh = hf.MINIMAP_IMG
                mm = np.asarray(frame())[my : my + mh, mx : mx + mw, :3]
                ah = hf.minimap_heading(mm)
                left = None if state["deadline"] is None else round(state["deadline"]
                                                                    - time.monotonic())  # fmt: skip
                return {"png": str(png), "left_s": left, "me": snap["me"],
                        "heading_deg": None if ah is None else round(math.degrees(ah) % 360),
                        "boxes": bx, "mobs": mobs, "items": items, "deaths": snap["deaths"],
                        "bars": snap["bars"], "engagements": len(engagements)}  # fmt: skip

            handlers = {"look": do_look, "strike": do_attack, "walk": do_walk, "loot": do_loot}
            if SOCK.exists():
                SOCK.unlink()
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(str(SOCK))
            srv.listen(1)
            srv.settimeout(0.5)
            while True:
                if state["deadline"] is not None and time.monotonic() >= state["deadline"]:
                    state["ended"] = "time_box"
                    break
                if live.bars:
                    state["ended"] = f"hard_bar:{live.bars[0]}"
                    break
                try:
                    conn, _ = srv.accept()
                except TimeoutError:
                    continue
                with conn:
                    buf = b""
                    while not buf.endswith(b"\n"):
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buf += chunk
                    try:
                        q = json.loads(buf.decode() or "{}")
                        cmd = q.get("cmd")
                        if cmd == "end":
                            state["ended"] = "agent_end"
                            out: dict[str, Any] = {"ok": True}
                        elif cmd == "status":
                            out = {"session": sid, "engagements": len(engagements),
                                   "left_s": None if state["deadline"] is None
                                   else round(state["deadline"] - time.monotonic())}  # fmt: skip
                        elif cmd == "wait":
                            time.sleep(min(10.0, float(q.get("s", 1.0))))
                            out = {"ok": True}
                        elif cmd in handlers:
                            t_c = time.monotonic()
                            out = handlers[cmd](q)
                            out["cmd_ms"] = round((time.monotonic() - t_c) * 1000)
                            if cmd != "look":
                                ev({"kind": f"agent_{cmd}", **{k: q.get(k) for k in
                                                               ("u", "v", "gid", "fid", "cx",
                                                                "cy", "why", "fact")},
                                    "result": out})  # fmt: skip
                        else:
                            out = {"error": f"unknown command {cmd!r}"}
                    except Exception as exc:  # noqa: BLE001 -- answered, never silent
                        out = {"error": f"{type(exc).__name__}: {exc}"}
                    conn.sendall((json.dumps(out, default=str) + "\n").encode())
                if state["ended"]:
                    break
        except BaseException as exc:
            state["ended"] = state["ended"] or f"stopped:{type(exc).__name__}: {str(exc)[:200]}"
        finally:
            if srv is not None:
                srv.close()
                with contextlib.suppress(FileNotFoundError):
                    SOCK.unlink()
            halt.set()
            stop_rec.set()
            if rec.is_alive():
                rec.join(timeout=5)
            if sampler is not None:
                sampler.stop()
                with (log.dir / "boxes.jsonl").open("w") as fh:
                    for t_b, bs in sampler.frames:
                        fh.write(
                            json.dumps(
                                {
                                    "t": t_b,
                                    "boxes": [
                                        [b.x0, b.y0, b.x1, b.y1, float(b.score), b.cls] for b in bs
                                    ],
                                }
                            )
                            + "\n"
                        )
            # what the packets say about our engagements (offline labels, after play)
            for e in engagements:
                g = e.get("track")
                if g is not None and int(g) in live.deaths:
                    e["result"] = "dead"
            after: dict[str, Any] = {"skipped": state["ended"]}
            with contextlib.suppress(r.Stop):
                after = f0._brief(gm_state.ensure_fixed(agent, screen, why=f"{RULE}:after",
                                                        out_dir=log.dir / "gm_state",
                                                        profile="hunt-flow"))  # fmt: skip
                bench.close_chat(agent, screen)
            ev({"kind": "gm_state_after", **after})
            operator_hud.disable(hud_tok)
            det.close()
    events_f.close()
    clicks_f.close()
    events, anchor = record_session.write_packets(log.dir, t_first, r.ns())
    (log.dir / "engagements.json").write_text(json.dumps(engagements, default=str))
    summary = {"engagements": len(engagements), "looks": state["looks"],
               "live_bars": live.bars, "packet_assisted": True}  # fmt: skip
    log.finish(ended=state["ended"], packet_events=len(events), packet_anchor=anchor, **summary)
    print(json.dumps({"session": sid, "ended": state["ended"], **summary}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--minutes", type=float, default=10.0)
    s.add_argument("--round", default="R0")
    sub.add_parser("look")
    for name in ("strike", "walk", "loot"):
        p = sub.add_parser(name)
        p.add_argument("u", type=float, nargs="?")
        p.add_argument("v", type=float, nargs="?")
        p.add_argument(
            "--gid", type=int, help="a monster, by its packet gid (resolved at run time)"
        )
        p.add_argument("--fid", type=int, help="a floor item, by its packet floor id")
        p.add_argument("--cell", type=float, nargs=2, metavar=("X", "Y"))
        p.add_argument("--why")
        p.add_argument("--fact")
    w = sub.add_parser("wait")
    w.add_argument("s", type=float)
    sub.add_parser("status")
    sub.add_parser("end")
    a = ap.parse_args()
    if a.cmd == "serve":
        return serve(a)
    req: dict[str, Any] = {"cmd": a.cmd}
    for k in ("u", "v", "gid", "fid", "why", "fact", "s"):
        if getattr(a, k, None) is not None:
            req[k] = getattr(a, k)
    if getattr(a, "cell", None):
        req["cx"], req["cy"] = a.cell
    print(json.dumps(send(req), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
