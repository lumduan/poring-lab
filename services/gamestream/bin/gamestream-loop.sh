#!/usr/bin/env bash
# The console-mode stream client (ADR-0009): moonlight-qt shows the Sunshine stream of the Windows
# CONSOLE session in the lab's Xvfb :99 -- the mirror image of rdp-loop.sh.
#
# It streams only while the capture-backend lock says `console` AND no xfreerdp window is on the
# display (the second, independent interlock); otherwise it naps, waking when the lock changes. It
# never exits (restart: unless-stopped would loop), never fights: every failure backs off.
#   moonlight-qt flags: windowed at the stream's own size, then MOVED (never resized) to the session
#   area at the canvas' top-left (place_stream, SESSION_SIZE), --absolute-mouse (XTest positions ->
#   LiSendMousePositionEvent), software H.264 decode, --game-optimization (lets Sunshine set the
#   console to the stream's size), audio stays on the PC.
#
# The lock functions below are a COPY of rdp-loop.sh's (tests/test_capture_lock.py keeps them in
# lock-step).
set -uo pipefail

log() { printf '%s gamestream: %s\n' "$(date -Is)" "$*" >&2; }

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

# The second interlock: an xfreerdp window means the RDP backend owns the session.
rdp_client_present() {
  xwininfo -root -tree -display "${DISPLAY}" 2>/dev/null | grep -qiE '\("xfreerdp"'
}

# The shared X socket is mounted at /x11 (read-only); a private /tmp/.X11-unix also hosts the
# pairing display :50 (scripts/capture_backend.py pair).
setup_display() {
  [[ -e /x11 ]] || return 0 # not in the container (tests): nothing to link
  mkdir -p /tmp/.X11-unix "${XDG_CACHE_HOME:-/tmp/cache}"
  install -d -m 0700 "${XDG_RUNTIME_DIR:-/tmp/xdg}"  # Qt wants 0700
  ln -sfn /x11/X99 /tmp/.X11-unix/X99
}

# The stream window, 1:1 at the session area (ADR-0009 amendment, 2026-10-02). Without a window
# manager Moonlight's windowed mode opens at the stream's own size only when that is under 80 % of
# the screen in both directions, centred -- hence the 1920x1200 canvas around the 1440x900 session.
# This MOVES that window to 0,0 and never resizes it: Moonlight drops resize events while it builds
# its renderer, and a resize during start-up (by script, or by a kiosk WM) left it black
# (2026-10-02). A move changes only where the window is drawn. Runs in the background for the
# stream's lifetime (a re-created window is moved again) and logs each window geometry it sees once.
stream_size() {
  printf '%s\n' "${GAMESTREAM_RESOLUTION:-${SESSION_SIZE:-1440x900}}"
}

# "x y w h" of a window from `xdotool getwindowgeometry --shell` (parsed, never eval'd).
window_geometry() {
  local out re=$'(^|\n)X=(-?[0-9]+)\nY=(-?[0-9]+)\nWIDTH=([0-9]+)\nHEIGHT=([0-9]+)'
  out="$(xdotool getwindowgeometry --shell "$1" 2>/dev/null)" || return 1
  [[ "${out}" =~ ${re} ]] || return 1
  printf '%s %s %s %s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" \
    "${BASH_REMATCH[5]}"
}

place_stream() {
  local want wid x y w h seen=" "
  want="$(stream_size)"
  while sleep 0.2; do
    for wid in $(xdotool search --onlyvisible --name '^Moonlight$' 2>/dev/null); do
      read -r x y w h < <(window_geometry "${wid}") || continue
      if [[ "${seen}" != *" ${wid}:${w}x${h}+${x}+${y} "* ]]; then
        log "Moonlight window ${wid}: ${w}x${h}+${x}+${y} (stream ${want})"
        seen+="${wid}:${w}x${h}+${x}+${y} "
      fi
      if [[ "${w}x${h}" == "${want}" && "${x}+${y}" != "0+0" ]]; then
        xdotool windowmove "${wid}" 0 0 && log "moved the stream window ${wid} to 0,0"
      fi
    done
  done
}

stream_args() {
  printf '%s\n' stream "${WIN_HOST}" "${GAMESTREAM_APP:-Desktop}" \
    --resolution "$(stream_size)" --fps "${GAMESTREAM_FPS:-30}" \
    --bitrate "${GAMESTREAM_BITRATE_KBPS:-20000}" --video-codec H.264 --video-decoder software \
    --display-mode windowed --absolute-mouse --game-optimization --audio-on-host \
    --no-vsync --no-frame-pacing --no-quit-after --capture-system-keys never \
    --no-performance-overlay
}

main() {
  if [[ -z "${WIN_HOST:-}" ]]; then
    log "WIN_HOST is not set: no stream, idling."
    exec sleep infinity
  fi
  setup_display
  gamestream-unpack || { log "could not unpack moonlight-qt: idling"; exec sleep infinity; }
  local backoff=2 rc held="" rdp_noted="" started placer
  while true; do
    wait_for_x
    read_lock
    # Stream only on console/STEADY: during the switch the session is not on the console yet, and
    # Sunshine can't apply its display settings (VDD only, resolution) without a console session --
    # a stream started early captured an empty, black display (2026-10-02).
    if [[ "${LOCK_BACKEND}" != console || "${LOCK_PHASE}" != steady ]]; then
      local why="${LOCK_WHY}"
      if [[ "${LOCK_BACKEND}" == console ]]; then
        why="phase ${LOCK_PHASE:-unset}: the session is not on the console yet"
      fi
      if [[ "${held}" != "${LOCK_BACKEND}:${LOCK_SEQ}:${why}" ]]; then
        log "capture-backend ${LOCK_BACKEND} seq=${LOCK_SEQ}: holding (no stream)" "${why:+-- ${why}}"
        held="${LOCK_BACKEND}:${LOCK_SEQ}:${why}"
      fi
      nap 30
      continue
    fi
    if rdp_client_present; then
      if [[ -z "${rdp_noted}" ]]; then
        log "an xfreerdp window is on ${DISPLAY}: holding although the lock says console" \
          "(second interlock)"
        rdp_noted=1
      fi
      nap 5
      continue
    fi
    held="" rdp_noted=""
    log "capture-backend console seq=${LOCK_SEQ}: streaming ${WIN_HOST} at" \
      "$(stream_size)@${GAMESTREAM_FPS:-30}"
    started=$(date +%s)
    mapfile -t args < <(stream_args)
    place_stream &
    placer=$!
    "${MOONLIGHT_DIR:-/tmp/moonlight}/AppRun" "${args[@]}"
    rc=$?
    kill "${placer}" 2>/dev/null
    wait "${placer}" 2>/dev/null
    if (($(date +%s) - started > 60)); then backoff=2; fi
    log "moonlight exited (rc=${rc}); next attempt in ${backoff}s (or when the lock changes)"
    nap "${backoff}"
    backoff=$((backoff * 2 > 60 ? 60 : backoff * 2))
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
