# Spec #1E — Portal do Cliente: abertura, lista e detalhe de chamados (com vínculo de contrato)

**Data:** 2026-06-05
**Status:** aprovado (escopo travado no brainstorming) → pronto para plano/execução
**Escopo deste ciclo (#1E):** fluxo de **tickets no portal do cliente** — abrir chamado
(com **seleção de contrato**), listar os chamados e ver detalhe/responder. Toda escrita/leitura
de ticket no Znuny via Generic Interface (webservice custom **`GertiTicket`**). O chamado
nasce **vinculado a um contrato** (`gerti.ticket_contract_link` + DynamicField `GertiContractId`),
deixando o terreno **billing-ready**.
**Fora deste ciclo (próxima spec, logo em seguida):** a **cobrança/consumo** (#1B) —
atividade no ticket → `gerti.consumption_event` → debita saldo. Esta spec NÃO debita saldo;
só estabelece o vínculo ao qual o consumo futuro se atrela.

## 1. Decisões (brainstorming 2026-06-05)

- **D-1E-1 (escopo):** fluxo **completo** no portal — criar + listar + detalhe/responder.
  Substitui o placeholder `/tickets` (#1H).
- **D-1E-2 (seleção de contrato):** todo chamado nasce **vinculado a um contrato**.
  Se o tenant tem **1** contrato ativo → auto-vincula sem perguntar. Se tem **≥2** →
  o cliente **escolhe** (obrigatório). Vínculo sempre presente (melhor para faturamento).
- **D-1E-3 (campos do formulário):** além de **contrato + assunto + descrição**, o form
  tem **serviço/fila**, **tipo**, **prioridade** e **anexos** — modelo Znuny, em **página única**.
- **D-1E-4 (vínculo no Znuny):** o contrato é gravado **no próprio ticket** via DynamicField
  **`GertiContractId`** (parte da #1B trazida para cá) **e** em `gerti.ticket_contract_link`.
  O agente vê o contrato ao atender; webhooks de consumo futuros já carregam o vínculo.
- **D-1E-5 (visibilidade da lista):** **por papel** (#1H): `helpdesk` vê só os chamados que
  ele abriu (`CustomerUserID`); `admin` vê todos da empresa (`CustomerID`).
- **D-1E-6 (mecanismo GI):** webservice custom **`GertiTicket`** em `znuny/Custom/...` com
  `AccessToken` fail-closed — mesmo padrão do `GertiAdmin` já em prod. NÃO usar o Ticket
  Connector nativo (auth divergente + superfície genérica a travar).
- **D-1E-7 (layout):** formulário de abertura em **página única** (form A do mockup),
  Nuxt UI auto-branded, seletor de contrato condicional (some com 1, aparece com ≥2).
- **D-1E-8 (cobrança):** **próxima spec** (#1B). #1E entrega o link billing-ready; nada
  de consumo/débito de saldo neste ciclo.
- **D-1E-9 (UX-first):** as telas do portal são conduzidas por um **especialista de
  frontend/UX** (skill `frontend-design`). Aceite = o cliente final entende, de bate-pronto,
  o que está acontecendo: linguagem clara, estados vazios/carregando/erro compreensíveis,
  feedback explícito de cada ação, acessibilidade.

## 2. Arquitetura

```
Browser → cloudflared → portal:3000 (SSR proxy, cookie gsid)
                            │
                            ▼
                       sidecar:8001  ──(GI AccessToken)──►  znuny-web
                       /v1/tickets/*                         webservice GertiTicket
                       /v1/ticketing/*                       + DynamicField GertiContractId
                            │
                            ▼
                       gerti schema (RLS)
                       ticket_contract_link  ← popula o vínculo (billing-ready)
```

Princípios herdados (não-negociáveis): núcleo Znuny **imutável** (escrita/leitura de ticket
só via GI); **sidecar é a única porta** (browser nunca fala com Znuny/DB); **RLS multi-tenant**
nos endpoints do cliente; **profile-gated `gerti`**, aditivo (um `make up` da stack Znuny não toca).

### 2.1 Znuny (`znuny/Custom/`, bakeado na imagem no build)

- **DynamicField `GertiContractId`** — tipo `Text`, objeto `Ticket`, criado de forma
  **idempotente** no deploy (`bin/otrs.Console.pl Admin::DynamicField::*` com checagem de
  existência, ou import YAML). Guarda o `contract_id` (UUID) no ticket.
- **Webservice `GertiTicket`** (`Custom/Kernel/GenericInterface/Operation/GertiTicket/*`
  + `webservices/GertiTicket.yml` COPY na imagem). Operações, todas `AccessToken` fail-closed
  (mesmo `ZNUNY_WS_TOKEN`), embrulhando API Perl nativa:

  | Operação | Embrulha | Papel |
  |---|---|---|
  | `TicketCreate` | `Ticket::TicketCreate` + `ArticleCreate` | Cria como `CustomerUser` (da sessão), seta Service/Type/Priority, grava `GertiContractId`, 1º artigo com corpo + anexos base64 |
  | `TicketSearch` | `TicketSearch` | Lista por `CustomerUserID` (helpdesk) **ou** `CustomerID` (admin) |
  | `TicketGet` | `TicketGet` + `Article*` | Detalhe + thread (só artigos `IsVisibleForCustomer`) |
  | `TicketReply` | `ArticleCreate` (customer) | Resposta do cliente a ticket existente |
  | `FormMeta` | `Service::ServiceList(CustomerUser)`, `PriorityList`, `TypeList` | Catálogo do formulário (serviços por cliente + prioridades + tipos) |

- **Guarda de deploy:** import idempotente; **nunca** remove/substitui `GertiCustomerAuth`
  nem `GertiAdmin` (mesma checagem `Admin::WebService::List | grep` do runbook #1G-a).

### 2.2 Sidecar (`apps/sidecar`)

- **`integrations/znuny_ticket.py`** (espelha `znuny_customer_admin.py`): `create_ticket`,
  `search_tickets`, `get_ticket`, `reply_ticket`, `form_meta`. Auth `AccessToken`
  (`ZNUNY_WS_TOKEN`); base `ZNUNY_ADMIN_WS_URL` com path `/Webservice/GertiTicket`. Erros:
  `ZnunyUnavailable`→503, `ZnunyWriteError`→4xx (exceções já existentes).
- **`domain/ticketing_service.py`** — `open_ticket(session, payload)`:
  1. valida `contract_id` existe e `active` **sob RLS** (some → 404, padrão `contracts.py`);
  2. nenhum contrato informado + 1 ativo → auto-seleciona; ≥2 e vazio → **422**;
  3. `znuny_ticket.create_ticket(...)` com `GertiContractId`;
  4. grava `gerti.ticket_contract_link` (`znuny_ticket_id`, `contract_id`, `tenant_id`,
     `billing_status='pending'`, `linked_by_rule='portal:<customer_login>'`) — **billing-ready**;
  5. retorna número do chamado.
  O link só é gravado **após** o ticket nascer no Znuny. Falha no INSERT pós-criação é
  reconciliável por `znuny_ticket_id` (PK = ticket id → idempotente).
- **Endpoints:**

  | Método | Rota | Auth | Papel |
  |---|---|---|---|
  | `GET` | `/v1/ticketing/contracts` | `get_current_session` | qualquer logado (contratos ativos selecionáveis — **novo, não-`require_admin`**) |
  | `GET` | `/v1/ticketing/form-meta` | `get_current_session` | qualquer logado (serviços/prioridades/tipos) |
  | `POST` | `/v1/tickets` | `get_current_session` + `get_tenant_session` | qualquer logado |
  | `GET` | `/v1/tickets` | `get_current_session` | escopo por papel (helpdesk=meus / admin=empresa) |
  | `GET` | `/v1/tickets/{id}` | `get_current_session` | guarda de posse |
  | `POST` | `/v1/tickets/{id}/reply` | `get_current_session` | guarda de posse |

### 2.3 Portal (`apps/portal`)

- **Server proxies** (`sidecarFetch`, encaminha `gsid`):
  `server/api/portal/ticketing/{contracts,form-meta}.get.ts`,
  `server/api/portal/tickets/{index.get,index.post,[id].get,[id]/reply.post}.ts`
  (o `index.post` repassa `multipart/form-data` dos anexos).
- **Páginas** (`middleware: 'auth'`, layout `default`, brand tokens, Nuxt UI):
  - `/tickets` — **substitui o placeholder**: lista por papel (número, assunto, status badge,
    contrato, data) + botão "Novo chamado".
  - `/tickets/novo` — **form A (página única)**: contrato (condicional ≥2), serviço, tipo,
    prioridade, assunto, descrição, anexos.
  - `/tickets/[id]` — detalhe: cabeçalho + thread (artigos visíveis ao cliente) + caixa de resposta.
- **UX-first (D-1E-9):** especialista `frontend-design` é dono das telas. Cores semânticas
  (`warning`/`error`) nunca usam a cor de marca (H8). Estados de loading/erro/vazio no padrão
  do `login.vue`. Nav do header ganha "Chamados" para os papéis adequados.

## 3. Segurança

- **Listagem de contratos selecionáveis** é endpoint **novo não-admin** (`/v1/ticketing/contracts`);
  os `/v1/contracts*` (#1F-b) continuam `require_admin`. Devolve só o necessário ao dropdown
  (`id`, `code`, label do tipo, saldo formatado), read-only, sob RLS por tenant.
- **Escopo por papel** vem do claim `role` no JWT (#1H): `helpdesk`→`CustomerUserID=login`;
  `admin`→`CustomerID=tenant.znuny_customer_id`.
- **Guarda de posse (anti-IDOR):** `GET`/`reply` `/v1/tickets/{id}` validam que o ticket
  pertence ao `CustomerID` do tenant da sessão **antes** de devolver/responder (o `TicketGet`
  recebe o `CustomerID`; sidecar rejeita 403/404 se não bater). Defesa em profundidade além
  do isolamento por subdomínio.
- **Anexos:** `POST /v1/tickets` aceita `multipart/form-data`; sidecar valida tipo/tamanho
  (limite configurável + allowlist de extensão), converte para base64 e repassa no GI.
- Toda escrita/leitura de ticket via GI (Spec #0) — **zero SQL direto** no schema Znuny
  (grep-guard de teste garante).

## 4. Dados

- **`gerti.ticket_contract_link`** já existe e está migrada: criada pela migration
  `0008_policy_ticketlink` (PK `znuny_ticket_id`, `contract_id`, `tenant_id`, `billing_status`
  default `pending`, `linked_at`, `linked_by_rule`; índices em `contract_id` e
  `(tenant_id, billing_status)`; **ENABLE+FORCE RLS** com policy `tenant_isolation`). Modelo
  ORM em `models/ticket_link.py`.
- **Nenhuma migration nova** neste ciclo — só uso de escrita na tabela já existente.

## 5. Testes (zero-tolerância, gate `ruff + mypy + pytest`)

- **Sidecar (pytest + testcontainers):** auto-seleção de contrato único; **422** se ≥2 sem
  escolha; contrato inexistente → **404** sob RLS; guarda de posse anti-IDOR (ticket de outro
  `CustomerID` → 403); escopo por papel (helpdesk só os seus); GI mockado (sucesso,
  `ZnunyUnavailable`→503, `ZnunyWriteError`→4xx); idempotência do link por `znuny_ticket_id`;
  grep-guard: nenhum endpoint novo escreve no schema `znuny`.
- **Znuny:** import idempotente do `GertiTicket` (não duplica, não toca `GertiAdmin`/
  `GertiCustomerAuth`); DynamicField criado uma vez; smoke real via `bin/otrs.Console.pl`/curl interno.
- **Portal:** e2e smoke abrir→listar→detalhe→responder (sidecar mockado); seletor de contrato
  some com 1 contrato e aparece com 2.
- **Stack Znuny base (`make test`, 24 asserts) continua verde** — `gerti` não quebra o núcleo.

## 6. Deploy (profile `gerti`, aditivo, padrão D13/D15/D19)

- Rebuild `znuny-web` (bakeia `GertiTicket.yml` + módulos GI + DynamicField idempotente) →
  recria `znuny-web`/`znuny-daemon` (downtime curto; provisionamento idempotente, D6).
- Import idempotente do webservice `GertiTicket` (guard: nunca remove auth/admin).
- Rebuild `sidecar` (traz `/v1/tickets*` e `/v1/ticketing*`; **sem migration nova** se o link
  já está na head) + rebuild `portal`.
- Verificação e2e em prod: abrir chamado real vinculado a contrato → conferir DynamicField no
  Znuny + linha em `ticket_contract_link` → limpar throwaway.
- Runbook novo em `OPS.md` + atualizar `ARCHITECTURE.md`/`INTEGRATION.md` (padrão voyager,
  mesmo PR).

## 7. Faseamento (4 fases sequenciais, cada uma com gate verde)

1. **Znuny GI** — `GertiTicket` (Create/Search/Get/Reply/FormMeta) + DynamicField + import
   idempotente. Provado com `bin/otrs.Console.pl`/curl interno.
2. **Sidecar** — cliente GI + `ticketing_service` + 6 endpoints + RLS/posse/papel + anexos.
   Gate pytest verde.
3. **Portal UI/UX** — as 3 telas, conduzidas pelo especialista `frontend-design`
   (form A, lista, detalhe). Aceite = clareza pro cliente final.
4. **Deploy + docs** — rebuild/up profile `gerti`, verificação e2e em prod, runbook + `.ia/`.

Fases 1 e 2 podem andar em paralelo até certo ponto (contrato de API combinado antes);
recomenda-se sequencial para manter o gate limpo.

## 8. Não-objetivos (explícitos)

- **Cobrança/consumo** (#1B) — próxima spec.
- Notas internas do agente, mudança de estado/SLA pela UI do cliente, satisfação/CSAT.
- Edição de contrato/ciclo/glosa pela UI (é #1G-b).
- Notificações por e-mail (já são do Znuny nativo; não mexemos).
