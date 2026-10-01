#!/usr/bin/env python3
"""PreToolUse hook (matcher Bash): no unguarded docker build / pull / run / start / recreate here.

Why (CLAUDE.md rule 5): this host's Docker shares ONE virtual disk with live quant capture. Three
times in 2026-09/10 an agent ran a heavy step outside `scripts/guarded_build.py` -- a full image
build (52.8 % capture IO stall), a sniffer recreate (67 %) and a desktop force-recreate (30.8 %).
`scripts/dev.sh` refuses those subcommands unless the guard is its parent; this hook closes the
other door: docker / docker compose typed directly.

REFUSES (exit 2, reason on stderr):
  - docker build | buildx | pull | run | create | start | restart (and `docker container|image …`)
  - docker compose / docker-compose / scripts/dev.sh with a mutating subcommand
    (up create build pull run restart start down rm scale watch) or --force-recreate
  - docker compose config WITHOUT --no-interpolate / -q (an interpolated config prints .env secrets)
ALLOWS everything else -- ps, logs, exec, inspect, images, stats, tag, stop … -- and any command
whose head is `scripts/guarded_build.py` (the guard's own docker calls are subprocesses and never
reach this hook).

SEES THROUGH: `;` `&&` `||` `|` `&` `( )`, newlines, leading VAR=… assignments, the wrappers sudo,
env, nice, ionice, timeout, nohup, exec, command, time, stdbuf, `bash|sh -c "…"`, and a heredoc fed
to a local shell. CANNOT SEE: commands built at run time ($VAR, $(…), eval, xargs) or run by a
script/program (`python -c 'subprocess.run(["docker", "build", …])'`) -- the stated boundary.

FAIL DIRECTION: unreadable hook input -> allow (a guard that blocks every Bash call is worse); a
command the tokenizer can't parse -> a conservative regex still refuses the plain forms.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

GUARDED = "python3 scripts/guarded_build.py --sustain 30 --spike 25 <step>"
STEPS = "start:<svc>[@s] recreate:<svc>[@s] restart:<svc>[@s] build:<svc> pull:<svc>"
DOCKER_BLOCK = frozenset({"build", "buildx", "pull", "run", "create", "start", "restart"})
COMPOSE_BLOCK = frozenset(
    {"up", "create", "build", "pull", "run", "restart", "start", "down", "rm", "scale", "watch"}
)
DOCKER_OPTS_WITH_VALUE = frozenset(
    {"--context", "-c", "-H", "--host", "--config", "-l", "--log-level", "--tlscacert",
     "--tlscert", "--tlskey"}
)  # fmt: skip
COMPOSE_OPTS_WITH_VALUE = frozenset(
    {"-f", "--file", "-p", "--project-name", "--profile", "--env-file", "--project-directory",
     "--ansi", "--progress", "--parallel"}
)  # fmt: skip
WRAPPERS = frozenset(
    {"sudo", "env", "nice", "ionice", "timeout", "nohup", "exec", "command", "time", "stdbuf"}
)
WRAPPER_OPTS_WITH_VALUE = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "ionice": frozenset({"-c", "-n", "-p", "--class", "--classdata"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "stdbuf": frozenset({"-i", "-o", "-e"}),
}
SHELLS = frozenset({"bash", "sh", "dash", "zsh"})
KEYWORDS = frozenset({"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}", "time"})
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
FALLBACK = re.compile(
    r"(?:^|[;&|\s(])(?:docker\s+(?:compose\s+)?|docker-compose\s+|scripts/dev\.sh\s+)"
    r"(?:\S+\s+)*?(build|buildx|pull|run|create|start|restart|up|down|--force-recreate)\b"
)


def _strip_heredocs(command: str) -> tuple[str, list[str]]:
    """Remove heredoc bodies; return (command without bodies, bodies fed to a local shell)."""
    lines = command.split("\n")
    out: list[str] = []
    shell_bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            word = m.group(2)
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != word:
                body.append(lines[i])
                i += 1
            head = line[: m.start()].split()
            if head and head[-1] in SHELLS | {"-s"} or (head and head[0] in SHELLS):
                shell_bodies.append("\n".join(body))
        i += 1
    return "\n".join(out), shell_bodies


def _segments(command: str) -> list[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"  # newlines separate commands (quoted ones stay inside a word)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    segments: list[list[str]] = [[]]
    for tok in lexer:
        if tok and set(tok) <= set(";&|()\n"):
            segments.append([])
        else:
            segments[-1].append(tok)
    return [s for s in segments if s]


def _unwrap(words: list[str]) -> list[str]:
    i = 0
    while i < len(words):
        w = words[i]
        if ASSIGN.match(w) or w in KEYWORDS:
            i += 1
        elif w in WRAPPERS:
            opts = WRAPPER_OPTS_WITH_VALUE.get(w, frozenset())
            i += 1
            if w == "timeout":  # timeout [opts] DURATION cmd
                while i < len(words) and words[i].startswith("-"):
                    i += 2 if words[i] in opts else 1
                i += 1
                continue
            while i < len(words) and (words[i].startswith("-") or ASSIGN.match(words[i])):
                i += 2 if words[i] in opts else 1
        else:
            break
    return words[i:]


def _compose_reason(args: list[str], what: str) -> str | None:
    sub = None
    force = safe_config = False
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in COMPOSE_OPTS_WITH_VALUE:
            skip = True
        elif a == "--force-recreate":
            force = True
        elif a in ("--no-interpolate", "-q", "--quiet"):
            safe_config = True
        elif not a.startswith("-") and sub is None:
            sub = a
    if sub in COMPOSE_BLOCK:
        return f"`{what} {sub}`"
    if force:
        return f"`{what} … --force-recreate`"
    if sub == "config" and not safe_config:
        return f"`{what} config` without --no-interpolate/-q (prints .env secrets)"
    return None


def classify_words(words: list[str], depth: int = 0) -> str | None:
    """A refusal reason for one simple command, or None if it is allowed."""
    words = _unwrap(words)
    if not words:
        return None
    head = words[0].rsplit("/", 1)[-1]
    if head in SHELLS:
        if "-c" in words[1:]:
            idx = words.index("-c", 1)
            if idx + 1 < len(words) and depth < 4:
                return classify(words[idx + 1], depth + 1)
        script = next((w for w in words[1:] if not w.startswith("-")), "")
        if script.endswith("dev.sh"):
            return _compose_reason(words[2:], "scripts/dev.sh")
        return None
    if head.startswith("python") and any(
        w.endswith("scripts/guarded_build.py") for w in words[1:3]
    ):
        return None  # the guard itself
    if head == "dev.sh":
        return _compose_reason(words[1:], "scripts/dev.sh")
    if head == "docker-compose":
        return _compose_reason(words[1:], "docker-compose")
    if head != "docker":
        return None
    rest = words[1:]
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        i += 2 if rest[i] in DOCKER_OPTS_WITH_VALUE else 1
    if i >= len(rest):
        return None
    verb = rest[i]
    if verb == "compose":
        return _compose_reason(rest[i + 1 :], "docker compose")
    sub_blocked = i + 1 < len(rest) and (verb == "buildx" or rest[i + 1] in DOCKER_BLOCK)
    if verb in ("container", "image", "buildx") and sub_blocked:
        return f"`docker {verb} {rest[i + 1]}`"
    if verb in DOCKER_BLOCK:
        return f"`docker {verb}`"
    return None


def classify(command: str, depth: int = 0) -> str | None:
    stripped, shell_bodies = _strip_heredocs(command)
    try:
        segments = _segments(stripped)
    except ValueError:  # unbalanced quotes: the conservative regex
        m = FALLBACK.search(stripped)
        return f"`{m.group(0).strip()}` (unparsable command)" if m else None
    for words in segments:
        reason = classify_words(words, depth)
        if reason:
            return reason
    for body in shell_bodies:
        reason = classify(body, depth + 1)
        if reason:
            return reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "")
    except Exception:  # noqa: BLE001 -- unreadable input: fail open
        return 0
    if not isinstance(command, str) or not command:
        return 0
    reason = classify(command)
    if reason is None:
        return 0
    print(
        f"BLOCKED by poring-lab's docker guard (CLAUDE.md rule 5): {reason} must run through the "
        f"IO guard. Use: {GUARDED}  (steps: {STEPS}). Read-only docker/compose commands (ps, "
        "logs, exec, inspect, config --no-interpolate) are fine.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
