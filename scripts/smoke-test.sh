#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  End-to-end smoke test for the Ground Control Znuny stack.
#  Exits non-zero on the first MANDATORY failure (items 1-9, 11).
#  cloudflared (item 10) is informational only.
# ─────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "$0")/.."

DC="docker compose"
PASS=0; FAIL=0
HTTP_PORT="$(grep -E '^ZNUNY_HTTP_PORT=' .env 2>/dev/null | cut -d= -f2)"; HTTP_PORT="${HTTP_PORT:-8080}"
PGUSER="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2)"; PGUSER="${PGUSER:-znuny}"
PGDB="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2)"; PGDB="${PGDB:-znuny}"
ADMIN="$(grep -E '^ZNUNY_ADMIN_USER=' .env 2>/dev/null | cut -d= -f2)"; ADMIN="${ADMIN:-root@localhost}"

ok()  { echo "  ✓ $*"; PASS=$((PASS+1)); }
bad() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }
hdr() { echo; echo "── $* ──"; }

# 1 — build
hdr "1. docker compose build (znuny image)"
if $DC build znuny-web >/tmp/gc-build.log 2>&1; then ok "image built"; else bad "build failed (see /tmp/gc-build.log)"; tail -30 /tmp/gc-build.log; exit 1; fi

# 2 — up
hdr "2. docker compose up -d"
if $DC up -d >/tmp/gc-up.log 2>&1; then ok "stack started"; else bad "up failed"; cat /tmp/gc-up.log; exit 1; fi

# 3 — healthchecks
hdr "3. wait for healthy: postgres redis opensearch znuny-web"
wait_healthy() {
  local svc="$1" tries="${2:-60}"
  for _ in $(seq 1 "$tries"); do
    local st
    st="$($DC ps --format '{{.Service}} {{.Health}}' | awk -v s="$svc" '$1==s{print $2}')"
    [ "$st" = "healthy" ] && { ok "$svc healthy"; return 0; }
    sleep 5
  done
  bad "$svc not healthy"; $DC ps; $DC logs --tail=40 "$svc"; return 1
}
wait_healthy postgres 30   || exit 1
wait_healthy redis 20      || exit 1
wait_healthy opensearch 40 || exit 1
wait_healthy znuny-web 60  || exit 1

# 4 — DB schema
hdr "4. Postgres: znuny schema + seeded rows"
Q() { $DC exec -T postgres psql -U "$PGUSER" -d "$PGDB" -tAc "$1" 2>/dev/null | tr -d '[:space:]'; }
for t in ticket users valid ticket_state; do
  [ "$(Q "SELECT to_regclass('public.$t') IS NOT NULL;")" = "t" ] && ok "table $t exists" || bad "table $t missing"
done
V=$(Q "SELECT count(*) FROM valid;");        [ "${V:-0}" -gt 0 ] && ok "valid rows=$V"        || bad "valid empty"
S=$(Q "SELECT count(*) FROM ticket_state;"); [ "${S:-0}" -gt 0 ] && ok "ticket_state rows=$S" || bad "ticket_state empty"
U=$(Q "SELECT count(*) FROM users;");        [ "${U:-0}" -gt 0 ] && ok "users rows=$U"        || bad "users empty"

# 5 — web login page
hdr "5. Znuny web returns login HTML"
BODY="$(curl -fsS "http://localhost:${HTTP_PORT}/znuny/index.pl" 2>/dev/null || true)"
echo "$BODY" | grep -qi 'login' && ok "HTTP 200 + login form" || bad "no login HTML"

# 6 — console proves app+DB; admin user verified
hdr "6. Console runs + admin user exists"
# Znuny 7.2 has no Admin::User::Search; prove app+DB via Maint::Database::Check
# (a real console command that opens the DB) AND verify the admin in `users`.
if $DC exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Console.pl Maint::Database::Check" 2>&1 | grep -qiE 'ok|success'; then
  ok "console Maint::Database::Check OK (app+DB work)"
else
  bad "Maint::Database::Check failed"
fi
AN="$(Q "SELECT count(*) FROM users WHERE login='$ADMIN';")"
[ "${AN:-0}" -ge 1 ] && ok "admin '$ADMIN' present in users (n=$AN)" || bad "admin '$ADMIN' missing"

# 7 — daemon
hdr "7. Daemon running, container up"
sleep 10
if $DC exec -T znuny-daemon su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Daemon.pl status" 2>/dev/null | grep -qi running; then
  ok "daemon status: running"
else
  bad "daemon not running"; $DC logs --tail=40 znuny-daemon
fi

# 8 — Redis cache keys
hdr "8. Redis holds Znuny cache keys"
$DC exec -T znuny-web su otrs -s /bin/bash -c "cd /opt/otrs && bin/otrs.Console.pl Maint::Config::Rebuild" >/dev/null 2>&1 || true
curl -fsS "http://localhost:${HTTP_PORT}/znuny/index.pl" >/dev/null 2>&1 || true
KEYS="$($DC exec -T redis redis-cli KEYS '*' 2>/dev/null | head -5)"
KN="$($DC exec -T redis redis-cli DBSIZE 2>/dev/null | tr -d '[:space:]')"
if [ "${KN:-0}" -gt 0 ]; then ok "redis DBSIZE=$KN (sample: $(echo $KEYS|tr '\n' ' '))"; else bad "no keys in redis"; fi

# 9 — OpenSearch
hdr "9. OpenSearch health + Znuny ES check"
H="$($DC exec -T opensearch curl -fsS http://localhost:9200/_cluster/health 2>/dev/null)"
echo "$H" | grep -qE '"status":"(green|yellow)"' && ok "cluster: $(echo $H|grep -oE '"status":"[a-z]+"')" || bad "cluster unhealthy"
# Znuny 7.2 CORE has NO Elasticsearch console command (it's an add-on).
# The meaningful infra check: prove the Znuny container can reach the
# OpenSearch cluster and gets a healthy response (documented in README).
ESOUT="$($DC exec -T znuny-web bash -c 'curl -fsS http://opensearch:9200/_cluster/health' 2>/dev/null || true)"
if echo "$ESOUT" | grep -qE '"status":"(green|yellow)"'; then
  ok "Znuny→OpenSearch reachable: $(echo "$ESOUT" | grep -oE '\"status\":\"[a-z]+\"')"
else
  bad "Znuny cannot reach OpenSearch"; echo "    $ESOUT"
fi

# 10 — cloudflared (informational)
hdr "10. cloudflared (pending real token — informational)"
if $DC ps --format '{{.Service}} {{.State}}' | grep -q '^cloudflared'; then
  ok "cloudflared container exists ($($DC ps --format '{{.Service}} {{.State}}'|awk '$1=="cloudflared"{print $2}'))"
  echo "  i last log:"; $DC logs --tail=3 cloudflared 2>/dev/null | sed 's/^/    /'
else
  echo "  i cloudflared not running (acceptable until token supplied)"
fi

# 11 — idempotent restart
hdr "11. Idempotent down/up (no destructive re-init)"
$DC down >/tmp/gc-down.log 2>&1
$DC up -d >/tmp/gc-up2.log 2>&1
wait_healthy znuny-web 60 || { bad "web not healthy after restart"; }
ERRS="$($DC logs znuny-web 2>&1 | grep -iE 'duplicate key|already exists' | grep -vi 'skipping' | head -3)"
if [ -z "$ERRS" ]; then ok "no duplicate-key / re-init errors"; else bad "idempotency broken: $ERRS"; fi
SKIP="$($DC logs znuny-web 2>&1 | grep -i 'already present — skipping' | tail -1)"
[ -n "$SKIP" ] && ok "DB init skipped on 2nd boot: $SKIP" || echo "  i no skip line seen (check provisioning logs)"

# ── Summary
hdr "SUMMARY"
echo "  PASS=$PASS  FAIL=$FAIL"
$DC ps
[ "$FAIL" -eq 0 ] && { echo; echo "ALL MANDATORY CHECKS PASSED"; exit 0; } || { echo; echo "FAILURES PRESENT"; exit 1; }
