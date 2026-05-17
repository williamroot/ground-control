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
│   └── portal/     placeholder Vue 3/Nuxt 3 (Spec #1F — vazio)
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

- **GertiHooks.opm** (Perl mínimo, Spec #1B — *não iniciado*): dynamic
  fields (`GertiContractId`, `GertiBillableMinutes`, `GertiBillingStatus`),
  queues template e event handlers que disparam **webhooks HMAC**.
- **Znuny → sidecar:** webhook assinado (HMAC) em mudança de
  ticket/artigo → endpoint IN do sidecar → grava `gerti.consumption_event`
  (idempotência por `webhook_event_id`).
- **Sidecar → Znuny:** escrita via **Generic Interface** (REST); leitura
  do schema `znuny` read-only. Nunca SQL direto no schema Znuny.
- **Fluxo de domínio:** `contract → contract_cycle → consumption_event →
  glosa → billing` (ciclos faturamento/fechamento), materializado pelos
  workers Celery (fechamento, alertas, retry de webhook).

## (e) Construído vs pendente

| Item | Status |
|---|---|
| Plano 1A (fundação: estrutura, RLS, sidecar skeleton, testes) | **Pronto, verificado** |
| #1C Task 1 (enums de contrato + migration `0004_contract_enums`) | **Pronto, verificado** |
| #1C T2–T13 (engine de contrato: modelos, repos, ciclos, glosa) | Pendente — plano em `docs/superpowers/plans/2026-05-17-spec-1c-contract-domain.md` |
| #1B GertiHooks.opm (webhooks/dynamic fields no Znuny) | Não iniciado |
| Convergência prod p/ cluster Postgres único compartilhado | Item aberto (ver (b)) |
| Portal (Spec #1F) | Placeholder vazio |

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
