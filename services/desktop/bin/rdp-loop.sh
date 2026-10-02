#!/usr/bin/env bash
# The ONE RDP session into the Windows host (ADR-0001), kept alive with an exit-code policy.
#
# Windows client editions allow a single interactive session: connecting kicks whoever is on it,
# and whoever connects next kicks us. So this loop must never fight a human for the session and
# must never hammer a bad password into an account-lockout policy.
#
# Exit codes come from FreeRDP's xf_exit_code_from_disconnect_reason(). The enum is identical in 3.15
# and 3.32.1 up to 159; 3.32 adds 160 CONNECT_TARGET_BOOTING and 161 HYBRID_REQUIRED_BY_SERVER, which
# fall to the backoff branch (diffed from the tagged sources, 2026-10-01):
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
# The capture-backend lock (ADR-0009, scripts/capture_backend.py) decides who owns the ONE Windows
# session: this loop connects only while it says `rdp`, and never while a Moonlight window is on the
# display (a second, independent interlock). Every wait wakes early when the lock changes.
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

# --- capture-backend lock ---------------------------------------------------------------------
# ${LAB_STATE_DIR:-/lab-state}/capture-backend, written only by scripts/capture_backend.py on the host
# (atomic rename; the directory is bind-mounted read-only). KEY=word lines:
#   BACKEND=rdp|console  SEQ=<n>  PHASE=steady|switching  OWNER=..  SINCE=..  REASON=..
# Sets LOCK_BACKEND (rdp | console | hold), LOCK_SEQ, LOCK_PHASE and LOCK_WHY. Fail-closed: no
# mounted directory, a malformed line, an unknown key or backend -> `hold`. A mounted directory
# without the file is the default, `rdp` (the lab before the lock existed).
read_lock() {
  local dir="${LAB_STATE_DIR:-/lab-state}" line key value backend="" seq="0" phase="steady"
  LOCK_BACKEND=hold LOCK_SEQ=0 LOCK_PHASE="" LOCK_WHY=""
  if [[ ! -d "${dir}" ]]; then
    LOCK_WHY="lock directory ${dir} is not mounted"
    return 0
  fi
  if [[ ! -e "${dir}/capture-backend" ]]; then
    LOCK_BACKEND=rdp LOCK_PHASE=steady LOCK_WHY="no lock file: default rdp"
    return 0
  fi
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ ! "${line}" =~ ^([A-Z_]+)=([A-Za-z0-9_.:-]*)$ ]]; then
      LOCK_WHY="malformed lock line: ${line:0:60}"
      return 0
    fi
    key="${BASH_REMATCH[1]}" value="${BASH_REMATCH[2]}"
    case "${key}" in
      BACKEND) backend="${value}" ;;
      SEQ)
        [[ "${value}" =~ ^[0-9]+$ ]] || { LOCK_WHY="SEQ='${value}' is not a number"; return 0; }
        seq="${value}" ;;
      PHASE)
        [[ "${value}" == steady || "${value}" == switching ]] || {
          LOCK_WHY="PHASE='${value}' is not steady|switching"
          return 0
        }
        phase="${value}" ;;
      OWNER | SINCE | REASON) ;;
      *) LOCK_WHY="unknown lock key ${key}"; return 0 ;;
    esac
  done <"${dir}/capture-backend"
  case "${backend}" in
    rdp | console) LOCK_BACKEND="${backend}" LOCK_SEQ="${seq}" LOCK_PHASE="${phase}" ;;
    *) LOCK_WHY="BACKEND='${backend}' is not rdp|console" ;;
  esac
  return 0
}

# Changes whenever the lock is rewritten (atomic rename = new inode) or appears/disappears.
lock_stamp() {
  stat -c '%i.%Y.%s' "${LAB_STATE_DIR:-/lab-state}/capture-backend" 2>/dev/null || echo none
}

# sleep N seconds, but return early (status 0) as soon as the lock changes.
nap() {
  local n="$1" stamp i
  stamp="$(lock_stamp)"
  for ((i = 0; i < n; i++)); do
    sleep 1
    if [[ "$(lock_stamp)" != "${stamp}" ]]; then
      log "capture-backend lock changed: waking early"
      return 0
    fi
  done
  return 0
}

# The second interlock: a Moonlight (gamestream) window on this display means the console backend
# is streaming, whatever the lock file says. (xwininfo -tree prints `("class" "Class")` per window.)
stream_client_present() {
  xwininfo -root -tree -display "${DISPLAY}" 2>/dev/null | grep -qiE '\("moonlight"'
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
#   RDP_GFX=""|off|progressive|AVC444|AVC420|AVCthin|RFX  RDP_NETWORK=auto|lan  RDP_FRAME_ACK=on|off
#   RDP_GDI=sw|hw
# A variant = write the file, then TERM xfreerdp3: the loop reconnects with it a few seconds later.
load_overrides() {
  local file="${RDP_OVERRIDE_FILE:-/dev/shm/rdp-override}" line key value
  # Every connect starts from the container's own settings: a key missing from the file (or no
  # file at all) means "back to the default", never "keep the previous override".
  RDP_GFX="${BASE_RDP_GFX-}" RDP_NETWORK="${BASE_RDP_NETWORK-auto}"
  RDP_FRAME_ACK="${BASE_RDP_FRAME_ACK-on}" RDP_GDI="${BASE_RDP_GDI-sw}"
  [[ -f "${file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ ! "${line}" =~ ^([A-Z_]+)=([A-Za-z0-9]*)$ ]]; then
      [[ -n "${line}" ]] && log "override ignored (not KEY=word): ${line}"
      continue
    fi
    key="${BASH_REMATCH[1]}" value="${BASH_REMATCH[2]}"
    case "${key}=${value}" in
      RDP_GFX= | RDP_GFX=off | RDP_GFX=progressive | RDP_GFX=AVC444 | RDP_GFX=AVC420 | \
        RDP_GFX=AVCthin | RDP_GFX=RFX)
        RDP_GFX="${value}" ;;
      RDP_NETWORK=auto | RDP_NETWORK=lan) RDP_NETWORK="${value}" ;;
      RDP_FRAME_ACK=on | RDP_FRAME_ACK=off) RDP_FRAME_ACK="${value}" ;;
      RDP_GDI=sw | RDP_GDI=hw) RDP_GDI="${value}" ;;
      *) log "override ignored: ${key}=${value}" ;;
    esac
  done <"${file}"
}

override_mtime() {
  stat -c %Y "${RDP_OVERRIDE_FILE:-/dev/shm/rdp-override}" 2>/dev/null || echo none
}

# X keyboard focus back to PointerRoot, a fresh Xvfb's default: keys go to the window under the
# pointer, which the backend keeps inside the session. SDL (Moonlight, console mode) focuses its own
# window with RevertToNone, so after a stream the focus was None and every key vanished (2026-10-02).
# /f took the focus itself on EnterNotify; the windowed /size mode expects a WM, and there is none.
# python3 + ctypes: this image has libX11 (xfreerdp) but no xdotool or python-xlib.
focus_pointer_root() {
  python3 - <<'PY' || log "could not reset the X keyboard focus to PointerRoot"
import ctypes, ctypes.util
x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
dpy = x11.XOpenDisplay(None)
if not dpy:
    raise SystemExit(1)
x11.XSetInputFocus(dpy, 1, 1, 0)  # PointerRoot, RevertToPointerRoot, CurrentTime
x11.XSync(dpy, 0)
x11.XCloseDisplay(dpy)
PY
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
  # Geometry (no window manager either way). SESSION_SIZE set: the session is drawn 1:1 at the
  # canvas' top-left, /size at 0,0 -- the canvas is larger so Moonlight's console-mode window can open
  # at native size (ADR-0009 amendment, 2026-10-02). Unset: /f, sized to the whole Xvfb screen.
  # -toggle-fullscreen: Ctrl+Alt+Enter must not change the geometry the pipeline depends on.
  if [[ -n "${SESSION_SIZE:-}" ]]; then
    printf '%s\n' "/size:${SESSION_SIZE}" /window-position:0x0 -decorations
  else
    printf '%s\n' /f
  fi
  printf '%s\n' -toggle-fullscreen /kbd:layout:0x409 /audio-mode:2 \
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
    # AVCthin: AVC with the 10.3 AVC_THINCLIENT capability flag -- caps restricted to 10.3 (mask
    # = every other version filtered), AVC444 on so AVC is not disabled, thin-client on. Windows
    # answers with full-screen AVC (event 162: 0xA0301, profile 2048) and, unlike AVC444 on 10.7,
    # a short latency tail (docs/h264-plan.md, 2026-10-01). FreeRDP 3.15 only sends 10.x caps
    # while AVC444 is on, and a plain AVC420 request (8.1 caps) got "AVC available: 0".
    AVCthin) printf '%s\n' "/gfx:AVC444:on,thin-client:on,mask:2015${ack:+,${ack}}" ;;
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
  if [[ -n "${SESSION_SIZE:-}" && ! "${SESSION_SIZE}" =~ ^[1-9][0-9]*x[1-9][0-9]*$ ]]; then
    idle_forever "SESSION_SIZE='${SESSION_SIZE:0:20}' is not WxH: NOT connecting (fix .env, recreate)."
  fi
  if [[ -z "${RDP_CERT_SHA256:-}" ]]; then
    log "WARNING: RDP_CERT_SHA256 unset -> /cert:ignore (no server identity check). Pin it in .env."
  fi

  BASE_RDP_GFX="${RDP_GFX:-}" BASE_RDP_NETWORK="${RDP_NETWORK:-auto}"
  BASE_RDP_FRAME_ACK="${RDP_FRAME_ACK:-on}" BASE_RDP_GDI="${RDP_GDI:-sw}"
  local backoff=2 rc override_stamp held="" stream_noted=""
  while true; do
    wait_for_x
    read_lock
    if [[ "${LOCK_BACKEND}" != rdp ]]; then
      if [[ "${held}" != "${LOCK_BACKEND}:${LOCK_SEQ}:${LOCK_WHY}" ]]; then
        log "capture-backend ${LOCK_BACKEND} seq=${LOCK_SEQ}: holding (no RDP connect)" \
          "${LOCK_WHY:+-- ${LOCK_WHY}}"
        held="${LOCK_BACKEND}:${LOCK_SEQ}:${LOCK_WHY}"
      fi
      nap 30
      continue
    fi
    if stream_client_present; then
      if [[ -z "${stream_noted}" ]]; then
        log "a Moonlight window is on ${DISPLAY}: holding although the lock says rdp" \
          "(second interlock; run scripts/capture_backend.py to-rdp --recover)"
        stream_noted=1
      fi
      nap 10
      continue
    fi
    if [[ -n "${held}" || -n "${stream_noted}" ]]; then
      log "capture-backend rdp seq=${LOCK_SEQ}: resuming"
      held="" stream_noted=""
    fi
    load_overrides
    override_stamp="$(override_mtime)"
    log "connecting to ${WIN_HOST}:${RDP_PORT:-3389} as ${RDP_USER} (gfx=${RDP_GFX:-auto}" \
      "network=${RDP_NETWORK:-auto} frame-ack=${RDP_FRAME_ACK:-on} gdi=${RDP_GDI:-sw}" \
      "clipboard=${RDP_CLIPBOARD:-off} drives=${RDP_DRIVES:-none})"
    focus_pointer_root
    env -u RDP_PASSWORD xfreerdp3 /args-from:stdin < <(build_args)
    rc=$?
    case "${rc}" in
      0 | 1 | 2 | 3 | 4 | 11 | 12)
        log "session ended (exit ${rc}); reconnecting in 2s"
        backoff=2
        nap 2
        ;;
      5)
        log "exit 5 DISCONNECTED_BY_OTHER_CONNECTION: someone else took the single session." \
          "Backing off 600s (or until the capture-backend lock changes). Stop this stack if you" \
          "are using the Windows host yourself."
        nap 600
        ;;
      132 | 134 | 135 | 14[89] | 15[0-9])
        idle_forever "exit ${rc}: authentication/account failure. NOT retrying (Windows account" \
          "lockout risk). Fix RDP_* in .env, then: python3 scripts/guarded_build.py --sustain 30" \
          "--spike 25 restart:desktop@90"
        ;;
      1[6-9] | 2[0-6])
        idle_forever "exit ${rc}: licensing or command-line error. NOT retrying; see log above."
        ;;
      *)
        if [[ "$(override_mtime)" != "${override_stamp}" ]]; then
          # A deliberate switch (the override file changed, then xfreerdp was TERMed): not a
          # failing target, so no backoff growth.
          log "exit ${rc} after an override change; reconnecting in 2s"
          backoff=2
          nap 2
          continue
        fi
        log "exit ${rc}; retrying in ${backoff}s"
        nap "${backoff}"
        backoff=$((backoff * 2 > 60 ? 60 : backoff * 2))
        ;;
    esac
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
