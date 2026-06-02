# Spec #1F-b — Portal Cliente: Visão de contratos rica (Fatia A) — Design

**Status:** aprovado no brainstorming (2026-06-01)
**Repo:** `ground-control` (NÃO o repo `gerti`, que é só a apresentação) — branch `main`, base `05efdcb`
**Depende de:** #1F-a (portal white-label de pé: branding por subdomínio, login Znuny→cookie `gsid`, `get_current_session`, `GET /v1/contracts` básico — em prod) e #1C (motor de contratos). Difere #1D (OIDC), #1E (tickets/catálogo) e #1G (admin).

## 1. Objetivo (uma frase)

Transformar a lista crua de contratos do #1F-a numa **visão de contratos rica e bonita** — detalhe completo do contrato, extrato de consumo paginado, gráficos SVG nativos (saldo, consumo no tempo) e um dashboard com alertas de saldo baixo — **100% read-only sobre o domínio #1C**, branded por tenant, com assinatura discreta da WAS.

## 2. Decisões travadas (constraints — não renegociar no plano)

1. **Read-only absoluto sobre #1C.** O portal **NUNCA** muta contrato, ciclo, glosa, evento de consumo, reajuste ou renovação. Esta fatia só adiciona **endpoints de leitura** e telas. Toda escrita do domínio (`record`, `close`, `apply_adjustment`, `renew`, aprovar glosa) fica fora — é operação do MSP/admin, não do cliente.
2. **Regras de negócio = o código, não a intuição.** Saldo, glosa, overage e ciclos vêm **literalmente** de `ConsumptionService.balance`, `CycleService.close` e `AdjustmentService` do #1C (§4.1). Nenhuma regra é reimplementada na borda; os endpoints **chamam os services/repos existentes** ou espelham exatamente sua lógica de leitura.
3. **Mesma muralha de auth/RLS do #1F-a.** Todos os novos endpoints ficam atrás de `get_current_session` (JWT `gsid` + checagem `tenant_id == request.state.tenant.id`) **e** `get_tenant_session` (abre `tenant_session_scope` → seta `app.current_tenant` → RLS). Zero rota nova de resolução de tenant. Cross-tenant é fail-closed: RLS não devolve linha de outro tenant ⇒ vira 404 (§6).
4. **Gráficos = SVG puro, sem lib externa.** Nada de Chart.js/D3/ApexCharts. Componentes Vue que recebem `props` de dados já agregados pelo backend e desenham `<svg>` com `path`/`rect`/`line`, SSR-friendly, pintados com `--brand-primary`/`--brand-accent`. Justificativa: bundle mínimo, SSR sem flash, controle total do visual premium.
5. **MVP BONITO é requisito verificável, não enfeite.** O critério de pronto inclui inspeção visual por screenshot em **dois tenants** (Aurora ciano + TechNova violeta). Ver §8.4 e §10.
6. **Assinatura WAS discreta e onipresente, sem competir com o white-label.** Crédito de plataforma "Desenvolvido por WAS Soluções em Tecnologia", mudo, no rodapé — a marca do tenant é a protagonista (§4.3.5).
7. **Stack inalterada.** Sidecar FastAPI + SQLAlchemy async + Pydantic; portal Nuxt 3 SSR + Nuxt UI v3 + Tailwind v4 + fontes Bricolage Grotesque (display) / Hanken Grotesk (body), branding via CSS vars lidas de `useState('branding')` (SSR, sem flash). Nenhuma dependência nova.

## 3. Arquitetura

```
Navegador  (https://aurora.suporte.gerti.com.br)
  │
  ▼
Nuxt 3 SSR (apps/portal)
  ├─ Nitro mw branding (#1F-a): Host→subdomínio → GET /v1/branding → event.context.branding
  ├─ páginas: / (dashboard rica) , /contratos/[id] (detalhe rico)
  │     SSR fetch (encaminha cookie gsid) via rotas server Nuxt → sidecar
  └─ componentes SVG puros (saldo, série temporal, alertas) — props já agregadas
  │
  ▼ (cookie gsid; fetch server-side)
Sidecar FastAPI (apps/sidecar)
  ├─ TenantMiddleware (#1C): subdomínio → request.state.tenant → não seta GUC sozinho
  ├─ get_current_session (#1F-a): valida gsid + tenant==subdomínio (401/403)
  ├─ get_tenant_session (#1C): tenant_session_scope → SET LOCAL app.current_tenant → RLS
  └─ NOVOS routers read-only:
       GET /v1/contracts            (estendido: +id, +consumed_percent)
       GET /v1/contracts/{id}       (detalhe completo)
       GET /v1/contracts/{id}/consumption  (extrato paginado)
       GET /v1/contracts/{id}/series        (série agregada p/ gráfico)
       GET /v1/dashboard            (resumo + alertas de saldo baixo)
  reusa: ConsumptionService.balance, repos/queries do #1C; NENHUMA escrita.
```

O Nuxt nunca fala com o Znuny nem com o Postgres direto — o sidecar é a única porta, como no #1F-a. Os novos routers entram em `main.py` com `prefix=settings.api_v1_prefix`, exatamente como `contracts`/`me`/`branding` já entram (`app.include_router(...)`).

## 4. Componentes

### 4.1 Regras de negócio verificadas no código #1C (fonte da verdade)

Estas três regras foram **lidas no código** e os endpoints abaixo as honram sem reimplementá-las:

**(A) Saldo por tipo — `ConsumptionService.balance(contract_id) -> Balance(kind, remaining)`** (`domain/consumption_service.py:72-119`). Verificado:

| `ContractType` | `kind` | `remaining` |
|---|---|---|
| `hour_bank` | `"hours"` | `initial_hours − (Σ billable_minutes / 60)` |
| `credit_brl`, `credit_shared` | `"brl"` | `initial_amount_brl − Σ billable_amount_brl` |
| `service_count` | `"services"` | `initial_service_count − count(eventos com source_kind='service_item')` |
| `closed_value`, `saas_product` | `"n/a"` | `None` (sem saldo corrente) |

Os 6 valores de `ContractType` são exatamente `closed_value, credit_brl, credit_shared, hour_bank, saas_product, service_count` (`models/enums.py`).

**(B) Regra S3 da glosa — "conta para o saldo?"** (`consumption_service.py:76-90`). **Somente glosa `approved` remove o consumo do saldo.** Um evento é excluído **se e somente se** seu `glosa_id` aponta para uma glosa com `status = 'approved'`. Eventos com `glosa_id IS NULL` **ou** com glosa `pending`/`rejected` **ainda contam** (o dinheiro é devido até o write-off ser aprovado). O código usa explicitamente o braço `glosa_id IS NULL OR glosa_id NOT IN (<ids approved>)` justamente para evitar o footgun do SQL `NULL NOT IN (..) = NULL` (que descartaria erradamente eventos sem glosa). `GlosaStatus` = `{pending, approved, rejected}`.
> Nota de implementação verificada: `CycleService.close` (`cycle_service.py:37-50`) aplica a **mesma** regra approved-only, mas via `ConsumptionEvent.id.not_in(<consumption_event_id de glosas approved>)` **sem** braço `IS NULL` — correto ali porque `consumption_event.id` é `BigInteger Identity` NOT NULL (nunca nulo), então não há footgun. O endpoint de extrato (§4.2.3) usa a forma do `balance()` (com `IS NULL`) para marcar "conta para o saldo".

**(C) Overage / franquia (hour_bank) — `CycleService.close`** (`cycle_service.py:61-70`). Verificado: `franchise_minutes = initial_hours × 60` **apenas para `hour_bank`** (senão `0`); `overage_minutes = max(0, consumed_minutes − franchise_minutes)`; `overage_amount_brl = (overage_minutes / 60) × unit_price_brl` **apenas para `hour_bank`** (senão `0`). Carry-over (`accumulate_balance_between_cycles=true`) = `max(0, franchise_minutes − consumed_minutes)`; senão `0`. Ciclo de **fechamento** (`CycleKind.closing`) é o único que pode ser fechado (billing ≠ closing); ledger é append-only (o close só carimba `closing_cycle_id`/`totals`/`status=closed`/`closed_at` valor-Python). Esses números **já vivem** em `contract_cycle.totals` (JSONB) para ciclos fechados — o detalhe (§4.2.2) os **lê de lá**, não recalcula.

**Reajuste/renovação — `AdjustmentService`** (`adjustment_service.py`): regra de reajuste honra `cap_percent` (clamp: `percent = min(percent, cap_percent)`); `_add_months` preserva o dia-do-mês quando válido, senão clampa para o **último dia real** do mês-alvo (corrige o bug de billing date); renovação só com `auto_renew=true`. O detalhe (§4.2.2) **lê** `index_code, cadence_months, next_run_on, cap_percent, last_applied_on, last_applied_percent` de `contract_adjustment_rule` e `auto_renew, notice_days, next_review_on, renewal_term_months` de `contract_renewal_policy` — read-only, **sem** disparar reajuste/renovação.

> **Divergência vs brief:** nenhuma divergência material. Brief e código coincidem em (A), (B) e (C). Único ponto a registrar: o brief disse "balance() usa braço IS NULL para evitar NULL NOT IN" — confirmado; e a assimetria benigna entre `balance()` (com `IS NULL`) e `close()` (sem, por usar `id`) está documentada acima. Os campos do `contract_adjustment_rule` são `cadence_months` (não `cadence`) e a regra/política têm PK = `contract_id` (1:1 com contrato).

### 4.2 Sidecar — novos/estendidos endpoints (todos read-only)

Padrão comum a **todos**: dependências `_session = Depends(get_current_session)` **e** `session = Depends(get_tenant_session)`; nenhuma escrita (sem `add`/`flush`/`commit`/`update`); modelos de resposta Pydantic (`BaseModel`); `tenant_id` jamais vem do path/query — vem do tenant da sessão/RLS. Ordenação determinística. Datas como `dt.date`, timestamps como `dt.datetime` (timezone-aware), valores monetários/horas como `float` (espelhando os modelos Pydantic já usados no `contracts.py`).

Sugestão de organização: estender `routers/contracts.py` (lista + detalhe + consumption + series) e criar `routers/dashboard.py`. Helpers de agregação puros em `domain/portal_views.py` (read-only, testáveis isoladamente) — opcional, decidido no plano.

#### 4.2.1 `GET /v1/contracts` (estendido)

Mantém os campos atuais (`code, type, status, starts_on, ends_on, saldo:{kind,remaining}`) e **acrescenta**:

- `id: uuid` — o id do contrato (hoje **não** exposto), necessário para linkar ao detalhe.
- `consumed_percent: float | null` — % consumido para desenhar a barra de progresso. Definição **fixada** por tipo (deriva de `Balance` + campos iniciais; sem nova query além do `balance()` que já roda):
  - `hour_bank`: `clamp01((initial_hours − remaining) / initial_hours) × 100` (i.e. `consumed_hours / initial_hours`); se `initial_hours` ausente/0 → `null`.
  - `credit_brl`/`credit_shared`: `clamp01((initial_amount_brl − remaining) / initial_amount_brl) × 100`; se base 0/ausente → `null`.
  - `service_count`: `clamp01((initial_service_count − remaining) / initial_service_count) × 100`; se base 0/ausente → `null`.
  - `closed_value`/`saas_product`: `null` (não há saldo corrente — `kind="n/a"`).
  - `clamp01` satura em `[0,100]` (overage não estoura a barra; o overage é mostrado como rótulo, não como barra > 100%).

Forma (1 item): `{ id, code, type, status, starts_on, ends_on, saldo:{kind, remaining}, consumed_percent }`. Ordenação: `Contract.code` (como hoje).

#### 4.2.2 `GET /v1/contracts/{id}` — detalhe completo

`id` no path. Se o contrato não é do tenant da sessão, **RLS não o devolve** → `404 contract_not_found` (documentado: não distinguimos "não existe" de "é de outro tenant" — não vaza existência cross-tenant). Resposta (Pydantic):

```
{
  id, code, type, status, starts_on, ends_on,
  initial_amount_brl, initial_hours, initial_service_count,
  unit_price_brl, travel_franchise_count,
  billing_period_months, closing_period_months,
  billing_in_advance, accumulate_balance_between_cycles,
  saldo: { kind, remaining },                 # ConsumptionService.balance
  consumed_percent,                            # mesma regra de 4.2.1
  cycles: [ {                                  # billing E closing
    id, kind, period_start, period_end, status,
    closed_at,                                 # null se aberto
    totals                                     # JSONB cru de contract_cycle.totals (null se aberto):
                                               #   {consumed_minutes, consumed_brl, franchise_minutes,
                                               #    overage_minutes, overage_amount_brl, carry_over, event_count}
  } ],
  adjustment_rule: {                           # null se contrato sem regra
    index_code, cadence_months, next_run_on,
    cap_percent, last_applied_on, last_applied_percent
  },
  renewal_policy: {                            # null se sem política
    auto_renew, notice_days, next_review_on, renewal_term_months
  },
  billing_parties: [ {                         # 0..n
    legal_name, document, fiscal_address, payment_method
  } ]
}
```

`cycles` ordenados por `period_start` ascendente, ambos os `kind`. `totals` é exposto **como está** no JSONB (já calculado pelo `close()` do #1C); para ciclos abertos é `null` (não recalculamos no portal — read-only).

#### 4.2.3 `GET /v1/contracts/{id}/consumption` — extrato paginado

Extrato append-only de `consumption_event` do contrato. **Paginação fixada:** query params `?page=<int≥1>&page_size=<int>` com **`page_size` default = 50, máximo = 200** (acima clampa a 200). **Ordenação fixada: `occurred_at DESC, id DESC`** (mais recente primeiro; `id` como desempate determinístico). 404 se o `id` não é do tenant (RLS, como §4.2.2). Resposta:

```
{
  page, page_size, total,                      # total = COUNT na janela (mesma RLS)
  items: [ {
    id,                                         # bigint do evento
    occurred_at, source_kind, source_ref,
    billable_minutes, billable_amount_brl,
    glosa: { status } | null,                   # status da glosa associada (se houver)
    counts_toward_balance: bool                 # regra S3 (B): true se SEM glosa OU glosa != approved
  } ]
}
```

`counts_toward_balance` aplica **exatamente** a regra S3 verificada (§4.1-B): `glosa is null OR glosa.status != 'approved'`. Documentado no docstring do endpoint citando `consumption_service.balance` como fonte. A `glosa` é obtida por join/lookup do `glosa_id` do evento (lembrando que `consumption_event.glosa_id` **não** tem FK no banco — integridade na camada app, §`models/consumption.py` H8; é seguro só para leitura).

#### 4.2.4 `GET /v1/contracts/{id}/series` — série temporal agregada (p/ gráfico SVG)

Série de consumo agregada para o gráfico de "consumo ao longo do tempo". 404 cross-tenant (RLS). **Agregação fixada:**

- **Granularidade: diária por padrão** (`?granularity=day|week`, default `day`). Bucket por `date(occurred_at)` (UTC) — `week` agrupa por segunda-feira ISO.
- **Janela: a janela do contrato** (`starts_on`..`min(ends_on, hoje)`); buckets sem evento são **preenchidos com zero** (densos), para a área/linha não ter buracos. Limite de segurança: se a janela densa exceder **400 buckets**, força `granularity=week` (evita payload patológico em contratos plurianuais).
- **Métrica por tipo:** `hour_bank` → `value_hours = Σ billable_minutes / 60` por bucket; `credit_brl`/`credit_shared`/`closed_value`/`saas_product` → `value_brl = Σ billable_amount_brl`; `service_count` → `value_count = COUNT(source_kind='service_item')`. O campo populado segue o `kind` do saldo; os demais vêm `0`/ausentes.
- **Regra de glosa na série:** aplica a **mesma** regra S3 (B) — soma só o que **conta para o saldo** (exclui glosa approved). Documentado.

Resposta:

```
{
  granularity,                                  # "day" | "week"
  kind,                                          # "hours" | "brl" | "services" | "n/a"
  points: [ { bucket: date, value: float } ]    # ordenado asc por bucket; densos (zeros incluídos)
}
```

Para `kind="n/a"` (closed_value/saas_product) a série de horas/brl pode vir vazia/zeros — o front esconde o gráfico de série nesse caso e mostra só os ciclos.

#### 4.2.5 `GET /v1/dashboard` — resumo do home + alertas de saldo baixo

Agregado para o dashboard. Tenant da sessão (RLS). Read-only. Resposta:

```
{
  contract_count,                               # nº de contratos do tenant
  balances_by_type: [ {                         # um item por ContractType presente
    type, kind, contract_count,
    total_remaining: float | null               # soma de remaining dos contratos desse tipo (null p/ n/a)
  } ],
  low_balance_alerts: [ {                        # ver regra abaixo
    contract_id, code, type, kind,
    remaining, consumed_percent,
    severity                                     # "warning" | "critical"
  } ]
}
```

**Regra de saldo baixo (fixada):** um contrato entra em `low_balance_alerts` quando o **percentual restante** (`remaining / inicial`) cai abaixo do limiar, **apenas para tipos com saldo corrente** (`hour_bank`, `credit_brl`, `credit_shared`, `service_count`; `closed_value`/`saas_product` nunca alertam, `kind="n/a"`):

- `remaining_pct = remaining / inicial` (inicial = `initial_hours` | `initial_amount_brl` | `initial_service_count` conforme o tipo). Se inicial 0/ausente → sem alerta.
- **`warning` quando `remaining_pct < 20%`** (i.e. consumido > 80%).
- **`critical` quando `remaining_pct ≤ 0%`** (saldo zerado ou negativo/overage).
- `severity` = `critical` se `≤ 0`, senão `warning`. Contratos com `remaining_pct ≥ 20%` não aparecem.

O limiar de 20% é o threshold canônico desta spec (alinhado ao exemplo do brief "hour_bank remaining < 20% of initial") e vale para todos os tipos com saldo.

### 4.3 Portal — Nuxt 3 SSR (`apps/portal`)

Reusa o app shell, branding (`useState('branding')` lido de `useRequestEvent().context.branding`, SSR sem flash), fontes e CSS vars do #1F-a. Todas as telas pintam com `--brand-primary`/`--brand-accent`; default neutro quando tenant sem branding (#1F-a já garante).

#### 4.3.1 Rotas server Nuxt (proxy, encaminham cookie `gsid`)

`server/api/`: `contracts.get.ts` (lista), `contracts/[id].get.ts` (detalhe), `contracts/[id]/consumption.get.ts` (com `page`/`page_size`), `contracts/[id]/series.get.ts` (com `granularity`), `dashboard.get.ts`. Cada uma repassa ao `SIDECAR_URL` com o cookie da request (mesmo padrão do #1F-a). Sessão ausente/expirada → o sidecar responde 401 → o handler redireciona SSR para `/login`.

#### 4.3.2 Páginas

- **`/` (dashboard rica)** — SSR busca `/v1/dashboard` + `/v1/contracts`. Mostra:
  - **Cartões de contrato** com `consumed_percent` em **barra de progresso SVG** (hour-bank/credit/service), saldo grande, tipo/status como badge, datas.
  - **Faixa de alertas de saldo baixo** no topo (componente `LowBalanceAlerts`): `warning` em âmbar, `critical` em vermelho — cores semânticas fixas, **não** brand (alerta precisa ler como alerta em qualquer marca), com link para o detalhe.
  - **Mini-gráfico de série** opcional por cartão (sparkline SVG) — ou um gráfico agregado no topo; decisão visual no plano, ambos SVG puro.
- **`/contratos/[id]` (detalhe rico)** — SSR busca `/v1/contracts/[id]` + `/v1/contracts/[id]/series` + 1ª página de `/v1/contracts/[id]/consumption`. Estrutura:
  - **Header**: code + tipo/status (badges branded), período de vigência.
  - **Saldo grande** (hero): número + unidade (`h` / `R$` / serviços) + barra/anel SVG de `consumed_percent`; rótulo de overage quando passou da franquia.
  - **Gráfico de consumo no tempo** (área/linha SVG, brand-colored) a partir de `/series`.
  - **Timeline de ciclos**: billing & closing em ordem cronológica, status (open/closed/invoiced) como pílulas; para ciclos `closed`, expõe `totals` (consumido, franquia, overage R$, carry-over).
  - **Tabela de extrato paginada** (`/consumption`): colunas occurred_at, origem (`source_kind`/`source_ref`), minutos, R$, e **indicador de glosa** — ícone/badge por status (`pending` âmbar, `approved` vermelho riscado = não conta, `rejected` cinza) e marca visual de `counts_toward_balance=false`. Paginação client/SSR via `page`/`page_size`.
  - **Reajuste & renovação**: cartão com `index_code`, cadência, `cap_percent`, próximo reajuste, último aplicado; auto-renovação (sim/não), aviso prévio, próxima revisão, prazo.
  - **Partes de faturamento** (`billing_parties`): razão social, documento, endereço fiscal, forma de pagamento.

#### 4.3.3 Componentes SVG puros (sem lib; `apps/portal/app/components/charts/` ou similar)

Cada um é **puro de props → `<svg>`**, SSR-friendly, testável isoladamente no vitest:

- `ProgressBar.vue` — `percent` (0..100) → barra/anel; cor `--brand-primary`, satura em 100%, estado de overage opcional.
- `AreaChart.vue` / `LineChart.vue` — `points: {bucket, value}[]` → `path` de área/linha com gradiente brand; eixos mínimos, labels enxutas; estado vazio (sem pontos) elegante.
- `Sparkline.vue` — versão compacta para cartões.
- Sem dependência de tamanho do browser para SSR: `viewBox` + `preserveAspectRatio`, responsivo por CSS.

#### 4.3.4 Estados e micro-interações (parte do "bonito")

Toda tela cobre **loading** (skeletons branded), **vazio** (ilustração/copy gentil, ex.: "Nenhum contrato ainda"), **erro** (mensagem amigável + retry; 401 → redirect login). Micro-interações: hover/focus em cartões e linhas, transições suaves de barra/área, foco acessível. **Responsivo** mobile→desktop. Nada de elemento cru/sem estilo (requisito de §10).

#### 4.3.5 Assinatura WAS (requisito)

**Crédito discreto de plataforma**, mudo, sem competir com o white-label do tenant:

- **Texto:** "Desenvolvido por WAS Soluções em Tecnologia" (pode abreviar para "Plataforma WAS" em telas estreitas).
- **Placement:** no **rodapé** do app shell autenticado (presente em `/` e `/contratos/[id]`) **e** no rodapé da tela de **login**. Pequeno (`text-xs`), cor mutada (token de texto secundário/`opacity` baixa), nunca usando `--brand-primary` (não pode parecer marca do tenant). Sem logo grande, sem link chamativo (link opcional discreto para o site da WAS, `rel="noopener"`).
- **Regra:** a marca do tenant (logo/nome/cor) é a protagonista; a WAS aparece só como assinatura de plataforma/dev. Verificado nos screenshots de §10 (presente e discreto em ambos os tenants).

## 5. Fluxos

- **Dashboard:** browser (cookie `gsid`) → Nuxt SSR → rotas server `/api/dashboard` + `/api/contracts` → sidecar (`get_current_session` valida tenant==subdomínio; `get_tenant_session` abre RLS) → `ConsumptionService.balance` + agregações → cartões + barras SVG + alertas branded.
- **Detalhe:** clique no cartão → `/contratos/[id]` → SSR busca detalhe + série + 1ª página de extrato → header + saldo + gráfico + timeline de ciclos + tabela + reajuste/renovação + partes.
- **Paginação do extrato:** navegação de página → rota server `/api/contracts/[id]/consumption?page=N` → sidecar (mesma RLS) → próxima fatia (50/página).
- **Cross-tenant negado:** cookie de outro tenant → `get_current_session` 403; id de contrato de outro tenant no path → RLS oculta → 404 (sem vazar existência).

## 6. Erros & segurança

- **RLS fail-closed (defesa de dados):** sem `app.current_tenant` setado, as policies do #1C não devolvem linha. `get_tenant_session` sempre seta a GUC a partir do tenant resolvido; nenhum endpoint novo usa sessão admin/bypass.
- **Cross-tenant via sessão:** `get_current_session` rejeita 401 (sem cookie/expirado/inválido) e 403 (`tenant_id` do cookie ≠ tenant do subdomínio) — herdado do #1F-a, sem alteração.
- **`{id}` de outro tenant → 404** (não 403): a RLS oculta a linha, então o `session.get(Contract, id)`/select retorna `None` → `404 contract_not_found`. **Documentado:** não distinguimos inexistente de alheio (não vaza existência). Vale para detalhe, consumption e series.
- **Read-only garantido:** code review/teste confirma ausência de `INSERT/UPDATE/DELETE`/`flush(`/`commit(` nos novos paths. O portal jamais muta o domínio #1C.
- **Validação de input:** `page≥1`, `page_size` clamp `[1,200]`, `granularity ∈ {day,week}`; valores inválidos → 422 (FastAPI/Pydantic) ou clamp documentado.
- **`glosa_id` sem FK** (H8): só leitura por lookup; nenhuma integridade nova exigida.

## 7. Riscos / assunções

- **R1 (baixo):** payload de série em contratos longos. Mitigado pelo cap de 400 buckets que força `week` (§4.2.4).
- **R2 (baixo):** custo de `balance()` por contrato no dashboard (N queries). Aceitável no volume atual (poucos contratos/tenant); se virar gargalo, otimização (1 query agregada) é tarefa futura — **não** nesta fatia (YAGNI).
- **R3 (baixo):** consistência visual entre Aurora e TechNova. Mitigado pela verificação por screenshot dupla (§10) como gate de pronto.
- **Assunção:** fixtures/seed do #1C já têm Aurora e TechNova com contratos cobrindo os tipos com saldo (hour_bank/credit/service) e ao menos uma glosa `approved` e uma `pending`/`rejected` para provar a regra S3. Se faltar, o plano estende o seed (read-only para o portal; seed é util de teste).

## 8. Testes (todos os gates verdes)

### 8.1 Sidecar (pytest + testcontainers, padrão #1C/#1F-a)

Para **cada** endpoint novo/estendido: (a) **tenant-scoped** (devolve só dados do tenant da sessão); (b) **RLS fail-closed** (sem GUC → 0 linhas); (c) **cross-tenant** (cookie/sessão de TechNova não enxerga Aurora → 403; id de contrato Aurora pedido como TechNova → 404); (d) **matemática da regra de negócio**:

- **Saldo (B+A):** evento com glosa `approved` **não** conta; evento com glosa `pending` e `rejected` **conta**; evento sem glosa conta (prova explícita do braço `IS NULL`). Verifica `remaining` por tipo (hours/brl/services) e `consumed_percent`.
- **Série hour_bank:** agregação diária densa (buckets-zero), soma de minutos/60, granularidade `week` quando estoura 400 buckets; exclui glosa approved.
- **Extrato:** ordenação `occurred_at DESC, id DESC`; paginação (`total`, `page_size` clamp 200); `counts_toward_balance` coerente com a regra S3.
- **Detalhe:** `cycles` billing+closing com `totals` cru do JSONB (closed) e `null` (open); `adjustment_rule`/`renewal_policy`/`billing_parties` corretos; 404 cross-tenant.
- **Dashboard:** `balances_by_type` somando por tipo; `low_balance_alerts` com limiar 20% (`warning`) e ≤0 (`critical`); closed_value/saas_product nunca alertam.

Reusa as fixtures Aurora + TechNova do #1C/#1F-a.

### 8.2 Portal (vitest + @nuxt/test-utils)

- Componentes SVG puros (`ProgressBar`, `AreaChart`/`LineChart`, `Sparkline`) dado `props` de dados → snapshot/asserção de `path`/`rect` (incl. estado vazio e clamp 100%).
- Render do detalhe a partir de payload mock (header, saldo, ciclos, tabela com indicadores de glosa).
- Lógica de alerta de saldo baixo (warning/critical) renderizando cor/severidade certas.
- Assinatura WAS presente no rodapé (login + app shell) e com classe mutada (não brand).

### 8.3 E2E (estende o smoke do #1F-a)

Aurora vs TechNova: login Aurora → dashboard + detalhe de um contrato Aurora com gráficos; sessão Aurora **não** acessa detalhe de contrato TechNova (404). Roda no gate de CI/`make`.

### 8.4 Verificação visual (gate de "bonito")

Screenshots de `/` e `/contratos/[id]` em **Aurora (ciano)** e **TechNova (violeta)**: hierarquia/spacing coesos, fontes corretas, barras/gráficos brand-colored, alertas legíveis, estados de loading/vazio polidos, responsivo, assinatura WAS discreta. O controller aprova antes do deploy.

## 9. Fora de escopo (YAGNI — exclusões duras, NÃO implementar)

- **Qualquer escrita/mutação** de contrato, ciclo, glosa, evento de consumo, reajuste ou renovação — o portal é **read-only** sobre o #1C. Aprovar/rejeitar glosa, fechar ciclo, aplicar reajuste, renovar: **não**.
- **Tickets, catálogo de serviços, abrir chamado** (#1E / Fatia B).
- **Admin/onboarding de tenant, UI de branding** (#1G).
- **OIDC / servidor de auth PKCE** (#1D) — segue a auth credencial-Znuny do #1F-a.
- **Multi-Znuny / instâncias dedicadas.**
- Exportar extrato (CSV/PDF), filtros avançados/busca no extrato, i18n, lib de gráficos externa, dashboards executivos, otimização de N+1 do dashboard — tudo futuro.

## 10. Entregável / definição de pronto

- Novos endpoints read-only **no ar e tenant-scoped** (RLS provado): `/v1/contracts` estendido (+`id`,+`consumed_percent`), `/v1/contracts/{id}`, `/v1/contracts/{id}/consumption`, `/v1/contracts/{id}/series`, `/v1/dashboard`.
- Dashboard rica + detalhe `/contratos/[id]` renderizando **branded por tenant**, com **gráficos SVG puros**, alertas de saldo baixo, extrato paginado com indicadores de glosa, ciclos, reajuste/renovação e partes de faturamento.
- **MVP bonito** verificado por screenshots **Aurora + TechNova** (§8.4); nenhum elemento cru; estados loading/vazio/erro polidos; responsivo.
- **Assinatura WAS** presente e discreta no rodapé do login e do app shell.
- Gates verdes: ruff+mypy+pytest (sidecar), vitest (portal), build/SSR do portal, e2e cross-tenant.
- Deploy **aditivo** (portal + sidecar rebuildados, sem migration — esta fatia não cria tabela), documentado no padrão do #1F-a.
