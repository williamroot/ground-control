# Ground Control — Arquitetura

## Topologia

```
                       Internet
                          │
                 ┌────────▼────────┐   rede: edge
                 │   cloudflared   │   (znuny-dev.was.dev.br)
                 └────────┬────────┘
                          │
                 ┌────────▼────────┐
                 │   znuny-web     │  Apache2 + mod_perl2  (:8080→80)
                 │  (Znuny 7.2.3)  │
                 └────────┬────────┘
        rede: app         │           ┌──────────────┐
                 ┌────────┼───────────┤ znuny-daemon │ bin/otrs.Daemon.pl
                 │        │           └──────────────┘ (foreground/supervisado)
   ┌─────────────▼──┐ ┌───▼────┐ ┌────▼─────────┐
   │  postgres:18   │ │redis:7 │ │ opensearch:2 │   rede: data
   │ schema Znuny   │ │ cache  │ │ single-node  │   (internal: true)
   └────────────────┘ └────────┘ └──────────────┘
```

## Containers

| Serviço | Imagem | Papel | Health |
|---|---|---|---|
| `postgres` | `postgres:18` | DB do Znuny (schema em `public`; `gerti` virá com o sidecar) | `pg_isready` |
| `redis` | `redis:7-alpine` | Cache backend do Znuny (`Cache::Redis` custom) | `redis-cli ping` |
| `opensearch` | `opensearchproject/opensearch:2` | Cluster de busca single-node (security off, dev) | cluster health |
| `znuny-web` | build do tarball 7.2.3 | Apache2 + mod_perl2, serve `/znuny/index.pl` | HTTP login 200 |
| `znuny-daemon` | mesma imagem | `bin/otrs.Daemon.pl` supervisado em foreground | marcador + status |
| `cloudflared` | `cloudflare/cloudflared:latest` | Tunnel `znuny-dev.was.dev.br` (token pendente) | n/a (restarting até token) |

## Redes (segregação)

- **edge** — cloudflared ↔ znuny-web
- **app** — znuny-web/daemon ↔ postgres/redis/opensearch
- **data** — `internal: true`: postgres/redis/opensearch **não roteáveis** de fora do projeto

## Volumes nomeados

- `postgres-data` → `/var/lib/postgresql` (PG18 usa subdir de major-version; **não** `/data`)
- `znuny-var` → `/opt/otrs/var` (article storage)
- `opensearch-data`

## Imagem Znuny

- Base **`debian:bookworm-slim`** (NÃO `perl:5.40` — evita dois perls; mod_perl usa o perl do sistema, CLI usaria 5.40 → `@INC` mismatch quebrava `CheckModules.pl`). Decisão em `DECISIONS.md`.
- Deps Perl: pacotes Debian `lib*-perl`; resto via `cpanm` no mesmo perl do sistema.
- `bin/otrs.CheckModules.pl` roda como **gate de build** — módulo *required* faltando falha o `docker build`.
- Install real em `/opt/otrs`; `/opt/znuny → /opt/otrs` simlink (Znuny hardcoda `/opt/znuny` em apache include/cron). Path web: `/znuny/index.pl`.

## Provisionamento (`znuny/entrypoint.sh`) — automatizado e idempotente

1. Renderiza `Kernel/Config.pm` de `Config.pm.tmpl` com env (DSN, Redis, OpenSearch endpoint, SystemID, FQDN).
2. Espera o Postgres pronto.
3. **Init de DB idempotente**: carrega schema + initial + post-schema **só se** a tabela `valid` não existe; senão loga `schema already present — skipping`.
4. Rebuild SysConfig, garante/cria admin, seta senha deterministicamente, verifica em `users`.
5. Prova alcance Znuny→OpenSearch.
6. Role `web` → exec Apache2 (foreground). Role `daemon` → espera marcador do web, roda `bin/otrs.Daemon.pl` supervisado.

## Cache Redis (custom)

Core Znuny 7.2 só tem `Cache::FileStorable`. Adicionamos `Kernel::System::Cache::Redis` em `Custom/` (primeiro no `@INC`, upgrade-safe) implementando o contrato exato (`Set/Get/Delete/CleanUp`), serialização `Storable`, `SETEX` nativo, índice SET por `Type`. Verificado: 150+ chaves `znuny:*` no Redis, FS bypassed.

## Sidecar Python (`apps/sidecar/`) + infra dev (`infra/`)

Serviço **FastAPI + SQLAlchemy 2 async + Alembic** que detém o domínio
de contratos/consumo/faturamento no schema **`gerti`** (Spec #0). Estado:
**fundação (Plano 1A) + #1C Task 1 prontos e verificados** — gate
`ruff + mypy + pytest` (16 testes, testcontainers) verde nesta localização.

- **Limite de integração com o Znuny:** núcleo Znuny imutável. Escrita
  Znuny via **Generic Interface** (REST); leitura do schema `znuny`
  read-only. Znuny → sidecar via **webhooks HMAC** (GertiHooks.opm,
  Spec #1B — não iniciado) alimentando `gerti.consumption_event`.
- **Multi-tenant:** GUC `app.current_tenant` (SET LOCAL por transação)
  + **FORCE RLS** por tabela `gerti.*`, fail-closed; runtime conecta
  como `gerti_sidecar` (sem BYPASSRLS).
- **Schema compartilhado:** Spec #0 prevê **um cluster Postgres** com
  schemas `znuny` + `gerti`. Hoje o Znuny de prod usa o `postgres:18`
  próprio (schema `public`); o sidecar testa via testcontainers +
  `infra/compose/postgres/init/001_schemas_and_roles.sql`. Convergência
  para cluster único = **item de integração aberto**.
- **`infra/compose/`** = infra **dev** opcional do sidecar
  (postgres/redis/minio) + init SQL + smoke-test. **Separada** da stack
  Znuny de produção (`docker-compose.yml` raiz); não compartilham containers.

### Deploy em prod (profile `gerti`, single-cluster)

3 serviços **gated por `profiles:["gerti"]`** no `docker-compose.yml`
raiz (NÃO sobem num `make up` da stack Znuny — aditivos, Postgres não
reinicia):

| Serviço | Papel | Role DB |
|---|---|---|
| `gerti-db-init` | one-shot idempotente: cria schema `gerti`+roles+RLS no `postgres:18` VIVO (psql superusuário, zero DROP, não toca `public`/`znuny`) | superusuário |
| `sidecar-migrate` | one-shot: `alembic upgrade head` (dono do DDL); `service_completed_successfully` libera o app | `gerti_admin_user` (BYPASSRLS) |
| `sidecar` | FastAPI long-running em `:8001`, redes `data`+`edge` | `gerti_sidecar` (RLS-subject, sem BYPASSRLS) |

Exposto em `api-dev.was.dev.br` (2º hostname no tunnel `znuny-dev`,
token-mode multi-host; ingress via read-modify-write). Runbook em
[`OPS.md`](OPS.md) "Deploy do sidecar"; decisão em
[`DECISIONS.md`](DECISIONS.md) D13.

Detalhe completo: [`INTEGRATION.md`](INTEGRATION.md).

## Landing (`landing/`)

Estático (HTML/CSS/JS), estética mission-control. Deploy próprio independente: nginx + cloudflared → `groundcontrol.was.dev.br`. Não compartilha containers com a stack Znuny. Detalhes em `landing/README.md`.

## Fluxos

- **Request externo** → Cloudflare edge → cloudflared (tunnel) → znuny-web:80 → Apache/mod_perl → Postgres/Redis.
- **Jobs/escalações** → znuny-daemon (independente do web; só sobe após marcador de provisionamento do web).
- **Cache** → toda leitura/escrita de cache do Znuny → Redis (não FS).
