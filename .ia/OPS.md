# Ground Control — OPS / Runbook

## Hosts

| Host | Uso | Acesso |
|---|---|---|
| `100.99.49.110` / LAN `192.168.1.40` | **VPS de produção do ground-control** (Znuny + sidecar #1C) | **`ssh gc`** (jump via node `postgres`→LAN) — ver nota abaixo |
| `100.96.54.61` | node `postgres` (mesma LAN; jump host saudável) | `ssh ubuntu@100.96.54.61` (key) |
| local | dev | docker compose |

> Não confundir com a VPS `gerti` (host `gerti`), que serve a apresentação `plano-gerti.was.dev.br`. São máquinas distintas.

> **Acesso SSH ao ground-control — path Tailscale direto é assimétrico (CGNAT do uplink):** `tailscale status` mostra `direct 189.1.162.120:41641, tx≫rx`; `tailscale ping` responde mas SSH/TCP direto p/ `100.99.49.110` dá *"timed out (banner exchange)"*, intermitente. **Não é MTU** (mesmo assim `tailscale0` foi p/ 1240 via drop-in `tailscaled.service.d/mtu.conf` — higiene, persistente) **nem firewall do host** (ufw off, DERP sao 9.7ms). Causa: retorno UDP do WireGuard descartado pelo NAT/roteador do uplink — **fix permanente é no roteador/ISP** (port-forward 41641 / UPnP / tirar do CGNAT). **Acesso confiável:** alias `~/.ssh/config` `Host gc` → `ProxyJump ubuntu@100.96.54.61` → `192.168.1.40` (key-based; node `postgres` tem path Tailscale simétrico). Tráfego público (Cloudflare Tunnel) não usa Tailscale e nunca foi afetado.

## Domínios / Cloudflare Tunnel

| Domínio | Tunnel | Serviço | Estado |
|---|---|---|---|
| `znuny-dev.was.dev.br` | (token-mode, em `.env.prod`) | znuny-web:80 | aguardando token do connector |
| `groundcontrol.was.dev.br` | `ground-control` (id `4f515441-d21e-4992-9389-f59b4c35e0d2`) | landing web:80 | ingress configurado via API; falta DNS CNAME |

DNS pendente (token Cloudflare atual sem `Zone:DNS:Edit`): criar CNAME **proxied**
`groundcontrol` → `4f515441-d21e-4992-9389-f59b4c35e0d2.cfargotunnel.com`.

## Deploy (resumo — completo em `../DEPLOY.md`)

```bash
ssh ubuntu@100.99.49.110
git clone git@github.com:williamroot/ground-control.git   # 1ª vez
cd ground-control && git pull
make init
# editar .env.prod com CLOUDFLARE_TUNNEL_TOKEN real
make build && make up
make test          # validar 24/24 antes de considerar no ar
```

Atualização de conteúdo já implantado: `git pull` + `docker compose up -d --build` (ou só `up -d` se nada de imagem mudou).

## Runbooks

### Stack não sobe / container unhealthy
1. `docker compose ps` — qual serviço
2. `make logs svc=<serviço>`
3. Postgres unhealthy + log `/var/lib/postgresql/data (unused mount)` → volume PG18 deve ser `/var/lib/postgresql` (já corrigido no compose; se editaram, reverter)
4. znuny-web loop + `Can't locate /opt/znuny/...` → simlink `/opt/znuny→/opt/otrs` ausente; rebuild da imagem

### cloudflared `token is not valid`
Esperado até `.env.prod` ter token real. Não afeta o resto da stack (nada depende do cloudflared). Após colar token: `docker compose up -d cloudflared`.

### Cache não vai pro Redis
`make redis-keys` deve listar `znuny:*`. Se vazio: `Cache::Redis` não carregou → conferir `Custom/Kernel/System/Cache/Redis.pm` na imagem e `Cache::Module` no Config.pm; rebuild.

### Reset total (destrói dados)
`make reset` — apaga todos os volumes (DB incluso). Só em dev / recriação consciente.

### Smoke-test
`make test` — 24 asserts e2e a partir do estado atual. Para validação real pós-deploy, rodar do zero: `make reset && make build && make up && make test`.

### Seed de demonstração (apresentação)
`scripts/seed-demo.sh` — semeia, **de forma idempotente**, a operação MSP
fictícia "Aurora Móveis" (5 agentes, 5 customer users, 5 filas, 11 serviços,
3 SLAs, 17 tickets com artigos e horas). Roda na VPS dentro de `~/ground-control`
com a stack de pé. Detalhes, credenciais e roteiro em [`DEMO.md`](DEMO.md).
- `./scripts/seed-demo.sh` — semeia / re-semeia (seguro reexecutar)
- `./scripts/seed-demo.sh --verify` — só verificação e2e
- `./scripts/seed-demo.sh --reset` — apaga só os dados de demo (pede `SIM`)
O motor é `scripts/seed-demo.pl` (API nativa Znuny, executado como `otrs`
dentro de `znuny-web`); `scripts/seed-authcheck.pl` valida credenciais.

### Deploy do sidecar de contratos (Spec #1C — profile `gerti`)

Plano canônico: [`../docs/superpowers/plans/2026-05-17-spec-1c-deploy.md`](../docs/superpowers/plans/2026-05-17-spec-1c-deploy.md).
**Aditivo e gated por profile**: nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny fica intocado (Postgres
não reinicia, nada do Znuny é reconstruído). Single-cluster: schema
`gerti` no MESMO `postgres:18` do Znuny (Spec #0). Verificado local:
`docker compose config --services` SEM profile lista só os 6 serviços
Znuny (o footgun `${VAR:?}` que quebraria isso foi eliminado — segredos
têm default vazio no `environment:` e são exigidos em runtime no shell
do container, não no parse do compose).

**Pré-requisito (humano, one-time):** em `~/ground-control/.env.prod`
na VPS (gitignored — NUNCA commitar), adicionar as duas linhas
`GERTI_SIDECAR_DB_PASSWORD=…` e `GERTI_ADMIN_DB_PASSWORD=…` (valores
fortes; ver `.env.prod.example`). O agente gera os segredos e os
entrega out-of-band (Human-needed #2 do plano).

```bash
ssh ubuntu@100.99.49.110
cd ground-control && git pull                       # traz compose + gerti-init + sidecar
# 1) garantir GERTI_SIDECAR_DB_PASSWORD / GERTI_ADMIN_DB_PASSWORD em .env.prod
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 2) D1 — schema gerti + roles + RLS no cluster VIVO (idempotente)
$DC run --rm gerti-db-init       # verá o SELECT listando gerti_* roles + schemas

# 3) D2 — build + migrate (Alembic como gerti_admin_user) + app
$DC build sidecar
$DC up -d sidecar                # sidecar-migrate roda e sai 0; sidecar sobe healthy
$DC ps                           # sidecar healthy; sidecar-migrate Exit 0

# 4) prova de schema + RLS real em prod (zero-tolerância)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select count(*) from gerti.contract;"      # 0 linhas, tabela existe
docker compose exec -T postgres psql -U gerti_sidecar -d "$POSTGRES_DB" \
  -c "select * from gerti.tenant;"               # 0 linhas (GUC ausente → fail-closed)
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select relname,relrowsecurity,relforcerowsecurity from pg_class c \
   join pg_namespace n on n.oid=relnamespace where nspname='gerti' and relkind='r';"
#  → relrowsecurity AND relforcerowsecurity = t p/ TODA tabela gerti.*

# 5) Znuny/landing intactos
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**D3 — expor `api-dev.was.dev.br`** (ingress no MESMO tunnel `znuny-dev`,
token-mode multi-hostname): usar o script **read-modify-write** do plano
de deploy §D3 (GET config → splice da regra `api-dev` ANTES do catch-all
`http_status:404` → guard aborta se `znuny-dev` sumir → PUT do objeto
inteiro → re-GET assert ambos hostnames). DNS `CNAME api-dev →
<tunnel_id>.cfargotunnel.com` proxied. **Nunca** PUT de config
hand-written (substitui o array inteiro e derruba `znuny-dev` + demo
Aurora). Verificar: `curl -fsS https://api-dev.was.dev.br/v1/health`.

**Rollback (sidecar só, Znuny intocado):**
`$DC stop sidecar` → `git checkout <sha-anterior> -- apps/sidecar docker-compose.yml`
→ `$DC up -d sidecar`. Migration ruim: `$DC run --rm sidecar-migrate uv run alembic downgrade -1`.
**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-05-17):** artefatos de deploy prontos, commitados e
> no `origin/main` (compose profile `gerti`, `postgres/gerti-init/`,
> `.env.prod.example`). A execução na VPS ficou **pendente: SSH p/
> `100.99.49.110` inacessível** (porta 22 timeout / ICMP 100% loss,
> embora o node apareça no tailnet) no momento do deploy autônomo —
> bloqueio externo do lado da VPS. Assim que o SSH voltar, o deploy é
> um `git pull` + os passos 1–5 + D3 acima (nenhuma mudança de código
> pendente).

### Deploy do portal (Spec #1F-a — profile `gerti`)

**Pré-requisito:** `GERTI_SESSION_SECRET` (forte, 32+ bytes hex) em
`~/ground-control/.env.prod` na VPS (gitignored — NUNCA commitar).
`GERTI_ADMIN_DB_PASSWORD` já deve estar presente (sidecar #1C).

**Pré-requisito de deploy:** o webservice `Session::SessionCreate` deve
estar criado no Znuny prod antes de o portal receber tráfego real de
login. Detalhes em
`docs/superpowers/spikes/2026-05-17-r1-znuny-customer-auth.md` (R1,
ADR D14 — mecanismo `CustomerUserLogin`/`Password` → `SessionID`).

```bash
ssh gc 'cd ~/ground-control && git pull'
ssh gc 'cd ~/ground-control && \
  DC="docker compose --env-file .env --env-file .env.prod --profile gerti"; \
  $DC build portal && $DC up -d portal && $DC ps'
```

**Seed dos tenants de teste (idempotente):**

```bash
# Branding dos 2 tenants (gerti_admin_user, BYPASSRLS):
ssh gc 'cd ~/ground-control/apps/sidecar && \
  DATABASE_URL="postgresql+asyncpg://gerti_admin_user:${GERTI_ADMIN_DB_PASSWORD}@postgres:5432/znuny" \
  uv run python scripts/seed_demo_branding.py'

# Fixture Znuny do TechNova (1 empresa + 1 usuário, idempotente):
# login demo: admin.tech@technova.example / TechNova@Demo2026
ssh gc 'cd ~/ground-control && ./scripts/seed-demo.sh'
```

`./scripts/seed-demo.sh` roda `scripts/seed-technova.pl` dentro de
`znuny-web` como `otrs` (idempotente). Aurora já existe em prod desde #1C.

**Ingresso Cloudflare — AMBOS os subdomínios (read-modify-write, padrão D3/D15):**

Resolver account + tunnel id pelo conector: decodificar base64 do
`CLOUDFLARE_TUNNEL_TOKEN` em `.env.prod`
(`{"a":<account_id>,"t":<tunnel_id>,...}`) — OU via CF API
(`GET /accounts` → `GET /accounts/{acct}/cfd_tunnel?is_deleted=false`)
procurando o tunnel cujo ingress contém `znuny-dev.was.dev.br`.
Esse tunnel chama-se **`ground-control`** (id
`4f515441-d21e-4992-9389-f59b4c35e0d2`) — **NÃO confundir** com o
`groundcontrol-landing` (serve `groundcontrol.was.dev.br`).

Passos:
1. GET configuração completa do tunnel.
2. Com `jq`: remover regras pré-existentes de
   `aurora.suporte.gerti.com.br` e `technova.suporte.gerti.com.br`
   (idempotência), depois splicing AMBAS as regras
   `aurora` e `technova` → `http://portal:3000` ANTES do catch-all
   `http_status:404`.
3. **Guard obrigatório:** abortar o PUT se qualquer um dos quatro
   hostnames (`znuny-dev.was.dev.br`, `api-dev.was.dev.br`,
   `aurora.suporte.gerti.com.br`, `technova.suporte.gerti.com.br`)
   estiver ausente no objeto montado — e se o último elemento não for
   `http_status:404`. **Nunca** fazer PUT de config hand-written
   (sobrescreve o array inteiro e derruba `znuny-dev`+`api-dev`).
4. PUT do objeto completo → re-GET e assertar os 4 hostnames presentes.

**DNS — CNAME idempotente (ambos os subdomínios):**

Para cada subdomínio (`aurora.suporte.gerti.com.br`,
`technova.suporte.gerti.com.br`):
`GET /zones/{zone}/dns_records?name=<sub>` → `POST` se ausente / `PUT`
se presente → CNAME proxied para
`<tunnel_id>.cfargotunnel.com`. Se o token CF não tiver
`Zone:DNS:Edit`, criar os dois CNAMEs manualmente no dashboard (não
bloqueia o código).

**Verificação:**

```bash
# Branding diferente por subdomínio (prova white-label):
curl -fsS https://aurora.suporte.gerti.com.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsS https://technova.suporte.gerti.com.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK

# Serviços anteriores intactos:
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**Rollback (portal somente; Znuny e sidecar intocados):**

```bash
$DC stop portal
```

Reverter compose se necessário: `git checkout <sha-anterior> -- apps/portal docker-compose.yml && $DC up -d portal`.
Schema `gerti` e Znuny permanecem intactos. **NUNCA** `make reset`
(destrói o DB compartilhado).

> **Status (2026-05-17):** portal implementado e gateado; deploy per
> runbook acima. A execução na VPS é etapa separada (deploy agent
> concorrente); este runbook é o procedimento de referência.

> **Domínios dos tenants de teste (Spec #1F-a):** Os 2 white-labels de
> teste (Aurora / TechNova) são expostos sob **`aurora.was.dev.br` /
> `technova.was.dev.br`** (1-nível, cobertos pelo Cloudflare Universal SSL
> `*.was.dev.br`) — este é o caminho ativo para testes agora (SSL válido
> out-of-the-box). Os padrões 2-nível `*.suporte.was.dev.br` (Cloudflare
> Tunnel) e `*.suporte.gerti.com.br` (produção) continuam aceitos; o
> resolver (sidecar `SUBDOMAIN_RE` e portal `SUB_RE`) aceita as **3
> alternativas** via regex ancorado. Hosts de infra `znuny-dev.was.dev.br`,
> `api-dev.was.dev.br`, `groundcontrol.was.dev.br` estão em `ROOT_HOSTS`
> (sidecar) / `INFRA_HOSTS` (portal) e curto-circuitam para no-tenant /
> branding default antes de qualquer lookup. Domínio de produção
> `<tenant>.suporte.gerti.com.br` permanece inalterado (Spec §1F-a) —
> **item TLS pendente em prod:** o cert de 2-nível exige ACM SAN ou
> Cloudflare for SaaS; Universal SSL `*.suporte.gerti.com.br` não é emitido
> automaticamente pelo CF free tier.

### Deploy do Console de Administração (Spec #1G-a — profile `gerti`)

App **separado** da equipe Gerti (NÃO white-label), subdomínio próprio
(`gerti.was.dev.br` em teste; `admin.suporte.gerti.com.br` em prod). Aditivo
e profile-gated (padrão D13/D15): um `make up` da stack Znuny não o toca.
Fala só com o `sidecar` (endpoints `/v1/admin/*`, cross-tenant). ADR D19.

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` na VPS —
gitignored):**
- `ZNUNY_ADMIN_WS_URL` = base do webservice GertiAdmin, p.ex.
  `https://znuny-dev.was.dev.br/znuny/nph-genericinterface.pl/Webservice/GertiAdmin`.
- `ZNUNY_WS_TOKEN` (já presente p/ o auth #1F) — o **mesmo** valor é reusado
  como `GERTI_ADMIN_WS_TOKEN` (token do webservice GertiAdmin) e renderizado no
  `Config.pm` do Znuny pelo entrypoint. O sidecar o envia como `AccessToken`.
- `GERTI_SESSION_SECRET` (já presente p/ o portal #1H) — assina o `gsid_adm`.

```bash
# 0) levar o código #1G-a para a VPS (NÃO mergeia na main; deploy da branch):
ssh gc 'cd ~/ground-control && git fetch origin && git checkout feature/spec-1g-admin && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild da imagem (bakeia os módulos GI custom de T1.G via COPY no
#    Dockerfile + renderiza GertiAdmin::AccessToken do env) e recria web+daemon.
#    NOTA: recria o core Znuny (downtime curto). Provisionamento é idempotente (D6).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) importar/atualizar o webservice GertiAdmin no Znuny (idempotente):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -qi GertiAdmin || \
   bin/otrs.Console.pl Admin::WebService::Add --name GertiAdmin --source-path /opt/otrs/webservices/GertiAdmin.yml"'
#   (o YAML é COPY'd p/ a imagem no build; confirmar Admin::WebService::List lista
#    GertiCustomerAuth E GertiAdmin — nunca remover/substituir o de auth.)

# 3) sidecar: rebuild (traz os /v1/admin/*) + up (aditivo, sem migration nova):
ssh gc "cd ~/ground-control && $DC build sidecar && $DC up -d sidecar && $DC ps"

# 4) admin UI: build + up (profile gerti):
ssh gc "cd ~/ground-control && $DC build admin && $DC up -d admin && $DC ps"

# 5) prova interna (sem depender do subdomínio público):
ssh gc 'docker compose exec -T sidecar curl -fsS http://127.0.0.1:8001/v1/health && echo SIDECAR_OK'
ssh gc 'cd ~/ground-control && docker compose exec -T admin node -e \
  "fetch(\"http://127.0.0.1:3000/login\").then(r=>console.log(\"ADMIN_UI\",r.status))"'
# login de agente real (william/Gerti@Demo2026, .ia/DEMO.md) deve emitir gsid_adm:
ssh gc 'docker compose exec -T sidecar curl -fsS -i -X POST \
  -H "content-type: application/json" -H "host: gerti.was.dev.br" \
  -d "{\"login\":\"william\",\"password\":\"Gerti@Demo2026\"}" \
  http://127.0.0.1:8001/v1/admin/auth/login | grep -i "set-cookie: gsid_adm" && echo ADMIN_LOGIN_OK'
```

**Ingresso Cloudflare — `gerti.was.dev.br` (read-modify-write, padrão D3/D15):**
GET config do tunnel `ground-control` (id `4f515441-d21e-4992-9389-f59b4c35e0d2`)
→ com `jq`, remover regra pré-existente de `gerti.was.dev.br` (idempotência) e
fazer splice de `gerti.was.dev.br → http://admin:3000` **ANTES** do catch-all
`http_status:404` → **guard obrigatório**: abortar o PUT se qualquer um de
`znuny-dev.was.dev.br`, `api-dev.was.dev.br`, `aurora.was.dev.br`,
`technova.was.dev.br` sumir, ou se o último elemento não for `http_status:404`
→ PUT do objeto inteiro → re-GET assertando os 5 hostnames. **Nunca** PUT
hand-written (substitui o array e derruba os outros). DNS: CNAME proxied
`gerti → <tunnel_id>.cfargotunnel.com`.

> **Status (2026-06-02): DEPLOYADO em prod e verificado ao vivo.** `main`
> (`24da5c7`) na VPS; imagem Znuny rebuildada (módulos GI bakeados +
> `GertiAdmin::AccessToken` renderizado), `znuny-web`/`znuny-daemon` recriados
> (Healthy, login público 200), webservice `GertiAdmin` presente (id 2),
> `sidecar` rebuildado (Healthy, sem migration), serviço `admin` up (Healthy).
> `.env.prod` recebeu `ZNUNY_ADMIN_WS_URL` (interno) + `ZNUNY_WS_TOKEN` (gerado).
> **Prova e2e em prod:** agent login `william` → 200 + `gsid_adm`; onboarding
> real → 201 criando CustomerCompany+CustomerUser reais no Znuny via GertiAdmin;
> throwaway limpo. **Único pendente — exposição pública:** o ingress de
> `gerti.was.dev.br` (passos abaixo) exige um **CF API token** com
> `Account:Cloudflare Tunnel:Edit` que **não está** no `.env.prod` (só o
> `CLOUDFLARE_TUNNEL_TOKEN` connector, que não edita config) — mesma classe de
> bloqueio do D13 (DNS). Rodar o passo de ingress + CNAME assim que o token CF
> estiver disponível; o console já está rodando e verificado internamente.

**Rollback (admin somente; Znuny/sidecar/portal intocados):** `$DC stop admin`.
Reverter compose: `git checkout <sha> -- apps/admin docker-compose.yml && $DC up -d admin`.
Para o token Znuny: o rebuild da imagem é idempotente; reverter o sha do
`znuny/` e rebuild. **NUNCA** `make reset` (destrói o DB compartilhado).

### Deploy do fluxo de tickets do portal (Spec #1E — profile `gerti`)

Aditivo e profile-gated (padrão D13/D15): nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny pura fica intocado. Sem
migration nova (tabela `gerti.ticket_contract_link` foi provisionada na
migration `0008`).

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` na VPS —
gitignored — NUNCA commitar):**
- `ZNUNY_TICKET_WS_URL` = base do webservice GertiTicket, p.ex.
  `https://znuny-dev.was.dev.br/znuny/nph-genericinterface.pl/Webservice/GertiTicket`.
- `ZNUNY_WS_TOKEN` (já presente desde #1G-a) — reusado como `AccessToken`
  do webservice GertiTicket e renderizado no `Config.pm` do Znuny pelo
  entrypoint como `GertiAdmin::AccessToken`.

```bash
# 0) levar o código #1E para a VPS:
ssh gc 'cd ~/ground-control && git fetch origin && git checkout feature/spec-1e-portal-ticketing && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild da imagem (bakeia operações GertiTicket + GertiTicket.yml
#    via COPY no Dockerfile; perl -c é gate de build) e recria web+daemon.
#    NOTA: recria o core Znuny (downtime curto). Provisionamento é idempotente (D6).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) criar o DynamicField GertiContractId no Znuny (idempotente):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && perl scripts/ensure-gerti-dynamicfield.pl"'

# 3) importar o webservice GertiTicket no Znuny (idempotente):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -qi GertiTicket || \
   bin/otrs.Console.pl Admin::WebService::Add --name GertiTicket --source-path /opt/otrs/webservices/GertiTicket.yml"'
#   GUARD: confirmar que os 3 webservices estão presentes (nunca remover os outros):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'
#   → deve listar GertiCustomerAuth + GertiAdmin + GertiTicket (nenhum pode sumir)

# 4) sidecar: rebuild (traz /v1/tickets* e /v1/ticketing/*; SEM migration nova) + up:
ssh gc "cd ~/ground-control && $DC build sidecar && $DC up -d sidecar && $DC ps"

# 5) portal: rebuild (traz páginas de tickets) + up:
ssh gc "cd ~/ground-control && $DC build portal && $DC up -d portal && $DC ps"

# 6) verificação e2e em prod:
#    a) abrir chamado real via portal (tenant Aurora ou TechNova) vinculado a contrato
#    b) conferir DynamicField GertiContractId preenchido no ticket Znuny
#    c) conferir linha em gerti.ticket_contract_link:
ssh gc 'docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select * from gerti.ticket_contract_link order by created_at desc limit 5;"'
#    d) limpar o ticket throwaway criado no teste

# 7) serviços anteriores intactos:
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsS https://aurora.was.dev.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsS https://technova.was.dev.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi 'login' && echo ADMIN_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**Rollback (tickets somente; Znuny/sidecar base/portal base intactos):**

```bash
$DC stop portal    # desliga o portal (chamados somem do UI)
$DC stop sidecar   # opcional: desliga /v1/tickets* também
```

Para reverter código Znuny de tickets: `git checkout <sha-anterior> -- znuny/` →
rebuild: `$DC build znuny-web && $DC up -d znuny-web znuny-daemon`. O DynamicField
e a linha `ticket_contract_link` persistem no DB (não destrutivo). **NUNCA**
`make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-06-08): DEPLOYADO em prod e verificado ao vivo.** `main` (`508b82c`) na VPS;
> imagem Znuny rebuildada (5 módulos GertiTicket `perl -c` verde no build), `znuny-web`/
> `znuny-daemon` recriados (Healthy, login público 200), DynamicField `GertiContractId`
> criado (id 6), webservice `GertiTicket` importado (`Admin::WebService::List`: GertiCustomerAuth
> 1 + GertiAdmin 2 + GertiTicket 3 — nenhum removido), `sidecar`+`portal` rebuildados (Healthy,
> sem migration). **Prova e2e em prod (tenant Aurora, helpdesk):** `GET /v1/ticketing/contracts`
> 200 (6); `form-meta` 200 (prioridades do Znuny vivo); `POST /v1/tickets` 201 → ticket Znuny
> real `2026060810000014` com DynamicField `GertiContractId` + linha `gerti.ticket_contract_link`
> (`pending`); 422 sem contrato (≥2); listar/detalhe/responder (1→2 artigos) OK; cross-tenant
> (TechNova) → 404. Throwaway (ticket+link) limpo. Serviços anteriores intactos (znuny-dev/
> api-dev/aurora/technova/landing). Gates pré-deploy: sidecar `ruff`+`mypy`+`pytest` 131,
> portal typecheck+vitest 56, e2e local 100%. **Bug de runbook corrigido:** `Admin::WebService::Add`
> exige **`--name`** (sem ele imprime usage e NÃO importa — mascarado pelo `grep -qi … ||`);
> afetava #1E **e** #1G-a — corrigido nos dois pontos deste arquivo.
> Único pré-existente não relacionado: ingress público de `gerti.was.dev.br` (admin #1G-a)
> segue pendente de CF API token.

### Deploy do worker de consumo/cobrança (Spec #1B — profile `gerti`)

Aditivo e profile-gated (padrão D13/D15): nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny pura fica intocado.
Adiciona uma **nova operação GI** ao webservice `GertiTicket` já existente
(`TimeAccountingSince`) e um novo serviço compose **`sidecar-worker`** (loop
de reconciliação de consumo + fechamento de ciclos).

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` na VPS —
gitignored — NUNCA commitar):**
- Nenhuma variável obrigatória nova: a URL do GertiTicket é derivada
  automaticamente de `ZNUNY_ADMIN_WS_URL` (troca `/GertiAdmin` →
  `/GertiTicket`), assim como `ZNUNY_WS_TOKEN` já presente.
- **Opcionais** (padrão aplicado se ausentes):
  - `RECONCILE_INTERVAL_SECONDS` — intervalo do loop de reconciliação (default `120`).
  - `TIME_UNIT_TO_MINUTES` — fator de conversão de unidade de tempo para minutos (default `1`).

```bash
# 0) levar o código #1B para a VPS:
ssh gc 'cd ~/ground-control && git fetch origin && git checkout feature/spec-1b-consumo-cobranca && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild da imagem (bakeia a nova op GertiTicket::TimeAccountingSince
#    via COPY no Dockerfile; perl -c é gate de build) e recria web+daemon.
#    NOTA: recria o core Znuny (downtime curto). Provisionamento é idempotente (D6).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) CRÍTICO — atualizar o webservice GertiTicket (já existe em prod desde #1E):
#    Admin::WebService::Add FALHA se o WS já existir — usar UPDATE idempotente.
#    NOTA: nesta versão do Znuny, Admin::WebService::Update exige --webservice-id
#    (NÃO --name); resolver o id pela saída de Admin::WebService::List.
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && \
   WSID=\$(bin/otrs.Console.pl Admin::WebService::List | sed -n \"s/.*GertiTicket (\\([0-9]\\+\\)).*/\\1/p\"); \
   if [ -n \"\$WSID\" ]; then \
     bin/otrs.Console.pl Admin::WebService::Update --webservice-id \"\$WSID\" \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   else \
     bin/otrs.Console.pl Admin::WebService::Add --name GertiTicket \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   fi"'
#   GUARD: confirmar que os 3 webservices seguem presentes:
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'
#   → deve listar GertiCustomerAuth + GertiAdmin + GertiTicket (nenhum pode sumir)
#   O GertiTicket agora inclui a operação TimeAccountingSince.

# 3) sidecar: rebuild (traz reconciliation_service + cycle_closer + jobs/worker)
#    + migration 0013 (consumption_sync_cursor) + app + worker:
ssh gc "cd ~/ground-control && $DC build sidecar"
ssh gc "cd ~/ground-control && $DC up -d sidecar-migrate"
#   aguardar Exit 0:
ssh gc "cd ~/ground-control && $DC ps sidecar-migrate"
ssh gc "cd ~/ground-control && $DC up -d sidecar sidecar-worker && $DC ps"
#   → sidecar: Up/healthy; sidecar-worker: Up; sidecar-migrate: Exit 0

# 4) verificação e2e:
#    a) lançar TimeUnits num ticket vinculado a contrato (via painel Znuny)
#    b) forçar/aguardar um tick do worker (ou docker compose restart sidecar-worker)
#    c) conferir consumption_event gerado + saldo debitado:
ssh gc 'docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select id, contract_id, billable_minutes, billable_amount_brl, created_at \
      from gerti.consumption_event order by created_at desc limit 5;"'
#    d) conferir no portal /v1/dashboard ou detalhe do contrato que o saldo diminuiu
#    e) limpar o ticket/time-entry throwaway criado no teste

# 5) serviços anteriores intactos:
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsS https://aurora.was.dev.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsS https://technova.was.dev.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi 'login' && echo ADMIN_OK
```

**Rollback (worker somente; Znuny/sidecar/portal/admin intocados):**

```bash
$DC stop sidecar-worker   # reconciliação para; nada destrutivo (cursor permanece)
```

Para reverter código: `git checkout <sha-anterior> -- apps/sidecar znuny/ docker-compose.yml`
→ rebuild: `$DC build znuny-web sidecar && $DC up -d znuny-web znuny-daemon sidecar`.
Migration reversa (se necessário): `$DC run --rm sidecar-migrate uv run alembic downgrade -1`.
**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-06-09): mergeado na `main` (`origin/main` em `bffa1bf`); DEPLOYADO em prod.**
> Gates pré-deploy verdes: `perl -c` no build, sidecar `ruff`+`mypy`+`pytest` (138), e
> **e2e LOCAL 100% verde** (reconciliação debita saldo ao vivo: hour_bank 34.0→33.5h e
> credit_brl 20000→19900 BRL = 30/60×200; idempotente via uuid5; ciclo vencido fechado).
> **Prod:** `git pull` (bffa1bf); `znuny-web` rebuildado (`TimeAccountingSince syntax OK`) +
> Healthy; webservice **GertiTicket atualizado por `--webservice-id`** (op nova incluída;
> GertiCustomerAuth 1 + GertiAdmin 2 + GertiTicket 3 intactos); migration **0013** aplicada
> (`gerti.consumption_sync_cursor` presente); `sidecar` Healthy + `sidecar-worker` Up. **Worker
> provado vivo em prod:** log `cycles.closed count=1`. **e2e de consumo em prod VERIFICADO ao
> vivo (2026-06-09):** ticket Aurora vinculado ao `AUR-HORAS-2026` (hour_bank) → 45 min em
> `time_accounting` → tick do worker → `gerti.consumption_event` (45 min, `ticket_work`,
> `recorded_by=worker:reconcile`) + cursor avançado → saldo debitado. Ciclo auto-fechado
> `7f130956` (`AUR-HORAS-2026`, period_end 2026-01-31, legitimamente vencido, 360 min
> consolidados). Throwaways limpos (ticket Znuny + `time_accounting` + link removidos; o
> `consumption_event` é append-only e persiste por design). Serviços anteriores intactos.
> **Bugs de runbook corrigidos no e2e:** (1) `Admin::WebService::Update` exige `--webservice-id`
> (não `--name`) nesta versão Znuny; (2) `sidecar-worker` precisa de `healthcheck: {disable: true}`
> (não roda HTTP).

### Deploy do time tracker do agente (Spec #1J — profile `gerti`)

Aditivo e profile-gated (padrão D13/D15): nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny pura fica intocado.
Adiciona **3 operações GI** ao webservice `GertiTicket` já existente
(`TimeAccountingAdd`, `AgentTicketSearch`, `AgentTicketGet`) com token
**separado** (`GertiAgent::AccessToken`) e um novo serviço de rotas no
sidecar + app `admin` (`/atendimento`).

> **Novo segredo obrigatório — `ZNUNY_AGENT_WS_TOKEN`:** token separado
> das ops de agente (root/cross-tenant); gerar forte (32+ bytes hex) e
> adicionar ao `.env.prod` na VPS **antes** do deploy. NUNCA commitar.

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` na VPS —
gitignored — NUNCA commitar):**
- `ZNUNY_AGENT_WS_TOKEN` — **NOVO**: token do webservice `GertiAgent::AccessToken`
  (ops de agente: root/cross-tenant; token separado do `ZNUNY_WS_TOKEN`/`GertiAdmin`;
  gerar forte, ex.: `openssl rand -hex 32`).
- Demais já presentes: `ZNUNY_WS_TOKEN` (`GertiAdmin::AccessToken`),
  `ZNUNY_ADMIN_WS_URL`, `ZNUNY_TICKET_WS_URL`, `GERTI_SESSION_SECRET`,
  `GERTI_SIDECAR_DB_PASSWORD`, `GERTI_ADMIN_DB_PASSWORD`.

```bash
ssh gc 'cd ~/ground-control && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild da imagem (bakeia as 3 novas ops GertiTicket de agente +
#    renderiza GertiAgent::AccessToken do env via Config.pm.tmpl + entrypoint;
#    perl -c é gate de build) e recria web+daemon.
#    NOTA: recria o core Znuny (downtime curto). Provisionamento é idempotente (D6).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) CRÍTICO — atualizar o webservice GertiTicket (já existe em prod desde #1E):
#    Admin::WebService::Update exige --webservice-id (NÃO --name nesta versão Znuny;
#    aprendido no #1B — usar Update com id resolvido via Admin::WebService::List).
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && \
   WSID=\$(bin/otrs.Console.pl Admin::WebService::List | sed -n \"s/.*GertiTicket (\\([0-9]\\+\\)).*/\\1/p\"); \
   if [ -n \"\$WSID\" ]; then \
     bin/otrs.Console.pl Admin::WebService::Update --webservice-id \"\$WSID\" \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   else \
     bin/otrs.Console.pl Admin::WebService::Add --name GertiTicket \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   fi"'
#   GUARD: confirmar que os 3 webservices seguem presentes (nunca remover os outros):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'
#   → deve listar GertiCustomerAuth + GertiAdmin + GertiTicket (nenhum pode sumir)
#   O GertiTicket agora inclui TimeAccountingAdd + AgentTicketSearch + AgentTicketGet.

# 3) sidecar + admin UI: rebuild (traz timer_service + /v1/admin/timer/* + /atendimento)
#    + migration 0014 (agent_timer) + app:
ssh gc "cd ~/ground-control && $DC build sidecar admin"
ssh gc "cd ~/ground-control && $DC up -d sidecar-migrate"
#   aguardar Exit 0:
ssh gc "cd ~/ground-control && $DC ps sidecar-migrate"
ssh gc "cd ~/ground-control && $DC up -d sidecar admin && $DC ps"
#   → sidecar: Up/healthy; admin: Up/healthy; sidecar-migrate: Exit 0

# 4) verificação e2e (resumo):
#    a) logar no console admin (gsid_adm) com agente real (william/Gerti@Demo2026)
#    b) ir p/ /atendimento e buscar ticket Aurora vinculado a contrato
#    c) start timer → pause → resume → stop com adjust_minutes + nota
#    d) conferir time_accounting criado no Znuny (psql ou GI):
ssh gc 'docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select ticket_id, time_unit, article_id, create_time from time_accounting order by create_time desc limit 5;"'
#    e) aguardar/forçar tick do sidecar-worker (#1B): consumption_event deve aparecer
#    f) conferir saldo debitado no contrato Aurora via /v1/admin/tenants/{id}/contracts
#    g) limpar throwaways: timer na tabela gerti.agent_timer (soft-stopped já),
#       time_accounting entry + artigo interno no Znuny; consumption_event é append-only.
ssh gc 'docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select id, agent_login, ticket_id, state, started_at, stopped_at from gerti.agent_timer order by started_at desc limit 5;"'
```

**Rollback (timer somente; Znuny/sidecar-worker/portal/admin base intocados):**

```bash
$DC stop admin    # UI /atendimento some; sidecar-worker e portal não são afetados
```

Para reverter código: `git checkout <sha-anterior> -- apps/sidecar apps/admin znuny/ docker-compose.yml`
→ rebuild: `$DC build znuny-web sidecar admin && $DC up -d znuny-web znuny-daemon sidecar admin`.
Migration reversa (se necessário): `$DC run --rm sidecar-migrate uv run alembic downgrade -1`.
**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-06-09): DEPLOYADO em prod e verificado ao vivo.** `main` na VPS; `znuny-web`
> rebuildado (3 ops `syntax OK` + `GertiAgent::AccessToken` renderizado), Healthy; `GertiTicket`
> atualizado por `--webservice-id 3` (3 ops de agente incluídas; os 3 webservices intactos);
> migration **0014** aplicada (`gerti.agent_timer`); `sidecar`+`admin` Healthy. **`ZNUNY_AGENT_WS_TOKEN`
> adicionado ao `.env.prod`.** **Prova e2e em prod (agente william, ticket Aurora 36, contrato
> AUR-HORAS-2026 hour_bank):** search mostra o contrato; start→stop(ajuste 30min) cria
> `time_accounting`+nota → #1B reconcilia → `consumption_event` (30min) → **saldo 31.25h→30.75h
> (−0.5h)**; ownership cross-agente (bruno) → **404**; teto `adjust_minutes` → **409**. Throwaway
> limpo (`time_accounting`/timer/link; `consumption_event` é append-only e persiste). Serviços
> anteriores intactos (znuny/api-dev 200). **Único pré-existente não relacionado:** ingress
> público de `gerti.was.dev.br` (Console admin, onde vive `/atendimento`) segue pendente de CF API
> token desde #1G-a — o `admin` roda Healthy internamente; o e2e foi pela API do sidecar.
>
> _(histórico) mergeado na `main` (`origin/main` em `05bb825`); e2e LOCAL 100% verde antes do deploy._
> Gates verdes: `perl -c` no build Znuny (3 ops novas), sidecar `ruff`+`mypy`+`pytest` (149),
> admin typecheck+vitest (41). **e2e vivo no stack local** (verificado): agente busca ticket
> Aurora vinculado → start/pause/resume → stop (ajuste 30min + nota) cria `time_accounting`
> (create_by=agente) + nota interna → worker #1B reconcilia → `consumption_event` (30min,
> worker:reconcile) → saldo **33.5h→33.0h** (−0.5h); guarda de posse cross-agente → **404**;
> start idempotente; teto `adjust_minutes` → **409**. Dois rounds de review de segurança
> aplicados: **token `GertiAgent` separado** + **ownership check (IDOR)** + guarda de pause +
> teto de ajuste. **Deploy na VPS PENDENTE** (bloqueio externo de SSH — jump host
> `100.96.54.61` em timeout; público segue 200). Quando o SSH voltar: adicionar
> **`ZNUNY_AGENT_WS_TOKEN`** ao `.env.prod` (NOVO segredo obrigatório — sem ele o entrypoint não
> renderiza `GertiAgent::AccessToken` e as 3 ops de agente falham fail-closed) + `git pull` +
> os passos acima (rebuild znuny-web + Update GertiTicket `--webservice-id` + migration 0014 +
> sidecar/admin) + e2e em prod.

### Deploy do CMDB/ativos (Spec #1K — profile `gerti` + rebuild Znuny)

Aditivo e profile-gated (padrão D13/D15): nenhum serviço `gerti` sobe sem
`--profile gerti`; um `make up` da stack Znuny pura fica intocado.
Estende o webservice `GertiTicket` com **3 operações GI novas**
(`ConfigItemSearch`, `ConfigItemGet`, `TicketCreate` estendido com
`LinkObject RelevantTo`) e bakeia os **3 add-ons ITSM oficiais** na imagem
Znuny (`GeneralCatalog` → `ITSMCore` → `ITSMConfigurationManagement`,
versão **7.2.1** — instalados idempotentemente por `znuny/scripts/ensure-itsm.sh`
chamado pelo entrypoint). Sem migration nova no sidecar.

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` na VPS —
gitignored — NUNCA commitar):**
- Nenhuma variável nova: `ZNUNY_WS_TOKEN` (`GertiAdmin::AccessToken`) e
  `ZNUNY_AGENT_WS_TOKEN` (`GertiAgent::AccessToken`) já presentes (#1G-a/#1J)
  são reusados como `AccessToken` das novas ops GI.
- Demais já presentes: `ZNUNY_ADMIN_WS_URL`, `ZNUNY_TICKET_WS_URL`,
  `GERTI_SESSION_SECRET`, `GERTI_SIDECAR_DB_PASSWORD`, `GERTI_ADMIN_DB_PASSWORD`.

```bash
ssh gc 'cd ~/ground-control && git fetch origin && git checkout feature/spec-1k-cmdb-ativos && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild da imagem.
#    O build bakeia os 3 .opm ITSM (COPY znuny/addons/ → /opt/otrs/addons/),
#    as 3 novas ops GI de CMDB (COPY znuny/Custom/...) e o ensure-itsm.sh.
#    perl -c é gate de build de todas as ops GertiTicket.
#    O entrypoint chama ensure-itsm.sh na inicialização: instala/verifica os
#    add-ons em ordem (GeneralCatalog → ITSMCore → ITSMConfigurationManagement)
#    idempotentemente (skip se já instalados) e rebuilda o SysConfig/Agent/
#    Customer menus. Provisionamento é idempotente (D6).
#    NOTA: recria o core Znuny (downtime curto).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) CRÍTICO — atualizar o webservice GertiTicket (já existe em prod desde #1E).
#    Admin::WebService::Update exige --webservice-id (NÃO --name nesta versão Znuny;
#    aprendido no #1B e confirmado no #1J).
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && \
   WSID=\$(bin/otrs.Console.pl Admin::WebService::List | sed -n \"s/.*GertiTicket (\\([0-9]\\+\\)).*/\\1/p\"); \
   if [ -n \"\$WSID\" ]; then \
     bin/otrs.Console.pl Admin::WebService::Update --webservice-id \"\$WSID\" \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   else \
     bin/otrs.Console.pl Admin::WebService::Add --name GertiTicket \
       --source-path /opt/otrs/webservices/GertiTicket.yml; \
   fi"'
#   GUARD: confirmar que os 3 webservices seguem presentes (nunca remover os outros):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'
#   → deve listar GertiCustomerAuth + GertiAdmin + GertiTicket (nenhum pode sumir)
#   O GertiTicket agora inclui ConfigItemSearch + ConfigItemGet + TicketCreate+LinkObject.

# 3) sidecar: rebuild (traz /v1/assets*, config_item_id em /v1/tickets; SEM migration nova) + up:
ssh gc "cd ~/ground-control && $DC build sidecar && $DC up -d sidecar && $DC ps"

# 4) portal: rebuild (traz /ativos, /ativos/[id], nav "Ativos") + up:
ssh gc "cd ~/ground-control && $DC build portal && $DC up -d portal && $DC ps"

# 5) verificação e2e:
#    a) MSP: criar um Config Item para Aurora com CustomerID=AURORA no Znuny
#       (ITSM → Config Items → Add → classe Computador, CustomerID=AURORA)
#    b) logar no portal Aurora como customer → acessar /ativos → CI deve aparecer
#    c) clicar no CI → /ativos/<id> deve mostrar o detalhe
#    d) clicar "Abrir chamado sobre este ativo" → /tickets/novo?ativo=<id>
#    e) submeter o ticket → conferir ticket Znuny criado com link RelevantTo:
ssh gc 'docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && perl -e \"
    use Kernel::System::ObjectManager;
    local \\\$Kernel::OM = Kernel::System::ObjectManager->new();
    my \\\$LinkObject = \\\$Kernel::OM->Get(\\\"Kernel::System::LinkObject\\\");
    my %List = \\\$LinkObject->LinkList(
      Object => \\\"Ticket\\\", Key => <TICKET_ID>,
      Object2 => \\\"ITSMConfigItem\\\", UserID => 1,
    );
    use Data::Dumper; print Dumper(\\\\%List);
  \""'
#    f) confirmar link RelevantTo presente na saída do Dumper
#    g) limpar throwaways: ticket Znuny + link + CI criados no teste (via UI MSP)

# 6) serviços anteriores intactos:
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsS https://aurora.was.dev.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsS https://technova.was.dev.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi 'login' && echo ADMIN_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**Rollback (sidecar + portal somente; Znuny — add-ons persistem no DB, não destrutivo):**

```bash
$DC stop portal sidecar   # UI /ativos some; add-ons ITSM e tickets anteriores intactos
```

Para reverter código Znuny: `git checkout <sha-anterior> -- znuny/`
→ rebuild: `$DC build znuny-web && $DC up -d znuny-web znuny-daemon`.
Os add-ons ITSM instalados no DB Znuny **persistem** (desinstalar manualmente
se necessário, em ordem inversa: `Admin::Package::Uninstall` para
`ITSMConfigurationManagement` → `ITSMCore` → `GeneralCatalog`).
**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-06-09): mergeado na `main` (`origin/main` em `671b1a9`); DEPLOYADO em staging
> e verificado ao vivo.** Gates: `perl -c` das 3 ops GI + sidecar (159) + portal (75) + e2e local
> verdes. **Staging:** `znuny-web` rebuildado (3 add-ons ITSM bakeados em `/opt/otrs/itsm-opm`
> — NÃO `var/packages`, que é volume e seria sombreado; `ensure-itsm.sh` instala+`ReinstallAll`
> idempotente no provisionamento), `GeneralCatalog`/`ITSMCore`/`ITSMConfigurationManagement`
> instalados; `GertiTicket` atualizado (`--webservice-id 3`, ops ConfigItem); `sidecar`+`portal`
> Healthy. **Prova e2e em staging (Aurora):** Config Item criado (Computer, CustomerID=AURORA) →
> `GET /v1/assets` 200 escopado (TechNova `[]`) → detalhe com SerialNumber → cross-tenant **404**
> → "abrir chamado a partir do ativo" cria ticket **linkado ao CI** (`link_relation` RelevantTo).
> Throwaway limpo; serviços anteriores intactos (znuny/api-dev/gerti/aurora 200/302).
> **Bug de deploy corrigido (staging revelou):** `.opm` em `var/packages` é sombreado pelo volume
> `znuny-var` → movido p/ `/opt/otrs/itsm-opm`. Referência: `docs/superpowers/spikes/2026-06-09-r1k-znuny-itsm-cmdb.md`.

### Deploy de anexos de vídeo + CMDB enriquecido (Spec #1L — profile `gerti` + rebuild Znuny)

**O que muda.** (A) Anexos de **vídeo** no chamado: o sidecar passa a aceitar
`.mp4/.mov/.webm/.mkv/.avi` (cap **100 MB/arquivo**, `_MAX_ATTACH_BYTES`); o GI
`GertiTicket` sobe `MaxLength` 100 MB → **200 MB** (`200000000`) p/ caber o base64
(100 MB ≈ 133 MB base64). (B) Classe **Computer** ganha `Disco`/`Memoria`/`CPU`
(o ITSM já traz CPU+OperatingSystem nativos); o `ConfigItemGet` passa a mapear
**todos** os atributos da versão (genérico) + `Created` (data de criação); portal
`/ativos/[id]` renderiza a ficha rica (SO/CPU/Memória/Disco/data).

```bash
# 1) Pull + rebuild znuny-web (novo MaxLength no GertiTicket.yml + ensure-cmdb-fields.pl
#    no provisionamento + ConfigItemGet genérico) e recria web+daemon.
#    NB: o curl dos .opm ITSM agora tem --retry/--max-time (build flakou no
#    addons.znuny.com — exit 28; endurecido em 1125a94).
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build znuny-web && $DC up -d znuny-web znuny-daemon

# 2) Atualiza o webservice GertiTicket (id 3) p/ pegar MaxLength 200 MB.
#    O console NÃO roda como root → su otrs. O yml vem bakeado em /opt/otrs/webservices/.
docker compose exec -T znuny-web su -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::Update \
     --webservice-id 3 --source-path /opt/otrs/webservices/GertiTicket.yml" -s /bin/bash otrs

# 3) Campos CMDB: ensure-cmdb-fields.pl é idempotente e JÁ roda no entrypoint
#    (após ensure-itsm.sh). Conferir: deve dizer "skip (já tem Disco/Memoria)".
docker compose exec -T znuny-web su -c "perl /opt/otrs/scripts/ensure-cmdb-fields.pl" -s /bin/bash otrs

# 4) Rebuild sidecar + portal (allowlist de vídeo, AssetDetail.created, ficha rica).
$DC build sidecar portal && $DC up -d sidecar portal

# 5) Re-seed dos ativos da Aurora (enriquece AUR-NB-001/AUR-PC-014 via VersionAdd).
#    ATENÇÃO: seed-cmdb.pl vive em /opt/otrs/var/ (volume znuny-var) e é SOMBREADO
#    pela cópia antiga — copiar a versão nova do repo do host antes de rodar:
docker compose cp scripts/seed-cmdb.pl znuny-web:/opt/otrs/var/seed-cmdb.pl
docker compose exec -T znuny-web bash -lc "chown otrs:www-data /opt/otrs/var/seed-cmdb.pl"
docker compose exec -T znuny-web su -c "perl /opt/otrs/var/seed-cmdb.pl" -s /bin/bash otrs
```

> **Ressalva Cloudflare (A3).** O plano free do Cloudflare limita o corpo da
> requisição a **~100 MB na borda** — um vídeo perto do teto pode ser rejeitado
> *antes* de chegar ao Znuny no acesso público via tunnel. O caminho interno
> (sidecar→Znuny) aceita até o `MaxLength` (200 MB base64). Para vídeos grandes,
> orientar o cliente a comprimir ou usar link externo.

> **Status (2026-06-09): mergeado na `main` (`origin/main` em `1125a94`); DEPLOYADO em
> staging e verificado ao vivo.** Gates: `perl -c` do `ConfigItemGet` + ruff/testes do
> sidecar + portal + e2e local verdes. **Staging:** `znuny-web` rebuildado (MaxLength 200 MB,
> `ensure-cmdb-fields` DefinitionID 6, ConfigItemGet genérico), `GertiTicket` atualizado,
> `sidecar`+`portal` Healthy, AUR-NB-001/AUR-PC-014 enriquecidos (VersionAdd #7/#8).
> **Prova e2e em staging (Aurora):** `ConfigItem/Get` do CI #2 retorna `Attributes`
> {OperatingSystem=Windows 11 Pro, CPU=i5-1135G7, Memoria=16 GB, Disco=512 GB SSD,
> Vendor/Model/SerialNumber} + `Created=2026-06-09 18:38:31`; CI #3 idem (Ubuntu 22.04 /
> Ryzen 5 / 32 GB / 1 TB); **IDOR**: CI da Aurora pedido como TECHNOVA → `NotFound`;
> allowlist de vídeo (`.mp4/.mov/.webm/.mkv/.avi`) + cap 100 MB live no sidecar.

### Deploy do CSAT no portal (Spec #1M — profile `gerti`)

**O que muda.** Avaliação **1–5** do cliente quando o chamado é fechado, inline no
detalhe do ticket no portal. Tabela `gerti.csat_response` (RLS, 1 resposta/ticket).
Sem mudança no Znuny — só migration + sidecar + portal.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build sidecar && $DC run --rm sidecar-migrate         # alembic upgrade head -> 0015_csat
$DC build portal  && $DC up -d sidecar sidecar-worker portal
```

> **Status (2026-06-09): DEPLOYADO em staging + e2e ao vivo.** Migration `0015_csat`
> aplicada; sidecar (178 testes) + portal (80) verdes. **e2e (Aurora, via API):**
> login 200 → `POST /v1/tickets/36/csat` (fechado) **201** `{submitted,score:5}` →
> replay **409** `csat_already_submitted` → `GET /v1/tickets/36` traz `csat:{submitted,score}` →
> ticket aberto (#39) **422** `ticket_not_closed`. Posse company-scoped via `get_ticket(CustomerID)`.

### Deploy da IA — Ollama Cloud (Spec #1N — profile `gerti`)

**O que muda.** Console do agente ganha **resumo de ticket** e **resposta sugerida** via
LLM **Ollama Cloud `gpt-oss:120b`**. Feature **opt-in** (`AI_FEATURES_ENABLED=true` +
`OLLAMA_API_KEY`); sem isso, endpoints `404` e o painel some. Tabela operacional
`gerti.ai_generation_log` (só metadados — agente/ticket/kind/model/duração/ok; **nunca**
conteúdo). Sem mudança no Znuny (`AgentTicketGet` já trazia a thread desde #1J).

> **Segredo (NUNCA commitar).** O `OLLAMA_API_KEY` vai SÓ no `.env.prod` da VPS (gitignored),
> junto de `OLLAMA_BASE_URL=https://ollama.com`, `OLLAMA_MODEL=gpt-oss:120b`, `AI_FEATURES_ENABLED=true`.
> O `docker-compose.yml` repassa essas vars ao `sidecar` (defaults vazios/false — kill-switch fail-safe).

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build sidecar && $DC run --rm sidecar-migrate     # -> 0016_ai_generation_log
$DC build admin   && $DC up -d sidecar sidecar-worker admin
# smoke do motor: curl https://ollama.com/api/chat -H "Authorization: Bearer $OLLAMA_API_KEY" \
#   -d '{"model":"gpt-oss:120b","messages":[{"role":"user","content":"ok"}],"stream":false}'
```

**Egress externo (decisão de segurança — ADR).** Resumir/sugerir **envia conteúdo de ticket
para o Ollama Cloud** (serviço externo). Mitigações: opt-in por env; só agente (`gsid_adm`);
resposta sugerida é **rascunho editável** (nunca auto-enviada ao cliente); auditoria em
`ai_generation_log`. **Prompt injection:** conteúdo de ticket é não-confiável — defesa em
camadas (spotlighting com delimitadores `<<<UNTRUSTED>>>`, sanitização dos marcadores,
**sem tools/function-calling**, saída tratada como não-confiável + escapada no front, limites
de tamanho, teste de regressão). Ver roadmap §E e `docs/superpowers/plans/2026-06-09-1n-ai-ollama.md`.

> **Status (2026-06-09): DEPLOYADO em staging + e2e ao vivo.** Migration `0016`; sidecar
> (206 testes) + admin (47) verdes. **e2e (agente william):** login 200 → `GET /v1/admin/ai/enabled`
> `{enabled:true}` → `POST /summarize {ticket_id:36}` **200** (resumo PT-BR coerente: problema/
> tentativas/estado/próximo passo, da thread real do Outlook) → `POST /suggest-reply` **200**
> (rascunho profissional com a instrução do agente) → `ai_generation_log` com 2 linhas (summary
> 3306ms / reply 3542ms, ok=t, gpt-oss:120b, sem conteúdo).

### Deploy dos Dashboards (Spec #1O — profile `gerti` + rebuild Znuny)

**O que muda.** KPIs por tenant: volume/estado/prioridade/dia, SLA estourado/risco,
CSAT médio (#1M), horas (#1B), saldo. Charts SVG próprios no portal (admin do tenant) e
console (`/analytics`, seletor de tenant + "Todos"). Nova GI op **`TicketStats`** (anti-IDOR
por `CustomerID`). OpenSearch Dashboards só para exploração **ad-hoc interna** (não exposto).
Sem migration (só agrega).

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build znuny-web && $DC up -d znuny-web znuny-daemon     # bakeia TicketStats.pm (perl -c no build)
docker compose exec -T znuny-web su -c "cd /opt/otrs && bin/otrs.Console.pl \
  Admin::WebService::Update --webservice-id 3 --source-path /opt/otrs/webservices/GertiTicket.yml" -s /bin/bash otrs
$DC build sidecar portal admin && $DC up -d sidecar sidecar-worker portal admin
```

> **Bug de deploy corrigido (staging revelou):** o overlay GertiTicket copia **cada `.pm`
> individualmente** no `znuny/Dockerfile` (não por wildcard) + um loop `perl -c` por nome.
> Op nova exige **adicionar a linha `COPY` E o nome no loop** — sem isso o GI responde
> `Can't load operation backend module ...TicketStats`. Corrigido em `dd11529`. **Checklist
> p/ futuras ops GI:** (1) criar `.pm` em `Custom/...`; (2) registrar no `GertiTicket.yml`
> (op + rota); (3) **COPY no Dockerfile** + nome no loop `perl -c`; (4) rebuild znuny-web +
> `Update --webservice-id 3`.

> **Status (2026-06-09): DEPLOYADO em staging + e2e ao vivo.** sidecar (212) + portal (94) +
> admin (50) verdes. **e2e (Aurora):** `TicketStats` GI → `Total 17, SlaBreached 9`, ByState/
> ByPriority/ByDay; **anti-IDOR**: TECHNOVA → Total 0 (sem vazar os 17 da Aurora). Portal admin
> `eduardo.salvi` → `/dashboard/metrics` com `csat.avg=5.0 {5:1}` (do #1M), `hours 1.25h`, saldos,
> `tickets.total=17`. Console `william` → `/admin/analytics?tenant_id=aurora` idem.
> OpenSearch Dashboards ad-hoc interno: ferramenta de operação (dados crus do Znuny), **sem**
> Public Hostname no tunnel — subir sob demanda no profile interno.

### Deploy das Faturas (Spec #1P — profile `gerti`)

**O que muda.** Geração de **fatura interna** (não-fiscal) a partir de um **ciclo fechado** (#1B):
PDF branded (logo/cores do tenant) + numeração sequencial por tenant + status
`open/paid/overdue/void`. Tabelas `invoice`+`invoice_line` (RLS). PDF via **WeasyPrint**
(libs nativas no Dockerfile do sidecar). Worker marca `overdue` 1x/dia. Sem mudança no Znuny.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build sidecar && $DC run --rm sidecar-migrate     # -> 0017_invoice (enum + 2 tabelas + RLS)
$DC build portal admin && $DC up -d sidecar sidecar-worker portal admin
# validar WeasyPrint NO VENV (uv run — não o python base!):
docker compose exec -T sidecar uv run python -c "import weasyprint; print(weasyprint.__version__)"
```

> **Pegadinha de verificação:** o app roda via `uv run` (venv `.venv`). Testar `import` com o
> `python` base do container dá **falso-negativo** (`ModuleNotFoundError`). Sempre use
> `uv run python -c "import weasyprint"`.

> **Status (2026-06-09): DEPLOYADO em staging + e2e ao vivo.** sidecar (224) + portal (104) +
> admin (50) verdes; WeasyPrint 69.0 importa no venv (pacote + libpango/libcairo/gdk-pixbuf).
> **e2e (Aurora, ciclos fechados Jan/Fev):** gerar fatura **201** (number 1, open) → mesmo ciclo
> **409** (idempotente) → portal admin lista → `GET /v1/invoices/1/pdf` **200 application/pdf**
> (13.7 KB) → marcar paga **paid** → 2ª fatura com `due_at` vencido + restart do worker → **overdue**.

### Deploy do Motor de Automação (Spec #1Q — profile `gerti` + rebuild Znuny)

**O que muda.** Regras no-code (gatilho de evento + condições + ações) no console; o Znuny
dispara um **Event module** (`GertiAutomation.pm`) que assina HMAC e posta os eventos de
ticket ao sidecar (`/v1/hooks/znuny/ticket-event`); o `AutomationEngine` avalia as regras do
tenant (DSL pura, allowlist) e executa ações via GI **`AgentTicketUpdate`** (nova op). Tabelas
`automation_rule`/`automation_run` (RLS). Segredo HMAC compartilhado nos 2 lados.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
# 1) Segredo HMAC (uma vez): mesmo valor nos dois lados.
SEC=$(openssl rand -hex 32)
#    a) .env.prod (gitignored, NUNCA commitar): GERTI_WEBHOOK_SIGNING_SECRET=$SEC
#    b) DB (sidecar lê daqui): UPDATE gerti.znuny_instance SET webhook_signing_secret_ref='$SEC';
# 2) Znuny: rebuild (bakeia GertiAutomation.pm + AgentTicketUpdate.pm + a XML no path REAL) + recreate.
$DC build znuny-web && $DC up -d --force-recreate znuny-web znuny-daemon
#    (entrypoint roda Maint::Config::Rebuild → carrega a Setting do Event module; ensure-automation deploya)
docker compose exec -T znuny-web su -c "cd /opt/otrs && bin/otrs.Console.pl \
  Admin::WebService::Update --webservice-id 3 --source-path /opt/otrs/webservices/GertiTicket.yml" -s /bin/bash otrs
# 3) Sidecar: migration 0018 + rebuild.
$DC build sidecar admin && $DC run --rm sidecar-migrate && $DC up -d sidecar sidecar-worker admin
```

> **Três bugs que a staging revelou no e2e do motor (corrigidos — `c91d18f`/`d953e91`):**
> 1. **XML no path errado:** o SysConfig escaneia `Kernel/Config/Files/XML/`, **NÃO** o overlay
>    `Custom/`. A Setting `Ticket::EventModulePost###9700-GertiAutomation` ficava `invalid` e o
>    event module nunca disparava. → COPY da XML no path REAL (a `.pm` continua em `Custom/`).
> 2. **`WebUserAgent->Request` não envia corpo bruto** (exige `Data` hashref/arrayref, form-encoded)
>    → o POST assinado nunca saía. Trocado por **`LWP::UserAgent`+`HTTP::Request`** assinando/enviando
>    os bytes UTF-8 exatos (casa o HMAC do sidecar sobre o corpo bruto).
> 3. **Loop de feedback:** `add_note` cria artigo → `ArticleCreate` → regra casa → `add_note` → … (137
>    runs num ticket). → guarda anti-loop: só reage a `ArticleCreate` de **`SenderType=customer`**.

> **Status (2026-06-09): DEPLOYADO em staging + e2e ao vivo.** sidecar (253) + admin (58) verdes.
> **e2e (Aurora):** regra `article_create` + `title contains "urgente"` → `set_priority "5 very high"`
> + `add_note`. Ticket "URGENTE…" → webhook **200** → `automation_run matched=t` (**1 execução**, sem
> loop) → prioridade **5 very high** + nota; ticket não-urgente → `matched=f`, prioridade normal;
> assinatura inválida → **401**; validação de regra (campo fora da allowlist) → **422**. **Checklist
> de op:** após qualquer rebuild do `znuny-web`, o `--force-recreate` faz o entrypoint rodar
> `Maint::Config::Rebuild` (carrega XML→DB); sem recreate, settings novas de XML não entram.

### Deploy do servidor do agente de inventário (Spec #1R-a — profile `gerti` + rebuild Znuny)

**O que muda.** Equipamentos se auto-registram no CMDB do cliente via um agente: tokens de
enrollment **por tenant** (`token → tenant → CustomerID` server-trusted = cliente certo
garantido), endpoints `POST /v1/agent/enroll` + `/heartbeat` (Bearer hasheado), GI **`ConfigItemUpsert`**
(escrita anti-IDOR), e UI no console (`clientes/{id}/agentes`) para o operador gerar o comando de
instalação, listar/aprovar/revogar dispositivos. Híbrido: `max_registrations`/expiração → device
`pending` (fora do CMDB) até aprovação. Credenciais só como sha256. Nova GI op → rebuild Znuny.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build znuny-web && $DC up -d --force-recreate znuny-web znuny-daemon   # bakeia ConfigItemUpsert.pm; ensure-cmdb-fields adiciona campo Fingerprint
docker compose exec -T znuny-web su -c "cd /opt/otrs && bin/otrs.Console.pl \
  Admin::WebService::Update --webservice-id 3 --source-path /opt/otrs/webservices/GertiTicket.yml" -s /bin/bash otrs
$DC build sidecar admin && $DC run --rm sidecar-migrate && $DC up -d sidecar sidecar-worker admin   # -> 0019_agent_inventory
```

> **Env var nova:** `AGENT_SERVER_URL` (base pública onde o agente bate enroll/heartbeat; default
> `https://api-dev.was.dev.br`) — usada para montar o `install_command` no console. Para o agente
> Go (#1R-b) funcionar de fora, é preciso um **Public Hostname no Cloudflare → sidecar:8001**
> (os paths `/v1/agent/*` estão na allowlist do `TenantMiddleware`, resolvem sem subdomínio).

> **Status (2026-06-10): DEPLOYADO em staging + e2e ao vivo.** sidecar (288) + admin (69) verdes;
> `ConfigItemUpsert` `syntax OK` no build; campo `Fingerprint` (DefinitionID 7); migration `0019`.
> **e2e (Aurora, curl simulando o agente):** gerar token → `enroll` FP1 **201 active** → ativo
> aparece em `/v1/assets` **só** da Aurora → re-enroll FP1 **idempotente** (não duplica) →
> `heartbeat` (secret fresco) **200** → token inválido **401** → `max_registrations=1` + FP2 →
> **`pending` (202, fora do CMDB)** → aprovar no console → entra no CMDB (`config_item_id`) →
> revogar → heartbeat **401** → desabilitar token → enroll **401**. (Nota: re-enroll rotaciona o
> `agent_secret` — o agente real enrolla 1× e guarda o secret.)

### Deploy do agente Go + distribuição (Spec #1R-b — profile `gerti`)

**O que muda.** O binário Go (`apps/agent/`) que roda na máquina do cliente + sua distribuição
pelo sidecar. O operador copia o comando no console (`clientes/{id}/agentes`) e roda na máquina:
`curl <server>/v1/agent/install.sh | sh -s -- --enroll-token=<tok> --server=<server>`.

```bash
# 1) Buildar os binários (precisa Go 1.22+) → apps/sidecar/agent-dist/ (gitignored)
cd apps/agent && bash build.sh ../sidecar/agent-dist   # linux-amd64, windows-amd64.exe, darwin-arm64
# 2) Levar os binários ao host de staging (gitignored → scp, não git):
scp apps/sidecar/agent-dist/* gc:~/ground-control/apps/sidecar/agent-dist/
# 3) Build do sidecar DEPOIS dos binários (Dockerfile bakeia agent-dist → /app/agent-dist):
ssh gc 'cd ~/ground-control && DC="docker compose --env-file .env --env-file .env.prod --profile gerti" && \
  git pull origin main && $DC build sidecar && $DC up -d sidecar'
```

> **Empacotamento:** o build context do `sidecar` é `./apps/sidecar`, que **não alcança** `apps/agent/`.
> Por isso os binários são pré-buildados em `apps/sidecar/agent-dist/` (gitignored) antes do `docker build`.
> Alternativa futura: mudar o context p/ a raiz + multi-stage Go no Dockerfile.

> **Exposição pública (FEITO em staging):** os endpoints `/v1/agent/*` (enroll/heartbeat/install.sh/
> download) estão atrás do **Public Hostname Cloudflare `api-dev.was.dev.br` → `sidecar:8001`**
> (= `AGENT_SERVER_URL`). Os paths `/v1/agent/*` estão na allowlist do `TenantMiddleware` (resolvem sem
> subdomínio; o tenant vem do token). Sem auth de sessão por design (a credencial é o Bearer).

> **Status (2026-06-10): VALIDADO em staging (agente real).** `go test`/`go vet` verdes;
> cross-compile dos 3 alvos OK; router de distribuição (8 testes). **e2e (container Debian limpo na
> rede `ground-control_app`, simulando a máquina do cliente):** `gc-agent enroll --server
> http://sidecar:8001 --enroll-token <token do console>` → **status active**, `agent.conf` (0600)
> gravado com `agent_id`+`agent_secret` e **sem o enroll_token** (descartado) → `gc-agent run` inicia
> o heartbeat → no servidor o `device_agent` fica `active` (last_seen setado) e o ativo
> (`fd5a8d5098f9`, OS Debian 12 coletado pelo agente) aparece no **CMDB da Aurora**.
> **e2e PÚBLICO (via Cloudflare, 2026-06-10):** container Debian limpo baixou o binário de
> `https://api-dev.was.dev.br/v1/agent/download/linux-amd64` e fez enroll+heartbeat por
> `https://api-dev.was.dev.br` → device `active`, ativo no CMDB da Aurora — o caminho real de uma
> máquina de cliente. Resta apenas o e2e do `install.sh`+systemd numa **VM real** (o teste em
> container rodou o binário direto, não o serviço systemd).

### Deploy do assistente de escrita por IA (Spec #1S — profile `gerti`)

**O que muda.** Botão **"✨ Melhorar com IA"** no `/tickets/novo` do portal: o cliente escreve o
problema, a IA (Ollama #1N) devolve título + descrição estruturados (rascunho editável). Endpoint
`POST /v1/ticketing/assist` (cliente, opt-in `AI_FEATURES_ENABLED`, rate-limit 20/h, anti-injeção).
Sem mudança no Znuny.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build sidecar portal && $DC run --rm sidecar-migrate && $DC up -d sidecar sidecar-worker portal   # -> 0020_ai_assist_kind
```

> **Status (2026-06-10): DEPLOYADO em staging + e2e ao vivo.** sidecar (314) + portal (111) verdes;
> migration `0020`. **e2e (Aurora):** `form-meta.ai_assist_enabled=true`; `POST /v1/ticketing/assist`
> "Nao imprime"/"resolva" → **200** com `{title:"Não imprime", body:"Problema:… Início: Não
> informado…"}` (estruturou sem inventar fatos); body vazio → **400**; auditoria em `ai_generation_log`
> (kind=`assist`, customer_login, gpt-oss:120b). Kill-switch `AI_FEATURES_ENABLED` off → botão some + 404.

## Backup (a definir em prod)

- Postgres: `pg_dump` agendado → storage externo (não implementado nesta fase)
- `znuny-var` (anexos): snapshot de volume
- Ação futura: pgBackRest + retenção, documentar aqui quando implementado.

## Observabilidade (a definir)

Logs via `docker compose logs` por enquanto. Stack de observabilidade (OTEL/Grafana) é fase posterior — documentar aqui quando entrar.

### Deploy da Contratação + Asaas (Spec #2 — profile `gerti`)

Aditivo/profile-gated (padrão D13/D15): novo serviço `checkout` + migration `0021`
+ rebuild do `sidecar` (traz `/v1/checkout/*` e o webhook). **Feature opt-in**: sem
`ASAAS_ENABLED=true` + `ASAAS_API_KEY` o checkout responde 404 (deploy seguro a
qualquer momento; liga-se quando a chave Asaas estiver no `.env.prod`).

**Pré-requisitos (humano, one-time, em `~/ground-control/.env.prod` — gitignored):**
- `ASAAS_API_KEY` (sandbox primeiro: conta Asaas sandbox), `ASAAS_BASE_URL`
  (`https://api-sandbox.asaas.com/v3` sandbox / `https://api.asaas.com/v3` prod),
  `ASAAS_WEBHOOK_TOKEN` (forte; cadastrar IGUAL no painel Asaas), `ASAAS_ENABLED=true`.
- Catálogo: ao menos 1 linha em `gerti.plan` (public+active) e a conta default.

```bash
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"
git pull origin main
$DC build sidecar && $DC run --rm sidecar-migrate      # -> 0021_contratacao_asaas
$DC build checkout && $DC up -d sidecar sidecar-worker checkout && $DC ps
# seed de um plano (exemplo) via psql (gerti_admin_user/superuser):
#   INSERT INTO gerti.plan (slug,name,audience,contract_type,billing_mode,price_cents,cycle,initial_amount_brl)
#   VALUES ('starter','Starter','msp','saas_product','subscription',149000,'MONTHLY',1490.00);
```

**Webhook Asaas:** cadastrar no painel a URL `https://api-dev.was.dev.br/v1/hooks/asaas/payment`
com o header `asaas-access-token` = `ASAAS_WEBHOOK_TOKEN`, eventos de PAYMENT.

**Ingresso Cloudflare** (read-modify-write, padrão D3/D15): splice de
`contratar.was.dev.br → http://checkout:3000` ANTES do catch-all 404 + DNS CNAME
proxied. Guard: não remover os hostnames existentes.

**Verificação:** `curl https://api-dev.was.dev.br/v1/checkout/plans` (200 com
ASAAS_ENABLED; 404 sem). e2e sandbox: criar sessão → simular webhook
`PAYMENT_RECEIVED` → tenant provisionado (limpar throwaway).

**Rollback (checkout só):** `$DC stop checkout`; reverter sidecar: `git checkout
<sha> -- apps/sidecar docker-compose.yml && $DC build sidecar && $DC up -d sidecar`.
Migration reversa: `$DC run --rm sidecar-migrate uv run alembic downgrade -1`.
**NUNCA** `make reset`.

> **Status (2026-06-20):** implementado (backend + app `apps/checkout`), gates
> verdes (ruff/mypy/319 testes; build+lint do checkout). Deploy per runbook;
> **pendente humano:** chave Asaas sandbox no `.env.prod` + cadastro do webhook +
> ingress `contratar.*`. Sem a chave, o checkout fica 404 (fail-safe).

### Deploy da paridade de interface (Spec #3 — profile `gerti`)

**O que muda.** Seis subsistemas novos no portal e no console — base de
conhecimento, catálogo de serviços, notificações + preferências, identidade visual
editável, trilha de auditoria e saúde do sistema + busca global. **Sem mudança no
Znuny** (nenhuma op GI nova, nenhum rebuild de `znuny-web`) e **sem serviço novo**
no compose. Três migrations (`0022`–`0024`) e rebuild de `sidecar`, `portal` e
`admin`. Decisões em [`DECISIONS.md`](DECISIONS.md) D20; arquitetura em
[`ARCHITECTURE.md`](ARCHITECTURE.md).

**Pré-requisitos:** nenhum segredo novo, nenhuma variável de ambiente nova.

```bash
ssh gc 'cd ~/ground-control && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) migrations 0022 → 0023 → 0024 (encadeadas; sidecar-migrate roda como
#    gerti_admin_user, BYPASSRLS, dono do DDL). Aguardar Exit 0.
ssh gc "cd ~/ground-control && $DC build sidecar && $DC run --rm sidecar-migrate"

# 2) app + worker + fronts
ssh gc "cd ~/ground-control && $DC build portal admin && \
        $DC up -d sidecar sidecar-worker portal admin && $DC ps"

# 3) prova de RLS das tabelas novas (zero-tolerância): as 4 tenant-scoped
#    precisam ter relrowsecurity E relforcerowsecurity = t; audit_log é
#    operacional e fica FALSE de propósito (só AdminSessionLocal a lê).
ssh gc 'cd ~/ground-control && docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select relname,relrowsecurity,relforcerowsecurity from pg_class c \
   join pg_namespace n on n.oid=relnamespace \
   where nspname='"'"'gerti'"'"' and relname in \
   ('"'"'kb_article'"'"','"'"'service_catalog_item'"'"','"'"'notification'"'"','"'"'user_preference'"'"','"'"'audit_log'"'"');"'

# 4) fail-closed de verdade: como gerti_sidecar, sem o GUC app.current_tenant,
#    toda tabela nova tem que devolver zero linha.
ssh gc 'cd ~/ground-control && docker compose exec -T postgres psql -U gerti_sidecar -d "$POSTGRES_DB" \
  -c "select count(*) from gerti.kb_article;"'   # → 0

# 5) serviços anteriores intactos
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsS https://aurora.was.dev.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsS https://technova.was.dev.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi 'login' && echo ADMIN_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**Roteiro de teste manual:** [`../docs/COMO-TESTAR-PARIDADE-INTERFACE.md`](../docs/COMO-TESTAR-PARIDADE-INTERFACE.md).

**Rollback (portal/admin/sidecar; Znuny intocado):**

```bash
$DC stop portal admin          # as telas novas somem; Znuny e worker seguem
git checkout <sha-anterior> -- apps/sidecar apps/portal apps/admin
$DC build sidecar portal admin && $DC up -d sidecar portal admin
# migration reversa, se necessário (uma por vez, na ordem inversa):
$DC run --rm sidecar-migrate uv run alembic downgrade -1
```

**NUNCA** `make reset` (destrói o DB Znuny compartilhado).

> **Status (2026-07-30): DEPLOYADO em staging e verificado ao vivo.** Branch
> `feature/spec-3-paridade-grounddesk` (`43147d9`) na VPS; migrations `0022`→`0025`
> aplicadas; `sidecar`, `sidecar-worker`, `portal` e `admin` reconstruídos e de pé.
> **Provas colhidas:** RLS das 4 tabelas de negócio com `relrowsecurity` e
> `relforcerowsecurity` = `t` (`audit_log` = `f`, por desenho); fail-closed real —
> `gerti_sidecar` sem o GUC lê **0 linhas** de `kb_article`; `audit_log` responde
> **`permission denied`** ao papel de runtime (após a `0025`); os 6 endpoints novos
> respondem **401** sem sessão; login de agente real (`william`) → `/v1/admin/system/health`
> com sondas reais (db 2 ms, Znuny GI 67 ms `pong`, IA habilitada, Asaas desligado),
> `/v1/admin/audit-logs?limit=20` **200** e `?limit=500` **422**, `/v1/admin/search` **200**.
> As 8 páginas novas (5 no portal, 3 no console) respondem **302 → login** sem sessão
> (rota existe e a guarda funciona). Serviços anteriores intactos: znuny 200,
> api-dev 200, aurora 302, technova 302, gerti 200, landing 200.
>
> **Achado operacional revelado pelo próprio painel novo, e o falso alarme que ele
> gerou.** `worker.last_sync_at` (então única leitura da sonda) estava em
> **2026-06-24** — lag de ~35 dias — sugerindo worker travado. Investigação ao
> vivo mostrou o oposto: o cursor `gerti.consumption_sync_cursor` estava **à
> frente** do lançamento de horas mais recente no Znuny (`time_accounting`);
> não havia nada pendente. O worker é silencioso por desenho (só loga quando
> reconcilia algo ou em erro) — um worker vivo e ocioso ficava indistinguível de
> um travado, porque `updated_at` do cursor significa "última vez que
> reconciliou", não "última vez que verificou".
>
> **Correção (migration `0026_worker_heartbeat`):** o worker agora grava
> `gerti.worker_heartbeat` a CADA tick, com trabalho ou sem. A sonda passou a
> avaliar essa prova de vida (`last_tick_at`, `ok` = heartbeat mais novo que 3×
> `reconcile_interval_seconds`) em vez do cursor, e devolve os dois tempos
> (`last_tick_at`/`last_sync_at`) com nomes honestos — cursor velho + heartbeat
> fresco agora reporta `ok: true` com a mensagem "sem lançamentos novos para
> processar", em vez de soar como travamento. Detalhe do contrato em
> [`ARCHITECTURE.md`](ARCHITECTURE.md) "Saúde do sistema".

### Deploy da capa de administração do Znuny (Spec #4 — profile `gerti` + rebuild Znuny)

**O que muda.** O console passa a administrar o próprio Znuny: filas, SLAs,
serviços, tipos/estados/prioridades, classes de CI, agentes/permissões e
calendário/jornada. **15 módulos GI novos** no webservice `GertiAdmin` (rebuild do
`znuny-web` obrigatório), rotas `/v1/admin/znuny/*` no sidecar e 7 telas no console.
**Nenhuma migration** — a spec não persiste nada (D21).

**Pré-requisitos:** nenhum segredo novo. Reusa `ZNUNY_ADMIN_WS_URL` e
`ZNUNY_WS_TOKEN` (`GertiAdmin::AccessToken`), já presentes desde o #1G-a.

```bash
ssh gc 'cd ~/ground-control && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild (bakeia os 15 .pm; perl -c é gate de build) e recria web+daemon.
#    NOTA: recria o core Znuny (downtime curto). Provisionamento é idempotente (D6).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) CRÍTICO — atualizar o webservice GertiAdmin (já existe em prod desde #1G-a).
#    Admin::WebService::Update exige --webservice-id (NÃO --name) nesta versão.
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && \
   WSID=\$(bin/otrs.Console.pl Admin::WebService::List | sed -n \"s/.*GertiAdmin (\\([0-9]\\+\\)).*/\\1/p\"); \
   bin/otrs.Console.pl Admin::WebService::Update --webservice-id \"\$WSID\" \
     --source-path /opt/otrs/webservices/GertiAdmin.yml"'
#   GUARD: os 3 webservices seguem presentes (nenhum pode sumir):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'

# 3) sidecar + console (SEM migration nova):
ssh gc "cd ~/ground-control && $DC build sidecar admin && $DC up -d sidecar sidecar-worker admin && $DC ps"
```

**Verificação — a que importa é a de invariante:**

```bash
# nenhuma tabela de configuração do Znuny foi criada no schema gerti.
# CUIDADO: `znuny_instance` existe desde a migration 0001 — é o registro de
# instâncias do modelo multi-tenant, NÃO configuração. Por isso ela é excluída.
ssh gc 'cd ~/ground-control && set -a && . ./.env && set +a && \
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c \
  "select count(*) from information_schema.tables where table_schema='"'"'gerti'"'"' \
   and table_name in ('"'"'znuny_queue'"'"','"'"'znuny_sla'"'"','"'"'znuny_service'"'"', \
                      '"'"'znuny_state'"'"','"'"'znuny_priority'"'"','"'"'znuny_agent'"'"', \
                      '"'"'znuny_ci_class'"'"','"'"'znuny_calendar'"'"');"'   # → 0

# e a prova mais forte: a cabeça da cadeia de migrations não mudou com a #4.
ssh gc 'cd ~/ground-control && docker compose run --rm sidecar-migrate \
  uv run alembic current 2>&1 | tail -2'      # → 0025_audit_log_revoke_app

# endpoints fail-closed sem sessão de agente:
ssh gc 'cd ~/ground-control && docker compose exec -T sidecar sh -lc \
  "curl -s -o /dev/null -w \"objects=%{http_code} calendar=%{http_code}\\n\" \
   http://127.0.0.1:8001/v1/admin/znuny/objects/Queue"'   # → 401

# objeto fora da allowlist é 404, não 500:
#   GET /v1/admin/znuny/objects/Kernel::System::Ticket  → 404
```

Mais o e2e no console: abrir `/znuny/filas` e conferir que lista as filas **reais**
do Znuny; criar uma fila throwaway; invalidá-la (`ValidID=2`); conferir a linha
correspondente em `/auditoria`; e remover o throwaway pelo painel do Znuny.

> **Cuidado com o Bloco D (calendário).** É o único ponto do console que grava em
> SysConfig e dispara deploy de configuração. Antes de testar em staging, anote a
> jornada atual para poder restaurá-la. Se a gravação falhar, o backend libera o
> `SettingLock` e **nada é aplicado** — pode tentar de novo com segurança.

**Rollback (console/sidecar; Znuny volta pelo rebuild do sha anterior):**

```bash
$DC stop admin                       # as telas /znuny/* somem
git checkout <sha-anterior> -- apps/sidecar apps/admin znuny/
$DC build znuny-web sidecar admin && $DC up -d znuny-web znuny-daemon sidecar admin
```

Nenhuma migration para reverter. **NUNCA** `make reset`.

> **Status (2026-07-30): DEPLOYADO em staging e verificado ao vivo.** Branch
> `feature/spec-3-paridade-grounddesk` (`1bc0f2f`); imagem Znuny rebuildada com os
> **16 módulos GI** (`perl -c` verde), `znuny-web`/`znuny-daemon` recriados
> (Healthy); `GertiAdmin` atualizado por `--webservice-id 2` com os 3 webservices
> intactos (`GertiCustomerAuth` 1 + `GertiAdmin` 2 + `GertiTicket` 3);
> `sidecar`+`admin` rebuildados e Healthy. **Sem migration** — a cabeça da cadeia
> segue `0025`.
>
> **Provas colhidas:** zero tabelas de configuração do Znuny no schema `gerti`;
> os 5 grupos de endpoint respondem **401** sem `gsid_adm`; login de agente real
> (`william`) → `GET /objects/Queue` devolve as **filas reais da instância**
> (Postmaster, Raw, Junk…), `GET /calendar` devolve a **jornada real**
> (`TimeWorkingHours` seg–sex 8–20); `objects/Kernel::System::Ticket` → **404**
> (o dispatcher não pode ser induzido a carregar classe Perl arbitrária);
> `?calendar=99` → **404**. As 7 telas respondem 302→login. Serviços anteriores
> intactos: znuny 200, api-dev 200, aurora 302, technova 302, console 200,
> landing 200.
>
> **Duas quebras de integração corrigidas antes do deploy** (achadas pela revisão
> adversarial, nunca chegaram a subir): o contrato do calendário divergia entre
> tela e router — a tela do Bloco D estava 100% não-funcional; e "Definir senha"
> era tela sem backend, sempre 422. Ambas fechadas em `6946a44`.
>
> **Pendente de e2e manual:** o caminho de falha do `SettingLock` (gravação de
> calendário que falha no meio) foi verificado por leitura de código e por teste
> com GI mockado, **não** contra um Znuny real. Exercitar pelo roteiro
> `docs/COMO-TESTAR-ADMIN-ZNUNY.md`, Parte 6.

> **Status (2026-07-30, atualização): MERGEADO NA `main` e rodando a partir dela.**
> `main` em `58cd6d3`; o host de staging saiu do branch e está na `main`. Todos os
> serviços Healthy. **Verificação final dos quatro blocos, autenticada:**
> Bloco A — `Queue`/`SLA`/`Service`/`Type`/`State`/`Priority` todos **200**;
> Bloco B — classes de CI **200** listando as 5 nativas (Computer, Hardware,
> Location, Network, Software) e a definição da `Computer` **200** com o YAML real;
> Bloco C — agentes e grupos **200**; Bloco D — calendário **200** (padrão e
> `Calendar3`). **Guardas:** classe Perl arbitrária → **404**, classe de CI
> inexistente → **404**, sufixo de calendário inválido → **404**, senha curta →
> **422**.
>
> **Três bugs achados só na verificação ao vivo** (todos os gates estavam verdes):
> 1. Quatro caminhos GI do cliente Python divergiam das rotas do `GertiAdmin.yml`
>    — classes de CI davam **500** no Znuny. Os testes não pegaram porque
>    **codificavam o caminho errado**. Fechado com `test_gi_routes_match_webservice.py`,
>    que lê o `RouteOperationMapping` e confronta com os caminhos realmente usados,
>    nos dois sentidos.
> 2. `AdminCiClassList` devolve `Classes`, o cliente lia `Items` — a lista vinha
>    **vazia com 200**, modo de falha mais traiçoeiro que o 500: o operador
>    concluiria que o CMDB está vazio.
> 3. Leitura de recurso inexistente devolvia **422**, o mesmo código do
>    `DefinitionCheck` reprovando — indistinguível de "definição inválida". Agora é
>    404 com o recurso nomeado.
>
> **Pendências declaradas:** (a) ~~o caminho de falha do `SettingLock` segue
> verificado por leitura de código e teste mockado, não contra Znuny vivo — Parte 6
> do `COMO-TESTAR-ADMIN-ZNUNY`~~ — **BAIXADA em 2026-08-15**: exercitada contra o
> Znuny vivo do staging no deploy da Onda 0 (T-R13.1), com falha injetada de
> verdade na 2ª das 3 gravações; ver a seção da Onda 0 no fim deste arquivo;
> (b) `contratar.was.dev.br` é **NXDOMAIN** desde a
> Spec #2 (ingress nunca criado, falta token Cloudflare) — o serviço `checkout`
> responde 200 internamente; (c) ~~o `sidecar-worker` não reconcilia consumo desde
> 2026-06-24, pré-existente, revelado pelo painel de saúde novo~~ — **falso
> alarme, investigado e corrigido**: não havia lançamentos novos a reconciliar
> (cursor já estava à frente do `time_accounting` do Znuny), o worker seguia
> vivo e ocioso. A sonda antiga confundia isso com travamento por olhar só o
> cursor; ver correção via `worker_heartbeat` (migration `0026`) no achado
> logo acima.

> **Login por e-mail ou usuário (2026-07-30) — DEPLOYADO e verificado.** Os dois
> lados aceitam ambos os formatos. **Prova ao vivo:** console com
> `williamalvesroot@gmail.com` → 200 e a sessão carrega `agent_login: "william"`
> (o login **canônico**, não o e-mail) — a sessão vira o `AgentLogin` de toda
> operação GI, então guardar o e-mail faria a pessoa entrar e todas as telas
> quebrarem depois; `bruno.cardoso@gerti.com.br` → 200; e-mail inexistente, senha
> errada e e-mail ambíguo → **o mesmo 401**, sem vazar enumeração. Portal:
> `eduardo.salvi` e o e-mail completo, ambos 200.
>
> **A causa raiz do login "impossível" era de front-end:** o campo era
> `type="email"`, e o navegador barrava o envio do login curto **antes de qualquer
> requisição sair** — sem erro de servidor, sem log, sem nada para investigar.
> Guards nos dois apps (`test/login-field.test.ts`) travam a regressão.

### Deploy da Onda 0 da campanha "Recursos Administrativos" (profile `gerti` + rebuild Znuny)

**O que muda.** Cinco defeitos que já estavam quebrados e apareceram ao cruzar os
requisitos do vídeo do Kleber com o código
([`../docs/CAMPANHA-RECURSOS-ADMINISTRATIVOS.md`](../docs/CAMPANHA-RECURSOS-ADMINISTRATIVOS.md)):

| Camada | O que muda | Ação de deploy |
|---|---|---|
| **Znuny** | 4 módulos GI alterados: `GertiAdmin/AdminSpec.pm`, `GertiAdmin/AdminObjectList.pm`, `GertiTicket/TicketGet.pm`, `GertiTicket/TicketReply.pm` | **rebuild obrigatório da imagem** — os `.pm` entram por `COPY` em build time; sem rebuild a criação de fila continua quebrada e a guarda de posse não vale |
| **sidecar** | fatura de contrato não-crédito, ciclo, `domain/ticket_scope.py` (novo), busca, listas de apoio, dependência `reportlab` | rebuild + up |
| **admin** | tela de filas com os 4 campos obrigatórios da fila | rebuild + up |
| **portal** | nada | **não** precisa recriar |

**Nenhuma migration** — nenhuma tabela nova; `totals` é JSONB e as chaves novas
são aditivas. A cabeça da cadeia segue `0026_worker_heartbeat`; se `alembic
heads` apontar outra coisa, **pare e investigue**.

**Nenhuma operação GI nova e nenhum `.pm` novo** — os webservices
`GertiAdmin`/`GertiTicket` **não** precisam de re-import (`Admin::WebService::Update`).
Ainda assim, confira como guarda que os **três** seguem presentes.

**Pré-requisitos (humano):** nenhum. Nenhum segredo novo, `.env.prod` intocado,
nenhum hostname novo (ingress Cloudflare **não** se mexe nesta onda).

```bash
ssh gc 'cd ~/ground-control && git fetch origin && git checkout campanha/onda-0-defeitos && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 0) guarda ANTES de subir: nenhuma migration pendente.
ssh gc "cd ~/ground-control && $DC run --rm sidecar-migrate uv run alembic current | tail -1"
ssh gc "cd ~/ground-control && $DC run --rm sidecar-migrate uv run alembic heads   | tail -1"
#    → os dois devem dizer 0026_worker_heartbeat (head)

# 1) Znuny: rebuild (bakeia os 4 .pm; perl -c é gate de build) e recria web+daemon.
#    NOTA: recria o core Znuny (DOWNTIME CURTO). Provisionamento é idempotente (D6) —
#    conferir no log do boot a linha que prova que não houve re-init destrutivo.
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"
ssh gc 'cd ~/ground-control && docker compose logs znuny-web --since 10m | grep -i "schema already present"'
#    → [entrypoint:web] Znuny schema already present — skipping DB init (idempotent).

# 2) GUARD (não há re-import; só conferência): os 3 webservices seguem presentes.
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List | grep -iE \"GertiCustomerAuth|GertiAdmin|GertiTicket\""'

# 3) sidecar + console (SEM migration nova). O portal NÃO é recriado.
ssh gc "cd ~/ground-control && $DC build sidecar admin && $DC run --rm sidecar-migrate && \
        $DC up -d sidecar sidecar-worker admin && $DC ps"

# 4) reportlab (T-R0.6) precisa existir NO VENV — `uv run`, nunca o python base:
ssh gc 'cd ~/ground-control && docker compose exec -T sidecar uv run python -c \
  "import reportlab, weasyprint; print(reportlab.Version, weasyprint.__version__)"'
```

**Verificação — serviços anteriores intactos:**

```bash
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsSL https://aurora.was.dev.br/ | grep -qi 'Aurora' && echo AURORA_OK
curl -fsSL https://technova.was.dev.br/ | grep -qi 'TechNova' && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi 'login' && echo ADMIN_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

> **Pegadinha das duas verificações de portal:** `aurora`/`technova` respondem
> **302 → /login** na raiz; sem `-L` o `grep` do branding não casa e parece falha.
> Use `curl -fsSL`.

**Verificação — o que esta onda corrigiu (e2e ao vivo):**

1. **Criar fila pelo console.** Login no console → `GET
   /api/admin/znuny/objects/Queue` tem que trazer `support.SystemAddressList`,
   `SalutationList` e `SignatureList` **preenchidas** (se vierem vazias, o deploy
   do sidecar não pegou — `_SUPPORT_LIST_KEYS` é filtro, não documentação) →
   `POST` da fila com os 4 ids obrigatórios → **201** → conferir no painel nativo
   (`AdminQueue;Subaction=Change;QueueID=<id>`) que os selects vieram marcados.
   Contraprova: `POST` sem os campos → **422** nomeando os que faltam.
2. **Guarda de posse do chamado.** Usuário de papel `helpdesk` pedindo
   `/tickets/<id>` de colega da mesma empresa → **404** (nunca 403, nunca o
   chamado); a busca do portal **não** devolve o chamado do colega; o papel
   `admin` do portal continua vendo a empresa inteira. `reply` e `csat` do
   chamado alheio → **404** também.
3. **T-R13.1 — caminho de falha da trava de calendário.** Ver o bloco abaixo.

> **Como forçar a falha da 2ª das 3 gravações do calendário, com segurança.**
> `PUT /v1/admin/znuny/calendar` grava **três** settings em sequência
> (`TimeWorkingHours` → `TimeVacationDays` → `TimeVacationDaysOneTime`) e não
> existe transação que abranja os três. Para exercitar a falha **depois** do
> `SettingLock` (que é onde mora o risco de trava presa), o caminho mais cirúrgico
> é um **trigger de injeção** no Postgres, escopado por NOME de setting, sobre um
> **calendário não usado** (confira antes: `select calendar_name from queue` /
> `from sla` — nenhum pode apontar para o alvo):
>
> ```sql
> CREATE OR REPLACE FUNCTION gerti_tr131_inject() RETURNS trigger AS $$
> BEGIN
>   IF NEW.name = 'TimeVacationDays::Calendar9' THEN
>     RAISE EXCEPTION 'falha injetada na 2a gravacao';
>   END IF;
>   RETURN NEW;
> END; $$ LANGUAGE plpgsql;
> CREATE TRIGGER gerti_tr131_inject_trg BEFORE INSERT OR UPDATE ON sysconfig_modified
>   FOR EACH ROW EXECUTE FUNCTION gerti_tr131_inject();
> ```
>
> `ModifiedSettingAdd` insere em `sysconfig_modified` **antes** de
> `sysconfig_modified_version`, então a exceção aborta cedo e **não deixa órfão**.
> Depois do teste: `DROP TRIGGER`/`DROP FUNCTION` e devolva o calendário ao estado
> original com `SettingReset` (lock → reset → unlock → deploy), que apaga a linha
> de `sysconfig_modified` e restaura o default de fábrica — mais limpo que
> regravar o valor antigo.

**Rollback (escrito antes de subir; sha anterior do staging = `214842b`):**

```bash
$DC stop admin                                        # as telas novas somem
git checkout 214842b -- apps/sidecar apps/admin znuny/    # (ou: git checkout main)
$DC build znuny-web sidecar admin
$DC up -d znuny-web znuny-daemon sidecar sidecar-worker admin
```

**Nenhuma migration a desfazer** (a cabeça não mudou: `0026_worker_heartbeat`);
nenhum webservice a reimportar; `.env.prod` e o ingress Cloudflare não foram
tocados. **NUNCA** `make reset`.

> **Status (2026-08-15): DEPLOYADO em staging e verificado ao vivo.** Branch
> `campanha/onda-0-defeitos` no host — **não** mergeada na `main`. O **código**
> deployado (imagens construídas) é o de `42d38af`; o host ficou em `318c7ac`, que
> é este próprio documento e não altera uma linha de código.
> Imagem Znuny rebuildada com os 4 `.pm` (`perl -c` verde dentro do container —
> note que `AdminObjectList.pm` precisa de `-ICustom` no `perl -c` manual, porque
> carrega o `AdminSpec` irmão do overlay), `znuny-web`/`znuny-daemon` recriados e
> Healthy, boot com `Znuny schema already present — skipping DB init (idempotent)`
> (sem re-init destrutivo). `sidecar`, `sidecar-worker` e `admin` recriados e
> Healthy; `portal` **não** foi tocado (nada mudou nele) e seguiu de pé o tempo
> todo. `alembic current` = `heads` = **`0026_worker_heartbeat`** antes e depois.
> Os 3 webservices intactos (`GertiCustomerAuth` 1 + `GertiAdmin` 2 + `GertiTicket` 3).
> `reportlab 5.0.0` + `weasyprint 69.0` importam no venv.
>
> **Prova (a) — criar fila pelo console, o defeito principal.** `GET
> objects/Queue` trouxe `support` com as **7** listas, incluindo as três que o
> sidecar descartava: `SystemAddressList {1: Znuny System <znuny@localhost>}`,
> `SalutationList {1: …}`, `SignatureList {1: …}`. `POST` da fila
> `ZZ-TESTE-ONDA0` → **201** (`ID 10`, com `SystemAddressID/SalutationID/
> SignatureID = 1`). No **painel nativo** (`AdminQueue`) a fila aparece na lista e
> o formulário de edição traz os selects marcados: `SystemAddressID →
> znuny@localhost`, `SalutationID → system standard salutation (en)`,
> `SignatureID → system standard signature (en)`. Contraprova no mesmo endpoint,
> sem os campos: **422** `AdminObjectAdd: required field(s) missing for 'Queue':
> SystemAddressID, SalutationID, SignatureID, FollowUpID` — é exatamente o erro
> que a tela batia antes, agora impossível de emitir pela UI.
>
> **Prova (b) — guarda de posse.** Chamado **49** ("Outlook travando ao anexar
> arquivos grandes", dono `carla.dorneles`, empresa AURORA). Como
> `helpdesk@auroramoveis.com.br` (papel `helpdesk`): `GET /tickets/49` → **404**;
> busca `?q=Outlook` → `{"tickets":[]}`. Controle positivo com `carla.dorneles`
> (também `helpdesk`, dona do 49): busca devolve **só** o 49 e **não** o 36 do
> colega; `GET /tickets/49` → **200**, `GET /tickets/36` → **404**;
> `POST /tickets/36/reply` e `POST /tickets/36/csat` → **404**
> `ticket_not_found` (nada foi escrito no chamado alheio). Regressão do admin:
> `eduardo.salvi@auroramoveis.com.br` (papel `admin`) lista os **22** chamados da
> AURORA e abre o 49 → **200**.
>
> **Prova (c) — T-R13.1, o caminho de falha do `SettingLock`, contra o Znuny
> real.** Falha injetada na **2ª** das 3 gravações (trigger escopado a
> `TimeVacationDays::Calendar9`, calendário não referenciado por nenhuma fila/SLA).
> `PUT /calendar` → **422** com o corpo nomeando os dois lados:
> `{"applied":["TimeWorkingHours::Calendar9"],"failed_setting":
> "TimeVacationDays::Calendar9"}`. `gerti.audit_log` registrou a aplicação
> parcial: *"calendário 9: aplicação PARCIAL (1/3) — falhou em
> TimeVacationDays::Calendar9"*, com `applied`, `failed_setting` e `error` no
> metadata. **E a asserção que importa:** o `SettingLock` do setting que falhou
> ficou **LIBERADO** — `exclusive_lock_guid = '0'`, `exclusive_lock_user_id` e
> `exclusive_lock_expiry_time` nulos; zero locks presos em **toda** a
> `sysconfig_default`. A 1ª gravação ficou aplicada e deployada (`is_dirty=0`) e a
> 3ª nem foi tentada, como o contrato manda. Throwaways desfeitos: trigger e
> função removidos, `Calendar9` devolvido ao default por `SettingReset` (o `GET`
> do calendário voltou **byte a byte igual** ao snapshot pré-teste; o calendário
> **padrão** nunca foi tocado, também conferido por diff).
>
> **Limpeza:** fila `ZZ-TESTE-ONDA0` **invalidada** (`ValidID=2`) pelo console —
> o Znuny invalida, não exclui, então ela **fica** na base como fila inválida
> (id 10), que é o estado terminal esperado. Nenhum chamado de teste foi criado.
> As linhas de `gerti.audit_log` do teste permanecem (a trilha é append-only por
> desenho). O `Calendar9` voltou ao estado de fábrica.
>
> **Dois achados que só a execução ao vivo revelou (nenhum é regressão desta
> onda; ambos são pré-existentes e ficam registrados como dívida):**
>
> 1. **A gravação do calendário estoura o timeout do cliente.** Uma chamada
>    `AdminSysConfigSet` neste staging leva **~12 s** (medido: `tempo=11.98s`,
>    `http=200`, `Deployed=1`), contra o `_TIMEOUT = 10.0` de
>    `znuny_admin_sysconfig.py`. Resultado: o console devolve **503** com
>    `{"applied":[],"failed_setting":"TimeWorkingHours::Calendar9"}` e **mensagem
>    vazia** (o `str()` de um `httpx.ReadTimeout` é vazio) numa gravação que o
>    Znuny pode estar concluindo do outro lado. É o modo de falha que a própria
>    tela existe para evitar — "não apliquei nada" quando talvez tenha aplicado.
>    Nas três repetições observadas nada chegou a ser gravado (`change_time`
>    inalterado) e **nenhum lock ficou preso**, mas isso é dependente de tempo,
>    não garantido. Correção óbvia: subir o timeout dessa chamada (a operação faz
>    `ConfigurationDeploy`, é lenta por natureza) e nunca deixar a mensagem vazia.
> 2. **O papel do portal é resolvido pela string exata do login.**
>    `gerti.portal_user_role` guarda `eduardo.salvi@auroramoveis.com.br`; quem
>    entra como `eduardo.salvi` (login curto, aceito desde a correção de
>    2026-07-30) cai no papel **default** `helpdesk` e passa a ver só os próprios
>    chamados — a mesma pessoa enxerga coisas diferentes conforme o formato do
>    login que digitou. Confirmado ao vivo: `/api/portal/me` devolve
>    `role: "helpdesk"` para `eduardo.salvi` e `role: "admin"` para o e-mail
>    completo. O console já canonicaliza o login do agente; o portal não faz o
>    equivalente para o papel.

### Deploy da Onda 1 — cadastro de cliente, usuário único e filas (profile `gerti`)

Onda 1 da campanha Recursos Administrativos (R1 · R2 exceto ingestão de e-mail ·
R5). Aditivo e profile-gated. **Quatro migrations novas** (0027–0030) e **três
operações GI novas** no webservice `GertiAdmin`, que já existe em prod desde
#1G-a — logo, `Admin::WebService::Update --webservice-id`, nunca `Add`.

**Pré-requisitos:** nenhuma variável nova. `ZNUNY_WS_TOKEN`
(`GertiAdmin::AccessToken`) e `ZNUNY_ADMIN_WS_URL` já presentes são reusados
pelas ops novas.

```bash
ssh gc 'cd ~/ground-control && git fetch origin && git checkout campanha/onda-1-cadastro && git pull'
DC="docker compose --env-file .env --env-file .env.prod --profile gerti"

# 1) Znuny: rebuild (bakeia CustomerCompanyUpdate + CustomerUserUpdate +
#    CustomerUserList, e o LEFT JOIN novo do TimeAccountingSince). `perl -c` é
#    gate de build. NOTA: recria o core Znuny (downtime curto).
ssh gc "cd ~/ground-control && $DC build znuny-web && $DC up -d znuny-web znuny-daemon"

# 2) CRÍTICO — atualizar o webservice GertiAdmin (JÁ EXISTE: id 2).
#    `Admin::WebService::Add` FALHA se o WS existir; `Update` exige
#    --webservice-id (não --name) nesta versão do Znuny — lição do #1B.
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && \
   WSID=\$(bin/otrs.Console.pl Admin::WebService::List | sed -n \"s/.*GertiAdmin (\\([0-9]\\+\\)).*/\\1/p\"); \
   bin/otrs.Console.pl Admin::WebService::Update --webservice-id \"\$WSID\" \
     --source-path /opt/otrs/webservices/GertiAdmin.yml"'
#   GUARD: os três webservices seguem presentes (nenhum pode sumir):
ssh gc 'cd ~/ground-control && docker compose exec -T znuny-web su otrs -s /bin/bash -c \
  "cd /opt/otrs && bin/otrs.Console.pl Admin::WebService::List"'
#   → GertiCustomerAuth (1) + GertiAdmin (2) + GertiTicket (3)
#   NOTA: `TimeAccountingSince` vive no GertiTicket e NÃO mudou de contrato —
#   só o corpo do .pm. Não precisa atualizar o GertiTicket.yml.

# 3) migrations 0027→0030, ANTES do app (invariante 8):
ssh gc "cd ~/ground-control && $DC build sidecar admin"
ssh gc "cd ~/ground-control && $DC up -d sidecar-migrate"
ssh gc "cd ~/ground-control && $DC ps -a sidecar-migrate"     # Exit (0)
ssh gc "cd ~/ground-control && $DC up -d sidecar sidecar-worker admin && $DC ps"

# 4) serviços anteriores intactos:
curl -fsS https://znuny-dev.was.dev.br/znuny/index.pl | grep -qi login && echo ZNUNY_OK
curl -fsS https://api-dev.was.dev.br/v1/health && echo SIDECAR_OK
curl -fsSL https://aurora.was.dev.br/   | grep -qi Aurora   && echo AURORA_OK
curl -fsSL https://technova.was.dev.br/ | grep -qi TechNova && echo TECHNOVA_OK
curl -fsS https://gerti.was.dev.br/login | grep -qi login && echo ADMIN_OK
curl -fsS https://groundcontrol.was.dev.br >/dev/null && echo LANDING_OK
```

**Rollback (Onda 1 somente).** As migrations 0027–0030 são **aditivas** — colunas
nullable e tabelas novas. Voltar o código sem voltar o schema é seguro: nada do
código anterior lê as colunas novas.

```bash
ssh gc 'cd ~/ground-control && git checkout campanha/onda-0-defeitos'
$DC build znuny-web sidecar admin && $DC up -d znuny-web znuny-daemon sidecar admin
# e reimportar o GertiAdmin.yml da branch anterior (mesmo comando do passo 2)
```

Se for preciso reverter o schema também: `$DC run --rm sidecar-migrate uv run
alembic downgrade 0026_worker_heartbeat` (derruba `tenant_queue` e
`consumption_orphan` e as colunas de endereço/ramal — **destrói** o que tiver
sido configurado nelas). **NUNCA** `make reset`.

> **Status (2026-08-16): DEPLOYADO em staging e verificado ao vivo.** Branch
> `campanha/onda-1-cadastro` (`bce770b`) no host — **não** mergeada na `main` no
> momento do deploy. Sha anterior do staging: `c7f9025`
> (`campanha/onda-0-defeitos`), alembic `0026`.
>
> Imagem Znuny rebuildada (5 ops `perl -c` verdes: `CustomerCompanyUpdate`,
> `CustomerUserUpdate`, `CustomerUserList`, `AdminGroupList`,
> `TimeAccountingSince`); `znuny-web`/`znuny-daemon` Healthy; `GertiAdmin`
> atualizado por `--webservice-id 2` com os três webservices intactos;
> migrations **0027→0030** aplicadas (`Exit 0`); `sidecar`, `sidecar-worker` e
> `admin` Healthy. Serviços anteriores intactos (znuny-dev, api-dev, aurora,
> technova, gerti, landing — todos 200, white-label preservado).
>
> **Provas ao vivo (tenant Aurora, `5effe6fd…`):**
>
> - **A1.1** — `PUT /v1/admin/tenants/{id}` com endereço e contato → **200**; o
>   `GET` devolve `Belo Horizonte` / CEP `30130005` / contato `Eduardo Salvi`.
> - **A1.4** — o espelho chegou ao Znuny: `customer_company` da AURORA passou a
>   ter `street='Av. Afonso Pena, 1500 — Centro'`, `zip='30130005'`,
>   `city='Belo Horizonte/MG'` e o contato no campo `comments`.
> - **A1.2** — `PUT` tentando trocar `subdomain` → **422**
>   (`extra_forbidden`), e o valor no banco continua `aurora`. Idem
>   `znuny_customer_id`. Tenant inexistente → **404**.
> - **A2.5** — `GET /v1/admin/tenants/{id}/users` devolve **7** pessoas:
>   as 6 do `customer_user` do Znuny **mais** 1 que só tem papel no nosso lado.
>   Quatro delas (`carla.dorneles`, `eduardo.salvi`, `fernando.rech`,
>   `juliana.peruzzo`) foram criadas direto no Znuny pelo seed e **eram
>   invisíveis no console até esta onda** — agora aparecem marcadas como "sem
>   acesso ao portal".
> - **A2.1/A2.4** — usuário descartável criado com telefone, celular e ramal
>   (`+553133339999` / `+5531999998888` / `777`) → **201**; a listagem devolve os
>   três; `PUT {"active": false}` → **200** e a pessoa passa a `ValidID=2`,
>   continuando na lista como inativa (invariante 3: sem exclusão).
> - **A5.1/A5.5** — filas 6/7/8 associadas com a 6 (`Suporte::N1`) como padrão;
>   o `GET` devolve as três com o grupo que as atende. Mover o padrão de 6 para
>   7 e voltar → **200** nas duas (o índice parcial único não colide). PUT
>   repetido não duplica linha.
> - **A5.3** — fila `99999`, que não existe no Znuny → **422**
>   `"fila inexistente no Znuny: 99999"` e **zero** linhas gravadas. Duas filas
>   marcadas como padrão → **422**.
> - **A5.2** — chamado aberto pelo portal da Aurora **sem informar fila** nasceu
>   em **`Suporte::N1`**, não em `Raw` (ticket 74). Com fila explícita
>   `Suporte::N2` (associada) → nasceu na N2 (ticket 76).
> - **Worker** — tick com `last_error` vazio depois da mudança no
>   `TimeAccountingSince` (`worker_heartbeat.ticks=11528`), e zero linhas em
>   `gerti.consumption_orphan`.
>
> **Defeito que só a execução ao vivo revelou (corrigido e redeployado,
> `bce770b`):** abrir chamado com `queue=Financeiro` — fila que a Aurora **não**
> acessa — devolvia **201** em vez de 422. O serviço validava; a **rota** não
> recebia o campo do formulário, então `OpenTicketInput.queue` era sempre `None`
> e a guarda nunca rodava. Não era brecha de isolamento (o chamado caía na fila
> padrão do próprio cliente), mas o 422 prometido era código morto. Depois da
> correção: `queue=Financeiro` → **422** `queue_not_allowed`. Dois testes de
> **rota** entraram — o de serviço passava e não pegava nada, mesma forma do que
> a Onda 0 encontrou na criação de fila.
>
> **Limpeza:** os 3 chamados descartáveis (74/75/76) foram apagados
> (`Maint::Ticket::Delete`) junto das linhas de `gerti.ticket_contract_link`. O
> usuário de teste `zz.teste.onda1@auroramoveis.com.br` fica **invalidado**
> (`ValidID=2`) — o Znuny invalida, não exclui, e esse é o estado terminal
> esperado (mesmo tratamento da fila `ZZ-TESTE-ONDA0` da Onda 0).
>
> **Mudanças de comportamento deixadas de pé em staging, de propósito:** o
> endereço e o contato da Aurora (eram nulos), e a associação de filas
> 6/7/8 com `Suporte::N1` como padrão. **Chamado novo da Aurora agora nasce em
> `Suporte::N1`, não mais em `Raw`** — é o requisito R5 funcionando, e é o que
> se demonstra ao Kleber. Para voltar ao comportamento antigo basta
> `PUT /v1/admin/tenants/{id}/queues {"queues": []}`.
