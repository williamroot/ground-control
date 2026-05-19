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
