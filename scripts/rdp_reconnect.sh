#!/usr/bin/env bash
# Reconnect the ONE RDP session (ADR-0001) with an optional codec override, safely.
#
#   scripts/rdp_reconnect.sh [KEYWORD|-]            # e.g. progressive | AVCthin | AVC444 | - (no override)
#   scripts/rdp_reconnect.sh --reload [KEYWORD|-]   # also restart rdp-loop (re-reads an edited script)
#
# The override goes to the desktop's RAM file (/dev/shm/rdp-override, whitelisted keywords only, see
# rdp-loop.sh); the client is TERMed and rdp-loop reconnects. With --reload, rdp-loop itself is
# stopped through supervisord and restarted only once ZERO client processes remain -- never two
# sessions. In FreeRDP 3.32 the binary is `xfreerdp` and `xfreerdp3` is a link to it; comm follows the
# name it was exec'd by, so rdp-loop's client still shows as `xfreerdp3` (verified 2026-10-01) -- but
# both names count, so a client started any other way is never missed. Prints the new connect line
# and the process count; exits 1 if it isn't exactly 1.
set -euo pipefail
C=poring-lab-desktop-1
SUP=(supervisorctl -c /etc/supervisor/supervisord.conf)
reload=false
[[ "${1:-}" == --reload ]] && { reload=true; shift; }
kw="${1:--}"
[[ "${kw}" == - || "${kw}" =~ ^[A-Za-z0-9]+$ ]] || { echo "bad keyword ${kw}" >&2; exit 2; }

count() {
  docker exec "${C}" sh -c 'n=0; for p in /proc/[0-9]*; do case "$(cat $p/comm 2>/dev/null)" in
    xfreerdp|xfreerdp3) n=$((n+1));; esac; done; echo $n'
}
term_clients() {
  docker exec "${C}" sh -c 'for p in /proc/[0-9]*; do case "$(cat $p/comm 2>/dev/null)" in
    xfreerdp|xfreerdp3) kill -TERM "${p#/proc/}";; esac; done; true'
}

if [[ "${kw}" == - ]]; then
  docker exec "${C}" rm -f /dev/shm/rdp-override
else
  docker exec "${C}" sh -c "printf 'RDP_GFX=%s\n' '${kw}' > /dev/shm/rdp-override"
fi
since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if ${reload}; then
  docker exec "${C}" "${SUP[@]}" stop rdp >/dev/null
  term_clients
  for _ in $(seq 1 40); do [[ "$(count)" == 0 ]] && break; sleep 0.5; done
  [[ "$(count)" == 0 ]] || { echo "client still running after stop: NOT starting a second one" >&2; exit 1; }
  docker exec "${C}" "${SUP[@]}" start rdp >/dev/null
else
  term_clients
fi
for _ in $(seq 1 40); do
  docker logs --since "${since}" "${C}" 2>&1 | grep -q "connecting to" && break
  sleep 0.5
done
sleep 8
docker logs --since "${since}" "${C}" 2>&1 | grep "connecting to" | tail -1 | sed 's/.*(gfx=/gfx=/'
n="$(count)"
echo "client processes: ${n}"
[[ "${n}" == 1 ]]
