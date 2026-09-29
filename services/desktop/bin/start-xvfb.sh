#!/usr/bin/env bash
# Xvfb on ${DISPLAY}. The socket lives in the shared /tmp/.X11-unix volume, so a socket left over from
# a previous container life must be removed first (the lock file lives in the container's own /tmp).
#
#   -nolisten tcp  : unix socket only -- reachable solely by containers that mount the volume
#   -ac            : no X access control; the volume mount IS the access boundary
#   -noreset       : keep the server up when the last client (e.g. xfreerdp) disconnects
set -euo pipefail

num="${DISPLAY#:}"
rm -f "/tmp/.X11-unix/X${num}" "/tmp/.X${num}-lock"

exec Xvfb "${DISPLAY}" -screen 0 "${XVFB_RESOLUTION}" -nolisten tcp -ac -noreset -dpi 96
