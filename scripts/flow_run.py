#!/usr/bin/env python3
"""The /flows page's RUN button, the host side (Batt 2026-11-13: "I put the bot on the map, press
run on flows, and the bot plays by itself, with the flow that earns the most a round").

    flow_run.py serve        the helper loop (scripts/host/poring-lab-flowrun.service)
    flow_run.py status       print the status file
    flow_run.py command FLOW print the exact runner command a FLOW runs

WHAT IT RUNS: the proven runner (scripts/dungeon_hunt.py run), never a new executor. A flow is a
FIXED entry of FLOWS below: its whole command line lives here, in the repo. A request names a flow
by its id and says start or stop; nothing in a request becomes an argument.

THE CHANNEL: the backend writes ``settings/flowrun/request.json`` (POST /flows/run, behind
routes_settings.write_gate: a console browser on the LAN, never the lab host or the Windows host,
the CSRF token, rate-limited and audited) and reads ``status.json``, which this loop rewrites every
STATUS_EVERY_S (its heartbeat). ``settings/`` is the human-only store, mounted only into the backend
(CLAUDE.md, "The human-only settings store"); vision cannot write it.

A START runs, in order (as the night chain's run_pilot_v3.sh does):
1. refuse while another runner or the night chain runs (one input writer at a time, ADR-0002);
2. the vision worker up (``guarded_build.py worker:vision``) if it is not;
3. the detect server (``unit_detector.py serve-cmd``, its time box = the run's cap + 150 s), and
   its "listening" line;
4. the runner, in --player-mode (it types no line; it starts where the person left her, reads her
   stock from the hotbar, refuses a heavy bag or too little stock, ends when the Fly Wings fall to
   one and goes home on a Butterfly Wing if F8 holds one). Its own checks refuse every unsafe start
   (ASSIST, the interlock, her identity, her cell).
A STOP sends SIGINT to the runner's process group (a clean end, rc 130). Either way the detect
server is ended by PID when the runner exits, and the run's session goes into data/econ/lab.sqlite.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "settings" / "flowrun"
SCRATCH = Path("/dev/shm/poring-lab-tmp")
SERVE_LOG = SCRATCH / "poring-guarded-execdev-vision.log"
WORKER = "poring-lab-vision-worker-1"
PY = str(ROOT / ".venv" / "bin" / "python")
STATUS_EVERY_S = 2.0
POLL_S = 1.0
LISTEN_WAIT_S = 120.0
CAP_GRACE_S = 300.0  # the helper's own cap beyond the runner's --minutes
VERSION = 1

# The runner's fixed part, as the night chain ran it (docs/records/pilot-chain/run_pilot_v3.sh +
# pilot_rec2.sh's BASE) WITHOUT --clear-map (a GM line: --player-mode refuses it), --seed fixed.
FIXED = [
    "--char", "rogue", "--map", "xmas_dun02", "--strategy", "P2", "--search", "patrol",
    "--walk-trust", "--npc-guard", "--miss-cue", "--loot", "trim", "--seed", "20261105",
    "--box-strike", "--box-now", "--self-recheck", "--still-strike", "--engage-screen",
    "--reach-check", "--far-single", "--far-approach", "--explore", "--walk-pick", "--kill-gap",
    "--loot-first", "--walk-pick-step", "--quiet-scan", "--garm-fly", "--garm-confirm", "2",
    "--late-confirm", "--still-target", "--lead-press",
]  # fmt: skip


@dataclass(frozen=True)
class Flow:
    id: str
    title: str
    minutes: int
    flags: tuple[str, ...]
    why: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# rogue-xmas02.md 4DQ (2026-11-13): the Knife on arm B's fast loot JOINED THE BASE -- the highest
# common-item z/h with every bar passed (67,269); Batt chose it for the Run button, played until
# Stop or until the stock runs low, a 2-h cap.
FLOWS: dict[str, Flow] = {
    "xmas_dun02_rogue": Flow(
        "xmas_dun02_rogue",
        "xmas_dun02: the Rogue with Batt's Knife swap (the base of 4DQ), as a player",
        120,
        (
            "--value-target",
            "--hud",
            "--hud-fast",
            "0.2",
            "--loot-items",
            "xmas02fi5",
            "--loot-memory",
            "--bare-steal",
            "--bare-ready",
            "--steal-opener",
            "F4",
            "--steal-cue",
            "popup",
            "--swap-gap",
            "--player-mode",
        ),  # fmt: skip
        "rogue-xmas02.md 4DQ (the base) + --player-mode (Batt 2026-11-13: no GM lines)",
    ),
}


def command(flow: Flow, label: str) -> list[str]:
    """PURE: the runner's argv for ``flow`` (the label names its session)."""
    return ["nice", "-n", "10", "uv", "run", "--quiet", "python", "scripts/dungeon_hunt.py", "run",
            *FIXED, "--minutes", str(flow.minutes), "--label", label, *flow.flags]  # fmt: skip


def parse_request(text: str) -> dict[str, Any] | str:
    """PURE: a valid request ({"id", "action", "flow"}) or why it is not one."""
    try:
        req = json.loads(text)
    except ValueError:
        return "unparsable request"
    if not isinstance(req, dict):
        return "unparsable request"
    rid, action, flow = req.get("id"), req.get("action"), req.get("flow")
    if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", rid):
        return "bad request id"
    if action not in ("start", "stop"):
        return f"unknown action {action!r}"
    if action == "start" and flow not in FLOWS:
        return f"unknown flow {flow!r}"
    return {"id": rid, "action": action, "flow": flow}


def busy_reason(ps_lines: Sequence[str]) -> str | None:
    """PURE: why a new run must not start (another input writer of ours), from `ps -eo args`."""
    for ln in ps_lines:
        if "chain.py" in ln and "poring-lab-tmp/chain" in ln:
            return "the night chain is running (one input writer at a time)"
        if "dungeon_hunt.py run" in ln and "uv run" not in ln:
            return "another runner is playing (one input writer at a time)"
    return None


def tail(path: Path, n: int = 6) -> list[str]:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return [ln[:240] for ln in lines[-n:]]


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(data, sort_keys=True) + "\n")
    os.replace(tmp, path)


def ict(t: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() if t is None else t))


class Helper:
    def __init__(self, d: Path = DIR) -> None:
        self.dir = d
        self.state = "idle"
        self.detail = "waiting for the Run button"
        self.flow: str | None = None
        self.label: str | None = None
        self.request_id: str | None = None
        self.started: str | None = None
        self.ended: str | None = None
        self.rc: int | None = None
        self.runner: subprocess.Popen[bytes] | None = None
        self.server: subprocess.Popen[bytes] | None = None
        self.run_dir: Path | None = None
        self.t_start = 0.0
        self.cap_s = 0.0

    # -- status --
    def status(self) -> dict[str, Any]:
        log = None if self.run_dir is None else self.run_dir / "run.log"
        return {"v": VERSION, "state": self.state, "detail": self.detail, "flow": self.flow,
                "label": self.label, "request_id": self.request_id, "started": self.started,
                "ended": self.ended, "rc": self.rc, "t_wall": time.time(),
                "log_tail": [] if log is None else tail(log),
                "flows": {k: {"title": f.title, "minutes": f.minutes}
                          for k, f in FLOWS.items()}}  # fmt: skip

    def write_status(self) -> None:
        write_json(self.dir / "status.json", self.status())

    def note(self, **kw: Any) -> None:
        with open(self.dir / "runs.jsonl", "a") as fh:
            fh.write(json.dumps({"t": ict(), **kw}) + "\n")

    # -- requests --
    def take_request(self) -> dict[str, Any] | None:
        f = self.dir / "request.json"
        if not f.exists():
            return None
        try:
            text = f.read_text()
        finally:
            f.unlink(missing_ok=True)  # a request is consumed once, valid or not
        req = parse_request(text)
        if isinstance(req, str):
            self.note(event="request_refused", why=req)
            self.detail = f"a request was refused: {req}"
            return None
        return req

    def handle(self, req: Mapping[str, Any]) -> None:
        if req["action"] == "stop":
            self.stop(req["id"])
        elif self.runner is not None or self.state in ("starting", "running", "stopping"):
            self.detail = "a run is already going: press Stop first"
            self.note(event="start_refused", why="busy", request=req["id"])
        else:
            self.start(FLOWS[req["flow"]], req["id"])

    # -- a run --
    def start(self, flow: Flow, rid: str) -> None:
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
        why = busy_reason(ps.splitlines())
        if why is not None:
            self.state, self.detail, self.request_id = "refused", why, rid
            self.note(event="start_refused", why=why, request=rid)
            return
        self.state, self.flow, self.request_id = "starting", flow.id, rid
        self.started, self.ended, self.rc = ict(), None, None
        self.label = "flowrun-" + time.strftime("%m%d%H%M")
        self.run_dir = SCRATCH / self.label
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.cap_s = flow.minutes * 60 + CAP_GRACE_S
        self.note(event="start", flow=flow.id, label=self.label, request=rid)
        self.detail = "starting the vision worker"
        self.write_status()
        up = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", WORKER],
                            capture_output=True, text=True).stdout.strip()  # fmt: skip
        if up != "true":
            r = subprocess.run(["python3", "scripts/guarded_build.py", "worker:vision@60"],
                               cwd=ROOT, capture_output=True, text=True)  # fmt: skip
            if r.returncode != 0:
                return self.fail("the vision worker did not start", r.stdout[-300:])
        self.detail = "starting the detect server"
        self.write_status()
        cmd = subprocess.run([PY, "scripts/unit_detector.py", "serve-cmd", "--backend", "openvino",
                              "--seconds", str(int(self.cap_s + 150))], cwd=ROOT,
                             capture_output=True, text=True)  # fmt: skip
        if cmd.returncode != 0 or not cmd.stdout.strip():
            return self.fail("the detect server's command did not build", cmd.stderr[-300:])
        SERVE_LOG.unlink(missing_ok=True)  # only the NEW step's start line may match
        with open(self.run_dir / "serve.log", "wb") as fh:
            self.server = subprocess.Popen(
                ["bash", "-c", cmd.stdout.strip()],
                cwd=ROOT,
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        t0 = time.monotonic()
        while time.monotonic() - t0 < LISTEN_WAIT_S:
            time.sleep(1.0)
            text = SERVE_LOG.read_text(errors="replace") if SERVE_LOG.exists() else ""
            if '"listening"' in text and '"precision": "f32"' in text:
                break
            if "REFUSED" in (self.run_dir / "serve.log").read_text(errors="replace"):
                return self.fail("the detect server refused", tail(self.run_dir / "serve.log", 3))
        else:
            return self.fail("the detect server did not listen in time", [])
        self.detail = "the runner starts (its own checks first: ASSIST, the interlock, her cell)"
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(SCRATCH)}
        with open(self.run_dir / "run.log", "wb") as fh:
            self.runner = subprocess.Popen(command(flow, self.label), cwd=ROOT, env=env, stdout=fh,
                                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                           start_new_session=True)  # fmt: skip
        self.t_start = time.monotonic()
        self.state, self.detail = "running", "playing"
        self.write_status()

    def stop(self, rid: str) -> None:
        if self.runner is None or self.runner.poll() is not None:
            self.detail = "nothing is running"
            return
        self.state, self.detail, self.request_id = "stopping", "Stop pressed: ending cleanly", rid
        self.note(event="stop", label=self.label, request=rid)
        os.killpg(self.runner.pid, signal.SIGINT)

    def fail(self, why: str, info: Any) -> None:
        self.state, self.detail, self.ended = "failed", why, ict()
        self.note(event="failed", why=why, info=info, label=self.label)
        self.end_server()
        self.write_status()

    def end_server(self) -> None:
        """Our own detect server in the worker, ended by host PID (as the night chain does)."""
        out = subprocess.run(["docker", "top", WORKER], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            f = ln.split()
            ours = f[7:10] == ["python", "-m", "poring_vision.detect_server"]
            if len(f) > 8 and f[0] == "bot" and ours:
                subprocess.run(["kill", "-TERM", f[1]])
        if self.server is not None:
            try:
                self.server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(self.server.pid, signal.SIGTERM)
        self.server = None

    def tick(self) -> None:
        if self.runner is None:
            return
        rc = self.runner.poll()
        if rc is None and time.monotonic() - self.t_start > self.cap_s:
            self.note(event="cap", label=self.label)
            os.killpg(self.runner.pid, signal.SIGINT)
            return
        if rc is None:
            return
        self.rc, self.ended, self.runner = rc, ict(), None
        last = tail(self.run_dir / "run.log", 3) if self.run_dir else []
        refused = next((ln for ln in last if "refused" in ln), None)
        self.state = "ended" if rc in (0, 130) else "failed"
        self.detail = (refused or ("stopped (Stop)" if rc == 130 else
                                   "ended by itself (time box or stock)" if rc == 0
                                   else f"the runner ended rc {rc}"))  # fmt: skip
        self.note(event="end", label=self.label, rc=rc, detail=self.detail)
        self.end_server()
        self.record()
        self.write_status()

    def record(self) -> None:
        """The run's session into data/econ/lab.sqlite (ADR-0025), when it made one."""
        demo = Path("/dev/shm/poring-lab-demo")
        sess = sorted(demo.glob(f"*-{self.label}")) if self.label else []
        if sess:
            subprocess.run([PY, "scripts/econ_db.py", "update", str(sess[-1])], cwd=ROOT,
                           capture_output=True)  # fmt: skip

    def serve(self) -> int:
        self.dir.mkdir(parents=True, exist_ok=True)
        last = 0.0
        while True:
            req = self.take_request()
            if req is not None:
                self.handle(req)
            self.tick()
            if time.monotonic() - last >= STATUS_EVERY_S:
                self.write_status()
                last = time.monotonic()
            time.sleep(POLL_S)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    sub.add_parser("status")
    c = sub.add_parser("command")
    c.add_argument("flow", choices=sorted(FLOWS))
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        return Helper().serve()
    if a.cmd == "status":
        f = DIR / "status.json"
        print(f.read_text() if f.exists() else '{"state": "no helper"}')
        return 0
    print(" ".join(command(FLOWS[a.flow], "flowrun-LABEL")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
