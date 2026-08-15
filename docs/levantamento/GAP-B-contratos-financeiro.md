# GAP-B — Contratos e Financeiro (R3, R6, R15, R18a, R18b)

> Recorte: só R3, R6, R15, R18a, R18b. Base de código lida em 2026-08-15.
> HEAD real de migration: **`0026_worker_heartbeat`** (`apps/sidecar/alembic/versions/0026_worker_heartbeat.py:29-30`)
> — toda migration nova encadeia a partir daí.
> Suíte atual do sidecar: **486 funções de teste** em `apps/sidecar/tests/` (contagem por grep de `def test`).

---

## R3 — Tipos de contrato (catálogo FECHADO, sem contrato programável)

**Pedido (citação curta do Kleber):** "Livre, crédito, crédito compartilhado, limite de horas,
contrato de SaaS, contrato com limite de atendimento. […] A TIFLUX permite personalizar os
contratos, mas eu não acho legal isso aqui, cara. Acho que a plataforma tem que ter os modelos
e o contrato tem que funcionar conforme os fluxos estabelecidos na plataforma."
(transcrição linhas 44-48)

**Estado atual:** **PARCIAL**

O catálogo é de fato fechado em 4 camadas — esse é o ponto forte:

| Camada | Evidência |
|---|---|
| Enum nativo no Postgres (6 valores) | `apps/sidecar/alembic/versions/0004_contract_enums.py:20-27` |
| Enum Python espelhando o DB | `apps/sidecar/src/gerti_sidecar/models/enums.py:8-14` |
| Coluna com o tipo nativo (sem texto livre) | `apps/sidecar/src/gerti_sidecar/models/contract.py:27,50` |
| Contrato Pydantic `Literal` na API | `apps/sidecar/src/gerti_sidecar/routers/admin_contracts.py:29-36`, conversão em `:95` |
| Campo inicial obrigatório por tipo | `apps/sidecar/src/gerti_sidecar/domain/contract_service.py:36-43,60-62` |
| UI espelha os 6 tipos, sem campo livre | `apps/admin/shared/contracts.ts:5-30,90-103` · `apps/admin/pages/clientes/[id]/contratos/novo.vue:14` |
| Teste de valores do enum | `apps/sidecar/tests/test_enums.py:11-19` |
| Teste por tipo (6 casos parametrizados) | `apps/sidecar/tests/test_admin_contracts.py:95-114` |

**Mapa tipo a tipo (o que Kleber citou × o que existe):**

| Kleber | Código | Estado | Evidência |
|---|---|---|---|
| crédito | `credit_brl` | **existe e funciona** (saldo em R$ debita) | `consumption_service.py:113-115` · `reconciliation_service.py:32,121-124` |
| limite de horas | `hour_bank` | **existe e funciona** (saldo em horas; franquia + overage no fechamento) | `consumption_service.py:110-112` · `cycle_service.py:61-71` |
| SaaS | `saas_product` | **existe como rótulo**, sem comportamento: saldo `n/a` e **nenhuma cobrança recorrente do valor fixo** | `consumption_service.py:119` · `invoice_service.py:100-160` (só soma consumo) |
| crédito compartilhado | `credit_shared` | **nome existe, comportamento NÃO**: o saldo é calculado sobre `contract.initial_amount_brl`, ignorando o pool | `consumption_service.py:113-115`; `Contract.shared_pool_id` (`models/contract.py:75-77`) e `SharedCreditPool` (`models/catalog.py:54-70`) **sem nenhum leitor** no domínio (grep em `src/` → só models/migrations) |
| contrato com limite de atendimento | `service_count` | **nome existe, nunca consome**: o saldo conta eventos com `source_kind == "service_item"`, e o único produtor de eventos grava `"ticket_work"` | `consumption_service.py:103-109` × `reconciliation_service.py:135` |
| **livre** | — | **AUSENTE**: não há tipo pós-pago/sem-saldo que fature hora a hora. `closed_value` é "valor fechado" (saldo `n/a`), não "livre" | `enums.py:8-14` · `consumption_service.py:119` · `apps/admin/shared/contracts.ts:27` (rótulo "Valor fechado") |
| (intercâmbio — custom do Kleber) | — | fora do catálogo por decisão de produto dele mesmo; **mas a Gerti usa hoje** → decisão aberta | transcrição linha 46 |

Faltando ainda: **não existe teste-guarda de catálogo fechado**. `tests/test_admin_contracts.py`
exercita os 6 tipos válidos; nenhum caso com `type` desconhecido.

**Gap (comportamento observável que falta):**
1. Um contrato `credit_shared` de dois contratos irmãos consome saldos separados — não há pool comum.
2. Um contrato `service_count` nunca perde saldo, por mais atendimentos que receba.
3. Não existe o tipo "livre" (pós-pago por hora, sem saldo) que o Kleber cita primeiro.
4. `POST .../contracts` com `type:"intercambio"` hoje responde 422 pelo `Literal` — mas isso não está provado por teste; uma refatoração para `str` passaria despercebida.

**Tarefas:**
- **T-R3.1 — Provar que o catálogo é fechado (teste-guarda, sem código novo de produção).**
  Camada: testes. Arquivos: `apps/sidecar/tests/test_admin_contracts.py`, `apps/sidecar/tests/test_enums.py`.
  Pronto quando: um `type` fora dos 6 devolve 422 no router; `ContractType("intercambio")` levanta `ValueError`;
  e o teste falha se alguém trocar o `Literal` de `admin_contracts.py:29-36` por `str`.
- **T-R3.2 — Ligar `credit_shared` ao pool compartilhado.**
  Camada: domínio. Arquivos: `apps/sidecar/src/gerti_sidecar/domain/consumption_service.py` (`balance`),
  `domain/contract_read_service.py` (`_initial_for`, `low_balance`), `routers/admin_contracts.py` (aceitar `shared_pool_id`),
  migration nova a partir de `0026` só se for preciso índice/constraint.
  Pronto quando: dois contratos apontando para o mesmo `shared_pool_id` compartilham um saldo único; consumo em um reduz o saldo exibido no outro.
- **T-R3.3 — Fazer `service_count` consumir de verdade.**
  Camada: domínio + worker. Arquivos: `domain/reconciliation_service.py` (classificar `source_kind` por tipo de contrato),
  `domain/consumption_service.py:103-109`.
  Pronto quando: um atendimento lançado num contrato `service_count` reduz o saldo em 1 serviço.
- **T-R3.4 — Decidir e (se aprovado) introduzir o tipo "livre".**
  Camada: modelo + domínio + UI. Arquivos: `alembic/versions/0027_*.py` (`ALTER TYPE gerti.contract_type ADD VALUE`),
  `models/enums.py`, `domain/contract_service.py:36-43`, `routers/admin_contracts.py:29-36`,
  `apps/admin/shared/contracts.ts`.
  Pronto quando: contrato "livre" aceita `unit_price_brl` sem campo inicial de saldo, acumula consumo faturável e nunca dispara alerta de saldo baixo.

**Testes de validação:**
- **V-R3.1 (pytest, guarda de catálogo fechado)** — `apps/sidecar/tests/test_admin_contracts.py`:
  `POST /v1/admin/tenants/{id}/contracts` com `{"type": "intercambio", ...}` (sessão `gsid_adm` válida) → **422**,
  e `SELECT count(*) FROM gerti.contract` inalterado. Complemento em `tests/test_enums.py`:
  `pytest.raises(ValueError): ContractType("intercambio")` e `set(ContractType) == {closed_value, credit_brl, credit_shared, hour_bank, saas_product, service_count}` (falha se alguém acrescentar tipo sem migration).
- **V-R3.2 (pytest, pool compartilhado)** — `apps/sidecar/tests/test_consumption_service.py`:
  pool R$ 1.000 + contratos A e B com o mesmo `shared_pool_id`; consumo de R$ 300 em A →
  `balance(A).remaining == 700.0` **e** `balance(B).remaining == 700.0` (hoje daria 1000 em B).
- **V-R3.3 (pytest, service_count)** — `apps/sidecar/tests/test_consumption_service.py`:
  contrato `service_count` com `initial_service_count=10`; 2 atendimentos reconciliados →
  `balance(c).kind == "services"` e `remaining == 8.0`.
- **V-R3.4 (vitest, UI não abre exceção)** — `apps/admin/test/` (arquivo novo `contract-types.test.ts`):
  `CONTRACT_TYPES` de `apps/admin/shared/contracts.ts` tem exatamente os mesmos valores do `Literal` do sidecar
  (lista hardcoded no teste) e `typeLabel('intercambio') === 'intercambio'` (fallback, nunca cria tipo).

**Risco/decisão aberta:**
- "Livre" e "intercâmbio" precisam de decisão do Kleber **antes** de virar enum: `ALTER TYPE … ADD VALUE`
  é irreversível na prática (não há `DROP VALUE` no Postgres) e cada novo valor amplia o catálogo que ele
  quis manter fechado. Sugestão: mapear "intercâmbio" para um dos 6 e documentar.
- `credit_shared` com pool cross-tenant é impossível sob RLS (`SharedCreditPool.tenant_id` NOT NULL,
  `models/catalog.py:60-62`): confirmar que "compartilhado" é entre contratos **do mesmo cliente**, não entre clientes.

---

## R6 — Configuração de faturamento por cliente (SMS / e-mail com detalhamento / integração financeira)

**Pedido (citação curta do Kleber):** "E aí a parte de faturamento do cliente, que são algumas
configurações pra enviar SMS, pra enviar e-mail, né? Com detalhamento. Se tiver integração com
sistemas financeiros, aparece aqui." (transcrição linhas 66-68)

**Estado atual:** **AUSENTE** (existem fragmentos reaproveitáveis, nada do requisito)

- **Não há configuração de faturamento por cliente.** `Tenant` não tem nenhum campo de faturamento
  (`apps/sidecar/src/gerti_sidecar/models/tenant.py:15-39`) e não existe tabela `*_billing_config`
  em nenhuma das 26 migrations (`apps/sidecar/alembic/versions/`).
- **Não existe canal de entrega de e-mail nem de SMS no sidecar.** Grep por `smtp|SMTP|twilio|sendgrid|send_email|sms`
  em `apps/sidecar/src/` → **zero ocorrências**. As notificações são in-app apenas
  (`apps/sidecar/src/gerti_sidecar/models/notification.py:1-10,35-60`), com o kind `invoice_issued`
  (`models/notification.py:24-32`) emitido em `domain/invoice_service.py:174-195` — grava linha em `gerti.notification`,
  não envia nada.
- **Preferências existem, mas no escopo errado e sem efeito.** `email_notifications`, `invoice_alerts`,
  `weekly_report` são por **usuário do portal** (`models/user_preference.py:47-62`), não por cliente,
  e só têm CRUD (`routers/preferences.py:26-52`); nenhum consumidor lê essas flags para enviar algo (grep).
- **Integração financeira existe, mas só no checkout de contratação.** Asaas cobre venda self-service
  (`models/contratacao.py:31,56,92,137`, `routers/checkout.py`, `routers/asaas_hooks.py`,
  `integrations/asaas_client.py`), gateado por `asaas_enabled` (`config.py:80-85`). `Payment.invoice_id`
  é nullable e **nunca é preenchido a partir de uma fatura de ciclo** (`models/contratacao.py:163-164`);
  não há toggle nem conta financeira por cliente na ficha do cliente
  (`apps/admin/pages/clientes/[id]/index.vue` não tem aba de faturamento).

**Gap:** na ficha do cliente do console não existe aba "Faturamento"; não é possível dizer
"este cliente recebe a fatura por e-mail com detalhamento e um SMS de aviso"; nem escolher se a
cobrança vai para o Asaas. Nada disso é configurável nem executável hoje.

**Tarefas:**
- **T-R6.1 — Modelar `gerti.tenant_billing_config` (1:1 com tenant, tenant-scoped).**
  Camada: modelo + migration. Arquivos: `apps/sidecar/alembic/versions/0027_tenant_billing_config.py`
  (down_revision `0026_worker_heartbeat`), `src/gerti_sidecar/models/tenant_billing_config.py`, `models/__init__.py`.
  Campos mínimos: `email_enabled`, `email_recipients` (lista validada), `email_detail_level`
  (`summary|detailed`), `sms_enabled`, `sms_recipients`, `provider` (`none|asaas`), `provider_account_id`,
  `due_days`. Segue literalmente o padrão de `alembic/versions/0017_invoice.py`: `ENABLE` + `FORCE ROW LEVEL SECURITY` + policy `tenant_id = current_setting('app.current_tenant')::uuid` na própria migration.
  Pronto quando: `tests/test_rls_contract_tables.py` (mesmo molde) prova isolamento cross-tenant da tabela nova.
- **T-R6.2 — Serviço + endpoints de configuração.**
  Camada: domínio + router. Arquivos: `domain/billing_config_service.py`,
  `routers/admin_billing_config.py` (`GET|PUT /v1/admin/tenants/{id}/billing-config`, `get_admin_session`),
  registro em `main.py`, auditoria via `audit_service.record` (molde `routers/admin_branding.py`).
  Pronto quando: 200 no GET com defaults seguros (tudo desligado), 422 em e-mail inválido, 404 em tenant inexistente, linha em `audit_log` no PUT.
- **T-R6.3 — Canal de entrega de e-mail (adapter isolado, feature-flag).**
  Camada: integrações + domínio. Arquivos: `integrations/mailer.py` (molde de `integrations/ollama.py`:
  transport injetável, erro tipado), `config.py` (`SMTP_*`, `BILLING_NOTIFICATIONS_ENABLED=False` por default),
  `domain/invoice_service.py` (ponto de emissão já existente em `:174-195`).
  Pronto quando: com flag off nada é enviado; com flag on, emitir fatura dispara 1 e-mail com o PDF anexado
  para os destinatários da config; falha do SMTP **não** derruba a emissão (best-effort, igual ao `try/except` de `:165-171`).
- **T-R6.4 — SMS: decidir provedor e implementar atrás da mesma interface.** (bloqueada por decisão comercial)
  Camada: integrações. Arquivos: `integrations/sms.py`, `config.py`.
  Pronto quando: `sms_enabled=true` gera 1 envio curto ("Fatura #0012 disponível — R$ 1.234,56, vence 30/08"), sem valores sensíveis além disso.
- **T-R6.5 — Aba "Faturamento" na ficha do cliente.**
  Camada: UI. Arquivos: `apps/admin/pages/clientes/[id]/faturamento.vue`, proxy em
  `apps/admin/server/api/admin/tenants/[id]/billing-config.{get,put}.ts`, link em `apps/admin/pages/clientes/[id]/index.vue`.
  Pronto quando: o operador liga/desliga e-mail e SMS, escolhe detalhamento e o provedor financeiro, e a tela reflete o estado salvo após reload.

**Testes de validação:**
- **V-R6.1 (pytest, RLS)** — `apps/sidecar/tests/test_rls_contract_tables.py`:
  linha de `tenant_billing_config` do tenant A é invisível numa sessão com `app.current_tenant = B`
  (`SELECT count(*) == 0`) rodando sob o papel **sem** BYPASSRLS.
- **V-R6.2 (pytest, contrato de API)** — `apps/sidecar/tests/test_admin_billing_config_router.py` (novo):
  `PUT` com `{"email_enabled": true, "email_recipients": ["nao-e-email"]}` → **422** com mensagem citando o campo;
  `PUT` válido → **200** e `GET` subsequente devolve exatamente o que foi gravado; `gsid` de cliente em `/v1/admin/*` → **401**.
- **V-R6.3 (pytest, entrega de e-mail com flag)** — `apps/sidecar/tests/test_invoice_notification_producer.py`
  (estende o arquivo existente): com `BILLING_NOTIFICATIONS_ENABLED=False`, `create_from_cycle` → mailer fake
  recebe **0** chamadas; com `True` e `email_enabled=true`, recebe **1** chamada cujo anexo começa com `b"%PDF-"`;
  mailer que levanta exceção → a fatura **continua gravada** (`invoice.number == 1`).
- **V-R6.4 (vitest, UI)** — `apps/admin/test/billing-config.test.ts` (novo): helper puro de normalização de
  destinatários — `["a@b.com", " ", "a@b.com"]` → `["a@b.com"]` (dedupe + trim + descarte de vazio).
- **V-R6.5 (manual, staging)** — ligar e-mail para o tenant Aurora, emitir uma fatura, confirmar chegada
  com PDF anexado; desligar, emitir outra, confirmar que nada chega.

**Risco/decisão aberta:**
- Quem envia o e-mail: o **Znuny** (já tem MTA configurado e é o dono da comunicação com o cliente)
  ou o **sidecar** (dono da fatura)? Enviar pelo Znuny respeitaria a invariante do R9 ("sai pela mesma
  fila que entrou") mas exigiria op GI nova; enviar pelo sidecar é mais simples e não toca o núcleo.
  **Recomendo o sidecar** — a fatura não pertence a nenhuma fila de atendimento.
- SMS tem custo por mensagem e provedor não escolhido — manter T-R6.4 atrás de flag e fora do MVP.
- "Detalhamento" precisa de definição: é o PDF anexado, o corpo do e-mail com as linhas, ou link para o portal?

---

## R15 — Financeiro global (tipos de contrato, serviços avulsos, valores extras)

**Pedido (citação curta do Kleber):** "E aqui a parte financeiro, né? Que são lá os tipos de contrato,
os serviços avulsos, se forem cadastrados aqui, quanto que a gente cobra por hora, tal. Para quando o
cliente não tem contrato, entrou um serviço avulso, a gente bilheta também aquele cliente e manda nota
fiscal e boleto por atendimento. E valores extras, caso a gente tenha aqui valor de deslocamento […]"
(transcrição linhas 134-137)

**Estado atual:** **AUSENTE** (a peça de fatura existe; o caso de uso do Kleber não)

- **Cliente sem contrato não consegue nem abrir chamado**, quanto mais ser cobrado:
  `apps/sidecar/src/gerti_sidecar/domain/ticketing_service.py:62-76` levanta `NoActiveContract`
  quando `len(active) == 0`.
- **Todo o modelo financeiro é contrato-obrigatório:** `ConsumptionEvent.contract_id` é
  `nullable=False` (`models/consumption.py:33-35`) e `Invoice.contract_id` idem
  (`models/invoice.py:53-55`). Cobrança avulsa é **estruturalmente impossível** hoje, não é só "falta tela".
- **Catálogo de serviços com preço existe no schema e está morto.** `gerti.service_catalog_item` tem
  `unit_price_brl` e `tenant_id` **nullable** (linhas globais) — `models/catalog.py:28-51` — e a policy RLS
  já libera as linhas globais para qualquer tenant (`alembic/versions/0006_catalog_scope.py:151-176`).
  **Nenhum service/router lê ou escreve essa tabela** (grep em `src/` fora de `models/`: 0 hits;
  as ocorrências em `routers/admin_catalog.py:148,208,241` são só a string de auditoria do catálogo do
  Spec #3, que é outra tabela — `models/catalog_item.py:63-83`, **sem campo de preço**).
- **Deslocamento é meia-implementação:** existe `Contract.travel_franchise_count`
  (`models/contract.py:63`, exposto na UI em `apps/admin/pages/clientes/[id]/contratos/novo.vue:140-141`)
  e o rótulo/unidade `travel` na fatura (`domain/invoice_service.py:49,55`), mas
  **nenhum produtor de evento `travel`**: o único caminho de consumo grava `source_kind="ticket_work"`
  (`domain/reconciliation_service.py:135`), e não há endpoint de lançamento manual de consumo
  (nenhum `POST` de consumo em `src/gerti_sidecar/routers/`).
- **NF/boleto por atendimento não existe:** a fatura é declaradamente **não fiscal**
  (`templates/invoice.html:10` e `domain/invoice_pdf.py:156` — "Documento interno — não é nota fiscal");
  o Asaas só é acionado no checkout de contratação, nunca a partir de `gerti.invoice`.
- **Bug financeiro adjacente (relevante ao R15):** a fatura **ignora o overage do ciclo**.
  `InvoiceService.create_from_cycle` soma `billable_amount_brl` dos eventos
  (`domain/invoice_service.py:100-106,134-160`), e o worker só preenche esse campo para tipos de crédito
  (`domain/reconciliation_service.py:32,121-124`). Enquanto isso, `CycleService.close` calcula
  `overage_amount_brl` e o guarda em `cycle.totals` (`domain/cycle_service.py:66-71,77-85`) —
  e **ninguém lê**. Resultado observável: fatura de contrato `hour_bank`, `closed_value` ou
  `saas_product` sai com **R$ 0,00**, mesmo com horas excedentes ou mensalidade fixa contratada.

**Gap:** (a) não existe catálogo global de serviços avulsos com valor-hora; (b) não existe cobrança
para cliente sem contrato; (c) não existe lançamento de valor extra (deslocamento) por atendimento;
(d) contratos de valor fixo e banco de horas faturam zero.

**Tarefas:**
- **T-R15.1 — Reanimar o catálogo global de serviços avulsos (preço por hora / por serviço).**
  Camada: domínio + router + UI. Arquivos: `domain/billing_catalog_service.py` (novo, sobre a tabela
  **já existente** `gerti.service_catalog_item`), `routers/admin_billing_catalog.py`
  (`GET|POST|PUT /v1/admin/billing/services`, `get_admin_session`), `main.py`,
  `apps/admin/pages/financeiro/servicos.vue`.
  Pronto quando: o operador cadastra "Hora técnica avulsa — R$ 220/h" como linha global
  (`tenant_id IS NULL`) e ela aparece para todos os tenants.
- **T-R15.2 — Permitir consumo e fatura sem contrato (cobrança avulsa).**
  Camada: modelo + domínio. Arquivos: `alembic/versions/0028_avulso.py` (tornar
  `consumption_event.contract_id` e `invoice.contract_id` nullable + `CHECK` de que ao menos um de
  contrato/serviço está presente; RLS já vigente nas duas tabelas), `models/consumption.py:33-35`,
  `models/invoice.py:53-55`, `domain/consumption_service.py:53-70`, `domain/invoice_service.py`
  (novo `create_adhoc(...)`), `domain/ticketing_service.py:62-76` (permitir abrir chamado sem contrato
  quando o tenant estiver marcado como avulso).
  Pronto quando: um tenant sem nenhum contrato ativo abre chamado, o tempo lançado vira
  `consumption_event` avulso precificado pelo catálogo, e é possível emitir fatura por atendimento.
- **T-R15.3 — Lançamento de valores extras (deslocamento) por atendimento.**
  Camada: domínio + router + UI. Arquivos: `domain/consumption_service.py` (`record` já aceita
  `source_kind` livre — `:22,59`), `routers/admin_extras.py`
  (`POST /v1/admin/tenants/{id}/consumption/extras`, `get_admin_session`),
  `apps/admin/pages/atendimento/[id].vue` (botão "Lançar deslocamento" ao lado do timer).
  Pronto quando: lançar 1 deslocamento gera evento `source_kind="travel"` que aparece como linha
  "Deslocamento" na próxima fatura (o rótulo já existe em `invoice_service.py:49,55`), respeitando
  `travel_franchise_count` do contrato (`models/contract.py:63`).
- **T-R15.4 — Fazer a fatura refletir mensalidade fixa e overage.**
  Camada: domínio. Arquivos: `domain/invoice_service.py:100-160` (ler `cycle.totals` e o tipo do contrato),
  eventualmente `domain/cycle_service.py`.
  Pronto quando: fatura de `saas_product`/`closed_value` traz linha de mensalidade com o valor contratado,
  e fatura de `hour_bank` traz linha de excedente = `overage_amount_brl` do ciclo.
- **T-R15.5 — NF/boleto por atendimento (integração fiscal/cobrança).** (depende de T-R6.1)
  Camada: integrações + domínio. Arquivos: `domain/invoice_service.py`, `integrations/asaas_client.py:138+`
  (cobrança avulsa já existe no cliente), `models/contratacao.py:163-164` (`payment.invoice_id`).
  Pronto quando: emitir fatura com `provider="asaas"` cria a cobrança e grava `payment.invoice_id`;
  NF-e fica explicitamente **fora** do escopo até haver emissor definido.

**Testes de validação:**
- **V-R15.1 (pytest, cliente SEM contrato ainda gera cobrança — assert central do R15)** —
  `apps/sidecar/tests/test_invoice_service.py`: tenant com **zero** linhas em `gerti.contract`;
  registrar consumo avulso de 90 min a R$ 200/h → `create_adhoc(...)` devolve fatura com
  `contract_id is None`, `total_cents == 30000` e 1 linha com `unit == "h"` e `quantity == 1.50`.
- **V-R15.2 (pytest, abertura de chamado sem contrato)** — `apps/sidecar/tests/test_ticketing_service.py`:
  tenant sem contrato ativo e modo avulso ligado → `open_ticket(...)` **não** levanta `NoActiveContract`
  e retorna `contract_id is None` (hoje o mesmo cenário dá 404 via `ticketing_service.py:74`).
- **V-R15.3 (pytest, deslocamento)** — `apps/sidecar/tests/test_invoice_service.py`:
  ciclo com 2h de `ticket_work` + 1 evento `travel` de R$ 80 → a fatura tem **2** linhas e uma delas
  tem `description == "Deslocamento"` e `amount_cents == 8000`.
- **V-R15.4 (pytest, fatura não sai zerada)** — `apps/sidecar/tests/test_invoice_service.py`:
  contrato `hour_bank` com franquia de 10h e 12h consumidas, `unit_price_brl = 200` →
  `total_cents == 40000` (2h de excedente). **Hoje esse mesmo cenário dá `total_cents == 0`.**
- **V-R15.5 (pytest, catálogo global visível a todos)** — `apps/sidecar/tests/test_rls_contract_tables.py`:
  linha de `service_catalog_item` com `tenant_id IS NULL` é lida por sessões dos tenants A **e** B;
  linha com `tenant_id = A` é invisível para B.

**Risco/decisão aberta:**
- Tornar `consumption_event.contract_id` nullable enfraquece uma invariante do #1C (todo consumo pertence
  a um contrato). Alternativa mais conservadora: criar um **contrato implícito do tipo "livre"** por cliente
  avulso (T-R3.4), preservando o modelo. **Essa alternativa é provavelmente melhor** e depende da decisão do R3.
- "Nota fiscal" real exige emissor (Focus NFe / eNotas / prefeitura) — não decidido; o boleto via Asaas
  é factível já.
- Precificação avulsa por cliente ("personalização de contrato para um cliente específico") colide com
  `contract_scope_service.unit_price_override` (`models/contract_scope.py:15-27`), que também está morto —
  reusar em vez de criar tabela nova.

---

## R18a — Gráfico de consumo por cliente (últimos 3 meses, unidade seguindo o tipo de contrato)

**Pedido (citação curta do Kleber):** "Se eu quero saber qual o consumo de cada cliente, eu venho aqui
e pego esse cara aqui e vejo nos últimos três meses qual foi o ciclo de utilização dele […]
Quando é contrato de hora, é hora, aparece em formato de hora. Quando é contrato de grana,
aparece em formato de grana." (transcrição linhas 160-164)

**Estado atual:** **PARCIAL** — a regra de unidade já existe e está certa; a janela e a superfície, não.

O que existe:
- `GET /v1/contracts/{id}/series` (`apps/sidecar/src/gerti_sidecar/routers/contracts.py:318-334`)
  sobre `ContractReadService.series` (`domain/contract_read_service.py:100-165`).
- **A unidade já segue o tipo de contrato**, exatamente como o Kleber pede
  (`domain/contract_read_service.py:117-130`): `hour_bank` → `kind="hours"` com
  `sum(billable_minutes)/60`; `credit_brl`/`credit_shared` → `kind="brl"` com `sum(billable_amount_brl)`;
  `service_count` → `kind="services"` (contagem); `closed_value`/`saas_product` → `kind="n/a"` e série vazia.
  Confirmado por teste: `apps/sidecar/tests/test_contract_series_router.py:113` (`body["kind"] == "hours"`).
- Regra de glosa S3 centralizada e aplicada à série (`domain/contract_read_service.py:26-37,143`).
- Gráfico renderizado no portal do cliente: `apps/portal/pages/contratos/[id].vue:39-40,106-108`
  (`AreaChart`), oculto quando `kind === 'n/a'`.

O que falta:
- **Janela errada.** A série cobre a **vida inteira do contrato** (`starts_on` até `min(ends_on, today)`
  — `domain/contract_read_service.py:108-116`), com degradação automática dia→semana acima de 400 buckets.
  Não existe "últimos 3 meses" nem agregação **por ciclo** ("ciclo de utilização"), embora
  `contract_cycle.totals` já guarde o fechado por ciclo (`domain/cycle_service.py:77-85`).
- **Superfície errada.** O endpoint é do **portal** e exige `require_admin` sobre o cookie de cliente
  (`routers/contracts.py:32`). O Kleber é agente da Gerti (cookie `gsid_adm`) e olha **por cliente,
  escolhendo na lista**. No console não há nada disso: `routers/admin_analytics.py:31-56` devolve
  tickets/CSAT/horas/saldo, **sem série de consumo**, e a página `apps/admin/pages/analytics/index.vue:164-179`
  só tem volume de chamados, estado e CSAT. Não existe nenhuma rota `/v1/admin/**/series` (grep: `series`
  aparece só em `routers/contracts.py` e `domain/contract_read_service.py`).
- **Sem visão por cliente agregada**: um cliente com 3 contratos não tem um gráfico só; a série é por contrato.

**Gap:** o agente Gerti não consegue selecionar um cliente e ver o consumo dos últimos 3 meses
na unidade do contrato — precisa entrar no portal do cliente, contrato a contrato, e olhar a vida inteira.

**Tarefas:**
- **T-R18a.1 — Janela por período no serviço de leitura.**
  Camada: domínio. Arquivos: `domain/contract_read_service.py:100-165` (parâmetros `months: int = 3` /
  granularidade `month`, mantendo o cap de 400 buckets e a regra S3 intacta).
  Pronto quando: `series(contract, months=3, granularity="month")` devolve exatamente 3 pontos mensais
  zero-filled, sem mudar o `kind`.
- **T-R18a.2 — Endpoint de consumo por cliente no console.**
  Camada: router. Arquivos: `routers/admin_analytics.py` (novo
  `GET /v1/admin/tenants/{id}/consumption-series?months=3`, `get_admin_session`, padrão D16:
  valida tenant via `AdminSessionLocal` e depois `tenant_session_scope(...)`), `main.py`.
  Pronto quando: devolve uma série por contrato ativo + `kind` de cada uma; tenant inexistente → 404;
  cookie `gsid` de cliente → 401.
- **T-R18a.3 — Gráfico no console, com seletor de cliente.**
  Camada: UI. Arquivos: `apps/admin/pages/analytics/index.vue` (bloco novo) ou
  `apps/admin/pages/clientes/[id]/consumo.vue`, proxy em `apps/admin/server/api/admin/tenants/[id]/consumption-series.get.ts`,
  reuso de `AreaChart`/`BarChart` já existentes.
  Pronto quando: o eixo/rótulo mostra **"h"** para contratos de hora e **"R$"** para contratos de crédito,
  nunca ambos misturados no mesmo gráfico.
- **T-R18a.4 — Série por ciclo (opcional, fiel a "ciclo de utilização").**
  Camada: domínio. Arquivos: `domain/contract_read_service.py`, lendo `contract_cycle.totals`
  (`domain/cycle_service.py:77-85`).
  Pronto quando: para um contrato com ciclos mensais fechados, os 3 pontos batem com
  `totals["consumed_minutes"]/60` de cada ciclo.

**Testes de validação:**
- **V-R18a.1 (pytest, UNIDADE — hour_bank devolve horas)** —
  `apps/sidecar/tests/test_contract_series_router.py`: contrato `hour_bank` com dois eventos de
  90 min e 30 min no mesmo mês → resposta com `kind == "hours"` e o ponto do mês valendo **2.0**
  (não 120). Assert explícito de que `sum(points) * 60 == sum(billable_minutes)`.
- **V-R18a.2 (pytest, UNIDADE — credit_brl devolve reais)** —
  mesmo arquivo: contrato `credit_brl` com eventos de R$ 300,00 e R$ 150,00 → `kind == "brl"` e
  ponto do mês valendo **450.0**; e o mesmo payload **não** contém minutos.
  Complemento negativo: contrato `saas_product` → `kind == "n/a"` e `points == []`.
- **V-R18a.3 (pytest, JANELA — exatamente 3 meses/ciclos)** —
  `apps/sidecar/tests/test_contract_read_service.py`: contrato iniciado há 12 meses, com consumo em
  M-5 e M-1; `series(..., months=3, today=2026-08-15)` → `len(points) == 3`,
  `points[0].bucket == date(2026,6,1)`, `points[-1].bucket == date(2026,8,1)`, e o consumo de M-5
  **não** aparece (assert de exclusão, não só de tamanho).
- **V-R18a.4 (pytest, autorização da nova rota)** —
  `apps/sidecar/tests/test_admin_analytics_router.py`: `GET /v1/admin/tenants/{id}/consumption-series`
  sem `gsid_adm` → **401**; com `gsid` de cliente → **401**; tenant inexistente → **404**.
- **V-R18a.5 (vitest, rótulo de unidade na UI)** — `apps/admin/test/charts.test.ts` (estende):
  helper puro `unitLabel(kind)` → `'hours' → 'h'`, `'brl' → 'R$'`, `'services' → 'atend.'`,
  `'n/a' → ''`; e o componente não renderiza gráfico quando `kind === 'n/a'`.

**Risco/decisão aberta:**
- "Últimos 3 meses" é **mês-calendário** ou **3 ciclos de faturamento** (que podem ser bimestrais)?
  O Kleber diz "ciclo de utilização" — sugere ciclo. Decidir antes de T-R18a.1/T-R18a.4.
- Cliente com contratos de tipos diferentes (um em horas, outro em R$) não pode ter um gráfico único —
  a UI precisa de um gráfico por unidade. Não misturar é requisito, não detalhe.

---

## R18b — Relatório executivo mensal em PDF por cliente

**Pedido (citação curta do Kleber):** "Tenho um report executivo mensal aqui, que eu vou pegar,
por exemplo, maio. Vou pegar aqui a data stone […] Aí, isso aqui eu consigo fazer em PDF. […]
para ele saber quanto gastou, quanto consumiu, quais foram os principais tipos de ticket […]
No final, a gente põe a listona de chamados, de tudo que foi consumido aí."
(transcrição linhas 165-175)

**Estado atual:** **AUSENTE** — existe um pipeline de PDF branded (reaproveitável), mas ele produz
**fatura**, não relatório executivo.

O que existe (e é reutilizável):
- Render de PDF branded com logo/cor do tenant: `domain/invoice_pdf.py:63-82,162-171`
  (WeasyPrint primário, ReportLab no fallback — `:85-89,92-159`) + `templates/invoice.html`.
- Endpoint de download com o PDF persistido em `bytea`: `routers/invoices.py:125-146`
  (gera on-demand, guarda em `invoice.pdf_bytes` — `models/invoice.py:75-76`).
- Proxy e botão no portal: `apps/portal/server/api/portal/invoices/[number]/pdf.get.ts:1-13`,
  `apps/portal/pages/faturas/index.vue:122-128`.
- Números de consumo por período já calculáveis: `MetricsService.tenant_metrics`
  (`domain/metrics_service.py:51-72`) e `ContractReadService.series`.

O que **não** existe:
- **Nenhuma seleção mês + cliente → relatório.** Não há endpoint de relatório em `routers/`;
  o console **não tem nenhuma referência a PDF** (grep `pdf` em `apps/admin/` fora do lockfile: 0 hits) —
  o agente Gerti não consegue baixar nada.
- **"Principais tipos de ticket" não é computável hoje.** O GI `TicketStats` agrega apenas
  `ByState`, `ByPriority` e `ByDay` (`znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm:71-73,119-128`;
  cliente em `integrations/znuny_ticket.py:492-518`). Não há `ByType`, `ByService` nem `ByQueue` —
  e "tipo de solicitação" no vocabulário do Kleber (R12) é justamente Type/Service do Znuny.
- **"Listona de chamados" não existe em lugar nenhum como agregado do mês.** `TicketSearch`/`AgentTicketSearch`
  existem para operação, mas nenhum agregador mensal por cliente com horas por chamado.
- O documento atual é conceitualmente outro: `InvoiceService.create_from_cycle` agrega o período em linhas
  por `source_kind` (`domain/invoice_service.py:100-157`) — 2 a 3 linhas, sem chamados, sem tipos, sem gráfico;
  e roda por **ciclo de contrato**, não por **mês-calendário escolhido**.

**Gap:** o entregável que a Gerti manda para o cliente **todo mês** não pode ser produzido hoje —
nem o conteúdo (tipos de ticket, listagem), nem o gatilho (mês + cliente), nem o canal (PDF no console).

**Tarefas:**
- **T-R18b.1 — Estender o GI com agregação por tipo de ticket.**
  Camada: Znuny GI (leitura). Arquivos:
  `znuny/Custom/Kernel/GenericInterface/Operation/GertiTicket/TicketStats.pm:71-73,119-128`
  (acrescentar `ByType`, `ByService`, `ByQueue`), `znuny/webservices/GertiTicket.yml` se o contrato mudar,
  `integrations/znuny_ticket.py:148,492-518` (dataclass `TicketStats` + parse).
  Pronto quando: `ticket_stats` devolve `by_type` populado; `perl -c` continua verde no build da imagem
  e `tests/test_gi_routes_match_webservice.py` continua passando.
- **T-R18b.2 — Listagem de chamados do período por cliente.**
  Camada: integrações + domínio. Arquivos: `integrations/znuny_ticket.py` (reusar `TicketSearch` com janela),
  `domain/report_service.py` (novo), cruzando com `gerti.ticket_contract_link` e `consumption_event`
  para trazer horas por chamado.
  Pronto quando: para mês + cliente, sai a lista `[número, título, aberto em, estado, horas]` ordenada por data.
- **T-R18b.3 — `ReportService` + template do relatório executivo.**
  Camada: domínio + template. Arquivos: `domain/report_service.py`,
  `templates/executive_report.html` (novo, mesmo padrão de `templates/invoice.html`),
  `domain/report_pdf.py` (ou reuso do render de `invoice_pdf.py:162-171`).
  Pronto quando: o PDF traz cabeçalho branded, consumo do mês **na unidade do contrato**, top tipos de ticket,
  CSAT/SLA (já disponíveis em `metrics_service.py`) e a lista final de chamados.
- **T-R18b.4 — Endpoints de relatório.**
  Camada: router. Arquivos: `routers/admin_reports.py` (novo:
  `GET /v1/admin/tenants/{id}/reports/monthly?month=YYYY-MM` → JSON e `.../monthly.pdf` → `application/pdf`,
  ambos sob `get_admin_session`), `main.py`; opcionalmente espelho no portal
  (`GET /v1/reports/monthly.pdf`, `require_admin`) para o cliente baixar sozinho.
  Pronto quando: 404 para tenant desconhecido, 422 para `month` malformado, 200 com `%PDF-` no corpo.
- **T-R18b.5 — Tela no console: mês + cliente → visualizar/baixar.**
  Camada: UI. Arquivos: `apps/admin/pages/relatorios/index.vue` (novo), proxy
  `apps/admin/server/api/admin/tenants/[id]/reports/monthly.get.ts` (+ passthrough binário no molde de
  `apps/portal/server/utils/sidecar.ts:56-58`), link no menu do console.
  Pronto quando: o operador escolhe "maio/2026 + DataStone", vê a prévia e baixa o PDF.

**Testes de validação:**
- **V-R18b.1 (pytest, conteúdo do relatório)** — `apps/sidecar/tests/test_report_service.py` (novo):
  mês com 3 chamados (2 do tipo "Incidente", 1 "Solicitação") e 5h lançadas →
  `report["top_ticket_types"][0] == ("Incidente", 2)`, `report["consumption"]["kind"] == "hours"`,
  `report["consumption"]["value"] == 5.0`, `len(report["tickets"]) == 3`.
- **V-R18b.2 (pytest, unidade do relatório segue o contrato)** — mesmo arquivo:
  cliente com contrato `credit_brl` → `report["consumption"]["kind"] == "brl"` e valor em reais;
  o relatório **não** expõe minutos para esse cliente.
- **V-R18b.3 (pytest, PDF)** — `apps/sidecar/tests/test_report_pdf.py` (novo, molde de
  `tests/test_invoice_pdf.py`): `render_report_pdf(...)` devolve bytes começando com `b"%PDF-"`,
  tamanho > 1 KB, e o HTML intermediário contém o `display_name` do tenant e o número de cada chamado listado.
- **V-R18b.4 (pytest, rota e autorização)** — `apps/sidecar/tests/test_admin_reports_router.py` (novo):
  `GET /v1/admin/tenants/{id}/reports/monthly.pdf?month=2026-05` com `gsid_adm` → **200** com
  `content-type: application/pdf`; `month=2026-13` → **422**; sem cookie → **401**;
  tenant inexistente → **404**; GI fora do ar (`ZnunyUnavailable`) → **503** ou relatório degradado
  sem o bloco de tickets — **decidir e travar no teste** (hoje o padrão do `metrics_service.py:158-169` é degradar).
- **V-R18b.5 (perl/manual, GI)** — `apps/sidecar/tests/test_ticket_stats_client.py` (estende):
  payload GI com `ByType: {"Incidente": 2}` → `TicketStats.by_type == {"Incidente": 2}`;
  payload sem o bloco → `by_type == {}` (failure-soft, sem exceção).
- **V-R18b.6 (vitest, UI)** — `apps/admin/test/reports.test.ts` (novo): helper puro de mês
  — `monthRange('2026-05')` → `('2026-05-01', '2026-05-31')`; `monthRange('2026-13')` → `null`
  (a tela não deixa chamar a API com mês inválido).

**Risco/decisão aberta:**
- Znuny "Type" costuma ter poucos valores (Incidente/Solicitação); "principais tipos de ticket" na
  cabeça do Kleber pode ser o **catálogo de serviço** (R12, dois níveis) e não o Type. Confirmar com ele
  **antes** de T-R18b.1, senão o gráfico sai com duas barras e sem valor.
- Relatório de meses antigos depende de dados que só existem a partir do go-live — combinar expectativa.
- O PDF do relatório vai na marca **do cliente** (white-label, como a fatura) ou na marca **da Gerti**
  (é a Gerti que envia)? A fatura hoje usa `TenantBranding` (`routers/invoices.py:114-122`); para o
  relatório executivo a resposta pode ser outra.
- Custo de geração: WeasyPrint com listas longas é lento. Se um cliente tiver 500 chamados/mês,
  considerar geração assíncrona + cache em `bytea` (o padrão de `invoice.pdf_bytes` já serve).

---

## Resumo

| Requisito | Estado | # tarefas | Esforço |
|---|---|---|---|
| R3 — tipos de contrato (catálogo fechado) | **PARCIAL** | 4 | **M** |
| R6 — config de faturamento por cliente (SMS/e-mail/financeiro) | **AUSENTE** | 5 | **G** |
| R15 — financeiro global (avulsos, valor-hora, extras, NF/boleto) | **AUSENTE** | 5 | **G** |
| R18a — gráfico de consumo por cliente (3 meses, unidade por tipo) | **PARCIAL** | 4 | **M** |
| R18b — relatório executivo mensal em PDF | **AUSENTE** | 5 | **G** |

**Total: 23 tarefas, 25 testes de validação.**

### Achados transversais (valem para mais de um requisito)

1. **A fatura de contratos não-crédito sai R$ 0,00.** `invoice_service.py:100-160` soma
   `billable_amount_brl`, que `reconciliation_service.py:121-124` só preenche para
   `credit_brl`/`credit_shared`; o `overage_amount_brl` calculado em `cycle_service.py:66-71`
   nunca é lido. Afeta R15 e, por tabela, o "quanto gastou" do R18b.
2. **Três estruturas financeiras existem no schema e estão mortas:** `gerti.service_catalog_item`
   (com `unit_price_brl` e suporte a linhas globais — `models/catalog.py:28-51`,
   `0006_catalog_scope.py:151-176`), `gerti.shared_credit_pool` + `Contract.shared_pool_id`
   (`models/catalog.py:54-70`, `models/contract.py:75-77`) e
   `contract_scope_service.unit_price_override` (`models/contract_scope.py:15-27`).
   R15 e R3.2 devem **reusar**, não criar tabela nova.
3. **Nada no sidecar envia e-mail ou SMS.** Zero ocorrências de `smtp|twilio|sendgrid|send_email|sms`
   em `apps/sidecar/src/`. O R6 depende de construir o canal do zero (ou delegar ao Znuny).
