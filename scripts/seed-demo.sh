#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  seed-demo.sh — Semeia a instância Znuny com a operação MSP fictícia
#  "Aurora Móveis" (demo Gerti Service Desk).  IDEMPOTENTE.
#
#  Uso (na VPS, dentro de ~/ground-control):
#      ./scripts/seed-demo.sh            # semeia / re-semeia (seguro)
#      ./scripts/seed-demo.sh --verify   # só roda as verificações e2e
#      ./scripts/seed-demo.sh --reset    # APAGA os tickets/entidades demo (destrutivo)
#
#  Requisitos: stack de pé (`docker compose ps` healthy). Roda o helper Perl
#  `seed-demo.pl` DENTRO do container znuny-web como usuário 'otrs', usando a
#  API nativa do Znuny (Ticket/CustomerUser/Queue/Service/SLA/User/Group).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

DC="docker compose"
WEB="znuny-web"
PG="postgres"
CONSOLE="/opt/otrs/bin/otrs.Console.pl"
PERL_LOCAL="scripts/seed-demo.pl"
PERL_IN_CT="/opt/otrs/var/seed-demo.pl"
AUTH_LOCAL="scripts/seed-authcheck.pl"
AUTH_IN_CT="/opt/otrs/var/seed-authcheck.pl"
PGUSER="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2)"; PGUSER="${PGUSER:-znuny}"
PGDB="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2)";   PGDB="${PGDB:-znuny}"

c_otrs() { $DC exec -T "$WEB" su -s /bin/bash otrs -c "$*"; }
psql_q() { $DC exec -T "$PG" psql -U "$PGUSER" -d "$PGDB" -tAc "$*"; }
hdr()    { echo; echo "── $* ──"; }

# ── --reset : remove SOMENTE os dados de demonstração ────────────────────────
if [[ "${1:-}" == "--reset" ]]; then
  hdr "RESET demo (destrutivo — só dados Aurora/Gerti)"
  read -r -p "Confirma apagar tickets/empresa/usuários demo? [digite SIM]: " ans
  [[ "$ans" == "SIM" ]] || { echo "abortado."; exit 1; }
  # tickets da empresa AURORA
  TIDS="$(psql_q "SELECT id FROM ticket WHERE customer_id='AURORA';" | tr '\n' ' ')"
  if [[ -n "${TIDS// }" ]]; then
    c_otrs "$CONSOLE Maint::Ticket::Delete $(for t in $TIDS; do echo -n " --ticket-id $t"; done)" || true
  fi
  psql_q "DELETE FROM customer_user WHERE customer_id='AURORA';" >/dev/null || true
  psql_q "DELETE FROM customer_company WHERE customer_id='AURORA';" >/dev/null || true
  echo "Agentes/filas/SLAs/serviços são preservados (compartilhados). Reset de tickets+empresa OK."
  exit 0
fi

# ── copia o helper Perl para dentro do container ─────────────────────────────
if [[ "${1:-}" != "--verify" ]]; then
  hdr "Copiando helper Perl para o container"
  $DC cp "$PERL_LOCAL" "$WEB:$PERL_IN_CT"
  $DC cp "$AUTH_LOCAL" "$WEB:$AUTH_IN_CT"
  $DC exec -T "$WEB" chown otrs:otrs "$PERL_IN_CT" "$AUTH_IN_CT"
  echo "  ok: $PERL_IN_CT + $AUTH_IN_CT"

  hdr "Executando seed (idempotente) via API Znuny"
  c_otrs "perl $PERL_IN_CT"
fi

# garante helper de auth no container (também no modo --verify isolado)
$DC cp "$AUTH_LOCAL" "$WEB:$AUTH_IN_CT" >/dev/null 2>&1 || true
$DC exec -T "$WEB" chown otrs:otrs "$AUTH_IN_CT" >/dev/null 2>&1 || true

# ── VERIFICAÇÃO END-TO-END ───────────────────────────────────────────────────
hdr "Verificação e2e"
FAIL=0
ok()  { echo "  ✓ $*"; }
bad() { echo "  ✗ $*"; FAIL=$((FAIL+1)); }

# agentes
# (Admin::User::List não existe no Znuny 7.2.3 — valida via SQL na tabela users)
AG="$(psql_q "SELECT count(*) FROM users WHERE login IN ('william','bruno.cardoso','patricia.menezes','rafael.tavares','diego.fontana');")"
AGN="$(psql_q "SELECT string_agg(login,', ' ORDER BY login) FROM users WHERE login IN ('william','bruno.cardoso','patricia.menezes','rafael.tavares','diego.fontana');")"
[[ "$AG" -ge 5 ]] && ok "agentes seedados: $AG/5 ($AGN)" || bad "agentes faltando ($AG/5)"

# empresa
CC="$(psql_q "SELECT name FROM customer_company WHERE customer_id='AURORA';")"
[[ -n "$CC" ]] && ok "empresa: $CC" || bad "empresa AURORA ausente"

# customer users
CU="$(psql_q "SELECT count(*) FROM customer_user WHERE customer_id='AURORA';")"
[[ "$CU" -ge 5 ]] && ok "customer users: $CU/5" || bad "customer users faltando ($CU/5)"

# filas
Qn="$(c_otrs "$CONSOLE Admin::Queue::List" 2>/dev/null | grep -cE 'Suporte::N1|Suporte::N2|Field Service|Financeiro' || true)"
[[ "$Qn" -ge 4 ]] && ok "filas MSP: $Qn (Admin::Queue::List)" || bad "filas faltando ($Qn)"

# serviços / SLA
SVC="$(psql_q "SELECT count(*) FROM service;")"
SLA="$(psql_q "SELECT count(*) FROM sla;")"
[[ "$SVC" -ge 10 ]] && ok "serviços: $SVC" || bad "serviços insuficientes ($SVC)"
[[ "$SLA" -ge 3  ]] && ok "SLAs: $SLA"     || bad "SLAs insuficientes ($SLA)"

# tickets por estado
hdr "Tickets por estado (SQL)"
psql_q "SELECT ts.name, count(*) FROM ticket t JOIN ticket_state ts ON ts.id=t.ticket_state_id WHERE t.customer_id='AURORA' GROUP BY ts.name ORDER BY ts.name;" \
  | sed 's/|/  →  /' | sed 's/^/  /'
TT="$(psql_q "SELECT count(*) FROM ticket WHERE customer_id='AURORA';")"
[[ "$TT" -ge 15 ]] && ok "total tickets Aurora: $TT (>=15)" || bad "poucos tickets ($TT)"

# artigos (back-and-forth)
ART="$(psql_q "SELECT count(*) FROM article a JOIN ticket t ON t.id=a.ticket_id WHERE t.customer_id='AURORA';")"
[[ "$ART" -ge 30 ]] && ok "artigos totais: $ART" || bad "poucos artigos ($ART)"

# credencial do William válida (auth check via API nativa do Znuny)
AUTHOK="$(c_otrs "perl $AUTH_IN_CT agent william 'Gerti@Demo2026'" 2>/dev/null | tr -d '\r\n' || true)"
[[ "$AUTHOK" == OK:* ]] && ok "login agente william AUTENTICA ($AUTHOK)" || bad "auth william falhou ($AUTHOK)"

# credencial customer válida
CAUTH="$(c_otrs "perl $AUTH_IN_CT customer eduardo.salvi 'Aurora@Demo2026'" 2>/dev/null | tr -d '\r\n' || true)"
[[ "$CAUTH" == OK:* ]] && ok "login cliente eduardo.salvi AUTENTICA ($CAUTH)" || bad "auth customer falhou ($CAUTH)"

# interfaces HTTP vivas
AURL="https://znuny-dev.was.dev.br/znuny/index.pl"
CURL_C="https://znuny-dev.was.dev.br/znuny/customer.pl"
AH="$(curl -sk -o /dev/null -w '%{http_code}' "$AURL" || echo 000)"
CH="$(curl -sk -o /dev/null -w '%{http_code}' "$CURL_C" || echo 000)"
[[ "$AH" == 200 ]] && ok "agente $AURL → 200" || bad "agente HTTP $AH"
[[ "$CH" == 200 ]] && ok "cliente $CURL_C → 200" || bad "cliente HTTP $CH"

hdr "Resultado"
if [[ "$FAIL" -eq 0 ]]; then
  echo "  ✓ TODAS as verificações passaram."
  exit 0
else
  echo "  ✗ $FAIL verificação(ões) falharam."
  exit 1
fi
