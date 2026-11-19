#!/usr/bin/env python3
"""poring-lab's setup wizard: a student runs `./setup.sh`, which runs this (Batt, 2026-11-17).

    ./setup.sh                 the screens below, resumable (.setup/progress.json)
    ./setup.sh --check         read-only status: pre-flight, .env (secrets hidden), Windows and
                               Sunshine, the services, the pairing. Safe on a running lab host.
    ./setup.sh --check --no-exec   the same without the one probe that runs inside a container
    ./setup.sh --dry-run       every step it would run, in order; nothing runs or is written
    ./setup.sh --restart       forget the saved progress (never .env) and start at screen 0

The screens: 0 pre-flight and the host profile, 1 this server's address, 2 the console port,
3 the Windows PC and Sunshine, 4 review and .env, 5 the install (docs/setup/new-lab-host.md
section 6, every step through scripts/guarded_build.py), 6 the Sunshine pairing, 7 the stream test,
8 the summary. Every screen offers Back and Quit; Ctrl+C saves and stops; a re-run resumes.

The decisions, checks and commands are in setup_core.py (plain, tested). This file only draws
and asks; it imports rich only for the interactive screens (--check and --dry-run are plain
text, so they work before `uv sync`). Before it: docs/setup/sunshine-windows.md on the PC.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_core as core  # noqa: E402

SCREENS = (
    "preflight", "server", "port", "windows", "storage", "review", "install", "pair", "stream",
    "done",
)  # fmt: skip
TITLES = {
    "preflight": "Pre-flight checks and the host profile",
    "server": "This server's address",
    "port": "The console port",
    "windows": "The Windows PC and Sunshine",
    "storage": "Where long-term files go",
    "review": "Review, then write .env",
    "install": "Install: build and start every service",
    "pair": "Pair with Sunshine",
    "stream": "The stream test",
    "done": "Done",
}
GUIDE = "docs/setup/sunshine-windows.md"


class Back(Exception):
    """The student chose Back."""


class Quit(Exception):
    """The student chose Quit (progress is saved; ./setup.sh resumes)."""


# --- plain modes (no rich) ------------------------------------------------------------------------


def plain_check(no_exec: bool) -> int:
    rep = core.run_check(core.run_process, core.REPO, exec_ok=not no_exec)
    print(core.format_check(rep))
    failed = [c for c in [*rep.preflight, *rep.status] if c.status == "fail"]
    return 1 if failed else 0


def guessed_answers(progress: dict[str, Any]) -> core.Answers:
    """--dry-run's answers: the saved ones, else .env's, else the detected defaults."""
    env = core.read_env(core.REPO / ".env")
    a = core.Answers.from_dict(progress.get("answers", {}))
    if not a.server_ip:
        a.server_ip = env.get("HOST_LAN_IP", "").strip() or (
            core.default_route_ip(core.run_process) or "<SERVER_IP>"
        )
    if not a.console_port:
        text = env.get("CONSOLE_PORT", "").strip()
        a.console_port = int(text) if text.isdigit() else core.DEFAULT_CONSOLE_PORT
    a.win_ip = a.win_ip or env.get("WIN_HOST", "").strip() or "<WIN_PC_IP>"
    a.profile = (
        a.profile
        or env.get("LAB_HOST_PROFILE", "").strip()
        or core.default_profile(core.detect_gpu())
    )
    return a


def plain_dry_run(progress: dict[str, Any]) -> int:
    a = guessed_answers(progress)
    if a.project:
        os.environ["COMPOSE_PROJECT_NAME"] = a.project
    env = core.read_env(core.REPO / ".env")
    print("DRY RUN: nothing below runs; values from the saved progress, .env or detection.")
    # ADR-0026: the wizard refuses a name another folder's containers use and asks for one; the
    # plan must not show (or check against) THAT copy's containers
    taken = core.check_project(core.run_process, core.REPO)
    if taken.status != "ok":
        free = core.free_project_name(core.run_process, core.project())
        print(f"  NOTE: {taken.detail}: the wizard will ask for another name; this plan uses "
              f"'{free}'.")  # fmt: skip
        a.project = free
        os.environ["COMPOSE_PROJECT_NAME"] = free
    _, nets = core.check_subnets(core.run_process, env)
    if nets and not a.nets:
        a.nets = nets
        print(f"  NOTE: the default subnets are taken: this plan uses {', '.join(nets.values())}.")
    if not a.server_ip.startswith("<"):
        moves = core.port_moves(a.server_ip, env, core.our_ports(core.run_process))
        for key, (_old, new) in moves.items():
            if new:
                a.ports.setdefault(key, new)
        if moves:
            shown = ", ".join(f"{k} {old}->{new or '?'}" for k, (old, new) in moves.items())
            print(f"  NOTE: ports another program holds; the wizard proposes: {shown}")
        held = core.our_ports(core.run_process)
        if not core.port_verdict(a.server_ip, a.console_port, held=held)[0]:
            print(f"  NOTE: the console port {a.console_port} is in use: the wizard asks for "
                  "another.")  # fmt: skip
    print(
        f"  server {a.server_ip}, console {core.console_url(a.server_ip, a.console_port)}, "
        f"Windows PC {a.win_ip}, profile {a.profile}, vision image {a.build_vision}"
    )
    for n, line in enumerate(
        core.dry_run_lines(
            core.REPO, a, env, gid=core.render_gid(), home=Path.home(), runner=core.run_process
        ),
        1,
    ):
        print(f"{n:>3}. {line}")
    return 0


# --- the interactive screens (rich) ---------------------------------------------------------------


def esc(text: object) -> str:
    """Rich markup off for a dynamic text (a log line, a fix, an address): `[Login]` stays text."""
    from rich.markup import escape

    return escape(str(text))


class UI:
    """Thin drawing helpers over rich."""

    def __init__(self) -> None:
        from rich.console import Console

        self.c = Console(highlight=False)

    def screen(self, index: int, name: str) -> None:
        from rich.rule import Rule

        self.c.print()
        self.c.print(Rule(f"[bold]poring-lab setup[/]  ·  {index}/8  ·  {TITLES[name]}"))

    def p(self, text: str = "", style: str = "") -> None:
        self.c.print(text, style=style or None)

    def ok(self, text: str) -> None:
        self.c.print(f"[green]✔[/] {esc(text)}")

    def warn(self, text: str) -> None:
        self.c.print(f"[yellow]![/] {esc(text)}")

    def err(self, text: str) -> None:
        self.c.print(f"[red]✘[/] {esc(text)}")

    def fixes(self, title: str, items: Sequence[str]) -> None:
        """`title` may carry markup; every item is plain text."""
        if title:
            self.c.print(f"[bold]{title}[/]")
        for n, item in enumerate(items, 1):
            self.c.print(f"  {n}. {esc(item)}")

    def read(self, prompt: str) -> str:
        return self.c.input(f"[bold cyan]{esc(prompt)}[/] ").strip()

    def menu(
        self, options: Sequence[tuple[str, str]], *, back: bool = True, default: str | None = None
    ) -> str:
        """Numbered choices plus [b] Back and [q] Quit; returns the chosen key."""
        from rich.markup import escape

        keys = {k for k, _ in options}
        for key, label in options:
            mark = "  (Enter)" if key == default else ""
            self.c.print(f"  [bold]{escape(f'[{key}]')}[/] {escape(label)}{mark}")
        extra = [f"[bold]{escape('[q]')}[/] Quit (resume later with ./setup.sh)"]
        if back:
            extra.insert(0, f"[bold]{escape('[b]')}[/] Back")
        self.c.print("  " + "   ".join(extra))
        while True:
            got = self.read(">").lower()
            if not got and default is not None:
                return default
            if got == "q":
                raise Quit
            if got == "b" and back:
                raise Back
            if got in keys:
                return got
            self.err("choose one of the keys in brackets")

    def ask(self, prompt: str, default: str = "") -> str:
        """Free text; 'b' = Back, 'q' = Quit, Enter = the default."""
        hint = f" [{default}]" if default else ""
        got = self.read(f"{prompt}{hint} (b = Back, q = Quit):")
        if got.lower() == "q":
            raise Quit
        if got.lower() == "b":
            raise Back
        return got or default

    def checks(self, checks: Sequence[core.Check]) -> None:
        from rich.table import Table

        table = Table(show_header=True, header_style="bold", expand=True)
        table.add_column("", width=4)
        table.add_column("Check", ratio=1)
        table.add_column("Result", ratio=3)
        mark = {
            "ok": "[green]OK[/]",
            "warn": "[yellow]WARN[/]",
            "fail": "[red]FAIL[/]",
            "info": "[blue]INFO[/]",
        }
        for c in checks:
            table.add_row(mark[c.status], esc(c.title), esc(c.detail))
        self.c.print(table)
        for c in checks:
            if c.fix and c.status in ("warn", "fail"):
                self.c.print(f"[bold]{esc(c.title)}[/] -> {esc(c.fix)}")

    def rows(
        self, rows: Sequence[tuple[str, str]], title: str = "", *, markup: bool = False
    ) -> None:
        """A two-column table; values are plain text unless `markup` (then escape the dynamic
        parts yourself)."""
        from rich.table import Table

        table = Table(show_header=False, title=esc(title) if title else None, expand=True)
        table.add_column(style="bold", ratio=1)
        table.add_column(ratio=2)
        for key, value in rows:
            table.add_row(esc(key), value if markup else esc(value))
        self.c.print(table)

    def pin(self, pin: str) -> None:
        from rich.align import Align
        from rich.panel import Panel
        from rich.text import Text

        big = Text("  ".join(pin), style="bold white on blue", justify="center")
        self.c.print(Panel(Align.center(big), title="PIN", padding=(1, 8), expand=False))

    def run(
        self, label: str, cmd: Sequence[str], *, log: Path, timeout: float | None
    ) -> core.Result:
        """One command with a live status line and its elapsed time; output only to `log`."""
        with self.c.status(f"{label}  0:00") as status:

            def tick(elapsed: float) -> None:
                m, s = divmod(int(elapsed), 60)
                status.update(f"{label}  {m}:{s:02d}   (log: {log})")

            return core.run_process(cmd, timeout=timeout, log=log, tick=tick)

    def tail(self, text: str, lines: int = 15) -> None:
        from rich.panel import Panel
        from rich.text import Text

        last = "\n".join(text.rstrip().splitlines()[-lines:])
        self.c.print(Panel(Text(last or "(no output)"), title="the last lines", border_style="red"))


def fmt_s(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


class Wizard:
    def __init__(self, ui: UI, progress: dict[str, Any]) -> None:
        self.ui = ui
        self.progress = progress
        self.a = core.Answers.from_dict(progress.get("answers", {}))
        self.gpu: core.Gpu | None = None
        self.addrs: list[core.Addr] = []
        if self.a.project:  # ADR-0026: every step this run starts uses this copy's own name
            os.environ["COMPOSE_PROJECT_NAME"] = self.a.project

    # -- bookkeeping --

    def save(self) -> None:
        self.progress["answers"] = asdict(self.a)
        core.save_progress(self.progress)

    def steps_state(self) -> dict[str, Any]:
        steps: dict[str, Any] = self.progress.setdefault("steps", {})
        return steps

    def env(self) -> dict[str, str]:
        return core.read_env(core.REPO / ".env")

    # -- the loop --

    def run(self) -> int:
        start = self.progress.get("screen", SCREENS[0])
        i = SCREENS.index(start) if start in SCREENS else 0
        if self.progress and i > 0:
            self.ui.p(f"Saved progress found: next is screen {i}, {TITLES[SCREENS[i]]}.")
            got = self.ui.menu(
                [
                    ("1", "Resume there"),
                    (
                        "2",
                        "Start at screen 0 (keeps .env; "
                        "finished install steps are checked, not redone)",
                    ),
                ],
                back=False,
                default="1",
            )
            if got == "2":
                i = 0
        while i < len(SCREENS):
            name = SCREENS[i]
            self.progress["screen"] = name
            self.save()
            try:
                self.ui.screen(i, name)
                getattr(self, f"s_{name}")()
                i += 1
            except Back:
                i = max(0, i - 1)
        self.progress["screen"] = "done"
        self.progress["completed"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        return 0

    # -- 0 --

    def s_preflight(self) -> None:
        ui = self.ui
        while True:
            with ui.c.status("Checking this machine (read-only)..."):
                checks, self.gpu = core.preflight(
                    core.run_process, build_vision=self.a.build_vision
                )
            ui.checks(checks)
            stops = core.blocking(checks)
            if any(c.key == "project" for c in stops):
                self.choose_project()
                continue
            if stops:
                ui.err("The wizard cannot go on until the FAIL lines above are fixed.")
                ui.menu([("r", "Check again")], back=False, default="r")
                continue
            if ui.menu([("1", "Continue"), ("r", "Check again")], back=False, default="1") == "1":
                break
        _, nets = core.check_subnets(core.run_process, core.env_baseline(core.REPO))
        self.a.nets = nets  # ADR-0026: a taken pinned /24 -> the first free pair (shown above)
        self.choose_profile()

    def choose_project(self) -> None:
        """Batt 2026-11-17: the name is another folder's -> this copy takes another (ADR-0026)."""
        ui = self.ui
        base = core.project()
        free = core.free_project_name(core.run_process, base)
        ui.p(f"The Docker name [bold]{base}[/] belongs to another poring-lab copy on this host. "
             "This copy needs its own (COMPOSE_PROJECT_NAME): its containers, networks, volumes "
             "and images all start with it; the other copy is never touched.")  # fmt: skip
        while True:
            got = ui.menu([("1", f"Use {free}"), ("t", "Type a name")], back=False, default="1")
            name = free if got == "1" else ui.ask("The name (lowercase letters, digits, - and _)")
            if not core.lab_env.PROJECT_RE.match(name):
                ui.err(f"{name!r}: lowercase letters, digits, - and _ only, starting with a letter "
                       "or digit")  # fmt: skip
                continue
            check = core.check_project(core.run_process, core.REPO, name)
            if check.status != "ok":
                ui.err(check.detail)
                continue
            self.a.project = name
            os.environ["COMPOSE_PROJECT_NAME"] = name
            self.save()
            return

    def choose_profile(self) -> None:
        """ADR-0022 Amendment 2026-11-17 (Batt: "detect the GPU and recommend it; no GPU -> the
        CPU"): the recommendation from what a container cannot bring (gpu_ready), the person
        decides; shared-nvidia only behind its warning."""
        ui = self.ui
        assert self.gpu is not None
        rec = core.gpu_recommendation(self.gpu, core.run_process)
        ui.p()
        ui.p(
            f"[bold]The host profile[/] (LAB_HOST_PROFILE; manual section 5). Found: "
            f"{esc(rec.summary())}."
        )
        if rec.fixes:
            ui.fixes(
                "[yellow]To use this GPU, fix on the host (then re-run ./setup.sh):[/]", rec.fixes
            )
        for note in rec.notes:
            ui.p(f"Note: {esc(note)}")
        others = [
            x
            for x in ("dedicated-nvidia", "dedicated-intel", "dedicated-amd", "dedicated-cpu")
            if x != rec.profile
        ]
        options = [("1", f"{rec.profile}  (recommended)")]
        options += [(str(n), name) for n, name in enumerate(others, 2)]
        options.append(
            (
                "s",
                "shared-nvidia  (ONLY a host shared with live capture services: read the warning)",
            )
        )
        by_key = {"1": rec.profile, **{str(n): name for n, name in enumerate(others, 2)}}
        current = self.a.profile or rec.profile
        default = next((k for k, v in by_key.items() if v == current), "1")
        got = ui.menu(options, default=default)
        if got == "s":
            ui.warn(
                "shared-nvidia is the old lab VM's profile: GPU sharing rules R1-R3 need a "
                "Frigate NVR on the same host and REFUSE every GPU step without one; it adds "
                "market-hour gates and a 100 GB recorder floor. Never on a machine that is "
                "the lab's alone."
            )
            if ui.ask("Type shared to choose it anyway") != "shared":
                raise Back
            self.a.profile = "shared-nvidia"
        else:
            self.a.profile = by_key[got]
        self.a.build_vision = False
        self.a.worker_mem = ""
        self.a.render_node = ""
        if self.a.profile != "dedicated-cpu":
            ready = rec.ready and self.a.profile == rec.profile
            if not ready:
                ui.warn(
                    "This GPU profile is not the recommendation: the vision steps may fail "
                    "until the fixes above are done; the CPU detector runs meanwhile."
                )
            ui.p(
                "The GPU vision image (~12 GB, 20-60 min) is needed only for the GPU detector "
                "(manual section 9); without it the CPU detector runs."
            )
            got = ui.menu(
                [("1", "Skip it for now"), ("2", "Build it during the install")],
                default="2" if ready else "1",
            )
            self.a.build_vision = got == "2"
            self.a.worker_mem = rec.worker_mem if ready else ""
            self.a.render_node = rec.render_node if ready else ""
        self.save()

    # -- 1 --

    def s_server(self) -> None:
        ui = self.ui
        self.addrs = core.host_addrs(core.run_process)
        detected = core.default_route_ip(core.run_process)
        current = self.a.server_ip or detected or ""
        while True:
            if current and not core.server_ip_problem(current, self.addrs):
                where = next((a for a in self.addrs if a.ip == current), None)
                net = f" (interface {where.ifname}, {where.network})" if where else ""
                ui.p(f"This server's LAN address: [bold]{current}[/]{net}")
                ui.p("Everything binds to it, and the game server tells the client to use it.")
                if (
                    ui.menu(
                        [("1", f"Yes, use {current}"), ("2", "Pick another address")], default="1"
                    )
                    == "1"
                ):
                    self.a.server_ip = current
                    self.a.viewer_net = self.viewer_net(current)
                    return
            elif current:
                ui.err(core.server_ip_problem(current, self.addrs))
            options = [
                (str(n), f"{a.ip}  ({a.ifname}, {a.network})") for n, a in enumerate(self.addrs, 1)
            ]
            options.append(("t", "Type an address"))
            got = ui.menu(options)
            current = ui.ask("The address") if got == "t" else self.addrs[int(got) - 1].ip

    def viewer_net(self, ip: str) -> str:
        """VIEWER_NETWORKS, only when the current list (default: every private range) does not
        cover this server's own network -- and then that network is ADDED to the list, never put
        in its place (Batt 2026-11-19: "do not lock it to the local network"; 2026-11-17: no LAN
        assumed; ADR-0026)."""
        import ipaddress

        where = next((a for a in self.addrs if a.ip == ip), None)
        listed = self.env().get("VIEWER_NETWORKS", "").strip() or core.PRIVATE_NETWORKS
        if listed.lower() == "any":
            return ""
        try:
            nets = [ipaddress.ip_network(n.strip(), strict=False) for n in listed.split(",") if n]
            if any(ipaddress.ip_address(ip) in n for n in nets):
                return ""
        except ValueError:
            pass
        return f"{listed},{where.network}" if where else ""

    # -- 2 --

    def s_port(self) -> None:
        ui = self.ui
        env_port = self.env().get("CONSOLE_PORT", "").strip()
        default = str(
            self.a.console_port or (env_port if env_port.isdigit() else core.DEFAULT_CONSOLE_PORT)
        )
        ui.p(
            "The web console opens at http://<server>:<port>. The default is 3000; any free port "
            f"from {core.PORT_MIN} to {core.PORT_MAX} works, except the lab's own "
            f"({', '.join(str(p) for p in sorted(core.LAB_PORTS))})."
        )
        while True:
            port, why = core.parse_port(ui.ask("Console port", default))
            if port is None or why:
                ui.err(why)
                continue
            held = core.our_ports(core.run_process)  # this copy's own containers
            ok, msg = core.port_verdict(self.a.server_ip, port, held=held)
            if not ok:
                ui.err(msg)
                continue
            if port in self.a.ports.values():
                ui.err(f"{port} is one of this install's own ports: pick another")
                continue
            ui.ok(msg)
            url = core.console_url(self.a.server_ip, port)
            ui.p(f"The console will be at [bold]{url}[/] (open it from a third computer).")
            if (
                ui.menu([("1", f"Use port {port}"), ("2", "Choose another port")], default="1")
                == "1"
            ):
                self.a.console_port = port
                self.move_busy_ports()
                return
            default = str(port)

    def move_busy_ports(self) -> None:
        """ADR-0026: the game, backend and noVNC ports another program holds on this address
        move to a free one (this copy's own running containers hold theirs: not counted)."""
        ui = self.ui
        env = {**self.env(), **{k: str(v) for k, v in self.a.ports.items()}}
        held = core.our_ports(core.run_process)
        moves = core.port_moves(self.a.server_ip, env, held)
        moves = {k: v for k, v in moves.items() if v[1] != self.a.console_port}
        if not moves:
            ui.ok("This install's other ports are free (or this copy's own).")
            return
        ui.rows(
            [
                (k, f"{old} is in use -> {new or '(none free: type one)'}")
                for k, (old, new) in moves.items()
            ],
            title="Ports another program holds",
        )
        for key, (old, new) in moves.items():
            while not new:
                port, why = core.parse_port(ui.ask(f"{key} (instead of {old})"))
                if port is None or why:
                    ui.err(why)
                    continue
                if core.bind_state(self.a.server_ip, port) != "free":
                    ui.err(f"{port} is in use too")
                    continue
                new = port
            self.a.ports[key] = new
        ui.warn(
            "rAthena's ports changed: your game client's clientinfo.xml must name the new "
            "login port (manual 7.1); rAthena advertises the char and map ports itself."
        )
        self.save()

    # -- 3 --

    def s_windows(self) -> None:
        ui = self.ui
        self.addrs = self.addrs or core.host_addrs(core.run_process)
        ui.p(
            f"Do the Windows guide first ({GUIDE}): Sunshine installed and running, its web login "
            "set, its firewall rules scoped to THIS server, and the PC's fixed address."
        )
        ui.p("On the PC, `ipconfig` shows the address: the 'IPv4 Address' line.")
        default = self.a.win_ip or self.env().get("WIN_HOST", "").strip()
        ip = ""
        while True:
            if not ip:
                ip = ui.ask("The Windows PC's IPv4 address", default)
                err, warnings = core.win_ip_problems(ip, self.a.server_ip, self.addrs)
                if err:
                    ui.err(err)
                    ip = ""
                    continue
                for w in warnings:
                    ui.warn(w)
            with ui.c.status(
                f"Testing Sunshine on {ip} (TCP {', '.join(map(str, core.SUNSHINE_TCP))})"
            ):
                ports = core.probe_sunshine(ip)
            ui.rows(
                [
                    (f"TCP {p}", "[green]open[/]" if okp else "[red]closed or filtered[/]")
                    for p, okp in ports.items()
                ],
                markup=True,
            )
            if all(ports.values()):
                ui.ok(
                    f"Sunshine answers on {ip}. (UDP 47998-48000 carries the video; the stream "
                    "test on screen 7 proves it.)"
                )
                self.a.win_ip = ip
                if ui.menu([("1", "Continue"), ("2", "Change the address")], default="1") == "1":
                    return
                default, ip = ip, ""
                continue
            ui.err(f"Sunshine does not answer on every port at {ip}.")
            ui.fixes("Check, on the PC:", core.SUNSHINE_FIXES)
            got = ui.menu(
                [
                    ("r", "Test again"),
                    ("2", "Change the address"),
                    ("c", "Continue anyway (pairing will fail until it answers)"),
                ],
                default="r",
            )
            if got == "2":
                default, ip = ip, ""
            elif got == "c":
                self.a.win_ip = ip
                return

    # -- 3b --

    def s_storage(self) -> None:
        """Batt 2026-11-17: "most users have no NAS: just set where the files are stored in the
        setup" (ADR-0026). One folder (LAB_STORE_DIR); a NAS is a folder mounted there."""
        ui = self.ui
        home = Path.home()
        default = (
            self.a.store_dir
            or self.env().get("LAB_STORE_DIR", "").strip()
            or str(home / core.lab_env.STORE_DEFAULT)
        )
        ui.p(
            "Long-term files (datasets, archives, recordings, the deployed models) go to ONE "
            "folder. No NAS is needed; with a NAS, mount it and give that folder. Recordings "
            "take 0.84 GB/h (video) or 7-8 GB/h (PNG)."
        )
        while True:
            raw = ui.ask("The storage folder", default)
            path = Path(raw).expanduser()
            if not path.is_absolute():
                ui.err("Give an absolute folder, e.g. /srv/poring-lab-store")
                continue
            probe = path
            while not probe.exists() and probe != probe.parent:
                probe = probe.parent
            free = shutil.disk_usage(probe).free / 1e9
            later = "" if path.exists() else " (created at the next step)"
            say = ui.ok if free >= 50 else ui.warn
            say(f"{path}: {free:.0f} GB free on its disk{later}")
            if ui.menu([("1", f"Use {path}"), ("2", "Another folder")], default="1") == "1":
                self.a.store_dir = str(path)
                self.save()
                return
            default = str(path)

    # -- 4 --

    def s_review(self) -> None:
        ui = self.ui
        env_path = core.REPO / ".env"
        current = core.env_baseline(core.REPO)  # before .env exists: .env.example's defaults
        gid = core.render_gid()
        plan = core.planned_env(self.a, current, gid=gid, home=Path.home())
        changes = core.env_changes(current, plan)
        ui.rows(
            [
                ("Server address", self.a.server_ip),
                ("Console", core.console_url(self.a.server_ip, self.a.console_port)),
                ("Windows PC", self.a.win_ip),
                ("Host profile", self.a.profile),
                ("GPU vision image", "build it" if self.a.build_vision else "skip (CPU detector)"),
                ("Docker name", core.project()),
                ("Storage folder", self.a.store_dir or "(default)"),
                ("Moved ports", ", ".join(f"{k}={v}" for k, v in self.a.ports.items()) or "none"),
                (
                    "Docker subnets",
                    ", ".join(f"{v}.0/24" for v in self.a.nets.values())
                    or "the defaults (10.210.96/97)",
                ),
                (
                    "Display path",
                    "RDP credentials are set in .env (see the warning below)"
                    if core.rdp_credentials_set(current)
                    else "Sunshine only: RDP stays off (RDP_USER / RDP_PASSWORD empty)",
                ),
            ],
            title="Your settings",
        )
        if not env_path.exists():
            ui.p(
                "No .env yet: scripts/init_env.sh creates it with RANDOM secrets (database, the "
                "inter-server account, the test, agent and GM game accounts), then:"
            )
        if changes:
            ui.rows(
                [(k, f"{core.shown(k, old)}  ->  {core.shown(k, new)}") for k, old, new in changes],
                title=".env changes (through rotate_secrets.py set, read back)",
            )
        else:
            ui.ok(".env already has every one of these settings: nothing to change.")
        with ui.c.status("Which running services must take the new settings?"):
            recreate = core.services_to_recreate(changes, core.run_process) if changes else []
        if recreate:
            ui.warn(
                "These services already run with the old values and will be RECREATED during the "
                f"install (guarded): {', '.join(recreate)}."
            )
        if core.rdp_credentials_set(current):
            ui.warn(
                "RDP_USER / RDP_PASSWORD are set in this .env: with WIN_HOST set, the desktop "
                "opens an RDP session to the PC (it takes the PC's one session). This wizard "
                "sets up the Sunshine-only path and will SKIP pairing and the stream test on "
                "an RDP host (rule 2: one display path). The wizard never edits those "
                "secrets: empty them in .env yourself for Sunshine only."
            )
        if ui.menu([("1", "Write .env and continue")], default="1") != "1":
            raise Back
        log = core.step_log("env", 0)
        try:
            created, done = core.write_env(
                core.REPO, self.a, core.run_process, gid=gid, home=Path.home(), log=log
            )
        except core.SetupError as exc:
            ui.err(str(exc))
            ui.menu([("r", "Try again")], default="r")
            raise Back from None
        if created:
            ui.ok(".env created by scripts/init_env.sh (mode 600, random secrets)")
        ui.ok("set in .env and read back: " + (", ".join(k for k, _, _ in done) or "nothing new"))
        self.progress["env_written"] = time.strftime("%Y-%m-%d %H:%M:%S")
        pending = set(self.progress.get("recreate", [])) | set(recreate)
        self.progress["recreate"] = [s for s in core.RECREATE_ORDER if s in pending]

    # -- 5 --

    def s_install(self) -> None:
        ui = self.ui
        state = self.steps_state()
        if not state:
            have = core.lab_containers(core.run_process)
            if have:
                ui.warn(
                    f"{core.project()} containers already exist on this host ({len(have)}: "
                    f"{', '.join(sorted(have))}). The install checks each step and skips "
                    "what is done, but it may start or rebuild services. For a status only, "
                    "quit and run ./setup.sh --check."
                )
                if ui.ask("Type install to go on") != "install":
                    raise Back
        env = self.env()
        steps = core.install_plan(core.REPO, env, self.a)
        steps += core.recreate_steps(self.progress.get("recreate", []))
        ui.p(
            f"{len(steps)} steps, one at a time through scripts/guarded_build.py. The first "
            "install downloads and builds for a while (often 30-90 minutes). Logs: "
            f"{core.SCRATCH / 'logs'}"
        )
        for n, step in enumerate(steps, 1):
            label = f"[{n}/{len(steps)}] {step.title}"
            log = core.step_log(step.id, n)
            if state.get(step.id, {}).get("state") == "skipped":
                ui.warn(f"{label}: skipped earlier")
                continue
            if step.done is not None and step.done(core.run_process):
                ui.ok(f"{label}: already done")
                state[step.id] = {"state": "done", "checked": time.strftime("%H:%M:%S")}
                self.save()
                continue
            while True:
                t0 = time.monotonic()
                res = ui.run(label, step.cmd, log=log, timeout=step.timeout)
                took = fmt_s(time.monotonic() - t0)
                if res.ok:
                    ui.ok(f"{label}  ({took})")
                    state[step.id] = {"state": "done", "took": took, "log": str(log)}
                    settled = core.RECREATE_DONE.get(step.id, ())
                    self.progress["recreate"] = [
                        s for s in self.progress.get("recreate", []) if s not in settled
                    ]
                    self.save()
                    break
                ui.err(f"{label} FAILED (exit {res.rc}, after {took})")
                ui.tail(res.out)
                ui.p(f"[bold]Fix:[/] {esc(step.fix)}")
                ui.p(f"Full output: {esc(log)}")
                state[step.id] = {"state": "failed", "rc": res.rc, "log": str(log)}
                self.save()
                options = [("r", "Retry")]
                if step.optional:
                    options.append(("s", "Skip this optional step"))
                got = ui.menu(options, default="r")
                if got == "s":
                    state[step.id] = {"state": "skipped"}
                    self.save()
                    break
        ip, port = self.a.server_ip, self.a.console_port
        health = f"http://{ip}:{core.backend_port(core.read_env(core.REPO / '.env'))}/health"
        while True:
            with ui.c.status("Waiting for the backend and the console (up to 3 minutes)..."):
                backend = core.wait_http(health, 180)
                console = core.wait_http(f"{core.console_url(ip, port)}/api/health", 180)
            for ok, what in (
                (backend, f"the backend: {health}"),
                (console, f"the console: {core.console_url(ip, port)}"),
            ):
                (ui.ok if ok else ui.warn)(what + ("" if ok else " does not answer yet"))
            if backend and console:
                return
            ui.p("`scripts/dev.sh ps` and `scripts/dev.sh logs <service>` show why.")
            if ui.menu([("1", "Continue anyway"), ("r", "Check again")], default="r") == "1":
                return

    # -- 6 --

    def s_pair(self) -> None:
        ui = self.ui
        env = self.env()
        if core.rdp_configured(env):
            ui.warn(
                "RDP is configured on this host: the Sunshine pairing and stream test are "
                "skipped (rule 2: one display path). The RDP handovers are in "
                "scripts/capture_backend.py."
            )
            self.progress["paired"] = "skipped (RDP host)"
            ui.menu([("1", "Continue")], default="1")
            return
        while True:
            with ui.c.status("Is the lab's Sunshine client paired?"):
                state = core.paired_state(core.run_process)
            if state == "paired":
                ui.ok("Already paired with Sunshine: nothing to do.")
                self.progress["paired"] = "yes"
                return
            if state != "not paired":
                ui.err(f"Cannot pair: {state}. The install's last step starts gamestream.")
                ui.menu([("r", "Check again")], default="r")
                continue
            pin = core.new_pin()
            ui.p("On the Windows PC (at the PC itself: Sunshine's page opens only there):")
            ui.fixes(
                "",
                (
                    "Open Sunshine's web page: https://localhost:47990 (log in with YOUR Sunshine "
                    "login; the wizard never asks for it).",
                    "Click PIN in the top bar.",
                    "Type the PIN below, and a device name (for example poring-lab).",
                    "Click Send. 'Success! Please check Moonlight to continue' means done.",
                ),
            )
            ui.pin(pin)
            ui.p("The wizard asks Sunshine FIRST (a PIN is accepted only while it waits), so:")
            if (
                ui.menu(
                    [("1", "Start pairing now, then type the PIN on the PC within 3 minutes")],
                    default="1",
                )
                != "1"
            ):
                continue
            log = core.step_log("pair", 0)
            res = ui.run(
                f"Waiting for PIN {pin} on the PC", core.pair_cmd(pin), log=log, timeout=300
            )
            if core.paired_state(core.run_process) == "paired":
                ui.ok("Paired: the lab's client key is in the gamestream-state volume.")
                self.progress["paired"] = "yes"
                return
            ui.err(f"Pairing did not complete (exit {res.rc}).")
            ui.tail(res.out)
            ui.fixes("Check:", core.PAIR_FIXES)
            ui.menu([("r", "Try again with a new PIN")], default="r")

    # -- 7 --

    def s_stream(self) -> None:
        ui = self.ui
        env = self.env()
        if core.rdp_configured(env):
            ui.warn("RDP is configured on this host: the Sunshine stream test is skipped.")
            self.progress["stream"] = {"ok": False, "why": "RDP host"}
            ui.menu([("1", "Continue")], default="1")
            return
        session = core.session_size(env.get("SESSION_SIZE", ""))
        while True:
            lock = core.lock_now(core.REPO)
            here = (lock.get("BACKEND"), lock.get("PHASE"), lock.get("REASON"))
            if here != ("console", "steady", "sunshine-only"):
                ui.p(
                    "Switching the ONE display path to Sunshine: capture_backend.py to-console "
                    "--sunshine-only (it refuses if RDP could connect) and waiting for the "
                    "first decoded frame."
                )
                log = core.step_log("stream-on", 0)
                res = ui.run("Starting the stream", core.stream_on_cmd(), log=log, timeout=240)
                if not res.ok:
                    ui.err(f"The stream did not start (exit {res.rc}).")
                    ui.tail(res.out)
                    ui.fixes("Check:", core.STREAM_FIXES)
                    if self.retry_or_continue():
                        continue
                    return
                ui.ok("The lock is console/steady: the S2 client streams the PC.")
            else:
                ui.ok("Already streaming (console/steady, sunshine-only).")
            out = core.SCRATCH / "stream-test.png"
            log = core.step_log("stream-frame", 0)
            res = ui.run("Grabbing one fresh frame", core.frame_cmd(out), log=log, timeout=120)
            try:
                rep = core.parse_frame_report(res.out) if res.ok else {}
            except core.SetupError:
                rep = {}
            problems = core.judge_frame(rep, session) if rep else ["no frame was grabbed"]
            if rep:
                ui.rows(
                    [
                        ("Picture", str(rep.get("path"))),
                        ("Size", f"{rep.get('width')} x {rep.get('height')}"),
                        ("Source", f"{rep.get('source')} (the S2 frame bus = the live stream)"),
                        ("Frame age", f"{rep.get('age_ms')} ms"),
                        (
                            "New frames in 2 s",
                            "yes" if rep.get("advanced") else "no (a still screen)",
                        ),
                        ("Black pixels", f"{float(rep.get('dark_fraction', 0)):.0%}"),
                    ],
                    title="The stream test",
                )
            if not problems:
                ui.ok(
                    "This is the Windows PC's screen, live. Open the picture to see it "
                    f"(from your laptop: scp {os.environ.get('USER', 'you')}@"
                    f"{self.a.server_ip}:{out} .)"
                )
                self.progress["stream"] = {
                    "ok": True,
                    "size": f"{rep['width']}x{rep['height']}",
                    "png": str(out),
                }
                return
            for prob in problems:
                ui.err(prob)
            if not res.ok:
                ui.tail(res.out)
            ui.fixes("Check:", core.STREAM_FIXES)
            if not self.retry_or_continue():
                return

    def retry_or_continue(self) -> bool:
        got = self.ui.menu(
            [("r", "Test again"), ("c", "Continue without a working stream")], default="r"
        )
        if got == "c":
            self.progress["stream"] = {"ok": False, "why": "not working"}
            return False
        return True

    # -- 8 --

    def s_done(self) -> None:
        ui = self.ui
        env = self.env()
        url = core.console_url(self.a.server_ip, self.a.console_port)
        stream = self.progress.get("stream", {})
        stream_txt = (
            f"OK, {stream.get('size')} frame: {stream.get('png')}"
            if stream.get("ok")
            else f"NOT OK ({stream.get('why', 'not run')})"
        )
        ui.rows(
            [
                (
                    "Console",
                    f"{url}  (from a third computer: the Settings page refuses writes from this "
                    "server and from the game PC)",
                ),
                ("Server address", self.a.server_ip),
                ("Windows PC", self.a.win_ip),
                ("Host profile", env.get("LAB_HOST_PROFILE", self.a.profile)),
                ("Sunshine paired", str(self.progress.get("paired", "no"))),
                ("Stream test", stream_txt),
                (".env", str(core.REPO / ".env") + " (mode 600; secrets stay there)"),
                ("Logs", str(core.SCRATCH / "logs") + " (RAM: gone after a reboot)"),
                ("Resume file", str(core.PROGRESS)),
            ],
            title="poring-lab is set up",
        )
        ui.p()
        ui.fixes(
            "Next steps:",
            (
                f"Open {url}: the console always starts in HUMAN mode; only a person switches "
                "it to ASSIST or BOT.",
                "The game client on the PC (docs/windows-setup.md sections 1 and 2): its "
                f"clientinfo.xml points at {self.a.server_ip} port 6900, its account-settings "
                f"files (AssistAddr) at {self.a.server_ip}:8888.",
                "Settings page (from your laptop): add and confirm YOUR servers "
                f"({self.a.server_ip} ports 6900, 6121, 5121). Do not confirm the shipped "
                "suggestions (they name the lab's own server).",
                "Client-derived data and the detector: docs/setup/new-lab-host.md sections 8 "
                "and 9.",
                "Status any time: ./setup.sh --check",
            ),
        )
        ui.p()
        ui.fixes("[yellow]KNOWN LIMIT of this Sunshine-only setup (read it):[/]", core.S2_LIMIT)


def interactive(progress: dict[str, Any]) -> int:
    try:
        import rich  # noqa: F401
    except ImportError:
        print("rich is not installed in this environment: run ./setup.sh (it runs `uv sync`).")
        return 1
    ui = UI()
    ui.p(
        "[bold]poring-lab setup[/]: this server becomes a lab host; the Windows PC streams the "
        f"game with Sunshine ({GUIDE} first). English screens; every one has Back and Quit; "
        "Ctrl+C saves and stops."
    )
    wizard = Wizard(ui, progress)
    try:
        return wizard.run()
    except Quit:
        wizard.save()
        ui.p("Saved. Run ./setup.sh to resume.")
        return 0
    except KeyboardInterrupt:
        wizard.save()
        ui.p("\nStopped (Ctrl+C). Saved: run ./setup.sh to resume.")
        return 130


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only status")
    mode.add_argument("--dry-run", action="store_true", help="print every step; run nothing")
    ap.add_argument(
        "--no-exec",
        action="store_true",
        help="with --check: no probe inside a container (the pairing check)",
    )
    ap.add_argument("--restart", action="store_true", help="forget the saved progress (not .env)")
    a = ap.parse_args(argv)
    if a.check:
        return plain_check(a.no_exec)
    progress = {} if a.restart else core.load_progress()
    if a.dry_run:
        return plain_dry_run(progress)
    return interactive(progress)


if __name__ == "__main__":
    sys.exit(main())
