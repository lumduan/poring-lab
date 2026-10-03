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

# --- clean-room variants (ADR-0009, Batt 2026-10-03) ---------------------------------------------
# ${LAB_STATE_DIR}/gamestream-variant, written only by scripts/capture_backend.py `stream --variant`
# (atomic rename; read-only here). KEY=word lines, every value WHITELISTED:
#   CLIENT=moonlight-qt|s2spike   WM=none|openbox   GDB_AFTER_S=<seconds>|(empty)   PAINT=x11|bus
#   S2 (2026-10-03): INPUT=x11|socket, and the key->paint tail experiments' knobs (s2spike only):
#   FPS=30|60   EVIDENCE=inline|thread   DECODE_THREADS=1|2|4
# Missing file or anything invalid -> the V1 defaults (moonlight-qt, no WM, no gdb), logged.
variant_defaults() {
  VARIANT_CLIENT=moonlight-qt VARIANT_WM=none VARIANT_GDB="" VARIANT_PAINT=x11 VARIANT_INPUT=x11
  VARIANT_FPS="" VARIANT_EVIDENCE=inline VARIANT_DECODE_THREADS=2
}

read_variant() {
  local file="${LAB_STATE_DIR:-/lab-state}/gamestream-variant" line key value
  variant_defaults
  VARIANT_WHY=""
  [[ -e "${file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ ! "${line}" =~ ^([A-Z_]+)=([A-Za-z0-9_.-]*)$ ]]; then
      variant_defaults
      VARIANT_WHY="malformed variant line: ${line:0:60} (defaults)"
      return 0
    fi
    key="${BASH_REMATCH[1]}" value="${BASH_REMATCH[2]}"
    case "${key}=${value}" in
      CLIENT=moonlight-qt | CLIENT=s2spike) VARIANT_CLIENT="${value}" ;;
      WM=none | WM=openbox) VARIANT_WM="${value}" ;;
      PAINT=x11 | PAINT=bus) VARIANT_PAINT="${value}" ;;
      INPUT=x11 | INPUT=socket) VARIANT_INPUT="${value}" ;;
      FPS=30 | FPS=60) VARIANT_FPS="${value}" ;;
      EVIDENCE=inline | EVIDENCE=thread) VARIANT_EVIDENCE="${value}" ;;
      DECODE_THREADS=1 | DECODE_THREADS=2 | DECODE_THREADS=4) VARIANT_DECODE_THREADS="${value}" ;;
      GDB_AFTER_S=) VARIANT_GDB="" ;;
      *)
        if [[ "${key}" == GDB_AFTER_S && "${value}" =~ ^[0-9]{1,4}$ ]]; then
          VARIANT_GDB="${value}"
        else
          variant_defaults
          VARIANT_WHY="invalid variant ${key}=${value:0:30} (defaults)"
          return 0
        fi
        ;;
    esac
  done <"${file}"
  return 0
}

# The lock's REASON (read_lock above must stay byte-identical to rdp-loop's, so this is separate).
# A `cleanroom*` reason makes each stream ONE-SHOT: when the client exits, wait for the next lock
# change instead of relaunching, so a crashing client can never loop /launch on Sunshine.
lock_reason() {
  local line
  LOCK_REASON=""
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" =~ ^REASON=([A-Za-z0-9_.:-]*)$ ]] && LOCK_REASON="${BASH_REMATCH[1]}"
  done 2>/dev/null <"${LAB_STATE_DIR:-/lab-state}/capture-backend"
  return 0
}

# V2: openbox around the client only (rc.xml: no decorations, no resize, NO key/mouse bindings).
# Its config and data live in /tmp, never in ~/.config (the pairing volume).
start_wm() {
  wm=""
  [[ "${VARIANT_WM}" == openbox ]] || return 0
  mkdir -p /tmp/xdg-openbox /tmp/xdg-data
  XDG_CONFIG_HOME=/tmp/xdg-openbox XDG_DATA_HOME=/tmp/xdg-data \
    openbox --config-file /opt/openbox/rc.xml --sm-disable >/tmp/openbox.log 2>&1 &
  wm=$!
  sleep 1
  log "clean-room V2: openbox (pid ${wm}) manages ${DISPLAY} for this stream only"
}

stop_wm() {
  [[ -n "${wm:-}" ]] || return 0
  kill "${wm}" 2>/dev/null
  wait "${wm}" 2>/dev/null
  log "openbox stopped"
  wm=""
}

# V3: the S2 spike (services/gamestream/s2spike), decoding in-process. Its X window is a spike-only
# shim (x11_mirror_shim.py) so the console, rdp-loop's interlock and /health can see it.
# V3b (PAINT=bus): decoded frames go to the frame bus, never into Xvfb; the window only takes input.
# S2 (PAINT=bus INPUT=socket, step 3): input comes from the backend's mux over the s2-input socket;
# no X window takes part (an unmapped presence marker keeps the interlocks).
run_s2spike() {
  local view=(--mirror-x)
  if [[ "${VARIANT_PAINT:-x11}" == bus ]]; then
    view=(--framebus "${FRAMEBUS_RING:-/framebus/ring}")
    if [[ "${VARIANT_INPUT:-x11}" == socket ]]; then
      view+=(--input-socket "${S2_INPUT_SOCKET:-/s2-input/input.sock}")
    fi
  fi
  python3 -m s2spike stream --host "${WIN_HOST}" --app "${GAMESTREAM_APP:-Desktop}" \
    --size "$(stream_size)" --fps "${VARIANT_FPS:-${GAMESTREAM_FPS:-30}}" \
    --bitrate "${GAMESTREAM_BITRATE_KBPS:-20000}" --evidence "${VARIANT_EVIDENCE:-inline}" \
    --decode-threads "${VARIANT_DECODE_THREADS:-2}" "${view[@]}"
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
    # The stream window is titled "<host> - Moonlight" (class com.moonlight_stream.Moonlight);
    # Moonlight's own Qt windows are skipped by size below anyway.
    for wid in $(xdotool search --onlyvisible --class 'moonlight' 2>/dev/null); do
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

# X keyboard focus back to PointerRoot after a stream. SDL focuses Moonlight's window with
# RevertToNone, so when it closed the focus became None and every key to the next RDP session
# vanished (2026-10-02). A COPY of rdp-loop.sh's (tests/test_capture_lock.py keeps them equal).
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

# The pid of a process by its comm name (no procps in this image).
pid_of() {
  local p
  for p in /proc/[0-9]*; do
    [[ "$(cat "${p}/comm" 2>/dev/null)" == "$1" ]] && { printf '%s\n' "${p#/proc/}"; return 0; }
  done
  return 1
}

# Moonlight, or -- diagnostics only, GAMESTREAM_GDB_AFTER_S=N -- Moonlight launched BY gdb (with
# ptrace_scope 1 only a parent may trace), which dumps every thread's stack N s into the stream and
# lets it run on. For the start-up stall of 2026-10-02: the main thread parked in a futex, nothing
# presented, with either SDL renderer (opengl/llvmpipe and software).
run_moonlight() {
  local bin gdb
  bin="$(readlink -f "${MOONLIGHT_DIR:-/tmp/moonlight}/AppRun")"
  gdb="$(command -v gdb || command -v gdb-minimal)"
  if [[ ! "${GAMESTREAM_GDB_AFTER_S:-}" =~ ^[0-9]+$ || -z "${gdb}" ]]; then
    "${bin}" "$@"
    return
  fi
  log "DIAGNOSTICS: Moonlight under gdb; thread stacks after ${GAMESTREAM_GDB_AFTER_S}s"
  (
    sleep "${GAMESTREAM_GDB_AFTER_S}"
    pid="$(pid_of moonlight)" && kill -INT "${pid}"
  ) &
  "${gdb}" -q -batch -nx -ex 'set pagination off' -ex 'set print thread-events off' \
    -ex 'handle SIGPIPE SIGUSR1 SIGUSR2 SIGTERM SIGCHLD SIGALRM nostop noprint pass' \
    -ex run -ex 'info threads' -ex 'thread apply all bt 40' -ex continue \
    --args "${bin}" "$@"
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
  local backoff=2 rc held="" rdp_noted="" started placer stamp wm=""
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
    read_variant
    lock_reason
    [[ -n "${VARIANT_WHY}" ]] && log "${VARIANT_WHY}"
    log "capture-backend console seq=${LOCK_SEQ}: streaming ${WIN_HOST} at" \
      "$(stream_size)@${GAMESTREAM_FPS:-30} (client=${VARIANT_CLIENT} wm=${VARIANT_WM}" \
      "gdb=${VARIANT_GDB:-off} paint=${VARIANT_PAINT} input=${VARIANT_INPUT}" \
      "fps=${VARIANT_FPS:-default} evidence=${VARIANT_EVIDENCE}" \
      "decode_threads=${VARIANT_DECODE_THREADS} reason=${LOCK_REASON:-none})"
    started=$(date +%s)
    stamp="$(lock_stamp)"
    mapfile -t args < <(stream_args)
    start_wm
    placer=""
    # Under openbox (V2) the WM places the window at 0,0 (rc.xml). xdotool then reports it
    # relative to openbox's frame, and the placer "moved" it several times a second, forever.
    if [[ "${VARIANT_WM}" != openbox ]]; then
      place_stream &
      placer=$!
    fi
    if [[ "${VARIANT_CLIENT}" == s2spike ]]; then
      run_s2spike
    else
      GAMESTREAM_GDB_AFTER_S="${VARIANT_GDB:-${GAMESTREAM_GDB_AFTER_S:-}}" \
        run_moonlight "${args[@]}"
    fi
    rc=$?
    if [[ -n "${placer}" ]]; then
      kill "${placer}" 2>/dev/null
      wait "${placer}" 2>/dev/null
    fi
    stop_wm
    focus_pointer_root
    if [[ "${LOCK_REASON}" == cleanroom* ]]; then
      log "${VARIANT_CLIENT} exited (rc=${rc}); clean room: one-shot, waiting for a lock change"
      while [[ "$(lock_stamp)" == "${stamp}" ]]; do nap 30; done
      continue
    fi
    if (($(date +%s) - started > 60)); then backoff=2; fi
    log "moonlight exited (rc=${rc}); next attempt in ${backoff}s (or when the lock changes)"
    nap "${backoff}"
    backoff=$((backoff * 2 > 60 ? 60 : backoff * 2))
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
