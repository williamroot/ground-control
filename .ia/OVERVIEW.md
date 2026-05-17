# Ground Control — Overview

## Problema

MSPs que prestam Service Desk hoje pagam SaaS por agente (custo cresce com o time, não com o lucro), não conseguem oferecer um portal com a marca de **cada cliente final** que atendem, e ferramentas genéricas não modelam contratos de MSP (banco de horas, crédito compartilhado, glosa, ciclos de fechamento ≠ faturamento). Os dados moram na casa do fornecedor, com lock-in e extensibilidade limitada.

Ground Control inverte isso: núcleo **own-source** (Znuny), **zero licença por agente**, **white-label por cliente final**, contratos MSP como cidadão de primeira classe, rodando na infra de quem opera.

## Escopo

### Dentro (deste repositório)
- Camada de **infra/orquestração**: Docker Compose acoplado do Znuny 7.2.3 + Postgres 18 + Redis + OpenSearch + Cloudflare Tunnel
- Imagem Znuny construída do **tarball oficial** (sem imagens comunitárias)
- Provisionamento **100% automatizado e idempotente** (zero instalador web)
- Backend de cache Redis custom (core 7.2 não tem)
- Smoke-test e2e (24 asserts) a partir de estado limpo
- **Landing comercial** em `landing/` (estático, deploy próprio)

### Fora (não-objetivos aqui)
- **Sidecar Python** (contratos, faturamento, dashboards) — repo `gerti`, virá depois
- **Portal Cliente Nuxt 3** — repo `gerti`, virá depois
- Indexação completa de documentos no OpenSearch — depende do add-on `Znuny-Elasticsearch` (gap conhecido)
- Multi-tenancy aplicacional do produto — modelado na spec do `gerti`, não nesta camada

> Este repo é o monorepo de **deploy** de toda a plataforma; sidecar/portal serão adicionados quando estabilizarem.

## Terminologia

| Termo | Significado |
|---|---|
| **Znuny** | Fork open-source do OTRS (GPL v3). Núcleo de ticketing/ITSM. Versão 7.2.3 |
| **Sidecar** | Serviço Python/FastAPI com a lógica de produto (contratos etc.) — fora deste repo |
| **Tenant** | Cada cliente final que a MSP atende, com portal white-label próprio |
| **MSP** | Managed Service Provider — quem opera o Ground Control e revende com a marca dele |
| **`.opm`** | Pacote de extensão do Znuny |
| **Ground station / órbita** | Metáfora mission-control: estação = este repo; órbita = cada tenant |
| **PG18** | PostgreSQL 18 — confirmado compatível com Znuny 7.2.3, sem fallback |

## Projetos relacionados

- `gerti` — spec/plano/sidecar/portal (substituição do Tiflux para a Gerti)
- `ground-control-landing` — repo standalone original da landing (consolidado em `landing/` aqui)
- Spec base: `~/projetos/gerti/docs/superpowers/specs/2026-05-12-gerti-servicedesk-znuny-design.md`
