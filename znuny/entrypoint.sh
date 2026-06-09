#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  Znuny container entrypoint — 100% automated provisioning.
#
#  Roles (argv[1]):
#    web      → render config, provision DB once, seed admin, exec Apache
#    daemon   → wait for web's provisioning, exec bin/otrs.Daemon.pl (fg)
#
#  Idempotent: DB schema is loaded only if the `valid` table is absent.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

OTRS_HOME="${OTRS_HOME:-/opt/otrs}"
ROLE="${1:-web}"

log() { echo "[entrypoint:${ROLE}] $*"; }

# ── Env defaults ────────────────────────────────────────────────────
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:=znuny}"
: "${POSTGRES_USER:=znuny}"
: "${POSTGRES_PASSWORD:=znuny}"
: "${REDIS_HOST:=redis}"
: "${REDIS_PORT:=6379}"
: "${REDIS_DB:=0}"
: "${OPENSEARCH_HOST:=opensearch}"
: "${OPENSEARCH_PORT:=9200}"
: "${OPENSEARCH_INITIAL_ADMIN_PASSWORD:=admin}"
: "${ZNUNY_FQDN:=znuny-dev.local}"
: "${ZNUNY_SYSTEM_ID:=10}"
: "${ZNUNY_ADMIN_USER:=root@localhost}"
: "${ZNUNY_ADMIN_PASSWORD:=changeme}"

export PGPASSWORD="${POSTGRES_PASSWORD}"
PSQL=(psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -qtA)

# ── 1. Render Kernel/Config.pm from template ────────────────────────
render_config() {
    log "Rendering Kernel/Config.pm from template…"
    local tmpl="${OTRS_HOME}/Kernel/Config.pm.tmpl"
    local out="${OTRS_HOME}/Kernel/Config.pm"
    sed \
        -e "s|__DB_HOST__|${POSTGRES_HOST}|g" \
        -e "s|__DB_PORT__|${POSTGRES_PORT}|g" \
        -e "s|__DB_NAME__|${POSTGRES_DB}|g" \
        -e "s|__DB_USER__|${POSTGRES_USER}|g" \
        -e "s|__DB_PASS__|${POSTGRES_PASSWORD}|g" \
        -e "s|__REDIS_HOST__|${REDIS_HOST}|g" \
        -e "s|__REDIS_PORT__|${REDIS_PORT}|g" \
        -e "s|__REDIS_DB__|${REDIS_DB}|g" \
        -e "s|__SYSTEM_ID__|${ZNUNY_SYSTEM_ID}|g" \
        -e "s|__FQDN__|${ZNUNY_FQDN}|g" \
        -e "s|__OS_HOST__|${OPENSEARCH_HOST}|g" \
        -e "s|__OS_PORT__|${OPENSEARCH_PORT}|g" \
        -e "s|__GERTI_ADMIN_WS_TOKEN__|${GERTI_ADMIN_WS_TOKEN:-}|g" \
        -e "s|__GERTI_AGENT_WS_TOKEN__|${GERTI_AGENT_WS_TOKEN:-}|g" \
        "${tmpl}" > "${out}"
    chown otrs:www-data "${out}"
    chmod 660 "${out}"
}

# ── 2. Wait for PostgreSQL ──────────────────────────────────────────
wait_for_postgres() {
    log "Waiting for PostgreSQL ${POSTGRES_HOST}:${POSTGRES_PORT}…"
    for i in $(seq 1 60); do
        if pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" >/dev/null 2>&1; then
            if "${PSQL[@]}" -c 'SELECT 1' >/dev/null 2>&1; then
                log "PostgreSQL is ready."
                return 0
            fi
        fi
        sleep 2
    done
    log "FATAL: PostgreSQL never became ready"; exit 1
}

# ── 3. Idempotent DB provisioning ───────────────────────────────────
schema_present() {
    local n
    n="$("${PSQL[@]}" -c "SELECT to_regclass('public.valid') IS NOT NULL;" 2>/dev/null || echo f)"
    [ "${n}" = "t" ]
}

provision_db() {
    if schema_present; then
        log "Znuny schema already present — skipping DB init (idempotent)."
        return 0
    fi
    local dbdir="${OTRS_HOME}/scripts/database"
    log "Loading Znuny PostgreSQL schema…"
    "${PSQL[@]}" -f "${dbdir}/schema.postgresql.sql"
    log "Loading initial data…"
    "${PSQL[@]}" -f "${dbdir}/initial_insert.postgresql.sql"
    log "Applying post-schema (foreign keys)…"
    "${PSQL[@]}" -f "${dbdir}/schema-post.postgresql.sql"
    log "Schema loaded."
}

# ── 4. Rebuild config cache + seed admin ────────────────────────────
seed_admin() {
    log "Rebuilding SysConfig…"
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Console.pl Maint::Config::Rebuild" || true

    # The built-in super-agent shipped by initial_insert is login 'root@localhost'.
    # Ensure it exists; create if a custom ZNUNY_ADMIN_USER was requested.
    local exists
    exists="$("${PSQL[@]}" -c "SELECT count(*) FROM users WHERE login='${ZNUNY_ADMIN_USER}';" 2>/dev/null | tr -d '[:space:]')"
    if [ "${exists:-0}" = "0" ]; then
        log "Creating admin user '${ZNUNY_ADMIN_USER}'…"
        su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Console.pl Admin::User::Add \
            --user-name '${ZNUNY_ADMIN_USER}' --first-name Gerti --last-name Admin \
            --email-address '${ZNUNY_ADMIN_USER}' --password '${ZNUNY_ADMIN_PASSWORD}' \
            --group admin" || log "WARN: Admin::User::Add failed"
    fi

    log "Setting admin '${ZNUNY_ADMIN_USER}' password…"
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Console.pl Admin::User::SetPassword '${ZNUNY_ADMIN_USER}' '${ZNUNY_ADMIN_PASSWORD}'" \
        || log "WARN: SetPassword failed"

    # Verify via DB (Znuny 7.2 has no Admin::User::Search console command)
    local n
    n="$("${PSQL[@]}" -c "SELECT count(*) FROM users WHERE login='${ZNUNY_ADMIN_USER}';" 2>/dev/null | tr -d '[:space:]')"
    if [ "${n:-0}" -ge 1 ]; then
        log "Admin user verified in DB: ${ZNUNY_ADMIN_USER} (users.login match=${n})"
    else
        log "FATAL: admin user ${ZNUNY_ADMIN_USER} not found in users table"; return 1
    fi
}

# ── 5. OpenSearch wiring + reachability proof ───────────────────────
#   NOTE: Znuny 7.2 *core* does NOT bundle Elasticsearch/OpenSearch
#   support — it's the separate installable "Znuny-Elasticsearch"
#   add-on package. We therefore (a) prove the Znuny container can
#   reach the OpenSearch cluster (the meaningful infra-level check),
#   and (b) attempt to install the ES add-on from Znuny's online repo
#   if reachable. Lack of the add-on does NOT fail provisioning.
configure_opensearch() {
    log "Verifying Znuny→OpenSearch reachability (${OPENSEARCH_HOST}:${OPENSEARCH_PORT})…"
    local health
    health="$(curl -fsS "http://${OPENSEARCH_HOST}:${OPENSEARCH_PORT}/_cluster/health" 2>/dev/null || true)"
    if echo "${health}" | grep -qE '"status":"(green|yellow)"'; then
        log "OpenSearch reachable from Znuny container. Health: ${health}"
        echo "${health}" > "${OTRS_HOME}/var/tmp/.opensearch_health" 2>/dev/null || true
    else
        log "WARN: OpenSearch not reachable from Znuny container yet."
    fi

    # Best-effort: register ES online repo + install add-on if available.
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && timeout 60 bin/otrs.Console.pl Admin::Package::Install Znuny-Elasticsearch" 2>/dev/null \
        && log "Znuny-Elasticsearch add-on installed." \
        || log "NOTE: Znuny-Elasticsearch add-on not installed (offline / not in repo) — core has no ES; reachability proven above."
}

# ── Provisioning marker so the daemon waits for web to finish ───────
MARKER="${OTRS_HOME}/var/tmp/.provisioned"

provision_all() {
    render_config
    wait_for_postgres
    provision_db
    seed_admin
    configure_opensearch
    # ── ITSM CMDB add-ons (#1K, R1K): idempotent install (baked .opm, 3 pkgs)
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bash scripts/ensure-itsm.sh" \
        && log "ITSM CMDB packages ensured." \
        || log "WARN: ensure-itsm.sh failed — ITSM CMDB may not be installed; continuing."
    # ── CMDB fields (#1L, R1L): idempotent append of Disco/Memoria to Computer class.
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && perl scripts/ensure-cmdb-fields.pl" \
        && log "CMDB Computer fields (Disco/Memoria) ensured." \
        || log "WARN: ensure-cmdb-fields falhou — continuando."
    su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Console.pl Maint::Cache::Delete" || true
    mkdir -p "$(dirname "${MARKER}")"
    date -u +%FT%TZ > "${MARKER}"
    chown -R otrs:www-data "${OTRS_HOME}/var" || true
    log "Provisioning complete."
}

case "${ROLE}" in
    web)
        provision_all
        log "Starting Apache (foreground)…"
        rm -f /var/run/apache2/apache2.pid || true
        # /etc/apache2/envvars references unset vars → relax `set -u`.
        set +u
        # shellcheck disable=SC1091
        source /etc/apache2/envvars
        set -u
        exec apache2 -D FOREGROUND
        ;;

    daemon)
        render_config
        wait_for_postgres
        log "Waiting for web container to finish provisioning…"
        for i in $(seq 1 120); do
            if schema_present && [ -f "${MARKER}" ]; then break; fi
            sleep 2
        done
        if ! schema_present; then
            log "FATAL: schema not present after wait"; exit 1
        fi
        su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Console.pl Maint::Config::Rebuild" || true
        log "Starting Znuny Daemon (foreground supervised)…"
        # Daemon backgrounds itself; we supervise + tail to stay PID 1.
        su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Daemon.pl start" || true
        sleep 5
        # Foreground supervisor loop
        while true; do
            if ! su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Daemon.pl status" 2>/dev/null | grep -qi 'running'; then
                log "Daemon not running — (re)starting…"
                su otrs -s /bin/bash -c "cd ${OTRS_HOME} && bin/otrs.Daemon.pl start" || true
            fi
            sleep 15
        done
        ;;

    shell) exec /bin/bash ;;
    *)     exec "$@" ;;
esac
