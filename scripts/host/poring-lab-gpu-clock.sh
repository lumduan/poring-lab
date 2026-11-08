#!/usr/bin/env bash
# poring-lab-gpu-clock.service's helper (installed as /usr/local/libexec/poring-lab-gpu-clock.sh).
#   start: every i915 GT's clock floor (rps_min_freq_mhz) := its RP0; waits up to 30 s for the card
#   stop:  the floor back to RPn (the driver's default)
# docs/planning/bot-server-migration.md 19.
set -u
mode="${1:-start}"
for _ in $(seq 30); do
    compgen -G '/sys/class/drm/card*/gt/gt0/rps_min_freq_mhz' >/dev/null && break
    sleep 1
done
n=0
for g in /sys/class/drm/card*/gt/gt0; do
    [ -w "$g/rps_min_freq_mhz" ] || continue
    if [ "$mode" = stop ]; then
        cat "$g/rps_RPn_freq_mhz" >"$g/rps_min_freq_mhz"
    else
        cat "$g/rps_RP0_freq_mhz" >"$g/rps_min_freq_mhz"
    fi
    echo "$g: floor $(cat "$g/rps_min_freq_mhz") MHz ($mode)"
    n=$((n + 1))
done
[ "$mode" = stop ] || [ "$n" -gt 0 ]
