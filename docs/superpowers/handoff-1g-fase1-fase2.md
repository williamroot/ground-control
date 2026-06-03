# Handoff #1G-a — prompt para a sessão da Fase 1 + Fase 2 (end-to-end, sem perguntas)

> **Como usar:** abra uma sessão NOVA em `~/projetos/ground-control` e cole o
> bloco "PROMPT" abaixo. Todo o escopo já está decidido (Opção A, ver ADR D19);
> a sessão deve executar até o fim sem fazer mais perguntas.

Estado atual (já no ar, branch `feature/spec-1g-admin`):
- `546dd42` — Fase 0: spike R1G + ADR D19 (rascunho) + freeze de contratos/stubs
  (501) + scaffold `apps/admin/` + serviço compose `admin`. Gate verde.
- `0881141` — docs: Opção A registrada + tarefa T1.G adicionada ao plano.

---

## PROMPT (colar na sessão nova)

```
Estou em ~/projetos/ground-control, branch feature/spec-1g-admin (Fase 0 do #1G-a
já commitada e verde: 546dd42 + 0881141). Execute a Fase 1 e a Fase 2 do ciclo
#1G-a (Console de Administração) ATÉ O FIM, sem me fazer perguntas — todo o escopo
já foi decidido (Opção A: e2e completo, inclui a operação GI custom GertiAdmin).

ANTES de tudo, leia (nesta ordem):
1. docs/superpowers/plans/2026-06-02-spec-1g-admin-onboarding-plan.md  (plano, já com T1.G)
2. docs/superpowers/specs/2026-06-02-spec-1g-admin-onboarding-design.md  (spec)
3. docs/superpowers/spikes/2026-06-02-r1g-znuny-admin-gi.md  (spike R1G — contratos congelados)
4. .ia/DECISIONS.md → D14, D16, D18, D19  (auth GI, BYPASSRLS, require_admin, admin/GI custom)

Regras gerais:
- NÃO faça merge na main; trabalhe na branch feature/spec-1g-admin.
- Contratos CONGELADOS na Fase 0 — a Fase 1 só PREENCHE corpo, não muda assinaturas
  Pydantic nem de service/integração. Ninguém toca: apps/sidecar/.../main.py,
  models/__init__.py, middleware/tenant.py, apps/admin/nuxt.config.ts,
  docker-compose.yml (a Fase 0 já registrou tudo). Sem migration nova.
- Não masque defeitos: se um gate falhar, conserte de verdade.

FASE 1 — dispare os 7 agentes T1.A–T1.G EM PARALELO, numa única mensagem, cada um
no seu PRÓPRIO git worktree (isolation), respeitando a propriedade de arquivo "OWNS"
do plano (arquivos disjuntos → zero colisão). Cada agente: implementer + spec-review
+ code-review e DEIXA o gate verde antes de concluir. Depois faça merge de cada
worktree de volta na feature/spec-1g-admin (resolvendo nada além do trivial, pois os
OWNS são disjuntos).

OWNS por tarefa (resumo — detalhe no plano):
- T1.A  sidecar auth de agente + sessão admin: integrations/znuny_agent_auth.py,
        auth/admin_session.py, routers/admin_auth.py, tests/test_admin_auth.py.
        (authenticate_agent via GI SessionCreate UserLogin — failure-safe 503;
        login/logout emitindo cookie gsid_adm; testes 200/401/503 + isolamento
        cookie cliente gsid NÃO vale em /v1/admin/*.)
- T1.B  sidecar GI write-client: integrations/znuny_customer_admin.py,
        tests/test_znuny_customer_admin.py. (create_customer_company/
        create_customer_user/set_password chamando o webservice GertiAdmin; GI
        mockado nos testes; ZnunyUnavailable/ZnunyWriteError.)
- T1.C  sidecar onboarding: domain/onboarding_service.py, routers/admin_tenants.py,
        tests/test_admin_tenants.py. (POST /v1/admin/tenants orquestra GI[interface
        de T1.B, pode mockar] + gerti.tenant+branding+portal_user_role via
        AdminSessionLocal/tenant_id explícito; GET lista/detalhe; idempotência por
        znuny_customer_id/subdomínio.)
- T1.D  sidecar criar contrato: routers/admin_contracts.py, tests/test_admin_contracts.py.
        (POST /v1/admin/tenants/{id}/contracts → tenant_session_scope(id) +
        ContractService.create; 6 tipos; 404 tenant inexistente; invariante #1C.)
- T1.E  admin UI login+shell: apps/admin/pages/login.vue, middleware/admin-auth.ts,
        server/api/admin/auth/*, composables/useAdmin.ts, test/admin-auth.test.ts.
- T1.F  admin UI lista+assistente+form contrato: apps/admin/pages/index.vue,
        pages/clientes/novo.vue, pages/clientes/[id].vue,
        pages/clientes/[id]/contratos/novo.vue, server/api/admin/tenants*,
        test/admin-onboarding.test.ts.
- T1.G  Znuny GI custom (Opção A): znuny/Custom/Kernel/GenericInterface/Operation/
        CustomerCompany/CustomerCompanyAdd.pm, CustomerUser/CustomerUserAdd.pm,
        CustomerUser/SetPassword.pm, znuny/webservices/GertiAdmin.yml (+ COPY no
        znuny/Dockerfile se preciso). Embrulha a API Perl nativa; prova importando
        o YAML e chamando a operação numa instância Znuny (como o R1G fez).

CONTRATO GertiAdmin congelado (T1.B ⇄ T1.G coordenam SÓ por isto — não precisam
conversar): webservice REST provider nome "GertiAdmin", AccessToken (mesmo esquema
do webservice de auth, D14). RouteOperationMapping:
  CustomerCompanyAdd      → POST /CustomerCompany       (Type CustomerCompany::CustomerCompanyAdd)
  CustomerUserAdd         → POST /CustomerUser          (Type CustomerUser::CustomerUserAdd)
  CustomerUserSetPassword → POST /CustomerUser/Password (Type CustomerUser::SetPassword)
O sidecar chama POST {base_url}/nph-genericinterface.pl/Webservice/GertiAdmin/<Route>.
URL/token do write-client por env nova ZNUNY_ADMIN_WS_URL (+ reusa ZNUNY_WS_TOKEN);
T1.B lê via os.environ como o znuny_gi.py faz; a Fase 2 injeta no compose (default
vazio, NUNCA :? — footgun D13).

Gates (cada agente roda o seu antes de concluir):
- Sidecar: cd apps/sidecar && DATABASE_URL="postgresql+asyncpg://u:p@localhost/db" \
  uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q
  (DATABASE_URL dummy é necessário no import por causa do `app = create_app()` no
  topo do main.py; o pytest usa testcontainers → precisa de Docker.)
- Admin UI: cd apps/admin && pnpm install && pnpm exec nuxt prepare && pnpm lint &&
  pnpm test:run  (em cada worktree; node_modules não é compartilhado).
- T1.G: importar znuny/webservices/GertiAdmin.yml numa instância e exercer a operação.

Acesso ao Znuny vivo (para T1.G / e2e): `ssh gc '<cmd>'` (jump via node postgres —
ver .ia/OPS.md). Stack viva: postgres/znuny-web/znuny-daemon. Agente p/ teste:
login `william` / senha `Gerti@Demo2026` (admin; .ia/DEMO.md).

FASE 2 (sozinho, após a Fase 1 mergear):
- Remova os 501 remanescentes; ligue UI↔API ponta-a-ponta.
- e2e: onboarding de "Acme" → login do novo admin no PORTAL (apps/portal) → enxerga
  o contrato criado. Prove isolamento admin×cliente (cookie gsid não acessa
  /v1/admin/*, e vice-versa).
- Gates completos (sidecar + admin UI) verdes.
- Reviews finais: code-review + security/authz (sessão admin cross-tenant é
  superfície sensível — verifique BYPASSRLS só em /v1/admin/*, claim typ:admin,
  segredos não logados).
- Deploy: build+up do serviço `admin` (profile gerti) + import do webservice
  GertiAdmin no Znuny + subdomínio Cloudflare gerti.was.dev.br (MANUAL,
  read-modify-write estilo D4/D15 — NUNCA PUT hand-written; afirme znuny-dev/
  api-dev intactos). Verificação live.
- Docs: finalize ADR D19 (status final + evidência de gate/e2e), .ia/INTEGRATION.md
  (linhas #1G), README, e atualize o .txt/PDF de acessos (~/Documents/
  WAS-Portal-Cliente-Documentacao.pdf) com o endereço do console admin.

Use as skills: superpowers:using-git-worktrees, superpowers:dispatching-parallel-agents
(ou subagent-driven-development), superpowers:test-driven-development,
superpowers:requesting-code-review, superpowers:verification-before-completion,
superpowers:finishing-a-development-branch. No fim, me mostre: o que cada agente
entregou, os gates verdes, o resultado do e2e e do deploy.
```

---

## Notas de risco / gotchas (para quem orquestrar)
- **DATABASE_URL no import:** `apps/sidecar/.../main.py` faz `app = create_app()` no
  nível de módulo → qualquer `pytest`/import de `create_app` exige `DATABASE_URL`
  setado (DSN dummy basta; o testcontainer fornece o DB real). Sem isso a coleta
  do pytest falha na hora.
- **pytest = Docker:** o conftest sobe um Postgres via testcontainers. 7 worktrees
  rodando pytest em paralelo sobem vários containers — ok, mas pesado; se faltar
  recurso, serialize os gates de sidecar.
- **Admin UI por worktree:** cada worktree precisa do seu `pnpm install` +
  `nuxt prepare` (eslint/tsconfig dependem do `.nuxt` gerado).
- **`.pyc` versionados:** o repo tem `__pycache__/*.pyc` rastreados (dívida pré-
  existente). Ao commitar, adicione só os arquivos-fonte (evite o churn de `.pyc`).
- **Cross-tenant:** TenantMiddleware JÁ pula `/v1/admin/*` (Fase 0) — não mexer.
- **Sem migration nova** no #1G-a (admins = agentes Znuny; tenant/branding/role já
  existem). Se algum agente "precisar" de tabela, é sinal de divergência — pare.
