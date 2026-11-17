#!/usr/bin/env bash
# poring-lab's one setup command (Batt 2026-11-17: a student clones, cd's in, runs this; nothing else).
#
#   ./setup.sh             the setup wizard: checks, settings, install, pairing, stream test
#   ./setup.sh --check     read-only: what is set up and what answers (safe on a running lab host)
#   ./setup.sh --dry-run   prints every step the wizard would run; runs and writes nothing
#
# Before the wizard: Linux, git and uv. A missing uv is explained and installed ONLY after you
# answer yes. Then `uv sync` (the host environment) and `git config core.hooksPath .githooks` (the
# commit guard), both safe to repeat. --check and --dry-run skip those two and change nothing.
# Re-run it any time: the wizard resumes where it stopped (.setup/progress.json).
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '%s\n' "$*"; }
stop() {
  printf '\nSTOP: %s\n' "$*" >&2
  exit 1
}

read_only=false
for arg in "$@"; do
  case "${arg}" in
    --check | --dry-run) read_only=true ;;
  esac
done

[[ "$(uname -s)" == Linux ]] || stop "poring-lab runs on a Linux server (Ubuntu 26.04 LTS, see README.md)."
command -v git >/dev/null 2>&1 || stop "git is missing: sudo apt-get install -y git"

if $read_only; then
  # stdlib only: works before `uv sync` and never touches .venv
  command -v python3 >/dev/null 2>&1 || stop "python3 is missing: sudo apt-get install -y python3"
  exec python3 scripts/setup_wizard.py "$@"
fi

UV_INSTALL='curl -LsSf https://astral.sh/uv/install.sh | sh'
if ! command -v uv >/dev/null 2>&1 && [[ -x "${HOME}/.local/bin/uv" ]]; then
  export PATH="${HOME}/.local/bin:${PATH}" # installed earlier, not on PATH in this shell yet
fi
if ! command -v uv >/dev/null 2>&1; then
  say "uv is not installed. poring-lab uses it for its Python environment (README, manual section 2)."
  say "Astral's official installer puts uv in ~/.local/bin (no sudo):"
  say ""
  say "    ${UV_INSTALL}"
  say ""
  command -v curl >/dev/null 2>&1 || stop "curl is missing (sudo apt-get install -y curl), or install uv yourself: https://docs.astral.sh/uv/"
  read -r -p "Run that command now? [Y/n] " answer || answer=n
  case "${answer:-y}" in
    y | Y | yes | YES) ;;
    *) stop "uv is needed. Install it (the command above), then run ./setup.sh again." ;;
  esac
  sh -c "${UV_INSTALL}"
  export PATH="${HOME}/.local/bin:${PATH}"
  command -v uv >/dev/null 2>&1 || stop "uv is still not on PATH: open a new terminal, then ./setup.sh"
fi

# Rule 7: scratch and caches in RAM, never host /tmp; no bytecode on the disk.
export TMPDIR="${TMPDIR:-/dev/shm/poring-lab-tmp}"
if [[ "${TMPDIR}" == /tmp* ]]; then
  export TMPDIR=/dev/shm/poring-lab-tmp
fi
mkdir -p "${TMPDIR}"
export PYTHONDONTWRITEBYTECODE=1

say "== uv sync (the host environment: poring_env, the backend, the tools; no torch)"
uv sync || stop "uv sync failed: read the lines above (internet? disk space?), then ./setup.sh again."
say "== the commit guard (git config core.hooksPath .githooks)"
git config core.hooksPath .githooks
[[ "$(git config --get core.hooksPath)" == .githooks ]] || stop "core.hooksPath did not read back"

exec uv run --no-sync python scripts/setup_wizard.py "$@"
