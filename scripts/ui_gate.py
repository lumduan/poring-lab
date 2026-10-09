#!/usr/bin/env python3
"""THE UI GATE (Batt 2026-10-09 ~15:20, walk@17 item 6, MANDATORY): before ANY typing, every
harness checks the client's UI state from PIXELS and never presses Enter into an unknown state.

Why: on 2026-10-09 (demonstrations 3.29a) a walk click opened an NPC's dialog; every Enter the
harness typed afterwards went into it (5 "next" + 5 menu choices), and the next run started on top
of it. Typing is the path that presses Enter, so the gate sits in ro_agent.open_chat (every
chat_line / gm / say / where_fix line) and in bench.close_chat.

What is read, on two FRESH frames that must agree, with the cursor parked away from the windows:
* an NPC dialog / menu: talk@1's T2 reader (poring_env.npc_dialog; proven 168 / 168 on held-out
  RDP frames, 2026-10-09 15:49), templates in data/ui_anchors/npc_dialog/;
* the four windows with cut anchors (status, skills, inventory, equipment; ADR-0011,
  open_window@1): data/ui_anchors, each looked for within HOME_PX of where the client reopens it
  (ui_anchors.CAPTURE_ORIGINS: the client reopens a window where it last was, and the lab never
  drags them). A full-frame search costs ~4 s per frame, too slow for every typed line.

Only KNOWN steps close anything, each followed by the same two-frame check:
* an NPC dialog showing CLOSE and no menu: Enter (talk@1's drives: every Enter on CLOSE became the
  server's npc_close_click);
* one of the four windows: its own L2 chord (open_window@1's toggle).
Anything else STOPS (ro_agent.Stop), nothing typed, a frame saved for a person: a dialog showing
NEXT (Enter would advance an unknown script), a menu (a choice is an NPC interaction), an unreadable
or unstable state, missing templates, a path without templates (the T2 templates are RDP-cut).
Known gaps (stated, not hidden): windows without a cut anchor (the options window, a shop, a
trade) are not seen by this gate, nor one of the four dragged more than HOME_PX from its home.

    ui_gate.py check          one live check (read only: no key; the cursor is parked)
    ui_gate.py clear          ensure_clear once (may press the KNOWN steps; else stops)
    ui_gate.py prove-windows  the positive case for the windows: each of the four opened by its
                              chord, then the gate must see it and close it by the same chord
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402

WINDOWS4 = ("status", "skills", "inventory", "equipment")
PARK = ((1250, 380), (1250, 300))  # talk1's rest points: right of the dialog's default place
LOG = r.ROOT / "data" / "ro_agent" / "ui_gate.jsonl"
FAIL_DIR = Path("/dev/shm/poring-lab-tmp/ui-gate")
MAX_STEPS = 4  # known closing steps per check (a dialog's CLOSE + up to three windows)
SETTLE_S = 0.6
HOME_PX = 12  # a window's search box around its home (CAPTURE_ORIGINS), each side
WINDOW_CLIENT = "kro-20211103-prere"  # the lab client's L2 build (rule_run.WINDOW_CLIENT)

_cache: dict[str, Any] = {}


class UiUnknown(r.Stop):
    """The gate could not establish a known, clear state: nothing was typed."""


def _templates() -> Any:
    from poring_env import npc_dialog as nd

    if "nd" not in _cache:
        _cache["nd"] = nd.load_templates(r.ROOT / nd.TEMPLATE_DIR)
    return _cache["nd"]


def _registry() -> Any:
    from poring_env import ui_anchors as ua

    if "reg" not in _cache:
        _cache["reg"] = ua.default_registry(r.ROOT / "data" / "ui_anchors")
    return _cache["reg"]


def window_keys(window: str) -> list[str]:
    from poring_skills.resolve import load_l2

    return list(load_l2(WINDOW_CLIENT)["shortcut"]["window"][window]["keys"])


def decide(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """PURE: what to do from two observations ({"npc": NpcUiState-like summary, "windows": [...]}).
    -> {"do": "clear" | "enter_close" | "chord", "window"?} or {"do": "stop", "why": ...}."""
    na, nb = a["npc"], b["npc"]
    if not (na["ok"] and nb["ok"]):
        why = na["reason"] if not na["ok"] else nb["reason"]
        return {"do": "stop", "why": f"npc_unreadable:{why}"}
    if na["sig"] != nb["sig"] or sorted(a["windows"]) != sorted(b["windows"]):
        return {"do": "stop", "why": "unstable"}
    dialog, menu = na.get("dialog"), na.get("menu")
    if menu is not None:
        return {"do": "stop", "why": "npc_menu_open"}
    if dialog is not None:
        if dialog.get("button") == "close":
            return {"do": "enter_close"}
        return {"do": "stop", "why": f"npc_dialog_open:{dialog.get('button') or 'no_button'}"}
    if a["windows"]:
        return {"do": "chord", "window": sorted(a["windows"])[0]}
    return {"do": "clear"}


def _park(agent: Any, k: int) -> None:
    gx, gy, _, _ = r.game_region()
    pu, pv = PARK[k % 2]
    agent.move(gx + pu - 3, gy + pv - 3)
    time.sleep(0.05)
    agent.move(gx + pu, gy + pv)
    time.sleep(SETTLE_S)


def observe(agent: Any, screen: Any, after_ns: int | None, k: int,
            park: bool = True) -> tuple[dict[str, Any], Any]:  # fmt: skip
    from poring_env import npc_dialog as nd

    if park:
        _park(agent, k)
    frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), after_ns)[..., :3])
    st = nd.state(frame, _templates())
    summ = st.summary()
    summ["sig"] = repr(st.signature())
    return {"npc": summ, "windows": windows_at_home(frame)}, frame


def windows_at_home(frame: Any, reg: Any = None) -> list[str]:
    """Which of the four windows show within HOME_PX of their home (the registry's own match
    and threshold, on a small box instead of the whole frame)."""
    from poring_env import ui_anchors as ua

    reg = reg if reg is not None else _registry()
    gray = ua.to_gray(frame)
    h, w = gray.shape
    out = []
    for name in WINDOWS4:
        spec, tmpl = reg.windows[name], reg.templates.get(name)
        if tmpl is None:
            continue
        hx, hy = ua.CAPTURE_ORIGINS[name]
        tx, ty = hx + spec.template_offset[0], hy + spec.template_offset[1]
        th, tw = tmpl.shape
        x0, y0 = max(0, tx - HOME_PX), max(0, ty - HOME_PX)
        x1, y1 = min(w, tx + tw + HOME_PX), min(h, ty + th + HOME_PX)
        if x1 - x0 < tw or y1 - y0 < th:
            continue
        m = ua.match_template(gray[y0:y1, x0:x1], tmpl, reg.masks.get(name))
        if m is not None and m.distance <= spec.max_distance:
            out.append(name)
    return sorted(out)


def _log(rec: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _require_ready() -> None:
    import record_session

    backend = str(record_session.read_lock(r.ROOT / "state").backend)
    if backend != "rdp":
        raise UiUnknown(f"ui gate: the T2 templates are RDP-cut, the lock says {backend}: "
                        "nothing typed")  # fmt: skip
    missing = _templates().missing
    if missing:
        raise UiUnknown(f"ui gate: no NPC dialog templates ({','.join(missing)}; talk@1 cut): "
                        "nothing typed")  # fmt: skip
    if not all(w in _registry().templates for w in WINDOWS4):
        raise UiUnknown("ui gate: a window anchor is missing (data/ui_anchors): nothing typed")


def ensure_clear(agent: Any, screen: Any, *, why: str) -> dict[str, Any]:
    """Return once the client shows no NPC dialog / menu and none of the four windows, closing
    them by KNOWN steps only; else raise UiUnknown. Every check and step is logged."""
    _require_ready()
    t0 = r.ns()
    steps: list[dict[str, Any]] = []
    after: int | None = t0
    for k in range(MAX_STEPS + 1):
        a, _ = observe(agent, screen, after, k)  # the cursor parked once per round ...
        b, frame = observe(agent, screen, r.ns(), k, park=False)  # ... a later frame, same place
        d = decide(a, b)
        rec = {"t_ns": r.ns(), "why": why, "k": k, "decision": d, "npc": a["npc"],
               "windows": a["windows"]}  # fmt: skip
        _log(rec)
        if d["do"] == "clear":
            return {"clear": True, "steps": steps, "checks": k + 1,
                    "ms": round((r.ns() - t0) / 1e6)}  # fmt: skip
        if d["do"] == "stop" or k == MAX_STEPS:
            FAIL_DIR.mkdir(parents=True, exist_ok=True)
            shot = r.to_png(frame, FAIL_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}.png")
            reason = d.get("why", "too_many_steps")
            raise UiUnknown(f"ui gate ({why}): {reason}; nothing typed, left for a person "
                            f"(frame {shot})")  # fmt: skip
        r.activate_client(agent, screen)
        if d["do"] == "enter_close":
            agent.keys("Enter")  # the KNOWN close: the dialog shows CLOSE on two frames, no menu
            steps.append({"step": "enter_close", "t_ns": r.ns()})
        else:
            agent.chord(*window_keys(d["window"]))  # its own toggle (open_window@1)
            steps.append({"step": "chord", "window": d["window"], "t_ns": r.ns()})
        after = r.ns()
        time.sleep(SETTLE_S)
    raise AssertionError("unreachable")


def prove_windows(agent: Any, screen: Any) -> dict[str, Any]:
    """Each of the four windows opened by its own chord, seen by the gate (and by the full-frame
    locate, the registry's own search), then closed by ensure_clear. PASS: all four."""
    out: dict[str, Any] = {}
    first = ensure_clear(agent, screen, why="prove-windows:start")
    for w in WINDOWS4:
        r.activate_client(agent, screen)
        agent.chord(*window_keys(w))
        time.sleep(1.0)
        frame = np.ascontiguousarray(r.grab_after(screen, r.game_region(), r.ns())[..., :3])
        home = windows_at_home(frame)
        full = sorted(set(_registry().locate(frame)) & set(WINDOWS4))
        got = ensure_clear(agent, screen, why=f"prove-windows:{w}")
        out[w] = {"home": home, "full": full, "steps": got["steps"],
                  "pass": home == [w] and full == [w]
                  and [st.get("window") for st in got["steps"]] == [w]}  # fmt: skip
    out["start_steps"] = first["steps"]
    out["pass"] = all(out[w]["pass"] for w in WINDOWS4)
    return out


def main() -> int:
    cmd = sys.argv[1:]
    if cmd not in (["check"], ["clear"], ["prove-windows"]):
        print(__doc__)
        return 2
    _require_ready()
    with r.session("ui-gate-check") as (agent, screen):
        if cmd == ["check"]:
            a, _ = observe(agent, screen, r.ns(), 0)
            b, _ = observe(agent, screen, r.ns(), 1)
            print(json.dumps({"decision": decide(a, b), "a": a, "b": b}, indent=1))
        elif cmd == ["clear"]:
            print(json.dumps(ensure_clear(agent, screen, why="cli"), indent=1))
        else:
            res = prove_windows(agent, screen)
            print(json.dumps(res, indent=1))
            return 0 if res["pass"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
