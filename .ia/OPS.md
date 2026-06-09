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

## Backup (a definir em prod)

- Postgres: `pg_dump` agendado → storage externo (não implementado nesta fase)
- `znuny-var` (anexos): snapshot de volume
- Ação futura: pgBackRest + retenção, documentar aqui quando implementado.

## Observabilidade (a definir)

Logs via `docker compose logs` por enquanto. Stack de observabilidade (OTEL/Grafana) é fase posterior — documentar aqui quando entrar.
