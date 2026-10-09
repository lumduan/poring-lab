#!/usr/bin/env python3
"""The TYPING GUARD (Batt 2026-10-09, ADR-0020 #10): every chat line the agent types passes here
(`ro_agent.chat_line`, `ro_agent.say`). It REFUSES; it never waits a line out and never inserts
another line to make one pass.

Batt (2026-10-09 ~12:15): "Players type /where once and are done; they don't interleave filler
commands." The rules, from L2 `chat` (the measured fact and the policy):
- **No filler:** a line sent only to reset the client's repeat count (`/ex`, the only such line our
  code ever typed) is refused outright.
- **No 3rd identical line in a row** of a kind (`policy.refuse_identical_in_a_row`). The client
  itself accepts 3 and silently drops the 4th slash command (`repeat`, measured). The kinds count
  apart: a slash command does not reset the chat count.
- **The minimum interval:** a line within `min_line_interval_s` of the previous one is refused.
- **/where once per need:**
  - a /where within `where_retry_s` of the previous one is refused (a quick retype is not what a
    player does);
  - a /where over the current run's budget is refused;
  - every /where typed is logged with its reason.
- **Every refusal is logged** in `data/ro_agent/chat_guard.jsonl` with its rule. Only slash and GM
  (`@`) lines are logged with their text; free chat is logged as its kind only.
- `ChatRefused` is raised. With `on_refuse="skip"`, the line is simply not typed and the caller is
  told (False). That is for an idempotent GM command, whose repeat would be dropped anyway.

**A RUN** (`start_run`) sets the /where budget and resets its count. Without one, the L2 default
budget applies to the host's default run.

**The state is per HOST:** `/dev/shm/poring-lab-tmp/chat-guard.json`, under a flock. Several
processes type through the one client in turn. An unreadable state file starts fresh with a
warning.

    chat_guard.py status | where | start-run --id ID [--budget N]
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = Path("/dev/shm/poring-lab-tmp/chat-guard.json")
LOG = ROOT / "data" / "ro_agent" / "chat_guard.jsonl"
L2_CLIENT = "kro-20211103-prere"
FILLER = frozenset({"/ex"})  # lines our code typed only to reset the repeat count (where@2)
FALLBACK_POLICY = {"refuse_identical_in_a_row": 3, "where_retry_s": 60,
                   "where_budget_per_run": 12, "min_line_interval_s": 0.5}  # fmt: skip


class ChatRefused(RuntimeError):
    """The guard refused this line; ``rule`` names why."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"chat guard ({rule}): {message}")
        self.rule = rule


def policy() -> dict[str, Any]:
    """L2 `chat.policy` (the measured values if L2 cannot be read here: never off)."""
    try:
        sys.path.insert(0, str(ROOT / "packages" / "poring_skills" / "src"))
        from poring_skills.resolve import load_l2

        return {**FALLBACK_POLICY, **load_l2(L2_CLIENT)["chat"]["policy"]}
    except Exception:  # noqa: BLE001 -- the guard must never be off
        return dict(FALLBACK_POLICY)


def kind_of(text: str) -> str:
    return "slash" if text.startswith("/") else "chat"


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            if not isinstance(state, dict):
                raise ValueError("not an object")
        except (OSError, ValueError) as exc:
            print(f"chat_guard: state unreadable ({type(exc).__name__}): starting fresh",
                  file=sys.stderr)  # fmt: skip
            state = {}
        yield state
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(path)


def _log(log: Path, row: dict[str, Any]) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps({"t_wall": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **row}) + "\n")


def _shown(text: str) -> str:
    return text if text.startswith(("/", "@")) else "<chat>"


def start_run(run_id: str, budget: int | None = None, *, state_path: Path = STATE,
              log: Path = LOG) -> None:  # fmt: skip
    """A new run: its own /where budget, its count at zero."""
    b = int(policy()["where_budget_per_run"] if budget is None else budget)
    if b < 0:
        raise ValueError("budget must be >= 0")
    with _locked(state_path) as state:
        state["run"] = {"id": run_id, "budget": b, "where": 0}
    _log(log, {"event": "run_start", "run": run_id, "where_budget": b})


def before_typing(text: str, *, reason: str | None = None, on_refuse: str = "raise",
                  state_path: Path = STATE, log: Path = LOG, pol: dict[str, Any] | None = None,
                  clock: Callable[[], float] = time.monotonic) -> bool:  # fmt: skip
    """Call right before typing ``text``. True: type it now. A refusal is logged, then raised
    (ChatRefused) or, with ``on_refuse="skip"``, returned as False."""
    if on_refuse not in ("raise", "skip"):
        raise ValueError(f"on_refuse: {on_refuse!r}")
    p = policy() if pol is None else pol
    kind, now = kind_of(text), clock()
    is_where = text.strip() == "/where"
    refusal: tuple[str, str] | None = None
    with _locked(state_path) as state:
        last = state.get(kind) or {}
        n = int(last.get("count", 0)) + 1 if last.get("text") == text else 1
        run = state.get("run") or {"id": "default", "budget": int(p["where_budget_per_run"]),
                                   "where": 0}  # fmt: skip
        last_t, last_where = state.get("last_t"), state.get("last_where_t")
        gap = now - last_t if isinstance(last_t, (int, float)) else None
        where_gap = now - last_where if isinstance(last_where, (int, float)) else None
        if text.strip() in FILLER:
            refusal = ("filler", f"{text!r} is only ever a separator: never type a line to reset "
                                 "the client's repeat count (Batt 2026-10-09)")  # fmt: skip
        elif n >= int(p["refuse_identical_in_a_row"]):
            refusal = ("repeat", f"{text!r} would be identical {kind} line #{n} in a row")
        elif gap is not None and 0 <= gap < float(p["min_line_interval_s"]):
            refusal = ("interval", f"{gap:.2f} s after the previous line "
                                   f"(min {p['min_line_interval_s']} s)")  # fmt: skip
        elif is_where and where_gap is not None and 0 <= where_gap < float(p["where_retry_s"]):
            refusal = ("where_retry", f"/where {where_gap:.1f} s after the previous one (once "
                                      f"per need; retry after {p['where_retry_s']} s)")  # fmt: skip
        elif is_where and int(run["where"]) >= int(run["budget"]):
            refusal = ("where_budget", f"the run {run['id']!r} used its /where budget "
                                       f"({run['budget']})")  # fmt: skip
        if refusal is None:
            state[kind] = {"text": text, "count": n}
            state["last_t"] = now
            if is_where:
                run["where"] = int(run["where"]) + 1
                state["run"] = run
                state["last_where_t"] = now
    if refusal is not None:
        _log(log, {"event": "refused", "rule": refusal[0], "line": _shown(text),
                   "reason": reason, "argv0": Path(sys.argv[0]).name})  # fmt: skip
        if on_refuse == "skip":
            return False
        raise ChatRefused(*refusal)
    if is_where:
        _log(log, {"event": "where", "run": run["id"], "n": run["where"], "budget": run["budget"],
                   "reason": reason or "unspecified", "argv0": Path(sys.argv[0]).name})  # fmt: skip
    return True


def summary(log: Path = LOG, run_id: str | None = None) -> dict[str, Any]:
    """The /where count and reasons and the refusals by rule (for one run, or all)."""
    rows = []
    if log.exists():
        for line in log.read_text().splitlines():
            with contextlib.suppress(ValueError):
                rows.append(json.loads(line))
    where = [r for r in rows if r.get("event") == "where"
             and (run_id is None or r.get("run") == run_id)]  # fmt: skip
    refused = [r for r in rows if r.get("event") == "refused"]
    reasons: dict[str, int] = {}
    for r in where:
        reasons[str(r.get("reason"))] = reasons.get(str(r.get("reason")), 0) + 1
    rules: dict[str, int] = {}
    for r in refused:
        rules[str(r.get("rule"))] = rules.get(str(r.get("rule")), 0) + 1
    return {"where": len(where), "where_reasons": reasons, "refused": rules}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("cmd", choices=("status", "where", "start-run"))
    ap.add_argument("--id", default=None)
    ap.add_argument("--budget", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "start-run":
        if not a.id:
            raise SystemExit("start-run needs --id")
        start_run(a.id, a.budget)
    elif a.cmd == "status":
        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        print(json.dumps({"policy": policy(), **state}))
    else:
        print(json.dumps(summary(run_id=a.id)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
