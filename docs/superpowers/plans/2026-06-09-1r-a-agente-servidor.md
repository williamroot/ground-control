# #1R-a — Servidor do agente de inventário Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. Steps usam checkbox (`- [ ]`). Spec: `docs/superpowers/specs/2026-06-09-1r-agente-inventario-design.md`.

**Goal:** lado servidor do auto-registro de equipamentos no CMDB — tokens de enrollment por tenant, endpoints `enroll`/`heartbeat`, op GI de escrita `ConfigItemUpsert`, e UI no console para o operador instalar/listar/aprovar/revogar/rotacionar. Garante que o ativo só entra no cliente certo.

**Architecture:** modelos `agent_enroll_token`+`device_agent` (RLS); router `/v1/agent/*` (tenant via token, fora do middleware de subdomínio); GI `ConfigItemUpsert` escopada por `CustomerID` (anti-IDOR); console por tenant. Credenciais (enroll token, agent secret) guardadas **só como sha256** (constant-time).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic (RLS), Znuny GI Perl (`Custom/`), Nuxt 3, pytest, vitest.

**Predecessor de migration:** `down_revision = "0018_automation"`.

---

### Task 1: Models `AgentEnrollToken` + `DeviceAgent` + migration `0019`

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/agent_inventory.py`
- Modify: `models/__init__.py`
- Create: `apps/sidecar/alembic/versions/0019_agent_inventory.py`
- Test: `apps/sidecar/tests/test_model_agent_inventory.py`

- [ ] **Step 1: Teste falhando** — RLS por tenant em ambas; `UNIQUE(tenant_id, fingerprint)` em `device_agent`; `UNIQUE token_hash`; CHECK status `pending|active|revoked`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Models** (schema `gerti`, espelha `models/csat.py`/`models/automation.py`):
  - `AgentEnrollToken`: `id uuid pk`, `tenant_id uuid FK tenant`, `token_hash str UNIQUE`, `label str`, `expires_at tz NULL`, `max_registrations int NULL`, `registration_count int default 0`, `enabled bool default true`, `created_at`.
  - `DeviceAgent`: `id uuid pk`, `tenant_id uuid FK`, `fingerprint str`, `agent_secret_hash str`, `status str` (CHECK), `znuny_config_item_id int NULL`, `hostname str`, `os str NULL`, `specs JSONB` (`server_default '{}'`), `last_seen_at tz NULL`, `enrolled_at tz`, `created_at`, `updated_at`. `UniqueConstraint(tenant_id, fingerprint)`.
  - Migration `0019_agent_inventory` (`down_revision="0018_automation"`): cria as 2 tabelas + **FORCE RLS + policy por tenant_id + GRANT `gerti_app`** (padrão de `0007`/`0015`/`0018`).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): models agent_enroll_token/device_agent + migration 0019 (RLS)`.

---

### Task 2: Helpers de token (hash sha256 constant-time)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/agent_secrets.py`
- Test: `apps/sidecar/tests/test_agent_secrets.py`

- [ ] **Step 1: Teste falhando** — `new_enroll_token()` → `('gcat_<rand>', '<sha256hex>')`; `new_agent_secret()` → `('gca_<rand>', hash)`; `hash_token(t)` determinístico; `verify(presented, stored_hash)` usa `hmac.compare_digest`, False se vazio.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** `secrets.token_urlsafe(32)` com prefixo; `hash_token = sha256(t.encode()).hexdigest()`; `verify` constant-time. Nenhum plaintext persistido.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): helpers de token/secret (sha256, constant-time)`.

---

### Task 3: GI `ConfigItemUpsert.pm` (escrita no CMDB, anti-IDOR) + cliente

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/ConfigItemUpsert.pm`
- Modify: `znuny/webservices/GertiTicket.yml` (op + rota `/ConfigItem/Upsert`)
- Modify: `znuny/Dockerfile` (**COPY do .pm + nome no loop `perl -c`** — lição #1O/#1Q)
- Modify: `znuny/scripts/ensure-cmdb-fields.pl` (garantir campo `Fingerprint` na classe Computer, idempotente)
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (`config_item_upsert(...)`)
- Test: `apps/sidecar/tests/test_config_item_upsert_client.py`

- [ ] **Step 1: Teste falhando (cliente)** — mock GI: `config_item_upsert(customer_id, name, specs, config_item_id=None)` monta payload `/ConfigItem/Upsert` e retorna `(config_item_id, action)`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3a: Perl** — `ConfigItemUpsert.pm` (esqueleto = `ConfigItemGet.pm`): `_CheckAccessToken` (`GertiAdmin::AccessToken`); `CustomerCompany` obrigatório; resolve ClassID/DeplStateID/InciStateID por nome; **update** se `ConfigItemID` (valida `CustomerID==CustomerCompany` → senão `NotFound`); **create** senão (`ConfigItemAdd`+`VersionAdd`, XMLData `[undef,{Version=>[undef,{<Key>=>[undef,{Content=>$v}]}]}]`); retorna `{ConfigItemID, VersionID, Number, Action}`.
- [ ] **Step 3b: YAML** + rota; **Dockerfile** COPY + loop; `ensure-cmdb-fields.pl` adiciona `Fingerprint` (string) à Computer se faltar.
- [ ] **Step 3c: Cliente** — `config_item_upsert(*, customer_id, name, depl_state="Production", inci_state="Operational", fingerprint, attributes, config_item_id=None)` via `_post("/ConfigItem/Upsert", …)`.
- [ ] **Step 4: Rodar** → PASS; `perl -c` (gate no build). **Commit:** `feat(#1R-a): GI ConfigItemUpsert (escrita anti-IDOR) + campo Fingerprint`.

---

### Task 4: Domain `AgentEnrollService` (enroll + guardrails + heartbeat)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/agent_enroll_service.py`
- Modify: `domain/errors.py` (`EnrollError`, `EnrollTokenInvalid`, `AgentRevoked`)
- Test: `apps/sidecar/tests/test_agent_enroll_service.py`

- [ ] **Step 1: Testes falhando** —
  1. `enroll(token, fingerprint, hostname, specs)`: token válido + sob limite → device `active`, chama `config_item_upsert` (mock), `registration_count++`, retorna `(device, agent_secret_plain)`.
  2. mesmo fingerprint de novo → re-enroll: rotaciona secret, mantém `config_item_id`, **não** duplica, não incrementa o contador.
  3. `max_registrations` atingido (fingerprint novo) → device `pending`, **não** chama CMDB.
  4. token inexistente/`!enabled`/expirado → `EnrollTokenInvalid`.
  5. `heartbeat(agent_secret, specs)`: device ativo → atualiza `last_seen`, re-sync CMDB se specs mudaram; `revoked` → `AgentRevoked`; secret desconhecido → `EnrollTokenInvalid`.
  6. **anti-IDOR**: o `customer_id` passado ao CMDB vem SEMPRE do tenant do token (nunca do input do agente).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Service** — `__init__(self, session, gi)`; resolve tenant→`znuny_customer_id` via join (tenant-scoped sob GUC). Usa `agent_secrets` (Task 2). Guardrails conforme spec. `pending` não escreve CMDB; `approve()` (chamado pelo router console) faz a escrita e vira `active`.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): AgentEnrollService (enroll/guardrails/heartbeat, anti-IDOR)`.

---

### Task 5: Router público `/v1/agent/*` + allowlist no middleware

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/agent.py`
- Modify: `main.py` (include_router) e `middleware/tenant.py` (allowlist `/v1/agent` — tenant vem do token, não do subdomínio)
- Test: `apps/sidecar/tests/test_agent_router.py`

- [ ] **Step 1: Testes falhando** — `POST /v1/agent/enroll` Bearer token válido → 201 `{agent_id, agent_secret, status:"active"}`; sobre limite → 202 `pending` (sem agent_secret? — retorna agent_id+secret p/ heartbeat mas status pending; CMDB vazio); token ruim → 401. `POST /v1/agent/heartbeat` Bearer secret → 200; revogado → 401. Sem subdomínio resolve (middleware allowlist).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** Router sem dependência de sessão (auth é o Bearer do agente). Extrai `Authorization: Bearer`. `AdminSessionLocal` para resolver o token cross-tenant, depois `tenant_session_scope(tenant_id)` para a escrita tenant-scoped. Mapear `EnrollTokenInvalid/AgentRevoked`→401, guardrail→202, `ZnunyUnavailable`→503. Adicionar `/v1/agent` à lista de paths que o `TenantMiddleware` pula (como `/v1/admin` e `/v1/hooks`).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): endpoints /v1/agent/enroll + /heartbeat (Bearer, fora do middleware)`.

---

### Task 6: Console — CRUD de tokens + dispositivos (API)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/admin_agents.py`
- Modify: `main.py`
- Test: `apps/sidecar/tests/test_admin_agents_router.py`

- [ ] **Step 1: Testes falhando** — `gsid_adm`: `POST /v1/admin/tenants/{id}/agent-tokens` → 201 com token **em claro uma vez** (label/expiry/max opcionais); `GET …/agent-tokens` lista (sem plaintext); `GET …/devices` lista; `POST …/devices/{id}/approve` (pending→active + CMDB) ; `POST …/devices/{id}/revoke`; sem sessão → 401; tenant inválido → 404.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** Router `Depends(get_admin_session)`, `AdminSessionLocal`+`tenant_session_scope(tid, factory=AdminSessionLocal)`. `approve` chama `AgentEnrollService.approve(device_id)`. `revoke` seta status `revoked`. Rotacionar = criar novo token + desabilitar o antigo (endpoint POST cria; PATCH/DELETE desabilita).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): API console de tokens/dispositivos do agente`.

---

### Task 7: Console — página "Agentes" (instalar/listar/aprovar/revogar)

**Files:**
- Create: `apps/admin/pages/clientes/[id]/agentes.vue`
- Create: proxies `apps/admin/server/api/admin/tenants/[id]/agent-tokens.*.ts`, `.../devices.*.ts`, `.../devices/[deviceId]/approve.post.ts`, `.../revoke.post.ts`
- Create: `apps/admin/components/agent/InstallCommand.vue`, `DeviceRow.vue`
- Modify: `apps/admin/pages/clientes/[id].vue` (link "Agentes")
- Test: `apps/admin/test/agent-install.test.ts`

- [ ] **Step 1: Teste de componente** — `InstallCommand` monta `curl <server>/install.sh | sh -s -- --enroll-token=<t> --server=<server>` e tem copy-to-clipboard; `DeviceRow` mostra status com cor **semântica** (active=success, pending=warning, offline=neutral, revoked=error — H8) e emite `approve`/`revoke`.
- [ ] **Step 2: Rodar** vitest → FAIL.
- [ ] **Step 3:** Proxies `sidecarFetch` (status passthrough). `agentes.vue`: seção "Instalar agente" (gerar token → mostra o comando 1×; rotacionar), tabela de dispositivos (status/OS/último contato/specs), ações aprovar/revogar com `useToast`. `offline` = `last_seen_at` > 2× intervalo. Componentes testáveis sem `U*`/`@nuxt/icon` (lição #1M..#1Q).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1R-a): página Agentes no console (instalar/aprovar/revogar)`.

---

### Task 8: Deploy + e2e staging + docs

**Files:**
- Modify: `.ia/INTEGRATION.md` (#1R-a), `.ia/OPS.md` (runbook), `.ia/ARCHITECTURE.md` (fluxo do agente), `.ia/DECISIONS.md` (ADR: token→tenant server-trusted; bearer hasheado vs HMAC; híbrido auto+pending).

- [ ] **Step 1:** `make test` verde + `perl -c` no .pm.
- [ ] **Step 2:** Deploy — `znuny-web` rebuild (bakeia `ConfigItemUpsert.pm`) + `--force-recreate` (entrypoint roda `ensure-cmdb-fields.pl` p/ o campo Fingerprint) + `Update --webservice-id 3`; `sidecar-migrate` (0019); rebuild+up `sidecar` e `admin`.
- [ ] **Step 3: e2e (Aurora, via curl simulando o agente):**
  1. console: `POST agent-tokens` → token em claro.
  2. `POST /v1/agent/enroll` (Bearer token, fingerprint FP1, specs) → 201 `active`; `/v1/assets` (sessão Aurora) mostra o novo ativo; TechNova **não** vê (anti-IDOR).
  3. re-enroll FP1 → mesmo `config_item_id` (sem duplicar).
  4. `POST /v1/agent/heartbeat` (Bearer agent_secret, specs novas) → 200, `last_seen` atualiza, specs no CI mudam.
  5. token com `max_registrations=1` + FP2 → device `pending` (não no CMDB) → aprovar no console → entra.
  6. revogar device → heartbeat **401**; rotacionar token → token antigo **401**.
- [ ] **Step 4:** `.ia/` status "DEPLOYADO + e2e". **Commit:** `docs(#1R-a): servidor do agente deployado + e2e`.

## Não-objetivos
O binário Go (é #1R-b), mTLS/TPM, monitoramento, exposição no portal do cliente.
