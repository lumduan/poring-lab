"""agent_play (agent-demo@1, Batt 2026-10-17): the packet world's pure parts, and ADR-0007
Amendment D's line -- the bot never imports the agent's packet view."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

import agent_play as ap  # noqa: E402

S = 1_000_000_000


def ev(t: float, typ: str, **kw: object) -> dict[str, object]:
    return {"t_mono_ns": int(t * S), "type": typ, **kw}


def test_a_mob_walks_its_move_at_its_speed_and_stops_at_the_end() -> None:
    rec = {"x": 10, "y": 10, "x1": 14, "y1": 10, "t_move": 0, "speed": 200}
    assert ap.mob_cell_at(rec, int(0.4 * S)) == (12.0, 10.0)
    assert ap.mob_cell_at(rec, int(5 * S)) == (14.0, 10.0)
    assert ap.mob_cell_at({"x": 3, "y": 4}, 0) == (3.0, 4.0)


def test_the_live_world_tracks_mobs_us_items_deaths_and_the_hard_bars() -> None:
    w = ap.LiveWorld()
    w.feed([ev(1.0, "self_move", x0=100, y0=100, x1=103, y1=100),
            ev(1.1, "entity_appear", gid=7, job=1002, x=105, y=100, x1=None, y1=None, speed=400),
            ev(1.2, "entity_appear", gid=8, job=1018, x=120, y=100, x1=None, y1=None, speed=150),
            ev(1.3, "floor_item_appear", floor_id=55, x=104, y=101, sub_x=12,
               sub_y=3)])  # fmt: skip
    snap = w.snapshot(int(3 * S))
    assert snap["me"] == [103.0, 100.0]
    assert [m["species"] for m in snap["mobs"]] == ["Poring", "Creamy"]  # the nearest first
    assert snap["items"][0]["cell"] == [104, 101]
    assert ap.self_moving(w.me, int(1.2 * S)) and not ap.self_moving(w.me, int(3 * S))
    w.t0 = int(2 * S)
    w.feed([ev(2.5, "act", src_gid=ap.GM_GID, target_gid=7, damage=180),
            ev(2.6, "entity_vanish", gid=7, reason=1),
            ev(2.7, "act", src_gid=ap.GM_GID, target_gid=8, damage=170)])  # fmt: skip
    snap = w.snapshot(int(3 * S))
    assert [d["gid"] for d in snap["deaths"]] == [7]
    assert snap["bars"] == ["non_target_hit:1018"]
    w.feed([ev(2.4, "npc_contact")])  # older than the last event: ignored
    assert w.bars == ["non_target_hit:1018"]


def test_nearest_box_and_the_item_offset() -> None:
    a = SimpleNamespace(x0=100, y0=100, x1=140, y1=136)
    b = SimpleNamespace(x0=300, y0=100, x1=340, y1=136)
    assert ap.nearest_box([a, b], 125, 120, 40) is a
    assert ap.nearest_box([a, b], 220, 120, 40) is None
    assert ap.item_px_offset([8, 8]) == (0.0, 0.0)
    assert ap.item_px_offset(None) == (0.0, 0.0)


def test_the_bot_never_imports_the_agents_packet_view() -> None:
    """ADR-0007 Amendment D: only agent-demo sessions read packets during play."""
    out = subprocess.run(["git", "grep", "-l", "agent_play", "--", "scripts", "packages",
                          "services/vision", "services/backend/src"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split()  # fmt: skip
    assert set(out) <= {"scripts/agent_play.py"}, out
