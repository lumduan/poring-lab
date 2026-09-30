#!/usr/bin/env bash
# Post-`up` smoke test for the core + remote profiles:
#   docker compose --profile core --profile remote up -d && scripts/smoke_test.sh
# Checks: every container healthy; rathena's LAN ports; backend/frontend/noVNC answer; >= 30 frames on
# /ws/stream with increasing frame ids; a mouse_move lands on the Xvfb pointer; the input log recorded
# it with source=human; rathena advertises HOST_LAN_IP. Works without Windows credentials (Xvfb-only).
#
#   scripts/smoke_test.sh --core   db + rathena only (dev mode: the production frontend isn't running)
#                                  and the Thai charset chain (database default charset tis620).
set -uo pipefail
cd "$(dirname "$0")/.."
core_only=false
[[ "${1:-}" == "--core" ]] && core_only=true
services=(db rathena desktop backend frontend)
$core_only && services=(db rathena)

HOST="$(sed -n 's/^HOST_LAN_IP=//p' .env)"
failures=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() {
  printf '  \033[31mFAIL\033[0m %s\n' "$*"
  failures=$((failures + 1))
}

echo "== containers healthy (up to 300 s; rathena's map-server loads for a while)"
for svc in "${services[@]}"; do
  state=""
  for _ in $(seq 1 150); do
    cid="$(docker compose ps -q "$svc" 2>/dev/null)"
    state="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo missing)"
    [[ "$state" == healthy ]] && break
    sleep 2
  done
  [[ "$state" == healthy ]] && pass "$svc healthy" || fail "$svc: $state"
done

echo "== rathena reachable on the LAN IP"
for port in 6900 6121 5121; do
  if timeout 3 bash -c "</dev/tcp/${HOST}/${port}" 2>/dev/null; then
    pass "${HOST}:${port} accepts TCP"
  else
    fail "${HOST}:${port} closed"
  fi
done
# Capture first: with pipefail, `logs | grep -q` fails when grep exits early and logs gets SIGPIPE.
rathena_logs="$(docker compose logs rathena 2>/dev/null)"
if grep -q "clients will be sent to char ${HOST}:6121 and map ${HOST}:5121" <<<"$rathena_logs"; then
  pass "rathena advertises ${HOST} for char/map"
else
  fail "rathena does not advertise ${HOST} (check conf/import rendering)"
fi

echo "== Thai charset chain"
charset="$(docker compose exec -T db sh -c 'MYSQL_PWD="$MARIADB_PASSWORD" mariadb -u"$MARIADB_USER" \
  -N -e "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=DATABASE()" \
  "$MARIADB_DATABASE"' 2>/dev/null | tr -d '\r')"
[[ "$charset" == tis620 ]] && pass "database charset tis620" || fail "database charset '${charset}' (want tis620)"

if $core_only; then
  echo
  if ((failures == 0)); then echo "SMOKE TEST (--core) PASSED"; else echo "SMOKE TEST (--core) FAILED: ${failures} check(s)"; exit 1; fi
  exit 0
fi

echo "== HTTP endpoints"
for url in "http://${HOST}:8000/health" "http://${HOST}:3000/api/health" "http://${HOST}:6080/vnc.html"; do
  if curl -fsS -o /dev/null --max-time 5 "$url"; then pass "$url"; else fail "$url"; fi
done
if curl -fsS --max-time 5 "http://${HOST}:8001/" -o /dev/null 2>/dev/null; then
  fail ":8001 (internal agent listener) is reachable from the LAN"
else
  pass ":8001 not published"
fi

echo "== stream + input round trip"
if uv run --quiet python scripts/ws_probe.py --backend "http://${HOST}:8000" --seconds 3 --min-frames 30 --input-probe; then
  pass "ws_probe"
else
  fail "ws_probe (see JSON above)"
fi

echo "== input log"
latest="$(ls -t data/input_log/*.jsonl 2>/dev/null | head -1)"
if [[ -n "$latest" ]] && grep -q '"source":"human".*"type":"mouse_move"' <<<"$(tail -n 50 "$latest")"; then
  pass "$latest has a human mouse_move record"
else
  fail "no human mouse_move in data/input_log/"
fi

echo
if ((failures == 0)); then
  echo "SMOKE TEST PASSED"
else
  echo "SMOKE TEST FAILED: ${failures} check(s)"
  exit 1
fi
