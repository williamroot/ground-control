# ADR 0001 — Layout monorepo

Status: Accepted · 2026-05-12

## Contexto
A Spec #0 prevê 3 artefatos de software (sidecar Python, portal Vue 3 / Nuxt 3, plugin Perl .opm) + infra
declarativa. Cada um tem seu ciclo de build/test, mas evoluem juntos e referenciam contratos
compartilhados (eventos, schemas).

## Decisão
Monorepo único em `gerti/` com:
- `apps/sidecar/` — código Python (FastAPI, workers Celery)
- `apps/portal/` — código Vue 3 + Nuxt 3 (SSR Universal)
- `services/znuny-hooks/` — pacote Perl .opm
- `infra/compose/` — Docker Compose + scripts de provisionamento
- `docs/` — specs, plans, ADRs

## Consequências
+ Mudanças que cruzam camadas (ex.: novo dynamic field) podem ir em um único PR
+ Setup local com um clone só
+ CI pode rodar matriz por camada
− Disciplina exigida: PRs grandes precisam ser revisados por área
