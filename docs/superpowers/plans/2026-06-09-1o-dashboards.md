# #1O — Dashboards por tenant (híbrido) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. Steps usam checkbox (`- [ ]`).

**Goal:** KPIs operacionais por tenant — volume de chamados no tempo, por estado/prioridade, SLA em risco/estourado, utilização de agentes (horas), **CSAT médio** (#1M) e saldo/consumo (#1B). **Charts próprios** (SVG) no portal (admin do tenant vê o seu) e no console (agente vê por-tenant + global); **OpenSearch Dashboards** só para exploração ad-hoc **interna** (não exposto ao cliente).

**Architecture:** sem tabela nova. O sidecar **agrega**: o que já é nosso (consumo `#1B`, CSAT `#1M`, timers `#1J`) vem do Postgres tenant-scoped; contagens de ticket por estado/período/SLA vêm de uma **nova GI op `TicketStats`** (escopada por `CustomerID`). Endpoint `GET /v1/dashboard/metrics` (portal admin, tenant-scoped) e `GET /v1/admin/analytics?tenant_id=` (console). Charts reusam o padrão SVG (`AreaChart`/`ProgressBar`) + 2 novos (`BarChart`, `DonutChart`). OpenSearch Dashboards apenas configurado/documentado apontando para os índices do Znuny.

**Tech Stack:** FastAPI, GI Perl (`Custom/`), Nuxt 3 (charts SVG), pytest, vitest. **Sem migration** (encadeia depois de `0016`; este plano não cria revisão).

---

### Task 1: GI op `TicketStats` (contagens por CustomerID)

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm`
- Modify: `znuny/webservices/GertiTicket.yml` (registrar op + rota `/Ticket/Stats`)
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (`ticket_stats(customer_id, since, until)`)
- Test: `apps/sidecar/tests/test_ticket_stats_client.py`

- [ ] **Step 1: Teste falhando (cliente)** — mock GI retornando `{ByState:{open:3,closed:7}, ByPriority:{...}, ByDay:[{date,count}], SlaBreached:2, SlaAtRisk:1}`; `ticket_stats` mapeia para dataclass `TicketStats`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3a: Perl** — `TicketStats.pm` (overlay `Custom/`, mesmo esqueleto de `ConfigItemGet.pm`): valida `AccessToken` (`GertiAdmin::AccessToken`) + `CustomerCompany` obrigatório (anti-IDOR: só conta tickets do `CustomerID` do tenant); usa `TicketSearch` com `CustomerID`, filtros de período e agrupa por `StateType`/`Priority`/dia; conta escalation (`TicketSearch` com `TicketEscalationTimeOlderMinutes`/flags de SLA) para `SlaBreached`/`SlaAtRisk`. Retorna o hash acima. **Nunca** retorna dados de outro CustomerID.
- [ ] **Step 3b: YAML** — adicionar `TicketStats` em `Operation` (`Type: GertiTicket::TicketStats`) e rota `/Ticket/Stats` no `RouteOperationMapping` (POST), espelhando `ConfigItemGet`.
- [ ] **Step 3c: Cliente** — `ticket_stats(*, customer_id, since, until)` via `_post("/Ticket/Stats", {...})`.
- [ ] **Step 4: Rodar** → PASS; `perl -c` no .pm. **Commit:** `feat(#1O): GI TicketStats (contagens por CustomerID, anti-IDOR)`.

---

### Task 2: Domain `MetricsService` (agrega Postgres + GI)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/metrics_service.py`
- Test: `apps/sidecar/tests/test_metrics_service.py`

- [ ] **Step 1: Teste falhando** — com seed de `csat_response` (notas), `consumption_event`/saldo e mock de `ticket_stats`, `tenant_metrics(tenant_id, customer_id, period)` retorna um dict tipado `{tickets:{by_state,by_day,sla_breached}, csat:{avg,count,distribution}, hours:{...}, balance:{...}}`. Provar que CSAT médio é calculado da tabela sob `tenant_session_scope` (RLS).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Service** — `__init__(self, session, gi)`; `tenant_metrics(...)`:
  - CSAT: `SELECT avg(score), count(*), score histogram FROM csat_response` (tenant-scoped).
  - Horas: agregação de `agent_timer.committed_time_unit` / time accounting do período (reusar `contract_read_service` se já expõe).
  - Saldo/consumo: reusar `ContractReadService` (#1B) — não reimplementar.
  - Tickets/SLA: `await gi.ticket_stats(customer_id=..., since=..., until=...)`.
  - Falha do GI → degrada o bloco `tickets` para `None` (dashboard ainda renderiza o resto). Failure-soft.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1O): MetricsService agregando CSAT/horas/saldo/tickets`.

---

### Task 3: Endpoints — portal (`/v1/dashboard/metrics`) e console (`/v1/admin/analytics`)

**Files:**
- Modify: `apps/sidecar/src/gerti_sidecar/routers/dashboard.py` (novo `GET /dashboard/metrics`, admin do tenant)
- Create: `apps/sidecar/src/gerti_sidecar/routers/admin_analytics.py` (`GET /admin/analytics?tenant_id=`, agente)
- Modify: `main.py` (`include_router(admin_analytics.router, ...)`)
- Test: `apps/sidecar/tests/test_dashboard_metrics_router.py`, `tests/test_admin_analytics_router.py`

- [ ] **Step 1: Testes falhando** — portal: `gsid` admin do tenant → 200 com blocos; `helpdesk` → 403 (reusar `require_admin`); sem sessão → 401. Console: `gsid_adm` + `tenant_id` → 200; `tenant_id` inválido → 404; sem sessão → 401.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:**
  - Portal: `GET /dashboard/metrics` com `Depends(require_admin)`; resolve `customer_id` do `request.state.tenant`; `tenant_session_scope(tenant_id)`; chama `MetricsService.tenant_metrics(...)`. Aceita `?period=30d|90d` (default 30d).
  - Console: `GET /admin/analytics` com `Depends(get_admin_session)`; valida `tenant_id` (UUID) via `AdminSessionLocal`; resolve `customer_id` do tenant; `tenant_session_scope(tenant_id, factory=AdminSessionLocal)`; mesma agregação. (Agente é cross-tenant → BYPASSRLS, mas a query passa o GUC para reusar as policies sem vazamento.)
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1O): endpoints dashboard/metrics (portal) + admin/analytics (console)`.

---

### Task 4: Charts novos `BarChart.vue` + `DonutChart.vue`

**Files:**
- Create: `apps/portal/components/charts/BarChart.vue`, `apps/portal/components/charts/DonutChart.vue`
- Copy: idem em `apps/admin/components/charts/` (mesmos arquivos — apps não compartilham bundle)
- Test: `apps/portal/test/charts.test.ts` (estender)

- [ ] **Step 1: Teste falhando** — `BarChart` renderiza N `<rect>` a partir de `{label,value}[]`, usa `var(--brand-primary)`, SSR-safe (`viewBox` fixo, `useId()`); `DonutChart` renderiza `<path>`/`<circle>` por fatia, soma proporcional, cores **semânticas** para estados (ex.: SLA estourado=error).
- [ ] **Step 2: Rodar** vitest → FAIL.
- [ ] **Step 3:** Implementar ambos em SVG puro seguindo `AreaChart.vue` (props tipadas, `preserveAspectRatio`, sem `window`). `DonutChart` aceita `palette: 'brand' | 'semantic'`.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1O): BarChart + DonutChart (SVG, brand/semântico, SSR-safe)`.

---

### Task 5: Páginas de dashboard (portal + console)

**Files:**
- Create: `apps/portal/server/api/portal/dashboard/metrics.get.ts`
- Modify: `apps/portal/pages/index.vue` (seção “Indicadores” com os charts, admin-only — a página já é admin-only)
- Create: `apps/admin/server/api/admin/analytics.get.ts`
- Create: `apps/admin/pages/analytics/index.vue` (seletor de tenant + charts; global = todos)
- Modify: `apps/admin/layouts/default.vue` (nav “Analytics”)
- Test: `apps/portal/test/dashboard-metrics.test.ts`

- [ ] **Step 1: Teste** — proxy repassa status; página monta os charts a partir do payload (mock de `useAsyncData`).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** Proxies (`sidecarFetch`); `pages/index.vue` ganha cards com `AreaChart` (volume/dia), `DonutChart` (por estado, semântico), `BarChart` (CSAT distribution), `ProgressBar` (saldo) + KPIs numéricos (CSAT médio, SLA estourado) com `Intl.NumberFormat('pt-BR')`. Console `analytics/index.vue`: `USelect` de tenant (lista de `/v1/admin/tenants`) + opção “Todos”; ao trocar, refaz o fetch; mesmos charts. **H8**: estados em cores semânticas, identidade na marca.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1O): páginas de dashboard (portal indicadores + console analytics)`.

---

### Task 6: OpenSearch Dashboards ad-hoc (interno) + deploy + e2e + docs

**Files:**
- Modify: `docker-compose.yml` (garantir serviço OpenSearch Dashboards no profile interno, **sem** rota pública no Cloudflare — só acesso interno/VPN)
- Modify: `.ia/ARCHITECTURE.md` (fluxo de métricas + OpenSearch ad-hoc interno), `.ia/INTEGRATION.md` (#1O), `.ia/OPS.md` (runbook: `Update --webservice-id 3` p/ TicketStats; acesso ao OpenSearch Dashboards interno).

- [ ] **Step 1:** `make test` verde (sidecar + portal + admin).
- [ ] **Step 2:** Deploy — `Update --webservice-id 3` (TicketStats); rebuild+up `sidecar`, `portal`, `admin`. Subir OpenSearch Dashboards **apenas interno** (sem Public Hostname no tunnel; documentar que é ferramenta de operação, dados crus do Znuny).
- [ ] **Step 3: e2e** — portal (admin Aurora): `/` mostra indicadores com dados reais (volume, CSAT médio do #1M, saldo). Console: `/analytics` com seletor de tenant troca os números; “Todos” agrega. Confer que helpdesk não vê os indicadores admin.
- [ ] **Step 4:** `.ia/` status “DEPLOYADO + e2e”. **Commit:** `docs(#1O): dashboards deployados + OpenSearch ad-hoc interno`.

## Não-objetivos
Métricas em tempo real/streaming, exportar PDF/CSV do dashboard (fica para um #export futuro), expor OpenSearch Dashboards ao cliente (é só interno), drill-down por ticket, comparação entre períodos.
