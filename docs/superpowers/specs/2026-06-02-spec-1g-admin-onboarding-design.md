# Spec #1G — Console de Administração (Gerti): onboarding de cliente + criar contrato

**Data:** 2026-06-02
**Status:** aprovado (escopo travado no brainstorming) → pronto para plano/execução
**Escopo deste ciclo (#1G-a):** app admin separado para a equipe Gerti, com (1) login
de **agente Znuny**, (2) **onboarding de cliente** (tenant + branding + usuários + papéis
num fluxo) e (3) **criar contrato** dos 6 tipos. Gestão avançada (editar contrato, fechar
ciclo, aprovar glosa, aplicar reajuste pela UI) fica para **#1G-b**.

## 1. Decisões (brainstorming 2026-06-02)
- **D-1G-1**: UI em **app admin separado** (equipe Gerti), subdomínio próprio
  (`gerti.was.dev.br` em teste; `admin.suporte.gerti.com.br` em prod). NÃO é o portal
  white-label do cliente. Identidade visual = Gerti/WAS (não white-label).
- **D-1G-2**: autenticação = **agente Znuny** via Generic Interface (padrão D14, mas
  `Kernel::System::Auth`/`UserLogin` em vez de `CustomerAuth`/`CustomerUserLogin`).
  Qualquer agente Znuny válido entra no admin (a base de agentes já é a equipe Gerti).
- **D-1G-3**: escopo = **onboarding + criar contrato** (ver acima).
- **D-1G-4**: subdomínio white-label do cliente continua **manual** (DNS + ingress
  Cloudflare são passo de operação). A UI cria tenant/branding/usuários/contratos; mostra
  ao operador o subdomínio a registrar. Automação Cloudflare = follow-up.

## 2. Incógnitas a resolver no SPIKE (bloqueante — R1G)
Antes de implementar, um spike confirma os 2 mecanismos de Znuny (como o #1F T1 fez p/ auth):
1. **Auth de agente via GI**: `Session::SessionCreate` aceita `UserLogin`+`Password` →
   `SessionID`? Em qual webservice? (provável: estender o webservice existente ou criar
   `GertiAdminAuth`). `seed-authcheck.pl` confirma que `Kernel::System::Auth->Auth` funciona
   localmente; o spike valida o caminho **GI**.
2. **Escrita de cliente via GI**: existem operações GI para criar `CustomerCompany` +
   `CustomerUser` + setar senha? (Spec #0: escrita no Znuny SEMPRE via Generic Interface,
   nunca SQL direto.) Se o GI não expuser isso trivialmente, o spike decide o mecanismo
   suportado (operação GI custom no webservice). **Sem isso, o onboarding não cria o login.**

O spike CONGELA: assinaturas do cliente GI de escrita, shape da sessão admin, e os contratos
(schemas request/response) dos endpoints — para os agentes paralelos não divergirem.

## 3. Arquitetura

### 3.1 Sidecar — sessão admin (cross-tenant)
- `auth/admin_session.py`: JWT HS256 com `{agent_login, role:"gerti_staff", exp}`, cookie
  **próprio** `gsid_adm` (NUNCA colide com o `gsid` do cliente). `get_admin_session`
  (401 sem/with inválida). **Não é tenant-scoped** — o admin opera cross-tenant.
- `integrations/znuny_agent_auth.py`: `authenticate_agent(login, password) -> bool`
  (GI agent SessionCreate; mesmo contrato failure-safe do `authenticate_customer`).

### 3.2 Sidecar — DB: dois caminhos claros
- **Criar tenant/branding/papéis/usuário**: escrita cross-tenant → usa **AdminSessionLocal**
  (BYPASSRLS, D16) com `tenant_id` explícito. (Mesmo padrão dos seeds que rodam como
  `gerti_admin_user`.)
- **Criar contrato para um tenant X**: abre `tenant_session_scope(X)` na role app
  (RLS-subject) e usa `ContractService(session).create(NewContract)` — assim TODAS as
  invariantes #1C (RLS, enums, append-only) valem, sem reescrever regra.
- **Znuny (CustomerCompany/User)**: via Generic Interface (cliente de escrita do spike),
  NUNCA SQL direto no schema do Znuny.

### 3.3 Sidecar — endpoints (`/v1/admin/*`, todos exigem `get_admin_session`)
- `POST /v1/admin/auth/login` (agente) · `POST /v1/admin/auth/logout`.
- `GET  /v1/admin/tenants` — lista (id, trade_name, subdomain, contract_count, status).
- `POST /v1/admin/tenants` — **onboarding**: cria CustomerCompany+CustomerUser(s) no Znuny
  (GI) + `gerti.tenant` + `gerti.tenant_branding` + `gerti.portal_user_role` (1 por usuário).
  Idempotente por `znuny_customer_id`/subdomínio. Retorna o tenant + o subdomínio a registrar.
- `GET  /v1/admin/tenants/{id}` — detalhe (branding, usuários/papéis, contratos).
- `POST /v1/admin/tenants/{id}/contracts` — cria contrato (6 tipos) via `ContractService`.
- `POST /v1/admin/tenants/{id}/users` — adiciona usuário (Znuny customer_user + papel).

### 3.4 App admin (Nuxt) — `apps/admin/`
- App **separado** (própria imagem/serviço compose `admin`, subdomínio próprio). Reusa Nuxt
  UI + a identidade Gerti/WAS. Server proxies para `/v1/admin/*` repassando o cookie `gsid_adm`.
- Páginas: `/login` (agente), `/` (lista de clientes), `/clientes/novo` (assistente:
  dados + branding + usuários/papéis), `/clientes/[id]` (detalhe), `/clientes/[id]/contratos/novo`
  (form por tipo de contrato). Guarda de rota por sessão admin (middleware nomeada).

## 4. Segurança
- Sessão admin é **separada** do cliente (cookie distinto, role `gerti_staff`); endpoints
  `/v1/admin/*` exigem `get_admin_session` → 401 sem ela. Os endpoints do cliente
  (`require_admin` do #1H) continuam intactos e NÃO aceitam a sessão admin (cookies distintos).
- Escrita cross-tenant só pelo caminho admin BYPASSRLS, e SÓ nos endpoints `/v1/admin/*`.
- `SESSION_SECRET` forte já exigido em prod (#1H). Senhas de cliente nunca logadas.
- Toda escrita no Znuny via GI (Spec #0) — zero SQL direto no schema Znuny.

## 5. Testes
- Spike: prova viva do agent-auth GI e do customer-create GI (script, como R1 do #1F).
- Sidecar: `authenticate_agent` (200/401/503 failure-safe); `get_admin_session`
  (401/role); onboarding cria tenant+branding+papéis (+ chama o GI write-client mockado);
  contrato criado via ContractService respeita invariantes #1C; **isolamento**: cookie
  cliente não acessa `/v1/admin/*` e vice-versa.
- Admin UI (vitest): guarda por sessão, render do assistente, validação do form de contrato.
- e2e: onboarding de um tenant fictício "Acme" → login do novo admin no portal → vê contrato.

## 6. Deploy
Novo serviço `admin` (profile `gerti`, aditivo) + subdomínio Cloudflare (manual, D4-style).
Migrations: **#1G-a não adiciona tabela nova** (admins = agentes Znuny; tenant/branding/role
já existem) → sem migration nova (evita colisão na cadeia em execução paralela). Auditoria de
onboarding (`gerti.admin_audit`) fica como follow-up opcional.

## 7. Não-objetivos (YAGNI)
- Sem editar contrato / fechar ciclo / glosa / reajuste pela UI (#1G-b).
- Sem automação de subdomínio Cloudflare (manual neste ciclo).
- Sem gestão de agentes Znuny (isso é no próprio Znuny).
- Sem OIDC/SSO (#1D).
