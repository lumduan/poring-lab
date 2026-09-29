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
set -uo pipefail

log() { printf '%s rdp-loop: %s\n' "$(date -Is)" "$*"; }

idle_forever() {
  log "$*"
  exec sleep infinity
}

if [[ -z "${WIN_HOST:-}" || -z "${RDP_USER:-}" || -z "${RDP_PASSWORD:-}" ]]; then
  idle_forever "WIN_HOST / RDP_USER / RDP_PASSWORD not set: RDP disabled, display runs Xvfb-only."
fi

wait_for_x() {
  until xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do sleep 0.5; done
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
  printf '%s\n' /f -toggle-fullscreen /kbd:layout:0x409 /audio-mode:2 -clipboard \
    /log-level:INFO +auto-reconnect /auto-reconnect-max-retries:20
  # Codec knob for the Phase-0 fidelity/FPS/latency comparison. Passing any of /gfx /rfx /bpp
  # /network opts out of FreeRDP's autodetect (GFX + AVC444 + RFX), so empty passes none of them.
  case "${RDP_GFX:-}" in
    "") ;;
    off) printf '%s\n' -gfx /bpp:32 ;;
    progressive | AVC444 | AVC420 | RFX) printf '%s\n' "/gfx:${RDP_GFX}" ;;
    *) log "unknown RDP_GFX='${RDP_GFX}', using autodetect" ;;
  esac
}

if [[ -z "${RDP_CERT_SHA256:-}" ]]; then
  log "WARNING: RDP_CERT_SHA256 unset -> /cert:ignore (no server identity check). Pin it in .env."
fi

backoff=2
while true; do
  wait_for_x
  log "connecting to ${WIN_HOST}:${RDP_PORT:-3389} as ${RDP_USER} (gfx=${RDP_GFX:-auto})"
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
