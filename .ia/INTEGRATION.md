# Ground Control — Integração Sidecar ↔ Stack Znuny

Como o **sidecar Python** (domínio de contratos/consumo/faturamento) se
integra à stack **Znuny** já no ar neste monorepo. Leia junto de
`ARCHITECTURE.md` (stack Znuny) e da Spec #0
(`../docs/superpowers/specs/2026-05-12-gerti-servicedesk-znuny-design.md`).

## (a) Layout do monorepo (estado atual)

```
ground-control/
├── docker-compose.yml / znuny/ / postgres/ / scripts/   stack Znuny (no ar)
├── apps/
│   ├── sidecar/    serviço Python · FastAPI · SQLAlchemy 2 async · Alembic
│   │               · pytest + testcontainers   (fundação + #1C T1)
│   ├── portal/     Nuxt 3 SSR · branding middleware · auth proxy (Spec #1F-a)
│   │               · tickets (#1E): /tickets, /tickets/novo, /tickets/[id]
│   └── admin/      Nuxt 3 SSR · Console de Administração Gerti (Spec #1G-a)
│                   · identidade FIXA (não white-label) · proxy /v1/admin/*
├── infra/
│   └── compose/    infra DEV do sidecar (postgres/redis/minio) + init SQL
│                   + smoke-test; SEPARADA da stack Znuny de produção
├── landing/        landing comercial estática (deploy próprio)
└── docs/
    ├── superpowers/specs|plans/   Spec #0, roadmap, Plano 1A, Plano #1C
    ├── adr/0001-monorepo-layout.md  ADR do projeto (layout do monorepo)
    └── decisions/0001-stack.md      ADR canônico da stack Znuny (não confundir)
```

`apps/sidecar/Makefile` é independente do `Makefile` raiz (stack Znuny).
gerti agora contém **só a apresentação** — todo o código vive aqui.

## (b) Modelo de schema Postgres compartilhado (Spec #0)

Spec #0: **um cluster Postgres, dois schemas**. Znuny dono de `znuny`;
sidecar dono de `gerti`. Núcleo Znuny imutável — nunca escrevemos em
`znuny` direto (escrita via Generic Interface; leitura read-only).

Estado atual (ponto de convergência — item aberto):

- **Znuny (prod):** roda seu próprio `postgres:18` (schema em `public`),
  ver `ARCHITECTURE.md`. O schema `gerti` ainda **não** existe nesse cluster.
- **Sidecar (testes):** usa **testcontainers** + o init
  `infra/compose/postgres/init/001_schemas_and_roles.sql`, que cria os
  schemas `gerti` + `znuny` e as roles `gerti_app` (NOLOGIN, RLS),
  `gerti_admin` (BYPASSRLS) e o usuário **`gerti_sidecar`** (IN ROLE
  `gerti_app`, **NÃO** bypassrls — runtime mínimo privilégio).
- **Convergência (pendente, item de integração):** unificar produção em
  um único cluster com ambos os schemas, sidecar conectando como
  `gerti_sidecar`. Hoje os dois caminhos coexistem sem acoplamento.

## (c) Segurança multi-tenant (verificada)

- `tenant_session_scope` / `get_tenant_session` (`apps/sidecar/src/
  gerti_sidecar/db.py`) abrem transação explícita e fazem
  `SELECT set_config('app.current_tenant', :tid, true)` (SET LOCAL
  transaction-scoped; asyncpg não aceita bind em `SET LOCAL`).
- Middleware de tenant resolve subdomínio → tenant e ativa o GUC.
- **FORCE RLS** por tabela `gerti.*`; políticas filtram por
  `current_setting('app.current_tenant')::uuid`.
- **Fail-closed:** sem `app.current_tenant` válido as policies não
  liberam linha; `gerti_sidecar` não tem BYPASSRLS. Coberto por
  `test_rls_isolation.py` e `test_tenant_session.py` rodando sob o
  usuário sem privilégio — **16/16 testes verdes nesta localização**.

## (d) Integração runtime Znuny ↔ sidecar (Spec #0 — alvo)

- **GertiHooks.opm** (Perl mínimo — webhooks HMAC; fora do escopo do #1B): dynamic
  fields (`GertiContractId`, `GertiBillableMinutes`, `GertiBillingStatus`),
  queues template e event handlers que disparam **webhooks HMAC**.
- **Znuny → sidecar (#1B, pull):** `sidecar-worker` faz **pull** via GI
  `TimeAccountingSince` (cursor `consumption_sync_cursor`) → `reconciliation_service`
  → grava `gerti.consumption_event` (idempotência por `webhook_event_id=uuid5`).
  Webhooks HMAC push (GertiHooks.opm) permanecem fora do escopo desta fase.
- **Sidecar → Znuny:** escrita via **Generic Interface** (REST); leitura
  do schema `znuny` read-only. Nunca SQL direto no schema Znuny.
- **Fluxo de domínio:** `contract → contract_cycle → consumption_event →
  glosa → billing` (ciclos faturamento/fechamento), materializado pelos
  workers Celery (fechamento, alertas, retry de webhook).

## (e) Construído vs pendente

| Item | Status |
|---|---|
| Plano 1A (fundação: estrutura, RLS, sidecar skeleton, testes) | **Pronto, verificado** |
| #1C T1–T13 (engine de contrato: enums, modelos, RLS, repos, ciclos, glosa, reajuste, matview, e2e) | **Pronto, verificado** — gate 33 passed/0 skip, S1 RLS hard-assert verde no head `0010`, review final independente APPROVE |
| Gap S1 (`gerti.znuny_instance` sem RLS desde 0001) | **Corrigido** — `0009_rls_znuny_instance` ENABLE+FORCE escopada por tenant (ADR D12) |
| Artefatos de deploy (compose profile `gerti`, `postgres/gerti-init/`, runbook) | **Prontos, no `origin/main`** — execução na VPS pendente (SSH inacessível no momento; ver OPS "Deploy do sidecar") |
| #1B GertiHooks.opm (webhooks/dynamic fields no Znuny) | Não iniciado |
| Convergência prod p/ cluster Postgres único compartilhado | **Resolvida no design**: `gerti-db-init` (job idempotente, profile-gated) introduz schema `gerti`+roles+RLS no `postgres:18` vivo; ver (b) e D13 |
| `tenant_branding` table + RLS (migration `0011_tenant_branding`) | **Pronto** |
| `GET /v1/branding` | **Pronto** |
| `POST /v1/auth/login`, `POST /v1/auth/logout` | **Pronto** |
| `GET /v1/me` | **Pronto** |
| `GET /v1/contracts` | **Pronto** |
| `znuny_gi.authenticate_customer` (mecanismo per D14: GI `Session::SessionCreate`) | **Pronto** |
| Portal SSR Nuxt 3 (`apps/portal/`) + branding middleware + tema CSS vars | **Pronto, gateado (profile `gerti`)** |
| 2 tenants white-label de teste Aurora + TechNova (seeded idempotentemente: `seed_demo_branding.py` + `scripts/seed-technova.pl` via `scripts/seed-demo.sh`) | **Pronto** |
| OIDC / #1D (troca de login-layer — swap-only, sem mudança de API pública) | Pendente (deferred) |
| Branding admin UI / onboarding de tenants (#1G) — estes 2 tenants são fixtures de teste, NÃO onboarding | **Pronto** (#1G-a, ADR D19) |
| Portal (Spec #1F) | **Pronto, gateado; deploy per runbook** |
| `GET /v1/contracts` estendido (+`id`, +`consumed_percent`) | **Pronto, gateado; deploy per runbook** — read-only sobre #1C |
| `GET /v1/contracts/{id}` (detalhe: saldo, totais, ciclo ativo, reajuste/renovação) | **Pronto, gateado; deploy per runbook** — read-only sobre #1C |
| `GET /v1/contracts/{id}/consumption` (eventos paginados + `counts_toward_balance`) | **Pronto, gateado; deploy per runbook** — read-only sobre #1C |
| `GET /v1/contracts/{id}/series` (série densa, cap 400 buckets) | **Pronto, gateado; deploy per runbook** — read-only sobre #1C |
| `GET /v1/dashboard` (cards saldo + alertas `warning`/`critical`) | **Pronto, gateado; deploy per runbook** — read-only sobre #1C |
| `contract_read_service` (`domain/contract_read_service.py`, regra S3 centralizada — ADR D17) | **Pronto, gateado** |
| Portal rich dashboard `/` (cards + sparklines + alertas) + detalhe `/contratos/[id]` (hero saldo + AreaChart + ciclos + ledger c/ glosa) | **Pronto, gateado; deploy per runbook** |
| Componentes SVG puros: `ProgressBar.vue`, `AreaChart.vue`, `Sparkline.vue` (brand-var, sem lib, SSR-safe) | **Pronto, gateado** |
| Assinatura WAS discreta (`WASSignature.vue`) nos dois tenants | **Pronto, gateado** |
| 2 tenants white-label de teste `aurora.was.dev.br` + `technova.was.dev.br` | **Pronto, ativos** |
| Papéis no portal (#1H): `gerti.portal_user_role` (migration 0012, FORCE RLS) + enum `gerti.portal_role` | **Pronto** (ADR D18) |
| Login resolve papel + claim `role` no JWT + `require_admin` (admin-only em `/v1/contracts*` e `/v1/dashboard`); `/v1/me` devolve `role` | **Pronto** — least-privilege em toda omissão |
| Portal #1H: middleware nomeada `auth`, nav por papel, página `/tickets` (placeholder #1E), login por e-mail | **Pronto** |
| Seed papéis: `portal_user_role` (admin+helpdesk/tenant) + `scripts/seed-helpdesk.pl` (customer_user help-desk no Znuny) | **Pronto** |
| Tickets / catálogo / abrir-chamado (#1E) | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: webservice Znuny `GertiTicket` (5 ops: `TicketCreate`/`TicketSearch`/`TicketGet`/`TicketReply`/`FormMeta`); `AccessToken` fail-closed | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: DynamicField `GertiContractId` (criado idempotentemente por `ensure-gerti-dynamicfield.pl`) | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: `GET /v1/ticketing/contracts` (selecionáveis pelo customer, non-admin) + `GET /v1/ticketing/form-meta` | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: `POST /v1/tickets` (multipart, cria ticket), `GET /v1/tickets` (role-scoped), `GET /v1/tickets/{id}` (ownership-guarded), `POST /v1/tickets/{id}/reply` | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: páginas portal `/tickets`, `/tickets/novo`, `/tickets/[id]` | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| #1E: `gerti.ticket_contract_link` populado após criação do ticket Znuny (billing-ready) | **Pronto + DEPLOYADO em prod (2026-06-08, e2e ao vivo)** |
| Billing / consumo (#1B) | **Pronto, gateado; deploy per runbook** |
| #1B: GI op `TimeAccountingSince` (GertiTicket WS, read-only, `time_accounting` since cursor, `AccessToken` fail-closed) | **Pronto, gateado; deploy per runbook** |
| #1B: migration `0013_consumption_sync_cursor` (watermark operacional `gerti.consumption_sync_cursor`) | **Pronto, gateado; deploy per runbook** |
| #1B: `reconciliation_service` (pull GI → `consumption_event` idempotente via uuid5; conversão hour_bank/credit_brl/shared; cross-tenant BYPASSRLS read + per-tenant RLS write; avança cursor) | **Pronto, gateado; deploy per runbook** |
| #1B: `cycle_closer` (fecha ciclos vencidos por tenant via `CycleService.close`, 1×/dia) | **Pronto, gateado; deploy per runbook** |
| #1B: `sidecar-worker` (serviço compose; loop asyncio: reconcile + close cycles) | **Pronto, gateado; deploy per runbook** |
| Console de Administração #1G-a: auth de agente (`/v1/admin/auth/*`, cookie `gsid_adm`), onboarding (`POST /v1/admin/tenants` → GI + tenant/branding/papéis), criar contrato (`POST /v1/admin/tenants/{id}/contracts`), app `apps/admin/` | **Pronto + DEPLOYADO em prod** (verificado ao vivo; ingress público `gerti.was.dev.br` pendente de CF API token — ADR D19) |
| Znuny GI custom (#1G-a, Opção A): webservice `GertiAdmin` + ops `CustomerCompanyAdd`/`CustomerUserAdd`/`SetPassword` (idempotentes, `AccessToken` fail-closed) em `znuny/Custom/...` | **Pronto, provado ao vivo** |
| Time tracker do agente (#1J): GI op `TimeAccountingAdd` (artigo interno + `TicketAccountTime`, resolve UserID do agente) | **Pronto, gateado; deploy per runbook** |
| #1J: GI op `AgentTicketSearch` (busca cross-tenant por agente) | **Pronto, gateado; deploy per runbook** |
| #1J: GI op `AgentTicketGet` (detalhe de ticket para agente + contrato vinculado) | **Pronto, gateado; deploy per runbook** |
| #1J: token `GertiAgent::AccessToken` (env `ZNUNY_AGENT_WS_TOKEN`) — separado do `GertiAdmin::AccessToken`; segurança por separação de ops root/cross-tenant | **Pronto, gateado; deploy per runbook** |
| #1J: migration `0014_agent_timer` (tabela operacional `gerti.agent_timer` + partial unique index: max 1 timer ativo por agente/ticket) | **Pronto, gateado; deploy per runbook** |
| #1J: `domain/timer_service.py` (start idempotente / pause / resume / stop com ownership check; computa minutos; cap `adjust_minutes` 1440; lança via GI e marca stopped) | **Pronto, gateado; deploy per runbook** |
| #1J: `routers/admin_timer.py` (`/v1/admin/timer/{start,pause,resume,stop,active}`; sob `get_admin_session`) | **Pronto, gateado; deploy per runbook** |
| #1J: `GET /v1/admin/tickets` (busca cross-tenant) + `GET /v1/admin/tickets/{id}` (detalhe + contrato vinculado) | **Pronto, gateado; deploy per runbook** |
| #1J: pages `apps/admin/` `/atendimento` (lista + timers inline + chip ativos) + `/atendimento/[id]` (detalhe + timer card) | **Pronto, gateado; deploy per runbook** |
| #1J: composable `useTimers`, componentes `TimerControls`/`TimerStopDialog`/`ContractBadge` | **Pronto, gateado; deploy per runbook** |
| #1K: 3 add-ons ITSM oficiais bakeados na imagem Znuny 7.2.1 (`GeneralCatalog`→`ITSMCore`→`ITSMConfigurationManagement`); `ensure-itsm.sh` instala idempotentemente no provisionamento; 5 classes nativas de CI com campo `CustomerID` (escopo por tenant) | **Pronto, gateado; deploy per runbook** |
| #1K: GI `ConfigItemSearch` (busca por CustomerID/tenant) + `ConfigItemGet` (detalhe anti-IDOR) no webservice `GertiTicket` | **Pronto, gateado; deploy per runbook** |
| #1K: `TicketCreate` estendido com `ConfigItemId` → link `RelevantTo` via `LinkObject` no Znuny | **Pronto, gateado; deploy per runbook** |
| #1K: sidecar `GET /v1/assets` (lista CIs scoped por tenant) + `GET /v1/assets/{id}` (detalhe anti-IDOR 404) | **Pronto, gateado; deploy per runbook** |
| #1K: `POST /v1/tickets` aceita `config_item_id` (opcional) | **Pronto, gateado; deploy per runbook** |
| #1K: portal `/ativos` (lista read-only) + `/ativos/[id]` (detalhe) + "Abrir chamado sobre este ativo" → `/tickets/novo?ativo=<id>`; nav "Ativos"; proxies com guard de path-injection | **Pronto, gateado; deploy per runbook** |
| Gestão avançada pela UI (editar contrato/fechar ciclo/glosa/reajuste) #1G-b | Pendente (deferred §9) |
| OIDC / PKCE (#1D) | Pendente (deferred §9) |
| Export CSV/PDF, filtros avançados, i18n | Pendente (deferred §9) |

## (f) Como rodar/testar o sidecar neste repo

```bash
cd apps/sidecar
uv sync --all-extras
make check          # = lint (ruff) + typecheck (mypy) + test (pytest)
# ou o gate completo verificado:
uv run ruff check . && uv run ruff format --check . && uv run mypy src \
  && DATABASE_URL=postgresql+asyncpg://x:y@localhost/z uv run pytest -q
```

`pytest` sobe Postgres efêmero via **testcontainers** e aplica
`infra/compose/postgres/init/001_schemas_and_roles.sql` (precisa de Docker).
A infra dev opcional (`infra/compose/`) é independente da stack Znuny raiz.
