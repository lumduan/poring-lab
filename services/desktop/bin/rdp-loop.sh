#!/usr/bin/env bash
# The ONE RDP session into the Windows host (ADR-0001), kept alive with an exit-code policy.
#
# Windows client editions allow a single interactive session: connecting kicks whoever is on it,
# and whoever connects next kicks us. So this loop must never fight a human for the session and
# must never hammer a bad password into an account-lockout policy.
#
# Exit codes come from FreeRDP 3.15's xf_exit_code_from_disconnect_reason():
#   0 1 2 3 4 11 12        clean end / RPC / logoff / idle / logon timeout / user disconnect
#                          -> reconnect after 2 s
#   5                      DISCONNECTED_BY_OTHER_CONNECTION: someone took the session
#                          -> back off 10 min, log loudly
#   132 134 135 148-159    authentication / account problems (154 wrong password, 135 locked)
#                          -> STOP (idle until the container is restarted)
#   16-26                  licensing errors, and CLI parse errors (negative codes truncated to 8 bits)
#                          -> STOP
#   anything else          connect / DNS / TLS / transport failure, target booting
#                          -> exponential backoff 2 s -> 60 s
#
# Sourcing this file (tests) defines the functions without starting the loop.
set -uo pipefail

# stderr: build_args' STDOUT is xfreerdp's argument list (/args-from:stdin), so a log line printed
# while building it must never land there. supervisord merges stderr into the container log.
log() { printf '%s rdp-loop: %s\n' "$(date -Is)" "$*" >&2; }

idle_forever() {
  log "$*"
  exec sleep infinity
}

wait_for_x() {
  until xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do sleep 0.5; done
}

# Clipboard (ADR-0004) by KEYWORD, never raw flags: a free-form value could re-enable
# Windows -> X copying or smuggle in other xfreerdp options.
#   off (default)    -clipboard
#   text-to-remote   text from this display to Windows only; no file clipboard (F2 is off), and
#                    Windows -> X disabled, so the Windows clipboard never appears on the display.
clipboard_args() {
  case "${RDP_CLIPBOARD:-off}" in
    off | "") printf '%s\n' -clipboard ;;
    text-to-remote) printf '%s\n' /clipboard:direction-to:remote,files-to:off ;;
    *)
      log "unknown RDP_CLIPBOARD='${RDP_CLIPBOARD}' (off | text-to-remote): clipboard stays OFF"
      printf '%s\n' -clipboard
      ;;
  esac
}

# Drive redirection (ADR-0004) by KEYWORD. `transfer` = the tmpfs volume at /transfer, seen in
# Windows as \\tsclient\transfer. Nothing else on this container is ever redirected.
drive_args() {
  local entry dir="${TRANSFER_DIR:-/transfer}"
  local -a entries
  IFS=',' read -ra entries <<<"${RDP_DRIVES:-}"
  for entry in "${entries[@]}"; do
    entry="${entry// /}"
    case "${entry}" in
      "") ;;
      transfer)
        if [[ -d "${dir}" ]]; then
          printf '%s\n' "/drive:transfer,${dir}"
        else
          log "RDP_DRIVES=transfer but ${dir} is not mounted: no drive redirected"
        fi
        ;;
      *) log "unknown RDP_DRIVES entry '${entry}' (only: transfer): ignored" ;;
    esac
  done
}

# Phase 0 A/B of the RDP leg (docs/phase0-latency.md) without restarting the container: before each
# connect, an optional override file (the desktop's own /dev/shm, RAM) may set these keywords. Only
# KEY=VALUE lines with whitelisted keys and values are honoured; the file is never executed.
#   RDP_GFX=""|off|progressive|AVC444|AVC420|RFX  RDP_NETWORK=auto|lan  RDP_FRAME_ACK=on|off
#   RDP_GDI=sw|hw
# A variant = write the file, then TERM xfreerdp3: the loop reconnects with it a few seconds later.
load_overrides() {
  local file="${RDP_OVERRIDE_FILE:-/dev/shm/rdp-override}" line key value
  [[ -f "${file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ ! "${line}" =~ ^([A-Z_]+)=([A-Za-z0-9]*)$ ]]; then
      [[ -n "${line}" ]] && log "override ignored (not KEY=word): ${line}"
      continue
    fi
    key="${BASH_REMATCH[1]}" value="${BASH_REMATCH[2]}"
    case "${key}=${value}" in
      RDP_GFX= | RDP_GFX=off | RDP_GFX=progressive | RDP_GFX=AVC444 | RDP_GFX=AVC420 | RDP_GFX=RFX)
        RDP_GFX="${value}" ;;
      RDP_NETWORK=auto | RDP_NETWORK=lan) RDP_NETWORK="${value}" ;;
      RDP_FRAME_ACK=on | RDP_FRAME_ACK=off) RDP_FRAME_ACK="${value}" ;;
      RDP_GDI=sw | RDP_GDI=hw) RDP_GDI="${value}" ;;
      *) log "override ignored: ${key}=${value}" ;;
    esac
  done <"${file}"
}

# One argument per line for /args-from:stdin (which stops at the first blank line). printf is a
# bash builtin, so the password never appears in any process's argv.
build_args() {
  printf '%s\n' "/v:${WIN_HOST}:${RDP_PORT:-3389}" "/u:${RDP_USER}" "/p:${RDP_PASSWORD}"
  if [[ -n "${RDP_DOMAIN:-}" ]]; then printf '%s\n' "/d:${RDP_DOMAIN}"; fi
  if [[ -n "${RDP_CERT_SHA256:-}" ]]; then
    printf '%s\n' "/cert:deny,fingerprint:sha256:${RDP_CERT_SHA256}"
  else
    printf '%s\n' "/cert:ignore"
  fi
  # /f: sized to the Xvfb screen at (0,0) -- works without a window manager.
  # -toggle-fullscreen: Ctrl+Alt+Enter must not change the geometry the pipeline depends on.
  printf '%s\n' /f -toggle-fullscreen /kbd:layout:0x409 /audio-mode:2 \
    /log-level:INFO +auto-reconnect /auto-reconnect-max-retries:20
  clipboard_args
  drive_args
  # Codec knob for the Phase-0 fidelity/FPS/latency comparison. Passing any of /gfx /rfx /bpp
  # /network opts out of FreeRDP's autodetect (GFX + AVC444 + RFX), so empty passes none of them.
  # RDP_FRAME_ACK=off asks the server to stop waiting for frame acknowledgements (GFX only).
  local ack=""
  [[ "${RDP_FRAME_ACK:-on}" == off ]] && ack="frame-ack:off"
  case "${RDP_GFX:-}" in
    "") [[ -n "${ack}" ]] && printf '%s\n' "/gfx:${ack}" ;;
    off) printf '%s\n' -gfx /bpp:32 ;;
    progressive | AVC444 | AVC420 | RFX) printf '%s\n' "/gfx:${RDP_GFX}${ack:+,${ack}}" ;;
    *) log "unknown RDP_GFX='${RDP_GFX}', using autodetect" ;;
  esac
  [[ "${RDP_NETWORK:-auto}" == lan ]] && printf '%s\n' /network:lan
  [[ "${RDP_GDI:-sw}" == hw ]] && printf '%s\n' /gdi:hw
  return 0
}

main() {
  if [[ -z "${WIN_HOST:-}" || -z "${RDP_USER:-}" || -z "${RDP_PASSWORD:-}" ]]; then
    idle_forever "WIN_HOST / RDP_USER / RDP_PASSWORD not set: RDP disabled, display runs Xvfb-only."
  fi
  if [[ -z "${RDP_CERT_SHA256:-}" ]]; then
    log "WARNING: RDP_CERT_SHA256 unset -> /cert:ignore (no server identity check). Pin it in .env."
  fi

  local backoff=2 rc
  while true; do
    wait_for_x
    load_overrides
    log "connecting to ${WIN_HOST}:${RDP_PORT:-3389} as ${RDP_USER} (gfx=${RDP_GFX:-auto}" \
      "network=${RDP_NETWORK:-auto} frame-ack=${RDP_FRAME_ACK:-on} gdi=${RDP_GDI:-sw}" \
      "clipboard=${RDP_CLIPBOARD:-off} drives=${RDP_DRIVES:-none})"
    env -u RDP_PASSWORD xfreerdp3 /args-from:stdin < <(build_args)
    rc=$?
    case "${rc}" in
      0 | 1 | 2 | 3 | 4 | 11 | 12)
        log "session ended (exit ${rc}); reconnecting in 2s"
        backoff=2
        sleep 2
        ;;
      5)
        log "exit 5 DISCONNECTED_BY_OTHER_CONNECTION: someone else took the single session." \
          "Backing off 600s. Stop this stack if you are using the Windows host yourself."
        sleep 600
        ;;
      132 | 134 | 135 | 14[89] | 15[0-9])
        idle_forever "exit ${rc}: authentication/account failure. NOT retrying (Windows account" \
          "lockout risk). Fix RDP_* in .env, then: docker compose restart desktop"
        ;;
      1[6-9] | 2[0-6])
        idle_forever "exit ${rc}: licensing or command-line error. NOT retrying; see log above."
        ;;
      *)
        log "exit ${rc}; retrying in ${backoff}s"
        sleep "${backoff}"
        backoff=$((backoff * 2 > 60 ? 60 : backoff * 2))
        ;;
    esac
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
