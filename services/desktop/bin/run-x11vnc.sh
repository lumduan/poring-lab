#!/usr/bin/env bash
# Debug viewer for the display. VIEW-ONLY by default: an interactive VNC client would be a third,
# unlogged input source that bypasses the input mux (ADR-0002). Set NOVNC_VIEW_ONLY=false only for
# emergency hands-on debugging. noVNC has NO authentication -- the port is LAN-only by design.
set -euo pipefail

until xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do sleep 0.5; done

# -nosel: no selection/clipboard exchange with VNC viewers at all. Otherwise x11vnc reads the X
# CLIPBOARD whenever it changes -- including the text of a human paste while the backend owns it
# (ADR-0004) -- and relays it to every (unauthenticated) noVNC viewer.
args=(-display "${DISPLAY}" -rfbport 5900 -localhost -forever -shared -nopw -quiet -nosel)
if [[ "${NOVNC_VIEW_ONLY:-true}" != "false" ]]; then
  args+=(-viewonly)
fi

exec x11vnc "${args[@]}"
