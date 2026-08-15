# GAP-A — Clientes e Usuários (R1, R2, R5, R7, R8, R14, R16)

> Gap analysis entre o BRIEF-KLEBER (vídeo `Recursos Administrativos - TIFLUX.webm`,
> transcrição `docs/transcricoes/2026-08-15-kleber-recursos-administrativos-tiflux.txt`)
> e o código real do monorepo em `main` (commit `50fb3c9`).
> Toda afirmação abaixo tem `arquivo:linha` como prova. Onde não achei arquivo, digo AUSENTE.

---

## R1 — Cadastro de cliente (a tela "mais importante")

**Pedido (citação curta do Kleber):** *"A primeira coisa que eu vou fazer é cadastrar o cliente
aqui. Então essa tela é uma das telas mais importantes. […] ele tem um passo a passo de cadastro
do cliente […] e ao final do cadastro do cliente, ele vai me levar pra uma telinha de edição […]
pode colocar logo, nome fantasia, os dados cadastrados da empresa, endereço, contato"*
(transcrição linhas 10–15).

**Estado atual:** **PARCIAL**

- Existe onboarding cross-tenant real: `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:199` (`POST /v1/admin/tenants`) orquestrando `apps/sidecar/src/gerti_sidecar/domain/onboarding_service.py:75` (`onboard()`)
- Lista e detalhe existem: `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:168` (`GET /v1/admin/tenants`) e `:277` (`GET /v1/admin/tenants/{tenant_id}`)
- Telas existem: `apps/admin/pages/index.vue:15` (lista, com estado vazio + CTA em `:36`), `apps/admin/pages/clientes/novo.vue:182` (formulário), `apps/admin/pages/clientes/[id]/index.vue:31` (detalhe)
- Proxies existem: `apps/admin/server/api/admin/tenants.get.ts`, `tenants.post.ts`, `tenants/[id].get.ts`
- **Não é assistente passo a passo:** o formulário é uma única página com 3 `<section>` e um único `submit` — `apps/admin/pages/clientes/novo.vue:182`, `:191`, `:214`, `:237`
- **Não existe tela de edição do cliente:** o router só tem `GET ""`, `POST ""`, `GET "/{id}"`, `POST "/{id}/users"` — não há `PUT /v1/admin/tenants/{id}` em `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:168,199,277,292`. O detalhe em `apps/admin/pages/clientes/[id]/index.vue:124` é `<dl>` read-only.
- **Não há endereço nem contato em lugar nenhum:** o modelo tem só `legal_name/trade_name/document/znuny_customer_id/znuny_instance_id/subdomain/status` — `apps/sidecar/src/gerti_sidecar/models/tenant.py:25-39`; o corpo de entrada idem — `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:61-68`
- **O Znuny também não recebe endereço:** a op GI grava apenas `CustomerID` + `CustomerCompanyName` + `ValidID` — `znuny/Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyAdd.pm:115-119` (o `customer_company` nativo tem `street/zip/city/country/url/comments`, todos ignorados)
- **Logo é URL digitada, não upload:** `apps/admin/pages/clientes/novo.vue:231` (`UInput` "URL do logo"); persistido em `tenant_branding.logo_url` — `apps/sidecar/src/gerti_sidecar/models/tenant_branding.py`
- **Abas presentes:** Agentes, Faturas, Conhecimento, Catálogo, Identidade visual, Novo contrato — `apps/admin/pages/clientes/[id]/index.vue:73-119`; Contratos listados em `:194`; Usuários listados em `:179`
- **Abas ausentes:** **Tickets do cliente** (existe `GET /v1/admin/tickets?customer_id=` em `apps/sidecar/src/gerti_sidecar/routers/admin_timer.py:170-177`, mas a tela `/atendimento` não passa `customer_id` — `apps/admin/pages/atendimento/index.vue:55` só manda `q`), **Relacionamentos/filas** (R5), **Faturamento/config** (R6, fora deste recorte)
- Rotas aninhadas do cliente já existem e o parent `<NuxtPage />` está resolvido (fix `2195613`) — `apps/admin/pages/clientes/[id]/` tem 6 filhos

**Gap (comportamento observável):**
1. O operador não consegue **corrigir** nada depois de criar: errou a razão social ou o CNPJ → não há tela nem endpoint.
2. Endereço e contato do cliente **não existem** como dado — nem em `gerti`, nem no Znuny.
3. O cadastro é um formulão único; o Kleber espera etapas com validação por etapa.
4. Logo só por URL externa (sem upload), o que na prática força o operador a hospedar o arquivo em outro lugar.
5. Não há visão dos chamados daquele cliente dentro da ficha (o backend já suporta).

**Tarefas:**

1. **T-R1.1 — Estender `gerti.tenant` com endereço e contato** — *migration + sidecar*
   Arquivos: `apps/sidecar/alembic/versions/0027_tenant_address_contact.py` (novo), `apps/sidecar/src/gerti_sidecar/models/tenant.py`
   Colunas nullable: `address_street`, `address_number`, `address_complement`, `address_district`, `address_city`, `address_state`, `address_zip`, `contact_name`, `contact_email`, `contact_phone`.
   Pronto quando: `alembic upgrade head` roda limpo, colunas são `NULL`-safe (tenants existentes não quebram), RLS/`FORCE` da tabela intacto (nenhuma policy alterada).

2. **T-R1.2 — Expor `PUT /v1/admin/tenants/{id}` (edição do cadastro)** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py`, `apps/sidecar/src/gerti_sidecar/domain/onboarding_service.py` (novo método `update_registration`)
   Regras: `subdomain` e `znuny_customer_id` são **imutáveis** (mudar quebra branding e RLS); alterar `trade_name` propaga para o Znuny via `CustomerCompanyAdd` idempotente (ou nova op `CustomerCompanyUpdate`); `audit_service.record(action="update", entity="tenant")`.
   Pronto quando: 200 com o `TenantDetail` atualizado; 404 para id desconhecido; 422 ao tentar mudar `subdomain`.

3. **T-R1.3 — Propagar endereço/contato ao Znuny (`CustomerCompanyUpdate`)** — *znuny*
   Arquivos: `znuny/Custom/Kernel/GenericInterface/Operation/CustomerCompany/CustomerCompanyUpdate.pm` (novo), `znuny/webservices/GertiAdmin.yml`, `znuny/Dockerfile` (COPY + `perl -c`), `apps/sidecar/src/gerti_sidecar/integrations/znuny_customer_admin.py`
   Pronto quando: `perl -c` passa como gate de build; a op grava `Street/Zip/City/Country` no `customer_company`; `AccessToken` fail-closed igual às irmãs (`CustomerCompanyAdd.pm:88`).

4. **T-R1.4 — Converter `/clientes/novo` em assistente de 3 etapas** — *admin*
   Arquivos: `apps/admin/pages/clientes/novo.vue`, `apps/admin/composables/useTenantWizard.ts` (novo, lógica pura de etapas/validação)
   Etapas: (1) dados cadastrais + endereço/contato, (2) identidade visual, (3) usuários. Validação por etapa; "Avançar" bloqueado com erro em português; ao final redireciona para `/clientes/{id}` (tela de edição).
   Pronto quando: não é possível avançar com etapa inválida; o corpo POST final é idêntico ao de hoje + novos campos.

5. **T-R1.5 — Tela de edição `/clientes/[id]/editar.vue`** — *admin*
   Arquivos: `apps/admin/pages/clientes/[id]/editar.vue` (novo), `apps/admin/server/api/admin/tenants/[id].put.ts` (novo), botão em `apps/admin/pages/clientes/[id]/index.vue`
   Pronto quando: loading / erro / 422 do sidecar tratados; nome do tenant visível no cabeçalho (invariante 2); campos imutáveis renderizados desabilitados com explicação.

6. **T-R1.6 — Aba "Chamados" na ficha do cliente** — *admin*
   Arquivos: `apps/admin/pages/clientes/[id]/chamados.vue` (novo), `apps/admin/server/api/admin/tenants/[id]/tickets.get.ts` (novo proxy → `GET /v1/admin/tickets?customer_id=`)
   Pronto quando: lista os chamados do `znuny_customer_id` daquele tenant, com estado vazio/erro; cabeçalho mostra o nome do cliente.

**Testes de validação:**

- **V-R1.1** (pytest, estender `apps/sidecar/tests/test_admin_tenants.py`): `PUT /v1/admin/tenants/{id}` com `{"legal_name": "Nova Razão LTDA", "address_city": "Belo Horizonte"}` → 200 e `GET /v1/admin/tenants/{id}` devolve `legal_name == "Nova Razão LTDA"` e `address_city == "Belo Horizonte"`.
- **V-R1.2** (pytest, mesmo arquivo — **negativo/imutabilidade**): `PUT` com `{"subdomain": "outro"}` → **422** e o `SELECT tenant.subdomain` permanece o original.
- **V-R1.3** (pytest, mesmo arquivo — **negativo/anti-IDOR cross-tenant**): `PUT /v1/admin/tenants/{uuid_inexistente}` → **404** (nunca 403/500); `PUT` sem cookie `gsid_adm` → **401**; `PUT` com cookie `gsid` de **cliente** → **401** (reusar o padrão de `test_admin_tenants.py:344` `test_all_endpoints_require_admin_session`).
- **V-R1.4** (pytest, novo `apps/sidecar/tests/test_migration_0027_tenant_address.py`): após `upgrade head`, `INSERT` de tenant sem nenhum campo de endereço → sucesso (colunas nullable); `information_schema.columns` contém as 10 colunas novas.
- **V-R1.5** (vitest, novo `apps/admin/test/tenant-wizard.test.ts`): `canAdvance(step=1, draft sem document)` → `false` com mensagem `'CNPJ/documento é obrigatório.'`; `canAdvance(step=1, draft completo)` → `true`; `buildTenantBody(draft)` → objeto com `address_zip` normalizado (só dígitos).
- **V-R1.6** (vitest, novo `apps/admin/test/tenant-edit-proxy.test.ts`): proxy `tenants/[id].put.ts` com id não-UUID → **404** sem chamar o sidecar (guard de path-injection, mesmo padrão de `apps/admin/test/znuny-guard.test.ts`); 422 do sidecar é repassado com o `detail` original.
- **V-R1.7** (manual/e2e Playwright, novo `apps/admin/test/e2e/cliente-editar.spec.ts`): criar cliente pelo assistente → cair em `/clientes/{id}` → clicar "Editar" → alterar cidade → recarregar → cidade persistida; nome do cliente visível no header em todas as telas.

**Risco/decisão aberta:**
- Fonte de verdade do endereço: `gerti.tenant` (nossa) **ou** `customer_company` do Znuny (nativa)? Opções: **(a)** só `gerti` (rápido, mas o agente no Znuny não vê o endereço); **(b)** só Znuny via GI (paridade total, exige `CustomerCompanyUpdate.pm` novo e leitura via GI a cada render); **(c)** `gerti` como dona + espelho best-effort no Znuny. Recomendação de leitura: **(c)** — segue o padrão já usado no branding, mas precisa da tua decisão porque cria duplicidade.
- Upload de logo exige storage (MinIO já existe em `infra/compose/` mas **não** na stack de produção). Manter URL até haver decisão de storage é aceitável.

---

## R2 — Usuário único do cliente (portal + e-mail) — **o diferencial pedido**

**Pedido (citação curta do Kleber):** *"A pessoa que tá cadastrada no portal, quando ela abre os
chamados, ele identifica os tickets que foram abertos pelo portal. Quando a pessoa manda e-mail,
os tickets que ela mandou por e-mail não vai pro portal. […] Não é melhor a gente cadastrar um
usuário único e dar acesso ao portal, deixar esse cara, todo o usuário do cliente já é
automaticamente um solicitante?"* (transcrição linhas 23–29). Campos: *"nome, e-mail, telefone e
ramal […] se o cara tá ativo ou não ativo"* (linha 31) + flag *"libera tickets por e-mail"* (linha 21).

**Estado atual:** **PARCIAL** — a *arquitetura* já é de usuário único; o *caminho de e-mail não
existe* e os campos do cadastro não existem.

O que **já está certo por construção** (é preciso dizer isto com clareza — é o alicerce do diferencial):

- Existe **um único** cadastro de pessoa do cliente: `CustomerUser` no Znuny, com `UserLogin == UserEmail` (o sidecar manda os dois iguais) — `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:311-317` e `apps/sidecar/src/gerti_sidecar/domain/onboarding_service.py:113-120`
- A op GI é idempotente por login — `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm:111-119`
- O papel do portal referencia o **mesmo** login — `apps/sidecar/src/gerti_sidecar/models/portal_user_role.py:35` (`customer_login`), unicidade por `(tenant_id, lower(customer_login))`
- A listagem do portal busca por `CustomerUserLogin` (escopo `own`) ou `CustomerID` (escopo `company`), **não** por "origem do ticket" — `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketSearch.pm:35-40`, acionado por `apps/sidecar/src/gerti_sidecar/routers/tickets.py:145-151`
- Ou seja: **se** o Znuny gravar `customer_user_id = <login> `num ticket vindo por e-mail, ele **aparece** na `/tickets` do portal sem nenhuma mudança de código. O `TicketSearch` não filtra por canal.

O que **falta**, factualmente:

- **Não há ingestão de e-mail nenhuma configurada.** Zero `MailAccount`, zero `PostMaster*` em todo o diretório `znuny/` (verificado com grep em `*.tmpl`, `*.sh`, `*.pl`, `*.pm`, `*.yml`; a única ocorrência de `PostMasterSearch` é `znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentResolveLogin.pm:93`, que resolve **agente**, não cliente). `znuny/Config.pm.tmpl` só define `AdminEmail` (`:34`) e `CheckEmailAddresses` (`:41`) — nenhum fetch de caixa.
  → **Consequência honesta: hoje o cenário do Kleber não é reproduzível nem para falhar.** Não existe "ticket aberto por e-mail" nesta stack. O diferencial está *arquiteturalmente pronto* e *operacionalmente inexistente*.
- **Ticket por e-mail nasceria sem contrato.** O vínculo `gerti.ticket_contract_link` só é criado no `POST /v1/tickets` do portal (`apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py`, chamado em `apps/sidecar/src/gerti_sidecar/routers/tickets.py:124`). O worker de billing **descarta** lançamentos de tickets sem vínculo **e avança o cursor mesmo assim** — `apps/sidecar/src/gerti_sidecar/domain/reconciliation_service.py:105-109`:
  ```python
  if lnk is None:
      # Cursor avança mesmo sobre entradas sem vínculo; um ticket linkado APÓS
      # o scan do seu lançamento perderia aquele tempo. […]
      continue  # ticket sem contrato → ignora
  ```
  → **Ligar e-mail sem resolver isto faz a Gerti perder faturamento silenciosamente** em todo chamado que entrar por e-mail.
- **Campos do cadastro ausentes:** telefone e ramal não existem no corpo de entrada (`apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:45-50` — só `email`, `first_name`, `last_name`, `password`, `role`) nem são enviados ao Znuny (`CustomerUserAdd.pm:91-101` exige apenas 5 campos; o `customer_user` nativo tem `phone`/`mobile`).
- **Ativo/inativo ausente:** o sidecar sempre cria com o default `ValidID = 1` (`CustomerUserAdd.pm:103-104`) e **não existe** endpoint de update/desativação de usuário de cliente — `apps/sidecar/src/gerti_sidecar/integrations/znuny_customer_admin.py` expõe só `create_customer_company` (`:107`), `create_customer_user` (`:124`), `set_password` (`:147`).
- **Flag "libera tickets por e-mail" ausente:** grep por `libera|email_enabled|allow_email` não retorna nada em `apps/sidecar/src` nem em `znuny/Custom`.
- **A ficha do cliente lista usuários a partir de `portal_user_role`, não do Znuny** — `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:121-131`. Um `CustomerUser` criado direto no Znuny (ou pelo PostMaster com auto-criação) **não aparece** no console.
- **Sem UI para adicionar usuário depois do onboarding:** o endpoint existe (`admin_tenants.py:292`, `POST /{tenant_id}/users`) mas **não há proxy** em `apps/admin/server/api/admin/tenants/[id]/` (diretório contém `agent-tokens`, `automation-rules`, `branding`, `catalog`, `contracts`, `devices`, `invoices`, `kb` — nenhum `users`) e nenhuma chamada em `apps/admin/pages/`.
- **Inconsistência de escopo (achado colateral, relevante porque R2 aumenta o nº de usuários):** a **lista** é `own` para papel `helpdesk` (`tickets.py:145`) mas o **detalhe** só valida a empresa — `tickets.py:174-176` passa apenas `customer_id`, e `znuny/Custom/…/GertiTicket/TicketGet.pm:42` compara só `CustomerID`. Um usuário `helpdesk` que não vê o ticket na lista **consegue abri-lo** informando o id.

**Gap (comportamento observável):**
1. Um humano cadastrado no console não tem telefone/ramal, não pode ser desativado e não tem a flag de e-mail.
2. Um chamado enviado por e-mail hoje simplesmente não entra (não há caixa configurada). Quando entrar: aparecerá no portal (arquitetura correta) **mas sem contrato e sem faturamento**.
3. Um usuário criado direto no Znuny é invisível para o console.
4. Não dá para adicionar/editar usuário de um cliente já existente pela UI.

**Tarefas:**

1. **T-R2.1 — Cadastro rico de usuário do cliente (telefone, ramal, ativo, flag de e-mail)** — *znuny + sidecar + migration*
   Arquivos: `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserAdd.pm` (aceitar `UserPhone`, `UserMobile`, `ValidID` já aceito), `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserUpdate.pm` (novo), `znuny/webservices/GertiAdmin.yml`, `znuny/Dockerfile`, `apps/sidecar/src/gerti_sidecar/integrations/znuny_customer_admin.py`, `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py`, `apps/sidecar/alembic/versions/0028_portal_user_email_intake.py` (coluna `email_intake_enabled BOOLEAN NOT NULL DEFAULT true` em `portal_user_role`)
   Pronto quando: `POST /{tenant}/users` aceita `phone`/`extension`/`active`/`email_intake_enabled`; `PUT /{tenant}/users/{login}` altera os mesmos; `perl -c` gate verde.

2. **T-R2.2 — `GET /v1/admin/tenants/{id}/users` lendo do Znuny (fonte de verdade)** — *znuny + sidecar*
   Arquivos: `znuny/Custom/Kernel/GenericInterface/Operation/CustomerUser/CustomerUserList.pm` (novo, por `CustomerID`), `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py`
   Regra: a resposta junta o Znuny (identidade, contato, `ValidID`) com `portal_user_role` (papel, `email_intake_enabled`); usuário existente no Znuny sem papel aparece marcado como "sem acesso ao portal".
   Pronto quando: usuário criado direto no Znuny aparece na listagem do console.

3. **T-R2.3 — Vincular contrato a ticket originado por e-mail** — *sidecar (+ znuny)*
   Arquivos: `apps/sidecar/src/gerti_sidecar/domain/reconciliation_service.py`, `apps/sidecar/src/gerti_sidecar/routers/hooks.py`, `apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py`
   Regra: quando um lançamento cai num ticket **sem** `ticket_contract_link`, resolver o tenant pelo `CustomerID` do ticket e vincular ao **único contrato ativo**; se houver 0 ou ≥2, gravar o ticket numa fila de pendência visível no console em vez de descartar. **O cursor não pode avançar sobre entrada descartada sem registro.**
   Pronto quando: um `time_accounting` em ticket sem vínculo gera vínculo automático (1 contrato ativo) ou uma pendência auditável (0 ou ≥2), nunca silêncio.

4. **T-R2.4 — Alinhar a guarda de posse do detalhe de ticket ao escopo da lista** — *sidecar + znuny*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/tickets.py:167-203`, `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketGet.pm:42`
   Regra: papel `helpdesk` só abre ticket cujo `CustomerUserID` é o dele; papel `admin` continua com escopo de empresa.
   Pronto quando: helpdesk pedindo id de colega → **404**.

5. **T-R2.5 — UI de usuários do cliente (listar/adicionar/editar/desativar)** — *admin*
   Arquivos: `apps/admin/pages/clientes/[id]/usuarios.vue` (novo), `apps/admin/server/api/admin/tenants/[id]/users/index.get.ts` (novo), `index.post.ts` (novo), `[login].put.ts` (novo), `apps/admin/composables/useTenantUsers.ts` (novo), link em `apps/admin/pages/clientes/[id]/index.vue`
   Regra de UX: um único formulário por pessoa, com o texto explícito **"Este usuário abre chamados pelo portal e por e-mail — é o mesmo cadastro"** (é o diferencial vendido); desativar é destrutivo → diálogo de confirmação com o e-mail digitado (invariante 3).
   Pronto quando: loading / vazio com CTA / erro; 422 do sidecar exibido em português; nome do cliente visível no header.

6. **T-R2.6 — Configurar ingestão de e-mail (pré-requisito do diferencial)** — *znuny*
   Arquivos: `znuny/entrypoint.sh`, `znuny/Config.pm.tmpl`, `znuny/scripts/ensure-mail-accounts.pl` (novo, idempotente)
   Escopo aqui: **apenas** o suficiente para R2 (uma conta de entrada → fila padrão). O mapeamento rico conta↔fila e remetente de saída é R9 (outro recorte).
   Pronto quando: e-mail enviado de um endereço de `CustomerUser` conhecido vira ticket com `customer_user_id` igual ao login.

**Testes de validação:**

- **V-R2.1** (pytest, novo `apps/sidecar/tests/test_tenant_users_router.py`): `POST /v1/admin/tenants/{id}/users` com `{"email":"ana@acme.example","phone":"+553133330000","extension":"204","active":true,"email_intake_enabled":true}` → **201**; `GET /v1/admin/tenants/{id}/users` devolve a linha com `phone == "+553133330000"` e `extension == "204"`.
- **V-R2.2** (pytest, mesmo arquivo — **o assert que prova o diferencial**): dado um `CustomerUser` `ana@acme.example` e um fake de `znuny_ticket.search_tickets` que devolve **dois** tickets — um com `origem=portal` e outro com `origem=email`, **ambos com `CustomerUserLogin == "ana@acme.example"`** — `GET /v1/tickets` com `gsid` de `ana` (papel `helpdesk`, escopo `own`) → **os dois** aparecem na resposta. Estender `apps/sidecar/tests/test_tickets_router.py:201` (`test_list_helpdesk_scope_own`), que hoje só assere lista vazia.
- **V-R2.3** (pytest, estender `apps/sidecar/tests/test_reconciliation_service.py` — **o teste que protege o faturamento**): lançamento de `time_accounting` em ticket **sem** `ticket_contract_link`, tenant com **exatamente 1** contrato ativo → cria o vínculo e grava `consumption_event`; `balance()` debita. Com **2** contratos ativos → **nenhum** `consumption_event`, mas uma pendência registrada e o cursor **não** avança sobre ela.
- **V-R2.4** (pytest — **negativo / anti-IDOR cross-usuário**): estender `apps/sidecar/tests/test_tickets_router.py:85` (`test_get_ticket_ownership`): `gsid` de `helpdesk` `bob@acme` pedindo `GET /v1/tickets/{id_de_ana}` (mesma empresa) → **404**. Hoje esse caso passa por causa de `tickets.py:174-176` + `TicketGet.pm:42`.
- **V-R2.5** (pytest — **negativo / anti-IDOR cross-tenant**): `POST /v1/admin/tenants/{tenant_A}/users` com cookie `gsid` (cliente, não agente) → **401**; `GET /v1/admin/tenants/{tenant_B}/users` com `gsid_adm` válido → 200 (é privilégio legítimo) **mas** `GET /v1/tenants/{B}/users` com `gsid` de A → 401/404, nunca 200. Padrão de `test_admin_tenants.py:344`.
- **V-R2.6** (vitest, novo `apps/admin/test/tenant-users.test.ts`): `validateUserDraft({email:'sem-arroba'})` → `['E-mail inválido.']`; `buildUserPayload(draft)` **nunca** contém a chave de senha quando é edição (espelhar `apps/admin/test/agent-permissions.test.ts:56`); `confirmDeactivateMatches('ana@acme.example','ana@acme.example')` → `true`, com qualquer outro texto → `false`.
- **V-R2.7** (vitest, mesmo arquivo): proxy `users/[login].put.ts` com login contendo `../` → **404** sem chamar o sidecar (guard de path-injection).
- **V-R2.8** (manual/e2e, novo `docs/runbooks`-style ou `apps/sidecar/tests/test_portal_e2e_smoke.py` estendido): enviar e-mail real da caixa de `ana@acme.example` para a conta de entrada → ticket criado → login de `ana` no portal → o ticket **aparece** em `/tickets` e o contrato aparece vinculado. Este é o **aceite do Kleber**; sem T-R2.6 ele não roda.

**Risco/decisão aberta:**
- **Quem é a fonte de verdade do usuário do cliente?** Hoje há duplicidade parcial: identidade no Znuny (`customer_user`) + papel em `gerti.portal_user_role` (`admin_tenants.py:121-131` lê só o segundo). Opções: **(a)** Znuny é dono, `gerti` guarda só papel/flags (recomendado — evita divergência e resolve "usuário criado no Znuny some do console"); **(b)** `gerti` é dono e espelha no Znuny (dá controle total mas duplica a verdade). Precisa da tua decisão antes de T-R2.2.
- **Auto-criação de `CustomerUser` pelo PostMaster** (`CustomerUser::AutoCreate`): se ligada, qualquer remetente desconhecido vira usuário do cliente — cômodo e perigoso (define quem recebe acesso implícito). Se desligada, e-mail de remetente não-cadastrado precisa de uma fila de "não reconhecido". A flag *"libera tickets por e-mail"* do Kleber é exatamente o botão dessa decisão. Opções: (a) auto-criar sempre; (b) nunca auto-criar (e-mail desconhecido → fila de triagem); (c) auto-criar só se o domínio do remetente estiver na lista de domínios autorizados do cliente (é o que o Kleber descreve em R9, linha 96 da transcrição). Recomendação de leitura: **(c)**, mas depende de R9.
- **Comportamento do cursor de billing** em T-R2.3: mudar o avanço do cursor é mexer em código de faturamento em produção. Alternativa menos invasiva: manter o avanço e gravar as entradas órfãs numa tabela de pendência (`consumption_orphan`), reprocessando ao vincular. Decisão do William.

---

## R5 — Relacionamentos: quais filas cada cliente acessa

**Pedido (citação curta do Kleber):** *"Os relacionamentos. Aqui a gente vai falar quais filas de
atendimento o cara vai ter acesso. […] a gente tem uma fila padrão. Tudo que entra por e-mail vem
pra essa fila. E aí o analista no nível 1, ele classifica se é uma solicitação, se é um incidente.
[…] Pode associar quais técnicos vão atender cada fila. Tem toda uma estratégia de permissionamento
lá."* (transcrição linhas 54–65).

**Estado atual:** **PARCIAL** — o CRUD global de filas existe e o permissionamento técnico↔fila
existe (por grupo); a **associação cliente↔filas não existe em lugar nenhum**.

- CRUD de fila ao vivo no Znuny: `apps/sidecar/src/gerti_sidecar/routers/admin_znuny.py:40` (allowlist inclui `Queue`), ops genéricas em `znuny/Custom/…/GertiAdmin/AdminObjectAdd.pm`/`Update.pm`/`List.pm`/`Get.pm`, tabela em `znuny/Custom/…/GertiAdmin/AdminSpec.pm:51-68`
- Tela existe: `apps/admin/pages/znuny/filas.vue:42` (lista), `:99` (update), `:103` (create); lógica pura em `apps/admin/composables/useZnunyObject.ts:131-236`
- **Técnico↔fila existe, indiretamente:** `Queue.GroupID` é campo gravável (`AdminSpec.pm:62`, `useZnunyObject.ts:133,218`) e agente↔grupo é gravável (`apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:273`, `znuny/Custom/…/GertiAdmin/AdminAgentGroupSet.pm:120-123`). Ou seja: fila → grupo → agentes. Não há uma tela que mostre isso como uma coisa só.
- **Não existe associação cliente↔fila:** grep por `queue` em `apps/sidecar/src/gerti_sidecar/` retorna apenas: allowlist do Znuny (`admin_znuny.py:40`), `catalog_item.znuny_queue` (`apps/sidecar/src/gerti_sidecar/models/catalog_item.py:74` — fila **sugerida por item de catálogo**, não por cliente), `service_catalog_item.default_queue_name` (`apps/sidecar/src/gerti_sidecar/models/catalog.py:41`) e a ação de automação `set_queue` (`apps/sidecar/src/gerti_sidecar/domain/automation_actions.py:53`). **Nenhuma tabela `tenant_queue`.**
- **O portal não deixa o cliente escolher fila e não sabe quais existem:** `FormMeta.pm:35-55` devolve só `Services`, `Priorities`, `Types` — nunca `Queues`; `TicketCreate.pm:67` faz `$CreateArgs{Queue} = $D->{Queue} || 'Raw';`, ou seja, **fila padrão hardcoded `Raw`** quando nada é informado.
- Migrations: nenhuma das 26 (`apps/sidecar/alembic/versions/0001…0026`) cria relação cliente↔fila.

**Gap (comportamento observável):**
1. O operador não consegue dizer "a Aurora acessa as filas Suporte, IMAC e Preventivo"; qualquer cliente cai na mesma fila padrão.
2. A "fila padrão" é literalmente a string `Raw` no Perl (`TicketCreate.pm:67`) — não é configurável por cliente nem globalmente pela UI.
3. Não existe tela que responda "quem atende esta fila?" numa olhada.

**Tarefas:**

1. **T-R5.1 — Tabela `gerti.tenant_queue` (associação cliente↔fila + fila padrão)** — *migration*
   Arquivos: `apps/sidecar/alembic/versions/0029_tenant_queue.py` (novo), `apps/sidecar/src/gerti_sidecar/models/tenant_queue.py` (novo)
   Colunas: `tenant_id` (FK, RLS `FORCE` + policy igual às irmãs), `znuny_queue_id INT`, `znuny_queue_name TEXT` (denormalizado para exibir sem GI), `is_default BOOLEAN`, `UNIQUE(tenant_id, znuny_queue_id)` e índice parcial garantindo **no máximo uma** `is_default` por tenant (mesmo padrão do `agent_timer`, migration `0014`).
   Pronto quando: `upgrade head` limpo; `test_rls_isolation.py` estendido continua verde sob o usuário sem BYPASSRLS.

2. **T-R5.2 — `GET/PUT /v1/admin/tenants/{id}/queues`** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py` (ou novo `admin_tenant_queues.py`), `apps/sidecar/src/gerti_sidecar/domain/tenant_queue_service.py` (novo)
   Regra: valida cada `znuny_queue_id` contra a lista viva do Znuny (`zao.object_list("Queue")`) antes de gravar — fila inexistente → **422**; escrita em `AdminSessionLocal` com `tenant_id` explícito (D16); `audit_service.record`.
   Pronto quando: PUT idempotente (mesmo conjunto → mesmo estado), audita antes/depois.

3. **T-R5.3 — Aplicar a fila padrão do cliente na abertura de chamado** — *sidecar (+ znuny)*
   Arquivos: `apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py`, `apps/sidecar/src/gerti_sidecar/integrations/znuny_ticket.py:356-370` (já aceita `queue`), `apps/sidecar/src/gerti_sidecar/routers/ticketing_meta.py`
   Regra: `POST /v1/tickets` sem fila explícita usa a `is_default` do tenant; se o cliente informar fila, ela precisa estar em `tenant_queue` — senão **422**. `Raw` deixa de ser o destino silencioso.
   Pronto quando: ticket do tenant A nasce na fila padrão de A.

4. **T-R5.4 — Tela `/clientes/[id]/filas.vue` (Relacionamentos)** — *admin*
   Arquivos: `apps/admin/pages/clientes/[id]/filas.vue` (novo), `apps/admin/server/api/admin/tenants/[id]/queues.get.ts` + `.put.ts` (novos), `apps/admin/composables/useTenantQueues.ts` (novo), link em `apps/admin/pages/clientes/[id]/index.vue`
   Conteúdo: multi-seleção das filas do Znuny, marcação de **uma** como padrão, e — por fila escolhida — a lista de **grupos/técnicos que a atendem** (derivada de `Queue.GroupID` + `GET /v1/admin/znuny/agents`), read-only com link para `/znuny/agentes`.
   Pronto quando: loading / vazio com CTA "Cadastrar filas no Znuny" / erro; nome do cliente no header; remover fila padrão exige confirmação (invariante 3).

5. **T-R5.5 — Coluna "atendida por" na tela global de filas** — *admin*
   Arquivos: `apps/admin/pages/znuny/filas.vue`, `apps/admin/composables/useAgentGroups.ts`
   Pronto quando: cada linha de fila mostra o grupo e a contagem de agentes com `rw` naquele grupo.

**Testes de validação:**

- **V-R5.1** (pytest, novo `apps/sidecar/tests/test_admin_tenant_queues_router.py`): `PUT /v1/admin/tenants/{A}/queues` com `[{queue_id:3,is_default:true},{queue_id:5}]` (fake do GI devolvendo as filas 3 e 5) → **200**; `GET` devolve as duas, com `is_default` só na 3.
- **V-R5.2** (pytest, mesmo arquivo — **negativo**): `PUT` com `queue_id: 999` (não existe no Znuny) → **422** e **nenhuma** linha gravada em `tenant_queue`; `PUT` com duas filas `is_default: true` → **422**.
- **V-R5.3** (pytest, novo `apps/sidecar/tests/test_rls_tenant_queue.py` — **negativo / anti-IDOR cross-tenant**): sob `tenant_session_scope(A)` (usuário `gerti_sidecar`, sem BYPASSRLS), `SELECT * FROM gerti.tenant_queue` **não** retorna nenhuma linha do tenant B; sem `app.current_tenant` setado → 0 linhas (fail-closed). Espelhar `apps/sidecar/tests/test_rls_isolation.py`.
- **V-R5.4** (pytest, estender `apps/sidecar/tests/test_ticketing_service.py`): `open_ticket` sem `queue` para tenant com padrão "Suporte::N1" → o payload GI enviado contém `Queue == "Suporte::N1"` (e **não** `"Raw"`); `open_ticket` com `queue="Financeiro"` não associada ao tenant → **422**.
- **V-R5.5** (vitest, novo `apps/admin/test/tenant-queues.test.ts`): `validateQueueSelection([])` → `['Selecione ao menos uma fila.']`; `validateQueueSelection([{id:3,is_default:false},{id:5,is_default:false}])` → `['Marque uma fila como padrão.']`; `buildQueuesPayload(sel)` → array ordenado por id, sem duplicatas.
- **V-R5.6** (e2e Playwright, novo `apps/admin/test/e2e/cliente-filas.spec.ts`): associar 2 filas ao cliente → abrir chamado pelo portal daquele tenant → o chamado aparece na fila padrão configurada.

**Risco/decisão aberta:**
- **Onde mora a associação cliente↔fila?** Opções: **(a)** `gerti.tenant_queue` (nossa tabela — simples, viola em nada o Znuny, mas o agente logado no Znuny não vê a restrição); **(b)** grupo Znuny por cliente + `CustomerUserGroup` nativo (`CustomerGroupSupport`) — paridade real com o Znuny e a restrição vale também na interface nativa, porém dispara criação de N grupos e mexe em SysConfig de risco alto (Bloco D da Spec #4). Recomendação de leitura: **(a)** para o MVP com nota de que a restrição é da nossa camada. Decisão do William.
- A fila padrão hardcoded `Raw` (`TicketCreate.pm:67`) já é um comportamento em **produção/staging**; mudá-la altera onde chamados existentes caem. Precisa de janela e comunicação, não é refactor silencioso.

---

## R7 — Aprovação de tickets (por cliente, opcional)

**Pedido (citação curta do Kleber):** *"Tem uma função de autorização de tickets, de aprovação,
mas a gente não usa. Na verdade, na DataStone a gente utiliza, todo ticket passa, quando essa
chave tá habilitada, todo ticket passa por aqui e vai pra um aprovador. […] Ele tem acesso ao
portal, quando vem um ticket ele recebe um e-mail pra aprovar, ele entra lá no portal e aprova ou
não aprova o ticket."* (transcrição linhas 34–39).

**Estado atual:** **AUSENTE**

- Grep por `aprova|approv` em `apps/sidecar/src`, `apps/admin/pages`, `apps/admin/server`, `apps/portal/pages`, `apps/portal/server`, `znuny/Custom` retorna **apenas** dois domínios não relacionados: aprovação de **dispositivo** (`apps/sidecar/src/gerti_sidecar/routers/admin_agents.py:235`, `apps/sidecar/src/gerti_sidecar/domain/agent_enroll_service.py:200`) e status de **glosa** (`apps/sidecar/src/gerti_sidecar/models/enums.py:38,44`, `apps/sidecar/src/gerti_sidecar/domain/consumption_service.py:77-89`).
- Nenhuma das 26 migrations (`apps/sidecar/alembic/versions/`) tem tabela de aprovação de ticket.
- `apps/sidecar/src/gerti_sidecar/main.py:86-148` não inclui nenhum router de aprovação.
- Papéis do portal são só `admin` e `helpdesk` — `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:50`, `apps/sidecar/src/gerti_sidecar/models/enums.py` (`PortalRole`). Não há papel "aprovador".

**Gap:** o fluxo inteiro. Chave por cliente, papel de aprovador, estado "aguardando aprovação" no
ticket, e-mail ao aprovador, tela de aprovar/reprovar no portal, e o que acontece com o chamado
reprovado.

**Tarefas:**

1. **T-R7.1 — Modelo de aprovação** — *migration*
   Arquivos: `apps/sidecar/alembic/versions/0030_ticket_approval.py` (novo), `apps/sidecar/src/gerti_sidecar/models/ticket_approval.py` (novo)
   Conteúdo: coluna `approval_required BOOLEAN NOT NULL DEFAULT false` em `gerti.tenant`; valor `approver` no enum `gerti.portal_role`; tabela `gerti.ticket_approval` (`tenant_id`, `znuny_ticket_id`, `status` pending/approved/rejected via `CHECK` string — padrão do projeto, sem enum nativo novo, ver nota da migration `0021`), `approver_login`, `decided_at`, `reason`, `UNIQUE(tenant_id, znuny_ticket_id)`, RLS `FORCE` + policy.
   Pronto quando: `upgrade head` limpo; enum estendido sem quebrar `portal_user_role` existente.

2. **T-R7.2 — Barrar o ticket na criação quando o cliente exige aprovação** — *sidecar (+ znuny)*
   Arquivos: `apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py`, `apps/sidecar/src/gerti_sidecar/routers/tickets.py:80`, `znuny/Custom/…/GertiTicket/TicketCreate.pm`
   Regra: com `approval_required`, o ticket nasce num estado Znuny de espera (`new` + fila/estado dedicado, decidido em T-R7.6) e ganha linha `ticket_approval` `pending`. **Não** é criado e depois "escondido" — o estado é real no Znuny, senão o agente atende algo não aprovado.
   Pronto quando: `POST /v1/tickets` de tenant com flag ligada devolve 201 com `approval: "pending"`.

3. **T-R7.3 — `POST /v1/tickets/{id}/approval` (aprovar/reprovar)** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/tickets.py`, `apps/sidecar/src/gerti_sidecar/domain/approval_service.py` (novo)
   Regra: só papel `approver` (ou `admin`) do **mesmo** tenant; decisão é única (segunda chamada → **409**, mesmo padrão do CSAT em `tickets.py:241-266`); aprovar move o ticket ao estado normal via GI `AgentTicketUpdate`; reprovar fecha com nota.
   Pronto quando: 403/404 para quem não é aprovador; 409 em replay; auditado.

4. **T-R7.4 — Notificar o aprovador** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/domain/notification_service.py`, `apps/sidecar/src/gerti_sidecar/jobs/worker.py`
   Regra: reusar `gerti.notification` (migration `0023`) para a notificação in-app; o e-mail sai pelo canal já existente do Znuny (nota/notificação nativa), não por um SMTP novo no sidecar.
   Pronto quando: aprovador vê a pendência em `/notifications` do portal.

5. **T-R7.5 — UI: chave no console + fila de aprovação no portal** — *admin + portal*
   Arquivos: `apps/admin/pages/clientes/[id]/editar.vue` (chave "Exigir aprovação de chamados", depende de T-R1.5), `apps/portal/pages/aprovacoes/index.vue` (novo), `apps/portal/pages/tickets/[id].vue` (bloco de decisão), proxies correspondentes em `apps/portal/server/api/`
   Regra: reprovar é destrutivo → confirmação com motivo obrigatório (invariante 3); nunca `v-html` no motivo.
   Pronto quando: loading / vazio / erro nos dois lados; papel `approver` selecionável no cadastro de usuário (T-R2.5).

6. **T-R7.6 — Definir o estado Znuny de "aguardando aprovação"** — *znuny*
   Arquivos: `znuny/scripts/ensure-approval-state.pl` (novo, idempotente), `znuny/entrypoint.sh`
   Pronto quando: o estado existe após provisionamento, sem passo manual.

**Testes de validação:**

- **V-R7.1** (pytest, novo `apps/sidecar/tests/test_ticket_approval_service.py`): tenant com `approval_required=false` → `POST /v1/tickets` devolve `approval == null` e **nenhuma** linha em `ticket_approval`; com `true` → `approval == "pending"` e 1 linha.
- **V-R7.2** (pytest, mesmo arquivo): `POST /v1/tickets/{id}/approval {"decision":"approved"}` com `gsid` de papel `approver` → **200**, `status == "approved"`, e o fake do GI recebeu `agent_ticket_update` com o estado normal.
- **V-R7.3** (pytest, mesmo arquivo — **negativo**): mesma chamada com `gsid` de papel `helpdesk` → **403**; repetir a decisão já tomada → **409**; decisão `rejected` sem `reason` → **422**.
- **V-R7.4** (pytest — **negativo / anti-IDOR cross-tenant**): `gsid` de aprovador do tenant **B** decidindo um ticket do tenant **A** → **404** (não 403: não deve revelar existência). Espelhar `test_tickets_router.py:141` (`test_reply_ownership_404`).
- **V-R7.5** (pytest, novo `apps/sidecar/tests/test_rls_ticket_approval.py`): sob `tenant_session_scope(B)`, `SELECT` em `ticket_approval` não vê linhas de A; sem GUC → 0 linhas.
- **V-R7.6** (vitest, novo `apps/portal/test/approval.test.ts`): `canDecide(role,'pending')` → `true` só para `approver`/`admin`; `validateRejection({reason:''})` → `['Informe o motivo da reprovação.']`.
- **V-R7.7** (e2e Playwright, novo `apps/portal/test/e2e/aprovacao.spec.ts`): ligar a chave no console → abrir chamado pelo portal → aprovador loga, vê a pendência, aprova → o chamado sai de "aguardando aprovação".

**Risco/decisão aberta:**
- **Como representar "aguardando aprovação" no Znuny?** Opções: **(a)** estado novo (`pending approval`) — mais limpo, exige `ensure-approval-state.pl` e afeta relatórios/SLA; **(b)** fila de quarentena — não mexe em estados mas polui a lista de filas e confunde com R5; **(c)** DynamicField `GertiApprovalStatus` — mínimo impacto, porém o agente pode atender um ticket não aprovado sem perceber. Recomendação de leitura: **(a)**. Decisão do William.
- **SLA conta durante a espera?** O relógio do Znuny corre no estado novo. Se contar, o cliente que demora a aprovar queima o SLA da Gerti. Provavelmente o estado precisa ser `pending`-type (para o SLA), o que muda a resposta acima.
- **O aprovador é um `CustomerUser` a mais?** Se sim, entra na contagem de usuários do cliente (R16 é sobre agentes, não clientes — sem impacto de licença). Confirmar com o Kleber se o aprovador pode ser alguém que **não** abre chamados.

---

## R8 — Importações (clientes, usuários de cliente, outros cadastros)

**Pedido (citação curta do Kleber):** *"Tem as importações que a gente pode eventualmente fazer.
Então, ó. Quero importar cadastros, quero importar cliente, quero importar usuário do cliente,
quero importar, sei lá. Algumas outras coisas."* (transcrição linhas 82–86).

**Estado atual:** **AUSENTE**

- Grep por `csv|UploadFile|multipart` em `apps/sidecar/src/gerti_sidecar`, `apps/admin/server` e `apps/admin/pages` retorna **apenas** o upload de **anexo de chamado** no portal — `apps/sidecar/src/gerti_sidecar/routers/tickets.py:15,48,90`. Nenhum endpoint de importação.
- `apps/sidecar/src/gerti_sidecar/main.py:86-148` não registra router de import.
- O que mais se aproxima são scripts de **seed** (não de importação de dados do cliente): `apps/sidecar/scripts/seed_demo_branding.py`, `scripts/seed-technova.pl`, `scripts/seed-demo.sh`.
- O `OnboardingService.onboard()` (`apps/sidecar/src/gerti_sidecar/domain/onboarding_service.py:75`) já é **idempotente por `znuny_customer_id`/`subdomain`** — é a peça reusável para um importador em lote.

**Gap:** não existe nenhuma forma de carga em lote. A migração do TIFLUX (60 clientes, 43 contratos
ativos, conforme a transcrição linha 144-145) seria feita cliente a cliente, na mão, pelo assistente.

**Tarefas:**

1. **T-R8.1 — Endpoint de validação de importação (dry-run)** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_import.py` (novo), `apps/sidecar/src/gerti_sidecar/domain/import_service.py` (novo), registro em `apps/sidecar/src/gerti_sidecar/main.py`
   `POST /v1/admin/import/{kind}/validate` (`kind` ∈ allowlist `{tenants, tenant_users}`) recebe CSV (multipart), devolve por linha: `ok | erro` com número da linha e mensagem em português. **Não grava nada.**
   Pronto quando: CSV com cabeçalho errado → 422 com a lista de colunas esperadas; nenhuma escrita no Znuny nem no Postgres.

2. **T-R8.2 — Endpoint de execução idempotente** — *sidecar*
   Arquivos: mesmos de T-R8.1
   `POST /v1/admin/import/{kind}` reusa `OnboardingService.onboard()` (já idempotente) por linha; erro numa linha **não** aborta as demais; resposta traz `created`/`skipped`/`failed` com motivo por linha; `audit_service.record` uma vez por lote **e** por linha criada.
   Pronto quando: reexecutar o mesmo CSV → `created == 0`, `skipped == N`, zero duplicata.

3. **T-R8.3 — Limites e proteção** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_import.py`
   Cap de tamanho (ex.: 5 MB / 2.000 linhas), rejeição de conteúdo não-CSV, e **nenhuma senha em texto claro no CSV** — senha é gerada e devolvida uma única vez (ou o usuário nasce sem senha e recebe convite).
   Pronto quando: arquivo acima do cap → **413**; coluna `password` presente no CSV → **422** com mensagem explicando.

4. **T-R8.4 — Tela `/importacoes`** — *admin*
   Arquivos: `apps/admin/pages/importacoes/index.vue` (novo), `apps/admin/server/api/admin/import/[kind]/validate.post.ts` e `[kind].post.ts` (novos), `apps/admin/composables/useImport.ts` (novo, parser/validador puro), link no menu
   Fluxo: escolher tipo → baixar modelo CSV → subir → **pré-visualizar o resultado do dry-run** → confirmar. Importar é destrutivo-ish → confirmação explícita com a contagem ("Criar 47 clientes?").
   Pronto quando: loading / vazio com CTA "Baixar modelo" / erro; erros por linha listados em português; nunca `v-html` no conteúdo do CSV (é entrada não-confiável).

**Testes de validação:**

- **V-R8.1** (pytest, novo `apps/sidecar/tests/test_admin_import_router.py`): CSV com 3 linhas válidas em `POST /v1/admin/import/tenants/validate` → **200**, `{"valid":3,"invalid":0}`, e **zero** chamadas ao fake do GI (asserção explícita de que dry-run não escreve).
- **V-R8.2** (pytest, mesmo arquivo): `POST /v1/admin/import/tenants` com as mesmas 3 linhas → `created == 3`; **repetir** → `created == 0, skipped == 3` e `SELECT count(*) FROM gerti.tenant == 3`.
- **V-R8.3** (pytest, mesmo arquivo — **negativo**): CSV com linha 2 tendo `subdomain` já usado por **outro** `znuny_customer_id` → resposta `failed == 1` citando **linha 2**, e as linhas 1 e 3 criadas (falha isolada); `kind = "contracts"` (fora da allowlist) → **404**.
- **V-R8.4** (pytest, mesmo arquivo — **negativo / auth**): `POST /v1/admin/import/tenants` sem `gsid_adm` → **401**; com `gsid` de cliente → **401**.
- **V-R8.5** (pytest, mesmo arquivo — **negativo / anti-IDOR cross-tenant**): CSV de `tenant_users` para `tenant_id` **B** enviado por um lote cujo cabeçalho aponta o tenant A → cada linha é validada contra o tenant do corpo, e um `tenant_id` desconhecido → **404** sem criar `CustomerUser` no Znuny (assert no fake: zero chamadas).
- **V-R8.6** (vitest, novo `apps/admin/test/import-csv.test.ts`): `parseCsv('email,nome\\nana@x.com,Ana')` → 1 linha; cabeçalho faltando coluna obrigatória → `{ok:false, missing:['nome']}`; célula com `=cmd|' /C calc'!A0` (CSV injection) é tratada como texto e **nunca** renderizada como HTML.

**Risco/decisão aberta:**
- **Formato:** CSV (simples, o Kleber já exporta do TIFLUX) vs. XLSX (o que o pessoal usa no dia a dia, exige dependência nova). Recomendação de leitura: CSV UTF-8 com modelo baixável; XLSX depois.
- **Senha na importação:** gerar e exibir uma vez (operador copia) vs. criar sem senha e disparar convite por e-mail (depende de e-mail funcionando — ver R2/T-R2.6). Decisão do William.
- **Escopo de "outros cadastros"** (linha 85 da transcrição, deliberadamente vago): sugiro fechar em `tenants` e `tenant_users` no MVP e tratar catálogo/contratos como fase 2.

---

## R14 — Usuários da plataforma (agentes), grupos de atendente e permissões

**Pedido (citação curta do Kleber):** *"Aqui a parte de usuários da plataforma, os grupos de
atendente, as permissões. Isso é importante também."* (transcrição linha 130).

**Estado atual:** **PARCIAL** — é o requisito mais bem coberto deste recorte; falta granularidade
de permissão e criação de grupo.

- Endpoints completos de agente: `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:158` (list), `:171` (get), `:186` (create), `:222` (update), `:312` (set password — operação **separada**, 204)
- Grupos: `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:260` (`GET /groups`) e `:273` (`PUT /agents/{id}/groups`)
- Ops GI: `znuny/Custom/…/GertiAdmin/AdminAgentList.pm`, `AdminAgentGet.pm`, `AdminAgentSet.pm`, `AdminAgentSetPassword.pm`, `AdminGroupList.pm`, `AdminAgentGroupSet.pm`; rotas em `znuny/webservices/GertiAdmin.yml:122-146`
- **Senha nunca vaza:** filtrada no Perl e nos DTOs — `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:6-16` (docstring) e `AgentUpdate` sem campo de senha (`:76-80`)
- **Anti-lockout real, no Perl:** `znuny/Custom/…/GertiAdmin/AdminAgentGroupSet.pm:98-109` — agente não se remove do grupo `admin`
- **Auditoria antes/depois na mudança de permissão:** `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:299-312` (`AgentGroupsOut` com `before`/`after`)
- Tela + lógica pura testada: `apps/admin/pages/znuny/agentes.vue`, `apps/admin/composables/useAgentGroups.ts`, `apps/admin/test/agent-permissions.test.ts:119` (`diffAgentGroups`), `:162` (`wouldRemoveSelfFromAdmin`)
- **Limitação 1 — permissão é tudo-ou-nada:** a associação grava apenas `rw` — `znuny/Custom/…/GertiAdmin/AdminAgentGroupSet.pm:120-123` (`Permission => { rw => $IsDesired ? 1 : 0 }`) e lê apenas `Type => 'rw'` (`:92-94`, `:136-138`). Os demais tipos nativos do Znuny (`ro`, `move_into`, `create`, `note`, `owner`, `priority`) **não são expostos** — é exatamente a "estratégia de permissionamento" que o Kleber cita (linha 65).
- **Limitação 2 — não dá para criar grupo:** só existe `AdminGroupList.pm`; não há `AdminGroupAdd/Update` (`znuny/webservices/GertiAdmin.yml:138-142` só mapeia `/Group/List`). "Grupos de atendente" é read-only.
- **Limitação 3 — nada de papéis (Roles):** o Znuny tem `roles` (`Kernel::System::Group`), não expostos em `AdminSpec.pm:50-145` nem em `admin_znuny_people.py`.
- **Limitação 4 — sem exclusão** (correto e intencional): a Spec #4 invalida com `ValidID=2`, e a UI diz "Invalidar".

**Gap (comportamento observável):**
1. Não é possível dar a um técnico acesso **somente leitura** a uma fila — ou ele tem `rw` no grupo, ou não tem nada.
2. Não é possível criar um grupo novo (ex.: "DPO") pelo console; precisa entrar no Znuny nativo.
3. Não há conceito de perfil/papel reutilizável — cada agente é configurado grupo a grupo.

**Tarefas:**

1. **T-R14.1 — Permissões granulares por grupo** — *znuny + sidecar*
   Arquivos: `znuny/Custom/Kernel/GenericInterface/Operation/GertiAdmin/AdminAgentGroupSet.pm`, `apps/sidecar/src/gerti_sidecar/integrations/znuny_admin_people.py`, `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:273`
   Regra: o corpo passa de `group_ids: list[int]` para `groups: list[{id, permissions: [ro|move_into|create|note|owner|priority|rw]}]`; allowlist fechada dos 7 tipos, tipo desconhecido → **422** (nunca descarte silencioso, padrão de `AdminSpec.pm:185-195`); **anti-lockout preservado** (`AdminAgentGroupSet.pm:98-109`) e estendido: não dá para rebaixar o próprio `rw` no grupo `admin`.
   Pronto quando: `perl -c` verde; `before`/`after` da auditoria passam a carregar os tipos, não só o nome do grupo.

2. **T-R14.2 — Criar e invalidar grupos** — *znuny + sidecar*
   Arquivos: `znuny/Custom/…/GertiAdmin/AdminGroupAdd.pm` e `AdminGroupUpdate.pm` (novos) **ou** — preferível — incluir a chave `Group` na tabela genérica `znuny/Custom/…/GertiAdmin/AdminSpec.pm:50` (`Kernel::System::Group`, `GroupList`/`GroupGet`/`GroupAdd`/`GroupUpdate`, `Fields => [Name Comment ValidID]`) e na allowlist `apps/sidecar/src/gerti_sidecar/routers/admin_znuny.py:40`
   Pronto quando: zero módulo Perl novo (reusa Bloco A); `GET/POST/PUT /v1/admin/znuny/objects/Group` funcionam; sem exclusão (só `ValidID=2`).

3. **T-R14.3 — Matriz agente × grupo × permissão na UI** — *admin*
   Arquivos: `apps/admin/pages/znuny/agentes.vue`, `apps/admin/composables/useAgentGroups.ts`, `apps/admin/components/znuny/` (novo componente de matriz)
   Regra: diálogo de confirmação mostrando o diff **antes de gravar** (já existe para grupos — `apps/admin/test/agent-permissions.test.ts:119`), agora por tipo de permissão; remoção de permissão é destrutiva → confirmação (invariante 3).
   Pronto quando: loading / vazio / erro; a matriz é operável por teclado; SSR-safe (`useId()` nos ids da tabela).

4. **T-R14.4 — Tela `/znuny/grupos.vue`** — *admin*
   Arquivos: `apps/admin/pages/znuny/grupos.vue` (novo), `apps/admin/server/api/admin/znuny/objects/[object]/*` (já genérico — **nenhum proxy novo**), link no menu
   Pronto quando: cria/edita/invalida grupo reusando `useZnunyObject.ts`; texto "Invalidar", nunca "Excluir".

**Testes de validação:**

- **V-R14.1** (pytest, estender `apps/sidecar/tests/test_admin_znuny_people_router.py`): `PUT /v1/admin/znuny/agents/7/groups` com `[{"id":3,"permissions":["ro","note"]}]` → **200** e o fake do GI recebeu `Permission => {ro:1, note:1, rw:0}`.
- **V-R14.2** (pytest, mesmo arquivo — **negativo**): `permissions: ["superuser"]` (fora da allowlist) → **422** e **zero** chamadas ao GI; corpo sem `permissions` → 422.
- **V-R14.3** (pytest, mesmo arquivo — **negativo / anti-lockout**): agente `admin@gerti` removendo a si mesmo do grupo `admin` → **422** com a mensagem do Perl repassada, e `PermissionUserGroupGet` continua listando o grupo. (O guard existe em `AdminAgentGroupSet.pm:98-109` — o teste prova que sobrevive à mudança de contrato.)
- **V-R14.4** (pytest, mesmo arquivo — **negativo / vazamento de senha**): `GET /v1/admin/znuny/agents/7` → o JSON **não** contém nenhuma chave casando `/pw|password|hash/i` (grep na resposta serializada), mesmo que o fake do GI devolva `UserPw`.
- **V-R14.5** (pytest, estender `apps/sidecar/tests/test_admin_znuny_router.py`): `POST /v1/admin/znuny/objects/Group {"Name":"dpo"}` → **201**; `POST` com campo fora da allowlist (`{"Name":"x","Secret":"y"}`) → **422** citando `Secret`; `GET /v1/admin/znuny/objects/Roles` → **404** (allowlist).
- **V-R14.6** (vitest, estender `apps/admin/test/agent-permissions.test.ts`): `diffAgentPermissions(before, after)` devolve ganhos e perdas **por tipo** (`{group:'suporte', gained:['note'], lost:['rw']}`); `wouldDowngradeSelfInAdmin(self, draft)` → `true` ao tirar `rw` do próprio admin.
- **V-R14.7** (vitest, novo `apps/admin/test/znuny-group.test.ts`): `validateGroupDraft({Name:''})` → `['Nome do grupo é obrigatório.']`; `buildInvalidateGroupPayload(draft).ValidID === 2`.
- **V-R14.8** (pytest — **auth**): todas as rotas novas sem `gsid_adm` → **401**; com `gsid` de cliente → **401** (padrão `test_admin_tenants.py:344`).

**Risco/decisão aberta:**
- **Roles do Znuny:** expor ou não? O Kleber fala de "grupos de atendente", não de roles. Opções: (a) só grupos (menor superfície, alinhado à fala); (b) grupos + roles (mais poder, mas duas hierarquias de permissão confundem o operador). Recomendação de leitura: **(a)**.
- Migrar de `rw`-only para permissões granulares **muda o significado do estado atual**: hoje todo agente associado tem `rw`. A tela precisa mostrar isso honestamente na primeira abertura ("todos os grupos atuais estão como acesso total"), senão o operador acha que perdeu configuração.

---

## R16 — Licenciamento / seats (impacta o faturamento DA GERTI)

**Pedido (citação curta do Kleber):** *"Esse quadrinho aqui à direita, são o que a gente tem de
direito. Então, hoje tem sete usuários ativos, a gente tem um total de nove […] Total de clientes
cadastrados, 60. Contratos ativos, 43. […] a gente acaba no usuário cadastrando aqui qual tipo de
licença ele tem […] qual módulo esse cara vai ter ativo, se ele vai poder falar no WhatsApp, se
ele vai poder fazer acesso remoto ou não. […] Isso aqui impacta no faturamento da plataforma para
a gente."* (transcrição linhas 140–153).

**Estado atual:** **AUSENTE**

- Grep por `licen|seat` (case-insensitive) em `apps/sidecar/src`, `apps/admin/pages` e `apps/admin/composables` → **nenhuma ocorrência**. Idem para `mfa`, `splashtop`, `whatsapp`.
- Nenhuma das 26 migrations (`apps/sidecar/alembic/versions/0001…0026`) tem tabela de licença, seat ou módulo por agente.
- O modelo de agente é o do Znuny e não tem nada de licença: `apps/sidecar/src/gerti_sidecar/routers/admin_znuny_people.py:61-68` (`AgentOut`: `id/login/first_name/last_name/email/valid`).
- **Não há painel agregado da operação.** `GET /v1/admin/analytics` **exige** `tenant_id` e é por cliente — `apps/sidecar/src/gerti_sidecar/routers/admin_analytics.py:34-37`. A lista de clientes é um grid sem totalizador — `apps/admin/pages/index.vue:53-80`. Não existe "60 clientes / 43 contratos ativos / 7 de 9 agentes" em lugar nenhum. (O dado *base* existe: `list_tenants` já devolve `contract_count` por tenant — `apps/sidecar/src/gerti_sidecar/routers/admin_tenants.py:174-196`.)
- O que existe de "quadro" é a **saúde técnica**, não direitos comerciais: `GET /v1/admin/system/health` (`apps/sidecar/src/gerti_sidecar/routers/admin_system.py:21`, tela `apps/admin/pages/sistema/index.vue`).

**Gap:** o conceito inteiro. Sem tipo de licença por agente, sem módulos habilitáveis, sem MFA, sem
teto contratado e sem o painel de "ativos vs. direito". Como o próprio Kleber diz que isso **impacta
o faturamento da plataforma**, é o requisito deste recorte com maior risco comercial de ser
esquecido — e o único cujo dado **não existe nem parcialmente**.

**Tarefas:**

1. **T-R16.1 — Modelo de licenciamento** — *migration*
   Arquivos: `apps/sidecar/alembic/versions/0031_licensing.py` (novo), `apps/sidecar/src/gerti_sidecar/models/licensing.py` (novo)
   Tabelas **operacionais não-tenant** (mesmo padrão de `audit_log`/`worker_heartbeat`: sem RLS, acessadas só por `AdminSessionLocal` — ver `apps/sidecar/alembic/versions/0024_audit_log.py` e `0026_worker_heartbeat.py`):
   - `gerti.license_plan` — catálogo fechado de tipos (`code`, `name`, `included_modules JSONB`, `monthly_price_brl`)
   - `gerti.license_entitlement` — o teto contratado (`seats_total`, `valid_from`, `valid_to`)
   - `gerti.agent_license` — `znuny_agent_login` (chave), `plan_code`, `modules JSONB` (allowlist), `mfa_enabled`, `phone`, `active`, `assigned_at`
   Pronto quando: `upgrade head` limpo; `gerti_app` **sem** GRANT nestas tabelas (espelhar `0025_audit_log_revoke_app.py`), com teste provando.

2. **T-R16.2 — `GET/PUT /v1/admin/licensing/agents/{login}`** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_licensing.py` (novo), `apps/sidecar/src/gerti_sidecar/domain/licensing_service.py` (novo), registro em `apps/sidecar/src/gerti_sidecar/main.py`
   Regra: módulos vêm de **allowlist fechada** (`tickets`, `remote_access`, `whatsapp`, `inventory`) — módulo desconhecido → **422**; atribuir licença quando `seats_used >= seats_total` → **409** com mensagem explícita ("sem seats disponíveis: 9 de 9 em uso"); toda mudança auditada (`audit_service.record`, entity `agent_license`).
   Pronto quando: o 409 é o comportamento default (fail-closed), não um aviso.

3. **T-R16.3 — `GET /v1/admin/licensing/summary` (o "quadrinho")** — *sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_licensing.py`
   Devolve `{seats_used, seats_total, seats_free, tenants_total, contracts_active, agents_active}`. Reusa a contagem já existente de `list_tenants` (`admin_tenants.py:174-186`) e o enum de status de contrato.
   Pronto quando: os números batem com `SELECT count(*)` direto no banco (asserção no teste).

4. **T-R16.4 — Módulos passam a gatear a UI do console** — *admin + sidecar*
   Arquivos: `apps/sidecar/src/gerti_sidecar/routers/admin_auth.py` (incluir `modules` no payload de `/v1/admin/me`), `apps/admin/server/api/admin/me.get.ts`, `apps/admin/composables/useAdmin.ts`, `apps/admin/app.vue`/layout (menu)
   Regra: **gating é servidor-side também** — esconder o link não basta; o endpoint correspondente precisa negar. Exemplo do Kleber: *"a Georgia só usa tickets, não tem acesso remoto → não vê o inventário"* (linha 150-151) → sem módulo `inventory`, `/clientes/[id]/agentes` responde 403.
   Pronto quando: um agente sem `inventory` recebe **403** na API, não só um menu escondido.

5. **T-R16.5 — Telas `/licenciamento`** — *admin*
   Arquivos: `apps/admin/pages/licenciamento/index.vue` (novo, o quadro + lista de agentes com licença), `apps/admin/server/api/admin/licensing/summary.get.ts` e `agents/[login].get.ts`/`.put.ts` (novos), `apps/admin/composables/useLicensing.ts` (novo), card resumo em `apps/admin/pages/index.vue`
   Regra visual: `seats_free == 0` → estado `warning`; `seats_used > seats_total` (estouro por importação/legado) → `error`. Tokens semânticos, nunca cor crua (invariante 4). Revogar licença é destrutivo → confirmação com o login digitado (invariante 3).
   Pronto quando: loading / vazio com CTA "Definir o total contratado" / erro; SSR-safe.

6. **T-R16.6 — MFA do agente** — *znuny + sidecar* (**avaliar antes de comprometer**)
   Arquivos: investigação primeiro — o Znuny 7.2 tem 2FA nativo por preferência de usuário; o login do console é `Session::SessionCreate` (`apps/sidecar/src/gerti_sidecar/integrations/znuny_agent_auth.py`), que pode não carregar o segundo fator.
   Pronto quando: existir uma nota de decisão dizendo se MFA é do Znuny, do console ou de um IdP (ver R16 risco abaixo).

**Testes de validação:**

- **V-R16.1** (pytest, novo `apps/sidecar/tests/test_licensing_service.py`): `entitlement.seats_total = 2`, duas licenças ativas → `PUT /v1/admin/licensing/agents/carol` → **409** com `detail` contendo `"2 de 2"`; após revogar uma → mesma chamada → **200**.
- **V-R16.2** (pytest, mesmo arquivo — **negativo/allowlist**): `PUT` com `modules: ["remote_access","god_mode"]` → **422** citando `god_mode`, e `SELECT modules` inalterado.
- **V-R16.3** (pytest, novo `apps/sidecar/tests/test_admin_licensing_router.py`): com 3 tenants, 5 contratos (2 `active`) e 2 agentes licenciados de 9 → `GET /v1/admin/licensing/summary` → `{"seats_used":2,"seats_total":9,"seats_free":7,"tenants_total":3,"contracts_active":2}`.
- **V-R16.4** (pytest, mesmo arquivo — **negativo / gating server-side**): `gsid_adm` de agente **sem** o módulo `inventory` → `GET /v1/admin/tenants/{id}/devices` → **403**; com o módulo → 200. (Prova que o gate não é só de menu.)
- **V-R16.5** (pytest, mesmo arquivo — **negativo / auth e cross-tenant**): rotas de licenciamento sem `gsid_adm` → **401**; com `gsid` de cliente → **401**. Como licenciamento é dado **da Gerti** (não de tenant), incluir também: nenhuma rota `/v1/*` de cliente devolve qualquer campo de licença (grep na resposta de `GET /v1/me` por `licen|seat|module` → vazio).
- **V-R16.6** (pytest, novo `apps/sidecar/tests/test_licensing_not_readable_by_app.py`): conectado como `gerti_sidecar` **sem** BYPASSRLS, `SELECT * FROM gerti.agent_license` → erro de permissão. Espelhar `apps/sidecar/tests/test_audit_log_not_readable_by_app.py` e `test_worker_heartbeat_not_readable_by_app.py`.
- **V-R16.7** (vitest, novo `apps/admin/test/licensing.test.ts`): `seatsTone({used:9,total:9})` → `'warning'`; `{used:10,total:9}` → `'error'`; `{used:7,total:9}` → `'neutral'`; `formatSeats({used:7,total:9})` → `'7 de 9 licenças em uso · 2 disponíveis'`; `validateLicenseDraft({plan:'',modules:[]})` → `['Selecione o tipo de licença.']`.
- **V-R16.8** (vitest, mesmo arquivo): `confirmRevokeMatches('vinicius','vinicius')` → `true`; qualquer divergência → `false` (invariante 3).

**Risco/decisão aberta:**
- **Qual é o modelo comercial da Gerti?** Kleber descreve o licenciamento que **ele compra do TIFLUX**. No Ground Control a Gerti é a dona da plataforma — cabe decidir se: **(a)** o console apenas *espelha* o contrato Gerti↔WAS (a WAS cobra por seat de agente) — então `license_entitlement` é definido pela WAS e o Kleber só consome; **(b)** vira também o motor de cobrança da WAS (integrando com o Asaas da Spec #2). Isto muda tudo: quem escreve `seats_total`. **Decisão do William, bloqueante para T-R16.1.**
- **Módulos citados não existem no produto:** `whatsapp` e `remote_access`/Splashtop não têm nenhuma implementação no monorepo. Opções: (a) modelar os módulos agora e deixá-los inertes (o licenciamento fica pronto, o recurso vem depois); (b) modelar só os módulos reais hoje (`tickets`, `inventory`) e crescer. Recomendação de leitura: **(b)** — evita vender no console um botão que não faz nada.
- **MFA:** do Znuny (nativo, mas o login do console passa por `Session::SessionCreate` e pode ignorar o 2º fator), do console (JWT `gsid_adm` próprio, TOTP nosso) ou de um IdP (bate com o #1D/OIDC, hoje `Pendente (deferred)` em `.ia/INTEGRATION.md:99,159`). Recomendação de leitura: adiar MFA e resolver junto com OIDC — implementá-lo agora no console cria um segundo sistema de identidade para desfazer depois.

---

## Tabela-resumo

| Requisito | Estado | # tarefas | Esforço grosseiro |
|---|---|---|---|
| R1 — Cadastro de cliente | **PARCIAL** | 6 | **M** |
| R2 — Usuário único (portal + e-mail) | **PARCIAL** | 6 | **G** |
| R5 — Relacionamentos / filas por cliente | **PARCIAL** | 5 | **M** |
| R7 — Aprovação de tickets | **AUSENTE** | 6 | **G** |
| R8 — Importações | **AUSENTE** | 4 | **M** |
| R14 — Agentes, grupos e permissões | **PARCIAL** | 4 | **M** |
| R16 — Licenciamento / seats | **AUSENTE** | 6 | **G** |

**Totais:** 37 tarefas · 47 testes de validação (12 deles negativos/anti-IDOR).

**Ordem sugerida (dependências reais, não prioridade comercial):**
`T-R1.1/1.2` (edição de cliente) → `T-R2.1/2.2/2.5` (usuário rico) → `T-R2.3` (**vínculo de contrato — protege o faturamento**) → `T-R5.1/5.2/5.3` (filas por cliente) → `T-R2.6` (ingestão de e-mail, que só faz sentido depois de R5 e T-R2.3) → `T-R8.*` (importação, que consome o modelo já estabilizado) → `T-R14.*` → `T-R7.*` → `T-R16.*` (bloqueado por decisão comercial).

**Bloqueios de decisão que travam início de tarefa:**
`T-R1.1` (fonte de verdade do endereço) · `T-R2.2` (fonte de verdade do usuário) · `T-R2.6` (auto-criação pelo PostMaster) · `T-R2.3` (comportamento do cursor de billing) · `T-R5.1` (tabela nossa vs. grupos Znuny) · `T-R7.6` (representação do estado de aprovação + SLA) · `T-R16.1` (modelo comercial da WAS).
