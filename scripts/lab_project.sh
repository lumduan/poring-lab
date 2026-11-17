#!/usr/bin/env bash
# This copy's Docker Compose project name, for bash (Batt 2026-11-17: "don't lock an IP or
# anything"; two copies on one host need two names). Every container, network, volume and image of
# a copy starts with it: "<project>-desktop-1", "<project>_default", "<project>/sniffer:local".
# The SAME order as scripts/lab_env.py's project() and scripts/dev.sh: the environment's
# COMPOSE_PROJECT_NAME, else the repo .env's first COMPOSE_PROJECT_NAME= line, else poring-lab.
#
#   source "$(dirname "$0")/lab_project.sh" && C="$(lab_project)-desktop-1"   # in a script
#   P="$(scripts/lab_project.sh)"                                              # by hand: prints it
lab_project() {
  local root p=""
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  p="${COMPOSE_PROJECT_NAME:-}"
  if [[ -z "${p}" && -f "${root}/.env" ]]; then
    p="$(sed -n '/^COMPOSE_PROJECT_NAME=/{s///;s/[[:space:]]//g;p;q}' "${root}/.env")"
  fi
  p="${p:-poring-lab}"
  if [[ ! "${p}" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]]; then
    echo "COMPOSE_PROJECT_NAME='${p}': lowercase letters, digits, - and _ only" >&2
    return 64
  fi
  printf '%s\n' "${p}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  lab_project
fi
