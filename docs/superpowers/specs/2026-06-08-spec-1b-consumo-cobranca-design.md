# Spec #1B — Cobrança/consumo: tempo no Znuny → consumption_event → débito de saldo (+ fechamento de ciclo)

**Data:** 2026-06-08
**Status:** aprovado (escopo travado no brainstorming) → pronto para plano/execução
**Escopo deste ciclo (#1B):** fechar a ponte que falta — o tempo lançado pelo agente no Znuny
(TimeUnits) vira `gerti.consumption_event` no contrato vinculado (via `ticket_contract_link`,
populado pelo #1E), **debitando o saldo** já exibido no portal — **mais** o **fechamento
automático de ciclo** quando o período vence. Captura via **pull GI agendado** + um **worker
dedicado**. Reusa `ConsumptionService.record()`/`balance()` e `CycleService.close()` (#1C) sem
alterá-los.
**Fora deste ciclo:** invoice/fatura (Spec #2); UI de glosa/aprovação (#1G-b); escrever
`GertiBillingStatus`/`GertiBillableMinutes` de volta no ticket Znuny; tempo real (há lag do
intervalo do worker).

## 1. Decisões (brainstorming 2026-06-08)

- **D-1B-1 (escopo):** captura de consumo (tempo → débito de saldo) **+** fechamento automático
  de ciclo. Sem invoice/glosa-UI/write-back no Znuny.
- **D-1B-2 (mecanismo):** **pull via GI agendado** — o sidecar puxa os lançamentos de tempo do
  Znuny por uma op GI nova; um worker reconcilia em `consumption_event`. NÃO event-driven
  `.opm`/webhook (evita Perl HTTP+retry+DLQ frágil; reusa o padrão GI provado de #1E/#1G).
- **D-1B-3 (runner):** serviço compose dedicado **`sidecar-worker`** (mesma imagem do `sidecar`,
  `command` próprio, profile `gerti`), loop asyncio. Desacoplado do processo web; sem dep nova.
- **D-1B-4 (conversão):** registro **uniforme** — grava `consumption_event` para todo ticket
  vinculado com `billable_minutes = TimeUnit`. `balance()` (#1C, intocado) faz a matemática por
  tipo: hour_bank debita horas; `credit_brl`/`credit_shared` debitam BRL (`billable_amount_brl =
  round(minutos/60 × contract.unit_price_brl, 2)`, calculado no registro); `service_count`/
  `closed_value`/`saas_product` recebem o evento para histórico mas **não** têm o saldo afetado
  por tempo (o `balance()` já ignora tempo nesses).
- **D-1B-5 (fonte + idempotência):** fonte = tabela nativa `time_accounting` do Znuny (cada
  lançamento é uma linha imutável). Idempotência determinística:
  `webhook_event_id = uuid5(NS, f'znuny:timeaccounting:{id}')` → re-execução não duplica
  (`record()` já retorna o evento existente). Cursor de eficiência por `znuny_instance`.

## 2. Arquitetura

```
                    ┌──────────── sidecar-worker (NOVO, profile gerti) ────────────┐
                    │  loop asyncio (mesma imagem do sidecar, command próprio):     │
   znuny-web  ◄─────┤  • reconcile (a cada RECONCILE_INTERVAL_SECONDS, default 120):│
   time_accounting  │      GI TimeAccountingSince → consumption_event (idempotente) │
   (via GI AccessTok)│  • close-cycles (1×/dia): varre ciclos vencidos → close()    │
                    │  por-tenant (tenant_session_scope); try/except por iteração   │
                    └───────────────────────────────┬──────────────────────────────┘
                                                     ▼
                              gerti (RLS): consumption_event, contract_cycle, consumption_sync_cursor
                              ← balance() já debita por tipo (#1C, intocado)
```

Princípios herdados (não-negociáveis): núcleo Znuny **imutável** (lê tempo via **GI**, nunca
escreve; o SQL read-only de `time_accounting` vive dentro da op GI, não no sidecar); RLS
multi-tenant (escrita de evento sob `tenant_session_scope(tenant_id)`; leitura cross-tenant de
vínculos/contratos pelo caminho **admin/BYPASSRLS**, padrão D16); `ConsumptionService`/
`CycleService` reusados **sem mudança**; aditivo e **profile-gated `gerti`** (um `make up` da
stack Znuny não sobe o worker nem reconcilia nada).

### 2.1 Znuny (`znuny/Custom/`) — op GI `TimeAccountingSince`

Operação nova no webservice **`GertiTicket`** já existente (mesmo `AccessToken` fail-closed,
sem webservice novo): `Custom/Kernel/GenericInterface/Operation/GertiTicket/TimeAccountingSince.pm`
+ 1 entrada em `znuny/webservices/GertiTicket.yml` (rota `/TimeAccounting/Since`).

- **Leitura pura** da tabela nativa `time_accounting` (`id, ticket_id, article_id, time_unit,
  create_time`) via `Kernel::System::DB`, `WHERE id > SinceId ORDER BY id ASC LIMIT Limit`.
- `Request: { AccessToken, SinceId, Limit }` → `Response: { Entries:[{Id,TicketId,ArticleId,
  TimeUnit,Created}], MaxId }`.
- Não conhece contrato — o sidecar filtra os `TicketId` vinculados. `perl -c` no build é o gate.

### 2.2 Sidecar (`apps/sidecar`)

- **`integrations/znuny_ticket.py`** (+1): `time_accounting_since(since_id, limit) ->
  TimeAccountingPage(entries, max_id)`. Auth `AccessToken`; erros reusados (`ZnunyUnavailable`/
  `ZnunyWriteError`).
- **Migration** `gerti.consumption_sync_cursor` — tabela **operacional não-tenant** (acessada
  pelo caminho admin/BYPASSRLS, como `znuny_instance`): `znuny_instance_id` (PK/FK),
  `last_time_accounting_id` (bigint, default 0), `updated_at`. **Sem** policy de RLS por tenant.
- **`domain/reconciliation_service.py`** — `reconcile()`:
  1. lê o cursor (admin/BYPASSRLS);
  2. `time_accounting_since(since_id, limit)`;
  3. **leitura cross-tenant (BYPASSRLS):** resolve `TicketId`→`ticket_contract_link` e carrega o
     contrato (`type`, `unit_price_brl`, `tenant_id`); entradas sem vínculo são ignoradas;
  4. **escrita por tenant (RLS-subject):** agrupa por `tenant_id`, `tenant_session_scope` e
     `ConsumptionService.record(RecordConsumption(...))` com:
     `source_kind='ticket_work'`, `source_ref=f'znuny:article:{ArticleId}'`, `occurred_at=Created`,
     `recorded_by='worker:reconcile'`, `billable_minutes=TimeUnit`,
     `billable_amount_brl=round(minutos/60×unit_price_brl,2)` só p/ crédito (senão 0),
     `webhook_event_id=uuid5(NS, f'znuny:timeaccounting:{Id}')`;
  5. avança o cursor para o `max_id` processado (admin/BYPASSRLS).
- **`domain/cycle_closer.py`** — `close_due_cycles()`: leitura cross-tenant dos ciclos `open`
  com `period_end < hoje`; por tenant, `tenant_session_scope` + `CycleService.close(cycle_id)`
  (reuso #1C). Idempotente.
- **`jobs/worker.py`** — entrypoint do `sidecar-worker`: chama `init_db()`, então loop asyncio:
  `reconcile()` a cada `RECONCILE_INTERVAL_SECONDS` (default 120); `close_due_cycles()` 1×/dia
  (marca `last_close_run`). Cada iteração em try/except + log `structlog`; nunca derruba o processo.

**Premissa (a confirmar no e2e):** `time_unit` do Znuny está em **minutos**. Se a instalação usar
outra unidade, um fator configurável por env (`TIME_UNIT_TO_MINUTES`, default 1) corrige sem código.

### 2.3 Compose — serviço `sidecar-worker`

Mesma imagem `ground-control/sidecar`; `command: ["python","-m","gerti_sidecar.jobs.worker"]`;
redes `data`+`app`+`edge`; mesmos envs do `sidecar` (DATABASE_URL `gerti_sidecar` +
DATABASE_ADMIN_URL `gerti_admin_user` + `ZNUNY_*`); `restart: unless-stopped`; sem porta;
`profiles:["gerti"]`; `depends_on` postgres healthy + `sidecar-migrate` concluído.

## 3. Segurança / invariantes

- Worker reconcilia cross-tenant, mas **escreve** consumo sempre sob `tenant_session_scope`
  (RLS-subject) — as invariantes #1C valem. Leitura cross-tenant de vínculos/contratos/cursor
  só pelo caminho **admin (BYPASSRLS, D16)**.
- Toda leitura de tempo no Znuny via **GI** (Spec #0) — zero SQL direto no schema Znuny a partir
  do sidecar (o SQL read-only de `time_accounting` está na op GI, dentro do Znuny). Grep-guard de
  teste garante.
- Idempotência forte por `webhook_event_id` determinístico → reprocesso seguro; o cursor é só
  eficiência (correção não depende dele).
- `ConsumptionService`/`balance()`/`CycleService` **não são alterados** — a regra S3 de glosa e a
  matemática de saldo por tipo permanecem a fonte única.

## 4. Dados

- **Nova:** migration `gerti.consumption_sync_cursor` (operacional, não-tenant, sem RLS por tenant).
- **Reuso:** `consumption_event` (idempotência `webhook_event_id` UNIQUE já existe),
  `ticket_contract_link`, `contract`, `contract_cycle` — **sem alteração de schema**.

## 5. Testes (zero-tolerância)

- **Sidecar (pytest + testcontainers):** idempotência (re-run não duplica via uuid5); conversão
  por tipo (hour_bank → horas; crédito → `minutos/60×unit_price`; service_count/closed/saas não
  afetam saldo); ticket sem vínculo ignorado; isolamento RLS na escrita; avanço de cursor; GI
  mockado (`ZnunyUnavailable` não trava o lote, não avança cursor além do processado);
  `cycle_closer` (fecha vencidos, pula já-fechados, por tenant); cliente GI `time_accounting_since`
  (mock); grep-guard (sem SQL direto no schema znuny no sidecar).
- **Znuny:** `perl -c` da op no build; smoke vivo (lançar TimeUnits → a op retorna a linha).
- **Stack base (`make test`, 24) e a suíte sidecar atual continuam verdes.**

## 6. Deploy (profile `gerti`, aditivo, padrão D13)

Rebuild `znuny-web` (op GI nova + perl -c) + recria; import idempotente do `GertiTicket`
atualizado (`Admin::WebService::Add --name`, já corrigido em #1E); `sidecar-migrate` aplica a
migration do cursor; rebuild `sidecar`; **up do novo `sidecar-worker`**. Runbook em `OPS.md` +
`ARCHITECTURE`/`INTEGRATION` no mesmo PR. **e2e em prod:** lançar TimeUnits num ticket Aurora
vinculado → forçar/aguardar um ciclo do worker → conferir `consumption_event` + saldo debitado no
`/v1/dashboard`/detalhe do contrato → limpar throwaway. Rollback: `$DC stop sidecar-worker`
(reconciliação para; nada destrutivo); reverter sha + rebuild. **NUNCA** `make reset`.

## 7. Faseamento (4 fases sequenciais, gate verde cada)

1. **Znuny GI** — `TimeAccountingSince.pm` + entrada no `GertiTicket.yml` + perl -c no build.
2. **Sidecar domínio** — migration `consumption_sync_cursor` + cliente GI + `reconciliation_service`
   + `cycle_closer` (TDD, testcontainers).
3. **Worker** — `jobs/worker.py` + serviço compose `sidecar-worker`.
4. **Deploy + docs + e2e prod.**

## 8. Não-objetivos (explícitos)

- Invoice/fatura (Spec #2); UI de glosa/aprovação (#1G-b); write-back de `GertiBillingStatus`/
  `GertiBillableMinutes` no ticket Znuny; tempo real (event-driven `.opm`); franquia de
  deslocamento/`travel` (todo tempo entra como `ticket_work` neste corte); Celery/DLQ (o worker
  asyncio idempotente basta).
