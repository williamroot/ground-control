# Spec #1J — Time Tracker do Agente: start/pause/stop no atendimento

**Data:** 2026-06-09
**Status:** aprovado (escopo travado no brainstorming) → pronto para plano/execução
**Escopo deste ciclo (#1J):** um **cronômetro por ticket** no Console de agente (apps/admin) com
**start / pause / resume / stop**. No **stop**, o tempo acumulado (com **ajuste opcional de
minutos + nota**) é **lançado** como uma linha `time_accounting` no Znuny via GI. A **cobrança
não é feita pelo botão** — o lançamento alimenta o **#1B**, que reconcilia → `consumption_event`
→ debita o saldo do contrato vinculado (assíncrono). Pipeline unificado: timer e tempo passivo
caem no mesmo `time_accounting`.
**Fora deste ciclo:** editar a UI nativa do Znuny; múltiplos lançamentos por sessão; relatórios
de produtividade do agente; auto-vincular contrato (o ticket precisa já ter vínculo #1E — a lista
avisa quando não tem).

## 1. Decisões (brainstorming 2026-06-09)

- **D-1J-1 (superfície):** o timer vive no **app de agente `apps/admin`** (autenticado por
  `gsid_adm`), **nas duas superfícies**: inline na **lista/busca de tickets** E em destaque no
  **detalhe do ticket**. NÃO integrar na UI nativa do Znuny (núcleo imutável).
- **D-1J-2 (concorrência):** **vários timers simultâneos** por agente (um por ticket). Sem
  auto-pause. A dupla contagem do relógio do agente é aceita (decisão do usuário).
- **D-1J-3 (commit):** pause/resume só **acumulam**. No **stop**, grava **UM** `time_accounting`
  com o total; antes de confirmar, o agente pode **ajustar os minutos** e adicionar uma **nota**.
- **D-1J-4 (lista de tickets):** busca em **todos os tickets** (qualquer fila/cliente), com
  filtro por número/assunto/cliente. Cada linha mostra o **contrato vinculado** (de
  `gerti.ticket_contract_link`) ou **⚠ sem contrato** (tempo não cobrável até vincular).
- **D-1J-5 (semântica do botão):** o stop **"Lança"** o tempo (escreve `time_accounting`). A
  **cobrança é downstream e automática** (#1B) — o botão não cobra nem promete cobrar na hora.
- **D-1J-6 (estado no servidor):** o estado do timer (running/paused, acumulado) vive em
  `gerti.agent_timer` — sobrevive a refresh/fechar aba; a UI calcula o display ticando a partir
  do estado do servidor.

## 2. Arquitetura

```
apps/admin (agente, gsid_adm)                 sidecar /v1/admin/*               znuny-web (GI GertiTicket)
  /atendimento: busca + timer inline ─proxy─► GET /admin/tickets (busca)  ──►  AgentTicketSearch (op nova)
  /atendimento/[id]: detalhe + timer  ─proxy─► GET /admin/tickets/{id}    ──►  AgentTicketGet (op nova)
  ▶ start / ⏸ pause / ⏵ resume / ⏹ stop ─proxy► POST /admin/timer/{start,pause,resume,stop}
                                                    │  (estado vivo)
                                                    ▼
                                           gerti.agent_timer (BYPASSRLS, agente)
                                                    │ no STOP (minutos ajustados + nota)
                                                    ▼
                                           GI TimeAccountingAdd (op nova) ──► TicketObject->TicketAccountTime
                                                                                (create_by = UserID do agente)
                                                    ⇣ depois (assíncrono)
                                           #1B reconcilia time_accounting → consumption_event → debita saldo
```

Princípios herdados: núcleo Znuny **imutável** (escrita de tempo embrulhando o nativo
`TicketAccountTime`; busca/leitura via GI); sessão de **agente** (`gsid_adm`, `get_admin_session`,
cross-tenant, BYPASSRLS, padrão #1G-a/D16); estado no servidor; **reusa o #1B sem alterá-lo** (o
timer só produz `time_accounting`); aditivo/profile-gated.

### 2.1 Znuny (`znuny/Custom/`) — 3 ops novas no webservice `GertiTicket`

(`AccessToken` fail-closed; `perl -c` no build é o gate; nenhum webservice novo.)

> **Token SEPARADO `GertiAgent::AccessToken` (review de segurança).** As 3 ops de
> agente são **mais poderosas** (root `UserID=>1`, cross-tenant, artigos internos)
> que as ops customer #1E. Por isso leem `GertiAgent::AccessToken` (env
> `ZNUNY_AGENT_WS_TOKEN`), **distinto** do token customer `GertiAdmin::AccessToken`
> (`ZNUNY_WS_TOKEN`) — um vazamento do token de fluxo-cliente não alcança as ops de
> agente. Erro de auth: `GertiAgent.AuthFail`. As demais ops `GertiTicket` (#1E)
> mantêm `GertiAdmin::AccessToken`.

| Op | Embrulha | Papel |
|---|---|---|
| `TimeAccountingAdd` | `Ticket::Article::ArticleCreate` (nota interna) + `Ticket::TicketAccountTime` (+ `User::UserLookup` p/ resolver UserID do `AgentLogin`) | Cria uma **nota interna de agente** (a partir da nota do stop) e lança 1 linha `time_accounting` **nesse artigo** (TimeUnit em minutos, `create_by`=UserID do agente) |
| `AgentTicketSearch` | `Ticket::TicketSearch` (sem escopo de customer) + `TicketGet` resumido | Busca cross-cliente p/ o agente (`Number`/`Title`/`CustomerID`/filtros) → lista resumida |
| `AgentTicketGet` | `TicketGet` + `Article*` (artigos visíveis) | Detalhe p/ o agente (sem a guarda de posse por CustomerID do #1E — agente é staff) |

> `TimeAccountingAdd` resolve o **UserID do Znuny** a partir do `AgentLogin` dentro do Perl
> (`$UserObject->UserLookup(UserLogin => ...)`), então o sidecar passa só o login (que já tem na
> sessão). Falha-fecha se o login não resolver. O nativo `TicketAccountTime` **exige** um
> `ArticleID` truthy — por isso a op cria primeiro uma nota interna (canal `Internal`,
> `SenderType=agent`, `IsVisibleForCustomer=0`, corpo = nota do stop) e contabiliza o tempo nela;
> retorna o `ArticleID` criado. Falha-fecha (`TimeAccountingAdd.ArticleError`) se o artigo não criar.

### 2.2 Sidecar (`apps/sidecar`)

- **Migration** `gerti.agent_timer` — tabela **operacional não-tenant** (acessada via
  AdminSessionLocal/BYPASSRLS; o agente é cross-tenant): `id` (uuid PK), `agent_login` (str),
  `znuny_ticket_id` (int), `status` (`running`|`paused`|`stopped`), `accumulated_seconds` (int,
  default 0), `last_started_at` (timestamptz, null quando pausado/parado), `note` (str null),
  `committed_time_unit` (numeric null — minutos lançados no stop), `created_at`, `updated_at`.
  Índice parcial único `(agent_login, znuny_ticket_id) WHERE status <> 'stopped'` → no máximo um
  timer ativo por (agente, ticket). **Sem** RLS por tenant.
- **`domain/timer_service.py`** (todo cálculo de tempo isolado e testável):
  - `start(agent_login, ticket_id)` → cria `running` (`last_started_at=now`); se já existe ativo
    p/ (agente,ticket), retorna o existente (idempotente).
  - `pause(timer_id)` → `accumulated += now - last_started_at`; `status=paused`; `last_started_at=NULL`.
  - `resume(timer_id)` → `status=running`; `last_started_at=now`.
  - `stop(timer_id, *, adjust_minutes=None, note=None)` → calcula total
    (`accumulated + (now - last_started_at se running)`); minutos = `adjust_minutes` se informado,
    senão `round(total_seconds/60, 2)`; chama `znuny_ticket.time_accounting_add(ticket_id,
    agent_login, minutes, note)`; marca `status=stopped`, `committed_time_unit=minutes`. **Só
    marca stopped após o GI confirmar** (sem lançamento perdido).
  - `elapsed_seconds(timer)` → helper puro p/ o display (servidor é a fonte; UI tica localmente).
- **Cliente GI** `integrations/znuny_ticket.py` (+3): `time_accounting_add(...)`,
  `agent_search(query, filters)`, `agent_get(ticket_id)`. Auth `AccessToken`; erros reusados.
- **Router** `routers/admin_timer.py` (todos `get_admin_session`):
  `POST /v1/admin/timer/start` · `/pause` · `/resume` · `/stop` · `GET /v1/admin/timer/active`
  (timers running/paused do agente, p/ o chip do header). E busca/detalhe de agente:
  `GET /v1/admin/tickets?q=&...` · `GET /v1/admin/tickets/{id}` (chama o GI + junta o contrato
  vinculado de `gerti.ticket_contract_link` por ticket, BYPASSRLS, p/ mostrar/avisar).

### 2.3 App admin (`apps/admin`)

- **`pages/atendimento/index.vue`** — busca + lista com **timer inline** por linha (estado
  running/paused/idle; cronômetro ticando via `setInterval` a partir do estado do servidor;
  contrato vinculado ou ⚠ sem contrato); chip **"timers ativos"** no header (de `/timer/active`).
- **`pages/atendimento/[id].vue`** — detalhe do ticket com **card de timer em destaque** + thread
  de artigos + diálogo de **stop** (ajuste de minutos + nota → **"Lançar"**).
- Composable `useTimers` (estado dos timers do agente + tick), server proxies
  `server/api/admin/timer/*` e `server/api/admin/tickets*` (repassam `gsid_adm`). Nav do Console
  ganha "Atendimento". Cores semânticas nunca usam a cor de marca (H8).

## 3. Segurança / invariantes

- Endpoints sob `get_admin_session` (agente Znuny, `typ:admin`/`gerti_staff`); cookie `gsid_adm`
  distinto do cliente — um `gsid` de cliente nunca acessa `/v1/admin/*` (isolamento já provado).
- O timer é **agente-escopo**, cross-tenant → caminho **admin/BYPASSRLS** (D16); o `agent_timer`
  não tem RLS por tenant. A leitura do contrato vinculado (`ticket_contract_link`) é BYPASSRLS
  só para exibir/avisar (read-only).
- Toda escrita/leitura de ticket/tempo no Znuny via **GI** (Spec #0) — zero SQL direto no schema
  znuny a partir do sidecar (grep-guard de teste). `TimeAccountingAdd` resolve UserID e falha-fecha.
- **Token de agente separado.** As 3 ops de agente (`TimeAccountingAdd`/`AgentTicketSearch`/
  `AgentTicketGet`) usam `GertiAgent::AccessToken` (env `ZNUNY_AGENT_WS_TOKEN`), **distinto** do
  token customer `GertiAdmin::AccessToken` (`ZNUNY_WS_TOKEN`) das ops #1E. Como são mais poderosas
  (root `UserID=>1`, cross-tenant, artigos internos), um vazamento do token de fluxo-cliente **não**
  alcança as ops de agente. O sidecar POSTa essas 3 com `_post_agent` (lê `ZNUNY_AGENT_WS_TOKEN`).
- `TimeAccountingAdd` cria uma **nota interna** (`IsVisibleForCustomer=0`, a partir da nota do stop)
  e contabiliza o tempo **nesse artigo** — o nativo `TicketAccountTime` exige `ArticleID` truthy.
- O stop só persiste `stopped` **após** o GI confirmar o lançamento — sem tempo perdido nem
  lançamento duplicado (um timer `stopped` não relança).

## 4. Dados

- **Nova:** migration `gerti.agent_timer` (operacional, não-tenant, índice parcial único de ativo).
- **Reuso sem alteração:** `time_accounting` (Znuny, via GI), `gerti.ticket_contract_link`,
  e todo o #1B (`reconciliation_service`, `consumption_event`, `balance()`).

## 5. Testes (zero-tolerância)

- **Sidecar (pytest):** `timer_service` — start idempotente; pause acumula; resume; stop calcula
  total e usa `adjust_minutes` quando dado; stop só marca `stopped` após o GI (mock) confirmar;
  GI falha → timer continua não-parado (sem perda); cálculo de `elapsed_seconds`. Router: auth
  (401 sem `gsid_adm`), start/pause/resume/stop, `/timer/active`. Busca/detalhe de agente (GI
  mockado) + junção do contrato vinculado. Grep-guard: sem SQL direto no schema znuny.
- **Znuny:** `perl -c` das 3 ops no build; smoke vivo (`TimeAccountingAdd` cria a linha;
  `AgentTicketSearch`/`AgentTicketGet` retornam).
- **App admin (vitest):** lógica do tick/estado do timer; render dos 3 estados da linha; o
  diálogo de stop manda `adjust_minutes`/`note`.
- **Stack base (`make test`, 24) e a suíte sidecar atual continuam verdes.**

## 6. Deploy (profile `gerti`, aditivo, padrão D13)

Rebuild `znuny-web` (3 ops novas; perl -c) + recria; **Update** do webservice `GertiTicket`
(`Admin::WebService::Update --webservice-id` — já corrigido no #1B); `sidecar-migrate` aplica a
migration `agent_timer`; rebuild `sidecar`; rebuild `admin`. **e2e em prod:** logar como agente
(`gsid_adm`) → buscar um ticket Aurora vinculado → start → (esperar) → stop com ajuste → conferir
a linha `time_accounting` (via GI/DB) → aguardar/forçar o worker #1B → **saldo debitado** →
limpar throwaway. Runbook em `OPS.md` + `ARCHITECTURE`/`INTEGRATION` no mesmo PR.
Rollback: `$DC stop admin` (UI some) e/ou reverter sha + rebuild. **NUNCA** `make reset`.

## 7. Faseamento (4 fases sequenciais, gate verde cada)

1. **Znuny GI** — `TimeAccountingAdd` + `AgentTicketSearch` + `AgentTicketGet` (+ yml + Dockerfile + perl -c).
2. **Sidecar** — migration `agent_timer` + cliente GI (3) + `timer_service` + router `/v1/admin/timer/*`
   + busca/detalhe de agente (TDD).
3. **App admin** — `/atendimento` (lista+timer inline) + `/atendimento/[id]` (detalhe+timer) +
   composable/proxies/nav (conduzido com foco de UX).
4. **Deploy + docs + e2e** (local e prod).

## 8. Não-objetivos (explícitos)

- Edição da UI nativa do Znuny; múltiplos lançamentos por sessão (1 no stop); auto-vínculo de
  contrato; relatórios/produtividade do agente; faturamento (Spec #2); cobrança feita pelo botão
  (é #1B, assíncrona). Tempo em ticket sem contrato vinculado é lançado no Znuny mas não cobra até
  o vínculo existir (a UI avisa).
