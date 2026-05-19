# Spec #1F-a — Portal Cliente white-label (fatia vertical) — Design

**Status:** aprovado no brainstorming (2026-05-17)
**Repo:** `ground-control` (NÃO o repo `gerti`, que é só a apresentação)
**Depende de:** #1C (motor de contratos — pronto, em prod). Difere #1D
(Auth Bridge OIDC) e o resto do #1E (tickets/catálogo/dashboards).

## 1. Objetivo (uma frase)

Pôr o **white-label de pé ponta-a-ponta**: cada cliente da Gerti acessa
`<tenant>.suporte.gerti.com.br`, vê um portal com a **marca dele**, faz
login com credencial validada no Znuny e enxerga **seus contratos e
saldos** (reaproveitando o motor #1C), tudo isolado por tenant via RLS.

## 2. Decisões travadas (constraints — não renegociar no plano)

1. **Sempre exatamente 1 Znuny.** Sem instâncias dedicadas, sem modo
   híbrido. `gerti.znuny_instance` continua existindo (do #1C) mas com
   1 linha; multi-tenant é 100% lógico (CustomerCompany/filas no Znuny
   único + RLS no schema `gerti`). Nada de roteamento de instância.
2. **Tudo é white-label, sempre.** Não existe portal genérico. Todo
   tenant tem branding; subdomínio sem branding cai num **tema-default
   neutro seguro** (nunca quebra), nunca numa marca "Gerti".
3. **Auth mínima = credencial Znuny via sidecar.** Portal manda
   usuário/senha pro sidecar, que valida no **CustomerAuth do Znuny**
   (Generic Interface) e devolve **cookie de sessão assinado**
   (HttpOnly/Secure/SameSite, server-side). Sem servidor OIDC. Migra
   pro #1D depois trocando só a camada de login — telas não mudam.
4. **Uma visão real:** contratos + saldo do tenant (read-only),
   reusando `ConsumptionService.balance` do #1C. Sem tickets/catálogo/
   dashboards nesta spec.
5. **Portal em `ground-control/apps/portal`** (hoje só `.gitkeep`):
   Nuxt 3 SSR + Nuxt UI v3 + Tailwind + Pinia + TypeScript (stack do
   roadmap).

## 3. Arquitetura

```
Navegador
  │  (https://acme.suporte.gerti.com.br)
  ▼
Nuxt 3 SSR (apps/portal)  ── Nitro server middleware: Host→subdomínio
  │                            → GET /v1/branding (SSR) → injeta tema
  │  (cookie de sessão; fetch server-side via rota proxy Nuxt)
  ▼
Sidecar FastAPI (apps/sidecar)
  ├─ TenantMiddleware (JÁ EXISTE): subdomínio → tenant → set GUC
  │                                 app.current_tenant
  ├─ schema gerti  (tenant_branding, contract…) — RLS por tenant (#1C)
  └─ Znuny Generic Interface (REST) — só validação de credencial
```

O Nuxt **nunca** fala direto com o Znuny. O sidecar é a única porta.
O `TenantMiddleware` do sidecar **já** resolve `<sub>.suporte.gerti.com.br`
→ tenant → `app.current_tenant`; reaproveitamos isso (zero código novo
de resolução). Endpoint desconhecido de subdomínio já responde 404 (o
Nuxt trata como "tenant inexistente" → tema default + mensagem).

## 4. Componentes

### 4.1 Dados — migration `0011_tenant_branding` (`apps/sidecar/alembic`)

Tabela `gerti.tenant_branding`:

| coluna | tipo | nota |
|---|---|---|
| `tenant_id` | uuid PK, FK→`gerti.tenant.id` ON DELETE CASCADE | 1:1 com tenant |
| `display_name` | text NOT NULL | nome exibido no portal |
| `logo_url` | text NULL | URL absoluta do logo (asset externo p/ MVP) |
| `primary_color` | text NOT NULL default `'#2563EB'` | hex |
| `accent_color` | text NOT NULL default `'#1E40AF'` | hex |
| `default_theme` | text NOT NULL default `'light'` | `light`\|`dark` |
| `support_email` | text NULL | rodapé/contato |
| `created_at`/`updated_at` | timestamptz | padrão #1C (`onupdate`) |

**RLS:** mesmo template do #1C — `ENABLE` + `FORCE ROW LEVEL SECURITY`,
policy `USING/WITH CHECK tenant_id = NULLIF(current_setting(
'app.current_tenant', true), '')::uuid`, GRANT a `gerti_app`. Leitura
pré-auth funciona porque o `TenantMiddleware` seta a GUC **a partir do
subdomínio** (sem credencial) → a sessão enxerga só o branding do
próprio tenant. Sem necessidade de role privilegiada/bypass.

Branding é **semeado por script idempotente** (`seed_demo_branding.py`,
no padrão do `seed_demo_contracts.py` do #1C) — Aurora ganha um branding
de demonstração. UI admin de branding fica para spec futura (#1G).

### 4.2 Sidecar — novos routers (subconjunto mínimo do futuro #1E)

Todos sob `apps/sidecar/src/gerti_sidecar/routers/`, incluídos em
`main.py` com `prefix=settings.api_v1_prefix`.

- **`GET /v1/branding`** — *não autenticado*, tenant-scoped via
  subdomínio (TenantMiddleware já setou a GUC). Retorna
  `{display_name, logo_url, primary_color, accent_color, default_theme,
  support_email}`. Se a GUC não resolveu (host sem subdomínio) → 404
  (Nuxt aplica default). Payload mínimo, sem dado sensível → seguro
  expor sem auth.
- **`POST /v1/auth/login`** — body `{username, password}`. Resolve
  tenant pela GUC (subdomínio). Chama o **Znuny Generic Interface**
  (webservice de auth de customer — ver §6 Riscos) p/ validar. Sucesso
  → cria sessão como **JWT HS256** assinado com `SESSION_SECRET` (de
  config) carregando `{tenant_id, customer_login, exp}`; seta cookie
  `gsid` HttpOnly, Secure, SameSite=Lax, expiração configurável.
  Falha de credencial → 401; Znuny inacessível → 503.
- **`POST /v1/auth/logout`** — limpa o cookie.
- **`GET /v1/me`** — lê a sessão do cookie; valida que `tenant_id` da
  sessão == tenant do subdomínio atual (anti cookie cross-tenant);
  retorna `{tenant_id, display_name, customer_login}`. Sem sessão →401.
- **`GET /v1/contracts`** — *autenticado*. Deriva `tenant_id` da
  sessão, abre `tenant_session_scope(tenant_id)` (seam do #1C) → RLS →
  lista contratos do tenant com `{code, type, status, starts_on,
  ends_on, saldo:{kind,remaining}}` via `ConsumptionService.balance`.
  Read-only.

**Dependência de auth (seam):** uma dependency FastAPI
`get_current_session(request)` que (1) lê/valida o cookie `gsid`,
(2) confere `session.tenant_id == request.state.tenant.id`
(o TenantMiddleware popula `request.state.tenant`), (3) injeta a
sessão. `/v1/contracts` e `/v1/me` usam-na; `/v1/branding` e
`/v1/auth/login` não.

**Cliente Znuny GI:** módulo fino
`gerti_sidecar/integrations/znuny_gi.py` — só `authenticate_customer(
login, password) -> bool` nesta spec. Endpoint/token do webservice vêm
de `gerti.znuny_instance` (campos `base_url`,
`webservice_token_secret_ref`) — a única instância.

### 4.3 Portal — Nuxt 3 SSR (`apps/portal`)

- **Nitro server middleware** (`server/middleware/branding.ts`): lê
  `Host` → deriva subdomínio → `GET {SIDECAR_URL}/v1/branding`
  server-side → guarda em `event.context.branding`; cache em memória
  por subdomínio (TTL curto, ex. 60s). Falha/404 → objeto de
  **tema-default neutro**. Sem flash: o tema vira **CSS custom
  properties** no `<html>` no SSR (`app.head`/`useHead` server-side),
  pintado antes do paint.
- **Páginas:**
  - `/login` — formulário branded; posta numa **rota server Nuxt**
    (`server/api/auth/login.post.ts`) que repassa ao sidecar e
    re-emite o cookie como first-party do subdomínio.
  - `/` — landing autenticada: SSR busca `/v1/me` e `/v1/contracts`
    (encaminhando o cookie); lista contratos+saldo branded. Sem sessão
    → redirect SSR p/ `/login`.
  - logout → rota server → sidecar `/v1/auth/logout` → limpa cookie →
    `/login`.
- **Tema:** design tokens como CSS vars (`--brand-primary`,
  `--brand-accent`, logo, nome); Nuxt UI v3 + Tailwind lendo os tokens.
- **Config:** `SIDECAR_URL` (interno), domínio base, `SESSION_COOKIE`
  name — via runtime config.

## 5. Fluxos

- **Não-auth (login):** browser →(subdomínio) Nuxt SSR → Nitro mw →
  sidecar `GET /v1/branding` (GUC por subdomínio, RLS) → login pintado
  com a marca.
- **Login:** form → rota server Nuxt → sidecar `POST /v1/auth/login` →
  Znuny GI valida → cookie `gsid` assinado → redirect `/`.
- **Visão autenticada:** Nuxt SSR (cookie) → `GET /v1/me` +
  `GET /v1/contracts` → sidecar valida sessão, confere tenant==
  subdomínio, abre `tenant_session_scope` → RLS → saldos → página
  branded.

## 6. Erros & segurança

- Subdomínio desconhecido → sidecar 404 → Nuxt: tema default + página
  "ambiente não encontrado" (sem vazar marca alheia).
- Znuny fora no login → 503 amigável; credencial inválida → 401.
- Sessão expirada/ausente em rota protegida → redirect SSR p/ `/login`
  branded.
- Falha no `/v1/branding` → tema default; portal ainda funcional.
- **Anti cross-tenant:** `get_current_session` rejeita (401/403) se o
  `tenant_id` do cookie ≠ tenant do subdomínio (cookie roubado de
  outro tenant não vale). Cookie HttpOnly/Secure/SameSite=Lax; segredo
  de assinatura em config (`.env.prod`, nunca commitado). RLS continua
  sendo a defesa de dados (fail-closed sem GUC, como no #1C).
- Sem armazenar senha em lugar nenhum; senha só trafega
  portal→sidecar→Znuny no momento do login (HTTPS).

## 7. Riscos / assunções (resolver no plano com spike)

- **R1 (alto):** validar credencial de customer exige um **webservice
  de auth no Znuny** exposto via Generic Interface. Znuny core **não**
  expõe CustomerAuth por GI por padrão. *Mitigação no plano:* 1ª task =
  **spike** — configurar/importar um webservice mínimo no Znuny
  (operation de SessionCreate/CustomerUserAuth ou equivalente) na
  instância de prod, documentar em `.ia/`. Não é o #1B (não precisa de
  GertiHooks.opm); é config Znuny-side via SysConfig/import de
  webservice. Se inviável no core, fallback documentado: validar via
  leitura read-only do schema `znuny` (tabela de customer + hash de
  senha) — decisão tomada no spike, registrada como ADR.
- **R2 (médio):** cookie cross-subdomínio. Mitigado por SameSite=Lax +
  cookie por host do subdomínio + checagem tenant==subdomínio.
- **R3 (baixo):** flash de tema. Mitigado por SSR injetando CSS vars no
  HTML inicial (sem JS client-side decidindo tema).

## 8. Testes

- **Sidecar (pytest + testcontainers, padrão #1C):**
  - migration `0011`: `tenant_branding` com RLS ENABLE+FORCE; teste
    negativo (sem GUC → 0 linhas) somado ao S1 existente.
  - `/v1/branding`: resolve por subdomínio; tenant sem branding →
    payload default; host sem subdomínio → 404.
  - `/v1/auth/login`: Znuny GI **mockado** — sucesso emite cookie
    válido; senha errada →401; Znuny down →503.
  - `get_current_session`: cookie válido ok; cookie de outro tenant →
    rejeitado; expirado → rejeitado.
  - `/v1/contracts`: tenant-scoped, RLS fail-closed, devolve saldos do
    tenant da sessão (reusa fixtures/seed do #1C).
- **Portal (Vitest + @nuxt/test-utils):** middleware de branding
  (subdomínio→tokens; default em falha); guard SSR (sem sessão →
  redirect login); render do tema a partir de tokens.
- **E2E smoke:** seed branding Aurora → request a
  `aurora.suporte.gerti.com.br` (Host header) → login branded → login
  como customer Aurora (mesmo da demo #1C/Znuny) → lista contratos
  Aurora (os 6 do seed #1C). Roda como o gate dos demais (CI/`make`).

## 9. Fora de escopo (YAGNI — não implementar)

Tickets, catálogo de serviços, abertura de chamado, dashboards
executivos (#1E/#1F full) · servidor/fluxo OIDC PKCE (#1D) · UI admin
de branding e onboarding de tenant (#1G) · multi-Znuny / instâncias
dedicadas · upload de logo (usa URL externa por enquanto) · i18n.

## 10. Entregável / definição de pronto

Subdomínio `aurora.suporte.gerti.com.br` (Host) serve um portal com a
marca da Aurora; login com um customer Aurora (validado no Znuny);
após login, a lista de contratos/saldos da Aurora (os 6 do #1C)
aparece; outro subdomínio sem branding cai no tema default; RLS
fail-closed provado; gate (ruff+mypy+pytest sidecar; vitest portal;
e2e smoke) verde; deploy aditivo documentado em `.ia/` (profile/serviço
do portal no compose, como o sidecar do #1C).
