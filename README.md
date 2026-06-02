# Ground Control

Plataforma de Service Desk **own-source, white-label, MSP-first** — núcleo **Znuny 7.2.3** acoplado em Docker Compose, sob medida para substituir o Tiflux no projeto Gerti e ser revendida por MSPs com a marca delas.

> **Conceito:** *Mission Control.* Cada cliente da MSP é uma órbita; este repositório é a estação de controle que mantém todas no ar — ticketing, contratos, faturamento e telemetria a partir de um único console.

## Status atual

- **Núcleo no ar:** Znuny 7.2.3 (build próprio do tarball oficial) sobre **PostgreSQL 18** — compatível, sem fallback
- **Stack validada:** 24/24 asserts no smoke-test e2e a partir de `down -v` limpo; provisionamento idempotente
- **Cache real:** backend `Kernel::System::Cache::Redis` custom (core 7.2 só tem FileStorable) — 150+ chaves `znuny:*` no Redis
- **Busca:** OpenSearch single-node healthy e alcançável pelo Znuny (indexação completa depende do add-on `Znuny-Elasticsearch` — gap documentado)
- **Em prod:** VPS `100.99.49.110` via Cloudflare Tunnel → `znuny-dev.was.dev.br` (aguardando token do connector)
- **Demo pronta para apresentação:** seed idempotente ([`scripts/seed-demo.sh`](scripts/seed-demo.sh)) cria a operação MSP fictícia "Aurora Móveis" — 5 agentes, 5 clientes, 5 filas, 11 serviços, 3 SLAs, 17 tickets. Credenciais e roteiro em [`.ia/DEMO.md`](.ia/DEMO.md)
- **Sidecar Python:** em [`apps/sidecar/`](apps/sidecar/) — FastAPI + SQLAlchemy + Alembic; **fundação (Plano 1A) + motor de contratos #1C** prontos e verificados (gate `ruff + mypy + pytest`, RLS multi-tenant sob role sem privilégio). Integração com o Znuny em [`.ia/INTEGRATION.md`](.ia/INTEGRATION.md)
- **Portal do Cliente (Ground Desk):** em [`apps/portal/`](apps/portal/) — Nuxt 3 SSR white-label por tenant; login por e-mail (valida no Znuny), visão rica de contratos/saldos (#1F) e **papéis admin × help-desk** (#1H): admin vê contratos+valores, help-desk vê a operação/tickets. Gating server-side (RLS + `require_admin`), least-privilege. No ar em `aurora.was.dev.br` / `technova.was.dev.br`
- **Landing comercial:** em [`landing/`](landing/) — deploy próprio para `groundcontrol.was.dev.br`

## Stack

```
Znuny 7.2.3 (Perl · Apache2 + mod_perl2 · build do tarball oficial)
PostgreSQL 18  ·  Redis 7 (cache backend custom)  ·  OpenSearch 2.x
cloudflared (Cloudflare Tunnel · znuny-dev.was.dev.br)
Docker Compose · 3 redes segregadas (edge / app / data-internal)
Provisionamento 100% automatizado · zero instalador web
Landing: HTML/CSS/JS estático · nginx + cloudflared (groundcontrol.was.dev.br)
```

## Arquitetura

```
ground-control/
├── docker-compose.yml            stack: redes, healthchecks, depends_on
├── docker-compose.override.yml   dev: expõe portas, carrega .env.prod
├── znuny/
│   ├── Dockerfile                imagem do tarball oficial 7.2.3 (debian-slim)
│   ├── entrypoint.sh             provisionamento idempotente
│   ├── Config.pm.tmpl            Kernel/Config.pm renderizado de env
│   └── Cache/Redis.pm            backend Redis custom (upgrade-safe, Custom/)
├── apps/sidecar/                 serviço Python (FastAPI · SQLAlchemy · Alembic) — domínio de contratos
├── infra/compose/                infra DEV do sidecar (separada da stack Znuny)
├── postgres/init/                hooks de init do cluster
├── scripts/smoke-test.sh         teste e2e (24 asserts)
├── scripts/seed-demo.sh          seed idempotente da demo + verificação e2e
├── scripts/seed-demo.pl          motor do seed (API nativa Znuny)
├── landing/                      landing comercial Ground Control (estático)
├── docs/decisions/0001-stack.md  ADR canônico (PG18, base image, gaps)
└── .ia/                          documentação viva (ler antes de mexer)
```

Detalhes em [`.ia/`](.ia/) — overview, arquitetura, decisões, runbook operacional.

## Como subir (dev)

```bash
git clone git@github.com:williamroot/ground-control.git
cd ground-control
make init      # cria .env e .env.prod a partir dos exemplos commitados
make build     # constrói a imagem Znuny (~1-2 min cache quente)
make up        # sobe a stack inteira
make test      # smoke-test e2e (24 asserts) — deve dar FAIL=0
```

Abra <http://localhost:8080/znuny/index.pl>. Super-agente semeado (em `.env`):
`root@localhost` / `ZNUNY_ADMIN_PASSWORD` (troque).

Atalhos: `make logs svc=znuny-web`, `make shell`, `make psql`, `make redis-keys`, `make es-health`, `make reset` (destrói volumes).

## Deploy

Produção em `100.99.49.110` via Cloudflare Tunnel. Passo a passo em [`DEPLOY.md`](DEPLOY.md).

## Documentação

| Arquivo | Conteúdo |
|---|---|
| [`.ia/OVERVIEW.md`](.ia/OVERVIEW.md) | Problema, escopo, terminologia |
| [`.ia/ARCHITECTURE.md`](.ia/ARCHITECTURE.md) | Containers, redes, fluxos, provisionamento |
| [`.ia/OPS.md`](.ia/OPS.md) | Hosts, deploy, runbooks, troubleshooting |
| [`.ia/DEMO.md`](.ia/DEMO.md) | Instância de demonstração: empresa fictícia, credenciais, roteiro de apresentação, como (re)semear |
| [`.ia/DECISIONS.md`](.ia/DECISIONS.md) | ADRs — por que cada escolha |
| [`.ia/INTEGRATION.md`](.ia/INTEGRATION.md) | Sidecar Python ↔ stack Znuny: monorepo, schema `gerti`, RLS, webhooks, built vs pendente |
| [`docs/decisions/0001-stack.md`](docs/decisions/0001-stack.md) | ADR técnico canônico (inglês) |

Engineered by **WAS Soluções em Tecnologia**.
