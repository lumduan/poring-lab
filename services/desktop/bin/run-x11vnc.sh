#!/usr/bin/env bash
# Debug viewer for the display. VIEW-ONLY by default: an interactive VNC client would be a third,
# unlogged input source that bypasses the input mux (ADR-0002). Set NOVNC_VIEW_ONLY=false only for
# emergency hands-on debugging. noVNC has NO authentication -- the port is LAN-only by design.
set -euo pipefail

until xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; do sleep 0.5; done

args=(-display "${DISPLAY}" -rfbport 5900 -localhost -forever -shared -nopw -quiet)
if [[ "${NOVNC_VIEW_ONLY:-true}" != "false" ]]; then
  args+=(-viewonly)
fi

exec x11vnc "${args[@]}"
