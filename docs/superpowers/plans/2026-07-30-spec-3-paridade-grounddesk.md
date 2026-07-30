# Spec #3 — Paridade de interface com o protótipo `grounddesk-itsm`

> **Para workers agênticos:** este documento é o **contrato**. Backend e frontend
> trabalham em paralelo contra ele. Se algo aqui divergir do código existente, o
> **código existente vence** — avise no relatório final em vez de improvisar.

**Referência:** `/Users/will/projetos/grounddesk-itsm` — protótipo React/Vite/Base44
de um ITSM ("GERTI"), 43 telas, ~10,5k LOC.

**Achado estruturante:** o protótipo é uma **maquete visual**. Das 43 páginas,
apenas `ZnunyIntegration.jsx` faz I/O real; todo o resto lê arrays de
`src/lib/mockData.js`. Não há CRUD, validação, paginação, confirmação de
destrutivo, loading nem tratamento de erro. Portanto **não existe "portar" —
existe projetar de verdade** o que a maquete só desenha.

---

## Escopo desta entrega (6 verticais)

| # | Vertical | Portal (cliente) | Console (staff) |
|---|---|---|---|
| V1 | **Base de Conhecimento** | lista, busca, categoria, detalhe | CRUD completo |
| V2 | **Catálogo de Serviços** | vitrine → abre chamado pré-preenchido | CRUD completo |
| V3 | **Notificações + Perfil** | central, badge, preferências | — |
| V4 | **Identidade visual editável** | (consome) | editor + preview ao vivo |
| V5 | **Trilha de auditoria** | — | consulta filtrada |
| V6 | **Saúde do sistema + busca global** | busca | saúde + busca |

### Fora de escopo — e por quê (registrar em DECISIONS)

Filas, políticas de SLA, tipos/estados de chamado, classes de CI, calendário de
feriados, jornadas de trabalho, agenda da equipe, gestão de agentes/usuários/
perfis de acesso: **são configuração nativa do Znuny**. Nossa invariante mãe é
"núcleo Znuny imutável, o Znuny é a fonte da verdade" — espelhar o painel dele no
nosso console criaria uma segunda fonte de verdade e um caminho de escrita fora do
GI. O MSP administra isso no painel do Znuny.

Inventário de estoque (`mockInventoryItems`) e gamificação/conquistas
(`mockAchievements`) são produtos novos, não paridade de interface — ficam para
uma fase 2. Relatórios e painel SLA já são cobertos parcialmente pelo #1O
(`/analytics`).

---

## Invariantes (valem para todos os agentes)

1. **Núcleo Znuny imutável.** Escrita no Znuny só via GI. O sidecar é a única
   porta; o browser nunca fala com o Znuny nem com o banco.
2. **Multi-tenant fail-closed.** Tabela de negócio = `tenant_id` + `FORCE ROW
   LEVEL SECURITY` + policy `tenant_id = current_setting('app.current_tenant')::uuid`;
   acesso por `tenant_session_scope`. Tabela operacional cross-tenant = sem RLS,
   lida por `AdminSessionLocal` (BYPASSRLS), **só** em `/v1/admin/*`.
3. **Anti-IDOR.** `GET /recurso/{id}` fora do tenant → **404**, nunca 403.
4. **Auth.** cliente → `get_current_session`; agente → `get_admin_session`.
   `gsid` e `gsid_adm` nunca se cruzam.
5. **Validação server-side é a verdade.** Pydantic com limites explícitos; 422 com
   mensagem útil. O cliente valida também, por UX, nunca por segurança.
6. **Design.** Tokens semânticos (`bg-default`, `text-muted`, `border-default`…),
   zero cor crua, tema claro/escuro/sistema funcionando, cor de marca só para
   identidade (H8). Textos em **português do Brasil**. Nunca `v-html`.
7. **Tudo em Docker.** Nenhuma instalação no host.

---

## Migrations reservadas (não negocie estes números)

| Revisão | `down_revision` | Tabelas | Dono |
|---|---|---|---|
| `0022_kb_catalog` | `0021_contratacao_asaas` | `kb_article`, `service_catalog_item` | agente B1 |
| `0023_notifications_prefs` | `0022_kb_catalog` | `notification`, `user_preference` | agente B2 |
| `0024_audit_log` | `0023_notifications_prefs` | `audit_log` | agente B3 |

---

## Contrato de API

Prefixo `/v1`. Todos os corpos são JSON. Erros seguem o padrão de `domain/errors.py`.

### V1 — Base de Conhecimento

**Tabela `gerti.kb_article`** (tenant-scoped, FORCE RLS)
`id uuid pk` · `tenant_id uuid not null` · `slug text not null` · `title text not null` ·
`summary text` · `body_markdown text not null` · `category text not null` ·
`tags text[] not null default '{}'` · `visibility text not null` (`public`|`internal`) ·
`status text not null` (`draft`|`published`|`archived`) · `views int not null default 0` ·
`author_login text` · `created_at`/`updated_at timestamptz not null`.
**Unique** `(tenant_id, slug)`.

Cliente (`get_current_session` + `get_tenant_session`) — enxerga **apenas**
`visibility='public' AND status='published'`:

| Método | Rota | Resposta |
|---|---|---|
| GET | `/kb/articles?q=&category=&limit=20&offset=0` | `{items:[{id,slug,title,summary,category,tags,views,updated_at}],total,limit,offset}` |
| GET | `/kb/articles/{slug}` | item + `body_markdown`; incrementa `views`; 404 se não público/publicado |
| GET | `/kb/categories` | `[{category,count}]` |

Console (`get_admin_session`) — cross-tenant por `tenant_id` no path:

| Método | Rota |
|---|---|
| GET | `/admin/tenants/{tid}/kb/articles?q=&category=&status=&limit=&offset=` |
| POST | `/admin/tenants/{tid}/kb/articles` → **201** |
| GET | `/admin/tenants/{tid}/kb/articles/{id}` |
| PUT | `/admin/tenants/{tid}/kb/articles/{id}` |
| DELETE | `/admin/tenants/{tid}/kb/articles/{id}` → **204** |

Corpo de escrita: `{title, summary?, body_markdown, category, tags[], visibility, status}`.
**Validações:** `title` 3–200 · `summary` ≤500 · `body_markdown` 1–50000 ·
`category` 2–60 · `tags` ≤10 itens, cada ≤30 chars, normalizados para minúsculas
sem duplicatas · `visibility` e `status` só os enums acima.
**Slug:** derivado do título (minúsculas, sem acento, `[a-z0-9-]`), único por
tenant — em colisão sufixa `-2`, `-3`… Não muda quando o título é editado
(preserva links).

`views` incrementa em `UPDATE … SET views = views + 1` (sem race), e **nunca**
conta acesso do console.

### V2 — Catálogo de Serviços

**Tabela `gerti.service_catalog_item`** (tenant-scoped, FORCE RLS)
`id uuid pk` · `tenant_id uuid not null` · `name text not null` · `category text not null` ·
`description text` · `sla_hours int` · `icon text not null default 'ticket'` ·
`znuny_queue text` · `znuny_service text` · `default_priority text` ·
`active bool not null default true` · `sort_order int not null default 0` ·
`created_at`/`updated_at`.

Cliente — **apenas `active=true`**:

| Método | Rota | Resposta |
|---|---|---|
| GET | `/catalog/items?category=` | `[{id,name,category,description,sla_hours,icon}]` ordenado por `sort_order,name` |
| GET | `/catalog/items/{id}` | item completo (inclui `znuny_queue`, `znuny_service`, `default_priority`); **404** cross-tenant ou inativo |
| GET | `/catalog/categories` | `[{category,count}]` |

Console: CRUD em `/admin/tenants/{tid}/catalog/items` (mesma forma do KB:
GET lista, POST 201, GET item, PUT, DELETE 204).

**Validações:** `name` 3–120 · `category` 2–60 · `description` ≤1000 ·
`sla_hours` int 1–720 (opcional) · `icon` da allowlist
`['ticket','shield','user-plus','server','package','database','box','printer','lock','wifi','mail','settings']`
(fora da lista → 422) · `znuny_queue`/`znuny_service`/`default_priority` ≤200 ·
`sort_order` 0–999.

**Integração com abertura de chamado:** o portal leva o cliente de
`/catalogo` para `/tickets/novo?servico=<id>`; a página de novo chamado busca o
item e pré-preenche assunto, fila, serviço e prioridade (todos editáveis). Se o
id não existir/estiver inativo, a página abre normalmente **sem** pré-preenchimento
e sem erro ruidoso.

### V3 — Notificações e preferências

**Tabela `gerti.notification`** (tenant-scoped, FORCE RLS)
`id uuid pk` · `tenant_id uuid not null` · `recipient_login text not null` ·
`kind text not null` (`ticket_update`|`ticket_reply`|`sla_warning`|`sla_breach`|`contract_alert`|`invoice_issued`|`system`) ·
`title text not null` · `body text` · `link_path text` · `read_at timestamptz` ·
`created_at timestamptz not null`. Índice `(tenant_id, recipient_login, created_at desc)`.

**Tabela `gerti.user_preference`** (tenant-scoped, FORCE RLS)
`id uuid pk` · `tenant_id uuid not null` · `user_login text not null` ·
`theme text not null default 'system'` (`light`|`dark`|`system`) ·
`email_notifications bool default true` · `sla_alerts bool default true` ·
`ticket_updates bool default true` · `contract_alerts bool default true` ·
`invoice_alerts bool default true` · `weekly_report bool default false` ·
`created_at`/`updated_at`. **Unique** `(tenant_id, user_login)`.

| Método | Rota | Nota |
|---|---|---|
| GET | `/notifications?status=all\|unread\|read&limit=20&offset=0` | `{items,total,unread,limit,offset}` — **só do `recipient_login` da sessão** |
| POST | `/notifications/{id}/read` | 204; **404** se não for do usuário/tenant |
| POST | `/notifications/read-all` | `{updated:n}` |
| GET | `/me/preferences` | cria com defaults na primeira leitura (upsert idempotente) |
| PUT | `/me/preferences` | corpo parcial permitido; 422 fora do enum |

**Produção de notificações** (`NotificationService.emit`, idempotente por
`(tenant_id, recipient_login, kind, link_path, dia)` para não spammar):
- fatura emitida (`invoice_service`) → `invoice_issued` para os admins do tenant;
- resposta de agente em chamado (hook de `ArticleCreate` com `SenderType=agent`)
  → `ticket_reply` para o solicitante;
- saldo crítico no fechamento de ciclo → `contract_alert` para os admins.

O primeiro é obrigatório; os outros dois, se o tempo permitir — declare no relatório
o que ficou de fora.

### V4 — Identidade visual editável

| Método | Rota | Auth |
|---|---|---|
| GET | `/admin/tenants/{tid}/branding` | agente |
| PUT | `/admin/tenants/{tid}/branding` | agente |

Corpo: `{display_name, primary_color, accent_color, logo_url?, default_theme}`.
**Validações:** `display_name` 2–80 · cores no regex `^#[0-9A-Fa-f]{6}$` (422 com
mensagem explícita) · `logo_url` opcional, **precisa ser `https://`**, ≤500 chars ·
`default_theme` ∈ `light|dark|system`.
Reusa a tabela `tenant_branding` existente — **não crie tabela nova**. A leitura
pública por host (`GET /v1/branding`) continua intacta.

### V5 — Trilha de auditoria

**Tabela `gerti.audit_log`** (operacional, cross-tenant, **sem RLS**, lida com
BYPASSRLS)
`id uuid pk` · `at timestamptz not null default now()` · `actor_type text not null`
(`agent`|`customer`|`system`) · `actor_login text` · `tenant_id uuid` (nullable) ·
`action text not null` (`create`|`update`|`delete`|`login`|`export`) ·
`entity text not null` · `entity_id text` · `description text not null` ·
`ip text` · `user_agent text` · `metadata jsonb not null default '{}'`.
Índices em `(at desc)` e `(tenant_id, at desc)`.

`audit_service.record(...)` é chamado nos endpoints admin de escrita já
existentes **e** nos novos: onboarding de cliente, criação de contrato, fatura
(gerar/pagar/cancelar), branding, KB, catálogo, tokens de agente, regras de
automação. **Nunca** grave segredo, senha, token ou corpo de ticket no
`description`/`metadata`.

| Método | Rota |
|---|---|
| GET | `/admin/audit-logs?q=&action=&tenant_id=&from=&to=&limit=50&offset=0` |

`limit` máximo **200** (acima disso → 422). `q` casa em `actor_login`, `entity`,
`entity_id` e `description`.

### V6 — Saúde do sistema e busca global

`GET /admin/system/health` (agente) →
```json
{
  "db": {"ok": true, "latency_ms": 3},
  "znuny_gi": {"ok": true, "latency_ms": 120, "message": "pong"},
  "worker": {"ok": true, "last_sync_at": "…", "lag_seconds": 42},
  "ai": {"enabled": true, "ok": true},
  "asaas": {"enabled": false},
  "version": "0.1.0"
}
```
Cada sonda tem timeout curto (≤3 s) e **falha isolada**: uma sonda vermelha não
derruba a resposta — o campo vira `{"ok": false, "message": "..."}` e o HTTP
continua 200. Nunca exponha URL com credencial, token ou senha.

`GET /search?q=` (cliente) → `{tickets:[…≤5], assets:[…≤5], kb:[…≤5], catalog:[…≤5]}`
`GET /admin/search?q=` (agente) → `{tenants:[…≤5], tickets:[…≤5], kb:[…≤5]}`
`q` obrigatório, 2–100 chars (422 fora disso). Cada item traz `{id,title,subtitle,path}`
— **`path` é a rota final pronta** (o protótipo tinha um bug de concatenação que
gerava `/knowledge-basekb-001`; não repita).

---

## Superfície de front-end

### Portal (`apps/portal`)

| Rota | Tela |
|---|---|
| `/base-conhecimento` | grid de artigos, busca, pills de categoria, estado vazio |
| `/base-conhecimento/[slug]` | artigo renderizado (markdown → HTML **sanitizado**, jamais `v-html` cru), tags, views, voltar |
| `/catalogo` | vitrine por categoria, SLA no card, "Solicitar" → `/tickets/novo?servico=<id>` |
| `/notificacoes` | lista com filtros Todas/Não lidas/Lidas, marcar uma, marcar todas |
| `/perfil` | dados da sessão (read-only) + preferências (salvar de verdade) |
| `/busca` | busca federada nas 4 fontes |

Mais: badge de não lidas no cabeçalho autenticado e os itens novos no menu.

### Console (`apps/admin`)

| Rota | Tela |
|---|---|
| `/clientes/[id]/conhecimento` | lista + criar/editar/excluir artigo (confirmação no excluir) |
| `/clientes/[id]/catalogo` | lista + criar/editar/excluir item, toggle ativo, ordenação |
| `/clientes/[id]/identidade` | editor de marca com **preview ao vivo** |
| `/auditoria` | tabela com busca, filtro de ação, filtro de cliente, paginação |
| `/sistema` | cartões de saúde (banco, Znuny, worker, IA, Asaas) + versão |
| `/busca` | busca federada do staff |

Lembre-se: rota filha de `clientes/[id]` exige `<NuxtPage />` no pai.

---

## Definição de pronto

Uma vertical só está pronta quando tem: migration com RLS provada · service com
teste unitário · router com teste de happy path, 401, **404 cross-tenant** e 422 ·
página com loading, vazio e erro · teste do proxy Nuxt · texto em pt-BR · gate
verde. Sem isso, não está pronta — e o relatório deve dizer.
