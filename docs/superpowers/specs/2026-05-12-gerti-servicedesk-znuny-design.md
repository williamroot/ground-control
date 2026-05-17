# Spec #0 — Gerti Service Desk: arquitetura geral baseada em Znuny

**Data**: 2026-05-12
**Status**: Draft para revisão
**Autor**: William Alves (Gerti) com assistência Claude (Anthropic)
**Cobertura**: arquitetura geral, modelo de dados de contratos, contratos de integração, multi-tenancy, fluxos críticos, infraestrutura (Docker Compose), ADRs, roadmap.

---

## 1. Resumo executivo

A Gerti construirá uma **plataforma própria de Service Desk multi-tenant** para operar internamente e atender seus clientes finais, substituindo o **Tiflux SaaS** atualmente em `suporte.gerti.com.br`. A base será **Znuny LTS** (fork open-source GPL v3 do OTRS Community 6.0.30, mantido pela Znuny GmbH) acrescida de um **sidecar Python/FastAPI** que carrega a lógica de produto (contratos, faturamento, dashboards, branding) e um **Portal Cliente Nuxt 3 (Vue 3)** white-label por cliente final em modo SSR/Universal.

O caminho é deliberadamente **híbrido**: o pacote `.opm` que estende o Znuny é mínimo (dynamic fields, queues, event handlers que disparam webhooks); toda a lógica de negócio fica no sidecar Python, que o time da Gerti consegue manter (stack PHP/Node/Python/Go). Conceitualmente continua sendo "um plugin do Znuny" — mas o ponto de extensão pesado é um serviço sidecar moderno.

**Horizonte**: piloto operando para um cliente novo em **12 semanas (3 meses) firme**, com time expandido (~6-7 pessoas) e paralelismo entre sub-projetos. **Migração de dados do Tiflux está fora do MVP** — o foco é operar como se fosse para cliente novo. Plano de fases em [`../plans/2026-05-12-spec-1-roadmap.md`](../plans/2026-05-12-spec-1-roadmap.md).

## 2. Visão e princípios fundadores

### 2.1 Princípios

1. **Znuny core é imutável**. Nunca escrevemos no schema `znuny` direto. Escrita via Generic Interface (REST); leitura via repository read-only.
2. **Sidecar é o cérebro de negócio**. Contratos, ciclos, glosa, faturamento, dashboards, branding são responsabilidade do sidecar Python. Znuny só sabe de tickets, filas, SLA, ACLs, CMDB.
3. **Identidade unificada**. Agentes e customer users existem no Znuny (autoritativo). Sidecar e Portal autenticam via Auth Bridge OIDC. Sem duplicação.
4. **Multi-tenancy híbrido**. Pool compartilhado para a maioria + instâncias dedicadas sob demanda para clientes grandes/regulados.
5. **Open standards**. REST/OpenAPI 3.1, OAuth2/OIDC, webhooks com HMAC, OpenTelemetry.
6. **Plugin `.opm` mínimo**. Apenas dynamic fields, queues e event handlers que disparam webhooks; nada de regra de negócio em Perl.
7. **Extensível para roadmap futuro**. WhatsApp, IA, integrações (Zabbix/PRTG/M365) cabem sem reabrir arquitetura.

### 2.2 Não-objetivos da Spec #0

- UX/telas detalhadas do portal — Spec #1
- Detalhe de integração Asaas/NFe — Spec #2
- App mobile do técnico — Spec #3
- Migração de dados Tiflux — fora do MVP

### 2.3 Stack escolhida (Abordagem B do brainstorming)

| Camada | Tech |
|---|---|
| Core de ticketing/ITSM | **Znuny LTS** (Perl + mod_perl + Apache) |
| Plugin de gancho | **GertiHooks.opm** (Perl, mínimo) |
| Sidecar de negócio | **Python 3.12 + FastAPI + SQLAlchemy + Alembic + Pydantic** |
| Jobs assíncronos | **Celery + Redis** |
| Banco de dados | **PostgreSQL 16** (cluster único, schemas `znuny` e `gerti`) |
| Portal cliente | **Nuxt 3 (Vue 3, SSR Universal) + Nuxt UI v3 + Pinia + @vueuse/nuxt + TypeScript + Tailwind** |
| Auth bridge | **FastAPI** custom (OIDC + JWT RS256) |
| Anexos | **MinIO** (S3-compatível) |
| Email | **Postfix + Dovecot + OpenDKIM + relay SES** |
| Antivírus | **ClamAV** |
| Busca | **OpenSearch 2.x** |
| Observabilidade | **OpenTelemetry → Grafana + Loki + Tempo + Prometheus** |
| Secrets | **Vault OSS** (ou AWS Secrets Manager) |
| Reverse proxy | **Traefik** |
| Plataforma de deploy | **Docker Compose** (uma stack por instância) |

## 3. Arquitetura de componentes

### 3.1 Diagrama geral

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CLIENTES (Web/Mobile/Email)                     │
└────────┬─────────────────────────────────────────┬──────────────────┘
         │                                         │
         ▼                                         ▼
┌─────────────────────┐                  ┌──────────────────────────┐
│ Portal Cliente SPA  │                  │ Znuny Customer Interface │
│  Vue 3 · Nuxt 3 SSR │                  │ (fallback admin)         │
│ <tenant>.suporte.   │                  └──────────────────────────┘
│  gerti.com.br       │
└────────┬────────────┘
         │ HTTPS/REST + OAuth2 (PKCE)
         ▼
┌────────────────────────────────────────────────────────────────────┐
│           Gerti Service Desk API (Sidecar Python/FastAPI)          │
│  módulos: contratos | portal | catálogo | dashboards | webhooks   │
│           znuny_repository (read-only views) | auth_bridge         │
└──────┬──────────────────────────┬─────────────────────────────────┘
       │ REST (Generic Interface) │ SELECT em schema znuny (read-only)
       ▼                          │
┌──────────────────────┐          │
│ Znuny (Apache+Perl)  │◄─────────┘
│ + GertiHooks.opm     │
│ + ITSM CMDB pkg      │──── webhooks HMAC ────┐
└────────┬─────────────┘                       │
         ▼                                     ▼
┌──────────────────────────────────────┐   ┌─────────────────────┐
│ PostgreSQL (schemas znuny + gerti)   │   │ Celery workers + beat│
└──────────────────────────────────────┘   └─────────────────────┘
         ▲                                     ▲
         │                                     │
    Redis (cache + broker), MinIO (anexos), OpenSearch (busca),
    ClamAV, Postfix/Dovecot, OTEL stack, Vault.
```

### 3.2 Tabela de componentes

| Componente | Responsabilidade | Tech |
|---|---|---|
| Znuny core | Tickets, filas, SLA, ACLs, Process Mgmt, customer companies, ITSM/CMDB | Perl 5 + mod_perl |
| GertiHooks `.opm` | Dynamic fields (`GertiContractId`, `GertiBillableMinutes`, `GertiBillingStatus`), queues template, event handlers → webhooks | Perl 5 |
| Sidecar API | CRUD contratos, ciclos, consumo, glosa, dashboards, catálogo, branding, webhooks IN, OIDC bridge | FastAPI |
| Workers Celery | Fechamento de ciclo, alertas, retry webhooks, materialização de dashboards, jobs LGPD | Celery + Redis |
| Portal (Nuxt) | Interface white-label por subdomínio, login OIDC PKCE, abertura via catálogo, dashboards, aprovação de tickets, server middleware para BFF e injeção de branding por tenant | Nuxt 3 + Vue 3 + Nuxt UI v3 + Pinia |
| MinIO | S3-compatível para anexos (Znuny + Portal); chave `tenant/{tenant_id}/...` | MinIO |
| Postfix MTA | Email-to-ticket inbound + outbound com DKIM/SPF/DMARC via SES | Postfix |
| ClamAV | Scan AV antes de liberar anexo (`pending_scan` → `available`) | clamav-daemon |
| OpenSearch | Indexa tickets e KB para busca rápida | OpenSearch 2.x |
| Auth Bridge | Endpoints OIDC (`/authorize`, `/token`, `/userinfo`); valida contra Znuny; emite JWT RS256 | FastAPI |
| Observabilidade | OTEL Collector → Loki + Tempo + Prometheus → Grafana | Grafana stack |
| Vault | Secrets para Asaas, NFe, Meta, SES, tokens Znuny | Vault OSS |
| Reverse proxy | TLS interno, roteamento por host, rate limit, auth headers | Traefik |

## 4. Modelo de dados — schema `gerti`

### 4.1 Diagrama de entidades

```
tenant ──┬── tenant_branding
         ├── tenant_billing_profile
         └── contract ──┬── contract_billing_party
                        ├── contract_scope_service (→ service_catalog_item)
                        ├── contract_scope_ci      (→ znuny.configitem via view)
                        ├── contract_adjustment_rule
                        ├── contract_renewal_policy
                        ├── shared_credit_pool (opcional, N:N)
                        └── contract_cycle ──┬── consumption_event ──┬── glosa
                                              │                      │
                                              └── ticket_contract_link
znuny_instance ── tenant (cada tenant aponta para instância)
audit_log (transversal, append-only)
```

### 4.2 DDL completo (PostgreSQL 16)

```sql
CREATE SCHEMA gerti;

-- ENUMS ---------------------------------------------------------------------

CREATE TYPE gerti.contract_type AS ENUM (
  'closed_value',    -- valor fechado por serviços
  'credit_brl',      -- crédito em R$ pré-pago
  'credit_shared',   -- crédito compartilhado entre contratos
  'hour_bank',       -- banco de horas + franquia de deslocamento
  'saas_product',    -- SaaS/produto recorrente
  'service_count'    -- N serviços fixos por ciclo
);

CREATE TYPE gerti.contract_status   AS ENUM ('draft', 'active', 'suspended', 'expired', 'terminated');
CREATE TYPE gerti.cycle_kind        AS ENUM ('billing', 'closing');
CREATE TYPE gerti.cycle_status      AS ENUM ('open', 'closed', 'invoiced');
CREATE TYPE gerti.glosa_status      AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE gerti.billing_status    AS ENUM ('pending', 'approved', 'billed', 'disputed');
CREATE TYPE gerti.instance_mode     AS ENUM ('pool', 'dedicated');

-- INSTÂNCIAS Znuny -----------------------------------------------------------

CREATE TABLE gerti.znuny_instance (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                        TEXT NOT NULL,
  base_url                    TEXT NOT NULL,
  db_dsn_secret_ref           TEXT NOT NULL,           -- ref Vault
  webservice_token_secret_ref TEXT NOT NULL,
  webhook_signing_secret_ref  TEXT NOT NULL,
  mode                        gerti.instance_mode NOT NULL,
  status                      TEXT NOT NULL DEFAULT 'active',
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- TENANT (cliente da Gerti) --------------------------------------------------

CREATE TABLE gerti.tenant (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_name          TEXT NOT NULL,
  trade_name          TEXT NOT NULL,
  document            TEXT NOT NULL,            -- CNPJ
  znuny_customer_id   TEXT NOT NULL UNIQUE,     -- liga com customer_company do Znuny
  znuny_instance_id   UUID NOT NULL REFERENCES gerti.znuny_instance(id),
  subdomain           TEXT NOT NULL UNIQUE,     -- 'acme' → acme.suporte.gerti.com.br
  status              TEXT NOT NULL DEFAULT 'active',
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at         TIMESTAMPTZ
);

CREATE INDEX ON gerti.tenant (status);
CREATE INDEX ON gerti.tenant (znuny_instance_id);

CREATE TABLE gerti.tenant_branding (
  tenant_id           UUID PRIMARY KEY REFERENCES gerti.tenant(id) ON DELETE CASCADE,
  logo_url            TEXT,
  favicon_url         TEXT,
  primary_color       TEXT,
  accent_color        TEXT,
  custom_css          TEXT,
  allowed_origins     TEXT[] NOT NULL DEFAULT '{}',
  smtp_from           TEXT,                     -- ex: suporte@acme.com
  smtp_relay_secret_ref TEXT,                   -- relay próprio opcional
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gerti.tenant_billing_profile (
  tenant_id           UUID PRIMARY KEY REFERENCES gerti.tenant(id) ON DELETE CASCADE,
  legal_name          TEXT NOT NULL,
  document            TEXT NOT NULL,
  state_registration  TEXT,
  fiscal_address      JSONB NOT NULL,
  default_payment_method TEXT,
  asaas_customer_id   TEXT,                     -- mapeado pelo módulo Spec #2
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CATÁLOGO DE SERVIÇOS -------------------------------------------------------

CREATE TABLE gerti.service_catalog_item (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID REFERENCES gerti.tenant(id),  -- NULL = global
  code                TEXT NOT NULL,
  title               TEXT NOT NULL,
  description         TEXT,
  category            TEXT,
  default_queue_name  TEXT NOT NULL,            -- nome lógico mapeado por tenant
  default_priority    SMALLINT NOT NULL DEFAULT 3,
  default_sla_minutes INTEGER,
  form_schema         JSONB NOT NULL DEFAULT '{}',  -- JSON Schema do formulário dinâmico
  unit_price_brl      NUMERIC(14,2),
  active              BOOLEAN NOT NULL DEFAULT true,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ON gerti.service_catalog_item (COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid), code);
CREATE INDEX ON gerti.service_catalog_item (tenant_id, active);

-- POOL DE CRÉDITO COMPARTILHADO ---------------------------------------------

CREATE TABLE gerti.shared_credit_pool (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID NOT NULL REFERENCES gerti.tenant(id),
  name                  TEXT NOT NULL,
  total_amount_brl      NUMERIC(14,2) NOT NULL,
  cycle_kind            gerti.cycle_kind NOT NULL,
  cycle_period_months   INTEGER NOT NULL,
  current_cycle_start   DATE NOT NULL,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON gerti.shared_credit_pool (tenant_id);

-- CONTRATO -------------------------------------------------------------------

CREATE TABLE gerti.contract (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                   UUID NOT NULL REFERENCES gerti.tenant(id),
  code                        TEXT NOT NULL,
  type                        gerti.contract_type NOT NULL,
  status                      gerti.contract_status NOT NULL DEFAULT 'active',
  starts_on                   DATE NOT NULL,
  ends_on                     DATE NOT NULL,

  initial_amount_brl          NUMERIC(14,2),
  initial_hours               NUMERIC(10,2),
  initial_service_count       INTEGER,
  unit_price_brl              NUMERIC(14,2),
  travel_franchise_count      INTEGER NOT NULL DEFAULT 0,

  billing_period_months       INTEGER NOT NULL DEFAULT 1,
  closing_period_months       INTEGER NOT NULL DEFAULT 1,
  billing_in_advance          BOOLEAN NOT NULL DEFAULT true,

  accumulate_balance_between_cycles BOOLEAN NOT NULL DEFAULT false,

  shared_pool_id              UUID REFERENCES gerti.shared_credit_pool(id),

  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by                  TEXT NOT NULL,
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (tenant_id, code),
  CHECK (ends_on > starts_on),
  CHECK (closing_period_months % billing_period_months = 0
         OR billing_period_months % closing_period_months = 0)
);

CREATE INDEX ON gerti.contract (tenant_id, status);
CREATE INDEX ON gerti.contract (ends_on) WHERE status = 'active';
CREATE INDEX ON gerti.contract (shared_pool_id) WHERE shared_pool_id IS NOT NULL;

-- DETALHES DO CONTRATO -------------------------------------------------------

CREATE TABLE gerti.contract_billing_party (
  contract_id      UUID PRIMARY KEY REFERENCES gerti.contract(id) ON DELETE CASCADE,
  legal_name       TEXT NOT NULL,
  document         TEXT NOT NULL,
  fiscal_address   JSONB NOT NULL,
  payment_method   TEXT
);

CREATE TABLE gerti.contract_scope_service (
  contract_id          UUID REFERENCES gerti.contract(id) ON DELETE CASCADE,
  service_id           UUID REFERENCES gerti.service_catalog_item(id),
  unit_price_override  NUMERIC(14,2),
  PRIMARY KEY (contract_id, service_id)
);

CREATE TABLE gerti.contract_scope_ci (
  contract_id       UUID REFERENCES gerti.contract(id) ON DELETE CASCADE,
  znuny_ci_id       INTEGER NOT NULL,        -- liga com znuny.configitem via view
  covered_from      DATE NOT NULL,
  covered_until     DATE,
  PRIMARY KEY (contract_id, znuny_ci_id, covered_from)
);

CREATE TABLE gerti.contract_adjustment_rule (
  contract_id       UUID PRIMARY KEY REFERENCES gerti.contract(id) ON DELETE CASCADE,
  index_code        TEXT NOT NULL,           -- IPCA, IGPM, CDI, fixed
  cadence_months    INTEGER NOT NULL,
  next_run_on       DATE NOT NULL,
  cap_percent       NUMERIC(5,2),
  last_applied_on   DATE,
  last_applied_percent NUMERIC(6,3)
);

CREATE TABLE gerti.contract_renewal_policy (
  contract_id      UUID PRIMARY KEY REFERENCES gerti.contract(id) ON DELETE CASCADE,
  auto_renew       BOOLEAN NOT NULL DEFAULT false,
  notice_days      INTEGER NOT NULL DEFAULT 30,
  next_review_on   DATE NOT NULL,
  renewal_term_months INTEGER
);

-- CICLOS ---------------------------------------------------------------------

CREATE TABLE gerti.contract_cycle (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id   UUID NOT NULL REFERENCES gerti.contract(id),
  kind          gerti.cycle_kind NOT NULL,
  period_start  DATE NOT NULL,
  period_end    DATE NOT NULL,
  status        gerti.cycle_status NOT NULL DEFAULT 'open',
  opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at     TIMESTAMPTZ,
  totals        JSONB,
  UNIQUE (contract_id, kind, period_start)
);

CREATE INDEX ON gerti.contract_cycle (contract_id, status);
CREATE INDEX ON gerti.contract_cycle (period_end) WHERE status = 'open';

-- CONSUMO (append-only) ------------------------------------------------------

CREATE TABLE gerti.consumption_event (
  id                  BIGSERIAL PRIMARY KEY,
  contract_id         UUID NOT NULL REFERENCES gerti.contract(id),
  occurred_at         TIMESTAMPTZ NOT NULL,
  source_kind         TEXT NOT NULL,         -- ticket_work | travel | service_item | adjustment
  source_ref          TEXT NOT NULL,         -- znuny:ticket:12345 / znuny:article:67
  service_id          UUID REFERENCES gerti.service_catalog_item(id),
  billable_minutes    NUMERIC(10,2) NOT NULL DEFAULT 0,
  billable_amount_brl NUMERIC(14,2) NOT NULL DEFAULT 0,
  unit_price_at_event NUMERIC(14,2),
  glosa_id            UUID,
  closing_cycle_id    UUID REFERENCES gerti.contract_cycle(id),
  recorded_by         TEXT NOT NULL,
  recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  webhook_event_id    UUID                    -- idempotência
);

CREATE UNIQUE INDEX consumption_event_idempotency
  ON gerti.consumption_event (webhook_event_id) WHERE webhook_event_id IS NOT NULL;

CREATE INDEX ON gerti.consumption_event (contract_id, occurred_at DESC);
CREATE INDEX ON gerti.consumption_event (closing_cycle_id);
CREATE INDEX ON gerti.consumption_event (source_ref);

-- GLOSA ----------------------------------------------------------------------

CREATE TABLE gerti.glosa (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  consumption_event_id  BIGINT NOT NULL REFERENCES gerti.consumption_event(id),
  status                gerti.glosa_status NOT NULL DEFAULT 'pending',
  reason                TEXT NOT NULL,
  requested_by          TEXT NOT NULL,
  requested_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_by           TEXT,
  reviewed_at           TIMESTAMPTZ,
  reviewer_note         TEXT
);

CREATE INDEX ON gerti.glosa (consumption_event_id);
CREATE INDEX ON gerti.glosa (status);

-- LINK TICKET ↔ CONTRATO -----------------------------------------------------

CREATE TABLE gerti.ticket_contract_link (
  znuny_ticket_id  INTEGER PRIMARY KEY,
  contract_id      UUID NOT NULL REFERENCES gerti.contract(id),
  tenant_id        UUID NOT NULL REFERENCES gerti.tenant(id),
  billing_status   gerti.billing_status NOT NULL DEFAULT 'pending',
  linked_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  linked_by_rule   TEXT NOT NULL    -- auto:scope_service | auto:default | manual
);

CREATE INDEX ON gerti.ticket_contract_link (contract_id);
CREATE INDEX ON gerti.ticket_contract_link (tenant_id, billing_status);

-- AUDIT LOG (append-only com hash chain) ------------------------------------

CREATE TABLE gerti.audit_log (
  id              BIGSERIAL PRIMARY KEY,
  occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor           TEXT NOT NULL,           -- 'user:<id>' | 'system' | 'webhook:znuny'
  tenant_id       UUID,
  action          TEXT NOT NULL,           -- contract.created | data.exported | ...
  resource_kind   TEXT NOT NULL,
  resource_id     TEXT,
  payload         JSONB,                   -- delta ou contexto
  prev_hash       BYTEA,                   -- hash do registro anterior
  record_hash     BYTEA NOT NULL           -- sha256(prev_hash || payload)
);

CREATE INDEX ON gerti.audit_log (tenant_id, occurred_at DESC);
CREATE INDEX ON gerti.audit_log (resource_kind, resource_id);

-- View materializada de saldo --------------------------------------------------

CREATE MATERIALIZED VIEW gerti.contract_balance_current AS
SELECT
  c.id AS contract_id,
  c.type,
  CASE c.type
    WHEN 'credit_brl' THEN
      c.initial_amount_brl - COALESCE(SUM(ce.billable_amount_brl) FILTER (
        WHERE ce.glosa_id IS NULL OR EXISTS (
          SELECT 1 FROM gerti.glosa g
          WHERE g.id = ce.glosa_id AND g.status = 'rejected'
        )
      ), 0)
    WHEN 'hour_bank' THEN
      c.initial_hours - COALESCE(SUM(ce.billable_minutes) FILTER (
        WHERE ce.glosa_id IS NULL OR EXISTS (
          SELECT 1 FROM gerti.glosa g
          WHERE g.id = ce.glosa_id AND g.status = 'rejected'
        )
      ), 0) / 60.0
    WHEN 'service_count' THEN
      c.initial_service_count - COALESCE(COUNT(ce.*) FILTER (
        WHERE ce.source_kind = 'service_item'
      ), 0)
    ELSE NULL
  END AS remaining
FROM gerti.contract c
LEFT JOIN gerti.consumption_event ce ON ce.contract_id = c.id
GROUP BY c.id;

CREATE UNIQUE INDEX ON gerti.contract_balance_current (contract_id);

-- VIEWS de leitura do schema znuny (read-only) -------------------------------

CREATE OR REPLACE VIEW gerti.v_znuny_ticket AS
  SELECT
    t.id              AS ticket_id,
    t.tn              AS ticket_number,
    t.title           AS title,
    t.queue_id,
    t.customer_id     AS customer_company_key,
    t.customer_user_id AS customer_user_login,
    t.ticket_state_id,
    t.create_time     AS created_at,
    t.change_time     AS updated_at
  FROM znuny.ticket t;

CREATE OR REPLACE VIEW gerti.v_znuny_article AS
  SELECT
    a.id              AS article_id,
    a.ticket_id,
    a.create_by       AS agent_id,
    a.create_time     AS created_at,
    a.is_visible_for_customer
  FROM znuny.article a;

-- Role read-only para o sidecar acessar schema znuny -------------------------

CREATE ROLE gerti_app NOLOGIN;
GRANT USAGE ON SCHEMA znuny TO gerti_app;
GRANT SELECT ON ALL TABLES IN SCHEMA znuny TO gerti_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA znuny GRANT SELECT ON TABLES TO gerti_app;
GRANT USAGE, CREATE ON SCHEMA gerti TO gerti_app;

-- Usuário aplicacional herda gerti_app
CREATE USER gerti_sidecar PASSWORD :'sidecar_password' IN ROLE gerti_app;

-- RLS para multi-tenancy em pool ---------------------------------------------

ALTER TABLE gerti.contract             ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.consumption_event    ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_cycle       ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.ticket_contract_link ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.service_catalog_item ENABLE ROW LEVEL SECURITY;

CREATE POLICY t_isolation ON gerti.contract
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY t_isolation ON gerti.consumption_event
  USING (contract_id IN (
    SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid
  ));

CREATE POLICY t_isolation ON gerti.contract_cycle
  USING (contract_id IN (
    SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid
  ));

CREATE POLICY t_isolation ON gerti.ticket_contract_link
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

CREATE POLICY t_isolation ON gerti.service_catalog_item
  USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true)::uuid);

-- Tabelas adicionais com RLS
ALTER TABLE gerti.tenant_branding         ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.tenant_billing_profile  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_billing_party  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_scope_service  ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_scope_ci       ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_adjustment_rule ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.contract_renewal_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.glosa                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.shared_credit_pool      ENABLE ROW LEVEL SECURITY;
ALTER TABLE gerti.audit_log               ENABLE ROW LEVEL SECURITY;

CREATE POLICY t_isolation ON gerti.tenant_branding
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY t_isolation ON gerti.tenant_billing_profile
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY t_isolation ON gerti.contract_billing_party
  USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid));
CREATE POLICY t_isolation ON gerti.contract_scope_service
  USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid));
CREATE POLICY t_isolation ON gerti.contract_scope_ci
  USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid));
CREATE POLICY t_isolation ON gerti.contract_adjustment_rule
  USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid));
CREATE POLICY t_isolation ON gerti.contract_renewal_policy
  USING (contract_id IN (SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid));
CREATE POLICY t_isolation ON gerti.glosa
  USING (consumption_event_id IN (
    SELECT id FROM gerti.consumption_event WHERE contract_id IN (
      SELECT id FROM gerti.contract WHERE tenant_id = current_setting('app.current_tenant', true)::uuid
    )
  ));
CREATE POLICY t_isolation ON gerti.shared_credit_pool
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);
CREATE POLICY t_isolation ON gerti.audit_log
  USING (tenant_id IS NULL OR tenant_id = current_setting('app.current_tenant', true)::uuid);

-- Role admin bypass para jobs administrativos cross-tenant (Celery beat etc.)
CREATE ROLE gerti_admin NOLOGIN BYPASSRLS;
```

### 4.3 Diferenciadores vs Tiflux mapeados no schema

| Diferenciador | Implementação |
|---|---|
| Horas acumulam entre ciclos (opcional) | `contract.accumulate_balance_between_cycles` |
| Reajuste automático por índice | `contract_adjustment_rule` + Celery beat |
| Renovação automática com aviso | `contract_renewal_policy` + alerta `notice_days` |
| Vínculo CMDB ↔ contrato | `contract_scope_ci` |
| Ciclo billing ≠ closing nativo | `billing_period_months` + `closing_period_months` |
| Quarteirização | `contract_billing_party` |
| White-label por cliente final | `tenant.subdomain` + `tenant_branding` |
| Imutabilidade de consumo | `consumption_event` append-only + glosa |
| Idempotência de webhook | `webhook_event_id UNIQUE` |
| Snapshot de preço | `unit_price_at_event` |
| Audit log com hash chain | `audit_log.prev_hash` + `record_hash` |

## 5. Contratos de integração (APIs)

### 5.1 API pública do Sidecar (OpenAPI 3.1)

Base: `https://api.gerti.com.br/v1/` ou `https://<tenant>.suporte.gerti.com.br/api/v1/`.

#### 5.1.1 Recursos e operações

```
TICKETS
  POST   /v1/tickets                              criar ticket via portal
  GET    /v1/tickets?contract_id&status&cursor    listar (filtros + paginação cursor)
  GET    /v1/tickets/{id}                         detalhe (Znuny + Sidecar mesclado)
  POST   /v1/tickets/{id}/approve-billing         cliente aprova p/ faturamento
  POST   /v1/tickets/{id}/dispute                 cliente abre glosa
  POST   /v1/tickets/{id}/attachments             anexar (presigned MinIO)

CONTRATOS
  GET    /v1/contracts?tenant_id&status&cursor    listar contratos
  POST   /v1/contracts                            criar
  GET    /v1/contracts/{id}                       detalhe + saldo
  PATCH  /v1/contracts/{id}                       alterar (admin Gerti)
  GET    /v1/contracts/{id}/consumption?cursor    histórico consumo
  POST   /v1/contracts/{id}/cycles/{cid}/close    fechamento manual (admin)
  POST   /v1/contracts/{id}/adjustment            reajuste imediato (admin)
  POST   /v1/contracts/{id}/renewal               renovar (admin)

CATÁLOGO
  GET    /v1/catalog/services?tenant_id           catálogo visível
  POST   /v1/catalog/services                     CRUD (admin)
  GET    /v1/catalog/services/{id}                detalhe + form_schema

DASHBOARDS
  GET    /v1/dashboards/executive                 KPIs do tenant logado
  GET    /v1/dashboards/contract/{id}             consumo + SLA + ciclos
  GET    /v1/dashboards/sla?period                cumprimento SLA agregado

TENANTS / BRANDING
  POST   /v1/tenants                              criar tenant (admin Gerti)
  GET    /v1/tenants/{id}                         detalhe
  PATCH  /v1/tenants/{id}/branding                white-label
  POST   /v1/tenants/{id}/users                   convidar customer user

UPLOADS
  POST   /v1/uploads/presign                      presigned URL MinIO
  POST   /v1/uploads/{id}/finalize                enfileirar scan ClamAV

USER / LGPD
  GET    /v1/me                                   user info
  POST   /v1/me/data-export                       requisição LGPD export
  POST   /v1/me/erasure-request                   requisição LGPD anonimização

WEBHOOKS IN (Znuny → Sidecar)
  POST   /v1/webhooks/znuny/ticket.created
  POST   /v1/webhooks/znuny/article.created
  POST   /v1/webhooks/znuny/ticket.field_changed
  POST   /v1/webhooks/znuny/ticket.state_changed
  POST   /v1/webhooks/znuny/ci.created
```

#### 5.1.2 Padrões transversais

- **Autenticação**: OAuth2 Bearer JWT (RS256) emitido pelo Auth Bridge. PKCE obrigatório no Authorization Code flow
- **Idempotência**: header `Idempotency-Key` obrigatório em POSTs sensíveis. Servidor retorna mesmo resultado para 24h
- **Paginação**: cursor-based (`?cursor=opaque&limit=50`); `Link: <...>; rel="next"` no header
- **Filtros**: `?field[op]=value` (ops: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`)
- **Erros**: RFC 7807 (`application/problem+json`) com `type`, `title`, `status`, `detail`, `instance`, e campos custom `code`, `tenant_id`
- **Versionamento**: prefixo `/v1/`. Breaking → `/v2/`. Sunset com header e changelog
- **Tenant scoping**: nunca em body. Sempre via subdomínio ou claim do JWT (`tenant_id`)
- **CORS**: por tenant via `tenant_branding.allowed_origins[]`
- **Rate limit**: token bucket por `tenant_id` + global
- **Tracing**: `traceparent` propagado em todas as chamadas internas

#### 5.1.3 Exemplo de payload — POST `/v1/tickets`

```json
// Request
{
  "service_id": "9a8c...uuid",
  "subject": "Não consigo imprimir no setor financeiro",
  "description": "Impressora HP_FIN_03 está com erro 0x803...",
  "priority": 3,
  "fields": { "ci_id": 4012, "urgency": "medium" },
  "attachments": ["upl_01HXY..."]
}

// 201 Response
{
  "id": "tkt_01HXYZ...",
  "ticket_number": "2026000123",
  "znuny_ticket_id": 12345,
  "tenant_id": "tnt_...",
  "contract_id": "ctr_...",
  "queue": "Acme::Suporte::N2",
  "sla_eta": "2026-05-12T18:00:00Z",
  "status": "new",
  "created_at": "2026-05-12T15:00:00Z"
}
```

### 5.2 Sidecar → Znuny via Generic Interface

Webservice configurado no Znuny: `gerti-bridge`. Ops principais:

| Op | Uso |
|---|---|
| `TicketCreate` | criar ticket disparado pelo Portal |
| `TicketUpdate` | mudar estado, dynamic fields, owner |
| `TicketGet` | leitura sob demanda (alternativa às views) |
| `ArticleCreate` | publicar resposta do cliente |
| `SessionCreate` | criar sessão Znuny a partir de token OIDC validado |

Auth: token estático em Vault → header `OTRS_AccessToken`. TLS obrigatório. mTLS opcional em ADR-016 futuro.

### 5.3 Znuny → Sidecar via webhooks HMAC

#### 5.3.1 Eventos subscritos no `.opm`

| Evento Znuny | Endpoint sidecar |
|---|---|
| `TicketCreate` | `POST /v1/webhooks/znuny/ticket.created` |
| `ArticleCreate` (com `TimeUnit`) | `POST /v1/webhooks/znuny/article.created` |
| `TicketDynamicFieldUpdate` | `POST /v1/webhooks/znuny/ticket.field_changed` |
| `TicketStateUpdate` | `POST /v1/webhooks/znuny/ticket.state_changed` |
| `ConfigItemCreate` (ITSM) | `POST /v1/webhooks/znuny/ci.created` |

#### 5.3.2 Garantias

- **HMAC-SHA256**: `X-Gerti-Signature: sha256=<hex>` computado sobre o body com secret do Vault
- **Idempotência**: `X-Gerti-Event-Id: <UUID>`. Sidecar grava em `consumption_event.webhook_event_id` (UNIQUE)
- **Retry**: backoff 1s → 5s → 30s → 5min → 30min → DLQ no filesystem do `.opm`. Job admin re-publica
- **Ordering**: não garantido. `occurred_at` no payload + reordenação na escrita se necessário

#### 5.3.3 Payload exemplo — `article.created`

```json
{
  "event_id": "evt_01HXY...",
  "event_type": "article.created",
  "occurred_at": "2026-05-12T14:23:11Z",
  "znuny_instance": "main",
  "schema_version": 1,
  "data": {
    "ticket_id": 12345,
    "article_id": 67890,
    "time_unit_minutes": 30,
    "customer_id": "acme",
    "queue_name": "Acme::Suporte::N2",
    "agent_login": "tec.silva",
    "is_internal": true,
    "is_billable": true,
    "subject": "Atendimento remoto",
    "body_preview": "Reset de senha AD..."
  }
}
```

### 5.4 Auth Bridge (OIDC ↔ Znuny)

```
GET  /oidc/.well-known/openid-configuration
GET  /oidc/jwks.json
GET  /oidc/authorize       → tela login renderizada pelo Portal (SPA)
POST /oidc/token           → code → access_token + refresh_token + id_token
GET  /oidc/userinfo        → reflete claims do JWT
POST /oidc/revoke
POST /oidc/logout
```

JWT claims:
```json
{
  "iss": "https://auth.gerti.com.br",
  "sub": "znuny:customer_user:joao.silva@acme.com",
  "aud": "gerti-portal",
  "tenant_id": "tnt_01HXY...",
  "roles": ["customer_user"],
  "customer_id": "acme",
  "exp": 1747059300,
  "iat": 1747058400
}
```

Access token: RS256, 15 min. Refresh token: opaco, rotação a cada uso, 8h.

### 5.5 Convenções gerais

- Tempo: UTC ISO 8601 em todos os contratos. Frontend converte `America/Sao_Paulo`
- IDs sidecar: UUIDv7 (ordenável temporalmente)
- IDs Znuny: inteiros, segregados como `znuny_ticket_id`
- Logs estruturados JSON com `tenant_id` em todo span/log

## 6. Multi-tenancy e isolamento

### 6.1 Modo Pool (default)

Compartilha Znuny, sidecar, portal. Isolamento:

| Camada | Mecanismo |
|---|---|
| Znuny | `customer_company` por tenant, grupos de queues, ACLs |
| Sidecar (linhas) | `tenant_id` em todas tabelas; RLS Postgres com `app.current_tenant` |
| Storage MinIO | chave `tenant/{tenant_id}/...`; presigned URLs limitadas |
| Portal | subdomínio resolve `tenant_id`; branding e CORS por tenant |
| OIDC | JWT carrega `tenant_id`; rejeitado se ≠ subdomínio |
| Observabilidade | `tenant_id` como label (cardinalidade controlada) |

Middleware FastAPI:

```python
@app.middleware("http")
async def set_tenant(request, call_next):
    tenant = resolve_tenant(request)  # via subdomain ou JWT
    async with get_db_session(request) as session:
        await session.execute(
            text("SET LOCAL app.current_tenant = :tid"),
            {"tid": str(tenant.id)},
        )
        request.state.tenant = tenant
        return await call_next(request)
```

### 6.2 Modo Dedicado

Cliente grande/regulado recebe:
- Stack Znuny própria (containers próprios em VM dedicada)
- Schema `znuny` próprio (cluster DB pode ser compartilhado ou não)
- Bucket MinIO dedicado ou path totalmente segregado
- Email com domínio próprio (`@suporte.acme.com`)

Sidecar comum opera múltiplas instâncias via `gerti.znuny_instance`. Repository é parametrizado.

### 6.3 Onboarding de tenant

```
Admin Gerti em Portal Admin → POST /v1/tenants
   1. INSERT gerti.tenant
   2. via Generic Interface: cria customer_company, queue tree, dynamic fields no Znuny
   3. cria tenant_branding default
   4. provisiona DNS *.suporte.gerti.com.br (Cloudflare API)
   5. emite credenciais admin tenant
   Se modo dedicado:
   6. pipeline Ansible/SSH provisiona stack Compose em host alvo
   7. registra znuny_instance
```

### 6.4 Riscos de tenancy

| Risco | Mitigação |
|---|---|
| RLS desativado por engano | Teste de integração tenta ler dados de outro tenant; falha CI |
| JWT vazado dá acesso cross-tenant | `tenant_id` validado em roteamento; RLS é segunda barreira |
| Bug em resolver de subdomínio | Subdomínio é hint; autoridade é claim JWT |
| Performance degrada com volume | Particionamento `consumption_event` por mês; monitoring top tenants |
| Cliente grande satura pool | Política de migração para dedicado a partir de threshold |

## 7. Fluxos críticos

### 7.1 Abertura de ticket pelo cliente

```
Cliente Web ─→ Portal SPA ─→ Sidecar /v1/tickets ─→ Znuny GenIface
                                  │
                                  └→ MinIO presigned upload (anexo)

1. Cliente em acme.suporte.gerti.com.br (Portal SPA carregado via CDN)
2. Portal → GET /v1/me (JWT) → tenant + roles
3. Cliente escolhe serviço (GET /v1/catalog/services)
4. Preenche formulário dinâmico (form_schema)
5. Upload opcional:
   a. POST /v1/uploads/presign → URL S3 + upload_id
   b. Browser PUT direto no MinIO
   c. POST /v1/uploads/{id}/finalize → enfileira ClamAV
6. POST /v1/tickets {service_id, fields, attachments[], Idempotency-Key}
7. Sidecar:
   a. Valida JWT + tenant
   b. Localiza contrato ativo (regra: service_id ∈ contract_scope_service ou default)
   c. Resolve queue Znuny (tenant + service → queue_name)
   d. Chama Znuny POST /TicketCreate via GenIface
   e. Recebe znuny_ticket_id; INSERT gerti.ticket_contract_link
   f. Retorna {ticket_id, public_id, sla_eta}
8. Portal mostra confirmação
```

### 7.2 Apontamento de horas → consumo de contrato

```
Agente Znuny → Znuny event ArticleCreate → GertiHooks.opm → webhook → workers

1. Técnico no Agent Interface adiciona artigo interno com TimeUnit=30min
2. Znuny dispara evento "ArticleCreate"
3. GertiHooks.opm:
   a. Lê article + ticket + dynamic fields
   b. Gera event_id UUID
   c. POST https://api.gerti/v1/webhooks/znuny/article.created (HMAC)
   d. Retry com backoff em falha
4. Sidecar:
   a. Valida HMAC
   b. Verifica idempotência (webhook_event_id UNIQUE)
   c. Lê ticket_contract_link → contract_id
   d. Valida vigência do contrato no occurred_at
   e. Calcula billable_minutes e billable_amount_brl
   f. INSERT consumption_event
   g. Refresh contract_balance_current (concurrent)
   h. Se saldo < 10%: notificação aos responsáveis
   i. Retorna 200
5. Portal do cliente atualiza saldo via WebSocket /ws/dashboards
```

### 7.3 Fechamento de ciclo

```
Celery beat (cron 03:00) → worker → Postgres → notificações

1. Beat dispara closing_cycle_scan()
2. SELECT contract_cycle WHERE kind='closing' AND status='open' AND period_end < CURRENT_DATE
3. Para cada ciclo:
   a. SELECT consumption_event onde:
        closing_cycle_id IS NULL
        AND contract_id = ?
        AND occurred_at BETWEEN cycle.period_start AND cycle.period_end
        AND (glosa_id IS NULL OR glosa.status IN ('rejected','pending'))
   b. Calcula totals: consumed_minutes/brl, overage_minutes/brl,
      travel_used vs franchise, carry_over (se accumulate=true)
   c. UPDATE contract_cycle SET status='closed', closed_at=now(), totals=jsonb
   d. UPDATE consumption_event SET closing_cycle_id=?
   e. INSERT próximo contract_cycle (period_start = period_end + 1)
   f. Publica evento gerti.contract.cycle_closed (Redis pubsub)
      → Spec #2 (Faturamento) consumirá para gerar cobrança Asaas
4. Audit log de cada fechamento
5. Sumário diário aos admins Gerti
```

### 7.4 Casos de borda

| Caso | Tratamento |
|---|---|
| Cliente sem contrato ativo abre ticket | Bloqueio com mensagem; admin pode permitir ticket sem cobrança (`contract_id = NULL`) |
| Apontamento retroativo | Aceito; `occurred_at` real; alocado ao ciclo correspondente; se ciclo fechado, gera ajuste no ciclo atual com referência |
| Contrato expira durante ticket aberto | Tickets em curso continuam no contrato expirado até resolução; novos artigos checam vigência |
| Webhook após sidecar reiniciar | Retry do `.opm`; idempotência via event_id evita duplicação |
| Glosa aprovada após ciclo fechado | Reabre ciclo (status='open') e recalcula; gera reversal no Asaas (Spec #2) |
| Contrato renovado com novo preço | Novo contract row; `unit_price_at_event` preserva preço histórico em events anteriores |

## 8. Deploy e infraestrutura (Docker Compose)

### 8.1 Topologia

Stack por instância: uma `prod` compartilhada + uma adicional por tenant dedicado.

```
Cloudflare (DNS *, TLS, WAF, CDN)
  │
  ▼
Host de Produção (VM 16-32 vCPU / 64-128 GB RAM)
docker-compose.prod.yml:
  Edge:           traefik
  App:            portal-spa (nginx) | sidecar-api (×2-4) | sidecar-workers (×2-3)
                  sidecar-beat (×1) | znuny-web (×1-2) | znuny-daemon (×1)
                  auth-bridge (×1-2)
  Data:           postgres | redis | minio | opensearch | clamav
  Mail:           postfix | dovecot
  Observ:         otel-collector | loki | tempo | prometheus | grafana | alertmanager
  Security:       vault

Hosts dedicados (1 por tenant grande): docker-compose.tenant-<acme>.yml
  Stack reduzida: znuny + postgres + conector ao sidecar central
```

### 8.2 Estrutura de arquivos

```
infra/
├── compose/
│   ├── docker-compose.base.yml
│   ├── docker-compose.prod.yml
│   ├── docker-compose.staging.yml
│   ├── docker-compose.dev.yml
│   ├── docker-compose.tenant.yml.tmpl
│   └── .env.example
├── traefik/{traefik.yml,dynamic/}
├── scripts/{backup.sh,restore.sh,provision-tenant-dedicated.sh,upgrade.sh}
└── secrets/  (placeholders; reais via Vault ou sops)
```

### 8.3 Redes Docker

```yaml
networks:
  edge:    # traefik + público
  app:     # sidecar, portal, znuny
  data:    # postgres, redis, minio, opensearch
  observ:  # otel, loki, tempo, prometheus, grafana
  mail:    # postfix, dovecot
```

Cada serviço anexa só às redes que precisa.

### 8.4 Escala e disponibilidade

| Aspecto | Estratégia |
|---|---|
| Escala horizontal | `deploy.replicas: N` ou `--scale` (limitado ao host) |
| Escala vertical | dimensionamento da VM; suficiente para MVP |
| HA | aceito não ter HA real no MVP; gatilhos para migração em ADR-015 |
| Rolling upgrade | `upgrade.sh` com healthcheck por serviço |
| Failover de host | snapshot diário + restore manual em standby (RTO ~1h) |

### 8.5 Backup, DR, segurança

| Item | Implementação |
|---|---|
| Postgres | pgBackRest companion → S3 externo; WAL streaming; restore trimestral |
| MinIO | `mc mirror` agendado + versionamento bucket |
| Volumes | snapshot LVM diário do host |
| Vault | Raft em volume; chave Shamir entre 3 admins |
| Secrets em compose | `.env` produção encriptado com `sops` (KMS ou age); CI descripta |
| Firewall host | só 80/443 expostos; SSH com chaves; fail2ban |
| Imagem hardening | distroless/alpine; SBOM Syft; scan Trivy no CI |
| Logs | driver `loki` ou `fluentd` → Loki |
| LGPD | `/me/data-export` e `/me/erasure-request`; retention por categoria |
| Pentest | antes do go-live + anual |

### 8.6 CI/CD

- Build: GitHub/GitLab Actions → registry privado
- Deploy:
  - `staging`: push automático após CI verde via SSH/Watchtower
  - `prod`: manual via tag SemVer + aprovação 1 reviewer
- Migrations: Alembic no entrypoint do `sidecar-api` com advisory lock; Znuny migrations em janela

## 9. Architecture Decision Records (ADRs)

### ADR-001 — Arquitetura híbrida (Znuny core + sidecar Python)

**Status**: Accepted
**Context**: Gerti precisa estender Znuny com funcionalidades pesadas (contratos, faturamento, portal moderno). Time é PHP/Node/Python/Go, "Perl só o mínimo". Plugin `.opm` puro em Perl exigiria curva alta e UI restrita ao visual datado do Znuny.
**Decision**: Znuny inalterado + pacote `.opm` mínimo (dynamic fields + event handlers que disparam webhooks) + sidecar Python/FastAPI que carrega regras de negócio.
**Consequences (+)**: stack moderna no que mais importa; team produtivo; portal SPA desacoplado; roadmap futuro acomodado.
**Consequences (−)**: duas peças para operar; consistência eventual entre bancos (mitigada por idempotência).
**Alternatives**: plugin `.opm` puro (rejeitado por time e UI); híbrido invertido `.opm` + SPA via iframe (rejeitado por complexidade).

### ADR-002 — Banco compartilhado, schemas segregados

**Status**: Accepted
**Context**: Spec #0 escolheu Abordagem B (DB compartilhado).
**Decision**: PostgreSQL único; schemas `znuny` (gerenciado pelo Znuny) e `gerti` (gerenciado pelo sidecar). Sidecar nunca escreve em `znuny`.
**Consequences (+)**: leitura direta sem dupla escrita; backup unificado; transações cruzadas possíveis (cautela).
**Consequences (−)**: acoplamento ao schema Znuny — risco em upgrades LTS; mitigado por `znuny_repository` isolando consultas.
**Alternatives**: bancos separados (rejeitado por necessidade de leitura direta).

### ADR-003 — Sidecar lê schema znuny via repository read-only

**Status**: Accepted
**Decision**: views `gerti.v_znuny_*` ou camada Python `znuny_repository` encapsulam todas as queries de leitura. Sem `SELECT` cru espalhado.
**Consequences (+)**: ponto único para adaptar quebras de schema; testável; auditável.
**Consequences (−)**: ligeira fricção para devs (não SELECT direto), mas baixa.

### ADR-004 — Comunicação Znuny → Sidecar via webhooks HMAC

**Status**: Accepted
**Decision**: event handlers no `.opm` enviam POST autenticado por HMAC-SHA256, com `event_id` UUID para idempotência, retry exponencial e DLQ.
**Consequences (+)**: assíncrono, resiliente, simples de operar.
**Consequences (−)**: garantia "at-least-once" requer idempotência rigorosa no sidecar (atendido por `webhook_event_id UNIQUE`).
**Alternatives**: fila central (RabbitMQ) entre Znuny e sidecar (rejeitado por complexidade no MVP).

### ADR-005 — Comunicação Sidecar → Znuny via Generic Interface

**Status**: Accepted
**Decision**: webservice `gerti-bridge` no Znuny expõe operações via REST autenticadas por token; sidecar chama síncrono.
**Consequences (+)**: usa mecanismo oficial Znuny; sem hacks.
**Consequences (−)**: chamadas síncronas no caminho crítico (mitigar com timeout curto + circuit breaker).

### ADR-006 — Plugin `.opm` deliberadamente fino

**Status**: Accepted
**Decision**: `.opm` registra apenas dynamic fields, queues template, event handlers. Sem lógica de negócio.
**Consequences (+)**: estabilidade do plugin alta; pouco Perl para manter; evolução sem reinstalar pacote.
**Consequences (−)**: comportamento que precisa "viver dentro do Znuny" requer workaround (ex.: ACLs avançadas que dependam do contrato → solucionadas com dynamic field calculado).

### ADR-007 — Multi-tenancy híbrido com RLS no pool

**Status**: Accepted
**Decision**: pool default (RLS + `tenant_id`) + dedicado on-demand (stack Compose separada por tenant grande).
**Consequences (+)**: ótimo custo/benefício; trajetória clara para clientes regulados.
**Consequences (−)**: gerenciar duas modalidades requer disciplina operacional.

### ADR-008 — Auth Bridge OIDC custom (sem IdP externo)

**Status**: Accepted (revisitar em ADR-016 se complexidade crescer)
**Decision**: serviço FastAPI próprio implementa OIDC mínimo, validando contra a API de auth do Znuny e emitindo JWT RS256.
**Consequences (+)**: integração direta com base de usuários Znuny; sem dupla fonte de verdade.
**Consequences (−)**: implementar OIDC corretamente é cuidadoso; sem MFA/social nativo. Mitigação: usar libs auditadas (`authlib`).
**Alternatives**: Keycloak/Authentik externos (mais funcionalidade pronta, mais infra; postergado para ADR-016 se MFA virar requisito).

### ADR-009 — Append-only para consumption_event + idempotência

**Status**: Accepted
**Decision**: nunca `UPDATE`/`DELETE` em `consumption_event`. Correções via `glosa`. `webhook_event_id` UNIQUE para idempotência.
**Consequences (+)**: auditabilidade total; recálculo determinístico; reproduzível.
**Consequences (−)**: tabela cresce rápido; mitigar por particionamento mensal.

### ADR-010 — Acúmulo opcional de horas entre ciclos

**Status**: Accepted
**Decision**: flag `accumulate_balance_between_cycles` por contrato.
**Consequences (+)**: diferencial frente ao Tiflux (que sempre zera saldo na virada); contratos comerciais mais flexíveis.
**Consequences (−)**: cálculo de saldo mais complexo no fechamento; testes extensos.

### ADR-011 — Catálogo de serviços como recurso de primeira classe

**Status**: Accepted
**Decision**: `service_catalog_item` com `form_schema` (JSON Schema), ligado ao contrato via `contract_scope_service`. Portal renderiza dinamicamente.
**Consequences (+)**: experiência guiada para cliente final; precificação automática; Service Catalog ITIL.
**Consequences (−)**: implementar render de JSON Schema com validação cliente+servidor.

### ADR-012 — White-label por cliente final (subdomínio + branding)

**Status**: Accepted
**Decision**: cada tenant tem subdomínio próprio, logo, cores, custom CSS, CORS, SMTP opcional.
**Consequences (+)**: vai além do Tiflux (que só faz WL para a MSP); Gerti pode oferecer "portal próprio" aos clientes dela.
**Consequences (−)**: complexidade de DNS wildcard, certificados, SMTP por tenant.

### ADR-013 — Audit log append-only com hash chain + WORM S3

**Status**: Accepted
**Decision**: `gerti.audit_log` insert-only com hash chain SHA-256; sink secundário em S3 com Object Lock para período legal.
**Consequences (+)**: prova de integridade; cumprimento LGPD; rastreabilidade.
**Consequences (−)**: armazenamento adicional; cuidado em queries por volume.

### ADR-014 — Docker Compose como plataforma de deploy

**Status**: Accepted
**Context**: Gerti não tem operação K8s madura; foco em MVP em 12 semanas com infra simples.
**Decision**: Docker Compose como plataforma primária. Stack `prod` única + stacks dedicadas por tenant grande.
**Consequences (+)**: setup rápido; time entende; ops simples; dev local idêntico a prod.
**Consequences (−)**: sem HPA, sem auto-healing além de `restart`; HA real exige migração futura.
**Alternatives**: Kubernetes (rejeitado por complexidade); Docker Swarm (rejeitado por comunidade pequena); PaaS gerenciado (rejeitado por custo/lock-in).
**Migration path**: `docker-compose.yml` estruturado para tradução Kompose se HA virar requisito; ADR-015 documentará gatilhos.

### ADR-015 — Gatilhos de migração de Compose para plataforma com HA

**Status**: Proposed
**Decision**: migrar para K8s/Swarm quando ≥2 dos seguintes acontecerem:
- > 5k tickets/dia
- Requisito contratual de uptime ≥ 99.9%
- > 3 hosts em paralelo para escala horizontal
- Time atinge ≥3 engenheiros DevOps confortáveis com K8s
**Consequences**: explícito o ponto de virada — evita "migrar cedo demais".

## 10. Roadmap das specs subsequentes

| Spec | Escopo | Estimativa | Bloqueia |
|---|---|---|---|
| **#0 (esta)** | Arquitetura geral + ADRs + APIs + modelo dados contratos | 1-2 semanas | tudo |
| **#1** | GertiHooks.opm + sidecar contratos + portal cliente MVP + onboarding + OIDC | 12 semanas (6 sprints paralelos) | piloto |
| **#2** | Faturamento Asaas/NFe + ciclo cobrança + glosa cliente | 4-6 semanas | go-live comercial |
| **#3** | PWA mobile técnico em campo + apontamento offline | 6-8 semanas | field service real |
| **#4 (futuro)** | WhatsApp + IA + integrações Zabbix/PRTG/M365 | n/a | feature parity Tiflux |
| **#5 (opcional)** | Migração de dados Tiflux | n/a | descontinuar Tiflux total |

**Caminho crítico para piloto em 12 semanas** (com time expandido ~6-7 pessoas):
- Sprint 1 (sem 1-2): Plano 1A foundation, time todo
- Sprint 2 (sem 3-4): paralelos — 1B Perl OPM, 1C+1D Python, scaffold de portal
- Sprint 3 (sem 5-6): 1E APIs públicas + componentes de portal
- Sprint 4 (sem 7-8): 1F Portal MVP + 1G Onboarding
- Sprint 5 (sem 9-10): integração e2e + hardening
- Sprint 6 (sem 11-12): piloto com 1 cliente novo + buffer
- **Demos quinzenais** ao final de cada sprint para validação com stakeholders
- **Corte de escopo pré-acordado** no portal: dashboards refinados → Spec #2; dynamic forms ricos → Spec #2; catálogo básico no MVP

## 11. Riscos top-5

| # | Risco | Mitigação |
|---|---|---|
| 1 | Schema Znuny mudar entre LTS releases | Testes de contrato em `znuny_repository`; pin de versão Znuny |
| 2 | RLS impactar performance | Benchmark antecipado; índices por `tenant_id`; particionamento mensal de `consumption_event` |
| 3 | Estimativa Spec #1 estourar | Fatiar em milestones quinzenais com demo; corte de escopo pré-acordado |
| 4 | Acoplamento maior do esperado entre sidecar e Znuny | `znuny_repository` definido cedo, mantido pequeno; revisão arquitetural mensal |
| 5 | Onboarding de tenant dedicado consumir engenharia | Automar via IaC desde o primeiro caso; template Compose pronto |

## 12. Métricas de sucesso

- **Operacional**: ≥1 cliente novo na nova plataforma em 4-6 meses sem incidente crítico
- **Negócio**: custo mensal Tiflux reduzido em percentual a ser definido pelo time comercial Gerti antes do go-live (referência de mercado: assinatura de SaaS deslocada para custo de infra própria + manutenção interna; mensurar em 12 meses contra baseline atual)
- **Técnico**: cobertura sidecar ≥80%; p95 API < 300ms; uptime ≥99.5% no primeiro semestre
- **Time**: contratação Python/Vue (Nuxt) no prazo

## 13. Glossário

| Termo | Definição |
|---|---|
| Tenant | Cliente final da Gerti (empresa que recebe Service Desk) |
| Pool | Modo de tenancy compartilhado (RLS) |
| Dedicado | Modo de tenancy isolado (stack Compose própria) |
| Ciclo de faturamento | Período em que se cobra (ex.: mensal) |
| Ciclo de fechamento | Período em que se calcula excedentes (ex.: trimestral) |
| Glosa | Impugnação/abatimento de consumo pelo cliente |
| Quarteirização | Cobrar CNPJ diferente do que recebeu o serviço |
| GertiHooks | Pacote `.opm` Gerti com event handlers para webhook |
| Sidecar | Serviço Python/FastAPI que carrega a lógica de negócio |
| Auth Bridge | OIDC provider custom que valida contra Znuny |

## 14. Pontos abertos (a tratar em Spec #1)

1. Cardinalidade exata do `tenant_id` em métricas — pode estourar séries no Prometheus se muitos tenants ativos; estratégia de agregação ou exemplar-based.
2. Modelo de glosa parcial (% do valor) vs anulação total — manter total no MVP.
3. Detalhamento UX do portal — telas, fluxos, microcopy.
4. Política de retenção de anexos LGPD — definir prazo por categoria.
5. Estratégia de tratamento de feriados em SLA — usar `Calendar` do Znuny.

---

**Próximo passo**: revisão do usuário → ajustes → Spec #1 via skill `superpowers:writing-plans`.
