# Ground Control — Arquitetura

## Topologia

```
                       Internet
                          │
                 ┌────────▼────────┐   rede: edge
                 │   cloudflared   │   (znuny-dev.was.dev.br)
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │   znuny-web     │  Apache2 + mod_perl2  (:8080→80)
                 │  (Znuny 7.2.3)  │
                 └────────┬────────┘
        rede: app         │           ┌──────────────┐
                 ┌────────┼───────────┤ znuny-daemon │ bin/otrs.Daemon.pl
                 │        │           └──────────────┘ (foreground/supervisado)
   ┌─────────────▼──┐ ┌───▼────┐ ┌────▼─────────┐
   │  postgres:18   │ │redis:7 │ │ opensearch:2 │   rede: data
   │ schema Znuny   │ │ cache  │ │ single-node  │   (internal: true)
   └────────────────┘ └────────┘ └──────────────┘
```

## Containers

| Serviço | Imagem | Papel | Health |
|---|---|---|---|
| `postgres` | `postgres:18` | DB do Znuny (schema em `public`; `gerti` virá com o sidecar) | `pg_isready` |
| `redis` | `redis:7-alpine` | Cache backend do Znuny (`Cache::Redis` custom) | `redis-cli ping` |
| `opensearch` | `opensearchproject/opensearch:2` | Cluster de busca single-node (security off, dev) | cluster health |
| `znuny-web` | build do tarball 7.2.3 | Apache2 + mod_perl2, serve `/znuny/index.pl` | HTTP login 200 |
| `znuny-daemon` | mesma imagem | `bin/otrs.Daemon.pl` supervisado em foreground | marcador + status |
| `cloudflared` | `cloudflare/cloudflared:latest` | Tunnel `znuny-dev.was.dev.br` (token pendente) | n/a (restarting até token) |

## Redes (segregação)

- **edge** — cloudflared ↔ znuny-web
- **app** — znuny-web/daemon ↔ postgres/redis/opensearch
- **data** — `internal: true`: postgres/redis/opensearch **não roteáveis** de fora do projeto

## Volumes nomeados

- `postgres-data` → `/var/lib/postgresql` (PG18 usa subdir de major-version; **não** `/data`)
- `znuny-var` → `/opt/otrs/var` (article storage)
- `opensearch-data`

## Imagem Znuny

- Base **`debian:bookworm-slim`** (NÃO `perl:5.40` — evita dois perls; mod_perl usa o perl do sistema, CLI usaria 5.40 → `@INC` mismatch quebrava `CheckModules.pl`). Decisão em `DECISIONS.md`.
- Deps Perl: pacotes Debian `lib*-perl`; resto via `cpanm` no mesmo perl do sistema.
- `bin/otrs.CheckModules.pl` roda como **gate de build** — módulo *required* faltando falha o `docker build`.
- Install real em `/opt/otrs`; `/opt/znuny → /opt/otrs` simlink (Znuny hardcoda `/opt/znuny` em apache include/cron). Path web: `/znuny/index.pl`.

## Provisionamento (`znuny/entrypoint.sh`) — automatizado e idempotente

1. Renderiza `Kernel/Config.pm` de `Config.pm.tmpl` com env (DSN, Redis, OpenSearch endpoint, SystemID, FQDN).
2. Espera o Postgres pronto.
3. **Init de DB idempotente**: carrega schema + initial + post-schema **só se** a tabela `valid` não existe; senão loga `schema already present — skipping`.
4. Rebuild SysConfig, garante/cria admin, seta senha deterministicamente, verifica em `users`.
5. Prova alcance Znuny→OpenSearch.
6. Role `web` → exec Apache2 (foreground). Role `daemon` → espera marcador do web, roda `bin/otrs.Daemon.pl` supervisado.

## Cache Redis (custom)

Core Znuny 7.2 só tem `Cache::FileStorable`. Adicionamos `Kernel::System::Cache::Redis` em `Custom/` (primeiro no `@INC`, upgrade-safe) implementando o contrato exato (`Set/Get/Delete/CleanUp`), serialização `Storable`, `SETEX` nativo, índice SET por `Type`. Verificado: 150+ chaves `znuny:*` no Redis, FS bypassed.

## Sidecar Python (`apps/sidecar/`) + infra dev (`infra/`)

Serviço **FastAPI + SQLAlchemy 2 async + Alembic** que detém o domínio
de contratos/consumo/faturamento no schema **`gerti`** (Spec #0). Estado:
**fundação (Plano 1A) + #1C Task 1 prontos e verificados** — gate
`ruff + mypy + pytest` (16 testes, testcontainers) verde nesta localização.

- **Limite de integração com o Znuny:** núcleo Znuny imutável. Escrita
  Znuny via **Generic Interface** (REST); leitura do schema `znuny`
  read-only. Znuny → sidecar via **webhooks HMAC** (GertiHooks.opm,
  Spec #1B — não iniciado) alimentando `gerti.consumption_event`.
- **Multi-tenant:** GUC `app.current_tenant` (SET LOCAL por transação)
  + **FORCE RLS** por tabela `gerti.*`, fail-closed; runtime conecta
  como `gerti_sidecar` (sem BYPASSRLS).
- **Schema compartilhado:** Spec #0 prevê **um cluster Postgres** com
  schemas `znuny` + `gerti`. Hoje o Znuny de prod usa o `postgres:18`
  próprio (schema `public`); o sidecar testa via testcontainers +
  `infra/compose/postgres/init/001_schemas_and_roles.sql`. Convergência
  para cluster único = **item de integração aberto**.
- **`infra/compose/`** = infra **dev** opcional do sidecar
  (postgres/redis/minio) + init SQL + smoke-test. **Separada** da stack
  Znuny de produção (`docker-compose.yml` raiz); não compartilham containers.

### Deploy em prod (profile `gerti`, single-cluster)

3 serviços **gated por `profiles:["gerti"]`** no `docker-compose.yml`
raiz (NÃO sobem num `make up` da stack Znuny — aditivos, Postgres não
reinicia):

| Serviço | Papel | Role DB |
|---|---|---|
| `gerti-db-init` | one-shot idempotente: cria schema `gerti`+roles+RLS no `postgres:18` VIVO (psql superusuário, zero DROP, não toca `public`/`znuny`) | superusuário |
| `sidecar-migrate` | one-shot: `alembic upgrade head` (dono do DDL); `service_completed_successfully` libera o app | `gerti_admin_user` (BYPASSRLS) |
| `sidecar` | FastAPI long-running em `:8001`, redes `data`+`edge` | `gerti_sidecar` (RLS-subject, sem BYPASSRLS) |

Exposto em `api-dev.was.dev.br` (2º hostname no tunnel `znuny-dev`,
token-mode multi-host; ingress via read-modify-write). Runbook em
[`OPS.md`](OPS.md) "Deploy do sidecar"; decisão em
[`DECISIONS.md`](DECISIONS.md) D13.

Detalhe completo: [`INTEGRATION.md`](INTEGRATION.md).

## Portal Cliente (`apps/portal/`) — Spec #1F-a

Nuxt 3 SSR (`apps/portal/`) exposto na porta 3000, nas redes `app` e
`edge`. Suporte a múltiplos tenants white-label sem Znuny separado por
tenant.

### Tema claro/escuro/sistema

O portal suporta os 3 modos via `@nuxtjs/color-mode` (trazido pelo `@nuxt/ui`).
Default `system` (segue o SO), `fallback: light` para SSR/sem-JS; a escolha do
usuário persiste (cookie/localStorage). O seletor é `components/ThemeToggle.vue`
(segmentado sol/monitor/lua), presente no header das views autenticadas e no
canto superior do `/login`. As cores das páginas usam **tokens semânticos do
Nuxt UI** (`bg-default`/`bg-muted`/`bg-elevated`, `text-default`/`text-muted`/
`text-dimmed`/`text-highlighted`, `border-default`) que viram no `.dark` — não
há mais cores cruas (`bg-white`, `text-neutral-*`). Alertas de saldo e glosa
usam tokens semânticos fixos `warning`/`error` (nunca a cor de marca — H8),
que também adaptam ao tema. A cor de marca (`--brand-primary/-accent`) é
protagonista nos dois modos.

### Branding middleware (Nitro)

Toda requisição SSR passa pelo `tenantBranding` server middleware antes
de renderizar qualquer página:

- Extrai o subdomínio da `Host` header e chama `GET /v1/branding` no
  sidecar (60 s de cache no servidor; nunca expira na borda para
  subdomínios desconhecidos).
- Injeta as variáveis de tema (cores, nome do tenant, `logo_url`) no
  contexto da requisição para uso no layout.
- **Default neutro:** quando o subdomínio não casa com nenhum tenant, o
  middleware retorna um tema neutro — nunca "Gerti" como marca exposta.

### Autenticação server-proxied

O portal **não** expõe o sidecar diretamente ao browser:

- `POST /login` → proxy server-side → `POST /v1/auth/login` no sidecar
  → sidecar valida credencial via `znuny_gi.authenticate_customer` →
  minta JWT HS256 como cookie **`gsid`** (first-party, `SameSite=Lax`,
  `HttpOnly`, `Secure`).
- Logout: `/logout` → proxy → `POST /v1/auth/logout` → limpa o `gsid`.
- O sidecar é a **ÚNICA porta para o Znuny**; o browser nunca fala
  diretamente com `znuny-web` nem com a DB.

### Dois tenants white-label de teste (§2.1)

Implementado e gateado; deploy per runbook (`OPS.md`):

| Tenant | Subdomínio | Palette |
|---|---|---|
| Aurora Móveis | `aurora.suporte.gerti.com.br` | laranja/âmbar |
| TechNova | `technova.suporte.gerti.com.br` | violeta/escuro |

Ambos apontam para o **mesmo Znuny único** (`gerti.znuny_instance`,
id `b437f4d5-8266-4270-9253-ef536c8ff59c`). Nenhum Znuny separado por
tenant — §2.1 preservado.

**Prova de isolamento cross-tenant:** um cookie `gsid` mintado para o
tenant Aurora é rejeitado com **401** ao bater em qualquer endpoint do
tenant TechNova (e vice-versa) — fail-closed: o `gsid` é tenant-scoped e
não valida fora do seu tenant. Verificado no e2e smoke (`test_portal_e2e_smoke.py`)
e ao vivo via browser (2026-06-20).

Tenants seeded de forma idempotente por `scripts/seed_demo_branding.py`
(branding + TechNova tenant) + `scripts/seed-technova.pl` via
`scripts/seed-demo.sh` (customer Znuny de TechNova;
`admin.tech@technova.example` / `TechNova@Demo2026`).

### Topologia

```
Browser → cloudflared → portal:3000 → sidecar:8001 → (Znuny GI | gerti schema RLS)
```

O portal vive nas redes `app` (alcança `sidecar:8001`) e `edge`
(cloudflared roteia os subdomínios `aurora.suporte.gerti.com.br` e
`technova.suporte.gerti.com.br`). O sidecar **não** está na rede `edge`
— o portal é o único ponto de entrada público para o domínio de
contratos.

### Deploy (profile `gerti`)

Serviço `portal` gated por `profiles:["gerti"]` no `docker-compose.yml`
raiz — idêntico ao padrão D13/D15. Um `make up` da stack Znuny pura não
o toca. Runbook e ingress Cloudflare em [`OPS.md`](OPS.md);
decisão em [`DECISIONS.md`](DECISIONS.md) D15.

### Portal #1F-b — visão de contratos rica (read-only)

Implementado e gateado; deploy per runbook (`OPS.md`).

#### Endpoints novos (read-only sobre #1C)

| Endpoint | Descrição |
|---|---|
| `GET /v1/contracts` | Lista estendida: inclui `id` e `consumed_percent` por contrato |
| `GET /v1/contracts/{id}` | Detalhe do contrato: saldo, totais, ciclo ativo, reajuste/renovação |
| `GET /v1/contracts/{id}/consumption` | Eventos de consumo paginados com flag `counts_toward_balance` |
| `GET /v1/contracts/{id}/series` | Série densa de consumo (cap 400 buckets diários→semanal, H5) |
| `GET /v1/dashboard` | Cards de saldo + alertas de saldo baixo (`warning`/`critical`) |

Todos os endpoints utilizam `get_current_session` + `get_tenant_session` (autenticação + RLS); nenhum endpoint de escrita foi adicionado. Grep-guard `test_portal_read_only_guard.py` garante ausência de `add`/`flush`/`commit`/`INSERT`/`UPDATE`/`DELETE` em qualquer router de contracts/dashboard (H3).

#### `contract_read_service.py` — regra S3 centralizada (ADR D17)

`domain/contract_read_service.py` é **read-only puro** (só `select`/`session.get`/`ConsumptionService.balance`). Centraliza:

- `not_written_off_predicate()` — idêntico ao braço S3 do `balance()` (braço `glosa_id IS NULL` explícito evita o footgun `NULL NOT IN`);
- `consumed_percent_from` / `consumed_percent` — `clamp01((initial − remaining)/initial)×100`, `None` para `kind=="n/a"` e base 0;
- `series` — série densa zero-filled, cap 400 buckets;
- `low_balance` — limiar 20% `warning` / ≤0 `critical`; `closed_value`/`saas_product` nunca alertam.

Nenhum router redefine a regra S3 (D17).

#### Componentes SVG puros (sem lib externa)

Três componentes Vue SSR-safe, brand-var, zero dependência de lib:

| Componente | Uso |
|---|---|
| `ProgressBar.vue` | Barra de consumo por contrato (usa `--brand-primary`) |
| `AreaChart.vue` | Série temporal de consumo no detalhe do contrato |
| `Sparkline.vue` | Mini-sparkline nos cards do dashboard |

#### Páginas do portal

| Rota | Página |
|---|---|
| `/` | Dashboard rico: cards de saldo + alertas + sparklines |
| `/contratos/[id]` | Detalhe: hero saldo + AreaChart + ciclos + ledger c/ indicadores de glosa + reajuste/renovação/partes |

#### Assinatura WAS discreta

Footer com assinatura "Powered by WAS" presente em ambos os tenants (Aurora e TechNova). Implementado em `WASSignature.vue`; verificado nos testes de portal e no gate visual (Task 15 Step 5 — controller).

#### Topologia (inalterada)

```
Browser → cloudflared → portal:3000 → sidecar:8001 → gerti schema RLS
```

O portal é read-only sobre o domínio #1C. Nenhuma rota de escrita foi exposta.

### Portal #1E — abertura/lista/detalhe de chamados

Implementado e gateado; deploy per runbook (`OPS.md`). Billing/consumo (#1B) é o próximo spec.

#### Fluxo

```
Browser → portal:3000 → sidecar:8001 → GertiTicket GI → Znuny
                                      → gerti schema (ticket_contract_link)
```

- **Seleção de contrato:** automática se o customer tiver exatamente 1 contrato ativo;
  seletor condicional exibido se houver ≥ 2 (422 se nenhum escolhido); 404 para contrato
  desconhecido (RLS). O `contract_id` é gravado no DynamicField **`GertiContractId`**
  do ticket Znuny e em `gerti.ticket_contract_link` (billing-ready para o #1B).
- **Webservice Znuny** (`GertiTicket`): 5 operações (`TicketCreate`, `TicketSearch`,
  `TicketGet`, `TicketReply`, `FormMeta`), `AccessToken` fail-closed (reusa
  `GertiAdmin::AccessToken`). Definição em `znuny/webservices/GertiTicket.yml`;
  módulos Perl em `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/`.
  `perl -c` é gate de build da imagem.
- **DynamicField `GertiContractId`:** criado idempotentemente por
  `znuny/scripts/ensure-gerti-dynamicfield.pl` (passo explícito no runbook de deploy).
- **Endpoints sidecar:** `GET /v1/ticketing/contracts` (selecionáveis pelo customer,
  non-admin), `GET /v1/ticketing/form-meta`, `POST /v1/tickets` (multipart, cria ticket),
  `GET /v1/tickets` (lista role-scoped), `GET /v1/tickets/{id}` (ownership-guarded),
  `POST /v1/tickets/{id}/reply`.
- **Páginas portal:** `/tickets` (lista, role-scoped), `/tickets/novo` (form
  single-page + seletor condicional de contrato), `/tickets/[id]` (detalhe + reply).
- **Env var nova:** `ZNUNY_TICKET_WS_URL` (base do GertiTicket; fallback: derivado
  de `ZNUNY_ADMIN_WS_URL` trocando `/GertiAdmin` → `/GertiTicket`).
  `ZNUNY_WS_TOKEN` reusado como AccessToken.

---

## Console de Administração (`apps/admin/`) — Spec #1G-a

Nuxt 3 SSR **separado** do portal (própria imagem/serviço compose `admin`,
profile `gerti`, redes `app`+`edge`), identidade **FIXA Gerti/WAS** — NÃO é
white-label. É a casa da equipe Gerti para **onboarding de cliente** e **criar
contrato**. ADR D19.

```
Browser → cloudflared → admin:3000 → sidecar:8001 (/v1/admin/*, cross-tenant)
```

- **Auth = agente Znuny** (não customer): `POST /v1/admin/auth/login` valida via
  GI (`Session::SessionCreate` com `UserLogin`+`Password` → `Kernel::System::Auth`,
  D19) e emite o cookie **`gsid_adm`** (JWT HS256 `{agent_login, role:"gerti_staff",
  typ:"admin"}`), **distinto** do `gsid` do cliente. `get_admin_session` é
  fail-closed por `typ:admin`+role; um `gsid` de cliente nunca vale em `/v1/admin/*`
  e vice-versa (isolamento bidirecional provado no e2e).
- **Cross-tenant, dois caminhos de DB (D16):** criar tenant/branding/papéis usa
  `AdminSessionLocal` (BYPASSRLS) com `tenant_id` explícito; criar contrato abre
  `tenant_session_scope(id)` (RLS-subject) + `ContractService` — preserva as
  invariantes #1C. BYPASSRLS só em `/v1/admin/*`.
- **Escrita no Znuny via GI** (Spec #0): o webservice custom **`GertiAdmin`**
  (`znuny/Custom/Kernel/GenericInterface/Operation/...`) embrulha a API Perl nativa
  (`CustomerCompanyAdd`/`CustomerUserAdd`/`SetPassword`), idempotente e com
  `AccessToken` fail-closed. O sidecar é a única porta; o browser nunca fala com o
  Znuny.
- **Páginas:** `/login` (agente), `/` (lista de clientes), `/clientes/novo`
  (assistente: dados+branding+usuários/papéis), `/clientes/[id]` (detalhe),
  `/clientes/[id]/contratos/novo` (form por tipo de contrato). Guarda de rota
  `admin-auth` (gate real é o 401 do sidecar). Subdomínio white-label do cliente
  continua **manual** (D-1G-4) — a UI mostra ao operador o subdomínio a registrar.

### Deploy (profile `gerti`)

Serviço `admin` aditivo/profile-gated (padrão D13/D15). Runbook completo em
[`OPS.md`](OPS.md) "Deploy do Console de Administração"; decisão em
[`DECISIONS.md`](DECISIONS.md) D19. Sem migration nova (#1G-a).

### Worker de consumo/cobrança (#1B)

Serviço compose **`sidecar-worker`** (mesma imagem do `sidecar`, command
`uv run python -m gerti_sidecar.jobs.worker`, profile `gerti`) implementa o
ciclo automático de billing:

**Fluxo de pull (sidecar-worker → Znuny → DB):**

```
sidecar-worker
  └─ loop a cada RECONCILE_INTERVAL_SECONDS (default 120 s)
       └─ GI GertiTicket::TimeAccountingSince (cursor consumption_sync_cursor)
            └─ reconciliation_service: entrada por ticket vinculado
                 └─ consumption_event por entrada (idempotente via webhook_event_id=uuid5)
                      └─ balance() debita automaticamente
  └─ 1×/dia: cycle_closer → CycleService.close (fecha ciclos vencidos por tenant)
```

- **Cursor:** tabela operacional `gerti.consumption_sync_cursor` (migration `0013`;
  watermark por instância Znuny; não é tabela de tenant — lida com BYPASSRLS).
- **Segurança multi-tenant:** leitura cross-tenant via `BYPASSRLS` (busca entradas
  de todos os tenants de uma vez); escrita de `consumption_event` por tenant via
  `tenant_session_scope(id)` (RLS-subject) — preserva as invariantes #1C.
- **Conversão:** `hour_bank` → `billable_minutes`; `credit_brl`/`shared` →
  `billable_amount_brl = round(minutes/60 × unit_price, 2)`. Outros tipos
  (`n/a`, `saas`, …) são registrados mas não afetam o saldo.
- **Idempotência:** `webhook_event_id = uuid5(namespace, f"timeaccounting:{id}")`
  — reprocessar não duplica.
- **Op Znuny nova:** `TimeAccountingSince` no webservice `GertiTicket` (read-only,
  lê tabela nativa `time_accounting` desde um cursor, `AccessToken` fail-closed;
  `perl -c` é gate de build da imagem).
- **Faturamento/glosa UI:** Spec #2 (invoice/NF) e #1G-b (glosa UI) permanecem
  fora do escopo desta branch.

Runbook de deploy em [`OPS.md`](OPS.md) "Deploy do worker de consumo/cobrança".

### Time tracker do agente (#1J)

Estende o Console de Administração (`apps/admin/`) e o sidecar com controle
de tempo por agente, integrado ao fluxo de billing do #1B.

**Superfície de UI (`apps/admin/`):**
- `/atendimento` — busca de tickets cross-tenant (chip de timers ativos) com
  controle de timer inline por linha.
- `/atendimento/[id]` — detalhe do ticket com card de timer proeminente + badge
  do contrato vinculado (`ContractBadge`). Stop dialog permite `adjust_minutes`
  (cap 1440 min) + nota **opcional** antes de lançar.
- Composable `useTimers`; componentes `TimerControls`, `TimerStopDialog`,
  `ContractBadge`. Link de navegação no menu admin.

**3 ops GI novas no webservice `GertiTicket` — token separado:**
- `TimeAccountingAdd` — cria artigo interno (nota de stop) + `TicketAccountTime`
  no Znuny; resolve `UserID` do agente pelo login.
- `AgentTicketSearch` — busca cross-tenant de tickets por agente.
- `AgentTicketGet` — detalhe de ticket para agente (inclui contrato vinculado).

Estas ops usam **`GertiAgent::AccessToken`** (env `ZNUNY_AGENT_WS_TOKEN`),
**token separado** do `GertiAdmin::AccessToken` (`ZNUNY_WS_TOKEN`). Segurança
por separação: as ops de agente são root/cross-tenant; comprometer o token de
admin não expõe as ops de agente e vice-versa. Renderizado em `Config.pm.tmpl`
pelo entrypoint; `perl -c` é gate de build da imagem.

**Tabela `gerti.agent_timer` (migration `0014_agent_timer`):**
- Tabela operacional não-tenant (lida com BYPASSRLS pelo sidecar).
- `PARTIAL UNIQUE INDEX` garante no máximo um timer ativo por par
  `(agent_login, ticket_id)` — invariante de negócio aplicada na DB.

**`domain/timer_service.py`:**
- `start` (idempotente), `pause` (com guarda), `resume`, `stop`.
- Stop: computa minutos, aplica `adjust_minutes` (cap 1440), chama
  `time_accounting_add` via GI, marca timer como `stopped`.
- **Ownership check** por agente em pause/resume/stop — `TimerNotFound` → 404.
- Estado do timer é server-side (a UI só reflete; o agente não pode fraudar tempo).

**Endpoints sidecar — `/v1/admin/timer/*` (todos sob `get_admin_session`):**
- `POST /v1/admin/timer/start`, `pause`, `resume`, `stop`
- `GET /v1/admin/timer/active`
- `GET /v1/admin/tickets` (busca), `GET /v1/admin/tickets/{id}` (detalhe com
  contrato vinculado via join).

**Fluxo stop → billing:**
```
stop → time_accounting_add (Znuny, artigo interno) → sidecar-worker (#1B)
     → reconciliation_service → consumption_event → balance() debita saldo
```
Ticket sem contrato vinculado: `time_accounting` é gravado no Znuny mas o
`consumption_event` não é gerado até o vínculo existir (UI avisa o agente).
Billing é downstream/assíncrono via worker #1B.

Implementado e gateado; deploy per runbook [`OPS.md`](OPS.md) "Deploy do time
tracker do agente".

### CMDB / Ativos (#1K)

Estende o Znuny com os 3 **add-ons ITSM oficiais** (versão 7.2.1) e expõe o
inventário de Config Items ao cliente de forma read-only, com escopo por tenant.

**Znuny — add-ons ITSM:**
Os `.opm` `GeneralCatalog`, `ITSMCore` e `ITSMConfigurationManagement` são
bakeados na imagem (`znuny/addons/`) e instalados idempotentemente na
inicialização pelo script `znuny/scripts/ensure-itsm.sh` (chamado pelo
`entrypoint.sh`). As **5 classes nativas de CI** (Computador, Hardware, Rede,
Software, Localização) incluem o campo `CustomerID` (Input type `CustomerCompany`)
que é usado como chave de escopo por tenant — sem atributo customizado.

**GI ops novas no webservice `GertiTicket`:**
- `ConfigItemSearch` — busca Config Items por `CustomerID` (scoped por tenant).
- `ConfigItemGet` — detalhe de CI com guarda de posse anti-IDOR (CustomerID
  do item deve casar com o tenant do token).
- `TicketCreate` estendido — aceita `ConfigItemId` e cria o link
  `RelevantTo` via `Kernel::System::LinkObject` após a criação do ticket.

**Sidecar (`apps/sidecar/`):**
- `znuny_gi.config_item_search` / `config_item_get` (cliente GI).
- `POST /v1/tickets` aceita `config_item_id` (opcional).
- `GET /v1/assets` — lista CIs do tenant (scoped por `znuny_customer_id`).
- `GET /v1/assets/{id}` — detalhe com guarda anti-IDOR → 404 se CustomerID não bater.
- Sessão de customer (qualquer papel autenticado).

**Portal (`apps/portal/`):**
- `/ativos` — lista read-only de Config Items do tenant.
- `/ativos/[id]` — detalhe; botão "Abrir chamado sobre este ativo" →
  `/tickets/novo?ativo=<id>` (passa `config_item_id` no form).
- Nav "Ativos" adicionada ao menu autenticado.
- Proxies validam id numérico (guard de path-injection).

**Fluxo:**
```
MSP cadastra CI no Znuny (CustomerID=AURORA)
  → GI ConfigItemSearch/Get
  → sidecar /v1/assets (scoped)
  → portal /ativos (read-only)
  → "Abrir chamado" → /tickets/novo?ativo=<id>
  → POST /v1/tickets (config_item_id)
  → GI TicketCreate + LinkObject RelevantTo
  → ticket Znuny linkado ao CI
```

O MSP gerencia o inventário no Znuny; o portal expõe apenas visibilidade
read-only ao cliente. Deploy per runbook [`OPS.md`](OPS.md)
"Deploy do CMDB/ativos"; spike de API em
`docs/superpowers/spikes/2026-06-09-r1k-znuny-itsm-cmdb.md`.

## Landing (`landing/`)

Estático (HTML/CSS/JS), estética mission-control. Deploy próprio independente: nginx + cloudflared → `groundcontrol.was.dev.br`. Não compartilha containers com a stack Znuny. Detalhes em `landing/README.md`.

## Fluxos

- **Request externo** → Cloudflare edge → cloudflared (tunnel) → znuny-web:80 → Apache/mod_perl → Postgres/Redis.
- **Jobs/escalações** → znuny-daemon (independente do web; só sobe após marcador de provisionamento do web).
- **Cache** → toda leitura/escrita de cache do Znuny → Redis (não FS).
