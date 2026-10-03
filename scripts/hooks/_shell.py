"""The shell tokenizer shared by the PreToolUse hooks (guard_docker.py, guard_bigread.py).

Standard library only: a hook runs under the host's bare `python3`, with no venv.

  strip_heredocs(cmd) -> (cmd without heredoc bodies, the bodies fed to a local shell)
  strip_comments(cmd) -> cmd with every unquoted `# …` removed up to (NOT including) its newline
  segments(cmd)       -> the simple commands, split at ; & | ( ) and newlines
  unwrap(words)       -> words without leading VAR=…, keywords and wrappers (sudo, env, timeout …)

Comments are stripped by a quote-aware pass BEFORE tokenizing, because shlex's own comment handling
ate the newline that ends a comment: `echo hi # note` + newline + `docker build .` came out as ONE
`echo` command and slipped past the docker guard (found 2026-10-03). bash starts a comment only at
a word start, so `foo#bar`, `$#` and `${#x}` are not comments, and a quoted `'#'` never is.
"""

from __future__ import annotations

import re
import shlex

SEPARATORS = ";&|()\n"
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
_WORD_START = set(" \t\r" + SEPARATORS)


def strip_heredocs(command: str) -> tuple[str, list[str]]:
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


def strip_comments(command: str) -> str:
    """Drop unquoted `#` comments (to end of line; the newline stays a command separator)."""
    out: list[str] = []
    quote = ""  # "", "'" or '"'
    i = 0
    n = len(command)
    while i < n:
        c = command[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = ""
        elif c == "\\" and i + 1 < n:  # an escaped char (inside "…" or bare) is never special
            out.append(command[i : i + 2])
            i += 1
        elif quote == '"':
            out.append(c)
            if c == '"':
                quote = ""
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "#" and (i == 0 or command[i - 1] in _WORD_START):
            nl = command.find("\n", i)
            i = n if nl < 0 else nl  # keep the newline itself
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def segments(command: str) -> list[list[str]]:
    """Simple commands. Raises ValueError on unbalanced quotes (callers fall back to a regex)."""
    lexer = shlex.shlex(strip_comments(command), posix=True, punctuation_chars=SEPARATORS)
    lexer.whitespace = " \t\r"  # newlines separate commands (quoted ones stay inside a word)
    lexer.whitespace_split = True
    lexer.commenters = ""  # done above, quote-aware, without eating the newline
    out: list[list[str]] = [[]]
    for tok in lexer:
        if tok and set(tok) <= set(SEPARATORS):
            out.append([])
        else:
            out[-1].append(tok)
    return [s for s in out if s]


def unwrap(words: list[str]) -> list[str]:
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
