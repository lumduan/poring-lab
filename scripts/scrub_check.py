#!/usr/bin/env python3
"""The sniffer's credential scrub, checked on the LIVE captures (ADR-0007; pcapng.LoginScrub).

    scrub_check.py --since EPOCH_S [--account gm]

After a sniffer rebuild + recreate, the GM logs in again (guarded_build's auto re-login). This
looks for that account's USER and PASSWORD bytes in every capture file written since --since. Two
positive controls (CLAUDE.md §2a's rule: a zero proves nothing unless the sensor can see the event):
the sniffer's own `login_accepted` event inside the window for that account (a login DID happen),
and the account's CHARACTER NAME in the files (unscrubbed traffic was captured).

It prints FOUND / NOT FOUND per label and counts of files, never a value (Batt 2026-10-09: "secrets
are never printed (the scrub check must report found / not found only)"). The needles reach the
search inside the backend container (the only place that mounts the captures volume, read-only)
on STDIN, never on a command line.
Exit 0: both controls seen and both secrets not found. 1: a secret found. 2: a control missing
(inconclusive).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = "poring-lab-backend-1"
# Runs INSIDE the backend container: reads {"since": s, "needles": {label: hex}} on stdin, prints
# only per-label booleans and file counts.
INNER = r"""
import json, os, sys
req = json.load(sys.stdin)
needles = {k: bytes.fromhex(v) for k, v in req["needles"].items()}
found = {k: False for k in needles}
files = 0
for n in sorted(os.listdir("/captures")):  # one flat directory: a listing, never a walk
    if not n.endswith((".pcapng", ".pcap")):
        continue
    p = os.path.join("/captures", n)
    try:
        if os.path.getmtime(p) < req["since"]:
            continue
        data = open(p, "rb").read()
    except OSError:
        continue
    files += 1
    for k, v in needles.items():
        if not found[k] and v in data:
            found[k] = True
print(json.dumps({"files": files, "found": found}))
"""


def env_values(keys: list[str]) -> dict[str, str]:
    vals: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        k, sep, v = line.partition("=")
        if sep and k.strip() in keys:
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    ap.add_argument("--since", type=float, required=True, help="epoch seconds (the recreate)")
    ap.add_argument("--account", choices=("gm", "agent"), default="gm")
    a = ap.parse_args()
    pre = {"gm": "RATHENA_GM", "agent": "RATHENA_AGENT"}[a.account]
    v = env_values([f"{pre}_USER", f"{pre}_PASSWORD", f"{pre}_CHAR"])
    if len(v) != 3 or not all(v.values()):
        print(json.dumps({"error": "account values missing in .env (not printed)"}))
        return 2
    needles = {"user": v[f"{pre}_USER"], "password": v[f"{pre}_PASSWORD"],
               "char_name_control": v[f"{pre}_CHAR"]}  # fmt: skip
    req = {"since": a.since, "needles": {k: s.encode().hex() for k, s in needles.items()}}
    out = subprocess.run(
        ["docker", "exec", "-i", BACKEND, "python3", "-c", INNER],
        input=json.dumps(req), capture_output=True, text=True, check=False,
    )  # fmt: skip
    if out.returncode != 0:
        print(json.dumps({"error": "the search failed", "rc": out.returncode}))
        return 2
    res = json.loads(out.stdout)
    f = res["found"]
    logins = login_events(a.since)

    def word(hit: bool) -> str:
        return "FOUND" if hit else "NOT FOUND"

    report = {"files": res["files"], "account": a.account, "user": word(f["user"]),
              "password": word(f["password"]), "control_char_name": word(f["char_name_control"]),
              "control_login_accepted_events": logins}  # fmt: skip
    print(json.dumps(report))
    if not f["char_name_control"] or not logins:
        return 2
    return 1 if (f["user"] or f["password"]) else 0


def login_events(since_s: float) -> int:
    """How many `login_accepted` events the sniffer emitted since ``since_s`` (its own events,
    record_session's window; host monotonic clock), any account: the window held a login."""
    import time

    sys.path.insert(0, str(ROOT / "scripts"))
    import record_session
    import ro_agent as r

    t1 = r.ns()
    t0 = t1 - int((time.time() - since_s) * 1e9)
    out = Path("/dev/shm/poring-lab-tmp/scrub-check")  # reused, never deleted (no rm under /dev/shm)
    out.mkdir(parents=True, exist_ok=True)
    events, _ = record_session.write_packets(out, t0, t1)
    return sum(1 for e in events if e.get("type") == "login_accepted")


if __name__ == "__main__":
    sys.exit(main())
