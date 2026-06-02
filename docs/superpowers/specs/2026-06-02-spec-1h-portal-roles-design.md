# Spec #1H — Papéis no login do Portal (admin × help-desk)

**Data:** 2026-06-02
**Status:** aprovado (brainstorming) → em implementação
**Escopo:** camada de papéis/autorização no Portal do Cliente (Ground Desk).
NÃO inclui a feature de tickets (#1E, deferida) — help-desk vê um placeholder.

## 1. Problema

Hoje todo usuário autenticado do portal vê tudo do seu tenant (contratos +
valores financeiros). Os clientes (ex.: Aurora) têm dois tipos de usuário:

- **admin do cliente** — acompanha **contratos e valores** (financeiro);
- **help-desk / operação** — acompanha **tickets** (a operação em si).

Precisamos diferenciar o que cada papel acessa no MESMO portal white-label.

## 2. Decisões (do brainstorming)

- **D-1H-1**: ambos os papéis são usuários **do cliente**, no mesmo portal.
- **D-1H-2**: escopo deste ciclo = **camada de papéis + gating**. Admin vê
  contratos+valores; help-desk loga e cai numa área de tickets **"em breve"**.
  Tickets reais ficam para o #1E.
- **D-1H-3**: a verdade do papel mora no **schema `gerti`** (Abordagem A) —
  não nos grupos do Znuny. Papel é um conceito de produto do portal; Znuny
  segue intocado (só lemos `customer_user.login` read-only, como já hoje).
- **D-1H-4**: default **least-privilege = `helpdesk`** (usuário não-mapeado e
  token sem claim `role` ⇒ helpdesk). Nunca conceder admin por omissão.

## 3. Identidade: como o papel casa com o usuário

O JWT de sessão (`gsid`) carrega `customer_login`, que hoje **é o e-mail**
digitado no login (`auth.py`: `encode_session(tenant_id, body.username, ...)` —
login é sempre por e-mail, ADR D14/decision-login-by-email). Portanto o papel
é resolvido **pelo e-mail/identificador de login** (case-insensitive), o mesmo
valor que vai para o claim `customer_login`. Sem dependência do `login` interno
do Znuny resolvido em `znuny_gi`.

## 4. Modelo de dados (schema `gerti`)

Enum Postgres `gerti.portal_role` = `('admin','helpdesk')` + `StrEnum`
`PortalRole` espelhando (em `models/enums.py`).

Tabela `gerti.portal_user_role`:

| coluna | tipo | nota |
|---|---|---|
| `id` | uuid pk default gen_random_uuid() | |
| `tenant_id` | uuid not null FK gerti.tenant(id) ON DELETE CASCADE | escopo RLS |
| `customer_login` | text not null | normalizado **lower** no insert/lookup; = claim `customer_login` (e-mail) |
| `role` | gerti.portal_role not null | |
| `created_at`/`updated_at` | timestamptz not null default now() | |

- **Único** `(tenant_id, lower(customer_login))` — um papel por usuário/tenant.
- **FORCE RLS por tenant** com o template canônico (igual `0011`):
  `USING/WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)`,
  `GRANT SELECT,INSERT,UPDATE,DELETE ... TO gerti_app`.
- Migration `0012_portal_user_role` (down_revision `0011_tenant_branding`),
  reusando os helpers `_enable_tenant_rls`/`_disable_tenant_rls`.
- Model SQLAlchemy `PortalUserRole` em `models/portal_user_role.py`, exportado
  em `models/__init__.py`.

## 5. Resolução do papel no login

Novo service `domain/portal_role_service.py`:

```python
async def resolve_role(session, customer_login: str) -> PortalRole
```

- `SELECT role FROM gerti.portal_user_role WHERE lower(customer_login)=lower(:login)`
  (RLS já escopa por tenant — sessão tenant-scoped). 0 linhas ⇒ `PortalRole.helpdesk`.

`POST /v1/auth/login` (router `auth.py`), após `authenticate_customer` == True:

```python
async with tenant_session_scope(tenant.id) as s:
    role = await resolve_role(s, body.username)
token = encode_session(str(tenant.id), body.username, role.value, settings)
```

- A resolução é tenant-scoped (RLS) — defesa em profundidade.
- Falha de DB na resolução ⇒ **helpdesk** (least-privilege), nunca derruba o
  login (failure-safe, paridade com a resolução e-mail→login).

## 6. JWT / sessão

`SessionPayload` ganha `role: str`. `encode_session(tenant_id, customer_login, role, settings)`.
`decode_session`: se o token não traz `role` (tokens antigos em trânsito, TTL 8h)
⇒ default `"helpdesk"` (least-privilege; re-login devolve admin). `get_current_session`
inalterado fora isso (401 sem sessão, 403 cross-tenant).

## 7. Autorização (sidecar)

Nova dependency em `auth/session.py`:

```python
async def require_admin(session = Depends(get_current_session)) -> SessionPayload:
    if session["role"] != "admin":
        raise HTTPException(403, detail="forbidden_role")
    return session
```

Aplicada a **nível de router** (admin-only — dados de contrato + valores):

- `routers/contracts.py` → `APIRouter(..., dependencies=[Depends(require_admin)])`
  (cobre `/contracts`, `/contracts/{id}`, `/contracts/{id}/consumption`, `/series`).
- `routers/dashboard.py` → idem.

`GET /v1/me` permanece aberto a **qualquer** sessão e passa a devolver `role`
(o portal decide a navegação). `MeResponse` ganha `role: str`.

## 8. Portal (Nuxt)

- **`composables/useMe.ts`**: `useAsyncData('me', () => $fetch('/api/portal/me', { headers: cookie }))`.
  Retorna `{ tenant_id, display_name, customer_login, role } | null`.
- **`middleware/auth.global.ts`** (SSR, roda em toda navegação):
  - rota `/login` → libera;
  - sem sessão (`me == null`) → redireciona `/login`;
  - rotas **admin-only** (`/` e `/contratos/...`): se `role !== 'admin'` →
    redireciona `/tickets`;
  - `/tickets` → libera para qualquer sessão.
- **`pages/tickets.vue`** (nova): área branded **"Tickets — em breve"**
  (placeholder do #1E), com a mesma qualidade visual do resto (ícone, cópia
  clara, assinatura WAS via layout). É a home do help-desk.
- **`layouts/default.vue`**: nav por papel via `useMe` — admin vê
  **Contratos** (+ "Tickets" marcado *em breve*); help-desk vê só **Tickets**.
  Header/rodapé/branding inalterados.
- **Login**: após sucesso continua `navigateTo('/')`; o middleware global
  redireciona o help-desk para `/tickets` automaticamente (não precisa saber o
  papel no submit).
- `me.get.ts` já repassa o corpo do `/v1/me` — `role` chega de graça.

## 9. Seed / demo (dois papéis logináveis por tenant)

Para a apresentação, cada tenant precisa de **um admin e um help-desk** que
logam de verdade:

- **gerti** (`seed_demo_branding.py`, idempotente): semear `portal_user_role`:
  - Aurora: `eduardo.salvi@auroramoveis.com.br` → admin; `helpdesk@auroramoveis.com.br` → helpdesk.
  - TechNova: `admin.tech@technova.example` → admin; `suporte.ops@technova.example` → helpdesk.
- **Znuny** (scripts de seed Perl/GI existentes): criar idempotentemente o
  customer_user help-desk de cada tenant com senha de demo, espelhando o
  padrão dos admins atuais. Senhas de demo: `Aurora@Help2026` / `TechNova@Help2026`.

(Os e-mails/senhas exatos vão para o PDF de acessos.)

## 10. Erros & segurança

- Least-privilege em toda omissão (§2 D-1H-4, §5, §6).
- Papel é **intra-tenant**: `portal_user_role` é FORCE RLS; uma sessão nunca
  enxerga/usa mapeamento de papel de outro tenant. Cross-tenant 403 inalterado.
- 403 `forbidden_role` para help-desk nos endpoints admin; o portal trata como
  redirect (não quebra). Nenhuma senha logada; resolução de papel não loga PII
  além do necessário.

## 11. Testes

**Sidecar (pytest + testcontainers):**
- `resolve_role`: mapeado admin → admin; mapeado helpdesk → helpdesk;
  não-mapeado → helpdesk (default).
- login embute `role` no JWT (decode confirma); `decode_session` sem `role` → helpdesk.
- `require_admin`: admin 200 nos endpoints de contrato/dashboard; helpdesk **403**;
  sem sessão **401**; cross-tenant **403** (inalterado).
- `/v1/me` devolve `role` para ambos os papéis.
- **RLS** de `portal_user_role`: sessão sem GUC vê 0 linhas; tenant A não vê
  mapeamento de tenant B (cross-tenant hard-assert, padrão `test_rls_isolation`).
- e2e Aurora: admin vê contratos+dashboard; helpdesk → 403 nesses + 200 em `/me` role=helpdesk.

**Portal (vitest):**
- nav renderiza Contratos só para admin; Tickets para ambos (helpdesk sem Contratos).
- `tickets.vue` renderiza o placeholder.
- (guarda SSR coberta por teste de unidade do middleware se viável; senão,
  documentada e verificada no smoke pós-deploy).

## 12. Deploy

Mesmo runbook (`.ia/OPS.md`): `sidecar-migrate` aplica `0012`; rodar o seed
gerti (`seed_demo_branding.py`) + o seed Znuny dos help-desks; rebuild/redeploy
do portal. Verificação pós-deploy: admin Aurora vê contratos; help-desk Aurora
loga e cai em `/tickets`; cross-tenant 403 intacto; Znuny/landing 200.

## 13. Pós-entrega (fora do código)

Atualizar o PDF de acessos (`~/Documents/WAS-Portal-Cliente-Documentacao.pdf`)
com os dois logins por tenant (admin + help-desk) e uma nota explicando a
diferença de papéis. Atualizar `.ia/INTEGRATION.md` + ADR (D18: papéis no portal).

## 14. Não-objetivos (YAGNI)

- Sem UI de gestão de papéis (isso é #1G onboarding).
- Sem múltiplos papéis por usuário, sem papéis além de admin/helpdesk.
- Sem feature de tickets (placeholder apenas) — #1E.
- Sem mudança no mecanismo de auth do Znuny (D14 intacto).
