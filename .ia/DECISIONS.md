# Ground Control — Decisões (ADRs)

Resumo das decisões não óbvias. ADR técnico canônico (gerado no build, inglês):
[`../docs/decisions/0001-stack.md`](../docs/decisions/0001-stack.md).

## D1 — Znuny do tarball oficial, não imagem comunitária
Zero tolerância a falha. Imagens comunitárias de Znuny são desatualizadas/opacas.
Build próprio do tarball oficial 7.2.3 = versão pinada, reprodutível, auditável.

## D2 — Base `debian:bookworm-slim`, NÃO `perl:5.40`
`libapache2-mod-perl2` linka contra o perl **do sistema** (5.36). Em base `perl:5.40`
há dois perls: mod_perl usa o do sistema; CLI/`cpanm`/`otrs.CheckModules.pl` usam o 5.40.
Verificado quebrando o build (`CheckModules.pl` reportava módulos apt-instalados como
ausentes — `@INC` mismatch). Um perl só elimina a classe inteira de bug.

## D3 — PostgreSQL 18: COMPATÍVEL, sem fallback
**Veredito: Znuny 7.2.3 instala e roda limpo no `postgres:18` (verificado 18.4).**
Schema load, `DBD::Pg`, console, daemon e web — tudo funciona. Sem fallback p/ PG17.
Único ajuste (de *imagem*, não incompatibilidade do Znuny): `postgres:18` espera o
volume em `/var/lib/postgresql` (subdir de major-version), não `/var/lib/postgresql/data`.

## D4 — Backend de cache Redis custom
Core Znuny 7.2 só tem `Cache::FileStorable` (Redis é add-on pago/feature). Decisão:
shipar `Kernel::System::Cache::Redis` fiel ao contrato (`Set/Get/Delete/CleanUp`),
em `Custom/` (upgrade-safe), `Storable` + `SETEX` + índice SET por `Type`.
Verificado: 150+ chaves `znuny:*` no Redis, FS bypassed.

## D5 — OpenSearch: alcance provado, indexação é add-on-gated
Core Znuny 7.2 **não** tem suporte ES/OpenSearch (é o add-on `Znuny-Elasticsearch`,
fora do repo público de releases). Decisão (mínimo acordado): OpenSearch healthy,
endpoint em `Config.pm` (`GertiOpenSearchEndpoint`), e **alcance Znuny→OpenSearch
provado** (`status: green`). **Gap conhecido:** indexação completa de documentos
exige o add-on (trabalho futuro).

## D6 — Provisionamento automatizado e idempotente
Sem instalador web, nunca. `entrypoint.sh` renderiza Config.pm de env, init de DB
só se schema ausente, admin/SystemID via Console.pl. `down && up` repetido não
duplica nem reinicializa destrutivamente.

## D7 — Redes segregadas
`edge` (cloudflared↔web), `app` (znuny↔serviços), `data` (`internal: true` —
postgres/redis/opensearch não roteáveis de fora).

## D8 — cloudflared token-mode via `.env.prod`
Token não commitado. Placeholder → cloudflared loga "token is not valid" e reinicia;
esperado e inócuo (nada depende dele). Token real ativa o tunnel.

## D10 — `make` interpola de `.env` **e** `.env.prod`
**Bug encontrado no deploy real:** `DC := docker compose` usava só o `.env`
default; o token em `.env.prod` (via `env_file:` do override) injeta no
*ambiente do container* mas **não** alimenta a interpolação compose-time de
`${CLOUDFLARE_TUNNEL_TOKEN}` no `command: --token`. Resultado: `make up`
limpo nunca conectava o tunnel (ficava `MISSING_TOKEN`); forçar
`--env-file .env.prod` conectava o tunnel mas zerava todas as outras vars
(quebrava postgres/znuny-web). **Fix:** `DC := docker compose --env-file
.env --env-file .env.prod` (compose mescla, último vence). `init` agora
depende de file-targets `.env`/`.env.prod` silenciosos e é prereq de todos
os alvos, garantindo que ambos existam. Token mora em `.env.prod` (design
documentado preservado).

## D9 — Monorepo de deploy + landing consolidada
Repo `ground-control` é o monorepo de deploy. Landing comercial consolidada em
`landing/` (era repo standalone `ground-control-landing`). Sidecar/portal entram
quando estabilizarem. Documentação no padrão **voyager** (`.ia/` + README conceito
mission-control).

## D11 — Sidecar e código do projeto consolidados no monorepo ground-control (gerti = só apresentação)
O sidecar Python, `infra/`, specs/planos/ADRs do projeto e o CI
(`sidecar-ci.yml`) viviam no repo `gerti`. `gerti` agora contém **apenas a
apresentação** (`apresentacao/`); todo o código/infra/docs migrou para
`ground-control/apps/sidecar`, `infra/`, `docs/superpowers/`, `docs/adr/`,
`.github/workflows/`. **Racional:** monorepo único de deploy evita
*split-brain* (código x stack em repos separados), um só ciclo de deploy,
docs de integração ao lado da stack que integram. Gate verificado
(`ruff + mypy + pytest` 16/16, RLS/tenant-session sob role sem privilégio)
**revalidado verde na nova localização** — `conftest` resolve o init SQL
via `infra/` copiado sem editar código.

**Decisão de integração — schema `gerti` compartilhado:** Spec #0 mantém
**um cluster Postgres, dois schemas** (`znuny` imutável + `gerti` do
sidecar). Convergir produção para esse cluster único (Znuny hoje usa
`postgres:18` próprio; sidecar testa via testcontainers) é **item aberto
documentado** em `INTEGRATION.md`, não regressão.

## D12 — `gerti.znuny_instance` sob RLS escopada por tenant (gap S1)
**Defeito real pego pelo gate, não mascarado.** `gerti.znuny_instance`
(criada em `0001`, DML concedido a `gerti_app` em `0002`) **nunca**
recebeu RLS ENABLE+FORCE em 0001–0008 → sessão `gerti_sidecar`
(sem BYPASSRLS) lia/escrevia instâncias de **todos os tenants** sem
escopo. O hard-assert S1 (`test_every_gerti_table_has_rls_enabled_and_forced`),
desenhado para ativar exatamente no head 0008, expôs a falha
(implementer **escalou em vez de enfraquecer o teste** — disciplina
zero-tolerância). `znuny_instance` não tem `tenant_id`; o tenant
alcança sua instância via `gerti.tenant.znuny_instance_id`.
**Fix:** migration `0009_rls_znuny_instance` — ENABLE+FORCE +
policy `znuny_instance_tenant_isolation` (USING **e** WITH CHECK):
`id IN (SELECT znuny_instance_id FROM gerti.tenant WHERE id =
NULLIF(current_setting('app.current_tenant', true), '')::uuid)`.
Fail-closed (GUC vazia/'' → NULLIF→NULL → subquery vazia → 0 linhas);
onboarding admin roda como `gerti_admin` (BYPASSRLS) e não é afetado;
a subquery funciona porque a RLS do próprio `gerti.tenant` deixa a
sessão ver só seu tenant. Matview renumerada `0009`→`0010`
(`down_revision=0009_rls_znuny_instance`). Teste de regressão
permanente (`test_znuny_instance_rls_scoped_by_tenant`): tenant A vê
só a instância de A, GUC vazia → 0 linhas, sob role `gerti_sidecar`.
Gate verde **26 passed, 0 skip**.

## D13 — Deploy do sidecar: cluster Postgres ÚNICO, profile-gated, sem downtime
Spec #0 manda **um cluster, dois schemas**. O cluster prod do Znuny já
existe e é saudável; `./postgres/init` está vazio (só `.gitkeep`) e
`docker-entrypoint-initdb.d` só roda no 1º init do cluster — não há
caminho de init-script p/ introduzir `gerti` no cluster vivo. Subir um
2º Postgres violaria Spec #0 e dobraria a superfície de ops/backup.
**Decisão:** manter o `postgres:18` único; introduzir schema `gerti` +
roles + RLS no cluster *em execução* via job one-shot idempotente
`gerti-db-init` (psql como superusuário, SQL auditado linha-a-linha,
zero DROP, zero escrita em `public`/`znuny`), depois Alembic como
`gerti_admin_user` (BYPASSRLS, dono do DDL) e o app como
`gerti_sidecar` (RLS-subject). **Todos os 3 serviços
(`gerti-db-init`/`sidecar-migrate`/`sidecar`) sob `profiles:["gerti"]`**
→ um `make up` da stack Znuny nunca os toca (aditivo, Postgres não
reinicia, nada Znuny reconstruído). Exposição: `api-dev.was.dev.br`
como 2º hostname no MESMO tunnel `znuny-dev` (token-mode multi-host),
ingress via **read-modify-write** (GET→splice antes do 404→guard→PUT;
PUT hand-written derrubaria `znuny-dev`+demo).

**Footgun corrigido (não propagado do plano):** o snippet do plano usava
`${GERTI_*_DB_PASSWORD:?…}` no `command` do `gerti-db-init`. O Compose
interpola o arquivo **inteiro antes de filtrar profiles** → `:?` fazia
`docker compose config`/`up` da stack **só-Znuny** abortar (quebrava o
zero-downtime). **Fix verificado local:** segredos com default vazio no
`environment:` (`${VAR:-}`), exigência movida p/ **runtime** no shell do
container (`: "$${VAR:?…}"` — `$$` = `$` literal p/ o Compose, bash lê
do env real). Confirmado: `docker compose config --services` SEM profile
lista só os 6 serviços Znuny; com `--profile gerti` parseia OK.

**Status (2026-05-17):** artefatos prontos e em `origin/main`. Execução
na VPS `100.99.49.110` ficou **pendente — SSH inacessível** (porta 22
timeout, ICMP 100% loss; node aparece no tailnet mas sshd/porta não
respondem) durante a janela de deploy autônomo: bloqueio externo do
lado da VPS, não fabricado. Runbook completo em `OPS.md` "Deploy do
sidecar"; segredos fortes gerados e entregues out-of-band. Retomar =
`git pull` + passos 1–5 + D3 (zero mudança de código pendente).

## D14 — Validação de credencial de customer Znuny (R1, fatia #1F-a)

**Contexto.** O sidecar precisa validar uma credencial de *customer*
Znuny no login do Portal Cliente SEM depender de GertiHooks/#1B (ainda
inexistente). SPIKE R1 investigou o Znuny prod vivo via `ssh gc`
(jump alias via node `postgres`; Tailscale direto quebrado — ver
`.ia/OPS.md`). Inventário (`Admin::WebService::List`) retornou
**lista vazia** (`Listing all web services... Done.`) — nenhum
webservice cadastrado, nada a dumpar. `ls
.../GenericInterface/Operation/Session/` retornou `Common.pm
SessionCreate.pm SessionGet.pm SessionRemove.pm` → operação core
`Session::SessionCreate` PRESENTE (código Znuny 7.2, não #1B). A fonte
de `SessionCreate.pm` documenta os campos `UserLogin` **ou**
`CustomerUserLogin` + `Password`; `Session::Common::CreateSessionID`
roteia `CustomerUserLogin` para `Kernel::System::CustomerAuth->Auth`
(auth de CUSTOMER, respeita `Customer::AuthModule`), retorna undef em
credencial inválida → `SessionCreate.pm` devolve `SessionCreate.AuthFail`.

**Decisão: PRIMARY.** Mecanismo = webservice Generic Interface REST
(provider) expondo a operação core `Session::SessionCreate`, transporte
`HTTP::REST`, rota **`POST /Session`** mapeada para a operação
`SessionCreate` (`Type: Session::SessionCreate`). O sidecar faz
`POST {base_url}/nph-genericinterface.pl/Webservice/<Name>/Session`
com body JSON usando o campo de login de customer **exato
`CustomerUserLogin`** + `Password` (texto plano). Resposta com
`Data.SessionID` ⇒ credencial válida; `SessionCreate.AuthFail`/`Error`/
HTTP 4xx ⇒ inválida; falha de transporte ⇒ indisponível. O webservice
**ainda não existe** no Znuny prod (lista vazia) — criá-lo/importá-lo é
etapa de deploy (Task 5/6); a definição YAML exata está no arquivo de
evidência. FALLBACK (query read-only `customer_user` + `CryptType`)
**não foi necessário nem exercido**.

**Contrato CONGELADO (verbatim, para Task 5):**

```python
class ZnunyUnavailable(RuntimeError):
    ...

async def authenticate_customer(login: str, password: str) -> bool:
    ...
```

Semântica:
- credencial válida (HTTP 2xx, body com `SessionID`) → `return True`
- credencial inválida (`Error`/`SessionCreate.AuthFail`/HTTP 4xx) →
  `return False`
- erro de conexão / timeout / HTTP 5xx → `raise ZnunyUnavailable`

**Endpoint/token.** Da linha ÚNICA de `gerti.znuny_instance`
(`id=b437f4d5-8266-4270-9253-ef536c8ff59c`, `name="Gerti Prod
(znuny-dev)"`, `mode=pool`, `status=active`):
- `base_url` = `https://znuny-dev.was.dev.br`
- token de acesso ao webservice via `webservice_token_secret_ref` =
  `vault://gerti/znuny-dev/webservice`
- `db_dsn_secret_ref` = `vault://gerti/znuny-dev/db` (só seria usado no
  FALLBACK — NÃO é o caso).

**Evidência.** `docs/superpowers/spikes/2026-05-17-r1-znuny-customer-auth.md`
(transcrições reais: `Admin::WebService::List`, `ls Session/`, fonte de
`SessionCreate.pm`/`Common.pm`, `\d gerti.znuny_instance` + a linha).

## D16 — TenantMiddleware resolve subdomínio->tenant por um caminho BYPASSRLS estreito (somente identidade); todo dado de tenant permanece RLS-subject

**Contexto.** `gerti.tenant` é FORCE RLS (D-0003); em prod o sidecar
conecta como `gerti_sidecar` (RLS-subject, BYPASSRLS não herdado via
role membership — #1C); o `TenantMiddleware` resolve o subdomínio ANTES
de qualquer GUC, então um session RLS-subject retorna 0 linhas e 404
para todo tenant válido.

**Decisão.** Introduzir `Settings.database_admin_url` (opcional),
`db.admin_engine`/`db.AdminSessionLocal` (criados em `init_db` quando o
DSN existe, descartados em `dispose_db`); `TenantMiddleware` usa
`AdminSessionLocal or SessionLocal` SÓ para o
`select(Tenant).where(subdomain==...)` (lookup de diretório, só
identidade); todo DADO de tenant continua RLS-subject via
`tenant_session_scope`. Prod: compose injeta `DATABASE_ADMIN_URL` do
`gerti_admin_user`+`${GERTI_ADMIN_DB_PASSWORD:-}` (nunca `${VAR:?}` —
footgun D13). Dev/test sem DSN admin: `AdminSessionLocal=None` => cai no
`SessionLocal` (que os testes ligam ao admin engine, como
`test_tenant_middleware.py`).

**Evidência.** `test_tenant_resolution_admin_path.py` (subdomínio válido
resolve 200-class via path BYPASSRLS; RLS ainda fail-closed no dado).

## D15 — Deploy do Portal: serviço aditivo profile-gated, sidecar como única porta

**Contexto.** O portal Nuxt 3 SSR (`apps/portal/`) precisa ser exposto
publicamente em dois subdomínios white-label (`aurora.suporte.gerti.com.br`,
`technova.suporte.gerti.com.br`) sem tocar na stack Znuny em execução
nem introduzir um Znuny separado por tenant.

**Decisão.**

- `portal` é um serviço `profiles:["gerti"]` no `docker-compose.yml`
  raiz. Um `make up` da stack Znuny pura não o toca — aditivo,
  zero-downtime para o Znuny (padrão D13).
- Redes: `app` (para alcançar `sidecar:8001`) + `edge` (para ser
  roteado pelo cloudflared). O portal fala **somente** com o
  `sidecar:8001`; nunca com `znuny-web` diretamente.
- Imagem multi-stage: dependências de build (Node.js, devDeps) ficam
  apenas no estágio de build; o estágio de runtime é minimalista
  (`internal: true` no sentido de superfície reduzida).
- Ingresso Cloudflare por **read-modify-write** (mesmo padrão D3 do
  sidecar): GET → splice idempotente de AMBAS as regras
  `aurora.suporte`/`technova.suporte` antes do catch-all `http_status:404`
  → guard afirma `znuny-dev`+`api-dev` intactos E ambos os novos
  hostnames presentes → PUT do objeto completo. **Nunca** PUT
  hand-written (sobrescreve o array inteiro e derruba `znuny-dev`).
- Segredos no compose com default vazio, nunca `${VAR:?}` — footgun D13:
  - `SESSION_SECRET`: `${GERTI_SESSION_SECRET:-}` (em `.env.prod`,
    gitignored).
  - `DATABASE_ADMIN_URL`: construída de `gerti_admin_user` +
    `${GERTI_ADMIN_DB_PASSWORD:-}` (mesmo segredo já usado pelo
    `sidecar-migrate` — nenhum segredo novo).
- **Rollback:** `$DC stop portal`. Znuny e sidecar intocados.
  **NUNCA** `make reset`.

**Resultado.** Portal implementado e gateado; deploy per runbook
`OPS.md` "Deploy do portal". ADR final em `.ia/DECISIONS.md` (ordem:
D14 spike auth, D16 TenantMiddleware BYPASSRLS, D15 deploy portal).

## D17 — Read-service do portal (#1F-b): regra S3 da glosa centralizada, leitura pura

**Contexto.** A fatia #1F-b (visão de contratos rica) precisa de
`consumed_percent`, `counts_toward_balance` por evento, série densa de
consumo e alertas de saldo baixo. A regra S3 — apenas glosa `approved`
remove o evento do saldo, com o braço explícito `glosa_id IS NULL` que
evita o footgun `NULL NOT IN (..)` = NULL — já vive em
`ConsumptionService.balance` (`domain/consumption_service.py`).
Reimplementá-la dentro dos routers `/v1/contracts/*` e `/v1/dashboard`
duplicaria o footgun e arriscaria drift (ex.: dropar o braço `IS NULL`
descartaria silenciosamente eventos sem glosa).

**Decisão.** Introduzir `domain/contract_read_service.py`, **READ-ONLY**
(somente `select(...)`/`session.get(...)`/`ConsumptionService.balance`;
zero `add`/`flush`/`commit`/`INSERT`/`UPDATE`/`DELETE`), expondo:
- `not_written_off_predicate()` — idêntico ao braço do `balance()`;
- `consumed_percent_from` / `consumed_percent` — `clamp01((initial -
  remaining)/initial)*100`, `None` para `kind=="n/a"` e base 0/ausente;
- `series` — série densa zero-filled na janela do contrato, cap de 400
  buckets diários → semanal (H5);
- `low_balance` — limiar 20% `warning` / `≤0` `critical`, só tipos com
  saldo (`hour_bank`/`credit_brl`/`credit_shared`/`service_count`);
  `closed_value`/`saas_product` nunca alertam.
Os routers consomem este service; NENHUM router redefine a regra S3.
O portal é read-only sobre o domínio #1C.

**Nota de modelagem (H8/#1C, reforçada em H15).** `balance()` exclui um
evento da soma keando no **back-pointer** `consumption_event.glosa_id`
(app-layer, SEM FK), não em `Glosa.consumption_event_id`. Testes/seeds
que exercitam exclusão de glosa `approved` DEVEM setar
`event.glosa_id = glosa.id` após criar a glosa (criar só
`Glosa(consumption_event_id=...)` deixa `glosa_id` NULL → nada é
excluído). Glosas `pending`/`rejected` continuam contando (sem
back-pointer).

**Evidência.** `tests/test_contract_read_service.py`: o predicate casa
com `balance()` (glosa `approved` exclui via back-pointer → remaining
8.0 / consumed 20%; `pending`/ausente contam); `consumed_percent` é
`None` para `closed_value` e para base 0. Gate sidecar **48 passed**;
S1 e `test_request_with_unknown_subdomain_returns_404` verdes.

## D18 — Papéis no Portal (#1H): admin × help-desk, verdade no schema `gerti`, gating server-side

**Contexto.** Os clientes (ex.: Aurora) têm dois tipos de usuário no Portal
do Cliente: **admin** (acompanha contratos e valores financeiros) e
**help-desk / operação** (acompanha tickets — feature #1E, ainda deferida).
Até #1F-b todo usuário autenticado via tudo do seu tenant. O JWT de sessão
(`gsid`) só carregava `tenant_id` + `customer_login` — sem papel.

**Decisão.** A verdade do papel mora no **schema `gerti`** (não nos grupos
do Znuny — Abordagem A do brainstorming): tabela `gerti.portal_user_role`
(`tenant_id`, `customer_login` normalizado lower, `role ∈ {admin,helpdesk}`),
**FORCE RLS por tenant** (template canônico, igual `tenant_branding`), única
por `(tenant_id, lower(customer_login))`. O papel é resolvido no login
(`domain/portal_role_service.resolve_role`, sob sessão tenant-scoped → RLS) e
**embutido como claim assinado HS256 no JWT** (`SessionPayload.role`). O
enforcement é **server-side**: a dependency `require_admin` (compõe sobre
`get_current_session`) protege a nível de router `/v1/contracts*` e
`/v1/dashboard` (403 `forbidden_role` para help-desk). `/v1/me` devolve
`role` e fica aberto (sem dados financeiros) para o portal decidir a navegação.

**Least-privilege em toda omissão.** Token sem claim `role` (emitido antes do
#1H, TTL em trânsito), usuário não-mapeado, e erro de DB na resolução **todos
caem em `helpdesk`**. `decode_session` valida o `role` contra um allowlist
(`admin`/`helpdesk`); valor desconhecido → `helpdesk`. Nenhum caminho concede
admin por omissão.

**Identidade.** O papel é keado pelo `customer_login` do JWT, que é o
**e-mail** digitado no login (login é sempre por e-mail, ver
[decision-login-by-email] / D14). Match case-insensitive; o seed grava
lowercased. Sem dependência do `login` interno do Znuny resolvido em
`znuny_gi`.

**Hardening.** Como o papel agora viaja como claim assinado, um
`SESSION_SECRET` default/conhecido permitiria forjar `role=admin`. O `Settings`
passou a **falhar o boot em production/staging** se o secret for o default.

**Portal.** Middleware **nomeada** `auth` (aplicada via `definePageMeta` em
`/`, `/contratos/[id]`, `/tickets`) — não global, para não rodar no `/login`
nem em mounts isolados de layout. Help-desk em rota admin-only → `/tickets`
(placeholder branded "em breve", home do help-desk). A middleware é
conveniência de UX; **o gate real é o 403 do sidecar** — um cliente que pule a
SPA e chame `/v1/contracts` direto ainda toma 403.

**Demo.** `seed_demo_branding.py` semeia `portal_user_role` (admin + help-desk
por tenant); `scripts/seed-helpdesk.pl` cria os `customer_user` help-desk no
Znuny (`helpdesk@auroramoveis.com.br` / `suporte.ops@technova.example`, senhas
`Aurora@Help2026` / `TechNova@Help2026`).

**Evidência.** Gate sidecar **69 passed** (`resolve_role` default/RLS,
`require_admin` 200/403/401, `/me` com role, login→role, secret-em-prod);
portal **34 vitest** (guarda + nav por papel). Reviews independentes de código
e de **autorização** APROVADAS (sem blockers): privilege-escalation fechado,
least-privilege em toda omissão, claim assinado validado por allowlist,
`portal_user_role` FORCE-RLS resolvido após o 403 cross-tenant, query
parametrizada, enforcement server-side.

## D19 (RASCUNHO — spike R1G, #1G-a) — Console de Administração: auth de agente via GI + escrita de cliente via operação GI custom

**Status:** RASCUNHO (congela contratos para a Fase 1; finalizado na Fase 2 com
evidência de gate + e2e). **Spike:** `docs/superpowers/spikes/2026-06-02-r1g-znuny-admin-gi.md`
(transcrições reais via `ssh gc` contra o Znuny 7.2.3 vivo).

**Contexto.** O #1G-a adiciona um app admin separado (equipe Gerti) com login
de **agente** Znuny, onboarding de cliente (tenant+branding+usuários+papéis) e
criar contrato. Duas incógnitas de Znuny GI eram bloqueantes (como o R1/#1F foi
para o portal): (1) auth de agente via GI; (2) escrita de `CustomerCompany`/
`CustomerUser` via GI (Spec #0: escrita no Znuny SEMPRE via GI).

**Decisão incógnita 1 — PRIMARY (live-proven).** A operação core
`Session::SessionCreate` aceita `UserLogin`+`Password` e roteia para
`Kernel::System::Auth->Auth` (auth de AGENTE) — fonte `Session/Common.pm:55-65`.
Prova viva: `Auth(User=>"william", Pw=>"Gerti@Demo2026")` → `william`;
senha errada → undef (`SessionCreate.AuthFail`). Mesmo webservice/contrato do
D14, **trocando só o campo de login** (`UserLogin` em vez de
`CustomerUserLogin`). SEM resolução e-mail→login (agentes logam pelo `login` da
tabela `users`, não pelo e-mail). Contrato congelado:
`authenticate_agent(login, password) -> bool` + `ZnunyUnavailable` (mesma
semântica failure-safe do `authenticate_customer`).

**Decisão incógnita 2 — operação GI CUSTOM.** O GI core **não** expõe escrita de
cliente: `ls .../Operation/` = `Common.pm Session Test Ticket User`, e `User/`
(que é agente) só tem `OutOfOffice.pm`. A API Perl, porém, expõe
`CustomerCompanyAdd` (`Kernel/System/CustomerCompany.pm`), `CustomerUserAdd` e
`SetPassword` (`Kernel/System/CustomerUser.pm`); e o overlay `Custom/Kernel/...`
já é usado nesta imagem (`Cache/Redis.pm`). Mecanismo congelado: **operação GI
custom** embrulhando a API Perl, exposta por um webservice `GertiAdmin`
(`CustomerCompany::CustomerCompanyAdd`, `CustomerUser::CustomerUserAdd`,
`CustomerUser::SetPassword`), shipada via `znuny/Custom/...` no build da imagem.
Contrato congelado (`integrations/znuny_customer_admin.py`):
`create_customer_company`, `create_customer_user`, `set_password` +
`ZnunyUnavailable` (transporte/5xx → 503) e `ZnunyWriteError` (rejeição limpa,
ex.: login duplicado → 4xx).

**Impacto no desenho (a decidir no checkpoint do spike).** A incógnita 2 adiciona
um artefato **Znuny-side** (Perl custom + import do webservice `GertiAdmin`) que
não estava listado no plano — é pré-requisito do e2e (#1G-a só cria o login se a
operação existir). Opção A: incluir no ciclo (deploy Fase 2). Opção B: entregar
UI/API + tenant/branding/papéis no Postgres e deixar a criação do CustomerUser
no Znuny para follow-up. (Ver spike, seção final.)

**Sessão admin.** JWT HS256 `{agent_login, role:"gerti_staff", exp}`, cookie
**próprio** `gsid_adm` (≠ `gsid` do cliente), **não tenant-scoped** (admin opera
cross-tenant). Endpoints `/v1/admin/*` exigem `get_admin_session` (401 sem ela);
os endpoints de cliente (`require_admin`, D18) NÃO aceitam a sessão admin
(cookies/segredos de claim distintos). Escrita cross-tenant só pelo caminho
admin BYPASSRLS (AdminSessionLocal, D16) e SÓ em `/v1/admin/*`; criar contrato
para um tenant abre `tenant_session_scope(id)` e usa `ContractService` (preserva
invariantes #1C). **Sem migration nova** no #1G-a.
