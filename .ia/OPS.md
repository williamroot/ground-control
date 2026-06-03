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
   bin/otrs.Console.pl Admin::WebService::Add --source-path /opt/otrs/webservices/GertiAdmin.yml"'
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

## Backup (a definir em prod)

- Postgres: `pg_dump` agendado → storage externo (não implementado nesta fase)
- `znuny-var` (anexos): snapshot de volume
- Ação futura: pgBackRest + retenção, documentar aqui quando implementado.

## Observabilidade (a definir)

Logs via `docker compose logs` por enquanto. Stack de observabilidade (OTEL/Grafana) é fase posterior — documentar aqui quando entrar.
