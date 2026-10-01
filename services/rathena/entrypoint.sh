#!/usr/bin/env bash
# rAthena in one container: render conf/import from env, bootstrap the DB once, run login + char +
# map (+ optional web) and exit as soon as any of them dies so Docker restarts the whole set.
#
# THE LAN-CLIENT RULE: char_ip / map_ip are the addresses the servers ADVERTISE to game clients.
# They must be the Docker host's LAN IP (HOST_LAN_IP). Left unset, rAthena auto-detects the
# container's bridge IP (172.x) and every LAN client fails right after login. They are NOT bind
# addresses -- that IP does not exist inside the container, so never set bind_ip to it.
set -euo pipefail

log() { printf '%s rathena: %s\n' "$(date -Is)" "$*"; }
die() { log "FATAL: $*"; exit 64; }

# THE DISK RULE: the runtime tree (~1600 files) ships as ONE tar and is extracted into a tmpfs at
# every start (compose.yaml mounts /opt/rathena as tmpfs), so it never becomes per-file metadata on
# the shared host disk. Persistent state lives only in MariaDB.
rt=/opt/rathena
if ! grep -qs " ${rt} tmpfs " /proc/mounts; then
  log "WARNING: ${rt} is not a tmpfs; the runtime tree is being written to disk"
fi
tar -C "${rt}" -xf /opt/rathena-runtime.tar
log "runtime extracted into ${rt}: $(du -sm "${rt}" | cut -f1) MiB in ${SECONDS}s"
cd "${rt}"

: "${HOST_LAN_IP:?HOST_LAN_IP must be the Docker host LAN IP that game clients connect to}"
: "${DB_HOST:=db}" "${DB_PORT:=3306}"
: "${DB_NAME:?}" "${DB_USER:?}" "${DB_PASSWORD:?}"
: "${RATHENA_SERVER_USER:?}" "${RATHENA_SERVER_PASSWORD:?}"
: "${RATHENA_SERVER_NAME:=PoringLab}" "${RATHENA_NEW_ACCOUNT:=yes}" "${RATHENA_PINCODE:=no}"
: "${RATHENA_WEB_SERVER:=false}" "${RATHENA_TEST_USER:=}" "${RATHENA_TEST_PASSWORD:=}"
: "${RATHENA_AGENT_USER:=}" "${RATHENA_AGENT_PASSWORD:=}" "${RATHENA_GM_USER:=}" "${RATHENA_GM_PASSWORD:=}"

# rAthena's conf parser takes everything after "key: " to end of line, and the server account is
# also written into SQL below -- keep these to a safe charset instead of escaping them.
safe='^[A-Za-z0-9_.-]{4,64}$'
# char/map keep the inter-server userid/passwd in NAME_LENGTH (24-byte) buffers: a longer value is
# silently truncated and login then rejects it ("Invalid password", map never reaches char).
server_safe='^[A-Za-z0-9_.-]{4,23}$'
[[ "${DB_PASSWORD}" =~ ${safe} ]] || die "DB_PASSWORD must match ${safe}"
[[ "${RATHENA_SERVER_USER}" =~ ${server_safe} ]] || die "RATHENA_SERVER_USER must match ${server_safe}"
[[ "${RATHENA_SERVER_PASSWORD}" =~ ${server_safe} ]] ||
  die "RATHENA_SERVER_PASSWORD must match ${server_safe} (rAthena truncates longer ones)"
[[ "${RATHENA_SERVER_NAME}" =~ ^[A-Za-z0-9_.\ -]{1,20}$ ]] || die "RATHENA_SERVER_NAME: 1-20 plain chars"
[[ "${HOST_LAN_IP}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "HOST_LAN_IP must be an IPv4 address"
[[ "${DB_NAME}" =~ ^[A-Za-z0-9_]{1,64}$ ]] || die "DB_NAME must match ^[A-Za-z0-9_]{1,64}$"
# Optional accounts (login.userid is varchar(23), user_pass varchar(32)): the operator's test
# player, the agent's player (group 0) and the agent's validation GM (group 20, groups.yml).
for acct in TEST AGENT GM; do
  user_var="RATHENA_${acct}_USER" pass_var="RATHENA_${acct}_PASSWORD"
  if [[ -n "${!user_var}${!pass_var}" ]]; then
    [[ "${!user_var}" =~ ^[A-Za-z0-9_]{4,23}$ ]] || die "${user_var}: 4-23 of [A-Za-z0-9_]"
    [[ "${!pass_var}" =~ ^[A-Za-z0-9]{8,32}$ ]] || die "${pass_var}: 8-32 of [A-Za-z0-9]"
  fi
done

export HOST_LAN_IP DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD RATHENA_SERVER_USER \
  RATHENA_SERVER_PASSWORD RATHENA_SERVER_NAME RATHENA_NEW_ACCOUNT RATHENA_PINCODE
vars='${HOST_LAN_IP} ${DB_HOST} ${DB_PORT} ${DB_NAME} ${DB_USER} ${DB_PASSWORD}'
vars+=' ${RATHENA_SERVER_USER} ${RATHENA_SERVER_PASSWORD} ${RATHENA_SERVER_NAME}'
vars+=' ${RATHENA_NEW_ACCOUNT} ${RATHENA_PINCODE}'
for tmpl in /opt/rathena-conf-templates/*.txt.tmpl; do
  out="conf/import/$(basename "${tmpl}" .tmpl)"
  envsubst "${vars}" <"${tmpl}" >"${out}"
  log "rendered ${out}"
done
# Static (no variables): the Validation group for the agent's GM account.
cp /opt/rathena-conf-templates/groups.yml conf/import/groups.yml
log "installed conf/import/groups.yml"
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

# Thai end to end: rAthena stores the client's raw chat/name bytes (CP874) and only runs SET NAMES
# (conf/import/inter_conf.txt: *_codepage tis620). The database must already default to tis620 (the
# db service's --character-set-server), or the imported tables would be utf8mb4 and mangle them.
charset="$(sql -e "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA \
                   WHERE SCHEMA_NAME='${DB_NAME}'")"
[[ "${charset}" == tis620 ]] || die "database ${DB_NAME} has charset '${charset}', expected tis620 \
(the db volume was initialised without --character-set-server=tis620; recreate it)"

if [[ -z "$(sql -e "SHOW TABLES LIKE 'login'")" ]]; then
  log "empty database: importing schema"
  for f in main.sql web.sql roulette_default_data.sql logs.sql; do
    log "  sql-files/${f}"
    sql <"sql-files/${f}"
  done
fi

# Chat ground truth must be byte-exact: VARBINARY keeps every CP874 byte (no charset conversion at
# all), and 300 holds the client's 255-byte maximum (stock varchar(150) loses longer lines).
msgtype="$(sql -e "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='${DB_NAME}' \
                   AND TABLE_NAME='chatlog' AND COLUMN_NAME='message'")"
if [[ "${msgtype}" != "varbinary(300)" ]]; then
  log "chatlog.message ${msgtype} -> varbinary(300)"
  sql -e "ALTER TABLE chatlog MODIFY message VARBINARY(300) NOT NULL DEFAULT ''"
fi

# Replace main.sql's insecure default server account (s1/p1) with ours. char and map log in to
# login with these exact credentials (conf/import/{char,map}_conf.txt). Credentials go through
# stdin, never argv.
sql <<SQL
UPDATE login SET userid='${RATHENA_SERVER_USER}', user_pass='${RATHENA_SERVER_PASSWORD}'
  WHERE account_id=1 AND sex='S';
SQL
# ensure_account <user> <password> <group_id|keep>: create if missing, reset the password; with a
# group id, also (re)assert the group at every start. Credentials go through stdin, never argv,
# and are never logged.
ensure_account() {
  local group_sql=""
  [[ "$3" == keep ]] || group_sql=", group_id=$3"
  sql <<SQL
INSERT INTO login (userid, user_pass, sex, email, group_id)
  SELECT '$1', '$2', 'M', 'a@a.com', 0 FROM DUAL
  WHERE NOT EXISTS (SELECT 1 FROM login WHERE userid='$1');
UPDATE login SET user_pass='$2'${group_sql}
  WHERE userid='$1' AND sex <> 'S';
SQL
}
if [[ -n "${RATHENA_TEST_USER}" ]]; then
  ensure_account "${RATHENA_TEST_USER}" "${RATHENA_TEST_PASSWORD}" keep
  log "test account ensured"
fi
# The agent's accounts (docs/rathena-client.md "Agent accounts"): a plain player, and the GM
# account in the Validation group (20) -- only for Phase 1 ground-truth checks.
if [[ -n "${RATHENA_AGENT_USER}" ]]; then
  ensure_account "${RATHENA_AGENT_USER}" "${RATHENA_AGENT_PASSWORD}" 0
  log "agent player account ensured (group 0)"
fi
if [[ -n "${RATHENA_GM_USER}" ]]; then
  ensure_account "${RATHENA_GM_USER}" "${RATHENA_GM_PASSWORD}" 20
  log "agent validation account ensured (group 20)"
fi
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
