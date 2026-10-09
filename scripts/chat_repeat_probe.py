#!/usr/bin/env python3
"""Measure the client's REPEAT-PHRASE refusal live (Batt 2026-10-09, ADR-0020 #10: "first test it
(type /where 6+ times in a row, nothing in between) and record the real behaviour in L2 knowledge").

    chat_repeat_probe.py same --n 7       /where n times in a row, nothing between (after an @heal)
    chat_repeat_probe.py sep  --n 5       "/ex" then "/where", n times (where@2's pattern)

After every typed line the chat's NEWEST line is classified from pixels (where_fix's colours):
`yellow` = a /where answer (its X, Y parsed when it parses), `red` = the client's refusal line,
`cyan` = the /ex answer, `none` = no new line. Each chat-area crop is saved under
/dev/shm/poring-lab-tmp/chat-repeat/ so a person can check the reading. Typing through the chat
input, ASSIST, deliberately PAST the typing guard (scripts/chat_guard.py) that
enforces what it measured; no click, no packets.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ro_agent as r  # noqa: E402
import where_fix as wf  # noqa: E402

OUT = Path("/dev/shm/poring-lab-tmp/chat-repeat")


def newest_kind(before: Any, area: Any, templates: dict[str, Any]) -> dict[str, Any]:
    """The newest chat line's colour, if the area changed at all."""
    changed = int((np.abs(area.astype(int) - before.astype(int)).sum(-1) > 60).sum())
    if changed < 20:
        return {"kind": "none", "changed_px": changed}
    yellow = np.nonzero(wf.text_mask(area).sum(1))[0]
    a = area[..., :3].astype(int)
    b, g, red = a[..., 0], a[..., 1], a[..., 2]
    rows = {"red": np.nonzero(((red > 200) & (g < 90) & (b < 90)).sum(1) >= 3)[0],
            "cyan": np.nonzero(((g > 200) & (b > 200) & (red < 90)).sum(1) >= 3)[0],
            "yellow": yellow}  # fmt: skip
    last = {k: int(v[-1]) for k, v in rows.items() if len(v)}
    if not last:
        return {"kind": "other", "changed_px": changed}
    kind = max(last, key=lambda k: last[k])
    out: dict[str, Any] = {"kind": kind, "changed_px": changed}
    if kind == "yellow":
        out["xy"] = wf.parse_v2(area, templates)
    return out


def chat_mode(agent: Any, screen: Any, n: int, gap_s: float) -> int:
    """The POST-REFUSAL chat state (Batt 2026-10-09: "make open_chat recognise and recover from
    the post-refusal chat state"): one GM line typed n times in a row past the guard. After each:
    the chat_open signature's distance, a screenshot of the chat window + input, then whether
    open_chat itself still works."""
    gx, gy, _, _ = r.game_region()
    rows = []
    for k in range(n):
        r.open_chat(agent, screen)
        agent.type_text("@heal\n")
        time.sleep(1.2)
        dist = r.distance(screen, "chat_open")
        r.to_png(screen.grab(gx, gy + 530, 680, 190)[1], OUT / f"chat-{k:02d}.png")
        rows.append({"k": k, "chat_open_distance": round(float(dist), 2),
                     "chat_open": bool(dist <= r.SIG_MATCH)})  # fmt: skip
        print(json.dumps(rows[-1]), flush=True)
        time.sleep(gap_s)
    try:
        r.open_chat(agent, screen)
        after = "open_chat ok"
    except r.Stop as exc:
        after = f"open_chat Stop: {exc}"
    r.to_png(screen.grab(gx, gy + 530, 680, 190)[1], OUT / "chat-after.png")
    print(json.dumps({"mode": "chat", "n": n, "after": after}), flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("mode", choices=("same", "sep", "chat"))
    ap.add_argument("--n", type=int, default=7)
    ap.add_argument("--gap-s", type=float, default=1.5)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    templates = wf.load_templates(wf.TEMPLATES_V2)
    rows = []
    with r.session("rule:chat-repeat-probe") as (agent, screen):
        r.activate_client(agent, screen)
        r.gm(agent, screen, "@heal")  # a different line first: whatever was typed before is not
        time.sleep(a.gap_s)  #           what the probe repeats
        if a.mode == "chat":
            return chat_mode(agent, screen, a.n, a.gap_s)
        for k in range(a.n):
            lines = ["/ex", "/where"] if a.mode == "sep" else ["/where"]
            for line in lines:
                before = wf.stable_area(screen)
                # the probe MEASURES the limit, so it must be able to exceed it: it types past the
                # typing guard (ro_agent.chat_line would refuse the 4th identical line)
                r.open_chat(agent, screen)
                agent.type_text(line + "\n")
                time.sleep(wf.SETTLE_S)
                area = wf.stable_area(screen)
                got = newest_kind(before, area, templates)
                stem = f"{a.mode}-{k:02d}-{line.strip('/')}"
                r.to_png(area, OUT / f"{stem}.png")
                rows.append({"k": k, "line": line, **got,
                             "t_wall": time.strftime("%H:%M:%S")})  # fmt: skip
                print(json.dumps(rows[-1], default=str), flush=True)
                time.sleep(a.gap_s)
        r.to_png(screen.full(), OUT / f"{a.mode}-final.png")
    answered = sum(1 for x in rows if x["line"] == "/where" and x["kind"] == "yellow")
    refused = sum(1 for x in rows if x["line"] == "/where" and x["kind"] == "red")
    seq = [x["kind"] for x in rows if x["line"] == "/where"]
    print(json.dumps({"mode": a.mode, "n": a.n, "where_answered": answered,
                      "where_refused": refused, "sequence": seq}), flush=True)  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
