#!/usr/bin/env bash
# rAthena in one container: render conf/import from env, bootstrap the DB once, run login + char +
# map (+ optional web) and exit as soon as any of them dies so Docker restarts the whole set.
#
# THE LAN-CLIENT RULE: char_ip / map_ip are the addresses the servers ADVERTISE to game clients.
# They must be the Docker host's LAN IP (HOST_LAN_IP). Left unset, rAthena auto-detects the
# container's bridge IP (172.x) and every LAN client fails right after login. They are NOT bind
# addresses -- that IP does not exist inside the container, so never set bind_ip to it.
set -euo pipefail
cd /opt/rathena

log() { printf '%s rathena: %s\n' "$(date -Is)" "$*"; }
die() { log "FATAL: $*"; exit 64; }

: "${HOST_LAN_IP:?HOST_LAN_IP must be the Docker host LAN IP that game clients connect to}"
: "${DB_HOST:=db}" "${DB_PORT:=3306}"
: "${DB_NAME:?}" "${DB_USER:?}" "${DB_PASSWORD:?}"
: "${RATHENA_SERVER_USER:?}" "${RATHENA_SERVER_PASSWORD:?}"
: "${RATHENA_SERVER_NAME:=PoringLab}" "${RATHENA_NEW_ACCOUNT:=yes}" "${RATHENA_PINCODE:=no}"
: "${RATHENA_WEB_SERVER:=false}"

# rAthena's conf parser takes everything after "key: " to end of line, and the server account is
# also written into SQL below -- keep these to a safe charset instead of escaping them.
safe='^[A-Za-z0-9_.-]{4,64}$'
[[ "${DB_PASSWORD}" =~ ${safe} ]] || die "DB_PASSWORD must match ${safe}"
[[ "${RATHENA_SERVER_USER}" =~ ${safe} ]] || die "RATHENA_SERVER_USER must match ${safe}"
[[ "${RATHENA_SERVER_PASSWORD}" =~ ${safe} ]] || die "RATHENA_SERVER_PASSWORD must match ${safe}"
[[ "${RATHENA_SERVER_NAME}" =~ ^[A-Za-z0-9_.\ -]{1,20}$ ]] || die "RATHENA_SERVER_NAME: 1-20 plain chars"
[[ "${HOST_LAN_IP}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "HOST_LAN_IP must be an IPv4 address"

export HOST_LAN_IP DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD RATHENA_SERVER_USER \
  RATHENA_SERVER_PASSWORD RATHENA_SERVER_NAME RATHENA_NEW_ACCOUNT RATHENA_PINCODE
vars='${HOST_LAN_IP} ${DB_HOST} ${DB_PORT} ${DB_NAME} ${DB_USER} ${DB_PASSWORD}'
vars+=' ${RATHENA_SERVER_USER} ${RATHENA_SERVER_PASSWORD} ${RATHENA_SERVER_NAME}'
vars+=' ${RATHENA_NEW_ACCOUNT} ${RATHENA_PINCODE}'
for tmpl in conf-templates/*.txt.tmpl; do
  out="conf/import/$(basename "${tmpl}" .tmpl)"
  envsubst "${vars}" <"${tmpl}" >"${out}"
  log "rendered ${out}"
done
log "clients will be sent to char ${HOST_LAN_IP}:6121 and map ${HOST_LAN_IP}:5121 ($(tr '\n' ' ' <BUILD_INFO))"

# DB credentials via an option file, never argv.
umask 077
mycnf="$(mktemp)"
printf '[client]\nhost=%s\nport=%s\nuser=%s\npassword=%s\n' \
  "${DB_HOST}" "${DB_PORT}" "${DB_USER}" "${DB_PASSWORD}" >"${mycnf}"
sql() { mariadb --defaults-extra-file="${mycnf}" --batch --skip-column-names "${DB_NAME}" "$@"; }

until sql -e 'SELECT 1' >/dev/null 2>&1; do
  log "waiting for database ${DB_HOST}:${DB_PORT}"
  sleep 2
done

if [[ -z "$(sql -e "SHOW TABLES LIKE 'login'")" ]]; then
  log "empty database: importing schema"
  for f in main.sql web.sql roulette_default_data.sql logs.sql; do
    log "  sql-files/${f}"
    sql <"sql-files/${f}"
  done
fi

# Replace main.sql's insecure default server account (s1/p1) with ours. char and map log in to
# login with these exact credentials (conf/import/{char,map}_conf.txt).
sql -e "UPDATE login SET userid='${RATHENA_SERVER_USER}', user_pass='${RATHENA_SERVER_PASSWORD}' \
        WHERE account_id=1 AND sex='S'"
rm -f "${mycnf}"

pids=()
start() {
  log "starting $1"
  "./$1" &
  pids+=("$!")
}
shutdown() {
  log "signal received, stopping servers"
  kill -TERM "${pids[@]}" 2>/dev/null || true
  wait || true
  exit 0
}
trap shutdown TERM INT

start login-server
start char-server
start map-server
if [[ "${RATHENA_WEB_SERVER}" == "true" ]]; then start web-server; fi

set +e
wait -n "${pids[@]}"
rc=$?
log "a server exited (rc=${rc}); stopping the others so Docker restarts the set"
kill -TERM "${pids[@]}" 2>/dev/null
wait
exit $((rc == 0 ? 1 : rc))
