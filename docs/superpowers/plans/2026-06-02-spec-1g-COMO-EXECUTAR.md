# Como executar o #1G em paralelo (runbook para a nova sessão)

Acompanha:
- Spec: `docs/superpowers/specs/2026-06-02-spec-1g-admin-onboarding-design.md`
- Plano: `docs/superpowers/plans/2026-06-02-spec-1g-admin-onboarding-plan.md`

## Regra de ouro
**Fase 0 roda SOZINHA e dá merge ANTES de qualquer paralelismo.** Ela faz o spike
bloqueante (Znuny GI) e congela contratos + cria stubs + registra routers/serviços.
Só depois dispare a Fase 1 (6 agentes em paralelo, arquivos disjuntos). Fase 2 fecha
(integração + deploy + docs), sequencial.

Sequência: **Fase 0 (1 agente) → merge → Fase 1 (A–F paralelos) → Fase 2 (1 agente)**.

Disciplina por tarefa: implementer + spec-review + code-review; gate verde
(`ruff + ruff format + mypy + pytest` no sidecar; `vitest + eslint` no admin UI);
zero mascaramento de defeito; worktrees por agente na Fase 1 (isolation).

---

## PROMPT PARA A NOVA SESSÃO (cole isto)

> Estou no repo `~/projetos/ground-control`. Execute o ciclo **#1G-a (Console de
> Administração)** seguindo EXATAMENTE o plano já commitado em
> `docs/superpowers/plans/2026-06-02-spec-1g-admin-onboarding-plan.md` e a spec
> `docs/superpowers/specs/2026-06-02-spec-1g-admin-onboarding-design.md`. Leia os dois antes.
>
> Regras:
> 1. Crie a branch `feature/spec-1g-admin`.
> 2. **Fase 0 primeiro, sozinha** (NÃO paralelize): rode o spike R1G (auth de agente via
>    Znuny GI + criar CustomerCompany/CustomerUser via GI), documente no spike + ADR D19
>    rascunho, e implemente T0.2 (freeze de contratos Pydantic, stubs 501, `get_admin_session`
>    mínimo, registro dos 3 routers admin no `main.py`, scaffold `apps/admin/` + serviço
>    compose `admin`). Gate verde com stubs. Commit.
> 3. **Fase 1**: dispare os 6 agentes T1.A–T1.F **em paralelo, numa única mensagem**, cada um
>    em seu worktree, respeitando a propriedade de arquivo "OWNS" do plano (nenhum toca
>    `main.py`/`models/__init__`/`nuxt.config`/`docker-compose.yml`). Cada agente: implementer
>    + spec-review + code-review, gate verde. T1.C pode mockar a interface da T1.B.
> 4. **Fase 2** (sozinho): remova os 501, integre UI↔API, e2e (onboarding "Acme" → login do
>    novo admin no portal → vê o contrato), reviews final code + security/authz, deploy do
>    serviço `admin` + subdomínio Cloudflare (manual), e docs (ADR D19, INTEGRATION, README,
>    atualizar o `.txt`/PDF de acessos com o endereço do console).
>
> Pare e me mostre o resultado do spike R1G antes de implementar a Fase 1 (as 2 incógnitas de
> Znuny GI podem mudar o desenho). Não masque defeitos; se um gate falhar, conserte de verdade.

---

## Prompts por tarefa (opcional — para disparo manual fino na Fase 1)

Use só se quiser controlar agente a agente em vez de deixar o main orquestrar. Cada um:
"Implemente a tarefa **T1.X** do plano `…spec-1g-admin-onboarding-plan.md` (seção FASE 1).
Edite SOMENTE os arquivos em 'OWNS' dessa tarefa. Use os contratos Pydantic já congelados na
Fase 0. Escreva testes e deixe o gate verde. Não toque em arquivos de outras tarefas."

- **T1.A** auth de agente + sessão admin (`gsid_adm`, `get_admin_session`, login/logout).
- **T1.B** GI write-client (CustomerCompany/User + senha).
- **T1.C** onboarding de tenant (`POST /v1/admin/tenants` + list/detail).
- **T1.D** criar contrato (`POST /v1/admin/tenants/{id}/contracts`, 6 tipos).
- **T1.E** admin UI: login + shell + guarda.
- **T1.F** admin UI: lista + assistente de cliente + form de contrato.

## Checklist de sucesso (#1G-a pronto)
- [ ] Spike R1G respondido (auth de agente + customer-create via GI) + ADR D19.
- [ ] `/v1/admin/auth/login` autentica agente; `/v1/admin/*` exige sessão admin (401 sem ela);
      cookie cliente `gsid` NÃO acessa admin (e vice-versa).
- [ ] `POST /v1/admin/tenants` cria Znuny customer + tenant + branding + papéis (idempotente).
- [ ] `POST /v1/admin/tenants/{id}/contracts` cria os 6 tipos via ContractService (invariantes #1C).
- [ ] Admin UI: login + lista + assistente de cliente + form de contrato.
- [ ] Gates verdes (sidecar + admin UI); reviews code + authz APROVADAS.
- [ ] Deploy live do serviço `admin` + subdomínio; e2e "Acme" ponta-a-ponta.
- [ ] Docs atualizados (ADR D19, INTEGRATION, README, acessos).
