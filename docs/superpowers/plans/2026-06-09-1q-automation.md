# #1Q — Motor de automação próprio no sidecar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`. Steps usam checkbox (`- [ ]`).

**Goal:** automação no-code de escalonamento/triagem: o operador define **regras** (gatilho de evento + condições + ações) numa UI no console; o sidecar ingere eventos de ticket do Znuny (webhook assinado), avalia as regras do tenant e executa ações via GI (mover fila, mudar prioridade/estado, adicionar nota, notificar, acionar IA #1N). Motor **próprio** no sidecar (não GenericAgent).

**Architecture:** Znuny dispara um **Invoker GI** em eventos de ticket → `POST /v1/hooks/znuny/ticket-event` (HMAC, segredo de `ZnunyInstance.webhook_signing_secret_ref`). O `AutomationEngine` resolve o tenant pelo `CustomerID`, carrega `automation_rule` (RLS), avalia condições com um **avaliador puro** (DSL field/op/value — sem `eval`), executa ações (allowlist) via GI, e registra `automation_run`. UI no-code no console (linhas de condição/ação com dropdowns).

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic (RLS), Znuny GI Invoker (Perl/YAML), HMAC, Nuxt 3, pytest, vitest.

**Predecessor de migration:** `down_revision = "0017_invoice"`.

> **Pontos a verificar (roadmap §4):** nomes exatos dos eventos na 7.2.3 (`TicketCreate`, `ArticleCreate`, `TicketStateUpdate`, `Escalation<Type>TimeStart`) e que o Invoker GI consegue postar a payload necessária. Validar no spike antes da Task 1.

---

### Task 0 (spike, gated): Invoker GI do Znuny posta evento de ticket

**Files:** `docs/superpowers/spikes/2026-06-09-r1q-znuny-invoker.md`

- [ ] Provar num Znuny de teste: um webservice GI tipo **Invoker** (HTTP::REST) que dispara em `TicketCreate`/`ArticleCreate` e faz `POST` para um endpoint capturando `TicketID`, `CustomerID`, evento, e campos (estado/prioridade/fila/serviço/título). Confirmar como assinar (HMAC via header) — se o Invoker nativo não assina, usar um **Event module** Perl no `Custom/` que monta a payload + assinatura e faz o POST. Congelar o snippet (YAML do webservice + .pm do mapping/event). **Sem isso, as Tasks 1–2 ficam bloqueadas.**

---

### Task 1: Models `AutomationRule` + `AutomationRun` + migration `0018`

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/models/automation.py`
- Create: `apps/sidecar/alembic/versions/0018_automation.py`
- Test: `apps/sidecar/tests/test_model_automation.py`

- [ ] **Step 1: Teste falhando** — RLS por tenant em ambas; FK `automation_run.rule_id`→`rule`; CHECK em `trigger_event`.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3: Models** (schema `gerti`):
  - `AutomationRule`: `id uuid`, `tenant_id uuid FK`, `name str`, `enabled bool default true`, `trigger_event str` (CHECK in `ticket_create|article_create|state_update|escalation`), `conditions JSONB` (lista `[{field, op, value}]`), `actions JSONB` (lista `[{type, params}]`), `position int` (ordem de avaliação), `created_at`, `updated_at`.
  - `AutomationRun`: `id uuid`, `tenant_id uuid FK`, `rule_id uuid FK`, `znuny_ticket_id int`, `event str`, `matched bool`, `actions_result JSONB`, `error str | None`, `created_at`.
  - Migration: tabelas + **FORCE RLS + policy** por `tenant_id` (padrão das demais), GRANT app.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1Q): models automation_rule/run + migration 0018 (RLS)`.

---

### Task 2: Avaliador de condições puro (DSL field/op/value)

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/automation_eval.py`
- Test: `apps/sidecar/tests/test_automation_eval.py`

- [ ] **Step 1: Teste falhando** — `evaluate(conditions, facts)` (AND de todas): ops `eq, ne, contains, not_contains, gt, lt, in, not_in`; campos permitidos `priority, queue, state, type, service, customer_id, title, age_minutes, sla_state`; campo desconhecido → `False` (fail-safe, nunca exceção); tipos coeridos com segurança (numérico p/ gt/lt). Sem `eval`/`exec`.

```python
def test_eval_and_semantics():
    facts = {"priority": "5 very high", "title": "Servidor fora do ar", "age_minutes": 120}
    assert evaluate([{"field":"priority","op":"contains","value":"high"},
                     {"field":"age_minutes","op":"gt","value":60}], facts) is True
    assert evaluate([{"field":"queue","op":"eq","value":"Suporte"}], facts) is False  # campo ausente
    assert evaluate([{"field":"__danger__","op":"eq","value":"x"}], facts) is False    # campo não-permitido
```

- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** `ALLOWED_FIELDS` (set), `OPS` (dict de funções puras). `evaluate(conditions, facts)`: `all(_test(c, facts) for c in conditions)`; `_test` ignora campo fora da allowlist (`return False`), aplica op com try/except → `False`. Coerção numérica só p/ `gt/lt/age_minutes`. **Nenhum** acesso dinâmico a atributos/código.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1Q): avaliador de condições puro (DSL, fail-safe, sem eval)`.

---

### Task 3: Ações via GI — `AgentTicketUpdate` + executor

**Files:**
- Create: `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/AgentTicketUpdate.pm` (set queue/state/priority/owner + add note)
- Modify: `znuny/webservices/GertiTicket.yml` (op + rota `/Agent/Ticket/Update`)
- Modify: `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py` (`agent_ticket_update(...)`, token de agente)
- Create: `apps/sidecar/src/gerti_sidecar/domain/automation_actions.py` (executor: mapeia `{type, params}` → chamada GI/IA)
- Test: `apps/sidecar/tests/test_automation_actions.py`

- [ ] **Step 1: Teste falhando** — executor com mock GI: ação `set_priority`/`set_queue`/`set_state`/`add_note` chama o `agent_ticket_update` certo; `notify` chama o canal; `ai_summarize_note` chama `AiService` (#1N) e posta nota; tipo de ação fora da allowlist → ignorada com registro; falha de uma ação não aborta as demais (coleta resultados).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3a: Perl** `AgentTicketUpdate.pm` (overlay `Custom/`, token `GertiAgent::AccessToken`): valida token + `TicketID`; aplica `Queue`/`State`/`Priority`/`Owner` se presentes (via `TicketQueueSet`/`StateSet`/`PrioritySet`); `Note` → `ArticleCreate` interno. Idempotente/seguro; nunca toca outro ticket.
- [ ] **Step 3b: YAML** + cliente `agent_ticket_update(*, ticket_id, queue=None, state=None, priority=None, note=None)`.
- [ ] **Step 3c:** `automation_actions.py` — `ACTION_HANDLERS` (allowlist): `set_priority`, `set_queue`, `set_state`, `add_note`, `notify` (e-mail via Znuny/articulo), `ai_summarize_note` (chama #1N e adiciona o resumo como nota interna). `execute(actions, ctx)` roda cada uma, captura erro por ação, retorna lista de resultados.
- [ ] **Step 4: Rodar** → PASS; `perl -c`. **Commit:** `feat(#1Q): GI AgentTicketUpdate + executor de ações (allowlist)`.

---

### Task 4: `AutomationEngine` (orquestra evento→regras→ações) + webhook HMAC

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/domain/automation_service.py`
- Create: `apps/sidecar/src/gerti_sidecar/routers/hooks.py` (`POST /v1/hooks/znuny/ticket-event`)
- Create: `apps/sidecar/src/gerti_sidecar/integrations/webhook_sig.py` (verificação HMAC constant-time)
- Modify: `main.py` (incluir router; middleware **não** exige tenant para `/v1/hooks/*` — adicionar à allowlist do `TenantMiddleware`, como `/v1/admin`)
- Test: `apps/sidecar/tests/test_automation_engine.py`, `tests/test_hooks_router.py`

- [ ] **Step 1: Testes falhando** —
  - `webhook_sig`: assinatura válida passa; corpo adulterado falha; `hmac.compare_digest`.
  - Engine: dado um evento (`customer_id`, ticket facts) e 2 regras (1 casa, 1 não), executa só as ações da que casou, grava `automation_run` (matched true/false), e nunca cruza tenant.
  - Router: assinatura inválida → 401; tenant não resolvido pelo `customer_id` → 202 (aceita e ignora, não vaza); ok → 200 e enfileira/processa.
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:**
  - `webhook_sig.verify(secret, body_bytes, header_sig)` (HMAC-SHA256, constant-time).
  - `hooks.py`: lê raw body, verifica assinatura (segredo do `ZnunyInstance` via `AdminSessionLocal`), parseia evento, resolve `tenant` por `CustomerID` (BYPASSRLS lookup), e chama `AutomationEngine.handle(tenant, event, facts)`. Sempre 200/202 rápido (processamento síncrono no MVP; assíncrono via worker é melhoria futura).
  - `automation_service.py`: `handle(tenant, event, facts)`: `tenant_session_scope(tenant.id)` carrega regras `enabled` com `trigger_event == event` ordenadas por `position`; para cada, `evaluate(conditions, facts)`; se casa, `execute(actions, ctx)`; grava `automation_run`. Erros isolados por regra (uma regra ruim não derruba as outras).
  - `TenantMiddleware`: adicionar `/v1/hooks` à lista que pula resolução por subdomínio (o tenant vem do `CustomerID` assinado).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1Q): AutomationEngine + webhook HMAC de eventos Znuny`.

---

### Task 5: CRUD de regras (console) — API

**Files:**
- Create: `apps/sidecar/src/gerti_sidecar/routers/admin_automation.py` (`GET/POST/PUT/DELETE /v1/admin/tenants/{id}/automation-rules`)
- Modify: `main.py`
- Test: `apps/sidecar/tests/test_admin_automation_router.py`

- [ ] **Step 1: Testes falhando** — `gsid_adm`: criar regra (valida `trigger_event`, condições/ações contra as allowlists → 422 se inválida), listar por tenant, editar, habilitar/desabilitar, deletar; sem sessão → 401; tenant inválido → 404. **Validação server-side** das ações/condições (não confiar na UI).
- [ ] **Step 2: Rodar** → FAIL.
- [ ] **Step 3:** Router (`Depends(get_admin_session)`, `AdminSessionLocal` + `tenant_session_scope(tenant_id, factory=AdminSessionLocal)`): Pydantic schemas `RuleIn` validam `field`/`op`/`type` contra `ALLOWED_FIELDS`/`OPS`/`ACTION_HANDLERS` (reusar as constantes do domínio — fonte única de verdade). CRUD direto na `automation_rule`.
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1Q): CRUD de regras de automação (console, validação server-side)`.

---

### Task 6: UI no-code de regras (console)

**Files:**
- Create: `apps/admin/server/api/admin/.../automation-rules.*.ts` (proxies CRUD)
- Create: `apps/admin/pages/automacoes/index.vue` (lista por tenant) e `apps/admin/pages/automacoes/[ruleId].vue` (editor)
- Create: `apps/admin/components/automation/ConditionRow.vue`, `ActionRow.vue`
- Modify: `apps/admin/layouts/default.vue` (nav “Automações”)
- Test: `apps/admin/test/automation-editor.test.ts`

- [ ] **Step 1: Teste de componente** — `ConditionRow` emite `{field, op, value}` a partir de dropdowns; `ActionRow` idem `{type, params}`; editor monta o payload e bloqueia salvar se inválido.
- [ ] **Step 2: Rodar** vitest → FAIL.
- [ ] **Step 3:** Proxies CRUD; `automacoes/index.vue`: seletor de tenant + `UTable` de regras (nome, gatilho, enabled toggle). Editor: nome, `USelect` de `trigger_event`, lista dinâmica de `ConditionRow` (add/remove), lista de `ActionRow`, salvar. Dropdowns alimentados por metadados (`ALLOWED_FIELDS`/`OPS`/ações) servidos por um `GET /v1/admin/automation/meta`. **H8** nas cores; sem auto-aplicar (só salva a regra; execução é no evento real).
- [ ] **Step 4: Rodar** → PASS. **Commit:** `feat(#1Q): UI no-code de regras de automação (console)`.

---

### Task 7: Provisionamento do Invoker no Znuny + deploy + e2e + docs

**Files:**
- Create/Modify: `znuny/webservices/GertiAutomation.yml` (ou estender GertiTicket) — webservice Invoker que dispara nos eventos e posta no sidecar; `znuny/scripts/ensure-automation-invoker.pl` (idempotente, registra/atualiza o invoker + o segredo HMAC) chamado pelo entrypoint.
- Modify: `docker-compose.yml`/env (segredo HMAC compartilhado sidecar↔Znuny — em `.env.prod`, **não commitar**).
- Modify: `.ia/ARCHITECTURE.md` (fluxo de eventos Znuny→sidecar), `.ia/INTEGRATION.md` (#1Q), `.ia/OPS.md` (runbook), `.ia/DECISIONS.md` (ADR: motor próprio vs GenericAgent; HMAC; síncrono no MVP).

- [ ] **Step 1:** `make test` verde + `perl -c` nos .pm.
- [ ] **Step 2:** Deploy — migration 0018; `Update --webservice-id 3` (AgentTicketUpdate) + registrar o webservice Invoker; rodar `ensure-automation-invoker.pl`; rebuild+up `sidecar`, `admin`. Setar o segredo HMAC nos dois lados.
- [ ] **Step 3: e2e** — console (Aurora): criar regra `trigger=article_create` + condição `title contains "urgente"` + ações `set_priority=5 very high` e `add_note`. Como cliente, criar/atualizar um ticket “urgente …” → Znuny dispara o evento → ticket tem prioridade elevada + nota; verificar `automation_run` (matched=true) e que outro tenant não foi afetado. Regra desabilitada não dispara. Assinatura inválida (curl manual) → 401.
- [ ] **Step 4:** `.ia/` status “DEPLOYADO + e2e”. **Commit:** `docs(#1Q): automação deployada em staging + e2e`.

## Não-objetivos
Processamento assíncrono/fila dedicada (MVP é síncrono no request do webhook; mover p/ worker se latência exigir), regras com OR/aninhamento (MVP é AND de condições), ações destrutivas (deletar ticket/cliente — fora da allowlist), agendamento por tempo puro (isso o GenericAgent nativo já cobre; aqui é orientado a evento), versionamento/auditoria de mudança de regra além do `created_at/updated_at`.
