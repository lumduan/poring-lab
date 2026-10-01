#!/usr/bin/env bash
# Dev stack without image builds (see compose.dev.yaml). Read-only and stop commands only:
#   scripts/dev.sh ps / logs -f backend / exec backend … / config --no-interpolate
#   scripts/dev.sh stop frontend-dev              # console off; desktop (RDP) keeps running
#
# Everything that creates, starts, restarts, recreates, builds or pulls goes through the IO guard
# (CLAUDE.md rule 5; three unguarded runs hurt live capture in 2026-09/10):
#   python3 scripts/guarded_build.py --sustain 30 --spike 25 start:<svc>@<s>     # up -d --no-build
#   python3 scripts/guarded_build.py --sustain 30 --spike 25 recreate:<svc>@<s>  # --force-recreate
#   python3 scripts/guarded_build.py --sustain 30 --spike 25 restart:<svc>@<s>   # e.g. backend code
#   python3 scripts/guarded_build.py --sustain 30 --spike 25 build:<svc>
# This script refuses those subcommands unless its parent process IS scripts/guarded_build.py.
set -euo pipefail
cd "$(dirname "$0")/.."

guarded_parent() {
  local cmdline
  cmdline="$(tr '\0' ' ' <"/proc/${PPID}/cmdline" 2>/dev/null || true)"
  [[ "${cmdline}" == *"scripts/guarded_build.py"* ]]
}

refuse() {
  echo "scripts/dev.sh: REFUSED '$*' -- $1 must go through the IO guard:" >&2
  echo "  python3 scripts/guarded_build.py --sustain 30 --spike 25 <step>" >&2
  echo "  steps: start:<svc>[@s]  recreate:<svc>[@s]  restart:<svc>[@s]  build:<svc>  pull:<svc>" >&2
  exit 64
}

# Find the compose subcommand: the first word that is not a global option (or its value).
sub="" config_safe=false force=false
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  a="${args[i]}"
  case "${a}" in
    --profile | -f | --file | -p | --project-name | --env-file | --project-directory | --ansi | \
      --progress | --parallel)
      ((i += 1)) ;;
    --force-recreate) force=true ;;
    --no-interpolate | -q | --quiet) config_safe=true ;;
    -*) ;;
    *) [[ -z "${sub}" ]] && sub="${a}" ;;
  esac
done

case "${sub}" in
  "" | ps | logs | exec | top | images | ls | version | port | events | stop | kill | pause | unpause)
    ;;
  config)
    ${config_safe} || { echo "scripts/dev.sh: REFUSED 'config' without --no-interpolate or -q" \
      "(an interpolated config prints .env secrets)" >&2; exit 64; } ;;
  *)
    guarded_parent || refuse "${sub}" ;;
esac
if ${force} && ! guarded_parent; then refuse "--force-recreate"; fi

exec docker compose -f compose.yaml -f compose.dev.yaml --profile remote --profile dev "$@"
