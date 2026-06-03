# Plano de implementação — Spec #1G-a (Console de Administração)

Base: `docs/superpowers/specs/2026-06-02-spec-1g-admin-onboarding-design.md`.
Branch sugerida: `feature/spec-1g-admin`. Gate por tarefa: `ruff + ruff format + mypy + pytest`
(sidecar) e `vitest + eslint` (UI). Cada tarefa = implementer + spec-review + code-review.

## ⚠️ Regras para execução PARALELA (ler antes de disparar agentes)
1. **A Fase 0 NÃO é paralela.** Um único agente roda a Fase 0 inteira e dá merge ANTES de
   qualquer outra. Ela cria o spike, congela contratos (schemas), cria **stubs** e **registra
   routers/serviços** — é o que impede os agentes paralelos de colidirem.
2. **Propriedade de arquivo é exclusiva.** Cada tarefa da Fase 1 só edita os arquivos listados
   em "OWNS". Ninguém toca `main.py`, `models/__init__.py`, `nuxt.config`, `docker-compose.yml`
   na Fase 1 (a Fase 0 já fez). Arquivos compartilhados foram divididos por tarefa (routers e
   integrações GI ficam em arquivos separados de propósito).
3. **Contratos congelados na Fase 0.** Request/response Pydantic e assinaturas dos
   services/integrações são definidos como stubs na Fase 0; a Fase 1 só preenche corpo.
4. **Migrations:** #1G-a NÃO cria migration. Se o spike concluir que precisa (ex.: allowlist
   de agentes), a ÚNICA migration é criada na Fase 0.
5. Use worktrees por agente (isolation) para não pisar no working tree um do outro.

---

## FASE 0 — Fundação (SEQUENCIAL, bloqueante) — 1 agente

### T0.1 — Spike R1G (Znuny GI) + ADR
- Provar via GI: (a) `Session::SessionCreate` com `UserLogin`+`Password` → `SessionID`
  (auth de agente); (b) operações GI para criar `CustomerCompany` + `CustomerUser` + senha.
  Se (b) não existir pronto, decidir o webservice/operação a configurar e documentar.
- Entregar `docs/superpowers/spikes/2026-06-02-r1g-znuny-admin-gi.md` + ADR D19 (rascunho).
- **Congela**: endpoint do webservice + nomes das operações GI + formato de erro.

### T0.2 — Freeze de contratos + stubs + registro
- **OWNS**: `src/gerti_sidecar/main.py`, `auth/admin_session.py`,
  `routers/admin_auth.py`, `routers/admin_tenants.py`, `routers/admin_contracts.py`,
  `integrations/znuny_agent_auth.py`, `integrations/znuny_customer_admin.py`,
  `domain/onboarding_service.py`, `apps/admin/` (scaffold), `docker-compose.yml`.
- Criar **stubs** (assinaturas + modelos Pydantic request/response; corpo = `raise
  HTTPException(501)`), `get_admin_session` mínimo, e **registrar os 3 routers admin** no
  `main.py`. Cliente GI de escrita e agent-auth como interfaces (stubs que levantam
  `NotImplementedError`).
- Scaffold `apps/admin/`: `nuxt.config.ts`, layout/identidade Gerti, `server/utils/sidecar.ts`
  (cookie `gsid_adm`), `middleware/admin-auth.ts` (stub), páginas placeholder, serviço compose
  `admin` (profile `gerti`) — análogo ao portal.
- Gate verde com stubs (501) + smoke. Merge. **A partir daqui a Fase 1 paraleliza.**

---

## FASE 1 — Paralela (arquivos disjuntos) — até 6 agentes simultâneos

### T1.A — Sidecar: auth de agente + sessão admin
- **OWNS**: `integrations/znuny_agent_auth.py`, `auth/admin_session.py`,
  `routers/admin_auth.py`, testes `tests/test_admin_auth.py`.
- Implementa `authenticate_agent` (GI, failure-safe 503), `encode/decode` admin JWT,
  `get_admin_session`, `POST /v1/admin/auth/login|logout`. Testes: 200/401/503; cookie
  `gsid_adm`; isolamento (cookie `gsid` do cliente NÃO vale em `/v1/admin/*`).

### T1.B — Sidecar: GI write-client (CustomerCompany/User)
- **OWNS**: `integrations/znuny_customer_admin.py`, `tests/test_znuny_customer_admin.py`.
- Implementa `create_customer_company(...)`, `create_customer_user(...)`, `set_password(...)`
  conforme o spike. Failure-safe + erros mapeáveis. Testes com GI mockado.

### T1.C — Sidecar: onboarding de tenant
- **OWNS**: `domain/onboarding_service.py`, `routers/admin_tenants.py`,
  `tests/test_admin_tenants.py`.
- `POST /v1/admin/tenants` orquestra: GI (via interface da T1.B) + `gerti.tenant` +
  `tenant_branding` + `portal_user_role` (AdminSessionLocal, tenant_id explícito). `GET`
  lista/detalhe. Idempotência por `znuny_customer_id`/subdomínio. Testes: cria tudo;
  reexecução não duplica; valida subdomínio único.

### T1.D — Sidecar: criar contrato
- **OWNS**: `routers/admin_contracts.py`, `tests/test_admin_contracts.py`.
- `POST /v1/admin/tenants/{id}/contracts` → `tenant_session_scope(id)` +
  `ContractService.create(NewContract)`. Cobre os 6 tipos; valida campos por tipo;
  404 tenant inexistente. Testes por tipo + invariante #1C preservada.

### T1.E — Admin UI: login + shell
- **OWNS**: `apps/admin/pages/login.vue`, `apps/admin/middleware/admin-auth.ts`,
  `apps/admin/server/api/admin/auth/*`, `apps/admin/composables/useAdmin.ts`,
  `apps/admin/test/admin-auth.test.ts`.
- Login de agente → cookie `gsid_adm`; guarda de rota; layout/identidade Gerti.

### T1.F — Admin UI: lista + assistente + form de contrato
- **OWNS**: `apps/admin/pages/index.vue`, `apps/admin/pages/clientes/novo.vue`,
  `apps/admin/pages/clientes/[id].vue`, `apps/admin/pages/clientes/[id]/contratos/novo.vue`,
  `apps/admin/server/api/admin/tenants*`, `apps/admin/test/admin-onboarding.test.ts`.
- Consome os contratos congelados; o form de contrato adapta campos por tipo.

*(T1.E e T1.F compartilham só o scaffold criado na Fase 0; cada um tem páginas/arquivos
próprios — sem colisão.)*

### T1.G — Znuny: operação GI custom + webservice GertiAdmin (escopo decidido no spike R1G → Opção A, ADR D19)
- **OWNS**: `znuny/Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm`,
  `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm`,
  `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/SetPassword.pm`,
  `znuny/webservices/GertiAdmin.yml`, `znuny/Dockerfile` (só COPY do overlay, se preciso).
- Operações GI custom embrulhando a API Perl nativa (`CustomerCompanyAdd`/
  `CustomerUserAdd`/`SetPassword`), expostas pelo webservice `GertiAdmin`
  (rota REST). Espelha o contrato congelado de `znuny_customer_admin.py` (T1.B).
  Prova: importar o YAML + chamar a operação numa instância Znuny (como o R1G).
- **Disjunto de tudo** (arquivos `znuny/...` novos) → paraleliza sem colisão.
  T1.B (write-client Python) e T1.G coordenam só pelo contrato congelado no spike.

---

## FASE 2 — Integração + deploy + docs (SEQUENCIAL) — 1 agente
- Remover os 501 remanescentes; ligar UI↔API ponta-a-ponta; **e2e**: onboarding "Acme" →
  login do novo admin no portal → enxerga o contrato criado; isolamento admin×cliente.
- Gates completos (sidecar + admin UI). Reviews final code + **security/authz** (sessão
  admin cross-tenant é superfície sensível).
- Deploy: build+up do serviço `admin`, subdomínio Cloudflare (manual D4), verificação live.
- Docs: ADR D19 final, `.ia/INTEGRATION.md` (+linhas #1G), README, e atualizar o PDF/`.txt`
  de acessos com o endereço do console admin.

## Sequência de disparo (resumo)
1. **Fase 0** (1 agente, sozinho) → merge.
2. **Fase 1**: A, B, C, D, E, F em paralelo (worktrees). B é dependência lógica de C →
   C pode mockar a interface da B e integrar na Fase 2 (não bloqueia).
3. **Fase 2** (1 agente) após Fase 1.
