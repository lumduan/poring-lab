#!/usr/bin/env bash
# Healthy = the X display answers and noVNC is listening. The RDP session is deliberately NOT part
# of health: the stack must run (Xvfb-only) without Windows credentials. RDP state is visible as
# `rdp_window_present` in the backend's /health and status messages.
set -euo pipefail
xdpyinfo -display "${DISPLAY:-:99}" >/dev/null 2>&1
exec 3<>/dev/tcp/127.0.0.1/6080
