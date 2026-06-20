# Plano — Página de Contratação + Integração Asaas (Spec #2 / "contratação")

> Status: **PLANO** (não implementado). Data: 2026-06-20.
> Baseado em: padrão Asaas do projeto `~/projetos/billing/` (Django, HTTP puro)
> + arquitetura atual do Ground Control (sidecar FastAPI, portal/admin Nuxt,
> schema `gerti`, contratos #1C, onboarding #1G, faturas #1P).
> Decisões de produto coletadas com o William (2026-06-20) — ver §1.

---

## 0. Objetivo

Hoje **não existe pagamento** no Ground Control: `contract_billing_party.payment_method`
é só um campo textual; faturas (#1P) são internas/não-fiscais e marcadas pagas à mão;
onboarding (#1G) e criação de contrato (#1C) só acontecem pelo Console (agente).

Queremos uma **página de contratação self-service** que: apresenta planos, coleta os
dados do contratante, **cobra via Asaas** (PIX/PIX recorrente/Boleto/Cartão), e ao
**confirmar o pagamento provisiona automaticamente** (tenant + contrato + usuários),
fechando o ciclo de aquisição sem intervenção manual. E que conecte o Asaas ao
faturamento recorrente já existente (#1P) para cobrar os ciclos mensais.

### Não-objetivos (desta fase)
- Substituir o motor de faturamento/consumo (#1B/#1P) — o Asaas é a **camada de cobrança**, não o cálculo.
- Emissão fiscal (NF-e) — o `billing/` emite NF-e via Asaas; aqui fica **opcional/fase posterior** (faturas GC seguem não-fiscais por ora).
- Antifraude avançado / 3DS — fora do MVP (cartão tokenizado + Asaas já mitiga).

---

## 1. Decisões de produto (William, 2026-06-20)

| Decisão | Escolha | Implicação |
|---|---|---|
| **Quem contrata / conta Asaas** | **Ambos, configurável** | Cliente final paga o MSP (conta Asaas do MSP) **e** MSP novo paga a Gerti (conta Asaas da Gerti). Exige **resolução de conta por contexto** + multi-conta. |
| **Modelo de cobrança** | **Os dois conforme o tipo de contrato** | `saas_product`/recorrentes → **Asaas Subscription**; `hour_bank`/`credit_*`/`service_count` pré-pago → **Asaas Payment** avulso (recarga). |
| **Métodos** | **PIX, PIX recorrente, Boleto, Cartão** | `billingType` por método; PIX recorrente = Subscription com `billingType=PIX`. |
| **Pós-pagamento** | **"Outro" (em aberto)** | Ver §6 — proponho **pré-cadastro → paga → webhook provisiona**, com auto-onboarding configurável. **Principal ponto a confirmar.** |

> A flexibilidade total ("ambos/os dois/todos") é a **visão**. O plano entrega em
> **fases** (§9): MVP estreito e correto primeiro, flexibilidade depois — sem
> reescrever (o modelo de dados já nasce pronto para multi-conta e ambos os modos).

---

## 2. Arquitetura — onde encaixa

```
                 (público, sem login)
Prospecto ─▶ apps/checkout (Nuxt SSR)  ──┐
MSP no Console ─▶ "gerar link"          │   POST /v1/checkout/*        ┌────────────┐
Cliente no Portal ─▶ "contratar/expandir"┘  (rotas PÚBLICAS no sidecar)│  Asaas API │
                                             │  AsaasClient (httpx) ───▶│ (sandbox/  │
                          sidecar (FastAPI)  │                          │  prod)     │
                                             │◀── webhook ──────────────└────────────┘
                              POST /v1/hooks/asaas/payment (token + idempotência)
                                             │
                              on PAYMENT_RECEIVED ▶ ProvisioningService
                                             │   ├─ OnboardingService (#1G)  [se tenant pendente]
                                             │   ├─ ContractService (#1C)     [cria/ativa contrato]
                                             │   └─ InvoiceService.mark_paid  [#1P, p/ ciclos recorrentes]
```

**Princípios herdados do GC (reaproveitar, não reinventar):**
- **Client externo** no molde de `integrations/ollama.py` (httpx, timeout, feature-flag, transport injetável p/ teste) e da base do `billing` (`access_token` header, tratamento de erro por status).
- **Webhook de entrada** no molde de `routers/hooks.py` + `integrations/webhook_sig.py` (idempotência por `event_id`, sempre 200, processa e marca PROCESSED) — porém a **auth do webhook Asaas é por token** (`asaas-access-token` header, compare_digest), como no `billing`, **não** HMAC.
- **Provisionamento** reusa `OnboardingService.onboard()` e `ContractService` — cross-tenant via `AdminSessionLocal` (BYPASSRLS), exatamente como o Console faz hoje.
- **Rotas públicas** entram na **allowlist do `TenantMiddleware`** (como `/v1/hooks`, `/v1/admin`, `/v1/agent`) — não dependem de subdomínio de tenant.
- **Segredos** só em `.env.prod` (ver [[deploy-secrets]] no padrão) e/ou em tabela com referência (multi-conta).

---

## 3. Modelo de dados — migration `0021_contratacao_asaas`

Schema `gerti`, RLS conforme cada tabela. (Última migration hoje: `0020_ai_assist_kind`.)

### 3.1 Catálogo de planos vendáveis — `gerti.plan`
O prospecto escolhe um **plano** (não um "tipo de contrato" cru). Plano = receita para criar o contrato.
- `id` UUID, `slug` (único, p/ URL), `name`, `description`
- `audience` enum (`end_client` | `msp`) — quem pode contratar (casa com "ambos")
- `contract_type` (FK lógica ao `ContractType`: saas_product, hour_bank, …)
- `billing_mode` enum (`subscription` | `one_off`) — deriva do tipo, mas explícito
- `price_cents`, `cycle` (`MONTHLY`/`YEARLY`/… quando subscription), `initial_*` (horas/serviços/crédito p/ pré-pago)
- `provider_account_id` (FK → `payment_provider_account`, NULL = conta default/Gerti)
- `active` bool, `public` bool (aparece no checkout público?)
- **Tenant-agnóstico** (catálogo global) → tabela **não-tenant**, lida com BYPASSRLS.

### 3.2 Conta de provedor (multi-conta Asaas) — `gerti.payment_provider_account`
- `id` UUID, `owner_kind` enum (`gerti` | `msp`), `tenant_id` NULL (preenchido quando `owner_kind=msp`)
- `provider` enum (`asaas`), `mode` enum (`sandbox` | `production`)
- `api_key_ref` (referência ao segredo — NUNCA a key em claro; ver §8), `base_url`
- `webhook_token` (UUID gerado por nós; valida o header `asaas-access-token`)
- `default_pix_addresskey` (opcional), `active`
- **Não-tenant** (config de infra), lida com BYPASSRLS. A linha `gerti` é a conta da plataforma; linhas `msp` são por-tenant.

### 3.3 Sessão de checkout — `gerti.checkout_session`
Captura o prospecto **antes** do pagamento (tenant ainda pode não existir).
- `id` UUID, `plan_id` FK, `provider_account_id` FK (resolvido do plano/contexto)
- `status` enum (`started` | `awaiting_payment` | `paid` | `provisioned` | `failed` | `expired` | `canceled`)
- `target_tenant_id` UUID NULL (preenchido se contratação por tenant existente; NULL = novo)
- `applicant` JSONB (razão social, CNPJ, e-mail, subdomínio desejado, branding, usuário admin) — dados p/ o onboarding
- `asaas_customer_id`, `asaas_subscription_id`, `asaas_payment_id` (preenchidos ao criar no Asaas)
- `guest_token` (JWT curto, assinado, p/ o front consultar status sem login)
- `created_at`, `expires_at`, `provisioned_tenant_id` (resultado)
- **Não-tenant** (o tenant pode não existir ainda) — BYPASSRLS, mas dados sensíveis mínimos.

### 3.4 Pagamento — `gerti.payment`
Espelho local de cada cobrança Asaas (avulsa ou parcela de assinatura).
- `id` UUID, `tenant_id` NULL (preenchível pós-provisionamento), `checkout_session_id` FK NULL
- `contract_id` FK NULL, `invoice_id` FK NULL (vincula à fatura #1P quando for ciclo recorrente)
- `provider` (`asaas`), `asaas_payment_id` (único), `asaas_subscription_id` NULL
- `billing_type` enum (`PIX` | `BOLETO` | `CREDIT_CARD`)
- `status` enum (`pending` | `confirmed` | `received` | `overdue` | `refunded` | `failed` | `canceled`)
- `value_cents`, `due_date`, `paid_at`, `external_reference` (= checkout_session_id ou invoice_id)
- RLS quando `tenant_id` presente; criadas via BYPASSRLS no fluxo de checkout.

### 3.5 Idempotência de webhook — `gerti.asaas_webhook_event`
- `id` UUID, `event_id` (do Asaas, **único**), `event_type`, `payload` JSONB
- `status` enum (`received` | `processed` | `failed`), `received_at`, `processed_at`, `error`
- Reprocessável (flag). **Não-tenant**, BYPASSRLS. (Molde: `billing` `AsaasWebhookEvent`.)

### 3.6 Vínculo Asaas customer ↔ tenant
- Adicionar `asaas_customer_id` em `gerti.tenant` (NULL) **ou** tabela `payment_customer (tenant_id, provider, provider_account_id, asaas_customer_id)` para suportar o mesmo tenant em contas diferentes. → **payment_customer** (mais correto p/ multi-conta).

---

## 4. Integração Asaas (sidecar)

### 4.1 `integrations/asaas_client.py` (novo)
Molde: `ollama.py` (client tipado, timeout, transport injetável) + base do `billing`.
- `AsaasClient(base_url, api_key, *, timeout, transport)`; header `access_token: <key>`, `User-Agent: GroundControl`.
- Métodos (subset do `billing`, só o necessário):
  - `find_customer_by_document(cpf_cnpj)`, `create_customer(...)` (com `externalReference`=tenant/checkout id)
  - `create_payment(customer, value, due_date, billing_type, *, description, external_reference, credit_card_token=None, remote_ip)` — avulso
  - `tokenize_credit_card(data)` (POST `/creditCard/tokenize`) — **nunca** guardamos PAN; só o token
  - `create_subscription(customer, billing_type, value, next_due_date, cycle, *, credit_card_token=None, external_reference)` — recorrente (inclui PIX recorrente)
  - `get_pix_qrcode(payment_id)` → `{encodedImage(base64), payload(copia-e-cola), expirationDate}`
  - `get_billing_info(payment_id)` → boleto (`bankSlipUrl`, `barCode`, `identificationField`)
  - `cancel_subscription(id)`, `get_payment(id)`
- **Erros**: `AsaasUnavailable` (timeout/5xx → 503), `AsaasError` (4xx → mapeia `errors[].description`, vira 422/400) — molde do decorator `handle_asaas_exception` do `billing`.
- **Resolução de conta**: o client é instanciado com a `payment_provider_account` resolvida (Gerti default ou do MSP). Factory `asaas_for(account)`.
- **PIX**: garantir chave ativa (o `billing` gera aleatória se não houver — replicar `list_active_pix_keys`/`generate_random_pix_key`; em breve obrigatório no Asaas).

### 4.2 Config (`config.py`, pydantic-settings)
- `ASAAS_ENABLED` (feature-flag, default false), `ASAAS_BASE_URL` (default sandbox `https://api-sandbox.asaas.com/v3`), `ASAAS_API_KEY` (conta Gerti default), `ASAAS_WEBHOOK_TOKEN` (token default), `CHECKOUT_PUBLIC_BASE_URL`.
- Contas de MSP: `payment_provider_account.api_key_ref` aponta a um segredo (env `ASAAS_MSP_<slug>_KEY` ou um cofre simples; ver §8).

### 4.3 Webhook handler — `domain/asaas_webhook_service.py` + `routers/hooks.py`
- Endpoint **`POST /v1/hooks/asaas/payment`** (allowlist no TenantMiddleware).
- **Auth**: header `asaas-access-token` == `payment_provider_account.webhook_token` (compare_digest). Como há multi-conta, resolver a conta pelo token (lookup) — 401 se nenhum casar.
- **Idempotência**: `event_id` único em `asaas_webhook_event`; se já PROCESSED → 200 e sai.
- **Sempre 200** (mesmo evento ignorado), processa inline ou enfileira (ver §4.4).
- **Eventos** (subset do `billing`): `PAYMENT_CONFIRMED`, `PAYMENT_RECEIVED`, `PAYMENT_OVERDUE`, `PAYMENT_CREATED` (parcela de assinatura), `PAYMENT_REFUNDED`.
  - **PIX**: ignorar `CONFIRMED`, agir no `RECEIVED` (gotcha do `billing`).
  - **Cartão/Boleto**: agir no `CONFIRMED`/`RECEIVED`.
- **Ação por evento**:
  - pagamento de **checkout** (external_reference = checkout_session) confirmado → `ProvisioningService.provision(session)` (§6).
  - pagamento de **ciclo recorrente** (external_reference = invoice/contract) → `InvoiceService.mark_paid(invoice)` (#1P) e atualiza saldo se aplicável.
  - `OVERDUE` → marca `payment.overdue` + (futuro) suspende contrato / `InvoiceService.mark_overdue`.

### 4.4 Execução assíncrona
O `billing` usa RQ. O GC já tem o **`sidecar-worker`** (#1B). Opções:
- **MVP**: processar o webhook **inline** (transação curta; Asaas reentrega em falha) — mais simples, sem fila nova.
- **Robusto**: gravar `asaas_webhook_event(received)` e deixar o `sidecar-worker` processar (desacopla provisionamento lento do ack 200). **Recomendado** porque o provisionamento toca o Znuny (lento/external). → adicionar um loop no worker que drena eventos `received`.

---

## 5. Endpoints (sidecar) — fluxo público de checkout

Todos **públicos** (allowlist no TenantMiddleware), rate-limited, sem cookie de sessão.
- `GET  /v1/checkout/plans?audience=…` — planos públicos vendáveis (do catálogo §3.1).
- `POST /v1/checkout/sessions` — body: `plan_slug`, `applicant{razão social, CNPJ, email, subdomínio desejado, branding, admin user}`, `billing_type`, `target_tenant_id?`. Cria `checkout_session` (`started`), cria/acha Asaas customer, cria **subscription** (recorrente) **ou** **payment** (avulso) conforme `plan.billing_mode`, devolve `{session_id, guest_token, billing_type, pix?{qrcode,copiaecola}, boleto?{url,linha}, card?{status}}`.
  - Validações **antes** de cobrar: subdomínio/znuny_customer_id livres (mesma checagem do `OnboardingService`), CNPJ válido, plano ativo/público, valor ≥ mínimo (R$5 no `billing`).
- `POST /v1/checkout/sessions/{id}/card` — tokeniza cartão (recebe dados, chama `tokenize_credit_card`, cria payment/subscription com token). **Nunca** persistir PAN/CVV.
- `GET  /v1/checkout/sessions/{id}` (auth: `guest_token`) — status p/ polling do front (`awaiting_payment`→`provisioned`), e quando `provisioned`: subdomínio + URL de acesso.

### Console (admin) e Portal (cliente) — superfícies autenticadas
- **Console**: `POST /v1/admin/checkout/links` — gera link de contratação para um prospecto/tenant (operador-assistido). Lista de pagamentos/assinaturas por tenant (`GET /v1/admin/tenants/{id}/payments`).
- **Portal**: `POST /v1/checkout/sessions` reutilizado com `target_tenant_id` = tenant logado (expandir/recarregar: comprar mais horas, novo contrato) — exige sessão `gsid`.

---

## 6. Provisionamento pós-pagamento — `domain/provisioning_service.py` (decisão em aberto)

> Você marcou **"outro"** no pós-pagamento. **Recomendação** (modelo
> *pré-cadastro → paga → webhook provisiona*, combinando auto-onboarding):

1. **Checkout** grava o `applicant` na `checkout_session` (tenant ainda **não** criado — nada no Znuny/`gerti.tenant`). Status `awaiting_payment`.
2. **Pagamento confirmado** (webhook `RECEIVED`/`CONFIRMED`):
   - Se `target_tenant_id` **NULL** (novo cliente): `OnboardingService.onboard(applicant)` (cria Znuny CustomerCompany/User + `gerti.tenant`/branding/roles) **e** `ContractService.create(plan→contrato, status=active)`.
   - Se `target_tenant_id` **presente** (expansão/recarga): só `ContractService.create`/recarga de saldo + ativa.
   - Vincula `payment.tenant_id/contract_id`, marca `checkout_session=provisioned`, dispara e-mail "bem-vindo + subdomínio + 1º acesso".
3. **Idempotente**: reentrega do webhook não duplica (guarda por `event_id` + `checkout_session.status`).

**Por que pré-cadastro (não criar tenant antes de pagar):** evita tenants "fantasma"/lixo no Znuny de quem abandona o checkout (já vimos lixo de teste poluindo o Znuny). O tenant nasce **pago**.

**Alternativas (se você preferir):**
- (A) **Onboarding imediato + ativação no pagamento**: cria tenant `draft`/suspenso no checkout, ativa no webhook. Permite "reservar" subdomínio, mas gera tenants pendentes.
- (B) **Só registra contrato** (sem onboarding): exige tenant pré-existente (operador faz onboarding). Menos self-service.

→ **Confirmar qual modelo** antes de implementar o §6 (é a única peça que muda o fluxo de ponta a ponta).

---

## 7. Frontend — a página de contratação

**Onde:** o portal (`apps/portal`) é por-tenant e exige login; a `landing/` é estática.
A contratação é **pública e sem tenant**. **Recomendação: novo app `apps/checkout` (Nuxt 3 SSR)** — como o `billing-checkout` é separado no projeto de referência. Isola o fluxo público (sem cookie de tenant), com identidade neutra/Gerti ou branding do MSP quando `?ref=<msp>`.

Telas:
1. **Planos** (`/` ou `/planos`) — cards dos planos públicos (de `GET /v1/checkout/plans`), filtrados por `audience`.
2. **Dados** (`/contratar/[plano]`) — form: empresa (CNPJ, razão/fantasia), subdomínio desejado (com checagem de disponibilidade ao vivo), usuário admin, branding básico (opcional).
3. **Pagamento** — escolha do método (PIX / PIX recorrente / Boleto / Cartão). Componentes:
   - **PIX**: QR (base64) + copia-e-cola + polling do status.
   - **Boleto**: link do PDF + linha digitável.
   - **Cartão**: form tokenizado (envia ao `/card`; idealmente tokenização client-side ou via sidecar — **nunca** o PAN toca nosso banco).
4. **Confirmação** — polling `GET /v1/checkout/sessions/{id}` → quando `provisioned`, mostra subdomínio + botão "Acessar o portal".

Reuso de componentes do portal/admin (ProgressBar, charts não; UButton/UInput do Nuxt UI). Tema/branding via `?ref` (conta MSP) ou neutro (Gerti).
**Deploy**: serviço `checkout` no `docker-compose.yml` (profile `gerti`), subdomínio `contratar.gerti.com.br` / `contratar.was.dev.br` (ingress Cloudflare, padrão D3/D15). Admin "gerar link" e Portal "contratar mais" reaproveitam os mesmos endpoints.

---

## 8. Segurança

- **Superfície pública nova** → rate-limit por IP/CNPJ no `/v1/checkout/*`; CAPTCHA opcional na criação de sessão; valor mínimo (R$5).
- **Webhook**: token (`asaas-access-token`) por conta, compare_digest; idempotência; sempre 200; logar evento bruto em `asaas_webhook_event`. Considerar allowlist de IPs do Asaas (defesa em profundidade).
- **Dados de cartão**: **jamais** persistir PAN/CVV; só `creditCardToken` do Asaas. Tokenização preferencialmente sem o dado passar “parado” pelo nosso log.
- **Segredos**: `ASAAS_API_KEY`/`ASAAS_WEBHOOK_TOKEN` da Gerti em `.env.prod` (gitignored). Para **multi-conta MSP**, as keys ficam em segredo referenciado por `payment_provider_account.api_key_ref` — MVP: env `ASAAS_MSP_<slug>_KEY`; evolução: cofre (idealmente criptografado at-rest, não em claro no Postgres).
- **RLS**: `payment`/`payment_customer` tenant-scoped quando o tenant existe; `checkout_session`/`plan`/`provider_account`/`webhook_event` são não-tenant (BYPASSRLS, fail-closed na resolução de conta).
- **Não vazar existência** de subdomínio/tenant em erros públicos (mensagens genéricas).
- **Anti-replay de provisionamento**: `checkout_session.status` + `event_id` garantem uma única execução.

---

## 9. Fases de entrega

**Fase 0 — Spike Asaas (sandbox)** · spike doc em `docs/superpowers/spikes/`.
Conta sandbox, criar customer+payment PIX, pegar QR, simular webhook `PAYMENT_RECEIVED`. Valida client + auth + formato de webhook. (Sem tocar prod.)

**Fase 1 — MVP self-service (conta Gerti, 1 plano recorrente, cartão+PIX)**
- migration `0021` (todas as tabelas, já prontas p/ flexibilidade).
- `AsaasClient` + config + feature-flag.
- `POST /v1/checkout/sessions` (subscription, cartão+PIX) + `/card` + `GET status`.
- webhook `/v1/hooks/asaas/payment` (idempotente; inline ou worker).
- `ProvisioningService` (modelo §6 confirmado) reusando #1G + #1C.
- `apps/checkout` (planos → dados → pagamento → confirmação) para 1 plano `saas_product`.
- Gates + **e2e** (estende `e2e/`): sandbox, criar sessão, simular webhook, assert tenant provisionado, idempotência.

**Fase 2 — Boleto + pré-pago avulso + conectar ao #1P**
- `billing_type=BOLETO`; `billing_mode=one_off` p/ `hour_bank`/`credit_*`/`service_count` (recarga).
- webhook de **ciclo recorrente** → `InvoiceService.mark_paid` (liga Asaas ao faturamento #1P existente: worker #1B fecha ciclo → gera fatura → cria cobrança Asaas → webhook marca paga).
- Portal "contratar mais / recarregar"; Console "gerar link".

**Fase 3 — Multi-conta (MSP) + "ambos"**
- `payment_provider_account owner_kind=msp`; resolução de conta por plano/tenant/`?ref`.
- Onboarding de conta Asaas do MSP no Console; branding do checkout por MSP.

**Fase 4 (opcional) — NF-e + dunning**
- NF-e via Asaas (como `billing`: `municipalServiceId`, impostos) se o produto exigir fiscal.
- Régua de cobrança: `OVERDUE` → suspende contrato (#1C status `suspended`) + notifica; refund.

---

## 10. Config, deploy e operação

- **Novos segredos** (`.env.prod`): `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `ASAAS_BASE_URL`, `ASAAS_ENABLED=true`, `CHECKOUT_PUBLIC_BASE_URL`. (multi-conta: `ASAAS_MSP_*` ou cofre.)
- **Webhook no Asaas**: cadastrar a URL `https://api-dev.was.dev.br/v1/hooks/asaas/payment` (ou domínio prod) com o `asaas-access-token` = nosso `ASAAS_WEBHOOK_TOKEN`, eventos de PAYMENT.
- **Deploy** (padrão profile `gerti`, ver `.ia/OPS.md`): migration `0021` via `sidecar-migrate`; rebuild `sidecar` (+`sidecar-worker` se processar fila); novo serviço `checkout` (build + ingress Cloudflare `contratar.*` read-modify-write D3/D15 + DNS). Sem tocar Znuny.
- **Sandbox primeiro** em staging (= prod, ambiente único) com `ASAAS_BASE_URL` sandbox; trocar p/ produção só após e2e verde.

## 11. Testes
- **Unit** (sidecar, uv/pytest): `AsaasClient` com `httpx.MockTransport` (molde Ollama); idempotência de webhook; resolução de conta; provisioning (mock Znuny GI).
- **e2e** (`e2e/`): fluxo de checkout contra **sandbox** (criar sessão → simular/curl webhook `PAYMENT_RECEIVED` → assert tenant+contrato provisionados → limpar throwaway). Marcar `@destructive` (cria tenant) e rodar manual.
- **Gates**: ruff+mypy+pytest (sidecar); typecheck+vitest (apps/checkout). Webhook NUNCA derruba (sempre 200; falha vira `asaas_webhook_event.failed` + retry).

## 12. Riscos / pontos de atenção
- **PIX recorrente**: confirmar suporte/limitações no Asaas (assinatura `billingType=PIX`); pode exigir chave PIX ativa (gerar como o `billing`).
- **Provisionamento toca o Znuny** (lento/externo) → preferir processamento no worker (não no request do webhook) p/ ack rápido + retry.
- **Multi-conta**: guardar keys de MSP com segurança (não em claro no DB) — definir cofre antes da Fase 3.
- **Reconciliação**: divergência Asaas×local — job de reconciliação (lista pagamentos Asaas e concilia) como o `billing` faz.
- **Pós-pagamento (§6)**: decisão de produto pendente — trava o desenho do fluxo.

## 13. Atualização de documentação (padrão voyager)
Ao implementar: `.ia/ARCHITECTURE.md` (novo serviço `checkout` + fluxo Asaas), `.ia/OPS.md` (runbook de deploy + cadastro do webhook + segredos), `.ia/DECISIONS.md` (ADR: Asaas via HTTP, multi-conta, pré-cadastro-antes-de-pagar), `.ia/INTEGRATION.md`, e spec/design em `docs/superpowers/`.

---

### Referências
- Padrão Asaas: `~/projetos/billing/billing-backend/apps/integrations/connections/asaas/base.py`, `.../models/asaas_webhook_event.py`, `.../authentication/asaas.py`, `~/projetos/billing/billing-checkout/`.
- GC: `apps/sidecar/.../domain/onboarding_service.py`, `contract_service.py`, `invoice_service.py`, `integrations/{ollama,webhook_sig,znuny_customer_admin}.py`, `routers/hooks.py`, `middleware/tenant.py`, `models/{contract,invoice,enums,tenant}.py`, `alembic/versions/0017_invoice.py` (molde RLS).
